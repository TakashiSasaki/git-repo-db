"""Current PR/text/thread acceptance has typed owners and independent evidence."""

import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.json_contracts import (
    JsonContractError,
    guard_sql,
    validate_catalog,
    validate_record,
)
from repo_catalog.adapters.sqlite.schema import (
    DDL_SHA256,
    FORMAT_ID,
    SCHEMA_VERSION,
    schema_sql,
)
from repo_catalog.domain.models import CatalogError


@pytest.fixture
def api():
    db = sqlite3.connect(":memory:", autocommit=True)
    db.row_factory = sqlite3.Row
    db.executescript(schema_sql())
    db.execute(
        "INSERT INTO database_identity VALUES(1,?,?,?,?,?,'validated')",
        (FORMAT_ID, SCHEMA_VERSION, str(uuid.uuid4()), 0, DDL_SHA256),
    )
    service, repo, binding, change = [str(uuid.uuid4()) for _ in range(4)]
    db.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','synthetic','{}')",
        (service,),
    )
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'synthetic','{}')",
        (repo,),
    )
    db.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,metadata) VALUES(?,?,?,'{}')",
        (binding, repo, service),
    )
    db.execute(
        "INSERT INTO change_requests VALUES(?,?,?,'pull_request',1)",
        (change, repo, binding),
    )
    context = {
        "repository_uuidv4": repo,
        "repository_binding_id": binding,
        "service_instance_uuidv4": service,
        "change_request_id": change,
    }
    yield CurrentApiState(db), context
    db.close()


def candidate(api, *, kind="change-request", clock=10, **fields):
    _, context = api
    result = {
        **context,
        "kind": kind,
        "provider_resource_id": "12",
        "observed_at_us": 100,
        "parsed_at_us": 101,
        "parser_module": "synthetic.parser",
        "parser_version": "1",
        "provider_updated_at_us": clock,
        "provider_clock_scope": "github-pr-updated-at",
        "acquisition_scope": {**context, "endpoint": "pulls/1"},
        **fields,
    }
    if kind in {"pr-title", "pr-body"}:
        result.pop("provider_resource_id")
        result["provider_change_request_document_id"] = "12"
    elif kind == "review-thread":
        result.update(
            provider_resource_id="opaque-thread-node",
            provider_updated_at_us=None,
            provider_clock_scope=None,
        )
    return result


def current(adapter, table):
    return adapter.candidate_from_row(
        table, adapter.c.execute("SELECT * FROM " + table).fetchone()
    )


def test_sparse_api_update_preserves_exact_origin_and_older_fill(api):
    adapter, _ = api
    first = candidate(api, state="open", draft=False, metadata={"mergeable": None})
    assert (
        adapter.admit("change_request_state", first, source="import").status
        == "accepted"
    )
    newer = candidate(api, clock=20, state="closed", parser_version="2")
    assert (
        adapter.admit("change_request_state", newer, source="import").status
        == "accepted"
    )
    older = candidate(api, clock=15, locked=True)
    assert (
        adapter.admit("change_request_state", older, source="import").status
        == "accepted"
    )
    row = current(adapter, "change_request_state")
    assert (row["state"], row["draft"], row["locked"]) == ("closed", 0, 1)
    assert row["field_evidence"]['["state"]']["parser_version"] == "2"
    assert row["field_evidence"]['["draft"]']["parser_version"] == "1"
    assert row["field_evidence"]['["locked"]']["provider_updated_at_us"] == 15
    assert validate_catalog(adapter.c)["records_checked"] > 0


def test_pr_metadata_conflict_preserves_independently_valid_documents(api):
    adapter, _ = api
    adapter.admit("change_request_state", candidate(api, state="open"), source="import")
    adapter.admit(
        "document_state",
        candidate(api, kind="pr-body", body="exact\nbody\0"),
        source="import",
    )
    assert (
        adapter.admit(
            "change_request_state", candidate(api, state="closed"), source="import"
        ).status
        == "conflict"
    )
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM eligible_change_request_state"
        ).fetchone()[0]
        == 0
    )
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_document_state").fetchone()[0]
        == 1
    )
    assert (
        adapter.admit(
            "change_request_state",
            candidate(api, clock=20, state="closed"),
            source="import",
        ).status
        == "accepted"
    )
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_document_state").fetchone()[0]
        == 1
    )
    assert current(adapter, "document_state")["body"] == "exact\nbody\0"


