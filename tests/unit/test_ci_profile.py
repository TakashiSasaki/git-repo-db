import json
import sys
from argparse import Namespace

import jsonschema
import pytest

from scripts import ci_profile
from tests.support.cli import response_validator


def test_cached_cli_validator_still_rejects_invalid_envelope():
    with pytest.raises(jsonschema.ValidationError):
        response_validator().validate({"status": "ok"})


def test_junit_aggregation_preserves_failures(tmp_path):
    xml = tmp_path / "tests.xml"
    xml.write_text(
        '<testsuites><testsuite><testcase classname="tests.unit.synthetic" name="a" time="1.25"/><testcase classname="tests.unit.synthetic" name="b" time="2"><failure/></testcase><testcase classname="tests.unit.other" name="c" time="0.1"><skipped/></testcase></testsuite></testsuites>'
    )
    result = ci_profile.junit(xml)
    assert result["count"] == 3
    assert result["files"][0] == {
        "file": "tests/unit/synthetic.py",
        "seconds": 3.25,
        "tests": 2,
        "failures": 1,
        "skipped": 0,
    }


@pytest.mark.parametrize("exit_code", [0, 7])
def test_command_status_metadata_and_stale_junit(tmp_path, monkeypatch, exit_code):
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    xml = tmp_path / "stale.xml"
    xml.write_text(
        '<testsuites><testsuite><testcase name="stale"/></testsuite></testsuites>'
    )
    args = Namespace(
        command=[sys.executable, "-c", f"raise SystemExit({exit_code})"],
        output=tmp_path,
        name="command",
        junit=xml,
        mode="sequential",
        workers=1,
    )
    assert ci_profile.run(args) == (exit_code or 2)
    saved = json.loads((tmp_path / "command.json").read_text())
    assert saved["measurement_error"]
    assert saved["wall_seconds"] > 0
    assert saved["runtime"]["cpu_count"] > 0
    assert "junit" not in saved


def test_coverage_rejects_omitted_duplicate_skipped_and_failed_tests(tmp_path):
    expected = tmp_path / "required.txt"
    expected.write_text(
        "tests/unit/synthetic.py::a\ntests/unit/synthetic.py::b\n2 tests collected\n"
    )
    profile = tmp_path / "result.json"
    record = {
        "exit_code": 0,
        "junit": {
            "tests": [
                {"nodeid": f"tests/unit/synthetic.py::{name}", "status": "passed"}
                for name in ("a", "b")
            ]
        },
    }
    profile.write_text(json.dumps(record))
    assert ci_profile.coverage(expected, [profile])["executed_once"] == 2
    for bad in (
        record["junit"]["tests"][:1],
        record["junit"]["tests"] * 2,
        [{"nodeid": "tests/unit/synthetic.py::a", "status": "skipped"}],
    ):
        profile.write_text(json.dumps({"exit_code": 0, "junit": {"tests": bad}}))
        with pytest.raises(ValueError):
            ci_profile.coverage(expected, [profile])


def test_compare_reports_median_range_not_single_sample(tmp_path):
    paths = []
    for i, seconds in enumerate((3.0, 1.0, 2.0)):
        path = tmp_path / f"{i}.json"
        path.write_text(
            json.dumps(
                {"mode": "xdist", "workers": 2, "wall_seconds": seconds, "exit_code": 0}
            )
        )
        paths.append(path)
    assert ci_profile.compare(paths)[0] == {
        "mode": "xdist",
        "series": "pytest",
        "workers": 2,
        "samples": 3,
        "median": 2.0,
        "minimum": 1.0,
        "maximum": 3.0,
        "failures": 0,
    }


def test_ci_profile_recovers_from_journal_when_junit_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary.md"))
    journal = tmp_path / "events.jsonl"
    lines = [
        json.dumps(
            {
                "event": "phase",
                "nodeid": "tests/unit/a.py::test_one",
                "phase": "setup",
                "outcome": "passed",
                "duration": 0.001,
            }
        ),
        json.dumps(
            {
                "event": "phase",
                "nodeid": "tests/unit/a.py::test_one",
                "phase": "call",
                "outcome": "passed",
                "duration": 0.020,
            }
        ),
        json.dumps(
            {
                "event": "phase",
                "nodeid": "tests/unit/a.py::test_one",
                "phase": "teardown",
                "outcome": "passed",
                "duration": 0.002,
            }
        ),
    ]
    script = f"from pathlib import Path; Path({repr(str(journal))}).write_text({repr(chr(10).join(lines) + chr(10))})"
    missing_xml = tmp_path / "does_not_exist.xml"
    args = Namespace(
        command=[sys.executable, "-c", script],
        output=tmp_path,
        name="profiled_lane",
        junit=missing_xml,
        journal=journal,
        mode="sequential",
        workers=1,
    )
    assert ci_profile.run(args) == 0
    saved = json.loads((tmp_path / "profiled_lane.json").read_text())
    assert saved["junit"]["count"] == 1
    assert saved["measurement_recovered_from_journal"] is True
    assert "tests/unit/a.py::test_one" in saved["phases"]
    assert saved["phases"]["tests/unit/a.py::test_one"]["call"] == 0.020


