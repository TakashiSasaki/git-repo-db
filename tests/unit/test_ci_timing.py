"""Timing evidence must survive refusal/interruption and preserve overlap/missingness."""

import json
import sys
from argparse import Namespace

import pytest

from scripts import ci_profile, ci_query


def arguments(tmp_path, command):
    return Namespace(
        name="timing",
        command=command,
        output=tmp_path,
        junit=None,
        mode="sequential",
        workers=1,
    )


def test_child_observes_checkpoint_and_parent_association(tmp_path, monkeypatch):
    monkeypatch.setenv("CI_TASK_ID", "pr-timing")
    monkeypatch.setenv("CI_SESSION_ID", "author-window-1")
    monkeypatch.setenv("CI_PHASE_KIND", "preflight")
    script = """
import json, os, pathlib
profile = next(pathlib.Path(OUTPUT).glob('invocations/*.json'))
record = json.loads(profile.read_text())
assert record['exit_code'] is None
assert record['timing']['status'] == 'running'
assert record['timing']['phases'][-1]['name'] == 'command'
assert 'completed_at' not in record['timing']['phases'][-1]
assert os.environ['CI_PARENT_INVOCATION_ID'] == record['invocation_id']
raise SystemExit(9)
""".replace("OUTPUT", repr(str(tmp_path)))
    assert ci_profile.run(arguments(tmp_path, [sys.executable, "-c", script])) == 9
    saved = json.loads((tmp_path / "timing.json").read_text())
    timing = saved["timing"]
    assert timing["status"] == "completed"
    assert timing["task_id"] == "pr-timing"
    assert timing["session_id"] == "author-window-1"
    assert timing["kind"] == "preflight"
    assert (
        timing["elapsed_seconds"]
        >= next(
            p["elapsed_seconds"] for p in timing["phases"] if p["name"] == "command"
        )
        > 0
    )
    report = ci_query.timing_report([tmp_path, tmp_path / "timing.json"])
    assert report["invocation_count"] == 1
    assert report["cumulative_test_seconds_sum"] is None


@pytest.mark.parametrize(
    "exception", [FileNotFoundError("no executable"), KeyboardInterrupt()]
)
def test_runner_failure_preserves_observed_timing(tmp_path, monkeypatch, exception):
    monkeypatch.setattr(ci_profile, "runtime", lambda: {})

    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr(ci_profile.subprocess, "run", fail)
    with pytest.raises(type(exception)):
        ci_profile.run(arguments(tmp_path, ["nonexistent-test-command"]))
    saved = json.loads(next((tmp_path / "invocations").glob("*.json")).read_text())
    assert saved["exit_code"] != 0
    assert saved["verified"] is False
    assert saved["timing"]["status"] == (
        "interrupted" if isinstance(exception, KeyboardInterrupt) else "error"
    )
    assert saved["timing"]["elapsed_seconds"] > 0
    command = saved["timing"]["phases"][-1]
    assert command["name"] == "command"
    assert command["exception_type"] == type(exception).__name__
    assert command["elapsed_seconds"] > 0


def test_post_child_measurement_error_cannot_publish_a_successful_profile(
    tmp_path, monkeypatch
):
    from scripts import ci_execute

    journal = tmp_path / "broken.jsonl"
    script = f"from pathlib import Path; Path({str(journal)!r}).write_text('not-json\\n{{}}\\n')"
    args = arguments(tmp_path, [sys.executable, "-c", script])
    args.journal = journal
    with pytest.raises(ValueError):
        ci_profile.run(args)
    saved = json.loads((tmp_path / "timing.json").read_text())
    assert saved["child_exit_code"] == 0
    assert saved["exit_code"] != 0
    assert saved["verified"] is False
    assert saved["timing"]["status"] == "error"
    with pytest.raises(ValueError):
        ci_execute.successful_profile(tmp_path / "timing.json", {}, {})


