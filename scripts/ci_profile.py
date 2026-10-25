"""Run a CI command without hiding its exit status; summarize standard JUnit and journal."""

import argparse
import hashlib
import json
import math
import os
import platform
import re
import sqlite3
import statistics
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import ci_journal, resource_scheduler  # noqa: E402


def junit(path):
    root = ET.parse(path).getroot()
    tests = []
    files = {}
    for case in root.iter("testcase"):
        parts = case.get("classname", "unknown").split(".")
        name, classes = case.get("file"), []
        if not name:
            for end in range(len(parts), 0, -1):
                candidate = "/".join(parts[:end]) + ".py"
                if (ROOT / candidate).is_file():
                    name, classes = candidate, parts[end:]
                    break
        name = name or "/".join(parts) + ".py"
        status = next(
            (
                kind
                for kind in ("failure", "error", "skipped")
                if case.find(kind) is not None
            ),
            "passed",
        )
        failure_elem = next(
            (
                case.find(k)
                for k in ("failure", "error", "skipped")
                if case.find(k) is not None
            ),
            None,
        )
        details = None
        if failure_elem is not None:
            details = {
                "type": failure_elem.get("type", ""),
                "message": failure_elem.get("message", ""),
                "text": (failure_elem.text or "").strip(),
            }
        row = dict(
            file=name,
            name=case.get("name"),
            seconds=float(case.get("time", 0)),
            status=status,
            nodeid="::".join([name, *classes, case.get("name", "")]),
        )
        if details:
            row["details"] = details
        if not math.isfinite(row["seconds"]) or row["seconds"] < 0:
            raise ValueError("Invalid JUnit duration")
        tests.append(row)
        summary = files.setdefault(
            name, dict(file=name, seconds=0.0, tests=0, failures=0, skipped=0)
        )
        summary["seconds"] += row["seconds"]
        summary["tests"] += 1
        summary["failures"] += status in ("failure", "error")
        summary["skipped"] += status == "skipped"
    return dict(
        tests=tests,
        files=sorted(files.values(), key=lambda row: -row["seconds"]),
        count=len(tests),
    )


def runtime():
    db = sqlite3.connect(":memory:")
    try:
        sqlite_source_id = db.execute("SELECT sqlite_source_id()").fetchone()[0]
    finally:
        db.close()
    cpu = Path("/sys/fs/cgroup/cpu.max")
    git_sha = (
        os.environ.get("GITHUB_SHA")
        or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    )
    tree_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    tracked_changes = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            text=True,
        )
    )
    try:
        git_ver = subprocess.check_output(["git", "--version"], text=True).strip()
    except Exception:
        git_ver = "unknown"
    return dict(
        python=platform.python_version(),
        executable=sys.executable,
        sqlite_source_id=sqlite_source_id,
        sqlite=sqlite3.sqlite_version,
        git=git_ver,
        cpu_count=os.cpu_count(),
        affinity=len(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else None,
        cpu_quota=cpu.read_text().strip() if cpu.exists() else None,
        commit_sha=git_sha,
        tree_sha=tree_sha,
        run_id=os.environ.get("GITHUB_RUN_ID"),
        run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),
        feature_sha=os.environ.get("CI_FEATURE_SHA"),
        tracked_changes=tracked_changes,
        dirty=tracked_changes,
    )


def build_failure_index(junit_data, journal_data=None, log_path=None):
    failures = []
    skipped = []
    tests = junit_data.get("tests", []) if isinstance(junit_data, dict) else []

    for t in tests:
        status = t.get("status")
        nodeid = t.get("nodeid", "")
        if status in ("failure", "error"):
            details = t.get("details", {})
            raw_text = details.get("text", "")
            sample_lines = [line for line in raw_text.splitlines() if line.strip()][:25]

            # Identify known inherited Transfer failures
            if (
                "test_transfer_" in nodeid
                or "transfer_admission" in nodeid
                or "transfer_sql" in nodeid
            ):
                classification = "INHERITED_STAGE_TRANSFER"
            else:
                classification = "NEW_REGRESSION"

            failures.append(
                {
                    "nodeid": nodeid,
                    "status": status,
                    "phase": "call" if status == "failure" else "setup",
                    "duration": t.get("seconds", 0.0),
                    "classification": classification,
                    "exception_type": details.get("type", "Error"),
                    "message": details.get("message", ""),
                    "sample_lines": sample_lines,
                }
            )
        elif status == "skipped":
            details = t.get("details", {})
            skipped.append(
                {
                    "nodeid": nodeid,
                    "message": details.get("message", ""),
                }
            )

    return {
        "version": 1,
        "failure_count": len(failures),
        "skipped_count": len(skipped),
        "failures": failures,
        "skipped": skipped,
    }


