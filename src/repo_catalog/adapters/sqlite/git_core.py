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
from repo_catalog.domain.p1_core import (
    OID,
    CoreFailure,
    NativeObject,
    Provenance,
    ScalarClaim,
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
    "coverage_scopes": (
        "SELECT owner_kind,owner_coordinates_json,repository_uuidv4,object_format,full_oid,field,coverage_kind,observation_origin_uuidv4,ref_observation_uuidv7 FROM coverage_scopes ORDER BY owner_kind,owner_coordinates_json",
        (
            "owner_kind",
            "owner_coordinates_json",
            "repository_uuidv4",
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


class _InvalidStoredMetadataCopy(Exception):
    """Carry a stored-value validation failure past verification accounting."""


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


class _WorkCallbackError(Exception):
    """Keep a caller exception outside stored-data and SQLite classifiers."""

    def __init__(self, original):
        super().__init__()
        self.original = original


class _ProtectedWorkLimits:
    def __init__(self, budget):
        self.budget = budget

    @property
    def note_bytes(self):
        return self.budget._invoke(lambda: self.budget.work.limits.note_bytes)


class _ProtectedWorkBudget:
    """Do not lend writer/checked-byte capabilities to a work callback."""

    def __init__(self, core, work):
        self.core, self.work = core, work
        self.limits = _ProtectedWorkLimits(self)

    def _invoke(self, operation):
        core = self.core
        admitting = core._admitting
        checked = getattr(core, "_checked_byte_read", False)
        depth = getattr(core, "_work_callback_depth", 0)
        core._admitting = core._checked_byte_read = False
        core._work_callback_depth = depth + 1
        try:
            return operation()
        except Exception as error:
            raise _WorkCallbackError(error) from error
        finally:
            core._work_callback_depth = depth
            core._admitting, core._checked_byte_read = admitting, checked

    def require(self, unit, amount=1):
        return self._invoke(lambda: self.work.require(unit, amount))

    def charge(self, unit, amount):
        return self._invoke(lambda: self.work.charge(unit, amount))

    def __getattr__(self, name):
        if name != "abandon":
            raise AttributeError(name)
        method = self._invoke(lambda: getattr(self.work, name, None))
        if method is None:
            raise AttributeError(name)
        return lambda unit: self._invoke(lambda: method(unit))


@contextmanager
def _protected_work(core, work):
    try:
        yield _ProtectedWorkBudget(core, work)
    except _WorkCallbackError as error:
        raise error.original from None


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
    def _open_export_metadata_cursor(self, selector, parameters, *, lengths):
        selectors = _EXCHANGE_METADATA_ROWS
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
        return self._scan_exchange_metadata_rows(selector, parameters, work)

    def _scan_exchange_metadata_rows(self, selector, parameters, work):
        selectors = _EXCHANGE_METADATA_ROWS
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
                selector, parameters, lengths=True
            )
            try:
                values = self._open_export_metadata_cursor(
                    selector, parameters, lengths=False
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
    def ref_notes_inventory_projection(
        self,
        claim,
        work,
        *,
        max_groups=10_000,
        max_members=100_000,
        max_bytes=64 * 1024 * 1024,
        max_proofs=1_000,
        max_structures=100_000,
    ):
        """Read original Groups and current receiver proof for one exact Claim."""
        from repo_catalog.domain.p1_core import CoreCoverageScope
        from repo_catalog.domain.ref_coverage import REF_NOTES_INVENTORY
        from repo_catalog.domain.ref_observation import (
            NotesMappingGroup,
            RefNotesInventoryGroupProjection,
            RefNotesInventoryProjection,
            RefObservationClaim,
            account_notes_group_comparison,
        )

        if not isinstance(claim, RefObservationClaim) or any(
            type(value) is not int or not 0 < value < 2**63 - 1
            for value in (
                max_groups,
                max_members,
                max_bytes,
                max_proofs,
                max_structures,
            )
        ):
            raise CoreFailure(
                "QUERY_BUDGET", "ref-inventory", "typed finite scope required"
            )
        with _protected_work(self, work) as guarded, self._snapshot():
            self._require_ref_claim(
                claim,
                work=guarded,
                max_metadata_bytes=max_bytes,
                metadata_limit_code="QUERY_BUDGET",
            )
            observed = self.ref_observation(
                claim.ref_observation_key, guarded, max_bytes=max_bytes
            )
            rows = (
                self.ref_exchange_rows(
                    "groups",
                    claim.identity,
                    guarded,
                    maximum=max_groups,
                    max_bytes=max_bytes,
                )
                if claim.root_oid is not None
                else ()
            )
            groups = []
            for row in rows:
                (
                    fmt,
                    root,
                    kind,
                    version,
                    interpretation,
                    scope,
                    status,
                    raw,
                    provenance,
                ) = row
                if (
                    (fmt, root) != claim.root_oid.key
                    or type(raw) is not str
                    or type(provenance) is not str
                ):
                    self._integrity_stop(
                        (claim.identity, "invalid-stored-group-coordinates")
                    )

                # Count JSON containers/separators before materialization, with
                # bounded traversal even for malformed or adversarial groups.
                guarded.require("input_bytes", len(raw))
                tokens = 0
                scanned = 0
                quoted = escaped = False
                try:
                    for char in raw:
                        scanned += 1
                        if quoted:
                            if escaped:
                                escaped = False
                            elif char == "\\":
                                escaped = True
                            elif char == '"':
                                quoted = False
                        elif char == '"':
                            quoted = True
                        elif char in "[{,":
                            tokens += 1
                            if tokens > 4 * max_members + 4:
                                raise CoreFailure(
                                    "QUERY_BUDGET",
                                    claim.identity,
                                    "finite group member limit",
                                )
                finally:
                    guarded.charge("input_bytes", scanned)
                # Membership is traversed repeatedly to construct and check
                # the whole group and its canonical encoding.
                metadata_reservation = tokens + 4 * min(max_members, tokens)
                guarded.require("metadata_units", metadata_reservation)
                # Noncanonical stored Unicode can expand to twelve ASCII
                # escape characters per code point when re-encoded as JSON.
                raw_upper = len(raw) if raw.isascii() else 12 * len(raw)
                provenance_upper = (
                    len(provenance) if provenance.isascii() else 12 * len(provenance)
                )
                parse_bytes = 5 * raw_upper + 2 * provenance_upper
                try:
                    guarded.require("input_bytes", parse_bytes)
                except BaseException:
                    abandon = getattr(guarded, "abandon", None)
                    if abandon is not None:
                        abandon("metadata_units")
                    else:
                        guarded.charge("metadata_units", metadata_reservation)
                    raise
                metadata_work = metadata_reservation
                try:
                    members = self._stored(claim.identity, json.loads, raw)
                    if type(members) is not list:
                        self._integrity_stop(
                            (claim.identity, "invalid-stored-group-members")
                        )
                    if len(members) > max_members:
                        raise CoreFailure(
                            "QUERY_BUDGET", claim.identity, "finite group member limit"
                        )
                    metadata_work = min(metadata_reservation, tokens + 4 * len(members))

                    def decode_group():
                        group = NotesMappingGroup(
                            claim,
                            kind,
                            version,
                            interpretation,
                            scope,
                            status,
                            tuple(tuple(member) for member in members),
                            Provenance(*json.loads(provenance)),
                        )
                        if (
                            encode(group.members) != raw
                            or group.provenance.encoded != provenance
                        ):
                            raise ValueError("noncanonical stored group")
                        return group

                    group = self._stored(claim.identity, decode_group)
                finally:
                    guarded.charge("metadata_units", metadata_work)
                    guarded.charge("input_bytes", parse_bytes)
                for target, note, _ in group.members:
                    for oid in (target, note):
                        guarded.require("metadata_units", 1)
                        guarded.charge("metadata_units", 1)
                        if not self.sql(
                            "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                            (fmt, oid),
                        ):
                            self._integrity_stop(
                                (claim.identity, "missing-stored-group-object", oid)
                            )
                groups.append(group)

            scope = CoreCoverageScope(
                "ref_observation", (*claim.ref_observation_key.key, REF_NOTES_INVENTORY)
            )
            coverage = self.coverage(
                scope,
                guarded,
                max_proofs=max_proofs,
                max_bytes=max_bytes,
                max_structures=max_structures,
            )
            verified = []
            for coverage_claim in coverage.claims:
                if coverage_claim.state == "complete":
                    for proof in self.ref_coverage_proofs(
                        coverage_claim,
                        guarded,
                        max_proofs=max_proofs,
                        max_bytes=max_bytes,
                        max_structures=max_structures,
                    ):
                        guarded.require("metadata_units", 1)
                        guarded.charge("metadata_units", 1)
                        verified.append(proof)
            projected = []
            for group in groups:
                matches = []
                for proof in verified:
                    account_notes_group_comparison(group, proof.group, guarded)
                    if proof.group == group:
                        matches.append(proof.verification_provenance)
                projected.append(
                    RefNotesInventoryGroupProjection(group, tuple(matches))
                )
            return RefNotesInventoryProjection(
                claim, observed.ref_observation, tuple(projected), coverage
            )

    @_completed_read
    def ref_notes_inventory_projections(self, groups, work, *, max_items=100_000):
        """Check exact Groups and current Coverage in one protected snapshot."""
        from repo_catalog.domain.ref_observation import (
            NotesMappingGroup,
            account_notes_group_comparison,
        )

        if (
            type(groups) is not tuple
            or type(max_items) is not int
            or not 0 < max_items < 2**63
            or len(groups) > max_items
        ):
            raise CoreFailure("QUERY_BUDGET", "ref-inventory", "finite groups required")
        with _protected_work(self, work) as guarded, self._snapshot():
            results = []
            for group in groups:
                guarded.require("metadata_units", 1)
                guarded.charge("metadata_units", 1)
                if not isinstance(group, NotesMappingGroup):
                    raise CoreFailure(
                        "NOTES_INVENTORY", "group", "typed Group required"
                    )
                projection = self.ref_notes_inventory_projection(
                    group.ref_claim, guarded
                )
                current = False
                for view in projection.groups:
                    account_notes_group_comparison(view.group, group, guarded)
                    if view.group == group and view.current_verified:
                        current = True
                results.append((projection, current))
            guarded.require("metadata_units", len(results))
            guarded.charge("metadata_units", len(results))
            return tuple(results)

    def admit_notes_mapping_group(self, group, work=None):
        """Keep reported-Group callbacks outside the admission capability."""
        if work is None:
            return super().admit_notes_mapping_group(group)
        with _protected_work(self, work) as guarded:
            return super().admit_notes_mapping_group(group, guarded)

    def admit_ref_coverage_proof(self, proof, work, **kwargs):
        """Keep untrusted work callbacks outside the writer capability."""
        with _protected_work(self, work) as guarded:
            return super().admit_ref_coverage_proof(proof, guarded, **kwargs)

    def ref_coverage_proofs(self, claim, work, **kwargs):
        """Preserve callback exceptions through the checked proof reader."""
        with _protected_work(self, work) as guarded:
            return super().ref_coverage_proofs(claim, guarded, **kwargs)

    def coverage(self, scope, work=None, **kwargs):
        """Keep caller work errors outside stored Coverage classifiers."""
        if work is None:
            return super().coverage(scope, None, **kwargs)
        with _protected_work(self, work) as guarded:
            return super().coverage(scope, guarded, **kwargs)

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

        protected = column == "body" and table == "retained_metadata"
        # Generic metadata SQL cannot emit Ref-observation bodies or
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
                invalid_copy = _InvalidStoredMetadataCopy()
                try:
                    with account_verification(work):
                        try:
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
                                raise invalid_copy
                            parse_metadata(
                                oid.object_format, row["native_type"], row["body"]
                            )
                        except CoreFailure as error:
                            if error.code not in ("STORED_METADATA", "NATIVE_SYNTAX"):
                                raise
                            raise invalid_copy from error
                        except (
                            ValueError,
                            TypeError,
                            RecursionError,
                            OverflowError,
                        ) as error:
                            raise invalid_copy from error
                except _InvalidStoredMetadataCopy as error:
                    # account_verification restores the caller's original work
                    # error first, even when a validator catches ValueError.
                    # Only our own signal is authoritative stored corruption.
                    if error is not invalid_copy:
                        raise
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
