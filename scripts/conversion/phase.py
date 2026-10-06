"""Verified, atomic P2 -> P3A receipt; domain recipes are a later protocol.

One additional conversion_runs row owns the destination. The parent P2 run,
archive, mappings, diagnostics and batches remain unchanged. P3A only inserts
this receipt: a future domain writer must supply a reviewed phase protocol and
its own output proofs before changing any normalized value.
"""

from collections import Counter
from pathlib import Path

from scripts.schema_contract import tagged_key

from . import archive, batch, capacity, diagnostics, mapping, source, target
from .common import PARSER_VERSION, ConversionError, canonical, digest, now

PROTOCOL_VERSION = "p3a-handoff/1"
REVIEWED_PREDECESSOR_REVISION = "1e052e4b666039704ad0b8ea3a1d7a752d561358"


def no_fault(point, **context):
    pass


def _require_predecessor_layout(manifest, sealed):
    legacy_fields = {
        "format_id",
        "db_instance_id",
        "schema_sha256",
        "catalog",
        "migrations",
        "encoding",
        "original",
        "sealed",
        "caches",
    }
    reviewed = manifest["converter_sha256"] in target.REVIEWED_P2_CONVERTERS
    if reviewed != (set(sealed) == legacy_fields):
        raise ConversionError("UNSUPPORTED_P2_PREDECESSOR_LAYOUT")


def _exact_archive(db, src, run, manifest, tables, encoding):
    """Recompute source relationships independently of mutable output hashes."""
    expected_maps, expected_repositories, expected_diagnostics = [], [], Counter()
    record_count = 0
    for table in sorted(tables):
        for record in archive.rows(src, table):
            record_count += 1
            saved = db.execute(
                "SELECT id,row_sha256 FROM legacy_records WHERE source_id=? AND source_table=? AND source_key=?",
                (run["source_id"], table, record.key),
            ).fetchone()
            if saved is None or saved["row_sha256"] != record.row_sha256:
                raise ConversionError("ARCHIVE_SOURCE_MISMATCH")
            values = [
                tuple(row)
                for row in db.execute(
                    "SELECT column_name,storage_type,value_bytes FROM legacy_values WHERE record_id=? ORDER BY column_name",
                    (saved["id"],),
                )
            ]
            if values != sorted(record.values):
                raise ConversionError("ARCHIVE_SOURCE_MISMATCH")
            issues = diagnostics.classify(record, encoding)
            if manifest["map_repositories"] and table == "repositories":
                try:
                    projected = mapping.repository_projection(record)
                    key = tagged_key([("text", projected["id"].encode())])
                    expected_repositories.append(
                        (
                            projected["id"],
                            projected["name"],
                            None,
                            None,
                            projected["metadata"],
                        )
                    )
                    expected_maps.append(
                        (
                            saved["id"],
                            "repositories",
                            key,
                            "identity",
                            "P2 representative repository; preserve local ID",
                        )
                    )
                except ConversionError as exc:
                    issues.append((exc.code, "blocking", "id"))
            expected_diagnostics.update(
                (
                    "I31",
                    code,
                    severity,
                    canonical({"record_id": saved["id"], "column": column}),
                )
                for code, severity, column in issues
            )
    if db.execute("SELECT count(*) FROM legacy_records").fetchone()[0] != record_count:
        raise ConversionError("ARCHIVE_SOURCE_MISMATCH")
    if sorted(expected_maps) != sorted(
        tuple(row)[1:] for row in db.execute("SELECT * FROM id_mappings")
    ) or sorted(expected_repositories) != sorted(
        tuple(row) for row in db.execute("SELECT * FROM repositories")
    ):
        raise ConversionError("MAPPING_SOURCE_MISMATCH")
    actual_issues = diagnostics.source_issues(src)
    if Counter(map(canonical, actual_issues)) != Counter(
        map(canonical, manifest["source_fk_issues"])
    ):
        raise ConversionError("SOURCE_DIAGNOSTIC_MISMATCH")
    if actual_issues:
        expected_diagnostics.update(
            [
                (
                    "I01",
                    "SOURCE_FOREIGN_KEY_VIOLATION",
                    "blocking",
                    canonical({"count": len(actual_issues)}),
                )
            ]
        )
    actual_diagnostics = Counter(
        (row["invariant_id"], row["code"], row["severity"], row["details"])
        for row in db.execute(
            "SELECT * FROM validation_results WHERE run_id=?", (run["id"],)
        )
    )
    if actual_diagnostics != expected_diagnostics:
        raise ConversionError("DIAGNOSTIC_SOURCE_MISMATCH")


