"""Real Git/filesystem integration, without other catalog implementations."""

import csv
import hashlib
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from repo_catalog.local import LocalCatalog


def git(*arguments, cwd=None):
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Catalog Test",
            "-c",
            "user.email=catalog@example.invalid",
            "-c",
            "protocol.file.allow=always",
            *map(str, arguments),
        ],
        cwd=cwd,
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"},
        capture_output=True,
        check=True,
        timeout=30,
    )
    return result.stdout


def repository(path):
    path.mkdir(parents=True)
    git("init", "-b", "main", path)
    (path / "tracked.txt").write_text("tracked contents\n", encoding="utf-8")
    (path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    git("add", ".", cwd=path)
    git("commit", "-m", "fixture", cwd=path)
    return path


def rows(catalog, scan):
    return {
        os.fsdecode(entry.relative_path): entry
        for entry in catalog.filesystem.iter_entries(scan.scan_uuid)
    }


def test_expanded_worktrees_are_not_rediscovered_during_walk(tmp_path):
    first = repository(tmp_path / "first")
    second, third = tmp_path / "second", tmp_path / "third"
    git("worktree", "add", "-b", "second", second, cwd=first)
    git("worktree", "add", "-b", "third", third, cwd=first)
    nested = repository(second / "nested")
    with LocalCatalog.initialize(
        tmp_path / "files.sqlite3", tmp_path / "worktrees.sqlite3"
    ) as catalog:
        result = catalog.scan([first])
        assert result.status == "complete", result
        assert {d.requested_path for d in result.discoveries} == {
            os.fsencode(first),
            os.fsencode(nested),
        }
        assert {s.root_path for s in result.scans} == {
            os.fsencode(first),
            os.fsencode(second),
            os.fsencode(third),
        }
        for scan in result.scans:
            assert "tracked.txt" in rows(catalog, scan)
            refs = catalog.worktrees.scan_references(
                scan.namespace_uuid, scan.scan_uuid
            )
            assert sum(r["root_path"] == scan.root_path for r in refs) == 1

        # Explicit requests and later scans remain independent observations.
        explicit = catalog.scan([first, second])
        assert [d.requested_path for d in explicit.discoveries[:2]] == [
            os.fsencode(first),
            os.fsencode(second),
        ]
        assert explicit.status == "complete"
        assert len(explicit.scans) == 3
        assert (
            explicit.discoveries[0].observation_uuid
            != result.discoveries[0].observation_uuid
        )


def test_failed_explicit_alias_allows_real_path_retry(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    real = repository(parent / "repo")
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable to this test account")
    with LocalCatalog.initialize(
        tmp_path / "files.sqlite3", tmp_path / "worktrees.sqlite3"
    ) as catalog:
        discover = catalog.worktrees.discover

        def limited_alias(path, *, expand):
            if path == alias:
                return discover(path, expand=expand, output_limit_bytes=1)
            return discover(path, expand=expand)

        monkeypatch.setattr(catalog.worktrees, "discover", limited_alias)
        result = catalog.scan([alias, parent])
        assert result.status == "partial"
        failed = next(
            d for d in result.discoveries if d.requested_path == os.fsencode(alias)
        )
        assert failed.status == "error" and "LIMIT" in failed.errors
        retried = next(
            d for d in result.discoveries if d.requested_path == os.fsencode(real)
        )
        assert retried.status == "complete"
        parent_scan = next(
            s for s in result.scans if s.root_path == os.fsencode(parent)
        )
        references = catalog.worktrees.scan_references(
            parent_scan.namespace_uuid, parent_scan.scan_uuid
        )
        assert any(
            r["observation_uuid"] == retried.observation_uuid
            and r["root_path"] == os.fsencode(real)
            for r in references
        )


def test_distant_bare_repository_expands_all_worktrees_and_exports_offline(tmp_path):
    source = repository(tmp_path / "source")
    storage = tmp_path / "distant" / "storage.git"
    storage.parent.mkdir()
    git("clone", "--bare", source, storage)
    first, second = tmp_path / "first", tmp_path / "second"
    git("--git-dir", storage, "worktree", "add", first, "main")
    git("--git-dir", storage, "worktree", "add", "--detach", second, "main")
    (first / "ignored.txt").write_bytes(b"ignored but catalogued")
    (second / "untracked.txt").write_bytes(b"not committed")
    files, worktrees = tmp_path / "files.sqlite3", tmp_path / "worktrees.sqlite3"
    with LocalCatalog.initialize(files, worktrees) as catalog:
        result = catalog.scan([first, second])
        assert result.status == "complete", result
        assert {scan.root_path for scan in result.scans} == {
            os.fsencode(first),
            os.fsencode(second),
        }
        assert len(result.scans) == 2
        by_root = {scan.root_path: scan for scan in result.scans}
        first_rows = rows(catalog, by_root[os.fsencode(first)])
        assert (
            first_rows["ignored.txt"].sha256
            == hashlib.sha256(b"ignored but catalogued").hexdigest()
        )
        assert not any(
            name == ".git" or name.startswith(".git/") for name in first_rows
        )
        shutil.rmtree(first)
        shutil.rmtree(second)
        shutil.rmtree(storage)
        output = tmp_path / "offline.efu"
        catalog.export_efu([scan.scan_uuid for scan in result.scans], output)
        with output.open(encoding="utf-8", newline="") as stream:
            exported = list(csv.DictReader(stream))
        content = next(
            row for row in exported if row["Filename"].endswith("ignored.txt")
        )
        assert content["SHA256"] == first_rows["ignored.txt"].sha256
        assert content["RepoCatalog.CommonDir"] == str(storage)
        assert content["RepoCatalog.Branch"] == "refs/heads/main"


def test_nested_repository_does_not_expand_its_siblings(tmp_path):
    root = tmp_path / "ordinary"
    nested = repository(root / "nested")
    outside = tmp_path / "unselected"
    git("worktree", "add", "-b", "other", outside, cwd=nested)
    files, worktrees = tmp_path / "files.sqlite3", tmp_path / "worktrees.sqlite3"
    with LocalCatalog.initialize(files, worktrees) as catalog:
        result = catalog.scan([root])
        assert result.status == "complete", result
        assert [scan.root_path for scan in result.scans] == [os.fsencode(root)]
        assert any(
            entry.root_path == os.fsencode(nested)
            for discovery in result.discoveries
            for entry in discovery.entries
        )
        assert not any(
            entry.root_path == os.fsencode(outside)
            for discovery in result.discoveries
            for entry in discovery.entries
        )
        entries = rows(catalog, result.scans[0])
        assert "nested/tracked.txt" in {name.replace("\\", "/") for name in entries}
        assert not any(".git" in Path(name).parts for name in entries)


def test_missing_sibling_is_partial_without_losing_successful_scan(tmp_path):
    first = repository(tmp_path / "first")
    second = tmp_path / "second"
    git("worktree", "add", "-b", "other", second, cwd=first)
    shutil.rmtree(second)
    with LocalCatalog.initialize(
        tmp_path / "files.sqlite3", tmp_path / "worktrees.sqlite3"
    ) as catalog:
        result = catalog.scan([first])
        assert result.status == "partial"
        successful = next(
            scan for scan in result.scans if scan.root_path == os.fsencode(first)
        )
        assert successful.status == "complete"
        assert "tracked.txt" in rows(catalog, successful)
        output = tmp_path / "successful.efu"
        catalog.export_efu([successful.scan_uuid], output)
        assert output.exists()


def test_self_databases_excluded_and_filesystem_export_needs_no_worktree_db(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "ordinary.txt").write_text("contents", encoding="utf-8")
    files, worktrees = root / "files.sqlite3", root / "worktrees.sqlite3"
    with LocalCatalog.initialize(files, worktrees) as catalog:
        result = catalog.scan([root])
        assert result.status == "complete", result
        scan = result.scans[0]
        names = set(rows(catalog, scan))
        assert "ordinary.txt" in names
        assert not any(
            name.startswith(("files.sqlite3", "worktrees.sqlite3")) for name in names
        )
    worktrees.unlink()
    with LocalCatalog.open(files, readonly=True) as catalog:
        output = tmp_path / "plain.csv"
        catalog.export_efu([scan.scan_uuid], output)
        assert "RepoCatalog.CommonDir" not in output.read_text(encoding="utf-8")
    assert not worktrees.exists()


def test_bare_input_records_topology_without_scanning_admin_files(tmp_path):
    bare = tmp_path / "bare.git"
    git("init", "--bare", bare)
    with LocalCatalog.initialize(
        tmp_path / "files.sqlite3", tmp_path / "worktrees.sqlite3"
    ) as catalog:
        result = catalog.scan([bare])
        assert not result.scans
        assert any(entry.bare for d in result.discoveries for entry in d.entries)


def test_duplicate_export_failure_preserves_existing_destination(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_text("contents", encoding="utf-8")
    with LocalCatalog.initialize(
        tmp_path / "files.sqlite3", tmp_path / "worktrees.sqlite3"
    ) as catalog:
        first = catalog.scan([root]).scans[0]
        second = catalog.scan([root]).scans[0]
        output = tmp_path / "existing.efu"
        output.write_text("original", encoding="utf-8")
        with pytest.raises(ValueError, match="(?i)duplicate"):
            catalog.export_efu([first.scan_uuid, second.scan_uuid], output)
        assert output.read_text(encoding="utf-8") == "original"
        assert not list(tmp_path.glob(".efu-*"))


def test_export_cannot_replace_either_catalog_or_their_sidecars(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    files, worktrees = tmp_path / "files.sqlite3", tmp_path / "worktrees.sqlite3"
    with LocalCatalog.initialize(files, worktrees) as catalog:
        scan = catalog.scan([root]).scans[0]
        for database in (files, worktrees):
            for suffix in ("", "-wal", "-shm", "-journal"):
                with pytest.raises(ValueError, match="catalog"):
                    catalog.export_efu([scan.scan_uuid], Path(str(database) + suffix))
        assert catalog.filesystem.get_scan(scan.scan_uuid) == scan
        assert catalog.worktrees.list_discoveries()


def test_store_failure_stops_further_writes_and_preserves_committed_scan(
    tmp_path, monkeypatch
):
    roots = [tmp_path / name for name in ("first", "second", "third")]
    for root in roots:
        root.mkdir()
    with LocalCatalog.initialize(
        tmp_path / "files.sqlite3", tmp_path / "worktrees.sqlite3"
    ) as catalog:
        original = catalog.filesystem.scan
        attempted = []
        saved = []

        def failing_scan(root, **options):
            attempted.append(root)
            if root == roots[1]:
                raise sqlite3.DatabaseError("database disk image is malformed")
            result = original(root, **options)
            saved.append(result)
            return result

        monkeypatch.setattr(catalog.filesystem, "scan", failing_scan)
        with pytest.raises(sqlite3.DatabaseError):
            catalog.scan(roots)
        assert attempted == roots[:2]
        assert len(saved) == 1
        assert catalog.filesystem.get_scan(saved[0].scan_uuid) == saved[0]


@pytest.mark.parametrize("directory", [False, True])
def test_unrelated_dotgit_data_is_not_silently_excluded(tmp_path, directory):
    root = tmp_path / "root"
    root.mkdir()
    marker = root / ".git"
    if directory:
        marker.mkdir()
        ordinary = marker / "binary.dat"
    else:
        ordinary = marker
    ordinary.write_bytes(b"ordinary binary data\x00\xff")
    with LocalCatalog.initialize(
        tmp_path / "files.sqlite3", tmp_path / "worktrees.sqlite3"
    ) as catalog:
        result = catalog.scan([root])
        assert len(result.scans) == 1
        assert result.scans[0].status == "complete"
        entries = rows(catalog, result.scans[0])
        entry = entries[str(ordinary.relative_to(root))]
        assert (
            entry.sha256 == hashlib.sha256(b"ordinary binary data\x00\xff").hexdigest()
        )
        assert result.discoveries[0].status == "error"


def test_physical_root_alias_is_scanned_once_and_self_databases_stay_excluded(tmp_path):
    parent = tmp_path / "real"
    root = parent / "root"
    root.mkdir(parents=True)
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(parent, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable to this test account")
    (root / "ordinary.txt").write_bytes(b"ordinary")
    with LocalCatalog.initialize(
        root / "files.sqlite3", root / "worktrees.sqlite3"
    ) as catalog:
        result = catalog.scan([alias / "root", root])
        assert result.status == "complete", result
        assert len(result.scans) == 1
        assert result.scans[0].root_path == os.fsencode(alias / "root")
        entries = rows(catalog, result.scans[0])
        assert "ordinary.txt" in entries
        assert not any(
            name.startswith(("files.sqlite3", "worktrees.sqlite3")) for name in entries
        )
