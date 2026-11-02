"""Core-specific snapshot coordination using shared catalog primitives."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path

from repo_catalog.adapters.sqlite.catalog_runtime import (
    ReadSnapshot as ReadSnapshot,
)
from repo_catalog.adapters.sqlite.catalog_runtime import (
    SnapshotReadLimits as SnapshotReadLimits,
)
from repo_catalog.adapters.sqlite.catalog_runtime import (
    _Cursor as _Cursor,
)
from repo_catalog.adapters.sqlite.catalog_runtime import (
    _digest as _digest,
)
from repo_catalog.adapters.sqlite.catalog_runtime import (
    _identity as _identity,
)
from repo_catalog.adapters.sqlite.catalog_runtime import (
    _json as _json,
)
from repo_catalog.adapters.sqlite.catalog_runtime import (
    _sqlite_corruption as _sqlite_corruption,
)
from repo_catalog.adapters.sqlite.catalog_runtime import (
    apply_snapshot_read_limits as apply_snapshot_read_limits,
)
from repo_catalog.adapters.sqlite.catalog_runtime import (
    catalog_completion as catalog_completion,
)
from repo_catalog.adapters.sqlite.catalog_runtime import (
    catalog_gate as catalog_gate,
)
from repo_catalog.adapters.sqlite.catalog_runtime import (
    persist_catalog_stop as persist_catalog_stop,
)
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_coordination import CoordinationError


class CoreCoordinator:
    """Core-only pinned reads with shared persistent stop and completion fencing."""

    def __init__(
        self,
        directory: Path,
        *,
        read_limits: SnapshotReadLimits | None = None,
        metadata_only: bool = False,
    ):
        self.directory = Path(directory)
        self.read_limits = read_limits
        self.metadata_only = metadata_only
        self.last_read_costs_ns: dict[str, int] = {}

    def _open(self, role: str):
        if role != "core":
            raise CoordinationError("AUTHORITY_UNAVAILABLE", role)
        path = self.directory / "core.sqlite3"
        if not path.is_file():
            raise CoordinationError("AUTHORITY_UNAVAILABLE", "core")
        try:
            return connect(path, "core")
        except Exception as error:
            self._record_corruption(error)
            raise

    def _check_running(self):
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoordinationError("RECOVERY_REQUIRED", "catalog")

    def _record_corruption(self, error: Exception, *, existing: bool = True):
        codes = {"AUTHORITATIVE_CORRUPTION"}
        if existing:
            codes |= {"CORRUPTION", "FOREIGN_KEY", "MISSING_CORE_REFERENCE"}
        if getattr(error, "code", None) in codes or _sqlite_corruption(error):
            # Persist before stack unwinding, rollback, callback or gate release.
            persist_catalog_stop(self.directory, str(error))

    def _guard_read(self, db: sqlite3.Connection):
        def authorize(action, _first, _second, _database, _trigger):
            if action == sqlite3.SQLITE_PRAGMA and (
                (_first in ("integrity_check", "foreign_key_check") and _second is None)
                or _first == "table_info"
            ):
                return sqlite3.SQLITE_OK
            if action not in (
                sqlite3.SQLITE_READ,
                sqlite3.SQLITE_SELECT,
                sqlite3.SQLITE_FUNCTION,
            ):
                return sqlite3.SQLITE_DENY
            if (
                action == sqlite3.SQLITE_READ
                and (self.directory / "p1-recovery-stop.json").exists()
            ):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(authorize)

    def stop(self, reason: str):
        """Persistent catalog stop outside damaged authority/derivatives.

        Never cleared here. P7 activation must select a fresh verified catalog.
        This only fences cooperating application operations; it is not forensic
        source capture or a promise to make filesystem bytes read-only.
        """
        persist_catalog_stop(self.directory, reason)

    @contextmanager
    def core_snapshot(self) -> Iterator[ReadSnapshot]:
        self._check_running()
        try:
            with self._core_snapshot() as core:
                yield core
        except Exception as error:
            if (
                self.read_limits is not None
                and getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
            ):
                raise CoordinationError(
                    "QUERY_BUDGET", "snapshot", "SQLite VM step limit"
                ) from error
            if _sqlite_corruption(error):
                self._record_corruption(error)
            raise

    @contextmanager
    def _core_snapshot(self) -> Iterator[ReadSnapshot]:
        with ExitStack() as stack:
            with catalog_gate(self.directory, exclusive=False):
                self._check_running()
                core = stack.enter_context(closing(self._open("core")))
                core.execute("PRAGMA query_only=ON")
                core.execute("BEGIN")
                try:
                    _identity(core, "core")  # SELECT pins a real SQLite snapshot.
                except Exception as error:
                    self._record_corruption(error)
                    raise
                apply_snapshot_read_limits(core, self.read_limits)
                self._guard_read(core)
            try:
                read = ReadSnapshot(
                    core,
                    self._check_running,
                    self._record_corruption,
                    directory=self.directory,
                )
                yield read
            finally:
                read._active = False
                core.set_authorizer(None)
                core.rollback()