def test_missing_document_body_does_not_replace_known_body(api):
    adapter, _ = api
    adapter.admit(
        "document_state", candidate(api, kind="pr-body", body=""), source="import"
    )
    adapter.admit(
        "document_state",
        candidate(api, kind="pr-body", clock=20, author="new"),
        source="import",
    )
    row = current(adapter, "document_state")
    assert row["body"] == "" and row["body_status"] == "present"
    assert row["field_evidence"]['["body"]']["provider_updated_at_us"] == 10
    adapter.admit(
        "document_state",
        candidate(api, kind="pr-body", clock=30, body=None),
        source="import",
    )
    assert current(adapter, "document_state")["body_status"] == "provider-null"


def test_unclocked_thread_requires_live_fence_and_import_never_checks(api):
    adapter, _ = api
    first = candidate(api, kind="review-thread", resolved=False, outdated=False)
    adapter.admit("review_thread_state", first, source="import")
    update = candidate(api, kind="review-thread", resolved=True)
    assert (
        adapter.admit("review_thread_state", update, source="import").status
        == "conflict"
    )
    revision, scope = adapter.capture_context(update["acquisition_scope"])
    assert (
        adapter.admit(
            "review_thread_state", update, base_revision=revision, scope_context=scope
        ).status
        == "accepted"
    )
    assert current(adapter, "review_thread_state")["last_checked_at_us"] == 100
    imported = candidate(
        api, kind="review-thread", resolved=True, last_checked_at_us=999
    )
    adapter.admit("review_thread_state", imported, source="import")
    assert current(adapter, "review_thread_state")["last_checked_at_us"] == 100


def test_ten_thousand_updates_retain_one_current_value_and_no_edit_store(api):
    adapter, _ = api
    for i in range(10000):
        adapter.admit(
            "document_state",
            candidate(api, kind="pr-title", clock=i, body=str(i)),
            source="import",
        )
    assert adapter.c.execute("SELECT count(*) FROM document_state").fetchone()[0] == 1
    assert adapter.c.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] == 0
    assert current(adapter, "document_state")["body"] == "9999"
    assert adapter.c.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 10000
    tables = {
        row[0]
        for row in adapter.c.execute(
            "SELECT name FROM sqlite_schema WHERE type='table'"
        )
    }
    assert not tables & {
        "parsed_results",
        "document_observations",
        "change_request_observations",
        "fetch_occurrences",
        "parser_profiles",
    }


def test_valid_resource_and_empty_terminal_receipt_need_no_operational_rows(api):
    adapter, context = api
    assert (
        adapter.admit(
            "change_request_state", candidate(api, state="open"), source="import"
        ).status
        == "accepted"
    )
    adapter.c.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,scope_json) VALUES('collection',?,?, 'comments',?)",
        (
            context["repository_uuidv4"],
            context["change_request_id"],
            json.dumps({**context, "endpoint": "comments"}),
        ),
    )
    proof = CurrentCollectionProof(adapter.c)
    assert proof.evidence("collection") is None
    proof.page(
        "collection", 0, 100, None, [], parser_module="synthetic", parser_version="1"
    )
    assert proof.evidence("collection")["terminal"] is True
    assert adapter.c.execute("SELECT count(*) FROM resume_scopes").fetchone()[0] == 0
    assert adapter.c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    assert "next_cursor" not in dict(
        adapter.c.execute("SELECT * FROM current_collection_pages").fetchone()
    )
    assert adapter.c.execute("PRAGMA foreign_key_check").fetchall() == []


