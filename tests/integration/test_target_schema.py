"""Catalog3 structural contracts in isolated synthetic SQLite databases."""

import hashlib
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.schema import schema_sql
from tests.support.parser_facts import enrich, register_test_profile, repository_uuid


def construct(sql=None):
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(sql or schema_sql())
    return db


H = b"h" * 20
B = b"b" * 20
TIME = 1791201600000000


def put(db, table, **values):
    values = enrich(db, table, values)
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
        source_registration_uuidv4="00000000-0000-4000-8000-000000000201",
        source_id="source",
        service_instance_uuidv4="00000000-0000-4000-8000-000000000101",
        discovery_kind="github_inventory",
        name="fixture",
        settings="{}",
    )
    for index, repo in enumerate(("a", "b"), 1):
        put(db, "repositories", repository_uuidv4=repo, name=repo, metadata="{}")
        put(
            db,
            "repository_bindings",
            repository_binding_id="binding-" + repo,
            repository_uuidv4=repo,
            service_instance_uuidv4="00000000-0000-4000-8000-000000000101",
            provider_repository_id=repo,
            metadata="{}",
        )
        put(
            db,
            "repository_endpoints",
            repository_endpoint_id="endpoint-" + repo,
            repository_uuidv4=repo,
            url="file:///fixture/" + repo,
            transport="file",
            metadata="{}",
        )
        put(
            db,
            "git_acquisitions",
            git_acquisition_id="run-" + repo,
            repository_uuidv4=repo,
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
            repository_uuidv4=repo,
            published=0,
            generation=1,
            created_at_us=TIME,
        )
        put(
            db,
            "change_requests",
            change_request_id="cr-" + repo,
            repository_uuidv4=repo,
            repository_binding_id="binding-" + repo,
            change_request_kind="pull_request",
            provider_change_request_number=1,
        )
        put(
            db,
            "change_request_observations",
            change_request_observation_id=index,
            change_request_id="cr-" + repo,
            observed_at_us=TIME,
            published=1,
            payload="{}",
            parsed_at_us=TIME,
        )
        db.execute(
            "UPDATE snapshots SET published=1 WHERE snapshot_id=?",
            ("snapshot-" + repo,),
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
            observed_at_us=TIME,
            parsed_at_us=TIME,
            metadata="{}",
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
            observed_at_us=TIME,
        )
        put(
            db,
            "resume_scopes",
            resume_scope_id="scope-" + repo,
            repository_uuidv4=repo,
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
                repository_uuidv4=repo,
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
        "stored_bytes",
        sha256=hashlib.sha256(b"[]").digest(),
        body=b"[]",
        byte_length=2,
    )
    put(
        db,
        "payloads",
        representation="decoded_api",
        sha256=hashlib.sha256(b"[]").digest(),
    )
    put(
        db,
        "fetch_occurrences",
        fetch_occurrence_id=1,
        fetch_collection_id="a-commits",
        ordinal=0,
        payload_representation="decoded_api",
        payload_sha256=hashlib.sha256(b"[]").digest(),
        request="{}",
        observed_at_us=TIME,
        parsed_at_us=TIME,
    )
    put(
        db,
        "fetch_occurrences",
        fetch_occurrence_id=2,
        fetch_collection_id="a-files",
        ordinal=0,
        payload_representation="decoded_api",
        payload_sha256=hashlib.sha256(b"[]").digest(),
        request="{}",
        observed_at_us=TIME,
        parsed_at_us=TIME,
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
        >= 90
    )
    assert all(
        row[5] == 1
        for row in db.execute("PRAGMA table_list")
        if row[2] == "table" and row[1] not in ("sqlite_schema", "sqlite_temp_schema")
    )
    assert all(
        fk[5] in ("RESTRICT", "NO ACTION") and fk[6] in ("RESTRICT", "NO ACTION")
        for (table,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        for fk in db.execute(f"PRAGMA foreign_key_list({table})")
    )


@pytest.mark.parametrize("mode", ["autocommit", "transaction", "savepoint"])
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE snapshots SET snapshot_id='temporary' WHERE snapshot_id='snapshot-a'",
        "UPDATE snapshots SET git_acquisition_id='run-b', repository_uuidv4='00000000-0000-4000-8000-000000000302' WHERE snapshot_id='snapshot-a'",
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
            f"SELECT count(*) FROM {table} WHERE {entity_id}=?", (key,)
        ).fetchone()[0]
        == 1
    )


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE repositories SET preferred_repository_endpoint_id='endpoint-b' WHERE repository_uuidv4='00000000-0000-4000-8000-000000000301'",
        "INSERT INTO review_comments(change_request_id,kind,provider_change_request_document_id) VALUES('cr-a','review-comment','native-b')",
        "INSERT INTO reviews(change_request_id,kind,provider_change_request_document_id) VALUES('cr-a','review','native-b')",
        "UPDATE fetch_collections SET change_request_id='cr-b' WHERE fetch_collection_id='a-commits'",
        "DELETE FROM repositories WHERE repository_uuidv4='00000000-0000-4000-8000-000000000301'",
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
        "INSERT OR REPLACE INTO snapshots SELECT * FROM snapshots WHERE snapshot_id='snapshot-a'",
        "INSERT INTO snapshots SELECT * FROM snapshots WHERE snapshot_id='snapshot-a' ON CONFLICT(snapshot_id) DO UPDATE SET published=0",
        "INSERT OR REPLACE INTO document_observations SELECT * FROM document_observations WHERE document_observation_id=2",
        "INSERT OR REPLACE INTO text_bodies SELECT 99,body,byte_length,sha256 FROM text_bodies WHERE text_body_id=1",
        "INSERT OR REPLACE INTO code_listings SELECT * FROM code_listings WHERE code_listing_id='listing-a-commits'",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql)
    put(
        db,
        "git_acquisitions",
        git_acquisition_id="other-run-a",
        repository_uuidv4="a",
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
    put(db, "repositories", repository_uuidv4="new", name="new", metadata="{}")
    put(
        db,
        "git_acquisitions",
        git_acquisition_id="new-run",
        repository_uuidv4="new",
        kind="git",
        request="{}",
    )
    put(
        db,
        "snapshots",
        snapshot_id="new-snapshot",
        git_acquisition_id="new-run",
        repository_uuidv4="new",
        published=0,
        generation=0,
    )
    result = db.execute(
        "SELECT parsed_result_uuidv4 FROM snapshots WHERE snapshot_id='new-snapshot'"
    ).fetchone()[0]
    model = ParserModel(db)
    model.publish_result(result)
    with pytest.raises(sqlite3.IntegrityError):
        model.select_fact(result, fact_kind="git")
    db.execute("UPDATE snapshots SET published=1 WHERE snapshot_id='new-snapshot'")
    model.select_fact(result, fact_kind="git")
    db.execute("ROLLBACK")
    assert (
        db.execute(
            "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
            (repository_uuid("new"),),
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
        "INSERT INTO code_listing_progress(code_listing_id,state,terminal,page_count,context_proven) VALUES('listing-a-commits','invented',0,0,0)",
        "UPDATE code_listing_progress SET page_count=-1 WHERE code_listing_id='listing-a-commits'",
        "UPDATE code_listing_progress SET state='complete' WHERE code_listing_id='listing-a-commits'",
        "INSERT INTO code_observations(code_observation_id,change_request_id,change_request_observation_id,state,details) VALUES(1,'cr-a',1,'complete','{}')",
    ],
)
def test_json_and_listing_state(target, sql):
    with pytest.raises(sqlite3.IntegrityError):
        target.execute(sql)


@pytest.mark.parametrize("settings", ["[]", "invalid-json"])
def test_source_settings_insert_requires_json_object(target, settings):
    values = {
        "service_instance_uuidv4": "00000000-0000-4000-8000-000000000101",
        "discovery_kind": "github_inventory",
        "name": "settings-check",
    }
    put(
        target,
        "sources",
        source_id="valid-settings",
        source_registration_uuidv4="00000000-0000-4000-8000-000000000202",
        settings="{}",
        **values,
    )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        put(
            target,
            "sources",
            source_id="invalid-settings",
            source_registration_uuidv4="00000000-0000-4000-8000-000000000203",
            settings=settings,
            **values,
        )


def test_git_meaning_and_multiple_ref_origins(target):
    db = target
    # This input remains open while structural facts and roots are built; the
    # target fixture's previously sealed empty inputs cannot acquire late bytes.
    acquisition = "meaning-acquisition"
    repo = repository_uuid("a")
    put(
        db,
        "git_acquisitions",
        git_acquisition_id=acquisition,
        repository_uuidv4=repo,
        object_format="sha1",
        kind="git",
        request="{}",
    )
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
    for ident in (1, 2, 3):
        put(
            db,
            "repository_object_sources",
            repository_uuidv4=repo,
            git_object_id=ident,
            git_acquisition_id=acquisition,
        )
    result = ParserModel(db).create_result(
        register_test_profile(db),
        repository_uuidv4=repo,
        inputs=[{"git_acquisition_id": acquisition}],
    )
    put(
        db,
        "snapshots",
        snapshot_id="meaning-snapshot",
        git_acquisition_id=acquisition,
        repository_uuidv4=repo,
        parsed_result_uuidv4=result,
        published=1,
        generation=2,
    )
    provenance = {
        "parsed_result_uuidv4": result,
        "repository_uuidv4": repo,
        "git_acquisition_id": acquisition,
    }
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "commits",
            **provenance,
            git_fact_uuidv4=str(uuid.uuid4()),
            message_text="",
            git_object_id=2,
            tree_git_object_id=3,
            raw_headers=b"",
            raw_message=b"",
            metadata="{}",
        )
    put(
        db,
        "commits",
        **provenance,
        git_fact_uuidv4=str(uuid.uuid4()),
        message_text="",
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
            **provenance,
            git_fact_uuidv4=str(uuid.uuid4()),
            commit_git_object_id=2,
            parent_ordinal=0,
            parent_git_object_id=3,
        )
    put(
        db,
        "acquisition_roots",
        acquisition_root_id=1,
        git_acquisition_id=acquisition,
        repository_uuidv4="a",
        object_format="sha1",
        oid=H,
        role="head",
        published=1,
    )
    for ordinal, name in enumerate((b"refs/heads/main", b"refs/heads/alias")):
        put(
            db,
            "ref_observations",
            snapshot_id="meaning-snapshot",
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
            snapshot_id="meaning-snapshot",
            repository_uuidv4="a",
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
            snapshot_id="meaning-snapshot",
            repository_uuidv4="a",
        )


