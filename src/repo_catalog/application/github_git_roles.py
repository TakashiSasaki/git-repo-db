"""Explicit Git source checks for captured live Provider PR comparison inputs."""

from __future__ import annotations

import os
from copy import deepcopy
from fnmatch import fnmatchcase
from pathlib import Path
from string import Formatter
from uuid import uuid4

from repo_catalog.adapters.github.production_intake import (
    github_resource_id,
    parse_git_oid,
)
from repo_catalog.domain.models import CatalogError, Waiting
from repo_catalog.domain.p1_core import uuid4_value


def validate_git_source(value):
    if type(value) is not dict or set(value) - {
        "kind",
        "source_registration_uuidv4",
        "repository_uuidv4",
        "path_hex",
        "remote",
        "ref_templates",
        "metadata_bytes",
        "max_objects",
    }:
        raise ValueError("Explicit Git source object required")
    uuid4_value(value["source_registration_uuidv4"])
    uuid4_value(value["repository_uuidv4"])
    kind = value.get("kind", "local")
    if kind not in {"local", "remote"}:
        raise ValueError("Git source kind must be local or remote")
    if kind == "local":
        raw = bytes.fromhex(value["path_hex"])
        if (
            not raw
            or b"\0" in raw
            or raw.hex() != value["path_hex"]
            or "remote" in value
        ):
            raise ValueError("Canonical lossless local Git path required")
    elif type(value.get("remote")) is not dict or "path_hex" in value:
        raise ValueError("Explicit credential-free remote Git settings required")
    elif (
        type(value["remote"].get("refspecs")) not in (list, tuple)
        or not value["remote"]["refspecs"]
    ):
        raise ValueError(
            "Remote PR role work requires explicit refspecs covering its role refs"
        )
    if kind == "remote":
        from repo_catalog.application.remote_git_acquisition import (
            validate_remote_git_settings,
        )

        validate_remote_git_settings(value["remote"])
    templates = value.get("ref_templates")
    if (
        type(templates) is not dict
        or set(templates) - {"head", "base", "merge"}
        or not {"head", "base"} <= set(templates)
    ):
        raise ValueError("Explicit head/base ref templates required")
    for template in templates.values():
        if (
            type(template) is not str
            or not template.startswith("refs/")
            or "\0" in template
            or len(template) > 4096
        ):
            raise ValueError("Full bounded Git ref template required")
        for _, name, spec, conversion in Formatter().parse(template):
            if name is not None and (
                name not in {"number", "base_ref"} or spec or conversion
            ):
                raise ValueError("Only number/base_ref template fields are supported")
    for name, maximum in (("metadata_bytes", 2**63 - 1), ("max_objects", 100_000)):
        if name in value and (
            type(value[name]) is not int or not 0 < value[name] <= maximum
        ):
            raise ValueError("Positive finite Git source bound required")
    return value


