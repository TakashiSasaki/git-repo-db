"""P1 target contracts in isolated SQLite databases; no production runner/data."""

import hashlib
import sqlite3

import pytest

from scripts.schema_contract import construct

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
        id="instance",
        kind="github",
        name="fixture",
        metadata="{}",
    )
    put(
        db,
        "sources",
        id="source",
        instance_id="instance",
        discovery_kind="github_inventory",
        name="fixture",
        settings="{}",
    )
    for index, repo in enumerate(("a", "b"), 1):
        put(db, "repositories", id=repo, name=repo, metadata="{}")
        put(
            db,
            "repository_bindings",
            id="binding-" + repo,
            repo_id=repo,
            instance_id="instance",
            provider_repo_id=repo,
            metadata="{}",
        )
        put(
            db,
            "repository_endpoints",
            id="endpoint-" + repo,
            repo_id=repo,
            url="file:///fixture/" + repo,
            transport="file",
            metadata="{}",
        )
        put(
            db,
            "git_acquisitions",
            id="run-" + repo,
            repo_id=repo,
            endpoint_id="endpoint-" + repo,
            endpoint_url="file:///fixture/" + repo,
            object_format="sha1",
            kind="git",
            request="{}",
            source_id="source",
        )
        put(
            db,
            "snapshots",
            id="snapshot-" + repo,
            acquisition_id="run-" + repo,
            repo_id=repo,
            published=0,
            generation=1,
            created_at=TIME,
        )
        put(
            db,
            "change_requests",
            id="cr-" + repo,
            repo_id=repo,
            binding_id="binding-" + repo,
            request_kind="pull_request",
            number=1,
        )
        put(
            db,
            "change_request_observations",
            id=index,
            change_request_id="cr-" + repo,
            observed_at=TIME,
            published=0,
            payload="{}",
            parsed_at=TIME,
        )
        db.execute("UPDATE snapshots SET published=1 WHERE id=?", ("snapshot-" + repo,))
        db.execute(
            "UPDATE change_request_observations SET published=1 WHERE id=?", (index,)
        )
        db.execute(
            "UPDATE repositories SET current_snapshot_id=? WHERE id=?",
            ("snapshot-" + repo, repo),
        )
        db.execute(
            "UPDATE change_requests SET current_observation_id=? WHERE id=?",
            (index, "cr-" + repo),
        )
        put(
            db,
            "text_bodies",
            id=index,
            body=repo,
            byte_length=1,
            sha256=hashlib.sha256(repo.encode()).digest(),
        )
        put(
            db,
            "documents",
            id="doc-" + repo,
            change_request_id="cr-" + repo,
            kind="pr-body",
            provider_id="native",
            deleted=0,
            metadata="{}",
        )
        put(db, "document_versions", id=index, document_id="doc-" + repo, body_id=index)
        db.execute(
            "UPDATE documents SET current_version_id=? WHERE id=?",
            (index, "doc-" + repo),
        )
        put(
            db,
            "review_threads",
            id="thread-" + repo,
            change_request_id="cr-" + repo,
            payload="{}",
            observed_at=TIME,
        )
        put(
            db,
            "resume_scopes",
            id="scope-" + repo,
            repo_id=repo,
            binding_id="binding-" + repo,
            source_id="source",
            request_context="{}",
            parser_version="p1",
            profile_version="catalog-text-v1",
            confidence="proven",
        )
        for kind in ("commits", "files"):
            collection = repo + "-" + kind
            put(
                db,
                "fetch_collections",
                id=collection,
                repo_id=repo,
                change_request_id="cr-" + repo,
                source_id="source",
                scope_id="scope-" + repo,
                kind=kind,
            )
            put(
                db,
                "code_listings",
                id="listing-" + collection,
                change_request_id="cr-" + repo,
                collection_id=collection,
                kind=kind,
                scope_id="scope-" + repo,
                object_format="sha1",
                head_oid=H,
                base_oid=B,
            )
            put(
                db,
                "code_listing_progress",
                listing_id="listing-" + collection,
                state="partial",
                terminal=0,
                page_count=0,
                context_proven=0,
            )
    put(
        db,
        "payloads",
        id=1,
        sha256=hashlib.sha256(b"[]").digest(),
        body=b"[]",
        byte_length=2,
        representation="decoded_api",
    )
    put(
        db,
        "fetch_occurrences",
        id=1,
        collection_id="a-commits",
        ordinal=0,
        payload_id=1,
        request="{}",
        observed_at=TIME,
        parsed_at=TIME,
    )
    put(
        db,
        "fetch_occurrences",
        id=2,
        collection_id="a-files",
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
        == 74
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
        "UPDATE snapshots SET id='temporary' WHERE id='snapshot-a'",
        "UPDATE snapshots SET acquisition_id='run-b', repo_id='b' WHERE id='snapshot-a'",
        "UPDATE snapshots SET published=0 WHERE id='snapshot-a'",
        "UPDATE change_request_observations SET id=999 WHERE id=1",
        "UPDATE change_request_observations SET change_request_id='cr-b' WHERE id=1",
        "UPDATE change_request_observations SET published=0 WHERE id=1",
        "UPDATE documents SET id='temporary' WHERE id='doc-a'",
        "UPDATE documents SET change_request_id='cr-b' WHERE id='doc-a'",
        "UPDATE document_versions SET id=999 WHERE id=1",
        "UPDATE text_bodies SET id=999 WHERE id=1",
        "UPDATE code_listings SET id='temporary' WHERE id='listing-a-commits'",
        "UPDATE code_listings SET scope_id='scope-b' WHERE id='listing-a-commits'",
        "DELETE FROM snapshots WHERE id='snapshot-a'",
        "DELETE FROM document_versions WHERE id=1",
        "DELETE FROM text_bodies WHERE id=1",
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
        db.execute("SELECT published FROM snapshots WHERE id='snapshot-a'").fetchone()[
            0
        ]
        == 1
    )
    assert (
        db.execute(
            "SELECT published FROM change_request_observations WHERE id=1"
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
            "current_observation_id",
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
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(f"UPDATE {table} SET id=? WHERE id=?", (temp, key))
    db.execute("ROLLBACK TO attack")
    db.execute("RELEASE attack")
    db.execute("COMMIT")
    assert (
        db.execute(f"SELECT published FROM {table} WHERE id=?", (key,)).fetchone()[0]
        == 1
    )
    assert (
        db.execute(f"SELECT {pointer} FROM {owner} WHERE id=?", (entity,)).fetchone()[0]
        == key
    )


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE repositories SET current_snapshot_id='snapshot-b' WHERE id='a'",
        "UPDATE repositories SET preferred_endpoint_id='endpoint-b' WHERE id='a'",
        "UPDATE change_requests SET current_observation_id=2 WHERE id='cr-a'",
        "UPDATE documents SET current_version_id=2 WHERE id='doc-a'",
        "INSERT INTO review_comments VALUES('doc-a','cr-a','thread-b','{}')",
        "INSERT INTO reviews VALUES('review','cr-a','doc-b','{}')",
        "UPDATE fetch_collections SET change_request_id='cr-b' WHERE id='a-commits'",
        "DELETE FROM repositories WHERE id='a'",
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
        "INSERT OR REPLACE INTO snapshots SELECT id,acquisition_id,repo_id,0,generation,created_at FROM snapshots WHERE id='snapshot-a'",
        "INSERT INTO snapshots SELECT * FROM snapshots WHERE id='snapshot-a' ON CONFLICT(id) DO UPDATE SET published=0",
        "INSERT OR REPLACE INTO document_versions VALUES(1,'doc-b',2,NULL)",
        "INSERT OR REPLACE INTO text_bodies SELECT 99,body,byte_length,sha256 FROM text_bodies WHERE id=1",
        "INSERT OR REPLACE INTO code_listings SELECT * FROM code_listings WHERE id='listing-a-commits'",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql)
    put(
        db,
        "git_acquisitions",
        id="other-run-a",
        repo_id="a",
        object_format="sha1",
        kind="git",
        request="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE snapshots SET acquisition_id='other-run-a' WHERE id='snapshot-a'"
        )


def test_bootstrap_and_rollback(target):
    db = target
    db.execute("BEGIN")
    put(db, "repositories", id="new", name="new", metadata="{}")
    put(
        db,
        "git_acquisitions",
        id="new-run",
        repo_id="new",
        object_format="sha1",
        kind="git",
        request="{}",
    )
    put(
        db,
        "snapshots",
        id="new-snapshot",
        acquisition_id="new-run",
        repo_id="new",
        published=0,
        generation=0,
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE repositories SET current_snapshot_id='new-snapshot' WHERE id='new'"
        )
    db.execute("UPDATE snapshots SET published=1 WHERE id='new-snapshot'")
    db.execute(
        "UPDATE repositories SET current_snapshot_id='new-snapshot' WHERE id='new'"
    )
    db.execute("ROLLBACK")
    assert db.execute("SELECT id FROM repositories WHERE id='new'").fetchall() == []


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
        put(target, "git_objects", id=1, **fields)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO sources VALUES('bad','instance','github_inventory','bad','[]')",
        "INSERT INTO sources VALUES('bad','instance','github_inventory','bad','invalid-json')",
        "INSERT INTO code_listing_progress VALUES('listing-a-commits','invented',0,0,0)",
        "UPDATE code_listing_progress SET page_count=-1 WHERE listing_id='listing-a-commits'",
        "UPDATE code_listing_progress SET state='complete' WHERE listing_id='listing-a-commits'",
        "INSERT INTO code_observations(id,change_request_id,observation_id,state,details) VALUES(1,'cr-a',1,'complete','{}')",
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
            id=id,
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
            object_id=2,
            tree_id=3,
            raw_headers=b"",
            raw_message=b"",
            metadata="{}",
        )
    put(
        db,
        "commits",
        object_id=2,
        tree_id=1,
        raw_headers=b"",
        raw_message=b"",
        metadata="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(db, "commit_parents", commit_id=2, parent_ordinal=0, parent_id=3)
    put(
        db,
        "acquisition_roots",
        id=1,
        acquisition_id="run-a",
        repo_id="a",
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
            id=ordinal + 1,
            root_id=1,
            origin_kind="ref",
            raw_ref_name=name,
            source_ordinal=ordinal,
            snapshot_id="snapshot-a",
            repo_id="a",
        )
    assert (
        db.execute("SELECT count(*) FROM root_origins WHERE root_id=1").fetchone()[0]
        == 2
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "root_origins",
            id=3,
            root_id=1,
            origin_kind="ref",
            raw_ref_name=b"no-ref",
            source_ordinal=2,
            snapshot_id="snapshot-a",
            repo_id="a",
        )


def test_body_sharing_preserves_a_b_a_and_times(target):
    db = target
    put(db, "document_versions", id=3, document_id="doc-a", body_id=2)
    for id, version, time in (
        (1, 1, "observed-A"),
        (2, 3, "observed-B"),
        (3, 1, "observed-A-again"),
        (4, 1, "same-body-new-observation"),
    ):
        put(
            db,
            "document_observations",
            id=id,
            document_id="doc-a",
            version_id=version,
            observed_at=time,
            parsed_at="later",
            metadata="{}",
        )
    assert db.execute(
        "SELECT version_id,observed_at FROM document_observations ORDER BY id"
    ).fetchall() == [
        (1, "observed-A"),
        (3, "observed-B"),
        (1, "observed-A-again"),
        (1, "same-body-new-observation"),
    ]
    assert db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "document_observations",
            id=5,
            document_id="doc-a",
            version_id=2,
            parsed_at="later",
            metadata="{}",
        )


