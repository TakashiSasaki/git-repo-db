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
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('repo','repo','{}')"
        )
        store.execute(
            "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,kind,request) VALUES('acquisition','repo','git','{}')"
        )
        store.execute(
            "INSERT INTO cache_locators(cache_locator_id,repository_uuidv4,path,access,state) VALUES('locator','repo','cache/repo/1.git','target_active','available')"
        )
        store.execute(
            "INSERT INTO active_cache_entries(active_cache_entry_id,cache_locator_id,generation,state,last_used_us,bytes) VALUES('active','locator',1,'active',0,4096)"
        )
        path = tmp_path / "cache/repo/1.git"
        path.mkdir(parents=True)
        (path / "HEAD").write_bytes(b"ref: refs/heads/main\n")
        yield store


def seed_job(store, job="job", attempt=1):
    with store.transaction():
        store.execute(
            "INSERT INTO jobs(job_id,kind,request,current_attempt) VALUES(?,'sync','{}',?)",
            (job, attempt),
        )
        store.execute(
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
    store.execute("UPDATE active_cache_entries SET last_used_us=?", (last_used_us,))
    monkeypatch.setattr(
        "repo_catalog.adapters.filesystem.cache.now_us",
        lambda: last_used_us + elapsed_us,
    )
    entry = CacheManager(store).collect()[0]
    assert entry["ttl_expired"] is expired
    assert entry["action"] == ("candidate" if expired else "retained")


def test_gc_obligations_and_preserved_source(cache_store, tmp_path):
    store = cache_store
    source = tmp_path / "preserved.git"
    source.mkdir()
    (source / "HEAD").write_bytes(b"preserved bytes")
    store.execute(
        "INSERT INTO cache_locators(cache_locator_id,repository_uuidv4,path,access,state) VALUES('preserved','repo',?,'source_readonly','available')",
        (str(source),),
    )
    store.execute(
        "INSERT INTO contents(content_id,byte_length,text_state) VALUES(1,14,'unknown')"
    )
    store.execute(
        "INSERT INTO content_locations(content_id,kind,locator,cache_locator_id,state) VALUES(1,'cache','active-content','locator','available')"
    )
    store.execute(
        "INSERT INTO content_locations(content_id,kind,locator,cache_locator_id,state) VALUES(1,'legacy','source-content','preserved','available')"
    )
    # The schema must reject attempts to enroll preserved source material in GC.
    with pytest.raises(sqlite3.IntegrityError, match="Readonly source cache"):
        store.execute(
            "INSERT INTO active_cache_entries(active_cache_entry_id,cache_locator_id,generation,state,last_used_us,bytes) VALUES('unsafe','preserved',2,'active',0,0)"
        )
    store.execute(
        "INSERT INTO preservation_obligations(git_acquisition_id,cache_locator_id,roots_fixed,structure_done,digest_done,text_done,published) VALUES('acquisition','locator',1,1,1,0,0)"
    )
    entry = CacheManager(store).collect(apply=True)[0]
    assert entry["action"] == "retained"
    assert entry["blocked_by"] == ["pending_obligations:acquisition"]
    store.execute("UPDATE preservation_obligations SET text_done=1,published=1")
    entry = CacheManager(store).collect(apply=True)[0]
    assert entry["action"] == "evicted"
    assert (
        store.one(
            "SELECT state FROM active_cache_entries WHERE active_cache_entry_id='active'"
        )[0]
        == "evicted"
    )
    assert (
        store.one("SELECT state FROM cache_locators WHERE cache_locator_id='locator'")[
            0
        ]
        == "missing"
    )
    assert (
        store.one(
            "SELECT state FROM cache_locators WHERE cache_locator_id='preserved'"
        )[0]
        == "available"
    )
    assert (
        store.one(
            "SELECT state FROM content_locations WHERE cache_locator_id='locator'"
        )[0]
        == "unavailable"
    )
    assert (
        store.one(
            "SELECT state FROM content_locations WHERE cache_locator_id='preserved'"
        )[0]
        == "available"
    )
    assert (source / "HEAD").read_bytes() == b"preserved bytes"


def test_gc_os_lock_fences_lease_cleanup(cache_store):
    store = cache_store
    seed_job(store)
    store.execute(
        "INSERT INTO cache_leases(active_cache_entry_id,job_id,attempt,acquired_at_us) VALUES('active','job',1,0)"
    )
    with FileLock(store.path / "locks/cache-active.lock"):
        entry = CacheManager(store).collect(apply=True)[0]
        assert entry["action"] == "retained"
        assert "generation_in_use" in entry["blocked_by"]
        assert store.one("SELECT count(*) FROM cache_leases")[0] == 1
    assert CacheManager(store).collect(apply=True)[0]["action"] == "evicted"
    assert store.one("SELECT count(*) FROM cache_leases")[0] == 0


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
        cache_store.one(
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
        "repository_uuidv4": "repo",
        "generation": 1,
        "path": "cache/repo/1.git",
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
        store.one("SELECT reserved FROM space_reservations WHERE attempt=1")[0] == 2048
    )
    with store.transaction():
        store.execute(
            "INSERT INTO job_attempts(job_id,attempt,state,checkpoint) VALUES('job',2,'running','{}')"
        )
        store.execute("UPDATE jobs SET current_attempt=2 WHERE job_id='job'")
    # Resuming cannot consume or release admission retained from an old attempt.
    with pytest.raises(CatalogError, match="Missing admission reservation"):
        capacity.monitor("job", capacity.used())
    capacity.reserve("job", 4096)
    assert capacity.reserved_elsewhere("job", 2) == 2048
    capacity.release("job")
    assert [
        tuple(row)
        for row in store.all("SELECT attempt,reserved FROM space_reservations")
    ] == [(1, 2048)]


def test_capacity_admission_failure_rolls_back(cache_store):
    seed_job(cache_store)
    capacity = Capacity(cache_store)
    with pytest.raises(Waiting) as raised:
        capacity.reserve("job", cache_store.config["cache"]["max_bytes"] + 1)
    assert raised.value.code == "CAPACITY_WAIT"
    assert cache_store.one("SELECT count(*) FROM space_reservations")[0] == 0


def test_acquisition_and_obligation_cannot_use_another_owner_cache(cache_store):
    store = cache_store
    seed_job(store)
    store.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES('other','other','{}')"
    )
    store.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,kind,request) VALUES('other-acquisition','other','git','{}')"
    )
    with pytest.raises(sqlite3.IntegrityError, match="cache owner mismatch"):
        store.execute(
            "INSERT INTO acquisition_progress(git_acquisition_id,job_id,attempt,state,generation,active_cache_entry_id) VALUES('other-acquisition','job',1,'planned',1,'active')"
        )
    with pytest.raises(sqlite3.IntegrityError, match="cache owner mismatch"):
        store.execute(
            "INSERT INTO preservation_obligations(git_acquisition_id,cache_locator_id,roots_fixed,structure_done,digest_done,text_done,published) VALUES('other-acquisition','locator',0,0,0,0,0)"
        )
