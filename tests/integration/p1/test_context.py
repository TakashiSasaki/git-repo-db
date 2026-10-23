"""Adversarial P3 interface tests against the actual isolated Context DDL."""

import sqlite3

import pytest

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_schema import compose, register_functions
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from tests.support.authorized_context import FixtureContextStore

REPO = "9ebbe38a-f937-40e6-a99c-701835ebcf10"
SERVICE = "aad25448-03eb-4f83-a578-ceec84375b5a"
SOURCE = "80f5c4f9-6d6b-4691-af3c-00ab02ad9f53"
KEY = ResourceKey.from_native(SERVICE, "issue", "7")
PROVENANCE = canonical({"source": "provider.example", "evidence": "event-7"})


def p1_grants():
    """Finite identities used by this fixture and its imported Coverage tests."""
    parents = tuple(
        ResourceKey.from_native(SERVICE, "pull_request", value)
        for value in ("10", "11", "absent", "global-shape-test")
    )
    return DependencySet(
        resources={
            KEY,
            *parents,
            *(
                ResourceKey.from_native(SERVICE, "issue", value)
                for value in ("detached", "detached-transfer", "absent", "8")
            ),
            *(
                ResourceKey.document(parent, "review", "review", "same-provider-doc-id")
                for parent in parents[:2]
            ),
            ResourceKey.document(parents[2], "document", "body", "real-id"),
            ResourceKey.document(parents[3], "document", "body", "D1"),
        },
        repositories={
            REPO,
            "a1a5dfd6-69a3-4274-bbc7-2e7f6bcd39a4",
            "86556e5f-ee55-4f4d-87c1-d30c5e14dff9",
        },
        sources={SOURCE},
        source_repository_pairs={(SOURCE, REPO)},
        provider_registrations={SERVICE},
        object_oids={OID("sha1", "a" * 40)},
    )


@pytest.fixture
def context(tmp_path):
    path = tmp_path / "context.sqlite3"
    db = sqlite3.connect(path, isolation_level=None)
    register_functions(db)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    db.executescript(compose("context"))
    db.execute("INSERT INTO providers VALUES(?,?,?)", (SERVICE, "github", "{}"))
    db.execute("INSERT INTO repository_context VALUES(?,?)", (REPO, "{}"))
    db.execute("INSERT INTO sources VALUES(?,?,?)", (SOURCE, SERVICE, "{}"))
    store = FixtureContextStore(db, p1_grants())
    store.resource(KEY, REPO)
    yield db, store, path
    store.close()
    db.close()


def candidate(
    value, *, clock=4, domain="provider.updated_at", evidence="event-7", observed=10
):
    return FieldCandidate(
        KEY,
        "title",
        canonical(value),
        FieldClock(domain, clock),
        canonical({"source": "provider.example", "evidence": evidence}),
        observed,
    )


def test_missing_differs_from_explicit_null(context):
    _, store, _ = context
    assert store.candidates(KEY, "title") == ()
    store.admit_field(candidate(None))
    assert store.candidates(KEY, "title")[0].value_json == "null"


def test_current_candidates_preserve_equal_and_incomparable(context):
    _, store, _ = context
    for item in [
        candidate("a"),
        candidate("b", evidence="event-8"),
        candidate("other", domain="other-provider"),
        candidate("unclocked", clock=None),
    ]:
        assert store.admit_field(item) == "insert"
    assert len(store.candidates(KEY, "title")) == 4
    store.admit_field(candidate("new", clock=5))
    assert {json.value_json for json in store.candidates(KEY, "title")} == {
        '"new"',
        '"other"',
        '"unclocked"',
    }
    assert store.admit_field(candidate("old", clock=3)) == "stale"


def test_exact_original_replay_does_not_rewrite_provenance(context):
    _, store, _ = context
    original = candidate("title", observed=1)
    assert store.admit_field(original) == "insert"
    assert store.admit_field(original) == "duplicate"
    with pytest.raises(ValueError, match="observation time"):
        store.admit_field(candidate("title", observed=999))
    assert store.candidates(KEY, "title") == (original,)


def test_generated_source_clock_is_real_sqlite_value(context):
    db, store, _ = context
    store.admit_field(candidate("a", clock=(1 << 63) - 1))
    assert db.execute(
        "SELECT clock_domain,source_clock_us FROM field_candidates"
    ).fetchone() == ("provider.updated_at", (1 << 63) - 1)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                *KEY.coordinates(),
                "broken",
                "null",
                '{"domain":"actual"}',
                PROVENANCE,
                1,
            ),
        )


