"""Run a CI command without hiding its exit status; summarize standard JUnit and journal."""

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
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


def sha256_path(path: Path) -> str:
    """Compute SHA-256 digest streaming in 64 KiB chunks without reading whole file into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_text(path: Path, content: str) -> None:
    """Write text to a temporary file in the destination directory and replace atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, encoding="utf-8"
    ) as tf:
        tf.write(content)
        tmp_name = tf.name
    os.replace(tmp_name, path)


def atomic_copy(src: Path, dst: Path) -> None:
    """Copy a file to destination atomically using a temporary file in destination directory."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=dst.parent, delete=False) as tf:
        with open(src, "rb") as sf:
            shutil.copyfileobj(sf, tf)
        tmp_name = tf.name
    os.replace(tmp_name, dst)


def build_failure_index(
    junit_data, journal_data=None, log_path=None, reconciliation=None
):
    """Build structured failure index.

    Never classify an inherited failure from a test name alone.
    Uses authoritative reconciliation evidence when available; otherwise labels failures as unclassified.
    """
    failures = []
    skipped = []
    tests = junit_data.get("tests", []) if isinstance(junit_data, dict) else []

    reconcil_map = {}
    if isinstance(reconciliation, dict):
        for item in reconciliation.get("node_details", []):
            if "node_id" in item:
                reconcil_map[item["node_id"]] = item

    for t in tests:
        status = t.get("status")
        nodeid = t.get("nodeid", "")
        if status in ("failure", "error"):
            details = t.get("details", {})
            raw_text = details.get("text", "")
            sample_lines = [line for line in raw_text.splitlines() if line.strip()][:25]

            # Authoritative failure classification
            if reconcil_map and nodeid in reconcil_map:
                r_item = reconcil_map[nodeid]
                cls = r_item.get("classification", "UNCLASSIFIED_FAILURE")
                is_inherited = r_item.get("is_inherited", False) or cls in (
                    "STAGE_TRANSFER",
                    "ADMISSION_PERMISSION_DENIED",
                    "INHERITED_STAGE_TRANSFER",
                    "INHERITED_KNOWN_FAILURE",
                )
                if is_inherited and not cls.startswith("INHERITED_"):
                    classification = f"INHERITED_{cls}"
                else:
                    classification = cls
            elif reconciliation is not None:
                # Authoritative reconciliation was provided, but this node was not an expected inherited failure
                classification = "NEW_REGRESSION"
                is_inherited = False
            else:
                # Before reconciliation against baseline, all failures are unclassified
                classification = "UNCLASSIFIED_FAILURE"
                is_inherited = False

            failures.append(
                {
                    "nodeid": nodeid,
                    "status": status,
                    "phase": "call" if status == "failure" else "setup",
                    "duration": t.get("seconds", 0.0),
                    "classification": classification,
                    "is_inherited": is_inherited,
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


def build_execution_summary(record, failure_index=None, reconciliation=None):
    """Build compact execution summary.

    Verifies exact selected/executed node multisets before reporting exact reconciliation.
    Never produces PASS for missing, duplicate, unexpected, interrupted, or unverified execution.
    """
    junit_data = record.get("junit", {})
    tests = junit_data.get("tests", []) if isinstance(junit_data, dict) else []

    passed_count = sum(1 for t in tests if t.get("status") == "passed")
    failed_count = sum(1 for t in tests if t.get("status") == "failure")
    error_count = sum(1 for t in tests if t.get("status") == "error")
    skipped_count = sum(1 for t in tests if t.get("status") == "skipped")

    inherited_count = 0
    new_regressions_count = 0
    changed_failures_count = 0
    unclassified_count = 0

    if failure_index:
        for f in failure_index.get("failures", []):
            if f.get("is_inherited") or f.get("classification", "").startswith(
                "INHERITED_"
            ):
                inherited_count += 1
            elif f.get("classification") == "CHANGED_FAILURE":
                changed_failures_count += 1
            elif f.get("classification") == "NEW_REGRESSION":
                new_regressions_count += 1
            else:
                unclassified_count += 1

    selection = record.get("selection", {})
    selected_nodes = selection.get("test_ids", [])
    executed_nodes = [t.get("nodeid") for t in tests if t.get("nodeid")]

    from collections import Counter

    selected_counter = Counter(selected_nodes)
    executed_counter = Counter(executed_nodes)
    selected_set = set(selected_nodes)
    executed_set = set(executed_nodes)

    missing_nodes = sorted(selected_set - executed_set)
    unexpected_nodes = sorted(executed_set - selected_set)
    duplicate_executed = [nid for nid, cnt in executed_counter.items() if cnt > 1]
    duplicate_selected = [nid for nid, cnt in selected_counter.items() if cnt > 1]
    duplicate_nodes = sorted(set(duplicate_executed) | set(duplicate_selected))

    counts = {
        "total": len(executed_nodes),
        "passed": passed_count,
        "failed": failed_count,
        "error": error_count,
        "skipped": skipped_count,
        "inherited": inherited_count,
        "unexecuted": len(missing_nodes),
    }

    interrupted = record.get("interrupted", False) or record.get("exit_code") in (
        2,
        130,
        143,
        137,
    )
    exit_code = record.get("exit_code", -1)

    reconciliation_status = "NOT_EVALUATED"
    reconciliation_consistent = True

    if interrupted:
        reconciliation_status = "INTERRUPTED_EXECUTION"
        reconciliation_consistent = False
    elif selected_nodes:
        if selected_counter == executed_counter and not duplicate_nodes:
            if failed_count == 0 and error_count == 0 and exit_code == 0:
                reconciliation_status = "EXACT_ONCE_MATCH"
                reconciliation_consistent = True
            elif (
                reconciliation is not None
                and reconciliation.get("acceptance_verdict") == "PASSED"
                and reconciliation.get("new_regressions_count", 0) == 0
                and reconciliation.get("changed_failures_count", 0) == 0
                and inherited_count > 0
                and (passed_count + inherited_count == len(selected_nodes))
            ):
                reconciliation_status = "RECONCILED_WITH_INHERITED_FAILURES"
                reconciliation_consistent = True
            elif (
                reconciliation is not None
                and reconciliation.get("acceptance_verdict") != "PASSED"
            ):
                reconciliation_status = f"RECONCILIATION_REJECTED ({reconciliation.get('acceptance_verdict', 'REJECTED')})"
                reconciliation_consistent = False
            elif (
                inherited_count > 0
                and (passed_count + inherited_count == len(selected_nodes))
                and (
                    new_regressions_count == 0
                    and changed_failures_count == 0
                    and unclassified_count == 0
                )
                and reconciliation is not None
                and reconciliation.get("acceptance_verdict") == "PASSED"
            ):
                reconciliation_status = "RECONCILED_WITH_INHERITED_FAILURES"
                reconciliation_consistent = True
            else:
                reconciliation_status = "REGRESSIONS_DETECTED"
                reconciliation_consistent = False
        else:
            reconciliation_status = (
                f"NODE_MISMATCH (missing={len(missing_nodes)}, "
                f"unexpected={len(unexpected_nodes)}, "
                f"duplicates={len(duplicate_nodes)})"
            )
            reconciliation_consistent = False
    elif executed_nodes and failed_count == 0 and error_count == 0 and exit_code == 0:
        reconciliation_status = "ALL_PASSED_UNVERIFIED_SELECTION"
        reconciliation_consistent = True
    elif failed_count > 0 or error_count > 0:
        reconciliation_status = "REGRESSIONS_DETECTED"
        reconciliation_consistent = False
    elif exit_code != 0:
        reconciliation_status = f"COMMAND_FAILED (exit={exit_code})"
        reconciliation_consistent = False

    return {
        "version": 1,
        "invocation_id": record.get("invocation_id"),
        "lane": record.get("name"),
        "mode": record.get("mode"),
        "commit_sha": record.get("runtime", {}).get("commit_sha"),
        "tree_sha": record.get("runtime", {}).get("tree_sha"),
        "exit_code": exit_code,
        "child_exit_code": record.get("child_exit_code", exit_code),
        "verification_exit_code": (
            0
            if reconciliation_consistent
            else (1 if not record.get("measurement_error") else 2)
        ),
        "wall_seconds": record.get("wall_seconds"),
        "cumulative_test_seconds": record.get("cumulative_test_seconds"),
        "workers": record.get("workers"),
        "counts": counts,
        "reconciliation": {
            "status": reconciliation_status,
            "selected_count": len(selected_nodes),
            "executed_count": len(executed_nodes),
            "missing_count": len(missing_nodes),
            "unexpected_count": len(unexpected_nodes),
            "duplicate_count": len(duplicate_nodes),
            "missing_nodes": missing_nodes,
            "unexpected_nodes": unexpected_nodes,
            "duplicate_nodes": duplicate_nodes,
            "consistent": reconciliation_consistent,
        },
        "artifacts": record.get("artifacts", {}),
    }


def terminal_excerpt(value, max_chars=240, *, first_line=False):
    """Bound presentation only; keep complete evidence in the saved records."""
    text = str(value)
    if first_line:
        lines = text.splitlines()
        text = lines[0] if lines else ""
    if len(text) > max_chars:
        return text[:max_chars] + f"... [truncated {len(text) - max_chars} chars]"
    return text


def format_terminal_summary(record, execution_summary, failure_index=None):
    counts = execution_summary["counts"]
    reconcil = execution_summary["reconciliation"]
    runtime_info = record.get("runtime", {})
    commit_short = (runtime_info.get("commit_sha") or "unknown")[:8]
    tree_short = (runtime_info.get("tree_sha") or "unknown")[:8]
    lane = terminal_excerpt(record.get("name", "test"), 80, first_line=True)
    workers = record.get("workers", 1)
    mode = record.get("mode", "sequential")
    wall = record.get("wall_seconds", 0.0)
    exit_code = record.get("exit_code", 0)
    inv_id = record.get("invocation_id", "unknown")
    evidence_dir = record.get("artifacts", {}).get(
        "profile", str(Path("artifacts/ci-profile/invocations") / inv_id)
    )

    verdict = (
        "PASSED" if (exit_code == 0 and reconcil.get("consistent", True)) else "FAILED"
    )
    command_str = " ".join(record.get("command", []))
    is_pytest = (
        "pytest" in command_str or counts["total"] > 0 or bool(record.get("selection"))
    )

    lines = []
    if not is_pytest:
        lines.append(
            f"[{lane}] {verdict} (exit={exit_code}, wall={wall:.2f}s, commit={commit_short}, tree={tree_short})"
        )
        lines.append(f"  evidence: {terminal_excerpt(evidence_dir, 360)}")
    else:
        lines.append(
            f"[{lane}] {verdict} ({mode}, {workers}w, exit={exit_code}, wall={wall:.2f}s, commit={commit_short}, tree={tree_short})"
        )
        counts_str = (
            f"  tests: {counts['total']} executed, {counts['passed']} passed, {counts['failed']} failed, "
            f"{counts['error']} error, {counts['skipped']} skipped, {counts['inherited']} inherited, {counts['unexecuted']} unexecuted"
        )
        lines.append(counts_str)
        lines.append(f"  reconciliation: {terminal_excerpt(reconcil['status'], 160)}")
        lines.append(f"  evidence: {terminal_excerpt(evidence_dir, 360)}")

    if failure_index and failure_index.get("failures"):
        failures = failure_index["failures"]
        inherited = sum(
            1
            for f in failures
            if f.get("is_inherited")
            or f.get("classification", "").startswith("INHERITED_")
        )
        new_or_unclass = len(failures) - inherited
        lines.append(
            f"  failures: {len(failures)} total ({new_or_unclass} new/unclassified, {inherited} inherited)"
        )
        for idx, f in enumerate(failures[:3], start=1):
            msg = terminal_excerpt(f.get("message") or "error", first_line=True)
            node = terminal_excerpt(f.get("nodeid"), first_line=True)
            classification = terminal_excerpt(f.get("classification"), 80)
            lines.append(f"    {idx}. [{classification}] {node}: {msg}")
        lines.append(
            "  tracebacks: retained in failure index; inspect one node with ci_query.py failure"
        )
        if len(failures) > 3:
            lines.append(
                f"    ... and {len(failures) - 3} more failure(s). See {terminal_excerpt(evidence_dir, 360)}"
            )

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
    command = list(args.command)
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

    # Allocate unique immutable invocation paths BEFORE starting child process
    inv_dir = args.output / "invocations"
    inv_dir.mkdir(parents=True, exist_ok=True)

    inv_log = inv_dir / f"{args.name}-{invocation_id}.log"
    inv_xml = (
        (inv_dir / f"{args.name}-{invocation_id}.xml")
        if getattr(args, "junit", None)
        else None
    )
    inv_journal = (
        (inv_dir / f"{args.name}-{invocation_id}-journal.jsonl")
        if getattr(args, "journal", None)
        else None
    )

    junit_arg = getattr(args, "junit", None)
    junit_path = Path(junit_arg) if junit_arg else None
    if junit_path:
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        junit_path.unlink(missing_ok=True)

    journal_arg = getattr(args, "journal", None)
    journal_path = Path(journal_arg) if journal_arg else None
    if journal_path:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        journal_path.unlink(missing_ok=True)

    # Replace --junitxml and --journal target in command with unique invocation paths
    if inv_xml:
        if "--junitxml" in command:
            idx = command.index("--junitxml")
            if idx + 1 < len(command):
                command[idx + 1] = str(inv_xml)
        elif any(c.startswith("--junitxml=") for c in command):
            for i, c in enumerate(command):
                if c.startswith("--junitxml="):
                    command[i] = f"--junitxml={inv_xml}"
                    break

    if inv_journal:
        if "--journal" in command:
            idx = command.index("--journal")
            if idx + 1 < len(command):
                command[idx + 1] = str(inv_journal)
        elif any(c.startswith("--journal=") for c in command):
            for i, c in enumerate(command):
                if c.startswith("--journal="):
                    command[i] = f"--journal={inv_journal}"
                    break

    quiet = getattr(args, "quiet", True)
    workers = getattr(args, "workers", 1)
    is_pytest = any("pytest" in str(c) for c in command)

    start = time.perf_counter()

    def _execute():
        nonlocal exit_code
        if quiet:
            with open(inv_log, "wb") as log_file:
                completed = subprocess.run(
                    command,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                exit_code = completed.returncode
        else:
            with open(inv_log, "wb") as log_file:
                proc = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                assert proc.stdout is not None
                for chunk in iter(lambda: proc.stdout.read(4096), b""):
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                    log_file.write(chunk)
                proc.wait()
                exit_code = proc.returncode

    exit_code = 0
    if is_pytest and workers > 1:
        lock_file = getattr(args, "resource_lock", None)
        with resource_scheduler.scoped_host_cpu_reservation(
            workers, lock_path=lock_file
        ) as granted:
            if granted != workers and not getattr(args, "explicit_workers", False):
                workers = granted
                if "-n" in command:
                    idx = command.index("-n")
                    if idx + 1 < len(command):
                        command[idx + 1] = str(granted)
            _execute()
    else:
        _execute()

    wall_seconds = time.perf_counter() - start
    completed_at = datetime.now(UTC).isoformat()

    record = dict(
        profile_version=1,
        invocation_id=invocation_id,
        name=args.name,
        series=getattr(args, "series", None) or re.sub(r"-\d+$", "", args.name),
        mode=args.mode,
        workers=workers,
        runtime=meta,
        started_at=started_at,
        completed_at=completed_at,
        command=command,
        wall_seconds=wall_seconds,
        exit_code=exit_code,
        child_exit_code=exit_code,
        interrupted=exit_code < 0 or exit_code in (2, 130, 143, 137),
    )

    target_journal = None
    if inv_journal and inv_journal.is_file():
        target_journal = inv_journal
    elif journal_path and journal_path.is_file():
        target_journal = journal_path
        if inv_journal:
            atomic_copy(journal_path, inv_journal)

    if target_journal and target_journal.is_file():
        journal_summary = ci_journal.aggregate_journal(target_journal)
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

    if junit_path:
        target_xml = None
        if inv_xml and inv_xml.is_file():
            target_xml = inv_xml
        elif junit_path.is_file():
            target_xml = junit_path
            if inv_xml:
                atomic_copy(junit_path, inv_xml)

        if target_xml and target_xml.is_file():
            try:
                record["junit"] = junit(target_xml)
            except (OSError, ValueError, ET.ParseError):
                if record.get("journal", {}).get("count", 0) > 0:
                    record["junit"] = ci_journal.journal_to_junit_summary(
                        record["journal"]
                    )
                    record["measurement_recovered_from_journal"] = True
                else:
                    record["measurement_error"] = "Missing or malformed JUnit"
                    if record["exit_code"] == 0:
                        record["exit_code"] = 2
        else:
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

    # Construct complete, immutable artifact references using streaming hashes
    inv_file = inv_dir / f"{args.name}-{invocation_id}.json"
    fail_index_file = inv_dir / f"failures-{args.name}-{invocation_id}.json"
    summary_file = inv_dir / f"summary-{args.name}-{invocation_id}.json"

    artifacts_map = {
        "profile": str(inv_file.relative_to(args.output)),
        "failure_index": str(fail_index_file.relative_to(args.output)),
        "execution_summary": str(summary_file.relative_to(args.output)),
    }
    if inv_log.is_file():
        artifacts_map["log"] = str(inv_log.relative_to(args.output))
        artifacts_map["log_sha256"] = sha256_path(inv_log)

    if inv_xml and inv_xml.is_file():
        artifacts_map["junit"] = str(inv_xml.relative_to(args.output))
        artifacts_map["junit_sha256"] = sha256_path(inv_xml)
    if inv_journal and inv_journal.is_file():
        artifacts_map["journal"] = str(inv_journal.relative_to(args.output))
        artifacts_map["journal_sha256"] = sha256_path(inv_journal)

    # Populate artifacts into record BEFORE building execution summary
    record["artifacts"] = artifacts_map

    # Build failure index and execution summary with populated artifacts
    reconciliation = getattr(args, "reconciliation", None)
    failure_index = build_failure_index(
        record.get("junit", {}),
        record.get("journal", {}),
        inv_log,
        reconciliation=reconciliation,
    )
    exec_summary = build_execution_summary(
        record,
        failure_index=failure_index,
        reconciliation=reconciliation,
    )

    # Derive the effective exit status before persisting any result.
    # A successful child must not override missing or inconsistent evidence.
    child_exit_code = record["child_exit_code"]
    if record.get("measurement_error"):
        verification_exit_code = 2
        verification_status = record["measurement_error"]
    elif not exec_summary["reconciliation"]["consistent"]:
        verification_exit_code = 1
        verification_status = exec_summary["reconciliation"]["status"]
    else:
        verification_exit_code = 0
        verification_status = exec_summary["reconciliation"]["status"]
    effective_exit_code = (
        child_exit_code or record["exit_code"] or verification_exit_code
    )
    record.update(
        child_exit_code=child_exit_code,
        verification_exit_code=verification_exit_code,
        verification_status=verification_status,
        verified=effective_exit_code == 0,
        exit_code=effective_exit_code,
    )
    exec_summary.update(
        exit_code=effective_exit_code,
        child_exit_code=child_exit_code,
        verification_exit_code=verification_exit_code,
    )

    # Persist immutable invocation files in inv_dir
    fail_index_file.write_text(json.dumps(failure_index, indent=2) + "\n")
    summary_file.write_text(json.dumps(exec_summary, indent=2) + "\n")
    inv_file.write_text(json.dumps(record, indent=2) + "\n")

    # Atomic publication of top-level pointer files
    atomic_write_text(
        args.output / "failure-index.json",
        json.dumps(failure_index, indent=2) + "\n",
    )
    atomic_write_text(
        args.output / "execution-summary.json",
        json.dumps(exec_summary, indent=2) + "\n",
    )
    atomic_write_text(
        args.output / (args.name + ".json"),
        json.dumps(record, indent=2) + "\n",
    )
    report = markdown(record)
    atomic_write_text(args.output / (args.name + ".md"), report)

    # Atomically copy primary evidence to standard lane locations for compatibility
    if inv_log.is_file():
        atomic_copy(inv_log, args.output / f"{args.name}.log")
    if inv_xml and inv_xml.is_file():
        atomic_copy(inv_xml, args.output / f"{args.name}.xml")
    if inv_journal and inv_journal.is_file():
        atomic_copy(inv_journal, args.output / f"{args.name}-journal.jsonl")

    if junit_path and inv_xml and inv_xml.is_file() and junit_path != inv_xml:
        atomic_copy(inv_xml, junit_path)
    if (
        journal_path
        and inv_journal
        and inv_journal.is_file()
        and journal_path != inv_journal
    ):
        atomic_copy(inv_journal, journal_path)

    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write(report)

    if quiet:
        summary_text = format_terminal_summary(record, exec_summary, failure_index)
        print(summary_text, end="")

    return effective_exit_code


def profile_focused(args):
    """Run focused pytest selection with automatic isolated output, preserving JUnit and journal."""
    args.output.mkdir(parents=True, exist_ok=True)
    pytest_targets = args.pytest_args
    if pytest_targets[:1] == ["--"]:
        pytest_targets = pytest_targets[1:]

    workers = args.workers
    if workers == 1 and not getattr(args, "explicit_workers", False):
        workers = resource_scheduler.calculate_worker_budget(lane_name="focused")

    xml = args.output / f"{args.name}.xml"
    journal = args.output / f"{args.name}-journal.jsonl"

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
