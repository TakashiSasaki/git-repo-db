"""Canonical Repository/Context validation and pinned reads; no ledger or Search code."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import ExitStack, closing, contextmanager
from dataclasses import dataclass
from time import perf_counter_ns

from repo_catalog.adapters.sqlite.catalog_runtime import (
    ReadSnapshot,
    _digest,
    _identity,
    _sqlite_corruption,
    apply_snapshot_read_limits,
    catalog_gate,
)
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.repository_coordination import RepositoryCoordinator
from repo_catalog.domain.p1_coordination import CoordinationError, SnapshotToken


def validate_dependencies(
    repository_store: sqlite3.Connection, context: sqlite3.Connection
):
    for object_format, object_oid in context.execute(
        "SELECT DISTINCT object_format,object_oid FROM repository_references"
    ):
        if not repository_store.execute(
            "SELECT 1 FROM git_objects WHERE object_format=? AND object_oid=?",
            (object_format, object_oid),
        ).fetchone():
            raise CoordinationError(
                "MISSING_REPOSITORY_REFERENCE", "context", object_oid
            )


def validate_pair(
    repository_store: sqlite3.Connection,
    context: sqlite3.Connection,
    *,
    metadata_only: bool = False,
    phase_costs_ns: dict[str, int] | None = None,
) -> SnapshotToken:
    """Validate persisted authorities, including failures of semantic CHECK UDFs.

    Invalid stored UTF-8/JSON can make integrity_check raise SQLITE_ERROR instead
    of returning a corruption row. It is still failed authoritative validation,
    not a rejected incoming unit. Transient cancellation/locking or a denied
    capability is not evidence of storage corruption.
    """
    try:
        return _validate_pair(
            repository_store,
            context,
            metadata_only=metadata_only,
            phase_costs_ns=phase_costs_ns,
        )
    except sqlite3.DatabaseError as error:
        code = getattr(error, "sqlite_errorcode", 0) & 255
        detail = str(error)
        storage_fault = code in {
            sqlite3.SQLITE_CORRUPT,
            sqlite3.SQLITE_NOTADB,
            sqlite3.SQLITE_IOERR,
        }
        semantic_fault = (
            code == sqlite3.SQLITE_ERROR
            and detail == "user-defined function raised exception"
        ) or detail.startswith("Could not decode to UTF-8 column")
        if not (storage_fault or semantic_fault):
            # Locking, cancellation, resource exhaustion and capability misuse
            # do not establish persisted corruption. IOERR during these reads
            # is an authoritative storage fault preventing required validation.
            raise
        failure = CoordinationError(
            "CORRUPTION",
            "repository+context",
            "authoritative validation failed: " + str(error),
        )
        _notify_validation_corruption(repository_store, context, failure)
        raise failure from error
    except Exception as error:
        _notify_validation_corruption(repository_store, context, error)
        raise


def _notify_validation_corruption(repository_store, context, error):
    if getattr(error, "code", None) in {
        "CORRUPTION",
        "FOREIGN_KEY",
        "MISSING_REPOSITORY_REFERENCE",
        "AUTHORITATIVE_CORRUPTION",
    }:
        # A caller may catch validation failure inside an already pinned pair.
        # Notify its owning capability now, before outer context unwinding.
        # Raw connections rely on their coordinator's initial validation catch.
        for db in (repository_store, context):
            if isinstance(db, ReadSnapshot):
                db._on_error(error)


def _validate_pair(
    repository_store: sqlite3.Connection,
    context: sqlite3.Connection,
    *,
    metadata_only: bool = False,
    phase_costs_ns: dict[str, int] | None = None,
) -> SnapshotToken:
    started = perf_counter_ns()
    identity = _identity(repository_store, "repository")
    if identity != _identity(context, "context"):
        raise CoordinationError("PAIR_IDENTITY", "repository+context")
    for db, role in ((repository_store, "repository"), (context, "context")):
        if not metadata_only and [
            tuple(row) for row in db.execute("PRAGMA integrity_check")
        ] != [("ok",)]:
            raise CoordinationError("CORRUPTION", role)
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise CoordinationError("FOREIGN_KEY", role)
    # SQLite does not re-evaluate insertion triggers for an existing snapshot.
    from repo_catalog.adapters.sqlite.p1_repository import validate_embedded_references

    validate_embedded_references(repository_store)
    validate_dependencies(repository_store, context)
    validated = perf_counter_ns()
    if phase_costs_ns is not None:
        phase_costs_ns["authority_validation"] = validated - started
    token = SnapshotToken(
        *identity,
        _digest(repository_store, metadata_only=metadata_only),
        _digest(context, metadata_only=metadata_only),
    )
    if phase_costs_ns is not None:
        phase_costs_ns["snapshot_token_generation"] = perf_counter_ns() - validated
    return token


@dataclass
class PairedSnapshot:
    repository_store: ReadSnapshot
    context: ReadSnapshot
    token: SnapshotToken


class PairSnapshotCoordinator(RepositoryCoordinator):
    """Read-only pair integration; richer writers reuse this snapshot owner."""

    def _open(self, role: str):
        if role == "repository":
            return super()._open(role)
        if role != "context":
            raise CoordinationError("AUTHORITY_UNAVAILABLE", role)
        if role == "context":
            from pathlib import Path

            from repo_catalog.domain.resource_stage import (
                _isolated_dir_fixtures,
                _NonClosingConnection,
            )

            resolved = Path(self.directory).resolve()
            if resolved in _isolated_dir_fixtures:
                fixture, _ = _isolated_dir_fixtures[resolved]
                return _NonClosingConnection(fixture)
        path = self.directory / f"{role}.sqlite3"
        if not path.is_file():
            raise CoordinationError("AUTHORITY_UNAVAILABLE", role)
        try:
            return connect(path, role)
        except Exception as error:
            self._record_corruption(error)
            raise

    @contextmanager
    def snapshots(self) -> Iterator[PairedSnapshot]:
        self.last_read_costs_ns.clear()
        self._check_running()
        try:
            with self._snapshots() as pair:
                yield pair
        except Exception as error:
            if (
                self.read_limits is not None
                and getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT
            ):
                raise CoordinationError(
                    "QUERY_BUDGET", "snapshot", "SQLite VM step limit"
                ) from error
            if getattr(error, "code", None) in (
                "CORRUPTION",
                "FOREIGN_KEY",
                "MISSING_REPOSITORY_REFERENCE",
            ) or _sqlite_corruption(error):
                self._record_corruption(error)
            raise

    @contextmanager
    def _snapshots(self) -> Iterator[PairedSnapshot]:
        with ExitStack() as stack:
            with catalog_gate(self.directory, exclusive=False):
                self._check_running()
                repository_store = stack.enter_context(
                    closing(self._open("repository"))
                )
                context = stack.enter_context(closing(self._open("context")))
                try:
                    for db in (repository_store, context):
                        db.execute("PRAGMA query_only=ON")
                        db.execute("BEGIN")
                        db.execute("SELECT * FROM store_identity").fetchall()
                        apply_snapshot_read_limits(db, self.read_limits)
                        self._guard_read(db)
                    token = validate_pair(
                        repository_store,
                        context,
                        metadata_only=self.metadata_only,
                        phase_costs_ns=self.last_read_costs_ns,
                    )
                except Exception as error:
                    self._record_corruption(error)
                    raise
            try:
                reads = (
                    ReadSnapshot(
                        repository_store,
                        self._check_running,
                        self._record_corruption,
                        directory=self.directory,
                    ),
                    ReadSnapshot(
                        context,
                        self._check_running,
                        self._record_corruption,
                        directory=self.directory,
                    ),
                )
                yield PairedSnapshot(*reads, token)
            finally:
                for read in reads:
                    read._active = False
                repository_store.set_authorizer(None)
                context.set_authorizer(None)
                repository_store.rollback()
                context.rollback()
