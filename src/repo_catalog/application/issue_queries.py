"""Offline ordinary Issue queries over admitted current resources."""

from __future__ import annotations

import hashlib
import json

from repo_catalog.domain.document import verify_text_body
from repo_catalog.domain.models import CatalogError


def _scope(query, command, options):
    if options.get("parser_profile"):
        raise CatalogError(
            "INVALID_ARGUMENT",
            "Current Issue resources use module/version attribution; parser profiles select historical facts",
        )
    repositories = [r["repository_uuidv4"] for r in query.repos(options)]
    if command in ("issue show", "issue comments"):
        query.single_repo(options)
    conditions = [
        "i.repository_uuidv4 IN (" + ",".join("?" for _ in repositories) + ")"
        if repositories
        else "0",
        "i.kind='issue'",
    ]
    values = list(repositories)
    for option, column in (
        ("provider_issue_number", "provider_issue_number"),
        ("provider_resource_id", "provider_resource_id"),
        ("binding", "repository_binding_id"),
    ):
        value = options.get(option)
        if value is None:
            continue
        if option == "provider_issue_number" and (type(value) is not int or value <= 0):
            raise CatalogError("INVALID_ARGUMENT", "Issue number must be positive")
        conditions.append(f"i.{column}=?")
        values.append(value)
    rows = query.s.execute(
        "SELECT i.*,r.name FROM issue_resources i JOIN repositories r "
        "USING(repository_uuidv4) WHERE "
        + " AND ".join(conditions)
        + " ORDER BY i.repository_uuidv4,i.provider_issue_number,"
        "i.service_instance_uuidv4,i.provider_resource_id",
        values,
    )
    if command in ("issue show", "issue comments"):
        if all(
            options.get(field) is None
            for field in ("provider_issue_number", "provider_resource_id")
        ):
            raise CatalogError(
                "INVALID_ARGUMENT", "Select an Issue number or provider ID"
            )
        selected = rows.fetchmany(2)
        if not selected:
            raise CatalogError("NOT_FOUND", "Issue not found")
        if len(selected) != 1:
            raise CatalogError(
                "INVALID_ARGUMENT", "Issue number is ambiguous; select --binding"
            )
        return selected
    return rows


def _eligible(query, row):
    return query.s.one(
        "SELECT i.*,b.body,b.byte_length body_byte_length FROM eligible_issue_resources i "
        "LEFT JOIN text_bodies b ON b.sha256=i.text_body_sha256 "
        "WHERE i.service_instance_uuidv4=? AND i.kind=? AND i.provider_resource_id=? "
        "AND i.deleted=0",
        (row["service_instance_uuidv4"], row["kind"], row["provider_resource_id"]),
    )


def _fields(row, repository):
    verify_text_body(row["body"], row["text_body_sha256"], row["body_byte_length"])
    return {
        "repository_uuidv4": row["repository_uuidv4"],
        "repository": repository,
        "repository_binding_id": row["repository_binding_id"],
        "service_instance_uuidv4": row["service_instance_uuidv4"],
        "resource_kind": row["kind"],
        "provider_resource_id": row["provider_resource_id"],
        "parent_provider_resource_id": row["parent_provider_resource_id"],
        "provider_issue_number": row["provider_issue_number"],
        "title": row["title"],
        "state": row["state"],
        "author": row["author"],
        "url": row["url"],
        "body": row["body"],
        "text_body_sha256": row["text_body_sha256"].hex()
        if row["text_body_sha256"] is not None
        else None,
        "body_status": row["body_status"],
        "provider_updated_at_us": row["provider_updated_at_us"],
        "observed_at_us": row["observed_at_us"],
        "last_checked_at_us": row["last_checked_at_us"],
        "parsed_at_us": row["parsed_at_us"],
        "parser_module": row["parser_module"],
        "parser_version": row["parser_version"],
        "field_evidence": json.loads(row["field_evidence_json"]),
        "metadata": json.loads(row["metadata"]),
        "resource_lifecycle": "current",
    }


