"""Catalog3 structural contracts in isolated synthetic SQLite databases."""

import hashlib
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.schema import schema_sql


def construct(sql=None):
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(sql or schema_sql())
    return db


H = b"h" * 20
B = b"b" * 20
TIME = "2026-10-05T12:00:00Z"


def put(db, table, **values):
    names = ",".join(values)
    db.execute(
        f"INSERT INTO {table}({names}) VALUES({','.join('?' for _ in values)})",
        tuple(values.values()),
    )


def build_target(sql=None):
    """Seed a synthetic fixture using the complete DDL, optionally a review blob."""
    db = construct(sql)
    put(
        db,
        "service_instances",
        service_instance_uuidv4="00000000-0000-4000-8000-000000000101",
        service_kind="github",
        name="fixture",
        metadata="{}",
    )
    put(
        db,
        "sources",
        source_id="source",
        service_instance_uuidv4="00000000-0000-4000-8000-000000000101",
        discovery_kind="github_inventory",
        name="fixture",
        settings="{}",
    )
    for index, repo in enumerate(("a", "b"), 1):
        put(db, "repositories", repository_id=repo, name=repo, metadata="{}")
        put(
            db,
            "repository_bindings",
            repository_binding_id="binding-" + repo,
            repository_id=repo,
            service_instance_uuidv4="00000000-0000-4000-8000-000000000101",
            provider_repository_id=repo,
            metadata="{}",
        )
        put(
            db,
            "repository_endpoints",
            repository_endpoint_id="endpoint-" + repo,
            repository_id=repo,
            url="file:///fixture/" + repo,
            transport="file",
            metadata="{}",
        )
        put(
            db,
            "git_acquisitions",
            git_acquisition_id="run-" + repo,
            repository_id=repo,
            repository_endpoint_id="endpoint-" + repo,
            endpoint_url="file:///fixture/" + repo,
            object_format="sha1",
            kind="git",
            request="{}",
            source_id="source",
        )
        put(
            db,
            "snapshots",
            snapshot_id="snapshot-" + repo,
            git_acquisition_id="run-" + repo,
            repository_id=repo,
            published=0,
            generation=1,
            created_at=TIME,
        )
        put(
            db,
            "change_requests",
            change_request_id="cr-" + repo,
            repository_id=repo,
            repository_binding_id="binding-" + repo,
            change_request_kind="pull_request",
            provider_change_request_number=1,
        )
        put(
            db,
            "change_request_observations",
            change_request_observation_id=index,
            change_request_id="cr-" + repo,
            observed_at=TIME,
            published=0,
            payload="{}",
            parsed_at=TIME,
        )
        db.execute(
            "UPDATE snapshots SET published=1 WHERE snapshot_id=?",
            ("snapshot-" + repo,),
        )
        db.execute(
            "UPDATE change_request_observations SET published=1 WHERE change_request_observation_id=?",
            (index,),
        )
        db.execute(
            "UPDATE repositories SET current_snapshot_id=? WHERE repository_id=?",
            ("snapshot-" + repo, repo),
        )
        db.execute(
            "UPDATE change_requests SET current_change_request_observation_id=? WHERE change_request_id=?",
            (index, "cr-" + repo),
        )
        put(
            db,
            "text_bodies",
            text_body_id=index,
            body=repo,
            byte_length=1,
            sha256=hashlib.sha256(repo.encode()).digest(),
        )
        put(
            db,
            "documents",
            change_request_id="cr-" + repo,
            kind="pr-body",
            provider_change_request_document_id="native",
            deleted=0,
            metadata="{}",
        )
        put(
            db,
            "document_observations",
            document_observation_id=index,
            change_request_id="cr-" + repo,
            kind="pr-body",
            provider_change_request_document_id="native",
            text_body_sha256=hashlib.sha256(repo.encode()).digest(),
            observed_at=TIME,
            parsed_at=TIME,
            metadata="{}",
        )
        db.execute(
            "UPDATE documents SET current_document_observation_id=? WHERE change_request_id=? AND kind='pr-body' AND provider_change_request_document_id='native'",
            (index, "cr-" + repo),
        )
        for document_kind in ("review", "review-comment"):
            put(
                db,
                "documents",
                change_request_id="cr-" + repo,
                kind=document_kind,
                provider_change_request_document_id="native-" + repo,
                deleted=0,
                metadata="{}",
            )
        put(
            db,
            "review_threads",
            provider_resource_id="thread-" + repo,
            change_request_id="cr-" + repo,
            payload="{}",
            observed_at=TIME,
        )
        put(
            db,
            "resume_scopes",
            resume_scope_id="scope-" + repo,
            repository_id=repo,
            repository_binding_id="binding-" + repo,
            source_id="source",
            request_context="{}",
            parser_version="catalog3-test/1",
            profile_version="catalog-text-v1",
            confidence="proven",
        )
        for kind in ("commits", "files"):
            collection = repo + "-" + kind
            put(
                db,
                "fetch_collections",
                fetch_collection_id=collection,
                repository_id=repo,
                change_request_id="cr-" + repo,
                source_id="source",
                resume_scope_id="scope-" + repo,
                kind=kind,
            )
            put(
                db,
                "code_listings",
                code_listing_id="listing-" + collection,
                change_request_id="cr-" + repo,
                fetch_collection_id=collection,
                kind=kind,
                resume_scope_id="scope-" + repo,
                object_format="sha1",
                head_oid=H,
                base_oid=B,
            )
            put(
                db,
                "code_listing_progress",
                code_listing_id="listing-" + collection,
                state="partial",
                terminal=0,
                page_count=0,
                context_proven=0,
            )
    put(
        db,
        "payloads",
        payload_id=1,
        sha256=hashlib.sha256(b"[]").digest(),
        body=b"[]",
        byte_length=2,
        representation="decoded_api",
    )
    put(
        db,
        "fetch_occurrences",
        fetch_occurrence_id=1,
        fetch_collection_id="a-commits",
        ordinal=0,
        payload_id=1,
        request="{}",
        observed_at=TIME,
        parsed_at=TIME,
    )
    put(
        db,
        "fetch_occurrences",
        fetch_occurrence_id=2,
        fetch_collection_id="a-files",
        ordinal=0,
        payload_id=1,
        request="{}",
        observed_at=TIME,
        parsed_at=TIME,
    )
    return db


