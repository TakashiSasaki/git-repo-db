"""Fixtures for P7 adversarial recovery integration testing."""

import hashlib
import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.application.recovery import RecoveryService


@pytest.fixture
def repo_uuid():
    return str(uuid4())


@pytest.fixture
def instance_uuid():
    return str(uuid4())


@pytest.fixture
def recovery_service():
    return RecoveryService()


@pytest.fixture
def synthetic_catalog(tmp_path, repo_uuid, instance_uuid):
    catalog_dir = tmp_path / "catalog"
    catalog_dir.mkdir(parents=True)

    core_path = catalog_dir / "core.sqlite3"
    ctx_path = catalog_dir / "context.sqlite3"
    op_path = catalog_dir / "operational.sqlite3"
    search_path = catalog_dir / "search.sqlite3"

    initialize(core_path, "core", repo_uuid, instance_uuid)
    initialize(ctx_path, "context", repo_uuid, instance_uuid)
    initialize(op_path, "operational", repo_uuid, instance_uuid)
    initialize(search_path, "search", repo_uuid, instance_uuid)

    # Populate sample valid Git Core objects
    core_conn = sqlite3.connect(str(core_path))
    sample_commit_body = b"tree 0000000000000000000000000000000000000000\nauthor Test <test@example.com> 1700000000 +0000\ncommitter Test <test@example.com> 1700000000 +0000\n\nInitial commit\n"
    sample_commit_oid = hashlib.sha1(
        b"commit " + str(len(sample_commit_body)).encode() + b"\0" + sample_commit_body
    ).hexdigest()

    # Check tables in core
    tables = [
        r[0]
        for r in core_conn.execute(
            "SELECT name FROM sqlite_schema WHERE type='table'"
        ).fetchall()
    ]
    if "git_object_bytes" in tables:
        core_conn.execute(
            "INSERT INTO git_object_bytes(object_oid, object_type, raw_bytes) VALUES(?, ?, ?)",
            (sample_commit_oid, "commit", sample_commit_body),
        )
    core_conn.commit()
    core_conn.close()

    # Populate sample Context documents if table exists
    ctx_conn = sqlite3.connect(str(ctx_path))
    ctx_tables = [
        r[0]
        for r in ctx_conn.execute(
            "SELECT name FROM sqlite_schema WHERE type='table'"
        ).fetchall()
    ]
    if "change_request_documents" in ctx_tables:
        ctx_conn.execute(
            "INSERT INTO change_request_documents(document_id, content) VALUES(?, ?)",
            ("doc-1", "Sample review text for PR #1"),
        )
    ctx_conn.commit()
    ctx_conn.close()

    return catalog_dir
