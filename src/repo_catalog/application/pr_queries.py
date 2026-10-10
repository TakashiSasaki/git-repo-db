"""Offline PR queries over typed current resources and exact code targets."""

from __future__ import annotations

import json

from repo_catalog.domain.document import verify_text_body
from repo_catalog.domain.models import CatalogError, path_fields


def pr_state(state):
    if state.get("merged"):
        return "merged"
    return state.get("state") or "unknown"


def _collection_boundary(query, collection_id):
    return query.s.one(
        "SELECT max(observed_at_us) FROM (SELECT observed_at_us FROM current_collection_pages WHERE fetch_collection_id=? UNION ALL SELECT observed_at_us FROM completion_markers WHERE fetch_collection_id=?)",
        (collection_id, collection_id),
    )[0]


def _latest_collections(query, rows):
    candidates, latest = [], None
    for row in rows:
        boundary = _collection_boundary(query, row["fetch_collection_id"])
        if boundary is not None and (latest is None or boundary > latest):
            candidates, latest = [row], boundary
        elif boundary is not None and boundary == latest:
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
    graph = _collection_proof_graph(query)
    boundary = _collection_boundary(query, row["fetch_collection_id"])
    markers = [
        m
        for m in graph.matching(
            "completion_markers",
            ("fetch_collection_id",),
            (row["fetch_collection_id"],),
        )
        if m["observed_at_us"] == boundary
    ]
    if not markers:
        return "partial" if boundary is not None else "unknown"
    states = {m["asserted_state"] for m in markers}
    if len(states) != 1:
        return "conflict"
    if states != {"complete"}:
        return next(iter(states))
    for marker in markers:
        required = graph.proof_requirements("completion_markers", marker)
        if required is None:
            return "unknown"
        if any(
            query.s.one(
                "SELECT 1 FROM exchange_staging WHERE record_key=? AND reason LIKE 'conflict:%'",
                (key,),
            )
            for key in required | {graph.key("completion_markers", marker)}
        ):
            return "conflict"
    return "complete"


def _scope_rows(query, command, options):
    repositories = [r["repository_uuidv4"] for r in query.repos(options)]
    if command in {
        "pr show",
        "pr documents",
        "pr threads",
        "pr thread",
        "pr code",
        "pr events",
        "pr timeline",
    }:
        query.single_repo(options)
    where = (
        "p.repository_uuidv4 IN (" + ",".join("?" for _ in repositories) + ")"
        if repositories
        else "0"
    )
    values = list(repositories)
    number = options.get(
        "provider_change_request_number", options.get("number", options.get("pr"))
    )
    if number is not None:
        if type(number) is not int or number <= 0:
            raise CatalogError("INVALID_ARGUMENT", "PR number must be positive")
        where += " AND p.provider_change_request_number=?"
        values.append(number)
    if options.get("change_request_kind"):
        where += " AND p.change_request_kind=?"
        values.append(options["change_request_kind"])
    if options.get("binding"):
        where += " AND p.repository_binding_id=?"
        values.append(options["binding"])
    rows = query.s.all(
        "SELECT p.*,r.name FROM change_requests p JOIN repositories r USING(repository_uuidv4) WHERE "
        + where
        + " ORDER BY p.repository_uuidv4,p.provider_change_request_number,p.change_request_id",
        values,
    )
    if command in {
        "pr show",
        "pr documents",
        "pr threads",
        "pr thread",
        "pr code",
        "pr events",
        "pr timeline",
    }:
        if number is None:
            raise CatalogError("INVALID_ARGUMENT", "An explicit PR number is required")
        if not rows:
            raise CatalogError("NOT_FOUND", "PR not found")
        if len(rows) > 1:
            raise CatalogError(
                "INVALID_ARGUMENT", "PR number is ambiguous; select a binding"
            )
    return rows


def _state(query, pr):
    row = query.s.one(
        "SELECT * FROM eligible_change_request_state WHERE change_request_id=?",
        (pr["change_request_id"],),
    )
    return dict(row) if row else None


