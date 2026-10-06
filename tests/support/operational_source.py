"""Synthetic operational v2 fixtures prepared outside the converter guard."""

import sqlite3
from pathlib import Path

from tests.support.legacy_v2 import initialize

STAMP = "2026-01-01T00:00:00Z"


def add_operational_indexes(
    database, *, kinds=("code",), analyze=False, documents=3, partial=False
):
    """Add real app-generated FTS, including to the malformed P2 fixture.

    Replaces only synthetic search/index fixture rows before generating new
    ones; all other acquisition facts and deliberately invalid values remain.
    """
    database = Path(database)
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("DELETE FROM index_membership")
        db.execute("DELETE FROM index_generations")
        db.execute("DELETE FROM search_documents")
        for kind in ("code", "pr", "commits"):
            for number in range(documents):
                db.execute(
                    "INSERT INTO search_documents(kind,source_key,body,metadata) VALUES(?,?,?,?)",
                    (
                        kind,
                        f"synthetic-{kind}-{number}",
                        f"Original Abc {kind} {number} 日本語",
                        "{}",
                    ),
                )
        for ident, kind in enumerate(kinds, 1):
            table = f"catalog_fts_{ident}"
            maximum = db.execute(
                "SELECT coalesce(max(id),0) FROM search_documents WHERE kind=?", (kind,)
            ).fetchone()[0]
            db.execute(
                "INSERT INTO index_generations VALUES(?,?,?,?,?,?)",
                (
                    ident,
                    kind,
                    "building" if partial else "ready",
                    table,
                    maximum,
                    STAMP,
                ),
            )
            db.execute(
                f"CREATE VIRTUAL TABLE {table} USING fts5(body, tokenize='trigram case_sensitive 1',content='',detail=full)"
            )
            rows = db.execute(
                "SELECT id,body FROM search_documents WHERE kind=? AND id<=? ORDER BY id",
                (kind, maximum),
            ).fetchall()
            for row in rows[:200] if partial else rows:
                db.execute(f"INSERT INTO {table}(rowid,body) VALUES(?,?)", row)
                db.execute(
                    "INSERT INTO index_membership VALUES(?,?,?)",
                    (ident, row[0], "utf8-literal-v1"),
                )
        if analyze:
            db.execute("ANALYZE")


def make_operational_source(
    state_dir, *, kinds=(), analyze=False, documents=3, partial=False
):
    state_dir = Path(state_dir)
    database, cache = initialize(state_dir)
    add_operational_indexes(
        database, kinds=kinds, analyze=analyze, documents=documents, partial=partial
    )
    (cache / "synthetic-evidence").write_bytes(b"synthetic-cache-original")
    return database, cache