def test_generated_json_contract_is_exact(api):
    from importlib.resources import files

    assert (
        files("repo_catalog").joinpath("resources/json_contracts.sql").read_text()
        == guard_sql()
    )
    assert api[0].c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_source_roster_fenced_sparse_values_and_partial_no_absence_deletion(api):
    adapter, context = api
    source_registration = str(uuid.uuid4())
    adapter.c.execute(
        "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('source',?,?,'github_inventory','synthetic','{}')",
        (source_registration, context["service_instance_uuidv4"]),
    )
    other = str(uuid.uuid4())
    adapter.c.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'R2','{}')",
        (other,),
    )
    scope = {
        "source_registration_uuidv4": source_registration,
        "service_instance_uuidv4": context["service_instance_uuidv4"],
        "endpoint": "inventory",
        "principal_ref": "synthetic",
    }

    def confirm(repo, observed, name=None, metadata=None, fenced=False, version="1"):
        revision = (
            adapter._one(
                "SELECT db_instance_id,local_revision FROM database_identity WHERE singleton=1"
            )
            if fenced
            else None
        )
        return adapter.confirm_source_repository(
            "source",
            repo,
            observed_at_us=observed,
            parsed_at_us=observed + 1,
            scope=scope,
            parser_module="synthetic",
            parser_version=version,
            name=name,
            metadata=metadata,
            base_revision=revision,
            scope_context=scope if fenced else None,
        )

    assert (
        confirm(context["repository_uuidv4"], 100, "R1", {"private": False})
        == "accepted"
    )
    assert confirm(other, 100, "R2") == "accepted"
    adapter.assess_source_inventory(
        "source",
        scope=scope,
        observed_at_us=100,
        state="complete",
        members=[context["repository_uuidv4"], other],
        terminal=True,
        parser_module="synthetic",
        parser_version="1",
    )
    assert confirm(context["repository_uuidv4"], 200, "R1 renamed") == "conflict"
    assert (
        confirm(
            context["repository_uuidv4"], 200, "R1 renamed", fenced=True, version="2"
        )
        == "accepted"
    )
    adapter.assess_source_inventory(
        "source",
        scope=scope,
        observed_at_us=200,
        state="partial",
        members=[context["repository_uuidv4"]],
        terminal=False,
        parser_module="synthetic",
        parser_version="2",
    )
    assert (
        adapter.c.execute("SELECT count(*) FROM source_repositories").fetchone()[0] == 2
    )
    row = adapter._one(
        "SELECT * FROM source_repositories WHERE source_id='source' AND repository_uuidv4=?",
        (context["repository_uuidv4"],),
    )
    evidence = json.loads(row["field_evidence_json"])
    assert row["name"] == "R1 renamed"
    assert evidence['["name"]']["parser_version"] == "2"
    assert evidence['["metadata","private"]']["parser_version"] == "1"
    assert validate_catalog(adapter.c)["records_checked"] > 0


def test_source_evidence_accepts_explicit_null_and_rejects_missing_payload(api):
    adapter, context = api
    registration = str(uuid.uuid4())
    adapter.c.execute(
        "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('source-null',?,?,'manual_git','synthetic','{}')",
        (registration, context["service_instance_uuidv4"]),
    )
    scope = {
        "source_registration_uuidv4": registration,
        "service_instance_uuidv4": context["service_instance_uuidv4"],
        "endpoint": "inventory",
    }

    def proof():
        return {
            "provider_updated_at_us": None,
            "provider_clock_scope": None,
            "observed_at_us": 100,
            "parsed_at_us": 101,
            "parser_module": "synthetic",
            "parser_version": "1",
            "acquisition_scope": scope,
        }

    assert (
        adapter.confirm_source_repository(
            "source-null",
            context["repository_uuidv4"],
            observed_at_us=100,
            parsed_at_us=101,
            scope=scope,
            parser_module="synthetic",
            parser_version="1",
            field_evidence={'["name"]': proof()},
        )
        == "accepted"
    )
    row = adapter._one(
        "SELECT * FROM source_repositories WHERE source_id='source-null'"
    )
    assert row["name"] is None
    assert adapter.admit_source_row(row) == "accepted"
    assert json.loads(row["field_evidence_json"])['["name"]']["observed_at_us"] == 100

    assert (
        adapter.confirm_source_repository(
            "source-null",
            context["repository_uuidv4"],
            observed_at_us=200,
            parsed_at_us=201,
            scope=scope,
            parser_module="synthetic",
            parser_version="1",
            metadata={},
            field_evidence={'["metadata"]': proof()},
        )
        == "accepted"
    )
    row = adapter._one(
        "SELECT * FROM source_repositories WHERE source_id='source-null'"
    )
    assert row["metadata_json"] == "{}"

    for metadata, path in (
        (None, '["metadata"]'),
        (None, '["metadata","missing"]'),
        ({"private": True}, '["metadata","archived"]'),
    ):
        with pytest.raises(CatalogError) as raised:
            adapter.confirm_source_repository(
                "source-null",
                context["repository_uuidv4"],
                observed_at_us=300,
                parsed_at_us=301,
                scope=scope,
                parser_module="synthetic",
                parser_version="1",
                metadata=metadata,
                field_evidence={path: proof()},
            )
        assert raised.value.code in {
            "INVALID_CURRENT_RESOURCE",
            "INVALID_JSON_REFERENCE",
        }, (metadata, path, raised.value.code, str(raised.value))