def _document_fields(row):
    fields = dict(row)
    body = fields.pop("body", None)
    length = fields.pop("body_byte_length", None)
    digest = fields.get("text_body_sha256")
    verify_text_body(body, digest, length)
    fields["text_body_sha256"] = digest.hex() if digest is not None else None
    fields["body"] = body
    fields["resource_lifecycle"] = "current"
    fields["resource_kind"] = fields["kind"]
    fields["document_kind"] = fields["kind"]
    if fields["kind"] == "review":
        fields["review_state"] = fields.get("state")
    for column, output in (
        ("metadata", "metadata"),
        ("field_evidence_json", "field_evidence"),
        ("acquisition_scope_json", "acquisition_scope"),
    ):
        fields[output] = json.loads(fields.pop(column))
    for key, value in tuple(fields.items()):
        if isinstance(value, bytes):
            if key == "raw_path":
                fields.update(path_fields(value))
                fields.pop(key)
            else:
                fields[key] = value.hex()
    return fields


def _document_rows(query, pr, options):
    kind = options.get("document_kind")
    conditions = "r.change_request_id=? AND r.deleted=0"
    values = [pr["change_request_id"]]
    if kind:
        conditions += " AND r.kind=?"
        values.append(kind)
    for table in ("eligible_document_state", "eligible_review_resources"):
        for row in query.s.execute(
            f"SELECT r.*,b.body,b.byte_length body_byte_length FROM {table} r LEFT JOIN text_bodies b ON b.sha256=r.text_body_sha256 WHERE {conditions} ORDER BY r.kind,r.provider_change_request_document_id",
            values,
        ):
            if (
                options.get("document_author")
                and row["author"] != options["document_author"]
            ):
                continue
            if options.get("thread") and (
                table != "eligible_review_resources"
                or row["review_thread_provider_resource_id"] != options["thread"]
            ):
                continue
            yield row


def _code_observation(query, pr):
    state = _state(query, pr)
    if state is None:
        return None
    rows = query.s.all(
        "SELECT * FROM code_assessments WHERE change_request_id=? AND object_format IS ? AND head_oid IS ? AND base_oid IS ? ORDER BY observed_at_us DESC,code_assessment_id",
        (
            pr["change_request_id"],
            state["object_format"],
            state["head_oid"],
            state["base_oid"],
        ),
    )
    if not rows:
        return None
    latest = rows[0]["observed_at_us"]
    selected = [dict(row) for row in rows if row["observed_at_us"] == latest]
    signatures = {
        json.dumps(
            {
                k: v.hex() if isinstance(v, bytes) else v
                for k, v in row.items()
                if k
                not in {
                    "code_assessment_id",
                    "observed_at_us",
                    "parser_module",
                    "parser_version",
                }
            },
            sort_keys=True,
        )
        for row in selected
    }
    return selected[0] if len(signatures) == 1 else None


def code_role_gaps(store, pr, code, *, check):
    required = {
        role: (code["object_format"], code[role + "_oid"])
        for role in ("head", "base")
        if code[role + "_oid"] is not None
    }
    declared = json.loads(code.get("details_json", "{}")).get("expected_roles", {})
    if not isinstance(declared, dict):
        yield {
            "reason": "code_role_targets_unresolved",
            "code_assessment_id": code["code_assessment_id"],
        }
        return
    for role, oid in declared.items():
        try:
            target = (code["object_format"], bytes.fromhex(oid))
        except (ValueError, TypeError):
            yield {"reason": "code_role_targets_unresolved", "role": role}
            continue
        if role in required and required[role] != target:
            yield {"reason": "code_role_target_conflict", "role": role}
        required[role] = target
    for target in store.execute(
        "SELECT role,object_format,oid FROM code_acquisitions WHERE code_assessment_id=?",
        (code["code_assessment_id"],),
    ):
        check()
        pair = (target["object_format"], target["oid"])
        if target["role"] in required and required[target["role"]] != pair:
            yield {"reason": "code_role_target_conflict", "role": target["role"]}
        required[target["role"]] = pair
    links = {
        (r["role"], r["object_format"], r["oid"])
        for r in store.execute(
            "SELECT a.role,a.object_format,a.oid FROM code_acquisitions a JOIN acquisition_roots r USING(acquisition_root_id) JOIN available_git_objects g ON g.object_format=a.object_format AND g.oid=a.oid WHERE a.code_assessment_id=? AND r.repository_uuidv4=? AND r.complete=1 AND r.object_format=a.object_format AND r.oid=a.oid AND (r.expected_oid IS NULL OR r.expected_oid=a.oid) AND g.type='commit'",
            (code["code_assessment_id"], pr["repository_uuidv4"]),
        )
    }
    for role, (fmt, oid) in sorted(required.items()):
        check()
        if (role, fmt, oid) not in links:
            yield {
                "reason": "code_role_acquisition_missing",
                "code_assessment_id": code["code_assessment_id"],
                "role": role,
                "expected_oid": fmt + ":" + oid.hex(),
            }


