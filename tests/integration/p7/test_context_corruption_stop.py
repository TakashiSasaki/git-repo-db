"""Bounded existing Context replay checks diagnose actual retained corruption."""

import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.core_recovery import RecoveryWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import (
    expected_schema,
    register_functions,
    schema_rows,
)
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.adapters.sqlite.recovery_validation import (
    verify_existing_context_text,
)
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.recovery import CorruptionDetectedError, RecoveryBudget


def _text(restored_catalog):
    with sqlite3.connect(restored_catalog / "context.sqlite3") as db:
        return db.execute(
            "SELECT sha256,text_value FROM text_bodies LIMIT 1"
        ).fetchone()


def _corrupt(restored_catalog, raw):
    path = restored_catalog / "context.sqlite3"
    with sqlite3.connect(path) as db:
        register_functions(db)
        sql = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='text_bodies_no_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER text_bodies_no_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE text_bodies SET text_value=CAST(? AS TEXT)", (raw,))
        db.execute(sql)
        db.commit()
        assert schema_rows(db) == expected_schema("context")


def _candidate(tmp_path, digest, text):
    source = tmp_path / "context.jsonl"
    source.write_text(
        json.dumps(
            {
                "candidate_type": "context_document",
                "extraction_status": "clean",
                "payload": {"text_value": text, "sha256": digest},
            }
        )
        + "\n"
    )
    return source


@pytest.mark.parametrize(
    "corrupt_bytes", [b"damaged retained text", b"\x80invalid UTF-8"]
)
def test_existing_retained_text_damage_stops_destination_without_mutation(
    restored_catalog, tmp_path, corrupt_bytes
):
    digest, original = _text(restored_catalog)
    _corrupt(restored_catalog, corrupt_bytes)
    source = _candidate(tmp_path, digest, original)
    with sqlite3.connect(restored_catalog / "context.sqlite3") as db:
        before = db.execute(
            "SELECT sha256, CAST(text_value AS BLOB) FROM text_bodies"
        ).fetchall()
    with pytest.raises(CorruptionDetectedError, match="destination Context corruption"):
        SQLiteRecoveryAdapter().merge_salvage(restored_catalog, source)
    assert (restored_catalog / "p1-recovery-stop.json").exists()
    with sqlite3.connect(restored_catalog / "context.sqlite3") as db:
        assert (
            db.execute(
                "SELECT sha256, CAST(text_value AS BLOB) FROM text_bodies"
            ).fetchall()
            == before
        )
    with pytest.raises(CoreFailure) as stopped:
        GitCore(restored_catalog / "core.sqlite3")
    assert stopped.value.code == "RECOVERY_STOP"


def test_invalid_incoming_digest_does_not_stop_healthy_destination(
    restored_catalog, tmp_path
):
    _, original = _text(restored_catalog)
    source = _candidate(tmp_path, "0" * 64, original)
    receipt = SQLiteRecoveryAdapter().merge_salvage(restored_catalog, source)
    assert receipt.rejected_units == 1
    assert not (restored_catalog / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("refusal", ["individual_size", "verification_budget"])
def test_existing_text_refusal_precedes_byte_materialization(restored_catalog, refusal):
    digest, original = _text(restored_catalog)
    with sqlite3.connect(restored_catalog / "context.sqlite3") as db:
        statements = []
        db.set_trace_callback(statements.append)
        budget = (
            RecoveryWorkBudget(work_limits={"verification_bytes": 1})
            if refusal == "verification_budget"
            else RecoveryWorkBudget()
        )
        with pytest.raises(CoreFailure) as failure:
            verify_existing_context_text(
                db,
                digest,
                original.encode(),
                1 if refusal == "individual_size" else 1024,
                budget,
            )
        assert failure.value.code == "BUDGET"
        assert not any(
            sql.startswith("SELECT CAST(text_value AS BLOB)") for sql in statements
        )
    assert not (restored_catalog / "p1-recovery-stop.json").exists()


def test_existing_replay_verification_cost_is_durably_accounted(
    restored_catalog, tmp_path
):
    digest, original = _text(restored_catalog)
    source = _candidate(tmp_path, digest, original)
    receipt = SQLiteRecoveryAdapter().merge_salvage(
        restored_catalog,
        source,
        budget=RecoveryBudget(),
        request_id="context-verified-replay",
    )
    assert receipt.replayed_units == 1
    state = json.loads(
        (
            restored_catalog / "p1-recovery-request-context-verified-replay.json"
        ).read_text()
    )
    # Incoming SHA, stored SHA and exact stored-byte comparison all cost work.
    assert state["cumulative_usage"]["verification_bytes"] >= len(original.encode()) * 3
    assert state["cumulative_usage"]["input_bytes"] >= len(original.encode())