def test_ci_profile_generates_unique_invocation_identity_and_safe_layout(tmp_path):
    args = Namespace(
        command=[sys.executable, "-c", "import time; time.sleep(0.01)"],
        output=tmp_path,
        name="isolated_run",
        junit=None,
        journal=None,
        mode="sequential",
        workers=1,
    )
    assert ci_profile.run(args) == 0
    saved = json.loads((tmp_path / "isolated_run.json").read_text())
    assert "invocation_id" in saved
    assert saved["invocation_id"].startswith("isolated_run-")
    assert "started_at" in saved
    assert "completed_at" in saved
    assert "tree_sha" in saved["runtime"]
    assert "dirty" in saved["runtime"]
    assert "wall_seconds" in saved
    assert saved["wall_seconds"] > 0

    # Verify collision-safe copy was written to invocations directory
    inv_dir = tmp_path / "invocations"
    assert inv_dir.is_dir()
    inv_files = list(inv_dir.glob("isolated_run-*.json"))
    assert len(inv_files) == 1
    assert inv_files[0].name == f"isolated_run-{saved['invocation_id']}.json"


def test_ci_profile_focused_subcommand_ergonomics(tmp_path, monkeypatch):
    test_f = tmp_path / "test_ergonomics.py"
    test_f.write_text("def test_ok(): pass\n")
    args = Namespace(
        name="focused",
        output=tmp_path,
        workers=1,
        pytest_args=[str(test_f)],
    )
    assert ci_profile.profile_focused(args) == 0
    assert (tmp_path / "focused.json").is_file()
    assert (tmp_path / "focused.md").is_file()
    record = json.loads((tmp_path / "focused.json").read_text())
    assert record["name"] == "focused"
    assert record["exit_code"] == 0
    assert record["wall_seconds"] > 0
    assert "cumulative_test_seconds" in record


def test_ci_profile_timing_semantics_distinguish_wall_and_cumulative(tmp_path):
    journal = tmp_path / "events.jsonl"
    lines = [
        json.dumps({"event": "start", "nodeid": "t1"}),
        json.dumps(
            {
                "event": "phase",
                "nodeid": "t1",
                "phase": "setup",
                "outcome": "passed",
                "duration": 0.05,
            }
        ),
        json.dumps(
            {
                "event": "phase",
                "nodeid": "t1",
                "phase": "call",
                "outcome": "passed",
                "duration": 0.10,
            }
        ),
        json.dumps(
            {
                "event": "phase",
                "nodeid": "t1",
                "phase": "teardown",
                "outcome": "passed",
                "duration": 0.05,
            }
        ),
        json.dumps({"event": "start", "nodeid": "t2"}),
        json.dumps(
            {
                "event": "phase",
                "nodeid": "t2",
                "phase": "setup",
                "outcome": "passed",
                "duration": 0.05,
            }
        ),
        json.dumps(
            {
                "event": "phase",
                "nodeid": "t2",
                "phase": "call",
                "outcome": "passed",
                "duration": 0.10,
            }
        ),
        json.dumps(
            {
                "event": "phase",
                "nodeid": "t2",
                "phase": "teardown",
                "outcome": "passed",
                "duration": 0.05,
            }
        ),
    ]
    script = f"from pathlib import Path; Path({repr(str(journal))}).write_text({repr(chr(10).join(lines) + chr(10))})"
    args = Namespace(
        command=[sys.executable, "-c", script],
        output=tmp_path,
        name="timing_lane",
        junit=None,
        journal=journal,
        mode="sequential",
        workers=1,
    )
    assert ci_profile.run(args) == 0
    record = json.loads((tmp_path / "timing_lane.json").read_text())
    # Cumulative test duration is sum of phases (0.20 + 0.20 = 0.40)
    assert record["cumulative_test_seconds"] == 0.40
    # Wall seconds is command execution time
    assert record["wall_seconds"] > 0
    md = (tmp_path / "timing_lane.md").read_text()
    assert "Command wall time:" in md
    assert "Cumulative test duration: 0.40s" in md


def test_signal_terminated_command_records_interrupted(tmp_path, monkeypatch):
    import signal
    import subprocess

    class FakeCompleted:
        returncode = -signal.SIGTERM

    monkeypatch.setattr(
        ci_profile,
        "runtime",
        lambda: {
            "commit_sha": "0" * 40,
            "tree_sha": "0" * 40,
            "dirty": False,
            "tracked_changes": False,
            "python": "3.12.3",
            "sqlite": "3.45.1",
            "git": "git version 2.43.0",
        },
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeCompleted())
    args = Namespace(
        command=["fake"],
        output=tmp_path,
        name="sigterm_test",
        junit=None,
        journal=None,
        mode="sequential",
        workers=1,
    )
    rc = ci_profile.run(args)
    assert rc == -signal.SIGTERM
    record = json.loads((tmp_path / "sigterm_test.json").read_text())
    assert record["interrupted"] is True
    assert record["exit_code"] == -signal.SIGTERM
    md = (tmp_path / "sigterm_test.md").read_text()
    assert "Execution was interrupted; results are partial" in md
