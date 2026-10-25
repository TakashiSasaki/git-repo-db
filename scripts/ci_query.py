"""Query test execution summaries, failure indices, and diagnostic traces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_execution_summary(directory: Path) -> dict | None:
    directory = Path(directory)
    summary_path = directory / "execution-summary.json"
    if summary_path.is_file():
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    # Fallback to standard profile JSON
    candidates = list(directory.glob("*.json"))
    for candidate in sorted(candidates):
        if candidate.name in (
            "summary.json",
            "execution-summary.json",
            "failure-index.json",
        ):
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            if "profile_version" in data and "invocation_id" in data:
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def load_failure_index(directory: Path) -> dict | None:
    directory = Path(directory)
    index_path = directory / "failure-index.json"
    if index_path.is_file():
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return None


def query_summary(args: argparse.Namespace) -> int:
    summary = load_execution_summary(args.path)
    if summary is None:
        print(f"No execution summary found in {args.path}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        counts = summary.get("counts", {})
        reconcil = summary.get("reconciliation", {})
        print(f"Invocation:     {summary.get('invocation_id', 'unknown')}")
        print(f"Lane:           {summary.get('name', summary.get('lane', 'unknown'))}")
        print(f"Exit Code:      {summary.get('exit_code', -1)}")
        print(f"Wall Time:      {summary.get('wall_seconds', 0.0):.2f}s")
        print(f"Workers:        {summary.get('workers', 1)}")
        print(f"Passed/Failed:  {counts.get('passed', 0)} / {counts.get('failed', 0)}")
        print(f"Reconciliation: {reconcil.get('status', 'unknown')}")
    return 0


def query_failures(args: argparse.Namespace) -> int:
    index = load_failure_index(args.path)
    if index is None:
        # Check if execution summary reports zero failures
        summary = load_execution_summary(args.path)
        if summary and summary.get("counts", {}).get("failed", 0) == 0:
            if args.json:
                print(json.dumps({"failures": []}, indent=2))
            else:
                print("No test failures recorded.")
            return 0
        print(f"No failure index found in {args.path}", file=sys.stderr)
        return 1

    failures = index.get("failures", [])
    if args.new_only:
        failures = [
            f for f in failures if f.get("classification") != "INHERITED_KNOWN_FAILURE"
        ]

    if args.json:
        print(json.dumps({"count": len(failures), "failures": failures}, indent=2))
    else:
        print(f"Total matching failures: {len(failures)}")
        for f in failures:
            cls = f.get("classification", "FAILURE")
            node = f.get("nodeid", "unknown")
            msg = (
                f.get("message", "").splitlines()[0] if f.get("message") else "unknown"
            )
            print(f"- [{cls}] {node}: {msg}")
    return 0 if not failures else 1


def query_single_failure(args: argparse.Namespace) -> int:
    index = load_failure_index(args.path)
    if index is None:
        print(f"No failure index found in {args.path}", file=sys.stderr)
        return 1

    matches = [f for f in index.get("failures", []) if args.node in f.get("nodeid", "")]
    if not matches:
        print(f"No failure matching node '{args.node}' found.", file=sys.stderr)
        return 1

    f = matches[0]
    if args.json:
        print(json.dumps(f, indent=2))
    else:
        print(f"Node:           {f.get('nodeid')}")
        print(f"Classification: {f.get('classification')}")
        print(f"Phase:          {f.get('phase')}")
        print(f"Exception Type: {f.get('exception_type')}")
        print(f"Message:        {f.get('message')}")
        samples = f.get("sample_lines", [])
        if samples:
            print("\nTraceback Sample:")
            for line in samples:
                print(f"  {line}")
    return 0


def query_status(args: argparse.Namespace) -> int:
    summary = load_execution_summary(args.path)
    if summary is None:
        print("UNKNOWN: No summary found", file=sys.stderr)
        return 2
    exit_code = summary.get("exit_code", 1)
    if exit_code == 0:
        print("PASSED")
        return 0
    print(f"FAILED (exit code {exit_code})")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    sum_p = sub.add_parser("summary", help="Print compact execution summary")
    sum_p.add_argument(
        "path", type=Path, nargs="?", default=Path("artifacts/ci-profile")
    )
    sum_p.add_argument("--json", action="store_true", help="Output raw JSON")

    fail_p = sub.add_parser("failures", help="List failed test nodes")
    fail_p.add_argument(
        "path", type=Path, nargs="?", default=Path("artifacts/ci-profile")
    )
    fail_p.add_argument(
        "--new-only", action="store_true", help="Exclude inherited known failures"
    )
    fail_p.add_argument("--json", action="store_true", help="Output raw JSON")

    one_p = sub.add_parser(
        "failure", help="Inspect diagnostic traceback for a single node"
    )
    one_p.add_argument(
        "path", type=Path, nargs="?", default=Path("artifacts/ci-profile")
    )
    one_p.add_argument("--node", required=True, help="Pytest node ID or substring")
    one_p.add_argument("--json", action="store_true", help="Output raw JSON")

    stat_p = sub.add_parser("status", help="Print overall pass/fail status")
    stat_p.add_argument(
        "path", type=Path, nargs="?", default=Path("artifacts/ci-profile")
    )

    args = parser.parse_args(argv)
    if args.action == "summary":
        return query_summary(args)
    if args.action == "failures":
        return query_failures(args)
    if args.action == "failure":
        return query_single_failure(args)
    if args.action == "status":
        return query_status(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
