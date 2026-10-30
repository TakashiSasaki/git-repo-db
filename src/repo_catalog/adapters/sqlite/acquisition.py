"""P5 production Operational adapter over `operational.sqlite3`.

Owns reconstructible progress, finite cumulative actual-work accounting via `WorkLedger`,
continuation checkpoints, retry/backoff state (`retry_state`), cache locators
(`cache_locators`), and non-authoritative Exchange receipt tracking.
Deleting and recreating `operational.sqlite3` invalidates old in-flight continuations
(`CONTINUATION_UNAVAILABLE`) while preserving committed Core and Context facts.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from repo_catalog.adapters.sqlite.notes import NotesProgress
from repo_catalog.adapters.sqlite.p1_coordination import NotesWorkBudget, WorkLedger
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_coordination import (
    CoordinationError,
    NotesLimits,
    RequestIdentity,
)
from repo_catalog.domain.p1_core import CoreFailure, encode, uuid4_value
from repo_catalog.domain.ports.notes import request_scope
from repo_catalog.domain.time import (
    validate_observation_us,
    validate_required_observation_us,
)


class UnlimitedWorkBudget:
    """In-memory bounded WorkBudget used when caller does not supply an Operational ledger."""

    def __init__(
        self,
        *,
        note_bytes: int = 16 * 1024 * 1024,
        work_limits: dict[str, int] | None = None,
    ) -> None:
        self.limits = NotesLimits(note_bytes=note_bytes)
        self._max = dict(NotesLimits.work_limits())
        if work_limits is not None:
            self._max.update(work_limits)
        self.usage: dict[str, int] = dict.fromkeys(self._max, 0)
        self._pending: dict[str, int] = {}

    def require(self, unit: str, amount: int = 1) -> None:
        if type(amount) is not int or amount < 0:
            raise ValueError("nonnegative integer work amount required")
        limit = self._max.get(unit)
        if limit is None:
            raise ValueError(f"unknown work unit: {unit}")
        if self.usage[unit] + amount > limit:
            raise CoreFailure("BUDGET", unit, "finite cumulative request budget")
        if unit in self._pending:
            raise CoordinationError("UNSETTLED_WORK", "request", unit)
        self.usage[unit] += amount
        self._pending[unit] = amount

    def abandon(self, unit: str) -> None:
        if unit not in self._pending:
            raise CoordinationError("UNRESERVED_WORK", "request", unit)
        del self._pending[unit]

    def charge(self, unit: str, amount: int) -> None:
        if unit not in self._pending:
            raise CoordinationError("UNRESERVED_WORK", "request", unit)
        reserved = self._pending.pop(unit)
        if type(amount) is not int or amount < 0 or amount > reserved:
            raise ValueError("invalid charged work amount")
        self.usage[unit] += amount - reserved


class InMemoryNotesProgress:
    """Ephemeral NotesProgress when running without `operational.sqlite3`."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._request_identity = (str(uuid4()), str(uuid4()))
        self._scan_locks: dict[str, threading.Lock] = {}
        self._scan_locks_guard = threading.Lock()

    @contextmanager
    def scan_guard(self, scope):
        normalized = encode(json.loads(scope))
        stripe = hashlib.sha256(normalized.encode("ascii")).hexdigest()[:4]
        with self._scan_locks_guard:
            lock = self._scan_locks.setdefault(stripe, threading.Lock())
        if not lock.acquire(blocking=False):
            raise CoreFailure(
                "ACQUISITION_BUSY",
                scope,
                "another scan owns the acquisition guard; retry",
            )
        try:
            yield
        finally:
            lock.release()

    def bind(
        self,
        repository: str,
        instance: str,
        source_attribution: str,
        source_scope: str,
        work: Any,
        *,
        catalog_repository_uuidv4: str | None = None,
    ) -> None:
        if catalog_repository_uuidv4 is not None:
            uuid4_value(catalog_repository_uuidv4)
        request_scope(repository, instance, source_attribution, source_scope)

    def load(self, scope: str) -> dict[str, Any] | None:
        return self._store.get(scope)

    def request_identity(self) -> tuple[str, str]:
        return self._request_identity

    def save_once(self, scope: str, value: dict[str, Any]) -> dict[str, Any]:
        if scope not in self._store:
            self._store[scope] = json.loads(encode(value))
        return self._store[scope]

    def load_bounded(self, scope: str, max_bytes: int):
        value = self._store.get(scope)
        if value is not None and len(encode(value)) > max_bytes:
            raise CoreFailure("BUDGET", scope, "finite pinned metadata limit")
        return value

    def save_once_bounded(
        self, scope: str, value: dict[str, Any], max_bytes: int, *, encoded
    ):
        if len(encoded) > max_bytes:
            raise CoreFailure("BUDGET", scope, "finite pinned metadata limit")
        if scope not in self._store:
            self._store[scope] = json.loads(encoded)
        return self._store[scope]


