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
    "parser_module",
    "parser_version",
    "metadata",
    "acquisition_scope",
    "field_evidence",
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
    "provider_resource_id",
}
_GENERATED = {
    "parent_kind",
    "parent_review_kind",
    "reply_kind",
}
_MAX_STAGED_VARIANTS = 16
_CLOCK_SCOPES = {
    "issue": "github-issue-updated-at",
    "issue-comment": "github-issue-comment-updated-at",
    "review-comment": "github-review-comment-updated-at",
}

_STRUCTURAL_FIELDS = {
    "kind",
    "source_id",
    "service_instance_uuidv4",
    "repository_uuidv4",
    "repository_binding_id",
    "provider_resource_id",
    "provider_issue_number",
    "parent_provider_resource_id",
    "change_request_id",
    "provider_change_request_document_id",
    "provider_resource_id",
}


def _field_values(candidate):
    """Flatten observed mutable values; body and its availability form one field."""
    values = {}
    for name, value in semantic_content(candidate).items():
        if name in _STRUCTURAL_FIELDS or name in {"text_body_sha256", "body_status"}:
            continue
        if name == "metadata":

            def visit(path, item):
                values[_canonical(path)] = () if isinstance(item, dict) else item
                if isinstance(item, dict):
                    for key, child in item.items():
                        visit([*path, key], child)

            visit([name], candidate[name])
        else:
            values[_canonical([name])] = value
    if "body" in candidate or "body_status" in candidate:
        body = candidate.get("body")
        status = candidate.get(
            "body_status", "present" if body is not None else "provider-null"
        )
        values[_canonical(["body"])] = (status, body)
    return values