def test_cpu_wait_is_separate_from_command_elapsed(tmp_path, monkeypatch):
    from contextlib import contextmanager

    class Clock:
        value = 0

    clock = Clock()
    monkeypatch.setattr(ci_profile.time, "perf_counter", lambda: clock.value)
    monkeypatch.setattr(
        ci_profile,
        "runtime",
        lambda: {
            "commit_sha": "a",
            "tree_sha": "b",
            "dirty": False,
            "python": "test",
            "sqlite": "test",
        },
    )

    @contextmanager
    def reservation(*args, **kwargs):
        clock.value += 5
        yield 2

    def command(*args, **kwargs):
        clock.value += 3
        return Namespace(returncode=0)

    monkeypatch.setattr(
        ci_profile.resource_scheduler, "scoped_host_cpu_reservation", reservation
    )
    monkeypatch.setattr(ci_profile.subprocess, "run", command)
    args = arguments(tmp_path, ["synthetic-pytest"])
    args.workers = 2
    assert ci_profile.run(args) == 0
    saved = json.loads((tmp_path / "timing.json").read_text())
    phases = {p["name"]: p["elapsed_seconds"] for p in saved["timing"]["phases"]}
    assert phases["resource_wait"] == 5
    assert phases["command"] == 3
    assert saved["wall_seconds"] == 8


def write_profile(path, identity, start=None, end=None, seconds=None, **extra):
    data = dict(profile_version=1, invocation_id=identity, exit_code=0, **extra)
    if start is not None:
        data["started_at"] = f"2026-11-01T00:00:{start:02d}+00:00"
    if end is not None:
        data["completed_at"] = f"2026-11-01T00:00:{end:02d}+00:00"
    if seconds is not None:
        data["wall_seconds"] = seconds
    path.write_text(json.dumps(data))
    return data


def test_overlapping_and_repeated_invocations_are_not_sequential_work(tmp_path):
    write_profile(tmp_path / "one.json", "one", 0, 10, 10)
    write_profile(tmp_path / "two.json", "two", 5, 15, 10)
    write_profile(tmp_path / "repeat.json", "repeat", 20, 25, 5)
    write_profile(
        tmp_path / "open.json", "open", timing={"status": "running", "phases": []}
    )
    report = ci_query.timing_report([tmp_path])
    assert report["recorded_wall_seconds_sum"] == 25
    assert report["interval_union_seconds"] == 20
    assert report["observed_span_seconds"] == 25
    assert report["missing_interval_count"] == 1
    assert report["command_seconds_sum"] is None
    assert report["active_work_share"] is None


def test_new_command_interval_excludes_resource_wait_and_finalization(tmp_path):
    write_profile(
        tmp_path / "result.json",
        "new",
        0,
        30,
        30,
        timing={
            "status": "completed",
            "phases": [
                {
                    "name": "command",
                    "started_at": "2026-11-01T00:00:10+00:00",
                    "completed_at": "2026-11-01T00:00:20+00:00",
                    "elapsed_seconds": 10,
                }
            ],
        },
    )
    report = ci_query.timing_report([tmp_path])
    assert report["interval_union_seconds"] == 10
    assert report["command_seconds_sum"] == 10
    assert report["recorded_wall_seconds_sum"] == 30


def test_conflicting_alias_cannot_silently_replace_an_invocation(tmp_path):
    write_profile(tmp_path / "one.json", "same", 0, 10, 10)
    write_profile(tmp_path / "two.json", "same", 0, 20, 20)
    with pytest.raises(ValueError, match="Conflicting"):
        ci_query.timing_report([tmp_path])


@pytest.mark.parametrize("mutation", ["reversed", "naive", "negative", "nan"])
def test_invalid_timing_is_refused(tmp_path, mutation):
    path = tmp_path / "bad.json"
    data = write_profile(path, "bad", 0, 10, 10)
    if mutation == "reversed":
        data["started_at"], data["completed_at"] = (
            data["completed_at"],
            data["started_at"],
        )
    elif mutation == "naive":
        data["started_at"] = "2026-11-01T00:00:00"
    else:
        data["wall_seconds"] = -1 if mutation == "negative" else float("nan")
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        ci_query.timing_report([tmp_path])
