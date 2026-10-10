"""Pure live provider projections for mutable resources.

REST ``updated_at`` orders Issues and comments within their documented resource
clock. Review summaries have no such field; submitted_at is only submission time.
Missing properties are omitted so partial GraphQL projections cannot erase data.
"""

from __future__ import annotations

from repo_catalog.adapters.github.identity import database_resource_id
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import parse_iso8601_us

PARSER_MODULE = __name__
PARSER_VERSION = "3"


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
        if author is None:
            result["author"] = None
        elif "login" in author:
            result["author"] = author["login"]
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
        metadata=modeled_metadata(
            value,
            (
                "state_reason",
                "created_at",
                "closed_at",
                "locked",
                "active_lock_reason",
                "comments",
            ),
        ),
    )
    return result


def issue_comment(value, context, observed_at_us, parent_provider_resource_id):
    result = _common(value, context, observed_at_us)
    result.update(
        kind="issue-comment",
        provider_resource_id=resource_id(value),
        parent_provider_resource_id=parent_provider_resource_id,
        provider_clock_scope="github-issue-comment-updated-at",
        metadata=modeled_metadata(value, ("created_at",)),
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
    metadata = {"node_id": value["node_id"]} if "node_id" in value else {}
    if "_links" in value:
        links = value["_links"]
        if links is None:
            metadata["_links"] = None
        elif not isinstance(links, dict):
            raise CatalogError("API_SCHEMA", "Malformed GitHub review links")
        else:
            metadata["_links"] = {
                field: _select(links[field], ("href",))
                for field in ("self", "html", "pull_request")
                if field in links
            }
    result["metadata"] = metadata
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
            if parent is None:
                result["review_provider_resource_id"] = None
            elif not isinstance(parent, dict):
                raise CatalogError("API_SCHEMA", "Malformed GitHub pullRequestReview")
            elif "fullDatabaseId" in parent:
                result["review_provider_resource_id"] = resource_id(
                    parent, "fullDatabaseId"
                )
        if "replyTo" in value:
            parent = value["replyTo"]
            if parent is None:
                result["in_reply_to_provider_resource_id"] = None
            elif not isinstance(parent, dict):
                raise CatalogError("API_SCHEMA", "Malformed GitHub replyTo")
            elif "fullDatabaseId" in parent:
                result["in_reply_to_provider_resource_id"] = resource_id(
                    parent, "fullDatabaseId"
                )
        for source, target in (
            ("commit", "target_commit_oid"),
            ("originalCommit", "original_commit_oid"),
        ):
            if source in value:
                commit = value[source]
                if commit is None:
                    result[target] = None
                elif not isinstance(commit, dict):
                    raise CatalogError("API_SCHEMA", f"Malformed GitHub {source}")
                elif "oid" in commit:
                    result[target] = _oid(commit["oid"])
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


# Closed domain vocabularies deliberately omit API envelopes and unmodeled
# extensions. Nested values are projected too; naming a metadata field does not
# authorize an opaque copy of its provider object.
_ACTOR_FIELDS = ("id", "login", "type", "html_url")
_LABEL_FIELDS = ("id", "name", "color", "description", "default")
_REACTION_FIELDS = (
    "total_count",
    "+1",
    "-1",
    "laugh",
    "confused",
    "heart",
    "hooray",
    "eyes",
    "rocket",
)


def _select(value, fields):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CatalogError("API_SCHEMA", "Expected modeled metadata object")
    return {field: value[field] for field in fields if field in value}


def _actor(value):
    return _select(value, _ACTOR_FIELDS)


def _milestone(value):
    result = _select(
        value,
        (
            "id",
            "number",
            "title",
            "description",
            "state",
            "due_on",
            "created_at",
            "updated_at",
            "closed_at",
            "open_issues",
            "closed_issues",
            "html_url",
        ),
    )
    if result is not None and "creator" in value:
        result["creator"] = _actor(value["creator"])
    return result


def modeled_metadata(value, scalar_fields):
    result = {field: value[field] for field in scalar_fields if field in value}
    for name, projector in (
        ("labels", lambda item: _select(item, _LABEL_FIELDS)),
        ("assignees", _actor),
        ("requested_reviewers", _actor),
        (
            "requested_teams",
            lambda item: _select(
                item, ("id", "name", "slug", "description", "privacy", "html_url")
            ),
        ),
    ):
        if name in value:
            if value[name] is None:
                result[name] = None
            elif isinstance(value[name], list):
                result[name] = [projector(item) for item in value[name]]
            else:
                raise CatalogError("API_SCHEMA", f"Malformed GitHub {name}")
    if "milestone" in value:
        result["milestone"] = _milestone(value["milestone"])
    if "reactions" in value:
        result["reactions"] = _select(value["reactions"], _REACTION_FIELDS)
    return result


def pull_request(value, context, observed_at_us):
    result = _common(value, context, observed_at_us)
    # The documents are the sole title/body owners.
    for field in ("body", "body_status"):
        result.pop(field, None)
    result.update(
        kind="change-request",
        provider_resource_id=resource_id(value),
        provider_clock_scope="github-pr-updated-at",
    )
    for field in ("state", "draft", "merged", "locked"):
        if field in value:
            result[field] = value[field]
    for source, target in (
        ("created_at", "created_at_us"),
        ("closed_at", "closed_at_us"),
        ("merged_at", "merged_at_us"),
    ):
        _time(value, source, target, result)
    oids = []
    targets = {}
    for role in ("head", "base"):
        if role not in value:
            continue
        target = value[role]
        if target is None:
            result[role + "_oid"] = None
            result[role + "_ref"] = None
            targets[role] = None
            continue
        if not isinstance(target, dict):
            raise CatalogError("API_SCHEMA", f"Malformed PR {role}")
        if "sha" in target:
            oid = _oid(target["sha"])
            result[role + "_oid"] = oid
            if oid:
                oids.append(oid)
        if "ref" in target:
            result[role + "_ref"] = target["ref"]
        modeled = _select(target, ("label",))
        if "user" in target:
            modeled["user"] = _actor(target["user"])
        if "repo" in target:
            modeled["repository"] = _select(
                target["repo"],
                ("id", "name", "full_name", "html_url", "private", "default_branch"),
            )
        targets[role] = modeled
    if "merge_commit_sha" in value:
        result["merge_oid"] = _oid(value["merge_commit_sha"])
        if result["merge_oid"]:
            oids.append(result["merge_oid"])
    if oids:
        if len({len(oid) for oid in oids}) != 1:
            raise CatalogError("API_SCHEMA", "Mixed PR object formats")
        result["object_format"] = "sha256" if len(oids[0]) == 64 else "sha1"
    metadata = modeled_metadata(
        value,
        (
            "author_association",
            "active_lock_reason",
            "mergeable",
            "mergeable_state",
            "rebaseable",
            "maintainer_can_modify",
            "comments",
            "review_comments",
            "commits",
            "changed_files",
            "additions",
            "deletions",
        ),
    )
    if targets:
        metadata["targets"] = targets
    if "auto_merge" in value:
        item = _select(
            value["auto_merge"], ("merge_method", "commit_title", "commit_message")
        )
        if item is not None and "enabled_by" in value["auto_merge"]:
            item["enabled_by"] = _actor(value["auto_merge"]["enabled_by"])
        metadata["auto_merge"] = item
    if "merged_by" in value:
        metadata["merged_by"] = _actor(value["merged_by"])
    result["metadata"] = metadata
    return result


def document(value, context, observed_at_us, kind):
    result = _common(value, context, observed_at_us)
    result.update(
        kind=kind,
        provider_change_request_document_id=resource_id(value),
        provider_clock_scope="github-pr-updated-at"
        if kind in ("pr-title", "pr-body")
        else "github-issue-comment-updated-at",
    )
    if kind == "pr-title":
        result.pop("body", None)
        result.pop("body_status", None)
        if "title" in value:
            if not isinstance(value["title"], str):
                raise CatalogError("API_SCHEMA", "PR title must be text")
            result.update(body=value["title"], body_status="present")
    result["metadata"] = (
        modeled_metadata(value, ("created_at", "author_association"))
        if kind == "issue-comment"
        else {}
    )
    return result


def thread(value, context, observed_at_us):
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("id"), str)
        or not value["id"]
    ):
        raise CatalogError("API_SCHEMA", "Thread identity missing")
    result = {
        **context,
        "kind": "review-thread",
        "provider_resource_id": value["id"],
        "observed_at_us": observed_at_us,
        "parser_module": PARSER_MODULE,
        "parser_version": PARSER_VERSION,
    }
    for source, target in (
        ("isResolved", "resolved"),
        ("isOutdated", "outdated"),
        ("path", "raw_path"),
        ("line", "line"),
        ("startLine", "start_line"),
        ("originalLine", "original_line"),
        ("originalStartLine", "original_start_line"),
        ("diffSide", "side"),
        ("startDiffSide", "start_side"),
    ):
        if source in value:
            result[target] = value[source]
    result["metadata"] = {}
    return result


