"""Production derivative Search adapter over `search.sqlite3` (`search_projections`, `search_documents`).

Key invariants enforced:
1. Restricted strictly to `projection_kind IN ('git_metadata', 'notes', 'context_text')`.
   Ordinary file blobs (`native_type == 'blob'` outside proven/reported Notes) are
   never indexed into `search.sqlite3`.
2. Every projection row and document row is pinned to an exact canonical
   `snapshot_token_json`.
3. Any missing file, schema mismatch, lock, truncation, corrupt SQLite page
   (`sqlite3.DatabaseError`), stale token, or structural inconsistency in
   `search.sqlite3` cleanly returns `None` from candidate lookup so the caller
   falls back to `authority_scan`.
4. Derivative `search.sqlite3` failures NEVER write `p1-recovery-stop.json`.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import (
    SnapshotReadLimits,
    apply_snapshot_read_limits,
)
from repo_catalog.adapters.sqlite.p1_schema import SchemaError, connect, initialize
from repo_catalog.domain.p1_context import FieldCandidate, FieldClock, ResourceKey
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import OID, Capture, GitObservation, Provenance
from repo_catalog.domain.production_query import (
    SEARCH_PROJECTION_KINDS,
    QueryError,
    SnapshotFenceToken,
    canonical_json,
    provider_role_summary,
    repository_relation_summary,
)


class BoundedDocuments(dict):
    """Finite derivative working set, checked before retaining each document."""

    max_documents = 10000
    max_document_bytes = 1024 * 1024
    max_total_bytes = 16 * 1024 * 1024

    def __init__(self):
        super().__init__()
        self.total_bytes = 0

    def __setitem__(self, key, value):
        size = len(key.encode("utf-8")) + len(value.encode("utf-8"))
        old = self.get(key)
        replaced = (
            0 if old is None else len(key.encode("utf-8")) + len(old.encode("utf-8"))
        )
        total = self.total_bytes - replaced + size
        if (
            size > self.max_document_bytes
            or total > self.max_total_bytes
            or (key not in self and len(self) >= self.max_documents)
        ):
            raise QueryError(
                "QUERY_BUDGET", "search", "derivative document working-set limit"
            )
        super().__setitem__(key, value)
        self.total_bytes = total


class ProductionSearchAdapter:
    """Disposable candidate index adapter over `search.sqlite3`."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.path = self.directory / "search.sqlite3"

    def ensure_store(
        self, repository_uuidv4: str, catalog_instance_uuidv4: str
    ) -> Path:
        """Initialize `search.sqlite3` if absent, or recreate if corrupt."""
        if not self.path.exists():
            initialize(
                self.path,
                "search",
                repository_uuidv4,
                catalog_instance_uuidv4,
            )
            return self.path
        try:
            with closing(connect(self.path, "search")) as db:
                row = db.execute(
                    "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity WHERE store_role='search'"
                ).fetchone()
                if row is None or (row[0], row[1]) != (
                    repository_uuidv4,
                    catalog_instance_uuidv4,
                ):
                    raise SchemaError("search store identity mismatch")
        except (sqlite3.DatabaseError, SchemaError, OSError):
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(str(self.path) + suffix)
                if candidate.exists():
                    candidate.unlink()
            initialize(
                self.path,
                "search",
                repository_uuidv4,
                catalog_instance_uuidv4,
            )
        return self.path

    def replace_projection(
        self,
        projection_kind: str,
        snapshot_token: str,
        documents: dict[str, str],
        *,
        repository_uuidv4: str | None = None,
        catalog_instance_uuidv4: str | None = None,
    ) -> int:
        """Atomically replace one projection kind for the given snapshot token."""
        if projection_kind not in SEARCH_PROJECTION_KINDS:
            raise QueryError("INVALID_PROJECTION_KIND", "search", projection_kind)
        parsed_token = SnapshotFenceToken.parse(snapshot_token)
        repo_id = repository_uuidv4 or parsed_token.repository_uuidv4
        inst_id = catalog_instance_uuidv4 or parsed_token.catalog_instance_uuidv4
        self.ensure_store(repo_id, inst_id)
        with closing(connect(self.path, "search")) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute(
                    "DELETE FROM search_documents WHERE projection_kind=?",
                    (projection_kind,),
                )
                db.execute(
                    "DELETE FROM search_projections WHERE projection_kind=?",
                    (projection_kind,),
                )
                db.execute(
                    "INSERT INTO search_projections VALUES(?,?)",
                    (projection_kind, snapshot_token),
                )
                if documents:
                    db.executemany(
                        "INSERT INTO search_documents VALUES(?,?,?,?)",
                        [
                            (projection_kind, snapshot_token, doc_key, text)
                            for doc_key, text in sorted(documents.items())
                        ],
                    )
                db.commit()
            except BaseException:
                if db.in_transaction:
                    db.rollback()
                raise
        return len(documents)

    def query_candidates(
        self,
        projection_kind: str,
        snapshot_token: str,
        query_text: str,
        expected_doc_count: int | None = None,
    ) -> dict[str, str] | None:
        """Query candidate `(document_key_json -> searchable_text)` rows at `snapshot_token`.

        Returns `None` on any missing/stale/incomplete/corrupt state so the caller
        transparently falls back to `authority_scan` without stopping the catalog.
        """
        if projection_kind not in SEARCH_PROJECTION_KINDS:
            raise QueryError("INVALID_PROJECTION_KIND", "search", projection_kind)
        if not self.path.is_file():
            return None
        try:
            with closing(connect(self.path, "search")) as db:
                db.execute("PRAGMA query_only=ON")
                db.execute("BEGIN")
                try:
                    apply_snapshot_read_limits(db, SnapshotReadLimits())
                    # SQLite can report encoded BLOB length without decoding or
                    # materializing malicious derivative TEXT into Python.
                    oversize = db.execute(
                        "SELECT 1 FROM search_documents WHERE "
                        "length(CAST(document_key_json AS BLOB)) + length(CAST(searchable_text AS BLOB)) > ? LIMIT 1",
                        (BoundedDocuments.max_document_bytes,),
                    ).fetchone()
                    if oversize is not None:
                        return None
                    proj_rows = db.execute(
                        "SELECT snapshot_token_json FROM search_projections WHERE projection_kind=?",
                        (projection_kind,),
                    ).fetchall()
                    if len(proj_rows) != 1 or proj_rows[0][0] != snapshot_token:
                        return None
                    # Verify no documents exist with a mismatched token for this kind
                    mismatched = db.execute(
                        "SELECT 1 FROM search_documents WHERE projection_kind=? AND snapshot_token_json<>? LIMIT 1",
                        (projection_kind, snapshot_token),
                    ).fetchone()
                    if mismatched is not None:
                        return None
                    if expected_doc_count is not None:
                        total_docs = db.execute(
                            "SELECT count(*) FROM search_documents WHERE projection_kind=? AND snapshot_token_json=?",
                            (projection_kind, snapshot_token),
                        ).fetchone()[0]
                        if total_docs != expected_doc_count:
                            return None
                    rows = db.execute(
                        "SELECT document_key_json,searchable_text FROM search_documents "
                        "WHERE projection_kind=? AND snapshot_token_json=? AND instr(searchable_text,?)>0 "
                        "ORDER BY document_key_json",
                        (projection_kind, snapshot_token, query_text),
                    )
                    result: dict[str, str] = BoundedDocuments()
                    for key_json, text_val in rows:
                        parsed_key = json.loads(key_json)
                        if (
                            not isinstance(parsed_key, list)
                            or canonical_json(parsed_key) != key_json
                            or not isinstance(text_val, str)
                        ):
                            return None
                        result[key_json] = text_val
                    return result
                finally:
                    if db.in_transaction:
                        db.rollback()
        except (
            sqlite3.DatabaseError,
            SchemaError,
            ValueError,
            TypeError,
            OSError,
            CoordinationError,
            RecursionError,
        ):
            return None

    @staticmethod
    def extract_git_metadata_documents(
        core: GitCore,
    ) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
        """Extract searchable `git_metadata` documents and summaries from a pinned `GitCore`.

        Indexes commit/tag messages, author/committer/tagger identities, tag names,
        ref observations, and decoded tree entry names. Strictly excludes ordinary
        file blobs (`type == 'blob'`).
        """
        documents: dict[str, str] = BoundedDocuments()
        summaries: dict[str, dict[str, object]] = {}

        # 1. Inspect git_objects and their scalar/relation claims
        obj_rows = core.sql(
            "SELECT object_format,full_oid FROM git_objects ORDER BY object_format,full_oid"
        )
        for row in obj_rows:
            oid = OID(row[0], row[1])
            type_proj = core.scalar(oid, "type")
            known_types = {
                alt["value"][1]
                for alt in type_proj.alternatives
                if isinstance(alt["value"], list)
                and len(alt["value"]) == 2
                and alt["value"][0] == "known"
            }
            canonical_type = (
                type_proj.canonical[1]
                if isinstance(type_proj.canonical, list)
                and len(type_proj.canonical) == 2
                and type_proj.canonical[0] == "known"
                else None
            )
            # Strictly exclude ordinary file blobs
            if canonical_type == "blob" or (known_types == {"blob"}):
                continue

            # Scalar text fields for commit/tag/metadata
            for field in (
                "message",
                "author",
                "author_name",
                "author_email",
                "committer",
                "committer_name",
                "committer_email",
                "tag_name",
                "tagger",
                "decoded_name",
            ):
                proj = core.scalar(oid, field)
                for alt in proj.alternatives:
                    val = alt["value"]
                    if (
                        isinstance(val, list)
                        and len(val) == 2
                        and val[0] == "known"
                        and isinstance(val[1], str)
                        and val[1]
                    ):
                        prov_json = canonical_json(alt["provenance"])
                        doc_key = canonical_json(
                            [
                                "scalar",
                                oid.object_format,
                                oid.full_oid,
                                field,
                                prov_json,
                            ]
                        )
                        documents[doc_key] = val[1]
                        summaries[doc_key] = {
                            "checked": alt["checked"],
                            "field": field,
                            "full_oid": oid.full_oid,
                            "kind": "scalar",
                            "native_type": canonical_type,
                            "object_format": oid.object_format,
                            "provenance": alt["provenance"],
                        }

            # Tree entry names (decoded from hex)
            tree_proj = core.relations(oid, "tree_entries")
            for alt in tree_proj.alternatives:
                prov_json = canonical_json(alt["provenance"])
                for member in alt["membership"]:
                    coord, target_fmt, target_oid = member
                    mode, name_hex = coord[0], coord[1]
                    decoded_name = bytes.fromhex(name_hex).decode(
                        "utf-8", "backslashreplace"
                    )
                    doc_key = canonical_json(
                        [
                            "tree_entry",
                            oid.object_format,
                            oid.full_oid,
                            name_hex,
                            target_oid,
                            prov_json,
                        ]
                    )
                    documents[doc_key] = decoded_name
                    summaries[doc_key] = {
                        "checked": alt["checked"],
                        "entry_mode": mode,
                        "entry_name": decoded_name,
                        "full_oid": oid.full_oid,
                        "kind": "tree_entry",
                        "object_format": oid.object_format,
                        "target_oid": [target_fmt, target_oid],
                    }

        # 2. Ref observations
        obs_rows = core.sql(
            "SELECT capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,kind,scope,value,provenance "
            "FROM git_observations WHERE kind='ref' "
            "ORDER BY capture_origin_uuidv4,capture_uuidv4,scope,provenance"
        )
        for row in obs_rows:
            observation = GitObservation(
                row[0],
                row[1],
                row[2],
                row[3],
                tuple(json.loads(row[4])),
                json.loads(row[5]),
                Provenance(*json.loads(row[6])),
            )
            value = observation.value
            ref_name = value.get("ref")
            if isinstance(ref_name, str) and ref_name:
                doc_key = canonical_json(
                    [
                        "ref_observation",
                        row[0],
                        row[1],
                        ref_name,
                        row[6],
                    ]
                )
                target = value.get("target")
                searchable = (
                    f"{ref_name} {target[1]}"
                    if isinstance(target, list) and len(target) == 2
                    else ref_name
                )
                documents[doc_key] = searchable
                summaries[doc_key] = {
                    "capture_origin_uuidv4": row[0],
                    "capture_uuidv4": row[1],
                    "kind": "ref_observation",
                    "observed_at_us": value.get("observed_at_us"),
                    "ref": ref_name,
                    "target": target,
                }

        return documents, summaries

    @staticmethod
    def extract_notes_documents(
        core: GitCore,
    ) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
        """Extract searchable `notes` documents and summaries from a pinned `GitCore`.

        Indexes retained note text (verified via `core.read_note`) and note target/capture
        mappings.
        """
        documents: dict[str, str] = BoundedDocuments()
        summaries: dict[str, dict[str, object]] = {}

        cap_rows = core.sql(
            "SELECT capture_origin_uuidv4,capture_uuidv4,repository_uuidv4,source,ref,object_format,root "
            "FROM captures ORDER BY capture_origin_uuidv4,capture_uuidv4"
        )
        for crow in cap_rows:
            raw_ref = bytes.fromhex(json.loads(crow[4])[1]).decode(
                "utf-8", "backslashreplace"
            )
            capture = Capture(
                crow[0],
                crow[1],
                crow[2],
                crow[3],
                raw_ref,
                OID(crow[5], crow[6]),
            )
            fmt = capture.root.object_format
            targets: set[str] = set()
            for r in core.sql(
                "SELECT DISTINCT target FROM notes_claims WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                capture.pair,
            ):
                targets.add(r[0])
            for r in core.sql(
                "SELECT DISTINCT target FROM note_roles WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                capture.pair,
            ):
                targets.add(r[0])
            for r in core.sql(
                "SELECT membership FROM notes_groups WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                capture.pair,
            ):
                for m in json.loads(r[0]):
                    targets.add(m[0])

            for target_hex in sorted(targets):
                target_oid = OID(fmt, target_hex)
                proj = core.notes_projection(capture, target_oid)
                note_oids: set[OID] = set()
                if proj.canonical is not None:
                    note_oids.add(proj.canonical)
                for alt in proj.alternatives:
                    if alt.note is not None:
                        note_oids.add(alt.note)

                for note_oid in sorted(note_oids):
                    body_text = ""
                    retained = False
                    has_retained = bool(
                        core.sql(
                            "SELECT 1 FROM retained_notes n JOIN note_roles r "
                            "ON r.object_format=n.object_format AND r.note=n.full_oid "
                            "WHERE r.capture_origin_uuidv4=? AND r.capture_uuidv4=? "
                            "AND r.object_format=? AND r.target=? AND r.note=? LIMIT 1",
                            (
                                *capture.pair,
                                fmt,
                                target_oid.full_oid,
                                note_oid.full_oid,
                            ),
                        )
                    )
                    if has_retained:
                        raw_bytes = core.read_note(capture, target_oid, note_oid)
                        body_text = raw_bytes.decode("utf-8", "backslashreplace")
                        retained = True
                    searchable = (
                        f"{capture.ref} {target_oid.full_oid} {note_oid.full_oid} {body_text}"
                        if body_text
                        else f"{capture.ref} {target_oid.full_oid} {note_oid.full_oid}"
                    )
                    doc_key = canonical_json(
                        [
                            capture.capture_origin_uuidv4,
                            capture.capture_uuidv4,
                            fmt,
                            target_oid.full_oid,
                            note_oid.full_oid,
                        ]
                    )
                    documents[doc_key] = searchable
                    summaries[doc_key] = {
                        "capture_origin_uuidv4": capture.capture_origin_uuidv4,
                        "capture_uuidv4": capture.capture_uuidv4,
                        "canonical": proj.canonical == note_oid,
                        "note_oid": [fmt, note_oid.full_oid],
                        "note_retained": retained,
                        "note_text": body_text if retained else None,
                        "ref": capture.ref,
                        "role_verified": proj.canonical is not None,
                        "target_oid": [fmt, target_oid.full_oid],
                    }

        return documents, summaries

    @staticmethod
    def extract_context_documents(
        context,
        *,
        evidence=None,
    ) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
        """Extract searchable `context_text` documents and summaries from a pinned Context snapshot.

        Resolves `text_body_sha256` via the verification-aware `read_verified_text`
        callable, and indexes current string `field_candidates` while excluding explicit
        JSON `"null"`.
        """
        context._validate_stage()
        documents: dict[str, str] = BoundedDocuments()
        summaries: dict[str, dict[str, object]] = {}

        rows = context.db.execute(
            "SELECT service_instance_uuidv4,resource_kind,provider_resource_id,field_name,"
            "clock_json,value_json,provenance_json,observed_at_us "
            "FROM field_candidates "
            "ORDER BY service_instance_uuidv4,resource_kind,provider_resource_id,field_name,clock_json,value_json,provenance_json"
        ).fetchall()
        for row in rows:
            (
                service_id,
                r_kind,
                r_id,
                field_name,
                clock_json,
                value_json,
                prov_json,
                obs_at,
            ) = row
            parsed_clock = json.loads(clock_json)
            clock = FieldClock(parsed_clock["domain"], parsed_clock["at_us"])
            if clock.encode() != clock_json:
                raise ValueError("invalid stored canonical clock")
            FieldCandidate(
                ResourceKey(service_id, r_kind, r_id),
                field_name,
                value_json,
                clock,
                prov_json,
                obs_at,
            )
            decoded_val = json.loads(value_json)
            if decoded_val is None:
                continue
            if field_name == "text_body_sha256":
                if not isinstance(decoded_val, str):
                    continue
                text_val = context.read_text(decoded_val)
            elif isinstance(decoded_val, str):
                text_val = decoded_val
            else:
                continue

            doc_key = canonical_json(
                [
                    service_id,
                    r_kind,
                    r_id,
                    field_name,
                    clock_json,
                    value_json,
                    prov_json,
                ]
            )
            documents[doc_key] = text_val
            summaries[doc_key] = {
                "clock": json.loads(clock_json),
                "field_name": field_name,
                "observed_at_us": obs_at,
                "provenance": json.loads(prov_json),
                "provider_resource_id": r_id,
                "resource_kind": r_kind,
                "service_instance_uuidv4": service_id,
                "repository_roles": [
                    provider_role_summary(role)
                    for role in context.provider_repository_roles(
                        ResourceKey(service_id, r_kind, r_id), evidence=evidence
                    )
                ],
            }

        for resource in context.resources():
            for role in context.provider_repository_roles(resource, evidence=evidence):
                key = canonical_json(
                    [
                        "provider_repository_role",
                        *resource.coordinates(),
                        role.scope.relation_kind,
                        canonical_json(role.scope.to_dict()),
                        role.provenance_json,
                    ]
                )
                targets = (
                    role.mapping.active_repository_uuidv4s
                    if role.mapping is not None
                    else ()
                )
                documents[key] = " ".join(
                    (
                        role.scope.relation_kind,
                        role.scope.provider_repository_id or "null",
                        *targets,
                    )
                )
                summaries[key] = {
                    "kind": "current_provider_repository_role",
                    **provider_role_summary(role),
                }
            for relation in context.repository_relations(resource, evidence=evidence):
                key = canonical_json(
                    ["repository_relation", *relation.claim_key.coordinates()]
                )
                documents[key] = " ".join(
                    (
                        relation.relation_kind,
                        relation.relation.target_repository_uuidv4 or "null",
                    )
                )
                summaries[key] = {
                    "kind": "stored_core_target_relation",
                    **repository_relation_summary(relation),
                }

        return documents, summaries
