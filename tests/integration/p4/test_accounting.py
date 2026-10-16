"""Production Operational accounting with real SQLite and killed worker input.

SIGKILL proves process-interruption behavior, not host-power-loss durability.
"""

import contextlib
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_coordination import NotesWorkBudget, WorkLedger
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.domain.p1_coordination import (
    CoordinationError,
    NotesLimits,
    RequestIdentity,
)
from repo_catalog.domain.p1_core import CoreFailure


@pytest.fixture
def accounting(tmp_path):
    path = tmp_path / "operational.sqlite3"
    repository, instance = str(uuid4()), str(uuid4())
    initialize(path, "operational", repository, instance)
    with contextlib.closing(connect(path, "operational")) as db:
        ledger = WorkLedger(
            db, repository_uuidv4=repository, catalog_instance_uuidv4=instance
        )
        request = RequestIdentity(str(uuid4()), str(uuid4()))
        ledger.new_request(
            request,
            '{"intent":"notes"}',
            {unit: 10 for unit in NotesLimits.work_limits()},
        )
        attempt = str(uuid4())
        ledger.attempt(request, attempt)
        yield path, db, ledger, request, attempt


def budget(accounting):
    _, _, ledger, request, attempt = accounting
    return NotesWorkBudget(ledger, request, attempt, NotesLimits())


def test_production_defaults_are_finite_and_independent():
    assert NotesLimits().note_bytes == 16 * 1024 * 1024
    limits = NotesLimits.work_limits()
    assert limits == {
        "input_bytes": 256 * 1024 * 1024,
        "verification_bytes": 2 * 1024 * 1024 * 1024,
        "metadata_units": 1_000_000,
        "proof_steps": 100_000,
    }
    limits["input_bytes"] = 0
    assert NotesLimits.work_limits()["input_bytes"] > 0


def test_failed_reservation_does_not_collide_on_resumed_attempt(accounting):
    _, db, ledger, request, _ = accounting
    work = budget(accounting)
    work.require("input_bytes", 8)
    work.charge("input_bytes", 8)
    with pytest.raises(CoreFailure, match="finite cumulative"):
        work.require("input_bytes", 3)
    ledger.increase_limit(request, "input_bytes", 20)
    work.require("input_bytes", 3)
    work.charge("input_bytes", 3)
    resumed = budget(accounting)
    resumed.require("input_bytes", 2)
    resumed.charge("input_bytes", 2)
    assert ledger.usage(request)["input_bytes"] == 13
    assert db.execute("SELECT count(*) FROM work_accounting").fetchone()[0] == 3


def test_two_budget_handles_same_attempt_allocate_independent_steps(accounting):
    first, second = budget(accounting), budget(accounting)
    first.require("metadata_units")
    second.require("metadata_units")
    first.charge("metadata_units", 1)
    second.charge("metadata_units", 1)
    assert accounting[2].usage(accounting[3])["metadata_units"] == 2


def test_noncontiguous_existing_processing_coordinates_do_not_collide(accounting):
    _, db, ledger, request, attempt = accounting
    ledger.reserve(request, attempt, "input_bytes", "processing-step:2", 1)
    work = budget(accounting)
    work.require("input_bytes", 1)
    assert {
        r[0] for r in db.execute("SELECT work_coordinate FROM work_accounting")
    } == {"processing-step:2", "processing-step:3"}


def test_measured_success_settles_actual_input_not_hypothetical_full_body(accounting):
    path, _, ledger, request, _ = accounting
    source = path.parent / "input"
    source.write_bytes(b"abc")
    work = budget(accounting)
    with work.measured("input_bytes", 10) as meter:
        data = source.read_bytes()
        meter.actual = len(data)
    assert data == b"abc"
    assert ledger.usage(request)["input_bytes"] == 3
    with work.measured("input_bytes", 7) as meter:
        meter.actual = len(source.read_bytes())
    assert ledger.usage(request)["input_bytes"] == 6  # Actual reread costs again.


