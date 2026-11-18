"""Shared authored advisory grammar at Python and actual Repository/Context SQL edges."""

import json
import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.domain.authored_metadata import MAX_AUTHORED_BYTES
from repo_catalog.domain.coverage_details import validate_coverage_details
from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope
from repo_catalog.domain.shared_values import encode
from tests.integration.p1.test_context import REPO, context

__all__ = ["context"]

BAD_DETAILS = (
    "null",
    "[]",
    "1",
    '"text"',
    "{broken}",
    '{"raw_api_response":{"data":{"body":"synthetic original"}}}',
    '{"encoded_response":"c3ludGhldGlj"}',
    '{"reason":{"data":{"body":"synthetic original"}}}',
    '{"missing":[{"kind":"pr","reason":{"body":"synthetic original"}}]}',
    '{"detail":{"body":"original"}}',
    '{"missing":[{"body":"original","reason":"missing"}]}',
    '{"original":"encoded original"}',
    '{"reason":"first","reason":"second"}',
    '{"reason":"first", "detail":"noncanonical"}',
    '{"refs_checked":true}',
    '{"refs_checked":-1}',
    '{"refs_checked":9223372036854775808}',
    '{"capture_uuidv4":"encoded-original"}',
)


@pytest.fixture(params=["repository", "context"])
def advisory_database(tmp_path, request):
    role = request.param
    repository = str(uuid4())
    path = tmp_path / (role + ".sqlite3")
    initialize(path, role, repository, str(uuid4()))
    db = connect(path, role)
    if role == "context":
        db.execute("INSERT INTO repository_context VALUES(?,?)", (repository, "{}"))
    coordinates = encode((repository, "guard"))
    db.execute(
        "INSERT INTO coverage_scopes(owner_kind,owner_coordinates_json,repository_uuidv4,coverage_kind) VALUES('repository',?,?,?)",
        (coordinates, repository, "guard"),
    )
    try:
        yield db, coordinates
    finally:
        db.close()


def test_original_carriers_and_nonobjects_fail_python_and_real_sql(advisory_database):
    db, coordinates = advisory_database
    scope = CoverageScope.repository(REPO, "guard")
    for details in BAD_DETAILS:
        with pytest.raises((TypeError, ValueError)):
            CoverageClaim(scope, 1, "partial", details)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO coverage_claims VALUES('repository',?,1,'partial',?)",
                (coordinates, details),
            )
        assert db.execute("SELECT count(*) FROM coverage_claims").fetchone()[0] == 0
    assert [row[1] for row in db.execute("PRAGMA table_xinfo(coverage_claims)")] == [
        "owner_kind",
        "owner_coordinates_json",
        "observed_at_us",
        "coverage_state",
        "details_json",
    ]


def test_large_legitimate_advisory_and_null_roundtrip_verbatim(advisory_database):
    db, coordinates = advisory_database
    details = encode(
        {
            "capture_origin_uuidv4": str(uuid4()),
            "capture_uuidv4": str(uuid4()),
            "retained_count": 3,
            "metadata_only_count": 2,
            "nominal_missing_count": 1,
            "refs_checked": 4,
            "detail": "x" * 65536,
            "reason": 'Domain prose may mention body or encoded_response; "response" is not scanned.',
            "missing": [
                {
                    "kind": "notes",
                    "reason": "not observed",
                    "role": "root",
                    "roles": ["direct", "peeled"],
                }
            ],
        }
    )
    assert validate_coverage_details(details) == json.loads(details)
    assert validate_coverage_details(None) is None
    for stamp, value in ((1, None), (2, "{}"), (3, details)):
        db.execute(
            "INSERT INTO coverage_claims VALUES('repository',?,?,'partial',?)",
            (coordinates, stamp, value),
        )
    assert [
        row[0]
        for row in db.execute(
            "SELECT details_json FROM coverage_claims ORDER BY observed_at_us"
        )
    ] == [None, "{}", details]


@pytest.mark.parametrize("value", [1, True, b"{}", {}, [], "{}\n"])
def test_advisory_validation_is_strict_before_sqlite_affinity(value):
    with pytest.raises((ValueError, TypeError)):
        CoverageClaim(CoverageScope.repository(REPO, "guard"), 1, "partial", value)


def test_advisory_input_is_finite_before_json_parsing():
    with pytest.raises(ValueError, match="finite byte limit"):
        validate_coverage_details(encode({"detail": "x" * MAX_AUTHORED_BYTES}))
    with pytest.raises(ValueError, match="finite depth limit"):
        validate_coverage_details('{"missing":' + "[" * 13 + "]" * 13 + "}")
    with pytest.raises(ValueError, match="finite element limit"):
        validate_coverage_details(encode({"missing": [None] * 4096}))


def test_advisory_counts_and_descriptions_never_prove_complete(context):
    _db, store, _path = context
    scope = CoverageScope.repository(REPO, "guard")
    store.scope(scope)
    claim = CoverageClaim(
        scope,
        1,
        "complete",
        '{"reason":"complete","refs_checked":1000,"retained_count":1000}',
    )
    assert store.admit_coverage(claim) == "insert"
    result = store.coverage(scope)
    assert result.claims == (claim,)
    assert result.state == "unknown"
    assert not result.known_empty
