"""P5 Exchange application service (`ExchangeService`) for selective export and validating import.

Enforces:
- Verification-aware export: reads retained bytes, note roles, note bodies, notes inventories,
  and Context text bodies through checked adapter methods so corrupt persisted state stops
  the catalog rather than being exported.
- Untrusted package import: re-verifies every native object, note proof, note inventory,
  and text body digest; rejects ordinary file blobs (`RETENTION_PURPOSE`); never trusts
  sender-claimed `intrinsic` / `receiver_intrinsic` rows without accompanying verified bytes;
  evaluates `core_references` against the receiver's actual `core.sqlite3`; and records
  package receipts only in `operational.sqlite3`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator
from uuid import uuid4

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import (
    AdmissionTransaction,
    PairCoordinator,
    SnapshotReadLimits,
    catalog_completion,
    catalog_gate,
)
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangeImportReport,
    ExchangePackage,
    ExchangeSelectionScope,
    decode_package,
    empty_context_section,
    empty_core_section,
)
from repo_catalog.domain.git_native import DECODER, DECODER_VERSION, parse_metadata
from repo_catalog.domain.p1_coordination import (
    AdmissionFailure,
    CoordinationError,
    RequestIdentity,
)
from repo_catalog.domain.p1_core import (
    OID,
    CoreCoverageScope,
    CoreFailure,
    GitObservation,
    NativeObject,
    Provenance,
    RelationGroup,
    RelationMember,
    RepositoryClaim,
    ScalarClaim,
    _performed,
    account_verification,
    encode,
    intrinsic_members,
    uuid4_value,
    valid_coverage_members,
    valid_group,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ports.p1_core import WorkBudget
from repo_catalog.domain.selective_exchange import (
    CorePreflight,
    bound_sections,
    expand_resources,
    explicit_scope,
    filter_sections,
    preserve_context_coverage,
    terminal_key,
    transfer_reports,
    validate_context,
    validate_context_bindings,
)
from repo_catalog.domain.selective_exchange import (
    disposition as decode_disposition,
)
from repo_catalog.domain.selective_exchange import (
    relation as decode_relation,
)

if TYPE_CHECKING:
    from repo_catalog.adapters.sqlite.production_context import Context


def _recomputed_intrinsic_keys(
    native: NativeObject,
) -> tuple[
    set[tuple[str, str, str, str, str]], set[tuple[str, str, str, str, str, str]]
]:
    """Compute exact (object_format, object_oid, ...) keys that GitCore.admit_metadata generates."""
    claim_keys: set[tuple[str, str, str, str, str]] = set()
    group_keys: set[tuple[str, str, str, str, str, str]] = set()

    for field_name, val in (("type", native.native_type), ("size", len(native.body))):
        prov = Provenance(
            "receiver-intrinsic",
            encode(native.object_oid.key),
            f"native-{field_name}",
            "p1-native",
            "1",
            "receiver_intrinsic",
        )
        claim = ScalarClaim(native.object_oid, field_name, val, prov)
        claim_keys.add(claim.key)

    parsed = parse_metadata(
        native.object_oid.object_format, native.native_type, native.body
    )
    for field_name, val in parsed.scalars.items():
        if field_name in ("type", "size", "tree_count"):
            continue
        prov = Provenance(
            "receiver-intrinsic",
            encode(native.object_oid.key),
            "native-" + field_name,
            DECODER,
            DECODER_VERSION,
            "receiver_intrinsic",
        )
        claim = ScalarClaim(native.object_oid, field_name, val, prov)
        claim_keys.add(claim.key)

    relations = {
        "commit": ("commit_parents", "commit_tree"),
        "tree": ("tree_entries",),
        "tag": ("tag_target",),
    }[native.native_type]
    for rel_name in relations:
        members = intrinsic_members(
            native.object_oid.object_format, native.native_type, native.body, rel_name
        )
        prov = Provenance(
            "receiver-intrinsic",
            encode(native.object_oid.key),
            rel_name,
            "p1-native",
            "1",
            "receiver_intrinsic",
        )
        group = RelationGroup(
            native.object_oid,
            rel_name,
            "native-entire-relation",
            "complete" if members else "known_empty",
            tuple(
                RelationMember(
                    tuple(m[0]) if isinstance(m[0], list) else m[0], OID(m[1], m[2])
                )
                for m in members
            ),
            prov,
        )
        group_keys.add(group.key)

    return claim_keys, group_keys


def _checked_registration(ctx: Context, kind: str, encoded: str) -> str:
    ctx.registration_metadata(kind, encoded)
    return encoded


class _ContextCallbackFailure(Exception):
    """Carry a work-callback failure across the Context storage boundary."""

    def __init__(self, original):
        self.original = original


class _IdentityBudgetRefusal(Exception):
    """The pair identity is known, but Context validation exceeded the budget."""

    def __init__(self, identity):
        self.identity = identity


class _ContextCallbackWork:
    """Do not let Context's storage fault guard classify caller work errors."""

    def __init__(self, work):
        self._work = work

    def __getattr__(self, name):
        return getattr(self._work, name)

    def _call(self, method, *args):
        try:
            return getattr(self._work, method)(*args)
        except BaseException as error:
            raise _ContextCallbackFailure(error) from error

    def require(self, unit, amount=1):
        return self._call("require", unit, amount)

    def charge(self, unit, amount):
        return self._call("charge", unit, amount)

    def abandon(self, unit):
        return self._call("abandon", unit)


class _ReceiveWork:
    """Receiver-owned cumulative processing ceiling over the durable request."""

    def __init__(self, work, limit):
        self._work, self._limit = work, limit
        self._check(0)

    def __getattr__(self, name):
        return getattr(self._work, name)

    def _check(self, amount):
        spent = self._work.ledger.usage(self._work.request)
        if spent["metadata_units"] + spent["proof_steps"] + amount > self._limit:
            raise CoreFailure(
                "BUDGET",
                "exchange_work",
                "finite cumulative receive processing limit",
            )

    def require(self, unit, amount=1):
        if unit in ("metadata_units", "proof_steps"):
            self._check(amount)
        self._work.require(unit, amount)

    def charge(self, unit, amount):
        self._work.charge(unit, amount)

    def abandon(self, unit):
        self._work.abandon(unit)


