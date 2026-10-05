import fcntl
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from scripts.schema_contract import validate

from .common import (
    DESIGN,
    PARSER_VERSION,
    ROOT,
    ConversionError,
    canonical,
    digest,
    fsync_directory,
    now,
)


def schema_fingerprint(db):
    rows = [
        tuple(r)
        for r in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]
    return digest(canonical(rows).encode())


def resources(ddl=None, contract=None):
    ddl = Path(ddl or DESIGN / "target-schema.sql").read_bytes()
    contract = Path(contract or DESIGN / "conversion-contract.json").read_bytes()
    spec = json.loads(contract)
    if digest(ddl) != spec["ddl_sha256"] or spec["contract_version"] != 1:
        raise ConversionError("TARGET_CONTRACT_DDL_MISMATCH")
    try:
        validate(spec, ddl.decode())
    except ValueError:
        raise ConversionError("INVALID_CONVERSION_CONTRACT") from None
    expected = sqlite3.connect(":memory:")
    try:
        expected.executescript(ddl.decode())
        fingerprint = schema_fingerprint(expected)
    finally:
        expected.close()
    modules = [
        *sorted((ROOT / "scripts/conversion").glob("*.py")),
        ROOT / "scripts/schema_contract.py",
        ROOT / "scripts/schema_audit.py",
        ROOT / "scripts/offline_convert.py",
    ]
    converter_sha256 = digest(
        canonical(
            {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in modules}
        ).encode()
    )
    return (
        ddl,
        spec,
        {
            "ddl_sha256": digest(ddl),
            "contract_sha256": digest(contract),
            "contract_version": spec["contract_version"],
            "parser_version": PARSER_VERSION,
            "converter_sha256": converter_sha256,
            "target_schema_sha256": fingerprint,
        },
    )


@contextmanager
def writer_lock(workspace):
    with (Path(workspace) / "writer.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ConversionError("CONVERTER_ALREADY_RUNNING") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def connect(path):
    db = sqlite3.connect(path, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA synchronous=EXTRA")
    db.execute("PRAGMA temp_store=MEMORY")
    db.enable_load_extension(False)
    # No side databases, extension loading, or weakening target enforcement.
    db.set_authorizer(
        lambda action, arg1, arg2, *rest: (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_ATTACH
            or (action == sqlite3.SQLITE_FUNCTION and arg2 == "load_extension")
            else sqlite3.SQLITE_OK
        )
    )
    return db


def create(
    workspace,
    sealed,
    ddl,
    signatures,
    capacity,
    *,
    batch_size,
    map_repositories,
    source_issues,
):
    workspace = Path(workspace)
    final, temporary = workspace / "target.sqlite3", workspace / "target.sqlite3.part"
    if final.exists() or temporary.exists():
        raise ConversionError("DESTINATION_EXISTS")
    # Exclusive filesystem creation prevents aliasing or overwriting any DB.
    with temporary.open("xb"):
        pass
    db = connect(temporary)
    target_id, source_id, run_id = (str(uuid.uuid4()) for _ in range(3))
    manifest = {
        **signatures,
        "seal": sealed,
        "capacity": capacity,
        "batch_size": batch_size,
        "map_repositories": map_repositories,
        "archive_complete": False,
        "source_fk_issues": source_issues,
    }
    values = (
        canonical(manifest),
        canonical(sealed["catalog"]).encode(),
        canonical(sealed["migrations"]).encode(),
        now(),
    )
    try:
        db.executescript(ddl.decode())
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO database_identity VALUES(1,?,3,?,0,?,'building')",
            (
                "repo-catalog/catalog3-p1",
                target_id,
                bytes.fromhex(signatures["ddl_sha256"]),
            ),
        )
        db.execute(
            "INSERT INTO conversion_sources VALUES(?,?,?,?,?,?,?)",
            (
                source_id,
                bytes.fromhex(sealed["sealed"]["sha256"]),
                bytes.fromhex(sealed["schema_sha256"]),
                sealed["format_id"],
                sealed["db_instance_id"],
                values[1],
                values[2],
            ),
        )
        db.execute(
            "INSERT INTO conversion_runs VALUES(?,?,?,NULL,?,'building',?)",
            (run_id, source_id, values[3], PARSER_VERSION, values[0]),
        )
        if source_issues:
            db.execute(
                "INSERT INTO validation_results(run_id,invariant_id,code,severity,observed_at,details) VALUES(?,'I01','SOURCE_FOREIGN_KEY_VIOLATION','blocking',?,?)",
                (run_id, values[3], canonical({"count": len(source_issues)})),
            )
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()
    temporary.rename(final)
    fsync_directory(workspace)
    return manifest


def verify(db, sealed, signatures, *, batch_size=None, map_repositories=None):
    identity = db.execute("SELECT * FROM database_identity").fetchall()
    if (
        len(identity) != 1
        or identity[0]["format_id"] != "repo-catalog/catalog3-p1"
        or identity[0]["schema_version"] != 3
        or identity[0]["lifecycle"] != "building"
        or bytes(identity[0]["ddl_sha256"]).hex() != signatures["ddl_sha256"]
    ):
        raise ConversionError("TARGET_IDENTITY_MISMATCH")
    if schema_fingerprint(db) != signatures["target_schema_sha256"]:
        raise ConversionError("TARGET_SCHEMA_MISMATCH")
    runs = db.execute("SELECT * FROM conversion_runs").fetchall()
    if len(runs) != 1:
        raise ConversionError("CONVERSION_RUN_MISMATCH")
    run = runs[0]
    if run["state"] not in {"building", "paused"}:
        raise ConversionError("CONVERSION_LIFECYCLE_MISMATCH")
    manifest = json.loads(run["manifest"])
    if (
        any(manifest.get(key) != value for key, value in signatures.items())
        or run["parser_version"] != PARSER_VERSION
    ):
        raise ConversionError("RESUME_VERSION_MISMATCH")
    if manifest["seal"] != sealed:
        raise ConversionError("RESUME_SOURCE_MISMATCH")
    if (batch_size is not None and manifest["batch_size"] != batch_size) or (
        map_repositories is not None
        and manifest["map_repositories"] != map_repositories
    ):
        raise ConversionError("RESUME_OPTIONS_MISMATCH")
    source = db.execute(
        "SELECT * FROM conversion_sources WHERE id=?", (run["source_id"],)
    ).fetchone()
    if (
        source is None
        or source["source_sha256"].hex() != sealed["sealed"]["sha256"]
        or source["schema_sha256"].hex() != sealed["schema_sha256"]
        or source["source_db_instance_id"] != sealed["db_instance_id"]
        or source["format_id"] != sealed["format_id"]
        or source["source_catalog"] != canonical(sealed["catalog"]).encode()
        or source["source_migrations"] != canonical(sealed["migrations"]).encode()
    ):
        raise ConversionError("RESUME_SOURCE_LEDGER_MISMATCH")
    if (
        db.execute("PRAGMA foreign_key_check").fetchone()
        or db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
    ):
        raise ConversionError("TARGET_INTEGRITY_FAILURE")
    return run, manifest
