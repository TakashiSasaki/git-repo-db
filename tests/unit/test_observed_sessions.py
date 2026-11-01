"""Explicit observations and measurement-only evidence; no product operations."""

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from scripts import ci_execute, ci_query, ci_timing


def clock(monkeypatch):
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = [0]
    monkeypatch.setattr(
        ci_timing, "utc_now", lambda: (origin + timedelta(seconds=state[0])).isoformat()
    )
    return state


def transition(out, action, **kwargs):
    return ci_timing.session_transition(out, "author", action, **kwargs)


def test_transitions_and_observed_pauses_are_not_effort(tmp_path, monkeypatch):
    now = clock(monkeypatch)
    transition(tmp_path, "start", task_id="task")
    now[0] = 10
    transition(tmp_path, "pause", reason="approval_wait")
    now[0] = 15
    transition(tmp_path, "resume")
    now[0] = 25
    path, record = transition(tmp_path, "end")
    assert record["measurement_only"] and not record["verified"]
    report = ci_query.timing_report([path])["sessions"]
    assert report["active_seconds_sum"] == 20
    assert report["pause_seconds_sum"] == 5
    assert report["records"][0]["pause_seconds_by_reason"] == {"approval_wait": 5}
    assert report["incomplete_count"] == 0
    assert report["recorded_command_fraction_of_observed_active_sessions"] is None
    with pytest.raises(ValueError):
        ci_execute.successful_profile(path, {}, {})


@pytest.mark.parametrize(
    "action,kwargs",
    [
        ("start", {"task_id": "task"}),
        ("resume", {}),
        ("pause", {}),
        ("pause", {"reason": "secret free text"}),
    ],
)
def test_invalid_transitions_preserve_record(tmp_path, action, kwargs):
    path, _ = transition(tmp_path, "start", task_id="task")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        transition(tmp_path, action, **kwargs)
    assert path.read_bytes() == before
    transition(tmp_path, "end")
    with pytest.raises(ValueError):
        transition(tmp_path, "end")


def test_double_pause_and_concurrent_resume_have_one_winner(tmp_path):
    path, _ = transition(tmp_path, "start", task_id="task")
    transition(tmp_path, "pause", reason="environment_wait")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        transition(tmp_path, "pause", reason="deliberate_pause")
    assert path.read_bytes() == before

    def resume(_):
        try:
            transition(tmp_path, "resume")
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(resume, range(2))) == [False, True]
    assert len(json.loads(path.read_text())["timing"]["phases"]) == 3


def test_open_and_interrupted_sessions_do_not_infer_a_current_end(
    tmp_path, monkeypatch
):
    now = clock(monkeypatch)
    transition(tmp_path, "start", task_id="task")
    now[0] = 100
    report = ci_query.timing_report([tmp_path])["sessions"]
    assert report["active_seconds_sum"] is None
    assert report["records"][0]["open_phase_count"] == 1
    assert report["incomplete_count"] == 1
    transition(tmp_path, "end", interrupted=True)
    report = ci_query.timing_report([tmp_path])["sessions"]
    assert report["active_seconds_sum"] == 100
    assert report["incomplete_count"] == 1
    assert report["recorded_command_fraction_of_observed_active_sessions"] is None


def test_clock_reversal_is_missingness_not_negative_activity(tmp_path, monkeypatch):
    now = clock(monkeypatch)
    now[0] = 10
    transition(tmp_path, "start", task_id="task")
    now[0] = 5
    transition(tmp_path, "end")
    report = ci_query.timing_report([tmp_path])["sessions"]
    assert report["active_seconds_sum"] is None
    assert report["records"][0]["clock_error_count"] == 1
    assert report["incomplete_count"] == 1


def test_atomic_transition_failure_leaves_previous_checkpoint(tmp_path, monkeypatch):
    path, _ = transition(tmp_path, "start", task_id="task")
    before = path.read_bytes()

    def fail(*args):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(ci_timing.os, "replace", fail)
    with pytest.raises(OSError):
        transition(tmp_path, "pause", reason="deliberate_pause")
    assert path.read_bytes() == before


def command(out, name, start, end, parent=None, **overrides):
    def stamp(s):
        return f"2026-01-01T00:00:{s:02d}+00:00"

    record = dict(
        profile_version=1,
        invocation_id=name,
        exit_code=0,
        measurement_only=True,
        timing=dict(
            status="completed",
            task_id="task",
            session_id="author",
            parent_invocation_id=parent,
            phases=[
                dict(
                    name="command",
                    started_at=stamp(start),
                    completed_at=stamp(end),
                    elapsed_seconds=end - start,
                )
            ],
        ),
    )
    record.update(overrides)
    path = out / "invocations" / f"{name}.json"
    path.write_text(json.dumps(record))
    return record


