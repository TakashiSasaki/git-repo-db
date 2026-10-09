from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.git.importer import GitImporter
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application import repository_identity as identity
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import (
    CancellationToken,
    CatalogError,
    CoverageReport,
    Result,
)
from repo_catalog.domain.time import now_us


def select_repositories(s, selectors=(), source=None):
    rows = s.all(
        "SELECT * FROM repositories"
        + (
            " WHERE EXISTS(SELECT 1 FROM source_repositories m WHERE m.repository_uuidv4=repositories.repository_uuidv4 AND m.source_id=?)"
            if source
            else ""
        )
        + " ORDER BY repository_uuidv4",
        (source,) if source else (),
    )
    rows = [identity.repository_row(s, row) for row in rows]
    if not selectors or selectors == ("all",):
        return rows
    if "all" in selectors:
        raise CatalogError(
            "INVALID_ARGUMENT", "all cannot be combined with individual repos"
        )
    selected = []
    for selector in selectors:
        matches = [
            dict(r)
            for r in rows
            if selector
            in (r["repository_uuidv4"], r["name"], f"{r['provider_host']}/{r['name']}")
            or s.one(
                "SELECT 1 FROM repository_bindings b JOIN service_instances i ON i.service_instance_uuidv4=b.service_instance_uuidv4 WHERE b.repository_uuidv4=? AND ?=i.name||'/'||?",
                (r["repository_uuidv4"], selector, r["name"]),
            )
        ]
        if not matches:
            raise CatalogError(
                "NOT_FOUND", "Repository selector not found", {"selector": selector}
            )
        if len(matches) != 1:
            raise CatalogError("INVALID_ARGUMENT", "Ambiguous repository selector")
        if matches[0] not in selected:
            selected.append(matches[0])
    return sorted(selected, key=lambda r: r["repository_uuidv4"])


def single_repository(store, selector):
    rows = select_repositories(store, (selector,))
    if len(rows) != 1:
        raise CatalogError("INVALID_ARGUMENT", "Select one repository")
    return rows[0]


