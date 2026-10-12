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