def prepare_issue_coverage(query, command, options):
    for repository in query.repos(options):
        query.check()
        scope = query.s.one(
            "SELECT coverage_state FROM current_coverage "
            "WHERE repository_uuidv4=? AND change_request_id IS NULL AND kind='issue'",
            (repository["repository_uuidv4"],),
        )
        if scope is None or scope[0] not in ("complete", "not_applicable"):
            query.coverage.add(
                "issue",
                "collection_incomplete",
                repository_uuidv4=repository["repository_uuidv4"],
            )
    for issue in _scope(query, command, options):
        query.check()
        if not issue["deleted"] and _eligible(query, issue) is None:
            query.coverage.add(
                "issue",
                "current_resource_unresolved",
                service_instance_uuidv4=issue["service_instance_uuidv4"],
                resource_kind=issue["kind"],
                provider_resource_id=issue["provider_resource_id"],
            )
        if not issue["deleted"] and issue["body_status"] in ("missing", "inaccessible"):
            query.coverage.add(
                "issue",
                "body_unavailable",
                resource_kind=issue["kind"],
                provider_resource_id=issue["provider_resource_id"],
                body_status=issue["body_status"],
            )
        candidates = (
            query.s.execute(
                "SELECT * FROM issue_resources WHERE service_instance_uuidv4=? "
                "AND kind='issue-comment' AND parent_provider_resource_id=?",
                (issue["service_instance_uuidv4"], issue["provider_resource_id"]),
            )
            if command == "issue comments" or command == "search issue"
            else ()
        )
        for row in candidates:
            query.check()
            if not row["deleted"] and _eligible(query, row) is None:
                query.coverage.add(
                    "issue",
                    "current_resource_unresolved",
                    service_instance_uuidv4=row["service_instance_uuidv4"],
                    resource_kind=row["kind"],
                    provider_resource_id=row["provider_resource_id"],
                )
            elif not row["deleted"] and row["body_status"] in (
                "missing",
                "inaccessible",
            ):
                query.coverage.add(
                    "issue",
                    "body_unavailable",
                    resource_kind=row["kind"],
                    provider_resource_id=row["provider_resource_id"],
                    body_status=row["body_status"],
                )


def issue_query(query, command, options):
    literal = query.literal(options) if command == "search issue" else None
    state = options.get("state", "all")
    if state not in ("all", "open", "closed"):
        raise CatalogError(
            "INVALID_ARGUMENT", "Issue state must be all, open or closed"
        )
    for identity in _scope(query, command, options):
        query.check()
        issue = _eligible(query, identity)
        if issue is None:
            continue
        if state != "all" and issue["state"] != state:
            continue
        if options.get("author") and issue["author"] != options["author"]:
            continue
        rows = (
            query.s.execute(
                "SELECT i.*,b.body,b.byte_length body_byte_length FROM eligible_issue_resources i "
                "LEFT JOIN text_bodies b ON b.sha256=i.text_body_sha256 "
                "WHERE i.service_instance_uuidv4=? AND i.kind='issue-comment' "
                "AND i.parent_provider_resource_id=? AND i.deleted=0 "
                "ORDER BY i.provider_resource_id",
                (issue["service_instance_uuidv4"], issue["provider_resource_id"]),
            )
            if command in ("issue comments", "search issue")
            else ()
        )
        if command != "issue comments":
            yield from _project(query, issue, identity["name"], options, literal)
        for comment in rows:
            query.check()
            yield from _project(query, comment, identity["name"], options, literal)


def _project(query, row, repository, options, literal):
    if options.get("document_author") and row["author"] != options["document_author"]:
        return
    key = [
        row["repository_uuidv4"],
        row["provider_issue_number"],
        row["service_instance_uuidv4"],
        row["parent_provider_resource_id"] or row["provider_resource_id"],
        row["kind"],
        row["provider_resource_id"],
    ]
    fields = _fields(row, repository)
    if literal is None:
        yield key, fields
        return
    for field in ("title", "body"):
        text = row[field]
        if text is None:
            continue
        digest = hashlib.sha256(text.encode("utf8")).hexdigest()
        if query.literal_match("issue", digest, text, literal):
            yield (
                key + [0 if field == "title" else 1],
                {
                    **fields,
                    "field": field,
                    "text": text,
                },
            )
