"""Pure provider projections for mutable resources and diagnostic archive inspection.

REST ``updated_at`` orders Issues and comments within their documented resource
clock. Review summaries have no such field; submitted_at is only submission time.
Missing properties are omitted so partial GraphQL projections cannot erase data.
"""

from __future__ import annotations

from repo_catalog.adapters.github.identity import database_resource_id
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import parse_iso8601_us

PARSER_MODULE = __name__
PARSER_VERSION = "1"


def resource_id(value, field="id"):
    try:
        ident = database_resource_id(value.get(field))
        if ident != str(int(ident)):
            raise ValueError("Noncanonical identifier")
        return ident
    except (ValueError, AttributeError):
        raise CatalogError(
            "CANONICAL_DOCUMENT_ID_MISSING",
            f"GitHub {field} must be a canonical positive database ID",
        ) from None


def _time(value, source, target, result):
    if source not in value:
        return
    raw = value[source]
    try:
        result[target] = None if raw is None else parse_iso8601_us(raw)
    except (ValueError, TypeError):
        raise CatalogError("API_SCHEMA", f"Invalid GitHub {source}") from None


def _common(value, context, observed_at_us, *, graphql=False, update_clock=True):
    if not isinstance(value, dict):
        raise CatalogError("API_SCHEMA", "Provider resource must be an object")
    result = {
        **context,
        "parser_module": PARSER_MODULE,
        "parser_version": PARSER_VERSION,
        "observed_at_us": observed_at_us,
        "acquisition_scope": context["acquisition_scope"],
    }
    for source, target in (("body", "body"), ("html_url", "url")):
        if graphql and source == "html_url":
            source = "url"
        if source in value:
            raw = value[source]
            if raw is not None and not isinstance(raw, str):
                raise CatalogError("API_SCHEMA", f"Malformed GitHub {source}")
            if target == "body" and raw is None:
                result["body_status"] = "provider-null"
            else:
                result[target] = raw
                if target == "body":
                    result["body_status"] = "present"
    source = "author" if graphql else "user"
    if source in value:
        author = value[source]
        if author is not None and (
            not isinstance(author, dict)
            or author.get("login") is not None
            and not isinstance(author["login"], str)
        ):
            raise CatalogError("API_SCHEMA", "Malformed GitHub author")
        result["author"] = author.get("login") if author else None
    if update_clock:
        _time(
            value,
            "updatedAt" if graphql else "updated_at",
            "provider_updated_at_us",
            result,
        )
    return result


def issue(value, context, observed_at_us):
    """Return an ordinary Issue projection; Issues API PR entries return None."""
    if not isinstance(value, dict):
        raise CatalogError("API_SCHEMA", "Issue must be an object")
    if "pull_request" in value:
        return None
    result = _common(value, context, observed_at_us)
    number = value.get("number")
    if type(number) is not int or not 0 < number < 1 << 63:
        raise CatalogError("API_SCHEMA", "Issue number must be positive")
    if not isinstance(value.get("title"), str) or value.get("state") not in (
        "open",
        "closed",
    ):
        raise CatalogError("API_SCHEMA", "Issue title/state missing")
    result.update(
        kind="issue",
        provider_resource_id=resource_id(value),
        provider_issue_number=number,
        title=value["title"],
        state=value["state"],
        provider_clock_scope="github-issue-updated-at",
        metadata={
            **result.get("metadata", {}),
            **{
                key: value[key]
                for key in (
                    "state_reason",
                    "created_at",
                    "closed_at",
                    "locked",
                    "active_lock_reason",
                    "labels",
                    "assignees",
                    "milestone",
                    "comments",
                    "reactions",
                )
                if key in value
            },
        },
    )
    return result


def issue_comment(value, context, observed_at_us, parent_provider_resource_id):
    result = _common(value, context, observed_at_us)
    result.update(
        kind="issue-comment",
        provider_resource_id=resource_id(value),
        parent_provider_resource_id=parent_provider_resource_id,
        provider_clock_scope="github-issue-comment-updated-at",
        metadata={
            **result.get("metadata", {}),
            **{key: value[key] for key in ("created_at", "reactions") if key in value},
        },
    )
    return result


