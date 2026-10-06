"""One guarded stored-data owner with atomic, source-derived domain checkpoints.

Proofs contain keys and hashes, never another copy of preserved payload bytes.
Each locked invocation audits entry once and compares committed output at exit.
"""

import json
import os
import sqlite3
from pathlib import Path

from scripts.schema_audit import identifier
from scripts.schema_contract import tagged_key

from . import archive, batch, capacity, identity_phase, source, target
from .common import ConversionError, canonical, digest, now, stat_identity

PROTOCOL_VERSION = "p3-integrated/1"


def no_fault(point, **context):
    pass


def modules():
    from . import git_domain, pr_domain

    return git_domain, pr_domain


def recipe_plan():
    git, pr = modules()
    late_git = {"ref_root_origins", "pr_root_origins", "unknown_root_origins"}
    return (
        [(git, recipe) for recipe in git.RECIPES if recipe not in late_git]
        + [(pr, recipe) for recipe in pr.RECIPES]
        + [(git, recipe) for recipe in git.RECIPES if recipe in late_git]
    )


def definitions():
    columns, keys = {}, {}
    for module in modules():
        for table, value in module.COLUMNS.items():
            if table in columns and columns[table] != value:
                raise ConversionError("INTEGRATED_TABLE_DEFINITION_CONFLICT")
            columns[table] = value
        keys.update(module.KEYS)
    return columns, keys


def integrated_contract():
    columns, keys = definitions()
    from . import identity

    normalized = {
        module.SOURCE_TABLES.get(recipe, recipe)
        for module in (*modules(), identity)
        for recipe in module.RECIPES
    }
    deferred = {
        "cache_entries",
        "cache_leases",
        "content_locations",
        "coverage_components",
        "index_generations",
        "index_membership",
        "preservation_obligations",
        "space_reservations",
    }
    source_tables = [
        item["name"]
        for item in json.loads((source.DESIGN / "current-schema.json").read_bytes())[
            "tables"
        ]
    ]
    return {
        "protocol": PROTOCOL_VERSION,
        "implementation": "scripts.conversion.integrated_phase",
        "recipes": [
            {
                "recipe": recipe,
                "implementation": module.__name__,
                "source_table": module.SOURCE_TABLES.get(recipe, recipe),
            }
            for module, recipe in recipe_plan()
        ],
        "write_ownership": {
            "tables": sorted(columns),
            "operations": ["insert", "reuse", "update_listing_progress"],
        },
        "target_keys": {table: list(keys.get(table, ("id",))) for table in columns},
        "source_dispositions": {
            table: "normalized; invalid/unsupported records stay attributed in the typed archive"
            if table in normalized
            else "deferred operational state; exact typed archive and sealed cache evidence retained"
            if table in deferred
            else "archive preserved; derived search is replaced by original-text scan"
            if table == "search_documents"
            else "archive preserved; source format/migration identity already authenticated"
            for table in source_tables
        },
        "git_verification": "source-owned conversion run and atomic output proofs are the verification pipeline; verify only reconstructable exact Git bytes/hash/size, preserve legacy claims separately",
        "origin_order": "deterministic source-key ref/PR ordinals are reconstructed ordering; exact original roots_manifest array remains preserved",
        "checkpoint": "rows, typed mappings, diagnostics and committed source/output hashes in one transaction",
        "verification": "one authenticated entry/resume audit and one streamed source comparison at exit; deliberate deep audit available",
        "content": "available originals and digest assertions preserved separately; unavailable bytes never become empty bytes",
        "observations": "saved source times, distinct occurrences and A->B->A retained; replay does not advance watermarks",
        "publication": "building, no activation or new current/publication pointers",
    }


def resources():
    ddl, spec, signatures = identity_phase.resources()
    if spec.get("p3_integrated") != integrated_contract():
        raise ConversionError("INVALID_INTEGRATED_CONTRACT")
    return ddl, spec, signatures


