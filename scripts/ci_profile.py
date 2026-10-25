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

from scripts import ci_journal  # noqa: E402


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
        row = dict(
            file=name,
            name=case.get("name"),
            seconds=float(case.get("time", 0)),
            status=status,
            nodeid="::".join([name, *classes, case.get("name", "")]),
        )
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

    start = time.perf_counter()
    completed = subprocess.run(command, check=False)
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
        exit_code=completed.returncode,
        interrupted=completed.returncode < 0
        or completed.returncode in (2, 130, 143, 137),
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
    if args.workers > 1:
        command += ["-n", str(args.workers), "--dist", "worksteal"]

    run_args = argparse.Namespace(
        name=args.name,
        command=command,
        output=args.output,
        junit=xml,
        journal=journal,
        mode="xdist" if args.workers > 1 else "sequential",
        workers=args.workers,
        series="focused",
        reference=None,
        invocation_id=inv_id,
    )
    code = run(run_args)
    report_path = args.output / f"{args.name}.md"
    if report_path.is_file():
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
    execute.add_argument("command", nargs=argparse.REMAINDER)

    prof = actions.add_parser(
        "profile",
        help="Run focused local tests with isolated output and profile",
    )
    prof.add_argument("--name", default="focused")
    prof.add_argument("--output", type=Path, default=Path("artifacts/ci-profile"))
    prof.add_argument("--workers", type=int, default=1)
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
        return profile_focused(args)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
