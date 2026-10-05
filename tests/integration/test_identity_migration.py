import copy
import hashlib
import json
import sqlite3
import uuid
from importlib.resources import files

import pytest

from repo_catalog.adapters.sqlite.store import Store, statements
from repo_catalog.application import repository_identity
from repo_catalog.config import DEFAULTS, serialize
from repo_catalog.domain.models import CatalogError
from tests.support.cli import run


def legacy_state(path):
    path.mkdir()
    config = copy.deepcopy(DEFAULTS)
    config["cache"].update(max_bytes=67108864, min_free_bytes=0)
    (path / "catalog.toml").write_text(serialize(config))
    for name in ("cache", "work", "quarantine", "locks", "logs"):
        (path / name).mkdir()
    ids = {
        name: str(uuid.uuid4())
        for name in (
            "catalog",
            "source",
            "repo",
            "job",
            "run",
            "github_source",
            "github_repo",
        )
    }
    sql = (
        files("repo_catalog")
        .joinpath("resources/migrations/001_initial.sql")
        .read_text()
    )
    with sqlite3.connect(path / "catalog.sqlite3") as db:
        db.execute("PRAGMA foreign_keys=ON")
        for statement in statements(sql):
            db.execute(statement)
        db.execute(
            "INSERT INTO schema_migrations VALUES(1,?,?)",
            (hashlib.sha256(sql.encode()).hexdigest(), "legacy"),
        )
        db.execute("INSERT INTO catalog_meta VALUES(1,?,41,1)", (ids["catalog"],))
        db.execute(
            "INSERT INTO sources VALUES(?,'local-git','old-local',?)",
            (ids["source"], json.dumps({"url": "file:///old-mount/app.git"})),
        )
        db.execute(
            "INSERT INTO sources VALUES(?,'github','fixture',?)",
            (ids["github_source"], json.dumps({"owner": "fixture"})),
        )
        db.execute(
            "INSERT INTO repositories VALUES(?,?,'local',?,'old-local','file:///old-mount/app.git','{}',NULL)",
            (ids["repo"], ids["source"], ids["source"]),
        )
        db.execute(
            "INSERT INTO repositories VALUES(?,?,'github.com','42','fixture/app','https://github.com/fixture/app.git','{}',NULL)",
            (ids["github_repo"], ids["github_source"]),
        )
        db.execute(
            "INSERT INTO jobs VALUES(?,'sync','{}','complete',1,NULL,'{}',NULL,'legacy','legacy')",
            (ids["job"],),
        )
        db.execute(
            "INSERT INTO collection_runs(id,job_id,repo_id,generation,attempt,state,started_at,kind) VALUES(?,?,?,1,1,'published','legacy','git')",
            (ids["run"], ids["job"], ids["repo"]),
        )
        db.execute(
            "INSERT INTO snapshots VALUES(?,?,?,1,1,'legacy')",
            (ids["run"], ids["run"], ids["repo"]),
        )
        db.execute(
            "UPDATE repositories SET current_snapshot=? WHERE id=?",
            (ids["run"], ids["repo"]),
        )
        raw = b"legacy"
        oid = hashlib.sha1(b"blob 6\0" + raw).digest()
        db.execute("INSERT INTO git_objects VALUES(100,'sha1',?,'blob',6,1)", (oid,))
        db.execute("INSERT INTO contents VALUES(77,6,'legacy','eligible','legacy')")
        db.execute("INSERT INTO blob_content_map VALUES(100,77,?)", (ids["run"],))
        for algorithm in ("md5", "sha1", "sha256"):
            db.execute(
                "INSERT INTO content_digests VALUES(77,'raw',?,?, 'legacy','legacy')",
                (algorithm, hashlib.new(algorithm, raw).digest()),
            )
    return ids


