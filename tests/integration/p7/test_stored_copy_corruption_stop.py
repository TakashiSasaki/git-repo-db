"""Existing physical copies are boundedly rechecked before salvage replay."""

import sqlite3

import pytest

from repo_catalog.adapters.sqlite.core_recovery import RecoveryWorkBudget
from repo_catalog.adapters.sqlite.p1_schema import (
    expected_schema,
    register_functions,
    schema_rows,
)
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.recovery import CorruptionDetectedError, RecoveryBudget
from tests.integration.p7.test_exact_replay import _authority, _candidate, _merge


def _damage(catalog, table, column, value):
    with sqlite3.connect(catalog / "core.sqlite3") as db:
        register_functions(db)
        trigger = f"p1_immutable_{table}_update"
        sql = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name=?", (trigger,)
        ).fetchone()[0]
        db.execute(f"DROP TRIGGER {trigger}")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(f"UPDATE {table} SET {column}=?", (value,))
        db.execute(sql)
        db.commit()
        assert schema_rows(db) == expected_schema("core")


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("retained_metadata", "size", 999),
        ("retained_metadata", "native_type", "blob"),
        ("retained_metadata", "body", b"damaged native bytes"),
    ],
)
def test_invalid_existing_physical_copy_stops_without_repair(
    restored_catalog, tmp_path, table, column, value
):
    candidate = _candidate(restored_catalog, table)
    _damage(restored_catalog, table, column, value)
    before = _authority(restored_catalog)
    with pytest.raises(CorruptionDetectedError, match="destination Core corruption"):
        _merge(restored_catalog, tmp_path, candidate)
    assert (restored_catalog / "p1-recovery-stop.json").exists()
    assert _authority(restored_catalog) == before


@pytest.mark.parametrize("table", ["retained_metadata"])
@pytest.mark.parametrize("refusal", ["payload", "verification"])
def test_existing_copy_resource_refusal_never_claims_corruption(
    restored_catalog, table, refusal
):
    payload = _candidate(restored_catalog, table)["payload"]
    work = (
        RecoveryWorkBudget(work_limits={"verification_bytes": 1})
        if refusal == "verification"
        else RecoveryWorkBudget()
    )
    budget = (
        RecoveryBudget(max_payload_bytes=1)
        if refusal == "payload"
        else RecoveryBudget()
    )
    with pytest.raises(CoreFailure) as error:
        SQLiteRecoveryAdapter()._verify_existing_retained_copy(
            restored_catalog,
            table,
            (
                payload["object_format"],
                payload["object_oid"],
                payload["physical_copy_uuidv4"],
            ),
            budget,
            work,
        )
    assert error.value.code == "BUDGET"
    assert not (restored_catalog / "p1-recovery-stop.json").exists()