def build_execution_summary(record, failure_index=None):
    junit_data = record.get("junit", {})
    tests = junit_data.get("tests", []) if isinstance(junit_data, dict) else []

    passed_count = sum(1 for t in tests if t.get("status") == "passed")
    failed_count = sum(1 for t in tests if t.get("status") == "failure")
    error_count = sum(1 for t in tests if t.get("status") == "error")
    skipped_count = sum(1 for t in tests if t.get("status") == "skipped")

    inherited_count = 0
    if failure_index:
        inherited_count = sum(
            1
            for f in failure_index.get("failures", [])
            if f.get("classification") == "INHERITED_STAGE_TRANSFER"
        )

    counts = {
        "total": junit_data.get("count", 0),
        "passed": passed_count,
        "failed": failed_count,
        "error": error_count,
        "skipped": skipped_count,
        "inherited": inherited_count,
        "unexecuted": 0,
    }

    selection = record.get("selection", {})
    selected_nodes = selection.get("test_ids", [])
    executed_count = counts["total"]

    reconciliation_status = "NOT_EVALUATED"
    reconciliation_consistent = True
    if selected_nodes:
        if (
            len(selected_nodes) == executed_count
            and failed_count == 0
            and error_count == 0
        ):
            reconciliation_status = "EXACT_ONCE_MATCH"
        elif inherited_count > 0 and (
            passed_count + inherited_count == len(selected_nodes)
        ):
            reconciliation_status = "RECONCILED_WITH_INHERITED_FAILURES"
        else:
            reconciliation_status = f"COUNT_MISMATCH (selected={len(selected_nodes)}, executed={executed_count})"
            reconciliation_consistent = False
    elif executed_count > 0 and failed_count == 0 and error_count == 0:
        reconciliation_status = "ALL_PASSED"
    elif failed_count > 0 or error_count > 0:
        if inherited_count > 0 and (failed_count + error_count == inherited_count):
            reconciliation_status = "INHERITED_FAILURES_ONLY"
        else:
            reconciliation_status = "REGRESSIONS_DETECTED"
            reconciliation_consistent = False

    return {
        "version": 1,
        "invocation_id": record.get("invocation_id"),
        "lane": record.get("name"),
        "mode": record.get("mode"),
        "commit_sha": record.get("runtime", {}).get("commit_sha"),
        "tree_sha": record.get("runtime", {}).get("tree_sha"),
        "exit_code": record.get("exit_code"),
        "wall_seconds": record.get("wall_seconds"),
        "cumulative_test_seconds": record.get("cumulative_test_seconds"),
        "workers": record.get("workers"),
        "counts": counts,
        "reconciliation": {
            "status": reconciliation_status,
            "selected_count": len(selected_nodes) if selected_nodes else executed_count,
            "executed_count": executed_count,
            "consistent": reconciliation_consistent,
        },
        "artifacts": record.get("artifacts", {}),
    }


