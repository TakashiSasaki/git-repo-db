"""Offline change-request queries over catalog3 facts and observations."""

from __future__ import annotations

import base64
import binascii
import json

from repo_catalog.domain.document import DocumentKey
from repo_catalog.domain.models import CatalogError, GitOid
from repo_catalog.domain.pr_scope import document_scope_includes


def pr_state(payload):
    merged = payload.get("merged")
    if merged is None and "merged_at" in payload:
        merged = payload["merged_at"] is not None
    if merged:
        return "merged"
    if payload.get("state") == "open":
        return "open"
    return "closed" if merged is False else "unknown"


def _collection_boundary(query, collection_id):
    """Observation boundary excludes mutable progress and unobserved attempts."""
    return query.s.one(
        "SELECT max(observed_at_us) FROM ("
        "SELECT observed_at_us FROM fetch_occurrences WHERE fetch_collection_id=? "
        "AND coalesce(json_extract(request,'$.operational_only'),0)=0 "
        "UNION ALL SELECT observed_at_us FROM completion_markers WHERE fetch_collection_id=?)",
        (collection_id, collection_id),
    )[0]


def _latest_collections(query, rows):
    candidates = []
    latest = None
    for row in rows:
        query.check()
        boundary = _collection_boundary(query, row["fetch_collection_id"])
        if boundary is not None and (latest is None or boundary > latest):
            candidates = [row]
            latest = boundary
        elif boundary == latest:
            candidates.append(row)
    return candidates


def _collection_proof_graph(query):
    from repo_catalog.adapters.sqlite.exchange import Graph

    graph = getattr(query, "collection_proof_graph", None)
    if graph is None:
        graph = Graph(query.s.connection, persist_identities=False)
        query.collection_proof_graph = graph
    return graph


def _collection_state(query, row):
    """Qualify immutable collection evidence independently of local job progress."""
    graph = _collection_proof_graph(query)
    markers = graph.matching(
        "completion_markers", ("fetch_collection_id",), (row["fetch_collection_id"],)
    )
    boundary = _collection_boundary(query, row["fetch_collection_id"])
    latest = [marker for marker in markers if marker["observed_at_us"] == boundary]
    if markers and not latest:
        return "partial"
    states = {marker["asserted_state"] for marker in latest}
    if states and states != {"complete"}:
        return next(iter(states)) if len(states) == 1 else "conflict"
    for marker in latest:
        query.check()
        key = graph.key("completion_markers", marker)
        proof = graph.proof_requirements("completion_markers", marker)
        if not proof:
            return "unknown"
        if any(
            query.s.one(
                "SELECT 1 FROM exchange_staging WHERE record_key=? AND reason LIKE 'conflict:%'",
                (dependency,),
            )
            for dependency in proof | {key}
        ):
            return "conflict"
        evidence = json.loads(marker["evidence"])
        acquisitions = list(evidence.get("fetch_occurrence_uuidv4s", []))
        if evidence.get("status") == 304:
            acquisitions.append(evidence["fetch_occurrence_uuidv4"])
        if any(
            query.s.one(
                "SELECT 1 FROM fetch_occurrences f JOIN payload_quarantine q ON q.sha256=f.payload_sha256 WHERE f.fetch_occurrence_uuidv4=?",
                (identifier,),
            )
            for identifier in acquisitions
        ):
            return "unknown"
    if latest:
        return "complete"
    return row["state"]


