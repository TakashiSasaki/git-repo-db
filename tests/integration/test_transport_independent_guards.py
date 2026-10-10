"""Current writes prepare and validate without legacy transport/parser stores."""

import copy
import json
import re
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.schema import (
    DDL_SHA256,
    FORMAT_ID,
    SCHEMA_VERSION,
    schema_sql,
)
from repo_catalog.domain.models import CatalogError

LEGACY_STORES = (
    "parser_profiles",
    "parser_profile_capabilities",
    "parser_profile_verifications",
    "parsed_results",
    "fact_selection_decisions",
    "fetch_occurrences",
    "source_input_observations",
    "payloads",
    "stored_bytes",
)


@pytest.fixture
def detached_catalog():
    db = sqlite3.connect(":memory:", autocommit=True)
    db.row_factory = sqlite3.Row
    db.executescript(schema_sql())
    db.execute(
        "INSERT INTO database_identity VALUES(1,?,?,?,?,?,'validated')",
        (FORMAT_ID, SCHEMA_VERSION, str(uuid.uuid4()), 0, DDL_SHA256),
    )
    owners = []
    for number in (1, 2):
        service, repository, binding, request = (str(uuid.uuid4()) for _ in range(4))
        db.execute(
            "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) "
            "VALUES(?,'github','synthetic','{}')",
            (service,),
        )
        db.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) "
            "VALUES(?,'synthetic','{}')",
            (repository,),
        )
        db.execute(
            "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,"
            "service_instance_uuidv4,provider_repository_id,metadata) VALUES(?,?,?,?,'{}')",
            (binding, repository, service, str(number)),
        )
        db.execute(
            "INSERT INTO change_requests VALUES(?,?,?,'pull_request',?)",
            (request, repository, binding, number),
        )
        owners.append(
            {
                "service_instance_uuidv4": service,
                "repository_uuidv4": repository,
                "repository_binding_id": binding,
                "change_request_id": request,
            }
        )
    # Only empty legacy tables are removed. Foreign keys remain enabled, and
    # actual current writes must prepare their triggers against the reduced DB.
    existing = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
    }
    for table in LEGACY_STORES:
        if table in existing:
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
            db.execute(f"DROP TABLE {table}")
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    yield db, owners
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()


def candidate(owner, kind):
    context = {key: value for key, value in owner.items() if key != "change_request_id"}
    row = {
        **context,
        "kind": kind,
        "body": "exact domain text\x00suffix",
        "observed_at_us": 10,
        "parsed_at_us": 11,
        "parser_module": __name__,
        "parser_version": "1",
        "acquisition_scope": {**context, "endpoint": "synthetic-" + kind},
    }
    if kind == "issue":
        row.update(
            provider_resource_id="12",
            provider_issue_number=2,
            title="title",
            state="open",
            provider_updated_at_us=10,
            provider_clock_scope="github-issue-updated-at",
        )
    else:
        row.update(
            change_request_id=owner["change_request_id"],
            provider_change_request_document_id="12",
            state="COMMENTED",
        )
        row["acquisition_scope"]["change_request_id"] = owner["change_request_id"]
    return row


def test_current_json_triggers_have_no_legacy_store_dependencies(detached_catalog):
    db, _ = detached_catalog
    triggers = db.execute(
        "SELECT name,sql FROM sqlite_schema WHERE type='trigger' "
        "AND (name LIKE 'json_issue_resources_%' OR name LIKE 'json_review_resources_%')"
    ).fetchall()
    assert {trigger["name"] for trigger in triggers} == {
        f"json_{table}_{column}_{operation}"
        for table in ("issue_resources", "review_resources")
        for column in ("metadata", "acquisition_scope_json", "field_evidence_json")
        for operation in ("insert", "update")
    }
    for trigger in triggers:
        for table in LEGACY_STORES:
            assert not re.search(r"\b" + table + r"\b", trigger["sql"]), (
                trigger["name"],
                table,
            )
    present = {row[0] for row in db.execute("SELECT name FROM sqlite_schema")}
    assert not present.intersection(LEGACY_STORES)


@pytest.mark.parametrize("kind", ["issue", "review"])
def test_current_admission_and_conflicts_work_with_legacy_stores_absent(
    detached_catalog, kind
):
    db, owners = detached_catalog
    resources = CurrentResources(db)
    first = candidate(owners[0], kind)
    assert resources.admit(first, source="import").status == "accepted"
    table = "issue_resources" if kind == "issue" else "review_resources"
    row = resources.candidate_from_row(
        table, db.execute(f"SELECT * FROM {table}").fetchone()
    )
    assert row["body"] == first["body"]
    assert row["field_evidence"]['["body"]']["parser_module"] == __name__
    assert row["field_evidence"]['["body"]']["parser_version"] == "1"
    assert (
        resources.admit(
            {**first, "body": "unordered alternative", "parser_version": "999"},
            source="import",
        ).status
        == "conflict"
    )
    assert db.execute(f"SELECT count(*) FROM eligible_{table}").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 1
    assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


@pytest.mark.parametrize("kind", ["issue", "review"])
@pytest.mark.parametrize("location", ["acquisition_scope_json", "field_evidence_json"])
@pytest.mark.parametrize(
    "extra",
    [
        {"parser_profile_uuidv4": "00000000-0000-4000-8000-000000000001"},
        {"parsed_result_uuidv4": "00000000-0000-4000-8000-000000000001"},
        {"fetch_occurrence_uuidv4": "00000000-0000-4000-8000-000000000001"},
        {"payload": {"representation": "decoded_api", "sha256": "0" * 64}},
        {"unrecognized_owner_uuidv4": "00000000-0000-4000-8000-000000000001"},
        "foreign_binding",
    ],
)
def test_current_guards_reject_legacy_references_and_false_capture_owners(
    detached_catalog, kind, location, extra
):
    db, owners = detached_catalog
    resources = CurrentResources(db)
    first = candidate(owners[0], kind)
    assert resources.admit(first, source="import").status == "accepted"
    table = "issue_resources" if kind == "issue" else "review_resources"
    stored = db.execute(f"SELECT * FROM {table}").fetchone()
    value = json.loads(stored[location])
    scope = (
        value
        if location == "acquisition_scope_json"
        else value['["body"]']["acquisition_scope"]
    )
    extra = (
        {"repository_binding_id": owners[1]["repository_binding_id"]}
        if extra == "foreign_binding"
        else extra
    )
    scope.update(extra)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(f"UPDATE {table} SET {location}=?", (json.dumps(value),))
    invalid = copy.deepcopy(first)
    if location == "acquisition_scope_json":
        invalid["acquisition_scope"].update(extra)
    else:
        invalid["field_evidence"] = value
    with pytest.raises(CatalogError):
        resources.admit(invalid, source="import")
    assert (
        stored[location] == db.execute(f"SELECT {location} FROM {table}").fetchone()[0]
    )
