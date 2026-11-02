"""P5 production acquisition orchestration for Git Core, Provider Context, and Paired catalogs.

Implements:
- `GitAcquisition`: metadata-first and selective native Git + P4 Notes acquisition
- `ProviderAcquisition`: normalized GitHub REST/GraphQL intake into P3 Context
- `PairedAcquisitionCoordinator`: Core-first, Context-second coordinated admission and
  deferred CoreReference dependency reconciliation
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from typing import Iterator

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.adapters.github.production_intake import (
    NormalizedContextUnit,
    normalize_issue,
    normalize_issue_comment,
    normalize_pr_commit,
    normalize_pr_file,
    normalize_pull_request,
    normalize_repository_fields,
    normalize_review,
    normalize_review_comment,
    normalize_review_thread,
    normalize_timeline_event,
)
from repo_catalog.adapters.sqlite.acquisition import (
    OperationalAcquisitionLedger,
)
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import (
    AdmissionTransaction,
    PairCoordinator,
)
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.git_acquisition import (
    GitAcquisition as GitAcquisition,
)
from repo_catalog.application.git_acquisition import (
    _charge as _charge,
)
from repo_catalog.application.git_acquisition import (
    _defer_ref_work as _defer_ref_work,
)
from repo_catalog.application.git_acquisition import (
    _finish_ref_inventories as _finish_ref_inventories,
)
from repo_catalog.application.git_acquisition import (
    _open_core as _open_core,
)
from repo_catalog.application.git_acquisition import (
    _open_operational as _open_operational,
)
from repo_catalog.application.git_acquisition import (
    _PreparedCore as _PreparedCore,
)
from repo_catalog.domain.acquisition import (
    AcquisitionError,
    DependencyReconciliationReport,
    GitAcquisitionReport,
    GitMetadataInput,
    GitNativeAcquisitionRequest,
    PairedAcquisitionResult,
    ProviderAcquisitionReport,
    ProviderIntakeBatch,
)
from repo_catalog.domain.p1_context import (
    OMITTED_ISSUER,
    FieldClock,
    MappingProvenance,
    MappingSupport,
    ProviderRepositoryScope,
    ResourceKey,
    TransferEventReport,
    encode_transfer_supported_provenance,
)
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.ports.notes import NotesSource, request_scope
from repo_catalog.domain.production_context import CoreReference


class ProviderAcquisition:
    """Normalized Provider intake into P3 Context (standalone or paired)."""

    def __init__(
        self,
        context: Context | Path | str,
        *,
        core: GitCore | Path | str | None = None,
        operational: OperationalAcquisitionLedger | Path | str | None = None,
        authorization=None,
        admission=None,
    ) -> None:
        self.context = context
        self.core = core
        self.operational = operational
        self.authorization = authorization
        self.admission = admission

    @contextmanager
    def _open_context(self, override: Context | None = None) -> Iterator[Context]:
        auth, adm = self.authorization, self.admission
        if auth is None or adm is None:
            from repo_catalog.domain.context_admission import AdmissionRefused

            raise AdmissionRefused("PERMISSION_DENIED")
        if override is not None:
            yield override
            return
        if isinstance(self.context, Context):
            yield self.context
            return
        path = Path(self.context)
        if not (path / "context.sqlite3").is_file():
            from repo_catalog.domain.context_admission import AdmissionRefused

            raise AdmissionRefused("PERMISSION_DENIED")
        with Context.transaction(path, authorization=auth, admission=adm) as ctx:
            yield ctx

    def _make_core_validator(
        self,
        ctx: Context,
        core_override: GitCore | None = None,
    ) -> Callable[[str, str], bool]:
        target_core = core_override if core_override is not None else self.core
        if isinstance(target_core, GitCore):
            return lambda fmt, object_oid: bool(
                target_core.sql(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                    (fmt, object_oid),
                )
            )
        core_path: Path | None = None
        if isinstance(target_core, (Path, str)):
            p = Path(target_core)
            core_path = p if p.is_file() else (p / "core.sqlite3")
        elif (ctx.directory / "core.sqlite3").is_file():
            core_path = ctx.directory / "core.sqlite3"

        if core_path is None or not core_path.is_file():
            return lambda _fmt, _oid: False

        def _validate(fmt: str, object_oid: str) -> bool:
            with closing(connect(core_path, "core")) as db:
                row = db.execute(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                    (fmt, object_oid),
                ).fetchone()
                return row is not None

        return _validate

    @staticmethod
    def _ensure_repository_row(ctx: Context, repository_uuidv4: str) -> None:
        exists = ctx.db.execute(
            "SELECT 1 FROM repository_context WHERE repository_uuidv4=?",
            (repository_uuidv4,),
        ).fetchone()
        if not exists:
            ctx.repository(repository_uuidv4, "{}")

    def _admit_core_ref(
        self,
        ctx: Context,
        core_ref: CoreReference,
        clock: FieldClock,
        observed_at_us: int | None,
        validate_core: Callable[[str, str], bool],
        linked_list: list[CoreReference],
        pending_list: list[CoreReference],
    ) -> None:
        self._register_reference(ctx, core_ref.resource)
        ctx.report_core_reference(core_ref, clock=clock, observed_at_us=observed_at_us)
        if validate_core(
            core_ref.object_oid.object_format, core_ref.object_oid.object_oid
        ):
            ctx.link_core(
                core_ref.resource,
                core_ref.role,
                core_ref.object_oid.object_format,
                core_ref.object_oid.object_oid,
                core_ref.provenance_json,
                validate_core,
            )
            if core_ref not in linked_list:
                linked_list.append(core_ref)
        else:
            if core_ref not in pending_list:
                pending_list.append(core_ref)

    def _ensure_resource_hierarchy(
        self,
        ctx: Context,
        key: ResourceKey,
        repo_uuid: str | None,
        admitted: list[ResourceKey],
        identification=None,
    ) -> None:
        if identification is None and key.resource_kind in {
            "review",
            "comment",
            "thread",
            "document",
        }:
            try:
                identification = ctx.identification(key)
            except (ValueError, KeyError):
                pass
        ctx.resource(key, repo_uuid, identification=identification)
        if key not in admitted:
            admitted.append(key)

    def _admit_normalized_unit(
        self,
        ctx: Context,
        unit: NormalizedContextUnit,
        validate_core: Callable[[str, str], bool],
        admitted_resources: list[ResourceKey],
        admitted_texts: list[str],
        linked_refs: list[CoreReference],
        pending_refs: list[CoreReference],
    ) -> None:
        from repo_catalog.domain.resource_stage import (
            UnsupportedResourceStage,
            has_transfer_fence,
            refuse_transfer,
        )

        if unit.transfer_event:
            self._validate_transfer_evidence(unit)
            if has_transfer_fence(ctx.db):
                raise UnsupportedResourceStage("Provider Transfer intake")

        declarations = {obs.resource: obs.identification for obs in unit.observations}
        self._ensure_resource_hierarchy(
            ctx,
            unit.primary_resource,
            None,
            admitted_resources,
            declarations.get(unit.primary_resource),
        )
        for obs in unit.observations:
            self._ensure_resource_hierarchy(
                ctx, obs.resource, None, admitted_resources, obs.identification
            )
            ctx.observe(obs)
        for relation in unit.relations:
            if not unit.transfer_event:
                refuse_transfer(relation.relation_kind)
        for extra_text in unit.extra_texts:
            digest = ctx.text(extra_text)
            if digest not in admitted_texts:
                admitted_texts.append(digest)
        for res_key, text_val, clock, prov, obs_us in unit.text_admissions:
            self._ensure_resource_hierarchy(
                ctx, res_key, None, admitted_resources, declarations.get(res_key)
            )
            if text_val is not None:
                digest = ctx.text(text_val)
                if digest not in admitted_texts:
                    admitted_texts.append(digest)
            ctx.admit_text(res_key, text_val, clock, prov, obs_us)
        for rel in unit.relations:
            for member in rel.members:
                self._ensure_resource_hierarchy(
                    ctx, member, None, admitted_resources, declarations.get(member)
                )
            if rel.relation_kind == "provider_repository_roles" and unit.transfer_event:
                continue
            ctx.relation(rel)
            if rel.relation_kind == "provider_repository_roles":
                for qualified in ctx.provider_repository_roles(rel.resource):
                    if qualified.provenance_json == rel.provenance_json:
                        for candidate in qualified.resolved_candidates:
                            ctx.admit_repository_relation(
                                candidate,
                                require_support=not candidate.is_explicit_null_target,
                            )
        if unit.transfer_event:
            self._admit_transfer_unit(ctx, unit)
        for core_ref, clock, obs_us in unit.core_references:
            self._admit_core_ref(
                ctx,
                core_ref,
                clock,
                obs_us,
                validate_core,
                linked_refs,
                pending_refs,
            )

    def _validate_transfer_evidence(self, unit: NormalizedContextUnit) -> None:
        type_fields = [
            c
            for obs in unit.observations
            for c in obs.fields
            if c.resource == unit.primary_resource
            and c.field_name in ("event", "provider_event_type")
        ]
        if not type_fields or any(
            json.loads(c.value_json) not in ("transferred", "TransferredEvent")
            or c.clock != unit.clock
            or c.provenance_json != unit.provenance_json
            or c.observed_at_us != unit.observed_at_us
            for c in type_fields
        ):
            raise AcquisitionError("TRANSFER_TYPE_EVIDENCE", unit.primary_resource)
        role_relations = [
            r for r in unit.relations if r.relation_kind == "provider_repository_roles"
        ]
        scopes = (
            ProviderRepositoryScope.from_json(role_relations[0].scope_json)
            if role_relations
            else ProviderRepositoryScope({})
        )
        if len(role_relations) > 1:
            raise AcquisitionError("TRANSFER_REPORT_UNIT", unit.primary_resource)
        if any(
            role not in ("transfer_from_repository", "transfer_to_repository")
            for role in scopes.roles
        ):
            raise AcquisitionError("TRANSFER_REPORT_ROLE", unit.primary_resource)
        if role_relations:
            relation = role_relations[0]
            expected_members = {
                ResourceKey(
                    unit.primary_resource.service_instance_uuidv4,
                    "repository",
                    entry.provider_repository_id,
                )
                for entry in scopes.roles.values()
                if entry.provider_repository_id is not None
            }
            if (
                relation.resource != unit.primary_resource
                or relation.provenance_json != unit.provenance_json
                or relation.observed_at_us != unit.observed_at_us
                or len(relation.members) != len(expected_members)
                or set(relation.members) != expected_members
            ):
                raise AcquisitionError("TRANSFER_REPORT_UNIT", unit.primary_resource)

    def _admit_transfer_unit(self, ctx, unit):
        """One actual event observation, paired only within its immutable report."""
        self._validate_transfer_evidence(unit)
        role_relations = [
            r for r in unit.relations if r.relation_kind == "provider_repository_roles"
        ]
        scopes = (
            ProviderRepositoryScope.from_json(role_relations[0].scope_json)
            if role_relations
            else ProviderRepositoryScope({})
        )
        refs, targets, supports = {}, {}, []
        for role in ("transfer_from_repository", "transfer_to_repository"):
            entry = scopes.role(role)
            refs[role] = None
            targets[role] = None
            if entry is None:
                continue
            if entry.clock != unit.clock or entry.observed_at_us != unit.observed_at_us:
                raise AcquisitionError("TRANSFER_REPORT_CLOCK", unit.primary_resource)
            if entry.state == "explicit_null":
                targets[role] = "null"
                continue
            if entry.state != "unresolved_provider_only":
                raise AcquisitionError(
                    "TRANSFER_MAPPING_EVIDENCE", unit.primary_resource
                )
            provider = ResourceKey(
                unit.primary_resource.service_instance_uuidv4,
                "repository",
                entry.provider_repository_id,
            )
            refs[role] = provider
            self._ensure_resource_hierarchy(ctx, provider, None, [])
            by_target = {}
            for claim in ctx.evaluate_provider_repository(provider).active_claims:
                by_target.setdefault(claim.target_json, []).append(claim)
            targets[role] = tuple(sorted(by_target)) or None
            supports.extend(
                (role, MappingSupport(provider, tuple(claims)))
                for _, claims in sorted(by_target.items())
            )
        original = MappingProvenance.from_json(unit.provenance_json)
        issuer = (
            original.claimed_issuer
            if original.claimed_issuer_state != "omitted"
            else OMITTED_ISSUER
        )
        provenance = (
            unit.provenance_json
            if not supports
            else encode_transfer_supported_provenance(
                original.source, original.evidence, supports, claimed_issuer=issuer
            )
        )
        from repo_catalog.domain.p1_context import (
            ProviderEndpointDeclaration,
            canonical,
        )
        from repo_catalog.domain.parent_report import (
            ParentObservation,
            ParentReportKey,
        )
        from repo_catalog.domain.production_context import ResourceRelation

        decl_from = (
            refs.get("transfer_from_repository")
            if refs.get("transfer_from_repository") is not None
            else (
                "explicit_null"
                if targets.get("transfer_from_repository") == "null"
                else "not_reported"
            )
        )
        decl_to = (
            refs.get("transfer_to_repository")
            if refs.get("transfer_to_repository") is not None
            else (
                "explicit_null"
                if targets.get("transfer_to_repository") == "null"
                else "not_reported"
            )
        )
        endpoint_declaration = ProviderEndpointDeclaration(decl_from, decl_to)

        endpoints = []
        for role in ("transfer_from_repository", "transfer_to_repository"):
            val = targets.get(role)
            if val is not None:
                if isinstance(val, str):
                    endpoints.append((role, val))
                else:
                    for t in val:
                        endpoints.append((role, t))
        endpoints_tuple = tuple(endpoints)

        parent_row = ctx.db.execute(
            "SELECT members_json, provenance_json, scope_json, observed_at_us FROM resource_relations "
            "WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND relation_kind='parent'",
            unit.primary_resource.coordinates(),
        ).fetchone()
        if parent_row:
            parent_report = ParentObservation(
                ParentReportKey(
                    unit.primary_resource,
                    parent_row[0],
                    parent_row[1],
                    parent_row[2],
                ),
                parent_row[3],
            )
        else:
            coords = unit.primary_resource.scoped_document_coordinates()
            issue_key = ResourceKey(
                unit.primary_resource.service_instance_uuidv4, coords[0], coords[1]
            )
            self._ensure_resource_hierarchy(ctx, issue_key, None, [])
            parent_members = canonical([list(issue_key.coordinates())])
            parent_scope = canonical(
                {
                    "clock": json.loads(unit.clock.encode()),
                    "document_kind": coords[2] if len(coords) > 2 else "timeline_event",
                    "state": "complete",
                }
            )
            parent_report = ParentObservation(
                ParentReportKey(
                    unit.primary_resource,
                    parent_members,
                    provenance,
                    parent_scope,
                ),
                unit.observed_at_us,
            )
            ctx.relation(
                ResourceRelation(
                    unit.primary_resource,
                    "parent",
                    (issue_key,),
                    provenance,
                    parent_scope,
                    unit.observed_at_us,
                )
            )

        report = TransferEventReport.from_targets(
            unit.primary_resource,
            clock=unit.clock,
            provenance_json=provenance,
            observed_at_us=unit.observed_at_us,
            parent_report=parent_report,
            endpoint_declaration=endpoint_declaration,
            endpoints=endpoints_tuple,
            from_target_json=targets["transfer_from_repository"],
            to_target_json=targets["transfer_to_repository"],
        )
        # Mapping state may change after this real event. Re-delivery must replay
        # the original event unit, not issue a new provenance/key from a recheck.
        for prior in ctx.transfer_event_reports(unit.primary_resource):
            if prior.clock != unit.clock:
                continue
            old_supports = [
                (r.relation_kind, r.embedded_support)
                for r in (*prior.from_relations, *prior.to_relations)
                if r.embedded_support is not None
            ]
            expected = (
                unit.provenance_json
                if not old_supports
                else encode_transfer_supported_provenance(
                    original.source,
                    original.evidence,
                    old_supports,
                    claimed_issuer=issuer,
                )
            )
            if prior.provenance_json != expected:
                continue
            if (
                prior.from_provider_repository != report.from_provider_repository
                or prior.to_provider_repository != report.to_provider_repository
                or prior.provided_roles != report.provided_roles
                or (prior.from_state == "explicit_null")
                != (report.from_state == "explicit_null")
                or (prior.to_state == "explicit_null")
                != (report.to_state == "explicit_null")
                or prior.observed_at_us != unit.observed_at_us
            ):
                raise AcquisitionError("TRANSFER_REPORT_REBIND", unit.primary_resource)
            report = prior
            break
        ctx.admit_transfer_event(report)

    def admit_unit(
        self,
        unit: NormalizedContextUnit,
        *,
        context: Context | None = None,
        core: GitCore | None = None,
    ) -> None:
        """Admit a single NormalizedContextUnit into Context."""
        self._preflight_units((unit,))
        with self._open_context(context) as ctx, ctx._unit():
            validate_core = self._make_core_validator(ctx, core)
            self._admit_normalized_unit(
                ctx,
                unit,
                validate_core,
                [],
                [],
                [],
                [],
            )

    def admit_units(
        self,
        units: Sequence[NormalizedContextUnit],
        *,
        context: Context | None = None,
        core: GitCore | None = None,
    ) -> None:
        """Admit multiple NormalizedContextUnits into Context."""
        self._preflight_units(units)
        with self._open_context(context) as ctx, ctx._unit():
            validate_core = self._make_core_validator(ctx, core)
            for unit in units:
                self._admit_normalized_unit(
                    ctx,
                    unit,
                    validate_core,
                    [],
                    [],
                    [],
                    [],
                )

    @staticmethod
    def _preflight_units(units):
        from repo_catalog.domain.resource_stage import (
            UnsupportedResourceStage,
            _isolated_fixtures,
            refuse_transfer,
        )

        for unit in units:
            if unit.transfer_event:
                if not any(f._active for f in _isolated_fixtures.get()):
                    raise UnsupportedResourceStage("Provider Transfer intake")
            for relation in unit.relations:
                refuse_transfer(relation.relation_kind)

    @staticmethod
    def _register_reference(ctx, key):
        identification = None
        if key.resource_kind in {"review", "comment", "thread", "document"}:
            try:
                identification = ctx.identification(key)
            except (ValueError, KeyError):
                pass
        ctx.resource(key, identification=identification)

    def admit_batch(
        self,
        batch: ProviderIntakeBatch,
        *,
        context: Context | None = None,
        core: GitCore | None = None,
    ) -> ProviderAcquisitionReport:
        """Normalize and admit a ProviderIntakeBatch into Context."""
        from repo_catalog.domain.context_registration import registration_json

        for items, kind in (
            (batch.providers, "provider"),
            (batch.repositories, "repository"),
            (batch.sources, "source"),
        ):
            for item in items:
                registration_json(kind, item.configuration_json)
        for item in batch.sources:
            registration_json("membership", item.association_attributes_json)
        from repo_catalog.domain.resource_stage import refuse_transfer

        timeline_units = tuple(
            normalize_timeline_event(
                batch.service_instance_uuidv4,
                item.parent_kind,
                item.parent_id,
                item.event_id,
                item.payload,
                item.observed_at_us,
                item.provenance_json,
                graphql=item.graphql,
                parent_resource=item.parent_resource,
            )
            for item in batch.timeline_events
        )
        self._preflight_units(timeline_units)
        for relation in (*batch.mapping_claims, *batch.relations):
            refuse_transfer(relation.relation_kind)
        with self._open_context(context) as ctx, ctx._unit():
            validate_core = self._make_core_validator(ctx, core)

            for prov in batch.providers:
                ctx.provider(
                    prov.service_instance_uuidv4,
                    prov.provider_kind,
                    prov.configuration_json,
                )
            has_default_provider = ctx.db.execute(
                "SELECT 1 FROM providers WHERE service_instance_uuidv4=?",
                (batch.service_instance_uuidv4,),
            ).fetchone()
            if not has_default_provider:
                raise ValueError("explicit Provider registration required")

            admitted_resources: list[ResourceKey] = []
            admitted_texts: list[str] = []
            linked_refs: list[CoreReference] = []
            pending_refs: list[CoreReference] = []
            skipped_pr_issues = 0
            admitted_collections = 0
            admitted_inventories = 0

            for repo in batch.repositories:
                ctx.repository(repo.repository_uuidv4, repo.configuration_json)
                if repo.raw_metadata is not None:
                    obs_us = repo.observed_at_us
                    if repo.provenance_json is None:
                        raise ValueError(
                            "repository metadata requires original provenance"
                        )
                    prov_json = repo.provenance_json
                    unit = normalize_repository_fields(
                        batch.service_instance_uuidv4,
                        repo.raw_metadata,
                        obs_us,
                        prov_json,
                        clock_domain=repo.clock_domain,
                        graphql=repo.graphql,
                    )
                    self._admit_normalized_unit(
                        ctx,
                        unit,
                        validate_core,
                        admitted_resources,
                        admitted_texts,
                        linked_refs,
                        pending_refs,
                    )

            for claim in batch.mapping_claims:
                self._ensure_resource_hierarchy(
                    ctx, claim.resource, None, admitted_resources
                )
                ctx.admit_repository_relation(claim)
            for disposition in batch.mapping_dispositions:
                ctx.admit_mapping_disposition(disposition)
            for provider_repository in batch.provider_repositories:
                unit = normalize_repository_fields(
                    batch.service_instance_uuidv4,
                    provider_repository.payload,
                    provider_repository.observed_at_us,
                    provider_repository.provenance_json,
                    graphql=provider_repository.graphql,
                )
                self._admit_normalized_unit(
                    ctx,
                    unit,
                    validate_core,
                    admitted_resources,
                    admitted_texts,
                    linked_refs,
                    pending_refs,
                )

            for src in batch.sources:
                has_src_prov = ctx.db.execute(
                    "SELECT 1 FROM providers WHERE service_instance_uuidv4=?",
                    (src.service_instance_uuidv4,),
                ).fetchone()
                if not has_src_prov:
                    raise ValueError("Source requires registered Provider identity")
                ctx.source(
                    src.source_registration_uuidv4,
                    src.service_instance_uuidv4,
                    src.configuration_json,
                )
                for assoc_repo in src.associated_repositories:
                    self._ensure_repository_row(ctx, assoc_repo)
                    ctx.associate_source(
                        src.source_registration_uuidv4,
                        assoc_repo,
                        src.association_attributes_json,
                    )

            for inv in batch.source_inventories:
                for repo_uuid in inv.repositories:
                    self._ensure_repository_row(ctx, repo_uuid)
                ctx.inventory(inv)
                admitted_inventories += 1

            for cov_claim, inv in batch.source_inventory_proofs:
                for repo_uuid in inv.repositories:
                    self._ensure_repository_row(ctx, repo_uuid)
                ctx.inventory(inv)
                ctx.prove_inventory(cov_claim, inv)

            for issue_in in batch.issues:
                unit = normalize_issue(
                    batch.service_instance_uuidv4,
                    issue_in.payload,
                    issue_in.observed_at_us,
                    issue_in.provenance_json,
                    graphql=issue_in.graphql,
                )
                if unit is None:
                    skipped_pr_issues += 1
                else:
                    self._admit_normalized_unit(
                        ctx,
                        unit,
                        validate_core,
                        admitted_resources,
                        admitted_texts,
                        linked_refs,
                        pending_refs,
                    )

            for pr_in in batch.pull_requests:
                unit = normalize_pull_request(
                    batch.service_instance_uuidv4,
                    pr_in.payload,
                    pr_in.observed_at_us,
                    pr_in.provenance_json,
                    graphql=pr_in.graphql,
                )
                self._admit_normalized_unit(
                    ctx,
                    unit,
                    validate_core,
                    admitted_resources,
                    admitted_texts,
                    linked_refs,
                    pending_refs,
                )

            for rev_in in batch.reviews:
                unit = normalize_review(
                    batch.service_instance_uuidv4,
                    rev_in.pull_request_id,
                    rev_in.payload,
                    rev_in.observed_at_us,
                    rev_in.provenance_json,
                    graphql=rev_in.graphql,
                )
                self._admit_normalized_unit(
                    ctx,
                    unit,
                    validate_core,
                    admitted_resources,
                    admitted_texts,
                    linked_refs,
                    pending_refs,
                )

            for th_in in batch.review_threads:
                unit = normalize_review_thread(
                    batch.service_instance_uuidv4,
                    th_in.pull_request_id,
                    th_in.payload,
                    th_in.observed_at_us,
                    th_in.provenance_json,
                )
                self._admit_normalized_unit(
                    ctx,
                    unit,
                    validate_core,
                    admitted_resources,
                    admitted_texts,
                    linked_refs,
                    pending_refs,
                )

            for rc_in in batch.review_comments:
                unit = normalize_review_comment(
                    batch.service_instance_uuidv4,
                    rc_in.pull_request_id,
                    rc_in.payload,
                    rc_in.observed_at_us,
                    rc_in.provenance_json,
                    graphql=rc_in.graphql,
                    thread_id=rc_in.thread_id,
                )
                self._admit_normalized_unit(
                    ctx,
                    unit,
                    validate_core,
                    admitted_resources,
                    admitted_texts,
                    linked_refs,
                    pending_refs,
                )

            for ic_in in batch.issue_comments:
                unit = normalize_issue_comment(
                    batch.service_instance_uuidv4,
                    ic_in.parent_kind,
                    ic_in.parent_id,
                    ic_in.payload,
                    ic_in.observed_at_us,
                    ic_in.provenance_json,
                    graphql=ic_in.graphql,
                )
                self._admit_normalized_unit(
                    ctx,
                    unit,
                    validate_core,
                    admitted_resources,
                    admitted_texts,
                    linked_refs,
                    pending_refs,
                )

            for unit in timeline_units:
                self._admit_normalized_unit(
                    ctx,
                    unit,
                    validate_core,
                    admitted_resources,
                    admitted_texts,
                    linked_refs,
                    pending_refs,
                )

            for pc_in in batch.pr_commits:
                unit = normalize_pr_commit(
                    batch.service_instance_uuidv4,
                    pc_in.pull_request_id,
                    pc_in.payload,
                    pc_in.observed_at_us,
                    pc_in.provenance_json,
                )
                self._admit_normalized_unit(
                    ctx,
                    unit,
                    validate_core,
                    admitted_resources,
                    admitted_texts,
                    linked_refs,
                    pending_refs,
                )

            for pf_in in batch.pr_files:
                unit = normalize_pr_file(
                    batch.service_instance_uuidv4,
                    pf_in.pull_request_id,
                    pf_in.payload,
                    pf_in.observed_at_us,
                    pf_in.provenance_json,
                )
                self._admit_normalized_unit(
                    ctx,
                    unit,
                    validate_core,
                    admitted_resources,
                    admitted_texts,
                    linked_refs,
                    pending_refs,
                )

            for transfer in batch.transfers:
                raise AcquisitionError(
                    "ACTUAL_TRANSFER_EVENT_REQUIRED",
                    transfer.resource,
                    "Affiliation changes are not Transfer observations; use ProviderTimelineIntake",
                )

            for obs in batch.observations:
                ctx.observe(obs)
                if obs.resource not in admitted_resources:
                    admitted_resources.append(obs.resource)

            for rel in batch.relations:
                self._register_reference(ctx, rel.resource)
                for member in rel.members:
                    self._register_reference(ctx, member)
                ctx.relation(rel)

            for core_ref, clock, obs_us in batch.core_references:
                self._admit_core_ref(
                    ctx,
                    core_ref,
                    clock,
                    obs_us,
                    validate_core,
                    linked_refs,
                    pending_refs,
                )

            for coll in batch.collections:
                self._register_reference(ctx, coll.resource)
                for member in coll.members:
                    self._register_reference(ctx, member)
                ctx.collection(coll)
                admitted_collections += 1

            for cov_claim, coll, req_scope in batch.collection_proofs:
                self._register_reference(ctx, coll.resource)
                for member in coll.members:
                    self._register_reference(ctx, member)
                ctx.collection(coll)
                ctx.prove_collection(cov_claim, coll, required_scope_json=req_scope)

            for cov_claim in batch.coverage_claims:
                ctx.scope(cov_claim.scope)
                ctx.admit_coverage(cov_claim)

            return ProviderAcquisitionReport(
                service_instance_uuidv4=batch.service_instance_uuidv4,
                admitted_resources=tuple(admitted_resources),
                skipped_pull_request_issues=skipped_pr_issues,
                linked_core_references=tuple(linked_refs),
                pending_core_references=tuple(pending_refs),
                admitted_texts=tuple(admitted_texts),
                admitted_collections=admitted_collections,
                admitted_inventories=admitted_inventories,
            )


def _reconcile_context_dependencies_in_tx(
    ctx: Context,
    validate_core: Callable[[str, str], bool],
) -> DependencyReconciliationReport:
    promoted: list[CoreReference] = []
    unresolved: list[CoreReference] = []

    rows = ctx.db.execute(
        "SELECT DISTINCT service_instance_uuidv4, resource_kind, provider_resource_id "
        "FROM field_candidates WHERE field_name GLOB 'reported_core_reference:*' "
        "ORDER BY service_instance_uuidv4, resource_kind, provider_resource_id"
    ).fetchall()

    for svc, r_kind, p_id in rows:
        res_key = ResourceKey(svc, r_kind, p_id)
        deps = ctx.core_dependencies(res_key, validate=validate_core)
        already_required = {
            (
                d.reference.role,
                d.reference.object_oid.object_format,
                d.reference.object_oid.object_oid,
                d.reference.provenance_json,
            )
            for d in deps
            if d.required
        }
        for dep in deps:
            if dep.required:
                continue
            ref = dep.reference
            key_tuple = (
                ref.role,
                ref.object_oid.object_format,
                ref.object_oid.object_oid,
                ref.provenance_json,
            )
            if dep.available:
                if key_tuple not in already_required:
                    ctx.link_core(
                        ref.resource,
                        ref.role,
                        ref.object_oid.object_format,
                        ref.object_oid.object_oid,
                        ref.provenance_json,
                        validate_core,
                    )
                    already_required.add(key_tuple)
                    if ref not in promoted:
                        promoted.append(ref)
            else:
                if ref not in unresolved:
                    unresolved.append(ref)

    return DependencyReconciliationReport(
        promoted_references=tuple(promoted),
        remaining_unresolved=tuple(unresolved),
    )


class PairedAcquisitionCoordinator:
    """Coordinated Core-first, Context-second admission and dependency reconciliation."""

    def __init__(
        self,
        directory: Path | str,
        *,
        operational: OperationalAcquisitionLedger | Path | str | None = None,
        authorization=None,
        admission=None,
    ) -> None:
        self.directory = Path(directory)
        self.coordinator = PairCoordinator(self.directory, authorization=authorization)
        self.operational = operational if operational is not None else self.directory
        self.authorization = authorization
        self.admission = admission

    def _core_validator_on_disk(self) -> Callable[[str, str], bool]:
        core_path = self.directory / "core.sqlite3"

        def _validate(fmt: str, object_oid: str) -> bool:
            if not core_path.is_file():
                return False
            with closing(connect(core_path, "core")) as db:
                row = db.execute(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                    (fmt, object_oid),
                ).fetchone()
                return row is not None

        return _validate

    def admit_paired(
        self,
        *,
        git_source: GitNativeSource | None = None,
        git_request: GitNativeAcquisitionRequest | None = None,
        git_input: GitMetadataInput | None = None,
        notes_source: NotesSource | None = None,
        provider_batch: ProviderIntakeBatch | None = None,
        core_fn: Callable[[GitCore], GitAcquisitionReport | None] | None = None,
        context_fn: Callable[[Context], ProviderAcquisitionReport | None] | None = None,
        cut: Callable[[str], None] = lambda point: None,
        reconcile_dependencies: bool = True,
        new_request: bool = False,
        request_identity: RequestIdentity | None = None,
    ) -> PairedAcquisitionResult:
        """Execute Core-first, Context-second paired admission via PairCoordinator.admit."""
        if (self.directory / "p1-recovery-stop.json").exists():
            from repo_catalog.domain.p1_coordination import CoordinationError

            raise CoordinationError("RECOVERY_REQUIRED", "catalog")

        git_report_holder: list[GitAcquisitionReport | None] = [None]
        provider_report_holder: list[ProviderAcquisitionReport | None] = [None]

        def _core_unit(core_tx: AdmissionTransaction) -> None:
            with GitCore.for_transaction(core_tx) as core_cap:  # type: ignore[arg-type]
                git_acq = GitAcquisition(core_cap, operational=self.operational)
                if git_source is not None and git_request is not None:
                    git_report_holder[0] = git_acq.acquire_from_native(
                        git_source,
                        git_request,
                        new_request=new_request,
                        request_identity=request_identity,
                    )
                elif git_input is not None:
                    git_report_holder[0] = git_acq.acquire_metadata_only(
                        git_input,
                        notes_source=notes_source,
                        new_request=new_request,
                        request_identity=request_identity,
                    )
                elif core_fn is not None:
                    git_report_holder[0] = core_fn(core_cap)

        def _context_unit(context_tx: AdmissionTransaction) -> None:
            with Context.for_transaction(
                context_tx,
                self.directory,
                authorization=self.authorization,
                admission=self.admission,
            ) as ctx_cap:
                if provider_batch is not None:
                    prov_acq = ProviderAcquisition(
                        ctx_cap,
                        core=self.directory / "core.sqlite3",
                        operational=self.operational,
                        authorization=self.authorization,
                        admission=self.admission,
                    )
                    provider_report_holder[0] = prov_acq.admit_batch(
                        provider_batch, context=ctx_cap
                    )
                elif context_fn is not None:
                    provider_report_holder[0] = context_fn(ctx_cap)

                if (
                    reconcile_dependencies
                    and self.authorization is not None
                    and self.admission is not None
                ):
                    _reconcile_context_dependencies_in_tx(
                        ctx_cap, self._core_validator_on_disk()
                    )

        # Fetch/parse bounded external Git input before the short Core transaction.
        # Operational permits remain live until the prepared typed admissions finish.
        with ExitStack() as preparation:
            prepared = None
            if git_source is not None or git_input is not None:
                actual = preparation.enter_context(_open_core(self.directory))
                prepared = _PreparedCore(actual)
                unit = git_request if git_source is not None else git_input
                if unit is None:
                    raise ValueError("Git source requires a request")
                acq = GitAcquisition(prepared, operational=self.operational)
                custom_scope = None
                if git_source is not None and unit.notes is not None:
                    custom_scope = request_scope(
                        unit.repository_uuidv4,
                        actual.catalog_identity()[1],
                        unit.source_attribution,
                        GitNotesSource(git_source).scope,
                    )
                elif (
                    git_input is not None
                    and unit.notes is not None
                    and notes_source is not None
                ):
                    custom_scope = request_scope(
                        unit.repository_uuidv4,
                        actual.catalog_identity()[1],
                        unit.source_attribution,
                        notes_source.scope,
                    )
                budget, progress = preparation.enter_context(
                    acq._resolve_budget_and_progress(
                        actual,
                        "p5-git-native"
                        if git_source is not None
                        else "p5-git-metadata-input",
                        unit.capture_origin_uuidv4,
                        unit.capture_uuidv4,
                        None,
                        None,
                        custom_scope=custom_scope,
                        repository_uuidv4=unit.repository_uuidv4,
                        new_request=new_request,
                        request_identity=request_identity,
                    )
                )
                if git_source is not None:
                    git_report_holder[0] = acq.acquire_from_native(
                        git_source,
                        git_request,
                        work=budget,
                        progress=progress,
                        request_identity=budget.request,
                    )
                else:
                    git_report_holder[0] = acq.acquire_metadata_only(
                        git_input,
                        notes_source=notes_source,
                        work=budget,
                        progress=progress,
                    )

            def _prepared_core_unit(core_tx):
                if prepared is None:
                    return _core_unit(core_tx)
                with GitCore.for_transaction(core_tx) as core_cap:
                    prepared.apply(core_cap)

            auth = self.authorization
            adm = self.admission
            if (
                provider_batch is not None
                or context_fn is not None
                or (
                    reconcile_dependencies
                    and git_input is None
                    and git_source is None
                    and git_request is None
                )
            ):
                if auth is None or adm is None:
                    from repo_catalog.domain.context_admission import (
                        AdmissionRefused,
                    )

                    raise AdmissionRefused("PERMISSION_DENIED")

            coord = (
                self.coordinator
                if self.coordinator._authorization is not None
                else PairCoordinator(self.directory, authorization=auth)
            )
            admission = coord.admit(
                _prepared_core_unit,
                _context_unit,
                cut=cut,
                authorization=auth,
                admission=adm,
            )
            if prepared is not None and git_report_holder[0] is not None:
                actual_notes_source = (
                    GitNotesSource(git_source)
                    if git_source is not None and unit.notes is not None
                    else notes_source
                )
                try:
                    git_report_holder[0] = _finish_ref_inventories(
                        git_report_holder[0],
                        actual,
                        actual_notes_source,
                        budget,
                        progress,
                        unit.source_attribution,
                    )
                except BaseException as error:
                    try:
                        BaseException.add_note(
                            error,
                            "Core and Context committed before independent Notes inventory "
                            "verification; retry with the same request identity.",
                        )
                    except BaseException:
                        # A caller may supply malformed or immutable exception notes.
                        # Never replace its original exception during annotation.
                        pass
                    raise
            return PairedAcquisitionResult(
                admission=admission,
                git_report=git_report_holder[0],
                provider_report=provider_report_holder[0],
            )

    def reconcile_core_dependencies(self) -> DependencyReconciliationReport:
        """Promote unresolved `reported_core_reference:*` candidates once their OIDs exist in Core."""
        report_holder: list[DependencyReconciliationReport] = []

        def _core_noop(_core_tx: AdmissionTransaction) -> None:
            return None

        def _context_reconcile(context_tx: AdmissionTransaction) -> None:
            with Context.for_transaction(
                context_tx,
                self.directory,
                authorization=self.authorization,
                admission=self.admission,
            ) as ctx_cap:
                report = _reconcile_context_dependencies_in_tx(
                    ctx_cap, self._core_validator_on_disk()
                )
                report_holder.append(report)

        auth = self.authorization
        adm = self.admission
        if auth is None or adm is None:
            from repo_catalog.domain.context_admission import (
                AdmissionRefused,
            )

            raise AdmissionRefused("PERMISSION_DENIED")

        coord = (
            self.coordinator
            if self.coordinator._authorization is not None
            else PairCoordinator(self.directory, authorization=auth)
        )
        coord.admit(_core_noop, _context_reconcile, authorization=auth, admission=adm)
        return report_holder[0]
