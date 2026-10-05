from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.git.importer import GitImporter
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import (
    CancellationToken,
    CatalogError,
    CoverageReport,
    Result,
    now,
)


def select_repositories(s, selectors=(), source=None):
    rows = s.all(
        "SELECT * FROM repositories"
        + (" WHERE source_id=?" if source else "")
        + " ORDER BY id",
        (source,) if source else (),
    )
    if not selectors or selectors == ("all",):
        return rows
    if "all" in selectors:
        raise CatalogError(
            "INVALID_ARGUMENT", "all cannot be combined with individual repos"
        )
    selected = []
    for selector in selectors:
        matches = [
            r
            for r in rows
            if selector in (r["id"], r["name"], f"{r['provider_host']}/{r['name']}")
        ]
        if not matches:
            raise CatalogError(
                "NOT_FOUND", "Repository selector not found", {"selector": selector}
            )
        if len(matches) != 1:
            raise CatalogError("INVALID_ARGUMENT", "Ambiguous repository selector")
        if matches[0] not in selected:
            selected.append(matches[0])
    return sorted(selected, key=lambda r: r["id"])


class CollectionService:
    def __init__(self, state_dir, token=None):
        self.path = Path(state_dir)
        self.token = token or CancellationToken()

    def discover(self, source=None):
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            job = JobService(s).create("discover", {"source": source})
            return self._discover(s, job, source)

    def _discover(self, s, job, source):
        sources = s.all(
            "SELECT * FROM sources" + (" WHERE id=?" if source else ""),
            (source,) if source else (),
        )
        if source and not sources:
            raise CatalogError("NOT_FOUND", "Source not found")
        items = []
        coverage = CoverageReport()
        for src in sources:
            self.token.check()
            settings = json.loads(src["settings"])
            run = str(uuid.uuid4())
            with s.transaction():
                s.execute(
                    "INSERT INTO inventory_runs VALUES(?,?,?,?,?,NULL)",
                    (run, src["id"], "running", json.dumps(settings), now()),
                )
            try:
                uncertainty = None
                if src["kind"] == "local-git":
                    repos = [
                        {
                            "host": "local",
                            "provider_id": src["id"],
                            "name": src["name"],
                            "url": settings["url"],
                            "metadata": {},
                        }
                    ]
                else:
                    from repo_catalog.adapters.github.collector import GitHubCollector

                    collector = GitHubCollector(s, self.token)
                    repos = collector.inventory(src, job)
                    uncertainty = collector.inventory_uncertainty
                if uncertainty:
                    coverage.add("inventory", uncertainty, source_id=src["id"])
                with s.transaction():
                    for repo in repos:
                        existing = s.one(
                            "SELECT id FROM repositories WHERE provider_host=? AND provider_repo_id=?",
                            (repo["host"], repo["provider_id"]),
                        )
                        ident = existing[0] if existing else str(uuid.uuid4())
                        s.execute(
                            "INSERT INTO repositories(id,source_id,provider_host,provider_repo_id,name,url,metadata) VALUES(?,?,?,?,?,?,?) ON CONFLICT(provider_host,provider_repo_id) DO UPDATE SET name=excluded.name,url=excluded.url,metadata=excluded.metadata",
                            (
                                ident,
                                src["id"],
                                repo["host"],
                                repo["provider_id"],
                                repo["name"],
                                repo["url"],
                                json.dumps(repo["metadata"]),
                            ),
                        )
                        s.execute(
                            "INSERT OR IGNORE INTO repository_names VALUES(?,?,?)",
                            (ident, repo["name"], now()),
                        )
                        items.append({"repo_id": ident, "name": repo["name"]})
                    s.execute(
                        "UPDATE inventory_runs SET state=?,reason=? WHERE id=?",
                        ("partial" if uncertainty else "complete", uncertainty, run),
                    )
                    s.publish()
            except CatalogError as e:
                coverage.add("inventory", e.code, source_id=src["id"])
                with s.transaction():
                    s.execute(
                        "UPDATE inventory_runs SET state='partial',reason=? WHERE id=?",
                        (e.code, run),
                    )
        JobService(s).update(
            job, "complete" if coverage.complete_for_requested_scope else "waiting"
        )
        return Result(
            {"job_id": job, "repositories": items},
            coverage,
            "complete" if coverage.complete_for_requested_scope else "partial",
            s.revision(),
        )

    def sync(self, request):
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            data = {
                "kind": request.kind,
                "repositories": list(request.repositories),
                "source": request.source,
            }
            job = JobService(s).create("sync", data)
            return self._sync(s, job, data)

    def resume(self, job):
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            kind, request = JobService(s).resume(job)
            if kind == "discover":
                return self._discover(s, job, request.get("source"))
            if kind == "sync":
                return self._sync(s, job, request)
            raise CatalogError("INVALID_ARGUMENT", "Unsupported resumable job kind")

    def _sync(self, s, job, request):
        items = []
        coverage = CoverageReport()
        not_before = None
        s.expected_attempt = s.one("SELECT attempt FROM jobs WHERE id=?", (job,))[0]
        try:
            from repo_catalog.adapters.filesystem.cache import CacheManager
            from repo_catalog.adapters.filesystem.capacity import Capacity

            CacheManager(s).recover()
            if (
                Capacity(s).used()
                > s.config["cache"]["max_bytes"] * s.config["cache"]["high_water_ratio"]
            ):
                CacheManager(s).collect(apply=True, pressure=True)
            repos = select_repositories(
                s, tuple(request["repositories"]), request.get("source")
            )
            for repo in repos:
                for kind in (
                    ("git", "pr") if request["kind"] == "all" else (request["kind"],)
                ):
                    self.token.check()
                    try:
                        if kind == "git":
                            done = s.one(
                                "SELECT id FROM collection_runs WHERE job_id=? AND repo_id=? AND kind='git' AND state='published'",
                                (job, repo["id"]),
                            )
                            item = (
                                {
                                    "repo_id": repo["id"],
                                    "snapshot_id": done[0],
                                    "state": "complete",
                                }
                                if done
                                else GitImporter(s, self.token).sync(repo, job)
                            )
                        elif repo["provider_host"] == "local":
                            item = {"repo_id": repo["id"], "state": "not_applicable"}
                        else:
                            from repo_catalog.adapters.github.collector import (
                                GitHubCollector,
                            )

                            item = GitHubCollector(s, self.token).sync(repo, job)
                        items.append({"kind": kind, **item})
                    except CatalogError as e:
                        if e.code == "CANCELLED":
                            raise
                        coverage.add(kind, e.code, repo_id=repo["id"])
                        items.append(
                            {
                                "kind": kind,
                                "repo_id": repo["id"],
                                "state": "partial",
                                "error": e.code,
                            }
                        )
                        not_before = e.details.get("not_before", not_before)
            JobService(s).update(
                job,
                "complete" if coverage.complete_for_requested_scope else "waiting",
                not_before=not_before,
            )
            return Result(
                {"job_id": job, "results": items},
                coverage,
                "complete" if coverage.complete_for_requested_scope else "partial",
                s.revision(),
            )
        except CatalogError as e:
            JobService(s).update(
                job, "interrupted" if e.code == "CANCELLED" else "failed", e.code
            )
            e.details["job_id"] = job
            raise
        except (OSError, sqlite3.Error) as cause:
            code = "DATABASE_ERROR" if isinstance(cause, sqlite3.Error) else "IO_ERROR"
            error = CatalogError(
                code,
                f"Collection failed: {type(cause).__name__}",
                {"job_id": job},
                True,
            )
            try:
                JobService(s).update(job, "failed", code)
            except sqlite3.Error:
                # A full/unwritable DB can prevent this final metadata update;
                # the durable job ID still permits recovery after repair.
                pass
            raise error from cause
