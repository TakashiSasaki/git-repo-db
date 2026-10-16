"""Fixtures and helpers for P5 Git acquisition, Provider intake, Paired admission, and Exchange tests."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.p1_core import OID


def git(path: Path, *args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        input=data,
        capture_output=True,
        check=True,
    ).stdout


def write_git_object(
    path: Path,
    fmt: Literal["sha1", "sha256"],
    kind: str,
    body: bytes,
) -> OID:
    out = git(path, "hash-object", "-w", "-t", kind, "--stdin", data=body)
    return OID(fmt, out.strip().decode("ascii"))


def tree_entry(mode: bytes, name: bytes, target: OID) -> bytes:
    return mode + b" " + name + b"\0" + bytes.fromhex(target.full_oid)


def build_sample_git_repo(
    path: Path,
    fmt: Literal["sha1", "sha256"] = "sha1",
) -> dict[str, OID]:
    """Initialize a bare Git repo in `fmt` with a blob, tree, root commit, child commit, annotated tag, and notes ref."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "--bare", f"--object-format={fmt}")
    blob = write_git_object(path, fmt, "blob", b"hello world\n")
    tree = write_git_object(
        path, fmt, "tree", tree_entry(b"100644", b"README.md", blob)
    )
    commit1_body = (
        f"tree {tree.full_oid}\n"
        "author Alice <alice@example.com> 1700000000 +0000\n"
        "committer Alice <alice@example.com> 1700000000 +0000\n\n"
        "Initial commit\n"
    ).encode("utf-8")
    commit1 = write_git_object(path, fmt, "commit", commit1_body)

    commit2_body = (
        f"tree {tree.full_oid}\n"
        f"parent {commit1.full_oid}\n"
        "author Bob <bob@example.com> 1700000100 +0000\n"
        "committer Bob <bob@example.com> 1700000100 +0000\n\n"
        "Second commit\n"
    ).encode("utf-8")
    commit2 = write_git_object(path, fmt, "commit", commit2_body)

    tag_body = (
        f"object {commit2.full_oid}\n"
        "type commit\n"
        "tag v1.0.0\n"
        "tagger Alice <alice@example.com> 1700000200 +0000\n\n"
        "Release v1.0.0\n"
    ).encode("utf-8")
    tag = write_git_object(path, fmt, "tag", tag_body)

    note_blob = write_git_object(path, fmt, "blob", b"Reviewed-by: CI\n")
    notes_tree = write_git_object(
        path,
        fmt,
        "tree",
        tree_entry(b"100644", commit2.full_oid.encode("ascii"), note_blob),
    )
    notes_commit_body = (
        f"tree {notes_tree.full_oid}\n"
        "author CI <ci@example.com> 1700000300 +0000\n"
        "committer CI <ci@example.com> 1700000300 +0000\n\n"
        "Notes commit\n"
    ).encode("utf-8")
    notes_commit = write_git_object(path, fmt, "commit", notes_commit_body)

    git(path, "update-ref", "refs/heads/main", commit2.full_oid)
    git(path, "update-ref", "refs/tags/v1.0.0", tag.full_oid)
    git(path, "update-ref", "refs/notes/commits", notes_commit.full_oid)

    return {
        "blob": blob,
        "tree": tree,
        "commit1": commit1,
        "commit2": commit2,
        "tag": tag,
        "note_blob": note_blob,
        "notes_tree": notes_tree,
        "notes_commit": notes_commit,
    }


def init_catalog_stores(
    directory: Path,
    *,
    repository_uuidv4: str | None = None,
    catalog_instance_uuidv4: str | None = None,
    stores: tuple[str, ...] = ("core", "context", "operational"),
) -> tuple[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    repo_id = repository_uuidv4 or str(uuid4())
    inst_id = catalog_instance_uuidv4 or str(uuid4())
    for role in stores:
        initialize(directory / f"{role}.sqlite3", role, repo_id, inst_id)
    return repo_id, inst_id


@pytest.fixture(params=["sha1", "sha256"])
def git_format(request: pytest.FixtureRequest) -> Literal["sha1", "sha256"]:
    return request.param
