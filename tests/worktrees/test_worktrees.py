"""Standalone tests: no shared runtime, Core, Access, or filesystem imports."""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from repo_catalog.worktrees import WorktreeCatalog, WorktreeError, discover_topology
from repo_catalog.worktrees.models import native_path, observation_uuid


def git(path, *args):
    env = dict(os.environ)
    for key in tuple(env):
        if key.startswith("GIT_"):
            env.pop(key)
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_AUTHOR_NAME="test",
        GIT_AUTHOR_EMAIL="test@example.invalid",
        GIT_COMMITTER_NAME="test",
        GIT_COMMITTER_EMAIL="test@example.invalid",
        GIT_ALLOW_PROTOCOL="file",
    )
    result = subprocess.run(
        ["git", "-C", str(path), *args], env=env, capture_output=True, check=True
    )
    return result.stdout


def repository(path, *, bare=False, object_format="sha1"):
    path.mkdir()
    git(
        path,
        "init",
        "-q",
        "--initial-branch=main",
        f"--object-format={object_format}",
        *(["--bare"] if bare else []),
    )
    if not bare:
        (path / "tracked.txt").write_text("worktree data\n")
        git(path, "add", "tracked.txt")
        git(path, "commit", "-qm", "initial")
    return path


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_linked_worktrees_share_storage_and_keep_own_heads(tmp_path, object_format):
    primary = repository(tmp_path / "main tree 日本語", object_format=object_format)
    linked = tmp_path / "linked tree"
    git(primary, "worktree", "add", "-q", "--detach", str(linked))
    git(primary, "worktree", "lock", "--reason", "held for test", str(linked))
    result = discover_topology(linked)
    assert result.status == "complete", result
    assert len(result.entries) == 2
    by_root = {entry.root_path: entry for entry in result.entries}
    first, second = by_root[native_path(primary)], by_root[native_path(linked)]
    assert first.common_dir == second.common_dir == native_path(primary / ".git")
    assert first.git_dir != second.git_dir
    assert second.branch is None and second.locked == b"held for test"
    assert first.head_oid == second.head_oid
    assert first.object_format == object_format


def test_distant_bare_and_missing_registered_worktree(tmp_path):
    bare = repository(tmp_path / "distant.git", bare=True)
    checkout = tmp_path / "checkout"
    git(bare, "worktree", "add", "-q", "--orphan", str(checkout))
    result = discover_topology(bare)
    assert result.status == "complete", result
    assert len(result.entries) == 2
    assert next(entry for entry in result.entries if not entry.bare).head_oid is None
    shutil.rmtree(checkout)
    missing = discover_topology(bare)
    assert missing.status == "partial"
    assert any(
        entry.root_path == native_path(checkout) and entry.error
        for entry in missing.entries
    )
    assert (bare / "worktrees").exists()


def test_separate_git_directory_and_plain_directory(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    external = tmp_path / "external.git"
    git(checkout, "init", "-q", "--separate-git-dir", str(external))
    result = discover_topology(checkout, expand=False)
    assert result.status == "complete", result
    assert result.entries[0].git_dir == native_path(external)
    assert result.entries[0].root_path == native_path(checkout)
    plain = tmp_path / "plain"
    plain.mkdir()
    assert discover_topology(plain).status == "not_git"
    (plain / ".git").write_text("gitdir: /missing/unsupported\n")
    assert discover_topology(plain).status == "error"


def test_submodule_is_its_own_repository(tmp_path):
    source = repository(tmp_path / "source")
    parent = repository(tmp_path / "parent")
    git(
        parent,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(source),
        "child",
    )
    parent_result = discover_topology(parent, expand=False)
    child_result = discover_topology(parent / "child", expand=False)
    assert child_result.status == "complete", child_result
    assert child_result.entries[0].root_path == native_path(parent / "child")
    assert child_result.common_dir != parent_result.common_dir


def test_git_selection_environment_cannot_redirect_discovery(tmp_path, monkeypatch):
    source = repository(tmp_path / "source")
    other = repository(tmp_path / "other")
    marker = tmp_path / "trace"
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_TRACE", str(marker))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.worktree")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(other))
    result = discover_topology(source)
    assert result.status == "complete"
    assert result.entries[0].root_path == native_path(source)
    assert not marker.exists()
    limited = discover_topology(source, output_limit_bytes=1)
    assert limited.status == "error" and limited.errors == ("LIMIT",)


