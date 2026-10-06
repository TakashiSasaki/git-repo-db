"""Offline change-request queries over catalog3 facts and observations."""

from __future__ import annotations

import base64
import binascii
import json

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
    if pr["current_observation_id"] is None:
        query.coverage.add(
            "pr", "current_selection_unresolved", change_request_id=pr["id"]
        )
    if pr["observation_id"] is None:
        query.coverage.add(
            "pr", "change_request_observation_missing", change_request_id=pr["id"]
        )
    rows = s.all(
        "SELECT c.kind,p.state,c.id FROM fetch_collections c "
        "LEFT JOIN collection_progress p ON p.collection_id=c.id "
        "WHERE c.change_request_id=? AND NOT EXISTS(SELECT 1 FROM fetch_collections newer "
        "WHERE newer.change_request_id=c.change_request_id AND newer.kind=c.kind "
        "AND (coalesce(newer.observed_at,'')>coalesce(c.observed_at,'') "
        "OR (newer.observed_at IS c.observed_at AND newer.rowid>c.rowid))) ORDER BY c.kind",
        (pr["id"],),
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
                collection_id=row["id"],
                collection_kind=row["kind"],
            )
    for row in s.all(
        "SELECT cs.id,cs.kind,cc.effective_state FROM coverage_scopes cs LEFT JOIN coverage_claims cc "
        "ON cc.id=cs.current_claim_id WHERE cs.change_request_id=?",
        (pr["id"],),
    ):
        if documents_only and row["kind"] in ("pr-code", "code", "commits", "files"):
            continue
        if row["effective_state"] not in ("complete", "not_applicable"):
            query.coverage.add("pr", "saved_scope_incomplete", scope_id=row["id"])

    for row in s.all(
        "SELECT d.id FROM documents d WHERE d.change_request_id=? AND NOT EXISTS(SELECT 1 FROM document_versions v WHERE v.document_id=d.id)",
        (pr["id"],),
    ):
        query.coverage.add("pr", "document_body_missing", document_id=row["id"])


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
    allowed = {r["id"] for r in query.repos(o)}
    if command not in ("pr list", "search pr", "pr thread"):
        query.single_repo(o)
    rows = s.all(
        "SELECT p.*,r.name,obs.payload,obs.observed_at,obs.id observation_id "
        "FROM change_requests p JOIN repositories r ON r.id=p.repo_id "
        "LEFT JOIN change_request_observations obs ON obs.id=coalesce(p.current_observation_id, "
        "(SELECT max(id) FROM change_request_observations WHERE change_request_id=p.id)) "
        "ORDER BY p.repo_id,p.number,p.id"
    )
    rows = [
        r
        for r in rows
        if r["repo_id"] in allowed
        and (o.get("number") is None or r["number"] == o["number"])
        and (not o.get("binding") or r["binding_id"] == o["binding"])
    ]
    if o.get("number") is not None and not rows:
        raise CatalogError("NOT_FOUND", "Pull request not found")
    if o.get("number") is not None and len(rows) != 1:
        raise CatalogError("INVALID_ARGUMENT", "Number is ambiguous; select --binding")
    if command == "pr thread":
        thread = s.one(
            "SELECT t.*,p.repo_id,p.number FROM review_threads t JOIN change_requests p ON p.id=t.change_request_id WHERE t.id=?",
            (o["thread_id"],),
        )
        if not thread or thread["repo_id"] not in allowed:
            raise CatalogError(
                "NOT_FOUND", "Review thread not found in selected repository scope"
            )
        for row in s.all(
            "SELECT d.id,b.body,rc.payload FROM review_comments rc JOIN documents d ON d.id=rc.document_id "
            "LEFT JOIN document_versions v ON v.id=d.current_version_id LEFT JOIN text_bodies b ON b.id=v.body_id "
            "WHERE rc.thread_id=? ORDER BY d.id",
            (thread["id"],),
        ):
            if row["body"] is None:
                query.coverage.add("pr", "document_body_missing", document_id=row["id"])
            yield (
                [row["id"]],
                {
                    "document_id": row["id"],
                    "body": row["body"],
                    "thread_id": thread["id"],
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
        if not pr_applicable(s, repo["id"]):
            continue
        summary_kind = "pr-documents" if documents_only else "pr"
        summary = s.one(
            "SELECT cc.effective_state FROM coverage_scopes cs LEFT JOIN coverage_claims cc "
            "ON cc.id=cs.current_claim_id WHERE cs.repo_id=? AND cs.change_request_id IS NULL AND cs.kind=?",
            (repo["id"], summary_kind),
        )
        if summary is None or summary[0] not in ("complete", "not_applicable"):
            query.coverage.add(
                "pr",
                "collection_incomplete",
                repo_id=repo["id"],
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
                "SELECT payload FROM reviews WHERE change_request_id=?", (pr["id"],)
            )
        ):
            continue
        code = s.one(
            "SELECT * FROM code_observations WHERE change_request_id=? AND observation_id=? ORDER BY id DESC LIMIT 1",
            (pr["id"], pr["observation_id"]),
        )
        if not documents_only and code and code["state"] != "complete":
            query.coverage.add(
                "pr", "code_observation_incomplete", code_observation_id=code["id"]
            )
        if o.get("commit"):
            oid = GitOid.parse(o["commit"])
            if not code or not s.one(
                "SELECT 1 FROM code_commits WHERE listing_id=? AND object_format=? AND oid=?",
                (code["commit_listing_id"], oid.algorithm, oid.value),
            ):
                continue
        if path is not None:
            changes = (
                s.all(
                    "SELECT raw_path FROM code_file_changes WHERE listing_id=?",
                    (code["file_listing_id"],),
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
            "repo_id": pr["repo_id"],
            "repository": pr["name"],
            "number": pr["number"],
            "pr_id": pr["id"],
            "change_request_id": pr["id"],
            "binding_id": pr["binding_id"],
            "current_selected": pr["current_observation_id"] is not None,
            "state": state,
            "observed_at": pr["observed_at"],
            "url": payload.get("html_url"),
        }
        if command in ("pr list", "pr show"):
            collections = s.all(
                "SELECT c.*,p.state,p.cursor,p.reason FROM fetch_collections c LEFT JOIN collection_progress p ON p.collection_id=c.id WHERE c.change_request_id=? ORDER BY c.kind,c.observed_at,c.id",
                (pr["id"],),
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
                            (code["id"],),
                        )
                    ]
                    if code
                    else []
                )
                item["commits"] = (
                    [
                        json.loads(r[0])
                        for r in s.all(
                            "SELECT payload FROM code_commits WHERE listing_id=? ORDER BY occurrence_id,position",
                            (code["commit_listing_id"],),
                        )
                    ]
                    if code
                    else []
                )
                item["file_changes"] = (
                    [
                        json.loads(r[0])
                        for r in s.all(
                            "SELECT payload FROM code_file_changes WHERE listing_id=? ORDER BY occurrence_id,position",
                            (code["file_listing_id"],),
                        )
                    ]
                    if code
                    else []
                )
                item["observations"] = [
                    dict(r)
                    for r in s.all(
                        "SELECT id,observed_at FROM change_request_observations WHERE change_request_id=? ORDER BY id",
                        (pr["id"],),
                    )
                ]
            yield [pr["repo_id"], pr["number"], pr["id"]], _bounded(item)
        elif command == "pr timeline":
            for event in s.all(
                "SELECT * FROM change_request_events WHERE change_request_id=? ORDER BY ordinal,id",
                (pr["id"],),
            ):
                yield (
                    [pr["repo_id"], pr["number"], event["id"]],
                    {
                        **base,
                        "event_id": event["id"],
                        "provider_id": event["provider_id"],
                        "observed_at": event["observed_at"],
                        "payload": json.loads(event["payload"]),
                    },
                )
        else:
            versions = o.get("document_versions", "latest")
            docs = s.execute(
                "SELECT d.*,v.id version_id,b.body FROM documents d JOIN document_versions v ON v.document_id=d.id JOIN text_bodies b ON b.id=v.body_id WHERE d.change_request_id=?"
                + (
                    " AND v.id=d.current_version_id AND d.deleted=0"
                    if versions == "latest" and not o.get("version")
                    else ""
                )
                + " ORDER BY d.id,v.id",
                (pr["id"],),
            )
            if o.get("version") and not s.one(
                "SELECT 1 FROM document_versions v JOIN documents d ON d.id=v.document_id WHERE v.id=? AND d.change_request_id=?",
                (o["version"], pr["id"]),
            ):
                raise CatalogError("NOT_FOUND", "Document version not found in PR")
            for doc in docs:
                if any(
                    o.get(k) is not None and doc[field] != o[k]
                    for k, field in (
                        ("document", "id"),
                        ("version", "version_id"),
                        ("document_kind", "kind"),
                        ("document_author", "author"),
                    )
                ):
                    continue
                meta = json.loads(doc["metadata"])
                comment = s.one(
                    "SELECT thread_id,payload FROM review_comments WHERE document_id=?",
                    (doc["id"],),
                )
                thread_id = comment["thread_id"] if comment else meta.get("thread_id")
                thread = (
                    s.one("SELECT payload FROM review_threads WHERE id=?", (thread_id,))
                    if thread_id
                    else None
                )
                thread_payload = json.loads(thread[0]) if thread else {}
                if any(
                    o.get(k, "any") != "any"
                    and thread_payload.get(field) is not (o[k] == "true")
                    for k, field in (
                        ("resolved", "isResolved"),
                        ("outdated", "isOutdated"),
                    )
                ):
                    continue
                if literal and not query.literal_match(
                    "pr", doc["version_id"], doc["body"], literal
                ):
                    continue
                observations = [
                    dict(r)
                    for r in s.all(
                        "SELECT id,observed_at,version_id FROM document_observations WHERE document_id=? AND version_id=? ORDER BY id",
                        (doc["id"], doc["version_id"]),
                    )
                ]
                yield (
                    [pr["repo_id"], pr["number"], doc["id"], doc["version_id"]],
                    {
                        **base,
                        "document_id": doc["id"],
                        "version_id": doc["version_id"],
                        "document_kind": doc["kind"],
                        "author": doc["author"],
                        "document_url": doc["url"],
                        "body": doc["body"],
                        "observations": observations,
                        "metadata": meta,
                        "thread": thread_payload or None,
                        **(
                            {"review_position": json.loads(comment["payload"])}
                            if comment
                            else {}
                        ),
                    },
                )
