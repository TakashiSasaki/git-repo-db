import fcntl
import json
import os
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

# Exact reviewed P2 implementation at 1e052e4b666039704ad0b8ea3a1d7a752d561358.
# Only the handoff verifier may admit it; ordinary P2 resume remains exact.
REVIEWED_P2_CONVERTERS = frozenset(
    {"644d04524ae83ffeccc0169e7e496328d8dc20f2b7a0a438839f39e271c747d3"}
)


def require_p2_owner(db):
    runs = db.execute("SELECT parser_version FROM conversion_runs").fetchall()
    if len(runs) != 1 or runs[0][0] != PARSER_VERSION:
        raise ConversionError("PHASE_OWNERSHIP_MISMATCH")


def require_p2_destination(path, sealed=None, signatures=None):
    # An immutable ownership read ignores a target hot journal. The subsequent
    # writer may recover that journal only after the prior committed owner was
    # checked. Source sidecars remain prohibited by source.readonly.
    with readonly_destination(path) as db:
        try:
            require_p2_owner(db)
        except ConversionError:
            journal = Path(str(path) + "-journal")
            if sealed is None or signatures is None or not journal.is_file():
                raise
            with journal.open("rb") as file:
                hot = journal.stat().st_size > 512 and file.read(8) == bytes.fromhex(
                    "d9d505f920a163d7"
                )
            if not hot:
                raise
            # A spilled, uncommitted handoff can expose its inserted receipt
            # through immutable reads. Only this recognized current-version
            # transition may be recovered; recheck P2 ownership on the recovered
            # connection before any normal archive write.
            require_pending_handoff(db, sealed, signatures)


def require_pending_handoff(db, sealed, signatures, *, allow_reviewed=False):
    """Authorize recovery only for the bounded spilled phase initialization.

    Overflow pages can be inconsistent through immutable reads while a rollback
    journal is pending, so inspect headers and the new small phase receipt here.
    Full P2 archive/manifest/output proofs follow SQLite recovery before writes.
    """
    from . import phase

    rows = db.execute(
        "SELECT id,source_id,started_at,ended_at,parser_version,state FROM conversion_runs"
    ).fetchall()
    parents = [row for row in rows if row["parser_version"] == PARSER_VERSION]
    phases = [row for row in rows if row["parser_version"] == phase.PROTOCOL_VERSION]
    if len(rows) != 2 or len(parents) != 1 or len(phases) != 1:
        raise ConversionError("PHASE_OWNERSHIP_MISMATCH")
    parent, phase_run = parents[0], phases[0]
    receipt = json.loads(
        db.execute(
            "SELECT manifest FROM conversion_runs WHERE id=?", (phase_run["id"],)
        ).fetchone()[0]
    )
    transition_id = receipt.pop("transition_id", None)
    predecessor = receipt.get("parent", {}).get("converter_sha256")
    identity = db.execute("SELECT * FROM database_identity").fetchone()
    source_row = db.execute("SELECT * FROM conversion_sources").fetchall()
    if (
        parent["state"] != "paused"
        or phase_run["state"] != "paused"
        or phase_run["source_id"] != parent["source_id"]
        or receipt.get("phase_protocol") != phase.PROTOCOL_VERSION
        or receipt.get("state") != "committed"
        or receipt.get("signatures") != signatures
        or receipt.get("parent", {}).get("run_id") != parent["id"]
        or receipt.get("parent", {}).get("parser_version") != PARSER_VERSION
        or not (
            predecessor == signatures["converter_sha256"]
            or (allow_reviewed and predecessor in REVIEWED_P2_CONVERTERS)
        )
        or receipt.get("source", {}).get("source_id") != parent["source_id"]
        or receipt.get("source", {}).get("seal_sha256")
        != digest(canonical(sealed).encode())
        or receipt.get("source", {}).get("physical_sha256")
        != sealed["sealed"]["sha256"]
        or receipt.get("source", {}).get("core_schema_sha256")
        != sealed["schema_sha256"]
        or phase_run["started_at"] != receipt.get("committed_at")
        or phase_run["ended_at"] != receipt.get("committed_at")
        or phase_run["id"] != transition_id
        or transition_id != "p3a:" + digest(canonical(receipt).encode())
        or identity is None
        or identity["format_id"] != "repo-catalog/catalog3-p1"
        or identity["schema_version"] != 3
        or identity["lifecycle"] != "building"
        or identity["ddl_sha256"].hex() != signatures["ddl_sha256"]
        or receipt.get("target", {}).get("db_instance_id") != identity["db_instance_id"]
        or len(source_row) != 1
        or source_row[0]["id"] != parent["source_id"]
        or source_row[0]["source_sha256"].hex() != sealed["sealed"]["sha256"]
        or source_row[0]["schema_sha256"].hex() != sealed["schema_sha256"]
        or source_row[0]["source_db_instance_id"] != sealed["db_instance_id"]
        or source_row[0]["format_id"] != sealed["format_id"]
        or source_row[0]["source_catalog"] != canonical(sealed["catalog"]).encode()
        or source_row[0]["source_migrations"]
        != canonical(sealed["migrations"]).encode()
        or schema_fingerprint(db) != signatures["target_schema_sha256"]
    ):
        raise ConversionError("PHASE_OWNERSHIP_MISMATCH")
    phase._require_predecessor_layout({"converter_sha256": predecessor}, sealed)
    require_internal_schema(db)


