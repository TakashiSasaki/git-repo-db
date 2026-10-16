"""Tests for persistent corruption stop and suspect preservation under ADR 0026."""

import pytest

from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import CatalogStoppedError


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


# Note: test_stop_survives_process_restart, test_stop_survives_operational_loss,
# and test_read_only_suspect_preservation are comprehensively covered by
# test_adversarial_contract_cases.py (Cases 10, 15, 16).


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
