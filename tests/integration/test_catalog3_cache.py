import copy
import sqlite3

import pytest

from repo_catalog.adapters.filesystem.cache import CacheManager
from repo_catalog.adapters.filesystem.capacity import Capacity
from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.config import DEFAULTS, serialize
from repo_catalog.domain.models import CatalogError, Waiting


@pytest.fixture
def cache_store(tmp_path):
    config = copy.deepcopy(DEFAULTS)
    config["cache"].update(max_bytes=64 * 1024 * 1024, min_free_bytes=0, ttl_seconds=0)
    (tmp_path / "catalog.toml").write_text(serialize(config))
    for directory in ("cache", "quarantine", "locks", "work"):
        (tmp_path / directory).mkdir()
    with Store(tmp_path, initialize=True) as store:
        store.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('10000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001','{}')"
        )
        store.execute(
            "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,kind,request) VALUES('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001','git','{}')"
        )
        store.operational.execute(
            "INSERT INTO cache_locators(cache_locator_id,repository_uuidv4,path,access,state) VALUES('locator','10000000-0000-4000-8000-000000000001','cache/10000000-0000-4000-8000-000000000001/1.git','target_active','available')"
        )
        store.operational.execute(
            "INSERT INTO active_cache_entries(active_cache_entry_id,cache_locator_id,generation,state,last_used_us,bytes) VALUES('active','locator',1,'active',0,4096)"
        )
        path = tmp_path / "cache/10000000-0000-4000-8000-000000000001/1.git"
        path.mkdir(parents=True)
        (path / "HEAD").write_bytes(b"ref: refs/heads/main\n")
        yield store


def seed_job(store, job="job", attempt=1):
    with store.operational.transaction():
        store.operational.execute(
            "INSERT INTO jobs(job_id,kind,request,current_attempt) VALUES(?,'sync','{}',?)",
            (job, attempt),
        )
        store.operational.execute(
            "INSERT INTO job_attempts(job_id,attempt,state,checkpoint) VALUES(?,?,'running','{}')",
            (job, attempt),
        )


@pytest.mark.parametrize(
    "elapsed_us,expired", [(-1, False), (999_999, False), (1_000_000, True)]
)
def test_cache_ttl_boundary_uses_integer_elapsed_microseconds(
    cache_store, monkeypatch, elapsed_us, expired
):
    store = cache_store
    last_used_us = 1_791_360_000_123_456
    store.config["cache"]["ttl_seconds"] = 1
    store.operational.execute(
        "UPDATE active_cache_entries SET last_used_us=?", (last_used_us,)
    )
    monkeypatch.setattr(
        "repo_catalog.adapters.filesystem.cache.now_us",
        lambda: last_used_us + elapsed_us,
    )
    entry = CacheManager(store).collect()[0]
    assert entry["ttl_expired"] is expired
    assert entry["action"] == ("candidate" if expired else "retained")


def test_gc_obligations_and_preserved_source(cache_store, tmp_path):
    store = cache_store
    seed_job(store)
    source = tmp_path / "preserved.git"
    source.mkdir()
    (source / "HEAD").write_bytes(b"preserved bytes")
    store.operational.execute(
        "INSERT INTO cache_locators(cache_locator_id,repository_uuidv4,path,access,state) VALUES('preserved','10000000-0000-4000-8000-000000000001',?,'source_readonly','available')",
        (str(source),),
    )
    store.execute("INSERT INTO contents(content_id,byte_length) VALUES(1,14)")
    # The schema must reject attempts to enroll preserved source material in GC.
    with pytest.raises(sqlite3.IntegrityError, match="Readonly source cache"):
        store.operational.execute(
            "INSERT INTO active_cache_entries(active_cache_entry_id,cache_locator_id,generation,state,last_used_us,bytes) VALUES('unsafe','preserved',2,'active',0,0)"
        )
    store.operational.execute(
        "INSERT INTO acquisition_progress(git_acquisition_id,job_id,attempt,state,generation,active_cache_entry_id) VALUES('20000000-0000-4000-8000-000000000001','job',1,'planned',1,'active')"
    )
    store.execute(
        "INSERT INTO preservation_obligations(git_acquisition_id,roots_fixed,structure_done,digest_done,text_done,complete) VALUES('20000000-0000-4000-8000-000000000001',1,1,1,0,0)"
    )
    entry = CacheManager(store).collect(apply=True)[0]
    assert entry["action"] == "retained"
    assert entry["blocked_by"] == [
        "pending_obligations:20000000-0000-4000-8000-000000000001"
    ]
    store.execute("UPDATE preservation_obligations SET text_done=1,complete=1")
    entry = CacheManager(store).collect(apply=True)[0]
    assert entry["action"] == "evicted"
    assert (
        store.operational.one(
            "SELECT state FROM active_cache_entries WHERE active_cache_entry_id='active'"
        )[0]
        == "evicted"
    )
    assert (
        store.operational.one(
            "SELECT state FROM cache_locators WHERE cache_locator_id='locator'"
        )[0]
        == "missing"
    )
    assert (
        store.operational.one(
            "SELECT state FROM cache_locators WHERE cache_locator_id='preserved'"
        )[0]
        == "available"
    )
    assert (source / "HEAD").read_bytes() == b"preserved bytes"


