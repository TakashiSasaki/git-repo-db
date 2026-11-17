"""Scoped Context cursors expose exact insert metadata without a SQL escape."""

import sqlite3
from contextlib import closing

import pytest

from repo_catalog.adapters.sqlite.admission_transaction import AdmissionTransaction
from repo_catalog.adapters.sqlite.production_context import _GuardedCursor


@pytest.mark.parametrize("coordinator", [False, True], ids=["sqlite", "coordinator"])
def test_guarded_cursor_counts_real_insert_and_noop_for_both_trusted_cursor_types(
    coordinator,
):
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as db:
        db.execute("CREATE TABLE evidence (value TEXT PRIMARY KEY) STRICT")
        db.execute("BEGIN")
        owner = AdmissionTransaction(db) if coordinator else db
        completions, errors = [], []
        for expected in (1, 0):
            cursor = owner.execute(
                "INSERT INTO evidence VALUES(?) ON CONFLICT DO NOTHING", ("original",)
            )
            guarded = _GuardedCursor(
                cursor, errors.append, lambda: completions.append(True)
            )
            assert guarded.rowcount == expected
            assert not hasattr(guarded, "connection")
            assert not hasattr(guarded, "execute")
            guarded.close()
        assert not errors
        assert len(completions) >= 2
        assert db.execute("SELECT count(*) FROM evidence").fetchone() == (1,)
        # The trusted test owner ends the outer transaction; the coordinator
        # facade deliberately cannot grant transaction completion to its caller.
        db.set_authorizer(None)
        db.rollback()