def key_values(table, row):
    columns, keys = definitions()
    return tuple(row[columns[table].index(key)] for key in keys.get(table, ("id",)))


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


def find(db, table, row):
    _, keys = definitions()
    return db.execute(
        f"SELECT * FROM {identifier(table)} WHERE "
        + " AND ".join(f"{identifier(key)}=?" for key in keys.get(table, ("id",))),
        key_values(table, row),
    ).fetchone()


def row_hash(row):
    return batch.proof_digest(batch.encode([row]))


def batches(db, src, run, receipt):
    for module, recipe in recipe_plan():
        index, pending = 0, []
        table = module.SOURCE_TABLES.get(recipe, recipe)
        for record in archive.rows(src, table):
            pending.append(record)
            if len(pending) == receipt["batch_size"]:
                records = tuple(pending)
                yield (
                    module,
                    recipe,
                    index,
                    records,
                    input_hash(run, recipe, index, records),
                )
                index, pending = index + 1, []
        if pending or index == 0:
            records = tuple(pending)
            yield (
                module,
                recipe,
                index,
                records,
                input_hash(run, recipe, index, records),
            )


def input_hash(run, recipe, index, records):
    return digest(
        canonical(
            {
                "protocol": PROTOCOL_VERSION,
                "source_id": run["source_id"],
                "recipe": recipe,
                "index": index,
                "records": [
                    [record.key.hex(), record.row_sha256.hex()] for record in records
                ],
            }
        ).encode()
    )


def operation_proof(op):
    value = {
        "record_id": op["record_id"],
        "table": op["table"],
        "operation": op["operation"],
        "key": batch.encode([key_values(op["table"], op["row"])])[0],
        "sha256": row_hash(op["row"]),
    }
    if "before" in op:
        value["before_sha256"] = row_hash(op["before"])
    return value


def compact(output, mapping_ids, diagnostic_ids, stamp):
    return {
        "operations": [operation_proof(op) for op in output["operations"]],
        "decisions": output["decisions"],
        "mapping_ids": mapping_ids,
        "diagnostic_ids": diagnostic_ids,
        "mappings_sha256": row_hash(output["mappings"]),
        "diagnostics_sha256": row_hash(output["diagnostics"]),
        "observed_at": stamp,
    }


def persist_mapping(db, mapped, expected_id):
    record_id, table, key, relation, reason = mapped
    key = bytes.fromhex(key)
    values = [
        v.decode("utf-8") if kind == "text" else v
        for kind, v in archive.decode_key(key)
    ]
    _, keys = definitions()
    names = keys.get(table, ("id",))
    if len(values) != len(names):
        raise ConversionError("INVALID_TARGET_KEY")
    found = db.execute(
        f"SELECT {','.join(identifier(name) for name in names)} FROM {identifier(table)} WHERE "
        + " AND ".join(f"{identifier(name)}=?" for name in names),
        values,
    ).fetchone()
    if found is None or typed_key(tuple(found)) != key:
        raise ConversionError("ID_MAPPING_TARGET_MISSING")
    db.execute(
        "INSERT INTO id_mappings VALUES(?,?,?,?,?,?)",
        (expected_id, record_id, table, key, relation, reason),
    )


