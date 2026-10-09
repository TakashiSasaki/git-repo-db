from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.git.importer import GitImporter
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application import job_plans
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
                "SELECT 1 FROM repository_observed_names WHERE repository_uuidv4=? AND name=?",
                (r["repository_uuidv4"], selector),
            )
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
            candidates = (
                [identity.source(s, source)]
                if source is not None
                else s.all("SELECT * FROM sources ORDER BY source_registration_uuidv4")
            )
            sources, skipped = [], []
            for candidate in candidates:
                try:
                    sources.append(job_plans.freeze_source(s, candidate))
                except CatalogError as cause:
                    if source is not None:
                        raise
                    skipped.append(
                        {
                            "source_registration_uuidv4": candidate[
                                "source_registration_uuidv4"
                            ],
                            "reason": cause.code,
                        }
                    )
            if not sources:
                raise CatalogError(
                    "NO_USABLE_SOURCE",
                    "No configured acquisition source",
                    {"sources": skipped},
                )
            plan = {
                "sources": sources,
                "source_registration_uuids": [
                    row["source_registration_uuidv4"] for row in candidates
                ],
                "skipped_sources": skipped,
                "acquisition_config": job_plans.freeze_config(s),
            }
            job = JobService(s).create("discover", plan)
            return self._discover(s, job, plan)

    def _discover(self, s, job, plan):
        from repo_catalog.adapters.sqlite.parser_model import ParserModel
        from repo_catalog.adapters.sqlite.payloads import intern_payload

        job_plans.activate(s, plan)
        sources = plan["sources"]
        items = []
        coverage = CoverageReport()
        skipped = list(plan["skipped_sources"])
        for skipped_source in skipped:
            coverage.add(
                "inventory",
                skipped_source["reason"],
                source_registration_uuidv4=skipped_source["source_registration_uuidv4"],
            )
        source_outcomes = list(skipped)
        acquisition_failed = False
        for src in sources:
            try:
                self.token.check()
            except CatalogError as cause:
                JobService(s).update(
                    job,
                    "interrupted",
                    cause.code,
                    result={
                        "status": "partial",
                        "source_outcomes": source_outcomes,
                        "skipped_sources": skipped,
                    },
                )
                cause.details["job_id"] = job
                raise
            try:
                job_plans.check_registration(s, src)
                settings = json.loads(src["settings"])
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
            result_uuid = None
            model = ParserModel(s.connection)
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
                        s, self.token, config=src["github_config"]
                    )
                    inventory_scope["response_evidence"] = collector.inventory_evidence
                    repos = collector.inventory(src, job)
                    uncertainty = collector.inventory_uncertainty
                if uncertainty:
                    acquisition_failed = True
                    coverage.add("inventory", uncertainty, source_id=src["source_id"])
                with s.transaction():
                    if collector is not None:
                        result_uuid = collector.inventory_result(src)
                    else:
                        input_uuid = str(uuid.uuid4())
                        ref = intern_payload(
                            s.connection,
                            json.dumps(settings, sort_keys=True).encode(),
                            representation="legacy_normalized",
                        )
                        s.execute(
                            "INSERT INTO source_input_observations(source_input_uuidv4,source_registration_uuidv4,observed_at_us,request_context_json,payload_representation,payload_sha256) VALUES(?,?,?,?,?,?)",
                            (
                                input_uuid,
                                src["source_registration_uuidv4"],
                                observed_at_us,
                                json.dumps(
                                    {
                                        "kind": "manual_git_configuration",
                                        "source_registration_uuidv4": src[
                                            "source_registration_uuidv4"
                                        ],
                                    }
                                ),
                                *ref.parameters(),
                            ),
                        )
                        profile = model.ensure_builtin_profile()
                        result_uuid = model.create_result(
                            profile,
                            source_registration_uuidv4=src[
                                "source_registration_uuidv4"
                            ],
                            inputs=[{"source_input_uuidv4": input_uuid}],
                        )
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
                                (ident, repo["name"], "{}"),
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
                        identity.observe_name(
                            s,
                            ident,
                            repo["name"],
                            observed_at_us,
                            parsed_result_uuidv4=result_uuid,
                        )
                        s.execute(
                            "INSERT INTO repository_inventory_observations VALUES(?,?,?,?,?,?)",
                            (
                                str(uuid.uuid4()),
                                ident,
                                result_uuid,
                                src["source_registration_uuidv4"],
                                repo["name"],
                                json.dumps(repo["metadata"], allow_nan=False),
                            ),
                        )
                        items.append({"repository_uuidv4": ident, "name": repo["name"]})
                    s.execute(
                        "INSERT INTO inventory_observations(inventory_observation_id,source_id,asserted_state,scope,observed_at_us,reason,parsed_result_uuidv4,source_registration_uuidv4) VALUES(?,?,?,?,?,?,?,?)",
                        (
                            run,
                            src["source_id"],
                            "partial" if uncertainty else "complete",
                            json.dumps(inventory_scope),
                            observed_at_us,
                            uncertainty,
                            result_uuid,
                            src["source_registration_uuidv4"],
                        ),
                    )
                    if not self._publish_inventory(s, model, result_uuid, src):
                        coverage.add(
                            "inventory",
                            "PARSER_PROFILE_UNSELECTED",
                            source_id=src["source_id"],
                        )
                    s.publish()
                source_outcomes.append(
                    {
                        "source_registration_uuidv4": src["source_registration_uuidv4"],
                        "state": "partial" if uncertainty else "complete",
                        "parsed_result_uuidv4": result_uuid,
                    }
                )
            except CatalogError as e:
                if e.code == "CANCELLED":
                    JobService(s).update(
                        job,
                        "interrupted",
                        e.code,
                        result={
                            "status": "partial",
                            "source_outcomes": source_outcomes,
                            "skipped_sources": skipped,
                        },
                    )
                    e.details["job_id"] = job
                    raise
                acquisition_failed = True
                coverage.add("inventory", e.code, source_id=src["source_id"])
                source_outcomes.append(
                    {
                        "source_registration_uuidv4": src["source_registration_uuidv4"],
                        "state": "failed",
                        "reason": e.code,
                    }
                )
                # An attempted request with no received input is a job outcome,
                # never remote inventory evidence.
                if collector is not None and collector.inventory_evidence:
                    with s.transaction():
                        result_uuid = collector.inventory_result(src)
                        s.execute(
                            "INSERT INTO inventory_observations(inventory_observation_id,source_id,asserted_state,scope,observed_at_us,reason,parsed_result_uuidv4,source_registration_uuidv4) VALUES(?,?,?,?,?,?,?,?)",
                            (
                                run,
                                src["source_id"],
                                "partial",
                                json.dumps(inventory_scope),
                                observed_at_us,
                                e.code,
                                result_uuid,
                                src["source_registration_uuidv4"],
                            ),
                        )
                        self._publish_inventory(s, model, result_uuid, src)
        JobService(s).update(
            job,
            "complete" if not acquisition_failed else "waiting",
            result={
                "status": "complete"
                if coverage.complete_for_requested_scope
                else "partial",
                "skipped_sources": skipped,
                "source_outcomes": source_outcomes,
            },
        )
        return Result(
            {"job_id": job, "repositories": items, "skipped_sources": skipped},
            coverage,
            "complete" if coverage.complete_for_requested_scope else "partial",
            s.revision(),
        )

    @staticmethod
    def _publish_inventory(store, model, result_uuid, src):
        model.publish_result(result_uuid)
        profile = store.one(
            "SELECT parser_profile_uuidv4 FROM parsed_results WHERE parsed_result_uuidv4=?",
            (result_uuid,),
        )[0]
        scope = model.ensure_scope_profile(
            profile,
            source_registration_uuidv4=src["source_registration_uuidv4"],
            fact_kind="inventory",
        )
        if scope is None:
            return False
        model.select_fact(result_uuid, fact_kind="inventory")
        return True

    def sync(self, request):
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as s:
            explicit = identity.source(s, request.source) if request.source else None
            if explicit is not None:
                job_plans.freeze_source(s, explicit)
            source_id = explicit["source_id"] if explicit is not None else None
            repos = select_repositories(s, request.repositories, source_id)
            if request.repository_endpoint_id and len(repos) != 1:
                raise CatalogError(
                    "INVALID_ARGUMENT", "An explicit endpoint requires one repository"
                )
            targets, sources, skipped_sources = [], {}, []
            for repo in repos:
                if request.kind in ("git", "all") and repo.get("source_id"):
                    git_source = identity.source(s, "local:" + repo["source_id"])
                    frozen_git_source = job_plans.freeze_source(
                        s, git_source, require_credentials=False
                    )
                    sources[frozen_git_source["source_registration_uuidv4"]] = (
                        frozen_git_source
                    )
                target = {
                    "repository": dict(repo),
                    "repository_endpoint_id": request.repository_endpoint_id,
                }
                if request.kind in ("git", "all"):
                    endpoint_id = request.repository_endpoint_id
                    if (
                        endpoint_id is None
                        and explicit is not None
                        and explicit["discovery_kind"] == "manual_git"
                    ):
                        url = identity.git_url(
                            identity.source_settings(explicit)["url"]
                        )
                        endpoint = s.one(
                            "SELECT * FROM repository_endpoints WHERE repository_uuidv4=? AND url=?",
                            (repo["repository_uuidv4"], url),
                        )
                        if endpoint is None:
                            raise CatalogError(
                                "NOT_FOUND", "Source endpoint is not registered"
                            )
                    else:
                        endpoint = identity.endpoint(
                            s, repo["repository_uuidv4"], endpoint_id
                        )
                    target["repository_endpoint_id"] = endpoint[
                        "repository_endpoint_id"
                    ]
                    target["endpoint_url"] = endpoint["url"]
                if request.kind in ("pr", "all"):
                    src = identity.pr_source(s, repo["repository_uuidv4"], source_id)
                    if src is not None:
                        try:
                            frozen = job_plans.freeze_source(s, src)
                        except CatalogError as cause:
                            if explicit is not None:
                                raise
                            diagnostic = {
                                "source_registration_uuidv4": src[
                                    "source_registration_uuidv4"
                                ],
                                "repository_uuidv4": repo["repository_uuidv4"],
                                "reason": cause.code,
                            }
                            target["api_source_skip"] = diagnostic
                            skipped_sources.append(diagnostic)
                        else:
                            target["api_source"] = frozen
                            sources[frozen["source_registration_uuidv4"]] = frozen
                targets.append(target)
            if explicit is not None:
                sources[explicit["source_registration_uuidv4"]] = (
                    job_plans.freeze_source(s, explicit)
                )
            if request.kind == "pr" and skipped_sources and not sources:
                raise CatalogError(
                    "NO_USABLE_SOURCE",
                    "No configured acquisition source",
                    {"sources": skipped_sources},
                )
            data = {
                "source_registration_uuids": sorted(
                    set(sources)
                    | {row["source_registration_uuidv4"] for row in skipped_sources}
                ),
                "skipped_sources": skipped_sources,
                "kind": request.kind,
                "repositories": [r["repository_uuidv4"] for r in repos],
                "source": source_id,
                "targets": targets,
                "sources": list(sources.values()),
                "acquisition_config": job_plans.freeze_config(s),
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
                return self._discover(s, job, request)
            if kind == "sync":
                return self._sync(s, job, request)
            raise CatalogError("INVALID_ARGUMENT", "Unsupported resumable job kind")

    def _sync(self, s, job, request):
        job_plans.activate(s, request)
        items = []
        coverage = CoverageReport()
        acquisition_failed = False
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
            for target in request["targets"]:
                repo = target["repository"]
                repository_endpoint_id = target["repository_endpoint_id"]
                if target.get("endpoint_url") is not None:
                    endpoint = identity.endpoint(
                        s, repo["repository_uuidv4"], repository_endpoint_id
                    )
                    if endpoint["url"] != target["endpoint_url"]:
                        raise CatalogError(
                            "ENDPOINT_CHANGED", "Frozen endpoint changed"
                        )
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
                            if target.get("api_source_skip"):
                                reason = target["api_source_skip"]
                                coverage.add(
                                    "pr",
                                    reason["reason"],
                                    repository_uuidv4=repo["repository_uuidv4"],
                                )
                                items.append(
                                    {"kind": "pr", "state": "skipped", **reason}
                                )
                                continue
                            src = target.get("api_source")
                            if src is not None:
                                job_plans.check_registration(s, src)
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
                                config=src["github_config"],
                                repository_endpoint_id=repository_endpoint_id,
                            ).sync(api_repo, job)
                        if (
                            kind == "git"
                            and item.get("snapshot_id")
                            and not s.one(
                                "SELECT 1 FROM current_snapshots WHERE repository_uuidv4=? AND snapshot_id=?",
                                (repo["repository_uuidv4"], item["snapshot_id"]),
                            )
                        ):
                            coverage.add(
                                "git",
                                "CURRENT_SELECTION_UNRESOLVED",
                                repository_uuidv4=repo["repository_uuidv4"],
                            )
                            item = {
                                **item,
                                "state": "partial",
                                "acquisition_complete": True,
                                "current_selection": "unresolved",
                            }
                        items.append({"kind": kind, **item})
                    except CatalogError as e:
                        if e.code == "CANCELLED":
                            raise
                        skipped_before_acquisition = e.code in (
                            "SOURCE_CREDENTIAL_UNAVAILABLE",
                            "SOURCE_UNCONFIGURED",
                            "SOURCE_INVALID_SETTINGS",
                            "SOURCE_IDENTITY_CHANGED",
                        )
                        acquisition_failed |= not skipped_before_acquisition
                        coverage.add(
                            kind, e.code, repository_uuidv4=repo["repository_uuidv4"]
                        )
                        items.append(
                            {
                                "kind": kind,
                                "repository_uuidv4": repo["repository_uuidv4"],
                                "state": "skipped"
                                if skipped_before_acquisition
                                else "partial",
                                "source_registration_uuidv4": target.get(
                                    "api_source", {}
                                ).get("source_registration_uuidv4"),
                                "error": e.code,
                            }
                        )
                        not_before_us = e.details.get("not_before_us", not_before_us)
            JobService(s).update(
                job,
                "waiting" if acquisition_failed else "complete",
                not_before_us=not_before_us,
                result={
                    "status": "complete"
                    if coverage.complete_for_requested_scope
                    else "partial",
                    "source_outcomes": items,
                },
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
