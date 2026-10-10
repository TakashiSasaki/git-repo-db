"""Typed domain exchange: ordering, integrity, ownership and latest-only state."""

import copy
import hashlib
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, SCHEMA_VERSION, schema_sql
from repo_catalog.domain.current_state import fingerprint_candidate


def uid():
    return str(uuid.uuid4())


def catalog():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(schema_sql())
    db.execute(
        "INSERT INTO database_identity VALUES(1,'repo-catalog/catalog3',?,?,0,?,'validated')",
        (SCHEMA_VERSION, uid(), DDL_SHA256),
    )
    return db


@pytest.fixture
def databases():
    connections = [catalog(), catalog()]
    yield connections
    for db in connections:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        db.close()


def candidate(expected, kind="change-request", body=None, *, updated=1):
    values = {
        "change_request_id": expected["cr"],
        "kind": kind,
        "repository_uuidv4": expected["repository"],
        "repository_binding_id": expected["binding"],
        "service_instance_uuidv4": expected["service"],
        "observed_at_us": updated,
        "parsed_at_us": updated,
        "provider_updated_at_us": updated,
        "provider_clock_scope": "github-pr-updated-at"
        if kind != "issue-comment"
        else "github-issue-comment-updated-at",
        "parser_module": "synthetic",
        "parser_version": "v1",
        "metadata": {},
        "acquisition_scope": {
            "repository_uuidv4": expected["repository"],
            "repository_binding_id": expected["binding"],
            "service_instance_uuidv4": expected["service"],
            "source_registration_uuidv4": expected["source"],
            "change_request_id": expected["cr"],
            "endpoint": "synthetic",
            "request_context": {},
        },
    }
    if kind == "change-request":
        values.update(
            state="open", draft=False, merged=False, provider_resource_id="node-1"
        )
    else:
        values.update(
            provider_change_request_document_id="1",
            body=body,
            body_status="present" if body is not None else "provider-null",
        )
    return values


def fixture(
    db,
    *,
    repository=None,
    source_local="source",
    source_registration=None,
    service=None,
    body=b"hello",
    next_cursor=None,
):
    expected = {
        "repository": repository or uid(),
        "source": source_registration or uid(),
        "service": service or uid(),
        "binding": uid(),
        "cr": uid(),
        "collection": uid(),
    }
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'repo','{}')",
        (expected["repository"],),
    )
    if not db.execute(
        "SELECT 1 FROM service_instances WHERE service_instance_uuidv4=?",
        (expected["service"],),
    ).fetchone():
        db.execute(
            "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','github','{}')",
            (expected["service"],),
        )
    if not db.execute(
        "SELECT 1 FROM sources WHERE source_registration_uuidv4=?",
        (expected["source"],),
    ).fetchone():
        db.execute(
            "INSERT INTO sources VALUES(?,?,?,'github_inventory','source',NULL)",
            (source_local, expected["source"], expected["service"]),
        )
    db.execute(
        "INSERT INTO repository_bindings VALUES(?,?,?,?,'{}',0)",
        (
            expected["binding"],
            expected["repository"],
            expected["service"],
            expected["repository"],
        ),
    )
    db.execute(
        "INSERT INTO change_requests VALUES(?,?,?,'pull_request',1)",
        (expected["cr"], expected["repository"], expected["binding"]),
    )
    db.execute(
        "INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES(?,?)",
        (source_local, expected["repository"]),
    )
    api = CurrentApiState(db)
    assert api.admit("change_request_state", candidate(expected)).status == "accepted"
    document = candidate(expected, "pr-body", body.decode("utf8"))
    assert api.admit("document_state", document).status == "accepted"
    db.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,source_id,kind,observed_at_us,scope_json) VALUES(?,?,?,?, 'pr-body',1,?)",
        (
            expected["collection"],
            expected["repository"],
            expected["cr"],
            source_local,
            json.dumps(candidate(expected)["acquisition_scope"]),
        ),
    )
    CurrentCollectionProof(db).page(
        expected["collection"],
        0,
        1,
        next_cursor,
        [
            {
                "family": "document",
                "change_request_id": expected["cr"],
                "kind": "pr-body",
                "provider_change_request_document_id": "1",
                "state_digest": fingerprint_candidate(document),
            }
        ],
        parser_module="synthetic",
        parser_version="v1",
    )
    return expected