def test_nested_parallel_commands_are_clipped_to_their_session(tmp_path, monkeypatch):
    now = clock(monkeypatch)
    transition(tmp_path, "start", task_id="task")
    now[0] = 10
    transition(tmp_path, "pause", reason="environment_wait")
    now[0] = 20
    transition(tmp_path, "resume")
    now[0] = 30
    transition(tmp_path, "end")
    command(tmp_path, "parent", 5, 25)
    command(tmp_path, "child", 6, 9, parent="parent")
    command(tmp_path, "parallel", 0, 8)
    report = ci_query.timing_report([tmp_path])
    assert report["command_seconds_sum"] == 31
    assert report["root_command_seconds_sum"] == 28
    assert report["interval_union_seconds"] == 25
    sessions = report["sessions"]
    assert sessions["active_interval_union_seconds"] == 20
    assert sessions["recorded_command_in_active_union_seconds"] == 15
    assert sessions["recorded_command_fraction_of_observed_active_sessions"] == 0.75
    assert report["active_work_share"] is None


def test_external_bootstrap_wrapper_is_stdlib_only_and_non_acceptance(tmp_path):
    script = "import sys; assert not any(k.startswith('repo_catalog') for k in sys.modules); raise SystemExit(7)"
    path, result = ci_timing.run_external(
        tmp_path, "setup", [sys.executable, "-I", "-c", script]
    )
    assert result["exit_code"] == 7
    assert result["timing"]["status"] == "completed"
    assert result["measurement_only"] and not result["verified"]
    assert "runtime" not in result
    with pytest.raises(ValueError):
        ci_execute.successful_profile(path, {}, {})


@pytest.mark.parametrize(
    "error", [KeyboardInterrupt(), FileNotFoundError("no executable")]
)
def test_external_exception_retains_failed_checkpoint(tmp_path, monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(ci_timing.subprocess, "run", fail)
    with pytest.raises(type(error)):
        ci_timing.run_external(tmp_path, "external", ["command"])
    record = json.loads(next((tmp_path / "invocations").glob("*.json")).read_text())
    assert record["exit_code"] != 0
    assert record["timing"]["exception_type"] == type(error).__name__
    assert record["timing"]["phases"][-1]["elapsed_seconds"] >= 0


def test_cli_supports_separate_process_transitions_without_product_runtime(tmp_path):
    script = str(ci_timing.__file__)

    def run(action, *args):
        return subprocess.run(
            [
                sys.executable,
                "-I",
                script,
                action,
                "--output",
                str(tmp_path),
                "--session-id",
                "standalone",
                *args,
            ],
            capture_output=True,
            text=True,
        )

    assert run("start", "--task-id", "task").returncode == 0
    assert run("pause", "--reason", "approval_wait").returncode == 0
    assert run("resume").returncode == 0
    assert run("end").returncode == 0
    assert run("end").returncode != 0


def test_parallel_sessions_report_sum_and_union_separately(tmp_path, monkeypatch):
    now = clock(monkeypatch)
    transition(tmp_path, "start", task_id="task")
    now[0] = 5
    ci_timing.session_transition(
        tmp_path, "reviewer", "start", task_id="task", parent_id="session-author"
    )
    now[0] = 15
    ci_timing.session_transition(tmp_path, "reviewer", "end")
    now[0] = 20
    transition(tmp_path, "end")
    result = ci_query.timing_report([tmp_path])["sessions"]
    assert result["active_seconds_sum"] == 30
    assert result["active_interval_union_seconds"] == 20
    assert result["closed_session_elapsed_seconds_sum"] == 30
    assert result["session_interval_union_seconds"] == 20


def test_open_command_retains_missingness_in_a_closed_session(tmp_path, monkeypatch):
    now = clock(monkeypatch)
    transition(tmp_path, "start", task_id="task")
    now[0] = 10
    transition(tmp_path, "end")
    record = command(tmp_path, "open-command", 0, 5)
    record["timing"]["status"] = "running"
    del record["timing"]["phases"][0]["completed_at"]
    del record["timing"]["phases"][0]["elapsed_seconds"]
    (tmp_path / "invocations/open-command.json").write_text(json.dumps(record))
    report = ci_query.timing_report([tmp_path])
    assert report["missing_interval_count"] == 1
    assert report["sessions"]["records"][0]["missing_command_interval_count"] == 1
    assert (
        report["sessions"]["recorded_command_fraction_of_observed_active_sessions"]
        is None
    )


def test_monotonic_command_survives_a_reversed_wall_clock(tmp_path):
    (tmp_path / "invocations").mkdir()
    record = command(tmp_path, "reversed", 9, 5)
    record["timing"]["phases"][0]["elapsed_seconds"] = 4
    (tmp_path / "invocations/reversed.json").write_text(json.dumps(record))
    report = ci_query.timing_report([tmp_path])
    assert report["command_seconds_sum"] == 4
    assert report["interval_union_seconds"] is None
    assert report["invocations"][0]["clock_error"] == "wall_clock_reversed"