@pytest.fixture
def target():
    db = build_target()
    yield db
    if db.in_transaction:
        db.rollback()
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()


def test_fresh_complete_schema(target):
    db = target
    assert (
        len(db.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall())
        == 73
    )
    assert all(
        row[5] == 1
        for row in db.execute("PRAGMA table_list")
        if row[1] not in ("sqlite_schema", "sqlite_temp_schema")
    )
    assert all(
        fk[5] == "RESTRICT" and fk[6] == "RESTRICT"
        for (table,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        for fk in db.execute(f"PRAGMA foreign_key_list({table})")
    )


@pytest.mark.parametrize("mode", ["autocommit", "transaction", "savepoint"])
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE snapshots SET snapshot_id='temporary' WHERE snapshot_id='snapshot-a'",
        "UPDATE snapshots SET git_acquisition_id='run-b', repository_id='b' WHERE snapshot_id='snapshot-a'",
        "UPDATE snapshots SET published=0 WHERE snapshot_id='snapshot-a'",
        "UPDATE change_request_observations SET change_request_observation_id=999 WHERE change_request_observation_id=1",
        "UPDATE change_request_observations SET change_request_id='cr-b' WHERE change_request_observation_id=1",
        "UPDATE change_request_observations SET published=0 WHERE change_request_observation_id=1",
        "UPDATE documents SET provider_change_request_document_id='temporary' WHERE change_request_id='cr-a'",
        "UPDATE documents SET change_request_id='cr-b' WHERE change_request_id='cr-a'",
        "UPDATE document_observations SET document_observation_id=999 WHERE document_observation_id=1",
        "UPDATE text_bodies SET text_body_id=999 WHERE text_body_id=1",
        "UPDATE code_listings SET code_listing_id='temporary' WHERE code_listing_id='listing-a-commits'",
        "UPDATE code_listings SET resume_scope_id='scope-b' WHERE code_listing_id='listing-a-commits'",
        "DELETE FROM snapshots WHERE snapshot_id='snapshot-a'",
        "DELETE FROM document_observations WHERE document_observation_id=1",
        "DELETE FROM text_bodies WHERE text_body_id=1",
    ],
)
def test_parent_identity_and_facts_fixed(target, mode, sql):
    db = target
    if mode == "transaction":
        db.execute("BEGIN")
    if mode == "savepoint":
        db.execute("SAVEPOINT attempt")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql)
    if mode == "savepoint":
        db.execute("ROLLBACK TO attempt")
        db.execute("RELEASE attempt")
    if mode == "transaction":
        db.execute("COMMIT")
    assert (
        db.execute(
            "SELECT published FROM snapshots WHERE snapshot_id='snapshot-a'"
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT published FROM change_request_observations WHERE change_request_observation_id=1"
        ).fetchone()[0]
        == 1
    )


