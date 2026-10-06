"""Read-only usability of the independent target; entirely synthetic local bytes."""

import base64
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite.target import (
    TARGET_DDL_SHA256,
    TARGET_SCHEMA_SHA256,
    TargetReader,
    schema_digest,
)
from repo_catalog.application.target_queries import TargetQueryService
from repo_catalog.cli.main import main
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.integration.test_target_schema import put

TIME = "2026-10-05T12:00:00Z"
OID = "sha1:" + (b"c" * 20).hex()
RAW_PATH = b"odd-\xff.txt"


@pytest.fixture
def target_query_db(tmp_path):
    path = tmp_path / "target.sqlite3"
    db = sqlite3.connect(path, isolation_level=None)
    ddl = (
        Path(__file__).parents[2] / "docs/schema-hardening/target-schema.sql"
    ).read_bytes()
    assert hashlib.sha256(ddl).hexdigest() == TARGET_DDL_SHA256
    db.executescript(ddl.decode())
    assert schema_digest(db) == TARGET_SCHEMA_SHA256
    put(
        db,
        "database_identity",
        singleton=1,
        format_id="repo-catalog/catalog3-p1",
        schema_version=3,
        db_instance_id="synthetic-target",
        publication_seq=0,
        ddl_sha256=bytes.fromhex(TARGET_DDL_SHA256),
        lifecycle="building",
    )
    put(
        db,
        "service_instances",
        id="instance",
        kind="github",
        name="synthetic",
        metadata="{}",
    )
    put(
        db,
        "sources",
        id="source",
        instance_id="instance",
        discovery_kind="github_inventory",
        name="synthetic",
        settings="{}",
    )
    for repo in ("a", "b"):
        put(db, "repositories", id=repo, name="same-name", metadata="{}")
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
            "git_acquisitions",
            id="acquisition-" + repo,
            repo_id=repo,
            object_format="sha1",
            kind="legacy",
            request="{}",
            observed_at=TIME,
        )
    for ident, kind, oid, size in (
        (1, "commit", b"c" * 20, 99),
        (2, "tree", b"t" * 20, 51),
        (3, "blob", b"a" * 20, 11),
        (4, "blob", b"b" * 20, 7),
        (5, "commit", b"x" * 20, 10),
        (6, "commit", b"y" * 20, 10),
    ):
        put(
            db,
            "git_objects",
            id=ident,
            type=kind,
            object_format="sha1",
            oid=oid,
            size=size,
            verified=0,
        )
        put(
            db,
            "repository_object_sources",
            repo_id="a",
            object_id=ident,
            acquisition_id="acquisition-a",
        )
    put(
        db,
        "repository_object_sources",
        repo_id="b",
        object_id=3,
        acquisition_id="acquisition-b",
    )
    put(
        db,
        "commits",
        object_id=1,
        tree_id=2,
        raw_headers=b"synthetic headers\n",
        raw_message=b"needle commit\n",
        metadata='{"author":"synthetic"}',
    )
    for ordinal, parent in ((0, 6), (1, 5)):
        put(db, "commit_parents", commit_id=1, parent_ordinal=ordinal, parent_id=parent)
    for name, child, oid in (
        (RAW_PATH, 3, b"a" * 20),
        (b"unavailable.txt", 4, b"b" * 20),
    ):
        put(
            db,
            "tree_entries",
            tree_id=2,
            raw_name=name,
            mode=33188,
            child_format="sha1",
            child_oid=oid,
            child_id=child,
        )
    for ident, text, length, obj in ((101, "needle code", 11, 3), (102, None, 7, 4)):
        put(
            db,
            "contents",
            id=ident,
            raw_text=text,
            byte_length=length,
            text_state="eligible",
        )
        put(
            db,
            "blob_content_map",
            object_id=obj,
            content_id=ident,
            acquisition_id="acquisition-a",
        )
    put(
        db,
        "content_digests",
        content_id=101,
        representation="raw-content-v1",
        algorithm="sha256",
        digest=hashlib.sha256(b"needle code").digest(),
        pipeline_version="synthetic",
    )
    put(
        db,
        "change_requests",
        id="pr-a",
        repo_id="a",
        binding_id="binding-a",
        request_kind="pull_request",
        number=7,
    )
    for ident, observed, body in (
        (11, TIME, "A"),
        (12, "2026-10-05T13:00:00Z", "B"),
        (13, "2026-10-05T14:00:00Z", "A"),
    ):
        put(
            db,
            "change_request_observations",
            id=ident,
            change_request_id="pr-a",
            observed_at=observed,
            published=0,
            payload=json.dumps({"title": "needle title", "body": body}),
            parsed_at=TIME,
        )
    put(
        db,
        "documents",
        id="document-a",
        change_request_id="pr-a",
        kind="pr-body",
        provider_id="native",
        deleted=0,
        metadata="{}",
    )
    for ident, body in ((201, "A needle"), (202, "B")):
        put(
            db,
            "text_bodies",
            id=ident,
            body=body,
            byte_length=len(body),
            sha256=hashlib.sha256(body.encode()).digest(),
        )
    for ident, body, observed in (
        (301, 201, TIME),
        (302, 202, "2026-10-05T13:00:00Z"),
        (303, 201, "2026-10-05T14:00:00Z"),
    ):
        put(db, "document_versions", id=ident, document_id="document-a", body_id=body)
        put(
            db,
            "document_observations",
            id=ident + 100,
            document_id="document-a",
            version_id=ident,
            observed_at=observed,
            parsed_at=TIME,
            metadata="{}",
        )
    put(
        db,
        "resume_scopes",
        id="scope",
        repo_id="a",
        binding_id="binding-a",
        source_id="source",
        request_context="{}",
        parser_version="synthetic",
        profile_version="synthetic",
        confidence="legacy_unknown",
    )
    put(
        db,
        "fetch_collections",
        id="collection",
        repo_id="a",
        change_request_id="pr-a",
        source_id="source",
        kind="files",
        scope_id="scope",
        observed_at=TIME,
    )
    put(
        db,
        "code_listings",
        id="listing",
        change_request_id="pr-a",
        collection_id="collection",
        kind="files",
        scope_id="scope",
    )
    put(
        db,
        "code_listing_progress",
        listing_id="listing",
        state="partial",
        terminal=0,
        page_count=1,
        context_proven=0,
    )
    db.close()
    return path


