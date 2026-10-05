from __future__ import annotations

import copy
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from repo_catalog import __version__
from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.config import DEFAULTS, serialize, validate
from repo_catalog.domain.models import CatalogError, Result


class MaintenanceService:
    def __init__(self, state_dir):
        self.path = Path(state_dir)

    def init(self, profile, cache_max_bytes, min_free_bytes):
        if self.path.exists() and any(self.path.iterdir()):
            raise CatalogError(
                "INVALID_ARGUMENT", "State directory must be new or empty"
            )
        cfg = copy.deepcopy(DEFAULTS)
        cfg["cache"].update(max_bytes=cache_max_bytes, min_free_bytes=min_free_bytes)
        cfg["preservation"]["profile"] = profile
        validate(cfg)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=".repo-catalog-init-", dir=self.path.parent)
        )
        try:
            os.chmod(stage, 0o700)
            (stage / "catalog.toml").write_text(serialize(cfg))
            for name in ("cache", "work", "quarantine", "locks", "logs"):
                (stage / name).mkdir(mode=0o700)
            with Store(stage, initialize=True) as store:
                revision = store.revision()
            os.rename(stage, self.path)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        return Result(
            {"state_dir": str(self.path), "configuration": cfg}, catalog=revision
        )

    def doctor(self):
        capabilities = {
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version,
            "git": None,
            "strict": False,
            "fts5_trigram": False,
        }
        try:
            capabilities["git"] = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        c = sqlite3.connect(":memory:")
        for key, sql in [
            ("strict", "CREATE TABLE p(x INTEGER) STRICT"),
            (
                "fts5_trigram",
                "CREATE VIRTUAL TABLE f USING fts5(body, tokenize='trigram case_sensitive 1',content='',detail=full)",
            ),
        ]:
            try:
                c.execute(sql)
                capabilities[key] = True
            except sqlite3.Error:
                pass
        c.close()
        initialized = (self.path / "catalog.toml").is_file()
        existing = self.path
        while not existing.exists():
            existing = existing.parent
        data = {
            "version": __version__,
            "initialized": initialized,
            "state_dir": str(self.path),
            "capabilities": capabilities,
            "free_bytes": shutil.disk_usage(existing).free,
        }
        result = Result(data)
        if (
            not capabilities["strict"]
            or not capabilities["git"]
            or sys.version_info < (3, 12)
        ):
            raise CatalogError(
                "RUNTIME_UNSUPPORTED",
                "Required Python/Git/SQLite capability missing",
                data,
            )
        git_version = tuple(
            int(x) for x in capabilities["git"].split()[2].split(".")[:2]
        )
        if git_version < (2, 43):
            raise CatalogError("RUNTIME_UNSUPPORTED", "Git 2.43+ required", data)
        if initialized:
            with Store(self.path, readonly=True) as s:
                data.update(
                    schema_version=s.one("SELECT schema_version FROM catalog_meta")[0],
                    journal_mode=s.one("PRAGMA journal_mode")[0],
                    configuration=s.config,
                )
                result.catalog = s.revision()
        return result

    def source_add(
        self,
        kind,
        *,
        owner=None,
        name=None,
        url=None,
        clone_url_overrides=None,
        include_repositories=None,
    ):
        if kind == "github":
            if not owner:
                raise CatalogError("INVALID_ARGUMENT", "GitHub source requires --owner")
            import re
            from urllib.parse import urlsplit

            if not re.fullmatch(r"[A-Za-z0-9-]+", owner):
                raise CatalogError("INVALID_ARGUMENT", "Invalid GitHub owner")
            for repository in include_repositories or ():
                if not re.fullmatch(
                    r"[A-Za-z0-9_.-]+", repository.removeprefix(owner + "/")
                ):
                    raise CatalogError(
                        "INVALID_ARGUMENT",
                        "Included repository must be a name within declared owner",
                    )
            for override in (clone_url_overrides or {}).values():
                parsed = urlsplit(override)
                if (
                    parsed.password
                    or parsed.scheme in ("http", "https")
                    and parsed.username
                ):
                    raise CatalogError(
                        "INVALID_ARGUMENT",
                        "Use a credential helper for clone overrides",
                    )
            settings = {
                "owner": owner,
                "clone_url_overrides": clone_url_overrides or {},
                "include_repositories": include_repositories or [],
            }
            name = owner
        else:
            if include_repositories or clone_url_overrides:
                raise CatalogError(
                    "INVALID_ARGUMENT", "GitHub options require a github source"
                )
            if not name or not url:
                raise CatalogError(
                    "INVALID_ARGUMENT", "local-git source requires --name and --url"
                )
            from urllib.parse import urlsplit

            parsed = urlsplit(url)
            if (
                parsed.password
                or parsed.scheme in ("http", "https")
                and parsed.username
            ):
                raise CatalogError(
                    "INVALID_ARGUMENT",
                    "Use a credential helper, not credentials embedded in a URL",
                )
            settings = {"url": url}
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            ident = str(uuid.uuid4())
            with s.transaction():
                s.execute(
                    "INSERT INTO sources VALUES(?,?,?,?)",
                    (ident, kind, name, json.dumps(settings)),
                )
                s.publish()
            return Result(
                {"source_id": ident, "kind": kind, "name": name}, catalog=s.revision()
            )

    def gc(self, apply=False):
        from repo_catalog.adapters.filesystem.cache import CacheManager

        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            return Result(
                {"dry_run": not apply, "entries": CacheManager(s).collect(apply=apply)},
                catalog=s.revision(),
            )

    def rebuild(self, kind, token=None):
        from repo_catalog.adapters.sqlite.index import rebuild
        from repo_catalog.application.job_service import JobService

        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            job = JobService(s).create("index", {"kind": kind})
            try:
                data = rebuild(s, kind, token)
                JobService(s).update(job, "complete")
                return Result(
                    {"job_id": job, "generations": data}, catalog=s.revision()
                )
            except CatalogError as e:
                JobService(s).update(
                    job, "interrupted" if e.code == "CANCELLED" else "failed", e.code
                )
                raise

    def database(self, action, args):
        if action == "restore":
            return self.restore(args.input)
        with (
            FileLock(self.path / "locks/writer.lock"),
            Store(self.path, migrate=action == "migrate") as s,
        ):
            if action == "migrate":
                s.migrate()
                return Result(
                    {
                        "schema_version": s.one(
                            "SELECT schema_version FROM catalog_meta"
                        )[0]
                    },
                    catalog=s.revision(),
                )
            if action == "check":
                return self.check(s, args.full)
            if action == "backup":
                output = Path(args.output).expanduser().resolve()
                if output.exists() or output == s.db_path:
                    raise CatalogError(
                        "INVALID_ARGUMENT", "Backup output must be a new file"
                    )
                output.parent.mkdir(parents=True, exist_ok=True)
                stage = output.with_name(output.name + "." + uuid.uuid4().hex + ".tmp")
                try:
                    target = sqlite3.connect(stage)
                    try:
                        s.connection.backup(target)
                    finally:
                        target.close()
                    conn = sqlite3.connect(stage.as_uri() + "?mode=ro", uri=True)
                    try:
                        if (
                            conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                            or conn.execute("PRAGMA foreign_key_check").fetchall()
                        ):
                            raise CatalogError(
                                "BACKUP_INTEGRITY", "Backup verification failed"
                            )
                    finally:
                        conn.close()
                    import hashlib

                    digest = hashlib.file_digest(stage.open("rb"), "sha256").hexdigest()
                    os.rename(stage, output)
                    manifest = {
                        "schema_version": 1,
                        "catalog": s.revision(),
                        "sha256": digest,
                        "configuration": s.config,
                    }
                    output.with_name(output.name + ".manifest.json").write_text(
                        json.dumps(manifest, indent=2)
                    )
                    return Result(
                        {"output": str(output), "manifest": manifest},
                        catalog=s.revision(),
                    )
                finally:
                    if stage.exists():
                        stage.unlink()
        raise CatalogError("INVALID_ARGUMENT", "Unknown database operation")

    def check(self, s, full=False):
        checks = {}
        checks["sqlite"] = [
            r[0]
            for r in s.all("PRAGMA integrity_check" if full else "PRAGMA quick_check")
        ]
        checks["foreign_keys"] = [tuple(r) for r in s.all("PRAGMA foreign_key_check")]
        checks["dangling_publications"] = [
            dict(r)
            for r in s.all(
                "SELECT r.id FROM repositories r LEFT JOIN snapshots sn ON sn.id=r.current_snapshot WHERE r.current_snapshot IS NOT NULL AND (sn.id IS NULL OR sn.published!=1)"
            )
        ]
        checks["unfinished_published_runs"] = [
            dict(r)
            for r in s.all(
                "SELECT * FROM preservation_obligations WHERE published=1 AND (roots_fixed!=1 OR structure_done!=1 OR digest_done!=1 OR text_done!=1)"
            )
        ]
        from repo_catalog.adapters.sqlite.index import fts_available

        checks["index"] = {"status": "unavailable", "generations": []}
        if fts_available(s):
            checks["index"]["status"] = "passed"
            for row in s.all("SELECT * FROM index_generations WHERE state='ready'"):
                try:
                    with s.transaction():
                        s.execute(
                            f"INSERT INTO {row['table_name']}({row['table_name']}) VALUES('integrity-check')"
                        )
                    checks["index"]["generations"].append(
                        {"id": row["id"], "status": "passed"}
                    )
                except sqlite3.Error:
                    with s.transaction():
                        s.execute(
                            "UPDATE index_generations SET state='unavailable' WHERE id=?",
                            (row["id"],),
                        )
                    checks["index"]["status"] = "failed"
                    checks["index"]["generations"].append(
                        {"id": row["id"], "status": "failed"}
                    )
        if (
            checks["sqlite"] != ["ok"]
            or checks["foreign_keys"]
            or checks["dangling_publications"]
            or checks["unfinished_published_runs"]
            or checks["index"]["status"] == "failed"
        ):
            raise CatalogError(
                "INTEGRITY_ERROR", "Catalog integrity check failed", checks
            )
        return Result({"checks": checks}, catalog=s.revision())

    def restore(self, input_file):
        source = Path(input_file).expanduser().resolve()
        manifest_path = source.with_name(source.name + ".manifest.json")
        if not source.is_file() or not manifest_path.is_file():
            raise CatalogError("NOT_FOUND", "Backup and manifest are required")
        if self.path.exists() and any(self.path.iterdir()):
            raise CatalogError(
                "INVALID_ARGUMENT", "Restore destination must be new or empty"
            )
        import hashlib

        manifest = json.loads(manifest_path.read_text())
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != manifest["sha256"]:
            raise CatalogError("BACKUP_INTEGRITY", "Backup checksum mismatch")
        cfg = validate(manifest["configuration"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=".repo-catalog-restore-", dir=self.path.parent)
        )
        try:
            (stage / "catalog.toml").write_text(serialize(cfg))
            for directory in ("cache", "work", "quarantine", "locks", "logs"):
                (stage / directory).mkdir(mode=0o700)
            shutil.copyfile(source, stage / cfg["database"]["filename"])
            with Store(stage) as s:
                self.check(s)
                with s.transaction():
                    s.execute(
                        "UPDATE catalog_meta SET db_instance_id=? WHERE id=1",
                        (str(uuid.uuid4()),),
                    )
                    s.execute("UPDATE cache_entries SET state='evicted',bytes=0")
                    s.execute("DELETE FROM cache_leases")
                    s.execute("DELETE FROM space_reservations")
                    s.execute(
                        "UPDATE content_locations SET state='unavailable' WHERE kind='cache'"
                    )
                    s.execute(
                        "UPDATE jobs SET state='interrupted',reason='restored_state_requires_admission' WHERE state='running'"
                    )
                revision = s.revision()
            (stage / "restore-origin.json").write_text(
                json.dumps(
                    {
                        "backup": str(source),
                        "source_catalog": manifest["catalog"],
                        "sha256": digest,
                    }
                )
            )
            os.rename(stage, self.path)
            return Result(
                {"state_dir": str(self.path), "source_catalog": manifest["catalog"]},
                catalog=revision,
            )
        finally:
            if stage.exists():
                shutil.rmtree(stage)

    def hydrate(self, content_id, repo_selector, token):
        from repo_catalog.adapters.git.importer import GitImporter
        from repo_catalog.adapters.git.runner import GitRunner
        from repo_catalog.application.collection_service import select_repositories
        from repo_catalog.application.job_service import JobService

        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            content = s.one("SELECT * FROM contents WHERE id=?", (content_id,))
            if not content:
                raise CatalogError("NOT_FOUND", "Content not found")
            if content["text_state"] != "eligible":
                raise CatalogError(
                    "PROFILE_UNSUPPORTED", "Profile does not allow this raw content"
                )
            if content["raw_text"] is not None:
                return Result(
                    {"content_id": content_id, "state": "already_saved"},
                    catalog=s.revision(),
                )
            repos = select_repositories(s, (repo_selector,) if repo_selector else ())
            job = JobService(s).create(
                "hydrate", {"content_id": content_id, "repo": repo_selector}
            )
            try:
                for repo in repos:
                    candidates = s.all(
                        "SELECT g.*,b.run_id FROM blob_content_map b JOIN git_objects g ON g.id=b.object_id JOIN repository_object_sources p ON p.object_id=g.id JOIN collection_runs r ON r.id=p.run_id WHERE b.content_id=? AND p.repo_id=? AND r.state='published'",
                        (content_id, repo["id"]),
                    )
                    if not candidates:
                        continue
                    cache = s.one(
                        "SELECT * FROM cache_entries WHERE repo_id=? AND state='available' ORDER BY generation DESC LIMIT 1",
                        (repo["id"],),
                    )
                    if not cache:
                        # Explicit re-fetch creates a fresh current observation, without claiming lost OIDs are available.
                        GitImporter(s, token).sync(repo, job)
                        cache = s.one(
                            "SELECT * FROM cache_entries WHERE repo_id=? AND state='available' ORDER BY generation DESC LIMIT 1",
                            (repo["id"],),
                        )
                    with FileLock(
                        s.path / f"locks/cache-{cache['id']}.lock", inheritable=True
                    ) as lock:
                        runner = GitRunner(token, lock)
                        for obj in candidates:
                            try:
                                GitImporter(s, token).preserve_text(
                                    s.path / cache["path"],
                                    obj["object_format"],
                                    obj["id"],
                                    {"id": obj["run_id"]},
                                    runner,
                                )
                            except CatalogError as e:
                                if e.code == "GIT_ERROR":
                                    continue
                                raise
                            with s.transaction():
                                s.publish()
                            JobService(s).update(job, "complete")
                            return Result(
                                {
                                    "job_id": job,
                                    "content_id": content_id,
                                    "state": "saved",
                                },
                                catalog=s.revision(),
                            )
                raise CatalogError(
                    "RAW_CONTENT_UNAVAILABLE",
                    "No configured source can provide the recorded content",
                )
            except CatalogError as e:
                JobService(s).update(
                    job, "interrupted" if e.code == "CANCELLED" else "failed", e.code
                )
                e.details["job_id"] = job
                raise