def review(value, context, observed_at_us):
    result = _common(value, context, observed_at_us, update_clock=False)
    # GitHub's review endpoint does not provide a last-update clock. Ignore an
    # unknown extension named updated_at rather than treating it as authority.
    result.update(kind="review", provider_change_request_document_id=resource_id(value))
    if "state" in value:
        if value["state"] not in (
            "APPROVED",
            "CHANGES_REQUESTED",
            "COMMENTED",
            "DISMISSED",
            "PENDING",
        ):
            raise CatalogError("API_SCHEMA", "Malformed GitHub review state")
        result["state"] = value["state"]
    _time(value, "submitted_at", "submitted_at_us", result)
    if "commit_id" in value:
        result["target_commit_oid"] = _oid(value["commit_id"])
    result["metadata"] = {
        **result.get("metadata", {}),
        **{key: value[key] for key in ("node_id", "_links") if key in value},
    }
    return result


def _oid(value):
    if value is not None and (
        not isinstance(value, str)
        or len(value) not in (40, 64)
        or any(char not in "0123456789abcdefABCDEF" for char in value)
    ):
        raise CatalogError("API_SCHEMA", "Malformed GitHub commit OID")
    return value.lower() if value is not None else None


def review_comment(value, context, observed_at_us, *, graphql=False, thread=None):
    result = _common(value, context, observed_at_us, graphql=graphql)
    result.update(
        kind="review-comment",
        provider_change_request_document_id=resource_id(
            value, "fullDatabaseId" if graphql else "id"
        ),
        provider_clock_scope="github-review-comment-updated-at",
    )
    if thread is not None:
        result["review_thread_provider_resource_id"] = thread
    for source, target in (
        ("pull_request_review_id", "review_provider_resource_id"),
        ("in_reply_to_id", "in_reply_to_provider_resource_id"),
    ):
        if source in value:
            result[target] = (
                resource_id({"id": value[source]})
                if value[source] is not None
                else None
            )
    if graphql:
        if "pullRequestReview" in value:
            parent = value["pullRequestReview"]
            result["review_provider_resource_id"] = (
                resource_id(parent, "fullDatabaseId") if parent else None
            )
        if "replyTo" in value:
            parent = value["replyTo"]
            result["in_reply_to_provider_resource_id"] = (
                resource_id(parent, "fullDatabaseId") if parent else None
            )
        for source, target in (
            ("commit", "target_commit_oid"),
            ("originalCommit", "original_commit_oid"),
        ):
            if source in value:
                result[target] = (
                    _oid(value[source].get("oid")) if value[source] else None
                )
    else:
        for source, target in (
            ("commit_id", "target_commit_oid"),
            ("original_commit_id", "original_commit_oid"),
        ):
            if source in value:
                result[target] = _oid(value[source])
    for source, target in (
        ("path", "raw_path"),
        ("diffHunk" if graphql else "diff_hunk", "diff_hunk"),
        ("originalPosition" if graphql else "original_position", "original_position"),
        ("position", "current_position"),
    ):
        if source in value:
            raw = value[source]
            if target in ("raw_path", "diff_hunk"):
                if raw is not None and not isinstance(raw, str):
                    raise CatalogError("API_SCHEMA", f"Malformed GitHub {source}")
            elif raw is not None and (type(raw) is not int or not 0 <= raw < 1 << 63):
                raise CatalogError("API_SCHEMA", f"Malformed GitHub {source}")
            result[target] = raw
    metadata = {**result.get("metadata", {})}
    for source, target in (
        ("line", "line"),
        ("originalLine" if graphql else "original_line", "original_line"),
        ("side", "side"),
        ("start_line", "start_line"),
        ("original_start_line", "original_start_line"),
        ("start_side", "start_side"),
        ("subject_type", "subject_type"),
        ("created_at", "created_at"),
    ):
        if source in value:
            metadata[target] = value[source]
    result["metadata"] = metadata
    return result
