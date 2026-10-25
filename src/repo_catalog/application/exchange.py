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
from typing import Any, Iterator
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
from repo_catalog.adapters.sqlite.production_context import Context
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
from repo_catalog.domain.notes import NotesInventory, verify_inventory
from repo_catalog.domain.p1_context import (
    CoverageClaim as ContextCoverageClaim,
)
from repo_catalog.domain.p1_context import (
    CoverageScope as ContextCoverageScope,
)
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_coordination import (
    AdmissionFailure,
    CoordinationError,
    RequestIdentity,
)
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreCoverageScope,
    CoreFailure,
    GitObservation,
    NativeObject,
    NotesClaim,
    NotesGroup,
    NotesProof,
    Provenance,
    RelationGroup,
    RelationMember,
    RepositoryClaim,
    ScalarClaim,
    _notes_group,
    _performed,
    account_verification,
    encode,
    intrinsic_members,
    valid_note_role,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ports.p1_core import WorkBudget
from repo_catalog.domain.production_context import (
    CollectionObservation,
    ResourceRelation,
    SourceInventory,
)
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


def _recomputed_intrinsic_keys(
    native: NativeObject,
) -> tuple[
    set[tuple[str, str, str, str, str]], set[tuple[str, str, str, str, str, str]]
]:
    """Compute exact (object_format, full_oid, ...) keys that GitCore.admit_metadata generates."""
    claim_keys: set[tuple[str, str, str, str, str]] = set()
    group_keys: set[tuple[str, str, str, str, str, str]] = set()

    for field_name, val in (("type", native.native_type), ("size", len(native.body))):
        prov = Provenance(
            "receiver-intrinsic",
            encode(native.oid.key),
            f"native-{field_name}",
            "p1-native",
            "1",
            "receiver_intrinsic",
        )
        claim = ScalarClaim(native.oid, field_name, val, prov)
        claim_keys.add(claim.key)

    parsed = parse_metadata(native.oid.object_format, native.native_type, native.body)
    for field_name, val in parsed.scalars.items():
        if field_name in ("type", "size", "tree_count"):
            continue
        prov = Provenance(
            "receiver-intrinsic",
            encode(native.oid.key),
            "native-" + field_name,
            DECODER,
            DECODER_VERSION,
            "receiver_intrinsic",
        )
        claim = ScalarClaim(native.oid, field_name, val, prov)
        claim_keys.add(claim.key)

    relations = {
        "commit": ("commit_parents", "commit_tree"),
        "tree": ("tree_entries",),
        "tag": ("tag_target",),
    }[native.native_type]
    for rel_name in relations:
        members = intrinsic_members(
            native.oid.object_format, native.native_type, native.body, rel_name
        )
        prov = Provenance(
            "receiver-intrinsic",
            encode(native.oid.key),
            rel_name,
            "p1-native",
            "1",
            "receiver_intrinsic",
        )
        group = RelationGroup(
            native.oid,
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


def _decode_capture_ref(raw_ref: str) -> str:
    if raw_ref.startswith("refs/"):
        return raw_ref
    try:
        parsed = json.loads(raw_ref)
        if isinstance(parsed, list) and len(parsed) == 2 and parsed[0] == "native-ref":
            return bytes.fromhex(parsed[1]).decode("utf-8", "surrogateescape")
    except Exception:
        pass
    return raw_ref


def _notes_proof_from_bundle_json(
    cap: Capture,
    target: OID,
    note: OID,
    path: str,
    bundle_json: str,
) -> NotesProof:
    try:
        raw_bundle = json.loads(bundle_json)
        fmt = cap.root.object_format
        structures = []
        for item in raw_bundle:
            body_hex = item[2]
            if (
                type(body_hex) is not str
                or len(body_hex) % 2
                or any(char not in "0123456789abcdef" for char in body_hex)
            ):
                raise ValueError("lowercase contiguous proof body hex required")
            body = bytes.fromhex(body_hex)
            _performed("verification_bytes", len(body))
            structures.append(
                NativeObject(
                    OID(fmt, item[0]),
                    item[1],
                    body,
                    len(body),
                    hashlib.sha256(body).hexdigest(),
                )
            )
        structures = tuple(structures)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise CoreFailure(
            "NOTES_PROOF", (cap.pair, target), f"invalid proof bundle: {exc}"
        ) from exc
    return NotesProof(cap, target, note, path, structures)


def _checked_registration(ctx: Context, kind: str, encoded: str) -> str:
    ctx.registration_metadata(kind, encoded)
    return encoded


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

    def _store_identity(self) -> tuple[str, str]:
        self._check_stop()
        if self._has_core():
            core = GitCore(self.directory / "core.sqlite3")
            try:
                repo_id, inst_id = core.catalog_identity()
            finally:
                core.close()
            if self._has_context():
                with Context.snapshot(
                    self.directory,
                    read_limits=SnapshotReadLimits(),
                ) as ctx:
                    row = ctx.db.execute(
                        "SELECT repository_uuidv4, catalog_instance_uuidv4 FROM store_identity"
                    ).fetchone()
                    if row != (repo_id, inst_id):
                        raise CoordinationError("PAIR_IDENTITY", "core+context")
            return repo_id, inst_id
        if self._has_context():
            with Context.snapshot(
                self.directory,
                read_limits=SnapshotReadLimits(),
            ) as ctx:
                row = ctx.db.execute(
                    "SELECT repository_uuidv4, catalog_instance_uuidv4 FROM store_identity"
                ).fetchone()
                if row is None:
                    raise CoordinationError("STORE_IDENTITY", "context")
                return str(row[0]), str(row[1])
        raise CoordinationError("AUTHORITY_UNAVAILABLE", "catalog")

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
            pkg_id = package_id or str(uuid4())
            repo_uuid, sender_instance = self._store_identity()

            core_section: dict[str, list[dict[str, Any]]] | None = None
            if scope.include_core and self._has_core():
                try:
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

            context_section: dict[str, list[dict[str, Any]]] | None = None
            if scope.include_context and self._has_context():
                try:
                    context_section = self._export_context(scope)
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

            self._selection_details["omissions"].extend(
                filter_sections(
                    core_section,
                    context_section,
                    scope,
                )
            )
            limited, counts = bound_sections(core_section, context_section, scope)
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
                    [r["object_format"], r["full_oid"]]
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
                for owner in sorted(frontier, key=lambda oid: oid.key):
                    for row in core.sql(
                        "SELECT membership FROM relation_groups WHERE object_format=? AND full_oid=? ORDER BY relation,scope,status,membership,provenance",
                        owner.key,
                    ):
                        for member in json.loads(row[0]):
                            target = OID(member[1], member[2])
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
                                "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
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
            scope, object_oids=tuple(sorted(chosen, key=lambda oid: oid.key))
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

        selected_notes_refs = (
            None if scope.notes_refs is None else set(scope.notes_refs)
        )

        core = GitCore(self.directory / "core.sqlite3")
        try:
            self._bound_export_connection(core._db)
            core.ensure_available()
            referenced_oids: set[OID] = set()

            for row in core.sql(
                "SELECT repository_uuidv4 FROM repositories ORDER BY repository_uuidv4"
            ):
                section["repositories"].append({"repository_uuidv4": row[0]})

            for row in core.sql(
                "SELECT repository_uuidv4, field, value, provenance FROM repository_claims "
                "ORDER BY repository_uuidv4, field, value, provenance"
            ):
                section["repository_claims"].append(
                    {
                        "repository_uuidv4": row[0],
                        "field": row[1],
                        "value_json": row[2],
                        "provenance_json": row[3],
                    }
                )

            # Verify all retained_metadata rows via core.read_metadata(oid)
            meta_rows = core.sql(
                "SELECT object_format, full_oid, physical_copy_uuidv4, native_type, size, digest_sha256 "
                "FROM retained_metadata ORDER BY object_format, full_oid, physical_copy_uuidv4"
            )
            for row in meta_rows:
                if row[4] > scope.max_bytes:
                    self._selection_details["omissions"].append(
                        {
                            "section": "retained_metadata",
                            "unit": list(row[:2]),
                            "reason": "byte_limit",
                        }
                    )
                    continue
                oid = OID(row[0], row[1])
                if selected_oids is not None and oid not in selected_oids:
                    continue
                # Always call read_metadata to verify byte/hash/grammar integrity before export
                body = core.read_metadata(oid)
                referenced_oids.add(oid)
                if scope.include_retained_bytes:
                    section["retained_metadata"].append(
                        {
                            "object_format": row[0],
                            "full_oid": row[1],
                            "physical_copy_uuidv4": row[2],
                            "native_type": row[3],
                            "body_hex": body.hex(),
                            "size": row[4],
                            "digest_sha256": row[5],
                        }
                    )

            claim_rows = core.sql(
                "SELECT c.object_format, c.full_oid, c.field, c.value, c.provenance, "
                "EXISTS(SELECT 1 FROM intrinsic_claims i WHERE i.object_format=c.object_format "
                "AND i.full_oid=c.full_oid AND i.field=c.field AND i.value=c.value "
                "AND i.provenance=c.provenance) AS checked "
                "FROM scalar_claims c ORDER BY c.object_format, c.full_oid, c.field, c.value, c.provenance"
            )
            for row in claim_rows:
                oid = OID(row[0], row[1])
                if selected_oids is not None and oid not in selected_oids:
                    continue
                # Run typed scalar projection check on this field
                core.scalar(oid, row[2])
                referenced_oids.add(oid)
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
                            "full_oid": row[1],
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
                            "full_oid": row[1],
                            "field": row[2],
                            "value_json": row[3],
                            "provenance_json": row[4],
                            "authority": "intrinsic" if is_checked else "reported",
                        }
                    )

            group_rows = core.sql(
                "SELECT g.object_format, g.full_oid, g.relation, g.scope, g.status, g.membership, g.provenance, "
                "EXISTS(SELECT 1 FROM intrinsic_groups i WHERE i.object_format=g.object_format "
                "AND i.full_oid=g.full_oid AND i.relation=g.relation AND i.scope=g.scope "
                "AND i.status=g.status AND i.membership=g.membership AND i.provenance=g.provenance) AS checked "
                "FROM relation_groups g ORDER BY g.object_format, g.full_oid, g.relation, g.scope, g.status, g.membership, g.provenance"
            )
            for row in group_rows:
                oid = OID(row[0], row[1])
                if selected_oids is not None and oid not in selected_oids:
                    continue
                core.relations(oid, row[2], row[3])
                referenced_oids.add(oid)
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
                            "full_oid": row[1],
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
                            "full_oid": row[1],
                            "relation": row[2],
                            "scope": row[3],
                            "status": row[4],
                            "membership_json": row[5],
                            "provenance_json": row[6],
                            "authority": "intrinsic" if is_checked else "reported",
                        }
                    )

            for row in core.sql(
                "SELECT capture_origin_uuidv4, capture_uuidv4, repository_uuidv4, kind, scope, value, provenance "
                "FROM git_observations ORDER BY capture_origin_uuidv4, capture_uuidv4"
            ):
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

            capture_rows = core.sql(
                "SELECT capture_origin_uuidv4, capture_uuidv4, repository_uuidv4, source, ref, object_format, root "
                "FROM captures ORDER BY capture_origin_uuidv4, capture_uuidv4"
            )
            exported_captures: list[Capture] = []
            exported_capture_pairs: set[tuple[str, str]] = set()
            for row in capture_rows:
                if (
                    selected_oids is not None
                    and OID(row[5], row[6]) not in selected_oids
                ):
                    continue
                decoded_ref = _decode_capture_ref(row[4])
                if (
                    selected_notes_refs is not None
                    and decoded_ref not in selected_notes_refs
                ):
                    continue
                cap = Capture(
                    row[0], row[1], row[2], row[3], decoded_ref, OID(row[5], row[6])
                )
                exported_captures.append(cap)
                exported_capture_pairs.add(cap.pair)
                referenced_oids.add(cap.root)
                section["captures"].append(
                    {
                        "capture_origin_uuidv4": row[0],
                        "capture_uuidv4": row[1],
                        "repository_uuidv4": row[2],
                        "source": row[3],
                        "ref": row[4],
                        "object_format": row[5],
                        "root": row[6],
                    }
                )

            for row in core.sql(
                "SELECT capture_origin_uuidv4, capture_uuidv4, object_format, target, note, provenance "
                "FROM notes_claims ORDER BY capture_origin_uuidv4, capture_uuidv4, object_format, target, note, provenance"
            ):
                if (row[0], row[1]) not in exported_capture_pairs:
                    continue
                target_oid = OID(row[2], row[3])
                if selected_oids is not None and target_oid not in selected_oids:
                    continue
                note_oid = OID(row[2], row[4])
                referenced_oids.add(target_oid)
                referenced_oids.add(note_oid)
                section["notes_claims"].append(
                    {
                        "capture_origin_uuidv4": row[0],
                        "capture_uuidv4": row[1],
                        "object_format": row[2],
                        "target": row[3],
                        "note": row[4],
                        "provenance_json": row[5],
                    }
                )

            for cap in exported_captures:
                # 1. Verify receiver_intrinsic notes_inventories via core.notes_inventories(cap)
                invs = core.notes_inventories(cap)
                for inv in invs:
                    for t_hex, n_hex, _p in inv.members:
                        referenced_oids.add(OID(cap.root.object_format, t_hex))
                        referenced_oids.add(OID(cap.root.object_format, n_hex))
                    if scope.include_retained_bytes:
                        section["notes_inventories"].append(
                            {
                                "capture_origin_uuidv4": cap.capture_origin_uuidv4,
                                "capture_uuidv4": cap.capture_uuidv4,
                                "status": inv.status,
                                "members": [list(m) for m in inv.members],
                                "structures": [
                                    {
                                        "object_format": s.oid.object_format,
                                        "full_oid": s.oid.full_oid,
                                        "native_type": s.native_type,
                                        "body_hex": s.body.hex(),
                                        "declared_size": s.declared_size,
                                        "digest_sha256": s.digest_sha256,
                                    }
                                    for s in inv.structures
                                ],
                                "failure": (
                                    None
                                    if inv.failure is None
                                    else [inv.failure.code, inv.failure.detail]
                                ),
                            }
                        )
                    else:
                        downgraded_prov = Provenance(
                            cap.source,
                            encode(cap.key),
                            "notes-inventory",
                            "git-native-notes-inventory",
                            "1",
                            "reported",
                        )
                        section["notes_groups"].append(
                            {
                                "capture_origin_uuidv4": cap.capture_origin_uuidv4,
                                "capture_uuidv4": cap.capture_uuidv4,
                                "object_format": cap.root.object_format,
                                "scope": "all-notes-mappings",
                                "status": inv.status,
                                "membership_json": encode(
                                    [list(m) for m in inv.members]
                                ),
                                "provenance_json": downgraded_prov.encoded,
                                "authority": "reported",
                            }
                        )

                # 2. Verify notes_groups and note_roles via core.notes_projection
                core.notes_projection(cap, cap.root)
                role_targets = core.sql(
                    "SELECT DISTINCT object_format, target FROM note_roles "
                    "WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                    cap.pair,
                )
                for rt in role_targets:
                    t_oid = OID(rt[0], rt[1])
                    if selected_oids is not None and t_oid not in selected_oids:
                        continue
                    core.notes_projection(cap, t_oid)

                prev_checked = getattr(core, "_checked_byte_read", False)
                core._checked_byte_read = True
                try:
                    ng_rows = core.sql(
                        "SELECT scope, status, membership, provenance FROM notes_groups "
                        "WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? "
                        "ORDER BY scope, status, membership, provenance",
                        (*cap.pair, cap.root.object_format),
                    )
                    for ng in ng_rows:
                        if not ng[0] or not _notes_group(
                            cap.root.object_format, ng[1], ng[2]
                        ):
                            core._integrity_stop(
                                (cap.pair, "invalid-stored-notes-group")
                            )
                        prov = core._provenance_value(cap.pair, ng[3])
                        if prov.qualification != "reported":
                            continue
                        for m in json.loads(ng[2]):
                            referenced_oids.add(OID(cap.root.object_format, m[0]))
                            referenced_oids.add(OID(cap.root.object_format, m[1]))
                        section["notes_groups"].append(
                            {
                                "capture_origin_uuidv4": cap.capture_origin_uuidv4,
                                "capture_uuidv4": cap.capture_uuidv4,
                                "object_format": cap.root.object_format,
                                "scope": ng[0],
                                "status": ng[1],
                                "membership_json": ng[2],
                                "provenance_json": ng[3],
                                "authority": "reported",
                            }
                        )

                    nr_rows = core.sql(
                        "SELECT object_format, root, target, note, path, proof_bundle FROM note_roles "
                        "WHERE capture_origin_uuidv4=? AND capture_uuidv4=? "
                        "ORDER BY object_format, root, target, note, path, proof_bundle",
                        cap.pair,
                    )
                    for nr in nr_rows:
                        t_oid = OID(nr[0], nr[2])
                        n_oid = OID(nr[0], nr[3])
                        if selected_oids is not None and t_oid not in selected_oids:
                            continue
                        if not valid_note_role(
                            nr[0], nr[1], nr[2], nr[3], nr[4], nr[5]
                        ):
                            core._integrity_stop((cap.pair, t_oid, "notes-role"))
                        referenced_oids.add(t_oid)
                        referenced_oids.add(n_oid)
                        section["note_roles"].append(
                            {
                                "capture_origin_uuidv4": cap.capture_origin_uuidv4,
                                "capture_uuidv4": cap.capture_uuidv4,
                                "object_format": nr[0],
                                "root": nr[1],
                                "target": nr[2],
                                "note": nr[3],
                                "path": nr[4],
                                "proof_bundle_json": nr[5],
                            }
                        )

                    rn_rows = core.sql(
                        "SELECT object_format, full_oid, physical_copy_uuidv4, size, digest_sha256, "
                        "root, target, path, proof_bundle FROM retained_notes "
                        "WHERE capture_origin_uuidv4=? AND capture_uuidv4=? "
                        "ORDER BY object_format, full_oid, physical_copy_uuidv4",
                        cap.pair,
                    )
                finally:
                    core._checked_byte_read = prev_checked

                for rn in rn_rows:
                    t_oid = OID(rn[0], rn[6])
                    n_oid = OID(rn[0], rn[1])
                    if selected_oids is not None and t_oid not in selected_oids:
                        continue
                    # Always call core.read_note to verify role proof + note blob integrity
                    note_bytes = core.read_note(cap, t_oid, n_oid)
                    referenced_oids.add(t_oid)
                    referenced_oids.add(n_oid)
                    if scope.include_retained_bytes:
                        section["retained_notes"].append(
                            {
                                "object_format": rn[0],
                                "full_oid": rn[1],
                                "physical_copy_uuidv4": rn[2],
                                "body_hex": note_bytes.hex(),
                                "size": rn[3],
                                "digest_sha256": rn[4],
                                "capture_origin_uuidv4": cap.capture_origin_uuidv4,
                                "capture_uuidv4": cap.capture_uuidv4,
                                "root": rn[5],
                                "target": rn[6],
                                "path": rn[7],
                                "proof_bundle_json": rn[8],
                            }
                        )

            cov_scope_rows = core.sql(
                "SELECT owner_kind, owner_coordinates_json, repository_uuidv4, "
                "capture_origin_uuidv4, capture_uuidv4, object_format, full_oid, field, coverage_kind "
                "FROM coverage_scopes ORDER BY owner_kind, owner_coordinates_json"
            )
            exported_cov_scopes: set[tuple[str, str]] = set()
            for row in cov_scope_rows:
                owner_kind = row[0]
                if (
                    owner_kind == "capture"
                    and (row[3], row[4]) not in exported_capture_pairs
                ):
                    continue
                if owner_kind in ("object", "field") and selected_oids is not None:
                    if OID(row[5], row[6]) not in selected_oids:
                        continue
                coords = tuple(json.loads(row[1]))
                c_scope = CoreCoverageScope(owner_kind, coords)
                core.coverage(c_scope)
                exported_cov_scopes.add((row[0], row[1]))
                section["coverage_scopes"].append(
                    {
                        "owner_kind": row[0],
                        "owner_coordinates_json": row[1],
                    }
                )

            for row in core.sql(
                "SELECT owner_kind, owner_coordinates_json, observed_at_us, coverage_state, details_json "
                "FROM coverage_claims ORDER BY observed_at_us, owner_kind, owner_coordinates_json, coverage_state"
            ):
                if (row[0], row[1]) not in exported_cov_scopes:
                    continue
                section["coverage_claims"].append(
                    {
                        "owner_kind": row[0],
                        "owner_coordinates_json": row[1],
                        "observed_at_us": row[2],
                        "coverage_state": row[3],
                        "details_json": row[4],
                    }
                )

            for row in core.sql(
                "SELECT owner_kind, owner_coordinates_json, observed_at_us, coverage_state, members_json, provenance "
                "FROM core_coverage_proofs ORDER BY observed_at_us, owner_kind, owner_coordinates_json"
            ):
                if (row[0], row[1]) not in exported_cov_scopes:
                    continue
                members = [OID(m[0], m[1]) for m in json.loads(row[4])]
                for m in members:
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

            for row in core.sql(
                "SELECT object_format, full_oid FROM git_objects ORDER BY object_format, full_oid"
            ):
                oid = OID(row[0], row[1])
                if (
                    selected_oids is not None
                    and oid not in selected_oids
                    and oid not in referenced_oids
                ):
                    continue
                section["git_objects"].append(
                    {"object_format": row[0], "full_oid": row[1]}
                )

            return section
        finally:
            core.close()

    def _export_context(
        self,
        scope: ExchangeSelectionScope,
    ) -> dict[str, list[dict[str, Any]]]:
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
        ) as ctx:
            for row in ctx.db.execute(
                "SELECT service_instance_uuidv4, provider_kind, configuration_json "
                "FROM providers ORDER BY service_instance_uuidv4"
            ):
                section["providers"].append(
                    {
                        "service_instance_uuidv4": row[0],
                        "provider_kind": row[1],
                        "configuration_json": _checked_registration(
                            ctx, "provider", row[2]
                        ),
                    }
                )

            for row in ctx.db.execute(
                "SELECT repository_uuidv4, configuration_json FROM repository_context ORDER BY repository_uuidv4"
            ):
                section["repositories"].append(
                    {
                        "repository_uuidv4": row[0],
                        "configuration_json": _checked_registration(
                            ctx, "repository", row[1]
                        ),
                    }
                )

            for row in ctx.db.execute(
                "SELECT source_registration_uuidv4, service_instance_uuidv4, configuration_json "
                "FROM sources ORDER BY source_registration_uuidv4"
            ):
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

            for row in ctx.db.execute(
                "SELECT source_registration_uuidv4, repository_uuidv4, attributes_json "
                "FROM source_repositories ORDER BY source_registration_uuidv4, repository_uuidv4"
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

            for row in ctx.db.execute(
                "SELECT source_registration_uuidv4, scope_json, observed_at_us, coverage_state, "
                "terminal, members_json, provenance_json "
                "FROM source_inventory_evidence ORDER BY observed_at_us, source_registration_uuidv4, scope_json"
            ):
                if selected_sources is not None and row[0] not in selected_sources:
                    continue
                section["source_inventories"].append(
                    {
                        "source_registration_uuidv4": row[0],
                        "scope_json": row[1],
                        "observed_at_us": row[2],
                        "coverage_state": row[3],
                        "terminal": bool(row[4]),
                        "members_json": row[5],
                        "provenance_json": row[6],
                    }
                )

            # Determine full set of exported resources (including parents/members of selected resources)
            all_resource_rows = ctx.db.execute(
                "SELECT service_instance_uuidv4, resource_kind, provider_resource_id, "
                "identifier_namespace_kind, identifier_namespace_id, document_kind, provider_document_id "
                "FROM resources ORDER BY service_instance_uuidv4, resource_kind, provider_resource_id"
            ).fetchall()

            rel_rows = ctx.db.execute(
                "SELECT service_instance_uuidv4, resource_kind, provider_resource_id, "
                "relation_kind, members_json, provenance_json, scope_json, observed_at_us "
                "FROM resource_relations ORDER BY observed_at_us, service_instance_uuidv4, resource_kind, provider_resource_id, relation_kind"
            ).fetchall()
            coll_rows = ctx.db.execute(
                "SELECT c.service_instance_uuidv4, c.resource_kind, c.provider_resource_id, "
                "c.collection_kind, c.provenance_json, c.scope_json, "
                "t.observed_at_us, t.terminal_state, t.members_json "
                "FROM collections c JOIN collection_terminals t "
                "ON c.service_instance_uuidv4=t.service_instance_uuidv4 "
                "AND c.resource_kind=t.resource_kind "
                "AND c.provider_resource_id=t.provider_resource_id "
                "AND c.collection_kind=t.collection_kind "
                "AND c.provenance_json=t.provenance_json "
                "ORDER BY t.observed_at_us, c.service_instance_uuidv4, c.resource_kind, c.provider_resource_id, c.collection_kind"
            ).fetchall()
            support_columns = (
                "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,"
                "target_json,clock_json,provenance_json,observed_at_us,"
                "event_report_members_json,event_report_scope_json"
            )
            support_rows = [
                dict(zip(support_columns.split(","), r))
                for r in ctx.db.execute(
                    "SELECT "
                    + support_columns
                    + " FROM resource_repository_relations ORDER BY "
                    + support_columns
                )
            ]
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
            for table, columns in (
                (
                    "resource_repository_relations",
                    "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us,event_report_members_json,event_report_scope_json",
                ),
                (
                    "repository_mapping_dispositions",
                    "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,claim_clock_json,claim_target_json,claim_provenance_json,disposition_kind,disposition_clock_json,disposition_provenance_json,observed_at_us,replacement_clock_json,replacement_target_json,replacement_provenance_json",
                ),
            ):
                for row in ctx.db.execute(
                    "SELECT " + columns + " FROM " + table + " ORDER BY " + columns
                ):
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
            fc_rows = ctx.db.execute(
                "SELECT service_instance_uuidv4, resource_kind, provider_resource_id, "
                "field_name, value_json, clock_domain, source_clock_us, provenance_json, observed_at_us "
                "FROM field_candidates "
                "ORDER BY observed_at_us, service_instance_uuidv4, resource_kind, provider_resource_id, field_name"
            ).fetchall()
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

            tb_rows = ctx.db.execute(
                "SELECT sha256 FROM text_bodies ORDER BY sha256"
            ).fetchall()
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

            cr_rows = ctx.db.execute(
                "SELECT service_instance_uuidv4, resource_kind, provider_resource_id, "
                "role, object_format, full_oid, provenance_json "
                "FROM core_references "
                "ORDER BY service_instance_uuidv4, resource_kind, provider_resource_id, role, object_format, full_oid"
            ).fetchall()
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
                        "full_oid": row[5],
                        "provenance_json": row[6],
                    }
                )

            exported_ctx_scopes: set[tuple[str, str]] = set()
            for row in ctx.db.execute(
                "SELECT owner_kind, owner_coordinates_json FROM coverage_scopes "
                "ORDER BY owner_kind, owner_coordinates_json"
            ):
                coords = json.loads(row[1])
                if row[0] == "source" and selected_sources is not None:
                    if coords[0] not in selected_sources:
                        continue
                if row[0] in ("resource", "collection") and selected_rks is not None:
                    rk = ResourceKey(coords[0], coords[1], coords[2])
                    if rk not in included_rks:
                        continue
                c_scope = ContextCoverageScope(row[0], coords)
                ctx.coverage(c_scope)
                exported_ctx_scopes.add((row[0], row[1]))
                section["coverage_scopes"].append(
                    {
                        "owner_kind": row[0],
                        "owner_coordinates_json": row[1],
                    }
                )

            for row in ctx.db.execute(
                "SELECT owner_kind, owner_coordinates_json, observed_at_us, coverage_state, details_json "
                "FROM coverage_claims ORDER BY observed_at_us, owner_kind, owner_coordinates_json, coverage_state"
            ):
                if (row[0], row[1]) not in exported_ctx_scopes:
                    continue
                section["coverage_claims"].append(
                    {
                        "owner_kind": row[0],
                        "owner_coordinates_json": row[1],
                        "observed_at_us": row[2],
                        "coverage_state": row[3],
                        "details_json": row[4],
                    }
                )

            for row in ctx.db.execute(
                "SELECT owner_kind, owner_coordinates_json, observed_at_us, coverage_state, "
                "service_instance_uuidv4, resource_kind, provider_resource_id, collection_kind, "
                "provenance_json, terminal_observed_at_us, terminal_state, members_json "
                "FROM coverage_proofs ORDER BY observed_at_us, owner_kind, owner_coordinates_json"
            ):
                if (row[0], row[1]) not in exported_ctx_scopes:
                    continue
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

            for row in ctx.db.execute(
                "SELECT owner_kind, owner_coordinates_json, observed_at_us, coverage_state, "
                "source_registration_uuidv4, scope_json, inventory_observed_at_us, "
                "inventory_state, terminal, members_json, provenance_json "
                "FROM source_coverage_proofs ORDER BY observed_at_us, owner_kind, owner_coordinates_json"
            ):
                if (row[0], row[1]) not in exported_ctx_scopes:
                    continue
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
            measurement = {"metadata_units": 0, "verification_bytes": 0}
            token = _WIRE_WORK.set(measurement)
            try:
                for unit, amount in (
                    ("input_bytes", MAX_PACKAGE_BYTES),
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
                    "input_bytes": input_bytes,
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
            oid = ref.get("full_oid")
            if fmt and oid:
                object_oids.add(OID(fmt, oid))

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
            if package.context is not None and want_context:
                from repo_catalog.domain.selective_exchange import preflight_i2_context

                preflight_i2_context(package.context)
                self._prevalidate_context_section(package.context)
                validate_context(package.context)
        cut("after_preflight")
        core_data = copy.deepcopy(package.core)
        context_data = copy.deepcopy(package.context)
        omissions = filter_sections(
            core_data, context_data, package.selection_scope, permitted=permitted
        )
        if selection != package.selection_scope:
            omissions.extend(
                filter_sections(core_data, context_data, selection, permitted=permitted)
            )
        # Fence the receiver-selected atomic unit before dependency rewriting,
        # package replay/binding, or either authority's effects.
        if want_context and context_data is not None:
            from repo_catalog.domain.selective_exchange import preflight_i2_context

            preflight_i2_context(context_data)
        limited, _ = bound_sections(core_data, context_data, selection)
        omissions.extend(limited)
        omissions.extend(
            filter_sections(core_data, context_data, selection, permitted=permitted)
        )
        # Nothing outside the receiver permission can enter even when it is a
        # required dependency of an otherwise selected unit.
        self._receive_selection = selection
        self._dependency_rows = 0
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
                    ("object_format", "full_oid", "field", "provenance_json"),
                    ("value_json",),
                ),
                (
                    "relation_groups",
                    (
                        "object_format",
                        "full_oid",
                        "relation",
                        "scope",
                        "provenance_json",
                    ),
                    ("status", "membership_json"),
                ),
                (
                    "notes_claims",
                    (
                        "capture_origin_uuidv4",
                        "capture_uuidv4",
                        "object_format",
                        "target",
                        "provenance_json",
                    ),
                    ("note",),
                ),
                (
                    "notes_groups",
                    (
                        "capture_origin_uuidv4",
                        "capture_uuidv4",
                        "object_format",
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
                    if section == "notes_groups":
                        prior = core.original_notes_group_payload(
                            (row["capture_origin_uuidv4"], row["capture_uuidv4"]),
                            row["object_format"],
                            row["scope"],
                            row["provenance_json"],
                        )
                        found = [] if prior is None else [prior]
                    else:
                        found = core.sql(
                            "SELECT "
                            + ",".join(column(k) for k in payload)
                            + " FROM "
                            + section
                            + " WHERE "
                            + " AND ".join(column(k) + "=?" for k in keys),
                            tuple(row[k] for k in keys),
                        )
                    if found:
                        self._dependency_rows += 1
                        if tuple(found[0]) != tuple(row[k] for k in payload):
                            raise ExchangeError(
                                "IMMUTABLE_REPLAY_CONFLICT", ["core", section]
                            )
            repos = {
                r[0] for r in core.sql("SELECT repository_uuidv4 FROM repositories")
            }
            for row in data["captures"]:
                existing = core.capture_binding(
                    (row["capture_origin_uuidv4"], row["capture_uuidv4"])
                )
                if existing is not None:
                    self._dependency_rows += 1
                    incoming = Capture(
                        row["capture_origin_uuidv4"],
                        row["capture_uuidv4"],
                        row["repository_uuidv4"],
                        row["source"],
                        _decode_capture_ref(row["ref"]),
                        OID(row["object_format"], row["root"]),
                    )
                    if existing != incoming:
                        raise ExchangeError(
                            "IMMUTABLE_REPLAY_CONFLICT", ["core", "captures"]
                        )
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
                for r in core.sql("SELECT object_format,full_oid FROM git_objects")
            }
            captures = {
                tuple(r)
                for r in core.sql(
                    "SELECT capture_origin_uuidv4,capture_uuidv4 FROM captures"
                )
            }
        self._dependency_rows += len(repos) + len(captures) + len(oids)
        repos.update(r["repository_uuidv4"] for r in data["repositories"])
        oids.update((r["object_format"], r["full_oid"]) for r in data["git_objects"])

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

        for key in ("repository_claims", "git_observations", "captures"):
            keep(key, lambda r: r["repository_uuidv4"] in repos)
        captures.update(
            (r["capture_origin_uuidv4"], r["capture_uuidv4"]) for r in data["captures"]
        )
        for key in (
            "notes_claims",
            "notes_groups",
            "notes_inventories",
            "note_roles",
            "retained_notes",
        ):
            keep(
                key,
                lambda r: (r["capture_origin_uuidv4"], r["capture_uuidv4"]) in captures,
            )

        def scope_available(r):
            coordinates = json.loads(r["owner_coordinates_json"])
            if r["owner_kind"] == "repository":
                return coordinates[0] in repos
            if r["owner_kind"] == "capture":
                return tuple(coordinates[:2]) in captures
            return tuple(coordinates[:2]) in oids

        for key in ("coverage_scopes", "coverage_claims", "coverage_proofs"):
            keep(key, scope_available)
        return omissions

    def _context_dependencies(self, data):
        """Classify missing dependencies without registering synthetic parents."""
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
        captures_by_pair: dict[tuple[str, str], Capture] = {}
        for c_item in core_data["captures"]:
            cap = Capture(
                c_item["capture_origin_uuidv4"],
                c_item["capture_uuidv4"],
                c_item["repository_uuidv4"],
                c_item["source"],
                _decode_capture_ref(c_item["ref"]),
                OID(c_item["object_format"], c_item["root"]),
            )
            captures_by_pair[cap.pair] = cap

        for meta in core_data["retained_metadata"]:
            oid = OID(meta["object_format"], meta["full_oid"])
            native_type = meta["native_type"]
            if native_type == "blob":
                raise CoreFailure(
                    "RETENTION_PURPOSE",
                    oid,
                    "ordinary file blob bodies are excluded from retained_metadata",
                )
            try:
                body = bytes.fromhex(meta["body_hex"])
            except (ValueError, TypeError) as exc:
                raise CoreFailure(
                    "NATIVE_INTEGRITY", oid, "invalid hex body in retained_metadata"
                ) from exc
            native = NativeObject(
                oid,
                native_type,
                body,
                meta["size"],
                str(meta["digest_sha256"]),
            )
            native.validate()
            parse_metadata(oid.object_format, native_type, body)

        for inv_item in core_data["notes_inventories"]:
            pair = (
                inv_item["capture_origin_uuidv4"],
                inv_item["capture_uuidv4"],
            )
            if pair not in captures_by_pair:
                raise CoreFailure(
                    "NOTES_INVENTORY", pair, "missing Capture for notes_inventory"
                )
            cap = captures_by_pair[pair]
            structures = tuple(
                NativeObject(
                    OID(s["object_format"], s["full_oid"]),
                    s["native_type"],
                    bytes.fromhex(s["body_hex"]),
                    s["declared_size"],
                    str(s["digest_sha256"]),
                )
                for s in inv_item["structures"]
            )
            fail_raw = inv_item.get("failure")
            failure = (
                None
                if fail_raw is None
                else CoreFailure(fail_raw[0], cap.pair, fail_raw[1])
            )
            members = tuple(tuple(m) for m in inv_item["members"])
            inv = NotesInventory(cap, inv_item["status"], members, structures, failure)
            verify_inventory(inv, work)

        for nr in core_data["note_roles"]:
            pair = (nr["capture_origin_uuidv4"], nr["capture_uuidv4"])
            cap = captures_by_pair.get(pair)
            if cap is None:
                raise CoreFailure("NOTES_PROOF", pair, "missing Capture for note_role")
            if (nr["object_format"], nr["root"]) != cap.root.key:
                raise ExchangeError("NOTES_CAPTURE_ROOT", "note_roles")
            proof = _notes_proof_from_bundle_json(
                cap,
                OID(nr["object_format"], nr["target"]),
                OID(nr["object_format"], nr["note"]),
                nr["path"],
                nr["proof_bundle_json"],
            )
            proof.validate()

        for rn in core_data["retained_notes"]:
            pair = (rn["capture_origin_uuidv4"], rn["capture_uuidv4"])
            cap = captures_by_pair.get(pair)
            if cap is None:
                raise CoreFailure(
                    "NOTES_PROOF", pair, "missing Capture for retained_note"
                )
            if (rn["object_format"], rn["root"]) != cap.root.key:
                raise ExchangeError("NOTES_CAPTURE_ROOT", "retained_notes")
            note_oid = OID(rn["object_format"], rn["full_oid"])
            target_oid = OID(rn["object_format"], rn["target"])
            proof = _notes_proof_from_bundle_json(
                cap,
                target_oid,
                note_oid,
                rn["path"],
                rn["proof_bundle_json"],
            )
            proof.validate()
            try:
                body = bytes.fromhex(rn["body_hex"])
            except (ValueError, TypeError) as exc:
                raise CoreFailure(
                    "NATIVE_INTEGRITY", note_oid, "invalid hex body in retained_notes"
                ) from exc
            native = NativeObject(
                note_oid,
                "blob",
                body,
                rn["size"],
                str(rn["digest_sha256"]),
            )
            native.validate()

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
        extra_count_sql = "SELECT (SELECT count(*) FROM repositories)+(SELECT count(*) FROM repository_claims)+(SELECT count(*) FROM git_observations)+(SELECT count(*) FROM captures)+(SELECT count(*) FROM notes_claims)+(SELECT count(*) FROM notes_groups)+(SELECT count(*) FROM coverage_scopes)+(SELECT count(*) FROM coverage_claims)+(SELECT count(*) FROM core_coverage_proofs)"
        before_extra_count = core_cap.sql(extra_count_sql)[0][0]
        before_obj_count = core_cap.sql("SELECT COUNT(*) FROM git_objects")[0][0]
        before_claim_count = core_cap.sql("SELECT COUNT(*) FROM scalar_claims")[0][0]
        before_group_count = core_cap.sql("SELECT COUNT(*) FROM relation_groups")[0][0]
        before_meta_count = core_cap.sql("SELECT COUNT(*) FROM retained_metadata")[0][0]
        before_role_count = core_cap.sql("SELECT COUNT(*) FROM note_roles")[0][0]
        before_note_count = core_cap.sql("SELECT COUNT(*) FROM retained_notes")[0][0]

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
            oid = OID(obj["object_format"], obj["full_oid"])
            core_cap.admit_object(oid)
            admitted_objects += 1

        # Admit retained_metadata first so receiver_intrinsic claims/groups are generated by receiver
        verified_intrinsic_claims: set[tuple[str, str, str, str, str]] = set()
        verified_intrinsic_groups: set[tuple[str, str, str, str, str, str]] = set()
        admitted_meta = 0
        for meta in core_data["retained_metadata"]:
            _performed("metadata_units", 1)
            oid = OID(meta["object_format"], meta["full_oid"])
            body = bytes.fromhex(meta["body_hex"])
            native = NativeObject(
                oid,
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
            oid = OID(sc["object_format"], sc["full_oid"])
            prov = Provenance(*json.loads(sc["provenance_json"]))
            val_dec = json.loads(sc["value_json"])
            orig_val = None if val_dec == ["unknown"] else val_dec[1]
            claim = ScalarClaim(oid, sc["field"], orig_val, prov)
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
            oid = OID(rg["object_format"], rg["full_oid"])
            prov = Provenance(*json.loads(rg["provenance_json"]))
            members = tuple(
                RelationMember(
                    tuple(m[0]) if isinstance(m[0], list) else m[0],
                    OID(m[1], m[2]),
                )
                for m in json.loads(rg["membership_json"])
            )
            group = RelationGroup(
                oid,
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

        captures_by_pair: dict[tuple[str, str], Capture] = {}
        for cap_item in core_data["captures"]:
            _performed("metadata_units", 1)
            decoded_ref = _decode_capture_ref(cap_item["ref"])
            cap = Capture(
                cap_item["capture_origin_uuidv4"],
                cap_item["capture_uuidv4"],
                cap_item["repository_uuidv4"],
                cap_item["source"],
                decoded_ref,
                OID(cap_item["object_format"], cap_item["root"]),
            )
            captures_by_pair[cap.pair] = cap
            core_cap.admit_capture(cap)

        for nc in core_data["notes_claims"]:
            _performed("metadata_units", 1)
            cap = captures_by_pair[(nc["capture_origin_uuidv4"], nc["capture_uuidv4"])]
            prov = Provenance(*json.loads(nc["provenance_json"]))
            core_cap.admit_notes_claim(
                NotesClaim(
                    cap,
                    OID(nc["object_format"], nc["target"]),
                    OID(nc["object_format"], nc["note"]),
                    prov,
                )
            )

        verified_inventory_captures: set[tuple[str, str]] = set()
        for inv_item in core_data["notes_inventories"]:
            _performed("metadata_units", 1)
            cap = captures_by_pair[
                (
                    inv_item["capture_origin_uuidv4"],
                    inv_item["capture_uuidv4"],
                )
            ]
            structures = tuple(
                NativeObject(
                    OID(s["object_format"], s["full_oid"]),
                    s["native_type"],
                    bytes.fromhex(s["body_hex"]),
                    s["declared_size"],
                    str(s["digest_sha256"]),
                )
                for s in inv_item["structures"]
            )
            fail_raw = inv_item.get("failure")
            failure = (
                None
                if fail_raw is None
                else CoreFailure(fail_raw[0], cap.pair, fail_raw[1])
            )
            members = tuple(tuple(m) for m in inv_item["members"])
            inv = NotesInventory(cap, inv_item["status"], members, structures, failure)
            core_cap.admit_notes_inventory(inv, work)
            verified_inventory_captures.add(cap.pair)

        for ng in core_data["notes_groups"]:
            _performed("metadata_units", 1)
            cap = captures_by_pair[(ng["capture_origin_uuidv4"], ng["capture_uuidv4"])]
            prov = Provenance(*json.loads(ng["provenance_json"]))
            authority = ng.get("authority", "reported")
            if authority == "intrinsic" or prov.qualification == "receiver_intrinsic":
                if cap.pair not in verified_inventory_captures:
                    ignored_groups += 1
                continue
            members = tuple(tuple(m) for m in json.loads(ng["membership_json"]))
            core_cap.admit_notes_group(
                NotesGroup(cap, ng["scope"], ng["status"], members, prov)
            )

        admitted_roles = 0
        for nr in core_data["note_roles"]:
            _performed("metadata_units", 1)
            cap = captures_by_pair[(nr["capture_origin_uuidv4"], nr["capture_uuidv4"])]
            proof = _notes_proof_from_bundle_json(
                cap,
                OID(nr["object_format"], nr["target"]),
                OID(nr["object_format"], nr["note"]),
                nr["path"],
                nr["proof_bundle_json"],
            )
            core_cap.admit_notes_role(proof, work)
            admitted_roles += 1

        admitted_notes = 0
        for rn in core_data["retained_notes"]:
            _performed("metadata_units", 1)
            cap = captures_by_pair[(rn["capture_origin_uuidv4"], rn["capture_uuidv4"])]
            note_oid = OID(rn["object_format"], rn["full_oid"])
            target_oid = OID(rn["object_format"], rn["target"])
            proof = _notes_proof_from_bundle_json(
                cap,
                target_oid,
                note_oid,
                rn["path"],
                rn["proof_bundle_json"],
            )
            native = NativeObject(
                note_oid,
                "blob",
                bytes.fromhex(rn["body_hex"]),
                rn["size"],
                str(rn["digest_sha256"]),
            )
            core_cap.admit_note(proof, native, rn["physical_copy_uuidv4"], work)
            admitted_notes += 1

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

        after_obj_count = core_cap.sql("SELECT COUNT(*) FROM git_objects")[0][0]
        after_claim_count = core_cap.sql("SELECT COUNT(*) FROM scalar_claims")[0][0]
        after_group_count = core_cap.sql("SELECT COUNT(*) FROM relation_groups")[0][0]
        after_meta_count = core_cap.sql("SELECT COUNT(*) FROM retained_metadata")[0][0]
        after_role_count = core_cap.sql("SELECT COUNT(*) FROM note_roles")[0][0]
        after_note_count = core_cap.sql("SELECT COUNT(*) FROM retained_notes")[0][0]

        new_rows = (
            (after_obj_count - before_obj_count)
            + (after_claim_count - before_claim_count)
            + (after_group_count - before_group_count)
            + (after_meta_count - before_meta_count)
            + (after_role_count - before_role_count)
            + (after_note_count - before_note_count)
        )

        new_rows += core_cap.sql(extra_count_sql)[0][0] - before_extra_count
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
                oid = OID(oid_pair[0], oid_pair[1])
                ref_key = (
                    rk,
                    role,
                    oid.object_format,
                    oid.full_oid,
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
                if validate_core(oid.object_format, oid.full_oid):
                    ctx.link_core(
                        rk,
                        role,
                        oid.object_format,
                        oid.full_oid,
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
                                *oid.key,
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
            oid = OID(cr["object_format"], cr["full_oid"])
            role = cr["role"]
            prov_json = cr["provenance_json"]
            ref_key = (rk, role, oid.object_format, oid.full_oid, prov_json)
            if ref_key in seen_core_refs:
                continue
            seen_core_refs.add(ref_key)
            if validate_core(oid.object_format, oid.full_oid):
                ctx.link_core(
                    rk,
                    role,
                    oid.object_format,
                    oid.full_oid,
                    prov_json,
                    validate_core,
                )
                linked_refs += 1
            else:
                missing_refs.append(
                    {
                        "section": "core_references",
                        "unit": [list(rk.coordinates()), role, *oid.key, prov_json],
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
