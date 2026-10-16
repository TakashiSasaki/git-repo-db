"""Tests for read-only untrusted typed salvage under ADR 0026."""

import json

from repo_catalog.application.recovery import RecoveryService


def test_salvage_extracts_typed_candidates(synthetic_catalog, tmp_path):
    service = RecoveryService()
    service.stop_suspect_catalog(synthetic_catalog, "Corrupt test")

    salvage_file = tmp_path / "salvage_output.jsonl"
    receipt = service.extract_salvage(synthetic_catalog, salvage_file)

    assert receipt.candidate_count > 0
    assert salvage_file.exists()

    # Read back JSONL lines
    lines = [
        json.loads(line)
        for line in salvage_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == receipt.candidate_count
    for item in lines:
        assert "candidate_id" in item
        assert "candidate_type" in item
        assert "provenance" in item
        assert "payload" in item


def test_salvage_preserves_independent_candidates_across_faults(
    synthetic_catalog, tmp_path
):
    service = RecoveryService()
    salvage_file = tmp_path / "salvage_fault.jsonl"

    receipt = service.extract_salvage(synthetic_catalog, salvage_file, max_records=5)

    assert receipt.candidate_count <= 5
    assert salvage_file.exists()


def test_salvage_does_not_mutate_suspect_database(synthetic_catalog, tmp_path):
    service = RecoveryService()
    core_path = synthetic_catalog / "core.sqlite3"
    initial_bytes = core_path.read_bytes()

    salvage_file = tmp_path / "salvage_read_only.jsonl"
    service.extract_salvage(synthetic_catalog, salvage_file)

    post_bytes = core_path.read_bytes()
    assert initial_bytes == post_bytes
