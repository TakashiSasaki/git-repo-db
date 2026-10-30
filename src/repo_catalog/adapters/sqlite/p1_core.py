"""P1 executable reference adapter, deliberately outside the normal initializer.

The supported boundary is this class, not an arbitrary privileged sqlite3
connection. SQLite triggers protect rows against ordinary mutation; its
connection authorizer additionally excludes schema/PRAGMA/ATTACH and all generic
writes. A process with DDL/filesystem authority can destroy any SQLite database.
Statement caching is disabled by p1_schema.connect so authorization is repeated.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from functools import wraps
from pathlib import Path

from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreCoverageScope,
    CoreFailure,
    GitObservation,
    NativeObject,
    NotesAlternative,
    NotesClaim,
    NotesGroup,
    NotesProjection,
    NotesProof,
    Projection,
    Provenance,
    RelationGroup,
    RelationMember,
    RepositoryClaim,
    ScalarClaim,
    ScalarField,
    _notes_group,
    account_verification,
    claim_value,
    encode,
    intrinsic_members,
    uuid4_value,
    valid_coverage_members,
    valid_group,
    valid_native,
    valid_note_role,
)
from repo_catalog.domain.p1_coverage import (
    CoverageClaim,
    CoverageProjection,
    derive_coverage_state,
)
from repo_catalog.domain.ports.p1_core import WorkBudget
from repo_catalog.domain.ref_coverage import (
    REF_NOTES_INVENTORY,
    LocalRefCoverageWork,
    RefNotesInventoryCoverageProof,
    deserialize_structures,
    verify_ref_notes_inventory,
)
from repo_catalog.domain.ref_observation import (
    NotesMapping,
    NotesMappingClaim,
    NotesMappingEvidence,
    NotesMappingEvidenceRecord,
    NotesMappingGroup,
    NotesMappingProjection,
    RefAbsenceEvidence,
    RefEnumerationLink,
    RefEnumerationObservation,
    RefEnumerationResult,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
    RefObservationProjection,
    ref_claim_conflict,
)

# Fixed trusted selectors and all variable-width columns that a typed read
# materializes. Never accept table, column or predicate names from callers.
_BOUNDED_STORED_ROWS = {
    "ref_enumeration_observations": (
        "observation_origin_uuidv4=? AND enumeration_uuidv7=?",
        (
            "observation_origin_uuidv4",
            "enumeration_uuidv7",
            "repository_uuidv4",
            "source_attribution",
            "visibility_scope",
            "enumeration_scope_json",
            "enumeration_state",
            "completion_coordinate",
        ),
        False,
    ),
    "ref_observations": (
        "observation_origin_uuidv4=? AND ref_observation_uuidv7=?",
        (
            "observation_origin_uuidv4",
            "ref_observation_uuidv7",
            "repository_uuidv4",
            "ref_name_bytes",
            "source_attribution",
            "visibility_scope",
        ),
        False,
    ),
    "ref_observation_claims": (
        "observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND provenance=?",
        (
            "observation_origin_uuidv4",
            "ref_observation_uuidv7",
            "provenance",
            "presence_state",
            "ref_form",
            "direct_format",
            "direct_target_oid",
            "symbolic_target_ref_name",
            "resolved_format",
            "resolved_target_oid",
            "peeled_format",
            "peeled_target_oid",
            "root_format",
            "root_oid",
            "absence_evidence",
        ),
        False,
    ),
    "ref_retained_notes": (
        "object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
        (
            "object_format",
            "full_oid",
            "physical_copy_uuidv4",
            "digest_sha256",
            "observation_origin_uuidv4",
            "ref_observation_uuidv7",
            "ref_claim_provenance",
            "role_format",
            "root_oid",
            "interpretation_kind",
            "interpretation_version",
            "interpretation_scope",
            "annotated_object_oid",
            "note_oid",
            "mapping_path_json",
            "verification_scope",
            "role_provenance",
        ),
        True,
    ),
    "retained_notes": (
        "object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
        (
            "object_format",
            "full_oid",
            "physical_copy_uuidv4",
            "digest_sha256",
            "capture_origin_uuidv4",
            "capture_uuidv4",
            "root",
            "target",
            "path",
        ),
        True,
    ),
    "captures": (
        "capture_origin_uuidv4=? AND capture_uuidv4=?",
        (
            "capture_origin_uuidv4",
            "capture_uuidv4",
            "repository_uuidv4",
            "source",
            "ref",
            "object_format",
            "root",
        ),
        False,
    ),
}


def _sqlite_authority_failure(error):
    """Extended engine codes retain their authoritative primary failure scope."""
    return isinstance(error, sqlite3.DatabaseError) and (
        getattr(error, "sqlite_errorcode", 0) & 255
        in (sqlite3.SQLITE_NOTADB, sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_IOERR)
    )


def _completed_read(method):
    """Linearize successful result delivery against the persistent stop fence."""

    @wraps(method)
    def completed(self, *args, **kwargs):
        result = method(self, *args, **kwargs)
        return self._complete_read(result)

    return completed


def _decoded_read(method):
    """Only fixed typed readers may diagnose stored text/JSON decode failures."""

    @wraps(method)
    def decoded(self, *args, **kwargs):
        prior_depth = getattr(self, "_typed_read_depth", 0)
        self._typed_read_depth = prior_depth + 1
        try:
            return method(self, *args, **kwargs)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            self._integrity_stop((method.__name__, "stored-decode", str(error)))
        except sqlite3.OperationalError as error:
            if "Could not decode to UTF-8" in str(error):
                self._integrity_stop((method.__name__, "stored-utf8"))
            raise
        finally:
            self._typed_read_depth = prior_depth

    return decoded


class Core:
    def __init__(
        self,
        path: Path,
        *,
        on_corruption: Callable[[CoreFailure], None] | None = None,
        read_limits=None,
    ):
        from repo_catalog.adapters.sqlite.p1_schema import connect

        self._directory = Path(path).parent
        from repo_catalog.adapters.sqlite.p1_coordination import (
            catalog_gate,
            persist_catalog_stop,
        )

        with catalog_gate(self._directory, exclusive=False):
            if (self._directory / "p1-recovery-stop.json").exists():
                raise CoreFailure(
                    "RECOVERY_STOP", "catalog", "normal catalog operation stopped"
                )
            try:
                self._db = connect(path, "core")
                if read_limits is not None:
                    from repo_catalog.adapters.sqlite.p1_coordination import (
                        apply_snapshot_read_limits,
                    )

                    try:
                        apply_snapshot_read_limits(self._db, read_limits)
                    except BaseException:
                        self._db.close()
                        raise
            except sqlite3.DatabaseError as error:
                if Path(path).is_file() and _sqlite_authority_failure(error):
                    persist_catalog_stop(
                        self._directory, "Core open corruption: " + str(error)
                    )
                raise
        self._admitting = False
        self._reading = False
        self._external = False
        self._active = True
        self._stopped = False
        self._on_corruption = on_corruption
        self._db.set_authorizer(self._authorize)

    @classmethod
    @contextmanager
    def for_transaction(cls, db: sqlite3.Connection) -> Iterator[Core]:
        """Bind typed units to a coordinator-owned local Core transaction.

        Trusted infrastructure supplies an uncached supported connection with no
        prior authorizer. Each admission uses a savepoint; only the coordinator
        commits the outer transaction. The capability expires at block exit.
        This does not make two databases' commits atomic.
        """
        if not db.in_transaction:
            raise CoreFailure(
                "TRANSACTION", "core", "active coordinator transaction required"
            )
        rows = db.execute("SELECT store_role FROM store_identity").fetchall()
        if len(rows) != 1 or rows[0][0] != "core":
            raise CoreFailure(
                "STORE_ROLE",
                "core",
                "Core capability requires a Core store transaction",
            )
        result = cls.__new__(cls)
        result._directory = None
        result._db, result._external, result._active = db, True, True
        result._admitting, result._stopped, result._on_corruption = False, False, None
        result._reading = False
        db.set_authorizer(result._authorize)
        try:
            yield result
        finally:
            result._active = False
            db.set_authorizer(None)

    def _authorize(
        self, action: int, _a: str, _b: str, _database: str, _trigger: str
    ) -> int:
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        if self._reading:
            allowed.add(sqlite3.SQLITE_TRANSACTION)
        if self._admitting:
            allowed |= {
                sqlite3.SQLITE_INSERT,
                sqlite3.SQLITE_TRANSACTION,
                sqlite3.SQLITE_SAVEPOINT,
            }
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    def _available(self) -> None:
        if getattr(self, "_work_callback_depth", 0):
            raise sqlite3.DatabaseError(
                "Core reentry is prohibited during a work callback"
            )
        if not self._active:
            raise CoreFailure(
                "CAPABILITY_EXPIRED",
                "core",
                "transaction-bound Core capability expired",
            )
        if (
            self._directory is not None
            and (self._directory / "p1-recovery-stop.json").exists()
        ):
            self._stopped = True
        if self._stopped:
            raise CoreFailure(
                "RECOVERY_STOP", "catalog", "normal catalog operation stopped"
            )

    def _complete_read(self, result):
        """A stop detected while reading forbids ordinary result completion.

        No completion lock is held during parsing/SQL: a corruption detector may
        need to publish its stop from that very operation. Transaction-bound
        capabilities use the coordinator's outer completion boundary.
        """
        self._available()
        if self._directory is None:
            return result
        from repo_catalog.adapters.sqlite.p1_coordination import catalog_completion
        from repo_catalog.domain.p1_coordination import CoordinationError

        try:
            with catalog_completion(self._directory):
                self._available()
                return result
        except CoordinationError:
            # Translate a stop that raced between the availability check and
            # fence acquisition to this port's normal typed stopped failure.
            self._available()
            raise

    def close(self) -> None:
        self._active = False
        if not self._external:
            self._db.close()

    @_completed_read
    def sql(self, statement: str, parameters: tuple = ()) -> list[sqlite3.Row]:
        self._available()
        if self._admitting:
            raise CoreFailure(
                "CAPABILITY", "sql", "generic SQL cannot borrow admission capability"
            )
        try:
            return self._db.execute(statement, parameters).fetchall()
        except sqlite3.DatabaseError as error:
            if _sqlite_authority_failure(error) or (
                getattr(self, "_typed_read_depth", 0)
                and str(error).startswith("Could not decode to UTF-8")
            ):
                # A fixed typed query identified corruption. Publish before
                # snapshot rollback/unwinding can admit another completion.
                self._integrity_stop(("Core read", str(error)))
            raise

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._available()
        if self._admitting:
            raise CoreFailure("TRANSACTION", "core", "nested admission is unsupported")
        from repo_catalog.adapters.sqlite.p1_coordination import catalog_gate

        gate = (
            nullcontext()
            if self._external
            else catalog_gate(self._directory, exclusive=True)
        )
        with gate:
            self._available()
            self._admitting = True
            try:
                self._db.execute(
                    "SAVEPOINT p1_core_unit" if self._external else "BEGIN IMMEDIATE"
                )
                try:
                    yield
                    if self._external:
                        self._db.execute("RELEASE p1_core_unit")
                    else:
                        from repo_catalog.adapters.sqlite.p1_coordination import (
                            catalog_completion,
                        )

                        with catalog_completion(self._directory):
                            self._available()
                            self._db.execute("COMMIT")
                except BaseException as error:
                    try:
                        if _sqlite_authority_failure(error):
                            self._integrity_stop(("Core transaction", str(error)))
                    finally:
                        if self._db.in_transaction:
                            if self._external:
                                self._db.execute("ROLLBACK TO p1_core_unit")
                                self._db.execute("RELEASE p1_core_unit")
                            else:
                                self._db.execute("ROLLBACK")
                    raise
            except sqlite3.DatabaseError as error:
                # BEGIN/SAVEPOINT may itself fail before the inner unit exists.
                if _sqlite_authority_failure(error):
                    self._integrity_stop(("Core transaction open", str(error)))
                raise
            finally:
                self._admitting = False

    @contextmanager
    def _snapshot(self) -> Iterator[None]:
        """Pin once under the cooperative gate, then release the gate for writers.

        Every SELECT for one projection reads this transaction. Coordinator-owned
        transactions already supply the pinned authoritative snapshot.
        """
        self._available()
        if self._db.in_transaction:
            yield
            return
        from repo_catalog.adapters.sqlite.p1_coordination import catalog_gate

        with catalog_gate(self._directory, exclusive=False):
            self._available()
            self._reading = True
            try:
                self._db.execute("BEGIN")
                self._db.execute("SELECT * FROM store_identity").fetchall()
            finally:
                self._reading = False
        try:
            yield
        finally:
            self._reading = True
            try:
                self._db.execute("ROLLBACK")
            finally:
                self._reading = False

    def _stored(self, scope, decoder, *values):
        """Validate only values fetched from authority, never caller arguments."""
        try:
            return decoder(*values)
        except CoreFailure as error:
            if error.code in ("BUDGET", "QUERY_BUDGET"):
                raise
            self._integrity_stop((scope, "invalid-stored-value", str(error)))
        except (ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
            self._integrity_stop((scope, "invalid-stored-value", str(error)))

    def _provenance_value(
        self,
        scope,
        encoded,
        *,
        work: WorkBudget | None = None,
        max_metadata_bytes: int = 64 * 1024 * 1024,
    ):
        def decode(value):
            if work is not None:
                self._meter_input_metadata(work, (value,), max_metadata_bytes)
            result = Provenance(*json.loads(value))
            if work is not None:
                self._meter_provenance_encoding(work, result, max_metadata_bytes)
            if result.encoded != value:
                raise ValueError("noncanonical stored provenance")
            return result

        return self._stored(scope, decode, encoded)

    def _insert(self, table: str, values: tuple) -> None:
        # Every caller supplies a fixed internal table name; no user SQL reaches here.
        result = self._db.execute(
            f"INSERT INTO {table} VALUES({','.join('?' for _ in values)}) ON CONFLICT DO NOTHING",
            values,
        )
        if result.rowcount == 0:
            names = [
                column[0]
                for column in self._db.execute(
                    f"SELECT * FROM {table} LIMIT 0"
                ).description
            ]
            row = self._db.execute(
                f"SELECT 1 FROM {table} WHERE {' AND '.join(name + ' IS ?' for name in names)}",
                values,
            ).fetchone()
            if row is None:
                raise CoreFailure(
                    "INCOMPATIBLE_REPLAY",
                    table,
                    "inconsistent immutable evidence coordinate",
                )

    def _object(self, oid: OID) -> None:
        self._insert("git_objects", oid.key)

    def _meter_input_metadata(
        self,
        work: WorkBudget,
        values: tuple,
        max_metadata_bytes: int,
        *,
        limit_code: str = "BUDGET",
    ) -> None:
        """Bound caller metadata before encoding it into keys or SQL inputs."""
        if type(max_metadata_bytes) is not int or not 0 < max_metadata_bytes < 2**63:
            raise CoreFailure(
                limit_code, "metadata", "positive finite metadata limit required"
            )
        minimum = sum(len(value) for value in values if isinstance(value, (str, bytes)))
        if minimum > max_metadata_bytes:
            raise CoreFailure(limit_code, "metadata", "finite input metadata limit")
        upper = sum(
            len(value)
            if isinstance(value, bytes) or value.isascii()
            else len(value) * 4
            for value in values
            if isinstance(value, (str, bytes))
        )
        if upper >= 2**63:
            raise CoreFailure(limit_code, "metadata", "finite input metadata limit")
        work.require("input_bytes", upper)
        try:
            actual = sum(
                len(value)
                if isinstance(value, bytes) or value.isascii()
                else len(value.encode("utf-8", "surrogatepass"))
                for value in values
                if isinstance(value, (str, bytes))
            )
        except BaseException:
            abandon = getattr(work, "abandon", None)
            if abandon is not None:
                abandon("input_bytes")
            else:
                work.charge("input_bytes", upper)
            raise
        work.charge("input_bytes", actual)
        if actual > max_metadata_bytes:
            raise CoreFailure(limit_code, "metadata", "finite input metadata limit")

    @staticmethod
    def _json_string_bytes(value: str) -> int:
        """Exact ensure_ascii JSON string length without allocating the string."""
        size = 2
        for character in value:
            code = ord(character)
            if character in '"\\\b\f\n\r\t':
                size += 2
            elif code < 0x20 or code >= 0x7F:
                size += 6 if code <= 0xFFFF else 12
            else:
                size += 1
        return size

    def _meter_json_string_scans(
        self, work, values, max_metadata_bytes, *, limit_code, scope
    ):
        """Reserve the character walk before measuring JSON-escaped lengths."""
        length = sum(len(value) for value in values)
        if length > max_metadata_bytes or length >= 2**63:
            raise CoreFailure(limit_code, scope, "finite input metadata limit")
        work.require("input_bytes", length)
        try:
            result = tuple(self._json_string_bytes(value) for value in values)
        except BaseException:
            abandon = getattr(work, "abandon", None)
            if abandon is not None:
                abandon("input_bytes")
            else:
                work.charge("input_bytes", length)
            raise
        work.charge("input_bytes", length)
        return result

    def _meter_provenance_encoding(
        self,
        work: WorkBudget,
        provenance: Provenance,
        max_metadata_bytes: int,
        *,
        limit_code: str = "BUDGET",
    ) -> None:
        values = provenance.key
        lengths = self._meter_json_string_scans(
            work, values, max_metadata_bytes, limit_code=limit_code, scope="provenance"
        )
        size = 2 + len(values) - 1 + sum(lengths)
        if size > max_metadata_bytes or size >= 2**63:
            raise CoreFailure(limit_code, "provenance", "finite encoded metadata limit")
        self._charge(work, "input_bytes", size)

    def _meter_mapping_path_encoding(
        self,
        work: WorkBudget,
        path: str | None,
        max_metadata_bytes: int,
        *,
        limit_code: str = "BUDGET",
    ) -> None:
        size = (
            4
            if path is None
            else self._meter_json_string_scans(
                work,
                (path,),
                max_metadata_bytes,
                limit_code=limit_code,
                scope="mapping_path",
            )[0]
        )
        if size > max_metadata_bytes or size >= 2**63:
            raise CoreFailure(
                limit_code, "mapping_path", "finite encoded metadata limit"
            )
        self._charge(work, "input_bytes", size)

    def _meter_absence_encoding(
        self,
        work: WorkBudget,
        evidence: RefAbsenceEvidence,
        max_metadata_bytes: int,
        *,
        limit_code: str = "BUDGET",
    ) -> None:
        prefix = (
            4
            if evidence.enumeration_prefix_bytes is None
            else 2 + 2 * len(evidence.enumeration_prefix_bytes)
        )
        values = (
            evidence.source_attribution,
            evidence.visibility_scope,
            evidence.method,
            evidence.completion_coordinate,
            *(
                (evidence.enumeration_state,)
                if evidence.enumeration_state is not None
                else ()
            ),
        )
        lengths = self._meter_json_string_scans(
            work, values, max_metadata_bytes, limit_code=limit_code, scope="absence"
        )
        state = 4 if evidence.enumeration_state is None else lengths[-1]
        size = (
            8 + sum(lengths[:4]) + 2 + 2 * len(evidence.ref_name_bytes) + prefix + state
        )
        if size > max_metadata_bytes or size >= 2**63:
            raise CoreFailure(limit_code, "absence", "finite encoded metadata limit")
        self._charge(work, "input_bytes", size)

    def _meter_proof_bundle(
        self, work: WorkBudget, evidence: NotesMappingEvidence, max_proof_bytes: int
    ) -> None:
        """Bound the canonical hex proof before its serialization."""
        if type(max_proof_bytes) is not int or not 0 < max_proof_bytes < 2**63:
            raise CoreFailure("BUDGET", "proof", "positive finite proof limit required")
        if len(evidence.structures) > max_proof_bytes:
            raise CoreFailure("BUDGET", "proof", "finite encoded proof limit")
        size = 2 + len(evidence.structures) - 1
        for structure in evidence.structures:
            self._charge(work, "proof_steps", 1)
            if (
                not isinstance(structure.oid, OID)
                or not isinstance(structure.native_type, str)
                or len(structure.native_type) > 6
                or structure.native_type not in ("commit", "tree", "tag", "blob")
                or type(structure.body) is not bytes
            ):
                raise CoreFailure(
                    "NOTES_ROLE", "proof", "typed native structure required"
                )
            size += (
                4
                + self._json_string_bytes(structure.oid.full_oid)
                + self._json_string_bytes(structure.native_type)
                + 2
                + 2 * len(structure.body)
            )
        if size > max_proof_bytes or size >= 2**63:
            raise CoreFailure("BUDGET", "proof", "finite encoded proof limit")
        self._charge(work, "input_bytes", size)

    @staticmethod
    def _claim_input_values(claim: RefObservationClaim) -> tuple:
        values = [
            *claim.ref_observation_key.key,
            *claim.provenance.key,
            claim.presence_state,
            claim.ref_form,
            claim.symbolic_target_ref_name,
        ]
        for oid in (
            claim.direct_target_oid,
            claim.resolved_target_oid,
            claim.peeled_target_oid,
            claim.root_oid,
        ):
            if oid is not None:
                values.extend(oid.key)
        if claim.absence_evidence is not None:
            absence = claim.absence_evidence
            values.extend(
                (
                    absence.source_attribution,
                    absence.visibility_scope,
                    absence.ref_name_bytes,
                    absence.method,
                    absence.completion_coordinate,
                    absence.enumeration_prefix_bytes,
                    absence.enumeration_state,
                )
            )
        return tuple(values)

    @staticmethod
    def _mapping_input_values(mapping: NotesMapping) -> tuple:
        return (
            *mapping.root_oid.key,
            mapping.interpretation_kind,
            mapping.interpretation_version,
            mapping.interpretation_scope,
            mapping.annotated_object_oid.full_oid,
            mapping.note_oid.full_oid,
            mapping.mapping_path,
        )

    def admit_repository(self, repository_uuidv4: str) -> None:
        uuid4_value(repository_uuidv4)
        with self._transaction():
            self._insert("repositories", (repository_uuidv4,))

    def admit_repository_claim(self, claim: RepositoryClaim) -> None:
        self._reported(claim.provenance)
        with self._transaction():
            self._insert("repository_claims", claim.key)

    def admit_observation(self, observation: GitObservation) -> None:
        self._reported(observation.provenance)
        with self._transaction():
            self._insert("git_observations", observation.key)

    def admit_object(self, oid: OID) -> None:
        with self._transaction():
            self._object(oid)

    @staticmethod
    def _reported(provenance: Provenance) -> None:
        if provenance.qualification != "reported":
            raise CoreFailure(
                "UNTRUSTED_VERIFICATION",
                provenance,
                "report cannot assert receiver checks",
            )

    def _claim(self, claim: ScalarClaim) -> None:
        self._object(claim.subject)
        self._insert("scalar_claims", claim.key)

    def admit_claim(self, claim: ScalarClaim) -> None:
        self._reported(claim.provenance)
        with self._transaction():
            self._claim(claim)

    def _group(self, group: RelationGroup) -> None:
        self._object(group.subject)
        for member in group.members:
            self._object(member.target)
        self._insert("relation_groups", group.key)

    def admit_group(
        self, group: RelationGroup, *, before_commit: Callable[[], None] | None = None
    ) -> None:
        self._reported(group.provenance)
        with self._transaction():
            self._group(group)
            if before_commit is not None:
                before_commit()

    def admit_ref_observation(self, observation: RefObservation) -> None:
        """Admit one immutable subject; a reused key must match all fields."""
        if not isinstance(observation, RefObservation):
            raise CoreFailure(
                "OBSERVATION", observation, "typed ref observation required"
            )
        with self._transaction():
            if self._db.execute(
                "SELECT 1 FROM ref_observations WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=?",
                observation.ref_observation_key.key,
            ).fetchone():
                self._validate_ref_subject_dependency(observation.ref_observation_key)
            self._insert("ref_observations", observation.key)

    def admit_ref_observation_claim(self, claim: RefObservationClaim) -> None:
        """Append an attributed result, with no mutation of earlier reports."""
        if not isinstance(claim, RefObservationClaim):
            raise CoreFailure("OBSERVATION", claim, "typed ref result claim required")
        with self._transaction():
            if self._db.execute(
                "SELECT 1 FROM ref_observation_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND provenance=?",
                claim.identity,
            ).fetchone():
                self._require_ref_claim(claim)
            for oid in (
                claim.direct_target_oid,
                claim.resolved_target_oid,
                claim.peeled_target_oid,
                claim.root_oid,
            ):
                if oid is not None:
                    self._object(oid)
            self._insert("ref_observation_claims", claim.key)

    def admit_ref_enumeration(
        self,
        event,
        links,
        work: WorkBudget,
        *,
        max_replay_links=200_000,
        max_replay_bytes=64 * 1024 * 1024,
    ) -> None:
        """Atomically admit one original scan and its exact item/absence links."""
        if not isinstance(event, RefEnumerationObservation) or not isinstance(
            links, tuple
        ):
            raise CoreFailure(
                "ENUMERATION", "event", "typed event and link tuple required"
            )
        if (
            type(max_replay_links) is not int
            or not 0 < max_replay_links < 2**63 - 1
            or type(max_replay_bytes) is not int
            or not 0 < max_replay_bytes < 2**63
        ):
            raise CoreFailure(
                "BUDGET", "enumeration-replay", "positive finite limits required"
            )
        if len(links) != event.link_count:
            raise CoreFailure("ENUMERATION", event.identity, "event link count differs")
        if len(links) > event.ref_limit + len(event.nominated):
            raise CoreFailure("BUDGET", event.identity, "finite event link limit")
        self._charge(work, "metadata_units", len(event.prefixes) + len(event.nominated))
        seen = set()
        checked_events = {id(event)}
        for link in links:
            self._charge(work, "metadata_units", 1)
            if not isinstance(link, RefEnumerationLink):
                raise CoreFailure(
                    "ENUMERATION", event.identity, "link belongs to another event"
                )
            if id(link.event) not in checked_events:
                self._charge(
                    work,
                    "metadata_units",
                    len(link.event.prefixes) + len(link.event.nominated) + 1,
                )
                self._meter_input_metadata(
                    work,
                    (
                        link.event.source_attribution,
                        link.event.visibility_scope,
                        link.event.completion_coordinate,
                        *link.event.prefixes,
                        *link.event.nominated,
                    ),
                    event.byte_limit,
                )
                if link.event != event:
                    raise CoreFailure(
                        "ENUMERATION", event.identity, "link belongs to another event"
                    )
                checked_events.add(id(link.event))
            name = link.observation.ref_name_bytes
            if name in seen or link.position != len(seen):
                raise CoreFailure(
                    "ENUMERATION", event.identity, "duplicate name in one scan"
                )
            seen.add(name)
            self._meter_input_metadata(
                work,
                (
                    name,
                    link.observation.source_attribution,
                    link.observation.visibility_scope,
                    *self._claim_input_values(link.claim),
                ),
                event.byte_limit,
            )
            self._meter_provenance_encoding(
                work, link.claim.provenance, event.byte_limit
            )
            if link.claim.absence_evidence is not None:
                self._meter_absence_encoding(
                    work, link.claim.absence_evidence, event.byte_limit
                )
        self._meter_input_metadata(
            work,
            (
                event.source_attribution,
                event.visibility_scope,
                event.completion_coordinate,
                *event.prefixes,
                *event.nominated,
            ),
            event.byte_limit,
        )
        # Scope encoding is hex and thus can be bounded exactly before allocating.
        scope_size = 7 + sum(
            2 * len(v) + 2 for v in (*event.prefixes, *event.nominated)
        )
        scope_size += max(0, len(event.prefixes) - 1) + max(0, len(event.nominated) - 1)
        if scope_size > event.byte_limit:
            raise CoreFailure("BUDGET", event.identity, "finite event scope limit")
        self._charge(work, "input_bytes", scope_size)
        scope_json = event.scope_json
        with self._transaction():
            self._charge(work, "metadata_units", 1)
            existing = self._db.execute(
                "SELECT 1 FROM ref_enumeration_observations WHERE observation_origin_uuidv4=? AND enumeration_uuidv7=?",
                event.identity,
            ).fetchone()
            if existing:
                stored = self._read_ref_enumeration(
                    *event.identity,
                    work,
                    max_links=max_replay_links,
                    max_bytes=max_replay_bytes,
                )
                if stored.event != event or len(stored.links) != len(links):
                    raise CoreFailure(
                        "INCOMPATIBLE_REPLAY",
                        event.identity,
                        "enumeration event changed",
                    )
                for old, incoming in zip(stored.links, links, strict=True):
                    self._charge(work, "metadata_units", 1)
                    self._meter_input_metadata(
                        work,
                        (
                            incoming.observation.ref_name_bytes,
                            incoming.observation.source_attribution,
                            incoming.observation.visibility_scope,
                            *self._claim_input_values(incoming.claim),
                        ),
                        max_replay_bytes,
                    )
                    if (
                        old.observation != incoming.observation
                        or old.claim != incoming.claim
                        or old.derivation != incoming.derivation
                        or old.position != incoming.position
                    ):
                        raise CoreFailure(
                            "INCOMPATIBLE_REPLAY",
                            event.identity,
                            "enumeration item changed",
                        )
                return
            self._insert(
                "ref_enumeration_observations",
                (
                    *event.identity,
                    event.repository_uuidv4,
                    event.source_attribution,
                    event.visibility_scope,
                    scope_json,
                    event.enumeration_state,
                    event.completion_coordinate,
                    event.observed_at_us,
                    event.byte_limit,
                    event.ref_limit,
                    event.link_count,
                ),
            )
            for link in links:
                observation, claim = link.observation, link.claim
                self._charge(work, "metadata_units", 1)
                if self._db.execute(
                    "SELECT 1 FROM ref_observations WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=?",
                    observation.ref_observation_key.key,
                ).fetchone():
                    self._validate_ref_subject_dependency(
                        observation.ref_observation_key, work=work
                    )
                self._insert("ref_observations", observation.key)
                self._charge(work, "metadata_units", 1)
                if self._db.execute(
                    "SELECT 1 FROM ref_observation_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND provenance=?",
                    claim.identity,
                ).fetchone():
                    self._require_ref_claim(claim, work=work)
                for oid in (
                    claim.direct_target_oid,
                    claim.resolved_target_oid,
                    claim.peeled_target_oid,
                    claim.root_oid,
                ):
                    if oid is not None:
                        self._object(oid)
                self._meter_provenance_encoding(
                    work, claim.provenance, event.byte_limit
                )
                if claim.absence_evidence is not None:
                    self._meter_absence_encoding(
                        work, claim.absence_evidence, event.byte_limit
                    )
                self._insert("ref_observation_claims", claim.key)
                self._meter_provenance_encoding(
                    work, claim.provenance, event.byte_limit
                )
                key = link.key
                self._charge(work, "metadata_units", 1)
                self._insert("ref_enumeration_links", key)

    @_completed_read
    @_decoded_read
    def ref_enumeration(
        self,
        origin,
        event_id,
        work: WorkBudget,
        *,
        max_links=10_000,
        max_bytes=64 * 1024 * 1024,
    ):
        """Read one event and its actual links under a bounded snapshot."""
        uuid4_value(origin)
        from repo_catalog.domain.ref_observation import uuid7_value

        uuid7_value(event_id)
        if (
            type(max_links) is not int
            or not 0 < max_links < 2**63 - 1
            or type(max_bytes) is not int
            or not 0 < max_bytes < 2**63
        ):
            raise CoreFailure(
                "QUERY_BUDGET", (origin, event_id), "finite positive limits required"
            )
        self._available()
        with self._snapshot():
            return self._read_ref_enumeration(
                origin, event_id, work, max_links=max_links, max_bytes=max_bytes
            )

    def _read_ref_enumeration(self, origin, event_id, work, *, max_links, max_bytes):
        """Read fixed authority inside the caller's snapshot or writer cut."""
        row = self._bounded_stored_row(
            "ref_enumeration_observations",
            (origin, event_id),
            work,
            max_bytes,
            metadata_limit_code="QUERY_BUDGET",
        )
        if row is None:
            self._charge(work, "metadata_units", 1)
            if self._ref_note_one(
                "SELECT 1 FROM ref_enumeration_links WHERE enumeration_origin_uuidv4=? AND enumeration_uuidv7=? LIMIT 1",
                (origin, event_id),
            ):
                self._integrity_stop(((origin, event_id), "missing-enumeration-event"))
            raise CoreFailure(
                "ENUMERATION_UNAVAILABLE", (origin, event_id), "event unavailable"
            )

        def decode_event(value):
            scope = json.loads(value["enumeration_scope_json"])
            if (
                not isinstance(scope, list)
                or len(scope) != 2
                or not all(isinstance(group, list) for group in scope)
            ):
                raise ValueError("invalid enumeration scope")
            if sum(map(len, scope)) > max_links:
                raise CoreFailure(
                    "QUERY_BUDGET",
                    (origin, event_id),
                    "finite enumeration scope limit",
                )
            self._charge(work, "metadata_units", sum(map(len, scope)))
            prefixes, nominated = (
                tuple(bytes.fromhex(item) for item in group) for group in scope
            )
            event = RefEnumerationObservation(
                value["observation_origin_uuidv4"],
                value["enumeration_uuidv7"],
                value["repository_uuidv4"],
                value["source_attribution"],
                value["visibility_scope"],
                prefixes,
                nominated,
                value["enumeration_state"],
                value["completion_coordinate"],
                value["observed_at_us"],
                value["byte_limit"],
                value["ref_limit"],
                value["link_count"],
            )
            self._charge(work, "input_bytes", len(value["enumeration_scope_json"]))
            if event.key != tuple(value):
                raise ValueError("noncanonical enumeration event")
            return event

        event = self._stored((origin, event_id), decode_event, row)
        if event.link_count > max_links:
            raise CoreFailure(
                "QUERY_BUDGET", event.identity, "finite enumeration links limit"
            )
        self._charge(work, "metadata_units", 1)
        if not self._ref_note_one(
            "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
            (event.repository_uuidv4,),
        ):
            self._integrity_stop((event.identity, "missing-enumeration-repository"))
        columns = (
            "enumeration_origin_uuidv4",
            "enumeration_uuidv7",
            "observation_origin_uuidv4",
            "ref_observation_uuidv7",
            "claim_provenance",
            "derivation",
        )
        size_expr = "+".join(
            f"coalesce(octet_length({column}),0)" for column in columns
        )
        scan_limit = event.link_count + 1
        work.require("metadata_units", scan_limit)
        try:
            sizes = self._ref_note_many(
                f"SELECT {size_expr} FROM ref_enumeration_links WHERE enumeration_origin_uuidv4=? AND enumeration_uuidv7=? LIMIT ?",
                (origin, event_id, scan_limit),
            )
        except BaseException:
            abandon = getattr(work, "abandon", None)
            if abandon:
                abandon("metadata_units")
            else:
                work.charge("metadata_units", scan_limit)
            raise
        work.charge("metadata_units", len(sizes))
        total = sum(r[0] for r in sizes)
        if len(sizes) != event.link_count:
            self._integrity_stop((event.identity, "enumeration-link-count"))
        if total > max_bytes:
            raise CoreFailure(
                "QUERY_BUDGET", event.identity, "finite enumeration links limit"
            )
        self._charge(work, "input_bytes", total)
        rows = self._ref_note_many(
            "SELECT * FROM ref_enumeration_links WHERE enumeration_origin_uuidv4=? AND enumeration_uuidv7=? ORDER BY position",
            event.identity,
        )
        if len(rows) != event.link_count:
            self._integrity_stop((event.identity, "enumeration-link-count"))
        links, names = [], set()
        for item in rows:
            key = self._stored(
                event.identity,
                RefObservationKey,
                item["observation_origin_uuidv4"],
                item["ref_observation_uuidv7"],
            )
            subject_row = self._bounded_stored_row(
                "ref_observations",
                key.key,
                work,
                max_bytes,
                metadata_limit_code="QUERY_BUDGET",
            )
            claim_row = self._bounded_stored_row(
                "ref_observation_claims",
                (*key.key, item["claim_provenance"]),
                work,
                max_bytes,
                metadata_limit_code="QUERY_BUDGET",
            )
            if subject_row is None or claim_row is None:
                self._integrity_stop(
                    (event.identity, "missing-enumeration-link-dependency")
                )
            subject = self._stored(
                event.identity,
                RefObservation,
                key,
                subject_row["repository_uuidv4"],
                subject_row["ref_name_bytes"],
                subject_row["source_attribution"],
                subject_row["visibility_scope"],
                subject_row["observed_at_us"],
            )
            claim = self._stored(
                event.identity,
                lambda v: self._decode_ref_claim(
                    v,
                    work=work,
                    max_metadata_bytes=max_bytes,
                    metadata_limit_code="QUERY_BUDGET",
                ),
                claim_row,
            )
            self._require_ref_claim(
                claim,
                work=work,
                max_metadata_bytes=max_bytes,
                metadata_limit_code="QUERY_BUDGET",
            )
            link = self._stored(
                event.identity,
                RefEnumerationLink,
                event,
                subject,
                claim,
                item["derivation"],
                item["position"],
            )
            if subject.ref_name_bytes in names or link.position != len(links):
                self._integrity_stop((event.identity, "duplicate-enumeration-name"))
            names.add(subject.ref_name_bytes)
            links.append(link)
        return RefEnumerationResult(event, tuple(links))

    def _validate_ref_subject_dependency(
        self,
        key: RefObservationKey,
        *,
        work: WorkBudget | None = None,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        metadata_limit_code: str = "BUDGET",
    ) -> None:
        if work is None:
            row = self._db.execute(
                "SELECT * FROM ref_observations WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=?",
                key.key,
            ).fetchone()
        else:
            row = self._bounded_stored_row(
                "ref_observations",
                key.key,
                work,
                max_metadata_bytes,
                metadata_limit_code=metadata_limit_code,
            )
        if row is None:
            self._integrity_stop((key, "missing-observation-subject"))
        subject = self._stored(
            key,
            RefObservation,
            key,
            row["repository_uuidv4"],
            row["ref_name_bytes"],
            row["source_attribution"],
            row["visibility_scope"],
            row["observed_at_us"],
        )
        if (
            tuple(row) != subject.key
            or not self._db.execute(
                "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
                (subject.repository_uuidv4,),
            ).fetchone()
        ):
            self._integrity_stop((key, "invalid-observation-subject"))

    def _require_ref_claim(
        self,
        claim: RefObservationClaim,
        *,
        work: WorkBudget | None = None,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        metadata_limit_code: str = "BUDGET",
    ) -> None:
        """Never bind new evidence to a changed or absent result Claim."""
        if work is not None:
            self._meter_input_metadata(
                work,
                self._claim_input_values(claim),
                max_metadata_bytes,
                limit_code=metadata_limit_code,
            )
            self._meter_provenance_encoding(
                work,
                claim.provenance,
                max_metadata_bytes,
                limit_code=metadata_limit_code,
            )
        identity = claim.identity
        if work is None:
            row = self._db.execute(
                "SELECT * FROM ref_observation_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND provenance=?",
                identity,
            ).fetchone()
        else:
            row = self._bounded_stored_row(
                "ref_observation_claims",
                identity,
                work,
                max_metadata_bytes,
                metadata_limit_code=metadata_limit_code,
            )
        if row is None:
            raise CoreFailure(
                "MISSING_DEPENDENCY",
                identity,
                "original result claim is required",
            )
        if work is not None:
            self._meter_provenance_encoding(
                work,
                claim.provenance,
                max_metadata_bytes,
                limit_code=metadata_limit_code,
            )
            if claim.absence_evidence is not None:
                self._meter_absence_encoding(
                    work,
                    claim.absence_evidence,
                    max_metadata_bytes,
                    limit_code=metadata_limit_code,
                )
        if tuple(row) != claim.key:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY",
                identity,
                "original result claim cannot be rebound",
            )
        self._validate_ref_subject_dependency(
            claim.ref_observation_key,
            work=work,
            max_metadata_bytes=max_metadata_bytes,
            metadata_limit_code=metadata_limit_code,
        )
        for oid in (
            claim.direct_target_oid,
            claim.resolved_target_oid,
            claim.peeled_target_oid,
            claim.root_oid,
        ):
            if work is not None and oid is not None:
                self._charge(work, "metadata_units", 1)
            if (
                oid is not None
                and not self._db.execute(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                    oid.key,
                ).fetchone()
            ):
                self._integrity_stop((claim.identity, "missing-claim-object", oid.key))

    def _decode_ref_claim(
        self,
        row,
        *,
        work: WorkBudget | None = None,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        metadata_limit_code: str = "BUDGET",
    ) -> RefObservationClaim:
        def oid(fmt, value):
            if (fmt is None) != (value is None):
                raise ValueError("partial typed OID")
            return None if fmt is None else OID(fmt, value)

        result = RefObservationClaim(
            RefObservationKey(
                row["observation_origin_uuidv4"], row["ref_observation_uuidv7"]
            ),
            Provenance(*json.loads(row["provenance"])),
            row["presence_state"],
            row["ref_form"],
            oid(row["direct_format"], row["direct_target_oid"]),
            row["symbolic_target_ref_name"],
            oid(row["resolved_format"], row["resolved_target_oid"]),
            oid(row["peeled_format"], row["peeled_target_oid"]),
            oid(row["root_format"], row["root_oid"]),
            None
            if row["absence_evidence"] is None
            else RefAbsenceEvidence.decode(
                row["absence_evidence"],
                before_compare=(
                    None
                    if work is None
                    else lambda evidence: self._meter_absence_encoding(
                        work,
                        evidence,
                        max_metadata_bytes,
                        limit_code=metadata_limit_code,
                    )
                ),
            ),
        )
        if work is not None:
            self._meter_provenance_encoding(
                work,
                result.provenance,
                max_metadata_bytes,
                limit_code=metadata_limit_code,
            )
            if result.absence_evidence is not None:
                self._meter_absence_encoding(
                    work,
                    result.absence_evidence,
                    max_metadata_bytes,
                    limit_code=metadata_limit_code,
                )
        if result.key != tuple(row):
            raise ValueError("noncanonical stored ref claim")
        return result

    @_completed_read
    @_decoded_read
    def ref_observation(
        self,
        key: RefObservationKey,
        work: WorkBudget,
        *,
        max_claims: int = 10_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> RefObservationProjection:
        if not isinstance(key, RefObservationKey):
            raise CoreFailure("IDENTITY", key, "typed ref observation key required")
        if (
            type(max_claims) is not int
            or not 0 < max_claims < 2**63 - 2
            or type(max_bytes) is not int
            or not 0 < max_bytes < 2**63
        ):
            raise CoreFailure(
                "QUERY_BUDGET", key, "positive finite query limits required"
            )
        with self._snapshot():
            # Fetch only lengths before charging the bounded materialization;
            # reserve the maximum row scan before issuing either query.
            work.require("metadata_units", max_claims + 2)
            try:
                subject_length = "+".join(
                    f"coalesce(octet_length({column}),0)"
                    for column in _BOUNDED_STORED_ROWS["ref_observations"][1]
                )
                claim_length = "+".join(
                    f"coalesce(octet_length({column}),0)"
                    for column in _BOUNDED_STORED_ROWS["ref_observation_claims"][1]
                )
                subject_size = self.sql(
                    f"SELECT {subject_length} FROM ref_observations WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=?",
                    key.key,
                )
                claim_sizes = self.sql(
                    f"SELECT {claim_length} FROM ref_observation_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? LIMIT ?",
                    (*key.key, max_claims + 1),
                )
            except BaseException:
                abandon = getattr(work, "abandon", None)
                if abandon is not None:
                    abandon("metadata_units")
                else:
                    work.charge("metadata_units", max_claims + 2)
                raise
            else:
                work.charge("metadata_units", len(subject_size) + len(claim_sizes))
            input_bytes = sum(row[0] for row in subject_size) + sum(
                row[0] for row in claim_sizes
            )
            if not subject_size and claim_sizes:
                self._integrity_stop((key, "orphan-ref-claims"))
            if len(claim_sizes) > max_claims or input_bytes > max_bytes:
                raise CoreFailure(
                    "QUERY_BUDGET", key, "ref projection exceeds finite input limits"
                )
            self._charge(work, "input_bytes", input_bytes)
            rows = self.sql(
                "SELECT * FROM ref_observations WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=?",
                key.key,
            )
            if not rows:
                raise CoreFailure(
                    "OBSERVATION_UNAVAILABLE", key, "ref observation not found"
                )
            row = rows[0]
            observation = self._stored(
                key,
                RefObservation,
                key,
                row["repository_uuidv4"],
                row["ref_name_bytes"],
                row["source_attribution"],
                row["visibility_scope"],
                row["observed_at_us"],
            )
            self._validate_ref_subject_dependency(
                key,
                work=work,
                max_metadata_bytes=max_bytes,
                metadata_limit_code="QUERY_BUDGET",
            )
            rows = self.sql(
                "SELECT * FROM ref_observation_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? ORDER BY provenance",
                key.key,
            )
            claims = tuple(
                self._stored(
                    key,
                    lambda value: self._decode_ref_claim(
                        value,
                        work=work,
                        max_metadata_bytes=max_bytes,
                        metadata_limit_code="QUERY_BUDGET",
                    ),
                    row,
                )
                for row in rows
            )
            for claim in claims:
                self._charge(work, "metadata_units", 1)
                self._require_ref_claim(
                    claim,
                    work=work,
                    max_metadata_bytes=max_bytes,
                    metadata_limit_code="QUERY_BUDGET",
                )
                evidence = claim.absence_evidence
                if evidence is not None and (
                    evidence.source_attribution,
                    evidence.visibility_scope,
                    evidence.ref_name_bytes,
                ) != (
                    observation.source_attribution,
                    observation.visibility_scope,
                    observation.ref_name_bytes,
                ):
                    self._integrity_stop((key, "absence-subject"))
            return RefObservationProjection(
                observation, claims, ref_claim_conflict(claims)
            )

    def _notes_mapping(self, mapping: NotesMapping) -> None:
        existing = self._db.execute(
            "SELECT 1 FROM notes_mappings WHERE object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? AND note_oid=? AND mapping_path_json=?",
            mapping.key,
        ).fetchone()
        for oid in (mapping.root_oid, mapping.annotated_object_oid, mapping.note_oid):
            if (
                existing
                and not self._db.execute(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                    oid.key,
                ).fetchone()
            ):
                self._integrity_stop((mapping.key, "missing-mapping-object", oid.key))
            self._object(oid)
        self._insert("notes_mappings", mapping.key)

    def admit_notes_mapping(self, mapping: NotesMapping, work: WorkBudget) -> None:
        """Admit shareable mapping content without inventing a report or proof."""
        if not isinstance(mapping, NotesMapping):
            raise CoreFailure("NOTES_MAPPING", mapping, "typed mapping required")
        self._meter_input_metadata(
            work, self._mapping_input_values(mapping), 64 * 1024 * 1024
        )
        self._meter_mapping_path_encoding(work, mapping.mapping_path, 64 * 1024 * 1024)
        self._charge(work, "metadata_units", 4)
        with self._transaction():
            self._notes_mapping(mapping)

    def admit_notes_mapping_claim(self, claim: NotesMappingClaim) -> None:
        if not isinstance(claim, NotesMappingClaim):
            raise CoreFailure("NOTES_MAPPING", claim, "typed mapping claim required")
        with self._transaction():
            self._require_ref_claim(claim.ref_claim)
            self._notes_mapping(claim.mapping)
            self._insert("notes_mapping_claims", claim.key)

    def admit_notes_mapping_group(
        self, group: NotesMappingGroup, work: WorkBudget | None = None
    ) -> None:
        if not isinstance(group, NotesMappingGroup):
            raise CoreFailure("NOTES_GROUP", group, "typed mapping group required")
        if work is not None:
            if len(group.members) > 100_000:
                raise CoreFailure("BUDGET", "notes-group", "finite membership count")
            limit = 64 * 1024 * 1024
            values = (
                group.interpretation_kind,
                group.interpretation_version,
                group.interpretation_scope,
                group.group_scope,
                group.status,
                *group.provenance.key,
                *(value for member in group.members for value in member),
            )
            self._meter_input_metadata(work, values, limit)
            size = 2 + max(0, len(group.members) - 1)
            for member in group.members:
                self._charge(work, "metadata_units", 1)
                size += 4 + sum(
                    4 if value is None else self._json_string_bytes(value)
                    for value in member
                )
            if size > limit:
                raise CoreFailure(
                    "BUDGET", "notes-group", "finite membership encoding limit"
                )
            self._charge(work, "input_bytes", 2 * size)
            for _ in range(2):
                self._meter_provenance_encoding(work, group.provenance, limit)
                self._meter_provenance_encoding(work, group.ref_claim.provenance, limit)
        with self._transaction():
            self._require_ref_claim(group.ref_claim, work=work)
            if work is not None:
                self._charge(work, "metadata_units", 1)
            existing = self._db.execute(
                "SELECT 1 FROM notes_mapping_groups WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND group_scope=? AND status=? AND membership=? AND provenance=?",
                group.key,
            ).fetchone()
            for target, note, _path in group.members:
                for value in (target, note):
                    if work is not None:
                        self._charge(work, "metadata_units", 1)
                    oid = OID(group.ref_claim.root_oid.object_format, value)
                    if (
                        existing
                        and not self._db.execute(
                            "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                            oid.key,
                        ).fetchone()
                    ):
                        self._integrity_stop(
                            (group.ref_claim.identity, "missing-group-object", oid.key)
                        )
                    self._object(oid)
            self._insert("notes_mapping_groups", group.key)

    def _decode_mapping(
        self,
        row,
        *,
        work: WorkBudget | None = None,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        metadata_limit_code: str = "BUDGET",
    ) -> NotesMapping:
        path = json.loads(row["mapping_path_json"])
        if path is not None and not isinstance(path, str):
            raise ValueError("invalid stored mapping path")
        if work is not None:
            self._meter_mapping_path_encoding(
                work, path, max_metadata_bytes, limit_code=metadata_limit_code
            )
        if encode(path) != row["mapping_path_json"]:
            raise ValueError("noncanonical mapping path")
        return NotesMapping(
            OID(row["object_format"], row["root_oid"]),
            row["interpretation_kind"],
            row["interpretation_version"],
            row["interpretation_scope"],
            OID(row["object_format"], row["annotated_object_oid"]),
            OID(row["object_format"], row["note_oid"]),
            path,
        )

    def _assert_stored_mapping(self, mapping: NotesMapping, scope: object) -> None:
        row = self.sql(
            "SELECT 1 FROM notes_mappings WHERE object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? AND note_oid=? AND mapping_path_json=?",
            mapping.key,
        )
        if not row:
            self._integrity_stop((scope, "missing-notes-mapping"))
        for oid in (mapping.root_oid, mapping.annotated_object_oid, mapping.note_oid):
            if not self.sql(
                "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                oid.key,
            ):
                self._integrity_stop((scope, "missing-mapping-object", oid.key))

    def _ref_note_one(self, statement: str, parameters: tuple):
        """Execute a fixed one-row internal query in the current snapshot/cut."""
        try:
            return self._db.execute(statement, parameters).fetchone()
        except sqlite3.DatabaseError as error:
            if _sqlite_authority_failure(error) or (
                isinstance(error, sqlite3.OperationalError)
                and str(error).startswith("Could not decode to UTF-8")
            ):
                self._integrity_stop(("ref-note-read", str(error)))
            raise

    def _ref_note_many(self, statement: str, parameters: tuple):
        """Execute an already bounded fixed query within the current cut."""
        try:
            return self._db.execute(statement, parameters).fetchall()
        except sqlite3.DatabaseError as error:
            if _sqlite_authority_failure(error) or (
                isinstance(error, sqlite3.OperationalError)
                and str(error).startswith("Could not decode to UTF-8")
            ):
                self._integrity_stop(("ref-enumeration-read", str(error)))
            raise

    def _bounded_stored_row(
        self,
        table: str,
        parameters: tuple,
        work: WorkBudget,
        max_metadata_bytes: int,
        max_proof_bytes: int = 64 * 1024 * 1024,
        *,
        metadata_limit_code: str = "BUDGET",
    ):
        """Reserve every variable column before materializing a trusted row."""
        if table not in _BOUNDED_STORED_ROWS:
            raise ValueError("unsupported bounded row")
        if (
            type(max_metadata_bytes) is not int
            or not 0 < max_metadata_bytes < 2**63
            or type(max_proof_bytes) is not int
            or not 0 < max_proof_bytes < 2**63
        ):
            raise CoreFailure("BUDGET", table, "positive finite row limits required")
        predicate, columns, note = _BOUNDED_STORED_ROWS[table]
        self._charge(work, "metadata_units", 1)
        # SQLite's octet_length(column) reads the stored byte length from
        # metadata; casting a TEXT value to BLOB here would load its contents
        # before the input reservation. P1 already requires SQLite >= 3.51.3.
        sizes = ",".join(f"octet_length({column})" for column in columns)
        if note:
            sizes += ",octet_length(body),octet_length(proof_bundle),size"
        lengths = self._ref_note_one(
            f"SELECT {sizes} FROM {table} WHERE {predicate}", parameters
        )
        if lengths is None:
            return None
        metadata_lengths = tuple(lengths[: len(columns)])
        if any(
            value is not None and type(value) is not int for value in metadata_lengths
        ):
            self._integrity_stop((table, "invalid-column-length"))
        metadata_bytes = sum(value or 0 for value in metadata_lengths)
        body_bytes = proof_bytes = 0
        if note:
            body_bytes, proof_bytes, declared_size = tuple(lengths[len(columns) :])
            if (
                type(body_bytes) is not int
                or type(proof_bytes) is not int
                or type(declared_size) is not int
                or body_bytes != declared_size
            ):
                self._integrity_stop((table, parameters, "stored-note-size"))
            if (
                type(work.limits.note_bytes) is not int
                or not 0 < work.limits.note_bytes < 2**63
                or body_bytes > work.limits.note_bytes
                or proof_bytes > max_proof_bytes
            ):
                raise CoreFailure("BUDGET", table, "finite note or proof limit")
        reserved = metadata_bytes + body_bytes + proof_bytes
        if metadata_bytes > max_metadata_bytes or reserved >= 2**63:
            raise CoreFailure(
                metadata_limit_code, table, "finite metadata or row limit"
            )
        work.require("input_bytes", reserved)
        try:
            row = self._ref_note_one(
                f"SELECT * FROM {table} WHERE {predicate}", parameters
            )
        except BaseException:
            abandon = getattr(work, "abandon", None)
            if abandon is not None:
                abandon("input_bytes")
            else:
                work.charge("input_bytes", reserved)
            raise
        work.charge("input_bytes", reserved if row is not None else 0)
        if row is None:
            self._integrity_stop((table, parameters, "disappeared-stored-row"))
        return row

    def _fetch_ref_note_copy(
        self,
        oid: OID,
        copy: str,
        work: WorkBudget,
        max_proof_bytes: int,
        max_metadata_bytes: int,
    ):
        return self._bounded_stored_row(
            "ref_retained_notes",
            (*oid.key, copy),
            work,
            max_metadata_bytes,
            max_proof_bytes,
        )

    def _bounded_copy_key(self, tail: str, parameters: tuple, work: WorkBudget, scope):
        """Find one fixed-width copy identity before materializing its text."""
        self._charge(work, "metadata_units", 1)
        length = self._ref_note_one(
            "SELECT octet_length(physical_copy_uuidv4) " + tail, parameters
        )
        if length is None:
            return None
        if length[0] != 36:
            self._integrity_stop((scope, "invalid-copy-identity-length"))
        self._charge(work, "input_bytes", 36)
        self._charge(work, "metadata_units", 1)
        row = self._ref_note_one("SELECT physical_copy_uuidv4 " + tail, parameters)
        if row is None:
            self._integrity_stop((scope, "disappeared-copy-identity"))
        return self._stored(scope, uuid4_value, row[0])

    def _validate_stored_ref_note(
        self, row, work: WorkBudget, max_metadata_bytes: int, max_proof_bytes: int
    ):
        """Validate stored claim, root, mapping, role and body, not caller data."""
        scope = (row["object_format"], row["full_oid"], row["physical_copy_uuidv4"])
        self._stored(scope, uuid4_value, row["physical_copy_uuidv4"])
        identity = (
            row["observation_origin_uuidv4"],
            row["ref_observation_uuidv7"],
            row["ref_claim_provenance"],
        )
        stored_claim = self._bounded_stored_row(
            "ref_observation_claims", identity, work, max_metadata_bytes
        )
        if stored_claim is None:
            self._integrity_stop((scope, "missing-note-claim"))
        claim = self._stored(
            scope,
            lambda value: self._decode_ref_claim(
                value, work=work, max_metadata_bytes=max_metadata_bytes
            ),
            stored_claim,
        )
        try:
            self._require_ref_claim(
                claim, work=work, max_metadata_bytes=max_metadata_bytes
            )
        except sqlite3.OperationalError as error:
            if str(error).startswith("Could not decode to UTF-8"):
                self._integrity_stop((scope, "stored-claim-or-subject-utf8"))
            raise
        mapping = self._stored(
            scope,
            lambda value: self._decode_mapping(
                value, work=work, max_metadata_bytes=max_metadata_bytes
            ),
            row,
        )
        if (
            row["role_format"] != row["object_format"]
            or row["full_oid"] != row["note_oid"]
            or claim.root_oid != mapping.root_oid
        ):
            self._integrity_stop((scope, "note-claim-root"))
        self._meter_mapping_path_encoding(
            work, mapping.mapping_path, max_metadata_bytes
        )
        mapping_key = mapping.key
        self._charge(work, "metadata_units", 1)
        if not self._ref_note_one(
            "SELECT 1 FROM notes_mappings WHERE object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? AND note_oid=? AND mapping_path_json=?",
            mapping_key,
        ):
            self._integrity_stop((scope, "missing-notes-mapping"))
        for oid in (mapping.root_oid, mapping.annotated_object_oid, mapping.note_oid):
            self._charge(work, "metadata_units", 1)
            if not self._ref_note_one(
                "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                oid.key,
            ):
                self._integrity_stop((scope, "missing-mapping-object", oid.key))
        evidence_values = (
            *identity,
            *mapping_key,
            row["verification_scope"],
            row["role_provenance"],
            row["proof_bundle"],
        )
        self._meter_input_metadata(
            work,
            (
                *identity,
                *mapping_key,
                row["verification_scope"],
                row["role_provenance"],
            ),
            max_metadata_bytes,
        )
        self._meter_input_metadata(work, (row["proof_bundle"],), max_proof_bytes)
        self._charge(work, "metadata_units", 1)
        if not self._ref_note_one(
            "SELECT 1 FROM notes_mapping_evidence WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? AND note_oid=? AND mapping_path_json=? AND verification_scope=? AND provenance=? AND proof_bundle=?",
            evidence_values,
        ):
            self._integrity_stop((scope, "missing-notes-role-evidence"))
        role = self._stored(
            scope,
            NotesMappingEvidenceRecord,
            mapping,
            row["verification_scope"],
            self._provenance_value(
                scope,
                row["role_provenance"],
                work=work,
                max_metadata_bytes=max_metadata_bytes,
            ),
            row["proof_bundle"],
        )
        self._meter_input_metadata(work, (role.proof_bundle,), max_proof_bytes)
        try:
            with account_verification(work):
                try:
                    valid = valid_note_role(
                        *mapping.root_oid.key,
                        mapping.annotated_object_oid.full_oid,
                        mapping.note_oid.full_oid,
                        mapping.mapping_path,
                        role.proof_bundle,
                    ) and valid_native(
                        *mapping.note_oid.key,
                        "blob",
                        row["body"],
                        row["size"],
                        row["digest_sha256"],
                    )
                except (ValueError, TypeError, RecursionError, OverflowError):
                    valid = False
                if not valid:
                    raise CoreFailure(
                        "STORED_NOTES_EVIDENCE", scope, "invalid stored proof or body"
                    )
        except CoreFailure as error:
            if error.code == "STORED_NOTES_EVIDENCE":
                self._integrity_stop((scope, "invalid-note-proof-or-body"))
            raise
        return claim, mapping, row["body"]

    def _validate_stored_legacy_note(
        self, row, work: WorkBudget, max_metadata_bytes: int, max_proof_bytes: int
    ):
        """Diagnose old-format authority without using it for a new role."""
        scope = (row["object_format"], row["full_oid"], row["physical_copy_uuidv4"])
        self._stored(scope, uuid4_value, row["physical_copy_uuidv4"])
        pair = (row["capture_origin_uuidv4"], row["capture_uuidv4"])
        capture_row = self._bounded_stored_row(
            "captures", pair, work, max_metadata_bytes
        )
        if capture_row is None:
            self._integrity_stop((scope, "missing-legacy-capture"))

        def decode_capture(value):
            tag, raw_hex = json.loads(value["ref"])
            if tag != "native-ref":
                raise ValueError("invalid stored ref tag")
            raw = bytes.fromhex(raw_hex)
            ref = raw.decode("utf-8", "surrogateescape")
            capture = Capture(
                value["capture_origin_uuidv4"],
                value["capture_uuidv4"],
                value["repository_uuidv4"],
                value["source"],
                ref,
                OID(value["object_format"], value["root"]),
            )
            encoded_size = 3 + self._json_string_bytes("native-ref") + 2 + 2 * len(raw)
            if encoded_size > max_metadata_bytes:
                raise CoreFailure("BUDGET", scope, "finite legacy ref metadata limit")
            self._charge(work, "input_bytes", encoded_size)
            if capture.key != tuple(value):
                raise ValueError("noncanonical stored capture")
            return capture

        capture = self._stored(scope, decode_capture, capture_row)
        root = self._stored(scope, OID, row["object_format"], row["root"])
        target = self._stored(scope, OID, row["object_format"], row["target"])
        note = self._stored(scope, OID, row["object_format"], row["full_oid"])
        if capture.root != root:
            self._integrity_stop((scope, "legacy-capture-root"))
        self._charge(work, "metadata_units", 1)
        if not self._ref_note_one(
            "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
            (capture.repository_uuidv4,),
        ):
            self._integrity_stop((scope, "missing-legacy-repository"))
        for oid in (root, target, note):
            self._charge(work, "metadata_units", 1)
            if not self._ref_note_one(
                "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                oid.key,
            ):
                self._integrity_stop((scope, "missing-legacy-object", oid.key))
        self._meter_input_metadata(
            work,
            (*pair, *root.key, target.full_oid, note.full_oid, row["path"]),
            max_metadata_bytes,
        )
        self._meter_input_metadata(work, (row["proof_bundle"],), max_proof_bytes)
        self._charge(work, "metadata_units", 1)
        if not self._ref_note_one(
            "SELECT 1 FROM note_roles WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? AND root=? AND target=? AND note=? AND path=? AND proof_bundle=?",
            (
                *pair,
                *root.key,
                target.full_oid,
                note.full_oid,
                row["path"],
                row["proof_bundle"],
            ),
        ):
            self._integrity_stop((scope, "missing-legacy-role"))
        self._meter_input_metadata(work, (row["proof_bundle"],), max_proof_bytes)
        try:
            with account_verification(work):
                try:
                    valid = valid_note_role(
                        *root.key,
                        target.full_oid,
                        note.full_oid,
                        row["path"],
                        row["proof_bundle"],
                    ) and valid_native(
                        *note.key,
                        "blob",
                        row["body"],
                        row["size"],
                        row["digest_sha256"],
                    )
                except (ValueError, TypeError, RecursionError, OverflowError):
                    valid = False
                if not valid:
                    raise CoreFailure(
                        "STORED_NOTES_EVIDENCE", scope, "invalid legacy proof or body"
                    )
        except CoreFailure as error:
            if error.code == "STORED_NOTES_EVIDENCE":
                self._integrity_stop((scope, "invalid-legacy-proof-or-body"))
            raise
        return row["body"]

    def _diagnose_ref_note_conflict(
        self,
        native: NativeObject,
        work: WorkBudget,
        max_proof_bytes: int,
        max_metadata_bytes: int,
        max_existing_copies: int,
    ) -> None:
        """Check only an observed representation conflict, inside the writer cut.

        A valid colliding representation is an incompatible input, not proof of
        catalog damage. Each inspected copy is bounded and charged separately.
        """
        inspected = 0
        for table in ("ref_retained_notes", "retained_notes"):
            previous = ""
            while True:
                tail = (
                    f"FROM {table} WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4>? "
                    "ORDER BY physical_copy_uuidv4 LIMIT 1"
                )
                copy = self._bounded_copy_key(
                    tail, (*native.oid.key, previous), work, native.oid
                )
                if copy is None:
                    break
                if inspected == max_existing_copies:
                    raise CoreFailure("BUDGET", native.oid, "note conflict copy limit")
                row = self._bounded_stored_row(
                    table,
                    (*native.oid.key, copy),
                    work,
                    max_metadata_bytes,
                    max_proof_bytes,
                )
                if row is None:
                    self._integrity_stop((native.oid, copy, "missing-conflict-copy"))
                if table == "ref_retained_notes":
                    self._validate_stored_ref_note(
                        row, work, max_metadata_bytes, max_proof_bytes
                    )
                else:
                    self._validate_stored_legacy_note(
                        row, work, max_metadata_bytes, max_proof_bytes
                    )
                # Continue through both tables even after a valid collision:
                # another compared copy may independently be damaged.
                previous = copy
                inspected += 1

    def _note_comparison_cost(
        self, native: NativeObject, work: WorkBudget, max_copies: int
    ) -> int:
        """Preflight the body comparisons performed by the INSERT triggers.

        The query returns only bounded metadata; octet_length on the columns
        does not materialize their bodies. Failed scans keep their reservation.
        """
        work.require("metadata_units", max_copies + 1)
        try:
            rows = self._db.execute(
                "SELECT octet_length(body),size FROM ref_retained_notes WHERE object_format=? AND full_oid=? "
                "UNION ALL SELECT octet_length(body),size FROM retained_notes WHERE object_format=? AND full_oid=? LIMIT ?",
                (*native.oid.key, *native.oid.key, max_copies + 1),
            ).fetchall()
        except BaseException as error:
            abandon = getattr(work, "abandon", None)
            if abandon is not None:
                abandon("metadata_units")
            else:
                work.charge("metadata_units", max_copies + 1)
            if _sqlite_authority_failure(error):
                self._integrity_stop((native.oid, "note-comparison-scan"))
            raise
        work.charge("metadata_units", len(rows))
        for length, declared in rows:
            if (
                type(length) is not int
                or type(declared) is not int
                or length != declared
            ):
                self._integrity_stop((native.oid, "stored-note-size"))
        if len(rows) > max_copies:
            raise CoreFailure("BUDGET", native.oid, "note comparison copy limit")
        total = sum(row[0] for row in rows)
        if total >= 2**63:
            raise CoreFailure("BUDGET", native.oid, "note comparison bytes limit")
        return total

    @_completed_read
    @_decoded_read
    def notes_mapping_projection(
        self,
        ref_claim: RefObservationClaim,
        annotated_object_oid: OID,
        interpretation_kind: str,
        interpretation_version: str,
        interpretation_scope: str,
        work: WorkBudget,
        *,
        max_units: int = 10_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> NotesMappingProjection:
        """Expose attributed reports, whole groups and independently checked evidence.

        The explicit interpretation scope avoids combining incomparable mappings.
        Actual proof revalidation is charged to the supplied finite work budget.
        """
        if (
            not isinstance(ref_claim, RefObservationClaim)
            or ref_claim.root_oid is None
            or not isinstance(annotated_object_oid, OID)
            or annotated_object_oid.object_format != ref_claim.root_oid.object_format
            or not all(
                isinstance(x, str) and x
                for x in (
                    interpretation_kind,
                    interpretation_version,
                    interpretation_scope,
                )
            )
            or type(max_units) is not int
            or not 0 < max_units < 2**63 - 1
            or type(max_bytes) is not int
            or not 0 < max_bytes < 2**63
        ):
            raise CoreFailure(
                "NOTES_SCOPE",
                ref_claim,
                "exact claim, typed target and interpretation scope required",
            )
        self._available()
        self._meter_input_metadata(
            work,
            (
                *self._claim_input_values(ref_claim),
                *annotated_object_oid.key,
                interpretation_kind,
                interpretation_version,
                interpretation_scope,
            ),
            max_bytes,
            limit_code="QUERY_BUDGET",
        )
        self._meter_provenance_encoding(
            work, ref_claim.provenance, max_bytes, limit_code="QUERY_BUDGET"
        )
        coordinates = (
            *ref_claim.identity,
            *ref_claim.root_oid.key,
            interpretation_kind,
            interpretation_version,
            interpretation_scope,
        )
        with self._snapshot():
            self._require_ref_claim(
                ref_claim,
                work=work,
                max_metadata_bytes=max_bytes,
                metadata_limit_code="QUERY_BUDGET",
            )
            # Bound both row count and materialized text before fetching whole
            # memberships/proof bundles into Python. This scans at most one
            # extra row per selected family; no over-limit result is truncated
            # into an apparently complete projection.
            units = 0
            input_bytes = 0
            where = (
                "observation_origin_uuidv4=? AND ref_observation_uuidv7=? "
                "AND ref_claim_provenance=? AND object_format=? AND root_oid=? "
                "AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=?"
            )
            families = (
                ("notes_mapping_claims", ("provenance", "mapping_path_json"), True),
                (
                    "notes_mapping_groups",
                    ("provenance", "membership", "group_scope", "status"),
                    False,
                ),
                (
                    "notes_mapping_evidence",
                    (
                        "provenance",
                        "mapping_path_json",
                        "verification_scope",
                        "proof_bundle",
                    ),
                    True,
                ),
            )
            common = (
                "observation_origin_uuidv4",
                "ref_observation_uuidv7",
                "ref_claim_provenance",
                "object_format",
                "root_oid",
                "interpretation_kind",
                "interpretation_version",
                "interpretation_scope",
            )
            # Reserve the maximum scan before touching rows. Failed or
            # interrupted scans keep the reservation when work is uncertain.
            work.require("metadata_units", max_units + 1)
            try:
                for table, extra, target_scoped in families:
                    columns = (*common, *extra)
                    if target_scoped:
                        columns += ("annotated_object_oid", "note_oid")
                    size_expr = "+".join(
                        f"coalesce(octet_length({column}),0)" for column in columns
                    )
                    predicate = where + (
                        " AND annotated_object_oid=?" if target_scoped else ""
                    )
                    values = (
                        *coordinates,
                        *((annotated_object_oid.full_oid,) if target_scoped else ()),
                        max_units - units + 1,
                    )
                    sizes = self.sql(
                        f"SELECT {size_expr} FROM {table} WHERE {predicate} LIMIT ?",
                        values,
                    )
                    units += len(sizes)
                    input_bytes += sum(row[0] for row in sizes)
                    if units > max_units or input_bytes > max_bytes:
                        break
            except BaseException:
                abandon = getattr(work, "abandon", None)
                if abandon is not None:
                    abandon("metadata_units")
                else:
                    work.charge("metadata_units", max_units + 1)
                raise
            else:
                work.charge("metadata_units", units)
            if units > max_units or input_bytes > max_bytes:
                raise CoreFailure(
                    "QUERY_BUDGET",
                    ref_claim.identity,
                    "mapping projection exceeds finite input limits",
                )
            # The full text is fetched only after its bounded byte cost is
            # charged; the preflight above materializes integer lengths only.
            self._charge(work, "input_bytes", input_bytes)
            reported_rows = self.sql(
                "SELECT * FROM notes_mapping_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? ORDER BY provenance",
                (*coordinates, annotated_object_oid.full_oid),
            )
            reports = []
            for row in reported_rows:

                def decode_report(value):
                    claim = NotesMappingClaim(
                        ref_claim,
                        self._decode_mapping(
                            value,
                            work=work,
                            max_metadata_bytes=max_bytes,
                            metadata_limit_code="QUERY_BUDGET",
                        ),
                        Provenance(*json.loads(value["provenance"])),
                    )
                    if claim.key != tuple(value):
                        raise ValueError("noncanonical stored mapping claim")
                    return claim

                self._charge(work, "metadata_units", 1)
                report = self._stored(ref_claim.identity, decode_report, row)
                self._assert_stored_mapping(report.mapping, ref_claim.identity)
                reports.append(report)
            group_rows = self.sql(
                "SELECT * FROM notes_mapping_groups WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? ORDER BY group_scope,provenance",
                coordinates,
            )
            groups = []
            for row in group_rows:

                def decode_group(value):
                    group = NotesMappingGroup(
                        ref_claim,
                        value["interpretation_kind"],
                        value["interpretation_version"],
                        value["interpretation_scope"],
                        value["group_scope"],
                        value["status"],
                        tuple(tuple(m) for m in json.loads(value["membership"])),
                        Provenance(*json.loads(value["provenance"])),
                    )
                    if group.key != tuple(value):
                        raise ValueError("noncanonical stored mapping group")
                    return group

                self._charge(work, "metadata_units", 1)
                group = self._stored(ref_claim.identity, decode_group, row)
                for target, note, _path in group.members:
                    self._charge(work, "metadata_units", 1)
                    for oid in (target, note):
                        if not self.sql(
                            "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                            (ref_claim.root_oid.object_format, oid),
                        ):
                            self._integrity_stop(
                                (ref_claim.identity, "missing-group-object", oid)
                            )
                groups.append(group)
            evidence_rows = self.sql(
                "SELECT * FROM notes_mapping_evidence WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? ORDER BY provenance",
                (*coordinates, annotated_object_oid.full_oid),
            )
            evidence = []
            for row in evidence_rows:

                def decode_evidence(value):
                    record = NotesMappingEvidenceRecord(
                        self._decode_mapping(
                            value,
                            work=work,
                            max_metadata_bytes=max_bytes,
                            metadata_limit_code="QUERY_BUDGET",
                        ),
                        value["verification_scope"],
                        Provenance(*json.loads(value["provenance"])),
                        value["proof_bundle"],
                    )
                    if (
                        *ref_claim.identity,
                        *record.mapping.key,
                        record.verification_scope,
                        record.provenance.encoded,
                        record.proof_bundle,
                    ) != tuple(value):
                        raise ValueError("noncanonical stored mapping evidence")
                    return record

                self._charge(work, "metadata_units", 1)
                record = self._stored(ref_claim.identity, decode_evidence, row)
                self._assert_stored_mapping(record.mapping, ref_claim.identity)
                try:
                    with account_verification(work):
                        self._charge(work, "input_bytes", len(record.proof_bundle))
                        if not valid_note_role(
                            *record.mapping.root_oid.key,
                            annotated_object_oid.full_oid,
                            record.mapping.note_oid.full_oid,
                            record.mapping.mapping_path,
                            record.proof_bundle,
                        ):
                            raise CoreFailure(
                                "STORED_NOTES_EVIDENCE",
                                ref_claim.identity,
                                "invalid stored mapping proof",
                            )
                except CoreFailure as error:
                    if error.code == "STORED_NOTES_EVIDENCE":
                        self._integrity_stop(
                            (ref_claim.identity, "notes-mapping-evidence")
                        )
                    raise
                evidence.append(record)
            positives = {claim.mapping.note_oid for claim in reports}
            absent = False
            for group in groups:
                matching = [
                    member
                    for member in group.members
                    if member[0] == annotated_object_oid.full_oid
                ]
                positives.update(
                    OID(annotated_object_oid.object_format, member[1])
                    for member in matching
                )
                if (
                    group.group_scope
                    in (
                        "all-notes-mappings",
                        encode(["target", annotated_object_oid.full_oid]),
                    )
                    and group.status in ("complete", "known_empty")
                    and not matching
                ):
                    absent = True
            checked = {record.mapping.note_oid for record in evidence}
            return NotesMappingProjection(
                ref_claim,
                annotated_object_oid,
                tuple(reports),
                tuple(groups),
                tuple(evidence),
                next(iter(checked)) if len(checked) == 1 else None,
                len(positives | checked) > 1 or (absent and bool(positives | checked)),
            )

    def _notes_mapping_evidence(
        self,
        evidence: NotesMappingEvidence,
        *,
        work: WorkBudget | None = None,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        max_proof_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        self._require_ref_claim(
            evidence.ref_claim, work=work, max_metadata_bytes=max_metadata_bytes
        )
        if work is not None:
            self._meter_mapping_path_encoding(
                work, evidence.mapping.mapping_path, max_metadata_bytes
            )
            self._meter_mapping_path_encoding(
                work, evidence.mapping.mapping_path, max_metadata_bytes
            )
        self._notes_mapping(evidence.mapping)
        if work is not None:
            self._meter_provenance_encoding(
                work, evidence.ref_claim.provenance, max_metadata_bytes
            )
            self._meter_mapping_path_encoding(
                work, evidence.mapping.mapping_path, max_metadata_bytes
            )
            self._meter_provenance_encoding(
                work, evidence.provenance, max_metadata_bytes
            )
            self._meter_proof_bundle(work, evidence, max_proof_bytes)
        self._insert("notes_mapping_evidence", evidence.key)

    def admit_notes_mapping_evidence(
        self,
        evidence: NotesMappingEvidence,
        work: WorkBudget,
        *,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        max_proof_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        """Check actual structure locally; a sender flag is never role authority."""
        if not isinstance(evidence, NotesMappingEvidence):
            raise CoreFailure(
                "NOTES_ROLE", evidence, "typed receiver evidence required"
            )
        self._available()
        self._meter_input_metadata(
            work,
            (
                *self._mapping_input_values(evidence.mapping),
                *evidence.provenance.key,
                evidence.verification_scope,
            ),
            max_metadata_bytes,
        )
        self._meter_provenance_encoding(work, evidence.provenance, max_metadata_bytes)
        self._meter_mapping_path_encoding(
            work, evidence.mapping.mapping_path, max_metadata_bytes
        )
        with account_verification(work):
            for structure in evidence.structures:
                self._charge(work, "input_bytes", len(structure.body))
            self._meter_proof_bundle(work, evidence, max_proof_bytes)
            evidence.validate()
            self._charge(work, "metadata_units", 1)
            with self._transaction():
                self._notes_mapping_evidence(
                    evidence,
                    work=work,
                    max_metadata_bytes=max_metadata_bytes,
                    max_proof_bytes=max_proof_bytes,
                )

    def admit_ref_note(
        self,
        evidence: NotesMappingEvidence,
        native: NativeObject,
        physical_copy_uuidv4: str,
        work: WorkBudget,
        *,
        before_commit: Callable[[], None] | None = None,
        max_proof_bytes: int = 64 * 1024 * 1024,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        max_existing_copies: int = 1_000,
    ) -> None:
        """Admit a body only with locally checked claim-specific role evidence."""
        if not isinstance(evidence, NotesMappingEvidence) or not isinstance(
            native, NativeObject
        ):
            raise CoreFailure("NOTES_BODY", "ref", "typed evidence and body required")
        self._available()
        uuid4_value(physical_copy_uuidv4)
        if (
            type(work.limits.note_bytes) is not int
            or not 0 < work.limits.note_bytes < 2**63
        ):
            raise CoreFailure(
                "BUDGET", "note_bytes", "positive finite note limit required"
            )
        if len(native.body) > work.limits.note_bytes:
            raise CoreFailure("BUDGET", native.oid, "individual note size limit")
        if native.oid != evidence.mapping.note_oid or native.native_type != "blob":
            raise CoreFailure(
                "NOTES_BODY", native.oid, "exact mapped note blob required"
            )
        if (
            type(max_proof_bytes) is not int
            or not 0 < max_proof_bytes < 2**63
            or type(max_metadata_bytes) is not int
            or not 0 < max_metadata_bytes < 2**63
            or type(max_existing_copies) is not int
            or not 0 < max_existing_copies < 2**63 - 1
        ):
            raise CoreFailure(
                "BUDGET", native.oid, "positive finite proof and copy limits required"
            )
        self._meter_input_metadata(
            work,
            (
                *self._mapping_input_values(evidence.mapping),
                *evidence.provenance.key,
                evidence.verification_scope,
            ),
            max_metadata_bytes,
        )
        self._meter_provenance_encoding(work, evidence.provenance, max_metadata_bytes)
        self._meter_mapping_path_encoding(
            work, evidence.mapping.mapping_path, max_metadata_bytes
        )
        with account_verification(work):
            for structure in evidence.structures:
                self._charge(work, "proof_steps", 1)
                self._charge(work, "input_bytes", len(structure.body))
                structure.validate()
            self._meter_proof_bundle(work, evidence, max_proof_bytes)
            evidence.validate()
            self._charge(work, "input_bytes", len(native.body))
            native.validate()
            self._charge(work, "metadata_units", 1)
            with self._transaction():
                # A copy key stores only the claim coordinate; compare the
                # entire incoming result to its immutable original on replay.
                self._require_ref_claim(
                    evidence.ref_claim, work=work, max_metadata_bytes=max_metadata_bytes
                )
                # This is inside the writer cut, before any replay insertion can
                # trip a representation trigger or conceal damaged authority.
                existing = self._fetch_ref_note_copy(
                    native.oid,
                    physical_copy_uuidv4,
                    work,
                    max_proof_bytes,
                    max_metadata_bytes,
                )
                self._meter_provenance_encoding(
                    work, evidence.ref_claim.provenance, max_metadata_bytes
                )
                self._meter_mapping_path_encoding(
                    work, evidence.mapping.mapping_path, max_metadata_bytes
                )
                self._meter_provenance_encoding(
                    work, evidence.provenance, max_metadata_bytes
                )
                self._meter_proof_bundle(work, evidence, max_proof_bytes)
                values = (
                    *native.oid.key,
                    physical_copy_uuidv4,
                    native.body,
                    native.declared_size,
                    native.digest_sha256,
                    *evidence.key,
                )
                if existing is not None:
                    self._validate_stored_ref_note(
                        existing, work, max_metadata_bytes, max_proof_bytes
                    )
                    if tuple(existing) != values:
                        raise CoreFailure(
                            "INCOMPATIBLE_REPLAY",
                            native.oid,
                            "inconsistent immutable note copy",
                        )
                    if before_commit is not None:
                        before_commit()
                    return
                self._notes_mapping_evidence(
                    evidence,
                    work=work,
                    max_metadata_bytes=max_metadata_bytes,
                    max_proof_bytes=max_proof_bytes,
                )
                comparison_bytes = self._note_comparison_cost(
                    native, work, max_existing_copies
                )
                if comparison_bytes:
                    work.require("input_bytes", comparison_bytes)
                try:
                    self._insert("ref_retained_notes", values)
                except BaseException as error:
                    if comparison_bytes:
                        abandon = getattr(work, "abandon", None)
                        if abandon is not None:
                            abandon("input_bytes")
                        else:
                            work.charge("input_bytes", comparison_bytes)
                    if (
                        isinstance(error, sqlite3.IntegrityError)
                        and str(error) == "conflicting exact note representation"
                    ):
                        self._diagnose_ref_note_conflict(
                            native,
                            work,
                            max_proof_bytes,
                            max_metadata_bytes,
                            max_existing_copies,
                        )
                    raise
                else:
                    if comparison_bytes:
                        work.charge("input_bytes", comparison_bytes)
                if before_commit is not None:
                    before_commit()

    @_completed_read
    @_decoded_read
    def read_ref_note(
        self,
        claim: RefObservationClaim,
        mapping: NotesMapping,
        work: WorkBudget,
        *,
        max_proof_bytes: int = 64 * 1024 * 1024,
        max_metadata_bytes: int = 64 * 1024 * 1024,
    ) -> bytes:
        if (
            not isinstance(claim, RefObservationClaim)
            or not isinstance(mapping, NotesMapping)
            or claim.root_oid != mapping.root_oid
        ):
            raise CoreFailure(
                "NOTES_ROLE", claim, "exact claimed root and mapping required"
            )
        if (
            type(max_proof_bytes) is not int
            or not 0 < max_proof_bytes < 2**63
            or type(max_metadata_bytes) is not int
            or not 0 < max_metadata_bytes < 2**63
        ):
            raise CoreFailure(
                "BUDGET",
                claim.ref_observation_key,
                "positive finite proof limit required",
            )
        self._available()
        self._meter_input_metadata(
            work, self._mapping_input_values(mapping), max_metadata_bytes
        )
        self._meter_mapping_path_encoding(
            work, mapping.mapping_path, max_metadata_bytes
        )
        with self._snapshot():
            self._require_ref_claim(
                claim, work=work, max_metadata_bytes=max_metadata_bytes
            )
            self._meter_provenance_encoding(work, claim.provenance, max_metadata_bytes)
            self._meter_mapping_path_encoding(
                work, mapping.mapping_path, max_metadata_bytes
            )
            identity = claim.identity
            mapping_key = mapping.key
            copy = self._bounded_copy_key(
                "FROM ref_retained_notes INDEXED BY ref_retained_notes_role_lookup WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND role_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? AND note_oid=? AND mapping_path_json=? ORDER BY physical_copy_uuidv4 LIMIT 1",
                (*identity, *mapping_key),
                work,
                identity,
            )
            if copy is None:
                raise CoreFailure(
                    "NOTES_ROLE_UNAVAILABLE",
                    claim.identity,
                    "no claim-specific receiver-proven note body",
                )
            row = self._fetch_ref_note_copy(
                mapping.note_oid, copy, work, max_proof_bytes, max_metadata_bytes
            )
            if row is None:
                self._integrity_stop((claim.identity, "missing-selected-note"))
            stored_claim, stored_mapping, body = self._validate_stored_ref_note(
                row, work, max_metadata_bytes, max_proof_bytes
            )
            if stored_claim != claim or stored_mapping != mapping:
                self._integrity_stop((claim.identity, "selected-note-scope"))
            return body

    def _capture(self, capture: Capture) -> None:
        self._object(capture.root)
        self._insert("captures", capture.key)

    def admit_capture(self, capture: Capture) -> None:
        with self._transaction():
            self._capture(capture)

    def admit_notes_claim(self, claim: NotesClaim) -> None:
        self._reported(claim.provenance)
        with self._transaction():
            self._capture(claim.capture)
            self._object(claim.target)
            self._object(claim.note)
            self._insert("notes_claims", claim.key)

    def admit_notes_group(self, group: NotesGroup) -> None:
        self._reported(group.provenance)
        with self._transaction():
            self._capture(group.capture)
            for target, note, _path in group.members:
                self._object(OID(group.capture.root.object_format, target))
                self._object(OID(group.capture.root.object_format, note))
            self._insert("notes_groups", group.key)

    @staticmethod
    def _charge(work: WorkBudget, unit: str, amount: int) -> None:
        work.require(unit, amount)
        work.charge(unit, amount)

    def _metadata(self, native: NativeObject, copy: str) -> None:
        self._object(native.oid)
        self._insert(
            "retained_metadata",
            (
                *native.oid.key,
                copy,
                native.native_type,
                native.body,
                native.declared_size,
                native.digest_sha256,
            ),
        )
        for field, value in (("type", native.native_type), ("size", len(native.body))):
            provenance = Provenance(
                "receiver-intrinsic",
                encode(native.oid.key),
                f"native-{field}",
                "p1-native",
                "1",
                "receiver_intrinsic",
            )
            claim = ScalarClaim(native.oid, field, value, provenance)
            self._claim(claim)
            self._insert("intrinsic_claims", (*claim.key, copy))
        relations = {
            "commit": ("commit_parents", "commit_tree"),
            "tree": ("tree_entries",),
            "tag": ("tag_target",),
        }[native.native_type]
        for relation in relations:
            members = intrinsic_members(
                native.oid.object_format, native.native_type, native.body, relation
            )
            provenance = Provenance(
                "receiver-intrinsic",
                encode(native.oid.key),
                relation,
                "p1-native",
                "1",
                "receiver_intrinsic",
            )
            group = RelationGroup(
                native.oid,
                relation,
                "native-entire-relation",
                "complete" if members else "known_empty",
                tuple(
                    RelationMember(
                        tuple(m[0]) if isinstance(m[0], list) else m[0], OID(m[1], m[2])
                    )
                    for m in members
                ),
                provenance,
            )
            self._group(group)
            self._insert("intrinsic_groups", (*group.key, copy))

    def admit_metadata(
        self, native: NativeObject, physical_copy_uuidv4: str, work: WorkBudget
    ) -> None:
        self._available()
        uuid4_value(physical_copy_uuidv4)
        if native.native_type not in ("commit", "tree", "tag"):
            raise CoreFailure(
                "RETENTION_PURPOSE",
                native.oid,
                "ordinary-file blob bodies are excluded",
            )
        with account_verification(work):
            self._charge(work, "input_bytes", len(native.body))
            native.validate()
            self._charge(work, "metadata_units", 1)
            with self._transaction():
                self._metadata(native, physical_copy_uuidv4)

    def admit_notes_role(self, proof: NotesProof, work: WorkBudget) -> None:
        """Check one relevant structural mapping without acquiring note bytes."""
        self._available()
        with account_verification(work):
            for structure in proof.structures:
                self._charge(work, "input_bytes", len(structure.body))
            proof.validate()
            self._charge(work, "metadata_units", 1)
            with self._transaction():
                self._capture(proof.capture)
                self._object(proof.target)
                self._object(proof.note)
                self._insert("note_roles", proof.key)

    def admit_note(
        self,
        proof: NotesProof,
        native: NativeObject,
        physical_copy_uuidv4: str,
        work: WorkBudget,
        *,
        before_commit: Callable[[], None] | None = None,
    ) -> None:
        self._available()
        uuid4_value(physical_copy_uuidv4)
        if (
            type(work.limits.note_bytes) is not int
            or not 0 < work.limits.note_bytes < 2**63
        ):
            raise CoreFailure(
                "BUDGET", "note_bytes", "positive finite note limit required"
            )
        if len(native.body) > work.limits.note_bytes:
            raise CoreFailure("BUDGET", native.oid, "individual note size limit")
        if native.oid != proof.note or native.native_type != "blob":
            raise CoreFailure(
                "NOTES_BODY", proof.note, "note body must have exact blob identity"
            )
        with account_verification(work):
            for structure in proof.structures:
                self._charge(work, "proof_steps", 1)
                self._charge(work, "input_bytes", len(structure.body))
                structure.validate()
            proof.validate()
            self._charge(work, "input_bytes", len(native.body))
            native.validate()
            self._charge(work, "metadata_units", 1)
            with self._transaction():
                self._capture(proof.capture)
                self._object(proof.target)
                self._object(proof.note)
                self._insert("note_roles", proof.key)
                self._insert(
                    "retained_notes",
                    (
                        *native.oid.key,
                        physical_copy_uuidv4,
                        native.body,
                        native.declared_size,
                        native.digest_sha256,
                        *proof.capture.pair,
                        proof.capture.root.full_oid,
                        proof.target.full_oid,
                        proof.path,
                        proof.bundle,
                    ),
                )
                if before_commit is not None:
                    before_commit()

    @_completed_read
    @_decoded_read
    def scalar(self, oid: OID, field: ScalarField) -> Projection:
        rows = self.sql(
            "SELECT c.*, EXISTS(SELECT 1 FROM intrinsic_claims i WHERE i.object_format=c.object_format AND i.full_oid=c.full_oid AND i.field=c.field AND i.value=c.value AND i.provenance=c.provenance) checked FROM scalar_claims c WHERE object_format=? AND full_oid=? AND field=?",
            (*oid.key, field),
        )

        def decode_claim(row):
            value = json.loads(row["value"])
            original = None if value == ["unknown"] else value[1]
            if claim_value(field, original) != row["value"]:
                raise ValueError("invalid stored scalar claim")
            provenance = self._provenance_value((oid, field), row["provenance"])
            if row["checked"] and provenance.qualification != "receiver_intrinsic":
                raise ValueError("reported assertion has invalid intrinsic link")
            return value

        alternatives = tuple(
            {
                "value": self._stored((oid, field), decode_claim, r),
                "provenance": json.loads(r["provenance"]),
                "checked": bool(r["checked"]),
            }
            for r in rows
        )
        checked = {encode(a["value"]) for a in alternatives if a["checked"]}
        reports = {encode(a["value"]) for a in alternatives if a["value"][0] == "known"}
        return Projection(
            json.loads(next(iter(checked))) if len(checked) == 1 else None,
            alternatives,
            len(reports) > 1,
            f"native-{field}" if checked else None,
        )

    @_completed_read
    @_decoded_read
    def relations(
        self, oid: OID, relation: str, scope: str | None = None
    ) -> Projection:
        rows = self.sql(
            "SELECT g.*, EXISTS(SELECT 1 FROM intrinsic_groups i WHERE i.object_format=g.object_format AND i.full_oid=g.full_oid AND i.relation=g.relation AND i.scope=g.scope AND i.status=g.status AND i.membership=g.membership AND i.provenance=g.provenance) checked FROM relation_groups g WHERE object_format=? AND full_oid=? AND relation=?",
            (*oid.key, relation),
        )

        def decode_group(row):
            if not row["scope"] or not valid_group(
                oid.object_format, row["relation"], row["status"], row["membership"]
            ):
                raise ValueError("invalid stored relation group")
            provenance = self._provenance_value((oid, relation), row["provenance"])
            if row["checked"] and provenance.qualification != "receiver_intrinsic":
                raise ValueError("reported group has invalid intrinsic link")
            return json.loads(row["membership"])

        alternatives = tuple(
            {
                "status": r["status"],
                "membership": self._stored((oid, relation), decode_group, r),
                "scope": r["scope"],
                "provenance": json.loads(r["provenance"]),
                "checked": bool(r["checked"]),
            }
            for r in rows
            if scope is None or r["scope"] == scope
        )
        checked = {
            encode([a["status"], a["membership"]]) for a in alternatives if a["checked"]
        }

        def slot(member):
            coordinate = member[0]
            if relation == "tree_entries":
                return coordinate[1]  # Raw name is the logical slot; mode is a value.
            return coordinate

        def asserted(member):
            coordinate, fmt, target = member
            return (
                (coordinate[0], fmt, target)
                if relation == "tree_entries"
                else (fmt, target)
            )

        slots = {}
        closed_values = {}
        conflict = False
        for alternative in alternatives:
            group_scope = alternative["scope"]
            for member in alternative["membership"]:
                logical = slot(member)
                if logical is not None:
                    # Positive claims identify the same intrinsic slot even
                    # when independent observations cover different fragments.
                    # Scope restricts negative closure below, not a real ordinal
                    # or raw name that both observations explicitly supplied.
                    slots.setdefault(encode(logical), set()).add(asserted(member))
            if alternative["status"] in ("complete", "known_empty"):
                normalized = sorted(
                    (encode(slot(m)), asserted(m)) for m in alternative["membership"]
                )
                closed_values.setdefault(group_scope, set()).add(encode(normalized))
        conflict |= any(len(values) > 1 for values in slots.values())
        conflict |= any(len(values) > 1 for values in closed_values.values())
        for closed_group in alternatives:
            if closed_group["status"] not in ("complete", "known_empty"):
                continue
            closed_slots = {encode(slot(m)) for m in closed_group["membership"]}
            closed_targets = {(m[1], m[2]) for m in closed_group["membership"]}
            for other in alternatives:
                # Locally checked native groups enumerate the whole intrinsic
                # relation, so their exclusions apply to every observation.
                # Reported bounded scopes retain only their own negative scope.
                if (
                    not closed_group["checked"]
                    and other["scope"] != closed_group["scope"]
                ):
                    continue
                for member in other["membership"]:
                    logical = slot(member)
                    if (
                        logical is not None and encode(logical) not in closed_slots
                    ) or (
                        logical is None and (member[1], member[2]) not in closed_targets
                    ):
                        conflict = True
        return Projection(
            json.loads(next(iter(checked))) if len(checked) == 1 else None,
            alternatives,
            conflict,
            relation if checked else None,
        )

    def admit_coverage_scope(self, scope: CoreCoverageScope) -> None:
        values = dict(
            repository_uuidv4=None,
            capture_origin_uuidv4=None,
            capture_uuidv4=None,
            observation_origin_uuidv4=None,
            ref_observation_uuidv7=None,
            object_format=None,
            full_oid=None,
            field=None,
        )
        names = {
            "repository": ("repository_uuidv4",),
            "capture": ("capture_origin_uuidv4", "capture_uuidv4"),
            "ref_observation": ("observation_origin_uuidv4", "ref_observation_uuidv7"),
            "object": ("object_format", "full_oid"),
            "field": ("object_format", "full_oid", "field"),
        }
        values.update(zip(names[scope.owner_kind], scope.coordinates[:-1], strict=True))
        with self._transaction():
            self._insert(
                "coverage_scopes",
                (
                    scope.owner_kind,
                    scope.encoded,
                    *values.values(),
                    scope.coordinates[-1],
                ),
            )

    def admit_coverage(self, claim: CoverageClaim) -> str:
        scope = claim.scope
        with self._transaction():
            newest = self._db.execute(
                "SELECT max(observed_at_us) FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=?",
                (scope.owner_kind, scope.encoded),
            ).fetchone()[0]
            if newest is not None and newest > claim.observed_at_us:
                return "stale"
            exists = self._db.execute(
                "SELECT 1 FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state=?",
                (scope.owner_kind, scope.encoded, claim.observed_at_us, claim.state),
            ).fetchone()
            if exists:
                return "duplicate"
            self._insert(
                "coverage_claims",
                (
                    scope.owner_kind,
                    scope.encoded,
                    claim.observed_at_us,
                    claim.state,
                    claim.details_json,
                ),
            )
            return "insert"

    def _ref_coverage_group_key(self, group, work, max_bytes):
        """Encode the exact reported group after charging all variable input."""
        if len(group.members) > 100_000:
            raise CoreFailure("BUDGET", "ref-coverage", "finite member limit")
        values = (
            *group.ref_claim.provenance.key,
            *group.provenance.key,
            group.interpretation_kind,
            group.interpretation_version,
            group.interpretation_scope,
            group.group_scope,
            group.status,
        )
        self._meter_input_metadata(work, values, max_bytes)
        upper = 2
        for member in group.members:
            self._charge(work, "metadata_units", 1)
            upper += 16 + sum(
                4 if value is None else 12 * len(value) for value in member
            )
            if upper > max_bytes:
                raise CoreFailure("BUDGET", "ref-coverage", "finite membership limit")
        work.require("input_bytes", upper)
        try:
            membership = encode(group.members)
            if len(membership) > upper:
                raise CoreFailure(
                    "BUDGET", "ref-coverage", "membership reservation exceeded"
                )
        except BaseException:
            abandon = getattr(work, "abandon", None)
            if abandon:
                abandon("input_bytes")
            else:
                work.charge("input_bytes", upper)
            raise
        work.charge("input_bytes", len(membership))
        self._meter_provenance_encoding(work, group.ref_claim.provenance, max_bytes)
        self._meter_provenance_encoding(work, group.provenance, max_bytes)
        return (
            *group.ref_claim.identity,
            *group.ref_claim.root_oid.key,
            group.interpretation_kind,
            group.interpretation_version,
            group.interpretation_scope,
            group.group_scope,
            group.status,
            membership,
            group.provenance.encoded,
        )

    def _read_ref_coverage_proofs(
        self, claim, work, *, max_proofs, max_bytes, max_structures=100_000
    ):
        """Validate stored proof rows within the caller's snapshot or writer cut."""
        if (
            not isinstance(claim, CoverageClaim)
            or not isinstance(claim.scope, CoreCoverageScope)
            or claim.scope.owner_kind != "ref_observation"
            or claim.scope.coordinates[-1] != REF_NOTES_INVENTORY
            or claim.state != "complete"
        ):
            raise CoreFailure(
                "REF_COVERAGE_PROOF", "scope", "typed inventory scope required"
            )
        if (
            type(max_proofs) is not int
            or not 0 < max_proofs < 2**63 - 1
            or type(max_bytes) is not int
            or not 0 < max_bytes < 2**63
            or type(max_structures) is not int
            or not 0 < max_structures < 2**63
        ):
            raise CoreFailure(
                "QUERY_BUDGET", "ref-coverage", "positive finite limits required"
            )
        scope = claim.scope
        key = (scope.owner_kind, scope.encoded, claim.observed_at_us, claim.state)
        columns = (
            "owner_kind",
            "owner_coordinates_json",
            "coverage_state",
            "observation_origin_uuidv4",
            "ref_observation_uuidv7",
            "ref_claim_provenance",
            "object_format",
            "root_oid",
            "interpretation_kind",
            "interpretation_version",
            "interpretation_scope",
            "group_scope",
            "group_status",
            "group_membership",
            "group_provenance",
            "verification_provenance",
            "structures_json",
        )
        size = "+".join(f"coalesce(octet_length({column}),0)" for column in columns)
        where = "owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state=?"
        work.require("metadata_units", max_proofs + 1)
        try:
            sizes = self._ref_note_many(
                f"SELECT {size} FROM ref_coverage_proofs WHERE {where} LIMIT ?",
                (*key, max_proofs + 1),
            )
        except BaseException:
            abandon = getattr(work, "abandon", None)
            if abandon:
                abandon("metadata_units")
            else:
                work.charge("metadata_units", max_proofs + 1)
            raise
        work.charge("metadata_units", len(sizes))
        total = sum(row[0] for row in sizes)
        if len(sizes) > max_proofs or total > max_bytes:
            raise CoreFailure("QUERY_BUDGET", scope, "finite proof projection limit")
        work.require("input_bytes", total)
        try:
            rows = self._ref_note_many(
                f"SELECT * FROM ref_coverage_proofs WHERE {where} ORDER BY verification_provenance LIMIT ?",
                (*key, max_proofs + 1),
            )
        except BaseException:
            abandon = getattr(work, "abandon", None)
            if abandon:
                abandon("input_bytes")
            else:
                work.charge("input_bytes", total)
            raise
        work.charge("input_bytes", total)
        if len(rows) != len(sizes):
            self._integrity_stop((scope, "disappeared-ref-coverage-proof"))
        if rows:
            self._charge(work, "metadata_units", 1)
            if not self._ref_note_one(
                "SELECT 1 FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state=?",
                key,
            ):
                self._integrity_stop((scope, "missing-ref-coverage-claim-parent"))
        result = []
        for row in rows:
            identity = (
                row["observation_origin_uuidv4"],
                row["ref_observation_uuidv7"],
                row["ref_claim_provenance"],
            )
            stored_claim = self._bounded_stored_row(
                "ref_observation_claims",
                identity,
                work,
                max_bytes,
                metadata_limit_code="QUERY_BUDGET",
            )
            if stored_claim is None:
                self._integrity_stop((scope, "missing-ref-coverage-claim"))
            ref_claim = self._stored(
                scope,
                lambda value: self._decode_ref_claim(
                    value,
                    work=work,
                    max_metadata_bytes=max_bytes,
                    metadata_limit_code="QUERY_BUDGET",
                ),
                stored_claim,
            )
            try:
                self._require_ref_claim(
                    ref_claim,
                    work=work,
                    max_metadata_bytes=max_bytes,
                    metadata_limit_code="QUERY_BUDGET",
                )
            except CoreFailure as error:
                if error.code in ("MISSING_DEPENDENCY", "INCOMPATIBLE_REPLAY"):
                    self._integrity_stop((scope, "invalid-ref-coverage-claim"))
                raise

            membership = row["group_membership"]
            self._charge(work, "input_bytes", 3 * len(membership))
            upper = max(1, len(membership))
            work.require("metadata_units", upper)
            try:

                def decode_group():
                    return NotesMappingGroup(
                        ref_claim,
                        row["interpretation_kind"],
                        row["interpretation_version"],
                        row["interpretation_scope"],
                        row["group_scope"],
                        row["group_status"],
                        tuple(tuple(item) for item in json.loads(membership)),
                        Provenance(*json.loads(row["group_provenance"])),
                    )

                group = self._stored(scope, decode_group)
            except BaseException:
                abandon = getattr(work, "abandon", None)
                if abandon:
                    abandon("metadata_units")
                else:
                    work.charge("metadata_units", upper)
                raise
            work.charge("metadata_units", 1 + 3 * len(group.members))
            group_key = self._ref_coverage_group_key(group, work, max_bytes)
            if tuple(row)[4:16] != group_key:
                self._integrity_stop((scope, "invalid-ref-coverage-group-key"))
            self._charge(work, "metadata_units", 1)
            self._charge(work, "input_bytes", len(group_key[-2]))
            if not self._ref_note_one(
                "SELECT 1 FROM notes_mapping_groups WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND group_scope=? AND status=? AND membership=? AND provenance=?",
                group_key,
            ):
                self._integrity_stop((scope, "missing-ref-coverage-group"))
            for target, note, _path in group.members:
                for value in (target, note):
                    self._charge(work, "metadata_units", 1)
                    if not self._ref_note_one(
                        "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                        (group.ref_claim.root_oid.object_format, value),
                    ):
                        self._integrity_stop((scope, "missing-ref-coverage-member"))
            provenance = self._provenance_value(
                scope,
                row["verification_provenance"],
                work=work,
                max_metadata_bytes=max_bytes,
            )
            structures = self._stored(
                scope,
                lambda value: deserialize_structures(
                    value, work, max_structures=max_structures, max_bytes=max_bytes
                ),
                row["structures_json"],
            )
            proof = self._stored(
                scope,
                RefNotesInventoryCoverageProof,
                claim,
                group,
                provenance,
                structures,
            )
            self._stored(
                scope,
                lambda: verify_ref_notes_inventory(
                    proof, work, max_structures=max_structures, max_bytes=max_bytes
                ),
            )
            result.append(proof)
        return tuple(result)

    @_completed_read
    @_decoded_read
    def ref_coverage_proofs(
        self,
        claim,
        work: WorkBudget,
        *,
        max_proofs=1_000,
        max_bytes=64 * 1024 * 1024,
        max_structures=100_000,
    ):
        with self._snapshot():
            return self._read_ref_coverage_proofs(
                claim,
                work,
                max_proofs=max_proofs,
                max_bytes=max_bytes,
                max_structures=max_structures,
            )

    def admit_ref_coverage_proof(
        self,
        proof: RefNotesInventoryCoverageProof,
        work: WorkBudget,
        *,
        max_structures=100_000,
        max_bytes=64 * 1024 * 1024,
    ) -> None:
        """Admit one locally rechecked complete inventory and its exact source group."""
        if not isinstance(proof, RefNotesInventoryCoverageProof):
            raise CoreFailure(
                "REF_COVERAGE_PROOF", "notes-inventory", "typed proof required"
            )
        self._available()
        group_key = self._ref_coverage_group_key(proof.group, work, max_bytes)
        self._meter_input_metadata(work, proof.verification_provenance.key, max_bytes)
        self._meter_provenance_encoding(work, proof.verification_provenance, max_bytes)
        bundle = verify_ref_notes_inventory(
            proof, work, max_structures=max_structures, max_bytes=max_bytes
        )
        claim, group = proof.coverage_claim, proof.group
        scope = claim.scope
        values = (
            scope.owner_kind,
            scope.encoded,
            claim.observed_at_us,
            claim.state,
            *group_key,
            proof.verification_provenance.encoded,
            bundle,
        )
        provenance_coordinate = proof.verification_provenance.key[:3]
        with self._transaction():
            self._charge(work, "metadata_units", 1)
            existing = self._db.execute(
                "SELECT observed_at_us,coverage_state FROM ref_coverage_proofs WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND json_extract(verification_provenance,'$[0]')=? AND json_extract(verification_provenance,'$[1]')=? AND json_extract(verification_provenance,'$[2]')=?",
                (*group_key[:3], *provenance_coordinate),
            ).fetchone()
            if existing:
                prior_claim = CoverageClaim(scope, existing[0], existing[1])
                prior = self._read_ref_coverage_proofs(
                    prior_claim,
                    work,
                    max_proofs=1_000,
                    max_bytes=max_bytes,
                    max_structures=max_structures,
                )
                self._charge(work, "metadata_units", len(prior))
                candidates = [
                    p
                    for p in prior
                    if p.verification_provenance.key[:3] == provenance_coordinate
                ]
                if len(candidates) != 1:
                    self._integrity_stop((scope, "missing-verification-coordinate"))
                old = candidates[0]
                self._charge(
                    work, "metadata_units", len(old.group.members) + len(group.members)
                )
                self._charge(work, "input_bytes", len(bundle) + len(group_key[-2]))
                if (
                    old.coverage_claim.observed_at_us != claim.observed_at_us
                    or old.group != group
                    or old.verification_provenance != proof.verification_provenance
                    or old.structures != proof.structures
                ):
                    raise CoreFailure(
                        "INCOMPATIBLE_REPLAY",
                        scope,
                        "verification coordinate cannot be rebound",
                    )
                return
            self._require_ref_claim(
                group.ref_claim, work=work, max_metadata_bytes=max_bytes
            )
            self._charge(work, "metadata_units", 1)
            self._charge(work, "input_bytes", len(group_key[-2]))
            if not self._db.execute(
                "SELECT 1 FROM notes_mapping_groups WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND group_scope=? AND status=? AND membership=? AND provenance=?",
                group_key,
            ).fetchone():
                raise CoreFailure(
                    "MISSING_DEPENDENCY", scope, "exact reported group required"
                )
            self._charge(work, "metadata_units", 1 + len(group.members))
            self._charge(
                work,
                "input_bytes",
                2 * len(bundle)
                + 2 * len(group_key[-2])
                + len(group_key[-1])
                + len(values[-2]),
            )
            self._insert("ref_coverage_proofs", values)

    def admit_coverage_proof(
        self, claim: CoverageClaim, members: tuple[OID, ...], provenance: Provenance
    ) -> None:
        self._reported(provenance)
        if claim.scope.owner_kind == "ref_observation":
            raise CoreFailure(
                "UNSUPPORTED_REF_COVERAGE_PROOF",
                claim.scope,
                "ref-observation Coverage proof requires I2 typed evidence",
            )
        with self._transaction():
            for member in members:
                self._object(member)
            self._insert(
                "core_coverage_proofs",
                (
                    claim.scope.owner_kind,
                    claim.scope.encoded,
                    claim.observed_at_us,
                    claim.state,
                    encode([m.key for m in members]),
                    provenance.encoded,
                ),
            )

    def _ref_coverage_candidates(self, scope, work, max_bytes):
        """Reserve every latest candidate's variable bytes before materialization."""
        self._meter_input_metadata(
            work, scope.coordinates, max_bytes, limit_code="QUERY_BUDGET"
        )
        self._charge(
            work, "input_bytes", sum(len(value) for value in scope.coordinates)
        )
        encoded_size = (
            2
            + len(scope.coordinates)
            - 1
            + sum(self._json_string_bytes(value) for value in scope.coordinates)
        )
        if encoded_size > max_bytes:
            raise CoreFailure("QUERY_BUDGET", scope, "finite Coverage scope limit")
        self._charge(work, "input_bytes", encoded_size)
        encoded_scope = scope.encoded
        if len(encoded_scope) != encoded_size:
            raise CoreFailure("QUERY_BUDGET", scope, "Coverage scope encoding mismatch")
        coordinates = (scope.owner_kind, encoded_scope, scope.owner_kind, encoded_scope)
        where = "owner_kind=? AND owner_coordinates_json=? AND observed_at_us=(SELECT max(observed_at_us) FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=?)"
        work.require("metadata_units", 5)
        try:
            sizes = self.sql(
                "SELECT octet_length(coverage_state),coalesce(octet_length(details_json),0) FROM coverage_claims WHERE "
                + where
                + " ORDER BY coverage_state LIMIT 5",
                coordinates,
            )
        except BaseException:
            abandon = getattr(work, "abandon", None)
            if abandon:
                abandon("metadata_units")
            else:
                work.charge("metadata_units", 5)
            raise
        work.charge("metadata_units", len(sizes))
        if len(sizes) > 4:
            self._integrity_stop((scope, "invalid-ref-coverage-candidate-count"))
        if any(type(value) is not int or value < 0 for row in sizes for value in row):
            self._integrity_stop((scope, "invalid-ref-coverage-candidate-size"))
        total = sum(row[0] + row[1] for row in sizes)
        if total > max_bytes:
            raise CoreFailure(
                "QUERY_BUDGET", scope, "finite Coverage candidate byte limit"
            )
        self._charge(work, "input_bytes", total)
        rows = self.sql(
            "SELECT observed_at_us,coverage_state,details_json FROM coverage_claims WHERE "
            + where
            + " ORDER BY coverage_state LIMIT 5",
            coordinates,
        )
        if len(rows) != len(sizes):
            self._integrity_stop((scope, "disappeared-ref-coverage-claim"))
        claims = []
        for row in rows:
            self._charge(work, "metadata_units", 1)
            if type(row[1]) is not str or (
                row[2] is not None and type(row[2]) is not str
            ):
                self._integrity_stop((scope, "invalid-ref-coverage-claim-type"))
            self._charge(work, "input_bytes", len(row[1]) + 2 * len(row[2] or ""))
            claims.append(
                self._stored(scope, CoverageClaim, scope, row[0], row[1], row[2])
            )
        return encoded_scope, rows, tuple(claims)

    @_completed_read
    @_decoded_read
    def coverage(
        self,
        scope: CoreCoverageScope,
        work: WorkBudget | None = None,
        *,
        max_proofs: int = 1_000,
        max_bytes: int = 64 * 1024 * 1024,
        max_structures: int = 100_000,
        max_claims: int = 10_000,
    ) -> CoverageProjection:
        with self._snapshot():
            ref_work = work
            if scope.owner_kind == "ref_observation":
                if ref_work is None:
                    ref_work = LocalRefCoverageWork(max_bytes)
                encoded_scope, rows, claims = self._ref_coverage_candidates(
                    scope, ref_work, max_bytes
                )
            else:
                encoded_scope = scope.encoded
                rows = self.sql(
                    "SELECT observed_at_us,coverage_state,details_json FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=(SELECT max(observed_at_us) FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=?) ORDER BY coverage_state",
                    (scope.owner_kind, encoded_scope, scope.owner_kind, encoded_scope),
                )
                claims = tuple(
                    self._stored(scope, CoverageClaim, scope, row[0], row[1], row[2])
                    for row in rows
                )
            state = derive_coverage_state(claim.state for claim in claims)
            if scope.owner_kind == "ref_observation":
                known_empty = False
                if rows and state == "complete":
                    self._charge(ref_work, "metadata_units", 1)
                    generic = self.sql(
                        "SELECT 1 FROM core_coverage_proofs WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? LIMIT 1",
                        (scope.owner_kind, encoded_scope, rows[0][0]),
                    )
                    if generic:
                        self._integrity_stop((scope, "unsupported-ref-coverage-proof"))
                    self._charge(ref_work, "metadata_units", 1)
                    has_typed = self.sql(
                        "SELECT 1 FROM ref_coverage_proofs WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state='complete' LIMIT 1",
                        (scope.owner_kind, encoded_scope, rows[0][0]),
                    )
                    if not has_typed:
                        state = "unknown"
                    elif work is None:
                        raise CoreFailure(
                            "QUERY_BUDGET",
                            scope,
                            "typed ref Coverage needs a finite work budget",
                        )
                    else:
                        complete_claim = next(
                            value for value in claims if value.state == "complete"
                        )
                        verified = self._read_ref_coverage_proofs(
                            complete_claim,
                            work,
                            max_proofs=max_proofs,
                            max_bytes=max_bytes,
                            max_structures=max_structures,
                        )
                        observed = self.ref_observation(
                            RefObservationKey(*scope.coordinates[:2]),
                            work,
                            max_claims=max_claims,
                            max_bytes=max_bytes,
                        )
                        self._charge(work, "metadata_units", len(verified))
                        self._charge(
                            work,
                            "metadata_units",
                            sum(1 + len(value.group.members) for value in verified),
                        )
                        self._charge(
                            work,
                            "input_bytes",
                            sum(
                                len(part)
                                for value in verified
                                for member in value.group.members
                                for part in member
                                if isinstance(part, str)
                            ),
                        )
                        alternatives = {
                            (value.group.ref_claim.root_oid, value.group.members)
                            for value in verified
                        }
                        if observed.conflict or len(alternatives) > 1:
                            state = "conflict"
                        else:
                            known_empty = bool(verified) and all(
                                value.group.status == "known_empty"
                                for value in verified
                            )
                return CoverageProjection(
                    state, rows[0][0] if rows else None, claims, known_empty
                )
            proofs = (
                self.sql(
                    "SELECT members_json FROM core_coverage_proofs WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state='complete'",
                    (scope.owner_kind, scope.encoded, rows[0][0]),
                )
                if rows and state == "complete"
                else []
            )
            if any(not valid_coverage_members(row[0]) for row in proofs):
                self._integrity_stop((scope, "invalid-stored-coverage-proof"))
            if state == "complete" and not proofs:
                state = "unknown"
            return CoverageProjection(
                state,
                rows[0][0] if rows else None,
                claims,
                bool(proofs) and all(row[0] == "[]" for row in proofs),
            )

    def _integrity_stop(self, scope: object) -> None:
        self._stopped = True
        failure = CoreFailure(
            "AUTHORITATIVE_CORRUPTION",
            scope,
            "authoritative integrity failure; stop catalog and restore fresh",
        )
        if self._directory is not None:
            from repo_catalog.adapters.sqlite.p1_coordination import (
                persist_catalog_stop,
            )

            persist_catalog_stop(self._directory, str(failure))
        if self._on_corruption is not None:
            self._on_corruption(failure)
        raise failure

    @_completed_read
    @_decoded_read
    def read_metadata(self, oid: OID) -> bytes:
        rows = self.sql(
            "SELECT * FROM retained_metadata WHERE object_format=? AND full_oid=? ORDER BY physical_copy_uuidv4",
            oid.key,
        )
        if not rows:
            raise CoreFailure(
                "BYTES_UNAVAILABLE",
                oid,
                "metadata-only identity has no retained representation",
            )
        row = rows[0]
        if not valid_native(
            *oid.key, row["native_type"], row["body"], row["size"], row["digest_sha256"]
        ):
            self._integrity_stop((oid, row["physical_copy_uuidv4"]))
        from repo_catalog.domain.git_native import parse_metadata

        try:
            parse_metadata(oid.object_format, row["native_type"], row["body"])
        except (ValueError, TypeError):
            self._integrity_stop((oid, row["physical_copy_uuidv4"], "native-syntax"))
        return row["body"]

    @_completed_read
    @_decoded_read
    def notes_projection(self, capture: Capture, target: OID) -> NotesProjection:
        """Metadata-only alternatives and precisely relevant checked mapping.

        Proven roles prefer only Capture+target association, never provenance,
        ref freshness, completeness of groups, target bytes or body availability.
        All genuine reports/groups remain available and conflicts stay explicit.
        """
        if target.object_format != capture.root.object_format:
            raise CoreFailure(
                "NOTES_SCOPE", (capture.pair, target), "Capture object-format mismatch"
            )
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
            alternatives = []
            positive = set()
            claims = self.sql(
                "SELECT note,provenance FROM notes_claims WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? AND target=?",
                (*capture.pair, target.object_format, target.full_oid),
            )
            for row in claims:
                note = self._stored(
                    (capture.pair, target), OID, target.object_format, row[0]
                )
                positive.add(note)
                alternatives.append(
                    NotesAlternative(
                        "claim",
                        capture.pair,
                        target,
                        note,
                        None,
                        None,
                        (),
                        self._provenance_value((capture.pair, target), row[1]),
                        None,
                        False,
                    )
                )
            absent_closed = False
            groups = self.sql(
                "SELECT scope,status,membership,provenance FROM notes_groups WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=?",
                (*capture.pair, target.object_format),
            )
            for row in groups:
                if not row[0] or not _notes_group(target.object_format, row[1], row[2]):
                    self._integrity_stop(
                        (capture.pair, target, "invalid-stored-notes-group")
                    )
                members = tuple(tuple(m) for m in json.loads(row[2]))
                relevant = [m for m in members if m[0] == target.full_oid]
                # Groups preserve their asserted scope; complete/empty excludes
                # unlisted targets only when explicitly scoped to all mappings.
                applicable = row[0] == "all-notes-mappings" or row[0] == encode(
                    ["target", target.full_oid]
                )
                if not relevant and not applicable:
                    continue
                for member in relevant:
                    positive.add(OID(target.object_format, member[1]))
                absent_closed |= (
                    applicable
                    and row[1] in ("complete", "known_empty")
                    and not relevant
                )
                alternatives.append(
                    NotesAlternative(
                        "group",
                        capture.pair,
                        target,
                        OID(target.object_format, relevant[0][1]) if relevant else None,
                        row[0],
                        row[1],
                        members,
                        self._provenance_value((capture.pair, target), row[3]),
                        relevant[0][2] if relevant else None,
                        False,
                    )
                )
            checked = set()
            roles = self.sql(
                "SELECT root,note,path,proof_bundle FROM note_roles WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? AND target=?",
                (*capture.pair, target.object_format, target.full_oid),
            )
            for row in roles:
                if not valid_note_role(
                    target.object_format,
                    row[0],
                    target.full_oid,
                    row[1],
                    row[2],
                    row[3],
                ):
                    self._integrity_stop((capture.pair, target, "notes-role"))
                note = OID(target.object_format, row[1])
                checked.add(note)
                alternatives.append(
                    NotesAlternative(
                        "receiver_role",
                        capture.pair,
                        target,
                        note,
                        "relevant-root-to-target-mapping",
                        None,
                        (),
                        None,
                        row[2],
                        True,
                    )
                )
            return NotesProjection(
                capture,
                target,
                next(iter(checked)) if len(checked) == 1 else None,
                tuple(alternatives),
                len(positive | checked) > 1
                or (absent_closed and bool(positive | checked)),
                "relevant-root-to-target-mapping" if checked else None,
            )

    @_completed_read
    @_decoded_read
    def read_note(self, capture: Capture, target: OID, note: OID) -> bytes:
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
                "SELECT n.*,r.root AS requested_root,r.path AS requested_path,r.proof_bundle AS requested_proof FROM retained_notes n JOIN note_roles r ON r.object_format=n.object_format AND r.note=n.full_oid WHERE r.capture_origin_uuidv4=? AND r.capture_uuidv4=? AND r.object_format=? AND r.target=? AND r.note=? ORDER BY n.physical_copy_uuidv4",
                (*capture.pair, target.object_format, target.full_oid, note.full_oid),
            )
            if not rows:
                raise CoreFailure(
                    "NOTES_ROLE_UNAVAILABLE",
                    (capture.pair, target, note),
                    "no receiver-proven note role/body for requested scope",
                )
            row = rows[0]
            if not valid_note_role(
                target.object_format,
                row["requested_root"],
                target.full_oid,
                note.full_oid,
                row["requested_path"],
                row["requested_proof"],
            ) or not valid_native(
                *note.key, "blob", row["body"], row["size"], row["digest_sha256"]
            ):
                self._integrity_stop((note, row["physical_copy_uuidv4"]))
            return row["body"]


def validate_embedded_references(db) -> None:
    """Revalidate semantic embedded FKs for backup/read certification.

    SQLite integrity_check does not execute INSERT triggers on existing rows.
    Embedded whole-value keys must therefore be shape- and referent-checked
    alongside ordinary composite FKs, including after untrusted restoration.
    """
    from repo_catalog.domain.p1_core import (
        _notes_group,
        valid_coverage_members,
        valid_group,
    )

    def nominal(fmt, oid):
        return (
            db.execute(
                "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                (fmt, oid),
            ).fetchone()
            is not None
        )

    for fmt, relation, status, membership in db.execute(
        "SELECT object_format,relation,status,membership FROM relation_groups"
    ):
        if not valid_group(fmt, relation, status, membership) or any(
            not nominal(member[1], member[2]) for member in json.loads(membership)
        ):
            raise CoreFailure(
                "AUTHORITATIVE_CORRUPTION",
                "relation_groups",
                "invalid embedded relation reference",
            )
    for fmt, status, membership in db.execute(
        "SELECT object_format,status,membership FROM notes_groups UNION ALL "
        "SELECT object_format,status,membership FROM notes_mapping_groups"
    ):
        if not _notes_group(fmt, status, membership) or any(
            not nominal(fmt, member[0]) or not nominal(fmt, member[1])
            for member in json.loads(membership)
        ):
            raise CoreFailure(
                "AUTHORITATIVE_CORRUPTION",
                "notes_groups",
                "invalid embedded notes reference",
            )
    for evidence, source, visibility, ref_name in db.execute(
        "SELECT c.absence_evidence,o.source_attribution,o.visibility_scope,o.ref_name_bytes "
        "FROM ref_observation_claims c JOIN ref_observations o "
        "USING(observation_origin_uuidv4,ref_observation_uuidv7) "
        "WHERE c.presence_state='absent'"
    ):
        try:
            absence = RefAbsenceEvidence.decode(evidence)
            if (
                absence.source_attribution,
                absence.visibility_scope,
                absence.ref_name_bytes,
            ) != (source, visibility, ref_name):
                raise ValueError("absence subject mismatch")
        except (ValueError, TypeError) as error:
            raise CoreFailure(
                "AUTHORITATIVE_CORRUPTION",
                "ref_observation_claims",
                "invalid scoped absence evidence",
            ) from error
    if db.execute(
        "SELECT 1 FROM core_coverage_proofs WHERE owner_kind='ref_observation' LIMIT 1"
    ).fetchone():
        raise CoreFailure(
            "AUTHORITATIVE_CORRUPTION",
            "core_coverage_proofs",
            "unsupported ref-observation Coverage proof",
        )
    for row in db.execute("SELECT members_json FROM core_coverage_proofs"):
        membership = row[0]
        if not valid_coverage_members(membership) or any(
            not nominal(*member) for member in json.loads(membership)
        ):
            raise CoreFailure(
                "AUTHORITATIVE_CORRUPTION",
                "core_coverage_proofs",
                "invalid embedded Coverage reference",
            )
