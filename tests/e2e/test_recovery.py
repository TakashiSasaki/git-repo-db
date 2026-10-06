import sqlite3

from tests.e2e.test_cache import expire
from tests.support.cli import pages, run
from tests.support.process import start_hooked, wait_unlocked


def interrupted_job(state):
    with sqlite3.connect(state / "catalog.sqlite3") as c:
        return c.execute(
            "SELECT j.job_id FROM jobs j JOIN job_attempts a ON a.job_id=j.job_id AND a.attempt=j.current_attempt WHERE a.state='running' AND j.kind='sync' ORDER BY j.created_at DESC LIMIT 1"
        ).fetchone()[0]


def test_kill_before_publish(catalog, tmp_path):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    old = pages(state, "snapshots", "list", "--repo", repos["alpha"])[-1]["snapshot_id"]
    fixture.advance()
    p, hooks = start_hooked(
        state, "before_publish", tmp_path, "sync", "git", "--repo", repos["alpha"]
    )
    p.kill()
    p.communicate(timeout=10)
    assert (
        run(state, "repos", "show", "--repo", repos["alpha"])["data"]["items"][0][
            "current_snapshot_id"
        ]
        == old
    )
    run(state, "jobs", "resume", interrupted_job(state))
    assert pages(
        state, "search", "path", "--repo", repos["alpha"], "--path", "new-only.txt"
    )


def test_kill_mid_blob(catalog, tmp_path):
    state, fixture, repos = catalog
    p, hooks = start_hooked(
        state, "mid_blob", tmp_path, "sync", "git", "--repo", repos["alpha"]
    )
    p.kill()
    p.communicate(timeout=10)
    with sqlite3.connect(state / "catalog.sqlite3") as c:
        assert (
            c.execute("SELECT count(*) FROM snapshots WHERE published=1").fetchone()[0]
            == 0
        )
        cache = c.execute(
            "SELECT active_cache_entry_id FROM active_cache_entries"
        ).fetchone()[0]
    wait_unlocked(state / f"locks/cache-{cache}.lock")
    run(state, "jobs", "resume", interrupted_job(state))
    assert pages(state, "search", "code", "--repo", repos["alpha"], "--literal", "認証")


def test_kill_during_gc(catalog, tmp_path):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    expire(state)
    p, hooks = start_hooked(
        state, "after_gc_rename", tmp_path, "cache", "gc", "--apply"
    )
    p.kill()
    p.communicate(timeout=10)
    assert list((state / "quarantine").iterdir())
    run(state, "cache", "gc", "--apply")
    assert not list((state / "quarantine").iterdir())
    assert pages(state, "search", "code", "--literal", "認証")


def test_old_run_history_publish(catalog, tmp_path):
    state, fixture, repos = catalog
    p, hooks = start_hooked(
        state, "before_publish", tmp_path, "sync", "git", "--repo", repos["alpha"]
    )
    p.kill()
    p.communicate(timeout=10)
    oldjob = interrupted_job(state)
    fixture.advance()
    run(state, "sync", "git", "--repo", repos["alpha"])
    newer = run(state, "repos", "show", "--repo", repos["alpha"])["data"]["items"][0][
        "current_snapshot_id"
    ]
    expire(state)
    dry = run(state, "cache", "gc")
    assert any(
        any(reason.startswith("pending_obligations:") for reason in entry["blocked_by"])
        for entry in dry["data"]["entries"]
    )
    run(state, "jobs", "resume", oldjob)
    assert (
        run(state, "repos", "show", "--repo", repos["alpha"])["data"]["items"][0][
            "current_snapshot_id"
        ]
        == newer
    )
    assert pages(
        state,
        "search",
        "path",
        "--repo",
        repos["alpha"],
        "--path",
        "old-only.txt",
        "--scope",
        "recorded",
    )
    run(state, "cache", "gc", "--apply")
    assert not list((state / "cache").rglob("HEAD"))
