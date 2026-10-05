from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import time
import uuid

from repo_catalog.adapters.filesystem.capacity import Capacity
from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.git.runner import GitRunner, git_env, hook
from repo_catalog.domain.models import CatalogError, now


class GitImporter:
    def __init__(self, store, token):
        self.s, self.token = store, token

    def sync(self, repo, job, *, pr_roots=None, observation_id=None):
        s = self.s
        kind = "pr" if pr_roots else "git"
        request = json.dumps(pr_roots or {}, sort_keys=True)
        run = s.one(
            "SELECT * FROM collection_runs WHERE job_id=? AND repo_id=? AND kind=? AND request=? AND state!='published' ORDER BY generation DESC LIMIT 1",
            (job, repo["id"], kind, request),
        )
        if not run:
            generation = s.one(
                "SELECT coalesce(max(generation),0)+1 FROM collection_runs WHERE repo_id=?",
                (repo["id"],),
            )[0]
            cache = s.one(
                "SELECT * FROM cache_entries WHERE repo_id=? AND state='available' ORDER BY generation DESC LIMIT 1",
                (repo["id"],),
            )
            if not cache:
                cid = str(uuid.uuid4())
                relative = f"cache/{repo['id']}/{generation}.git"
                with s.transaction():
                    s.execute(
                        "INSERT INTO cache_entries VALUES(?,?,?,?,?,?,?)",
                        (
                            cid,
                            repo["id"],
                            generation,
                            relative,
                            "available",
                            time.time(),
                            0,
                        ),
                    )
                cache = s.one("SELECT * FROM cache_entries WHERE id=?", (cid,))
            rid = str(uuid.uuid4())
            attempt = s.one("SELECT attempt FROM jobs WHERE id=?", (job,))[0]
            with s.transaction():
                s.execute(
                    "INSERT INTO collection_runs(id,job_id,repo_id,cache_id,generation,attempt,state,started_at,kind,request) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        rid,
                        job,
                        repo["id"],
                        cache["id"],
                        generation,
                        attempt,
                        "planned",
                        now(),
                        kind,
                        request,
                    ),
                )
                s.execute(
                    "INSERT INTO preservation_obligations(run_id,cache_id) VALUES(?,?)",
                    (rid, cache["id"]),
                )
                if kind == "git":
                    s.execute(
                        "INSERT INTO snapshots VALUES(?,?,?,?,0,?)",
                        (rid, rid, repo["id"], generation, now()),
                    )
            run = s.one("SELECT * FROM collection_runs WHERE id=?", (rid,))
        attempt = getattr(
            s,
            "expected_attempt",
            s.one("SELECT attempt FROM jobs WHERE id=?", (job,))[0],
        )
        if run["attempt"] != attempt:
            with s.transaction():
                s.execute(
                    "UPDATE collection_runs SET attempt=? WHERE id=?",
                    (attempt, run["id"]),
                )
            run = s.one("SELECT * FROM collection_runs WHERE id=?", (run["id"],))
        cache = s.one("SELECT * FROM cache_entries WHERE id=?", (run["cache_id"],))
        path = (s.path / cache["path"]).resolve()
        if not path.is_relative_to(s.path / "cache") or cache["state"] != "available":
            raise CatalogError("CACHE_UNAVAILABLE", "Run cache generation unavailable")
        with FileLock(
            s.path / f"locks/cache-{cache['id']}.lock", inheritable=True
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
                s.execute(
                    "INSERT OR REPLACE INTO cache_leases VALUES(?,?,?,?)",
                    (
                        cache["id"],
                        job,
                        s.one("SELECT attempt FROM jobs WHERE id=?", (job,))[0],
                        now(),
                    ),
                )
            try:
                if not path.exists():
                    # Format is detected from successful remote ref advertisement, never from dates.
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
                        "Shallow/promisor/alternate cache is not a full independent closure",
                    )
                if run["roots_manifest"]:
                    refs = json.loads(run["roots_manifest"])
                else:
                    namespace = f"refs/intake/{run['id']}"
                    with s.transaction():
                        s.execute(
                            "UPDATE collection_runs SET state='fetching',object_format=? WHERE id=?",
                            (fmt, run["id"]),
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
                        suffix = ref.removeprefix(namespace.encode() + b"/")
                        original = b"refs/" + suffix
                        refs.append(
                            {
                                "name": original.decode("utf8", "backslashreplace"),
                                "name_b64": base64.b64encode(original).decode(),
                                "oid": oid.decode(),
                                "type": typ.decode(),
                                "peeled": peeled.decode() or None,
                            }
                        )
                    if kind == "pr":
                        for r in refs:
                            root = pr_roots[int(r["name"].split("/")[-1])]
                            r.update(
                                role=root["role"],
                                number=root["number"],
                                expected=root["expected"],
                            )
                            if r["oid"] != root["expected"]:
                                raise CatalogError(
                                    "PR_CODE_RACE",
                                    "API and fetched PR code OIDs differ",
                                    retryable=True,
                                )
                    with s.transaction():
                        s.execute(
                            "UPDATE collection_runs SET state='refs_captured',roots_manifest=?,refs_at=?,object_format=? WHERE id=?",
                            (json.dumps(refs), now(), fmt, run["id"]),
                        )
                        s.execute(
                            "UPDATE preservation_obligations SET roots_fixed=1 WHERE run_id=?",
                            (run["id"],),
                        )
                        for r in refs:
                            if kind == "git":
                                refkind = (
                                    "head"
                                    if r["name"].startswith("refs/heads/")
                                    else "tag"
                                )
                                s.execute(
                                    "INSERT INTO ref_observations VALUES(?,?,?,?,?,?,?)",
                                    (
                                        run["id"],
                                        base64.b64decode(r["name_b64"]),
                                        refkind,
                                        fmt,
                                        bytes.fromhex(r["oid"]),
                                        bytes.fromhex(r["peeled"])
                                        if r["peeled"]
                                        else None,
                                        r["type"],
                                    ),
                                )
                            s.execute(
                                "INSERT INTO acquisition_roots(run_id,repo_id,object_format,oid,role,pr_number,observation_id,expected_oid) VALUES(?,?,?,?,?,?,?,?)",
                                (
                                    run["id"],
                                    repo["id"],
                                    fmt,
                                    bytes.fromhex(r["oid"]),
                                    r.get(
                                        "role",
                                        "head"
                                        if r["name"].startswith("refs/heads/")
                                        else "tag",
                                    ),
                                    r.get("number"),
                                    observation_id,
                                    r.get("expected"),
                                ),
                            )
                if kind != "pr" or not self.reusable_direct_roots(repo, fmt, pr_roots):
                    self.import_objects(path, fmt, refs, repo, run, job, lock)
                self.manifests(fmt, refs, job)
                # Required durable text is only all observed heads tips, not all historical blobs.
                required = s.all(
                    "SELECT DISTINCT b.object_id FROM root_manifest_entries e JOIN blob_content_map b ON b.object_id=e.object_id WHERE e.tree_id IN (SELECT c.tree_id FROM acquisition_roots r JOIN git_objects g ON g.object_format=r.object_format AND g.oid=r.oid JOIN commits c ON c.object_id=g.id WHERE r.run_id=? AND r.role='head')",
                    (run["id"],),
                )
                for item in required:
                    self.preserve_text(path, fmt, item[0], run, runner)
                hook("before_publish")
                self.token.check()
                with s.transaction():
                    current_attempt = s.one(
                        "SELECT attempt,state FROM jobs WHERE id=?", (job,)
                    )
                    run_attempt = s.one(
                        "SELECT attempt,state FROM collection_runs WHERE id=?",
                        (run["id"],),
                    )
                    if (
                        current_attempt["attempt"] != attempt
                        or current_attempt["state"] != "running"
                        or run_attempt["attempt"] != attempt
                    ):
                        raise CatalogError(
                            "STALE_ATTEMPT",
                            "Refusing publication from an obsolete attempt",
                        )
                    s.execute(
                        "UPDATE preservation_obligations SET structure_done=1,digest_done=1,text_done=1,published=1 WHERE run_id=?",
                        (run["id"],),
                    )
                    s.execute(
                        "UPDATE collection_runs SET state='published',ended_at=? WHERE id=?",
                        (now(), run["id"]),
                    )
                    s.execute(
                        "UPDATE acquisition_roots SET published=1 WHERE run_id=?",
                        (run["id"],),
                    )
                    if kind == "git":
                        s.execute(
                            "UPDATE snapshots SET published=1 WHERE id=?", (run["id"],)
                        )
                        current = s.one(
                            "SELECT generation FROM snapshots WHERE id=(SELECT current_snapshot FROM repositories WHERE id=?)",
                            (repo["id"],),
                        )
                        if not current or current[0] < run["generation"]:
                            s.execute(
                                "UPDATE repositories SET current_snapshot=? WHERE id=?",
                                (run["id"], repo["id"]),
                            )
                    for component in ("structure", "digests", "heads-text", "refs"):
                        s.coverage(run["id"], component, "complete")
                    s.publish()
                return {
                    "repo_id": repo["id"],
                    "run_id": run["id"],
                    "snapshot_id": run["id"] if kind == "git" else None,
                    "state": "complete",
                }
            finally:
                with s.transaction():
                    s.execute(
                        "DELETE FROM cache_leases WHERE cache_id=? AND job_id=?",
                        (cache["id"], job),
                    )
                    s.execute(
                        "UPDATE cache_entries SET last_used=? WHERE id=?",
                        (time.time(), cache["id"]),
                    )
                    Capacity(s).release(job)

    def reusable_direct_roots(self, repo, fmt, roots):
        for root in roots:
            # Symbolic PR heads still require remote observation. Direct related
            # OIDs can reuse this repository's already published full closure.
            if root["role"] == "head" or root["ref"] != root.get("expected"):
                return False
            if not self.s.one(
                "SELECT 1 FROM git_objects g JOIN repository_object_sources p ON p.object_id=g.id JOIN collection_runs r ON r.id=p.run_id WHERE g.object_format=? AND g.oid=? AND g.type='commit' AND g.verified=1 AND p.repo_id=? AND r.state='published' LIMIT 1",
                (fmt, bytes.fromhex(root["ref"]), repo["id"]),
            ):
                return False
        return bool(roots)

    def import_objects(self, path, fmt, refs, repo, run, job, lock):
        s = self.s
        capacity = Capacity(s)
        next_capacity_scan = 0.0
        used = 0
        roots = b"".join(r["oid"].encode() + b"\n" for r in refs)
        spool = s.path / "work" / f"{run['id']}.objects"
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
            pending = s.path / "work" / f"{run['id']}.pending-objects"
            with pending.open("w+b") as requests:
                for line in out:
                    self.token.check()
                    obj = s.one(
                        "SELECT * FROM git_objects WHERE object_format=? AND oid=?",
                        (fmt, bytes.fromhex(line.strip().decode())),
                    )
                    reusable = obj is not None and obj["verified"]
                    if reusable and obj["type"] == "blob":
                        reusable = (
                            s.one(
                                "SELECT count(*) FROM blob_content_map b JOIN content_digests d ON d.content_id=b.content_id WHERE b.object_id=? AND d.representation='raw-content-v1'",
                                (obj["id"],),
                            )[0]
                            == 3
                        )
                    elif reusable:
                        reusable = self.parsed(obj["id"], obj["type"])
                    if reusable:
                        # The fixed-root walk establishes this repository's
                        # reachability. Reuse durable, verified object data;
                        # incomplete staged structures still enter cat-file.
                        self.source(obj["id"], repo, run)
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
                    data = bytearray() if typ != "blob" else None
                    hashes = {a: hashlib.new(a) for a in ("md5", "sha1", "sha256")}
                    git_hash = hashlib.new(fmt)
                    git_hash.update(f"{typ} {size}\0".encode())
                    remaining = size
                    text_buffer = (
                        bytearray() if typ == "blob" and size <= 8388608 else None
                    )
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
                        if text_buffer is not None:
                            text_buffer.extend(chunk)
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
                    existing = s.one(
                        "SELECT * FROM git_objects WHERE object_format=? AND oid=?",
                        (fmt, bytes.fromhex(oid.decode())),
                    )
                    if typ == "blob":
                        text_state = "oversize"
                        if text_buffer is not None:
                            try:
                                text_buffer.decode("utf8", "strict")
                                text_state = (
                                    "nul" if b"\0" in text_buffer else "eligible"
                                )
                            except UnicodeDecodeError:
                                text_state = "non_utf8"
                        self.save_blob(fmt, oid, size, hashes, text_state, repo, run)
                    else:
                        with s.transaction():
                            s.execute(
                                "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES(?,?,?,?,1) ON CONFLICT(object_format,oid) DO NOTHING",
                                (fmt, bytes.fromhex(oid.decode()), typ, size),
                            )
                            obj = s.object_id(fmt, bytes.fromhex(oid.decode()))
                            self.source(obj, repo, run)
                        # Deferred parsing allows arbitrary rev-list object order.
                        raw_path = s.path / "work" / f"{run['id']}-{oid.decode()}.raw"
                        if existing is None or not self.parsed(obj, typ):
                            raw_path.write_bytes(data)
                if reader.wait() != 0:
                    raise CatalogError("INCOMPLETE_CLOSURE", "cat-file failed")
            finally:
                if reader.poll() is None:
                    reader.terminate()
                    reader.wait()
                requests.close()
                pending.unlink()
        spool.unlink()
        for file in sorted((s.path / "work").glob(f"{run['id']}-*.raw")):
            self.token.check()
            oid = bytes.fromhex(file.name.split("-")[-1].removesuffix(".raw"))
            obj = s.one(
                "SELECT * FROM git_objects WHERE object_format=? AND oid=?", (fmt, oid)
            )
            payload = file.read_bytes()
            with s.transaction():
                self.parse(obj, payload, fmt)
            file.unlink()
        hook("after_digest")

    def source(self, obj, repo, run):
        prior = self.s.one(
            "SELECT 1 FROM repository_object_sources p JOIN collection_runs r ON r.id=p.run_id WHERE p.repo_id=? AND p.object_id=? AND r.state='published'",
            (repo["id"], obj),
        )
        if not prior:
            self.s.execute(
                "INSERT OR IGNORE INTO repository_object_sources VALUES(?,?,?)",
                (repo["id"], obj, run["id"]),
            )

    def save_blob(self, fmt, oid, size, hashes, state, repo, run):
        s = self.s
        raw = bytes.fromhex(oid.decode())
        previous = s.one(
            "SELECT c.id,c.byte_length,d.digest FROM git_objects g JOIN blob_content_map b ON b.object_id=g.id JOIN contents c ON c.id=b.content_id JOIN content_digests d ON d.content_id=c.id AND d.algorithm='sha256' WHERE g.object_format=? AND g.oid=?",
            (fmt, raw),
        )
        if previous and (
            previous["digest"] != hashes["sha256"].digest()
            or previous["byte_length"] != size
        ):
            raise CatalogError(
                "INTEGRITY_ERROR", "Existing OID maps to different raw content"
            )
        with s.transaction():
            s.execute(
                "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES(?,?,'blob',?,1) ON CONFLICT(object_format,oid) DO NOTHING",
                (fmt, raw, size),
            )
            obj = s.object_id(fmt, raw)
            if not previous:
                candidates = s.all(
                    "SELECT c.id FROM contents c JOIN content_digests d ON d.content_id=c.id WHERE d.algorithm='sha256' AND d.digest=? AND c.byte_length=?",
                    (hashes["sha256"].digest(), size),
                )
                cid = None
                for candidate in candidates:
                    digests = {
                        r["algorithm"]: r["digest"]
                        for r in s.all(
                            "SELECT * FROM content_digests WHERE content_id=?",
                            (candidate["id"],),
                        )
                    }
                    if all(digests.get(a) == h.digest() for a, h in hashes.items()):
                        cid = candidate["id"]
                        break
                if cid is None:
                    cid = s.execute(
                        "INSERT INTO contents(byte_length,text_state,created_at) VALUES(?,?,?)",
                        (size, state, now()),
                    ).lastrowid
                for algo, h in hashes.items():
                    s.execute(
                        "INSERT OR IGNORE INTO content_digests VALUES(?,?,?,?,?,?)",
                        (cid, "raw-content-v1", algo, h.digest(), now(), "v1"),
                    )
                s.execute(
                    "INSERT INTO blob_content_map VALUES(?,?,?)", (obj, cid, run["id"])
                )
            self.source(obj, repo, run)

    def parsed(self, obj, typ):
        table = {"commit": "commits", "tree": "root_manifests", "tag": "tag_objects"}[
            typ
        ]
        col = "tree_id" if typ == "tree" else "object_id"
        return self.s.one(f"SELECT 1 FROM {table} WHERE {col}=?", (obj,)) is not None

    def parse(self, obj, data, fmt):
        s = self.s
        if obj["type"] == "commit":
            headers, message = data.split(b"\n\n", 1)
            entries = [
                line.split(b" ", 1)
                for line in headers.split(b"\n")
                if not line.startswith(b" ")
            ]
            tree = next(v for k, v in entries if k == b"tree")
            tid = s.object_id(fmt, bytes.fromhex(tree.decode()))
            if tid is None:
                raise CatalogError("INCOMPLETE_CLOSURE", "Missing commit root tree")
            metadata = {
                k.decode("ascii", "backslashreplace"): v.decode(
                    "utf8", "backslashreplace"
                )
                for k, v in entries
                if k not in (b"tree", b"parent")
            }
            s.execute(
                "INSERT OR IGNORE INTO commits VALUES(?,?,?,?,?)",
                (obj["id"], tid, headers, message, json.dumps(metadata)),
            )
            for ordinal, parent in enumerate(v for k, v in entries if k == b"parent"):
                pid = s.object_id(fmt, bytes.fromhex(parent.decode()))
                if pid is None:
                    raise CatalogError("INCOMPLETE_CLOSURE", "Missing parent")
                s.execute(
                    "INSERT OR IGNORE INTO commit_parents VALUES(?,?,?)",
                    (obj["id"], ordinal, pid),
                )
            s.execute(
                "INSERT OR IGNORE INTO search_documents(kind,source_key,body) VALUES('commits',?,?)",
                (str(obj["id"]), message.decode("utf8", "replace")),
            )
        elif obj["type"] == "tree":
            s.execute("INSERT OR IGNORE INTO root_manifests VALUES(?,0)", (obj["id"],))
            offset = 0
            n = 20 if fmt == "sha1" else 32
            while offset < len(data):
                space = data.index(b" ", offset)
                end = data.index(b"\0", space)
                mode = int(data[offset:space], 8)
                name = data[space + 1 : end]
                child = data[end + 1 : end + 1 + n]
                if not name or b"/" in name or len(child) != n:
                    raise CatalogError("INTEGRITY_ERROR", "Malformed tree entry")
                child_id = None if mode == 0o160000 else s.object_id(fmt, child)
                if child_id is None and mode != 0o160000:
                    raise CatalogError("INCOMPLETE_CLOSURE", "Missing tree child")
                s.execute(
                    "INSERT OR IGNORE INTO tree_entries VALUES(?,?,?,?,?,?)",
                    (obj["id"], name, mode, fmt, child, child_id),
                )
                offset = end + 1 + n
        elif obj["type"] == "tag":
            target = bytes.fromhex(data.split(b"\n", 1)[0].split(b" ", 1)[1].decode())
            tid = s.object_id(fmt, target)
            if tid is None:
                raise CatalogError("INCOMPLETE_CLOSURE", "Missing tag target")
            s.execute(
                "INSERT OR IGNORE INTO tag_objects VALUES(?,?,?)",
                (obj["id"], tid, data),
            )

    def manifests(self, fmt, refs, job):
        for ref in refs:
            if not ref["name"].startswith("refs/heads/") and ref.get("role") != "head":
                continue
            obj = self.s.object_id(fmt, bytes.fromhex(ref["oid"]))
            row = self.s.one("SELECT tree_id FROM commits WHERE object_id=?", (obj,))
            if row is None:
                raise CatalogError("INTEGRITY_ERROR", "Head must target a commit")
            self.build_manifest(row[0])

    def build_manifest(self, tree):
        s = self.s
        if s.one("SELECT complete FROM root_manifests WHERE tree_id=?", (tree,))[0]:
            return
        stack = [(tree, b"")]
        batch = []
        batch_bytes = 0

        def flush():
            with s.transaction():
                s.connection.executemany(
                    "INSERT OR IGNORE INTO root_manifest_entries VALUES(?,?,?,?,?,?)",
                    batch,
                )
            batch.clear()

        while stack:
            self.token.check()
            current, prefix = stack.pop()
            for r in s.all(
                "SELECT * FROM tree_entries WHERE tree_id=? ORDER BY raw_name",
                (current,),
            ):
                path = prefix + r["raw_name"]
                if r["mode"] == 0o40000:
                    stack.append((r["child_id"], path + b"/"))
                else:
                    row_bytes = len(path) + len(r["child_oid"]) + 64
                    if batch and (
                        len(batch) >= s.config["collection"]["write_batch_rows"]
                        or batch_bytes + row_bytes
                        > s.config["collection"]["write_batch_bytes"]
                    ):
                        flush()
                        batch_bytes = 0
                    batch.append(
                        (
                            tree,
                            path,
                            r["mode"],
                            r["child_id"],
                            r["child_format"],
                            r["child_oid"],
                        )
                    )
                    batch_bytes += row_bytes
        if batch:
            flush()
        with s.transaction():
            s.execute("UPDATE root_manifests SET complete=1 WHERE tree_id=?", (tree,))

    def preserve_text(self, path, fmt, obj, run, runner):
        s = self.s
        r = s.one(
            "SELECT g.oid,c.*,d.digest FROM git_objects g JOIN blob_content_map b ON b.object_id=g.id JOIN contents c ON c.id=b.content_id JOIN content_digests d ON d.content_id=c.id AND d.algorithm='sha256' WHERE g.id=?",
            (obj,),
        )
        if r["text_state"] != "eligible" or r["raw_text"] is not None:
            return
        raw = runner.run(["cat-file", "blob", r["oid"].hex()], cwd=path)
        if len(raw) != r["byte_length"] or hashlib.sha256(raw).digest() != r["digest"]:
            raise CatalogError("INTEGRITY_ERROR", "Durable text round-trip mismatch")
        text = raw.decode("utf8", "strict")
        with s.transaction():
            s.execute("UPDATE contents SET raw_text=? WHERE id=?", (text, r["id"]))
            s.execute(
                "INSERT OR IGNORE INTO content_locations VALUES(?,'durable-content',?,NULL,'available')",
                (r["id"], f"sqlite:contents/{r['id']}"),
            )
            s.execute(
                "INSERT OR IGNORE INTO search_documents(kind,source_key,body) VALUES('code',?,?)",
                (str(r["id"]), text),
            )