@pytest.mark.parametrize(
    "table,key,temp,pointer,owner,entity",
    [
        (
            "snapshots",
            "snapshot-a",
            "temporary",
            "current_snapshot_id",
            "repositories",
            "a",
        ),
        (
            "change_request_observations",
            1,
            999,
            "current_change_request_observation_id",
            "change_requests",
            "cr-a",
        ),
    ],
)
def test_reviewed_multi_statement_attack(
    target, table, key, temp, pointer, owner, entity
):
    db = target
    db.execute("BEGIN")
    db.execute("SAVEPOINT attack")
    entity_id = {
        "snapshots": "snapshot_id",
        "change_request_observations": "change_request_observation_id",
    }[table]
    owner_id = {
        "repositories": "repository_id",
        "change_requests": "change_request_id",
    }[owner]
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(f"UPDATE {table} SET {entity_id}=? WHERE {entity_id}=?", (temp, key))
    db.execute("ROLLBACK TO attack")
    db.execute("RELEASE attack")
    db.execute("COMMIT")
    assert (
        db.execute(
            f"SELECT published FROM {table} WHERE {entity_id}=?", (key,)
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            f"SELECT {pointer} FROM {owner} WHERE {owner_id}=?", (entity,)
        ).fetchone()[0]
        == key
    )


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE repositories SET current_snapshot_id='snapshot-b' WHERE repository_id='a'",
        "UPDATE repositories SET preferred_repository_endpoint_id='endpoint-b' WHERE repository_id='a'",
        "UPDATE change_requests SET current_change_request_observation_id=2 WHERE change_request_id='cr-a'",
        "UPDATE documents SET current_document_observation_id=2 WHERE change_request_id='cr-a' AND kind='pr-body'",
        "INSERT INTO review_comments(change_request_id,kind,provider_change_request_document_id,review_thread_provider_resource_id,payload) VALUES('cr-a','review-comment','native-a','thread-b','{}')",
        "INSERT INTO reviews(change_request_id,kind,provider_change_request_document_id,payload) VALUES('cr-a','review','native-b','{}')",
        "UPDATE fetch_collections SET change_request_id='cr-b' WHERE fetch_collection_id='a-commits'",
        "DELETE FROM repositories WHERE repository_id='a'",
    ],
)
def test_cross_owner_and_parent_deletion(target, sql):
    with pytest.raises(sqlite3.IntegrityError):
        target.execute(sql)


