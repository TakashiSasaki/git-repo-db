"""Agreed provider scopes, natural thread keys, and no second Node-ID identity."""

import sqlite3
import uuid

import pytest

from repo_catalog.adapters.github.identity import database_resource_id
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.application.query_service import QueryService
from repo_catalog.cli.main import parser
from repo_catalog.domain.document import DocumentKey
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_document_identity import catalog as catalog
from tests.integration.test_catalog3_document_identity import observe
from tests.support.parser_facts import new_result, register_test_profile


def test_no_normalized_node_or_local_thread_id(catalog):
    _, store = catalog
    for row in store.all("SELECT name FROM sqlite_schema WHERE type='table'"):
        names = {c["name"] for c in store.all(f'PRAGMA table_info("{row[0]}")')}
        assert not names & {"provider_node_id", "review_thread_id"}
    columns = store.all("PRAGMA table_info(review_threads)")
    assert [c["name"] for c in sorted(columns, key=lambda c: c["pk"]) if c["pk"]] == [
        "change_request_id",
        "provider_resource_id",
    ]
    names = {c["name"] for c in store.all("PRAGMA table_info(change_requests)")}
    assert {"change_request_kind", "provider_change_request_number"} <= names
    assert not names & {"request_kind", "number"}


def thread(store, owner, resource):
    store.execute(
        "INSERT INTO review_threads(change_request_id,provider_resource_id) VALUES(?,?)",
        (owner, resource),
    )


def current_review_comment(store, owner, resource, body, *, thread_id=None):
    """Admit an explicit current comment with separately selected thread history."""
    binding = store.one(
        "SELECT c.repository_uuidv4,c.repository_binding_id,b.service_instance_uuidv4 "
        "FROM change_requests c JOIN repository_bindings b USING(repository_binding_id) "
        "WHERE c.change_request_id=?",
        (owner,),
    )
    scope = {
        **dict(binding),
        "change_request_id": owner,
        "endpoint": "synthetic-provider-identity",
    }
    if thread_id is not None:
        model = ParserModel(store.connection)
        profile = register_test_profile(store.connection)
        model.ensure_scope_profile(
            profile,
            repository_uuidv4=binding["repository_uuidv4"],
            fact_kind="review-thread",
        )
        result = new_result(store.connection, binding["repository_uuidv4"])
        store.execute(
            "INSERT INTO review_thread_observations(thread_observation_uuidv4,"
            "repository_uuidv4,change_request_id,provider_resource_id,parsed_result_uuidv4,"
            "observed_at_us,payload) VALUES(?,?,?,?,?,0,'{}')",
            (
                str(uuid.uuid4()),
                binding["repository_uuidv4"],
                owner,
                thread_id,
                result,
            ),
        )
        model.publish_result(result)
        model.select_fact(
            result,
            fact_kind="review-thread",
            change_request_id=owner,
            provider_resource_id=thread_id,
        )
    admitted = CurrentResources(store).admit(
        {
            **dict(binding),
            "change_request_id": owner,
            "kind": "review-comment",
            "provider_change_request_document_id": resource,
            "body": body,
            "provider_updated_at_us": 0,
            "provider_clock_scope": "github-review-comment-updated-at",
            "observed_at_us": 0,
            "parsed_at_us": 0,
            "parser_module": __name__,
            "parser_version": "1",
            "review_thread_provider_resource_id": thread_id,
            "acquisition_scope": scope,
        },
        source="import",
    )
    assert admitted.status == "accepted"


def test_thread_uniqueness_is_parent_scoped_not_service_global(catalog):
    _, store = catalog
    with store.transaction():
        thread(store, "pr1", "opaque:shared/id")
        thread(store, "pr2", "opaque:shared/id")
    assert store.one("SELECT count(*) FROM review_threads")[0] == 2
    with pytest.raises(sqlite3.IntegrityError):
        thread(store, "pr1", "opaque:shared/id")
    for invalid in (None, ""):
        with pytest.raises(sqlite3.IntegrityError):
            thread(store, "pr1", invalid)
    with pytest.raises(sqlite3.IntegrityError):
        store.execute("UPDATE review_threads SET provider_resource_id='changed'")


