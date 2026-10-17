"""Linux local Access snapshots, fresh inactive restore, and explicit Scope fork.

Trusted adapter infrastructure, not protection against the filesystem owner.
All transfer input is bounded and validated on private copies. SQLite Backup API
includes committed WAL; no live-file copy or in-place restore. No P7 imports.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from repo_catalog.adapters.sqlite import access_schema as schema
from repo_catalog.domain.access_backup import AccessBackupLimits, ScopeFork
from repo_catalog.domain.access_registry import AccessRegistryError, registration_time

FORMAT = "git-repo-db/access-backup-v1"
FILES = frozenset(("manifest.json", "manifest.sha256", "access.sqlite3"))
MAX_MANIFEST_BYTES = 16_384


def _error(code: str, message: str) -> AccessRegistryError:
    return AccessRegistryError(code, message)


def _encoded(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


class _Budget:
    def __init__(self, limits: AccessBackupLimits, cancelled: Callable[[], bool]):
        self.limits = limits
        self.cancelled = cancelled
        self.deadline = time.monotonic() + limits.timeout_seconds
        self.interrupted = None

    def check(self) -> None:
        if self.cancelled():
            raise _error("CANCELLED", "Access maintenance cancelled")
        if time.monotonic() >= self.deadline:
            raise _error("LIMIT", "Access maintenance deadline exceeded")

    def progress(self, *_args) -> None:
        self.check()

    @contextmanager
    def sql(self, db: sqlite3.Connection) -> Iterator[None]:
        def callback():
            try:
                self.check()
                return 0
            except AccessRegistryError as error:
                self.interrupted = error
                return 1

        self.check()
        db.set_progress_handler(callback, 1000)
        try:
            yield
        except sqlite3.Error:
            if self.interrupted is not None:
                raise self.interrupted from None
            raise
        finally:
            db.set_progress_handler(None, 0)


def _directory(path: Path, *, private: bool = False) -> int:
    """Pin every component; final directory must be owned and not externally writable."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & (0o077 if private else 0o022):
            raise _error("PATH", "owned private-write directory required")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _identity(info) -> tuple:
    return info.st_dev, info.st_ino


def _same_directory(path: Path, fd: int) -> None:
    current = _directory(path)
    try:
        if _identity(os.fstat(current)) != _identity(os.fstat(fd)):
            raise _error("PATH_CHANGED", "maintenance directory changed")
    finally:
        os.close(current)


def _regular(parent: int, name: str, maximum: int) -> int:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        os.close(fd)
        raise _error("PATH", "owned private regular input required")
    if not 0 < info.st_size <= maximum:
        os.close(fd)
        raise _error("LIMIT", "input size is outside the explicit bound")
    return fd


def _read(fd: int, maximum: int, budget: _Budget) -> bytes:
    chunks = []
    total = 0
    while True:
        budget.check()
        block = os.read(fd, min(65536, maximum + 1 - total))
        if not block:
            break
        chunks.append(block)
        total += len(block)
        if total > maximum:
            raise _error("LIMIT", "bounded input exceeded")
    return b"".join(chunks)


