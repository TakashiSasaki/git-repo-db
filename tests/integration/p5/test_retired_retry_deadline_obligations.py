"""Scheduling deadlines stay distinct from positive observation coordinates."""

import json

import httpx
import pytest

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.application.provider_fetch import acquire_github
from repo_catalog.domain.p1_coordination import RequestIdentity
from repo_catalog.domain.retry_deadline import validate_retry_deadline_us
from tests.integration.p4.test_accounting import accounting
from tests.integration.p5.test_separated_github_fetch import response, setup

__all__ = ["accounting"]


def test_retry_deadline_validator_preserves_absence_zero_and_int64(accounting):
    _, _, work, request, _ = accounting
    assert validate_retry_deadline_us(None) is None
    for value in (0, 1, 2**63 - 1):
        assert validate_retry_deadline_us(value) == value
    with OperationalAcquisitionLedger(work) as ledger:
        scope = ["actual-scheduling-scope"]
        assert ledger.get_retry_state(scope, request=request) is None
        zero = ledger.record_retry_state(scope, not_before_us=0, request=request)
        assert zero["not_before_us"] == zero["next_retry_at_us"] == 0
        assert zero["attempt_count"] == 1
        maximum = ledger.record_retry_state(
            scope, next_retry_at_us=2**63 - 1, request=request
        )
        assert maximum["not_before_us"] == 2**63 - 1
        assert maximum["attempt_count"] == 2
        assert (
            ledger.get_retry_state(scope, request=request)["not_before_us"] == 2**63 - 1
        )
        assert (
            ledger.record_retry_state(scope, not_before_us=None, request=request)
            is None
        )
        assert ledger.get_retry_state(scope, request=request) is None
        assert ledger.db.execute("SELECT count(*) FROM retry_state").fetchone()[0] == 0


@pytest.mark.parametrize(
    "value",
    [False, True, 0.0, "0", -1, 2**63],
    ids=["bool-false", "bool-true", "float", "string", "negative", "overflow"],
)
def test_invalid_retry_deadline_never_changes_existing_schedule(accounting, value):
    _, db, work, request, _ = accounting
    with OperationalAcquisitionLedger(work) as ledger:
        scope = ["actual-scheduling-scope"]
        ledger.record_retry_state(scope, not_before_us=0, request=request)
        original = ledger.get_retry_state(scope, request=request)
        usage = work.usage(request)
        before = db.total_changes
        with pytest.raises((ValueError, TypeError)):
            validate_retry_deadline_us(value)
        with pytest.raises((ValueError, TypeError)):
            ledger.record_retry_state(scope, not_before_us=value, request=request)
        assert db.total_changes == before
        assert ledger.get_retry_state(scope, request=request) == original
        assert work.usage(request) == usage


def test_real_http_retry_deadline_zero_is_eligible_and_future_refuses_all_work(
    tmp_path,
):
    document, authorization, admission = setup(tmp_path)
    document.update(operation="discover", include_repositories=["repo"])
    request = RequestIdentity(*document["request_identity"])
    stamp = 10_000_000
    calls = []

    def handle(incoming):
        calls.append(incoming.url.path)
        if incoming.url.path == "/user":
            return response(incoming, {"id": 1, "login": "owner"})
        assert incoming.url.path == "/repos/owner/repo"
        return response(
            incoming, {"id": 10, "full_name": "owner/repo", "private": False}
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
            clock_us=lambda: stamp,
        )
        assert first.status == "complete" and first.http_attempts == len(calls) == 2
        document["new_request"] = False
        with OperationalAcquisitionLedger(tmp_path) as ledger:
            frozen = json.loads(
                ledger.db.execute(
                    "SELECT request_scope_json FROM acquisition_requests WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                    request.values(),
                ).fetchone()[0]
            )
            assert frozen[0] == "github-http"
            retry_scope = ["github-http-retry", frozen[1]]
            future = ledger.record_retry_state(
                retry_scope,
                not_before_us=stamp + 1,
                request=request,
            )
            before = ledger.work_ledger.usage(request)
        blocked = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
            clock_us=lambda: stamp,
        )
        assert blocked.status == "partial" and blocked.failure_code == "NOT_BEFORE"
        assert blocked.not_before_us == stamp + 1
        assert blocked.http_attempts == blocked.network_bytes == 0
        assert len(calls) == 2 and blocked.batches == ()
        with OperationalAcquisitionLedger(tmp_path) as ledger:
            assert ledger.work_ledger.usage(request) == before
            expired = ledger.record_retry_state(
                retry_scope,
                not_before_us=0,
                request=request,
            )
            assert expired["attempt_count"] == future["attempt_count"] + 1
        resumed = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
            clock_us=lambda: stamp,
        )
    assert resumed.status == "complete" and resumed.http_attempts == 2
    assert resumed.request_identity == first.request_identity == request
    assert len(calls) == 4
    with OperationalAcquisitionLedger(tmp_path) as ledger:
        after = ledger.work_ledger.usage(request)
        assert after["input_bytes"] > before["input_bytes"]
        assert all(after[kind] >= value for kind, value in before.items())
        assert (
            ledger.db.execute("SELECT count(*) FROM acquisition_requests").fetchone()[0]
            == 1
        )
    assert not (tmp_path / "p1-recovery-stop.json").exists()