def test_context_independent_transaction_rollback_and_restart(context):
    db, store, path = context
    with store.transaction(rollback=True):
        store.admit_field(candidate("discarded"))
    other = sqlite3.connect(path)
    register_functions(other)
    try:
        assert ContextStore(other).candidates(KEY, "title") == ()
    finally:
        other.close()
    store.admit_field(candidate("durable"))
    assert store.candidates(KEY, "title")[0].value_json == '"durable"'


def test_context_only_resource_needs_no_core_or_source_membership(context):
    db, store, path = context
    detached = ResourceKey.from_native(SERVICE, "issue", "detached")
    store.resource(detached, None)
    assert db.execute("SELECT count(*) FROM source_repositories").fetchone()[0] == 0
    # File-backed I6-A writes acquire the catalog gate; no Core/Operational
    # store or Source membership is created by detached Context registration.
    assert sorted(p.name for p in path.parent.iterdir()) == [
        "context.sqlite3",
        "p1-writer.lock",
    ]


def test_portable_core_reference_validated_and_no_sender_promotion(context):
    db, store, _ = context
    sender = canonical(
        {"source": "remote", "evidence": "event-8", "sender_verified": True}
    )
    with pytest.raises(ValueError, match="absent"):
        store.link_core(KEY, "head", "sha1", "a" * 40, sender, lambda *_: False)
    store.link_core(KEY, "head", "sha1", "a" * 40, sender, lambda *_: True)
    assert db.execute(
        "SELECT object_format,full_oid,provenance_json FROM core_references"
    ).fetchone() == ("sha1", "a" * 40, sender)
    assert "receiver_verified" not in sender


def test_source_membership_cannot_be_removed_or_rebound(context):
    db, _, _ = context
    db.execute("INSERT INTO source_repositories VALUES(?,?,?)", (SOURCE, REPO, "{}"))
    second = "a1a5dfd6-69a3-4274-bbc7-2e7f6bcd39a4"
    db.execute("INSERT INTO repository_context VALUES(?,?)", (second, "{}"))
    for sql, args in [
        ("DELETE FROM source_repositories", ()),
        ("UPDATE source_repositories SET repository_uuidv4=?", (second,)),
        (
            "INSERT OR REPLACE INTO source_repositories VALUES(?,?,?)",
            (SOURCE, REPO, "{}"),
        ),
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql, args)
    assert (
        db.execute("SELECT repository_uuidv4 FROM source_repositories").fetchone()[0]
        == REPO
    )


def test_source_empty_inventory_is_durable_without_any_membership(context):
    db, _, _ = context
    db.execute(
        "INSERT INTO source_inventory_evidence VALUES(?,?,?,?,?,?,?)",
        (SOURCE, "{}", 5, "complete", 1, "[]", PROVENANCE),
    )
    assert db.execute("SELECT count(*) FROM source_repositories").fetchone()[0] == 0
    assert db.execute(
        "SELECT terminal,members_json FROM source_inventory_evidence"
    ).fetchone() == (1, "[]")


def test_children_have_real_parent_and_document_kind_coordinates(context):
    db, store, _ = context
    first = ResourceKey.from_native(SERVICE, "pull_request", "10")
    second = ResourceKey.from_native(SERVICE, "pull_request", "11")
    for parent in (first, second):
        store.resource(parent, REPO)
        key = ResourceKey.document(parent, "review", "review", "same-provider-doc-id")
        store.resource(
            key,
            REPO,
            identification=RI.scoped(key, parent, "review", "same-provider-doc-id"),
        )

    assert (
        db.execute(
            "SELECT count(*) FROM resources WHERE resource_kind='review'"
        ).fetchone()[0]
        == 2
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
            (
                SERVICE,
                "review",
                canonical("same-provider-doc-id"),
                "pull_request",
                first.provider_resource_id,
                "review",
                "same-provider-doc-id",
            ),
        )
    absent = ResourceKey.from_native(SERVICE, "pull_request", "absent")
    child = ResourceKey.document(absent, "document", "body", "real-id")
    declaration = RI.scoped(child, absent, "body", "real-id")
    store.resource(child, REPO, identification=declaration)
    assert store.identification(child) == declaration
    assert not db.execute(
        "SELECT 1 FROM resources WHERE resource_kind='pull_request' AND provider_resource_id=?",
        (absent.provider_resource_id,),
    ).fetchall()
    assert not db.execute("SELECT 1 FROM resource_relations").fetchall()