def test_gc_os_lock_fences_lease_cleanup(cache_store):
    store = cache_store
    seed_job(store)
    store.operational.execute(
        "INSERT INTO cache_leases(active_cache_entry_id,job_id,attempt,acquired_at_us) VALUES('active','job',1,0)"
    )
    with FileLock(store.path / "locks/cache-active.lock"):
        entry = CacheManager(store).collect(apply=True)[0]
        assert entry["action"] == "retained"
        assert "generation_in_use" in entry["blocked_by"]
        assert store.operational.one("SELECT count(*) FROM cache_leases")[0] == 1
    assert CacheManager(store).collect(apply=True)[0]["action"] == "evicted"
    assert store.operational.one("SELECT count(*) FROM cache_leases")[0] == 0


def test_gc_quarantine_recovery(cache_store, monkeypatch):
    import repo_catalog.adapters.filesystem.cache as cache_module

    def interrupted(event):
        assert event == "after_gc_rename"
        raise CatalogError("INTERRUPTED", "synthetic interruption")

    monkeypatch.setattr(cache_module, "hook", interrupted)
    with pytest.raises(CatalogError, match="synthetic interruption"):
        CacheManager(cache_store).collect(apply=True)
    assert (cache_store.path / "quarantine/active/HEAD").exists()
    assert (
        cache_store.operational.one(
            "SELECT state FROM active_cache_entries WHERE active_cache_entry_id='active'"
        )[0]
        == "evicting"
    )
    monkeypatch.setattr(cache_module, "hook", lambda _: None)
    assert CacheManager(cache_store).recover()[0]["action"] == "evicted"
    assert not (cache_store.path / "quarantine/active").exists()


def test_gc_rejects_quarantine_escape(cache_store):
    row = {
        "active_cache_entry_id": "../escape",
        "repository_uuidv4": "10000000-0000-4000-8000-000000000001",
        "generation": 1,
        "path": "cache/10000000-0000-4000-8000-000000000001/1.git",
    }
    with pytest.raises(CatalogError) as raised:
        CacheManager(cache_store).paths(row)
    assert raised.value.code == "UNMANAGED_CACHE_PATH"


def test_capacity_reservations_are_attempt_scoped(cache_store):
    store = cache_store
    seed_job(store)
    capacity = Capacity(store)
    capacity.reserve("job", 1024)
    capacity.reserve("job", 2048)
    assert (
        store.operational.one(
            "SELECT reserved FROM space_reservations WHERE attempt=1"
        )[0]
        == 2048
    )
    with store.operational.transaction():
        store.operational.execute(
            "INSERT INTO job_attempts(job_id,attempt,state,checkpoint) VALUES('job',2,'running','{}')"
        )
        store.operational.execute(
            "UPDATE jobs SET current_attempt=2 WHERE job_id='job'"
        )
    # Resuming cannot consume or release admission retained from an old attempt.
    with pytest.raises(CatalogError, match="Missing admission reservation"):
        capacity.monitor("job", capacity.used())
    capacity.reserve("job", 4096)
    assert capacity.reserved_elsewhere("job", 2) == 2048
    capacity.release("job")
    assert [
        tuple(row)
        for row in store.operational.all(
            "SELECT attempt,reserved FROM space_reservations"
        )
    ] == [(1, 2048)]


def test_capacity_admission_failure_rolls_back(cache_store):
    seed_job(cache_store)
    capacity = Capacity(cache_store)
    with pytest.raises(Waiting) as raised:
        capacity.reserve("job", cache_store.config["cache"]["max_bytes"] + 1)
    assert raised.value.code == "CAPACITY_WAIT"
    assert (
        cache_store.operational.one("SELECT count(*) FROM space_reservations")[0] == 0
    )


def test_acquisition_and_obligation_foreign_keys(cache_store):
    store = cache_store
    seed_job(store)
    # Foreign key checks on core and operational stores
    with pytest.raises(sqlite3.IntegrityError):
        store.operational.execute(
            "INSERT INTO acquisition_progress(git_acquisition_id,job_id,attempt,state,generation,active_cache_entry_id) VALUES('20000000-0000-4000-8000-000000000002','non-existent-job',1,'planned',1,'active')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.execute(
            "INSERT INTO preservation_obligations(git_acquisition_id,roots_fixed,structure_done,digest_done,text_done,complete) VALUES('non-existent-acq',0,0,0,0,0)"
        )


