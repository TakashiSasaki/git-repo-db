"""Separate scratch lifetime, pairing and multi-database commit/recovery."""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from repo_catalog.adapters.import_v2 import engine, workspace
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.finalization import finalize_catalog
from repo_catalog.application.import_service import import_catalog
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.models import CatalogError
from tests.support.integrated_fixture import IDS, make_integrated_source
from tests.support.legacy_v2 import initialize


def tables(db, schema="main"):
    return {
        r[0]
        for r in db.execute(
            f"SELECT name FROM {schema}.sqlite_schema WHERE type='table'"
        )
    }


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fresh_catalog_has_no_import_tables_or_workspace(tmp_path):
    state = tmp_path / "fresh"
    MaintenanceService(state).init("catalog-text-v1", 67108864, 0)
    with Store(state) as store:
        assert not (tables(store.connection) & workspace.TABLES)
        assert len(tables(store.connection)) == 66
        for table in tables(store.connection):
            assert (
                not {row[2] for row in store.all(f'PRAGMA foreign_key_list("{table}")')}
                & workspace.TABLES
            )
        assert finalize_catalog(store)["lifecycle"] == "validated"
        assert not workspace.has_attachment(store.connection)
    assert not (state / "import-v2").exists()


def test_finalized_catalog_operates_and_restores_without_workspace(tmp_path):
    source, cache = make_integrated_source(tmp_path / "source")
    state = tmp_path / "target"
    import_catalog(source, state, source_caches=[cache])
    path = workspace.path_for(state / "catalog.sqlite3")
    with engine.connect(state / "catalog.sqlite3") as db:
        assert not (tables(db) & workspace.TABLES)
        assert workspace.TABLES <= tables(db, workspace.SCHEMA)
        assert db.execute("SELECT count(*) FROM legacy_records").fetchone()[0] > 100
        assert db.execute("PRAGMA main.journal_mode").fetchone()[0] == "delete"
        assert (
            db.execute("PRAGMA import_workspace.journal_mode").fetchone()[0] == "delete"
        )
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("ATTACH ':memory:' AS unauthorized")
    with Store(state, allow_building=True) as store:
        result = finalize_catalog(store)
        assert result["lifecycle"] == "validated"
        assert not workspace.has_attachment(store.connection)
        counts = {
            t: store.one(f"SELECT count(*) FROM {t}")[0]
            for t in (
                "documents",
                "git_objects",
                "document_observations",
                "unresolved_payloads",
            )
        }
    with sqlite3.connect(path) as scratch:
        assert (
            scratch.execute("SELECT state FROM conversion_runs").fetchone()[0]
            == "validated"
        )
    # Only disposable synthetic workspace is removed. Neither original is touched.
    source_before = hash_file(source)
    shutil.rmtree(state / "import-v2")
    service = MaintenanceService(state)
    service.database("check", SimpleNamespace(full=True))
    service.database("finalize", SimpleNamespace())
    backup = tmp_path / "backup.sqlite3"
    service.database("backup", SimpleNamespace(output=backup))
    restored = tmp_path / "restored"
    MaintenanceService(restored).restore(backup)
    MaintenanceService(restored).database("check", SimpleNamespace(full=True))
    with Store(restored, readonly=True) as store:
        assert not (tables(store.connection) & workspace.TABLES)
        assert counts == {t: store.one(f"SELECT count(*) FROM {t}")[0] for t in counts}
    assert hash_file(source) == source_before
    assert not (restored / "import-v2").exists()


@pytest.mark.parametrize(
    "failure",
    ["missing", "other_catalog", "symlink", "hardlink", "changed_schema", "wal"],
)
def test_unsafe_or_missing_workspace_blocks_without_changing_catalog(tmp_path, failure):
    source, cache = initialize(tmp_path / "source")
    state = tmp_path / "target"
    import_catalog(source, state, source_caches=[cache])
    path = workspace.path_for(state / "catalog.sqlite3")
    if failure == "missing":
        path.unlink()
    elif failure in ("symlink", "hardlink"):
        path.unlink()
        if failure == "symlink":
            path.symlink_to(source)
        else:
            os.link(source, path)
    elif failure == "other_catalog":
        other = tmp_path / "other"
        import_catalog(source, other, source_caches=[cache])
        shutil.copyfile(workspace.path_for(other / "catalog.sqlite3"), path)
    elif failure == "changed_schema":
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE unexpected(value)")
    elif failure == "wal":
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA journal_mode=WAL")
    before = hash_file(state / "catalog.sqlite3"), hash_file(source)
    with Store(state, allow_building=True) as store:
        with pytest.raises(CatalogError) as error:
            finalize_catalog(store)
        assert error.value.code.startswith("IMPORT_WORKSPACE_")
        assert store.one("SELECT lifecycle FROM database_identity")[0] == "building"
        assert not workspace.has_attachment(store.connection)
    assert before == (hash_file(state / "catalog.sqlite3"), hash_file(source))
    with pytest.raises(CatalogError):
        import_catalog(source, state, source_caches=[cache])
    assert before == (hash_file(state / "catalog.sqlite3"), hash_file(source))


