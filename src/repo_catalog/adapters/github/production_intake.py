"""P5 pure deterministic normalization of GitHub REST and GraphQL payloads into P3 Context units.

Does not import or reuse Schema 21 persistence assumptions.
Enforces:
- Canonical positive decimal database IDs (except GraphQL review threads)
- Strict separation of ordinary Issues vs. Pull Requests
- Explicit `None` (`"null"`) vs. omitted fields in partial projections
- Content-addressed UTF-8 `text_bodies` in Context without ever retaining file blobs in Git Core
- Portable `CoreReference` extraction for both `sha1` and `sha256` commit OIDs
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from repo_catalog.domain.acquisition import AcquisitionError
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ProviderRepositoryRoleScope,
    ProviderRepositoryScope,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.production_context import (
    CoreReference,
    ResourceObservation,
    ResourceRelation,
    json_value,
)
from repo_catalog.domain.resource_identity import (
    IdentityValue,
    encode_identity,
    parse_identity,
)
from repo_catalog.domain.time import parse_iso8601_us, validate_observation_us

_ACTOR_FIELDS = ("id", "login", "type", "html_url", "url")
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


def canonical_database_id(value: object, field_name: str = "id") -> str:
    """Validate and return a canonical positive decimal database ID string."""
    if type(value) is int and value > 0:
        return str(value)
    if (
        type(value) is str
        and value.isascii()
        and value.isdecimal()
        and value.strip("0")
        and not value.startswith("0")
    ):
        return value
    raise AcquisitionError(
        "CANONICAL_ID_REQUIRED",
        field_name,
        f"GitHub {field_name} must be a canonical positive decimal database ID",
    )


def github_resource_id(payload: dict[str, Any], *, graphql: bool) -> str:
    """Return canonical identity TEXT, keeping decimal and Node namespaces distinct."""
    if graphql:
        for name in ("fullDatabaseId", "databaseId"):
            if payload.get(name) is not None:
                return encode_identity(canonical_database_id(payload[name], name))
        value = payload.get("id")
        if type(value) is not str or not value:
            raise AcquisitionError("NODE_ID_REQUIRED", "id")
        return encode_identity(["github:node_id", value])
    return encode_identity(canonical_database_id(payload.get("id")))


def github_repository_id(payload, *, graphql):
    """Return canonical TEXT in the explicit Node or decimal Repository namespace."""
    if graphql and "__typename" in payload and payload["__typename"] != "Repository":
        raise AcquisitionError("RESOURCE_KIND", "repository")
    if graphql and "id" in payload:
        value = payload["id"]
        if type(value) is not str or not value:
            raise AcquisitionError("NODE_ID_REQUIRED", "repository.id")
        return encode_identity(["github:node_id", value])
    return github_resource_id(payload, graphql=graphql)


def github_timeline_input_id(value, *, graphql):
    """Return canonical TEXT: integers are database IDs; GraphQL strings are Node IDs."""
    if graphql and type(value) is str:
        if not value:
            raise AcquisitionError("NODE_ID_REQUIRED", "timeline.id")
        return encode_identity(["github:node_id", value])
    return encode_identity(canonical_database_id(value))


def repository_role_relation(
    resource, clock, provenance_json, observed_at_us, values, *, graphql
):
    """Preserve the actual Provider role projection; NULL never means unmapped."""
    roles = {}
    members = []
    for role, value in values.items():
        if value is None:
            entry = ProviderRepositoryRoleScope.explicit_null(
                role, clock, observed_at_us
            )
        else:
            if type(value) is not dict:
                raise AcquisitionError(
                    "REPOSITORY_REFERENCE", role, "object or null required"
                )
            ident = github_repository_id(value, graphql=graphql)
            entry = ProviderRepositoryRoleScope.unresolved(
                role, ident, clock, observed_at_us
            )
            member = ResourceKey(resource.service_instance_uuidv4, "repository", ident)
            if member not in members:
                members.append(member)
        roles[role] = entry
    if not roles:
        return ()
    return (
        ResourceRelation(
            resource,
            "provider_repository_roles",
            tuple(members),
            provenance_json,
            ProviderRepositoryScope(roles).encoded,
            observed_at_us,
        ),
    )


def parse_git_oid(value: object, scope: object = "oid") -> OID | None:
    """Parse a 40-char SHA-1 or 64-char SHA-256 hex string into a typed OID."""
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) not in (40, 64)
        or any(ch not in "0123456789abcdefABCDEF" for ch in value)
    ):
        raise AcquisitionError(
            "INVALID_GIT_OID", scope, "commit OID must be 40 or 64 hex characters"
        )
    lower = value.lower()
    fmt: Literal["sha1", "sha256"] = "sha256" if len(lower) == 64 else "sha1"
    return OID(fmt, lower)


def _parse_optional_time_us(
    payload: dict[str, Any], key: str
) -> tuple[bool, int | None]:
    if key not in payload:
        return False, None
    raw = payload[key]
    if raw is None:
        return True, None
    if type(raw) is int:
        return True, validate_observation_us(raw)
    try:
        return True, validate_observation_us(parse_iso8601_us(raw))
    except (ValueError, TypeError) as exc:
        raise AcquisitionError("INVALID_TIMESTAMP", key, str(exc)) from exc


def _select_dict(value: object, allowed_keys: tuple[str, ...]) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AcquisitionError("MALFORMED_OBJECT", allowed_keys, "expected JSON object")
    return {k: value[k] for k in allowed_keys if k in value}


def _extract_actorLogin(
    payload: dict[str, Any], *, graphql: bool = False
) -> tuple[bool, str | None]:
    key = (
        "author"
        if graphql and "author" in payload
        else (
            "user" if "user" in payload else ("author" if "author" in payload else "")
        )
    )
    if not key:
        return False, None
    actor = payload[key]
    if actor is None:
        return True, None
    if isinstance(actor, str):
        return True, actor
    if not isinstance(actor, dict):
        raise AcquisitionError("MALFORMED_ACTOR", key, "actor must be object or null")
    if "login" not in actor:
        return False, None
    login = actor["login"]
    if login is not None and not isinstance(login, str):
        raise AcquisitionError("MALFORMED_ACTOR", key, "login must be string or null")
    return True, login


def _candidate(
    resource: ResourceKey,
    field_name: str,
    value: object,
    clock: FieldClock,
    provenance_json: str,
    observed_at_us: int | None,
) -> FieldCandidate:
    return FieldCandidate(
        resource=resource,
        field_name=field_name,
        value_json=canonical(value),
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
    )


@dataclass(frozen=True)
class NormalizedContextUnit:
    """Pure normalized Context artifacts produced from a single Provider payload."""

    primary_resource: ResourceKey
    clock: FieldClock
    provenance_json: str
    observed_at_us: int | None
    observations: tuple[ResourceObservation, ...]
    text_admissions: tuple[
        tuple[ResourceKey, str | None, FieldClock, str, int | None], ...
    ]
    extra_texts: tuple[str, ...]
    relations: tuple[ResourceRelation, ...]
    core_references: tuple[tuple[CoreReference, FieldClock, int | None], ...]
    transfer_event: bool = False


def make_document_key(
    parent: ResourceKey,
    resource_kind: str,
    document_kind: str,
    provider_document_id: IdentityValue,
) -> ResourceKey:
    """Create a scoped key from a native local ID and a canonical namespace key."""
    mapped_kind = {
        "pull_request_document": "document",
        "review_thread": "thread",
        "review_comment": "comment",
        "issue_comment": "comment",
        "timeline_event": "comment",
        "pr_commit": "document",
        "pr_file": "document",
    }.get(resource_kind, resource_kind)
    return ResourceKey.document(
        parent, mapped_kind, document_kind, provider_document_id
    )


def normalize_repository_fields(
    service_instance_uuidv4: str,
    payload: dict[str, Any],
    observed_at_us: int | None,
    provenance_json: str,
    *,
    clock_domain: str = "github:repository:updated_at",
    graphql: bool = False,
) -> NormalizedContextUnit:
    """Normalize repository-level GitHub metadata into a Context ResourceObservation."""
    if not isinstance(payload, dict):
        raise AcquisitionError("MALFORMED_PAYLOAD", "repository", "dict required")
    validate_observation_us(observed_at_us)
    json_value(provenance_json, provenance=True)
    repo_id = github_repository_id(payload, graphql=graphql)
    resource = ResourceKey(service_instance_uuidv4, "repository", repo_id)
    has_upd, upd_us = _parse_optional_time_us(
        payload, "updatedAt" if "updatedAt" in payload else "updated_at"
    )
    clock = FieldClock(clock_domain, upd_us if has_upd else None)
    fields: list[FieldCandidate] = []
    scalar_names = (
        "name",
        "full_name",
        "html_url",
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
    for name in scalar_names:
        if name in payload:
            fields.append(
                _candidate(
                    resource,
                    name,
                    payload[name],
                    clock,
                    provenance_json,
                    observed_at_us,
                )
            )
    for src_time, dst_time in (
        ("created_at", "created_at_us"),
        ("updated_at", "updated_at_us"),
        ("pushed_at", "pushed_at_us"),
    ):
        present, ts = _parse_optional_time_us(payload, src_time)
        if present:
            fields.append(
                _candidate(
                    resource, dst_time, ts, clock, provenance_json, observed_at_us
                )
            )
    if "owner" in payload:
        fields.append(
            _candidate(
                resource,
                "owner",
                _select_dict(payload["owner"], _ACTOR_FIELDS),
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    return NormalizedContextUnit(
        primary_resource=resource,
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
        observations=(ResourceObservation(resource, tuple(fields)),),
        text_admissions=(),
        extra_texts=(),
        relations=(),
        core_references=(),
    )


def normalize_issue(
    service_instance_uuidv4: str,
    payload: dict[str, Any],
    observed_at_us: int | None,
    provenance_json: str,
    *,
    graphql: bool = False,
) -> NormalizedContextUnit | None:
    """Normalize a GitHub Issue payload; returns None for Issues API PR entries."""
    if not isinstance(payload, dict):
        raise AcquisitionError("MALFORMED_PAYLOAD", "issue", "dict required")
    if "pull_request" in payload:
        return None
    if graphql and payload.get("__typename") == "PullRequest":
        return None
    if graphql and "__typename" in payload and payload["__typename"] != "Issue":
        raise AcquisitionError("RESOURCE_KIND", "issue")
    validate_observation_us(observed_at_us)
    json_value(provenance_json, provenance=True)
    issue_id = github_resource_id(payload, graphql=graphql)
    issue_key = ResourceKey(service_instance_uuidv4, "issue", issue_id)
    _, updated_us = _parse_optional_time_us(
        payload, "updatedAt" if graphql and "updatedAt" in payload else "updated_at"
    )
    clock = FieldClock("github:issue:updated_at", updated_us)
    fields: list[FieldCandidate] = []
    if "number" in payload:
        num = payload["number"]
        if num is not None and (type(num) is not int or num <= 0):
            raise AcquisitionError("INVALID_FIELD", "number", "positive int required")
        fields.append(
            _candidate(issue_key, "number", num, clock, provenance_json, observed_at_us)
        )
    if "title" in payload:
        title = payload["title"]
        if title is not None and not isinstance(title, str):
            raise AcquisitionError("INVALID_FIELD", "title", "string or null required")
        fields.append(
            _candidate(
                issue_key, "title", title, clock, provenance_json, observed_at_us
            )
        )
    if "state" in payload:
        state = payload["state"]
        if isinstance(state, str) and state.upper() in ("OPEN", "CLOSED"):
            state = state.lower()
        elif state is not None:
            raise AcquisitionError("INVALID_FIELD", "state", "open or closed required")
        fields.append(
            _candidate(
                issue_key, "state", state, clock, provenance_json, observed_at_us
            )
        )
    has_author, login = _extract_actorLogin(payload, graphql=graphql)
    if has_author:
        fields.append(
            _candidate(
                issue_key, "author", login, clock, provenance_json, observed_at_us
            )
        )
    url_key = (
        "url"
        if graphql and "url" in payload
        else (
            "html_url" if "html_url" in payload else ("url" if "url" in payload else "")
        )
    )
    if url_key:
        fields.append(
            _candidate(
                issue_key,
                "url",
                payload[url_key],
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    for scalar in ("state_reason", "locked", "active_lock_reason", "comments"):
        if scalar in payload:
            fields.append(
                _candidate(
                    issue_key,
                    scalar,
                    payload[scalar],
                    clock,
                    provenance_json,
                    observed_at_us,
                )
            )
    for src_t, dst_t in (
        (
            "createdAt" if graphql and "createdAt" in payload else "created_at",
            "created_at_us",
        ),
        (
            "closedAt" if graphql and "closedAt" in payload else "closed_at",
            "closed_at_us",
        ),
    ):
        present, ts = _parse_optional_time_us(payload, src_t)
        if present:
            fields.append(
                _candidate(issue_key, dst_t, ts, clock, provenance_json, observed_at_us)
            )
    if "labels" in payload:
        raw_labels = payload["labels"]
        if isinstance(raw_labels, dict) and "nodes" in raw_labels:
            raw_labels = raw_labels["nodes"]
        labels = (
            None
            if raw_labels is None
            else [_select_dict(item, _LABEL_FIELDS) for item in raw_labels]
        )
        fields.append(
            _candidate(
                issue_key, "labels", labels, clock, provenance_json, observed_at_us
            )
        )
    if "assignees" in payload:
        raw_assignees = payload["assignees"]
        if isinstance(raw_assignees, dict) and "nodes" in raw_assignees:
            raw_assignees = raw_assignees["nodes"]
        assignees = (
            None
            if raw_assignees is None
            else [_select_dict(item, _ACTOR_FIELDS) for item in raw_assignees]
        )
        fields.append(
            _candidate(
                issue_key,
                "assignees",
                assignees,
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    if "milestone" in payload:
        ms = _select_dict(
            payload["milestone"], ("id", "number", "title", "state", "due_on")
        )
        fields.append(
            _candidate(
                issue_key, "milestone", ms, clock, provenance_json, observed_at_us
            )
        )
    text_admissions: list[tuple[ResourceKey, str | None, FieldClock, str, int]] = []
    if "body" in payload:
        body = payload["body"]
        if body is not None and not isinstance(body, str):
            raise AcquisitionError("INVALID_FIELD", "body", "string or null required")
        text_admissions.append(
            (issue_key, body, clock, provenance_json, observed_at_us)
        )
    return NormalizedContextUnit(
        primary_resource=issue_key,
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
        observations=(ResourceObservation(issue_key, tuple(fields)),),
        text_admissions=tuple(text_admissions),
        extra_texts=(),
        relations=repository_role_relation(
            issue_key,
            clock,
            provenance_json,
            observed_at_us,
            {"owning_repository": payload["repository"]}
            if "repository" in payload
            else {},
            graphql=graphql,
        ),
        core_references=(),
    )


def normalize_pull_request(
    service_instance_uuidv4: str,
    payload: dict[str, Any],
    observed_at_us: int | None,
    provenance_json: str,
    *,
    graphql: bool = False,
) -> NormalizedContextUnit:
    """Normalize a GitHub Pull Request payload, including title/body documents and CoreReferences."""
    if not isinstance(payload, dict):
        raise AcquisitionError("MALFORMED_PAYLOAD", "pull_request", "dict required")
    if graphql and "__typename" in payload and payload["__typename"] != "PullRequest":
        raise AcquisitionError("RESOURCE_KIND", "pull_request")
    validate_observation_us(observed_at_us)
    json_value(provenance_json, provenance=True)
    pr_id = github_resource_id(payload, graphql=graphql)
    pr_key = ResourceKey(service_instance_uuidv4, "pull_request", pr_id)
    _, updated_us = _parse_optional_time_us(
        payload, "updatedAt" if graphql and "updatedAt" in payload else "updated_at"
    )
    clock = FieldClock("github:pr:updated_at", updated_us)
    fields: list[FieldCandidate] = []
    observations: list[ResourceObservation] = []
    text_admissions: list[tuple[ResourceKey, str | None, FieldClock, str, int]] = []
    relations: list[ResourceRelation] = []
    core_refs: list[tuple[CoreReference, FieldClock, int]] = []

    if "number" in payload:
        num = payload["number"]
        if num is not None and (type(num) is not int or num <= 0):
            raise AcquisitionError("INVALID_FIELD", "number", "positive int required")
        fields.append(
            _candidate(pr_key, "number", num, clock, provenance_json, observed_at_us)
        )
    if "state" in payload:
        state = payload["state"]
        if isinstance(state, str) and state.upper() in ("OPEN", "CLOSED", "MERGED"):
            state = state.lower()
        elif state is not None:
            raise AcquisitionError("INVALID_FIELD", "state", "invalid PR state")
        fields.append(
            _candidate(pr_key, "state", state, clock, provenance_json, observed_at_us)
        )
    has_author, login = _extract_actorLogin(payload, graphql=graphql)
    if has_author:
        fields.append(
            _candidate(pr_key, "author", login, clock, provenance_json, observed_at_us)
        )
    url_key = (
        "url"
        if graphql and "url" in payload
        else (
            "html_url" if "html_url" in payload else ("url" if "url" in payload else "")
        )
    )
    if url_key:
        fields.append(
            _candidate(
                pr_key, "url", payload[url_key], clock, provenance_json, observed_at_us
            )
        )
    for scalar in (
        "draft",
        "merged",
        "locked",
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
        "author_association",
        "active_lock_reason",
    ):
        if scalar in payload:
            fields.append(
                _candidate(
                    pr_key,
                    scalar,
                    payload[scalar],
                    clock,
                    provenance_json,
                    observed_at_us,
                )
            )
    for src_t, dst_t in (
        (
            "createdAt" if graphql and "createdAt" in payload else "created_at",
            "created_at_us",
        ),
        (
            "closedAt" if graphql and "closedAt" in payload else "closed_at",
            "closed_at_us",
        ),
        (
            "mergedAt" if graphql and "mergedAt" in payload else "merged_at",
            "merged_at_us",
        ),
    ):
        present, ts = _parse_optional_time_us(payload, src_t)
        if present:
            fields.append(
                _candidate(pr_key, dst_t, ts, clock, provenance_json, observed_at_us)
            )

    seen_formats: set[str] = set()
    for role, gql_oid_key, gql_ref_key in (
        ("head", "headRefOid", "headRefName"),
        ("base", "baseRefOid", "baseRefName"),
    ):
        if role in payload:
            branch = payload[role]
            if branch is None:
                fields.append(
                    _candidate(
                        pr_key,
                        f"{role}_oid",
                        None,
                        clock,
                        provenance_json,
                        observed_at_us,
                    )
                )
                fields.append(
                    _candidate(
                        pr_key,
                        f"{role}_ref",
                        None,
                        clock,
                        provenance_json,
                        observed_at_us,
                    )
                )
            elif isinstance(branch, dict):
                if "ref" in branch:
                    fields.append(
                        _candidate(
                            pr_key,
                            f"{role}_ref",
                            branch["ref"],
                            clock,
                            provenance_json,
                            observed_at_us,
                        )
                    )
                if "sha" in branch:
                    oid = parse_git_oid(branch["sha"], f"pr.{role}.sha")
                    if oid is None:
                        fields.append(
                            _candidate(
                                pr_key,
                                f"{role}_oid",
                                None,
                                clock,
                                provenance_json,
                                observed_at_us,
                            )
                        )
                    else:
                        seen_formats.add(oid.object_format)
                        fields.append(
                            _candidate(
                                pr_key,
                                f"{role}_oid",
                                oid.full_oid,
                                clock,
                                provenance_json,
                                observed_at_us,
                            )
                        )
                        core_refs.append(
                            (
                                CoreReference(pr_key, role, oid, provenance_json),
                                clock,
                                observed_at_us,
                            )
                        )
            else:
                raise AcquisitionError(
                    "MALFORMED_FIELD", role, "object or null required"
                )
        elif graphql:
            if gql_ref_key in payload:
                fields.append(
                    _candidate(
                        pr_key,
                        f"{role}_ref",
                        payload[gql_ref_key],
                        clock,
                        provenance_json,
                        observed_at_us,
                    )
                )
            if gql_oid_key in payload:
                oid = parse_git_oid(payload[gql_oid_key], f"pr.{gql_oid_key}")
                if oid is None:
                    fields.append(
                        _candidate(
                            pr_key,
                            f"{role}_oid",
                            None,
                            clock,
                            provenance_json,
                            observed_at_us,
                        )
                    )
                else:
                    seen_formats.add(oid.object_format)
                    fields.append(
                        _candidate(
                            pr_key,
                            f"{role}_oid",
                            oid.full_oid,
                            clock,
                            provenance_json,
                            observed_at_us,
                        )
                    )
                    core_refs.append(
                        (
                            CoreReference(pr_key, role, oid, provenance_json),
                            clock,
                            observed_at_us,
                        )
                    )

    if "merge_commit_sha" in payload:
        oid = parse_git_oid(payload["merge_commit_sha"], "pr.merge_commit_sha")
        if oid is None:
            fields.append(
                _candidate(
                    pr_key, "merge_oid", None, clock, provenance_json, observed_at_us
                )
            )
        else:
            seen_formats.add(oid.object_format)
            fields.append(
                _candidate(
                    pr_key,
                    "merge_oid",
                    oid.full_oid,
                    clock,
                    provenance_json,
                    observed_at_us,
                )
            )
            core_refs.append(
                (
                    CoreReference(pr_key, "merge", oid, provenance_json),
                    clock,
                    observed_at_us,
                )
            )
    elif graphql and "mergeCommit" in payload:
        mc = payload["mergeCommit"]
        if mc is None:
            fields.append(
                _candidate(
                    pr_key, "merge_oid", None, clock, provenance_json, observed_at_us
                )
            )
        elif isinstance(mc, dict) and "oid" in mc:
            oid = parse_git_oid(mc["oid"], "pr.mergeCommit.oid")
            if oid is None:
                fields.append(
                    _candidate(
                        pr_key,
                        "merge_oid",
                        None,
                        clock,
                        provenance_json,
                        observed_at_us,
                    )
                )
            else:
                seen_formats.add(oid.object_format)
                fields.append(
                    _candidate(
                        pr_key,
                        "merge_oid",
                        oid.full_oid,
                        clock,
                        provenance_json,
                        observed_at_us,
                    )
                )
                core_refs.append(
                    (
                        CoreReference(pr_key, "merge", oid, provenance_json),
                        clock,
                        observed_at_us,
                    )
                )

    if len(seen_formats) > 1:
        raise AcquisitionError(
            "MIXED_OBJECT_FORMATS", pr_key, "mixed SHA-1 and SHA-256 commit OIDs in PR"
        )

    doc_members: list[ResourceKey] = []
    if "title" in payload:
        title_val = payload["title"]
        if title_val is not None and not isinstance(title_val, str):
            raise AcquisitionError("INVALID_FIELD", "title", "string or null required")
        fields.append(
            _candidate(
                pr_key, "title", title_val, clock, provenance_json, observed_at_us
            )
        )
        title_doc = make_document_key(
            pr_key, "pull_request_document", "pr_title", parse_identity(pr_id)
        )
        observations.append(ResourceObservation(title_doc, ()))
        text_admissions.append(
            (title_doc, title_val, clock, provenance_json, observed_at_us)
        )
        doc_members.append(title_doc)

    if "body" in payload:
        body_val = payload["body"]
        if body_val is not None and not isinstance(body_val, str):
            raise AcquisitionError("INVALID_FIELD", "body", "string or null required")
        body_doc = make_document_key(
            pr_key, "pull_request_document", "pr_body", parse_identity(pr_id)
        )
        observations.append(ResourceObservation(body_doc, ()))
        text_admissions.append(
            (body_doc, body_val, clock, provenance_json, observed_at_us)
        )
        doc_members.append(body_doc)

    observations.insert(0, ResourceObservation(pr_key, tuple(fields)))
    if doc_members:
        relations.append(
            ResourceRelation(
                pr_key,
                "documents",
                tuple(doc_members),
                provenance_json,
                canonical({"document_scope": "pr_title_body"}),
                observed_at_us,
            )
        )

    repository_values = {}
    for role, gql_field in (("base", "baseRepository"), ("head", "headRepository")):
        if graphql and gql_field in payload:
            repository_values[role + "_repository"] = payload[gql_field]
        elif (
            not graphql
            and isinstance(payload.get(role), dict)
            and "repo" in payload[role]
        ):
            repository_values[role + "_repository"] = payload[role]["repo"]
    relations.extend(
        repository_role_relation(
            pr_key,
            clock,
            provenance_json,
            observed_at_us,
            repository_values,
            graphql=graphql,
        )
    )
    return NormalizedContextUnit(
        primary_resource=pr_key,
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
        observations=tuple(observations),
        text_admissions=tuple(text_admissions),
        extra_texts=(),
        relations=tuple(relations),
        core_references=tuple(core_refs),
    )


def normalize_review(
    service_instance_uuidv4: str,
    pull_request_id: str | int,
    payload: dict[str, Any],
    observed_at_us: int | None,
    provenance_json: str,
    *,
    graphql: bool = False,
) -> NormalizedContextUnit:
    """Normalize a GitHub PR Review summary without inventing a synthetic update clock."""
    if not isinstance(payload, dict):
        raise AcquisitionError("MALFORMED_PAYLOAD", "review", "dict required")
    validate_observation_us(observed_at_us)
    json_value(provenance_json, provenance=True)
    pr_id = canonical_database_id(pull_request_id, "pull_request_id")
    pr_key = ResourceKey.from_native(service_instance_uuidv4, "pull_request", pr_id)
    id_field = (
        "fullDatabaseId"
        if graphql and "fullDatabaseId" in payload
        else ("databaseId" if graphql and "databaseId" in payload else "id")
    )
    review_id = canonical_database_id(payload.get(id_field), id_field)
    review_key = make_document_key(pr_key, "review", "review_summary", review_id)

    has_sub, submitted_us = _parse_optional_time_us(
        payload,
        "submittedAt" if graphql and "submittedAt" in payload else "submitted_at",
    )
    # Reviews do not have a mutable updated_at clock; order is clockless observation or submission instant.
    clock = FieldClock("github:review:observation", None)
    fields: list[FieldCandidate] = []
    if has_sub:
        fields.append(
            _candidate(
                review_key,
                "submitted_at_us",
                submitted_us,
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    if "state" in payload:
        state = payload["state"]
        if state is not None and state not in (
            "APPROVED",
            "CHANGES_REQUESTED",
            "COMMENTED",
            "DISMISSED",
            "PENDING",
        ):
            raise AcquisitionError("INVALID_FIELD", "state", "invalid review state")
        fields.append(
            _candidate(
                review_key, "state", state, clock, provenance_json, observed_at_us
            )
        )
    has_author, login = _extract_actorLogin(payload, graphql=graphql)
    if has_author:
        fields.append(
            _candidate(
                review_key, "author", login, clock, provenance_json, observed_at_us
            )
        )
    url_key = (
        "url"
        if graphql and "url" in payload
        else (
            "html_url" if "html_url" in payload else ("url" if "url" in payload else "")
        )
    )
    if url_key:
        fields.append(
            _candidate(
                review_key,
                "url",
                payload[url_key],
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    core_refs: list[tuple[CoreReference, FieldClock, int]] = []
    commit_raw = None
    has_commit = False
    if "commit_id" in payload:
        has_commit = True
        commit_raw = payload["commit_id"]
    elif graphql and "commit" in payload:
        has_commit = True
        c_obj = payload["commit"]
        commit_raw = c_obj.get("oid") if isinstance(c_obj, dict) else None
    if has_commit:
        oid = parse_git_oid(commit_raw, "review.commit_id")
        if oid is None:
            fields.append(
                _candidate(
                    review_key,
                    "target_commit_oid",
                    None,
                    clock,
                    provenance_json,
                    observed_at_us,
                )
            )
        else:
            fields.append(
                _candidate(
                    review_key,
                    "target_commit_oid",
                    oid.full_oid,
                    clock,
                    provenance_json,
                    observed_at_us,
                )
            )
            core_refs.append(
                (
                    CoreReference(review_key, "target_commit", oid, provenance_json),
                    clock,
                    observed_at_us,
                )
            )
    text_admissions: list[tuple[ResourceKey, str | None, FieldClock, str, int]] = []
    if "body" in payload:
        body = payload["body"]
        if body is not None and not isinstance(body, str):
            raise AcquisitionError("INVALID_FIELD", "body", "string or null required")
        text_admissions.append(
            (review_key, body, clock, provenance_json, observed_at_us)
        )
    relation = ResourceRelation(
        pr_key,
        "reviews",
        (review_key,),
        provenance_json,
        canonical({"review_id": review_id}),
        observed_at_us,
    )
    return NormalizedContextUnit(
        primary_resource=review_key,
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
        observations=(
            ResourceObservation(pr_key, ()),
            ResourceObservation(review_key, tuple(fields)),
        ),
        text_admissions=tuple(text_admissions),
        extra_texts=(),
        relations=(relation,),
        core_references=tuple(core_refs),
    )


def normalize_review_thread(
    service_instance_uuidv4: str,
    pull_request_id: str | int,
    payload: dict[str, Any],
    observed_at_us: int | None,
    provenance_json: str,
) -> NormalizedContextUnit:
    """Normalize a GraphQL PullRequestReviewThread into a Context thread resource."""
    if not isinstance(payload, dict):
        raise AcquisitionError("MALFORMED_PAYLOAD", "review_thread", "dict required")
    validate_observation_us(observed_at_us)
    json_value(provenance_json, provenance=True)
    pr_id = canonical_database_id(pull_request_id, "pull_request_id")
    pr_key = ResourceKey.from_native(service_instance_uuidv4, "pull_request", pr_id)
    thread_id = payload.get("id")
    if type(thread_id) is not str or not thread_id.strip():
        raise AcquisitionError(
            "THREAD_ID_REQUIRED", "review_thread", "non-empty string thread id required"
        )
    thread_key = make_document_key(pr_key, "review_thread", "thread", thread_id)
    clock = FieldClock("github:review_thread:observation", None)
    fields: list[FieldCandidate] = []
    mappings = (
        (("isResolved", "resolved"), "resolved"),
        (("isOutdated", "outdated"), "outdated"),
        (("path", "raw_path"), "raw_path"),
        (("line",), "line"),
        (("startLine", "start_line"), "start_line"),
        (("originalLine", "original_line"), "original_line"),
        (("originalStartLine", "original_start_line"), "original_start_line"),
        (("diffSide", "side"), "side"),
        (("startDiffSide", "start_side"), "start_side"),
    )
    for src_keys, target_field in mappings:
        for src in src_keys:
            if src in payload:
                fields.append(
                    _candidate(
                        thread_key,
                        target_field,
                        payload[src],
                        clock,
                        provenance_json,
                        observed_at_us,
                    )
                )
                break
    relation = ResourceRelation(
        pr_key,
        "threads",
        (thread_key,),
        provenance_json,
        canonical({"thread_id": thread_id}),
        observed_at_us,
    )
    return NormalizedContextUnit(
        primary_resource=thread_key,
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
        observations=(
            ResourceObservation(pr_key, ()),
            ResourceObservation(thread_key, tuple(fields)),
        ),
        text_admissions=(),
        extra_texts=(),
        relations=(relation,),
        core_references=(),
    )


def normalize_review_comment(
    service_instance_uuidv4: str,
    pull_request_id: str | int,
    payload: dict[str, Any],
    observed_at_us: int | None,
    provenance_json: str,
    *,
    graphql: bool = False,
    thread_id: str | None = None,
) -> NormalizedContextUnit:
    """Normalize a REST or GraphQL PR Review Comment with review, thread, and reply relations."""
    if not isinstance(payload, dict):
        raise AcquisitionError("MALFORMED_PAYLOAD", "review_comment", "dict required")
    validate_observation_us(observed_at_us)
    json_value(provenance_json, provenance=True)
    pr_id = canonical_database_id(pull_request_id, "pull_request_id")
    pr_key = ResourceKey.from_native(service_instance_uuidv4, "pull_request", pr_id)
    id_field = (
        "fullDatabaseId"
        if graphql and "fullDatabaseId" in payload
        else ("databaseId" if graphql and "databaseId" in payload else "id")
    )
    comment_id = canonical_database_id(payload.get(id_field), id_field)
    comment_key = make_document_key(pr_key, "review_comment", "comment", comment_id)

    _, updated_us = _parse_optional_time_us(
        payload, "updatedAt" if graphql and "updatedAt" in payload else "updated_at"
    )
    clock = FieldClock("github:review_comment:updated_at", updated_us)
    fields: list[FieldCandidate] = []
    extra_observations: list[ResourceObservation] = [ResourceObservation(pr_key, ())]
    relations: list[ResourceRelation] = [
        ResourceRelation(
            pr_key,
            "comments",
            (comment_key,),
            provenance_json,
            canonical({"review_comment_id": comment_id}),
            observed_at_us,
        )
    ]
    core_refs: list[tuple[CoreReference, FieldClock, int]] = []
    extra_texts: list[str] = []

    has_author, login = _extract_actorLogin(payload, graphql=graphql)
    if has_author:
        fields.append(
            _candidate(
                comment_key, "author", login, clock, provenance_json, observed_at_us
            )
        )
    url_key = (
        "url"
        if graphql and "url" in payload
        else (
            "html_url" if "html_url" in payload else ("url" if "url" in payload else "")
        )
    )
    if url_key:
        fields.append(
            _candidate(
                comment_key,
                "url",
                payload[url_key],
                clock,
                provenance_json,
                observed_at_us,
            )
        )

    for src_keys, dst_field in (
        (("path", "raw_path"), "raw_path"),
        (("diffHunk", "diff_hunk"), "diff_hunk"),
        (("position", "current_position"), "current_position"),
        (("originalPosition", "original_position"), "original_position"),
        (("line",), "line"),
        (("originalLine", "original_line"), "original_line"),
        (("side",), "side"),
        (("startLine", "start_line"), "start_line"),
        (("originalStartLine", "original_start_line"), "original_start_line"),
        (("startSide", "start_side"), "start_side"),
        (("subject_type",), "subject_type"),
    ):
        for src in src_keys:
            if src in payload:
                val = payload[src]
                fields.append(
                    _candidate(
                        comment_key,
                        dst_field,
                        val,
                        clock,
                        provenance_json,
                        observed_at_us,
                    )
                )
                if dst_field == "diff_hunk" and isinstance(val, str):
                    extra_texts.append(val)
                break

    present_created, created_us = _parse_optional_time_us(
        payload, "createdAt" if graphql and "createdAt" in payload else "created_at"
    )
    if present_created:
        fields.append(
            _candidate(
                comment_key,
                "created_at_us",
                created_us,
                clock,
                provenance_json,
                observed_at_us,
            )
        )

    # Review relation
    review_db_id: str | None = None
    has_review_field = False
    if "pull_request_review_id" in payload:
        has_review_field = True
        if payload["pull_request_review_id"] is not None:
            review_db_id = canonical_database_id(
                payload["pull_request_review_id"], "pull_request_review_id"
            )
    elif graphql and "pullRequestReview" in payload:
        has_review_field = True
        pr_rev = payload["pullRequestReview"]
        if isinstance(pr_rev, dict):
            rid_key = (
                "fullDatabaseId"
                if "fullDatabaseId" in pr_rev
                else ("databaseId" if "databaseId" in pr_rev else "id")
            )
            if rid_key in pr_rev and pr_rev[rid_key] is not None:
                review_db_id = canonical_database_id(pr_rev[rid_key], rid_key)
    if has_review_field:
        fields.append(
            _candidate(
                comment_key,
                "review_id",
                review_db_id,
                clock,
                provenance_json,
                observed_at_us,
            )
        )
        if review_db_id is not None:
            review_key = make_document_key(
                pr_key, "review", "review_summary", review_db_id
            )
            extra_observations.append(ResourceObservation(review_key, ()))
            relations.append(
                ResourceRelation(
                    comment_key,
                    "belongs_to_review",
                    (review_key,),
                    provenance_json,
                    canonical({"review_id": review_db_id}),
                    observed_at_us,
                )
            )

    # Reply relation
    reply_db_id: str | None = None
    has_reply_field = False
    if "in_reply_to_id" in payload:
        has_reply_field = True
        if payload["in_reply_to_id"] is not None:
            reply_db_id = canonical_database_id(
                payload["in_reply_to_id"], "in_reply_to_id"
            )
    elif graphql and "replyTo" in payload:
        has_reply_field = True
        rep = payload["replyTo"]
        if isinstance(rep, dict):
            rid_key = (
                "fullDatabaseId"
                if "fullDatabaseId" in rep
                else ("databaseId" if "databaseId" in rep else "id")
            )
            if rid_key in rep and rep[rid_key] is not None:
                reply_db_id = canonical_database_id(rep[rid_key], rid_key)
    if has_reply_field:
        fields.append(
            _candidate(
                comment_key,
                "in_reply_to_id",
                reply_db_id,
                clock,
                provenance_json,
                observed_at_us,
            )
        )
        if reply_db_id is not None:
            parent_comment_key = make_document_key(
                pr_key, "review_comment", "comment", reply_db_id
            )
            extra_observations.append(ResourceObservation(parent_comment_key, ()))
            relations.append(
                ResourceRelation(
                    comment_key,
                    "in_reply_to",
                    (parent_comment_key,),
                    provenance_json,
                    canonical({"in_reply_to_id": reply_db_id}),
                    observed_at_us,
                )
            )

    # Thread relation
    effective_thread = (
        thread_id if thread_id is not None else payload.get("review_thread_id")
    )
    if effective_thread is not None:
        if type(effective_thread) is not str or not effective_thread.strip():
            raise AcquisitionError(
                "THREAD_ID_REQUIRED",
                "review_thread",
                "non-empty string thread id required",
            )
        fields.append(
            _candidate(
                comment_key,
                "review_thread_id",
                effective_thread,
                clock,
                provenance_json,
                observed_at_us,
            )
        )
        thread_key = make_document_key(
            pr_key, "review_thread", "thread", effective_thread
        )
        extra_observations.append(ResourceObservation(thread_key, ()))
        relations.append(
            ResourceRelation(
                comment_key,
                "in_thread",
                (thread_key,),
                provenance_json,
                canonical({"thread_id": effective_thread}),
                observed_at_us,
            )
        )

    # Commit references (target_commit, original_commit)
    for role, rest_key, gql_key in (
        ("target_commit", "commit_id", "commit"),
        ("original_commit", "original_commit_id", "originalCommit"),
    ):
        has_oid = False
        raw_oid = None
        if rest_key in payload:
            has_oid = True
            raw_oid = payload[rest_key]
        elif graphql and gql_key in payload:
            has_oid = True
            c_obj = payload[gql_key]
            raw_oid = c_obj.get("oid") if isinstance(c_obj, dict) else None
        if has_oid:
            oid = parse_git_oid(raw_oid, f"review_comment.{role}")
            if oid is None:
                fields.append(
                    _candidate(
                        comment_key,
                        f"{role}_oid",
                        None,
                        clock,
                        provenance_json,
                        observed_at_us,
                    )
                )
            else:
                fields.append(
                    _candidate(
                        comment_key,
                        f"{role}_oid",
                        oid.full_oid,
                        clock,
                        provenance_json,
                        observed_at_us,
                    )
                )
                core_refs.append(
                    (
                        CoreReference(comment_key, role, oid, provenance_json),
                        clock,
                        observed_at_us,
                    )
                )

    text_admissions: list[tuple[ResourceKey, str | None, FieldClock, str, int]] = []
    if "body" in payload:
        body = payload["body"]
        if body is not None and not isinstance(body, str):
            raise AcquisitionError("INVALID_FIELD", "body", "string or null required")
        text_admissions.append(
            (comment_key, body, clock, provenance_json, observed_at_us)
        )

    return NormalizedContextUnit(
        primary_resource=comment_key,
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
        observations=(
            *extra_observations,
            ResourceObservation(comment_key, tuple(fields)),
        ),
        text_admissions=tuple(text_admissions),
        extra_texts=tuple(extra_texts),
        relations=tuple(relations),
        core_references=tuple(core_refs),
    )


def normalize_issue_comment(
    service_instance_uuidv4: str,
    parent_kind: Literal["issue", "pull_request"],
    parent_id: str | int,
    payload: dict[str, Any],
    observed_at_us: int | None,
    provenance_json: str,
    *,
    graphql: bool = False,
) -> NormalizedContextUnit:
    """Normalize a GitHub Issue Comment under an Issue or Pull Request."""
    if not isinstance(payload, dict):
        raise AcquisitionError("MALFORMED_PAYLOAD", "issue_comment", "dict required")
    if parent_kind not in ("issue", "pull_request"):
        raise AcquisitionError("PARENT_KIND", parent_kind)
    validate_observation_us(observed_at_us)
    json_value(provenance_json, provenance=True)
    pid = canonical_database_id(parent_id, "parent_id")
    parent_key = ResourceKey.from_native(service_instance_uuidv4, parent_kind, pid)
    id_field = (
        "fullDatabaseId"
        if graphql and "fullDatabaseId" in payload
        else ("databaseId" if graphql and "databaseId" in payload else "id")
    )
    comment_id = canonical_database_id(payload.get(id_field), id_field)
    comment_key = make_document_key(parent_key, "issue_comment", "comment", comment_id)

    _, updated_us = _parse_optional_time_us(
        payload, "updatedAt" if graphql and "updatedAt" in payload else "updated_at"
    )
    clock = FieldClock("github:issue_comment:updated_at", updated_us)
    fields: list[FieldCandidate] = []
    has_author, login = _extract_actorLogin(payload, graphql=graphql)
    if has_author:
        fields.append(
            _candidate(
                comment_key, "author", login, clock, provenance_json, observed_at_us
            )
        )
    url_key = (
        "url"
        if graphql and "url" in payload
        else (
            "html_url" if "html_url" in payload else ("url" if "url" in payload else "")
        )
    )
    if url_key:
        fields.append(
            _candidate(
                comment_key,
                "url",
                payload[url_key],
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    present_created, created_us = _parse_optional_time_us(
        payload, "createdAt" if graphql and "createdAt" in payload else "created_at"
    )
    if present_created:
        fields.append(
            _candidate(
                comment_key,
                "created_at_us",
                created_us,
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    if "author_association" in payload:
        fields.append(
            _candidate(
                comment_key,
                "author_association",
                payload["author_association"],
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    text_admissions: list[tuple[ResourceKey, str | None, FieldClock, str, int]] = []
    if "body" in payload:
        body = payload["body"]
        if body is not None and not isinstance(body, str):
            raise AcquisitionError("INVALID_FIELD", "body", "string or null required")
        text_admissions.append(
            (comment_key, body, clock, provenance_json, observed_at_us)
        )
    relation = ResourceRelation(
        parent_key,
        "comments",
        (comment_key,),
        provenance_json,
        canonical({"issue_comment_id": comment_id}),
        observed_at_us,
    )
    return NormalizedContextUnit(
        primary_resource=comment_key,
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
        observations=(
            ResourceObservation(parent_key, ()),
            ResourceObservation(comment_key, tuple(fields)),
        ),
        text_admissions=tuple(text_admissions),
        extra_texts=(),
        relations=(relation,),
        core_references=(),
    )


def normalize_timeline_event(
    service_instance_uuidv4: str,
    parent_kind: Literal["issue", "pull_request"],
    parent_id: str | int,
    event_id: str | int,
    payload: dict[str, Any],
    observed_at_us: int | None,
    provenance_json: str,
    *,
    graphql: bool = False,
    parent_resource: ResourceKey | None = None,
) -> NormalizedContextUnit:
    """Normalize a GitHub Issue/PR Timeline event."""
    if not isinstance(payload, dict):
        raise AcquisitionError("MALFORMED_PAYLOAD", "timeline_event", "dict required")
    if parent_kind not in ("issue", "pull_request"):
        raise AcquisitionError("PARENT_KIND", parent_kind)
    validate_observation_us(observed_at_us)
    json_value(provenance_json, provenance=True)
    pid = github_timeline_input_id(parent_id, graphql=graphql)
    parent_key = parent_resource or ResourceKey(
        service_instance_uuidv4, parent_kind, pid
    )
    if (
        parent_key.service_instance_uuidv4 != service_instance_uuidv4
        or parent_key.resource_kind != parent_kind
    ):
        raise AcquisitionError("EVENT_PARENT_MISMATCH", "timeline_event")
    database_aliases = set()
    if graphql and isinstance(payload.get("issue"), dict):
        database_aliases = {
            encode_identity(canonical_database_id(payload["issue"][name], name))
            for name in ("fullDatabaseId", "databaseId")
            if payload["issue"].get(name) is not None
        }
        if len(database_aliases) > 1:
            raise AcquisitionError("EVENT_PARENT_MISMATCH", "timeline_event")
        if (
            "__typename" in payload["issue"]
            and payload["issue"]["__typename"] != "Issue"
        ):
            raise AcquisitionError("EVENT_PARENT_MISMATCH", "timeline_event")
        if (
            github_resource_id(payload["issue"], graphql=True)
            != parent_key.provider_resource_id
            or parent_key.resource_kind != "issue"
        ):
            raise AcquisitionError("EVENT_PARENT_MISMATCH", "timeline_event")
    if pid != parent_key.provider_resource_id:
        # An explicit ResourceKey cannot replace contradictory Provider coordinates.
        # GraphQL may supply the same observed Issue in Node and database namespaces;
        # bind both coordinates to that actual payload rather than decoding the Node ID.
        observed_issue = payload.get("issue") if graphql else None
        if not isinstance(observed_issue, dict):
            raise AcquisitionError("EVENT_PARENT_MISMATCH", "timeline_event")
        observed_aliases = (
            {github_timeline_input_id(observed_issue["id"], graphql=True)}
            if "id" in observed_issue
            else set()
        )
        if pid not in observed_aliases | database_aliases:
            raise AcquisitionError("EVENT_PARENT_MISMATCH", "timeline_event")
    eid = github_timeline_input_id(event_id, graphql=graphql)
    if "id" not in payload:
        raise AcquisitionError(
            "EVENT_ID_REQUIRED",
            "timeline_event",
            "Provider event payload must identify the event",
        )
    if (
        "id" in payload
        and github_timeline_input_id(payload["id"], graphql=graphql) != eid
    ):
        raise AcquisitionError("EVENT_ID_MISMATCH", "timeline_event")
    if not eid:
        raise AcquisitionError("EVENT_ID_REQUIRED", "timeline_event")
    event_key = make_document_key(
        parent_key, "timeline_event", "timeline_event", parse_identity(eid)
    )
    _, created_us = _parse_optional_time_us(
        payload, "createdAt" if graphql else "created_at"
    )
    clock = FieldClock("github:timeline:created_at", created_us)
    fields: list[FieldCandidate] = []
    core_refs: list[tuple[CoreReference, FieldClock, int]] = []
    if graphql and "__typename" in payload:
        fields.append(
            _candidate(
                event_key,
                "provider_event_type",
                payload["__typename"],
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    for k in ("event", "state", "lock_reason", "author_association"):
        if k in payload:
            fields.append(
                _candidate(
                    event_key, k, payload[k], clock, provenance_json, observed_at_us
                )
            )
    if "actor" in payload:
        fields.append(
            _candidate(
                event_key,
                "actor",
                _select_dict(payload["actor"], _ACTOR_FIELDS),
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    if "label" in payload:
        fields.append(
            _candidate(
                event_key,
                "label",
                _select_dict(payload["label"], _LABEL_FIELDS),
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    if "rename" in payload:
        fields.append(
            _candidate(
                event_key,
                "rename",
                _select_dict(payload["rename"], ("from", "to")),
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    if "commit_id" in payload:
        raw_cid = payload["commit_id"]
        oid = parse_git_oid(raw_cid, "timeline.commit_id")
        fields.append(
            _candidate(
                event_key,
                "commit_id",
                None if oid is None else oid.full_oid,
                clock,
                provenance_json,
                observed_at_us,
            )
        )
        if oid is not None:
            core_refs.append(
                (
                    CoreReference(event_key, "referenced_commit", oid, provenance_json),
                    clock,
                    observed_at_us,
                )
            )
    relation = ResourceRelation(
        parent_key,
        "timeline_events",
        (event_key,),
        provenance_json,
        canonical({"event_id": eid}),
        observed_at_us,
    )
    transferred = (
        payload.get("__typename") == "TransferredEvent"
        if graphql
        else payload.get("event") == "transferred"
    )
    values = {}
    if transferred:
        if parent_kind != "issue":
            raise AcquisitionError(
                "TRANSFER_PARENT", "timeline_event", "Issue parent required"
            )
        for role, name in (
            (
                "transfer_from_repository",
                "fromRepository" if graphql else "from_repository",
            ),
            ("transfer_to_repository", "toRepository" if graphql else "to_repository"),
        ):
            if name in payload:
                values[role] = payload[name]
    role_relations = repository_role_relation(
        event_key, clock, provenance_json, observed_at_us, values, graphql=graphql
    )
    return NormalizedContextUnit(
        primary_resource=event_key,
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
        observations=(
            ResourceObservation(parent_key, ()),
            ResourceObservation(event_key, tuple(fields)),
        ),
        text_admissions=(),
        extra_texts=(),
        relations=(relation, *role_relations),
        core_references=tuple(core_refs),
        transfer_event=transferred,
    )


def normalize_pr_commit(
    service_instance_uuidv4: str,
    pull_request_id: str | int,
    payload: dict[str, Any],
    observed_at_us: int | None,
    provenance_json: str,
) -> NormalizedContextUnit:
    """Normalize a GitHub PR commit entry into a Context document and CoreReference."""
    if not isinstance(payload, dict):
        raise AcquisitionError("MALFORMED_PAYLOAD", "pr_commit", "dict required")
    validate_observation_us(observed_at_us)
    json_value(provenance_json, provenance=True)
    pr_id = canonical_database_id(pull_request_id, "pull_request_id")
    pr_key = ResourceKey.from_native(service_instance_uuidv4, "pull_request", pr_id)
    oid = parse_git_oid(payload.get("sha"), "pr_commit.sha")
    if oid is None:
        raise AcquisitionError(
            "INVALID_GIT_OID", "pr_commit.sha", "commit sha required"
        )
    commit_doc = make_document_key(pr_key, "pr_commit", "pr_commit", oid.full_oid)
    clock = FieldClock("github:pr_commit:observation", None)
    fields: list[FieldCandidate] = [
        _candidate(
            commit_doc, "sha", oid.full_oid, clock, provenance_json, observed_at_us
        )
    ]
    if "html_url" in payload:
        fields.append(
            _candidate(
                commit_doc,
                "url",
                payload["html_url"],
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    for role in ("author", "committer"):
        if role in payload:
            fields.append(
                _candidate(
                    commit_doc,
                    role,
                    _select_dict(payload[role], _ACTOR_FIELDS),
                    clock,
                    provenance_json,
                    observed_at_us,
                )
            )
    text_admissions: list[tuple[ResourceKey, str | None, FieldClock, str, int]] = []
    if "commit" in payload and isinstance(payload["commit"], dict):
        c_data = payload["commit"]
        if "message" in c_data:
            msg = c_data["message"]
            fields.append(
                _candidate(
                    commit_doc,
                    "message",
                    msg,
                    clock,
                    provenance_json,
                    observed_at_us,
                )
            )
            text_admissions.append(
                (commit_doc, msg, clock, provenance_json, observed_at_us)
            )
    if "parents" in payload and isinstance(payload["parents"], list):
        parent_shas = [
            p.get("sha")
            for p in payload["parents"]
            if isinstance(p, dict) and "sha" in p
        ]
        fields.append(
            _candidate(
                commit_doc,
                "parents",
                parent_shas,
                clock,
                provenance_json,
                observed_at_us,
            )
        )
    core_refs = (
        (
            CoreReference(commit_doc, "commit", oid, provenance_json),
            clock,
            observed_at_us,
        ),
        (
            CoreReference(pr_key, "pr_commit", oid, provenance_json),
            clock,
            observed_at_us,
        ),
    )
    relation = ResourceRelation(
        pr_key,
        "documents",
        (commit_doc,),
        provenance_json,
        canonical({"pr_commit": oid.full_oid}),
        observed_at_us,
    )
    return NormalizedContextUnit(
        primary_resource=commit_doc,
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
        observations=(
            ResourceObservation(pr_key, ()),
            ResourceObservation(commit_doc, tuple(fields)),
        ),
        text_admissions=tuple(text_admissions),
        extra_texts=(),
        relations=(relation,),
        core_references=core_refs,
    )


def normalize_pr_file(
    service_instance_uuidv4: str,
    pull_request_id: str | int,
    payload: dict[str, Any],
    observed_at_us: int | None,
    provenance_json: str,
) -> NormalizedContextUnit:
    """Normalize a GitHub PR file entry into Context metadata and patch text without retaining Git blobs."""
    if not isinstance(payload, dict):
        raise AcquisitionError("MALFORMED_PAYLOAD", "pr_file", "dict required")
    validate_observation_us(observed_at_us)
    json_value(provenance_json, provenance=True)
    pr_id = canonical_database_id(pull_request_id, "pull_request_id")
    pr_key = ResourceKey.from_native(service_instance_uuidv4, "pull_request", pr_id)
    filename = payload.get("filename")
    if not isinstance(filename, str) or not filename:
        raise AcquisitionError("FILENAME_REQUIRED", "pr_file", "filename required")
    file_doc = make_document_key(pr_key, "pr_file", "pr_file", filename)
    clock = FieldClock("github:pr_file:observation", None)
    fields: list[FieldCandidate] = [
        _candidate(
            file_doc, "filename", filename, clock, provenance_json, observed_at_us
        )
    ]
    for k in (
        "previous_filename",
        "status",
        "sha",
        "additions",
        "deletions",
        "changes",
        "blob_url",
        "raw_url",
        "contents_url",
    ):
        if k in payload:
            fields.append(
                _candidate(
                    file_doc, k, payload[k], clock, provenance_json, observed_at_us
                )
            )
    text_admissions: list[tuple[ResourceKey, str | None, FieldClock, str, int]] = []
    if "patch" in payload:
        patch = payload["patch"]
        if patch is not None and not isinstance(patch, str):
            raise AcquisitionError("INVALID_FIELD", "patch", "string or null required")
        fields.append(
            _candidate(file_doc, "patch", patch, clock, provenance_json, observed_at_us)
        )
        text_admissions.append(
            (file_doc, patch, clock, provenance_json, observed_at_us)
        )
    relation = ResourceRelation(
        pr_key,
        "documents",
        (file_doc,),
        provenance_json,
        canonical({"pr_file": filename}),
        observed_at_us,
    )
    return NormalizedContextUnit(
        primary_resource=file_doc,
        clock=clock,
        provenance_json=provenance_json,
        observed_at_us=observed_at_us,
        observations=(
            ResourceObservation(pr_key, ()),
            ResourceObservation(file_doc, tuple(fields)),
        ),
        text_admissions=tuple(text_admissions),
        extra_texts=(),
        relations=(relation,),
        core_references=(),
    )
