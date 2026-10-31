"""Core snapshots and catalog-wide stop fences, without optional store implementations.

Cooperating POSIX processes share permanent file gates. These primitives preserve
existing catalog-stop and completion algorithms; they are not a recovery engine.
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
from repo_catalog.domain.p1_coordination import CoordinationError


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
    on_steps: Callable[[int], bool] | None = None

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
        shared_limit = limits.on_steps is not None and limits.on_steps(100)
        return remaining < 0 or shared_limit

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

    def close(self):
        return self._run(self._cursor.close)

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

    def __init__(self, db, running, on_error, *, directory=None):
        self._directory = None if directory is None else Path(directory).resolve()
        self._db = db
        self._running, self._active = running, True
        self._on_error = on_error

    def _available(self):
        if not self._active:
            raise CoordinationError("SNAPSHOT_EXPIRED", "read")
        self._running()

    @property
    def catalog_directory(self):
        """Actual coordinator owner; unrelated caller paths cannot route a stop."""
        self._available()
        if self._directory is None:
            raise CoordinationError("SNAPSHOT_OWNER", "read", "unbound catalog")
        return self._directory

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


class CoreCoordinator:
    """Core-only pinned reads with shared persistent stop and completion fencing."""

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
        self.last_read_costs_ns: dict[str, int] = {}

    def _open(self, role: str):
        if role != "core":
            raise CoordinationError("AUTHORITY_UNAVAILABLE", role)
        path = self.directory / "core.sqlite3"
        if not path.is_file():
            raise CoordinationError("AUTHORITY_UNAVAILABLE", "core")
        try:
            return connect(path, "core")
        except Exception as error:
            self._record_corruption(error)
            raise

    def _check_running(self):
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoordinationError("RECOVERY_REQUIRED", "catalog")

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
                read = ReadSnapshot(
                    core,
                    self._check_running,
                    self._record_corruption,
                    directory=self.directory,
                )
                yield read
            finally:
                read._active = False
                core.set_authorizer(None)
                core.rollback()