def test_authoritative_empty_source_metadata_replaces_known_descendants(api):
    adapter, context = api
    registration = str(uuid.uuid4())
    adapter.c.execute(
        "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('source-empty',?,?,'manual_git','synthetic','{}')",
        (registration, context["service_instance_uuidv4"]),
    )
    scope = {
        "source_registration_uuidv4": registration,
        "service_instance_uuidv4": context["service_instance_uuidv4"],
        "endpoint": "inventory",
    }
    assert (
        adapter.confirm_source_repository(
            "source-empty",
            context["repository_uuidv4"],
            observed_at_us=100,
            parsed_at_us=101,
            scope=scope,
            parser_module="synthetic",
            parser_version="1",
            name="fixture",
            metadata={"owner": {"login": "x"}},
        )
        == "accepted"
    )
    before = adapter._one(
        "SELECT * FROM source_repositories WHERE source_id='source-empty'"
    )
    before_evidence = json.loads(before["field_evidence_json"])
    assert '["metadata","owner","login"]' in before_evidence
    revision = adapter._one(
        "SELECT db_instance_id,local_revision FROM database_identity WHERE singleton=1"
    )

    assert (
        adapter.confirm_source_repository(
            "source-empty",
            context["repository_uuidv4"],
            observed_at_us=200,
            parsed_at_us=201,
            scope=scope,
            parser_module="synthetic",
            parser_version="2",
            metadata={},
            base_revision=revision,
            scope_context=scope,
        )
        == "accepted"
    )
    after = adapter._one(
        "SELECT * FROM source_repositories WHERE source_id='source-empty'"
    )
    evidence = json.loads(after["field_evidence_json"])
    assert after["metadata_json"] == "{}"
    assert '["metadata"]' in evidence
    assert not any(path.startswith('["metadata",') for path in evidence)