@pytest.mark.parametrize("recursive", [0, 1])
def test_replace_upsert_and_same_repo_reassignment(target, recursive):
    db = target
    db.execute(f"PRAGMA recursive_triggers={recursive}")
    for sql in (
        "INSERT OR REPLACE INTO snapshots SELECT snapshot_id,git_acquisition_id,repository_id,0,generation,created_at FROM snapshots WHERE snapshot_id='snapshot-a'",
        "INSERT INTO snapshots SELECT * FROM snapshots WHERE snapshot_id='snapshot-a' ON CONFLICT(snapshot_id) DO UPDATE SET published=0",
        "INSERT OR REPLACE INTO document_observations SELECT 1,change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at,parsed_at,origin_key,fetch_occurrence_id,metadata FROM document_observations WHERE document_observation_id=2",
        "INSERT OR REPLACE INTO text_bodies SELECT 99,body,byte_length,sha256 FROM text_bodies WHERE text_body_id=1",
        "INSERT OR REPLACE INTO code_listings SELECT * FROM code_listings WHERE code_listing_id='listing-a-commits'",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql)
    put(
        db,
        "git_acquisitions",
        git_acquisition_id="other-run-a",
        repository_id="a",
        object_format="sha1",
        kind="git",
        request="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE snapshots SET git_acquisition_id='other-run-a' WHERE snapshot_id='snapshot-a'"
        )


def test_bootstrap_and_rollback(target):
    db = target
    db.execute("BEGIN")
    put(db, "repositories", repository_id="new", name="new", metadata="{}")
    put(
        db,
        "git_acquisitions",
        git_acquisition_id="new-run",
        repository_id="new",
        object_format="sha1",
        kind="git",
        request="{}",
    )
    put(
        db,
        "snapshots",
        snapshot_id="new-snapshot",
        git_acquisition_id="new-run",
        repository_id="new",
        published=0,
        generation=0,
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE repositories SET current_snapshot_id='new-snapshot' WHERE repository_id='new'"
        )
    db.execute("UPDATE snapshots SET published=1 WHERE snapshot_id='new-snapshot'")
    db.execute(
        "UPDATE repositories SET current_snapshot_id='new-snapshot' WHERE repository_id='new'"
    )
    db.execute("ROLLBACK")
    assert (
        db.execute(
            "SELECT repository_id FROM repositories WHERE repository_id='new'"
        ).fetchall()
        == []
    )


@pytest.mark.parametrize(
    "fields",
    [
        {
            "object_format": "sha1",
            "oid": b"x" * 19,
            "type": "blob",
            "size": 1,
            "verified": 1,
        },
        {
            "object_format": "sha256",
            "oid": b"x" * 20,
            "type": "blob",
            "size": 1,
            "verified": 1,
        },
        {
            "object_format": "sha1",
            "oid": H,
            "type": "invented",
            "size": 1,
            "verified": 1,
        },
        {"object_format": "sha1", "oid": H, "type": "blob", "size": -1, "verified": 1},
        {"object_format": "sha1", "oid": H, "type": "blob", "size": 1, "verified": 2},
        {
            "object_format": "sha1",
            "oid": H,
            "type": "blob",
            "size": None,
            "verified": 1,
        },
    ],
)
def test_oid_type_numeric_boolean_null(target, fields):
    with pytest.raises(sqlite3.IntegrityError):
        put(target, "git_objects", git_object_id=1, **fields)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO sources(source_id,service_instance_uuidv4,discovery_kind,name,settings) VALUES('bad','00000000-0000-4000-8000-000000000101','github_inventory','bad','[]')",
        "INSERT INTO sources(source_id,service_instance_uuidv4,discovery_kind,name,settings) VALUES('bad','00000000-0000-4000-8000-000000000101','github_inventory','bad','invalid-json')",
        "INSERT INTO code_listing_progress(code_listing_id,state,terminal,page_count,context_proven) VALUES('listing-a-commits','invented',0,0,0)",
        "UPDATE code_listing_progress SET page_count=-1 WHERE code_listing_id='listing-a-commits'",
        "UPDATE code_listing_progress SET state='complete' WHERE code_listing_id='listing-a-commits'",
        "INSERT INTO code_observations(code_observation_id,change_request_id,change_request_observation_id,state,details) VALUES(1,'cr-a',1,'complete','{}')",
    ],
)
def test_json_and_listing_state(target, sql):
    with pytest.raises(sqlite3.IntegrityError):
        target.execute(sql)


