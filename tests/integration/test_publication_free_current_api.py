"""Current PR/text/thread acceptance has typed owners and independent evidence."""

import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.json_contracts import guard_sql, validate_catalog
from repo_catalog.adapters.sqlite.schema import (
    DDL_SHA256,
    FORMAT_ID,
    SCHEMA_VERSION,
    schema_sql,
)


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
