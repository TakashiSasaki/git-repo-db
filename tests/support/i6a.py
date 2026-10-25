"""Explicit disposable harness; never a normal product catalog opening path."""

import sqlite3
from contextlib import contextmanager

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.domain.resource_stage import (
    TRANSFER_FENCE_DEFINITIONS,
    _isolated_transfer_fixture,
    has_transfer_fence,
)


@contextmanager
def isolated_context_db():
    """Create, verify, unfence and close one fresh in-memory synthetic Context."""
    db = sqlite3.connect(":memory:", isolation_level=None)
    try:
        p1_schema.register_functions(db)
        p1_schema.configure(db)
        db.executescript(p1_schema.compose("context"))
        db.execute(
            "INSERT INTO store_identity VALUES('context',?,?)",
            (
                "9ebbe38a-f937-40e6-a99c-701835ebcf10",
                "aad25448-03eb-4f83-a75e-cb7055fd33be",
            ),
        )
        p1_schema.validate(db, "context")
        assert has_transfer_fence(db)
        for _, name, _, _ in TRANSFER_FENCE_DEFINITIONS:
            db.execute(f"DROP TRIGGER {name}")
        expected = tuple(
            row
            for row in p1_schema.expected_schema("context")
            if row not in TRANSFER_FENCE_DEFINITIONS
        )
        assert p1_schema.schema_rows(db) == expected
        p1_schema.verify_connection(db)
        with _isolated_transfer_fixture(db) as fixture:
            yield fixture
    finally:
        if db.in_transaction:
            db.rollback()
        db.close()