def _canonical_scope_json(scope_key: object) -> str:
    if isinstance(scope_key, str):
        try:
            parsed = json.loads(scope_key)
            return encode(parsed)
        except (ValueError, TypeError):
            return encode(scope_key)
    return encode(scope_key)


class OperationalAcquisitionLedger:
    """Production Operational adapter managing work budgets, retries, continuations, and cache locators."""

    def __init__(
        self,
        target: Path | str | sqlite3.Connection | WorkLedger,
        *,
        repository_uuidv4: str | None = None,
        catalog_instance_uuidv4: str | None = None,
    ) -> None:
        self._owns_connection = False
        if isinstance(target, WorkLedger):
            self.work_ledger = target
            self.db = target.db
        elif isinstance(target, sqlite3.Connection):
            self.db = target
            self.work_ledger = WorkLedger(
                target,
                repository_uuidv4=repository_uuidv4,
                catalog_instance_uuidv4=catalog_instance_uuidv4,
            )
        else:
            path = Path(target)
            if path.is_dir():
                path = path / "operational.sqlite3"
            self.db = connect(path, "operational")
            self._owns_connection = True
            try:
                self.work_ledger = WorkLedger(
                    self.db,
                    repository_uuidv4=repository_uuidv4,
                    catalog_instance_uuidv4=catalog_instance_uuidv4,
                )
            except BaseException:
                self.db.close()
                raise
        self.repository_uuidv4, self.catalog_instance_uuidv4 = (
            self.work_ledger.store_identity()
        )
        self._locator_timestamps: dict[tuple[str, str, str], int] = {}

    def close(self) -> None:
        if self._owns_connection:
            self.db.close()

    def __enter__(self) -> OperationalAcquisitionLedger:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _default_request(self) -> RequestIdentity:
        """Deterministic Operational request identity for general retry/receipt entries."""
        request = RequestIdentity(self.repository_uuidv4, self.catalog_instance_uuidv4)
        self.work_ledger._ready()
        row = self.db.execute(
            "SELECT 1 FROM acquisition_requests WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            request.values(),
        ).fetchone()
        if row is None:
            self._witness_new_request(request)
            self.work_ledger.new_request(
                request,
                encode(
                    [
                        "p5-operational-ledger",
                        self.repository_uuidv4,
                        self.catalog_instance_uuidv4,
                    ]
                ),
                NotesLimits.work_limits(),
            )
        return request

    def _witness_new_request(self, request: RequestIdentity) -> None:
        """Crash-conservative issuance witness outside disposable SQLite.

        It stores only the explicit request coordinates, never source input or
        authority. Losing SQLite cannot make an issued request unspent. An
        incomplete witness is equally sufficient to refuse recreation.
        """
        directory = (
            self.work_ledger._path.parent
            / "p5-request-witnesses"
            / request.request_origin_uuidv4
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / request.request_uuidv4
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise CoordinationError(
                "CONTINUATION_UNAVAILABLE",
                "request",
                "issued request lost Operational accounting; initiate a genuinely new request",
            ) from error
        with os.fdopen(descriptor, "w") as handle:
            handle.write(encode(list(request.values())))
            handle.flush()
            os.fsync(handle.fileno())
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def ensure_request(
        self,
        request: RequestIdentity | None = None,
        *,
        scope: object | None = None,
        limits: dict[str, int] | None = None,
        new_request: bool = False,
    ) -> RequestIdentity:
        self.work_ledger._ready()
        if request is None:
            return self._default_request()
        row = self.db.execute(
            "SELECT 1 FROM acquisition_requests WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            request.values(),
        ).fetchone()
        if row is None:
            if not new_request:
                raise CoordinationError(
                    "CONTINUATION_UNAVAILABLE",
                    "request",
                    "explicit new request required",
                )
            scope_json = (
                _canonical_scope_json(scope)
                if scope is not None
                else encode(["p5-request", *request.values()])
            )
            self._witness_new_request(request)
            self.work_ledger.new_request(
                request,
                scope_json,
                limits if limits is not None else NotesLimits.work_limits(),
            )
        else:
            self.work_ledger.validate_continuation(
                request,
                scope=_canonical_scope_json(scope) if scope is not None else None,
            )
        return request

    def create_budget(
        self,
        *,
        scope: object,
        request: RequestIdentity | None = None,
        attempt_uuidv4: str | None = None,
        limits: NotesLimits | None = None,
        work_limits: dict[str, int] | None = None,
        new_request: bool = False,
    ) -> tuple[RequestIdentity, str, NotesWorkBudget, NotesProgress]:
        """Register or resume a request and allocate a new attempt budget + progress tracker."""
        notes_limits = limits or NotesLimits()
        effective_limits = dict(NotesLimits.work_limits())
        if work_limits is not None:
            effective_limits.update(work_limits)
        req = request or RequestIdentity(self.repository_uuidv4, str(uuid4()))
        scope_json = scope if isinstance(scope, str) else _canonical_scope_json(scope)
        self.ensure_request(
            req,
            scope=scope_json,
            limits=effective_limits,
            new_request=new_request or request is None,
        )
        attempt = attempt_uuidv4 or str(uuid4())
        uuid4_value(attempt)
        existing = self.db.execute(
            "SELECT 1 FROM acquisition_attempts WHERE request_origin_uuidv4=? AND request_uuidv4=? AND attempt_uuidv4=?",
            (*req.values(), attempt),
        ).fetchone()
        if existing is None:
            self.work_ledger.attempt(req, attempt)
        budget = NotesWorkBudget(self.work_ledger, req, attempt, notes_limits)
        progress = NotesProgress(budget)
        return req, attempt, budget, progress

    def save_continuation(
        self,
        request: RequestIdentity,
        scope_key: object,
        cursor_value: object,
    ) -> Any:
        """Persist resumable progress in `request_continuations` via `WorkLedger`."""
        scope_json = _canonical_scope_json(scope_key)
        return self.work_ledger.set_progress_once(request, scope_json, cursor_value)

    def load_continuation(
        self,
        request: RequestIdentity,
        scope_key: object,
    ) -> Any | None:
        """Load resumable progress from `request_continuations`, validating checkpoint integrity."""
        scope_json = _canonical_scope_json(scope_key)
        return self.work_ledger.get_progress(request, scope_json)

    def record_retry_state(
        self,
        scope_key: object,
        *,
        not_before_us: int | None = None,
        next_retry_at_us: int | None = None,
        reason: str = "transient_failure",
        attempt_count: int | None = None,
        state: dict[str, Any] | None = None,
        request: RequestIdentity | None = None,
    ) -> dict[str, Any]:
        """Record or update retry/backoff state in `operational.sqlite3.retry_state`."""
        self.work_ledger._ready()
        retry_us = not_before_us if not_before_us is not None else next_retry_at_us
        validate_required_observation_us(retry_us)
        req = self.ensure_request(request)
        scope_json = _canonical_scope_json(scope_key)
        prior = self.get_retry_state(scope_key, request=req)
        if attempt_count is None:
            count = (prior["attempt_count"] + 1) if prior is not None else 1
        else:
            if type(attempt_count) is not int or attempt_count < 1:
                raise ValueError("attempt_count must be a positive integer")
            count = attempt_count
        payload = {
            "attempt_count": count,
            "reason": reason,
            "state": state if state is not None else {},
        }
        reason_encoded = encode(payload)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                """INSERT INTO retry_state(request_origin_uuidv4,request_uuidv4,retry_scope_json,not_before_us,reason)
                VALUES(?,?,?,?,?)
                ON CONFLICT(request_origin_uuidv4,request_uuidv4,retry_scope_json)
                DO UPDATE SET not_before_us=excluded.not_before_us, reason=excluded.reason""",
                (*req.values(), scope_json, retry_us, reason_encoded),
            )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        return {
            "request_origin_uuidv4": req.request_origin_uuidv4,
            "request_uuidv4": req.request_uuidv4,
            "scope_key_json": scope_json,
            "not_before_us": retry_us,
            "next_retry_at_us": retry_us,
            "attempt_count": count,
            "reason": reason,
            "state": payload["state"],
            "state_json": encode(payload["state"]),
        }

    def get_retry_state(
        self,
        scope_key: object,
        *,
        request: RequestIdentity | None = None,
    ) -> dict[str, Any] | None:
        """Query retry/backoff state from `operational.sqlite3.retry_state`."""
        self.work_ledger._ready()
        scope_json = _canonical_scope_json(scope_key)
        if request is not None:
            self.work_ledger.validate_continuation(request)
            row = self.db.execute(
                "SELECT request_origin_uuidv4,request_uuidv4,retry_scope_json,not_before_us,reason "
                "FROM retry_state WHERE request_origin_uuidv4=? AND request_uuidv4=? AND retry_scope_json=?",
                (*request.values(), scope_json),
            ).fetchone()
        else:
            req = RequestIdentity(self.repository_uuidv4, self.catalog_instance_uuidv4)
            row = self.db.execute(
                "SELECT request_origin_uuidv4,request_uuidv4,retry_scope_json,not_before_us,reason "
                "FROM retry_state WHERE request_origin_uuidv4=? AND request_uuidv4=? AND retry_scope_json=?",
                (*req.values(), scope_json),
            ).fetchone()
        if row is None:
            return None
        raw_reason = row[4]
        try:
            parsed = json.loads(raw_reason)
            if isinstance(parsed, dict) and "attempt_count" in parsed:
                count = int(parsed["attempt_count"])
                reason = str(parsed.get("reason", ""))
                state = parsed.get("state", {})
            else:
                count, reason, state = 1, raw_reason, {}
        except (ValueError, TypeError):
            count, reason, state = 1, raw_reason, {}
        return {
            "request_origin_uuidv4": row[0],
            "request_uuidv4": row[1],
            "scope_key_json": row[2],
            "not_before_us": row[3],
            "next_retry_at_us": row[3],
            "attempt_count": count,
            "reason": reason,
            "state": state,
            "state_json": encode(state),
        }

    def clear_retry_state(
        self,
        scope_key: object,
        *,
        request: RequestIdentity | None = None,
    ) -> bool:
        """Remove a resolved retry state entry from `operational.sqlite3.retry_state`."""
        self.work_ledger._ready()
        scope_json = _canonical_scope_json(scope_key)
        req = request or RequestIdentity(
            self.repository_uuidv4, self.catalog_instance_uuidv4
        )
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cursor = self.db.execute(
                "DELETE FROM retry_state WHERE request_origin_uuidv4=? AND request_uuidv4=? AND retry_scope_json=?",
                (*req.values(), scope_json),
            )
            self.db.commit()
            return cursor.rowcount > 0
        except BaseException:
            self.db.rollback()
            raise

    def record_cache_locator(
        self,
        cache_key: object,
        locator: str,
        *,
        cache_purpose: str = "metadata",
        observed_at_us: int | None = None,
        repository_uuidv4: str | None = None,
    ) -> None:
        """Record a non-authoritative cache locator in `operational.sqlite3.cache_locators`."""
        self.work_ledger._ready()
        repo = repository_uuidv4 or self.repository_uuidv4
        uuid4_value(repo)
        if cache_purpose not in ("metadata", "verified_notes"):
            raise ValueError("cache_purpose must be 'metadata' or 'verified_notes'")
        if not isinstance(locator, str) or not locator:
            raise ValueError("nonempty locator string required")
        if observed_at_us is not None:
            validate_observation_us(observed_at_us)
        coord_json = _canonical_scope_json(cache_key)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                """INSERT INTO cache_locators(repository_uuidv4,cache_purpose,semantic_coordinate_json,locator)
                VALUES(?,?,?,?)
                ON CONFLICT(repository_uuidv4,cache_purpose,semantic_coordinate_json)
                DO UPDATE SET locator=excluded.locator""",
                (repo, cache_purpose, coord_json, locator),
            )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        if observed_at_us is not None:
            self._locator_timestamps[(repo, cache_purpose, coord_json)] = observed_at_us

    def get_cache_locator(
        self,
        cache_key: object,
        *,
        cache_purpose: str = "metadata",
        repository_uuidv4: str | None = None,
    ) -> dict[str, Any] | None:
        """Look up a non-authoritative cache locator from `operational.sqlite3.cache_locators`."""
        self.work_ledger._ready()
        repo = repository_uuidv4 or self.repository_uuidv4
        coord_json = _canonical_scope_json(cache_key)
        row = self.db.execute(
            "SELECT repository_uuidv4,cache_purpose,semantic_coordinate_json,locator "
            "FROM cache_locators WHERE repository_uuidv4=? AND cache_purpose=? AND semantic_coordinate_json=?",
            (repo, cache_purpose, coord_json),
        ).fetchone()
        if row is None:
            return None
        return {
            "repository_uuidv4": row[0],
            "cache_purpose": row[1],
            "cache_key_json": row[2],
            "semantic_coordinate_json": row[2],
            "locator": row[3],
            "observed_at_us": self._locator_timestamps.get((row[0], row[1], row[2])),
        }

    def record_exchange_receipt(
        self,
        package_id: str,
        package_digest_sha256: str,
        sender_catalog_instance_uuidv4: str,
        report: dict[str, Any],
        *,
        observed_at_us: int | None = None,
    ) -> None:
        """Record non-authoritative Exchange package receipt in Operational tables only."""
        uuid4_value(package_id)
        uuid4_value(sender_catalog_instance_uuidv4)
        scope = ["exchange-receipt", package_id, package_digest_sha256]
        # This is a newly measured local receipt time, not a substitute for any
        # original observation or package export timestamp.
        received_at_us = time.time_ns() // 1_000
        self.record_retry_state(
            scope,
            not_before_us=received_at_us,
            reason="exchange_imported",
            attempt_count=1,
            state={
                "package_id": package_id,
                "package_digest_sha256": package_digest_sha256,
                "sender_catalog_instance_uuidv4": sender_catalog_instance_uuidv4,
                "report": report,
            },
        )
        self.record_cache_locator(
            ["exchange-package", package_id, package_digest_sha256],
            f"sender:{sender_catalog_instance_uuidv4}",
            cache_purpose="metadata",
            observed_at_us=observed_at_us,
        )

    def get_exchange_receipt(
        self,
        package_id: str,
        package_digest_sha256: str,
    ) -> dict[str, Any] | None:
        """Retrieve a prior Exchange receipt if recorded in Operational."""
        state = self.get_retry_state(
            ["exchange-receipt", package_id, package_digest_sha256]
        )
        if state is None or state["reason"] != "exchange_imported":
            return None
        return state["state"]


RetryLedger = OperationalAcquisitionLedger
