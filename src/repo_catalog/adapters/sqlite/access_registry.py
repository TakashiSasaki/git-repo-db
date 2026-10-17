"""Typed opt-in Scope registry. No public SQL, grants, dispatch, or auto-discovery.

Each operation owns one short SQLite transaction; no callback or network operation
runs inside it. Factory connections and private Python attributes are trusted code,
not a security boundary against arbitrary Python/filesystem owners. Current route
controls NEVER constitute local approval. A2 must supply real approval/execution.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from repo_catalog.adapters.sqlite import access_schema as schema
from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    AccessScope,
    RegistrationPage,
    RegistrationResult,
    ScopeLocatorRegistration,
    display_label,
    page_size,
    scope_uuid,
)


class AccessRegistry:
    def __init__(self, path: str | Path, *, writable: bool = False):
        self._db, self.path = schema.open_checked(path, writable=writable)
        self._token = schema.file_token(self.path)
        self._writable = writable
        self._closed = False
        self._failed = False
        self._active = False
        self._writing = False
        self._db.set_authorizer(self._authorize)

    def __enter__(self) -> AccessRegistry:
        self._ready()
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._db.close()
            self._closed = True

    def _authorize(self, action, _a, _b, _database, _trigger):
        if not self._active:
            return sqlite3.SQLITE_DENY
        if action in (
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE,
            sqlite3.SQLITE_TRANSACTION,
        ):
            return sqlite3.SQLITE_OK
        if self._writing and action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def _ready(self) -> None:
        if self._closed:
            raise AccessRegistryError("CLOSED", "Access registry handle is closed")
        if self._failed:
            raise AccessRegistryError("STOPPED", "Access handle is disabled after failure")
        schema.check_stop(self.path)
        if schema.file_token(self.path) != self._token:
            self._failed = True
            raise AccessRegistryError("PATH_CHANGED", "Access file was replaced")

    def _corrupt(self) -> None:
        self._failed = True
        schema.persist_stop(self.path)
        raise AccessRegistryError("CORRUPT", "invalid stored Access registry data") from None

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        self._ready()
        if write and not self._writable:
            raise AccessRegistryError("READ_ONLY", "writable Access handle required")
        if self._active:
            raise AccessRegistryError("TRANSACTION", "nested registry operation denied")
        self._active, self._writing = True, write
        try:
            self._db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield self._db
            self._ready()
            self._db.commit()
        except BaseException as error:
            if self._db.in_transaction:
                self._db.rollback()
            if isinstance(error, sqlite3.DatabaseError):
                code = getattr(error, "sqlite_errorcode", 0) & 255
                if schema.is_corruption_error(error):
                    self._corrupt()
                if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise AccessRegistryError("BUSY", "Access transaction is busy") from None
                raise AccessRegistryError("SQLITE", "Access registry operation failed") from None
            raise
        finally:
            self._active = self._writing = False

    def _scope(self, db: sqlite3.Connection, identity: str) -> AccessScope:
        row = db.execute(
            "SELECT scope_uuidv4,display_name FROM access_scopes WHERE scope_uuidv4=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise AccessRegistryError("NOT_FOUND", "Scope is not registered")
        try:
            return AccessScope(*row)
        except ValueError:
            self._corrupt()

    def _registration(self, row: tuple) -> ScopeLocatorRegistration:
        try:
            return ScopeLocatorRegistration(*row)
        except ValueError:
            self._corrupt()

    @staticmethod
    def _input(registration: ScopeLocatorRegistration) -> ScopeLocatorRegistration:
        if not isinstance(registration, ScopeLocatorRegistration):
            raise AccessRegistryError("TYPE", "typed locator registration required")
        return ScopeLocatorRegistration(*registration.key)

    @staticmethod
    def _has_registration(db: sqlite3.Connection, registration: ScopeLocatorRegistration) -> bool:
        return db.execute(
            "SELECT 1 FROM scope_locators WHERE scope_uuidv4=? AND registered_at_us=? "
            "AND scope_locator_uri=?",
            registration.key,
        ).fetchone() is not None

    def scope(self, scope_uuidv4: str) -> AccessScope:
        identity = scope_uuid(scope_uuidv4)
        with self._transaction() as db:
            return self._scope(db, identity)

    def register_scope(self, scope: AccessScope) -> Literal["insert", "duplicate"]:
        if not isinstance(scope, AccessScope):
            raise AccessRegistryError("TYPE", "typed Scope required")
        value = AccessScope(scope.scope_uuidv4, scope.display_name)
        with self._transaction(write=True) as db:
            row = db.execute(
                "SELECT display_name FROM access_scopes WHERE scope_uuidv4=?",
                (value.scope_uuidv4,),
            ).fetchone()
            if row is not None:
                if row[0] != value.display_name:
                    raise AccessRegistryError("SCOPE_CONFLICT", "use explicit label update")
                return "duplicate"
            db.execute("INSERT INTO access_scopes VALUES(?,?)", (value.scope_uuidv4, value.display_name))
            return "insert"

    def rename_scope(self, scope_uuidv4: str, display_name: str) -> None:
        identity, label = scope_uuid(scope_uuidv4), display_label(display_name)
        with self._transaction(write=True) as db:
            self._scope(db, identity)
            db.execute("UPDATE access_scopes SET display_name=? WHERE scope_uuidv4=?", (label, identity))

    def register_locator(self, registration: ScopeLocatorRegistration) -> RegistrationResult:
        value = self._input(registration)
        with self._transaction(write=True) as db:
            self._scope(db, value.scope_uuidv4)
            latest = db.execute(
                "SELECT MAX(registered_at_us) FROM scope_locators WHERE scope_uuidv4=?",
                (value.scope_uuidv4,),
            ).fetchone()[0]
            if self._has_registration(db, value):
                # Never recreate missing controls or revive disabled settings on replay.
                return RegistrationResult("duplicate", latest, False)
            db.execute("INSERT INTO scope_locators VALUES(?,?,?)", value.key)
            db.execute("INSERT INTO scope_locator_controls VALUES(?,?,?,0)", value.key)
            return RegistrationResult("insert", latest, latest is not None and value.registered_at_us < latest)

    def first_choices(
        self, scope_uuidv4: str, *, max_candidates: int = 1000
    ) -> tuple[ScopeLocatorRegistration, ...]:
        identity, bound = scope_uuid(scope_uuidv4), page_size(max_candidates)
        with self._transaction() as db:
            self._scope(db, identity)
            rows = db.execute(
                "SELECT * FROM scope_first_choices WHERE scope_uuidv4=? "
                "ORDER BY scope_locator_uri LIMIT ?",
                (identity, bound + 1),
            ).fetchall()
            if len(rows) > bound:
                raise AccessRegistryError("CANDIDATE_LIMIT", "latest tie set exceeds explicit bound")
            # Lexical ordering is display stability, NOT winner selection.
            return tuple(self._registration(row) for row in rows)

    def history(
        self,
        scope_uuidv4: str,
        *,
        limit: int = 100,
        after: ScopeLocatorRegistration | None = None,
    ) -> RegistrationPage:
        identity, bound = scope_uuid(scope_uuidv4), page_size(limit)
        cursor = None if after is None else self._input(after)
        if cursor is not None and cursor.scope_uuidv4 != identity:
            raise AccessRegistryError("CURSOR_SCOPE", "history cursor has a different Scope")
        with self._transaction() as db:
            self._scope(db, identity)
            if cursor is not None and not self._has_registration(db, cursor):
                raise AccessRegistryError("CURSOR", "history cursor registration is absent")
            clause, args = "", (identity,)
            if cursor is not None:
                clause = " AND (registered_at_us<? OR (registered_at_us=? AND scope_locator_uri>?))"
                args += (cursor.registered_at_us, cursor.registered_at_us, cursor.scope_locator_uri)
            rows = db.execute(
                "SELECT * FROM scope_locators WHERE scope_uuidv4=?" + clause
                + " ORDER BY registered_at_us DESC,scope_locator_uri LIMIT ?",
                (*args, bound + 1),
            ).fetchall()
            values = tuple(self._registration(row) for row in rows[:bound])
            return RegistrationPage(values, values[-1] if len(rows) > bound else None)

    def locator_enabled(self, registration: ScopeLocatorRegistration) -> bool:
        value = self._input(registration)
        with self._transaction() as db:
            if not self._has_registration(db, value):
                raise AccessRegistryError("NOT_FOUND", "locator registration is absent")
            row = db.execute(
                "SELECT enabled FROM scope_locator_controls WHERE scope_uuidv4=? "
                "AND registered_at_us=? AND scope_locator_uri=?", value.key
            ).fetchone()
            if row is None:
                return False
            if type(row[0]) is not int or row[0] not in (0, 1):
                self._corrupt()
            return bool(row[0])

    def set_locator_enabled(self, registration: ScopeLocatorRegistration, enabled: bool) -> None:
        value = self._input(registration)
        if type(enabled) is not bool:
            raise AccessRegistryError("TYPE", "enabled must be boolean")
        with self._transaction(write=True) as db:
            if not self._has_registration(db, value):
                raise AccessRegistryError("NOT_FOUND", "locator registration is absent")
            row = db.execute(
                "SELECT 1 FROM scope_locator_controls WHERE scope_uuidv4=? "
                "AND registered_at_us=? AND scope_locator_uri=?", value.key
            ).fetchone()
            if row is None:
                # Unlike replay, this is an explicit control operation.
                db.execute("INSERT INTO scope_locator_controls VALUES(?,?,?,?)", (*value.key, int(enabled)))
            else:
                db.execute(
                    "UPDATE scope_locator_controls SET enabled=? WHERE scope_uuidv4=? "
                    "AND registered_at_us=? AND scope_locator_uri=?", (int(enabled), *value.key)
                )
