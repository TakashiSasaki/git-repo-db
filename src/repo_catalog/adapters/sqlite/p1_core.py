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
from repo_catalog.domain.ref_observation import (
    NotesMapping,
    NotesMappingClaim,
    NotesMappingEvidence,
    NotesMappingEvidenceRecord,
    NotesMappingGroup,
    NotesMappingProjection,
    RefAbsenceEvidence,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
    RefObservationProjection,
    ref_claim_conflict,
)


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
        except (ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
            self._integrity_stop((scope, "invalid-stored-value", str(error)))

    def _provenance_value(self, scope, encoded):
        def decode(value):
            result = Provenance(*json.loads(value))
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

    def _validate_ref_subject_dependency(self, key: RefObservationKey) -> None:
        row = self._db.execute(
            "SELECT * FROM ref_observations WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=?",
            key.key,
        ).fetchone()
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

    def _require_ref_claim(self, claim: RefObservationClaim) -> None:
        """Never bind new evidence to a changed or absent result Claim."""
        row = self._db.execute(
            "SELECT * FROM ref_observation_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND provenance=?",
            claim.identity,
        ).fetchone()
        if row is None:
            raise CoreFailure(
                "MISSING_DEPENDENCY",
                claim.identity,
                "original result claim is required",
            )
        if tuple(row) != claim.key:
            raise CoreFailure(
                "INCOMPATIBLE_REPLAY",
                claim.identity,
                "original result claim cannot be rebound",
            )
        self._validate_ref_subject_dependency(claim.ref_observation_key)
        for oid in (
            claim.direct_target_oid,
            claim.resolved_target_oid,
            claim.peeled_target_oid,
            claim.root_oid,
        ):
            if (
                oid is not None
                and not self._db.execute(
                    "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                    oid.key,
                ).fetchone()
            ):
                self._integrity_stop((claim.identity, "missing-claim-object", oid.key))

    @staticmethod
    def _decode_ref_claim(row) -> RefObservationClaim:
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
            else RefAbsenceEvidence.decode(row["absence_evidence"]),
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
                subject_size = self.sql(
                    "SELECT length(ref_name_bytes)+length(CAST(source_attribution AS BLOB))+"
                    "length(CAST(visibility_scope AS BLOB))+length(repository_uuidv4)+"
                    "length(observation_origin_uuidv4)+length(ref_observation_uuidv7) "
                    "FROM ref_observations WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=?",
                    key.key,
                )
                claim_sizes = self.sql(
                    "SELECT length(CAST(provenance AS BLOB))+"
                    "coalesce(length(symbolic_target_ref_name),0)+"
                    "coalesce(length(CAST(absence_evidence AS BLOB)),0)+"
                    "coalesce(length(direct_target_oid),0)+coalesce(length(resolved_target_oid),0)+"
                    "coalesce(length(peeled_target_oid),0)+coalesce(length(root_oid),0) "
                    "FROM ref_observation_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? LIMIT ?",
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
            self._validate_ref_subject_dependency(key)
            rows = self.sql(
                "SELECT * FROM ref_observation_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? ORDER BY provenance",
                key.key,
            )
            claims = tuple(
                self._stored(key, self._decode_ref_claim, row) for row in rows
            )
            for claim in claims:
                self._charge(work, "metadata_units", 1)
                self._require_ref_claim(claim)
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

    def admit_notes_mapping_claim(self, claim: NotesMappingClaim) -> None:
        if not isinstance(claim, NotesMappingClaim):
            raise CoreFailure("NOTES_MAPPING", claim, "typed mapping claim required")
        with self._transaction():
            self._require_ref_claim(claim.ref_claim)
            self._notes_mapping(claim.mapping)
            self._insert("notes_mapping_claims", claim.key)

    def admit_notes_mapping_group(self, group: NotesMappingGroup) -> None:
        if not isinstance(group, NotesMappingGroup):
            raise CoreFailure("NOTES_GROUP", group, "typed mapping group required")
        with self._transaction():
            self._require_ref_claim(group.ref_claim)
            existing = self._db.execute(
                "SELECT 1 FROM notes_mapping_groups WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND group_scope=? AND status=? AND membership=? AND provenance=?",
                group.key,
            ).fetchone()
            for target, note, _path in group.members:
                for value in (target, note):
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

    @staticmethod
    def _decode_mapping(row) -> NotesMapping:
        path = json.loads(row["mapping_path_json"])
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

    def _fetch_ref_note_copy(
        self, oid: OID, copy: str, work: WorkBudget, max_proof_bytes: int
    ):
        """Reserve the actual selected copy's bytes before materializing them."""
        self._charge(work, "metadata_units", 1)
        # SQLite's octet_length(column) reads the stored byte length from
        # metadata; casting a TEXT value to BLOB here would load its contents
        # before the input reservation. P1 already requires SQLite >= 3.51.3.
        lengths = self._ref_note_one(
            "SELECT octet_length(body) AS body_bytes,octet_length(proof_bundle) AS proof_bytes,size "
            "FROM ref_retained_notes WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
            (*oid.key, copy),
        )
        if lengths is None:
            return None
        body_bytes, proof_bytes, declared_size = tuple(lengths)
        if (
            type(body_bytes) is not int
            or type(proof_bytes) is not int
            or type(declared_size) is not int
            or body_bytes != declared_size
        ):
            self._integrity_stop((oid, copy, "stored-note-size"))
        if (
            type(work.limits.note_bytes) is not int
            or not 0 < work.limits.note_bytes < 2**63
            or type(max_proof_bytes) is not int
            or not 0 < max_proof_bytes < 2**63
            or body_bytes > work.limits.note_bytes
            or proof_bytes > max_proof_bytes
            or body_bytes + proof_bytes >= 2**63
        ):
            raise CoreFailure("BUDGET", (oid, copy), "finite note or proof limit")
        reserved = body_bytes + proof_bytes
        work.require("input_bytes", reserved)
        try:
            row = self._ref_note_one(
                "SELECT * FROM ref_retained_notes WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                (*oid.key, copy),
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
            self._integrity_stop((oid, copy, "disappeared-note-copy"))
        return row

    def _validate_stored_ref_note(self, row, work: WorkBudget):
        """Validate stored claim, root, mapping, role and body, not caller data."""
        scope = (row["object_format"], row["full_oid"], row["physical_copy_uuidv4"])
        self._stored(scope, uuid4_value, row["physical_copy_uuidv4"])
        identity = (
            row["observation_origin_uuidv4"],
            row["ref_observation_uuidv7"],
            row["ref_claim_provenance"],
        )
        self._charge(work, "metadata_units", 1)
        stored_claim = self._ref_note_one(
            "SELECT * FROM ref_observation_claims WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND provenance=?",
            identity,
        )
        if stored_claim is None:
            self._integrity_stop((scope, "missing-note-claim"))
        claim = self._stored(scope, self._decode_ref_claim, stored_claim)
        try:
            self._require_ref_claim(claim)
        except sqlite3.OperationalError as error:
            if str(error).startswith("Could not decode to UTF-8"):
                self._integrity_stop((scope, "stored-claim-or-subject-utf8"))
            raise
        mapping = self._stored(scope, self._decode_mapping, row)
        if (
            row["role_format"] != row["object_format"]
            or row["full_oid"] != row["note_oid"]
            or claim.root_oid != mapping.root_oid
        ):
            self._integrity_stop((scope, "note-claim-root"))
        self._charge(work, "metadata_units", 1)
        if not self._ref_note_one(
            "SELECT 1 FROM notes_mappings WHERE object_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? AND note_oid=? AND mapping_path_json=?",
            mapping.key,
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
            *mapping.key,
            row["verification_scope"],
            row["role_provenance"],
            row["proof_bundle"],
        )
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
            self._provenance_value(scope, row["role_provenance"]),
            row["proof_bundle"],
        )
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

    def _diagnose_ref_note_conflict(
        self,
        native: NativeObject,
        work: WorkBudget,
        max_proof_bytes: int,
        max_conflict_copies: int,
    ) -> None:
        """Check only an observed representation conflict, inside the writer cut.

        A valid colliding representation is an incompatible input, not proof of
        catalog damage. Each inspected copy is bounded and charged separately.
        """
        previous = ""
        for inspected in range(max_conflict_copies + 1):
            self._charge(work, "metadata_units", 1)
            candidate = self._ref_note_one(
                "SELECT physical_copy_uuidv4 FROM ref_retained_notes WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4>? ORDER BY physical_copy_uuidv4 LIMIT 1",
                (*native.oid.key, previous),
            )
            if candidate is None:
                return
            if inspected == max_conflict_copies:
                raise CoreFailure("BUDGET", native.oid, "note conflict copy limit")
            copy = self._stored(native.oid, uuid4_value, candidate[0])
            row = self._fetch_ref_note_copy(native.oid, copy, work, max_proof_bytes)
            if row is None:
                self._integrity_stop((native.oid, copy, "missing-conflict-copy"))
            _, _, body = self._validate_stored_ref_note(row, work)
            if body != native.body:
                return  # A checked collision remains an ordinary refusal.
            previous = copy

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
        coordinates = (
            *ref_claim.identity,
            *ref_claim.root_oid.key,
            interpretation_kind,
            interpretation_version,
            interpretation_scope,
        )
        with self._snapshot():
            self._require_ref_claim(ref_claim)
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
                    ("provenance", "membership", "group_scope"),
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
                        f"coalesce(length(CAST({column} AS BLOB)),0)"
                        for column in columns
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
                        self._decode_mapping(value),
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
                        self._decode_mapping(value),
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

    def _notes_mapping_evidence(self, evidence: NotesMappingEvidence) -> None:
        self._require_ref_claim(evidence.ref_claim)
        self._notes_mapping(evidence.mapping)
        self._insert("notes_mapping_evidence", evidence.key)

    def admit_notes_mapping_evidence(
        self, evidence: NotesMappingEvidence, work: WorkBudget
    ) -> None:
        """Check actual structure locally; a sender flag is never role authority."""
        if not isinstance(evidence, NotesMappingEvidence):
            raise CoreFailure(
                "NOTES_ROLE", evidence, "typed receiver evidence required"
            )
        self._available()
        with account_verification(work):
            for structure in evidence.structures:
                self._charge(work, "input_bytes", len(structure.body))
            evidence.validate()
            self._charge(work, "metadata_units", 1)
            with self._transaction():
                self._notes_mapping_evidence(evidence)

    def admit_ref_note(
        self,
        evidence: NotesMappingEvidence,
        native: NativeObject,
        physical_copy_uuidv4: str,
        work: WorkBudget,
        *,
        before_commit: Callable[[], None] | None = None,
        max_proof_bytes: int = 64 * 1024 * 1024,
        max_conflict_copies: int = 1_000,
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
            or type(max_conflict_copies) is not int
            or not 0 < max_conflict_copies < 2**63 - 1
        ):
            raise CoreFailure(
                "BUDGET", native.oid, "positive finite proof and copy limits required"
            )
        with account_verification(work):
            for structure in evidence.structures:
                self._charge(work, "proof_steps", 1)
                self._charge(work, "input_bytes", len(structure.body))
                structure.validate()
            evidence.validate()
            self._charge(work, "input_bytes", len(native.body))
            native.validate()
            self._charge(work, "metadata_units", 1)
            with self._transaction():
                # This is inside the writer cut, before any replay insertion can
                # trip a representation trigger or conceal damaged authority.
                existing = self._fetch_ref_note_copy(
                    native.oid, physical_copy_uuidv4, work, max_proof_bytes
                )
                if existing is not None:
                    self._validate_stored_ref_note(existing, work)
                self._notes_mapping_evidence(evidence)
                try:
                    self._insert(
                        "ref_retained_notes",
                        (
                            *native.oid.key,
                            physical_copy_uuidv4,
                            native.body,
                            native.declared_size,
                            native.digest_sha256,
                            *evidence.key,
                        ),
                    )
                except sqlite3.IntegrityError as error:
                    if str(error) == "conflicting exact note representation":
                        self._diagnose_ref_note_conflict(
                            native, work, max_proof_bytes, max_conflict_copies
                        )
                    raise
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
    ) -> bytes:
        if (
            not isinstance(claim, RefObservationClaim)
            or not isinstance(mapping, NotesMapping)
            or claim.root_oid != mapping.root_oid
        ):
            raise CoreFailure(
                "NOTES_ROLE", claim, "exact claimed root and mapping required"
            )
        if type(max_proof_bytes) is not int or not 0 < max_proof_bytes < 2**63:
            raise CoreFailure(
                "BUDGET", claim.identity, "positive finite proof limit required"
            )
        with self._snapshot():
            self._require_ref_claim(claim)
            self._charge(work, "metadata_units", 1)
            selected = self._ref_note_one(
                "SELECT physical_copy_uuidv4 FROM ref_retained_notes INDEXED BY ref_retained_notes_role_lookup WHERE observation_origin_uuidv4=? AND ref_observation_uuidv7=? AND ref_claim_provenance=? AND role_format=? AND root_oid=? AND interpretation_kind=? AND interpretation_version=? AND interpretation_scope=? AND annotated_object_oid=? AND note_oid=? AND mapping_path_json=? ORDER BY physical_copy_uuidv4 LIMIT 1",
                (*claim.identity, *mapping.key),
            )
            if selected is None:
                raise CoreFailure(
                    "NOTES_ROLE_UNAVAILABLE",
                    claim.identity,
                    "no claim-specific receiver-proven note body",
                )
            copy = self._stored(claim.identity, uuid4_value, selected[0])
            row = self._fetch_ref_note_copy(
                mapping.note_oid, copy, work, max_proof_bytes
            )
            if row is None:
                self._integrity_stop((claim.identity, "missing-selected-note"))
            stored_claim, stored_mapping, body = self._validate_stored_ref_note(
                row, work
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

    @_completed_read
    @_decoded_read
    def coverage(self, scope: CoreCoverageScope) -> CoverageProjection:
        with self._snapshot():
            rows = self.sql(
                "SELECT observed_at_us,coverage_state,details_json FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=(SELECT max(observed_at_us) FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=?) ORDER BY coverage_state",
                (scope.owner_kind, scope.encoded, scope.owner_kind, scope.encoded),
            )
            claims = tuple(
                self._stored(scope, CoverageClaim, scope, row[0], row[1], row[2])
                for row in rows
            )
            state = derive_coverage_state(claim.state for claim in claims)
            proofs = (
                self.sql(
                    "SELECT members_json FROM core_coverage_proofs WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state='complete'",
                    (scope.owner_kind, scope.encoded, rows[0][0]),
                )
                if rows and state == "complete"
                else []
            )
            if scope.owner_kind == "ref_observation" and proofs:
                self._integrity_stop((scope, "unsupported-ref-coverage-proof"))
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
