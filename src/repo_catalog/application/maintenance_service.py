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
from repo_catalog.application import repository_identity as identity
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
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA recursive_triggers=ON")
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
        if initialized:
            with Store(self.path, readonly=True) as s:
                data.update(
                    schema_version=s.one(
                        "SELECT schema_version FROM database_identity"
                    )[0],
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
        repo=None,
        instance=None,
        provider_repository_id=None,
        token_env_var=None,
    ):
        if kind == "git-url":
            kind = "local-git"
        if kind not in ("github", "local-git"):
            raise CatalogError("INVALID_ARGUMENT", "Unknown source kind")
        if provider_repository_id is not None and not instance:
            raise CatalogError(
                "INVALID_ARGUMENT", "Provider repository ID requires an instance"
            )
        if kind == "github":
            if repo or provider_repository_id:
                raise CatalogError(
                    "INVALID_ARGUMENT",
                    "Use repos bind to attach a GitHub provider ID before discovery",
                )
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
            if token_env_var:
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token_env_var):
                    raise CatalogError(
                        "INVALID_ARGUMENT", "Token environment variable name is invalid"
                    )
                settings["api_settings"] = {"token_env_var": token_env_var}
            name = owner
        else:
            if token_env_var:
                raise CatalogError(
                    "INVALID_ARGUMENT", "API credentials require an API source"
                )
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
            settings = {"url": identity.git_url(url)}
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            ident = str(uuid.uuid4())
            with s.transaction():
                service_instance_uuidv4 = (
                    identity.instance(s, instance)["service_instance_uuidv4"]
                    if instance
                    else None
                )
                if kind == "github":
                    service_instance_uuidv4 = (
                        service_instance_uuidv4 or identity.default_github_instance(s)
                    )
                    if (
                        identity.instance(s, service_instance_uuidv4)["service_kind"]
                        != "github"
                    ):
                        raise CatalogError(
                            "INVALID_ARGUMENT",
                            "GitHub source requires a GitHub instance",
                        )
                if repo:
                    from repo_catalog.application.collection_service import (
                        single_repository,
                    )

                    settings["repository_uuidv4"] = single_repository(s, repo)[
                        "repository_uuidv4"
                    ]
                if provider_repository_id is not None:
                    if not str(provider_repository_id).strip():
                        raise CatalogError(
                            "INVALID_ARGUMENT",
                            "Provider repository ID must be nonempty",
                        )
                    settings["provider_repository_id"] = str(provider_repository_id)
                s.execute(
                    "INSERT INTO sources(source_id,discovery_kind,name,settings,service_instance_uuidv4,source_registration_uuidv4) VALUES(?,?,?,?,?,?)",
                    (
                        ident,
                        "github_inventory" if kind == "github" else "manual_git",
                        name,
                        json.dumps(settings),
                        service_instance_uuidv4,
                        str(uuid.uuid4()),
                    ),
                )
                s.publish()
            return Result(
                {
                    "source_id": ident,
                    "source_registration_uuidv4": s.one(
                        "SELECT source_registration_uuidv4 FROM sources WHERE source_id=?",
                        (ident,),
                    )[0],
                    "kind": kind,
                    "name": name,
                },
                catalog=s.revision(),
            )

    def instance_add(self, kind, name, web_base_url=None, api_base_url=None):
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            with s.transaction():
                ident = identity.add_instance(s, kind, name, web_base_url, api_base_url)
                s.publish()
            return Result({"service_instance_uuidv4": ident}, catalog=s.revision())

    def repository_bind(self, repo, instance, provider_repository_id=None):
        from repo_catalog.application.collection_service import single_repository

        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            with s.transaction():
                repository_uuidv4 = single_repository(s, repo)["repository_uuidv4"]
                service_instance_uuidv4 = identity.instance(s, instance)[
                    "service_instance_uuidv4"
                ]
                identity.bind(
                    s,
                    repository_uuidv4,
                    service_instance_uuidv4,
                    provider_repository_id,
                )
                s.publish()
            return Result(
                {
                    "repository_uuidv4": repository_uuidv4,
                    "service_instance_uuidv4": service_instance_uuidv4,
                    "provider_repository_id": provider_repository_id,
                },
                catalog=s.revision(),
            )

    def endpoint_add(self, repo, url, label=None, preferred=False):
        from repo_catalog.application.collection_service import single_repository

        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            with s.transaction():
                repository_uuidv4 = single_repository(s, repo)["repository_uuidv4"]
                ident = identity.add_endpoint(
                    s, repository_uuidv4, url, label, preferred
                )
                s.publish()
            return Result(
                {
                    "repository_uuidv4": repository_uuidv4,
                    "repository_endpoint_id": ident,
                },
                catalog=s.revision(),
            )

    def endpoint_prefer(self, repo, repository_endpoint_id):
        from repo_catalog.application.collection_service import single_repository

        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            with s.transaction():
                repository_uuidv4 = single_repository(s, repo)["repository_uuidv4"]
                identity.prefer_endpoint(s, repository_uuidv4, repository_endpoint_id)
                s.publish()
            return Result(
                {
                    "repository_uuidv4": repository_uuidv4,
                    "repository_endpoint_id": repository_endpoint_id,
                },
                catalog=s.revision(),
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
        if action == "finalize":
            from repo_catalog.application.finalization import finalize_catalog

            with (
                FileLock(self.path / "locks/writer.lock"),
                Store(self.path, allow_building=True) as s,
            ):
                report = finalize_catalog(s)
                return (
                    report
                    if isinstance(report, Result)
                    else Result(report, catalog=s.revision())
                )
        with (
            FileLock(self.path / "locks/writer.lock"),
            Store(self.path) as s,
        ):
            if action == "check":
                return self.check(s, args.full)
            if action == "backup":
                output = Path(args.output).expanduser().resolve()
                if (
                    output.exists()
                    or output.with_name(output.name + ".manifest.json").exists()
                    or output == s.db_path
                ):
                    raise CatalogError(
                        "INVALID_ARGUMENT", "Backup output must be a new file"
                    )
                output.parent.mkdir(parents=True, exist_ok=True)
                stage = output.with_name(output.name + "." + uuid.uuid4().hex + ".tmp")
                try:
                    target = sqlite3.connect(stage)
                    target.execute("PRAGMA foreign_keys=ON")
                    target.execute("PRAGMA recursive_triggers=ON")
                    try:
                        s.connection.backup(target)
                    finally:
                        target.close()
                    conn = sqlite3.connect(stage.as_uri() + "?mode=ro", uri=True)
                    conn.execute("PRAGMA foreign_keys=ON")
                    conn.execute("PRAGMA recursive_triggers=ON")
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
                        "schema_version": s.one(
                            "SELECT schema_version FROM database_identity"
                        )[0],
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
        from repo_catalog.application.finalization import check_catalog

        checks = {
            "owner_evidence": check_catalog(s),
            "sqlite": [
                r[0]
                for r in s.all(
                    "PRAGMA integrity_check" if full else "PRAGMA quick_check"
                )
            ],
            "foreign_keys": [tuple(r) for r in s.all("PRAGMA foreign_key_check")],
            "dangling_publications": [
                dict(r)
                for r in s.all(
                    "SELECT r.repository_uuidv4 FROM repositories r LEFT JOIN snapshots sn ON sn.snapshot_id=r.current_snapshot_id WHERE r.current_snapshot_id IS NOT NULL AND (sn.snapshot_id IS NULL OR sn.repository_uuidv4!=r.repository_uuidv4 OR sn.published!=1)"
                )
            ],
            "unfinished_published_runs": [
                dict(r)
                for r in s.all(
                    "SELECT * FROM preservation_obligations WHERE published=1 AND "
                    "(roots_fixed!=1 OR structure_done!=1 OR digest_done!=1 OR text_done!=1)"
                )
            ],
            "repository_endpoints": [
                dict(r)
                for r in s.all(
                    "SELECT r.repository_uuidv4 FROM repositories r LEFT JOIN repository_endpoints e ON e.repository_endpoint_id=r.preferred_repository_endpoint_id WHERE r.preferred_repository_endpoint_id IS NOT NULL AND (e.repository_endpoint_id IS NULL OR e.repository_uuidv4!=r.repository_uuidv4)"
                )
            ],
            "change_request_current": [
                dict(r)
                for r in s.all(
                    "SELECT p.change_request_id FROM change_requests p LEFT JOIN change_request_observations o ON o.change_request_observation_id=p.current_change_request_observation_id WHERE p.current_change_request_observation_id IS NOT NULL AND (o.change_request_observation_id IS NULL OR o.change_request_id!=p.change_request_id OR o.published!=1)"
                )
            ],
            "index": {"status": "passed", "generations": []},
        }
        for row in s.all("SELECT * FROM index_generations WHERE state='ready'"):
            try:
                with s.transaction():
                    s.execute(
                        f"INSERT INTO {row['table_name']}({row['table_name']}) VALUES('integrity-check')"
                    )
                checks["index"]["generations"].append(
                    {
                        "index_generation_id": row["index_generation_id"],
                        "status": "passed",
                    }
                )
            except sqlite3.Error:
                checks["index"]["status"] = "failed"
                checks["index"]["generations"].append(
                    {
                        "index_generation_id": row["index_generation_id"],
                        "status": "failed",
                    }
                )
        if (
            checks["sqlite"] != ["ok"]
            or any(
                checks[key]
                for key in (
                    "owner_evidence",
                    "foreign_keys",
                    "dangling_publications",
                    "unfinished_published_runs",
                    "repository_endpoints",
                    "change_request_current",
                )
            )
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
                        "UPDATE database_identity SET db_instance_id=? WHERE singleton=1",
                        (str(uuid.uuid4()),),
                    )
                    s.execute(
                        "UPDATE active_cache_entries SET state='evicted',bytes=0 WHERE cache_locator_id IN (SELECT cache_locator_id FROM cache_locators WHERE access='target_active')"
                    )
                    s.execute(
                        "UPDATE cache_locators SET state='missing' WHERE access='target_active'"
                    )
                    s.execute("DELETE FROM cache_leases")
                    s.execute("DELETE FROM space_reservations")
                    s.execute(
                        "UPDATE content_locations SET state='unavailable' WHERE kind='cache' AND cache_locator_id IN (SELECT cache_locator_id FROM cache_locators WHERE access='target_active')"
                    )
                    s.execute(
                        "UPDATE job_attempts SET state='interrupted',reason='restored_state_requires_admission' WHERE state='running'"
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
            if self.path.exists():
                self.path.rmdir()
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
            content = s.one("SELECT * FROM contents WHERE content_id=?", (content_id,))
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
                        "SELECT g.*,b.git_acquisition_id FROM blob_content_map b JOIN git_objects g ON g.git_object_id=b.git_object_id JOIN repository_object_sources p ON p.git_object_id=g.git_object_id JOIN acquisition_progress r ON r.git_acquisition_id=p.git_acquisition_id WHERE b.content_id=? AND p.repository_uuidv4=? AND r.state='published'",
                        (content_id, repo["repository_uuidv4"]),
                    )
                    if not candidates:
                        continue
                    cache = s.one(
                        "SELECT a.*,l.repository_uuidv4,l.path FROM active_cache_entries a JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE l.repository_uuidv4=? AND a.state='active' AND l.access='target_active' AND l.state='available' ORDER BY a.generation DESC LIMIT 1",
                        (repo["repository_uuidv4"],),
                    )
                    if not cache:
                        # Explicit re-fetch creates a fresh current observation, without claiming lost OIDs are available.
                        GitImporter(s, token).sync(repo, job)
                        cache = s.one(
                            "SELECT a.*,l.repository_uuidv4,l.path FROM active_cache_entries a JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE l.repository_uuidv4=? AND a.state='active' AND l.access='target_active' AND l.state='available' ORDER BY a.generation DESC LIMIT 1",
                            (repo["repository_uuidv4"],),
                        )
                    with FileLock(
                        s.path / f"locks/cache-{cache['active_cache_entry_id']}.lock",
                        inheritable=True,
                    ) as lock:
                        runner = GitRunner(token, lock)
                        for obj in candidates:
                            try:
                                GitImporter(s, token).preserve_text(
                                    s.path / cache["path"],
                                    obj["object_format"],
                                    obj["git_object_id"],
                                    {"git_acquisition_id": obj["git_acquisition_id"]},
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
