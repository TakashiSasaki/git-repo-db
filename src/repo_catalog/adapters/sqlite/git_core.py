"""Production append-only Git Core, using the exact four-store P1 contracts.

The P1 adapter supplies enforcement, immutable semantic replay, coherent reads,
notes roles and Coverage. This adapter completes native parsing and checked
scalar admission; it intentionally exposes no public initializer or file archive.
"""

from __future__ import annotations

from repo_catalog.adapters.sqlite.p1_core import Core
from repo_catalog.domain.git_native import DECODER, DECODER_VERSION, parse_metadata
from repo_catalog.domain.p1_core import (
    OID,
    CoreFailure,
    NativeObject,
    NotesProof,
    Provenance,
    ScalarClaim,
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

    def _authorize(self, action, table, column, database, trigger):
        import sqlite3

        protected = (
            column == "body" and table in ("retained_metadata", "retained_notes")
        ) or (column == "proof_bundle" and table in ("note_roles", "retained_notes"))
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

    def read_note(self, capture, target: OID, note: OID) -> bytes:
        self._checked_byte_read = True
        try:
            return super().read_note(capture, target, note)
        finally:
            self._checked_byte_read = False

    def notes_projection(self, capture, target: OID):
        self._checked_byte_read = True
        try:
            return super().notes_projection(capture, target)
        finally:
            self._checked_byte_read = False

    def admit_notes_role(self, proof: NotesProof, work) -> None:
        # P1 valid_note_role delegates full production grammar before trusting
        # the relevant mapping, including every supplied commit/tree structure.
        return super().admit_notes_role(proof, work)
