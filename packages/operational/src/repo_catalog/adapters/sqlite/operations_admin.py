"""Administrative request state transitions preserving cumulative accounting."""

import json
from pathlib import Path

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.catalog_runtime import (
    catalog_completion,
    catalog_gate,
)
from repo_catalog.adapters.sqlite.managed_git_cache import reserved_disk_bytes
from repo_catalog.domain.p1_coordination import CoordinationError


class OperationsAdmin:
    def __init__(self, directory):
        self.directory = Path(directory)

    def _stop(self):
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoordinationError("RECOVERY_REQUIRED", "catalog")

    def inspect(self, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit must be 1..1000")
        self._stop()
        with (
            catalog_gate(self.directory, exclusive=False),
            OperationalAcquisitionLedger(self.directory) as store,
        ):
            rows = store.db.execute(
                "SELECT request_origin_uuidv4,request_uuidv4,request_scope_json,state FROM acquisition_requests ORDER BY request_origin_uuidv4,request_uuidv4 LIMIT ?",
                (limit + 1,),
            ).fetchall()
            result = {
                "requests": [dict(row) for row in rows[:limit]],
                "has_more": len(rows) > limit,
                "cache_locators": [
                    dict(row)
                    for row in store.db.execute(
                        "SELECT * FROM cache_locators ORDER BY repository_uuidv4,cache_purpose,semantic_coordinate_json LIMIT ?",
                        (limit,),
                    )
                ],
            }
            with catalog_completion(self.directory):
                self._stop()
            return result

    def transition(self, request, *, resume=False, complete=False):
        self._stop()
        with (
            catalog_gate(self.directory, exclusive=True),
            OperationalAcquisitionLedger(self.directory) as store,
        ):
            ledger = store.work_ledger
            ledger._ready()
            store.db.execute("BEGIN IMMEDIATE")
            try:
                row = store.db.execute(
                    "SELECT state,request_scope_json FROM acquisition_requests WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                    request.values(),
                ).fetchone()
                if row is None or row[0] == "complete":
                    raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
                # Temporarily open inside the locked transaction so the canonical
                # checkpoint verifier checks every existing reservation/progress.
                store.db.execute(
                    "UPDATE acquisition_requests SET state='open' WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                    request.values(),
                )
                ledger._validated.clear()
                ledger._check(request, scope=row[1])
                if complete and reserved_disk_bytes(store.db, request):
                    raise CoordinationError("CAPACITY_RESERVATION_ACTIVE", "request")
                state = "complete" if complete else "open" if resume else "stopped"
                store.db.execute(
                    "UPDATE acquisition_requests SET state=? WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                    (state, *request.values()),
                )
                self._stop()
                store.db.commit()
            except BaseException:
                store.db.rollback()
                raise
            return {
                "request": request.values(),
                "state": state,
                "scope": json.loads(row[1]),
            }

    def increase(self, request, unit, value):
        self._stop()
        with (
            catalog_gate(self.directory, exclusive=False),
            OperationalAcquisitionLedger(self.directory) as store,
        ):
            store.work_ledger.increase_limit(request, unit, value)
            return store.work_ledger.usage(request)

    def show(self, request):
        self._stop()
        with (
            catalog_gate(self.directory, exclusive=False),
            OperationalAcquisitionLedger(self.directory) as store,
        ):
            row = store.db.execute(
                "SELECT * FROM acquisition_requests WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                request.values(),
            ).fetchone()
            if row is None:
                raise CoordinationError("CONTINUATION_UNAVAILABLE", "request")
            budgets = [
                dict(item)
                for item in store.db.execute(
                    "SELECT work_kind,finite_limit,spent_or_reserved FROM request_budgets WHERE request_origin_uuidv4=? AND request_uuidv4=? ORDER BY work_kind",
                    request.values(),
                )
            ]
            attempts = [
                dict(item)
                for item in store.db.execute(
                    "SELECT * FROM acquisition_attempts WHERE request_origin_uuidv4=? AND request_uuidv4=? ORDER BY attempt_uuidv4",
                    request.values(),
                )
            ]
            if row["state"] == "open":
                store.work_ledger.validate_continuation(request)
            with catalog_completion(self.directory):
                self._stop()
            return {
                "request": dict(row),
                "budgets": budgets,
                "attempts": len(attempts),
                "attempt_records": attempts,
            }
