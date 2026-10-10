"""Exercise corrected current clocks through the integrated Exchange receiver.

Uses only generated repositories, a local fixture server and MockTransport. The
state directory must be new and explicit; no authenticated provider is contacted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import guard_sql
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, SCHEMA_VERSION, schema_sql
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_exchange import catalog, receive
from tests.integration.test_current_collection_rejection_clocks import (
    assert_no_original,
    mock_collector,
    new_job,
    resume_job,
    seed_pr,
)
from tests.support.github_runtime import github_runtime


def state(db):
    return tuple(
        db.execute(
            "SELECT observed_at_us,coverage_state FROM current_coverage WHERE kind='review'"
        ).fetchone()
    )


def fresh_schema(source_root):
    db = catalog()
    try:
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        objects = {
            kind: db.execute(
                "SELECT count(*) FROM sqlite_schema WHERE type=? AND sql IS NOT NULL",
                (kind,),
            ).fetchone()[0]
            for kind in ("view", "trigger", "index")
        }
        # Names come exclusively from sqlite_schema, never caller input.
        columns = sum(
            len(db.execute(f'PRAGMA table_xinfo("{t}")').fetchall()) for t in tables
        )
        foreign_keys = sum(
            len({row[0] for row in db.execute(f'PRAGMA foreign_key_list("{t}")')})
            for t in tables
        )
        report = {
            "schema_version": SCHEMA_VERSION,
            "ddl_sha256": DDL_SHA256.hex(),
            "schema_sql_hash_consistent": hashlib.sha256(schema_sql().encode()).digest()
            == DDL_SHA256,
            "tables": len(tables),
            "columns": columns,
            "foreign_key_constraints": foreign_keys,
            "views": objects["view"],
            "triggers": objects["trigger"],
            "explicit_indexes": objects["index"],
            "generated_json_exact": guard_sql()
            == (
                source_root / "src/repo_catalog/resources/json_contracts.sql"
            ).read_text(),
            "foreign_keys": db.execute("PRAGMA foreign_key_check").fetchall(),
            "integrity": db.execute("PRAGMA integrity_check").fetchone()[0],
        }
        assert report["generated_json_exact"] and report["schema_sql_hash_consistent"]
        assert report["foreign_keys"] == [] and report["integrity"] == "ok"
        assert (len(tables), columns, foreign_keys, objects) == (
            103,
            665,
            226,
            {"view": 48, "trigger": 498, "index": 113},
        )
        return report
    finally:
        db.close()


def run(directory):
    directory.mkdir(parents=True, exist_ok=False)
    monkeypatch = pytest.MonkeyPatch()
    fixture = github_runtime.__wrapped__(directory, monkeypatch)
    store, repo, _, api = next(fixture)
    target = catalog()
    states = []
    try:
        pr = seed_pr(store, repo)
        endpoint = api.url + "/repos/fixture/alpha/pulls/41/reviews"
        clock, mode = [100], ["empty"]

        def response(request):
            if mode[0] == "empty":
                return httpx.Response(200, json=[])
            if request.url.params.get("page", "1") == "1":
                clock[0] = 150
                return httpx.Response(
                    200,
                    json=[],
                    headers={"Link": f'<{endpoint}?page=2>; rel="next"'},
                )
            clock[0] = 200 if mode[0] == "rejected" else 175
            return httpx.Response(
                200,
                json=[{"id": 2, "body": []}] if mode[0] == "rejected" else [],
            )

        with mock_collector(store, response, clock) as collector:

            def collect(job):
                collector.current_collection(
                    repo, pr, "review", job, endpoint, current_parser.review
                )

            def exchange(expected, reverse=False):
                unit = Graph(store.connection).export(repo["repository_uuidv4"])
                if reverse:
                    unit["records"].reverse()
                receive(target, unit)
                receive(target, unit)
                assert state(store.connection) == expected
                assert state(target) == expected
                assert_no_original(store)
                assert target.execute(
                    "SELECT count(*) FROM fetch_occurrences"
                ).fetchone() == (0,)
                states.append({"expected": expected, "actual_receiver": state(target)})
                return unit

            first = new_job(store)
            collect(first)
            JobService(store).update(first, "complete")
            old = exchange((100, "complete"))
            mode[0] = "rejected"
            interrupted = new_job(store)
            try:
                collect(interrupted)
            except CatalogError as error:
                assert error.code == "API_SCHEMA"
            else:
                raise AssertionError("identified invalid body was admitted")
            exchange((200, "partial"), reverse=True)
            # Clearing an empty immutable-conflict closure must not erase domain
            # partialness or let old complete replay become current.
            Graph(target).refresh_resolution_blocks()
            receive(target, old)
            assert state(target) == (200, "partial")
            resume_job(store, interrupted)
            mode[0] = "retry"
            collect(interrupted)
            exchange((200, "partial"))
            mode[0], clock[0] = "empty", 300
            latest = new_job(store)
            collect(latest)
            exchange((300, "complete"), reverse=True)
            assert target.execute("PRAGMA foreign_key_check").fetchall() == []
            assert target.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        target.close()
        try:
            next(fixture)
        except StopIteration:
            pass
        monkeypatch.undo()
    return states


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    assert Path(current_parser.__file__).resolve() == (
        source_root / "src/repo_catalog/adapters/github/current_parser.py"
    ), "PYTHONPATH does not select the declared source checkout"

    def revision():
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD", "HEAD^{tree}"], cwd=source_root, text=True
        ).splitlines()

    head, tree = revision()
    paths = (
        "src/repo_catalog/adapters/github/current_parser.py",
        "src/repo_catalog/adapters/github/collector.py",
        "src/repo_catalog/adapters/github/persistence.py",
        "src/repo_catalog/adapters/sqlite/exchange.py",
        "src/repo_catalog/adapters/sqlite/schema.py",
        "src/repo_catalog/resources/catalog3.sql",
        "src/repo_catalog/resources/identity_relations.sql",
    )
    hashes = {
        path: hashlib.sha256((source_root / path).read_bytes()).hexdigest()
        for path in paths
    }
    schema = fresh_schema(source_root)
    states = run(args.state_dir)
    assert hashes == {
        path: hashlib.sha256((source_root / path).read_bytes()).hexdigest()
        for path in paths
    }, "source changed during independent probe"
    assert [head, tree] == revision(), "revision changed during independent probe"
    report = {
        "kind": "independent-integrated-current-clock-exchange-v1",
        "source_head": head,
        "source_tree": tree,
        "source_sha256": hashes,
        "current_parser_version": current_parser.PARSER_VERSION,
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "bootstrap_override": False,
        "fresh_schema": schema,
        "states": states,
        "limits": [
            "Focused interaction probe; not full acceptance or a timing benchmark."
        ],
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
