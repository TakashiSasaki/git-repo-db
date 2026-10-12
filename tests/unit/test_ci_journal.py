"""Adversarial and functional unit tests for append-only JSONL test event journaling."""

import json
import subprocess
import sys

from scripts import ci_journal


def test_journal_writer_and_parser_roundtrip(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ci_journal.JournalWriter(path)
    writer.record_phase("tests/unit/a.py::test_one", "setup", "passed", 0.001)
    writer.record_phase("tests/unit/a.py::test_one", "call", "passed", 0.050)
    writer.record_phase("tests/unit/a.py::test_one", "teardown", "passed", 0.002)
    writer.close()

    events = ci_journal.parse_journal(path)
    assert len(events) == 3
    assert events[0]["phase"] == "setup"
    assert events[1]["phase"] == "call"
    assert events[2]["phase"] == "teardown"
    assert events[1]["duration"] == 0.050

    summary = ci_journal.aggregate_journal(events)
    assert summary["count"] == 1
    assert summary["completed"] == 1
    assert summary["partial"] == 0
    assert not summary["interrupted"]
    test_one = summary["tests"][0]
    assert test_one["nodeid"] == "tests/unit/a.py::test_one"
    assert test_one["status"] == "passed"
    assert test_one["completed"] is True
    assert test_one["phases"] == {"setup": 0.001, "call": 0.05, "teardown": 0.002}
    assert test_one["duration"] == 0.053


def test_parser_tolerates_corrupted_or_truncated_trailing_lines(tmp_path):
    path = tmp_path / "crashed_journal.jsonl"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "event": "phase",
                    "nodeid": "t1",
                    "phase": "setup",
                    "outcome": "passed",
                    "duration": 0.01,
                }
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "event": "phase",
                    "nodeid": "t1",
                    "phase": "call",
                    "outcome": "passed",
                    "duration": 0.02,
                }
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "event": "phase",
                    "nodeid": "t1",
                    "phase": "teardown",
                    "outcome": "passed",
                    "duration": 0.005,
                }
            )
            + "\n"
        )
        # Incomplete / truncated JSON write from abrupt crash / power loss
        handle.write('{"event": "phase", "nodeid": "t2", "phase": "call", "dur\n')

    events = ci_journal.parse_journal(path)
    assert len(events) == 3
    summary = ci_journal.aggregate_journal(events)
    assert summary["count"] == 1
    assert summary["completed"] == 1


def test_interrupted_run_recovers_partial_evidence(tmp_path):
    path = tmp_path / "interrupted.jsonl"
    writer = ci_journal.JournalWriter(path)
    # Test 1 completed
    writer.record_phase("tests/unit/a.py::test_1", "setup", "passed", 0.001)
    writer.record_phase("tests/unit/a.py::test_1", "call", "passed", 0.010)
    writer.record_phase("tests/unit/a.py::test_1", "teardown", "passed", 0.001)

    # Test 2 completed
    writer.record_phase("tests/unit/a.py::test_2", "setup", "passed", 0.002)
    writer.record_phase("tests/unit/a.py::test_2", "call", "failed", 0.020)
    writer.record_phase("tests/unit/a.py::test_2", "teardown", "passed", 0.001)

    # Test 3 was interrupted during call phase (setup completed, teardown never ran)
    writer.record_phase("tests/unit/a.py::test_3", "setup", "passed", 0.003)
    writer.close()

    summary = ci_journal.aggregate_journal(path)
    assert summary["count"] == 3
    assert summary["completed"] == 2
    assert summary["partial"] == 1
    assert summary["interrupted"] is True

    test_3 = next(
        t for t in summary["tests"] if t["nodeid"] == "tests/unit/a.py::test_3"
    )
    assert test_3["completed"] is False
    assert test_3["phases"]["setup"] == 0.003
    assert test_3["phases"]["call"] == 0.0
    assert test_3["phases"]["teardown"] == 0.0

    junit_view = ci_journal.journal_to_junit_summary(summary)
    assert junit_view["count"] == 3
    assert junit_view["interrupted"] is True
    assert len(junit_view["files"]) == 1
    assert junit_view["files"][0]["failures"] == 1


def test_real_pytest_execution_generates_per_phase_journal(tmp_path):
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(
        "import time\n"
        "def test_fast():\n"
        "    time.sleep(0.01)\n"
        "    assert True\n"
        "def test_failing():\n"
        "    assert False\n"
    )
    journal_file = tmp_path / "events.jsonl"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_file),
        "-q",
        f"--journal={journal_file}",
        "-p",
        "scripts.ci_journal",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 1  # 1 test failed

    assert journal_file.exists()
    events = ci_journal.parse_journal(journal_file)
    assert len(events) == 6  # 2 tests * 3 phases

    summary = ci_journal.aggregate_journal(events)
    assert summary["count"] == 2
    assert summary["completed"] == 2
    assert not summary["interrupted"]

    fast = next(t for t in summary["tests"] if "test_fast" in t["nodeid"])
    assert fast["status"] == "passed"
    assert fast["phases"]["call"] >= 0.008

    failing = next(t for t in summary["tests"] if "test_failing" in t["nodeid"])
    assert failing["status"] == "failed"


def test_adversarial_worker_abort_preserves_earlier_tests(tmp_path):
    test_file = tmp_path / "test_abort.py"
    test_file.write_text(
        "import os\n"
        "def test_first():\n"
        "    assert True\n"
        "def test_crashing():\n"
        "    os._exit(42)\n"
        "def test_never_reached():\n"
        "    assert True\n"
    )
    journal_file = tmp_path / "abort_events.jsonl"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_file),
        "-q",
        f"--journal={journal_file}",
        "-p",
        "scripts.ci_journal",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode != 0

    assert journal_file.exists()
    events = ci_journal.parse_journal(journal_file)
    summary = ci_journal.aggregate_journal(events)
    # test_first must be completely recorded
    first = next(t for t in summary["tests"] if "test_first" in t["nodeid"])
    assert first["completed"] is True
    assert first["status"] == "passed"

    # test_crashing must have setup recorded before the sudden os._exit
    crashing = next(t for t in summary["tests"] if "test_crashing" in t["nodeid"])
    assert crashing["completed"] is False
    assert crashing["phases"]["setup"] >= 0.0
    assert summary["interrupted"] is True


def test_real_pytest_xdist_parallel_journaling(tmp_path):
    test_file = tmp_path / "test_parallel.py"
    test_file.write_text(
        "import time\n"
        "def test_p1(): time.sleep(0.01)\n"
        "def test_p2(): time.sleep(0.01)\n"
        "def test_p3(): time.sleep(0.01)\n"
        "def test_p4(): time.sleep(0.01)\n"
    )
    journal_file = tmp_path / "parallel_events.jsonl"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_file),
        "-n",
        "2",
        "-q",
        f"--journal={journal_file}",
        "-p",
        "scripts.ci_journal",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0

    assert journal_file.exists()
    summary = ci_journal.aggregate_journal(journal_file)
    assert summary["count"] == 4
    assert summary["completed"] == 4
    assert not summary["interrupted"]
    for t in summary["tests"]:
        assert t["phases"]["call"] > 0
        assert t["completed"] is True