def test_initial_pair_publication_can_resume_after_process_death(tmp_path):
    source, cache = initialize(tmp_path / "source")
    state = tmp_path / "target"
    # Set up only the configuration/seal through the ordinary service; inject a
    # real process death between the two initial filename publications.
    script = """
import os,sys
from repo_catalog.adapters.import_v2 import engine,worker
original=engine.run
def fault(point,**context):
    if point=='after_catalog_initialization_publish':os._exit(77)
def crashing(*args,**kwargs):return original(*args,**kwargs,fault=fault)
engine.run=crashing
worker.main()
"""
    state.mkdir()
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            "--source",
            str(source),
            "--state-dir",
            str(state),
            "--source-cache",
            str(cache),
        ],
        capture_output=True,
        text=True,
    )
    assert child.returncode == 77, child.stderr
    assert (state / "catalog.sqlite3").is_file()
    assert (state / "import-v2/workspace.sqlite3.part").is_file()
    assert not (state / "import-v2/workspace.sqlite3").exists()
    assert import_catalog(source, state, source_caches=[cache])["complete"]
    with Store(state, allow_building=True) as store:
        assert finalize_catalog(store)["lifecycle"] == "validated"


@pytest.mark.parametrize(
    "point", ["after_data", "after_mapping", "before_commit", "after_commit"]
)
def test_target_and_workspace_batch_recover_together(tmp_path, point):
    source, cache = make_integrated_source(tmp_path / "source")
    state = tmp_path / "target"
    import_catalog(source, state, source_caches=[cache], max_batches=0)
    before = hash_file(source)
    script = """
import os,sys
from repo_catalog.adapters.import_v2 import engine,worker
original=engine.run
def fault(point,**context):
    if point==os.environ['CRASH_POINT'] and context.get('table')=='recipe:repositories':os._exit(77)
def crashing(*args,**kwargs):return original(*args,**kwargs,fault=fault)
engine.run=crashing
worker.main()
"""
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            "--source",
            str(source),
            "--state-dir",
            str(state),
            "--source-cache",
            str(cache),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "CRASH_POINT": point},
    )
    assert child.returncode == 77, child.stderr
    # Opening this paired connection performs SQLite rollback-journal recovery.
    with engine.connect(state / "catalog.sqlite3") as db:
        repositories = db.execute("SELECT count(*) FROM repositories").fetchone()[0]
        receipts = db.execute(
            "SELECT count(*) FROM conversion_batches WHERE source_table='recipe:repositories'"
        ).fetchone()[0]
        mappings = db.execute(
            "SELECT count(*) FROM id_mappings WHERE target_table='repositories'"
        ).fetchone()[0]
        assert (
            bool(repositories)
            == bool(receipts)
            == bool(mappings)
            == (point == "after_commit")
        )
    assert import_catalog(source, state, source_caches=[cache])["complete"]
    assert hash_file(source) == before
    with Store(state, allow_building=True) as store:
        assert finalize_catalog(store)["lifecycle"] == "validated"


