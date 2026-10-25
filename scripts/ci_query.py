"""Query test execution summaries, failure indices, and diagnostic traces."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import sys
import zipfile
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
        print(f"Error: No execution summary found in {args.path}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        counts = summary.get("counts", {})
        reconcil = summary.get("reconciliation", {})
        exit_code = summary.get("exit_code", -1)
        wall = summary.get("wall_seconds", 0.0)
        workers = summary.get("workers", 1)
        mode = summary.get("mode", "sequential")
        lane = summary.get("name", summary.get("lane", "unknown"))
        inv_id = summary.get("invocation_id", "unknown")

        print(f"Invocation:     {inv_id}")
        print(f"Lane:           {lane} ({mode}, {workers}w)")
        print(f"Exit Code:      {exit_code}")
        print(f"Wall Time:      {wall:.2f}s")
        print(
            f"Tests:          {counts.get('total', 0)} total | {counts.get('passed', 0)} passed | "
            f"{counts.get('failed', 0)} failed | {counts.get('error', 0)} error | "
            f"{counts.get('skipped', 0)} skipped | {counts.get('inherited', 0)} inherited | "
            f"{counts.get('unexecuted', 0)} unexecuted"
        )
        print(f"Reconciliation: {reconcil.get('status', 'unknown')}")
        artifacts = summary.get("artifacts", {})
        if artifacts:
            log_ref = artifacts.get("log", "")
            if log_ref:
                print(f"Log:            {log_ref}")

    consistent = summary.get("reconciliation", {}).get("consistent", True)
    exit_code = summary.get("exit_code", -1)
    return (
        0 if (exit_code == 0 and consistent) else (1 if exit_code == 0 else exit_code)
    )


def query_failures(args: argparse.Namespace) -> int:
    index = load_failure_index(args.path)
    if index is None:
        # Check if execution summary reports zero failures and valid completion
        summary = load_execution_summary(args.path)
        if (
            summary
            and summary.get("exit_code") == 0
            and summary.get("counts", {}).get("failed", 0) == 0
            and summary.get("counts", {}).get("error", 0) == 0
            and summary.get("counts", {}).get("unexecuted", 0) == 0
            and summary.get("reconciliation", {}).get("consistent", True)
        ):
            if args.json:
                print(json.dumps({"count": 0, "failures": []}, indent=2))
            else:
                print("No test failures recorded.")
            return 0
        print(
            f"Error: No failure index found in {args.path} and execution was not verified clean.",
            file=sys.stderr,
        )
        return 2

    failures = index.get("failures", [])
    if args.new_only:
        # Only exclude verified unchanged inherited failures
        failures = [
            f
            for f in failures
            if not (
                f.get("is_inherited")
                or f.get("classification", "").startswith("INHERITED_")
                or f.get("classification")
                in ("STAGE_TRANSFER", "ADMISSION_PERMISSION_DENIED")
            )
        ]

    total_matching = len(failures)
    limit = (
        args.limit
        if getattr(args, "limit", None) is not None and args.limit > 0
        else None
    )
    display_failures = failures[:limit] if limit else failures

    if args.json:
        print(
            json.dumps(
                {
                    "count": len(display_failures),
                    "total_matching": total_matching,
                    "failures": display_failures,
                },
                indent=2,
            )
        )
    else:
        print(f"Total matching failures: {total_matching}")
        for f in display_failures:
            cls = f.get("classification", "FAILURE")
            node = f.get("nodeid", "unknown")
            msg = (
                f.get("message", "").splitlines()[0] if f.get("message") else "unknown"
            )
            print(f"- [{cls}] {node}: {msg}")
        if limit and total_matching > len(display_failures):
            print(
                f"... and {total_matching - len(display_failures)} more failure(s). Use --limit 0 to view all."
            )
    return 0 if total_matching == 0 else 1


def query_single_failure(args: argparse.Namespace) -> int:
    index = load_failure_index(args.path)
    if index is None:
        print(f"Error: No failure index found in {args.path}", file=sys.stderr)
        return 2

    failures = index.get("failures", [])
    # Exact match has priority
    exact = [f for f in failures if f.get("nodeid") == args.node]
    if exact:
        matches = exact
    else:
        matches = [f for f in failures if args.node in f.get("nodeid", "")]

    if not matches:
        print(f"Error: No failure matching node '{args.node}' found.", file=sys.stderr)
        return 2

    if len(matches) > 1:
        print(
            f"Error: Ambiguous query '{args.node}' matches {len(matches)} nodes:",
            file=sys.stderr,
        )
        for m in matches[:5]:
            print(f"  - {m.get('nodeid')}", file=sys.stderr)
        if len(matches) > 5:
            print(f"  ... and {len(matches) - 5} more", file=sys.stderr)
        print("Please specify the exact node ID.", file=sys.stderr)
        return 2

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
            limit = None if getattr(args, "full", False) else 15
            print("\nTraceback Sample:")
            for line in samples if limit is None else samples[:limit]:
                print(f"  {line}")
            if limit is not None and len(samples) > limit:
                print(
                    f"  ... and {len(samples) - limit} more line(s). Use --full to see complete sample."
                )
    return 0


def query_status(args: argparse.Namespace) -> int:
    summary = load_execution_summary(args.path)
    if summary is None:
        print("UNKNOWN: No summary found", file=sys.stderr)
        return 2
    exit_code = summary.get("exit_code", 1)
    consistent = summary.get("reconciliation", {}).get("consistent", True)
    if exit_code == 0 and consistent:
        print("PASSED")
        return 0
    status = summary.get("reconciliation", {}).get("status", f"exit code {exit_code}")
    print(f"FAILED ({status})")
    return 1 if exit_code == 0 else exit_code


def filter_log(args: argparse.Namespace) -> int:
    """Filter out base64 CI receipt lines from log stream or file."""
    if args.log_path and str(args.log_path) != "-":
        with open(args.log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    for line in lines:
        if line.startswith("CI_RECEIPTS_DATA_V1 "):
            continue
        sys.stdout.write(line)
    return 0


def extract_receipt(args: argparse.Namespace) -> int:
    """Extract and decode base64 CI receipt archive into destination directory."""
    if args.log_path and str(args.log_path) != "-":
        with open(args.log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    chunks = []
    in_receipt = False
    expected_digest = None

    for line in lines:
        line_s = line.strip()
        if line_s.startswith("CI_RECEIPTS_BEGIN_V1 "):
            parts = line_s.split()
            if len(parts) >= 2:
                expected_digest = parts[1]
            in_receipt = True
            chunks = []
        elif line_s.startswith("CI_RECEIPTS_END_V1 "):
            in_receipt = False
            break
        elif in_receipt and line_s.startswith("CI_RECEIPTS_DATA_V1 "):
            chunks.append(line_s[len("CI_RECEIPTS_DATA_V1 ") :])

    if not chunks:
        print("Error: No CI receipt data found in log", file=sys.stderr)
        return 2

    raw_b64 = "".join(chunks)
    try:
        body = base64.b64decode(raw_b64, validate=True)
    except Exception as e:
        print(f"Error decoding base64 receipt: {e}", file=sys.stderr)
        return 2

    if expected_digest:
        actual_digest = hashlib.sha256(body).hexdigest()
        if actual_digest != expected_digest:
            print(
                f"Error: Digest mismatch: expected {expected_digest}, got {actual_digest}",
                file=sys.stderr,
            )
            return 2

    args.dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(body), "r") as zf:
        zf.extractall(args.dest)
        extracted = zf.namelist()

    print(
        f"Successfully extracted {len(extracted)} receipt file(s) to {args.dest} (digest: {expected_digest})"
    )
    return 0


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
    fail_p.add_argument(
        "--limit", type=int, default=20, help="Maximum failures to display (0 for all)"
    )
    fail_p.add_argument("--json", action="store_true", help="Output raw JSON")

    one_p = sub.add_parser(
        "failure", help="Inspect diagnostic traceback for a single node"
    )
    one_p.add_argument(
        "path", type=Path, nargs="?", default=Path("artifacts/ci-profile")
    )
    one_p.add_argument("--node", required=True, help="Pytest node ID or substring")
    one_p.add_argument(
        "--full", action="store_true", help="Display complete traceback sample"
    )
    one_p.add_argument("--json", action="store_true", help="Output raw JSON")

    stat_p = sub.add_parser("status", help="Print overall pass/fail status")
    stat_p.add_argument(
        "path", type=Path, nargs="?", default=Path("artifacts/ci-profile")
    )

    filt_p = sub.add_parser(
        "filter-log", help="Filter out base64 CI receipts from log for clean viewing"
    )
    filt_p.add_argument(
        "log_path", type=Path, nargs="?", help="Path to log file (or stdin if omitted)"
    )

    ext_p = sub.add_parser(
        "extract-receipt", help="Extract and decode base64 CI receipts into a directory"
    )
    ext_p.add_argument(
        "log_path", type=Path, help="Path to log file containing CI_RECEIPTS"
    )
    ext_p.add_argument(
        "--dest",
        type=Path,
        required=True,
        help="Destination directory to unpack receipts",
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
    if args.action == "filter-log":
        return filter_log(args)
    if args.action == "extract-receipt":
        return extract_receipt(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