def _parent(db, src, sealed, spec, signatures, parent_id):
    from .engine import validate_ledger

    run, manifest = target.verify(
        db,
        sealed,
        signatures,
        run_id=parent_id,
        allow_reviewed_predecessor=True,
    )
    _require_predecessor_layout(manifest, sealed)
    if not manifest["archive_complete"] or run["state"] != "paused":
        raise ConversionError("P2_ARCHIVE_INCOMPLETE")
    tables = {row["table"] for row in spec["source_columns"]}
    expected = [
        (
            table,
            index,
            (),
            archive.input_manifest(sealed["sealed"]["sha256"], table, index, records),
        )
        for table, index, records in archive.batches(
            src, tables, manifest["batch_size"]
        )
    ]
    completed = validate_ledger(db, run, expected, no_fault)
    if completed != len(expected) or manifest.get("committed_batches") != completed:
        raise ConversionError("ARCHIVE_COMPLETENESS_MISMATCH")
    _exact_archive(db, src, run, manifest, tables, sealed["encoding"])
    if db.execute("SELECT count(*) FROM conversion_sources").fetchone()[0] != 1:
        raise ConversionError("RESUME_SOURCE_LEDGER_MISMATCH")
    if db.execute(
        "SELECT 1 FROM conversion_batches WHERE run_id!=?", (run["id"],)
    ).fetchone():
        raise ConversionError("UNEXPECTED_COMMITTED_BATCH")
    allowed_tables = {
        "database_identity",
        "conversion_sources",
        "conversion_runs",
        "conversion_batches",
        "legacy_records",
        "legacy_values",
        "id_mappings",
        "validation_results",
        "repositories",
    }
    for (name,) in db.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        if (
            name not in allowed_tables
            and db.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone()
        ):
            raise ConversionError("UNLEDGERED_OUTPUT")
    identity = dict(db.execute("SELECT * FROM database_identity").fetchone())
    if identity["publication_seq"] != 0:
        raise ConversionError("TARGET_IDENTITY_MISMATCH")
    # Hash frozen metadata and every accepted output proof, retaining IDs and
    # converter event timestamps without duplicating archived payload bytes.
    evidence = {
        "run": batch.encode([tuple(run)]),
        "source": batch.encode(
            [tuple(db.execute("SELECT * FROM conversion_sources").fetchone())]
        ),
        "identity": batch.encode(
            [tuple(db.execute("SELECT * FROM database_identity").fetchone())]
        ),
        "batches": batch.encode(
            [
                tuple(row)
                for row in db.execute("SELECT * FROM conversion_batches ORDER BY id")
            ]
        ),
        "maps": batch.encode(
            [tuple(row) for row in db.execute("SELECT * FROM id_mappings ORDER BY id")]
        ),
        "diagnostics": batch.encode(
            [
                tuple(row)
                for row in db.execute("SELECT * FROM validation_results ORDER BY id")
            ]
        ),
    }
    return run, manifest, digest(canonical(evidence).encode()), identity


def _receipt(db, src, sealed, spec, signatures, parent_id, committed_at):
    run, manifest, parent_sha256, identity = _parent(
        db, src, sealed, spec, signatures, parent_id
    )
    admitted = source.identify(src)
    value = {
        "phase_protocol": PROTOCOL_VERSION,
        "state": "committed",
        "committed_at": committed_at,
        "source": {
            "source_id": run["source_id"],
            "physical_sha256": sealed["sealed"]["sha256"],
            "core_schema_sha256": sealed["schema_sha256"],
            "full_schema_sha256": admitted["source_schema_sha256"],
            "seal_sha256": digest(canonical(sealed).encode()),
            "preservation_dispositions_sha256": digest(
                canonical(admitted["preservation_dispositions"]).encode()
            ),
        },
        "parent": {
            "run_id": run["id"],
            "parser_version": run["parser_version"],
            "converter_sha256": manifest["converter_sha256"],
            "proof_sha256": parent_sha256,
            "reviewed_predecessor_revision": REVIEWED_PREDECESSOR_REVISION
            if manifest["converter_sha256"] in target.REVIEWED_P2_CONVERTERS
            else None,
        },
        "target": {
            "db_instance_id": identity["db_instance_id"],
            "format_id": identity["format_id"],
            "schema_version": identity["schema_version"],
            "lifecycle": "building",
        },
        "signatures": signatures,
        "write_ownership": {
            "owner": PROTOCOL_VERSION,
            "initialization": "one phase receipt INSERT in conversion_runs",
            "immutable_parent": [
                "conversion_sources",
                "conversion_runs:parent",
                "conversion_batches",
                "legacy_records",
                "legacy_values",
                "id_mappings",
                "validation_results",
                "repositories",
            ],
            "normalized_writes": [],
        },
        "diagnostics": diagnostics.counts(db, run["id"]),
        "activation_permitted": False,
    }
    value["transition_id"] = "p3a:" + digest(canonical(value).encode())
    return value


def _owners(db):
    runs = db.execute("SELECT * FROM conversion_runs ORDER BY id").fetchall()
    parents = [run for run in runs if run["parser_version"] == PARSER_VERSION]
    phases = [run for run in runs if run["parser_version"] == PROTOCOL_VERSION]
    if len(parents) != 1 or len(phases) > 1 or len(runs) != 1 + len(phases):
        raise ConversionError("PHASE_OWNERSHIP_MISMATCH")
    return parents, phases


