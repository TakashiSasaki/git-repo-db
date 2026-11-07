"""Standalone catalog acceptance; deliberately independent of root fixtures."""

import csv
import hashlib
import io
import os
import sqlite3
from dataclasses import replace

import pytest

from repo_catalog.filesystem import (
    FileEntry,
    FilesystemCatalog,
    FilesystemError,
    export_efu,
    scanner,
)


def test_full_hash_history_exclusions_and_offline_export(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    (root / "empty").write_bytes(b"")
    (root / "binary").write_bytes(b"\x00\xff\r\n")
    (root / "excluded").mkdir()
    (root / "excluded" / "secret").write_bytes(b"not scanned")
    with FilesystemCatalog.initialize(root / "files.sqlite3") as catalog:
        first = catalog.scan(root, exclude_paths=[root / "excluded"])
        assert first.status == "complete"
        entries = {e.relative_path: e for e in catalog.iter_entries(first.scan_uuid)}
        assert set(entries) == {b"", b"empty", b"binary"}
        assert entries[b"empty"].sha256 == hashlib.sha256(b"").hexdigest()
        assert entries[b"binary"].sha256 == hashlib.sha256(b"\x00\xff\r\n").hexdigest()
        (root / "binary").write_bytes(b"changed")
        second = catalog.scan(root, exclude_paths=[root / "excluded"])
        assert second.scan_uuid != first.scan_uuid
        assert (
            next(
                e
                for e in catalog.iter_entries(first.scan_uuid)
                if e.relative_path == b"binary"
            ).sha256
            == entries[b"binary"].sha256
        )
        (root / "binary").unlink()
        result = catalog.export_efu(first.scan_uuid, tmp_path / "files.efu")
        assert result.written == 3
        assert b"\r\n" in (tmp_path / "files.efu").read_bytes()
        assert catalog.verify()["integrity"] == "ok"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            catalog._db.execute("DELETE FROM entries")


def test_missing_root_partial_requires_explicit_export(tmp_path):
    with FilesystemCatalog.initialize(tmp_path / "files.db") as catalog:
        result = catalog.scan(tmp_path / "missing")
        assert result.status == "partial" and result.errors == 1
        output = tmp_path / "output.efu"
        output.write_text("original")
        with pytest.raises(FilesystemError, match="allow_partial"):
            catalog.export_efu(result.scan_uuid, output)
        assert output.read_text() == "original"
        catalog.export_efu(result.scan_uuid, output, allow_partial=True)
        assert catalog.verify()["integrity"] == "ok"


@pytest.mark.skipif(os.name != "posix", reason="POSIX native path and FIFO semantics")
def test_lossless_path_symlink_fifo_and_non_utf8_export(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    raw = os.fsencode(root) + b"/bad-\xff"
    fd = os.open(raw, os.O_CREAT | os.O_WRONLY, 0o600)
    os.write(fd, b"native")
    os.close(fd)
    (root / "link").symlink_to(root, target_is_directory=True)
    os.mkfifo(root / "pipe")
    with FilesystemCatalog.initialize(tmp_path / "files.db") as catalog:
        scan = catalog.scan(root)
        assert scan.status == "complete"
        rows = {e.relative_path: e for e in catalog.iter_entries(scan.scan_uuid)}
        assert rows[b"bad-\xff"].sha256 == hashlib.sha256(b"native").hexdigest()
        assert rows[b"link"].kind == "symlink" and rows[b"link"].sha256 is None
        assert rows[b"pipe"].kind == "special" and rows[b"pipe"].sha256 is None
        output = tmp_path / "output.efu"
        output.write_text("preserved")
        with pytest.raises(FilesystemError, match="representable"):
            catalog.export_efu(scan.scan_uuid, output)
        assert output.read_text() == "preserved"
        assert (
            catalog.export_efu(scan.scan_uuid, output, skip_non_utf8=True).skipped == 1
        )


def test_changed_during_hash_is_not_admitted(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    target = root / "file"
    target.write_bytes(b"a" * 1024)
    original = scanner.os.read
    mutated = False

    def changing_read(fd, count):
        nonlocal mutated
        data = original(fd, count)
        if data and not mutated:
            mutated = True
            target.write_bytes(b"different")
        return data

    monkeypatch.setattr(scanner.os, "read", changing_read)
    with FilesystemCatalog.initialize(tmp_path / "files.db") as catalog:
        scan = catalog.scan(root)
        entry = next(
            e
            for e in catalog.iter_entries(scan.scan_uuid)
            if e.relative_path == b"file"
        )
        assert scan.status == "partial"
        assert scan.enumeration_complete and not scan.hashing_complete
        assert entry.sha256 is None and entry.hash_status == "changed"


def test_interruption_keeps_history_and_no_false_completion(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "file").write_bytes(b"body")
    import repo_catalog.filesystem.store as store

    original = store.walk

    def interrupted(*args):
        yield next(original(*args))
        raise KeyboardInterrupt

    monkeypatch.setattr(store, "walk", interrupted)
    with FilesystemCatalog.initialize(tmp_path / "files.db") as catalog:
        with pytest.raises(KeyboardInterrupt):
            catalog.scan(root)
        record = catalog.list_scans()[0]
        assert record.status == "interrupted" and record.entries == 1
        catalog.verify()


def test_efu_golden_extensions_timestamps_and_collisions():
    entry = FileEntry(
        "namespace",
        "scan",
        b"a",
        b'C:\\root\\a,"\xe6\x97\xa5.txt',
        "file",
        size=3,
        mtime_ns=0,
        sha256="a" * 64,
        hash_status="complete",
    )
    output = io.StringIO(newline="")
    export_efu(
        [entry],
        output,
        extra_columns=["RepoCatalog.HashStatus", "Git.Repository"],
        row_enricher=lambda row: {"Git.Repository": "repo"},
    )
    rows = list(csv.reader(io.StringIO(output.getvalue())))
    assert rows[0] == [
        "Filename",
        "Size",
        "Date Modified",
        "Date Created",
        "Attributes",
        "SHA256",
        "RepoCatalog.HashStatus",
        "Git.Repository",
    ]
    assert rows[1][1:] == [
        "3",
        "116444736000000000",
        "",
        "0",
        "a" * 64,
        "complete",
        "repo",
    ]
    assert "\r\n" in output.getvalue()
    with pytest.raises(FilesystemError, match="duplicate"):
        export_efu([entry, entry], io.StringIO())
    with pytest.raises(FilesystemError, match="reserved"):
        export_efu([], io.StringIO(), extra_columns=["SHA256"])
    directory = replace(
        entry,
        kind="directory",
        size=None,
        sha256=None,
        hash_status="not-applicable",
        absolute_path=b"C:\\root",
    )
    output = io.StringIO()
    export_efu([directory], output)
    assert list(csv.reader(io.StringIO(output.getvalue())))[1][4] == "16"


def test_explicit_path_mapping_and_unrepresentable_time():
    entry = FileEntry("namespace", "scan", b"a", b"/root/a", "file", mtime_ns=-1)
    out = io.StringIO()
    export_efu([entry], out, path_map=("/root", "X:\\mapped"))
    row = list(csv.reader(io.StringIO(out.getvalue())))[1]
    assert row[0] == "X:\\mapped\\a"
    assert row[2] == "116444735999999999"
    with pytest.raises(FilesystemError, match="FILETIME"):
        export_efu([replace(entry, mtime_ns=-(1 << 100))], io.StringIO())


def test_standalone_verified_backup_restore_and_tampering(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "file").write_bytes(b"snapshot")
    backup = tmp_path / "backup.db"
    with FilesystemCatalog.initialize(tmp_path / "files.db") as catalog:
        scan = catalog.scan(root)
        catalog.backup(backup)
    with FilesystemCatalog.restore(backup, tmp_path / "restored.db") as restored:
        assert restored.get_scan(scan.scan_uuid).status == "complete"
        assert restored.verify()["integrity"] == "ok"
    with pytest.raises(FileExistsError):
        FilesystemCatalog.restore(backup, tmp_path / "restored.db")
    with backup.open("r+b") as output:
        output.seek(100)
        output.write(b"tampered")
    with pytest.raises(FilesystemError, match="digest mismatch"):
        FilesystemCatalog.restore(backup, tmp_path / "bad.db")


def test_live_identity_change_is_not_certified_in_backup(tmp_path):
    with FilesystemCatalog.initialize(tmp_path / "files.db") as catalog:
        trigger = catalog._db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='catalog_metadata_update'"
        ).fetchone()[0]
        catalog._db.execute("DROP TRIGGER catalog_metadata_update")
        catalog._db.execute(
            "UPDATE catalog_metadata SET value=? WHERE key='namespace_uuid'",
            ("12345678-1234-4234-8234-123456789abc",),
        )
        catalog._db.execute(trigger)
        catalog._db.commit()
        with pytest.raises(FilesystemError, match="identity changed"):
            catalog.backup(tmp_path / "bad-backup.db")
        assert not (tmp_path / "bad-backup.db").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows native reparse metadata")
def test_windows_junction_and_birthtime(tmp_path):
    import subprocess

    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "not-traversed").write_bytes(b"outside")
    (root / "file").write_bytes(b"inside")
    (root / "nested").mkdir()
    (root / "nested" / "file").write_bytes(b"nested")
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root / "junction"), str(outside)],
        check=True,
        capture_output=True,
    )
    with FilesystemCatalog.initialize(tmp_path / "files.db") as catalog:
        scan = catalog.scan(root)
        assert scan.status == "complete"
        entries = {e.relative_path: e for e in catalog.iter_entries(scan.scan_uuid)}
        assert set(entries) == {b"", b"file", b"junction", b"nested", b"nested\\file"}
        assert entries[b"junction"].kind == "symlink"
        assert entries[b"file"].birthtime_ns is not None
        assert entries[b"file"].sha256 == hashlib.sha256(b"inside").hexdigest()
