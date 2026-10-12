from repo_catalog.adapters.sqlite.store import Store
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
