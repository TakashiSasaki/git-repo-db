"""Unavailable parents cannot excuse known ownership or scalar contradictions."""

import copy
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import (
    validate_catalog,
    validate_record,
)
from repo_catalog.domain.models import CatalogError
from tests.integration.test_publication_free_architecture_corrections import (
    catalog as catalog,
)
from tests.integration.test_publication_free_architecture_corrections import pr
from tests.integration.test_publication_free_pending_contract import insert_stage, stage


def pending(ids, table):
    value = pr(ids)
    value["change_request_id"] = value["acquisition_scope"]["change_request_id"] = str(
        uuid.uuid4()
    )
    if table == "document_state":
        value.update(
            kind="pr-body", provider_change_request_document_id="22", body="body"
        )
        value.pop("state")
        value.pop("provider_resource_id")
    elif table == "review_thread_state":
        value.update(kind="review-thread", resolved=False)
        value.pop("state")
    elif table == "review_resources":
        value.update(
            kind="review", provider_change_request_document_id="22", body="body"
        )
        value.pop("state")
        value.pop("provider_resource_id")
    elif table == "issue_resources":
        value.update(
            kind="issue-comment",
            provider_resource_id="22",
            parent_provider_resource_id="12",
            provider_issue_number=1,
            body="body",
            provider_clock_scope="github-issue-comment-updated-at",
        )
        value.pop("state")
        value.pop("change_request_id")
        value["acquisition_scope"].pop("change_request_id")
    if table in {"review_thread_state", "review_resources"}:
        value["provider_updated_at_us"] = value["provider_clock_scope"] = None
    return value


def admit(db, table, value):
    if table in {"issue_resources", "review_resources"}:
        return CurrentResources(db).admit(value, source="import")
    return CurrentApiState(db).admit(table, value, source="import")


def reject_all_routes(db, table, value):
    row = stage(db, value, value)
    row["table_name"] = table
    with pytest.raises(CatalogError):
        admit(db, table, value)
    with pytest.raises(CatalogError):
        validate_record(db, "exchange_staging", row)
    with pytest.raises(sqlite3.IntegrityError):
        insert_stage(db, row)
    # Labelling a newly inserted malformed row as a diagnostic is no bypass.
    row["reason"] = "current_state:invalid"
    with pytest.raises(sqlite3.IntegrityError):
        insert_stage(db, row)
    assert db.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0


@pytest.mark.parametrize(
    "table",
    [
        "change_request_state",
        "document_state",
        "review_thread_state",
        "review_resources",
        "issue_resources",
    ],
)
@pytest.mark.parametrize("contradiction", ["repository", "service", "source"])
def test_missing_parent_still_checks_existing_owners(catalog, table, contradiction):
    db, ids = catalog
    value = pending(ids, table)
    if contradiction == "source":
        foreign_service, registration = str(uuid.uuid4()), str(uuid.uuid4())
        db.execute(
            "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','other','{}')",
            (foreign_service,),
        )
        db.execute(
            "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('foreign',?,?,'github_inventory','foreign','{}')",
            (registration, foreign_service),
        )
        value["acquisition_scope"]["source_registration_uuidv4"] = registration
    else:
        field = (
            "repository_uuidv4"
            if contradiction == "repository"
            else "service_instance_uuidv4"
        )
        value[field] = value["acquisition_scope"][field] = str(uuid.uuid4())
    reject_all_routes(db, table, value)


@pytest.mark.parametrize(
    "table,changes",
    [
        ("change_request_state", {"object_format": "sha256", "head_oid": "a" * 40}),
        ("review_thread_state", {"object_format": "sha1", "commit_oid": "a" * 64}),
        ("review_thread_state", {"object_format": "unsupported"}),
        ("document_state", {"body_status": "unsupported"}),
        ("document_state", {"body_status": "present", "body": None}),
        ("document_state", {"body_status": "missing", "body": "body"}),
        ("review_resources", {"state": "unsupported"}),
        ("review_resources", {"provider_change_request_document_id": "00"}),
        ("review_resources", {"target_commit_oid": "a" * 39}),
        ("review_resources", {"raw_path": "comment-only"}),
        ("issue_resources", {"state": "closed"}),
        ("issue_resources", {"provider_resource_id": "00"}),
    ],
)
def test_pending_scalars_obey_the_typed_domain_contract(catalog, table, changes):
    db, ids = catalog
    value = pending(ids, table)
    value.update(changes)
    reject_all_routes(db, table, value)


def test_detached_pending_capture_checks_known_binding_without_requiring_absent_one(
    catalog,
):
    db, ids = catalog
    value = pending(ids, "issue_resources")
    value["acquisition_scope"]["repository_uuidv4"] = str(uuid.uuid4())
    # Retained binding belongs to the current repository, not the captured one.
    reject_all_routes(db, "issue_resources", value)
    value["acquisition_scope"]["repository_binding_id"] = str(uuid.uuid4())
    assert admit(db, "issue_resources", value).status == "missing_dependency"
    assert validate_catalog(db)["records_checked"] > 0


