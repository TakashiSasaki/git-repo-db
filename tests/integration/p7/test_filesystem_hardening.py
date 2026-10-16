"""Independent Linux local-filesystem failures; no host power-loss claim."""

import hashlib
import json
import multiprocessing
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite import recovery as module
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import (
    ActivationError,
    BackupScope,
    BackupValidationError,
    CatalogStoppedError,
    RecoveryError,
    RestoreValidationError,
)


@pytest.fixture
def backup(synthetic_catalog, tmp_path):
    path = tmp_path / "backup"
    RecoveryService().create_consistent_backup(
        synthetic_catalog, path, BackupScope.PAIRED
    )
    return path


def rewrite_manifest(backup, data):
    value = json.dumps(data).encode()
    (backup / "manifest.json").write_bytes(value)
    (backup / "manifest.json.sha256").write_text(
        hashlib.sha256(value).hexdigest() + "  manifest.json\n"
    )


@pytest.mark.parametrize("name", ["manifest.json", "manifest.json.sha256", "stores"])
def test_restore_rejects_symlink_components(backup, tmp_path, repo_uuid, name):
    original = backup / name
    outside = tmp_path / (name + ".outside")
    original.rename(outside)
    original.symlink_to(outside)
    with pytest.raises(RestoreValidationError):
        RecoveryService().restore_backup(backup, tmp_path / "dest", repo_uuid)
    assert not (tmp_path / "dest").exists()


@pytest.mark.parametrize("data", [[], None, {"stores": []}, {"manifest_version": True}])
def test_malformed_manifest_fails_closed(backup, tmp_path, repo_uuid, data):
    rewrite_manifest(backup, data)
    with pytest.raises(RestoreValidationError):
        RecoveryService().restore_backup(backup, tmp_path / "dest", repo_uuid)


def test_oversized_manifest_is_rejected_before_json(
    backup, tmp_path, repo_uuid, monkeypatch
):
    (backup / "manifest.json").write_bytes(b" " * (65536 + 1))
    monkeypatch.setattr(module.json, "loads", lambda *a: pytest.fail("JSON allocated"))
    with pytest.raises(RestoreValidationError, match="finite byte limit"):
        RecoveryService().restore_backup(backup, tmp_path / "dest", repo_uuid)


@pytest.mark.parametrize(
    "sidecar", ["core.sqlite3-wal", "core.sqlite3-shm", "extra-dir"]
)
def test_normal_backup_sidecars_and_extras_rejected(
    backup, tmp_path, repo_uuid, sidecar
):
    path = backup / "stores" / sidecar
    if sidecar == "extra-dir":
        path.mkdir()
    else:
        path.write_bytes(b"")
    with pytest.raises(RestoreValidationError, match="Unexpected"):
        RecoveryService().restore_backup(backup, tmp_path / "dest", repo_uuid)


def test_copied_bytes_not_prior_hash_control_restore(
    backup, tmp_path, repo_uuid, monkeypatch
):
    original = module._copy_verified_fd

    def mutate(fd, target, size, digest):
        with (backup / "stores/core.sqlite3").open("r+b") as stream:
            stream.seek(100)
            stream.write(b"changed")
        return original(fd, target, size, digest)

    monkeypatch.setattr(module, "_copy_verified_fd", mutate)
    with pytest.raises(RestoreValidationError, match="mutation or SHA-256"):
        RecoveryService().restore_backup(backup, tmp_path / "dest", repo_uuid)
    assert not (tmp_path / "dest").exists()


def test_pinned_source_survives_parent_symlink_swap(
    backup, tmp_path, repo_uuid, monkeypatch
):
    original = module._copy_verified_fd
    moved = tmp_path / "original-stores"

    def swap(fd, target, size, digest):
        if not moved.exists():
            (backup / "stores").rename(moved)
            hostile = tmp_path / "hostile"
            hostile.mkdir()
            (hostile / "core.sqlite3").write_bytes(b"untrusted substitution")
            (backup / "stores").symlink_to(hostile)
        return original(fd, target, size, digest)

    monkeypatch.setattr(module, "_copy_verified_fd", swap)
    receipt = RecoveryService().restore_backup(backup, tmp_path / "dest", repo_uuid)
    assert receipt.revalidated_clean


