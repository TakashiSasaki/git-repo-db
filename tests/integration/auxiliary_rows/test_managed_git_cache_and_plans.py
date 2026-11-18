"""Actual finite disk reservations, conservative cache GC and frozen plans."""

import copy
import json
import os
from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.managed_git_cache import ManagedGitCache
from repo_catalog.adapters.sqlite.operational_coordination import WorkLedger
from repo_catalog.adapters.sqlite.operations_admin import OperationsAdmin
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.application.frozen_acquisition_plan import FrozenAcquisitionPlan
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity


def create_request(directory, *, request=None):
    request = request or RequestIdentity(str(uuid4()), str(uuid4()))
    attempt = str(uuid4())
    with OperationalAcquisitionLedger(directory) as store:
        store.ensure_request(
            request, scope={"intent": "managed-git-input"}, new_request=True
        )
        store.work_ledger.attempt(request, attempt)
    return request, attempt


@pytest.fixture
def catalog(tmp_path):
    initialize(
        tmp_path / "operational.sqlite3", "operational", str(uuid4()), str(uuid4())
    )
    return tmp_path


def git_cache(directory, name="repository.git"):
    path = directory / "cache" / name
    (path / "objects").mkdir(parents=True)
    (path / "HEAD").write_bytes(b"ref: refs/heads/main\n")
    (path / "objects" / "metadata.pack").write_bytes(b"synthetic metadata input")
    return path


def rows(directory):
    with closing(connect(directory / "operational.sqlite3", "operational")) as db:
        return [
            tuple(row)
            for row in db.execute(
                "SELECT * FROM request_continuations ORDER BY request_origin_uuidv4,request_uuidv4,continuation_scope_json"
            )
        ]


def test_disk_reservations_use_actual_stats_aggregate_other_attempts_and_rollback(
    catalog, monkeypatch
):
    first, attempt = create_request(catalog)
    second, another = create_request(catalog)
    git_cache(catalog)
    policy = ManagedGitCache(catalog, max_bytes=10000, ttl_seconds=0)
    measured = []
    original_statvfs = os.fstatvfs
    with monkeypatch.context() as observation:

        def record_actual_disk(fd):
            value = original_statvfs(fd)
            measured.append(value)
            return value

        observation.setattr(os, "fstatvfs", record_actual_disk)
        current = policy.status()
    assert current["used_bytes"] == sum(
        path.stat().st_size for path in (catalog / "cache").rglob("*") if path.is_file()
    )
    assert measured
    disk = measured[-1]
    assert current["free_bytes"] == disk.f_bavail * disk.f_frsize
    policy = ManagedGitCache(
        catalog, max_bytes=current["used_bytes"] + 100, ttl_seconds=0
    )
    assert policy.reserve(first, attempt, 60)["reserved_elsewhere"] == 0
    before = rows(catalog)
    with pytest.raises(CoordinationError, match="finite cumulative|cache") as error:
        policy.reserve(second, another, 50)
    assert error.value.code == "CAPACITY_WAIT"
    assert rows(catalog) == before
    assert policy.reserve(first, attempt, 40)["reserved_bytes"] == 40
    later = str(uuid4())
    with OperationalAcquisitionLedger(catalog) as store:
        store.work_ledger.attempt(first, later)
    with pytest.raises(CoordinationError) as error:
        policy.monitor(first, later)
    assert error.value.code == "CAPACITY_RESERVATION_UNAVAILABLE"
    assert policy.reserve(first, later, 50)["reserved_elsewhere"] == 40
    assert policy.release(first, later)["reserved_bytes"] == 0
    before = rows(catalog)
    with monkeypatch.context() as fault:

        def fail_checkpoint(*_args):
            raise RuntimeError("checkpoint persistence failed")

        fault.setattr(WorkLedger, "_save_checkpoint", fail_checkpoint)
        with pytest.raises(RuntimeError, match="checkpoint persistence"):
            policy.release(first, attempt)
    assert rows(catalog) == before
    assert policy.monitor(first, attempt)["reserved_bytes"] == 40
    assert policy.release(first, attempt)["state"] == "released"