@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
def test_finalization_process_death_preserves_paired_readiness_and_retries_once(
    tmp_path, point
):
    source, cache = make_integrated_source(tmp_path / "source")
    preserved = {
        path: hash_file(path) for path in (source, cache / "synthetic-evidence")
    }
    state = tmp_path / "target"
    assert import_catalog(source, state, source_caches=[cache])["complete"]

    def snapshot(store):
        queries = {
            "identity": "SELECT db_instance_id,lifecycle,publication_seq FROM database_identity",
            "runs": "SELECT conversion_run_id,state,manifest FROM conversion_runs ORDER BY conversion_run_id",
            "receipts": "SELECT conversion_run_id,observed_at_us,details FROM validation_results WHERE code='RUNTIME_FINALIZATION' ORDER BY conversion_run_id",
            "repositories": "SELECT repository_uuidv4,current_snapshot_id FROM repositories ORDER BY repository_uuidv4",
            "prs": "SELECT change_request_id,current_change_request_observation_id FROM change_requests ORDER BY change_request_id",
            "published": "SELECT change_request_observation_id,published FROM change_request_observations ORDER BY change_request_observation_id",
            "documents": "SELECT kind,provider_change_request_document_id,current_document_observation_id FROM documents ORDER BY kind,provider_change_request_document_id",
            "observation_count": "SELECT count(*) FROM document_observations",
            "batch_count": "SELECT count(*) FROM conversion_batches",
        }
        with workspace.attached(store.connection, store.db_path):
            for schema in ("main", workspace.SCHEMA):
                assert store.one(f"PRAGMA {schema}.integrity_check")[0] == "ok"
                assert not store.all(f"PRAGMA {schema}.foreign_key_check")
            return {
                name: [tuple(row) for row in store.all(query)]
                for name, query in queries.items()
            }

    with Store(state, allow_building=True) as store:
        before = snapshot(store)
    assert before["identity"][0][1:] == ("building", 0)
    assert before["runs"][0][1] == "paused"
    assert before["receipts"] == []
    assert all(row[-1] is None for row in before["documents"])

    # Kill the process at the actual transaction COMMIT without adding a
    # production fault API. Both variants reach all pending finalization writes;
    # they differ only in whether SQLite has committed the attached transaction.
    script = """
import os,sys
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.finalization import finalize_catalog
original=Store.execute
def crashing(self,sql,args=()):
    if sql != 'COMMIT':
        return original(self,sql,args)
    assert self.connection.in_transaction
    assert self.one('SELECT lifecycle,publication_seq FROM database_identity')[:] == ('validated',1)
    assert self.one('SELECT state FROM conversion_runs')[0] == 'validated'
    assert self.one("SELECT count(*) FROM validation_results WHERE code='RUNTIME_FINALIZATION'")[0] == 1
    assert self.one('SELECT count(*) FROM documents WHERE current_document_observation_id IS NOT NULL')[0] == 4
    if sys.argv[2] == 'after_commit':
        original(self,sql,args)
        assert not self.connection.in_transaction
    os._exit(77)
Store.execute=crashing
with Store(sys.argv[1],allow_building=True) as store:
    finalize_catalog(store)
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(state), point],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 77, child.stderr
    if point == "before_commit":
        assert (state / "catalog.sqlite3-journal").is_file()
        assert (state / "import-v2/workspace.sqlite3-journal").is_file()

    # Open normally: SQLite, not test-side journal cleanup, recovers each file.
    with Store(state, allow_building=True) as store:
        recovered = snapshot(store)
        if point == "before_commit":
            assert recovered == before
        else:
            assert recovered["identity"][0][1:] == ("validated", 1)
            assert recovered["runs"][0][1] == "validated"
            assert len(recovered["receipts"]) == 1
        first_retry = finalize_catalog(store)
        after = snapshot(store)
        assert first_retry["catalog"]["publication_seq"] == 1
        assert after["identity"][0] == (before["identity"][0][0], "validated", 1)
        assert after["runs"][0][1] == "validated"
        assert after["observation_count"] == before["observation_count"]
        assert after["batch_count"] == before["batch_count"]
        assert dict(after["repositories"]) == {
            IDS["repo"]: IDS["run"],
            IDS["mirror"]: None,
            IDS["local_repo"]: None,
        }
        assert after["prs"] == [(IDS["pr"], 303)]
        assert after["published"] == [(301, 1), (302, 1), (303, 1)]
        assert after["documents"] == [
            ("issue-comment", "901", 303),
            ("issue-comment", "902", None),
            ("issue-comment", "903", 304),
            ("pr-body", "701", None),
            ("pr-title", "701", None),
            ("review", "1001", 305),
            ("review-comment", "1002", 306),
        ]
        assert len(after["receipts"]) == 1
        receipt = json.loads(after["receipts"][0][2])
        assert {
            (item["owner_id"], item["candidate_id"])
            for item in receipt["restored"]
            if item["table"] == "repositories"
        } == {row for row in after["repositories"] if row[1] is not None}
        assert {
            (item["owner_id"], item["candidate_id"])
            for item in receipt["restored"]
            if item["table"] == "change_requests"
        } == set(after["prs"])
        assert {
            (
                item["document_key"]["change_request_id"],
                item["document_key"]["kind"],
                item["document_key"]["provider_change_request_document_id"],
                item["candidate_id"],
            )
            for item in receipt["restored"]
            if item["table"] == "documents"
        } == {(IDS["pr"], *row) for row in after["documents"] if row[-1] is not None}
        assert len(receipt["restored"]) == 6
        assert len(receipt["unresolved"]) == 2
        if point == "after_commit":
            assert after == recovered
        else:
            assert receipt["restored"] == first_retry["restored"]
        assert finalize_catalog(store)["catalog"] == first_retry["catalog"]
        assert snapshot(store) == after
    assert preserved == {path: hash_file(path) for path in preserved}