def _coverage(query, pr, documents_only):
    s = query.s
    if pr["change_request_observation_id"] is None:
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
    rows = s.execute(
        "SELECT c.kind,p.state,c.fetch_collection_id FROM fetch_collections c LEFT JOIN collection_progress p ON p.fetch_collection_id=c.fetch_collection_id WHERE c.change_request_id=? ORDER BY c.kind",
        (pr["change_request_id"],),
    )
    by_kind = {}
    for row in rows:
        by_kind.setdefault(row["kind"], []).append(row)
    for row in (
        row
        for candidates in by_kind.values()
        for row in _latest_collections(query, candidates)
    ):
        query.check()
        if documents_only and not document_scope_includes(row["kind"]):
            continue
        if _collection_state(query, row) != "complete":
            query.coverage.add(
                "pr",
                "collection_incomplete",
                fetch_collection_id=row["fetch_collection_id"],
                collection_kind=row["kind"],
            )
    for row in s.execute(
        "SELECT coverage_scope_id,kind,coverage_state FROM current_coverage WHERE change_request_id=?",
        (pr["change_request_id"],),
    ):
        query.check()
        if documents_only and not document_scope_includes(row["kind"]):
            continue
        if row["coverage_state"] not in ("complete", "not_applicable"):
            query.coverage.add(
                "pr",
                "saved_scope_incomplete",
                coverage_scope_id=row["coverage_scope_id"],
            )

    for row in s.execute(
        "SELECT d.change_request_id,d.kind,d.provider_change_request_document_id,EXISTS(SELECT 1 FROM document_observations o WHERE o.change_request_id=d.change_request_id AND o.kind=d.kind AND o.provider_change_request_document_id=d.provider_change_request_document_id) has_observation FROM documents d LEFT JOIN current_document_observations selected USING(change_request_id,kind,provider_change_request_document_id) WHERE d.change_request_id=? AND selected.document_observation_id IS NULL",
        (pr["change_request_id"],),
    ):
        query.check()
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


def _scope_rows(query, command, o):
    """Stream the identity scope, before filters requiring saved content.

    Missing content in this scope may itself be a matching result, so coverage
    cannot be restricted to rows that happen to survive content filters.
    """
    s = query.s
    allowed = {r["repository_uuidv4"] for r in query.repos(o)}
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
    conditions = [
        "p.repository_uuidv4 IN (" + ",".join("?" for _ in allowed) + ")"
        if allowed
        else "0"
    ]
    values = list(allowed)
    for option, column in (
        ("provider_change_request_number", "provider_change_request_number"),
        ("change_request_kind", "change_request_kind"),
        ("binding", "repository_binding_id"),
    ):
        value = o.get(option)
        if value is None or option == "binding" and not value:
            continue
        conditions.append(f"p.{column}=?")
        values.append(value)
    rows = s.execute(
        "SELECT p.*,r.name,obs.payload,obs.observed_at_us,obs.change_request_observation_id,obs.change_request_observation_uuidv4,obs.parsed_result_uuidv4,profile.parser_profile_uuidv4 FROM change_requests p JOIN repositories r ON r.repository_uuidv4=p.repository_uuidv4 LEFT JOIN current_change_request_observations obs ON obs.change_request_id=p.change_request_id LEFT JOIN parsed_results profile ON profile.parsed_result_uuidv4=obs.parsed_result_uuidv4 WHERE "
        + " AND ".join(conditions)
        + " ORDER BY p.repository_uuidv4,p.provider_change_request_number,p.change_request_id",
        values,
    )
    if o.get("provider_change_request_number") is not None:
        # Two identities are enough to prove that a provider number is ambiguous.
        rows = rows.fetchmany(2)
        if not rows:
            raise CatalogError("NOT_FOUND", "Pull request not found")
        if len(rows) != 1:
            raise CatalogError(
                "INVALID_ARGUMENT",
                "Number is ambiguous; select --binding and --change-request-kind",
            )
    return rows


def _selected_thread(query, rows, o):
    request = next(iter(rows))
    thread = query.s.one(
        "SELECT * FROM current_review_thread_observations WHERE change_request_id=? AND provider_resource_id=?",
        (request["change_request_id"], o["provider_resource_id"]),
    )
    if not thread:
        identity = query.s.one(
            "SELECT * FROM review_threads WHERE change_request_id=? AND provider_resource_id=?",
            (request["change_request_id"], o["provider_resource_id"]),
        )
        if identity is None:
            raise CatalogError(
                "NOT_FOUND", "Review thread not found in selected change request"
            )
        query.coverage.add(
            "pr",
            "thread_current_selection_unresolved",
            change_request_id=request["change_request_id"],
            provider_resource_id=o["provider_resource_id"],
        )
    return request, thread


def _query_filters(query, command, o):
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
    return literal, path, documents_only