def format_terminal_summary(record, execution_summary, failure_index=None):
    counts = execution_summary["counts"]
    reconcil = execution_summary["reconciliation"]
    runtime_info = record.get("runtime", {})
    commit_short = (runtime_info.get("commit_sha") or "unknown")[:8]
    tree_short = (runtime_info.get("tree_sha") or "unknown")[:8]
    lane = record.get("name", "test")
    workers = record.get("workers", 1)
    mode = record.get("mode", "sequential")
    wall = record.get("wall_seconds", 0.0)
    cum = record.get("cumulative_test_seconds", wall)
    exit_code = record.get("exit_code", 0)
    exit_str = "SUCCESS" if exit_code == 0 else f"FAILURE (exit code {exit_code})"
    inv_id = record.get("invocation_id", "unknown")
    evidence_dir = record.get("artifacts", {}).get(
        "profile", str(Path("artifacts/ci-profile/invocations") / inv_id)
    )

    lines = [
        f"=== Validation Summary: {lane} ({mode}-{workers}) ===",
        f"Invocation ID:   {inv_id}",
        f"Commit & Tree:   {commit_short} / {tree_short}",
        f"Validation Lane: {lane}",
        f"Outcomes:        Total: {counts['total']} | Passed: {counts['passed']} | Failed: {counts['failed']} | Skipped: {counts['skipped']} | Inherited: {counts['inherited']} | Unexecuted: {counts['unexecuted']}",
        f"Reconciliation:  {reconcil['status']}",
        f"Worker Count:    {workers} worker(s)",
        f"Wall Duration:   {wall:.2f}s (cumulative test time: {cum:.2f}s)",
        f"Exit Status:     {exit_str}",
        f"Evidence Dir:    {evidence_dir}",
        "===========================================",
    ]

    if failure_index and failure_index.get("failures"):
        failures = failure_index["failures"]
        new_regressions = sum(
            1 for f in failures if f.get("classification") != "INHERITED_STAGE_TRANSFER"
        )
        inherited = sum(
            1 for f in failures if f.get("classification") == "INHERITED_STAGE_TRANSFER"
        )
        lines.append("")
        lines.append(
            f"Failures: {len(failures)} total ({new_regressions} new regression(s), {inherited} inherited)"
        )
        lines.append("Bounded Failure Samples (max 3 shown):")
        for idx, f in enumerate(failures[:3], start=1):
            lines.append(f"  {idx}. [{f.get('classification')}] {f.get('nodeid')}")
            lines.append(
                f"     Exception: {f.get('exception_type')}: {f.get('message')}"
            )
            samples = f.get("sample_lines", [])
            if samples:
                lines.append("     Traceback sample:")
                for s_line in samples[:15]:
                    lines.append(f"       {s_line}")
        if len(failures) > 3:
            lines.append(
                f"  ... and {len(failures) - 3} more failure(s). See failure-index.json."
            )
        lines.append("")
        lines.append(f"Full diagnostics and raw logs available in: {evidence_dir}")
    return "\n".join(lines) + "\n"


def markdown(record):
    cum_time = record.get("cumulative_test_seconds", 0.0)
    lines = [
        f"### {record['name']}: {record['wall_seconds']:.2f}s command wall time (exit {record['exit_code']})",
        "",
        f"Mode `{record['mode']}`, workers {record['workers']}, SHA `{record['runtime']['commit_sha']}`, tree `{record['runtime']['tree_sha']}`, Python {record['runtime']['python']}, SQLite {record['runtime']['sqlite']}.",
        f"Invocation ID: `{record.get('invocation_id', 'unknown')}`. Dirty tree: `{record['runtime']['dirty']}`.",
        f"Command wall time: {record['wall_seconds']:.2f}s; Cumulative test duration: {cum_time:.2f}s.",
        "",
        "| Test file | Aggregate seconds (setup/call/teardown) | Tests | Failures |",
        "|---|---:|---:|---:|",
    ]
    for row in record.get("junit", {}).get("files", [])[:10]:
        lines.append(
            f"| {row['file']} | {row['seconds']:.2f} | {row['tests']} | {row['failures']} |"
        )
    if record.get("journal", {}).get("tests"):
        lines += [
            "",
            "#### Slowest tests by phase",
            "",
            "| Test node | Setup (s) | Call (s) | Teardown (s) | Total (s) | Status |",
            "|---|---:|---:|---:|---:|:---:|",
        ]
        sorted_tests = sorted(
            record["journal"]["tests"],
            key=lambda t: -t["duration"],
        )[:10]
        for t in sorted_tests:
            p = t.get("phases", {})
            lines.append(
                f"| `{t['nodeid']}` | {p.get('setup', 0.0):.4f} | {p.get('call', 0.0):.4f} | {p.get('teardown', 0.0):.4f} | {t['duration']:.4f} | {t['status']} |"
            )
    for warning in record.get("warnings", []):
        lines += ["", "Timing warning: " + warning]
    if record.get("measurement_error"):
        lines += ["", "Measurement error: " + record["measurement_error"]]
    if record.get("interrupted"):
        lines += ["", "**Warning: Execution was interrupted; results are partial.**"]
    return "\n".join(lines) + "\n"


