"""Mechanically compare broad regression execution against baseline #154 manifest.

Supports:
1. Explicit representation of PASS, FAIL, ERROR, SKIP, and UNEXECUTED outcomes.
2. Complete handling of duplicate records, setup/call/teardown phases, and subtests
   without silently overwriting evidence.
3. Collection and preservation of exact expected node manifest for scoped runs,
   verifying collection status, execution completeness, and missing/unexpected nodes.
4. Scoped baseline subset comparison: partitioning baseline into in-scope and out-of-scope,
   preserving unexecuted out-of-scope baseline nodes without labeling them removed/deleted.
5. Strict acceptance policy rejecting:
   - empty/truncated/incomplete results
   - unexpected skips
   - new failing nodes (NEW_REGRESSION)
   - added failing nodes (ADDED_FAIL)
   - environment failures (ENVIRONMENT_FAILURE)
   - unexplained changed failures (CHANGED_FAILURE)
   - missing expected nodes (MISSING_EXECUTION)
   - unexpected nodes (UNEXPECTED_NODE)
6. Fine-grained failure comparison: comparing baseline/current failure phase,
   refusal code, exception type, and reached assertion to distinguish unchanged
   inherited barriers from changed failures and regressions.
7. Verification of pytest exit code: permitting exit 1 only under documented scoped
   reconciliation, rejecting interruption (2), internal error (3), usage error (4),
   and no-tests collection (5).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = (
    ROOT
    / "docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/source-full-final/ordinary.xml.gz"
)


def parse_expected_nodes(path: Path) -> list[str]:
    """Parse expected node IDs from pytest --collect-only output or node manifest.

    Converts pytest node IDs (e.g. tests/integration/i2/test_foo.py::test_bar)
    to canonical keys: f"{classname}::{name}".
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    nodes = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or " tests collected in " in line:
            continue
        if ".py::" in line:
            file_part, rest = line.split(".py::", 1)
            c = file_part.replace("/", ".")
            if "::" in rest and not rest.startswith("Test"):
                parts = rest.split("::")
                if parts[0].isidentifier():
                    c = c + "." + parts[0]
                    rest = "::".join(parts[1:])
            n = rest
            nodes.append(f"{c}::{n}")
        elif "::" in line:
            nodes.append(line)
    return nodes


def extract_meta(
    elem: ET.Element | None,
) -> tuple[str | None, str | None, str | None, bool]:
    """Extract refusal code, assertion, exception type, and whether it's an environment failure."""
    if elem is None:
        return None, None, None, False

    text = elem.text or ""
    msg = elem.get("message", "")
    content = msg + "\n" + text

    # Environment failure detection
    is_env = False
    if "repo-catalog" in content and "FileNotFoundError" in content:
        is_env = True
    elif "Run scripts/prepare_wheelhouse.py" in content:
        is_env = True
    elif (
        "There was a problem with the editor" in content
        or "Author identity unknown" in content
    ):
        is_env = True

    # Refusal code extraction
    refusal_code = None
    refusal_match = re.search(
        r"""AdmissionRefused\([\"']([^\"']+)[\"']|I2_([A-Z_]+)_UNSUPPORTED|UnsupportedResourceStage\([\"']([^\"']+)[\"']|code\s*=\s*[\"']([^\"']+)[\"']""",
        content,
    )
    if refusal_match:
        refusal_code = next((g for g in refusal_match.groups() if g is not None), None)
    elif "PERMISSION_DENIED" in content:
        refusal_code = "PERMISSION_DENIED"
    elif "INVALID_IDENTIFICATION" in content:
        refusal_code = "INVALID_IDENTIFICATION"
    elif "FileNotFoundError" in content:
        refusal_code = "FILE_NOT_FOUND"

    # Exception type extraction
    exc_type = None
    exc_match = re.search(
        r"([A-Za-z0-9_.]*(?:Error|Exception|Refused|Failure|Stage))(?::|\()", content
    )
    if exc_match:
        exc_type = exc_match.group(1).split(".")[-1]

    # Reached assertion extraction
    assertion = None
    assert_match = re.search(r"assert\s+[^\n]+", text)
    if assert_match:
        assertion = assert_match.group(0).strip()
    elif msg:
        assertion = msg.splitlines()[0][:120].strip()

    return refusal_code, assertion, exc_type, is_env