def _check(db, src, sealed, spec, signatures, *, require_phase):
    parents, phases = _owners(db)
    if require_phase and not phases:
        raise ConversionError("P3_PHASE_NOT_COMMITTED")
    receipt = _receipt(
        db,
        src,
        sealed,
        spec,
        signatures,
        parents[0]["id"],
        phases[0]["started_at"] if phases else now(),
    )
    if phases:
        phase_run = phases[0]
        if (
            phase_run["id"] != receipt["transition_id"]
            or phase_run["source_id"] != parents[0]["source_id"]
            or phase_run["state"] != "paused"
            or phase_run["started_at"] != phase_run["ended_at"]
            or not phase_run["started_at"]
            or phase_run["manifest"] != canonical(receipt)
        ):
            raise ConversionError("PHASE_RECEIPT_MISMATCH")
    return receipt, bool(phases)


def _result(receipt, *, created=False):
    return {
        "phase": PROTOCOL_VERSION,
        "transition_id": receipt["transition_id"],
        "parent_proof_sha256": receipt["parent"]["proof_sha256"],
        "phase_committed": True,
        "new_phase": created,
        "archive_complete": True,
        "lifecycle": "building",
        "activation_permitted": False,
        "diagnostics": receipt["diagnostics"],
    }


def handoff(workspace, *, ddl=None, contract=None, free_bytes=None, fault=no_fault):
    workspace = Path(workspace)
    _, spec, signatures = target.resources(ddl, contract)
    with target.writer_lock(workspace):
        sealed = source.verify_seal(workspace, allow_legacy=True)
        destination = workspace / "target.sqlite3"
        if destination.is_symlink() or not destination.is_file():
            raise ConversionError("DESTINATION_MISSING_OR_NOT_REGULAR")
        # A writable open can change the header through journal_mode, so prove
        # the recognized owner and complete predecessor before target recovery.
        with (
            target.readonly_destination(destination) as existing,
            source.readonly(workspace / "source.sqlite3") as src,
        ):
            if Path(str(destination) + "-journal").exists():
                # Immutable reads ignore rollback journals and can expose an
                # uncommitted spilled receipt. Recognize only the bounded owner
                # and exact predecessor here; never report success until the
                # accepted target's journal has been recovered and all output
                # proofs have been checked again on the recovered connection.
                headers = existing.execute(
                    "SELECT parser_version FROM conversion_runs"
                ).fetchall()
                if len(headers) == 2:
                    target.require_pending_handoff(
                        existing, sealed, signatures, allow_reviewed=True
                    )
                    parents, phases = [], []
                else:
                    parents, phases = _owners(existing)
                if parents:
                    _, manifest = target.verify(
                        existing,
                        sealed,
                        signatures,
                        run_id=parents[0]["id"],
                        allow_reviewed_predecessor=True,
                        check_integrity=False,
                    )
                    _require_predecessor_layout(manifest, sealed)
            else:
                receipt, exists = _check(
                    existing, src, sealed, spec, signatures, require_phase=False
                )
                if exists:
                    return _result(receipt)
        # Only target recovery is writable; sealed/original sidecars still fail.
        db = target.connect(destination)
        try:
            with source.readonly(workspace / "source.sqlite3") as src:
                receipt, exists = _check(
                    db, src, sealed, spec, signatures, require_phase=False
                )
            if exists:
                return _result(receipt)
            capacity.preflight(
                workspace,
                {
                    "required_free_bytes": 4 * len(canonical(receipt).encode())
                    + 64 * 1024 * 1024
                },
                free_bytes=free_bytes,
            )
            source.verify_seal(workspace, allow_legacy=True)
            stamp = receipt["committed_at"]
            receipt_text = canonical(receipt)
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO conversion_runs VALUES(?,?,?,?,?,'paused',?)",
                (
                    receipt["transition_id"],
                    receipt["source"]["source_id"],
                    stamp,
                    stamp,
                    PROTOCOL_VERSION,
                    receipt_text,
                ),
            )
            fault("before_handoff_commit", transition_id=receipt["transition_id"])
            db.execute("COMMIT")
            fault("after_handoff_commit", transition_id=receipt["transition_id"])
            return _result(receipt, created=True)
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()


def verify(workspace, *, ddl=None, contract=None):
    workspace = Path(workspace)
    _, spec, signatures = target.resources(ddl, contract)
    with target.writer_lock(workspace):
        sealed = source.verify_seal(workspace, allow_legacy=True)
        with (
            source.readonly(workspace / "source.sqlite3") as src,
            source.readonly(workspace / "target.sqlite3") as db,
        ):
            receipt, _ = _check(db, src, sealed, spec, signatures, require_phase=True)
            return _result(receipt)