@contextmanager
def readonly_destination(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file():
        raise ConversionError("DESTINATION_MISSING_OR_NOT_REGULAR")
    db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("PRAGMA trusted_schema=OFF")
    db.execute("PRAGMA temp_store=MEMORY")
    db.enable_load_extension(False)
    try:
        yield db
    finally:
        db.close()


def schema_fingerprint(db):
    rows = [
        tuple(r)
        for r in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
    ]
    return digest(canonical(rows).encode())


def require_internal_schema(db):
    # The historical P2 fingerprint intentionally excludes SQLite names. Keep
    # that proof definition, but separately verify every internal schema object
    # against trusted target DDL; sqlite_ prefixes do not authorize ANALYZE or
    # other additions to the independently identified destination.
    query = (
        "SELECT type,name,tbl_name,sql FROM sqlite_schema "
        "WHERE name LIKE 'sqlite_%' ORDER BY type,name"
    )
    expected = sqlite3.connect(":memory:")
    try:
        expected.executescript((DESIGN / "target-schema.sql").read_text())
        if [tuple(row) for row in db.execute(query)] != expected.execute(
            query
        ).fetchall():
            raise ConversionError("TARGET_SCHEMA_MISMATCH")
    finally:
        expected.close()


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
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if os.path.lexists(sidecar) and (
            sidecar.is_symlink()
            or not sidecar.is_file()
            or sidecar.stat().st_nlink != 1
        ):
            raise ConversionError("TARGET_SIDECAR_ALIAS_UNSUPPORTED")
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


def verify(
    db,
    sealed,
    signatures,
    *,
    batch_size=None,
    map_repositories=None,
    run_id=None,
    allow_reviewed_predecessor=False,
    check_integrity=True,
):
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
    require_internal_schema(db)
    if run_id is None:
        require_p2_owner(db)
    runs = db.execute(
        "SELECT * FROM conversion_runs" + (" WHERE id=?" if run_id else ""),
        (run_id,) if run_id else (),
    ).fetchall()
    if len(runs) != 1:
        raise ConversionError("CONVERSION_RUN_MISMATCH")
    run = runs[0]
    if run["state"] not in {"building", "paused"}:
        raise ConversionError("CONVERSION_LIFECYCLE_MISMATCH")
    manifest = json.loads(run["manifest"])
    accepted_converter = manifest.get("converter_sha256") == signatures[
        "converter_sha256"
    ] or (
        allow_reviewed_predecessor
        and manifest.get("converter_sha256") in REVIEWED_P2_CONVERTERS
    )
    if (
        any(
            manifest.get(key) != value
            for key, value in signatures.items()
            if key != "converter_sha256"
        )
        or not accepted_converter
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
    if check_integrity and (
        db.execute("PRAGMA foreign_key_check").fetchone()
        or db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
    ):
        raise ConversionError("TARGET_INTEGRITY_FAILURE")
    return run, manifest
