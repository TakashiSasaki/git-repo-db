"""Bounded optional Search timing history in checkpointed Operational progress."""

import json
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.catalog_runtime import (
    SnapshotReadLimits,
    apply_snapshot_read_limits,
    catalog_completion,
    catalog_gate,
)
from repo_catalog.adapters.sqlite.operational_rows import ROW_TYPES
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
from repo_catalog.domain.shared_values import encode

_REQUEST = ["search-maintenance", 1]
_RUN = encode(["search-maintenance-run", 1])
_KINDS = {"git_metadata", "notes", "context_text"}


class SearchTelemetry:
    def __init__(self, directory, *, max_runs=1000):
        if type(max_runs) is not int or not 0 < max_runs <= 10000:
            raise ValueError("finite Search telemetry history bound required")
        self.directory, self.max_runs = Path(directory), max_runs

    def _stop(self):
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoordinationError("RECOVERY_REQUIRED", "catalog")

    @staticmethod
    def _validate(value):
        if (
            type(value) is not dict
            or set(value) != {"counts", "duration_ns"}
            or type(value["duration_ns"]) is not int
            or value["duration_ns"] < 0
            or type(value["counts"]) is not dict
            or not value["counts"]
            or set(value["counts"]) - _KINDS
            or any(
                type(count) is not int or count < 0
                for count in value["counts"].values()
            )
        ):
            raise ValueError("invalid recorded Search rebuild")
        return value

    def _ledger(self, identity):
        if not (self.directory / "operational.sqlite3").is_file():
            raise FileNotFoundError("Operational telemetry is not initialized")
        ledger = OperationalAcquisitionLedger(
            self.directory,
            repository_uuidv4=identity[0],
            catalog_instance_uuidv4=identity[1],
        )
        try:
            apply_snapshot_read_limits(ledger.db, SnapshotReadLimits())
            return ledger
        except BaseException:
            ledger.close()
            raise

    def history(self, identity, kinds):
        self._stop()
        with (
            catalog_gate(self.directory, exclusive=False),
            self._ledger(identity) as ledger,
        ):
            ledger.db.execute("BEGIN")
            sizes = ledger.db.execute(
                "SELECT octet_length(cursor_json) FROM request_continuations WHERE continuation_scope_json=? LIMIT ?",
                (_RUN, self.max_runs + 1),
            ).fetchall()
            if len(sizes) > self.max_runs or any(
                type(row[0]) is not int or row[0] > 8192 for row in sizes
            ):
                raise ValueError("finite Search telemetry history limit")
            rows = ledger.db.execute(
                "SELECT * FROM request_continuations WHERE continuation_scope_json=? ORDER BY request_origin_uuidv4,request_uuidv4 LIMIT ?",
                (_RUN, self.max_runs),
            ).fetchall()
            durations = []
            for raw in rows:
                row = ROW_TYPES["request_continuations"].from_record(raw)
                request = RequestIdentity(row.request_origin_uuidv4, row.request_uuidv4)
                original = ledger.db.execute(
                    "SELECT request_scope_json,state FROM acquisition_requests WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                    request.values(),
                ).fetchone()
                checkpoint = ledger.db.execute(
                    "SELECT CASE WHEN octet_length(cursor_json)<=8192 THEN cursor_json END FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
                    (*request.values(), ledger.work_ledger._CHECKPOINT_SCOPE),
                ).fetchone()
                if (
                    original is None
                    or checkpoint is None
                    or checkpoint[0] is None
                    or original[0] != encode(_REQUEST)
                ):
                    raise ValueError("Search telemetry request binding unavailable")
                ledger.work_ledger._check_inventory(
                    request, original[0], json.loads(checkpoint[0])
                )
                value = self._validate(json.loads(row.cursor_json))
                if encode(value) != row.cursor_json:
                    raise ValueError("noncanonical Search telemetry record")
                if original[1] == "complete" and set(value["counts"]) == set(kinds):
                    durations.append(value["duration_ns"])
            with catalog_completion(self.directory):
                self._stop()
                if (
                    ledger.work_ledger._stat_identity()
                    != ledger.work_ledger._file_identity
                ):
                    raise CoordinationError("CONTINUATION_UNAVAILABLE", "telemetry")
            return {
                "runs": len(durations),
                "average_duration_ns": sum(durations) // len(durations)
                if durations
                else None,
                "estimated_duration_ns": sum(durations) // len(durations)
                if durations
                else None,
            }

    def record(self, identity, counts, duration_ns):
        value = self._validate({"counts": counts, "duration_ns": duration_ns})
        self._stop()
        with (
            catalog_gate(self.directory, exclusive=True),
            ExitStack() as completion,
            self._ledger(identity) as ledger,
        ):
            size = ledger.db.execute(
                "SELECT count(*) FROM request_continuations WHERE continuation_scope_json=?",
                (_RUN,),
            ).fetchone()[0]
            if size >= self.max_runs:
                raise ValueError("finite Search telemetry history limit")
            request = RequestIdentity(identity[0], str(uuid4()))
            ledger.ensure_request(request, scope=_REQUEST, new_request=True)
            with ledger.work_ledger._checked(request, write=True) as checkpoint:
                ledger.work_ledger._put_continuation(
                    request, checkpoint, _RUN, encode(value)
                )
                # No source allocations exist on this telemetry-only request.
                ledger.db.execute(
                    "UPDATE acquisition_requests SET state='complete' WHERE request_origin_uuidv4=? AND request_uuidv4=?",
                    request.values(),
                )
                completion.enter_context(catalog_completion(self.directory))
                self._stop()
                if (
                    ledger.work_ledger._stat_identity()
                    != ledger.work_ledger._file_identity
                ):
                    raise CoordinationError("CONTINUATION_UNAVAILABLE", "telemetry")