def complete_collection(db, collection_id):
    proof = CurrentCollectionProof(db)
    db.execute(
        "INSERT INTO completion_markers(fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,'complete',?,?)",
        (
            collection_id,
            json.dumps(proof.evidence(collection_id)),
            proof.observed_at_us(collection_id),
        ),
    )
    return collection_id


def receive(db, unit):
    db.execute("BEGIN IMMEDIATE")
    try:
        result = Graph(db).receive(unit)
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise


@pytest.mark.parametrize("reverse", [False, True])
def test_domain_roundtrip_latest_only_repeated_reverse(databases, reverse):
    source, target = databases
    expected = fixture(source)
    complete_collection(source, expected["collection"])
    old = Graph(source).export(expected["repository"])
    newer = candidate(expected, "pr-body", "new current body", updated=2)
    assert CurrentApiState(source).admit("document_state", newer).status == "accepted"
    current = Graph(source).export(expected["repository"])
    assert "hello" not in json.dumps(current)
    assert not {"parsed_results", "fetch_occurrences", "payloads", "stored_bytes"} & {
        r["table"] for r in current["records"]
    }
    units = [old, current]
    if reverse:
        units.reverse()
    for unit in units:
        unit = copy.deepcopy(unit)
        unit["records"].reverse()
        result = receive(target, unit)
        assert result["staged_records"] == 0, target.execute(
            "SELECT table_name,reason FROM exchange_staging"
        ).fetchall()
    assert target.execute(
        "SELECT body FROM document_state s JOIN text_bodies b ON b.sha256=s.text_body_sha256"
    ).fetchall() == [("new current body",)]
    assert receive(target, current)["received_records"] == 0
    assert target.execute("SELECT count(*) FROM document_state").fetchone() == (1,)
    assert "record_json" not in {
        r[1] for r in target.execute("PRAGMA table_info(exchange_admissions)")
    }
    assert "hello" not in json.dumps(Graph(target).export(expected["repository"]))


def test_missing_parent_stays_pending_then_promotes(databases):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    root = next(r for r in unit["records"] if r["table"] == "repositories")
    partial = {
        **unit,
        "records": [r for r in unit["records"] if r["table"] != "repositories"],
    }
    assert receive(target, partial)["staged_records"] > 0
    assert target.execute("SELECT count(*) FROM document_state").fetchone() == (0,)
    assert receive(target, {**unit, "records": [root]})["staged_records"] == 0
    assert target.execute(
        "SELECT count(*) FROM eligible_document_state"
    ).fetchone() == (1,)


def test_corrupt_text_rejected_without_staging_byte_copy(databases):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    text = next(r for r in unit["records"] if r["table"] == "text_bodies")
    text["values"]["body"] = "corrupt"
    result = receive(target, unit)
    assert result["rejected_records"] >= 2
    assert target.execute("SELECT count(*) FROM text_bodies").fetchone() == (0,)
    assert "corrupt" not in str(
        target.execute("SELECT record_json FROM exchange_staging").fetchall()
    )


def test_arbitrary_dependency_hint_does_not_authorize_bytes(databases):
    source, target = databases
    expected = fixture(source)
    complete_collection(source, expected["collection"])
    unit = Graph(source).export(expected["repository"])
    digest = hashlib.sha256(b"unrelated API envelope").digest()
    orphan = {
        "table": "stored_bytes",
        "key": "stored_bytes:"
        + json.dumps({"sha256": {"$sha256": digest.hex()}}, separators=(",", ":")),
        "values": {
            "sha256": {"$sha256": digest.hex()},
            "body": {
                "$bytes": __import__("base64")
                .b64encode(b"unrelated API envelope")
                .decode()
            },
            "byte_length": 22,
        },
    }
    orphan["values"]["byte_length"] = len(b"unrelated API envelope")
    marker = next(r for r in unit["records"] if r["table"] == "completion_markers")
    marker["requires"].append(orphan["key"])
    unit["records"].append(orphan)
    assert receive(target, unit)["rejected_records"] == 1
    assert target.execute("SELECT count(*) FROM stored_bytes").fetchone() == (0,)
    assert "unrelated API envelope" not in str(
        target.execute("SELECT record_json FROM exchange_staging").fetchall()
    )
    assert target.execute(
        "SELECT count(*) FROM eligible_document_state"
    ).fetchone() == (1,)


