"""Existing authority validation failures stop before releasing its read gate."""

from contextlib import closing

import pytest

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
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
def test_paired_validation_udf_failure_persists_stop(tmp_path, damaged):
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
