"""Tests for regression comparator and workflow contract verification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.compare_access_regressions import (
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