def _write(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _sync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish(parent_fd: int, stage: str, destination: str) -> None:
    """Atomic no-replace publication; no racy exists()+rename fallback."""
    libc = ctypes.CDLL(None, use_errno=True)
    if not hasattr(libc, "renameat2"):
        raise _error("PLATFORM", "atomic no-replace publication unavailable")
    fn = libc.renameat2
    fn.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    fn.restype = ctypes.c_int
    if fn(parent_fd, os.fsencode(stage), parent_fd, os.fsencode(destination), 1):
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise _error("EXISTS", "destination already exists")
        raise _error("PUBLICATION", "atomic no-replace publication failed")


@contextmanager
def _stage(destination: str | Path, budget: _Budget):
    target = Path(os.path.abspath(destination))
    parent = target.parent
    parent_fd = _directory(parent)
    stage = None
    stage_fd = None
    published = False
    try:
        if os.path.lexists(target):
            raise _error("EXISTS", "destination already exists")
        stage = Path(tempfile.mkdtemp(prefix=".access-stage-", dir=parent))
        stage_fd = _directory(stage, private=True)

        def publish():
            nonlocal published
            budget.check()
            _same_directory(parent, parent_fd)
            _same_directory(stage, stage_fd)
            for item in stage.iterdir():
                _sync_file(item)
            os.fsync(stage_fd)
            budget.check()
            _publish(parent_fd, stage.name, target.name)
            published = True
            try:
                os.fsync(parent_fd)
            except OSError:
                # The complete target may exist; do not delete it or report success.
                raise _error(
                    "PUBLICATION_UNCERTAIN",
                    "published target durability is indeterminate",
                ) from None

        yield stage, publish
    finally:
        if stage is not None and not published and stage_fd is not None:
            try:
                _same_directory(parent, parent_fd)
                _same_directory(stage, stage_fd)
                shutil.rmtree(stage)
            except (OSError, AccessRegistryError):
                pass  # Leave an unpromoted private stage; never delete another path.
        if stage_fd is not None:
            os.close(stage_fd)
        os.close(parent_fd)


def _counts(db: sqlite3.Connection, budget: _Budget) -> dict:
    result = {}
    total = 0
    for table in schema.TABLES:
        budget.check()
        count = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        total += count
        if total > budget.limits.max_rows:
            raise _error("LIMIT", "Access row limit exceeded")
        result[table] = count
    return result


def _validate(db: sqlite3.Connection, budget: _Budget) -> dict:
    page_bytes = (
        db.execute("PRAGMA page_size").fetchone()[0]
        * db.execute("PRAGMA page_count").fetchone()[0]
    )
    if page_bytes > budget.limits.max_bytes:
        raise _error("LIMIT", "Access snapshot size exceeded")
    # Reject hostile schema BEFORE enumerating its tables, CHECKs or functions.
    if schema.schema_rows(db) != schema.expected_schema():
        raise _error("FORMAT", "Access snapshot schema mismatch")
    counts = _counts(db, budget)
    schema.validate(db)
    return counts


@contextmanager
def _live(source: str | Path, budget: _Budget, *, writable=False):
    path = schema._path(source)
    schema.check_stop(path)
    token = schema.file_token(path)
    if writable:
        # Validate without a writable open; repeat under the later write snapshot.
        with _live(source, budget) as (_, ready_read):
            ready_read()
        schema.check_stop(path)
        if schema.file_token(path) != token:
            raise _error("PATH_CHANGED", "source replaced before writable open")
    db = schema._connect(path, writable=writable)
    try:
        with budget.sql(db):
            if writable:
                db.execute("PRAGMA synchronous=EXTRA")
            db.execute("BEGIN IMMEDIATE" if writable else "BEGIN")
            try:
                _validate(db, budget)
            except BaseException as error:
                if (
                    isinstance(error, AccessRegistryError) and error.code == "CORRUPT"
                ) or (
                    isinstance(error, sqlite3.Error)
                    and schema.is_corruption_error(error)
                ):
                    schema.persist_stop(path)
                raise
            if db.execute("PRAGMA journal_mode").fetchone() != ("wal",):
                raise _error("FORMAT", "live Access WAL format required")

            def ready():
                budget.check()
                schema.check_stop(path)
                if schema.file_token(path) != token:
                    raise _error("PATH_CHANGED", "source Access file replaced")

            ready()
            yield db, ready
            ready()
            db.commit()
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


def _manifest(value: bytes) -> dict:
    try:
        result = json.loads(value)
        if not isinstance(result, dict) or _encoded(result) != value:
            raise ValueError()
        if set(result) != {
            "format",
            "created_at_us",
            "store_format",
            "schema_version",
            "ddl_sha256",
            "store",
            "row_counts",
            "local_grants_included",
            "source_grants_omitted",
            "requires_local_reapproval",
            "domain_catalog_included",
        }:
            raise ValueError()
        registration_time(result["created_at_us"])
        if (
            result["format"] != FORMAT
            or result["store_format"] != schema.FORMAT
            or type(result["schema_version"]) is not int
            or result["schema_version"] != schema.SCHEMA_VERSION
            or result["ddl_sha256"] != schema.fingerprint()
        ):
            raise ValueError()
        if (
            result["local_grants_included"] is not False
            or result["requires_local_reapproval"] is not True
            or result["domain_catalog_included"] is not False
        ):
            raise ValueError()
        counts = result["row_counts"]
        if (
            not isinstance(counts, dict)
            or set(counts) != set(schema.TABLES)
            or any(type(n) is not int or n < 0 for n in counts.values())
            or counts["local_access_grants"] != 0
        ):
            raise ValueError()
        n = result["source_grants_omitted"]
        if type(n) is not int or not 0 <= n < 2**63:
            raise ValueError()
        store = result["store"]
        if (
            not isinstance(store, dict)
            or set(store) != {"path", "bytes", "sha256"}
            or store["path"] != "access.sqlite3"
        ):
            raise ValueError()
        if (
            type(store["bytes"]) is not int
            or store["bytes"] <= 0
            or not isinstance(store["sha256"], str)
            or len(store["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in store["sha256"])
        ):
            raise ValueError()
        return result
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise _error("BACKUP_FORMAT", "invalid Access backup manifest") from None


def _hash_file(path: Path, budget: _Budget) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while block := stream.read(65536):
            budget.check()
            total += len(block)
            if total > budget.limits.max_bytes:
                raise _error("LIMIT", "backup file too large")
            digest.update(block)
    return total, digest.hexdigest()


def _load_bundle(bundle: str | Path, output: Path, budget: _Budget) -> dict:
    """Copy exact hashed bytes once; only the private, sidecar-free copy reaches SQLite."""
    root = Path(os.path.abspath(bundle))
    root_fd = _directory(root, private=True)
    fds = []
    try:
        if set(os.listdir(root_fd)) != FILES:
            raise _error("BACKUP_FORMAT", "unexpected or missing backup member")
        for name, bound in (
            ("manifest.json", MAX_MANIFEST_BYTES),
            ("manifest.sha256", 65),
        ):
            fds.append(_regular(root_fd, name, bound))
        manifest_bytes = _read(fds[0], MAX_MANIFEST_BYTES, budget)
        digest_bytes = _read(fds[1], 65, budget)
        if (
            digest_bytes
            != hashlib.sha256(manifest_bytes).hexdigest().encode("ascii") + b"\n"
        ):
            raise _error("BACKUP_HASH", "manifest digest mismatch")
        manifest = _manifest(manifest_bytes)
        expected = manifest["store"]
        if (
            expected["bytes"] > budget.limits.max_bytes
            or sum(manifest["row_counts"].values()) > budget.limits.max_rows
        ):
            raise _error("LIMIT", "declared backup exceeds limits")
        fd = _regular(root_fd, "access.sqlite3", budget.limits.max_bytes)
        fds.append(fd)
        before = os.fstat(fd)
        digest = hashlib.sha256()
        total = 0
        out_fd = os.open(
            output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(out_fd, "wb") as stream:
            while block := os.read(fd, 65536):
                budget.check()
                total += len(block)
                if total > expected["bytes"]:
                    raise _error("BACKUP_HASH", "backup length mismatch")
                digest.update(block)
                stream.write(block)
            stream.flush()
            os.fsync(stream.fileno())
        after = os.fstat(fd)
        if (
            total != expected["bytes"]
            or digest.hexdigest() != expected["sha256"]
            or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            raise _error("BACKUP_HASH", "backup content changed or hash mismatch")
        _same_directory(root, root_fd)
        # Never trust executable schema or sender grants, even with a correct hash.
        db = schema._connect(output, writable=False)
        try:
            with budget.sql(db):
                db.execute("BEGIN")
                counts = _validate(db, budget)
                if db.execute("PRAGMA journal_mode").fetchone() != ("delete",):
                    raise _error(
                        "BACKUP_FORMAT", "standalone DELETE-journal snapshot required"
                    )
                if counts != manifest["row_counts"]:
                    raise _error("BACKUP_FORMAT", "snapshot count mismatch")
                db.rollback()
        finally:
            db.close()
        return manifest
    finally:
        for fd in fds:
            os.close(fd)
        os.close(root_fd)


class AccessBackup:
    """One explicit Access store; no domain-catalog pairing, activation or migration."""

    def __init__(
        self,
        limits: AccessBackupLimits = AccessBackupLimits(),
        *,
        cancelled: Callable[[], bool] = lambda: False,
    ):
        if type(limits) is not AccessBackupLimits or not callable(cancelled):
            raise _error("TYPE", "typed limits and cancellation callback required")
        self.limits = AccessBackupLimits(
            limits.max_bytes, limits.max_rows, limits.timeout_seconds
        )
        self.cancelled = cancelled

    def _budget(self) -> _Budget:
        schema.require_runtime()
        if sys.platform != "linux":
            raise _error("PLATFORM", "Linux no-replace filesystem adapter required")
        budget = _Budget(self.limits, self.cancelled)
        budget.check()
        return budget

    def backup(self, source: str | Path, destination: str | Path) -> dict:
        budget = self._budget()
        with _stage(destination, budget) as (stage, publish):
            output = stage / "access.sqlite3"
            _write(output, b"")
            with _live(source, budget) as (src, ready):
                omitted = src.execute(
                    "SELECT count(*) FROM local_access_grants"
                ).fetchone()[0]
                dst = schema._connect(output, writable=True)
                try:
                    src.backup(dst, pages=128, progress=budget.progress, sleep=0.01)
                    with budget.sql(dst):
                        _validate(dst, budget)
                        dst.execute("PRAGMA journal_mode=DELETE")
                        dst.execute("DELETE FROM local_access_grants")
                        dst.execute(
                            "VACUUM"
                        )  # Private copy only; omit freed consent bytes, too.
                        counts = _validate(dst, budget)
                finally:
                    dst.close()
                ready()
            length, digest = _hash_file(output, budget)
            manifest = {
                "format": FORMAT,
                "created_at_us": registration_time(time.time_ns() // 1000),
                "store_format": schema.FORMAT,
                "schema_version": schema.SCHEMA_VERSION,
                "ddl_sha256": schema.fingerprint(),
                "store": {"path": "access.sqlite3", "bytes": length, "sha256": digest},
                "row_counts": counts,
                "local_grants_included": False,
                "source_grants_omitted": omitted,
                "requires_local_reapproval": True,
                "domain_catalog_included": False,
            }
            encoded = _encoded(manifest)
            _manifest(encoded)
            _write(stage / "manifest.json", encoded)
            _write(
                stage / "manifest.sha256",
                hashlib.sha256(encoded).hexdigest().encode("ascii") + b"\n",
            )
            ready()  # Still checks original file identity and stop after hashing.
            publish()
        return manifest

    def inspect(self, bundle: str | Path) -> dict:
        budget = self._budget()
        with tempfile.TemporaryDirectory(prefix="access-inspect-") as directory:
            return _load_bundle(bundle, Path(directory) / "access.sqlite3", budget)

    def restore(self, bundle: str | Path, destination: str | Path) -> dict:
        budget = self._budget()
        with _stage(destination, budget) as (stage, publish):
            output = stage / "access.sqlite3"
            manifest = _load_bundle(bundle, output, budget)
            db = schema._connect(output, writable=True)
            try:
                with budget.sql(db):
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("DELETE FROM local_access_grants")
                    db.execute("UPDATE scope_locator_controls SET enabled=0")
                    counts = _validate(db, budget)
                    if counts != manifest["row_counts"]:
                        raise _error(
                            "CORRUPT",
                            "restoration changed registration/configuration counts",
                        )
                    db.commit()
                    if db.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
                        raise _error("CAPABILITY", "restored WAL unavailable")
                    db.execute("PRAGMA synchronous=EXTRA")
                    _validate(db, budget)
            finally:
                db.close()
            if set(p.name for p in stage.iterdir()) != {"access.sqlite3"}:
                raise _error("RESTORE", "restored database has unresolved sidecars")
            receipt = {
                "format": "git-repo-db/access-restore-v1",
                "mode": "continuity",
                "created_at_us": registration_time(time.time_ns() // 1000),
                "backup_store_sha256": manifest["store"]["sha256"],
                "row_counts": counts,
                "local_grants": 0,
                "enabled_routes": 0,
                "scope_uuids_preserved": True,
                "registration_times_preserved": True,
                "requires_local_reapproval": True,
                "domain_catalog_included": False,
            }
            _write(stage / "restore.json", _encoded(receipt))
            publish()
        return receipt

    def fork_scope(self, source: str | Path, request: ScopeFork) -> dict:
        if type(request) is not ScopeFork:
            raise _error("TYPE", "typed fork request required")
        request = ScopeFork(
            request.source_scope_uuidv4, request.target_scope, request.registration
        )
        budget = self._budget()
        old = request.source_scope_uuidv4
        new = request.target_scope.scope_uuidv4
        with _live(source, budget, writable=True) as (db, ready):
            if not db.execute(
                "SELECT 1 FROM access_scopes WHERE scope_uuidv4=?", (old,)
            ).fetchone():
                raise _error("NOT_FOUND", "source Scope is absent")
            if db.execute(
                "SELECT 1 FROM access_scopes WHERE scope_uuidv4=?", (new,)
            ).fetchone():
                raise _error("EXISTS", "fork Scope already exists")
            before = _counts(db, budget)
            db.execute(
                "INSERT INTO access_scopes VALUES(?,?)",
                (new, request.target_scope.display_name),
            )
            db.execute(
                "INSERT INTO scope_locators VALUES(?,?,?)", request.registration.key
            )
            db.execute(
                "INSERT INTO scope_locator_controls VALUES(?,?,?,0)",
                request.registration.key,
            )
            # Copy CURRENT intended settings only, all disabled; never clone prior grants/history.
            for table, columns in (
                ("scope_execution_contexts", "execution_context_json,0"),
                ("repository_locators", "locator_text,repository_uuidv4,0"),
                ("connection_configurations", "configuration_name,options_json,0"),
                ("locator_connections", "locator_text,configuration_name,purpose,0"),
            ):
                db.execute(
                    f"INSERT INTO {table} SELECT ?,{columns} FROM {table} WHERE scope_uuidv4=?",
                    (new, old),
                )
            db.execute(
                "INSERT INTO repository_access_preferences SELECT repository_uuidv4,?,purpose,locator_text,configuration_name FROM repository_access_preferences WHERE scope_uuidv4=?",
                (new, old),
            )
            after = _validate(db, budget)
            ready()
        return {
            "format": "git-repo-db/access-fork-v1",
            "source_scope_uuidv4": old,
            "target_scope_uuidv4": new,
            "registered_at_us": request.registration.registered_at_us,
            "original_history_rewritten": False,
            "repository_uuids_preserved": True,
            "requires_local_reapproval": True,
            "rows_added": {key: after[key] - before[key] for key in before},
        }
