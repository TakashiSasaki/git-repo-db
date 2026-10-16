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


@dataclass(frozen=True)
class SnapshotReadLimits:
    """Finite per-store SQLite read work; exhaustion is not corruption."""

    max_store_bytes: int = 64 * 1024 * 1024
    max_total_rows: int = 10000
    max_sql_vm_steps: int = 5_000_000

    def __post_init__(self):
        for value in (self.max_store_bytes, self.max_total_rows, self.max_sql_vm_steps):
            if type(value) is not int or value <= 0:
                raise ValueError("positive finite integer read limits required")


def apply_snapshot_read_limits(db, limits: SnapshotReadLimits | None):
    """Reserve an explicit finite working set before validation/extraction."""
    if limits is None:
        return
    remaining = limits.max_sql_vm_steps

    def progress():
        nonlocal remaining
        remaining -= 100
        return remaining < 0

    db.set_progress_handler(progress, 100)
    size = (
        db.execute("PRAGMA page_size").fetchone()[0]
        * db.execute("PRAGMA page_count").fetchone()[0]
    )
    if size > limits.max_store_bytes:
        raise CoordinationError("QUERY_BUDGET", "snapshot", "store byte limit")
    total = 0
    for (name,) in db.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall():
        quoted = '"' + name.replace('"', '""') + '"'
        total += db.execute(f"SELECT count(*) FROM {quoted}").fetchone()[0]
        if total > limits.max_total_rows:
            raise CoordinationError("QUERY_BUDGET", "snapshot", "stored row limit")