def repository_metadata(value):
    result = {
        field: value[field]
        for field in (
            "name",
            "full_name",
            "html_url",
            "ssh_url",
            "git_url",
            "private",
            "visibility",
            "archived",
            "disabled",
            "fork",
            "default_branch",
            "description",
            "homepage",
            "topics",
            "language",
            "created_at",
            "updated_at",
            "pushed_at",
            "size",
            "stargazers_count",
            "watchers_count",
            "forks_count",
            "open_issues_count",
            "has_issues",
            "has_projects",
            "has_wiki",
            "has_pages",
            "has_downloads",
            "has_discussions",
            "allow_forking",
            "is_template",
        )
        if field in value
    }
    if "owner" in value:
        result["owner"] = _actor(value["owner"])
    for field in ("parent", "source"):
        if field in value:
            result[field] = _select(value[field], ("id", "full_name", "html_url"))
    if "license" in value:
        result["license"] = _select(value["license"], ("key", "name", "spdx_id"))
    if "permissions" in value:
        result["permissions"] = _select(
            value["permissions"], ("admin", "maintain", "push", "triage", "pull")
        )
    if "security_and_analysis" in value:
        item = value["security_and_analysis"]
        result["security_and_analysis"] = (
            None
            if item is None
            else {
                key: _select(item[key], ("status",))
                for key in (
                    "advanced_security",
                    "secret_scanning",
                    "secret_scanning_push_protection",
                    "dependabot_security_updates",
                )
                if key in item
            }
        )
    return result