def commit(db, run, recipe, index, input_sha256, output, fault=no_fault):
    owners = db.execute(
        "SELECT id FROM conversion_runs WHERE parser_version=?", (PROTOCOL_VERSION,)
    ).fetchall()
    if len(owners) != 1 or owners[0][0] != run["id"]:
        raise ConversionError("INTEGRATED_OWNER_REQUIRED")
    columns, _ = definitions()
    if any(op["table"] not in columns for op in output["operations"]):
        raise ConversionError("INTEGRATED_WRITE_NOT_OWNED")
    first_map, first_diagnostic = (
        batch.next_id(db, "id_mappings"),
        batch.next_id(db, "validation_results"),
    )
    mapping_ids = list(range(first_map, first_map + len(output["mappings"])))
    diagnostic_ids = list(
        range(first_diagnostic, first_diagnostic + len(output["diagnostics"]))
    )
    stamp = now()
    value = compact(output, mapping_ids, diagnostic_ids, stamp)
    proof = canonical(
        {
            "protocol": PROTOCOL_VERSION,
            "recipe": recipe,
            "index": index,
            "output": value,
            "output_sha256": batch.proof_digest(value),
        }
    )
    fault("before_insert", table=recipe, index=index)
    try:
        db.execute("BEGIN IMMEDIATE")
        for op in output["operations"]:
            table, row, operation = op["table"], op["row"], op["operation"]
            actual = find(db, table, row)
            if operation in {"insert", "reuse"}:
                if actual is None:
                    if operation == "reuse":
                        raise ConversionError("INTEGRATED_BEFORE_IMAGE_MISMATCH")
                    db.execute(
                        f"INSERT INTO {identifier(table)} VALUES({','.join('?' for _ in row)})",
                        row,
                    )
                elif tuple(actual) != tuple(row):
                    raise ConversionError("INTEGRATED_OUTPUT_CONFLICT")
            elif (
                operation in {"update", "update_listing_progress"}
                and table == "code_listing_progress"
            ):
                if actual is None or tuple(actual) != tuple(op["before"]):
                    raise ConversionError("INTEGRATED_BEFORE_IMAGE_MISMATCH")
                db.execute(
                    "UPDATE code_listing_progress SET "
                    + ",".join(f"{identifier(c)}=?" for c in columns[table][1:])
                    + " WHERE listing_id=?",
                    [*row[1:], row[0]],
                )
            else:
                raise ConversionError("INVALID_INTEGRATED_OPERATION")
        fault("after_data", table=recipe, index=index)
        for ident, mapped in zip(mapping_ids, output["mappings"], strict=True):
            persist_mapping(db, mapped, ident)
        fault("after_mapping", table=recipe, index=index)
        for ident, diagnostic in zip(
            diagnostic_ids, output["diagnostics"], strict=True
        ):
            db.execute(
                "INSERT INTO validation_results VALUES(?,?,?,?,?,?,?)",
                (ident, run["id"], *diagnostic[:3], stamp, diagnostic[3]),
            )
        db.execute(
            "INSERT INTO conversion_batches VALUES(?,?,?,?,?,?)",
            (
                batch.next_id(db, "conversion_batches"),
                run["id"],
                recipe,
                bytes.fromhex(input_sha256),
                stamp,
                proof,
            ),
        )
        db.execute(
            "UPDATE conversion_runs SET state='building',ended_at=NULL WHERE id=?",
            (run["id"],),
        )
        fault("before_commit", table=recipe, index=index)
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    fault("after_commit", table=recipe, index=index)