@pytest.mark.parametrize("table", ["change_request_state", "issue_resources"])
def test_late_contradiction_is_diagnosed_without_blocking_valid_sibling(catalog, table):
    db, ids = catalog
    value = pending(ids, table)
    registration = str(uuid.uuid4())
    value["acquisition_scope"]["source_registration_uuidv4"] = registration
    assert admit(db, table, value).status == "missing_dependency"
    assert validate_catalog(db)["records_checked"] > 0

    foreign_service = str(uuid.uuid4())
    db.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','other','{}')",
        (foreign_service,),
    )
    db.execute(
        "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('late',?,?,'github_inventory','late','{}')",
        (registration, foreign_service),
    )
    sibling = pending(ids, "change_request_state")
    assert admit(db, "change_request_state", sibling).status == "missing_dependency"
    db.execute(
        "INSERT INTO change_requests VALUES(?,?,?,'pull_request',2)",
        (
            sibling["change_request_id"],
            ids["repository_uuidv4"],
            ids["repository_binding_id"],
        ),
    )
    assert CurrentApiState(db).promote_staging() == 1
    assert CurrentResources(db).promote_staging() == 0
    rows = db.execute("SELECT * FROM exchange_staging").fetchall()
    assert len(rows) == 1 and rows[0]["reason"] == "current_state:invalid"
    assert validate_catalog(db)["records_checked"] > 0
    candidates = CurrentApiState(db).export_candidates(
        ids["repository_uuidv4"]
    ) + CurrentResources(db).export_candidates(ids["repository_uuidv4"])
    assert len(candidates) == 1
    assert candidates[0][1]["change_request_id"] == sibling["change_request_id"]
    assert Graph(db).export(ids["repository_uuidv4"])["records"]
    # A diagnostic transition may retain the same rejected input, never alter it.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE exchange_staging SET record_json=?",
            (json.dumps({**value, "parser_module": "changed"}),),
        )


def test_sparse_git_update_inherits_known_format_and_capture(catalog):
    db, ids = catalog
    value = pr(ids)
    value.update(object_format="sha1", head_oid="a" * 40)
    assert admit(db, "change_request_state", value).status == "accepted"
    update = copy.deepcopy(value)
    update.pop("object_format")
    update.update(head_oid="b" * 40, provider_updated_at_us=20, observed_at_us=200)
    assert admit(db, "change_request_state", update).status == "accepted"
    row = db.execute("SELECT * FROM change_request_state").fetchone()
    assert row["object_format"] == "sha1" and row["head_oid"] == bytes.fromhex("b" * 40)
    evidence = json.loads(row["field_evidence_json"])
    assert evidence['["object_format"]']["observed_at_us"] == 100
    assert evidence['["head_oid"]']["observed_at_us"] == 200


@pytest.mark.parametrize("damage", ["unstored", "hash", "origin", "payload"])
def test_invalid_diagnostic_exemption_requires_the_exact_retained_input(
    catalog, damage
):
    db, ids = catalog
    value = pending(ids, "change_request_state")
    missing_binding = str(uuid.uuid4())
    value["repository_binding_id"] = value["acquisition_scope"][
        "repository_binding_id"
    ] = missing_binding
    assert admit(db, "change_request_state", value).status == "missing_dependency"
    other_repository = str(uuid.uuid4())
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'other','{}')",
        (other_repository,),
    )
    db.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,metadata) VALUES(?,?,?,'{}')",
        (missing_binding, other_repository, ids["service_instance_uuidv4"]),
    )
    assert CurrentApiState(db).promote_staging() == 0
    row = dict(db.execute("SELECT * FROM exchange_staging").fetchone())
    assert row["reason"] == "current_state:invalid"
    validate_record(db, "exchange_staging", row)
    original_key, original_hash = row["record_key"], row["content_sha256"]
    if damage == "unstored":
        db.execute("DELETE FROM exchange_staging")
    elif damage == "hash":
        row["content_sha256"] = b"x" * 32
    elif damage == "origin":
        row["origin_catalog_uuidv4"] = str(uuid.uuid4())
    else:
        row["record_json"] = json.dumps(
            {**json.loads(row["record_json"]), "parsed_at_us": 102}
        )
    with pytest.raises(CatalogError):
        validate_record(db, "exchange_staging", row)
    with pytest.raises(sqlite3.IntegrityError):
        if damage == "unstored":
            insert_stage(db, row)
        else:
            db.execute(
                "UPDATE exchange_staging SET "
                + ",".join(name + "=?" for name in row)
                + " WHERE record_key=? AND content_sha256=?",
                (*row.values(), original_key, original_hash),
            )
