"""Indexed collection closure has no parser/input/history prerequisites."""

import json
import sqlite3

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.domain.current_state import fingerprint_candidate
from tests.integration.test_catalog3_exchange import (
    candidate,
    complete_collection,
    fixture,
    receive,
    uid,
)
from tests.integration.test_catalog3_exchange import databases as databases


def another_collection(db, expected, *, observed=2, body="other comment"):
    values = candidate(expected, "issue-comment", body, updated=observed)
    values["provider_change_request_document_id"] = str(observed)
    assert CurrentApiState(db).admit("document_state", values).status == "accepted"
    collection = uid()
    db.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,scope_json) VALUES(?,?,?,'comments',?)",
        (
            collection,
            expected["repository"],
            expected["cr"],
            json.dumps(values["acquisition_scope"]),
        ),
    )
    CurrentCollectionProof(db).page(
        collection,
        0,
        observed,
        None,
        [
            {
                "family": "document",
                "change_request_id": expected["cr"],
                "kind": "issue-comment",
                "provider_change_request_document_id": str(observed),
                "state_digest": fingerprint_candidate(values),
            }
        ],
        parser_module="synthetic",
        parser_version="v1",
    )
    complete_collection(db, collection)
    return collection


def test_selected_collection_includes_actual_members_without_siblings(databases):
    source, target = databases
    expected = fixture(source)
    complete_collection(source, expected["collection"])
    sibling = another_collection(source, expected)
    unit = Graph(source).export(
        expected["repository"], fetch_collection_id=expected["collection"]
    )
    assert sibling not in json.dumps(unit)
    assert "other comment" not in json.dumps(unit)
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute(
        "SELECT count(*) FROM eligible_document_state"
    ).fetchone() == (1,)
    assert target.execute("SELECT count(*) FROM completion_markers").fetchone() == (1,)


def test_reopen_missing_dependency_intake_then_onward_export(databases, tmp_path):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    parents = [
        r
        for r in unit["records"]
        if r["table"] in {"repositories", "repository_bindings"}
    ]
    partial = {**unit, "records": [r for r in unit["records"] if r not in parents]}
    assert receive(target, partial)["staged_records"] > 0
    disk = sqlite3.connect(tmp_path / "receiver.sqlite", isolation_level=None)
    target.backup(disk)
    disk.close()
    disk = sqlite3.connect(tmp_path / "receiver.sqlite", isolation_level=None)
    disk.execute("PRAGMA foreign_keys=ON")
    disk.execute("PRAGMA recursive_triggers=ON")
    try:
        assert receive(disk, {**unit, "records": parents})["staged_records"] == 0
        onward = Graph(disk).export(expected["repository"])
        assert receive(source, onward)["staged_records"] == 0
        assert disk.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        disk.close()


def test_valid_member_usable_before_terminal_evidence(databases):
    source, target = databases
    expected = fixture(source)
    complete_collection(source, expected["collection"])
    unit = Graph(source).export(expected["repository"])
    marker = next(r for r in unit["records"] if r["table"] == "completion_markers")
    assert (
        receive(
            target, {**unit, "records": [r for r in unit["records"] if r is not marker]}
        )["staged_records"]
        == 0
    )
    assert target.execute(
        "SELECT count(*) FROM eligible_document_state"
    ).fetchone() == (1,)
    assert target.execute("SELECT count(*) FROM completion_markers").fetchone() == (0,)
    assert receive(target, {**unit, "records": [marker]})["staged_records"] == 0


def test_selected_collection_preserves_bounded_current_conflict(databases):
    source, target = databases
    expected = fixture(source)
    alternative = candidate(expected, "pr-body", "unordered alternative", updated=1)
    assert (
        CurrentApiState(source).admit("document_state", alternative).status
        == "conflict"
    )
    unit = Graph(source).export(
        expected["repository"], fetch_collection_id=expected["collection"]
    )
    assert sum(r["table"] == "document_state" for r in unit["records"]) == 2
    result = receive(target, unit)
    assert result["staged_records"] == 1
    assert target.execute(
        "SELECT count(*) FROM eligible_document_state"
    ).fetchone() == (0,)
    assert receive(target, unit)["received_records"] == 0
