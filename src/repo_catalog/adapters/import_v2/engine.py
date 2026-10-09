"""One source-owned importer, using the authoritative ordinary runtime schema.

Normalized facts live in the destination; archives, mappings, diagnostics and
source/output proofs live in a separate workspace. Each batch commits both together.
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.sqlite.schema import (
    DDL_SHA256,
    FORMAT_ID,
    SCHEMA_VERSION,
    schema_sql,
)
from repo_catalog.domain.document import text_body_sha256
from repo_catalog.domain.time import now_us

from . import (
    archive,
    batch,
    capacity,
    diagnostics,
    git_domain,
    guards,
    identity,
    pr_domain,
    source,
)
from . import workspace as import_workspace
from .common import (
    ConversionError,
    canonical,
    digest,
    fsync_directory,
    require_local_filesystem,
)
from .types import identifier, tagged_key

PROTOCOL = "offline-v2/1"
MAX_BATCH_BYTES = 8 * 1024 * 1024
SINGLE_RECORD = {
    "saved_document_repair",
    "saved_listing_repair",
    "saved_pr_document_repair",
    "sync_checkpoints",
}


def no_fault(point, **context):
    pass


def recipe_plan():
    late = {"ref_root_origins", "pr_root_origins", "unknown_root_origins"}
    return (
        [(identity, name) for name in identity.RECIPES]
        + [(git_domain, name) for name in git_domain.RECIPES if name not in late]
        + [(pr_domain, name) for name in pr_domain.RECIPES]
        + [(git_domain, name) for name in git_domain.RECIPES if name in late]
    )


def definitions():
    columns, keys = {}, {}
    for module in (identity, git_domain, pr_domain):
        columns.update(module.COLUMNS)
        keys.update(module.KEYS)
    return columns, keys


def typed_key(values):
    return tagged_key(
        [
            ("null", None)
            if value is None
            else ("blob", value)
            if isinstance(value, bytes)
            else ("text", value.encode("utf-8"))
            if isinstance(value, str)
            else ("integer", value)
            if isinstance(value, int)
            else ("real", value)
            for value in values
        ]
    )


def key_values(table, row):
    columns, keys = definitions()
    return tuple(row[columns[table].index(key)] for key in keys[table])


def row_hash(row):
    return batch.proof_digest(batch.encode([row]))


def find(db, table, row):
    keys = definitions()[1][table]
    return db.execute(
        f"SELECT {','.join(identifier(c) for c in definitions()[0][table])} FROM {identifier(table)} WHERE "
        + " AND ".join(f"{identifier(key)}=?" for key in keys),
        key_values(table, row),
    ).fetchone()


def schema_fingerprint(db):
    return digest(
        canonical(
            [
                tuple(row)
                for row in db.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
                )
            ]
        ).encode()
    )


def expected_schema():
    with sqlite3.connect(":memory:") as db:
        db.executescript(schema_sql())
        return schema_fingerprint(db)


@contextmanager
def connect(path, *, creating_workspace=False):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ConversionError("DESTINATION_NOT_REGULAR")
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if os.path.lexists(sidecar) and (
            sidecar.is_symlink()
            or not sidecar.is_file()
            or sidecar.stat().st_nlink != 1
        ):
            raise ConversionError("TARGET_SIDECAR_ALIAS_UNSUPPORTED")
    db = sqlite3.connect(path, isolation_level=None, uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    db.execute("PRAGMA synchronous=EXTRA")
    db.execute("PRAGMA temp_store=MEMORY")
    db.enable_load_extension(False)
    try:
        import_workspace.attach(db, path, creating=creating_workspace)
    except BaseException:
        db.close()
        raise
    db.set_authorizer(
        lambda action, arg1, arg2, *args: (
            sqlite3.SQLITE_DENY
            if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH)
            or (action == sqlite3.SQLITE_FUNCTION and arg2 == "load_extension")
            else sqlite3.SQLITE_OK
        )
    )
    try:
        yield db
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()


def implementation_signature():
    return digest(
        canonical(
            {
                path.name: digest(path.read_bytes())
                for path in sorted(Path(__file__).parent.glob("*.py"))
            }
        ).encode()
    )


def create(destination, sealed, batch_size, estimate, fault=no_fault):
    temporary = Path(str(destination) + ".part")
    if os.path.lexists(destination) or os.path.lexists(temporary):
        raise ConversionError("DESTINATION_EXISTS")
    work = import_workspace.path_for(destination)
    work_pending = import_workspace.path_for(temporary)
    work.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(work) or os.path.lexists(work_pending):
        raise ConversionError("IMPORT_WORKSPACE_EXISTS")
    with temporary.open("xb"):
        pass
    with work_pending.open("xb"):
        pass
    stamp, conversion_source_id, conversion_run_id = (
        now_us(),
        str(uuid.uuid4()),
        str(uuid.uuid4()),
    )
    receipt = {
        "protocol": PROTOCOL,
        "implementation_sha256": implementation_signature(),
        "ddl_sha256": DDL_SHA256.hex(),
        "seal": sealed,
        "batch_size": batch_size,
        "encoding": sealed["encoding"],
        "capacity": estimate,
        "complete": False,
    }
    with connect(temporary, creating_workspace=True) as db:
        db.executescript(schema_sql())
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO database_identity(singleton,format_id,schema_version,db_instance_id,publication_seq,ddl_sha256,lifecycle) VALUES(1,?,?,?,0,?,'building')",
            (FORMAT_ID, SCHEMA_VERSION, str(uuid.uuid4()), DDL_SHA256),
        )
        import_workspace.initialize(db)
        db.execute(
            "INSERT INTO conversion_sources(conversion_source_id,source_sha256,schema_sha256,format_id,source_db_instance_id,source_catalog,source_migrations) VALUES(?,?,?,?,?,?,?)",
            (
                conversion_source_id,
                bytes.fromhex(sealed["sealed"]["sha256"]),
                bytes.fromhex(sealed["schema_sha256"]),
                sealed["format_id"],
                sealed["db_instance_id"],
                canonical(sealed["catalog"]).encode(),
                canonical(sealed["migrations"]).encode(),
            ),
        )
        db.execute(
            "INSERT INTO conversion_runs(conversion_run_id,conversion_source_id,started_at_us,ended_at_us,parser_version,state,manifest) VALUES(?,?,?,NULL,?,'building',?)",
            (
                conversion_run_id,
                conversion_source_id,
                stamp,
                PROTOCOL,
                canonical(receipt),
            ),
        )
        db.execute("COMMIT")
    # Both initial identities have committed before publishing either filename.
    fsync_directory(work.parent)
    fsync_directory(destination.parent)
    temporary.rename(destination)
    fsync_directory(destination.parent)
    fault("after_catalog_initialization_publish")
    work_pending.rename(work)
    fsync_directory(work.parent)


def check(db, sealed, batch_size):
    import_workspace.verify(db)
    identities = db.execute(
        "SELECT singleton,format_id,schema_version,db_instance_id,publication_seq,ddl_sha256,lifecycle FROM database_identity"
    ).fetchall()
    runs = db.execute(
        "SELECT conversion_run_id,conversion_source_id,started_at_us,ended_at_us,parser_version,state,manifest FROM conversion_runs"
    ).fetchall()
    if (
        len(identities) != 1
        or identities[0]["format_id"] != FORMAT_ID
        or identities[0]["schema_version"] != SCHEMA_VERSION
        or identities[0]["ddl_sha256"].hex() != DDL_SHA256.hex()
        or identities[0]["lifecycle"] != "building"
        or schema_fingerprint(db) != expected_schema()
    ):
        raise ConversionError("IMPORT_TARGET_IDENTITY_MISMATCH")
    if (
        len(runs) != 1
        or runs[0]["parser_version"] != PROTOCOL
        or runs[0]["state"] not in {"building", "paused"}
    ):
        raise ConversionError("IMPORT_OWNER_MISMATCH")
    run, receipt = runs[0], json.loads(runs[0]["manifest"])
    if (
        receipt.get("protocol") != PROTOCOL
        or receipt.get("implementation_sha256") != implementation_signature()
        or receipt.get("ddl_sha256") != DDL_SHA256.hex()
        or receipt.get("seal") != sealed
        or receipt.get("batch_size") != batch_size
    ):
        raise ConversionError("IMPORT_RESUME_MISMATCH")
    saved = db.execute(
        "SELECT conversion_source_id,source_sha256,schema_sha256,format_id,source_db_instance_id,source_catalog,source_migrations FROM conversion_sources"
    ).fetchall()
    if len(saved) != 1 or tuple(saved[0]) != (
        run["conversion_source_id"],
        bytes.fromhex(sealed["sealed"]["sha256"]),
        bytes.fromhex(sealed["schema_sha256"]),
        sealed["format_id"],
        sealed["db_instance_id"],
        canonical(sealed["catalog"]).encode(),
        canonical(sealed["migrations"]).encode(),
    ):
        raise ConversionError("IMPORT_SOURCE_LEDGER_MISMATCH")
    return run, receipt


def descriptors(src, run, receipt):
    tables = {
        item["table"]
        for item in json.loads(
            (source.DESIGN / "conversion-contract.json").read_bytes()
        )["source_columns"]
    }
    for table in sorted(tables):
        yield from bounded_batches(
            src, table, receipt["batch_size"], None, "archive:" + table, run
        )
    for module, recipe in recipe_plan():
        table = module.SOURCE_TABLES.get(recipe, recipe)
        size = 1 if recipe in SINGLE_RECORD else receipt["batch_size"]
        yield from bounded_batches(src, table, size, module, "recipe:" + recipe, run)


def bounded_batches(src, table, limit, module, name, run):
    index, pending, byte_count = 0, [], 0
    for record in archive.rows(src, table):
        size = (
            len(record.key)
            + len(record.row_sha256)
            + sum(len(raw) for _, _, raw in record.values)
        )
        if pending and byte_count + size > MAX_BATCH_BYTES:
            yield descriptor(run, module, name, index, tuple(pending))
            index, pending, byte_count = index + 1, [], 0
        pending.append(record)
        byte_count += size
        if len(pending) >= limit or byte_count >= MAX_BATCH_BYTES:
            yield descriptor(run, module, name, index, tuple(pending))
            index, pending, byte_count = index + 1, [], 0
    if pending or index == 0:
        yield descriptor(run, module, name, index, tuple(pending))


def descriptor(run, module, name, index, records):
    h = digest(
        canonical(
            {
                "protocol": PROTOCOL,
                "conversion_source_id": run["conversion_source_id"],
                "recipe": name,
                "index": index,
                "records": [[r.key.hex(), r.row_sha256.hex()] for r in records],
            }
        ).encode()
    )
    return module, name, index, records, h


def archive_output(db, run, records, stamp, encoding):
    ident = batch.next_id(db, "legacy_records")
    diag = batch.next_id(db, "validation_results")
    rows = {"legacy_records": [], "legacy_values": [], "validation_results": []}
    for record in records:
        rows["legacy_records"].append(
            (
                ident,
                run["conversion_source_id"],
                record.table,
                record.key,
                record.row_sha256,
            )
        )
        rows["legacy_values"].extend((ident, *value) for value in record.values)
        for code, severity, column in diagnostics.classify(record, encoding):
            rows["validation_results"].append(
                (
                    diag,
                    run["conversion_run_id"],
                    "I31",
                    code,
                    severity,
                    stamp,
                    canonical({"legacy_record_id": ident, "column": column}),
                )
            )
            diag += 1
        ident += 1
    return rows


def archive_proof(rows):
    return {
        name: [batch.row_proof(name, row) for row in values]
        for name, values in rows.items()
    }


def compact(output, mapping_ids, diagnostic_ids, stamp):
    operations = []
    for op in output["operations"]:
        value = {
            "legacy_record_id": op["legacy_record_id"],
            "table": op["table"],
            "operation": op["operation"],
            "key": batch.encode([key_values(op["table"], op["row"])])[0],
            "sha256": row_hash(op["row"]),
        }
        if "before" in op:
            value["before_sha256"] = row_hash(op["before"])
        operations.append(value)
    return {
        "operations": operations,
        "decisions": output["decisions"],
        "mapping_ids": mapping_ids,
        "diagnostic_ids": diagnostic_ids,
        "mappings_sha256": row_hash(output["mappings"]),
        "diagnostics_sha256": row_hash(output["diagnostics"]),
        "observed_at_us": stamp,
    }


def commit(db, src, run, receipt, item, fault=no_fault):
    module, name, index, records, input_sha256 = item
    stamp = now_us()
    if module is None:
        rows = archive_output(db, run, records, stamp, receipt["encoding"])
        saved = archive_proof(rows)
    else:
        output = module.prepare(
            db,
            src,
            run,
            name.removeprefix("recipe:"),
            index,
            records,
            encoding=receipt["encoding"],
        )
        mapping_ids = list(
            range(
                batch.next_id(db, "id_mappings"),
                batch.next_id(db, "id_mappings") + len(output["mappings"]),
            )
        )
        diagnostic_ids = list(
            range(
                batch.next_id(db, "validation_results"),
                batch.next_id(db, "validation_results") + len(output["diagnostics"]),
            )
        )
        saved = compact(output, mapping_ids, diagnostic_ids, stamp)
    manifest = canonical(
        {
            "protocol": PROTOCOL,
            "recipe": name,
            "index": index,
            "output": saved,
            "output_sha256": batch.proof_digest(saved),
        }
    )
    fault("before_insert", table=name, index=index)
    try:
        db.execute("BEGIN IMMEDIATE")
        if module is None:
            for table, values in rows.items():
                if values:
                    db.executemany(
                        f"INSERT INTO {table} VALUES({','.join('?' for _ in values[0])})",
                        values,
                    )
        else:
            for op in output["operations"]:
                table, row, operation = op["table"], op["row"], op["operation"]
                if table == "text_bodies":
                    _, body, byte_length, sha = row
                    if (
                        text_body_sha256(body) != sha
                        or len(body.encode("utf-8")) != byte_length
                    ):
                        raise ConversionError("TEXT_BODY_DIGEST_MISMATCH")
                    same_digest = db.execute(
                        "SELECT body,byte_length FROM text_bodies WHERE sha256=?",
                        (sha,),
                    ).fetchone()
                    if same_digest is not None and tuple(same_digest) != (
                        body,
                        byte_length,
                    ):
                        raise ConversionError("TEXT_BODY_IDENTITY_CONFLICT")
                actual = find(db, table, row)
                if operation in {"insert", "reuse"}:
                    if actual is None and operation == "insert":
                        columns = definitions()[0][table]
                        db.execute(
                            f"INSERT INTO {identifier(table)}({','.join(identifier(c) for c in columns)}) VALUES({','.join('?' for _ in row)})",
                            row,
                        )
                    elif actual is None or tuple(actual) != tuple(row):
                        raise ConversionError("IMPORT_OUTPUT_CONFLICT")
                elif operation == "preference" and table == "repositories":
                    if actual is None or list(actual) != [
                        row[0],
                        row[1],
                        None,
                        None,
                        row[4],
                    ]:
                        raise ConversionError("IMPORT_BEFORE_IMAGE_MISMATCH")
                    db.execute(
                        "UPDATE repositories SET preferred_repository_endpoint_id=? WHERE repository_uuidv4=?",
                        (row[2], row[0]),
                    )
                elif operation == "manifest_completion" and table == "root_manifests":
                    if actual is None or actual[0] != row[0] or actual[1] != 0:
                        raise ConversionError("IMPORT_BEFORE_IMAGE_MISMATCH")
                    db.execute(
                        "UPDATE root_manifests SET complete=? WHERE tree_git_object_id=?",
                        (row[1], row[0]),
                    )
                elif (
                    operation in {"update", "update_listing_progress"}
                    and table == "code_listing_progress"
                ):
                    if actual is None or tuple(actual) != tuple(op["before"]):
                        raise ConversionError("IMPORT_BEFORE_IMAGE_MISMATCH")
                    db.execute(
                        "UPDATE code_listing_progress SET "
                        + ",".join(
                            f"{identifier(c)}=?" for c in definitions()[0][table][1:]
                        )
                        + " WHERE code_listing_id=?",
                        [*row[1:], row[0]],
                    )
                else:
                    raise ConversionError("IMPORT_UNOWNED_OPERATION")
            fault("after_data", table=name, index=index)
            for ident, mapped in zip(mapping_ids, output["mappings"], strict=True):
                legacy_record_id, table, key, relation, reason = mapped
                values = [
                    raw.decode("utf-8") if kind == "text" else raw
                    for kind, raw in archive.decode_key(bytes.fromhex(key))
                ]
                keys = definitions()[1][table]
                found = db.execute(
                    f"SELECT {','.join(identifier(k) for k in keys)} FROM {identifier(table)} WHERE "
                    + " AND ".join(f"{identifier(k)}=?" for k in keys),
                    values,
                ).fetchone()
                if found is None or typed_key(tuple(found)).hex() != key:
                    raise ConversionError("IMPORT_MAPPING_TARGET_MISSING")
                db.execute(
                    "INSERT INTO id_mappings(id_mapping_id,legacy_record_id,target_table,target_key,relation,reason) VALUES(?,?,?,?,?,?)",
                    (
                        ident,
                        legacy_record_id,
                        table,
                        bytes.fromhex(key),
                        relation,
                        reason,
                    ),
                )
            fault("after_mapping", table=name, index=index)
            for ident, diagnostic in zip(
                diagnostic_ids, output["diagnostics"], strict=True
            ):
                db.execute(
                    "INSERT INTO validation_results(validation_result_id,conversion_run_id,invariant_id,code,severity,observed_at_us,details) VALUES(?,?,?,?,?,?,?)",
                    (
                        ident,
                        run["conversion_run_id"],
                        *diagnostic[:3],
                        stamp,
                        diagnostic[3],
                    ),
                )
        db.execute(
            "INSERT INTO conversion_batches(conversion_batch_id,conversion_run_id,source_table,input_sha256,committed_at_us,output_manifest) VALUES(?,?,?,?,?,?)",
            (
                batch.next_id(db, "conversion_batches"),
                run["conversion_run_id"],
                name,
                bytes.fromhex(input_sha256),
                stamp,
                manifest,
            ),
        )
        db.execute(
            "UPDATE conversion_runs SET state='building',ended_at_us=NULL WHERE conversion_run_id=?",
            (run["conversion_run_id"],),
        )
        fault("before_commit", table=name, index=index)
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    fault("after_commit", table=name, index=index)


def verify_output(db, src, run, receipt):
    """Reproduce decisions from immutable inputs and compare all owned rows."""
    ledger = sqlite3.connect(":memory:")
    ledger.executescript(
        "CREATE TABLE rows(t TEXT,k BLOB,h TEXT,PRIMARY KEY(t,k)); CREATE TABLE maps(id INTEGER PRIMARY KEY); CREATE TABLE diagnostics(id INTEGER PRIMARY KEY);"
    )
    expected = descriptors(src, run, receipt)
    count = 0
    try:
        for saved_batch in db.execute(
            "SELECT conversion_batch_id,conversion_run_id,source_table,input_sha256,committed_at_us,output_manifest FROM conversion_batches WHERE conversion_run_id=? ORDER BY conversion_batch_id",
            (run["conversion_run_id"],),
        ):
            item = next(expected, None)
            if item is None:
                raise ConversionError("IMPORT_UNEXPECTED_BATCH")
            module, name, index, records, input_sha256 = item
            manifest = json.loads(saved_batch["output_manifest"])
            saved = manifest.get("output", {})
            if (
                manifest.get("protocol") != PROTOCOL
                or manifest.get("recipe") != name
                or manifest.get("index") != index
                or saved_batch["source_table"] != name
                or saved_batch["input_sha256"].hex() != input_sha256
                or manifest.get("output_sha256") != batch.proof_digest(saved)
            ):
                raise ConversionError("IMPORT_BATCH_PROOF_MISMATCH")
            if module is None:
                # The source record key binds stable destination archive IDs.
                rows = {
                    "legacy_records": [],
                    "legacy_values": [],
                    "validation_results": [],
                }
                for record in records:
                    actual = db.execute(
                        "SELECT legacy_record_id,conversion_source_id,source_table,source_key,row_sha256 FROM legacy_records WHERE conversion_source_id=? AND source_table=? AND source_key=?",
                        (run["conversion_source_id"], record.table, record.key),
                    ).fetchone()
                    if actual is None or actual["row_sha256"] != record.row_sha256:
                        raise ConversionError("IMPORT_ARCHIVE_MISMATCH")
                    rows["legacy_records"].append(tuple(actual))
                    rows["legacy_values"].extend(
                        (actual["legacy_record_id"], *value) for value in record.values
                    )
                    for code, severity, column in diagnostics.classify(
                        record, receipt["encoding"]
                    ):
                        found = db.execute(
                            "SELECT validation_result_id,conversion_run_id,invariant_id,code,severity,observed_at_us,details FROM validation_results WHERE conversion_run_id=? AND code=? AND details=?",
                            (
                                run["conversion_run_id"],
                                code,
                                canonical(
                                    {
                                        "legacy_record_id": actual["legacy_record_id"],
                                        "column": column,
                                    }
                                ),
                            ),
                        ).fetchall()
                        if len(found) != 1:
                            raise ConversionError("IMPORT_ARCHIVE_DIAGNOSTIC_MISMATCH")
                        rows["validation_results"].append(
                            (
                                found[0]["validation_result_id"],
                                run["conversion_run_id"],
                                "I31",
                                code,
                                severity,
                                saved_batch["committed_at_us"],
                                canonical(
                                    {
                                        "legacy_record_id": actual["legacy_record_id"],
                                        "column": column,
                                    }
                                ),
                            )
                        )
                if archive_proof(rows) != saved:
                    raise ConversionError("IMPORT_ARCHIVE_PROOF_MISMATCH")
                for table, values in rows.items():
                    for row in values:
                        key = typed_key(
                            row[:2] if table == "legacy_values" else row[:1]
                        )
                        ledger.execute(
                            "INSERT INTO rows(t,k,h) VALUES(?,?,?)",
                            (table, key, row_hash(row)),
                        )
                        if table == "validation_results":
                            ledger.execute(
                                "INSERT INTO diagnostics(id) VALUES(?)", (row[0],)
                            )
            else:
                output = module.prepare(
                    db,
                    src,
                    run,
                    name.removeprefix("recipe:"),
                    index,
                    records,
                    encoding=receipt["encoding"],
                    verifying=True,
                )
                if saved != compact(
                    output,
                    saved.get("mapping_ids", []),
                    saved.get("diagnostic_ids", []),
                    saved_batch["committed_at_us"],
                ):
                    raise ConversionError("IMPORT_SOURCE_OUTPUT_MISMATCH")
                if len(saved["mapping_ids"]) != len(output["mappings"]) or len(
                    saved["diagnostic_ids"]
                ) != len(output["diagnostics"]):
                    raise ConversionError("IMPORT_BATCH_PROOF_MISMATCH")
                for op in output["operations"]:
                    table, row = op["table"], op["row"]
                    key, sha = typed_key(key_values(table, row)), row_hash(row)
                    prior = ledger.execute(
                        "SELECT h FROM rows WHERE t=? AND k=?", (table, key)
                    ).fetchone()
                    if (
                        prior
                        and prior[0] != sha
                        and not (
                            op["operation"] == "preference" and table == "repositories"
                        )
                        and not (
                            op["operation"] == "manifest_completion"
                            and table == "root_manifests"
                        )
                        and not (
                            table == "code_listing_progress"
                            and op["operation"] in {"update", "update_listing_progress"}
                            and prior[0] == row_hash(op["before"])
                        )
                    ):
                        raise ConversionError("IMPORT_OUTPUT_CONFLICT")
                    ledger.execute(
                        "INSERT INTO rows(t,k,h) VALUES(?,?,?) ON CONFLICT(t,k) DO UPDATE SET h=excluded.h",
                        (table, key, sha),
                    )
                for ident, mapped in zip(
                    saved["mapping_ids"], output["mappings"], strict=True
                ):
                    ledger.execute("INSERT INTO maps(id) VALUES(?)", (ident,))
                    actual = db.execute(
                        "SELECT id_mapping_id,legacy_record_id,target_table,target_key,relation,reason FROM id_mappings WHERE id_mapping_id=?",
                        (ident,),
                    ).fetchone()
                    if actual is None or tuple(actual) != (
                        ident,
                        mapped[0],
                        mapped[1],
                        bytes.fromhex(mapped[2]),
                        *mapped[3:],
                    ):
                        raise ConversionError("IMPORT_MAPPING_MISMATCH")
                for ident, diagnostic in zip(
                    saved["diagnostic_ids"], output["diagnostics"], strict=True
                ):
                    row = (
                        ident,
                        run["conversion_run_id"],
                        *diagnostic[:3],
                        saved_batch["committed_at_us"],
                        diagnostic[3],
                    )
                    ledger.execute("INSERT INTO diagnostics(id) VALUES(?)", (ident,))
                    actual = db.execute(
                        "SELECT validation_result_id,conversion_run_id,invariant_id,code,severity,observed_at_us,details FROM validation_results WHERE validation_result_id=?",
                        (ident,),
                    ).fetchone()
                    if actual is None or tuple(actual) != row:
                        raise ConversionError("IMPORT_DIAGNOSTIC_MISMATCH")
            count += 1
        complete = next(expected, None) is None
        for table in ("legacy_records", "legacy_values", *definitions()[0]):
            total = 0
            columns = definitions()[0].get(table)
            columns = (
                columns
                or {
                    "legacy_records": (
                        "legacy_record_id",
                        "conversion_source_id",
                        "source_table",
                        "source_key",
                        "row_sha256",
                    ),
                    "legacy_values": (
                        "legacy_record_id",
                        "column_name",
                        "storage_type",
                        "value_bytes",
                    ),
                }[table]
            )
            selected = ",".join(identifier(c) for c in columns)
            for actual in db.execute(f"SELECT {selected} FROM {identifier(table)}"):
                key = (
                    typed_key(
                        tuple(actual[:2] if table == "legacy_values" else actual[:1])
                    )
                    if table in {"legacy_records", "legacy_values"}
                    else typed_key(key_values(table, actual))
                )
                saved = ledger.execute(
                    "SELECT h FROM rows WHERE t=? AND k=?", (table, key)
                ).fetchone()
                if saved is None or saved[0] != row_hash(tuple(actual)):
                    raise ConversionError("IMPORT_UNLEDGERED_OUTPUT")
                total += 1
            if (
                total
                != ledger.execute(
                    "SELECT count(*) FROM rows WHERE t=?", (table,)
                ).fetchone()[0]
            ):
                raise ConversionError("IMPORT_OUTPUT_MISSING")
        for table, key in (
            ("id_mappings", "maps"),
            ("validation_results", "diagnostics"),
        ):
            if (
                db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                != ledger.execute(f"SELECT count(*) FROM {key}").fetchone()[0]
            ):
                raise ConversionError("IMPORT_UNLEDGERED_AUDIT")
        return {
            "complete": complete,
            "committed_batches": count,
            "diagnostics": diagnostics.counts(db, run["conversion_run_id"]),
        }
    finally:
        ledger.close()


def run(
    policy,
    state_dir,
    *,
    source_path,
    source_caches=(),
    batch_size=100,
    max_batches=None,
    fault=no_fault,
):
    state_dir = Path(state_dir).resolve()
    if not isinstance(policy, guards.WorkerPolicy) or policy.workspace != state_dir:
        raise ConversionError("GUARDED_WORKER_REQUIRED")
    if (
        type(batch_size) is not int
        or batch_size < 1
        or (
            max_batches is not None
            and (type(max_batches) is not int or max_batches < 0)
        )
    ):
        raise ConversionError("INVALID_BATCH_OPTIONS")
    workspace = state_dir / "import-v2"
    destination = state_dir / "catalog.sqlite3"
    require_local_filesystem(state_dir)
    with FileLock(state_dir / "locks/writer.lock"):
        workspace.mkdir(exist_ok=True)
        if not (workspace / "sealed.json").exists():
            if destination.exists():
                raise ConversionError("DESTINATION_EXISTS")
            # An interrupted initial seal has no committed descriptor or target.
            # Discard only this importer's isolated temporary output before retry.
            import_workspace.discard_pending_initialization(destination)
            for incomplete in (
                workspace / "source.sqlite3.part",
                workspace / "source.sqlite3",
                workspace / "sealed.json.part",
            ):
                if os.path.lexists(incomplete):
                    if (
                        incomplete.is_symlink()
                        or not incomplete.is_file()
                        or incomplete.stat().st_nlink != 1
                    ):
                        raise ConversionError("IMPORT_INCOMPLETE_OUTPUT_ALIAS")
                    incomplete.unlink()
            with source.readonly(source_path) as src:
                try:
                    source.identify(src)
                except source.admission.SourceAdmissionError as exc:
                    # Rejected schema evidence stays local; sensitive DDL is never
                    # emitted by the CLI. No source or destination DB is changed.
                    report = canonical(
                        {
                            "state": "rejected",
                            "sealed": False,
                            "source_fingerprint": source.file_fingerprint(
                                source.check_file(source_path)
                            ),
                            "admission": exc.report,
                        }
                    )
                    pending = workspace / "source-admission.json.part"
                    if pending.exists():
                        if pending.is_symlink() or pending.stat().st_nlink != 1:
                            raise ConversionError(
                                "IMPORT_INCOMPLETE_OUTPUT_ALIAS"
                            ) from None
                        pending.unlink()
                    with pending.open("x", encoding="utf-8") as stream:
                        stream.write(report)
                        stream.flush()
                        os.fsync(stream.fileno())
                    pending.replace(workspace / "source-admission.json")
                    fsync_directory(workspace)
                    raise
                tables = {
                    item["table"]
                    for item in json.loads(
                        (source.DESIGN / "conversion-contract.json").read_bytes()
                    )["source_columns"]
                }
                estimate = capacity.preflight(
                    state_dir,
                    capacity.estimate(src, tables, Path(source_path).stat().st_size),
                )
            source.seal(source_path, workspace, source_caches)
        sealed = source.verify_seal(workspace)
        if str(Path(source_path).absolute()) != sealed["original"]["path"] or [
            str(Path(p).absolute()) for p in source_caches
        ] != [c["path"] for c in sealed["caches"]]:
            raise ConversionError("IMPORT_RESUME_SOURCE_MISMATCH")
        with source.readonly(workspace / "source.sqlite3") as src:
            if not destination.exists():
                import_workspace.discard_pending_initialization(destination)
                # A seal may survive interruption before destination creation.
                tables = {
                    item["table"]
                    for item in json.loads(
                        (source.DESIGN / "conversion-contract.json").read_bytes()
                    )["source_columns"]
                }
                estimate = capacity.preflight(
                    state_dir,
                    capacity.estimate(
                        src, tables, (workspace / "source.sqlite3").stat().st_size
                    ),
                )
                create(destination, sealed, batch_size, estimate, fault)
            import_workspace.recover_initialization(destination)
            with connect(destination) as db:
                run_row, receipt = check(db, sealed, batch_size)
                status = verify_output(db, src, run_row, receipt)
                new_batches = 0
                for ordinal, item in enumerate(descriptors(src, run_row, receipt)):
                    if ordinal < status["committed_batches"]:
                        continue
                    if max_batches is not None and new_batches >= max_batches:
                        break
                    commit(db, src, run_row, receipt, item, fault)
                    new_batches += 1
                if new_batches:
                    status = verify_output(db, src, run_row, receipt)
                if (
                    db.execute("PRAGMA foreign_key_check").fetchone()
                    or db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                ):
                    raise ConversionError("IMPORT_TARGET_INTEGRITY_FAILURE")
                import_workspace.verify(db)
                source.verify_seal(workspace)
                receipt["complete"] = status["complete"]
                receipt["committed_batches"] = status["committed_batches"]
                receipt["source_foreign_key_issues"] = diagnostics.source_issues(src)
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "UPDATE conversion_runs SET state='paused',ended_at_us=?,manifest=? WHERE conversion_run_id=?",
                    (
                        now_us() if status["complete"] else None,
                        canonical(receipt),
                        run_row["conversion_run_id"],
                    ),
                )
                db.execute("COMMIT")
                return {
                    **status,
                    "new_batches": new_batches,
                    "lifecycle": "building",
                    "format_id": FORMAT_ID,
                    "sqlite_version": sqlite3.sqlite_version,
                    "source_untouched": True,
                    "acquisition_allowed": False,
                    "import_workspace": str(import_workspace.path_for(destination)),
                }
