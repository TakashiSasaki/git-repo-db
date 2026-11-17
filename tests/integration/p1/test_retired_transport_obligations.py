"""Actual separated primitive, current-field and transport-independent obligations."""

import json
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite import p1_schema as schema
from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageScope,
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_core import CoreFailure, ScalarClaim
from repo_catalog.domain.resource_identification import ResourceIdentification
from tests.integration.p1.test_context import (
    KEY,
    PROVENANCE,
    REPO,
    SERVICE,
    SOURCE,
    p1_grants,
)
from tests.integration.p1.test_core import Budget, core, native, oid, provenance
from tests.support.authorized_context import FixtureContextStore

__all__ = ["core"]


@pytest.fixture
def authority(tmp_path):
    path = tmp_path / "context.sqlite3"
    schema.initialize(path, "context", REPO, str(uuid4()))
    db = schema.connect(path, "context")
    db.execute("INSERT INTO providers VALUES(?,?,?)", (SERVICE, "github", "{}"))
    db.execute("INSERT INTO repository_context VALUES(?,?)", (REPO, "{}"))
    db.execute("INSERT INTO sources VALUES(?,?,?)", (SOURCE, SERVICE, "{}"))
    store = FixtureContextStore(db, p1_grants())
    store.resource(KEY)
    try:
        yield db, store, path
    finally:
        store.close()
        db.close()


def field(name, value, stamp, version, *, key=KEY):
    producer = canonical(
        {
            "source": "actual-field-producer",
            "evidence": {
                "capture": "original-" + version,
                "parser_module": __name__,
                "parser_version": version,
                "field": name,
            },
        }
    )
    return FieldCandidate(
        key,
        name,
        canonical(value),
        FieldClock("provider.updated_at", stamp),
        producer,
        stamp,
    )


@pytest.mark.parametrize("role", schema.STORES)
def test_actual_separated_role_has_no_retired_transport_or_publication_tables(
    tmp_path, role
):
    path = tmp_path / (role + ".sqlite3")
    schema.initialize(path, role, str(uuid4()), str(uuid4()))
    db = schema.connect(path, role)
    try:
        tables = {
            row[1]
            for row in db.execute("PRAGMA table_list")
            if row[1] != "sqlite_schema" and not row[1].startswith("sqlite_")
        }
        assert tables
        assert not tables & {
            "parsed_results",
            "parser_profiles",
            "parser_profile_verifications",
            "fetch_occurrences",
            "source_inputs",
            "publications",
            "git_acquisition_publications",
            "change_request_state",
            "document_state",
            "review_thread_state",
        }
        if role in {"core", "context"}:
            assert not tables & {
                "jobs",
                "job_attempts",
                "cache_locators",
                "active_cache_entries",
                "cache_leases",
                "space_reservations",
                "acquisition_progress",
                "search_documents",
                "incremental_scans",
                "resume_cursors",
                "content_locations",
            }
            assert [
                row[1] for row in db.execute("PRAGMA table_xinfo(coverage_claims)")
            ] == [
                "owner_kind",
                "owner_coordinates_json",
                "observed_at_us",
                "coverage_state",
                "details_json",
            ]
        assert all(
            row[4] == 1 and row[5] == 1
            for row in db.execute("PRAGMA table_list")
            if row[1] in tables
        )
        for table in tables:
            assert all(
                row[5] in {"NO ACTION", "RESTRICT"}
                and row[6] in {"NO ACTION", "RESTRICT"}
                for row in db.execute(f'PRAGMA foreign_key_list("{table}")')
            )
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        db.close()
    assert list(tmp_path.glob("*.sqlite3")) == [path]