def test_history_independent_references_and_checked_backup(tmp_path):
    source = repository(tmp_path / "source")
    database = tmp_path / "worktrees.sqlite3"
    with WorktreeCatalog.initialize(database) as catalog:
        first = catalog.discover(source)
        second = catalog.discover(source)
        assert first.observation_uuid != second.observation_uuid
        assert len(catalog.list_discoveries()) == 2
        filesystem_namespace, scan = str(uuid4()), observation_uuid()
        catalog.record_scan_reference(
            first.observation_uuid,
            first.entries[0].root_path,
            filesystem_namespace,
            scan,
        )
        assert (
            catalog.scan_references(filesystem_namespace, scan)[0]["observation_uuid"]
            == first.observation_uuid
        )
        repo1, repo2 = str(uuid4()), str(uuid4())
        catalog.link_repository(first.common_dir, repo1)
        catalog.link_repository(first.common_dir, repo2)
        assert set(catalog.repository_links(first.common_dir)) == {repo1, repo2}
        with pytest.raises(sqlite3.IntegrityError):
            catalog._db.execute("DELETE FROM observations")
        catalog._db.rollback()
        backup = tmp_path / "backup"
        manifest = catalog.backup(backup)
        assert (
            manifest["sha256"]
            == hashlib.sha256((backup / "worktrees.sqlite3").read_bytes()).hexdigest()
        )
    shutil.rmtree(source)
    with WorktreeCatalog.restore(backup, tmp_path / "restored.sqlite3") as restored:
        assert restored.get_discovery(first.observation_uuid) == first
        assert restored.verify()["status"] == "complete"
    with pytest.raises(FileExistsError):
        WorktreeCatalog.restore(backup, tmp_path / "restored.sqlite3")
    manifest["sha256"] = "0" * 64
    (backup / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(WorktreeError, match="checksum"):
        WorktreeCatalog.restore(backup, tmp_path / "failed.sqlite3")
    assert not (tmp_path / "failed.sqlite3").exists()
    assert not (tmp_path / "core.sqlite3").exists()


def test_readonly_open_and_schema_tampering_refused(tmp_path):
    database = tmp_path / "worktrees.sqlite3"
    with WorktreeCatalog.initialize(database):
        pass
    with WorktreeCatalog.open(database, readonly=True) as catalog:
        with pytest.raises(WorktreeError, match="read-only"):
            catalog.discover(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER observations_no_update")
    with pytest.raises(WorktreeError, match="schema"):
        WorktreeCatalog.open(database, readonly=True)


def test_restore_binds_manifest_to_copied_bytes_before_destination(
    tmp_path, monkeypatch
):
    from repo_catalog.worktrees import catalog as storage

    namespace = str(uuid4())
    with WorktreeCatalog.initialize(
        tmp_path / "original.sqlite3", namespace_uuid=namespace
    ) as original:
        original.backup(tmp_path / "backup")
    replacement = tmp_path / "replacement.sqlite3"
    with WorktreeCatalog.initialize(replacement, namespace_uuid=namespace) as other:
        other.link_repository(native_path(tmp_path / "another.git"), str(uuid4()))
    source = tmp_path / "backup" / "worktrees.sqlite3"
    copy = storage._copy_snapshot

    def replace_before_pin(incoming, destination):
        if incoming == source:
            os.replace(replacement, source)
        return copy(incoming, destination)

    monkeypatch.setattr(storage, "_copy_snapshot", replace_before_pin)
    destination = tmp_path / "restored.sqlite3"
    with pytest.raises(WorktreeError, match="checksum"):
        WorktreeCatalog.restore(tmp_path / "backup", destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".worktrees-restore-*"))


def test_restore_uses_verified_stage_after_original_changes(tmp_path, monkeypatch):
    from repo_catalog.worktrees import catalog as storage

    with WorktreeCatalog.initialize(tmp_path / "original.sqlite3") as original:
        namespace = original.namespace_uuid
        original.backup(tmp_path / "backup")
    source = tmp_path / "backup" / "worktrees.sqlite3"
    copy = storage._copy_snapshot

    def alter_after_stage(incoming, destination):
        digest = copy(incoming, destination)
        if incoming == source:
            source.write_bytes(b"source replaced after staging")
        return digest

    monkeypatch.setattr(storage, "_copy_snapshot", alter_after_stage)
    with WorktreeCatalog.restore(
        tmp_path / "backup", tmp_path / "restored.sqlite3"
    ) as restored:
        assert restored.namespace_uuid == namespace
        assert restored.verify()["counts"]["repository_links"] == 0


@pytest.mark.skipif(os.name != "posix", reason="POSIX byte filenames")
def test_non_utf8_and_newline_root_paths_are_lossless(tmp_path):
    raw = os.fsencode(tmp_path) + b"/tree-\xff\n"
    source = repository(Path(os.fsdecode(raw)))
    result = discover_topology(source)
    assert result.status == "complete", result
    assert result.entries[0].root_path == raw


def test_windows_unc_volume_root_and_drive_relative_paths(monkeypatch):
    from repo_catalog.worktrees import models

    windows_paths = SimpleNamespace(
        fspath=os.fspath,
        fsdecode=os.fsdecode,
        fsencode=os.fsencode,
        name="nt",
        path=ntpath,
    )
    monkeypatch.setattr(models, "os", windows_paths)
    assert native_path(r"\\server\share") == os.fsencode(r"\\server\share")
    assert native_path("C:\\") == b"C:\\"
    with pytest.raises(WorktreeError, match="drive-relative"):
        native_path("C:relative")
