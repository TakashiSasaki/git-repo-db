"""Portable typed domain records and discardable dependency intake.

An envelope checks transport integrity. It never creates or owns domain facts.
Mutable resources are admitted by the same field-aware merge as acquisition;
only unresolved candidates survive intake. Git structure comes from verified raw
objects, so receiving half a tree cannot make a complete intrinsic object.
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
GIT_FACTS = {"git_commit_facts", "git_text_facts", "git_name_facts"}
CURRENT_RESOURCES = {
    "issue_resources",
    "review_resources",
    "change_request_state",
    "document_state",
    "review_thread_state",
    "source_repositories",
}
# Closed domain vocabulary. New operational tables cannot become exchange roots
# merely by having a repository foreign key.
DOMAIN_TABLES = {
    "service_instances",
    "sources",
    "repositories",
    "repository_bindings",
    "repository_endpoints",
    "repository_names",
    "source_repositories",
    "change_requests",
    "documents",
    "review_threads",
    *CURRENT_RESOURCES,
    *GIT_FACTS,
    "fetch_collections",
    "current_collection_pages",
    "thread_collection_requirements",
    "thread_collection_targets",
    "completion_markers",
    "coverage_scopes",
    "coverage_claims",
    "code_listings",
    "code_commits",
    "code_file_changes",
    "code_assessments",
    "code_acquisitions",
    "change_request_events",
    "git_acquisitions",
    "snapshots",
    "ref_observations",
    "acquisition_roots",
    "root_origins",
    "git_objects",
    "git_object_payloads",
    "repository_object_sources",
    "contents",
    "content_digests",
    "blob_content_map",
    "text_bodies",
    "payloads",
    "stored_bytes",
    "identity_relations",
    "identity_relation_cancellations",
}
# Intrinsic Git rows are derived atomically by the canonical-object installer.
# Decoder facts remain local interpretations of transported authoritative bytes.
NATURAL = {
    "sources": ("source_registration_uuidv4",),
    "stored_bytes": ("sha256",),
    "payloads": ("representation", "sha256"),
    "text_bodies": ("sha256",),
    "git_objects": ("object_format", "oid"),
    "git_commit_facts": ("git_object_id", "decoder_key"),
    "git_text_facts": ("git_object_id", "decoder_key"),
    "coverage_claims": ("coverage_scope_id", "observed_at_us", "coverage_state"),
}
LOCAL_COLUMNS = {
    "repositories": {"preferred_repository_endpoint_id"},
    "fetch_collections": {"resume_scope_id"},
    "completion_markers": {"resume_scope_id"},
    "code_listings": {"resume_scope_id"},
}
SCOPES = {"coverage_scopes"}
SHA = re.compile(r"[0-9a-f]{64}\Z")
PR_COLLECTION_KINDS = {
    "pr-list",
    "pr-detail",
    "pr-code-check",
    "issue-comment",
    "issue-comment-incremental",
    "review",
    "review-comment",
    "review-comment-incremental",
    "threads",
    "thread-comments",
    "timeline",
    "pr-commits",
    "pr-files",
    "pr-title",
    "pr-body",
}
GIT_COVERAGE_KINDS = {"git", "refs", "structure", "digests", "heads-text"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_digest(record):
    return hashlib.sha256(canonical(record).encode("utf-8")).digest()


def staging_owner(table_name, reason):
    if reason.startswith("current_state:"):
        if table_name not in CURRENT_RESOURCES:
            raise CatalogError(
                "INVALID_EXCHANGE_STAGING", "Invalid current staging owner"
            )
        return "current_candidate"
    return "current_record" if table_name in CURRENT_RESOURCES else "immutable_record"


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
    if (
        set(value) == {"$sha256"}
        and isinstance(value["$sha256"], str)
        and SHA.fullmatch(value["$sha256"])
    ):
        return bytes.fromhex(value["$sha256"])
    if set(value) == {"$bytes"} and isinstance(value["$bytes"], str):
        try:
            return base64.b64decode(value["$bytes"], validate=True)
        except (ValueError, TypeError) as cause:
            raise CatalogError("INVALID_EXCHANGE", "Invalid base64 bytes") from cause
    raise CatalogError("INVALID_EXCHANGE", "Invalid typed value")


class Graph:
    def __init__(self, db, *, persist_identities=True):
        from repo_catalog.adapters.sqlite.cas_integrity import (
            register_git_object_sql_function,
        )

        register_git_object_sql_function(db)
        self.db, self.persist_identities = db, persist_identities
        self.rejected_records = 0
        self.columns, self.keys, self.foreign = {}, {}, {}
        names = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        for table in sorted(
            (DOMAIN_TABLES - {"contents", "content_digests", "blob_content_map"})
            & names
        ):
            info = list(db.execute(f'PRAGMA table_info("{table}")'))
            self.columns[table] = {r[1]: r[2] for r in info}
            self.keys[table] = tuple(
                r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]
            )
            groups = defaultdict(list)
            for row in db.execute(f'PRAGMA foreign_key_list("{table}")'):
                groups[row[0]].append(row)
            self.foreign[table] = []
            for group in groups.values():
                group.sort(key=lambda r: r[1])
                if any(r[3] not in self.columns[table] for r in group):
                    continue  # Generated family discriminators are SQL constraints.
                self.foreign[table].append(
                    (
                        group[0][2],
                        tuple(r[3] for r in group),
                        tuple(r[4] for r in group),
                    )
                )
            self.foreign[table].sort(
                key=lambda fk: fk[0] not in {"service_instances", "change_requests"}
            )
        for table, column in (
            ("git_commit_facts", "git_object_id"),
            ("git_text_facts", "git_object_id"),
            ("git_name_facts", "tree_git_object_id"),
        ):
            if table in self.columns:
                self.foreign[table] = [("git_objects", (column,), ("git_object_id",))]
        self.children = defaultdict(list)
        for child, foreign in self.foreign.items():
            for parent, child_cols, parent_cols in foreign:
                self.children[parent].append((child, child_cols, parent_cols))
        self.key_cache = {}

    def rows(self, table):
        return self.matching(table, (), ())

    def matching(self, table, columns, values):
        if table not in self.columns:
            return []
        fields = tuple(self.columns[table])
        sql = f'SELECT {",".join(chr(34) + c + chr(34) for c in fields)} FROM "{table}"'
        if columns:
            sql += " WHERE " + " AND ".join(f'"{c}" IS ?' for c in columns)
        return [
            dict(zip(fields, row, strict=True)) for row in self.db.execute(sql, values)
        ]

    def lookup(self, table, columns, values, *, allow_null=False):
        if (
            table not in self.columns
            or not allow_null
            and any(v is None for v in values)
        ):
            return None
        rows = self.matching(table, columns, values)
        return rows[0] if rows else None

    def local_key(self, table, row):
        columns = self.keys[table]
        if not all(c in row for c in columns) and table in NATURAL:
            columns = NATURAL[table]
        return canonical({c: encode(row[c], c) for c in columns})

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

    def _integer_identity(self, table):
        pk = self.keys[table]
        return (
            len(pk) == 1
            and self.columns[table][pk[0]] == "INTEGER"
            and not any(pk[0] in fk[1] for fk in self.foreign[table])
        )

    def key(self, table, row):
        local = self.local_key(table, row)
        cache = (table, local)
        if cache in self.key_cache:
            return self.key_cache[cache]
        previous = self.db.execute(
            "SELECT record_key FROM exchange_local_identities WHERE table_name=? AND local_key_json=?",
            cache,
        ).fetchone()
        if previous:
            self.key_cache[cache] = previous[0]
            return previous[0]
        values = {}
        for column in self.portable_columns(table):
            value = row[column]
            if self._integer_identity(table) and column in self.keys[table]:
                value = str(uuid.uuid4())
            else:
                value = self._foreign_value(table, row, column, value)
            values[column] = encode(value, column)
        key = table + ":" + canonical(values)
        if self.persist_identities:
            self.db.execute(
                "INSERT OR IGNORE INTO exchange_local_identities VALUES(?,?,?)",
                (table, local, key),
            )
        self.key_cache[cache] = key
        return key

    def _foreign_value(self, table, row, column, value):
        for parent, child_cols, parent_cols in self.foreign[table]:
            if (
                column not in child_cols
                or parent not in self.columns
                or any(c in LOCAL_COLUMNS.get(table, ()) for c in child_cols)
            ):
                continue
            if any(row.get(c) is None for c in child_cols):
                continue
            values = tuple(row[c] for c in child_cols)
            target = self.lookup(parent, parent_cols, values)
            key = (
                self.key(parent, target)
                if target
                else self.missing_parent_key(parent, parent_cols, values)
            )
            return {"$ref": key, "column": parent_cols[child_cols.index(column)]}
        return value

    def missing_parent_key(self, table, columns, values):
        identity = dict(zip(columns, values, strict=True))
        if not all(c in identity for c in self.portable_columns(table)):
            raise CatalogError(
                "INVALID_EXCHANGE", "Unavailable parent identity is incomplete"
            )
        return (
            table
            + ":"
            + canonical(
                {
                    c: encode(self._foreign_value(table, identity, c, identity[c]), c)
                    for c in self.portable_columns(table)
                }
            )
        )

    def expected_columns(self, table):
        columns = set(self.columns[table])
        if self._integer_identity(table):
            columns.remove(self.keys[table][0])
        if table == "sources":
            columns.discard("source_id")
        if table == "git_text_facts":
            columns.discard("content_id")
        if table in SCOPES:
            columns.difference_update(self.keys[table])
        if table in CURRENT_RESOURCES:
            columns.discard("last_checked_at_us")
        return columns

    def _json_references(self, table, column, text, *, incoming=False):
        """Translate modeled local IDs inside normalized authored domain JSON.

        Provider strings and text are never interpreted as references. Captured
        UUIDs can remain detached; only actual local integer owner keys require
        translation. Wire reference objects are accepted solely in those slots.
        """
        from repo_catalog.adapters.sqlite.json_contracts import (
            JSON_REGISTRY,
            REFERENCE_LISTS,
            REFERENCE_TARGETS,
        )

        schema = JSON_REGISTRY.get((table, column))
        if (
            schema is None
            or text is None
            or schema.category
            in {
                "provider",
                "decoded-headers",
                "operational",
                "local-key",
                "staging-envelope",
            }
        ):
            return text
        value = json.loads(text)
        targets = dict(REFERENCE_TARGETS)
        targets.update(
            {
                "code_listing_id": ("code_listings", "code_listing_id"),
                "code_assessment_id": ("code_assessments", "code_assessment_id"),
            }
        )

        def item(name, obj):
            target = targets.get(name)
            if (
                target
                and target[0] in self.columns
                and self.columns[target[0]].get(target[1]) == "INTEGER"
                and obj is not None
            ):
                parent, pcol = target
                if incoming:
                    if (
                        not isinstance(obj, dict)
                        or set(obj) != {"$ref", "column"}
                        or obj["column"] != pcol
                        or not obj["$ref"].startswith(parent + ":")
                    ):
                        raise CatalogError(
                            "INVALID_EXCHANGE",
                            "Invalid normalized JSON owner reference",
                        )
                    found = self._resolve_key(obj["$ref"])
                    if found is None:
                        raise CatalogError(
                            "EXCHANGE_DEPENDENCY_MISSING", "JSON owner is unavailable"
                        )
                    return found[pcol]
                found = self.lookup(parent, (pcol,), (obj,))
                if found is None:
                    raise CatalogError(
                        "INVALID_EXCHANGE", "JSON local owner is unavailable"
                    )
                return {"$ref": self.key(parent, found), "column": pcol}
            if name in REFERENCE_LISTS and isinstance(obj, list):
                return [item(REFERENCE_LISTS[name], child) for child in obj]
            if isinstance(obj, dict):
                return {key: item(key, child) for key, child in obj.items()}
            if isinstance(obj, list):
                return [item("", child) for child in obj]
            return obj

        return canonical(item("", value))

    def record(self, table, row):
        if table not in self.columns:
            raise CatalogError("INVALID_EXCHANGE", "Unsupported domain table")
        data = {}
        for column in self.expected_columns(table):
            value = row.get(column)
            if table == "sources" and column == "settings":
                value = None
            if column in LOCAL_COLUMNS.get(table, ()):
                value = None
            elif isinstance(value, str):
                value = self._json_references(table, column, value)
            data[column] = (
                encode(self._foreign_value(table, row, column, value), column)
                if column not in LOCAL_COLUMNS.get(table, ())
                else value
            )
        record = {"key": self.key(table, row), "table": table, "values": data}
        if table in {"completion_markers", "coverage_claims"}:
            proof = self.proof_requirements(table, row)
            if proof is not None:
                record["requires"] = sorted(proof)
        return record

    def _resolve_key(self, key):
        mapping = self.db.execute(
            "SELECT table_name,local_key_json FROM exchange_local_identities WHERE record_key=? "
            "UNION ALL SELECT table_name,local_key_json FROM exchange_admissions WHERE record_key=? LIMIT 1",
            (key, key),
        ).fetchone()
        if mapping:
            local = json.loads(mapping[1])
            return self.lookup(
                mapping[0],
                tuple(local),
                tuple(decode(v) for v in local.values()),
                allow_null=True,
            )
        try:
            table, value = key.split(":", 1)
            identity = json.loads(value)
        except (ValueError, TypeError):
            return None
        if table not in self.columns or set(identity) != set(
            self.portable_columns(table)
        ):
            return None
        resolved = {}
        for column, value in identity.items():
            if isinstance(value, dict) and "$ref" in value:
                parent = self._resolve_key(value["$ref"])
                if parent is None:
                    return None
                resolved[column] = parent[value["column"]]
            else:
                resolved[column] = decode(value)
        return self.lookup(
            table, tuple(resolved), tuple(resolved.values()), allow_null=True
        )

    def resolve(self, record):
        data = {}
        for column, value in record["values"].items():
            if isinstance(value, dict) and "$ref" in value:
                if self.db.execute(
                    "SELECT 1 FROM exchange_staging WHERE record_key=? AND reason LIKE 'conflict:%'",
                    (value["$ref"],),
                ).fetchone():
                    return None, "dependency_conflict"
                target = self._resolve_key(value["$ref"])
                if target is None:
                    return None, "missing_dependency"
                data[column] = target[value["column"]]
            else:
                decoded = decode(value)
                try:
                    data[column] = (
                        self._json_references(
                            record["table"], column, decoded, incoming=True
                        )
                        if isinstance(decoded, str)
                        else decoded
                    )
                except CatalogError as error:
                    if error.code == "EXCHANGE_DEPENDENCY_MISSING":
                        return None, "missing_json_dependency"
                    raise
        return data, None

    def _member(self, member):
        family = member.get("family")
        layout = {
            "issue": (
                "issue_resources",
                ("service_instance_uuidv4", "kind", "provider_resource_id"),
            ),
            "review": (
                "review_resources",
                ("change_request_id", "kind", "provider_change_request_document_id"),
            ),
            "change-request": ("change_request_state", ("change_request_id",)),
            "document": (
                "document_state",
                ("change_request_id", "kind", "provider_change_request_document_id"),
            ),
            "thread": (
                "review_thread_state",
                ("change_request_id", "provider_resource_id"),
            ),
            "code-commit": ("code_commits", ("code_listing_id", "position")),
            "code-file": ("code_file_changes", ("code_listing_id", "position")),
            "event": (
                "change_request_events",
                ("change_request_event_uuidv4",),
            ),
        }
        if family not in layout:
            return None
        table, columns = layout[family]
        if table not in self.columns or not all(c in member for c in columns):
            return None
        return (table, self.lookup(table, columns, tuple(member[c] for c in columns)))

    def current_page_requirements(self, collection_id, ordinals, *, baseline=True):
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        proof = CurrentCollectionProof(self.db)
        evidence = proof.evidence(collection_id)
        if evidence is None or evidence.get("page_ordinals") != ordinals:
            return None
        collection = self.lookup(
            "fetch_collections", ("fetch_collection_id",), (collection_id,)
        )
        if collection is None:
            return None
        required = {self.key("fetch_collections", collection)}
        for page in proof.pages(collection_id):
            required.add(self.key("current_collection_pages", page))
            for member in json.loads(page["members"]):
                subject = self._member(member)
                if subject is None or subject[1] is None:
                    return None
                # The old state digest attests a value at the observation time.
                # Latest-only resources need their stable identity, not that old
                # value or an impossible comparison with today's state digest.
                required.add(self.key(*subject))
        return required

    def proof_requirements(self, table, row, _visited=None):
        """Qualify one exact domain scope; incoming hints add no authority."""
        visited = set() if _visited is None else _visited
        if table == "completion_markers":
            identity = row.get(
                "completion_marker_uuidv4", row.get("completion_marker_id")
            )
            if identity in visited:
                return None
            visited = visited | {identity}
            if row["asserted_state"] != "complete":
                return set()
            evidence = json.loads(row["evidence"])
            if evidence.get("kind") not in {
                "current-resource-pages-v1",
                "current-resource-tree-v1",
            }:
                return None
            collection_id = row["fetch_collection_id"]
            required = self.current_page_requirements(
                collection_id, evidence.get("page_ordinals")
            )
            if required is None:
                return None
            pages = self.matching(
                "current_collection_pages", ("fetch_collection_id",), (collection_id,)
            )
            from repo_catalog.adapters.sqlite.current_collections import (
                CurrentCollectionProof,
            )

            if not pages or not CurrentCollectionProof(self.db).is_complete_marker(row):
                return None
            # Required children belong to this exact root enumeration. A child
            # from a prior scan cannot discharge the new root's obligations.
            obligations = self.matching(
                "thread_collection_requirements",
                ("fetch_collection_id",),
                (collection_id,),
            )
            thread_members = {
                member["provider_resource_id"]
                for page in pages
                for member in json.loads(page["members"])
                if member.get("family") == "thread"
            }
            if thread_members - {item["provider_resource_id"] for item in obligations}:
                return None
            for obligation in obligations:
                required.add(
                    self.key(
                        "thread_collection_requirements",
                        obligation,
                    )
                )
                child_id = obligation.get("child_fetch_collection_id")
                if not child_id:
                    return None
                child = self.lookup(
                    "fetch_collections", ("fetch_collection_id",), (child_id,)
                )
                parent = self.lookup(
                    "fetch_collections", ("fetch_collection_id",), (collection_id,)
                )
                if child is None or any(
                    child.get(c) != parent.get(c)
                    for c in ("repository_uuidv4", "change_request_id")
                ):
                    return None
                markers = self.matching(
                    "completion_markers", ("fetch_collection_id",), (child_id,)
                )
                complete = [m for m in markers if m["asserted_state"] == "complete"]
                if not complete:
                    return None
                latest = max(m["observed_at_us"] for m in markers)
                selected = [m for m in markers if m["observed_at_us"] == latest]
                if any(m["asserted_state"] != "complete" for m in selected):
                    return None
                for marker in selected:
                    child_required = self.proof_requirements(
                        "completion_markers", marker, visited
                    )
                    if child_required is None:
                        return None
                    required.update(child_required)
                    required.add(self.key("completion_markers", marker))
            return required
        if table != "coverage_claims" or row.get("coverage_state") != "complete":
            return set()
        details = json.loads(row.get("details_json") or "{}")
        required = set()
        scope = self.lookup(
            "coverage_scopes", ("coverage_scope_id",), (row["coverage_scope_id"],)
        )
        if scope is None:
            return None
        required.add(self.key("coverage_scopes", scope))
        if scope["kind"] in GIT_COVERAGE_KINDS:
            if details.get("completion_marker_uuidv4s"):
                return None
            snapshot = self.lookup(
                "snapshots", ("snapshot_id",), (details.get("snapshot_id"),)
            )
            if (
                snapshot is None
                or snapshot["repository_uuidv4"] != scope["repository_uuidv4"]
                or not snapshot["complete"]
                or scope.get("change_request_id") is not None
                or details.get("git_acquisition_id", snapshot["git_acquisition_id"])
                != snapshot["git_acquisition_id"]
            ):
                return None
            acquisition = self.lookup(
                "git_acquisitions",
                ("git_acquisition_id",),
                (snapshot["git_acquisition_id"],),
            )
            if (
                acquisition is None
                or acquisition["kind"] != "git"
                or acquisition["refs_observed_at_us"] is None
                or acquisition["refs_observed_at_us"] > row["observed_at_us"]
            ):
                return None
            from repo_catalog.adapters.git.parsing import validate_git_acquisition

            try:
                validate_git_acquisition(self.db, acquisition["git_acquisition_id"])
            except (CatalogError, sqlite3.IntegrityError):
                return None
            required.update(
                {
                    self.key("snapshots", snapshot),
                    self.key("git_acquisitions", acquisition),
                }
            )
            for table in (
                "ref_observations",
                "acquisition_roots",
                "repository_object_sources",
            ):
                column = (
                    "snapshot_id"
                    if table == "ref_observations"
                    else "git_acquisition_id"
                )
                value = (
                    snapshot["snapshot_id"]
                    if table == "ref_observations"
                    else acquisition["git_acquisition_id"]
                )
                for subject in self.matching(table, (column,), (value,)):
                    required.add(self.key(table, subject))
                    if (
                        table == "repository_object_sources"
                        and scope["kind"] == "heads-text"
                    ):
                        obj = self.lookup(
                            "git_objects",
                            ("git_object_id",),
                            (subject["git_object_id"],),
                        )
                        if obj is not None and obj["type"] == "blob":
                            candidates = self.matching(
                                "git_text_facts",
                                ("git_object_id",),
                                (obj["git_object_id"],),
                            )
                            if not candidates:
                                return None
                            required.update(
                                self.key("git_text_facts", fact) for fact in candidates
                            )
            return required
        marker_ids = details.get("completion_marker_uuidv4s")
        if not isinstance(marker_ids, list) or not marker_ids:
            return None
        subject_kinds = set()
        empty_pr_roster = False
        for identifier in marker_ids:
            marker = self.lookup(
                "completion_markers", ("completion_marker_uuidv4",), (identifier,)
            )
            if marker is None or marker["observed_at_us"] > row["observed_at_us"]:
                return None
            collection = self.lookup(
                "fetch_collections",
                ("fetch_collection_id",),
                (marker["fetch_collection_id"],),
            )
            if (
                collection is None
                or collection["repository_uuidv4"] != scope["repository_uuidv4"]
                or scope.get("change_request_id") is not None
                and collection.get("change_request_id") != scope["change_request_id"]
            ):
                return None
            kind = scope["kind"]
            allowed = (
                {"issue", "issues", "ordinary-issue-comment"}
                if kind == "issue"
                else PR_COLLECTION_KINDS
                if kind == "pr"
                else PR_COLLECTION_KINDS - {"pr-commits", "pr-files", "pr-code-check"}
                if kind == "pr-documents"
                else {
                    "pr-commits",
                    "pr-files",
                    "pr-code-check",
                    "pr-detail",
                    "pr-list",
                    "review",
                    "review-comment",
                    "threads",
                    "thread-comments",
                }
                if kind in {"pr-code", "pr-code-listings"}
                else {kind}
                if kind in PR_COLLECTION_KINDS | {"ordinary-issue-comment"}
                else set()
            )
            if collection["kind"] not in allowed:
                return None
            subject_kinds.add(collection["kind"])
            if collection["kind"] == "pr-list":
                empty_pr_roster |= not any(
                    member.get("family") == "change-request"
                    for page in self.matching(
                        "current_collection_pages",
                        ("fetch_collection_id",),
                        (collection["fetch_collection_id"],),
                    )
                    for member in json.loads(page["members"])
                )
            proof = self.proof_requirements("completion_markers", marker, visited)
            if proof is None:
                return None
            required.update(proof)
            required.add(self.key("completion_markers", marker))
        if (
            scope["kind"] in {"pr-code", "pr-code-listings"}
            and not empty_pr_roster
            and not {"pr-commits", "pr-files"} <= subject_kinds
        ):
            return None
        return required

    def _parents(self, table, row):
        for parent, child_cols, parent_cols in self.foreign[table]:
            if (
                parent not in self.columns
                or any(c in LOCAL_COLUMNS.get(table, ()) for c in child_cols)
                or any(row.get(c) is None for c in child_cols)
            ):
                continue
            target = self.lookup(parent, parent_cols, tuple(row[c] for c in child_cols))
            if target:
                yield parent, target

        if (
            table == "issue_resources"
            and row.get("kind") == "issue-comment"
            and row.get("parent_provider_resource_id")
        ):
            parent = self.lookup(
                "issue_resources",
                ("service_instance_uuidv4", "kind", "provider_resource_id"),
                (
                    row["service_instance_uuidv4"],
                    "issue",
                    row["parent_provider_resource_id"],
                ),
            )
            if parent:
                yield "issue_resources", parent
        if table == "review_resources":
            for column, kind in (
                ("review_provider_resource_id", "review"),
                ("in_reply_to_provider_resource_id", "review-comment"),
            ):
                if row.get(column):
                    parent = self.lookup(
                        "review_resources",
                        (
                            "change_request_id",
                            "kind",
                            "provider_change_request_document_id",
                        ),
                        (row["change_request_id"], kind, row[column]),
                    )
                    if parent:
                        yield "review_resources", parent
            if row.get("review_thread_provider_resource_id"):
                thread = self.lookup(
                    "review_threads",
                    ("change_request_id", "provider_resource_id"),
                    (
                        row["change_request_id"],
                        row["review_thread_provider_resource_id"],
                    ),
                )
                if thread:
                    yield "review_threads", thread
        if table in CURRENT_RESOURCES:
            scope = json.loads(row.get("acquisition_scope_json", "{}"))
            registration = scope.get("source_registration_uuidv4")
            if registration and scope.get("repository_uuidv4") == row.get(
                "repository_uuidv4"
            ):
                source = self.lookup(
                    "sources", ("source_registration_uuidv4",), (registration,)
                )
                if source:
                    yield "sources", source
                    membership = self.lookup(
                        "source_repositories",
                        ("source_id", "repository_uuidv4"),
                        (source["source_id"], row["repository_uuidv4"]),
                    )
                    if membership:
                        yield "source_repositories", membership

    def _json_dependencies(self, record):
        from repo_catalog.adapters.sqlite.json_contracts import (
            JSON_REGISTRY,
            reference_dependencies,
        )

        # Foreign refs are already handled separately. Natural authored IDs
        # supply real domain dependencies, with detached capture evidence excluded
        # by the same JSON contract as ordinary admission.
        data = {c: v for c, v in record["values"].items() if not isinstance(v, dict)}
        try:
            dependencies = reference_dependencies(record["table"], data)
        except CatalogError:
            dependencies = []
        for dependency in dependencies:
            table = dependency["table"]
            if table in self.columns:
                target = self.lookup(table, dependency["columns"], dependency["values"])
                if target:
                    yield table, target
        for column, value in record["values"].items():
            if (record["table"], column) not in JSON_REGISTRY or not isinstance(
                value, str
            ):
                continue

            def walk(obj):
                if isinstance(obj, dict):
                    if set(obj) == {"$ref", "column"}:
                        target = self._resolve_key(obj["$ref"])
                        if target:
                            yield obj["$ref"].split(":", 1)[0], target
                    else:
                        for item in obj.values():
                            yield from walk(item)
                elif isinstance(obj, list):
                    for item in obj:
                        yield from walk(item)

            yield from walk(json.loads(value))

    def current_candidate_row(self, candidate):
        if candidate.get("kind") == "source-repository":
            from repo_catalog.adapters.sqlite.current_api import CurrentApiState

            return CurrentApiState(self.db).source_candidate_row(candidate)
        row = dict(candidate)
        body = row.pop("body", None)
        if "body_status" in candidate:
            row["text_body_sha256"] = (
                hashlib.sha256(body.encode("utf-8")).digest()
                if body is not None
                else None
            )
        for column in (
            "head_oid",
            "base_oid",
            "merge_oid",
            "commit_oid",
            "original_commit_oid",
        ):
            if candidate.get("kind") in {
                "change-request",
                "review-thread",
            } and isinstance(row.get(column), str):
                row[column] = bytes.fromhex(row[column])
        if candidate.get("kind") == "review-thread" and isinstance(
            row.get("raw_path"), str
        ):
            row["raw_path"] = row["raw_path"].encode("utf8")
        for plain, stored in (
            ("metadata", "metadata"),
            ("acquisition_scope", "acquisition_scope_json"),
            ("field_evidence", "field_evidence_json"),
        ):
            if plain in row:
                row[stored] = canonical(row.pop(plain))
        return row

    def _candidate_exports(self, repository_uuidv4):
        from repo_catalog.adapters.sqlite.current_resources import CurrentResources

        result = list(CurrentResources(self.db).export_candidates(repository_uuidv4))
        if "change_request_state" in self.columns:
            from repo_catalog.adapters.sqlite.current_api import CurrentApiState

            result.extend(CurrentApiState(self.db).export_candidates(repository_uuidv4))

        return result

    def export(
        self, repository_uuidv4, *, fetch_collection_id=None, git_acquisition_id=None
    ):
        # A caller's writer/read transaction already establishes its snapshot.
        # Direct use establishes one too; portable-ID writes stay in that unit.
        owns = not self.db.in_transaction
        if owns:
            self.db.execute("BEGIN")
        try:
            result = self._export(
                repository_uuidv4,
                fetch_collection_id=fetch_collection_id,
                git_acquisition_id=git_acquisition_id,
            )
            if owns:
                self.db.execute("COMMIT")
            return result
        except BaseException:
            if owns and self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def _export(self, repository_uuidv4, *, fetch_collection_id, git_acquisition_id):
        repository = self.lookup(
            "repositories", ("repository_uuidv4",), (repository_uuidv4,)
        )
        if repository is None:
            raise CatalogError("NOT_FOUND", "Repository not found")
        if fetch_collection_id is not None and git_acquisition_id is not None:
            raise CatalogError("INVALID_EXCHANGE_SELECTION", "Select one domain scope")
        selected, queue = {}, deque()
        extra = []
        deferred = set()

        def add(table, row):
            if table not in self.columns or row is None:
                return
            if row.get("repository_uuidv4") not in (None, repository_uuidv4):
                raise CatalogError(
                    "INVALID_EXCHANGE", "Dependency belongs to a foreign repository"
                )
            if (
                table == "coverage_claims"
                and row["coverage_state"] == "complete"
                and self.proof_requirements(table, row) is None
            ):
                return
            local = (table, self.local_key(table, row))
            if local not in selected:
                selected[local] = row
                queue.append((table, row))

        add("repositories", repository)
        partial = fetch_collection_id is not None or git_acquisition_id is not None
        if fetch_collection_id is not None:
            root = self.lookup(
                "fetch_collections", ("fetch_collection_id",), (fetch_collection_id,)
            )
            if root is None or root["repository_uuidv4"] != repository_uuidv4:
                raise CatalogError(
                    "INVALID_EXCHANGE_SELECTION",
                    "Collection is unavailable in this repository",
                )
            add("fetch_collections", root)
            marker_ids = {
                row["completion_marker_uuidv4"]
                for row in self.matching(
                    "completion_markers",
                    ("fetch_collection_id",),
                    (fetch_collection_id,),
                )
            }
            if marker_ids:
                fields = tuple(self.columns["coverage_claims"])
                for marker in sorted(marker_ids):
                    for values in self.db.execute(
                        "SELECT "
                        + ",".join("c." + field for field in fields)
                        + " FROM coverage_claim_markers m"
                        + " JOIN coverage_claims c USING(coverage_claim_id)"
                        + " JOIN coverage_scopes s USING(coverage_scope_id)"
                        + " WHERE m.completion_marker_uuidv4=?"
                        + " AND s.repository_uuidv4=? AND s.change_request_id IS ?",
                        (marker, repository_uuidv4, root["change_request_id"]),
                    ):
                        add("coverage_claims", dict(zip(fields, values, strict=True)))
        elif git_acquisition_id is not None:
            root = self.lookup(
                "git_acquisitions", ("git_acquisition_id",), (git_acquisition_id,)
            )
            if root is None or root["repository_uuidv4"] != repository_uuidv4:
                raise CatalogError(
                    "INVALID_EXCHANGE_SELECTION",
                    "Git acquisition is unavailable in this repository",
                )
            add("git_acquisitions", root)
        else:
            for table, columns in self.columns.items():
                if (
                    "repository_uuidv4" in columns
                    and table not in CURRENT_RESOURCES
                    and table not in {"source_repositories"}
                ):
                    for row in self.matching(
                        table, ("repository_uuidv4",), (repository_uuidv4,)
                    ):
                        add(table, row)
            for table, candidate, _conflict in self._candidate_exports(
                repository_uuidv4
            ):
                row = self.current_candidate_row(candidate)
                body = candidate.get("body")
                if body is not None:
                    extra.append(
                        (
                            "text_bodies",
                            {
                                "sha256": hashlib.sha256(body.encode("utf8")).digest(),
                                "body": body,
                                "byte_length": len(body.encode("utf8")),
                            },
                        )
                    )
                extra.append((table, row))
                for parent, target in self._parents(table, row):
                    add(parent, target)

        def add_alternatives(table, identity):
            if not partial or table not in CURRENT_RESOURCES:
                return
            from repo_catalog.adapters.sqlite.current_api import CurrentApiState
            from repo_catalog.adapters.sqlite.current_resources import CurrentResources

            resources = (
                CurrentResources(self.db)
                if table in {"issue_resources", "review_resources"}
                else CurrentApiState(self.db)
            )
            candidate = dict(identity)
            if table == "source_repositories":
                candidate["kind"] = "source-repository"
            elif table == "review_thread_state":
                candidate["kind"] = "review-thread"
            elif table == "change_request_state":
                candidate["kind"] = "change-request"
            for stage in resources._stages(candidate):
                if stage["reason"] not in {
                    "current_state:conflict",
                    "current_state:missing_dependency",
                }:
                    continue
                staged = json.loads(stage["record_json"])
                if staged["repository_uuidv4"] != repository_uuidv4:
                    continue
                state = self.current_candidate_row(staged)
                if staged.get("body") is not None:
                    body = staged["body"]
                    extra.append(
                        (
                            "text_bodies",
                            {
                                "body": body,
                                "sha256": hashlib.sha256(body.encode("utf8")).digest(),
                                "byte_length": len(body.encode("utf8")),
                            },
                        )
                    )
                extra.append((table, state))
                for parent, target in self._parents(table, state):
                    add(parent, target)

        while queue:
            table, row = queue.popleft()
            add_alternatives(table, row)
            for parent, target in self._parents(table, row):
                add(parent, target)
            record = self.record(table, row)
            for key in record.get("requires", ()):
                target = self._resolve_key(key)
                if target and target.get("repository_uuidv4") in (
                    None,
                    repository_uuidv4,
                ):
                    add(key.split(":", 1)[0], target)
            for parent, target in self._json_dependencies(record):
                add(parent, target)
            for child, child_cols, parent_cols in self.children[table]:
                # Reverse ownership edges add members; registrations never pull
                # all same-repository resources into a selected closure.
                include = (
                    table == "fetch_collections"
                    and child
                    in {
                        "current_collection_pages",
                        "completion_markers",
                        "thread_collection_requirements",
                        "thread_collection_targets",
                        "code_listings",
                    }
                    or table == "coverage_scopes"
                    and child == "coverage_claims"
                    and not partial
                    or table == "code_listings"
                    and child in {"code_commits", "code_file_changes"}
                    or table == "git_acquisitions"
                    and child
                    in {"snapshots", "acquisition_roots", "repository_object_sources"}
                    or table == "snapshots"
                    and child == "ref_observations"
                    or table == "acquisition_roots"
                    and child == "root_origins"
                    or table == "git_objects"
                    and child in {"git_object_payloads", "blob_content_map", *GIT_FACTS}
                    or table == "contents"
                    and child == "content_digests"
                )
                if include:
                    for target in self.matching(
                        child, child_cols, tuple(row[c] for c in parent_cols)
                    ):
                        add(child, target)
            if table == "current_collection_pages":
                for member in json.loads(row["members"]):
                    target = self._member(member)
                    if target:
                        add_alternatives(target[0], member)
                    if (
                        target
                        and target[1]
                        and target[1].get("repository_uuidv4")
                        in (None, repository_uuidv4)
                    ):
                        add(*target)
            if table == "thread_collection_requirements" and row.get(
                "child_fetch_collection_id"
            ):
                add(
                    "fetch_collections",
                    self.lookup(
                        "fetch_collections",
                        ("fetch_collection_id",),
                        (row["child_fetch_collection_id"],),
                    ),
                )
        records = [self.record(table, row) for (table, _), row in selected.items()]
        records.extend(self.record(table, row) for table, row in extra)
        # Retain genuine unresolved wire records for onward delivery. API
        # candidates already come from the bounded shared admission export.
        if partial:

            def typed_references(record):
                for value in record["values"].values():
                    if isinstance(value, dict) and "$ref" in value:
                        yield value["$ref"]

                from repo_catalog.adapters.sqlite.json_contracts import JSON_REGISTRY

                def nested(value):
                    if isinstance(value, dict):
                        if set(value) == {"$ref", "column"}:
                            yield value["$ref"]
                        else:
                            for item in value.values():
                                yield from nested(item)
                    elif isinstance(value, list):
                        for item in value:
                            yield from nested(item)

                for column, value in record["values"].items():
                    if (record["table"], column) in JSON_REGISTRY and isinstance(
                        value, str
                    ):
                        yield from nested(json.loads(value))

            pending = deque(
                key
                for record in records
                for key in (
                    record["key"],
                    *typed_references(record),
                    *record.get("requires", ()),
                )
            )
            visited = set()
            while pending:
                key = pending.popleft()
                if key in visited:
                    continue
                visited.add(key)
                for stage in self.db.execute(
                    "SELECT record_json,reason FROM exchange_staging WHERE record_key=? AND repository_uuidv4=? AND reason NOT LIKE 'current_state:%'",
                    (key, repository_uuidv4),
                ):
                    record = json.loads(stage[0])
                    if record["table"] in self.columns:
                        records.append(record)
                        if stage[1] == "deferred:git_closure":
                            deferred.add((record["key"], record_digest(record)))
                        pending.extend(typed_references(record))
                if key.startswith("acquisition_roots:"):
                    for stage in self.db.execute(
                        "SELECT record_json FROM exchange_staging WHERE table_name='root_origins' "
                        "AND json_extract(record_json,'$.values.acquisition_root_id.\"$ref\"')=? AND repository_uuidv4=?",
                        (key, repository_uuidv4),
                    ):
                        record = json.loads(stage[0])
                        records.append(record)
                        # Follow the candidate key as well, preserving genuine
                        # alternatives of this selected pending child.
                        pending.append(record["key"])
                        pending.extend(typed_references(record))
        else:
            for stage in self.db.execute(
                "SELECT record_json,reason FROM exchange_staging WHERE repository_uuidv4=? AND reason NOT LIKE 'current_state:%'",
                (repository_uuidv4,),
            ):
                record = json.loads(stage[0])
                if record["table"] in self.columns:
                    records.append(record)
                    if stage[1] == "deferred:git_closure":
                        deferred.add((record["key"], record_digest(record)))
        # An incomplete receiver row is the physical prefix of its one deferred
        # closure candidate. Forward that candidate once, without manufacturing
        # competing complete/incomplete envelopes for the same capture.
        unique = {(record["key"], record_digest(record)): record for record in records}
        for key, digest in list(unique):
            candidate = unique[key, digest]
            if (key, digest) not in deferred:
                continue
            prefix = {**candidate, "values": {**candidate["values"], "complete": 0}}
            unique.pop((key, record_digest(prefix)), None)
        records = sorted(
            unique.values(), key=lambda r: (r["table"], r["key"], record_digest(r))
        )
        authorized = self._git_authorizations(records, include_staging=False)
        records = [
            r
            for r in records
            if r["table"] not in {"payloads", "stored_bytes"} or r["key"] in authorized
        ]
        identity = self.db.execute(
            "SELECT db_instance_id FROM database_identity WHERE singleton=1"
        ).fetchone()
        return {
            "format": FORMAT,
            "repository_uuidv4": repository_uuidv4,
            "origin_catalog_uuidv4": identity[0],
            "records": records,
        }

    def validate_record(self, record):
        if not isinstance(record, dict) or set(record) not in (
            {"key", "table", "values"},
            {"key", "table", "values", "requires"},
        ):
            raise CatalogError("INVALID_EXCHANGE", "Invalid domain record envelope")
        table, data = record["table"], record["values"]
        if (
            table not in self.columns
            or not isinstance(data, dict)
            or set(data) != self.expected_columns(table)
        ):
            raise CatalogError(
                "INVALID_EXCHANGE",
                "Unexpected domain table or columns",
                {"table": table},
            )
        if not isinstance(record["key"], str) or not record["key"].startswith(
            table + ":"
        ):
            raise CatalogError("INVALID_EXCHANGE", "Invalid portable record key")
        if "requires" in record and (
            table not in {"completion_markers", "coverage_claims"}
            or not isinstance(record["requires"], list)
            or any(not isinstance(k, str) for k in record["requires"])
            or len(record["requires"]) != len(set(record["requires"]))
        ):
            raise CatalogError("INVALID_EXCHANGE", "Invalid domain dependency hints")
        for column, value in data.items():
            if isinstance(value, dict) and "$ref" in value:
                if (
                    set(value) != {"$ref", "column"}
                    or not isinstance(value["$ref"], str)
                    or not any(
                        value["$ref"].startswith(parent + ":")
                        and value["column"] == parent_cols[child_cols.index(column)]
                        for parent, child_cols, parent_cols in self.foreign[table]
                        if column in child_cols
                    )
                ):
                    raise CatalogError(
                        "INVALID_EXCHANGE",
                        "Reference is not a declared typed foreign key",
                    )
            else:
                decode(value)
                if (
                    value is not None
                    and column not in LOCAL_COLUMNS.get(table, ())
                    and any(
                        column in child_cols
                        and parent in self.columns
                        and all(data.get(c) is not None for c in child_cols)
                        for parent, child_cols, _ in self.foreign[table]
                    )
                ):
                    raise CatalogError(
                        "INVALID_EXCHANGE",
                        "Typed foreign keys require portable references",
                    )
        portable = self.portable_columns(table)
        if all(c in data for c in portable) and record[
            "key"
        ] != table + ":" + canonical({c: data[c] for c in portable}):
            raise CatalogError(
                "INVALID_EXCHANGE", "Record key disagrees with typed identity"
            )
        for column in LOCAL_COLUMNS.get(table, ()):
            if data.get(column) is not None:
                raise CatalogError(
                    "INVALID_EXCHANGE", "Operational pointers are receiver-local"
                )
        if table == "payloads" and data["representation"] != "git-object-raw-v1":
            raise CatalogError(
                "INVALID_EXCHANGE", "Only authoritative Git bytes are portable payloads"
            )
        if table in {"stored_bytes", "text_bodies"}:
            body = decode(data["body"])
            digest = decode(data["sha256"])
            encoded = (
                body.encode("utf8")
                if isinstance(body, str) and table == "text_bodies"
                else body
            )
            if (
                not isinstance(encoded, bytes)
                or not isinstance(digest, bytes)
                or hashlib.sha256(encoded).digest() != digest
                or data["byte_length"] != len(encoded)
            ):
                raise CatalogError(
                    "PAYLOAD_DIGEST_MISMATCH",
                    "Domain bytes do not match their exact SHA-256",
                )
        self._validate_unresolved_json(table, data)

    def _validate_unresolved_json(self, table, data):
        """Check modeled shapes before a missing parent can enter intake.

        Portable identities may omit attributes of an unresolved parent. Do
        not infer those attributes from an older capture: transferred Issue
        comments retain that capture. Admission checks actual resolved owners.
        """
        from repo_catalog.adapters.sqlite.json_contracts import (
            JSON_REGISTRY,
            REFERENCE_LISTS,
            REFERENCE_TARGETS,
            _check_schema,
            _load,
        )

        def scalar(value):
            if not isinstance(value, dict) or "$ref" not in value:
                return decode(value)
            parent, encoded = value["$ref"].split(":", 1)
            column = value["column"]
            if self.columns[parent][column] == "INTEGER":
                return 1  # Only a shape placeholder, never a retained local ID.
            try:
                identity = json.loads(encoded)
            except ValueError:
                raise CatalogError(
                    "INVALID_EXCHANGE", "Invalid portable parent key"
                ) from None
            found = identity.get(column)
            return scalar(found) if found is not None else None

        values = {column: scalar(value) for column, value in data.items()}

        def json_scalar(name, value):
            if isinstance(value, dict) and "$ref" in value:
                target = REFERENCE_TARGETS.get(name)
                if (
                    not target
                    or target[0] not in self.columns
                    or self.columns[target[0]].get(target[1]) != "INTEGER"
                    or set(value) != {"$ref", "column"}
                    or value["column"] != target[1]
                    or not isinstance(value["$ref"], str)
                    or not value["$ref"].startswith(target[0] + ":")
                ):
                    raise CatalogError(
                        "INVALID_EXCHANGE", "Invalid modeled JSON reference"
                    )
                return scalar(value)
            if isinstance(value, dict):
                return {key: json_scalar(key, child) for key, child in value.items()}
            if isinstance(value, list):
                return [
                    json_scalar(REFERENCE_LISTS.get(name, ""), child) for child in value
                ]
            return value

        for (owner, column), schema in JSON_REGISTRY.items():
            if owner != table or values.get(column) is None:
                continue
            parsed = _load(values[column], schema, table + "." + column)
            if schema.category in {
                "authored",
                "git-roots",
                "current-members",
                "inventory-members",
            }:
                parsed = json_scalar("", parsed)
            _check_schema(table, column, parsed, values, check_owner=False)

    def _git_authorizations(self, records, *, include_staging=True):
        """Real typed Git byte consumers authorize content, never `requires`."""
        from repo_catalog.domain.git_object import validate_git_object

        by_key = {r["key"]: r for r in records}
        # Already staged mappings permit reversed delivery of their raw bytes.
        stages = (
            self.db.execute(
                "SELECT record_json FROM exchange_staging WHERE table_name IN ('git_objects','git_object_payloads','repository_object_sources','payloads','stored_bytes') AND reason NOT LIKE 'conflict:%'"
            )
            if include_staging
            else ()
        )
        for stage in stages:
            try:
                record = json.loads(stage[0])
                by_key.setdefault(record["key"], record)
            except (ValueError, KeyError):
                continue

        def get(key):
            if key in by_key:
                return by_key[key]
            table = key.split(":", 1)[0]
            target = self._resolve_key(key)
            return (
                self.record(table, target)
                if target is not None and table in self.columns
                else None
            )

        # A single pass builds the actual typed association set. Checking each
        # object's consumer must not repeatedly traverse every selected record.
        associated_objects = {
            record["values"]["git_object_id"]["$ref"]
            for record in by_key.values()
            if record["table"] == "repository_object_sources"
            and isinstance(record["values"].get("git_object_id"), dict)
            and "$ref" in record["values"]["git_object_id"]
        }
        authorized = set()
        for mapping in list(by_key.values()):
            if mapping["table"] != "git_object_payloads":
                continue
            values = mapping["values"]
            objref = values.get("git_object_id")
            payloadref = values.get("payload_sha256")
            if not isinstance(objref, dict) or not isinstance(payloadref, dict):
                continue
            obj, payload = get(objref["$ref"]), get(payloadref["$ref"])
            if obj is None or payload is None:
                continue
            rawref = payload["values"].get("sha256")
            if not isinstance(rawref, dict):
                continue
            raw = get(rawref["$ref"])
            if raw is None:
                continue
            body = decode(raw["values"]["body"])
            digest = decode(raw["values"]["sha256"])
            object_values = obj["values"]
            # A genuine typed repository association is needed. The sender's
            # arbitrary dependency hints cannot authorize orphan content.
            associated = obj["key"] in associated_objects
            local_obj = self._resolve_key(obj["key"])
            if local_obj is not None:
                associated |= bool(
                    self.db.execute(
                        "SELECT 1 FROM repository_object_sources WHERE git_object_id=? LIMIT 1",
                        (local_obj["git_object_id"],),
                    ).fetchone()
                )
            if not associated:
                continue
            try:
                validate_git_object(
                    object_values["object_format"],
                    decode(object_values["oid"]),
                    object_values["type"],
                    object_values["size"],
                    body,
                    digest,
                )
            except CatalogError:
                continue
            authorized.update({obj["key"], mapping["key"], payload["key"], raw["key"]})
        return authorized

    def _existing(self, table, data):
        columns = self.portable_columns(table)
        if self._integer_identity(table) and not all(c in data for c in columns):
            # These typed subjects have real natural UNIQUE constraints.
            # Discarding processing aliases must not duplicate admitted facts.
            columns = {
                "acquisition_roots": (
                    "git_acquisition_id",
                    "object_format",
                    "oid",
                    "role",
                ),
                "root_origins": (
                    "acquisition_root_id",
                    "origin_kind",
                    "source_ordinal",
                ),
            }.get(table, columns)
        if all(c in data for c in columns):
            return self.lookup(
                table, columns, tuple(data[c] for c in columns), allow_null=True
            )
        return None

    def _remember(self, record, data):
        local = self.local_key(record["table"], data)
        self.db.execute(
            "INSERT OR IGNORE INTO exchange_local_identities VALUES(?,?,?)",
            (record["table"], local, record["key"]),
        )
        self.db.execute(
            "INSERT INTO exchange_admissions VALUES(?,?,?,?) ON CONFLICT(record_key) DO UPDATE SET table_name=excluded.table_name,local_key_json=excluded.local_key_json,content_sha256=excluded.content_sha256",
            (record["key"], record["table"], local, record_digest(record)),
        )

    def _restore_code_progress(self, listing):
        """Reconstruct a disposable listing assessment from its exact receipt."""
        from repo_catalog.adapters.sqlite.current_collections import (
            CurrentCollectionProof,
        )

        collection = self.lookup(
            "fetch_collections",
            ("fetch_collection_id",),
            (listing["fetch_collection_id"],),
        )
        if collection is None:
            return False
        context = json.loads(collection["scope_json"]).get("request_context", {})
        expected_kind = "pr-commits" if listing["kind"] == "commits" else "pr-files"
        targets_match = (
            collection["kind"] == expected_kind
            and collection["change_request_id"] == listing["change_request_id"]
            and all(
                context.get(name, {}).get("sha")
                == (listing[name + "_oid"].hex() if listing[name + "_oid"] else None)
                for name in ("head", "base")
            )
        )
        proof = CurrentCollectionProof(self.db)
        pages = proof.pages(collection["fetch_collection_id"])
        markers = self.matching(
            "completion_markers",
            ("fetch_collection_id",),
            (collection["fetch_collection_id"],),
        )
        complete = targets_match and any(
            marker["asserted_state"] == "complete"
            and self.proof_requirements("completion_markers", marker) is not None
            for marker in markers
        )
        terminal = bool(pages and not pages[-1]["has_next"])
        previous = self.db.execute(
            "SELECT state FROM code_listing_progress WHERE code_listing_id=?",
            (listing["code_listing_id"],),
        ).fetchone()
        if previous is None:
            self.db.execute(
                "INSERT INTO code_listing_progress VALUES(?,?,?,?,?)",
                (
                    listing["code_listing_id"],
                    "complete" if complete else "partial",
                    int(terminal),
                    len(pages),
                    int(targets_match),
                ),
            )
        elif previous[0] != "complete":
            self.db.execute(
                "UPDATE code_listing_progress SET state=?,terminal=?,page_count=?,context_proven=? WHERE code_listing_id=?",
                (
                    "complete" if complete else "partial",
                    int(terminal),
                    len(pages),
                    int(targets_match),
                    listing["code_listing_id"],
                ),
            )
        return complete

    def _admit(self, record, origin_catalog_uuidv4, repository_uuidv4):
        table = record["table"]
        data, reason = self.resolve(record)
        if reason:
            return reason
        if data.get("repository_uuidv4") not in (None, repository_uuidv4):
            return "invalid:cross_repository_owner"
        if table == "git_text_facts":
            content = self.db.execute(
                "SELECT content_id FROM blob_content_map WHERE git_object_id=?",
                (data["git_object_id"],),
            ).fetchone()
            if content is None:
                return "missing_git_subject"
            data["content_id"] = content[0]
        if table in GIT_FACTS:
            subject = data.get("git_object_id", data.get("tree_git_object_id"))
            if not self.db.execute(
                "SELECT 1 FROM repository_object_sources WHERE repository_uuidv4=? AND git_object_id=? LIMIT 1",
                (repository_uuidv4, subject),
            ).fetchone():
                return "missing_git_owner"
            from repo_catalog.adapters.git.parsing import validate_git_fact

            try:
                data = validate_git_fact(self.db, table, data)
            except CatalogError as error:
                return (
                    "missing_git_subject"
                    if error.code == "EXCHANGE_DEPENDENCY_MISSING"
                    else "invalid:git_decoder_value"
                )
        from repo_catalog.adapters.sqlite.json_contracts import (
            MissingJsonDependencies,
            validate_record,
        )

        try:
            validate_record(self.db, table, data)
        except MissingJsonDependencies:
            return "missing_json_dependency"
        except CatalogError:
            return "invalid:domain_json"
        if table == "root_origins" and data["origin_kind"] == "ref":
            root = self.lookup(
                "acquisition_roots",
                ("acquisition_root_id",),
                (data["acquisition_root_id"],),
            )
            snapshot = self.lookup(
                "snapshots", ("snapshot_id",), (data["snapshot_id"],)
            )
            if (
                root is None
                or snapshot is None
                or root["repository_uuidv4"] != data["repository_uuidv4"]
                or snapshot["repository_uuidv4"] != data["repository_uuidv4"]
                or root["git_acquisition_id"] != snapshot["git_acquisition_id"]
                or data["change_request_id"] is not None
                or data["code_assessment_id"] is not None
                or not isinstance(data["raw_ref_name"], bytes)
                or not data["raw_ref_name"]
                or type(data["source_ordinal"]) is not int
                or data["source_ordinal"] < 0
            ):
                return "invalid:git_ref_origin"
            ref = self.lookup(
                "ref_observations",
                ("snapshot_id", "raw_ref_name"),
                (data["snapshot_id"], data["raw_ref_name"]),
            )
            if ref is None:
                return "missing_captured_ref"
            if (
                ref["object_format"] != root["object_format"]
                or (ref["peeled_oid"] or ref["target_oid"]) != root["oid"]
            ):
                return "invalid:git_ref_origin"
        if table == "code_assessments" and data["state"] == "complete":
            for column in ("commit_code_listing_id", "file_code_listing_id"):
                listing = self.lookup(
                    "code_listings", ("code_listing_id",), (data[column],)
                )
                if listing is None or not self._restore_code_progress(listing):
                    return "missing_code_listing_proof"
        if table in {"completion_markers", "coverage_claims"}:
            proof = self.proof_requirements(table, data)
            complete = (
                data.get("asserted_state", data.get("coverage_state")) == "complete"
            )
            if complete and proof is None:
                return "missing_completeness_proof"
            if complete and set(record.get("requires", ())) != proof:
                # Processing aliases may change after receipt loss. Compare
                # resolved domain subjects, never treat an alias as authority.
                def subjects(keys):
                    result = set()
                    for key in keys:
                        owner = key.split(":", 1)[0]
                        subject = self._resolve_key(key)
                        if subject is None:
                            return None
                        result.add((owner, self.local_key(owner, subject)))
                    return result

                received_subjects = subjects(record.get("requires", ()))
                if received_subjects is None:
                    return "missing_completeness_dependency"
                if received_subjects != subjects(proof):
                    return "invalid:completeness_dependencies"
            for key in proof or ():
                if self._resolve_key(key) is None:
                    return "missing_completeness_dependency"
                if self.db.execute(
                    "SELECT 1 FROM exchange_staging WHERE record_key=? AND reason LIKE 'conflict:%'",
                    (key,),
                ).fetchone():
                    return "dependency_conflict"
        if table in CURRENT_RESOURCES:
            from repo_catalog.adapters.sqlite.current_resources import CurrentResources

            if table == "source_repositories":
                from repo_catalog.adapters.sqlite.current_api import CurrentApiState

                resources = CurrentApiState(self.db)
                resources.admit_source_row(data, source="import")
            elif table in {"issue_resources", "review_resources"}:
                resources = CurrentResources(self.db)
                candidate = resources.candidate_from_row(table, data)
                resources.admit(candidate, source="import")
            else:
                from repo_catalog.adapters.sqlite.current_api import CurrentApiState

                resources = CurrentApiState(self.db)
                candidate = resources.candidate_from_row(table, data)
                resources.admit(table, candidate, source="import")
            # Record existence mapping, never a saved mutable accepted envelope.
            self.db.execute(
                "INSERT OR IGNORE INTO exchange_local_identities VALUES(?,?,?)",
                (table, self.local_key(table, data), record["key"]),
            )
            return None
        existing = self._resolve_key(record["key"]) or self._existing(table, data)
        if existing is not None and table in {"git_text_facts", "git_commit_facts"}:
            data["git_fact_uuidv4"] = existing["git_fact_uuidv4"]
        if existing is not None and self._integer_identity(table):
            data[self.keys[table][0]] = existing[self.keys[table][0]]
        requested_complete = (
            table in {"snapshots", "acquisition_roots"} and data.get("complete") == 1
        )
        if requested_complete:
            data["complete"] = existing["complete"] if existing else 0
        if table == "sources":
            if existing and any(
                existing[c] != data[c]
                for c in ("service_instance_uuidv4", "discovery_kind")
            ):
                return "conflict:source_identity"
            if existing:
                data = existing
            else:
                data.update(source_id=str(uuid.uuid4()), settings=None)
        elif table in {"repositories", "service_instances"} and existing:
            if (
                table == "service_instances"
                and existing["service_kind"] != data["service_kind"]
            ):
                return "conflict:service_identity"
            data = existing
        elif existing:
            if table in SCOPES:
                data.update({c: existing[c] for c in self.keys[table]})
            from repo_catalog.adapters.sqlite.json_contracts import JSON_REGISTRY

            def equivalent(column, value):
                previous = existing.get(column)
                if (
                    (table, column) in JSON_REGISTRY
                    and previous is not None
                    and value is not None
                ):
                    return json.loads(previous) == json.loads(value)
                return previous == value

            if any(not equivalent(c, value) for c, value in data.items()):
                return "conflict:immutable_content"
        if existing is None:
            if table in SCOPES:
                data.update({c: str(uuid.uuid4()) for c in self.keys[table]})
            if table == "stored_bytes":
                intern_stored_bytes(self.db, data["body"], data["sha256"])
            elif table in {"identity_relations", "identity_relation_cancellations"}:
                from repo_catalog.adapters.sqlite.identity_relations import (
                    IdentityRelations,
                )

                status = IdentityRelations(self.db).admit(
                    "relation" if table == "identity_relations" else "cancellation",
                    data,
                )
                if status not in {"accepted", "duplicate"}:
                    return "missing_identity_dependency"
            else:
                columns = tuple(data)
                cursor = self.db.execute(
                    f'INSERT INTO "{table}"({",".join(columns)}) VALUES({",".join("?" for _ in columns)})',
                    tuple(data.values()),
                )
                if self._integer_identity(table):
                    data[self.keys[table][0]] = cursor.lastrowid
        if table == "git_object_payloads":
            self._install_git(data, repository_uuidv4)
        if table in {"code_listings", "completion_markers", "current_collection_pages"}:
            for listing in self.matching(
                "code_listings",
                ("fetch_collection_id",),
                (data["fetch_collection_id"],),
            ):
                self._restore_code_progress(listing)
        if requested_complete:
            from repo_catalog.adapters.git.parsing import validate_git_acquisition

            self._remember(record, data)
            try:
                validate_git_acquisition(self.db, data["git_acquisition_id"])
                if table == "acquisition_roots":
                    if not self.db.execute(
                        "SELECT 1 FROM available_git_objects g JOIN repository_object_sources r USING(git_object_id) WHERE r.git_acquisition_id=? AND g.object_format=? AND g.oid=?",
                        (
                            data["git_acquisition_id"],
                            data["object_format"],
                            data["oid"],
                        ),
                    ).fetchone():
                        return "deferred:git_closure"
                key_columns = self.keys[table]
                self.db.execute(
                    f"UPDATE {table} SET complete=1 WHERE "
                    + " AND ".join(c + "=?" for c in key_columns),
                    tuple(data[c] for c in key_columns),
                )
                data["complete"] = 1
            except (CatalogError, sqlite3.IntegrityError):
                return "deferred:git_closure"
        self._remember(record, data)
        return None

    def _install_git(self, data, repository_uuidv4):
        from repo_catalog.adapters.git.parsing import install_git_object

        obj = self.lookup("git_objects", ("git_object_id",), (data["git_object_id"],))
        raw = self.lookup("stored_bytes", ("sha256",), (data["payload_sha256"],))
        if obj is None or raw is None:
            raise CatalogError("EXCHANGE_DEPENDENCY_MISSING", "Git body is unavailable")
        # The installer validates OID/type/size and writes the entire intrinsic
        # object transactionally. A wire relation prefix has no admission route.
        install_git_object(
            self.db,
            obj["object_format"],
            obj["oid"],
            obj["type"],
            raw["body"],
            repository_uuid=repository_uuidv4,
            decode=False,
        )

    def receive(self, unit):
        from repo_catalog.adapters.sqlite.json_contracts import JsonContractError

        self.rejected_records = 0
        if (
            not isinstance(unit, dict)
            or set(unit)
            != {"format", "repository_uuidv4", "origin_catalog_uuidv4", "records"}
            or unit["format"] != FORMAT
            or not isinstance(unit["records"], list)
        ):
            raise CatalogError(
                "INVALID_EXCHANGE", "Unsupported repository exchange envelope"
            )
        for name in ("repository_uuidv4", "origin_catalog_uuidv4"):
            try:
                identity = uuid.UUID(unit[name])
                if identity.version != 4 or str(identity) != unit[name]:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError) as cause:
                raise CatalogError(
                    "INVALID_EXCHANGE", "Owner requires canonical UUIDv4"
                ) from cause
        rejected = set()
        invalid_values = 0
        records = []
        for record in unit["records"]:
            try:
                self.validate_record(record)
            except JsonContractError:
                # A malformed modeled value rejects this candidate. It cannot
                # hide a valid sibling or remain in original-bearing intake.
                invalid_values += 1
                continue
            except CatalogError as error:
                if error.code != "PAYLOAD_DIGEST_MISMATCH":
                    raise
                rejected.add(record["key"])
            records.append(record)
        owner = "repositories:" + canonical(
            {"repository_uuidv4": unit["repository_uuidv4"]}
        )
        for record in records:
            ref = record["values"].get("repository_uuidv4")
            if (
                record["table"] == "repositories"
                and record["key"] != owner
                or isinstance(ref, dict)
                and ref.get("$ref", "").startswith("repositories:")
                and ref.get("$ref") != owner
            ):
                raise CatalogError(
                    "INVALID_EXCHANGE", "Foreign repository record in envelope"
                )
        authorized = self._git_authorizations(records)
        for record in records:
            if (
                record["table"]
                in {"stored_bytes", "payloads", "git_objects", "git_object_payloads"}
                and record["key"] not in authorized
            ):
                # Missing Git body may legitimately wait behind its real typed
                # mapping. Unconsumed byte envelopes cannot become an archive.
                if record["table"] in {"stored_bytes", "payloads"}:
                    rejected.add(record["key"])
        changed = True
        while changed:
            changed = False
            for record in records:
                if record["key"] not in rejected and any(
                    isinstance(v, dict) and v.get("$ref") in rejected
                    for v in record["values"].values()
                ):
                    rejected.add(record["key"])
                    changed = True
        received = 0
        for record in records:
            if record["key"] in rejected:
                continue
            digest = record_digest(record)
            previous = self.db.execute(
                "SELECT content_sha256 FROM exchange_admissions WHERE record_key=?",
                (record["key"],),
            ).fetchone()
            if (
                previous
                and previous[0] == digest
                and record["table"] not in CURRENT_RESOURCES
            ):
                continue
            # Shared current admission handles stale/equal/unordered candidates.
            if record["table"] in CURRENT_RESOURCES:
                data, reason = self.resolve(record)
                if reason is None:
                    existing = self._existing(record["table"], data)
                    if (
                        existing
                        and record_digest(self.record(record["table"], existing))
                        == digest
                    ):
                        continue
            if record["table"] in CURRENT_RESOURCES and reason is None:
                if record["table"] in {"issue_resources", "review_resources"}:
                    from repo_catalog.adapters.sqlite.current_resources import (
                        CurrentResources,
                    )

                    resources = CurrentResources(self.db)
                else:
                    from repo_catalog.adapters.sqlite.current_api import CurrentApiState

                    resources = CurrentApiState(self.db)
                candidate = resources.candidate_from_row(record["table"], data)
                if any(
                    json.loads(stage["record_json"]) == candidate
                    or record_digest(
                        self.record(
                            record["table"],
                            self.current_candidate_row(
                                json.loads(stage["record_json"])
                            ),
                        )
                    )
                    == digest
                    for stage in resources._stages(candidate)
                ):
                    continue
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO exchange_staging VALUES(?,?,?,?,?,?,?)",
                (
                    record["key"],
                    digest,
                    record["table"],
                    unit["repository_uuidv4"],
                    unit["origin_catalog_uuidv4"],
                    canonical(record),
                    "missing_dependency",
                ),
            )
            received += cursor.rowcount
        for key, table in self.db.execute(
            "SELECT record_key,table_name FROM exchange_staging WHERE reason NOT LIKE 'current_state:%' GROUP BY record_key,table_name HAVING count(*)>1"
        ).fetchall():
            if table not in CURRENT_RESOURCES | GIT_FACTS:
                self.db.execute(
                    "UPDATE exchange_staging SET reason='conflict:competing_variants' WHERE record_key=?",
                    (key,),
                )
        admitted = self.promote(unit["origin_catalog_uuidv4"])
        return {
            "received_records": received,
            "rejected_records": invalid_values + len(rejected) + self.rejected_records,
            "admitted_records": admitted,
            "staged_records": self.db.execute(
                "SELECT count(*) FROM exchange_staging"
            ).fetchone()[0],
            "repository_uuidv4": unit["repository_uuidv4"],
        }

    def promote(self, origin_catalog_uuidv4=None):
        from repo_catalog.adapters.sqlite.current_resources import CurrentResources

        # Decoder value claims have a canonical byte-backed validation result.
        # A demonstrably false value cannot monopolize its typed decoder subject
        # or survive as a saved interpretation archive.
        self.db.execute(
            "UPDATE exchange_staging SET reason='missing_dependency' WHERE table_name IN ('git_commit_facts','git_text_facts','git_name_facts') AND reason='conflict:competing_variants'"
        )
        promoted = 0
        while True:
            changed = False
            rows = self.db.execute(
                "SELECT record_key,content_sha256,record_json,origin_catalog_uuidv4,repository_uuidv4 FROM exchange_staging WHERE reason NOT LIKE 'current_state:%' AND reason NOT LIKE 'conflict:%' AND reason NOT LIKE 'invalid:%' ORDER BY record_key"
            ).fetchall()
            for key, digest, text, origin, repository in rows:
                self.db.execute("SAVEPOINT exchange_record")
                before_mapping = self._resolve_key(key)
                try:
                    reason = self._admit(json.loads(text), origin, repository)
                    if reason and reason.startswith("deferred:"):
                        self.db.execute("RELEASE exchange_record")
                        if before_mapping is None:
                            changed = True
                        self.db.execute(
                            "UPDATE exchange_staging SET reason=? WHERE record_key=? AND content_sha256=?",
                            (reason, key, digest),
                        )
                        continue
                    if reason:
                        self.db.execute("ROLLBACK TO exchange_record")
                        self.db.execute("RELEASE exchange_record")
                        if reason == "invalid:git_decoder_value":
                            self.db.execute(
                                "DELETE FROM exchange_staging WHERE record_key=? AND content_sha256=?",
                                (key, digest),
                            )
                            self.rejected_records += 1
                            changed = True
                            continue
                        self.db.execute(
                            "UPDATE exchange_staging SET reason=? WHERE record_key=? AND content_sha256=?",
                            (reason, key, digest),
                        )
                        continue
                    self.db.execute(
                        "DELETE FROM exchange_staging WHERE record_key=? AND content_sha256=?",
                        (key, digest),
                    )
                    self.db.execute("RELEASE exchange_record")
                except (CatalogError, sqlite3.IntegrityError) as error:
                    self.db.execute("ROLLBACK TO exchange_record")
                    self.db.execute("RELEASE exchange_record")
                    reason = (
                        "missing_dependency"
                        if isinstance(error, CatalogError)
                        and error.code == "EXCHANGE_DEPENDENCY_MISSING"
                        else "invalid:domain_constraint"
                    )
                    self.db.execute(
                        "UPDATE exchange_staging SET reason=? WHERE record_key=? AND content_sha256=?",
                        (reason, key, digest),
                    )
                    continue
                changed = True
                promoted += 1
            promoted += CurrentResources(self.db).promote_staging()
            if "change_request_state" in self.columns:
                from repo_catalog.adapters.sqlite.current_api import CurrentApiState

                promoted += CurrentApiState(self.db).promote_staging()
            if not changed:
                break
        self.refresh_resolution_blocks()
        return promoted

    def refresh_resolution_blocks(self):
        """A contested proof blocks its claims, independently of resource use."""
        self.db.execute("DELETE FROM exchange_blocked_coverage_claims")
        repositories = [
            r[0]
            for r in self.db.execute(
                "SELECT DISTINCT repository_uuidv4 FROM exchange_staging WHERE reason LIKE 'conflict:%' OR reason LIKE 'current_state:conflict'"
            )
        ]
        if not repositories:
            return
        fields = tuple(self.columns["coverage_claims"])
        for raw in self.db.execute(
            "SELECT c.* FROM coverage_claims c JOIN coverage_scopes s USING(coverage_scope_id) WHERE s.repository_uuidv4 IN ("
            + ",".join("?" for _ in repositories)
            + ") AND c.coverage_state='complete' AND c.observed_at_us=(SELECT max(n.observed_at_us) FROM coverage_claims n WHERE n.coverage_scope_id=c.coverage_scope_id)",
            repositories,
        ):
            row = dict(zip(fields, raw, strict=True))
            proof = self.proof_requirements("coverage_claims", row)
            conflicted = proof is None or any(
                self.db.execute(
                    "SELECT 1 FROM exchange_staging WHERE record_key=? AND reason LIKE 'conflict:%'",
                    (key,),
                ).fetchone()
                for key in proof or ()
            )
            if conflicted:
                self.db.execute(
                    "INSERT OR IGNORE INTO exchange_blocked_coverage_claims VALUES(?)",
                    (row["coverage_claim_id"],),
                )