def test_listing_scope_context_partial_complete(target):
    db = target
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "code_commits",
            listing_id="listing-a-files",
            occurrence_id=1,
            position=0,
            object_format="sha1",
            oid=H,
            payload="{}",
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "code_commits",
            listing_id="listing-a-commits",
            occurrence_id=2,
            position=0,
            object_format="sha1",
            oid=H,
            payload="{}",
        )
    put(
        db,
        "code_commits",
        listing_id="listing-a-commits",
        occurrence_id=1,
        position=0,
        object_format="sha1",
        oid=H,
        payload="{}",
    )
    for id in ("listing-a-commits", "listing-a-files"):
        db.execute(
            "UPDATE code_listing_progress SET state='complete',terminal=1,context_proven=1,page_count=1 WHERE listing_id=?",
            (id,),
        )
    put(
        db,
        "code_observations",
        id=1,
        change_request_id="cr-a",
        observation_id=1,
        commit_listing_id="listing-a-commits",
        file_listing_id="listing-a-files",
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
            id=2,
            change_request_id="cr-a",
            observation_id=1,
            commit_listing_id="listing-a-commits",
            file_listing_id="listing-a-files",
            state="complete",
            object_format="sha1",
            head_oid=B,
            base_oid=B,
            details="{}",
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE code_listing_progress SET state='partial' WHERE listing_id='listing-a-commits'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "code_commits",
            listing_id="listing-a-commits",
            occurrence_id=1,
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
        id="scan",
        scope_id="scope-a",
        collection_id="a-commits",
        scan_started_at=TIME,
        safe_watermark=TIME,
        evidence="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE incremental_scans SET safe_watermark='2099-01-01' WHERE id='scan'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "completion_markers",
            id=1,
            scope_id="scope-b",
            collection_id="a-commits",
            asserted_state="complete",
            evidence="{}",
        )
    put(
        db,
        "completion_markers",
        id=1,
        scope_id="scope-a",
        collection_id="a-commits",
        asserted_state="partial",
        evidence="{}",
        observed_at=TIME,
    )
    put(db, "resume_cursors", scope_id="scope-a", scan_id="scan", reusable=0)
    with pytest.raises(sqlite3.IntegrityError):
        put(db, "resume_cursors", scope_id="scope-b", scan_id="scan", reusable=1)


