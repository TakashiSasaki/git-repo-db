"""Direct admission for current PR metadata, documents, threads and Source roster.

The shared field engine orders actual provider clocks and preserves inherited
field origins. These typed resources have no collection or operation prerequisite.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import NamedTuple

from repo_catalog.adapters.sqlite.current_resources import (
    CurrentResources,
    _canonical,
    _equal_field,
    _field_values,
)
from repo_catalog.adapters.sqlite.text_bodies import intern_text_body
from repo_catalog.domain.document import verify_text_body
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import validate_epoch_us


class ChangeRequestKey(NamedTuple):
    change_request_id: str


class DocumentKey(NamedTuple):
    change_request_id: str
    kind: str
    provider_change_request_document_id: str


class ThreadKey(NamedTuple):
    change_request_id: str
    provider_resource_id: str


class SourceRepositoryKey(NamedTuple):
    source_id: str
    repository_uuidv4: str


TABLES = {"change_request_state", "document_state", "review_thread_state"}
_CONTEXT = {
    "repository_uuidv4",
    "repository_binding_id",
    "service_instance_uuidv4",
    "provider_updated_at_us",
    "provider_clock_scope",
    "observed_at_us",
    "last_checked_at_us",
    "parsed_at_us",
    "parser_module",
    "parser_version",
    "acquisition_scope",
    "field_evidence",
    "metadata",
    "kind",
    "change_request_id",
}
_FIELDS = {
    "change_request_state": {
        "provider_resource_id",
        "state",
        "draft",
        "merged",
        "locked",
        "author",
        "url",
        "object_format",
        "head_oid",
        "base_oid",
        "merge_oid",
        "head_ref",
        "base_ref",
        "head_repository_binding_id",
        "base_repository_binding_id",
        "created_at_us",
        "closed_at_us",
        "merged_at_us",
    },
    "document_state": {
        "provider_change_request_document_id",
        "body",
        "body_status",
        "author",
        "url",
        "deleted",
    },
    "review_thread_state": {
        "provider_resource_id",
        "resolved",
        "outdated",
        "raw_path",
        "line",
        "start_line",
        "original_line",
        "original_start_line",
        "side",
        "start_side",
        "object_format",
        "commit_oid",
        "original_commit_oid",
        "diff_hunk",
    },
}
_BINARY = {
    "head_oid",
    "base_oid",
    "merge_oid",
    "commit_oid",
    "original_commit_oid",
    "raw_path",
}
_CLOCKS = {
    "change-request": "github-pr-updated-at",
    "issue-comment": "github-issue-comment-updated-at",
    "pr-title": "github-pr-updated-at",
    "pr-body": "github-pr-updated-at",
}


class CurrentApiState(CurrentResources):
    def _stage_key(self, candidate):
        if candidate.get("kind") == "source-repository":
            return self._source_stage_key(
                candidate["source_id"], candidate["repository_uuidv4"]
            )
        return super()._stage_key(candidate)

    def _table_key(self, candidate):
        if candidate.get("kind") == "source-repository":
            return (
                "source_repositories",
                SourceRepositoryKey(
                    candidate["source_id"], candidate["repository_uuidv4"]
                ),
                "source_id=? AND repository_uuidv4=?",
            )
        if "provider_change_request_document_id" in candidate:
            key = DocumentKey(
                candidate["change_request_id"],
                candidate["kind"],
                candidate["provider_change_request_document_id"],
            )
            return (
                "document_state",
                key,
                "change_request_id=? AND kind=? AND provider_change_request_document_id=?",
            )
        if candidate["kind"] == "change-request":
            key = ChangeRequestKey(candidate["change_request_id"])
            return "change_request_state", key, "change_request_id=?"
        if candidate["kind"] == "review-thread":
            key = ThreadKey(
                candidate["change_request_id"], candidate["provider_resource_id"]
            )
            return (
                "review_thread_state",
                key,
                "change_request_id=? AND provider_resource_id=?",
            )
        raise CatalogError("INVALID_CURRENT_RESOURCE", "Unsupported typed API resource")

    def _validate(self, candidate):
        table, key, _ = self._table_key(candidate)
        unknown = candidate.keys() - (_CONTEXT | _FIELDS[table])
        if unknown:
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE",
                "Unknown typed API fields",
                {"fields": sorted(unknown)},
            )
        if table == "document_state" and candidate["kind"] not in {
            "pr-title",
            "pr-body",
            "issue-comment",
        }:
            raise CatalogError("INVALID_CURRENT_RESOURCE", "Unsupported document kind")
        for name, value in candidate.items():
            if name.endswith("_us") and value is not None:
                validate_epoch_us(value)
            if name in _BINARY and value is not None:
                if not isinstance(value, str) or (
                    name != "raw_path"
                    and (
                        len(value) not in {40, 64}
                        or any(ch not in "0123456789abcdef" for ch in value)
                    )
                ):
                    raise CatalogError(
                        "INVALID_CURRENT_RESOURCE",
                        "Binary domain field requires canonical text",
                        {"field": name},
                    )
            if (
                name in {"draft", "merged", "locked", "resolved", "outdated", "deleted"}
                and value is not None
                and (type(value) not in {int, bool} or value not in {0, 1})
            ):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE",
                    "Domain flag must be boolean",
                    {"field": name},
                )
        for name in ("parser_module", "parser_version"):
            if name in candidate and (
                not isinstance(candidate[name], str)
                or not candidate[name]
                or "\0" in candidate[name]
            ):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE", "Actual parser attribution required"
                )
        if candidate.get("provider_clock_scope") is not None and candidate[
            "provider_clock_scope"
        ] != _CLOCKS.get(candidate["kind"]):
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE_CLOCK", "Unverified provider clock scope"
            )
        if "metadata" in candidate and not isinstance(candidate["metadata"], dict):
            raise CatalogError("INVALID_CURRENT_RESOURCE", "Metadata must be an object")
        if "field_evidence" in candidate:
            from repo_catalog.adapters.sqlite.json_contracts import (
                validate_field_evidence,
            )

            validate_field_evidence(self.c, candidate["field_evidence"], candidate)
            if candidate["field_evidence"].keys() - _field_values(candidate).keys():
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE", "Evidence refers to omitted fields"
                )
        if "metadata" in candidate:
            from repo_catalog.adapters.sqlite.json_contracts import _check_schema

            _check_schema(table, "metadata", candidate["metadata"], candidate)
        if "acquisition_scope" in candidate:
            from repo_catalog.adapters.sqlite.json_contracts import _acquisition_shape

            _acquisition_shape(
                candidate["acquisition_scope"], candidate.get("service_instance_uuidv4")
            )
            if (
                candidate["acquisition_scope"].get("change_request_id")
                != candidate["change_request_id"]
            ):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE_SCOPE", "Capture parent mismatch"
                )
        _canonical(candidate)
        return table, key

    def _complete(self, incoming, previous):
        table, _, _ = self._table_key(incoming)
        result = dict(previous or {})
        result.update(incoming)
        metadata = dict((previous or {}).get("metadata", {}))
        if "metadata" in incoming:
            from repo_catalog.adapters.sqlite.current_resources import _merge_projection

            metadata = _merge_projection(metadata, incoming["metadata"])
        result["metadata"] = metadata
        for name in _FIELDS[table] - {
            "provider_resource_id",
            "provider_change_request_document_id",
            "body",
            "body_status",
            "deleted",
        }:
            result.setdefault(name, None)
        for name in (
            "provider_updated_at_us",
            "provider_clock_scope",
            "last_checked_at_us",
        ):
            result.setdefault(name, None)
        if table == "document_state":
            result.setdefault("body", None)
            result.setdefault("body_status", "missing")
            result.setdefault("deleted", 0)
            if "body" in incoming:
                result["body_status"] = incoming.get(
                    "body_status",
                    "present" if incoming["body"] is not None else "provider-null",
                )
            if incoming.get("body_status") == "provider-null":
                result["body"] = None
        return result

    def _missing(self, candidate, *, source="import"):
        for name in (
            "repository_uuidv4",
            "repository_binding_id",
            "service_instance_uuidv4",
            "observed_at_us",
            "parsed_at_us",
            "parser_module",
            "parser_version",
            "acquisition_scope",
        ):
            if candidate.get(name) is None:
                return "missing resource fields"
        parent = self._one(
            "SELECT c.*,b.service_instance_uuidv4 FROM change_requests c JOIN repository_bindings b USING(repository_binding_id) WHERE c.change_request_id=?",
            (candidate["change_request_id"],),
        )
        if not parent:
            return "missing parent change request"
        if any(
            parent[name] != candidate[name]
            for name in (
                "repository_uuidv4",
                "repository_binding_id",
                "service_instance_uuidv4",
            )
        ):
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE_OWNER", "Typed PR owner mismatch"
            )
        scope = candidate["acquisition_scope"]
        if scope.get("change_request_id") != candidate["change_request_id"]:
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE_SCOPE", "Capture parent mismatch"
            )
        from repo_catalog.adapters.sqlite.json_contracts import (
            validate_acquisition_scope,
            validate_field_evidence,
        )

        pending = validate_acquisition_scope(
            self.c,
            scope,
            service_instance_uuidv4=candidate["service_instance_uuidv4"],
            repository_uuidv4=candidate["repository_uuidv4"],
            repository_binding_id=candidate["repository_binding_id"],
        )
        pending += validate_field_evidence(
            self.c, candidate.get("field_evidence", {}), candidate
        )
        return "missing capture dependencies" if pending else None

    def _project_child_membership(self, candidate):
        return candidate

    def candidate_from_row(self, table, row):
        if table == "source_repositories":
            candidate = dict(row)
            candidate["kind"] = "source-repository"
            for stored, plain in (
                ("metadata_json", "metadata"),
                ("scope_json", "acquisition_scope"),
                ("field_evidence_json", "field_evidence"),
            ):
                candidate[plain] = json.loads(candidate.pop(stored))
            return candidate
        if table not in TABLES:
            raise ValueError("Unsupported typed API table")
        candidate = dict(row)
        candidate["metadata"] = json.loads(candidate["metadata"])
        candidate["acquisition_scope"] = json.loads(
            candidate.pop("acquisition_scope_json")
        )
        candidate["field_evidence"] = json.loads(candidate.pop("field_evidence_json"))
        for name in _BINARY & candidate.keys():
            value = candidate[name]
            if value is not None:
                candidate[name] = (
                    value.decode("utf-8") if name == "raw_path" else value.hex()
                )
        if table == "document_state":
            digest = candidate.pop("text_body_sha256")
            candidate["body"] = None
            if digest is not None:
                body = self._one(
                    "SELECT body,byte_length FROM text_bodies WHERE sha256=?", (digest,)
                )
                if not body:
                    raise CatalogError(
                        "CURRENT_BODY_MISSING", "Document body unavailable"
                    )
                verify_text_body(body["body"], digest, body["byte_length"])
                candidate["body"] = body["body"]
        return candidate

    def _write(self, table, candidate, previous):
        values = dict(candidate)
        if table == "document_state":
            self.c.execute(
                "INSERT INTO documents(change_request_id,kind,provider_change_request_document_id) SELECT ?,?,? WHERE NOT EXISTS(SELECT 1 FROM documents WHERE change_request_id=? AND kind=? AND provider_change_request_document_id=?)",
                (*self._table_key(candidate)[1], *self._table_key(candidate)[1]),
            )
            body = values.pop("body")
            values["text_body_sha256"] = (
                intern_text_body(self.c, body) if body is not None else None
            )
        elif table == "review_thread_state":
            self.c.execute(
                "INSERT INTO review_threads(change_request_id,provider_resource_id) SELECT ?,? WHERE NOT EXISTS(SELECT 1 FROM review_threads WHERE change_request_id=? AND provider_resource_id=?)",
                (*self._table_key(candidate)[1], *self._table_key(candidate)[1]),
            )
        values["metadata"] = _canonical(values["metadata"])
        values["acquisition_scope_json"] = _canonical(values.pop("acquisition_scope"))
        values["field_evidence_json"] = _canonical(values.pop("field_evidence"))
        for name in _BINARY & values.keys():
            if values[name] is not None:
                values[name] = (
                    values[name].encode("utf-8")
                    if name == "raw_path"
                    else bytes.fromhex(values[name])
                )
        _, key, where = self._table_key(candidate)
        if previous is None:
            self.c.execute(
                f"INSERT INTO {table}({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                tuple(values.values()),
            )
        else:
            updates = {
                name: value for name, value in values.items() if name not in key._fields
            }
            self.c.execute(
                f"UPDATE {table} SET {','.join(name + '=?' for name in updates)} WHERE {where}",
                (*updates.values(), *key),
            )

    def admit(self, table, candidate, **options):
        if table == "source_repositories":
            return self.admit_source_row(
                self.source_candidate_row(candidate), **options
            )
        if table not in TABLES or self._table_key(candidate)[0] != table:
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE", "Typed API table/key mismatch"
            )
        return super().admit(candidate, **options)

    def _promote_staging(self):
        count = 0
        while True:
            changed = False
            for row in self._all(
                "SELECT * FROM exchange_staging WHERE table_name IN ('change_request_state','document_state','review_thread_state') AND reason='current_state:missing_dependency'"
            ):
                candidate = json.loads(row["record_json"])
                try:
                    with self._transaction():
                        if self._missing(candidate):
                            continue
                        self.c.execute(
                            "DELETE FROM exchange_staging WHERE record_key=? AND content_sha256=?",
                            (row["record_key"], row["content_sha256"]),
                        )
                        result = self.admit(
                            row["table_name"], candidate, source="import"
                        )
                except (CatalogError, sqlite3.IntegrityError) as error:
                    if isinstance(error, CatalogError) and not error.code.startswith(
                        ("INVALID_CURRENT_RESOURCE", "INVALID_JSON_REFERENCE")
                    ):
                        raise
                    self.c.execute(
                        "UPDATE exchange_staging SET reason='current_state:invalid' WHERE record_key=? AND content_sha256=?",
                        (row["record_key"], row["content_sha256"]),
                    )
                    continue
                if result.status in {"accepted", "identical", "stale"}:
                    count += 1
                    changed = True
            if not changed:
                return count

    def export_candidates(self, repository_uuidv4):
        result = []
        for table in sorted(TABLES):
            for row in self._all(
                f"SELECT * FROM {table} WHERE repository_uuidv4=?", (repository_uuidv4,)
            ):
                candidate = self.candidate_from_row(table, row)
                result.append(
                    (
                        table,
                        candidate,
                        any(
                            stage["reason"] == "current_state:conflict"
                            for stage in self._stages(candidate)
                        ),
                    )
                )
        for stage in self._all(
            "SELECT * FROM exchange_staging WHERE repository_uuidv4=? AND table_name IN ('change_request_state','document_state','review_thread_state') AND reason IN ('current_state:conflict','current_state:missing_dependency')",
            (repository_uuidv4,),
        ):
            result.append(
                (
                    stage["table_name"],
                    json.loads(stage["record_json"]),
                    stage["reason"] == "current_state:conflict",
                )
            )
        for row in self._all(
            "SELECT * FROM source_repositories WHERE repository_uuidv4=?",
            (repository_uuidv4,),
        ):
            candidate = self.candidate_from_row("source_repositories", row)
            result.append(
                (
                    "source_repositories",
                    candidate,
                    bool(
                        self._source_stages(candidate["source_id"], repository_uuidv4)
                    ),
                )
            )
        for stage in self._all(
            "SELECT * FROM exchange_staging WHERE repository_uuidv4=? AND table_name='source_repositories' AND reason='current_state:conflict'",
            (repository_uuidv4,),
        ):
            result.append(
                ("source_repositories", json.loads(stage["record_json"]), True)
            )
        return result

    @staticmethod
    def source_candidate_row(candidate):
        row = {
            name: candidate.get(name)
            for name in (
                "source_id",
                "repository_uuidv4",
                "first_seen_us",
                "last_seen_us",
                "name",
                "parser_module",
                "parser_version",
            )
        }
        row["last_seen_us"] = candidate.get(
            "last_seen_us", candidate.get("observed_at_us")
        )
        row["first_seen_us"] = candidate.get("first_seen_us", row["last_seen_us"])
        for plain, stored in (
            ("metadata", "metadata_json"),
            ("acquisition_scope", "scope_json"),
            ("field_evidence", "field_evidence_json"),
        ):
            row[stored] = _canonical(candidate.get(plain, {}))
        return row

    @staticmethod
    def _source_stage_key(source_id, repository_uuidv4):
        return (
            "source-current:"
            + hashlib.sha256(
                _canonical([source_id, repository_uuidv4]).encode()
            ).hexdigest()
        )

    def _source_stages(self, source_id, repository_uuidv4):
        return self._all(
            "SELECT * FROM exchange_staging WHERE record_key=? AND reason='current_state:conflict'",
            (self._source_stage_key(source_id, repository_uuidv4),),
        )

    def admit_source_row(self, row, *, source="import", **options):
        """Admit one known positive pair with its current attribute evidence."""
        from repo_catalog.adapters.sqlite.json_contracts import validate_record

        row = dict(row)
        validate_record(self.c, "source_repositories", row)
        candidate = self.candidate_from_row("source_repositories", row)
        first, last = candidate["first_seen_us"], candidate["last_seen_us"]
        for value in (first, last):
            if value is not None:
                validate_epoch_us(value)
        evidence = candidate["field_evidence"]
        if candidate["name"] is None and not candidate["metadata"] and not evidence:
            # Older/bootstrap positive associations need no invented producer or
            # observation. Their absence of attributes cannot overwrite knowledge.
            with self._transaction():
                self.c.execute(
                    "INSERT INTO source_repositories(source_id,repository_uuidv4,first_seen_us,last_seen_us) VALUES(?,?,?,?) ON CONFLICT(source_id,repository_uuidv4) DO UPDATE SET first_seen_us=CASE WHEN source_repositories.first_seen_us IS NULL THEN excluded.first_seen_us WHEN excluded.first_seen_us IS NULL THEN source_repositories.first_seen_us ELSE min(source_repositories.first_seen_us,excluded.first_seen_us) END,last_seen_us=CASE WHEN source_repositories.last_seen_us IS NULL THEN excluded.last_seen_us WHEN excluded.last_seen_us IS NULL THEN source_repositories.last_seen_us ELSE max(source_repositories.last_seen_us,excluded.last_seen_us) END",
                    (
                        candidate["source_id"],
                        candidate["repository_uuidv4"],
                        first,
                        last,
                    ),
                )
            return "accepted"
        if last is None:
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE",
                "Named Source values require observation evidence",
            )
        fields = {"metadata": candidate["metadata"]}
        if candidate["name"] is not None:
            fields["name"] = candidate["name"]
        required = _field_values(fields)
        if not candidate["metadata"] and '["metadata"]' not in evidence:
            required.pop('["metadata"]', None)
        if required.keys() - evidence.keys() or evidence.keys() - required.keys():
            raise CatalogError(
                "INVALID_CURRENT_RESOURCE",
                "Named Source values require exact current field evidence",
            )
        return self.confirm_source_repository(
            candidate["source_id"],
            candidate["repository_uuidv4"],
            observed_at_us=last,
            first_seen_us=first,
            scope=candidate["acquisition_scope"],
            parser_module=candidate["parser_module"],
            parser_version=candidate["parser_version"],
            name=candidate["name"],
            metadata=candidate["metadata"] if '["metadata"]' in evidence else None,
            parsed_at_us=max(proof["parsed_at_us"] for proof in evidence.values()),
            field_evidence=evidence,
            source=source,
            **options,
        )

    def confirm_source_repository(
        self,
        source_id,
        repository_uuidv4,
        *,
        observed_at_us,
        scope,
        parser_module,
        parser_version,
        name=None,
        metadata=None,
        parsed_at_us=None,
        field_evidence=None,
        first_seen_us=None,
        source="live",
        base_revision=None,
        scope_context=None,
    ):
        from repo_catalog.domain.time import now_us

        from .json_contracts import _check_schema, validate_capture_shape

        validate_capture_shape(scope)
        if metadata is not None:
            _check_schema("source_repositories", "metadata_json", metadata, {})
        validate_epoch_us(observed_at_us)
        if first_seen_us is not None:
            validate_epoch_us(first_seen_us)
        parsed_at_us = now_us() if parsed_at_us is None else parsed_at_us
        validate_epoch_us(parsed_at_us)
        for value in (parser_module, parser_version):
            if not isinstance(value, str) or not value or "\0" in value:
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE",
                    "Source attribution requires actual producer",
                )
        if source not in {"live", "import"}:
            raise ValueError("Unknown Source admission source")
        incoming = {
            "kind": "source-repository",
            "source_id": source_id,
            "repository_uuidv4": repository_uuidv4,
            "provider_updated_at_us": None,
            "provider_clock_scope": None,
            "observed_at_us": observed_at_us,
            "parsed_at_us": parsed_at_us,
            "parser_module": parser_module,
            "parser_version": parser_version,
            "acquisition_scope": scope,
        }
        if name is not None:
            if not isinstance(name, str):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE", "Source member name requires text"
                )
            incoming["name"] = name
        if metadata is not None:
            if not isinstance(metadata, dict):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE", "Source member metadata requires object"
                )
            incoming["metadata"] = metadata
        if field_evidence is not None:
            incoming["field_evidence"] = dict(field_evidence)
        with self._transaction():
            owner = self._one("SELECT * FROM sources WHERE source_id=?", (source_id,))
            if (
                owner is None
                or self._one(
                    "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
                    (repository_uuidv4,),
                )
                is None
            ):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE_OWNER",
                    "Source roster requires registered typed identities",
                )
            if scope.get("source_registration_uuidv4") != owner[
                "source_registration_uuidv4"
            ] or (
                owner["service_instance_uuidv4"] is not None
                and scope.get("service_instance_uuidv4")
                != owner["service_instance_uuidv4"]
            ):
                raise CatalogError(
                    "INVALID_CURRENT_RESOURCE_SCOPE",
                    "Inventory capture differs from Source",
                )
            if field_evidence is not None:
                from repo_catalog.adapters.sqlite.json_contracts import validate_record

                validate_record(
                    self.c, "source_repositories", self.source_candidate_row(incoming)
                )
                for proof in field_evidence.values():
                    capture = proof["acquisition_scope"]
                    if capture.get("source_registration_uuidv4") != owner[
                        "source_registration_uuidv4"
                    ] or (
                        owner["service_instance_uuidv4"] is not None
                        and capture.get("service_instance_uuidv4")
                        != owner["service_instance_uuidv4"]
                    ):
                        raise CatalogError(
                            "INVALID_CURRENT_RESOURCE_SCOPE",
                            "Field capture differs from Source",
                        )
            old = self._one(
                "SELECT * FROM source_repositories WHERE source_id=? AND repository_uuidv4=?",
                (source_id, repository_uuidv4),
            )
            previous = None
            if old is not None:
                previous = {
                    "kind": "source-repository",
                    "source_id": source_id,
                    "repository_uuidv4": repository_uuidv4,
                    "name": old["name"],
                    "metadata": json.loads(old["metadata_json"]),
                    "field_evidence": json.loads(old["field_evidence_json"]),
                    "provider_updated_at_us": None,
                    "provider_clock_scope": None,
                    "observed_at_us": old["last_seen_us"],
                    "parsed_at_us": parsed_at_us,
                    "parser_module": old["parser_module"],
                    "parser_version": old["parser_version"],
                    "acquisition_scope": json.loads(old["scope_json"]),
                }
            engine = _SourceFieldEngine(self.c)
            revision = self._one(
                "SELECT db_instance_id,local_revision FROM database_identity WHERE singleton=1"
            )
            authoritative = (
                source == "live"
                and base_revision is not None
                and dict(base_revision) == revision
                and scope_context is not None
                and dict(scope_context) == scope
            )
            candidate, conflict, _ = engine._merge_fields(
                incoming, previous, authoritative
            )
            key = self._source_stage_key(source_id, repository_uuidv4)
            stages = self._source_stages(source_id, repository_uuidv4)
            earliest = first_seen_us if first_seen_us is not None else observed_at_us
            first_seen = (
                earliest
                if old is None or old["first_seen_us"] is None
                else min(old["first_seen_us"], earliest)
            )
            supplied = engine._observation_evidence(incoming)
            old_values = _field_values(previous) if previous is not None else {}
            unchanged_current = previous is not None and all(
                path in old_values and _equal_field(value, old_values[path])
                for path, value in _field_values(incoming).items()
            )
            if not conflict:
                conflict = any(
                    not engine._dominates(
                        candidate,
                        json.loads(stage["record_json"]),
                        supplied if authoritative else (),
                    )
                    for stage in stages
                )
            if conflict and not unchanged_current:
                alternative = engine._complete(incoming, None)
                alternative["field_evidence"] = supplied
                alternative["first_seen_us"] = (
                    first_seen_us if first_seen_us is not None else observed_at_us
                )
                alternative["last_seen_us"] = observed_at_us
                digest = hashlib.sha256(
                    _canonical(
                        {
                            k: v
                            for k, v in alternative.items()
                            if k in {"name", "metadata"}
                        }
                    ).encode()
                ).digest()
                if len(stages) >= 16 and all(
                    stage["content_sha256"] != digest for stage in stages
                ):
                    raise CatalogError(
                        "CURRENT_STATE_STAGING_FULL",
                        "Source association has sixteen unresolved alternatives",
                    )
                self.c.execute(
                    "INSERT INTO exchange_staging(record_key,content_sha256,table_name,repository_uuidv4,origin_catalog_uuidv4,record_json,reason) VALUES(?,?,'source_repositories',?,?,?,'current_state:conflict') ON CONFLICT(record_key,content_sha256) DO UPDATE SET record_json=excluded.record_json",
                    (
                        key,
                        digest,
                        repository_uuidv4,
                        revision["db_instance_id"],
                        _canonical(alternative),
                    ),
                )
                if old is not None:
                    self.c.execute(
                        "UPDATE source_repositories SET first_seen_us=?,last_seen_us=? WHERE source_id=? AND repository_uuidv4=?",
                        (
                            first_seen,
                            max(old["last_seen_us"], observed_at_us)
                            if old["last_seen_us"] is not None
                            else observed_at_us,
                            source_id,
                            repository_uuidv4,
                        ),
                    )
                return "conflict"
            last_seen = (
                observed_at_us
                if old is None or old["last_seen_us"] is None
                else max(old["last_seen_us"], observed_at_us)
            )
            values = (
                first_seen,
                last_seen,
                candidate.get("name"),
                _canonical(candidate["metadata"]),
                _canonical(candidate["acquisition_scope"]),
                candidate["parser_module"],
                candidate["parser_version"],
                _canonical(candidate["field_evidence"]),
                source_id,
                repository_uuidv4,
            )
            if old is None:
                self.c.execute(
                    "INSERT INTO source_repositories(first_seen_us,last_seen_us,name,metadata_json,scope_json,parser_module,parser_version,field_evidence_json,source_id,repository_uuidv4) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    values,
                )
            else:
                self.c.execute(
                    "UPDATE source_repositories SET first_seen_us=?,last_seen_us=?,name=?,metadata_json=?,scope_json=?,parser_module=?,parser_version=?,field_evidence_json=? WHERE source_id=? AND repository_uuidv4=?",
                    values,
                )
            if not conflict:
                self.c.execute(
                    "DELETE FROM exchange_staging WHERE record_key=? AND reason='current_state:conflict'",
                    (key,),
                )
            return "conflict" if conflict else "accepted"

    def assess_source_inventory(
        self,
        source_id,
        *,
        scope,
        observed_at_us,
        state,
        members,
        terminal,
        reason=None,
        parser_module,
        parser_version,
    ):
        from repo_catalog.adapters.sqlite.json_contracts import validate_record

        validate_epoch_us(observed_at_us)
        if type(terminal) is not bool:
            raise CatalogError(
                "INVALID_COLLECTION_PROOF", "Terminal evidence must be boolean"
            )
        if state == "complete" and not terminal:
            raise CatalogError(
                "INVALID_COLLECTION_PROOF",
                "Inventory completion needs terminal evidence",
            )
        scope_key = hashlib.sha256(_canonical(scope).encode()).hexdigest()
        with self._transaction():
            validate_record(
                self.c,
                "source_inventory_assessments",
                {
                    "source_id": source_id,
                    "scope_json": _canonical(scope),
                    "state": state,
                    "terminal": int(terminal),
                    "members_json": _canonical(members),
                },
            )
            self.c.execute(
                "INSERT INTO source_inventory_assessments(source_id,scope_key,scope_json,observed_at_us,state,terminal,members_json,parser_module,parser_version,reason) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id,scope_key,observed_at_us,state) DO NOTHING",
                (
                    source_id,
                    scope_key,
                    _canonical(scope),
                    observed_at_us,
                    state,
                    int(terminal),
                    _canonical(members),
                    parser_module,
                    parser_version,
                    reason,
                ),
            )


class _SourceFieldEngine(CurrentResources):
    def _complete(self, incoming, previous):
        candidate = dict(previous or {})
        candidate.update(incoming)
        candidate.setdefault("name", None)
        candidate.setdefault("metadata", {})
        return candidate
