"""Durable Operational accounting, independent of concrete authority code."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from repo_catalog.adapters.sqlite.catalog_runtime import _identity, _json
from repo_catalog.domain.p1_coordination import (
    CoordinationError,
    NotesLimits,
    RequestIdentity,
    WorkMeasurement,
    WorkPermit,
)
from repo_catalog.domain.shared_values import CoreFailure


class WorkLedger:
    """Durable finite request accounting, with mandatory loss-detecting checkpoints.

    Every mutation and its checkpoint commit together. A new connection, or any
    unknown same/other-connection write, verifies the actual accounting inventory
    before continuation. Normal steps update fixed-size counters/checksums in O(1)
    work; no Core ledger or authoritative success state is introduced.

    Acquisition units meter actual source/native/admission work. Operational
    durability bookkeeping is internal and does not recursively meter itself.
    Fresh/unknown-writer validation is a finite O(recorded work, attempts and
    progress) scan of accounting metadata only; it never reads source/body data.
    """

    _CHECKPOINT_SCOPE = '["work-ledger","checkpoint",1]'

    def __init__(
        self,
        db: sqlite3.Connection,
        *,
        repository_uuidv4: str | None = None,
        catalog_instance_uuidv4: str | None = None,
    ):
        self.db = db
        self._issued_permits: dict[int, WorkPermit] = {}
        self._validated = {}
        self._path = Path(db.execute("PRAGMA database_list").fetchone()[2])
        self._file_identity = self._stat_identity()
        self._ready()
        self.identity = _identity(db, "operational")
        repository, instance = self.identity
        if (repository_uuidv4 is not None and repository != repository_uuidv4) or (
            catalog_instance_uuidv4 is not None and instance != catalog_instance_uuidv4
        ):
            raise CoordinationError("STORE_IDENTITY", "operational")

    def store_identity(self):
        self._ready()
        if _identity(self.db, "operational") != self.identity:
            raise CoordinationError("STORE_IDENTITY", "operational")
        return self.identity

    def _stat_identity(self):
        try:
            stat = self._path.stat()
        except OSError as error:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request") from error
        return stat.st_dev, stat.st_ino

    def _ready(self):
        if self.db.in_transaction:
            raise CoordinationError("ACCOUNTING_TRANSACTION", "request")
        if (
            self.db.isolation_level is not None
            or self.db.execute("PRAGMA synchronous").fetchone()[0] < 2
            or self.db.execute("PRAGMA journal_mode").fetchone()[0] != "wal"
            or self.db.execute("PRAGMA foreign_keys").fetchone()[0] != 1
        ):
            raise CoordinationError("ACCOUNTING_DURABILITY", "request")
        if self._stat_identity() != self._file_identity:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")

    def _stamp(self):
        return self.db.execute("PRAGMA data_version").fetchone()[
            0
        ], self.db.total_changes

    @staticmethod
    def _digest_row(row):
        # An Operational consistency checksum, never a domain PK or provenance.
        return int.from_bytes(
            hashlib.sha256(_json(tuple(row)).encode()).digest(), "big"
        )

    @classmethod
    def _toggle(cls, checkpoint, field, *rows):
        value = int(checkpoint[field], 16)
        for row in rows:
            value ^= cls._digest_row(row)
        checkpoint[field] = f"{value:064x}"

    @staticmethod
    def _allocation_scope(attempt):
        return _json(
            {"attempt_uuidv4": attempt, "purpose": "processing-step-allocation"}
        )

    @staticmethod
    def _empty_checkpoint(scope, budgets):
        return {
            "version": 1,
            "scope_sha256": hashlib.sha256(scope.encode()).hexdigest(),
            "budgets": budgets,
            "attempt_count": 0,
            "attempt_xor": "0" * 64,
            "work_count": 0,
            "work_xor": "0" * 64,
            "usage": dict.fromkeys(NotesLimits.work_limits(), 0),
            "continuation_count": 0,
            "continuation_xor": "0" * 64,
        }

    def _save_checkpoint(self, request, checkpoint):
        cursor = self.db.execute(
            "UPDATE request_continuations SET cursor_json=? "
            "WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
            (_json(checkpoint), *request.values(), self._CHECKPOINT_SCOPE),
        )
        if cursor.rowcount != 1:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")

    def _check_inventory(self, request, scope, checkpoint):
        budget_rows = list(
            self.db.execute(
                "SELECT work_kind,finite_limit,spent_or_reserved FROM request_budgets "
                "WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                request.values(),
            )
        )
        budgets = {row[0]: row[1] for row in budget_rows}
        sql_usage = {row[0]: row[2] for row in budget_rows}
        actual = self._empty_checkpoint(scope, budgets)
        attempts = set()
        for row in self.db.execute(
            "SELECT attempt_uuidv4,continuation_json FROM acquisition_attempts "
            "WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            request.values(),
        ):
            attempts.add(row[0])
            actual["attempt_count"] += 1
            self._toggle(actual, "attempt_xor", row)
        for row in self.db.execute(
            "SELECT attempt_uuidv4,work_kind,work_coordinate,reserved,actual "
            "FROM work_accounting WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            request.values(),
        ):
            if row[0] not in attempts or row[1] not in actual["usage"]:
                raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
            actual["work_count"] += 1
            actual["usage"][row[1]] += row[3] if row[4] is None else row[4]
            self._toggle(actual, "work_xor", row)
        allocation_scopes = {self._allocation_scope(attempt) for attempt in attempts}
        found_allocations = set()
        for row in self.db.execute(
            "SELECT continuation_scope_json,cursor_json FROM request_continuations "
            "WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json<>?",
            (*request.values(), self._CHECKPOINT_SCOPE),
        ):
            actual["continuation_count"] += 1
            self._toggle(actual, "continuation_xor", row)
            if row[0] in allocation_scopes:
                found_allocations.add(row[0])
        if (
            _json(actual) != _json(checkpoint)
            or _json(sql_usage) != _json(actual["usage"])
            or set(budgets) != set(NotesLimits.work_limits())
            or found_allocations != allocation_scopes
        ):
            raise CoordinationError(
                "CONTINUATION_UNAVAILABLE",
                "request",
                "accounting inventory/checkpoint mismatch",
            )

    def _check(self, request, attempt=None, scope=None):
        row = self.db.execute(
            "SELECT state,request_scope_json FROM acquisition_requests WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            request.values(),
        ).fetchone()
        saved = self.db.execute(
            "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
            (*request.values(), self._CHECKPOINT_SCOPE),
        ).fetchone()
        if row is None or row[0] != "open" or saved is None:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
        try:
            checkpoint = json.loads(saved[0])
            if self._validated.get(request) != self._stamp():
                self._check_store_identity()
                self._check_inventory(request, row[1], checkpoint)
        except (KeyError, ValueError, TypeError, RecursionError) as error:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request") from error
        if scope is not None and _json(json.loads(row[1])) != _json(json.loads(scope)):
            raise CoordinationError("REQUEST_SCOPE", "request")
        if (
            attempt is not None
            and not self.db.execute(
                "SELECT 1 FROM acquisition_attempts WHERE request_origin_uuidv4=? AND request_uuidv4=? AND attempt_uuidv4=?",
                (*request.values(), attempt),
            ).fetchone()
        ):
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
        return checkpoint

    def _check_store_identity(self):
        if _identity(self.db, "operational") != self.identity:
            raise CoordinationError("STORE_IDENTITY", "operational")

    @contextmanager
    def _checked(self, request, attempt=None, *, scope=None, write=False):
        self._ready()
        # Even read validation takes the short write fence: its cached stamp
        # must describe the same snapshot and cannot race another writer commit.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            checkpoint = self._check(request, attempt, scope)
            yield checkpoint
            if write:
                self._save_checkpoint(request, checkpoint)
            stamp = self._stamp()  # Capture before releasing the write fence.
            if write:
                self.db.commit()
            else:
                self.db.rollback()
            self._validated[request] = stamp
        except BaseException:
            self._validated.pop(request, None)
            self.db.rollback()
            raise

    def validate_continuation(self, request, attempt_uuidv4=None, *, scope=None):
        with self._checked(request, attempt_uuidv4, scope=scope):
            pass

    def usage(self, request):
        with self._checked(request) as checkpoint:
            return dict(checkpoint["usage"])

    def new_request(self, request, scope, limits):
        if set(limits) != set(NotesLimits.work_limits()):
            raise ValueError("all four finite work limits required")
        for limit in limits.values():
            if type(limit) is not int or not 0 <= limit <= 2**63 - 1:
                raise ValueError("finite signed int64 nonnegative limit required")
        self._ready()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "INSERT INTO acquisition_requests VALUES(?,?,?,'open')",
                (*request.values(), scope),
            )
            self.db.executemany(
                "INSERT INTO request_budgets(request_origin_uuidv4,request_uuidv4,work_kind,finite_limit) VALUES(?,?,?,?)",
                [(*request.values(), kind, limit) for kind, limit in limits.items()],
            )
            self.db.execute(
                "INSERT INTO request_continuations VALUES(?,?,?,?)",
                (
                    *request.values(),
                    self._CHECKPOINT_SCOPE,
                    _json(self._empty_checkpoint(scope, limits)),
                ),
            )
            stamp = self._stamp()
            self.db.commit()
            self._validated[request] = stamp
        except BaseException:
            self._validated.pop(request, None)
            self.db.rollback()
            raise

    def _put_continuation(self, request, checkpoint, scope, value):
        old = self.db.execute(
            "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
            (*request.values(), scope),
        ).fetchone()
        if old is None:
            checkpoint["continuation_count"] += 1
        else:
            self._toggle(checkpoint, "continuation_xor", (scope, old[0]))
        self.db.execute(
            "INSERT INTO request_continuations VALUES(?,?,?,?) ON CONFLICT(request_origin_uuidv4,request_uuidv4,continuation_scope_json) DO UPDATE SET cursor_json=excluded.cursor_json",
            (*request.values(), scope, value),
        )
        self._toggle(checkpoint, "continuation_xor", (scope, value))

    def attempt(self, request, attempt_uuidv4, continuation="{}"):
        with self._checked(request, write=True) as checkpoint:
            self.db.execute(
                "INSERT INTO acquisition_attempts VALUES(?,?,?,?)",
                (*request.values(), attempt_uuidv4, continuation),
            )
            checkpoint["attempt_count"] += 1
            self._toggle(checkpoint, "attempt_xor", (attempt_uuidv4, continuation))
            self._put_continuation(
                request,
                checkpoint,
                self._allocation_scope(attempt_uuidv4),
                _json({"last_processing_step": 0}),
            )

    def increase_limit(self, request, work_kind, finite_limit):
        if type(finite_limit) is not int or not 0 <= finite_limit <= 2**63 - 1:
            raise ValueError("finite nonnegative signed int64 limit required")
        with self._checked(request, write=True) as checkpoint:
            cursor = self.db.execute(
                "UPDATE request_budgets SET finite_limit=? WHERE request_origin_uuidv4=? AND request_uuidv4=? AND work_kind=? AND finite_limit<?",
                (finite_limit, *request.values(), work_kind, finite_limit),
            )
            if cursor.rowcount != 1:
                raise CoordinationError("FINITE_INCREASE_REQUIRED", "request")
            checkpoint["budgets"][work_kind] = finite_limit

    def _insert_reservation(
        self, request, attempt, kind, coordinate, amount, checkpoint
    ):
        self.db.execute(
            "INSERT INTO work_accounting VALUES(?,?,?,?,?,?,NULL)",
            (*request.values(), attempt, kind, coordinate, amount),
        )
        checkpoint["work_count"] += 1
        checkpoint["usage"][kind] += amount
        self._toggle(checkpoint, "work_xor", (attempt, kind, coordinate, amount, None))

    def reserve(self, request, attempt_uuidv4, work_kind, work_coordinate, upper_bound):
        if type(upper_bound) is not int or not 0 <= upper_bound <= 2**63 - 1:
            raise ValueError("finite nonnegative upper bound required")
        with self._checked(request, attempt_uuidv4, write=True) as checkpoint:
            self._insert_reservation(
                request,
                attempt_uuidv4,
                work_kind,
                work_coordinate,
                upper_bound,
                checkpoint,
            )
            if work_coordinate.startswith("processing-step:"):
                suffix = work_coordinate.removeprefix("processing-step:")
                if suffix.isascii() and suffix.isdigit():
                    step = int(suffix)
                    if not 0 < step <= 2**63 - 1:
                        raise CoordinationError("ACCOUNTING_STATE", "request")
                    allocation_scope = self._allocation_scope(attempt_uuidv4)
                    row = self.db.execute(
                        "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? "
                        "AND request_uuidv4=? AND continuation_scope_json=?",
                        (*request.values(), allocation_scope),
                    ).fetchone()
                    if row is None:
                        raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
                    last = json.loads(row[0])["last_processing_step"]
                    self._put_continuation(
                        request,
                        checkpoint,
                        allocation_scope,
                        _json({"last_processing_step": max(last, step)}),
                    )
        return self._issue(
            WorkPermit(request, attempt_uuidv4, work_kind, work_coordinate, upper_bound)
        )

    def _issue(self, permit):
        self._issued_permits[id(permit)] = permit
        return permit

    def abandon(self, permit):
        self._check_permit(permit)
        del self._issued_permits[id(permit)]

    def _check_permit(self, permit):
        if self._issued_permits.get(id(permit)) is not permit:
            raise CoordinationError("PERMIT_ALREADY_SETTLED_OR_LOST", "request")

    def reserve_processing_step(self, request, attempt, kind, amount):
        if type(amount) is not int or not 0 <= amount <= 2**63 - 1:
            raise ValueError("finite nonnegative upper bound required")
        with self._checked(request, attempt, write=True) as checkpoint:
            allocation_scope = self._allocation_scope(attempt)
            row = self.db.execute(
                "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
                (*request.values(), allocation_scope),
            ).fetchone()
            if row is None:
                raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
            last = json.loads(row[0])["last_processing_step"]
            if type(last) is not int or not 0 <= last < 2**63 - 1:
                raise CoordinationError("ACCOUNTING_STATE", "request")
            coordinate = f"processing-step:{last + 1}"
            self._insert_reservation(
                request, attempt, kind, coordinate, amount, checkpoint
            )
            self._put_continuation(
                request,
                checkpoint,
                allocation_scope,
                _json({"last_processing_step": last + 1}),
            )
        return self._issue(WorkPermit(request, attempt, kind, coordinate, amount))

    def finish(self, permit, actual):
        self._check_permit(permit)
        if type(actual) is not int or not 0 <= actual <= permit.reserved:
            raise ValueError("actual work exceeds reserved bound")
        with self._checked(
            permit.request, permit.attempt_uuidv4, write=True
        ) as checkpoint:
            cursor = self.db.execute(
                "UPDATE work_accounting SET actual=? WHERE request_origin_uuidv4=? AND request_uuidv4=? AND attempt_uuidv4=? AND work_kind=? AND work_coordinate=? AND actual IS NULL AND reserved=?",
                (
                    actual,
                    *permit.request.values(),
                    permit.attempt_uuidv4,
                    permit.work_kind,
                    permit.work_coordinate,
                    permit.reserved,
                ),
            )
            if cursor.rowcount != 1:
                raise CoordinationError("PERMIT_ALREADY_SETTLED_OR_LOST", "request")
            checkpoint["usage"][permit.work_kind] += actual - permit.reserved
            row = (
                permit.attempt_uuidv4,
                permit.work_kind,
                permit.work_coordinate,
                permit.reserved,
            )
            self._toggle(checkpoint, "work_xor", (*row, None), (*row, actual))
        del self._issued_permits[id(permit)]

    def _progress_scope(self, scope):
        parsed = json.loads(scope)
        normalized = _json(parsed)
        if normalized == self._CHECKPOINT_SCOPE or (
            isinstance(parsed, dict)
            and parsed.get("purpose") == "processing-step-allocation"
        ):
            raise CoordinationError("PROGRESS_SCOPE", "request")
        return normalized

    def get_progress(self, request, scope):
        """Return decoded original progress, or None only for a genuine new slot."""
        scope = self._progress_scope(scope)
        with self._checked(request):
            row = self.db.execute(
                "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
                (*request.values(), scope),
            ).fetchone()
            return None if row is None else json.loads(row[0])

    def progress_length(self, request, scope):
        scope = self._progress_scope(scope)
        with self._checked(request):
            row = self.db.execute(
                "SELECT octet_length(cursor_json) FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
                (*request.values(), scope),
            ).fetchone()
            return None if row is None else row[0]

    def get_progress_bounded(self, request, scope, limit):
        scope = self._progress_scope(scope)
        with self._checked(request):
            row = self.db.execute(
                "SELECT cursor_json,octet_length(cursor_json) FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=? AND octet_length(cursor_json)<=?",
                (*request.values(), scope, limit),
            ).fetchone()
            if row is None:
                raise CoordinationError(
                    "CONTINUATION_UNAVAILABLE",
                    "request",
                    "progress changed or exceeds reserved bytes",
                )
            return json.loads(row[0]), row[1]

    def set_progress_once_bounded(self, request, scope, encoded, limit):
        """Never materialize a concurrent winner larger than the reservation."""
        scope = self._progress_scope(scope)
        with self._checked(request, write=True) as checkpoint:
            row = self.db.execute(
                "SELECT octet_length(cursor_json) FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
                (*request.values(), scope),
            ).fetchone()
            if row is not None:
                if row[0] > limit:
                    raise CoordinationError(
                        "CONTINUATION_UNAVAILABLE",
                        "request",
                        "concurrent progress exceeds reserved bytes",
                    )
                value = self.db.execute(
                    "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=? AND octet_length(cursor_json)<=?",
                    (*request.values(), scope, limit),
                ).fetchone()
                return json.loads(value[0]), row[0]
            if len(encoded) > limit:
                raise CoordinationError(
                    "CONTINUATION_UNAVAILABLE",
                    "request",
                    "progress exceeds reserved bytes",
                )
            self._put_continuation(request, checkpoint, scope, encoded)
            return json.loads(encoded), len(encoded)

    def bind_exchange_package(self, request, sender, package_id, digest):
        """Bind a PackageKey globally in this Operational generation.

        The existing continuation inventory carries only the digest, never the
        package payload. BEGIN IMMEDIATE serializes lookup and first insertion
        across requests and connections. Request issuance remains independent.
        """
        from repo_catalog.domain.exchange import ExchangeError
        from repo_catalog.domain.p1_core import uuid4_value

        uuid4_value(sender)
        uuid4_value(package_id)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("SHA-256 required")
        scope = self._progress_scope(
            _json(["adr0030-package-binding", sender, package_id])
        )
        with self._checked(request, write=True) as checkpoint:
            rows = self.db.execute(
                "SELECT cursor_json FROM request_continuations WHERE continuation_scope_json=? AND json_extract(continuation_scope_json,'$[0]')='adr0030-package-binding'",
                (scope,),
            ).fetchall()
            if rows:
                if any(json.loads(row[0]) != {"digest_sha256": digest} for row in rows):
                    raise ExchangeError("PACKAGE_KEY_REBOUND", [sender, package_id])
                return False
            self._put_continuation(
                request, checkpoint, scope, _json({"digest_sha256": digest})
            )
            return True

    def set_progress_once(self, request, scope, value):
        """Atomically preserve the first decoded JSON value for a semantic slot."""
        scope = self._progress_scope(scope)
        encoded = _json(value)
        with self._checked(request, write=True) as checkpoint:
            row = self.db.execute(
                "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
                (*request.values(), scope),
            ).fetchone()
            if row is not None:
                return json.loads(row[0])
            self._put_continuation(request, checkpoint, scope, encoded)
            return value


class NotesWorkBudget:
    """P4-facing require/charge bridge, separate from Core transaction ownership.

    Coordinates are actual ordered processing steps in this genuine attempt,
    rather than new per-fact identities. New attempts retain the same request.
    """

    def __init__(
        self,
        ledger: WorkLedger,
        request: RequestIdentity,
        attempt_uuidv4: str,
        limits: NotesLimits,
    ):
        self.ledger, self.request = ledger, request
        self.attempt_uuidv4, self.limits = attempt_uuidv4, limits
        self.pending: dict[str, WorkPermit] = {}
        ledger._ready()
        ledger.validate_continuation(request, attempt_uuidv4)

    def require(self, unit: str, amount: int = 1):
        if unit in self.pending:
            raise CoordinationError("UNSETTLED_WORK", "request", unit)
        try:
            permit = self.ledger.reserve_processing_step(
                self.request, self.attempt_uuidv4, unit, amount
            )
        except sqlite3.IntegrityError as error:
            if str(error) != "finite cumulative request budget":
                raise
            raise CoreFailure("BUDGET", (self.request, unit), str(error)) from error
        self.pending[unit] = permit

    def abandon(self, unit: str):
        """Forget a local pending handle, retaining its full durable charge.

        Use only when precise performed work cannot be measured (e.g. a failed
        input operation). This never settles or refunds the reservation.
        """
        if unit not in self.pending:
            raise CoordinationError("UNRESERVED_WORK", "request", unit)
        self.ledger.abandon(self.pending[unit])
        del self.pending[unit]

    def charge(self, unit: str, amount: int):
        if unit not in self.pending:
            raise CoordinationError("UNRESERVED_WORK", "request", unit)
        self.ledger.finish(self.pending[unit], amount)
        del self.pending[unit]

    @contextmanager
    def measured(self, unit: str, upper_bound: int) -> Iterator[WorkMeasurement]:
        """Reserve before work; settle measured success, retain failed uncertainty.

        Set meter.actual only after counting performed work. Any exceptional
        exit, including process interruption, retains the full reservation.
        Failure to obtain a permit prevents entry into the work block.
        """
        self.require(unit, upper_bound)
        meter = WorkMeasurement()
        try:
            yield meter
        except BaseException:
            self.abandon(unit)
            raise
        else:
            if meter.actual is None:
                self.abandon(unit)
            else:
                self.charge(unit, meter.actual)
