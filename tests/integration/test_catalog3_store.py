"""Mutable readers, capability boundary and atomic durable runtime jobs."""

import sqlite3

import pytest

from repo_catalog.adapters.sqlite.schema import SCHEMA_VERSION
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
            assert reader.revision()["local_revision"] == 0
        with writer.transaction():
            writer.advance_local_revision()
        with reader.transaction(read=True):
            assert reader.revision()["local_revision"] == 1
        with writer.transaction():
            writer.advance_local_revision()
        assert reader.revision()["local_revision"] == 2
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.advance_local_revision()


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
            assert reader.revision()["local_revision"] == 0
        return
    with Store(state) as writer, Store(state, readonly=True) as reader:
        with reader.transaction(read=True):
            assert reader.one("SELECT local_revision FROM database_identity")[0] == 0
            with writer.transaction():
                writer.advance_local_revision()
            assert reader.one("SELECT local_revision FROM database_identity")[0] == 0
        assert reader.revision()["local_revision"] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.advance_local_revision()


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
        assert (
            reader.one("SELECT schema_version FROM database_identity")[0]
            == SCHEMA_VERSION
        )


def test_job_attempt_resume_cleans_old_capacity_and_obeys_injected_time(tmp_path):
    initialize(tmp_path / "state")
    with Store(tmp_path / "state") as store:
        jobs = JobService(store, clock_us=lambda: 10_000_000)
        job = jobs.create("sync", {"kind": "git"})
        store.operational.execute(
            "INSERT INTO space_reservations(job_id,attempt,reserved,consumed) VALUES(?,1,4096,0)",
            (job,),
        )
        jobs.update(job, "waiting", "backoff", not_before_us=11_000_000)
        before = store.revision()
        with pytest.raises(Waiting) as waiting:
            jobs.resume(job)
        assert waiting.value.details["not_before_us"] == 11_000_000
        assert tuple(
            store.operational.one(
                "SELECT not_before_us,typeof(not_before_us) FROM job_attempts"
            )
        ) == (11_000_000, "integer")
        assert store.operational.one("SELECT current_attempt FROM jobs")[0] == 1
        jobs.clock_us = lambda: 12_000_000
        assert jobs.resume(job) == ("sync", {"kind": "git"})
        assert store.operational.one("SELECT current_attempt FROM jobs")[0] == 2
        assert (
            store.operational.one("SELECT state FROM job_attempts WHERE attempt=1")[0]
            == "waiting"
        )
        assert not store.operational.one("SELECT 1 FROM space_reservations")
        assert store.revision() == before
        legacy = jobs.create("legacy", {})
        jobs.update(legacy, "interrupted")
        with pytest.raises(CatalogError, match="historical jobs"):
            jobs.resume(legacy)


def test_job_retry_at_epoch_zero_is_a_real_deadline(tmp_path):
    initialize(tmp_path / "state")
    with Store(tmp_path / "state") as store:
        jobs = JobService(store, clock_us=lambda: -1)
        job = jobs.create("sync", {"kind": "git"})
        jobs.update(job, "waiting", "backoff", not_before_us=0)
        with pytest.raises(Waiting) as waiting:
            jobs.resume(job)
        assert waiting.value.details["not_before_us"] == 0
        assert store.operational.one("SELECT current_attempt FROM jobs")[0] == 1
        jobs.clock_us = lambda: 0
        assert jobs.resume(job) == ("sync", {"kind": "git"})
        assert store.operational.one("SELECT current_attempt FROM jobs")[0] == 2


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
    with pytest.raises(CatalogError, match="Current catalog format is required"):
        Store(tmp_path / "state")
    assert path.read_bytes() == before


@pytest.mark.parametrize("readonly", [False, True])
def test_previous_catalog3_identity_is_rejected_without_mutation(tmp_path, readonly):
    state = tmp_path / "state"
    initialize(state)
    with Store(state) as store:
        identity = tuple(
            store.one(
                "SELECT singleton,format_id,schema_version,db_instance_id,local_revision,ddl_sha256,lifecycle FROM database_identity"
            )
        )
    database = state / "catalog.sqlite3"
    database.unlink()
    with sqlite3.connect(database) as old:
        old.execute(
            "CREATE TABLE database_identity(singleton,format_id,schema_version,db_instance_id,local_revision,ddl_sha256,lifecycle)"
        )
        old.execute(
            "INSERT INTO database_identity(singleton,format_id,schema_version,db_instance_id,local_revision,ddl_sha256,lifecycle) VALUES(?,?,?,?,?,?,?)",
            (*identity[:2], 3, *identity[3:]),
        )
    before = database.read_bytes()
    with pytest.raises(CatalogError) as rejected:
        Store(state, readonly=readonly)
    assert rejected.value.code == "SCHEMA_ERROR"
    assert database.read_bytes() == before


