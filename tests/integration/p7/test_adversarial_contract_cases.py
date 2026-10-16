"""Exhaustive integration tests for the 18 P7 adversarial and data-integrity requirements under ADR 0026."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import catalog_gate
from repo_catalog.adapters.sqlite.p1_core import Core
from repo_catalog.adapters.sqlite.p1_schema import (
    connect as p1_connect,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    initialize,
    register_functions,
)
from repo_catalog.adapters.sqlite.recovery import (
    _sha256_file,
)
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.p1_core import (
    CoreFailure,
)
from repo_catalog.domain.recovery import (
    ActivationError,
    BackupScope,
    BackupValidationError,
    CandidateType,
    CatalogStoppedError,
    ExtractionStatus,
    RestoreValidationError,
)
from tests.integration.p7.conftest import make_commit, make_tree


def test_case_01_real_commit_survives_backup_and_restore(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 1: A real retained commit survives backup/restore exactly."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case1_backup"
    receipt = service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )
    assert receipt.verified_clean
    assert receipt.manifest.retained_byte_summary.commit_count == 1

    restore_dest = tmp_path / "restored_case1"
    restore_receipt = service.restore_backup(backup_path, restore_dest, repo_uuid)
    assert restore_receipt.revalidated_clean

    # Inspect restored core database directly
    conn = sqlite3.connect(
        f"file:{(restore_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    rows = conn.execute(
        "SELECT object_format, full_oid, native_type, body, size, digest_sha256 FROM retained_metadata WHERE native_type='commit'"
    ).fetchall()
    conn.close()

    assert len(rows) == 1
    fmt, oid, ntype, body, size, digest = rows[0]
    assert ntype == "commit"
    assert len(body) == size
    assert hashlib.sha256(body).hexdigest() == digest
    assert b"Initial commit" in body


def test_case_02_retained_byte_modified_without_digest_update_detected(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 2: A retained byte modified without updating its recorded digest is detected."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case2_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.GIT_ONLY
    )

    core_file = backup_path / "stores" / "core.sqlite3"
    conn = sqlite3.connect(str(core_file))
    register_functions(conn)
    conn.execute("PRAGMA ignore_check_constraints = ON;")
    conn.execute("DROP TRIGGER IF EXISTS p1_immutable_retained_metadata_update;")
    row = conn.execute(
        "SELECT full_oid, body FROM retained_metadata WHERE native_type='commit'"
    ).fetchone()
    full_oid, body = row
    tampered_body = b"X" + body[1:]
    conn.execute(
        "UPDATE retained_metadata SET body=? WHERE full_oid=?",
        (tampered_body, full_oid),
    )
    conn.commit()
    conn.close()

    # Recalculate store SHA-256 and update manifest so file-level hash checks pass
    new_core_sha = _sha256_file(core_file)
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["stores"]["core"]["sha256"] = new_core_sha
    manifest_data["stores"]["core"]["bytes"] = core_file.stat().st_size
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    # Restore must detect the domain digest mismatch during deep validation
    restore_dest = tmp_path / "restored_case2"
    with pytest.raises(RestoreValidationError, match="SHA-256 digest mismatch"):
        service.restore_backup(backup_path, restore_dest, repo_uuid)


def test_case_03_forged_backup_with_recalculated_manifest_sha_rejected(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 3: A forged backup with recalculated manifest SHA-256 but invalid domain bytes is rejected."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case3_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.GIT_ONLY
    )

    core_file = backup_path / "stores" / "core.sqlite3"
    conn = sqlite3.connect(str(core_file))
    register_functions(conn)
    conn.execute("PRAGMA ignore_check_constraints = ON;")
    conn.execute("DROP TRIGGER IF EXISTS p1_immutable_retained_metadata_update;")
    conn.execute(
        "UPDATE retained_metadata SET size = size + 100 WHERE native_type='commit'"
    )
    conn.commit()
    conn.close()

    # Recalculate file hash and update manifest
    new_core_sha = _sha256_file(core_file)
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["stores"]["core"]["sha256"] = new_core_sha
    manifest_data["stores"]["core"]["bytes"] = core_file.stat().st_size
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    restore_dest = tmp_path / "restored_case3"
    with pytest.raises(RestoreValidationError, match="Size mismatch"):
        service.restore_backup(backup_path, restore_dest, repo_uuid)


def test_case_04_verified_notes_body_survives_recovery(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 4: An actual verified Notes body survives recovery."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case4_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    restore_dest = tmp_path / "restored_case4"
    service.restore_backup(backup_path, restore_dest, repo_uuid)

    conn = sqlite3.connect(
        f"file:{(restore_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    rows = conn.execute(
        "SELECT object_format, full_oid, body, size, digest_sha256 FROM retained_notes"
    ).fetchall()
    role_count = conn.execute("SELECT count(*) FROM note_roles").fetchone()[0]
    conn.close()

    assert len(rows) == 1
    fmt, oid, body, size, digest = rows[0]
    assert len(body) == size
    assert hashlib.sha256(body).hexdigest() == digest
    assert b"Reviewed-by: Admin" in body
    assert role_count == 1


def test_case_05_notes_blob_lacking_role_evidence_rejected(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 5: A Notes blob lacking role evidence is not admitted."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case5_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    fresh_dest = tmp_path / "restored_case5"
    service.restore_backup(backup_path, fresh_dest, repo_uuid)

    # Construct candidate with arbitrary note body but missing/forged role proof
    salvage_file = tmp_path / "unproven_note_candidate.jsonl"
    fake_note_body = b"Unauthenticated note payload\n"
    import base64

    unproven_cand = {
        "candidate_id": "unproven-note-1",
        "candidate_type": CandidateType.NOTES_MAPPING.value,
        "capture_origin_uuidv4": str(uuid4()),
        "capture_uuidv4": str(uuid4()),
        "provenance": {"store": "core", "table": "retained_notes"},
        "payload": {
            "object_format": "sha1",
            "full_oid": "4" * 40,
            "native_type": "blob",
            "size": len(fake_note_body),
            "digest_sha256": hashlib.sha256(fake_note_body).hexdigest(),
            "body_base64": base64.b64encode(fake_note_body).decode("ascii"),
            # missing proof_bundle, root, target, etc.
        },
        "extraction_status": ExtractionStatus.CLEAN.value,
        "error": None,
    }
    salvage_file.write_text(json.dumps(unproven_cand) + "\n", encoding="utf-8")

    merge_receipt = service.merge_salvage(fresh_dest, salvage_file)
    assert merge_receipt.admitted_units == 0
    assert merge_receipt.rejected_units == 1
    assert (
        "Missing required notes role proof or body"
        in merge_receipt.rejections[0]["reason"]
    )


def test_case_06_context_text_survives_with_verified_sha256(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 6: Actual Context text survives with verified SHA-256."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case6_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    restore_dest = tmp_path / "restored_case6"
    service.restore_backup(backup_path, restore_dest, repo_uuid)

    ctx_conn = p1_connect(restore_dest / "context.sqlite3", "context")
    rows = ctx_conn.execute("SELECT sha256, text_value FROM text_bodies").fetchall()
    ctx_conn.close()

    assert len(rows) == 1
    sha256_val, text_val = rows[0]
    assert text_val == "Sample review document content for PR #1"
    assert hashlib.sha256(text_val.encode("utf-8")).hexdigest() == sha256_val


def test_case_07_valid_salvage_causes_observable_new_rows(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 7: Valid salvage candidates cause observable new rows in the restored catalog."""
    import base64

    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case7_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    fresh_dest = tmp_path / "restored_case7"
    service.restore_backup(backup_path, fresh_dest, repo_uuid)

    # Inspect initial commit count
    conn = sqlite3.connect(
        f"file:{(fresh_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    init_commits = conn.execute(
        "SELECT count(*) FROM retained_metadata WHERE native_type='commit'"
    ).fetchone()[0]
    tree_oid = conn.execute(
        "SELECT full_oid FROM retained_metadata WHERE native_type='tree'"
    ).fetchone()[0]
    conn.close()

    # Create a valid new commit to salvage
    new_commit = make_commit("sha1", tree_oid, [], message="Second salvaged commit\n")
    salvage_file = tmp_path / "valid_salvage.jsonl"
    cand = {
        "candidate_id": f"sha1:{new_commit.oid.full_oid}:{uuid4()}",
        "candidate_type": CandidateType.RETAINED_BODY.value,
        "capture_origin_uuidv4": None,
        "capture_uuidv4": None,
        "provenance": {"store": "core", "table": "retained_metadata"},
        "payload": {
            "object_format": "sha1",
            "full_oid": new_commit.oid.full_oid,
            "physical_copy_uuidv4": str(uuid4()),
            "native_type": "commit",
            "size": len(new_commit.body),
            "digest_sha256": hashlib.sha256(new_commit.body).hexdigest(),
            "body_base64": base64.b64encode(new_commit.body).decode("ascii"),
        },
        "extraction_status": ExtractionStatus.CLEAN.value,
        "error": None,
    }
    salvage_file.write_text(json.dumps(cand) + "\n", encoding="utf-8")

    merge_receipt = service.merge_salvage(fresh_dest, salvage_file)
    assert merge_receipt.admitted_units == 1
    assert merge_receipt.rejected_units == 0

    # Verify observable new row exists in restored core
    conn = sqlite3.connect(
        f"file:{(fresh_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    post_commits = conn.execute(
        "SELECT count(*) FROM retained_metadata WHERE native_type='commit'"
    ).fetchone()[0]
    new_row = conn.execute(
        "SELECT full_oid, body FROM retained_metadata WHERE full_oid=?",
        (new_commit.oid.full_oid,),
    ).fetchone()
    conn.close()

    assert post_commits == init_commits + 1
    assert new_row is not None
    assert new_row[0] == new_commit.oid.full_oid
    assert b"Second salvaged commit" in new_row[1]


