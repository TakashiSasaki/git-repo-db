"""Tests for persistent corruption stop and suspect preservation under ADR 0026."""

import hashlib
from pathlib import Path

import pytest

from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import CatalogStoppedError


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def test_persistent_stop_on_corruption(synthetic_catalog):
    service = RecoveryService()
    assert not service.is_stopped(synthetic_catalog)

    # Incur stop
    service.stop_suspect_catalog(
        synthetic_catalog,
        reason="Retained commit byte SHA-256 mismatch detected",
        details={"object_oid": "abc12345", "kind": "commit"},
    )

    assert service.is_stopped(synthetic_catalog)
    with pytest.raises(CatalogStoppedError, match="recovery stop mode"):
        service.assert_not_stopped(synthetic_catalog)

    assert (synthetic_catalog / "recovery.stop").exists()
    assert (synthetic_catalog / "p1-recovery-stop.json").exists()


def test_stop_survives_process_restart(synthetic_catalog):
    service1 = RecoveryService()
    service1.stop_suspect_catalog(synthetic_catalog, "Simulated fatal error")

    # Simulate fresh process restart with new service instance
    service2 = RecoveryService()
    assert service2.is_stopped(synthetic_catalog)
    with pytest.raises(CatalogStoppedError):
        service2.assert_not_stopped(synthetic_catalog)


def test_stop_survives_operational_loss(synthetic_catalog):
    service = RecoveryService()
    service.stop_suspect_catalog(synthetic_catalog, "Authoritative corruption")

    # Simulate deletion of reconstructible Operational store
    op_path = synthetic_catalog / "operational.sqlite3"
    if op_path.exists():
        op_path.unlink()

    assert service.is_stopped(synthetic_catalog)
    with pytest.raises(CatalogStoppedError):
        service.assert_not_stopped(synthetic_catalog)


def test_operational_loss_does_not_falsely_stop_catalog(synthetic_catalog):
    service = RecoveryService()
    # Loss or corruption of reconstructible operational store alone must NOT stop authoritative catalog
    op_path = synthetic_catalog / "operational.sqlite3"
    if op_path.exists():
        # Corrupt operational store by writing garbage
        op_path.write_bytes(b"CORRUPTED_OPERATIONAL_DATA")

    # Authoritative catalog is NOT stopped
    assert not service.is_stopped(synthetic_catalog)
    # Should not raise CatalogStoppedError
    service.assert_not_stopped(synthetic_catalog)


def test_read_only_suspect_preservation(synthetic_catalog):
    service = RecoveryService()
    core_path = synthetic_catalog / "core.sqlite3"
    initial_sha = _sha256_file(core_path)

    # Trigger stop
    service.stop_suspect_catalog(synthetic_catalog, "Preservation test stop")

    # Verify original core database file bytes remain exactly untouched
    post_stop_sha = _sha256_file(core_path)
    assert initial_sha == post_stop_sha
