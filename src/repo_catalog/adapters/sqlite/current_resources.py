"""Transactional admission of shared latest-state provider resources.

Provider clocks are comparable only within an explicitly declared endpoint scope.
An authoritative live response needs both the pre-request catalog revision and
the identical typed acquisition scope. Arrival and parser timestamps never order
different values. Unordered candidates use the existing bounded intake staging.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from typing import Mapping

from repo_catalog.adapters.sqlite.text_bodies import intern_text_body
from repo_catalog.domain.current_state import (
    AdmissionResult,
    IssueResourceKey,
    fingerprint_candidate,
    resource_key,
    semantic_content,
)
from repo_catalog.domain.document import verify_text_body
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import validate_epoch_us

_ID = re.compile(r"[1-9][0-9]*\Z")
_COMMON = {
    "kind",
    "repository_uuidv4",
    "repository_binding_id",
    "service_instance_uuidv4",
    "body",
    "body_status",
    "title",
    "state",
    "author",
    "url",
    "deleted",
    "provider_updated_at_us",
    "provider_clock_scope",
    "observed_at_us",
    "last_checked_at_us",
    "parsed_at_us",
    "parser_profile_uuidv4",
    "metadata",
    "acquisition_scope",
}
_ISSUE = {
    "provider_resource_id",
    "provider_issue_number",
    "parent_provider_resource_id",
}
_REVIEW = {
    "change_request_id",
    "provider_change_request_document_id",
    "submitted_at_us",
    "target_commit_oid",
    "original_commit_oid",
    "original_position",
    "current_position",
    "raw_path",
    "diff_hunk",
    "review_provider_resource_id",
    "in_reply_to_provider_resource_id",
    "review_thread_provider_resource_id",
}
_NULLABLE_COMMON = {
    "title",
    "state",
    "author",
    "url",
    "provider_updated_at_us",
    "provider_clock_scope",
    "last_checked_at_us",
}
_NULLABLE_REVIEW = _REVIEW - {
    "change_request_id",
    "provider_change_request_document_id",
}
_GENERATED = {
    "parent_kind",
    "parent_review_kind",
    "reply_kind",
    "owner_kind",
    "fact_kind",
}
_MAX_STAGED_VARIANTS = 16
_CLOCK_SCOPES = {
    "issue": "github-issue-updated-at",
    "issue-comment": "github-issue-comment-updated-at",
    "review-comment": "github-review-comment-updated-at",
}


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _merge_projection(previous, incoming):
    result = dict(previous)
    for name, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(name), dict):
            result[name] = _merge_projection(result[name], value)
        else:
            result[name] = value
    return result


class CurrentResources:
    def __init__(self, store_or_connection):
        self.store = (
            store_or_connection if hasattr(store_or_connection, "connection") else None
        )
        self.c = self.store.connection if self.store else store_or_connection

    @contextmanager
    def _transaction(self):
        if self.c.in_transaction:
            yield
            return
        self.c.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.c.execute(
                "UPDATE database_identity SET publication_seq=publication_seq+1 WHERE singleton=1"
            )
            self.c.execute("COMMIT")
        except BaseException:
            if self.c.in_transaction:
                self.c.execute("ROLLBACK")
            raise

    def _one(self, sql, args=()):
        cursor = self.c.execute(sql, args)
        row = cursor.fetchone()
        return (
            dict(zip((col[0] for col in cursor.description), row))
            if row is not None
            else None
        )

    def _all(self, sql, args=()):
        cursor = self.c.execute(sql, args)
        names = [col[0] for col in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def capture_context(self, scope_context):
        """Capture immediately before a serialized live request, never after it."""
        revision = self._one(
            "SELECT db_instance_id,publication_seq FROM database_identity WHERE singleton=1"
        )
        return revision, dict(scope_context)

    def candidate_from_row(self, table, row):
        if table not in ("issue_resources", "review_resources"):
            raise ValueError("Unsupported current table")
        candidate = {k: v for k, v in dict(row).items() if k not in _GENERATED}
        digest = candidate.pop("text_body_sha256")
        if digest is None:
            candidate["body"] = None
            candidate["metadata"] = json.loads(candidate["metadata"])
            candidate["acquisition_scope"] = json.loads(
                candidate.pop("acquisition_scope_json")
            )
            return candidate
        body = self._one(
            "SELECT body,byte_length FROM text_bodies WHERE sha256=?", (digest,)
        )
        if body is None:
            raise CatalogError(
                "CURRENT_BODY_MISSING", "Current resource body is missing"
            )
        candidate["body"] = body["body"]
        verify_text_body(body["body"], digest, body["byte_length"])
        candidate["metadata"] = json.loads(candidate["metadata"])
        candidate["acquisition_scope"] = json.loads(
            candidate.pop("acquisition_scope_json")
        )
        return candidate

    def _table_key(self, candidate):
        key = resource_key(candidate)
        if isinstance(key, IssueResourceKey):
            return (
                "issue_resources",
                key,
                "service_instance_uuidv4=? AND kind=? AND provider_resource_id=?",
            )
        return (
            "review_resources",
            key,
            "change_request_id=? AND kind=? AND provider_change_request_document_id=?",
        )

    def _stage_key(self, candidate):
        table, key, _ = self._table_key(candidate)
        return (
            "current-state:"
            + hashlib.sha256(_canonical([table, list(key)]).encode()).hexdigest()
        )

    def _stages(self, candidate):
        return self._all(
            "SELECT * FROM exchange_staging WHERE record_key=? AND reason LIKE 'current_state:%'",
            (self._stage_key(candidate),),
        )

    def _stage(self, candidate, reason):
        table, key, _ = self._table_key(candidate)
        record_key = self._stage_key(candidate)
        # One slot per distinct semantic value; repeat captures cannot grow a
        # local observation history. Retain up to sixteen unresolved alternatives.
        content_hash = bytes.fromhex(fingerprint_candidate(candidate))
        existing = self._one(
            "SELECT record_json FROM exchange_staging WHERE record_key=? AND content_sha256=?",
            (record_key, content_hash),
        )
        if existing:
            old = json.loads(existing["record_json"])
            newer_clock = candidate.get("provider_updated_at_us")
            if newer_clock is not None and self._clock_order(candidate, old) == 1:
                self.c.execute(
                    "UPDATE exchange_staging SET record_json=? WHERE record_key=? AND content_sha256=?",
                    (_canonical(candidate), record_key, content_hash),
                )
            if reason == "conflict":
                self.c.execute(
                    "UPDATE exchange_staging SET reason='current_state:conflict' WHERE record_key=? AND content_sha256=?",
                    (record_key, content_hash),
                )
            return
        if len(self._stages(candidate)) >= _MAX_STAGED_VARIANTS:
            raise CatalogError(
                "CURRENT_STATE_STAGING_FULL",
                "Current resource has sixteen unresolved alternatives",
                {"key": list(key)},
            )
        catalog = self._one(
            "SELECT db_instance_id FROM database_identity WHERE singleton=1"
        )
        self.c.execute(
            "INSERT INTO exchange_staging(record_key,content_sha256,table_name,repository_uuidv4,origin_catalog_uuidv4,record_json,reason) VALUES(?,?,?,?,?,?,?)",
            (
                record_key,
                content_hash,
                table,
                candidate["repository_uuidv4"],
                catalog["db_instance_id"],
                _canonical(candidate),
                "current_state:" + reason,
            ),
        )

    def _selected(self, candidate):
        kind = candidate["kind"]
        if kind in ("issue", "issue-comment"):
            fact_kind = "ordinary-issue-comment" if kind == "issue-comment" else kind
            row = self._one(
                "SELECT 1 FROM effective_repository_parser_profiles WHERE repository_uuidv4=? AND fact_kind=? AND parser_profile_uuidv4=?",
                (
                    candidate["repository_uuidv4"],
                    fact_kind,
                    candidate["parser_profile_uuidv4"],
                ),
            )
        else:
            row = self._one(
                "SELECT 1 FROM effective_change_request_parser_profiles WHERE change_request_id=? AND fact_kind=? AND parser_profile_uuidv4=?",
                (
                    candidate["change_request_id"],
                    kind,
                    candidate["parser_profile_uuidv4"],
                ),
            )
        return row is not None

    def _validate(self, candidate):
        table, key, _ = self._table_key(candidate)
        allowed = _COMMON | (_ISSUE if table == "issue_resources" else _REVIEW)
        unknown = set(candidate) - allowed
        if unknown:
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE",
                "Unknown current resource fields",
                {"fields": sorted(unknown)},
            )
        id_fields = (
            ("provider_resource_id", "parent_provider_resource_id")
            if table == "issue_resources"
            else (
                "provider_change_request_document_id",
                "review_provider_resource_id",
                "in_reply_to_provider_resource_id",
            )
        )
        for name in id_fields:
            value = candidate.get(name)
            if value is not None and (
                not isinstance(value, str) or not _ID.fullmatch(value)
            ):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE_ID",
                    "Canonical positive provider ID required",
                    {"field": name},
                )
        for name, value in candidate.items():
            if name.endswith("_us") and value is not None:
                validate_epoch_us(value)
        if "deleted" in candidate and type(candidate["deleted"]) not in (int, bool):
            raise CatalogError("INVALID_CURRENT_RESOURCE", "Deleted must be boolean")
        if "metadata" in candidate and not isinstance(candidate["metadata"], dict):
            raise CatalogError("INVALID_CURRENT_RESOURCE", "Metadata must be an object")
        if "acquisition_scope" in candidate and not isinstance(
            candidate["acquisition_scope"], dict
        ):
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE", "Acquisition scope must be an object"
            )
        clock_scope = candidate.get("provider_clock_scope")
        if clock_scope is not None and clock_scope != _CLOCK_SCOPES.get(
            candidate["kind"]
        ):
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE_CLOCK",
                "Provider endpoint has no verified comparable clock scope",
            )
        if (
            candidate["kind"] == "review"
            and candidate.get("provider_updated_at_us") is not None
        ):
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE_CLOCK",
                "Review submission time is not an update clock",
            )
        _canonical(candidate)
        fingerprint_candidate(candidate)
        return table, key

    def _missing(self, candidate):
        required = {
            "repository_uuidv4",
            "repository_binding_id",
            "service_instance_uuidv4",
            "observed_at_us",
            "parsed_at_us",
            "parser_profile_uuidv4",
            "acquisition_scope",
        }
        if candidate["kind"] in ("issue", "issue-comment"):
            required.add("provider_issue_number")
            if candidate["kind"] == "issue-comment":
                required.add("parent_provider_resource_id")
        if any(name not in candidate or candidate[name] is None for name in required):
            return "missing resource fields"
        binding = self._one(
            "SELECT * FROM repository_bindings WHERE repository_binding_id=?",
            (candidate["repository_binding_id"],),
        )
        if binding is None:
            return "missing repository binding"
        if (
            binding["repository_uuidv4"] != candidate["repository_uuidv4"]
            or binding["service_instance_uuidv4"]
            != candidate["service_instance_uuidv4"]
        ):
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE_OWNER",
                "Binding does not match current resource owner",
            )
        capability = (
            "ordinary-issue-comment"
            if candidate["kind"] == "issue-comment"
            else candidate["kind"]
        )
        if (
            self._one(
                "SELECT 1 FROM parser_profile_capabilities WHERE parser_profile_uuidv4=? AND owner_kind='repository' AND fact_kind=?",
                (candidate["parser_profile_uuidv4"], capability),
            )
            is None
        ):
            return "missing parser profile capability"
        if candidate["kind"] == "issue-comment":
            parent = self._one(
                "SELECT * FROM issue_resources WHERE service_instance_uuidv4=? AND kind='issue' AND provider_resource_id=?",
                (
                    candidate["service_instance_uuidv4"],
                    candidate["parent_provider_resource_id"],
                ),
            )
            if parent is None:
                return "missing ordinary Issue parent"
            if any(
                parent[name] != candidate[name]
                for name in (
                    "repository_uuidv4",
                    "repository_binding_id",
                    "provider_issue_number",
                )
            ):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE_OWNER",
                    "Comment does not match its Issue membership",
                )
        if candidate["kind"] in ("review", "review-comment"):
            owner = self._one(
                "SELECT * FROM change_requests WHERE change_request_id=?",
                (candidate["change_request_id"],),
            )
            if owner is None:
                return "missing parent change request"
            if any(
                owner[name] != candidate[name]
                for name in ("repository_uuidv4", "repository_binding_id")
            ):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE_OWNER",
                    "Review does not match its parent change request",
                )
            for field, parent_kind in (
                ("review_provider_resource_id", "review"),
                ("in_reply_to_provider_resource_id", "review-comment"),
            ):
                if (
                    candidate.get(field) is not None
                    and self._one(
                        "SELECT 1 FROM review_resources WHERE change_request_id=? AND kind=? AND provider_change_request_document_id=?",
                        (candidate["change_request_id"], parent_kind, candidate[field]),
                    )
                    is None
                ):
                    return "missing " + field
            thread = candidate.get("review_thread_provider_resource_id")
            if (
                thread is not None
                and self._one(
                    "SELECT 1 FROM review_threads WHERE change_request_id=? AND provider_resource_id=?",
                    (candidate["change_request_id"], thread),
                )
                is None
            ):
                return "missing review thread"
        scope = candidate["acquisition_scope"]
        scope_names = [
            "service_instance_uuidv4",
            "repository_uuidv4",
            "repository_binding_id",
        ]
        if "change_request_id" in candidate:
            scope_names.append("change_request_id")
        if (
            any(scope.get(name) != candidate[name] for name in scope_names)
            or not isinstance(scope.get("endpoint"), str)
            or not scope["endpoint"]
        ):
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE_SCOPE",
                "Acquisition scope does not match typed owner",
            )
        return None

    def _complete(self, incoming, previous):
        candidate = dict(previous or {})
        if "metadata" in incoming:
            metadata = _merge_projection(
                candidate.get("metadata", {}), incoming["metadata"]
            )
        else:
            metadata = candidate.get("metadata", {})
        candidate.update(incoming)
        candidate["metadata"] = metadata
        if incoming.get("body_status") == "provider-null":
            candidate["body"] = None
        if "body" in incoming:
            if "body_status" not in incoming:
                candidate["body_status"] = (
                    "present" if incoming["body"] is not None else "provider-null"
                )
        candidate.setdefault("body_status", "missing")
        candidate.setdefault("body", None)
        for name in _NULLABLE_COMMON:
            candidate.setdefault(name, None)
        if incoming["kind"] in ("issue", "issue-comment"):
            candidate.setdefault("parent_provider_resource_id", None)
        else:
            for name in _NULLABLE_REVIEW:
                candidate.setdefault(name, None)
        candidate.setdefault("deleted", 0)
        candidate["deleted"] = int(candidate["deleted"])
        return candidate

    @staticmethod
    def _clock_order(candidate, previous):
        scope = candidate.get("provider_clock_scope")
        new = candidate.get("provider_updated_at_us")
        old = previous.get("provider_updated_at_us")
        if (
            scope is None
            or scope != previous.get("provider_clock_scope")
            or new is None
            or old is None
        ):
            return None
        return (new > old) - (new < old)

    def _write(self, table, candidate, previous):
        body = candidate["body"]
        digest = intern_text_body(self.c, body) if body is not None else None
        values = dict(candidate)
        values.pop("body")
        values["text_body_sha256"] = digest
        values["metadata"] = _canonical(values["metadata"])
        values["acquisition_scope_json"] = _canonical(values.pop("acquisition_scope"))
        _, key, where = self._table_key(candidate)
        if previous is None:
            self.c.execute(
                f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
        else:
            key_names = key._fields
            updates = {
                name: value for name, value in values.items() if name not in key_names
            }
            self.c.execute(
                f"UPDATE {table} SET {','.join(name + '=?' for name in updates)} WHERE {where}",
                (*updates.values(), *key),
            )

    def admit(
        self,
        candidate: Mapping,
        *,
        source="live",
        base_revision=None,
        scope_context=None,
    ):
        if source not in ("live", "import", "replay"):
            raise ValueError("Unknown current resource admission source")
        incoming = dict(candidate)
        self._validate(incoming)
        with self._transaction():
            return self._admit(
                incoming,
                source=source,
                base_revision=base_revision,
                scope_context=scope_context,
            )

    def _admit(self, incoming, *, source, base_revision, scope_context):
        table, key, where = self._table_key(incoming)
        stored = self._one(f"SELECT * FROM {table} WHERE {where}", tuple(key))
        previous = self.candidate_from_row(table, stored) if stored else None
        candidate = self._complete(incoming, previous)
        digest = fingerprint_candidate(incoming)
        missing = self._missing(candidate)
        if missing:
            self._stage(candidate, "missing_dependency")
            return AdmissionResult("missing_dependency", key, digest, missing)
        if not self._selected(candidate) and (
            source == "live"
            or (
                previous
                and previous["parser_profile_uuidv4"]
                != candidate["parser_profile_uuidv4"]
            )
        ):
            self._stage(candidate, "profile_pending")
            return AdmissionResult(
                "missing_dependency",
                key,
                digest,
                "parser profile is not selected and trusted",
            )
        stages = self._stages(candidate)
        revision = self._one(
            "SELECT db_instance_id,publication_seq FROM database_identity WHERE singleton=1"
        )
        authoritative = (
            source == "live"
            and base_revision is not None
            and dict(base_revision) == revision
            and scope_context is not None
            and dict(scope_context) == candidate["acquisition_scope"]
        )
        if previous is not None:
            equal = semantic_content(candidate) == semantic_content(previous)
            order = self._clock_order(candidate, previous)
            if equal:
                # Unchanged refresh is idempotent. A replay/import is never a new
                # local successful check, and cannot move clocks backwards.
                if order == 1 or (source == "live" and authoritative):
                    evidence = candidate
                    candidate = dict(previous)
                    if order == 1:
                        candidate["provider_updated_at_us"] = evidence[
                            "provider_updated_at_us"
                        ]
                    if source == "live" and authoritative:
                        checked = incoming.get(
                            "last_checked_at_us", incoming.get("observed_at_us")
                        )
                        if checked is not None:
                            prior = candidate.get("last_checked_at_us")
                            candidate["last_checked_at_us"] = (
                                checked if prior is None else max(prior, checked)
                            )
                    self._write(table, candidate, previous)
                alternatives = [
                    json.loads(stage["record_json"])
                    for stage in stages
                    if stage["reason"] == "current_state:conflict"
                ]
                resolved = authoritative or all(
                    semantic_content(candidate) == semantic_content(alt)
                    or self._clock_order(candidate, alt) == 1
                    for alt in alternatives
                )
                if alternatives and not resolved:
                    return AdmissionResult(
                        "conflict", key, digest, "unresolved alternatives remain"
                    )
                if alternatives and resolved:
                    self.c.execute(
                        "DELETE FROM exchange_staging WHERE record_key=? AND reason='current_state:conflict'",
                        (self._stage_key(candidate),),
                    )
                return AdmissionResult("identical", key, digest)
            if order == -1:
                return AdmissionResult("stale", key, digest)
            if not authoritative and order != 1:
                self._stage(candidate, "conflict")
                return AdmissionResult(
                    "conflict", key, digest, "different states have no proven order"
                )
        # A newer clock/live fence must dominate every staged conflicting value,
        # not just the incumbent; otherwise no public winner can be claimed.
        for stage in stages:
            if stage["reason"] != "current_state:conflict":
                continue
            alternative = json.loads(stage["record_json"])
            if semantic_content(candidate) == semantic_content(alternative):
                continue
            if not authoritative and self._clock_order(candidate, alternative) != 1:
                self._stage(candidate, "conflict")
                return AdmissionResult(
                    "conflict", key, digest, "cannot order all staged alternatives"
                )
        self._write(table, candidate, previous)
        self.c.execute(
            "DELETE FROM exchange_staging WHERE record_key=? AND reason IN ('current_state:conflict','current_state:missing_dependency')",
            (self._stage_key(candidate),),
        )
        return AdmissionResult("accepted", key, digest)

    def promote_staging(self):
        """Retry legitimate missing dependencies; unknown ordering stays visible."""
        with self._transaction():
            return self._promote_staging()

    def _promote_staging(self):
        promoted = 0
        while True:
            changed = False
            stages = self._all(
                "SELECT * FROM exchange_staging WHERE table_name IN ('issue_resources','review_resources') AND reason IN ('current_state:missing_dependency','current_state:profile_pending')"
            )
            for stage in stages:
                candidate = json.loads(stage["record_json"])
                if stage[
                    "reason"
                ] == "current_state:profile_pending" and not self._selected(candidate):
                    continue
                self.c.execute("SAVEPOINT current_resource_promotion")
                try:
                    if self._missing(candidate):
                        self.c.execute("RELEASE current_resource_promotion")
                        continue
                    self.c.execute(
                        "DELETE FROM exchange_staging WHERE record_key=? AND content_sha256=?",
                        (stage["record_key"], stage["content_sha256"]),
                    )
                    result = self.admit(candidate, source="import")
                except (CatalogError, sqlite3.IntegrityError) as error:
                    self.c.execute("ROLLBACK TO current_resource_promotion")
                    self.c.execute("RELEASE current_resource_promotion")
                    if isinstance(error, CatalogError) and not error.code.startswith(
                        "INVALID_CURRENT_RESOURCE"
                    ):
                        raise
                    # Late ownership resolution can reveal an invalid candidate.
                    # Diagnose it locally without blocking independent resources.
                    self.c.execute(
                        "UPDATE exchange_staging SET reason='current_state:invalid' WHERE record_key=? AND content_sha256=?",
                        (stage["record_key"], stage["content_sha256"]),
                    )
                    continue
                self.c.execute("RELEASE current_resource_promotion")
                if result.status in ("accepted", "identical", "stale"):
                    promoted += 1
                    changed = True
            if not changed:
                break
        return promoted

    def export_candidates(self, repository_uuidv4):
        result = []
        for table in ("issue_resources", "review_resources"):
            for row in self._all(
                f"SELECT * FROM {table} WHERE repository_uuidv4=?", (repository_uuidv4,)
            ):
                candidate = self.candidate_from_row(table, row)
                conflicted = any(
                    s["reason"] == "current_state:conflict"
                    for s in self._stages(candidate)
                )
                result.append((table, candidate, conflicted))
        for stage in self._all(
            "SELECT * FROM exchange_staging WHERE repository_uuidv4=? AND table_name IN ('issue_resources','review_resources') AND reason LIKE 'current_state:%'",
            (repository_uuidv4,),
        ):
            result.append(
                (
                    stage["table_name"],
                    json.loads(stage["record_json"]),
                    stage["reason"] == "current_state:conflict",
                )
            )
        return result
