"""Isolated P1 target schemas. Never imported by the normal catalog initializer.

These factory connections are trusted adapter infrastructure, not a public SQL
admission API. Core's supported application boundary is p1_core.Core. A process
with arbitrary DDL/filesystem access can replace the database or these guards.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from importlib.resources import files
from pathlib import Path
from uuid import UUID

STORES = ("core", "context", "operational", "search")
MIN_SQLITE = (3, 51, 3)  # Includes the verified WAL-reset fix, STRICT and JSON.
FORMAT = "repo-catalog/p1-isolated-1"

REQUIRED_PRAGMAS = {
    "foreign_keys": 1,
    "recursive_triggers": 1,
    "ignore_check_constraints": 0,
    "defer_foreign_keys": 0,
    "trusted_schema": 1,
}


class SchemaError(ValueError):
    """Wrong format, unsupported runtime or a nonempty initialization target."""


def uuid4(value: object) -> bool:
    try:
        return (
            isinstance(value, str)
            and str(UUID(value)) == value
            and UUID(value).version == 4
        )
    except (ValueError, TypeError, AttributeError):
        return False


def oid(object_format: object, full_oid: object) -> bool:
    width = {"sha1": 40, "sha256": 64}.get(object_format)
    return bool(
        width
        and isinstance(full_oid, str)
        and re.fullmatch("[0-9a-f]{%d}" % width, full_oid)
    )


def canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _json(value: object) -> bool:
    try:
        return isinstance(value, str) and canonical(json.loads(value)) == value
    except (ValueError, TypeError, OverflowError, RecursionError):
        return False


def register_functions(db: sqlite3.Connection) -> None:
    """All deterministic functions required to construct or validate target DDL."""
    db.create_function("p1_uuid4", 1, uuid4, deterministic=True)
    db.create_function("p1_oid", 2, oid, deterministic=True)
    db.create_function("p1_json", 1, _json, deterministic=True)
    db.create_function(
        "p1_array", -1, lambda *values: canonical(values), deterministic=True
    )
    from repo_catalog.domain.p1_core import register_functions as register_core

    register_core(db)
    from repo_catalog.adapters.sqlite.p1_context import (
        register_functions as register_context,
    )

    register_context(db)


def _resource(name: str) -> str:
    return (
        files("repo_catalog.adapters.sqlite")
        .joinpath("p1_ddl", name)
        .read_text(encoding="utf-8")
    )


def compose(store: str) -> str:
    """Deterministic packaged DDL, including immutable guards for every Core row."""
    if store not in STORES:
        raise SchemaError(f"unknown store: {store}")
    identity = f"""CREATE TABLE store_identity(
    store_role TEXT PRIMARY KEY CHECK(store_role='{store}'),
    repository_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(repository_uuidv4)),
    catalog_instance_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(catalog_instance_uuidv4))
) STRICT, WITHOUT ROWID;
"""
    sql = identity + "\n" + _resource(f"{store}.sql")
    if store in {"core", "context"}:
        sql += "\n" + _resource("coverage.sql")
    if store == "core":
        tables = re.findall(r"CREATE TABLE\s+(\w+)\s*\(", sql, flags=re.IGNORECASE)
    else:
        tables = ["store_identity"]
    for table in tables:
        for action in ("UPDATE", "DELETE"):
            sql += f"\nCREATE TRIGGER p1_immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable {store} fact'); END;\n"
    return sql


def fingerprint(store: str) -> str:
    return hashlib.sha256(compose(store).encode("utf-8")).hexdigest()


def schema_rows(db: sqlite3.Connection) -> tuple[tuple, ...]:
    return tuple(
        tuple(r)
        for r in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    )


def configure(db: sqlite3.Connection) -> None:
    """Configure before BEGIN; Python schema UDFs require this trusted profile."""
    for name, value in REQUIRED_PRAGMAS.items():
        db.execute(f"PRAGMA {name}={value}")
    db.execute("PRAGMA synchronous=EXTRA")
    verify_connection(db)


def verify_connection(db: sqlite3.Connection) -> None:
    for name, value in REQUIRED_PRAGMAS.items():
        if db.execute(f"PRAGMA {name}").fetchone()[0] != value:
            raise SchemaError(f"unsupported SQLite configuration: {name}")
    functions = {(r[0], r[4]): r[5] for r in db.execute("PRAGMA function_list")}
    for name, arity in (
        ("p1_resource_identity_v1", 1),
        ("p1_resource_identification_v1", 6),
        ("p1_parent_report_v1", 7),
    ):
        if not functions.get((name, arity), 0) & 2048:
            raise SchemaError(
                f"required deterministic SQLite function unavailable: {name}"
            )


def expected_schema(store: str) -> tuple[tuple, ...]:
    db = sqlite3.connect(":memory:")
    try:
        register_functions(db)
        configure(db)
        db.executescript(compose(store))
        return schema_rows(db)
    finally:
        db.close()


def expected_ddl_manifest() -> dict:
    return {
        "format": FORMAT,
        "stores": {
            s: {
                "ddl_sha256": fingerprint(s),
                "sqlite_schema_sha256": hashlib.sha256(
                    canonical(expected_schema(s)).encode()
                ).hexdigest(),
                "tables": [r[1] for r in expected_schema(s) if r[0] == "table"],
            }
            for s in STORES
        },
    }


def verify_declared() -> None:
    if json.loads(_resource("fingerprints.json")) != expected_ddl_manifest():
        raise SchemaError(
            "declared P1 schema fingerprints differ from composed resources"
        )


def _open(path: Path | str, *, fresh: bool = False) -> sqlite3.Connection:
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        raise SchemaError("P1 requires SQLite >= 3.51.3 with safe WAL, STRICT and JSON")
    path = Path(path)
    if not fresh and not path.is_file():
        raise SchemaError(f"store absent: {path.name}")
    db = sqlite3.connect(path, isolation_level=None, cached_statements=0)
    try:
        db.row_factory = sqlite3.Row
        register_functions(db)
        configure(db)
        if db.execute("SELECT json_array(1),json_valid('[]')").fetchone()[1] != 1:
            raise SchemaError("SQLite JSON required")
        return db
    except BaseException:
        db.close()
        raise


def initialize(
    path: Path | str, store: str, repository_uuidv4: str, catalog_instance_uuidv4: str
) -> None:
    """Build one fresh store only; no migration, implicit Context or runtime switch."""
    verify_declared()
    if not uuid4(repository_uuidv4) or not uuid4(catalog_instance_uuidv4):
        raise SchemaError(
            "canonical UUIDv4 repository and catalog-instance identities required"
        )
    # Exclusive creation avoids opening or altering an existing catalog.
    path = Path(path)
    with path.open("xb"):
        pass
    db = _open(path, fresh=True)
    try:
        if db.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
            raise SchemaError("WAL unavailable")
        # executescript's implicit COMMIT is avoided by putting BEGIN in the script.
        db.executescript("BEGIN IMMEDIATE;\n" + compose(store))
        db.execute(
            "INSERT INTO store_identity VALUES(?,?,?)",
            (store, repository_uuidv4, catalog_instance_uuidv4),
        )
        if store == "core":
            db.execute("INSERT INTO repositories VALUES(?)", (repository_uuidv4,))
        db.commit()
        validate(db, store)
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


def validate(db: sqlite3.Connection, store: str) -> None:
    if schema_rows(db) != expected_schema(store):
        raise SchemaError(f"{store} physical schema differs from packaged target")
    verify_connection(db)
    rows = db.execute("SELECT * FROM store_identity").fetchall()
    if len(rows) != 1 or rows[0][0] != store:
        raise SchemaError("store identity missing or wrong role")
    if not uuid4(rows[0][1]) or not uuid4(rows[0][2]):
        raise SchemaError("invalid catalog or repository identity")


def connect(path: Path | str, store: str) -> sqlite3.Connection:
    """Trusted adapter connection; validate before changing persistent settings."""
    db = _open(path)
    try:
        verify_declared()
        validate(db, store)
        return db
    except BaseException:
        db.close()
        raise
