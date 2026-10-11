"""Closed typed JSON guards, capture ownership and no retired authority."""

import base64
import copy
import json
import sqlite3
import uuid
from importlib.resources import files

import pytest

from repo_catalog.adapters.sqlite.json_contracts import (
    JsonContractError,
    MissingJsonDependencies,
    guard_sql,
    inventory,
    reference_dependencies,
    validate_catalog,
    validate_record,
)
from tests.support.domain_facts import (
    SERVICE,
    TIME_US,
    admit_document,
    admit_pr,
    candidate,
    collection,
    fresh_domain_db,
    insert,
    repository_uuid,
)


@pytest.fixture
def facts():
    db = fresh_domain_db()
    for number in (1, 2):
        admit_pr(db, number, state="open")
        admit_document(db, number, body="domain text")
    yield db
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    db.close()


def record(provenance):
    return {
        "repository_uuidv4": repository_uuid(1),
        "provenance_json": json.dumps(provenance),
    }


def insert_name(db, provenance):
    insert(
        db,
        "repository_names",
        repository_uuidv4=repository_uuid(1),
        name=str(uuid.uuid4()),
        provenance_json=json.dumps(provenance),
    )


def current_row(db):
    cursor = db.execute("SELECT * FROM document_state WHERE change_request_id='pr1'")
    return dict(
        zip(
            (column[0] for column in cursor.description), cursor.fetchone(), strict=True
        )
    )


def test_registry_is_exhaustive_and_packaged_guards_match(facts):
    entries = inventory(facts)
    assert {e["category"] for e in entries} >= {
        "authored",
        "operational",
        "current-field-evidence",
        "current-members",
    }
    assert not {e["category"] for e in entries} & {"definition", "fact-manifest"}
    assert (
        files("repo_catalog").joinpath("resources/json_contracts.sql").read_text()
        == guard_sql()
    )
    assert validate_catalog(facts)["json_columns"] == len(entries)
    facts.execute("CREATE TABLE unclassified(body TEXT CHECK(json_valid(body)))")
    with pytest.raises(JsonContractError, match="Unclassified"):
        inventory(facts)
    facts.execute("DROP TABLE unclassified")
    facts.execute("CREATE TABLE no_check(provenance_json TEXT)")
    with pytest.raises(JsonContractError, match="Unclassified"):
        inventory(facts)
    facts.execute("DROP TABLE no_check")


@pytest.mark.parametrize(
    "malformed",
    [1, [], "UPPERCASE", "00000000-0000-0000-0000-000000000000", SERVICE + "\0"],
)
def test_nested_reference_requires_canonical_typed_uuid(facts, malformed):
    provenance = {"nested": [{"repository_uuidv4": malformed}]}
    with pytest.raises(JsonContractError):
        validate_record(facts, "repository_names", record(provenance))
    with pytest.raises(sqlite3.IntegrityError):
        insert_name(facts, provenance)


@pytest.mark.parametrize(
    "field",
    [
        "repository_uuidv4",
        "repository_binding_id",
        "change_request_id",
        "service_instance_uuidv4",
    ],
)
def test_capture_references_reject_foreign_owner_in_python_and_sql(facts, field):
    row = current_row(facts)
    scope = json.loads(row["acquisition_scope_json"])
    foreign = candidate(2)["acquisition_scope"]
    if field == "service_instance_uuidv4":
        foreign[field] = "00000000-0000-4000-8000-000000000102"
    scope[field] = foreign[field]
    row["acquisition_scope_json"] = json.dumps(scope)
    with pytest.raises(JsonContractError):
        validate_record(facts, "document_state", row)
    with pytest.raises(sqlite3.IntegrityError):
        facts.execute(
            "UPDATE document_state SET acquisition_scope_json=? WHERE change_request_id='pr1'",
            (row["acquisition_scope_json"],),
        )


@pytest.mark.parametrize(
    "key",
    [
        "parsed_result_uuidv4",
        "parsed_result_uuidv4s",
        "parser_profile_uuidv4",
        "parser_profile_verification_uuidv4",
        "selection_decision_uuidv4",
        "selection_predecessors",
        "fetch_occurrence_uuidv4",
        "fetch_occurrence_uuidv4s",
        "source_input_uuidv4",
        "payload",
        "unregistered_uuidv4",
        "text_body_id",
        "git_object_id",
        "source_id",
        "resume_scope_id",
        "stable_scope",
    ],
)
def test_retired_unknown_or_local_references_cannot_bypass_authored_guards(facts, key):
    provenance = {"nested": [{key: str(uuid.uuid4())}]}
    with pytest.raises(JsonContractError):
        validate_record(facts, "repository_names", record(provenance))
    with pytest.raises(sqlite3.IntegrityError):
        insert_name(facts, provenance)


