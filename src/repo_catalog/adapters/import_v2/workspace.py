"""Import-owned durable scratch database, attached only for import/finalization.

The ordinary catalog never depends on this file after successful finalization.
The attachment path is fixed relative to the catalog, not taken from source data.
Both databases use on-disk rollback journals and one connection/transaction so a
committed target batch cannot be separated from its mapping/progress receipt.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from repo_catalog.adapters.sqlite.schema import DDL_SHA256

from .common import (
    ConversionError,
    canonical,
    fsync_directory,
    require_local_filesystem,
)

SCHEMA = "import_workspace"
FORMAT = "repo-catalog/import-workspace"
VERSION = 2
TABLES = frozenset(
    {
        "conversion_sources",
        "conversion_runs",
        "conversion_batches",
        "legacy_records",
        "legacy_values",
        "id_mappings",
        "validation_results",
        "reanalysis_runs",
    }
)


def schema_sql():
    return (
        files("repo_catalog").joinpath("resources/import_v2/workspace.sql").read_text()
    )


DDL_DIGEST = hashlib.sha256(schema_sql().encode()).digest()


def path_for(catalog):
    catalog = Path(catalog)
    suffix = ".part" if catalog.name.endswith(".part") else ""
    return catalog.parent / "import-v2" / ("workspace.sqlite3" + suffix)


def regular(path):
    """Reject aliases before SQLite can open/write a file or replay a journal."""
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ConversionError("IMPORT_WORKSPACE_ALIAS")
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ConversionError("IMPORT_WORKSPACE_MISSING_OR_NOT_REGULAR")
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if os.path.lexists(sidecar) and (
            sidecar.is_symlink()
            or not sidecar.is_file()
            or sidecar.stat().st_nlink != 1
        ):
            raise ConversionError("IMPORT_WORKSPACE_SIDECAR_ALIAS")
    return path


def _fingerprint(db, schema):
    rows = db.execute(
        f"SELECT type,name,tbl_name,sql FROM {schema}.sqlite_schema ORDER BY type,name"
    )
    return hashlib.sha256(canonical([tuple(row) for row in rows]).encode()).digest()


@lru_cache(maxsize=1)
def expected_fingerprint():
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(schema_sql())
        return _fingerprint(db, "main")
    finally:
        db.close()


def has_attachment(db):
    return any(row[1] == SCHEMA for row in db.execute("PRAGMA database_list"))


def initialize(db):
    """Install only workspace objects within the caller's initial transaction."""
    pending = ""
    for line in schema_sql().splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            statement = re.sub(
                r"\bCREATE (TABLE|TRIGGER|INDEX) (\w+)",
                rf"CREATE \1 {SCHEMA}.\2",
                pending,
                count=1,
            )
            db.execute(statement)
            pending = ""
    if pending.strip():
        raise ConversionError("IMPORT_WORKSPACE_SCHEMA_INCOMPLETE")
    target = db.execute(
        "SELECT db_instance_id,ddl_sha256 FROM main.database_identity WHERE singleton=1"
    ).fetchone()
    if target is None:
        raise ConversionError("IMPORT_WORKSPACE_TARGET_MISSING")
    db.execute(
        "INSERT INTO import_workspace.import_workspace_identity VALUES(1,?,?,?,?,?)",
        (FORMAT, VERSION, target[0], target[1], DDL_DIGEST),
    )


def verify(db):
    """Fail closed on foreign/stale workspace, changed schema or broken ledger FK."""
    if not has_attachment(db):
        raise ConversionError("IMPORT_WORKSPACE_REQUIRED")
    try:
        rows = db.execute(
            "SELECT singleton,format_id,schema_version,target_db_instance_id,"
            "target_ddl_sha256,workspace_ddl_sha256 FROM import_workspace.import_workspace_identity"
        ).fetchall()
        target = db.execute(
            "SELECT db_instance_id,ddl_sha256 FROM main.database_identity WHERE singleton=1"
        ).fetchone()
        if (
            target is None
            or target[1] != DDL_SHA256
            or len(rows) != 1
            or tuple(rows[0]) != (1, FORMAT, VERSION, target[0], DDL_SHA256, DDL_DIGEST)
            or _fingerprint(db, SCHEMA) != expected_fingerprint()
            or any(
                row[0] in TABLES | {"import_workspace_identity"}
                for row in db.execute(
                    "SELECT name FROM main.sqlite_schema WHERE type='table'"
                )
            )
        ):
            raise ConversionError("IMPORT_WORKSPACE_IDENTITY_MISMATCH")
        if db.execute("PRAGMA import_workspace.foreign_key_check").fetchall() or [
            row[0] for row in db.execute("PRAGMA import_workspace.quick_check")
        ] != ["ok"]:
            raise ConversionError("IMPORT_WORKSPACE_INTEGRITY_FAILURE")
    except sqlite3.Error as exc:
        raise ConversionError("IMPORT_WORKSPACE_INVALID") from exc


