import json
import os
import signal
import sqlite3
import subprocess
import sys
import time

from repo_catalog.adapters.filesystem.locks import FileLock
from tests.e2e.test_cache import expire
from tests.support.cli import run
from tests.support.process import wait_unlocked


def test_capacity_scan_during_temporary_file_removal(tmp_path, monkeypatch):
    from repo_catalog.adapters.filesystem.capacity import allocated_bytes

    keep = tmp_path / "keep.pack"
    gone = tmp_path / "temporary.pack"
    keep.write_bytes(b"k" * 8192)
    gone.write_bytes(b"g" * 8192)
    walk = os.walk

    def changing_walk(*args, **kwargs):
        for root, dirs, names in walk(*args, **kwargs):
            gone.unlink()
            yield root, dirs, names

    monkeypatch.setattr(os, "walk", changing_walk)
    assert allocated_bytes(tmp_path) == keep.stat().st_blocks * 512


def test_git_transfer_timeout_terminates_child_group(tmp_path):
    import pytest

    from repo_catalog.adapters.git.runner import GitRunner
    from repo_catalog.domain.models import CancellationToken, CatalogError

    with FileLock(tmp_path / "generation.lock", inheritable=True) as lock:
        with pytest.raises(CatalogError) as raised:
            GitRunner(CancellationToken(), lock).transfer(
                ["-c", "alias.hold=!sleep 30", "hold"], timeout=0.1
            )
        assert raised.value.code == "GIT_TIMEOUT" and raised.value.retryable
    wait_unlocked(tmp_path / "generation.lock")


def test_locks_fencing(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    expire(state)
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        cache = db.execute(
            "SELECT a.active_cache_entry_id FROM active_cache_entries a JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE l.repository_uuidv4=?",
            (repos["alpha"],),
        ).fetchone()[0]
    with FileLock(state / f"locks/cache-{cache}.lock"):
        result = run(state, "cache", "gc", "--apply")
        entry = next(
            r for r in result["data"]["entries"] if r["active_cache_entry_id"] == cache
        )
        assert (
            entry["action"] == "retained" and "generation_in_use" in entry["blocked_by"]
        )


def test_old_obligations(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    expire(state)
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        db.execute(
            "UPDATE preservation_obligations SET text_done=0 WHERE git_acquisition_id=(SELECT s.git_acquisition_id FROM snapshots s JOIN repositories r ON r.current_snapshot_id=s.snapshot_id WHERE r.repository_uuidv4=?)",
            (repos["alpha"],),
        )
    result = run(state, "cache", "gc", "--apply")
    assert any(
        any(r.startswith("pending_obligations:") for r in e["blocked_by"])
        for e in result["data"]["entries"]
    )
    assert list((state / "cache").rglob("HEAD"))


def test_capacity_wait(catalog):
    from repo_catalog.config import load, serialize

    state, fixture, repos = catalog
    cfg = load(state)
    cfg["cache"]["max_bytes"] = 100
    (state / "catalog.toml").write_text(serialize(cfg))
    value = run(state, "sync", "git", "--repo", repos["alpha"], expected=3)
    assert value["data"]["results"][0]["error"] == "CAPACITY_WAIT"
    assert not list((state / "cache").rglob("HEAD"))


def test_failed_fetch_cleanup(catalog):
    state, fixture, repos = catalog
    run(
        state,
        "endpoints",
        "add",
        "--repo",
        repos["alpha"],
        "--url",
        "file:///does-not-exist",
        "--preferred",
    )
    run(state, "sync", "git", "--repo", repos["alpha"], expected=3)
    expire(state)
    value = run(state, "cache", "gc", "--apply")
    assert all(r["action"] == "evicted" for r in value["data"]["entries"])
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        assert (
            db.execute(
                "SELECT count(*) FROM preservation_obligations WHERE roots_fixed=1"
            ).fetchone()[0]
            == 0
        )


def test_orphan_git_holds_lock(catalog, tmp_path):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    expire(state)
    with sqlite3.connect(state / "catalog.sqlite3") as db:
        cache = db.execute(
            "SELECT a.active_cache_entry_id FROM active_cache_entries a JOIN cache_locators l ON l.cache_locator_id=a.cache_locator_id WHERE l.repository_uuidv4=?",
            (repos["alpha"],),
        ).fetchone()[0]
    lockfile = state / f"locks/cache-{cache}.lock"
    marker = tmp_path / "child.json"
    code = """
import json,subprocess,time,sys
from pathlib import Path
from repo_catalog.adapters.filesystem.locks import FileLock
with FileLock(sys.argv[1],inheritable=True) as lock:
    child=subprocess.Popen(['git','-c','alias.hold=!sleep 60','hold'],pass_fds=(lock.fd,),start_new_session=True)
    Path(sys.argv[2]).write_text(json.dumps({'pid':child.pid}))
    while True: time.sleep(1)
"""
    owner = subprocess.Popen([sys.executable, "-c", code, str(lockfile), str(marker)])
    child = None
    try:
        end = time.monotonic() + 10
        while not marker.exists():
            if time.monotonic() > end:
                raise AssertionError("Child handshake failed")
            time.sleep(0.01)
        child = json.loads(marker.read_text())["pid"]
        owner.kill()
        owner.wait()
        value = run(state, "cache", "gc", "--apply")
        entry = next(
            e for e in value["data"]["entries"] if e["active_cache_entry_id"] == cache
        )
        assert "generation_in_use" in entry["blocked_by"]
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait()
        if child:
            try:
                os.killpg(child, signal.SIGTERM)
            except ProcessLookupError:
                pass
        wait_unlocked(lockfile)
