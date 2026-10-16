"""Actual input bounds precede Python materialization and untrusted parsing."""

from __future__ import annotations

import io
import json
import sqlite3
import tracemalloc

import pytest

from repo_catalog.adapters.sqlite import recovery
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import RecoveryBudget, SalvageError


@pytest.mark.parametrize("kind", ["BLOB", "TEXT"])
@pytest.mark.parametrize("size", [8000, 4_000_000])
def test_oversized_sqlite_row_never_materializes_in_python(tmp_path, kind, size):
    catalog = tmp_path / "suspect"
    catalog.mkdir()
    conn = sqlite3.connect(catalog / "core.sqlite3")
    conn.execute(f'CREATE TABLE "large" (value {kind})')
    conn.execute(
        "INSERT INTO large VALUES (?)", (b"x" * size if kind == "BLOB" else "x" * size,)
    )
    conn.commit()
    conn.close()
    output = tmp_path / "out.jsonl"
    tracemalloc.start()
    receipt = RecoveryService().extract_salvage(
        catalog, output, budget=RecoveryBudget(max_payload_bytes=1024)
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert (
        peak < 1_000_000
    )  # excludes the pre-existing source, includes copy/JSON buffers
    assert receipt.partial
    assert receipt.corrupt_count == 0
    if size > 65536:
        assert receipt.candidate_count == 0
        assert "too big" in receipt.unreadable_scope[0]
    else:
        assert receipt.partial_count == 1
        candidate = json.loads(output.read_text())
        assert candidate["extraction_status"] == "partial"
        assert candidate["payload"] == {}
        assert "finite payload limit" in candidate["error"]


def test_sqlite_table_names_are_quoted_and_output_budget_is_honest(tmp_path):
    catalog = tmp_path / "suspect"
    catalog.mkdir()
    with sqlite3.connect(catalog / "core.sqlite3") as conn:
        conn.execute('CREATE TABLE "odd""table" ("odd""column" TEXT)')
        conn.execute('INSERT INTO "odd""table" VALUES (?)', ("hello",))
    receipt = RecoveryService().extract_salvage(catalog, tmp_path / "out")
    assert receipt.candidate_count == 1
    assert not receipt.partial
    assert not receipt.unreadable_scope


def test_missing_authority_is_not_complete_enumeration(tmp_path):
    source = tmp_path / "empty"
    source.mkdir()
    receipt = RecoveryService().extract_salvage(source, tmp_path / "out")
    assert receipt.partial
    assert receipt.candidate_count == 0
    assert "missing source database" in receipt.unreadable_scope[0]


def test_copy_accounts_db_and_sidecars_cumulatively(tmp_path):
    source, dest = tmp_path / "source", tmp_path / "dest"
    source.mkdir()
    dest.mkdir()
    (source / "core.sqlite3").write_bytes(b"a" * 100)
    (source / "core.sqlite3-wal").write_bytes(b"b" * 100)
    with pytest.raises(SalvageError, match="copy budget"):
        recovery._copy_forensic_files(source, dest, 150)
    assert sum(p.stat().st_size for p in dest.iterdir()) <= 150


def test_copy_detects_growth_after_preflight_without_copying_suffix(
    tmp_path, monkeypatch
):
    source, dest = tmp_path / "source", tmp_path / "dest"
    source.mkdir()
    dest.mkdir()
    evidence = source / "core.sqlite3"
    evidence.write_bytes(b"a" * 100)
    real_fstat = recovery.os.fstat
    grown = False

    def grow_after_stat(fd):
        nonlocal grown
        before = real_fstat(fd)
        if not grown:
            grown = True
            with evidence.open("ab") as out:
                out.write(b"b" * 1_000_000)
        return before

    monkeypatch.setattr(recovery.os, "fstat", grow_after_stat)
    with pytest.raises(SalvageError, match="grew"):
        recovery._copy_forensic_files(source, dest, 100)
    assert (dest / "core.sqlite3").stat().st_size == 100


def test_json_depth_and_elements_are_rejected_before_decoder(monkeypatch):
    def decoder_must_not_run(*args, **kwargs):
        pytest.fail("JSON decoder allocated before lexical input guard")

    monkeypatch.setattr(recovery.json, "loads", decoder_must_not_run)
    with pytest.raises(ValueError, match="depth"):
        recovery._bounded_json_loads(b"[" * 100_000, RecoveryBudget())
    with pytest.raises(ValueError, match="element"):
        recovery._bounded_json_loads(b"[" + b"0," * 30_000 + b"0]", RecoveryBudget())


def test_base64_and_proof_hex_are_bounded_before_decoding(monkeypatch):
    def decoder_must_not_run(*args, **kwargs):
        pytest.fail("base64 allocated before size guard")

    monkeypatch.setattr(recovery.base64, "b64decode", decoder_must_not_run)
    with pytest.raises(ValueError, match="finite"):
        recovery._decode_bounded_base64("A" * 10_000, 10)
    with pytest.raises(ValueError, match="finite"):
        recovery._decode_proof_bundle(
            json.dumps([["1" * 40, "tree", "aa" * 1024]]),
            RecoveryBudget(max_payload_bytes=10),
            "sha1",
        )


def test_jsonl_stops_at_huge_line_without_scanning_suffix():
    stream = io.BytesIO(b"x" * 10_000_000)
    reservations = []
    with pytest.raises(recovery._InputLimit, match="line"):
        list(
            recovery._bounded_jsonl_records(
                stream,
                max_line_bytes=4096,
                max_bytes=100_000_000,
                reserve=lambda unit, amount: reservations.append((unit, amount)),
            )
        )
    assert stream.tell() == 65536
    assert reservations == [("input_scan_bytes", 65536)]


def test_rejected_records_consume_work_and_limit_reports_unknown_suffix(
    synthetic_catalog, tmp_path
):
    salvage = tmp_path / "malformed.jsonl"
    salvage.write_bytes(b"not-json\n" * 1_000_000)
    receipt = RecoveryService().merge_salvage(
        synthetic_catalog, salvage, budget=RecoveryBudget(max_input_records=2)
    )
    assert receipt.candidates_processed == 2
    assert receipt.rejected_units == 2
    assert receipt.unprocessed_units == 1  # explicit lower bound, never a suffix scan
    assert not receipt.input_complete
    assert not receipt.unprocessed_count_exact
    state = json.loads(
        next(synthetic_catalog.glob("p1-recovery-request-*.json")).read_text()
    )
    assert state["cumulative_usage"]["input_records"] == 2
    assert state["cumulative_usage"]["input_scan_bytes"] == 65536


def test_invalid_utf8_is_rejected_without_losing_following_candidate(
    synthetic_catalog, tmp_path
):
    salvage = tmp_path / "invalid.jsonl"
    salvage.write_bytes(b"\xff\n{}\n")
    receipt = RecoveryService().merge_salvage(synthetic_catalog, salvage)
    assert receipt.candidates_processed == 2
    assert receipt.rejected_units == 2
    assert receipt.input_complete


def test_oversized_jsonl_is_incomplete_without_admission(synthetic_catalog, tmp_path):
    salvage = tmp_path / "huge.jsonl"
    salvage.write_bytes(b"x" * 1_000_000)
    receipt = RecoveryService().merge_salvage(
        synthetic_catalog, salvage, budget=RecoveryBudget(max_payload_bytes=16)
    )
    assert receipt.candidates_processed == receipt.admitted_units == 0
    assert receipt.unprocessed_units == 1
    assert not receipt.input_complete


def test_salvage_output_cannot_replace_source_evidence(synthetic_catalog):
    before = (synthetic_catalog / "core.sqlite3").read_bytes()
    with pytest.raises(SalvageError, match="outside preserved source"):
        RecoveryService().extract_salvage(
            synthetic_catalog, synthetic_catalog / "core.sqlite3"
        )
    assert (synthetic_catalog / "core.sqlite3").read_bytes() == before


@pytest.mark.parametrize("text", ["x" * 2000, "あ" * 512, 17, [], {}, "\ud800"])
def test_context_invalid_or_large_text_does_not_block_later_unit(
    synthetic_catalog, tmp_path, text
):
    salvage = tmp_path / "context-bounds.jsonl"
    rows = [
        {"candidate_type": "context_document", "payload": {"text_value": text}},
        {
            "candidate_type": "context_document",
            "payload": {"text_value": "independent accepted text"},
        },
    ]
    salvage.write_text("".join(json.dumps(row) + "\n" for row in rows))
    receipt = RecoveryService().merge_salvage(
        synthetic_catalog, salvage, budget=RecoveryBudget(max_payload_bytes=1024)
    )
    assert receipt.rejected_units == receipt.admitted_units == 1
    assert receipt.candidates_processed == 2
    assert receipt.input_complete
    with sqlite3.connect(synthetic_catalog / "context.sqlite3") as conn:
        assert conn.execute(
            "SELECT 1 FROM text_bodies WHERE text_value=?",
            ("independent accepted text",),
        ).fetchone()


@pytest.mark.parametrize(
    "bad",
    [
        {"extraction_provenance": 17},
        {"provenance": []},
        {"payload": {"full_oid": [], "native_type": "tree"}},
        {"payload": {"full_oid": "0" * 40, "object_format": {}, "native_type": "tree"}},
        {"payload": {"size": True}},
    ],
)
def test_malformed_primitive_shape_is_one_rejection_not_merge_abort(
    synthetic_catalog, tmp_path, bad
):
    row = {"candidate_type": "git_metadata", "payload": {}}
    row.update(bad)
    salvage = tmp_path / "types.jsonl"
    salvage.write_text(
        json.dumps(row)
        + "\n"
        + json.dumps(
            {
                "candidate_type": "context_document",
                "payload": {"text_value": "later accepted"},
            }
        )
        + "\n"
    )
    receipt = RecoveryService().merge_salvage(synthetic_catalog, salvage)
    assert receipt.rejected_units == receipt.admitted_units == 1
    assert receipt.input_complete


def test_none_provenance_remains_a_qualified_observation(synthetic_catalog, tmp_path):
    salvage = tmp_path / "null-provenance.jsonl"
    salvage.write_text(
        json.dumps(
            {
                "candidate_type": "git_metadata",
                "payload": {},
                "provenance": None,
                "extraction_provenance": None,
            }
        )
        + "\n"
    )
    receipt = RecoveryService().merge_salvage(synthetic_catalog, salvage)
    assert receipt.observation_units == 1
    assert receipt.input_complete


def test_hash_verification_reserves_before_expenditure(monkeypatch):
    work = recovery.RecoveryWorkBudget(work_limits={"verification_bytes": 1})

    def forbidden_hash(*args, **kwargs):
        pytest.fail("hash was computed after budget was exhausted")

    monkeypatch.setattr(recovery.hashlib, "sha256", forbidden_hash)
    with pytest.raises(recovery.CoreFailure, match="budget"):
        recovery._hash_recovery_bytes(b"too much", work)


@pytest.mark.parametrize("operation", ["merge", "copy"])
def test_fifo_input_fails_in_separate_process_without_hanging(
    synthetic_catalog, tmp_path, operation
):
    import os
    import subprocess
    import sys
    from pathlib import Path

    fifo = tmp_path / "input.fifo"
    os.mkfifo(fifo)
    destination = tmp_path / "forensic"
    destination.mkdir()
    source = tmp_path / "fifo-source"
    source.mkdir()
    os.mkfifo(source / "core.sqlite3")
    script = """
import sys
from pathlib import Path
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter, _copy_forensic_files
from repo_catalog.domain.recovery import RecoveryError
try:
    if sys.argv[1] == 'merge':
        SQLiteRecoveryAdapter().merge_salvage(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        _copy_forensic_files(Path(sys.argv[4]), Path(sys.argv[5]), 1000)
except RecoveryError as error:
    assert 'regular file' in str(error), error
    print('rejected without blocking')
else:
    raise AssertionError('FIFO accepted')
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            operation,
            str(synthetic_catalog),
            str(fifo),
            str(source),
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=3,
        env={**os.environ, "PYTHONPATH": str(Path(recovery.__file__).parents[3])},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "rejected without blocking" in result.stdout


def test_input_chunk_settles_measured_bytes_including_empty_eof():
    reservations, settlements = [], []
    records = list(
        recovery._bounded_jsonl_records(
            io.BytesIO(b"{}\n"),
            max_line_bytes=1024,
            max_bytes=1_000_000,
            reserve=lambda unit, amount: reservations.append(amount),
            settle=lambda unit, amount: settlements.append(amount),
        )
    )
    assert records == [b"{}\n"]
    assert reservations == [65536, 65536]
    assert settlements == [3, 0]


def test_native_header_limit_precedes_all_line_materialization():
    from repo_catalog.domain.git_native import headers
    from repo_catalog.domain.p1_core import account_verification

    body = b"extension value\n" * 300_000 + b"\nmessage"
    work = recovery.RecoveryWorkBudget(work_limits={"metadata_units": 1})
    tracemalloc.start()
    try:
        with pytest.raises(recovery.CoreFailure, match="budget"):
            with account_verification(work):
                headers(body, "commit")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # The byte-bounded raw header slice is allowed; a full list of 300k lines
    # would require substantially more memory before the second work check.
    assert peak < len(body) * 2
    assert work.usage["metadata_units"] == 1
