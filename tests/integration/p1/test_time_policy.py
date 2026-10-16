"""ADR 0028 separates unknown/positive observations from signed Git instants."""

import json
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope, FieldClock
from repo_catalog.domain.p1_core import GitObservation, RepositoryClaim, ScalarClaim
from repo_catalog.domain.production_context import (
    CollectionObservation,
    ResourceRelation,
    SourceInventory,
)
from repo_catalog.domain.time import (
    MAX_EPOCH_US,
    MIN_EPOCH_US,
    parse_iso8601_us,
    unix_seconds_to_us,
    validate_epoch_us,
    validate_observation_us,
    validate_required_observation_us,
)
from tests.integration.p1.test_context import KEY, PROVENANCE, candidate, context
from tests.integration.p1.test_core import core, oid, provenance

__all__ = ["context", "core"]

INVALID_OBSERVATIONS = [
    MIN_EPOCH_US - 1,
    MIN_EPOCH_US,
    -1,
    0,
    MAX_EPOCH_US + 1,
    True,
    False,
    1.0,
    "1",
]


@pytest.mark.parametrize("stamp", [None, 1, MAX_EPOCH_US])
def test_nullable_provider_and_observation_round_trip(context, stamp):
    db, store, _ = context
    value = candidate(None, clock=stamp, observed=stamp)
    assert store.admit_field(value) == "insert"
    assert store.candidates(KEY, "title") == (value,)
    assert db.execute(
        "SELECT observed_at_us,source_clock_us FROM field_candidates"
    ).fetchone() == (stamp, stamp)
    assert store.admit_field(value) == "duplicate"


@pytest.mark.parametrize("stamp", INVALID_OBSERVATIONS)
def test_observation_and_provider_reject_invalid_original_types(stamp):
    with pytest.raises((TypeError, ValueError)):
        validate_observation_us(stamp)
    with pytest.raises((TypeError, ValueError)):
        FieldClock("provider.edit", stamp)
    with pytest.raises((TypeError, ValueError)):
        candidate("title", observed=stamp)


@pytest.mark.parametrize("stamp", [None, *INVALID_OBSERVATIONS])
def test_required_coverage_and_terminal_coordinates_fail_closed(stamp):
    scope = CoverageScope.resource(KEY, "presence")
    with pytest.raises((TypeError, ValueError)):
        validate_required_observation_us(stamp)
    with pytest.raises((TypeError, ValueError)):
        CoverageClaim(scope, stamp, "unknown")
    with pytest.raises((TypeError, ValueError)):
        CollectionObservation(KEY, "comments", PROVENANCE, "{}", stamp, "unknown")
    with pytest.raises((TypeError, ValueError)):
        SourceInventory(str(uuid4()), "{}", stamp, "unknown", False, (), PROVENANCE)


def test_unknown_clock_never_orders_or_overwrites_candidates(context):
    _, store, _ = context
    unknown = candidate("unclocked", clock=None, observed=None)
    known = candidate(None, clock=1, observed=1)
    store.admit_field(unknown)
    store.admit_field(known)
    assert set(store.candidates(KEY, "title")) == {unknown, known}
    assert store.candidates(KEY, "missing") == ()
    assert json.loads(known.value_json) is None
    with pytest.raises(ValueError, match="observation time"):
        store.admit_field(replace(unknown, observed_at_us=1))
    assert (
        ResourceRelation(KEY, "references", (), PROVENANCE, "{}", None).observed_at_us
        is None
    )


@pytest.mark.parametrize("stamp", [MIN_EPOCH_US, -1, 0, 1, MAX_EPOCH_US])
def test_git_native_signed_values_remain_exact(core, stamp):
    store, _, _ = core
    assert validate_epoch_us(stamp) == stamp
    for field in ("author_time_us", "committer_time_us"):
        claim = ScalarClaim(oid(), field, stamp, provenance(coordinate=field))
        store.admit_claim(claim)
        assert store.scalar(oid(), field).alternatives[0]["value"] == ["known", stamp]


@pytest.mark.parametrize("stamp", [None, 1, MAX_EPOCH_US])
def test_core_storage_does_not_make_observation_git_native(core, stamp):
    store, _, repository = core
    original = provenance()
    claim = RepositoryClaim(repository, "observation_us", stamp, original)
    store.admit_repository_claim(claim)
    observation = GitObservation(
        str(uuid4()),
        str(uuid4()),
        repository,
        "ref",
        ("refs/heads/a",),
        {"ref": "refs/heads/a", "target": list(oid().key), "observed_at_us": stamp},
        original,
    )
    store.admit_observation(observation)
    if stamp is None:
        with pytest.raises(ValueError, match="terminal"):
            replace(
                observation, value={**observation.value, "terminal_observation": True}
            )


@pytest.mark.parametrize(
    "stamp", [MIN_EPOCH_US, -1, 0, True, 1.0, "1", MAX_EPOCH_US + 1]
)
def test_json_clock_preserves_original_type_and_rejects_invalid_values(context, stamp):
    db, _, _ = context
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                *KEY.coordinates(),
                "title",
                "null",
                json.dumps(
                    {"at_us": stamp, "domain": "provider.edit"},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                PROVENANCE,
                None,
            ),
        )


@pytest.mark.parametrize("stamp", [-1, 0])
def test_sql_stored_observation_range_is_enforced(context, stamp):
    db, _, _ = context
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (
                *KEY.coordinates(),
                "title",
                "null",
                FieldClock("provider.edit", None).encode(),
                PROVENANCE,
                stamp,
            ),
        )
    # SQLite applies column affinity before CHECK. The API test above, not SQL,
    # proves rejection of original bool/float/numeric-string input types.


def test_external_units_are_converted_only_at_explicit_boundary():
    assert unix_seconds_to_us(1) == 1_000_000
    assert validate_observation_us(1) == 1  # No magnitude-based unit guessing.
    assert parse_iso8601_us("1970-01-01T00:00:01Z") == 1_000_000
    for value in (0, -1):
        assert validate_epoch_us(unix_seconds_to_us(value)) == value * 1_000_000
        with pytest.raises(ValueError):
            validate_observation_us(unix_seconds_to_us(value))


@pytest.mark.parametrize(
    "stamp", [True, False, 1.0, "1", MIN_EPOCH_US - 1, MAX_EPOCH_US + 1]
)
def test_git_native_timestamp_never_coerces_original_input(stamp):
    with pytest.raises((TypeError, ValueError)):
        validate_epoch_us(stamp)
    with pytest.raises(ValueError):
        ScalarClaim(oid(), "author_time_us", stamp, provenance())
