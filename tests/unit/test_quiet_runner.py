import base64
import concurrent.futures
import io
import json
import sys
import zipfile
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


def test_build_failure_index_unclassified_without_reconciliation():
    junit_data = {
        "count": 2,
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
        ],
    }
    # Without authoritative reconciliation, ALL failures must be UNCLASSIFIED_FAILURE,
    # never inferred as inherited from test name patterns!
    index = ci_profile.build_failure_index(junit_data)
    assert index["failure_count"] == 2
    for f in index["failures"]:
        assert f["classification"] == "UNCLASSIFIED_FAILURE"
        assert f["is_inherited"] is False


def test_build_failure_index_with_authoritative_reconciliation():
    junit_data = {
        "count": 3,
        "tests": [
            {
                "nodeid": "tests/integration/p3/test_transfer_admission.py::test_transfer_blocked",
                "status": "failure",
                "seconds": 0.12,
                "details": {
                    "type": "TransferError",
                    "message": "Transfer stage requirement unfulfilled",
                },
            },
            {
                "nodeid": "tests/integration/p3/test_transfer_admission.py::test_transfer_changed",
                "status": "failure",
                "seconds": 0.10,
                "details": {
                    "type": "UnexpectedException",
                    "message": "Changed failure exception",
                },
            },
            {
                "nodeid": "tests/unit/test_fresh.py::test_regress",
                "status": "failure",
                "seconds": 0.05,
                "details": {
                    "type": "AssertionError",
                    "message": "assert 1 == 2",
                },
            },
        ],
    }
    reconciliation = {
        "acceptance_verdict": "FAILED",
        "new_regressions_count": 1,
        "changed_failures_count": 1,
        "node_details": [
            {
                "node_id": "tests/integration/p3/test_transfer_admission.py::test_transfer_blocked",
                "classification": "STAGE_TRANSFER",
                "is_inherited": True,
            },
            {
                "node_id": "tests/integration/p3/test_transfer_admission.py::test_transfer_changed",
                "classification": "CHANGED_FAILURE",
                "is_inherited": False,
            },
            {
                "node_id": "tests/unit/test_fresh.py::test_regress",
                "classification": "NEW_REGRESSION",
                "is_inherited": False,
            },
        ],
    }
    index = ci_profile.build_failure_index(junit_data, reconciliation=reconciliation)
    assert index["failure_count"] == 3

    f_map = {f["nodeid"]: f for f in index["failures"]}
    f1 = f_map["tests/integration/p3/test_transfer_admission.py::test_transfer_blocked"]
    assert f1["classification"] == "INHERITED_STAGE_TRANSFER"
    assert f1["is_inherited"] is True

    # Same test file/prefix, but with changed exception: must NOT be inherited!
    f2 = f_map["tests/integration/p3/test_transfer_admission.py::test_transfer_changed"]
    assert f2["classification"] == "CHANGED_FAILURE"
    assert f2["is_inherited"] is False

    f3 = f_map["tests/unit/test_fresh.py::test_regress"]
    assert f3["classification"] == "NEW_REGRESSION"
    assert f3["is_inherited"] is False


def test_build_execution_summary_exact_once_match():
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


def test_build_execution_summary_adversarial_equal_count_different_nodes():
    """Adversarial check: Equal node count (2 == 2) must NEVER produce EXACT_ONCE_MATCH if identities differ."""
    record = {
        "invocation_id": "inv-adversarial",
        "name": "tests",
        "mode": "xdist",
        "runtime": {"commit_sha": "abc1234567890", "tree_sha": "def1234567890"},
        "exit_code": 0,
        "wall_seconds": 5.0,
        "cumulative_test_seconds": 5.0,
        "workers": 2,
        "selection": {
            "test_ids": ["tests/unit/test_a.py::t1", "tests/unit/test_a.py::t2"]
        },
        "junit": {
            "count": 2,
            # Equal count (2), but t2 is missing and t_unexpected is extra!
            "tests": [
                {"nodeid": "tests/unit/test_a.py::t1", "status": "passed"},
                {"nodeid": "tests/unit/test_a.py::t_unexpected", "status": "passed"},
            ],
        },
        "artifacts": {"profile": "invocations/tests-inv-adversarial.json"},
    }
    summary = ci_profile.build_execution_summary(record)
    assert summary["reconciliation"]["status"] != "EXACT_ONCE_MATCH"
    assert "NODE_MISMATCH" in summary["reconciliation"]["status"]
    assert summary["reconciliation"]["consistent"] is False
    assert summary["reconciliation"]["missing_count"] == 1
    assert summary["reconciliation"]["unexpected_count"] == 1
    assert summary["counts"]["unexecuted"] == 1