@pytest.mark.parametrize(
    "case",
    [
        "sha1-width",
        "sha256-width",
        "type-claim",
        "negative-size-claim",
        "unknown-size-native",
        "boolean-size-native",
        "untrusted-verified",
    ],
)
def test_typed_core_identity_and_native_admission_reject_original_primitive_adversaries(
    core, case
):
    store, path, _ = core
    expected = {
        "sha1-width": "IDENTITY",
        "sha256-width": "IDENTITY",
        "type-claim": "CLAIM",
        "negative-size-claim": "CLAIM",
        "unknown-size-native": "NATIVE_INTEGRITY",
        "boolean-size-native": "NATIVE_INTEGRITY",
        "untrusted-verified": "UNTRUSTED_VERIFICATION",
    }[case]
    with pytest.raises(CoreFailure) as error:
        if case == "sha1-width":
            type(oid())("sha1", "a" * 38)
        elif case == "sha256-width":
            type(oid())("sha256", "a" * 40)
        elif case == "type-claim":
            store.admit_claim(ScalarClaim(oid(), "type", "invented", provenance()))
        elif case == "negative-size-claim":
            store.admit_claim(ScalarClaim(oid(), "size", -1, provenance()))
        elif case in {"unknown-size-native", "boolean-size-native"}:
            value = None if case == "unknown-size-native" else True
            store.admit_metadata(
                replace(native("tree", b""), declared_size=value),
                str(uuid4()),
                Budget(),
            )
        else:
            store.admit_claim(
                ScalarClaim(
                    oid(),
                    "type",
                    "tree",
                    replace(provenance(), qualification="receiver_intrinsic"),
                )
            )
    assert error.value.code == expected
    assert store.sql("SELECT count(*) FROM git_objects")[0][0] == 0
    assert store.sql("SELECT count(*) FROM retained_metadata")[0][0] == 0
    assert not (path.parent / "p1-recovery-stop.json").exists()
    store.admit_claim(ScalarClaim(oid(), "size", None, provenance()))
    assert store.scalar(oid(), "size").alternatives[0]["value"] == ["unknown"]
    assert store.scalar(oid(), "size").canonical is None


@pytest.mark.parametrize(
    "configuration",
    ["[]", "invalid-json", '"scalar"'],
    ids=["array", "broken", "scalar"],
)
def test_source_configuration_shape_is_checked_before_any_registration_write(
    authority, configuration
):
    db, _, _ = authority
    source = str(uuid4())
    before = db.total_changes
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO sources VALUES(?,?,?)", (source, SERVICE, configuration)
        )
    assert db.total_changes == before
    assert db.execute("SELECT count(*) FROM sources").fetchone()[0] == 1
    db.execute("INSERT INTO sources VALUES(?,?,?)", (source, SERVICE, "{}"))
    assert db.execute("SELECT count(*) FROM sources").fetchone()[0] == 2


def test_invented_collection_state_is_rejected_before_authoritative_writes(authority):
    db, store, _ = authority
    db.execute(
        "INSERT INTO collections VALUES(?,?,?,?,?,?)",
        (*KEY.coordinates(), "reviews", PROVENANCE, "{}"),
    )
    scope = CoverageScope.resource(KEY, "reviews")
    store.scope(scope)
    terminal = (*KEY.coordinates(), "reviews", PROVENANCE, 10, "invented", "[]")
    before = db.total_changes
    with pytest.raises(ValueError):
        store.admit_coverage(CoverageClaim(scope, 10, "invented"))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO collection_terminals VALUES(?,?,?,?,?,?,?,?)", terminal)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO coverage_claims VALUES(?,?,?,?,?)",
            (scope.owner_kind, scope.encoded, 10, "invented", None),
        )
    assert db.total_changes == before
    assert db.execute("SELECT count(*) FROM collection_terminals").fetchone()[0] == 0
    assert store.coverage(scope).claims == ()

    partial = (*terminal[:6], "partial", terminal[7])
    db.execute("INSERT INTO collection_terminals VALUES(?,?,?,?,?,?,?,?)", partial)
    claim = CoverageClaim(scope, 10, "partial")
    assert store.admit_coverage(claim) == "insert"
    result = store.coverage(scope)
    assert result.state == "partial" and result.claims == (claim,)
    assert not result.known_empty


def test_current_field_unit_is_visible_before_commit_and_rolls_back_without_publication(
    authority,
):
    db, store, path = authority
    original = field("title", "old", 1, "original")
    store.admit_field(original)
    with pytest.raises(RuntimeError, match="abort actual unit"):
        with store.transaction():
            replacement = field("title", "new", 2, "replacement")
            store.admit_field(replacement)
            assert store.candidates(KEY, "title") == (replacement,)
            assert db.in_transaction
            raise RuntimeError("abort actual unit")
    assert store.candidates(KEY, "title") == (original,)
    assert not db.in_transaction
    assert ContextQueryService(path.parent, mode="context_only").get_context_resource(
        KEY
    ).fields["title"] == (original,)