def test_gc_protects_bytes_after_operational_db_loss_and_permits_cleanup_when_complete(
    cache_store,
):
    store = cache_store
    repo_id = "10000000-0000-4000-8000-000000000001"
    acq_id = "20000000-0000-4000-8000-000000000001"
    # 1. Capture fixed Git roots in Core
    store.execute(
        "INSERT INTO preservation_obligations(git_acquisition_id,roots_fixed,structure_done,digest_done,text_done,complete) VALUES(?,1,1,1,0,0)",
        (acq_id,),
    )
    # 2. Leave Core preservation obligation incomplete (complete=0)
    # 3. Lose / reinitialize Operational DB
    if store._operational_store is not None:
        store._operational_store.close()
        store._operational_store = None
    op_path = store.path / "operational.sqlite3"
    if op_path.exists():
        op_path.unlink()
    # Re-access operational store (recreates empty Operational DB)
    assert store.operational.one("SELECT count(*) FROM active_cache_entries")[0] == 0

    cache_dir = store.path / f"cache/{repo_id}/1.git"
    assert (cache_dir / "HEAD").exists()

    # 4. Attempt cache GC under TTL or capacity pressure
    entries = CacheManager(store).collect(apply=True, pressure=True)
    assert len(entries) == 1
    # 5. Verify the needed physical bytes remain protected (action: retained)
    assert entries[0]["action"] == "retained"
    assert f"pending_obligations:{acq_id}" in entries[0]["blocked_by"]
    assert (cache_dir / "HEAD").exists()

    # 6. Complete preservation in Core
    store.execute(
        "UPDATE preservation_obligations SET text_done=1,complete=1 WHERE git_acquisition_id=?",
        (acq_id,),
    )
    # Verify that cache cleanup is permitted when all conditions are satisfied
    entries2 = CacheManager(store).collect(apply=True, pressure=True)
    assert len(entries2) == 1
    assert entries2[0]["action"] == "evicted"
    assert not cache_dir.exists()


def test_orphaned_physical_cache_enrolled_and_collision_prevention(
    cache_store, tmp_path
):
    import subprocess

    from repo_catalog.adapters.git.importer import GitImporter
    from repo_catalog.domain.models import CancellationToken

    store = cache_store
    repo_id = "10000000-0000-4000-8000-000000000001"
    seed_job(store, "job-collision", 1)

    # Initialize a valid dummy remote repository
    dummy_git = tmp_path / "dummy.git"
    subprocess.run(
        ["git", "init", "--bare", str(dummy_git)], check=True, capture_output=True
    )
    work_git = tmp_path / "work.git"
    subprocess.run(["git", "init", str(work_git)], check=True, capture_output=True)
    (work_git / "README").write_text("hello")
    subprocess.run(
        ["git", "-C", str(work_git), "config", "user.name", "Tester"], check=True
    )
    subprocess.run(
        ["git", "-C", str(work_git), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(["git", "-C", str(work_git), "add", "README"], check=True)
    subprocess.run(
        ["git", "-C", str(work_git), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work_git), "push", str(dummy_git), "HEAD:refs/heads/main"],
        check=True,
        capture_output=True,
    )

    # Place an orphaned cache generation 2 on disk
    orphaned_path = store.path / f"cache/{repo_id}/2.git"
    orphaned_path.mkdir(parents=True, exist_ok=True)
    (orphaned_path / "HEAD").write_bytes(b"ref: refs/heads/main\n")

    store.execute(
        "INSERT INTO repository_endpoints(repository_endpoint_id,repository_uuidv4,url,transport,label,metadata,created_at_us) VALUES('ep-1',?,?,'file',NULL,'{}',0)",
        (repo_id, dummy_git.as_uri()),
    )
    store.execute(
        "UPDATE repositories SET preferred_repository_endpoint_id='ep-1' WHERE repository_uuidv4=?",
        (repo_id,),
    )
    # Collector enrolls orphaned generation
    CacheManager(store).collect()
    row = store.operational.one("SELECT * FROM active_cache_entries WHERE generation=2")
    assert row is not None
    assert row["state"] == "active"

    # Now verify GitImporter prevents collision: next generation must be > max(core, op, disk) = 3
    importer = GitImporter(store, CancellationToken())
    # Make existing cache entries missing to force allocation of a new generation
    store.operational.execute("UPDATE active_cache_entries SET state='evicted'")
    store.operational.execute("UPDATE cache_locators SET state='missing'")

    # Run sync plan
    result = importer.sync(
        {"repository_uuidv4": repo_id},
        "job-collision",
    )
    assert result is not None
    snap_gen = store.one(
        "SELECT generation FROM snapshots WHERE repository_uuidv4=?", (repo_id,)
    )[0]
    assert snap_gen >= 3
    prog_gen = store.operational.one(
        "SELECT generation FROM acquisition_progress WHERE job_id='job-collision'"
    )[0]
    assert prog_gen >= 3
    new_cache = store.operational.one(
        "SELECT * FROM active_cache_entries WHERE generation >= 3"
    )
    assert new_cache is not None
    assert new_cache["generation"] != 1
    assert new_cache["generation"] != 2
