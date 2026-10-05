import json
import sqlite3
from pathlib import Path

from . import archive, batch, capacity, diagnostics, guards, source, target
from .common import ConversionError, canonical, require_local_filesystem


def no_fault(point, **context):
    pass


def run(policy, action, workspace, **options):
    """Supported entry point requires a worker's installed, immutable policy.

    Component functions below are also used by isolated synthetic unit tests;
    they are not an alternative unguarded conversion command.
    """
    if (
        not isinstance(policy, guards.WorkerPolicy)
        or policy.workspace != Path(workspace).resolve()
    ):
        raise ConversionError("GUARDED_WORKER_REQUIRED")
    if sqlite3.sqlite_version_info < (3, 46, 1):
        raise ConversionError("UNSUPPORTED_SQLITE_RUNTIME")
    if action == "seal":
        return seal_input(workspace=workspace, **options)
    if action == "archive":
        return convert(workspace, **options)
    if action == "verify":
        return verify(workspace, **options)
    raise ConversionError("UNKNOWN_CONVERSION_ACTION")


def seal_input(source_path, workspace, caches=(), *, free_bytes=None):
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    require_local_filesystem(workspace)
    with source.readonly(source_path) as db:
        source.identify(db)
        spec = json.loads((source.DESIGN / "conversion-contract.json").read_bytes())
        tables = {row["table"] for row in spec["source_columns"]}
        required = capacity.estimate(db, tables, Path(source_path).stat().st_size)
    capacity.preflight(workspace, required, free_bytes=free_bytes)
    # Cache evidence can be large even when the DB is tiny. Account for the
    # descriptor, target manifest and its rollback journal before copying.
    evidence = source.cache_inventory(caches)
    with source.readonly(source_path) as db:
        required = capacity.estimate(
            db,
            tables,
            Path(source_path).stat().st_size,
            len(
                canonical({"caches": evidence, "source": source.identify(db)}).encode()
            ),
        )
    capacity.preflight(workspace, required, free_bytes=free_bytes)
    with target.writer_lock(workspace):
        return source.seal(source_path, workspace, caches, expected_cache=evidence)


def validate_ledger(db, run, expected, fault):
    previous = db.execute(
        "SELECT * FROM conversion_batches WHERE run_id=? ORDER BY id", (run["id"],)
    ).fetchall()
    totals = {
        name: 0
        for name in ("legacy_records", "legacy_values", "repositories", "id_mappings")
    }
    for committed, (table, index, records, input_sha256) in zip(
        previous, expected, strict=False
    ):
        manifest = batch.validate_output(db, committed)
        if (
            committed["source_table"] != table
            or manifest["index"] != index
            or committed["input_sha256"].hex() != input_sha256
        ):
            raise ConversionError("COMMITTED_INPUT_MISMATCH")
        for name in totals:
            totals[name] += len(manifest["proof"][name])
        fault("during_resume", table=table, index=index)
    if len(previous) > len(expected):
        raise ConversionError("UNEXPECTED_COMMITTED_BATCH")
    for name, count in totals.items():
        if db.execute(f"SELECT count(*) FROM {name}").fetchone()[0] != count:
            raise ConversionError("UNLEDGERED_OUTPUT")
    return len(previous)


def convert(
    workspace,
    *,
    batch_size=100,
    map_repositories=False,
    max_batches=None,
    ddl=None,
    contract=None,
    free_bytes=None,
    fault=no_fault,
):
    """Archive foundation only. Never validated/active and never normal sync."""
    workspace = Path(workspace)
    if batch_size < 1 or (max_batches is not None and max_batches < 0):
        raise ConversionError("INVALID_BATCH_OPTIONS")
    require_local_filesystem(workspace)
    sealed = source.verify_seal(workspace)
    ddl_bytes, spec, signatures = target.resources(ddl, contract)
    tables = {row["table"] for row in spec["source_columns"]}
    with (
        target.writer_lock(workspace),
        source.readonly(workspace / "source.sqlite3") as src,
    ):
        required = capacity.estimate(
            src,
            tables,
            (workspace / "source.sqlite3").stat().st_size,
            len(canonical(sealed).encode()),
        )
        checked = capacity.preflight(workspace, required, free_bytes=free_bytes)
        destination = workspace / "target.sqlite3"
        if not destination.exists():
            target.create(
                workspace,
                sealed,
                ddl_bytes,
                signatures,
                checked,
                batch_size=batch_size,
                map_repositories=map_repositories,
                source_issues=diagnostics.source_issues(src),
            )
        db = target.connect(destination)
        try:
            run, manifest = target.verify(
                db,
                sealed,
                signatures,
                batch_size=batch_size,
                map_repositories=map_repositories,
            )
            # Input fingerprints are computed before any write transaction.
            # P2 keeps just batch descriptors; no full source payload in RAM.
            descriptors = [
                (
                    table,
                    index,
                    (),
                    archive.input_manifest(
                        sealed["sealed"]["sha256"], table, index, records
                    ),
                )
                for table, index, records in archive.batches(src, tables, batch_size)
            ]
            completed = validate_ledger(db, run, descriptors, fault)
            if manifest["archive_complete"] and completed != len(descriptors):
                raise ConversionError("ARCHIVE_COMPLETENESS_MISMATCH")
            committed = 0
            for position, (table, index, records) in enumerate(
                archive.batches(src, tables, batch_size)
            ):
                if position < completed:
                    continue
                if max_batches is not None and committed >= max_batches:
                    break
                output = batch.prepare(
                    db,
                    run["source_id"],
                    run["id"],
                    records,
                    map_repositories=map_repositories,
                    encoding=sealed["encoding"],
                )
                batch.commit(
                    db,
                    run,
                    table,
                    index,
                    descriptors[position][3],
                    output,
                    lambda point: fault(point, table=table, index=index),
                )
                committed += 1
            finished = completed + committed == len(descriptors)
            # Detect input/cache mutation during this execution, too.
            source.verify_seal(workspace)
            validate_ledger(db, run, descriptors, no_fault)
            manifest["archive_complete"] = finished
            manifest["committed_batches"] = completed + committed
            text = canonical(manifest)
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE conversion_runs SET state='paused',manifest=? WHERE id=?",
                (text, run["id"]),
            )
            db.execute("COMMIT")
            return {
                "archive_complete": finished,
                "committed_batches": completed + committed,
                "new_batches": committed,
                "lifecycle": "building",
                "diagnostics": diagnostics.counts(db, run["id"]),
            }
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()


def verify(workspace, *, ddl=None, contract=None):
    workspace = Path(workspace)
    sealed = source.verify_seal(workspace)
    _, spec, signatures = target.resources(ddl, contract)
    with (
        target.writer_lock(workspace),
        source.readonly(workspace / "source.sqlite3") as src,
    ):
        # Verification must never create an absent destination.
        with source.readonly(workspace / "target.sqlite3") as db:
            run, manifest = target.verify(db, sealed, signatures)
            tables = {row["table"] for row in spec["source_columns"]}
            expected = [
                (
                    table,
                    index,
                    (),
                    archive.input_manifest(
                        sealed["sealed"]["sha256"], table, index, records
                    ),
                )
                for table, index, records in archive.batches(
                    src, tables, manifest["batch_size"]
                )
            ]
            count = validate_ledger(db, run, expected, no_fault)
            if manifest["archive_complete"] and count != len(expected):
                raise ConversionError("ARCHIVE_COMPLETENESS_MISMATCH")
            return {
                "archive_complete": manifest["archive_complete"],
                "committed_batches": count,
                "lifecycle": "building",
                "diagnostics": diagnostics.counts(db, run["id"]),
            }