@pytest.mark.parametrize("already_stored", [False, True])
def test_global_document_cannot_be_reinterpreted_as_scoped_on_insert_or_replay(
    context, already_stored
):
    import json

    db, store, _ = context
    parent = ResourceKey.from_native(SERVICE, "pull_request", "global-shape-test")
    store.resource(parent)
    scoped = ResourceKey.document(parent, "document", "body", "D1")
    if already_stored:
        store.resource(scoped, identification=RI.scoped(scoped, parent, "body", "D1"))
    before = db.execute("SELECT * FROM resources").fetchall()
    native = json.loads(scoped.provider_resource_id)
    for global_key in (
        ResourceKey.global_document(SERVICE, native),
        ResourceKey.from_native(SERVICE, "document", native),
    ):
        assert global_key == scoped
        with pytest.raises(ValueError, match="explicit ResourceIdentification"):
            store.resource(global_key)
        assert db.execute("SELECT * FROM resources").fetchall() == before
    store.resource(scoped, identification=RI.scoped(scoped, parent, "body", "D1"))


def test_text_exact_utf8_content_addressing(context):
    db, store, _ = context
    digest = store.text("é\x00😀")
    assert store.text("é\x00😀") == digest
    assert (
        db.execute(
            "SELECT text_value FROM text_bodies WHERE sha256=?", (digest,)
        ).fetchone()[0]
        == "é\x00😀"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO text_bodies VALUES(?,?)", ("a" * 64, "different body"))


@pytest.mark.parametrize("stamp", [1, (1 << 63) - 1])
def test_epoch_int64_boundaries(context, stamp):
    _, store, _ = context
    assert (
        store.admit_field(candidate("boundary", clock=stamp, observed=stamp))
        == "insert"
    )


@pytest.mark.parametrize("stamp", [True, 1.2, 1 << 63, -(1 << 63) - 1])
def test_epoch_rejects_coercion_and_overflow(stamp):
    with pytest.raises((TypeError, ValueError)):
        candidate("invalid", clock=stamp)


def test_detached_issue_attachment_transfer_preserves_identity_and_original_provenance(
    context,
):
    db, store, _ = context
    key = ResourceKey.from_native(SERVICE, "issue", "detached-transfer")
    store.resource(key, None)
    second = "a1a5dfd6-69a3-4274-bbc7-2e7f6bcd39a4"
    db.execute("INSERT INTO repository_context VALUES(?,?)", (second, "{}"))
    assert store.repository_relations(key) == ()
    original = canonical({"source": "provider.example", "evidence": "attachment-1"})
    moved = canonical({"source": "provider.example", "evidence": "transfer-2"})
    claim1 = ResourceRepositoryRelation(
        key,
        "owning_repository",
        FieldClock("provider.updated_at", 1),
        canonical(REPO),
        original,
        10,
    )
    store.admit_repository_relation(claim1)
    claim2 = ResourceRepositoryRelation(
        key,
        "owning_repository",
        FieldClock("provider.updated_at", 2),
        canonical(second),
        moved,
        20,
    )
    store.admit_repository_relation(claim2)
    current = store.repository_relations(key)
    assert len(current) == 1
    assert current[0].target_repository_uuidv4 == second
    assert current[0].provenance_json == moved and current[0].observed_at_us == 20
    store.resource(key, REPO)
    assert store.repository_relations(key) == current
    assert (
        db.execute(
            "SELECT count(*) FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
            key.coordinates(),
        ).fetchone()[0]
        == 1
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.admit_repository_relation(
            ResourceRepositoryRelation(
                key,
                "owning_repository",
                FieldClock("provider.updated_at", 3),
                canonical("86556e5f-ee55-4f4d-87c1-d30c5e14dff9"),
                moved,
                30,
            )
        )
    assert store.repository_relations(key) == current


def test_missing_provenance_rejected_at_intended_source_evidence_boundary(context):
    db, _, _ = context
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                *KEY.coordinates(),
                "title",
                "null",
                '{"at_us":1,"domain":"provider.updated_at"}',
                "{}",
                1,
            ),
        )
    with pytest.raises(ValueError, match="provenance"):
        FieldCandidate(
            KEY, "title", "null", FieldClock("provider.updated_at", 1), "{}", 1
        )