def test_v1_migration_preserves_identity_data_and_unknown_provenance(tmp_path):
    state = tmp_path / "v1"
    ids = legacy_state(state)
    with pytest.raises(CatalogError, match="Explicit migration"):
        Store(state, readonly=True)
    result = run(state, "db", "migrate")
    assert result["catalog"]["db_instance_id"] == ids["catalog"]
    with Store(state) as store:
        assert store.one("SELECT schema_version,publication_seq FROM catalog_meta")[
            :
        ] == (2, 42)
        assert [
            r[0]
            for r in store.all("SELECT version FROM schema_migrations ORDER BY version")
        ] == [1, 2]
        assert store.one("PRAGMA foreign_keys")[0] == 1
        assert store.all("PRAGMA foreign_key_check") == []
        repo = store.one("SELECT * FROM repositories WHERE id=?", (ids["repo"],))
        assert repo["current_snapshot"] == ids["run"]
        assert store.one("SELECT raw_text FROM contents WHERE id=77")[0] == "legacy"
        assert store.one("SELECT count(*) FROM content_digests")[0] == 3
        assert store.one("SELECT endpoint_id,endpoint_url FROM collection_runs")[:] == (
            None,
            None,
        )
        assert store.one("SELECT count(*) FROM source_repositories")[0] == 2
        assert store.one("SELECT count(*) FROM repository_endpoints")[0] == 2
        binding = store.one("SELECT * FROM repository_bindings")
        assert (
            binding["repo_id"] == ids["github_repo"]
            and binding["provider_repo_id"] == "42"
        )
        assert uuid.UUID(binding["instance_id"]).version == 4
    run(state, "db", "migrate")
    with Store(state, readonly=True) as store:
        assert store.revision()["publication_seq"] == 42
    run(state, "db", "check", "--full")


def test_migration_failure_rolls_back_table_rebuild(tmp_path, monkeypatch):
    state = tmp_path / "v1"
    ids = legacy_state(state)

    def fail(store):
        repository_identity.default_github_instance(store)
        raise RuntimeError("injected identity migration failure")

    monkeypatch.setattr(repository_identity, "backfill_v2", fail)
    with pytest.raises(RuntimeError):
        Store(state, migrate=True)
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute(
            "SELECT schema_version,publication_seq FROM catalog_meta"
        ).fetchone() == (1, 41)
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name='service_instances'"
            ).fetchone()
            is None
        )
        assert db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT current_snapshot FROM repositories WHERE id=?", (ids["repo"],)
            ).fetchone()[0]
            == ids["run"]
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_tampered_v1_is_rejected_before_migration(tmp_path):
    state = tmp_path / "v1"
    legacy_state(state)
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        db.execute("UPDATE schema_migrations SET checksum='tampered'")
    assert run(state, "db", "migrate", expected=5)["error"]["code"] == "SCHEMA_ERROR"
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert db.execute("SELECT schema_version FROM catalog_meta").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name='repository_endpoints'"
            ).fetchone()
            is None
        )


def test_restore_v1_backup_migrates_destination_only(tmp_path):
    source = tmp_path / "legacy"
    ids = legacy_state(source)
    backup = source / "catalog.sqlite3"
    checksum = hashlib.sha256(backup.read_bytes()).hexdigest()
    config = copy.deepcopy(DEFAULTS)
    config["cache"].update(max_bytes=67108864, min_free_bytes=0)
    backup.with_name(backup.name + ".manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "configuration": config,
                "sha256": checksum,
                "catalog": {"db_instance_id": ids["catalog"], "publication_seq": 41},
            }
        )
    )
    destination = tmp_path / "restored"
    result = run(destination, "db", "restore", "--input", backup)
    assert result["catalog"]["db_instance_id"] != ids["catalog"]
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == checksum
    with Store(destination, readonly=True) as store:
        assert (
            store.one("SELECT id FROM repositories WHERE id=?", (ids["repo"],))[0]
            == ids["repo"]
        )
        assert store.one("SELECT schema_version FROM catalog_meta")[0] == 2
