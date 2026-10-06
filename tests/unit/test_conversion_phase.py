"""Synthetic phase receipts, exact preservation, ownership and fault boundary."""

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from scripts.conversion import batch, diagnostics, engine, phase, source, target
from scripts.conversion.common import DESIGN, ConversionError, canonical
from tests.support.conversion_fixture import make_source


@pytest.fixture
def archived(tmp_path):
    database = tmp_path / "v2.sqlite3"
    cache = make_source(database)
    workspace = tmp_path / "workspace"
    engine.seal_input(database, workspace, [cache])
    engine.convert(workspace, batch_size=2, map_repositories=True)
    return database, cache, workspace


def parent_evidence(workspace):
    with source.readonly(workspace / "target.sqlite3") as db:
        return {
            table: batch.encode(
                [tuple(row) for row in db.execute(f"SELECT * FROM {table}")]
            )
            for table in (
                "conversion_sources",
                "conversion_batches",
                "legacy_records",
                "legacy_values",
                "repositories",
                "id_mappings",
                "validation_results",
            )
        }


@contextmanager
def without_immutable_triggers(db, *names):
    before = target.schema_fingerprint(db)
    statements = [
        db.execute("SELECT sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()[0]
        for name in names
    ]
    for name in names:
        db.execute(f'DROP TRIGGER "{name}"')
    try:
        yield
    finally:
        for statement in statements:
            db.execute(statement)
    assert target.schema_fingerprint(db) == before


def test_complete_handoff_restart_keeps_all_parent_evidence(archived):
    database, cache, workspace = archived
    before = (
        database.read_bytes(),
        source.cache_inventory([cache]),
        parent_evidence(workspace),
    )
    first = phase.handoff(workspace)
    assert first["new_phase"] and first["phase_committed"]
    assert first["lifecycle"] == "building" and not first["activation_permitted"]
    assert first["diagnostics"]["blocking"] > 0
    assert phase.verify(workspace) == {**first, "new_phase": False}
    assert phase.handoff(workspace) == {**first, "new_phase": False}
    assert before == (
        database.read_bytes(),
        source.cache_inventory([cache]),
        parent_evidence(workspace),
    )
    with source.readonly(workspace / "target.sqlite3") as db:
        runs = list(db.execute("SELECT * FROM conversion_runs"))
        assert len(runs) == 2
        receipt = json.loads(
            next(
                row["manifest"]
                for row in runs
                if row["parser_version"] == phase.PROTOCOL_VERSION
            )
        )
        assert receipt["write_ownership"]["normalized_writes"] == []
        with source.readonly(workspace / "source.sqlite3") as src:
            assert (
                receipt["source"]["full_schema_sha256"]
                == source.identify(src)["source_schema_sha256"]
            )


def test_incomplete_archive_cannot_handoff(tmp_path):
    database = tmp_path / "v2.sqlite3"
    cache = make_source(database)
    workspace = tmp_path / "workspace"
    engine.seal_input(database, workspace, [cache])
    engine.convert(workspace, batch_size=2, max_batches=1)
    before = parent_evidence(workspace)
    with pytest.raises(ConversionError, match="P2_ARCHIVE_INCOMPLETE"):
        phase.handoff(workspace)
    assert before == parent_evidence(workspace)


@pytest.mark.parametrize("point", ["before_handoff_commit", "after_handoff_commit"])
def test_transition_fault_is_atomic_and_repeatable(archived, point):
    _, _, workspace = archived
    before = parent_evidence(workspace)

    def fault(actual, **context):
        if point == actual:
            raise ConversionError("INJECTED_FAILURE")

    with pytest.raises(ConversionError, match="INJECTED_FAILURE"):
        phase.handoff(workspace, fault=fault)
    with source.readonly(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == (
            2 if point == "after_handoff_commit" else 1
        )
    if point == "before_handoff_commit":
        assert engine.verify(workspace)["archive_complete"]
    result = phase.handoff(workspace)
    assert result["new_phase"] == (point == "before_handoff_commit")
    assert phase.verify(workspace)["transition_id"] == result["transition_id"]
    assert before == parent_evidence(workspace)


def test_writer_lock_covers_handoff_and_verification(archived):
    _, _, workspace = archived
    with target.writer_lock(workspace):
        with pytest.raises(ConversionError, match="CONVERTER_ALREADY_RUNNING"):
            phase.handoff(workspace)
        with pytest.raises(ConversionError, match="CONVERTER_ALREADY_RUNNING"):
            phase.verify(workspace)


def test_p2_rejects_owned_destination_before_writable_connect(archived, monkeypatch):
    _, _, workspace = archived
    phase.handoff(workspace)
    before = (workspace / "target.sqlite3").read_bytes()

    def forbidden(path):
        raise AssertionError("P2 opened a P3 destination writable")

    monkeypatch.setattr(target, "connect", forbidden)
    with pytest.raises(ConversionError, match="PHASE_OWNERSHIP_MISMATCH"):
        engine.convert(workspace, batch_size=2, map_repositories=True)
    assert before == (workspace / "target.sqlite3").read_bytes()


@pytest.mark.parametrize(
    "change",
    [
        "converter",
        "source",
        "ddl",
        "contract",
        "extra-diagnostic",
        "initial-diagnostic",
        "core-receipt",
    ],
)
def test_invalid_boundary_rejected(archived, tmp_path, change):
    database, _, workspace = archived
    options = {}
    if change in {"ddl", "contract"}:
        filename = (
            "target-schema.sql" if change == "ddl" else "conversion-contract.json"
        )
        altered = tmp_path / filename
        altered.write_bytes((DESIGN / filename).read_bytes() + b"\n")
        options[change] = altered
    elif change == "source":
        database.chmod(0o644)
        with target.connect(database) as db:
            db.execute("UPDATE catalog_meta SET publication_seq=99")
    else:
        with target.connect(workspace / "target.sqlite3") as db:
            run = db.execute("SELECT * FROM conversion_runs").fetchone()
            if change == "extra-diagnostic":
                db.execute(
                    "INSERT INTO validation_results(run_id,invariant_id,code,severity,observed_at,details) VALUES(?,'I31','UNEXPECTED','blocking','2026-01-01','{}')",
                    (run["id"],),
                )
            elif change == "initial-diagnostic":
                with without_immutable_triggers(db, "validation_results_immutable"):
                    db.execute(
                        "UPDATE validation_results SET details='{}' WHERE code='SOURCE_FOREIGN_KEY_VIOLATION'"
                    )
            else:
                manifest = json.loads(run["manifest"])
                if change == "converter":
                    manifest["converter_sha256"] = "0" * 64
                else:
                    manifest["seal"]["db_instance_id"] = "changed"
                db.execute(
                    "UPDATE conversion_runs SET manifest=?", (canonical(manifest),)
                )
    with pytest.raises(ConversionError):
        phase.handoff(workspace, **options)
    with source.readonly(workspace / "target.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == 1


@pytest.mark.parametrize(
    "name", ["legacy_values", "repositories", "validation_results", "id_mappings"]
)
def test_coherently_rehashed_output_cannot_replace_source_proof(archived, name):
    _, _, workspace = archived
    with (
        target.connect(workspace / "target.sqlite3") as db,
        without_immutable_triggers(
            db,
            "conversion_batches_immutable",
            "id_mappings_immutable",
            "validation_results_immutable",
        ),
    ):
        if name == "legacy_values":
            saved = db.execute(
                "SELECT * FROM legacy_values WHERE storage_type='blob' LIMIT 1"
            ).fetchone()
            statement = db.execute(
                "SELECT sql FROM sqlite_schema WHERE name='legacy_values_immutable'"
            ).fetchone()[0]
            db.execute("DROP TRIGGER legacy_values_immutable")
            db.execute(
                "UPDATE legacy_values SET value_bytes=x'cafe' WHERE record_id=? AND column_name=?",
                (saved["record_id"], saved["column_name"]),
            )
            db.execute(statement)
        elif name == "repositories":
            db.execute("UPDATE repositories SET name='changed'")
        elif name == "validation_results":
            db.execute(
                "UPDATE validation_results SET code='CHANGED' WHERE invariant_id='I31'"
            )
        else:
            db.execute("UPDATE id_mappings SET reason='CHANGED'")
        for committed in db.execute("SELECT * FROM conversion_batches").fetchall():
            manifest = json.loads(committed["output_manifest"])
            for proof in manifest["proof"][name]:
                key = proof["key"]
                if name == "legacy_values":
                    found = db.execute(
                        "SELECT * FROM legacy_values WHERE record_id=? AND column_name=?",
                        key,
                    ).fetchone()
                else:
                    found = db.execute(
                        f"SELECT * FROM {name} WHERE id=?", (key[0],)
                    ).fetchone()
                proof["sha256"] = batch.row_proof(name, tuple(found))["sha256"]
            manifest["output_sha256"] = batch.proof_digest(manifest["proof"])
            db.execute(
                "UPDATE conversion_batches SET output_manifest=? WHERE id=?",
                (canonical(manifest), committed["id"]),
            )
    with pytest.raises(
        ConversionError, match="(ARCHIVE|MAPPING|DIAGNOSTIC)_SOURCE_MISMATCH"
    ):
        phase.handoff(workspace)


@pytest.mark.parametrize(
    "change",
    ["manifest", "parent", "state", "extra-phase", "timestamp", "coherent-timestamp"],
)
def test_phase_restart_rejects_receipt_or_parent_tampering(archived, change):
    _, _, workspace = archived
    phase.handoff(workspace)
    with target.connect(workspace / "target.sqlite3") as db:
        row = db.execute(
            "SELECT * FROM conversion_runs WHERE parser_version=?",
            (phase.PROTOCOL_VERSION,),
        ).fetchone()
        if change == "manifest":
            manifest = json.loads(row["manifest"])
            manifest["activation_permitted"] = True
            db.execute(
                "UPDATE conversion_runs SET manifest=? WHERE id=?",
                (canonical(manifest), row["id"]),
            )
        elif change == "parent":
            db.execute(
                "UPDATE conversion_runs SET started_at='changed' WHERE parser_version!=?",
                (phase.PROTOCOL_VERSION,),
            )
        elif change == "state":
            db.execute(
                "UPDATE conversion_runs SET state='validated' WHERE id=?", (row["id"],)
            )
        elif change in {"timestamp", "coherent-timestamp"}:
            db.execute(
                "UPDATE conversion_runs SET started_at='changed',ended_at='changed' WHERE id=?",
                (row["id"],),
            )
            if change == "coherent-timestamp":
                manifest = json.loads(row["manifest"])
                manifest["committed_at"] = "changed"
                db.execute(
                    "UPDATE conversion_runs SET manifest=? WHERE id=?",
                    (canonical(manifest), row["id"]),
                )
        else:
            db.execute(
                "INSERT INTO conversion_runs SELECT 'duplicate',source_id,started_at,ended_at,parser_version,state,manifest FROM conversion_runs WHERE id=?",
                (row["id"],),
            )
    with pytest.raises(ConversionError):
        phase.verify(workspace)


def test_verify_phase_requires_committed_transition(archived):
    _, _, workspace = archived
    with pytest.raises(ConversionError, match="P3_PHASE_NOT_COMMITTED"):
        phase.verify(workspace)


def test_handoff_never_creates_absent_target(archived):
    _, _, workspace = archived
    (workspace / "target.sqlite3").rename(workspace / "preserved.sqlite3")
    with pytest.raises(ConversionError, match="DESTINATION_MISSING"):
        phase.handoff(workspace)
    assert not (workspace / "target.sqlite3").exists()


def test_reviewed_predecessor_requires_original_descriptor_layout(archived):
    _, _, workspace = archived
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
    with target.connect(workspace / "target.sqlite3") as db:
        manifest = json.loads(
            db.execute("SELECT manifest FROM conversion_runs").fetchone()[0]
        )
        manifest["converter_sha256"] = next(iter(target.REVIEWED_P2_CONVERTERS))
        db.execute("UPDATE conversion_runs SET manifest=?", (canonical(manifest),))
    with pytest.raises(ConversionError, match="UNSUPPORTED_P2_PREDECESSOR_LAYOUT"):
        phase.handoff(workspace)
    # A bounded legacy evidence fixture tests the descriptor/version pairing;
    # an independent guarded execution of the reviewed revision tests provenance.
    descriptor = json.loads((workspace / "sealed.json").read_bytes())
    descriptor = {key: descriptor[key] for key in legacy_fields}
    (workspace / "sealed.json").write_text(canonical(descriptor))
    with target.connect(workspace / "target.sqlite3") as db:
        manifest["seal"] = descriptor
        db.execute("UPDATE conversion_runs SET manifest=?", (canonical(manifest),))
    result = phase.handoff(workspace)
    assert phase.verify(workspace)["transition_id"] == result["transition_id"]


def test_extra_archive_rows_rejected_even_with_coherent_ledger(archived):
    _, _, workspace = archived
    with (
        target.connect(workspace / "target.sqlite3") as db,
        without_immutable_triggers(db, "conversion_batches_immutable"),
    ):
        source_id = db.execute("SELECT id FROM conversion_sources").fetchone()[0]
        record = [999999, source_id, "invented", b"unknown-key", bytes(32)]
        value = [999999, "invented", "blob", b"unknown-value"]
        db.execute("INSERT INTO legacy_records VALUES(?,?,?,?,?)", record)
        db.execute("INSERT INTO legacy_values VALUES(?,?,?,?)", value)
        committed = db.execute(
            "SELECT * FROM conversion_batches ORDER BY id LIMIT 1"
        ).fetchone()
        manifest = json.loads(committed["output_manifest"])
        manifest["proof"]["legacy_records"].append(
            batch.row_proof("legacy_records", record)
        )
        manifest["proof"]["legacy_values"].append(
            batch.row_proof("legacy_values", value)
        )
        manifest["output_sha256"] = batch.proof_digest(manifest["proof"])
        db.execute(
            "UPDATE conversion_batches SET output_manifest=? WHERE id=?",
            (canonical(manifest), committed["id"]),
        )
    with pytest.raises(ConversionError, match="ARCHIVE_SOURCE_MISMATCH"):
        phase.handoff(workspace)


def test_target_statistics_are_unapproved_schema(archived):
    _, _, workspace = archived
    with target.connect(workspace / "target.sqlite3") as db:
        db.execute("ANALYZE")
    with pytest.raises(ConversionError, match="TARGET_SCHEMA_MISMATCH"):
        phase.handoff(workspace)


@pytest.mark.parametrize("change", ["owner", "predecessor"])
def test_handoff_rejects_unsupported_owner_before_header_mutation(archived, change):
    _, _, workspace = archived
    destination = workspace / "target.sqlite3"
    with target.connect(destination) as db:
        if change == "owner":
            db.execute(
                "UPDATE conversion_runs SET parser_version='unsupported-owner/1'"
            )
        else:
            manifest = json.loads(
                db.execute("SELECT manifest FROM conversion_runs").fetchone()[0]
            )
            manifest["converter_sha256"] = "0" * 64
            db.execute("UPDATE conversion_runs SET manifest=?", (canonical(manifest),))
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    before = destination.read_bytes()
    with pytest.raises(ConversionError):
        phase.handoff(workspace)
    assert destination.read_bytes() == before


def test_foreign_key_diagnostic_enumeration_order_is_not_a_new_fact(
    archived, monkeypatch
):
    _, _, workspace = archived
    source_issues = diagnostics.source_issues
    monkeypatch.setattr(
        diagnostics, "source_issues", lambda db: list(reversed(source_issues(db)))
    )
    result = phase.handoff(workspace)
    assert phase.verify(workspace)["transition_id"] == result["transition_id"]


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm"])
@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_target_recovery_sidecar_alias_is_rejected_before_write(
    tmp_path, suffix, alias
):
    outside = tmp_path / "protected-evidence"
    outside.write_bytes(b"synthetic acquired evidence")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    destination = workspace / "target.sqlite3"
    sidecar = Path(str(destination) + suffix)
    if alias == "symlink":
        sidecar.symlink_to(outside)
    else:
        sidecar.hardlink_to(outside)
    before = source.file_fingerprint(outside)
    with pytest.raises(ConversionError, match="TARGET_SIDECAR_ALIAS_UNSUPPORTED"):
        target.connect(destination)
    assert before == source.file_fingerprint(outside)
    assert not destination.exists()