def test_source_pair_current_attributes_repeat_conflict_and_forward(databases):
    source, target = databases
    expected = fixture(source)
    api = CurrentApiState(source)
    scope = {
        "repository_uuidv4": expected["repository"],
        "service_instance_uuidv4": expected["service"],
        "source_registration_uuidv4": expected["source"],
        "endpoint": "synthetic-inventory",
    }
    assert (
        api.confirm_source_repository(
            "source",
            expected["repository"],
            observed_at_us=1,
            first_seen_us=-1,
            parsed_at_us=1,
            scope=scope,
            parser_module="source-parser",
            parser_version="1",
            name="named member",
            source="import",
        )
        == "accepted"
    )
    unit = Graph(source).export(expected["repository"])
    assert receive(target, unit)["staged_records"] == 0
    assert receive(target, unit)["received_records"] == 0
    assert target.execute(
        "SELECT first_seen_us,last_seen_us,name FROM source_repositories"
    ).fetchone() == (-1, 1, "named member")
    assert (
        receive(source, Graph(target).export(expected["repository"]))["staged_records"]
        == 0
    )
    assert (
        api.confirm_source_repository(
            "source",
            expected["repository"],
            observed_at_us=2,
            parsed_at_us=2,
            scope=scope,
            parser_module="source-parser",
            parser_version="1",
            name="unordered rename",
            source="import",
        )
        == "conflict"
    )
    conflicting = Graph(source).export(expected["repository"])
    assert sum(r["table"] == "source_repositories" for r in conflicting["records"]) == 2
    result = receive(target, conflicting)
    assert result["staged_records"] == 1
    assert target.execute("SELECT count(*) FROM source_repositories").fetchone() == (1,)
    assert target.execute(
        "SELECT count(*) FROM eligible_document_state"
    ).fetchone() == (1,)
    assert receive(target, conflicting)["received_records"] == 0
    assert (
        receive(source, Graph(target).export(expected["repository"]))["staged_records"]
        == 1
    )


def test_local_source_policy_and_unselected_repository_do_not_transfer(databases):
    source, target = databases
    expected = fixture(source)
    other = fixture(
        source,
        source_local="source",
        source_registration=expected["source"],
        service=expected["service"],
        body=b"other repository body",
    )
    source.execute(
        "UPDATE sources SET settings=?",
        (json.dumps({"token": "synthetic-sender-setting"}),),
    )
    target.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'receiver name','{}')",
        (expected["repository"],),
    )
    target.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','receiver label','{}')",
        (expected["service"],),
    )
    target.execute(
        "INSERT INTO sources VALUES('receiver-source',?,?,'github_inventory','receiver local',?)",
        (
            expected["source"],
            expected["service"],
            json.dumps({"token": "synthetic-receiver-setting"}),
        ),
    )
    unit = Graph(source).export(expected["repository"])
    serialized = json.dumps(unit)
    assert other["repository"] not in serialized
    assert "other repository body" not in serialized
    assert "synthetic-sender-setting" not in serialized
    assert receive(target, unit)["staged_records"] == 0
    assert json.loads(target.execute("SELECT settings FROM sources").fetchone()[0]) == {
        "token": "synthetic-receiver-setting"
    }
    assert target.execute("SELECT name FROM repositories").fetchone() == (
        "receiver name",
    )
    assert target.execute("SELECT source_id FROM source_repositories").fetchone() == (
        "receiver-source",
    )
