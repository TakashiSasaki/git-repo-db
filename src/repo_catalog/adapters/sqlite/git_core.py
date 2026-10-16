"""Production append-only Git Core, using the exact four-store P1 contracts.

The P1 adapter supplies enforcement, immutable semantic replay, coherent reads,
notes roles and Coverage. This adapter completes native parsing and checked
scalar admission; it intentionally exposes no public initializer or file archive.
"""

from __future__ import annotations

import json

from repo_catalog.adapters.sqlite.p1_core import Core, _completed_read
from repo_catalog.domain.git_native import DECODER, DECODER_VERSION, parse_metadata
from repo_catalog.domain.notes import (
    GRAMMAR,
    NotesInventory,
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

    def ensure_available(self) -> None:
        """Fence opt-in acquisition before any source I/O or request work."""
        self._available()

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
                        if (
                            provenance.source != "receiver-intrinsic"
                            or provenance.observation != encode(capture.key)
                            or provenance.decoder != "git-native-notes-inventory"
                            or provenance.decoder_version != "1"
                            or row[0] != "all-notes-mappings"
                        ):
                            raise ValueError("invalid receiver inventory provenance")
                        coordinate = json.loads(provenance.coordinate)
                        kind, grammar, evidence, diagnostic = coordinate
                        if (
                            kind != "inventory"
                            or grammar != GRAMMAR
                            or encode(coordinate) != provenance.coordinate
                        ):
                            raise ValueError(
                                "unsupported or noncanonical inventory evidence"
                            )
                        structures = tuple(
                            NativeObject(
                                OID(fmt, oid),
                                native_type,
                                bytes.fromhex(body),
                                size,
                                digest,
                            )
                            for fmt, oid, native_type, body, size, digest in evidence
                        )
                        if any(
                            native.body.hex() != entry[3]
                            for native, entry in zip(structures, evidence, strict=True)
                        ):
                            raise ValueError("noncanonical structural byte encoding")
                        if diagnostic is not None and (
                            not isinstance(diagnostic, list)
                            or len(diagnostic) != 2
                            or any(
                                not isinstance(value, str) or not value
                                for value in diagnostic
                            )
                        ):
                            raise ValueError("invalid inventory diagnostic")
                        failure = (
                            None
                            if diagnostic is None
                            else CoreFailure(diagnostic[0], capture.pair, diagnostic[1])
                        )
                        inventory = NotesInventory(
                            capture,
                            row[1],
                            tuple(tuple(m) for m in json.loads(row[2])),
                            structures,
                            failure,
                        )
                        verify_inventory(inventory, _InventoryReadWork())
                    except (
                        ValueError,
                        TypeError,
                        KeyError,
                        IndexError,
                        AttributeError,
                    ) as error:
                        self._integrity_stop(
                            (capture.pair, "notes-inventory", str(error))
                        )
                    result.append(inventory)
                return tuple(result)
        finally:
            self._checked_byte_read = previous


class _InventoryReadWork:
    """Read-time checking has no acquisition request or mutable success ledger."""

    def require(self, unit, amount=1):
        pass

    def charge(self, unit, amount):
        pass
