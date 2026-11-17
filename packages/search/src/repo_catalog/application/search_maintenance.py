"""Search maintenance with optional Operational timing, never projection authority."""

import sqlite3
import time

from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.query_contracts import SnapshotFenceToken
from repo_catalog.domain.search_query import SEARCH_PROJECTION_KINDS
from repo_catalog.domain.shared_values import CoreFailure

_NO_ESTIMATE = {"runs": 0, "average_duration_ns": None, "estimated_duration_ns": None}
_OPTIONAL_ERRORS = (
    ImportError,
    OSError,
    ValueError,
    sqlite3.Error,
    CoordinationError,
    CoreFailure,
)


class SearchMaintenance:
    def __init__(self, reader, *, clock_ns=time.perf_counter_ns, max_runs=1000):
        if type(max_runs) is not int or not 0 < max_runs <= 10000:
            raise ValueError("finite Search telemetry history bound required")
        self.reader, self.clock_ns, self.max_runs = reader, clock_ns, max_runs

    def _telemetry(self, token, kinds, *, counts=None, duration_ns=None):
        fence = SnapshotFenceToken.parse(token)
        identity = (fence.repository_uuidv4, fence.catalog_instance_uuidv4)
        try:
            from repo_catalog.adapters.sqlite.search_maintenance import SearchTelemetry

            history = SearchTelemetry(self.reader.directory, max_runs=self.max_runs)
            if counts is not None:
                history.record(identity, counts, duration_ns)
            estimate = history.history(identity, kinds)
            return {
                "telemetry_status": "available",
                "telemetry_diagnostic": None,
                "estimate": estimate,
            }
        except _OPTIONAL_ERRORS as error:
            if getattr(error, "code", None) in {
                "RECOVERY_REQUIRED",
                "RECOVERY_STOP",
                "AUTHORITATIVE_CORRUPTION",
            }:
                raise
            return {
                "telemetry_status": "uninitialized"
                if isinstance(error, FileNotFoundError)
                else "unavailable",
                "telemetry_diagnostic": type(error).__name__,
                "estimate": dict(_NO_ESTIMATE),
            }

    def status(self, projection_kinds=SEARCH_PROJECTION_KINDS, *, work=None):
        result = self.reader.search_projection_status(projection_kinds, work=work)
        return {**result, **self._telemetry(result["snapshot_token"], projection_kinds)}

    def rebuild(self, projection_kinds=SEARCH_PROJECTION_KINDS, *, work=None):
        started = self.clock_ns()
        counts = self.reader.rebuild_search(projection_kinds, work=work)
        finished = self.clock_ns()
        if type(started) is not int or type(finished) is not int or finished < started:
            raise ValueError("monotonic integer rebuild clock required")
        duration = finished - started
        token = self.reader.snapshot_token().encode()
        return {
            "counts": counts,
            "duration_ns": duration,
            "snapshot_token": token,
            **self._telemetry(
                token, tuple(counts), counts=counts, duration_ns=duration
            ),
        }
