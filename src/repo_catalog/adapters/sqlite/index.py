import hashlib
import sqlite3

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


def refresh_documents(store, kind, token):
    """Reconstruct disposable inputs from eligible domain text, including imports.

    Shared text storage can retain superseded bodies. It is not a search scope:
    only retained PR histories and admitted current resources supply inputs.
    """
    if kind == "code":
        rows = store.execute(
            "SELECT git_fact_uuidv4 source_key,raw_text body FROM current_git_text_facts WHERE raw_text IS NOT NULL ORDER BY git_fact_uuidv4"
        )
    elif kind == "commits":
        rows = store.execute(
            "SELECT git_fact_uuidv4 source_key,message_text body FROM current_git_commits ORDER BY git_fact_uuidv4"
        )
    elif kind == "pr":
        rows = store.execute(
            "SELECT lower(hex(b.sha256)) source_key,b.body,b.byte_length FROM text_bodies b "
            "WHERE b.sha256 IN (SELECT o.text_body_sha256 FROM document_observations o "
            "JOIN usable_parsed_results r USING(parsed_result_uuidv4) "
            "UNION SELECT text_body_sha256 FROM eligible_review_resources WHERE deleted=0) "
            "ORDER BY b.sha256"
        )
    elif kind == "issue":
        rows = store.execute(
            "SELECT lower(hex(b.sha256)) source_key,b.body,b.byte_length FROM text_bodies b "
            "WHERE b.sha256 IN (SELECT text_body_sha256 FROM eligible_issue_resources "
            "WHERE deleted=0) UNION SELECT NULL source_key,title body,NULL byte_length "
            "FROM eligible_issue_resources WHERE deleted=0 AND title IS NOT NULL"
        )
    else:
        raise CatalogError("INVALID_ARGUMENT", "Unknown index kind")
    batch = []
    batch_bytes = 0
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
        if batch and (len(batch) == 200 or batch_bytes + row_bytes > 8_388_608):
            _save_documents(store, kind, batch)
            batch = []
            batch_bytes = 0
        key = row["source_key"] or hashlib.sha256(body.encode("utf8")).hexdigest()
        batch.append((str(key), body))
        batch_bytes += row_bytes
    if batch:
        _save_documents(store, kind, batch)


def _save_documents(store, kind, batch):
    with store.transaction():
        for key, body in batch:
            row = store.one(
                "SELECT search_document_id,body FROM search_documents WHERE kind=? AND source_key=?",
                (kind, key),
            )
            if row is None:
                store.execute(
                    "INSERT INTO search_documents(kind,source_key,body,metadata) VALUES(?,?,?,'{}')",
                    (kind, key, body),
                )
            elif row["body"] != body:
                store.execute(
                    "UPDATE search_documents SET body=? WHERE search_document_id=?",
                    (body, row["search_document_id"]),
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
    for current in ("code", "pr", "issue", "commits") if kind == "all" else (kind,):
        token.check()
        refresh_documents(s, current, token)
        selected = {
            "code": "source_key IN (SELECT git_fact_uuidv4 FROM current_git_text_facts WHERE raw_text IS NOT NULL)",
            "commits": "source_key IN (SELECT git_fact_uuidv4 FROM current_git_commits)",
            "pr": "source_key IN (SELECT lower(hex(o.text_body_sha256)) FROM document_observations o JOIN usable_parsed_results r USING(parsed_result_uuidv4) UNION SELECT lower(hex(text_body_sha256)) FROM eligible_review_resources WHERE deleted=0)",
            "issue": "source_key IN (SELECT lower(hex(text_body_sha256)) FROM eligible_issue_resources WHERE deleted=0) OR EXISTS (SELECT 1 FROM eligible_issue_resources i WHERE i.deleted=0 AND i.title=search_documents.body)",
        }[current]
        selected = "(" + selected + ")"
        maximum = s.one(
            f"SELECT coalesce(max(search_document_id),0) FROM search_documents WHERE kind=? AND {selected}",
            (current,),
        )[0]
        with s.transaction():
            ident = s.one(
                "SELECT coalesce(max(index_generation_id),0)+1 FROM index_generations"
            )[0]
            table = f"catalog_fts_{ident}"
            s.execute(
                "INSERT INTO index_generations(index_generation_id,kind,state,table_name,target_max_search_document_id,created_at_us) VALUES(?,?,?,?,?,?)",
                (ident, current, "building", table, maximum, now_us()),
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
                f"SELECT * FROM search_documents WHERE kind=? AND {selected} AND search_document_id>? AND search_document_id<=? ORDER BY search_document_id LIMIT 200",
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
                    s.one(
                        "SELECT state FROM index_generations WHERE index_generation_id=?",
                        (ident,),
                    )[0]
                    != "building"
                ):
                    raise CatalogError(
                        "STALE_INDEX_JOB", "Index generation is no longer building"
                    )
                for doc in batch:
                    if not s.one(
                        "SELECT 1 FROM index_membership WHERE index_generation_id=? AND search_document_id=?",
                        (ident, doc["search_document_id"]),
                    ):
                        s.execute(
                            f"INSERT INTO {table}(rowid,body) VALUES(?,?)",
                            (doc["search_document_id"], doc["body"]),
                        )
                        s.execute(
                            "INSERT INTO index_membership(index_generation_id,search_document_id,input_version) VALUES(?,?,?)",
                            (ident, doc["search_document_id"], "utf8-literal-v1"),
                        )
                count += len(batch)
                last = batch[-1]["search_document_id"]
        with s.transaction():
            expected = s.one(
                f"SELECT count(*) FROM search_documents WHERE kind=? AND {selected} AND search_document_id<=?",
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
            s.execute(
                "UPDATE index_generations SET state='ready' WHERE index_generation_id=?",
                (ident,),
            )
        # Retired generations remain until explicit maintenance can obtain SQLite's DDL lock.
        for old in s.all(
            "SELECT * FROM index_generations WHERE kind=? AND state='retired'",
            (current,),
        ):
            try:
                with s.transaction():
                    s.execute(f"DROP TABLE {old['table_name']}")
                    s.execute(
                        "DELETE FROM index_membership WHERE index_generation_id=?",
                        (old["index_generation_id"],),
                    )
                    s.execute(
                        "UPDATE index_generations SET state='removed' WHERE index_generation_id=?",
                        (old["index_generation_id"],),
                    )
            except sqlite3.OperationalError:
                pass
        # Obsolete current-resource bodies can remain in shared domain storage,
        # but need not survive as duplicate disposable search inputs. Keep any
        # row still referenced by a generation whose DDL lock was unavailable.
        with s.transaction():
            s.execute(
                f"DELETE FROM search_documents WHERE kind=? AND NOT {selected} "
                "AND NOT EXISTS(SELECT 1 FROM index_membership m "
                "WHERE m.search_document_id=search_documents.search_document_id)",
                (current,),
            )
        results.append(
            {"kind": current, "generation": ident, "documents": count, "state": "ready"}
        )
    return results
