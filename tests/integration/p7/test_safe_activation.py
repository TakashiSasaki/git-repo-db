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
