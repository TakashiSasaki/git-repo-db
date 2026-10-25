"""Verify readable automatic Access CI receipts, preserving any failed outcome.

No artifact download, workflow dispatch, product execution or remote mutation.
Each JUnit lane is reported separately; overlapping lanes are never summed.
"""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from verify_development_receipt import (
    check,
    commit_identity,
    digest,
    indexed_payloads,
    log_views,
    recover_receipt,
    unique_json,
)


def verify_access(receipt, run, feature_commit, checkout_commit, base, expected_pr):
    files, index = indexed_payloads(receipt, flat=False)
    binding = unique_json(files["receipt-binding.json"])
    feature, feature_tree, _ = commit_identity(feature_commit)
    checkout, tree, parents = commit_identity(checkout_commit)
    check(
        run["head_sha"] == feature and run["event"] == "pull_request",
        "Access feature/event mismatch",
    )
    check(
        expected_pr in [pr["number"] for pr in run["pull_requests"]],
        "Access PR mismatch",
    )
    check(
        str(binding["run_id"]) == str(run["id"])
        and str(binding["run_attempt"]) == str(run["run_attempt"]),
        "Access run/attempt mismatch",
    )
    check(
        binding["head"] == checkout and parents == [base, feature],
        "Access actual checkout/parents mismatch",
    )
    check(tree == binding["tree"] == feature_tree, "Access actual tree mismatch")
    lanes = {}
    for name, raw in files.items():
        if not name.endswith(".xml"):
            continue
        cases = list(ET.fromstring(raw).iter("testcase"))
        failed = sum(case.find("failure") is not None for case in cases)
        errors = sum(case.find("error") is not None for case in cases)
        skipped = sum(case.find("skipped") is not None for case in cases)
        lanes[name] = {
            "cases": len(cases),
            "pass": len(cases) - failed - errors - skipped,
            "fail": failed,
            "error": errors,
            "skip": skipped,
        }
    executions = {}
    for name, raw in files.items():
        if name.endswith("execution.json"):
            data = unique_json(raw)
            executions[name] = {
                key: data[key]
                for key in ("command", "exit_code", "returncode", "cwd", "status")
                if key in data
            }
    return files, {
        "run_id": run["id"],
        "status": run["status"],
        "conclusion": run["conclusion"],
        "run_url": run["html_url"],
        "receipt_bytes": len(receipt),
        "receipt_sha256": digest(receipt),
        "indexed_payloads_verified": len(index),
        "feature": feature,
        "base": base,
        "checkout": checkout,
        "ordered_parents": parents,
        "effective_tree": tree,
        "junit_lanes_separate_overlapping": lanes,
        "execution_records": executions,
        "scope": "Available automatic Access evidence only. No Release acceptance or product runtime acceptance inferred from metadata or indexed receipt integrity.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, nargs="+", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--feature-commit", type=Path, required=True)
    parser.add_argument("--checkout-commit", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(not args.output.exists(), "use a new output directory")
    receipt, views = recover_receipt(log_views(args.logs))
    files, result = verify_access(
        receipt,
        unique_json(args.run.read_bytes()),
        unique_json(args.feature_commit.read_bytes()),
        unique_json(args.checkout_commit.read_bytes()),
        args.base,
        args.pr,
    )
    args.output.mkdir(parents=True)
    for name, raw in files.items():
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (args.output / "receipt.zip").write_bytes(receipt)
    result["actual_marker_views"] = views
    result["inputs"] = {
        str(path): {"bytes": path.stat().st_size, "sha256": digest(path.read_bytes())}
        for path in [*args.logs, args.run, args.feature_commit, args.checkout_commit]
    }
    (args.output / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
