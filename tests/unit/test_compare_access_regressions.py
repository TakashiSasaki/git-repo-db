"""Tests for regression comparator and workflow contract verification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.compare_access_regressions import (
    compare_failure_details,
    compare_manifests,
    load_junit,
    parse_expected_nodes,
)

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "compare_access_regressions.py"
)


def make_xml(cases: list[dict], suite_name: str = "testsuite") -> str:
    body = []
    for c in cases:
        elem_lines = []
        if c.get("failure"):
            msg = c.get("msg", "failed")
            text = c.get("text", "")
            elem_lines.append(f'<failure message="{msg}">{text}</failure>')
        elif c.get("error"):
            msg = c.get("msg", "error")
            text = c.get("text", "")
            elem_lines.append(f'<error message="{msg}">{text}</error>')
        elif c.get("skipped"):
            msg = c.get("msg", "skipped")
            elem_lines.append(f'<skipped message="{msg}"/>')

        body.append(
            f'<testcase classname="{c["classname"]}" name="{c["name"]}">'
            + "".join(elem_lines)
            + "</testcase>"
        )
    return f'<?xml version="1.0" encoding="utf-8"?><testsuite tests="{len(cases)}" name="{suite_name}">{"".join(body)}</testsuite>'


def test_empty_xml_rejected(tmp_path):
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    out_file = tmp_path / "out.json"

    base_file.write_text(make_xml([{"classname": "test_pkg", "name": "test_one"}]))
    curr_file.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuite tests="0"></testsuite>'
    )

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert (
        "Empty current JUnit XML" in proc.stderr
        or "missing from execution" in proc.stderr
    )


def test_skipped_testcase_rejected_under_strict(tmp_path):
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    out_file = tmp_path / "out.json"

    base_file.write_text(
        make_xml(
            [
                {
                    "classname": "test_pkg",
                    "name": "test_one",
                    "failure": True,
                    "msg": "failed",
                }
            ]
        )
    )
    curr_file.write_text(
        make_xml(
            [
                {
                    "classname": "test_pkg",
                    "name": "test_one",
                    "skipped": True,
                    "msg": "unexpected skip",
                }
            ]
        )
    )

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "unexpected skipped test nodes detected" in proc.stderr


def test_duplicate_and_subtest_records_handled_without_overwriting(tmp_path):
    curr_file = tmp_path / "current.xml"
    curr_file.write_text(
        make_xml(
            [
                {
                    "classname": "test_pkg",
                    "name": "test_dup",
                    "failure": True,
                    "msg": "call failure",
                },
                {"classname": "test_pkg", "name": "test_dup"},
            ]
        )
    )

    cases = load_junit(curr_file)
    node = cases["test_pkg::test_dup"]
    assert node["record_count"] == 2
    assert len(node["records"]) == 2
    assert node["status"] == "FAIL"


def test_added_failing_node_rejected_under_strict(tmp_path):
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    out_file = tmp_path / "out.json"

    base_file.write_text(make_xml([{"classname": "test_pkg", "name": "test_one"}]))
    curr_file.write_text(
        make_xml(
            [
                {"classname": "test_pkg", "name": "test_one"},
                {
                    "classname": "test_pkg",
                    "name": "test_new",
                    "failure": True,
                    "msg": "added failed",
                },
            ]
        )
    )

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "added failing test nodes detected" in proc.stderr


def test_environment_failure_rejected_under_strict(tmp_path):
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    out_file = tmp_path / "out.json"

    base_file.write_text(make_xml([{"classname": "test_pkg", "name": "test_one"}]))
    curr_file.write_text(
        make_xml(
            [
                {
                    "classname": "test_pkg",
                    "name": "test_one",
                    "error": True,
                    "msg": "FileNotFoundError: 'repo-catalog'",
                    "text": "FileNotFoundError: [Errno 2] No such file or directory: 'repo-catalog'",
                }
            ]
        )
    )

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "environment failures detected" in proc.stderr


def test_changed_failure_rejected_under_strict(tmp_path):
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    out_file = tmp_path / "out.json"

    base_file.write_text(
        make_xml(
            [
                {
                    "classname": "test_pkg",
                    "name": "test_one",
                    "failure": True,
                    "msg": "UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED",
                    "text": "UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED",
                }
            ]
        )
    )
    curr_file.write_text(
        make_xml(
            [
                {
                    "classname": "test_pkg",
                    "name": "test_one",
                    "error": True,
                    "msg": "setup error: DatabaseError: file is encrypted",
                    "text": "sqlite3.DatabaseError: file is encrypted",
                }
            ]
        )
    )

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "changed non-successes detected" in proc.stderr


def test_missing_expected_node_rejected(tmp_path):
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    exp_file = tmp_path / "expected.txt"
    out_file = tmp_path / "out.json"

    base_file.write_text(
        make_xml(
            [
                {"classname": "test_pkg", "name": "test_one"},
                {"classname": "test_pkg", "name": "test_two"},
            ]
        )
    )
    curr_file.write_text(make_xml([{"classname": "test_pkg", "name": "test_one"}]))
    exp_file.write_text("test_pkg::test_one\ntest_pkg::test_two\n")

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--expected",
        str(exp_file),
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "expected test nodes missing from execution" in proc.stderr


def test_scoped_baseline_subset_partitions_without_false_deletions(tmp_path):
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    exp_file = tmp_path / "expected.txt"
    out_file = tmp_path / "out.json"

    # Baseline has 3 nodes
    base_file.write_text(
        make_xml(
            [
                {"classname": "test_pkg", "name": "test_in_scope_pass"},
                {
                    "classname": "test_pkg",
                    "name": "test_in_scope_inherited",
                    "failure": True,
                    "msg": "UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED",
                    "text": "UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED",
                },
                {"classname": "test_pkg", "name": "test_out_of_scope"},
            ]
        )
    )
    # Scoped execution only targets 2 nodes
    curr_file.write_text(
        make_xml(
            [
                {"classname": "test_pkg", "name": "test_in_scope_pass"},
                {
                    "classname": "test_pkg",
                    "name": "test_in_scope_inherited",
                    "failure": True,
                    "msg": "UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED",
                    "text": "UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED",
                },
            ]
        )
    )
    exp_file.write_text(
        "test_pkg::test_in_scope_pass\ntest_pkg::test_in_scope_inherited\n"
    )

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--expected",
        str(exp_file),
        "--pytest-exit-code",
        "1",
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0

    base_cases = load_junit(base_file)
    curr_cases = load_junit(curr_file)
    exp_nodes = parse_expected_nodes(exp_file)
    summary = compare_manifests(
        base_cases, curr_cases, expected_nodes=exp_nodes, pytest_exit_code=1
    )
    assert summary["acceptance_verdict"] == "PASSED"
    assert summary["in_scope_baseline_nodes"] == 2
    assert summary["out_of_scope_baseline_nodes"] == 1
    assert summary["missing_nodes_count"] == 0
    assert summary["inherited_non_successes_count"] == 1
    assert summary["new_regressions_count"] == 0


@pytest.mark.parametrize("exit_code", [2, 3, 4, 5])
def test_abnormal_pytest_exit_codes_rejected(tmp_path, exit_code):
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    out_file = tmp_path / "out.json"

    base_file.write_text(make_xml([{"classname": "test_pkg", "name": "test_one"}]))
    curr_file.write_text(make_xml([{"classname": "test_pkg", "name": "test_one"}]))

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--pytest-exit-code",
        str(exit_code),
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "Pytest exit validation error" in proc.stderr


def test_counterexample_a_transfer_stage_fence_requires_error_marker(tmp_path):
    """Counterexample A: test name alone must not cause unrelated failure to be inherited."""
    b_info = {
        "name": "test_transfer_reports_never_shrunk_or_mixed",
        "phase": "call",
        "refusal_code": "I2_TRANSFER_UNSUPPORTED",
        "reached_assertion": "UnsupportedResourceStage",
        "exception_type": "UnsupportedResourceStage",
        "message": "UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED",
        "text": "UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED",
    }
    c_info = {
        "name": "test_transfer_reports_never_shrunk_or_mixed",
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": "assert 1 == 2",
        "exception_type": "AssertionError",
        "message": "AssertionError: assert 1 == 2",
        "text": "AssertionError: assert 1 == 2",
    }
    cat, unchanged, reason = compare_failure_details(b_info, c_info)
    assert cat == "CHANGED_FAILURE"
    assert not unchanged
    assert "Progressed past staged Transfer barrier" in (reason or "")

    # Also test via full manifest comparison and CLI
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    out_file = tmp_path / "out.json"

    base_file.write_text(
        make_xml(
            [
                {
                    "classname": "test_pkg",
                    "name": "test_transfer_reports_never_shrunk_or_mixed",
                    "failure": True,
                    "msg": "UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED",
                    "text": "repo_catalog.domain.resource_stage.UnsupportedResourceStage: I2_TRANSFER_UNSUPPORTED",
                }
            ]
        )
    )
    curr_file.write_text(
        make_xml(
            [
                {
                    "classname": "test_pkg",
                    "name": "test_transfer_reports_never_shrunk_or_mixed",
                    "failure": True,
                    "msg": "AssertionError: assert 1 == 2",
                    "text": "AssertionError: assert 1 == 2",
                }
            ]
        )
    )

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "changed non-successes detected" in proc.stderr


def test_counterexample_b_unknown_metadata_fallback_rejected(tmp_path):
    """Counterexample B: unknown metadata (None==None) must not be treated as unchanged."""
    b_info = {
        "name": "test_something",
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": None,
        "exception_type": "ValueError",
        "message": "",
        "text": "",
    }
    c_info = {
        "name": "test_something",
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": None,
        "exception_type": "TypeError",
        "message": "",
        "text": "",
    }
    cat, unchanged, reason = compare_failure_details(b_info, c_info)
    assert cat == "CHANGED_FAILURE"
    assert not unchanged
    assert "Exception type mismatch" in (reason or "")

    # CLI check
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    out_file = tmp_path / "out.json"

    base_file.write_text(
        make_xml(
            [
                {
                    "classname": "test_pkg",
                    "name": "test_b",
                    "failure": True,
                    "msg": "ValueError",
                    "text": "ValueError",
                }
            ]
        )
    )
    curr_file.write_text(
        make_xml(
            [
                {
                    "classname": "test_pkg",
                    "name": "test_b",
                    "failure": True,
                    "msg": "TypeError",
                    "text": "TypeError",
                }
            ]
        )
    )

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "changed non-successes detected" in proc.stderr


def test_admission_refusal_code_mismatch_rejected():
    """Admission refusal code mismatch (PERMISSION_DENIED vs INVALID_IDENTIFICATION) must be CHANGED_FAILURE."""
    b_info = {
        "phase": "call",
        "refusal_code": "PERMISSION_DENIED",
        "exception_type": "AdmissionRefused",
        "message": "AdmissionRefused: PERMISSION_DENIED",
        "text": "repo_catalog.domain.context_admission.AdmissionRefused: PERMISSION_DENIED",
    }
    c_info = {
        "phase": "call",
        "refusal_code": "INVALID_IDENTIFICATION",
        "exception_type": "AdmissionRefused",
        "message": "AdmissionRefused: INVALID_IDENTIFICATION",
        "text": "repo_catalog.domain.context_admission.AdmissionRefused: INVALID_IDENTIFICATION",
    }
    cat, unchanged, reason = compare_failure_details(b_info, c_info)
    assert cat == "CHANGED_FAILURE"
    assert not unchanged
    assert (
        "Admission refusal mismatch: baseline code=PERMISSION_DENIED vs current code=INVALID_IDENTIFICATION"
        in (reason or "")
    )


def test_admission_exception_type_mismatch_rejected():
    """Admission exception type mismatch must be CHANGED_FAILURE."""
    b_info = {
        "phase": "call",
        "refusal_code": "PERMISSION_DENIED",
        "exception_type": "AdmissionRefused",
        "message": "AdmissionRefused: PERMISSION_DENIED",
        "text": "repo_catalog.domain.context_admission.AdmissionRefused: PERMISSION_DENIED",
    }
    c_info = {
        "phase": "call",
        "refusal_code": "PERMISSION_DENIED",
        "exception_type": "ValueError",
        "message": "ValueError: PERMISSION_DENIED",
        "text": "ValueError: PERMISSION_DENIED",
    }
    cat, unchanged, reason = compare_failure_details(b_info, c_info)
    assert cat == "CHANGED_FAILURE"
    assert not unchanged


def test_admission_matching_permission_denied_accepted():
    """Matching PERMISSION_DENIED on compatible exception types is accepted as INHERITED_ADMISSION_PERMISSION_DENIED."""
    b_info = {
        "phase": "call",
        "refusal_code": "PERMISSION_DENIED",
        "exception_type": "AdmissionRefused",
        "message": "AdmissionRefused: PERMISSION_DENIED",
        "text": "repo_catalog.domain.context_admission.AdmissionRefused: PERMISSION_DENIED",
    }
    c_info = {
        "phase": "call",
        "refusal_code": "PERMISSION_DENIED",
        "exception_type": "AdmissionRefused",
        "message": "AdmissionRefused: PERMISSION_DENIED",
        "text": "repo_catalog.domain.context_admission.AdmissionRefused: PERMISSION_DENIED",
    }
    cat, unchanged, reason = compare_failure_details(b_info, c_info)
    assert cat == "INHERITED_ADMISSION_PERMISSION_DENIED"
    assert unchanged
    assert reason is None


def test_p7_recovery_classname_alone_without_matching_signature_rejected():
    """P7 recovery: classname alone without matching signature must be CHANGED_FAILURE."""
    b_info = {
        "classname": "tests.integration.p7.test_bounded_input",
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": "assert a == 1",
        "exception_type": "AssertionError",
        "message": "assert a == 1",
        "text": "assert a == 1",
    }
    c_info = {
        "classname": "tests.integration.p7.test_bounded_input",
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": "assert b == 2",
        "exception_type": "AssertionError",
        "message": "assert b == 2",
        "text": "assert b == 2",
    }
    cat, unchanged, reason = compare_failure_details(b_info, c_info)
    assert cat == "CHANGED_FAILURE"
    assert not unchanged
    assert "P7 recovery mismatch" in (reason or "")


def test_p7_recovery_matching_signature_accepted():
    """P7 recovery: matching refusal code and assertion is accepted as INHERITED_P7_RECOVERY."""
    b_info = {
        "classname": "tests.integration.p7.test_bounded_input",
        "phase": "call",
        "refusal_code": "PERMISSION_DENIED",
        "reached_assertion": "assert False",
        "exception_type": "AssertionError",
        "message": "assert False",
        "text": "assert False\nContext admission error: PERMISSION_DENIED",
    }
    c_info = {
        "classname": "tests.integration.p7.test_bounded_input",
        "phase": "call",
        "refusal_code": "PERMISSION_DENIED",
        "reached_assertion": "assert False",
        "exception_type": "AssertionError",
        "message": "assert False",
        "text": "assert False\nContext admission error: PERMISSION_DENIED",
    }
    cat, unchanged, reason = compare_failure_details(b_info, c_info)
    assert cat == "INHERITED_P7_RECOVERY"
    assert unchanged
    assert reason is None


def test_general_fallback_unknown_metadata_none_none_rejected():
    """General fallback: identical exception with unknown metadata on both sides must be CHANGED_FAILURE."""
    b_info = {
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": None,
        "exception_type": "ValueError",
    }
    c_info = {
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": None,
        "exception_type": "ValueError",
    }
    cat, unchanged, reason = compare_failure_details(b_info, c_info)
    assert cat == "CHANGED_FAILURE"
    assert not unchanged
    assert "missing concrete refusal_code or reached_assertion signature" in (
        reason or ""
    )


def test_general_fallback_matching_assertion_accepted():
    """General fallback: identical exception and non-None reached assertion is accepted as INHERITED_OTHER."""
    b_info = {
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": "assert len(items) == 5",
        "exception_type": "ValueError",
    }
    c_info = {
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": "assert len(items) == 5",
        "exception_type": "ValueError",
    }
    cat, unchanged, reason = compare_failure_details(b_info, c_info)
    assert cat == "INHERITED_OTHER"
    assert unchanged
    assert reason is None


def test_general_fallback_reached_assertion_mismatch_rejected():
    """General fallback: assertion mismatch must be CHANGED_FAILURE."""
    b_info = {
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": "assert len(items) == 5",
        "exception_type": "ValueError",
    }
    c_info = {
        "phase": "call",
        "refusal_code": None,
        "reached_assertion": "assert len(items) == 0",
        "exception_type": "ValueError",
    }
    cat, unchanged, reason = compare_failure_details(b_info, c_info)
    assert cat == "CHANGED_FAILURE"
    assert not unchanged
    assert "Reached assertion mismatch" in (reason or "")


def test_unexpected_nodes_executed_rejected_under_strict(tmp_path):
    """Unexpected test nodes executed beyond --expected must cause strict failure."""
    base_file = tmp_path / "baseline.xml"
    curr_file = tmp_path / "current.xml"
    exp_file = tmp_path / "expected.txt"
    out_file = tmp_path / "out.json"

    base_file.write_text(
        make_xml(
            [
                {"classname": "test_pkg", "name": "test_expected"},
                {"classname": "test_pkg", "name": "test_rogue"},
            ]
        )
    )
    curr_file.write_text(
        make_xml(
            [
                {"classname": "test_pkg", "name": "test_expected"},
                {"classname": "test_pkg", "name": "test_rogue"},
            ]
        )
    )
    exp_file.write_text("test_pkg::test_expected\n")

    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--baseline",
        str(base_file),
        "--current",
        str(curr_file),
        "--expected",
        str(exp_file),
        "--output",
        str(out_file),
        "--strict",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "unexpected test nodes executed" in proc.stderr
