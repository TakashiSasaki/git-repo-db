"""Synthetic-only salvage, guard and ordinary runtime acceptance."""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from repo_catalog.adapters.import_v2 import workspace
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.finalization import finalize_catalog
from repo_catalog.application.import_service import import_catalog
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.import_workspace import inspect_import
from tests.support.integrated_fixture import AVAILABLE_TEXT, IDS, make_integrated_source
from tests.support.legacy_v2 import initialize


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_import_resume_preserves_exact_source_and_enters_ordinary_runtime(tmp_path):
    source, cache, *_ = make_integrated_source(tmp_path / "legacy")
    with sqlite3.connect(source) as legacy:
        settings = json.loads(
            legacy.execute(
                "SELECT settings FROM sources WHERE id=?", (IDS["other_source"],)
            ).fetchone()[0]
        )
        settings.update(repo_id=IDS["repo"], provider_repo_id="401")
        saved_settings = json.dumps(settings)
        legacy.execute(
            "UPDATE sources SET settings=? WHERE id=?",
            (saved_settings, IDS["other_source"]),
        )
    before = sha(source)
    cached = sha(cache / "synthetic-evidence")
    state = tmp_path / "catalog3"
    first = import_catalog(
        source, state, source_caches=[cache], batch_size=2, max_batches=3
    )
    assert first["complete"] is False and first["committed_batches"] == 3
    with (
        Store(state, allow_building=True) as store,
        workspace.attached(store.connection, store.db_path),
    ):
        assert store.one("SELECT lifecycle FROM database_identity")[0] == "building"
        with pytest.raises(CatalogError):
            finalize_catalog(store)
    completed = import_catalog(source, state, source_caches=[cache], batch_size=2)
    assert completed["complete"] and completed["lifecycle"] == "building"
    assert sha(source) == before and sha(cache / "synthetic-evidence") == cached
    with (
        Store(state, allow_building=True) as store,
        workspace.attached(store.connection, store.db_path),
    ):
        assert store.one("SELECT count(*) FROM conversion_runs")[0] == 1
        assert (
            store.one(
                "SELECT raw_text FROM contents WHERE raw_text=?", (AVAILABLE_TEXT,)
            )[0]
            == AVAILABLE_TEXT
        )
        assert (
            store.one("SELECT count(*) FROM jobs WHERE current_attempt IS NOT NULL")[0]
            == 0
        )
        assert {row[0] for row in store.all("SELECT kind FROM jobs")} == {"legacy"}
        assert store.one("SELECT count(*) FROM active_cache_entries")[0] == 0
        assert store.one("SELECT count(*) FROM space_reservations")[0] == 0
        assert store.one("SELECT count(*) FROM contents WHERE raw_text IS NULL")[0] > 0
        assert store.one("SELECT count(*) FROM root_manifests WHERE complete=1")[0] > 0
        assert (
            store.one(
                "SELECT count(*) FROM root_manifest_entries WHERE typeof(raw_path)='blob'"
            )[0]
            > 0
        )
        assert store.one("SELECT count(*) FROM document_observations")[0] > 2
        assert store.one("SELECT count(*) FROM fetch_occurrences")[0] > 2
        assert (
            store.one("SELECT count(*) FROM legacy_values WHERE storage_type='blob'")[0]
            > 0
        )
        assert (
            store.one(
                "SELECT count(*) FROM validation_results WHERE severity='blocking'"
            )[0]
            == 0
        )
        archived = store.one(
            "SELECT v.value_bytes FROM legacy_values v JOIN legacy_records r ON r.legacy_record_id=v.legacy_record_id WHERE r.source_table='sources' AND v.column_name='settings' AND v.value_bytes=?",
            (saved_settings.encode(),),
        )
        assert bytes(archived[0]).decode() == saved_settings
        assert store.one("SELECT count(*) FROM legacy_values")[0] > 500
        result = finalize_catalog(store)
        assert result["lifecycle"] == "validated"
    # Ordinary queries after finalization depend on neither source nor scratch.
    source.rename(source.with_suffix(".preserved"))
    shutil.rmtree(state / "import-v2")
    with Store(state, readonly=True) as store:
        assert (
            store.one(
                "SELECT repository_uuidv4 FROM repositories WHERE repository_uuidv4=?",
                (IDS["repo"],),
            )[0]
            == IDS["repo"]
        )
        assert not store.one(
            "SELECT name FROM sqlite_schema WHERE name='legacy_records'"
        )
        settings = json.loads(
            store.one(
                "SELECT settings FROM sources WHERE source_id=?", (IDS["other_source"],)
            )[0]
        )
        assert settings["repository_uuidv4"] == IDS["repo"]
        assert settings["provider_repository_id"] == "401"
        assert "repo_id" not in settings and "provider_repo_id" not in settings


