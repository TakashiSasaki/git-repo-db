"""Salvage must not silently repair missing required destination authority."""

import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.core_recovery import RecoveryWorkBudget
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_schema import (
    expected_schema,
    register_functions,
    schema_rows,
)
from repo_catalog.adapters.sqlite.recovery_validation import (
    verify_existing_context_text,
)
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.recovery import CorruptionDetectedError
from tests.integration.p7.test_context_corruption_stop import (
    _candidate as _text_candidate,
)
from tests.integration.p7.test_context_corruption_stop import _text
from tests.integration.p7.test_exact_replay import _authority, _candidate, _merge
from tests.support.context_admission import fixture_context, fixture_service


def _context_fields(catalog, fields):
    from repo_catalog.adapters.sqlite.p1_schema import connect

    service_id = "99999999-9999-4999-8999-999999999999"
    key = ResourceKey.from_native(service_id, "issue", "42")
    authorization, _ = fixture_service(
        DependencySet(
            resources={key},
            provider_registrations={service_id},
        )
    )
    db = connect(catalog / "context.sqlite3", "context")
    try:
        db.execute("INSERT INTO providers VALUES(?,?,?)", (service_id, "github", "{}"))
        store = ContextStore(db, authorization=authorization)
        with store.admission_transaction(admission=fixture_context(authorization)):
            store.resource(key, None)
            for field, value in fields:
                store.admit_field(
                    FieldCandidate(
                        key,
                        field,
                        canonical(value),
                        FieldClock("provider.updated_at", 1),
                        canonical({"source": "independent", "evidence": "event42"}),
                        1,
                    )
                )
    finally:
        db.close()


def _delete(catalog, role, table):
    with sqlite3.connect(catalog / f"{role}.sqlite3") as db:
        register_functions(db)
        name = (
            "text_bodies_no_delete"
            if role == "context"
            else f"p1_immutable_{table}_delete"
        )
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name=?", (name,)
        ).fetchone()[0]
        db.execute(f"DROP TRIGGER {name}")
        db.execute(f"DELETE FROM {table}")
        db.execute(trigger)
        db.commit()
        assert schema_rows(db) == expected_schema(role)


def test_missing_required_context_body_stops_instead_of_reinsertion(
    synthetic_catalog, tmp_path
):
    digest, text = _text(synthetic_catalog)
    _context_fields(synthetic_catalog, [("text_body_sha256", digest)])
    _delete(synthetic_catalog, "context", "text_bodies")
    source = _text_candidate(tmp_path, digest, text)
    from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter

    with pytest.raises(
        CorruptionDetectedError, match="required retained Context text is missing"
    ):
        SQLiteRecoveryAdapter().merge_salvage(synthetic_catalog, source)
    with sqlite3.connect(synthetic_catalog / "context.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM text_bodies").fetchone() == (0,)
    assert (synthetic_catalog / "p1-recovery-stop.json").is_file()


def test_missing_referenced_metadata_copy_stops_instead_of_reinsertion(
    synthetic_catalog, tmp_path
):
    candidate = _candidate(synthetic_catalog, "retained_metadata")
    _delete(synthetic_catalog, "core", "retained_metadata")
    before = _authority(synthetic_catalog)
    with pytest.raises(
        CorruptionDetectedError, match="required retained metadata copy is missing"
    ):
        _merge(synthetic_catalog, tmp_path, candidate)
    assert _authority(synthetic_catalog) == before
    assert (synthetic_catalog / "p1-recovery-stop.json").is_file()


def test_absence_check_stops_at_finite_vm_work_without_claiming_healthy(
    synthetic_catalog,
):
    _context_fields(
        synthetic_catalog, [(f"unrelated-{index}", "x") for index in range(100)]
    )
    with sqlite3.connect(synthetic_catalog / "context.sqlite3") as db:
        work = RecoveryWorkBudget(work_limits={"metadata_units": 2})
        with pytest.raises(CoreFailure) as failure:
            verify_existing_context_text(db, "f" * 64, b"new", 1024, work)
        assert failure.value.code == "BUDGET"
        assert work.usage["metadata_units"] == 2
        # The interrupted query releases its VM handler; ordinary inspection works.
        assert db.execute("SELECT 1").fetchone() == (1,)
    assert not (synthetic_catalog / "p1-recovery-stop.json").exists()


def test_new_unreferenced_text_still_admits(synthetic_catalog, tmp_path):
    from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter

    source = tmp_path / "new.jsonl"
    source.write_text(
        json.dumps(
            {
                "candidate_type": "context_document",
                "payload": {"text_value": "new independent body"},
            }
        )
        + "\n"
    )
    receipt = SQLiteRecoveryAdapter().merge_salvage(synthetic_catalog, source)
    assert receipt.admitted_units == 1
    assert not (synthetic_catalog / "p1-recovery-stop.json").exists()
