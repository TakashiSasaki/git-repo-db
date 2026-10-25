"""Fixtures for P7 adversarial recovery integration testing under ADR 0026."""

from __future__ import annotations

import hashlib
import shutil

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_schema import connect as p1_connect
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    NativeObject,
    NotesProof,
    native_oid,
)
from tests.support.context_admission import fixture_context, fixture_service


def admit_context_text(connection, text):
    """Compose text-only fixture authority and own its actual commit boundary."""
    service, _ = fixture_service(DependencySet())
    store = ContextStore(connection, authorization=service)
    with store.admission_transaction(admission=fixture_context(service)):
        return store.text(text)


DEFAULT_REPO_UUID = "11111111-1111-4111-8111-111111111111"
DEFAULT_INSTANCE_UUID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def repo_uuid() -> str:
    return DEFAULT_REPO_UUID


@pytest.fixture
def instance_uuid() -> str:
    return DEFAULT_INSTANCE_UUID


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


@pytest.fixture(scope="session")
def _synthetic_catalog_template(tmp_path_factory):
    template_dir = tmp_path_factory.mktemp("synthetic_template") / "catalog"
    template_dir.mkdir(parents=True)

    core_path = template_dir / "core.sqlite3"
    ctx_path = template_dir / "context.sqlite3"
    op_path = template_dir / "operational.sqlite3"
    search_path = template_dir / "search.sqlite3"

    initialize(core_path, "core", DEFAULT_REPO_UUID, DEFAULT_INSTANCE_UUID)
    initialize(ctx_path, "context", DEFAULT_REPO_UUID, DEFAULT_INSTANCE_UUID)
    initialize(op_path, "operational", DEFAULT_REPO_UUID, DEFAULT_INSTANCE_UUID)
    initialize(search_path, "search", DEFAULT_REPO_UUID, DEFAULT_INSTANCE_UUID)

    budget = UnlimitedWorkBudget()

    # Populate real Git objects via GitCore
    core = GitCore(core_path)
    core.admit_repository(DEFAULT_REPO_UUID)

    tree = make_tree("sha1", [(b"100644", b"README.md", "1" * 40)])
    commit = make_commit("sha1", tree.oid.full_oid, [])
    tag = make_tag("sha1", commit.oid.full_oid)

    core.admit_metadata(tree, "33333333-3333-4333-8333-333333333333", budget)
    core.admit_metadata(commit, "44444444-4444-4444-8444-444444444444", budget)
    core.admit_metadata(tag, "55555555-5555-4555-8555-555555555555", budget)

    # Populate a real verified Note
    note_blob = make_native(
        "sha1", "blob", b"Reviewed-by: Admin <admin@example.com>\nApproved!\n"
    )
    notes_tree = make_tree(
        "sha1",
        [(b"100644", commit.oid.full_oid.encode("ascii"), note_blob.oid.full_oid)],
    )
    cap_origin = "66666666-6666-4666-8666-666666666666"
    cap_id = "77777777-7777-4777-8777-777777777777"
    capture = Capture(
        cap_origin,
        cap_id,
        DEFAULT_REPO_UUID,
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
    core.admit_note(
        notes_proof, note_blob, "88888888-8888-4888-8888-888888888888", budget
    )

    # Populate Context text body via ContextStore
    ctx_conn = p1_connect(ctx_path, "context")
    admit_context_text(ctx_conn, "Sample review document content for PR #1")
    ctx_conn.close()

    return template_dir


@pytest.fixture
def synthetic_catalog(tmp_path, _synthetic_catalog_template):
    dest = tmp_path / "catalog"
    shutil.copytree(_synthetic_catalog_template, dest)
    return dest
