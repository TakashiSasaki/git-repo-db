"""P4 Operational continuation metadata; never stages incoming body bytes."""

import json

from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import encode


class NotesProgress:
    def __init__(self, work):
        self.work = work

    def _check(self):
        self.work.ledger.validate_continuation(
            self.work.request, self.work.attempt_uuidv4
        )
        self.work.require("metadata_units", 1)
        self.work.charge("metadata_units", 1)

    def load(self, scope):
        self._check()
        row = self.work.ledger.db.execute(
            "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? "
            "AND request_uuidv4=? AND continuation_scope_json=?",
            (*self.work.request.values(), scope),
        ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, ValueError) as error:
            raise CoordinationError(
                "CONTINUATION_UNAVAILABLE", "notes-progress"
            ) from error

    def save_once(self, scope, value):
        self._check()
        db = self.work.ledger.db
        if db.in_transaction:
            raise CoordinationError("ACCOUNTING_TRANSACTION", "notes-progress")
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute(
                "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? "
                "AND request_uuidv4=? AND continuation_scope_json=?",
                (*self.work.request.values(), scope),
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO request_continuations VALUES(?,?,?,?)",
                    (*self.work.request.values(), scope, encode(value)),
                )
                result = value
            else:
                result = json.loads(row[0])
            db.commit()
            return result
        except BaseException:
            db.rollback()
            raise
