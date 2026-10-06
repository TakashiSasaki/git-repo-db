"""Ordinary catalog3 query and maintenance contracts on disposable catalogs."""

import json
import sqlite3

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
            "INSERT INTO repositories(repository_id,name,preferred_repository_endpoint_id,current_snapshot_id,metadata) VALUES('repo','before',NULL,NULL,'{}')"
        )
        writer.execute(
            "CREATE VIEW optional_query_projection AS SELECT repository_id FROM repositories"
        )
        writer.execute("ANALYZE")
        with Store(state, readonly=True) as reader, reader.transaction(read=True):
            assert reader.one("SELECT name FROM repositories")[0] == "before"
            writer.execute("BEGIN IMMEDIATE")
            writer.execute(
                "UPDATE repositories SET name='after' WHERE repository_id='repo'"
            )
            writer.execute("COMMIT")
            assert reader.one("SELECT name FROM repositories")[0] == "before"
            # A new ordinary query reads committed WAL bytes; it does not run a
            # schema hash audit or assume that the changing file is immutable.
            result = QueryService(state).query("repos list")
            assert result.data["items"][0]["name"] == "after"
        with TargetReader(database) as diagnostic:
            assert diagnostic.one("SELECT name FROM repositories")[0] == "after"


def test_fresh_catalog3_doctor_and_file_query(catalog):
    state, fixture, repositories = catalog
    run(state, "sync", "git")
    doctor = run(state, "doctor")
    assert doctor["data"]["schema_version"] == 5
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


def test_backup_restore_explicit_empty_destination(catalog, tmp_path):
    state, fixture, repositories = catalog
    run(state, "sync", "git")
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA recursive_triggers=ON")
        content_id = db.execute(
            "SELECT content_id FROM contents ORDER BY content_id LIMIT 1"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO cache_locators(cache_locator_id,repository_id,path,access,state) VALUES('preserved-source',?,'/synthetic/sealed-cache','source_readonly','available')",
            (repositories["alpha"],),
        )
        db.execute(
            "INSERT INTO content_locations(content_id,kind,locator,cache_locator_id,state) VALUES(?,'cache','source-observation','preserved-source','available')",
            (content_id,),
        )
    output = tmp_path / "backup.sqlite3"
    original = run(state, "db", "backup", "--output", output)
    destination = tmp_path / "restore"
    destination.mkdir()
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
        assert after.execute("SELECT count(*) FROM cache_leases").fetchone()[0] == 0
        assert (
            after.execute(
                "SELECT count(*) FROM active_cache_entries WHERE state!='evicted'"
            ).fetchone()[0]
            == 0
        )
        assert (
            after.execute(
                "SELECT * FROM cache_locators WHERE cache_locator_id='preserved-source'"
            ).fetchone()
            == before.execute(
                "SELECT * FROM cache_locators WHERE cache_locator_id='preserved-source'"
            ).fetchone()
        )
        assert (
            after.execute(
                "SELECT * FROM content_locations WHERE cache_locator_id='preserved-source'"
            ).fetchall()
            == before.execute(
                "SELECT * FROM content_locations WHERE cache_locator_id='preserved-source'"
            ).fetchall()
        )
        assert not after.execute(
            "SELECT 1 FROM cache_locators WHERE access='target_active' AND state!='missing'"
        ).fetchone()
    run(destination, "db", "check")
    assert (
        json.loads((destination / "restore-origin.json").read_text())["source_catalog"]
        == original["catalog"]
    )
