"""Tests for consistent backup creation and validation under ADR 0026."""

from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import BackupScope


def test_core_only_backup_and_restore(synthetic_catalog, tmp_path, repo_uuid):
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "core_backup"

    receipt = service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.GIT_ONLY
    )

    assert receipt.verified_clean
    assert receipt.scope == BackupScope.GIT_ONLY
    assert (backup_path / "manifest.json").exists()
    assert (backup_path / "manifest.json.sha256").exists()
    assert (backup_path / "stores" / "core.sqlite3").exists()
    assert not (backup_path / "stores" / "context.sqlite3").exists()

    # Restore into fresh destination
    restore_dest = tmp_path / "restored_core"
    restore_receipt = service.restore_backup(backup_path, restore_dest, repo_uuid)

    assert restore_receipt.revalidated_clean
    assert "core" in restore_receipt.revalidated_stores
    assert "context" not in restore_receipt.revalidated_stores
    assert (restore_dest / "core.sqlite3").exists()


# Note: test_paired_consistent_backup, test_backup_refuses_stopped_catalog,
# test_backup_refuses_existing_destination, test_restore_rejects_manifest_tampering,
# and test_restore_rejects_wrong_repository_uuid are comprehensively covered by
# test_adversarial_contract_cases.py (Cases 01, 02, 03, 12, 15, 16, 19).


def test_missing_ordinary_file_bodies_is_not_corruption(
    synthetic_catalog, tmp_path, repo_uuid
):
    # ADR 0014: non-acquisition of file blob bodies is expected product scope, not corruption
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "no_blob_backup"
    receipt = service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.GIT_ONLY
    )
    assert receipt.manifest.retained_byte_summary.commit_count == 1
    assert receipt.manifest.retained_byte_summary.tree_count == 1
    assert receipt.manifest.retained_byte_summary.tag_count == 1
    assert receipt.manifest.retained_byte_summary.notes_body_count == 1
    assert receipt.manifest.retained_byte_summary.total_retained_bytes > 0