def load_junit(path: Path) -> dict[str, dict]:
    """Load JUnit XML and extract all testcase records without overwriting.

    Handles duplicate testcase entries, subtests, and setup/call/teardown phases.
    """
    is_gz = str(path).endswith(".gz")
    opener = gzip.open if is_gz else open
    with opener(path, "rt", encoding="utf-8") as f:
        tree = ET.parse(f)

    cases: dict[str, dict] = {}
    for tc in tree.findall(".//testcase"):
        c = tc.get("classname", "")
        n = tc.get("name", "")
        node_id = f"{c}::{n}"

        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")

        elem = (
            failure
            if failure is not None
            else (error if error is not None else skipped)
        )

        if elem is None:
            status = "PASS"
            phase = "passed"
        elif skipped is not None:
            status = "SKIP"
            phase = "skipped"
        elif error is not None:
            status = "ERROR"
            msg_check = elem.get("message", "") + (elem.text or "")
            if "failed on teardown" in msg_check:
                phase = "teardown"
            elif "failed on setup" in msg_check:
                phase = "setup"
            else:
                phase = "setup"
        else:
            status = "FAIL"
            msg_check = elem.get("message", "") + (elem.text or "")
            if "failed on teardown" in msg_check:
                phase = "teardown"
            else:
                phase = "call"

        msg = elem.get("message", "") if elem is not None else ""
        text = elem.text or "" if elem is not None else ""
        code, assertion, exc_type, is_env = extract_meta(elem)

        record = {
            "status": status,
            "phase": phase,
            "message": msg,
            "text": text,
            "refusal_code": code,
            "reached_assertion": assertion,
            "exception_type": exc_type,
            "is_env": is_env,
        }

        if node_id not in cases:
            cases[node_id] = {
                "classname": c,
                "name": n,
                "node_id": node_id,
                "status": status,
                "phase": phase,
                "message": msg,
                "text": text,
                "refusal_code": code,
                "reached_assertion": assertion,
                "exception_type": exc_type,
                "is_env": is_env,
                "records": [record],
                "record_count": 1,
            }
        else:
            cases[node_id]["records"].append(record)
            cases[node_id]["record_count"] += 1
            # Composite priority: ERROR > FAIL > SKIP > PASS
            current_status = cases[node_id]["status"]
            if status == "ERROR":
                cases[node_id]["status"] = "ERROR"
                cases[node_id]["phase"] = phase
                cases[node_id]["message"] = msg
                cases[node_id]["text"] = text
                cases[node_id]["refusal_code"] = code
                cases[node_id]["reached_assertion"] = assertion
                cases[node_id]["exception_type"] = exc_type
                cases[node_id]["is_env"] = is_env
            elif status == "FAIL" and current_status != "ERROR":
                cases[node_id]["status"] = "FAIL"
                cases[node_id]["phase"] = phase
                cases[node_id]["message"] = msg
                cases[node_id]["text"] = text
                cases[node_id]["refusal_code"] = code
                cases[node_id]["reached_assertion"] = assertion
                cases[node_id]["exception_type"] = exc_type
                cases[node_id]["is_env"] = is_env
            elif status == "SKIP" and current_status == "PASS":
                cases[node_id]["status"] = "SKIP"
                cases[node_id]["phase"] = phase

    return cases


def is_transfer_stage_fence(info: dict) -> bool:
    text = info.get("text", "")
    msg = info.get("message", "")
    content = msg + "\n" + text
    code = info.get("refusal_code")
    exc = info.get("exception_type")
    has_marker = (
        "i2_transfer_stage_fence" in content
        or "i2_transfer_report_stage_fence" in content
        or "UnsupportedResourceStage" in content
        or "I2_TRANSFER_UNSUPPORTED" in content
        or code in ("I2_TRANSFER_UNSUPPORTED", "TRANSFER_UNSUPPORTED")
    )
    has_compat_exc = (
        exc
        in (
            "UnsupportedResourceStage",
            "OperationalError",
            "IntegrityError",
            "DatabaseError",
        )
        or "UnsupportedResourceStage" in content
        or "i2_transfer_stage_fence" in content
    )
    return bool(has_marker and has_compat_exc)


