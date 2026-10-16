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


def test_snapshot_cannot_redirect_catalog_corruption_stop(tmp_path):
    from repo_catalog.adapters.sqlite.production_context import Context
    from repo_catalog.domain.production_context import ContextError

    source, other = tmp_path / "source", tmp_path / "other"
    source.mkdir()
    other.mkdir()
    _catalog(source)
    _catalog(other)
    with pytest.raises((CoordinationError, CoreFailure)):
        with PairCoordinator(source, metadata_only=True).snapshots() as pair:
            for factory, read, failure in (
                (GitCore.for_snapshot, pair.core, CoreFailure),
                (Context.for_snapshot, pair.context, ContextError),
            ):
                with pytest.raises(failure) as rejected:
                    with factory(read, other):
                        pytest.fail("foreign catalog capability returned")
                assert rejected.value.code == "SNAPSHOT_OWNER"
            with GitCore.for_snapshot(pair.core, source) as core:
                # Exercise the same persistent typed-corruption publication boundary
                # before deliberately swallowing its error inside the live snapshot.
                with pytest.raises(CoreFailure):
                    core._integrity_stop("injected typed failure")
            pytest.fail("ordinary completion must be fenced after caught corruption")
    assert (source / "p1-recovery-stop.json").exists()
    assert not (other / "p1-recovery-stop.json").exists()
