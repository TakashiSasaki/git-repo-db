"""Read-only PR assessments over original Context scope and verified Git metadata.

Completeness describes the requested captured metadata scope. It never attests
remote freshness, issuer authenticity, or ordinary repository-file availability.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass, replace

from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.application.query_pagination import (
    _paginate_items,
    validate_page_request,
)
from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_context import CoverageScope, ResourceKey, canonical
from repo_catalog.domain.p1_repository import (
    OID,
    RepositoryFailure,
    account_verification,
)
from repo_catalog.domain.pr_assessment import anchored_code_scope as anchored_code_scope
from repo_catalog.domain.pr_assessment import decode_git_role_checks
from repo_catalog.domain.query_contracts import PageRequest, PageResult, QueryError
from repo_catalog.domain.query_work import UnlimitedWorkBudget
from repo_catalog.domain.ref_observation import RefObservationKey

CODE_KINDS = ("pr_commits", "pr_files")
DOCUMENT_KINDS = ("reviews", "review_comments", "review_threads", "issue_comments")


def _spend(work, amount=1):
    work.require("metadata_units", amount)
    work.charge("metadata_units", amount)


def _cursor(_endpoint, key):
    if (
        type(key) is not tuple
        or len(key) != 3
        or any(type(part) is not str for part in key)
    ):
        raise ValueError("ResourceKey cursor required")
    ResourceKey(*key)


def _state(states):
    if "conflict" in states:
        return "conflict"
    if states and all(value == "complete" for value in states):
        return "complete"
    return (
        "partial"
        if any(value in {"complete", "partial"} for value in states)
        else "unknown"
    )


def _document_filters(value, endpoint):
    value = {} if value is None else value
    if type(value) is not dict or set(value) - {
        "state",
        "author",
        "resolved",
        "outdated",
    }:
        raise QueryError(
            "INVALID_INPUT", endpoint, "known document metadata filters required"
        )
    for key, expected in value.items():
        if expected is None:
            continue
        if key in {"resolved", "outdated"}:
            valid = type(expected) is bool
        else:
            valid = type(expected) is str and len(expected) <= 16384
        if not valid:
            raise QueryError(
                "INVALID_INPUT",
                endpoint,
                "typed bounded document metadata filter required",
            )
    return dict(value)


def _listing_kinds(value, endpoint):
    if (
        type(value) not in {list, tuple}
        or not value
        or any(type(kind) is not str or kind not in CODE_KINDS for kind in value)
    ):
        raise QueryError(
            "INVALID_INPUT", endpoint, "explicit code listing kinds required"
        )
    return tuple(sorted(set(value)))


def _traversal(original):
    evidence = json.loads(original).get("evidence")
    if (
        not isinstance(evidence, dict)
        or type(evidence.get("traversal_attempt_uuidv4")) is not str
    ):
        return None
    return canonical(
        [
            evidence.get("service_instance_uuidv4"),
            evidence.get("source_registration_uuidv4"),
            evidence["traversal_attempt_uuidv4"],
        ]
    )


@contextmanager
def _snapshot_for(service, supplied):
    if supplied is not None:
        yield supplied
    else:
        with service.open_snapshot(required_store="context") as snapshot:
            yield snapshot


@dataclass(frozen=True)
class PRAssessment:
    resource: ResourceKey
    state: str
    coverage: dict
    anchors: dict
    collections: tuple[dict, ...]
    page: object
    git_metadata: dict
    member_keys: tuple = ()

    def to_dict(self):
        return {
            "resource": list(self.resource.coordinates()),
            "state": self.state,
            "coverage": self.coverage,
            "anchors": self.anchors,
            "collections": list(self.collections),
            "git_metadata": self.git_metadata,
            "items": [view.to_dict() for view in self.page.items],
            "total_count": self.page.total_count,
            "has_more": self.page.has_more,
            "next_cursor": self.page.next_cursor,
            "snapshot_token": self.page.snapshot_token,
        }


@dataclass(frozen=True)
class PRParentAssessment:
    resource: ResourceKey
    assessment: PRAssessment
    resource_view: object | None = None

    def to_dict(self):
        result = self.assessment.to_dict()
        result.pop("items")
        result["document_count"] = result.pop("total_count")
        if self.resource_view is not None:
            result["resource_view"] = self.resource_view.to_dict()
        return result


@dataclass(frozen=True)
class PRRepositoryAssessment:
    repository: ResourceKey
    state: str
    coverage: dict
    parent_listing: dict
    page: object

    def to_dict(self):
        return {
            "repository": self.repository.coordinates(),
            "state": self.state,
            "coverage": self.coverage,
            "parent_listing": self.parent_listing,
            "items": [item.to_dict() for item in self.page.items],
            "total_count": self.page.total_count,
            "has_more": self.page.has_more,
            "next_cursor": self.page.next_cursor,
            "snapshot_token": self.page.snapshot_token,
        }


class PRQueryService(ProductionQueryService):
    """Full requested-scope preflight before paginating exact PR documents."""

    def _view(
        self, context, key, work, *, include_text=False, validate_repository=None
    ):
        # Reserve stored metadata before Python materialization. The same work
        # object follows every parent/child read in a repository assessment.
        projections = {
            "field_candidates": "field_name,value_json,clock_json,provenance_json",
            "resource_relations": "relation_kind,members_json,provenance_json,scope_json",
            "collections": "collection_kind,provenance_json,scope_json",
            "collection_terminals": "collection_kind,provenance_json,members_json",
            "repository_references": "role,object_format,object_oid,provenance_json",
            "resource_repository_relations": "relation_kind,clock_json,target_json,provenance_json",
        }
        size = 0
        for table, columns in projections.items():
            amount, count = context.db.execute(
                f"SELECT coalesce(sum(octet_length(json_array({columns}))),0),count(*) FROM {table} "
                "WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                key.coordinates(),
            ).fetchone()
            _spend(work, count + 1)
            size += amount
        if include_text:
            size += context.db.execute(
                "SELECT coalesce(sum(octet_length(text_value)),0) FROM text_bodies WHERE sha256 IN "
                "(SELECT text_body_sha256 FROM field_candidates WHERE service_instance_uuidv4=? "
                "AND resource_kind=? AND provider_resource_id=? AND field_name='text_body_sha256')",
                key.coordinates(),
            ).fetchone()[0]
        work.require("input_bytes", size)
        try:
            result = self._context_resource_in_snapshot(
                context,
                key,
                include_text=include_text,
                validate_repository=validate_repository,
            )
        except BaseException:
            work.abandon("input_bytes")
            raise
        work.charge("input_bytes", size)
        return result

    def _inputs(self, resource, page, max_work, max_bytes, endpoint, filters):
        resource = self._checked_resource_key(resource, endpoint)
        if resource.resource_kind != "pull_request":
            raise QueryError(
                "INVALID_INPUT", endpoint, "Pull Request ResourceKey required"
            )
        for limit in (max_work, max_bytes):
            if type(limit) is not int or not 0 < limit <= 100_000_000:
                raise QueryError(
                    "INVALID_INPUT", endpoint, "positive finite query bounds required"
                )
        page = validate_page_request(
            page, endpoint_kind=endpoint, filters=filters, cursor_validator=_cursor
        )
        work = UnlimitedWorkBudget(
            work_limits={
                "metadata_units": max_work,
                "input_bytes": max_bytes,
                "verification_bytes": 3 * max_bytes,
                "proof_steps": max_work,
            }
        )
        return resource, page, work

    def _document_matches(self, context, parent, key, filters, work):
        view = self._view(context, key, work)
        thread = None
        for field, expected in filters.items():
            subject = view
            if field in {"resolved", "outdated"} and key.resource_kind != "thread":
                links = {
                    member
                    for relation in view.relations
                    if relation.relation_kind == "in_thread"
                    for member in relation.members
                }
                if len(links) != 1:
                    return False, {
                        "kind": "metadata_filter",
                        "resource": key.coordinates(),
                        "field": field,
                        "state": "conflict" if len(links) > 1 else "unknown",
                        "reason": "filter_thread_unresolved",
                    }
                if thread is None:
                    thread = self._view(context, next(iter(links)), work)
                if (
                    thread.resource.resource_kind != "thread"
                    or thread.identifier_namespace != parent
                ):
                    return False, {
                        "kind": "metadata_filter",
                        "resource": key.coordinates(),
                        "field": field,
                        "state": "conflict",
                        "reason": "filter_thread_subject_mismatch",
                    }
                subject = thread
            values = {
                candidate.value_json for candidate in subject.fields.get(field, ())
            }
            if len(values) != 1:
                return False, {
                    "kind": "metadata_filter",
                    "resource": key.coordinates(),
                    "field": field,
                    "state": "conflict" if len(values) > 1 else "unknown",
                    "reason": "filter_field_unresolved",
                }
            actual = json.loads(next(iter(values)))
            expected_type = bool if field in {"resolved", "outdated"} else str
            if actual is not None and type(actual) is not expected_type:
                return False, {
                    "kind": "metadata_filter",
                    "resource": key.coordinates(),
                    "field": field,
                    "state": "unknown",
                    "reason": "filter_field_invalid",
                }
            if actual != expected:
                return False, None
        return True, None

    def _current_anchors(self, view, work):
        values, originals = {}, None
        for role in ("head", "base"):
            candidates = view.fields.get(role + "_object_oid", ())
            _spend(work, len(candidates) + 1)
            distinct = {candidate.value_json for candidate in candidates}
            if len(distinct) > 1:
                return None, (), "conflict", "current_anchor_conflict"
            if not distinct or next(iter(distinct)) == "null":
                return None, (), "unknown", "current_anchor_unavailable"
            raw = json.loads(next(iter(distinct)))
            try:
                values[role] = OID("sha1" if len(raw) == 40 else "sha256", raw)
            except (TypeError, ValueError):
                return None, (), "unknown", "current_anchor_invalid"
            evidence = {
                (
                    candidate.provenance_json,
                    candidate.clock.encode(),
                    candidate.observed_at_us,
                )
                for candidate in candidates
            }
            originals = evidence if originals is None else originals & evidence
        if (
            values["head"].object_format != values["base"].object_format
            or not originals
        ):
            return None, (), "unknown", "current_anchor_not_coobserved"
        # A merge target is an additional role only when the actual current
        # detail captured it alongside this exact comparison. An absent/null
        # merge target never fabricates a required Git object.
        merge = view.fields.get("merge_object_oid", ())
        distinct = {candidate.value_json for candidate in merge}
        _spend(work, len(merge))
        if len(distinct) > 1:
            return None, (), "conflict", "current_merge_anchor_conflict"
        if distinct and next(iter(distinct)) != "null":
            evidence = {
                (
                    candidate.provenance_json,
                    candidate.clock.encode(),
                    candidate.observed_at_us,
                )
                for candidate in merge
            }
            if not originals & evidence:
                return None, (), "unknown", "current_merge_anchor_not_coobserved"
            raw = json.loads(next(iter(distinct)))
            try:
                values["merge"] = OID(values["head"].object_format, raw)
            except (TypeError, ValueError):
                return None, (), "unknown", "current_merge_anchor_invalid"
        return values, {original[0] for original in originals}, "complete", None

    def _capture_rows(self, context, observation, work, *, code):
        scope = json.loads(observation.scope_json)
        provenances = (
            scope.get("member_provenance_jsons") if isinstance(scope, dict) else None
        )
        if code and (
            type(provenances) is not list
            or any(type(p) is not str for p in provenances)
        ):
            return None
        captured = []
        for member in observation.members:
            _spend(work)
            if not code:
                captured.append((member.coordinates(), ()))
                continue
            size = context.db.execute(
                "SELECT octet_length(json_array(identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id)) "
                "FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                member.coordinates(),
            ).fetchone()
            if size is None:
                return None
            work.require("input_bytes", size[0])
            try:
                identification = context.identification(member)
            except BaseException:
                work.abandon("input_bytes")
                raise
            work.charge("input_bytes", size[0])
            identity_field = (
                "sha" if observation.collection_kind == "pr_commits" else "filename"
            )
            document_kind = (
                "pr_commit"
                if observation.collection_kind == "pr_commits"
                else "pr_file"
            )
            if (
                member.service_instance_uuidv4
                != observation.resource.service_instance_uuidv4
                or identification.identifier_namespace_kind
                != observation.resource.resource_kind
                or identification.identifier_namespace_id
                != observation.resource.provider_resource_id
                or identification.document_kind != document_kind
            ):
                return None
            # Preflight reads semantic field values, not full result views or
            # text bodies for later pages. Capture provenance prevents mutable
            # current fields from rewriting an old listing comparison.
            size = context.db.execute(
                "SELECT coalesce(sum(octet_length(field_name)+octet_length(value_json)+octet_length(provenance_json)),0) "
                "FROM field_candidates WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                member.coordinates(),
            ).fetchone()[0]
            work.require("input_bytes", size)
            try:
                rows = context.db.execute(
                    "SELECT field_name,value_json,provenance_json FROM field_candidates WHERE "
                    "service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? "
                    "ORDER BY field_name,value_json,provenance_json",
                    member.coordinates(),
                ).fetchall()
            except BaseException:
                work.abandon("input_bytes")
                raise
            work.charge("input_bytes", size)
            _spend(work, len(rows))
            fields = sorted(
                {(row[0], row[1]) for row in rows if not code or row[2] in provenances}
            )
            unique_fields = {}
            for name, value in fields:
                _spend(work)
                if name in unique_fields and unique_fields[name] != value:
                    return None
                unique_fields[name] = value
            if unique_fields.get(identity_field) != identification.provider_document_id:
                return None
            if code and observation.collection_kind == "pr_commits":
                try:
                    anchor = OID(*scope["head_object_oid"])
                    for name, value in fields:
                        if name == "sha":
                            OID(anchor.object_format, json.loads(value))
                except (KeyError, TypeError, ValueError):
                    return None
            captured.append((member.coordinates(), fields))
        return tuple(sorted(captured))

    def _collection(
        self,
        context,
        view,
        kind,
        work,
        *,
        anchors=None,
        originals=(),
        code=False,
        traversal_ids=None,
        exact_comparison=False,
    ):
        candidates = []
        for observation in view.collections:
            _spend(work)
            if observation.collection_kind != kind:
                continue
            if (
                traversal_ids is not None
                and _traversal(observation.provenance_json) not in traversal_ids
            ):
                continue
            scope = json.loads(observation.scope_json)
            if not isinstance(scope, dict):
                continue
            if (code or exact_comparison) and (
                scope.get("head_object_oid") != list(anchors["head"].key)
                or scope.get("base_object_oid") != list(anchors["base"].key)
                or scope.get("anchor_provenance_json") not in originals
            ):
                continue
            coverage_kind = scope.get("coverage_kind", kind)
            coverage = context.coverage(
                CoverageScope.collection(
                    view.resource, kind, observation.provenance_json, coverage_kind
                )
            )
            state = coverage.state
            if observation.state != "complete" and state == "complete":
                state = "partial"
            signature = self._capture_rows(context, observation, work, code=code)
            reason = "terminal_unproven" if state == "unknown" else None
            if signature is None:
                state, reason = "unknown", "captured_member_facts_unavailable"
            if kind == "git_role_checks":
                try:
                    checks = decode_git_role_checks(scope)
                    signature = sorted(
                        {
                            canonical(
                                [
                                    check["role"],
                                    check["expected_oid"],
                                    check["ref_name_hex"],
                                    check["actual_oid"],
                                ]
                            )
                            for check in checks
                        }
                    )
                except ValueError:
                    signature, state, reason = (
                        None,
                        "unknown",
                        "native_ref_checks_invalid",
                    )
            expected = scope.get("expected_count")
            if code:
                count_name = "commits" if kind == "pr_commits" else "changed_files"
                count_candidates = view.fields.get(count_name, ())
                counts = {candidate.value_json for candidate in count_candidates}
                comparison_originals = {
                    (
                        candidate.provenance_json,
                        candidate.clock.encode(),
                        candidate.observed_at_us,
                    )
                    for candidate in view.fields.get("head_object_oid", ())
                } & {
                    (
                        candidate.provenance_json,
                        candidate.clock.encode(),
                        candidate.observed_at_us,
                    )
                    for candidate in view.fields.get("base_object_oid", ())
                }
                actual_count = (
                    json.loads(next(iter(counts))) if len(counts) == 1 else None
                )
                count_checked = (
                    type(actual_count) is int
                    and actual_count >= 0
                    and any(
                        (
                            candidate.provenance_json,
                            candidate.clock.encode(),
                            candidate.observed_at_us,
                        )
                        in comparison_originals
                        for candidate in count_candidates
                    )
                )
                if len(counts) > 1:
                    state, reason = "conflict", "current_reported_count_conflict"
                elif counts and (type(actual_count) is not int or actual_count < 0):
                    state, reason = "unknown", "current_reported_count_invalid"
                elif expected is not None and (
                    type(expected) is not int
                    or expected < 0
                    or len(observation.members) != expected
                ):
                    state, reason = "partial", "reported_count_mismatch"
                elif (
                    expected is None
                    and count_checked
                    and len(observation.members) != actual_count
                ):
                    state, reason = "partial", "current_reported_count_mismatch"
                elif counts and (
                    (expected is None and not count_checked)
                    or (expected is not None and expected != actual_count)
                ):
                    state, reason = "unknown", "current_reported_count_not_checked"
                elif (
                    expected is None
                    and not count_checked
                    and len(observation.members)
                    >= (250 if kind == "pr_commits" else 3000)
                ):
                    state, reason = "partial", "provider_listing_limit_unproven"
            candidates.append(
                {
                    "observation": observation,
                    "state": state,
                    "reason": reason,
                    "signature": signature,
                }
            )
        if not candidates:
            return {
                "kind": kind,
                "state": "unknown",
                "reason": "matching_listing_unavailable",
                "members": (),
                "alternatives": (),
            }
        # Prefix terminals from the same actual traversal are progress, not
        # independent equal-clock captures. Its explicit source ordinal orders
        # those reports; unrelated traversals remain alternatives.
        traversals = {}
        for candidate in candidates:
            obs = candidate["observation"]
            evidence = json.loads(obs.provenance_json).get("evidence")
            token, ordinal = canonical([obs.provenance_json, obs.observed_at_us]), 0
            if isinstance(evidence, dict) and isinstance(
                evidence.get("terminal_report"), dict
            ):
                attempt = evidence.get("traversal_attempt_uuidv4")
                index = evidence["terminal_report"].get("ordinal")
                if isinstance(attempt, str) and type(index) is int and index > 0:
                    token, ordinal = (
                        canonical(
                            [
                                evidence.get("service_instance_uuidv4"),
                                evidence.get("source_registration_uuidv4"),
                                attempt,
                            ]
                        ),
                        index,
                    )
            traversals.setdefault(token, []).append((ordinal, candidate))
        candidates = []
        for entries in traversals.values():
            entries.sort(key=lambda entry: entry[0])
            highest = entries[-1][0]
            finalists = [entry[1] for entry in entries if entry[0] == highest]
            final = finalists[0]
            final_members = set(final["observation"].members)
            if (
                any(
                    not set(entry[1]["observation"].members) <= final_members
                    for entry in entries
                )
                or len(
                    {
                        canonical([entry["state"], entry["signature"]])
                        for entry in finalists
                    }
                )
                > 1
            ):
                final = {
                    **final,
                    "state": "conflict",
                    "reason": "traversal_prefix_conflict",
                }
            # Source-reported progress checksums are recomputed, never trusted
            # as a replacement for the actual typed member prefix.
            for _, entry in entries:
                observation = entry["observation"]
                evidence = json.loads(observation.provenance_json).get("evidence")
                terminal = (
                    evidence.get("terminal_report")
                    if isinstance(evidence, dict)
                    else None
                )
                if isinstance(terminal, dict) and "member_prefix_sha256" in terminal:
                    actual = hashlib.sha256(
                        canonical(
                            [list(m.coordinates()) for m in observation.members]
                        ).encode()
                    ).hexdigest()
                    if actual != terminal["member_prefix_sha256"]:
                        final = {
                            **final,
                            "state": "conflict",
                            "reason": "traversal_prefix_digest_mismatch",
                        }
            candidates.append(final)
        latest = max(entry["observation"].observed_at_us for entry in candidates)
        candidates = [
            entry
            for entry in candidates
            if entry["observation"].observed_at_us == latest
        ]
        signatures = {
            canonical([entry["state"], entry["signature"]]) for entry in candidates
        }
        state = "conflict" if len(signatures) > 1 else candidates[0]["state"]
        members = () if state == "conflict" else candidates[0]["observation"].members
        return {
            "kind": kind,
            "state": state,
            "reason": "equal_clock_listing_conflict"
            if len(signatures) > 1
            else candidates[0]["reason"],
            "members": members,
            "alternatives": tuple(
                {
                    "provenance_json": entry["observation"].provenance_json,
                    "scope_json": entry["observation"].scope_json,
                    "observed_at_us": latest,
                    "state": entry["state"],
                    "member_count": len(entry["observation"].members),
                }
                for entry in candidates
            ),
        }

    def _git(self, repository_store, anchors, work):
        if repository_store is None:
            return {
                "state": "unknown",
                "reason": "repository_unavailable",
                "verified_objects": 0,
            }
        pending = [(target, "commit") for target in anchors.values()]
        checked = {}
        while pending:
            object_oid, expected_kind = pending.pop()
            if object_oid in checked:
                if checked[object_oid] != expected_kind:
                    return {
                        "state": "conflict",
                        "reason": "role_target_type_conflict",
                        "object_oid": list(object_oid.key),
                        "verified_objects": len(checked),
                    }
                continue
            _spend(work)
            copies = repository_store.sql(
                "SELECT physical_copy_uuidv4 FROM retained_metadata WHERE object_format=? "
                "AND object_oid=? ORDER BY physical_copy_uuidv4 LIMIT 1",
                object_oid.key,
            )
            if not copies:
                missing = repository_store.sql(
                    "SELECT 1 FROM intrinsic_claims WHERE object_format=? AND object_oid=? "
                    "UNION ALL SELECT 1 FROM intrinsic_groups WHERE object_format=? AND object_oid=? LIMIT 1",
                    (*object_oid.key, *object_oid.key),
                )
                if missing:
                    repository_store._integrity_stop(
                        (object_oid, "lost-retained-metadata-copy")
                    )
                # Metadata-only input remains valid, but cannot prove retained
                # structural metadata availability for this requested comparison.
                return {
                    "state": "partial",
                    "reason": "role_metadata_unavailable",
                    "object_oid": list(object_oid.key),
                    "verified_objects": len(checked),
                }
            row = repository_store.read_metadata_copy(object_oid, copies[0][0], work)
            if row["native_type"] != expected_kind:
                return {
                    "state": "conflict",
                    "reason": "role_target_type_conflict",
                    "object_oid": list(object_oid.key),
                    "verified_objects": len(checked),
                }
            with account_verification(work):
                metadata = parse_metadata(
                    object_oid.object_format, row["native_type"], row["body"]
                )
            checked[object_oid] = row["native_type"]
            for name, relations in metadata.relations.items():
                _spend(work, len(relations))
                for member in relations:
                    if name == "tree_entries":
                        if member[0][0] != "40000":
                            continue  # Ordinary blobs and gitlinks are outside metadata closure.
                        target_kind = "tree"
                    else:
                        target_kind = "tree" if name == "commit_tree" else "commit"
                    pending.append((OID(member[1], member[2]), target_kind))
        return {"state": "complete", "reason": None, "verified_objects": len(checked)}

    def _review_roles(self, context, view, anchors, work):
        """Known captured review targets add roles, never a review-universe claim."""
        members = {
            key
            for relation in view.relations
            if relation.relation_kind == "reviews"
            for key in relation.members
        }
        for observation in view.collections:
            if observation.collection_kind == "reviews":
                members.update(observation.members)
        roles = dict(anchors)
        for member in sorted(members, key=lambda key: key.coordinates()):
            _spend(work)
            child = self._view(context, member, work)
            if (
                child.identifier_namespace != view.resource
                or child.document_kind != "review_summary"
            ):
                return roles, "conflict", "review_target_subject_mismatch"
            candidates = child.fields.get("target_commit_object_oid", ())
            values = {candidate.value_json for candidate in candidates}
            if len(values) > 1:
                return roles, "conflict", "current_review_target_conflict"
            if not values or next(iter(values)) == "null":
                continue
            try:
                target = OID(
                    anchors["head"].object_format, json.loads(next(iter(values)))
                )
            except (ValueError, TypeError):
                return roles, "unknown", "current_review_target_invalid"
            roles["review_target:" + member.provider_resource_id] = target
        return roles, "complete", None

    def _role_checks(self, snapshot, view, anchors, originals, work):
        listing = self._collection(
            snapshot.context,
            view,
            "git_role_checks",
            work,
            anchors=anchors,
            originals=originals,
            exact_comparison=True,
        )
        if not listing["alternatives"]:
            return {"state": "complete", "reason": "not_reported", "checked": 0}
        result = {"state": listing["state"], "reason": listing["reason"], "checked": 0}
        if listing["state"] in {"conflict", "unknown"}:
            return result
        if snapshot.repository_store is None:
            return {
                "state": "unknown",
                "reason": "native_ref_evidence_unavailable",
                "checked": 0,
            }
        for alternative in listing["alternatives"]:
            scope = json.loads(alternative["scope_json"])
            for check in decode_git_role_checks(scope):
                _spend(work)
                expected = OID(*check["expected_oid"])
                if anchors.get(check["role"]) != expected:
                    return {
                        **result,
                        "state": "unknown",
                        "reason": "native_ref_comparison_mismatch",
                    }
                try:
                    projection = snapshot.repository_store.ref_observation(
                        RefObservationKey(*check["ref_observation_key"]), work
                    )
                except RepositoryFailure as error:
                    if error.code != "OBSERVATION_UNAVAILABLE":
                        raise
                    return {
                        **result,
                        "state": "unknown",
                        "reason": "native_ref_evidence_unavailable",
                    }
                if projection.ref_observation.ref_name_bytes.hex() != check[
                    "ref_name_hex"
                ] or (
                    "repository_uuidv4" in scope
                    and projection.ref_observation.repository_uuidv4
                    != scope["repository_uuidv4"]
                ):
                    return {
                        **result,
                        "state": "unknown",
                        "reason": "native_ref_subject_mismatch",
                    }
                if projection.conflict:
                    return {
                        **result,
                        "state": "conflict",
                        "reason": "native_ref_evidence_conflict",
                    }
                presence = {claim.presence_state for claim in projection.claims}
                if presence == {"absent"}:
                    targets = {None}
                elif presence == {"present"}:
                    targets = {
                        claim.resolved_target_object_oid
                        for claim in projection.claims
                        if claim.resolved_target_object_oid is not None
                    }
                    if not targets:
                        targets = {
                            claim.direct_target_object_oid
                            for claim in projection.claims
                            if claim.direct_target_object_oid is not None
                        }
                else:
                    targets = set()
                if len(targets) != 1:
                    return {
                        **result,
                        "state": "unknown",
                        "reason": "native_ref_target_unresolved",
                    }
                actual = next(iter(targets))
                reported = (
                    OID(*check["actual_oid"])
                    if check["actual_oid"] is not None
                    else None
                )
                if actual != reported:
                    return {
                        **result,
                        "state": "unknown",
                        "reason": "native_ref_report_mismatch",
                    }
                result["checked"] += 1
                if actual != expected:
                    return {
                        **result,
                        "state": "partial",
                        "reason": "native_ref_target_changed",
                        "role": check["role"],
                        "expected_oid": list(expected.key),
                        "actual_oid": list(actual.key) if actual else None,
                    }
        return result

    def _page(
        self, snapshot, members, page, endpoint, filters, work, *, preflight=False
    ):
        if preflight:
            return PageResult(
                (), snapshot.token.encode(), None, False, len(set(members))
            )
        selected = _paginate_items(
            set(members),
            key_fn=lambda key: key.coordinates(),
            page=page,
            endpoint_kind=endpoint,
            filters=filters,
            snapshot_token=snapshot.token.encode(),
            cursor_validator=_cursor,
        )
        return replace(
            selected,
            items=tuple(
                self._view(
                    snapshot.context,
                    key,
                    work,
                    include_text=True,
                    validate_repository=self._context_repository_resolver(snapshot),
                )
                for key in selected.items
            ),
        )

    def get_pr_code(
        self,
        resource,
        *,
        page=PageRequest(),
        require_git=True,
        listing_kinds=CODE_KINDS,
        max_work=100000,
        max_bytes=16 * 1024 * 1024,
    ):
        return self._assess_pr_code(
            resource,
            page=page,
            require_git=require_git,
            listing_kinds=listing_kinds,
            max_work=max_work,
            max_bytes=max_bytes,
        )

    def _assess_pr_code(
        self,
        resource,
        *,
        page=PageRequest(),
        require_git=True,
        listing_kinds=CODE_KINDS,
        max_work=100000,
        max_bytes=16 * 1024 * 1024,
        snapshot=None,
        shared_work=None,
        preflight=False,
    ):
        listing_kinds = _listing_kinds(listing_kinds, "pr-code")
        if type(require_git) is not bool:
            raise QueryError("INVALID_INPUT", "pr-code", "bool require_git required")
        resource = self._checked_resource_key(resource, "pr-code")
        filters = {
            "resource": list(resource.coordinates()),
            "require_git": require_git,
            "listing_kinds": listing_kinds,
            "max_work": max_work,
            "max_bytes": max_bytes,
        }
        resource, page, work = self._inputs(
            resource, page, max_work, max_bytes, "pr-code", filters
        )
        work = shared_work if shared_work is not None else work
        try:
            with _snapshot_for(self, snapshot) as snapshot:
                view = self._view(snapshot.context, resource, work, include_text=False)
                anchors, originals, anchor_state, reason = self._current_anchors(
                    view, work
                )
                collections = (
                    []
                    if anchors is None
                    else [
                        self._collection(
                            snapshot.context,
                            view,
                            kind,
                            work,
                            anchors=anchors,
                            originals=originals,
                            code=True,
                        )
                        for kind in listing_kinds
                    ]
                )
                if anchors is not None and require_git:
                    anchors, role_state, role_reason = self._review_roles(
                        snapshot.context, view, anchors, work
                    )
                    git = (
                        self._git(snapshot.repository_store, anchors, work)
                        if role_state == "complete"
                        else {
                            "state": role_state,
                            "reason": role_reason,
                            "verified_objects": 0,
                        }
                    )
                else:
                    git = {
                        "state": "complete" if not require_git else "unknown",
                        "reason": "not_requested" if not require_git else reason,
                    }
                ref_checks = (
                    self._role_checks(snapshot, view, anchors, originals, work)
                    if anchors is not None and require_git
                    else {"state": "complete", "reason": "not_requested", "checked": 0}
                )
                git = {**git, "ref_checks": ref_checks}
                states = [
                    anchor_state,
                    *(collection["state"] for collection in collections),
                ]
                if require_git:
                    states.append(git["state"])
                    states.append(ref_checks["state"])
                state = _state(states)
                members = [
                    key for collection in collections for key in collection["members"]
                ]
                selected = self._page(
                    snapshot,
                    () if state == "conflict" else members,
                    page,
                    "pr-code",
                    filters,
                    work,
                    preflight=preflight,
                )
                missing = (
                    [{"kind": "anchors", "state": anchor_state, "reason": reason}]
                    if reason
                    else []
                ) + [
                    {
                        "kind": entry["kind"],
                        "state": entry["state"],
                        "reason": entry["reason"],
                    }
                    for entry in collections
                    if entry["state"] != "complete"
                ]
                if require_git and git["state"] != "complete":
                    missing.append({"kind": "git_metadata", **git})
                if require_git and ref_checks["state"] != "complete":
                    missing.append({"kind": "git_role_checks", **ref_checks})
                return PRAssessment(
                    resource,
                    state,
                    {
                        "complete_for_requested_scope": state == "complete",
                        "missing": missing,
                    },
                    {role: list(oid.key) for role, oid in (anchors or {}).items()},
                    tuple(
                        {k: v for k, v in entry.items() if k != "members"}
                        for entry in collections
                    ),
                    selected,
                    git,
                    tuple(set(members)),
                )
        except RepositoryFailure as error:
            if error.code in {"BUDGET", "QUERY_BUDGET"}:
                raise QueryError(
                    "QUERY_BUDGET",
                    "pr-code",
                    "full-scope assessment exceeded finite budget",
                ) from error
            raise

    def get_pr_code_capture(
        self,
        resource,
        kind,
        provenance_json,
        *,
        page=PageRequest(),
        require_git=False,
        max_work=100000,
        max_bytes=16 * 1024 * 1024,
    ):
        """Read one historical original listing, without asserting current PR state.

        Only still-retained attributes from this listing's original member reads
        are shown. Context does not archive normalized API edit history.
        """
        endpoint = "pr-code-capture"
        _listing_kinds((kind,), endpoint)
        if (
            type(require_git) is not bool
            or type(provenance_json) is not str
            or not provenance_json
            or len(provenance_json) > 1024 * 1024
        ):
            raise QueryError(
                "INVALID_INPUT",
                endpoint,
                "bounded original provenance and bool options required",
            )
        filters = {
            "resource": list(
                self._checked_resource_key(resource, endpoint).coordinates()
            ),
            "kind": kind,
            "provenance_json": provenance_json,
            "require_git": require_git,
            "max_work": max_work,
            "max_bytes": max_bytes,
        }
        resource, page, work = self._inputs(
            resource, page, max_work, max_bytes, endpoint, filters
        )
        try:
            with self.open_snapshot(required_store="context") as snapshot:
                view = self._view(snapshot.context, resource, work)
                matches = tuple(
                    observation
                    for observation in view.collections
                    if observation.collection_kind == kind
                    and observation.provenance_json == provenance_json
                )
                if not matches:
                    raise QueryError(
                        "CAPTURE_NOT_FOUND", endpoint, "original listing not retained"
                    )
                scopes = {observation.scope_json for observation in matches}
                if len(scopes) != 1:
                    raise QueryError(
                        "CAPTURE_CONFLICT",
                        endpoint,
                        "original listing has conflicting scopes",
                    )
                scope = json.loads(next(iter(scopes)))
                anchors = None
                originals = ()
                member_originals = ()
                if isinstance(scope, dict):
                    try:
                        head, base = (
                            OID(*scope["head_object_oid"]),
                            OID(*scope["base_object_oid"]),
                        )
                        original = scope["anchor_provenance_json"]
                        members = scope["member_provenance_jsons"]
                        if (
                            head.object_format != base.object_format
                            or type(original) is not str
                            or type(members) is not list
                            or any(type(value) is not str for value in members)
                        ):
                            raise ValueError("invalid captured comparison")
                        anchors = {"head": head, "base": base}
                        originals, member_originals = (original,), tuple(members)
                    except (KeyError, TypeError, ValueError):
                        pass
                # Empty current fields deliberately suppress current count/anchor
                # inference when qualifying this historical original scope.
                capture = replace(view, fields={}, collections=matches)
                listing = self._collection(
                    snapshot.context,
                    capture,
                    kind,
                    work,
                    anchors=anchors,
                    originals=originals,
                    code=anchors is not None,
                )
                if anchors is None:
                    listing = {
                        **listing,
                        "state": "unknown",
                        "reason": "captured_comparison_unavailable",
                    }
                git = (
                    self._git(snapshot.repository_store, anchors, work)
                    if require_git and anchors is not None
                    else {
                        "state": "unknown" if require_git else "complete",
                        "reason": "captured_comparison_unavailable"
                        if require_git
                        else "not_requested",
                    }
                )
                state = _state(
                    [listing["state"], git["state"]]
                    if require_git
                    else [listing["state"]]
                )
                members = () if listing["state"] == "conflict" else listing["members"]
                selected = _paginate_items(
                    set(members),
                    key_fn=lambda key: key.coordinates(),
                    page=page,
                    endpoint_kind=endpoint,
                    filters=filters,
                    snapshot_token=snapshot.token.encode(),
                    cursor_validator=_cursor,
                )
                items = []
                for key in selected.items:
                    current = self._view(snapshot.context, key, work)
                    fields = {
                        name: tuple(
                            candidate
                            for candidate in candidates
                            if candidate.provenance_json in member_originals
                        )
                        for name, candidates in current.fields.items()
                    }
                    fields = {
                        name: candidates
                        for name, candidates in fields.items()
                        if candidates
                    }
                    items.append(
                        replace(
                            current,
                            fields=fields,
                            resolved_texts={},
                            relations=(),
                            collections=(),
                            repository_uuidv4=None,
                            repository_roles=(),
                            repository_relations=(),
                            repository_dependencies=(),
                        )
                    )
                selected = replace(selected, items=tuple(items))
                missing = []
                if listing["state"] != "complete":
                    missing.append(
                        {
                            "kind": kind,
                            "state": listing["state"],
                            "reason": listing["reason"],
                        }
                    )
                if require_git and git["state"] != "complete":
                    missing.append({"kind": "git_metadata", **git})
                return PRAssessment(
                    resource,
                    state,
                    {
                        "scope_kind": "captured_listing",
                        "current_provider_state_asserted": False,
                        "complete_for_requested_scope": state == "complete",
                        "missing": missing,
                    },
                    {role: list(oid.key) for role, oid in (anchors or {}).items()},
                    (
                        {
                            key: value
                            for key, value in listing.items()
                            if key != "members"
                        },
                    ),
                    selected,
                    git,
                    tuple(set(members)),
                )
        except RepositoryFailure as error:
            if error.code in {"BUDGET", "QUERY_BUDGET"}:
                raise QueryError(
                    "QUERY_BUDGET", endpoint, "captured listing exceeded finite budget"
                ) from error
            raise

    def get_pr_documents(
        self,
        resource,
        *,
        kinds=DOCUMENT_KINDS,
        page=PageRequest(),
        require_text=True,
        thread_id=None,
        path=None,
        commit=None,
        metadata_filters=None,
        max_work=100000,
        max_bytes=16 * 1024 * 1024,
    ):
        return self._assess_pr_documents(
            resource,
            kinds=kinds,
            page=page,
            require_text=require_text,
            thread_id=thread_id,
            path=path,
            commit=commit,
            metadata_filters=metadata_filters,
            max_work=max_work,
            max_bytes=max_bytes,
        )

    def _assess_pr_documents(
        self,
        resource,
        *,
        kinds=DOCUMENT_KINDS,
        page=PageRequest(),
        require_text=True,
        thread_id=None,
        path=None,
        commit=None,
        metadata_filters=None,
        max_work=100000,
        max_bytes=16 * 1024 * 1024,
        snapshot=None,
        shared_work=None,
        preflight=False,
    ):
        metadata_filters = _document_filters(metadata_filters, "pr-documents")
        if (
            type(kinds) not in {tuple, list}
            or any(type(kind) is not str for kind in kinds)
            or not kinds
            or not set(kinds) <= set(DOCUMENT_KINDS)
            or type(require_text) is not bool
        ):
            raise QueryError(
                "INVALID_INPUT",
                "pr-documents",
                "explicit kinds and bool options required",
            )
        resource = self._checked_resource_key(resource, "pr-documents")
        for value in (thread_id, path):
            if value is not None and (
                type(value) is not str or not value or len(value) > 16384
            ):
                raise QueryError(
                    "INVALID_INPUT",
                    "pr-documents",
                    "bounded nonempty selector required",
                )
        if commit is not None and type(commit) is not OID:
            raise QueryError(
                "INVALID_INPUT", "pr-documents", "typed commit OID required"
            )
        if thread_id is not None:
            kinds = ("review_threads",)
        filters = {
            "resource": list(resource.coordinates()),
            "kinds": sorted(set(kinds)),
            "require_text": require_text,
            "max_work": max_work,
            "max_bytes": max_bytes,
            "thread_id": thread_id,
            "path": path,
            "commit": list(commit.key) if commit else None,
            "metadata_filters": metadata_filters,
        }
        resource, page, work = self._inputs(
            resource, page, max_work, max_bytes, "pr-documents", filters
        )
        work = shared_work if shared_work is not None else work
        try:
            with _snapshot_for(self, snapshot) as snapshot:
                view = self._view(snapshot.context, resource, work, include_text=False)
                if thread_id is None:
                    collections = [
                        self._collection(snapshot.context, view, kind, work)
                        for kind in sorted(set(kinds))
                    ]
                else:
                    selected_thread = ResourceKey.document(
                        resource, "thread", "thread", thread_id
                    )
                    root_listing = self._collection(
                        snapshot.context, view, "review_threads", work
                    )
                    traversal_ids = {
                        _traversal(row["provenance_json"])
                        for row in root_listing["alternatives"]
                    }
                    traversal_ids.discard(None)
                    if (
                        selected_thread not in root_listing["members"]
                        or not traversal_ids
                    ):
                        collections = [
                            {
                                "kind": "review_thread_comments",
                                "state": "conflict"
                                if root_listing["state"] == "conflict"
                                else "unknown",
                                "reason": "selected_thread_root_unavailable",
                                "members": (),
                                "alternatives": (),
                            }
                        ]
                    else:
                        child = self._view(
                            snapshot.context, selected_thread, work, include_text=False
                        )
                        collections = [
                            self._collection(
                                snapshot.context,
                                child,
                                "review_thread_comments",
                                work,
                                traversal_ids=traversal_ids,
                            )
                        ]
                members = [
                    key for collection in collections for key in collection["members"]
                ]
                missing = [
                    {
                        "kind": entry["kind"],
                        "state": entry["state"],
                        "reason": entry["reason"],
                    }
                    for entry in collections
                    if entry["state"] != "complete"
                ]
                for key in tuple(members):
                    _spend(work)
                    if key.resource_kind == "thread":
                        child = self._view(
                            snapshot.context, key, work, include_text=False
                        )
                        root_listing = next(
                            entry
                            for entry in collections
                            if entry["kind"] == "review_threads"
                        )
                        traversal_ids = {
                            _traversal(row["provenance_json"])
                            for row in root_listing["alternatives"]
                        }
                        traversal_ids.discard(None)
                        replies = self._collection(
                            snapshot.context,
                            child,
                            "review_thread_comments",
                            work,
                            traversal_ids=traversal_ids,
                        )
                        members.extend(replies["members"])
                        if replies["state"] != "complete":
                            missing.append(
                                {
                                    "kind": "review_thread_comments",
                                    "resource": key.coordinates(),
                                    "reason": replies["reason"],
                                }
                            )
                if require_text:
                    for key in set(members):
                        _spend(work)
                        if key.resource_kind == "thread":
                            continue
                        candidates = snapshot.context.candidates(
                            key, "text_body_sha256"
                        )
                        if not candidates or any(
                            candidate.value_json == "null" for candidate in candidates
                        ):
                            missing.append(
                                {
                                    "kind": "text_body",
                                    "resource": key.coordinates(),
                                    "reason": "body_unavailable",
                                }
                            )
                        elif (
                            len({candidate.value_json for candidate in candidates}) > 1
                        ):
                            missing.append(
                                {
                                    "kind": "text_body",
                                    "resource": key.coordinates(),
                                    "reason": "body_conflict",
                                }
                            )
                if path is not None or commit is not None:
                    anchors, originals, anchor_state, anchor_reason = (
                        self._current_anchors(view, work)
                    )
                    if anchors is None:
                        missing.append(
                            {"kind": "code_selector", "reason": anchor_reason}
                        )
                    else:
                        for kind in CODE_KINDS:
                            listing = self._collection(
                                snapshot.context,
                                view,
                                kind,
                                work,
                                anchors=anchors,
                                originals=originals,
                                code=True,
                            )
                            if listing["state"] != "complete":
                                missing.append(
                                    {
                                        "kind": "code_selector",
                                        "reason": listing["reason"],
                                    }
                                )
                        if (
                            commit is not None
                            and commit.object_format != anchors["head"].object_format
                        ):
                            missing.append(
                                {
                                    "kind": "code_selector",
                                    "reason": "selector_object_format_mismatch",
                                }
                            )
                        # Provider document selectors qualify captured Provider
                        # listing/field facts. Native byte availability and live
                        # Git ref checks are a separately requested code scope.
                    filtered = []
                    for key in members:
                        values = []
                        for field, requested in (
                            ("raw_path", path),
                            (
                                "target_commit_object_oid",
                                commit.object_oid if commit else None,
                            ),
                        ):
                            if requested is None:
                                continue
                            candidates = {
                                candidate.value_json
                                for candidate in snapshot.context.candidates(key, field)
                            }
                            if len(candidates) != 1:
                                missing.append(
                                    {
                                        "kind": "metadata_filter",
                                        "resource": key.coordinates(),
                                        "reason": "filter_field_unresolved",
                                    }
                                )
                                values.append(False)
                            else:
                                values.append(
                                    json.loads(next(iter(candidates))) == requested
                                )
                        if all(values):
                            filtered.append(key)
                    members = filtered
                if metadata_filters:
                    filtered = []
                    for key in members:
                        matches, gap = self._document_matches(
                            snapshot.context, resource, key, metadata_filters, work
                        )
                        if gap is not None:
                            missing.append(gap)
                        if matches:
                            filtered.append(key)
                    members = filtered
                state = _state([entry["state"] for entry in collections])
                if missing and state == "complete":
                    state = (
                        "conflict"
                        if any(gap.get("state") == "conflict" for gap in missing)
                        else "partial"
                    )
                selected = self._page(
                    snapshot,
                    members,
                    page,
                    "pr-documents",
                    filters,
                    work,
                    preflight=preflight,
                )
                return PRAssessment(
                    resource,
                    state,
                    {
                        "complete_for_requested_scope": state == "complete",
                        "missing": missing,
                    },
                    {},
                    tuple(
                        {k: v for k, v in entry.items() if k != "members"}
                        for entry in collections
                    ),
                    selected,
                    {"state": "not_applicable", "reason": "document_scope"},
                    tuple(set(members)),
                )
        except RepositoryFailure as error:
            if error.code in {"BUDGET", "QUERY_BUDGET"}:
                raise QueryError(
                    "QUERY_BUDGET",
                    "pr-documents",
                    "full-scope assessment exceeded finite budget",
                ) from error
            raise

    def _literal_matches(self, context, parent_view, member_keys, literal, work):
        if literal is None:
            return True
        for candidate in parent_view.fields.get("title", ()):
            value = json.loads(candidate.value_json)
            if type(value) is str and literal in value:
                return True
        keys = set(member_keys)
        for relation in parent_view.relations:
            if relation.relation_kind == "documents":
                keys.update(relation.members)
        for key in keys:
            _spend(work)
            for candidate in context.candidates(key, "text_body_sha256"):
                digest = json.loads(candidate.value_json)
                if digest is None:
                    continue
                size = context.db.execute(
                    "SELECT octet_length(text_value) FROM text_bodies WHERE sha256=?",
                    (digest,),
                ).fetchone()
                if size is None:
                    context.read_text(
                        digest
                    )  # Existing retained-body integrity classifier owns this failure.
                    continue
                work.require("input_bytes", size[0])
                try:
                    text = context.read_text(digest)
                except BaseException:
                    work.abandon("input_bytes")
                    raise
                work.charge("input_bytes", size[0])
                if literal in text:
                    return True
        return False

    def list_pr_assessments(
        self,
        repository,
        *,
        parents=None,
        assessment="documents",
        kinds=DOCUMENT_KINDS,
        listing_kinds=CODE_KINDS,
        page=PageRequest(),
        require_git=True,
        require_text=True,
        state=None,
        draft=None,
        author=None,
        text_literal=None,
        path=None,
        commit=None,
        metadata_filters=None,
        max_work=100000,
        max_bytes=16 * 1024 * 1024,
    ):
        """Assess the actual requested parent universe before paginating rows.

        Metadata/text filters select displayed results, never erase preflight
        gaps. A finite positive parent selection can exclude unrelated subjects;
        omitted selection requires the Provider Repository's real PR listing.
        """
        metadata_filters = _document_filters(metadata_filters, "pr-list")
        listing_kinds = _listing_kinds(listing_kinds, "pr-list")
        if assessment == "documents" and set(listing_kinds) != set(CODE_KINDS):
            raise QueryError(
                "INVALID_INPUT", "pr-list", "code listing selection requires code mode"
            )
        repository = self._checked_resource_key(repository, "pr-list")
        if repository.resource_kind != "repository" or assessment not in {
            "documents",
            "code",
        }:
            raise QueryError(
                "INVALID_INPUT",
                "pr-list",
                "Provider Repository and code/documents mode required",
            )
        if (
            type(require_git) is not bool
            or type(require_text) is not bool
            or draft is not None
            and type(draft) is not bool
        ):
            raise QueryError("INVALID_INPUT", "pr-list", "strict bool options required")
        for value in (state, author, text_literal):
            if value is not None and (type(value) is not str or len(value) > 16384):
                raise QueryError(
                    "INVALID_INPUT", "pr-list", "bounded text filter required"
                )
        if type(kinds) not in {list, tuple} or any(
            type(kind) is not str for kind in kinds
        ):
            raise QueryError(
                "INVALID_INPUT", "pr-list", "explicit document kinds required"
            )
        if parents is not None:
            if type(parents) is not tuple:
                raise QueryError(
                    "INVALID_INPUT", "pr-list", "explicit parent tuple required"
                )
            parents = tuple(
                self._checked_resource_key(key, "pr-list") for key in parents
            )
            if any(
                key.resource_kind != "pull_request"
                or key.service_instance_uuidv4 != repository.service_instance_uuidv4
                for key in parents
            ):
                raise QueryError(
                    "INVALID_INPUT", "pr-list", "same-Service PR parents required"
                )
            parents = tuple(sorted(set(parents), key=lambda key: key.coordinates()))
        for bound in (max_work, max_bytes):
            if type(bound) is not int or not 0 < bound <= 100_000_000:
                raise QueryError(
                    "INVALID_INPUT", "pr-list", "finite positive bounds required"
                )
        if commit is not None and type(commit) is not OID:
            raise QueryError(
                "INVALID_INPUT", "pr-list", "typed commit selector required"
            )
        if path is not None and (
            type(path) is not str or not path or len(path) > 16384
        ):
            raise QueryError("INVALID_INPUT", "pr-list", "bounded exact path required")
        if assessment == "code" and (
            path is not None or commit is not None or metadata_filters
        ):
            raise QueryError(
                "INVALID_INPUT",
                "pr-list",
                "path/commit selectors require documents mode",
            )
        if assessment == "documents" and (
            not kinds or not set(kinds) <= set(DOCUMENT_KINDS)
        ):
            raise QueryError(
                "INVALID_INPUT", "pr-list", "known requested document kinds required"
            )
        filters = {
            "repository": repository.coordinates(),
            "parents": None
            if parents is None
            else [key.coordinates() for key in parents],
            "assessment": assessment,
            "kinds": sorted(set(kinds)),
            "listing_kinds": listing_kinds,
            "require_git": require_git,
            "require_text": require_text,
            "state": state,
            "draft": draft,
            "author": author,
            "text_literal": text_literal,
            "path": path,
            "commit": list(commit.key) if commit else None,
            "metadata_filters": metadata_filters,
            "max_work": max_work,
            "max_bytes": max_bytes,
        }
        page = validate_page_request(
            page, endpoint_kind="pr-list", filters=filters, cursor_validator=_cursor
        )
        work = UnlimitedWorkBudget(
            work_limits={
                "metadata_units": max_work,
                "input_bytes": max_bytes,
                "verification_bytes": 3 * max_bytes,
                "proof_steps": max_work,
            }
        )
        try:
            with self.open_snapshot(required_store="context") as snapshot:
                provider_repository = self._view(
                    snapshot.context, repository, work, include_text=False
                )
                listing = self._collection(
                    snapshot.context, provider_repository, "pull_requests", work
                )
                available = set(listing["members"])
                invalid = {
                    key
                    for key in available
                    if key.resource_kind != "pull_request"
                    or key.service_instance_uuidv4 != repository.service_instance_uuidv4
                }
                parent_state = listing["state"]
                missing = []
                if invalid:
                    parent_state = "conflict"
                    missing.append(
                        {
                            "kind": "parent_listing",
                            "reason": "parent_member_subject_mismatch",
                        }
                    )
                requested = (
                    available - invalid
                    if parents is None
                    else set(parents) & available - invalid
                )
                if (
                    parents is not None
                    and parents
                    and set(parents) <= available
                    and not invalid
                ):
                    parent_state = "complete"  # Explicit finite known-positive subjects; no universe claim.
                if parents is not None:
                    for key in set(parents) - available:
                        missing.append(
                            {
                                "kind": "parent_listing",
                                "parent": key.coordinates(),
                                "reason": "selected_parent_membership_unknown",
                            }
                        )
                        parent_state = (
                            "unknown" if parent_state != "conflict" else parent_state
                        )
                if parent_state != "complete":
                    missing.append(
                        {
                            "kind": "parent_listing",
                            "state": parent_state,
                            "reason": listing["reason"] or "parent_universe_unproven",
                        }
                    )
                summaries, states = [], [parent_state]
                for key in sorted(requested, key=lambda key: key.coordinates()):
                    _spend(work)
                    if assessment == "code":
                        result = self._assess_pr_code(
                            key,
                            require_git=require_git,
                            listing_kinds=listing_kinds,
                            max_work=max_work,
                            max_bytes=max_bytes,
                            snapshot=snapshot,
                            shared_work=work,
                            preflight=True,
                        )
                    else:
                        result = self._assess_pr_documents(
                            key,
                            kinds=kinds,
                            require_text=require_text,
                            path=path,
                            commit=commit,
                            metadata_filters=metadata_filters,
                            max_work=max_work,
                            max_bytes=max_bytes,
                            snapshot=snapshot,
                            shared_work=work,
                            preflight=True,
                        )
                    states.append(result.state)
                    missing.extend(
                        {"parent": key.coordinates(), **gap}
                        for gap in result.coverage["missing"]
                    )
                    view = self._view(snapshot.context, key, work, include_text=False)
                    matches = True
                    for field, expected in (
                        ("state", state),
                        ("draft", draft),
                        ("author", author),
                    ):
                        if expected is None:
                            continue
                        values = {
                            candidate.value_json
                            for candidate in view.fields.get(field, ())
                        }
                        if len(values) != 1:
                            missing.append(
                                {
                                    "parent": key.coordinates(),
                                    "kind": "metadata_filter",
                                    "reason": "filter_field_unresolved",
                                    "field": field,
                                }
                            )
                            states.append("partial")
                            matches = False
                        else:
                            actual = json.loads(next(iter(values)))
                            if actual is not None and type(actual) is not type(
                                expected
                            ):
                                missing.append(
                                    {
                                        "parent": key.coordinates(),
                                        "kind": "metadata_filter",
                                        "reason": "filter_field_invalid",
                                        "field": field,
                                    }
                                )
                                states.append("partial")
                                matches = False
                            elif actual != expected:
                                matches = False
                    if matches and self._literal_matches(
                        snapshot.context, view, result.member_keys, text_literal, work
                    ):
                        summaries.append(PRParentAssessment(key, result))
                overall = _state(states)
                selected = _paginate_items(
                    summaries,
                    key_fn=lambda item: item.resource.coordinates(),
                    page=page,
                    endpoint_kind="pr-list",
                    filters=filters,
                    snapshot_token=snapshot.token.encode(),
                    cursor_validator=_cursor,
                )
                selected = replace(
                    selected,
                    items=tuple(
                        replace(
                            item,
                            resource_view=self._view(
                                snapshot.context, item.resource, work, include_text=True
                            ),
                        )
                        for item in selected.items
                    ),
                )
                return PRRepositoryAssessment(
                    repository,
                    overall,
                    {
                        "complete_for_requested_scope": overall == "complete",
                        "missing": missing,
                    },
                    {key: value for key, value in listing.items() if key != "members"},
                    selected,
                )
        except RepositoryFailure as error:
            if error.code in {"BUDGET", "QUERY_BUDGET"}:
                raise QueryError(
                    "QUERY_BUDGET",
                    "pr-list",
                    "full parent scope exceeded finite budget",
                ) from error
            raise
