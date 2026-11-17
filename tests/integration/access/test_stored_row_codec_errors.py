"""Stored primitive codec failures retain Access format/corruption boundaries."""

import json
import sqlite3
from contextlib import closing

import pytest

from repo_catalog.adapters.sqlite import access_schema as schema
from repo_catalog.adapters.sqlite.access_registry import AccessRegistry
from repo_catalog.cli.access_workflow import main
from repo_catalog.domain.access_registry import AccessRegistryError

SCOPE = "550e8400-e29b-41d4-a716-446655440000"
REPOSITORY = "750e8400-e29b-41d4-a716-446655440000"


def replace_table_declaration(db, table, ddl):
    cookie = db.execute("PRAGMA schema_version").fetchone()[0] + 1
    db.execute("PRAGMA writable_schema=ON")
    db.execute(
        "UPDATE sqlite_schema SET sql=? WHERE type='table' AND name=?", (ddl, table)
    )
    db.execute("PRAGMA writable_schema=OFF")
    db.execute(f"PRAGMA schema_version={cookie}")


def malformed_identity(path):
    """Fault injection: retain a TEXT primitive under the exact original DDL."""
    schema.initialize(path)
    with closing(sqlite3.connect(path)) as db:
        original = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='access_identity'"
        ).fetchone()[0]
        altered = original.replace("schema_version INTEGER", "schema_version TEXT")
        assert altered != original
        replace_table_declaration(db, "access_identity", altered)
        db.commit()
    with closing(sqlite3.connect(path)) as db:
        schema.register_functions(db)
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name='access_identity'"
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE access_identity SET schema_version='broken'")
        db.execute("PRAGMA ignore_check_constraints=OFF")
        for _, sql in triggers:
            db.execute(sql)
        replace_table_declaration(db, "access_identity", original)
        db.commit()
    with closing(sqlite3.connect(path)) as db:
        assert schema.schema_rows(db) == schema.expected_schema()
        assert db.execute(
            "SELECT schema_version,typeof(schema_version) FROM access_identity"
        ).fetchone() == ("broken", "text")


def test_malformed_stored_identity_keeps_format_error_and_structured_cli(
    tmp_path, capsys
):
    path = tmp_path / "access.sqlite3"
    malformed_identity(path)
    before = path.read_bytes()
    with pytest.raises(AccessRegistryError) as error:
        AccessRegistry(path, writable=True)
    assert error.value.code == "FORMAT"
    assert (
        main(
            [
                "review",
                "--access-db",
                str(path),
                "--repository",
                REPOSITORY,
                "--scope",
                SCOPE,
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"status": "error", "code": "FORMAT"}
    assert path.read_bytes() == before
    assert not schema.stop_path(path).exists()
