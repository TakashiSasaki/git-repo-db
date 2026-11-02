"""Search-owned derivative index; reads never create or repair an index."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from repo_catalog.adapters.sqlite.catalog_runtime import (
    SnapshotReadLimits,
    apply_snapshot_read_limits,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    SchemaError,
    configure,
    connect,
    initialize,
    register_functions,
    validate,
    verify_declared,
)
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.query_contracts import (
    QueryError,
    SnapshotFenceToken,
    canonical_json,
)
from repo_catalog.domain.search_query import SEARCH_PROJECTION_KINDS


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


def _open_index_read(path):
    # mode=ro closes the existence-check/open race without creating an empty DB.
    db = sqlite3.connect(
        Path(path).resolve().as_uri() + "?mode=ro",
        uri=True,
        isolation_level=None,
        cached_statements=0,
    )
    try:
        db.row_factory = sqlite3.Row
        register_functions(db, "search")
        apply_snapshot_read_limits(db, SnapshotReadLimits())
        configure(db, "search")
        verify_declared("search")
        validate(db, "search")
        return db
    except BaseException:
        db.close()
        raise


def _replace_projection_rows(db, projection_kind, snapshot_token, documents):
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


def _query_candidate_rows(
    db,
    projection_kind,
    snapshot_token,
    query_text,
    expected_doc_count=None,
    *,
    expected_identity,
):
    identities = db.execute(
        "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity WHERE store_role='search'"
    ).fetchall()
    if [tuple(row) for row in identities] != [expected_identity]:
        return None
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


class ProductionSearchAdapter:
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
            return _replace_projection_rows(
                db, projection_kind, snapshot_token, documents
            )

    def query_candidates(
        self, projection_kind, snapshot_token, query_text, expected_doc_count=None
    ):
        if projection_kind not in SEARCH_PROJECTION_KINDS:
            raise QueryError("INVALID_PROJECTION_KIND", "search", projection_kind)
        if not self.path.is_file():
            return None
        try:
            fence = SnapshotFenceToken.parse(snapshot_token)
            with closing(_open_index_read(self.path)) as db:
                db.execute("PRAGMA query_only=ON")
                db.execute("BEGIN")
                try:
                    return _query_candidate_rows(
                        db,
                        projection_kind,
                        snapshot_token,
                        query_text,
                        expected_doc_count,
                        expected_identity=(
                            fence.repository_uuidv4,
                            fence.catalog_instance_uuidv4,
                        ),
                    )
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
    def extract_git_metadata_documents(core):
        from repo_catalog.adapters.sqlite.search_core import (
            extract_git_metadata_documents,
        )

        return extract_git_metadata_documents(core)

    @staticmethod
    def extract_context_documents(context, *, evidence=None):
        from repo_catalog.adapters.sqlite.search_context import (
            extract_context_documents,
        )

        return extract_context_documents(context, evidence=evidence)
