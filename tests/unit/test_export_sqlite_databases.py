"""Test authoritative SQLite database exporter for SchemaSpy and external tools."""

import sqlite3
import tempfile
from pathlib import Path

from scripts.export_sqlite_databases import export_databases


def test_export_databases():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        dbs = export_databases(out_dir)

        assert "catalog.sqlite3" in dbs
        assert "operational.sqlite3" in dbs
        assert "search.sqlite3" in dbs
        assert "catalog.sql" in dbs
        assert "operational.sql" in dbs
        assert "search.sql" in dbs
        assert dbs["catalog.sql"].is_file()
        assert dbs["operational.sql"].is_file()
        assert dbs["search.sql"].is_file()

        # Core Store
        core_conn = sqlite3.connect(dbs["catalog.sqlite3"])
        try:
            core_tables = core_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            assert len(core_tables) == 70
        finally:
            core_conn.close()

        # Operational Store
        op_conn = sqlite3.connect(dbs["operational.sqlite3"])
        try:
            op_tables = op_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            assert len(op_tables) == 10
        finally:
            op_conn.close()

        # Search Store
        search_conn = sqlite3.connect(dbs["search.sqlite3"])
        try:
            search_tables = search_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            assert len(search_tables) == 4
        finally:
            search_conn.close()
