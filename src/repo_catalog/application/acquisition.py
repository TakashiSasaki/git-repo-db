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
from repo_catalog.application.notes import Discovery, NoteAcquisition, NotesAcquisition
from repo_catalog.domain.acquisition import (
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
from repo_catalog.domain.notes import NotesInventory
from repo_catalog.domain.p1_context import FieldClock, ResourceKey
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
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
            "admit_metadata",
            "admit_capture",
            "admit_notes_claim",
            "admit_notes_group",
            "admit_notes_inventory",
            "admit_notes_role",
            "admit_note",
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
                    else [scope_tag, origin_uuidv4, unit_uuidv4]
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
                native.oid.object_format, native.native_type, native.body
            )
            _charge(work, "metadata_units", 1)

        evidence_coord = encode([origin_uuidv4, capture_uuidv4, *native.oid.key])
        core_cap.admit_object(native.oid)
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
            claim = ScalarClaim(native.oid, field_name, val, prov)
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
                native.oid,
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
        tuple[NotesInventory, ...],
        tuple[NoteAcquisition, ...],
        list[OID],
    ]:
        discoveries: list[Discovery] = []
        inventories: list[NotesInventory] = []
        note_acquisitions: list[NoteAcquisition] = []
        extra_oids: list[OID] = []

        active_captures: list[Capture] = list(spec.explicit_captures)
        for cap in spec.explicit_captures:
            _charge(work, "metadata_units", 1)
            core_cap.admit_capture(cap)
            extra_oids.append(cap.root)

        for n_claim in spec.external_claims:
            _charge(work, "metadata_units", 1)
            core_cap.admit_notes_claim(n_claim)
            extra_oids.extend([n_claim.capture.root, n_claim.target, n_claim.note])

        for n_group in spec.external_groups:
            _charge(work, "metadata_units", 1)
            core_cap.admit_notes_group(n_group)
            extra_oids.append(n_group.capture.root)
            fmt = n_group.capture.root.object_format
            for target_hex, note_hex, _path in n_group.members:
                extra_oids.append(OID(fmt, target_hex))
                extra_oids.append(OID(fmt, note_hex))

        if notes_source is not None and (
            spec.discover_notes or spec.acquire_inventories or spec.target_oids
        ):
            notes_app = NotesAcquisition(
                core_cap,
                notes_source,
                work,
                progress,
                source_attribution=source_attribution,
            )
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
                for cap in disc.captures:
                    if cap not in active_captures:
                        active_captures.append(cap)
                    extra_oids.append(cap.root)

            if spec.acquire_inventories:
                for cap in active_captures:
                    inv = notes_app.inventory(cap)
                    inventories.append(inv)
                    fmt = cap.root.object_format
                    for target_hex, note_hex, _path in inv.members:
                        extra_oids.append(OID(fmt, target_hex))
                        extra_oids.append(OID(fmt, note_hex))

            for cap in active_captures:
                for target_oid in spec.target_oids:
                    na = notes_app.acquire_note(
                        cap,
                        target_oid,
                        retain_body=spec.retain_note_bodies,
                    )
                    note_acquisitions.append(na)
                    extra_oids.append(target_oid)
                    if na.note is not None:
                        extra_oids.append(na.note)

        return (
            tuple(discoveries),
            tuple(inventories),
            tuple(note_acquisitions),
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
        """Execute selective metadata-first acquisition against a local GitNativeSource."""
        with ExitStack() as stack:
            core_cap = stack.enter_context(_open_core(self.core))
            core_cap.ensure_available()
            actual_repo, actual_inst = core_cap.catalog_identity()
            if request.repository_uuidv4 != actual_repo:
                raise CoreFailure(
                    "REPOSITORY_SCOPE",
                    request.repository_uuidv4,
                    "request repository_uuidv4 does not match Core store_identity",
                )
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
                    new_request=new_request,
                    request_identity=request_identity,
                )
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
                "source": [
                    str(source.path),
                    source.object_format,
                    request.source_attribution,
                ],
                "observed_at_us": request.observed_at_us,
                "selected": [list(oid.key) for oid in request.select_oids],
                "retention": [
                    request.retain_bytes,
                    None
                    if request.retain_oids is None
                    else sorted([list(oid.key) for oid in request.retain_oids]),
                ],
                "refs": [request.include_refs, list(request.ref_prefixes)],
                "traverse_structural_targets": request.traverse_structural_targets,
                "notes": repr(request.notes),
            }
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

            def _record_admitted(oid: OID) -> None:
                if oid not in admitted_order:
                    admitted_order.append(oid)

            if request.include_refs:
                _charge(active_work, "metadata_units", 1)
                all_refs = source.refs(active_work)
                selected_refs = []
                for ref_bytes, target_oid, kind, peeled_oid in all_refs:
                    ref_name = ref_bytes.decode("utf-8", "surrogateescape")
                    if request.ref_prefixes and not any(
                        ref_name.startswith(prefix) for prefix in request.ref_prefixes
                    ):
                        continue
                    selected_refs.append((ref_name, target_oid, kind, peeled_oid))

                _charge(active_work, "metadata_units", 1 + len(selected_refs))
                for _ref_name, target_oid, _kind, peeled_oid in selected_refs:
                    core_cap.admit_object(target_oid)
                    _record_admitted(target_oid)
                    if peeled_oid is not None:
                        core_cap.admit_object(peeled_oid)
                        _record_admitted(peeled_oid)

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

            failure_code: str | None = None
            failure_detail: str = ""

            for missing_oid in request.nominal_missing_oids:
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

            for oid in request.select_oids:
                should_retain = (
                    oid in request.retain_oids
                    if request.retain_oids is not None
                    else request.retain_bytes
                )
                copy_id = None
                if should_retain:
                    copy_id = request.physical_copy_uuidv4s.get(oid)
                    if copy_id is None:
                        key = encode(
                            [
                                "p5-native-copy",
                                request.capture_origin_uuidv4,
                                request.capture_uuidv4,
                                *oid.key,
                            ]
                        )
                        saved = active_progress.load(key)
                        if saved is None:
                            saved = active_progress.save_once(
                                key, {"copy": str(uuid4())}
                            )
                        copy_id = saved["copy"]
                try:
                    native = source.metadata(oid, active_work)
                except CoreFailure as err:
                    if err.code == "OBJECT_UNAVAILABLE":
                        _charge(active_work, "metadata_units", 1)
                        core_cap.admit_object(oid)
                        _record_admitted(oid)
                        if oid not in nominal_missing_order:
                            nominal_missing_order.append(oid)
                        if oid not in metadata_only_order:
                            metadata_only_order.append(oid)
                        failure_code = err.code
                        failure_detail = str(err)
                        continue
                    raise

                if should_retain:
                    core_cap.admit_metadata(native, copy_id, active_work)
                    _record_admitted(oid)
                    if oid not in retained_order:
                        retained_order.append(oid)
                    if request.traverse_structural_targets:
                        with account_verification(active_work):
                            parsed = parse_metadata(
                                oid.object_format, native.native_type, native.body
                            )
                        for raw_members in parsed.relations.values():
                            for m in raw_members:
                                target_oid = OID(m[1], m[2])
                                _record_admitted(target_oid)
                                if (
                                    target_oid not in retained_order
                                    and target_oid not in metadata_only_order
                                ):
                                    metadata_only_order.append(target_oid)
                else:
                    targets = self._admit_metadata_claims_only(
                        core_cap,
                        native,
                        request.source_attribution,
                        request.capture_origin_uuidv4,
                        request.capture_uuidv4,
                        active_work,
                    )
                    _record_admitted(oid)
                    if oid not in metadata_only_order:
                        metadata_only_order.append(oid)
                    if request.traverse_structural_targets:
                        for target_oid in targets:
                            _record_admitted(target_oid)
                            if (
                                target_oid not in retained_order
                                and target_oid not in metadata_only_order
                            ):
                                metadata_only_order.append(target_oid)

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
            notes_inventories: tuple[NotesInventory, ...] = ()
            note_acquisitions: tuple[NoteAcquisition, ...] = ()
            if request.notes is not None:
                notes_src = GitNotesSource(source)
                (
                    notes_discoveries,
                    notes_inventories,
                    note_acquisitions,
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
                for na in note_acquisitions:
                    if na.failure_code is not None and failure_code is None:
                        failure_code = na.failure_code
                        failure_detail = na.detail

            # Clean metadata_only_order so any OID that was also retained is only in retained_order
            metadata_only_final = tuple(
                oid for oid in metadata_only_order if oid not in retained_order
            )

            non_missing_admitted = [
                oid for oid in admitted_order if oid not in nominal_missing_order
            ]
            if nominal_missing_order or failure_code is not None:
                status = "partial" if non_missing_admitted else "unknown"
                cov_state = "partial" if non_missing_admitted else "unknown"
            else:
                status = "complete" if admitted_order else "known_empty"
                # Selected objects do not prove repository-wide metadata closure.
                cov_state = "partial" if admitted_order else "unknown"

            for discovery in notes_discoveries:
                if discovery.observation.value["enumeration_state"] in (
                    "partial",
                    "unknown",
                ):
                    status = "partial" if admitted_order else "unknown"
                    failure_code = failure_code or "NOTES_INCOMPLETE"
            for inventory in notes_inventories:
                if inventory.status in ("partial", "unknown"):
                    status = "partial" if admitted_order else "unknown"
                    failure_code = failure_code or "NOTES_INCOMPLETE"

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

            return GitAcquisitionReport(
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
                notes_discoveries=notes_discoveries,
                notes_inventories=notes_inventories,
                note_acquisitions=note_acquisitions,
                coverage_claims=(cov_claim,),
                failure_code=failure_code,
                failure_detail=failure_detail,
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
        with ExitStack() as stack:
            core_cap = stack.enter_context(_open_core(self.core))
            core_cap.ensure_available()
            actual_repo, _ = core_cap.catalog_identity()
            if unit.repository_uuidv4 != actual_repo:
                raise CoreFailure(
                    "REPOSITORY_SCOPE",
                    unit.repository_uuidv4,
                    "unit repository_uuidv4 does not match Core store_identity",
                )
            active_work, active_progress = stack.enter_context(
                self._resolve_budget_and_progress(
                    core_cap,
                    "p5-git-metadata-input",
                    unit.capture_origin_uuidv4,
                    unit.capture_uuidv4,
                    work,
                    progress,
                    new_request=new_request,
                    request_identity=request_identity,
                )
            )

            _charge(active_work, "metadata_units", 1)
            core_cap.admit_repository(unit.repository_uuidv4)

            admitted_order: list[OID] = []
            retained_order: list[OID] = []
            metadata_only_order: list[OID] = []

            def _record_admitted(oid: OID) -> None:
                if oid not in admitted_order:
                    admitted_order.append(oid)

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
                copy_id = unit.physical_copy_uuidv4s.get(native.oid)
                if copy_id is None:
                    key = encode(
                        [
                            "p5-native-copy",
                            unit.capture_origin_uuidv4,
                            unit.capture_uuidv4,
                            *native.oid.key,
                        ]
                    )
                    saved = active_progress.load(key)
                    if saved is None:
                        saved = active_progress.save_once(key, {"copy": str(uuid4())})
                    copy_id = saved["copy"]
                core_cap.admit_metadata(native, copy_id, active_work)
                _record_admitted(native.oid)
                if native.oid not in retained_order:
                    retained_order.append(native.oid)
                with account_verification(active_work):
                    parsed = parse_metadata(
                        native.oid.object_format, native.native_type, native.body
                    )
                for raw_members in parsed.relations.values():
                    for m in raw_members:
                        target_oid = OID(m[1], m[2])
                        _record_admitted(target_oid)
                        if (
                            target_oid not in retained_order
                            and target_oid not in metadata_only_order
                        ):
                            metadata_only_order.append(target_oid)

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
            notes_inventories: tuple[NotesInventory, ...] = ()
            note_acquisitions: tuple[NoteAcquisition, ...] = ()
            if unit.notes is not None:
                (
                    notes_discoveries,
                    notes_inventories,
                    note_acquisitions,
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
                oid for oid in metadata_only_order if oid not in retained_order
            )
            status = "complete" if admitted_order else "known_empty"

            return GitAcquisitionReport(
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
                notes_inventories=notes_inventories,
                note_acquisitions=note_acquisitions,
                coverage_claims=tuple(admitted_cov_claims),
            )


class ProviderAcquisition:
    """Normalized Provider intake into P3 Context (standalone or paired)."""

    def __init__(
        self,
        context: Context | Path | str,
        *,
        core: GitCore | Path | str | None = None,
        operational: OperationalAcquisitionLedger | Path | str | None = None,
    ) -> None:
        self.context = context
        self.core = core
        self.operational = operational

    @contextmanager
    def _open_context(self, override: Context | None = None) -> Iterator[Context]:
        target = override if override is not None else self.context
        if isinstance(target, Context):
            yield target
            return
        path = Path(target)
        directory = path if path.is_dir() else path.parent
        with Context.transaction(directory) as ctx:
            yield ctx

    def _make_core_validator(
        self,
        ctx: Context,
        core_override: GitCore | None = None,
    ) -> Callable[[str, str], bool]:
        target_core = core_override if core_override is not None else self.core
        if isinstance(target_core, GitCore):
            return lambda fmt, oid: bool(
                target_core.sql(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                    (fmt, oid),
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

        def _validate(fmt: str, oid: str) -> bool:
            with closing(connect(core_path, "core")) as db:
                row = db.execute(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                    (fmt, oid),
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
        ctx.resource(core_ref.resource)
        if validate_core(core_ref.oid.object_format, core_ref.oid.full_oid):
            ctx.link_core(
                core_ref.resource,
                core_ref.role,
                core_ref.oid.object_format,
                core_ref.oid.full_oid,
                core_ref.provenance_json,
                validate_core,
            )
            if core_ref not in linked_list:
                linked_list.append(core_ref)
        else:
            ctx.report_core_reference(
                core_ref,
                clock=clock,
                observed_at_us=observed_at_us,
            )
            if core_ref not in pending_list:
                pending_list.append(core_ref)

    def _ensure_resource_hierarchy(
        self,
        ctx: Context,
        key: ResourceKey,
        repo_uuid: str | None,
        admitted: list[ResourceKey],
    ) -> None:
        if key.resource_kind in {"review", "comment", "thread", "document"}:
            try:
                parent_tuple = tuple(json.loads(key.provider_resource_id))
                if len(parent_tuple) == 4:
                    parent_key = ResourceKey(
                        key.service_instance_uuidv4,
                        parent_tuple[0],
                        parent_tuple[1],
                    )
                    self._ensure_resource_hierarchy(
                        ctx, parent_key, repo_uuid, admitted
                    )
                    ctx.resource(parent_key, repo_uuid)
                    if parent_key not in admitted:
                        admitted.append(parent_key)
            except Exception:
                pass
        ctx.resource(key, repo_uuid)
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
        if unit.repository_uuidv4 is not None:
            self._ensure_repository_row(ctx, unit.repository_uuidv4)
        self._ensure_resource_hierarchy(
            ctx, unit.primary_resource, unit.repository_uuidv4, admitted_resources
        )
        if unit.repository_uuidv4 is not None:
            ctx.admit_repository(
                unit.primary_resource,
                unit.repository_uuidv4,
                unit.clock,
                unit.provenance_json,
                unit.observed_at_us,
            )
        for obs in unit.observations:
            self._ensure_resource_hierarchy(
                ctx, obs.resource, unit.repository_uuidv4, admitted_resources
            )
            ctx.observe(obs)
        for extra_text in unit.extra_texts:
            digest = ctx.text(extra_text)
            if digest not in admitted_texts:
                admitted_texts.append(digest)
        for res_key, text_val, clock, prov, obs_us in unit.text_admissions:
            self._ensure_resource_hierarchy(
                ctx, res_key, unit.repository_uuidv4, admitted_resources
            )
            if text_val is not None:
                digest = ctx.text(text_val)
                if digest not in admitted_texts:
                    admitted_texts.append(digest)
            ctx.admit_text(res_key, text_val, clock, prov, obs_us)
        for rel in unit.relations:
            ctx.relation(rel)
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

    def admit_unit(
        self,
        unit: NormalizedContextUnit,
        *,
        context: Context | None = None,
        core: GitCore | None = None,
    ) -> None:
        """Admit a single NormalizedContextUnit into Context."""
        with self._open_context(context) as ctx:
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
        with self._open_context(context) as ctx:
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
        with self._open_context(context) as ctx:
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
                        repo.repository_uuidv4,
                        repo.raw_metadata,
                        obs_us,
                        prov_json,
                        clock_domain=repo.clock_domain,
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
                    repository_uuidv4=issue_in.repository_uuidv4,
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
                    repository_uuidv4=pr_in.repository_uuidv4,
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

            for tl_in in batch.timeline_events:
                unit = normalize_timeline_event(
                    batch.service_instance_uuidv4,
                    tl_in.parent_kind,
                    tl_in.parent_id,
                    tl_in.event_id,
                    tl_in.payload,
                    tl_in.observed_at_us,
                    tl_in.provenance_json,
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
                if transfer.target_repository_uuidv4 is not None:
                    self._ensure_repository_row(ctx, transfer.target_repository_uuidv4)
                ctx.resource(transfer.resource)
                if transfer.resource not in admitted_resources:
                    admitted_resources.append(transfer.resource)
                ctx.admit_repository(
                    transfer.resource,
                    transfer.target_repository_uuidv4,
                    transfer.clock,
                    transfer.provenance_json,
                    transfer.observed_at_us,
                )

            for obs in batch.observations:
                ctx.observe(obs)
                if obs.resource not in admitted_resources:
                    admitted_resources.append(obs.resource)

            for rel in batch.relations:
                ctx.resource(rel.resource)
                for member in rel.members:
                    ctx.resource(member)
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
                ctx.resource(coll.resource)
                for member in coll.members:
                    ctx.resource(member)
                ctx.collection(coll)
                admitted_collections += 1

            for cov_claim, coll, req_scope in batch.collection_proofs:
                ctx.resource(coll.resource)
                for member in coll.members:
                    ctx.resource(member)
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
                d.reference.oid.object_format,
                d.reference.oid.full_oid,
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
                ref.oid.object_format,
                ref.oid.full_oid,
                ref.provenance_json,
            )
            if dep.available:
                if key_tuple not in already_required:
                    ctx.link_core(
                        ref.resource,
                        ref.role,
                        ref.oid.object_format,
                        ref.oid.full_oid,
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
    ) -> None:
        self.directory = Path(directory)
        self.coordinator = PairCoordinator(self.directory)
        self.operational = operational if operational is not None else self.directory

    def _core_validator_on_disk(self) -> Callable[[str, str], bool]:
        core_path = self.directory / "core.sqlite3"

        def _validate(fmt: str, oid: str) -> bool:
            if not core_path.is_file():
                return False
            with closing(connect(core_path, "core")) as db:
                row = db.execute(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                    (fmt, oid),
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
            with Context.for_transaction(context_tx, self.directory) as ctx_cap:
                if provider_batch is not None:
                    prov_acq = ProviderAcquisition(
                        ctx_cap,
                        core=self.directory / "core.sqlite3",
                        operational=self.operational,
                    )
                    provider_report_holder[0] = prov_acq.admit_batch(
                        provider_batch, context=ctx_cap
                    )
                elif context_fn is not None:
                    provider_report_holder[0] = context_fn(ctx_cap)

                if reconcile_dependencies:
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

            admission = self.coordinator.admit(
                _prepared_core_unit, _context_unit, cut=cut
            )
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
            with Context.for_transaction(context_tx, self.directory) as ctx_cap:
                report = _reconcile_context_dependencies_in_tx(
                    ctx_cap, self._core_validator_on_disk()
                )
                report_holder.append(report)

        self.coordinator.admit(_core_noop, _context_reconcile)
        return report_holder[0]