@pytest.mark.parametrize(
    "key",
    [
        "parsed_result_uuidv4",
        "parser_profile_uuidv4",
        "fetch_occurrence_uuidv4",
        "payload",
        "selection_predecessors",
    ],
)
def test_current_capture_cannot_require_transport_or_parser_authority(facts, key):
    row = current_row(facts)
    scope = json.loads(row["acquisition_scope_json"])
    scope["nested"] = [{key: None}]
    row["acquisition_scope_json"] = json.dumps(scope)
    with pytest.raises(JsonContractError):
        validate_record(facts, "document_state", row)
    with pytest.raises(sqlite3.IntegrityError):
        facts.execute(
            "UPDATE document_state SET acquisition_scope_json=? WHERE change_request_id='pr1'",
            (row["acquisition_scope_json"],),
        )


def test_missing_multiple_targets_and_duplicate_reference_set_semantics(facts):
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    provenance = {
        "items": [
            {"repository_uuidv4": first},
            {"repository_uuidv4": second},
            {"repository_uuidv4": first},
        ]
    }
    with pytest.raises(MissingJsonDependencies) as cause:
        validate_record(facts, "repository_names", record(provenance))
    dependencies = cause.value.dependencies
    assert {item["values"] for item in dependencies} == {(first,), (second,)}
    assert len(dependencies) == 2
    assert (
        validate_record(
            facts, "repository_names", record(provenance), allow_missing=True
        )
        == dependencies
    )
    assert len(reference_dependencies("repository_names", record(provenance))) == 2


@pytest.mark.parametrize(
    "ambiguous",
    [
        '{"change_request_id":"pr1","change_request_id":"pr2"}',
        '{"nested":{"repository_uuidv4":null,"repository_uuidv4":null}}',
        '{"nested":[{"name":1,"name":2}]}',
    ],
)
def test_duplicate_json_keys_are_rejected_by_python_and_sql(facts, ambiguous):
    data = {"repository_uuidv4": repository_uuid(1), "provenance_json": ambiguous}
    with pytest.raises(JsonContractError):
        validate_record(facts, "repository_names", data)
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            facts,
            "repository_names",
            repository_uuidv4=repository_uuid(1),
            name="duplicate",
            provenance_json=ambiguous,
        )


def test_closed_modeled_metadata_rejects_duplicate_named_values(facts):
    row = current_row(facts)
    row["metadata"] = '{"node_id":"first","node_id":"second"}'
    with pytest.raises(JsonContractError):
        validate_record(facts, "document_state", row)
    with pytest.raises(sqlite3.IntegrityError):
        facts.execute(
            "UPDATE document_state SET metadata=? WHERE change_request_id='pr1'",
            (row["metadata"],),
        )


def test_same_keys_and_array_indices_in_distinct_containers_are_valid(facts):
    provenance = {
        "a": {"name": "A"},
        "b": {"name": "B"},
        "c": [{"name": "C"}, {"name": "D"}],
    }
    assert validate_record(facts, "repository_names", record(provenance)) == []
    insert_name(facts, provenance)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-path",
        "noncanonical-path",
        "absent-path",
        "missing-origin",
        "extra-origin",
        "foreign-parent",
        "foreign-binding",
        "null-observed",
        "float-observed",
        "overflow-time",
        "empty-parser",
        "nul-parser",
        "wrong-clock",
        "producer-mismatch",
    ],
)
def test_current_field_evidence_is_closed_and_owned(facts, mutation):
    row = current_row(facts)
    evidence = json.loads(row["field_evidence_json"])
    body = copy.deepcopy(evidence['["body"]'])
    if mutation == "unknown-path":
        evidence['["opaque_response"]'] = body
    elif mutation == "noncanonical-path":
        evidence['[ "body" ]'] = evidence.pop('["body"]')
    elif mutation == "absent-path":
        evidence['["metadata","absent"]'] = body
    elif mutation == "missing-origin":
        del evidence['["body"]']["parser_version"]
    elif mutation == "extra-origin":
        evidence['["body"]']["response"] = {"body": "unretained"}
    elif mutation == "foreign-parent":
        evidence['["body"]']["acquisition_scope"]["change_request_id"] = "pr2"
    elif mutation == "foreign-binding":
        evidence['["body"]']["acquisition_scope"]["repository_binding_id"] = "binding-2"
    elif mutation == "null-observed":
        evidence['["body"]']["observed_at_us"] = None
    elif mutation == "float-observed":
        evidence['["body"]']["observed_at_us"] = 1.0
    elif mutation == "overflow-time":
        evidence['["body"]']["parsed_at_us"] = 2**63
    elif mutation == "empty-parser":
        evidence['["body"]']["parser_module"] = ""
    elif mutation == "nul-parser":
        evidence['["body"]']["parser_version"] = "1\0"
    elif mutation == "wrong-clock":
        evidence['["body"]']["provider_clock_scope"] = "github-issue-updated-at"
    elif mutation == "producer-mismatch":
        evidence['["body"]']["acquisition_scope"]["parser_version"] = "other"
    row["field_evidence_json"] = json.dumps(evidence)
    with pytest.raises(JsonContractError):
        validate_record(facts, "document_state", row)
    with pytest.raises(sqlite3.IntegrityError):
        facts.execute(
            "UPDATE document_state SET field_evidence_json=? WHERE change_request_id='pr1'",
            (row["field_evidence_json"],),
        )


