import hashlib
import sqlite3
import time

from repo_catalog.domain.document import verify_text_body
from repo_catalog.domain.models import CancellationToken, CatalogError
from repo_catalog.domain.time import now_us


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


def refresh_documents(core_store, search_store_or_kind, kind_or_token, token=None):
    """Reconstruct disposable inputs from eligible domain text in core store into search store."""
    if token is None:
        kind = search_store_or_kind
        token = kind_or_token
        search_store = core_store.open_search(create=True)
    else:
        search_store = search_store_or_kind
        kind = kind_or_token

    if kind in {"code", "commits"}:
        from repo_catalog.application.git_query_context import decoded_fact

        table, object_type, field = (
            ("valid_git_text_facts", "blob", "raw_text")
            if kind == "code"
            else ("valid_git_commit_facts", "commit", "message_text")
        )

        def git_rows():
            for obj in core_store.execute(
                f"SELECT DISTINCT f.git_object_id FROM {table} f JOIN available_git_objects g USING(git_object_id) JOIN repository_object_sources s USING(git_object_id) ORDER BY git_object_id"
            ):
                token.check()
                result = decoded_fact(core_store, obj[0], object_type)
                if result["fact"] is not None and result["fact"][field] is not None:
                    yield {
                        "source_key": "git:" + str(obj[0]),
                        "body": result["fact"][field],
                    }

        rows = git_rows()
    elif kind == "pr":
        rows = core_store.execute(
            "SELECT lower(hex(b.sha256)) source_key,b.body,b.byte_length FROM text_bodies b "
            "WHERE b.sha256 IN (SELECT text_body_sha256 FROM eligible_document_state WHERE deleted=0 "
            "UNION SELECT text_body_sha256 FROM eligible_review_resources WHERE deleted=0) ORDER BY b.sha256"
        )
    elif kind == "issue":
        rows = core_store.execute(
            "SELECT lower(hex(b.sha256)) source_key,b.body,b.byte_length FROM text_bodies b "
            "WHERE b.sha256 IN (SELECT text_body_sha256 FROM eligible_issue_resources "
            "WHERE deleted=0) UNION SELECT NULL source_key,title body,NULL byte_length "
            "FROM eligible_issue_resources WHERE deleted=0 AND title IS NOT NULL"
        )
    else:
        raise CatalogError("INVALID_ARGUMENT", "Unknown index kind")

    batch = []
    batch_bytes = 0
    seen_keys = set()
    total_docs = 0
    total_bytes = 0
    for row in rows:
        token.check()
        body = (
            row["body"].decode("utf8", "replace")
            if isinstance(row["body"], bytes)
            else row["body"]
        )
        if kind in ("pr", "issue") and row["source_key"] is not None:
            verify_text_body(body, bytes.fromhex(row["source_key"]), row["byte_length"])
        row_bytes = len(body.encode("utf8"))
        key = row["source_key"] or hashlib.sha256(body.encode("utf8")).hexdigest()
        seen_keys.add(str(key))
        batch.append((str(key), body))
        batch_bytes += row_bytes
        total_docs += 1
        total_bytes += row_bytes
        if len(batch) == 200 or batch_bytes > 8_388_608:
            _save_documents(search_store, kind, batch)
            batch = []
            batch_bytes = 0
    if batch:
        _save_documents(search_store, kind, batch)

    with search_store.transaction():
        all_docs = search_store.all(
            "SELECT search_document_id, source_key FROM search_documents WHERE kind=?",
            (kind,),
        )
        obsolete_ids = [
            d["search_document_id"]
            for d in all_docs
            if d["source_key"] not in seen_keys
        ]
        for obs_id in obsolete_ids:
            if not search_store.one(
                "SELECT 1 FROM index_membership WHERE search_document_id=?",
                (obs_id,),
            ):
                search_store.execute(
                    "DELETE FROM search_documents WHERE search_document_id=?",
                    (obs_id,),
                )
    return total_docs, total_bytes


def _save_documents(search_store, kind, batch):
    with search_store.transaction():
        for key, body in batch:
            row = search_store.one(
                "SELECT search_document_id,body FROM search_documents WHERE kind=? AND source_key=?",
                (kind, key),
            )
            if row is None:
                search_store.execute(
                    "INSERT INTO search_documents(kind,source_key,body,metadata) VALUES(?,?,?,'{}')",
                    (kind, key, body),
                )
            elif row["body"] != body:
                search_store.execute(
                    "UPDATE search_documents SET body=? WHERE search_document_id=?",
                    (body, row["search_document_id"]),
                )


