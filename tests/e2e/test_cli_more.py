import json
import sqlite3

from repo_catalog.application.contracts import PageRequest, QueryRequest
from repo_catalog.application.query_service import QueryService
from tests.support.cli import run
from tests.support.process import start_hooked


def test_exit_codes(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    assert (
        run(state, "search", "code", "--literal", "definitely-no-match")["data"][
            "items"
        ]
        == []
    )
    assert (
        run(
            state,
            "search",
            "hash",
            "--algorithm",
            "raw-md5",
            "--digest",
            "abc",
            expected=2,
        )["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert (
        run(state, "repos", "show", "--repo", "absent", expected=4)["error"]["code"]
        == "NOT_FOUND"
    )
    assert (
        run(state, "search", "code", "--literal", "", expected=2)["error"]["code"]
        == "INVALID_ARGUMENT"
    )
    assert (
        run(state, "search", "path", "--path", "x", "--all", expected=2)["error"][
            "code"
        ]
        == "INVALID_ARGUMENT"
    )
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        db.execute("UPDATE schema_migrations SET checksum='wrong'")
    assert run(state, "repos", "list", expected=5)["error"]["code"] == "SCHEMA_ERROR"


def test_query_timeout_and_invalid_cursor(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    result = QueryService(state).execute(
        QueryRequest("search code", {"literal": "認証"}, PageRequest(), 1e-12)
    )
    assert result.status == "partial" and result.execution["timed_out"]
    assert (
        result.data["page"]["has_more"] is None
        and result.data["page"]["next_cursor"] is None
    )
    run(
        state,
        "search",
        "code",
        "--literal",
        "認証",
        "--cursor",
        "not-a-cursor",
        expected=2,
    )


def test_publication_fencing(catalog, tmp_path):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    before = run(state, "repos", "show", "--repo", repos["alpha"])["data"]["items"][0][
        "current_snapshot"
    ]
    fixture.advance()
    process, hooks = start_hooked(
        state, "before_publish", tmp_path, "sync", "git", "--repo", repos["alpha"]
    )
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        db.execute("UPDATE collection_runs SET attempt=99 WHERE state!='published'")
    (hooks / "before_publish.release").touch()
    out, err = process.communicate(timeout=10)
    assert (
        process.returncode == 3
        and json.loads(out)["data"]["results"][0]["error"] == "STALE_ATTEMPT"
    )
    assert (
        run(state, "repos", "show", "--repo", repos["alpha"])["data"]["items"][0][
            "current_snapshot"
        ]
        == before
    )


def test_read_transaction_released_before_output(catalog):
    from repo_catalog.adapters.sqlite.store import Store

    state, fixture, repos = catalog
    run(state, "sync", "git")
    result = QueryService(state).execute(QueryRequest("repos list"))
    with Store(state) as s:
        s.execute("PRAGMA busy_timeout=0")
        with s.transaction():
            s.execute("UPDATE catalog_meta SET publication_seq=publication_seq")
    assert result.data["items"]
