"""Production append-only Git Core, using the exact four-store P1 contracts.

The P1 adapter supplies enforcement, immutable semantic replay, coherent reads,
notes roles and Coverage. This adapter completes native parsing and checked
scalar admission; it intentionally exposes no public initializer or file archive.
"""

from __future__ import annotations

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
    CoreFailure,
    NativeObject,
    NotesGroup,
    NotesProof,
    Provenance,
    ScalarClaim,
    account_verification,
    encode,
)


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
        read_snapshot.identity("core")
        result = cls.__new__(cls)
        result._directory = Path(directory)
        result._db = read_snapshot._db
        result._snapshot_owner = read_snapshot
        result._external = result._active = True
        result._admitting = result._reading = result._stopped = False
        result._on_corruption = None
        result._db.set_authorizer(result._authorize)
        try:
            yield result
            result._complete_read(None)
        finally:
            result._active = False
            # The coordinator owns connection teardown and its read guard.
            from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator

            PairCoordinator(directory)._guard_read(result._db)

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

    def _authorize(self, action, table, column, database, trigger):
        import sqlite3

        protected = (
            column == "body" and table in ("retained_metadata", "retained_notes")
        ) or (column == "proof_bundle" and table in ("note_roles", "retained_notes"))
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
