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
        assert (
            s.one("SELECT count(*) FROM index_generations WHERE state='ready'")[0] == 3
        )
        for gen in s.all("SELECT * FROM index_generations WHERE state='ready'"):
            assert (
                s.one(f"SELECT count(*) FROM {gen['table_name']}")[0]
                == s.one(
                    "SELECT count(*) FROM index_membership WHERE generation_id=?",
                    (gen["id"],),
                )[0]
            )
            assert (
                s.one(f"SELECT body FROM {gen['table_name']} LIMIT 1")
                in (None, (None,))
                or s.one(f"SELECT body FROM {gen['table_name']} LIMIT 1")[0] is None
            )