def test_source_scope_is_bound_to_exact_registration_and_service(api):
    adapter, context = api
    service = context["service_instance_uuidv4"]
    registration_a, registration_b, registration_c = [
        str(uuid.uuid4()) for _ in range(3)
    ]
    adapter.c.executemany(
        "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES(?,?,?,'manual_git','synthetic','{}')",
        [
            ("source-a", registration_a, service),
            ("source-b", registration_b, service),
            ("source-unbound", registration_c, None),
        ],
    )
    wrong_service = str(uuid.uuid4())
    primary_repo = context["repository_uuidv4"]
    adapter.c.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','foreign','{}')",
        (wrong_service,),
    )
    other_repo = str(uuid.uuid4())
    adapter.c.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'other','{}')",
        (other_repo,),
    )

    def scope(registration, service_instance=service):
        result = {
            "source_registration_uuidv4": registration,
            "endpoint": "inventory",
        }
        if service_instance is not None:
            result["service_instance_uuidv4"] = service_instance
        return result

    adapter.c.execute(
        "INSERT INTO source_repositories(source_id,repository_uuidv4,first_seen_us,last_seen_us,scope_json) VALUES('source-a',?,1,2,?)",
        (context["repository_uuidv4"], json.dumps(scope(registration_a))),
    )
    valid = dict(
        adapter.c.execute(
            "SELECT * FROM source_repositories WHERE source_id='source-a'"
        ).fetchone()
    )
    invalid = dict(valid)
    invalid["scope_json"] = json.dumps(scope(registration_b))
    with pytest.raises(JsonContractError):
        validate_record(adapter.c, "source_repositories", invalid)
    with pytest.raises(JsonContractError):
        adapter.admit_source_row(invalid)

    mismatched_proof = {
        "provider_updated_at_us": None,
        "provider_clock_scope": None,
        "observed_at_us": 2,
        "parsed_at_us": 3,
        "parser_module": "synthetic",
        "parser_version": "1",
        "acquisition_scope": {
            **scope(registration_a),
            "parser_module": "synthetic",
            "parser_version": "2",
        },
    }
    bad_proof = dict(valid)
    bad_proof.update(
        name="captured-name",
        parser_module="synthetic",
        parser_version="1",
        field_evidence_json=json.dumps({'["name"]': mismatched_proof}),
    )
    with pytest.raises(JsonContractError):
        validate_record(adapter.c, "source_repositories", bad_proof)
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET name=?,parser_module=?,parser_version=?,field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            (
                "captured-name",
                "synthetic",
                "1",
                bad_proof["field_evidence_json"],
                primary_repo,
            ),
        )

    mismatched_row_scope = dict(valid)
    mismatched_row_scope.update(
        parser_module="synthetic",
        parser_version="1",
        scope_json=json.dumps(
            {
                **scope(registration_a),
                "parser_module": "synthetic",
                "parser_version": "2",
            }
        ),
    )
    with pytest.raises(JsonContractError):
        validate_record(adapter.c, "source_repositories", mismatched_row_scope)
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET scope_json=?,parser_module=?,parser_version=? WHERE source_id='source-a' AND repository_uuidv4=?",
            (
                mismatched_row_scope["scope_json"],
                "synthetic",
                "1",
                primary_repo,
            ),
        )

    empty_attributed_scope = scope(registration_a)
    adapter.c.execute(
        "INSERT INTO source_repositories(source_id,repository_uuidv4,first_seen_us,last_seen_us,scope_json,parser_module,parser_version) VALUES('source-a',?,7,8,?,'synthetic','1')",
        (other_repo, json.dumps(empty_attributed_scope)),
    )
    empty_attributed = dict(
        adapter.c.execute(
            "SELECT * FROM source_repositories WHERE source_id='source-a' AND repository_uuidv4=?",
            (other_repo,),
        ).fetchone()
    )
    assert adapter.admit_source_row(empty_attributed) == "accepted"
    retained_empty = adapter.c.execute(
        "SELECT first_seen_us,last_seen_us,scope_json,parser_module,parser_version FROM source_repositories WHERE source_id='source-a' AND repository_uuidv4=?",
        (other_repo,),
    ).fetchone()
    assert tuple(retained_empty) == (
        7,
        8,
        json.dumps(empty_attributed_scope, sort_keys=True, separators=(",", ":")),
        "synthetic",
        "1",
    )

    unproven_name = dict(valid)
    unproven_name["name"] = "current-without-proof"
    with pytest.raises(JsonContractError):
        validate_record(adapter.c, "source_repositories", unproven_name)
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET name='current-without-proof' WHERE source_id='source-a' AND repository_uuidv4=?",
            (primary_repo,),
        )

    unproven_metadata = dict(valid)
    unproven_metadata["metadata_json"] = '{"visible":1}'
    with pytest.raises(JsonContractError):
        validate_record(adapter.c, "source_repositories", unproven_metadata)
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET metadata_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            ('{"visible":1}', primary_repo),
        )
    metadata_root_only = {
        "provider_updated_at_us": None,
        "provider_clock_scope": None,
        "observed_at_us": 5,
        "parsed_at_us": 6,
        "parser_module": "synthetic",
        "parser_version": "1",
        "acquisition_scope": scope(registration_a),
    }
    missing_nested_json = json.dumps(
        {
            '["metadata"]': metadata_root_only,
            '["metadata","missing"]': metadata_root_only,
        }
    )
    missing_nested = dict(valid)
    missing_nested["field_evidence_json"] = missing_nested_json
    with pytest.raises(JsonContractError):
        validate_record(adapter.c, "source_repositories", missing_nested)
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            (missing_nested_json, primary_repo),
        )

    root_only_json = json.dumps({'["metadata"]': metadata_root_only})
    nested_metadata = dict(valid)
    nested_metadata["metadata_json"] = '{"visible":1}'
    nested_metadata["field_evidence_json"] = root_only_json
    with pytest.raises(JsonContractError):
        validate_record(adapter.c, "source_repositories", nested_metadata)
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET metadata_json=?,field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            ('{"visible":1}', root_only_json, primary_repo),
        )

    name_evidence = json.dumps({'["name"]': metadata_root_only})
    adapter.c.execute(
        "UPDATE source_repositories SET name='known-name',parser_module='synthetic',parser_version='1',field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
        (name_evidence, primary_repo),
    )
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET name=NULL,field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            (name_evidence, primary_repo),
        )
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET name=NULL,field_evidence_json='{}' WHERE source_id='source-a' AND repository_uuidv4=?",
            (primary_repo,),
        )
    refreshed_name_evidence = json.dumps(
        {
            '["name"]': {
                **metadata_root_only,
                "observed_at_us": 7,
                "parsed_at_us": 8,
            }
        }
    )
    adapter.c.execute(
        "UPDATE source_repositories SET name=NULL,field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
        (refreshed_name_evidence, primary_repo),
    )

    current_metadata = {"owner": {"login": "fixture"}, "size": 2}
    current_field_proof = {
        **metadata_root_only,
        "observed_at_us": 11,
        "parsed_at_us": 12,
    }
    complete_metadata_evidence = json.dumps(
        {
            '["name"]': current_field_proof,
            '["metadata"]': current_field_proof,
            '["metadata","owner"]': current_field_proof,
            '["metadata","owner","login"]': current_field_proof,
            '["metadata","size"]': current_field_proof,
        }
    )
    adapter.c.execute(
        "UPDATE source_repositories SET metadata_json=?,field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
        (json.dumps(current_metadata), complete_metadata_evidence, primary_repo),
    )
    adapter.c.execute(
        "UPDATE source_repositories SET metadata_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
        (json.dumps({"size": 2, "owner": {"login": "fixture"}}), primary_repo),
    )
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET metadata_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            (json.dumps({"owner": {"login": "changed"}, "size": 2}), primary_repo),
        )
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET metadata_json='{}',field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            (complete_metadata_evidence, primary_repo),
        )
    refreshed_empty_metadata_evidence = json.dumps(
        {
            '["name"]': current_field_proof,
            '["metadata"]': {
                **metadata_root_only,
                "observed_at_us": 13,
                "parsed_at_us": 14,
            },
        }
    )
    adapter.c.execute(
        "UPDATE source_repositories SET metadata_json='{}',field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
        (refreshed_empty_metadata_evidence, primary_repo),
    )
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET metadata_json='{}',field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            (name_evidence, primary_repo),
        )

    large_integer_metadata = {"parent": {"id": 9223372036854775808}}
    large_integer_proof = {
        **metadata_root_only,
        "observed_at_us": 15,
        "parsed_at_us": 16,
    }
    large_integer_evidence = json.dumps(
        {
            '["name"]': large_integer_proof,
            '["metadata"]': large_integer_proof,
            '["metadata","parent"]': large_integer_proof,
            '["metadata","parent","id"]': large_integer_proof,
        }
    )
    adapter.c.execute(
        "UPDATE source_repositories SET metadata_json=?,field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
        (
            json.dumps(large_integer_metadata),
            large_integer_evidence,
            primary_repo,
        ),
    )
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET metadata_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            (
                json.dumps({"parent": {"id": 9223372036854775809}}),
                primary_repo,
            ),
        )
    refreshed_integer_proof = {
        **large_integer_proof,
        "observed_at_us": 17,
        "parsed_at_us": 18,
    }
    partially_refreshed_integer_evidence = json.dumps(
        {
            '["name"]': large_integer_proof,
            '["metadata"]': refreshed_integer_proof,
            '["metadata","parent"]': large_integer_proof,
            '["metadata","parent","id"]': refreshed_integer_proof,
        }
    )
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET metadata_json=?,field_evidence_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            (
                json.dumps({"parent": {"id": 9223372036854775809}}),
                partially_refreshed_integer_evidence,
                primary_repo,
            ),
        )

    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "INSERT INTO source_repositories(source_id,repository_uuidv4,first_seen_us,last_seen_us,scope_json) VALUES('source-a',?,1,2,?)",
            (other_repo, json.dumps(scope(registration_b))),
        )
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET scope_json=? WHERE source_id='source-a' AND repository_uuidv4=?",
            (json.dumps(scope(registration_b)), primary_repo),
        )
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET scope_json='{}' WHERE source_id='source-a' AND repository_uuidv4=?",
            (primary_repo,),
        )

    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "INSERT INTO source_repositories(source_id,repository_uuidv4,first_seen_us,last_seen_us,scope_json) VALUES('source-unbound',?,1,2,?)",
            (other_repo, json.dumps(scope(registration_c, wrong_service))),
        )
    adapter.c.execute(
        "INSERT INTO source_repositories(source_id,repository_uuidv4,first_seen_us,last_seen_us,scope_json) VALUES('source-unbound',?,1,2,?)",
        (other_repo, json.dumps(scope(registration_c, None))),
    )
    bare_repo = str(uuid.uuid4())
    adapter.c.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'bare','{}')",
        (bare_repo,),
    )
    adapter.c.execute(
        "INSERT INTO source_repositories(source_id,repository_uuidv4,first_seen_us,last_seen_us,scope_json) VALUES('source-unbound',?,1,2,'{}')",
        (bare_repo,),
    )
    bare_pair = dict(
        adapter.c.execute(
            "SELECT * FROM source_repositories WHERE source_id='source-unbound' AND repository_uuidv4=?",
            (bare_repo,),
        ).fetchone()
    )
    validate_record(adapter.c, "source_repositories", bare_pair)
    bad_capture = {
        "provider_updated_at_us": None,
        "provider_clock_scope": None,
        "observed_at_us": 3,
        "parsed_at_us": 4,
        "parser_module": "synthetic",
        "parser_version": "1",
        "acquisition_scope": scope(registration_c, wrong_service),
    }
    bad_evidence = json.dumps({'["name"]': bad_capture})
    unbound = dict(
        adapter.c.execute(
            "SELECT * FROM source_repositories WHERE source_id='source-unbound'"
        ).fetchone()
    )
    unbound["field_evidence_json"] = bad_evidence
    with pytest.raises(JsonContractError):
        validate_record(adapter.c, "source_repositories", unbound)
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "UPDATE source_repositories SET name='foreign',field_evidence_json=? WHERE source_id='source-unbound'",
            (bad_evidence,),
        )

    with pytest.raises(JsonContractError):
        adapter.assess_source_inventory(
            "source-unbound",
            scope=scope(registration_c, wrong_service),
            observed_at_us=10,
            state="partial",
            members=[],
            terminal=False,
            parser_module="synthetic",
            parser_version="1",
        )
    with pytest.raises(sqlite3.IntegrityError):
        adapter.c.execute(
            "INSERT INTO source_inventory_assessments(source_id,scope_key,scope_json,observed_at_us,state,terminal,members_json,parser_module,parser_version) VALUES('source-unbound','foreign-service',?,10,'partial',0,'[]','synthetic','1')",
            (json.dumps(scope(registration_c, wrong_service)),),
        )


