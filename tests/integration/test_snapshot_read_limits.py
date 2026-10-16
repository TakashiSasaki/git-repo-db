"""Shared snapshot lifetime, metadata fence and finite-work regressions."""

from pathlib import Path
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import (
    PairCoordinator,
    SnapshotReadLimits,
)
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import CoreFailure


def _catalog(path: Path):
    repository, instance = str(uuid4()), str(uuid4())
    for role in ("core", "context"):
        initialize(path / f"{role}.sqlite3", role, repository, instance)


def test_supported_core_snapshot_expires_and_metadata_token_is_available(tmp_path):
    _catalog(tmp_path)
    with PairCoordinator(tmp_path, metadata_only=True).core_snapshot() as read:
        token = read.fingerprint(metadata_only=True)
        assert len(token) == 64
        with GitCore.for_snapshot(read, tmp_path) as core:
            assert core.catalog_identity() == read.identity("core")
        with pytest.raises(CoreFailure) as expired:
            core.sql("SELECT 1")
        assert expired.value.code == "CAPABILITY_EXPIRED"


@pytest.mark.parametrize(
    "limits",
    [
        SnapshotReadLimits(max_store_bytes=1),
        SnapshotReadLimits(max_total_rows=1),
        SnapshotReadLimits(max_sql_vm_steps=1),
    ],
)
def test_finite_snapshot_refusal_is_not_corruption(tmp_path, limits):
    _catalog(tmp_path)
    with pytest.raises(CoordinationError, match="QUERY_BUDGET"):
        with PairCoordinator(tmp_path, read_limits=limits).snapshots():
            pytest.fail("over-budget snapshot returned")
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    with PairCoordinator(tmp_path).snapshots():
        pass
