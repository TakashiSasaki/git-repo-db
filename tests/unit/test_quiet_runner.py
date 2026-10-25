import json
import sys
from argparse import Namespace

from scripts import ci_profile, ci_query


def test_build_failure_index_empty():
    junit_data = {
        "count": 2,
        "tests": [
            {
                "nodeid": "tests/unit/test_a.py::test_1",
                "status": "passed",
                "seconds": 0.01,
            },
            {
                "nodeid": "tests/unit/test_a.py::test_2",
                "status": "passed",
                "seconds": 0.02,
            },
        ],
    }
    index = ci_profile.build_failure_index(junit_data)
    assert index["version"] == 1
    assert index["failure_count"] == 0
    assert index["skipped_count"] == 0
    assert index["failures"] == []


def test_build_failure_index_with_classifications():
    junit_data = {
        "count": 3,
        "tests": [
            {
                "nodeid": "tests/unit/test_normal.py::test_fail",
                "status": "failure",
                "seconds": 0.05,
                "details": {
                    "type": "AssertionError",
                    "message": "assert False",
                    "text": "def test_fail():\n> assert False\nE AssertionError: assert False",
                },
            },
            {
                "nodeid": "tests/integration/p3/test_transfer_admission.py::test_transfer_blocked",
                "status": "failure",
                "seconds": 0.12,
                "details": {
                    "type": "TransferError",
                    "message": "Transfer stage requirement unfulfilled",
                    "text": "def test_transfer_blocked():\n> raise TransferError()",
                },
            },
            {
                "nodeid": "tests/unit/test_other.py::test_skip",
                "status": "skipped",
                "seconds": 0.001,
                "details": {
                    "type": "pytest.skip",
                    "message": "unsupported on this OS",
                    "text": "",
                },
            },
        ],
    }
    index = ci_profile.build_failure_index(junit_data)
    assert index["failure_count"] == 2
    assert index["skipped_count"] == 1

    f1 = index["failures"][0]
    assert f1["classification"] == "NEW_REGRESSION"
    assert f1["exception_type"] == "AssertionError"
    assert len(f1["sample_lines"]) > 0

    f2 = index["failures"][1]
    assert f2["classification"] == "INHERITED_STAGE_TRANSFER"
    assert f2["exception_type"] == "TransferError"


def test_build_execution_summary():
    record = {
        "invocation_id": "inv-12345",
        "name": "tests",
        "mode": "xdist",
        "runtime": {"commit_sha": "abc1234567890", "tree_sha": "def1234567890"},
        "exit_code": 0,
        "wall_seconds": 12.34,
        "cumulative_test_seconds": 45.67,
        "workers": 4,
        "selection": {
            "test_ids": ["tests/unit/test_a.py::t1", "tests/unit/test_a.py::t2"]
        },
        "junit": {
            "count": 2,
            "tests": [
                {"nodeid": "tests/unit/test_a.py::t1", "status": "passed"},
                {"nodeid": "tests/unit/test_a.py::t2", "status": "passed"},
            ],
        },
        "artifacts": {"profile": "invocations/tests-inv-12345.json"},
    }
    summary = ci_profile.build_execution_summary(record)
    assert summary["version"] == 1
    assert summary["invocation_id"] == "inv-12345"
    assert summary["exit_code"] == 0
    assert summary["counts"]["total"] == 2
    assert summary["counts"]["passed"] == 2
    assert summary["counts"]["failed"] == 0
    assert summary["reconciliation"]["status"] == "EXACT_ONCE_MATCH"
    assert summary["reconciliation"]["consistent"] is True


def test_format_terminal_summary_clean():
    record = {
        "invocation_id": "tests-100",
        "name": "tests",
        "mode": "xdist",
        "workers": 4,
        "wall_seconds": 10.0,
        "cumulative_test_seconds": 38.0,
        "exit_code": 0,
        "runtime": {"commit_sha": "12345678abcdef", "tree_sha": "fedcba87654321"},
        "artifacts": {"profile": "artifacts/ci-profile/invocations/tests-100.json"},
    }
    exec_summary = ci_profile.build_execution_summary(record)
    text = ci_profile.format_terminal_summary(record, exec_summary)
    assert "=== Validation Summary: tests (xdist-4) ===" in text
    assert "Invocation ID:   tests-100" in text
    assert "Exit Status:     SUCCESS" in text
    assert "Evidence Dir:" in text


