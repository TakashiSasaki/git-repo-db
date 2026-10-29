"""Production append-only Git Core, using the exact four-store P1 contracts.

The P1 adapter supplies enforcement, immutable semantic replay, coherent reads,
notes roles and Coverage. This adapter completes native parsing and checked
scalar admission; it intentionally exposes no public initializer or file archive.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from repo_catalog.adapters.sqlite.p1_core import (
    Core,
    _completed_read,
    _decoded_read,
    _sqlite_authority_failure,
)
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
    valid_native,
)
from repo_catalog.domain.ref_observation import NotesMappingEvidenceRecord

# The exchange reader accepts only these fixed projections. In particular, it
# cannot be used as a typed-read capability for caller-provided SQL or to read
# retained proof/body columns.
_REF_EXCHANGE_ROWS = {
    "groups": (
        "notes_mapping_groups",
        (
            "object_format",
            "root_oid",
            "interpretation_kind",
            "interpretation_version",
            "interpretation_scope",
            "group_scope",
            "status",
            "membership",
            "provenance",
        ),
        "WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? ORDER BY object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,group_scope,provenance",
        3,
        False,
        False,
    ),
    "mappings": (
        "notes_mapping_claims",
        (
            "object_format",
            "root_oid",
            "interpretation_kind",
            "interpretation_version",
            "interpretation_scope",
            "annotated_object_oid",
            "note_oid",
            "mapping_path_json",
            "provenance",
        ),
        "WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? ORDER BY object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid,provenance",
        3,
        False,
        False,
    ),
    "evidence": (
        "notes_mapping_evidence",
        (
            "object_format",
            "root_oid",
            "interpretation_kind",
            "interpretation_version",
            "interpretation_scope",
            "annotated_object_oid",
        ),
        "WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? ORDER BY object_format,root_oid,interpretation_kind,interpretation_version,interpretation_scope,annotated_object_oid",
        3,
        True,
        False,
    ),
    "copies": (
        "ref_retained_notes",
        ("object_format", "full_oid", "physical_copy_uuidv4"),
        "WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? ORDER BY object_format,full_oid,physical_copy_uuidv4",
        3,
        False,
        False,
    ),
    "observations": (
        "ref_observations",
        ("observation_origin_uuidv4", "ref_observation_uuidv7"),
        "ORDER BY observation_origin_uuidv4,ref_observation_uuidv7",
        0,
        False,
        True,
    ),
    "enumerations": (
        "ref_enumeration_observations",
        ("observation_origin_uuidv4", "enumeration_uuidv7"),
        "ORDER BY observation_origin_uuidv4,enumeration_uuidv7",
        0,
        False,
        True,
    ),
    "root_claims": (
        "ref_observation_claims",
        ("observation_origin_uuidv4", "ref_observation_uuidv7"),
        "WHERE root_format=? AND root_oid=? ORDER BY observation_origin_uuidv4,ref_observation_uuidv7",
        2,
        True,
        True,
    ),
    "links": (
        "ref_enumeration_links",
        ("enumeration_origin_uuidv4", "enumeration_uuidv7"),
        "WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? ORDER BY enumeration_origin_uuidv4,enumeration_uuidv7",
        2,
        False,
        True,
    ),
}

# Fixed Core metadata selections used by Exchange, including historical rows.
# These contain no retained bodies or protected proof bundles.
_EXCHANGE_METADATA_ROWS = {
    "repositories": (
        "SELECT repository_uuidv4 FROM repositories ORDER BY repository_uuidv4",
        ("repository_uuidv4",),
        0,
    ),
    "repository_claims": (
        "SELECT repository_uuidv4,field,value,provenance FROM repository_claims ORDER BY repository_uuidv4,field,value,provenance",
        ("repository_uuidv4", "field", "value", "provenance"),
        0,
    ),
    "retained_metadata": (
        "SELECT object_format,full_oid,physical_copy_uuidv4,native_type,size,digest_sha256 FROM retained_metadata ORDER BY object_format,full_oid,physical_copy_uuidv4",
        (
            "object_format",
            "full_oid",
            "physical_copy_uuidv4",
            "native_type",
            "size",
            "digest_sha256",
        ),
        0,
    ),
    "scalar_claims": (
        "SELECT c.object_format,c.full_oid,c.field,c.value,c.provenance,EXISTS(SELECT 1 FROM intrinsic_claims i WHERE i.object_format=c.object_format AND i.full_oid=c.full_oid AND i.field=c.field AND i.value=c.value AND i.provenance=c.provenance) AS checked FROM scalar_claims c ORDER BY c.object_format,c.full_oid,c.field,c.value,c.provenance",
        ("object_format", "full_oid", "field", "value", "provenance", "checked"),
        0,
    ),
    "relation_groups": (
        "SELECT g.object_format,g.full_oid,g.relation,g.scope,g.status,g.membership,g.provenance,EXISTS(SELECT 1 FROM intrinsic_groups i WHERE i.object_format=g.object_format AND i.full_oid=g.full_oid AND i.relation=g.relation AND i.scope=g.scope AND i.status=g.status AND i.membership=g.membership AND i.provenance=g.provenance) AS checked FROM relation_groups g ORDER BY g.object_format,g.full_oid,g.relation,g.scope,g.status,g.membership,g.provenance",
        (
            "object_format",
            "full_oid",
            "relation",
            "scope",
            "status",
            "membership",
            "provenance",
            "checked",
        ),
        0,
    ),
    "relation_membership": (
        "SELECT relation,scope,status,membership,provenance FROM relation_groups WHERE object_format=? AND full_oid=? ORDER BY relation,scope,status,membership,provenance",
        ("relation", "scope", "status", "membership", "provenance"),
        2,
    ),
    "git_observations": (
        "SELECT capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,kind,scope,value,provenance FROM git_observations ORDER BY capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,kind,scope,value,provenance",
        (
            "capture_origin_uuidv4",
            "capture_uuidv4",
            "repository_uuidv4",
            "kind",
            "scope",
            "value",
            "provenance",
        ),
        0,
    ),
    "captures": (
        "SELECT capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,source,ref,object_format,root FROM captures ORDER BY capture_origin_uuidv4,capture_uuidv4",
        (
            "capture_origin_uuidv4",
            "capture_uuidv4",
            "repository_uuidv4",
            "source",
            "ref",
            "object_format",
            "root",
        ),
        0,
    ),
    "notes_claims": (
        "SELECT capture_origin_uuidv4,capture_uuidv4,object_format,target,note,provenance FROM notes_claims ORDER BY capture_origin_uuidv4,capture_uuidv4,object_format,target,note,provenance",
        (
            "capture_origin_uuidv4",
            "capture_uuidv4",
            "object_format",
            "target",
            "note",
            "provenance",
        ),
        0,
    ),
    "note_role_targets": (
        "SELECT DISTINCT object_format,target FROM note_roles WHERE capture_origin_uuidv4=? AND capture_uuidv4=? ORDER BY object_format,target",
        ("object_format", "target"),
        2,
    ),
    "coverage_scopes": (
        "SELECT owner_kind,owner_coordinates_json,repository_uuidv4,capture_origin_uuidv4,capture_uuidv4,object_format,full_oid,field,coverage_kind,observation_origin_uuidv4,ref_observation_uuidv7 FROM coverage_scopes ORDER BY owner_kind,owner_coordinates_json",
        (
            "owner_kind",
            "owner_coordinates_json",
            "repository_uuidv4",
            "capture_origin_uuidv4",
            "capture_uuidv4",
            "object_format",
            "full_oid",
            "field",
            "coverage_kind",
            "observation_origin_uuidv4",
            "ref_observation_uuidv7",
        ),
        0,
    ),
    "coverage_claims": (
        "SELECT owner_kind,owner_coordinates_json,observed_at_us,coverage_state,details_json FROM coverage_claims ORDER BY owner_kind,owner_coordinates_json,observed_at_us,coverage_state",
        (
            "owner_kind",
            "owner_coordinates_json",
            "observed_at_us",
            "coverage_state",
            "details_json",
        ),
        0,
    ),
    "coverage_proofs": (
        "SELECT owner_kind,owner_coordinates_json,observed_at_us,coverage_state,members_json,provenance FROM core_coverage_proofs ORDER BY owner_kind,owner_coordinates_json,observed_at_us,coverage_state,members_json,provenance",
        (
            "owner_kind",
            "owner_coordinates_json",
            "observed_at_us",
            "coverage_state",
            "members_json",
            "provenance",
        ),
        0,
    ),
    "git_objects": (
        "SELECT object_format,full_oid FROM git_objects ORDER BY object_format,full_oid",
        ("object_format", "full_oid"),
        0,
    ),
}

# These legacy selections include protected proof/provenance and are available
# only to the internal Exchange path that validates each emitted role/copy.
_EXCHANGE_LEGACY_ROWS = {
    "notes_groups": (
        "SELECT scope,status,membership,provenance FROM notes_groups WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? ORDER BY scope,status,membership,provenance",
        ("scope", "status", "membership", "provenance"),
        3,
    ),
    "note_roles": (
        "SELECT object_format,root,target,note,path,proof_bundle FROM note_roles WHERE capture_origin_uuidv4=? AND capture_uuidv4=? ORDER BY object_format,root,target,note,path,proof_bundle",
        ("object_format", "root", "target", "note", "path", "proof_bundle"),
        2,
    ),
    "retained_notes": (
        "SELECT object_format,full_oid,physical_copy_uuidv4,size,digest_sha256,root,target,path,proof_bundle FROM retained_notes WHERE capture_origin_uuidv4=? AND capture_uuidv4=? ORDER BY object_format,full_oid,physical_copy_uuidv4",
        (
            "object_format",
            "full_oid",
            "physical_copy_uuidv4",
            "size",
            "digest_sha256",
            "root",
            "target",
            "path",
            "proof_bundle",
        ),
        2,
    ),
}


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

    @_decoded_read
    def _open_export_metadata_cursor(
        self, selector, parameters, *, lengths, protected=False
    ):
        selectors = _EXCHANGE_LEGACY_ROWS if protected else _EXCHANGE_METADATA_ROWS
        query, columns, _arity = selectors[selector]
        # Each fixed query orders by its complete immutable key, so the
        # measurement and value cursors traverse the same rows. Non-key payload
        # values are not included in an extra sort before their reservation.
        projection = (
            ",".join('octet_length("' + column + '")' for column in columns)
            if lengths
            else "*"
        )
        try:
            return self._db.execute(
                "SELECT " + projection + " FROM (" + query + ")", parameters
            )
        except sqlite3.DatabaseError as error:
            if _sqlite_authority_failure(error):
                self._integrity_stop((selector, "stored metadata query", str(error)))
            raise

    @_decoded_read
    def _next_export_metadata_row(self, cursor):
        try:
            return cursor.fetchone()
        except sqlite3.DatabaseError as error:
            if _sqlite_authority_failure(error):
                self._integrity_stop(("exchange metadata", "stored read", str(error)))
            raise

    @_completed_read
    def exchange_metadata_rows(self, selector, parameters, work):
        """Read only fixed Core metadata, reserving each row before fetching it.

        Both cursors use one pinned snapshot and a complete deterministic order.
        User work callbacks execute outside the narrow fixed-SQL decode boundary.
        """
        return self._scan_exchange_metadata_rows(selector, parameters, work, False)

    @_completed_read
    def _legacy_exchange_metadata_rows(self, selector, parameters, work):
        """Internal Exchange rows; the caller validates every emitted proof/copy."""
        prior = getattr(self, "_checked_byte_read", False)
        self._checked_byte_read = True
        try:
            return self._scan_exchange_metadata_rows(
                selector, parameters, _CheckedReadBudget(self, work), True
            )
        finally:
            self._checked_byte_read = prior

    def _scan_exchange_metadata_rows(self, selector, parameters, work, protected):
        selectors = _EXCHANGE_LEGACY_ROWS if protected else _EXCHANGE_METADATA_ROWS
        spec = selectors.get(selector) if type(selector) is str else None
        if (
            spec is None
            or type(parameters) is not tuple
            or len(parameters) != spec[2]
            or any(type(value) is not str for value in parameters)
        ):
            raise CoreFailure(
                "QUERY_BUDGET", "exchange-metadata", "fixed selector required"
            )
        with self._snapshot():
            measured = self._open_export_metadata_cursor(
                selector, parameters, lengths=True, protected=protected
            )
            try:
                values = self._open_export_metadata_cursor(
                    selector, parameters, lengths=False, protected=protected
                )
                try:
                    result = []
                    while True:
                        work.require("metadata_units", 1)
                        try:
                            lengths = self._next_export_metadata_row(measured)
                        except BaseException:
                            abandon = getattr(work, "abandon", None)
                            if abandon is None:
                                work.charge("metadata_units", 1)
                            else:
                                abandon("metadata_units")
                            raise
                        work.charge("metadata_units", int(lengths is not None))
                        if lengths is None:
                            break
                        if len(result) >= 1_000_000:
                            raise CoreFailure(
                                "QUERY_BUDGET", selector, "finite metadata row limit"
                            )
                        if any(
                            value is not None and (type(value) is not int or value < 0)
                            for value in lengths
                        ):
                            self._integrity_stop(
                                (selector, "invalid stored metadata length")
                            )
                        size = sum(value or 0 for value in lengths)
                        work.require("input_bytes", size)
                        try:
                            row = self._next_export_metadata_row(values)
                        except BaseException:
                            abandon = getattr(work, "abandon", None)
                            if abandon is None:
                                work.charge("input_bytes", size)
                            else:
                                abandon("input_bytes")
                            raise
                        work.charge("input_bytes", size)
                        if row is None:
                            self._integrity_stop(
                                (selector, "metadata changed in snapshot")
                            )
                        result.append(row)
                    return result
                finally:
                    values.close()
            finally:
                measured.close()

    @_decoded_read
    def _ref_exchange_fixed_rows(self, selector, parameters, limit, *, lengths):
        """Fetch one fixed authoritative projection, with no caller callbacks."""
        table, columns, tail, _arity, distinct, _pairs = _REF_EXCHANGE_ROWS[selector]
        query = (
            "SELECT "
            + ("DISTINCT " if distinct else "")
            + ",".join(columns)
            + " FROM "
            + table
            + " "
            + tail
        )
        projection = (
            ",".join("octet_length(" + column + ")" for column in columns)
            if lengths
            else "*"
        )
        return self.sql(
            "SELECT " + projection + " FROM (" + query + ") LIMIT ?",
            (*parameters, limit),
        )

    @_completed_read
    def ref_exchange_rows(self, selector, parameters, work, *, maximum, max_bytes):
        """Bound and read selected authoritative metadata for ref Exchange.

        The UTF-8 diagnosis covers only the fixed SQL fetch, not caller-supplied
        work callbacks or generic SQL. Every variable value is measured and
        reserved before materialization under the same snapshot.
        """
        spec = _REF_EXCHANGE_ROWS.get(selector) if type(selector) is str else None
        if (
            spec is None
            or type(parameters) is not tuple
            or len(parameters) != spec[3]
            or any(type(value) is not str for value in parameters)
            or type(maximum) is not int
            or not 0 < maximum < 2**63 - 1
            or type(max_bytes) is not int
            or not 0 < max_bytes < 2**63
        ):
            raise CoreFailure(
                "QUERY_BUDGET", "ref-exchange", "fixed bounded selector required"
            )
        with self._snapshot():
            work.require("metadata_units", maximum + 1)
            try:
                lengths = self._ref_exchange_fixed_rows(
                    selector, parameters, maximum + 1, lengths=True
                )
            except BaseException:
                abandon = getattr(work, "abandon", None)
                if abandon is None:
                    work.charge("metadata_units", maximum + 1)
                else:
                    abandon("metadata_units")
                raise
            work.charge("metadata_units", len(lengths))
            if len(lengths) > maximum:
                raise CoreFailure(
                    "QUERY_BUDGET", "ref-exchange", "finite metadata limit"
                )
            if any(
                value is not None and (type(value) is not int or value < 0)
                for row in lengths
                for value in row
            ):
                self._integrity_stop((selector, "invalid stored metadata length"))
            if spec[5] and any(tuple(row) != (36, 36) for row in lengths):
                self._integrity_stop((selector, "invalid stored identity length"))
            size = sum(value or 0 for row in lengths for value in row)
            if size > max_bytes:
                raise CoreFailure(
                    "QUERY_BUDGET", "ref-exchange", "finite metadata limit"
                )
            work.require("input_bytes", size)
            try:
                rows = self._ref_exchange_fixed_rows(
                    selector, parameters, maximum + 1, lengths=False
                )
            except BaseException:
                abandon = getattr(work, "abandon", None)
                if abandon is None:
                    work.charge("input_bytes", size)
                else:
                    abandon("input_bytes")
                raise
            work.charge("input_bytes", size)
            if len(rows) != len(lengths):
                self._integrity_stop((selector, "metadata changed in snapshot"))
            if spec[5]:
                from repo_catalog.domain.ref_observation import RefObservationKey

                return [
                    self._stored(selector, RefObservationKey, *row).key for row in rows
                ]
            return rows

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

    @_completed_read
    def read_legacy_note_copy(
        self,
        oid: OID,
        physical_copy_uuidv4: str,
        work,
        *,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        max_proof_bytes: int = 64 * 1024 * 1024,
    ):
        """Verify and return the exact legacy note copy and its stored role."""
        if not isinstance(oid, OID):
            raise CoreFailure("IDENTITY", oid, "typed note OID required")
        uuid4_value(physical_copy_uuidv4)
        work = _CheckedReadBudget(self, work)
        prior = getattr(self, "_checked_byte_read", False)
        self._checked_byte_read = True
        try:
            with self._snapshot():
                row = self._bounded_stored_row(
                    "retained_notes",
                    (*oid.key, physical_copy_uuidv4),
                    work,
                    max_metadata_bytes,
                    max_proof_bytes,
                )
                if row is None:
                    raise CoreFailure(
                        "NOTES_ROLE_UNAVAILABLE", oid, "physical note copy not found"
                    )
                self._validate_stored_legacy_note(
                    row, work, max_metadata_bytes, max_proof_bytes
                )
                return row
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
    def read_metadata_copy(
        self, oid: OID, physical_copy_uuidv4: str, work, *, max_bytes=64 * 1024 * 1024
    ):
        """Verify one retained structural metadata copy before exporting it."""
        if not isinstance(oid, OID):
            raise CoreFailure("IDENTITY", oid, "typed metadata OID required")
        uuid4_value(physical_copy_uuidv4)
        if type(max_bytes) is not int or not 0 < max_bytes < 2**63:
            raise CoreFailure("BUDGET", oid, "finite metadata copy limit required")
        work = _CheckedReadBudget(self, work)
        prior = getattr(self, "_checked_byte_read", False)
        self._checked_byte_read = True
        try:
            with self._snapshot():
                work.require("metadata_units", 1)
                try:
                    sizes = self._ref_note_one(
                        "SELECT octet_length(native_type),octet_length(body),size,octet_length(digest_sha256) FROM retained_metadata WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                        (*oid.key, physical_copy_uuidv4),
                    )
                except BaseException:
                    abandon = getattr(work, "abandon", None)
                    if abandon is None:
                        work.charge("metadata_units", 1)
                    else:
                        abandon("metadata_units")
                    raise
                work.charge("metadata_units", int(sizes is not None))
                if sizes is None:
                    raise CoreFailure(
                        "BYTES_UNAVAILABLE", oid, "physical metadata copy not found"
                    )
                if (
                    any(type(value) is not int or value < 0 for value in sizes)
                    or sizes[1] != sizes[2]
                    or sizes[0] > 6
                    or sizes[3] != 64
                ):
                    self._integrity_stop(
                        (oid, physical_copy_uuidv4, "invalid stored metadata size")
                    )
                total = sizes[0] + sizes[1] + sizes[3]
                if total > max_bytes:
                    raise CoreFailure("BUDGET", oid, "finite metadata copy limit")
                work.require("input_bytes", total)
                try:
                    row = self._ref_note_one(
                        "SELECT * FROM retained_metadata WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                        (*oid.key, physical_copy_uuidv4),
                    )
                except BaseException:
                    abandon = getattr(work, "abandon", None)
                    if abandon is None:
                        work.charge("input_bytes", total)
                    else:
                        abandon("input_bytes")
                    raise
                work.charge("input_bytes", total if row is not None else 0)
                if row is None:
                    self._integrity_stop(
                        (oid, physical_copy_uuidv4, "metadata copy disappeared")
                    )
                self._charge(work, "metadata_units", 1)
                missing = self._ref_note_one(
                    "SELECT 1 FROM intrinsic_claims i LEFT JOIN retained_metadata r ON r.object_format=i.object_format AND r.full_oid=i.full_oid AND r.physical_copy_uuidv4=i.physical_copy_uuidv4 WHERE i.object_format=? AND i.full_oid=? AND r.physical_copy_uuidv4 IS NULL UNION ALL SELECT 1 FROM intrinsic_groups i LEFT JOIN retained_metadata r ON r.object_format=i.object_format AND r.full_oid=i.full_oid AND r.physical_copy_uuidv4=i.physical_copy_uuidv4 WHERE i.object_format=? AND i.full_oid=? AND r.physical_copy_uuidv4 IS NULL LIMIT 1",
                    (*oid.key, *oid.key),
                )
                if missing:
                    self._integrity_stop((oid, "lost-retained-metadata-copy"))
                try:
                    with account_verification(work):
                        if row["native_type"] not in (
                            "commit",
                            "tree",
                            "tag",
                        ) or not valid_native(
                            *oid.key,
                            row["native_type"],
                            row["body"],
                            row["size"],
                            row["digest_sha256"],
                        ):
                            raise CoreFailure(
                                "STORED_METADATA", oid, "invalid structural copy"
                            )
                        parse_metadata(
                            oid.object_format, row["native_type"], row["body"]
                        )
                except CoreFailure as error:
                    if error.code in ("STORED_METADATA", "NATIVE_SYNTAX"):
                        self._integrity_stop(
                            (oid, physical_copy_uuidv4, "invalid structural copy")
                        )
                    raise
                except (ValueError, TypeError, RecursionError, OverflowError):
                    self._integrity_stop(
                        (oid, physical_copy_uuidv4, "invalid structural copy")
                    )
                return row
        finally:
            self._checked_byte_read = prior

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
