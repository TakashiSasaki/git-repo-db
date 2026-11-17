"""A real SIGINT inside an authoritative read releases the snapshot before exit."""

import json
import signal
import sqlite3

import pytest

from repo_catalog.cli.main import main
from tests.e2e.test_separated_cli import run, seed_metadata


def test_normal_cli_sigint_after_sql_read_returns_no_page_and_closes_snapshot(
    tmp_path, capsys, monkeypatch
):
    from repo_catalog.application.git_history_query import GitHistoryQuery

    catalog, _, _, commit, _ = seed_metadata(tmp_path, capsys)
    before = run(capsys, "query", "repository", "--catalog", catalog)
    original, connections = GitHistoryQuery._history, []

    def interrupt(self, core, token, *args, **kwargs):
        result = original(self, core, token, *args, **kwargs)
        assert result["items"]
        connections.append(core._db)
        assert core._db.in_transaction
        signal.raise_signal(signal.SIGINT)
        pytest.fail("SIGINT did not interrupt the active SQL snapshot")

    monkeypatch.setattr(GitHistoryQuery, "_history", interrupt)
    result = main(
        [
            "query",
            "log",
            "--catalog",
            str(catalog),
            "--object-oid",
            commit.object_oid,
        ]
    )
    captured = capsys.readouterr()
    assert result == 130 and captured.out == ""
    error = json.loads(captured.err)
    assert error["status"] == "error" and error["code"] == "CANCELLED"
    assert "items" not in error and "next_cursor" not in error
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("SELECT 1")
    monkeypatch.setattr(GitHistoryQuery, "_history", original)
    assert run(capsys, "query", "repository", "--catalog", catalog) == before
    assert run(
        capsys, "query", "log", "--catalog", catalog, "--object-oid", commit.object_oid
    )["items"]
    assert not (catalog / "p1-recovery-stop.json").exists()
    assert not (catalog / "context.sqlite3").exists()
