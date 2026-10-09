"""Executable decisions: portable service namespaces, natural documents and text."""

import hashlib
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.github.persistence import ApiFacts
from repo_catalog.adapters.sqlite import text_bodies
from repo_catalog.adapters.sqlite.index import rebuild
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.domain.document import DocumentKey, text_body_sha256
from repo_catalog.domain.models import CatalogError

OBSERVED_AT_US = 1_791_244_800_000_000


@pytest.fixture
def catalog(tmp_path):
    state = tmp_path / "catalog"
    MaintenanceService(state).init("catalog-text-v1", 67108864, 0)
    with Store(state) as store:
        with store.transaction():
            namespace = add_instance(store, "github", "synthetic")
            for number in (1, 2):
                store.execute(
                    "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,?,'{}')",
                    (
                        f"10000000-0000-4000-8000-{number:012d}",
                        f"synthetic/repo{number}",
                    ),
                )
                bind(
                    store,
                    f"10000000-0000-4000-8000-{number:012d}",
                    namespace,
                    str(number),
                )
                binding = store.one(
                    "SELECT repository_binding_id FROM repository_bindings WHERE repository_uuidv4=?",
                    (f"10000000-0000-4000-8000-{number:012d}",),
                )[0]
                store.execute(
                    "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES(?,?,?,'pull_request',1)",
                    (f"pr{number}", f"10000000-0000-4000-8000-{number:012d}", binding),
                )
        yield state, store


def observe(store, key, body, position, *, observed_at_us=OBSERVED_AT_US, node=None):
    """Synthetic explicit input, verified profile, result and selection."""
    if not hasattr(store, "fixture_profile") or not store.one(
        "SELECT 1 FROM parser_profiles WHERE parser_profile_uuidv4=?",
        (store.fixture_profile,),
    ):
        model = ParserModel(store.connection)
        definition = {
            "implementation": {"fixture": "document-contract"},
            "settings": {},
            "output_schema": {},
            "capabilities": [
                {"owner_kind": "repository", "fact_kind": kind}
                for kind in (
                    "pr-title",
                    "pr-body",
                    "issue-comment",
                    "review",
                    "review-comment",
                    "review-thread",
                )
            ],
        }
        profile = model.register_profile(definition)
        verification = model.verify_profile(
            profile,
            criteria={"fixture": True},
            evidence={
                "definition": definition,
                "capabilities": [
                    {**item, "outcome": "passed", "checks": ["synthetic-fixture"]}
                    for item in definition["capabilities"]
                ],
            },
        )
        model.trust_verification(verification)
        store.fixture_profile = profile
        store.fixture_acquisitions = {}
    cache_key = (*key, position, observed_at_us)
    saved = store.fixture_acquisitions.get(cache_key)
    if saved is None:
        repo = store.one(
            "SELECT repository_uuidv4 FROM change_requests WHERE change_request_id=?",
            (key.change_request_id,),
        )[0]
        scope, collection_id = str(uuid.uuid4()), str(uuid.uuid4())
        store.execute(
            "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,request_context,parser_version,profile_version,confidence) VALUES(?,?,'{}','fixture','fixture','proven')",
            (scope, repo),
        )
        store.execute(
            "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,resume_scope_id,observed_at_us) VALUES(?,?,?,?,?,?)",
            (
                collection_id,
                repo,
                key.change_request_id,
                key.kind,
                scope,
                observed_at_us,
            ),
        )
        payload = intern_payload(
            store.connection, body.encode("utf-8"), representation="decoded_api"
        )
        occurrence = store.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,observed_at_us,parsed_at_us) VALUES(?,?,?,0,?,?,'{}',?,?)",
            (
                str(uuid.uuid4()),
                repo,
                collection_id,
                *payload.parameters(),
                observed_at_us,
                observed_at_us,
            ),
        ).lastrowid
        collection = {
            "fetch_collection_id": collection_id,
            "change_request_id": key.change_request_id,
            "kind": key.kind,
        }
        facts = ApiFacts(store, store.config["github"])
        facts.profile_uuid = store.fixture_profile
        saved = facts, collection, occurrence
        store.fixture_acquisitions[cache_key] = saved
    facts, collection, occurrence = saved
    result = facts.document(
        *key,
        body,
        {"id": key.provider_change_request_document_id, "node_id": node, "body": body},
        collection,
        occurrence,
        position,
        observed_at_us,
    )
    facts.publish()
    return result


def test_no_document_local_id_or_version_and_direct_digest_fk(catalog):
    _, store = catalog
    table_names = {
        row[0] for row in store.all("SELECT name FROM sqlite_schema WHERE type='table'")
    }
    assert "document_versions" not in table_names
    key = ["change_request_id", "kind", "provider_change_request_document_id"]
    columns = store.all("PRAGMA table_info(documents)")
    assert [
        row["name"] for row in sorted(columns, key=lambda row: row["pk"]) if row["pk"]
    ] == key
    for table in table_names:
        names = {row["name"] for row in store.all(f'PRAGMA table_info("{table}")')}
        assert not names & {
            "document_id",
            "change_request_document_id",
            "document_version_id",
            "current_document_version_id",
            "service_instance_id",
            "provider_document_id",
        }
    assert any(
        row["from"] == "text_body_sha256"
        and row["table"] == "text_bodies"
        and row["to"] == "sha256"
        for row in store.all("PRAGMA foreign_key_list(document_observations)")
    )
    assert "text_body_id" in {
        row["name"] for row in store.all("PRAGMA table_info(text_bodies)")
    }


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
        bind(store, "10000000-0000-4000-8000-000000000001", a, "00123")
        bind(store, "10000000-0000-4000-8000-000000000002", b, "00123")
        with pytest.raises(CatalogError, match="already bound"):
            bind(store, "10000000-0000-4000-8000-000000000002", a, "00123")
        # Provider values are not silently normalized to integers.
        bind(store, "10000000-0000-4000-8000-000000000002", a, "123")
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
    assert store.one("SELECT count(*) FROM text_bodies")[0] == 1
    assert not store.all("PRAGMA foreign_key_check")


