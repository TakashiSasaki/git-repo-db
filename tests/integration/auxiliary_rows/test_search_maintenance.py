"""Actual rebuild telemetry never becomes Search generation authority."""

from contextlib import closing

import pytest

from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.application.search_maintenance import SearchMaintenance
from repo_catalog.domain.p1_repository import OID, RepositoryFailure
from repo_catalog.domain.query_work import UnlimitedWorkBudget
from repo_catalog.domain.search_query import SearchQuery
from tests.integration.p6.conftest import populate_rich_catalog


def service(tmp_path, *, clock_ns=None, max_runs=1000):
    populate_rich_catalog(tmp_path)
    reader = ProductionQueryService(tmp_path)
    options = {"max_runs": max_runs}
    if clock_ns is not None:
        options["clock_ns"] = clock_ns
    return reader, SearchMaintenance(reader, **options)


def test_actual_rebuild_history_estimates_and_per_kind_freshness(tmp_path):
    values = iter((10, 110, 500, 800))
    reader, maintenance = service(tmp_path, clock_ns=lambda: next(values))
    before = maintenance.status()
    assert before["status"] == "unavailable_or_stale"
    assert before["estimate"] == {
        "runs": 0,
        "average_duration_ns": None,
        "estimated_duration_ns": None,
    }
    first = maintenance.rebuild()
    assert all(count > 0 for count in first["counts"].values())
    assert first["duration_ns"] == 100
    assert first["telemetry_status"] == "available"
    assert first["estimate"] == {
        "runs": 1,
        "average_duration_ns": 100,
        "estimated_duration_ns": 100,
    }
    fresh = maintenance.status()
    assert fresh["status"] == "ready"
    assert all(item["fresh"] for item in fresh["kinds"].values())
    assert {
        kind: item["document_count"] for kind, item in fresh["kinds"].items()
    } == first["counts"]
    with closing(
        GitRepositoryStore(tmp_path / "repository.sqlite3")
    ) as repository_store:
        repository_store.admit_object(OID("sha1", "7" * 40))
    assert not any(item["fresh"] for item in maintenance.status()["kinds"].values())
    notes = maintenance.rebuild(("notes",))
    assert notes["duration_ns"] == 300 and notes["estimate"]["runs"] == 1
    partial = maintenance.status()
    assert partial["status"] == "partial"
    assert partial["kinds"]["notes"]["fresh"]
    assert not partial["kinds"]["git_metadata"]["fresh"]
    assert partial["estimate"]["average_duration_ns"] == 100
    assert reader.search(SearchQuery("p6")).total_count > 0


@pytest.mark.parametrize("loss", ["absent", "corrupt"])
def test_operational_loss_never_creates_telemetry_or_invalidates_search(tmp_path, loss):
    reader, maintenance = service(tmp_path)
    for suffix in ("", "-wal", "-shm"):
        path = tmp_path / ("operational.sqlite3" + suffix)
        if path.exists():
            path.unlink()
    if loss == "corrupt":
        (tmp_path / "operational.sqlite3").write_bytes(
            b"corrupt optional Operational header"
        )
    preserved = (
        (tmp_path / "operational.sqlite3").read_bytes() if loss == "corrupt" else None
    )
    result = maintenance.rebuild()
    assert result["counts"] and result["duration_ns"] >= 0
    assert result["telemetry_status"] == (
        "uninitialized" if loss == "absent" else "unavailable"
    )
    assert result["estimate"]["estimated_duration_ns"] is None
    status = maintenance.status()
    assert status["status"] == "ready"
    assert status["telemetry_status"] == result["telemetry_status"]
    assert reader.search(SearchQuery("p6")).backend == "verified_projection_scan"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    if loss == "absent":
        assert not (tmp_path / "operational.sqlite3").exists()
    else:
        assert (tmp_path / "operational.sqlite3").read_bytes() == preserved


def test_telemetry_write_failure_and_history_bound_do_not_block_real_rebuild(
    tmp_path, monkeypatch
):
    from repo_catalog.adapters.sqlite.search_maintenance import SearchTelemetry

    reader, maintenance = service(tmp_path, max_runs=1)
    first = maintenance.rebuild()
    assert first["estimate"]["runs"] == 1
    second = maintenance.rebuild()
    assert second["counts"] == first["counts"]
    assert second["telemetry_status"] == "unavailable"
    assert reader.search(SearchQuery("p6")).backend == "verified_projection_scan"
    with closing(connect(tmp_path / "operational.sqlite3", "operational")) as db:
        assert (
            db.execute("SELECT count(*) FROM acquisition_requests").fetchone()[0] == 1
        )
    with monkeypatch.context() as fault:

        def fail(*_args):
            raise OSError("optional timing progress unavailable")

        fault.setattr(SearchTelemetry, "record", fail)
        third = maintenance.rebuild()
    assert third["counts"] == first["counts"]
    assert third["telemetry_status"] == "unavailable"
    assert maintenance.status()["status"] == "ready"


def test_status_and_rebuild_keep_caller_finite_budget_refusal(tmp_path):
    _, maintenance = service(tmp_path)

    def limited():
        return UnlimitedWorkBudget(work_limits={"metadata_units": 0})

    with pytest.raises(RepositoryFailure) as error:
        maintenance.status(work=limited())
    assert error.value.code == "BUDGET"
    with pytest.raises(RepositoryFailure) as error:
        maintenance.rebuild(work=limited())
    assert error.value.code == "BUDGET"
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_search_keeps_pinned_generation_during_authority_write_and_then_falls_back(
    tmp_path, monkeypatch
):
    reader, maintenance = service(tmp_path)
    maintenance.rebuild()
    baseline = reader.search(SearchQuery("p6"))
    assert baseline.backend == "verified_projection_scan"
    original = reader.search_adapter.query_candidates
    changed = False

    def writer_after_authority_snapshot(*args, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            with closing(
                GitRepositoryStore(tmp_path / "repository.sqlite3")
            ) as repository_store:
                repository_store.admit_object(OID("sha1", "6" * 40))
        return original(*args, **kwargs)

    with monkeypatch.context() as concurrent:
        concurrent.setattr(
            reader.search_adapter, "query_candidates", writer_after_authority_snapshot
        )
        pinned = reader.search(SearchQuery("p6"))
    assert changed and pinned.backend == "verified_projection_scan"
    assert pinned.hits == baseline.hits
    current = reader.search(SearchQuery("p6"))
    assert current.backend == "authority_scan"
    assert [hit.matched_text for hit in current.hits] == [
        hit.matched_text for hit in baseline.hits
    ]
    assert maintenance.status()["status"] == "unavailable_or_stale"
