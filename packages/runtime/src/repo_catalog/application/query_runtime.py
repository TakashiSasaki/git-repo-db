"""Common Query input, stored reconstruction and catalog stop classification."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Literal

from repo_catalog.adapters.sqlite.catalog_runtime import (
    SnapshotReadLimits,
    persist_catalog_stop,
)
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.query_contracts import (
    CatalogReadMode,
    QueryError,
    SnapshotFenceToken,
)
from repo_catalog.domain.shared_values import CoreFailure


def _stored_view(method):
    """Fence complete fixed stored-row reconstruction, including argument unpacking."""

    @wraps(method)
    def call(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except QueryError:
            raise
        except (ValueError, TypeError, AttributeError, KeyError, IndexError) as error:
            if getattr(error, "code", None) in {
                "CAPABILITY_EXPIRED",
                "RECOVERY_STOP",
                "RECOVERY_REQUIRED",
                "RESOURCE_NOT_FOUND",
                "OBJECT_NOT_FOUND",
                "TEXT_UNAVAILABLE",
            }:
                raise
            persist_catalog_stop(
                self.directory, "invalid stored projection: " + str(error)
            )
            raise CoreFailure(
                "AUTHORITATIVE_CORRUPTION", method.__name__, str(error)
            ) from error

    return call


class _QueryWorkError(Exception):
    def __init__(self, original):
        super().__init__()
        self.original = original


class _QueryWorkLimits:
    def __init__(self, work):
        self.work = work

    @property
    def note_bytes(self):
        return self.work._invoke(lambda: self.work.inner.limits.note_bytes)


class _QueryWorkBoundary:
    """Carry callback exceptions beyond snapshot corruption classifiers."""

    def __init__(self, inner):
        self.inner = inner
        self.limits = _QueryWorkLimits(self)

    def _invoke(self, callback):
        try:
            return callback()
        except Exception as error:
            raise _QueryWorkError(error) from error

    def require(self, unit, amount=1):
        return self._invoke(lambda: self.inner.require(unit, amount))

    def charge(self, unit, amount):
        return self._invoke(lambda: self.inner.charge(unit, amount))

    def __getattr__(self, name):
        if name != "abandon":
            raise AttributeError(name)
        method = self._invoke(lambda: getattr(self.inner, name, None))
        if method is None:
            raise AttributeError(name)
        return lambda unit: self._invoke(lambda: method(unit))


class QueryReader:
    def __init__(
        self,
        directory: Path | str,
        *,
        mode: CatalogReadMode | Literal["auto"] = "auto",
        read_limits: SnapshotReadLimits = SnapshotReadLimits(),
    ):
        self.directory = Path(directory)
        if not isinstance(read_limits, SnapshotReadLimits):
            raise QueryError(
                "INVALID_LIMIT", "query", "finite SnapshotReadLimits required"
            )
        if mode not in ("auto", "core_only", "context_only", "paired"):
            raise QueryError("INVALID_MODE", "query", str(mode))
        self.read_limits = read_limits
        self.last_costs_ns: dict[str, int] = {}
        self._requested_mode = mode

    def _check_stop(self) -> None:
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoreFailure(
                "RECOVERY_STOP", "catalog", "normal catalog operation stopped"
            )

    @contextmanager
    def open_snapshot(self, *, required_store="any"):
        started = time.perf_counter_ns()
        self.last_costs_ns = {}
        try:
            with self._open_snapshot(required_store=required_store) as snapshot:
                self.last_costs_ns["snapshot_total"] = time.perf_counter_ns() - started
                yield snapshot
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
            persist_catalog_stop(
                self.directory, "stored typed data decoding: " + str(error)
            )
            raise CoreFailure(
                "AUTHORITATIVE_CORRUPTION", "query", str(error)
            ) from error
        except sqlite3.OperationalError as error:
            if str(error).startswith("Could not decode to UTF-8 column"):
                persist_catalog_stop(self.directory, str(error))
                raise CoreFailure(
                    "AUTHORITATIVE_CORRUPTION", "query", str(error)
                ) from error
            if getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
                raise QueryError(
                    "QUERY_BUDGET", "snapshot", "SQLite VM step limit"
                ) from error
            raise
        except CoordinationError as error:
            if error.code == "QUERY_BUDGET":
                raise QueryError("QUERY_BUDGET", "snapshot", str(error)) from error
            raise

    def _stored(self, constructor, *args, **kwargs):
        """Domain reconstruction concerns persisted rows, never caller input."""
        try:
            return constructor(*args, **kwargs)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            persist_catalog_stop(
                self.directory,
                "invalid stored " + constructor.__name__ + ": " + str(error),
            )
            raise CoreFailure(
                "AUTHORITATIVE_CORRUPTION", constructor.__name__, str(error)
            ) from error

    def snapshot_token(self) -> SnapshotFenceToken:
        with self.open_snapshot() as snap:
            return snap.token
