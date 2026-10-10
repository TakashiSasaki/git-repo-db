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
from collections import defaultdict, deque

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
    "unresolved_payloads",
    "payload_admission_staging",
    "parser_profile_selection_staging",
    "fact_selection_staging",
    "identity_relation_staging",
    "exchange_blocked_coverage_claims",
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
NATURAL = {
    "sources": ("source_registration_uuidv4",),
    "stored_bytes": ("sha256",),
    "payloads": ("representation", "sha256"),
    "text_bodies": ("sha256",),
    "git_objects": ("object_format", "oid"),
    "coverage_claims": ("coverage_scope_id", "observed_at_us", "coverage_state"),
}
LOCAL_COLUMNS = {
    "repositories": {"preferred_repository_endpoint_id"},
}
SCOPES = {"parser_profile_selection_scopes", "fact_selection_scopes", "coverage_scopes"}
CURRENT_RESOURCES = {"issue_resources", "review_resources"}
# Saved API messages are not independently exchangeable. The remaining
# historical facts and terminal proofs still require their exact input closure;
# verified Git object bytes are domain content with their own typed consumer.
ORIGINAL_RECORDS = {"fetch_occurrences", "payloads", "stored_bytes"}
DOMAIN_FACTS = {
    "change_request_observations",
    "document_observations",
    "change_request_events",
    "review_thread_observations",
    "code_observations",
    "code_commits",
    "code_file_changes",
    "repository_name_observations",
    "snapshots",
    "ref_observations",
    "commits",
    "commit_parents",
    "tree_entries",
    "tag_objects",
    "root_manifests",
    "root_manifest_entries",
    "git_text_facts",
}
ORIGINAL_PROOF_TABLES = (
    DOMAIN_FACTS
    | ORIGINAL_RECORDS
    | {
        "parsed_results",
        "parsed_result_inputs",
        "parsed_result_publications",
        "completion_markers",
        "git_acquisitions",
        "git_acquisition_publications",
        "acquisition_roots",
        "root_origins",
        "repository_object_sources",
        "git_objects",
        "git_object_payloads",
        "code_listings",
    }
)
SHA = re.compile(r"[0-9a-f]{64}\Z")


