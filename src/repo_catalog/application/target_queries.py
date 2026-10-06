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
        "object_id": row["id"],
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
        if not self.s.one("SELECT 1 FROM repositories WHERE id=?", (repo,)):
            raise CatalogError("NOT_FOUND", "Target repository not found")
        return repo

    def _rows(self, command, options):
        if command == "repos":
            yield from self._repositories(options)
        elif command in ("commit", "tree", "file"):
            repo = self._repo(options)
            obj = self._commit_object(repo, options.get("commit"))
            commit = self.s.one("SELECT * FROM commits WHERE object_id=?", (obj["id"],))
            if commit is None:
                self._add_missing(
                    "git", "commit_structure_missing", object_id=obj["id"]
                )
                yield object_fields(obj)
            elif command == "commit":
                yield self._commit_details(obj, commit)
            else:
                raw_path = self._path(options) if command == "file" else None
                found = False
                for entry in self._tree(commit["tree_id"]):
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
            "SELECT * FROM repositories WHERE (? IS NULL OR id=?) ORDER BY id",
            (repo, repo),
        ):
            self._check()
            yield {
                **row_fields(row),
                "bindings": [
                    row_fields(r)
                    for r in self.s.execute(
                        "SELECT * FROM repository_bindings WHERE repo_id=? ORDER BY id",
                        (row["id"],),
                    )
                ],
                "endpoints": [
                    row_fields(r)
                    for r in self.s.execute(
                        "SELECT * FROM repository_endpoints WHERE repo_id=? ORDER BY id",
                        (row["id"],),
                    )
                ],
                "name_assertions": [
                    dict(r)
                    for r in self.s.execute(
                        "SELECT * FROM repository_name_assertions WHERE repo_id=? ORDER BY name",
                        (row["id"],),
                    )
                ],
                "sources": [
                    dict(r)
                    for r in self.s.execute(
                        "SELECT * FROM source_repositories WHERE repo_id=? ORDER BY source_id",
                        (row["id"],),
                    )
                ],
            }

    def _commit_object(self, repo, value):
        oid = GitOid.parse(value or "")
        row = self.s.one(
            "SELECT g.* FROM git_objects g WHERE g.object_format=? AND g.oid=? AND g.type='commit' "
            "AND (EXISTS(SELECT 1 FROM repository_object_sources r WHERE r.repo_id=? AND r.object_id=g.id) "
            "OR EXISTS(SELECT 1 FROM acquisition_roots r WHERE r.repo_id=? AND r.object_format=g.object_format AND r.oid=g.oid))",
            (oid.algorithm, oid.value, repo, repo),
        )
        if not row:
            raise CatalogError(
                "NOT_FOUND",
                "Stored commit is not attributed to the selected repository",
            )
        return row

    def _commit_details(self, obj, commit):
        tree = self.s.one("SELECT * FROM git_objects WHERE id=?", (commit["tree_id"],))
        parents = [
            {"ordinal": r["parent_ordinal"], **object_fields(r)}
            for r in self.s.execute(
                "SELECT p.parent_ordinal,g.* FROM commit_parents p JOIN git_objects g ON g.id=p.parent_id WHERE p.commit_id=? ORDER BY p.parent_ordinal",
                (obj["id"],),
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
                self._add_missing("git", "tree_cycle", object_id=ident)
                continue
            rows = self.s.all(
                "SELECT * FROM tree_entries WHERE tree_id=? ORDER BY raw_name", (ident,)
            )
            if not rows:
                obj = self.s.one("SELECT size FROM git_objects WHERE id=?", (ident,))
                if obj and obj["size"]:
                    self._add_missing("git", "tree_structure_missing", object_id=ident)
            subtrees = []
            for row in rows:
                self._check()
                path = prefix + row["raw_name"]
                if row["mode"] == 16384:
                    subtrees.append((row["child_id"], path + b"/", ancestors | {ident}))
                    continue
                content = self.s.one(
                    "SELECT c.* FROM blob_content_map b JOIN contents c ON c.id=b.content_id WHERE b.object_id=?",
                    (row["child_id"],),
                )
                digests = self._digests(content["id"]) if content else []
                yield {
                    "raw_path": path,
                    "mode": format(row["mode"], "06o"),
                    "object_id": row["child_id"],
                    "oid": f"{row['child_format']}:{row['child_oid'].hex()}",
                    "content_id": content["id"] if content else None,
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
        number = options.get("number")
        if type(number) is not int or number <= 0:
            raise CatalogError("INVALID_ARGUMENT", "A positive --number is required")
        kind = options.get("request_kind", "pull_request")
        if kind not in ("pull_request", "merge_request"):
            raise CatalogError("INVALID_ARGUMENT", "Unknown request kind")
        rows = self.s.all(
            "SELECT * FROM change_requests WHERE repo_id=? AND number=? AND request_kind=? AND (? IS NULL OR binding_id=?) ORDER BY id",
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
            "SELECT l.id,p.state,p.page_count,p.terminal,p.context_proven FROM code_listings l LEFT JOIN code_listing_progress p ON p.listing_id=l.id WHERE l.change_request_id=? ORDER BY l.id",
            (ident,),
        ):
            if row["state"] != "complete":
                self._add_missing("pr", "code_listing_incomplete", **dict(row))
        for row in self.s.execute(
            "SELECT id,state FROM code_observations WHERE change_request_id=? AND state!='complete' ORDER BY id",
            (ident,),
        ):
            self._add_missing("pr", "code_observation_incomplete", **dict(row))
        for row in self.s.execute(
            "SELECT c.id,p.state,p.reason saved_reason,p.cursor FROM fetch_collections c LEFT JOIN collection_progress p ON p.collection_id=c.id WHERE c.change_request_id=? ORDER BY c.id",
            (ident,),
        ):
            if row["state"] != "complete":
                self._add_missing("pr", "collection_incomplete", **dict(row))
        for row in self.s.execute(
            "SELECT d.id FROM documents d WHERE d.change_request_id=? AND NOT EXISTS(SELECT 1 FROM document_versions v WHERE v.document_id=d.id) ORDER BY d.id",
            (ident,),
        ):
            self._add_missing("pr", "document_body_missing", document_id=row["id"])
        for row in self.s.execute(
            "SELECT s.id,c.effective_state FROM coverage_scopes s LEFT JOIN coverage_claims c ON c.scope_id=s.id WHERE s.change_request_id=? ORDER BY s.id,c.id",
            (ident,),
        ):
            if row["effective_state"] not in ("complete", "not_applicable"):
                self._add_missing("pr", "saved_scope_incomplete", **dict(row))

    def _pr(self, options):
        request = self._pr_identity(options)
        ident = request["id"]
        self._pr_coverage(ident)
        yield {"record_kind": "change_request", **row_fields(request)}
        queries = (
            (
                "observation",
                "SELECT * FROM change_request_observations WHERE change_request_id=? ORDER BY id",
            ),
            (
                "document",
                "SELECT * FROM documents WHERE change_request_id=? ORDER BY id",
            ),
            (
                "document_version",
                "SELECT v.*,b.body,b.byte_length,b.sha256 FROM document_versions v JOIN documents d ON d.id=v.document_id JOIN text_bodies b ON b.id=v.body_id WHERE d.change_request_id=? ORDER BY v.id",
            ),
            (
                "document_observation",
                "SELECT o.* FROM document_observations o JOIN documents d ON d.id=o.document_id WHERE d.change_request_id=? ORDER BY o.id",
            ),
            ("review", "SELECT * FROM reviews WHERE change_request_id=? ORDER BY id"),
            (
                "review_thread",
                "SELECT * FROM review_threads WHERE change_request_id=? ORDER BY id",
            ),
            (
                "review_comment",
                "SELECT * FROM review_comments WHERE change_request_id=? ORDER BY document_id",
            ),
            (
                "event",
                "SELECT * FROM change_request_events WHERE change_request_id=? ORDER BY id",
            ),
            (
                "code_observation",
                "SELECT * FROM code_observations WHERE change_request_id=? ORDER BY id",
            ),
            (
                "code_listing",
                "SELECT l.*,p.state,p.page_count,p.terminal,p.context_proven FROM code_listings l LEFT JOIN code_listing_progress p ON p.listing_id=l.id WHERE l.change_request_id=? ORDER BY l.id",
            ),
            (
                "code_commit",
                "SELECT i.* FROM code_commits i JOIN code_listings l ON l.id=i.listing_id WHERE l.change_request_id=? ORDER BY i.listing_id,i.occurrence_id,i.position",
            ),
            (
                "code_file_change",
                "SELECT i.* FROM code_file_changes i JOIN code_listings l ON l.id=i.listing_id WHERE l.change_request_id=? ORDER BY i.listing_id,i.occurrence_id,i.position",
            ),
            (
                "code_acquisition",
                "SELECT a.* FROM code_acquisitions a JOIN code_observations o ON o.id=a.code_observation_id WHERE o.change_request_id=? ORDER BY a.code_observation_id,a.role",
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
                "SELECT DISTINCT r.repo_id,g.id,g.object_format,g.oid,g.type,g.size,g.verified,c.id content_id,c.raw_text,c.text_state "
                "FROM repository_object_sources r JOIN git_objects g ON g.id=r.object_id "
                "LEFT JOIN blob_content_map b ON b.object_id=g.id LEFT JOIN contents c ON c.id=b.content_id "
                "WHERE g.type='blob' AND (? IS NULL OR r.repo_id=?) ORDER BY r.repo_id,g.id",
                (repo, repo),
            )
            for row in rows:
                self._check()
                if row["raw_text"] is None:
                    self._add_missing(
                        "code",
                        "body_not_saved",
                        repo_id=row["repo_id"],
                        object_id=row["id"],
                        content_id=row["content_id"],
                        text_state=row["text_state"],
                    )
                elif literal in row["raw_text"]:
                    yield {
                        "repo_id": row["repo_id"],
                        **object_fields(row),
                        "content_id": row["content_id"],
                        "text": row["raw_text"],
                        "digests": self._digests(row["content_id"]),
                    }
        elif kind == "commits":
            for row in self.s.execute(
                "SELECT DISTINCT r.repo_id,g.*,c.raw_message FROM repository_object_sources r JOIN git_objects g ON g.id=r.object_id LEFT JOIN commits c ON c.object_id=g.id WHERE g.type='commit' AND (? IS NULL OR r.repo_id=?) ORDER BY r.repo_id,g.id",
                (repo, repo),
            ):
                self._check()
                if row["raw_message"] is None:
                    self._add_missing(
                        "commits", "commit_structure_missing", object_id=row["id"]
                    )
                    continue
                try:
                    text = row["raw_message"].decode("utf8", "strict")
                except UnicodeDecodeError:
                    self._add_missing(
                        "commits", "message_non_utf8", object_id=row["id"]
                    )
                    continue
                if literal in text:
                    yield {
                        "repo_id": row["repo_id"],
                        **object_fields(row),
                        "text": text,
                        "raw_message": row["raw_message"],
                    }
        else:
            for request in self.s.execute(
                "SELECT * FROM change_requests WHERE (? IS NULL OR repo_id=?) ORDER BY repo_id,id",
                (repo, repo),
            ):
                ident = request["id"]
                self._pr_coverage(ident)
                base = {
                    "repo_id": request["repo_id"],
                    "change_request_id": ident,
                    "number": request["number"],
                    "binding_id": request["binding_id"],
                }
                for row in self.s.execute(
                    "SELECT * FROM change_request_observations WHERE change_request_id=? ORDER BY id",
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
                                "observation_id": row["id"],
                                "observed_at": row["observed_at"],
                                "field": field,
                                "text": text,
                            }
                for row in self.s.execute(
                    "SELECT d.id document_id,d.kind,v.id version_id,b.body,o.id observation_id,o.observed_at FROM documents d JOIN document_versions v ON v.document_id=d.id JOIN text_bodies b ON b.id=v.body_id LEFT JOIN document_observations o ON o.version_id=v.id WHERE d.change_request_id=? ORDER BY d.id,v.id,o.id",
                    (ident,),
                ):
                    self._check()
                    if row["observation_id"] is None:
                        self._add_missing(
                            "pr",
                            "document_observation_missing",
                            document_id=row["document_id"],
                            version_id=row["version_id"],
                        )
                    if literal in row["body"]:
                        yield {**base, "record_kind": "document", **dict(row)}
