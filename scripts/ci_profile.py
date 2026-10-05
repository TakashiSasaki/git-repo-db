"""Run a CI command without hiding its exit status; summarize standard JUnit."""

import argparse
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
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


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
                if (Path(__file__).resolve().parents[1] / candidate).is_file():
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
    cpu = Path("/sys/fs/cgroup/cpu.max")
    return dict(
        python=platform.python_version(),
        sqlite=sqlite3.sqlite_version,
        cpu_count=os.cpu_count(),
        affinity=len(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else None,
        cpu_quota=cpu.read_text().strip() if cpu.exists() else None,
        commit_sha=os.environ.get("GITHUB_SHA")
        or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        run_id=os.environ.get("GITHUB_RUN_ID"),
        run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),
        feature_sha=os.environ.get("CI_FEATURE_SHA"),
        tracked_changes=subprocess.run(
            ["git", "diff", "--quiet"], check=False
        ).returncode
        != 0,
    )


def markdown(record):
    lines = [
        f"### {record['name']}: {record['wall_seconds']:.2f}s, exit {record['exit_code']}",
        "",
        f"Mode `{record['mode']}`, workers {record['workers']}, SHA `{record['runtime']['commit_sha']}`, Python {record['runtime']['python']}, SQLite {record['runtime']['sqlite']}.",
        "",
        "| Test file | Aggregate seconds (setup/call/teardown) | Tests | Failures |",
        "|---|---:|---:|---:|",
    ]
    for row in record.get("junit", {}).get("files", [])[:10]:
        lines.append(
            f"| {row['file']} | {row['seconds']:.2f} | {row['tests']} | {row['failures']} |"
        )
    for warning in record.get("warnings", []):
        lines += ["", "Timing warning: " + warning]
    if record.get("measurement_error"):
        lines += ["", record["measurement_error"]]
    return "\n".join(lines) + "\n"


def run(args):
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise ValueError("A command is required")
    args.output.mkdir(parents=True, exist_ok=True)
    meta = runtime()
    if args.sqlite:
        meta["sqlite"] = args.sqlite  # minimum lane itself asserts its actual runtime
    started_at = datetime.now(UTC).isoformat()
    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        args.junit.unlink(missing_ok=True)
    start = time.perf_counter()
    completed = subprocess.run(command, check=False)
    record = dict(
        profile_version=1,
        name=args.name,
        series=getattr(args, "series", None) or re.sub(r"-\d+$", "", args.name),
        mode=args.mode,
        workers=args.workers,
        runtime=meta,
        started_at=started_at,
        command=command,
        wall_seconds=time.perf_counter() - start,
        exit_code=completed.returncode,
    )
    if args.junit:
        try:
            record["junit"] = junit(args.junit)
        except (OSError, ValueError, ET.ParseError):
            record["measurement_error"] = "Missing or malformed JUnit"
            if record["exit_code"] == 0:
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
    (args.output / (args.name + ".json")).write_text(
        json.dumps(record, indent=2) + "\n"
    )
    report = markdown(record)
    (args.output / (args.name + ".md")).write_text(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write(report)
    return record["exit_code"]


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
        "--mode", choices=("sequential", "xdist", "sharded"), default="sequential"
    )
    execute.add_argument("--workers", type=int, default=1)
    execute.add_argument("--sqlite")
    execute.add_argument("--series")
    execute.add_argument("--reference", type=Path)
    execute.add_argument("command", nargs=argparse.REMAINDER)
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
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
