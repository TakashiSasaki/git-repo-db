import sqlite3
import threading

from repo_catalog.adapters.sqlite.store import OperationalStore, Store
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.domain.models import CatalogError
from tests.support.cli import pages, run


def test_generation_switch(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    before = pages(state, "search", "code", "--literal", "observed_in")
    run(state, "index", "rebuild")
    run(state, "index", "rebuild")
    assert pages(state, "search", "code", "--literal", "observed_in") == before
    with Store(state, readonly=True) as s:
        with s.open_search(readonly=True) as search:
            assert (
                search.one(
                    "SELECT count(*) FROM index_generations WHERE state='ready'"
                )[0]
                == 4
            )
            for gen in search.all(
                "SELECT * FROM index_generations WHERE state='ready'"
            ):
                assert (
                    search.one(f"SELECT count(*) FROM {gen['table_name']}")[0]
                    == search.one(
                        "SELECT count(*) FROM index_membership WHERE index_generation_id=?",
                        (gen["index_generation_id"],),
                    )[0]
                )
                assert (
                    search.one(f"SELECT body FROM {gen['table_name']} LIMIT 1")
                    in (None, (None,))
                    or search.one(f"SELECT body FROM {gen['table_name']} LIMIT 1")[0]
                    is None
                )


def test_search_truthfulness_and_freshness_fallback(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")

    # 1. Before rebuild: index is absent/not ready, must report scan with fallback
    resp_before = run(state, "search", "code", "--literal", "observed_in")
    assert resp_before["execution"]["backend"] == "scan"
    assert resp_before["execution"]["search_fallback"] is True
    assert resp_before["execution"]["search_fallback_reason"] == "index_unavailable"

    # 2. After rebuild: fresh index must report backend: fts with no fallback
    run(state, "index", "rebuild")
    resp_fts = run(state, "search", "code", "--literal", "observed_in")
    assert resp_fts["execution"]["backend"] == "fts"
    assert (
        "search_fallback" not in resp_fts["execution"]
        or not resp_fts["execution"]["search_fallback"]
    )
    assert len(resp_fts["data"]["items"]) > 0

    # 3. Short literal (< 3 chars): cannot use trigram FTS, must fall back to scan
    resp_short = run(state, "search", "code", "--literal", "ob")
    assert resp_short["execution"]["backend"] == "scan"
    assert resp_short["execution"]["search_fallback"] is True
    assert resp_short["execution"]["search_fallback_reason"] == "unsupported_query"

    # 4. Advance Core revision without rebuild: index becomes stale, must fall back to scan
    with Store(state) as s:
        s.advance_local_revision()
    resp_stale = run(state, "search", "code", "--literal", "observed_in")
    assert resp_stale["execution"]["backend"] == "scan"
    assert resp_stale["execution"]["search_fallback"] is True
    assert resp_stale["execution"]["search_fallback_reason"] == "stale_index"
    # Even with stale index, scan path must return the exact same matching items
    assert resp_stale["data"]["items"] == resp_fts["data"]["items"]


def test_rebuild_cost_estimation(catalog):
    state, fixture, repos = catalog
    with Store(state) as s:
        # Zero historical runs
        est_op_0 = s.operational.estimate_rebuild_cost()
        assert est_op_0["runs"] == 0
        assert est_op_0["estimated_duration_ms"] is None

        with s.open_search(create=True) as search:
            est_search_0 = search.estimate_rebuild_cost()
            assert est_search_0["runs"] == 0
            assert est_search_0["estimated_duration_ms"] is None

    # Run rebuild
    run(state, "sync", "git")
    run(state, "index", "rebuild")

    with Store(state) as s:
        est_op_1 = s.operational.estimate_rebuild_cost()
        assert est_op_1["runs"] >= 1
        assert isinstance(est_op_1["estimated_duration_ms"], (int, float))
        assert est_op_1["estimated_duration_ms"] > 0

        with s.open_search(readonly=True) as search:
            est_search_1 = search.estimate_rebuild_cost()
            assert est_search_1["runs"] >= 1
            assert isinstance(est_search_1["estimated_duration_ms"], (int, float))
            assert est_search_1["estimated_duration_ms"] > 0


def test_search_snapshot_barrier_and_writer_isolation(catalog):
    """R2: FTS candidates and Core results must describe one snapshot."""
    state, fixture, repos = catalog
    run(state, "sync", "git")
    run(state, "index", "rebuild")

    # Step 1: Query at initial state S
    res_s = run(state, "search", "code", "--literal", "observed_in")
    assert res_s["execution"]["backend"] == "fts"
    s_items = res_s["data"]["items"]
    assert len(s_items) > 0

    # Step 2: Concurrency test with barrier
    reader_pinned = threading.Event()
    release_reader = threading.Event()
    reader_result = {}

    def barrier_hook():
        reader_pinned.set()
        assert release_reader.wait(timeout=10.0), "Barrier timed out"

    def run_reader():
        qs = QueryService(state)
        qs._search_snapshot_barrier = barrier_hook
        try:
            res = qs.query("search code", {"literal": "observed_in"})
            reader_result["res"] = res
        except Exception as e:
            reader_result["error"] = e

    t = threading.Thread(target=run_reader)
    t.start()

    assert reader_pinned.wait(timeout=10.0), "Reader failed to reach barrier"

    # Reader is now pinned in Core read transaction at snapshot S.
    # Attempt writer action on Core. Under rollback journal ('delete'), writer attempting
    # transaction may encounter 'database is locked' or wait because reader has SHARED lock.
    with Store(state) as writer:
        writer.connection.execute("PRAGMA busy_timeout=50")
        try:
            with writer.transaction():
                writer.advance_local_revision()
        except sqlite3.OperationalError as op_err:
            if "locked" not in str(op_err).lower():
                raise

    # Release reader
    release_reader.set()
    t.join(timeout=10.0)

    assert "res" in reader_result, f"Reader error: {reader_result.get('error')}"
    res = reader_result["res"]
    # Pinned reader returned complete result for snapshot S
    assert res.execution["backend"] == "fts"
    assert res.data["items"] == s_items

    # Step 3: Now writer commits new state S+1 with genuinely matching content
    new_files = {
        **fixture.b,
        b"concurrency_match.txt": b"observed_in concurrency match\n",
    }
    fixture.alpha.commit("CONC", new_files, ("N",))
    fixture.alpha.ref("refs/heads/main", "CONC")
    run(state, "sync", "git")

    # Step 4: Search on newer state S+1 detects stale index and falls back to scan,
    # safely returning BOTH original items AND the newly committed matching item!
    res_next = run(state, "search", "code", "--literal", "observed_in")
    assert res_next["execution"]["backend"] == "scan"
    assert res_next["execution"]["search_fallback"] is True
    assert res_next["execution"]["search_fallback_reason"] == "stale_index"
    assert len(res_next["data"]["items"]) == len(s_items) + 1
    assert any(
        "concurrency_match.txt" in str(item.get("path") or item)
        for item in res_next["data"]["items"]
    )


def test_search_equivalence_and_truthful_backend_reporting(catalog):
    """R3: Truthful backend reporting and equivalence matrix."""
    state, fixture, repos = catalog
    run(state, "sync", "git")
    run(state, "index", "rebuild")

    # 1. PR and Issue searches must report backend: "scan" and avoid FTS query
    resp_pr = run(state, "search", "pr", "--literal", "test", expected=None)
    assert resp_pr["execution"]["backend"] == "scan"
    assert resp_pr["execution"].get("search_fallback") is not True

    resp_issue = run(state, "search", "issue", "--literal", "test", expected=None)
    assert resp_issue["execution"]["backend"] == "scan"
    assert resp_issue["execution"].get("search_fallback") is not True

    # 2. Code search with ready index reports backend: "fts"
    resp_code = run(state, "search", "code", "--literal", "observed_in")
    assert resp_code["execution"]["backend"] == "fts"
    assert resp_code["execution"].get("search_fallback") is not True
    assert len(resp_code["data"]["items"]) > 0

    # 3. 0 hits for code search: reports backend: "fts" with empty items
    resp_zero = run(state, "search", "code", "--literal", "nonexistent_literal_xyz")
    assert resp_zero["execution"]["backend"] == "fts"
    assert resp_zero["execution"].get("search_fallback") is not True
    assert resp_zero["data"]["items"] == []

    # 4. Explicit decoder fallback: unsupported_decoder
    resp_decoder = run(
        state,
        "search",
        "code",
        "--literal",
        "observed_in",
        "--decoder-key",
        "raw",
        expected=None,
    )
    assert resp_decoder["execution"]["backend"] == "scan"
    assert resp_decoder["execution"]["search_fallback"] is True
    assert resp_decoder["execution"]["search_fallback_reason"] == "unsupported_decoder"
    assert any(
        m.get("reason") == "decoder_unavailable"
        for m in resp_decoder["coverage"].get("missing", [])
    )

    # 5. Short literal (< 3 chars): unsupported_query
    resp_short = run(state, "search", "code", "--literal", "ob")
    assert resp_short["execution"]["backend"] == "scan"
    assert resp_short["execution"]["search_fallback"] is True
    assert resp_short["execution"]["search_fallback_reason"] == "unsupported_query"

    # 6. Equivalence matrix: FTS vs direct scan on same state
    with Store(state) as s:
        s.advance_local_revision()
    resp_scan = run(state, "search", "code", "--literal", "observed_in")
    assert resp_scan["execution"]["backend"] == "scan"
    assert resp_scan["execution"]["search_fallback"] is True
    assert resp_scan["execution"]["search_fallback_reason"] == "stale_index"
    assert resp_scan["data"]["items"] == resp_code["data"]["items"]


def test_index_rebuild_telemetry_isolation_and_status_cli(catalog, monkeypatch):
    """R4: Telemetry failure does not fail rebuild, and index status CLI works."""
    state, fixture, repos = catalog
    run(state, "sync", "git")

    # 1. repo-catalog index status before rebuild
    st_before = run(state, "index", "status")
    assert st_before["status"] == "complete"
    assert st_before["data"]["status"] in ("absent", "stale")
    assert st_before["data"]["stale"] is True

    # 2. repo-catalog index rebuild returns estimate and metrics
    reb = run(state, "index", "rebuild")
    assert reb["status"] == "complete"
    assert "generations" in reb["data"]
    assert "duration_ms" in reb["data"]
    assert "estimate" in reb["data"]

    # 3. repo-catalog index status after rebuild
    st_after = run(state, "index", "status")
    assert st_after["data"]["status"] == "ready"
    assert st_after["data"]["stale"] is False
    assert st_after["data"]["core_revision"] == st_after["data"]["core_revision_fence"]
    assert st_after["data"]["age_us"] is not None
    assert st_after["data"]["cost_estimate"]["runs"] >= 1
    assert len(st_after["data"]["generations"]) > 0

    # 4. Fault injection: telemetry failure during rebuild must NOT fail the rebuild
    def mock_fail_metric(*args, **kwargs):
        raise sqlite3.OperationalError("simulated telemetry failure")

    monkeypatch.setattr(OperationalStore, "record_rebuild_metric", mock_fail_metric)

    maint = MaintenanceService(state)
    reb_result = maint.rebuild("code")
    assert reb_result.status == "complete"
    assert "rebuild_telemetry_unavailable" in reb_result.data.get("warning", "")
    assert len(reb_result.data["generations"]) > 0

    # Verify search index is still healthy and queryable
    with Store(state, readonly=True) as s:
        with s.open_search(readonly=True) as search:
            gen = search.one(
                "SELECT * FROM index_generations WHERE kind='code' AND state='ready'"
            )
            assert gen is not None


def test_per_kind_freshness_and_aggregate_status(catalog):
    """F1: Partial rebuild must not mark the aggregate index as fresh when kinds differ."""
    state, fixture, repos = catalog
    run(state, "sync", "git")

    # 1. Rebuild all four kinds
    run(state, "index", "rebuild")
    st_all = run(state, "index", "status")
    assert st_all["data"]["status"] == "ready"
    assert st_all["data"]["stale"] is False
    assert all(k["fresh"] for k in st_all["data"]["kinds"].values())

    # 2. Advance Core revision
    with Store(state) as s:
        with s.transaction():
            s.advance_local_revision()
        new_core_rev = s.revision()["local_revision"]

    # 3. Status after core revision advance without rebuild: all stale
    st_stale = run(state, "index", "status")
    assert st_stale["data"]["status"] == "stale"
    assert st_stale["data"]["stale"] is True
    assert not any(k["fresh"] for k in st_stale["data"]["kinds"].values())

    # 4. Rebuild ONLY Code
    run(state, "index", "rebuild", "--kind", "code")

    # 5. Calls index status
    st_partial = run(state, "index", "status")
    # 6. Confirms Code is fresh and remaining kinds are stale
    kinds = st_partial["data"]["kinds"]
    assert kinds["code"]["fresh"] is True
    assert kinds["code"]["indexed_core_revision"] == new_core_rev
    assert kinds["commits"]["fresh"] is False
    assert kinds["pr"]["fresh"] is False
    assert kinds["issue"]["fresh"] is False

    # Confirms aggregate status does NOT falsely claim complete freshness
    assert st_partial["data"]["status"] == "partial"
    assert st_partial["data"]["stale"] is True

    # 7. Verify individual query paths use their own valid revision fences
    # Code search is fresh: uses FTS
    resp_code = run(state, "search", "code", "--literal", "observed_in")
    assert resp_code["execution"]["backend"] == "fts"

    # Commits search is stale: falls back to scan with stale_index
    resp_commits = run(state, "search", "commits", "--literal", "commit", expected=None)
    assert resp_commits["execution"]["backend"] == "scan"
    assert resp_commits["execution"].get("search_fallback") is True
    assert resp_commits["execution"]["search_fallback_reason"] == "stale_index"


def test_search_health_separated_from_operational_telemetry(catalog, monkeypatch):
    """F2: Operational telemetry errors must not classify Search DB as corrupt or absent."""
    state, fixture, repos = catalog
    run(state, "sync", "git")
    run(state, "index", "rebuild")

    maint = MaintenanceService(state)

    # 1. Healthy Search DB + missing Operational DB
    orig_open_op = Store.operational.fget

    def mock_missing_op(self):
        raise CatalogError("NOT_INITIALIZED", "Operational DB missing")

    monkeypatch.setattr(Store, "operational", property(mock_missing_op))
    st1 = maint.index_status()
    assert st1.status == "complete"
    assert st1.data["status"] == "ready"
    assert st1.data["stale"] is False
    assert st1.data["telemetry_status"] == "uninitialized"

    # 2. Healthy Search DB + corrupt Operational DB
    def mock_corrupt_op(self):
        raise CatalogError("DATABASE_CORRUPT", "Operational DB corrupt")

    monkeypatch.setattr(Store, "operational", property(mock_corrupt_op))
    st2 = maint.index_status()
    assert st2.status == "complete"
    assert st2.data["status"] == "ready"
    assert st2.data["stale"] is False
    assert st2.data["telemetry_status"] == "unavailable"
    assert "DATABASE_CORRUPT" in st2.data["telemetry_diagnostic"]

    # Restore operational property
    monkeypatch.setattr(Store, "operational", property(orig_open_op))

    # 3. Healthy Search DB + failing telemetry SELECT
    def mock_fail_estimate(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error on operational DB")

    monkeypatch.setattr(OperationalStore, "estimate_rebuild_cost", mock_fail_estimate)
    st3 = maint.index_status()
    assert st3.status == "complete"
    assert st3.data["status"] == "ready"
    assert st3.data["telemetry_status"] == "unavailable"

    monkeypatch.undo()

    # 4. Corrupt Search DB + healthy Operational DB
    def mock_corrupt_search(self, *args, **kwargs):
        raise CatalogError("INDEX_CORRUPT", "Simulated search corruption")

    monkeypatch.setattr(Store, "open_search", mock_corrupt_search)
    st4 = maint.index_status()
    assert st4.status == "complete"
    assert st4.data["status"] == "corrupt"
    assert st4.data["error"] == "INDEX_CORRUPT"
    assert st4.data["telemetry_status"] == "available"

    monkeypatch.undo()

    # 5. Missing Search DB without automatic file creation
    state_fresh = state.parent / "fresh_no_search"
    run(
        state_fresh,
        "init",
        "--profile",
        "catalog-text-v1",
        "--cache-max-bytes",
        67108864,
        "--min-free-bytes",
        0,
    )
    maint_fresh = MaintenanceService(state_fresh)
    st5 = maint_fresh.index_status()
    assert st5.data["status"] == "absent"
    assert not (state_fresh / "search.sqlite3").exists()


def test_rebuild_tolerates_job_bookkeeping_failures(catalog, monkeypatch):
    """F3: Primary index rebuild success must be preserved when Job bookkeeping fails."""
    state, fixture, repos = catalog
    run(state, "sync", "git")

    from repo_catalog.application.job_service import JobService

    maint = MaintenanceService(state)

    # 1. Successful rebuild, successful Job completion update
    res1 = maint.rebuild("code")
    assert res1.status == "complete"
    assert "warnings" not in res1.data or not res1.data["warnings"]

    # 2. Successful rebuild, failed timing-metric recording
    def mock_fail_metric(*args, **kwargs):
        raise sqlite3.OperationalError("operational telemetry metric error")

    monkeypatch.setattr(OperationalStore, "record_rebuild_metric", mock_fail_metric)
    res2 = maint.rebuild("code")
    assert res2.status == "complete"
    assert "rebuild_telemetry_unavailable" in res2.data["warning"]
    monkeypatch.undo()

    # 3. Successful rebuild, failed final Job-state update
    def mock_fail_job_update(self, job_id, state, *args, **kwargs):
        if state == "complete":
            raise CatalogError("OPERATIONAL_ERROR", "Simulated job update failure")

    monkeypatch.setattr(JobService, "update", mock_fail_job_update)
    res3 = maint.rebuild("code")
    assert res3.status == "complete"
    assert "job_bookkeeping_unavailable" in res3.data["warning"]

    # Verify Search DB contains the successfully built generation
    with Store(state, readonly=True) as s:
        with s.open_search(readonly=True) as search:
            gen = search.one(
                "SELECT * FROM index_generations WHERE kind='code' AND state='ready'"
            )
            assert gen is not None
    monkeypatch.undo()

    # 4. Actual index-generation build or promotion failure
    from repo_catalog.adapters.sqlite import index as index_module

    def mock_fail_refresh(*args, **kwargs):
        raise CatalogError("INDEX_INTEGRITY", "Failed to project documents")

    monkeypatch.setattr(index_module, "refresh_documents", mock_fail_refresh)
    try:
        maint.rebuild("code")
        assert False, "Expected INDEX_INTEGRITY error"
    except CatalogError as e:
        assert e.code == "INDEX_INTEGRITY"

    # 5. Failure while recording failure does not mask primary error
    def mock_fail_all_updates(self, *args, **kwargs):
        raise RuntimeError("secondary error in job updater")

    monkeypatch.setattr(JobService, "update", mock_fail_all_updates)
    try:
        maint.rebuild("code")
        assert False, "Expected INDEX_INTEGRITY error without masking"
    except CatalogError as e:
        assert e.code == "INDEX_INTEGRITY"
    monkeypatch.undo()


def test_rebuild_estimate_truthful_and_distinguished(catalog):
    """F4: Rebuild estimate clearly distinguishes measurements from historical average."""
    state, fixture, repos = catalog
    with Store(state) as s:
        # Zero runs gives None for durations
        est0 = s.operational.estimate_rebuild_cost()
        assert est0["runs"] == 0
        assert est0["historical_average_duration_ms"] is None
        assert est0["previous_measured_duration_ms"] is None
        assert est0["estimated_duration_ms"] is None

    run(state, "sync", "git")
    run(state, "index", "rebuild")

    with Store(state) as s:
        est1 = s.operational.estimate_rebuild_cost()
        assert est1["runs"] >= 1
        assert est1["historical_average_duration_ms"] is not None
        assert est1["previous_measured_duration_ms"] is not None
        assert est1["previous_measured_duration_ms"] == est1["previous_duration_ms"]
        assert est1["estimate_basis"] == "historical_average"
        assert "across_all_recorded_rebuilds" in est1["scope_note"]
