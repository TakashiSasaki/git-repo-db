"""Mutable readers, capability boundary and atomic durable runtime jobs."""

import sqlite3

import pytest

from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.models import CatalogError, Waiting


def initialize(path):
    MaintenanceService(path).init("catalog-text-v1", 64 * 1024 * 1024, 0)


def test_readonly_snapshot_tracks_mutable_catalog_without_immutable(tmp_path):
    state = tmp_path / "state"
    initialize(state)
    with Store(state) as writer, Store(state, readonly=True) as reader:
        with reader.transaction(read=True):
            assert reader.revision()["publication_seq"] == 0
        with writer.transaction():
            writer.publish()
        with reader.transaction(read=True):
            assert reader.revision()["publication_seq"] == 1
        with writer.transaction():
            writer.publish()
        assert reader.revision()["publication_seq"] == 2
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.publish()


def test_optional_wal_is_guarded_or_reads_active_snapshot(tmp_path):
    state = tmp_path / "state"
    initialize(state)
    config = state / "catalog.toml"
    config.write_text(
        config.read_text().replace('journal_mode = "delete"', 'journal_mode = "wal"')
    )
    version = sqlite3.sqlite_version_info
    if not (version >= (3, 51, 3) or version in ((3, 44, 6), (3, 50, 7))):
        database = state / "catalog.sqlite3"
        before = database.read_bytes()
        with pytest.raises(CatalogError) as rejected:
            Store(state)
        assert rejected.value.code == "UNSAFE_WAL_RUNTIME"
        assert database.read_bytes() == before
        with Store(state, readonly=True) as reader:
            assert reader.revision()["publication_seq"] == 0
        return
    with Store(state) as writer, Store(state, readonly=True) as reader:
        with reader.transaction(read=True):
            assert reader.one("SELECT publication_seq FROM database_identity")[0] == 0
            with writer.transaction():
                writer.publish()
            assert reader.one("SELECT publication_seq FROM database_identity")[0] == 0
        assert reader.revision()["publication_seq"] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.publish()


def test_derived_fts_and_statistics_preserve_catalog_identity(tmp_path):
    initialize(tmp_path / "state")
    with Store(tmp_path / "state") as writer:
        writer.execute("CREATE VIRTUAL TABLE runtime_search USING fts5(body)")
        writer.execute("INSERT INTO runtime_search VALUES('synthetic sentinel')")
        writer.execute("ANALYZE")
    with Store(tmp_path / "state", readonly=True) as reader:
        assert (
            reader.one(
                "SELECT body FROM runtime_search WHERE runtime_search MATCH 'sentinel'"
            )[0]
            == "synthetic sentinel"
        )
        assert reader.one("SELECT schema_version FROM database_identity")[0] == 4


def test_job_attempt_resume_cleans_old_capacity_and_obeys_injected_time(tmp_path):
    initialize(tmp_path / "state")
    with Store(tmp_path / "state") as store:
        jobs = JobService(store, clock=lambda: 10)
        job = jobs.create("sync", {"kind": "git"})
        store.execute(
            "INSERT INTO space_reservations(job_id,attempt,reserved,consumed) VALUES(?,1,4096,0)",
            (job,),
        )
        jobs.update(job, "waiting", "backoff", 11)
        before = store.revision()
        with pytest.raises(Waiting):
            jobs.resume(job)
        assert store.one("SELECT current_attempt FROM jobs")[0] == 1
        jobs.clock = lambda: 12
        assert jobs.resume(job) == ("sync", {"kind": "git"})
        assert store.one("SELECT current_attempt FROM jobs")[0] == 2
        assert (
            store.one("SELECT state FROM job_attempts WHERE attempt=1")[0] == "waiting"
        )
        assert not store.one("SELECT 1 FROM space_reservations")
        assert store.revision() == before
        legacy = jobs.create("legacy", {})
        jobs.update(legacy, "interrupted")
        with pytest.raises(CatalogError, match="historical jobs"):
            jobs.resume(legacy)


def test_runtime_refuses_v2_without_modifying_it(tmp_path):
    initialize(tmp_path / "state")
    path = tmp_path / "state/catalog.sqlite3"
    path.unlink()
    with sqlite3.connect(path) as source:
        source.execute("CREATE TABLE catalog_meta(id INTEGER, schema_version INTEGER)")
        source.execute("INSERT INTO catalog_meta VALUES(1,2)")
        source.commit()
        source.execute("PRAGMA journal_mode=WAL")
    before = path.read_bytes()
    with pytest.raises(CatalogError, match="Catalog3 is required"):
        Store(tmp_path / "state")
    assert path.read_bytes() == before


@pytest.mark.parametrize("readonly", [False, True])
def test_previous_catalog3_identity_is_rejected_without_mutation(tmp_path, readonly):
    state = tmp_path / "state"
    initialize(state)
    with Store(state) as store:
        identity = tuple(
            store.one(
                "SELECT singleton,format_id,schema_version,db_instance_id,publication_seq,ddl_sha256,lifecycle FROM database_identity"
            )
        )
    database = state / "catalog.sqlite3"
    database.unlink()
    with sqlite3.connect(database) as old:
        old.execute(
            "CREATE TABLE database_identity(singleton,format_id,schema_version,db_instance_id,publication_seq,ddl_sha256,lifecycle)"
        )
        old.execute(
            "INSERT INTO database_identity(singleton,format_id,schema_version,db_instance_id,publication_seq,ddl_sha256,lifecycle) VALUES(?,?,?,?,?,?,?)",
            (*identity[:2], 3, *identity[3:]),
        )
    before = database.read_bytes()
    with pytest.raises(CatalogError) as rejected:
        Store(state, readonly=readonly)
    assert rejected.value.code == "SCHEMA_ERROR"
    assert database.read_bytes() == before
