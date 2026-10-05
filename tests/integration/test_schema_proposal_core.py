"""Executable design constraints only; no production migration is installed."""

import hashlib
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def proposed():
    sql = (
        Path(__file__).resolve().parents[2] / "docs/schema-hardening/proposal-core.sql"
    )
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(sql.read_text())
    db.execute(
        "INSERT INTO service_instances VALUES('instance','github','fixture',NULL,NULL,'{}')"
    )
    for name in ("a", "b"):
        db.execute("INSERT INTO repositories VALUES(?,?,NULL,NULL,'{}')", (name, name))
        db.execute(
            "INSERT INTO repository_bindings VALUES(?,?,?,?)",
            ("binding-" + name, name, "instance", name),
        )
        db.execute(
            "INSERT INTO repository_endpoints VALUES(?,?,?,'file',NULL)",
            ("endpoint-" + name, name, "file:///fixture/" + name),
        )
        db.execute(
            "INSERT INTO git_acquisitions VALUES(?,?,?,?,'sha1',NULL)",
            ("run-" + name, name, "endpoint-" + name, "file:///fixture/" + name),
        )
        db.execute(
            "INSERT INTO snapshots VALUES(?,?,?,1)",
            ("snapshot-" + name, "run-" + name, name),
        )
        db.execute(
            "INSERT INTO change_requests VALUES(?,?,?,'pull_request',1,NULL)",
            ("pr-" + name, name, "binding-" + name),
        )
        number = 1 if name == "a" else 2
        db.execute(
            "INSERT INTO change_request_observations VALUES(?,?,NULL,1,'{}')",
            (number, "pr-" + name),
        )
        raw = name.encode()
        db.execute(
            "INSERT INTO text_bodies VALUES(?,?,?,?)",
            (number, name, len(raw), hashlib.sha256(raw).digest()),
        )
        db.execute(
            "INSERT INTO documents VALUES(?,?,'pr-body','native',NULL,0)",
            ("doc-" + name, "pr-" + name),
        )
        db.execute(
            "INSERT INTO document_versions VALUES(?,?,?)",
            (number, "doc-" + name, number),
        )
        db.execute(
            "INSERT INTO review_threads VALUES(?,?)", ("thread-" + name, "pr-" + name)
        )
    yield db
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    db.close()


def test_scoped_owners_and_current_pointers(proposed):
    db = proposed
    for sql in (
        "UPDATE repositories SET current_snapshot_id='snapshot-b' WHERE id='a'",
        "UPDATE repositories SET preferred_endpoint_id='endpoint-b' WHERE id='a'",
        "UPDATE change_requests SET current_observation_id=2 WHERE id='pr-a'",
        "UPDATE documents SET current_version_id=2 WHERE id='doc-a'",
        "INSERT INTO document_observations VALUES(1,'doc-a',2,NULL,'conversion-time')",
        "INSERT INTO review_comments VALUES('doc-a','pr-a','thread-b')",
        "INSERT INTO code_observations VALUES(1,'pr-a',2,NULL,NULL,'partial')",
        "INSERT INTO fetch_collections VALUES('bad','a','pr-b','partial')",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql)
    db.execute("UPDATE repositories SET current_snapshot_id='snapshot-a' WHERE id='a'")
    for sql in (
        "UPDATE snapshots SET published=0 WHERE id='snapshot-a'",
        "DELETE FROM snapshots WHERE id='snapshot-a'",
        "UPDATE snapshots SET repo_id='b' WHERE id='snapshot-a'",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql)
    db.execute("UPDATE change_requests SET current_observation_id=1 WHERE id='pr-a'")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE change_request_observations SET published=0 WHERE id=1")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM change_request_observations WHERE id=1")
    db.execute("UPDATE documents SET current_version_id=1 WHERE id='doc-a'")
    for sql in (
        "DELETE FROM document_versions WHERE id=1",
        "UPDATE document_versions SET body_id=2 WHERE id=1",
        "UPDATE text_bodies SET body='changed' WHERE id=1",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(sql)
    db.execute(
        "INSERT INTO fetch_collections VALUES('collection','a','pr-a','complete')"
    )
    db.execute(
        "INSERT INTO code_listings VALUES('commit-list','pr-a','collection','commits')"
    )
    db.execute(
        "INSERT INTO code_listings VALUES('file-list','pr-a','collection','files')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO code_observations VALUES(2,'pr-a',1,'file-list','commit-list','complete')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO code_observations VALUES(2,'pr-a',1,NULL,NULL,'complete')"
        )
    db.execute(
        "INSERT INTO code_observations VALUES(2,'pr-a',1,'commit-list','file-list','complete')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE code_listings SET kind='files' WHERE id='commit-list'")


def test_same_seed_can_have_multiple_ref_origins(proposed):
    db = proposed
    db.execute(
        "INSERT INTO acquisition_roots VALUES(1,'run-a','sha1',?,'head')", (b"x" * 20,)
    )
    for ordinal, name in enumerate((b"refs/heads/main", b"refs/heads/alias")):
        db.execute(
            "INSERT INTO root_origins VALUES(?,1,'ref',?,?)",
            (ordinal + 1, name, ordinal),
        )
    assert db.execute("SELECT count(*) FROM acquisition_roots").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM root_origins").fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO acquisition_roots VALUES(2,'run-a','sha256',?,'head')",
            (b"x" * 20,),
        )


def test_body_dedup_does_not_dedup_observation_facts(proposed):
    db = proposed
    db.execute(
        "INSERT INTO document_observations VALUES(1,'doc-a',1,'observed-1','parsed-later')"
    )
    db.execute(
        "INSERT INTO document_observations VALUES(2,'doc-a',1,'observed-2','parsed-later')"
    )
    assert db.execute("SELECT count(*) FROM document_observations").fetchone()[0] == 2
    assert db.execute("SELECT count(*) FROM text_bodies WHERE id=1").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO job_attempts VALUES('job',0,'running')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO job_attempts VALUES('job',1,'invented')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO service_instances VALUES('bad','github','bad',NULL,NULL,'[]')"
        )
