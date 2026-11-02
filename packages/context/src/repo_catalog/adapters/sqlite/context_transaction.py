"""Context callback transaction capability, shared by standalone and paired admission."""

import sqlite3

from repo_catalog.adapters.sqlite.catalog_runtime import _Cursor
from repo_catalog.domain.p1_coordination import CoordinationError


class AdmissionTransaction:
    """Supported callback connection that cannot end the enclosing transaction.

    Domain authorizers compose with the transaction guard. Deliberate access to
    private infrastructure or arbitrary Python/filesystem privilege is outside
    the supported boundary.
    """

    def __init__(self, db: sqlite3.Connection, *, _context_admission=None):
        self._db = db
        self._active = True
        self._context_admission = _context_admission
        self.set_authorizer(None)

    def _check_active(self):
        if not self._active:
            raise CoordinationError("CAPABILITY_EXPIRED", "admission")

    def _check_admission_active(self):
        from repo_catalog.domain.context_admission import AdmissionRefused

        if not self._active or not self._db.in_transaction:
            raise AdmissionRefused("PERMISSION_DENIED")

    @property
    def context_admission_binding(self):
        self._check_admission_active()
        return self._context_admission

    def _expire(self):
        self._active = False

    @property
    def in_transaction(self):
        self._check_active()
        return self._db.in_transaction

    @property
    def total_changes(self):
        """Read-only connection-local count for committed-unit replay reporting."""
        self._check_active()
        return self._db.total_changes

    def set_authorizer(self, callback):
        self._check_active()

        def authorize(action, first, second, database, trigger):
            if action not in {
                sqlite3.SQLITE_SELECT,
                sqlite3.SQLITE_READ,
                sqlite3.SQLITE_FUNCTION,
                sqlite3.SQLITE_INSERT,
                sqlite3.SQLITE_UPDATE,
                sqlite3.SQLITE_DELETE,
                sqlite3.SQLITE_SAVEPOINT,
                sqlite3.SQLITE_RECURSIVE,
            }:
                return sqlite3.SQLITE_DENY
            if callback is not None:
                return callback(action, first, second, database, trigger)
            return sqlite3.SQLITE_OK

        self._db.set_authorizer(authorize)

    def execute(self, sql, parameters=()):
        self._check_active()
        return _Cursor(self._db.execute(sql, parameters), self)

    def executemany(self, sql, parameters):
        self._check_active()
        return _Cursor(self._db.executemany(sql, parameters), self)

    def _read_call(self, operation, *args):
        self._check_active()
        return operation(*args)

    def commit(self):
        raise CoordinationError("TRANSACTION_OWNERSHIP", "admission")

    rollback = commit

    def executescript(self, _sql):
        raise CoordinationError("TRANSACTION_OWNERSHIP", "admission")