def _matches_pr_filters(query, pr, payload, state, o):
    if o.get("state", "all") != "all" and state != o["state"]:
        return False
    if o.get("author") and (payload.get("user") or {}).get("login") != o["author"]:
        return False
    if o.get("draft", "any") != "any" and payload.get("draft") is not (
        o["draft"] == "true"
    ):
        return False
    if o.get("reviewer"):
        for row in query.s.execute(
            "SELECT metadata FROM current_document_observations WHERE change_request_id=? AND kind='review' AND deleted=0",
            (pr["change_request_id"],),
        ):
            query.check()
            if (json.loads(row[0]).get("user") or {}).get("login") == o["reviewer"]:
                break
        else:
            return False
    return True


def _code_observation(query, pr):
    return query.s.one(
        "SELECT * FROM current_code_observations WHERE change_request_id=? AND change_request_observation_id=?",
        (pr["change_request_id"], pr["change_request_observation_id"]),
    )


def _code_coverage(query, pr, payload):
    code = _code_observation(query, pr)
    if code is None:
        # A current API observation can be committed before its Git acquisition
        # finishes. An older complete claim cannot prove this observation's
        # code is present. Metadata-only PRs have no inferred code obligation.
        expects_code = any(
            isinstance(payload.get(role), dict) and payload[role].get("sha") is not None
            for role in ("head", "base")
        ) or query.s.one(
            "SELECT 1 FROM code_observations WHERE change_request_id=? UNION ALL SELECT 1 FROM code_listings WHERE change_request_id=? LIMIT 1",
            (pr["change_request_id"], pr["change_request_id"]),
        )
        if expects_code:
            query.coverage.add(
                "pr",
                "code_observation_missing",
                change_request_id=pr["change_request_id"],
                change_request_observation_id=pr["change_request_observation_id"],
            )
    elif code["state"] != "complete":
        query.coverage.add(
            "pr",
            "code_observation_incomplete",
            code_observation_id=code["code_observation_id"],
        )
    else:
        for gap in code_role_gaps(query.s, pr, code, check=query.check):
            query.coverage.add("pr", **gap)
    if code is not None:
        for scope in query.s.execute(
            "SELECT scope.fact_selection_scope_uuidv4 FROM fact_selection_scopes scope "
            "JOIN fetch_occurrences input ON input.fetch_occurrence_uuidv4=scope.fetch_occurrence_uuidv4 "
            "JOIN code_listings listing ON listing.fetch_collection_id=input.fetch_collection_id "
            "LEFT JOIN active_fact_selections active USING(fact_selection_scope_uuidv4) "
            "WHERE scope.change_request_id=? AND scope.fact_kind='code' "
            "AND listing.code_listing_id IN (?,?) AND active.fact_selection_decision_uuidv4 IS NULL",
            (
                pr["change_request_id"],
                code["commit_code_listing_id"],
                code["file_code_listing_id"],
            ),
        ):
            query.coverage.add("pr", "code_page_selection_unresolved", **dict(scope))


def code_role_gaps(store, pr, code, *, check):
    """Yield shared ordinary/diagnostic checks of explicitly required targets."""
    required = {
        role: GitOid(code["object_format"], code[role + "_oid"])
        for role in ("head", "base")
        if code[role + "_oid"] is not None
    }
    declared = json.loads(code["details"]).get("expected_roles", {})
    if not isinstance(declared, dict):
        yield {
            "reason": "code_role_targets_unresolved",
            "code_observation_id": code["code_observation_id"],
        }
        declared = {}
    for role, value in declared.items():
        check()
        try:
            if not role or not isinstance(value, str):
                raise ValueError()
            oid = GitOid.parse(f"{code['object_format']}:{value}")
        except (ValueError, CatalogError):
            yield {
                "reason": "code_role_targets_unresolved",
                "code_observation_id": code["code_observation_id"],
                "role": role,
            }
            continue
        if role in required and required[role] != oid:
            yield {
                "reason": "code_role_target_conflict",
                "code_observation_id": code["code_observation_id"],
                "role": role,
            }
        else:
            required[role] = oid
    if not required:
        return
    links = {
        (row["role"], row["object_format"], row["oid"])
        for row in store.execute(
            "SELECT a.role,a.object_format,a.oid FROM code_acquisitions a JOIN acquisition_roots r ON r.acquisition_root_id=a.acquisition_root_id JOIN git_objects o ON o.object_format=a.object_format AND o.oid=a.oid WHERE a.code_observation_id=? AND r.repository_uuidv4=? AND r.published=1 AND r.object_format=a.object_format AND r.oid=a.oid AND (r.expected_oid IS NULL OR r.expected_oid=a.oid) AND o.type='commit' AND o.verified=1",
            (code["code_observation_id"], pr["repository_uuidv4"]),
        )
    }
    for role, oid in sorted(required.items()):
        check()
        if (role, oid.algorithm, oid.value) not in links:
            yield {
                "reason": "code_role_acquisition_missing",
                "change_request_id": pr["change_request_id"],
                "code_observation_id": code["code_observation_id"],
                "role": role,
                "expected_oid": f"{oid.algorithm}:{oid.value.hex()}",
            }


