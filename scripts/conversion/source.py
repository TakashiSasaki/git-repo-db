import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from scripts.schema_audit import schema_inventory

from .common import (
    DESIGN,
    ROOT,
    ConversionError,
    canonical,
    digest,
    fsync_directory,
    require_local_filesystem,
    stat_identity,
)


def check_file(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file():
        raise ConversionError("SOURCE_NOT_REGULAR")
    require_local_filesystem(path)
    if any(
        os.path.lexists(str(path) + suffix) for suffix in ("-wal", "-shm", "-journal")
    ):
        raise ConversionError("SOURCE_NOT_SEALED")
    return path


def file_fingerprint(path):
    before = stat_identity(path)
    h = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            h.update(block)
    if stat_identity(path) != before:
        raise ConversionError("SOURCE_CHANGED")
    return {"stat": before, "sha256": h.hexdigest()}


@contextmanager
def readonly(path):
    path = check_file(path)
    db = sqlite3.connect(
        path.as_uri() + "?mode=ro&immutable=1", uri=True, isolation_level=None
    )
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("PRAGMA trusted_schema=OFF")
    db.execute("PRAGMA temp_store=MEMORY")
    db.enable_load_extension(False)
    # Defense in depth beyond immutable VFS flags; no attaching a writable DB.
    allowed = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
    db.set_authorizer(
        lambda action, *args: (
            sqlite3.SQLITE_OK
            if action in allowed
            or (
                action == sqlite3.SQLITE_PRAGMA
                and args[0]
                in {
                    "table_xinfo",
                    "index_list",
                    "index_xinfo",
                    "foreign_key_list",
                    "foreign_key_check",
                    "integrity_check",
                    "encoding",
                }
            )
            else sqlite3.SQLITE_DENY
        )
    )
    try:
        yield db
    finally:
        db.close()


def identify(db):
    # Audit inventory intentionally omits views/internal tables; do not silently
    # accept extra layouts (including derived FTS/ANALYZE structures) in P2.
    if db.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='view' OR (type='table' AND name LIKE 'sqlite_%')"
    ).fetchone():
        raise ConversionError("SOURCE_SCHEMA_MISMATCH")
    inventory = schema_inventory(db)
    contract = json.loads((DESIGN / "conversion-contract.json").read_bytes())
    if (
        inventory["schema_sha256"] != contract["source_schema_sha256"]
        or inventory["schema_version"] != 2
    ):
        raise ConversionError("SOURCE_SCHEMA_MISMATCH")
    expected = [
        (int(p.name[:3]), digest(p.read_bytes()))
        for p in sorted((ROOT / "src/repo_catalog/resources/migrations").glob("*.sql"))
    ]
    migrations = [
        tuple(r)
        for r in db.execute(
            "SELECT version,checksum FROM schema_migrations ORDER BY version"
        )
    ]
    if migrations != expected:
        raise ConversionError("SOURCE_MIGRATIONS_MISMATCH")
    meta = [dict(r) for r in db.execute("SELECT * FROM catalog_meta")]
    if (
        len(meta) != 1
        or meta[0]["id"] != 1
        or not meta[0]["db_instance_id"]
        or meta[0]["schema_version"] != 2
    ):
        raise ConversionError("SOURCE_IDENTITY_INVALID")
    return {
        "format_id": "repo-catalog/v2",
        "db_instance_id": meta[0]["db_instance_id"],
        "schema_sha256": inventory["schema_sha256"],
        "catalog": meta,
        "migrations": [
            dict(r)
            for r in db.execute("SELECT * FROM schema_migrations ORDER BY version")
        ],
        "encoding": db.execute("PRAGMA encoding").fetchone()[0],
    }


def cache_inventory(paths):
    result = []
    for path in paths:
        root = Path(path).absolute()
        if root.is_symlink() or not root.is_dir():
            raise ConversionError("CACHE_NOT_REGULAR")
        require_local_filesystem(root)
        before = stat_identity(root)
        files = []
        for item in sorted(root.rglob("*")):
            if item.is_symlink():
                raise ConversionError("CACHE_SYMLINK_UNSUPPORTED")
            if not item.is_dir() and not item.is_file():
                raise ConversionError("CACHE_NOT_REGULAR")
            relative = os.fsencode(item.relative_to(root)).hex()
            files.append(
                {
                    "path_bytes": relative,
                    "directory": item.is_dir(),
                    **(
                        {"stat": stat_identity(item)}
                        if item.is_dir()
                        else file_fingerprint(item)
                    ),
                }
            )
        if before != stat_identity(root):
            raise ConversionError("CACHE_CHANGED")
        result.append(
            {
                "path": str(root),
                "stat": before,
                "entries": files,
                "sha256": digest(canonical(files).encode()),
            }
        )
    return result


def seal(source, workspace, caches=(), *, expected_cache=None):
    """Stopped/sidecar-free source only. Never checkpoint or repair the original.

    An operator must stop the writer and supply a checkpointed, closed input.
    Live WAL is rejected; do not delete its sidecars to make this succeed.
    """
    source = check_file(source)
    workspace = Path(workspace)
    sealed = workspace / "source.sqlite3"
    descriptor = workspace / "sealed.json"
    if sealed.exists() or descriptor.exists():
        raise ConversionError("SEAL_ALREADY_EXISTS")
    before = file_fingerprint(source)
    with readonly(source) as db:
        metadata = identify(db)
    # Copy byte-for-byte, retaining storage encodings and database identity.
    temporary = workspace / "source.sqlite3.part"
    with source.open("rb") as src, temporary.open("xb") as dst:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            dst.write(block)
        dst.flush()
        os.fsync(dst.fileno())
    after = file_fingerprint(check_file(source))
    if before != after or file_fingerprint(temporary)["sha256"] != before["sha256"]:
        raise ConversionError("SOURCE_CHANGED")
    with readonly(temporary) as db:
        if identify(db) != metadata:
            raise ConversionError("SOURCE_CHANGED")
    temporary.chmod(0o444)
    temporary.rename(sealed)
    evidence = cache_inventory(caches)
    if expected_cache is not None and evidence != expected_cache:
        raise ConversionError("CACHE_CHANGED_DURING_SEAL")
    record = {
        **metadata,
        "original": {"path": str(source), **before},
        "sealed": file_fingerprint(sealed),
        "caches": evidence,
    }
    with descriptor.open("x", encoding="utf-8") as file:
        file.write(canonical(record))
        file.flush()
        os.fsync(file.fileno())
    fsync_directory(workspace)
    return record


def verify_seal(workspace):
    workspace = Path(workspace)
    record = json.loads((workspace / "sealed.json").read_bytes())
    if file_fingerprint(check_file(workspace / "source.sqlite3")) != record["sealed"]:
        raise ConversionError("SOURCE_FINGERPRINT_MISMATCH")
    if file_fingerprint(check_file(record["original"]["path"])) != {
        k: record["original"][k] for k in ("stat", "sha256")
    }:
        raise ConversionError("SOURCE_REPLACED_OR_CHANGED")
    if cache_inventory([c["path"] for c in record["caches"]]) != record["caches"]:
        raise ConversionError("CACHE_FINGERPRINT_MISMATCH")
    with readonly(workspace / "source.sqlite3") as db:
        if identify(db) != {
            k: record[k]
            for k in (
                "format_id",
                "db_instance_id",
                "schema_sha256",
                "catalog",
                "migrations",
                "encoding",
            )
        }:
            raise ConversionError("SOURCE_SCHEMA_MISMATCH")
    return record
