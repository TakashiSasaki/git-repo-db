"""Query test execution summaries, failure indices, and diagnostic traces."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.ci_execute import extract_receipt_archive
    from scripts.ci_profile import terminal_excerpt
except ImportError:
    from ci_execute import extract_receipt_archive
    from ci_profile import terminal_excerpt


def interval_union_seconds(intervals):
    """Elapsed coverage, not summed concurrent invocation/worker time."""
    if not intervals:
        return None
    total = 0.0
    start, end = sorted(intervals)[0]
    for left, right in sorted(intervals)[1:]:
        if left > end:
            total += (end - start).total_seconds()
            start, end = left, right
        else:
            end = max(end, right)
    return total + (end - start).total_seconds()


def timing_report(paths):
    """Read existing profiles, including failed/open checkpoints; never infer work."""
    records = {}
    for path in paths:
        path = Path(path)
        directory = path / "invocations"
        candidates = (
            [path]
            if path.is_file()
            else sorted((directory if directory.is_dir() else path).glob("*.json"))
        )
        if not candidates:
            raise ValueError(f"No profile candidates at {path}")
        for candidate in candidates:
            data = json.loads(candidate.read_text())
            if "profile_version" not in data or "invocation_id" not in data:
                continue
            key = data["invocation_id"]
            if key in records and records[key] != data:
                raise ValueError(f"Conflicting copies of invocation {key}")
            records[key] = data
    if not records:
        raise ValueError("No invocation profiles found")

    def seconds(value):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError("Invalid elapsed duration")
        if not math.isfinite(value) or value < 0:
            raise ValueError("Invalid elapsed duration")
        return value

    def timestamp(value):
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("Timing requires timezone-aware timestamps")
        return result

    rows, intervals = [], []
    for key, data in sorted(records.items()):
        timing = data.get("timing", {})
        phases = timing.get("phases", [])
        command = [phase for phase in phases if phase["name"] == "command"]
        if len(command) > 1:
            raise ValueError(f"Duplicate command phase in {key}")
        measured = command[0] if command else ({} if timing else data)
        interval = None
        if measured.get("started_at") and measured.get("completed_at"):
            interval = tuple(
                timestamp(measured[field]) for field in ("started_at", "completed_at")
            )
            if interval[1] < interval[0]:
                raise ValueError(f"Wall clock reversed in {key}")
            intervals.append(interval)
        cumulative = None
        if data.get("journal"):
            # Old non-test command profiles used wall time as this fallback.
            # Do not call that fallback measured test work.
            cumulative = seconds(data.get("cumulative_test_seconds"))
        elif data.get("junit", {}).get("tests"):
            values = [seconds(test.get("seconds")) for test in data["junit"]["tests"]]
            if all(value is not None for value in values):
                cumulative = sum(values)
        rows.append(
            {
                "invocation_id": key,
                "name": data.get("name"),
                "task_id": timing.get("task_id"),
                "session_id": timing.get("session_id"),
                "parent_invocation_id": timing.get("parent_invocation_id"),
                "kind": timing.get("kind", "unclassified"),
                "status": timing.get("status", "legacy"),
                "exit_code": data.get("exit_code"),
                "started_at": measured.get("started_at"),
                "completed_at": measured.get("completed_at"),
                "interval_scope": "command" if command else "legacy_command_and_wait",
                "recorded_wall_seconds": seconds(data.get("wall_seconds")),
                "command_seconds": seconds(command[0].get("elapsed_seconds"))
                if command
                else None,
                "cumulative_test_seconds": cumulative,
                "phases": phases,
                "interval_available": interval is not None,
            }
        )

    def known_sum(field):
        values = [row[field] for row in rows if row[field] is not None]
        return sum(values) if values else None

    return {
        "invocations": rows,
        "invocation_count": len(rows),
        "missing_interval_count": sum(not row["interval_available"] for row in rows),
        "recorded_wall_seconds_sum": known_sum("recorded_wall_seconds"),
        "command_seconds_sum": known_sum("command_seconds"),
        "command_duration_missing_count": sum(
            row["command_seconds"] is None for row in rows
        ),
        "cumulative_test_seconds_sum": known_sum("cumulative_test_seconds"),
        "cumulative_test_duration_missing_count": sum(
            row["cumulative_test_seconds"] is None for row in rows
        ),
        "interval_union_seconds": interval_union_seconds(intervals),
        "observed_span_seconds": (
            max(end for _, end in intervals) - min(start for start, _ in intervals)
        ).total_seconds()
        if intervals
        else None,
        "active_work_share": None,
        "limitations": [
            "Observed span includes idle gaps; task/session labels are associations, not active work windows.",
            "Missing/open intervals and unprofiled commands have unknown cost, not zero cost.",
            "Legacy intervals may include resource wait; new intervals cover only the child command.",
            "Intervals use wall clocks; elapsed durations use monotonic clocks in new profiles. Compare only synchronized hosts without clock jumps.",
            "Nested runner commands may include profiled children; do not add nested parent and child durations as independent work.",
        ],
    }


def query_timing(args):
    try:
        result = timing_report(args.paths)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


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
            cls = terminal_excerpt(f.get("classification", "FAILURE"), 80)
            node = terminal_excerpt(f.get("nodeid", "unknown"), first_line=True)
            msg = terminal_excerpt(f.get("message") or "unknown", first_line=True)
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
        print(
            f"Error: No failure matching node '{terminal_excerpt(args.node)}' found.",
            file=sys.stderr,
        )
        return 2

    if len(matches) > 1:
        print(
            f"Error: Ambiguous query '{args.node}' matches {len(matches)} nodes:",
            file=sys.stderr,
        )
        for m in matches[:5]:
            print(
                f"  - {terminal_excerpt(m.get('nodeid'), first_line=True)}",
                file=sys.stderr,
            )
        if len(matches) > 5:
            print(f"  ... and {len(matches) - 5} more", file=sys.stderr)
        print("Please specify the exact node ID.", file=sys.stderr)
        return 2

    f = matches[0]
    if args.json:
        print(json.dumps(f, indent=2))
    else:
        full = getattr(args, "full", False)
        shortened = False

        def display(value, limit=240):
            nonlocal shortened
            original = str(value)
            result = original if full else terminal_excerpt(original, limit)
            shortened |= result != original
            return result

        print(f"Node:           {display(f.get('nodeid'))}")
        print(f"Classification: {display(f.get('classification'), 80)}")
        print(f"Phase:          {display(f.get('phase'), 80)}")
        print(f"Exception Type: {display(f.get('exception_type'), 120)}")
        print(f"Message:        {display(f.get('message'), 1024)}")
        samples = f.get("sample_lines", [])
        if samples:
            limit = None if getattr(args, "full", False) else 15
            print("\nTraceback Sample:")
            for line in samples if limit is None else samples[:limit]:
                print(f"  {display(line, 160)}")
            if limit is not None and len(samples) > limit:
                print(
                    f"  ... and {len(samples) - limit} more line(s). Use --full to see complete sample."
                )
        if shortened:
            print("Text excerpts shortened; use --full or --json for saved detail.")
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

    timing_p = sub.add_parser(
        "timing",
        help="Summarize all retained invocation timings without double-counting overlaps",
    )
    timing_p.add_argument("paths", type=Path, nargs="+")

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
        "--full",
        action="store_true",
        help="Display complete message and traceback sample (may be large)",
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
    if args.action == "timing":
        return query_timing(args)
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
