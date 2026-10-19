"""Real durable SQLite production Context, including P1 review adversaries."""

import json
import sqlite3
from dataclasses import replace

import pytest

from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageScope,
    FieldCandidate,
    FieldClock,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_coordination import AdmissionFailure, CoordinationError
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.production_context import (
    CollectionObservation,
    ContextError,
    CoreReference,
    ResourceObservation,
    ResourceRelation,
    SourceInventory,
)
from tests.integration.p1 import test_context as p1_contract

REPO = p1_contract.REPO
SERVICE = p1_contract.SERVICE
SOURCE = p1_contract.SOURCE
KEY = p1_contract.KEY
PROVENANCE = p1_contract.PROVENANCE
INSTANCE = "49a14b65-20b1-48b3-a021-c2970247e95c"
OTHER_SERVICE = "6eb0350d-95e0-479d-ac57-f0f3b68ced2c"
OTHER_REPO = "22307f0c-6d1e-41da-b2fb-c4c11362e7d2"
PR = ResourceKey(SERVICE, "pull_request", "pr-7")


@pytest.fixture
def directory(tmp_path):
    initialize(tmp_path / "context.sqlite3", "context", REPO, INSTANCE)
    return tmp_path


@pytest.fixture
def context(directory):
    try:
        with Context.transaction(directory) as store:
            store.provider(SERVICE, "github", canonical({"name": "GitHub service"}))
            store.repository(REPO)
            store.source(SOURCE, SERVICE)
            store.resource(KEY)
            yield store.db, store, directory / "context.sqlite3"
    except CoordinationError as error:
        if (
            error.code != "RECOVERY_REQUIRED"
            or not (directory / "p1-recovery-stop.json").exists()
        ):
            raise


def field(
    key=KEY,
    name="title",
    value="value",
    clock=1,
    domain="provider.updated_at",
    evidence="event-7",
    observed=10,
):
    return FieldCandidate(
        key,
        name,
        canonical(value),
        FieldClock(domain, clock),
        canonical({"source": "provider.example", "evidence": evidence}),
        observed,
    )


def collection(
    key=KEY,
    *,
    provenance=PROVENANCE,
    scope=None,
    stamp=10,
    state="complete",
    members=(),
    kind="reviews",
):
    return CollectionObservation(
        key,
        kind,
        provenance,
        canonical(scope or {"coverage_kind": kind}),
        stamp,
        state,
        members,
    )


def claim_for(observation, stamp=None, state="complete"):
    return CoverageClaim(
        CoverageScope.collection(
            observation.resource,
            observation.collection_kind,
            observation.provenance_json,
            observation.collection_kind,
        ),
        observation.observed_at_us if stamp is None else stamp,
        state,
    )


@pytest.mark.parametrize(
    "scenario",
    [
        p1_contract.test_missing_differs_from_explicit_null,
        p1_contract.test_current_candidates_preserve_equal_and_incomparable,
        p1_contract.test_exact_original_replay_does_not_rewrite_provenance,
        p1_contract.test_generated_source_clock_is_real_sqlite_value,
        p1_contract.test_portable_core_reference_validated_and_no_sender_promotion,
        p1_contract.test_source_membership_cannot_be_removed_or_rebound,
        p1_contract.test_source_empty_inventory_is_durable_without_any_membership,
        p1_contract.test_children_have_real_parent_and_document_kind_coordinates,
        p1_contract.test_text_exact_utf8_content_addressing,
        p1_contract.test_detached_issue_attachment_transfer_preserves_identity_and_original_provenance,
        p1_contract.test_missing_provenance_rejected_at_intended_source_evidence_boundary,
        p1_contract.test_permanent_context_registered_identities_cannot_be_rebound,
        p1_contract.test_raw_sql_source_clock_json_overflow_is_rejected_at_actual_type,
        p1_contract.test_exact_text_reference_fk_differs_from_attributed_digest_metadata,
        p1_contract.test_exact_text_reference_explicit_null_is_distinct_from_missing,
    ],
    ids=lambda test: test.__name__,
)
def test_p1_contract_on_actual_production_adapter(context, scenario):
    scenario(context)


def test_provider_source_registration_and_configuration(context):
    db, store, _ = context
    store.provider(
        SERVICE,
        "github",
        canonical({"name": "Renamed service", "evidence": "config-v2"}),
    )
    store.source(
        SOURCE,
        SERVICE,
        canonical({"discovery_kind": "github_inventory", "evidence": "owner-settings"}),
    )
    store.provider(OTHER_SERVICE, "gitlab")
    with pytest.raises(ContextError, match="IDENTITY_REBIND"):
        store.provider(SERVICE, "gitlab")
    with pytest.raises(ContextError, match="IDENTITY_REBIND"):
        store.source(SOURCE, OTHER_SERVICE)
    assert (
        json.loads(
            db.execute(
                "SELECT configuration_json FROM providers WHERE service_instance_uuidv4=?",
                (SERVICE,),
            ).fetchone()[0]
        )["evidence"]
        == "config-v2"
    )
    assert db.execute("SELECT service_instance_uuidv4 FROM sources").fetchone() == (
        SERVICE,
    )


