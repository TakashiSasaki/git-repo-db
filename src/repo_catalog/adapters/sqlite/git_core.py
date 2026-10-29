"""Production append-only Git Core, using the exact four-store P1 contracts.

The P1 adapter supplies enforcement, immutable semantic replay, coherent reads,
notes roles and Coverage. This adapter completes native parsing and checked
scalar admission; it intentionally exposes no public initializer or file archive.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from repo_catalog.adapters.sqlite.p1_core import Core, _completed_read, _decoded_read
from repo_catalog.domain.git_native import DECODER, DECODER_VERSION, parse_metadata
from repo_catalog.domain.notes import (
    GRAMMAR,
    NotesInventory,
    decode_inventory_group,
    mapping_proof,
    verify_inventory,
)
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreFailure,
    NativeObject,
    NotesGroup,
    NotesProof,
    Provenance,
    ScalarClaim,
    _notes_group,
    account_verification,
    encode,
    uuid4_value,
)
from repo_catalog.domain.ref_observation import NotesMappingEvidenceRecord


class _CheckedReadLimits:
    def __init__(self, budget):
        self.budget = budget

    @property
    def note_bytes(self):
        return self.budget._invoke(lambda: self.budget.work.limits.note_bytes)


class _CheckedReadBudget:
    """Do not lend a typed-read capability to caller-supplied callbacks."""

    def __init__(self, core, work):
        self.core, self.work = core, work
        self.limits = _CheckedReadLimits(self)

    def _invoke(self, operation):
        prior = getattr(self.core, "_checked_byte_read", False)
        self.core._checked_byte_read = False
        try:
            return operation()
        finally:
            self.core._checked_byte_read = prior

    def require(self, unit, amount=1):
        return self._invoke(lambda: self.work.require(unit, amount))

    def charge(self, unit, amount):
        return self._invoke(lambda: self.work.charge(unit, amount))

    def __getattr__(self, name):
        if name != "abandon":
            raise AttributeError(name)
        self._invoke(lambda: getattr(self.work, name))
        return lambda unit: self._invoke(lambda: self.work.abandon(unit))


class GitCore(Core):
    """Durable production CoreAdmission/CoreRead with scoped typed failures.

    Admission parsing errors concern the incoming native object (NATIVE_SYNTAX),
    not catalog corruption. Already admitted conflicting reports remain reports.
    Byte reads verify the actual selected copy and invoke the persistent stop on
    corruption. Generic SQL is metadata inspection only: retained payload/proof
    byte columns are accessible only through the checked typed read methods.
    """

    @classmethod
    @contextmanager
    def for_snapshot(cls, read_snapshot, directory):
        """Checked, expiring typed reader over a coordinator-owned snapshot.

        Only this trusted adapter binds the underlying connection. Application
        callers never construct partially initialized capabilities or alter the
        coordinator authorizer. The original snapshot remains the lifetime owner.
        """
        from repo_catalog.adapters.sqlite.p1_coordination import ReadSnapshot

        if not isinstance(read_snapshot, ReadSnapshot):
            raise CoreFailure("SNAPSHOT_REQUIRED", "core")
        read_snapshot._available()
        if not read_snapshot.in_transaction:
            raise CoreFailure("TRANSACTION", "core")
        owner_directory = read_snapshot.catalog_directory
        if Path(directory).resolve() != owner_directory:
            raise CoreFailure("SNAPSHOT_OWNER", "core", "foreign catalog directory")
        read_snapshot.identity("core")
        result = cls.__new__(cls)
        result._directory = owner_directory
        result._db = read_snapshot._db
        result._snapshot_owner = read_snapshot
        result._external = result._active = True
        result._admitting = result._reading = result._stopped = False
        result._on_corruption = read_snapshot._on_error
        result._db.set_authorizer(result._authorize)
        try:
            yield result
            result._complete_read(None)
        finally:
            result._active = False
            # The coordinator owns connection teardown and its read guard.
            from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator

            PairCoordinator(owner_directory)._guard_read(result._db)

    def _available(self):
        super()._available()
        owner = getattr(self, "_snapshot_owner", None)
        if owner is not None:
            owner._available()

    def ensure_available(self) -> None:
        """Fence opt-in acquisition before any source I/O or request work."""
        self._available()

    @_completed_read
    @_decoded_read
    def catalog_identity(self):
        """Checked physical binding for opt-in acquisition request composition."""
        with self._snapshot():
            rows = self.sql(
                "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity"
            )
            if len(rows) != 1:
                self._integrity_stop("missing Core identity")
            from repo_catalog.domain.p1_core import uuid4_value

            return tuple(
                self._stored("Core identity", uuid4_value, value) for value in rows[0]
            )

    @_completed_read
    @_decoded_read
    def capture_binding(self, pair: tuple[str, str]) -> Capture | None:
        """Reconstruct one original binding and verify its required parents.

        Invalid caller coordinates are input errors; invalid stored authority
        enters the existing persistent stop boundary before acquisition can
        mistake damage for a conflict or recreate a missing parent.
        """
        if type(pair) is not tuple or len(pair) != 2:
            raise CoreFailure("CAPTURE", "binding", "actual Capture pair required")
        for value in pair:
            uuid4_value(value)
        with self._snapshot():
            rows = self.sql(
                "SELECT capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,source,ref,object_format,root "
                "FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                pair,
            )
            if not rows:
                return None

            def decode(row):
                origin, capture, repository, source, stored_ref, fmt, oid = row
                ref = json.loads(stored_ref)
                if type(ref) is not list or len(ref) != 2 or ref[0] != "native-ref":
                    raise ValueError("invalid stored Capture ref")
                actual = Capture(
                    origin,
                    capture,
                    repository,
                    source,
                    bytes.fromhex(ref[1]).decode("utf-8", "surrogateescape"),
                    OID(fmt, oid),
                )
                if actual.key != tuple(row):
                    raise ValueError("noncanonical stored Capture binding")
                return actual

            result = self._stored("Capture binding", decode, rows[0])
            repository = self.sql(
                "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
                (result.repository_uuidv4,),
            )
            root = self.sql(
                "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                result.root.key,
            )
            if not repository or not root:
                self._integrity_stop(("Capture binding", "missing required parent"))
            return result

    def _authorize(self, action, table, column, database, trigger):
        import sqlite3

        protected = (
            column == "body" and table in ("retained_metadata", "retained_notes")
        ) or (column == "proof_bundle" and table in ("note_roles", "retained_notes"))
        # Ref-observation roles have the same retained-byte boundary as the
        # legacy Capture roles. Generic metadata SQL cannot emit their bodies or
        # structural proofs without the claim-scoped typed validation below.
        protected = (
            protected
            or (table == "ref_retained_notes" and column in ("body", "proof_bundle"))
            or (table == "notes_mapping_evidence" and column == "proof_bundle")
        )
        protected = protected or (
            table == "ref_coverage_proofs" and column == "structures_json"
        )
        # P4 receiver inventory provenance contains exact structural evidence.
        # It must follow the same checked output boundary as proof_bundle.
        protected = protected or (table == "notes_groups" and column == "provenance")
        if (
            action == sqlite3.SQLITE_READ
            and protected
            and not (self._admitting or getattr(self, "_checked_byte_read", False))
        ):
            return sqlite3.SQLITE_DENY
        return super()._authorize(action, table, column, database, trigger)

    def notes_mapping_projection(
        self,
        ref_claim,
        annotated_object_oid,
        interpretation_kind,
        interpretation_version,
        interpretation_scope,
        work,
        *,
        max_units=10_000,
        max_bytes=64 * 1024 * 1024,
    ):
        guarded_work = _CheckedReadBudget(self, work)
        prior = getattr(self, "_checked_byte_read", False)
        self._checked_byte_read = True
        try:
            return super().notes_mapping_projection(
                ref_claim,
                annotated_object_oid,
                interpretation_kind,
                interpretation_version,
                interpretation_scope,
                guarded_work,
                max_units=max_units,
                max_bytes=max_bytes,
            )
        finally:
            self._checked_byte_read = prior

    def read_ref_note(
        self,
        claim,
        mapping,
        work,
        *,
        max_proof_bytes=64 * 1024 * 1024,
        max_metadata_bytes=64 * 1024 * 1024,
    ):
        guarded_work = _CheckedReadBudget(self, work)
        prior = getattr(self, "_checked_byte_read", False)
        self._checked_byte_read = True
        try:
            return super().read_ref_note(
                claim,
                mapping,
                guarded_work,
                max_proof_bytes=max_proof_bytes,
                max_metadata_bytes=max_metadata_bytes,
            )
        finally:
            self._checked_byte_read = prior

    @_completed_read
    @_decoded_read
    def read_ref_note_copy(
        self,
        oid: OID,
        physical_copy_uuidv4: str,
        work,
        *,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        max_proof_bytes: int = 64 * 1024 * 1024,
    ):
        """Return one exact physical copy and its locally rechecked role.

        The copy identifier is caller-supplied and never substitutes for the
        immutable Claim or mapping. All variable-width input is reserved before
        fetching; role and body verification are charged to the same budget.
        """
        if not isinstance(oid, OID):
            raise CoreFailure("IDENTITY", oid, "typed note OID required")
        uuid4_value(physical_copy_uuidv4)
        self._available()
        work = _CheckedReadBudget(self, work)
        prior = getattr(self, "_checked_byte_read", False)
        self._checked_byte_read = True
        try:
            with self._snapshot():
                row = self._fetch_ref_note_copy(
                    oid, physical_copy_uuidv4, work, max_proof_bytes, max_metadata_bytes
                )
                if row is None:
                    raise CoreFailure(
                        "NOTES_ROLE_UNAVAILABLE", oid, "physical note copy not found"
                    )
                claim, mapping, body = self._validate_stored_ref_note(
                    row, work, max_metadata_bytes, max_proof_bytes
                )
                evidence = self._stored(
                    claim.identity,
                    NotesMappingEvidenceRecord,
                    mapping,
                    row["verification_scope"],
                    self._provenance_value(
                        claim.identity,
                        row["role_provenance"],
                        work=work,
                        max_metadata_bytes=max_metadata_bytes,
                    ),
                    row["proof_bundle"],
                )
                native = NativeObject(
                    oid, "blob", body, row["size"], row["digest_sha256"]
                )
                return claim, evidence, native
        finally:
            self._checked_byte_read = prior

    def _read_ref_coverage_proofs(self, claim, work, **kwargs):
        guarded_work = _CheckedReadBudget(self, work)
        prior = getattr(self, "_checked_byte_read", False)
        self._checked_byte_read = True
        try:
            return super()._read_ref_coverage_proofs(claim, guarded_work, **kwargs)
        finally:
            self._checked_byte_read = prior

    def _metadata(self, native: NativeObject, copy: str) -> None:
        try:
            parsed = parse_metadata(
                native.oid.object_format, native.native_type, native.body
            )
        except CoreFailure as error:
            if error.code == "NATIVE_SYNTAX":
                raise CoreFailure(error.code, native.oid, str(error)) from error
            raise
        # The inherited entire unit installs the physical copy, type/size and
        # whole checked relation groups in this same Core transaction.
        super()._metadata(native, copy)
        for field, value in parsed.scalars.items():
            if field in ("type", "size", "tree_count"):
                continue
            provenance = Provenance(
                "receiver-intrinsic",
                encode(native.oid.key),
                "native-" + field,
                DECODER,
                DECODER_VERSION,
                "receiver_intrinsic",
            )
            claim = ScalarClaim(native.oid, field, value, provenance)
            self._claim(claim)
            self._insert("intrinsic_claims", (*claim.key, copy))

    @_completed_read
    def read_metadata(self, oid: OID) -> bytes:
        self._checked_byte_read = True
        try:
            with self._snapshot():
                missing = self.sql(
                    "SELECT 1 FROM intrinsic_claims i LEFT JOIN retained_metadata r "
                    "ON r.object_format=i.object_format AND r.full_oid=i.full_oid "
                    "AND r.physical_copy_uuidv4=i.physical_copy_uuidv4 "
                    "WHERE i.object_format=? AND i.full_oid=? AND r.physical_copy_uuidv4 IS NULL "
                    "UNION ALL SELECT 1 FROM intrinsic_groups i LEFT JOIN retained_metadata r "
                    "ON r.object_format=i.object_format AND r.full_oid=i.full_oid "
                    "AND r.physical_copy_uuidv4=i.physical_copy_uuidv4 "
                    "WHERE i.object_format=? AND i.full_oid=? AND r.physical_copy_uuidv4 IS NULL",
                    (*oid.key, *oid.key),
                )
                if missing:
                    self._integrity_stop((oid, "lost-retained-metadata-copy"))
                return super().read_metadata(oid)
        finally:
            self._checked_byte_read = False

    @_completed_read
    def read_note(self, capture, target: OID, note: OID) -> bytes:
        self._checked_byte_read = True
        try:
            return super().read_note(capture, target, note)
        finally:
            self._checked_byte_read = False

    @_completed_read
    def notes_projection(self, capture, target: OID):
        self._checked_byte_read = True
        try:
            with self._snapshot():
                self.notes_inventories(capture)
                return super().notes_projection(capture, target)
        finally:
            self._checked_byte_read = False

    def admit_notes_role(self, proof: NotesProof, work) -> None:
        # P1 valid_note_role delegates full production grammar before trusting
        # the relevant mapping, including every supplied commit/tree structure.
        return super().admit_notes_role(proof, work)

    def admit_notes_inventory(self, inventory: NotesInventory, work) -> None:
        """Admit one receiver-recomputed whole group without body dependencies.

        Exact structural evidence forms part of the group's semantic provenance;
        no generic sender group can claim this receiver-intrinsic qualification.
        The group and its positive object identities commit as one Core unit.
        """
        self._available()
        with account_verification(work):
            for native in inventory.structures:
                self._charge(work, "input_bytes", len(native.body))
            verify_inventory(inventory, work)
            supplied = {native.oid: native for native in inventory.structures}
            proofs = tuple(
                mapping_proof(
                    inventory.capture,
                    OID(inventory.capture.root.object_format, target),
                    supplied.__getitem__,
                    work,
                )
                for target, _note, _path in inventory.members
            )
            evidence = [
                [
                    *native.oid.key,
                    native.native_type,
                    native.body.hex(),
                    native.declared_size,
                    native.digest_sha256,
                ]
                for native in inventory.structures
            ]
            diagnostic = (
                None
                if inventory.failure is None
                else [inventory.failure.code, str(inventory.failure)]
            )
            provenance = Provenance(
                "receiver-intrinsic",
                encode(inventory.capture.key),
                encode(["inventory", GRAMMAR, evidence, diagnostic]),
                "git-native-notes-inventory",
                "1",
                "receiver_intrinsic",
            )
            group = NotesGroup(
                inventory.capture,
                "all-notes-mappings",
                inventory.status,
                inventory.members,
                provenance,
            )
            self._charge(work, "metadata_units", 1 + 3 * len(group.members))
            with self._transaction():
                self._capture(group.capture)
                for target, note, _path in group.members:
                    self._object(OID(group.capture.root.object_format, target))
                    self._object(OID(group.capture.root.object_format, note))
                self._insert("notes_groups", group.key)
                for proof in proofs:
                    self._insert("note_roles", proof.key)

    @_completed_read
    @_decoded_read
    def original_notes_group_payload(self, pair, object_format, scope, provenance_json):
        """Read one reported immutable UNIQUE binding through the checked boundary."""
        previous = getattr(self, "_checked_byte_read", False)
        self._checked_byte_read = True
        try:
            with self._snapshot():
                rows = self.sql(
                    "SELECT status,membership,provenance FROM notes_groups WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? AND scope=? AND provenance=?",
                    (*pair, object_format, scope, provenance_json),
                )
                if not rows:
                    return None
                row = rows[0]
                self._provenance_value(pair, row[2])
                if not _notes_group(object_format, row[0], row[1]):
                    self._integrity_stop((pair, "invalid-stored-notes-group"))
                return tuple(row[:2])
        finally:
            self._checked_byte_read = previous

    @_completed_read
    @_decoded_read
    def notes_inventories(self, capture) -> tuple[NotesInventory, ...]:
        """Emit distinct rechecked receiver inventories, never merged reports.

        Original reported alternatives remain available through notes_projection.
        No earlier group supplies terminal evidence to this group's capture.
        Persisted intrinsic structural damage stops the catalog before output.
        """
        previous = getattr(self, "_checked_byte_read", False)
        self._checked_byte_read = True
        try:
            with self._snapshot():
                bindings = self.sql(
                    "SELECT * FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                    capture.pair,
                )
                if bindings and tuple(bindings[0]) != capture.key:
                    raise CoreFailure(
                        "INCOMPATIBLE_REPLAY",
                        capture.pair,
                        "immutable Capture binding conflict",
                    )
                rows = self.sql(
                    "SELECT scope,status,membership,provenance FROM notes_groups "
                    "WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? "
                    "ORDER BY scope,status,membership,provenance",
                    (*capture.pair, capture.root.object_format),
                )
                result = []
                for row in rows:
                    provenance = self._provenance_value(capture.pair, row[3])
                    if provenance.qualification != "receiver_intrinsic":
                        continue
                    try:
                        inventory = decode_inventory_group(
                            encode(capture.key), row[0], row[1], row[2], row[3]
                        )
                    except (
                        ValueError,
                        TypeError,
                        KeyError,
                        IndexError,
                        AttributeError,
                        RecursionError,
                    ) as error:
                        self._integrity_stop(
                            (capture.pair, "notes-inventory", str(error))
                        )
                    result.append(inventory)
                return tuple(result)
        finally:
            self._checked_byte_read = previous
