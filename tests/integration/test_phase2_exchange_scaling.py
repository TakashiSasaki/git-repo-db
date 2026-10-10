"""Conflict-free intake barriers avoid walking unrelated Git history."""

from repo_catalog.adapters.sqlite.exchange import Graph
from tests.integration.test_catalog3_exchange import catalog, fixture
from tests.integration.test_phase1_exchange_scaling import (
    _add_captures,
    _measure_vm_steps,
)


def test_conflict_free_barrier_refresh_is_bounded_under_real_history_growth():
    db = catalog()
    try:
        expected = fixture(db)
        before, _ = _measure_vm_steps(
            db, Graph(db, persist_identities=False).refresh_resolution_blocks
        )
        _add_captures(db, expected, 1000)
        statements = []
        db.set_trace_callback(statements.append)
        try:
            after, _ = _measure_vm_steps(
                db, Graph(db, persist_identities=False).refresh_resolution_blocks
            )
        finally:
            db.set_trace_callback(None)
        assert after <= before + 2000
        assert not any(
            "FROM STORED_BYTES" in sql.upper() or "FROM GIT_OBJECTS" in sql.upper()
            for sql in statements
        )
    finally:
        db.close()