def _apply_field(candidate, path, value):
    path = json.loads(path)
    if path == ["body"]:
        candidate["body_status"], candidate["body"] = value
    elif path[0] != "metadata":
        candidate[path[0]] = value
    else:
        target = candidate
        for part in path[:-1]:
            if not isinstance(target.get(part), dict):
                target[part] = {}
            target = target[part]
        if value == ():
            if not isinstance(target.get(path[-1]), dict):
                target[path[-1]] = {}
        else:
            target[path[-1]] = value


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _equal_field(left, right):
    # Python treats True == 1, while these are distinct JSON values. The tuple
    # marker for a metadata object is also distinct from an empty JSON array.
    return type(left) is type(right) and _canonical(left) == _canonical(right)


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
        outer = not self.c.in_transaction
        if self.store:
            with self.store.transaction():
                yield
                if outer:
                    self.store.advance_local_revision()
            return
        from repo_catalog.adapters.sqlite.transactions import atomic_unit

        with atomic_unit(self.c):
            yield
            if outer:
                self.c.execute(
                    "UPDATE database_identity SET local_revision=local_revision+1 WHERE singleton=1"
                )

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
            "SELECT db_instance_id,local_revision FROM database_identity WHERE singleton=1"
        )
        return revision, dict(scope_context)

    def candidate_from_row(self, table, row):
        if table not in ("issue_resources", "review_resources"):
            raise ValueError("Unsupported current table")
        candidate = {k: v for k, v in dict(row).items() if k not in _GENERATED}
        candidate["field_evidence"] = json.loads(candidate.pop("field_evidence_json"))
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

    def _project_child_membership(self, candidate):
        """Derive transferred comment membership without rewriting its capture.

        Intake can predate the parent transfer. A different parent identity is
        an independent relation claim, never a redundant membership snapshot.
        """
        if candidate["kind"] != "issue-comment":
            return candidate
        table, key, where = self._table_key(candidate)
        incumbent = self._one(f"SELECT * FROM {table} WHERE {where}", tuple(key))
        if incumbent is None or incumbent[
            "parent_provider_resource_id"
        ] != candidate.get("parent_provider_resource_id"):
            return candidate
        parent = self._one(
            "SELECT repository_uuidv4,repository_binding_id,provider_issue_number FROM issue_resources WHERE service_instance_uuidv4=? AND kind='issue' AND provider_resource_id=?",
            (
                candidate["service_instance_uuidv4"],
                candidate.get("parent_provider_resource_id"),
            ),
        )
        return {**candidate, **parent} if parent else candidate

    def _stage(self, candidate, reason):
        candidate = dict(candidate)
        candidate.pop("last_checked_at_us", None)
        table, key, _ = self._table_key(candidate)
        record_key = self._stage_key(candidate)
        # One slot per distinct semantic value; repeat captures cannot grow a
        # local observation history. Retain up to sixteen unresolved alternatives.
        content_hash = bytes.fromhex(fingerprint_candidate(candidate))
        existing = self._one(
            "SELECT record_json,content_sha256 FROM exchange_staging WHERE record_key=? AND content_sha256=?",
            (record_key, content_hash),
        )
        if existing is None and candidate["kind"] == "issue-comment":
            existing = next(
                (
                    stage
                    for stage in self._stages(candidate)
                    if fingerprint_candidate(
                        self._project_child_membership(json.loads(stage["record_json"]))
                    )
                    == content_hash.hex()
                ),
                None,
            )
        if existing:
            old = self._project_child_membership(json.loads(existing["record_json"]))
            merged = dict(candidate if self._stronger_evidence(candidate, old) else old)
            evidence = dict(old.get("field_evidence", {}))
            for path, proof in candidate.get("field_evidence", {}).items():
                if path not in evidence or self._stronger_evidence(
                    proof, evidence[path]
                ):
                    evidence[path] = proof
            merged["field_evidence"] = evidence
            if merged != old or existing["content_sha256"] != content_hash:
                self.c.execute(
                    "UPDATE exchange_staging SET record_json=?,content_sha256=?,repository_uuidv4=? WHERE record_key=? AND content_sha256=?",
                    (
                        _canonical(merged),
                        content_hash,
                        merged["repository_uuidv4"],
                        record_key,
                        existing["content_sha256"],
                    ),
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

    def _validate(self, candidate):
        table, key, _ = self._table_key(candidate)
        allowed = _COMMON | (_ISSUE if table == "issue_resources" else _REVIEW)
        if table == "review_resources":
            allowed = allowed - {"title"}
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
        for name in ("parser_module", "parser_version"):
            if name in candidate and (
                not isinstance(candidate[name], str)
                or not candidate[name]
                or "\0" in candidate[name]
            ):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE",
                    "Parser attribution requires nonempty text",
                    {"field": name},
                )
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
        from repo_catalog.adapters.sqlite.json_contracts import (
            _acquisition_shape,
            _check_schema,
        )

        if "acquisition_scope" in candidate:
            _acquisition_shape(
                candidate["acquisition_scope"], candidate.get("service_instance_uuidv4")
            )
        if "metadata" in candidate:
            table, _, _ = self._table_key(candidate)
            _check_schema(table, "metadata", candidate["metadata"], candidate)
        if "field_evidence" in candidate:
            from repo_catalog.adapters.sqlite.json_contracts import (
                validate_field_evidence,
            )

            validate_field_evidence(self.c, candidate["field_evidence"], candidate)
            if set(candidate["field_evidence"]) - _field_values(candidate).keys():
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE", "Evidence refers to an absent field"
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
        from repo_catalog.adapters.sqlite.json_contracts import (
            validate_current_candidate_shape,
        )

        validate_current_candidate_shape(table, candidate)
        return table, key

    def _missing(self, candidate, *, source="import"):
        required = {
            "repository_uuidv4",
            "repository_binding_id",
            "service_instance_uuidv4",
            "observed_at_us",
            "parsed_at_us",
            "parser_module",
            "parser_version",
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
        from repo_catalog.adapters.sqlite.json_contracts import (
            JsonContractError,
            validate_acquisition_scope,
            validate_field_evidence,
        )

        detached = (
            candidate["kind"] == "issue-comment"
            and scope.get("repository_uuidv4") != candidate["repository_uuidv4"]
        )
        if detached and source == "live":
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE_SCOPE",
                "Live capture differs from current membership",
            )
        try:
            missing_capture = validate_acquisition_scope(
                self.c,
                scope,
                service_instance_uuidv4=candidate["service_instance_uuidv4"],
                repository_uuidv4=None if detached else candidate["repository_uuidv4"],
                repository_binding_id=None
                if detached
                else candidate["repository_binding_id"],
                allow_snapshot=detached,
            )
            missing_fields = validate_field_evidence(
                self.c, candidate.get("field_evidence", {}), candidate
            )
        except JsonContractError as error:
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE_SCOPE", "Invalid capture context"
            ) from error
        if (
            "change_request_id" in candidate
            and scope.get("change_request_id") != candidate["change_request_id"]
        ):
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE_SCOPE",
                "Capture differs from parent change request",
            )
        if missing_capture or missing_fields:
            return "missing capture dependencies"
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
            if name == "title" and incoming["kind"] in ("review", "review-comment"):
                continue
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
        values["field_evidence_json"] = _canonical(values.pop("field_evidence"))
        _, key, where = self._table_key(candidate)
        if previous is None:
            self.c.execute(
                f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
        else:
            key_names = key._fields
            old_values = dict(previous)
            old_body = old_values.pop("body")
            old_values["text_body_sha256"] = (
                hashlib.sha256(old_body.encode("utf-8")).digest()
                if old_body is not None
                else None
            )
            old_values["metadata"] = _canonical(old_values["metadata"])
            old_values["acquisition_scope_json"] = _canonical(
                old_values.pop("acquisition_scope")
            )
            old_values["field_evidence_json"] = _canonical(
                old_values.pop("field_evidence")
            )
            updates = {
                name: value
                for name, value in values.items()
                if name not in key_names and value != old_values.get(name)
            }
            if not updates:
                return
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
        if source not in ("live", "import"):
            raise ValueError("Unknown current resource admission source")
        incoming = dict(candidate)
        self._validate(incoming)
        if "deleted" in incoming:
            incoming["deleted"] = int(incoming["deleted"])
        with self._transaction():
            return self._admit(
                incoming,
                source=source,
                base_revision=base_revision,
                scope_context=scope_context,
            )

    def _observation_evidence(self, incoming):
        if "field_evidence" in incoming:
            return dict(incoming["field_evidence"])
        evidence = {
            name: incoming.get(name)
            for name in (
                "provider_updated_at_us",
                "provider_clock_scope",
                "observed_at_us",
                "parsed_at_us",
                "parser_module",
                "parser_version",
                "acquisition_scope",
            )
        }
        return {path: dict(evidence) for path in _field_values(incoming)}

    @staticmethod
    def _stronger_evidence(new, old):
        scope = new.get("provider_clock_scope")
        return (
            scope is not None
            and scope == old.get("provider_clock_scope")
            and new.get("provider_updated_at_us") is not None
            and (
                old.get("provider_updated_at_us") is None
                or new["provider_updated_at_us"] > old["provider_updated_at_us"]
            )
        )

    def _merge_fields(self, incoming, previous, authoritative):
        # Defaults permit nullable physical columns; only paths with evidence
        # assert knowledge. Inherited fields keep their own capture and clock.
        context = {
            name: value
            for name, value in incoming.items()
            if name in _STRUCTURAL_FIELDS
            or name
            in {
                "provider_updated_at_us",
                "provider_clock_scope",
                "observed_at_us",
                "parsed_at_us",
                "parser_module",
                "parser_version",
                "last_checked_at_us",
                "acquisition_scope",
            }
        }
        candidate = self._complete(context, previous)
        candidate["metadata"] = json.loads(_canonical(candidate.get("metadata", {})))
        evidence = dict(previous.get("field_evidence", {})) if previous else {}
        values = _field_values(incoming)
        supplied = self._observation_evidence(incoming)
        old_values = _field_values(previous) if previous else {}
        conflict = stale = False
        blocked = []
        for path in sorted(supplied, key=lambda path: (len(json.loads(path)), path)):
            parts = json.loads(path)
            if any(parts[: len(prefix)] == prefix for prefix in blocked):
                continue
            value, proof = values[path], supplied[path]
            old_proof = evidence.get(path)
            old_value = old_values.get(path)
            equal = old_proof is not None and _equal_field(old_value, value)
            order = self._clock_order(proof, old_proof or {})
            # A scalar replacing an object also replaces all known descendants;
            # it must justify ordering against each, not just the object marker.
            descendants = [
                key
                for key in evidence
                if len(json.loads(key)) > len(parts)
                and json.loads(key)[: len(parts)] == parts
            ]
            orders = [order]
            if value != ():
                orders.extend(
                    self._clock_order(proof, evidence[key]) for key in descendants
                )
            if old_proof is not None and not equal:
                if -1 in orders:
                    stale = True
                    blocked.append(parts)
                    continue
                if not authoritative and any(item != 1 for item in orders):
                    conflict = True
                    blocked.append(parts)
                    continue
            if equal and (
                order == -1
                or not authoritative
                and not self._stronger_evidence(proof, old_proof)
            ):
                continue
            _apply_field(candidate, path, value)
            if value != ():
                for key in descendants:
                    evidence.pop(key, None)
            evidence[path] = proof
        candidate["field_evidence"] = evidence
        return candidate, conflict, stale

    def _dominates(self, candidate, alternative, authoritative_paths=()):
        current_values, other_values = (
            _field_values(candidate),
            _field_values(alternative),
        )
        current_evidence = candidate.get("field_evidence", {})
        other_evidence = alternative.get("field_evidence", {})
        for path, other_proof in other_evidence.items():
            proof = current_evidence.get(path)
            if proof is None:
                parts = json.loads(path)
                ancestor = next(
                    (
                        _canonical(parts[:size])
                        for size in range(len(parts) - 1, 0, -1)
                        if _canonical(parts[:size]) in current_evidence
                        and current_values.get(_canonical(parts[:size])) != ()
                    ),
                    None,
                )
                if ancestor is None:
                    return False
                proof = current_evidence[ancestor]
                order = self._clock_order(proof, other_proof)
                if order != 1 and (ancestor not in authoritative_paths or order == -1):
                    return False
                continue
            if not _equal_field(current_values.get(path), other_values.get(path)) and (
                self._clock_order(proof, other_proof) == -1
                or path not in authoritative_paths
                and self._clock_order(proof, other_proof) != 1
            ):
                return False
        different_owner = any(
            candidate.get(name) != alternative.get(name) for name in _STRUCTURAL_FIELDS
        )
        return (
            not different_owner
            or bool(authoritative_paths)
            or self._clock_order(candidate, alternative) == 1
        )

    def _retain_equal_evidence(self, table, incoming, previous):
        """Save proofs of incumbent values even when another value is disputed.

        This never adopts a different value, clears intake or advances a local
        successful-check time. Only explicitly supplied, equal paths gain proof.
        """
        if previous is None:
            return previous
        values, old_values = _field_values(incoming), _field_values(previous)
        supplied = self._observation_evidence(incoming)
        evidence = dict(previous["field_evidence"])
        refreshed = dict(previous)
        for path, proof in supplied.items():
            if (
                path in old_values
                and _equal_field(values[path], old_values[path])
                and (
                    path not in evidence
                    or self._stronger_evidence(proof, evidence[path])
                )
            ):
                evidence[path] = proof
        refreshed["field_evidence"] = evidence
        if (
            all(
                path in old_values and _equal_field(old_values[path], values[path])
                for path in supplied
            )
            and all(
                incoming.get(name, previous.get(name)) == previous.get(name)
                for name in _STRUCTURAL_FIELDS
            )
            and self._stronger_evidence(incoming, previous)
        ):
            refreshed["provider_updated_at_us"] = incoming["provider_updated_at_us"]
            refreshed["provider_clock_scope"] = incoming["provider_clock_scope"]
        if refreshed != previous:
            self._write(table, refreshed, previous)
        return refreshed

    def _admit(self, incoming, *, source, base_revision, scope_context):
        table, key, where = self._table_key(incoming)
        stored = self._one(f"SELECT * FROM {table} WHERE {where}", tuple(key))
        previous = self.candidate_from_row(table, stored) if stored else None
        complete = self._complete(incoming, previous)
        complete["field_evidence"] = self._observation_evidence(incoming)
        digest = fingerprint_candidate(incoming)
        missing = self._missing(complete, source=source)
        if missing:
            self._stage(complete, "missing_dependency")
            return AdmissionResult("missing_dependency", key, digest, missing)
        revision = self._one(
            "SELECT db_instance_id,local_revision FROM database_identity WHERE singleton=1"
        )
        authoritative = (
            source == "live"
            and base_revision is not None
            and dict(base_revision) == revision
            and scope_context is not None
            and dict(scope_context) == complete["acquisition_scope"]
        )
        candidate, conflict, stale = self._merge_fields(
            incoming, previous, authoritative
        )
        order = self._clock_order(incoming, previous or {})
        structural_change = previous is not None and any(
            candidate.get(name) != previous.get(name) for name in _STRUCTURAL_FIELDS
        )
        if structural_change and order != 1:
            if order == -1:
                for name in _STRUCTURAL_FIELDS:
                    if name in previous:
                        candidate[name] = previous[name]
                stale = True
            elif not authoritative:
                conflict = True
        alternative = self._complete(incoming, None)
        alternative["field_evidence"] = self._observation_evidence(incoming)
        if conflict:
            self._retain_equal_evidence(table, incoming, previous)
            self._stage(alternative, "conflict")
            return AdmissionResult(
                "conflict", key, digest, "supplied fields have no proven order"
            )
        # Refresh the same semantic alternative's evidence even if another
        # candidate remains unordered. Known clocks can also disprove a fork.
        alternative_hash = fingerprint_candidate(alternative)
        if any(
            stage["content_sha256"].hex() == alternative_hash
            or incoming["kind"] == "issue-comment"
            and fingerprint_candidate(
                self._project_child_membership(json.loads(stage["record_json"]))
            )
            == alternative_hash
            for stage in self._stages(alternative)
        ):
            self._stage(alternative, "conflict")
        stages = self._stages(candidate)
        unresolved = []
        for stage in stages:
            if stage["reason"] != "current_state:conflict":
                continue
            other = self._project_child_membership(json.loads(stage["record_json"]))
            if not self._dominates(
                candidate,
                other,
                self._observation_evidence(incoming) if authoritative else (),
            ):
                unresolved.append(stage)
        if unresolved:
            previous = self._retain_equal_evidence(table, incoming, previous)
            if previous is None or not self._dominates(previous, alternative):
                self._stage(alternative, "conflict")
            return AdmissionResult(
                "conflict", key, digest, "cannot order all staged alternatives"
            )
        equal = previous is not None and _canonical(
            semantic_content(candidate)
        ) == _canonical(semantic_content(previous))
        # Resource-level evidence describes the newest accepted response, while
        # each field preserves its own freshness. Older complete responses may
        # add knowledge without rolling the aggregate clock backwards.
        if previous and order == -1:
            for name in (
                "provider_updated_at_us",
                "provider_clock_scope",
                "observed_at_us",
                "parsed_at_us",
                "parser_module",
                "parser_version",
                "acquisition_scope",
            ):
                candidate[name] = previous[name]
        if equal and previous:
            for name in (
                "observed_at_us",
                "parsed_at_us",
                "parser_module",
                "parser_version",
                "acquisition_scope",
            ):
                if (
                    not authoritative
                    or incoming["acquisition_scope"] == previous["acquisition_scope"]
                ):
                    candidate[name] = previous[name]
            if order != 1:
                candidate["provider_updated_at_us"] = previous["provider_updated_at_us"]
                candidate["provider_clock_scope"] = previous["provider_clock_scope"]
        candidate["last_checked_at_us"] = (
            previous.get("last_checked_at_us") if previous else None
        )
        if source == "live" and authoritative:
            checked = incoming.get("last_checked_at_us")
            if checked is None:
                checked = incoming.get("observed_at_us")
            prior = candidate["last_checked_at_us"]
            if checked is not None:
                candidate["last_checked_at_us"] = (
                    checked if prior is None else max(prior, checked)
                )
        if previous is None or _canonical(candidate) != _canonical(previous):
            self._write(table, candidate, previous)
        self.c.execute(
            "DELETE FROM exchange_staging WHERE record_key=? AND reason IN ('current_state:conflict','current_state:missing_dependency')",
            (self._stage_key(candidate),),
        )
        if equal:
            return AdmissionResult(
                "stale" if stale and candidate == previous else "identical", key, digest
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
                "SELECT * FROM exchange_staging WHERE table_name IN ('issue_resources','review_resources') AND reason='current_state:missing_dependency'"
            )
            for stage in stages:
                candidate = self._project_child_membership(
                    json.loads(stage["record_json"])
                )
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
        seen = set()

        def add_stage(stage, owner=None):
            identity = (stage["record_key"], stage["content_sha256"])
            if identity in seen:
                return
            seen.add(identity)
            candidate = self._project_child_membership(json.loads(stage["record_json"]))
            table, key, where = self._table_key(candidate)
            owner = owner or self._one(
                f"SELECT repository_uuidv4 FROM {table} WHERE {where}", tuple(key)
            )
            if owner and candidate["repository_uuidv4"] != owner["repository_uuidv4"]:
                raise CatalogError(
                    "CURRENT_STATE_CROSS_REPOSITORY_CONFLICT",
                    "One-repository exchange cannot represent disputed resource ownership",
                    {
                        "key": list(key),
                        "current_repository_uuidv4": owner["repository_uuidv4"],
                        "candidate_repository_uuidv4": candidate["repository_uuidv4"],
                    },
                )
            if candidate["repository_uuidv4"] == repository_uuidv4:
                result.append(
                    (table, candidate, stage["reason"] == "current_state:conflict")
                )

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
                for stage in self._stages(candidate):
                    add_stage(stage, candidate)
        for stage in self._all(
            "SELECT * FROM exchange_staging WHERE repository_uuidv4=? AND table_name IN ('issue_resources','review_resources') AND reason LIKE 'current_state:%'",
            (repository_uuidv4,),
        ):
            add_stage(stage)
        return result
