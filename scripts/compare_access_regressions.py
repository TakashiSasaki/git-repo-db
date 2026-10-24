"""Mechanically compare broad regression execution against baseline #154 manifest.

Classifies every node:
- RESOLVED: Failed in baseline #154, now passing.
- INHERITED_STAGE_TRANSFER: Transfer stage fences or unsupported stage refusals.
- INHERITED_ADMISSION_PERMISSION_DENIED: Context admission authorization refusals.
- INHERITED_P7_RECOVERY: P7 recovery context admission refusals.
- ENVIRONMENT: Missing executable or environment configuration.
- ADDED_PASS: New test nodes added since baseline #154 that pass.
- PASS: Existing passing test nodes that continue passing.
- NEW_REGRESSION: Previously passing tests that now fail (STRICTLY FAILS CI).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = (
    ROOT
    / "docs/implementation/evidence/adr0031-i6b-m01-m02-20261023/source-full-final/ordinary.xml.gz"
)


def load_junit(path: Path) -> dict[tuple[str, str], dict]:
    is_gz = str(path).endswith(".gz")
    opener = gzip.open if is_gz else open
    with opener(path, "rt", encoding="utf-8") as f:
        tree = ET.parse(f)
    cases = {}
    for tc in tree.findall(".//testcase"):
        c = tc.get("classname", "")
        n = tc.get("name", "")
        failure = tc.find("failure")
        error = tc.find("error")
        elem = failure if failure is not None else error
        status = "PASS" if elem is None else elem.tag.upper()
        msg = elem.get("message", "") if elem is not None else ""
        text = elem.text or "" if elem is not None else ""
        phase = (
            "setup"
            if elem is not None and elem.tag == "error"
            else ("call" if elem is not None else "passed")
        )
        if "failed on teardown" in msg:
            phase = "teardown"
        cases[(c, n)] = {
            "status": status,
            "phase": phase,
            "message": msg,
            "text": text,
        }
    return cases


def classify_non_success(
    key: tuple[str, str], node_data: dict, in_baseline: bool
) -> tuple[str, str | None, str | None]:
    c, n = key
    text = node_data.get("text", "")
    msg = node_data.get("message", "")

    # Extract exception/refusal code
    refusal_code = None
    refusal_match = re.search(
        r"AdmissionRefused\([\"']([^\"']+)[\"']|I2_([A-Z_]+)_UNSUPPORTED|UnsupportedResourceStage\([\"']([^\"']+)[\"']|code\s*=\s*[\"']([^\"']+)[\"']",
        text or msg,
    )
    if refusal_match:
        refusal_code = next((g for g in refusal_match.groups() if g is not None), None)
    elif "PERMISSION_DENIED" in (text or msg):
        refusal_code = "PERMISSION_DENIED"
    elif "INVALID_IDENTIFICATION" in (text or msg):
        refusal_code = "INVALID_IDENTIFICATION"
    elif "FileNotFoundError" in (text or msg):
        refusal_code = "FILE_NOT_FOUND"

    # Extract reached assertion where observable
    assertion = None
    assert_match = re.search(r"assert\s+[^\n]+", text)
    if assert_match:
        assertion = assert_match.group(0).strip()
    elif msg:
        assertion = msg.splitlines()[0][:120].strip()

    # Classification
    if "repo-catalog" in text and "FileNotFoundError" in text:
        cat = "ENVIRONMENT_MISSING_EXECUTABLE"
    elif "Run scripts/prepare_wheelhouse.py" in text:
        cat = "ENVIRONMENT_UNPREPARED_WHEELHOUSE"
    elif (
        "There was a problem with the editor" in text
        or "Author identity unknown" in text
    ):
        cat = "ENVIRONMENT_GIT_CONFIG"
    elif (
        "i2_transfer_stage_fence" in text
        or "i2_transfer_report_stage_fence" in text
        or "i2_transfer_stage_fence" in msg
    ):
        cat = "INHERITED_STAGE_TRANSFER"
    elif (
        "UnsupportedResourceStage" in text
        or "I2_TRANSFER_UNSUPPORTED" in text
        or "UnsupportedResourceStage" in msg
    ):
        cat = "INHERITED_STAGE_TRANSFER"
    elif "test_transfer_reports_never_shrunk_or_mixed" in n:
        cat = "INHERITED_STAGE_TRANSFER"
    elif "p7" in c or "Context admission error: PERMISSION_DENIED" in text:
        cat = "INHERITED_P7_RECOVERY"
    elif (
        "PERMISSION_DENIED" in text
        or "PERMISSION_DENIED" in msg
        or refusal_code in ("PERMISSION_DENIED", "INVALID_IDENTIFICATION")
    ):
        cat = "INHERITED_ADMISSION_PERMISSION_DENIED"
    elif not in_baseline:
        cat = "NEW_REGRESSION"
    else:
        cat = "INHERITED_OTHER"

    return cat, refusal_code, assertion


def compare_manifests(
    baseline_cases: dict[tuple[str, str], dict],
    current_cases: dict[tuple[str, str], dict],
) -> dict:
    baseline_keys = set(baseline_cases.keys())
    current_keys = set(current_cases.keys())

    added_keys = current_keys - baseline_keys
    removed_keys = baseline_keys - current_keys
    common_keys = baseline_keys & current_keys

    resolved = []
    inherited = []
    new_regressions = []
    added_passes = []
    added_failures = []
    unchanged_passes = []

    categorized_counts = {
        "RESOLVED": 0,
        "INHERITED_STAGE_TRANSFER": 0,
        "INHERITED_ADMISSION_PERMISSION_DENIED": 0,
        "INHERITED_P7_RECOVERY": 0,
        "ENVIRONMENT": 0,
        "NEW_REGRESSION": 0,
        "ADDED_PASS": 0,
        "ADDED_FAIL": 0,
        "PASS": 0,
    }

    all_node_details = []

    for key in sorted(common_keys):
        b_info = baseline_cases[key]
        c_info = current_cases[key]
        b_status = b_info["status"]
        c_status = c_info["status"]
        node_id = f"{key[0]}::{key[1]}"

        if b_status != "PASS" and c_status == "PASS":
            resolved.append(node_id)
            categorized_counts["RESOLVED"] += 1
            all_node_details.append(
                {
                    "node_id": node_id,
                    "baseline_status": b_status,
                    "current_status": "PASS",
                    "classification": "RESOLVED",
                    "phase": "passed",
                }
            )
        elif b_status != "PASS" and c_status != "PASS":
            cat, code, assertion = classify_non_success(key, c_info, in_baseline=True)
            inherited.append(node_id)
            if cat.startswith("INHERITED_STAGE_TRANSFER"):
                categorized_counts["INHERITED_STAGE_TRANSFER"] += 1
            elif cat.startswith("INHERITED_ADMISSION"):
                categorized_counts["INHERITED_ADMISSION_PERMISSION_DENIED"] += 1
            elif cat.startswith("INHERITED_P7"):
                categorized_counts["INHERITED_P7_RECOVERY"] += 1
            elif cat.startswith("ENVIRONMENT"):
                categorized_counts["ENVIRONMENT"] += 1
            else:
                categorized_counts[cat] = categorized_counts.get(cat, 0) + 1

            all_node_details.append(
                {
                    "node_id": node_id,
                    "baseline_status": b_status,
                    "current_status": c_status,
                    "classification": cat,
                    "phase": c_info["phase"],
                    "refusal_code": code,
                    "reached_assertion": assertion,
                }
            )
        elif b_status == "PASS" and c_status != "PASS":
            cat, code, assertion = classify_non_success(key, c_info, in_baseline=True)
            if cat.startswith("ENVIRONMENT"):
                categorized_counts["ENVIRONMENT"] += 1
                all_node_details.append(
                    {
                        "node_id": node_id,
                        "baseline_status": "PASS",
                        "current_status": c_status,
                        "classification": cat,
                        "phase": c_info["phase"],
                        "refusal_code": code,
                        "reached_assertion": assertion,
                    }
                )
            else:
                new_regressions.append(node_id)
                categorized_counts["NEW_REGRESSION"] += 1
                all_node_details.append(
                    {
                        "node_id": node_id,
                        "baseline_status": "PASS",
                        "current_status": c_status,
                        "classification": "NEW_REGRESSION",
                        "phase": c_info["phase"],
                        "refusal_code": code,
                        "reached_assertion": assertion,
                    }
                )
        else:
            unchanged_passes.append(node_id)
            categorized_counts["PASS"] += 1

    for key in sorted(added_keys):
        c_info = current_cases[key]
        c_status = c_info["status"]
        node_id = f"{key[0]}::{key[1]}"
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
                }
            )
        else:
            cat, code, assertion = classify_non_success(key, c_info, in_baseline=False)
            added_failures.append(node_id)
            categorized_counts["ADDED_FAIL"] += 1
            all_node_details.append(
                {
                    "node_id": node_id,
                    "baseline_status": "ADDED",
                    "current_status": c_status,
                    "classification": "ADDED_FAIL",
                    "phase": c_info["phase"],
                    "refusal_code": code,
                    "reached_assertion": assertion,
                }
            )

    summary = {
        "baseline_nodes": len(baseline_keys),
        "current_nodes": len(current_keys),
        "added_nodes_count": len(added_keys),
        "removed_nodes_count": len(removed_keys),
        "baseline_non_successes": sum(
            1 for v in baseline_cases.values() if v["status"] != "PASS"
        ),
        "current_non_successes": sum(
            1 for v in current_cases.values() if v["status"] != "PASS"
        ),
        "resolved_count": len(resolved),
        "inherited_non_successes_count": len(inherited),
        "new_regressions_count": len(new_regressions),
        "added_passes_count": len(added_passes),
        "categorized_counts": categorized_counts,
        "resolved_nodes": resolved,
        "new_regression_nodes": new_regressions,
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
        "--output",
        type=Path,
        required=True,
        help="Path to output comparison JSON",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any NEW_REGRESSION is detected",
    )
    args = parser.parse_args()

    baseline_cases = load_junit(args.baseline)
    current_cases = load_junit(args.current)

    summary = compare_manifests(baseline_cases, current_cases)
    summary["baseline_path"] = str(args.baseline)
    summary["baseline_sha256"] = hashlib.sha256(args.baseline.read_bytes()).hexdigest()
    summary["current_path"] = str(args.current)
    summary["current_sha256"] = hashlib.sha256(args.current.read_bytes()).hexdigest()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")

    print(
        json.dumps(
            {
                "baseline_nodes": summary["baseline_nodes"],
                "current_nodes": summary["current_nodes"],
                "baseline_non_successes": summary["baseline_non_successes"],
                "current_non_successes": summary["current_non_successes"],
                "resolved_count": summary["resolved_count"],
                "inherited_count": summary["inherited_non_successes_count"],
                "new_regressions": summary["new_regressions_count"],
                "categorized": summary["categorized_counts"],
            },
            indent=2,
        )
    )

    if args.strict and summary["new_regressions_count"] > 0:
        raise SystemExit(
            f"Comparison failed: {summary['new_regressions_count']} new product regressions detected!"
        )


if __name__ == "__main__":
    main()
