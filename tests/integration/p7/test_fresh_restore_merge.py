"""Tests for fresh restore and receiver-checked salvage merge under ADR 0026."""

import json
from uuid import uuid4

from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import BackupScope, CandidateType, ExtractionStatus


def test_fresh_restore_and_merge(synthetic_catalog, tmp_path, repo_uuid):
    service = RecoveryService()

    # 1. Create a healthy baseline backup
    backup_path = tmp_path / "backups" / "baseline"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    # 2. Restore into fresh destination
    fresh_dir = tmp_path / "fresh_dest"
    restore_receipt = service.restore_backup(backup_path, fresh_dir, repo_uuid)
    assert restore_receipt.revalidated_clean

    # 3. Create a synthetic salvage file with 1 admitted candidate, 1 observation candidate, and 2 corrupt candidates
    salvage_file = tmp_path / "salvage.jsonl"
    new_repo_id = str(uuid4())
    admitted_cand = {
        "candidate_id": str(uuid4()),
        "candidate_type": CandidateType.GIT_METADATA.value,
        "capture_origin_uuidv4": str(uuid4()),
        "capture_uuidv4": str(uuid4()),
        "extraction_provenance": {"store": "core", "table": "repositories"},
        "payload": {"repository_uuidv4": new_repo_id},
        "extraction_status": ExtractionStatus.CLEAN.value,
        "error": None,
    }
    observation_cand = {
        "candidate_id": str(uuid4()),
        "candidate_type": CandidateType.GIT_METADATA.value,
        "capture_origin_uuidv4": str(uuid4()),
        "capture_uuidv4": str(uuid4()),
        "provenance": {"source": "test"},
        "payload": {"ref_name": "refs/heads/main"},
        "extraction_status": ExtractionStatus.CLEAN.value,
        "error": None,
    }
    corrupt_cand = {
        "candidate_id": str(uuid4()),
        "candidate_type": CandidateType.GIT_METADATA.value,
        "capture_origin_uuidv4": str(uuid4()),
        "capture_uuidv4": str(uuid4()),
        "provenance": {"source": "corrupt_source"},
        "payload": {},
        "extraction_status": ExtractionStatus.CORRUPT_BOUNDARY.value,
        "error": "Corrupted row segment",
    }
    invalid_uuid_cand = {
        "candidate_id": str(uuid4()),
        "candidate_type": CandidateType.GIT_METADATA.value,
        "capture_origin_uuidv4": str(uuid4()),
        "capture_uuidv4": "not-a-uuid4",
        "provenance": {"source": "bad_uuid"},
        "payload": {},
        "extraction_status": ExtractionStatus.CLEAN.value,
        "error": None,
    }

    with salvage_file.open("w", encoding="utf-8") as f:
        for c in (admitted_cand, observation_cand, corrupt_cand, invalid_uuid_cand):
            f.write(json.dumps(c) + "\n")

    # 4. Merge salvage into fresh destination
    merge_receipt = service.merge_salvage(fresh_dir, salvage_file)
    assert merge_receipt.candidates_processed == 4
    assert merge_receipt.admitted_units == 1
    assert merge_receipt.observation_units == 1
    assert merge_receipt.rejected_units == 2
    assert len(merge_receipt.rejections) == 2

    # 5. Verify actual authoritative row exists in reopened database
    import sqlite3

    conn = sqlite3.connect(fresh_dir / "core.sqlite3")
    assert (
        conn.execute(
            "SELECT 1 FROM repositories WHERE repository_uuidv4=?", (new_repo_id,)
        ).fetchone()
        is not None
    )
    conn.close()


def test_merge_rejects_unproven_note_body(synthetic_catalog, tmp_path, repo_uuid):
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "baseline_notes"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    fresh_dir = tmp_path / "fresh_dest_notes"
    service.restore_backup(backup_path, fresh_dir, repo_uuid)

    salvage_file = tmp_path / "unproven_note.jsonl"
    # Unproven note body missing object_oid or object_type must be refused under ADR 0022
    unproven_cand = {
        "candidate_id": str(uuid4()),
        "candidate_type": CandidateType.RETAINED_BODY.value,
        "capture_origin_uuidv4": str(uuid4()),
        "capture_uuidv4": str(uuid4()),
        "provenance": {"source": "unproven_notes"},
        "payload": {
            "body": "some arbitrary note text"
        },  # missing object_oid and object_type
        "extraction_status": ExtractionStatus.CLEAN.value,
        "error": None,
    }
    salvage_file.write_text(json.dumps(unproven_cand) + "\n", encoding="utf-8")

    merge_receipt = service.merge_salvage(fresh_dir, salvage_file)
    assert merge_receipt.candidates_processed == 1
    assert merge_receipt.admitted_units == 0
    assert merge_receipt.rejected_units == 1
    assert (
        "Missing required object_oid or object_type"
        in merge_receipt.rejections[0]["reason"]
    )