def test_body_sharing_preserves_a_b_a_and_times(target):
    db = target
    values = (
        (11, "a", TIME + 1),
        (12, "b", TIME + 2),
        (13, "a", TIME + 3),
        (14, "a", TIME + 4),
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
            observed_at_us=timestamp,
            parsed_at_us=TIME + 100,
            metadata="{}",
        )
    assert db.execute(
        "SELECT b.body,o.observed_at_us FROM document_observations o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.document_observation_id>=11 ORDER BY o.document_observation_id"
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
            parsed_at_us=TIME + 100,
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
    result = db.execute(
        "SELECT parsed_result_uuidv4 FROM code_commits WHERE code_listing_id='listing-a-commits'"
    ).fetchone()[0]
    ParserModel(db).publish_result(result)
    with pytest.raises(sqlite3.IntegrityError):
        put(
            db,
            "code_commits",
            parsed_result_uuidv4=result,
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
        scan_started_at_us=TIME,
        safe_watermark_us=TIME,
        evidence="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE incremental_scans SET safe_watermark_us=4070908800000000 WHERE incremental_scan_id='scan'"
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
        observed_at_us=TIME,
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
        repository_uuidv4="a",
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
            last_used_us=1000000,
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
        observed_at_us=TIME,
        parsed_at_us=TIME,
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
