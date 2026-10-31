"""P5 production acquisition orchestration for Git Core, Provider Context, and Paired catalogs.

Implements:
- `GitAcquisition`: metadata-first and selective native Git + P4 Notes acquisition
- `ProviderAcquisition`: normalized GitHub REST/GraphQL intake into P3 Context
- `PairedAcquisitionCoordinator`: Core-first, Context-second coordinated admission and
  deferred CoreReference dependency reconciliation
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from contextlib import ExitStack, closing, contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

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
from repo_catalog.application.notes import (
    Discovery,
    NotesAcquisition,
    RefNoteAcquisition,
    RefNotesInventory,
    RefNotesInventoryVerification,
)
from repo_catalog.application.ref_observations import EnumeratedRef, RefScan, pin_scan
from repo_catalog.domain.acquisition import (
    AcquisitionError,
    DependencyReconciliationReport,
    GitAcquisitionReport,
    GitMetadataInput,
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
    PairedAcquisitionResult,
    ProviderAcquisitionReport,
    ProviderIntakeBatch,
)
from repo_catalog.domain.git_native import DECODER, DECODER_VERSION, parse_metadata
from repo_catalog.domain.native_acquisition import (
    metadata_input_intent,
    native_request_intent,
    ref_input_processing,
    ref_notes_input_intent,
    without_ref_inputs,
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
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
from repo_catalog.domain.p1_core import (
    OID,
    CoreCoverageScope,
    CoreFailure,
    GitObservation,
    NativeObject,
    Provenance,
    RelationGroup,
    RelationMember,
    ScalarClaim,
    account_verification,
    encode,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ports.notes import NotesSource, request_scope
from repo_catalog.domain.ports.p1_core import WorkBudget
from repo_catalog.domain.production_context import CoreReference


def _charge(work: WorkBudget, unit: str, amount: int = 1) -> None:
    work.require(unit, amount)
    work.charge(unit, amount)


class _PreparedCore:
    """Finite in-memory typed admission plan; confers no database capability."""

    _methods = frozenset(
        (
            "admit_repository",
            "admit_repository_claim",
            "admit_object",
            "admit_claim",
            "admit_group",
            "admit_observation",
            "admit_ref_enumeration",
            "admit_ref_observation",
            "admit_ref_observation_claim",
            "admit_notes_mapping",
            "admit_notes_mapping_claim",
            "admit_notes_mapping_evidence",
            "admit_notes_mapping_group",
            "admit_ref_note",
            "admit_metadata",
            "admit_coverage_scope",
            "admit_coverage",
            "admit_coverage_proof",
        )
    )

    def __init__(self, core: GitCore):
        self.core = core
        self.operations = []

    def ensure_available(self):
        self.core.ensure_available()

    def catalog_identity(self):
        return self.core.catalog_identity()

    def ref_observation(self, key, work):
        from repo_catalog.domain.ref_observation import (
            RefObservationProjection,
            ref_claim_conflict,
        )

        subject = None
        claims = []
        for name, args, _ in reversed(self.operations):
            _charge(work, "metadata_units", 1)
            if name == "admit_ref_observation" and args[0].ref_observation_key == key:
                subject = args[0]
            elif (
                name == "admit_ref_observation_claim"
                and args[0].ref_observation_key == key
            ):
                claims.append(args[0])
            if name == "admit_ref_enumeration":
                links = args[1]
                for link in links:
                    _charge(work, "metadata_units", 1)
                    if link.observation.ref_observation_key == key:
                        subject = link.observation
                        claims.append(link.claim)
        if subject is not None:
            return RefObservationProjection(
                subject, tuple(claims), ref_claim_conflict(tuple(claims))
            )
        return self.core.ref_observation(key, work)

    def __getattr__(self, name):
        if name not in self._methods:
            raise AttributeError(name)

        def prepare(*args, **kwargs):
            if len(self.operations) >= 200_000:
                raise CoreFailure("BUDGET", "admission-plan", "finite operation count")
            self.operations.append((name, args, kwargs))

        return prepare

    def apply(self, core: GitCore):
        for name, args, kwargs in self.operations:
            getattr(core, name)(*args, **kwargs)


def _finish_ref_inventories(report, core, source, work, progress, source_attribution):
    """Verify reported groups only after their Core admission is durable."""
    if isinstance(core, _PreparedCore):
        return report
    if not report.ref_notes_inventories:
        return core._complete_read(report)
    if source is None:
        raise CoreFailure("NOTES_SCOPE", "inventory", "actual Notes source required")
    external = getattr(core, "_external", False)
    notes_app = None
    if not external:
        notes_app = NotesAcquisition(
            core,
            source,
            work,
            progress,
            source_attribution=source_attribution,
            repository_uuidv4=report.repository_uuidv4,
        )
    verifications = []
    problem = None
    for inventory in report.ref_notes_inventories:
        _charge(work, "metadata_units", 1)
        if inventory.failure_code is not None:
            result = RefNotesInventoryVerification(
                inventory.group,
                None,
                None,
                False,
                inventory.failure_code,
                inventory.detail,
            )
        elif external:
            result = RefNotesInventoryVerification(
                inventory.group,
                None,
                None,
                False,
                "REF_INVENTORY_DEFERRED",
                "verify after the caller-owned Core transaction commits",
            )
        else:
            assert notes_app is not None
            result = notes_app.verify_ref_inventory(inventory.group)
        verifications.append(result)
        if not result.verified and problem is None:
            problem = (result.failure_code or "NOTES_INVENTORY", result.detail)
    _charge(work, "metadata_units", len(verifications))
    projections = [None] * len(verifications)
    selected = []
    for index, (inventory, result) in enumerate(
        zip(report.ref_notes_inventories, verifications, strict=True)
    ):
        _charge(work, "metadata_units", 2)
        if result.verified:
            selected.append((index, inventory.group))
    if selected:
        # The checked adapter protects callbacks and pins one Core snapshot.
        views = core.ref_notes_inventory_projections(
            tuple(group for _, group in selected), work
        )
        for (index, _), (projection, current) in zip(selected, views, strict=True):
            _charge(work, "metadata_units", 1)
            projections[index] = projection
            if problem is None and (
                projection.coverage.state != "complete" or not current
            ):
                problem = (
                    "REF_INVENTORY_CONFLICT"
                    if projection.coverage.state == "conflict"
                    else "REF_INVENTORY_NOT_CURRENT",
                    "latest Coverage does not establish this whole inventory",
                )
    status = report.status
    if problem is not None and status in ("complete", "known_empty"):
        status = "partial" if report.admitted_objects else "unknown"
    _charge(work, "metadata_units", 2 * len(verifications))
    completed = replace(
        report,
        status=status,
        failure_code=report.failure_code or (problem[0] if problem else None),
        failure_detail=report.failure_detail or (problem[1] if problem else ""),
        ref_inventory_verifications=tuple(verifications),
        ref_inventory_projections=tuple(projections),
    )
    return core._complete_read(completed)


def _defer_ref_work(report, spec, source):
    """A rootless report or missing source cannot satisfy requested verification."""
    if spec is None or not (spec.acquire_inventories or spec.target_object_oids):
        return report
    deferred = tuple(
        claim
        for unit in spec.ref_inputs
        for claim in unit.claims
        if claim.root_object_oid is None or source is None
    )
    if not deferred:
        return report
    return replace(
        report,
        deferred_ref_claims=deferred,
        status="partial" if report.admitted_objects else "unknown",
        failure_code=report.failure_code or "REF_NOTES_DEFERRED",
        failure_detail=report.failure_detail
        or "requested Notes work needs a concrete root and source",
    )


@contextmanager
def _open_core(target: GitCore | Path | str) -> Iterator[GitCore]:
    if isinstance(target, (GitCore, _PreparedCore)):
        yield target
        return
    path = Path(target)
    if path.is_dir():
        path = path / "core.sqlite3"
    core = GitCore(path)
    try:
        yield core
    finally:
        core.close()


@contextmanager
def _open_operational(
    target: OperationalAcquisitionLedger | Path | str | None,
    *,
    repository_uuidv4: str | None = None,
    catalog_instance_uuidv4: str | None = None,
) -> Iterator[OperationalAcquisitionLedger | None]:
    if target is None:
        yield None
        return
    if isinstance(target, OperationalAcquisitionLedger):
        yield target
        return
    path = Path(target)
    if path.is_dir():
        path = path / "operational.sqlite3"
    if not path.exists():
        yield None
        return
    ledger = OperationalAcquisitionLedger(
        path,
        repository_uuidv4=repository_uuidv4,
        catalog_instance_uuidv4=catalog_instance_uuidv4,
    )
    try:
        yield ledger
    finally:
        ledger.close()


class GitAcquisition:
    """Metadata-first and selective native Git + Notes acquisition into P2 GitCore."""

    def __init__(
        self,
        core: GitCore | Path | str,
        *,
        operational: OperationalAcquisitionLedger | Path | str | None = None,
        work: WorkBudget | None = None,
        progress: Any | None = None,
    ) -> None:
        self.core = core
        self.operational = operational
        self.work = work
        self.progress = progress

    @contextmanager
    def _resolve_budget_and_progress(
        self,
        core_cap: GitCore,
        scope_tag: str,
        origin_uuidv4: str,
        unit_uuidv4: str,
        work: WorkBudget | None,
        progress: Any | None,
        *,
        custom_scope: Any | None = None,
        repository_uuidv4: str | None = None,
        new_request: bool = False,
        request_identity: RequestIdentity | None = None,
    ) -> Iterator[tuple[WorkBudget, Any]]:
        if work is not None and progress is not None:
            yield work, progress
            return
        repo_uuid, instance_uuid = core_cap.catalog_identity()
        with _open_operational(
            self.operational,
            repository_uuidv4=repo_uuid,
            catalog_instance_uuidv4=instance_uuid,
        ) as ledger:
            if ledger is not None and (work is None and self.work is None):
                req = request_identity or RequestIdentity(origin_uuidv4, unit_uuidv4)
                target_scope = (
                    custom_scope
                    if custom_scope is not None
                    else [
                        scope_tag,
                        repository_uuidv4 or repo_uuid,
                        origin_uuidv4,
                        unit_uuidv4,
                    ]
                )
                _, _, op_work, op_progress = ledger.create_budget(
                    scope=target_scope,
                    request=req,
                    new_request=new_request,
                )
                yield (
                    op_work,
                    progress
                    if progress is not None
                    else (self.progress if self.progress is not None else op_progress),
                )
                return
            raise CoordinationError(
                "CONTINUATION_UNAVAILABLE",
                "request",
                "durable Operational ledger or explicit cumulative work and progress required",
            )

    def _admit_metadata_claims_only(
        self,
        core_cap: GitCore,
        native: NativeObject,
        source_attribution: str,
        origin_uuidv4: str,
        capture_uuidv4: str,
        work: WorkBudget,
    ) -> tuple[OID, ...]:
        """Parse a validated commit/tree/tag and admit its claims and relations without retaining raw bytes."""
        with account_verification(work):
            native.validate()
            parsed = parse_metadata(
                native.object_oid.object_format, native.native_type, native.body
            )
            _charge(work, "metadata_units", 1)

        evidence_coord = encode([origin_uuidv4, capture_uuidv4, *native.object_oid.key])
        core_cap.admit_object(native.object_oid)
        discovered_targets: list[OID] = []

        for field_name, val in parsed.scalars.items():
            prov = Provenance(
                source_attribution,
                evidence_coord,
                f"native-{field_name}",
                DECODER,
                DECODER_VERSION,
                "reported",
            )
            claim = ScalarClaim(native.object_oid, field_name, val, prov)
            _charge(work, "metadata_units", 1)
            core_cap.admit_claim(claim)

        for rel_name, raw_members in parsed.relations.items():
            prov = Provenance(
                source_attribution,
                evidence_coord,
                rel_name,
                DECODER,
                DECODER_VERSION,
                "reported",
            )
            members = tuple(
                RelationMember(
                    tuple(m[0]) if isinstance(m[0], list) else m[0],
                    OID(m[1], m[2]),
                )
                for m in raw_members
            )
            for member in members:
                discovered_targets.append(member.target)
            group = RelationGroup(
                native.object_oid,
                rel_name,
                "native-entire-relation",
                "complete" if members else "known_empty",
                members,
                prov,
            )
            _charge(work, "metadata_units", 1)
            core_cap.admit_group(group)

        return tuple(discovered_targets)

    def _run_notes_spec(
        self,
        core_cap: GitCore,
        spec: NotesAcquisitionSpec,
        *,
        repository_uuidv4: str,
        source_attribution: str,
        origin_uuidv4: str,
        observed_at_us: int | None,
        notes_source: NotesSource | None,
        work: WorkBudget,
        progress: Any,
    ) -> tuple[
        tuple[Discovery, ...],
        tuple[RefNoteAcquisition, ...],
        tuple[RefNotesInventory, ...],
        list[OID],
    ]:
        discoveries: list[Discovery] = []
        ref_note_acquisitions: list[RefNoteAcquisition] = []
        ref_notes_inventories: list[RefNotesInventory] = []
        extra_oids: list[OID] = []

        active_ref_claims = []
        for unit in spec.ref_inputs:
            ref_notes_input_intent(unit, repository_uuidv4, work)
            _charge(work, "metadata_units", 1)
            core_cap.admit_ref_observation(unit.observation)
            for claim in unit.claims:
                _charge(work, "metadata_units", 1)
                core_cap.admit_ref_observation_claim(claim)
                active_ref_claims.append(claim)
                extra_oids.extend(
                    object_oid
                    for object_oid in (
                        claim.direct_target_object_oid,
                        claim.resolved_target_object_oid,
                        claim.peeled_target_object_oid,
                        claim.root_object_oid,
                    )
                    if object_oid is not None
                )
            for mapping_claim in unit.mapping_claims:
                core_cap.admit_notes_mapping(mapping_claim.mapping, work)
                _charge(work, "metadata_units", 1)
                core_cap.admit_notes_mapping_claim(mapping_claim)
                extra_oids.extend(
                    (
                        mapping_claim.mapping.root_object_oid,
                        mapping_claim.mapping.annotated_object_oid,
                        mapping_claim.mapping.note_object_oid,
                    )
                )
            for group in unit.mapping_groups:
                core_cap.admit_notes_mapping_group(group, work)
                extra_oids.append(group.ref_claim.root_object_oid)
                fmt = group.ref_claim.root_object_oid.object_format
                for target, note, _ in group.members:
                    extra_oids.extend((OID(fmt, target), OID(fmt, note)))

        if notes_source is not None and (
            spec.discover_notes or spec.acquire_inventories or spec.target_object_oids
        ):
            notes_app = NotesAcquisition(
                core_cap,
                notes_source,
                work,
                progress,
                source_attribution=source_attribution,
                repository_uuidv4=repository_uuidv4,
            )
            for claim in active_ref_claims:
                if claim.root_object_oid is None:
                    continue
                if spec.acquire_inventories:
                    ref_notes_inventories.append(notes_app.inventory_ref(claim))
                for target in spec.target_object_oids:
                    result = notes_app.acquire_ref_note(
                        claim, target, retain_body=spec.retain_note_bodies
                    )
                    ref_note_acquisitions.append(result)
                    if result.note is not None:
                        extra_oids.append(result.note)
            if spec.discover_notes:
                disc_obs_id = spec.discovery_observation_uuidv4
                if disc_obs_id is None:
                    allocation_scope = encode(
                        ["p5-discovery-allocation", origin_uuidv4, observed_at_us]
                    )
                    saved = progress.load(allocation_scope)
                    if saved is None:
                        saved = progress.save_once(
                            allocation_scope, {"observation_uuidv4": str(uuid4())}
                        )
                    disc_obs_id = saved["observation_uuidv4"]
                disc = notes_app.discover(
                    repository_uuidv4,
                    source_attribution,
                    origin_uuidv4,
                    disc_obs_id,
                    observed_at_us,
                    spec.nominated_refs,
                )
                discoveries.append(disc)
                for enumeration in disc.enumerations:
                    for link in enumeration.links:
                        if link.claim.root_object_oid is None:
                            continue
                        extra_oids.append(link.claim.root_object_oid)
                        if spec.acquire_inventories:
                            ref_notes_inventories.append(
                                notes_app.inventory_ref(link.claim)
                            )
                        for target_object_oid in spec.target_object_oids:
                            result = notes_app.acquire_ref_note(
                                link.claim,
                                target_object_oid,
                                retain_body=spec.retain_note_bodies,
                            )
                            ref_note_acquisitions.append(result)
                            if result.note is not None:
                                extra_oids.append(result.note)

        for inventory in ref_notes_inventories:
            fmt = inventory.group.ref_claim.root_object_oid.object_format
            for target, note, _ in inventory.group.members:
                _charge(work, "metadata_units", 2)
                extra_oids.extend((OID(fmt, target), OID(fmt, note)))
        for result in ref_note_acquisitions:
            if result.note is not None:
                extra_oids.append(result.target)

        return (
            tuple(discoveries),
            tuple(ref_note_acquisitions),
            tuple(ref_notes_inventories),
            extra_oids,
        )

    def acquire_from_native(
        self,
        source: GitNativeSource,
        request: GitNativeAcquisitionRequest,
        *,
        work: WorkBudget | None = None,
        progress: Any | None = None,
        new_request: bool = False,
        request_identity: RequestIdentity | None = None,
    ) -> GitAcquisitionReport:
        """Acquire one explicitly selected repository; the catalog seed is not it.

        Validate all repository-owned claims/observations before any admission. Physical
        Core/Operational identity pairing remains anchored to store_identity.
        """
        preflight_intent = native_request_intent(without_ref_inputs(request))
        with ExitStack() as stack:
            core_cap = stack.enter_context(_open_core(self.core))
            core_cap.ensure_available()
            _catalog_seed, actual_inst = core_cap.catalog_identity()
            notes_scope = None
            if request.notes is not None:
                notes_src = GitNotesSource(source)
                notes_scope = request_scope(
                    request.repository_uuidv4,
                    actual_inst,
                    request.source_attribution,
                    notes_src.scope,
                )
            active_work, active_progress = stack.enter_context(
                self._resolve_budget_and_progress(
                    core_cap,
                    "p5-git-native",
                    request.capture_origin_uuidv4,
                    request.capture_uuidv4,
                    work,
                    progress,
                    custom_scope=notes_scope,
                    repository_uuidv4=request.repository_uuidv4,
                    new_request=new_request,
                    request_identity=request_identity,
                )
            )

            semantic_intent = (
                native_request_intent(request, active_work)
                if request.notes is not None and request.notes.ref_inputs
                else preflight_intent
            )
            _charge(active_work, "metadata_units", 1)
            intent_scope = encode(
                [
                    "p5-native-intent",
                    request.capture_origin_uuidv4,
                    request.capture_uuidv4,
                ]
            )
            intent = {
                "request": semantic_intent,
                "source": [
                    str(source.path),
                    source.object_format,
                    request.source_attribution,
                ],
                "observed_at_us": request.observed_at_us,
                "selected": [
                    list(object_oid.key) for object_oid in request.select_object_oids
                ],
                "retention": [
                    request.retain_bytes,
                    None
                    if request.retain_object_oids is None
                    else sorted(
                        [
                            list(object_oid.key)
                            for object_oid in request.retain_object_oids
                        ]
                    ),
                ],
                "refs": [
                    request.include_refs,
                    list(request.ref_prefixes),
                    [name.hex() for name in request.nominated_ref_names],
                ],
                "traverse_structural_targets": request.traverse_structural_targets,
                "notes": semantic_intent["notes"]
                if request.notes is not None and request.notes.ref_inputs
                else repr(request.notes),
            }
            with ref_input_processing(
                request.notes.ref_inputs if request.notes is not None else (),
                active_work,
            ):
                if active_progress.save_once(intent_scope, intent) != intent:
                    raise CoreFailure(
                        "INCOMPATIBLE_REPLAY", intent_scope, "request intent changed"
                    )
            core_cap.admit_repository(request.repository_uuidv4)

            for repo_claim in request.repository_claims:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_repository_claim(repo_claim)

            admitted_order: list[OID] = []
            retained_order: list[OID] = []
            metadata_only_order: list[OID] = []
            nominal_missing_order: list[OID] = []
            ref_observations: list[GitObservation] = []
            ref_enumerations = []
            failure_code: str | None = None
            failure_detail: str = ""

            def _record_admitted(object_oid: OID) -> None:
                if object_oid not in admitted_order:
                    admitted_order.append(object_oid)

            if request.include_refs:
                configured = tuple(os.fsencode(p) for p in request.ref_prefixes)
                if any(
                    not (p.startswith(b"refs/") or b"refs/".startswith(p))
                    for p in configured
                ):
                    raise CoreFailure(
                        "REF", configured, "ref prefix must cover a full refs namespace"
                    )
                prefixes = tuple(
                    sorted(
                        set(
                            p if p.startswith(b"refs/") else b"refs/"
                            for p in configured
                        )
                    )
                ) or (b"refs/",)
                ref_source = GitNotesSource(source)
                slot = encode(
                    [
                        "p5-ref-enumeration",
                        request.capture_origin_uuidv4,
                        request.capture_uuidv4,
                    ]
                )
                binding = [
                    request.repository_uuidv4,
                    request.source_attribution,
                    ref_source.scope,
                    [p.hex() for p in prefixes],
                    request.observed_at_us,
                ]

                def scan_refs():
                    refs = source.ref_records(active_work)
                    selected = tuple(
                        EnumeratedRef(r.name, r.target, r.symbolic_target, r.peeled)
                        for r in refs
                        if any(r.name.startswith(p) for p in prefixes)
                    )
                    return RefScan(selected, "complete", "git-for-each-ref:exit-0")

                enumeration = pin_scan(
                    core_cap,
                    active_progress,
                    active_work,
                    slot=slot,
                    binding=binding,
                    origin=request.capture_origin_uuidv4,
                    repository=request.repository_uuidv4,
                    source=request.source_attribution,
                    visibility=encode(
                        [ref_source.scope, "git-for-each-ref:resolvable"]
                    ),
                    prefixes=prefixes,
                    nominated=(),
                    observed_at_us=request.observed_at_us,
                    byte_limit=ref_source.discovery_bytes,
                    ref_limit=ref_source.discovery_refs,
                    scan=scan_refs,
                )
                ref_enumerations.append(enumeration)
                selected_refs = [
                    (
                        link.observation.ref_name_bytes.decode(
                            "utf-8", "surrogateescape"
                        ),
                        link.claim.root_object_oid,
                        "",
                        link.claim.peeled_target_object_oid,
                    )
                    for link in enumeration.links
                ]

                _charge(active_work, "metadata_units", 1 + len(selected_refs))
                for (
                    _ref_name,
                    target_object_oid,
                    _kind,
                    peeled_object_oid,
                ) in selected_refs:
                    core_cap.admit_object(target_object_oid)
                    _record_admitted(target_object_oid)
                    if peeled_object_oid is not None:
                        core_cap.admit_object(peeled_object_oid)
                        _record_admitted(peeled_object_oid)

                obs_prov = Provenance(
                    request.source_attribution,
                    encode([request.capture_origin_uuidv4, request.capture_uuidv4]),
                    "local-ref-snapshot",
                    DECODER,
                    DECODER_VERSION,
                    "reported",
                )
                ref_obs = GitObservation(
                    request.capture_origin_uuidv4,
                    request.capture_uuidv4,
                    request.repository_uuidv4,
                    "snapshot",
                    (
                        "local-git-refs",
                        request.source_attribution,
                        tuple(sorted(set(request.ref_prefixes))),
                    ),
                    {
                        "roots": [list(t.key) for _, t, _, _ in selected_refs],
                        "predecessor": None,
                        "observed_at_us": request.observed_at_us,
                        "source": request.source_attribution,
                        "refs": [
                            {"ref": name, "target": list(t.key)}
                            for name, t, _, _ in selected_refs
                        ],
                        "enumeration_state": (
                            "complete" if selected_refs else "known_empty"
                        ),
                        "terminal_observation": True,
                    },
                    obs_prov,
                )
                core_cap.admit_observation(ref_obs)
                ref_observations.append(ref_obs)

            if request.nominated_ref_names:
                named_source = GitNotesSource(source)
                for name in sorted(set(request.nominated_ref_names)):
                    slot = encode(
                        [
                            "p5-ref-lookup",
                            request.capture_origin_uuidv4,
                            request.capture_uuidv4,
                            name.hex(),
                        ]
                    )

                    def lookup(name=name):
                        present = source.lookup_ref_presence(name, active_work)
                        return RefScan(
                            (
                                EnumeratedRef(
                                    name,
                                    None,
                                    absent=not present,
                                    form_known=False,
                                    absence_method="lookup",
                                ),
                            ),
                            "complete",
                            "git-show-ref-exists:" + ("0" if present else "2"),
                        )

                    try:
                        result = pin_scan(
                            core_cap,
                            active_progress,
                            active_work,
                            slot=slot,
                            binding=[semantic_intent, named_source.scope, name.hex()],
                            origin=request.capture_origin_uuidv4,
                            repository=request.repository_uuidv4,
                            source=request.source_attribution,
                            visibility=encode(
                                [named_source.scope, "git-show-ref-exists"]
                            ),
                            prefixes=(),
                            nominated=(name,),
                            observed_at_us=request.observed_at_us,
                            byte_limit=named_source.discovery_bytes,
                            ref_limit=named_source.discovery_refs,
                            scan=lookup,
                        )
                        ref_enumerations.append(result)
                    except CoreFailure as error:
                        if error.code in ("AUTHORITATIVE_CORRUPTION", "RECOVERY_STOP"):
                            raise
                        failure_code, failure_detail = error.code, str(error)
                        break

            for missing_oid in request.nominal_missing_object_oids:
                if missing_oid.object_format != source.object_format:
                    raise CoreFailure(
                        "NATIVE_FORMAT",
                        missing_oid,
                        "nominal OID format differs from source format",
                    )
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_object(missing_oid)
                _record_admitted(missing_oid)
                if missing_oid not in nominal_missing_order:
                    nominal_missing_order.append(missing_oid)
                if missing_oid not in metadata_only_order:
                    metadata_only_order.append(missing_oid)

            for object_oid in request.select_object_oids:
                should_retain = (
                    object_oid in request.retain_object_oids
                    if request.retain_object_oids is not None
                    else request.retain_bytes
                )
                copy_id = None
                if should_retain:
                    copy_id = request.physical_copy_uuidv4s.get(object_oid)
                    if copy_id is None:
                        key = encode(
                            [
                                "p5-native-copy",
                                request.capture_origin_uuidv4,
                                request.capture_uuidv4,
                                *object_oid.key,
                            ]
                        )
                        saved = active_progress.load(key)
                        if saved is None:
                            saved = active_progress.save_once(
                                key, {"copy": str(uuid4())}
                            )
                        copy_id = saved["copy"]
                try:
                    native = source.metadata(object_oid, active_work)
                except CoreFailure as err:
                    if err.code == "OBJECT_UNAVAILABLE":
                        _charge(active_work, "metadata_units", 1)
                        core_cap.admit_object(object_oid)
                        _record_admitted(object_oid)
                        if object_oid not in nominal_missing_order:
                            nominal_missing_order.append(object_oid)
                        if object_oid not in metadata_only_order:
                            metadata_only_order.append(object_oid)
                        failure_code = err.code
                        failure_detail = str(err)
                        continue
                    raise

                if should_retain:
                    core_cap.admit_metadata(native, copy_id, active_work)
                    _record_admitted(object_oid)
                    if object_oid not in retained_order:
                        retained_order.append(object_oid)
                    if request.traverse_structural_targets:
                        with account_verification(active_work):
                            parsed = parse_metadata(
                                object_oid.object_format,
                                native.native_type,
                                native.body,
                            )
                        for raw_members in parsed.relations.values():
                            for m in raw_members:
                                target_object_oid = OID(m[1], m[2])
                                _record_admitted(target_object_oid)
                                if (
                                    target_object_oid not in retained_order
                                    and target_object_oid not in metadata_only_order
                                ):
                                    metadata_only_order.append(target_object_oid)
                else:
                    targets = self._admit_metadata_claims_only(
                        core_cap,
                        native,
                        request.source_attribution,
                        request.capture_origin_uuidv4,
                        request.capture_uuidv4,
                        active_work,
                    )
                    _record_admitted(object_oid)
                    if object_oid not in metadata_only_order:
                        metadata_only_order.append(object_oid)
                    if request.traverse_structural_targets:
                        for target_object_oid in targets:
                            _record_admitted(target_object_oid)
                            if (
                                target_object_oid not in retained_order
                                and target_object_oid not in metadata_only_order
                            ):
                                metadata_only_order.append(target_object_oid)

            for claim in request.extra_scalar_claims:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_claim(claim)
                _record_admitted(claim.subject)
                if (
                    claim.subject not in retained_order
                    and claim.subject not in metadata_only_order
                ):
                    metadata_only_order.append(claim.subject)

            for group in request.extra_relation_groups:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_group(group)
                _record_admitted(group.subject)
                if (
                    group.subject not in retained_order
                    and group.subject not in metadata_only_order
                ):
                    metadata_only_order.append(group.subject)
                for member in group.members:
                    _record_admitted(member.target)
                    if (
                        member.target not in retained_order
                        and member.target not in metadata_only_order
                    ):
                        metadata_only_order.append(member.target)

            notes_discoveries: tuple[Discovery, ...] = ()
            ref_note_acquisitions: tuple[RefNoteAcquisition, ...] = ()
            ref_notes_inventories: tuple[RefNotesInventory, ...] = ()
            notes_src = None
            if request.notes is not None:
                notes_src = GitNotesSource(source)
                (
                    notes_discoveries,
                    ref_note_acquisitions,
                    ref_notes_inventories,
                    notes_oids,
                ) = self._run_notes_spec(
                    core_cap,
                    request.notes,
                    repository_uuidv4=request.repository_uuidv4,
                    source_attribution=request.source_attribution,
                    origin_uuidv4=request.capture_origin_uuidv4,
                    observed_at_us=request.observed_at_us,
                    notes_source=notes_src,
                    work=active_work,
                    progress=active_progress,
                )
                for n_oid in notes_oids:
                    _record_admitted(n_oid)
                for na in (
                    *ref_note_acquisitions,
                    *ref_notes_inventories,
                ):
                    if na.failure_code is not None and failure_code is None:
                        failure_code = na.failure_code
                        failure_detail = na.detail

            # Clean metadata_only_order so any OID that was also retained is only in retained_order
            metadata_only_final = tuple(
                object_oid
                for object_oid in metadata_only_order
                if object_oid not in retained_order
            )

            non_missing_admitted = [
                object_oid
                for object_oid in admitted_order
                if object_oid not in nominal_missing_order
            ]
            if nominal_missing_order or failure_code is not None:
                status = "partial" if non_missing_admitted else "unknown"
                cov_state = "partial" if non_missing_admitted else "unknown"
            else:
                status = "complete" if admitted_order else "known_empty"
                # Selected objects do not prove repository-wide metadata closure.
                cov_state = "partial" if admitted_order else "unknown"

            for discovery in notes_discoveries:
                if discovery.failure_code is not None or discovery.observation.value[
                    "enumeration_state"
                ] in (
                    "partial",
                    "unknown",
                ):
                    status = "partial" if admitted_order else "unknown"
                    failure_code = (
                        failure_code or discovery.failure_code or "NOTES_INCOMPLETE"
                    )
                    failure_detail = failure_detail or discovery.detail
            cov_scope = CoreCoverageScope(
                "repository", (request.repository_uuidv4, "git_metadata")
            )
            cov_claim = CoverageClaim(
                cov_scope,
                request.observed_at_us,
                cov_state,
                encode(
                    {
                        "capture_origin_uuidv4": request.capture_origin_uuidv4,
                        "capture_uuidv4": request.capture_uuidv4,
                        "retained_count": len(retained_order),
                        "metadata_only_count": len(metadata_only_final),
                        "nominal_missing_count": len(nominal_missing_order),
                    }
                ),
            )
            _charge(active_work, "metadata_units", 1)
            core_cap.admit_coverage_scope(cov_scope)
            core_cap.admit_coverage(cov_claim)
            if cov_state == "complete":
                cov_prov = Provenance(
                    request.source_attribution,
                    encode([request.capture_origin_uuidv4, request.capture_uuidv4]),
                    "git-metadata-coverage",
                    DECODER,
                    DECODER_VERSION,
                    "reported",
                )
                core_cap.admit_coverage_proof(
                    cov_claim, tuple(admitted_order), cov_prov
                )

            report = GitAcquisitionReport(
                repository_uuidv4=request.repository_uuidv4,
                capture_origin_uuidv4=request.capture_origin_uuidv4,
                capture_uuidv4=request.capture_uuidv4,
                object_format=source.object_format,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                admitted_objects=tuple(admitted_order),
                retained_objects=tuple(retained_order),
                metadata_only_objects=metadata_only_final,
                nominal_missing_objects=tuple(nominal_missing_order),
                ref_observations=tuple(ref_observations),
                ref_enumerations=tuple(ref_enumerations),
                notes_discoveries=notes_discoveries,
                ref_note_acquisitions=ref_note_acquisitions,
                ref_notes_inventories=ref_notes_inventories,
                coverage_claims=(cov_claim,),
                failure_code=failure_code,
                failure_detail=failure_detail,
            )
            return _finish_ref_inventories(
                _defer_ref_work(report, request.notes, notes_src),
                core_cap,
                notes_src,
                active_work,
                active_progress,
                request.source_attribution,
            )

    def acquire_metadata_only(
        self,
        unit: GitMetadataInput,
        *,
        work: WorkBudget | None = None,
        progress: Any | None = None,
        notes_source: NotesSource | None = None,
        new_request: bool = False,
        request_identity: RequestIdentity | None = None,
    ) -> GitAcquisitionReport:
        """Admit a GitMetadataInput unit (with optional retained NativeObjects and Notes)."""
        preflight_intent = metadata_input_intent(without_ref_inputs(unit))
        with ExitStack() as stack:
            core_cap = stack.enter_context(_open_core(self.core))
            core_cap.ensure_available()
            notes_scope = None
            if unit.notes is not None and notes_source is not None:
                notes_scope = request_scope(
                    unit.repository_uuidv4,
                    core_cap.catalog_identity()[1],
                    unit.source_attribution,
                    notes_source.scope,
                )
            active_work, active_progress = stack.enter_context(
                self._resolve_budget_and_progress(
                    core_cap,
                    "p5-git-metadata-input",
                    unit.capture_origin_uuidv4,
                    unit.capture_uuidv4,
                    work,
                    progress,
                    custom_scope=notes_scope,
                    repository_uuidv4=unit.repository_uuidv4,
                    new_request=new_request,
                    request_identity=request_identity,
                )
            )

            semantic_intent = (
                metadata_input_intent(unit, active_work)
                if unit.notes is not None and unit.notes.ref_inputs
                else preflight_intent
            )
            semantic_intent["notes_source"] = (
                None
                if notes_source is None
                else [notes_source.scope, notes_source.object_format]
            )
            _charge(active_work, "metadata_units", 1)
            intent_scope = encode(
                ["p5-metadata-intent", unit.capture_origin_uuidv4, unit.capture_uuidv4]
            )
            with ref_input_processing(
                unit.notes.ref_inputs if unit.notes is not None else (), active_work
            ):
                if (
                    active_progress.save_once(intent_scope, semantic_intent)
                    != semantic_intent
                ):
                    raise CoreFailure(
                        "INCOMPATIBLE_REPLAY", "metadata", "request intent changed"
                    )
            core_cap.admit_repository(unit.repository_uuidv4)

            admitted_order: list[OID] = []
            retained_order: list[OID] = []
            metadata_only_order: list[OID] = []

            def _record_admitted(object_oid: OID) -> None:
                if object_oid not in admitted_order:
                    admitted_order.append(object_oid)

            for repo_claim in unit.repository_claims:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_repository_claim(repo_claim)

            for obs in unit.observations:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_observation(obs)

            for nom_oid in unit.nominal_objects:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_object(nom_oid)
                _record_admitted(nom_oid)
                if nom_oid not in metadata_only_order:
                    metadata_only_order.append(nom_oid)

            for native in unit.native_objects:
                copy_id = unit.physical_copy_uuidv4s.get(native.object_oid)
                if copy_id is None:
                    key = encode(
                        [
                            "p5-native-copy",
                            unit.capture_origin_uuidv4,
                            unit.capture_uuidv4,
                            *native.object_oid.key,
                        ]
                    )
                    saved = active_progress.load(key)
                    if saved is None:
                        saved = active_progress.save_once(key, {"copy": str(uuid4())})
                    copy_id = saved["copy"]
                core_cap.admit_metadata(native, copy_id, active_work)
                _record_admitted(native.object_oid)
                if native.object_oid not in retained_order:
                    retained_order.append(native.object_oid)
                with account_verification(active_work):
                    parsed = parse_metadata(
                        native.object_oid.object_format, native.native_type, native.body
                    )
                for raw_members in parsed.relations.values():
                    for m in raw_members:
                        target_object_oid = OID(m[1], m[2])
                        _record_admitted(target_object_oid)
                        if (
                            target_object_oid not in retained_order
                            and target_object_oid not in metadata_only_order
                        ):
                            metadata_only_order.append(target_object_oid)

            for s_claim in unit.scalar_claims:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_claim(s_claim)
                _record_admitted(s_claim.subject)
                if (
                    s_claim.subject not in retained_order
                    and s_claim.subject not in metadata_only_order
                ):
                    metadata_only_order.append(s_claim.subject)

            for r_group in unit.relation_groups:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_group(r_group)
                _record_admitted(r_group.subject)
                if (
                    r_group.subject not in retained_order
                    and r_group.subject not in metadata_only_order
                ):
                    metadata_only_order.append(r_group.subject)
                for member in r_group.members:
                    _record_admitted(member.target)
                    if (
                        member.target not in retained_order
                        and member.target not in metadata_only_order
                    ):
                        metadata_only_order.append(member.target)

            notes_discoveries: tuple[Discovery, ...] = ()
            ref_note_acquisitions: tuple[RefNoteAcquisition, ...] = ()
            ref_notes_inventories: tuple[RefNotesInventory, ...] = ()
            if unit.notes is not None:
                (
                    notes_discoveries,
                    ref_note_acquisitions,
                    ref_notes_inventories,
                    notes_oids,
                ) = self._run_notes_spec(
                    core_cap,
                    unit.notes,
                    repository_uuidv4=unit.repository_uuidv4,
                    source_attribution=unit.source_attribution,
                    origin_uuidv4=unit.capture_origin_uuidv4,
                    observed_at_us=unit.observed_at_us,
                    notes_source=notes_source,
                    work=active_work,
                    progress=active_progress,
                )
                for n_oid in notes_oids:
                    _record_admitted(n_oid)
                    if n_oid not in retained_order and n_oid not in metadata_only_order:
                        metadata_only_order.append(n_oid)

            admitted_cov_claims: list[CoverageClaim] = []
            for scope in unit.coverage_scopes:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_coverage_scope(scope)

            for c_claim in unit.coverage_claims:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_coverage_scope(c_claim.scope)
                core_cap.admit_coverage(c_claim)
                admitted_cov_claims.append(c_claim)

            for p_claim, p_members, p_prov in unit.coverage_proofs:
                _charge(active_work, "metadata_units", 1)
                core_cap.admit_coverage_scope(p_claim.scope)
                core_cap.admit_coverage(p_claim)
                core_cap.admit_coverage_proof(p_claim, p_members, p_prov)
                if p_claim not in admitted_cov_claims:
                    admitted_cov_claims.append(p_claim)

            metadata_only_final = tuple(
                object_oid
                for object_oid in metadata_only_order
                if object_oid not in retained_order
            )
            status = "complete" if admitted_order else "known_empty"
            note_failure = next(
                (
                    item
                    for item in (
                        *ref_note_acquisitions,
                        *ref_notes_inventories,
                    )
                    if item.failure_code
                ),
                None,
            )
            discovery_failure = next(
                (item for item in notes_discoveries if item.failure_code), None
            )
            if note_failure or discovery_failure:
                status = "partial" if admitted_order else "unknown"

            report = GitAcquisitionReport(
                repository_uuidv4=unit.repository_uuidv4,
                capture_origin_uuidv4=unit.capture_origin_uuidv4,
                capture_uuidv4=unit.capture_uuidv4,
                object_format=unit.object_format,
                status=status,  # type: ignore[arg-type]
                admitted_objects=tuple(admitted_order),
                retained_objects=tuple(retained_order),
                metadata_only_objects=metadata_only_final,
                nominal_missing_objects=(),
                ref_observations=unit.observations,
                notes_discoveries=notes_discoveries,
                ref_note_acquisitions=ref_note_acquisitions,
                ref_notes_inventories=ref_notes_inventories,
                coverage_claims=tuple(admitted_cov_claims),
                failure_code=(note_failure or discovery_failure).failure_code
                if note_failure or discovery_failure
                else None,
                failure_detail=(note_failure or discovery_failure).detail
                if note_failure or discovery_failure
                else "",
            )
            return _finish_ref_inventories(
                _defer_ref_work(report, unit.notes, notes_source),
                core_cap,
                notes_source,
                active_work,
                active_progress,
                unit.source_attribution,
            )


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