def test_coreless_durable_context_and_derivative_loss(directory):
    with Context.transaction(directory) as store:
        store.provider(SERVICE, "github")
        store.resource(KEY)
        store.admit_field(field())
    for role in ("operational", "search"):
        initialize(directory / f"{role}.sqlite3", role, REPO, INSTANCE)
        (directory / f"{role}.sqlite3").unlink()
    with Context.snapshot(directory) as store:
        assert store.candidates(KEY, "title") == (field(),)
        assert store.resources(kind="issue") == (KEY,)
    assert not (directory / "core.sqlite3").exists()
    assert not (directory / "operational.sqlite3").exists()


def test_observe_failure_rolls_back_new_identity_and_all_fields(context):
    _, store, _ = context
    resource = ResourceKey(SERVICE, "issue", "atomic")
    good = field(resource)
    bad = field(resource, name="text_body_sha256", value="0" * 64)
    with pytest.raises(sqlite3.IntegrityError):
        store.observe(ResourceObservation(resource, (good, bad)))
    assert resource not in store.resources()
    assert store.candidates(resource, "title") == ()
    assert store.observe(ResourceObservation(resource, (good,))) == ("insert",)


def test_outer_transaction_rolls_back_resource_fields_and_text(directory):
    with pytest.raises(RuntimeError):
        with Context.transaction(directory) as store:
            store.provider(SERVICE, "github")
            store.observe(ResourceObservation(KEY, (field(),)))
            store.admit_text(KEY, "exact text", FieldClock("source", 1), PROVENANCE, 10)
            raise RuntimeError("interrupt")
    with Context.snapshot(directory) as store:
        assert store.resources() == ()
        assert store.db.execute("SELECT count(*) FROM text_bodies").fetchone() == (0,)


def test_current_fields_scale_not_full_edit_history(context):
    db, store, _ = context
    for stamp in range(1, 1001):
        store.admit_field(
            field(
                value=f"value-{stamp}",
                clock=stamp,
                observed=stamp,
                evidence=f"event-{stamp}",
            )
        )
    assert len(store.candidates(KEY, "title")) == 1
    assert db.execute("SELECT count(*) FROM field_candidates").fetchone() == (1,)
    assert store.admit_field(field(value="late old", clock=10)) == "stale"


def test_field_specific_inheritance_preserves_original_alternatives(context):
    _, store, _ = context
    store.resource(PR)
    review = ResourceKey.document(PR, "review", "approval", "7")
    store.resource(review)
    original = field(PR, evidence="original", observed=70)
    other = field(PR, value="competing", domain="another-source", observed=30)
    for candidate in (original, other, field(PR, name="secret", value="not inherited")):
        store.admit_field(candidate)
    assert store.inherit_fields(PR, review, ("title", "unobserved")) == (
        "insert",
        "insert",
    )
    copied = store.candidates(review, "title")
    assert {
        (c.value_json, c.clock, c.provenance_json, c.observed_at_us) for c in copied
    } == {
        (c.value_json, c.clock, c.provenance_json, c.observed_at_us)
        for c in (original, other)
    }
    assert store.candidates(review, "secret") == ()
    wrong = ResourceKey(SERVICE, "pull_request", "other")
    store.resource(wrong)
    with pytest.raises(ContextError, match="INHERITANCE_OWNER"):
        store.inherit_fields(wrong, review, ("title",))


def test_document_child_ownership_and_relationship_roundtrip(context):
    _, store, _ = context
    store.resource(PR)
    review = ResourceKey.document(PR, "review", "review", "same-id")
    thread = ResourceKey.document(review, "thread", "review-thread", "same-id")
    comment = ResourceKey.document(thread, "comment", "comment", "same-id")
    document = ResourceKey.document(PR, "document", "description", "same-id")
    for resource in (review, thread, comment, document):
        store.resource(resource)
    relation = ResourceRelation(PR, "reviews", (review,), PROVENANCE, "{}", 10)
    assert store.relation(relation) == "insert"
    assert store.relation(relation) == "duplicate"
    assert store.relations(PR, "reviews") == (relation,)
    with pytest.raises(ContextError, match="EVIDENCE_REBIND"):
        store.relation(replace(relation, observed_at_us=11))
    assert store.relation(replace(relation, members=())) == "insert"
    assert len(store.relations(PR, "reviews")) == 2
    with pytest.raises(ContextError, match="RESOURCE_UNAVAILABLE"):
        store.relation(
            replace(relation, members=(ResourceKey(SERVICE, "issue", "absent"),))
        )


