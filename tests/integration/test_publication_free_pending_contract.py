"""Typed pending candidates defer dependencies, never their authored shape."""

import copy
import hashlib
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import (
    JsonContractError,
    validate_catalog,
    validate_record,
)
from repo_catalog.domain.models import CatalogError
from tests.integration.test_publication_free_architecture_corrections import (
    catalog as catalog,
)
from tests.integration.test_publication_free_architecture_corrections import pr


def stage(db, ids, value, *, key=None):
    raw = json.dumps(value)
    row = {
        "record_key": key or "current-state:" + "a" * 64,
        "content_sha256": hashlib.sha256(raw.encode()).digest(),
        "table_name": "change_request_state",
        "repository_uuidv4": ids["repository_uuidv4"],
        "origin_catalog_uuidv4": str(uuid.uuid4()),
        "record_json": raw,
        "reason": "current_state:missing_dependency",
    }
    return row


def insert_stage(db, row):
    db.execute(
        "INSERT INTO exchange_staging VALUES(?,?,?,?,?,?,?)", tuple(row.values())
    )


@pytest.mark.parametrize(
    "field",
    [
        "kind",
        "repository_uuidv4",
        "repository_binding_id",
        "service_instance_uuidv4",
        "change_request_id",
        "observed_at_us",
        "parsed_at_us",
        "parser_module",
        "parser_version",
        "acquisition_scope",
    ],
)
@pytest.mark.parametrize("null", [False, True])
def test_typed_pending_requires_minimum_candidate_before_sql_retention(
    catalog, field, null
):
    db, ids = catalog
    value = pr(ids)
    if null:
        value[field] = None
    else:
        value.pop(field)
    row = stage(db, ids, value)
    with pytest.raises(JsonContractError):
        validate_record(db, "exchange_staging", row)
    with pytest.raises(sqlite3.IntegrityError):
        insert_stage(db, row)
    assert db.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0


@pytest.mark.parametrize(
    "field",
    [
        "repository_uuidv4",
        "repository_binding_id",
        "service_instance_uuidv4",
        "change_request_id",
        "endpoint",
    ],
)
def test_pending_capture_cannot_omit_required_typed_context(catalog, field):
    db, ids = catalog
    value = pr(ids)
    value["acquisition_scope"].pop(field)
    row = stage(db, ids, value)
    with pytest.raises(JsonContractError):
        validate_record(db, "exchange_staging", row)
    with pytest.raises(sqlite3.IntegrityError):
        insert_stage(db, row)


@pytest.mark.parametrize(
    "field",
    [
        "repository_uuidv4",
        "repository_binding_id",
        "service_instance_uuidv4",
        "change_request_id",
    ],
)
@pytest.mark.parametrize("missing_parent", [False, True])
def test_pending_capture_owner_must_match_candidate_even_without_parent(
    catalog, field, missing_parent
):
    db, ids = catalog
    value = pr(ids)
    if missing_parent:
        value["change_request_id"] = value["acquisition_scope"]["change_request_id"] = (
            str(uuid.uuid4())
        )
    value["acquisition_scope"][field] = str(uuid.uuid4())
    row = stage(db, ids, value)
    with pytest.raises(JsonContractError):
        validate_record(db, "exchange_staging", row)
    with pytest.raises(sqlite3.IntegrityError):
        insert_stage(db, row)
    with pytest.raises(CatalogError):
        CurrentApiState(db).admit("change_request_state", value, source="import")
    assert db.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0


def test_reviewer_minimal_and_foreign_parent_candidates_reject_with_valid_key_shape(
    catalog,
):
    db, ids = catalog
    values = [{"kind": "change-request", "acquisition_scope": {}}, pr(ids)]
    values[1]["acquisition_scope"]["change_request_id"] = str(uuid.uuid4())
    for value in values:
        with pytest.raises(sqlite3.IntegrityError):
            insert_stage(db, stage(db, ids, value))
    assert validate_catalog(db)["records_checked"] > 0
    assert Graph(db).export(ids["repository_uuidv4"])["records"]


@pytest.mark.parametrize("case", ["repository", "key", "origin"])
def test_pending_envelope_and_field_origins_stay_with_their_typed_subject(
    catalog, case
):
    db, ids = catalog
    value = pr(ids)
    if case == "origin":
        origin = {
            key: value[key]
            for key in (
                "provider_updated_at_us",
                "provider_clock_scope",
                "observed_at_us",
                "parsed_at_us",
                "parser_module",
                "parser_version",
                "acquisition_scope",
            )
        }
        origin = copy.deepcopy(origin)
        origin["acquisition_scope"]["change_request_id"] = str(uuid.uuid4())
        value["field_evidence"] = {'["state"]': origin}
    row = stage(db, ids, value)
    if case == "repository":
        row["repository_uuidv4"] = str(uuid.uuid4())
    elif case == "key":
        row["record_key"] = "nonsense:record"
    with pytest.raises(JsonContractError):
        validate_record(db, "exchange_staging", row)
    with pytest.raises(sqlite3.IntegrityError):
        insert_stage(db, row)


