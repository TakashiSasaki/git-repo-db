"""Separate scratch lifetime, pairing and multi-database commit/recovery."""

import hashlib
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
from tests.support.integrated_fixture import make_integrated_source
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