def test_document_and_thread_read_without_parent_metadata_capture(api):
    adapter, _ = api
    assert (
        adapter.admit(
            "document_state",
            candidate(api, kind="pr-body", body="independent"),
            source="import",
        ).status
        == "accepted"
    )
    assert (
        adapter.admit(
            "review_thread_state",
            candidate(api, kind="review-thread", resolved=False),
            source="import",
        ).status
        == "accepted"
    )
    assert (
        adapter.c.execute("SELECT count(*) FROM change_request_state").fetchone()[0]
        == 0
    )
    assert (
        adapter.c.execute("SELECT count(*) FROM eligible_document_state").fetchone()[0]
        == 1
    )
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM eligible_review_thread_state"
        ).fetchone()[0]
        == 1
    )


def test_nested_failed_document_update_rolls_back_body_evidence_and_revision(api):
    adapter, _ = api
    adapter.admit(
        "document_state", candidate(api, kind="pr-body", body="old"), source="import"
    )
    previous = current(adapter, "document_state")
    revision = adapter._one(
        "SELECT local_revision FROM database_identity WHERE singleton=1"
    )
    adapter.c.execute(
        "CREATE TRIGGER fail_document_evidence AFTER UPDATE ON document_state BEGIN SELECT RAISE(ABORT,'injected field/evidence failure'); END"
    )
    adapter.c.execute("BEGIN IMMEDIATE")
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        adapter.admit(
            "document_state",
            candidate(api, kind="pr-body", clock=20, body="would leak"),
            source="import",
        )
    # The caller catches the failure, then commits unrelated outer work.
    adapter.c.execute(
        "UPDATE repositories SET name='outer work' WHERE repository_uuidv4=?",
        (previous["repository_uuidv4"],),
    )
    adapter.c.execute("COMMIT")
    assert current(adapter, "document_state") == previous
    assert (
        adapter.c.execute(
            "SELECT count(*) FROM text_bodies WHERE body='would leak'"
        ).fetchone()[0]
        == 0
    )
    assert (
        adapter._one("SELECT local_revision FROM database_identity WHERE singleton=1")
        == revision
    )
    assert (
        adapter.c.execute("SELECT name FROM repositories").fetchone()[0] == "outer work"
    )


