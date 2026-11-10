"""Connection guards protect trusted SQL callers, not arbitrary SQLite access."""

import sqlite3

import pytest

from repo_catalog.filesystem import FilesystemCatalog
from repo_catalog.filesystem.models import occurrence_uuid


@pytest.mark.parametrize("reopen", [False, True])
@pytest.mark.parametrize(
    "table", ["catalog_metadata", "scans", "entries", "scan_outcomes"]
)
def test_factory_connection_rejects_replace(tmp_path, reopen, table):
    database = tmp_path / "files.db"
    catalog = FilesystemCatalog.initialize(database)
    namespace = catalog.namespace_uuid
    scan = occurrence_uuid()
    with catalog._db:
        catalog._db.execute(
            "INSERT INTO scans VALUES (?,?,?,?,?)",
            (namespace, scan, b"/synthetic", 1, "[]"),
        )
        catalog._db.execute(
            "INSERT INTO entries (namespace_uuid,scan_uuid,relative_path,kind,hash_status) "
            "VALUES (?,?,?,'directory','not-applicable')",
            (namespace, scan, b""),
        )
        # Keep entries' scan incomplete: the terminal-insert guard must not hide
        # a failure of the append-only DELETE trigger during replacement.
        if table == "scan_outcomes":
            catalog._db.execute(
                "INSERT INTO scan_outcomes VALUES (?,?,2,'complete',1,0)",
                (namespace, scan),
            )
    if reopen:
        catalog.close()
        catalog = FilesystemCatalog.open(database, readonly=False)
    with catalog:
        before = [tuple(row) for row in catalog._db.execute(f"SELECT * FROM {table}")]
        # Private connection access deliberately tests trusted internal SQL.
        # No public API accepts this replacement command.
        with pytest.raises(sqlite3.IntegrityError, match="append-only catalog"):
            catalog._db.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM {table}")
        assert [
            tuple(row) for row in catalog._db.execute(f"SELECT * FROM {table}")
        ] == before
        assert catalog._db.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
        assert catalog._db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_readonly_factory_connection_enables_recursive_triggers(tmp_path):
    database = tmp_path / "files.db"
    with FilesystemCatalog.initialize(database):
        pass
    with FilesystemCatalog.open(database, readonly=True) as catalog:
        assert catalog._db.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
        assert catalog._db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