def test_text_exact_null_and_failed_reference_unit(context):
    db, store, _ = context
    content = "é\x00😀\r\nbody"
    assert (
        store.admit_text(KEY, content, FieldClock("source", 1), PROVENANCE, 10)
        == "insert"
    )
    digest = json.loads(store.candidates(KEY, "text_body_sha256")[0].value_json)
    assert store.read_text(digest) == content
    before = db.execute("SELECT count(*) FROM text_bodies").fetchone()
    with pytest.raises(sqlite3.IntegrityError):
        store.admit_text(
            ResourceKey(SERVICE, "issue", "absent"),
            "rolled back text",
            FieldClock("source", 1),
            PROVENANCE,
            10,
        )
    assert db.execute("SELECT count(*) FROM text_bodies").fetchone() == before
    store.admit_text(KEY, None, FieldClock("source", 2), PROVENANCE, 11)
    assert store.candidates(KEY, "text_body_sha256")[0].value_json == "null"
    assert store.read_text(digest) == content


def test_source_inventory_positive_preservation_reverse_replay(context):
    _, store, _ = context
    store.repository(OTHER_REPO)
    scope = canonical(
        {"coverage_kind": "repositories", "service_instance_uuidv4": SERVICE}
    )
    original = SourceInventory(
        SOURCE, scope, 10, "partial", False, (REPO, OTHER_REPO), PROVENANCE
    )
    store.inventory(original)
    store.inventory(replace(original, repositories=(OTHER_REPO, REPO)))
    empty = replace(
        original, observed_at_us=20, state="complete", terminal=True, repositories=()
    )
    store.inventory(empty)
    claim = CoverageClaim(
        CoverageScope.source_inventory(SOURCE, scope, "repositories"), 20, "complete"
    )
    store.prove_inventory(claim, empty)
    assert store.coverage(claim.scope).known_empty
    assert set(store.source_repositories(SOURCE)) == {REPO, OTHER_REPO}
    store.inventory(original)
    assert store.coverage(claim.scope).known_empty
    latest = replace(empty, observed_at_us=21, state="partial", terminal=False)
    store.inventory(latest)
    assert store.coverage(claim.scope).state == "unknown"
    assert set(store.source_repositories(SOURCE)) == {REPO, OTHER_REPO}


def test_source_inventory_empty_foreign_service_rejected(context):
    _, store, _ = context
    observation = SourceInventory(
        SOURCE,
        canonical({"service_instance_uuidv4": OTHER_SERVICE}),
        10,
        "complete",
        True,
        (),
        PROVENANCE,
    )
    with pytest.raises(ContextError, match="SOURCE_SERVICE"):
        store.inventory(observation)
    assert store.db.execute(
        "SELECT count(*) FROM source_inventory_evidence"
    ).fetchone() == (0,)