def test_document_commit_failure_rolls_back_entire_current_unit(api):
    adapter, _ = api

    class FailingCommit(sqlite3.Connection):
        fail_commit = False

        def execute(self, sql, *args, **kwargs):
            if sql == "COMMIT" and self.fail_commit:
                raise sqlite3.OperationalError("injected COMMIT failure")
            return super().execute(sql, *args, **kwargs)

    db = sqlite3.connect(":memory:", autocommit=True, factory=FailingCommit)
    db.row_factory = sqlite3.Row
    adapter.c.backup(db)
    failed = CurrentApiState(db)
    before = list(db.iterdump())
    db.fail_commit = True
    with pytest.raises(sqlite3.OperationalError, match="COMMIT"):
        failed.admit(
            "document_state",
            candidate(api, kind="pr-body", body="uncommitted"),
            source="import",
        )
    assert not db.in_transaction
    assert list(db.iterdump()) == before
    db.close()


def test_imported_source_pair_preserves_origins_and_promotes_captured_resource(api):
    sender, context = api
    registration = str(uuid.uuid4())
    sender.c.execute(
        "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('source',?,?,'github_inventory','synthetic','{}')",
        (registration, context["service_instance_uuidv4"]),
    )
    target = sqlite3.connect(":memory:", autocommit=True)
    target.row_factory = sqlite3.Row
    sender.c.backup(target)
    receiver = CurrentApiState(target)
    inventory_scope = {
        "source_registration_uuidv4": registration,
        "service_instance_uuidv4": context["service_instance_uuidv4"],
        "endpoint": "inventory",
    }
    captured = candidate(
        api,
        acquisition_scope={
            **context,
            "source_registration_uuidv4": registration,
            "endpoint": "pulls/1",
        },
        state="open",
    )
    assert (
        receiver.admit("change_request_state", captured, source="import").status
        == "missing_dependency"
    )
    assert (
        sender.confirm_source_repository(
            "source",
            context["repository_uuidv4"],
            observed_at_us=100,
            parsed_at_us=101,
            scope=inventory_scope,
            parser_module="sender.parser",
            parser_version="1",
            name="R1",
            metadata={"private": False},
        )
        == "accepted"
    )
    original = sender._one("SELECT * FROM source_repositories")
    assert receiver.admit_source_row(original) == "accepted"
    assert receiver._one("SELECT * FROM source_repositories") == original
    assert receiver.promote_staging() == 1
    assert (
        target.execute("SELECT count(*) FROM change_request_state").fetchone()[0] == 1
    )

    revision, scope = sender.capture_context(inventory_scope)
    assert (
        sender.confirm_source_repository(
            "source",
            context["repository_uuidv4"],
            observed_at_us=200,
            parsed_at_us=201,
            scope=scope,
            parser_module="sender.parser",
            parser_version="2",
            name="R1 renamed",
            base_revision=revision,
            scope_context=scope,
        )
        == "accepted"
    )
    renamed = sender._one("SELECT * FROM source_repositories")
    assert receiver.admit_source_row(renamed) == "conflict"
    assert receiver.admit_source_row(renamed) == "conflict"
    current_pair = receiver._one("SELECT * FROM source_repositories")
    assert current_pair["name"] == "R1"
    assert current_pair["first_seen_us"] == 100 and current_pair["last_seen_us"] == 200
    assert current_pair["field_evidence_json"] == original["field_evidence_json"]
    assert (
        target.execute("SELECT count(*) FROM eligible_source_repositories").fetchone()[
            0
        ]
        == 0
    )
    assert (
        receiver.admit(
            "change_request_state",
            {**captured, "provider_updated_at_us": 11},
            source="import",
        ).status
        == "identical"
    )
    exported = [
        item
        for item in receiver.export_candidates(context["repository_uuidv4"])
        if item[0] == "source_repositories"
    ]
    assert len(exported) == 2 and all(item[2] for item in exported)
    alternative_row = receiver.source_candidate_row(exported[1][1])
    assert (
        json.loads(alternative_row["field_evidence_json"])['["metadata","private"]'][
            "parser_version"
        ]
        == "1"
    )
    assert validate_catalog(target)["records_checked"] > 0
    target.close()