def _thread_root(query, request, thread):
    """Read acquisition-boundary evidence; this never selects normalized facts.

    A resumed child can be newer than a subsequently started root. Failed
    requests without resource data do not supersede saved semantic evidence.
    Preserve every candidate at the latest known observation boundary.
    """
    candidates = {}
    latest = None
    for row in query.s.execute(
        "SELECT root.*,member.kind member_kind,o.observed_at_us boundary,b.body FROM fetch_collections member "
        "JOIN resume_scopes scope ON scope.resume_scope_id=member.resume_scope_id "
        "JOIN fetch_collections root ON root.change_request_id=member.change_request_id "
        "AND root.repository_uuidv4=member.repository_uuidv4 "
        "AND root.source_id IS member.source_id AND root.kind='threads' "
        "AND root.fetch_collection_id=CASE WHEN member.kind='threads' "
        "THEN member.fetch_collection_id ELSE "
        "json_extract(scope.request_context,'$.parent_fetch_collection_id') END "
        "JOIN fetch_occurrences o ON o.fetch_collection_id=member.fetch_collection_id "
        "JOIN stored_bytes b ON b.sha256=o.payload_sha256 "
        "WHERE member.change_request_id=? "
        "AND (member.kind='threads' OR (member.kind='thread-comments' "
        "AND json_extract(scope.request_context,'$.thread')=?)) "
        "AND coalesce(json_extract(o.request,'$.operational_only'),0)=0 "
        "AND NOT EXISTS(SELECT 1 FROM payload_quarantine q WHERE q.sha256=o.payload_sha256) "
        "ORDER BY o.observed_at_us DESC,o.fetch_occurrence_uuidv4",
        (request["change_request_id"], thread["provider_resource_id"]),
    ):
        query.check()
        try:
            payload = json.loads(row["body"])
            resource = (
                payload["data"]["repository"]["pullRequest"]
                if row["member_kind"] == "threads"
                else payload["data"]["node"]
            )
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(resource, dict):
            continue
        if candidates and row["boundary"] != latest:
            break
        latest = row["boundary"]
        candidates[row["fetch_collection_id"]] = row
    return list(candidates.values())


def _thread_listing_complete(query, request, thread):
    """Prove this thread's comment boundary in the latest root scan.

    Root progress includes every thread, so an unrelated child's failure must not
    invalidate a terminal selected thread. The saved root response establishes its
    first comment page; further pages require a sealed child of this exact root.
    """
    roots = _thread_root(query, request, thread)
    return bool(roots) and all(
        _thread_root_listing_complete(query, request, thread, root) for root in roots
    )


