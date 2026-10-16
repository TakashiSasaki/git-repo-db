"""Tests for consistent backup creation and validation under ADR 0026."""

import json
from uuid import uuid4

import pytest

from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import (
    BackupScope,
    BackupValidationError,
    CatalogStoppedError,
    RestoreValidationError,
)


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


def test_paired_consistent_backup(synthetic_catalog, tmp_path, repo_uuid):
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "paired_backup"

    receipt = service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    assert receipt.verified_clean
    assert receipt.scope == BackupScope.PAIRED
    assert (backup_path / "stores" / "core.sqlite3").exists()
    assert (backup_path / "stores" / "context.sqlite3").exists()

    # Restore into fresh destination
    restore_dest = tmp_path / "restored_paired"
    restore_receipt = service.restore_backup(backup_path, restore_dest, repo_uuid)

    assert restore_receipt.revalidated_clean
    assert "core" in restore_receipt.revalidated_stores
    assert "context" in restore_receipt.revalidated_stores
    assert (restore_dest / "core.sqlite3").exists()
    assert (restore_dest / "context.sqlite3").exists()


def test_backup_refuses_stopped_catalog(synthetic_catalog, tmp_path):
    service = RecoveryService()
    service.stop_suspect_catalog(synthetic_catalog, "Injected corruption stop test")

    backup_path = tmp_path / "backups" / "stopped_backup"
    with pytest.raises(CatalogStoppedError, match="recovery stop mode"):
        service.create_consistent_backup(synthetic_catalog, backup_path)


def test_backup_refuses_existing_destination(synthetic_catalog, tmp_path):
    service = RecoveryService()
    existing_dest = tmp_path / "existing_dir"
    existing_dest.mkdir()

    with pytest.raises(BackupValidationError, match="already exists"):
        service.create_consistent_backup(synthetic_catalog, existing_dest)


def test_restore_rejects_manifest_tampering(synthetic_catalog, tmp_path, repo_uuid):
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "tampered_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.GIT_ONLY
    )

    # Tamper with manifest.json
    manifest_file = backup_path / "manifest.json"
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    data["created_at_us"] += 1000
    manifest_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    fresh_dest = tmp_path / "fresh_restore_attempt"
    with pytest.raises(RestoreValidationError, match="tampering detected"):
        service.restore_backup(backup_path, fresh_dest, repo_uuid)


def test_restore_rejects_wrong_repository_uuid(synthetic_catalog, tmp_path):
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "wrong_repo_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.GIT_ONLY
    )

    fresh_dest = tmp_path / "fresh_restore_wrong_repo"
    wrong_repo = str(uuid4())
    with pytest.raises(RestoreValidationError, match="Repository UUID mismatch"):
        service.restore_backup(backup_path, fresh_dest, wrong_repo)


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
