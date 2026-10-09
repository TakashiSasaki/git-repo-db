"""Agreed provider scopes, natural thread keys, and no second Node-ID identity."""

import sqlite3

import pytest

from repo_catalog.adapters.github.identity import database_resource_id
from repo_catalog.application.query_service import QueryService
from repo_catalog.cli.main import parser
from repo_catalog.domain.document import DocumentKey
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_document_identity import catalog as catalog
from tests.integration.test_catalog3_document_identity import observe


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
    key = DocumentKey("pr1", "review-comment", "99")
    with store.transaction():
        thread(store, "pr2", "remote-thread")
    with pytest.raises(sqlite3.IntegrityError), store.transaction():
        observe(store, key, "comment", 0, thread="remote-thread")
    with store.transaction():
        thread(store, "pr1", "remote-thread")
        observe(store, key, "comment", 0, thread="remote-thread")
    assert not store.all("PRAGMA foreign_key_check")


def test_nodes_do_not_bridge_distinct_documents_or_reject_changed_alias(catalog):
    _, store = catalog
    a = DocumentKey("pr1", "review-comment", "100")
    b = DocumentKey("pr1", "review-comment", "101")
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
            observe(
                store,
                DocumentKey(parent, "review-comment", "100"),
                parent,
                0,
                thread="shared-thread",
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
