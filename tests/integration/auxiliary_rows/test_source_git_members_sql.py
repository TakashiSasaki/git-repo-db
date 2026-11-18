"""The actual stored Source Git-members CHECK shares the pure typed grammar."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.context_rows import ROW_TYPES
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.shared_values import encode
from repo_catalog.domain.source_inventory_members import source_inventory_members_sql
from tests.integration.auxiliary_rows.test_source_inventory_history import prepare


@pytest.mark.parametrize(
    "case", ["non-uuid", "duplicate", "scalar", "noncanonical-order"]
)
def test_actual_sql_source_git_members_reject_malformed_originals_without_writes(
    tmp_path, case
):
    old, _, _, _, _ = prepare(tmp_path)
    repository = old.repositories[0]
    members = {
        "non-uuid": ["not-a-repository"],
        "duplicate": [repository, repository],
        "scalar": [True],
        "noncanonical-order": sorted([repository, str(uuid4())], reverse=True),
    }[case]
    with closing(connect(tmp_path / "context.sqlite3", "context")) as db:
        attempted = dict(
            zip(
                ROW_TYPES["source_inventory_evidence"].WRITE_COLUMNS,
                old.values,
                strict=True,
            )
        )
        attempted["members_json"] = encode(members)
        columns, values = ROW_TYPES["source_inventory_evidence"].insert_bindings(
            attempted
        )
        before = db.total_changes
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                f"INSERT INTO source_inventory_evidence({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                values,
            )
        assert db.total_changes == before
        assert (
            db.execute("SELECT count(*) FROM source_inventory_evidence").fetchone()[0]
            == 0
        )
        if case != "noncanonical-order":
            with pytest.raises((ValueError, TypeError)):
                replace(old, repositories=tuple(members))


def test_source_git_member_guard_accepts_empty_and_unresolved_uuid_without_repository_lookup(
    tmp_path,
):
    old, _, _, _, _ = prepare(tmp_path)
    unknown = str(uuid4())
    assert source_inventory_members_sql(encode([unknown])) == 1
    assert source_inventory_members_sql("[]") == 1
    with closing(connect(tmp_path / "context.sqlite3", "context")) as db:
        # Existing Context metadata is independent of a Repository repository row.
        # The pure validator above does not consult either authority.
        db.execute("INSERT INTO repository_context VALUES(?,?)", (unknown, "{}"))
        for offset, members in enumerate(((), (unknown,)), 1):
            observation = replace(
                old,
                repositories=members,
                provider_repositories=(),
                observed_at_us=old.observed_at_us + offset,
            )
            columns, values = ROW_TYPES["source_inventory_evidence"].insert_bindings(
                dict(
                    zip(
                        ROW_TYPES["source_inventory_evidence"].WRITE_COLUMNS,
                        observation.values,
                        strict=True,
                    )
                )
            )
            db.execute(
                f"INSERT INTO source_inventory_evidence({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                values,
            )
        assert (
            db.execute("SELECT count(*) FROM source_inventory_evidence").fetchone()[0]
            == 2
        )
    assert not (tmp_path / "repository.sqlite3").exists()
