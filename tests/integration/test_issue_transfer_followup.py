"""Transfers change membership while retaining actual acquisition evidence."""

import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import validate_catalog
from repo_catalog.adapters.sqlite.schema import (
    DDL_SHA256,
    FORMAT_ID,
    SCHEMA_VERSION,
    schema_sql,
)
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_exchange import receive
from tests.integration.test_current_resources import issue
from tests.integration.test_current_resources import resources as resources


def _source(db, service, repository):
    local, registration = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(
        "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name) VALUES(?,?,?,'github_inventory','synthetic transfer')",
        (local, registration, service),
    )
    db.execute("INSERT INTO source_repositories VALUES(?,?,-2,0)", (local, repository))
    return registration


def _transfer(resources):
    adapter, context, _, _, _ = resources
    db = adapter.c
    old_source = _source(
        db, context["service_instance_uuidv4"], context["repository_uuidv4"]
    )
    old_scope = {
        **context,
        "source_registration_uuidv4": old_source,
        "endpoint": "https://synthetic.invalid/repos/a/issues/2/comments",
    }
    parent = issue(
        resources,
        acquisition_scope={
            **old_scope,
            "endpoint": "https://synthetic.invalid/repos/a/issues",
        },
    )
    child = issue(
        resources,
        kind="issue-comment",
        provider_resource_id="23",
        parent_provider_resource_id="12",
        title=None,
        state=None,
        body="comment acquired in repository A",
        last_checked_at_us=-1,
        provider_clock_scope="github-issue-comment-updated-at",
        acquisition_scope=old_scope,
    )
    assert adapter.admit(parent, source="import").status == "accepted"
    assert adapter.admit(child, source="import").status == "accepted"
    before = dict(
        db.execute(
            "SELECT * FROM issue_resources WHERE kind='issue-comment'"
        ).fetchone()
    )
    destination, binding = str(uuid.uuid4()), str(uuid.uuid4())
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'destination','{}')",
        (destination,),
    )
    db.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata) VALUES(?,?,?,'22','{}')",
        (binding, destination, context["service_instance_uuidv4"]),
    )
    destination_source = _source(db, context["service_instance_uuidv4"], destination)
    destination_context = {
        **context,
        "repository_uuidv4": destination,
        "repository_binding_id": binding,
    }
    moved = {
        **parent,
        **destination_context,
        "provider_issue_number": 7,
        "provider_updated_at_us": 20,
        "observed_at_us": 30,
        "parsed_at_us": 31,
        "acquisition_scope": {
            **destination_context,
            "source_registration_uuidv4": destination_source,
            "endpoint": "https://synthetic.invalid/repos/b/issues",
        },
    }
    assert adapter.admit(moved, source="import").status == "accepted"
    return before, child, destination_context, destination_source, old_source


def _receiver():
    db = sqlite3.connect(":memory:", autocommit=True)
    db.row_factory = sqlite3.Row
    db.executescript(schema_sql())
    db.execute(
        "INSERT INTO database_identity VALUES(1,?,?,?,?,?,'validated')",
        (FORMAT_ID, SCHEMA_VERSION, str(uuid.uuid4()), 0, DDL_SHA256),
    )
    return db


def test_transfer_retains_capture_when_original_source_has_no_destination(resources):
    adapter, context, _, _, _ = resources
    before, _, destination, _, original_source = _transfer(resources)
    after = dict(
        adapter.c.execute(
            "SELECT * FROM issue_resources WHERE kind='issue-comment'"
        ).fetchone()
    )
    for field in ("repository_uuidv4", "repository_binding_id"):
        assert after[field] == destination[field]
    assert after["provider_issue_number"] == 7
    for field in before.keys() - {
        "repository_uuidv4",
        "repository_binding_id",
        "provider_issue_number",
    }:
        assert after[field] == before[field], field
    assert (
        json.loads(after["acquisition_scope_json"])["repository_uuidv4"]
        == context["repository_uuidv4"]
    )
    assert not adapter.c.execute(
        "SELECT 1 FROM source_repositories m JOIN sources s USING(source_id) WHERE s.source_registration_uuidv4=? AND m.repository_uuidv4=?",
        (original_source, destination["repository_uuidv4"]),
    ).fetchone()
    validate_catalog(adapter.c)
    assert adapter.c.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize(
    "body", ["comment acquired in repository A", "edited comment acquired in B"]
)
def test_actual_destination_refresh_replaces_capture_truthfully(resources, body):
    adapter, _, _, _, _ = resources
    before, child, destination, source, _ = _transfer(resources)
    refresh = {
        **child,
        **destination,
        "provider_issue_number": 7,
        "body": body,
        "provider_updated_at_us": 40,
        "observed_at_us": 41,
        "parsed_at_us": 42,
        "acquisition_scope": {
            **destination,
            "source_registration_uuidv4": source,
            "endpoint": "https://synthetic.invalid/repos/b/issues/7/comments",
        },
    }
    refresh.pop("last_checked_at_us")
    revision, scope = adapter.capture_context(refresh["acquisition_scope"])
    assert adapter.admit(
        refresh, source="live", base_revision=revision, scope_context=scope
    ).status in {"accepted", "identical"}
    after = adapter.candidate_from_row(
        "issue_resources",
        adapter.c.execute(
            "SELECT * FROM issue_resources WHERE kind='issue-comment'"
        ).fetchone(),
    )
    assert after["body"] == body
    assert after["acquisition_scope"] == refresh["acquisition_scope"]
    assert after["observed_at_us"] == 41
    assert after["parsed_at_us"] == 42
    assert after["last_checked_at_us"] == 41
    assert after["provider_updated_at_us"] == 40
    assert before["acquisition_scope_json"] != json.dumps(after["acquisition_scope"])
    validate_catalog(adapter.c)