@pytest.mark.parametrize("exception", [OSError, KeyboardInterrupt])
def test_failed_work_keeps_full_reservation_and_can_continue(accounting, exception):
    _, db, ledger, request, _ = accounting
    work = budget(accounting)
    with pytest.raises(exception):
        with work.measured("proof_steps", 8) as meter:
            meter.actual = 1  # Failure leaves uncertainty conservatively charged.
            raise exception("interrupted")
    assert ledger.usage(request)["proof_steps"] == 8
    assert db.execute("SELECT actual FROM work_accounting").fetchone()[0] is None
    with work.measured("proof_steps", 2) as meter:
        meter.actual = 2
    assert ledger.usage(request)["proof_steps"] == 10
    with pytest.raises(CoreFailure, match="finite cumulative"):
        with work.measured("proof_steps", 1):
            pytest.fail("work ran before reservation succeeded")


def test_unmeasured_success_keeps_conservative_reservation(accounting):
    work = budget(accounting)
    with work.measured("metadata_units", 8):
        pass
    assert accounting[2].usage(accounting[3])["metadata_units"] == 8
    work.require("metadata_units", 2)
    work.charge("metadata_units", 2)


def test_invalid_measurement_cannot_refund(accounting):
    work = budget(accounting)
    with pytest.raises(ValueError, match="exceeds reserved"):
        with work.measured("input_bytes", 5) as meter:
            meter.actual = 6
    assert accounting[2].usage(accounting[3])["input_bytes"] == 5


def test_request_scope_and_store_identity_fail_closed(accounting):
    _, db, ledger, request, attempt = accounting
    ledger.validate_continuation(request, attempt, scope='{"intent": "notes"}')
    with pytest.raises(CoordinationError, match="REQUEST_SCOPE"):
        ledger.validate_continuation(request, attempt, scope='{"intent":"other"}')
    for coordinate in ("repository_uuidv4", "catalog_instance_uuidv4"):
        with pytest.raises(CoordinationError, match="STORE_IDENTITY"):
            WorkLedger(db, **{coordinate: str(uuid4())})
    with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
        ledger.validate_continuation(request, str(uuid4()))


@pytest.mark.parametrize("setting", ["synchronous=OFF", "foreign_keys=OFF"])
def test_durability_settings_changed_after_open_refuse_performed_work(
    accounting, setting
):
    _, db, ledger, request, attempt = accounting
    db.execute(f"PRAGMA {setting}")
    with pytest.raises(CoordinationError, match="ACCOUNTING_DURABILITY"):
        ledger.reserve(request, attempt, "input_bytes", "never-started", 1)
    assert db.execute("SELECT count(*) FROM work_accounting").fetchone()[0] == 0


def test_non_autocommit_connection_cannot_return_uncommitted_permit(accounting):
    _, db, _, _, _ = accounting
    db.isolation_level = ""
    with pytest.raises(CoordinationError, match="ACCOUNTING_DURABILITY"):
        WorkLedger(db)


def test_operational_unlinked_with_live_connection_refuses_continuation(accounting):
    path, _, ledger, request, attempt = accounting
    path.unlink()
    with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
        ledger.reserve(request, attempt, "input_bytes", "never-started", 1)
    with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
        ledger.validate_continuation(request, attempt)


def test_missing_request_budget_cannot_be_interpreted_as_known_zero(accounting):
    _, db, ledger, request, attempt = accounting
    db.execute("DELETE FROM request_budgets WHERE work_kind='proof_steps'")
    with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
        ledger.usage(request)
    with pytest.raises(CoordinationError, match="CONTINUATION_UNAVAILABLE"):
        NotesWorkBudget(ledger, request, attempt, NotesLimits())