def staging_owner(table_name, reason):
    """Dispatch typed plain current candidates separately from wire envelopes.

    Both formats use the existing intake table. Table ownership identifies
    mutable resource envelopes; the current reason namespace identifies plain
    admission candidates. Portable record-key spelling has no role here.
    """
    current = table_name in CURRENT_RESOURCES
    if reason.startswith("current_state:"):
        if not current:
            raise CatalogError(
                "INVALID_EXCHANGE_STAGING", "Invalid current staging owner"
            )
        return "current_candidate"
    return "current_record" if current else "immutable_record"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_digest(record):
    # Completeness dependency manifests bind immutable evidence exactly.
    # Only mutable Source membership intervals are transport aggregates.
    content = dict(record)
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
    def __init__(self, db, *, persist_identities=True):
        self.db = db
        self.persist_identities = persist_identities
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
                if any(r[3] not in self.columns[table] for r in group):
                    # Generated discriminator columns enforce current-family
                    # parent types in SQL. Shared current admission owns those
                    # natural references; generated values are never portable
                    # writable columns.
                    continue
                self.foreign[table].append(
                    (
                        group[0][2],
                        tuple(r[3] for r in group),
                        tuple(r[4] for r in group),
                    )
                )
            if table in CURRENT_RESOURCES:
                # Natural-key owner references must remain stable when optional
                # thread/review associations are discovered or changed.
                self.foreign[table].sort(
                    key=lambda fk: fk[0] not in {"service_instances", "change_requests"}
                )
        self.key_cache = {}
        self._original_admission_keys = None
        self._original_export_keys = None

    def original_dependencies(self, record):
        """Follow typed domain-input/proof edges, excluding archive-only chains.

        Profiles, registrations, selection decisions and operational scopes do
        not justify transporting messages. In particular, authored JSON in an
        otherwise required profile cannot turn an unrelated payload into a
        required domain input.
        """
        from repo_catalog.adapters.sqlite.json_contracts import (
            JSON_REGISTRY,
            JsonContractError,
            reference_dependencies,
        )

        table = record["table"]
        if table not in ORIGINAL_PROOF_TABLES or table == "stored_bytes":
            return set()
        values = record["values"]
        # Reference validation needs authored JSON and ordinary scalar fields,
        # not resolved receiver-local IDs or a decoded original body.
        data, required = {}, set()
        for column, value in values.items():
            if isinstance(value, dict) and "$ref" in value:
                if (
                    set(value) != {"$ref", "column"}
                    or not isinstance(value["$ref"], str)
                    or not any(
                        value["$ref"].startswith(parent + ":")
                        and value["column"]
                        == parent_columns[child_columns.index(column)]
                        for parent, child_columns, parent_columns in self.foreign[table]
                        if column in child_columns
                    )
                ):
                    return None
                required.add(value["$ref"])
                data[column] = None
            else:
                try:
                    data[column] = decode(value)
                except CatalogError:
                    return None
        try:
            reference_dependencies(table, data)
        except JsonContractError:
            # Malformed authored evidence cannot authorize original retention.
            # Ordinary admission retains its existing diagnostic behavior.
            return None
        # Generic request/metadata references are validated for exchange, but
        # they are not consumers of extra saved originals. Retained input and
        # object manifests, plus exact terminal/304 fetch identities, own that
        # dependency. A request.payload annotation cannot archive another body.
        proof_data = {
            column: value
            for column, value in data.items()
            if (table, column) not in JSON_REGISTRY
            or JSON_REGISTRY[table, column].category
            in {"input-manifest", "git-roots", "git-object-manifest", "fact-manifest"}
        }
        if table == "completion_markers":
            evidence = json.loads(data["evidence"])
            proof_data["evidence"] = canonical(
                {
                    name: value
                    for name, value in evidence.items()
                    if name
                    in {
                        "fetch_occurrence_uuidv4s",
                        "fetch_occurrence_uuidv4",
                        "parsed_result_uuidv4",
                        "change_request_observation_uuidv4",
                        "current_page_collections",
                    }
                }
            )
        dependencies = reference_dependencies(table, proof_data)
        for dependency in dependencies:
            if dependency["table"] not in self.columns:
                continue
            required.add(
                self.missing_parent_key(
                    dependency["table"],
                    dependency["columns"],
                    dependency["values"],
                )
            )
        # Envelope requires lists are checked against derived proof at admission.
        # They cannot authorize retention: otherwise an unrelated fetch could be
        # attached to an otherwise valid proof by changing only its envelope.
        return required

    @staticmethod
    def original_key(table, row):
        if table == "fetch_occurrences":
            identity = {"fetch_occurrence_uuidv4": row["fetch_occurrence_uuidv4"]}
        elif table == "stored_bytes":
            identity = {"sha256": encode(row["sha256"], "sha256")}
        else:
            identity = {
                "representation": row["representation"],
                "sha256": {
                    "$ref": Graph.original_key("stored_bytes", row),
                    "column": "sha256",
                },
            }
        return table + ":" + canonical(identity)

    @staticmethod
    def original_root(record):
        table, values = record["table"], record["values"]
        if table in DOMAIN_FACTS:
            return True
        if table == "git_object_payloads":
            representation = values.get("payload_representation")
            if isinstance(representation, dict) and "$ref" in representation:
                try:
                    representation = json.loads(
                        representation["$ref"].split(":", 1)[1]
                    )["representation"]
                except (KeyError, IndexError, TypeError, ValueError):
                    return False
            return representation == "git-object-raw-v1"
        if table == "parsed_result_publications":
            try:
                manifest = json.loads(values["fact_manifest_json"])
            except (KeyError, TypeError, ValueError):
                return False
            return (
                isinstance(manifest, list)
                and bool(manifest)
                and all(
                    isinstance(item, dict)
                    and set(item) == {"table", "key"}
                    and isinstance(item["table"], str)
                    and item["table"] in DOMAIN_FACTS
                    and isinstance(item["key"], list)
                    and bool(item["key"])
                    and all(type(value) in (str, int) for value in item["key"])
                    for item in manifest
                )
            )
        if table == "completion_markers" and values.get("asserted_state") == "complete":
            try:
                evidence = json.loads(values["evidence"])
            except (KeyError, TypeError, ValueError):
                return False
            return isinstance(evidence, dict) and (
                (
                    evidence.get("terminal") is True
                    and bool(evidence.get("fetch_occurrence_uuidv4s"))
                )
                or evidence.get("status") == 304
                or evidence.get("kind") == "current-resource-pages-v1"
            )
        return False

    def required_original_keys(self, records):
        """Reach originals only from actual retained facts or terminal proofs."""
        records = list(records)
        by_key = {record["key"]: record for record in records}
        active, all_keys = [], set(by_key)
        for record in records:
            dependencies = self.original_dependencies(record)
            if (
                record.get("_original_rejected")
                or record["values"].get("owner_kind") == "source"
                or dependencies is None
            ):
                continue
            if (
                record["table"] == "git_object_payloads"
                and self.git_original_status(record, by_key) is False
            ):
                continue
            active.append((record, dependencies))
        # A known-invalid owner/descriptor cannot become an input consumer merely
        # because its domain descendants remain staged. Unknown valid parents
        # still preserve the ordinary partial-exchange path. A valid incumbent
        # with the same key remains an independent eligible descriptor.
        blocked = all_keys - {record["key"] for record, _ in active}
        while blocked:
            remaining = [item for item in active if not (item[1] & blocked)]
            if len(remaining) == len(active):
                break
            active = remaining
            blocked = all_keys - {record["key"] for record, _ in active}
        edges, pending = defaultdict(set), deque()
        for record, dependencies in active:
            edges[record["key"]].update(dependencies)
            if self.original_root(record):
                pending.append(record["key"])
        reached = set()
        while pending:
            key = pending.popleft()
            if key in reached:
                continue
            reached.add(key)
            pending.extend(edges[key] - reached)
        return reached

    def git_original_status(self, record, by_key):
        """Validate known Git input identity; missing valid parents remain pending."""
        from repo_catalog.domain.git_object import validate_git_object

        try:
            if not self.original_root(record):
                return False
            values = record["values"]
            payload_key = values["payload_sha256"]["$ref"]
            payload_identity = json.loads(payload_key.split(":", 1)[1])
            stored_key = payload_identity["sha256"]["$ref"]
            digest = decode(json.loads(stored_key.split(":", 1)[1])["sha256"])
            obj_key = values["git_object_id"]["$ref"]
            identity = json.loads(obj_key.split(":", 1)[1])
            obj = by_key.get(obj_key)
            if obj is None:
                attributes = self.lookup(
                    "git_objects",
                    ("object_format", "oid"),
                    (identity["object_format"], decode(identity["oid"])),
                )
            else:
                if obj.get("_original_rejected"):
                    return False
                attributes = {
                    column: decode(value) for column, value in obj["values"].items()
                }
            stored = by_key.get(stored_key)
            if stored is not None and "body" in stored["values"]:
                body = decode(stored["values"]["body"])
            else:
                local = self.db.execute(
                    "SELECT body FROM stored_bytes WHERE sha256=?", (digest,)
                ).fetchone()
                if local is None:
                    return None
                body = local[0]
            if attributes is None:
                # The missing row's portable key still declares its actual Git
                # format/OID. Reject bytes that cannot be that object, while a
                # matching body retains its typed missing-parent dependency.
                for object_type in ("blob", "tree", "commit", "tag"):
                    try:
                        validate_git_object(
                            identity["object_format"],
                            decode(identity["oid"]),
                            object_type,
                            len(body),
                            body,
                            digest,
                        )
                    except CatalogError:
                        continue
                    return True
                return False
            validate_git_object(
                attributes["object_format"],
                attributes["oid"],
                attributes["type"],
                attributes["size"],
                body,
                digest,
            )
        except (CatalogError, KeyError, IndexError, TypeError, ValueError):
            return False
        return True

    def local_original_context(self, repository_uuidv4=None):
        """Build dependency descriptors without encoding saved message bodies.

        A separate nonpersisting graph prevents a rejected original-only
        operation from registering portable identities as a side effect.
        """
        graph = (
            self
            if not self.persist_identities
            else Graph(self.db, persist_identities=False)
        )
        pending, seen, records = deque(), set(), []
        for table in DOMAIN_FACTS & graph.columns.keys():
            rows = (
                graph.matching(table, ("repository_uuidv4",), (repository_uuidv4,))
                if repository_uuidv4 is not None
                and "repository_uuidv4" in graph.columns[table]
                else graph.rows(table)
            )
            pending.extend((table, row) for row in rows)
        collections = (
            graph.matching(
                "fetch_collections", ("repository_uuidv4",), (repository_uuidv4,)
            )
            if repository_uuidv4 is not None
            else graph.rows("fetch_collections")
        )
        for collection in collections:
            pending.extend(
                ("completion_markers", row)
                for row in graph.matching(
                    "completion_markers",
                    ("fetch_collection_id",),
                    (collection["fetch_collection_id"],),
                )
                if row["asserted_state"] == "complete"
            )
        # Raw Git object bytes have an independent domain consumer even before
        # an interpretation has been published.
        pending.extend(
            ("git_object_payloads", row) for row in graph.rows("git_object_payloads")
        )
        while pending:
            table, row = pending.popleft()
            if (
                table not in ORIGINAL_PROOF_TABLES
                or row.get("owner_kind") == "source"
                or row.get("owner_source_registration_uuidv4")
            ):
                continue
            if row.get("parsed_result_uuidv4") and table != "parsed_results":
                result = graph.lookup(
                    "parsed_results",
                    ("parsed_result_uuidv4",),
                    (row["parsed_result_uuidv4"],),
                )
                if result and result["owner_kind"] == "source":
                    continue
            key = graph.key(table, row)
            if key in seen:
                continue
            seen.add(key)
            data = {
                column: encode(value, column)
                for column, value in row.items()
                if not (table == "stored_bytes" and column == "body")
            }
            for parent, child_columns, parent_columns in graph.foreign[table]:
                if parent not in graph.columns or any(
                    row.get(c) is None for c in child_columns
                ):
                    continue
                target = graph.lookup(
                    parent, parent_columns, tuple(row[c] for c in child_columns)
                )
                if target is None:
                    continue
                for child, column in zip(child_columns, parent_columns):
                    data[child] = {"$ref": graph.key(parent, target), "column": column}
                pending.append((parent, target))
            record = {"key": key, "table": table, "values": data}
            records.append(record)
            from repo_catalog.adapters.sqlite.json_contracts import (
                reference_dependencies,
            )

            for dependency in reference_dependencies(table, row):
                if dependency["table"] not in graph.columns:
                    continue
                target = graph.lookup(
                    dependency["table"], dependency["columns"], dependency["values"]
                )
                if target is not None:
                    pending.append((dependency["table"], target))
        return records

    def original_intake_context(self, records=(), repository_uuidv4=None):
        """Include prior domain staging so delayed required bytes can arrive."""
        context = list(self.local_original_context(repository_uuidv4))
        context.extend(
            json.loads(row[0])
            for row in self.db.execute("SELECT record_json FROM exchange_admissions")
        )
        query = "SELECT record_json,table_name,reason FROM exchange_staging"
        parameters = ()
        if repository_uuidv4 is not None:
            query += " WHERE repository_uuidv4=?"
            parameters = (repository_uuidv4,)
        for serialized, table, reason in self.db.execute(query, parameters):
            if staging_owner(table, reason) == "current_candidate":
                continue
            record = json.loads(serialized)
            try:
                self.validate_record(record)
            except CatalogError:
                record["_original_rejected"] = True
            if reason.startswith(("invalid:", "constraint:")):
                record["_original_rejected"] = True
            context.append(record)
        context.extend(records)
        if repository_uuidv4 is not None:
            by_key = {record["key"]: record for record in context}

            def owner(record, visited=None):
                visited = visited or set()
                if record["key"] in visited:
                    return None
                visited.add(record["key"])
                data = record["values"]
                for column in ("repository_uuidv4", "owner_repository_uuidv4"):
                    value = data.get(column)
                    if isinstance(value, str):
                        return value
                    if isinstance(value, dict) and "$ref" in value:
                        identity = json.loads(value["$ref"].split(":", 1)[1])
                        return identity.get("repository_uuidv4")
                for column in ("fetch_collection_id", "parsed_result_uuidv4"):
                    value = data.get(column)
                    if isinstance(value, dict) and value.get("$ref") in by_key:
                        return owner(by_key[value["$ref"]], visited)
                return None

            context = [
                dict(record, _original_rejected=True)
                if owner(record) not in (None, repository_uuidv4)
                else record
                for record in context
            ]
        return context

    def retained_git_body(self, record, records=()):
        """Recognize actual Git content, rather than an asserted representation."""
        context = self.original_intake_context(records)
        by_key = {item["key"]: item for item in context}
        for item in context:
            if item["table"] != "git_object_payloads" or item.get("_original_rejected"):
                continue
            try:
                payload_key = item["values"]["payload_sha256"]["$ref"]
                identity = json.loads(payload_key.split(":", 1)[1])
                if identity["sha256"]["$ref"] != record["key"]:
                    continue
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            # The candidate itself can be a late incoming body not yet staged.
            if self.git_original_status(item, by_key | {record["key"]: record}) is True:
                return True
        return False

    def rejected_api_original(self, record, records=()):
        """Diagnose an incumbent collision without retaining the incoming API body."""
        if record["table"] != "stored_bytes":
            return False
        digest = decode(record["values"]["sha256"])
        if not self.db.execute(
            "SELECT 1 FROM stored_bytes WHERE sha256=?", (digest,)
        ).fetchone():
            return False
        try:
            intern_stored_bytes(self.db, decode(record["values"]["body"]), digest)
        except CatalogError as error:
            if error.code not in {
                "PAYLOAD_CORRUPTION",
                "PAYLOAD_HASH_COLLISION",
                "PAYLOAD_QUARANTINED",
            }:
                raise
            if self.retained_git_body(record, records):
                return False
            if error.code == "PAYLOAD_CORRUPTION":
                from repo_catalog.adapters.sqlite.cas_integrity import (
                    diagnose_corruption,
                )

                diagnose_corruption(self.db, digest)
            return True
        return False

    def rows(self, table):
        columns = tuple(self.columns[table])
        selected = ",".join(f'"{column}"' for column in columns)
        return [
            dict(zip(columns, row))
            for row in self.db.execute(f'SELECT {selected} FROM "{table}"')
        ]

    def lookup(self, table, columns, values, *, allow_null=False):
        if table not in self.columns or (
            not allow_null and any(v is None for v in values)
        ):
            return None
        sql = " AND ".join(f'"{c}" IS ?' for c in columns)
        selected = ",".join(f'"{column}"' for column in self.columns[table])
        row = self.db.execute(
            f'SELECT {selected} FROM "{table}" WHERE {sql}', values
        ).fetchone()
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
                    if any(c in LOCAL_COLUMNS.get(table, ()) for c in child_cols):
                        continue
                    if col not in child_cols or parent not in self.columns:
                        continue
                    if any(row.get(c) is None for c in child_cols):
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
                    if table in CURRENT_RESOURCES:
                        value = {
                            "$ref": self.missing_parent_key(
                                parent, parent_cols, tuple(row[c] for c in child_cols)
                            ),
                            "column": parent_cols[child_cols.index(col)],
                        }
                        break
            values[col] = encode(value, col)
        key = table + ":" + canonical(values)
        if self.persist_identities:
            self.db.execute(
                "INSERT INTO exchange_local_identities VALUES(?,?,?)",
                (table, local, key),
            )
        self.key_cache[cache_key] = key
        return key

    def validate_git_payload(self, row):
        from repo_catalog.domain.git_object import validate_git_object

        obj = self.lookup("git_objects", ("git_object_id",), (row["git_object_id"],))
        stored = self.lookup("stored_bytes", ("sha256",), (row["payload_sha256"],))
        if obj is None or stored is None:
            raise CatalogError(
                "INVALID_EXCHANGE", "Raw Git object dependencies are unavailable"
            )
        if hashlib.sha256(stored["body"]).digest() != row["payload_sha256"]:
            raise CatalogError(
                "PAYLOAD_CORRUPTION",
                "Cannot exchange corrupt physical bytes",
                {"sha256": row["payload_sha256"].hex()},
            )
        validate_git_object(
            obj["object_format"],
            obj["oid"],
            obj["type"],
            obj["size"],
            stored["body"],
            row["payload_sha256"],
        )

    def record(self, table, row):
        from repo_catalog.adapters.sqlite.json_contracts import (
            MissingJsonDependencies,
            validate_record,
        )

        if table in ORIGINAL_RECORDS:
            required = self._original_export_keys
            if required is None:
                verifier = Graph(self.db, persist_identities=False)
                required = verifier.required_original_keys(
                    verifier.local_original_context()
                )
            if self.original_key(table, row) not in required:
                raise CatalogError(
                    "RETIRED_API_ORIGINAL_EXCHANGE",
                    "Saved messages require retained domain facts or completeness proof",
                )
        try:
            validate_record(self.db, table, row)
        except MissingJsonDependencies:
            if table not in CURRENT_RESOURCES:
                raise
        if table == "git_object_payloads":
            self.validate_git_payload(row)
        data = {c: encode(v, c) for c, v in row.items()}
        if table in CURRENT_RESOURCES:
            data.pop("last_checked_at_us", None)
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
        for parent, child_cols, parent_cols in self.foreign[table]:
            if parent not in self.columns or any(
                row.get(c) is None for c in child_cols
            ):
                continue
            if any(c in LOCAL_COLUMNS.get(table, ()) for c in child_cols):
                continue
            parent_row = self.lookup(
                parent, parent_cols, tuple(row[c] for c in child_cols)
            )
            if parent_row is None:
                if table not in CURRENT_RESOURCES:
                    raise CatalogError(
                        "INVALID_EXCHANGE", "Catalog has an unresolved foreign key"
                    )
                key = self.missing_parent_key(
                    parent, parent_cols, tuple(row[c] for c in child_cols)
                )
            else:
                key = self.key(parent, parent_row)
            for child, pcol in zip(child_cols, parent_cols):
                if child in data and not (
                    isinstance(data[child], dict) and "$ref" in data[child]
                ):
                    data[child] = {"$ref": key, "column": pcol}
        record = {"key": self.key(table, row), "table": table, "values": data}
        if table in {"completion_markers", "coverage_claims"}:
            requirements = self.proof_requirements(table, row)
            if requirements is not None:
                record["requires"] = sorted(requirements)
        return record

    def missing_parent_key(self, table, columns, values):
        """Encode a legitimate unavailable current parent without inventing it."""
        identity = dict(zip(columns, values, strict=True))
        key_columns = self.portable_columns(table)
        if not all(column in identity for column in key_columns):
            raise CatalogError("INVALID_EXCHANGE", "Parent identity is incomplete")
        portable = {}
        for column in key_columns:
            value = identity[column]
            for parent, child_columns, parent_columns in self.foreign[table]:
                if column not in child_columns or not all(
                    child in identity for child in child_columns
                ):
                    continue
                target = self.lookup(
                    parent,
                    parent_columns,
                    tuple(identity[child] for child in child_columns),
                )
                key = (
                    self.key(parent, target)
                    if target is not None
                    else self.missing_parent_key(
                        parent,
                        parent_columns,
                        tuple(identity[child] for child in child_columns),
                    )
                )
                value = {
                    "$ref": key,
                    "column": parent_columns[child_columns.index(column)],
                }
                break
            portable[column] = encode(value, column)
        return table + ":" + canonical(portable)

    def current_candidate_row(self, candidate):
        from repo_catalog.adapters.sqlite.text_bodies import intern_text_body

        row = dict(candidate)
        body = row.pop("body", None)
        row["text_body_sha256"] = (
            intern_text_body(self.db, body) if body is not None else None
        )
        row["metadata"] = canonical(row["metadata"])
        row["acquisition_scope_json"] = canonical(row.pop("acquisition_scope"))
        if "field_evidence" in row:
            row["field_evidence_json"] = canonical(row.pop("field_evidence"))
        return row

    def current_page_requirements(self, collection_id, ordinals, *, baseline=True):
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        proof = CurrentCollectionProof(self.db)
        evidence = proof.evidence(collection_id)
        if (
            not isinstance(ordinals, list)
            or any(
                type(ordinal) is not int or ordinal != i
                for i, ordinal in enumerate(ordinals)
            )
            or evidence is None
            or evidence["page_ordinals"] != ordinals
        ):
            return None
        collection = self.lookup(
            "fetch_collections", ("fetch_collection_id",), (collection_id,)
        )
        if collection is None:
            return None
        required = {self.key("fetch_collections", collection)}
        for page in proof.pages(collection_id):
            required.add(self.key("current_collection_pages", page))
        for member in proof.members(collection_id):
            if member["family"] == "issue":
                target_table = "issue_resources"
                columns = ("service_instance_uuidv4", "kind", "provider_resource_id")
            else:
                target_table = "review_resources"
                columns = (
                    "change_request_id",
                    "kind",
                    "provider_change_request_document_id",
                )
            target = self.lookup(
                target_table, columns, tuple(member[c] for c in columns)
            )
            if target is None:
                return None
            required.add(self.key(target_table, target))
        if baseline:
            inherited = self.current_baseline_requirements(collection)
            if inherited is None:
                return None
            required.update(inherited)
        return required

    def current_baseline_requirements(self, collection):
        """Follow lightweight incremental baselines without recursive history walks."""
        required, visited = set(), set()
        while True:
            scope = self.lookup(
                "resume_scopes", ("resume_scope_id",), (collection["resume_scope_id"],)
            )
            if scope is None:
                return None
            context = json.loads(scope["request_context"])
            marker_uuid = context.get("completion_marker_uuidv4")
            if not marker_uuid:
                return required
            if marker_uuid in visited:
                return None
            visited.add(marker_uuid)
            marker = self.lookup(
                "completion_markers", ("completion_marker_uuidv4",), (marker_uuid,)
            )
            if marker is None:
                return None
            previous = self.lookup(
                "fetch_collections",
                ("fetch_collection_id",),
                (marker["fetch_collection_id"],),
            )
            if previous is None or any(
                previous[column] != collection[column]
                for column in (
                    "repository_uuidv4",
                    "change_request_id",
                    "source_id",
                    "kind",
                )
            ):
                return None
            previous_scope = self.lookup(
                "resume_scopes", ("resume_scope_id",), (previous["resume_scope_id"],)
            )
            if previous_scope is None or any(
                previous_scope[column] != scope[column]
                for column in (
                    "repository_binding_id",
                    "source_id",
                    "principal_ref",
                    "api_version",
                    "parser_version",
                    "profile_version",
                    "confidence",
                )
            ):
                return None
            previous_context = json.loads(previous_scope["request_context"])
            fixed_context = {
                key: value
                for key, value in context.items()
                if key != "completion_marker_uuidv4"
            }
            old_fixed_context = {
                key: value
                for key, value in previous_context.items()
                if key != "completion_marker_uuidv4"
            }
            if (
                not isinstance(context.get("incremental_endpoint"), str)
                or fixed_context != old_fixed_context
            ):
                return None
            if {
                (page["parser_module"], page["parser_version"])
                for page in self.matching(
                    "current_collection_pages",
                    ("fetch_collection_id",),
                    (collection["fetch_collection_id"],),
                )
            } != {
                (page["parser_module"], page["parser_version"])
                for page in self.matching(
                    "current_collection_pages",
                    ("fetch_collection_id",),
                    (previous["fetch_collection_id"],),
                )
            }:
                return None
            from repo_catalog.adapters.sqlite.current_collections import (
                CurrentCollectionProof,
            )

            proof = CurrentCollectionProof(self.db)
            if not proof.is_complete_marker(marker):
                return None
            evidence = json.loads(marker["evidence"])
            dependencies = self.current_page_requirements(
                previous["fetch_collection_id"],
                evidence["page_ordinals"],
                baseline=False,
            )
            if dependencies is None:
                return None
            required.add(self.key("completion_markers", marker))
            required.update(dependencies)
            collection = previous

    def matching(self, table, columns, values):
        if table not in self.columns:
            return []
        where = " AND ".join(f'"{c}" IS ?' for c in columns)
        selected = ",".join(f'"{column}"' for column in self.columns[table])
        return [
            dict(zip(self.columns[table], row))
            for row in self.db.execute(
                f'SELECT {selected} FROM "{table}" WHERE {where}', values
            )
        ]

    def current_parents(self, table, row):
        """Resolve generated SQL discriminator relationships by natural key."""
        if table == "issue_resources" and row.get("parent_provider_resource_id"):
            return [
                (
                    table,
                    self.lookup(
                        table,
                        ("service_instance_uuidv4", "kind", "provider_resource_id"),
                        (
                            row["service_instance_uuidv4"],
                            "issue",
                            row["parent_provider_resource_id"],
                        ),
                    ),
                )
            ]
        if table == "review_resources":
            return [
                (
                    table,
                    self.lookup(
                        table,
                        (
                            "change_request_id",
                            "kind",
                            "provider_change_request_document_id",
                        ),
                        (row["change_request_id"], kind, row[column]),
                    ),
                )
                for column, kind in (
                    ("review_provider_resource_id", "review"),
                    ("in_reply_to_provider_resource_id", "review-comment"),
                )
                if row.get(column)
            ]
        return []

    def code_proof(self, result_uuid, repository_uuid, change_request_id):
        """Exact published code interpretation, sealed listings and Git roles."""
        result = self.lookup(
            "parsed_results", ("parsed_result_uuidv4",), (result_uuid,)
        )
        publication = self.lookup(
            "parsed_result_publications", ("parsed_result_uuidv4",), (result_uuid,)
        )
        if (
            result is None
            or publication is None
            or result["repository_uuidv4"] != repository_uuid
        ):
            return None
        observations = self.matching(
            "code_observations",
            ("parsed_result_uuidv4", "change_request_id", "state"),
            (result_uuid, change_request_id, "complete"),
        )
        if len(observations) != 1:
            return None
        observation = observations[0]
        details = json.loads(observation["details"])
        roles = details.get("expected_roles")
        if (
            details.get("api_head_base_stable") is not True
            or details.get("code_inputs_complete") is not True
            or details.get("missing_roles")
            or not isinstance(roles, dict)
            or not {"head", "base"} <= roles.keys()
        ):
            return None
        required = {
            self.key("parsed_result_publications", publication),
            self.key("code_observations", observation),
        }
        collections, acquisitions = set(), set()
        inputs = self.matching(
            "parsed_result_inputs", ("parsed_result_uuidv4",), (result_uuid,)
        )
        input_acquisitions = {
            item["git_acquisition_id"] for item in inputs if item["git_acquisition_id"]
        }
        input_fetches = {
            item["fetch_occurrence_uuidv4"]
            for item in inputs
            if item["fetch_occurrence_uuidv4"]
        }
        for listing_id, listing_kind in (
            (observation["commit_code_listing_id"], "commits"),
            (observation["file_code_listing_id"], "files"),
        ):
            listing = self.lookup("code_listings", ("code_listing_id",), (listing_id,))
            if (
                listing is None
                or listing["change_request_id"] != change_request_id
                or listing["kind"] != listing_kind
            ):
                return None
            collections.add(listing["fetch_collection_id"])
            required.add(self.key("code_listings", listing))
            fetches = self.matching(
                "fetch_occurrences",
                ("fetch_collection_id",),
                (listing["fetch_collection_id"],),
            )
            if (
                not fetches
                or not {item["fetch_occurrence_uuidv4"] for item in fetches}
                <= input_fetches
            ):
                return None
        links = self.matching(
            "code_acquisitions",
            ("code_observation_id",),
            (observation["code_observation_id"],),
        )
        if set(roles) != {link["role"] for link in links}:
            return None
        for link in links:
            root = self.lookup(
                "acquisition_roots",
                ("acquisition_root_id",),
                (link["acquisition_root_id"],),
            )
            if (
                root is None
                or root["published"] != 1
                or root["repository_uuidv4"] != repository_uuid
                or root["git_acquisition_id"] not in input_acquisitions
                or link["object_format"] != root["object_format"]
                or link["oid"] != root["oid"]
                or roles[link["role"]] != link["oid"].hex()
            ):
                return None
            if link["role"] in {"head", "base"} and (
                link["object_format"] != observation["object_format"]
                or link["oid"] != observation[link["role"] + "_oid"]
            ):
                return None
            acquisition_pub = self.lookup(
                "git_acquisition_publications",
                ("git_acquisition_id",),
                (root["git_acquisition_id"],),
            )
            if acquisition_pub is None:
                return None
            acquisitions.add(root["git_acquisition_id"])
            required.update(
                {
                    self.key("code_acquisitions", link),
                    self.key("acquisition_roots", root),
                    self.key("git_acquisition_publications", acquisition_pub),
                }
            )
        return {
            "requires": required,
            "collections": collections,
            "acquisitions": acquisitions,
            "observation": observation,
        }

    def aggregate_proof(self, scope, details, collection_rows):
        """A repository PR assessment proves a complete listing and every item."""
        requests = details.get("change_request_ids")
        if (
            not isinstance(requests, list)
            or len(set(requests)) != len(requests)
            or scope["change_request_id"] is not None
        ):
            return None
        listings = [
            item
            for item in collection_rows
            if item["kind"] == "pr-list" and item["change_request_id"] is None
        ]
        if not listings:
            return None
        required, listed_requests = set(), set()
        for listing in listings:
            for fetch in self.matching(
                "fetch_occurrences",
                ("fetch_collection_id",),
                (listing["fetch_collection_id"],),
            ):
                raw = self.lookup(
                    "stored_bytes", ("sha256",), (fetch["payload_sha256"],)
                )
                if raw is None:
                    return None
                try:
                    page = json.loads(raw["body"])
                except (ValueError, UnicodeError):
                    return None
                if not isinstance(page, list):
                    return None
                for provider_record in page:
                    if (
                        not isinstance(provider_record, dict)
                        or type(provider_record.get("number")) is not int
                    ):
                        return None
                    observations = [
                        item
                        for item in self.matching(
                            "change_request_observations",
                            ("origin_fetch_occurrence_id",),
                            (fetch["fetch_occurrence_id"],),
                        )
                        if json.loads(item["payload"]) == provider_record
                    ]
                    if len(observations) != 1:
                        return None
                    observation = observations[0]
                    publication = self.lookup(
                        "parsed_result_publications",
                        ("parsed_result_uuidv4",),
                        (observation["parsed_result_uuidv4"],),
                    )
                    if publication is None:
                        return None
                    listed_requests.add(observation["change_request_id"])
                    required.update(
                        {
                            self.key("change_request_observations", observation),
                            self.key("parsed_result_publications", publication),
                        }
                    )
        if not listed_requests <= set(requests):
            return None
        kinds = defaultdict(set)
        for collection in collection_rows:
            if collection["change_request_id"] is not None:
                kinds[collection["change_request_id"]].add(collection["kind"])
        required_kinds = {
            "pr-detail",
            "issue-comment",
            "review",
            "review-comment",
            "threads",
        }
        if scope["kind"] == "pr":
            required_kinds |= {"timeline", "pr-commits", "pr-files"}
        code_results = details.get("parsed_result_uuidv4s", [])
        if scope["kind"] == "pr" and (
            len(code_results) != len(requests)
            or len(set(code_results)) != len(code_results)
        ):
            return None
        if scope["kind"] == "pr-documents" and code_results:
            return None
        code_by_request = defaultdict(list)
        for result_uuid in code_results:
            for observation in self.matching(
                "code_observations",
                ("parsed_result_uuidv4", "state"),
                (result_uuid, "complete"),
            ):
                code_by_request[observation["change_request_id"]].append(result_uuid)
        for request_id in requests:
            request = self.lookup(
                "change_requests", ("change_request_id",), (request_id,)
            )
            if (
                request is None
                or request["repository_uuidv4"] != scope["repository_uuidv4"]
                or not required_kinds <= kinds[request_id]
            ):
                return None
            required.add(self.key("change_requests", request))
            if scope["kind"] == "pr":
                if len(code_by_request[request_id]) != 1:
                    return None
                code = self.code_proof(
                    code_by_request[request_id][0],
                    scope["repository_uuidv4"],
                    request_id,
                )
                if code is None or not code["collections"] <= {
                    item["fetch_collection_id"] for item in collection_rows
                }:
                    return None
                required.update(code["requires"])
        return required

    def proof_requirements(self, table, row):
        """Derive proof from immutable portable evidence, never envelope hints.

        A complete collection marker seals its exact acquisition UUID set. A
        coverage claim identifies exact collection/Git roots in its advisory
        JSON; absence of that evidence keeps the claim local. Extra repository
        records and later unrelated acquisitions cannot change this proof.
        """
        required = set()

        def require(target_table, columns, values):
            target = self.lookup(target_table, columns, values)
            if target is None:
                return None
            required.add(self.key(target_table, target))
            return target

        if table == "completion_markers":
            if row["asserted_state"] != "complete":
                return set()
            evidence = json.loads(row["evidence"])
            if evidence.get("kind") == "current-resource-pages-v1":
                from repo_catalog.adapters.sqlite.current_collections import (
                    CurrentCollectionProof,
                )

                proof = CurrentCollectionProof(self.db)
                if not proof.is_complete_marker(row):
                    return None
                # Identity dependencies certify independently usable domain
                # members. Their changing bodies are never immutable output
                # dependencies; the sealed receipt retains the observed digest.
                return self.current_page_requirements(
                    row["fetch_collection_id"], evidence["page_ordinals"]
                )
            manifest = evidence.get("fetch_occurrence_uuidv4s")
            validation = evidence.get("status") == 304
            if (
                not isinstance(manifest, list)
                or (not manifest and not validation)
                or len(set(manifest)) != len(manifest)
            ):
                return None
            collection_ids = evidence.get(
                "fetch_collection_ids", [row["fetch_collection_id"]]
            )
            if row["fetch_collection_id"] not in collection_ids:
                return None
            root_collection = self.lookup(
                "fetch_collections",
                ("fetch_collection_id",),
                (row["fetch_collection_id"],),
            )
            if root_collection is None:
                return None
            root_scope = self.lookup(
                "resume_scopes",
                ("resume_scope_id",),
                (root_collection["resume_scope_id"],),
            )
            for collection_id in collection_ids:
                collection = require(
                    "fetch_collections", ("fetch_collection_id",), (collection_id,)
                )
                if (
                    collection is None
                    or collection["repository_uuidv4"]
                    != root_collection["repository_uuidv4"]
                    or collection["change_request_id"]
                    != root_collection["change_request_id"]
                    or collection["source_id"] != root_collection["source_id"]
                ):
                    return None
                if collection_id != row["fetch_collection_id"]:
                    context = self.lookup(
                        "resume_scopes",
                        ("resume_scope_id",),
                        (collection["resume_scope_id"],),
                    )
                    if (
                        collection["kind"] != "thread-comments"
                        or context is None
                        or root_scope is None
                        or json.loads(context["request_context"]).get(
                            "parent_fetch_collection_id"
                        )
                        != row["fetch_collection_id"]
                        or any(
                            context[column] != root_scope[column]
                            for column in (
                                "repository_binding_id",
                                "source_id",
                                "principal_ref",
                                "api_version",
                                "parser_version",
                                "profile_version",
                                "confidence",
                            )
                        )
                        or json.loads(context["request_context"]).get("permissions")
                        != json.loads(root_scope["request_context"]).get("permissions")
                    ):
                        return None
            actual_rows = [
                item
                for collection_id in collection_ids
                for item in self.matching(
                    "fetch_occurrences", ("fetch_collection_id",), (collection_id,)
                )
            ]
            if set(manifest) != {
                item["fetch_occurrence_uuidv4"] for item in actual_rows
            }:
                return None
            observations = []
            page_manifest = evidence.get("current_page_collections", [])
            if not isinstance(page_manifest, list) or any(
                not isinstance(item, dict)
                or set(item) != {"fetch_collection_id", "page_ordinals"}
                for item in page_manifest
            ):
                return None
            page_ids = [item["fetch_collection_id"] for item in page_manifest]
            if len(page_ids) != len(set(page_ids)) or set(page_ids) != {
                collection_id
                for collection_id in collection_ids
                if self.matching(
                    "current_collection_pages",
                    ("fetch_collection_id",),
                    (collection_id,),
                )
            }:
                return None
            for item in page_manifest:
                page_proof = self.current_page_requirements(
                    item["fetch_collection_id"], item["page_ordinals"]
                )
                if page_proof is None:
                    return None
                required.update(page_proof)
                observations.extend(
                    page["observed_at_us"]
                    for page in self.matching(
                        "current_collection_pages",
                        ("fetch_collection_id",),
                        (item["fetch_collection_id"],),
                    )
                )
            for occurrence_uuid in manifest:
                fetch = require(
                    "fetch_occurrences",
                    ("fetch_occurrence_uuidv4",),
                    (occurrence_uuid,),
                )
                if fetch is None or fetch["fetch_collection_id"] not in collection_ids:
                    return None
                observations.append(fetch["observed_at_us"])
            if not validation and (
                not any(t is not None for t in observations)
                or row["observed_at_us"]
                != max(t for t in observations if t is not None)
            ):
                return None
            if not validation and evidence.get("terminal") is not True:
                return None
            observation_uuid = evidence.get("change_request_observation_uuidv4")
            if observation_uuid:
                observation = require(
                    "change_request_observations",
                    ("change_request_observation_uuidv4",),
                    (observation_uuid,),
                )
                if observation is None:
                    return None
                if (
                    require(
                        "parsed_result_publications",
                        ("parsed_result_uuidv4",),
                        (observation["parsed_result_uuidv4"],),
                    )
                    is None
                ):
                    return None
            if validation:
                if not observation_uuid or row["observed_at_us"] is None:
                    return None
                original_fetch = require(
                    "fetch_occurrences",
                    ("fetch_occurrence_uuidv4",),
                    (evidence.get("fetch_occurrence_uuidv4"),),
                )
                if (
                    original_fetch is None
                    or original_fetch["repository_uuidv4"]
                    != root_collection["repository_uuidv4"]
                    or observation["repository_uuidv4"]
                    != root_collection["repository_uuidv4"]
                    or observation["change_request_id"]
                    != root_collection["change_request_id"]
                    or evidence.get("parsed_result_uuidv4")
                    != observation["parsed_result_uuidv4"]
                    or observation["origin_fetch_occurrence_id"]
                    != original_fetch["fetch_occurrence_id"]
                    or evidence.get("payload")
                    != {
                        "representation": original_fetch["payload_representation"],
                        "sha256": original_fetch["payload_sha256"].hex(),
                    }
                ):
                    return None
            return required
        if row["coverage_state"] != "complete":
            return set()
        scope = self.lookup(
            "coverage_scopes", ("coverage_scope_id",), (row["coverage_scope_id"],)
        )
        details = json.loads(row["details_json"] or "{}")
        collections = details.get("fetch_collection_ids", [])
        acquisitions = details.get("git_acquisition_ids", [])
        if details.get("git_acquisition_id"):
            acquisitions = [*acquisitions, details["git_acquisition_id"]]
        if not collections and not acquisitions:
            return None
        times = []
        marker_uuids = details.get("completion_marker_uuidv4s", [])
        if collections and not marker_uuids:
            return None
        proof_markers = []
        for marker_uuid in marker_uuids:
            marker = require(
                "completion_markers", ("completion_marker_uuidv4",), (marker_uuid,)
            )
            if marker is None or marker["asserted_state"] != "complete":
                return None
            proof = self.proof_requirements("completion_markers", marker)
            if not proof:
                return None
            required.update(proof)
            proof_markers.append(marker)
        if {marker["fetch_collection_id"] for marker in proof_markers} != set(
            collections
        ):
            return None
        git_kinds = {"structure", "digests", "heads-text", "refs"}
        http_kinds = {
            "issue": {"issue", "ordinary-issue-comment"},
            "issue-comment": {"issue-comment", "ordinary-issue-comment"},
            "comment": {"comments", "comment"},
            "review": {"review"},
            "review-comment": {"review-comment", "thread-comments"},
            "events": {"timeline"},
            "timeline": {"timeline"},
            "threads": {"threads", "thread-comments"},
            "pr-detail": {"pr-detail"},
            "pr-list": {"pr-list"},
            "pr-commits": {"pr-commits"},
            "pr-files": {"pr-files"},
            "pr-code-check": {"pr-code-check"},
            "pr-code": {
                "pr-detail",
                "pr-code-check",
                "pr-commits",
                "pr-files",
                "review",
                "threads",
                "thread-comments",
            },
        }
        collection_rows = []
        for collection_id in collections:
            collection = require(
                "fetch_collections", ("fetch_collection_id",), (collection_id,)
            )
            if (
                collection is None
                or collection["repository_uuidv4"] != scope["repository_uuidv4"]
                or (
                    scope["change_request_id"] is not None
                    and collection["change_request_id"] != scope["change_request_id"]
                )
            ):
                return None
            collection_rows.append(collection)
            kind = scope["kind"]
            if kind in git_kinds:
                return None
            if kind == "pr-documents":
                if collection["kind"] in {
                    "pr-commits",
                    "pr-files",
                    "timeline",
                }:
                    return None
            elif kind not in {"pr", "pr-code"} and collection[
                "kind"
            ] not in http_kinds.get(kind, {kind}):
                return None
        for marker in proof_markers:
            evidence = json.loads(marker["evidence"])
            if evidence.get("status") == 304:
                fetch = self.lookup(
                    "fetch_occurrences",
                    ("fetch_occurrence_uuidv4",),
                    (evidence["fetch_occurrence_uuidv4"],),
                )
                times.append(fetch["observed_at_us"])
            else:
                times.append(marker["observed_at_us"])
        for acquisition_id in acquisitions:
            acquisition = require(
                "git_acquisitions", ("git_acquisition_id",), (acquisition_id,)
            )
            if (
                acquisition is None
                or acquisition["repository_uuidv4"] != scope["repository_uuidv4"]
            ):
                return None
            if scope["kind"] in git_kinds:
                times.append(acquisition["observed_at_us"])

                if (
                    acquisition["kind"] != "git"
                    or scope["change_request_id"] is not None
                    or not details.get("parsed_result_uuidv4")
                ):
                    return None
                snapshots = self.matching(
                    "snapshots",
                    ("git_acquisition_id", "parsed_result_uuidv4", "published"),
                    (acquisition_id, details["parsed_result_uuidv4"], 1),
                )
                if not snapshots:
                    return None
                for snapshot in snapshots:
                    required.add(self.key("snapshots", snapshot))
            elif scope["kind"] not in {"pr", "pr-code"}:
                return None
        result_uuid = details.get("parsed_result_uuidv4")
        if result_uuid:
            publication = require(
                "parsed_result_publications", ("parsed_result_uuidv4",), (result_uuid,)
            )
            result = self.lookup(
                "parsed_results", ("parsed_result_uuidv4",), (result_uuid,)
            )
            if (
                publication is None
                or result is None
                or result["repository_uuidv4"] != scope["repository_uuidv4"]
            ):
                return None
            result_inputs = self.matching(
                "parsed_result_inputs", ("parsed_result_uuidv4",), (result_uuid,)
            )
            if acquisitions and not set(acquisitions) <= {
                item["git_acquisition_id"] for item in result_inputs
            }:
                return None
        if scope["kind"] == "pr-code":
            if not result_uuid or scope["change_request_id"] is None:
                return None
            code = self.code_proof(
                result_uuid, scope["repository_uuidv4"], scope["change_request_id"]
            )
            if (
                code is None
                or not code["collections"] <= set(collections)
                or code["acquisitions"] != set(acquisitions)
            ):
                return None
            required.update(code["requires"])
        if scope["kind"] in {"pr", "pr-documents"}:
            aggregate = self.aggregate_proof(scope, details, collection_rows)
            if aggregate is None:
                return None
            required.update(aggregate)
        if (
            not times
            or any(t is None for t in times)
            or max(times) != row["observed_at_us"]
        ):
            return None
        return required

    def export(
        self,
        repository_uuidv4,
        *,
        fetch_occurrence_uuidv4s=None,
        fetch_collection_id=None,
    ):
        verifier = Graph(self.db, persist_identities=False)
        previous = self._original_export_keys
        self._original_export_keys = verifier.required_original_keys(
            verifier.local_original_context(repository_uuidv4)
        )
        try:
            return self._export(
                repository_uuidv4,
                fetch_occurrence_uuidv4s=fetch_occurrence_uuidv4s,
                fetch_collection_id=fetch_collection_id,
            )
        finally:
            self._original_export_keys = previous

    def _export(
        self,
        repository_uuidv4,
        *,
        fetch_occurrence_uuidv4s=None,
        fetch_collection_id=None,
    ):
        """Export a repository or an explicit acquisition set and its ancestors.

        Collection IDs select local catalog rows; fetch UUIDs are permanent
        portable identities. Only result-owned membership and explicit decision
        DAGs expand downwards. Shared repository/document/collection identities
        never pull sibling acquisition history into a selective unit.
        """
        from repo_catalog.adapters.sqlite.json_contracts import reference_dependencies

        partial = (
            fetch_occurrence_uuidv4s is not None or fetch_collection_id is not None
        )
        included, selected, queue = set(), {}, deque()
        current_alternatives = []

        def add(table, row):
            if row is None or table not in self.columns:
                return False
            if table in ORIGINAL_RECORDS and self._original_export_keys is not None:
                if self.original_key(table, row) not in self._original_export_keys:
                    return False
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
                result = self.lookup(
                    "parsed_results",
                    ("parsed_result_uuidv4",),
                    (row["parsed_result_uuidv4"],),
                )
                if result and result["owner_kind"] == "source":
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
            queue.append((table, row))
            return True

        repository = self.lookup(
            "repositories", ("repository_uuidv4",), (repository_uuidv4,)
        )
        if repository is None:
            raise CatalogError("NOT_FOUND", "Repository UUID is not registered")
        add("repositories", repository)
        selected_fetches = set()
        collection = None
        if fetch_collection_id is not None:
            collection = self.lookup(
                "fetch_collections", ("fetch_collection_id",), (fetch_collection_id,)
            )
            if (
                collection is None
                or collection["repository_uuidv4"] != repository_uuidv4
            ):
                raise CatalogError(
                    "NOT_FOUND", "Collection is not owned by the selected repository"
                )
            add("fetch_collections", collection)
        if partial:
            identifiers = fetch_occurrence_uuidv4s
            if identifiers is None:
                identifiers = [
                    row["fetch_occurrence_uuidv4"]
                    for row in self.matching(
                        "fetch_occurrences",
                        ("fetch_collection_id",),
                        (fetch_collection_id,),
                    )
                ]
            if not identifiers and collection is None:
                raise CatalogError(
                    "INVALID_EXCHANGE_SELECTION", "Fetch selection must not be empty"
                )
            for identifier in sorted(set(identifiers)):
                fetch = self.lookup(
                    "fetch_occurrences", ("fetch_occurrence_uuidv4",), (identifier,)
                )
                if (
                    fetch is None
                    or fetch["repository_uuidv4"] != repository_uuidv4
                    or (
                        collection
                        and fetch["fetch_collection_id"] != fetch_collection_id
                    )
                ):
                    raise CatalogError(
                        "NOT_FOUND",
                        "Fetch is not owned by the selected repository/collection",
                    )
                fetch_key = "fetch_occurrences:" + canonical(
                    {"fetch_occurrence_uuidv4": identifier}
                )
                if fetch_key not in self._original_export_keys:
                    if fetch_occurrence_uuidv4s is not None:
                        raise CatalogError(
                            "RETIRED_API_ORIGINAL_EXCHANGE",
                            "Fetch selection requires retained domain facts or completeness proof",
                        )
                    continue
                selected_fetches.add(identifier)
                add("fetch_occurrences", fetch)
        else:
            for table in self.columns:
                if "repository_uuidv4" in self.columns[table]:
                    for row in self.matching(
                        table, ("repository_uuidv4",), (repository_uuidv4,)
                    ):
                        add(table, row)

        def expand():
            while queue:
                table, row = queue.popleft()
                for parent, target in self.current_parents(table, row):
                    add(parent, target)
                # Real foreign keys and registered embedded references close
                # upwards. Selection decisions may retain unavailable results,
                # preserving an unresolved scope instead of pulling other fetches.
                for parent, child_cols, parent_cols in self.foreign[table]:
                    if parent not in self.columns or any(
                        c in LOCAL_COLUMNS.get(table, ()) for c in child_cols
                    ):
                        continue
                    target = self.lookup(
                        parent, parent_cols, tuple(row[c] for c in child_cols)
                    )
                    if (
                        partial
                        and table == "fact_selection_decisions"
                        and parent in {"parsed_result_publications", "parsed_results"}
                        and target
                        and (
                            "parsed_results",
                            canonical(
                                {"parsed_result_uuidv4": target["parsed_result_uuidv4"]}
                            ),
                        )
                        not in included
                    ):
                        continue
                    add(parent, target)
                for dependency in reference_dependencies(table, row):
                    if partial and table == "coverage_claims":
                        continue
                    add(
                        dependency["table"],
                        self.lookup(
                            dependency["table"],
                            dependency["columns"],
                            dependency["values"],
                        ),
                    )
                # Explicit child membership, not arbitrary descendants of shared
                # owners. Queries are keyed by selected parents, avoiding scans
                # through unrelated repository histories.
                for child, foreign in self.foreign.items():
                    for parent, child_cols, parent_cols in foreign:
                        if parent != table:
                            continue
                        permitted = (
                            table == "parsed_results"
                            and "parsed_result_uuidv4" in child_cols
                            or table == "fetch_occurrences"
                            and child == "parsed_result_inputs"
                            or table == "git_acquisitions"
                            and child
                            in {
                                "acquisition_roots",
                                "repository_object_sources",
                                "git_acquisition_publications",
                                "parsed_result_inputs",
                            }
                            or table == "acquisition_roots"
                            and child == "root_origins"
                            or table == "git_objects"
                            and child == "git_object_payloads"
                            or table == "contents"
                            and child == "content_digests"
                            or table == "parser_profiles"
                            and child
                            in {
                                "parser_profile_capabilities",
                                "parser_profile_verifications",
                            }
                            or table == "parser_profile_verifications"
                            and child == "parser_profile_verification_invalidations"
                            or table
                            in {
                                "parser_profile_selection_decisions",
                                "fact_selection_decisions",
                            }
                            and child.endswith(("_predecessors", "_publications"))
                        )
                        if not partial and table not in GLOBAL:
                            permitted = True
                        if permitted:
                            for member in self.matching(
                                child, child_cols, tuple(row[c] for c in parent_cols)
                            ):
                                add(child, member)
                if partial and table == "parsed_results":
                    for decision in self.matching(
                        "fact_selection_decisions",
                        ("parsed_result_uuidv4",),
                        (row["parsed_result_uuidv4"],),
                    ):
                        scope_id = decision["fact_selection_scope_uuidv4"]
                        for member in self.matching(
                            "fact_selection_decisions",
                            ("fact_selection_scope_uuidv4",),
                            (scope_id,),
                        ):
                            add("fact_selection_decisions", member)
                    for decision in self.matching(
                        "parser_profile_selection_decisions",
                        ("parser_profile_uuidv4",),
                        (row["parser_profile_uuidv4"],),
                    ):
                        for member in self.matching(
                            "parser_profile_selection_decisions",
                            ("selection_scope_uuidv4",),
                            (decision["selection_scope_uuidv4"],),
                        ):
                            add("parser_profile_selection_decisions", member)
                if table == "fetch_collections" and row.get("source_id"):
                    add(
                        "source_repositories",
                        self.lookup(
                            "source_repositories",
                            ("source_id", "repository_uuidv4"),
                            (row["source_id"], repository_uuidv4),
                        ),
                    )

                # Current-resource collection receipts select present domain
                # state by typed identity, without traversing archived messages.
                if table == "fetch_collections" and (
                    not partial or row["fetch_collection_id"] == fetch_collection_id
                ):
                    for page in self.matching(
                        "current_collection_pages",
                        ("fetch_collection_id",),
                        (row["fetch_collection_id"],),
                    ):
                        add("current_collection_pages", page)
                if table == "current_collection_pages":
                    for member in json.loads(row["members"]):
                        if member["family"] == "issue":
                            target_table = "issue_resources"
                            columns = (
                                "service_instance_uuidv4",
                                "kind",
                                "provider_resource_id",
                            )
                        else:
                            target_table = "review_resources"
                            columns = (
                                "change_request_id",
                                "kind",
                                "provider_change_request_document_id",
                            )
                        add(
                            target_table,
                            self.lookup(
                                target_table,
                                columns,
                                tuple(member[c] for c in columns),
                            ),
                        )
                if table == "completion_markers":
                    evidence = json.loads(row["evidence"])
                    current_ids = [
                        item["fetch_collection_id"]
                        for item in evidence.get("current_page_collections", [])
                    ]
                    if evidence.get("kind") == "current-resource-pages-v1":
                        current_ids.append(row["fetch_collection_id"])
                    for current_id in current_ids:
                        for page in self.matching(
                            "current_collection_pages",
                            ("fetch_collection_id",),
                            (current_id,),
                        ):
                            add("current_collection_pages", page)

        expand()
        if CURRENT_RESOURCES <= self.columns.keys():
            from repo_catalog.adapters.sqlite.current_resources import CurrentResources

            # Carry bounded unresolved alternatives alongside the incumbent.
            # An incumbent whose latest value is disputed cannot turn into an
            # undisputed winner merely by crossing the exchange boundary.
            selected_current = {
                (table, local)
                for table, local in selected
                if table in CURRENT_RESOURCES
            }
            seen = set()
            for table, candidate, _ in CurrentResources(self.db).export_candidates(
                repository_uuidv4
            ):
                row = self.current_candidate_row(candidate)
                if (
                    partial
                    and (table, self.local_key(table, row)) not in selected_current
                ):
                    continue
                record = self.record(table, row)
                digest = record_digest(record)
                if digest in seen:
                    continue
                seen.add(digest)
                current_alternatives.append(record)
                # Close required domain bodies and owners, including a legitimate
                # unavailable parent reference which remains staged on receipt.
                for parent, child_cols, parent_cols in self.foreign[table]:
                    if not all(row.get(c) is not None for c in child_cols):
                        continue
                    add(
                        parent,
                        self.lookup(
                            parent, parent_cols, tuple(row[c] for c in child_cols)
                        ),
                    )
                for parent, target in self.current_parents(table, row):
                    add(parent, target)
                for dependency in reference_dependencies(table, row):
                    add(
                        dependency["table"],
                        self.lookup(
                            dependency["table"],
                            dependency["columns"],
                            dependency["values"],
                        ),
                    )
            expand()
        if partial:
            included_fetches = {
                row["fetch_occurrence_uuidv4"]
                for (table, _), row in selected.items()
                if table == "fetch_occurrences"
            }
            collection_ids = {
                row["fetch_collection_id"]
                for (table, _), row in selected.items()
                if table == "fetch_collections"
            }
            for collection_id in collection_ids:
                for marker in self.matching(
                    "completion_markers", ("fetch_collection_id",), (collection_id,)
                ):
                    evidence = json.loads(marker["evidence"])
                    manifest = evidence.get("fetch_occurrence_uuidv4s", [])
                    if (
                        (
                            manifest
                            or evidence.get("status") == 304
                            or evidence.get("kind") == "current-resource-pages-v1"
                        )
                        and set(manifest) <= included_fetches
                        and self.proof_requirements("completion_markers", marker)
                    ):
                        add("completion_markers", marker)
            expand()
            for scope in self.matching(
                "coverage_scopes", ("repository_uuidv4",), (repository_uuidv4,)
            ):
                for claim in self.matching(
                    "coverage_claims",
                    ("coverage_scope_id",),
                    (scope["coverage_scope_id"],),
                ):
                    requirements = self.proof_requirements("coverage_claims", claim)
                    if (
                        claim["coverage_state"] == "complete"
                        and requirements
                        and requirements
                        <= {
                            self.key(table, row) for (table, _), row in selected.items()
                        }
                    ):
                        add("coverage_claims", claim)
            expand()
        records = []
        for (table, _), row in selected.items():
            if (
                table == "completion_markers"
                and row["asserted_state"] == "complete"
                and self.proof_requirements(table, row) is None
            ):
                continue
            if (
                table == "coverage_claims"
                and row["coverage_state"] == "complete"
                and self.proof_requirements(table, row) is None
            ):
                continue
            records.append(self.record(table, row))
        ordinary_current_digests = {
            record_digest(record)
            for record in records
            if record["table"] in CURRENT_RESOURCES
        }
        records.extend(
            record
            for record in current_alternatives
            if record_digest(record) not in ordinary_current_digests
        )
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
                if self.db.execute(
                    "SELECT 1 FROM payload_quarantine WHERE sha256=?", (digest,)
                ).fetchone():
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
        if table in CURRENT_RESOURCES:
            columns.discard("last_checked_at_us")
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
        if table in CURRENT_RESOURCES and isinstance(data, dict):
            required = {
                *self.keys[table],
                "repository_uuidv4",
                "repository_binding_id",
                "service_instance_uuidv4",
                "text_body_sha256",
                "observed_at_us",
                "parsed_at_us",
                "parser_module",
                "parser_version",
                "metadata",
                "acquisition_scope_json",
            }
            valid_columns = required <= data.keys() <= self.expected_columns(table)
        else:
            valid_columns = (
                table in self.columns
                and isinstance(data, dict)
                and set(data) == self.expected_columns(table)
            )
        if not valid_columns:
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
                    # Current resource keys name mutable identities. Their
                    # portable mapping is retained independently of immutable
                    # admission receipts, which must never seal an edit.
                    row = self.db.execute(
                        "SELECT table_name,local_key_json FROM exchange_local_identities WHERE record_key=? AND table_name IN ('issue_resources','review_resources')",
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
        if table in ORIGINAL_RECORDS:
            required = self._original_admission_keys
            if required is None:
                verifier = Graph(self.db, persist_identities=False)
                required = verifier.required_original_keys(
                    verifier.original_intake_context([record], repository_uuidv4)
                )
            if key not in required:
                return "invalid:retired_api_original"
            if self.rejected_api_original(record):
                return "invalid:rejected_api_original"
        for dependency in record.get("requires", ()):
            if not self.db.execute(
                "SELECT 1 FROM exchange_admissions WHERE record_key=? UNION ALL SELECT 1 FROM exchange_local_identities WHERE record_key=? AND table_name IN ('issue_resources','review_resources')",
                (dependency, dependency),
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
        from repo_catalog.adapters.sqlite.json_contracts import (
            JsonContractError,
            MissingJsonDependencies,
            validate_record,
        )

        try:
            validate_record(self.db, table, data)
        except MissingJsonDependencies:
            return "missing_json_dependency"
        except JsonContractError as exc:
            return "invalid:json_reference:" + str(exc)
        if table in {"completion_markers", "coverage_claims"}:
            requirements = self.proof_requirements(table, data)
            is_complete = (
                data.get("coverage_state", data.get("asserted_state")) == "complete"
            )
            if is_complete and requirements is None:
                return "missing_completeness_proof"
            if is_complete and set(record.get("requires", ())) != requirements:
                return "invalid:completeness_manifest"
        if table == "git_object_payloads":
            try:
                self.validate_git_payload(data)
            except CatalogError as exc:
                return "invalid:" + exc.code.lower()
        existing = self._existing(table, data)
        if table in CURRENT_RESOURCES:
            from repo_catalog.adapters.sqlite.current_resources import CurrentResources

            resources = CurrentResources(self.db)
            candidate = resources.candidate_from_row(table, data)
            resources.admit(candidate, source="import")
            # Accepted, identical, stale and conflicted mutable candidates were
            # all handled by the shared bounded admission mechanism. No sealed
            # immutable exchange receipt is created for a mutable state.
            # The natural identity mapping can precede a legitimate missing
            # parent. Shared staging retains one bounded semantic candidate,
            # rather than duplicate wire envelopes for every retry timestamp.
            local = self.local_key(table, data)
            self.db.execute(
                "INSERT OR IGNORE INTO exchange_local_identities VALUES(?,?,?)",
                (table, local, key),
            )
            return None
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
        if table == "code_listings":
            # Admission needs a receiver-local writable listing boundary. It
            # carries no sender completion, page count or operational state;
            # exact fact publication supplies the portable immutable seal.
            self.db.execute(
                "INSERT INTO code_listing_progress(code_listing_id,state,terminal,page_count,context_proven) SELECT ?,'partial',0,0,0 WHERE NOT EXISTS(SELECT 1 FROM code_listing_progress WHERE code_listing_id=?)",
                (existing["code_listing_id"], existing["code_listing_id"]),
            )
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
        verifier = Graph(self.db, persist_identities=False)
        required = verifier.required_original_keys(
            verifier.original_intake_context(records, unit["repository_uuidv4"])
        )
        # Reject independent original distribution before its Base64 envelope
        # can enter shared dependency staging or immutable admission receipts.
        for record in records:
            if record["table"] in ORIGINAL_RECORDS and record["key"] not in required:
                rejected.add(record["key"])
            elif self.rejected_api_original(record, records):
                rejected.add(record["key"])
        records = [record for record in records if record["key"] not in rejected]
        received = 0
        for record in records:
            serialized = canonical(record)
            digest = record_digest(record)
            previous = self.db.execute(
                "SELECT content_sha256,record_json FROM exchange_admissions WHERE record_key=?",
                (record["key"],),
            ).fetchone()
            if record["table"] in CURRENT_RESOURCES:
                # Shared state admission determines idempotence and ordering;
                # changing a natural-key resource is not UUID content conflict.
                previous = None
                data, unresolved = self.resolve(record)
                if not unresolved:
                    from repo_catalog.adapters.sqlite.current_resources import (
                        CurrentResources,
                    )

                    resources = CurrentResources(self.db)
                    candidate = resources.candidate_from_row(record["table"], data)
                    existing = self._existing(record["table"], data)
                    if (
                        existing is not None
                        and record_digest(self.record(record["table"], existing))
                        == digest
                    ):
                        if resources._stages(candidate):
                            # Exact current evidence still participates in
                            # re-evaluating alternatives that gained clocks or
                            # dependencies since this incumbent was admitted.
                            resources.admit(candidate, source="import")
                        continue
                    if any(
                        json.loads(stage["record_json"]) == candidate
                        for stage in resources._stages(candidate)
                    ):
                        # Exact repeated evidence is idempotent. A semantic
                        # fingerprint alone cannot discard a newly known clock
                        # or richer field-presence/acquisition evidence.
                        continue
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
            "SELECT record_key,table_name FROM exchange_staging GROUP BY record_key,table_name HAVING COUNT(*)>1"
        ).fetchall()
        for key, table in competing:
            if staging_owner(table, "") != "immutable_record":
                continue
            self.db.execute(
                "UPDATE exchange_staging SET reason='conflict:competing_variants' WHERE record_key=? AND table_name=?",
                (key, table),
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
        try:
            return self._promote(origin_catalog_uuidv4)
        finally:
            self._original_admission_keys = None

    def _promote(self, origin_catalog_uuidv4):
        admitted = 0
        changed = True
        while changed:
            changed = False
            if CURRENT_RESOURCES <= self.columns.keys():
                from repo_catalog.adapters.sqlite.current_resources import (
                    CurrentResources,
                )

                if CurrentResources(self.db).promote_staging():
                    changed = True
            pending = list(
                self.db.execute(
                    "SELECT record_key,content_sha256,record_json,reason,repository_uuidv4,origin_catalog_uuidv4,table_name FROM exchange_staging ORDER BY record_key,content_sha256"
                )
            )
            required_by_repository = {}
            verifier = Graph(self.db, persist_identities=False)
            for row in pending:
                repository = row[4]
                if repository not in required_by_repository:
                    required_by_repository[repository] = (
                        verifier.required_original_keys(
                            verifier.original_intake_context(
                                repository_uuidv4=repository
                            )
                        )
                    )
            for (
                key,
                digest,
                serialized,
                reason,
                repository_uuidv4,
                record_origin,
                table,
            ) in pending:
                if staging_owner(table, reason) == "current_candidate":
                    continue
                self._original_admission_keys = required_by_repository[
                    repository_uuidv4
                ]
                if (
                    table in ORIGINAL_RECORDS
                    and key not in self._original_admission_keys
                ):
                    # Direct-SQL/pending envelopes do not provide an alternate
                    # archive intake route. Delete the rejected envelope itself;
                    # retaining an invalid Base64 record would retain the body.
                    self.db.execute(
                        "DELETE FROM exchange_staging WHERE record_key=? AND content_sha256=?",
                        (key, digest),
                    )
                    continue
                record = json.loads(serialized)
                if table == "stored_bytes" and (
                    self.rejected_api_original(record)
                    or (
                        reason.startswith(("conflict:", "invalid:", "constraint:"))
                        and not self.retained_git_body(record)
                    )
                ):
                    # Rejected API bytes are not retry material. This applies
                    # before the normal invalid/conflict skip as well as intake;
                    # a real Git body keeps its existing repair staging meaning.
                    self.db.execute(
                        "DELETE FROM exchange_staging WHERE record_key=? AND content_sha256=?",
                        (key, digest),
                    )
                    continue
                if reason.startswith(("conflict:", "invalid:")):
                    continue
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
                    elif reason == "invalid:rejected_api_original":
                        self.db.execute(
                            "DELETE FROM exchange_staging WHERE record_key=? AND content_sha256=?",
                            (key, digest),
                        )
                except CatalogError as exc:
                    self.db.execute("ROLLBACK TO exchange_record")
                    if record["table"] in CURRENT_RESOURCES and (
                        exc.code.startswith("INVALID_CURRENT_RESOURCE")
                        or exc.code == "CURRENT_STATE_STAGING_FULL"
                    ):
                        reason = "invalid:" + exc.code.lower()
                    elif exc.code not in {
                        "PAYLOAD_CORRUPTION",
                        "PAYLOAD_HASH_COLLISION",
                        "PAYLOAD_QUARANTINED",
                    }:
                        raise
                    else:
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
        self.db.execute("DELETE FROM exchange_blocked_coverage_claims")
        blocked = set()
        pending = list(
            self.db.execute(
                "SELECT record_key,record_json,reason,table_name FROM exchange_staging"
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

        for key, serialized, reason, table in pending:
            if staging_owner(table, reason) == "current_candidate":
                continue
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
        from repo_catalog.adapters.sqlite.json_contracts import reference_dependencies

        # Build dependency edges once, then propagate with a queue. Shared
        # ancestry does not require repeatedly rescanning the complete graph.
        dependents = defaultdict(set)
        rows = {table: self.rows(table) for table in self.columns}
        for table, values in rows.items():
            for row in values:
                local = (table, self.local_key(table, row))
                for parent, child_cols, parent_cols in self.foreign[table]:
                    if parent not in rows:
                        continue
                    target = self.lookup(
                        parent, parent_cols, tuple(row[c] for c in child_cols)
                    )
                    if target is not None:
                        dependents[(parent, self.local_key(parent, target))].add(local)
                for dependency in reference_dependencies(table, row):
                    parent = dependency["table"]
                    target = self.lookup(
                        parent, dependency["columns"], dependency["values"]
                    )
                    if target is not None:
                        dependents[(parent, self.local_key(parent, target))].add(local)
                if row.get("parsed_result_uuidv4") and table != "parsed_results":
                    result = self.lookup(
                        "parsed_results",
                        ("parsed_result_uuidv4",),
                        (row["parsed_result_uuidv4"],),
                    )
                    if result is not None:
                        dependents[local].add(
                            ("parsed_results", self.local_key("parsed_results", result))
                        )
                if table == "git_acquisition_publications":
                    acquisition = self.lookup(
                        "git_acquisitions",
                        ("git_acquisition_id",),
                        (row["git_acquisition_id"],),
                    )
                    if acquisition is not None:
                        dependents[local].add(
                            (
                                "git_acquisitions",
                                self.local_key("git_acquisitions", acquisition),
                            )
                        )
        queue = deque(blocked)
        while queue:
            for dependent in dependents[queue.popleft()]:
                if dependent not in blocked:
                    blocked.add(dependent)
                    queue.append(dependent)
        for table, key in blocked:
            values = json.loads(key)
            row = self.lookup(
                table, tuple(values), tuple(decode(v) for v in values.values())
            )
            if table == "coverage_claims":
                self.db.execute(
                    "INSERT OR IGNORE INTO exchange_blocked_coverage_claims VALUES(?)",
                    (row["coverage_claim_id"],),
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