def _thread_root_listing_complete(query, request, thread, root):
    s = query.s
    graph = _collection_proof_graph(query)
    if any(
        s.one(
            "SELECT 1 FROM exchange_staging WHERE record_key=? AND reason LIKE 'conflict:%'",
            (graph.key("completion_markers", marker),),
        )
        for marker in graph.matching(
            "completion_markers",
            ("fetch_collection_id",),
            (root["fetch_collection_id"],),
        )
    ):
        return False
    # New attempts may retain rejected pages at the same cursor. Use the most
    # recent occurrence containing this thread, never an older successful page.
    pages = []
    latest = None
    for page in s.execute(
        "SELECT o.fetch_occurrence_id,o.observed_at_us,o.request,b.body FROM fetch_occurrences o "
        "JOIN stored_bytes b ON b.sha256=o.payload_sha256 "
        "WHERE o.fetch_collection_id=? "
        "AND NOT EXISTS(SELECT 1 FROM payload_quarantine q WHERE q.sha256=o.payload_sha256) "
        "ORDER BY o.observed_at_us DESC,o.ordinal DESC,o.fetch_occurrence_uuidv4",
        (root["fetch_collection_id"],),
    ):
        query.check()
        try:
            payload = json.loads(page["body"])
            nodes = payload["data"]["repository"]["pullRequest"]["reviewThreads"][
                "nodes"
            ]
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(nodes, list):
            continue
        selected = next(
            (
                node
                for node in nodes
                if isinstance(node, dict)
                and node.get("id") == thread["provider_resource_id"]
            ),
            None,
        )
        if selected is None:
            continue
        if pages and page["observed_at_us"] != latest:
            break
        latest = page["observed_at_us"]
        pages.append((page, payload, selected))
    return bool(pages) and all(
        _thread_page_complete(query, request, thread, root, page, payload, selected)
        for page, payload, selected in pages
    )


def _thread_page_complete(query, request, thread, root, page, payload, selected):
    s = query.s
    if payload.get("errors") or json.loads(page["request"]).get("normalization_error"):
        return False
    comments = selected.get("comments")
    if not isinstance(comments, dict) or not isinstance(comments.get("nodes"), list):
        return False
    expected = set()
    for comment in comments["nodes"]:
        query.check()
        provider = comment.get("fullDatabaseId") if isinstance(comment, dict) else None
        if type(provider) not in (int, str) or not str(provider):
            return False
        expected.add(str(provider))
    saved = {
        row[0]
        for row in s.execute(
            "SELECT o.provider_change_request_document_id FROM eligible_document_observations o "
            "WHERE o.fetch_occurrence_id=? AND o.change_request_id=? "
            "AND o.kind='review-comment' AND o.review_thread_provider_resource_id=?",
            (
                page["fetch_occurrence_id"],
                request["change_request_id"],
                thread["provider_resource_id"],
            ),
        )
    }
    if not expected <= saved:
        return False
    info = comments.get("pageInfo")
    if not isinstance(info, dict) or type(info.get("hasNextPage")) is not bool:
        return False
    if not info["hasNextPage"]:
        return True
    if not isinstance(info.get("endCursor"), str) or not info["endCursor"]:
        return False
    children = s.all(
        "SELECT f.*,p.state "
        "FROM fetch_collections f JOIN resume_scopes scope "
        "ON scope.resume_scope_id=f.resume_scope_id "
        "LEFT JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id "
        "WHERE f.change_request_id=? AND f.repository_uuidv4=? "
        "AND f.source_id IS ? AND f.kind='thread-comments' "
        "AND json_extract(scope.request_context,'$.thread')=? "
        "AND json_extract(scope.request_context,'$.parent_fetch_collection_id')=?",
        (
            request["change_request_id"],
            root["repository_uuidv4"],
            root["source_id"],
            thread["provider_resource_id"],
            root["fetch_collection_id"],
        ),
    )
    candidates = _latest_collections(query, children)
    return bool(candidates) and all(
        _collection_state(query, child) == "complete" for child in candidates
    )


