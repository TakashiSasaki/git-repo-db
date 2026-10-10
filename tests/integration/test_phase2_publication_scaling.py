"""Publication work follows the selected result, rather than unrelated history.

The fixtures contain valid empty Git acquisitions, immutable interpretations and
independent local naming evidence. VM instruction counts exercise the actual
publisher without relying on wall-clock performance under concurrent test runs.
"""

import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.schema import schema_sql
from tests.support.parser_facts import register_test_profile

RESULT_INDEXES = (
    "code_observations_parsed_result_idx",
    "change_request_events_parsed_result_idx",
    "snapshots_parsed_result_idx",
    "ref_observations_parsed_result_idx",
    "code_commits_parsed_result_idx",
    "code_file_changes_parsed_result_idx",
    "repository_names_parsed_result_idx",
)


def uid():
    return str(uuid.uuid4())


@pytest.fixture
def publication_catalog():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(schema_sql())
    model = ParserModel(db)
    profile = register_test_profile(db)
    owner, unrelated_owner = uid(), uid()
    acquisitions = {}
    for repo in (owner, unrelated_owner):
        db.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'synthetic','{}')",
            (repo,),
        )
        acquisition = acquisitions[repo] = uid()
        db.execute(
            "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,kind,request) VALUES(?,?,'git','{}')",
            (acquisition, repo),
        )
        db.execute(
            "INSERT INTO git_acquisition_publications VALUES(?,?,'[]','[]')",
            (acquisition, repo),
        )

    def snapshot(repo):
        result = model.create_result(
            profile,
            repository_uuidv4=repo,
            inputs=[{"git_acquisition_id": acquisitions[repo]}],
        )
        identity = uid()
        db.execute(
            "INSERT INTO snapshots(parsed_result_uuidv4,snapshot_id,git_acquisition_id,repository_uuidv4,published,generation,created_at_us) VALUES(?,?,?,?,1,0,0)",
            (result, identity, acquisitions[repo], repo),
        )
        return result, identity

    yield db, model, owner, unrelated_owner, snapshot
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    db.close()


def seal_and_count(db, model, result):
    steps = 0

    def progress():
        nonlocal steps
        steps += 1
        return 0

    db.set_progress_handler(progress, 1)
    try:
        model.publish_result(result)
    finally:
        db.set_progress_handler(None, 0)
    return steps


def assert_snapshot_seal(db, result, snapshot_id):
    manifest = db.execute(
        "SELECT declared_input_count,fact_manifest_json FROM parsed_result_publications WHERE parsed_result_uuidv4=?",
        (result,),
    ).fetchone()
    assert manifest[0] == 1
    assert json.loads(manifest[1]) == [{"table": "snapshots", "key": [snapshot_id]}]


def test_actual_publication_lookup_uses_all_seven_result_led_indexes(
    publication_catalog,
):
    db, model, owner, _, snapshot = publication_catalog
    result, snapshot_id = snapshot(owner)
    traced = []
    db.set_trace_callback(traced.append)
    try:
        model.publish_result(result)
    finally:
        db.set_trace_callback(None)
    assert_snapshot_seal(db, result, snapshot_id)
    member_query = next(
        sql
        for sql in traced
        if sql.startswith("SELECT table_name,fact_key_json FROM parsed_fact_members ")
    )
    plan = [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + member_query)]
    for index in RESULT_INDEXES:
        assert any(
            "SEARCH " in detail
            and index in detail
            and "parsed_result_uuidv4=?" in detail
            for detail in plan
        ), (index, plan)


def test_actual_sealing_vm_work_is_independent_of_unrelated_histories(
    publication_catalog,
):
    db, model, owner, unrelated, snapshot = publication_catalog
    definitions = [
        db.execute("SELECT sql FROM sqlite_schema WHERE name=?", (index,)).fetchone()[0]
        for index in RESULT_INDEXES
    ]

    def add_history(start, stop):
        for ordinal in range(start, stop):
            result, snapshot_id = snapshot(unrelated)
            model.publish_result(result)
            assert_snapshot_seal(db, result, snapshot_id)
            # Local naming evidence has no interpretation dependency or lifetime
            # coupling to the target result and is explicitly supported.
            db.execute(
                "INSERT INTO repository_name_observations VALUES(?,?,?,0,NULL,'{}',NULL,NULL)",
                (uid(), unrelated, f"synthetic-name-{ordinal}"),
            )

    def measure(indexed):
        result, snapshot_id = snapshot(owner)
        if not indexed:
            for index in RESULT_INDEXES:
                db.execute(f"DROP INDEX {index}")
        try:
            instructions = seal_and_count(db, model, result)
        finally:
            if not indexed:
                for definition in definitions:
                    db.execute(definition)
        assert_snapshot_seal(db, result, snapshot_id)
        return instructions

    add_history(0, 100)
    small_indexed = measure(True)
    small_unindexed = measure(False)
    add_history(100, 2000)
    large_indexed = measure(True)
    large_unindexed = measure(False)
    # Index B-tree height can add a bounded amount of work; unrelated member
    # counts must not produce a history-proportional output enumeration.
    assert large_indexed <= small_indexed * 1.15 + 64
    assert large_unindexed > small_unindexed * 5
    assert large_unindexed > large_indexed * 5
