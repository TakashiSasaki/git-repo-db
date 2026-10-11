"""Portable namespaces, natural current documents and exact shared text."""

import hashlib
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite import text_bodies
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.index import rebuild
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.domain.document import DocumentKey, text_body_sha256
from repo_catalog.domain.models import CatalogError
from tests.support.domain_facts import (
    TIME_US,
    admit_pr,
    candidate,
    repository_uuid,
    seed_owners,
)

OBSERVED_AT_US = TIME_US


@pytest.fixture
def catalog(tmp_path):
    state = tmp_path / "catalog"
    MaintenanceService(state).init("catalog-text-v1", 67108864, 0)
    with Store(state) as store:
        with store.transaction():
            seed_owners(store.connection)
            for number in (1, 2):
                assert admit_pr(store, number, state="open").status == "accepted"
        yield state, store
        assert not store.all("PRAGMA foreign_key_check")
        assert store.one("PRAGMA integrity_check")[0] == "ok"


def observe(store, key, body, position, *, observed_at_us=OBSERVED_AT_US, node=None):
    """Admit one current value with an actual comparable provider timestamp."""
    number = int(key.change_request_id.removeprefix("pr"))
    data = candidate(
        number,
        kind=key.kind,
        provider_change_request_document_id=key.provider_change_request_document_id,
        body=body,
        clock=observed_at_us + position,
        observed_at_us=observed_at_us + position,
    )
    if node is not None:
        data["metadata"] = {"node_id": node}
    result = CurrentApiState(store).admit("document_state", data, source="import")
    assert result.status in {"accepted", "identical", "stale"}
    return key


def test_no_document_local_id_or_version_and_direct_digest_fk(catalog):
    _, store = catalog
    for table in ("documents", "document_state"):
        columns = store.all(f"PRAGMA table_info({table})")
        assert not {row["name"] for row in columns} & {
            "document_id",
            "document_version_id",
            "document_observation_id",
            "parsed_result_uuidv4",
            "parser_profile_uuidv4",
        }
        assert [
            row["name"]
            for row in sorted(columns, key=lambda row: row["pk"])
            if row["pk"]
        ] == [
            "change_request_id",
            "kind",
            "provider_change_request_document_id",
        ]
    refs = store.all("PRAGMA foreign_key_list(document_state)")
    assert any(
        row["table"] == "text_bodies"
        and row["from"] == "text_body_sha256"
        and row["to"] == "sha256"
        for row in refs
    )
    assert not store.one(
        "SELECT 1 FROM sqlite_schema WHERE name='document_observations'"
    )


def test_service_uuidv4_namespaces_do_not_merge_by_url(catalog):
    _, store = catalog
    with store.transaction():
        a = add_instance(store, "gitlab", "first", "https://synthetic.invalid")
        b = add_instance(store, "gitlab", "second", "https://synthetic.invalid")
        assert a != b
        for value in (a, b):
            parsed = uuid.UUID(value)
            assert parsed.version == 4 and parsed.variant == uuid.RFC_4122
            assert str(parsed) == value
        bind(store, repository_uuid(1), a, "00123")
        bind(store, repository_uuid(2), b, "00123")
        with pytest.raises(CatalogError, match="already bound"):
            bind(store, repository_uuid(2), a, "00123")
        bind(store, repository_uuid(2), a, "123")
        assert {
            row[0]
            for row in store.all(
                "SELECT provider_repository_id FROM repository_bindings WHERE service_instance_uuidv4=?",
                (a,),
            )
        } == {"00123", "123"}


@pytest.mark.parametrize(
    "invalid",
    [
        "instance",
        str(uuid.uuid5(uuid.NAMESPACE_URL, "https://synthetic.invalid")),
        "00000000-0000-7000-8000-000000000101",
        "00000000-0000-4000-7000-000000000101",
        "550E8400-E29B-41D4-A716-446655440000",
        "00000000000040008000000000000101",
    ],
)
def test_noncanonical_or_non_v4_service_namespace_rejected(catalog, invalid):
    _, store = catalog
    with pytest.raises(sqlite3.IntegrityError):
        store.execute(
            "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'git','invalid','{}')",
            (invalid,),
        )


def test_document_tuple_distinguishes_parent_kind_and_provider_spelling(catalog):
    _, store = catalog
    keys = [
        DocumentKey("pr1", "pr-title", "00123"),
        DocumentKey("pr1", "pr-body", "00123"),
        DocumentKey("pr2", "pr-body", "00123"),
        DocumentKey("pr1", "pr-body", "123"),
    ]
    with store.transaction():
        for position, key in enumerate(keys):
            assert observe(store, key, "shared", position) == key
    assert store.one("SELECT count(*) FROM documents")[0] == 4
    assert store.one("SELECT count(*) FROM document_state")[0] == 4
    assert store.one("SELECT count(*) FROM text_bodies")[0] == 1