def test_comment_thread_fk_requires_same_change_request(catalog):
    _, store = catalog
    with store.transaction():
        thread(store, "pr2", "remote-thread")
        current_review_comment(store, "pr1", "99", "comment")
    with pytest.raises(sqlite3.IntegrityError), store.transaction():
        store.execute(
            "UPDATE review_resources SET review_thread_provider_resource_id='remote-thread' "
            "WHERE change_request_id='pr1' AND kind='review-comment'",
        )
    with store.transaction():
        thread(store, "pr1", "remote-thread")
        store.execute(
            "UPDATE review_resources SET review_thread_provider_resource_id='remote-thread' "
            "WHERE change_request_id='pr1' AND kind='review-comment'",
        )
    assert (
        store.one("SELECT review_thread_provider_resource_id FROM review_resources")[0]
        == "remote-thread"
    )
    assert not store.all("PRAGMA foreign_key_check")


def test_nodes_do_not_bridge_distinct_documents_or_reject_changed_alias(catalog):
    _, store = catalog
    # PR conversation comments retain immutable observed history. Node aliases
    # remain provider metadata and cannot bridge two natural document keys.
    a = DocumentKey("pr1", "issue-comment", "100")
    b = DocumentKey("pr1", "issue-comment", "101")
    with store.transaction():
        observe(store, a, "first", 0, node="old-node")
        observe(store, a, "second", 1, node="new-node")
        observe(store, b, "third", 2, node="new-node")
    assert store.one("SELECT count(*) FROM documents")[0] == 2
    assert store.one("SELECT count(*) FROM document_observations")[0] == 3
    assert [
        r[0]
        for r in store.all(
            "SELECT json_extract(metadata,'$.node_id') FROM document_observations ORDER BY document_observation_id"
        )
    ] == ["old-node", "new-node", "new-node"]


def test_thread_cli_and_query_require_parent_and_support_kind_scope(catalog):
    state, store = catalog
    with store.transaction():
        for parent in ("pr1", "pr2"):
            thread(store, parent, "shared-thread")
            current_review_comment(
                store, parent, "100", parent, thread_id="shared-thread"
            )
        binding = store.one(
            "SELECT repository_binding_id FROM change_requests WHERE change_request_id='pr1'"
        )[0]
        store.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES('mr1','10000000-0000-4000-8000-000000000001',?,'merge_request',1)",
            (binding,),
        )
    opts = dict(
        repo="10000000-0000-4000-8000-000000000001",
        provider_change_request_number=1,
        provider_resource_id="shared-thread",
    )
    query = QueryService(state)
    with pytest.raises(CatalogError, match="ambiguous"):
        query.query("pr thread", opts)
    rows = query.query(
        "pr thread", {**opts, "change_request_kind": "pull_request"}
    ).data["items"]
    assert len(rows) == 1 and rows[0]["body"] == "pr1"
    assert rows[0]["review_thread_provider_resource_id"] == "shared-thread"
    with pytest.raises(CatalogError, match="requires"):
        query.query(
            "pr thread",
            {
                "repo": "10000000-0000-4000-8000-000000000001",
                "provider_resource_id": "shared-thread",
            },
        )
    args = parser().parse_args(
        [
            "pr",
            "thread",
            "--repo",
            "10000000-0000-4000-8000-000000000001",
            "--provider-change-request-number",
            "1",
            "--change-request-kind",
            "pull_request",
            "--provider-resource-id",
            "shared-thread",
        ]
    )
    assert (
        args.provider_change_request_number == 1
        and args.change_request_kind == "pull_request"
    )
    with pytest.raises(CatalogError):
        parser().parse_args(["pr", "thread", "--thread-id", "old-synthetic-key"])


@pytest.mark.parametrize(
    "value,expected", [(123, "123"), ("00123", "00123"), (2**63, str(2**63))]
)
def test_database_resource_id_preserves_exact_value(value, expected):
    assert database_resource_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [None, True, False, 0, -1, 1.0, "", " 1", "0", "１２３", "NODE_only", {}, []],
)
def test_database_resource_id_does_not_accept_node_id_or_invalid_scalar(value):
    with pytest.raises(ValueError):
        database_resource_id(value)