def test_direct_observations_keep_a_a_b_a_and_replay_does_not_move_current(catalog):
    state, store = catalog
    key = DocumentKey("pr1", "pr-body", "123")
    with store.transaction():
        for position, body in enumerate(
            ("A marker", "A marker", "B marker", "A marker")
        ):
            observe(
                store, key, body, position, observed_at_us=OBSERVED_AT_US + position
            )
    rows = store.all(
        "SELECT document_observation_id,text_body_sha256,observed_at_us FROM document_observations ORDER BY document_observation_id"
    )
    assert len(rows) == 4 and len({row[0] for row in rows}) == 4
    assert rows[0][1] == rows[1][1] == rows[3][1] != rows[2][1]
    assert [row[2] for row in rows] == [OBSERVED_AT_US + i for i in range(4)]
    current = store.one(
        "SELECT document_observation_id FROM current_document_observations"
    )[0]
    assert current == rows[3][0]
    with store.transaction():
        observe(store, key, "A marker", 0)
    assert store.one("SELECT count(*) FROM document_observations")[0] == 4
    assert (
        store.one("SELECT document_observation_id FROM current_document_observations")[
            0
        ]
        == current
    )
    assert store.one("SELECT count(*) FROM text_bodies")[0] == 2
    # Indexed and scan lookup select the same distinct observations. FTS inputs
    # share bodies, but must not coalesce occurrences or select a stale state.
    query = QueryService(state)
    options = {
        "repo": "10000000-0000-4000-8000-000000000001",
        "literal": "A marker",
        "document_observations": "all",
    }
    before = query.query("search pr", options).data["items"]
    assert len(before) == 3
    rebuild(store, "pr")
    after = query.query("search pr", options).data["items"]
    assert after == before
    assert store.one("SELECT count(*) FROM search_documents WHERE kind='pr'")[0] == 2
    latest = query.query(
        "pr documents",
        {
            "repo": "10000000-0000-4000-8000-000000000001",
            "provider_change_request_number": 1,
        },
    ).data["items"]
    assert len(latest) == 1 and latest[0]["document_observation_id"] == current
    assert "document_id" not in latest[0] and "document_version_id" not in latest[0]


def test_current_observation_must_belong_to_exact_document(catalog):
    _, store = catalog
    title = DocumentKey("pr1", "pr-title", "123")
    body = DocumentKey("pr1", "pr-body", "123")
    with store.transaction():
        observe(store, title, "title", 0)
        observe(store, body, "body", 1)
    wrong = store.one(
        "SELECT parsed_result_uuidv4 FROM current_document_observations WHERE kind='pr-title'"
    )[0]
    with pytest.raises(sqlite3.IntegrityError):
        ParserModel(store.connection).select_fact(
            wrong,
            fact_kind="pr-body",
            change_request_id="pr1",
            kind="pr-body",
            provider_change_request_document_id="123",
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.execute(
            "UPDATE document_observations SET kind='pr-title' WHERE kind='pr-body'"
        )


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
    assert store.one("SELECT count(*) FROM text_bodies")[0] == len(bodies)
    assert check_catalog(store) == []
    for invalid in (None, b"bytes", "\ud800"):
        with pytest.raises(CatalogError) as exc:
            text_bodies.intern_text_body(store.connection, invalid)
        assert exc.value.code == "INVALID_TEXT_BODY"


def test_bad_digest_or_collision_is_error_not_second_body(catalog, monkeypatch):
    _, store = catalog
    with store.transaction():
        digest = text_bodies.intern_text_body(store.connection, "A")
    with pytest.raises(CatalogError) as exc:
        text_bodies.intern_text_body(store.connection, "A", expected_sha256=b"x" * 32)
    assert exc.value.code == "TEXT_BODY_DIGEST_MISMATCH"
    # Artificial collision injection tests handling, not a claimed SHA-256 break.
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


def test_unresolved_current_is_partial_not_implicit_maximum_observation(catalog):
    state, store = catalog
    with store.transaction():
        observe(store, DocumentKey("pr1", "pr-body", "123"), "A", 0)
        result_id = store.one("SELECT parsed_result_uuidv4 FROM document_observations")[
            0
        ]
        ParserModel(store.connection).select_fact(
            result_id,
            fact_kind="pr-body",
            change_request_id="pr1",
            kind="pr-body",
            provider_change_request_document_id="123",
            predecessors=[],
        )
    result = QueryService(state).query(
        "pr documents",
        {
            "repo": "10000000-0000-4000-8000-000000000001",
            "provider_change_request_number": 1,
        },
    )
    assert result.data["items"] == []
    assert any(
        item["reason"] == "document_current_selection_unresolved"
        for item in result.coverage.missing
    )
    history = QueryService(state).query(
        "pr documents",
        {
            "repo": "10000000-0000-4000-8000-000000000001",
            "provider_change_request_number": 1,
            "document_observations": "all",
        },
    )
    assert len(history.data["items"]) == 1