def test_git_meaning_and_multiple_ref_origins(target):
    db = target
    for id, kind, oid in ((1, "tree", b"t" * 20), (2, "commit", H), (3, "blob", B)):
        put(
            db,
            "git_objects",
            git_object_id=id,
            object_format="sha1",
            oid=oid,
            type=kind,
            size=1,
            verified=1,
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "commits",
            git_object_id=2,
            tree_git_object_id=3,
            raw_headers=b"",
            raw_message=b"",
            metadata="{}",
        )
    put(
        db,
        "commits",
        git_object_id=2,
        tree_git_object_id=1,
        raw_headers=b"",
        raw_message=b"",
        metadata="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "commit_parents",
            commit_git_object_id=2,
            parent_ordinal=0,
            parent_git_object_id=3,
        )
    put(
        db,
        "acquisition_roots",
        acquisition_root_id=1,
        git_acquisition_id="run-a",
        repository_id="a",
        object_format="sha1",
        oid=H,
        role="head",
        published=1,
    )
    for ordinal, name in enumerate((b"refs/heads/main", b"refs/heads/alias")):
        put(
            db,
            "ref_observations",
            snapshot_id="snapshot-a",
            raw_ref_name=name,
            kind="head",
            object_format="sha1",
            target_oid=H,
            target_type="commit",
        )
        put(
            db,
            "root_origins",
            root_origin_id=ordinal + 1,
            acquisition_root_id=1,
            origin_kind="ref",
            raw_ref_name=name,
            source_ordinal=ordinal,
            snapshot_id="snapshot-a",
            repository_id="a",
        )
    assert (
        db.execute(
            "SELECT count(*) FROM root_origins WHERE acquisition_root_id=1"
        ).fetchone()[0]
        == 2
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "root_origins",
            root_origin_id=3,
            acquisition_root_id=1,
            origin_kind="ref",
            raw_ref_name=b"no-ref",
            source_ordinal=2,
            snapshot_id="snapshot-a",
            repository_id="a",
        )


def test_body_sharing_preserves_a_b_a_and_times(target):
    db = target
    values = (
        (11, "a", "observed-A"),
        (12, "b", "observed-B"),
        (13, "a", "observed-A-again"),
        (14, "a", "same-body-new-observation"),
    )
    for ident, body, timestamp in values:
        put(
            db,
            "document_observations",
            document_observation_id=ident,
            change_request_id="cr-a",
            kind="pr-body",
            provider_change_request_document_id="native",
            text_body_sha256=hashlib.sha256(body.encode()).digest(),
            observed_at=timestamp,
            parsed_at="later",
            metadata="{}",
        )
    assert db.execute(
        "SELECT b.body,o.observed_at FROM document_observations o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.document_observation_id>=11 ORDER BY o.document_observation_id"
    ).fetchall() == [(body, timestamp) for _, body, timestamp in values]
    assert db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "document_observations",
            document_observation_id=15,
            change_request_id="cr-a",
            kind="pr-body",
            provider_change_request_document_id="absent",
            text_body_sha256=hashlib.sha256(b"a").digest(),
            parsed_at="later",
            metadata="{}",
        )


