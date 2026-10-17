"""Independent, opt-in Access registry format; never imported by P1 or the CLI.

Factory connections are trusted infrastructure. Public callers use AccessRegistry.
Only owned POSIX regular files in owned non-writable-by-others directories are
supported. This is not protection against the filesystem owner or a backup engine.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import time
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    AccessScope,
    ScopeLocatorRegistration,
    display_label,
    scope_locator,
    scope_uuid,
)

FORMAT = "repo-catalog/access-registry-1"
SCHEMA_VERSION = 1
MIN_SQLITE = (3, 51, 3)
TABLES = (
    "access_identity",
    "access_scopes",
    "scope_locator_controls",
    "scope_locators",
)


def schema_sql() -> str:
    return (
        files("repo_catalog.adapters.sqlite")
        .joinpath("access_ddl", "registry.sql")
        .read_text(encoding="utf-8")
    )


def fingerprint() -> str:
    return hashlib.sha256(schema_sql().encode("utf-8")).hexdigest()


def require_runtime() -> None:
    if sqlite3.sqlite_version_info < MIN_SQLITE or sqlite3.threadsafety == 0:
        raise AccessRegistryError(
            "SQLITE_RUNTIME", "SQLite >=3.51.3 with mutexes required"
        )
    if os.name != "posix":
        raise AccessRegistryError("PLATFORM", "POSIX local filesystem adapter required")


def is_corruption_error(error: BaseException) -> bool:
    """Recognize damaged stored values in the adapter's own bounded SQL reads.

    CPython reports invalid stored UTF-8 as OperationalError without SQLITE_CORRUPT.
    No user-supplied SQL expression participates in these reads.
    """
    code = getattr(error, "sqlite_errorcode", 0) & 255
    return code in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB) or (
        isinstance(error, sqlite3.OperationalError)
        and str(error).startswith("Could not decode to UTF-8 column")
    )


def register_functions(db: sqlite3.Connection) -> None:
    def predicate(validate):
        def check(value):
            try:
                validate(value)
                return 1
            except (ValueError, TypeError, OverflowError):
                return 0

        return check

    for name, validator in (
        ("access_uuid4", scope_uuid),
        ("access_label", display_label),
        ("access_scope_uri", scope_locator),
    ):
        db.create_function(name, 1, predicate(validator), deterministic=True)


def schema_rows(db: sqlite3.Connection) -> tuple[tuple, ...]:
    return tuple(
        db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    )


@lru_cache(maxsize=1)
def expected_schema() -> tuple[tuple, ...]:
    db = sqlite3.connect(":memory:", cached_statements=0)
    try:
        register_functions(db)
        db.executescript(schema_sql())
        return schema_rows(db)
    finally:
        db.close()


def validate(db: sqlite3.Connection) -> None:
    """Validate actual stored rows, not just the file's self-reported digest."""
    if schema_rows(db) != expected_schema():
        raise AccessRegistryError("FORMAT", "Access registry schema mismatch")
    expected = [("access", FORMAT, SCHEMA_VERSION, fingerprint())]
    if db.execute("SELECT * FROM access_identity").fetchall() != expected:
        raise AccessRegistryError("FORMAT", "Access registry identity mismatch")
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise AccessRegistryError("CORRUPT", "Access registry integrity failure")
    if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise AccessRegistryError("CORRUPT", "Access registry reference failure")
    try:
        for row in db.execute("SELECT scope_uuidv4,display_name FROM access_scopes"):
            AccessScope(*row)
        for row in db.execute("SELECT * FROM scope_locators"):
            ScopeLocatorRegistration(*row)
        for row in db.execute("SELECT enabled FROM scope_locator_controls"):
            if type(row[0]) is not int or row[0] not in (0, 1):
                raise AccessRegistryError("CORRUPT", "invalid route control")
    except (ValueError, UnicodeError):
        raise AccessRegistryError("CORRUPT", "invalid stored Access value") from None


def _path(value: str | Path) -> Path:
    path = Path(os.path.abspath(value))
    parent = path.parent
    try:
        info = parent.stat()
        if parent.resolve(strict=True) != parent:
            raise AccessRegistryError("PATH", "symlinked store parents are unsupported")
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o022
        ):
            raise AccessRegistryError(
                "PATH", "owned, private-write store directory required"
            )
    except OSError:
        raise AccessRegistryError("PATH", "store directory is unavailable") from None
    return path


def file_token(path: Path) -> tuple[int, int]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise AccessRegistryError("MISSING", "Access registry does not exist") from None
    except OSError:
        raise AccessRegistryError(
            "PATH", "Access registry cannot be inspected"
        ) from None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise AccessRegistryError(
            "PATH", "owned mode-0600 unaliased regular file required"
        )
    return info.st_dev, info.st_ino


