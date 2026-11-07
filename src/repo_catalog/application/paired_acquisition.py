"""Explicit Core-first and Context-second acquisition composition."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack, closing
from pathlib import Path

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import (
    AdmissionTransaction,
    PairCoordinator,
)
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.git_acquisition import (
    GitAcquisition,
    _finish_ref_inventories,
    _open_core,
    _PreparedCore,
)
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.acquisition import (
    DependencyReconciliationReport,
    GitAcquisitionReport,
    GitMetadataInput,
    GitNativeAcquisitionRequest,
    PairedAcquisitionResult,
    ProviderAcquisitionReport,
    ProviderIntakeBatch,
)
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.ports.notes import NotesSource, request_scope
from repo_catalog.domain.production_context import CoreReference


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