def test_import_resume_refuses_changed_source_and_existing_runtime(tmp_path):
    source, cache = initialize(tmp_path / "legacy")
    state = tmp_path / "final"
    import_catalog(source, state, source_caches=[cache], max_batches=1)
    original = source.read_bytes()
    with source.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(CatalogError, match="protected") as error:
        import_catalog(source, state, source_caches=[cache])
    assert error.value.code == "SOURCE_REPLACED_OR_CHANGED"
    source.write_bytes(original)
    with pytest.raises(CatalogError) as error:
        import_catalog(source, source.parent)
    assert error.value.code == "SOURCE_WORKSPACE_OVERLAP"


def test_worker_guards_reject_source_writes_native_network_and_unguarded_sqlite(
    tmp_path,
):
    source = tmp_path / "source.sqlite3"
    source.write_bytes(b"synthetic preserved input")
    workspace = tmp_path / "guarded"
    workspace.mkdir()
    outside = tmp_path / "outside.sqlite3"
    script = r"""
import ctypes,json,sqlite3,sys
from pathlib import Path
from repo_catalog.adapters.import_v2 import guards
workspace,source,outside=map(Path,sys.argv[1:])
guards.install(workspace,[source])
results={}
for name,operation in [('source_write',lambda:source.open('wb')),('sqlite_write',lambda:sqlite3.connect(outside))]:
    try:operation()
    except PermissionError:results[name]=True
    else:results[name]=False
libc=ctypes.CDLL(None,use_errno=True)
results['native_network']=libc.socket(2,1,0)==-1 and ctypes.get_errno()==1
print(json.dumps(results))
"""
    child = subprocess.run(
        [sys.executable, "-c", script, str(workspace), str(source), str(outside)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(child.stdout) == {
        "source_write": True,
        "sqlite_write": True,
        "native_network": True,
    }
    assert source.read_bytes() == b"synthetic preserved input" and not outside.exists()


def test_installed_wheel_imports_without_checkout_documents(tmp_path):
    source, cache = initialize(tmp_path / "legacy")
    repository = Path(__file__).resolve().parents[2]
    distribution = tmp_path / "dist"
    subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--no-build-isolation",
            "--out-dir",
            str(distribution),
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    wheel = next(distribution.glob("*.whl"))
    site = tmp_path / "site"
    subprocess.run(
        ["uv", "pip", "install", "--no-deps", "--target", str(site), str(wheel)],
        capture_output=True,
        text=True,
        check=True,
    )
    state = tmp_path / "installed-state"
    script = "import sys; sys.path.insert(0,sys.argv.pop(1)); from repo_catalog.application.import_service import import_catalog; import json; print(json.dumps(import_catalog(sys.argv[1],sys.argv[2],source_caches=[sys.argv[3]])))"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(site)
    child = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(site),
            str(source),
            str(state),
            str(cache),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(child.stdout)["complete"] is True
    with inspect_import(state) as db:
        assert db.execute(
            "SELECT format_id,lifecycle FROM database_identity"
        ).fetchone() == ("repo-catalog/catalog3", "building")
        assert db.execute("SELECT count(*) FROM conversion_runs").fetchone()[0] == 1


@pytest.mark.parametrize("crash_point", ["before_commit", "after_commit"])
def test_process_death_rolls_back_whole_batch_then_resumes(tmp_path, crash_point):
    source, cache = initialize(tmp_path / "legacy")
    with sqlite3.connect(source) as db:
        db.execute(
            "INSERT INTO sources VALUES(?,?,?, ?, NULL)",
            (
                "synthetic-source",
                "local-git",
                "synthetic source",
                '{"url":"file:///synthetic/repo.git"}',
            ),
        )
        db.execute(
            "INSERT INTO repositories VALUES(?,'synthetic-source','local','synthetic-repo',?,?,?,NULL)",
            (
                "00000000-0000-4000-8000-000000000123",
                "synthetic/repo",
                "file:///synthetic/repo.git",
                "{}",
            ),
        )
    before = sha(source)
    state = tmp_path / "catalog3"
    # The receipt/config exists, but no archive batches have been committed.
    import_catalog(source, state, source_caches=[cache], max_batches=0)
    script = r"""
import os,sys
from repo_catalog.adapters.import_v2 import engine,worker
original=engine.run
def fault(point,**context):
    if point==os.environ['IMPORT_TEST_CRASH_POINT'] and context.get('table')=='archive:repositories':os._exit(77)
def crashing(*args,**kwargs):return original(*args,**kwargs,fault=fault)
engine.run=crashing
worker.main()
"""
    crash_environment = os.environ.copy()
    crash_environment["IMPORT_TEST_CRASH_POINT"] = crash_point
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
        env=crash_environment,
    )
    assert child.returncode == 77
    if crash_point == "after_commit":
        with sqlite3.connect(
            (state / "import-v2/workspace.sqlite3").as_uri() + "?mode=ro", uri=True
        ) as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM conversion_batches WHERE source_table='archive:repositories'"
                ).fetchone()[0]
                == 1
            )
    else:
        # Leave rollback recovery to the guarded importer; opening a writer here
        # would recover the journal before the boundary under test runs.
        assert (state / "import-v2/workspace.sqlite3-journal").is_file()
    result = import_catalog(source, state, source_caches=[cache])
    assert result["complete"] and sha(source) == before
    with inspect_import(state) as db:
        assert db.execute("SELECT count(*) FROM repositories").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT count(*) FROM legacy_records WHERE source_table='repositories'"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM conversion_batches WHERE source_table='archive:repositories'"
            ).fetchone()[0]
            == 1
        )
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchone() is None


