"""Query test execution summaries, failure indices, and diagnostic traces."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.ci_execute import extract_receipt_archive
except ImportError:
    from ci_execute import extract_receipt_archive


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
    if getattr(args, "log_path", None) and str(args.log_path) != "-":
        log_path = Path(args.log_path)
        if not log_path.is_file():
            print(f"Error: Log file not found: {log_path}", file=sys.stderr)
            return 2
        in_stream = open(log_path, "r", encoding="utf-8", errors="replace")
        close_in = True
    else:
        in_stream = sys.stdin
        close_in = False

    out_path = getattr(args, "output", None)
    if out_path and str(out_path) != "-":
        out_file = Path(out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_stream = open(out_file, "w", encoding="utf-8")
        close_out = True
    else:
        out_stream = sys.stdout
        close_out = False

    pattern_data = re.compile(
        r"^\ufeff?(?:\d{4}-\d\d-\d\dT\S+ )?CI_RECEIPTS_DATA_V1\s+[A-Za-z0-9+/=]+"
    )

    try:
        for line in in_stream:
            if pattern_data.match(line):
                continue
            out_stream.write(line)
    finally:
        if close_in:
            in_stream.close()
        if close_out:
            out_stream.close()
    return 0


def extract_receipt(args: argparse.Namespace) -> int:
    """Extract and decode base64 CI receipt archive into destination directory."""
    if not args.dest:
        print("Error: Destination directory is required (-o / --dest)", file=sys.stderr)
        return 2

    log_path = getattr(args, "log_path", None)
    if log_path and str(log_path) != "-":
        log_file = Path(log_path)
        if not log_file.is_file():
            print(f"Error: Log file not found: {log_file}", file=sys.stderr)
            return 2
        source = log_file
    else:
        source = sys.stdin

    target_digest = getattr(args, "digest", None)
    try:
        files = extract_receipt_archive(source, args.dest, target_digest=target_digest)
    except Exception as err:
        print(f"Error extracting receipt: {err}", file=sys.stderr)
        return 2

    digest_info = f" (digest: {target_digest})" if target_digest else ""
    print(
        f"Successfully extracted {len(files)} receipt file(s) to {args.dest}{digest_info}"
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
    filt_p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Destination file to write filtered log (stdout if omitted)",
    )

    ext_p = sub.add_parser(
        "extract-receipt", help="Extract and decode base64 CI receipts into a directory"
    )
    ext_p.add_argument(
        "log_path",
        type=Path,
        nargs="?",
        help="Path to log file containing CI_RECEIPTS (or stdin if omitted)",
    )
    ext_p.add_argument(
        "-o",
        "--output",
        "--dest",
        dest="dest",
        type=Path,
        required=True,
        help="Destination directory to unpack receipts",
    )
    ext_p.add_argument(
        "--digest",
        type=str,
        default=None,
        help="Explicit SHA-256 digest to select when multiple candidate bundles are present",
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