def test_permanent_context_registered_identities_cannot_be_rebound(context):
    db, _, _ = context
    for sql in [
        "UPDATE repository_context SET repository_uuidv4=?",
        "UPDATE providers SET service_instance_uuidv4=?",
        "UPDATE sources SET source_registration_uuidv4=?",
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql, ("5b020945-03ed-4332-851d-d04726d6dc43",))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE providers SET provider_kind='different-provider'")


def test_raw_sql_source_clock_json_overflow_is_rejected_at_actual_type(context):
    db, _, _ = context
    for clock in [
        '{"at_us":9223372036854775808,"domain":"actual-source"}',
        '{"at_us":-9223372036854775809,"domain":"actual-source"}',
    ]:
        assert db.execute(
            "SELECT json_type(?,'$.at_us'),typeof(json_extract(?,'$.at_us'))",
            (clock, clock),
        ).fetchone() == ("integer", "real")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
                (*KEY.coordinates(), "title", "null", clock, PROVENANCE, 1),
            )


def test_attached_issue_explicit_detach_preserves_null_original_source_and_rollback(
    context,
):
    db, store, _ = context
    claim1 = ResourceRepositoryRelation(
        KEY,
        "owning_repository",
        FieldClock("provider.updated_at", 1),
        canonical(REPO),
        PROVENANCE,
        10,
    )
    store.admit_repository_relation(claim1)
    detached = canonical({"source": "provider.example", "evidence": "detached-20"})
    claim2 = ResourceRepositoryRelation(
        KEY,
        "owning_repository",
        FieldClock("provider.updated_at", 2),
        "null",
        detached,
        20,
    )
    with store.transaction(rollback=True):
        store.admit_repository_relation(claim2)
        assert store.repository_relations(KEY)[0].is_explicit_null_target is True
    assert store.repository_relations(KEY)[0].target_repository_uuidv4 == REPO
    store.admit_repository_relation(claim2)
    current = store.repository_relations(KEY)
    assert len(current) == 1 and current[0].is_explicit_null_target is True
    assert current[0].provenance_json == detached and current[0].observed_at_us == 20
    assert (
        db.execute(
            "SELECT repository_uuidv4 FROM resource_repository_relations",
        ).fetchone()[0]
        is None
    )
    assert (
        store.repository_relations(
            ResourceKey.from_native(SERVICE, "issue", "unobserved")
        )
        == ()
    )
    with pytest.raises(
        ValueError,
        match="field_name='repository_uuidv4' is retired; use repository_relations",
    ):
        store.candidates(KEY, "repository_uuidv4")


def test_exact_text_reference_fk_differs_from_attributed_digest_metadata(context):
    db, store, _ = context
    nonexistent = "a" * 64
    with pytest.raises(sqlite3.IntegrityError):
        store.admit_field(
            FieldCandidate(
                KEY,
                "text_body_sha256",
                canonical(nonexistent),
                FieldClock("provider.updated_at", 1),
                PROVENANCE,
                1,
            )
        )
    assert (
        store.admit_field(
            FieldCandidate(
                KEY,
                "reported_text_sha256",
                canonical(nonexistent),
                FieldClock("provider.updated_at", 1),
                PROVENANCE,
                1,
            )
        )
        == "insert"
    )
    digest = store.text("exact actual UTF8 body")
    assert (
        store.admit_field(
            FieldCandidate(
                KEY,
                "text_body_sha256",
                canonical(digest),
                FieldClock("provider.updated_at", 1),
                PROVENANCE,
                1,
            )
        )
        == "insert"
    )
    assert (
        db.execute(
            "SELECT text_body_sha256 FROM field_candidates WHERE field_name=?",
            ("text_body_sha256",),
        ).fetchone()[0]
        == digest
    )


def test_exact_text_reference_explicit_null_is_distinct_from_missing(context):
    _, store, _ = context
    assert store.candidates(KEY, "text_body_sha256") == ()
    digest = store.text("previous body")
    store.admit_field(
        FieldCandidate(
            KEY,
            "text_body_sha256",
            canonical(digest),
            FieldClock("provider.updated_at", 1),
            PROVENANCE,
            10,
        )
    )
    removed = canonical({"source": "provider.example", "evidence": "body-now-null"})
    store.admit_field(
        FieldCandidate(
            KEY,
            "text_body_sha256",
            "null",
            FieldClock("provider.updated_at", 2),
            removed,
            20,
        )
    )
    current = store.candidates(KEY, "text_body_sha256")
    assert (
        len(current) == 1
        and current[0].value_json == "null"
        and current[0].provenance_json == removed
    )
