import sqlite3
import threading

from repo_catalog.adapters.sqlite.store import OperationalStore, Store
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
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

    # Step 3: Now writer commits new state S+1
    with Store(state) as writer:
        with writer.transaction():
            writer.advance_local_revision()

    # Step 4: Search on newer state S+1 detects stale index and falls back to scan
    res_next = run(state, "search", "code", "--literal", "observed_in")
    assert res_next["execution"]["backend"] == "scan"
    assert res_next["execution"]["search_fallback"] is True
    assert res_next["execution"]["search_fallback_reason"] == "stale_index"
    assert res_next["data"]["items"] == s_items


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
