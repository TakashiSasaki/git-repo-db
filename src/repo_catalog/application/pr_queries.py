"""Offline change-request queries over catalog3 facts and observations."""

from __future__ import annotations

import base64
import binascii
import json

from repo_catalog.domain.document import DocumentKey
from repo_catalog.domain.models import CatalogError, GitOid


def pr_state(payload):
    merged = payload.get("merged")
    if merged is None and "merged_at" in payload:
        merged = payload["merged_at"] is not None
    if merged:
        return "merged"
    if payload.get("state") == "open":
        return "open"
    return "closed" if merged is False else "unknown"


def _coverage(query, pr, documents_only):
    s = query.s
    if pr["current_change_request_observation_id"] is None:
        query.coverage.add(
            "pr",
            "current_selection_unresolved",
            change_request_id=pr["change_request_id"],
        )
    if pr["change_request_observation_id"] is None:
        query.coverage.add(
            "pr",
            "change_request_observation_missing",
            change_request_id=pr["change_request_id"],
        )
    rows = s.all(
        "SELECT c.kind,p.state,c.fetch_collection_id FROM fetch_collections c LEFT JOIN collection_progress p ON p.fetch_collection_id=c.fetch_collection_id WHERE c.change_request_id=? AND NOT EXISTS(SELECT 1 FROM fetch_collections newer WHERE newer.change_request_id=c.change_request_id AND newer.kind=c.kind AND ((newer.observed_at_us IS NOT NULL AND (c.observed_at_us IS NULL OR newer.observed_at_us>c.observed_at_us)) OR (newer.observed_at_us IS c.observed_at_us AND newer.rowid>c.rowid))) ORDER BY c.kind",
        (pr["change_request_id"],),
    )
    for row in rows:
        if documents_only and row["kind"] in (
            "commits",
            "files",
            "pr-commits",
            "pr-files",
        ):
            continue
        if row["state"] != "complete":
            query.coverage.add(
                "pr",
                "collection_incomplete",
                fetch_collection_id=row["fetch_collection_id"],
                collection_kind=row["kind"],
            )
    for row in s.all(
        "SELECT coverage_scope_id,kind,coverage_state FROM current_coverage WHERE change_request_id=?",
        (pr["change_request_id"],),
    ):
        if documents_only and row["kind"] in ("pr-code", "code", "commits", "files"):
            continue
        if row["coverage_state"] not in ("complete", "not_applicable"):
            query.coverage.add(
                "pr",
                "saved_scope_incomplete",
                coverage_scope_id=row["coverage_scope_id"],
            )

    for row in s.all(
        "SELECT d.change_request_id,d.kind,d.provider_change_request_document_id,EXISTS(SELECT 1 FROM document_observations o WHERE o.change_request_id=d.change_request_id AND o.kind=d.kind AND o.provider_change_request_document_id=d.provider_change_request_document_id) has_observation FROM documents d WHERE d.change_request_id=? AND d.current_document_observation_id IS NULL",
        (pr["change_request_id"],),
    ):
        key = DocumentKey(
            row["change_request_id"],
            row["kind"],
            row["provider_change_request_document_id"],
        )
        query.coverage.add(
            "pr",
            "document_current_selection_unresolved"
            if row["has_observation"]
            else "document_body_missing",
            change_request_id=key.change_request_id,
            document_kind=key.kind,
            provider_change_request_document_id=key.provider_change_request_document_id,
        )


def _bounded(item):
    item["nested_collections"] = {}
    for name in (
        "collections",
        "code_links",
        "commits",
        "file_changes",
        "observations",
    ):
        if name not in item:
            continue
        total = len(item[name])
        item[name] = item[name][:100]
        item["nested_collections"][name] = {
            "returned": len(item[name]),
            "total": total,
            "has_more": total > len(item[name]),
        }
    return item