def test_build_execution_summary_interrupted():
    record = {
        "invocation_id": "inv-interrupted",
        "name": "tests",
        "mode": "sequential",
        "runtime": {"commit_sha": "abc1234567890", "tree_sha": "def1234567890"},
        "exit_code": 2,
        "interrupted": True,
        "wall_seconds": 1.0,
        "cumulative_test_seconds": 1.0,
        "workers": 1,
        "selection": {
            "test_ids": ["tests/unit/test_a.py::t1", "tests/unit/test_a.py::t2"]
        },
        "junit": {
            "count": 1,
            "tests": [{"nodeid": "tests/unit/test_a.py::t1", "status": "passed"}],
        },
    }
    summary = ci_profile.build_execution_summary(record)
    assert summary["reconciliation"]["status"] == "INTERRUPTED_EXECUTION"
    assert summary["reconciliation"]["consistent"] is False


def test_format_terminal_summary_clean():
    record = {
        "invocation_id": "tests-100",
        "name": "tests",
        "mode": "xdist",
        "workers": 4,
        "wall_seconds": 10.0,
        "cumulative_test_seconds": 38.0,
        "exit_code": 0,
        "command": ["pytest", "tests/unit"],
        "runtime": {"commit_sha": "12345678abcdef", "tree_sha": "fedcba87654321"},
        "artifacts": {"profile": "artifacts/ci-profile/invocations/tests-100.json"},
        "junit": {
            "count": 2,
            "tests": [
                {"nodeid": "tests/unit/test_a.py::t1", "status": "passed"},
                {"nodeid": "tests/unit/test_a.py::t2", "status": "passed"},
            ],
        },
    }
    exec_summary = ci_profile.build_execution_summary(record)
    text = ci_profile.format_terminal_summary(record, exec_summary)
    assert "[tests] PASSED" in text
    assert "xdist, 4w" in text
    assert "wall=10.00s" in text
    assert "reconciliation: ALL_PASSED_UNVERIFIED_SELECTION" in text
    assert len(text.encode("utf-8")) < 300


def test_format_terminal_summary_non_test_command():
    record = {
        "invocation_id": "lint-100",
        "name": "lint",
        "mode": "sequential",
        "workers": 1,
        "wall_seconds": 1.25,
        "exit_code": 0,
        "command": ["ruff", "check"],
        "runtime": {"commit_sha": "12345678", "tree_sha": "87654321"},
        "artifacts": {"profile": "invocations/lint-100.json"},
    }
    exec_summary = ci_profile.build_execution_summary(record)
    text = ci_profile.format_terminal_summary(record, exec_summary)
    assert "[lint] PASSED" in text
    assert "wall=1.25s" in text
    # Non-test operations must not print meaningless 0-passed test statistics
    assert "tests:" not in text
    assert len(text.encode("utf-8")) < 200


def test_quiet_execution_streams_log_and_saves_indices(tmp_path):
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
    # Artifacts map must contain valid paths
    assert "profile" in summary["artifacts"]
    assert "log" in summary["artifacts"]
    assert "log_sha256" in summary["artifacts"]

    fail_file = tmp_path / "failure-index.json"
    assert fail_file.is_file()
    fail_idx = json.loads(fail_file.read_text())
    assert fail_idx["failure_count"] == 0


def test_concurrent_invocations_isolated_paths(tmp_path):
    """Verify that multiple concurrent invocations in the same output dir do not collide."""

    def run_worker(idx):
        script = (
            f"import sys, time\ntime.sleep(0.05)\nprint('worker {idx}')\nsys.exit(0)\n"
        )
        args = Namespace(
            command=[sys.executable, "-c", script],
            output=tmp_path,
            name=f"worker-{idx}",
            junit=None,
            journal=None,
            mode="sequential",
            workers=1,
            quiet=True,
            invocation_id=f"concurrent-{idx}",
        )
        return ci_profile.run(args)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(run_worker, range(4)))

    assert results == [0, 0, 0, 0]
    inv_dir = tmp_path / "invocations"
    assert inv_dir.is_dir()
    for idx in range(4):
        log_f = inv_dir / f"worker-{idx}-concurrent-{idx}.log"
        assert log_f.is_file()
        assert f"worker {idx}" in log_f.read_text()
        summary_f = inv_dir / f"summary-worker-{idx}-concurrent-{idx}.json"
        assert summary_f.is_file()


