"""Packaged structural and adversarial typed contracts in synthetic SQLite."""

import hashlib
import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.transactions import atomic_unit
from repo_catalog.domain.document import text_body_sha256
from repo_catalog.domain.models import CatalogError
from tests.support.domain_facts import (
    SERVICE,
    TIME_US,
    admit_document,
    admit_pr,
    admit_thread,
    candidate,
    collection,
    fresh_domain_db,
    repository_uuid,
)
from tests.support.domain_facts import (
    insert as put,
)

H = b"h" * 20
B = b"b" * 20
TIME = TIME_US


def build_target(sql=None):
    db = fresh_domain_db(sql)
    for number in (1, 2):
        admit_pr(
            db,
            number,
            state="open",
            object_format="sha1",
            head_oid=H.hex(),
            base_oid=B.hex(),
        )
        admit_document(db, number, body=str(number))
        admit_thread(db, number, resource=f"thread-{number}", resolved=False)
        put(
            db,
            "repository_endpoints",
            repository_endpoint_id=f"endpoint-{number}",
            repository_uuidv4=repository_uuid(number),
            url=f"file:///synthetic/{number}",
            transport="file",
            metadata="{}",
        )
        put(
            db,
            "git_acquisitions",
            git_acquisition_id=f"run-{number}",
            repository_uuidv4=repository_uuid(number),
            repository_endpoint_id=f"endpoint-{number}",
            endpoint_url=f"file:///synthetic/{number}",
            object_format="sha1",
            kind="git",
            request="{}",
        )
        put(
            db,
            "snapshots",
            snapshot_id=f"snapshot-{number}",
            git_acquisition_id=f"run-{number}",
            repository_uuidv4=repository_uuid(number),
            complete=0,
            generation=number,
            created_at_us=TIME,
        )
        for kind in ("commits", "files"):
            scope = collection(db, number, identity=f"{number}-{kind}", kind=kind)
            put(
                db,
                "code_listings",
                code_listing_id=f"listing-{number}-{kind}",
                change_request_id=f"pr{number}",
                fetch_collection_id=f"{number}-{kind}",
                kind=kind,
                resume_scope_id=scope,
                object_format="sha1",
                head_oid=H,
                base_oid=B,
            )
            put(
                db,
                "code_listing_progress",
                code_listing_id=f"listing-{number}-{kind}",
                state="partial",
                terminal=0,
                page_count=0,
                context_proven=0,
            )
    return db


@pytest.fixture
def target():
    db = build_target()
    yield db
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    db.close()


def test_fresh_complete_schema(target):
    db = target
    names = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
    }
    assert {
        "change_request_state",
        "document_state",
        "review_thread_state",
        "git_objects",
        "coverage_claims",
    } <= names
    assert not names & {
        "parsed_results",
        "parser_profiles",
        "parser_profile_verifications",
        "document_observations",
        "change_request_observations",
        "fetch_occurrences",
        "source_inputs",
    }
    assert all(
        row[5] == 1
        for row in db.execute("PRAGMA table_list")
        if row[2] == "table" and not row[1].startswith("sqlite_")
    )
    assert all(
        fk[5] in ("RESTRICT", "NO ACTION") and fk[6] in ("RESTRICT", "NO ACTION")
        for table in names
        for fk in db.execute(f"PRAGMA foreign_key_list({table})")
    )
    for table in names:
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        assert not columns & {
            "parsed_result_uuidv4",
            "parser_profile_uuidv4",
            "publication_seq",
            "document_version_id",
        }
    assert [row[1] for row in db.execute("PRAGMA table_info(coverage_claims)")] == [
        "coverage_claim_id",
        "coverage_scope_id",
        "coverage_state",
        "observed_at_us",
        "details_json",
    ]


@pytest.mark.parametrize("mode", ["autocommit", "transaction", "savepoint"])
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE snapshots SET snapshot_id='temporary' WHERE snapshot_id='snapshot-1'",
        "UPDATE snapshots SET git_acquisition_id='run-2' WHERE snapshot_id='snapshot-1'",
        "UPDATE documents SET provider_change_request_document_id='temporary' WHERE change_request_id='pr1'",
        "UPDATE documents SET change_request_id='pr2' WHERE change_request_id='pr1'",
        "UPDATE document_state SET kind='pr-title' WHERE change_request_id='pr1'",
        "UPDATE document_state SET provider_change_request_document_id='temporary' WHERE change_request_id='pr1'",
        "UPDATE review_thread_state SET provider_resource_id='temporary' WHERE change_request_id='pr1'",
        "UPDATE change_request_state SET change_request_id='pr2' WHERE change_request_id='pr1'",
        "UPDATE text_bodies SET text_body_id=999 WHERE text_body_id=1",
        "UPDATE text_bodies SET body='changed' WHERE text_body_id=1",
        "UPDATE code_listings SET code_listing_id='temporary' WHERE code_listing_id='listing-1-commits'",
        "DELETE FROM snapshots WHERE snapshot_id='snapshot-1'",
        "DELETE FROM text_bodies WHERE text_body_id=1",
    ],
)
def test_parent_identity_and_facts_fixed(target, mode, sql):
    if mode == "transaction":
        target.execute("BEGIN")
    if mode == "savepoint":
        target.execute("SAVEPOINT attempt")
    with pytest.raises(sqlite3.IntegrityError):
        target.execute(sql)
    if mode == "savepoint":
        target.execute("ROLLBACK TO attempt")
        target.execute("RELEASE attempt")
    if mode == "transaction":
        target.execute("COMMIT")
    assert target.execute(
        "SELECT body FROM text_bodies WHERE text_body_id=1"
    ).fetchone() == ("1",)
    assert target.execute(
        "SELECT state FROM eligible_change_request_state WHERE change_request_id='pr1'"
    ).fetchone() == ("open",)