def stop_path(path: Path) -> Path:
    return path.with_name(path.name + ".access-stop.json")


def check_stop(path: Path) -> None:
    if os.path.lexists(stop_path(path)):
        raise AccessRegistryError("STOPPED", "Access-only diagnostic stop is present")


def persist_stop(path: Path) -> None:
    """Publish only a separate diagnostic; never write a suspect database."""
    body = (
        json.dumps(
            {
                "format": "repo-catalog/access-registry-stop-1",
                "reason": "detected-access-corruption",
                "recorded_at_us": time.time_ns() // 1000,
            },
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    try:
        fd = os.open(
            stop_path(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
    except FileExistsError:
        return
    except OSError:
        raise AccessRegistryError(
            "STOP_PERSIST_FAILED", "cannot publish Access stop"
        ) from None
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(path.parent)
    except OSError:
        raise AccessRegistryError(
            "STOP_PERSIST_FAILED", "cannot persist Access stop"
        ) from None


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _connect(path: Path, *, writable: bool) -> sqlite3.Connection:
    db = sqlite3.connect(
        path.as_uri() + ("?mode=rw" if writable else "?mode=ro"),
        uri=True,
        isolation_level=None,
        cached_statements=0,
        timeout=3.0,
    )
    try:
        db.enable_load_extension(False)
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
        register_functions(db)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA recursive_triggers=ON")
        if not writable:
            db.execute("PRAGMA query_only=ON")
        for pragma in ("foreign_keys", "recursive_triggers"):
            if db.execute(f"PRAGMA {pragma}").fetchone() != (1,):
                raise AccessRegistryError(
                    "CAPABILITY", "required SQLite protection missing"
                )
        return db
    except BaseException:
        db.close()
        raise


def _validate_snapshot(db: sqlite3.Connection) -> None:
    db.execute("BEGIN")
    try:
        validate(db)
        if db.execute("PRAGMA journal_mode").fetchone() != ("wal",):
            raise AccessRegistryError("FORMAT", "Access registry WAL mode required")
        db.commit()
    except BaseException:
        db.rollback()
        raise


def initialize(path: str | Path) -> None:
    """Explicit exclusive creation. Failure never permits overwriting the target."""
    require_runtime()
    target = _path(path)
    check_stop(target)
    for suffix in ("-wal", "-shm", "-journal"):
        if os.path.lexists(str(target) + suffix):
            raise AccessRegistryError(
                "PATH", "existing database sidecar prevents creation"
            )
    try:
        fd = os.open(target, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise AccessRegistryError("EXISTS", "Access target already exists") from None
    os.close(fd)
    db = _connect(target, writable=True)
    try:
        if db.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
            raise AccessRegistryError("CAPABILITY", "WAL unavailable")
        db.execute("PRAGMA synchronous=EXTRA")
        db.executescript("BEGIN IMMEDIATE;\n" + schema_sql())
        db.execute(
            "INSERT INTO access_identity VALUES(?,?,?,?)",
            ("access", FORMAT, SCHEMA_VERSION, fingerprint()),
        )
        db.commit()
        _validate_snapshot(db)
    except BaseException:
        if db.in_transaction:
            db.rollback()
        # Preserve the new incomplete target for diagnostics; never auto-recreate.
        raise
    finally:
        db.close()
    _fsync_directory(target.parent)


def open_checked(
    path: str | Path, *, writable: bool = False
) -> tuple[sqlite3.Connection, Path]:
    """Trusted factory, with read-only format validation before a writable open."""
    require_runtime()
    if type(writable) is not bool:
        raise AccessRegistryError("TYPE", "writable must be boolean")
    target = _path(path)
    check_stop(target)
    original = file_token(target)
    db = None
    try:
        db = _connect(target, writable=False)
        _validate_snapshot(db)
        if writable:
            db.close()
            db = None
            if file_token(target) != original:
                raise AccessRegistryError(
                    "PATH_CHANGED", "Access file replaced during open"
                )
            db = _connect(target, writable=True)
            _validate_snapshot(db)
            db.execute("PRAGMA synchronous=EXTRA")
        if file_token(target) != original:
            raise AccessRegistryError(
                "PATH_CHANGED", "Access file replaced during open"
            )
        check_stop(target)
        return db, target
    except BaseException as error:
        if db is not None:
            db.close()
        if isinstance(error, AccessRegistryError) and error.code == "CORRUPT":
            persist_stop(target)
        if isinstance(error, sqlite3.DatabaseError):
            if is_corruption_error(error):
                persist_stop(target)
                raise AccessRegistryError(
                    "CORRUPT", "damaged Access database"
                ) from None
            raise AccessRegistryError("SQLITE", "Access database open failed") from None
        raise