def test_transfer_exchange_retains_snapshot_without_exporting_other_repository(
    resources,
):
    adapter, context, _, _, _ = resources
    before, _, destination, _, original_source = _transfer(resources)
    old_unit = Graph(adapter.c).export(context["repository_uuidv4"])
    assert not any(
        record["table"] in {"issue_resources", "text_bodies"}
        for record in old_unit["records"]
    )
    unit = Graph(adapter.c).export(destination["repository_uuidv4"])
    assert sum(record["table"] == "issue_resources" for record in unit["records"]) == 2
    assert sum(record["table"] == "repositories" for record in unit["records"]) == 1
    target, onward = _receiver(), _receiver()
    try:
        assert receive(target, unit)["staged_records"] == 0
        assert not target.execute(
            "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
            (context["repository_uuidv4"],),
        ).fetchone()
        assert not target.execute(
            "SELECT 1 FROM sources WHERE source_registration_uuidv4=?",
            (original_source,),
        ).fetchone()
        child = target.execute(
            "SELECT * FROM issue_resources WHERE kind='issue-comment'"
        ).fetchone()
        assert child["acquisition_scope_json"] == before["acquisition_scope_json"]
        assert child["field_evidence_json"] == before["field_evidence_json"]
        assert (
            receive(onward, Graph(target).export(destination["repository_uuidv4"]))[
                "staged_records"
            ]
            == 0
        )
        assert (
            onward.execute(
                "SELECT acquisition_scope_json FROM issue_resources WHERE kind='issue-comment'"
            ).fetchone()[0]
            == before["acquisition_scope_json"]
        )
        for db in (target, onward):
            validate_catalog(db)
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        target.close()
        onward.close()


def test_historical_capture_cannot_certify_live_destination_observation(resources):
    adapter, _, _, _, _ = resources
    _, child, destination, _, _ = _transfer(resources)
    fabricated = {
        **child,
        **destination,
        "provider_issue_number": 7,
        "provider_updated_at_us": 40,
    }
    with pytest.raises(CatalogError):
        adapter.admit(fabricated, source="live")


def test_known_capture_binding_mismatch_rejected_by_sql(resources):
    adapter, context, _, _, _ = resources
    before, _, destination, _, _ = _transfer(resources)
    wrong = json.loads(before["acquisition_scope_json"])
    wrong["repository_binding_id"] = destination["repository_binding_id"]
    assert wrong["repository_uuidv4"] == context["repository_uuidv4"]
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE issue_resources SET acquisition_scope_json=? WHERE kind='issue-comment'",
            (json.dumps(wrong),),
        )


@pytest.mark.parametrize("mismatch", ["source", "service", "noncanonical"])
def test_detached_capture_keeps_typed_validation(resources, mismatch):
    adapter, _, _, _, _ = resources
    before, _, _, destination_source, _ = _transfer(resources)
    wrong = json.loads(before["acquisition_scope_json"])
    if mismatch == "source":
        # Both contexts are locally registered: a B-only Source must never be
        # substituted into the original A capture.
        wrong["source_registration_uuidv4"] = destination_source
    elif mismatch == "service":
        wrong["service_instance_uuidv4"] = str(uuid.uuid4())
    else:
        wrong["repository_uuidv4"] = "unregistered-and-not-a-uuid"
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE issue_resources SET acquisition_scope_json=? WHERE kind='issue-comment'",
            (json.dumps(wrong),),
        )


@pytest.mark.parametrize("mismatch", ["capture-source", "absent-path", "alias-path"])
def test_transferred_field_evidence_cannot_fabricate_capture_or_extra_fields(
    resources, mismatch
):
    adapter, _, _, _, _ = resources
    before, _, _, destination_source, _ = _transfer(resources)
    evidence = json.loads(before["field_evidence_json"])
    entry = dict(evidence['["body"]'])
    if mismatch == "capture-source":
        entry["acquisition_scope"] = {
            **entry["acquisition_scope"],
            "source_registration_uuidv4": destination_source,
        }
        evidence['["body"]'] = entry
    elif mismatch == "absent-path":
        evidence['["metadata","never-observed"]'] = entry
    else:
        # Alternate encodings cannot create a second slot for one semantic field.
        evidence['["\\u0062ody"]'] = entry
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE issue_resources SET field_evidence_json=? WHERE kind='issue-comment'",
            (json.dumps(evidence),),
        )