def rebuild(store, kind="all", token=None):
    token = token or CancellationToken()
    if not fts_available(store):
        raise CatalogError(
            "INDEX_UNAVAILABLE",
            "FTS5 trigram is unavailable or disabled; scan queries remain usable",
        )
    # PF-P17: Explicit index rebuild opens or initializes search DB
    search_store = store.open_search(create=True)
    started_at_us = now_us()
    start_time = time.monotonic()
    total_docs = 0
    total_bytes = 0
    results = []
    kinds = ("code", "pr", "issue", "commits") if kind == "all" else (kind,)
    try:
        for current in kinds:
            token.check()
            k_docs, k_bytes = refresh_documents(store, search_store, current, token)
            total_docs += k_docs
            total_bytes += k_bytes
            maximum = search_store.one(
                "SELECT coalesce(max(search_document_id),0) FROM search_documents WHERE kind=?",
                (current,),
            )[0]
            with search_store.transaction():
                ident = search_store.one(
                    "SELECT coalesce(max(index_generation_id),0)+1 FROM index_generations"
                )[0]
                table = f"catalog_fts_{ident}"
                search_store.execute(
                    "INSERT INTO index_generations(index_generation_id,kind,state,table_name,target_max_search_document_id,created_at_us) VALUES(?,?,?,?,?,?)",
                    (ident, current, "building", table, maximum, now_us()),
                )
                search_store.execute(
                    f"CREATE VIRTUAL TABLE {table} USING fts5(body, tokenize='trigram case_sensitive 1',content='',detail=full)"
                )
            last = 0
            count = 0
            while True:
                token.check()
                batch = []
                batch_bytes = 0
                for document in search_store.execute(
                    "SELECT * FROM search_documents WHERE kind=? AND search_document_id>? AND search_document_id<=? ORDER BY search_document_id LIMIT 200",
                    (current, last, maximum),
                ):
                    document_bytes = len(document["body"].encode("utf8"))
                    if batch and batch_bytes + document_bytes > 8_388_608:
                        break
                    batch.append(document)
                    batch_bytes += document_bytes
                if not batch:
                    break
                with search_store.transaction():
                    if (
                        search_store.one(
                            "SELECT state FROM index_generations WHERE index_generation_id=?",
                            (ident,),
                        )[0]
                        != "building"
                    ):
                        raise CatalogError(
                            "STALE_INDEX_JOB", "Index generation is no longer building"
                        )
                    for doc in batch:
                        if not search_store.one(
                            "SELECT 1 FROM index_membership WHERE index_generation_id=? AND search_document_id=?",
                            (ident, doc["search_document_id"]),
                        ):
                            search_store.execute(
                                f"INSERT INTO {table}(rowid,body) VALUES(?,?)",
                                (doc["search_document_id"], doc["body"]),
                            )
                            search_store.execute(
                                "INSERT INTO index_membership(index_generation_id,search_document_id,input_version) VALUES(?,?,?)",
                                (ident, doc["search_document_id"], "utf8-literal-v1"),
                            )
                    count += len(batch)
                    last = batch[-1]["search_document_id"]
            with search_store.transaction():
                expected = search_store.one(
                    "SELECT count(*) FROM search_documents WHERE kind=? AND search_document_id<=?",
                    (current, maximum),
                )[0]
                if count != expected:
                    raise CatalogError(
                        "INDEX_INTEGRITY", "Fixed index target not fully built"
                    )
                search_store.execute(
                    "UPDATE index_generations SET state='retired' WHERE kind=? AND state='ready'",
                    (current,),
                )
                search_store.execute(
                    "UPDATE index_generations SET state='ready' WHERE index_generation_id=?",
                    (ident,),
                )
            # Retired generations cleanup
            for old in search_store.all(
                "SELECT * FROM index_generations WHERE kind=? AND state='retired'",
                (current,),
            ):
                try:
                    with search_store.transaction():
                        search_store.execute(f"DROP TABLE {old['table_name']}")
                        search_store.execute(
                            "DELETE FROM index_membership WHERE index_generation_id=?",
                            (old["index_generation_id"],),
                        )
                        search_store.execute(
                            "UPDATE index_generations SET state='removed' WHERE index_generation_id=?",
                            (old["index_generation_id"],),
                        )
                except sqlite3.OperationalError:
                    pass
            results.append(
                {
                    "kind": current,
                    "generation": ident,
                    "documents": count,
                    "state": "ready",
                }
            )
        duration_ms = max(1, int((time.monotonic() - start_time) * 1000))
        ended_at_us = now_us()
        search_store.update_last_rebuilt(ended_at_us)
        # PF-P16: Measure update duration and record rebuild metrics in operational store
        store.operational.record_rebuild_metric(
            started_at_us=started_at_us,
            ended_at_us=ended_at_us,
            duration_ms=duration_ms,
            documents_indexed=total_docs,
            bytes_indexed=total_bytes,
            status="complete",
        )
        return results
    except Exception:
        duration_ms = max(1, int((time.monotonic() - start_time) * 1000))
        try:
            store.operational.record_rebuild_metric(
                started_at_us=started_at_us,
                ended_at_us=now_us(),
                duration_ms=duration_ms,
                documents_indexed=total_docs,
                bytes_indexed=total_bytes,
                status="failed",
            )
        except Exception:
            pass
        raise
