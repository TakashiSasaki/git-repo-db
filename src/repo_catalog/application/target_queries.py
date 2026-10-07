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
    GitOid,
    Result,
    path_fields,
)


def row_fields(row):
    result = dict(row)
    for key in ("metadata", "payload", "details", "request", "settings", "scope"):
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
                    "publication_seq",
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
                [
                    "Diagnostic target reads do not establish publication or runtime readiness"
                ]
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
        if not self.s.one("SELECT 1 FROM repositories WHERE repository_id=?", (repo,)):
            raise CatalogError("NOT_FOUND", "Target repository not found")
        return repo

    def _rows(self, command, options):
        if command == "repos":
            yield from self._repositories(options)
        elif command in ("commit", "tree", "file"):
            repo = self._repo(options)
            obj = self._commit_object(repo, options.get("commit"))
            commit = self.s.one(
                "SELECT * FROM commits WHERE git_object_id=?", (obj["git_object_id"],)
            )
            if commit is None:
                self._add_missing(
                    "git",
                    "commit_structure_missing",
                    git_object_id=obj["git_object_id"],
                )
                yield object_fields(obj)
            elif command == "commit":
                yield self._commit_details(obj, commit)
            else:
                raw_path = self._path(options) if command == "file" else None
                found = False
                for entry in self._tree(commit["tree_git_object_id"]):
                    if raw_path is not None and entry["raw_path"] != raw_path:
                        continue
                    found = True
                    raw = entry.pop("raw_path")
                    if (
                        command == "file"
                        and entry["text"] is None
                        and entry["mode"] != "160000"
                    ):
                        self._add_missing(
                            "code",
                            "body_not_saved",
                            content_id=entry["content_id"],
                            **path_fields(raw),
                        )
                    if command == "tree":
                        entry.pop("text")
                    yield {**path_fields(raw), **entry}
                if command == "file" and not found:
                    raise CatalogError(
                        "NOT_FOUND", "Raw path not present in stored commit tree"
                    )
        elif command == "pr":
            yield from self._pr(options)
        elif command == "search":
            yield from self._search(options)
        else:
            raise CatalogError("INVALID_ARGUMENT", "Unknown target query")

    def _repositories(self, options):
        repo = options.get("repo")
        if repo:
            self._repo(options)
        for row in self.s.execute(
            "SELECT * FROM repositories WHERE (? IS NULL OR repository_id=?) ORDER BY repository_id",
            (repo, repo),
        ):
            self._check()
            yield {
                **row_fields(row),
                "bindings": [
                    row_fields(r)
                    for r in self.s.execute(
                        "SELECT * FROM repository_bindings WHERE repository_id=? ORDER BY repository_binding_id",
                        (row["repository_id"],),
                    )
                ],
                "endpoints": [
                    row_fields(r)
                    for r in self.s.execute(
                        "SELECT * FROM repository_endpoints WHERE repository_id=? ORDER BY repository_endpoint_id",
                        (row["repository_id"],),
                    )
                ],
                "name_assertions": [
                    dict(r)
                    for r in self.s.execute(
                        "SELECT * FROM repository_name_assertions WHERE repository_id=? ORDER BY name",
                        (row["repository_id"],),
                    )
                ],
                "sources": [
                    dict(r)
                    for r in self.s.execute(
                        "SELECT * FROM source_repositories WHERE repository_id=? ORDER BY source_id",
                        (row["repository_id"],),
                    )
                ],
            }

    def _commit_object(self, repo, value):
        oid = GitOid.parse(value or "")
        row = self.s.one(
            "SELECT g.* FROM git_objects g WHERE g.object_format=? AND g.oid=? AND g.type='commit' AND (EXISTS(SELECT 1 FROM repository_object_sources r WHERE r.repository_id=? AND r.git_object_id=g.git_object_id) OR EXISTS(SELECT 1 FROM acquisition_roots r WHERE r.repository_id=? AND r.object_format=g.object_format AND r.oid=g.oid))",
            (oid.algorithm, oid.value, repo, repo),
        )
        if not row:
            raise CatalogError(
                "NOT_FOUND",
                "Stored commit is not attributed to the selected repository",
            )
        return row

    def _commit_details(self, obj, commit):
        tree = self.s.one(
            "SELECT * FROM git_objects WHERE git_object_id=?",
            (commit["tree_git_object_id"],),
        )
        parents = [
            {"ordinal": r["parent_ordinal"], **object_fields(r)}
            for r in self.s.execute(
                "SELECT p.parent_ordinal,g.* FROM commit_parents p JOIN git_objects g ON g.git_object_id=p.parent_git_object_id WHERE p.commit_git_object_id=? ORDER BY p.parent_ordinal",
                (obj["git_object_id"],),
            )
        ]
        return {
            **object_fields(obj),
            "tree": object_fields(tree),
            "parents": parents,
            "raw_headers": commit["raw_headers"],
            "raw_message": commit["raw_message"],
            "message_display": commit["raw_message"].decode("utf8", "backslashreplace"),
            "metadata": json.loads(commit["metadata"]),
        }

    @staticmethod
    def _path(options):
        if (options.get("path") is None) == (options.get("path_b64") is None):
            raise CatalogError(
                "INVALID_ARGUMENT", "Specify exactly one of --path and --path-b64"
            )
        if options.get("path_b64") is None:
            return options["path"].encode("utf8")
        try:
            return base64.b64decode(options["path_b64"], validate=True)
        except (ValueError, binascii.Error):
            raise CatalogError("INVALID_ARGUMENT", "Malformed base64 path") from None

    def _tree(self, tree):
        # Explicit frames preserve arbitrary raw names and reject cycles without
        # relying on textual SQLite concatenation or running Git.
        frames = [(tree, b"", frozenset())]
        while frames:
            self._check()
            ident, prefix, ancestors = frames.pop()
            if ident in ancestors:
                self._add_missing("git", "tree_cycle", git_object_id=ident)
                continue
            rows = self.s.all(
                "SELECT * FROM tree_entries WHERE tree_git_object_id=? ORDER BY raw_name",
                (ident,),
            )
            if not rows:
                obj = self.s.one(
                    "SELECT size FROM git_objects WHERE git_object_id=?", (ident,)
                )
                if obj and obj["size"]:
                    self._add_missing(
                        "git", "tree_structure_missing", git_object_id=ident
                    )
            subtrees = []
            for row in rows:
                self._check()
                path = prefix + row["raw_name"]
                if row["mode"] == 16384:
                    subtrees.append(
                        (row["child_git_object_id"], path + b"/", ancestors | {ident})
                    )
                    continue
                content = self.s.one(
                    "SELECT c.* FROM blob_content_map b JOIN contents c ON c.content_id=b.content_id WHERE b.git_object_id=?",
                    (row["child_git_object_id"],),
                )
                digests = self._digests(content["content_id"]) if content else []
                yield {
                    "raw_path": path,
                    "mode": format(row["mode"], "06o"),
                    "git_object_id": row["child_git_object_id"],
                    "oid": f"{row['child_format']}:{row['child_oid'].hex()}",
                    "content_id": content["content_id"] if content else None,
                    "byte_length": content["byte_length"] if content else None,
                    "text_state": content["text_state"] if content else "unknown",
                    "text": content["raw_text"] if content else None,
                    "raw_available": bool(content and content["raw_text"] is not None),
                    "digests": digests,
                }
            frames.extend(reversed(subtrees))

    def _digests(self, content):
        return [
            {**dict(row), "digest": row["digest"].hex()}
            for row in self.s.execute(
                "SELECT * FROM content_digests WHERE content_id=? ORDER BY algorithm",
                (content,),
            )
        ]

    def _pr_identity(self, options):
        repo = self._repo(options)
        number = options.get("provider_change_request_number")
        if type(number) is not int or number <= 0:
            raise CatalogError(
                "INVALID_ARGUMENT",
                "A positive --provider-change-request-number is required",
            )
        kind = options.get("change_request_kind", "pull_request")
        if kind not in ("pull_request", "merge_request"):
            raise CatalogError("INVALID_ARGUMENT", "Unknown request kind")
        rows = self.s.all(
            "SELECT * FROM change_requests WHERE repository_id=? AND provider_change_request_number=? AND change_request_kind=? AND (? IS NULL OR repository_binding_id=?) ORDER BY change_request_id",
            (repo, number, kind, options.get("binding"), options.get("binding")),
        )
        if not rows:
            raise CatalogError("NOT_FOUND", "Change request not found")
        if len(rows) != 1:
            raise CatalogError(
                "INVALID_ARGUMENT", "Number is ambiguous; select an explicit --binding"
            )
        return rows[0]

    def _pr_coverage(self, ident):
        if not self.s.one(
            "SELECT 1 FROM change_request_observations WHERE change_request_id=? LIMIT 1",
            (ident,),
        ):
            self._add_missing(
                "pr", "change_request_observation_missing", change_request_id=ident
            )
        for row in self.s.execute(
            "SELECT l.code_listing_id,p.state,p.page_count,p.terminal,p.context_proven FROM code_listings l LEFT JOIN code_listing_progress p ON p.code_listing_id=l.code_listing_id WHERE l.change_request_id=? ORDER BY l.code_listing_id",
            (ident,),
        ):
            if row["state"] != "complete":
                self._add_missing("pr", "code_listing_incomplete", **dict(row))
        for row in self.s.execute(
            "SELECT code_observation_id,state FROM code_observations WHERE change_request_id=? AND state!='complete' ORDER BY code_observation_id",
            (ident,),
        ):
            self._add_missing("pr", "code_observation_incomplete", **dict(row))
        for row in self.s.execute(
            "SELECT c.fetch_collection_id,p.state,p.reason saved_reason,p.cursor FROM fetch_collections c LEFT JOIN collection_progress p ON p.fetch_collection_id=c.fetch_collection_id WHERE c.change_request_id=? ORDER BY c.fetch_collection_id",
            (ident,),
        ):
            if row["state"] != "complete":
                self._add_missing("pr", "collection_incomplete", **dict(row))
        for row in self.s.execute(
            "SELECT d.change_request_id,d.kind,d.provider_change_request_document_id FROM documents d WHERE d.change_request_id=? AND NOT EXISTS(SELECT 1 FROM document_observations o WHERE o.change_request_id=d.change_request_id AND o.kind=d.kind AND o.provider_change_request_document_id=d.provider_change_request_document_id) ORDER BY d.kind,d.provider_change_request_document_id",
            (ident,),
        ):
            self._add_missing("pr", "document_body_missing", **dict(row))
        for row in self.s.execute(
            "SELECT s.coverage_scope_id,c.effective_state FROM coverage_scopes s LEFT JOIN coverage_claims c ON c.coverage_scope_id=s.coverage_scope_id WHERE s.change_request_id=? ORDER BY s.coverage_scope_id,c.coverage_claim_id",
            (ident,),
        ):
            if row["effective_state"] not in ("complete", "not_applicable"):
                self._add_missing("pr", "saved_scope_incomplete", **dict(row))

    def _pr(self, options):
        request = self._pr_identity(options)
        ident = request["change_request_id"]
        self._pr_coverage(ident)
        yield {"record_kind": "change_request", **row_fields(request)}
        queries = (
            (
                "observation",
                "SELECT * FROM change_request_observations WHERE change_request_id=? ORDER BY change_request_observation_id",
            ),
            (
                "document",
                "SELECT * FROM documents WHERE change_request_id=? ORDER BY kind,provider_change_request_document_id",
            ),
            (
                "document_observation",
                "SELECT o.*,b.body,b.byte_length FROM document_observations o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.change_request_id=? ORDER BY o.document_observation_id",
            ),
            (
                "review",
                "SELECT * FROM reviews WHERE change_request_id=? ORDER BY kind,provider_change_request_document_id",
            ),
            (
                "review_thread",
                "SELECT * FROM review_threads WHERE change_request_id=? ORDER BY provider_resource_id",
            ),
            (
                "review_comment",
                "SELECT * FROM review_comments WHERE change_request_id=? ORDER BY kind,provider_change_request_document_id",
            ),
            (
                "event",
                "SELECT * FROM change_request_events WHERE change_request_id=? ORDER BY change_request_event_id",
            ),
            (
                "code_observation",
                "SELECT * FROM code_observations WHERE change_request_id=? ORDER BY code_observation_id",
            ),
            (
                "code_listing",
                "SELECT l.*,p.state,p.page_count,p.terminal,p.context_proven FROM code_listings l LEFT JOIN code_listing_progress p ON p.code_listing_id=l.code_listing_id WHERE l.change_request_id=? ORDER BY l.code_listing_id",
            ),
            (
                "code_commit",
                "SELECT i.* FROM code_commits i JOIN code_listings l ON l.code_listing_id=i.code_listing_id WHERE l.change_request_id=? ORDER BY i.code_listing_id,i.fetch_occurrence_id,i.position",
            ),
            (
                "code_file_change",
                "SELECT i.* FROM code_file_changes i JOIN code_listings l ON l.code_listing_id=i.code_listing_id WHERE l.change_request_id=? ORDER BY i.code_listing_id,i.fetch_occurrence_id,i.position",
            ),
            (
                "code_acquisition",
                "SELECT a.* FROM code_acquisitions a JOIN code_observations o ON o.code_observation_id=a.code_observation_id WHERE o.change_request_id=? ORDER BY a.code_observation_id,a.role",
            ),
        )
        for kind, sql in queries:
            for row in self.s.execute(sql, (ident,)):
                self._check()
                item = row_fields(row)
                if "raw_path" in item:
                    item.update(path_fields(item.pop("raw_path")))
                yield {"record_kind": kind, **item}

    def _search(self, options):
        repo = options.get("repo")
        if repo:
            self._repo(options)
        literal, kind = options.get("literal"), options.get("kind")
        if (
            not isinstance(literal, str)
            or not literal
            or kind not in ("code", "commits", "pr")
        ):
            raise CatalogError(
                "INVALID_ARGUMENT",
                "Search needs nonempty --literal and --kind code, commits or pr",
            )
        if kind == "code":
            # Scan originals, not archived search_documents or rebuilt FTS.
            rows = self.s.execute(
                "SELECT DISTINCT r.repository_id,g.git_object_id,g.object_format,g.oid,g.type,g.size,g.verified,c.content_id content_id,c.raw_text,c.text_state FROM repository_object_sources r JOIN git_objects g ON g.git_object_id=r.git_object_id LEFT JOIN blob_content_map b ON b.git_object_id=g.git_object_id LEFT JOIN contents c ON c.content_id=b.content_id WHERE g.type='blob' AND (? IS NULL OR r.repository_id=?) ORDER BY r.repository_id,g.git_object_id",
                (repo, repo),
            )
            for row in rows:
                self._check()
                if row["raw_text"] is None:
                    self._add_missing(
                        "code",
                        "body_not_saved",
                        repository_id=row["repository_id"],
                        git_object_id=row["git_object_id"],
                        content_id=row["content_id"],
                        text_state=row["text_state"],
                    )
                elif literal in row["raw_text"]:
                    yield {
                        "repository_id": row["repository_id"],
                        **object_fields(row),
                        "content_id": row["content_id"],
                        "text": row["raw_text"],
                        "digests": self._digests(row["content_id"]),
                    }
        elif kind == "commits":
            for row in self.s.execute(
                "SELECT DISTINCT r.repository_id,g.*,c.raw_message FROM repository_object_sources r JOIN git_objects g ON g.git_object_id=r.git_object_id LEFT JOIN commits c ON c.git_object_id=g.git_object_id WHERE g.type='commit' AND (? IS NULL OR r.repository_id=?) ORDER BY r.repository_id,g.git_object_id",
                (repo, repo),
            ):
                self._check()
                if row["raw_message"] is None:
                    self._add_missing(
                        "commits",
                        "commit_structure_missing",
                        git_object_id=row["git_object_id"],
                    )
                    continue
                try:
                    text = row["raw_message"].decode("utf8", "strict")
                except UnicodeDecodeError:
                    self._add_missing(
                        "commits",
                        "message_non_utf8",
                        git_object_id=row["git_object_id"],
                    )
                    continue
                if literal in text:
                    yield {
                        "repository_id": row["repository_id"],
                        **object_fields(row),
                        "text": text,
                        "raw_message": row["raw_message"],
                    }
        else:
            for request in self.s.execute(
                "SELECT * FROM change_requests WHERE (? IS NULL OR repository_id=?) ORDER BY repository_id,change_request_id",
                (repo, repo),
            ):
                ident = request["change_request_id"]
                self._pr_coverage(ident)
                base = {
                    "repository_id": request["repository_id"],
                    "change_request_id": ident,
                    "provider_change_request_number": request[
                        "provider_change_request_number"
                    ],
                    "change_request_kind": request["change_request_kind"],
                    "repository_binding_id": request["repository_binding_id"],
                }
                for row in self.s.execute(
                    "SELECT * FROM change_request_observations WHERE change_request_id=? ORDER BY change_request_observation_id",
                    (ident,),
                ):
                    self._check()
                    payload = json.loads(row["payload"])
                    texts = [payload.get(key) for key in ("title", "body")]
                    for field, text in zip(("title", "body"), texts):
                        if isinstance(text, str) and literal in text:
                            yield {
                                **base,
                                "record_kind": "observation",
                                "change_request_observation_id": row[
                                    "change_request_observation_id"
                                ],
                                "observed_at_us": row["observed_at_us"],
                                "field": field,
                                "text": text,
                            }
                for row in self.s.execute(
                    "SELECT o.change_request_id,o.kind,o.provider_change_request_document_id,lower(hex(o.text_body_sha256)) text_body_sha256,b.body,o.document_observation_id,o.observed_at_us FROM document_observations o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.change_request_id=? ORDER BY o.kind,o.provider_change_request_document_id,o.document_observation_id",
                    (ident,),
                ):
                    self._check()
                    if literal in row["body"]:
                        yield {**base, "record_kind": "document", **dict(row)}
