"""Ordinary catalog3 query and maintenance contracts on disposable catalogs."""

import json
import sqlite3

from repo_catalog.adapters.sqlite.schema import SCHEMA_VERSION
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.adapters.sqlite.target import TargetReader
from repo_catalog.application.query_service import QueryService
from tests.support.cli import run


def initialized(tmp_path):
    state = tmp_path / "state"
    run(
        state,
        "init",
        "--profile",
        "catalog-text-v1",
        "--cache-max-bytes",
        67108864,
        "--min-free-bytes",
        0,
    )
    return state


def test_query_observes_sqlite_wal_snapshot_and_derived_schema(tmp_path):
    state = initialized(tmp_path)
    database = state / "catalog.sqlite3"
    with sqlite3.connect(database, autocommit=True) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('00000000-0000-4000-8000-000000000001','before','{}')"
        )
        writer.execute(
            "CREATE VIEW optional_query_projection AS SELECT repository_uuidv4 FROM repositories"
        )
        writer.execute("ANALYZE")
        with Store(state, readonly=True) as reader, reader.transaction(read=True):
            assert reader.one("SELECT count(*) FROM repositories")[0] == 1
            writer.execute("BEGIN IMMEDIATE")
            writer.execute(
                "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('00000000-0000-4000-8000-000000000002','after','{}')"
            )
            writer.execute("COMMIT")
            assert reader.one("SELECT count(*) FROM repositories")[0] == 1
            # A new ordinary query reads committed WAL bytes; it does not run a
            # schema hash audit or assume that the changing file is immutable.
            result = QueryService(state).query("repos list")
            assert {r["name"] for r in result.data["items"]} == {"before", "after"}
        with TargetReader(database) as diagnostic:
            assert diagnostic.one("SELECT count(*) FROM repositories")[0] == 2


def test_fresh_catalog3_doctor_and_file_query(catalog):
    state, fixture, repositories = catalog
    run(state, "sync", "git")
    doctor = run(state, "doctor")
    assert doctor["data"]["schema_version"] == SCHEMA_VERSION
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert (
            db.execute("SELECT format_id FROM database_identity").fetchone()[0]
            == "repo-catalog/catalog3"
        )
        assert not db.execute(
            "SELECT 1 FROM sqlite_schema WHERE name='catalog_meta'"
        ).fetchone()
    result = run(
        state,
        "file",
        "show",
        "--repo",
        repositories["alpha"],
        "--ref",
        "refs/heads/main",
        "--path",
        "shared/a.txt",
    )
    item = result["data"]["items"][0]
    assert item["raw_available"] and item["text"] is not None
    assert item["byte_length"] == len(item["text"].encode("utf8"))
    run(state, "db", "check", "--full")
    run(state, "cache", "status")


def test_backup_restore_requires_absent_destination_without_removing_empty_dir(
    catalog, tmp_path
):
    state, fixture, repositories = catalog
    run(state, "sync", "git")
    # A source locator is useful transient state, not part of a Core backup.
    with Store(state) as source:
        source.operational.execute(
            "INSERT INTO cache_locators(cache_locator_id,repository_uuidv4,path,access,state) VALUES('source-locator',?,'/synthetic/sealed-cache','source_readonly','available')",
            (repositories["alpha"],),
        )
    output = tmp_path / "backup.sqlite3"
    original = run(state, "db", "backup", "--output", output)
    preserved = tmp_path / "existing-empty"
    preserved.mkdir()
    rejected = run(preserved, "db", "restore", "--input", output, expected=2)
    assert rejected["error"]["code"] == "INVALID_ARGUMENT"
    assert preserved.is_dir() and not list(preserved.iterdir())
    destination = tmp_path / "restore"
    restored = run(destination, "db", "restore", "--input", output)
    assert (
        restored["catalog"]["db_instance_id"] != original["catalog"]["db_instance_id"]
    )
    with (
        sqlite3.connect(output) as before,
        sqlite3.connect(destination / "catalog.sqlite3") as after,
    ):
        for table in (
            "commits",
            "tree_entries",
            "contents",
            "content_digests",
            "repository_object_sources",
        ):
            assert (
                after.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                == before.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
            )
        for db in (before, after):
            assert not db.execute(
                "SELECT name FROM sqlite_schema WHERE name IN ('cache_leases','active_cache_entries','cache_locators','content_locations')"
            ).fetchall()
    # PF-P08/PF-P14: restored Core facts survive independently of disposable
    # cache/index state. A needed Operational store starts empty with a new owner.
    assert not (destination / "operational.sqlite3").exists()
    assert not (destination / "search.sqlite3").exists()
    with Store(destination) as copy, Store(state) as source:
        for table in ("cache_leases", "active_cache_entries", "cache_locators", "jobs"):
            assert copy.operational.one(f"SELECT count(*) FROM {table}")[0] == 0
        assert source.operational.one(
            "SELECT 1 FROM cache_locators WHERE cache_locator_id='source-locator'"
        )
        assert (
            copy.operational.catalog_db_instance_id == copy.revision()["db_instance_id"]
        )
        assert (
            copy.operational.catalog_db_instance_id
            != source.operational.catalog_db_instance_id
        )
    run(destination, "db", "check")
    assert (
        json.loads((destination / "restore-origin.json").read_text())["source_catalog"]
        == original["catalog"]
    )
