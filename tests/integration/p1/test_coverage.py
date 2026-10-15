"""Five real columns, lossless semantic keys and latest-observation semantics."""

import json
import sqlite3

import pytest

from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageScope,
    ResourceKey,
    canonical,
)
from tests.integration.p1.test_context import (
    KEY,
    PROVENANCE,
    REPO,
    SERVICE,
    SOURCE,
    context,
)

__all__ = ["context"]


def collection(
    db,
    *,
    key=KEY,
    kind="reviews",
    provenance=PROVENANCE,
    members="[]",
    stamp=10,
    state="complete",
):
    db.execute(
        "INSERT INTO collections VALUES(?,?,?,?,?,?)",
        (*key.coordinates(), kind, provenance, "{}"),
    )
    terminal = (*key.coordinates(), kind, provenance, stamp, state, members)
    db.execute("INSERT INTO collection_terminals VALUES(?,?,?,?,?,?,?,?)", terminal)
    return terminal


def proof(db, claim, terminal):
    db.execute(
        "INSERT INTO coverage_proofs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            claim.scope.owner_kind,
            claim.scope.encoded,
            claim.observed_at_us,
            claim.state,
            *terminal,
        ),
    )


def test_exactly_five_actual_columns_direct_pk_and_fk(context):
    db, _, _ = context
    columns = db.execute("PRAGMA table_xinfo(coverage_claims)").fetchall()
    assert [row[1] for row in columns] == [
        "owner_kind",
        "owner_coordinates_json",
        "observed_at_us",
        "coverage_state",
        "details_json",
    ]
    assert [row[5] for row in columns] == [1, 2, 3, 4, 0]
    assert all(row[6] == 0 for row in columns)
    assert db.execute(
        "SELECT wr,strict FROM pragma_table_list WHERE name='coverage_claims'"
    ).fetchone() == (1, 1)
    references = db.execute("PRAGMA foreign_key_list(coverage_proofs)").fetchall()
    claim_fk = [row for row in references if row[2] == "coverage_claims"]
    assert {row[3] for row in claim_fk} == {
        "owner_kind",
        "owner_coordinates_json",
        "observed_at_us",
        "coverage_state",
    }


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CoverageScope.repository(REPO, "inventory"),
        lambda: CoverageScope.resource(KEY, "comments"),
        lambda: CoverageScope.field(KEY, "title", "presence"),
        lambda: CoverageScope.collection(KEY, "reviews", PROVENANCE, "members"),
        lambda: CoverageScope.source(SOURCE, REPO, "membership"),
        lambda: CoverageScope.source_inventory(
            SOURCE, '{"owner":"actual"}', "inventory"
        ),
    ],
)
def test_real_owner_coordinates_round_trip_and_local_fk(context, factory):
    db, store, _ = context
    db.execute("INSERT INTO source_repositories VALUES(?,?,?)", (SOURCE, REPO, "{}"))
    collection(db)
    scope = factory()
    assert tuple(json.loads(scope.encoded)) == scope.coordinates
    store.scope(scope)
    store.admit_coverage(CoverageClaim(scope, 1, "partial"))
    assert store.coverage(scope).state == "partial"