def query(database, command, **options):
    return TargetQueryService(database, allow_building=True).query(command, options)


def test_target_cli_requires_opt_in_and_never_initializes_state(
    target_query_db, tmp_path, monkeypatch, capsys
):
    from repo_catalog.application import maintenance_service

    def forbidden(*args, **kwargs):
        raise AssertionError("Normal state or maintenance must not be opened")

    monkeypatch.setattr(maintenance_service.MaintenanceService, "__init__", forbidden)
    import socket
    import subprocess

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    state = tmp_path / "absent-state"
    before = target_query_db.read_bytes()
    args = [
        "--state-dir",
        str(state),
        "--format",
        "json",
        "target",
        "--database",
        str(target_query_db),
    ]
    assert main([*args, "repos"]) == 5
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "TARGET_NOT_READY"
    assert main([*args, "--allow-building", "repos"]) == 3
    output = json.loads(capsys.readouterr().out)
    assert output["catalog"]["lifecycle"] == "building"
    assert {r["id"] for r in output["data"]["items"]} == {"a", "b"}
    assert output["coverage"]["complete_for_requested_scope"] is False
    assert not state.exists() and target_query_db.read_bytes() == before
    assert sorted(p.name for p in target_query_db.parent.iterdir()) == [
        target_query_db.name
    ]


def test_target_contract_rejection_sidecars_and_query_only(target_query_db):
    with TargetReader(target_query_db, allow_building=True) as reader:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.execute("DELETE FROM repositories")
    sidecar = Path(str(target_query_db) + "-journal")
    sidecar.write_bytes(b"pending")
    with pytest.raises(CatalogError) as error:
        TargetReader(target_query_db, allow_building=True)
    assert error.value.code == "TARGET_BUSY" and sidecar.read_bytes() == b"pending"
    sidecar.unlink()
    db = sqlite3.connect(target_query_db)
    db.execute("CREATE TABLE unexpected(value)")
    db.commit()
    db.close()
    with pytest.raises(CatalogError) as error:
        TargetReader(target_query_db, allow_building=True)
    assert error.value.code == "SCHEMA_ERROR"


def test_target_rejected_lifecycle_is_never_admitted(target_query_db):
    with sqlite3.connect(target_query_db) as db:
        db.execute("UPDATE database_identity SET lifecycle='rejected'")
    with pytest.raises(CatalogError) as error:
        query(target_query_db, "repos")
    assert error.value.code == "TARGET_NOT_READY"


def test_commit_order_and_repository_ownership(target_query_db):
    result = query(target_query_db, "commit", repo="a", commit=OID)
    item = result.data["items"][0]
    assert [(r["ordinal"], r["object_id"]) for r in item["parents"]] == [(0, 6), (1, 5)]
    assert item["raw_headers"] == b"synthetic headers\n"
    assert item["raw_message"] == b"needle commit\n" and item["tree"]["object_id"] == 2
    with pytest.raises(CatalogError) as error:
        query(target_query_db, "commit", repo="b", commit=OID)
    assert error.value.code == "NOT_FOUND"


