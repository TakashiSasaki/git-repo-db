"""Independent-process reservation/retry tests on disposable P1 catalogs."""

from __future__ import annotations

import base64
import hashlib
import json
import multiprocessing
import os
import signal
import sqlite3
import uuid
from dataclasses import replace

import pytest

from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.domain.p1_core import native_oid
from repo_catalog.domain.recovery import RecoveryBudget, RecoveryError

REPO = "11111111-1111-4111-8111-111111111111"
INSTANCE = "22222222-2222-4222-8222-222222222222"


def _worker(directory, salvage, budget, stage, output=None, start=None):
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.adapters.sqlite.recovery import RecoveryWorkBudget
    from repo_catalog.adapters.sqlite.recovery_budget import DurableRecoveryRequest

    def die():
        os.kill(os.getpid(), signal.SIGKILL)

    if stage == "checkpoint":
        import repo_catalog.adapters.sqlite.recovery_budget as module

        original = module._write

        def write(path, data):
            original(path, data)
            if path.name.endswith(".reserved.json") and sum(
                data["cumulative_usage"].values()
            ):
                die()

        module._write = write
    elif stage == "reserved":
        original = DurableRecoveryRequest.reserve

        def reserve(self, usage):
            original(self, usage)
            die()

        DurableRecoveryRequest.reserve = reserve
    elif stage == "worked":
        original = RecoveryWorkBudget.charge

        def charge(self, unit, amount):
            original(self, unit, amount)
            die()

        RecoveryWorkBudget.charge = charge
    elif stage == "admitted":
        original = GitCore.admit_metadata

        def admit(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            die()
            return result

        GitCore.admit_metadata = admit
    if start:
        start.wait(10)
    receipt = SQLiteRecoveryAdapter().merge_salvage(
        directory, salvage, budget, "crash-request"
    )
    if output is not None:
        output.put((receipt.admitted_units, receipt.unprocessed_units))


@pytest.fixture
def catalog(tmp_path):
    destination = tmp_path / "fresh"
    destination.mkdir()
    initialize(destination / "core.sqlite3", "core", REPO, INSTANCE)
    return destination


def _candidate(tmp_path, message="one"):
    body = (
        "tree "
        + "1" * 40
        + "\nauthor A <a@b> 1 +0000\ncommitter A <a@b> 1 +0000\n\n"
        + message
        + "\n"
    ).encode()
    record = {
        "candidate_type": "retained_metadata",
        "extraction_status": "clean",
        "payload": {
            "object_format": "sha1",
            "full_oid": native_oid("sha1", "commit", body),
            "native_type": "commit",
            "size": len(body),
            "physical_copy_uuidv4": str(uuid.uuid4()),
            "digest_sha256": hashlib.sha256(body).hexdigest(),
            "body_base64": base64.b64encode(body).decode(),
        },
    }
    path = tmp_path / f"{message}.jsonl"
    path.write_text(json.dumps(record) + "\n")
    return path, body


def _state(catalog):
    return json.loads((catalog / "p1-recovery-request-crash-request.json").read_text())


def _count(catalog):
    with sqlite3.connect(catalog / "core.sqlite3") as connection:
        return connection.execute("SELECT count(*) FROM retained_metadata").fetchone()[
            0
        ]


@pytest.mark.parametrize("stage", ["checkpoint", "reserved", "worked", "admitted"])
def test_sigkill_keeps_reserved_expenditure_and_restart(catalog, tmp_path, stage):
    path, body = _candidate(tmp_path)
    budget = RecoveryBudget(max_work_units={"input_bytes": len(body)})
    process = multiprocessing.get_context("spawn").Process(
        target=_worker, args=(catalog, path, budget, stage)
    )
    process.start()
    process.join(15)
    assert not process.is_alive()
    assert process.exitcode == -signal.SIGKILL
    before = _state(catalog)["cumulative_usage"]
    if stage != "checkpoint":
        assert sum(before.values()) > 0
    else:
        checkpoint = json.loads(
            (catalog / "p1-recovery-request-crash-request.reserved.json").read_text()
        )
        assert sum(checkpoint["cumulative_usage"].values()) > 0
    assert _count(catalog) == (1 if stage == "admitted" else 0)
    for _ in range(3):
        retry = multiprocessing.get_context("spawn").Process(
            target=_worker, args=(catalog, path, budget, None)
        )
        retry.start()
        retry.join(15)
        assert retry.exitcode == 0
    after = _state(catalog)["cumulative_usage"]
    assert all(after[key] >= value for key, value in before.items())
    assert after["input_bytes"] <= len(body)
    assert _count(catalog) <= 1


def test_two_processes_cannot_spend_same_allowance(catalog, tmp_path):
    path1, body = _candidate(tmp_path, "one")
    path2, _ = _candidate(tmp_path, "two")
    budget = RecoveryBudget(max_work_units={"input_bytes": len(body)})
    context = multiprocessing.get_context("spawn")
    start, output = context.Event(), context.Queue()
    processes = [
        context.Process(
            target=_worker, args=(catalog, path, budget, None, output, start)
        )
        for path in (path1, path2)
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0
    results = [output.get(timeout=5), output.get(timeout=5)]
    assert sum(result[0] for result in results) == 1
    assert _count(catalog) == 1
    assert _state(catalog)["cumulative_usage"]["input_bytes"] == len(body)


@pytest.mark.parametrize(
    "damage",
    [
        "deleted",
        "corrupt",
        "truncated",
        "conflicting",
        "registry_deleted",
        "reservation_deleted",
        "reservation_corrupt",
    ],
)
def test_accounting_loss_or_damage_fails_closed(catalog, tmp_path, damage):
    path, _ = _candidate(tmp_path)
    SQLiteRecoveryAdapter().merge_salvage(catalog, path, request_id="crash-request")
    state = catalog / "p1-recovery-request-crash-request.json"
    if damage == "deleted":
        state.unlink()
    elif damage == "registry_deleted":
        (catalog / "p1-recovery-requests.json").unlink()
    elif damage.startswith("reservation_"):
        checkpoint = catalog / "p1-recovery-request-crash-request.reserved.json"
        if damage == "reservation_deleted":
            checkpoint.unlink()
        else:
            checkpoint.write_text("{}")
    elif damage == "conflicting":
        data = _state(catalog)
        data["request_id"] = "another"
        state.write_text(json.dumps(data))
    else:
        state.write_text("garbage" if damage == "corrupt" else '{"version":')
    with pytest.raises(RecoveryError):
        SQLiteRecoveryAdapter().merge_salvage(catalog, path, request_id="crash-request")
    assert _count(catalog) == 1


@pytest.mark.parametrize(
    "request_id", ["../escape", "a/b", "a\\b", "", ".", "x.y", " a", "é", "a" * 65]
)
def test_invalid_request_identity_never_creates_state(catalog, tmp_path, request_id):
    path, _ = _candidate(tmp_path)
    with pytest.raises(RecoveryError):
        SQLiteRecoveryAdapter().merge_salvage(catalog, path, request_id=request_id)
    assert not list(catalog.glob("p1-recovery-request*"))


def test_fixed_contract_and_operational_loss(catalog, tmp_path):
    path, _ = _candidate(tmp_path)
    budget = RecoveryBudget()
    adapter = SQLiteRecoveryAdapter()
    adapter.merge_salvage(catalog, path, budget, "crash-request")
    before = _state(catalog)
    with pytest.raises(RecoveryError, match="contract cannot change"):
        adapter.merge_salvage(
            catalog,
            path,
            replace(budget, max_input_bytes=budget.max_input_bytes + 1),
            "crash-request",
        )
    for role in ("operational", "search"):
        initialize(catalog / f"{role}.sqlite3", role, REPO, INSTANCE)
        (catalog / f"{role}.sqlite3").unlink()
    assert (
        adapter.merge_salvage(catalog, path, budget, "crash-request").replayed_units
        == 1
    )
    assert all(
        _state(catalog)["cumulative_usage"][key] >= value
        for key, value in before["cumulative_usage"].items()
    )
    assert (
        adapter.merge_salvage(
            catalog, path, budget, "explicit-new-request"
        ).replayed_units
        == 1
    )


def test_lowered_usage_report_cannot_reset_reservation(catalog, tmp_path):
    path, _ = _candidate(tmp_path)
    adapter = SQLiteRecoveryAdapter()
    adapter.merge_salvage(catalog, path, request_id="crash-request")
    state = _state(catalog)
    original_usage = dict(state["cumulative_usage"])
    state["cumulative_usage"] = dict.fromkeys(original_usage, 0)
    (catalog / "p1-recovery-request-crash-request.json").write_text(json.dumps(state))
    adapter.merge_salvage(catalog, path, request_id="crash-request")
    assert all(
        _state(catalog)["cumulative_usage"][key] >= value
        for key, value in original_usage.items()
    )
