"""Explicit catalog3 diagnostics; ordinary runtime queries use QueryService."""

from __future__ import annotations

import base64
import binascii
import json
import math
import sqlite3
import time

from repo_catalog.adapters.sqlite.target import TargetReader
from repo_catalog.domain.models import (
    CancellationToken,
    CatalogError,
    CoverageReport,
    Result,
)


def row_fields(row):
    result = dict(row)
    for key in (
        "metadata",
        "payload",
        "details",
        "request",
        "settings",
        "scope",
        "acquisition_scope_json",
        "field_evidence_json",
    ):
        if isinstance(result.get(key), str):
            result[key] = json.loads(result[key])
    return result


def object_fields(row):
    return {
        "git_object_id": row["git_object_id"],
        "oid": f"{row['object_format']}:{row['oid'].hex()}",
        "type": row["type"],
        "byte_length": row["size"],
        "verified": bool(row["verified"]),
    }


class TargetQueryService:
    def __init__(self, database, *, allow_building=False, token=None):
        self.database = database
        self.allow_building = allow_building
        self.token = token or CancellationToken()

    def query(self, command, options=None, *, limit=100, offset=0, timeout=30):
        if (
            type(limit) is not int
            or not 1 <= limit <= 1000
            or type(offset) is not int
            or offset < 0
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise CatalogError(
                "INVALID_ARGUMENT",
                "Limit must be 1..1000, offset nonnegative and timeout positive",
            )
        self.token.check()
        with TargetReader(self.database, allow_building=self.allow_building) as reader:
            self.s = reader
            self.coverage = CoverageReport()
            self.deadline = time.monotonic() + timeout
            identity = reader.identity
            catalog = {
                key: identity[key]
                for key in (
                    "db_instance_id",
                    "local_revision",
                    "format_id",
                    "schema_version",
                    "lifecycle",
                )
            }
            if identity["lifecycle"] == "building":
                self._add_missing("target", "building_diagnostic_read")
            reader.connection.set_progress_handler(
                lambda: self.token.cancelled or time.monotonic() > self.deadline, 1000
            )
            items, has_more, size = [], False, 0
            try:
                for index, item in enumerate(self._rows(command, options or {})):
                    self._check()
                    if index < offset:
                        continue
                    if has_more:
                        continue
                    item_size = len(json.dumps(item, default=lambda value: value.hex()))
                    if len(items) == limit or items and size + item_size > 8_388_608:
                        has_more = True
                        # Finish the scan so missing-content coverage describes
                        # the requested scope, including candidates after this page.
                        continue
                    items.append(item)
                    size += item_size
                reader.ensure_unchanged()
            except (TimeoutError, sqlite3.OperationalError) as error:
                self.token.check()
                if (
                    not isinstance(error, TimeoutError)
                    and "interrupt" not in str(error).lower()
                ):
                    raise
                reader.ensure_unchanged()
                self._add_missing("execution", "timeout")
                return Result(
                    self._page([], limit, offset, None),
                    self.coverage,
                    "partial",
                    catalog,
                    {"completed": False, "timed_out": True, "backend": "scan"},
                )
            return Result(
                self._page(items, limit, offset, has_more),
                self.coverage,
                "complete" if self.coverage.complete_for_requested_scope else "partial",
                catalog,
                {"completed": True, "timed_out": False, "backend": "scan"},
                ["Diagnostic target reads do not establish runtime readiness"]
                if identity["lifecycle"] == "building"
                else [],
            )

    @staticmethod
    def _page(items, limit, offset, has_more):
        return {
            "items": items,
            "page": {
                "limit": limit,
                "returned": len(items),
                "has_more": has_more,
                "next_cursor": None,
                "total": None,
                "next_offset": offset + len(items) if has_more else None,
            },
        }

    def _check(self):
        self.token.check()
        if time.monotonic() > self.deadline:
            raise TimeoutError()

    def _add_missing(self, kind, reason, **details):
        # A scan can discover many missing originals. Retain bounded evidence
        # without turning missing content into a claim of complete coverage.
        if len(self.coverage.missing) < 1000:
            self.coverage.add(kind, reason, **details)
        elif len(self.coverage.missing) == 1000:
            self.coverage.add("coverage", "additional_missing_details", count=1)
        else:
            self.coverage.missing[-1]["count"] += 1

    def _repo(self, options):
        repo = options.get("repo")
        if not repo:
            raise CatalogError("INVALID_ARGUMENT", "An explicit --repo ID is required")
        if not self.s.one(
            "SELECT 1 FROM repositories WHERE repository_uuidv4=?", (repo,)
        ):
            raise CatalogError("NOT_FOUND", "Target repository not found")
        return repo

    @staticmethod
    def _path(options):
        if options.get("path") is not None and options.get("path_b64") is not None:
            raise CatalogError("INVALID_ARGUMENT", "Path forms are mutually exclusive")
        try:
            if options.get("path_b64") is not None:
                return base64.b64decode(options["path_b64"], validate=True)
            if options.get("path") is not None:
                return options["path"].encode("utf8")
        except (ValueError, TypeError, binascii.Error) as cause:
            raise CatalogError("INVALID_ARGUMENT", "Invalid raw path") from cause
        raise CatalogError("INVALID_ARGUMENT", "A raw path is required")

    def _rows(self, command, options):
        from repo_catalog.application.query_service import QueryService

        query = QueryService.__new__(QueryService)
        query.s = self.s
        query.token = self.token
        query.coverage = self.coverage
        query.collection_proof_graph = None
        query.deadline = self.deadline
        query.backend = "scan"
        query.literal_cache = {}
        mapped = {
            "repos": "repos list",
            "commit": "commits show",
            "tree": "tree list",
            "file": "file show",
            "pr": "pr show",
        }.get(command)
        options = dict(options)
        if command == "pr":
            options["number"] = options.get("number", options.get("pr"))
        elif command == "search":
            kind = options.get("kind", "code")
            if kind not in {"code", "path", "hash", "commits", "pr", "issue"}:
                raise CatalogError("INVALID_ARGUMENT", "Unknown target search kind")
            mapped = "search " + kind
        if mapped is None:
            raise CatalogError("INVALID_ARGUMENT", "Unknown target query")
        query.prepare_coverage("pr list" if mapped == "search pr" else mapped, options)
        for _, row in query.iter_query(mapped, options):
            yield {**row, "record_kind": "change_request"} if command == "pr" else row
        if command == "pr":
            for _, row in query.iter_query("pr documents", options):
                kind = row["document_kind"]
                yield {
                    **row,
                    "record_kind": "review_comment"
                    if kind == "review-comment"
                    else "review"
                    if kind == "review"
                    else "document",
                }
            for _, row in query.iter_query("pr threads", options):
                yield {**row, "record_kind": "review_thread"}
            for _, row in query.iter_query("pr code", options):
                yield {**row, "record_kind": "code_" + row["kind"]}
