"""Corrected counterexamples exercise the actual admission and SQL boundaries."""

import hashlib
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import (
    JsonContractError,
    validate_catalog,
)
from repo_catalog.adapters.sqlite.schema import (
    DDL_SHA256,
    FORMAT_ID,
    SCHEMA_VERSION,
    schema_sql,
)
from repo_catalog.domain.models import CatalogError


@pytest.fixture
def catalog():
    db = sqlite3.connect(":memory:", autocommit=True)
    db.row_factory = sqlite3.Row
    db.executescript(schema_sql())
    db.execute(
        "INSERT INTO database_identity VALUES(1,?,?,?,?,?,'validated')",
        (FORMAT_ID, SCHEMA_VERSION, str(uuid.uuid4()), 0, DDL_SHA256),
    )
    ids = {
        key: str(uuid.uuid4())
        for key in (
            "repository_uuidv4",
            "repository_binding_id",
            "service_instance_uuidv4",
            "change_request_id",
        )
    }
    db.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','synthetic','{}')",
        (ids["service_instance_uuidv4"],),
    )
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'synthetic','{}')",
        (ids["repository_uuidv4"],),
    )
    db.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,metadata) VALUES(?,?,?,'{}')",
        (
            ids["repository_binding_id"],
            ids["repository_uuidv4"],
            ids["service_instance_uuidv4"],
        ),
    )
    db.execute(
        "INSERT INTO change_requests VALUES(?,?,?,'pull_request',1)",
        (
            ids["change_request_id"],
            ids["repository_uuidv4"],
            ids["repository_binding_id"],
        ),
    )
    yield db, ids
    db.close()


def pr(ids):
    return {
        **ids,
        "kind": "change-request",
        "provider_resource_id": "12",
        "state": "open",
        "observed_at_us": 100,
        "parsed_at_us": 101,
        "provider_updated_at_us": 10,
        "provider_clock_scope": "github-pr-updated-at",
        "parser_module": "correction.synthetic",
        "parser_version": "1",
        "acquisition_scope": {**ids, "endpoint": "pulls/1"},
    }


@pytest.mark.parametrize("missing_parent", [False, True])
@pytest.mark.parametrize(
    "replica",
    [
        {"raw_api_response": {"data": {"body": "synthetic original"}}},
        {"api_response_b64": "c3ludGhldGlj"},
        {"request_context": {"query": "query { pullRequest { body } }"}},
    ],
)
def test_api_capture_rejects_replica_before_current_or_pending_write(
    catalog, missing_parent, replica
):
    db, ids = catalog
    value = pr(ids)
    if missing_parent:
        value["change_request_id"] = value["acquisition_scope"]["change_request_id"] = (
            str(uuid.uuid4())
        )
    value["acquisition_scope"].update(replica)
    with pytest.raises(JsonContractError):
        CurrentApiState(db).admit("change_request_state", value, source="import")
    assert db.execute("SELECT count(*) FROM change_request_state").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0


def test_issue_metadata_rejects_original_but_keeps_modeled_nested_field(catalog):
    db, ids = catalog
    ids = {k: v for k, v in ids.items() if k != "change_request_id"}
    value = {
        **ids,
        "kind": "issue",
        "provider_resource_id": "10",
        "provider_issue_number": 1,
        "body": "domain text",
        "observed_at_us": 100,
        "parsed_at_us": 101,
        "provider_updated_at_us": 10,
        "provider_clock_scope": "github-issue-updated-at",
        "parser_module": "correction.synthetic",
        "parser_version": "1",
        "acquisition_scope": {**ids, "endpoint": "issues/1"},
        "metadata": {"raw_api_response": {"body": "synthetic original"}},
    }
    with pytest.raises(JsonContractError):
        CurrentResources(db).admit(value, source="import")
    value["metadata"] = {"milestone": {"title": "actual milestone", "state": "open"}}
    assert CurrentResources(db).admit(value, source="import").status == "accepted"
    row = db.execute(
        "SELECT metadata,field_evidence_json FROM issue_resources"
    ).fetchone()
    assert json.loads(row["metadata"]) == value["metadata"]
    assert '["metadata","milestone","title"]' in json.loads(row["field_evidence_json"])


def test_sql_current_capture_and_origin_have_same_closed_shape(catalog):
    db, ids = catalog
    CurrentApiState(db).admit("change_request_state", pr(ids), source="import")
    row = db.execute(
        "SELECT acquisition_scope_json,field_evidence_json FROM change_request_state"
    ).fetchone()
    scope = json.loads(row["acquisition_scope_json"])
    scope["encoded_response"] = "synthetic"
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE change_request_state SET acquisition_scope_json=?",
            (json.dumps(scope),),
        )
    evidence = json.loads(row["field_evidence_json"])
    next(iter(evidence.values()))["acquisition_scope"]["raw_api_response"] = {
        "body": "synthetic"
    }
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE change_request_state SET field_evidence_json=?",
            (json.dumps(evidence),),
        )
    assert validate_catalog(db)["records_checked"] > 0


