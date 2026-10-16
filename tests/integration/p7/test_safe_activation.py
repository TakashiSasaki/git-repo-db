"""Tests for safe activation and reconstructible store rebuilding under ADR 0026."""

import sqlite3
from pathlib import Path

import pytest

from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import ActivationError, BackupScope


def test_safe_activation_reconstructs_operational_and_search(
    synthetic_catalog, tmp_path, repo_uuid
):
    service = RecoveryService()

    # Create backup and restore
    backup_path = tmp_path / "backups" / "act_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    fresh_dir = tmp_path / "fresh_for_activation"
    service.restore_backup(backup_path, fresh_dir, repo_uuid)

    # In fresh_dir, operational and search do not exist yet (or are old)
    assert not (fresh_dir / "operational.sqlite3").exists()
    assert not (fresh_dir / "search.sqlite3").exists()

    # Activate
    active_locator = tmp_path / "active_catalog"
    receipt = service.activate_catalog(fresh_dir, active_locator)

    assert receipt.clean_operational
    assert "operational" in receipt.reconstructed_stores
    assert "search" in receipt.reconstructed_stores

    # Verify that operational.sqlite3 and search.sqlite3 exist and have valid schema
    activated_dir = Path(receipt.activated_catalog_path)
    op_path = activated_dir / "operational.sqlite3"
    search_path = activated_dir / "search.sqlite3"

    assert op_path.exists()
    assert search_path.exists()

    # Verify operational table count
    op_conn = sqlite3.connect(str(op_path))
    op_tables = op_conn.execute(
        "SELECT count(*) FROM sqlite_schema WHERE type='table'"
    ).fetchone()[0]
    op_conn.close()
    assert op_tables > 0

    # Verify search table count
    search_conn = sqlite3.connect(str(search_path))
    search_tables = search_conn.execute(
        "SELECT count(*) FROM sqlite_schema WHERE type='table'"
    ).fetchone()[0]
    search_conn.close()
    assert search_tables > 0


def test_activation_fails_on_missing_core(tmp_path):
    service = RecoveryService()
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    with pytest.raises(ActivationError, match="missing core.sqlite3"):
        service.activate_catalog(empty_dir, tmp_path / "active_loc")


@pytest.mark.parametrize(
    "stage,error_match",
    [
        ("before_validation", "Injected failure before validation"),
        ("between_core_and_context", "Injected failure between core and context"),
        ("after_operational_init", "Injected failure after operational initialization"),
        ("during_locator_replacement", "Injected failure during locator replacement"),
    ],
)
def test_activation_fault_stages_prevent_publication(
    synthetic_catalog, tmp_path, repo_uuid, stage, error_match
):
    service = RecoveryService()
    backup_path = tmp_path / f"backup_{stage}"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )
    fresh_dir = tmp_path / f"fresh_{stage}"
    service.restore_backup(backup_path, fresh_dir, repo_uuid)

    active_locator = tmp_path / f"active_{stage}"
    # Pre-create an existing valid locator target to verify no clobber/corruption on failure
    prev_dir = tmp_path / f"prev_target_{stage}"
    prev_dir.mkdir()
    (prev_dir / "marker.txt").write_text("old_valid_active", encoding="utf-8")
    active_locator.symlink_to(prev_dir)

    with pytest.raises(ActivationError, match=error_match):
        service.activate_catalog(fresh_dir, active_locator, fault_stage=stage)

    # Active locator must remain untouched and pointing to prev_dir
    assert active_locator.resolve() == prev_dir.resolve()
    assert (active_locator / "marker.txt").read_text(
        encoding="utf-8"
    ) == "old_valid_active"


def test_activation_replaces_existing_symlink_atomically(
    synthetic_catalog, tmp_path, repo_uuid
):
    service = RecoveryService()
    backup_path = tmp_path / "backup_symlink_replace"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )
    fresh_dir = tmp_path / "fresh_symlink_replace"
    service.restore_backup(backup_path, fresh_dir, repo_uuid)

    active_locator = tmp_path / "active_locator_symlink"
    old_target = tmp_path / "old_active_dir"
    old_target.mkdir()
    active_locator.symlink_to(old_target)

    receipt = service.activate_catalog(fresh_dir, active_locator)
    assert receipt.clean_operational
    assert active_locator.resolve() == fresh_dir.resolve()