@pytest.mark.parametrize("failure", ["identity", "body", "deferred-fk"])
def test_reviewed_multi_statement_attack_rolls_back_unit_and_revision(target, failure):
    before = target.execute("SELECT local_revision FROM database_identity").fetchone()[
        0
    ]
    with pytest.raises(sqlite3.IntegrityError), atomic_unit(target):
        assert (
            admit_document(target, body="changed", clock=TIME + 1).status == "accepted"
        )
        target.execute("UPDATE database_identity SET local_revision=local_revision+1")
        if failure == "identity":
            target.execute(
                "UPDATE document_state SET change_request_id='pr2' WHERE change_request_id='pr1'"
            )
        elif failure == "body":
            target.execute("UPDATE text_bodies SET body='corrupt' WHERE text_body_id=1")
        else:
            put(
                target,
                "jobs",
                job_id="deferred",
                kind="sync",
                request="{}",
                current_attempt=1,
            )
    assert (
        target.execute("SELECT local_revision FROM database_identity").fetchone()[0]
        == before
    )
    assert target.execute(
        "SELECT text_body_sha256 FROM document_state WHERE change_request_id='pr1'"
    ).fetchone()[0] == text_body_sha256("1")
    assert target.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 2
    assert not target.in_transaction


@pytest.mark.parametrize(
    "table", ["change_request_state", "document_state", "review_thread_state"]
)
@pytest.mark.parametrize(
    "owner_field,value",
    [
        ("repository_uuidv4", repository_uuid(2)),
        ("repository_binding_id", "binding-2"),
        ("service_instance_uuidv4", "00000000-0000-4000-8000-000000000102"),
    ],
)
def test_cross_owner_and_parent_deletion(target, table, owner_field, value):
    with pytest.raises(sqlite3.IntegrityError):
        target.execute(
            f"UPDATE {table} SET {owner_field}=? WHERE change_request_id='pr1'",
            (value,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        target.execute("DELETE FROM change_requests WHERE change_request_id='pr1'")


@pytest.mark.parametrize("recursive", [0, 1])
@pytest.mark.parametrize(
    "table,where",
    [
        ("snapshots", "snapshot_id='snapshot-1'"),
        ("documents", "change_request_id='pr1'"),
        ("review_threads", "change_request_id='pr1'"),
        ("text_bodies", "text_body_id=1"),
        ("code_listings", "code_listing_id='listing-1-commits'"),
    ],
)
def test_replace_upsert_and_same_repo_reassignment(target, recursive, table, where):
    target.execute(f"PRAGMA recursive_triggers={recursive}")
    with pytest.raises(sqlite3.IntegrityError):
        target.execute(
            f"INSERT OR REPLACE INTO {table} SELECT * FROM {table} WHERE {where}"
        )
    put(
        target,
        "git_acquisitions",
        git_acquisition_id="other-run",
        repository_uuidv4=repository_uuid(1),
        kind="git",
        request="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        target.execute(
            "UPDATE snapshots SET git_acquisition_id='other-run' WHERE snapshot_id='snapshot-1'"
        )


def test_bootstrap_and_rollback_needs_no_publication(target):
    before = target.execute("SELECT local_revision FROM database_identity").fetchone()[
        0
    ]
    with pytest.raises(RuntimeError), atomic_unit(target):
        result = admit_document(target, kind="pr-title", body="new", clock=TIME + 1)
        assert result.status == "accepted"
        assert (
            target.execute(
                "SELECT count(*) FROM eligible_document_state WHERE kind='pr-title'"
            ).fetchone()[0]
            == 1
        )
        raise RuntimeError("midway failure")
    assert not target.execute(
        "SELECT 1 FROM document_state WHERE kind='pr-title'"
    ).fetchall()
    assert (
        target.execute("SELECT local_revision FROM database_identity").fetchone()[0]
        == before
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
        put(target, "git_objects", **fields)


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE code_listing_progress SET state='invented' WHERE code_listing_id='listing-1-commits'",
        "UPDATE code_listing_progress SET page_count=-1 WHERE code_listing_id='listing-1-commits'",
        "UPDATE code_listing_progress SET state='complete' WHERE code_listing_id='listing-1-commits'",
        "UPDATE document_state SET body_status='present',text_body_sha256=NULL WHERE change_request_id='pr1'",
        "UPDATE document_state SET body_status='provider-null' WHERE change_request_id='pr1'",
    ],
)
def test_json_and_listing_state(target, sql):
    with pytest.raises(sqlite3.IntegrityError):
        target.execute(sql)


@pytest.mark.parametrize("settings", ["[]", "invalid-json", '"scalar"'])
def test_source_settings_insert_requires_json_object(target, settings):
    with pytest.raises(sqlite3.IntegrityError):
        put(
            target,
            "sources",
            source_id="invalid-settings",
            source_registration_uuidv4="00000000-0000-4000-8000-000000000202",
            service_instance_uuidv4=SERVICE,
            discovery_kind="github_inventory",
            name="synthetic",
            settings=settings,
        )


def test_git_meaning_and_multiple_ref_origins(target):
    body = b"canonical blob"
    oid = hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).digest()
    obj = put(
        target,
        "git_objects",
        object_format="sha1",
        oid=oid,
        type="blob",
        size=len(body),
        verified=1,
    ).lastrowid
    payload = intern_payload(target, body, representation="git-object-raw-v1")
    put(
        target,
        "git_object_payloads",
        git_object_id=obj,
        payload_representation=payload.representation,
        payload_sha256=payload.sha256,
    )
    put(
        target,
        "repository_object_sources",
        repository_uuidv4=repository_uuid(1),
        git_object_id=obj,
        git_acquisition_id="run-1",
    )
    root = put(
        target,
        "acquisition_roots",
        git_acquisition_id="run-1",
        repository_uuidv4=repository_uuid(1),
        object_format="sha1",
        oid=oid,
        role="traversal",
        complete=0,
    ).lastrowid
    for ordinal, name in enumerate((b"refs/heads/main", b"refs/heads/alias")):
        put(
            target,
            "ref_observations",
            snapshot_id="snapshot-1",
            repository_uuidv4=repository_uuid(1),
            raw_ref_name=name,
            kind="head",
            object_format="sha1",
            target_oid=oid,
            target_type="blob",
        )
        put(
            target,
            "root_origins",
            acquisition_root_id=root,
            origin_kind="ref",
            raw_ref_name=name,
            source_ordinal=ordinal,
            snapshot_id="snapshot-1",
            repository_uuidv4=repository_uuid(1),
        )
    assert (
        target.execute(
            "SELECT count(*) FROM root_origins WHERE acquisition_root_id=?", (root,)
        ).fetchone()[0]
        == 2
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            target,
            "root_origins",
            acquisition_root_id=root,
            origin_kind="ref",
            raw_ref_name=b"no-ref",
            source_ordinal=2,
            snapshot_id="snapshot-1",
            repository_uuidv4=repository_uuid(1),
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            target,
            "commits",
            git_object_id=obj,
            tree_format="sha1",
            tree_oid=oid,
            parent_count=0,
            raw_headers=b"",
            raw_message=b"",
        )