def test_unsupported_source_schema_is_preserved_with_local_rejection_evidence(tmp_path):
    source, cache = initialize(tmp_path / "legacy")
    with sqlite3.connect(source) as db:
        db.execute(
            "CREATE TABLE unsupported_private_schema(synthetic_id INTEGER PRIMARY KEY, value TEXT)"
        )
        db.execute(
            "INSERT INTO unsupported_private_schema VALUES(1,'synthetic preserved value')"
        )
    before = sha(source)
    state = tmp_path / "catalog3"
    with pytest.raises(CatalogError) as error:
        import_catalog(source, state, source_caches=[cache])
    assert error.value.code == "SOURCE_SCHEMA_MISMATCH"
    assert sha(source) == before and not (state / "catalog.sqlite3").exists()
    report = json.loads((state / "import-v2/source-admission.json").read_bytes())
    assert report["state"] == "rejected" and report["sealed"] is False
    assert any(
        item["classification"] == "unsupported"
        for item in report["admission"]["preservation_dispositions"]
    )


def test_import_cancellation_stops_guarded_worker_and_resumes_committed_batches(
    tmp_path,
):
    source, cache = make_integrated_source(tmp_path / "legacy")
    before = sha(source)
    state = tmp_path / "catalog3"
    import_catalog(source, state, source_caches=[cache], max_batches=0)

    class CancelAfterCheckpoint(CancellationToken):
        def check(self):
            with sqlite3.connect(
                (state / "import-v2/workspace.sqlite3").as_uri() + "?mode=ro", uri=True
            ) as db:
                if db.execute("SELECT count(*) FROM conversion_batches").fetchone()[0]:
                    self.cancelled = True
            super().check()

    with pytest.raises(CatalogError) as error:
        import_catalog(
            source,
            state,
            source_caches=[cache],
            batch_size=100,
            token=CancelAfterCheckpoint(),
        )
    assert error.value.code == "CANCELLED" and error.value.retryable
    with inspect_import(state) as db:
        committed = db.execute("SELECT count(*) FROM conversion_batches").fetchone()[0]
        assert committed > 0
        assert not json.loads(
            db.execute("SELECT manifest FROM conversion_runs").fetchone()[0]
        )["complete"]
    result = import_catalog(source, state, source_caches=[cache])
    assert result["complete"] and result["new_batches"] < result["committed_batches"]
    assert sha(source) == before