def test_inventory_atomic_rollback_unknown_repository(context):
    _, store, _ = context
    observation = SourceInventory(
        SOURCE, "{}", 10, "partial", False, (REPO, OTHER_REPO), PROVENANCE
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.inventory(observation)
    assert store.source_repositories(SOURCE) == ()
    assert store.db.execute(
        "SELECT count(*) FROM source_inventory_evidence"
    ).fetchone() == (0,)


def test_coverage_five_physical_columns_and_advisory_identity(context):
    db, store, _ = context
    assert [row[1] for row in db.execute("PRAGMA table_xinfo(coverage_claims)")] == [
        "owner_kind",
        "owner_coordinates_json",
        "observed_at_us",
        "coverage_state",
        "details_json",
    ]
    scope = CoverageScope.resource(KEY, "comments")
    store.scope(scope)
    assert (
        store.admit_coverage(CoverageClaim(scope, 10, "partial", '{"detail":"a"}'))
        == "insert"
    )
    assert (
        store.admit_coverage(CoverageClaim(scope, 10, "partial", '{"detail":"b"}'))
        == "duplicate"
    )
    assert store.admit_coverage(CoverageClaim(scope, 11, "unknown")) == "insert"
    assert store.coverage(scope).state == "unknown"
    assert store.admit_coverage(CoverageClaim(scope, 9, "complete")) == "stale"
    store.admit_coverage(CoverageClaim(scope, 11, "partial"))
    store.admit_coverage(CoverageClaim(scope, 11, "complete"))
    assert store.coverage(scope).state == "conflict"


def test_collection_known_empty_requires_genuine_terminal_proof(context):
    _, store, _ = context
    observation = collection()
    claim = claim_for(observation)
    store.collection(observation)
    store.scope(claim.scope)
    store.admit_coverage(claim)
    assert store.coverage(claim.scope).state == "unknown"
    store.prove_collection(
        claim, observation, required_scope_json=observation.scope_json
    )
    assert store.coverage(claim.scope).known_empty


def test_latest_partial_and_same_time_terminal_conflict_do_not_borrow_complete(context):
    _, store, _ = context
    observation = collection()
    claim = claim_for(observation)
    store.collection(observation)
    store.prove_collection(
        claim, observation, required_scope_json=observation.scope_json
    )
    store.collection(replace(observation, observed_at_us=11, state="partial"))
    assert store.coverage(claim.scope).state == "unknown"
    store.collection(replace(observation, observed_at_us=11))
    assert store.coverage(claim.scope).state == "conflict"
    with pytest.raises(sqlite3.IntegrityError, match="superseded or conflicting"):
        store.prove_collection(
            claim_for(observation, stamp=12),
            observation,
            required_scope_json=observation.scope_json,
        )


@pytest.mark.parametrize("wrong_owner", ["kind", "resource", "field", "source"])
def test_p1_review_scope_mismatch_not_complete_in_production(context, wrong_owner):
    _, store, _ = context
    store.associate_source(SOURCE, REPO)
    observation = collection(
        scope={
            "coverage_kind": "reviews",
            "repository_uuidv4": REPO,
            "source_registration_uuidv4": SOURCE,
        }
    )
    store.collection(observation)
    scopes = {
        "kind": CoverageScope.resource(KEY, "all-notes"),
        "resource": CoverageScope.resource(
            ResourceKey(SERVICE, "issue", "other"), "reviews"
        ),
        "field": CoverageScope.field(KEY, "title", "reviews"),
        "source": CoverageScope.source(SOURCE, REPO, "all-notes"),
    }
    store.resource(ResourceKey(SERVICE, "issue", "other"))
    claim = CoverageClaim(scopes[wrong_owner], 10, "complete")
    with pytest.raises(sqlite3.IntegrityError, match="owner mismatch"):
        store.prove_collection(
            claim, observation, required_scope_json=observation.scope_json
        )
    assert store.coverage(claim.scope).state == "unknown"


@pytest.mark.parametrize("changed", ["head", "base", "child"])
def test_exact_head_base_nested_scope_cannot_move(context, changed):
    _, store, _ = context
    exact = {
        "coverage_kind": "reviews",
        "head": ["sha1", "a" * 40],
        "base": ["sha256", "b" * 64],
        "child": ["thread", "real-thread"],
    }
    observation = collection(scope=exact)
    claim = claim_for(observation)
    store.collection(observation)
    store.prove_collection(
        claim, observation, required_scope_json=observation.scope_json
    )
    assert store.collection_coverage(
        KEY,
        "reviews",
        PROVENANCE,
        "reviews",
        required_scope_json=observation.scope_json,
    ).known_empty
    changed_scope = canonical({**exact, changed: "different"})
    with pytest.raises(ContextError, match="PROOF_SCOPE"):
        store.collection_coverage(
            KEY, "reviews", PROVENANCE, "reviews", required_scope_json=changed_scope
        )
    with pytest.raises(ContextError, match="EVIDENCE_REBIND"):
        store.collection(replace(observation, scope_json=changed_scope))
    with pytest.raises(ContextError, match="PROOF_SCOPE"):
        store.prove_collection(claim, observation, required_scope_json=changed_scope)


def test_source_collection_cross_service_rejected_even_empty(context):
    _, store, _ = context
    store.provider(OTHER_SERVICE, "gitlab")
    foreign = ResourceKey(OTHER_SERVICE, "issue", "foreign")
    store.resource(foreign)
    observation = collection(key=foreign, scope={"source_registration_uuidv4": SOURCE})
    with pytest.raises(ContextError, match="SOURCE_SERVICE"):
        store.collection(observation)


@pytest.mark.parametrize(
    "object_format,full_oid", [("sha1", "a" * 40), ("sha256", "b" * 64)]
)
def test_unavailable_portable_core_reference_durable_and_honest(
    context, object_format, full_oid
):
    _, store, _ = context
    reference = CoreReference(KEY, "head", OID(object_format, full_oid), PROVENANCE)
    store.report_core_reference(
        reference, clock=FieldClock("provider.updated_at", 1), observed_at_us=10
    )
    assert store.core_dependencies(KEY)[0].available is False
    assert store.core_dependencies(KEY)[0].reference == reference
    assert store.core_dependencies(
        KEY, lambda fmt, oid: (fmt, oid) == (object_format, full_oid)
    )[0].available


def test_missing_core_dependency_rejects_certified_pair(directory):
    initialize(directory / "core.sqlite3", "core", REPO, INSTANCE)
    coordinator = PairCoordinator(directory)

    def context_unit(db):
        with Context.for_transaction(db, directory) as store:
            store.provider(SERVICE, "github")
            store.resource(KEY)
            store.link_core(KEY, "head", "sha1", "a" * 40, PROVENANCE, lambda *_: True)

    with pytest.raises(AdmissionFailure) as error:
        coordinator.admit(lambda db: None, context_unit)
    assert error.value.outcome.core_committed
    assert not error.value.outcome.context_committed
    with Context.snapshot(directory) as store:
        assert store.resources() == ()


def test_paired_read_context_projection_no_savepoint_escape(directory):
    initialize(directory / "core.sqlite3", "core", REPO, INSTANCE)
    coordinator = PairCoordinator(directory)

    def context_unit(db):
        with Context.for_transaction(db, directory) as store:
            store.provider(SERVICE, "github")
            store.resource(KEY)
            observation = collection()
            store.collection(observation)
            store.prove_collection(
                claim_for(observation),
                observation,
                required_scope_json=observation.scope_json,
            )

    coordinator.admit(lambda db: None, context_unit)
    with coordinator.snapshots() as pair:
        with Context.for_snapshot(pair.context, directory) as store:
            assert store.coverage(claim_for(collection()).scope).known_empty
            with pytest.raises(ContextError, match="READ_ONLY"):
                store.text("forbidden write")
    with pytest.raises(ContextError, match="CAPABILITY_EXPIRED"):
        store.candidates(KEY, "title")


@pytest.mark.parametrize("entry", ["transaction", "snapshot"])
def test_corrupt_context_open_persists_stop(directory, entry):
    (directory / "context.sqlite3").write_bytes(b"not a sqlite database")
    with pytest.raises(sqlite3.DatabaseError):
        with getattr(Context, entry)(directory):
            pytest.fail("corruption admitted")
    assert (directory / "p1-recovery-stop.json").exists()
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        with Context.transaction(directory):
            pass


@pytest.mark.parametrize("operation", ["read", "replay"])
def test_retained_context_text_corruption_stops_before_unwind(directory, operation):
    with Context.transaction(directory) as store:
        digest = store.text("actual text")
    db = connect(directory / "context.sqlite3", "context")
    trigger = db.execute(
        "SELECT sql FROM sqlite_schema WHERE name='text_bodies_no_update'"
    ).fetchone()[0]
    db.execute("DROP TRIGGER text_bodies_no_update")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute("UPDATE text_bodies SET text_value=?", ("bad copy",))
    db.execute("PRAGMA ignore_check_constraints=OFF")
    db.execute(trigger)
    db.close()
    with pytest.raises(ContextError, match="AUTHORITATIVE_CORRUPTION"):
        with Context.transaction(directory) as store:
            if operation == "read":
                store.read_text(digest)
            else:
                store.text("actual text")
    assert (directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "operation", ["text", "field", "coverage", "resource", "candidates", "link"]
)
def test_all_inherited_methods_obey_stop(context, operation):
    _, store, path = context
    PairCoordinator(path.parent).stop("test stop")
    calls = {
        "text": lambda: store.text("not admitted"),
        "field": lambda: store.admit_field(field()),
        "coverage": lambda: store.coverage(CoverageScope.resource(KEY, "reviews")),
        "resource": lambda: store.resource(PR),
        "candidates": lambda: store.candidates(KEY, "title"),
        "link": lambda: store.link_core(
            KEY, "head", "sha1", "a" * 40, PROVENANCE, lambda *_: True
        ),
    }
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        calls[operation]()


def test_capability_expired_and_outer_transaction_required(directory):
    with Context.transaction(directory) as store:
        store.provider(SERVICE, "github")
    with pytest.raises(ContextError, match="CAPABILITY_EXPIRED"):
        store.provider(SERVICE, "github")
    db = connect(directory / "context.sqlite3", "context")
    try:
        with pytest.raises(ContextError, match="TRANSACTION_REQUIRED"):
            with Context.for_transaction(db, directory):
                pass
    finally:
        db.close()


def test_invalid_input_does_not_catalog_stop(context):
    _, store, path = context
    with pytest.raises(sqlite3.IntegrityError):
        store.resource(ResourceKey(SERVICE, "ordinary_file", "file"))
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert not hasattr(store, "retain_blob")


def test_forged_unpersisted_head_scope_cannot_create_proof(context):
    _, store, _ = context
    observation = collection(
        scope={"head": ["sha1", "a" * 40], "coverage_kind": "reviews"}
    )
    store.collection(observation)
    forged = replace(
        observation,
        scope_json=canonical({"head": ["sha1", "b" * 40], "coverage_kind": "reviews"}),
    )
    with pytest.raises(ContextError, match="PROOF_SCOPE"):
        store.prove_collection(
            claim_for(forged), forged, required_scope_json=forged.scope_json
        )
    assert store.coverage(claim_for(observation).scope).state == "unknown"
    assert store.db.execute("SELECT count(*) FROM coverage_proofs").fetchone() == (0,)


def test_missing_attributed_reference_does_not_poison_sound_pair(directory):
    initialize(directory / "core.sqlite3", "core", REPO, INSTANCE)
    reference = CoreReference(KEY, "head", OID("sha1", "a" * 40), PROVENANCE)
    with Context.transaction(directory) as store:
        store.provider(SERVICE, "github")
        store.resource(KEY)
        store.report_core_reference(
            reference, clock=FieldClock("provider.updated_at", 7), observed_at_us=20
        )
    with PairCoordinator(directory).snapshots() as pair:
        with Context.for_snapshot(pair.context, directory) as store:
            (dependency,) = store.core_dependencies(KEY)
            assert not dependency.available and not dependency.required
            assert dependency.candidate.clock == FieldClock("provider.updated_at", 7)
            assert dependency.candidate.observed_at_us == 20
    assert not (directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("deferred", [False, True])
def test_swallowed_sqlite_corruption_stops_immediately(directory, deferred):
    """Fault injection models execute and deferred row-step SQLite failures."""
    db = connect(directory / "context.sqlite3", "context")
    db.execute("BEGIN")
    error = sqlite3.DatabaseError("injected SQLite corruption")
    error.sqlite_errorcode = sqlite3.SQLITE_CORRUPT

    class FaultCursor:
        def fetchone(self):
            raise error

    class FaultConnection:
        in_transaction = True

        def execute(self, sql, parameters=()):
            # The capability now validates registration rows during binding.
            # Arm the fault only for the subsequent read_text operation, retaining
            # the original swallowed/deferred-corruption assertions below.
            if sql in {
                "SELECT store_role FROM store_identity",
                "SELECT name, sql FROM sqlite_schema WHERE type='table' AND name IN ('resource_repository_relations', 'repository_mapping_dispositions', 'field_candidates')",
                "SELECT configuration_json FROM providers",
                "SELECT configuration_json FROM repository_context",
                "SELECT configuration_json FROM sources",
                "SELECT attributes_json FROM source_repositories",
            }:
                return db.execute(sql, parameters)
            if deferred:
                return FaultCursor()
            raise error

    try:
        with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
            with Context.for_transaction(FaultConnection(), directory) as store:
                with pytest.raises(sqlite3.DatabaseError):
                    store.read_text("a" * 64)
                assert (directory / "p1-recovery-stop.json").exists()
                with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
                    store.provider(SERVICE, "github")
    finally:
        db.rollback()
        db.close()


@pytest.mark.parametrize("method", ["relation", "collection"])
def test_foreign_parent_child_cannot_be_collection_members(context, method):
    _, store, _ = context
    store.resource(PR)
    other = ResourceKey(SERVICE, "pull_request", "other")
    store.resource(other)
    child = ResourceKey.document(other, "review", "review", "7")
    store.resource(child)
    observation = collection(key=PR, members=(child,))
    with pytest.raises(ContextError, match="MEMBER_OWNER"):
        if method == "collection":
            store.collection(observation)
        else:
            store.relation(
                ResourceRelation(PR, "reviews", (child,), PROVENANCE, "{}", 10)
            )


def test_invalid_stored_field_is_corruption_not_bad_incoming_data(directory):
    with Context.transaction(directory) as store:
        store.provider(SERVICE, "github")
        store.observe(ResourceObservation(KEY, (field(),)))
    db = connect(directory / "context.sqlite3", "context")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute("UPDATE field_candidates SET provenance_json='not-json'")
    db.close()
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        with Context.snapshot(directory) as store:
            with pytest.raises(ContextError, match="AUTHORITATIVE_CORRUPTION"):
                store.candidates(KEY, "title")
            assert (directory / "p1-recovery-stop.json").exists()


def test_reserved_reference_field_requires_typed_identity(context):
    _, store, path = context
    with pytest.raises(ContextError, match="REFERENCE_VALUE"):
        store.admit_field(field(name="reported_core_reference:head", value="false OID"))
    assert not (path.parent / "p1-recovery-stop.json").exists()


def test_invalid_utf8_retained_text_stops_on_selected_bytes(directory):
    with Context.transaction(directory) as store:
        digest = store.text("valid original text")
    db = connect(directory / "context.sqlite3", "context")
    trigger = db.execute(
        "SELECT sql FROM sqlite_schema WHERE name='text_bodies_no_update'"
    ).fetchone()[0]
    db.execute("DROP TRIGGER text_bodies_no_update")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute("UPDATE text_bodies SET text_value=CAST(X'80' AS TEXT)")
    db.execute(trigger)
    db.close()
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        with Context.snapshot(directory) as store:
            with pytest.raises(ContextError, match="AUTHORITATIVE_CORRUPTION"):
                store.read_text(digest)
            assert (directory / "p1-recovery-stop.json").exists()


def test_explicit_null_detach_rollback_and_restart(directory):
    original = canonical({"source": "provider", "evidence": "attachment"})
    detached = canonical({"source": "provider", "evidence": "detachment"})
    with Context.transaction(directory) as store:
        store.provider(SERVICE, "github")
        store.repository(REPO)
        store.resource(KEY)
        store.admit_repository_relation(
            ResourceRepositoryRelation(
                KEY, "owning_repository", FieldClock("provider.updated_at", 1), canonical(REPO), original, 10
            )
        )
    with pytest.raises(RuntimeError):
        with Context.transaction(directory) as store:
            store.admit_repository_relation(
                ResourceRepositoryRelation(
                    KEY, "owning_repository", FieldClock("provider.updated_at", 2), "null", detached, 20
                )
            )
            assert store.repository_relations(KEY)[0].is_explicit_null_target is True
            raise RuntimeError("rollback")
    with Context.snapshot(directory) as store:
        assert store.repository_relations(KEY)[0].target_repository_uuidv4 == REPO
    with Context.transaction(directory) as store:
        store.admit_repository_relation(
            ResourceRepositoryRelation(
                KEY, "owning_repository", FieldClock("provider.updated_at", 2), "null", detached, 20
            )
        )
    with Context.snapshot(directory) as store:
        (relation,) = store.repository_relations(KEY)
        assert relation.is_explicit_null_target is True
        assert relation.provenance_json == detached and relation.observed_at_us == 20
        assert store.resources(kind="issue") == (KEY,)


def test_same_time_source_terminal_conflicts_preserved(context):
    _, store, _ = context
    scope_json = canonical({"coverage_kind": "inventory"})
    observation = SourceInventory(
        SOURCE, scope_json, 10, "complete", True, (), PROVENANCE
    )
    claim = CoverageClaim(
        CoverageScope.source_inventory(SOURCE, scope_json, "inventory"), 10, "complete"
    )
    store.inventory(observation)
    store.prove_inventory(claim, observation)
    assert store.coverage(claim.scope).known_empty
    store.inventory(replace(observation, state="partial"))
    assert store.coverage(claim.scope).state == "conflict"
    with pytest.raises(sqlite3.IntegrityError, match="superseded or conflicting"):
        store.prove_inventory(claim, observation)


def test_context_absence_is_unavailable_never_recreated(tmp_path):
    with pytest.raises((ValueError, FileNotFoundError)):
        with Context.snapshot(tmp_path):
            pytest.fail("missing Context fabricated")
    assert not (tmp_path / "context.sqlite3").exists()


@pytest.mark.parametrize("method", ["candidates", "coverage", "text"])
def test_stop_detected_during_last_sqlite_read_cannot_return_success(directory, method):
    with Context.transaction(directory) as store:
        store.provider(SERVICE, "github")
        store.observe(ResourceObservation(KEY, (field(),)))
        digest = store.text("retained text")
    db = connect(directory / "context.sqlite3", "context")
    db.execute("BEGIN")
    stop = PairCoordinator(directory)
    fired = False

    def trace(sql):
        nonlocal fired
        if not fired and sql.startswith("SELECT"):
            fired = True
            stop.stop("injected stop during last SELECT")

    try:
        with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
            with Context.for_snapshot(db, directory) as store:
                db.set_trace_callback(trace)
                if method == "candidates":
                    store.candidates(KEY, "title")
                elif method == "coverage":
                    store.coverage(CoverageScope.resource(KEY, "reviews"))
                else:
                    store.read_text(digest)
    finally:
        db.set_trace_callback(None)
        db.rollback()
        db.close()
    assert fired


def test_stopped_snapshot_finalizer_cannot_report_normal_completion(directory):
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        with Context.snapshot(directory):
            PairCoordinator(directory).stop("stop during result computation")


def test_invalid_utf8_stored_field_stops_before_caller_can_swallow(directory):
    with Context.transaction(directory) as store:
        store.provider(SERVICE, "github")
        store.observe(ResourceObservation(KEY, (field(),)))
    db = connect(directory / "context.sqlite3", "context")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute("UPDATE field_candidates SET provenance_json=CAST(X'80' AS TEXT)")
    db.close()
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        with Context.snapshot(directory) as store:
            with pytest.raises(sqlite3.OperationalError, match="decode to UTF-8"):
                store.candidates(KEY, "title")
            assert (directory / "p1-recovery-stop.json").exists()
            with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
                store.candidates(KEY, "missing")


@pytest.mark.parametrize("mode", ["transaction", "snapshot"])
def test_context_cannot_bind_core_shared_coverage_tables(directory, mode):
    initialize(directory / "core.sqlite3", "core", REPO, INSTANCE)
    coordinator = PairCoordinator(directory)
    if mode == "transaction":

        def wrong_core_unit(db):
            with Context.for_transaction(db, directory) as context:
                scope = CoverageScope.repository(REPO, "provider-inventory")
                context.scope(scope)
                context.admit_coverage(CoverageClaim(scope, 10, "complete"))

        with pytest.raises(AdmissionFailure) as failure:
            coordinator.admit(wrong_core_unit, lambda db: None)
        assert isinstance(failure.value.cause, ContextError)
        assert failure.value.cause.code == "STORE_ROLE"
        assert not failure.value.outcome.core_committed
    else:
        with coordinator.snapshots() as pair:
            with pytest.raises(ContextError, match="STORE_ROLE"):
                with Context.for_snapshot(pair.core, directory):
                    pytest.fail("Core claims mislabeled as Context")
    assert not (directory / "p1-recovery-stop.json").exists()
    with coordinator.snapshots() as pair:
        assert (
            pair.core.execute("SELECT count(*) FROM coverage_claims").fetchone()[0] == 0
        )


@pytest.mark.parametrize("operation", ["read", "replay"])
def test_known_retained_text_loss_stops_without_silent_repair(directory, operation):
    content = "previously retained exact Context body"
    with Context.transaction(directory) as store:
        store.provider(SERVICE, "github")
        store.resource(KEY)
        store.admit_text(
            KEY, content, FieldClock("provider.updated_at", 1), PROVENANCE, 10
        )
        digest = json.loads(store.candidates(KEY, "text_body_sha256")[0].value_json)
    db = connect(directory / "context.sqlite3", "context")
    trigger = db.execute(
        "SELECT sql FROM sqlite_schema WHERE name='text_bodies_no_delete'"
    ).fetchone()[0]
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("DROP TRIGGER text_bodies_no_delete")
    db.execute("DELETE FROM text_bodies WHERE sha256=?", (digest,))
    db.execute(trigger)
    db.close()
    with pytest.raises(ContextError, match="AUTHORITATIVE_CORRUPTION"):
        with Context.transaction(directory) as store:
            if operation == "read":
                store.read_text(digest)
            else:
                store.text(content)
    assert (directory / "p1-recovery-stop.json").exists()
    db = connect(directory / "context.sqlite3", "context")
    try:
        assert db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 0
    finally:
        db.close()


def test_unknown_text_digest_is_unavailable_without_false_corruption(context):
    _, store, path = context
    with pytest.raises(ContextError) as failure:
        store.read_text("a" * 64)
    assert failure.value.code == "TEXT_UNAVAILABLE"
    assert not (path.parent / "p1-recovery-stop.json").exists()
    digest = store.text("genuinely new Context text")
    assert store.read_text(digest) == "genuinely new Context text"


def test_production_context_relation_facade_methods(directory):
    with Context.transaction(directory) as store:
        store.provider(SERVICE, "github")
        store.repository(REPO)
        prov_repo = ResourceKey(SERVICE, "repository", "octocat/Hello-World")
        store.resource(prov_repo)
        
        # Test mapping_dispositions does not throw TypeError or false corruption
        disps = store.mapping_dispositions()
        assert disps == ()
        
        # Test relations_for_provider_repository with ResourceKey
        rels = store.relations_for_provider_repository(prov_repo)
        assert rels == ()
        
        # Test relations_for_provider_repository with separate strings
        rels2 = store.relations_for_provider_repository(SERVICE, "octocat/Hello-World")
        assert rels2 == ()
        
        # Test transfer_event_reports
        reports = store.transfer_event_reports()
        assert reports == ()
    
    assert not (directory / "p1-recovery-stop.json").exists()
