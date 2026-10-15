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
    account_verification,
    encode,
    intrinsic_members,
    uuid4_value,
    valid_native,
    valid_note_role,
)
from repo_catalog.domain.p1_coverage import (
    CoverageClaim,
    CoverageProjection,
    derive_coverage_state,
)
from repo_catalog.domain.ports.p1_core import WorkBudget


def _completed_read(method):
    """Linearize successful result delivery against the persistent stop fence."""

    @wraps(method)
    def completed(self, *args, **kwargs):
        result = method(self, *args, **kwargs)
        return self._complete_read(result)

    return completed


class Core:
    def __init__(
        self, path: Path, *, on_corruption: Callable[[CoreFailure], None] | None = None
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
            except sqlite3.DatabaseError as error:
                if Path(path).is_file() and getattr(
                    error, "sqlite_errorcode", None
                ) in (sqlite3.SQLITE_NOTADB, sqlite3.SQLITE_CORRUPT):
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
            if getattr(error, "sqlite_errorcode", None) in (
                sqlite3.SQLITE_NOTADB,
                sqlite3.SQLITE_CORRUPT,
            ):
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
                except BaseException:
                    if self._external:
                        self._db.execute("ROLLBACK TO p1_core_unit")
                        self._db.execute("RELEASE p1_core_unit")
                    else:
                        self._db.execute("ROLLBACK")
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
    def scalar(self, oid: OID, field: ScalarField) -> Projection:
        rows = self.sql(
            "SELECT c.*, EXISTS(SELECT 1 FROM intrinsic_claims i WHERE i.object_format=c.object_format AND i.full_oid=c.full_oid AND i.field=c.field AND i.value=c.value AND i.provenance=c.provenance) checked FROM scalar_claims c WHERE object_format=? AND full_oid=? AND field=?",
            (*oid.key, field),
        )
        alternatives = tuple(
            {
                "value": json.loads(r["value"]),
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
    def relations(
        self, oid: OID, relation: str, scope: str | None = None
    ) -> Projection:
        rows = self.sql(
            "SELECT g.*, EXISTS(SELECT 1 FROM intrinsic_groups i WHERE i.object_format=g.object_format AND i.full_oid=g.full_oid AND i.relation=g.relation AND i.scope=g.scope AND i.status=g.status AND i.membership=g.membership AND i.provenance=g.provenance) checked FROM relation_groups g WHERE object_format=? AND full_oid=? AND relation=?",
            (*oid.key, relation),
        )
        alternatives = tuple(
            {
                "status": r["status"],
                "membership": json.loads(r["membership"]),
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
            object_format=None,
            full_oid=None,
            field=None,
        )
        names = {
            "repository": ("repository_uuidv4",),
            "capture": ("capture_origin_uuidv4", "capture_uuidv4"),
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
    def coverage(self, scope: CoreCoverageScope) -> CoverageProjection:
        with self._snapshot():
            rows = self.sql(
                "SELECT observed_at_us,coverage_state,details_json FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=(SELECT max(observed_at_us) FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=?) ORDER BY coverage_state",
                (scope.owner_kind, scope.encoded, scope.owner_kind, scope.encoded),
            )
            claims = tuple(CoverageClaim(scope, row[0], row[1], row[2]) for row in rows)
            state = derive_coverage_state(claim.state for claim in claims)
            proofs = (
                self.sql(
                    "SELECT members_json FROM core_coverage_proofs WHERE owner_kind=? AND owner_coordinates_json=? AND observed_at_us=? AND coverage_state='complete'",
                    (scope.owner_kind, scope.encoded, rows[0][0]),
                )
                if rows and state == "complete"
                else []
            )
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
            "retained-byte corruption; stop catalog and restore fresh",
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
        return row["body"]

    @_completed_read
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
                note = OID(target.object_format, row[0])
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
                        Provenance(*json.loads(row[1])),
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
                        Provenance(*json.loads(row[3])),
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
        "SELECT object_format,status,membership FROM notes_groups"
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
