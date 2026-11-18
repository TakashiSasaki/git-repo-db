"""Canonical separated store factories with explicit per-role initialization.

These factory connections are trusted adapter infrastructure, not a public SQL
admission API. Use p1_repository.RepositoryStore for typed admission. A process
with arbitrary DDL/filesystem access can replace the database or these guards.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import sqlite3
from importlib.resources import files
from pathlib import Path
from uuid import UUID

# Four factory roles, not an inventory of every responsibility or startup store.
# Access has its own independent factory: adapters/sqlite/access_schema.py.
STORES = ("repository", "context", "operational", "search")
MIN_SQLITE = (3, 51, 3)  # Includes the verified WAL-reset fix, STRICT and JSON.
FORMAT = "repo-catalog/p1-isolated-5"
USER_VERSION = 5

REQUIRED_PRAGMAS = {
    "foreign_keys": 1,
    "recursive_triggers": 1,
    "ignore_check_constraints": 0,
    "defer_foreign_keys": 0,
    "trusted_schema": 1,
}


class SchemaError(ValueError):
    """Wrong format, unsupported runtime or a nonempty initialization target."""


class UnsupportedSchemaVersionError(SchemaError):
    """A catalog uses a different persistence format."""

    code = "UNSUPPORTED_SCHEMA_VERSION"


def reject_legacy_layout(directory: Path) -> None:
    old_path = directory / "core.sqlite3"
    if old_path.exists() or old_path.is_symlink():
        raise UnsupportedSchemaVersionError(
            "Legacy core.sqlite3 found. Preserve the old catalog and initialize "
            "the Repository format in a new empty directory."
        )


def uuid4(value: object) -> bool:
    try:
        return (
            isinstance(value, str)
            and str(UUID(value)) == value
            and UUID(value).version == 4
        )
    except (ValueError, TypeError, AttributeError):
        return False


def valid_object_oid(object_format: object, object_oid: object) -> bool:
    width = {"sha1": 40, "sha256": 64}.get(object_format)
    return bool(
        width
        and isinstance(object_oid, str)
        and re.fullmatch("[0-9a-f]{%d}" % width, object_oid)
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


def register_functions(db: sqlite3.Connection, store: str | None = None) -> None:
    """Register a store's functions; None retains the all-store helper profile."""
    if store is not None and store not in STORES:
        raise SchemaError(f"unknown store: {store}")
    db.create_function("p1_uuid4", 1, uuid4, deterministic=True)
    db.create_function("p1_object_oid", 2, valid_object_oid, deterministic=True)
    db.create_function("p1_json", 1, _json, deterministic=True)
    if store in (None, "repository", "context"):
        from repo_catalog.domain.coverage_details import coverage_details_sql

        db.create_function(
            "p1_coverage_details", 1, coverage_details_sql, deterministic=True
        )
    db.create_function(
        "p1_array", -1, lambda *values: canonical(values), deterministic=True
    )
    if store in (None, "repository"):
        from repo_catalog.adapters.sqlite.repository_schema_functions import (
            register_functions as register_repository,
        )

        register_repository(db)
    if store in (None, "context"):
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
    """Deterministic packaged DDL, including immutable guards for every Repository row."""
    if store not in STORES:
        raise SchemaError(f"unknown store: {store}")
    identity = f"""CREATE TABLE store_identity(
    store_role TEXT PRIMARY KEY CHECK(store_role='{store}'),
    repository_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(repository_uuidv4)),
    catalog_instance_uuidv4 TEXT NOT NULL CHECK(p1_uuid4(catalog_instance_uuidv4))
) STRICT, WITHOUT ROWID;
"""
    sql = identity + "\n" + _resource(f"{store}.sql")
    if store in {"repository", "context"}:
        sql += "\n" + _resource("coverage.sql")
    if store == "repository":
        tables = re.findall(r"CREATE TABLE\s+(\w+)\s*\(", sql, flags=re.IGNORECASE)
    else:
        tables = ["store_identity"]
    for table in tables:
        for action in ("UPDATE", "DELETE"):
            sql += f"\nCREATE TRIGGER p1_immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable {store} fact'); END;\n"
    return f"PRAGMA user_version = {USER_VERSION};\n" + sql


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


def configure(db: sqlite3.Connection, store: str | None = None) -> None:
    """Configure before BEGIN; Python schema UDFs require this trusted profile."""
    for name, value in REQUIRED_PRAGMAS.items():
        db.execute(f"PRAGMA {name}={value}")
    db.execute("PRAGMA synchronous=EXTRA")
    verify_connection(db, store)


