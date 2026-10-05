import hashlib
import sqlite3

import pytest

from scripts.schema_audit import diagnose, readonly, schema_inventory
from tests.e2e.test_github_sync import configure
from tests.support.cli import run
from tests.support.github_fixture import GitHubFixture


def file_sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").digest()


def test_schema_inventory_and_readonly_diagnostic(catalog):
    state, _, repos = catalog
    run(state, "sync", "git", "--repo", repos["alpha"])
    path = state / "catalog.sqlite3"
    before = file_sha(path)
    with readonly(path) as db:
        inventory = schema_inventory(db)
        assert len(inventory["tables"]) == 53
        assert len(inventory["triggers"]) == 2
        assert inventory["schema_version"] == 2
        report = diagnose(db, hash_payloads=True)
        assert report["violations"] == {}
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM repositories")
    assert file_sha(path) == before
    run(state, "index", "rebuild")
    before = file_sha(path)
    with readonly(path) as db:
        assert diagnose(db)["violations"] == {}
        assert len(schema_inventory(db)["tables"]) > 53
    assert file_sha(path) == before


def test_cross_owner_pointers_pass_v2_check_but_diagnostic_finds_them(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git", "--repo", repos["alpha"], "--repo", repos["beta"])
    with GitHubFixture(fixture) as api:
        _, repo, env = configure(state, api, fixture)
        run(state, "sync", "pr", "--repo", repo, env=env)
    path = state / "catalog.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        snapshot = db.execute(
            "SELECT current_snapshot FROM repositories WHERE id=?", (repos["beta"],)
        ).fetchone()[0]
        db.execute(
            "UPDATE repositories SET current_snapshot=? WHERE id=?",
            (snapshot, repos["alpha"]),
        )
        documents = db.execute(
            "SELECT id,current_version FROM pr_documents ORDER BY id LIMIT 2"
        ).fetchall()
        db.execute(
            "UPDATE pr_documents SET current_version=? WHERE id=?",
            (documents[1][1], documents[0][0]),
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    # Existing db check checks existence/publication but not owning repo/document.
    run(state, "db", "check", "--full")
    before = file_sha(path)
    with readonly(path) as db:
        report = diagnose(db)
    assert report["violations"]["current_snapshot"] == 1
    assert report["violations"]["current_document_version"] == 1
    assert file_sha(path) == before


def test_shape_checks_and_payload_hashing_find_fixture_corruption(catalog):
    state, _, repos = catalog
    run(state, "sync", "git", "--repo", repos["alpha"])
    path = state / "catalog.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("UPDATE jobs SET attempt=0,checkpoint='not-json' WHERE kind='sync'")
        db.execute("UPDATE git_objects SET verified=2 WHERE type='blob'")
        db.execute(
            "INSERT INTO api_responses(payload_sha256,body) VALUES(?,?)",
            (b"x" * 32, b'{"synthetic":true}'),
        )
    with readonly(path) as db:
        report = diagnose(db, hash_payloads=True)
    assert report["violations"]["attempt:jobs"] == 1
    assert report["violations"]["json:jobs.checkpoint"] == 1
    assert report["violations"]["boolean:git_objects.verified"] > 0
    assert report["violations"]["sha256:api_responses"] == 1
    assert "synthetic" not in str(report)


def test_readonly_rejects_unsealed_sidecars_and_missing_db(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError), readonly(missing):
        pass
    assert not missing.exists()
    with sqlite3.connect(missing):
        pass
    missing.with_name(missing.name + "-wal").touch()
    with pytest.raises(ValueError, match="Unsealed"), readonly(missing):
        pass