def test_body_sharing_preserves_current_a_b_a_and_field_times(target):
    for delta, body in enumerate(("A", "B", "A"), 1):
        assert (
            admit_document(
                target,
                body=body,
                clock=TIME + delta,
                observed_at_us=TIME + delta,
                parser_version=str(delta),
            ).status
            == "accepted"
        )
    row = target.execute(
        "SELECT text_body_sha256,field_evidence_json FROM document_state WHERE change_request_id='pr1'"
    ).fetchone()
    assert row[0] == text_body_sha256("A")
    assert json.loads(row[1])['["body"]']["parser_version"] == "3"
    assert (
        target.execute(
            "SELECT count(*) FROM document_state WHERE change_request_id='pr1'"
        ).fetchone()[0]
        == 1
    )
    assert target.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 4


def test_listing_scope_context_partial_complete(target):
    for listing in ("listing-1-commits", "listing-1-files"):
        target.execute(
            "UPDATE code_listing_progress SET state='complete',terminal=1,context_proven=1,page_count=1 WHERE code_listing_id=?",
            (listing,),
        )
    common = dict(
        change_request_id="pr1",
        repository_uuidv4=repository_uuid(1),
        commit_code_listing_id="listing-1-commits",
        file_code_listing_id="listing-1-files",
        state="complete",
        object_format="sha1",
        base_oid=B,
        parser_module=__name__,
        parser_version="1",
        details_json="{}",
    )
    put(
        target,
        "code_assessments",
        code_assessment_id="assessment",
        head_oid=H,
        **common,
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            target, "code_assessments", code_assessment_id="stale", head_oid=B, **common
        )
    with pytest.raises(sqlite3.IntegrityError):
        target.execute(
            "UPDATE code_assessments SET head_oid=? WHERE code_assessment_id='assessment'",
            (B,),
        )
    assert (
        admit_pr(
            target, head_oid=(b"c" * 20).hex(), object_format="sha1", clock=TIME + 1
        ).status
        == "accepted"
    )
    assert target.execute("SELECT head_oid FROM code_assessments").fetchone()[0] == H
    assert (
        target.execute(
            "SELECT head_oid FROM change_request_state WHERE change_request_id='pr1'"
        ).fetchone()[0]
        != H
    )


