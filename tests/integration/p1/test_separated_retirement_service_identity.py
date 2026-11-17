"""Keep canonical service identity constraints in actual separated Context DDL."""

import sqlite3
from uuid import NAMESPACE_URL, uuid5

import pytest

from tests.integration.p1.test_context import context

__all__ = ["context"]


def test_actual_provider_table_rejects_noncanonical_or_non_v4_service_uuids(context):
    db, _, _ = context
    invalid = (
        "instance",
        str(uuid5(NAMESPACE_URL, "https://synthetic.invalid")),
        "00000000-0000-7000-8000-000000000101",
        "00000000-0000-4000-7000-000000000101",
        "550E8400-E29B-41D4-A716-446655440000",
        "00000000000040008000000000000101",
    )
    original = db.execute("SELECT * FROM providers").fetchall()
    for value in invalid:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO providers VALUES(?,?,?)", (value, "git", "{}"))
        assert db.execute("SELECT * FROM providers").fetchall() == original