def prepare_pr_coverage(query, command, options):
    """Evaluate complete requested scope before result/byte pagination."""
    if (
        options.get("observation")
        or options.get("observations")
        or options.get("parser_profile")
        or command == "pr observations"
    ):
        raise CatalogError(
            "RETIRED_API_HISTORY",
            "PR edit history and parser-profile selection are retired",
        )
    from repo_catalog.application.repository_identity import pr_applicable
    from repo_catalog.domain.pr_scope import document_scope_includes

    documents_only = command in {
        "pr documents",
        "search pr",
        "pr thread",
        "pr threads",
    } and not any(options.get(k) is not None for k in ("commit", "path", "path_b64"))
    current_only_review = command in {"pr documents", "search pr"} and options.get(
        "document_kind"
    ) in {"review", "review-comment"}
    if command != "pr thread":
        for repo in query.repos(options):
            if not pr_applicable(query.s, repo["repository_uuidv4"]):
                continue
            summary_kind = "pr-documents" if documents_only else "pr"
            summary = query.s.one(
                "SELECT coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id IS NULL AND kind=?",
                (repo["repository_uuidv4"], summary_kind),
            )
            if current_only_review and summary is None:
                if any(
                    options.get(key) is not None
                    for key in ("provider_change_request_number", "number", "pr")
                ):
                    continue
                summary = query.s.one(
                    "SELECT coverage_state FROM current_coverage WHERE repository_uuidv4=? AND change_request_id IS NULL AND kind='pr'",
                    (repo["repository_uuidv4"],),
                )
            if summary is None or summary[0] not in {"complete", "not_applicable"}:
                query.coverage.add(
                    "pr",
                    "collection_incomplete",
                    repository_uuidv4=repo["repository_uuidv4"],
                    scope_kind=summary_kind,
                )
    for pr in _scope_rows(query, command, options):
        query.check()
        state = _state(query, pr)
        if state is None and not current_only_review:
            query.coverage.add(
                "pr",
                "current_resource_unresolved",
                change_request_id=pr["change_request_id"],
            )
        kinds = (
            {"review"}
            if options.get("document_kind") == "review"
            else {
                "review-comment",
                "review-comment-incremental",
                "threads",
                "thread-comments",
            }
            if current_only_review
            else None
        )
        if command == "pr thread":
            thread = options.get("thread", options.get("provider_resource_id"))
            if not thread:
                raise CatalogError("INVALID_ARGUMENT", "Select a provider thread ID")
            root = query.s.one(
                "SELECT * FROM eligible_review_thread_state WHERE change_request_id=? AND provider_resource_id=?",
                (pr["change_request_id"], thread),
            )
            if root is None:
                query.coverage.add(
                    "pr",
                    "thread_current_unresolved",
                    change_request_id=pr["change_request_id"],
                    provider_resource_id=thread,
                )
            roots = query.s.all(
                "SELECT * FROM fetch_collections WHERE change_request_id=? AND kind='threads'",
                (pr["change_request_id"],),
            )
            latest = _latest_collections(query, roots)
            if not latest or any(
                _collection_state(query, row) != "complete" for row in latest
            ):
                query.coverage.add(
                    "pr",
                    "thread_listing_incomplete",
                    change_request_id=pr["change_request_id"],
                    provider_resource_id=thread,
                )
            for row in query.s.execute(
                "SELECT r.provider_change_request_document_id FROM review_resources r WHERE r.change_request_id=? AND r.kind='review-comment' AND r.review_thread_provider_resource_id=? AND r.deleted=0 AND (r.body_status IN ('missing','inaccessible') OR NOT EXISTS(SELECT 1 FROM eligible_review_resources e WHERE e.change_request_id=r.change_request_id AND e.kind=r.kind AND e.provider_change_request_document_id=r.provider_change_request_document_id)) ORDER BY r.provider_change_request_document_id",
                (pr["change_request_id"], thread),
            ):
                query.coverage.add(
                    "pr",
                    "document_body_missing",
                    change_request_id=pr["change_request_id"],
                    document_kind="review-comment",
                    provider_change_request_document_id=row[0],
                )
            continue
        for scope in query.s.execute(
            "SELECT * FROM current_coverage WHERE repository_uuidv4=? AND change_request_id=?",
            (pr["repository_uuidv4"], pr["change_request_id"]),
        ):
            if (
                documents_only
                and not document_scope_includes(scope["kind"])
                or kinds is not None
                and scope["kind"] not in kinds
                and scope["kind"]
                in {
                    "pr-title",
                    "pr-body",
                    "issue-comment",
                    "issue-comment-incremental",
                    "comments",
                    "review",
                    "review-comment",
                    "review-comment-incremental",
                    "threads",
                    "thread-comments",
                }
            ):
                continue
            if scope["coverage_state"] not in {"complete", "not_applicable"}:
                query.coverage.add(
                    "pr",
                    "saved_scope_incomplete",
                    **{
                        ("scope_kind" if k == "kind" else k): v
                        for k, v in dict(scope).items()
                    },
                )
        grouped = {}
        for collection in query.s.all(
            "SELECT * FROM fetch_collections WHERE change_request_id=?",
            (pr["change_request_id"],),
        ):
            if (
                documents_only
                and not document_scope_includes(collection["kind"])
                or kinds is not None
                and collection["kind"] not in kinds
                and collection["kind"]
                in {
                    "pr-title",
                    "pr-body",
                    "issue-comment",
                    "issue-comment-incremental",
                    "comments",
                    "review",
                    "review-comment",
                    "review-comment-incremental",
                    "threads",
                    "thread-comments",
                }
            ):
                continue
            grouped.setdefault(collection["kind"], []).append(collection)
        if current_only_review:
            family = options["document_kind"]
            if family not in grouped:
                query.coverage.add(
                    "pr",
                    "collection_incomplete",
                    collection_kind=family,
                    change_request_id=pr["change_request_id"],
                )
        for kind, rows in grouped.items():
            latest = _latest_collections(query, rows)
            states = {_collection_state(query, row) for row in latest}
            if states != {"complete"}:
                query.coverage.add(
                    "pr",
                    "collection_incomplete",
                    collection_kind=kind,
                    change_request_id=pr["change_request_id"],
                    states=sorted(states),
                    **(
                        {"fetch_collection_id": latest[0]["fetch_collection_id"]}
                        if len(latest) == 1
                        else {}
                    ),
                )
        for row in query.s.execute(
            "SELECT table_name,reason FROM exchange_staging WHERE repository_uuidv4=? AND reason='current_state:conflict' AND json_extract(record_json,'$.change_request_id')=?",
            (pr["repository_uuidv4"], pr["change_request_id"]),
        ):
            if kinds is None or row["table_name"] == "review_resources":
                query.coverage.add(
                    "pr",
                    "current_resource_unresolved",
                    resource_family=row["table_name"],
                    change_request_id=pr["change_request_id"],
                )
        if command in {"pr documents", "search pr"}:
            for table in ("document_state", "review_resources"):
                for row in query.s.execute(
                    f"SELECT kind,provider_change_request_document_id FROM {table} WHERE change_request_id=? AND deleted=0 AND body_status IN ('missing','inaccessible') ORDER BY kind,provider_change_request_document_id",
                    (pr["change_request_id"],),
                ):
                    if (
                        not options.get("document_kind")
                        or row["kind"] == options["document_kind"]
                    ):
                        query.coverage.add(
                            "pr",
                            "document_body_missing",
                            change_request_id=pr["change_request_id"],
                            document_kind=row["kind"],
                            provider_change_request_document_id=row[
                                "provider_change_request_document_id"
                            ],
                        )
        if not documents_only:
            code = _code_observation(query, pr)
            expects_code = bool(
                state
                and (state["head_oid"] is not None or state["base_oid"] is not None)
            ) or query.s.one(
                "SELECT 1 FROM code_assessments WHERE change_request_id=? UNION ALL SELECT 1 FROM code_listings WHERE change_request_id=? LIMIT 1",
                (pr["change_request_id"], pr["change_request_id"]),
            )
            if code is None and expects_code:
                query.coverage.add(
                    "pr",
                    "code_assessment_missing",
                    change_request_id=pr["change_request_id"],
                )
            elif code is not None and code["state"] != "complete":
                query.coverage.add(
                    "pr",
                    "code_assessment_incomplete",
                    code_assessment_id=code["code_assessment_id"],
                )
            elif code:
                for gap in code_role_gaps(query.s, pr, code, check=query.check):
                    query.coverage.add(
                        "pr", change_request_id=pr["change_request_id"], **gap
                    )