def test_repeated_current_values_keep_one_state_and_search_current_body(catalog):
    state, store = catalog
    key = DocumentKey("pr1", "pr-body", "123")
    for position, body in enumerate(("A marker", "A marker", "B marker", "A marker")):
        observe(store, key, body, position)
    current = dict(store.one("SELECT * FROM document_state"))
    assert current["text_body_sha256"] == text_body_sha256("A marker")
    assert current["observed_at_us"] == OBSERVED_AT_US + 3
    observe(store, key, "B marker", 0)
    assert dict(store.one("SELECT * FROM document_state")) == current
    assert store.one("SELECT count(*) FROM document_state")[0] == 1
    assert store.one("SELECT count(*) FROM text_bodies")[0] == 2
    query = QueryService(state)
    options = {"repo": repository_uuid(1), "literal": "A marker"}
    before = query.query("search pr", options).data["items"]
    assert len(before) == 1
    assert (
        query.query("search pr", {**options, "literal": "B marker"}).data["items"] == []
    )
    rebuild(store, "pr")
    assert query.query("search pr", options).data["items"] == before
    latest = query.query(
        "pr documents",
        {"repo": repository_uuid(1), "provider_change_request_number": 1},
    ).data["items"]
    assert len(latest) == 1 and latest[0]["body"] == "A marker"
    assert not latest[0].keys() & {
        "document_id",
        "document_version_id",
        "document_observation_id",
    }


@pytest.mark.parametrize(
    "column,value",
    [
        ("kind", "pr-title"),
        ("change_request_id", "pr2"),
        ("provider_change_request_document_id", "999"),
    ],
)
def test_current_state_must_belong_to_exact_document(catalog, column, value):
    _, store = catalog
    observe(store, DocumentKey("pr1", "pr-body", "123"), "body", 0)
    with pytest.raises(sqlite3.IntegrityError):
        store.execute(f"UPDATE document_state SET {column}=?", (value,))
    assert store.one("SELECT kind FROM document_state")[0] == "pr-body"


def test_text_digest_exact_utf8_and_empty_not_missing(catalog):
    _, store = catalog
    bodies = ["é", "e\u0301", "line\n", "line\r\n", "line", "", "\x00", "日本語"]
    with store.transaction():
        digests = [
            text_bodies.intern_text_body(store.connection, body) for body in bodies
        ]
        for body, digest in zip(bodies, digests, strict=True):
            assert digest == hashlib.sha256(body.encode("utf-8")).digest()
            assert text_bodies.intern_text_body(store.connection, body) == digest
    assert len(set(digests)) == len(bodies)
    assert check_catalog(store) == []
    for invalid in (None, b"bytes", "\ud800"):
        with pytest.raises(CatalogError) as exc:
            text_bodies.intern_text_body(store.connection, invalid)
        assert exc.value.code == "INVALID_TEXT_BODY"


def test_bad_digest_or_collision_is_error_not_second_body(catalog, monkeypatch):
    _, store = catalog
    digest = text_bodies.intern_text_body(store.connection, "A")
    with pytest.raises(CatalogError) as exc:
        text_bodies.intern_text_body(store.connection, "A", expected_sha256=b"x" * 32)
    assert exc.value.code == "TEXT_BODY_DIGEST_MISMATCH"
    monkeypatch.setattr(text_bodies, "text_body_sha256", lambda body: digest)
    with pytest.raises(CatalogError) as exc, store.transaction():
        observe(store, DocumentKey("pr1", "pr-body", "123"), "B", 0)
    assert exc.value.code == "TEXT_BODY_IDENTITY_CONFLICT"
    assert store.one("SELECT count(*) FROM text_bodies")[0] == 1
    assert store.one("SELECT count(*) FROM documents")[0] == 0
    with pytest.raises(sqlite3.IntegrityError):
        store.execute(
            "INSERT INTO text_bodies(body,byte_length,sha256) VALUES('B',1,?)",
            (digest,),
        )


def test_explicit_audit_detects_digest_corruption(catalog):
    _, store = catalog
    store.execute(
        "INSERT INTO text_bodies(body,byte_length,sha256) VALUES('A',1,?)",
        (text_body_sha256("B"),),
    )
    assert any(
        issue.get("code") == "TEXT_BODY_DIGEST_MISMATCH"
        for issue in check_catalog(store)
    )


def test_unresolved_current_is_partial_without_parser_selection(catalog):
    state, store = catalog
    data = candidate(
        kind="pr-body", provider_change_request_document_id="123", body="A", clock=100
    )
    api = CurrentApiState(store)
    assert api.admit("document_state", data, source="import").status == "accepted"
    assert (
        api.admit(
            "document_state",
            {**data, "body": "B", "parsed_at_us": TIME_US + 100},
            source="import",
        ).status
        == "conflict"
    )
    assert store.one("SELECT count(*) FROM eligible_document_state")[0] == 0
    result = QueryService(state).query(
        "pr documents",
        {"repo": repository_uuid(1), "provider_change_request_number": 1},
    )
    assert result.data["items"] == []
    assert result.coverage.missing
    assert store.one("SELECT count(*) FROM document_state")[0] == 1
    assert (
        store.one(
            "SELECT count(*) FROM exchange_staging WHERE reason='current_state:conflict'"
        )[0]
        == 1
    )
    record = json.loads(store.one("SELECT record_json FROM exchange_staging")[0])
    assert record["body"] == "B"