def prepare_pr_coverage(query, command, o):
    """Evaluate the full requested scope in the query's read snapshot.

    Row projection can stop at either page bound without changing this report.
    PR metadata and missing references are scanned, with saved GraphQL page
    boundaries inspected for a selected thread. Result projection remains lazy.
    """
    s = query.s
    rows = _scope_rows(query, command, o)
    if command == "pr thread":
        request, thread = _selected_thread(query, rows, o)
        if thread is None:
            return
        if not _thread_listing_complete(query, request, thread):
            query.coverage.add(
                "pr",
                "thread_listing_incomplete",
                change_request_id=request["change_request_id"],
                provider_resource_id=thread["provider_resource_id"],
            )
        missing = {
            row[0]
            for row in s.execute(
                "SELECT d.provider_change_request_document_id FROM documents d "
                "WHERE d.change_request_id=? AND d.kind='review-comment' "
                "AND EXISTS(SELECT 1 FROM eligible_document_observations history "
                "WHERE history.change_request_id=d.change_request_id AND history.kind=d.kind "
                "AND history.provider_change_request_document_id=d.provider_change_request_document_id "
                "AND history.review_thread_provider_resource_id=?) "
                "AND NOT EXISTS(SELECT 1 FROM current_document_observations selected "
                "WHERE selected.change_request_id=d.change_request_id AND selected.kind=d.kind "
                "AND selected.provider_change_request_document_id=d.provider_change_request_document_id)",
                (request["change_request_id"], thread["provider_resource_id"]),
            )
        }
        comments = json.loads(thread["payload"]).get("comments")
        if isinstance(comments, dict) and isinstance(comments.get("nodes"), list):
            for comment in comments["nodes"]:
                query.check()
                provider = (
                    comment.get("fullDatabaseId") if isinstance(comment, dict) else None
                )
                if type(provider) not in (int, str):
                    continue
                if s.one(
                    "SELECT 1 FROM documents d WHERE change_request_id=? AND kind='review-comment' "
                    "AND provider_change_request_document_id=? AND NOT EXISTS(SELECT 1 FROM "
                    "current_document_observations selected WHERE selected.change_request_id=d.change_request_id "
                    "AND selected.kind=d.kind AND selected.provider_change_request_document_id=d.provider_change_request_document_id)",
                    (request["change_request_id"], str(provider)),
                ):
                    missing.add(str(provider))
        for provider in sorted(missing):
            query.coverage.add(
                "pr",
                "document_body_missing",
                change_request_id=request["change_request_id"],
                document_kind="review-comment",
                provider_change_request_document_id=provider,
            )
        return
    _, _, documents_only = _query_filters(query, command, o)
    from repo_catalog.application.repository_identity import pr_applicable

    for repo in query.repos(o):
        query.check()
        if not pr_applicable(s, repo["repository_uuidv4"]):
            continue
        summary_kind = "pr-documents" if documents_only else "pr"
        summary = s.one(
            "SELECT coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id IS NULL AND kind=?",
            (repo["repository_uuidv4"], summary_kind),
        )
        if summary is None or summary[0] not in ("complete", "not_applicable"):
            query.coverage.add(
                "pr",
                "collection_incomplete",
                repository_uuidv4=repo["repository_uuidv4"],
                scope_kind=summary_kind,
            )
    for pr in rows:
        query.check()
        _coverage(query, pr, documents_only)
        if command == "pr timeline":
            for scope in s.execute(
                "SELECT scope.fact_selection_scope_uuidv4 FROM fact_selection_scopes scope "
                "LEFT JOIN active_fact_selections active USING(fact_selection_scope_uuidv4) "
                "WHERE scope.change_request_id=? AND scope.fact_kind='events' "
                "AND active.fact_selection_decision_uuidv4 IS NULL",
                (pr["change_request_id"],),
            ):
                query.coverage.add(
                    "pr", "event_page_selection_unresolved", **dict(scope)
                )
        if documents_only:
            continue
        payload = json.loads(pr["payload"] or "{}")
        _code_coverage(query, pr, payload)