def test_minimum_actual_free_space_and_growth_are_enforced(catalog):
    request, attempt = create_request(catalog)
    path = git_cache(catalog)
    cache = ManagedGitCache(catalog, max_bytes=100000, ttl_seconds=0)
    disk = os.statvfs(catalog / "cache")
    blocked = ManagedGitCache(
        catalog,
        max_bytes=100000,
        min_free_bytes=disk.f_blocks * disk.f_frsize + 1,
        ttl_seconds=0,
    )
    before = rows(catalog)
    with pytest.raises(CoordinationError) as error:
        blocked.reserve(request, attempt, 1)
    assert error.value.code == "CAPACITY_WAIT"
    assert rows(catalog) == before
    cache.reserve(request, attempt, 4)
    (path / "objects" / "additional.pack").write_bytes(b"more than four bytes")
    with pytest.raises(CoordinationError) as error:
        cache.monitor(request, attempt)
    assert error.value.code == "CAPACITY_WAIT"


@pytest.mark.parametrize(
    "elapsed,expired", [(-1, False), (999999, False), (1000000, True)]
)
def test_integer_ttl_boundary_and_active_protection_preserve_sources(
    catalog, elapsed, expired
):
    request, attempt = create_request(catalog)
    managed = git_cache(catalog)
    orphan = catalog / "cache" / "unregistered.pack"
    orphan.write_bytes(b"unregistered input is preserved")
    source = catalog / "unmanaged-source"
    source.write_bytes(b"source sentinel must survive")
    (catalog / "cache" / "outside").symlink_to(source)
    cache = ManagedGitCache(catalog, max_bytes=100000, ttl_seconds=1)
    observed = 2_000_000
    entry = cache.register(request, attempt, "repository.git", observed)
    assert cache.reuse("repository.git")["availability"] == "reuse_candidate"
    assert (
        cache.collect(apply=True, now_us=observed + 2_000_000)["protected_requests"]
        == 1
    )
    assert managed.exists()
    OperationsAdmin(catalog).transition(request, complete=True)
    preview = cache.collect(now_us=observed + elapsed)
    assert bool(preview["candidates"]) is expired
    assert not preview["removed"] and managed.exists()
    applied = cache.collect(apply=True, now_us=observed + elapsed)
    assert applied["removed"] == ([entry["path_hex"]] if expired else [])
    assert managed.exists() is not expired
    assert orphan.read_bytes() == b"unregistered input is preserved"
    assert source.read_bytes() == b"source sentinel must survive"
    assert (catalog / "cache" / "outside").is_symlink()
    assert cache.reuse("repository.git")["availability"] == (
        "reuse_unavailable" if expired else "reuse_candidate"
    )


def test_symlink_entries_unknown_orphans_and_operational_loss_never_authorize_purge(
    catalog,
):
    request, attempt = create_request(catalog)
    managed = git_cache(catalog)
    source = catalog / "source"
    source.mkdir()
    (source / "HEAD").write_bytes(b"preserved source")
    (managed / "linked-source").symlink_to(source, target_is_directory=True)
    cache = ManagedGitCache(catalog, max_bytes=100000, ttl_seconds=0)
    cache.register(request, attempt, "repository.git", 1)
    OperationsAdmin(catalog).transition(request, complete=True)
    assert not cache.collect(apply=True, now_us=2)["removed"]
    assert (source / "HEAD").read_bytes() == b"preserved source"
    with pytest.raises(ValueError, match="relative"):
        cache.register(request, attempt, "../source", 3)
    identity = None
    with closing(connect(catalog / "operational.sqlite3", "operational")) as db:
        identity = tuple(
            db.execute(
                "SELECT repository_uuidv4,catalog_instance_uuidv4 FROM store_identity"
            ).fetchone()
        )
    (catalog / "operational.sqlite3").unlink()
    for suffix in ("-wal", "-shm"):
        (catalog / ("operational.sqlite3" + suffix)).unlink(missing_ok=True)
    assert cache.reuse("repository.git") == {"availability": "reuse_unavailable"}
    initialize(catalog / "operational.sqlite3", "operational", *identity)
    assert cache.reuse("repository.git")["availability"] == "reuse_unavailable"
    assert not cache.collect(apply=True, now_us=10)["removed"]
    assert managed.exists() and (source / "HEAD").read_bytes() == b"preserved source"
    with OperationalAcquisitionLedger(catalog) as store:
        with pytest.raises(CoordinationError) as error:
            store.ensure_request(request, new_request=True)
        assert error.value.code == "CONTINUATION_UNAVAILABLE"