def validate_output(db, src, run, receipt, *, require_complete=False, fault=no_fault):
    """Bounded Python buffers; SQLite key ledger compares final owned rows."""
    ledger = sqlite3.connect(":memory:")
    ledger.executescript(
        "CREATE TABLE rows(t TEXT,k BLOB,h TEXT,PRIMARY KEY(t,k)); CREATE TABLE maps(id INTEGER PRIMARY KEY); CREATE TABLE diagnostics(id INTEGER PRIMARY KEY);"
    )
    expected = batches(db, src, run, receipt)
    count = 0
    try:
        for committed in db.execute(
            "SELECT * FROM conversion_batches WHERE run_id=? ORDER BY id", (run["id"],)
        ):
            descriptor = next(expected, None)
            if descriptor is None:
                raise ConversionError("UNEXPECTED_COMMITTED_BATCH")
            module, recipe, index, records, input_sha256 = descriptor
            manifest = json.loads(committed["output_manifest"])
            saved = manifest.get("output", {})
            if (
                set(manifest)
                != {"protocol", "recipe", "index", "output", "output_sha256"}
                or manifest["protocol"] != PROTOCOL_VERSION
                or manifest["recipe"] != recipe
                or manifest["index"] != index
                or committed["source_table"] != recipe
                or committed["input_sha256"].hex() != input_sha256
                or manifest["output_sha256"] != batch.proof_digest(saved)
            ):
                raise ConversionError("INTEGRATED_BATCH_PROOF_MISMATCH")
            output = module.prepare(
                db,
                src,
                run,
                recipe,
                index,
                records,
                encoding=receipt["encoding"],
                verifying=True,
            )
            if saved != compact(
                output,
                saved.get("mapping_ids", []),
                saved.get("diagnostic_ids", []),
                committed["committed_at"],
            ):
                raise ConversionError("INTEGRATED_SOURCE_MISMATCH")
            if len(saved["mapping_ids"]) != len(output["mappings"]) or len(
                saved["diagnostic_ids"]
            ) != len(output["diagnostics"]):
                raise ConversionError("INTEGRATED_BATCH_PROOF_MISMATCH")
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
                        table == "code_listing_progress"
                        and op["operation"] in {"update", "update_listing_progress"}
                        and prior[0] == row_hash(op["before"])
                    )
                ):
                    raise ConversionError("INTEGRATED_OUTPUT_CONFLICT")
                ledger.execute(
                    "INSERT INTO rows VALUES(?,?,?) ON CONFLICT(t,k) DO UPDATE SET h=excluded.h",
                    (table, key, sha),
                )
            for ident, mapped in zip(
                saved["mapping_ids"], output["mappings"], strict=True
            ):
                ledger.execute("INSERT INTO maps VALUES(?)", (ident,))
                row = db.execute(
                    "SELECT * FROM id_mappings WHERE id=?", (ident,)
                ).fetchone()
                if row is None or tuple(row) != (
                    ident,
                    mapped[0],
                    mapped[1],
                    bytes.fromhex(mapped[2]),
                    *mapped[3:],
                ):
                    raise ConversionError("INTEGRATED_MAPPING_MISMATCH")
            for ident, diagnostic in zip(
                saved["diagnostic_ids"], output["diagnostics"], strict=True
            ):
                ledger.execute("INSERT INTO diagnostics VALUES(?)", (ident,))
                row = db.execute(
                    "SELECT * FROM validation_results WHERE id=?", (ident,)
                ).fetchone()
                if row is None or tuple(row) != (
                    ident,
                    run["id"],
                    *diagnostic[:3],
                    committed["committed_at"],
                    diagnostic[3],
                ):
                    raise ConversionError("INTEGRATED_DIAGNOSTIC_MISMATCH")
            count += 1
            fault("during_resume", table=recipe, index=index)
        complete = next(expected, None) is None
        if require_complete and not complete:
            raise ConversionError("INTEGRATED_CONVERSION_INCOMPLETE")
        rows = {}
        for table in definitions()[0]:
            total = 0
            for actual in db.execute(f"SELECT * FROM {identifier(table)}"):
                proof = ledger.execute(
                    "SELECT h FROM rows WHERE t=? AND k=?",
                    (table, typed_key(key_values(table, actual))),
                ).fetchone()
                if proof is None or proof[0] != row_hash(tuple(actual)):
                    raise ConversionError("INTEGRATED_UNLEDGERED_OUTPUT")
                total += 1
            if (
                total
                != ledger.execute(
                    "SELECT count(*) FROM rows WHERE t=?", (table,)
                ).fetchone()[0]
            ):
                raise ConversionError("INTEGRATED_OUTPUT_MISSING")
            rows[table] = total
        if (
            db.execute(
                "SELECT count(*) FROM validation_results WHERE run_id=?", (run["id"],)
            ).fetchone()[0]
            != ledger.execute("SELECT count(*) FROM diagnostics").fetchone()[0]
        ):
            raise ConversionError("INTEGRATED_UNLEDGERED_DIAGNOSTIC")
        return {
            "complete": complete,
            "committed_batches": count,
            "normalized_rows": rows,
            "diagnostics": dict(
                db.execute(
                    "SELECT severity,count(*) FROM validation_results WHERE run_id=? GROUP BY severity",
                    (run["id"],),
                )
            ),
        }
    finally:
        ledger.close()


