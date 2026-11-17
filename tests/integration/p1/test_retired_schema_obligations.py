"""Concrete retired-schema adversaries on actual separated Context authority.

These tests replace natural-key and evidence obligations, not legacy table names,
local surrogate IDs, publication ledgers, or the normal catalog implementation.
"""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from repo_catalog.adapters.sqlite.p1_schema import compose, register_functions
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope
from repo_catalog.domain.time import MAX_EPOCH_US, MIN_EPOCH_US
from tests.integration.p1.test_context import (
    KEY,
    REPO,
    candidate,
    context,
    p1_grants,
)
from tests.integration.p1.test_coverage import collection
from tests.support.authorized_context import FixtureContextStore

__all__ = ["context"]


@pytest.fixture(params=["tuple", "row"])
def coverage_context(context, request):
    db, store, path = context
    db.row_factory = sqlite3.Row if request.param == "row" else None
    scope = CoverageScope.repository(REPO, "git-inventory")
    store.scope(scope)
    return db, store, path, scope


@pytest.mark.parametrize(
    "details",
    [None, "{}", '{"reason":"original advisory"}'],
    ids=["null", "empty", "reason"],
)
def test_coverage_duplicate_stale_and_same_time_advisories_are_independent(
    coverage_context, details
):
    db, store, _, scope = coverage_context
    first = CoverageClaim(scope, 10, "complete", details)
    assert store.admit_coverage(first) == "insert"
    before = db.total_changes
    assert (
        store.admit_coverage(
            CoverageClaim(scope, 10, "complete", '{"reason":"duplicate"}')
        )
        == "duplicate"
    )
    assert (
        store.admit_coverage(CoverageClaim(scope, 9, "partial", '{"reason":"stale"}'))
        == "stale"
    )
    assert db.total_changes == before
    assert store.coverage(scope).claims == (first,)
    assert store.admit_coverage(CoverageClaim(scope, 10, "unknown")) == "insert"
    partial = CoverageClaim(scope, 10, "partial", '{"reason":"same-time partial"}')
    assert store.admit_coverage(partial) == "insert"
    current = store.coverage(scope)
    assert current.state == "conflict"
    assert current.claims == (first, partial, CoverageClaim(scope, 10, "unknown"))
    assert not current.known_empty


def test_coverage_latest_set_replays_into_an_independent_store(
    coverage_context, tmp_path
):
    db, store, _, scope = coverage_context
    for state, stamp in [
        ("complete", 1),
        ("complete", 2),
        ("partial", 2),
        ("unknown", 2),
    ]:
        store.admit_coverage(
            CoverageClaim(scope, stamp, state, '{"reason":"source advisory"}')
        )
    exported = store.coverage(scope).claims
    assert len(exported) == 3
    assert {claim.observed_at_us for claim in exported} == {2}
    assert db.execute("SELECT count(*) FROM coverage_claims").fetchone()[0] == 4
    destination_path = tmp_path / "destination" / "context.sqlite3"
    destination_path.parent.mkdir()
    destination = sqlite3.connect(destination_path, isolation_level=None)
    register_functions(destination, "context")
    destination.execute("PRAGMA foreign_keys=ON")
    destination.execute("PRAGMA recursive_triggers=ON")
    destination.executescript(compose("context"))
    destination.execute("INSERT INTO repository_context VALUES(?,?)", (REPO, "{}"))
    receiver = FixtureContextStore(destination, DependencySet(repositories={REPO}))
    try:
        receiver.scope(scope)
        for claim in exported:
            assert receiver.admit_coverage(claim) == "insert"
        before = destination.total_changes
        for claim in reversed(exported):
            assert receiver.admit_coverage(claim) == "duplicate"
        assert destination.total_changes == before
        assert receiver.coverage(scope) == store.coverage(scope)
        assert not destination.execute("PRAGMA foreign_key_check").fetchall()
        assert destination.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        receiver.close()
        destination.close()


@pytest.mark.parametrize(
    "stamp",
    [None, True, 1.0, "1", MIN_EPOCH_US - 1, MAX_EPOCH_US + 1, MIN_EPOCH_US, 0],
    ids=[
        "null",
        "bool",
        "float",
        "string",
        "below-int64",
        "above-int64",
        "negative",
        "zero",
    ],
)
def test_invalid_coverage_times_are_rejected_before_writing(coverage_context, stamp):
    db, store, _, scope = coverage_context
    before = db.total_changes
    with pytest.raises((TypeError, ValueError)):
        store.admit_coverage(CoverageClaim(scope, stamp, "complete"))
    assert db.total_changes == before
    assert store.coverage(scope).claims == ()
    assert store.admit_coverage(CoverageClaim(scope, 1, "partial")) == "insert"


