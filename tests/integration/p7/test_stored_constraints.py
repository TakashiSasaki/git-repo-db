"""Trusted revalidation must not inherit readonly SQLite CHECK omissions."""

import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.p1_schema import expected_schema, schema_rows
from repo_catalog.adapters.sqlite.recovery import is_catalog_stopped
from repo_catalog.adapters.sqlite.recovery_validation import _packaged_checks
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import CorruptionDetectedError


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("captures", "ref", "CAST(x'ff' AS TEXT)"),
        ("captures", "ref", "'not-a-valid-ref'"),
        ("scalar_claims", "provenance", "CAST(x'ff' AS TEXT)"),
        ("scalar_claims", "value", "'false'"),
        ("scalar_claims", "value", "'{'"),
    ],
)
def test_invalid_core_text_or_udf_check_stops_source(
    synthetic_catalog, tmp_path, table, column, value
):
    connection = sqlite3.connect(synthetic_catalog / "core.sqlite3")
    triggers = connection.execute(
        "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=? AND sql LIKE '%BEFORE UPDATE%'",
        (table,),
    ).fetchall()
    if table == "scalar_claims" and column == "value":
        triggers += connection.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name='intrinsic_claims' AND sql LIKE '%BEFORE UPDATE%'"
        ).fetchall()
    for name, _ in triggers:
        connection.execute(f'DROP TRIGGER "{name}"')
    connection.execute("PRAGMA ignore_check_constraints=ON")
    cursor = connection.execute(f'UPDATE "{table}" SET "{column}"={value}')
    assert cursor.rowcount > 0
    if table == "scalar_claims" and column == "value":
        connection.execute(f"UPDATE intrinsic_claims SET value={value}")
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    for _, sql in triggers:
        connection.execute(sql)
    connection.commit()
    assert schema_rows(connection) == expected_schema("core")
    connection.close()
    with pytest.raises(
        CorruptionDetectedError, match="invalid UTF-8|CHECK constraint failed"
    ):
        RecoveryService().create_consistent_backup(
            synthetic_catalog, tmp_path / "backup"
        )
    assert is_catalog_stopped(synthetic_catalog)
    assert not (tmp_path / "backup").exists()


def test_binary_notes_and_split_unicode_remain_valid(synthetic_catalog, tmp_path):
    from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
    from repo_catalog.adapters.sqlite.git_core import GitCore
    from repo_catalog.adapters.sqlite.p1_schema import connect
    from repo_catalog.domain.p1_core import OID, Capture, NotesProof
    from tests.integration.p7.conftest import (
        DEFAULT_REPO_UUID,
        admit_context_text,
        make_native,
        make_tree,
    )

    core = GitCore(synthetic_catalog / "core.sqlite3")
    target = OID(
        "sha1",
        core.sql("SELECT full_oid FROM retained_metadata WHERE native_type='commit'")[
            0
        ][0],
    )
    note = make_native("sha1", "blob", b"\xff\x00\xfe")
    tree = make_tree("sha1", [(b"100644", target.full_oid.encode(), note.oid.full_oid)])
    capture = Capture(
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        DEFAULT_REPO_UUID,
        "binary-source",
        "refs/notes/binary",
        tree.oid,
    )
    core.admit_capture(capture)
    core.admit_note(
        NotesProof(capture, target, note.oid, target.full_oid, (tree,)),
        note,
        str(uuid.uuid4()),
        UnlimitedWorkBudget(),
    )
    connection = connect(synthetic_catalog / "context.sqlite3", "context")
    admit_context_text(connection, "a" * 65535 + "📝" * 4)
    admit_context_text(connection, "")
    connection.close()
    service = RecoveryService()
    assert service.create_consistent_backup(
        synthetic_catalog, tmp_path / "backup"
    ).verified_clean
    assert service.restore_backup(
        tmp_path / "backup", tmp_path / "fresh", DEFAULT_REPO_UUID
    ).revalidated_clean
    assert not is_catalog_stopped(synthetic_catalog)


def test_packaged_check_parser_balances_quotes_comments_and_nested_parentheses():
    sql = """CREATE TABLE t("x)" TEXT CHECK("x)" IN ('a)', 'b''(')), y INTEGER CHECK((y>0 /* ) */) OR y IS NULL))"""
    assert list(_packaged_checks(sql)) == [
        "\"x)\" IN ('a)', 'b''(')",
        "(y>0 /* ) */) OR y IS NULL",
    ]