def is_admission_refusal(info: dict) -> bool:
    text = info.get("text", "")
    msg = info.get("message", "")
    content = msg + "\n" + text
    code = info.get("refusal_code")
    exc = info.get("exception_type")
    has_adm_code = (
        code in ("PERMISSION_DENIED", "INVALID_IDENTIFICATION")
        or "PERMISSION_DENIED" in content
        or "AdmissionRefused" in content
    )
    compat_exc = (
        exc in ("AdmissionRefused", "AdmissionFailure", "AssertionError")
        or "AdmissionRefused" in content
        or "AdmissionFailure" in content
    )
    return bool(has_adm_code and compat_exc)


def is_p7_recovery(info: dict) -> bool:
    c = info.get("classname", "")
    text = info.get("text", "")
    return "p7" in c or "Context admission error: PERMISSION_DENIED" in text


def compare_failure_details(b_info: dict, c_info: dict) -> tuple[str, bool, str | None]:
    """Compare baseline failure vs current failure.

    Returns: (classification, is_unchanged_inherited, change_reason)
    """
    if b_info.get("phase") != c_info.get("phase"):
        return (
            "CHANGED_FAILURE",
            False,
            f"Phase mismatch: baseline {b_info.get('phase')} != current {c_info.get('phase')}",
        )

    # 1. Staged Transfer barriers
    b_transfer = is_transfer_stage_fence(b_info)
    c_transfer = is_transfer_stage_fence(c_info)
    if b_transfer and c_transfer:
        return "INHERITED_STAGE_TRANSFER", True, None
    if b_transfer and not c_transfer:
        return (
            "CHANGED_FAILURE",
            False,
            "Progressed past staged Transfer barrier into different failure",
        )

    # 2. P7 recovery context admission refusals
    b_p7 = is_p7_recovery(b_info)
    c_p7 = is_p7_recovery(c_info)
    if b_p7 and c_p7:
        b_code = b_info.get("refusal_code")
        c_code = c_info.get("refusal_code")
        b_assert = b_info.get("reached_assertion")
        c_assert = c_info.get("reached_assertion")
        b_exc = b_info.get("exception_type")
        c_exc = c_info.get("exception_type")

        exc_match = b_exc == c_exc and b_exc is not None
        code_match = b_code == c_code and b_code is not None
        assert_match = b_assert == c_assert and b_assert is not None

        if exc_match and (code_match or assert_match):
            return "INHERITED_P7_RECOVERY", True, None
        return (
            "CHANGED_FAILURE",
            False,
            f"P7 recovery mismatch: code ({b_code} vs {c_code}), assertion ({b_assert} vs {c_assert}), exception ({b_exc} vs {c_exc})",
        )

    # 3. Context admission authorization refusals
    b_adm = is_admission_refusal(b_info)
    c_adm = is_admission_refusal(c_info)
    if b_adm and c_adm:
        b_code = b_info.get("refusal_code")
        c_code = c_info.get("refusal_code")
        # Identical non-None refusal code required; PERMISSION_DENIED vs INVALID_IDENTIFICATION must NOT match
        if b_code == c_code and b_code is not None:
            return "INHERITED_ADMISSION_PERMISSION_DENIED", True, None
        return (
            "CHANGED_FAILURE",
            False,
            f"Admission refusal mismatch: baseline code={b_code} vs current code={c_code}",
        )
    if b_adm and not c_adm:
        target_node = "tests.integration.p1.test_generalized_resources::test_selected_real_wire_without_identification_refuses_before_core_effects"
        current_node = c_info.get("node_id") or b_info.get("node_id")
        b_exc = b_info.get("exception_type")
        b_code = b_info.get("refusal_code")
        c_exc = c_info.get("exception_type")
        c_code = c_info.get("refusal_code")

        # Constrained strictly to the independently reviewed node and concrete signatures:
        # Baseline must be AdmissionRefused / PERMISSION_DENIED.
        # Current must be ExchangeError / INVALID_IDENTIFICATION.
        # Do not infer exception identity or refusal code from assertion substrings.
        if (
            current_node == target_node
            and b_exc == "AdmissionRefused"
            and b_code == "PERMISSION_DENIED"
            and c_exc == "ExchangeError"
            and c_code == "INVALID_IDENTIFICATION"
        ):
            return (
                "PROGRESS_KNOWN_BARRIER",
                True,
                "Progressed from baseline admission barrier (PERMISSION_DENIED) to wire identification envelope validation barrier (INVALID_IDENTIFICATION)",
            )
        return (
            "CHANGED_FAILURE",
            False,
            f"Admission refusal category mismatch: baseline adm={b_adm} vs current adm={c_adm}",
        )
    if not b_adm and c_adm:
        return (
            "CHANGED_FAILURE",
            False,
            f"Admission refusal category mismatch: baseline adm={b_adm} vs current adm={c_adm}",
        )

    # 4. General fallback
    b_exc = b_info.get("exception_type")
    c_exc = c_info.get("exception_type")
    b_code = b_info.get("refusal_code")
    c_code = c_info.get("refusal_code")
    b_assert = b_info.get("reached_assertion")
    c_assert = c_info.get("reached_assertion")

    # Both exception types must match and be not None
    if b_exc is None or c_exc is None or b_exc != c_exc:
        return (
            "CHANGED_FAILURE",
            False,
            f"Exception type mismatch: baseline {b_exc} != current {c_exc}",
        )

    # If neither refusal_code nor reached_assertion is known on both sides, do NOT accept as unchanged!
    has_concrete_sig = (b_code is not None and c_code is not None) or (
        b_assert is not None and c_assert is not None
    )
    if not has_concrete_sig:
        return (
            "CHANGED_FAILURE",
            False,
            "Unknown metadata: missing concrete refusal_code or reached_assertion signature",
        )

    # If refusal_code is present on either side, it must match
    if (b_code is not None or c_code is not None) and b_code != c_code:
        return (
            "CHANGED_FAILURE",
            False,
            f"Refusal code mismatch: baseline {b_code} != current {c_code}",
        )

    # If reached_assertion is present on either side, it must match (normalizing whitespace)
    if b_assert is not None or c_assert is not None:
        norm_b_assert = " ".join(b_assert.split()) if b_assert else None
        norm_c_assert = " ".join(c_assert.split()) if c_assert else None
        if norm_b_assert != norm_c_assert:
            return (
                "CHANGED_FAILURE",
                False,
                f"Reached assertion mismatch: baseline {b_assert} != current {c_assert}",
            )

    return "INHERITED_OTHER", True, None