def pr_query(query, command, options):
    s, o = query.s, options
    rows = _scope_rows(query, command, o)
    if command == "pr thread":
        request, thread = _selected_thread(query, rows, o)
        if thread is None:
            return
        documents = list(
            s.execute(
                "SELECT o.change_request_id,o.kind,o.provider_change_request_document_id,o.document_observation_id,o.parsed_result_uuidv4,b.body,o.metadata payload FROM current_document_observations o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.change_request_id=? AND o.review_thread_provider_resource_id=? AND o.deleted=0 ORDER BY o.kind,o.provider_change_request_document_id",
                (request["change_request_id"], thread["provider_resource_id"]),
            )
        )
        saved = {row["provider_change_request_document_id"] for row in documents}
        comments = json.loads(thread["payload"]).get("comments")
        if isinstance(comments, dict) and isinstance(comments.get("nodes"), list):
            for comment in comments["nodes"]:
                provider = (
                    comment.get("fullDatabaseId") if isinstance(comment, dict) else None
                )
                if type(provider) not in (int, str) or str(provider) in saved:
                    continue
                key = (request["change_request_id"], "review-comment", str(provider))
                if s.one(
                    "SELECT 1 FROM documents WHERE change_request_id=? AND kind=? AND provider_change_request_document_id=?",
                    key,
                ):
                    documents.append(
                        {
                            "change_request_id": key[0],
                            "kind": key[1],
                            "provider_change_request_document_id": key[2],
                            "document_observation_id": None,
                            "parsed_result_uuidv4": None,
                            "body": None,
                            "payload": "{}",
                        }
                    )
                    saved.add(str(provider))
        for row in sorted(
            documents,
            key=lambda item: (
                item["kind"],
                item["provider_change_request_document_id"],
            ),
        ):
            query.check()
            key = DocumentKey(
                row["change_request_id"],
                row["kind"],
                row["provider_change_request_document_id"],
            )
            yield (
                list(key),
                {
                    "change_request_id": key.change_request_id,
                    "document_kind": key.kind,
                    "provider_change_request_document_id": key.provider_change_request_document_id,
                    "document_observation_id": row["document_observation_id"],
                    "parsed_result_uuidv4": row["parsed_result_uuidv4"],
                    "thread_parsed_result_uuidv4": thread["parsed_result_uuidv4"],
                    "body": row["body"],
                    "review_thread_provider_resource_id": thread[
                        "provider_resource_id"
                    ],
                    "thread": json.loads(thread["payload"]),
                    "review_position": json.loads(row["payload"]),
                },
            )
        return
    literal, path, documents_only = _query_filters(query, command, o)
    for pr in rows:
        query.check()
        payload = json.loads(pr["payload"] or "{}")
        state = pr_state(payload)
        if not _matches_pr_filters(query, pr, payload, state, o):
            continue
        code = None if documents_only else _code_observation(query, pr)
        if o.get("commit"):
            oid = GitOid.parse(o["commit"])
            if not code or not s.one(
                "SELECT 1 FROM current_code_commits WHERE code_listing_id=? AND object_format=? AND oid=?",
                (code["commit_code_listing_id"], oid.algorithm, oid.value),
            ):
                continue
        if path is not None:
            changes = (
                s.all(
                    "SELECT raw_path FROM current_code_file_changes WHERE code_listing_id=?",
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
            "repository_uuidv4": pr["repository_uuidv4"],
            "repository": pr["name"],
            "provider_change_request_number": pr["provider_change_request_number"],
            "change_request_kind": pr["change_request_kind"],
            "pr_id": pr["change_request_id"],
            "change_request_id": pr["change_request_id"],
            "repository_binding_id": pr["repository_binding_id"],
            "current_selected": pr["change_request_observation_id"] is not None,
            "change_request_observation_uuidv4": pr[
                "change_request_observation_uuidv4"
            ],
            "change_request_parsed_result_uuidv4": pr["parsed_result_uuidv4"],
            "change_request_parser_profile_uuidv4": pr["parser_profile_uuidv4"],
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
                "collections": [
                    {**dict(r), "state": _collection_state(query, r)}
                    for r in collections
                ],
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
                            "SELECT c.payload FROM current_code_commits c JOIN fetch_occurrences f USING(fetch_occurrence_id) WHERE c.code_listing_id=? ORDER BY f.ordinal,c.position,c.parsed_result_uuidv4",
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
                            "SELECT c.payload FROM current_code_file_changes c JOIN fetch_occurrences f USING(fetch_occurrence_id) WHERE c.code_listing_id=? ORDER BY f.ordinal,c.position,c.parsed_result_uuidv4",
                            (code["file_code_listing_id"],),
                        )
                    ]
                    if code
                    else []
                )
                item["observations"] = [
                    dict(r)
                    for r in s.all(
                        "SELECT o.change_request_observation_id,o.observed_at_us,o.parsed_result_uuidv4,r.parser_profile_uuidv4 FROM change_request_observations o JOIN usable_parsed_results r USING(parsed_result_uuidv4) WHERE o.change_request_id=? ORDER BY o.observed_at_us,o.change_request_observation_uuidv4",
                        (pr["change_request_id"],),
                    )
                ]
            yield (
                [
                    pr["repository_uuidv4"],
                    pr["provider_change_request_number"],
                    pr["change_request_id"],
                ],
                _bounded(item),
            )
        elif command == "pr timeline":
            for event in s.all(
                "SELECT * FROM current_change_request_events WHERE change_request_id=? ORDER BY ordinal,change_request_event_id",
                (pr["change_request_id"],),
            ):
                yield (
                    [
                        pr["repository_uuidv4"],
                        pr["provider_change_request_number"],
                        event["change_request_event_id"],
                    ],
                    {
                        **base,
                        "event_id": event["change_request_event_id"],
                        "change_request_event_uuidv4": event[
                            "change_request_event_uuidv4"
                        ],
                        "parsed_result_uuidv4": event["parsed_result_uuidv4"],
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
            current = selection == "current" and not o.get("observation")
            table = (
                "current_document_observations" if current else "document_observations"
            )
            docs = s.execute(
                f"SELECT obs.*,obs.observed_at_us document_observed_at_us,"
                "obs.parsed_at_us document_parsed_at_us,obs.metadata observation_metadata,"
                "r.parser_profile_uuidv4,b.body,"
                "EXISTS(SELECT 1 FROM current_document_observations c "
                "WHERE c.document_observation_id=obs.document_observation_id) current_selected "
                f"FROM {table} obs JOIN usable_parsed_results r USING(parsed_result_uuidv4) "
                "JOIN text_bodies b ON b.sha256=obs.text_body_sha256 "
                "WHERE obs.change_request_id=?"
                + (" AND obs.deleted=0" if current else "")
                + (" AND r.parser_profile_uuidv4=?" if o.get("parser_profile") else "")
                + " ORDER BY obs.kind,obs.provider_change_request_document_id,obs.document_observation_id",
                (pr["change_request_id"],)
                + ((o["parser_profile"],) if o.get("parser_profile") else ()),
            )
            for doc in docs:
                query.check()
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
                review_thread_provider_resource_id = doc[
                    "review_thread_provider_resource_id"
                ]
                thread = None
                if review_thread_provider_resource_id:
                    if current:
                        thread = s.one(
                            "SELECT payload,parsed_result_uuidv4 FROM current_review_thread_observations WHERE change_request_id=? AND provider_resource_id=?",
                            (
                                doc["change_request_id"],
                                review_thread_provider_resource_id,
                            ),
                        )
                    else:
                        # Historical projections do not attach a current thread
                        # interpretation from an unrelated parsing execution.
                        thread = s.one(
                            "SELECT payload,parsed_result_uuidv4 FROM review_thread_observations WHERE change_request_id=? AND provider_resource_id=? AND parsed_result_uuidv4=?",
                            (
                                doc["change_request_id"],
                                review_thread_provider_resource_id,
                                doc["parsed_result_uuidv4"],
                            ),
                        )
                thread_payload = json.loads(thread["payload"]) if thread else {}
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
                        pr["repository_uuidv4"],
                        pr["provider_change_request_number"],
                        *key,
                        doc["document_observation_id"],
                    ],
                    {
                        **base,
                        "document_kind": key.kind,
                        "provider_change_request_document_id": key.provider_change_request_document_id,
                        "document_observation_id": doc["document_observation_id"],
                        "document_observation_uuidv4": doc[
                            "document_observation_uuidv4"
                        ],
                        "text_body_sha256": digest,
                        "document_observed_at_us": doc["document_observed_at_us"],
                        "document_parsed_at_us": doc["document_parsed_at_us"],
                        "document_current_selected": bool(doc["current_selected"]),
                        "parsed_result_uuidv4": doc["parsed_result_uuidv4"],
                        "parser_profile_uuidv4": doc["parser_profile_uuidv4"],
                        "origin_key": doc["origin_key"],
                        "fetch_occurrence_id": doc["fetch_occurrence_id"],
                        "author": doc["author"],
                        "document_url": doc["url"],
                        "body": doc["body"],
                        "metadata": meta,
                        "thread": thread_payload or None,
                        "thread_parsed_result_uuidv4": thread["parsed_result_uuidv4"]
                        if thread
                        else None,
                        **(
                            {"review_position": meta}
                            if doc["kind"] == "review-comment"
                            else {}
                        ),
                    },
                )