class CollectionService:
    def __init__(self, state_dir, token=None):
        self.path = Path(state_dir)
        self.token = token or CancellationToken()

    def discover(self, source=None):
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            if source is not None:
                selected_source = identity.source(s, source)
                identity.source_settings(selected_source)
                source = selected_source["source_id"]
            else:
                candidates = s.all("SELECT * FROM sources")
                unusable = []
                for candidate in candidates:
                    try:
                        identity.source_settings(candidate)
                    except CatalogError as cause:
                        unusable.append(
                            {
                                "source_registration_uuidv4": candidate[
                                    "source_registration_uuidv4"
                                ],
                                "reason": cause.code,
                            }
                        )
                if len(unusable) == len(candidates):
                    raise CatalogError(
                        "NO_USABLE_SOURCE",
                        "No configured acquisition source",
                        {"sources": unusable},
                    )
            job = JobService(s).create("discover", {"source": source})
            return self._discover(s, job, source)

    def _discover(self, s, job, source):
        sources = s.all(
            "SELECT * FROM sources" + (" WHERE source_id=?" if source else ""),
            (source,) if source else (),
        )
        if source and not sources:
            raise CatalogError("NOT_FOUND", "Source not found")
        items = []
        coverage = CoverageReport()
        skipped = []
        acquisition_failed = False
        for src in sources:
            self.token.check()
            try:
                settings = identity.source_settings(src)
            except CatalogError as cause:
                skipped.append(
                    {
                        "source_registration_uuidv4": src["source_registration_uuidv4"],
                        "reason": cause.code,
                    }
                )
                coverage.add("inventory", cause.code, source_id=src["source_id"])
                continue
            run = str(uuid.uuid4())
            observed_at_us = now_us()
            inventory_scope = dict(settings)
            collector = None
            try:
                uncertainty = None
                if src["discovery_kind"] == "manual_git":
                    repos = [
                        {
                            "host": "local",
                            "provider_repository_id": src["source_id"],
                            "name": src["name"],
                            "url": settings["url"],
                            "metadata": {},
                        }
                    ]
                else:
                    from repo_catalog.adapters.github.collector import GitHubCollector

                    collector = GitHubCollector(
                        s, self.token, config=identity.github_config(s, src)
                    )
                    inventory_scope["response_evidence"] = collector.inventory_evidence
                    repos = collector.inventory(src, job)
                    uncertainty = collector.inventory_uncertainty
                if uncertainty:
                    acquisition_failed = True
                    coverage.add("inventory", uncertainty, source_id=src["source_id"])
                with s.transaction():
                    for repo in repos:
                        provider_repository_id = (
                            repo["provider_repository_id"]
                            if src["discovery_kind"] == "github_inventory"
                            else settings.get("provider_repository_id")
                        )
                        target = settings.get("repository_uuidv4")
                        existing = (
                            s.one(
                                "SELECT repository_uuidv4 FROM repositories WHERE repository_uuidv4=?",
                                (target,),
                            )
                            if target
                            else None
                        )
                        if target and not existing:
                            raise CatalogError(
                                "NOT_FOUND",
                                "Explicit repository identity no longer exists",
                            )
                        if src["service_instance_uuidv4"] and provider_repository_id:
                            binding = s.one(
                                "SELECT repository_uuidv4 FROM repository_bindings WHERE service_instance_uuidv4=? AND provider_repository_id=?",
                                (
                                    src["service_instance_uuidv4"],
                                    provider_repository_id,
                                ),
                            )
                            if binding:
                                if existing and existing[0] != binding[0]:
                                    raise CatalogError(
                                        "IDENTITY_CONFLICT",
                                        "Source and provider identity refer to different repositories",
                                    )
                                existing = s.one(
                                    "SELECT repository_uuidv4 FROM repositories WHERE repository_uuidv4=?",
                                    (binding[0],),
                                )
                        if not existing and src["discovery_kind"] == "manual_git":
                            existing = s.one(
                                "SELECT repository_uuidv4 FROM source_repositories WHERE source_id=?",
                                (src["source_id"],),
                            )
                        ident = existing[0] if existing else str(uuid.uuid4())
                        if not existing:
                            s.execute(
                                "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,?,?)",
                                (ident, repo["name"], json.dumps(repo["metadata"])),
                            )
                        elif src["discovery_kind"] == "github_inventory":
                            s.execute(
                                "UPDATE repositories SET name=?,metadata=? WHERE repository_uuidv4=?",
                                (repo["name"], json.dumps(repo["metadata"]), ident),
                            )
                        if src["service_instance_uuidv4"]:
                            identity.bind(
                                s,
                                ident,
                                src["service_instance_uuidv4"],
                                provider_repository_id,
                            )
                        identity.link_source(s, src["source_id"], ident)
                        identity.add_endpoint(s, ident, repo["url"])
                        if not s.one(
                            "SELECT 1 FROM repository_name_assertions WHERE repository_uuidv4=? AND name=?",
                            (ident, repo["name"]),
                        ):
                            s.execute(
                                "INSERT INTO repository_name_assertions(repository_uuidv4,name,observed_at_us) VALUES(?,?,?)",
                                (ident, repo["name"], observed_at_us),
                            )
                        items.append({"repository_uuidv4": ident, "name": repo["name"]})
                    s.execute(
                        "INSERT INTO inventory_observations(inventory_observation_id,source_id,asserted_state,scope,observed_at_us,reason) VALUES(?,?,?,?,?,?)",
                        (
                            run,
                            src["source_id"],
                            "partial" if uncertainty else "complete",
                            json.dumps(inventory_scope),
                            observed_at_us,
                            uncertainty,
                        ),
                    )
                    s.publish()
            except CatalogError as e:
                acquisition_failed = True
                coverage.add("inventory", e.code, source_id=src["source_id"])
                with s.transaction():
                    s.execute(
                        "INSERT INTO inventory_observations(inventory_observation_id,source_id,asserted_state,scope,observed_at_us,reason) VALUES(?,?,?,?,?,?)",
                        (
                            run,
                            src["source_id"],
                            "partial",
                            json.dumps(inventory_scope),
                            observed_at_us,
                            e.code,
                        ),
                    )
        JobService(s).update(
            job,
            "complete" if not acquisition_failed else "waiting",
            result={
                "status": "complete"
                if coverage.complete_for_requested_scope
                else "partial",
                "skipped_sources": skipped,
            },
        )
        return Result(
            {"job_id": job, "repositories": items, "skipped_sources": skipped},
            coverage,
            "complete" if coverage.complete_for_requested_scope else "partial",
            s.revision(),
        )

    def sync(self, request):
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            if request.source is not None:
                identity.source_settings(identity.source(s, request.source))
            data = {
                "kind": request.kind,
                "repositories": list(request.repositories),
                "source": identity.source(s, request.source)["source_id"]
                if request.source is not None
                else None,
                "repository_endpoint_id": request.repository_endpoint_id,
            }
            job = JobService(s).create("sync", data)
            return self._sync(s, job, data)

    def resume(self, job):
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            row = s.one("SELECT kind FROM jobs WHERE job_id=?", (job,))
            if row is not None and row[0] not in ("discover", "sync"):
                raise CatalogError("INVALID_ARGUMENT", "Unsupported resumable job kind")
            kind, request = JobService(s).resume(job)
            if kind == "discover":
                return self._discover(s, job, request.get("source"))
            if kind == "sync":
                return self._sync(s, job, request)
            raise CatalogError("INVALID_ARGUMENT", "Unsupported resumable job kind")

    def _sync(self, s, job, request):
        items = []
        coverage = CoverageReport()
        not_before_us = None
        s.expected_attempt = s.one(
            "SELECT current_attempt FROM jobs WHERE job_id=?", (job,)
        )[0]
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
            if request.get("repository_endpoint_id") and len(repos) != 1:
                raise CatalogError(
                    "INVALID_ARGUMENT", "An explicit endpoint requires one repository"
                )
            for repo in repos:
                repository_endpoint_id = request.get("repository_endpoint_id")
                if not repository_endpoint_id and request.get("source"):
                    source = s.one(
                        "SELECT * FROM sources WHERE source_id=?", (request["source"],)
                    )
                    settings = identity.source_settings(source)
                    if source["discovery_kind"] == "manual_git":
                        source_endpoint = s.one(
                            "SELECT repository_endpoint_id FROM repository_endpoints WHERE repository_uuidv4=? AND url=?",
                            (
                                repo["repository_uuidv4"],
                                identity.git_url(settings["url"]),
                            ),
                        )
                        if not source_endpoint:
                            raise CatalogError(
                                "NOT_FOUND", "Source endpoint is not registered"
                            )
                        repository_endpoint_id = source_endpoint[0]
                for kind in (
                    ("git", "pr") if request["kind"] == "all" else (request["kind"],)
                ):
                    self.token.check()
                    try:
                        if kind == "git":
                            done = s.one(
                                "SELECT x.snapshot_id FROM snapshots x JOIN git_acquisitions a ON a.git_acquisition_id=x.git_acquisition_id JOIN acquisition_progress p ON p.git_acquisition_id=a.git_acquisition_id WHERE p.job_id=? AND a.repository_uuidv4=? AND a.kind='git' AND p.state='published' AND x.published=1",
                                (job, repo["repository_uuidv4"]),
                            )
                            item = (
                                {
                                    "repository_uuidv4": repo["repository_uuidv4"],
                                    "snapshot_id": done[0],
                                    "state": "complete",
                                }
                                if done
                                else GitImporter(s, self.token).sync(
                                    repo,
                                    job,
                                    repository_endpoint_id=repository_endpoint_id,
                                )
                            )
                        else:
                            src = identity.pr_source(
                                s, repo["repository_uuidv4"], request.get("source")
                            )
                            if not src:
                                if identity.pr_applicable(s, repo["repository_uuidv4"]):
                                    raise CatalogError(
                                        "PROVIDER_UNSUPPORTED",
                                        "PR/MR API collection requires a supported API source",
                                    )
                                items.append(
                                    {
                                        "kind": kind,
                                        "repository_uuidv4": repo["repository_uuidv4"],
                                        "state": "not_applicable",
                                    }
                                )
                                continue
                            from repo_catalog.adapters.github.collector import (
                                GitHubCollector,
                            )

                            api_repo = {
                                **dict(repo),
                                "source_id": src["source_id"],
                                "provider_repository_id": src["provider_repository_id"],
                            }
                            item = GitHubCollector(
                                s,
                                self.token,
                                config=identity.github_config(s, src),
                                repository_endpoint_id=repository_endpoint_id,
                            ).sync(api_repo, job)
                        items.append({"kind": kind, **item})
                    except CatalogError as e:
                        if e.code == "CANCELLED":
                            raise
                        coverage.add(
                            kind, e.code, repository_uuidv4=repo["repository_uuidv4"]
                        )
                        items.append(
                            {
                                "kind": kind,
                                "repository_uuidv4": repo["repository_uuidv4"],
                                "state": "partial",
                                "error": e.code,
                            }
                        )
                        not_before_us = e.details.get("not_before_us", not_before_us)
            JobService(s).update(
                job,
                "complete" if coverage.complete_for_requested_scope else "waiting",
                not_before_us=not_before_us,
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