class GitHubGitRoles:
    def __init__(
        self,
        catalog,
        config,
        *,
        ledger,
        work,
        progress,
        request,
        clock_us,
        cancelled=lambda: False,
    ):
        self.catalog, self.config = Path(catalog), deepcopy(validate_git_source(config))
        self.ledger, self.work, self.progress = ledger, work, progress
        self.request, self.clock_us = request, clock_us
        self.cancelled = cancelled
        self.targets = {}
        self.reports = []

    def _check_cancelled(self):
        if self.cancelled():
            raise CatalogError("CANCELLED", "Git role acquisition was cancelled")

    def record(self, parent, references):
        targets = self.targets.setdefault(parent.coordinates(), set())
        for reference, *_ in references:
            targets.add(reference.object_oid)

    def acquire(self, fetch, parent, number, detail, original, resource_path):
        from repo_catalog.adapters.git.metadata_walk import NativeMetadataWalk
        from repo_catalog.application.git_acquisition import GitAcquisition
        from repo_catalog.domain.git_acquisition import GitNativeAcquisitionRequest
        from repo_catalog.domain.p1_context import CoverageScope
        from repo_catalog.domain.p1_core import CoreFailure
        from repo_catalog.domain.p1_coverage import CoverageClaim
        from repo_catalog.domain.pr_assessment import git_role_check_scope
        from repo_catalog.domain.production_context import CollectionObservation
        from repo_catalog.domain.provider_acquisition import (
            ProviderPullRequestIntake,
            SourceRegistration,
            make_provenance,
        )

        config = self.config
        head = detail.get("head")
        base = detail.get("base")
        head_oid = parse_git_oid(head.get("sha")) if type(head) is dict else None
        base_oid = parse_git_oid(base.get("sha")) if type(base) is dict else None
        if (
            head_oid is None
            or base_oid is None
            or head_oid.object_format != base_oid.object_format
        ):
            fetch.partial_failure = fetch.partial_failure or "PR_CODE_INPUTS"
            return
        roles = {"head": head_oid, "base": base_oid}
        merge = parse_git_oid(detail.get("merge_commit_sha"))
        if merge is not None:
            roles["merge"] = merge
        templates = config["ref_templates"]
        if any(role not in templates for role in roles):
            fetch.partial_failure = fetch.partial_failure or "PR_GIT_ROUTE"
            return
        base_ref = base.get("ref")
        if any("{base_ref}" in template for template in templates.values()) and (
            type(base_ref) is not str or not base_ref
        ):
            fetch.partial_failure = fetch.partial_failure or "PR_GIT_ROUTE"
            return
        refs = {
            role: template.format(number=number, base_ref=base_ref).encode("utf-8")
            for role, template in templates.items()
            if role in roles
        }
        if config.get("kind", "local") == "remote" and any(
            not any(
                type(spec) is str
                and ":" in spec
                and fnmatchcase(name.decode("utf-8"), spec.split(":", 1)[1])
                for spec in config["remote"]["refspecs"]
            )
            for name in refs.values()
        ):
            fetch.partial_failure = fetch.partial_failure or "PR_GIT_ROUTE"
            return
        roots = tuple(
            sorted(
                set(roles.values()) | self.targets.get(parent.coordinates(), set()),
                key=lambda oid: oid.key,
            )
        )
        capture = str(uuid4())
        observed = self.clock_us()
        request = GitNativeAcquisitionRequest(
            config["repository_uuidv4"],
            self.request.request_origin_uuidv4,
            capture,
            "github-git-source:" + config["source_registration_uuidv4"],
            observed,
            select_object_oids=roots,
            include_refs=True,
            ref_prefixes=tuple(
                sorted({name.decode("utf-8") for name in refs.values()})
            ),
            nominated_ref_names=tuple(sorted(set(refs.values()))),
        )
        unit_scope = (
            "github-pr",
            fetch.service,
            parent.provider_resource_id,
            fetch.traversal_uuidv4,
        )

        def checked(enumerations):
            self._check_cancelled()
            links = {}
            for event in enumerations:
                for link in event.links:
                    name = link.observation.ref_name_bytes
                    if name not in links or link.claim.root_object_oid is not None:
                        links[name] = link
            checks = []
            mismatch = False
            for role, expected in roles.items():
                link = links.get(refs[role])
                if link is None:
                    continue
                actual = link.claim.root_object_oid
                mismatch |= actual != expected
                checks.append(
                    {
                        "role": role,
                        "expected_oid": list(expected.key),
                        "ref_name_hex": refs[role].hex(),
                        "actual_oid": None if actual is None else list(actual.key),
                        "ref_observation_key": list(
                            link.observation.ref_observation_key.key
                        ),
                    }
                )
            if not checks:
                raise CatalogError("PR_GIT_ROUTE", "No actual role ref observation")
            scope = git_role_check_scope(
                {
                    "source_registration_uuidv4": fetch.source,
                    "git_source_registration_uuidv4": config[
                        "source_registration_uuidv4"
                    ],
                    "repository_uuidv4": config["repository_uuidv4"],
                    "traversal_attempt_uuidv4": fetch.traversal_uuidv4,
                },
                head=head_oid,
                base=base_oid,
                anchor_provenance_json=original,
                role_checks=checks,
            )
            state = "partial" if mismatch or len(checks) != len(roles) else "complete"
            provenance = make_provenance(
                "github-git-role-check",
                {
                    "request_identity": list(self.request.values()),
                    "capture_origin_uuidv4": request.capture_origin_uuidv4,
                    "capture_uuidv4": capture,
                    "provider_detail_provenance_json": original,
                },
            )
            observation = CollectionObservation(
                parent, "git_role_checks", provenance, scope, observed, state, ()
            )
            claim = CoverageClaim(
                CoverageScope.collection(
                    parent, "git_role_checks", provenance, "git_role_checks"
                ),
                observed,
                state,
            )
            self.work.require("metadata_units", 1 + len(checks))
            self.work.charge("metadata_units", 1 + len(checks))
            fetch._emit(
                sources=(
                    SourceRegistration(
                        config["source_registration_uuidv4"],
                        fetch.service,
                        ensure_only=True,
                    ),
                ),
                collection_proofs=((claim, observation, scope),),
            )
            if state != "complete":
                raise CatalogError(
                    "PR_CODE_RACE",
                    "Fresh Git role refs differ from captured PR comparison",
                )

        def acquire(source):
            return GitAcquisition(
                self.catalog, operational=self.ledger
            ).acquire_from_native_with_budget(
                source,
                request,
                source_registration_uuidv4=config["source_registration_uuidv4"],
                ledger=self.ledger,
                work=self.work,
                progress=self.progress,
                request_identity=self.request,
                unit_scope=unit_scope,
                metadata_walk=NativeMetadataWalk(
                    source, roots, config.get("max_objects", 100_000)
                ),
                after_ref_scan=checked,
                before_metadata=self._check_cancelled,
            )

        try:
            self._check_cancelled()
            if config.get("kind", "local") == "local":
                from repo_catalog.adapters.git.native import GitNativeSource

                self.work.require("metadata_units", 1)
                self.work.charge("metadata_units", 1)
                source = GitNativeSource(
                    Path(os.fsdecode(bytes.fromhex(config["path_hex"]))),
                    metadata_bytes=config.get("metadata_bytes", 64 * 1024 * 1024),
                )
                report = acquire(source)
            else:
                from repo_catalog.application.remote_git_acquisition import (
                    acquire_remote_git_with_budget,
                )

                remote_document = dict(config["remote"])
                if "metadata_bytes" in config:
                    remote_document["metadata_bytes"] = config["metadata_bytes"]
                remote_report = acquire_remote_git_with_budget(
                    self.catalog,
                    {
                        **remote_document,
                        "request": request,
                        "request_identity": list(self.request.values()),
                        "new_request": False,
                    },
                    source_registration_uuidv4=config["source_registration_uuidv4"],
                    ledger=self.ledger,
                    work=self.work,
                    progress=self.progress,
                    request_identity=self.request,
                    unit_scope=unit_scope,
                    source_handler=acquire,
                    cancelled=self.cancelled,
                )
                self.reports.append(remote_report)
                report = remote_report.git_report
            if config.get("kind", "local") == "local":
                self.reports.append(report)
            if report.failure_code is not None:
                fetch.partial_failure = fetch.partial_failure or report.failure_code
            # This is a second genuine API observation, not a completion flag.
            # A later target cannot borrow the first comparison's listing or
            # native ref proof. Failed/unprojectable reads add no domain check.
            fresh, received, fresh_original = fetch._object(resource_path)
            if github_resource_id(fresh, graphql=False) != parent.provider_resource_id:
                raise CatalogError(
                    "SCOPE_MISMATCH", "Final PR check returned a different owner"
                )
            fetch._emit(
                pull_requests=(
                    ProviderPullRequestIntake(fresh, received, fresh_original),
                )
            )
            actual = {}
            for role in ("head", "base"):
                value = fresh.get(role)
                oid = parse_git_oid(value.get("sha")) if type(value) is dict else None
                if oid is None:
                    fetch.partial_failure = fetch.partial_failure or (
                        "PR_CODE_RACE" if role in fresh else "PR_CODE_CHECK_UNAVAILABLE"
                    )
                    return
                actual[role] = oid
            if "merge_commit_sha" in fresh:
                oid = parse_git_oid(fresh["merge_commit_sha"])
                if oid is not None:
                    actual["merge"] = oid
            elif "merge" in roles:
                fetch.partial_failure = (
                    fetch.partial_failure or "PR_CODE_CHECK_UNAVAILABLE"
                )
                return
            changed = actual != roles or any(
                key in detail and key in fresh and detail[key] != fresh[key]
                for key in ("commits", "changed_files")
            )
            if changed:
                fetch.partial_failure = fetch.partial_failure or "PR_CODE_RACE"
        except (CatalogError, CoreFailure) as error:
            if isinstance(error, Waiting):
                raise
            if error.code == "CANCELLED":
                raise
            if error.code in {
                "RECOVERY_REQUIRED",
                "RECOVERY_STOP",
                "AUTHORITATIVE_CORRUPTION",
                "INTEGRITY",
                "CORRUPT",
            }:
                raise
            fetch.partial_failure = fetch.partial_failure or error.code