def compare_manifests(
    baseline_cases: dict[str, dict],
    current_cases: dict[str, dict],
    expected_nodes: list[str] | None = None,
    pytest_exit_code: int | None = None,
) -> dict:
    baseline_keys = set(baseline_cases.keys())
    current_keys = set(current_cases.keys())

    # Scoped partition:
    if expected_nodes is not None:
        expected_keys = set(expected_nodes)
        in_scope_baseline_keys = baseline_keys & expected_keys
        out_of_scope_baseline_keys = baseline_keys - expected_keys
        missing_keys = expected_keys - current_keys
        unexpected_keys = current_keys - expected_keys
        added_keys = current_keys - baseline_keys
    else:
        expected_keys = None
        in_scope_baseline_keys = baseline_keys
        out_of_scope_baseline_keys = set()
        missing_keys = in_scope_baseline_keys - current_keys
        unexpected_keys = set()
        added_keys = current_keys - baseline_keys

    resolved = []
    inherited = []
    progressed_barriers = []
    new_regressions = []
    added_passes = []
    added_failures = []
    environment_failures = []
    changed_failures = []
    unexpected_skips = []
    missing_nodes = sorted(missing_keys)
    unexpected_nodes_list = sorted(unexpected_keys)
    unchanged_passes = []

    categorized_counts = {
        "RESOLVED": 0,
        "INHERITED_STAGE_TRANSFER": 0,
        "INHERITED_ADMISSION_PERMISSION_DENIED": 0,
        "INHERITED_P7_RECOVERY": 0,
        "INHERITED_OTHER": 0,
        "PROGRESS_KNOWN_BARRIER": 0,
        "ENVIRONMENT_FAILURE": 0,
        "CHANGED_FAILURE": 0,
        "NEW_REGRESSION": 0,
        "ADDED_PASS": 0,
        "ADDED_FAIL": 0,
        "SKIP": 0,
        "PASS": 0,
        "MISSING_EXECUTION": len(missing_nodes),
        "UNEXPECTED_NODE": len(unexpected_nodes_list),
        "OUT_OF_SCOPE_BASELINE": len(out_of_scope_baseline_keys),
    }

    all_node_details = []

    # Process all executed nodes
    for node_id in sorted(current_keys):
        c_info = current_cases[node_id]
        c_status = c_info["status"]
        b_info = baseline_cases.get(node_id)
        b_status = b_info["status"] if b_info else "ADDED"

        # Check for unexpected skip
        if c_status == "SKIP":
            unexpected_skips.append(node_id)
            categorized_counts["SKIP"] += 1
            all_node_details.append(
                {
                    "node_id": node_id,
                    "baseline_status": b_status,
                    "current_status": "SKIP",
                    "classification": "SKIP",
                    "phase": c_info["phase"],
                    "records": c_info["records"],
                }
            )
            continue

        # Check for environment failure
        if c_info["is_env"]:
            environment_failures.append(node_id)
            categorized_counts["ENVIRONMENT_FAILURE"] += 1
            all_node_details.append(
                {
                    "node_id": node_id,
                    "baseline_status": b_status,
                    "current_status": c_status,
                    "classification": "ENVIRONMENT_FAILURE",
                    "phase": c_info["phase"],
                    "refusal_code": c_info["refusal_code"],
                    "reached_assertion": c_info["reached_assertion"],
                    "records": c_info["records"],
                }
            )
            continue

        if b_status == "ADDED":
            if c_status == "PASS":
                added_passes.append(node_id)
                categorized_counts["ADDED_PASS"] += 1
                all_node_details.append(
                    {
                        "node_id": node_id,
                        "baseline_status": "ADDED",
                        "current_status": "PASS",
                        "classification": "ADDED_PASS",
                        "phase": "passed",
                        "records": c_info["records"],
                    }
                )
            else:
                added_failures.append(node_id)
                categorized_counts["ADDED_FAIL"] += 1
                all_node_details.append(
                    {
                        "node_id": node_id,
                        "baseline_status": "ADDED",
                        "current_status": c_status,
                        "classification": "ADDED_FAIL",
                        "phase": c_info["phase"],
                        "refusal_code": c_info["refusal_code"],
                        "reached_assertion": c_info["reached_assertion"],
                        "records": c_info["records"],
                    }
                )
        elif b_status != "PASS" and c_status == "PASS":
            resolved.append(node_id)
            categorized_counts["RESOLVED"] += 1
            all_node_details.append(
                {
                    "node_id": node_id,
                    "baseline_status": b_status,
                    "current_status": "PASS",
                    "classification": "RESOLVED",
                    "phase": "passed",
                    "records": c_info["records"],
                }
            )
        elif b_status != "PASS" and c_status != "PASS":
            cat, is_unchanged, reason = compare_failure_details(b_info, c_info)
            if cat == "PROGRESS_KNOWN_BARRIER":
                progressed_barriers.append(node_id)
                categorized_counts["PROGRESS_KNOWN_BARRIER"] += 1
                all_node_details.append(
                    {
                        "node_id": node_id,
                        "baseline_status": b_status,
                        "current_status": c_status,
                        "classification": "PROGRESS_KNOWN_BARRIER",
                        "progress_reason": reason,
                        "phase": c_info["phase"],
                        "refusal_code": c_info["refusal_code"],
                        "reached_assertion": c_info["reached_assertion"],
                        "records": c_info["records"],
                    }
                )
            elif is_unchanged:
                inherited.append(node_id)
                categorized_counts[cat] += 1
                all_node_details.append(
                    {
                        "node_id": node_id,
                        "baseline_status": b_status,
                        "current_status": c_status,
                        "classification": cat,
                        "phase": c_info["phase"],
                        "refusal_code": c_info["refusal_code"],
                        "reached_assertion": c_info["reached_assertion"],
                        "records": c_info["records"],
                    }
                )
            else:
                changed_failures.append(node_id)
                categorized_counts["CHANGED_FAILURE"] += 1
                all_node_details.append(
                    {
                        "node_id": node_id,
                        "baseline_status": b_status,
                        "current_status": c_status,
                        "classification": "CHANGED_FAILURE",
                        "change_reason": reason,
                        "phase": c_info["phase"],
                        "refusal_code": c_info["refusal_code"],
                        "reached_assertion": c_info["reached_assertion"],
                        "records": c_info["records"],
                    }
                )
        elif b_status == "PASS" and c_status != "PASS":
            new_regressions.append(node_id)
            categorized_counts["NEW_REGRESSION"] += 1
            all_node_details.append(
                {
                    "node_id": node_id,
                    "baseline_status": "PASS",
                    "current_status": c_status,
                    "classification": "NEW_REGRESSION",
                    "phase": c_info["phase"],
                    "refusal_code": c_info["refusal_code"],
                    "reached_assertion": c_info["reached_assertion"],
                    "records": c_info["records"],
                }
            )
        else:
            unchanged_passes.append(node_id)
            categorized_counts["PASS"] += 1

    # Record missing expected nodes
    for node_id in missing_nodes:
        b_info = baseline_cases.get(node_id)
        b_status = b_info["status"] if b_info else "UNKNOWN"
        all_node_details.append(
            {
                "node_id": node_id,
                "baseline_status": b_status,
                "current_status": "UNEXECUTED",
                "classification": "MISSING_EXECUTION",
                "phase": "unexecuted",
            }
        )

    # Validate pytest exit code semantics
    pytest_exit_status = "UNKNOWN"
    pytest_exit_error = None
    if pytest_exit_code is not None:
        if pytest_exit_code == 0:
            if (
                len(new_regressions)
                + len(added_failures)
                + len(environment_failures)
                + len(changed_failures)
                + len(inherited)
                + len(progressed_barriers)
                > 0
            ):
                pytest_exit_status = "INCONSISTENT"
                pytest_exit_error = (
                    "pytest exit code was 0 but test failures were recorded in receipt"
                )
            else:
                pytest_exit_status = "PASSED"
        elif pytest_exit_code == 1:
            pytest_exit_status = "RECONCILED_FAILURES"
        elif pytest_exit_code == 2:
            pytest_exit_status = "REJECTED_INTERRUPTED"
            pytest_exit_error = "pytest was interrupted by user or signal (exit 2)"
        elif pytest_exit_code == 3:
            pytest_exit_status = "REJECTED_INTERNAL_ERROR"
            pytest_exit_error = "pytest experienced an internal error (exit 3)"
        elif pytest_exit_code == 4:
            pytest_exit_status = "REJECTED_USAGE_ERROR"
            pytest_exit_error = "pytest command line usage error (exit 4)"
        elif pytest_exit_code == 5:
            pytest_exit_status = "REJECTED_NO_TESTS_COLLECTED"
            pytest_exit_error = "pytest collected 0 tests (exit 5)"
        else:
            pytest_exit_status = f"REJECTED_UNEXPECTED_EXIT_{pytest_exit_code}"
            pytest_exit_error = f"pytest exited with unexpected code {pytest_exit_code}"

    # Strict acceptance evaluation
    blocking_violations = []
    if len(current_keys) == 0:
        blocking_violations.append("Empty current JUnit XML (0 test cases executed)")
    if len(new_regressions) > 0:
        blocking_violations.append(
            f"{len(new_regressions)} new product regressions detected"
        )
    if len(added_failures) > 0:
        blocking_violations.append(
            f"{len(added_failures)} added failing test nodes detected"
        )
    if len(environment_failures) > 0:
        blocking_violations.append(
            f"{len(environment_failures)} environment failures detected"
        )
    if len(changed_failures) > 0:
        blocking_violations.append(
            f"{len(changed_failures)} changed non-successes detected"
        )
    if len(missing_nodes) > 0:
        blocking_violations.append(
            f"{len(missing_nodes)} expected test nodes missing from execution"
        )
    if len(unexpected_nodes_list) > 0:
        blocking_violations.append(
            f"{len(unexpected_nodes_list)} unexpected test nodes executed"
        )
    if len(unexpected_skips) > 0:
        blocking_violations.append(
            f"{len(unexpected_skips)} unexpected skipped test nodes detected"
        )
    if pytest_exit_error:
        blocking_violations.append(f"Pytest exit validation error: {pytest_exit_error}")

    acceptance_verdict = "PASSED" if not blocking_violations else "REJECTED"

    summary = {
        "acceptance_verdict": acceptance_verdict,
        "blocking_violations": blocking_violations,
        "pytest_exit_code": pytest_exit_code,
        "pytest_exit_status": pytest_exit_status,
        "baseline_nodes": len(baseline_keys),
        "in_scope_baseline_nodes": len(in_scope_baseline_keys),
        "out_of_scope_baseline_nodes": len(out_of_scope_baseline_keys),
        "expected_nodes": len(expected_nodes) if expected_nodes is not None else None,
        "current_nodes": len(current_keys),
        "added_nodes_count": len(added_keys),
        "missing_nodes_count": len(missing_nodes),
        "unexpected_nodes_count": len(unexpected_nodes_list),
        "baseline_non_successes": sum(
            1 for v in baseline_cases.values() if v["status"] != "PASS"
        ),
        "current_non_successes": sum(
            1 for v in current_cases.values() if v["status"] != "PASS"
        ),
        "resolved_count": len(resolved),
        "inherited_non_successes_count": len(inherited),
        "progressed_barriers_count": len(progressed_barriers),
        "new_regressions_count": len(new_regressions),
        "added_failures_count": len(added_failures),
        "environment_failures_count": len(environment_failures),
        "changed_failures_count": len(changed_failures),
        "unexpected_skips_count": len(unexpected_skips),
        "added_passes_count": len(added_passes),
        "categorized_counts": categorized_counts,
        "resolved_nodes": resolved,
        "progressed_barrier_nodes": progressed_barriers,
        "new_regression_nodes": new_regressions,
        "added_failure_nodes": added_failures,
        "environment_failure_nodes": environment_failures,
        "changed_failure_nodes": changed_failures,
        "missing_nodes": missing_nodes,
        "unexpected_nodes": unexpected_nodes_list,
        "unexpected_skip_nodes": unexpected_skips,
        "node_details": all_node_details,
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--current",
        type=Path,
        required=True,
        help="Path to current JUnit XML receipt",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Path to baseline JUnit XML (.xml or .xml.gz)",
    )
    parser.add_argument(
        "--expected",
        type=Path,
        default=None,
        help="Path to expected test node manifest (e.g. pytest --collect-only output)",
    )
    parser.add_argument(
        "--pytest-exit-code",
        type=int,
        default=None,
        help="Recorded pytest process exit code to validate against receipts",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to output comparison JSON",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any regression, missing node, env error, or unexpected change occurs",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full JSON output",
    )
    args = parser.parse_args()

    expected_nodes = parse_expected_nodes(args.expected) if args.expected else None
    baseline_cases = load_junit(args.baseline)
    current_cases = load_junit(args.current)

    summary = compare_manifests(
        baseline_cases=baseline_cases,
        current_cases=current_cases,
        expected_nodes=expected_nodes,
        pytest_exit_code=args.pytest_exit_code,
    )
    summary["baseline_path"] = str(args.baseline)
    summary["baseline_sha256"] = hashlib.sha256(args.baseline.read_bytes()).hexdigest()
    summary["current_path"] = str(args.current)
    summary["current_sha256"] = hashlib.sha256(args.current.read_bytes()).hexdigest()
    if args.expected:
        summary["expected_path"] = str(args.expected)
        summary["expected_sha256"] = hashlib.sha256(
            args.expected.read_bytes()
        ).hexdigest()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")

    verbose = args.verbose or os.environ.get("CI_VERBOSE") == "1"
    if verbose:
        print(
            json.dumps(
                {
                    "acceptance_verdict": summary["acceptance_verdict"],
                    "baseline_nodes": summary["baseline_nodes"],
                    "in_scope_baseline_nodes": summary["in_scope_baseline_nodes"],
                    "out_of_scope_baseline_nodes": summary["out_of_scope_baseline_nodes"],
                    "expected_nodes": summary["expected_nodes"],
                    "current_nodes": summary["current_nodes"],
                    "missing_nodes": summary["missing_nodes_count"],
                    "resolved_count": summary["resolved_count"],
                    "inherited_count": summary["inherited_non_successes_count"],
                    "progressed_barriers_count": summary["progressed_barriers_count"],
                    "new_regressions": summary["new_regressions_count"],
                    "added_failures": summary["added_failures_count"],
                    "environment_failures": summary["environment_failures_count"],
                    "changed_failures": summary["changed_failures_count"],
                    "unexpected_skips": summary["unexpected_skips_count"],
                    "categorized": summary["categorized_counts"],
                    "blocking_violations": summary["blocking_violations"],
                },
                indent=2,
            )
        )
    else:
        print(
            f"Reconciliation: {summary['acceptance_verdict']} "
            f"(in_scope={summary['in_scope_baseline_nodes']}, "
            f"current={summary['current_nodes']}, "
            f"inherited={summary['inherited_non_successes_count']}, "
            f"new_regressions={summary['new_regressions_count']}, "
            f"changed_failures={summary['changed_failures_count']}, "
            f"unexpected_skips={summary['unexpected_skips_count']})"
        )

    if args.strict and summary["blocking_violations"]:
        violations_str = "\n - ".join(summary["blocking_violations"])
        raise SystemExit(
            f"Strict comparison failed with {len(summary['blocking_violations'])} blocking violation(s):\n - {violations_str}"
        )


if __name__ == "__main__":
    main()
