from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import time
import uuid

from repo_catalog.adapters.filesystem.capacity import Capacity
from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.git.parsing import GitParsing
from repo_catalog.adapters.git.runner import GitRunner, git_env, hook
from repo_catalog.application.repository_identity import endpoint
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import now_us


class GitImporter:
    def __init__(self, store, token):
        self.s, self.token = store, token

    def sync(
        self,
        repo,
        job,
        *,
        pr_roots=None,
        code_assessment_id=None,
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
                    "INSERT INTO preservation_obligations(git_acquisition_id,cache_locator_id,roots_fixed,structure_done,digest_done,text_done,complete) VALUES(?,?,0,0,0,0,0)",
                    (rid, cache["cache_locator_id"]),
                )
                if kind == "git":
                    heads = s.all(
                        "SELECT snapshot_id FROM snapshots s WHERE repository_uuidv4=? AND complete=1 AND NOT EXISTS(SELECT 1 FROM snapshots n WHERE n.predecessor_snapshot_id=s.snapshot_id AND n.complete=1)",
                        (repo["repository_uuidv4"],),
                    )
                    if len(heads) > 1:
                        raise CatalogError(
                            "SELECTION_UNRESOLVED",
                            "Git ref captures have unresolved divergent heads; use an explicit snapshot",
                        )
                    s.execute(
                        "INSERT INTO snapshots(snapshot_id,git_acquisition_id,repository_uuidv4,predecessor_snapshot_id,complete,generation,created_at_us) VALUES(?,?,?,?,0,?,?)",
                        (
                            rid,
                            rid,
                            repo["repository_uuidv4"],
                            heads[0][0] if heads else None,
                            generation,
                            now_us(),
                        ),
                    )
            run = s.one(
                "SELECT a.*,p.generation,p.attempt,p.state,p.active_cache_entry_id FROM git_acquisitions a JOIN acquisition_progress p ON p.git_acquisition_id=a.git_acquisition_id WHERE a.git_acquisition_id=?",
                (rid,),
            )
        elif run["state"] == "complete":
            return self.result(repo, run, kind)
        elif run["attempt"] != attempt:
            with s.transaction():
                s.execute(
                    "UPDATE acquisition_progress SET attempt=? WHERE git_acquisition_id=?",
                    (attempt, run["git_acquisition_id"]),
                )
        self.parser = GitParsing(s, repo["repository_uuidv4"], token=self.token)
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
                                    "INSERT INTO ref_observations(repository_uuidv4,snapshot_id,raw_ref_name,kind,object_format,target_oid,peeled_oid,target_type) VALUES(?,?,?,?,?,?,?,?)",
                                    (
                                        repo["repository_uuidv4"],
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
                            root_role = "traversal" if kind == "git" else r["role"]
                            root = s.one(
                                "SELECT acquisition_root_id FROM acquisition_roots WHERE git_acquisition_id=? AND object_format=? AND oid=? AND role=?",
                                (run["git_acquisition_id"], fmt, root_oid, root_role),
                            )
                            acquisition_root_id = (
                                root[0]
                                if root
                                else s.execute(
                                    "INSERT INTO acquisition_roots(git_acquisition_id,object_format,oid,role,repository_uuidv4,expected_oid,complete) VALUES(?,?,?,?,?,?,0)",
                                    (
                                        run["git_acquisition_id"],
                                        fmt,
                                        root_oid,
                                        root_role,
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
                            elif code_assessment_id is not None:
                                assessment = s.one(
                                    "SELECT change_request_id FROM code_assessments WHERE code_assessment_id=? AND repository_uuidv4=?",
                                    (code_assessment_id, repo["repository_uuidv4"]),
                                )
                                if assessment is None:
                                    raise CatalogError(
                                        "NOT_FOUND",
                                        "Exact PR code assessment is missing",
                                    )
                                s.execute(
                                    "INSERT INTO root_origins(acquisition_root_id,origin_kind,source_ordinal,change_request_id,code_assessment_id,repository_uuidv4) VALUES(?,'pr_role',?,?,?,?)",
                                    (
                                        acquisition_root_id,
                                        ordinal,
                                        assessment[0],
                                        code_assessment_id,
                                        repo["repository_uuidv4"],
                                    ),
                                )
                # Even reuse captures this independent acquisition's exact object
                # membership; retained raw bytes avoid a second cat-file read.
                self.import_objects(path, fmt, refs, repo, run, job, lock)
                self.parser.parse_acquisition(run["git_acquisition_id"], refs)
                self.parser.validate_acquisition(run["git_acquisition_id"])
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
                        "UPDATE preservation_obligations SET structure_done=1,digest_done=1,text_done=1,complete=1 WHERE git_acquisition_id=?",
                        (run["git_acquisition_id"],),
                    )
                    s.execute(
                        "UPDATE acquisition_progress SET state='complete',ended_at_us=? WHERE git_acquisition_id=?",
                        (now_us(), run["git_acquisition_id"]),
                    )
                    s.execute(
                        "UPDATE acquisition_roots SET complete=1 WHERE git_acquisition_id=?",
                        (run["git_acquisition_id"],),
                    )
                    if kind == "git":
                        s.execute(
                            "UPDATE snapshots SET complete=1 WHERE snapshot_id=?",
                            (run["git_acquisition_id"],),
                        )
                        incoming = s.one(
                            "SELECT refs_observed_at_us FROM git_acquisitions WHERE git_acquisition_id=?",
                            (run["git_acquisition_id"],),
                        )[0]
                        # Fixed-root resume preserves its original remote observation.
                        # A PR-only acquisition cannot establish repository-wide refs.
                        for component in ("structure", "digests", "heads-text", "refs"):
                            s.coverage(
                                repo["repository_uuidv4"],
                                component,
                                "complete",
                                {
                                    "git_acquisition_id": run["git_acquisition_id"],
                                    "snapshot_id": run["git_acquisition_id"],
                                },
                                observed_at_us=incoming,
                            )
                    s.advance_local_revision()
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
            # OIDs can reuse this repository's already complete full closure.
            if root["role"] == "head" or root["ref"] != root.get("expected"):
                return False
            if not self.s.one(
                "SELECT 1 FROM available_git_objects g JOIN repository_object_sources p ON p.git_object_id=g.git_object_id JOIN acquisition_progress r ON r.git_acquisition_id=p.git_acquisition_id WHERE g.object_format=? AND g.oid=? AND g.type='commit' AND g.verified=1 AND p.repository_uuidv4=? AND r.state='complete' LIMIT 1",
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
                        "SELECT * FROM available_git_objects WHERE object_format=? AND oid=?",
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
                            self.parser.install_object(
                                fmt,
                                bytes.fromhex(oid.decode()),
                                typ,
                                raw_bytes,
                                acquisition=run["git_acquisition_id"],
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
        with self.s.transaction():
            before = self.s.connection.total_changes
            self.ensure(
                "repository_object_sources",
                ("repository_uuidv4", "git_object_id", "git_acquisition_id"),
                (repo["repository_uuidv4"], obj, run["git_acquisition_id"]),
                ("repository_uuidv4", "git_object_id", "git_acquisition_id"),
            )
            if self.s.connection.total_changes != before:
                self.s.advance_local_revision()
