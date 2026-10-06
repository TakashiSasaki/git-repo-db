import sqlite3

from repo_catalog.domain.models import CancellationToken, CatalogError, now


def fts_available(store):
    if store.config["search"]["backend"] == "scan":
        return False
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA recursive_triggers=ON")
    try:
        c.execute(
            "CREATE VIRTUAL TABLE f USING fts5(body, tokenize='trigram case_sensitive 1',content='',detail=full)"
        )
        return True
    except sqlite3.Error:
        return False
    finally:
        c.close()


def refresh_documents(store, kind, token):
    """Reconstruct disposable search inputs from catalog originals, including imports."""
    if kind == "code":
        rows = store.execute(
            "SELECT id source_key,raw_text body FROM contents WHERE raw_text IS NOT NULL ORDER BY id"
        )
    elif kind == "commits":
        rows = store.execute(
            "SELECT object_id source_key,raw_message body FROM commits ORDER BY object_id"
        )
    else:
        rows = store.execute(
            "SELECT v.id source_key,b.body FROM document_versions v JOIN text_bodies b ON b.id=v.body_id ORDER BY v.id"
        )
    batch = []
    batch_bytes = 0
    for row in rows:
        token.check()
        body = (
            row["body"].decode("utf8", "replace")
            if isinstance(row["body"], bytes)
            else row["body"]
        )
        row_bytes = len(body.encode("utf8"))
        if batch and (len(batch) == 200 or batch_bytes + row_bytes > 8_388_608):
            _save_documents(store, kind, batch)
            batch = []
            batch_bytes = 0
        batch.append((str(row["source_key"]), body))
        batch_bytes += row_bytes
    if batch:
        _save_documents(store, kind, batch)


def _save_documents(store, kind, batch):
    with store.transaction():
        for key, body in batch:
            row = store.one(
                "SELECT id,body FROM search_documents WHERE kind=? AND source_key=?",
                (kind, key),
            )
            if row is None:
                store.execute(
                    "INSERT INTO search_documents(kind,source_key,body,metadata) VALUES(?,?,?,'{}')",
                    (kind, key, body),
                )
            elif row["body"] != body:
                store.execute(
                    "UPDATE search_documents SET body=? WHERE id=?", (body, row["id"])
                )


def rebuild(store, kind, token=None):
    s = store
    token = token or CancellationToken()
    if not fts_available(s):
        raise CatalogError(
            "INDEX_UNAVAILABLE",
            "FTS5 trigram is unavailable or disabled; scan queries remain usable",
        )
    results = []
    for current in ("code", "pr", "commits") if kind == "all" else (kind,):
        token.check()
        refresh_documents(s, current, token)
        maximum = s.one(
            "SELECT coalesce(max(id),0) FROM search_documents WHERE kind=?", (current,)
        )[0]
        with s.transaction():
            ident = s.one("SELECT coalesce(max(id),0)+1 FROM index_generations")[0]
            table = f"catalog_fts_{ident}"
            s.execute(
                "INSERT INTO index_generations VALUES(?,?,?,?,?,?)",
                (ident, current, "building", table, maximum, now()),
            )
            s.execute(
                f"CREATE VIRTUAL TABLE {table} USING fts5(body, tokenize='trigram case_sensitive 1',content='',detail=full)"
            )
        last = 0
        count = 0
        while True:
            token.check()
            batch = []
            batch_bytes = 0
            for document in s.execute(
                "SELECT * FROM search_documents WHERE kind=? AND id>? AND id<=? ORDER BY id LIMIT 200",
                (current, last, maximum),
            ):
                document_bytes = len(document["body"].encode("utf8"))
                if batch and batch_bytes + document_bytes > 8_388_608:
                    break
                batch.append(document)
                batch_bytes += document_bytes
            if not batch:
                break
            with s.transaction():
                if (
                    s.one("SELECT state FROM index_generations WHERE id=?", (ident,))[0]
                    != "building"
                ):
                    raise CatalogError(
                        "STALE_INDEX_JOB", "Index generation is no longer building"
                    )
                for doc in batch:
                    if not s.one(
                        "SELECT 1 FROM index_membership WHERE generation_id=? AND document_id=?",
                        (ident, doc["id"]),
                    ):
                        s.execute(
                            f"INSERT INTO {table}(rowid,body) VALUES(?,?)",
                            (doc["id"], doc["body"]),
                        )
                        s.execute(
                            "INSERT INTO index_membership VALUES(?,?,?)",
                            (ident, doc["id"], "utf8-literal-v1"),
                        )
                count += len(batch)
                last = batch[-1]["id"]
        with s.transaction():
            expected = s.one(
                "SELECT count(*) FROM search_documents WHERE kind=? AND id<=?",
                (current, maximum),
            )[0]
            if count != expected:
                raise CatalogError(
                    "INDEX_INTEGRITY", "Fixed index target not fully built"
                )
            s.execute(
                "UPDATE index_generations SET state='retired' WHERE kind=? AND state='ready'",
                (current,),
            )
            s.execute("UPDATE index_generations SET state='ready' WHERE id=?", (ident,))
        # Retired generations remain until explicit maintenance can obtain SQLite's DDL lock.
        for old in s.all(
            "SELECT * FROM index_generations WHERE kind=? AND state='retired'",
            (current,),
        ):
            try:
                with s.transaction():
                    s.execute(f"DROP TABLE {old['table_name']}")
                    s.execute(
                        "DELETE FROM index_membership WHERE generation_id=?",
                        (old["id"],),
                    )
                    s.execute(
                        "UPDATE index_generations SET state='removed' WHERE id=?",
                        (old["id"],),
                    )
            except sqlite3.OperationalError:
                pass
        results.append(
            {"kind": current, "generation": ident, "documents": count, "state": "ready"}
        )
    return results