class ExchangeService:
    """Selective verification-aware export and untrusted package import service."""

    def export_transfer_events(self, *args, **kwargs):
        from repo_catalog.domain.resource_stage import UnsupportedResourceStage

        raise UnsupportedResourceStage("export_transfer_events")

    def __init__(
        self,
        directory: Path | str,
        *,
        operational: OperationalAcquisitionLedger | Path | str | None = None,
        authorization: Any = None,
        admission: Any = None,
        grants: Any = None,
    ) -> None:
        self.directory = Path(directory)
        self.operational = operational
        self.authorization = authorization
        self.admission = admission
        self.grants = grants

    def _has_core(self) -> bool:
        return (self.directory / "core.sqlite3").is_file()

    def _has_context(self) -> bool:
        return (self.directory / "context.sqlite3").is_file()

    def _check_stop(self) -> None:
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoordinationError("RECOVERY_REQUIRED", "catalog")

    def _read_limits(self):
        from repo_catalog.adapters.sqlite.p1_coordination import SnapshotReadLimits

        if hasattr(self, "_export_scope"):
            return SnapshotReadLimits(
                max_sql_vm_steps=max(1, self._export_scope.max_work),
                max_total_rows=max(1, self._export_scope.max_work),
                on_steps=self._export_steps,
            )
        if hasattr(self, "_receive_selection"):
            scope = self._receive_selection
            return SnapshotReadLimits(
                max_sql_vm_steps=max(1, scope.max_work),
                max_total_rows=max(10000, scope.max_units),
            )
        return SnapshotReadLimits()

    def _store_identity(self, *, validation_work=None) -> tuple[str, str]:
        self._check_stop()
        core_identity = None
        if self._has_core():
            core = GitCore(self.directory / "core.sqlite3")
            try:
                core_identity = core.catalog_identity()
            finally:
                core.close()
        if not self._has_context():
            if core_identity is not None:
                return core_identity
            raise CoordinationError("AUTHORITY_UNAVAILABLE", "catalog")
        if self._has_context():
            from repo_catalog.adapters.sqlite.production_context import Context

            identity = []

            def checked_identity(rows):
                if len(rows) != 1 or rows[0][0] != "context":
                    raise CoordinationError("STORE_IDENTITY", "context")
                pair = (uuid4_value(rows[0][1]), uuid4_value(rows[0][2]))
                if core_identity is not None and pair != core_identity:
                    raise CoordinationError("PAIR_IDENTITY", "core+context")
                identity.append(pair)

            limits = (
                SnapshotReadLimits(
                    max_sql_vm_steps=min(
                        5_000_000, max(1, self._export_scope.max_work)
                    ),
                    max_total_rows=min(10_000, max(1, self._export_scope.max_work)),
                    on_steps=self._export_steps,
                )
                if validation_work is not None
                else SnapshotReadLimits()
            )
            try:
                with Context.snapshot(
                    self.directory,
                    read_limits=limits,
                    validation_work=validation_work,
                    _identity_sink=checked_identity,
                ):
                    pass
            except _ContextCallbackFailure as error:
                if (
                    identity
                    and isinstance(error.original, (CoreFailure, CoordinationError))
                    and error.original.code in ("BUDGET", "QUERY_BUDGET")
                ):
                    raise _IdentityBudgetRefusal(identity[0]) from error.original
                raise error.original from None
            except (CoordinationError, sqlite3.OperationalError) as error:
                if (
                    validation_work is not None
                    and identity
                    and (
                        getattr(error, "code", None) == "QUERY_BUDGET"
                        or getattr(error, "sqlite_errorcode", None)
                        == sqlite3.SQLITE_INTERRUPT
                    )
                ):
                    raise _IdentityBudgetRefusal(identity[0]) from error
                raise
            return core_identity or identity[0]

    @contextmanager
    def _open_operational(
        self, repo_uuid: str, instance_uuid: str
    ) -> Iterator[OperationalAcquisitionLedger | None]:
        if isinstance(self.operational, OperationalAcquisitionLedger):
            if self.operational.work_ledger.store_identity() != (
                repo_uuid,
                instance_uuid,
            ):
                raise CoordinationError("STORE_IDENTITY", "operational")
            yield self.operational
            return
        op_path = (
            Path(self.operational)
            if isinstance(self.operational, (Path, str))
            else (self.directory / "operational.sqlite3")
        )
        if op_path.is_dir():
            op_path = op_path / "operational.sqlite3"
        if not op_path.is_file():
            yield None
            return
        ledger = OperationalAcquisitionLedger(
            op_path,
            repository_uuidv4=repo_uuid,
            catalog_instance_uuidv4=instance_uuid,
        )
        try:
            yield ledger
        finally:
            ledger.close()

    def export_package(
        self,
        *,
        selection: ExchangeSelectionScope | None = None,
        package_id: str | None = None,
        exported_at_us: int | None = None,
    ) -> ExchangePackage:
        """Export a verification-checked ExchangePackage from Core and/or Context."""
        with catalog_gate(self.directory, exclusive=False):
            self._check_stop()
            scope = selection or ExchangeSelectionScope()
            explicit_scope(scope)
            if (
                scope.include_context
                and not self._has_context()
                and not self._has_core()
            ):
                from repo_catalog.domain.context_admission import AdmissionRefused

                raise AdmissionRefused("PERMISSION_DENIED")
            self._selection_details = {
                "dependency_reasons": [],
                "omissions": [],
                "work": 0,
            }
            self._export_scope = scope
            from repo_catalog.application.ref_exchange import ref_export_work

            self._export_work = ref_export_work(scope, self._selection_details)
            pkg_id = package_id or str(uuid4())
            try:
                repo_uuid, sender_instance = self._store_identity(
                    validation_work=_ContextCallbackWork(self._export_work)
                )
            except _IdentityBudgetRefusal as error:
                # The physical pair is checked, but no data is emitted when
                # the coexisting Context could not be validated within budget.
                repo_uuid, sender_instance = error.identity
                self._selection_details["omissions"].append(
                    {"section": "context", "reason": "resource_limit"}
                )
                self._selection_details.update(
                    emitted_units=0,
                    emitted_payload_bytes=0,
                    effective={
                        "sources": [],
                        "providers": [],
                        "repositories": [],
                        "objects": [],
                        "resources": [],
                    },
                )
                with catalog_completion(self.directory):
                    self._check_stop()
                    return ExchangePackage(
                        package_id=pkg_id,
                        exported_at_us=exported_at_us,
                        sender_catalog_instance_uuidv4=sender_instance,
                        repository_uuidv4=repo_uuid,
                        selection_scope=scope,
                        selection_report=self._selection_details,
                        core=empty_core_section()
                        if scope.include_core and self._has_core()
                        else None,
                        context=empty_context_section()
                        if scope.include_context and self._has_context()
                        else None,
                    )

            core_section: dict[str, list[dict[str, Any]]] | None = None
            if scope.include_core and self._has_core():
                try:
                    with account_verification(self._export_work):
                        core_scope = self._expand_core_selection(scope)
                        core_section = self._export_core(core_scope, sender_instance)
                except (sqlite3.OperationalError, CoordinationError) as error:
                    if (
                        getattr(error, "sqlite_errorcode", None)
                        != sqlite3.SQLITE_INTERRUPT
                        and getattr(error, "code", None) != "QUERY_BUDGET"
                    ):
                        raise
                    core_section = empty_core_section()
                    self._selection_details["omissions"].append(
                        {"section": "core", "reason": "work_limit"}
                    )
                except CoreFailure as error:
                    if error.code not in ("BUDGET", "QUERY_BUDGET"):
                        raise
                    core_section = empty_core_section()
                    self._selection_details["omissions"].append(
                        {
                            "section": "core",
                            "reason": "work_limit"
                            if error.scope == "ref-exchange"
                            and "cumulative export work" in str(error)
                            else "resource_limit",
                        }
                    )

            context_section: dict[str, list[dict[str, Any]]] | None = None
            if scope.include_context and self._has_context():
                try:
                    original_work = self._export_work
                    self._export_work = _ContextCallbackWork(original_work)
                    try:
                        try:
                            context_section = self._export_context(scope)
                        except _ContextCallbackFailure as error:
                            raise error.original from None
                    finally:
                        self._export_work = original_work
                except (sqlite3.OperationalError, CoordinationError) as error:
                    if (
                        getattr(error, "sqlite_errorcode", None)
                        != sqlite3.SQLITE_INTERRUPT
                        and getattr(error, "code", None) != "QUERY_BUDGET"
                    ):
                        raise
                    context_section = empty_context_section()
                    self._selection_details["omissions"].append(
                        {"section": "context", "reason": "work_limit"}
                    )
                except CoreFailure as error:
                    if error.code not in ("BUDGET", "QUERY_BUDGET"):
                        raise
                    context_section = empty_context_section()
                    self._selection_details["omissions"].append(
                        {"section": "context", "reason": "resource_limit"}
                    )

            with account_verification(self._export_work):
                self._selection_details["omissions"].extend(
                    filter_sections(
                        core_section,
                        context_section,
                        scope,
                    )
                )
                limited, counts = bound_sections(
                    core_section, context_section, scope, work=self._export_work
                )
                self._selection_details["omissions"].extend(limited)
                self._selection_details.update(counts)
                self._selection_details["omissions"].extend(
                    filter_sections(core_section, context_section, scope)
                )
            self._selection_details["emitted_units"] = sum(
                len(rows)
                for data in (core_section, context_section)
                if data is not None
                for rows in data.values()
            )
            self._selection_details["emitted_payload_bytes"] = sum(
                len(
                    json.dumps(
                        row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ).encode()
                )
                for data in (core_section, context_section)
                if data is not None
                for rows in data.values()
                for row in rows
            )
            self._selection_details["effective"] = {
                "sources": [
                    r["source_registration_uuidv4"]
                    for r in (context_section or {}).get("sources", [])
                ],
                "providers": [
                    r["service_instance_uuidv4"]
                    for r in (context_section or {}).get("providers", [])
                ],
                "repositories": [
                    r["repository_uuidv4"]
                    for r in (core_section or {}).get("repositories", [])
                ],
                "objects": [
                    [r["object_format"], r["object_oid"]]
                    for r in (core_section or {}).get("git_objects", [])
                ],
                "resources": [
                    [
                        r["service_instance_uuidv4"],
                        r["resource_kind"],
                        r["provider_resource_id"],
                    ]
                    for r in (context_section or {}).get("resources", [])
                ],
            }
            with catalog_completion(self.directory):
                self._check_stop()
                return ExchangePackage(
                    package_id=pkg_id,
                    exported_at_us=exported_at_us,
                    sender_catalog_instance_uuidv4=sender_instance,
                    repository_uuidv4=repo_uuid,
                    selection_scope=scope,
                    selection_report=self._selection_details,
                    core=core_section,
                    context=context_section,
                )

    def _expand_core_selection(self, scope):
        if scope.object_oids is None:
            return scope
        chosen = set(scope.object_oids)
        frontier = chosen.copy()
        with closing(GitCore(self.directory / "core.sqlite3")) as core:
            self._bound_export_connection(core._db)
            for depth in range(scope.max_depth):
                added = set()
                for owner in sorted(frontier, key=lambda object_oid: object_oid.key):
                    for row in core.exchange_metadata_rows(
                        "relation_membership", owner.key, self._export_work
                    ):

                        def stored_members(value):
                            parsed = json.loads(value[3])
                            if type(parsed) is not list:
                                raise ValueError("invalid relation members")
                            self._export_work.require("metadata_units", len(parsed))
                            try:
                                if not value[1] or not valid_group(
                                    owner.object_format, value[0], value[2], value[3]
                                ):
                                    raise ValueError("invalid relation group")
                                provenance = Provenance(*json.loads(value[4]))
                                if provenance.encoded != value[4]:
                                    raise ValueError("noncanonical relation provenance")
                                targets = [
                                    OID(member[1], member[2]) for member in parsed
                                ]
                            except BaseException:
                                self._export_work.abandon("metadata_units")
                                raise
                            self._export_work.charge("metadata_units", len(parsed))
                            return targets

                        if type(row[3]) is not str or type(row[4]) is not str:
                            core._integrity_stop(
                                (owner, "invalid relation metadata type")
                            )
                        size = len(row[3]) + len(row[4])
                        self._export_work.require("input_bytes", 13 * size + 2)
                        try:
                            targets = core._stored(owner, stored_members, row)
                        except BaseException:
                            self._export_work.abandon("input_bytes")
                            raise
                        self._export_work.charge("input_bytes", 2 * size)
                        for target in targets:
                            if target in chosen:
                                continue
                            if len(chosen) >= scope.max_units:
                                self._selection_details["omissions"].append(
                                    {
                                        "section": "git_objects",
                                        "unit": list(target.key),
                                        "reason": "unit_limit",
                                    }
                                )
                            elif not core.sql(
                                "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                                target.key,
                            ):
                                self._selection_details["omissions"].append(
                                    {
                                        "section": "git_objects",
                                        "unit": list(target.key),
                                        "reason": "missing_sender_object",
                                    }
                                )
                            else:
                                chosen.add(target)
                                added.add(target)
                                self._selection_details["dependency_reasons"].append(
                                    {
                                        "from": list(owner.key),
                                        "to": list(target.key),
                                        "depth": depth + 1,
                                    }
                                )
                frontier = added
                if not frontier:
                    break
        return replace(
            scope,
            object_oids=tuple(sorted(chosen, key=lambda object_oid: object_oid.key)),
        )

    def _export_steps(self, amount):
        self._selection_details["work"] += amount
        return self._selection_details["work"] > self._export_scope.max_work

    def _bound_export_connection(self, db):
        db.set_progress_handler(lambda: self._export_steps(100), 100)

    def _export_core(
        self,
        scope: ExchangeSelectionScope,
        sender_instance: str,
    ) -> dict[str, list[dict[str, Any]]]:
        section = empty_core_section()
        selected_oids = None if scope.object_oids is None else set(scope.object_oids)

        core = GitCore(self.directory / "core.sqlite3")
        try:
            self._bound_export_connection(core._db)
            core.ensure_available()
            with core._snapshot():
                from repo_catalog.application.ref_exchange import export_ref_units

                ref_work = self._export_work
                with account_verification(ref_work):
                    referenced_oids: set[OID] = export_ref_units(
                        core,
                        section,
                        scope,
                        ref_work,
                        self._selection_details["omissions"],
                    )

                for row in core.exchange_metadata_rows("repositories", (), ref_work):
                    core._stored("repository", uuid4_value, row[0])
                    section["repositories"].append({"repository_uuidv4": row[0]})

                for row in core.exchange_metadata_rows(
                    "repository_claims", (), ref_work
                ):

                    def stored_repository_claim(value):
                        claim = RepositoryClaim(
                            value[0],
                            value[1],
                            json.loads(value[2]),
                            Provenance(*json.loads(value[3])),
                        )
                        if claim.key != tuple(value):
                            raise ValueError("noncanonical repository claim")
                        return claim

                    if type(row[2]) is not str or type(row[3]) is not str:
                        core._integrity_stop(("repository claim", "invalid JSON type"))
                    size = len(row[2]) + len(row[3])
                    ref_work.require("input_bytes", 13 * size + 2)
                    try:
                        core._stored("repository claim", stored_repository_claim, row)
                    except BaseException:
                        ref_work.abandon("input_bytes")
                        raise
                    ref_work.charge("input_bytes", 2 * size)
                    section["repository_claims"].append(
                        {
                            "repository_uuidv4": row[0],
                            "field": row[1],
                            "value_json": row[2],
                            "provenance_json": row[3],
                        }
                    )

                # Verify all retained_metadata rows via core.read_metadata(oid)
                meta_rows = core.exchange_metadata_rows(
                    "retained_metadata", (), ref_work
                )
                for row in meta_rows:
                    if type(row[4]) is not int or row[4] < 0:
                        core._integrity_stop(("retained metadata", "invalid size"))
                    if row[4] > scope.max_bytes:
                        self._selection_details["omissions"].append(
                            {
                                "section": "retained_metadata",
                                "unit": list(row[:2]),
                                "reason": "byte_limit",
                            }
                        )
                        continue
                    object_oid = core._stored("retained metadata", OID, row[0], row[1])
                    if selected_oids is not None and object_oid not in selected_oids:
                        continue
                    copy = core._stored("retained metadata", uuid4_value, row[2])
                    actual = core.read_metadata_copy(object_oid, copy, ref_work)
                    if tuple(
                        actual[name]
                        for name in (
                            "object_format",
                            "object_oid",
                            "physical_copy_uuidv4",
                            "native_type",
                            "size",
                            "digest_sha256",
                        )
                    ) != tuple(row):
                        core._integrity_stop(
                            (object_oid, copy, "changed metadata copy")
                        )
                    body = actual["body"]
                    referenced_oids.add(object_oid)
                    if scope.include_retained_bytes:
                        section["retained_metadata"].append(
                            {
                                "object_format": row[0],
                                "object_oid": row[1],
                                "physical_copy_uuidv4": row[2],
                                "native_type": row[3],
                                "body_hex": body.hex(),
                                "size": row[4],
                                "digest_sha256": row[5],
                            }
                        )

                claim_rows = core.exchange_metadata_rows("scalar_claims", (), ref_work)
                for row in claim_rows:
                    object_oid = core._stored("scalar claim", OID, row[0], row[1])
                    if selected_oids is not None and object_oid not in selected_oids:
                        continue
                    # Run typed scalar projection check on this field
                    core.scalar(object_oid, row[2])
                    referenced_oids.add(object_oid)
                    is_checked = bool(row[5])
                    if is_checked and not scope.include_retained_bytes:
                        orig_prov = Provenance(*json.loads(row[4]))
                        downgraded_prov = Provenance(
                            orig_prov.source,
                            orig_prov.observation,
                            orig_prov.coordinate,
                            orig_prov.decoder,
                            orig_prov.decoder_version,
                            "reported",
                        )
                        section["scalar_claims"].append(
                            {
                                "object_format": row[0],
                                "object_oid": row[1],
                                "field": row[2],
                                "value_json": row[3],
                                "provenance_json": downgraded_prov.encoded,
                                "authority": "reported",
                            }
                        )
                    else:
                        section["scalar_claims"].append(
                            {
                                "object_format": row[0],
                                "object_oid": row[1],
                                "field": row[2],
                                "value_json": row[3],
                                "provenance_json": row[4],
                                "authority": "intrinsic" if is_checked else "reported",
                            }
                        )

                group_rows = core.exchange_metadata_rows(
                    "relation_groups", (), ref_work
                )
                for row in group_rows:
                    object_oid = core._stored("relation group", OID, row[0], row[1])
                    if selected_oids is not None and object_oid not in selected_oids:
                        continue
                    core.relations(object_oid, row[2], row[3])
                    referenced_oids.add(object_oid)
                    for m in json.loads(row[5]):
                        referenced_oids.add(OID(m[1], m[2]))
                    is_checked = bool(row[7])
                    if is_checked and not scope.include_retained_bytes:
                        orig_prov = Provenance(*json.loads(row[6]))
                        downgraded_prov = Provenance(
                            orig_prov.source,
                            orig_prov.observation,
                            orig_prov.coordinate,
                            orig_prov.decoder,
                            orig_prov.decoder_version,
                            "reported",
                        )
                        section["relation_groups"].append(
                            {
                                "object_format": row[0],
                                "object_oid": row[1],
                                "relation": row[2],
                                "scope": row[3],
                                "status": row[4],
                                "membership_json": row[5],
                                "provenance_json": downgraded_prov.encoded,
                                "authority": "reported",
                            }
                        )
                    else:
                        section["relation_groups"].append(
                            {
                                "object_format": row[0],
                                "object_oid": row[1],
                                "relation": row[2],
                                "scope": row[3],
                                "status": row[4],
                                "membership_json": row[5],
                                "provenance_json": row[6],
                                "authority": "intrinsic" if is_checked else "reported",
                            }
                        )

                for row in core.exchange_metadata_rows(
                    "git_observations", (), ref_work
                ):

                    def stored_git_observation(value):
                        observation_scope = json.loads(value[4])
                        observed_value = json.loads(value[5])
                        if (
                            type(observation_scope) is not list
                            or type(observed_value) is not dict
                        ):
                            raise ValueError("invalid Git observation JSON")
                        units = sum(
                            len(observed_value[name])
                            for name in ("roots", "refs", "entries")
                            if type(observed_value.get(name)) is list
                        )
                        ref_work.require("metadata_units", units)
                        try:
                            observation = GitObservation(
                                value[0],
                                value[1],
                                value[2],
                                value[3],
                                tuple(observation_scope),
                                observed_value,
                                Provenance(*json.loads(value[6])),
                            )
                            if observation.key != tuple(value):
                                raise ValueError("noncanonical Git observation")
                        except BaseException:
                            ref_work.abandon("metadata_units")
                            raise
                        ref_work.charge("metadata_units", units)
                        return observation

                    if any(type(row[index]) is not str for index in (4, 5, 6)):
                        core._integrity_stop(("Git observation", "invalid JSON type"))
                    size = sum(len(row[index]) for index in (4, 5, 6))
                    ref_work.require("input_bytes", 13 * size + 2)
                    try:
                        core._stored("Git observation", stored_git_observation, row)
                    except BaseException:
                        ref_work.abandon("input_bytes")
                        raise
                    ref_work.charge("input_bytes", 2 * size)
                    section["git_observations"].append(
                        {
                            "capture_origin_uuidv4": row[0],
                            "capture_uuidv4": row[1],
                            "repository_uuidv4": row[2],
                            "kind": row[3],
                            "scope_json": row[4],
                            "value_json": row[5],
                            "provenance_json": row[6],
                        }
                    )

                cov_scope_rows = core.exchange_metadata_rows(
                    "coverage_scopes", (), ref_work
                )
                exported_cov_scopes: set[tuple[str, str]] = set()
                exported_ref_keys = {
                    (r["observation_origin_uuidv4"], r["ref_observation_uuidv7"])
                    for r in section["ref_observations"]
                }
                scopes_by_key = {}

                def stored_scope(row):
                    coordinates = json.loads(row[1])
                    if type(coordinates) is not list:
                        raise ValueError("Coverage coordinates must be a list")
                    stored = CoreCoverageScope(row[0], tuple(coordinates))
                    if (
                        stored.encoded != row["owner_coordinates_json"]
                        or stored.coordinates[-1] != row["coverage_kind"]
                    ):
                        raise ValueError("noncanonical Coverage scope")
                    columns = (
                        "repository_uuidv4",
                        "object_format",
                        "object_oid",
                        "field",
                        "observation_origin_uuidv4",
                        "ref_observation_uuidv7",
                    )
                    expected = dict.fromkeys(columns)
                    bindings = {
                        "repository": ("repository_uuidv4",),
                        "ref_observation": (
                            "observation_origin_uuidv4",
                            "ref_observation_uuidv7",
                        ),
                        "object": ("object_format", "object_oid"),
                        "field": ("object_format", "object_oid", "field"),
                    }
                    expected.update(
                        zip(
                            bindings[stored.owner_kind],
                            stored.coordinates[:-1],
                            strict=True,
                        )
                    )
                    if any(expected[column] != row[column] for column in columns):
                        raise ValueError("Coverage scope columns disagree")
                    return stored

                for row in cov_scope_rows:
                    owner_kind = row[0]
                    # Validate the actual stored identity, including its
                    # denormalized coordinates, before selection uses it.
                    if type(row[1]) is not str:
                        core._integrity_stop(
                            ("coverage scope", "invalid coordinates type")
                        )
                    ref_work.require("input_bytes", 13 * len(row[1]) + 2)
                    try:
                        c_scope = core._stored("coverage scope", stored_scope, row)
                    except BaseException:
                        ref_work.abandon("input_bytes")
                        raise
                    ref_work.charge("input_bytes", 2 * len(row[1]))
                    if owner_kind in ("object", "field") and selected_oids is not None:
                        if OID(row[5], row[6]) not in selected_oids:
                            continue
                    if (
                        owner_kind == "ref_observation"
                        and c_scope.coordinates[:2] not in exported_ref_keys
                    ):
                        continue
                    core.coverage(c_scope, ref_work)
                    exported_cov_scopes.add((row[0], row[1]))
                    scopes_by_key[(row[0], row[1])] = c_scope
                    section["coverage_scopes"].append(
                        {
                            "owner_kind": row[0],
                            "owner_coordinates_json": row[1],
                        }
                    )

                for row in core.exchange_metadata_rows("coverage_claims", (), ref_work):
                    if (row[0], row[1]) not in exported_cov_scopes:
                        continue
                    # Latest-state projection does not validate older claims.
                    # Preserve and validate every exported historical claim.
                    if row[4] is not None and type(row[4]) is not str:
                        core._integrity_stop(("coverage claim", "invalid details type"))
                    details_size = len(row[4]) if row[4] is not None else 0
                    ref_work.require("input_bytes", 13 * details_size + 2)
                    try:
                        core._stored(
                            "coverage claim",
                            CoverageClaim,
                            scopes_by_key[(row[0], row[1])],
                            row[2],
                            row[3],
                            row[4],
                        )
                    except BaseException:
                        ref_work.abandon("input_bytes")
                        raise
                    ref_work.charge("input_bytes", 2 * details_size)
                    section["coverage_claims"].append(
                        {
                            "owner_kind": row[0],
                            "owner_coordinates_json": row[1],
                            "observed_at_us": row[2],
                            "coverage_state": row[3],
                            "details_json": row[4],
                        }
                    )

                from repo_catalog.application.ref_observations import encode_metered
                from repo_catalog.domain.ref_coverage import (
                    REF_NOTES_INVENTORY,
                    serialize_structures,
                )
                from repo_catalog.domain.ref_exchange import mapping_group_to_wire

                for row in section["coverage_claims"]:
                    if (
                        row["owner_kind"] != "ref_observation"
                        or row["coverage_state"] != "complete"
                    ):
                        continue
                    c_scope = CoreCoverageScope(
                        row["owner_kind"],
                        tuple(json.loads(row["owner_coordinates_json"])),
                    )
                    if c_scope.coordinates[-1] != REF_NOTES_INVENTORY:
                        # Preserve unsupported Claims as metadata. A verifier
                        # for another kind must not be invented or borrowed.
                        continue
                    c_claim = CoverageClaim(
                        c_scope, row["observed_at_us"], row["coverage_state"]
                    )
                    for proof in core.ref_coverage_proofs(
                        c_claim,
                        ref_work,
                        max_proofs=max(1, scope.max_units),
                        max_bytes=max(1, scope.max_bytes),
                    ):
                        section["ref_coverage_proofs"].append(
                            {
                                "owner_kind": row["owner_kind"],
                                "owner_coordinates_json": row["owner_coordinates_json"],
                                "observed_at_us": row["observed_at_us"],
                                "coverage_state": row["coverage_state"],
                                "group_json": encode_metered(
                                    ref_work,
                                    mapping_group_to_wire(
                                        proof.group,
                                        membership_json=encode_metered(
                                            ref_work,
                                            proof.group.members,
                                            max(1, scope.max_bytes),
                                        ),
                                        provenance_json=encode_metered(
                                            ref_work,
                                            proof.group.provenance.key,
                                            max(1, scope.max_bytes),
                                        ),
                                    ),
                                    max(1, scope.max_bytes),
                                ),
                                "verification_provenance_json": proof.verification_provenance.encoded,
                                "structures_json": serialize_structures(
                                    proof.structures,
                                    ref_work,
                                    max_structures=100_000,
                                    max_bytes=max(1, scope.max_bytes),
                                ),
                            }
                        )

                exported_cov_claims = {
                    (
                        row["owner_kind"],
                        row["owner_coordinates_json"],
                        row["observed_at_us"],
                        row["coverage_state"],
                    )
                    for row in section["coverage_claims"]
                }
                for row in core.exchange_metadata_rows("coverage_proofs", (), ref_work):
                    if (row[0], row[1]) not in exported_cov_scopes:
                        continue
                    c_scope = scopes_by_key[(row[0], row[1])]
                    if tuple(row[:4]) not in exported_cov_claims:
                        core._integrity_stop((c_scope, "missing Coverage proof claim"))
                    if c_scope.owner_kind == "ref_observation":
                        core._integrity_stop(
                            (c_scope, "unsupported generic ref Coverage proof")
                        )
                    if type(row[4]) is not str or type(row[5]) is not str:
                        core._integrity_stop((c_scope, "invalid Coverage proof type"))

                    def stored_proof(value):
                        CoverageClaim(c_scope, value[2], value[3])
                        parsed = json.loads(value[4])
                        if type(parsed) is not list:
                            raise ValueError("invalid Coverage proof members")
                        ref_work.require("metadata_units", len(parsed))
                        try:
                            if not valid_coverage_members(value[4]):
                                raise ValueError("invalid Coverage proof members")
                            provenance = Provenance(*json.loads(value[5]))
                            if provenance.encoded != value[5]:
                                raise ValueError(
                                    "noncanonical Coverage proof provenance"
                                )
                            members = [OID(*m) for m in parsed]
                        except BaseException:
                            ref_work.abandon("metadata_units")
                            raise
                        ref_work.charge("metadata_units", len(parsed))
                        return members

                    input_size = len(row[4]) + len(row[5])
                    ref_work.require("input_bytes", 13 * input_size + 2)
                    try:
                        members = core._stored(c_scope, stored_proof, row)
                    except BaseException:
                        ref_work.abandon("input_bytes")
                        raise
                    ref_work.charge("input_bytes", 2 * input_size)
                    for m in members:
                        if not core.sql(
                            "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
                            m.key,
                        ):
                            core._integrity_stop(
                                (c_scope, "missing Coverage proof member", m.key)
                            )
                        referenced_oids.add(m)
                    section["coverage_proofs"].append(
                        {
                            "owner_kind": row[0],
                            "owner_coordinates_json": row[1],
                            "observed_at_us": row[2],
                            "coverage_state": row[3],
                            "members_json": row[4],
                            "provenance_json": row[5],
                        }
                    )

                for row in core.exchange_metadata_rows("git_objects", (), ref_work):
                    object_oid = core._stored("git object", OID, row[0], row[1])
                    if (
                        selected_oids is not None
                        and object_oid not in selected_oids
                        and object_oid not in referenced_oids
                    ):
                        continue
                    section["git_objects"].append(
                        {"object_format": row[0], "object_oid": row[1]}
                    )

                return section
        finally:
            core.close()

    def _export_context(
        self,
        scope: ExchangeSelectionScope,
    ) -> dict[str, list[dict[str, Any]]]:
        from repo_catalog.adapters.sqlite.production_context import Context
        from repo_catalog.domain.exchange import _bounded_json
        from repo_catalog.domain.exchange_rows import validate_rows
        from repo_catalog.domain.p1_context import CoverageScope as ContextCoverageScope
        from repo_catalog.domain.p1_context import ResourceKey
        from repo_catalog.domain.production_context import (
            CollectionObservation,
            ResourceRelation,
            SourceInventory,
            json_value,
        )
        from repo_catalog.domain.time import validate_required_observation_us

        section = empty_context_section()
        selected_rks = None if scope.resource_keys is None else set(scope.resource_keys)
        selected_sources = (
            None if scope.source_uuidv4s is None else set(scope.source_uuidv4s)
        )

        from repo_catalog.adapters.sqlite.p1_coordination import SnapshotReadLimits

        with Context.snapshot(
            self.directory,
            read_limits=SnapshotReadLimits(
                max_sql_vm_steps=max(1, scope.max_work),
                max_total_rows=max(1, scope.max_work),
                on_steps=self._export_steps,
            ),
            validation_work=self._export_work,
        ) as ctx:

            def validate_stored_context_row(name, row):
                """Validate only a row reconstructed from this pinned store."""
                size = sum(len(value) for value in row.values() if type(value) is str)
                self._export_work.require("input_bytes", 13 * size + 2)
                callback_error = None

                def spend(amount):
                    nonlocal callback_error
                    try:
                        self._export_work.require("metadata_units", amount)
                        self._export_work.charge("metadata_units", amount)
                    except BaseException as error:
                        callback_error = error
                        raise

                try:
                    try:
                        _bounded_json(row, root="row:" + name, spend=spend)
                    except BaseException as error:
                        if callback_error is not None:
                            raise callback_error
                        if (
                            isinstance(error, ExchangeError)
                            and error.code == "INPUT_LIMIT"
                        ):
                            raise CoreFailure(
                                "QUERY_BUDGET", name, "finite Context row limit"
                            ) from error
                        if isinstance(error, (ValueError, TypeError, RecursionError)):
                            with ctx._stored("exchange Context row"):
                                raise ValueError(
                                    "invalid stored Context JSON"
                                ) from error
                        raise
                    self._export_work.require("metadata_units", size + len(row))
                    try:
                        with ctx._stored("exchange Context row"):
                            try:
                                validate_rows(None, {name: [row]})
                            except RecursionError as error:
                                raise ValueError(
                                    "invalid stored Context nesting"
                                ) from error
                    except BaseException:
                        self._export_work.abandon("metadata_units")
                        raise
                    self._export_work.charge("metadata_units", size + len(row))
                except BaseException:
                    self._export_work.abandon("input_bytes")
                    raise
                self._export_work.charge("input_bytes", 4 * size)

            for row in ctx._exchange_metadata_rows("providers", self._export_work):
                section["providers"].append(
                    {
                        "service_instance_uuidv4": row[0],
                        "provider_kind": row[1],
                        "configuration_json": _checked_registration(
                            ctx, "provider", row[2]
                        ),
                    }
                )

            for row in ctx._exchange_metadata_rows("repositories", self._export_work):
                section["repositories"].append(
                    {
                        "repository_uuidv4": row[0],
                        "configuration_json": _checked_registration(
                            ctx, "repository", row[1]
                        ),
                    }
                )

            for row in ctx._exchange_metadata_rows("sources", self._export_work):
                if selected_sources is not None and row[0] not in selected_sources:
                    continue
                section["sources"].append(
                    {
                        "source_registration_uuidv4": row[0],
                        "service_instance_uuidv4": row[1],
                        "configuration_json": _checked_registration(
                            ctx, "source", row[2]
                        ),
                    }
                )

            for row in ctx._exchange_metadata_rows(
                "source_repositories", self._export_work
            ):
                if selected_sources is not None and row[0] not in selected_sources:
                    continue
                section["source_repositories"].append(
                    {
                        "source_registration_uuidv4": row[0],
                        "repository_uuidv4": row[1],
                        "attributes_json": _checked_registration(
                            ctx, "membership", row[2]
                        ),
                    }
                )

            for row in ctx._exchange_metadata_rows(
                "source_inventories", self._export_work
            ):
                if selected_sources is not None and row[0] not in selected_sources:
                    continue
                with ctx._stored("source inventory"):
                    if type(row[4]) is not int or row[4] not in (0, 1):
                        raise ValueError("invalid stored inventory terminal")
                record = {
                    "source_registration_uuidv4": row[0],
                    "scope_json": row[1],
                    "observed_at_us": row[2],
                    "coverage_state": row[3],
                    "terminal": bool(row[4]),
                    "members_json": row[5],
                    "provenance_json": row[6],
                }
                validate_stored_context_row("source_inventories", record)
                input_size = sum(len(row[index]) for index in (1, 5, 6))
                self._export_work.require("input_bytes", 13 * input_size + 2)
                try:
                    with ctx._stored("source inventory"):
                        members = json.loads(row[5])
                        if type(members) is not list:
                            raise ValueError("invalid stored inventory members")
                    self._export_work.require("metadata_units", len(members))
                    try:
                        with ctx._stored("source inventory"):
                            inventory = SourceInventory(
                                row[0],
                                row[1],
                                row[2],
                                row[3],
                                bool(row[4]),
                                tuple(members),
                                row[6],
                            )
                            if inventory.values != tuple(row):
                                raise ValueError("noncanonical source inventory")
                    except BaseException:
                        self._export_work.abandon("metadata_units")
                        raise
                    self._export_work.charge("metadata_units", len(members))
                except BaseException:
                    self._export_work.abandon("input_bytes")
                    raise
                self._export_work.charge("input_bytes", 2 * input_size)
                section["source_inventories"].append(record)

            # Determine full set of exported resources (including parents/members of selected resources)
            all_resource_rows = ctx._exchange_metadata_rows(
                "resources", self._export_work
            )

            rel_rows = ctx._exchange_metadata_rows("relations", self._export_work)
            coll_rows = ctx._exchange_metadata_rows("collections", self._export_work)
            support_columns = (
                "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,"
                "target_json,clock_json,provenance_json,observed_at_us,"
                "event_report_members_json,event_report_scope_json"
            )
            support_rows = [
                dict(zip(support_columns.split(","), r))
                for r in ctx._exchange_metadata_rows(
                    "repository_relations", self._export_work
                )
            ]
            resource_columns = (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
                "identifier_namespace_kind",
                "identifier_namespace_id",
                "document_kind",
                "provider_document_id",
            )
            relation_columns = (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
                "relation_kind",
                "members_json",
                "provenance_json",
                "scope_json",
                "observed_at_us",
            )
            collection_columns = (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
                "collection_kind",
                "provenance_json",
                "scope_json",
                "observed_at_us",
                "terminal_state",
                "members_json",
            )

            def validate_stored_context_graph(name, record):
                validate_stored_context_row(name, record)
                inputs = ("members_json", "provenance_json", "scope_json")
                size = sum(len(record[key]) for key in inputs)
                self._export_work.require("input_bytes", 13 * size + 2)
                try:
                    with ctx._stored("exchange Context graph"):
                        try:
                            members = json.loads(record["members_json"])
                        except RecursionError as error:
                            raise ValueError(
                                "invalid Context member nesting"
                            ) from error
                        if type(members) is not list:
                            raise ValueError("invalid Context members")
                    self._export_work.require("metadata_units", len(members))
                    try:
                        with ctx._stored("exchange Context graph"):
                            owner = ResourceKey(
                                record["service_instance_uuidv4"],
                                record["resource_kind"],
                                record["provider_resource_id"],
                            )
                            keys = tuple(ResourceKey(*member) for member in members)
                            if name == "resource_relations":
                                observed = ResourceRelation(
                                    owner,
                                    record["relation_kind"],
                                    keys,
                                    record["provenance_json"],
                                    record["scope_json"],
                                    record["observed_at_us"],
                                )
                            else:
                                observed = CollectionObservation(
                                    owner,
                                    record["collection_kind"],
                                    record["provenance_json"],
                                    record["scope_json"],
                                    record["observed_at_us"],
                                    record["terminal_state"],
                                    keys,
                                )
                            if observed.members_json != record["members_json"]:
                                raise ValueError("noncanonical Context members")
                    except BaseException:
                        self._export_work.abandon("metadata_units")
                        raise
                    self._export_work.charge("metadata_units", len(members))
                except BaseException:
                    self._export_work.abandon("input_bytes")
                    raise
                self._export_work.charge("input_bytes", 2 * size)

            for raw in all_resource_rows:
                validate_stored_context_row(
                    "resources", dict(zip(resource_columns, raw, strict=True))
                )
            for raw in rel_rows:
                validate_stored_context_graph(
                    "resource_relations", dict(zip(relation_columns, raw, strict=True))
                )
            for raw in coll_rows:
                validate_stored_context_graph(
                    "collections", dict(zip(collection_columns, raw, strict=True))
                )
            for raw in support_rows:
                validate_stored_context_row("resource_repository_relations", raw)
            included_rks, reasons, omissions = expand_resources(
                all_resource_rows, rel_rows, coll_rows, scope, support_rows
            )
            self._selection_details["dependency_reasons"].extend(reasons)
            self._selection_details["omissions"].extend(omissions)
            for row in all_resource_rows:
                if ResourceKey(*row[:3]) in included_rks:
                    section["resources"].append(
                        dict(
                            zip(
                                (
                                    "service_instance_uuidv4",
                                    "resource_kind",
                                    "provider_resource_id",
                                    "identifier_namespace_kind",
                                    "identifier_namespace_id",
                                    "document_kind",
                                    "provider_document_id",
                                ),
                                row,
                            )
                        )
                    )
            for rows, key, member_index in (
                (rel_rows, "resource_relations", 4),
                (coll_rows, "collections", 8),
            ):
                columns = (
                    (
                        "service_instance_uuidv4",
                        "resource_kind",
                        "provider_resource_id",
                        "relation_kind",
                        "members_json",
                        "provenance_json",
                        "scope_json",
                        "observed_at_us",
                    )
                    if key == "resource_relations"
                    else (
                        "service_instance_uuidv4",
                        "resource_kind",
                        "provider_resource_id",
                        "collection_kind",
                        "provenance_json",
                        "scope_json",
                        "observed_at_us",
                        "terminal_state",
                        "members_json",
                    )
                )
                for row in rows:
                    owner = ResourceKey(*row[:3])
                    if owner not in included_rks:
                        continue
                    if not all(
                        ResourceKey(*m) in included_rks
                        for m in json.loads(row[member_index])
                    ):
                        self._selection_details["omissions"].append(
                            {
                                "section": key,
                                "unit": list(row[:4]),
                                "reason": "whole_relation_missing_selected_member",
                            }
                        )
                        continue
                    if key == "resource_relations":
                        ctx.relations(owner, row[3])
                    section[key].append(dict(zip(columns, row)))
            for table, selector, columns in (
                (
                    "resource_repository_relations",
                    "repository_relations",
                    "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us,event_report_members_json,event_report_scope_json",
                ),
                (
                    "repository_mapping_dispositions",
                    "mapping_dispositions",
                    "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,claim_clock_json,claim_target_json,claim_provenance_json,disposition_kind,disposition_clock_json,disposition_provenance_json,observed_at_us,replacement_clock_json,replacement_target_json,replacement_provenance_json",
                ),
            ):
                for row in ctx._exchange_metadata_rows(selector, self._export_work):
                    if ResourceKey(*row[:3]) in included_rks:
                        section[table].append(dict(zip(columns.split(","), row)))
            # If graph limits withheld a Transfer scope, its endpoint rows must
            # also be withheld, never exported as a newly one-sided report.
            scopes = {
                (
                    r["service_instance_uuidv4"],
                    r["resource_kind"],
                    r["provider_resource_id"],
                    r["provenance_json"],
                    json.dumps(
                        json.loads(r["scope_json"]).get("clock"),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                for r in section["resource_relations"]
                if r["relation_kind"] == "transfer_event_report"
            }
            section["resource_repository_relations"] = [
                r
                for r in section["resource_repository_relations"]
                if not r["relation_kind"].startswith("transfer_")
                or (
                    r["service_instance_uuidv4"],
                    r["resource_kind"],
                    r["provider_resource_id"],
                    r["provenance_json"],
                    r["clock_json"],
                )
                in scopes
            ]

            referenced_text_digests: set[str] = set()
            fc_rows = ctx._exchange_metadata_rows("field_candidates", self._export_work)
            for row in fc_rows:
                rk = ResourceKey(row[0], row[1], row[2])
                if rk not in included_rks:
                    continue
                ctx.candidates(rk, row[3])
                if row[3] == "text_body_sha256":
                    digest_val = json.loads(row[4])
                    if digest_val is not None:
                        # Checked read ensures missing or corrupt text body stops the catalog
                        ctx.read_text(digest_val)
                        referenced_text_digests.add(digest_val)
                section["field_candidates"].append(
                    {
                        "service_instance_uuidv4": row[0],
                        "resource_kind": row[1],
                        "provider_resource_id": row[2],
                        "field_name": row[3],
                        "value_json": row[4],
                        "clock_domain": row[5],
                        "clock_ts_us": row[6],
                        "provenance_json": row[7],
                        "observed_at_us": row[8],
                    }
                )

            tb_rows = ctx._exchange_metadata_rows("text_bodies", self._export_work)
            for (sha256_hex,) in tb_rows:
                # Always verify every stored text body on export
                text_val = ctx.read_text(sha256_hex)
                if (
                    selected_rks is not None
                    and sha256_hex not in referenced_text_digests
                ):
                    continue
                section["text_bodies"].append(
                    {
                        "sha256": sha256_hex,
                        "text_value": text_val,
                    }
                )

            cr_rows = ctx._exchange_metadata_rows("core_references", self._export_work)
            for row in cr_rows:
                rk = ResourceKey(row[0], row[1], row[2])
                if rk not in included_rks:
                    continue
                ctx.core_dependencies(rk)
                section["core_references"].append(
                    {
                        "service_instance_uuidv4": row[0],
                        "resource_kind": row[1],
                        "provider_resource_id": row[2],
                        "role": row[3],
                        "object_format": row[4],
                        "object_oid": row[5],
                        "provenance_json": row[6],
                    }
                )

            exported_ctx_scopes: set[tuple[str, str]] = set()
            ctx_scopes_by_key = {}
            for row in ctx._exchange_metadata_rows("scopes", self._export_work):
                if type(row[1]) is not str:
                    with ctx._stored("exchange Coverage scope"):
                        raise ValueError("invalid stored coordinates type")
                self._export_work.require("input_bytes", 13 * len(row[1]) + 2)
                try:
                    with ctx._stored("exchange Coverage scope"):
                        coords = json.loads(row[1])
                        if type(coords) is not list:
                            raise ValueError("Coverage coordinates must be a list")
                        c_scope = ContextCoverageScope(row[0], tuple(coords))
                        if c_scope.encoded != row[1]:
                            raise ValueError("noncanonical Coverage scope")
                except BaseException:
                    self._export_work.abandon("input_bytes")
                    raise
                self._export_work.charge("input_bytes", 2 * len(row[1]))
                if row[0] == "source" and selected_sources is not None:
                    if coords[0] not in selected_sources:
                        continue
                if row[0] in ("resource", "collection") and selected_rks is not None:
                    rk = ResourceKey(coords[0], coords[1], coords[2])
                    if rk not in included_rks:
                        continue
                ctx.coverage(c_scope)
                exported_ctx_scopes.add((row[0], row[1]))
                ctx_scopes_by_key[(row[0], row[1])] = c_scope
                section["coverage_scopes"].append(
                    {
                        "owner_kind": row[0],
                        "owner_coordinates_json": row[1],
                    }
                )

            for row in ctx._exchange_metadata_rows("claims", self._export_work):
                if (row[0], row[1]) not in exported_ctx_scopes:
                    continue
                if row[4] is not None and type(row[4]) is not str:
                    with ctx._stored("exchange Coverage claim"):
                        raise ValueError("invalid stored details type")
                details_size = len(row[4]) if row[4] is not None else 0
                self._export_work.require("input_bytes", 13 * details_size + 2)
                try:
                    with ctx._stored("exchange Coverage claim"):
                        try:
                            CoverageClaim(
                                ctx_scopes_by_key[(row[0], row[1])],
                                row[2],
                                row[3],
                                row[4],
                            )
                        except RecursionError as error:
                            raise ValueError(
                                "invalid Coverage claim nesting"
                            ) from error
                except BaseException:
                    self._export_work.abandon("input_bytes")
                    raise
                self._export_work.charge("input_bytes", 2 * details_size)
                section["coverage_claims"].append(
                    {
                        "owner_kind": row[0],
                        "owner_coordinates_json": row[1],
                        "observed_at_us": row[2],
                        "coverage_state": row[3],
                        "details_json": row[4],
                    }
                )

            ctx_claim_keys = {
                (
                    row["owner_kind"],
                    row["owner_coordinates_json"],
                    row["observed_at_us"],
                    row["coverage_state"],
                )
                for row in section["coverage_claims"]
            }

            def checked_context_proof(row, *, source):
                c_scope = ctx_scopes_by_key[(row[0], row[1])]
                json_indexes = (5, 9, 10) if source else (8, 11)
                with ctx._stored("exchange Coverage proof"):
                    if tuple(row[:4]) not in ctx_claim_keys:
                        raise ValueError("missing Coverage proof claim")
                    if any(type(row[index]) is not str for index in json_indexes):
                        raise ValueError("invalid Coverage proof JSON type")
                input_size = sum(len(row[index]) for index in json_indexes)
                self._export_work.require("input_bytes", 13 * input_size + 2)
                try:
                    with ctx._stored("exchange Coverage proof"):
                        try:
                            CoverageClaim(c_scope, row[2], row[3])
                            if source:
                                uuid4_value(row[4])
                                original_scope = json_value(row[5])
                                validate_required_observation_us(row[6])
                                members = json_value(row[9])
                                json_value(row[10], provenance=True)
                                if (
                                    c_scope.owner_kind != "source_inventory"
                                    or c_scope.coordinates[:2] != (row[4], row[5])
                                    or type(original_scope) is not dict
                                    or original_scope.get("coverage_kind")
                                    != c_scope.coordinates[-1]
                                    or row[6] > row[2]
                                    or row[7]
                                    not in (
                                        "complete",
                                        "partial",
                                        "unknown",
                                        "not_applicable",
                                    )
                                    or row[8] != 1
                                    or (row[3] == "complete" and row[7] != "complete")
                                ):
                                    raise ValueError("invalid Source Coverage proof")
                            else:
                                ResourceKey(row[4], row[5], row[6])
                                if type(row[7]) is not str or not row[7]:
                                    raise ValueError("invalid collection kind")
                                json_value(row[8], provenance=True)
                                validate_required_observation_us(row[9])
                                members = json_value(row[11])
                                if (
                                    row[9] > row[2]
                                    or row[10] not in ("complete", "partial", "unknown")
                                    or (row[3] == "complete" and row[10] != "complete")
                                ):
                                    raise ValueError(
                                        "invalid collection Coverage proof"
                                    )
                            if type(members) is not list:
                                raise ValueError("invalid Coverage proof members")
                        except RecursionError as error:
                            raise ValueError(
                                "invalid Coverage proof nesting"
                            ) from error
                except BaseException:
                    self._export_work.abandon("input_bytes")
                    raise
                self._export_work.charge("input_bytes", 2 * input_size)
                self._export_work.require("metadata_units", len(members) + 1)
                try:
                    with ctx._stored("exchange Coverage proof"):
                        if source:
                            for member in members:
                                uuid4_value(member)
                            if (
                                len(set(members)) != len(members)
                                or sorted(members) != members
                            ):
                                raise ValueError("invalid Source Coverage members")
                        else:
                            for member in members:
                                ResourceKey(*member)
                        if source:
                            evidence = ctx.db.execute(
                                "SELECT 1 FROM source_inventory_evidence WHERE source_registration_uuidv4=? AND scope_json=? AND observed_at_us=? AND coverage_state=? AND terminal=? AND members_json=? AND provenance_json=?",
                                tuple(row[4:11]),
                            ).fetchone()
                        else:
                            evidence = ctx.db.execute(
                                "SELECT 1 FROM collection_terminals WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND collection_kind=? AND provenance_json=? AND observed_at_us=? AND terminal_state=? AND members_json=?",
                                tuple(row[4:12]),
                            ).fetchone()
                        if not evidence:
                            raise ValueError("missing Coverage proof evidence")
                except BaseException:
                    self._export_work.abandon("metadata_units")
                    raise
                self._export_work.charge("metadata_units", len(members) + 1)

            for row in ctx._exchange_metadata_rows("proofs", self._export_work):
                if (row[0], row[1]) not in exported_ctx_scopes:
                    continue
                checked_context_proof(row, source=False)
                section["coverage_proofs"].append(
                    {
                        "proof_kind": "collection",
                        "owner_kind": row[0],
                        "owner_coordinates_json": row[1],
                        "observed_at_us": row[2],
                        "coverage_state": row[3],
                        "service_instance_uuidv4": row[4],
                        "resource_kind": row[5],
                        "provider_resource_id": row[6],
                        "collection_kind": row[7],
                        "provenance_json": row[8],
                        "terminal_observed_at_us": row[9],
                        "terminal_state": row[10],
                        "members_json": row[11],
                    }
                )

            for row in ctx._exchange_metadata_rows("source_proofs", self._export_work):
                if (row[0], row[1]) not in exported_ctx_scopes:
                    continue
                checked_context_proof(row, source=True)
                section["coverage_proofs"].append(
                    {
                        "proof_kind": "source_inventory",
                        "owner_kind": row[0],
                        "owner_coordinates_json": row[1],
                        "observed_at_us": row[2],
                        "coverage_state": row[3],
                        "source_registration_uuidv4": row[4],
                        "scope_json": row[5],
                        "terminal_observed_at_us": row[6],
                        "terminal_state": row[7],
                        "terminal": bool(row[8]),
                        "members_json": row[9],
                        "provenance_json": row[10],
                    }
                )

            for name, records in section.items():
                for record in records:
                    validate_stored_context_row(name, record)
        return section

    def import_package(
        self,
        raw_package: ExchangePackage | str | bytes | dict[str, Any],
        *,
        work: WorkBudget | None = None,
        request: RequestIdentity | None = None,
        new_request: bool = False,
        permitted_repository_uuidv4s: tuple[str, ...] = (),
        selection: ExchangeSelectionScope | None = None,
        cut: Callable[[str], None] = lambda point: None,
        authorization: Any = None,
        admission: Any = None,
        grants: Any = None,
    ) -> ExchangeImportReport:
        """Validate and import an ExchangePackage into Core and/or Context."""
        self._check_stop()
        from repo_catalog.domain.p1_core import uuid4_value

        if not isinstance(permitted_repository_uuidv4s, tuple):
            raise ExchangeError("INVALID_PERMISSION", "repositories")
        for value in permitted_repository_uuidv4s:
            uuid4_value(value)
        repo_uuid, instance_uuid = self._store_identity()
        self._receiver_instance = instance_uuid
        if request is None:
            if isinstance(raw_package, ExchangePackage):
                origin, identifier = (
                    raw_package.sender_catalog_instance_uuidv4,
                    raw_package.package_id,
                )
            elif isinstance(raw_package, dict):
                origin, identifier = (
                    raw_package.get("sender_catalog_instance_uuidv4"),
                    raw_package.get("package_id"),
                )
            else:
                raise ExchangeError(
                    "REQUEST_REQUIRED",
                    "package",
                    "wire JSON requires an explicit cumulative request identity",
                )
            request = RequestIdentity(origin, identifier)
        with self._open_operational(repo_uuid, instance_uuid) as ledger:
            if ledger is None:
                raise CoordinationError(
                    "CONTINUATION_UNAVAILABLE",
                    "exchange",
                    "explicit Operational initialization required",
                )
            if work is not None:
                from repo_catalog.adapters.sqlite.p1_coordination import NotesWorkBudget

                if (
                    not isinstance(work, NotesWorkBudget)
                    or work.request != request
                    or work.ledger._path != ledger.work_ledger._path
                ):
                    raise ExchangeError("DURABLE_BUDGET_REQUIRED", "request")
                work.ledger.validate_continuation(request, work.attempt_uuidv4)
            if work is None:
                if ledger is None:
                    raise CoordinationError(
                        "CONTINUATION_UNAVAILABLE",
                        "exchange",
                        "Operational accounting required",
                    )
                _, _, work, _ = ledger.create_budget(
                    scope=["p5-exchange-import", *request.values()],
                    request=request,
                    new_request=new_request,
                    work_limits={"metadata_units": 10_000_000},
                )
            if selection is not None:
                explicit_scope(selection)
                work = _ReceiveWork(work, selection.max_work)
            # Reserve before JSON parsing, canonicalization, digest comparison or
            # bytes expansion. Successful work settles actual measured input;
            # failure/crash uncertainty retains the reserved upper bounds.
            from repo_catalog.domain.exchange import (
                _WIRE_WORK,
                MAX_ELEMENTS,
                MAX_PACKAGE_BYTES,
                _bounded_json,
            )

            pending = {}
            measurement = {
                "metadata_units": 0,
                "verification_bytes": 0,
                "ref_decode_input_bytes": 0,
            }
            token = _WIRE_WORK.set(measurement)
            try:
                for unit, amount in (
                    ("input_bytes", 4 * MAX_PACKAGE_BYTES),
                    ("verification_bytes", 2 * MAX_PACKAGE_BYTES),
                    ("metadata_units", 5 * MAX_ELEMENTS),
                ):
                    work.require(unit, amount)
                    pending[unit] = amount
                package = decode_package(raw_package)
                _bounded_json(package.to_dict())
                if isinstance(raw_package, bytes):
                    input_bytes = len(raw_package)
                elif isinstance(raw_package, str):
                    input_bytes = len(raw_package.encode("utf-8"))
                else:
                    from repo_catalog.domain.exchange import encode_package

                    input_bytes = len(encode_package(package).encode("utf-8"))
                actual = {
                    "input_bytes": input_bytes + measurement["ref_decode_input_bytes"],
                    "verification_bytes": measurement["verification_bytes"],
                    "metadata_units": measurement["metadata_units"],
                }
                for unit in tuple(pending):
                    if actual[unit] > pending[unit]:
                        raise ExchangeError(
                            "INPUT_LIMIT", unit, "measured work exceeds input bound"
                        )
                    work.charge(unit, actual[unit])
                    del pending[unit]
            except BaseException:
                for unit, amount in pending.items():
                    if hasattr(work, "abandon"):
                        work.abandon(unit)
                    else:
                        work.charge(unit, amount)
                raise
            finally:
                _WIRE_WORK.reset(token)
            explicit_scope(package.selection_scope)
            receive_selection = selection or package.selection_scope
            explicit_scope(receive_selection)
            if selection is None:
                # The effective default is learned only after bounded decode.
                # Previously performed decode work remains charged and counts
                # against this same frozen cumulative ceiling, even with no rows.
                work = _ReceiveWork(work, receive_selection.max_work)
            active_grants = grants if grants is not None else self.grants
            auth = authorization if authorization is not None else self.authorization
            adm = admission if admission is not None else self.admission
            want_context = package.context is not None
            if (
                want_context
                and auth is None
                and adm is None
                and not permitted_repository_uuidv4s
                and active_grants is None
            ):
                from repo_catalog.domain.context_admission import AdmissionRefused

                raise AdmissionRefused("PERMISSION_DENIED")

            request_binding = {
                "selection": receive_selection.to_dict(),
                "sender": package.sender_catalog_instance_uuidv4,
                "package_id": package.package_id,
                "digest": package.digest_sha256,
                "permitted_repositories": sorted(set(permitted_repository_uuidv4s)),
            }
            saved = ledger.work_ledger.set_progress_once(
                request, encode(["adr0030-receive-request"]), request_binding
            )
            if saved != request_binding:
                raise ExchangeError("REQUEST_SCOPE", "exchange")
            return self._import_package(
                package,
                work=work,
                ledger=ledger,
                request=request,
                permitted=permitted_repository_uuidv4s,
                selection=receive_selection,
                cut=cut,
                authorization=authorization,
                admission=admission,
                grants=grants,
            )

    @staticmethod
    def _extract_context_dependencies(
        context_data: dict[str, Any] | None,
    ) -> Any:
        from repo_catalog.domain.context_admission import DependencySet, dependencies

        if not context_data:
            return DependencySet()

        import json

        from repo_catalog.domain.p1_context import ResourceKey
        from repo_catalog.domain.p1_core import OID
        from repo_catalog.domain.selective_exchange import (
            disposition as decode_disposition,
        )
        from repo_catalog.domain.selective_exchange import (
            relation as decode_relation,
        )

        resources = set()
        repositories = set()
        sources = set()
        source_repository_pairs = set()
        provider_registrations = set()
        dispositions = set()
        mapping_claims = set()
        object_oids = set()

        for p in context_data.get("providers", ()):
            if "service_instance_uuidv4" in p:
                provider_registrations.add(p["service_instance_uuidv4"])

        for r in context_data.get("repositories", ()):
            if "repository_uuidv4" in r:
                repositories.add(r["repository_uuidv4"])

        for s in context_data.get("sources", ()):
            if "source_registration_uuidv4" in s:
                sources.add(s["source_registration_uuidv4"])
            if "service_instance_uuidv4" in s:
                provider_registrations.add(s["service_instance_uuidv4"])

        for sr in context_data.get("source_repositories", ()):
            src = sr.get("source_registration_uuidv4")
            repo = sr.get("repository_uuidv4")
            if src:
                sources.add(src)
            if repo:
                repositories.add(repo)
            if src and repo:
                source_repository_pairs.add((src, repo))

        for res in context_data.get("resources", ()):
            rk = ResourceKey(
                res["service_instance_uuidv4"],
                res["resource_kind"],
                res["provider_resource_id"],
            )
            resources.add(rk)
            if "service_instance_uuidv4" in res:
                provider_registrations.add(res["service_instance_uuidv4"])

        for rrr in context_data.get("resource_repository_relations", ()):
            if "repository_uuidv4" in rrr:
                repositories.add(rrr["repository_uuidv4"])
            try:
                rel = decode_relation(rrr)
                dep = dependencies(rel)
                resources.update(dep.resources)
                repositories.update(dep.repositories)
                sources.update(dep.sources)
                source_repository_pairs.update(dep.source_repository_pairs)
                mapping_claims.update(dep.mapping_claims)
                provider_registrations.update(dep.provider_registrations)
                object_oids.update(dep.object_oids)
                if rel.relation_kind == "represents_repository":
                    mapping_claims.add(rel.claim_key)
            except Exception:
                pass

        for rmd in context_data.get("repository_mapping_dispositions", ()):
            if "repository_uuidv4" in rmd:
                repositories.add(rmd["repository_uuidv4"])
            try:
                disp = decode_disposition(rmd)
                dep = dependencies(disp)
                dispositions.update(dep.dispositions)
                mapping_claims.update(dep.mapping_claims)
                if hasattr(disp, "claim_key"):
                    mapping_claims.add(disp.claim_key)
                if getattr(disp, "replacement_claim_key", None):
                    mapping_claims.add(disp.replacement_claim_key)
                if hasattr(disp, "disposition_key"):
                    dispositions.add(disp.disposition_key)
                resources.update(dep.resources)
                repositories.update(dep.repositories)
                provider_registrations.update(dep.provider_registrations)
            except Exception:
                pass

        for rel in context_data.get("resource_relations", ()):
            if (
                "service_instance_uuidv4" in rel
                and "resource_kind" in rel
                and "provider_resource_id" in rel
            ):
                resources.add(
                    ResourceKey(
                        rel["service_instance_uuidv4"],
                        rel["resource_kind"],
                        rel["provider_resource_id"],
                    )
                )
            members_json = rel.get("members_json")
            if members_json:
                try:
                    for m in json.loads(members_json):
                        resources.add(ResourceKey(*m))
                except Exception:
                    pass

        for ref in context_data.get("core_references", ()):
            fmt = ref.get("object_format")
            object_oid = ref.get("object_oid")
            if fmt and object_oid:
                object_oids.add(OID(fmt, object_oid))

        return DependencySet(
            resources=resources,
            repositories=repositories,
            sources=sources,
            source_repository_pairs=source_repository_pairs,
            mapping_claims=mapping_claims,
            dispositions=dispositions,
            provider_registrations=provider_registrations,
            object_oids=object_oids,
        )

    @staticmethod
    def _validate_receiver_authority(
        auth, adm, context_data: dict[str, Any] | None
    ) -> None:
        from repo_catalog.domain.context_admission import (
            AdmissionRefused,
            ContextAdmissionService,
        )

        if auth is None or adm is None:
            raise AdmissionRefused("PERMISSION_DENIED")
        if not isinstance(auth, ContextAdmissionService):
            raise AdmissionRefused("PERMISSION_DENIED")
        auth.validate_context(adm)
        policy = getattr(auth, "_policy", None)
        if policy is None or not callable(getattr(policy, "lease", None)):
            raise AdmissionRefused("PERMISSION_DENIED")

        package_deps = ExchangeService._extract_context_dependencies(context_data)
        if hasattr(policy, "grants") and policy.grants is None:
            if (
                package_deps.resources
                or package_deps.sources
                or package_deps.provider_registrations
                or package_deps.mapping_claims
                or package_deps.dispositions
            ):
                raise AdmissionRefused("PERMISSION_DENIED")

        with policy.lease(adm.principal, adm.operation, package_deps) as lease:
            if not callable(getattr(lease, "check_current", None)):
                raise AdmissionRefused("PERMISSION_DENIED")
            lease.check_current()

    def _import_package(
        self,
        raw_package,
        *,
        work: WorkBudget,
        ledger,
        request,
        permitted,
        selection,
        cut,
        authorization=None,
        admission=None,
        grants=None,
    ) -> ExchangeImportReport:
        self._check_stop()
        package = raw_package
        digest = package.digest_sha256
        repo_uuid, instance_uuid = self._store_identity()

        active_work = work

        want_core = (
            package.core is not None
            and package.selection_scope.include_core
            and selection.include_core
            and self._has_core()
        )
        want_context = (
            package.context is not None
            and package.selection_scope.include_context
            and selection.include_context
            and self._has_context()
        )

        # Validate every section, including units later withheld by permission.
        with account_verification(active_work):
            from repo_catalog.domain.exchange_rows import validate_replay_consistency

            validate_replay_consistency(package.core, package.context)
            if package.core is not None:
                self._prevalidate_core_section(package.core, active_work)
                self._import_core_units(CorePreflight(), package.core, active_work)
            if package.context is not None:
                if want_context:
                    from repo_catalog.domain.selective_exchange import (
                        preflight_i2_context,
                    )

                    preflight_i2_context(package.context)
                self._prevalidate_context_section(package.context)
                validate_context(package.context)
        cut("after_preflight")
        core_data = copy.deepcopy(package.core)
        context_data = copy.deepcopy(package.context)
        with account_verification(active_work):
            omissions = filter_sections(
                core_data, context_data, package.selection_scope, permitted=permitted
            )
            if selection != package.selection_scope:
                omissions.extend(
                    filter_sections(
                        core_data, context_data, selection, permitted=permitted
                    )
                )
        # Fence the receiver-selected atomic unit before dependency rewriting,
        # package replay/binding, or either authority's effects.
        if want_context and context_data is not None:
            from repo_catalog.domain.selective_exchange import preflight_i2_context

            preflight_i2_context(context_data)
        with account_verification(active_work):
            limited, _ = bound_sections(
                core_data, context_data, selection, work=active_work
            )
            omissions.extend(limited)
            omissions.extend(
                filter_sections(core_data, context_data, selection, permitted=permitted)
            )
        # Nothing outside the receiver permission can enter even when it is a
        # required dependency of an otherwise selected unit.
        self._receive_selection = selection
        self._dependency_rows = 0
        if core_data is not None and self._has_core():
            omissions.extend(
                self._preflight_ref_receiver(core_data, active_work, selection)
            )
        read_bound = 4 * max(10000, selection.max_units)
        active_work.require("metadata_units", read_bound)
        try:
            if core_data is not None and any(core_data.values()) and self._has_core():
                omissions.extend(self._core_dependencies(core_data))
            if (
                context_data is not None
                and any(context_data.values())
                and self._has_context()
            ):
                omissions.extend(self._context_dependencies(context_data))
            active_work.charge("metadata_units", self._dependency_rows)
        except BaseException:
            active_work.abandon("metadata_units")
            raise

        with catalog_completion(self.directory):
            self._check_stop()
            ledger.work_ledger.bind_exchange_package(
                request,
                package.sender_catalog_instance_uuidv4,
                package.package_id,
                digest,
            )
        cut("after_package_binding")
        prior_receipt = None

        core_stats: dict[str, Any] = {
            "admitted_core_objects": 0,
            "admitted_retained_metadata": 0,
            "admitted_note_roles": 0,
            "admitted_retained_notes": 0,
            "ignored_unverified_intrinsic_claims": 0,
            "ignored_unverified_intrinsic_groups": 0,
            "new_rows": 0,
        }
        ctx_stats: dict[str, Any] = {
            "admitted_context_resources": 0,
            "linked_core_references": 0,
            "pending_core_references": 0,
            "new_rows": 0,
        }

        checkpoint_written = {"core": False, "context": False}

        def checkpoint(point):
            cut(point)
            if point in ("after_core_commit", "after_context_commit"):
                stage = "core" if point == "after_core_commit" else "context"
                cut("before_" + stage + "_checkpoint")
                stats = core_stats if stage == "core" else ctx_stats
                ledger.work_ledger.set_progress_once(
                    request,
                    encode(
                        [
                            "adr0030-stage",
                            package.sender_catalog_instance_uuidv4,
                            package.package_id,
                            digest,
                            work.attempt_uuidv4,
                            stage,
                        ]
                    ),
                    dict(stats),
                )
                checkpoint_written[stage] = True
                cut("after_" + stage + "_checkpoint")

        if self._has_core() and self._has_context() and (want_core or want_context):
            auth = authorization if authorization is not None else self.authorization
            adm = admission if admission is not None else self.admission
            active_grants = grants if grants is not None else self.grants
            if want_context:
                admit_selection = replace(selection, include_core=True)
                if auth is None or adm is None:
                    if not permitted and active_grants is None:
                        from repo_catalog.domain.context_admission import (
                            AdmissionRefused,
                        )

                        raise AdmissionRefused("PERMISSION_DENIED")
                    from repo_catalog.domain.context_admission import (
                        create_local_admission_service,
                    )

                    auth, adm, _ = create_local_admission_service(
                        "exchange_import",
                        grants=active_grants,
                        permitted_repositories=frozenset(permitted),
                        selection=admit_selection,
                    )
                self._validate_receiver_authority(auth, adm, context_data)
            coordinator = PairCoordinator(self.directory, authorization=auth)

            def _core_unit(core_tx: AdmissionTransaction) -> None:
                if want_core and package.core is not None:
                    with GitCore.for_transaction(core_tx) as core_cap:  # type: ignore[arg-type]
                        core_stats.update(
                            self._import_core_into(core_cap, core_data, active_work)
                        )

            def _context_unit(context_tx: AdmissionTransaction) -> None:
                if want_context and package.context is not None:
                    from repo_catalog.adapters.sqlite.production_context import Context

                    with Context.for_transaction(
                        context_tx,
                        self.directory,
                        authorization=auth,
                        admission=adm,
                    ) as ctx_cap:
                        ctx_stats.update(
                            self._import_context_accounted(
                                ctx_cap,
                                context_data,
                                self._core_validator_on_disk(),
                                active_work,
                            )
                        )

            try:
                coordinator.admit(
                    _core_unit,
                    _context_unit,
                    cut=checkpoint,
                    authorization=auth,
                    admission=adm,
                )
            except AdmissionFailure as error:
                ledger.work_ledger.set_progress_once(
                    request,
                    encode(
                        [
                            "adr0030-partial",
                            package.sender_catalog_instance_uuidv4,
                            package.package_id,
                            digest,
                            work.attempt_uuidv4,
                        ]
                    ),
                    {
                        "core_committed": error.outcome.core_committed,
                        "context_committed": error.outcome.context_committed,
                    },
                )
                raise
        elif want_core and core_data is not None:
            with (
                catalog_gate(self.directory, exclusive=True),
                closing(connect(self.directory / "core.sqlite3", "core")) as db,
            ):
                db.execute("BEGIN IMMEDIATE")
                try:
                    with GitCore.for_transaction(AdmissionTransaction(db)) as core_cap:
                        core_stats.update(
                            self._import_core_into(core_cap, core_data, active_work)
                        )
                    db.set_authorizer(None)
                    checkpoint("before_core_commit")
                    with catalog_completion(self.directory):
                        db.commit()
                    checkpoint("after_core_commit")
                except BaseException:
                    db.set_authorizer(None)
                    db.rollback()
                    raise
        elif want_context and context_data is not None:
            from repo_catalog.adapters.sqlite.production_context import Context

            auth = authorization if authorization is not None else self.authorization
            adm = admission if admission is not None else self.admission
            active_grants = grants if grants is not None else self.grants
            admit_selection = replace(selection, include_core=True)
            if auth is None or adm is None:
                if not permitted and active_grants is None:
                    from repo_catalog.domain.context_admission import (
                        AdmissionRefused,
                    )

                    raise AdmissionRefused("PERMISSION_DENIED")
                from repo_catalog.domain.context_admission import (
                    create_local_admission_service,
                )

                auth, adm, _ = create_local_admission_service(
                    "exchange_import",
                    grants=active_grants,
                    permitted_repositories=frozenset(permitted),
                    selection=admit_selection,
                )
            self._validate_receiver_authority(auth, adm, context_data)
            with Context.transaction(
                self.directory, authorization=auth, admission=adm
            ) as ctx_cap:
                ctx_stats.update(
                    self._import_context_accounted(
                        ctx_cap,
                        context_data,
                        self._core_validator_on_disk(),
                        active_work,
                    )
                )
                checkpoint("during_context")
            checkpoint("after_context_commit")

        has_payload = bool(
            (want_core and package.core and any(package.core.values()))
            or (want_context and package.context and any(package.context.values()))
        )
        is_replay = prior_receipt is not None or (
            has_payload and core_stats["new_rows"] == 0 and ctx_stats["new_rows"] == 0
        )

        omissions.extend(ctx_stats.get("missing_refs", ()))
        report = ExchangeImportReport(
            package_id=package.package_id,
            package_digest_sha256=digest,
            sender_catalog_instance_uuidv4=package.sender_catalog_instance_uuidv4,
            repository_uuidv4=package.repository_uuidv4,
            core_imported=want_core,
            context_imported=want_context,
            idempotent_replay=is_replay,
            admitted_core_objects=core_stats["admitted_core_objects"],
            admitted_retained_metadata=core_stats["admitted_retained_metadata"],
            admitted_note_roles=core_stats["admitted_note_roles"],
            admitted_retained_notes=core_stats["admitted_retained_notes"],
            ignored_unverified_intrinsic_claims=core_stats[
                "ignored_unverified_intrinsic_claims"
            ],
            ignored_unverified_intrinsic_groups=core_stats[
                "ignored_unverified_intrinsic_groups"
            ],
            admitted_context_resources=ctx_stats["admitted_context_resources"],
            linked_core_references=ctx_stats["linked_core_references"],
            pending_core_references=ctx_stats["pending_core_references"],
            omissions=tuple(omissions),
            core_checkpoint=checkpoint_written["core"],
            context_checkpoint=checkpoint_written["context"],
        )

        ledger.work_ledger.set_progress_once(
            request,
            encode(
                [
                    "adr0030-summary",
                    package.sender_catalog_instance_uuidv4,
                    package.package_id,
                    digest,
                    work.attempt_uuidv4,
                ]
            ),
            {"core": core_stats, "context": ctx_stats, "omitted_units": len(omissions)},
        )
        cut("after_summary")

        return report

    def _preflight_ref_receiver(self, data, work, selection):
        """Reject immutable rebindings before either paired authority commits."""
        from repo_catalog.application.ref_reconstruction import decode_ref_units
        from repo_catalog.domain.ref_observation import RefObservationKey

        omissions = []
        stale_terminals = set()
        with account_verification(work):
            observations, claims, events, links = decode_ref_units(data)
            claims_by_subject = {}
            for identity, claim in claims.items():
                _performed("metadata_units", 1)
                claims_by_subject.setdefault(identity[:2], []).append(claim)
            with closing(
                GitCore(
                    self.directory / "core.sqlite3", read_limits=self._read_limits()
                )
            ) as core:
                for key, incoming in observations.items():
                    try:
                        current = core.ref_observation(
                            RefObservationKey(*key),
                            work,
                            max_claims=max(1, selection.max_units),
                            max_bytes=max(1, selection.max_bytes),
                        )
                    except CoreFailure as error:
                        if error.code == "OBSERVATION_UNAVAILABLE":
                            continue
                        raise
                    if current.ref_observation != incoming:
                        raise ExchangeError(
                            "IMMUTABLE_REPLAY_CONFLICT", ["core", "ref_observations"]
                        )
                    by_coordinate = {
                        existing.provenance.key[:3]: existing
                        for existing in current.claims
                    }
                    for claim in claims_by_subject.get(key, ()):
                        _performed("metadata_units", 1)
                        previous = by_coordinate.get(claim.provenance.key[:3])
                        if previous is not None and previous != claim:
                            raise ExchangeError(
                                "IMMUTABLE_REPLAY_CONFLICT",
                                ["core", "ref_observation_claims"],
                            )
                for key, incoming in events.items():
                    try:
                        current = core.ref_enumeration(
                            *key,
                            work,
                            max_links=max(1, selection.max_units),
                            max_bytes=max(1, selection.max_bytes),
                        )
                    except CoreFailure as error:
                        if error.code == "ENUMERATION_UNAVAILABLE":
                            continue
                        raise
                    bucket = links.get(key, {})
                    expected = tuple(bucket[position] for position in sorted(bucket))
                    if current.event != incoming or current.links != expected:
                        raise ExchangeError(
                            "IMMUTABLE_REPLAY_CONFLICT",
                            ["core", "ref_enumeration_observations"],
                        )
                for row in data["coverage_claims"]:
                    if row["owner_kind"] != "ref_observation":
                        continue
                    _performed("metadata_units", 1)
                    _performed("input_bytes", len(row["owner_coordinates_json"]))
                    scope = CoreCoverageScope(
                        row["owner_kind"],
                        tuple(json.loads(row["owner_coordinates_json"])),
                    )
                    current = core.coverage(
                        scope,
                        work,
                        max_proofs=max(1, selection.max_units),
                        max_claims=max(1, selection.max_units),
                        max_bytes=max(1, selection.max_bytes),
                    )
                    if (
                        current.observed_at_us is not None
                        and current.observed_at_us > row["observed_at_us"]
                    ):
                        terminal = (
                            row["owner_kind"],
                            row["owner_coordinates_json"],
                            row["observed_at_us"],
                            row["coverage_state"],
                        )
                        stale_terminals.add(terminal)
                        omissions.append(
                            {
                                "section": "coverage_claims",
                                "unit": list(terminal),
                                "reason": "stale_coverage_claim",
                            }
                        )
        if stale_terminals:
            for section in ("coverage_claims", "ref_coverage_proofs"):
                kept = []
                for row in data[section]:
                    with account_verification(work):
                        _performed("metadata_units", 1)
                    terminal = (
                        row["owner_kind"],
                        row["owner_coordinates_json"],
                        row["observed_at_us"],
                        row["coverage_state"],
                    )
                    if terminal not in stale_terminals:
                        kept.append(row)
                data[section] = kept
        return omissions

    def _core_dependencies(self, data):
        omissions = []
        with closing(
            GitCore(self.directory / "core.sqlite3", read_limits=self._read_limits())
        ) as core:
            # These I1 UNIQUE keys deliberately exclude the immutable assertion
            # payload. Check them before either domain commits, not only the PK.
            for section, keys, payload in (
                (
                    "repository_claims",
                    ("repository_uuidv4", "field", "provenance_json"),
                    ("value_json",),
                ),
                (
                    "scalar_claims",
                    ("object_format", "object_oid", "field", "provenance_json"),
                    ("value_json",),
                ),
                (
                    "relation_groups",
                    (
                        "object_format",
                        "object_oid",
                        "relation",
                        "scope",
                        "provenance_json",
                    ),
                    ("status", "membership_json"),
                ),
            ):

                def column(name):
                    return name.removesuffix("_json")

                for row in data[section]:
                    if row.get("authority", "reported") != "reported":
                        continue
                    found = core.sql(
                        "SELECT "
                        + ",".join((column(k) for k in payload))
                        + " FROM "
                        + section
                        + " WHERE "
                        + " AND ".join((column(k) + "=?" for k in keys)),
                        tuple((row[k] for k in keys)),
                    )
                    if found:
                        self._dependency_rows += 1
                        if tuple(found[0]) != tuple((row[k] for k in payload)):
                            raise ExchangeError(
                                "IMMUTABLE_REPLAY_CONFLICT", ["core", section]
                            )
            repos = {
                r[0] for r in core.sql("SELECT repository_uuidv4 FROM repositories")
            }
            for row in data["git_observations"]:
                existing = core.sql(
                    "SELECT value FROM git_observations WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND repository_uuidv4=? AND kind=? AND scope=? AND provenance=?",
                    (
                        row["capture_origin_uuidv4"],
                        row["capture_uuidv4"],
                        row["repository_uuidv4"],
                        row["kind"],
                        row["scope_json"],
                        row["provenance_json"],
                    ),
                )
                if existing:
                    self._dependency_rows += 1
                    if existing[0][0] != row["value_json"]:
                        raise ExchangeError(
                            "IMMUTABLE_REPLAY_CONFLICT", ["core", "git_observations"]
                        )
            oids = {
                tuple(r)
                for r in core.sql("SELECT object_format,object_oid FROM git_objects")
            }
        self._dependency_rows += len(repos) + len(oids)
        repos.update(r["repository_uuidv4"] for r in data["repositories"])
        oids.update((r["object_format"], r["object_oid"]) for r in data["git_objects"])

        def keep(key, predicate):
            kept = []
            for index, row in enumerate(data[key]):
                if predicate(row):
                    kept.append(row)
                else:
                    omissions.append(
                        {
                            "section": key,
                            "unit_index": index,
                            "reason": "missing_required_dependency",
                        }
                    )
            data[key] = kept

        for key in ("repository_claims", "git_observations"):
            keep(key, lambda r: r["repository_uuidv4"] in repos)
        keep("ref_observations", lambda r: r["repository_uuidv4"] in repos)
        ref_keys = {
            (r["observation_origin_uuidv4"], r["ref_observation_uuidv7"])
            for r in data["ref_observations"]
        }
        keep(
            "ref_observation_claims",
            lambda r: (
                (r["observation_origin_uuidv4"], r["ref_observation_uuidv7"])
                in ref_keys
                and all(
                    r[field] is None or tuple(r[field]) in oids
                    for field in (
                        "direct_target_object_oid",
                        "resolved_target_object_oid",
                        "peeled_target_object_oid",
                        "root_object_oid",
                    )
                )
            ),
        )
        ref_claims = {
            (
                r["observation_origin_uuidv4"],
                r["ref_observation_uuidv7"],
                r["provenance_json"],
            )
            for r in data["ref_observation_claims"]
        }

        def mapping_owner_available(row):
            return (
                row["observation_origin_uuidv4"],
                row["ref_observation_uuidv7"],
                row["ref_claim_provenance_json"],
            ) in ref_claims

        for key in (
            "notes_mapping_claims",
            "notes_mapping_evidence",
            "ref_retained_notes",
        ):
            keep(
                key,
                lambda r: (
                    mapping_owner_available(r)
                    and all(
                        (r["object_format"], object_oid) in oids
                        for object_oid in (
                            r["root_object_oid"],
                            r["annotated_object_oid"],
                            r["note_object_oid"],
                        )
                    )
                ),
            )
        keep(
            "notes_mapping_groups",
            lambda r: (
                mapping_owner_available(r)
                and (r["object_format"], r["root_object_oid"]) in oids
                and all(
                    (r["object_format"], object_oid) in oids
                    for target, note, _ in json.loads(r["membership_json"])
                    for object_oid in (target, note)
                )
            ),
        )
        event_links = {}
        for row in data["ref_enumeration_links"]:
            event_links.setdefault(
                (row["enumeration_origin_uuidv4"], row["enumeration_uuidv7"]), []
            ).append(row)
        keep(
            "ref_enumeration_observations",
            lambda r: (
                r["repository_uuidv4"] in repos
                and len(
                    event_links.get(
                        (r["observation_origin_uuidv4"], r["enumeration_uuidv7"]), ()
                    )
                )
                == r["link_count"]
                and all(
                    (
                        link["observation_origin_uuidv4"],
                        link["ref_observation_uuidv7"],
                        link["claim_provenance_json"],
                    )
                    in ref_claims
                    for link in event_links.get(
                        (r["observation_origin_uuidv4"], r["enumeration_uuidv7"]), ()
                    )
                )
            ),
        )
        event_keys = {
            (r["observation_origin_uuidv4"], r["enumeration_uuidv7"])
            for r in data["ref_enumeration_observations"]
        }
        keep(
            "ref_enumeration_links",
            lambda r: (
                (r["enumeration_origin_uuidv4"], r["enumeration_uuidv7"]) in event_keys
            ),
        )

        def scope_available(r):
            coordinates = json.loads(r["owner_coordinates_json"])
            if r["owner_kind"] == "repository":
                return coordinates[0] in repos
            if r["owner_kind"] == "ref_observation":
                return tuple(coordinates[:2]) in ref_keys
            return tuple(coordinates[:2]) in oids

        for key in ("coverage_scopes", "coverage_claims", "coverage_proofs"):
            keep(key, scope_available)
        coverage_keys = {
            (
                r["owner_kind"],
                r["owner_coordinates_json"],
                r["observed_at_us"],
                r["coverage_state"],
            )
            for r in data["coverage_claims"]
        }
        mapping_groups = {encode(row) for row in data["notes_mapping_groups"]}
        keep(
            "ref_coverage_proofs",
            lambda r: (
                (
                    r["owner_kind"],
                    r["owner_coordinates_json"],
                    r["observed_at_us"],
                    r["coverage_state"],
                )
                in coverage_keys
                and r["group_json"] in mapping_groups
            ),
        )
        return omissions

    def _context_dependencies(self, data):
        """Classify missing dependencies without registering synthetic parents."""
        from repo_catalog.adapters.sqlite.production_context import Context
        from repo_catalog.domain.p1_context import FieldClock, ResourceKey, canonical
        from repo_catalog.domain.selective_exchange import resource

        omissions = []
        original_terminals = [
            ("source_inventory", r) for r in data["source_inventories"]
        ] + [("collection", r) for r in data["collections"]]
        with Context.snapshot(self.directory, read_limits=self._read_limits()) as ctx:
            for row in data["collections"]:
                prior = ctx.db.execute(
                    "SELECT scope_json FROM collections WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND collection_kind=? AND provenance_json=?",
                    (
                        *resource(row).coordinates(),
                        row["collection_kind"],
                        row["provenance_json"],
                    ),
                ).fetchone()
                if prior is not None:
                    self._dependency_rows += 1
                    if prior[0] != row["scope_json"]:
                        raise ExchangeError(
                            "IMMUTABLE_REPLAY_CONFLICT", ["context", "collections"]
                        )
            for section, table, key, immutable in (
                ("providers", "providers", "service_instance_uuidv4", "provider_kind"),
                (
                    "sources",
                    "sources",
                    "source_registration_uuidv4",
                    "service_instance_uuidv4",
                ),
            ):
                for row in data[section]:
                    prior = ctx.db.execute(
                        f"SELECT {immutable} FROM {table} WHERE {key}=?", (row[key],)
                    ).fetchone()
                    if prior is not None:
                        self._dependency_rows += 1
                        if prior[0] != row[immutable]:
                            raise ExchangeError("IDENTITY_REBIND", ["context", section])
            providers = {
                r[0]
                for r in ctx.db.execute("SELECT service_instance_uuidv4 FROM providers")
            }
            source_services = {
                r[0]: r[1]
                for r in ctx.db.execute(
                    "SELECT source_registration_uuidv4,service_instance_uuidv4 FROM sources"
                )
            }
            sources = set(source_services)
            source_pairs = {
                tuple(row)
                for row in ctx.db.execute(
                    "SELECT source_registration_uuidv4,repository_uuidv4 FROM source_repositories"
                ).fetchall()
            }
            collection_keys = {
                tuple(row)
                for row in ctx.db.execute(
                    "SELECT service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,provenance_json FROM collections"
                ).fetchall()
            }
            resources = {
                ResourceKey(*r)
                for r in ctx.db.execute(
                    "SELECT service_instance_uuidv4,resource_kind,provider_resource_id FROM resources"
                )
            }
            repos = {
                r[0]
                for r in ctx.db.execute(
                    "SELECT repository_uuidv4 FROM repository_context"
                )
            }
            columns = (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
                "relation_kind",
                "target_json",
                "clock_json",
                "provenance_json",
                "observed_at_us",
                "event_report_members_json",
                "event_report_scope_json",
            )
            stored_relations = [
                decode_relation(dict(zip(columns, row)))
                for row in ctx.db.execute(
                    "SELECT "
                    + ",".join(columns)
                    + " FROM resource_repository_relations"
                )
            ]
            original_times = {r.claim_key: r.observed_at_us for r in stored_relations}
            mapping_keys = set(original_times)
            for row in data["repository_mapping_dispositions"]:
                disposition = decode_disposition(row)
                found = ctx.db.execute(
                    "SELECT observed_at_us,replacement_clock_json,replacement_target_json,replacement_provenance_json FROM repository_mapping_dispositions WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND relation_kind=? AND claim_clock_json=? AND claim_target_json=? AND claim_provenance_json=? AND disposition_kind=? AND disposition_clock_json=? AND disposition_provenance_json=?",
                    disposition.key_coordinates(),
                ).fetchone()
                if found is not None:
                    self._dependency_rows += 1
                    if tuple(found) != (
                        disposition.observed_at_us,
                        disposition.replacement_clock_json,
                        disposition.replacement_target_json,
                        disposition.replacement_provenance_json,
                    ):
                        raise ExchangeError(
                            "IMMUTABLE_REPLAY_CONFLICT",
                            ["context", "repository_mapping_dispositions"],
                        )
            for report in transfer_reports(data):
                existing_endpoints = {
                    (r.relation_kind, r.target_json, r.observed_at_us)
                    for r in stored_relations
                    if r.resource == report.event_resource
                    and r.clock == report.clock
                    and r.provenance_json == report.provenance_json
                    and r.relation_kind.startswith("transfer_")
                }
                incoming_endpoints = {
                    (r.relation_kind, r.target_json, r.observed_at_us)
                    for r in (*report.from_relations, *report.to_relations)
                }
                if existing_endpoints and existing_endpoints != incoming_endpoints:
                    raise ExchangeError(
                        "IMMUTABLE_REPLAY_CONFLICT",
                        ["context", "transfer_event_report"],
                    )
                found = ctx.db.execute(
                    "SELECT members_json,scope_json,observed_at_us FROM resource_relations WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND relation_kind='transfer_event_report' AND provenance_json=?",
                    (*report.event_resource.coordinates(), report.provenance_json),
                ).fetchall()
                self._dependency_rows += len(found)
                for members, stored_scope, observed_at in found:
                    if canonical(
                        json.loads(stored_scope).get("clock")
                    ) == report.clock.encode() and (
                        members != report.members_json
                        or stored_scope != report.scope_json
                        or observed_at != report.observed_at_us
                    ):
                        raise ExchangeError(
                            "IMMUTABLE_REPLAY_CONFLICT",
                            ["context", "transfer_event_report"],
                        )
            for row in data["resource_repository_relations"]:
                relation = decode_relation(row)
                if (
                    relation.claim_key in original_times
                    and original_times[relation.claim_key] != relation.observed_at_us
                ):
                    raise ExchangeError(
                        "IMMUTABLE_REPLAY_CONFLICT",
                        ["context", "resource_repository_relations"],
                    )
            # Exact original field/relation timestamps remain immutable even for
            # historical claims; a changed payload is not a fresh observation.
            for row in data["field_candidates"]:
                found = ctx.db.execute(
                    "SELECT observed_at_us FROM field_candidates WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND field_name=? AND clock_json=? AND value_json=? AND provenance_json=?",
                    (
                        *resource(row).coordinates(),
                        row["field_name"],
                        FieldClock(row["clock_domain"], row["clock_ts_us"]).encode(),
                        row["value_json"],
                        row["provenance_json"],
                    ),
                ).fetchone()
                if found is not None:
                    self._dependency_rows += 1
                    if found[0] != row["observed_at_us"]:
                        raise ExchangeError(
                            "IMMUTABLE_REPLAY_CONFLICT", ["context", "field_candidates"]
                        )
            for row in data["resource_relations"]:
                found = ctx.db.execute(
                    "SELECT observed_at_us FROM resource_relations WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND relation_kind=? AND members_json=? AND provenance_json=? AND scope_json=?",
                    (
                        *resource(row).coordinates(),
                        row["relation_kind"],
                        row["members_json"],
                        row["provenance_json"],
                        row["scope_json"],
                    ),
                ).fetchone()
                if found is not None:
                    self._dependency_rows += 1
                    if found[0] != row["observed_at_us"]:
                        raise ExchangeError(
                            "IMMUTABLE_REPLAY_CONFLICT",
                            ["context", "resource_relations"],
                        )

        self._dependency_rows += (
            len(providers)
            + len(sources)
            + len(resources)
            + len(repos)
            + len(mapping_keys)
            + len(source_pairs)
            + len(collection_keys)
        )

        def keep(key, predicate):
            good = []
            for row in data[key]:
                if predicate(row):
                    good.append(row)
                else:
                    omissions.append(
                        {
                            "section": key,
                            "unit": row,
                            "reason": "missing_required_dependency",
                        }
                    )
            data[key] = good

        providers.update(r["service_instance_uuidv4"] for r in data["providers"])
        repos.update(r["repository_uuidv4"] for r in data["repositories"])
        keep("sources", lambda r: r["service_instance_uuidv4"] in providers)
        sources.update(r["source_registration_uuidv4"] for r in data["sources"])
        source_services.update(
            (r["source_registration_uuidv4"], r["service_instance_uuidv4"])
            for r in data["sources"]
        )
        validate_context_bindings(data, source_services)
        pending = list(data["resources"])
        data["resources"] = []
        for row in pending:
            rk = resource(row)
            if rk.service_instance_uuidv4 not in providers:
                omissions.append(
                    {
                        "section": "resources",
                        "unit": row,
                        "reason": "missing_parent_or_provider",
                    }
                )
                continue
            if rk.resource_kind in ("review", "thread", "document", "comment"):
                from repo_catalog.domain.resource_identification import (
                    ResourceIdentification,
                )

                try:
                    ResourceIdentification.from_wire(row)
                except Exception:
                    omissions.append(
                        {
                            "section": "resources",
                            "unit": row,
                            "reason": "missing_required_dependency",
                        }
                    )
                    continue
            data["resources"].append(row)
            resources.add(rk)
        keep(
            "source_repositories",
            lambda r: (
                r["source_registration_uuidv4"] in sources
                and r["repository_uuidv4"] in repos
            ),
        )
        keep(
            "source_inventories",
            lambda r: (
                r["source_registration_uuidv4"] in sources
                and set(json.loads(r["members_json"])).issubset(repos)
            ),
        )
        reports = transfer_reports(data)
        denied = {
            report.report_key
            for report in reports
            if report.event_resource not in resources
            or any(
                p is not None and p not in resources
                for p in (
                    report.from_provider_repository,
                    report.to_provider_repository,
                )
            )
            or any(
                r.target_repository_uuidv4 is not None
                and r.target_repository_uuidv4 not in repos
                for r in (*report.from_relations, *report.to_relations)
            )
        }
        keep(
            "resource_repository_relations",
            lambda r: (
                resource(r) in resources
                and (
                    decode_relation(r).target_repository_uuidv4 is None
                    or decode_relation(r).target_repository_uuidv4 in repos
                )
                and (
                    not r["relation_kind"].startswith("transfer_")
                    or all(
                        not (
                            key.event_resource == resource(r)
                            and key.clock == FieldClock.from_json(r["clock_json"])
                            and key.provenance_json == r["provenance_json"]
                        )
                        for key in denied
                    )
                )
            ),
        )
        mapping_keys.update(
            decode_relation(r).claim_key for r in data["resource_repository_relations"]
        )
        unsupported = {
            decode_relation(r).claim_key
            for r in data["resource_repository_relations"]
            if decode_relation(r).embedded_support is not None
            and not all(
                k in mapping_keys
                for k in decode_relation(r).embedded_support.supporting_claims
            )
        }
        unsupported_reports = {
            report.report_key
            for report in reports
            if any(
                r.claim_key in unsupported
                for r in (*report.from_relations, *report.to_relations)
            )
        }
        denied.update(unsupported_reports)
        keep(
            "resource_repository_relations",
            lambda r: (
                decode_relation(r).claim_key not in unsupported
                and (
                    not r["relation_kind"].startswith("transfer_")
                    or not any(
                        k.event_resource == resource(r)
                        and k.clock == FieldClock.from_json(r["clock_json"])
                        and k.provenance_json == r["provenance_json"]
                        for k in unsupported_reports
                    )
                )
            ),
        )
        keep(
            "repository_mapping_dispositions",
            lambda r: (
                decode_disposition(r).claim_key in mapping_keys
                and (
                    decode_disposition(r).replacement_claim_key is None
                    or decode_disposition(r).replacement_claim_key in mapping_keys
                )
            ),
        )
        for key in ("resource_relations", "collections"):
            keep(
                key,
                lambda r: (
                    resource(r) in resources
                    and (
                        key != "collections"
                        or not isinstance(json.loads(r["scope_json"]), dict)
                        or "source_registration_uuidv4"
                        not in json.loads(r["scope_json"])
                        or json.loads(r["scope_json"])["source_registration_uuidv4"]
                        in sources
                    )
                    and all(
                        ResourceKey(*m) in resources
                        for m in json.loads(r["members_json"])
                    )
                    and (
                        r.get("relation_kind") != "transfer_event_report"
                        or all(
                            not (
                                k.event_resource == resource(r)
                                and k.provenance_json == r["provenance_json"]
                                and json.loads(k.clock.encode())
                                == json.loads(r["scope_json"])["clock"]
                            )
                            for k in denied
                        )
                    )
                ),
            )
        for key in ("field_candidates", "core_references"):
            keep(key, lambda r: resource(r) in resources)
        # Omit the entire associated Coverage assertion if a collection or
        # inventory unit is missing. A terminal is not reconstructed from rows.
        omissions.extend(preserve_context_coverage(data, original_terminals))

        source_pairs.update(
            (r["source_registration_uuidv4"], r["repository_uuidv4"])
            for r in data["source_repositories"]
        )
        collection_keys.update(
            (*resource(r).coordinates(), r["collection_kind"], r["provenance_json"])
            for r in data["collections"]
        )

        def scope_available(r):
            coords = json.loads(r["owner_coordinates_json"])
            if r["owner_kind"] == "source":
                return tuple(coords[:2]) in source_pairs
            if r["owner_kind"] == "source_inventory":
                return coords[0] in sources
            if r["owner_kind"] == "collection":
                return tuple(coords[:5]) in collection_keys
            if r["owner_kind"] == "repository":
                return coords[0] in repos
            return ResourceKey(*coords[:3]) in resources

        keep("coverage_scopes", scope_available)
        keep("coverage_claims", scope_available)
        keep("coverage_proofs", scope_available)
        return omissions

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

    def _prevalidate_core_section(
        self,
        core_data: dict[str, list[dict[str, Any]]],
        work: WorkBudget,
    ) -> None:
        # Validate all direct repository values before any Core unit is committed.
        for row in core_data["repository_claims"]:
            claim = RepositoryClaim(
                row["repository_uuidv4"],
                row["field"],
                json.loads(row["value_json"]),
                Provenance(*json.loads(row["provenance_json"])),
            )
            if claim.key[2] != row["value_json"]:
                raise ExchangeError(
                    "REPOSITORY_CLAIM", "core", "canonical value required"
                )

        for meta in core_data["retained_metadata"]:
            object_oid = OID(meta["object_format"], meta["object_oid"])
            native_type = meta["native_type"]
            if native_type == "blob":
                raise CoreFailure(
                    "RETENTION_PURPOSE",
                    object_oid,
                    "ordinary file blob bodies are excluded from retained_metadata",
                )
            try:
                body = bytes.fromhex(meta["body_hex"])
            except (ValueError, TypeError) as exc:
                raise CoreFailure(
                    "NATIVE_INTEGRITY",
                    object_oid,
                    "invalid hex body in retained_metadata",
                ) from exc
            native = NativeObject(
                object_oid,
                native_type,
                body,
                meta["size"],
                str(meta["digest_sha256"]),
            )
            native.validate()
            parse_metadata(object_oid.object_format, native_type, body)

    def _prevalidate_context_section(
        self,
        ctx_data: dict[str, list[dict[str, Any]]],
    ) -> None:
        from repo_catalog.domain.time import validate_observation_us

        provider_time_fields = {
            "created_at_us",
            "updated_at_us",
            "pushed_at_us",
            "closed_at_us",
            "merged_at_us",
            "submitted_at_us",
        }
        for candidate in ctx_data["field_candidates"]:
            if candidate["field_name"] in provider_time_fields:
                validate_observation_us(json.loads(candidate["value_json"]))
        package_digests: set[str] = set()
        for tb in ctx_data["text_bodies"]:
            sha256_hex = tb.get("sha256")
            text_val = tb.get("text_value")
            if not isinstance(sha256_hex, str) or not isinstance(text_val, str):
                raise ExchangeError(
                    "MALFORMED_TEXT_BODY",
                    sha256_hex,
                    "sha256 and text_value strings required",
                )
            _performed("verification_bytes", len(text_val.encode("utf-8")))
            actual = hashlib.sha256(text_val.encode("utf-8")).hexdigest()
            if actual != sha256_hex:
                raise ExchangeError(
                    "TEXT_DIGEST_MISMATCH",
                    sha256_hex,
                    f"computed sha256 {actual} != declared {sha256_hex}",
                )
            package_digests.add(sha256_hex)

        for fc in ctx_data["field_candidates"]:
            if fc.get("field_name") == "text_body_sha256":
                val = json.loads(fc["value_json"])
                if val is not None and val not in package_digests:
                    raise ExchangeError(
                        "MISSING_TEXT_BODY",
                        val,
                        "field_candidate references text_body_sha256 absent from text_bodies",
                    )

    def _import_core_into(self, core_cap, core_data, work):
        with account_verification(work):
            return self._import_core_units(core_cap, core_data, work)

    def _import_core_units(
        self,
        core_cap: GitCore,
        core_data: dict[str, list[dict[str, Any]]],
        work: WorkBudget,
    ) -> dict[str, int]:
        # Core units are INSERT-only. Connection-local SQLite change counts
        # capture every actual insertion, including new ref families, without
        # repeatedly scanning the entire catalog merely to classify replay.
        core_db = getattr(core_cap, "_db", None)
        before_changes = core_db.total_changes if core_db is not None else 0

        for repo in core_data["repositories"]:
            _performed("metadata_units", 1)
            core_cap.admit_repository(repo["repository_uuidv4"])

        for rc in core_data["repository_claims"]:
            _performed("metadata_units", 1)
            prov = Provenance(*json.loads(rc["provenance_json"]))
            # RepositoryClaim stores a direct JSON value, unlike ScalarClaim's
            # ["known", value]/["unknown"] tagged encoding. Never index a string.
            original_value = json.loads(rc["value_json"])
            core_cap.admit_repository_claim(
                RepositoryClaim(
                    rc["repository_uuidv4"], rc["field"], original_value, prov
                )
            )

        admitted_objects = 0
        for obj in core_data["git_objects"]:
            _performed("metadata_units", 1)
            object_oid = OID(obj["object_format"], obj["object_oid"])
            core_cap.admit_object(object_oid)
            admitted_objects += 1

        # Original ref subjects/results and whole enumeration links are typed
        # and checked separately from object or Context ownership.
        from repo_catalog.application.ref_exchange import (
            import_ref_notes,
            import_ref_units,
        )

        ref_claims = import_ref_units(core_cap, core_data, work)
        import_ref_notes(core_cap, core_data, ref_claims, work, self._receiver_instance)

        # Admit retained_metadata first so receiver_intrinsic claims/groups are generated by receiver
        verified_intrinsic_claims: set[tuple[str, str, str, str, str]] = set()
        verified_intrinsic_groups: set[tuple[str, str, str, str, str, str]] = set()
        admitted_meta = 0
        for meta in core_data["retained_metadata"]:
            _performed("metadata_units", 1)
            object_oid = OID(meta["object_format"], meta["object_oid"])
            body = bytes.fromhex(meta["body_hex"])
            native = NativeObject(
                object_oid,
                meta["native_type"],
                body,
                meta["size"],
                str(meta["digest_sha256"]),
            )
            c_keys, g_keys = _recomputed_intrinsic_keys(native)
            verified_intrinsic_claims.update(c_keys)
            verified_intrinsic_groups.update(g_keys)
            core_cap.admit_metadata(native, meta["physical_copy_uuidv4"], work)
            admitted_meta += 1

        ignored_claims = 0
        for sc in core_data["scalar_claims"]:
            _performed("metadata_units", 1)
            object_oid = OID(sc["object_format"], sc["object_oid"])
            prov = Provenance(*json.loads(sc["provenance_json"]))
            val_dec = json.loads(sc["value_json"])
            orig_val = None if val_dec == ["unknown"] else val_dec[1]
            claim = ScalarClaim(object_oid, sc["field"], orig_val, prov)
            if (
                claim.key[3] != sc["value_json"]
                or claim.key[4] != sc["provenance_json"]
            ):
                raise ExchangeError("NONCANONICAL_CLAIM", "scalar_claims")
            authority = sc.get("authority", "reported")
            if authority == "intrinsic" or prov.qualification == "receiver_intrinsic":
                if claim.key not in verified_intrinsic_claims:
                    ignored_claims += 1
                continue
            core_cap.admit_claim(claim)

        ignored_groups = 0
        for rg in core_data["relation_groups"]:
            _performed("metadata_units", 1)
            object_oid = OID(rg["object_format"], rg["object_oid"])
            prov = Provenance(*json.loads(rg["provenance_json"]))
            members = tuple(
                RelationMember(
                    tuple(m[0]) if isinstance(m[0], list) else m[0],
                    OID(m[1], m[2]),
                )
                for m in json.loads(rg["membership_json"])
            )
            group = RelationGroup(
                object_oid,
                rg["relation"],
                rg["scope"],
                rg["status"],
                members,
                prov,
            )
            if (
                group.key[5] != rg["membership_json"]
                or group.key[6] != rg["provenance_json"]
            ):
                raise ExchangeError("NONCANONICAL_GROUP", "relation_groups")
            authority = rg.get("authority", "reported")
            if authority == "intrinsic" or prov.qualification == "receiver_intrinsic":
                if group.key not in verified_intrinsic_groups:
                    ignored_groups += 1
                continue
            core_cap.admit_group(group)

        for obs in core_data["git_observations"]:
            _performed("metadata_units", 1)
            prov = Provenance(*json.loads(obs["provenance_json"]))
            scope_val = json.loads(obs["scope_json"])
            payload_val = json.loads(
                obs.get("value_json", obs.get("payload_json", "{}"))
            )
            origin_uuid = obs.get("capture_origin_uuidv4", obs.get("origin_uuidv4"))
            cap_uuid = obs.get("capture_uuidv4", obs.get("observation_uuidv4"))
            core_cap.admit_observation(
                GitObservation(
                    origin_uuid,
                    cap_uuid,
                    obs["repository_uuidv4"],
                    obs["kind"],
                    scope_val,
                    payload_val,
                    prov,
                )
            )

        admitted_roles = len(core_data["notes_mapping_evidence"])

        admitted_notes = len(core_data["ref_retained_notes"])

        for cs in core_data["coverage_scopes"]:
            _performed("metadata_units", 1)
            coords = tuple(json.loads(cs["owner_coordinates_json"]))
            core_cap.admit_coverage_scope(CoreCoverageScope(cs["owner_kind"], coords))

        sorted_claims = sorted(
            core_data["coverage_claims"], key=lambda item: item["observed_at_us"]
        )
        for cc in sorted_claims:
            _performed("metadata_units", 1)
            coords = tuple(json.loads(cc["owner_coordinates_json"]))
            c_scope = CoreCoverageScope(cc["owner_kind"], coords)
            core_cap.admit_coverage_scope(c_scope)
            core_cap.admit_coverage(
                CoverageClaim(
                    c_scope,
                    cc["observed_at_us"],
                    cc["coverage_state"],
                    cc["details_json"],
                )
            )

        from repo_catalog.application.ref_exchange import import_ref_coverage

        import_ref_coverage(
            core_cap, core_data, ref_claims, work, self._receiver_instance
        )

        for cp in core_data["coverage_proofs"]:
            _performed("metadata_units", 1)
            coords = tuple(json.loads(cp["owner_coordinates_json"]))
            c_scope = CoreCoverageScope(cp["owner_kind"], coords)
            c_claim = CoverageClaim(
                c_scope,
                cp["observed_at_us"],
                cp["coverage_state"],
            )
            members = tuple(OID(m[0], m[1]) for m in json.loads(cp["members_json"]))
            prov = Provenance(*json.loads(cp["provenance_json"]))
            core_cap.admit_coverage_proof(c_claim, members, prov)

        new_rows = core_db.total_changes - before_changes if core_db is not None else 0
        return {
            "admitted_core_objects": admitted_objects,
            "admitted_retained_metadata": admitted_meta,
            "admitted_note_roles": admitted_roles,
            "admitted_retained_notes": admitted_notes,
            "ignored_unverified_intrinsic_claims": ignored_claims,
            "ignored_unverified_intrinsic_groups": ignored_groups,
            "new_rows": new_rows,
        }

    def _import_context_accounted(self, ctx, data, validator, work):
        with account_verification(work):
            return self._import_context_into(ctx, data, validator)

    def _import_context_into(
        self,
        ctx: Context,
        ctx_data: dict[str, list[dict[str, Any]]],
        validate_core: Callable[[str, str], bool],
    ) -> dict[str, int]:
        from repo_catalog.domain.p1_context import CoverageClaim as ContextCoverageClaim
        from repo_catalog.domain.p1_context import CoverageScope as ContextCoverageScope
        from repo_catalog.domain.p1_context import (
            FieldCandidate,
            FieldClock,
            ResourceKey,
        )
        from repo_catalog.domain.production_context import (
            CollectionObservation,
            ResourceRelation,
            SourceInventory,
        )
        from repo_catalog.domain.selective_exchange import preflight_i2_context

        preflight_i2_context(ctx_data)
        count_sql = "SELECT (SELECT count(*) FROM providers)+(SELECT count(*) FROM repository_context)+(SELECT count(*) FROM sources)+(SELECT count(*) FROM source_repositories)+(SELECT count(*) FROM resources)+(SELECT count(*) FROM resource_repository_relations)+(SELECT count(*) FROM repository_mapping_dispositions)+(SELECT count(*) FROM field_candidates)+(SELECT count(*) FROM resource_relations)+(SELECT count(*) FROM text_bodies)+(SELECT count(*) FROM collections)+(SELECT count(*) FROM collection_terminals)+(SELECT count(*) FROM core_references)+(SELECT count(*) FROM coverage_scopes)+(SELECT count(*) FROM coverage_claims)+(SELECT count(*) FROM coverage_proofs)+(SELECT count(*) FROM source_inventory_evidence)+(SELECT count(*) FROM source_coverage_proofs)"
        before_changes = ctx.db.execute(count_sql).fetchone()[0]
        before_res_count = ctx.db.execute("SELECT COUNT(*) FROM resources").fetchone()[
            0
        ]
        before_fc_count = ctx.db.execute(
            "SELECT COUNT(*) FROM field_candidates"
        ).fetchone()[0]
        before_cr_count = ctx.db.execute(
            "SELECT COUNT(*) FROM core_references"
        ).fetchone()[0]

        for prov in ctx_data["providers"]:
            _performed("metadata_units", 1)
            ctx.provider(
                prov["service_instance_uuidv4"],
                prov["provider_kind"],
                prov["configuration_json"],
            )

        for repo in ctx_data["repositories"]:
            _performed("metadata_units", 1)
            ctx.repository(
                repo["repository_uuidv4"],
                repo["configuration_json"],
            )

        for src in ctx_data["sources"]:
            _performed("metadata_units", 1)
            ctx.source(
                src["source_registration_uuidv4"],
                src["service_instance_uuidv4"],
                src["configuration_json"],
            )

        for sr in ctx_data["source_repositories"]:
            _performed("metadata_units", 1)
            has_repo = ctx.db.execute(
                "SELECT 1 FROM repository_context WHERE repository_uuidv4=?",
                (sr["repository_uuidv4"],),
            ).fetchone()
            if not has_repo:
                raise ExchangeError(
                    "MISSING_REPOSITORY_DEPENDENCY", "source_membership"
                )
            ctx.associate_source(
                sr["source_registration_uuidv4"],
                sr["repository_uuidv4"],
                sr["attributes_json"],
            )

        from repo_catalog.domain.resource_identification import ResourceIdentification

        admitted_resources = 0
        for res in ctx_data["resources"]:
            _performed("metadata_units", 1)
            rk = ResourceKey(
                res["service_instance_uuidv4"],
                res["resource_kind"],
                res["provider_resource_id"],
            )
            ident = ResourceIdentification.from_wire(res)
            ctx.resource(rk, identification=ident)
            admitted_resources += 1

        for row in sorted(
            ctx_data["resource_repository_relations"],
            key=lambda r: r["relation_kind"] != "represents_repository",
        ):
            _performed("metadata_units", 1)
            if not row["relation_kind"].startswith("transfer_"):
                ctx.admit_repository_relation(decode_relation(row))
        for row in ctx_data["repository_mapping_dispositions"]:
            _performed("metadata_units", 1)
            ctx.admit_mapping_disposition(decode_disposition(row))
        for rel in ctx_data["resource_relations"]:
            _performed("metadata_units", 1)
            if rel["relation_kind"] == "transfer_event_report":
                continue
            owner_rk = ResourceKey(
                rel["service_instance_uuidv4"],
                rel["resource_kind"],
                rel["provider_resource_id"],
            )
            members = tuple(ResourceKey(*m) for m in json.loads(rel["members_json"]))
            ctx.relation(
                ResourceRelation(
                    owner_rk,
                    rel["relation_kind"],
                    members,
                    rel["provenance_json"],
                    rel["scope_json"],
                    rel["observed_at_us"],
                )
            )
        for report in transfer_reports(ctx_data):
            _performed("metadata_units", 1)
            ctx.admit_transfer_event(report)

        for tb in ctx_data["text_bodies"]:
            _performed("metadata_units", 1)
            ctx.text(tb["text_value"])

        linked_refs = 0
        pending_refs = 0
        missing_refs = []
        seen_core_refs: set[tuple[ResourceKey, str, str, str, str]] = set()

        for fc in ctx_data["field_candidates"]:
            _performed("metadata_units", 1)
            rk = ResourceKey(
                fc["service_instance_uuidv4"],
                fc["resource_kind"],
                fc["provider_resource_id"],
            )
            field_name = fc["field_name"]
            if field_name.startswith("reported_core_reference:"):
                role = field_name.removeprefix("reported_core_reference:")
                oid_pair = json.loads(fc["value_json"])
                object_oid = OID(oid_pair[0], oid_pair[1])
                ref_key = (
                    rk,
                    role,
                    object_oid.object_format,
                    object_oid.object_oid,
                    fc["provenance_json"],
                )
                seen_core_refs.add(ref_key)
                ctx.admit_field(
                    FieldCandidate(
                        rk,
                        field_name,
                        fc["value_json"],
                        FieldClock(fc["clock_domain"], fc["clock_ts_us"]),
                        fc["provenance_json"],
                        fc["observed_at_us"],
                    )
                )
                if validate_core(object_oid.object_format, object_oid.object_oid):
                    ctx.link_core(
                        rk,
                        role,
                        object_oid.object_format,
                        object_oid.object_oid,
                        fc["provenance_json"],
                        validate_core,
                    )
                    linked_refs += 1
                else:
                    missing_refs.append(
                        {
                            "section": "core_references",
                            "unit": [
                                list(rk.coordinates()),
                                role,
                                *object_oid.key,
                                fc["provenance_json"],
                            ],
                            "reason": "missing_core_oid",
                        }
                    )
                    pending_refs += 1
            else:
                ctx.admit_field(
                    FieldCandidate(
                        rk,
                        field_name,
                        fc["value_json"],
                        FieldClock(fc["clock_domain"], fc["clock_ts_us"]),
                        fc["provenance_json"],
                        fc["observed_at_us"],
                    )
                )

        for cr in ctx_data["core_references"]:
            _performed("metadata_units", 1)
            rk = ResourceKey(
                cr["service_instance_uuidv4"],
                cr["resource_kind"],
                cr["provider_resource_id"],
            )
            object_oid = OID(cr["object_format"], cr["object_oid"])
            role = cr["role"]
            prov_json = cr["provenance_json"]
            ref_key = (
                rk,
                role,
                object_oid.object_format,
                object_oid.object_oid,
                prov_json,
            )
            if ref_key in seen_core_refs:
                continue
            seen_core_refs.add(ref_key)
            if validate_core(object_oid.object_format, object_oid.object_oid):
                ctx.link_core(
                    rk,
                    role,
                    object_oid.object_format,
                    object_oid.object_oid,
                    prov_json,
                    validate_core,
                )
                linked_refs += 1
            else:
                missing_refs.append(
                    {
                        "section": "core_references",
                        "unit": [
                            list(rk.coordinates()),
                            role,
                            *object_oid.key,
                            prov_json,
                        ],
                        "reason": "missing_core_oid",
                    }
                )
                pending_refs += 1

        # Index coverage claims and proofs so collection and inventory proofs are admitted
        # while their terminal observation is the current latest terminal.
        claims_by_key: dict[tuple[str, str, int, str], dict[str, Any]] = {}
        for cc in ctx_data["coverage_claims"]:
            _performed("metadata_units", 1)
            claims_by_key[
                (
                    cc["owner_kind"],
                    cc["owner_coordinates_json"],
                    cc["observed_at_us"],
                    cc["coverage_state"],
                )
            ] = cc

        collection_proofs_by_terminal: dict[
            tuple[str, str, str, str, str, int], list[dict[str, Any]]
        ] = {}
        inventory_proofs_by_terminal: dict[
            tuple[str, str, int], list[dict[str, Any]]
        ] = {}
        for cp in ctx_data["coverage_proofs"]:
            _performed("metadata_units", 1)
            if cp.get("proof_kind") == "collection":
                t_key = terminal_key(cp, "collection")
                collection_proofs_by_terminal.setdefault(t_key, []).append(cp)
            elif cp.get("proof_kind") == "source_inventory":
                i_key = terminal_key(cp, "source_inventory")
                inventory_proofs_by_terminal.setdefault(i_key, []).append(cp)

        admitted_claim_keys: set[tuple[str, str, int, str]] = set()

        for inv in sorted(
            ctx_data["source_inventories"], key=lambda item: item["observed_at_us"]
        ):
            _performed("metadata_units", 1)
            repos = tuple(
                json.loads(inv.get("members_json", inv.get("repositories_json", "[]")))
            )
            for r_uuid in repos:
                _performed("metadata_units", 1)
                has_repo = ctx.db.execute(
                    "SELECT 1 FROM repository_context WHERE repository_uuidv4=?",
                    (r_uuid,),
                ).fetchone()
                if not has_repo:
                    raise ExchangeError(
                        "MISSING_REPOSITORY_DEPENDENCY", "source_inventory"
                    )
            state_val = inv.get("coverage_state", inv.get("terminal_state", "complete"))
            term_val = bool(inv.get("terminal", True))
            src_inv = SourceInventory(
                inv["source_registration_uuidv4"],
                inv["scope_json"],
                inv["observed_at_us"],
                state_val,
                term_val,
                repos,
                inv["provenance_json"],
            )
            ctx.inventory(src_inv)
            i_key = terminal_key(inv, "source_inventory")
            for cp in inventory_proofs_by_terminal.get(i_key, ()):
                _performed("metadata_units", 1)
                c_key = (
                    cp["owner_kind"],
                    cp["owner_coordinates_json"],
                    cp["observed_at_us"],
                    cp["coverage_state"],
                )
                cc_row = claims_by_key.get(c_key)
                details_json = cc_row["details_json"] if cc_row else None
                c_scope = ContextCoverageScope(
                    cp["owner_kind"], json.loads(cp["owner_coordinates_json"])
                )
                c_claim = ContextCoverageClaim(
                    c_scope,
                    cp["observed_at_us"],
                    cp["coverage_state"],
                    details_json,
                )
                ctx.prove_inventory(c_claim, src_inv)
                admitted_claim_keys.add(c_key)

        for coll in sorted(
            ctx_data["collections"], key=lambda item: item["observed_at_us"]
        ):
            _performed("metadata_units", 1)
            owner_rk = ResourceKey(
                coll["service_instance_uuidv4"],
                coll["resource_kind"],
                coll["provider_resource_id"],
            )
            members = tuple(ResourceKey(*m) for m in json.loads(coll["members_json"]))
            coll_obs = CollectionObservation(
                owner_rk,
                coll["collection_kind"],
                coll["provenance_json"],
                coll["scope_json"],
                coll["observed_at_us"],
                coll["terminal_state"],
                members,
            )
            ctx.collection(coll_obs)
            t_key = terminal_key(coll, "collection")
            for cp in collection_proofs_by_terminal.get(t_key, ()):
                _performed("metadata_units", 1)
                c_key = (
                    cp["owner_kind"],
                    cp["owner_coordinates_json"],
                    cp["observed_at_us"],
                    cp["coverage_state"],
                )
                cc_row = claims_by_key.get(c_key)
                details_json = cc_row["details_json"] if cc_row else None
                c_scope = ContextCoverageScope(
                    cp["owner_kind"], json.loads(cp["owner_coordinates_json"])
                )
                c_claim = ContextCoverageClaim(
                    c_scope,
                    cp["observed_at_us"],
                    cp["coverage_state"],
                    details_json,
                )
                ctx.prove_collection(
                    c_claim,
                    coll_obs,
                    required_scope_json=coll["scope_json"],
                )
                admitted_claim_keys.add(c_key)

        # Collection-owned scope FKs require their original collections first.
        for cs in ctx_data["coverage_scopes"]:
            _performed("metadata_units", 1)
            coords = json.loads(cs["owner_coordinates_json"])
            ctx.scope(ContextCoverageScope(cs["owner_kind"], coords))

        for cc in sorted(
            ctx_data["coverage_claims"], key=lambda item: item["observed_at_us"]
        ):
            _performed("metadata_units", 1)
            c_key = (
                cc["owner_kind"],
                cc["owner_coordinates_json"],
                cc["observed_at_us"],
                cc["coverage_state"],
            )
            if c_key in admitted_claim_keys:
                continue
            c_scope = ContextCoverageScope(
                cc["owner_kind"], json.loads(cc["owner_coordinates_json"])
            )
            ctx.scope(c_scope)
            ctx.admit_coverage(
                ContextCoverageClaim(
                    c_scope,
                    cc["observed_at_us"],
                    cc["coverage_state"],
                    cc["details_json"],
                )
            )

        after_res_count = ctx.db.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        after_fc_count = ctx.db.execute(
            "SELECT COUNT(*) FROM field_candidates"
        ).fetchone()[0]
        after_cr_count = ctx.db.execute(
            "SELECT COUNT(*) FROM core_references"
        ).fetchone()[0]
        new_rows = (
            (after_res_count - before_res_count)
            + (after_fc_count - before_fc_count)
            + (after_cr_count - before_cr_count)
        )

        new_rows = ctx.db.execute(count_sql).fetchone()[0] - before_changes
        return {
            "missing_refs": missing_refs,
            "admitted_context_resources": admitted_resources,
            "linked_core_references": linked_refs,
            "pending_core_references": pending_refs,
            "new_rows": new_rows,
        }
