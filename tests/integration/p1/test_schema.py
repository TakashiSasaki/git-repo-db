"""Physical schema and trusted infrastructure boundary, independent of CLI schema21."""

import json
import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite import p1_schema as schema


@pytest.mark.parametrize("store", schema.STORES)
def test_independent_fresh_store_and_real_constraints(tmp_path, store):
    path = tmp_path / (store + ".sqlite3")
    repository, instance = str(uuid4()), str(uuid4())
    schema.initialize(path, store, repository, instance)
    assert list(tmp_path.glob("*.sqlite3")) == [path]
    db = schema.connect(path, store)
    try:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert tuple(db.execute("SELECT * FROM store_identity").fetchone()) == (
            store,
            repository,
            instance,
        )
        tables = [
            r for r in db.execute("PRAGMA table_list") if not r[1].startswith("sqlite_")
        ]
        assert tables and all(
            r[4] == 1 and r[5] == 1 for r in tables
        )  # WITHOUT ROWID, STRICT
        for table in tables:
            columns = list(db.execute(f'PRAGMA table_xinfo("{table[1]}")'))
            assert any(c[5] for c in columns), table[1]
            # INTEGER alone is never the direct identity of a target relation.
            pk = [c for c in columns if c[5]]
            assert not (len(pk) == 1 and pk[0][2] == "INTEGER"), table[1]
        if store == "core":
            triggers = {
                r[0]
                for r in db.execute(
                    "SELECT name FROM sqlite_schema WHERE type='trigger'"
                )
            }
            for table in tables:
                for action in ("update", "delete"):
                    assert f"p1_immutable_{table[1]}_{action}" in triggers
    finally:
        db.close()
    with pytest.raises(FileExistsError):
        schema.initialize(path, store, repository, instance)


@pytest.mark.parametrize("store", schema.STORES)
def test_declared_ddl_and_executed_sqlite_schema_match(tmp_path, store):
    schema.verify_declared()
    declared = json.loads(schema._resource("fingerprints.json"))["stores"][store]
    assert declared["ddl_sha256"] == schema.fingerprint(store)
    path = tmp_path / "store.sqlite3"
    schema.initialize(path, store, str(uuid4()), str(uuid4()))
    db = schema.connect(path, store)
    assert schema.schema_rows(db) == schema.expected_schema(store)
    db.close()


def test_foreign_or_tampered_catalog_is_rejected(tmp_path):
    path = tmp_path / "foreign.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE unrelated(real TEXT PRIMARY KEY)")
    with pytest.raises(schema.SchemaError, match="physical schema"):
        schema.connect(path, "core")
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    with pytest.raises(schema.SchemaError, match="absent"):
        schema.connect(tmp_path / "absent.sqlite3", "core")
    assert not (tmp_path / "absent.sqlite3").exists()


def test_required_udfs_and_actual_generated_column_behavior():
    db = sqlite3.connect(":memory:")
    schema.register_functions(db)
    # Generated columns are NOT counted by table_info; tests must use table_xinfo.
    db.execute(
        "CREATE TABLE example(a TEXT PRIMARY KEY CHECK(p1_uuid4(a)), n INTEGER GENERATED ALWAYS AS (length(a)) STORED) STRICT, WITHOUT ROWID"
    )
    value = str(uuid4())
    db.execute("INSERT INTO example(a) VALUES(?)", (value,))
    assert db.execute("SELECT n FROM example").fetchone()[0] == 36
    assert len(db.execute("PRAGMA table_info(example)").fetchall()) == 1
    assert len(db.execute("PRAGMA table_xinfo(example)").fetchall()) == 2
    with pytest.raises(sqlite3.OperationalError, match="generated"):
        db.execute("INSERT INTO example(a,n) VALUES(?,?)", (str(uuid4()), 7))
    assert db.execute(
        "SELECT p1_json(?),p1_json(?),p1_oid(?,?)",
        ('["\\u65e5"]', '[ "x" ]', "sha1", "a" * 40),
    ).fetchone() == (1, 0, 1)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO example(a) VALUES('not-a-uuid')")
    db.close()


def test_baseline_initializer_remains_isolated():
    from repo_catalog.adapters.sqlite import schema as production

    assert production.SCHEMA_VERSION == 21
    assert "p1_" not in production.schema_sql()
    assert "store_identity" not in production.schema_sql()


@pytest.mark.parametrize("value", [0, -1, -(2**63), 2**63 - 1])
def test_sqlite_signed_epoch_microsecond_boundaries(value):
    # Target typed contracts additionally reject bool; SQLite enforces int64/STRICT.
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE clocks(git_author_time_us INTEGER PRIMARY KEY) STRICT, WITHOUT ROWID"
    )
    db.execute("INSERT INTO clocks VALUES(?)", (value,))
    assert db.execute("SELECT git_author_time_us FROM clocks").fetchone()[0] == value
    with pytest.raises(OverflowError):
        db.execute("INSERT INTO clocks VALUES(?)", (2**63,))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO clocks VALUES('yesterday')")
    db.close()