def test_operational_store_lifecycle_and_ownership(tmp_path):
    state = tmp_path / "state"
    initialize(state)
    op_path = state / "operational.sqlite3"
    assert not op_path.exists()

    with Store(state) as store:
        # Accessing store.operational automatically creates operational.sqlite3 (PF-P12)
        op = store.operational
        assert op_path.exists()
        row = op.one("SELECT catalog_db_instance_id FROM operational_identity")
        assert row[0] == store.revision()["db_instance_id"]

    # Test foreign owner rejection (PF-P11, PF-P12)
    with sqlite3.connect(op_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS _bypass(id INT)")  # trigger bypass
        # Operational identity is protected by trigger, so drop triggers or update directly
        conn.execute("DROP TRIGGER IF EXISTS operational_identity_immutable")
        conn.execute(
            "UPDATE operational_identity SET catalog_db_instance_id='foreign-instance-id'"
        )
        conn.commit()

    with Store(state) as store:
        with pytest.raises(CatalogError) as exc_info:
            _ = store.operational
        assert exc_info.value.code == "WRONG_CATALOG_OWNER"

    # Test corrupt operational DB failure (PF-P12) - should not silently overwrite
    op_path.write_bytes(b"corrupt non-sqlite header")
    with Store(state) as store:
        with pytest.raises(CatalogError) as exc_info:
            _ = store.operational
        assert exc_info.value.code in ("DATABASE_CORRUPT", "DATABASE_ERROR")
        assert op_path.read_bytes() == b"corrupt non-sqlite header"


def test_search_store_lifecycle_and_fallback(tmp_path):
    from repo_catalog.adapters.sqlite.index import rebuild
    from repo_catalog.application.query_service import QueryService

    state = tmp_path / "state"
    initialize(state)
    search_path = state / "search.sqlite3"
    assert not search_path.exists()

    with Store(state) as store:
        # Ordinary read fails closed when search DB does not exist (PF-P17)
        with pytest.raises(CatalogError) as exc_info:
            store.open_search(readonly=True)
        assert exc_info.value.code == "INDEX_UNAVAILABLE"
        assert not search_path.exists()

    # QueryService falls back to direct scan without creating search DB (PF-P15)
    qs = QueryService(state)
    fallback_res = qs.query("search code", {"literal": "anything"})
    assert fallback_res.execution["search_fallback"] is True
    assert fallback_res.execution["search_fallback_reason"] == "index_unavailable"
    assert fallback_res.execution["backend"] == "scan"
    assert not search_path.exists()

    with Store(state) as store:
        # Explicit rebuild creates search DB (PF-P16, PF-P17)
        rebuild(store)
        assert search_path.exists()

        # Search index is now usable
        with store.open_search(readonly=True) as search_db:
            gen_count = search_db.one(
                "SELECT count(*) FROM index_generations WHERE state='ready'"
            )[0]
            assert gen_count == 4

        # Operational store recorded rebuild metrics (PF-P16)
        estimate = store.operational.estimate_rebuild_cost()
        assert estimate["runs"] >= 1
        assert "avg_duration_ms" in estimate

    # QueryService now uses search index without fallback
    active_res = qs.query("search code", {"literal": "anything"})
    assert active_res.execution.get("search_fallback") is not True
    assert active_res.execution["backend"] == "fts"
    assert "index_age_us" in active_res.execution

    # Corrupt search DB triggers fallback (PF-P15)
    search_path.write_bytes(b"corrupt search index")
    corrupt_res = qs.query("search code", {"literal": "anything"})
    assert corrupt_res.execution["search_fallback"] is True
    assert corrupt_res.execution["backend"] == "scan"


def test_reconcile_core_and_operational_writes_on_resume(tmp_path):
    from repo_catalog.adapters.github.persistence import ApiFacts
    from repo_catalog.config import DEFAULTS

    state = tmp_path / "recon_state"
    initialize(state)

    repo_id = "00000000-0000-4000-8000-000000000001"
    inst_id = "00000000-0000-4000-8000-000000000101"
    reg_id = "00000000-0000-4000-8000-000000000201"
    repo = {
        "repository_uuidv4": repo_id,
        "source_id": "src-1",
        "provider_repository_id": "12345",
    }
    with Store(state) as store:
        store.execute(
            "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','github','{}')",
            (inst_id,),
        )
        store.execute(
            "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('src-1',?,?, 'github_inventory','test','{}')",
            (reg_id, inst_id),
        )
        store.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'test-repo','{}')",
            (repo_id,),
        )
        store.execute(
            "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata,created_at_us) VALUES('bind-1',?,?,'12345','{}',0)",
            (repo_id, inst_id),
        )
        job_id = "job-recon"
        with store.operational.transaction():
            store.operational.execute(
                "INSERT INTO jobs(job_id,kind,request,current_attempt) VALUES(?,'sync','{}',1)",
                (job_id,),
            )
            store.operational.execute(
                "INSERT INTO job_attempts(job_id,attempt,state,checkpoint) VALUES(?,1,'running','{}')",
                (job_id,),
            )

        facts = ApiFacts(store, DEFAULTS["github"])

        # Case 1: Interruption between Operational complete update and Core completion marker commit:
        # Operational claims 'complete', but Core has NO completion marker.
        c1 = facts.begin(
            repo, None, "pr-list", job_id, "https://api.github.com/repos/test/pulls"
        )
        fc_id_1 = c1["fetch_collection_id"]
        # Manually inject false complete in Operational DB
        store.operational.execute(
            "UPDATE collection_progress SET state='complete' WHERE fetch_collection_id=?",
            (fc_id_1,),
        )
        # Core has no completion marker!
        # begin() must reject false completeness and start a safe fresh collection
        c1_retry = facts.begin(
            repo, None, "pr-list", job_id, "https://api.github.com/repos/test/pulls"
        )
        assert c1_retry["fetch_collection_id"] != fc_id_1

        # Case 2: Interruption after Operational cursor update but before Core page commit:
        # Operational has cursor='https://api.github.com/page2', but Core has 0 pages!
        c2 = facts.begin(
            repo, None, "pr-list", job_id, "https://api.github.com/repos/test/pulls"
        )
        fc_id_2 = c2["fetch_collection_id"]
        store.operational.execute(
            "UPDATE collection_progress SET cursor='https://api.github.com/page2' WHERE fetch_collection_id=?",
            (fc_id_2,),
        )
        # Core has 0 pages! begin() must reject false progress and start fresh collection
        c2_retry = facts.begin(
            repo, None, "pr-list", job_id, "https://api.github.com/repos/test/pulls"
        )
        assert c2_retry["fetch_collection_id"] != fc_id_2

        # Case 3: Core has committed completion marker, but Operational DB was lost/recreated:
        c3 = facts.begin(
            repo, None, "pr-list", job_id, "https://api.github.com/repos/test/pulls"
        )
        fc_id_3 = c3["fetch_collection_id"]
        store.execute(
            "INSERT INTO current_collection_pages(fetch_collection_id,ordinal,observed_at_us,has_next,members,status,parser_module,parser_version) VALUES(?,0,100,0,'[]',200,'test','1')",
            (fc_id_3,),
        )
        facts.finish(c3)
        assert (
            store.one(
                "SELECT 1 FROM completion_markers WHERE fetch_collection_id=? AND asserted_state='complete'",
                (fc_id_3,),
            )
            is not None
        )

        # Wipe Operational DB
        store.operational.close()
        store._operational_store = None
        (state / "operational.sqlite3").unlink()

        # Seed running job in fresh Operational DB
        with store.operational.transaction():
            store.operational.execute(
                "INSERT INTO jobs(job_id,kind,request,current_attempt) VALUES(?,'sync','{}',1)",
                (job_id,),
            )
            store.operational.execute(
                "INSERT INTO job_attempts(job_id,attempt,state,checkpoint) VALUES(?,1,'running','{}')",
                (job_id,),
            )

        # Reopen and request with reuse=True: must restore and treat as complete
        c3_reused = facts.begin(
            repo,
            None,
            "pr-list",
            job_id,
            "https://api.github.com/repos/test/pulls",
            reuse=True,
        )
        assert c3_reused["fetch_collection_id"] == fc_id_3
        assert c3_reused["state"] == "complete"
        assert (
            store.operational.one(
                "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
                (fc_id_3,),
            )[0]
            == "complete"
        )

    # Case 4: Read-only operations when Operational DB is absent:
    (state / "operational.sqlite3").unlink()
    from repo_catalog.application.query_service import QueryService

    qs = QueryService(state)
    # jobs list and cache status must not crash, but return empty
    res_jobs = qs.query("jobs list")
    assert res_jobs.data["items"] == []
    res_cache = qs.query("cache status")
    assert res_cache.data["items"] == []