def timeline_event(value):
    result = modeled_metadata(
        value,
        (
            "event",
            "created_at",
            "submitted_at",
            "state",
            "body",
            "title",
            "message",
            "author_association",
            "commit_id",
            "lock_reason",
        ),
    )
    for field in ("actor", "user", "assignee", "assigner", "reviewer"):
        if field in value:
            result[field] = _actor(value[field])
    for field, projector in (
        ("label", lambda item: _select(item, _LABEL_FIELDS)),
        ("milestone", _milestone),
        ("rename", lambda item: _select(item, ("from", "to"))),
        ("requested_team", lambda item: _select(item, ("id", "name", "slug"))),
    ):
        if field in value:
            result[field] = projector(value[field])
    if "dismissed_review" in value:
        result["dismissed_review"] = _select(
            value["dismissed_review"],
            ("state", "review_id", "dismissal_message", "dismissal_commit_id"),
        )
    for field in ("before", "after"):
        if field in value:
            result[field] = (
                _select(value[field], ("sha",))
                if isinstance(value[field], dict)
                else value[field]
            )
    if "source" in value:
        source = _select(value["source"], ("type",))
        if source is not None and "issue" in value["source"]:
            source["issue"] = _select(
                value["source"]["issue"], ("id", "number", "html_url")
            )
        result["source"] = source
    for field in ("id", "pull_request_review_id"):
        if field in value:
            result[field] = value[field]
    return result


def code_commit_metadata(value):
    result = {key: value[key] for key in ("html_url",) if key in value}
    for field in ("author", "committer"):
        if field in value:
            result[field] = _actor(value[field])
    commit = value.get("commit")
    if commit is not None:
        if not isinstance(commit, dict):
            raise CatalogError("API_SCHEMA", "Malformed provider commit")
        data = _select(commit, ("message",))
        for field in ("author", "committer"):
            if field in commit:
                data[field] = _select(commit[field], ("name", "email", "date"))
        if "tree" in commit:
            data["tree"] = _select(commit["tree"], ("sha",))
        if "verification" in commit:
            data["verification"] = _select(
                commit["verification"],
                ("verified", "reason", "signature", "payload", "verified_at"),
            )
        result["commit"] = data
    if "parents" in value:
        if not isinstance(value["parents"], list):
            raise CatalogError("API_SCHEMA", "Malformed provider parents")
        result["parents"] = [_select(parent, ("sha",)) for parent in value["parents"]]
    return result


def code_file_metadata(value):
    return {
        key: value[key]
        for key in (
            "previous_filename",
            "status",
            "sha",
            "additions",
            "deletions",
            "changes",
            "patch",
            "blob_url",
            "raw_url",
            "contents_url",
        )
        if key in value
    }