def test_actual_work_reservation_survives_killed_process_and_retry(accounting):
    path, _, ledger, request, _ = accounting
    source = path.parent / "input"
    source.write_bytes(b"body")
    attempt = str(uuid4())
    ledger.attempt(request, attempt)
    code = """
import sys
from pathlib import Path
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.p1_coordination import WorkLedger, NotesWorkBudget
from repo_catalog.domain.p1_coordination import NotesLimits, RequestIdentity
path=Path(sys.argv[1])
db=connect(path, 'operational')
work=NotesWorkBudget(WorkLedger(db),RequestIdentity(*sys.argv[2:4]),sys.argv[4],NotesLimits())
with work.measured('input_bytes', 8) as meter:
    data=(path.parent/'input').read_bytes()
    print(len(data),flush=True)
    sys.stdin.read()
    meter.actual=len(data)
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[3] / "src"))
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(path), *request.values(), attempt],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "4"
        process.kill()
        process.communicate(timeout=15)
        assert process.returncode < 0
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=15)
    # A fresh connection proves accounting was committed before input was read.
    with contextlib.closing(connect(path, "operational")) as reopened:
        resumed = WorkLedger(reopened)
        assert resumed.usage(request)["input_bytes"] == 8
        retry = str(uuid4())
        resumed.attempt(request, retry)
        work = NotesWorkBudget(resumed, request, retry, NotesLimits())
        with pytest.raises(CoreFailure, match="finite cumulative"):
            work.require("input_bytes", 4)
        resumed.increase_limit(request, "input_bytes", 12)
        with work.measured("input_bytes", 4) as meter:
            meter.actual = len(source.read_bytes())
        assert resumed.usage(request)["input_bytes"] == 12


def test_concurrent_connections_share_one_finite_attempt_budget(accounting):
    import concurrent.futures
    import threading

    path, _, _, request, attempt = accounting
    barrier = threading.Barrier(2)

    def worker():
        with contextlib.closing(connect(path, "operational")) as db:
            work = NotesWorkBudget(WorkLedger(db), request, attempt, NotesLimits())
            barrier.wait(timeout=10)
            for _ in range(5):
                with work.measured("metadata_units", 1) as meter:
                    meter.actual = 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)
    assert accounting[2].usage(request)["metadata_units"] == 10
    with pytest.raises(CoreFailure) as error:
        budget(accounting).require("metadata_units", 1)
    assert error.value.code == "BUDGET"
    assert error.value.scope == (request, "metadata_units")


@pytest.mark.parametrize("committed_before_failure", [False, True])
def test_failed_reservation_commit_never_enters_work_and_lost_ack_stays_charged(
    accounting, committed_before_failure
):
    _, db, _, request, attempt = accounting

    class FailingCommit:
        """Fault at the commit boundary of an otherwise real SQLite connection."""

        def __getattr__(self, name):
            return getattr(db, name)

        def commit(self):
            if committed_before_failure:
                db.commit()
            raise OSError("injected commit/lost-ack failure")

    ledger = WorkLedger(FailingCommit())
    work = NotesWorkBudget(ledger, request, attempt, NotesLimits())
    with pytest.raises(OSError, match="injected commit"):
        with work.measured("proof_steps", 8):
            pytest.fail("work executed before successful reservation acknowledgement")
    assert not db.in_transaction
    assert accounting[2].usage(request)["proof_steps"] == (
        8 if committed_before_failure else 0
    )
    # An explicitly fresh handle resumes the actual durable state. A lost ack
    # cannot reuse its former coordinate or erase a potentially performed unit.
    resumed = budget(accounting)
    with resumed.measured("proof_steps", 2) as meter:
        meter.actual = 2
    assert accounting[2].usage(request)["proof_steps"] == (
        10 if committed_before_failure else 2
    )


def test_reconstructed_or_restarted_permits_cannot_refund_uncertain_work(accounting):
    from dataclasses import replace

    _, db, ledger, request, attempt = accounting
    permit = ledger.reserve(request, attempt, "proof_steps", "actual-read", 8)
    for owner, candidate in (
        (ledger, replace(permit)),
        (WorkLedger(db), permit),
    ):
        with pytest.raises(CoordinationError, match="PERMIT_ALREADY_SETTLED_OR_LOST"):
            owner.finish(candidate, 0)
    assert ledger.usage(request)["proof_steps"] == 8
    ledger.abandon(permit)
    with pytest.raises(CoordinationError, match="PERMIT_ALREADY_SETTLED_OR_LOST"):
        ledger.finish(permit, 0)
    assert ledger.usage(request)["proof_steps"] == 8


def test_settlement_of_same_issued_permit_is_one_time(accounting):
    _, _, ledger, request, attempt = accounting
    permit = ledger.reserve(request, attempt, "input_bytes", "read", 8)
    ledger.finish(permit, 4)
    with pytest.raises(CoordinationError, match="PERMIT_ALREADY_SETTLED_OR_LOST"):
        ledger.finish(permit, 0)
    assert ledger.usage(request)["input_bytes"] == 4