def receipt_value(parent_run, parent_proof, sealed, signatures, *, stamp, batch_size):
    value = {
        "protocol": PROTOCOL_VERSION,
        "committed_at": stamp,
        "source_id": parent_run["source_id"],
        "parent": parent_proof,
        "signatures": signatures,
        "batch_size": batch_size,
        "encoding": sealed["encoding"],
        "recipes": [recipe for _, recipe in recipe_plan()],
        "write_ownership": integrated_contract()["write_ownership"],
        "activation_permitted": False,
    }
    value["transition_id"] = "p3:" + digest(canonical(value).encode())
    return value


def check_receipt(db, parent_run, parent_proof, sealed, signatures, *, batch_size=None):
    runs = db.execute(
        "SELECT * FROM conversion_runs WHERE parser_version=?", (PROTOCOL_VERSION,)
    ).fetchall()
    if not runs:
        return None, None
    if len(runs) != 1:
        raise ConversionError("PHASE_OWNERSHIP_MISMATCH")
    run = runs[0]
    saved = json.loads(run["manifest"])
    size = saved.get("batch_size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ConversionError("INTEGRATED_RECEIPT_MISMATCH")
    receipt = receipt_value(
        parent_run,
        parent_proof,
        sealed,
        signatures,
        stamp=run["started_at"],
        batch_size=size,
    )
    if (
        run["id"] != receipt["transition_id"]
        or run["source_id"] != parent_run["source_id"]
        or run["manifest"] != canonical(receipt)
        or run["state"] not in {"building", "paused"}
        or run["ended_at"] not in {None, run["started_at"]}
    ):
        raise ConversionError("INTEGRATED_RECEIPT_MISMATCH")
    if batch_size is not None and size != batch_size:
        raise ConversionError("RESUME_OPTIONS_MISMATCH")
    return run, receipt


def _entry(db, src, sealed, spec, signatures, batch_size=None, fault=no_fault):
    from . import integrated_parent

    parent_run, _, _, parent_proof = integrated_parent.check_parent(
        db, src, sealed, spec, signatures, definitions()[0]
    )
    run, receipt = check_receipt(
        db, parent_run, parent_proof, sealed, signatures, batch_size=batch_size
    )
    status = validate_output(db, src, run, receipt, fault=fault) if run else None
    return parent_run, parent_proof, run, receipt, status


def _status(receipt, status, new_batches=0, *, exit_comparisons=1):
    parent_counts = receipt["parent"]["diagnostics"]
    return {
        **status,
        "phase": PROTOCOL_VERSION,
        "lifecycle": "building",
        "activation_permitted": False,
        "normalized_ready": bool(
            status["complete"]
            and not status["diagnostics"].get("blocking", 0)
            and not parent_counts.get("blocking", 0)
        ),
        "parent_diagnostics": parent_counts,
        "new_batches": new_batches,
        "verification": {"entry_audits": 1, "exit_comparisons": exit_comparisons},
    }


def convert(
    workspace, *, batch_size=100, max_batches=None, fault=no_fault, free_bytes=None
):
    from . import integrated_parent

    workspace = Path(workspace)
    if (
        batch_size < 1
        or isinstance(batch_size, bool)
        or (max_batches is not None and max_batches < 0)
    ):
        raise ConversionError("INVALID_BATCH_OPTIONS")
    _, spec, signatures = resources()
    with (
        target.writer_lock(workspace),
        source.readonly(workspace / "source.sqlite3") as src,
    ):
        sealed = source.verify_seal(workspace, allow_legacy=True)
        path = identity_phase._destination(workspace)
        journal = Path(str(path) + "-journal")
        hot = journal.exists() and identity_phase._hot_journal(journal)
        original_stat = stat_identity(path)
        with target.readonly_destination(path) as existing:
            if hot:
                integrated_parent.pending(
                    existing, sealed, spec, signatures, definitions()[0]
                )
                checked = None
            else:
                checked = _entry(
                    existing, src, sealed, spec, signatures, batch_size, fault
                )
        if not hot and stat_identity(path) != original_stat:
            raise ConversionError("TARGET_CHANGED_DURING_OPEN")
        db = target.connect(path)
        try:
            if hot or stat_identity(path) != original_stat:
                checked = _entry(db, src, sealed, spec, signatures, batch_size, fault)
            parent_run, parent_proof, run, receipt, status = checked
            if not run:
                receipt = receipt_value(
                    parent_run,
                    parent_proof,
                    sealed,
                    signatures,
                    stamp=now(),
                    batch_size=batch_size,
                )
                capacity.preflight(
                    workspace,
                    {
                        "required_free_bytes": 64 * 1024 * 1024
                        + 4 * len(canonical(receipt).encode())
                    },
                    free_bytes=free_bytes,
                )
                db.execute("BEGIN IMMEDIATE")
                try:
                    db.execute(
                        "INSERT INTO conversion_runs VALUES(?,?,?,?,?,'paused',?)",
                        (
                            receipt["transition_id"],
                            parent_run["source_id"],
                            receipt["committed_at"],
                            receipt["committed_at"],
                            PROTOCOL_VERSION,
                            canonical(receipt),
                        ),
                    )
                    fault("before_integrated_init_commit")
                    db.execute("COMMIT")
                except BaseException:
                    if db.in_transaction:
                        db.rollback()
                    raise
                fault("after_integrated_init_commit")
                run = db.execute(
                    "SELECT * FROM conversion_runs WHERE id=?",
                    (receipt["transition_id"],),
                ).fetchone()
                status = {"committed_batches": 0}
            new_batches = 0
            for ordinal, descriptor in enumerate(batches(db, src, run, receipt)):
                if ordinal < status["committed_batches"]:
                    continue
                if max_batches is not None and new_batches >= max_batches:
                    break
                module, recipe, index, records, input_sha256 = descriptor
                output = module.prepare(
                    db, src, run, recipe, index, records, encoding=receipt["encoding"]
                )
                commit(db, run, recipe, index, input_sha256, output, fault)
                new_batches += 1
            exit_comparisons = int(new_batches > 0 or "complete" not in status)
            if exit_comparisons:
                status = validate_output(db, src, run, receipt)
            parent_view = integrated_parent.ParentView(
                db, run, frozenset(definitions()[0])
            )
            if integrated_parent._proof(parent_view) != parent_proof["proof_sha256"]:
                raise ConversionError("INTEGRATED_PARENT_PROOF_MISMATCH")
            if (
                db.execute("PRAGMA foreign_key_check").fetchone()
                or db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            ):
                raise ConversionError("TARGET_INTEGRITY_FAILURE")
            source.verify_seal(workspace, allow_legacy=True)
            return _status(
                receipt, status, new_batches, exit_comparisons=exit_comparisons
            )
        finally:
            db.close()


def verify(workspace):
    workspace = Path(workspace)
    _, spec, signatures = resources()
    with (
        target.writer_lock(workspace),
        source.readonly(workspace / "source.sqlite3") as src,
    ):
        sealed = source.verify_seal(workspace, allow_legacy=True)
        path = identity_phase._destination(workspace)
        if any(
            os.path.lexists(str(path) + suffix)
            for suffix in ("-journal", "-wal", "-shm")
        ):
            raise ConversionError("TARGET_SIDECAR_UNSUPPORTED")
        with target.readonly_destination(path) as db:
            _, _, run, receipt, status = _entry(db, src, sealed, spec, signatures)
            if run is None:
                raise ConversionError("INTEGRATED_PHASE_NOT_COMMITTED")
            source.verify_seal(workspace, allow_legacy=True)
            return _status(receipt, status, exit_comparisons=0)