def _digest(db: sqlite3.Connection, *, metadata_only: bool = False) -> str:
    """Stream a versioned snapshot fingerprint without Python row materialization.

    Metadata-only fences cover keys, claims, sizes and declared body digests;
    they deliberately do not certify retained body/proof bytes. Typed byte reads
    still verify those bytes, and conservative Search verifies authority on every
    query. Backup certification retains the default complete fingerprint.
    """
    schema = [
        tuple(row)
        for row in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]
    digest = hashlib.sha256()

    def put(value):
        encoded = _json(value).encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)

    put(["snapshot-v2", metadata_only, schema])
    excluded = {"body", "proof_bundle", "text_value"} if metadata_only else set()
    for kind, name, _, _ in schema:
        if kind != "table":
            continue
        columns = [
            row[1]
            for row in db.execute(
                "PRAGMA table_info(" + '"' + name.replace('"', '""') + '"' + ")"
            )
            if row[1] not in excluded
        ]
        quoted = '"' + name.replace('"', '""') + '"'
        fields = ",".join('"' + c.replace('"', '""') + '"' for c in columns)
        put([name, columns])
        for row in db.execute(f"SELECT {fields} FROM {quoted} ORDER BY {fields}"):
            put(
                [
                    {"bytes": base64.b64encode(v).decode("ascii")}
                    if isinstance(v, bytes)
                    else {"type": type(v).__name__, "value": v}
                    for v in row
                ]
            )
    return digest.hexdigest()


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
    core: sqlite3.Connection,
    context: sqlite3.Connection,
    *,
    metadata_only: bool = False,
) -> SnapshotToken:
    """Validate persisted authorities, including failures of semantic CHECK UDFs.

    Invalid stored UTF-8/JSON can make integrity_check raise SQLITE_ERROR instead
    of returning a corruption row. It is still failed authoritative validation,
    not a rejected incoming unit. Transient cancellation/locking or a denied
    capability is not evidence of storage corruption.
    """
    try:
        return _validate_pair(core, context, metadata_only=metadata_only)
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
    core: sqlite3.Connection,
    context: sqlite3.Connection,
    *,
    metadata_only: bool = False,
) -> SnapshotToken:
    identity = _identity(core, "core")
    if identity != _identity(context, "context"):
        raise CoordinationError("PAIR_IDENTITY", "core+context")
    for db, role in ((core, "core"), (context, "context")):
        if not metadata_only and [
            tuple(row) for row in db.execute("PRAGMA integrity_check")
        ] != [("ok",)]:
            raise CoordinationError("CORRUPTION", role)
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise CoordinationError("FOREIGN_KEY", role)
    # SQLite does not re-evaluate insertion triggers for an existing snapshot.
    from repo_catalog.adapters.sqlite.p1_core import validate_embedded_references

    validate_embedded_references(core)
    validate_dependencies(core, context)
    return SnapshotToken(
        *identity,
        _digest(core, metadata_only=metadata_only),
        _digest(context, metadata_only=metadata_only),
    )


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

    def identity(self, role: str):
        self._available()
        return _identity(self, role)

    def fingerprint(self, *, metadata_only: bool = False):
        self._available()
        return _digest(self, metadata_only=metadata_only)

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
    def __init__(
        self,
        directory: Path,
        *,
        read_limits: SnapshotReadLimits | None = None,
        metadata_only: bool = False,
    ):
        self.directory = Path(directory)
        self.read_limits = read_limits
        self.metadata_only = metadata_only

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
            if action == sqlite3.SQLITE_PRAGMA and (
                (_first in ("integrity_check", "foreign_key_check") and _second is None)
                or _first == "table_info"
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
            if (
                self.read_limits is not None
                and getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
            ):
                raise CoordinationError(
                    "QUERY_BUDGET", "snapshot", "SQLite VM step limit"
                ) from error
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
                        apply_snapshot_read_limits(db, self.read_limits)
                        self._guard_read(db)
                    token = validate_pair(
                        core, context, metadata_only=self.metadata_only
                    )
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
            if (
                self.read_limits is not None
                and getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
            ):
                raise CoordinationError(
                    "QUERY_BUDGET", "snapshot", "SQLite VM step limit"
                ) from error
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
                apply_snapshot_read_limits(core, self.read_limits)
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
            if (
                self.read_limits is not None
                and getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
            ):
                raise CoordinationError(
                    "QUERY_BUDGET", "snapshot", "SQLite VM step limit"
                ) from error
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
    """Durable finite request accounting, with mandatory loss-detecting checkpoints.

    Every mutation and its checkpoint commit together. A new connection, or any
    unknown same/other-connection write, verifies the actual accounting inventory
    before continuation. Normal steps update fixed-size counters/checksums in O(1)
    work; no Core ledger or authoritative success state is introduced.

    Acquisition units meter actual source/native/admission work. Operational
    durability bookkeeping is internal and does not recursively meter itself.
    Fresh/unknown-writer validation is a finite O(recorded work, attempts and
    progress) scan of accounting metadata only; it never reads source/body data.
    """

    _CHECKPOINT_SCOPE = '["work-ledger","checkpoint",1]'

    def __init__(
        self,
        db: sqlite3.Connection,
        *,
        repository_uuidv4: str | None = None,
        catalog_instance_uuidv4: str | None = None,
    ):
        self.db = db
        self._issued_permits: dict[int, WorkPermit] = {}
        self._validated = {}
        self._path = Path(db.execute("PRAGMA database_list").fetchone()[2])
        self._file_identity = self._stat_identity()
        self._ready()
        self.identity = _identity(db, "operational")
        repository, instance = self.identity
        if (repository_uuidv4 is not None and repository != repository_uuidv4) or (
            catalog_instance_uuidv4 is not None and instance != catalog_instance_uuidv4
        ):
            raise CoordinationError("STORE_IDENTITY", "operational")

    def store_identity(self):
        self._ready()
        if _identity(self.db, "operational") != self.identity:
            raise CoordinationError("STORE_IDENTITY", "operational")
        return self.identity

    def _stat_identity(self):
        try:
            stat = self._path.stat()
        except OSError as error:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request") from error
        return stat.st_dev, stat.st_ino

    def _ready(self):
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

    def _stamp(self):
        return self.db.execute("PRAGMA data_version").fetchone()[
            0
        ], self.db.total_changes

    @staticmethod
    def _digest_row(row):
        # An Operational consistency checksum, never a domain PK or provenance.
        return int.from_bytes(
            hashlib.sha256(_json(tuple(row)).encode()).digest(), "big"
        )

    @classmethod
    def _toggle(cls, checkpoint, field, *rows):
        value = int(checkpoint[field], 16)
        for row in rows:
            value ^= cls._digest_row(row)
        checkpoint[field] = f"{value:064x}"

    @staticmethod
    def _allocation_scope(attempt):
        return _json(
            {"attempt_uuidv4": attempt, "purpose": "processing-step-allocation"}
        )

    @staticmethod
    def _empty_checkpoint(scope, budgets):
        return {
            "version": 1,
            "scope_sha256": hashlib.sha256(scope.encode()).hexdigest(),
            "budgets": budgets,
            "attempt_count": 0,
            "attempt_xor": "0" * 64,
            "work_count": 0,
            "work_xor": "0" * 64,
            "usage": dict.fromkeys(NotesLimits.work_limits(), 0),
            "continuation_count": 0,
            "continuation_xor": "0" * 64,
        }

    def _save_checkpoint(self, request, checkpoint):
        cursor = self.db.execute(
            "UPDATE request_continuations SET cursor_json=? "
            "WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
            (_json(checkpoint), *request.values(), self._CHECKPOINT_SCOPE),
        )
        if cursor.rowcount != 1:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")

    def _check_inventory(self, request, scope, checkpoint):
        budget_rows = list(
            self.db.execute(
                "SELECT work_kind,finite_limit,spent_or_reserved FROM request_budgets "
                "WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                request.values(),
            )
        )
        budgets = {row[0]: row[1] for row in budget_rows}
        sql_usage = {row[0]: row[2] for row in budget_rows}
        actual = self._empty_checkpoint(scope, budgets)
        attempts = set()
        for row in self.db.execute(
            "SELECT attempt_uuidv4,continuation_json FROM acquisition_attempts "
            "WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            request.values(),
        ):
            attempts.add(row[0])
            actual["attempt_count"] += 1
            self._toggle(actual, "attempt_xor", row)
        for row in self.db.execute(
            "SELECT attempt_uuidv4,work_kind,work_coordinate,reserved,actual "
            "FROM work_accounting WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            request.values(),
        ):
            if row[0] not in attempts or row[1] not in actual["usage"]:
                raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
            actual["work_count"] += 1
            actual["usage"][row[1]] += row[3] if row[4] is None else row[4]
            self._toggle(actual, "work_xor", row)
        allocation_scopes = {self._allocation_scope(attempt) for attempt in attempts}
        found_allocations = set()
        for row in self.db.execute(
            "SELECT continuation_scope_json,cursor_json FROM request_continuations "
            "WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json<>?",
            (*request.values(), self._CHECKPOINT_SCOPE),
        ):
            actual["continuation_count"] += 1
            self._toggle(actual, "continuation_xor", row)
            if row[0] in allocation_scopes:
                found_allocations.add(row[0])
        if (
            _json(actual) != _json(checkpoint)
            or _json(sql_usage) != _json(actual["usage"])
            or set(budgets) != set(NotesLimits.work_limits())
            or found_allocations != allocation_scopes
        ):
            raise CoordinationError(
                "CONTINUATION_UNAVAILABLE",
                "request",
                "accounting inventory/checkpoint mismatch",
            )

    def _check(self, request, attempt=None, scope=None):
        row = self.db.execute(
            "SELECT state,request_scope_json FROM acquisition_requests WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            request.values(),
        ).fetchone()
        saved = self.db.execute(
            "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
            (*request.values(), self._CHECKPOINT_SCOPE),
        ).fetchone()
        if row is None or row[0] != "open" or saved is None:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
        try:
            checkpoint = json.loads(saved[0])
            if self._validated.get(request) != self._stamp():
                self._check_store_identity()
                self._check_inventory(request, row[1], checkpoint)
        except (KeyError, ValueError, TypeError, RecursionError) as error:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request") from error
        if scope is not None and _json(json.loads(row[1])) != _json(json.loads(scope)):
            raise CoordinationError("REQUEST_SCOPE", "request")
        if (
            attempt is not None
            and not self.db.execute(
                "SELECT 1 FROM acquisition_attempts WHERE request_origin_uuidv4=? AND request_uuidv4=? AND attempt_uuidv4=?",
                (*request.values(), attempt),
            ).fetchone()
        ):
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
        return checkpoint

    def _check_store_identity(self):
        if _identity(self.db, "operational") != self.identity:
            raise CoordinationError("STORE_IDENTITY", "operational")

    @contextmanager
    def _checked(self, request, attempt=None, *, scope=None, write=False):
        self._ready()
        # Even read validation takes the short write fence: its cached stamp
        # must describe the same snapshot and cannot race another writer commit.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            checkpoint = self._check(request, attempt, scope)
            yield checkpoint
            if write:
                self._save_checkpoint(request, checkpoint)
            stamp = self._stamp()  # Capture before releasing the write fence.
            if write:
                self.db.commit()
            else:
                self.db.rollback()
            self._validated[request] = stamp
        except BaseException:
            self._validated.pop(request, None)
            self.db.rollback()
            raise

    def validate_continuation(self, request, attempt_uuidv4=None, *, scope=None):
        with self._checked(request, attempt_uuidv4, scope=scope):
            pass

    def usage(self, request):
        with self._checked(request) as checkpoint:
            return dict(checkpoint["usage"])

    def new_request(self, request, scope, limits):
        if set(limits) != set(NotesLimits.work_limits()):
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
                "INSERT INTO request_budgets(request_origin_uuidv4,request_uuidv4,work_kind,finite_limit) VALUES(?,?,?,?)",
                [(*request.values(), kind, limit) for kind, limit in limits.items()],
            )
            self.db.execute(
                "INSERT INTO request_continuations VALUES(?,?,?,?)",
                (
                    *request.values(),
                    self._CHECKPOINT_SCOPE,
                    _json(self._empty_checkpoint(scope, limits)),
                ),
            )
            stamp = self._stamp()
            self.db.commit()
            self._validated[request] = stamp
        except BaseException:
            self._validated.pop(request, None)
            self.db.rollback()
            raise

    def _put_continuation(self, request, checkpoint, scope, value):
        old = self.db.execute(
            "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
            (*request.values(), scope),
        ).fetchone()
        if old is None:
            checkpoint["continuation_count"] += 1
        else:
            self._toggle(checkpoint, "continuation_xor", (scope, old[0]))
        self.db.execute(
            "INSERT INTO request_continuations VALUES(?,?,?,?) ON CONFLICT(request_origin_uuidv4,request_uuidv4,continuation_scope_json) DO UPDATE SET cursor_json=excluded.cursor_json",
            (*request.values(), scope, value),
        )
        self._toggle(checkpoint, "continuation_xor", (scope, value))

    def attempt(self, request, attempt_uuidv4, continuation="{}"):
        with self._checked(request, write=True) as checkpoint:
            self.db.execute(
                "INSERT INTO acquisition_attempts VALUES(?,?,?,?)",
                (*request.values(), attempt_uuidv4, continuation),
            )
            checkpoint["attempt_count"] += 1
            self._toggle(checkpoint, "attempt_xor", (attempt_uuidv4, continuation))
            self._put_continuation(
                request,
                checkpoint,
                self._allocation_scope(attempt_uuidv4),
                _json({"last_processing_step": 0}),
            )

    def increase_limit(self, request, work_kind, finite_limit):
        if type(finite_limit) is not int or not 0 <= finite_limit <= 2**63 - 1:
            raise ValueError("finite nonnegative signed int64 limit required")
        with self._checked(request, write=True) as checkpoint:
            cursor = self.db.execute(
                "UPDATE request_budgets SET finite_limit=? WHERE request_origin_uuidv4=? AND request_uuidv4=? AND work_kind=? AND finite_limit<?",
                (finite_limit, *request.values(), work_kind, finite_limit),
            )
            if cursor.rowcount != 1:
                raise CoordinationError("FINITE_INCREASE_REQUIRED", "request")
            checkpoint["budgets"][work_kind] = finite_limit

    def _insert_reservation(
        self, request, attempt, kind, coordinate, amount, checkpoint
    ):
        self.db.execute(
            "INSERT INTO work_accounting VALUES(?,?,?,?,?,?,NULL)",
            (*request.values(), attempt, kind, coordinate, amount),
        )
        checkpoint["work_count"] += 1
        checkpoint["usage"][kind] += amount
        self._toggle(checkpoint, "work_xor", (attempt, kind, coordinate, amount, None))

    def reserve(self, request, attempt_uuidv4, work_kind, work_coordinate, upper_bound):
        if type(upper_bound) is not int or not 0 <= upper_bound <= 2**63 - 1:
            raise ValueError("finite nonnegative upper bound required")
        with self._checked(request, attempt_uuidv4, write=True) as checkpoint:
            self._insert_reservation(
                request,
                attempt_uuidv4,
                work_kind,
                work_coordinate,
                upper_bound,
                checkpoint,
            )
            if work_coordinate.startswith("processing-step:"):
                suffix = work_coordinate.removeprefix("processing-step:")
                if suffix.isascii() and suffix.isdigit():
                    step = int(suffix)
                    if not 0 < step <= 2**63 - 1:
                        raise CoordinationError("ACCOUNTING_STATE", "request")
                    allocation_scope = self._allocation_scope(attempt_uuidv4)
                    row = self.db.execute(
                        "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? "
                        "AND request_uuidv4=? AND continuation_scope_json=?",
                        (*request.values(), allocation_scope),
                    ).fetchone()
                    if row is None:
                        raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
                    last = json.loads(row[0])["last_processing_step"]
                    self._put_continuation(
                        request,
                        checkpoint,
                        allocation_scope,
                        _json({"last_processing_step": max(last, step)}),
                    )
        return self._issue(
            WorkPermit(request, attempt_uuidv4, work_kind, work_coordinate, upper_bound)
        )

    def _issue(self, permit):
        self._issued_permits[id(permit)] = permit
        return permit

    def abandon(self, permit):
        self._check_permit(permit)
        del self._issued_permits[id(permit)]

    def _check_permit(self, permit):
        if self._issued_permits.get(id(permit)) is not permit:
            raise CoordinationError("PERMIT_ALREADY_SETTLED_OR_LOST", "request")

    def reserve_processing_step(self, request, attempt, kind, amount):
        if type(amount) is not int or not 0 <= amount <= 2**63 - 1:
            raise ValueError("finite nonnegative upper bound required")
        with self._checked(request, attempt, write=True) as checkpoint:
            allocation_scope = self._allocation_scope(attempt)
            row = self.db.execute(
                "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
                (*request.values(), allocation_scope),
            ).fetchone()
            if row is None:
                raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
            last = json.loads(row[0])["last_processing_step"]
            if type(last) is not int or not 0 <= last < 2**63 - 1:
                raise CoordinationError("ACCOUNTING_STATE", "request")
            coordinate = f"processing-step:{last + 1}"
            self._insert_reservation(
                request, attempt, kind, coordinate, amount, checkpoint
            )
            self._put_continuation(
                request,
                checkpoint,
                allocation_scope,
                _json({"last_processing_step": last + 1}),
            )
        return self._issue(WorkPermit(request, attempt, kind, coordinate, amount))

    def finish(self, permit, actual):
        self._check_permit(permit)
        if type(actual) is not int or not 0 <= actual <= permit.reserved:
            raise ValueError("actual work exceeds reserved bound")
        with self._checked(
            permit.request, permit.attempt_uuidv4, write=True
        ) as checkpoint:
            cursor = self.db.execute(
                "UPDATE work_accounting SET actual=? WHERE request_origin_uuidv4=? AND request_uuidv4=? AND attempt_uuidv4=? AND work_kind=? AND work_coordinate=? AND actual IS NULL AND reserved=?",
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
            checkpoint["usage"][permit.work_kind] += actual - permit.reserved
            row = (
                permit.attempt_uuidv4,
                permit.work_kind,
                permit.work_coordinate,
                permit.reserved,
            )
            self._toggle(checkpoint, "work_xor", (*row, None), (*row, actual))
        del self._issued_permits[id(permit)]

    def _progress_scope(self, scope):
        parsed = json.loads(scope)
        normalized = _json(parsed)
        if normalized == self._CHECKPOINT_SCOPE or (
            isinstance(parsed, dict)
            and parsed.get("purpose") == "processing-step-allocation"
        ):
            raise CoordinationError("PROGRESS_SCOPE", "request")
        return normalized

    def get_progress(self, request, scope):
        """Return decoded original progress, or None only for a genuine new slot."""
        scope = self._progress_scope(scope)
        with self._checked(request):
            row = self.db.execute(
                "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
                (*request.values(), scope),
            ).fetchone()
            return None if row is None else json.loads(row[0])

    def set_progress_once(self, request, scope, value):
        """Atomically preserve the first decoded JSON value for a semantic slot."""
        scope = self._progress_scope(scope)
        encoded = _json(value)
        with self._checked(request, write=True) as checkpoint:
            row = self.db.execute(
                "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
                (*request.values(), scope),
            ).fetchone()
            if row is not None:
                return json.loads(row[0])
            self._put_continuation(request, checkpoint, scope, encoded)
            return value


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
