"""Fixtures for P7 adversarial recovery integration testing under ADR 0026."""

from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_schema import connect as p1_connect
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    NativeObject,
    NotesProof,
    native_oid,
)


@pytest.fixture
def repo_uuid() -> str:
    return str(uuid4())


@pytest.fixture
def instance_uuid() -> str:
    return str(uuid4())


@pytest.fixture
def recovery_service() -> RecoveryService:
    return RecoveryService()


def make_native(fmt: str, kind: str, body: bytes) -> NativeObject:
    oid_hex = native_oid(fmt, kind, body)
    return NativeObject(
        oid=OID(fmt, oid_hex),
        native_type=kind,
        body=body,
        declared_size=len(body),
        digest_sha256=hashlib.sha256(body).hexdigest(),
    )


def make_tree(fmt: str, entries: list[tuple[bytes, bytes, str]]) -> NativeObject:
    sorted_entries = sorted(
        entries,
        key=lambda item: item[1] + (b"/" if item[0] == b"40000" else b"\0"),
    )
    chunks = []
    for mode, name, target_hex in sorted_entries:
        chunks.append(mode + b" " + name + b"\0" + bytes.fromhex(target_hex))
    return make_native(fmt, "tree", b"".join(chunks))


def make_commit(
    fmt: str,
    tree_oid: str,
    parents: list[str],
    *,
    author: str = "Test Author <test@example.com> 1700000000 +0000",
    committer: str = "Test Committer <test@example.com> 1700000000 +0000",
    message: str = "Initial commit\n",
) -> NativeObject:
    lines = [f"tree {tree_oid}"]
    for parent in parents:
        lines.append(f"parent {parent}")
    lines.append(f"author {author}")
    lines.append(f"committer {committer}")
    raw = ("\n".join(lines) + "\n\n" + message).encode("utf-8")
    return make_native(fmt, "commit", raw)


def make_tag(
    fmt: str,
    target_oid: str,
    target_type: str = "commit",
    tag_name: str = "v1.0.0",
    *,
    tagger: str = "Test Tagger <tagger@example.com> 1700000100 +0000",
    message: str = "Release v1.0.0 tag\n",
) -> NativeObject:
    lines = [
        f"object {target_oid}",
        f"type {target_type}",
        f"tag {tag_name}",
        f"tagger {tagger}",
    ]
    raw = ("\n".join(lines) + "\n\n" + message).encode("utf-8")
    return make_native(fmt, "tag", raw)


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

    budget = UnlimitedWorkBudget()

    # Populate real Git objects via GitCore
    core = GitCore(core_path)
    core.admit_repository(repo_uuid)

    tree = make_tree("sha1", [(b"100644", b"README.md", "1" * 40)])
    commit = make_commit("sha1", tree.oid.full_oid, [])
    tag = make_tag("sha1", commit.oid.full_oid)

    core.admit_metadata(tree, str(uuid4()), budget)
    core.admit_metadata(commit, str(uuid4()), budget)
    core.admit_metadata(tag, str(uuid4()), budget)

    # Populate a real verified Note
    note_blob = make_native(
        "sha1", "blob", b"Reviewed-by: Admin <admin@example.com>\nApproved!\n"
    )
    notes_tree = make_tree(
        "sha1",
        [(b"100644", commit.oid.full_oid.encode("ascii"), note_blob.oid.full_oid)],
    )
    cap_origin = str(uuid4())
    cap_id = str(uuid4())
    capture = Capture(
        cap_origin,
        cap_id,
        repo_uuid,
        "local-notes",
        "refs/notes/commits",
        notes_tree.oid,
    )
    notes_proof = NotesProof(
        capture=capture,
        target=commit.oid,
        note=note_blob.oid,
        path=commit.oid.full_oid,
        structures=(notes_tree,),
    )
    core.admit_capture(capture)
    core.admit_note(notes_proof, note_blob, str(uuid4()), budget)

    # Populate Context text body via ContextStore
    ctx_conn = p1_connect(ctx_path, "context")
    ctx_store = ContextStore(ctx_conn)
    ctx_store.text("Sample review document content for PR #1")
    ctx_conn.close()

    return catalog_dir
