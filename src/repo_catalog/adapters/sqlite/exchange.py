"""Single-repository portable record graphs, with durable dependency staging.

SQLite integer primary keys never cross the boundary as identities. Every FK is
encoded as an explicit record reference; identities with no natural portable key
receive a persisted random identifier, reused on every subsequent export.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
import uuid
from collections import defaultdict

from repo_catalog.adapters.sqlite.payloads import intern_stored_bytes
from repo_catalog.domain.models import CatalogError

FORMAT = "repo-catalog/repository-exchange-v1"
EXCLUDED = {
    "database_identity",
    "jobs",
    "job_attempts",
    "job_source_plans",
    "acquisition_progress",
    "collection_progress",
    "code_listing_progress",
    "resume_cursors",
    "validators",
    "inventory_observations",
    "source_input_observations",
    "cache_locators",
    "content_locations",
    "active_cache_entries",
    "cache_leases",
    "space_reservations",
    "preservation_obligations",
    "search_documents",
    "index_generations",
    "index_membership",
    "payload_quarantine",
    "payload_repairs",
    "unresolved_payloads",
    "payload_admission_staging",
    "parser_profile_selection_staging",
    "fact_selection_staging",
    "identity_relation_staging",
}
GLOBAL = {
    "service_instances",
    "sources",
    "stored_bytes",
    "payloads",
    "text_bodies",
    "git_objects",
    "contents",
    "parser_profiles",
    "parser_profile_capabilities",
    "parser_profile_verifications",
    "parser_profile_verification_invalidations",
}
GIT_CHILDREN = {
    "commits": "git_object_id",
    "commit_parents": "commit_git_object_id",
    "tree_entries": "tree_git_object_id",
    "tag_objects": "git_object_id",
    "blob_content_map": "git_object_id",
    "content_digests": "content_id",
    "root_manifests": "tree_git_object_id",
    "root_manifest_entries": "tree_git_object_id",
}
NATURAL = {
    "sources": ("source_registration_uuidv4",),
    "stored_bytes": ("sha256",),
    "payloads": ("representation", "sha256"),
    "text_bodies": ("sha256",),
    "git_objects": ("object_format", "oid"),
    "coverage_claims": ("coverage_scope_id", "observed_at_us", "coverage_state"),
}
LOCAL_COLUMNS = {
    "repositories": {"preferred_repository_endpoint_id", "current_snapshot_id"},
    "change_requests": {"current_change_request_observation_id"},
    "documents": {"current_document_observation_id"},
}
SCOPES = {"parser_profile_selection_scopes", "fact_selection_scopes", "coverage_scopes"}
SHA = re.compile(r"[0-9a-f]{64}\Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_digest(record):
    # Dependency manifests and mutable membership interval aggregates are
    # transport projections, not immutable identity/fact content.
    content = {k: v for k, v in record.items() if k != "requires"}
    if record["table"] == "source_repositories":
        content["values"] = {
            k: v
            for k, v in record["values"].items()
            if k not in {"first_seen_us", "last_seen_us"}
        }
    return hashlib.sha256(canonical(content).encode()).digest()


def encode(value, column=""):
    if isinstance(value, bytes):
        if "sha256" in column:
            if len(value) != 32:
                raise CatalogError("INVALID_EXCHANGE", "SHA-256 must contain 32 bytes")
            return {"$sha256": value.hex()}
        return {"$bytes": base64.b64encode(value).decode("ascii")}
    return value


def decode(value):
    if not isinstance(value, dict):
        if value is not None and type(value) not in (str, int, float):
            raise CatalogError("INVALID_EXCHANGE", "Invalid scalar value")
        return value
    if set(value) == {"$sha256"} and isinstance(value["$sha256"], str):
        if not SHA.fullmatch(value["$sha256"]):
            raise CatalogError(
                "INVALID_EXCHANGE", "SHA-256 must be lowercase 64-digit hex"
            )
        return bytes.fromhex(value["$sha256"])
    if set(value) == {"$bytes"} and isinstance(value["$bytes"], str):
        try:
            return base64.b64decode(value["$bytes"], validate=True)
        except (ValueError, TypeError) as exc:
            raise CatalogError("INVALID_EXCHANGE", "Invalid base64 bytes") from exc
    raise CatalogError("INVALID_EXCHANGE", "Invalid typed value")


class Graph:
    def __init__(self, db):
        self.db = db
        self.columns, self.keys, self.foreign = {}, {}, {}
        names = [
            r[0]
            for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        ]
        for table in names:
            if table in EXCLUDED or table.startswith(
                ("sqlite_", "exchange_", "local_", "fts_")
            ):
                continue
            if not re.fullmatch("[a-z_]+", table):
                continue
            info = list(db.execute(f'PRAGMA table_info("{table}")'))
            self.columns[table] = {r[1]: r[2] for r in info}
            self.keys[table] = tuple(
                r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]
            )
            grouped = defaultdict(list)
            for row in db.execute(f'PRAGMA foreign_key_list("{table}")'):
                grouped[row[0]].append(row)
            self.foreign[table] = []
            for group in grouped.values():
                group.sort(key=lambda r: r[1])
                self.foreign[table].append(
                    (
                        group[0][2],
                        tuple(r[3] for r in group),
                        tuple(r[4] for r in group),
                    )
                )
        self.key_cache = {}

    def rows(self, table):
        columns = tuple(self.columns[table])
        return [
            dict(zip(columns, row))
            for row in self.db.execute(f'SELECT * FROM "{table}"')
        ]

    def lookup(self, table, columns, values, *, allow_null=False):
        if table not in self.columns or (
            not allow_null and any(v is None for v in values)
        ):
            return None
        sql = " AND ".join(f'"{c}" IS ?' for c in columns)
        row = self.db.execute(f'SELECT * FROM "{table}" WHERE {sql}', values).fetchone()
        return dict(zip(self.columns[table], row)) if row is not None else None

    def local_key(self, table, row):
        return canonical({c: encode(row[c], c) for c in self.keys[table]})

    def portable_columns(self, table):
        if table in SCOPES:
            return tuple(c for c in self.columns[table] if c not in self.keys[table])
        if table in NATURAL:
            return NATURAL[table]
        pk = self.keys[table]
        if len(pk) == 1 and self.columns[table][pk[0]] == "INTEGER":
            candidate = pk[0].removesuffix("_id") + "_uuidv4"
            if candidate in self.columns[table]:
                return (candidate,)
        return pk

    def key(self, table, row):
        local = self.local_key(table, row)
        cache_key = (table, local)
        if cache_key in self.key_cache:
            return self.key_cache[cache_key]
        previous = self.db.execute(
            "SELECT record_key FROM exchange_local_identities WHERE table_name=? AND local_key_json=?",
            cache_key,
        ).fetchone()
        if previous:
            self.key_cache[cache_key] = previous[0]
            return previous[0]
        columns = self.portable_columns(table)
        values = {}
        for col in columns:
            value = row[col]
            if (
                self.columns[table][col] == "INTEGER"
                and col in self.keys[table]
                and len(self.keys[table]) == 1
                and not any(col in fk[1] for fk in self.foreign[table])
            ):
                # Remaining integer-only entities are distinct registrations,
                # not content identities (notably general contents).
                value = str(uuid.uuid4())
            else:
                for parent, child_cols, parent_cols in self.foreign[table]:
                    if col not in child_cols or parent not in self.columns:
                        continue
                    parent_row = self.lookup(
                        parent, parent_cols, tuple(row[c] for c in child_cols)
                    )
                    if parent_row is not None:
                        value = {
                            "$ref": self.key(parent, parent_row),
                            "column": parent_cols[child_cols.index(col)],
                        }
                        break
            values[col] = encode(value, col)
        key = table + ":" + canonical(values)
        self.db.execute(
            "INSERT INTO exchange_local_identities VALUES(?,?,?)", (table, local, key)
        )
        self.key_cache[cache_key] = key
        return key

    def record(self, table, row):
        data = {c: encode(v, c) for c, v in row.items()}
        for col in LOCAL_COLUMNS.get(table, ()):
            if col in data:
                data[col] = None
        # Never transport catalog-local integer keys or source handles.
        pk = self.keys[table]
        if (
            len(pk) == 1
            and self.columns[table][pk[0]] == "INTEGER"
            and not any(pk[0] in fk[1] for fk in self.foreign[table])
        ):
            data.pop(pk[0])
        if table == "sources":
            data.pop("source_id")
        if table in SCOPES:
            for col in self.keys[table]:
                data.pop(col)
        if table == "root_manifests":
            # A receiver must verify/rebuild its own derived tree listing.
            # Retain entries, without exporting an unsupported completeness claim.
            data["complete"] = 0
        for parent, child_cols, parent_cols in self.foreign[table]:
            if parent not in self.columns or any(row[c] is None for c in child_cols):
                continue
            if any(c in LOCAL_COLUMNS.get(table, ()) for c in child_cols):
                continue
            parent_row = self.lookup(
                parent, parent_cols, tuple(row[c] for c in child_cols)
            )
            if parent_row is None:
                raise CatalogError(
                    "INVALID_EXCHANGE", "Catalog has an unresolved foreign key"
                )
            key = self.key(parent, parent_row)
            for child, pcol in zip(child_cols, parent_cols):
                if child in data and not (
                    isinstance(data[child], dict) and "$ref" in data[child]
                ):
                    data[child] = {"$ref": key, "column": pcol}
        record = {"key": self.key(table, row), "table": table, "values": data}
        if table == "completion_markers":
            required = set()
            for occurrence in self.rows("fetch_occurrences"):
                if occurrence["fetch_collection_id"] == row["fetch_collection_id"]:
                    required.add(self.key("fetch_occurrences", occurrence))
            evidence = json.loads(row["evidence"])
            observation_uuid = evidence.get("change_request_observation_uuidv4")
            if observation_uuid:
                observation = self.lookup(
                    "change_request_observations",
                    ("change_request_observation_uuidv4",),
                    (observation_uuid,),
                )
                if observation:
                    required.add(self.key("change_request_observations", observation))
            record["requires"] = sorted(required)
        return record

    def export(self, repository_uuidv4):
        rows = {table: self.rows(table) for table in self.columns}
        included = set()
        selected = {}

        def add(table, row):
            if (
                row.get("owner_kind") == "source"
                and table != "parser_profile_capabilities"
            ):
                return False
            if "repository_uuidv4" in row and row["repository_uuidv4"] not in (
                None,
                repository_uuidv4,
            ):
                return False
            if row.get("parsed_result_uuidv4") and table != "parsed_results":
                owner = self.db.execute(
                    "SELECT owner_kind FROM parsed_results WHERE parsed_result_uuidv4=?",
                    (row["parsed_result_uuidv4"],),
                ).fetchone()
                if owner and owner[0] == "source":
                    return False
            if table == "coverage_scopes" and row.get("kind", "").startswith(
                "inventory"
            ):
                return False
            identifier = (table, self.local_key(table, row))
            if identifier in included:
                return False
            included.add(identifier)
            selected[identifier] = row
            return True

        for table, values in rows.items():
            for row in values:
                if row.get("repository_uuidv4") == repository_uuidv4:
                    add(table, row)
        if not any(t == "repositories" for t, _ in included):
            raise CatalogError("NOT_FOUND", "Repository UUID is not registered")
        changed = True
        while changed:
            changed = False
            # Close every actual FK upward, preserving the original fetch and
            # original response bytes for 304 validation evidence.
            for (table, _), row in list(selected.items()):
                for parent, child_cols, parent_cols in self.foreign[table]:
                    if parent not in rows or any(
                        c in LOCAL_COLUMNS.get(table, ()) for c in child_cols
                    ):
                        continue
                    target = self.lookup(
                        parent, parent_cols, tuple(row[c] for c in child_cols)
                    )
                    if target is not None:
                        changed |= add(parent, target)
            # Child history belongs to the selected owner; shared identities do
            # not expand to other owners or source-wide acquisition histories.
            for table, values in rows.items():
                for row in values:
                    for parent, child_cols, parent_cols in self.foreign[table]:
                        if parent not in rows or (
                            parent in GLOBAL
                            and table not in GIT_CHILDREN
                            and table
                            not in {
                                "parser_profile_capabilities",
                                "parser_profile_verifications",
                                "parser_profile_verification_invalidations",
                            }
                        ):
                            continue
                        if (
                            table in GIT_CHILDREN
                            and GIT_CHILDREN[table] not in child_cols
                        ):
                            continue
                        target = self.lookup(
                            parent, parent_cols, tuple(row[c] for c in child_cols)
                        )
                        if (
                            target is not None
                            and (parent, self.local_key(parent, target)) in included
                        ):
                            changed |= add(table, row)
                            break
        records = [self.record(table, row) for (table, _), row in selected.items()]
        # A complete claim is transported only with acquisition proof and
        # the full selected closure. The five-column stored model is unchanged.
        # Its exchange manifest prevents truncated reception inventing complete.
        proof = any(
            record["table"]
            in {"fetch_occurrences", "git_acquisitions", "parsed_result_publications"}
            for record in records
        )
        requirements = sorted(
            record["key"] for record in records if record["table"] != "coverage_claims"
        )
        safe_records = []
        for record in records:
            if (
                record["table"] == "coverage_claims"
                and record["values"]["coverage_state"] == "complete"
            ):
                if not proof:
                    continue
                record["requires"] = requirements
            safe_records.append(record)
        records = safe_records
        records.sort(key=lambda record: record["key"])
        for record in records:
            if record["table"] == "stored_bytes":
                data = record["values"]
                body, digest = decode(data["body"]), decode(data["sha256"])
                if (
                    hashlib.sha256(body).digest() != digest
                    or len(body) != data["byte_length"]
                ):
                    raise CatalogError(
                        "PAYLOAD_CORRUPTION",
                        "Cannot exchange corrupt physical bytes",
                        {"sha256": digest.hex()},
                    )
                if (
                    self.db.execute(
                        "SELECT 1 FROM sqlite_schema WHERE name='payload_quarantine'"
                    ).fetchone()
                    and self.db.execute(
                        "SELECT 1 FROM payload_quarantine WHERE sha256=?", (digest,)
                    ).fetchone()
                ):
                    raise CatalogError(
                        "PAYLOAD_QUARANTINED",
                        "Cannot exchange quarantined physical bytes",
                    )
        origin = self.db.execute(
            "SELECT db_instance_id FROM database_identity"
        ).fetchone()
        return {
            "format": FORMAT,
            "repository_uuidv4": repository_uuidv4,
            "origin_catalog_uuidv4": origin[0] if origin else str(uuid.uuid4()),
            "records": records,
        }

    def expected_columns(self, table):
        columns = set(self.columns[table])
        pk = self.keys[table]
        if (
            len(pk) == 1
            and self.columns[table][pk[0]] == "INTEGER"
            and not any(pk[0] in fk[1] for fk in self.foreign[table])
        ):
            columns.remove(pk[0])
        if table == "sources":
            columns.remove("source_id")
        if table in SCOPES:
            columns.difference_update(self.keys[table])
        return columns

    def validate_record(self, record):
        if not isinstance(record, dict) or set(record) not in (
            {"key", "table", "values"},
            {"key", "table", "values", "requires"},
        ):
            raise CatalogError("INVALID_EXCHANGE", "Invalid record envelope")
        table, data = record["table"], record["values"]
        if "requires" in record and (
            table not in {"completion_markers", "coverage_claims"}
            or not isinstance(record["requires"], list)
            or any(not isinstance(k, str) for k in record["requires"])
            or len(record["requires"]) != len(set(record["requires"]))
        ):
            raise CatalogError(
                "INVALID_EXCHANGE", "Invalid explicit dependency manifest"
            )
        if (
            table not in self.columns
            or not isinstance(data, dict)
            or set(data) != self.expected_columns(table)
        ):
            raise CatalogError("INVALID_EXCHANGE", "Unexpected table or column set")
        if not isinstance(record["key"], str) or not record["key"].startswith(
            table + ":"
        ):
            raise CatalogError("INVALID_EXCHANGE", "Invalid portable record key")
        if (
            table == "coverage_claims"
            and data.get("coverage_state") == "complete"
            and not record.get("requires")
        ):
            raise CatalogError(
                "INVALID_EXCHANGE",
                "Complete coverage requires an acquisition dependency manifest",
            )
        for col, value in data.items():
            if isinstance(value, dict) and "$ref" in value:
                if set(value) != {"$ref", "column"} or not isinstance(
                    value["$ref"], str
                ):
                    raise CatalogError(
                        "INVALID_EXCHANGE", "Invalid foreign record reference"
                    )
                valid = any(
                    value["$ref"].startswith(parent + ":")
                    and value["column"] == parent_cols[child_cols.index(col)]
                    for parent, child_cols, parent_cols in self.foreign[table]
                    if col in child_cols
                )
                if not valid:
                    raise CatalogError(
                        "INVALID_EXCHANGE",
                        "Record reference is not a declared foreign key",
                    )
            else:
                decode(value)
                if value is not None and any(
                    col in fk[1]
                    and fk[0] in self.columns
                    and all(data.get(c) is not None for c in fk[1])
                    for fk in self.foreign[table]
                ):
                    raise CatalogError(
                        "INVALID_EXCHANGE",
                        "Foreign keys require explicit portable references",
                    )
        columns = self.portable_columns(table)
        if all(col in data for col in columns):
            expected = table + ":" + canonical({col: data[col] for col in columns})
            if expected != record["key"]:
                raise CatalogError(
                    "INVALID_EXCHANGE",
                    "Declared record key disagrees with immutable identity",
                )
        if table == "stored_bytes":
            body, digest = decode(data["body"]), decode(data["sha256"])
            if (
                not isinstance(body, bytes)
                or not isinstance(digest, bytes)
                or hashlib.sha256(body).digest() != digest
                or data["byte_length"] != len(body)
            ):
                raise CatalogError(
                    "PAYLOAD_DIGEST_MISMATCH",
                    "Received bytes do not match declared SHA-256",
                )
        if table == "text_bodies":
            body, digest = data["body"], decode(data["sha256"])
            if (
                not isinstance(body, str)
                or hashlib.sha256(body.encode("utf-8")).digest() != digest
                or len(body.encode("utf-8")) != data["byte_length"]
            ):
                raise CatalogError(
                    "PAYLOAD_DIGEST_MISMATCH",
                    "Received text does not match exact UTF-8 SHA-256",
                )
        for col in LOCAL_COLUMNS.get(table, ()):
            if col in data and data[col] is not None:
                raise CatalogError(
                    "INVALID_EXCHANGE", "Local current pointers are not exchangeable"
                )

    def resolve(self, record):
        data = {}
        for col, value in record["values"].items():
            if isinstance(value, dict) and "$ref" in value:
                key = value["$ref"]
                # A disputed input must never attach incoming dependent facts
                # to the existing row merely because its UUID happens to match.
                if self.db.execute(
                    "SELECT 1 FROM exchange_staging WHERE record_key=? AND reason LIKE 'conflict:%'",
                    (key,),
                ).fetchone():
                    return None, "dependency_conflict"
                row = self.db.execute(
                    "SELECT table_name,local_key_json FROM exchange_admissions WHERE record_key=?",
                    (key,),
                ).fetchone()
                if row is None:
                    if record["table"] in {
                        "parser_profile_selection_decisions",
                        "fact_selection_decisions",
                        "identity_relations",
                        "identity_relation_cancellations",
                    }:
                        natural = json.loads(key.split(":", 1)[1])
                        if value["column"] in natural and not isinstance(
                            natural[value["column"]], dict
                        ):
                            data[col] = natural[value["column"]]
                            continue
                    return None, "missing_dependency"
                local = json.loads(row[1])
                target = self.lookup(
                    row[0], tuple(local), tuple(decode(v) for v in local.values())
                )
                if target is None:
                    return None, "missing_dependency"
                data[col] = target[value["column"]]
            else:
                data[col] = decode(value)
        return data, None

    def _existing(self, table, data):
        if table in SCOPES:
            columns = tuple(c for c in self.columns[table] if c not in self.keys[table])
            if all(c in data for c in columns):
                semantic = self.lookup(
                    table, columns, tuple(data[c] for c in columns), allow_null=True
                )
                if semantic is not None:
                    return semantic
        columns = self.portable_columns(table)
        if all(c in data for c in columns):
            return self.lookup(table, columns, tuple(data[c] for c in columns))
        return None

    def _admit(self, record, origin_catalog_uuidv4, repository_uuidv4):
        table, key = record["table"], record["key"]
        for dependency in record.get("requires", ()):
            if not self.db.execute(
                "SELECT 1 FROM exchange_admissions WHERE record_key=?", (dependency,)
            ).fetchone():
                return "missing_manifest_dependency"
            if self.db.execute(
                "SELECT 1 FROM exchange_staging WHERE record_key=? AND reason LIKE 'conflict:%'",
                (dependency,),
            ).fetchone():
                return "dependency_conflict"
        data, reason = self.resolve(record)
        if reason:
            return reason
        if (
            data.get("owner_kind") == "source"
            and table != "parser_profile_capabilities"
        ):
            return "invalid:source_wide_record"
        if data.get("repository_uuidv4") not in (None, repository_uuidv4):
            return "invalid:cross_repository_owner"
        if table == "completion_markers":
            evidence = json.loads(data["evidence"])
            if "change_request_observation_id" in evidence:
                return "invalid:local_identity_in_evidence"
            observation_uuid = evidence.get("change_request_observation_uuidv4")
            if observation_uuid:
                anchor = self.db.execute(
                    "SELECT o.parsed_result_uuidv4,f.fetch_occurrence_uuidv4,f.payload_representation,f.payload_sha256,o.change_request_id,o.repository_uuidv4,c.change_request_id,c.repository_uuidv4 FROM change_request_observations o JOIN fetch_occurrences f ON f.fetch_occurrence_id=o.origin_fetch_occurrence_id JOIN fetch_collections c ON c.fetch_collection_id=? WHERE o.change_request_observation_uuidv4=?",
                    (data["fetch_collection_id"], observation_uuid),
                ).fetchone()
                if anchor is None:
                    return "missing_completion_observation"
                if anchor[4:6] != anchor[6:8] or any(
                    evidence.get(name) != anchor[index]
                    for index, name in enumerate(
                        ("parsed_result_uuidv4", "fetch_occurrence_uuidv4")
                    )
                ):
                    return "invalid:completion_origin"
                if "payload" in evidence and evidence["payload"] != {
                    "representation": anchor[2],
                    "sha256": anchor[3].hex(),
                }:
                    return "invalid:completion_payload"
        existing = self._existing(table, data)
        if table == "stored_bytes" and existing is not None:
            intern_stored_bytes(self.db, data["body"], data["sha256"])
        if table == "sources":
            if existing is not None:
                # Name/settings belong to this receiver; service/type are
                # immutable portable registration identity.
                if any(
                    existing[c] != data[c]
                    for c in ("service_instance_uuidv4", "discovery_kind")
                ):
                    return "conflict:source_identity"
            else:
                data.update(source_id=str(uuid.uuid4()), settings=None)
            provenance = canonical(record["values"])
        elif table in {"repositories", "service_instances"} and existing is not None:
            # Mutable labels are not identity claims. Portable bindings and
            # explicit name observations carry their separate immutable facts.
            data = existing
        elif existing is not None:
            if table == "source_repositories":
                self.merge_source_membership(existing, data)
                data = self.lookup(
                    table, self.keys[table], tuple(data[c] for c in self.keys[table])
                )
                existing = data
            if table in SCOPES:
                data.update({c: existing[c] for c in self.keys[table]})
            if any(existing.get(c) != value for c, value in data.items()):
                return "conflict:immutable_content"
        if existing is None:
            if table in SCOPES:
                data.update({c: str(uuid.uuid4()) for c in self.keys[table]})
            if table in {
                "parser_profile_selection_decisions",
                "fact_selection_decisions",
            }:
                from repo_catalog.adapters.sqlite.parser_model import ParserModel

                model = ParserModel(self.db)
                method = (
                    model.receive_profile_decision
                    if table == "parser_profile_selection_decisions"
                    else model.receive_fact_decision
                )
                if method(data) == "staged":
                    return "missing_parser_dependency"
            elif table in {"identity_relations", "identity_relation_cancellations"}:
                from repo_catalog.adapters.sqlite.identity_relations import (
                    IdentityRelations,
                )

                state = IdentityRelations(self.db).admit(
                    "relation" if table == "identity_relations" else "cancellation",
                    data,
                )
                if state not in {"accepted", "duplicate"}:
                    return "missing_identity_dependency"
            elif table == "stored_bytes":
                intern_stored_bytes(self.db, data["body"], data["sha256"])
            else:
                columns = tuple(data)
                sql = (
                    f'INSERT INTO "{table}" ('
                    + ",".join(f'"{c}"' for c in columns)
                    + ") VALUES("
                    + ",".join("?" for _ in columns)
                    + ")"
                )
                cursor = self.db.execute(sql, tuple(data[c] for c in columns))
                pk = self.keys[table]
                if len(pk) == 1 and pk[0] not in data:
                    data[pk[0]] = cursor.lastrowid
            existing = data
        local = self.local_key(table, existing)
        serialized = canonical(record)
        digest = record_digest(record)
        self.db.execute(
            "INSERT INTO exchange_admissions VALUES(?,?,?,?,?)",
            (key, table, local, digest, serialized),
        )
        known = self.db.execute(
            "SELECT record_key FROM exchange_local_identities WHERE table_name=? AND local_key_json=?",
            (table, local),
        ).fetchone()
        if known is None:
            self.db.execute(
                "INSERT INTO exchange_local_identities VALUES(?,?,?)",
                (table, local, key),
            )
        if table == "sources":
            digest = hashlib.sha256(provenance.encode()).digest()
            self.db.execute(
                "INSERT OR IGNORE INTO exchange_source_provenance VALUES(?,?,?,?)",
                (
                    existing["source_registration_uuidv4"],
                    origin_catalog_uuidv4,
                    digest,
                    provenance,
                ),
            )
        return None

    def receive(self, unit):
        if (
            not isinstance(unit, dict)
            or set(unit)
            != {"format", "repository_uuidv4", "origin_catalog_uuidv4", "records"}
            or unit["format"] != FORMAT
            or not isinstance(unit["records"], list)
        ):
            raise CatalogError(
                "INVALID_EXCHANGE", "Unsupported repository exchange unit"
            )
        for name in ("repository_uuidv4", "origin_catalog_uuidv4"):
            try:
                value = uuid.UUID(unit[name])
                if value.version != 4 or str(value) != unit[name]:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError) as exc:
                raise CatalogError(
                    "INVALID_EXCHANGE",
                    "Exchange owner identity must be canonical UUIDv4",
                ) from exc
        # Validate EVERY byte before persisting incoming records. A bad body
        # and all records that depend on it are rejected, while unrelated valid
        # evidence can still be admitted. Rejected bytes are never staged.
        rejected = set()
        for record in unit["records"]:
            try:
                self.validate_record(record)
            except CatalogError as exc:
                if exc.code != "PAYLOAD_DIGEST_MISMATCH":
                    raise
                rejected.add(record["key"])
        changed = True
        while changed:
            changed = False
            for record in unit["records"]:
                if record["key"] in rejected:
                    continue
                if any(
                    isinstance(v, dict) and v.get("$ref") in rejected
                    for v in record["values"].values()
                ) or any(key in rejected for key in record.get("requires", ())):
                    rejected.add(record["key"])
                    changed = True
        records = [
            record for record in unit["records"] if record["key"] not in rejected
        ]
        owner_key = "repositories:" + canonical(
            {"repository_uuidv4": unit["repository_uuidv4"]}
        )
        for record in records:
            data = record["values"]
            if record["table"] == "repositories" and record["key"] != owner_key:
                raise CatalogError(
                    "INVALID_EXCHANGE", "An exchange unit must contain one repository"
                )
            owner = data.get("repository_uuidv4")
            if (
                owner is not None
                and isinstance(owner, dict)
                and owner.get("$ref", "").startswith("repositories:")
                and owner["$ref"] != owner_key
            ):
                raise CatalogError(
                    "INVALID_EXCHANGE", "Cross-repository record in exchange unit"
                )
            if (
                data.get("owner_kind") == "source"
                and record["table"] != "parser_profile_capabilities"
            ):
                raise CatalogError(
                    "INVALID_EXCHANGE",
                    "Source-wide facts cannot be exchanged per repository",
                )
        received = 0
        for record in records:
            serialized = canonical(record)
            digest = record_digest(record)
            previous = self.db.execute(
                "SELECT content_sha256,record_json FROM exchange_admissions WHERE record_key=?",
                (record["key"],),
            ).fetchone()
            if previous and previous[0] == digest:
                if record["table"] == "source_repositories":
                    data, unresolved = self.resolve(record)
                    if not unresolved:
                        existing = self._existing(record["table"], data)
                        if existing:
                            self.merge_source_membership(existing, data)
                continue
            if previous and record["table"] in {
                "sources",
                "repositories",
                "service_instances",
            }:
                old = json.loads(previous[1])["values"]
                identity_columns = {
                    "sources": (
                        "source_registration_uuidv4",
                        "service_instance_uuidv4",
                        "discovery_kind",
                    ),
                    "repositories": ("repository_uuidv4",),
                    "service_instances": ("service_instance_uuidv4", "service_kind"),
                }[record["table"]]
                if all(old[c] == record["values"][c] for c in identity_columns):
                    if record["table"] == "sources":
                        provenance = canonical(record["values"])
                        self.db.execute(
                            "INSERT OR IGNORE INTO exchange_source_provenance VALUES(?,?,?,?)",
                            (
                                record["values"]["source_registration_uuidv4"],
                                unit["origin_catalog_uuidv4"],
                                hashlib.sha256(provenance.encode()).digest(),
                                provenance,
                            ),
                        )
                    continue
            reason = "conflict:immutable_content" if previous else "missing_dependency"
            self.db.execute(
                "INSERT OR IGNORE INTO exchange_staging VALUES(?,?,?,?,?,?,?)",
                (
                    record["key"],
                    digest,
                    record["table"],
                    unit["repository_uuidv4"],
                    unit["origin_catalog_uuidv4"],
                    serialized,
                    reason,
                ),
            )
            received += 1
        # Two competing unadmitted variants have no evidence-based winner.
        # Keep both; sorting, arrival order and UUID magnitude cannot choose.
        competing = self.db.execute(
            "SELECT record_key FROM exchange_staging GROUP BY record_key HAVING COUNT(*)>1"
        ).fetchall()
        for (key,) in competing:
            self.db.execute(
                "UPDATE exchange_staging SET reason='conflict:competing_variants' WHERE record_key=?",
                (key,),
            )
        admitted = self.promote(unit["origin_catalog_uuidv4"])
        count = self.db.execute("SELECT COUNT(*) FROM exchange_staging").fetchone()[0]
        return {
            "received_records": received,
            "rejected_records": len(rejected),
            "admitted_records": admitted,
            "staged_records": count,
            "repository_uuidv4": unit["repository_uuidv4"],
        }

    def promote(self, origin_catalog_uuidv4):
        admitted = 0
        changed = True
        while changed:
            changed = False
            pending = list(
                self.db.execute(
                    "SELECT record_key,content_sha256,record_json,reason,repository_uuidv4,origin_catalog_uuidv4 FROM exchange_staging ORDER BY record_key,content_sha256"
                )
            )
            for (
                key,
                digest,
                serialized,
                reason,
                repository_uuidv4,
                record_origin,
            ) in pending:
                if reason.startswith(("conflict:", "invalid:")):
                    continue
                record = json.loads(serialized)
                self.db.execute("SAVEPOINT exchange_record")
                try:
                    reason = self._admit(record, record_origin, repository_uuidv4)
                    if not reason:
                        self.db.execute(
                            "DELETE FROM exchange_staging WHERE record_key=? AND content_sha256=?",
                            (key, digest),
                        )
                        admitted += 1
                        changed = True
                except CatalogError as exc:
                    self.db.execute("ROLLBACK TO exchange_record")
                    if exc.code not in {
                        "PAYLOAD_CORRUPTION",
                        "PAYLOAD_HASH_COLLISION",
                        "PAYLOAD_QUARANTINED",
                    }:
                        raise
                    reason = "conflict:" + exc.code.lower()
                    if (
                        exc.code == "PAYLOAD_CORRUPTION"
                        and record["table"] == "stored_bytes"
                    ):
                        from repo_catalog.adapters.sqlite.cas_integrity import (
                            diagnose_corruption,
                        )

                        diagnose_corruption(self.db, decode(record["values"]["sha256"]))
                except sqlite3.IntegrityError as exc:
                    self.db.execute("ROLLBACK TO exchange_record")
                    reason = "constraint:" + str(exc)
                finally:
                    self.db.execute("RELEASE exchange_record")
                if reason:
                    self.db.execute(
                        "UPDATE exchange_staging SET reason=? WHERE record_key=? AND content_sha256=?",
                        (reason, key, digest),
                    )
        self.refresh_resolution_blocks()
        return admitted

    def merge_source_membership(self, existing, incoming):
        first = [
            v
            for v in (existing["first_seen_us"], incoming["first_seen_us"])
            if v is not None
        ]
        last = [
            v
            for v in (existing["last_seen_us"], incoming["last_seen_us"])
            if v is not None
        ]
        self.db.execute(
            "UPDATE source_repositories SET first_seen_us=?,last_seen_us=? WHERE source_id=? AND repository_uuidv4=?",
            (
                min(first) if first else None,
                max(last) if last else None,
                existing["source_id"],
                existing["repository_uuidv4"],
            ),
        )

    def refresh_resolution_blocks(self):
        """Block disputed identities and their actual local FK dependency closure.

        Retained immutable rows remain inspectable. Ordinary current derivation
        cannot expose the first of two conflicting arrivals as a winner.
        """
        self.db.execute("DELETE FROM exchange_blocked_results")
        self.db.execute("DELETE FROM exchange_selection_blocks")
        blocked = set()
        pending = list(
            self.db.execute(
                "SELECT record_key,record_json,reason FROM exchange_staging"
            )
        )

        def local_record(record):
            admitted = self.db.execute(
                "SELECT table_name,local_key_json FROM exchange_admissions WHERE record_key=?",
                (record["key"],),
            ).fetchone()
            if admitted:
                key = json.loads(admitted[1])
                return self.lookup(
                    admitted[0], tuple(key), tuple(decode(v) for v in key.values())
                )
            table = record["table"]
            data = {}
            for c, v in record["values"].items():
                if isinstance(v, dict) and "$ref" in v:
                    parent = self.db.execute(
                        "SELECT table_name,local_key_json FROM exchange_admissions WHERE record_key=?",
                        (v["$ref"],),
                    ).fetchone()
                    if parent:
                        key = json.loads(parent[1])
                        row = self.lookup(
                            parent[0],
                            tuple(key),
                            tuple(decode(k) for k in key.values()),
                        )
                        if row:
                            data[c] = row[v["column"]]
                else:
                    data[c] = decode(v)
            return self._existing(table, data)

        for key, serialized, reason in pending:
            record = json.loads(serialized)
            if reason.startswith("conflict:"):
                existing = local_record(record)
                if existing is not None:
                    blocked.add(
                        (record["table"], self.local_key(record["table"], existing))
                    )
            if record["table"] in {
                "parser_profile_selection_decisions",
                "fact_selection_decisions",
            }:
                kind = (
                    "profile"
                    if record["table"] == "parser_profile_selection_decisions"
                    else "fact"
                )
                col = (
                    "selection_scope_uuidv4"
                    if kind == "profile"
                    else "fact_selection_scope_uuidv4"
                )
                reference = record["values"][col]
                scope_record = self.db.execute(
                    "SELECT record_json FROM exchange_admissions WHERE record_key=?",
                    (reference["$ref"],),
                ).fetchone()
                if scope_record is None:
                    scope_record = self.db.execute(
                        "SELECT record_json FROM exchange_staging WHERE record_key=? LIMIT 1",
                        (reference["$ref"],),
                    ).fetchone()
                if scope_record:
                    scope = local_record(json.loads(scope_record[0]))
                    if scope:
                        self.db.execute(
                            "INSERT OR IGNORE INTO exchange_selection_blocks VALUES(?,?,?)",
                            (kind, scope[col], key),
                        )
        rows = {table: self.rows(table) for table in self.columns}
        changed = True
        while changed:
            changed = False
            for table, values in rows.items():
                for row in values:
                    local = (table, self.local_key(table, row))
                    if local not in blocked:
                        for parent, child_cols, parent_cols in self.foreign[table]:
                            if parent not in rows:
                                continue
                            target = self.lookup(
                                parent, parent_cols, tuple(row[c] for c in child_cols)
                            )
                            if (
                                target is not None
                                and (parent, self.local_key(parent, target)) in blocked
                            ):
                                blocked.add(local)
                                changed = True
                                break
                    if local in blocked and row.get("parsed_result_uuidv4"):
                        result = self.lookup(
                            "parsed_results",
                            ("parsed_result_uuidv4",),
                            (row["parsed_result_uuidv4"],),
                        )
                        if result is not None:
                            result_key = (
                                "parsed_results",
                                self.local_key("parsed_results", result),
                            )
                            if result_key not in blocked:
                                blocked.add(result_key)
                                changed = True
        for table, key in blocked:
            values = json.loads(key)
            row = self.lookup(
                table, tuple(values), tuple(decode(v) for v in values.values())
            )
            if table == "parsed_results":
                self.db.execute(
                    "INSERT OR IGNORE INTO exchange_blocked_results VALUES(?)",
                    (row["parsed_result_uuidv4"],),
                )
            if table in {
                "parser_profile_selection_scopes",
                "parser_profile_selection_decisions",
                "fact_selection_scopes",
                "fact_selection_decisions",
            }:
                kind = "profile" if table.startswith("parser_profile") else "fact"
                col = (
                    "selection_scope_uuidv4"
                    if kind == "profile"
                    else "fact_selection_scope_uuidv4"
                )
                self.db.execute(
                    "INSERT OR IGNORE INTO exchange_selection_blocks VALUES(?,?,?)",
                    (kind, row[col], "blocked:" + table + ":" + key),
                )