def member():
    return {
        "family": "document",
        "change_request_id": "pr1",
        "kind": "pr-body",
        "provider_change_request_document_id": "123",
        "state_digest": "a" * 64,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-family",
        "wrong-kind",
        "extra",
        "missing",
        "uppercase",
        "nul-digest",
        "short-digest",
        "null-id",
        "node-id",
        "duplicate",
        "duplicate-reordered",
    ],
)
def test_typed_members_have_closed_shape_and_canonical_identity(facts, mutation):
    item = member()
    members = [item]
    if mutation == "unknown-family":
        item["family"] = "bundle"
    elif mutation == "wrong-kind":
        item["kind"] = "review"
    elif mutation == "extra":
        item["payload"] = {}
    elif mutation == "missing":
        del item["change_request_id"]
    elif mutation == "uppercase":
        item["state_digest"] = "A" * 64
    elif mutation == "nul-digest":
        item["state_digest"] = "a" * 62 + "\0a"
    elif mutation == "short-digest":
        item["state_digest"] = "a" * 63
    elif mutation == "null-id":
        item["provider_change_request_document_id"] = None
    elif mutation == "node-id":
        item["provider_change_request_document_id"] = "NODE_only"
    elif mutation == "duplicate":
        members.append(dict(item))
    elif mutation == "duplicate-reordered":
        members.append(dict(reversed(list(item.items()))))
    collection(facts, identity="members")
    row = {"members": json.dumps(members)}
    with pytest.raises(JsonContractError):
        validate_record(facts, "current_collection_pages", row)
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            facts,
            "current_collection_pages",
            fetch_collection_id="members",
            ordinal=0,
            observed_at_us=TIME_US,
            has_next=0,
            status=200,
            parser_module=__name__,
            parser_version="1",
            **row,
        )


def test_stable_members_attest_prior_values_without_current_digest_rehash(facts):
    collection(facts, identity="members")
    insert(
        facts,
        "current_collection_pages",
        fetch_collection_id="members",
        ordinal=0,
        observed_at_us=100,
        has_next=0,
        members=json.dumps([member()]),
        status=200,
        parser_module=__name__,
        parser_version="1",
    )
    assert (
        admit_document(
            facts, body="new text", clock=TIME_US + 1, observed_at_us=TIME_US + 1
        ).status
        == "accepted"
    )
    assert validate_catalog(facts)["records_checked"] > 0
    assert facts.execute("SELECT members FROM current_collection_pages").fetchone()[
        0
    ] == json.dumps([member()])
    assert facts.execute("SELECT count(*) FROM document_state").fetchone()[0] == 2


@pytest.mark.parametrize("provider_id", ["123", "00123"])
def test_document_receipts_preserve_exact_provider_spelling(facts, provider_id):
    assert admit_document(facts, resource=provider_id, body="domain text").status in {
        "accepted",
        "identical",
    }
    collection(facts, identity="spelling")
    attested = {**member(), "provider_change_request_document_id": provider_id}
    row = {"members": json.dumps([attested])}
    assert validate_record(facts, "current_collection_pages", row) == []
    insert(
        facts,
        "current_collection_pages",
        fetch_collection_id="spelling",
        ordinal=0,
        observed_at_us=TIME_US,
        has_next=0,
        status=200,
        parser_module=__name__,
        parser_version="1",
        **row,
    )
    assert (
        json.loads(
            facts.execute("SELECT members FROM current_collection_pages").fetchone()[0]
        )[0]["provider_change_request_document_id"]
        == provider_id
    )