def test_resume_scope_and_immutable_scan(target):
    put(
        target,
        "incremental_scans",
        incremental_scan_id="scan",
        resume_scope_id="scope-1-commits",
        fetch_collection_id="1-commits",
        scan_started_at_us=TIME,
        safe_watermark_us=TIME,
        evidence="{}",
    )
    with pytest.raises(sqlite3.IntegrityError):
        target.execute(
            "UPDATE incremental_scans SET safe_watermark_us=? WHERE incremental_scan_id='scan'",
            (TIME + 1,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            target,
            "resume_cursors",
            resume_scope_id="scope-2-commits",
            incremental_scan_id="scan",
            reusable=1,
        )
    assert (
        target.execute("SELECT count(*) FROM eligible_document_state").fetchone()[0]
        == 2
    )


def test_old_cache_and_job_runtime_are_not_reactivated(target):
    put(
        target,
        "cache_locators",
        cache_locator_id="old-cache",
        repository_uuidv4=repository_uuid(1),
        path="/synthetic/cache",
        access="source_readonly",
        state="available",
    )
    with pytest.raises(sqlite3.IntegrityError):
        put(
            target,
            "active_cache_entries",
            active_cache_entry_id="active",
            cache_locator_id="old-cache",
            generation=1,
            state="active",
            last_used_us=TIME,
            bytes=0,
        )
    put(target, "jobs", job_id="job", kind="legacy", request="{}")
    with pytest.raises(sqlite3.IntegrityError):
        put(
            target,
            "job_attempts",
            job_id="job",
            attempt=0,
            state="running",
            checkpoint="{}",
        )
    put(
        target,
        "job_attempts",
        job_id="job",
        attempt=5,
        state="interrupted",
        checkpoint="{}",
    )
    target.execute("UPDATE jobs SET current_attempt=5 WHERE job_id='job'")
    assert target.execute(
        "SELECT attempt FROM job_attempts WHERE job_id='job'"
    ).fetchall() == [(5,)]


def test_distinct_natural_documents_survive_shared_body(target):
    assert admit_document(target, kind="pr-title", body="1").status == "accepted"
    assert (
        target.execute(
            "SELECT count(*) FROM document_state WHERE text_body_sha256=?",
            (text_body_sha256("1"),),
        ).fetchone()[0]
        == 2
    )
    assert target.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 2


def test_listing_commit_oid_format_matches_context(target):
    with pytest.raises(sqlite3.IntegrityError):
        put(
            target,
            "code_commits",
            code_listing_id="listing-1-commits",
            position=0,
            repository_uuidv4=repository_uuid(1),
            object_format="sha256",
            oid=b"x" * 32,
            metadata="{}",
        )


def test_known_empty_terminal_differs_from_no_terminal(target):
    proof = CurrentCollectionProof(target)
    assert proof.evidence("1-commits") is None
    proof.page(
        "1-commits", 0, 100, None, [], parser_module=__name__, parser_version="1"
    )
    assert proof.evidence("1-commits") == {
        "kind": "current-resource-pages-v1",
        "terminal": True,
        "page_ordinals": [0],
    }
    proof.page(
        "2-commits", 0, 100, "next", [], parser_module=__name__, parser_version="1"
    )
    assert proof.evidence("2-commits") is None
    assert (
        target.execute("SELECT count(*) FROM eligible_change_request_state").fetchone()[
            0
        ]
        == 2
    )


@pytest.mark.parametrize(
    "table,data",
    [
        (
            "change_request_state",
            candidate(state="closed", state_payload={"response": "opaque"}),
        ),
        (
            "document_state",
            candidate(
                kind="pr-body",
                provider_change_request_document_id="123",
                body="x",
                state_payload={},
            ),
        ),
    ],
)
def test_unknown_api_fields_cannot_become_response_archive(target, table, data):
    with pytest.raises(CatalogError):
        CurrentApiState(target).admit(table, data, source="import")