def verify_connection(db: sqlite3.Connection, store: str | None = None) -> None:
    for name, value in REQUIRED_PRAGMAS.items():
        if db.execute(f"PRAGMA {name}").fetchone()[0] != value:
            raise SchemaError(f"unsupported SQLite configuration: {name}")
    if store is not None and store not in STORES:
        raise SchemaError(f"unknown store: {store}")
    required = [("p1_uuid4", 1), ("p1_object_oid", 2), ("p1_json", 1), ("p1_array", -1)]
    if store in (None, "repository", "context"):
        required += [("p1_coverage_details", 1)]
    if store == "repository":
        required += [
            ("p1_identity_evidence_v1", 4),
            ("p1_uuid7", 1),
            ("p1_ref_absence", 1),
            ("p1_mapping_path", 1),
            ("p1_ref_result_formats", 4),
            ("p1_coverage_members", 1),
            ("p1_claim", 2),
            ("p1_group", 4),
            ("p1_native", 6),
            ("p1_note_role", 6),
            ("p1_notes_group", 3),
            ("p1_intrinsic_claim", 4),
            ("p1_intrinsic_group", 6),
            ("p1_provenance", 1),
            ("p1_git_observation", 7),
            ("p1_repository_claim", 4),
        ]
    if store in (None, "context"):
        required += [
            ("p1_identity_evidence_v1", 4),
            ("p1_source_git_members_v1", 1),
            ("p1_source_inventory_scope_v1", 3),
            ("p1_collection_members_v1", 5),
            ("p1_resource_identity_v1", 1),
            ("p1_resource_identification_v1", 6),
            ("p1_parent_report_v1", 7),
            ("p1_transfer_event_v1", 7),
            ("p1_transfer_value_v1", 2),
            ("p1_transfer_endpoint_v1", 4),
        ]
    functions = {(r[0], r[4]): r[5] for r in db.execute("PRAGMA function_list")}
    for name, arity in required:
        if not functions.get((name, arity), 0) & 2048:
            raise SchemaError(
                f"required deterministic SQLite function unavailable: {name}"
            )


def expected_schema(store: str) -> tuple[tuple, ...]:
    db = sqlite3.connect(":memory:")
    try:
        register_functions(db, store)
        configure(db, store)
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


def verify_declared(store: str | None = None) -> None:
    declared = json.loads(_resource("fingerprints.json"))
    if store is None:
        valid = declared == expected_ddl_manifest()
    else:
        if store not in STORES:
            raise SchemaError(f"unknown store: {store}")
        rows = expected_schema(store)
        expected = {
            "ddl_sha256": fingerprint(store),
            "sqlite_schema_sha256": hashlib.sha256(
                canonical(rows).encode()
            ).hexdigest(),
            "tables": [r[1] for r in rows if r[0] == "table"],
        }
        valid = (
            declared.get("format") == FORMAT
            and set(declared.get("stores", {})) == set(STORES)
            and declared["stores"].get(store) == expected
        )
    if not valid:
        raise SchemaError(
            "declared P1 schema fingerprints differ from composed resources"
        )


def _open(
    path: Path | str, store: str | None = None, *, fresh: bool = False
) -> sqlite3.Connection:
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        raise SchemaError("P1 requires SQLite >= 3.51.3 with safe WAL, STRICT and JSON")
    path = Path(path)
    if not fresh and not path.is_file():
        if store == "repository":
            reject_legacy_layout(path.parent)
        raise SchemaError(f"store absent: {path.name}")
    db = sqlite3.connect(
        path if fresh else path.resolve().as_uri() + "?mode=rw",
        uri=not fresh,
        isolation_level=None,
        cached_statements=0,
    )
    try:
        db.row_factory = sqlite3.Row
        register_functions(db, store)
        configure(db, store)
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
    verify_declared(store)
    if not uuid4(repository_uuidv4) or not uuid4(catalog_instance_uuidv4):
        raise SchemaError(
            "canonical UUIDv4 repository and catalog-instance identities required"
        )
    # Exclusive creation avoids opening or altering an existing catalog.
    path = Path(path)
    with path.open("xb"):
        pass
    db = _open(path, store, fresh=True)
    try:
        if db.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
            raise SchemaError("WAL unavailable")
        # executescript's implicit COMMIT is avoided by putting BEGIN in the script.
        db.executescript("BEGIN IMMEDIATE;\n" + compose(store))
        identity_type = _identity_row_type(store)
        columns, values = identity_type.insert_bindings(
            {
                "store_role": store,
                "repository_uuidv4": repository_uuidv4,
                "catalog_instance_uuidv4": catalog_instance_uuidv4,
            }
        )
        db.execute(
            f"INSERT INTO store_identity ({','.join(columns)}) VALUES(?,?,?)", values
        )
        if store == "repository":
            from repo_catalog.adapters.sqlite.repository_schema_functions import (
                initialize_repository,
            )

            initialize_repository(db, repository_uuidv4)
        db.commit()
        validate(db, store)
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


def _identity_row_type(store: str):
    """Load only the selected domain's generated codec, never optional peers."""
    return importlib.import_module(
        f"repo_catalog.adapters.sqlite.{store}_rows"
    ).ROW_TYPES["store_identity"]


def validate(db: sqlite3.Connection, store: str) -> None:
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version != USER_VERSION:
        raise UnsupportedSchemaVersionError(
            f"{store} schema version {version} is unsupported. Expected {USER_VERSION}."
        )
    if schema_rows(db) != expected_schema(store):
        raise SchemaError(f"{store} physical schema differs from packaged target")
    verify_connection(db, store)
    rows = db.execute("SELECT * FROM store_identity").fetchall()
    if len(rows) != 1:
        raise SchemaError("store identity missing or wrong role")
    try:
        identity_type = _identity_row_type(store)
        identity = identity_type.from_record(
            dict(zip(identity_type.COLUMNS, rows[0], strict=True))
        )
    except (ValueError, TypeError) as exc:
        raise SchemaError("invalid store identity row") from exc
    if identity.store_role != store:
        raise SchemaError("store identity missing or wrong role")
    if not uuid4(identity.repository_uuidv4) or not uuid4(
        identity.catalog_instance_uuidv4
    ):
        raise SchemaError("invalid catalog or repository identity")


def connect(path: Path | str, store: str) -> sqlite3.Connection:
    """Trusted adapter connection; validate before changing persistent settings."""
    db = _open(path, store)
    try:
        verify_declared(store)
        validate(db, store)
        return db
    except BaseException:
        db.close()
        raise
