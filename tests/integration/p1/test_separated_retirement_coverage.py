"""Preserve legacy coverage truth tables using separated semantic owners."""

import sqlite3
from itertools import permutations

from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope, canonical
from repo_catalog.domain.p1_coverage import derive_coverage_state
from tests.integration.p1.test_context import KEY, PROVENANCE, REPO, context
from tests.integration.p1.test_coverage import proof

__all__ = ["context"]


def prove_current_complete_collection(db, claim):
    """Install actual exact-owner terminal evidence, then its immutable proof."""
    kind = claim.scope.coordinates[-1]
    db.execute(
        "INSERT OR IGNORE INTO collections VALUES(?,?,?,?,?,?)",
        (
            *KEY.coordinates(),
            kind,
            PROVENANCE,
            canonical({"repository_uuidv4": REPO, "coverage_kind": kind}),
        ),
    )
    terminal = (
        *KEY.coordinates(),
        kind,
        PROVENANCE,
        claim.observed_at_us,
        "complete",
        "[]",
    )
    db.execute("INSERT INTO collection_terminals VALUES(?,?,?,?,?,?,?,?)", terminal)
    proof(db, claim, terminal)


def test_all_coverage_state_sets_preserve_claims_for_tuple_and_named_rows(context):
    db, store, _ = context
    cases = (
        ((), "unknown"),
        (("unknown",), "unknown"),
        (("complete",), "complete"),
        (("partial",), "partial"),
        (("not_applicable",), "not_applicable"),
        (("unknown", "complete"), "complete"),
        (("unknown", "partial"), "partial"),
        (("unknown", "not_applicable"), "not_applicable"),
        (("complete", "partial"), "conflict"),
        (("complete", "not_applicable"), "conflict"),
        (("partial", "not_applicable"), "conflict"),
        (("unknown", "complete", "partial"), "conflict"),
        (("unknown", "complete", "not_applicable"), "conflict"),
        (("unknown", "partial", "not_applicable"), "conflict"),
        (("complete", "partial", "not_applicable"), "conflict"),
        (("unknown", "complete", "partial", "not_applicable"), "conflict"),
    )
    for factory in (None, sqlite3.Row):
        db.row_factory = factory
        for index, (states, expected) in enumerate(cases):
            scope = CoverageScope.repository(REPO, f"truth-{factory is None}-{index}")
            store.scope(scope)
            for ordering in permutations(states):
                assert derive_coverage_state(ordering) == expected
            for state in reversed(states):
                claim = CoverageClaim(scope, 1, state)
                assert store.admit_coverage(claim) == "insert"
                if state == "complete":
                    prove_current_complete_collection(db, claim)
            current = store.coverage(scope)
            assert current.state == expected
            assert current.observed_at_us == (1 if states else None)
            assert [claim.state for claim in current.claims] == sorted(states)
            assert all(claim.details_json is None for claim in current.claims)
            assert current.known_empty is (expected == "complete")
            count = db.execute(
                "SELECT count(*) FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=?",
                (scope.owner_kind, scope.encoded),
            ).fetchone()[0]
            assert count == len(states)


def test_latest_history_keeps_old_claims_and_never_falls_back(context):
    db, store, _ = context
    cases = (
        ((("complete", 1), ("unknown", 2)), "unknown", 2, ("unknown",)),
        (
            (("complete", 1), ("complete", 2), ("partial", 2)),
            "conflict",
            2,
            ("complete", "partial"),
        ),
        (
            (("complete", 1), ("partial", 1), ("complete", 2)),
            "complete",
            2,
            ("complete",),
        ),
        (
            (("complete", 1), ("partial", 1), ("unknown", 2)),
            "unknown",
            2,
            ("unknown",),
        ),
    )
    for factory in (None, sqlite3.Row):
        db.row_factory = factory
        for index, (history, expected, stamp, states) in enumerate(cases):
            scope = CoverageScope.repository(REPO, f"history-{factory is None}-{index}")
            store.scope(scope)
            for state, observed in history:
                claim = CoverageClaim(scope, observed, state)
                assert store.admit_coverage(claim) == "insert"
                if state == "complete":
                    prove_current_complete_collection(db, claim)
            selected = store.coverage(scope)
            assert (selected.state, selected.observed_at_us) == (expected, stamp)
            assert tuple(claim.state for claim in selected.claims) == states
            assert db.execute(
                "SELECT count(*) FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=?",
                (scope.owner_kind, scope.encoded),
            ).fetchone()[0] == len(history)
            assert (
                store.admit_coverage(CoverageClaim(scope, 1, "not_applicable"))
                == "stale"
            )
            assert store.coverage(scope) == selected


def test_unproven_complete_claim_never_creates_complete_or_known_empty(context):
    db, store, _ = context
    scope = CoverageScope.repository(REPO, "unproven-complete")
    store.scope(scope)
    claim = CoverageClaim(scope, 1, "complete")
    assert store.admit_coverage(claim) == "insert"
    unproven = store.coverage(scope)
    assert unproven.claims == (claim,)
    assert unproven.observed_at_us == 1
    assert unproven.state == "unknown"
    assert not unproven.known_empty
    prove_current_complete_collection(db, claim)
    proven = store.coverage(scope)
    assert proven.claims == (claim,)
    assert proven.state == "complete"
    assert proven.known_empty


def test_coverage_admission_rolls_back_with_the_callers_transaction(context):
    db, store, _ = context
    scope = CoverageScope.repository(REPO, "caller-rollback")
    store.scope(scope)
    claim = CoverageClaim(scope, 1, "partial", '{"advisory":"original"}')
    with store.transaction(rollback=True):
        assert store.admit_coverage(claim) == "insert"
        assert db.in_transaction
        assert store.coverage(scope).claims == (claim,)
    assert not db.in_transaction
    current = store.coverage(scope)
    assert current.state == "unknown"
    assert current.observed_at_us is None
    assert current.claims == ()
    assert (
        db.execute(
            "SELECT count(*) FROM coverage_claims WHERE owner_kind=? AND owner_coordinates_json=?",
            (scope.owner_kind, scope.encoded),
        ).fetchone()[0]
        == 0
    )
