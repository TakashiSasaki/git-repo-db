"""Transaction-owner guard shared by authoritative admission callbacks."""

import sqlite3

from repo_catalog.adapters.sqlite.catalog_runtime import _Cursor
from repo_catalog.domain.p1_coordination import CoordinationError


class AdmissionTransaction:
    """Callback connection that cannot end its enclosing transaction."""

    def __init__(self, db: sqlite3.Connection):
        self._db = db
        self._active = True
        self.set_authorizer(None)

    def _check_active(self):
        if not self._active:
            raise CoordinationError("CAPABILITY_EXPIRED", "admission")

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