@pytest.mark.parametrize(
    "state", ["conflict", "pending", None], ids=["conflict", "pending", "null"]
)
def test_projection_only_or_invalid_states_cannot_be_authoritative_claims(
    coverage_context, state
):
    db, store, _, scope = coverage_context
    before = db.total_changes
    with pytest.raises(ValueError):
        store.admit_coverage(CoverageClaim(scope, 1, state))
    assert db.total_changes == before
    assert store.coverage(scope).claims == ()


@pytest.mark.parametrize("owner", [None, ""], ids=["null", "empty"])
def test_incomplete_typed_coverage_owner_is_rejected_before_writing(
    coverage_context, owner
):
    db, _, _, _ = coverage_context
    before = db.total_changes
    with pytest.raises(ValueError):
        CoverageScope.repository(owner, "git-inventory")
    assert db.total_changes == before
    assert db.execute("SELECT count(*) FROM coverage_claims").fetchone()[0] == 0


def test_maximum_required_observation_time_remains_exact(coverage_context):
    db, store, _, scope = coverage_context
    claim = CoverageClaim(scope, MAX_EPOCH_US, "partial")
    assert store.admit_coverage(claim) == "insert"
    assert store.coverage(scope).observed_at_us == MAX_EPOCH_US
    assert tuple(
        db.execute(
            "SELECT observed_at_us,typeof(observed_at_us) FROM coverage_claims"
        ).fetchone()
    ) == (MAX_EPOCH_US, "integer")


@pytest.mark.parametrize(
    "attack",
    ["state", "details", "time", "delete", "insert", "ignore", "replace", "upsert"],
)
def test_coverage_semantic_key_cannot_be_mutated_or_overwritten(
    coverage_context, attack
):
    db, store, _, scope = coverage_context
    claim = CoverageClaim(scope, 1, "partial", '{"reason":"original"}')
    store.admit_coverage(claim)
    before = [tuple(row) for row in db.execute("SELECT * FROM coverage_claims")]
    updates = {
        "state": "UPDATE coverage_claims SET coverage_state='complete'",
        "details": "UPDATE coverage_claims SET details_json='{}'",
        "time": "UPDATE coverage_claims SET observed_at_us=2",
        "delete": "DELETE FROM coverage_claims",
    }
    if attack in updates:
        sql = updates[attack]
    else:
        verb = {
            "insert": "INSERT",
            "ignore": "INSERT OR IGNORE",
            "replace": "INSERT OR REPLACE",
            "upsert": "INSERT",
        }[attack]
        sql = f"{verb} INTO coverage_claims SELECT * FROM coverage_claims WHERE 1"
        if attack == "upsert":
            sql += " ON CONFLICT(owner_kind,owner_coordinates_json,observed_at_us,coverage_state) DO UPDATE SET details_json='{}'"
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql)
    assert [tuple(row) for row in db.execute("SELECT * FROM coverage_claims")] == before
    assert store.coverage(scope).claims == (claim,)


def test_coverage_scope_uniqueness_and_claim_rollback(coverage_context):
    db, store, _, scope = coverage_context
    before = db.total_changes
    store.scope(scope)
    assert db.total_changes == before
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO coverage_scopes SELECT * FROM coverage_scopes")
    with pytest.raises(RuntimeError, match="caller rollback"):
        with store.transaction():
            store.admit_coverage(CoverageClaim(scope, 1, "partial"))
            assert store.coverage(scope).claims
            raise RuntimeError("caller rollback")
    assert store.coverage(scope).claims == ()
    assert not db.in_transaction


@pytest.mark.parametrize(
    "inputs,expected_state,accepted",
    [
        ((("complete", 10), ("complete", 10)), "unknown", 1),
        ((("complete", 10), ("partial", 10)), "conflict", 2),
        ((("partial", 9), ("complete", 10)), "unknown", None),
    ],
    ids=["duplicate", "same-time-conflict", "newer-wins"],
)
def test_competing_context_writers_preserve_atomic_coverage_admission(
    context, inputs, expected_state, accepted
):
    db, store, path = context
    scope = CoverageScope.repository(REPO, "git-inventory")
    store.scope(scope)
    barrier = Barrier(2)

    def admit(value):
        connection = sqlite3.connect(path, isolation_level=None, timeout=10)
        register_functions(connection, "context")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA recursive_triggers=ON")
        writer = FixtureContextStore(connection, p1_grants())
        try:
            barrier.wait(timeout=10)
            return writer.admit_coverage(CoverageClaim(scope, value[1], value[0]))
        finally:
            writer.close()
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(admit, inputs))
    current = store.coverage(scope)
    # An unproven complete repository claim cannot invent completeness; the
    # original claims remain visible and equal-clock partial still conflicts.
    assert current.state == expected_state
    assert current.observed_at_us == 10
    assert {claim.state for claim in current.claims} == {
        state for state, stamp in inputs if stamp == 10
    }
    if accepted is not None:
        assert results.count("insert") == accepted
        assert len(current.claims) == accepted
    before = db.total_changes
    assert store.admit_coverage(CoverageClaim(scope, 8, "unknown")) == "stale"
    assert db.total_changes == before