def test_large_log_streaming_and_chunked_hashing(tmp_path):
    """Verify that large output streams without whole-file read_bytes() buffering."""
    # Generate 1 MB of repetitive output
    script = "import sys\nfor _ in range(10000):\n    print('A' * 100)\nsys.exit(0)\n"
    args = Namespace(
        command=[sys.executable, "-c", script],
        output=tmp_path,
        name="large-log-test",
        junit=None,
        journal=None,
        mode="sequential",
        workers=1,
        quiet=True,
    )
    exit_code = ci_profile.run(args)
    assert exit_code == 0

    log_file = tmp_path / "large-log-test.log"
    assert log_file.is_file()
    assert log_file.stat().st_size > 1_000_000

    summary = json.loads((tmp_path / "execution-summary.json").read_text())
    assert "log_sha256" in summary["artifacts"]
    assert len(summary["artifacts"]["log_sha256"]) == 64


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
                "counts": {"total": 10, "passed": 10, "failed": 0},
                "reconciliation": {"status": "EXACT_ONCE_MATCH", "consistent": True},
            }
        )
    )
    fail_file = tmp_path / "failure-index.json"
    fail_file.write_text(
        json.dumps(
            {
                "version": 1,
                "failure_count": 3,
                "failures": [
                    {
                        "nodeid": "tests/unit/test_sample.py::test_boom",
                        "classification": "NEW_REGRESSION",
                        "is_inherited": False,
                        "phase": "call",
                        "exception_type": "AssertionError",
                        "message": "boom",
                        "sample_lines": ["> assert False", "E AssertionError: boom"],
                    },
                    {
                        "nodeid": "tests/unit/test_sample.py::test_changed",
                        "classification": "CHANGED_FAILURE",
                        "is_inherited": False,
                        "phase": "call",
                        "exception_type": "ValueError",
                        "message": "changed val",
                        "sample_lines": ["E ValueError: changed val"],
                    },
                    {
                        "nodeid": "tests/integration/test_transfer.py::test_transfer_blocked",
                        "classification": "INHERITED_STAGE_TRANSFER",
                        "is_inherited": True,
                        "phase": "call",
                        "exception_type": "TransferError",
                        "message": "stage transfer blocked",
                        "sample_lines": ["E TransferError"],
                    },
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
    assert "10 total | 10 passed | 0 failed" in captured.out

    # Test query failures (all)
    assert ci_query.main(["failures", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "Total matching failures: 3" in captured.out
    assert "[NEW_REGRESSION] tests/unit/test_sample.py::test_boom" in captured.out
    assert "[CHANGED_FAILURE] tests/unit/test_sample.py::test_changed" in captured.out
    assert (
        "[INHERITED_STAGE_TRANSFER] tests/integration/test_transfer.py::test_transfer_blocked"
        in captured.out
    )

    # Test query failures with --new-only: must keep NEW_REGRESSION and CHANGED_FAILURE, excluding only inherited!
    assert ci_query.main(["failures", str(tmp_path), "--new-only"]) == 1
    captured = capsys.readouterr()
    assert "Total matching failures: 2" in captured.out
    assert "test_boom" in captured.out
    assert "test_changed" in captured.out
    assert "test_transfer_blocked" not in captured.out

    # Test query specific failure node exact match
    assert (
        ci_query.main(
            ["failure", str(tmp_path), "--node", "tests/unit/test_sample.py::test_boom"]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert "AssertionError: boom" in captured.out

    # Test query ambiguous failure node substring match
    assert ci_query.main(["failure", str(tmp_path), "--node", "test_sample.py"]) == 2
    captured = capsys.readouterr()
    assert "Ambiguous query 'test_sample.py' matches 2 nodes" in captured.err


def test_ci_query_log_filter_and_receipt_extract(tmp_path):
    import hashlib

    # Create synthetic zip archive with verified receipt-index.json
    buf = io.BytesIO()
    file_data = b'{"ok": true}\n'
    idx_data = json.dumps(
        {
            "test-receipt.json": {
                "bytes": len(file_data),
                "sha256": hashlib.sha256(file_data).hexdigest(),
            }
        }
    ).encode("utf-8")
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test-receipt.json", file_data)
        zf.writestr("receipt-index.json", idx_data)
    zip_bytes = buf.getvalue()
    b64_payload = base64.b64encode(zip_bytes).decode("ascii")

    digest = hashlib.sha256(zip_bytes).hexdigest()

    log_content = (
        "Starting job...\n"
        f"CI_RECEIPTS_BEGIN_V1 {digest} {len(zip_bytes)}\n"
        f"CI_RECEIPTS_DATA_V1 {b64_payload[:40]}\n"
        f"CI_RECEIPTS_DATA_V1 {b64_payload[40:]}\n"
        f"CI_RECEIPTS_END_V1 {digest}\n"
        "Job completed successfully.\n"
    )
    log_file = tmp_path / "job.log"
    log_file.write_text(log_content)

    # Test filter-log
    output_filtered = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = output_filtered
        ci_query.main(["filter-log", str(log_file)])
    finally:
        sys.stdout = old_stdout

    filtered_text = output_filtered.getvalue()
    assert "Starting job..." in filtered_text
    assert "Job completed successfully." in filtered_text
    assert "CI_RECEIPTS_DATA_V1" not in filtered_text

    # Test extract-receipt
    dest_dir = tmp_path / "extracted"
    ret = ci_query.main(["extract-receipt", str(log_file), "--dest", str(dest_dir)])
    assert ret == 0
    assert (dest_dir / "test-receipt.json").is_file()
    assert json.loads((dest_dir / "test-receipt.json").read_text())["ok"] is True
