import sqlite3

from tests.support.cli import pages, run


def test_fts_fallback(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    queries = ["認証", "配分", "X", "observed_in", "linkWithPopup", "AND", '"quote"']
    expected = {q: pages(state, "search", "code", "--literal", q) for q in queries}
    run(state, "index", "rebuild")
    assert {
        q: pages(state, "search", "code", "--literal", q) for q in queries
    } == expected
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        name = db.execute(
            "SELECT table_name FROM index_generations WHERE kind='code' AND state='ready'"
        ).fetchone()[0]
        db.execute(f"DROP TABLE {name}")
    assert {
        q: pages(state, "search", "code", "--literal", q) for q in queries
    } == expected


def test_pages_cursor(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    first = run(state, "search", "path", "--path", "shared/a.txt", "--limit", 1)
    assert first["data"]["page"]["has_more"]
    cursor = first["data"]["page"]["next_cursor"]
    run(state, "index", "rebuild")
    run(state, "search", "path", "--path", "shared/a.txt", "--cursor", cursor)
    fixture.advance()
    run(state, "sync", "git")
    assert (
        run(
            state,
            "search",
            "path",
            "--path",
            "shared/a.txt",
            "--cursor",
            cursor,
            expected=4,
        )["error"]["code"]
        == "STALE_CURSOR"
    )