def test_genuine_missing_parent_stages_then_promotes_without_inventing_owner(catalog):
    db, ids = catalog
    value = pr(ids)
    parent = str(uuid.uuid4())
    value["change_request_id"] = value["acquisition_scope"]["change_request_id"] = (
        parent
    )
    adapter = CurrentApiState(db)
    assert (
        adapter.admit("change_request_state", value, source="import").status
        == "missing_dependency"
    )
    assert db.execute("SELECT count(*) FROM change_request_state").fetchone()[0] == 0
    assert validate_catalog(db)["records_checked"] > 0
    db.execute(
        "INSERT INTO change_requests VALUES(?,?,?,'pull_request',2)",
        (parent, ids["repository_uuidv4"], ids["repository_binding_id"]),
    )
    assert adapter.promote_staging() == 1
    assert (
        db.execute(
            "SELECT state FROM change_request_state WHERE change_request_id=?",
            (parent,),
        ).fetchone()[0]
        == "open"
    )
    assert db.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0


def test_detached_issue_comment_capture_stages_and_keeps_prior_origin_on_promotion(
    catalog,
):
    db, ids = catalog
    next_repo, next_binding = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'new','{}')",
        (next_repo,),
    )
    db.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,metadata) VALUES(?,?,?,'{}')",
        (next_binding, next_repo, ids["service_instance_uuidv4"]),
    )
    old = {
        key: ids[key]
        for key in (
            "repository_uuidv4",
            "repository_binding_id",
            "service_instance_uuidv4",
        )
    }
    moved = {
        **old,
        "repository_uuidv4": next_repo,
        "repository_binding_id": next_binding,
    }
    value = {
        **moved,
        "kind": "issue-comment",
        "provider_resource_id": "22",
        "provider_issue_number": 2,
        "parent_provider_resource_id": "12",
        "body": "prior captured comment",
        "provider_updated_at_us": 10,
        "provider_clock_scope": "github-issue-comment-updated-at",
        "observed_at_us": 100,
        "parsed_at_us": 101,
        "parser_module": "pending.synthetic",
        "parser_version": "1",
        "acquisition_scope": {**old, "endpoint": "issue-comments/22"},
    }
    adapter = CurrentResources(db)
    assert adapter.admit(value, source="import").status == "missing_dependency"
    assert validate_catalog(db)["records_checked"] > 0
    parent = {
        **value,
        "kind": "issue",
        "provider_resource_id": "12",
        "provider_clock_scope": "github-issue-updated-at",
        "acquisition_scope": {**moved, "endpoint": "issues/2"},
    }
    parent.pop("parent_provider_resource_id")
    assert adapter.admit(parent, source="import").status == "accepted"
    assert adapter.promote_staging() == 1
    row = adapter.candidate_from_row(
        "issue_resources",
        db.execute(
            "SELECT * FROM issue_resources WHERE kind='issue-comment'"
        ).fetchone(),
    )
    assert row["body"] == "prior captured comment"
    assert row["acquisition_scope"]["repository_uuidv4"] == old["repository_uuidv4"]
    assert db.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0


@pytest.mark.parametrize(
    "case", ["optional-source-uuid", "omitted-field", "metadata-ancestor"]
)
def test_pending_capture_and_evidence_shape_does_not_wait_for_dependencies(
    catalog, case
):
    db, ids = catalog
    value = pr(ids)
    if case == "optional-source-uuid":
        value["acquisition_scope"]["source_registration_uuidv4"] = "not-a-uuid"
    else:
        origin = {
            key: copy.deepcopy(value[key])
            for key in (
                "provider_updated_at_us",
                "provider_clock_scope",
                "observed_at_us",
                "parsed_at_us",
                "parser_module",
                "parser_version",
                "acquisition_scope",
            )
        }
        if case == "omitted-field":
            value.pop("state")
            value["field_evidence"] = {'["state"]': origin}
        else:
            value["metadata"] = {"milestone": {"title": "known"}}
            value["field_evidence"] = {'["metadata","milestone","title"]': origin}
    row = stage(db, ids, value)
    with pytest.raises(JsonContractError):
        validate_record(db, "exchange_staging", row)
    with pytest.raises(sqlite3.IntegrityError):
        insert_stage(db, row)
    assert db.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0


@pytest.mark.parametrize("instant", [0, -1, -(2**63), 2**63 - 1])
def test_signed_epoch_pending_retains_zero_negative_and_boundary_clocks(
    catalog, instant
):
    db, ids = catalog
    value = pr(ids)
    parent = str(uuid.uuid4())
    value["change_request_id"] = value["acquisition_scope"]["change_request_id"] = (
        parent
    )
    for name in ("observed_at_us", "parsed_at_us", "provider_updated_at_us"):
        value[name] = instant
    adapter = CurrentApiState(db)
    assert (
        adapter.admit("change_request_state", value, source="import").status
        == "missing_dependency"
    )
    assert validate_catalog(db)["records_checked"] > 0
    db.execute(
        "INSERT INTO change_requests VALUES(?,?,?,'pull_request',2)",
        (parent, ids["repository_uuidv4"], ids["repository_binding_id"]),
    )
    assert adapter.promote_staging() == 1
    row = db.execute(
        "SELECT observed_at_us,parsed_at_us,provider_updated_at_us FROM change_request_state WHERE change_request_id=?",
        (parent,),
    ).fetchone()
    assert tuple(row) == (instant, instant, instant)


@pytest.mark.parametrize("instant", [2**63, -(2**63) - 1, True, 0.5])
def test_optional_pending_provider_clock_still_requires_signed_int64(catalog, instant):
    db, ids = catalog
    value = pr(ids)
    value["provider_updated_at_us"] = instant
    row = stage(db, ids, value)
    with pytest.raises(JsonContractError):
        validate_record(db, "exchange_staging", row)
    with pytest.raises(sqlite3.IntegrityError):
        insert_stage(db, row)
    assert db.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0
