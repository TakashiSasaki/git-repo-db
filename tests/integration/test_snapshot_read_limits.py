"""Shared snapshot lifetime, metadata fence and finite-work regressions."""

from pathlib import Path
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.adapters.sqlite.p1_coordination import (
    PairCoordinator,
    SnapshotReadLimits,
)
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_repository import RepositoryFailure


def _catalog(path: Path):
    repository, instance = str(uuid4()), str(uuid4())
    for role in ("repository", "context"):
        initialize(path / f"{role}.sqlite3", role, repository, instance)


def test_supported_repository_snapshot_expires_and_metadata_token_is_available(
    tmp_path,
):
    _catalog(tmp_path)
    with PairCoordinator(tmp_path, metadata_only=True).repository_snapshot() as read:
        token = read.fingerprint(metadata_only=True)
        assert len(token) == 64
        with GitRepositoryStore.for_snapshot(read, tmp_path) as repository_store:
            assert repository_store.catalog_identity() == read.identity("repository")
        with pytest.raises(RepositoryFailure) as expired:
            repository_store.sql("SELECT 1")
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
    with pytest.raises((CoordinationError, RepositoryFailure)):
        with PairCoordinator(source, metadata_only=True).snapshots() as pair:
            for factory, read, failure in (
                (
                    GitRepositoryStore.for_snapshot,
                    pair.repository_store,
                    RepositoryFailure,
                ),
                (Context.for_snapshot, pair.context, ContextError),
            ):
                with pytest.raises(failure) as rejected:
                    with factory(read, other):
                        pytest.fail("foreign catalog capability returned")
                assert rejected.value.code == "SNAPSHOT_OWNER"
            with GitRepositoryStore.for_snapshot(
                pair.repository_store, source
            ) as repository_store:
                # Exercise the same persistent typed-corruption publication boundary
                # before deliberately swallowing its error inside the live snapshot.
                with pytest.raises(RepositoryFailure):
                    repository_store._integrity_stop("injected typed failure")
            pytest.fail("ordinary completion must be fenced after caught corruption")
    assert (source / "p1-recovery-stop.json").exists()
    assert not (other / "p1-recovery-stop.json").exists()


def test_paired_snapshot_reports_validation_and_token_generation_separately(tmp_path):
    _catalog(tmp_path)
    coordinator = PairCoordinator(tmp_path, metadata_only=True)
    assert coordinator.last_read_costs_ns == {}
    with coordinator.snapshots() as pair:
        assert pair.repository_store.identity("repository") == pair.context.identity(
            "context"
        )
        assert set(coordinator.last_read_costs_ns) == {
            "authority_validation",
            "snapshot_token_generation",
        }
        assert all(
            type(value) is int and value >= 0
            for value in coordinator.last_read_costs_ns.values()
        )