@pytest.fixture
def immutable_evidence(context):
    db, store, path = context
    store.text("original body")
    collection(db)
    return db, store, path


@pytest.mark.parametrize("mode", ["autocommit", "transaction", "savepoint"])
@pytest.mark.parametrize(
    "table", ["resources", "text_bodies", "collections", "collection_terminals"]
)
def test_context_identity_and_evidence_are_immutable_in_every_transaction_mode(
    immutable_evidence, table, mode
):
    db, _, _ = immutable_evidence
    original = [tuple(row) for row in db.execute(f'SELECT * FROM "{table}"')]
    assert original
    columns = [
        (row[1], row[2])
        for row in db.execute(f'PRAGMA table_xinfo("{table}")')
        if row[6] == 0
    ]
    if mode == "transaction":
        db.execute("BEGIN")
    elif mode == "savepoint":
        db.execute("SAVEPOINT attack")
    try:
        for column, sql_type in columns:
            # Reach the immutable-row guard with a genuine SQLite primitive;
            # STRICT type rejection alone does not exercise that guard.
            replacement = {"TEXT": "forged", "INTEGER": 2, "BLOB": b"forged"}[sql_type]
            with pytest.raises(
                sqlite3.IntegrityError, match="immutable Context evidence"
            ):
                db.execute(f'UPDATE "{table}" SET "{column}"=?', (replacement,))
        with pytest.raises(sqlite3.IntegrityError, match="immutable Context evidence"):
            db.execute(f'DELETE FROM "{table}"')
        names = ",".join(f'"{column}"' for column, _ in columns)
        with pytest.raises(sqlite3.IntegrityError, match="immutable Context evidence"):
            db.execute(
                f'INSERT OR REPLACE INTO "{table}" ({names}) SELECT {names} FROM "{table}"'
            )
        assert [
            tuple(row) for row in db.execute(f'SELECT * FROM "{table}"')
        ] == original
    finally:
        if mode == "transaction":
            db.execute("ROLLBACK")
        elif mode == "savepoint":
            db.execute("ROLLBACK TO attack")
            db.execute("RELEASE attack")
    assert not db.in_transaction
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_text_reuse_a_b_a_preserves_current_field_clock_without_api_edit_archive(
    context,
):
    db, store, _ = context
    first = store.text("A")
    other = store.text("B")
    assert first != other and store.text("A") == first
    for clock, digest in [(1, first), (2, other), (3, first)]:
        store.admit_field(
            replace(
                candidate(digest, clock=clock, observed=clock),
                field_name="text_body_sha256",
            )
        )
    current = store.candidates(KEY, "text_body_sha256")
    assert len(current) == 1
    assert current[0].value_json == f'"{first}"'
    assert current[0].clock.at_us == 3
    assert current[0].observed_at_us == 3
    assert db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 2
    assert db.execute("SELECT count(*) FROM field_candidates").fetchone()[0] == 1


@pytest.mark.parametrize("attack", ["identity", "body", "foreign-key"])
def test_context_multi_statement_failure_rolls_back_the_complete_typed_unit(
    immutable_evidence, attack
):
    db, store, _ = immutable_evidence
    tables = ("resources", "text_bodies", "collections", "collection_terminals")
    before = {
        table: [tuple(row) for row in db.execute(f'SELECT * FROM "{table}"')]
        for table in tables
    }
    with pytest.raises(sqlite3.IntegrityError), store.transaction():
        store.text("must roll back with failed identity/evidence unit")
        if attack == "identity":
            db.execute("UPDATE resources SET provider_resource_id='reparented'")
        elif attack == "body":
            db.execute("UPDATE text_bodies SET text_value='forged body'")
        else:
            db.execute(
                "INSERT INTO collections VALUES(?,?,?,?,?,?)",
                (
                    KEY.service_instance_uuidv4,
                    "issue",
                    "unregistered",
                    "reviews",
                    '{"evidence":"test","source":"provider.example"}',
                    "{}",
                ),
            )
    assert {
        table: [tuple(row) for row in db.execute(f'SELECT * FROM "{table}"')]
        for table in tables
    } == before
    assert not db.in_transaction
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
