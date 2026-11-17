"""Current-field pruning never permits in-place original evidence rebinding."""

import sqlite3
from dataclasses import replace

import pytest

from repo_catalog.domain.p1_context import FieldCandidate, FieldClock, canonical
from tests.integration.p1.test_context import (
    KEY,
    REPO,
    SERVICE,
    SOURCE,
    candidate,
    context,
)

__all__ = ["context"]


@pytest.mark.parametrize(
    "column,value",
    [
        ("field_name", "metadata.never-observed"),
        ("field_name", '["\\u0074itle"]'),
        ("value_json", '"different original value"'),
        ("clock_json", '{"at_us":20,"domain":"provider.updated_at"}'),
        ("observed_at_us", 20),
        (
            "provenance_json",
            canonical(
                {
                    "source": "provider.example",
                    "evidence": {
                        "source_registration_uuidv4": SOURCE,
                        "resource_path": "/repos/owner/B/issues/7/comments",
                    },
                }
            ),
        ),
        (
            "provenance_json",
            canonical(
                {
                    "source": "provider.example",
                    "evidence": {
                        "source_registration_uuidv4": "unregistered-and-not-a-uuid"
                    },
                }
            ),
        ),
        (
            "provenance_json",
            canonical(
                {
                    "source": "provider.example",
                    "evidence": {
                        "source_registration_uuidv4": "80f5c4f9-6d6b-4691-af3c-00ab02ad9f54"
                    },
                }
            ),
        ),
        (
            "provenance_json",
            canonical(
                {
                    "source": "provider.example",
                    "evidence": {
                        "service_instance_uuidv4": "6eb0350d-95e0-479d-ac57-f0f3b68ced2c"
                    },
                }
            ),
        ),
        (
            "provenance_json",
            canonical(
                {
                    "source": "provider.example",
                    "evidence": {"repository_uuidv4": "unregistered-and-not-a-uuid"},
                }
            ),
        ),
        ("provider_resource_id", '"different-identity"'),
    ],
    ids=[
        "unobserved-field",
        "alternate-path-spelling",
        "value",
        "clock-refinement",
        "observation-time",
        "capture-source-path",
        "malformed-detached-source",
        "different-detached-source",
        "different-service",
        "malformed-detached-repository",
        "identity",
    ],
)
@pytest.mark.parametrize("mode", ["autocommit", "transaction", "savepoint"])
def test_field_original_update_cannot_rebind_producer_time_value_or_key(
    context, column, value, mode
):
    db, store, _path = context
    original = replace(
        candidate("original", observed=10),
        provenance_json=canonical(
            {
                "source": "provider.example",
                "evidence": {
                    "source_registration_uuidv4": SOURCE,
                    "service_instance_uuidv4": SERVICE,
                    "repository_uuidv4": REPO,
                    "resource_path": "/repos/owner/A/issues/7/comments",
                },
            }
        ),
    )
    store.admit_field(original)
    before = tuple(store.candidates(KEY, "title"))
    if mode == "transaction":
        db.execute("BEGIN")
    elif mode == "savepoint":
        db.execute("SAVEPOINT attempt")
    try:
        with pytest.raises(
            sqlite3.IntegrityError, match="immutable original field candidate"
        ):
            db.execute(f'UPDATE field_candidates SET "{column}"=?', (value,))
        assert store.candidates(KEY, "title") == before
        assert store.candidates(KEY, "metadata.never-observed") == ()
    finally:
        if mode == "transaction":
            db.rollback()
        elif mode == "savepoint":
            db.execute("ROLLBACK TO attempt")
            db.execute("RELEASE attempt")
    assert not db.execute("PRAGMA foreign_key_check").fetchall()


def test_independent_original_insert_and_comparable_pruning_remain_supported(context):
    db, store, _path = context
    first = candidate("first", clock=10, observed=10)
    unknown = candidate("unknown", clock=None, evidence="other-capture", observed=11)
    for original in (first, unknown):
        assert store.admit_field(original) == "insert"
    newer = FieldCandidate(
        KEY,
        "title",
        '"newer"',
        FieldClock(first.clock.domain, 20),
        canonical({"source": "provider.example", "evidence": "genuine-new-original"}),
        30,
    )
    assert store.admit_field(newer) == "insert"
    assert set(store.candidates(KEY, "title")) == {unknown, newer}
    assert store.admit_field(newer) == "duplicate"
    assert store.admit_field(first) == "stale"
    assert db.execute("SELECT count(*) FROM field_candidates").fetchone()[0] == 2