def test_preview_does_not_create_a_cache_directory_and_missing_checkpoint_refuses(
    catalog,
):
    request, attempt = create_request(catalog)
    cache = ManagedGitCache(catalog, max_bytes=100000, ttl_seconds=0)
    assert not cache.collect()["removed"]
    assert not (catalog / "cache").exists()
    git_cache(catalog)
    cache.register(request, attempt, "repository.git", 1)
    with closing(connect(catalog / "operational.sqlite3", "operational")) as db:
        db.execute(
            "DELETE FROM request_continuations WHERE continuation_scope_json=?",
            ('["work-ledger","checkpoint",1]',),
        )
    assert cache.reuse("repository.git")["availability"] == "reuse_unavailable"
    with pytest.raises(CoordinationError) as error:
        cache.collect(apply=True, now_us=2)
    assert error.value.code == "CONTINUATION_UNAVAILABLE"
    assert (catalog / "cache" / "repository.git" / "HEAD").exists()


def test_frozen_multi_source_plan_survives_resume_and_keeps_only_credential_references(
    catalog, monkeypatch
):
    request, attempt = create_request(catalog)
    a, b = str(uuid4()), str(uuid4())
    sources = [
        {
            "source_registration_uuidv4": a,
            "kind": "github_inventory",
            "settings": {"owner": "original", "api": "https://synthetic.invalid/api"},
        },
        {
            "source_registration_uuidv4": b,
            "kind": "manual_git",
            "settings": {"url": "file:///original.git"},
        },
    ]
    references = {
        a: {"kind": "environment", "name": "PLAN_TEST_TOKEN"},
        b: {"kind": "credential-helper", "name": "local-profile"},
    }
    monkeypatch.setenv("PLAN_TEST_TOKEN", "synthetic-secret-value-never-persist")
    original = copy.deepcopy({"sources": sources, "credential_refs": references})
    with OperationalAcquisitionLedger(catalog) as store:
        plans = FrozenAcquisitionPlan(store)
        assert plans.freeze(request, sources, references) == original
        sources[0]["settings"]["owner"] = "replacement"
        sources.append(
            {"source_registration_uuidv4": str(uuid4()), "kind": "late", "settings": {}}
        )
        assert plans.freeze(request, sources, references) == original
        store.work_ledger.attempt(request, str(uuid4()))
    with OperationalAcquisitionLedger(catalog) as reopened:
        assert FrozenAcquisitionPlan(reopened).load(request) == original
    assert "synthetic-secret-value-never-persist" not in json.dumps(rows(catalog))
    assert "PLAN_TEST_TOKEN" in json.dumps(rows(catalog))


@pytest.mark.parametrize(
    "settings",
    [
        {"Authorization": "Bearer secret"},
        {"url": "https://user:secret@synthetic.invalid/repo"},
        {"nested": {"url": "https://synthetic.invalid/repo?access_token=secret"}},
        {"accessToken": "secret"},
        {"git_config": {"http.extraHeader": "Authorization: Bearer synthetic-secret"}},
        {"http.extraHeader": "Authorization: Bearer synthetic-secret"},
        {"http.https://synthetic.invalid/.extraHeader": "Cookie: synthetic-secret"},
        {"headers": {"X-Api-Key": "synthetic-secret"}},
        {"repository.sshCommand": "ssh -i synthetic-private-key"},
        {"private_key": "synthetic-private-key"},
        {"nested": {"client_secret": "synthetic-secret"}},
    ],
)
def test_secret_bearing_frozen_settings_reject_before_any_progress_write(
    catalog, settings
):
    request, _ = create_request(catalog)
    source = {
        "source_registration_uuidv4": str(uuid4()),
        "kind": "git",
        "settings": settings,
    }
    before = rows(catalog)
    with OperationalAcquisitionLedger(catalog) as store:
        with pytest.raises(ValueError, match="secret-bearing"):
            FrozenAcquisitionPlan(store).freeze(request, [source], {})
    assert rows(catalog) == before


def test_unknown_credential_reference_and_frozen_checkpoint_failure_do_not_persist(
    catalog, monkeypatch
):
    request, _ = create_request(catalog)
    ident = str(uuid4())
    sources = [{"source_registration_uuidv4": ident, "kind": "git", "settings": {}}]
    before = rows(catalog)
    with OperationalAcquisitionLedger(catalog) as store:
        plans = FrozenAcquisitionPlan(store)
        with pytest.raises(ValueError, match="reference"):
            plans.freeze(
                request, sources, {ident: {"kind": "inline-token", "name": "secret"}}
            )
        with monkeypatch.context() as fault:

            def fail(*_args):
                raise RuntimeError("checkpoint persistence failed")

            fault.setattr(WorkLedger, "_save_checkpoint", fail)
            with pytest.raises(RuntimeError, match="checkpoint persistence"):
                plans.freeze(request, sources, {})
    assert rows(catalog) == before
