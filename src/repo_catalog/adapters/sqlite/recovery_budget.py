"""Conservative recovery reservations, independent of reconstructible stores.

Supported contract: cooperating processes on a local POSIX filesystem honouring
flock, atomic replacement and fsync. State loss is an error, not zero expenditure.
This is process-crash safety; it is not a claim of tested host power-loss safety.
"""

from __future__ import annotations

import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from repo_catalog.adapters.sqlite.p1_coordination import _file_gate
from repo_catalog.domain.recovery import RecoveryBudget, RecoveryError

_MAX_STATE_BYTES = 1024 * 1024


def canonical_request_id(request_id: str | None) -> str:
    value = "default" if request_id is None else request_id
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", value
    ):
        raise RecoveryError(
            "Recovery request ID must be 1-64 canonical ASCII letters, digits, '_' or '-'"
        )
    return value


def _sync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _same_json(left, right) -> bool:
    # JSON equality is typed: Python considers True == 1, but a persisted
    # malformed version or contract must not alias a valid one.
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate recovery accounting key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Invalid recovery accounting number: {value}")


def _read(path: Path) -> dict:
    try:
        # Nonblocking open lets a malformed FIFO/device fail validation instead
        # of hanging before the regular-file check.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("regular private state file required")
            if info.st_size > _MAX_STATE_BYTES:
                raise ValueError("oversized state")
            raw = os.read(fd, info.st_size + 1)
            if len(raw) != info.st_size:
                raise ValueError("recovery state changed while reading")
        finally:
            os.close(fd)
        result = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        if not isinstance(result, dict):
            raise ValueError("object state required")
        return result
    except (OSError, ValueError, RecursionError) as error:
        raise RecoveryError(
            f"Recovery accounting unavailable: {path.name}: {error}"
        ) from error