def _publish_worker(stage, dest, gate, results):
    gate.wait()
    try:
        module._atomic_publish_noreplace(Path(stage), Path(dest))
    except BackupValidationError:
        results.put("exists")
    else:
        results.put("published")


def test_two_processes_publish_exactly_one_destination(tmp_path):
    ctx = multiprocessing.get_context("fork")
    gate, results = ctx.Event(), ctx.Queue()
    children = []
    for name in ("a", "b"):
        stage = tmp_path / name
        stage.mkdir()
        (stage / "identity").write_text(name)
        child = ctx.Process(
            target=_publish_worker, args=(stage, tmp_path / "dest", gate, results)
        )
        child.start()
        children.append(child)
    gate.set()
    for child in children:
        child.join(10)
        assert child.exitcode == 0
    assert sorted(results.get(timeout=1) for _ in children) == ["exists", "published"]
    assert (tmp_path / "dest/identity").read_text() in {"a", "b"}


def test_publication_parent_swap_uses_pinned_fd(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    parent.mkdir()
    stage = parent / "stage"
    stage.mkdir()
    real_cdll = module.ctypes.CDLL
    moved = tmp_path / "moved"

    # Python bound methods cannot carry ctypes signatures; use a callable wrapper.
    class Rename:
        def __call__(self, *args):
            parent.rename(moved)
            parent.symlink_to(tmp_path / "unrelated")
            return real_cdll(None, use_errno=True).renameat2(*args)

    class Library:
        renameat2 = Rename()

    monkeypatch.setattr(module.ctypes, "CDLL", lambda *a, **k: Library())
    module._atomic_publish_noreplace(stage, parent / "dest")
    assert (moved / "dest").is_dir()
    assert not (tmp_path / "unrelated").exists()


def test_sync_failure_never_returns_restore_success(
    backup, tmp_path, repo_uuid, monkeypatch
):
    def fail(fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(module.os, "fsync", fail)
    with pytest.raises(OSError, match="injected fsync"):
        RecoveryService().restore_backup(backup, tmp_path / "dest", repo_uuid)
    assert not (tmp_path / "dest").exists()


def test_rename_failure_never_publishes(backup, tmp_path, repo_uuid, monkeypatch):
    monkeypatch.setattr(
        module,
        "_atomic_publish_noreplace",
        lambda *a, **kw: (_ for _ in ()).throw(RecoveryError("rename failed")),
    )
    with pytest.raises(RecoveryError, match="rename failed"):
        RecoveryService().restore_backup(backup, tmp_path / "dest", repo_uuid)
    assert not (tmp_path / "dest").exists()


def test_hard_kill_during_copy_preserves_evidence(backup, tmp_path, repo_uuid):
    before = {
        str(p.relative_to(backup)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in backup.rglob("*")
        if p.is_file()
    }
    script = """
import os, signal, sys
from pathlib import Path
from repo_catalog.adapters.sqlite import recovery
from repo_catalog.application.recovery import RecoveryService
def die(*args):
    os.kill(os.getpid(), signal.SIGKILL)
recovery._copy_verified_fd = die
RecoveryService().restore_backup(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
"""
    env = dict(os.environ, PYTHONPATH=str(Path(module.__file__).parents[3]))
    run = subprocess.run(
        [sys.executable, "-c", script, str(backup), str(tmp_path / "dest"), repo_uuid],
        env=env,
    )
    assert run.returncode == -signal.SIGKILL
    assert not (tmp_path / "dest").exists()
    assert before == {
        str(p.relative_to(backup)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in backup.rglob("*")
        if p.is_file()
    }
    assert list(tmp_path.glob("dest.tmp.*"))  # interrupted staging remains inspectable


def test_activation_refuses_stopped_catalog(synthetic_catalog, tmp_path):
    module.stop_catalog(synthetic_catalog, "confirmed corruption")
    with pytest.raises(CatalogStoppedError):
        RecoveryService().activate_catalog(synthetic_catalog, tmp_path / "active")
    assert not (tmp_path / "active").exists()


def test_activation_alias_is_rejected(synthetic_catalog):
    with pytest.raises(ActivationError, match="distinct"):
        RecoveryService().activate_catalog(synthetic_catalog, synthetic_catalog)


def test_restore_destination_parent_swap_cannot_redirect_files(
    backup, tmp_path, repo_uuid, monkeypatch
):
    parent = tmp_path / "destination-parent"
    parent.mkdir()
    moved = tmp_path / "moved-parent"
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    original = module._copy_verified_fd

    def swap(fd, target, size, digest):
        if not moved.exists():
            parent.rename(moved)
            parent.symlink_to(unrelated)
        return original(fd, target, size, digest)

    monkeypatch.setattr(module, "_copy_verified_fd", swap)
    with pytest.raises(OSError):
        RecoveryService().restore_backup(backup, parent / "dest", repo_uuid)
    assert not list(unrelated.iterdir())
    assert (moved / "dest/core.sqlite3").is_file()  # coherent but unacknowledged


def test_post_rename_sync_failure_is_uncertain_publication(tmp_path, monkeypatch):
    stage, dest = tmp_path / "stage", tmp_path / "dest"
    stage.mkdir()
    monkeypatch.setattr(
        module.os,
        "fsync",
        lambda fd: (_ for _ in ()).throw(OSError("directory sync failed")),
    )
    with pytest.raises(OSError, match="directory sync failed"):
        module._atomic_publish_noreplace(stage, dest)
    assert dest.is_dir()
    assert not stage.exists()


def _activation_paused(catalog, locator, entered, release):
    original = module.SQLiteRecoveryAdapter._validate_and_summarize_core

    def validate(self, path):
        entered.set()
        if not release.wait(10):
            raise RuntimeError("test did not release validation")
        return original(self, path)

    module.SQLiteRecoveryAdapter._validate_and_summarize_core = validate
    RecoveryService().activate_catalog(Path(catalog), Path(locator))


def _enter_writer(catalog, attempted, acquired):
    attempted.set()
    with module.catalog_gate(Path(catalog), exclusive=True):
        acquired.set()


def test_activation_holds_writer_cut_through_publication(synthetic_catalog, tmp_path):
    ctx = multiprocessing.get_context("fork")
    entered, release, attempted, acquired = [ctx.Event() for _ in range(4)]
    activation = ctx.Process(
        target=_activation_paused,
        args=(synthetic_catalog, tmp_path / "active", entered, release),
    )
    activation.start()
    assert entered.wait(10)
    writer = ctx.Process(
        target=_enter_writer, args=(synthetic_catalog, attempted, acquired)
    )
    writer.start()
    assert attempted.wait(10)
    assert not acquired.wait(0.2)
    release.set()
    activation.join(10)
    writer.join(10)
    assert activation.exitcode == writer.exitcode == 0
    assert acquired.is_set()
    assert (tmp_path / "active").resolve() == synthetic_catalog


def test_activation_discards_derivative_sidecars(backup, tmp_path, repo_uuid):
    fresh = tmp_path / "fresh"
    service = RecoveryService()
    service.restore_backup(backup, fresh, repo_uuid)
    for name in ("operational.sqlite3", "search.sqlite3"):
        for suffix in ("", "-wal", "-shm"):
            (fresh / (name + suffix)).write_bytes(b"obsolete derivative data")
    receipt = service.activate_catalog(fresh, tmp_path / "active")
    assert receipt.search_derivative_state == "initialized_empty"
    assert receipt.clean_operational