def test_natural_documents_share_exact_body_without_aliasing_parent_or_identity(
    authority,
):
    db, store, path = authority
    parents = [
        ResourceKey.from_native(SERVICE, "pull_request", number)
        for number in ("10", "11")
    ]
    docs = [
        ResourceKey.document(parent, "review", "review", "same-provider-doc-id")
        for parent in parents
    ]
    for parent, document in zip(parents, docs, strict=True):
        store.resource(parent)
        store.resource(
            document,
            identification=ResourceIdentification.scoped(
                document, parent, "review", "same-provider-doc-id"
            ),
        )
    with pytest.raises(ValueError, match="reconstruct"):
        ResourceIdentification.scoped(
            docs[0], parents[1], "review", "same-provider-doc-id"
        )
    digest = store.text("shared exact body")
    for document in docs:
        store.admit_field(
            FieldCandidate(
                document,
                "text_body_sha256",
                canonical(digest),
                FieldClock("provider", 1),
                PROVENANCE,
                1,
            )
        )
    assert (
        docs[0] != docs[1]
        and docs[0].provider_resource_id != docs[1].provider_resource_id
    )
    assert db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 1
    assert (
        db.execute(
            "SELECT count(*) FROM field_candidates WHERE field_name='text_body_sha256'"
        ).fetchone()[0]
        == 2
    )
    reader = ContextQueryService(path.parent, mode="context_only")
    for parent, document in zip(parents, docs, strict=True):
        view = reader.get_context_resource(document)
        assert view.identifier_namespace == parent
        assert view.provider_document_id == canonical("same-provider-doc-id")
        assert view.resolved_texts[digest] == "shared exact body"
        assert not view.relations


def test_sparse_field_updates_preserve_each_actual_original_producer_and_clock(
    authority,
):
    _, store, path = authority
    first_body = store.text("first body")
    second_body = store.text("second body")
    older_body = store.text("older body")
    first = [
        field(name, value, 10, "1")
        for name, value in [
            ("title", "original title"),
            ("text_body_sha256", first_body),
            ("author", "first author"),
        ]
    ]
    for claim in first:
        store.admit_field(claim)
    second = field("text_body_sha256", second_body, 20, "2")
    store.admit_field(second)
    for name, value in [
        ("title", "older title"),
        ("text_body_sha256", older_body),
        ("author", None),
        ("url", "https://synthetic.invalid/original"),
    ]:
        store.admit_field(field(name, value, 5, "99"))
    expected = {
        "title": first[0],
        "author": first[2],
        "text_body_sha256": second,
        "url": field("url", "https://synthetic.invalid/original", 5, "99"),
    }
    view = ContextQueryService(path.parent, mode="context_only").get_context_resource(
        KEY
    )
    assert view.fields == {name: (claim,) for name, claim in expected.items()}
    for name, claims in view.fields.items():
        evidence = json.loads(claims[0].provenance_json)["evidence"]
        assert evidence["parser_version"] == (
            "2" if name == "text_body_sha256" else "99" if name == "url" else "1"
        )
        assert claims[0].clock.at_us == (
            20 if name == "text_body_sha256" else 5 if name == "url" else 10
        )


def test_explicit_null_survives_a_later_omission_with_original_field_evidence(
    authority,
):
    _, store, path = authority
    digest = store.text("initial body")
    for name, value in (
        ("title", "initial"),
        ("text_body_sha256", digest),
        ("author", "initial"),
    ):
        store.admit_field(field(name, value, 10, "1"))
    missing_null = [
        field(name, None, 20, "2") for name in ("text_body_sha256", "author")
    ]
    for claim in missing_null:
        store.admit_field(claim)
    later = field("title", "new title", 30, "3")
    store.admit_field(later)
    view = ContextQueryService(path.parent, mode="context_only").get_context_resource(
        KEY
    )
    assert view.fields["title"] == (later,)
    for claim in missing_null:
        assert view.fields[claim.field_name] == (claim,)
        assert view.fields[claim.field_name][0].value_json == "null"


