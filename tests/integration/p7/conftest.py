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
from repo_catalog.domain.p1_core import OID, NativeObject, native_object_oid
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
    oid_hex = native_object_oid(fmt, kind, body)
    return NativeObject(
        object_oid=OID(fmt, oid_hex),
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
    tree_object_oid: str,
    parents: list[str],
    *,
    author: str = "Test Author <test@example.com> 1700000000 +0000",
    committer: str = "Test Committer <test@example.com> 1700000000 +0000",
    message: str = "Initial commit\n",
) -> NativeObject:
    lines = [f"tree {tree_object_oid}"]
    for parent in parents:
        lines.append(f"parent {parent}")
    lines.append(f"author {author}")
    lines.append(f"committer {committer}")
    raw = ("\n".join(lines) + "\n\n" + message).encode("utf-8")
    return make_native(fmt, "commit", raw)


def make_tag(
    fmt: str,
    target_object_oid: str,
    target_type: str = "commit",
    tag_name: str = "v1.0.0",
    *,
    tagger: str = "Test Tagger <tagger@example.com> 1700000100 +0000",
    message: str = "Release v1.0.0 tag\n",
) -> NativeObject:
    lines = [
        f"object {target_object_oid}",
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
    commit = make_commit("sha1", tree.object_oid.object_oid, [])
    tag = make_tag("sha1", commit.object_oid.object_oid)

    core.admit_metadata(tree, "33333333-3333-4333-8333-333333333333", budget)
    core.admit_metadata(commit, "44444444-4444-4444-8444-444444444444", budget)
    core.admit_metadata(tag, "55555555-5555-4555-8555-555555555555", budget)

    # Populate a real verified Note
    note_blob = make_native(
        "sha1", "blob", b"Reviewed-by: Admin <admin@example.com>\nApproved!\n"
    )
    notes_tree = make_tree(
        "sha1",
        [
            (
                b"100644",
                commit.object_oid.object_oid.encode("ascii"),
                note_blob.object_oid.object_oid,
            )
        ],
    )
    cap_origin = "66666666-6666-4666-8666-666666666666"
    from repo_catalog.domain.p1_core import Provenance
    from repo_catalog.domain.ref_observation import (
        NotesMapping,
        NotesMappingEvidence,
        RefObservation,
        RefObservationClaim,
        RefObservationKey,
        new_uuid7,
    )

    key = RefObservationKey(cap_origin, new_uuid7())
    core.admit_ref_observation(
        RefObservation(
            key, DEFAULT_REPO_UUID, b"refs/notes/commits", "local-notes", "visible"
        )
    )
    claim = RefObservationClaim(
        key,
        Provenance("source", "read", "claim", "fixture", "1"),
        "present",
        root_object_oid=notes_tree.object_oid,
    )
    core.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        notes_tree.object_oid,
        "git-notes",
        "1",
        "native-notes-tree",
        commit.object_oid,
        note_blob.object_oid,
        commit.object_oid.object_oid,
    )
    evidence = NotesMappingEvidence(
        claim,
        mapping,
        "single-path",
        Provenance(
            "local-notes", "receiver", "path", "native-notes", "1", "receiver_intrinsic"
        ),
        (notes_tree,),
    )
    core.admit_ref_note(
        evidence, note_blob, "88888888-8888-4888-8888-888888888888", budget
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


@pytest.fixture
def restored_catalog(synthetic_catalog, tmp_path, repo_uuid, recovery_service):
    """Use the real verified-restore boundary before positive merge exercises."""
    backup, destination = tmp_path / "merge-baseline", tmp_path / "merge-target"
    recovery_service.create_consistent_backup(synthetic_catalog, backup)
    recovery_service.restore_backup(backup, destination, repo_uuid)
    return destination


def merge_preflight_input_bytes(directory):
    """Receipt bytes plus the two canonical UUIDs read before candidate work."""
    return len((directory / "p1-restored-baseline.json").read_bytes()) + 72