@pytest.mark.parametrize(
    "bad",
    [
        "name",
        "name_b64",
        "oid",
        "peeled",
        "type",
        "pr-number",
        "oid-nul",
        "peeled-nul",
        "expected-nul",
    ],
)
def test_captured_git_refs_validate_interpreted_fields_before_objects_exist(facts, bad):
    ref = {
        "name": "refs/heads/main",
        "name_b64": base64.b64encode(b"refs/heads/main").decode(),
        "oid": "a" * 40,
        "type": "commit",
        "peeled": None,
    }
    good = {
        "repository_uuidv4": repository_uuid(1),
        "object_format": "sha1",
        "roots_manifest": json.dumps([ref]),
    }
    assert validate_record(facts, "git_acquisitions", good) == []
    if bad == "pr-number":
        ref.update(role="head", expected=ref["oid"], number=False)
    elif bad == "expected-nul":
        ref.update(role="head", expected="a" * 38 + "\0a", number=1)
    elif bad.endswith("-nul"):
        ref[bad.removesuffix("-nul")] = "a" * 38 + "\0a"
    elif bad == "name_b64":
        ref[bad] = "!!!!"
    elif bad == "type":
        ref[bad] = "alien"
    elif bad == "name":
        ref[bad] = None
    else:
        ref[bad] = "A" * 40
    malformed = {**good, "roots_manifest": json.dumps([ref])}
    with pytest.raises(JsonContractError):
        validate_record(facts, "git_acquisitions", malformed)
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            facts,
            "git_acquisitions",
            git_acquisition_id="bad",
            repository_uuidv4=repository_uuid(1),
            object_format="sha1",
            kind="git",
            request="{}",
            roots_manifest=malformed["roots_manifest"],
        )


@pytest.mark.parametrize(
    "details",
    [
        {"expected_roles": []},
        {"expected_roles": {"head": "not-a-git-oid"}},
        {"expected_roles": {"head": "A" * 40}},
        {"expected_roles": {"unknown": "a" * 40}},
        {"api_head_base_stable": "yes"},
        {"code_inputs_complete": 1},
        {"missing_roles": [None]},
        {"provider_limits": {"commits": True}},
        {"merge": {"merge": "not-an-oid"}},
    ],
)
def test_interpreted_code_details_reject_malformed_git_declarations(facts, details):
    row = {
        "repository_uuidv4": repository_uuid(1),
        "object_format": "sha1",
        "details_json": json.dumps(details),
    }
    with pytest.raises(JsonContractError):
        validate_record(facts, "code_assessments", row)
    with pytest.raises(sqlite3.IntegrityError):
        insert(
            facts,
            "code_assessments",
            code_assessment_id="bad",
            change_request_id="pr1",
            state="partial",
            parser_module=__name__,
            parser_version="1",
            **row,
        )


def test_valid_code_expectations_do_not_require_git_or_old_pr_values(facts):
    details = {
        "api_head_base_stable": False,
        "code_inputs_complete": False,
        "expected_roles": {"head": "a" * 40, "review-target:" + "b" * 40: "b" * 40},
        "missing_roles": ["head"],
        "provider_limits": {"commits": 250, "files": 3000},
        "merge": {"merge": None, "test-merge": "c" * 40},
    }
    assert (
        validate_record(
            facts,
            "code_assessments",
            {
                "repository_uuidv4": repository_uuid(1),
                "object_format": "sha1",
                "details_json": json.dumps(details),
            },
        )
        == []
    )
    assert facts.execute("SELECT count(*) FROM git_acquisitions").fetchone()[0] == 0


@pytest.mark.parametrize(
    "metadata",
    [
        {"provider_response": {"body": "whole response", "headers": {}}},
        {"payload": {"representation": "decoded_api", "sha256": "a" * 64}},
        {"nested": {"parsed_result_uuidv4": str(uuid.uuid4())}},
    ],
)
def test_provider_metadata_does_not_hide_response_or_authority(facts, metadata):
    row = current_row(facts)
    row["metadata"] = json.dumps(metadata)
    with pytest.raises(JsonContractError):
        validate_record(facts, "document_state", row)
    with pytest.raises(sqlite3.IntegrityError):
        facts.execute(
            "UPDATE document_state SET metadata=? WHERE change_request_id='pr1'",
            (row["metadata"],),
        )