def test_old_cache_and_job_runtime_are_not_reactivated(target):
    db = target
    put(
        db,
        "cache_locators",
        id="old-cache",
        repo_id="a",
        path="/synthetic/sealed-cache",
        access="source_readonly",
        state="available",
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "active_cache_entries",
            id="active",
            locator_id="old-cache",
            generation=1,
            state="active",
            last_used=1.0,
            bytes=0,
        )
    put(db, "jobs", id="job", kind="legacy", request="{}")
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
    db.execute("UPDATE jobs SET current_attempt=5 WHERE id='job'")
    assert db.execute(
        "SELECT attempt FROM job_attempts WHERE job_id='job'"
    ).fetchall() == [(5,)]


def test_existing_version_ids_survive_shared_body(target):
    put(
        target,
        "document_versions",
        id=99,
        document_id="doc-a",
        body_id=1,
        legacy_body_sha256=b"x" * 32,
    )
    assert target.execute(
        "SELECT id FROM document_versions WHERE document_id='doc-a' AND body_id=1 ORDER BY id"
    ).fetchall() == [(1,), (99,)]


def test_listing_commit_oid_format_matches_context(target):
    with pytest.raises(sqlite3.IntegrityError):
        put(
            target,
            "code_commits",
            listing_id="listing-a-commits",
            occurrence_id=1,
            position=0,
            object_format="sha256",
            oid=b"x" * 32,
            payload="{}",
        )