@pytest.mark.parametrize("version", ["0.1", "100000.0", "zzz"])
def test_parser_version_never_resolves_equal_clock_field_conflict(authority, version):
    _, store, path = authority
    first = field("text_body_sha256", store.text("first body"), 10, "1")
    other = field("text_body_sha256", store.text("contradictory body"), 10, version)
    store.admit_field(first)
    store.admit_field(other)
    reader = ContextQueryService(path.parent, mode="context_only")
    assert set(reader.get_context_resource(KEY).fields["text_body_sha256"]) == {
        first,
        other,
    }
    resolved = field("text_body_sha256", store.text("provider resolved"), 11, "0")
    store.admit_field(resolved)
    assert reader.get_context_resource(KEY).fields["text_body_sha256"] == (resolved,)


def test_equal_field_values_keep_distinct_original_producers_without_false_conflict(
    authority,
):
    _, store, path = authority
    digest = store.text("same domain value")
    first = field("text_body_sha256", digest, 10, "1")
    other = field("text_body_sha256", digest, 10, "99")
    store.admit_field(first)
    store.admit_field(other)
    claims = (
        ContextQueryService(path.parent, mode="context_only")
        .get_context_resource(KEY)
        .fields["text_body_sha256"]
    )
    assert set(claims) == {first, other}
    assert {claim.value_json for claim in claims} == {canonical(digest)}


@pytest.mark.parametrize("kind", ["issue", "review"])
@pytest.mark.parametrize("layer", ["clock", "provenance"])
def test_supported_field_envelopes_cannot_resurrect_legacy_authority_or_cross_owner_pointer(
    authority, kind, layer
):
    db, store, path = authority
    if kind == "issue":
        key = KEY
    else:
        parent = ResourceKey.from_native(SERVICE, "pull_request", "10")
        key = ResourceKey.document(parent, "review", "review", "same-provider-doc-id")
        store.resource(parent)
        store.resource(
            key,
            identification=ResourceIdentification.scoped(
                key, parent, "review", "same-provider-doc-id"
            ),
        )
    original = field("title", "original value", 1, "original", key=key)
    store.admit_field(original)
    extras = [
        {"parser_profile_uuidv4": "00000000-0000-4000-8000-000000000001"},
        {"parsed_result_uuidv4": "00000000-0000-4000-8000-000000000001"},
        {"fetch_occurrence_uuidv4": "00000000-0000-4000-8000-000000000001"},
        {"payload": {"representation": "decoded_api", "sha256": "0" * 64}},
        {"unrecognized_owner_uuidv4": "00000000-0000-4000-8000-000000000001"},
        {"repository_binding_id": "foreign-binding"},
    ]
    expected = {original}
    declaration = store.identification(key)
    for index, extra in enumerate(extras):
        before = db.total_changes
        clock_json = canonical({"domain": "provider.updated_at", "at_us": 2, **extra})
        if layer == "clock":
            with pytest.raises(ValueError):
                clock = FieldClock.from_json(clock_json)
                attempted = FieldCandidate(
                    key,
                    "title",
                    canonical("poison"),
                    clock,
                    original.provenance_json,
                    2,
                )
                store.admit_field(attempted)
            # The currently supported clock envelope also has an actual closed
            # SQL CHECK; opaque source-evidence contents are not dereferenced.
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        *key.coordinates(),
                        "title",
                        canonical("poison"),
                        clock_json,
                        original.provenance_json,
                        2,
                    ),
                )
            assert db.total_changes == before
        else:
            # General field provenance intentionally preserves opaque source
            # annotations. They cannot select an owner, verify a value or refer
            # to a resurrected parser/transport store merely by naming an ID.
            annotated = replace(
                original,
                provenance_json=canonical(
                    {
                        "source": "actual-field-producer",
                        "evidence": f"annotation-{index}",
                        **extra,
                    }
                ),
            )
            assert store.admit_field(annotated) == "insert"
            expected.add(annotated)
        view = ContextQueryService(
            path.parent, mode="context_only"
        ).get_context_resource(key)
        assert set(view.fields["title"]) == expected
        assert {claim.value_json for claim in view.fields["title"]} == {
            original.value_json
        }
        assert view.resource == key and view.identification == declaration
        assert view.repository_uuidv4 is None and not view.repository_relations
    alternative = field("title", "equal-clock alternative", 1, "unranked", key=key)
    store.admit_field(alternative)
    assert set(
        ContextQueryService(path.parent, mode="context_only")
        .get_context_resource(key)
        .fields["title"]
    ) == expected | {alternative}