def test_scope_cannot_use_hash_or_opaque_alias(context):
    db, store, _ = context
    scope = CoverageScope.repository(REPO, "inventory")
    store.scope(scope)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO coverage_scopes(owner_kind,owner_coordinates_json,repository_uuidv4,coverage_kind) VALUES(?,?,?,?)",
            ("repository", '"opaque-short-alias"', REPO, "inventory"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.scope(
            CoverageScope.resource(ResourceKey(SERVICE, "issue", "absent"), "comments")
        )


def test_unicode_full_owner_coordinates_are_lossless(context):
    _, store, _ = context
    scope = CoverageScope.field(KEY, "é/😀", "真")
    store.scope(scope)
    assert json.loads(scope.encoded)[-2:] == ["é/😀", "真"]


def test_repeated_identical_and_advisory_only_replays(context):
    db, store, _ = context
    scope = CoverageScope.repository(REPO, "inventory")
    store.scope(scope)
    original = CoverageClaim(scope, 10, "complete", '{"advisory":"first"}')
    assert store.admit_coverage(original) == "insert"
    assert store.admit_coverage(original) == "duplicate"
    assert (
        store.admit_coverage(
            CoverageClaim(scope, 10, "complete", '{"advisory":"second"}')
        )
        == "duplicate"
    )
    assert db.execute(
        "SELECT count(*),details_json FROM coverage_claims"
    ).fetchone() == (1, '{"advisory":"first"}')
    for sql in [
        "UPDATE coverage_claims SET details_json='{}'",
        "DELETE FROM coverage_claims",
        "INSERT OR REPLACE INTO coverage_claims VALUES('repository',?,10,'complete','{}')",
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql, (scope.encoded,) if "?" in sql else ())


def test_latest_unknown_never_falls_back_to_older_complete(context):
    _, store, _ = context
    scope = CoverageScope.repository(REPO, "inventory")
    store.scope(scope)
    store.admit_coverage(CoverageClaim(scope, 10, "complete"))
    store.admit_coverage(CoverageClaim(scope, 11, "unknown"))
    assert store.coverage(scope).state == "unknown"
    assert store.coverage(scope).observed_at_us == 11
    assert store.admit_coverage(CoverageClaim(scope, 9, "complete")) == "stale"


def test_same_time_conflicting_states_preserved(context):
    _, store, _ = context
    scope = CoverageScope.resource(KEY, "reviews")
    store.scope(scope)
    for state in ["complete", "partial", "unknown"]:
        assert store.admit_coverage(CoverageClaim(scope, 5, state)) == "insert"
    current = store.coverage(scope)
    assert current.state == "conflict"
    assert len(current.claims) == 3
    assert not current.known_empty


def test_known_empty_requires_actual_terminal_not_absence(context):
    db, store, _ = context
    scope = CoverageScope.resource(KEY, "reviews")
    store.scope(scope)
    assert store.coverage(scope).state == "unknown"
    assert store.coverage(scope).observed_at_us is None
    claim = CoverageClaim(scope, 10, "complete")
    store.admit_coverage(claim)
    assert not store.coverage(scope).known_empty
    terminal = collection(db)
    proof(db, claim, terminal)
    assert store.coverage(scope).known_empty


def test_proofs_require_exact_claim_terminal_and_same_owner(context):
    db, store, _ = context
    scope = CoverageScope.resource(KEY, "reviews")
    store.scope(scope)
    terminal = collection(db)
    with pytest.raises(sqlite3.IntegrityError):
        proof(db, CoverageClaim(scope, 10, "complete"), terminal)
    store.admit_coverage(CoverageClaim(scope, 10, "complete"))
    proof(db, CoverageClaim(scope, 10, "complete"), terminal)
    wrong = ResourceKey(SERVICE, "issue", "8")
    store.resource(wrong, REPO)
    terminal2 = collection(db, key=wrong)
    with pytest.raises(sqlite3.IntegrityError, match="owner mismatch"):
        proof(db, CoverageClaim(scope, 10, "complete"), terminal2)
    with pytest.raises(sqlite3.IntegrityError):
        proof(db, CoverageClaim(scope, 10, "partial"), terminal)


def test_partial_terminal_cannot_prove_complete(context):
    db, store, _ = context
    scope = CoverageScope.resource(KEY, "reviews")
    store.scope(scope)
    claim = CoverageClaim(scope, 10, "complete")
    store.admit_coverage(claim)
    terminal = collection(db, state="partial")
    with pytest.raises(sqlite3.IntegrityError):
        proof(db, claim, terminal)


def test_scope_kind_does_not_merge_distinct_nested_head_base(context):
    db, store, _ = context
    head = canonical(
        {"source": "provider.example", "evidence": {"head": "a" * 40, "base": "b" * 40}}
    )
    changed = canonical(
        {"source": "provider.example", "evidence": {"head": "c" * 40, "base": "b" * 40}}
    )
    for evidence in [head, changed]:
        db.execute(
            "INSERT INTO collections VALUES(?,?,?,?,?,?)",
            (*KEY.coordinates(), "files", evidence, "{}"),
        )
        store.scope(CoverageScope.collection(KEY, "files", evidence, "members"))
    first = CoverageScope.collection(KEY, "files", head, "members")
    other = CoverageScope.collection(KEY, "files", changed, "members")
    store.admit_coverage(CoverageClaim(first, 10, "complete"))
    assert store.coverage(other).state == "unknown"


def test_source_known_positive_survives_unknown_and_disposable_loss(context):
    db, store, path = context
    db.execute("INSERT INTO source_repositories VALUES(?,?,?)", (SOURCE, REPO, "{}"))
    scope = CoverageScope.source(SOURCE, REPO, "membership")
    store.scope(scope)
    store.admit_coverage(CoverageClaim(scope, 3, "complete"))
    store.admit_coverage(CoverageClaim(scope, 4, "unknown"))
    for name in ["operational", "search"]:
        disposable = path.parent / f"{name}.sqlite3"
        sqlite3.connect(disposable).close()
        disposable.unlink()
    assert (
        db.execute("SELECT repository_uuidv4 FROM source_repositories").fetchone()[0]
        == REPO
    )
    assert store.coverage(scope).state == "unknown"


def test_source_inventory_scope_needs_no_fabricated_resource_or_membership(context):
    db, store, _ = context
    scope = CoverageScope.source_inventory(
        SOURCE, '{"filter":"actual"}', "repositories"
    )
    store.scope(scope)
    store.admit_coverage(CoverageClaim(scope, 3, "complete"))
    assert db.execute("SELECT count(*) FROM source_repositories").fetchone()[0] == 0
    assert store.coverage(scope).state == "complete"


def test_known_empty_source_inventory_has_exact_source_proof(context):
    db, store, _ = context
    scope = CoverageScope.source_inventory(
        SOURCE, '{"filter":"actual"}', "repositories"
    )
    store.scope(scope)
    claim = CoverageClaim(scope, 3, "complete")
    store.admit_coverage(claim)
    assert not store.coverage(scope).known_empty
    inventory = (SOURCE, '{"filter":"actual"}', 3, "complete", 1, "[]", PROVENANCE)
    db.execute("INSERT INTO source_inventory_evidence VALUES(?,?,?,?,?,?,?)", inventory)
    db.execute(
        "INSERT INTO source_coverage_proofs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (scope.owner_kind, scope.encoded, 3, "complete", *inventory),
    )
    assert store.coverage(scope).known_empty


def test_coverage_projection_pins_one_local_snapshot(context):
    db, store, path = context
    db.execute("PRAGMA journal_mode=WAL")
    scope = CoverageScope.resource(KEY, "reviews")
    store.scope(scope)
    claim = CoverageClaim(scope, 10, "complete")
    store.admit_coverage(claim)
    terminal = collection(db)
    other = sqlite3.connect(path, isolation_level=None)
    from repo_catalog.adapters.sqlite.p1_schema import register_functions

    register_functions(other)
    other.execute("PRAGMA foreign_keys=ON")
    inserted = False

    def between(statement):
        nonlocal inserted
        if (
            statement.startswith("SELECT members_json FROM coverage_proofs")
            and not inserted
        ):
            inserted = True
            proof(other, claim, terminal)

    db.set_trace_callback(between)
    try:
        assert not store.coverage(scope).known_empty
        assert inserted
    finally:
        db.set_trace_callback(None)
        other.close()
    assert store.coverage(scope).known_empty
