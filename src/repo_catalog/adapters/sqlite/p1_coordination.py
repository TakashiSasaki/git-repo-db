"""Isolated P1 reference adapters; the normal CLI does not import this module.

Support: cooperating processes on POSIX local filesystems with flock and SQLite
WAL locking. Unsupported platforms fail explicitly. Network filesystems and
hostile/privileged writers are outside this boundary. P7 must implement fresh
restore/activation and complete power-loss durability; this is not that engine.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_coordination import (
    AdmissionFailure,
    CoordinationError,
    NotesLimits,
    PairAdmission,
    RequestIdentity,
    SnapshotToken,
    WorkMeasurement,
    WorkPermit,
)
from repo_catalog.domain.p1_core import CoreFailure


@contextmanager
def catalog_gate(directory: Path, *, exclusive: bool) -> Iterator[None]:
    """One permanent gate inode per catalog; callers must not replace its file."""
    with _file_gate(directory / "p1-writer.lock", exclusive=exclusive):
        yield


@contextmanager
def _file_gate(path: Path, *, exclusive: bool) -> Iterator[None]:
    if os.name != "posix":
        raise CoordinationError("UNSUPPORTED_PLATFORM", "catalog", os.name)
    import fcntl

    with path.open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sqlite_corruption(error: BaseException) -> bool:
    code = getattr(error, "sqlite_errorcode", 0)
    return code & 255 in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB)


def persist_catalog_stop(directory: Path, reason: str) -> None:
    """Fence immediately, including while the detecting operation owns a gate.

    The separate short completion fence avoids recursively acquiring the main
    gate. Atomic sentinel creation precedes reason/fsync work: even process loss
    during that work leaves ordinary operations stopped. Full host-power-loss
    recovery and journal preservation remain P7 responsibilities.
    """
    directory = Path(directory)
    with _file_gate(directory / "p1-stop-fence.lock", exclusive=True):
        path = directory / "p1-recovery-stop.json"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return
        with os.fdopen(fd, "w") as handle:
            handle.write(_json({"reason": reason, "scope": "catalog"}))
            handle.flush()
            os.fsync(handle.fileno())
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


@contextmanager
def catalog_completion(directory: Path) -> Iterator[None]:
    """Serialize a final commit/certificate with the immediate stop transition."""
    directory = Path(directory)
    with _file_gate(directory / "p1-stop-fence.lock", exclusive=False):
        if (directory / "p1-recovery-stop.json").exists():
            raise CoordinationError("RECOVERY_REQUIRED", "catalog")
        yield


def _digest(db: sqlite3.Connection) -> str:
    """Conservative full content fingerprint of this already pinned snapshot.

    A derivative freshness token may be a digest: it never substitutes for a
    domain PK/FK. Includes whole schema and all values, independent of row order.
    P6 can optimize only with equally conservative evidence, never Core counters.
    """
    schema = [
        tuple(row)
        for row in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]
    rows = {}
    for kind, name, _, _ in schema:
        if kind != "table":
            continue
        quoted = '"' + name.replace('"', '""') + '"'
        values = []
        for row in db.execute(f"SELECT * FROM {quoted}"):
            values.append(
                _json(
                    [
                        {"bytes": base64.b64encode(v).decode("ascii")}
                        if isinstance(v, bytes)
                        else {"type": type(v).__name__, "value": v}
                        for v in row
                    ]
                )
            )
        rows[name] = sorted(values)
    return hashlib.sha256(_json([schema, rows]).encode()).hexdigest()


def _identity(db: sqlite3.Connection, role: str) -> tuple[str, str]:
    rows = db.execute(
        "SELECT store_role,repository_uuidv4,catalog_instance_uuidv4 "
        "FROM store_identity"
    ).fetchall()
    if len(rows) != 1 or rows[0][0] != role:
        raise CoordinationError("STORE_IDENTITY", role)
    return rows[0][1], rows[0][2]


def validate_dependencies(core: sqlite3.Connection, context: sqlite3.Connection):
    for object_format, full_oid in context.execute(
        "SELECT DISTINCT object_format,full_oid FROM core_references"
    ):
        if not core.execute(
            "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
            (object_format, full_oid),
        ).fetchone():
            raise CoordinationError("MISSING_CORE_REFERENCE", "context", full_oid)


def validate_pair(
    core: sqlite3.Connection, context: sqlite3.Connection
) -> SnapshotToken:
    """Validate persisted authorities, including failures of semantic CHECK UDFs.

    Invalid stored UTF-8/JSON can make integrity_check raise SQLITE_ERROR instead
    of returning a corruption row. It is still failed authoritative validation,
    not a rejected incoming unit. Transient cancellation/locking or a denied
    capability is not evidence of storage corruption.
    """
    try:
        return _validate_pair(core, context)
    except sqlite3.DatabaseError as error:
        code = getattr(error, "sqlite_errorcode", 0) & 255
        detail = str(error)
        storage_fault = code in {
            sqlite3.SQLITE_CORRUPT,
            sqlite3.SQLITE_NOTADB,
            sqlite3.SQLITE_IOERR,
        }
        semantic_fault = (
            code == sqlite3.SQLITE_ERROR
            and detail == "user-defined function raised exception"
        ) or detail.startswith("Could not decode to UTF-8 column")
        if not (storage_fault or semantic_fault):
            # Locking, cancellation, resource exhaustion and capability misuse
            # do not establish persisted corruption. IOERR during these reads
            # is an authoritative storage fault preventing required validation.
            raise
        failure = CoordinationError(
            "CORRUPTION",
            "core+context",
            "authoritative validation failed: " + str(error),
        )
        _notify_validation_corruption(core, context, failure)
        raise failure from error
    except Exception as error:
        _notify_validation_corruption(core, context, error)
        raise


def _notify_validation_corruption(core, context, error):
    if getattr(error, "code", None) in {
        "CORRUPTION",
        "FOREIGN_KEY",
        "MISSING_CORE_REFERENCE",
        "AUTHORITATIVE_CORRUPTION",
    }:
        # A caller may catch validation failure inside an already pinned pair.
        # Notify its owning capability now, before outer context unwinding.
        # Raw connections rely on their coordinator's initial validation catch.
        for db in (core, context):
            if isinstance(db, ReadSnapshot):
                db._on_error(error)


def _validate_pair(
    core: sqlite3.Connection, context: sqlite3.Connection
) -> SnapshotToken:
    identity = _identity(core, "core")
    if identity != _identity(context, "context"):
        raise CoordinationError("PAIR_IDENTITY", "core+context")
    for db, role in ((core, "core"), (context, "context")):
        if [tuple(row) for row in db.execute("PRAGMA integrity_check")] != [("ok",)]:
            raise CoordinationError("CORRUPTION", role)
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise CoordinationError("FOREIGN_KEY", role)
    # SQLite does not re-evaluate insertion triggers for an existing snapshot.
    from repo_catalog.adapters.sqlite.p1_core import validate_embedded_references

    validate_embedded_references(core)
    validate_dependencies(core, context)
    return SnapshotToken(*identity, _digest(core), _digest(context))


@dataclass
class PairedSnapshot:
    core: ReadSnapshot
    context: ReadSnapshot
    token: SnapshotToken


class _Cursor:
    """Do not leak a raw connection through Cursor.connection."""

    def __init__(self, cursor, owner):
        self._cursor, self.connection = cursor, owner

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def fetchone(self):
        return self._run(self._cursor.fetchone)

    def fetchall(self):
        return self._run(self._cursor.fetchall)

    def fetchmany(self, size=1):
        return self._run(self._cursor.fetchmany, size)

    def _run(self, operation, *args):
        if hasattr(self.connection, "_read_call"):
            return self.connection._read_call(operation, *args)
        return operation(*args)

    def __iter__(self):
        return self

    def __next__(self):
        return self._run(next, self._cursor)


class ReadSnapshot:
    """Pinned read capability; no public authorizer or transaction mutation."""

    def __init__(self, db, running, on_error):
        self._db = db
        self._running, self._active = running, True
        self._on_error = on_error

    def _available(self):
        if not self._active:
            raise CoordinationError("SNAPSHOT_EXPIRED", "read")
        self._running()

    @property
    def in_transaction(self):
        self._available()
        return self._db.in_transaction

    def execute(self, sql, parameters=()):
        return _Cursor(self._read_call(self._db.execute, sql, parameters), self)

    def _read_call(self, operation, *args):
        self._available()
        try:
            return operation(*args)
        except Exception as error:
            self._on_error(error)
            raise


class AdmissionTransaction:
    """Supported callback connection that cannot end the enclosing transaction.

    Domain authorizers compose with the transaction guard. Deliberate access to
    private infrastructure or arbitrary Python/filesystem privilege is outside
    the supported boundary.
    """

    def __init__(self, db: sqlite3.Connection):
        self._db = db
        self.set_authorizer(None)

    @property
    def in_transaction(self):
        return self._db.in_transaction

    def set_authorizer(self, callback):
        def authorize(action, first, second, database, trigger):
            if action not in {
                sqlite3.SQLITE_SELECT,
                sqlite3.SQLITE_READ,
                sqlite3.SQLITE_FUNCTION,
                sqlite3.SQLITE_INSERT,
                sqlite3.SQLITE_UPDATE,
                sqlite3.SQLITE_DELETE,
                sqlite3.SQLITE_SAVEPOINT,
                sqlite3.SQLITE_RECURSIVE,
            }:
                return sqlite3.SQLITE_DENY
            if callback is not None:
                return callback(action, first, second, database, trigger)
            return sqlite3.SQLITE_OK

        self._db.set_authorizer(authorize)

    def execute(self, sql, parameters=()):
        return _Cursor(self._db.execute(sql, parameters), self)

    def executemany(self, sql, parameters):
        return _Cursor(self._db.executemany(sql, parameters), self)

    def commit(self):
        raise CoordinationError("TRANSACTION_OWNERSHIP", "admission")

    rollback = commit

    def executescript(self, _sql):
        raise CoordinationError("TRANSACTION_OWNERSHIP", "admission")


class PairCoordinator:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _check_running(self):
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoordinationError("RECOVERY_REQUIRED", "catalog")

    def _open(self, role: str):
        path = self.directory / f"{role}.sqlite3"
        if not path.is_file():
            raise CoordinationError("AUTHORITY_UNAVAILABLE", role)
        try:
            return connect(path, role)
        except Exception as error:
            self._record_corruption(error)
            raise

    def _record_corruption(self, error: Exception, *, existing: bool = True):
        codes = {"AUTHORITATIVE_CORRUPTION"}
        if existing:
            codes |= {"CORRUPTION", "FOREIGN_KEY", "MISSING_CORE_REFERENCE"}
        if getattr(error, "code", None) in codes or _sqlite_corruption(error):
            # Persist before stack unwinding, rollback, callback or gate release.
            persist_catalog_stop(self.directory, str(error))

    def _guard_read(self, db: sqlite3.Connection):
        def authorize(action, _first, _second, _database, _trigger):
            if (
                action == sqlite3.SQLITE_PRAGMA
                and _first in ("integrity_check", "foreign_key_check")
                and _second is None
            ):
                return sqlite3.SQLITE_OK
            if action not in (
                sqlite3.SQLITE_READ,
                sqlite3.SQLITE_SELECT,
                sqlite3.SQLITE_FUNCTION,
            ):
                return sqlite3.SQLITE_DENY
            if (
                action == sqlite3.SQLITE_READ
                and (self.directory / "p1-recovery-stop.json").exists()
            ):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(authorize)

    def stop(self, reason: str):
        """Persistent catalog stop outside damaged authority/derivatives.

        Never cleared here. P7 activation must select a fresh verified catalog.
        This only fences cooperating application operations; it is not forensic
        source capture or a promise to make filesystem bytes read-only.
        """
        persist_catalog_stop(self.directory, reason)

    def admit(
        self,
        core_unit: Callable[[AdmissionTransaction], None],
        context_unit: Callable[[AdmissionTransaction], None],
        *,
        cut: Callable[[str], None] = lambda point: None,
    ) -> PairAdmission:
        self._check_running()
        try:
            return self._admit(core_unit, context_unit, cut=cut)
        except AdmissionFailure as error:
            if getattr(
                error.cause, "code", None
            ) == "AUTHORITATIVE_CORRUPTION" or _sqlite_corruption(error.cause):
                self._record_corruption(error.cause, existing=False)
            raise
        except Exception as error:
            # Opening/validating a damaged database can fail before a local
            # admission transaction exists; the external stop still applies.
            if _sqlite_corruption(error):
                self._record_corruption(error)
            raise

    def _admit(self, core_unit, context_unit, *, cut) -> PairAdmission:
        with catalog_gate(self.directory, exclusive=True), ExitStack() as stack:
            self._check_running()
            core = stack.enter_context(closing(self._open("core")))
            context = stack.enter_context(closing(self._open("context")))
            try:
                if _identity(core, "core") != _identity(context, "context"):
                    raise CoordinationError("PAIR_IDENTITY", "core+context")
            except Exception as error:
                self._record_corruption(error)
                raise
            core_committed, context_committed = False, False
            try:
                core.execute("BEGIN IMMEDIATE")
                core_unit(AdmissionTransaction(core))
                core.set_authorizer(None)
                cut("before_core_commit")
                with catalog_completion(self.directory):
                    core.commit()
                core_committed = True
                cut("after_core_commit")
                context.execute("BEGIN IMMEDIATE")
                context_unit(AdmissionTransaction(context))
                context.set_authorizer(None)
                cut("during_context")
                validate_dependencies(core, context)
                with catalog_completion(self.directory):
                    context.commit()
                context_committed = True
                cut("after_context_commit")
                self._check_running()
            except Exception as error:
                self._record_corruption(error, existing=False)
                core.set_authorizer(None)
                context.set_authorizer(None)
                core.rollback()
                context.rollback()
                raise AdmissionFailure(
                    PairAdmission(core_committed, context_committed), error
                ) from error
            except BaseException:
                core.set_authorizer(None)
                context.set_authorizer(None)
                core.rollback()
                context.rollback()
                raise
        return PairAdmission(True, True)

    @contextmanager
    def snapshots(self) -> Iterator[PairedSnapshot]:
        self._check_running()
        try:
            with self._snapshots() as pair:
                yield pair
        except Exception as error:
            if getattr(error, "code", None) in (
                "CORRUPTION",
                "FOREIGN_KEY",
                "MISSING_CORE_REFERENCE",
            ) or _sqlite_corruption(error):
                self._record_corruption(error)
            raise

    @contextmanager
    def _snapshots(self) -> Iterator[PairedSnapshot]:
        with ExitStack() as stack:
            with catalog_gate(self.directory, exclusive=False):
                self._check_running()
                core = stack.enter_context(closing(self._open("core")))
                context = stack.enter_context(closing(self._open("context")))
                try:
                    for db in (core, context):
                        db.execute("PRAGMA query_only=ON")
                        db.execute("BEGIN")
                        db.execute("SELECT * FROM store_identity").fetchall()
                        self._guard_read(db)
                    token = validate_pair(core, context)
                except Exception as error:
                    self._record_corruption(error)
                    raise
            try:
                reads = (
                    ReadSnapshot(core, self._check_running, self._record_corruption),
                    ReadSnapshot(context, self._check_running, self._record_corruption),
                )
                yield PairedSnapshot(*reads, token)
            finally:
                for read in reads:
                    read._active = False
                core.set_authorizer(None)
                context.set_authorizer(None)
                core.rollback()
                context.rollback()

    @contextmanager
    def core_snapshot(self) -> Iterator[ReadSnapshot]:
        self._check_running()
        try:
            with self._core_snapshot() as core:
                yield core
        except Exception as error:
            if _sqlite_corruption(error):
                self._record_corruption(error)
            raise

    @contextmanager
    def _core_snapshot(self) -> Iterator[ReadSnapshot]:
        with ExitStack() as stack:
            with catalog_gate(self.directory, exclusive=False):
                self._check_running()
                core = stack.enter_context(closing(self._open("core")))
                core.execute("PRAGMA query_only=ON")
                core.execute("BEGIN")
                try:
                    _identity(core, "core")  # SELECT pins a real SQLite snapshot.
                except Exception as error:
                    self._record_corruption(error)
                    raise
                self._guard_read(core)
            try:
                read = ReadSnapshot(core, self._check_running, self._record_corruption)
                yield read
            finally:
                read._active = False
                core.set_authorizer(None)
                core.rollback()

    def backup_candidate(
        self,
        destination: Path,
        *,
        cut: Callable[[str], None] = lambda point: None,
    ) -> SnapshotToken:
        self._check_running()
        try:
            return self._backup_candidate(destination, cut=cut)
        except Exception as error:
            if getattr(error, "code", None) in (
                "CORRUPTION",
                "FOREIGN_KEY",
                "MISSING_CORE_REFERENCE",
            ) or _sqlite_corruption(error):
                self._record_corruption(error)
            raise

    def _backup_candidate(self, destination: Path, *, cut) -> SnapshotToken:
        """Conservative unpublished pair, certified only after candidate checks.

        No overwrite, source mutation, restore or activation. The certificate is
        local process-completion evidence. Full fsync/power-loss protocol is P7.
        """
        destination = Path(destination)
        destination.mkdir()  # Never bless an interrupted/existing destination.
        with catalog_gate(self.directory, exclusive=False):
            self._check_running()
            for role in ("core", "context"):
                with (
                    closing(self._open(role)) as source,
                    closing(sqlite3.connect(destination / f"{role}.sqlite3")) as target,
                ):
                    try:
                        source.backup(target)
                    except Exception as error:
                        self._record_corruption(error)
                        raise
                cut(f"after_{role}_backup")
            try:
                with PairCoordinator(destination).snapshots() as pair:
                    token = pair.token
            except Exception as error:
                self._record_corruption(error)
                raise
            certificate = {
                "scope": "core+context",
                "token": token.__dict__,
                "files": {
                    f"{role}.sqlite3": hashlib.sha256(
                        (destination / f"{role}.sqlite3").read_bytes()
                    ).hexdigest()
                    for role in ("core", "context")
                },
                "power_loss_safe": False,
            }
            cut("before_certificate")
            with catalog_completion(self.directory):
                (destination / "p1-pair-candidate.json").write_text(_json(certificate))
            return token

    @staticmethod
    def validate_backup(destination: Path) -> SnapshotToken:
        candidate = json.loads((destination / "p1-pair-candidate.json").read_text())
        expected = {"core.sqlite3", "context.sqlite3"}
        if candidate["scope"] != "core+context" or set(candidate["files"]) != expected:
            raise CoordinationError("PAIR_CERTIFICATE", "backup")
        for name, digest in candidate["files"].items():
            if hashlib.sha256((destination / name).read_bytes()).hexdigest() != digest:
                raise CoordinationError("PAIR_BYTES", "backup")
        with PairCoordinator(destination).snapshots() as pair:
            if pair.token.__dict__ != candidate["token"]:
                raise CoordinationError("PAIR_CONTENT", "backup")
            return pair.token


class WorkLedger:
    """Request-scoped conservative accounting on a dedicated Operational DB.

    Reserve a finite upper bound durably BEFORE actual work. Finish records the
    measured cost; an interrupted/unsettled permit keeps its full reservation.
    Thus rollback or process death cannot refund already performed work. A lost
    Operational store cannot continue an old request. No authoritative success
    or retained bytes are inferred from this discardable state.
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        *,
        repository_uuidv4: str | None = None,
        catalog_instance_uuidv4: str | None = None,
    ):
        self.db = db
        self._issued_permits: dict[int, WorkPermit] = {}
        self._path = Path(db.execute("PRAGMA database_list").fetchone()[2])
        self._file_identity = self._stat_identity()
        self._ready()
        repository, instance = _identity(db, "operational")
        if (repository_uuidv4 is not None and repository != repository_uuidv4) or (
            catalog_instance_uuidv4 is not None and instance != catalog_instance_uuidv4
        ):
            raise CoordinationError("STORE_IDENTITY", "operational")

    def _stat_identity(self):
        try:
            stat = self._path.stat()
        except OSError as error:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request") from error
        return stat.st_dev, stat.st_ino

    def _ready(self):
        # Returning an uncommitted reservation would permit work before the
        # accounting survives process loss. Reject unsupported connections and
        # settings rather than silently changing caller transaction ownership.
        if self.db.in_transaction:
            raise CoordinationError("ACCOUNTING_TRANSACTION", "request")
        if (
            self.db.isolation_level is not None
            or self.db.execute("PRAGMA synchronous").fetchone()[0] < 2
            or self.db.execute("PRAGMA journal_mode").fetchone()[0] != "wal"
            or self.db.execute("PRAGMA foreign_keys").fetchone()[0] != 1
        ):
            raise CoordinationError("ACCOUNTING_DURABILITY", "request")
        if self._stat_identity() != self._file_identity:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")

    def validate_continuation(
        self, request: RequestIdentity, attempt_uuidv4=None, *, scope=None
    ):
        """Missing accounting never means a resumed request has spent zero."""
        self._ready()
        self._validate_continuation(request, attempt_uuidv4, scope=scope)

    def _validate_continuation(self, request, attempt_uuidv4=None, *, scope=None):
        row = self.db.execute(
            "SELECT state,request_scope_json FROM acquisition_requests WHERE request_origin_uuidv4=? "
            "AND request_uuidv4=?",
            request.values(),
        ).fetchone()
        kinds = {
            row[0]
            for row in self.db.execute(
                "SELECT work_kind FROM request_budgets WHERE request_origin_uuidv4=? "
                "AND request_uuidv4=?",
                request.values(),
            )
        }
        if row is None or row[0] != "open" or kinds != set(NotesLimits.work_limits()):
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
        if scope is not None and _json(json.loads(row[1])) != _json(json.loads(scope)):
            raise CoordinationError("REQUEST_SCOPE", "request")
        if (
            attempt_uuidv4 is not None
            and not self.db.execute(
                "SELECT 1 FROM acquisition_attempts WHERE request_origin_uuidv4=? "
                "AND request_uuidv4=? AND attempt_uuidv4=?",
                (*request.values(), attempt_uuidv4),
            ).fetchone()
        ):
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")

    def usage(self, request: RequestIdentity) -> dict[str, int]:
        """Conservative expenditure, including each unsettled full reservation."""
        self._ready()
        self.db.execute("BEGIN")
        try:
            self._validate_continuation(request)
            result = dict.fromkeys(NotesLimits.work_limits(), 0)
            for kind, reserved, actual in self.db.execute(
                "SELECT work_kind,reserved,actual FROM work_accounting "
                "WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                request.values(),
            ):
                result[kind] += reserved if actual is None else actual
            return result
        finally:
            self.db.rollback()

    def new_request(self, request: RequestIdentity, scope: str, limits: dict[str, int]):
        required = {
            "input_bytes",
            "verification_bytes",
            "metadata_units",
            "proof_steps",
        }
        if set(limits) != required:
            raise ValueError("all four finite work limits required")
        for limit in limits.values():
            if type(limit) is not int or not 0 <= limit <= 2**63 - 1:
                raise ValueError("finite signed int64 nonnegative limit required")
        self._ready()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT INTO acquisition_requests VALUES(?,?,?,'open')",
                (*request.values(), scope),
            )
            self.db.executemany(
                "INSERT INTO request_budgets VALUES(?,?,?,?)",
                [(*request.values(), kind, limit) for kind, limit in limits.items()],
            )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def attempt(self, request: RequestIdentity, attempt_uuidv4: str, continuation="{}"):
        self._ready()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._validate_continuation(request)
            self.db.execute(
                "INSERT INTO acquisition_attempts VALUES(?,?,?,?)",
                (*request.values(), attempt_uuidv4, continuation),
            )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def increase_limit(
        self, request: RequestIdentity, work_kind: str, finite_limit: int
    ):
        """Explicit finite increase; existing accounting is never reset."""
        if type(finite_limit) is not int or not 0 <= finite_limit <= 2**63 - 1:
            raise ValueError("finite nonnegative signed int64 limit required")
        self._ready()
        self._validate_continuation(request)
        cursor = self.db.execute(
            "UPDATE request_budgets SET finite_limit=? WHERE request_origin_uuidv4=? "
            "AND request_uuidv4=? AND work_kind=? AND finite_limit<?",
            (finite_limit, *request.values(), work_kind, finite_limit),
        )
        if cursor.rowcount != 1:
            raise CoordinationError("FINITE_INCREASE_REQUIRED", "request")

    def reserve(
        self,
        request: RequestIdentity,
        attempt_uuidv4: str,
        work_kind: str,
        work_coordinate: str,
        upper_bound: int,
    ) -> WorkPermit:
        self._ready()
        if type(upper_bound) is not int or not 0 <= upper_bound <= 2**63 - 1:
            raise ValueError("finite nonnegative upper bound required")
        self._validate_continuation(request, attempt_uuidv4)
        self._insert_reservation(
            request, attempt_uuidv4, work_kind, work_coordinate, upper_bound
        )
        return self._issue(
            WorkPermit(request, attempt_uuidv4, work_kind, work_coordinate, upper_bound)
        )

    def _issue(self, permit):
        self._issued_permits[id(permit)] = permit
        return permit

    def abandon(self, permit: WorkPermit):
        """Discard a live settlement capability without refunding its charge."""
        self._check_permit(permit)
        del self._issued_permits[id(permit)]

    def _check_permit(self, permit):
        # A reconstructed row value is not evidence of measured work. In
        # particular, no new process may settle a formerly uncertain permit.
        if self._issued_permits.get(id(permit)) is not permit:
            raise CoordinationError("PERMIT_ALREADY_SETTLED_OR_LOST", "request")

    def _insert_reservation(self, request, attempt, kind, coordinate, amount):
        self.db.execute(
            "INSERT INTO work_accounting VALUES(?,?,?,?,?,?,NULL)",
            (*request.values(), attempt, kind, coordinate, amount),
        )

    def reserve_processing_step(self, request, attempt, kind, amount) -> WorkPermit:
        """Allocate a real processing occurrence and reserve it in one commit.

        Counting rows is insufficient after failed reservations or noncontiguous
        prior coordinates. The write lock also serializes budget instances using
        the same request/attempt; no process-local counter is authoritative.
        """
        self._ready()
        if type(amount) is not int or not 0 <= amount <= 2**63 - 1:
            raise ValueError("finite nonnegative upper bound required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._validate_continuation(request, attempt)
            allocation_scope = _json(
                {
                    "attempt_uuidv4": attempt,
                    "purpose": "processing-step-allocation",
                }
            )
            cursor = self.db.execute(
                "SELECT cursor_json FROM request_continuations "
                "WHERE request_origin_uuidv4=? AND request_uuidv4=? "
                "AND continuation_scope_json=?",
                (*request.values(), allocation_scope),
            ).fetchone()
            if cursor is None:
                # Recover only the coordinate allocator from existing work,
                # never expenditure from a missing accounting history. This
                # scan happens once; the Operational cursor avoids O(n²) work.
                last = self.db.execute(
                    "SELECT coalesce(max(CAST(substr(work_coordinate,17) AS INTEGER)),0) "
                    "FROM work_accounting WHERE request_origin_uuidv4=? "
                    "AND request_uuidv4=? AND attempt_uuidv4=? "
                    "AND work_coordinate GLOB 'processing-step:[0-9]*'",
                    (*request.values(), attempt),
                ).fetchone()[0]
            else:
                last = json.loads(cursor[0])["last_processing_step"]
            if type(last) is not int or not 0 <= last < 2**63 - 1:
                raise CoordinationError("ACCOUNTING_STATE", "request")
            step = last + 1
            coordinate = f"processing-step:{step}"
            self._insert_reservation(request, attempt, kind, coordinate, amount)
            self.db.execute(
                "INSERT INTO request_continuations VALUES(?,?,?,?) "
                "ON CONFLICT(request_origin_uuidv4,request_uuidv4,continuation_scope_json) "
                "DO UPDATE SET cursor_json=excluded.cursor_json",
                (
                    *request.values(),
                    allocation_scope,
                    _json({"last_processing_step": step}),
                ),
            )
            self.db.commit()
            return self._issue(WorkPermit(request, attempt, kind, coordinate, amount))
        except BaseException:
            self.db.rollback()
            raise

    def finish(self, permit: WorkPermit, actual: int):
        self._check_permit(permit)
        if type(actual) is not int or not 0 <= actual <= permit.reserved:
            raise ValueError("actual work exceeds reserved bound")
        self._ready()
        self._validate_continuation(permit.request, permit.attempt_uuidv4)
        cursor = self.db.execute(
            "UPDATE work_accounting SET actual=? WHERE request_origin_uuidv4=? "
            "AND request_uuidv4=? AND attempt_uuidv4=? AND work_kind=? "
            "AND work_coordinate=? AND actual IS NULL AND reserved=?",
            (
                actual,
                *permit.request.values(),
                permit.attempt_uuidv4,
                permit.work_kind,
                permit.work_coordinate,
                permit.reserved,
            ),
        )
        if cursor.rowcount != 1:
            raise CoordinationError("PERMIT_ALREADY_SETTLED_OR_LOST", "request")
        del self._issued_permits[id(permit)]


class NotesWorkBudget:
    """P4-facing require/charge bridge, separate from Core transaction ownership.

    Coordinates are actual ordered processing steps in this genuine attempt,
    rather than new per-fact identities. New attempts retain the same request.
    """

    def __init__(
        self,
        ledger: WorkLedger,
        request: RequestIdentity,
        attempt_uuidv4: str,
        limits: NotesLimits,
    ):
        self.ledger, self.request = ledger, request
        self.attempt_uuidv4, self.limits = attempt_uuidv4, limits
        self.pending: dict[str, WorkPermit] = {}
        ledger._ready()
        ledger.validate_continuation(request, attempt_uuidv4)

    def require(self, unit: str, amount: int = 1):
        if unit in self.pending:
            raise CoordinationError("UNSETTLED_WORK", "request", unit)
        try:
            permit = self.ledger.reserve_processing_step(
                self.request, self.attempt_uuidv4, unit, amount
            )
        except sqlite3.IntegrityError as error:
            if str(error) != "finite cumulative request budget":
                raise
            raise CoreFailure("BUDGET", (self.request, unit), str(error)) from error
        self.pending[unit] = permit

    def abandon(self, unit: str):
        """Forget a local pending handle, retaining its full durable charge.

        Use only when precise performed work cannot be measured (e.g. a failed
        input operation). This never settles or refunds the reservation.
        """
        if unit not in self.pending:
            raise CoordinationError("UNRESERVED_WORK", "request", unit)
        self.ledger.abandon(self.pending[unit])
        del self.pending[unit]

    def charge(self, unit: str, amount: int):
        if unit not in self.pending:
            raise CoordinationError("UNRESERVED_WORK", "request", unit)
        self.ledger.finish(self.pending[unit], amount)
        del self.pending[unit]

    @contextmanager
    def measured(self, unit: str, upper_bound: int) -> Iterator[WorkMeasurement]:
        """Reserve before work; settle measured success, retain failed uncertainty.

        Set meter.actual only after counting performed work. Any exceptional
        exit, including process interruption, retains the full reservation.
        Failure to obtain a permit prevents entry into the work block.
        """
        self.require(unit, upper_bound)
        meter = WorkMeasurement()
        try:
            yield meter
        except BaseException:
            self.abandon(unit)
            raise
        else:
            if meter.actual is None:
                self.abandon(unit)
            else:
                self.charge(unit, meter.actual)


class SearchProjection:
    """Discardable authority-derived candidates; None requires authority scan.

    Public builders read actual pinned authority. There is no general text/body
    admission API: P6 owns additional typed projectors, including verified notes.
    """

    def __init__(self, db: sqlite3.Connection | None):
        self.db = db

    @staticmethod
    def context_documents(pair: PairedSnapshot) -> dict[str, str]:
        if validate_pair(pair.core, pair.context) != pair.token:
            raise CoordinationError("SNAPSHOT_CONTENT", "search")
        documents = {}
        for row in pair.context.execute(
            "SELECT c.service_instance_uuidv4,c.resource_kind,c.provider_resource_id,c.field_name,"
            "c.clock_json,c.value_json,c.provenance_json,b.text_value "
            "FROM field_candidates c LEFT JOIN text_bodies b ON c.text_body_sha256=b.sha256"
        ):
            # Only this named local FK denotes retained text. Reported digests
            # remain qualified metadata even if equal bytes happen to be local.
            value = row[7] if row[3] == "text_body_sha256" else json.loads(row[5])
            if isinstance(value, str):
                documents[_json(tuple(row[:7]))] = value
        return documents

    def rebuild_context(self, pair: PairedSnapshot):
        self._replace("context_text", pair.token, self.context_documents(pair))

    def rebuild_git_metadata(self, pair: PairedSnapshot):
        if validate_pair(pair.core, pair.context) != pair.token:
            raise CoordinationError("SNAPSHOT_CONTENT", "search")
        documents = {
            _json(tuple(row)): row[1]
            for row in pair.core.execute(
                "SELECT object_format,full_oid FROM git_objects"
            )
        }
        self._replace("git_metadata", pair.token, documents)

    def _replace(self, kind: str, token: SnapshotToken, documents: dict[str, str]):
        if self.db is None:
            raise CoordinationError("UNAVAILABLE", "search")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "DELETE FROM search_documents WHERE projection_kind=?", (kind,)
            )
            self.db.execute(
                "DELETE FROM search_projections WHERE projection_kind=?", (kind,)
            )
            self.db.execute(
                "INSERT INTO search_projections VALUES(?,?)", (kind, token.encode())
            )
            self.db.executemany(
                "INSERT INTO search_documents VALUES(?,?,?,?)",
                [(kind, token.encode(), key, text) for key, text in documents.items()],
            )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def candidates(
        self, kind: str, token: SnapshotToken, needle: str
    ) -> set[str] | None:
        if self.db is None:
            return None
        try:
            self.db.execute("BEGIN")
            if not self.db.execute(
                "SELECT 1 FROM search_projections WHERE projection_kind=? AND snapshot_token_json=?",
                (kind, token.encode()),
            ).fetchone():
                return None
            return {
                row[0]
                for row in self.db.execute(
                    "SELECT document_key_json FROM search_documents WHERE projection_kind=? "
                    "AND snapshot_token_json=? AND instr(searchable_text,?)>0",
                    (kind, token.encode(), needle),
                )
            }
        except sqlite3.DatabaseError:
            return None
        finally:
            self.db.rollback()

    def read(
        self,
        kind: str,
        token: SnapshotToken,
        needle: str,
        authoritative_scan: Callable[[], dict[str, str]],
    ) -> tuple[str, dict[str, str]]:
        candidates = self.candidates(kind, token, needle)
        rows = authoritative_scan()  # caller retains pinned authority snapshot
        expected = {key for key, text in rows.items() if needle in text}
        if candidates is not None and candidates != expected:
            # A matching freshness token alone cannot prove a damaged/truncated
            # projection complete. The conservative P1 adapter verifies against
            # direct authority; optimized completeness proof belongs to P6.
            candidates = None
        return (
            "projection" if candidates is not None else "authority_scan",
            {
                key: text
                for key, text in rows.items()
                if needle in text and (candidates is None or key in candidates)
            },
        )