@pytest.mark.parametrize(
    "table,reason",
    [
        ("not_a_domain_table", "missing_dependency"),
        ("change_request_state", "missing_dependency"),
        ("change_request_state", "current_state:missing_dependency"),
    ],
)
def test_staging_rejects_unmodeled_envelope_or_candidate_via_sql(
    catalog, table, reason
):
    db, ids = catalog
    raw = json.dumps({"entire_api_original": {"data": {"body": "synthetic"}}})
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO exchange_staging VALUES(?,?,?,?,?,?,?)",
            (
                "nonsense:record",
                hashlib.sha256(raw.encode()).digest(),
                table,
                ids["repository_uuidv4"],
                str(uuid.uuid4()),
                raw,
                reason,
            ),
        )


def test_pending_wire_metadata_validated_before_parent_resolution(catalog):
    db, ids = catalog
    CurrentApiState(db).admit("change_request_state", pr(ids), source="import")
    record = next(
        r
        for r in Graph(db).export(ids["repository_uuidv4"])["records"]
        if r["table"] == "change_request_state"
    )
    record["values"]["metadata"] = json.dumps(
        {"raw_api_response": {"data": {"body": "synthetic"}}}
    )
    receiver = sqlite3.connect(":memory:", autocommit=True)
    receiver.executescript(schema_sql())
    try:
        with pytest.raises(JsonContractError):
            Graph(receiver).validate_record(record)
        assert (
            receiver.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0
        )
    finally:
        receiver.close()


@pytest.mark.parametrize(
    "case",
    ["wrong-source", "foreign-pair", "non-uuid", "replica", "duplicate", "nonterminal"],
)
def test_source_inventory_requires_exact_owner_positive_pairs_and_terminal(
    catalog, case
):
    db, ids = catalog
    registrations = {name: str(uuid.uuid4()) for name in ("a", "b")}
    for name, registration in registrations.items():
        db.execute(
            "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES(?,?,?,'github_inventory',?,'{}')",
            (name, registration, ids["service_instance_uuidv4"], name),
        )
    db.execute(
        "INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES(?,?)",
        ("b" if case == "foreign-pair" else "a", ids["repository_uuidv4"]),
    )
    scope = {
        "source_registration_uuidv4": registrations[
            "b" if case == "wrong-source" else "a"
        ],
        "service_instance_uuidv4": ids["service_instance_uuidv4"],
        "endpoint": "inventory",
    }
    members = [ids["repository_uuidv4"]]
    if case == "non-uuid":
        members = ["not-a-repository"]
    elif case == "replica":
        members = [{"raw_api_response": {"body": "synthetic"}}]
    elif case == "duplicate":
        members *= 2
    terminal = case != "nonterminal"
    with pytest.raises(CatalogError):
        CurrentApiState(db).assess_source_inventory(
            "a",
            scope=scope,
            observed_at_us=100,
            state="complete",
            members=members,
            terminal=terminal,
            parser_module="correction.synthetic",
            parser_version="1",
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO source_inventory_assessments VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                "a",
                "synthetic-scope",
                json.dumps(scope),
                100,
                "complete",
                int(terminal),
                json.dumps(members),
                "correction.synthetic",
                "1",
                None,
            ),
        )
    assert (
        db.execute("SELECT count(*) FROM source_inventory_assessments").fetchone()[0]
        == 0
    )


@pytest.mark.parametrize(
    "members",
    [
        [],
        [
            {
                "family": "thread",
                "provider_resource_id": "thread-1",
                "state_digest": "a" * 64,
            }
        ],
    ],
)
def test_thread_completion_requires_each_observed_reply_obligation(catalog, members):
    db, ids = catalog
    if members:
        value = pr(ids)
        value.update(
            kind="review-thread",
            provider_resource_id="thread-1",
            provider_updated_at_us=None,
            provider_clock_scope=None,
            resolved=False,
        )
        value.pop("state")
        CurrentApiState(db).admit("review_thread_state", value, source="import")
        members[0]["change_request_id"] = ids["change_request_id"]
    collection = str(uuid.uuid4())
    db.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,scope_json) VALUES(?,?,?,'threads',?)",
        (
            collection,
            ids["repository_uuidv4"],
            ids["change_request_id"],
            json.dumps({**ids, "endpoint": "threads"}),
        ),
    )
    proof = CurrentCollectionProof(db)
    proof.page(
        collection,
        0,
        100,
        None,
        members,
        parser_module="correction.synthetic",
        parser_version="1",
    )
    evidence = {
        **proof.evidence(collection),
        "kind": "current-resource-tree-v1",
        "fetch_collection_ids": [],
    }
    marker = {
        "fetch_collection_id": collection,
        "asserted_state": "complete",
        "evidence": json.dumps(evidence),
        "observed_at_us": 100,
    }
    assert proof.is_complete_marker(marker) == (not members)
    if members:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO completion_markers(fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,'complete',?,100)",
                (collection, json.dumps(evidence)),
            )
    else:
        db.execute(
            "INSERT INTO completion_markers(fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,'complete',?,100)",
            (collection, json.dumps(evidence)),
        )
        assert (
            Graph(db).proof_requirements(
                "completion_markers",
                dict(db.execute("SELECT * FROM completion_markers").fetchone()),
            )
            is not None
        )
