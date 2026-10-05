import json

from repo_catalog.domain.models import CatalogError


def pr_state(payload):
    merged = payload.get("merged")
    if merged is None and "merged_at" in payload:
        merged = payload["merged_at"] is not None
    if merged:
        return "merged"
    if payload.get("state") == "open":
        return "open"
    return "closed" if merged is False else "unknown"


def pr_query(query, command, o):
    s = query.s
    allowed = {r["id"] for r in query.repos(o)}
    if command not in ("pr list", "search pr", "pr thread"):
        query.single_repo(o)
    rows = s.all(
        "SELECT p.*,r.name,o.payload,o.observed_at FROM pull_requests p JOIN repositories r ON r.id=p.repo_id JOIN pr_observations o ON o.id=p.current_observation ORDER BY p.repo_id,p.number"
    )
    if o.get("number") is not None:
        rows = [
            r for r in rows if r["number"] == o["number"] and r["repo_id"] in allowed
        ]
        if not rows:
            raise CatalogError("NOT_FOUND", "Pull request not found")
    if command == "pr thread":
        thread = s.one("SELECT * FROM review_threads WHERE id=?", (o["thread_id"],))
        if not thread:
            raise CatalogError("NOT_FOUND", "Review thread not found")
        for r in s.all(
            "SELECT d.*,v.body,rc.payload FROM review_comments rc JOIN pr_documents d ON d.id=rc.document_id JOIN document_versions v ON v.id=d.current_version WHERE rc.thread_id=? ORDER BY d.id",
            (thread["id"],),
        ):
            pr = s.one(
                "SELECT repo_id,number FROM pull_requests WHERE id=?", (r["pr_id"],)
            )
            if pr["repo_id"] not in allowed:
                raise CatalogError(
                    "NOT_FOUND", "Thread outside selected repository scope"
                )
            yield (
                [r["id"]],
                {
                    "document_id": r["id"],
                    "body": r["body"],
                    "thread_id": thread["id"],
                    "thread": json.loads(thread["payload"]),
                    "review_position": json.loads(r["payload"]),
                },
            )
        return
    literal = query.literal(o) if command == "search pr" else None
    for repo in query.repos(o):
        if repo["provider_host"] == "local":
            continue
        documents_only = command in ("search pr", "pr documents") and not any(
            o.get(key) is not None for key in ("commit", "path", "path_b64")
        )
        coverage = s.one(
            "SELECT state FROM coverage_components WHERE owner_id=? AND kind=?",
            (repo["id"], "pr-documents" if documents_only else "pr"),
        )
        if not coverage and documents_only:
            coverage = s.one(
                "SELECT state FROM coverage_components WHERE owner_id=? AND kind='pr'",
                (repo["id"],),
            )
        if not coverage or coverage[0] != "complete":
            query.coverage.add("pr", "collection_incomplete", repo_id=repo["id"])
    for pr in rows:
        if pr["repo_id"] not in allowed:
            continue
        payload = json.loads(pr["payload"])
        state = pr_state(payload)
        if o.get("state", "all") != "all" and state != o["state"]:
            continue
        if o.get("author") and (payload.get("user") or {}).get("login") != o["author"]:
            continue
        if o.get("draft", "any") != "any" and payload.get("draft") is not (
            o["draft"] == "true"
        ):
            continue
        if o.get("reviewer"):
            reviews = [
                json.loads(r[0])
                for r in s.all(
                    "SELECT payload FROM pr_reviews WHERE pr_id=?", (pr["id"],)
                )
            ]
            if not any(
                (r.get("user") or {}).get("login") == o["reviewer"] for r in reviews
            ):
                continue
        observations = s.all(
            "SELECT * FROM collections WHERE pr_id=? ORDER BY kind,observed_at",
            (pr["id"],),
        )
        code = s.one(
            "SELECT * FROM pr_code_observations WHERE pr_id=? ORDER BY id DESC LIMIT 1",
            (pr["id"],),
        )
        if o.get("commit"):
            from repo_catalog.domain.models import GitOid

            oid = GitOid.parse(o["commit"]).value.hex()
            if not code or not s.one(
                "SELECT 1 FROM pr_commits WHERE code_observation=? AND oid=?",
                (code["id"], oid),
            ):
                continue
        path = o.get("path")
        if o.get("path_b64"):
            import base64

            try:
                path = base64.b64decode(o["path_b64"], validate=True).decode("utf8")
            except (ValueError, UnicodeDecodeError):
                raise CatalogError("INVALID_ARGUMENT", "PR API paths must be UTF-8")
        if path is not None:
            changes = (
                [
                    r[0]
                    for r in s.all(
                        "SELECT path FROM pr_file_changes WHERE code_observation=?",
                        (code["id"],),
                    )
                ]
                if code
                else []
            )
            mode = o.get("path_mode", "exact")
            if not any(
                p == path
                if mode == "exact"
                else p.startswith(path)
                if mode == "prefix"
                else path in p
                for p in changes
            ):
                continue
        base = {
            "repo_id": pr["repo_id"],
            "repository": pr["name"],
            "number": pr["number"],
            "pr_id": pr["id"],
            "state": state,
            "observed_at": pr["observed_at"],
            "url": payload.get("html_url"),
        }
        if command in ("pr list", "pr show"):
            item = {
                **base,
                "payload": payload,
                "collections": [dict(r) for r in observations],
            }
            if command == "pr show":
                item["code_observation"] = dict(code) if code else None
                item["code_links"] = (
                    [
                        {**dict(r), "oid": f"{r['object_format']}:{r['oid'].hex()}"}
                        for r in s.all(
                            "SELECT * FROM pr_git_links WHERE code_observation=?",
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
                            "SELECT payload FROM pr_commits WHERE code_observation=? ORDER BY ordinal",
                            (code["id"],),
                        )
                    ]
                    if code
                    else []
                )
                item["file_changes"] = (
                    [
                        json.loads(r[0])
                        for r in s.all(
                            "SELECT payload FROM pr_file_changes WHERE code_observation=? ORDER BY ordinal",
                            (code["id"],),
                        )
                    ]
                    if code
                    else []
                )
                item["observations"] = [
                    {"id": r["id"], "observed_at": r["observed_at"]}
                    for r in s.all(
                        "SELECT * FROM pr_observations WHERE pr_id=? ORDER BY id",
                        (pr["id"],),
                    )
                ]
            # The outer page limit does not bound arrays inside one PR. Keep
            # their display finite and expose every omitted nested collection.
            item["nested_collections"] = {}
            for name in (
                "collections",
                "code_links",
                "commits",
                "file_changes",
                "observations",
            ):
                if name in item:
                    total = len(item[name])
                    item[name] = item[name][:100]
                    item["nested_collections"][name] = {
                        "returned": len(item[name]),
                        "total": total,
                        "has_more": total > len(item[name]),
                    }
            yield [pr["repo_id"], pr["number"]], item
        elif command == "pr timeline":
            latest = s.one(
                "SELECT id FROM collections WHERE pr_id=? AND kind='timeline' ORDER BY observed_at DESC LIMIT 1",
                (pr["id"],),
            )
            if latest:
                for event in s.all(
                    "SELECT * FROM pr_events WHERE run_id=? ORDER BY ordinal",
                    (latest[0],),
                ):
                    yield (
                        [pr["repo_id"], pr["number"], event["ordinal"]],
                        {
                            **base,
                            "event_id": event["id"],
                            "provider_id": event["provider_id"],
                            "payload": json.loads(event["payload"]),
                        },
                    )
        else:
            versions = o.get("document_versions", "latest")
            docs = s.all(
                "SELECT d.*,v.id version_id,v.body FROM pr_documents d JOIN document_versions v ON v.document_id=d.id WHERE d.pr_id=?"
                + (
                    " AND v.id=d.current_version AND d.deleted=0"
                    if versions == "latest" and not o.get("version")
                    else ""
                )
                + " ORDER BY d.id,v.id",
                (pr["id"],),
            )
            if o.get("version") and not any(
                r["version_id"] == o["version"] for r in docs
            ):
                raise CatalogError("NOT_FOUND", "Document version not found in PR")
            for doc in docs:
                if o.get("document") and doc["id"] != o["document"]:
                    continue
                if o.get("version") and doc["version_id"] != o["version"]:
                    continue
                if o.get("document_kind") and doc["kind"] != o["document_kind"]:
                    continue
                if o.get("document_author") and doc["author"] != o["document_author"]:
                    continue
                meta = json.loads(doc["metadata"])
                thread_id = meta.get("thread_id")
                thread = (
                    s.one("SELECT payload FROM review_threads WHERE id=?", (thread_id,))
                    if thread_id
                    else None
                )
                thread_payload = json.loads(thread[0]) if thread else {}
                if any(
                    o.get(k, "any") != "any"
                    and thread_payload.get(field) is not (o[k] == "true")
                    for k, field in [
                        ("resolved", "isResolved"),
                        ("outdated", "isOutdated"),
                    ]
                ):
                    continue
                if literal and not query.literal_match(
                    "pr", doc["version_id"], doc["body"], literal
                ):
                    continue
                observations = [
                    {
                        "id": r["id"],
                        "observed_at": r["observed_at"],
                        "version_id": r["version_id"],
                    }
                    for r in s.all(
                        "SELECT * FROM resource_observations WHERE document_id=? AND version_id=? ORDER BY id",
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
                    },
                )