def test_raw_tree_paths_file_text_digests_and_missing_content(target_query_db):
    tree = query(target_query_db, "tree", repo="a", commit=OID).data["items"]
    odd = next(item for item in tree if item["object_id"] == 3)
    assert base64.b64decode(odd["path_b64"]) == RAW_PATH and odd["path_utf8"] is None
    result = query(
        target_query_db, "file", repo="a", commit=OID, path_b64=odd["path_b64"]
    )
    item = result.data["items"][0]
    assert item["text"] == "needle code" and item["raw_available"] is True
    assert item["digests"][0]["digest"] == hashlib.sha256(b"needle code").hexdigest()
    missing = query(
        target_query_db, "file", repo="a", commit=OID, path="unavailable.txt"
    )
    assert missing.data["items"][0]["text"] is None
    assert missing.data["items"][0]["raw_available"] is False
    assert any(row["reason"] == "body_not_saved" for row in missing.coverage.missing)


def test_pr_history_retains_a_b_a_versions_observation_times_and_partial_listings(
    target_query_db,
):
    result = query(target_query_db, "pr", repo="a", number=7)
    rows = result.data["items"]
    versions = [row for row in rows if row["record_kind"] == "document_version"]
    assert [(row["id"], row["body_id"], row["body"]) for row in versions] == [
        (301, 201, "A needle"),
        (302, 202, "B"),
        (303, 201, "A needle"),
    ]
    observations = [row for row in rows if row["record_kind"] == "document_observation"]
    assert [(row["version_id"], row["observed_at"]) for row in observations] == [
        (301, TIME),
        (302, "2026-10-05T13:00:00Z"),
        (303, "2026-10-05T14:00:00Z"),
    ]
    assert any(
        row["reason"] == "code_listing_incomplete" and row["page_count"] == 1
        for row in result.coverage.missing
    )
    assert rows[0]["current_observation_id"] is None
    service = TargetQueryService(target_query_db, allow_building=True)
    first = service.query("pr", {"repo": "a", "number": 7}, limit=2)
    rest = service.query(
        "pr", {"repo": "a", "number": 7}, offset=first.data["page"]["next_offset"]
    )
    assert first.data["items"] + rest.data["items"] == rows


def test_scan_search_uses_available_originals_and_reports_missing(target_query_db):
    code = query(target_query_db, "search", kind="code", literal="needle")
    assert {r["repo_id"] for r in code.data["items"]} == {"a", "b"}
    assert any(
        r["content_id"] == 102
        for r in code.coverage.missing
        if r["reason"] == "body_not_saved"
    )
    commits = query(
        target_query_db, "search", kind="commits", literal="needle", repo="a"
    )
    assert [r["object_id"] for r in commits.data["items"]] == [1]
    pr = query(target_query_db, "search", kind="pr", literal="needle", repo="a")
    assert [
        r["version_id"] for r in pr.data["items"] if r["record_kind"] == "document"
    ] == [301, 303]
    assert [
        r["observation_id"]
        for r in pr.data["items"]
        if r["record_kind"] == "observation"
    ] == [11, 12, 13]
    assert pr.execution["backend"] == "scan"
    before = target_query_db.read_bytes()
    empty = query(target_query_db, "search", kind="code", literal="unsaved text")
    assert (
        empty.data["items"] == []
        and empty.coverage.complete_for_requested_scope is False
    )
    assert target_query_db.read_bytes() == before
    limited = TargetQueryService(target_query_db, allow_building=True).query(
        "search", {"kind": "code", "literal": "needle"}, limit=1
    )
    assert limited.data["page"]["has_more"] is True
    assert any(
        row["content_id"] == 102
        for row in limited.coverage.missing
        if row["reason"] == "body_not_saved"
    )


def test_wrong_format_and_missing_target_are_not_initialized(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(CatalogError) as error:
        TargetReader(missing, allow_building=True)
    assert error.value.code == "NOT_FOUND" and not missing.exists()
    sqlite3.connect(missing).close()
    before = missing.read_bytes()
    with pytest.raises(CatalogError) as error:
        TargetReader(missing, allow_building=True)
    assert error.value.code == "SCHEMA_ERROR" and missing.read_bytes() == before


def test_query_cancellation_and_change_detection(target_query_db):
    token = CancellationToken(cancelled=True)
    with pytest.raises(CatalogError) as error:
        TargetQueryService(target_query_db, allow_building=True, token=token).query(
            "repos"
        )
    assert error.value.code == "CANCELLED"
    with TargetReader(target_query_db, allow_building=True) as reader:
        with sqlite3.connect(target_query_db) as writer:
            writer.execute("UPDATE database_identity SET lifecycle='validated'")
        with pytest.raises(CatalogError) as error:
            reader.ensure_unchanged()
        assert error.value.code == "TARGET_BUSY"