def test_format_terminal_summary_with_failures():
    record = {
        "invocation_id": "tests-fail",
        "name": "tests",
        "mode": "xdist",
        "workers": 2,
        "wall_seconds": 5.0,
        "cumulative_test_seconds": 8.0,
        "exit_code": 1,
        "runtime": {"commit_sha": "12345678", "tree_sha": "87654321"},
        "artifacts": {"profile": "artifacts/ci-profile/invocations/tests-fail.json"},
    }
    junit_data = {
        "count": 1,
        "tests": [
            {
                "nodeid": "tests/unit/test_x.py::test_fail",
                "status": "failure",
                "seconds": 0.1,
                "details": {
                    "type": "RuntimeError",
                    "message": "broken state",
                    "text": "Traceback:\nE RuntimeError: broken state",
                },
            }
        ],
    }
    fail_idx = ci_profile.build_failure_index(junit_data)
    exec_summary = ci_profile.build_execution_summary(record, failure_index=fail_idx)
    text = ci_profile.format_terminal_summary(
        record, exec_summary, failure_index=fail_idx
    )
    assert "Exit Status:     FAILURE (exit code 1)" in text
    assert "Failures: 1 total (1 new regression(s), 0 inherited)" in text
    assert "[NEW_REGRESSION] tests/unit/test_x.py::test_fail" in text
    assert "RuntimeError: broken state" in text


def test_quiet_execution_streams_log_and_saves_indices(tmp_path, monkeypatch):
    script = "import sys\nprint('line 1')\nprint('line 2')\nsys.exit(0)\n"
    cmd = [sys.executable, "-c", script]
    args = Namespace(
        command=cmd,
        output=tmp_path,
        name="quiet-test",
        junit=None,
        journal=None,
        mode="sequential",
        workers=1,
        quiet=True,
    )
    exit_code = ci_profile.run(args)
    assert exit_code == 0

    log_file = tmp_path / "quiet-test.log"
    assert log_file.is_file()
    assert "line 1\nline 2" in log_file.read_text()

    summary_file = tmp_path / "execution-summary.json"
    assert summary_file.is_file()
    summary = json.loads(summary_file.read_text())
    assert summary["exit_code"] == 0

    fail_file = tmp_path / "failure-index.json"
    assert fail_file.is_file()
    fail_idx = json.loads(fail_file.read_text())
    assert fail_idx["failure_count"] == 0


def test_ci_query_cli(tmp_path, capsys):
    summary_file = tmp_path / "execution-summary.json"
    summary_file.write_text(
        json.dumps(
            {
                "version": 1,
                "invocation_id": "test-inv",
                "name": "unit",
                "lane": "unit",
                "exit_code": 0,
                "wall_seconds": 1.23,
                "workers": 2,
                "counts": {"passed": 10, "failed": 0},
                "reconciliation": {"status": "EXACT_ONCE_MATCH"},
            }
        )
    )
    fail_file = tmp_path / "failure-index.json"
    fail_file.write_text(
        json.dumps(
            {
                "version": 1,
                "failure_count": 1,
                "failures": [
                    {
                        "nodeid": "tests/unit/test_sample.py::test_boom",
                        "classification": "NEW_REGRESSION",
                        "phase": "call",
                        "exception_type": "AssertionError",
                        "message": "boom",
                        "sample_lines": ["> assert False", "E AssertionError: boom"],
                    }
                ],
            }
        )
    )

    # Test query status
    assert ci_query.main(["status", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert "PASSED" in captured.out

    # Test query summary
    assert ci_query.main(["summary", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert "Invocation:     test-inv" in captured.out
    assert "Passed/Failed:  10 / 0" in captured.out

    # Test query failures
    assert ci_query.main(["failures", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "[NEW_REGRESSION] tests/unit/test_sample.py::test_boom" in captured.out

    # Test query specific failure node
    assert ci_query.main(["failure", str(tmp_path), "--node", "test_boom"]) == 0
    captured = capsys.readouterr()
    assert "AssertionError: boom" in captured.out
    assert "assert False" in captured.out