def _write(path: Path, data: dict) -> None:
    raw = (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(raw) > _MAX_STATE_BYTES:
        raise RecoveryError("Recovery accounting capacity exhausted")
    temporary = path.with_name(f"{path.name}.tmp.{uuid.uuid4().hex}")
    # A failed/uncertain persistence prevents the caller from starting work.
    with temporary.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _sync_dir(path.parent)


class DurableRecoveryRequest:
    def __init__(self, path: Path, state: dict):
        self.path, self.state = path, state
        self.reservation_path = path.with_suffix(".reserved.json")
        self.failed = False

    @property
    def usage(self) -> dict[str, int]:
        return dict(self.state["cumulative_usage"])

    def reserve(self, usage: dict[str, int]) -> None:
        if self.failed:
            raise RecoveryError("Recovery reservation persistence previously failed")
        old = self.usage
        if set(old) != set(usage) or any(
            type(value) is not int or value < old[key] for key, value in usage.items()
        ):
            raise RecoveryError("Recovery reservations must be monotonic")
        updated = dict(self.state, cumulative_usage=dict(usage))
        self.failed = True
        # The reservation checkpoint leads the report. If interrupted between
        # writes, reopening conservatively adopts the greater reserved usage.
        _write(self.reservation_path, dict(updated, budget_exhausted=False))
        self.state = updated
        _write(self.path, updated)
        self.failed = False

    def settle(self, usage: dict[str, int]) -> None:
        """Settle a live successful measurement; lost acknowledgements never refund.

        The report leads a decrease, so any crash before checkpoint publication
        conservatively restores the previous greater reservation on reopening.
        """
        if self.failed:
            raise RecoveryError("Recovery accounting persistence previously failed")
        old = self.usage
        if set(old) != set(usage) or any(
            type(value) is not int or not 0 <= value <= old[key]
            for key, value in usage.items()
        ):
            raise RecoveryError("Invalid live recovery settlement")
        updated = dict(self.state, cumulative_usage=dict(usage))
        self.failed = True
        _write(self.path, updated)
        _write(self.reservation_path, dict(updated, budget_exhausted=False))
        self.state = updated
        self.failed = False

    def mark_exhausted(self, exhausted: bool) -> None:
        updated = dict(self.state, budget_exhausted=bool(exhausted))
        if self.failed:
            raise RecoveryError(
                "Recovery accounting persistence failed; reopen request"
            )
        _write(self.path, updated)
        self.state = updated


@contextmanager
def recovery_request(
    directory: Path,
    request_id: str | None,
    budget: RecoveryBudget,
    limits: dict[str, int],
):
    """Lock one request from persisted admission through final receipt generation.

    Registry entries anchor identity/contract even when an individual state file
    is deleted. The permanent registry marker detects registry loss. Removing
    *all* accounting evidence is outside this local cooperative-process contract.
    """
    req_id = canonical_request_id(request_id)
    directory = Path(directory)
    path = directory / f"p1-recovery-request-{req_id}.json"
    reservation_path = path.with_suffix(".reserved.json")
    registry_path = directory / "p1-recovery-requests.json"
    marker = directory / "p1-recovery-requests.initialized"
    contract = asdict(budget)
    # Freeze caller-owned Mapping instances as plain values.
    contract["max_work_units"] = dict(budget.max_work_units)
    with _file_gate(directory / f"p1-recovery-request-{req_id}.lock", exclusive=True):
        with _file_gate(directory / "p1-recovery-requests.lock", exclusive=True):
            if marker.exists() or marker.is_symlink():
                if not _same_json(_read(marker), {"version": 1}):
                    raise RecoveryError("Invalid recovery registry marker")
                registry = _read(registry_path)
            elif registry_path.exists() or registry_path.is_symlink():
                # Initialization publishes this exact empty registry before its
                # marker. No request/work may begin until both are durable.
                # Reconcile only this pristine crash cut, never a used registry
                # or any orphan state/checkpoint/temporary request artifact.
                registry = _read(registry_path)
                if not _same_json(registry, {"version": 1, "requests": {}}) or any(
                    entry.name.startswith("p1-recovery-request-")
                    and not entry.name.endswith(".lock")
                    for entry in directory.iterdir()
                ):
                    raise RecoveryError(
                        "Recovery accounting marker missing; cannot infer zero work"
                    )
                _write(marker, {"version": 1})
            elif any(
                entry.name.startswith("p1-recovery-request-")
                and not entry.name.endswith(".lock")
                for entry in directory.iterdir()
            ):
                raise RecoveryError(
                    "Recovery accounting registry missing with request artifacts"
                )
            else:
                # A crash between these writes can only resume from a validated
                # pristine registry; it never permits unaccounted work.
                registry = {"version": 1, "requests": {}}
                _write(registry_path, registry)
                _write(marker, {"version": 1})
            if (
                set(registry) != {"version", "requests"}
                or type(registry["version"]) is not int
                or registry["version"] != 1
                or not isinstance(registry["requests"], dict)
            ):
                raise RecoveryError("Invalid recovery request registry")
            requests = registry["requests"]
            if req_id not in requests:
                if path.exists() or path.is_symlink():
                    # An initial state published before registration can only
                    # be safely adopted if exactly pristine and matching.
                    orphan = _read(path)
                    if not _same_json(
                        orphan,
                        {
                            "version": 1,
                            "request_id": req_id,
                            "contract": contract,
                            "cumulative_usage": dict.fromkeys(limits, 0),
                            "budget_exhausted": False,
                        },
                    ):
                        raise RecoveryError("Unregistered conflicting recovery state")
                else:
                    _write(
                        path,
                        {
                            "version": 1,
                            "request_id": req_id,
                            "contract": contract,
                            "cumulative_usage": dict.fromkeys(limits, 0),
                            "budget_exhausted": False,
                        },
                    )
                initial = _read(path)
                if reservation_path.exists() or reservation_path.is_symlink():
                    if not _same_json(_read(reservation_path), initial):
                        raise RecoveryError(
                            "Unregistered conflicting reservation checkpoint"
                        )
                else:
                    _write(reservation_path, initial)
                requests[req_id] = contract
                _write(registry_path, registry)
            elif not _same_json(requests[req_id], contract):
                raise RecoveryError(
                    "Existing recovery request budget contract cannot change; use a distinct explicit request"
                )
            state = _read(path)
            if (
                set(state)
                != {
                    "version",
                    "request_id",
                    "contract",
                    "cumulative_usage",
                    "budget_exhausted",
                }
                or type(state["version"]) is not int
                or state["version"] != 1
                or state["request_id"] != req_id
                or not _same_json(state["contract"], contract)
                or type(state["budget_exhausted"]) is not bool
            ):
                raise RecoveryError("Conflicting recovery accounting state")
            usage = state["cumulative_usage"]
            if (
                not isinstance(usage, dict)
                or set(usage) != set(limits)
                or any(
                    type(v) is not int or not 0 <= v <= limits[k]
                    for k, v in usage.items()
                )
            ):
                raise RecoveryError("Invalid recovery expenditure state")
            reserved = _read(reservation_path)
            expected = dict(state, budget_exhausted=False)
            reserved_usage = reserved.get("cumulative_usage")
            if (
                not isinstance(reserved_usage, dict)
                or set(reserved_usage) != set(limits)
                or any(
                    type(v) is not int or not usage[k] <= v <= limits[k]
                    for k, v in reserved_usage.items()
                )
                or not _same_json(dict(reserved, cumulative_usage=usage), expected)
            ):
                raise RecoveryError("Conflicting recovery reservation checkpoint")
            if usage != reserved_usage:
                state = dict(state, cumulative_usage=reserved_usage)
                _write(path, state)
        yield DurableRecoveryRequest(path, state)
