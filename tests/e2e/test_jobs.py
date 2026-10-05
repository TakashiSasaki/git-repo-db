import json
import signal

from tests.e2e.test_recovery import interrupted_job
from tests.support.cli import run
from tests.support.process import start_hooked


def test_cancel_resume(catalog, tmp_path):
    state, fixture, repos = catalog
    p, hooks = start_hooked(
        state, "before_publish", tmp_path, "sync", "git", "--repo", repos["alpha"]
    )
    job = interrupted_job(state)
    assert (
        run(state, "jobs", "cancel", job, expected=4)["error"]["code"] == "JOB_RUNNING"
    )
    p.send_signal(signal.SIGINT)
    (hooks / "before_publish.release").touch()
    out, err = p.communicate(timeout=10)
    assert p.returncode == 130 and json.loads(out)["error"]["details"]["job_id"] == job
    run(state, "jobs", "resume", job)


def test_cancel_query_closes_read_transaction(catalog, tmp_path):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    process, hooks = start_hooked(
        state, "query_started", tmp_path, "search", "code", "--literal", "認証"
    )
    process.send_signal(signal.SIGINT)
    (hooks / "query_started.release").touch()
    out, err = process.communicate(timeout=10)
    assert process.returncode == 130 and json.loads(out)["error"]["code"] == "CANCELLED"
    run(state, "db", "check", "--full")
