from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import time
import uuid

from repo_catalog.adapters.filesystem.capacity import Capacity
from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.git.parsing import GitParsing, publish_git_acquisition
from repo_catalog.adapters.git.runner import GitRunner, git_env, hook
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.application.repository_identity import endpoint
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import now_us


class GitImporter:
    def __init__(self, store, token):
        self.s, self.token = store, token
        self.model = ParserModel(store.connection)

    def sync(
        self,
        repo,
        job,
        *,
        pr_roots=None,
        change_request_observation_id=None,
        repository_endpoint_id=None,
    ):
        """Collect into catalog3; committed fixed roots are reused across retries."""
        s = self.s
        kind = "pr" if pr_roots else "git"
        request = json.dumps({"roots": pr_roots or []}, sort_keys=True)
        run = s.one(
            "SELECT a.*,p.generation,p.attempt,p.state,p.active_cache_entry_id FROM git_acquisitions a JOIN acquisition_progress p ON p.git_acquisition_id=a.git_acquisition_id WHERE p.job_id=? AND a.repository_uuidv4=? AND a.kind=? AND a.request=? ORDER BY p.generation DESC LIMIT 1",
            (job, repo["repository_uuidv4"], kind, request),
        )
        selected = endpoint(
            s,
            repo["repository_uuidv4"],
            (run["repository_endpoint_id"] if run else None) or repository_endpoint_id,
        )
        attempt = s.one("SELECT current_attempt FROM jobs WHERE job_id=?", (job,))[0]
        if not run:
            generation = s.one(
                "SELECT coalesce(max(p.generation),0)+1 FROM acquisition_progress p JOIN git_acquisitions a ON a.git_acquisition_id=p.git_acquisition_id WHERE a.repository_uuidv4=?",
                (repo["repository_uuidv4"],),
            )[0]
            cache = s.one(
                "SELECT c.*,l.repository_uuidv4,l.path FROM active_cache_entries c JOIN cache_locators l ON l.cache_locator_id=c.cache_locator_id WHERE l.repository_uuidv4=? AND l.access='target_active' AND l.state='available' AND c.state='active' ORDER BY c.generation DESC LIMIT 1",
                (repo["repository_uuidv4"],),
            )
            rid = str(uuid.uuid4())
            with s.transaction():
                if not cache:
                    cid = str(uuid.uuid4())
                    relative = f"cache/{repo['repository_uuidv4']}/{generation}.git"
                    s.execute(
                        "INSERT INTO cache_locators(cache_locator_id,repository_uuidv4,path,access,state) VALUES(?,?,?,'target_active','available')",
                        (cid, repo["repository_uuidv4"], relative),
                    )
                    s.execute(
                        "INSERT INTO active_cache_entries(active_cache_entry_id,cache_locator_id,generation,state,last_used_us,bytes) VALUES(?,?,?,'active',?,0)",
                        (cid, cid, generation, now_us()),
                    )
                    cache = s.one(
                        "SELECT c.*,l.repository_uuidv4,l.path FROM active_cache_entries c JOIN cache_locators l ON l.cache_locator_id=c.cache_locator_id WHERE c.active_cache_entry_id=?",
                        (cid,),
                    )
                s.execute(
                    "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,repository_endpoint_id,endpoint_url,source_id,kind,started_at_us,request) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        rid,
                        repo["repository_uuidv4"],
                        selected["repository_endpoint_id"],
                        selected["url"],
                        repo.get("source_id") if isinstance(repo, dict) else None,
                        kind,
                        now_us(),
                        request,
                    ),
                )
                s.execute(
                    "INSERT INTO acquisition_progress(git_acquisition_id,job_id,attempt,state,generation,active_cache_entry_id) VALUES(?,?,?,'planned',?,?)",
                    (rid, job, attempt, generation, cache["active_cache_entry_id"]),
                )
                s.execute(
                    "INSERT INTO preservation_obligations(git_acquisition_id,cache_locator_id,roots_fixed,structure_done,digest_done,text_done,published) VALUES(?,?,0,0,0,0,0)",
                    (rid, cache["cache_locator_id"]),
                )
                if kind == "git":
                    profile = self.model.ensure_builtin_profile()
                    predecessors = [
                        row[0]
                        for row in s.all(
                            "SELECT d.fact_selection_decision_uuidv4 FROM fact_selection_decisions d JOIN fact_selection_publications p USING(fact_selection_decision_uuidv4) JOIN fact_selection_scopes f USING(fact_selection_scope_uuidv4) WHERE f.repository_uuidv4=? AND f.fact_kind='git' AND f.git_acquisition_id IS NULL AND NOT EXISTS(SELECT 1 FROM fact_selection_predecessors e JOIN fact_selection_publications ep ON ep.fact_selection_decision_uuidv4=e.fact_selection_decision_uuidv4 WHERE e.predecessor_decision_uuidv4=d.fact_selection_decision_uuidv4)",
                            (repo["repository_uuidv4"],),
                        )
                    ]
                    if len(predecessors) > 1:
                        raise CatalogError(
                            "SELECTION_UNRESOLVED",
                            "Resolve Git snapshot selection before starting a new selection",
                        )
                    parsed_result = self.model.create_result(
                        profile,
                        repository_uuidv4=repo["repository_uuidv4"],
                        inputs=[{"git_acquisition_id": rid}],
                        derivation={
                            "kind": "git",
                            "decoder": "git-object-v1",
                            "selection_decision_uuidv4": str(uuid.uuid4()),
                            "selection_predecessors": predecessors,
                        },
                    )
                    s.execute(
                        "INSERT INTO snapshots(snapshot_id,git_acquisition_id,repository_uuidv4,parsed_result_uuidv4,published,generation,created_at_us) VALUES(?,?,?,?,0,?,?)",
                        (
                            rid,
                            rid,
                            repo["repository_uuidv4"],
                            parsed_result,
                            generation,
                            now_us(),
                        ),
                    )
            run = s.one(
                "SELECT a.*,p.generation,p.attempt,p.state,p.active_cache_entry_id FROM git_acquisitions a JOIN acquisition_progress p ON p.git_acquisition_id=a.git_acquisition_id WHERE a.git_acquisition_id=?",
                (rid,),
            )
        elif run["state"] == "published":
            return self.result(repo, run, kind)
        elif run["attempt"] != attempt:
            with s.transaction():
                s.execute(
                    "UPDATE acquisition_progress SET attempt=? WHERE git_acquisition_id=?",
                    (attempt, run["git_acquisition_id"]),
                )
        # Git and PR acquisitions share the same immutable object parser.
        parsed = s.one(
            "SELECT parsed_result_uuidv4 FROM parsed_result_inputs WHERE git_acquisition_id=?",
            (run["git_acquisition_id"],),
        )
        if parsed is None:
            with s.transaction():
                parsed_uuid = self.model.create_result(
                    self.model.ensure_builtin_profile(),
                    repository_uuidv4=repo["repository_uuidv4"],
                    inputs=[{"git_acquisition_id": run["git_acquisition_id"]}],
                    derivation={"kind": "git-pr", "decoder": "git-object-v1"},
                )
        else:
            parsed_uuid = parsed[0]
        self.result_uuid = parsed_uuid
        repo = {**dict(repo), "url": run["endpoint_url"]}
        cache = s.one(
            "SELECT c.*,l.repository_uuidv4,l.path,l.access,l.state AS locator_state FROM active_cache_entries c JOIN cache_locators l ON l.cache_locator_id=c.cache_locator_id WHERE c.active_cache_entry_id=?",
            (run["active_cache_entry_id"],),
        )
        path = (s.path / cache["path"]).resolve()
        if (
            cache["access"] != "target_active"
            or not path.is_relative_to((s.path / "cache").resolve())
            or cache["state"] != "active"
            or cache["locator_state"] != "available"
        ):
            raise CatalogError("CACHE_UNAVAILABLE", "Run cache generation unavailable")
        with FileLock(
            s.path / f"locks/cache-{cache['active_cache_entry_id']}.lock",
            inheritable=True,
        ) as lock:
            baseline = Capacity(s).used()
            try:
                Capacity(s).reserve(job, 1048576)
            except CatalogError:
                from repo_catalog.adapters.filesystem.cache import CacheManager

                CacheManager(s).collect(apply=True, pressure=True)
                Capacity(s).reserve(job, 1048576)
            runner = GitRunner(
                self.token, lock, lambda: Capacity(s).monitor(job, baseline)
            )
            with s.transaction():
                if not s.one(
                    "SELECT 1 FROM cache_leases WHERE active_cache_entry_id=? AND job_id=? AND attempt=?",
                    (cache["active_cache_entry_id"], job, attempt),
                ):
                    s.execute(
                        "INSERT INTO cache_leases(active_cache_entry_id,job_id,attempt,acquired_at_us) VALUES(?,?,?,?)",
                        (cache["active_cache_entry_id"], job, attempt, now_us()),
                    )
            try:
                if not path.exists():
                    advertised = runner.run(["ls-remote", repo["url"]])
                    first = next(
                        (line.split()[0] for line in advertised.splitlines() if line),
                        b"",
                    )
                    fmt = "sha256" if len(first) == 64 else "sha1"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    runner.run(
                        [
                            "init",
                            "--bare",
                            "--template=",
                            "--object-format=" + fmt,
                            str(path),
                        ]
                    )
                fmt = (
                    runner.run(["rev-parse", "--show-object-format"], cwd=path)
                    .strip()
                    .decode()
                )
                if (
                    runner.run(
                        ["rev-parse", "--is-shallow-repository"], cwd=path
                    ).strip()
                    != b"false"
                    or list(path.glob("objects/pack/*.promisor"))
                    or (path / "objects/info/alternates").exists()
                ):
                    raise CatalogError(
                        "INCOMPLETE_CLOSURE",
                        "Cache must have an independent full closure",
                    )
                if run["roots_manifest"]:
                    refs = json.loads(run["roots_manifest"])
                else:
                    namespace = f"refs/intake/{run['git_acquisition_id']}"
                    with s.transaction():
                        s.execute(
                            "UPDATE acquisition_progress SET state='fetching' WHERE git_acquisition_id=?",
                            (run["git_acquisition_id"],),
                        )
                        if run["object_format"] is None:
                            s.execute(
                                "UPDATE git_acquisitions SET object_format=? WHERE git_acquisition_id=?",
                                (fmt, run["git_acquisition_id"]),
                            )
                    specs = (
                        [
                            f"+refs/heads/*:{namespace}/heads/*",
                            f"+refs/tags/*:{namespace}/tags/*",
                        ]
                        if kind == "git"
                        else [
                            f"+{root['ref']}:{namespace}/pr/{i}"
                            for i, root in enumerate(pr_roots)
                        ]
                    )
                    reuse = kind == "pr" and self.reusable_direct_roots(
                        repo, fmt, pr_roots
                    )
                    if reuse:
                        try:
                            for root in pr_roots:
                                runner.run(
                                    ["cat-file", "-e", root["ref"] + "^{commit}"],
                                    cwd=path,
                                )
                        except CatalogError as error:
                            if error.code != "GIT_ERROR":
                                raise
                            reuse = False
                    if reuse:
                        for i, root in enumerate(pr_roots):
                            runner.run(
                                ["update-ref", f"{namespace}/pr/{i}", root["ref"]],
                                cwd=path,
                            )
                    else:
                        runner.transfer(
                            [
                                "fetch",
                                "--atomic",
                                "--no-tags",
                                "--refmap=",
                                "--no-write-fetch-head",
                                repo["url"],
                                *specs,
                            ],
                            cwd=path,
                            timeout=s.config["collection"].get(
                                "git_transfer_timeout_seconds", 300
                            ),
                        )
                    raw = runner.run(
                        [
                            "for-each-ref",
                            "--format=%(refname)%00%(objectname)%00%(objecttype)%00%(*objectname)",
                            namespace + "/",
                        ],
                        cwd=path,
                    )
                    refs = []
                    for line in raw.splitlines():
                        ref, oid, typ, peeled = line.split(b"\0")
                        original = b"refs/" + ref.removeprefix(
                            namespace.encode() + b"/"
                        )
                        item = {
                            "name": original.decode("utf8", "backslashreplace"),
                            "name_b64": base64.b64encode(original).decode(),
                            "oid": oid.decode(),
                            "type": typ.decode(),
                            "peeled": peeled.decode() or None,
                        }
                        if kind == "pr":
                            root = pr_roots[int(item["name"].split("/")[-1])]
                            item.update(
                                role=root["role"],
                                number=root["number"],
                                expected=root["expected"],
                            )
                            if item["oid"] != root["expected"]:
                                raise CatalogError(
                                    "PR_CODE_RACE",
                                    "API and fetched PR code OIDs differ",
                                    retryable=True,
                                )
                        refs.append(item)
                    observed_at_us = now_us()
                    with s.transaction():
                        s.execute(
                            "UPDATE git_acquisitions SET roots_manifest=?,refs_observed_at_us=?,observed_at_us=? WHERE git_acquisition_id=?",
                            (
                                json.dumps(refs),
                                observed_at_us,
                                observed_at_us,
                                run["git_acquisition_id"],
                            ),
                        )
                        s.execute(
                            "UPDATE acquisition_progress SET state='refs_captured' WHERE git_acquisition_id=?",
                            (run["git_acquisition_id"],),
                        )
                        s.execute(
                            "UPDATE preservation_obligations SET roots_fixed=1 WHERE git_acquisition_id=?",
                            (run["git_acquisition_id"],),
                        )
                        for ordinal, r in enumerate(refs):
                            raw_name = base64.b64decode(r["name_b64"])
                            if kind == "git":
                                refkind = (
                                    "head"
                                    if raw_name.startswith(b"refs/heads/")
                                    else "tag"
                                )
                                s.execute(
                                    "INSERT INTO ref_observations(repository_uuidv4,parsed_result_uuidv4,snapshot_id,raw_ref_name,kind,object_format,target_oid,peeled_oid,target_type) VALUES(?,?,?,?,?,?,?,?,?)",
                                    (
                                        repo["repository_uuidv4"],
                                        s.one(
                                            "SELECT parsed_result_uuidv4 FROM snapshots WHERE snapshot_id=?",
                                            (run["git_acquisition_id"],),
                                        )[0],
                                        run["git_acquisition_id"],
                                        raw_name,
                                        refkind,
                                        fmt,
                                        bytes.fromhex(r["oid"]),
                                        bytes.fromhex(r["peeled"])
                                        if r["peeled"]
                                        else None,
                                        r["type"],
                                    ),
                                )
                            root_oid = bytes.fromhex(r["peeled"] or r["oid"])
                            root = s.one(
                                "SELECT acquisition_root_id FROM acquisition_roots WHERE git_acquisition_id=? AND object_format=? AND oid=? AND role='traversal'",
                                (run["git_acquisition_id"], fmt, root_oid),
                            )
                            acquisition_root_id = (
                                root[0]
                                if root
                                else s.execute(
                                    "INSERT INTO acquisition_roots(git_acquisition_id,object_format,oid,role,repository_uuidv4,expected_oid,published) VALUES(?,?,?,'traversal',?,?,0)",
                                    (
                                        run["git_acquisition_id"],
                                        fmt,
                                        root_oid,
                                        repo["repository_uuidv4"],
                                        bytes.fromhex(r["expected"])
                                        if r.get("expected")
                                        else None,
                                    ),
                                ).lastrowid
                            )
                            if kind == "git":
                                s.execute(
                                    "INSERT INTO root_origins(acquisition_root_id,origin_kind,raw_ref_name,source_ordinal,snapshot_id,repository_uuidv4) VALUES(?,'ref',?,?,?,?)",
                                    (
                                        acquisition_root_id,
                                        raw_name,
                                        ordinal,
                                        run["git_acquisition_id"],
                                        repo["repository_uuidv4"],
                                    ),
                                )
                # Even reuse captures this independent acquisition's exact object
                # membership; retained raw bytes avoid a second cat-file read.
                self.import_objects(path, fmt, refs, repo, run, job, lock)
                with s.transaction():
                    publish_git_acquisition(
                        s, run["git_acquisition_id"], repo["repository_uuidv4"]
                    )
                GitParsing(s, self.result_uuid, token=self.token).parse_acquisition(
                    run["git_acquisition_id"], refs
                )
                hook("before_publish")
                self.token.check()
                with s.transaction():
                    active = s.one(
                        "SELECT j.current_attempt,a.state FROM jobs j JOIN job_attempts a ON a.job_id=j.job_id AND a.attempt=j.current_attempt WHERE j.job_id=?",
                        (job,),
                    )
                    progress = s.one(
                        "SELECT attempt FROM acquisition_progress WHERE git_acquisition_id=?",
                        (run["git_acquisition_id"],),
                    )
                    if (
                        active["current_attempt"] != attempt
                        or active["state"] != "running"
                        or progress[0] != attempt
                    ):
                        raise CatalogError(
                            "STALE_ATTEMPT",
                            "Refusing publication from obsolete attempt",
                        )
                    s.execute(
                        "UPDATE preservation_obligations SET structure_done=1,digest_done=1,text_done=1,published=1 WHERE git_acquisition_id=?",
                        (run["git_acquisition_id"],),
                    )
                    s.execute(
                        "UPDATE acquisition_progress SET state='published',ended_at_us=? WHERE git_acquisition_id=?",
                        (now_us(), run["git_acquisition_id"]),
                    )
                    s.execute(
                        "UPDATE acquisition_roots SET published=1 WHERE git_acquisition_id=?",
                        (run["git_acquisition_id"],),
                    )
                    if kind == "git":
                        s.execute(
                            "UPDATE snapshots SET published=1 WHERE snapshot_id=?",
                            (run["git_acquisition_id"],),
                        )
                        incoming = s.one(
                            "SELECT refs_observed_at_us FROM git_acquisitions WHERE git_acquisition_id=?",
                            (run["git_acquisition_id"],),
                        )[0]
                        snapshot = s.one(
                            "SELECT parsed_result_uuidv4 FROM snapshots WHERE snapshot_id=?",
                            (run["git_acquisition_id"],),
                        )
                        profile = self.model.ensure_builtin_profile()
                        self.model.publish_result(snapshot[0])
                        selected_profile = self.model.ensure_scope_profile(
                            profile,
                            repository_uuidv4=repo["repository_uuidv4"],
                            fact_kind="git",
                        )
                        planned = json.loads(
                            s.one(
                                "SELECT derivation_json FROM parsed_results WHERE parsed_result_uuidv4=?",
                                (snapshot[0],),
                            )[0]
                        )
                        if selected_profile is not None:
                            self.model.select_fact(
                                snapshot[0],
                                fact_kind="git",
                                git_acquisition_id=run["git_acquisition_id"],
                            )
                            self.model.select_fact(
                                snapshot[0],
                                fact_kind="git",
                                predecessors=planned["selection_predecessors"],
                                decision_uuid=planned["selection_decision_uuidv4"],
                            )
                        # Fixed-root resume preserves its original remote observation.
                        # A PR-only acquisition cannot establish repository-wide refs.
                        for component in ("structure", "digests", "heads-text", "refs"):
                            s.coverage(
                                repo["repository_uuidv4"],
                                component,
                                "complete",
                                {
                                    "git_acquisition_id": run["git_acquisition_id"],
                                    "parsed_result_uuidv4": snapshot[0],
                                },
                                observed_at_us=incoming,
                            )
                    if kind == "pr":
                        self.model.publish_result(self.result_uuid)
                        scope = self.model.ensure_scope_profile(
                            self.model.ensure_builtin_profile(),
                            repository_uuidv4=repo["repository_uuidv4"],
                            fact_kind="git",
                        )
                        if scope is not None:
                            self.model.select_fact(
                                self.result_uuid,
                                fact_kind="git",
                                git_acquisition_id=run["git_acquisition_id"],
                            )
                    s.publish()
                return self.result(repo, run, kind)
            finally:
                with s.transaction():
                    s.execute(
                        "DELETE FROM cache_leases WHERE active_cache_entry_id=? AND job_id=? AND attempt=?",
                        (cache["active_cache_entry_id"], job, attempt),
                    )
                    s.execute(
                        "UPDATE active_cache_entries SET last_used_us=? WHERE active_cache_entry_id=?",
                        (now_us(), cache["active_cache_entry_id"]),
                    )
                    Capacity(s).release(job)

    @staticmethod
    def result(repo, run, kind):
        return {
            "repository_uuidv4": repo["repository_uuidv4"],
            "git_acquisition_id": run["git_acquisition_id"],
            "snapshot_id": run["git_acquisition_id"] if kind == "git" else None,
            "state": "complete",
            "repository_endpoint_id": run["repository_endpoint_id"],
            "endpoint_url": run["endpoint_url"],
        }

    def ensure(self, table, columns, values, keys):
        """Insert an immutable fact only when absent; conflict triggers stay enabled."""
        items = dict(zip(columns, values))
        where = " AND ".join(f"{name}=?" for name in keys)
        prior = self.s.one(
            f"SELECT * FROM {table} WHERE {where}", tuple(items[name] for name in keys)
        )
        if prior:
            # Observation times and mutable verification flags are separate from bytes.
            ignored = {
                "verified",
                "verified_at_us",
                "pipeline_version",
                "complete",
            }
            for name, value in items.items():
                if name not in ignored and prior[name] != value:
                    raise CatalogError(
                        "INTEGRITY_ERROR",
                        f"Stored {table} fact differs from acquired bytes",
                    )
            if table == "git_objects" and items["verified"] and not prior["verified"]:
                self.s.execute(
                    "UPDATE git_objects SET verified=1 WHERE git_object_id=?",
                    (prior["git_object_id"],),
                )
            return
        self.s.execute(
            f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in values)})",
            values,
        )

    def reusable_direct_roots(self, repo, fmt, roots):
        for root in roots:
            # Symbolic PR heads still require remote observation. Direct related
            # OIDs can reuse this repository's already published full closure.
            if root["role"] == "head" or root["ref"] != root.get("expected"):
                return False
            if not self.s.one(
                "SELECT 1 FROM git_objects g JOIN repository_object_sources p ON p.git_object_id=g.git_object_id JOIN acquisition_progress r ON r.git_acquisition_id=p.git_acquisition_id WHERE g.object_format=? AND g.oid=? AND g.type='commit' AND g.verified=1 AND p.repository_uuidv4=? AND r.state='published' LIMIT 1",
                (fmt, bytes.fromhex(root["ref"]), repo["repository_uuidv4"]),
            ):
                return False
        return bool(roots)

    def import_objects(self, path, fmt, refs, repo, run, job, lock):
        s = self.s
        capacity = Capacity(s)
        next_capacity_scan = 0.0
        used = 0
        roots = b"".join(
            oid.encode() + b"\n" for oid in sorted({r["oid"] for r in refs})
        )
        spool = s.path / "work" / f"{run['git_acquisition_id']}.objects"
        with spool.open("w+b") as out:
            p = subprocess.run(
                [
                    "git",
                    "--no-replace-objects",
                    "rev-list",
                    "--objects",
                    "--no-object-names",
                    "--stdin",
                ],
                cwd=path,
                input=roots,
                stdout=out,
                stderr=subprocess.PIPE,
                env=git_env(),
                pass_fds=(lock.fd,),
            )
            if p.returncode:
                raise CatalogError(
                    "INCOMPLETE_CLOSURE", "Unable to enumerate fixed object roots"
                )
            out.seek(0)
            pending = s.path / "work" / f"{run['git_acquisition_id']}.pending-objects"
            with pending.open("w+b") as requests:
                for line in out:
                    self.token.check()
                    obj = s.one(
                        "SELECT * FROM git_objects WHERE object_format=? AND oid=?",
                        (fmt, bytes.fromhex(line.strip().decode())),
                    )
                    reusable = (
                        obj is not None
                        and obj["verified"]
                        and s.one(
                            "SELECT 1 FROM git_object_payloads b WHERE b.git_object_id=? AND NOT EXISTS(SELECT 1 FROM payload_quarantine q WHERE q.sha256=b.payload_sha256)",
                            (obj["git_object_id"],),
                        )
                    )
                    if reusable:
                        # The fixed-root walk establishes this repository's
                        # reachability. Reuse durable, verified object data;
                        # incomplete staged structures still enter cat-file.
                        self.source(obj["git_object_id"], repo, run)
                    else:
                        requests.write(line)
            # Feed requested OIDs from disk. cat-file can stream a huge blob with bounded memory.
            requests = pending.open("rb")
            reader = subprocess.Popen(
                ["git", "--no-replace-objects", "cat-file", "--batch"],
                cwd=path,
                stdin=requests,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=git_env(),
                pass_fds=(lock.fd,),
            )
            try:
                while True:
                    self.token.check()
                    header = reader.stdout.readline()
                    if not header:
                        break
                    parts = header.rstrip(b"\n").split()
                    if len(parts) != 3 or parts[1] not in (
                        b"blob",
                        b"commit",
                        b"tree",
                        b"tag",
                    ):
                        raise CatalogError(
                            "INCOMPLETE_CLOSURE",
                            "Missing or malformed Git batch object",
                        )
                    oid, typ, size = parts[0], parts[1].decode(), int(parts[2])
                    data = bytearray()
                    hashes = {a: hashlib.new(a) for a in ("md5", "sha1", "sha256")}
                    git_hash = hashlib.new(fmt)
                    git_hash.update(f"{typ} {size}\0".encode())
                    remaining = size
                    while remaining:
                        self.token.check()
                        chunk = reader.stdout.read(
                            min(remaining, s.config["collection"]["blob_chunk_bytes"])
                        )
                        if not chunk:
                            raise CatalogError(
                                "INCOMPLETE_CLOSURE", "Truncated Git object payload"
                            )
                        remaining -= len(chunk)
                        git_hash.update(chunk)
                        for h in hashes.values():
                            h.update(chunk)
                        if data is not None:
                            data.extend(chunk)
                        if remaining == 0 or size - remaining >= 1048576:
                            # Physical headroom includes SQLite, journals and work spools.
                            # Recursive allocation scans are bounded by time, rather
                            # than repeated for every tiny object in a growing spool.
                            # Physical free space is still checked at each chunk.
                            instant = time.monotonic()
                            if instant >= next_capacity_scan:
                                used = capacity.used()
                                next_capacity_scan = instant + 0.5
                            if used > s.config["cache"]["max_bytes"]:
                                from repo_catalog.domain.models import Waiting

                                raise Waiting(
                                    "CAPACITY_WAIT",
                                    "Object import exceeded managed budget",
                                    retryable=True,
                                )
                            import shutil

                            if (
                                shutil.disk_usage(s.path).free
                                < s.config["cache"]["min_free_bytes"]
                            ):
                                from repo_catalog.domain.models import Waiting

                                raise Waiting(
                                    "CAPACITY_WAIT",
                                    "Object import exhausted physical headroom",
                                    retryable=True,
                                )
                        hook("mid_blob") if typ == "blob" else None
                    if (
                        reader.stdout.read(1) != b"\n"
                        or git_hash.hexdigest().encode() != oid
                    ):
                        raise CatalogError(
                            "INTEGRITY_ERROR",
                            "Git object OID or batch framing mismatch",
                        )
                    raw_bytes = bytes(data)
                    try:
                        with s.transaction():
                            payload = intern_payload(
                                s.connection,
                                raw_bytes,
                                representation="git-object-raw-v1",
                            )
                            if typ == "blob":
                                self.save_blob(
                                    fmt, oid, size, hashes, repo, run, raw_bytes
                                )
                            else:
                                self.ensure(
                                    "git_objects",
                                    (
                                        "object_format",
                                        "oid",
                                        "type",
                                        "size",
                                        "verified",
                                    ),
                                    (fmt, bytes.fromhex(oid.decode()), typ, size, 1),
                                    ("object_format", "oid"),
                                )
                                self.source(
                                    s.git_object_id(fmt, bytes.fromhex(oid.decode())),
                                    repo,
                                    run,
                                )
                            obj = s.git_object_id(fmt, bytes.fromhex(oid.decode()))
                            self.ensure(
                                "git_object_payloads",
                                (
                                    "git_object_id",
                                    "payload_representation",
                                    "payload_sha256",
                                ),
                                (obj, payload.representation, payload.sha256),
                                ("git_object_id",),
                            )
                    except CatalogError as error:
                        if error.code not in (
                            "PAYLOAD_CORRUPTION",
                            "PAYLOAD_HASH_COLLISION",
                        ):
                            raise
                        from repo_catalog.adapters.sqlite.cas_integrity import (
                            stage_verified_payload,
                        )
                        from repo_catalog.domain.payload import PayloadRef

                        with s.transaction():
                            stage_verified_payload(
                                s.connection,
                                raw_bytes,
                                PayloadRef(
                                    "git-object-raw-v1", hashes["sha256"].digest()
                                ),
                                {
                                    "git_acquisition_id": run["git_acquisition_id"],
                                    "repository_uuidv4": repo["repository_uuidv4"],
                                    "object_format": fmt,
                                    "oid": oid.decode(),
                                    "object_type": typ,
                                    "byte_length": size,
                                },
                                reason=error.code,
                            )
                        raise
                if reader.wait() != 0:
                    raise CatalogError("INCOMPLETE_CLOSURE", "cat-file failed")
            finally:
                if reader.poll() is None:
                    reader.terminate()
                    reader.wait()
                requests.close()
                pending.unlink()
        spool.unlink()
        hook("after_digest")

    def source(self, obj, repo, run):
        self.ensure(
            "repository_object_sources",
            ("repository_uuidv4", "git_object_id", "git_acquisition_id"),
            (repo["repository_uuidv4"], obj, run["git_acquisition_id"]),
            ("repository_uuidv4", "git_object_id", "git_acquisition_id"),
        )

    def save_blob(self, fmt, oid, size, hashes, repo, run, raw_bytes):
        s = self.s
        raw = bytes.fromhex(oid.decode())
        previous = s.one(
            "SELECT c.content_id,c.byte_length FROM git_objects g JOIN blob_content_map b ON b.git_object_id=g.git_object_id JOIN contents c ON c.content_id=b.content_id WHERE g.object_format=? AND g.oid=?",
            (fmt, raw),
        )
        if previous and previous["byte_length"] != size:
            raise CatalogError(
                "INTEGRITY_ERROR", "Existing OID maps to different raw length"
            )
        self.ensure(
            "git_objects",
            ("object_format", "oid", "type", "size", "verified"),
            (fmt, raw, "blob", size, 1),
            ("object_format", "oid"),
        )
        obj = s.git_object_id(fmt, raw)
        if previous:
            cid = previous["content_id"]
        else:
            candidates = s.all(
                "SELECT c.content_id FROM contents c JOIN content_digests d ON d.content_id=c.content_id WHERE d.algorithm='sha256' AND d.digest=? AND c.byte_length=?",
                (hashes["sha256"].digest(), size),
            )
            cid = None
            for candidate in candidates:
                digests = {
                    r["algorithm"]: r["digest"]
                    for r in s.all(
                        "SELECT * FROM content_digests WHERE content_id=?",
                        (candidate["content_id"],),
                    )
                }
                existing = s.one(
                    "SELECT sb.body FROM blob_content_map b JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes sb ON sb.sha256=p.payload_sha256 WHERE b.content_id=? LIMIT 1",
                    (candidate["content_id"],),
                )
                if (
                    existing
                    and existing[0] == raw_bytes
                    and all(digests.get(a) == h.digest() for a, h in hashes.items())
                ):
                    cid = candidate["content_id"]
                    break
            if cid is None:
                cid = s.execute(
                    "INSERT INTO contents(byte_length,created_at_us) VALUES(?,?)",
                    (size, now_us()),
                ).lastrowid
            s.execute(
                "INSERT INTO blob_content_map(git_object_id,content_id,git_acquisition_id) VALUES(?,?,?)",
                (obj, cid, run["git_acquisition_id"]),
            )
        for algo, h in hashes.items():
            self.ensure(
                "content_digests",
                (
                    "content_id",
                    "representation",
                    "algorithm",
                    "digest",
                    "verified_at_us",
                    "pipeline_version",
                ),
                (cid, "raw-content-v1", algo, h.digest(), now_us(), "v1"),
                ("content_id", "representation", "algorithm"),
            )
        self.source(obj, repo, run)