def run(args):
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise ValueError("A command is required")
    args.output.mkdir(parents=True, exist_ok=True)
    meta = runtime()
    started_at = datetime.now(UTC).isoformat()
    invocation_id = (
        getattr(args, "invocation_id", None)
        or f"{args.name}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    )

    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        args.junit.unlink(missing_ok=True)
    journal_path = getattr(args, "journal", None)
    if journal_path:
        journal_path = Path(journal_path)
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        journal_path.unlink(missing_ok=True)

    quiet = getattr(args, "quiet", True)
    log_path = args.output / f"{args.name}.log"

    start = time.perf_counter()
    if quiet:
        with open(log_path, "wb") as log_file:
            completed = subprocess.run(
                command,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                check=False,
            )
            exit_code = completed.returncode
    else:
        completed = subprocess.run(command, check=False)
        exit_code = completed.returncode

    wall_seconds = time.perf_counter() - start
    completed_at = datetime.now(UTC).isoformat()

    record = dict(
        profile_version=1,
        invocation_id=invocation_id,
        name=args.name,
        series=getattr(args, "series", None) or re.sub(r"-\d+$", "", args.name),
        mode=args.mode,
        workers=args.workers,
        runtime=meta,
        started_at=started_at,
        completed_at=completed_at,
        command=command,
        wall_seconds=wall_seconds,
        exit_code=exit_code,
        interrupted=exit_code < 0 or exit_code in (2, 130, 143, 137),
    )

    if journal_path and journal_path.is_file():
        journal_summary = ci_journal.aggregate_journal(journal_path)
        if journal_summary["count"] > 0:
            record["journal"] = journal_summary
            record["cumulative_test_seconds"] = journal_summary[
                "cumulative_test_seconds"
            ]
            record["phases"] = {
                t["nodeid"]: t["phases"] for t in journal_summary["tests"]
            }
            if journal_summary.get("interrupted"):
                record["interrupted"] = True
                record.setdefault("warnings", []).append(
                    f"Test execution was interrupted; partial results recovered from journal "
                    f"({journal_summary['completed']}/{journal_summary['count']} tests completed)."
                )
    else:
        record["cumulative_test_seconds"] = wall_seconds

    if args.junit:
        try:
            record["junit"] = junit(args.junit)
        except (OSError, ValueError, ET.ParseError):
            if record.get("journal", {}).get("count", 0) > 0:
                record["junit"] = ci_journal.journal_to_junit_summary(record["journal"])
                record["measurement_recovered_from_journal"] = True
            else:
                record["measurement_error"] = "Missing or malformed JUnit"
                if record["exit_code"] == 0:
                    record["exit_code"] = 2

    # If execution was interrupted, exit code must reflect interruption
    if record.get("interrupted") and record["exit_code"] == 0:
        record["exit_code"] = 2

    reference = getattr(args, "reference", None)
    if reference:
        baseline = json.loads(reference.read_text())
        lane = baseline["lanes"].get(args.name)
        context = {
            k: meta[k]
            for k in ("python", "sqlite", "cpu_count", "affinity", "cpu_quota")
        }
        if (
            lane
            and context == baseline["runtime"]
            and (args.mode, args.workers) == (lane["mode"], lane["workers"])
        ):
            if record["wall_seconds"] > lane["median_seconds"] * 1.5:
                record["warnings"] = [
                    "Timing exceeds reference median by >50%; advisory only. Compare repeated runs and coverage before changing the baseline."
                ]
        else:
            record["reference_note"] = (
                "Runner/lane differs; raw timings retained without a regression threshold."
            )

    if getattr(args, "selection", None) is not None:
        record["selection"] = args.selection
    if getattr(args, "acceptance_input_hash", None) is not None:
        record["acceptance_input_hash"] = args.acceptance_input_hash

    # Save collision-safe copy in invocations/ directory
    inv_dir = args.output / "invocations"
    inv_dir.mkdir(parents=True, exist_ok=True)
    inv_file = inv_dir / f"{args.name}-{invocation_id}.json"

    artifacts_map = {
        "profile": str(inv_file.relative_to(args.output)),
    }
    if log_path.is_file():
        inv_log = inv_dir / f"{args.name}-{invocation_id}.log"
        inv_log.write_bytes(log_path.read_bytes())
        artifacts_map["log"] = str(inv_log.relative_to(args.output))
        artifacts_map["log_sha256"] = hashlib.sha256(inv_log.read_bytes()).hexdigest()

    if args.junit and args.junit.is_file():
        inv_xml = inv_dir / f"{args.name}-{invocation_id}.xml"
        inv_xml.write_bytes(args.junit.read_bytes())
        artifacts_map["junit"] = str(inv_xml.relative_to(args.output))
        artifacts_map["junit_sha256"] = hashlib.sha256(inv_xml.read_bytes()).hexdigest()
    if journal_path and journal_path.is_file():
        inv_journal = inv_dir / f"{args.name}-{invocation_id}-journal.jsonl"
        inv_journal.write_bytes(journal_path.read_bytes())
        artifacts_map["journal"] = str(inv_journal.relative_to(args.output))
        artifacts_map["journal_sha256"] = hashlib.sha256(
            inv_journal.read_bytes()
        ).hexdigest()

    # Build failure index and execution summary
    failure_index = build_failure_index(
        record.get("junit", {}), record.get("journal", {}), log_path
    )
    exec_summary = build_execution_summary(record, failure_index=failure_index)

    fail_index_file = inv_dir / f"failures-{args.name}-{invocation_id}.json"
    fail_index_file.write_text(json.dumps(failure_index, indent=2) + "\n")
    (args.output / "failure-index.json").write_text(
        json.dumps(failure_index, indent=2) + "\n"
    )
    artifacts_map["failure_index"] = str(fail_index_file.relative_to(args.output))

    summary_file = inv_dir / f"summary-{args.name}-{invocation_id}.json"
    summary_file.write_text(json.dumps(exec_summary, indent=2) + "\n")
    (args.output / "execution-summary.json").write_text(
        json.dumps(exec_summary, indent=2) + "\n"
    )
    artifacts_map["execution_summary"] = str(summary_file.relative_to(args.output))

    record["artifacts"] = artifacts_map
    inv_file.write_text(json.dumps(record, indent=2) + "\n")

    # Save standard output for lane
    (args.output / (args.name + ".json")).write_text(
        json.dumps(record, indent=2) + "\n"
    )
    report = markdown(record)
    (args.output / (args.name + ".md")).write_text(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write(report)

    if quiet:
        summary_text = format_terminal_summary(record, exec_summary, failure_index)
        print(summary_text)

    return record["exit_code"]


def profile_focused(args):
    """Run focused pytest selection with automatic isolated output, preserving JUnit and journal."""
    args.output.mkdir(parents=True, exist_ok=True)
    inv_id = f"focused-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    inv_dir = args.output / "invocations" / inv_id
    inv_dir.mkdir(parents=True, exist_ok=True)
    xml = inv_dir / "junit.xml"
    journal = inv_dir / "journal.jsonl"
    pytest_targets = args.pytest_args
    if pytest_targets[:1] == ["--"]:
        pytest_targets = pytest_targets[1:]

    workers = args.workers
    if workers == 1 and not getattr(args, "explicit_workers", False):
        workers = resource_scheduler.calculate_worker_budget(lane_name="focused")

    command = [
        sys.executable,
        "-m",
        "pytest",
        *pytest_targets,
        "-p",
        "scripts.ci_journal",
        "--junitxml",
        str(xml),
        "--journal",
        str(journal),
        "--durations=20",
    ]
    if workers > 1:
        command += ["-n", str(workers), "--dist", "worksteal"]

    run_args = argparse.Namespace(
        name=args.name,
        command=command,
        output=args.output,
        junit=xml,
        journal=journal,
        mode="xdist" if workers > 1 else "sequential",
        workers=workers,
        series="focused",
        reference=None,
        invocation_id=inv_id,
        quiet=getattr(args, "quiet", True),
    )
    code = run(run_args)
    report_path = args.output / f"{args.name}.md"
    if report_path.is_file() and not getattr(args, "quiet", True):
        print(report_path.read_text())
    return code


def coverage(expected, profiles):
    nodes = {
        line.strip()
        for line in expected.read_text().splitlines()
        if line.startswith("tests/") and "::" in line
    }
    if not nodes:
        raise ValueError("Empty required test collection")
    actual = []
    for path in profiles:
        profile = json.loads(path.read_text())
        if profile["exit_code"] != 0:
            raise ValueError("A required lane failed")
        for item in profile["junit"]["tests"]:
            if item["status"] != "passed":
                raise ValueError("Required test failed or skipped")
            actual.append(item["nodeid"])
    if len(actual) != len(set(actual)) or set(actual) != nodes:
        raise ValueError(
            f"Required test coverage mismatch: missing={len(nodes - set(actual))}, extra={len(set(actual) - nodes)}, duplicates={len(actual) - len(set(actual))}"
        )
    return {"required": len(nodes), "executed_once": len(actual)}


def compare(paths):
    groups = {}
    for path in paths:
        record = json.loads(path.read_text())
        series = record.get("series") or re.sub(
            r"-\d+$", "", record.get("name", "pytest")
        )
        key = (series, record["mode"], record["workers"])
        groups.setdefault(key, []).append(record)
    result = []
    for (series, mode, workers), records in sorted(groups.items()):
        times = [r["wall_seconds"] for r in records]
        result.append(
            dict(
                mode=mode,
                series=series,
                workers=workers,
                samples=len(times),
                median=statistics.median(times),
                minimum=min(times),
                maximum=max(times),
                failures=sum(r["exit_code"] != 0 for r in records),
            )
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)

    execute = actions.add_parser("run")
    execute.add_argument("--name", required=True)
    execute.add_argument("--output", type=Path, default=Path("artifacts/ci-profile"))
    execute.add_argument("--junit", type=Path)
    execute.add_argument(
        "--journal",
        type=Path,
        help="Path to append-only JSONL test event journal",
    )
    execute.add_argument(
        "--mode",
        choices=("sequential", "xdist", "sharded"),
        default="sequential",
    )
    execute.add_argument("--workers", type=int, default=1)
    execute.add_argument("--series")
    execute.add_argument("--reference", type=Path)
    execute.add_argument(
        "--quiet",
        action="store_true",
        default=True,
        help="Compact terminal summary (default)",
    )
    execute.add_argument(
        "--verbose",
        dest="quiet",
        action="store_false",
        help="Stream raw output to terminal",
    )
    execute.add_argument("command", nargs=argparse.REMAINDER)

    prof = actions.add_parser(
        "profile",
        help="Run focused local tests with isolated output and profile",
    )
    prof.add_argument("--name", default="focused")
    prof.add_argument("--output", type=Path, default=Path("artifacts/ci-profile"))
    prof.add_argument("--workers", type=int, default=1)
    prof.add_argument(
        "--quiet",
        action="store_true",
        default=True,
        help="Compact terminal summary (default)",
    )
    prof.add_argument(
        "--verbose",
        dest="quiet",
        action="store_false",
        help="Stream raw output to terminal",
    )
    prof.add_argument("pytest_args", nargs=argparse.REMAINDER)

    aggregate = actions.add_parser("compare")
    aggregate.add_argument("profiles", type=Path, nargs="+")

    required = actions.add_parser("coverage")
    required.add_argument("--expected", type=Path, required=True)
    required.add_argument("profiles", type=Path, nargs="+")

    args = parser.parse_args()
    if args.action == "compare":
        print(json.dumps(compare(args.profiles), indent=2))
        return 0
    if args.action == "coverage":
        print(json.dumps(coverage(args.expected, args.profiles)))
        return 0
    if args.action == "profile":
        args.explicit_workers = "--workers" in sys.argv
        return profile_focused(args)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
