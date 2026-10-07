"""Coverage facts, deterministic current state and atomic admission contracts."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from itertools import permutations
from threading import Barrier

import pytest

from repo_catalog.adapters.sqlite.coverage import (
    admit_claim,
    current_coverages,
    export_current_claims,
)
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.domain.coverage import (
    decide_admission,
    derive_coverage_state,
    latest_claims,
)
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import MAX_EPOCH_US, MIN_EPOCH_US


def initialize(connection):
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA recursive_triggers=ON")
    connection.executescript(schema_sql())
    connection.execute(
        "INSERT INTO repositories(repository_id,name,metadata) VALUES('repo','synthetic','{}')"
    )
    connection.execute(
        "INSERT INTO coverage_scopes(coverage_scope_id,repository_id,kind) VALUES('scope','repo','git')"
    )


@pytest.fixture(params=[None, sqlite3.Row], ids=["tuple", "row"])
def catalog(request):
    connection = sqlite3.connect(":memory:", autocommit=True)
    connection.row_factory = request.param
    initialize(connection)
    yield connection
    assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    connection.close()


def claim(state, observed_at_us, details_json=None, *, scope="scope"):
    return {
        "coverage_scope_id": scope,
        "coverage_state": state,
        "observed_at_us": observed_at_us,
        "details_json": details_json,
    }


SAME_TIME_CASES = [
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
]


@pytest.mark.parametrize("states,expected", SAME_TIME_CASES)
def test_same_time_truth_table_matches_view_and_keeps_all_claims(
    catalog, states, expected
):
    for ordering in permutations(states):
        assert derive_coverage_state(ordering) == expected
    for state in reversed(states):
        assert admit_claim(catalog, "scope", state, 0) is not None
    component = current_coverages(catalog, "repo")[0]
    assert component["coverage_state"] == expected
    assert component["observed_at_us"] == (0 if states else None)
    assert component["claim_count"] == len(states)
    assert [row["coverage_state"] for row in component["claims"]] == sorted(states)
    assert export_current_claims(catalog, "scope") == component["claims"]
    assert all(row["details_json"] is None for row in component["claims"])


@pytest.mark.parametrize(
    "history,expected,expected_time,expected_states",
    [
        ([("complete", -1), ("unknown", 0)], "unknown", 0, ["unknown"]),
        (
            [("complete", 0), ("complete", 1), ("partial", 1)],
            "conflict",
            1,
            ["complete", "partial"],
        ),
        (
            [("complete", 0), ("partial", 0), ("complete", 1)],
            "complete",
            1,
            ["complete"],
        ),
        (
            [("complete", 0), ("partial", 0), ("unknown", 1)],
            "unknown",
            1,
            ["unknown"],
        ),
    ],
)
def test_latest_time_always_wins_and_conflict_never_falls_back(
    catalog, history, expected, expected_time, expected_states
):
    original = []
    for state, stamp in history:
        assert admit_claim(catalog, "scope", state, stamp) is not None
        original.append(claim(state, stamp))
    selected = latest_claims(reversed(original))
    assert derive_coverage_state(row["coverage_state"] for row in selected) == expected
    assert [row["coverage_state"] for row in selected] == expected_states
    component = current_coverages(catalog, "repo")[0]
    assert (component["coverage_state"], component["observed_at_us"]) == (
        expected,
        expected_time,
    )
    assert [row["coverage_state"] for row in component["claims"]] == expected_states
    assert catalog.execute("SELECT count(*) FROM coverage_claims").fetchone()[0] == len(
        history
    )


@pytest.mark.parametrize("first_details", [None, "{}", '{ "original": true }'])
def test_duplicate_and_stale_input_are_noops_without_advisory_merge(
    catalog, first_details
):
    first = admit_claim(catalog, "scope", "complete", 10, first_details)
    before = catalog.total_changes
    existing = export_current_claims(catalog, "scope")
    assert decide_admission(existing, claim("complete", 10, '{"new":1}')) == "duplicate"
    assert decide_admission(existing, claim("partial", 9, '{"new":2}')) == "stale"
    assert admit_claim(catalog, "scope", "complete", 10, '{"new":1}') is None
    assert admit_claim(catalog, "scope", "partial", 9, '{"new":2}') is None
    assert catalog.total_changes == before
    assert export_current_claims(catalog, "scope") == [
        {"coverage_claim_id": first, **claim("complete", 10, first_details)}
    ]
    # Neither missing details nor different advisory text alters admissibility.
    assert decide_admission(existing, claim("unknown", 10)) == "insert"
    assert admit_claim(catalog, "scope", "unknown", 10) is not None
    assert current_coverages(catalog, "repo")[0]["coverage_state"] == "complete"
    assert admit_claim(catalog, "scope", "partial", 10, '{"new":3}') is not None
    component = current_coverages(catalog, "repo")[0]
    assert component["coverage_state"] == "conflict"
    assert [row["details_json"] for row in component["claims"]] == [
        first_details,
        '{"new":3}',
        None,
    ]
    assert "details_json" not in component


def test_export_transports_latest_set_and_repeated_admission_is_idempotent(catalog):
    for state, stamp in [
        ("complete", 1),
        ("complete", 2),
        ("partial", 2),
        ("unknown", 2),
    ]:
        admit_claim(catalog, "scope", state, stamp, '{"from":"source"}')
    exported = export_current_claims(catalog, "scope")
    assert len(exported) == 3
    assert {row["observed_at_us"] for row in exported} == {2}
    with sqlite3.connect(":memory:", autocommit=True) as destination:
        initialize(destination)
        for row in exported:
            assert (
                admit_claim(
                    destination,
                    "scope",
                    row["coverage_state"],
                    row["observed_at_us"],
                    row["details_json"],
                )
                is not None
            )
        before = destination.total_changes
        for row in reversed(exported):
            assert (
                admit_claim(
                    destination,
                    "scope",
                    row["coverage_state"],
                    row["observed_at_us"],
                    row["details_json"],
                )
                is None
            )
        assert destination.total_changes == before
        assert current_coverages(destination, "repo")[0]["coverage_state"] == "conflict"
        assert [
            {key: value for key, value in row.items() if key != "coverage_claim_id"}
            for row in export_current_claims(destination, "scope")
        ] == [
            {key: value for key, value in row.items() if key != "coverage_claim_id"}
            for row in exported
        ]


def test_current_output_filters_kind_without_inventing_an_empty_scope_claim(catalog):
    catalog.execute(
        "INSERT INTO coverage_scopes(coverage_scope_id,repository_id,kind) VALUES('empty','repo','api')"
    )
    admit_claim(catalog, "scope", "partial", 1)
    assert [row["kind"] for row in current_coverages(catalog, "repo")] == ["api", "git"]
    assert current_coverages(catalog, "repo", "api") == [
        {
            "coverage_scope_id": "empty",
            "repository_id": "repo",
            "change_request_id": None,
            "kind": "api",
            "observed_at_us": None,
            "coverage_state": "unknown",
            "claim_count": 0,
            "claims": [],
        }
    ]
    assert current_coverages(catalog, "repo", "absent") == []
    assert current_coverages(catalog, "absent") == []
    assert export_current_claims(catalog, "empty") == []


@pytest.mark.parametrize("stamp", [MIN_EPOCH_US, MAX_EPOCH_US])
def test_admission_preserves_full_int64_observation_time(catalog, stamp):
    admit_claim(catalog, "scope", "unknown", stamp)
    assert current_coverages(catalog, "repo")[0]["observed_at_us"] == stamp


@pytest.mark.parametrize(
    "scope,state,stamp",
    [
        (None, "complete", 1),
        ("", "complete", 1),
        ("scope", "conflict", 1),
        ("scope", "pending", 1),
        ("scope", None, 1),
        ("scope", "complete", None),
        ("scope", "complete", True),
        ("scope", "complete", 1.0),
        ("scope", "complete", "1"),
        ("scope", "complete", MIN_EPOCH_US - 1),
        ("scope", "complete", MAX_EPOCH_US + 1),
    ],
)
def test_invalid_claim_is_rejected_before_writing(catalog, scope, state, stamp):
    before = catalog.total_changes
    with pytest.raises(CatalogError) as error:
        admit_claim(catalog, scope, state, stamp)
    assert error.value.code == "INVALID_COVERAGE_CLAIM"
    assert catalog.total_changes == before


@pytest.mark.parametrize("details_json", ["null", "[]", '"text"', "broken JSON"])
def test_advisory_details_require_json_object_or_sql_null(catalog, details_json):
    with pytest.raises(sqlite3.IntegrityError):
        admit_claim(catalog, "scope", "complete", 1, details_json)
    assert export_current_claims(catalog, "scope") == []


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE coverage_claims SET coverage_state='partial'",
        "UPDATE coverage_claims SET details_json='{\"changed\":1}'",
        "UPDATE coverage_claims SET observed_at_us=2",
        "DELETE FROM coverage_claims",
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us) VALUES('scope','complete',1)",
        "INSERT OR IGNORE INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us) VALUES('scope','complete',1)",
        "INSERT OR REPLACE INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us) VALUES('scope','complete',1)",
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us) VALUES('scope','complete',1) ON CONFLICT(coverage_scope_id,observed_at_us,coverage_state) DO UPDATE SET details_json='{}'",
    ],
)
def test_structure_retains_immutable_claims_and_prevents_semantic_duplicates(
    catalog, statement
):
    admit_claim(catalog, "scope", "complete", 1)
    before = export_current_claims(catalog, "scope")
    with pytest.raises(sqlite3.IntegrityError):
        catalog.execute(statement)
    assert export_current_claims(catalog, "scope") == before


def test_scope_uniqueness_prevents_split_repository_coverage(catalog):
    with pytest.raises(sqlite3.IntegrityError):
        catalog.execute(
            "INSERT INTO coverage_scopes(coverage_scope_id,repository_id,kind) VALUES('duplicate','repo','git')"
        )


def test_claim_admission_participates_in_caller_rollback(catalog):
    catalog.execute("BEGIN IMMEDIATE")
    admit_claim(catalog, "scope", "complete", 0)
    assert catalog.in_transaction
    assert len(export_current_claims(catalog, "scope")) == 1
    catalog.execute("ROLLBACK")
    assert export_current_claims(catalog, "scope") == []


@pytest.mark.parametrize(
    "inputs,expected_state,expected_count",
    [
        ((("complete", 1), ("complete", 1)), "complete", 1),
        ((("complete", 1), ("partial", 1)), "conflict", 2),
        ((("partial", 0), ("complete", 1)), "complete", None),
    ],
)
def test_competing_writers_observe_atomic_duplicate_and_timestamp_admission(
    tmp_path, inputs, expected_state, expected_count
):
    path = tmp_path / "concurrent.sqlite3"
    with sqlite3.connect(path, autocommit=True) as connection:
        initialize(connection)
    barrier = Barrier(2)

    def write(value):
        with sqlite3.connect(path, autocommit=True, timeout=5) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA recursive_triggers=ON")
            barrier.wait(timeout=5)
            return admit_claim(connection, "scope", *value)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, inputs))
    with sqlite3.connect(path, autocommit=True) as connection:
        component = current_coverages(connection, "repo")[0]
        assert component["coverage_state"] == expected_state
        assert component["observed_at_us"] == 1
        if expected_count is not None:
            assert sum(result is not None for result in results) == expected_count
            assert component["claim_count"] == expected_count
        before = connection.total_changes
        assert admit_claim(connection, "scope", "unknown", 0) is None
        assert connection.total_changes == before


def test_domain_helpers_reject_cross_scope_claim_sets_and_ignore_advisory_content():
    first = claim("unknown", 0, "arbitrary advisory text")
    assert latest_claims([first]) == (first,)
    assert decide_admission([], first) == "insert"
    assert decide_admission([first], claim("complete", 0)) == "insert"
    assert decide_admission([first], claim("unknown", 1)) == "insert"
    with pytest.raises(ValueError):
        latest_claims([first, claim("complete", 0, scope="different")])
    with pytest.raises(ValueError):
        decide_admission([first], claim("complete", 0, scope="different"))
    with pytest.raises(ValueError):
        derive_coverage_state(["conflict"])
