"""Existing authority validation failures stop before releasing its read gate."""

import sqlite3
from contextlib import closing

import pytest

from repo_catalog.adapters.sqlite import p1_coordination
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_coordination import (
    PairCoordinator,
    ReadSnapshot,
    validate_pair,
)
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_coordination import CoordinationError
from tests.integration.p1.test_coordination import (
    PROVIDER,
    build,
    context_unit,
    core_unit,
)


@pytest.mark.parametrize("damaged", ["provider", "field"])
@pytest.mark.parametrize("capability", [False, True])
def test_paired_validation_udf_failure_persists_stop(tmp_path, damaged, capability):
    directory = tmp_path / "catalog"
    build(directory)
    coordinator = PairCoordinator(directory)

    def context(tx):
        context_unit(tx)
        ContextStore(tx).admit_field(
            FieldCandidate(
                ResourceKey(PROVIDER, "issue", "7"),
                "title",
                canonical("actual title"),
                FieldClock("provider", 1),
                canonical({"source": "provider.example", "evidence": "event-7"}),
                1,
            )
        )

    coordinator.admit(core_unit, context)
    with closing(connect(directory / "context.sqlite3", "context")) as db:
        # Fault injection into a disposable store, outside supported admission.
        # This produces real invalid UTF-8 TEXT, so integrity_check cannot run
        # the registered semantic CHECK UDF. SQLite reports SQLITE_ERROR, not
        # SQLITE_CORRUPT; treating only the latter as corruption misses the stop.
        db.execute("PRAGMA ignore_check_constraints=ON")
        if damaged == "provider":
            db.execute("UPDATE providers SET configuration_json=CAST(X'ff' AS TEXT)")
        else:
            db.execute("UPDATE field_candidates SET value_json=CAST(X'ff' AS TEXT)")
    if capability:
        # Exercise owner notification before a caller can swallow the error.
        # Trusted test connections avoid initial validation intercepting this
        # already damaged fixture before testing the capability validation path.
        with (
            closing(connect(directory / "core.sqlite3", "core")) as core,
            closing(connect(directory / "context.sqlite3", "context")) as context,
        ):
            readers = [
                ReadSnapshot(
                    db, coordinator._check_running, coordinator._record_corruption
                )
                for db in (core, context)
            ]
            with pytest.raises(CoordinationError, match="CORRUPTION"):
                validate_pair(*readers)
            assert (directory / "p1-recovery-stop.json").exists()
    else:
        with pytest.raises(CoordinationError, match="CORRUPTION"):
            with coordinator.snapshots():
                pytest.fail("damaged authority was certified")
    assert (directory / "p1-recovery-stop.json").exists()
    for role in ("operational", "search"):
        (directory / f"{role}.sqlite3").unlink()
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        PairCoordinator(directory).admit(lambda tx: None, lambda tx: None)
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        with PairCoordinator(directory).core_snapshot():
            pytest.fail("derivative loss cleared the stop")


def test_cancelled_validation_does_not_diagnose_corruption(tmp_path, monkeypatch):
    directory = tmp_path / "catalog"
    build(directory)
    original = p1_coordination.validate_pair

    def interrupted(core, context):
        core.set_progress_handler(lambda: 1, 1)
        try:
            return original(core, context)
        finally:
            core.set_progress_handler(None, 0)

    monkeypatch.setattr(p1_coordination, "validate_pair", interrupted)
    with pytest.raises(sqlite3.OperationalError) as error:
        with PairCoordinator(directory).snapshots():
            pytest.fail("cancelled validation returned success")
    assert error.value.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT
    assert not (directory / "p1-recovery-stop.json").exists()
    monkeypatch.setattr(p1_coordination, "validate_pair", original)
    with PairCoordinator(directory).snapshots():
        pass