def _matches(state, options):
    wanted = options.get("state", "all")
    if wanted not in {"all", "open", "closed", "merged"}:
        raise CatalogError("INVALID_ARGUMENT", "Invalid PR state")
    if wanted != "all" and pr_state(state) != wanted:
        return False
    draft = options.get("draft", "any")
    if draft != "any" and bool(state.get("draft")) != (draft in {"yes", "true"}):
        return False
    return not options.get("author") or state.get("author") == options["author"]


def pr_query(query, command, options):
    literal = query.literal(options) if command == "search pr" else None
    for pr in _scope_rows(query, command, options):
        query.check()
        state = _state(query, pr)
        if state is not None and not _matches(state, options):
            continue
        if state is None and (
            options.get("state", "all") != "all"
            or options.get("draft", "any") != "any"
            or options.get("author")
        ):
            continue
        if options.get("reviewer") and not query.s.one(
            "SELECT 1 FROM eligible_review_resources WHERE change_request_id=? AND kind='review' AND author=? AND deleted=0",
            (pr["change_request_id"], options["reviewer"]),
        ):
            continue
        if any(options.get(k) is not None for k in ("commit", "path", "path_b64")):
            code = _code_observation(query, pr)
            if code is None or code["state"] != "complete":
                continue
            if options.get("commit"):
                from repo_catalog.domain.models import GitOid

                oid = GitOid.parse(options["commit"])
                if not query.s.one(
                    "SELECT 1 FROM code_commits WHERE code_listing_id=? AND object_format=? AND oid=?",
                    (code["commit_code_listing_id"], oid.algorithm, oid.value),
                ):
                    continue
            if options.get("path") is not None or options.get("path_b64") is not None:
                from repo_catalog.application.target_queries import TargetQueryService

                raw_path = TargetQueryService._path(options)
                if not query.s.one(
                    "SELECT 1 FROM code_file_changes WHERE code_listing_id=? AND raw_path=?",
                    (code["file_code_listing_id"], raw_path),
                ):
                    continue
        key = [
            pr["repository_uuidv4"],
            pr["provider_change_request_number"],
            pr["change_request_id"],
        ]
        if command in {"pr list", "pr show"}:
            if state is None:
                yield key, {**dict(pr), "current_state_status": "unavailable"}
                continue
            fields = {
                **dict(pr),
                **dict(state),
                "metadata": json.loads(state["metadata"]),
                "field_evidence": json.loads(state["field_evidence_json"]),
                "resource_lifecycle": "current",
            }
            fields.pop("field_evidence_json")
            fields["acquisition_scope"] = json.loads(
                fields.pop("acquisition_scope_json")
            )
            for column in ("head_oid", "base_oid", "merge_oid"):
                if fields[column] is not None:
                    fields[column] = (
                        fields["object_format"] + ":" + fields[column].hex()
                    )
            for row in _document_rows(query, pr, {}):
                if row["kind"] in {"pr-title", "pr-body"}:
                    document = _document_fields(row)
                    fields["title" if row["kind"] == "pr-title" else "body"] = document[
                        "body"
                    ]
            yield key, fields
        elif command in {"pr documents", "search pr", "pr thread"}:
            document_options = dict(options)
            if command == "pr thread":
                document_options["document_kind"] = "review-comment"
                document_options["thread"] = options.get(
                    "thread", options.get("provider_resource_id")
                )
            for row in _document_rows(query, pr, document_options):
                fields = _document_fields(row)
                fields["number"] = pr["provider_change_request_number"]
                fields["provider_change_request_number"] = pr[
                    "provider_change_request_number"
                ]
                if literal is not None and not query.literal_match(
                    "pr",
                    fields["text_body_sha256"] or "",
                    fields["body"] or "",
                    literal,
                ):
                    continue
                yield (
                    key + [row["kind"], row["provider_change_request_document_id"]],
                    fields,
                )
        elif command == "pr threads":
            for row in query.s.execute(
                "SELECT * FROM eligible_review_thread_state WHERE change_request_id=? ORDER BY provider_resource_id",
                (pr["change_request_id"],),
            ):
                if (
                    options.get("thread")
                    and row["provider_resource_id"] != options["thread"]
                ):
                    continue
                if any(
                    options.get(field, "any") != "any"
                    and bool(row[field]) != (options[field] in {"yes", "true"})
                    for field in ("resolved", "outdated")
                ):
                    continue
                fields = dict(row)
                fields["metadata"] = json.loads(fields["metadata"])
                fields["field_evidence"] = json.loads(fields.pop("field_evidence_json"))
                fields["acquisition_scope"] = json.loads(
                    fields.pop("acquisition_scope_json")
                )
                if fields["raw_path"] is not None:
                    fields.update(path_fields(fields.pop("raw_path")))
                for column in ("commit_oid", "original_commit_oid"):
                    if fields[column] is not None:
                        fields[column] = (
                            fields["object_format"] + ":" + fields[column].hex()
                        )
                fields["resource_lifecycle"] = "current"
                yield key + [row["provider_resource_id"]], fields
        elif command in {"pr events", "pr timeline"}:
            for row in query.s.execute(
                "SELECT * FROM change_request_events WHERE change_request_id=? ORDER BY created_at_us,change_request_event_uuidv4",
                (pr["change_request_id"],),
            ):
                fields = dict(row)
                fields["metadata"] = json.loads(fields["metadata"])
                if fields["commit_oid"] is not None:
                    fields["commit_oid"] = (
                        fields["object_format"] + ":" + fields["commit_oid"].hex()
                    )
                yield (
                    key
                    + [row["created_at_us"] or 0, row["change_request_event_uuidv4"]],
                    fields,
                )
        elif command == "pr code":
            code = _code_observation(query, pr)
            if code is None:
                continue
            for kind, table, column in (
                ("commits", "code_commits", "commit_code_listing_id"),
                ("files", "code_file_changes", "file_code_listing_id"),
            ):
                for row in query.s.execute(
                    f"SELECT * FROM {table} WHERE code_listing_id=? ORDER BY position",
                    (code[column],),
                ):
                    fields = dict(row)
                    fields["kind"] = kind
                    fields["code_assessment_id"] = code["code_assessment_id"]
                    fields["metadata"] = json.loads(fields["metadata"])
                    if fields.get("oid") is not None:
                        fields["oid"] = (
                            fields["object_format"] + ":" + fields["oid"].hex()
                        )
                    if fields.get("raw_path") is not None:
                        fields.update(path_fields(fields.pop("raw_path")))
                    if fields.get("previous_path") is not None:
                        fields["previous_path_b64"] = (
                            __import__("base64")
                            .b64encode(fields.pop("previous_path"))
                            .decode()
                        )
                    yield key + [kind, row["position"]], fields
        else:
            raise CatalogError("INVALID_ARGUMENT", "Unknown PR query")
