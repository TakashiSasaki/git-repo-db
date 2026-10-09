"""Explicit offline reanalysis of immutable saved GitHub acquisitions."""

from __future__ import annotations

import json
import uuid

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.github.persistence import canonical
from repo_catalog.domain.models import CancellationToken, CatalogError


class ParsingService:
    def __init__(self, store):
        self.s = store

    def reparse(self, fetch_occurrence_uuidv4, *, select=False, profile_uuid=None):
        """Create a new parsing execution without manufacturing a remote fetch.

        ``select`` is an explicit local decision to supersede the currently
        resolved fact heads. It never changes the selected parser profile.
        """
        if self.s.one(
            "SELECT 1 FROM git_acquisitions WHERE git_acquisition_id=?",
            (fetch_occurrence_uuidv4,),
        ):
            from repo_catalog.adapters.git.parsing import reparse_git

            return reparse_git(
                self.s,
                fetch_occurrence_uuidv4,
                select=select,
                profile_uuid=profile_uuid,
            )
        if profile_uuid is not None:
            raise CatalogError(
                "PARSER_UNSUPPORTED_PROFILE",
                "GitHub reparse uses the installed profile",
            )
        row = self.s.one(
            "SELECT o.*,f.kind,f.change_request_id,f.source_id,f.resume_scope_id "
            "FROM fetch_occurrences o JOIN fetch_collections f "
            "ON f.fetch_collection_id=o.fetch_collection_id "
            "WHERE o.fetch_occurrence_uuidv4=?",
            (fetch_occurrence_uuidv4,),
        )
        if row is None:
            raise CatalogError("NOT_FOUND", "Unknown acquisition UUID")
        kind = row["kind"]
        supported = {
            "pr-list",
            "pr-detail",
            "pr-code-check",
            "issue-comment",
            "issue-comment-incremental",
            "timeline",
            "threads",
            "thread-comments",
            "pr-commits",
            "pr-files",
        }
        if kind not in supported:
            raise CatalogError(
                "PARSER_UNSUPPORTED_INPUT",
                "No installed parser for saved input",
                {"kind": kind},
            )
        request = json.loads(row["request"])
        if request.get("operational_only"):
            raise CatalogError(
                "PARSER_UNSUPPORTED_INPUT",
                "Operational response is not a resource input",
            )
        from repo_catalog.adapters.sqlite.cas_integrity import is_quarantined

        if is_quarantined(self.s.connection, row["payload_sha256"]):
            raise CatalogError(
                "PAYLOAD_CORRUPTION", "Quarantined input cannot be parsed"
            )
        raw = self.s.one(
            "SELECT body FROM stored_bytes WHERE sha256=?", (row["payload_sha256"],)
        )[0]
        try:
            values = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise CatalogError("API_SCHEMA", "Saved payload is not JSON") from error
        collection = dict(row)
        repo = dict(
            self.s.one(
                "SELECT * FROM repositories WHERE repository_uuidv4=?",
                (row["repository_uuidv4"],),
            )
        )
        repo["source_id"] = row["source_id"]
        collector = GitHubCollector(
            self.s, CancellationToken(), transport=_OfflineTransport()
        )
        collector.facts.select_results = select
        collector.facts.replaying = True
        occurrence = row["fetch_occurrence_id"]
        timestamp = row["observed_at_us"]
        position_base = row["ordinal"] * 10000
        with self.s.transaction():
            result = collector.facts.result(occurrence)
            if kind in ("pr-detail", "pr-code-check", "pr-list"):
                entries = values if kind == "pr-list" else [values]
                if not isinstance(entries, list):
                    raise CatalogError("API_SCHEMA", "Expected PR list")
                for index, value in enumerate(entries):
                    collector.ensure_pr(
                        repo,
                        value,
                        collection,
                        occurrence,
                        position_base + index,
                        timestamp,
                    )
            elif kind in ("threads", "thread-comments"):
                if kind == "threads":
                    parent = collector.graphql_object(
                        values, "data", "repository", "pullRequest"
                    )
                    nodes, _, _ = collector.graphql_connection(
                        parent.get("reviewThreads")
                    )
                    pr = {"change_request_id": row["change_request_id"]}
                    for index, thread in enumerate(nodes):
                        thread_id = collector._thread(
                            repo, pr, thread, timestamp, occurrence
                        )
                        collector._thread_documents(
                            repo,
                            pr,
                            thread_id,
                            thread.get("comments"),
                            collection,
                            occurrence,
                            index * 10000,
                            timestamp,
                            base_revision=None,
                            refresh_root=True,
                        )
                else:
                    node = collector.graphql_object(values, "data", "node")
                    context = json.loads(
                        self.s.one(
                            "SELECT request_context FROM resume_scopes WHERE resume_scope_id=?",
                            (row["resume_scope_id"],),
                        )[0]
                    )
                    thread_id = context.get(
                        "review_thread_provider_resource_id"
                    ) or request.get("variables", {}).get("thread")
                    if not thread_id:
                        raise CatalogError(
                            "API_SCHEMA", "Saved thread context is missing"
                        )
                    collector._thread_documents(
                        repo,
                        {"change_request_id": row["change_request_id"]},
                        thread_id,
                        node.get("comments"),
                        collection,
                        occurrence,
                        position_base,
                        timestamp,
                        base_revision=None,
                    )
            else:
                if not isinstance(values, list):
                    raise CatalogError("API_SCHEMA", "Expected collection list")
                for index, value in enumerate(values):
                    collector.rest_item(value, kind)
                    position = position_base + index
                    if kind == "timeline":
                        self.s.execute(
                            "INSERT INTO change_request_events(change_request_event_uuidv4,repository_uuidv4,parsed_result_uuidv4,change_request_id,origin_key,ordinal,provider_event_id,payload,observed_at_us,origin_fetch_occurrence_uuidv4) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (
                                str(uuid.uuid4()),
                                row["repository_uuidv4"],
                                result,
                                row["change_request_id"],
                                collector.facts.origin(
                                    collection, occurrence, position
                                ),
                                position,
                                str(value["id"])
                                if value.get("id") is not None
                                else None,
                                canonical(value),
                                timestamp,
                                row["fetch_occurrence_uuidv4"],
                            ),
                        )
                    elif kind in ("pr-commits", "pr-files"):
                        self._code_item(row, result, value, position)
                    else:
                        pr_id = row["change_request_id"]
                        document_kind = kind.removesuffix("-incremental")
                        if pr_id is None:
                            parent = value.get("issue_url") or value.get(
                                "pull_request_url"
                            )
                            try:
                                number = int(parent.rstrip("/").rsplit("/", 1)[1])
                            except (AttributeError, ValueError, IndexError) as error:
                                raise CatalogError(
                                    "API_SCHEMA", "Comment parent is absent"
                                ) from error
                            parent_row = self.s.one(
                                "SELECT change_request_id FROM change_requests WHERE repository_uuidv4=? AND provider_change_request_number=?",
                                (row["repository_uuidv4"], number),
                            )
                            if parent_row is None:
                                raise CatalogError(
                                    "PARSER_INPUT_MISSING",
                                    "Comment parent has not been admitted",
                                )
                            pr_id = parent_row[0]
                        collector.facts.document(
                            pr_id,
                            document_kind,
                            collector.document_provider_id(value),
                            value.get("body") or "",
                            value,
                            collection,
                            occurrence,
                            position,
                            timestamp,
                        )
            collector.facts.choose_page(collection, occurrence)
            collector.facts.publish()
        return {
            "parsed_result_uuidv4": result,
            "fetch_occurrence_uuidv4": fetch_occurrence_uuidv4,
            "selected": select and result not in collector.facts.unselected_results,
            "selection_requested": select,
        }

    def _code_item(self, row, result, value, position):
        listing = self.s.one(
            "SELECT code_listing_id,object_format FROM code_listings WHERE fetch_collection_id=?",
            (row["fetch_collection_id"],),
        )
        if listing is None:
            raise CatalogError(
                "PARSER_INPUT_MISSING", "Code listing context is missing"
            )
        if row["kind"] == "pr-commits":
            from repo_catalog.domain.models import GitOid

            oid = GitOid.parse(listing["object_format"] + ":" + value["sha"]).value
            self.s.execute(
                "INSERT INTO code_commits(repository_uuidv4,parsed_result_uuidv4,code_listing_id,fetch_occurrence_id,position,object_format,oid,payload) VALUES(?,?,?,?,?,?,?,?)",
                (
                    row["repository_uuidv4"],
                    result,
                    listing[0],
                    row["fetch_occurrence_id"],
                    position,
                    listing["object_format"],
                    oid,
                    canonical(value),
                ),
            )
        else:
            self.s.execute(
                "INSERT INTO code_file_changes(repository_uuidv4,parsed_result_uuidv4,code_listing_id,fetch_occurrence_id,position,raw_path,payload) VALUES(?,?,?,?,?,?,?)",
                (
                    row["repository_uuidv4"],
                    result,
                    listing[0],
                    row["fetch_occurrence_id"],
                    position,
                    value["filename"].encode("utf-8"),
                    canonical(value),
                ),
            )


class _OfflineTransport:
    def request(self, *_args, **_kwargs):
        raise AssertionError("Offline reanalysis must not make HTTP requests")