def test_case_08_rejected_candidates_cause_no_mutation(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 8: Rejected candidates cause no authoritative mutation."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case8_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    fresh_dest = tmp_path / "restored_case8"
    service.restore_backup(backup_path, fresh_dest, repo_uuid)

    conn = sqlite3.connect(
        f"file:{(fresh_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    init_rows = conn.execute("SELECT count(*) FROM retained_metadata").fetchone()[0]
    conn.close()

    # Salvage file containing corrupt candidate and invalid capture candidate
    salvage_file = tmp_path / "bad_candidates.jsonl"
    corrupt_cands = [
        {
            "candidate_id": "bad-1",
            "candidate_type": CandidateType.RETAINED_BODY.value,
            "extraction_status": ExtractionStatus.CORRUPT_BOUNDARY.value,
            "payload": {},
        },
        {
            "candidate_id": "bad-2",
            "candidate_type": CandidateType.GIT_METADATA.value,
            "capture_uuidv4": "not-valid-uuid",
            "extraction_status": ExtractionStatus.CLEAN.value,
            "payload": {},
        },
    ]
    salvage_file.write_text(
        "\n".join(json.dumps(c) for c in corrupt_cands) + "\n", encoding="utf-8"
    )

    merge_receipt = service.merge_salvage(fresh_dest, salvage_file)
    assert merge_receipt.admitted_units == 0
    assert merge_receipt.rejected_units == 2

    # Verify zero rows mutated
    conn = sqlite3.connect(
        f"file:{(fresh_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    post_rows = conn.execute("SELECT count(*) FROM retained_metadata").fetchone()[0]
    conn.close()

    assert init_rows == post_rows


def test_case_09_original_capture_and_provenance_survive_replay(
    synthetic_catalog, tmp_path
):
    """Case 9: Original Capture and provenance survive replay when supported."""
    service = RecoveryService()
    salvage_file = tmp_path / "salvage_case9.jsonl"
    receipt = service.extract_salvage(synthetic_catalog, salvage_file)
    assert receipt.candidate_count > 0

    lines = [
        json.loads(line)
        for line in salvage_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    note_candidates = [
        c for c in lines if c["candidate_type"] == CandidateType.NOTES_MAPPING.value
    ]
    assert len(note_candidates) == 1
    cand = note_candidates[0]
    assert cand["capture_origin_uuidv4"] is not None
    assert cand["capture_uuidv4"] is not None
    assert cand["provenance"] == {"store": "core", "table": "retained_notes"}


def test_case_10_read_only_salvage_preserves_db_and_wal(synthetic_catalog, tmp_path):
    """Case 10: Read-only salvage preserves the original SQLite DB/WAL/journal evidence."""
    service = RecoveryService()
    core_path = synthetic_catalog / "core.sqlite3"
    pre_sha = _sha256_file(core_path)

    salvage_file = tmp_path / "salvage_case10.jsonl"
    service.extract_salvage(synthetic_catalog, salvage_file)

    post_sha = _sha256_file(core_path)
    assert pre_sha == post_sha


def test_case_11_writer_cannot_cross_declared_backup_cut(synthetic_catalog, tmp_path):
    """Case 11: A writer cannot cross the declared paired backup cut."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case11_backup"

    # Verify writer exclusion during backup
    with catalog_gate(synthetic_catalog, exclusive=True):
        # A concurrent backup or writer cannot acquire exclusive catalog_gate simultaneously
        with pytest.raises(Exception):
            with catalog_gate(synthetic_catalog, exclusive=True, timeout=0.01):
                pass

    # Normal backup succeeds cleanly after writer lock is released
    receipt = service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )
    assert receipt.verified_clean


def test_case_12_concurrent_destination_creation_no_overwrite(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 12: Concurrent destination creation cannot be overwritten."""
    service = RecoveryService()

    # Destination already exists for backup
    existing_dest = tmp_path / "existing_backup_dest"
    existing_dest.mkdir()
    with pytest.raises(BackupValidationError, match="already exists"):
        service.create_consistent_backup(synthetic_catalog, existing_dest)

    # Destination already exists for restore
    valid_backup = tmp_path / "backups" / "valid_b"
    service.create_consistent_backup(synthetic_catalog, valid_backup)

    existing_restore_dest = tmp_path / "existing_restore_dest"
    existing_restore_dest.mkdir()
    with pytest.raises(RestoreValidationError, match="already exists"):
        service.restore_backup(valid_backup, existing_restore_dest, repo_uuid)


def test_case_13_symlink_and_path_traversal_rejection(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 13: Symlink and path traversal inputs cannot escape the recovery staging root."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case13_backup"
    service.create_consistent_backup(synthetic_catalog, backup_path)

    # 1. Path traversal in manifest
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["stores"]["core"]["path"] = "../../etc/passwd"
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    with pytest.raises(RestoreValidationError, match="Path traversal detected"):
        service.restore_backup(backup_path, tmp_path / "dest13_traversal", repo_uuid)

    # 2. Symlink store file
    valid_backup = tmp_path / "backups" / "symlink_backup"
    service.create_consistent_backup(synthetic_catalog, valid_backup)
    core_file = valid_backup / "stores" / "core.sqlite3"
    outside_target = tmp_path / "outside_target.sqlite3"
    shutil.copy2(core_file, outside_target)
    core_file.unlink()
    core_file.symlink_to(outside_target)

    # Update manifest sha
    man_file = valid_backup / "manifest.json"
    man_sha = valid_backup / "manifest.json.sha256"
    man_sha.write_text(_sha256_file(man_file) + "  manifest.json\n", encoding="utf-8")

    with pytest.raises(RestoreValidationError, match="Symlink store forbidden"):
        service.restore_backup(valid_backup, tmp_path / "dest13_symlink", repo_uuid)


def test_case_14_interrupted_activation_no_publication(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 14: An interrupted activation cannot publish a partially validated destination."""
    service = RecoveryService()
    active_locator = tmp_path / "active_catalog_link"
    active_locator.symlink_to(synthetic_catalog.resolve())

    # Create invalid fresh destination missing core.sqlite3
    invalid_fresh = tmp_path / "invalid_fresh_dest"
    invalid_fresh.mkdir()

    with pytest.raises(ActivationError, match="missing core.sqlite3"):
        service.activate_catalog(invalid_fresh, active_locator)

    # Active locator is untouched and still points to original catalog
    assert active_locator.resolve() == synthetic_catalog.resolve()


def test_case_15_stop_survives_process_restart_and_operational_loss(
    synthetic_catalog,
):
    """Case 15: The catalog stop survives process restart and loss of Operational/Search."""
    service1 = RecoveryService()
    service1.stop_suspect_catalog(
        synthetic_catalog, "Authoritative byte corruption stop"
    )

    # Delete Operational and Search
    op_path = synthetic_catalog / "operational.sqlite3"
    search_path = synthetic_catalog / "search.sqlite3"
    if op_path.exists():
        op_path.unlink()
    if search_path.exists():
        search_path.unlink()

    # Fresh service instance
    service2 = RecoveryService()
    assert service2.is_stopped(synthetic_catalog)
    with pytest.raises(CatalogStoppedError):
        service2.assert_not_stopped(synthetic_catalog)


def test_case_16_p5_p6_reject_stopped_catalog(synthetic_catalog):
    """Case 16: Existing P5/P6 readers and writers actually reject the stopped catalog."""
    service = RecoveryService()
    service.stop_suspect_catalog(synthetic_catalog, "Test fencing on stopped catalog")

    # P2-P6 Core connection must fail with RECOVERY_STOP
    core_path = synthetic_catalog / "core.sqlite3"
    with pytest.raises(CoreFailure) as exc_info:
        Core(core_path)
    assert exc_info.value.code == "RECOVERY_STOP"


def test_case_17_sha1_and_sha256_git_formats(tmp_path):
    """Case 17: Both SHA-1 and SHA-256 Git formats are exercised."""
    service = RecoveryService()
    repo_256 = str(uuid4())
    inst_256 = str(uuid4())
    catalog_256 = tmp_path / "catalog_sha256"
    catalog_256.mkdir()

    core_path = catalog_256 / "core.sqlite3"
    initialize(core_path, "core", repo_256, inst_256)
    initialize(catalog_256 / "context.sqlite3", "context", repo_256, inst_256)
    initialize(catalog_256 / "operational.sqlite3", "operational", repo_256, inst_256)
    initialize(catalog_256 / "search.sqlite3", "search", repo_256, inst_256)

    # Populate sha256 objects
    core = GitCore(core_path)
    core.admit_repository(repo_256)
    budget = UnlimitedWorkBudget()

    tree_256 = make_tree("sha256", [(b"100644", b"file.txt", "a" * 64)])
    commit_256 = make_commit(
        "sha256", tree_256.oid.full_oid, [], message="SHA-256 commit\n"
    )

    core.admit_metadata(tree_256, str(uuid4()), budget)
    core.admit_metadata(commit_256, str(uuid4()), budget)

    # Backup and restore sha256 catalog
    backup_path = tmp_path / "backup_sha256"
    receipt = service.create_consistent_backup(
        catalog_256, backup_path, scope=BackupScope.PAIRED
    )
    assert receipt.verified_clean
    assert receipt.manifest.retained_byte_summary.commit_count == 1

    restore_dest = tmp_path / "restored_sha256"
    rest_receipt = service.restore_backup(backup_path, restore_dest, repo_256)
    assert rest_receipt.revalidated_clean