def pr_query(query, command, options):
    s, o = query.s, options
    allowed = {r["repository_id"] for r in query.repos(o)}
    if command not in ("pr list", "search pr", "pr thread"):
        query.single_repo(o)
    selected_kind = o.get("change_request_kind")
    if selected_kind not in (None, "pull_request", "merge_request"):
        raise CatalogError("INVALID_ARGUMENT", "Unknown change request kind")
    if command == "pr thread" and (
        type(o.get("provider_change_request_number")) is not int
        or o["provider_change_request_number"] <= 0
        or not isinstance(o.get("provider_resource_id"), str)
        or not o["provider_resource_id"]
    ):
        raise CatalogError(
            "INVALID_ARGUMENT",
            "Thread selection requires a positive provider change request number and provider resource ID",
        )
    rows = s.all(
        "SELECT p.*,r.name,obs.payload,obs.observed_at_us,obs.change_request_observation_id change_request_observation_id FROM change_requests p JOIN repositories r ON r.repository_id=p.repository_id LEFT JOIN change_request_observations obs ON obs.change_request_observation_id=coalesce(p.current_change_request_observation_id, (SELECT max(change_request_observation_id) FROM change_request_observations WHERE change_request_id=p.change_request_id)) ORDER BY p.repository_id,p.provider_change_request_number,p.change_request_id"
    )
    rows = [
        r
        for r in rows
        if r["repository_id"] in allowed
        and (
            o.get("provider_change_request_number") is None
            or r["provider_change_request_number"]
            == o["provider_change_request_number"]
        )
        and (selected_kind is None or r["change_request_kind"] == selected_kind)
        and (not o.get("binding") or r["repository_binding_id"] == o["binding"])
    ]
    if o.get("provider_change_request_number") is not None and not rows:
        raise CatalogError("NOT_FOUND", "Pull request not found")
    if o.get("provider_change_request_number") is not None and len(rows) != 1:
        raise CatalogError(
            "INVALID_ARGUMENT",
            "Number is ambiguous; select --binding and --change-request-kind",
        )
    if command == "pr thread":
        request = rows[0]
        thread = s.one(
            "SELECT * FROM review_threads WHERE change_request_id=? AND provider_resource_id=?",
            (request["change_request_id"], o["provider_resource_id"]),
        )
        if not thread:
            raise CatalogError(
                "NOT_FOUND", "Review thread not found in selected change request"
            )
        for row in s.all(
            "SELECT d.change_request_id,d.kind,d.provider_change_request_document_id,o.document_observation_id,b.body,rc.payload FROM review_comments rc JOIN documents d USING(change_request_id,kind,provider_change_request_document_id) LEFT JOIN document_observations o ON o.document_observation_id=d.current_document_observation_id LEFT JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE rc.change_request_id=? AND rc.review_thread_provider_resource_id=? ORDER BY d.kind,d.provider_change_request_document_id",
            (request["change_request_id"], thread["provider_resource_id"]),
        ):
            key = DocumentKey(
                row["change_request_id"],
                row["kind"],
                row["provider_change_request_document_id"],
            )
            if row["body"] is None:
                query.coverage.add(
                    "pr",
                    "document_body_missing",
                    change_request_id=key.change_request_id,
                    document_kind=key.kind,
                    provider_change_request_document_id=key.provider_change_request_document_id,
                )
            yield (
                list(key),
                {
                    "change_request_id": key.change_request_id,
                    "document_kind": key.kind,
                    "provider_change_request_document_id": key.provider_change_request_document_id,
                    "document_observation_id": row["document_observation_id"],
                    "body": row["body"],
                    "review_thread_provider_resource_id": thread[
                        "provider_resource_id"
                    ],
                    "thread": json.loads(thread["payload"]),
                    "review_position": json.loads(row["payload"]),
                },
            )
        return
    literal = query.literal(o) if command == "search pr" else None
    path = o.get("path").encode("utf8") if o.get("path") is not None else None
    if o.get("path_b64"):
        try:
            path = base64.b64decode(o["path_b64"], validate=True)
        except (ValueError, binascii.Error):
            raise CatalogError("INVALID_ARGUMENT", "Malformed base64 path") from None
    documents_only = command in ("search pr", "pr documents") and not any(
        o.get(k) is not None for k in ("commit", "path", "path_b64")
    )
    from repo_catalog.application.repository_identity import pr_applicable

    for repo in query.repos(o):
        if not pr_applicable(s, repo["repository_id"]):
            continue
        summary_kind = "pr-documents" if documents_only else "pr"
        summary = s.one(
            "SELECT coverage_state FROM current_coverage WHERE repository_id=? AND change_request_id IS NULL AND kind=?",
            (repo["repository_id"], summary_kind),
        )
        if summary is None or summary[0] not in ("complete", "not_applicable"):
            query.coverage.add(
                "pr",
                "collection_incomplete",
                repository_id=repo["repository_id"],
                scope_kind=summary_kind,
            )
    for pr in rows:
        query.token.check()
        _coverage(query, pr, documents_only)
        payload = json.loads(pr["payload"] or "{}")
        state = pr_state(payload)
        if o.get("state", "all") != "all" and state != o["state"]:
            continue
        if o.get("author") and (payload.get("user") or {}).get("login") != o["author"]:
            continue
        if o.get("draft", "any") != "any" and payload.get("draft") is not (
            o["draft"] == "true"
        ):
            continue
        if o.get("reviewer") and not any(
            (json.loads(r[0]).get("user") or {}).get("login") == o["reviewer"]
            for r in s.all(
                "SELECT payload FROM reviews WHERE change_request_id=?",
                (pr["change_request_id"],),
            )
        ):
            continue
        code = s.one(
            "SELECT * FROM code_observations WHERE change_request_id=? AND change_request_observation_id=? ORDER BY code_observation_id DESC LIMIT 1",
            (pr["change_request_id"], pr["change_request_observation_id"]),
        )
        if not documents_only and code and code["state"] != "complete":
            query.coverage.add(
                "pr",
                "code_observation_incomplete",
                code_observation_id=code["code_observation_id"],
            )
        if o.get("commit"):
            oid = GitOid.parse(o["commit"])
            if not code or not s.one(
                "SELECT 1 FROM code_commits WHERE code_listing_id=? AND object_format=? AND oid=?",
                (code["commit_code_listing_id"], oid.algorithm, oid.value),
            ):
                continue
        if path is not None:
            changes = (
                s.all(
                    "SELECT raw_path FROM code_file_changes WHERE code_listing_id=?",
                    (code["file_code_listing_id"],),
                )
                if code
                else []
            )
            mode = o.get("path_mode", "exact")
            if not any(
                r[0] == path
                if mode == "exact"
                else r[0].startswith(path)
                if mode == "prefix"
                else path in r[0]
                for r in changes
            ):
                continue
        base = {
            "repository_id": pr["repository_id"],
            "repository": pr["name"],
            "provider_change_request_number": pr["provider_change_request_number"],
            "change_request_kind": pr["change_request_kind"],
            "pr_id": pr["change_request_id"],
            "change_request_id": pr["change_request_id"],
            "repository_binding_id": pr["repository_binding_id"],
            "current_selected": pr["current_change_request_observation_id"] is not None,
            "state": state,
            "observed_at_us": pr["observed_at_us"],
            "url": payload.get("html_url"),
        }
        if command in ("pr list", "pr show"):
            collections = s.all(
                "SELECT c.*,p.state,p.cursor,p.reason FROM fetch_collections c LEFT JOIN collection_progress p ON p.fetch_collection_id=c.fetch_collection_id WHERE c.change_request_id=? ORDER BY c.kind,c.observed_at_us,c.fetch_collection_id",
                (pr["change_request_id"],),
            )
            item = {
                **base,
                "payload": payload,
                "collections": [dict(r) for r in collections],
            }
            if command == "pr show":
                item["code_observation"] = dict(code) if code else None
                item["code_links"] = (
                    [
                        {**dict(r), "oid": f"{r['object_format']}:{r['oid'].hex()}"}
                        for r in s.all(
                            "SELECT * FROM code_acquisitions WHERE code_observation_id=? ORDER BY role",
                            (code["code_observation_id"],),
                        )
                    ]
                    if code
                    else []
                )
                item["commits"] = (
                    [
                        json.loads(r[0])
                        for r in s.all(
                            "SELECT payload FROM code_commits WHERE code_listing_id=? ORDER BY fetch_occurrence_id,position",
                            (code["commit_code_listing_id"],),
                        )
                    ]
                    if code
                    else []
                )
                item["file_changes"] = (
                    [
                        json.loads(r[0])
                        for r in s.all(
                            "SELECT payload FROM code_file_changes WHERE code_listing_id=? ORDER BY fetch_occurrence_id,position",
                            (code["file_code_listing_id"],),
                        )
                    ]
                    if code
                    else []
                )
                item["observations"] = [
                    dict(r)
                    for r in s.all(
                        "SELECT change_request_observation_id,observed_at_us FROM change_request_observations WHERE change_request_id=? ORDER BY change_request_observation_id",
                        (pr["change_request_id"],),
                    )
                ]
            yield (
                [
                    pr["repository_id"],
                    pr["provider_change_request_number"],
                    pr["change_request_id"],
                ],
                _bounded(item),
            )
        elif command == "pr timeline":
            for event in s.all(
                "SELECT * FROM change_request_events WHERE change_request_id=? ORDER BY ordinal,change_request_event_id",
                (pr["change_request_id"],),
            ):
                yield (
                    [
                        pr["repository_id"],
                        pr["provider_change_request_number"],
                        event["change_request_event_id"],
                    ],
                    {
                        **base,
                        "event_id": event["change_request_event_id"],
                        "provider_event_id": event["provider_event_id"],
                        "observed_at_us": event["observed_at_us"],
                        "payload": json.loads(event["payload"]),
                    },
                )
        else:
            selection = o.get("document_observations", "current")
            if o.get("observation") and not s.one(
                "SELECT 1 FROM document_observations WHERE document_observation_id=? AND change_request_id=?",
                (o["observation"], pr["change_request_id"]),
            ):
                raise CatalogError("NOT_FOUND", "Document observation not found in PR")
            docs = s.execute(
                "SELECT d.*,obs.document_observation_id,obs.text_body_sha256,obs.observed_at_us document_observed_at_us,obs.parsed_at_us document_parsed_at_us,obs.origin_key,obs.fetch_occurrence_id,obs.metadata observation_metadata,b.body FROM documents d JOIN document_observations obs USING(change_request_id,kind,provider_change_request_document_id) JOIN text_bodies b ON b.sha256=obs.text_body_sha256 WHERE d.change_request_id=?"
                + (
                    " AND obs.document_observation_id=d.current_document_observation_id AND d.deleted=0"
                    if selection == "current" and not o.get("observation")
                    else ""
                )
                + " ORDER BY d.kind,d.provider_change_request_document_id,obs.document_observation_id",
                (pr["change_request_id"],),
            )
            for doc in docs:
                if any(
                    o.get(option) is not None and doc[field] != o[option]
                    for option, field in (
                        (
                            "provider_change_request_document_id",
                            "provider_change_request_document_id",
                        ),
                        ("observation", "document_observation_id"),
                        ("document_kind", "kind"),
                        ("document_author", "author"),
                    )
                ):
                    continue
                key = DocumentKey(
                    doc["change_request_id"],
                    doc["kind"],
                    doc["provider_change_request_document_id"],
                )
                meta = json.loads(doc["observation_metadata"])
                comment = s.one(
                    "SELECT review_thread_provider_resource_id,payload FROM review_comments WHERE change_request_id=? AND kind=? AND provider_change_request_document_id=?",
                    key,
                )
                review_thread_provider_resource_id = (
                    comment["review_thread_provider_resource_id"]
                    if comment
                    else meta.get("review_thread_provider_resource_id")
                )
                thread = (
                    s.one(
                        "SELECT payload FROM review_threads WHERE change_request_id=? AND provider_resource_id=?",
                        (
                            doc["change_request_id"],
                            review_thread_provider_resource_id,
                        ),
                    )
                    if review_thread_provider_resource_id
                    else None
                )
                thread_payload = json.loads(thread[0]) if thread else {}
                if any(
                    o.get(option, "any") != "any"
                    and thread_payload.get(field) is not (o[option] == "true")
                    for option, field in (
                        ("resolved", "isResolved"),
                        ("outdated", "isOutdated"),
                    )
                ):
                    continue
                digest = doc["text_body_sha256"].hex()
                if literal and not query.literal_match(
                    "pr", digest, doc["body"], literal
                ):
                    continue
                yield (
                    [
                        pr["repository_id"],
                        pr["provider_change_request_number"],
                        *key,
                        doc["document_observation_id"],
                    ],
                    {
                        **base,
                        "document_kind": key.kind,
                        "provider_change_request_document_id": key.provider_change_request_document_id,
                        "document_observation_id": doc["document_observation_id"],
                        "text_body_sha256": digest,
                        "document_observed_at_us": doc["document_observed_at_us"],
                        "document_parsed_at_us": doc["document_parsed_at_us"],
                        "document_current_selected": doc["document_observation_id"]
                        == doc["current_document_observation_id"],
                        "origin_key": doc["origin_key"],
                        "fetch_occurrence_id": doc["fetch_occurrence_id"],
                        "author": doc["author"],
                        "document_url": doc["url"],
                        "body": doc["body"],
                        "metadata": meta,
                        "thread": thread_payload or None,
                        **(
                            {"review_position": json.loads(comment["payload"])}
                            if comment
                            else {}
                        ),
                    },
                )