def attach(db, catalog, *, creating=False):
    """Authorize exactly this regular local file, before generic ATTACH is denied."""
    if db.in_transaction or has_attachment(db):
        raise ConversionError("IMPORT_WORKSPACE_CONNECTION_BUSY")
    catalog = regular(catalog)
    work = regular(path_for(catalog))
    require_local_filesystem(catalog.parent)
    require_local_filesystem(work.parent)
    if catalog.stat().st_dev != work.stat().st_dev or os.path.samefile(catalog, work):
        raise ConversionError("IMPORT_WORKSPACE_STORAGE_MISMATCH")
    if db.execute("PRAGMA main.journal_mode").fetchone()[0] != "delete":
        raise ConversionError("IMPORT_WORKSPACE_REQUIRES_DELETE_JOURNAL")
    # A missing workspace must never be silently created by ATTACH.
    db.execute("ATTACH DATABASE ? AS import_workspace", (work.as_uri() + "?mode=rw",))
    try:
        if db.execute("PRAGMA import_workspace.journal_mode").fetchone()[0] != "delete":
            raise ConversionError("IMPORT_WORKSPACE_REQUIRES_DELETE_JOURNAL")
        db.execute("PRAGMA main.synchronous=EXTRA")
        db.execute("PRAGMA import_workspace.synchronous=EXTRA")
        if not creating:
            verify(db)
    except BaseException:
        db.execute("DETACH DATABASE import_workspace")
        raise
    return work


def check_existing_attachment(db, catalog):
    """An existing attachment is not permission to bypass path/durability checks."""
    catalog = regular(catalog)
    work = regular(path_for(catalog))
    paths = {row[1]: row[2] for row in db.execute("PRAGMA database_list")}
    if (
        not paths.get("main")
        or not paths.get(SCHEMA)
        or not os.path.samefile(paths["main"], catalog)
        or not os.path.samefile(paths[SCHEMA], work)
        or catalog.stat().st_dev != work.stat().st_dev
    ):
        raise ConversionError("IMPORT_WORKSPACE_STORAGE_MISMATCH")
    for schema in ("main", SCHEMA):
        if db.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0] != "delete":
            raise ConversionError("IMPORT_WORKSPACE_REQUIRES_DELETE_JOURNAL")
        if db.execute(f"PRAGMA {schema}.synchronous").fetchone()[0] != 3:
            raise ConversionError("IMPORT_WORKSPACE_REQUIRES_EXTRA_SYNC")


def discard_pending_initialization(catalog):
    """Discard only unpublished initial files, never a published catalog pair."""
    catalog = Path(catalog)
    if os.path.lexists(catalog):
        raise ConversionError("IMPORT_WORKSPACE_INITIALIZATION_CONFLICT")
    candidates = []
    for base in (Path(str(catalog) + ".part"), Path(str(path_for(catalog)) + ".part")):
        for suffix in ("", "-journal", "-wal", "-shm"):
            candidate = Path(str(base) + suffix)
            if os.path.lexists(candidate):
                regular(candidate)
                candidates.append(candidate)
    # Validate every candidate before deleting any; source aliases fail closed.
    for candidate in candidates:
        candidate.unlink()


@contextmanager
def attached(db, catalog):
    """An explicit finalization scope; normal readers never open workspace files."""
    existing = has_attachment(db)
    if existing:
        check_existing_attachment(db, catalog)
        verify(db)
    else:
        attach(db, catalog)
    try:
        yield path_for(catalog)
    finally:
        if not existing:
            db.execute("DETACH DATABASE import_workspace")


def recover_initialization(catalog):
    """Complete publication after catalog rename but before workspace rename."""
    catalog = Path(catalog)
    work = path_for(catalog)
    pending = Path(str(work) + ".part")
    if work.exists():
        if os.path.lexists(pending):
            raise ConversionError("IMPORT_WORKSPACE_INITIALIZATION_CONFLICT")
        return
    if not os.path.lexists(pending):
        raise ConversionError("IMPORT_WORKSPACE_MISSING_OR_NOT_REGULAR")
    regular(catalog)
    regular(pending)
    # Check binding/schema in a read-only, query-only connection before rename.
    db = sqlite3.connect(catalog.as_uri() + "?mode=ro", uri=True, isolation_level=None)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute(
            "ATTACH DATABASE ? AS import_workspace", (pending.as_uri() + "?mode=ro",)
        )
        verify(db)
    finally:
        db.close()
    pending.rename(work)
    fsync_directory(work.parent)
