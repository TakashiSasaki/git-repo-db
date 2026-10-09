"""Explicit catalog3 diagnostics; ordinary runtime queries use QueryService."""

from __future__ import annotations

import base64
import binascii
import json
import math
import sqlite3
import time

from repo_catalog.adapters.sqlite.target import TargetReader
from repo_catalog.application.git_query_context import object_context
from repo_catalog.application.pr_queries import code_role_gaps
from repo_catalog.domain.document import verify_text_body
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
    for key in (
        "metadata",
        "payload",
        "details",
        "request",
        "settings",
        "scope",
        "acquisition_scope_json",
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
        if not self.s.one(
            "SELECT 1 FROM repositories WHERE repository_uuidv4=?", (repo,)
        ):
            raise CatalogError("NOT_FOUND", "Target repository not found")
        return repo

    def _rows(self, command, options):
        if command == "repos":
            yield from self._repositories(options)
        elif command in ("commit", "tree", "file"):
            repo = self._repo(options)
            obj = self._commit_object(repo, options.get("commit"))
            context = object_context(
                self.s,
                self._git_context(repo, options),
                obj["git_object_id"],
                obj["type"],
            )
            commit = self.s.one(
                f"SELECT * FROM {self._git_relation('commits', context)} WHERE repository_uuidv4=? AND parsed_result_uuidv4=? AND git_object_id=?",
                (repo, context["parsed_result_uuidv4"], obj["git_object_id"]),
            )
            if commit is None:
                self._add_missing(
                    "git",
                    "git_interpretation_selection_unresolved"
                    if context.get("selection_unresolved")
                    else "commit_structure_missing",
                    git_object_id=obj["git_object_id"],
                )
                yield object_fields(obj)
            elif command == "commit":
                yield self._commit_details(obj, commit, context)
            else:
                raw_path = self._path(options) if command == "file" else None
                found = False
                for entry in self._tree(commit["tree_git_object_id"], context):
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
            "SELECT * FROM repositories WHERE (? IS NULL OR repository_uuidv4=?) ORDER BY repository_uuidv4",
            (repo, repo),
        ):
            self._check()
            yield {
                **row_fields(row),
                "bindings": [
                    row_fields(r)
                    for r in self.s.execute(
                        "SELECT * FROM repository_bindings WHERE repository_uuidv4=? ORDER BY repository_binding_id",
                        (row["repository_uuidv4"],),
                    )
                ],
                "endpoints": [
                    row_fields(r)
                    for r in self.s.execute(
                        "SELECT * FROM repository_endpoints WHERE repository_uuidv4=? ORDER BY repository_endpoint_id",
                        (row["repository_uuidv4"],),
                    )
                ],
                "observed_names": [
                    r["name"]
                    for r in self.s.execute(
                        "SELECT name FROM repository_observed_names WHERE repository_uuidv4=? ORDER BY name",
                        (row["repository_uuidv4"],),
                    )
                ],
                "sources": [
                    dict(r)
                    for r in self.s.execute(
                        "SELECT * FROM source_repositories WHERE repository_uuidv4=? ORDER BY source_id",
                        (row["repository_uuidv4"],),
                    )
                ],
            }

    def _commit_object(self, repo, value):
        oid = GitOid.parse(value or "")
        row = self.s.one(
            "SELECT g.* FROM git_objects g WHERE g.object_format=? AND g.oid=? AND g.type='commit' AND (EXISTS(SELECT 1 FROM repository_object_sources r WHERE r.repository_uuidv4=? AND r.git_object_id=g.git_object_id) OR EXISTS(SELECT 1 FROM acquisition_roots r WHERE r.repository_uuidv4=? AND r.object_format=g.object_format AND r.oid=g.oid))",
            (oid.algorithm, oid.value, repo, repo),
        )
        if not row:
            raise CatalogError(
                "NOT_FOUND",
                "Stored commit is not attributed to the selected repository",
            )
        return row

    def _git_context(self, repo, options):
        if options.get("snapshot"):
            selected = self.s.one(
                "SELECT s.parsed_result_uuidv4 FROM snapshots s JOIN usable_parsed_results r USING(parsed_result_uuidv4) JOIN effective_repository_parser_profiles e ON e.repository_uuidv4=s.repository_uuidv4 AND e.fact_kind='git' AND e.parser_profile_uuidv4=r.parser_profile_uuidv4 WHERE s.repository_uuidv4=? AND s.snapshot_id=? AND s.published=1",
                (repo, options["snapshot"]),
            )
            if not selected:
                raise CatalogError("NOT_FOUND", "Published eligible snapshot not found")
        else:
            selected = self.s.one(
                "SELECT parsed_result_uuidv4 FROM active_fact_selections WHERE repository_uuidv4=? AND fact_kind='git' AND change_request_id IS NULL AND git_acquisition_id IS NULL",
                (repo,),
            )
        return {
            "repository_uuidv4": repo,
            "parsed_result_uuidv4": selected[0] if selected else None,
            "historical": bool(options.get("snapshot")),
        }

    @staticmethod
    def _git_relation(table, context):
        return ("eligible_git_" if context["historical"] else "current_git_") + table

    def _commit_details(self, obj, commit, context):
        tree = self.s.one(
            "SELECT * FROM git_objects WHERE git_object_id=?",
            (commit["tree_git_object_id"],),
        )
        parents = [
            {"ordinal": r["parent_ordinal"], **object_fields(r)}
            for r in self.s.execute(
                f"SELECT p.parent_ordinal,g.* FROM {self._git_relation('commit_parents', context)} p JOIN git_objects g ON g.git_object_id=p.parent_git_object_id WHERE p.repository_uuidv4=? AND p.parsed_result_uuidv4=? AND p.commit_git_object_id=? ORDER BY p.parent_ordinal",
                (
                    context["repository_uuidv4"],
                    context["parsed_result_uuidv4"],
                    obj["git_object_id"],
                ),
            )
        ]
        return {
            **object_fields(obj),
            "tree": object_fields(tree),
            "parents": parents,
            "raw_headers": commit["raw_headers"],
            "raw_message": commit["raw_message"],
            "message_display": commit["message_text"],
            "parsed_result_uuidv4": commit["parsed_result_uuidv4"],
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

    def _tree(self, tree, context):
        # Explicit frames preserve arbitrary raw names and reject cycles without
        # relying on textual SQLite concatenation or running Git.
        frames = [(tree, b"", "", frozenset())]
        while frames:
            self._check()
            ident, prefix, display_prefix, ancestors = frames.pop()
            if ident in ancestors:
                self._add_missing("git", "tree_cycle", git_object_id=ident)
                continue
            rows = self.s.all(
                f"SELECT * FROM {self._git_relation('tree_entries', context)} WHERE repository_uuidv4=? AND parsed_result_uuidv4=? AND tree_git_object_id=? ORDER BY raw_name",
                (context["repository_uuidv4"], context["parsed_result_uuidv4"], ident),
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
                display_path = display_prefix + row["decoded_name"]
                if row["mode"] == 16384:
                    subtrees.append(
                        (
                            row["child_git_object_id"],
                            path + b"/",
                            display_path + "/",
                            ancestors | {ident},
                        )
                    )
                    continue
                content = self.s.one(
                    f"SELECT t.*,c.byte_length FROM {self._git_relation('text_facts', context)} t JOIN contents c USING(content_id) WHERE t.repository_uuidv4=? AND t.parsed_result_uuidv4=? AND t.git_object_id=?",
                    (
                        context["repository_uuidv4"],
                        context["parsed_result_uuidv4"],
                        row["child_git_object_id"],
                    ),
                )
                digests = self._digests(content["content_id"]) if content else []
                yield {
                    "raw_path": path,
                    "path_display": "".join(
                        character
                        if character.isprintable()
                        else f"\\x{ord(character):02x}"
                        for character in display_path
                    ),
                    "parsed_result_uuidv4": context["parsed_result_uuidv4"],
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
            "SELECT * FROM change_requests WHERE repository_uuidv4=? AND provider_change_request_number=? AND change_request_kind=? AND (? IS NULL OR repository_binding_id=?) ORDER BY change_request_id",
            (repo, number, kind, options.get("binding"), options.get("binding")),
        )
        if not rows:
            raise CatalogError("NOT_FOUND", "Change request not found")
        if len(rows) != 1:
            raise CatalogError(
                "INVALID_ARGUMENT", "Number is ambiguous; select an explicit --binding"
            )
        return rows[0]

    def _pr_coverage(self, ident, options=None):
        if not self.s.one(
            "SELECT 1 FROM current_change_request_observations WHERE change_request_id=? LIMIT 1",
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
            f"SELECT c.*,p.repository_uuidv4 FROM {self._fact_relation('code_observations', options or {})} c JOIN change_requests p USING(change_request_id) WHERE c.change_request_id=? ORDER BY c.code_observation_id",
            (ident,),
        ):
            self._check()
            if row["state"] != "complete":
                self._add_missing(
                    "pr",
                    "code_observation_incomplete",
                    code_observation_id=row["code_observation_id"],
                    state=row["state"],
                )
            for gap in code_role_gaps(self.s, row, row, check=self._check):
                self._add_missing("pr", **gap)
        for row in self.s.execute(
            "SELECT c.fetch_collection_id,p.state,p.reason saved_reason,p.cursor FROM fetch_collections c LEFT JOIN collection_progress p ON p.fetch_collection_id=c.fetch_collection_id WHERE c.change_request_id=? ORDER BY c.fetch_collection_id",
            (ident,),
        ):
            if row["state"] != "complete":
                self._add_missing("pr", "collection_incomplete", **dict(row))
        for row in self.s.execute(
            "SELECT d.change_request_id,d.kind,d.provider_change_request_document_id FROM documents d WHERE d.change_request_id=? AND NOT EXISTS(SELECT 1 FROM current_document_observations o WHERE o.change_request_id=d.change_request_id AND o.kind=d.kind AND o.provider_change_request_document_id=d.provider_change_request_document_id) ORDER BY d.kind,d.provider_change_request_document_id",
            (ident,),
        ):
            self._add_missing("pr", "document_body_missing", **dict(row))
        for row in self.s.execute(
            "SELECT r.change_request_id,r.kind document_kind,r.provider_change_request_document_id "
            "FROM review_resources r WHERE r.change_request_id=? AND r.deleted=0 "
            "AND NOT EXISTS(SELECT 1 FROM eligible_review_resources e "
            "WHERE e.change_request_id=r.change_request_id AND e.kind=r.kind "
            "AND e.provider_change_request_document_id=r.provider_change_request_document_id)",
            (ident,),
        ):
            self._add_missing("pr", "current_resource_unresolved", **dict(row))
        for row in self.s.execute(
            "SELECT coverage_scope_id,coverage_state FROM current_coverage WHERE change_request_id=? ORDER BY coverage_scope_id",
            (ident,),
        ):
            if row["coverage_state"] not in ("complete", "not_applicable"):
                self._add_missing("pr", "saved_scope_incomplete", **dict(row))

    @staticmethod
    def _fact_relation(table, options):
        """Explicit history retains every usable profile without changing selection."""
        if options.get("observations", "current") == "all":
            return (
                f"(SELECT fact.* FROM {table} fact JOIN usable_parsed_results result "
                "USING(parsed_result_uuidv4))"
            )
        return "current_" + table

    def _pr(self, options):
        request = self._pr_identity(options)
        ident = request["change_request_id"]
        self._pr_coverage(ident, options)
        yield {"record_kind": "change_request", **row_fields(request)}

        def relation(table):
            return self._fact_relation(table, options)

        queries = (
            (
                "observation",
                f"SELECT * FROM {relation('change_request_observations')} WHERE change_request_id=? ORDER BY change_request_observation_id",
            ),
            (
                "document",
                "SELECT * FROM documents WHERE change_request_id=? ORDER BY kind,provider_change_request_document_id",
            ),
            (
                "document_observation",
                f"SELECT o.*,b.body,b.byte_length FROM {relation('document_observations')} o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.change_request_id=? ORDER BY o.document_observation_id",
            ),
            (
                "review",
                "SELECT r.*,b.body,b.byte_length body_byte_length FROM eligible_review_resources r LEFT JOIN text_bodies b "
                "ON b.sha256=r.text_body_sha256 WHERE r.change_request_id=? "
                "AND r.kind='review' AND r.deleted=0 ORDER BY r.provider_change_request_document_id",
            ),
            (
                "review_thread",
                f"SELECT * FROM {relation('review_thread_observations')} WHERE change_request_id=? ORDER BY provider_resource_id",
            ),
            (
                "review_comment",
                "SELECT r.*,b.body,b.byte_length body_byte_length FROM eligible_review_resources r LEFT JOIN text_bodies b "
                "ON b.sha256=r.text_body_sha256 WHERE r.change_request_id=? "
                "AND r.kind='review-comment' AND r.deleted=0 ORDER BY r.provider_change_request_document_id",
            ),
            (
                "event",
                f"SELECT * FROM {relation('change_request_events')} WHERE change_request_id=? ORDER BY change_request_event_id",
            ),
            (
                "code_observation",
                f"SELECT * FROM {relation('code_observations')} WHERE change_request_id=? ORDER BY code_observation_id",
            ),
            (
                "code_listing",
                "SELECT l.*,p.state,p.page_count,p.terminal,p.context_proven FROM code_listings l LEFT JOIN code_listing_progress p ON p.code_listing_id=l.code_listing_id WHERE l.change_request_id=? ORDER BY l.code_listing_id",
            ),
            (
                "code_commit",
                f"SELECT i.* FROM {relation('code_commits')} i JOIN code_listings l ON l.code_listing_id=i.code_listing_id WHERE l.change_request_id=? ORDER BY i.code_listing_id,i.fetch_occurrence_id,i.position",
            ),
            (
                "code_file_change",
                f"SELECT i.* FROM {relation('code_file_changes')} i JOIN code_listings l ON l.code_listing_id=i.code_listing_id WHERE l.change_request_id=? ORDER BY i.code_listing_id,i.fetch_occurrence_id,i.position",
            ),
            (
                "code_acquisition",
                f"SELECT a.* FROM code_acquisitions a JOIN {relation('code_observations')} o ON o.code_observation_id=a.code_observation_id WHERE o.change_request_id=? ORDER BY a.code_observation_id,a.role",
            ),
        )
        for kind, sql in queries:
            for row in self.s.execute(sql, (ident,)):
                self._check()
                item = row_fields(row)
                if isinstance(item.get("raw_path"), bytes):
                    item.update(path_fields(item.pop("raw_path")))
                if kind in ("review", "review_comment"):
                    verify_text_body(
                        row["body"], row["text_body_sha256"], row["body_byte_length"]
                    )
                    item["resource_lifecycle"] = "current"
                yield {"record_kind": kind, **item}

    def _search(self, options):
        repo = options.get("repo")
        if repo:
            self._repo(options)
        literal, kind = options.get("literal"), options.get("kind")
        if (
            not isinstance(literal, str)
            or not literal
            or kind not in ("code", "commits", "pr", "issue")
        ):
            raise CatalogError(
                "INVALID_ARGUMENT",
                "Search needs nonempty --literal and --kind code, commits, pr or issue",
            )
        if kind in ("code", "commits"):
            object_type = "blob" if kind == "code" else "commit"
            table = "text_facts" if kind == "code" else "commits"
            contexts = {}
            for row in self.s.execute(
                "SELECT DISTINCT r.repository_uuidv4,g.*,b.content_id FROM repository_object_sources r JOIN git_objects g USING(git_object_id) LEFT JOIN blob_content_map b USING(git_object_id) WHERE g.type=? AND (? IS NULL OR r.repository_uuidv4=?) ORDER BY r.repository_uuidv4,g.git_object_id",
                (object_type, repo, repo),
            ):
                self._check()
                repository = row["repository_uuidv4"]
                if repository not in contexts:
                    contexts[repository] = self._git_context(repository, {})
                context = object_context(
                    self.s, contexts[repository], row["git_object_id"], object_type
                )
                fact = self.s.one(
                    f"SELECT * FROM {self._git_relation(table, context)} WHERE repository_uuidv4=? AND parsed_result_uuidv4=? AND git_object_id=?",
                    (repository, context["parsed_result_uuidv4"], row["git_object_id"]),
                )
                if fact is None:
                    self._add_missing(
                        kind,
                        "git_interpretation_selection_unresolved"
                        if context.get("selection_unresolved")
                        else "body_not_saved"
                        if kind == "code"
                        else "commit_structure_missing",
                        repository_uuidv4=repository,
                        git_object_id=row["git_object_id"],
                    )
                    continue
                text = fact["raw_text"] if kind == "code" else fact["message_text"]
                if text is None:
                    self._add_missing(
                        kind,
                        "body_not_saved",
                        repository_uuidv4=repository,
                        git_object_id=row["git_object_id"],
                        content_id=row["content_id"],
                        text_state=fact["text_state"],
                    )
                    continue
                if literal in text:
                    item = {
                        "repository_uuidv4": repository,
                        **object_fields(row),
                        "text": text,
                        "parsed_result_uuidv4": fact["parsed_result_uuidv4"],
                    }
                    if kind == "code":
                        item.update(
                            content_id=fact["content_id"],
                            digests=self._digests(fact["content_id"]),
                        )
                    else:
                        item["raw_message"] = fact["raw_message"]
                    yield item
        elif kind == "issue":
            for row in self.s.execute(
                "SELECT r.*,b.body,b.byte_length body_byte_length FROM eligible_issue_resources r LEFT JOIN text_bodies b "
                "ON b.sha256=r.text_body_sha256 WHERE (? IS NULL OR r.repository_uuidv4=?) "
                "AND r.deleted=0 ORDER BY r.repository_uuidv4,r.kind,r.provider_resource_id",
                (repo, repo),
            ):
                self._check()
                verify_text_body(
                    row["body"], row["text_body_sha256"], row["body_byte_length"]
                )
                for field in ("title", "body"):
                    text = row[field]
                    if isinstance(text, str) and literal in text:
                        yield {
                            "record_kind": "current_resource",
                            **row_fields(row),
                            "field": field,
                            "text": text,
                        }
        else:
            for request in self.s.execute(
                "SELECT * FROM change_requests WHERE (? IS NULL OR repository_uuidv4=?) ORDER BY repository_uuidv4,change_request_id",
                (repo, repo),
            ):
                ident = request["change_request_id"]
                self._pr_coverage(ident, options)
                base = {
                    "repository_uuidv4": request["repository_uuidv4"],
                    "change_request_id": ident,
                    "provider_change_request_number": request[
                        "provider_change_request_number"
                    ],
                    "change_request_kind": request["change_request_kind"],
                    "repository_binding_id": request["repository_binding_id"],
                }
                for row in self.s.execute(
                    f"SELECT * FROM {self._fact_relation('change_request_observations', options)} WHERE change_request_id=? ORDER BY change_request_observation_id",
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
                    f"SELECT o.change_request_id,o.kind,o.provider_change_request_document_id,lower(hex(o.text_body_sha256)) text_body_sha256,b.body,o.document_observation_id,o.observed_at_us,o.parsed_result_uuidv4 FROM {self._fact_relation('document_observations', options)} o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.change_request_id=? ORDER BY o.kind,o.provider_change_request_document_id,o.document_observation_id",
                    (ident,),
                ):
                    self._check()
                    if literal in row["body"]:
                        yield {**base, "record_kind": "document", **dict(row)}
                for row in self.s.execute(
                    "SELECT r.*,b.body,b.byte_length body_byte_length FROM eligible_review_resources r LEFT JOIN text_bodies b "
                    "ON b.sha256=r.text_body_sha256 WHERE r.change_request_id=? "
                    "AND r.deleted=0 ORDER BY r.kind,r.provider_change_request_document_id",
                    (ident,),
                ):
                    self._check()
                    verify_text_body(
                        row["body"], row["text_body_sha256"], row["body_byte_length"]
                    )
                    if isinstance(row["body"], str) and literal in row["body"]:
                        yield {
                            **base,
                            "record_kind": "current_resource",
                            **row_fields(row),
                        }