def test_listing_scope_context_partial_complete(target):
    db = target
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "code_commits",
            code_listing_id="listing-a-files",
            fetch_occurrence_id=1,
            position=0,
            object_format="sha1",
            oid=H,
            payload="{}",
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "code_commits",
            code_listing_id="listing-a-commits",
            fetch_occurrence_id=2,
            position=0,
            object_format="sha1",
            oid=H,
            payload="{}",
        )
    put(
        db,
        "code_commits",
        code_listing_id="listing-a-commits",
        fetch_occurrence_id=1,
        position=0,
        object_format="sha1",
        oid=H,
        payload="{}",
    )
    for id in ("listing-a-commits", "listing-a-files"):
        db.execute(
            "UPDATE code_listing_progress SET state='complete',terminal=1,context_proven=1,page_count=1 WHERE code_listing_id=?",
            (id,),
        )
    put(
        db,
        "code_observations",
        code_observation_id=1,
        change_request_id="cr-a",
        change_request_observation_id=1,
        commit_code_listing_id="listing-a-commits",
        file_code_listing_id="listing-a-files",
        state="complete",
        object_format="sha1",
        head_oid=H,
        base_oid=B,
        details="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "code_observations",
            code_observation_id=2,
            change_request_id="cr-a",
            change_request_observation_id=1,
            commit_code_listing_id="listing-a-commits",
            file_code_listing_id="listing-a-files",
            state="complete",
            object_format="sha1",
            head_oid=B,
            base_oid=B,
            details="{}",
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE code_listing_progress SET state='partial' WHERE code_listing_id='listing-a-commits'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "code_commits",
            code_listing_id="listing-a-commits",
            fetch_occurrence_id=1,
            position=1,
            object_format="sha1",
            oid=B,
            payload="{}",
        )


def test_resume_scope_and_immutable_scan(target):
    db = target
    put(
        db,
        "incremental_scans",
        incremental_scan_id="scan",
        resume_scope_id="scope-a",
        fetch_collection_id="a-commits",
        scan_started_at=TIME,
        safe_watermark=TIME,
        evidence="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE incremental_scans SET safe_watermark='2099-01-01' WHERE incremental_scan_id='scan'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "completion_markers",
            completion_marker_id=1,
            resume_scope_id="scope-b",
            fetch_collection_id="a-commits",
            asserted_state="complete",
            evidence="{}",
        )
    put(
        db,
        "completion_markers",
        completion_marker_id=1,
        resume_scope_id="scope-a",
        fetch_collection_id="a-commits",
        asserted_state="partial",
        evidence="{}",
        observed_at=TIME,
    )
    put(
        db,
        "resume_cursors",
        resume_scope_id="scope-a",
        incremental_scan_id="scan",
        reusable=0,
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "resume_cursors",
            resume_scope_id="scope-b",
            incremental_scan_id="scan",
            reusable=1,
        )


def test_old_cache_and_job_runtime_are_not_reactivated(target):
    db = target
    put(
        db,
        "cache_locators",
        cache_locator_id="old-cache",
        repository_id="a",
        path="/synthetic/sealed-cache",
        access="source_readonly",
        state="available",
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "active_cache_entries",
            active_cache_entry_id="active",
            cache_locator_id="old-cache",
            generation=1,
            state="active",
            last_used=1.0,
            bytes=0,
        )
    put(db, "jobs", job_id="job", kind="legacy", request="{}")
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "job_attempts",
            job_id="job",
            attempt=0,
            state="running",
            checkpoint="{}",
        )
    put(
        db,
        "job_attempts",
        job_id="job",
        attempt=5,
        state="interrupted",
        checkpoint="{}",
    )
    db.execute("UPDATE jobs SET current_attempt=5 WHERE job_id='job'")
    assert db.execute(
        "SELECT attempt FROM job_attempts WHERE job_id='job'"
    ).fetchall() == [(5,)]


def test_distinct_observation_ids_survive_shared_body(target):
    put(
        target,
        "document_observations",
        document_observation_id=99,
        change_request_id="cr-a",
        kind="pr-body",
        provider_change_request_document_id="native",
        text_body_sha256=hashlib.sha256(b"a").digest(),
        observed_at=TIME,
        parsed_at=TIME,
        metadata="{}",
    )
    assert target.execute(
        "SELECT document_observation_id FROM document_observations WHERE change_request_id='cr-a' AND text_body_sha256=? ORDER BY document_observation_id",
        (hashlib.sha256(b"a").digest(),),
    ).fetchall() == [(1,), (99,)]


def test_listing_commit_oid_format_matches_context(target):
    with pytest.raises(sqlite3.IntegrityError):
        put(
            target,
            "code_commits",
            code_listing_id="listing-a-commits",
            fetch_occurrence_id=1,
            position=0,
            object_format="sha256",
            oid=b"x" * 32,
            payload="{}",
        )
