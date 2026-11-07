"""Regression cases for independent review findings."""

import csv
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
)


def test_efu_newlines_case_preservation_and_metadata():
    first = FileEntry(
        "namespace",
        "scan",
        b"A\n\tname",
        b"/root/A\n\tname",
        "symlink",
        link_target=b"target-\xff",
        observed_us=42,
    )
    second = replace(
        first, relative_path=b"a\n\tname", absolute_path=b"/root/a\n\tname"
    )
    out = io.StringIO(newline="")
    result = export_efu(
        [first, second],
        out,
        extra_columns=[
            "RepoCatalog.OriginalPath",
            "RepoCatalog.LinkTargetBase64",
            "RepoCatalog.ObservedMicroseconds",
        ],
    )
    rows = list(csv.reader(io.StringIO(out.getvalue(), newline="")))
    assert result.written == 2
    assert rows[1][0] == "/root/A\n\tname"
    assert rows[2][0] == "/root/a\n\tname"
    assert rows[1][-1] == "42" and rows[1][-3] == rows[1][0]


def test_efu_root_and_cross_dialect_mapping():
    root = FileEntry("namespace", "scan", b"", b"/source", "directory")
    child = replace(root, absolute_path=b"/source/child")
    out = io.StringIO()
    export_efu([root, child], out, path_map=("/source", "/"))
    rows = list(csv.reader(io.StringIO(out.getvalue())))
    assert [r[0] for r in rows[1:]] == ["/", "/child"]
    out = io.StringIO()
    export_efu(
        [replace(child, absolute_path=b"C:\\source\\nested\\child")],
        out,
        path_map=("C:\\source", "/mapped"),
    )
    assert list(csv.reader(io.StringIO(out.getvalue())))[1][0] == "/mapped/nested/child"


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink creation")
def test_alias_self_exclusion_and_export_protection(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with FilesystemCatalog.initialize(root / "files.db") as catalog:
        scan = catalog.scan(alias / "root")
        assert [e.relative_path for e in catalog.iter_entries(scan.scan_uuid)] == [b""]
        with pytest.raises(FilesystemError, match="catalog artifacts"):
            catalog.export_efu(scan.scan_uuid, alias / "root" / "files.db")
        catalog.verify()


def test_database_failure_does_not_retry_writes(tmp_path, monkeypatch):
    import repo_catalog.filesystem.store as store

    with FilesystemCatalog.initialize(tmp_path / "files.db") as catalog:

        def failed(*args):
            raise sqlite3.OperationalError("simulated storage failure")
            yield

        monkeypatch.setattr(store, "walk", failed)
        with pytest.raises(sqlite3.OperationalError):
            catalog.scan(tmp_path)
        result = catalog.list_scans()[0]
        assert result.status == "incomplete"
        assert (
            catalog._db.execute("SELECT count(*) FROM scan_outcomes").fetchone()[0] == 0
        )


def test_backup_wal_is_not_implicitly_admitted(tmp_path):
    source = tmp_path / "source.db"
    backup = tmp_path / "backup.db"
    with FilesystemCatalog.initialize(source) as catalog:
        catalog.backup(backup)
    Path = type(backup)
    Path(str(backup) + "-wal").write_bytes(b"not bound by manifest")
    with pytest.raises(FilesystemError, match="standalone"):
        FilesystemCatalog.restore(backup, tmp_path / "restored.db")


def test_windows_unc_and_drive_relative_input_rules(monkeypatch):
    from repo_catalog.filesystem import models

    with monkeypatch.context() as patch:
        patch.setattr(models.os, "name", "nt")
        unc = models.native_path("\\\\server\\share")
        with pytest.raises(FilesystemError, match="drive-relative"):
            models.native_path("D:escape")
    assert b"server" in unc and b"share" in unc


def test_windows_drive_relative_stored_entry_is_rejected(tmp_path):
    from repo_catalog.filesystem.models import occurrence_uuid

    database = tmp_path / "catalog.db"
    with FilesystemCatalog.initialize(database) as catalog:
        trigger = catalog._db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='catalog_metadata_update'"
        ).fetchone()[0]
        catalog._db.execute("DROP TRIGGER catalog_metadata_update")
        catalog._db.execute(
            "UPDATE catalog_metadata SET value='nt' WHERE key='path_dialect'"
        )
        catalog._db.execute(trigger)
        scan = occurrence_uuid()
        catalog._db.execute(
            "INSERT INTO scans VALUES (?,?,?,?,?)",
            (catalog.namespace_uuid, scan, b"C:\\root", 1, "[]"),
        )
        catalog._db.execute(
            "INSERT INTO entries(namespace_uuid,scan_uuid,relative_path,kind,hash_status) VALUES (?,?,?,?,?)",
            (catalog.namespace_uuid, scan, b"D:escape", "unknown", "not-applicable"),
        )
        catalog._db.commit()
    with pytest.raises(FilesystemError, match="relative file path"):
        FilesystemCatalog.open(database, readonly=True)


def test_extra_schema_with_sqlite_like_name_is_rejected(tmp_path):
    database = tmp_path / "catalog.db"
    with FilesystemCatalog.initialize(database) as catalog:
        catalog._db.execute("CREATE TABLE sqlitex_hidden(value TEXT)")
        with pytest.raises(FilesystemError, match="schema mismatch"):
            catalog.verify()
    with pytest.raises(FilesystemError, match="schema mismatch"):
        FilesystemCatalog.open(database, readonly=True)
