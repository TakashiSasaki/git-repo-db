"""Operation regressions for generated Core/Context persistence bindings."""

from dataclasses import replace
from uuid import uuid4

import pytest
from repo_catalog.adapters.sqlite.context_rows import ROW_TYPES as CONTEXT_ROWS

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_core import Core
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageScope,
    FieldClock,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_core import OID, CoreFailure, Provenance, ScalarClaim
from tests.integration.p1.test_context import KEY, PROVENANCE, REPO, context
from tests.integration.p1.test_core import Budget

__all__ = ["context"]


def test_core_exact_replay_uses_declared_columns_and_compares_payload(tmp_path):
    path = tmp_path / "core.sqlite3"
    initialize(path, "core", str(uuid4()), str(uuid4()))
    core = Core(path)
    statements = []
    core._db.set_trace_callback(statements.append)
    claim = ScalarClaim(
        OID("sha1", "a" * 40),
        "size",
        7,
        Provenance("source", "observation", "size", "parser", "1"),
    )
    try:
        core.admit_claim(claim)
        core.admit_claim(claim)
        with pytest.raises(CoreFailure) as conflict:
            core.admit_claim(replace(claim, value=8))
        assert conflict.value.code == "INCOMPATIBLE_REPLAY"
        projection = core.scalar(claim.subject, "size")
        assert projection.canonical is None
        assert projection.alternatives[0]["value"] == ["known", 7]
        assert projection.alternatives[0]["checked"] is False
        assert not any("LIMIT 0" in sql for sql in statements)
    finally:
        core.close()


def test_core_row_binding_refuses_boolean_before_sqlite_integer_coercion(tmp_path):
    path = tmp_path / "core.sqlite3"
    initialize(path, "core", str(uuid4()), str(uuid4()))
    core = Core(path)
    statements = []
    core._db.set_trace_callback(statements.append)
    try:
        with pytest.raises((TypeError, ValueError)):
            with core._transaction():
                core._insert(
                    "ref_enumeration_links",
                    (
                        "origin",
                        "enumeration",
                        "origin",
                        "observation",
                        "[]",
                        "item",
                        True,
                    ),
                )
        assert not any("INSERT INTO ref_enumeration_links" in sql for sql in statements)
        core.admit_object(OID("sha1", "a" * 40))
    finally:
        core.close()


def test_core_full_row_export_keeps_derived_checked_projection(tmp_path):
    path = tmp_path / "core.sqlite3"
    initialize(path, "core", str(uuid4()), str(uuid4()))
    core = GitCore(path)
    claim = ScalarClaim(
        OID("sha1", "a" * 40),
        "size",
        7,
        Provenance("source", "observation", "size", "parser", "1"),
    )
    work = Budget()
    try:
        core.admit_claim(claim)
        rows = core.exchange_metadata_rows("scalar_claims", (), work)
        assert len(rows) == 1
        assert tuple(rows[0]) == (*claim.key, 0)
        assert work.counts["metadata_units"] == 1
        assert work.counts["input_bytes"] > 0
    finally:
        core.close()


def test_context_binding_preserves_sql_order_generated_values_and_replay(context):
    db, store, _ = context
    relation = ResourceRepositoryRelation(
        KEY,
        "owning_repository",
        FieldClock("provider.updated_at", 2),
        canonical(REPO),
        PROVENANCE,
        10,
    )
    assert store.admit_repository_relation(relation) == "insert"
    cursor = db.execute("SELECT * FROM resource_repository_relations")
    row = CONTEXT_ROWS["resource_repository_relations"].from_record(
        dict(
            zip(
                (column[0] for column in cursor.description),
                cursor.fetchone(),
                strict=True,
            )
        )
    )
    assert row.clock_json == relation.clock_json
    assert row.target_json == relation.target_json
    assert row.repository_uuidv4 == REPO
    assert row.event_report_members_json is row.event_report_scope_json is None
    assert row.key_values() == relation.claim_key.coordinates()
    assert store.admit_repository_relation(relation) == "duplicate"
    with pytest.raises(ValueError, match="Original observation time changed"):
        store.admit_repository_relation(replace(relation, observed_at_us=11))


def test_context_scope_nulls_and_coverage_predicates_stay_operation_scoped(context):
    db, store, _ = context
    scope = CoverageScope.repository(REPO, "inventory")
    store.scope(scope)
    cursor = db.execute("SELECT * FROM coverage_scopes")
    row = CONTEXT_ROWS["coverage_scopes"].from_record(
        dict(
            zip(
                (column[0] for column in cursor.description),
                cursor.fetchone(),
                strict=True,
            )
        )
    )
    assert row.repository_uuidv4 == REPO
    assert row.source_registration_uuidv4 is row.field_name is None
    original = CoverageClaim(scope, 10, "partial", '{"original":true}')
    assert store.admit_coverage(original) == "insert"
    assert store.admit_coverage(replace(original, details_json="{}")) == "duplicate"
    assert store.admit_coverage(replace(original, observed_at_us=9)) == "stale"
    assert db.execute("SELECT details_json FROM coverage_claims").fetchall() == [
        ('{"original":true}',)
    ]
