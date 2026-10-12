"""Append-only JSONL test event journal for per-phase timings and crash recovery."""

import json
import math
import os
import time
from pathlib import Path


class JournalWriter:
    """Crash-tolerant append-only JSONL stream for test execution events."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.path, "a", encoding="utf-8")

    def record_phase(self, nodeid, phase, outcome, duration, timestamp=None):
        if not math.isfinite(duration) or duration < 0:
            duration = 0.0
        entry = {
            "event": "phase",
            "nodeid": nodeid,
            "phase": phase,
            "outcome": outcome,
            "duration": round(float(duration), 6),
            "timestamp": round(float(timestamp or time.time()), 6),
        }
        line = json.dumps(entry, separators=(",", ":")) + "\n"
        self.file.write(line)
        self.file.flush()
        try:
            os.fsync(self.file.fileno())
        except OSError:
            pass

    def close(self):
        if not self.file.closed:
            self.file.flush()
            try:
                os.fsync(self.file.fileno())
            except OSError:
                pass
            self.file.close()


def parse_journal(path):
    """Parse JSONL journal lines, gracefully tolerating partial trailing writes from crashes."""
    events = []
    path = Path(path)
    if not path.is_file():
        return events
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                # Truncated write from abrupt termination; ignore partial line
                continue
    return events


def aggregate_journal(source):
    """Aggregate per-phase test events into per-test and per-file duration profiles."""
    events = parse_journal(source) if isinstance(source, (str, Path)) else source
    tests = {}
    for ev in events:
        nodeid = ev.get("nodeid")
        if not nodeid or ev.get("event") != "phase":
            continue
        test = tests.setdefault(
            nodeid,
            {
                "nodeid": nodeid,
                "file": nodeid.split("::")[0],
                "name": nodeid.split("::")[-1],
                "phases": {"setup": 0.0, "call": 0.0, "teardown": 0.0},
                "duration": 0.0,
                "status": "passed",
                "completed": False,
            },
        )
        phase = ev.get("phase")
        duration = float(ev.get("duration", 0.0))
        outcome = ev.get("outcome", "passed")
        if phase in test["phases"]:
            test["phases"][phase] = round(duration, 6)
        if outcome in ("failed", "error") or test["status"] in ("failed", "error"):
            test["status"] = "failed"
        elif outcome == "skipped" and test["status"] != "failed":
            test["status"] = "skipped"
        if phase == "teardown":
            test["completed"] = True

    files = {}
    for test in tests.values():
        test["duration"] = round(sum(test["phases"].values()), 6)
        summary = files.setdefault(
            test["file"],
            {
                "file": test["file"],
                "seconds": 0.0,
                "tests": 0,
                "failures": 0,
                "skipped": 0,
            },
        )
        summary["seconds"] = round(summary["seconds"] + test["duration"], 6)
        summary["tests"] += 1
        summary["failures"] += test["status"] in ("failed", "error")
        summary["skipped"] += test["status"] == "skipped"

    completed = sum(1 for t in tests.values() if t["completed"])
    partial = len(tests) - completed
    return {
        "tests": list(tests.values()),
        "files": sorted(files.values(), key=lambda r: -r["seconds"]),
        "count": len(tests),
        "completed": completed,
        "partial": partial,
        "interrupted": partial > 0,
        "wall_seconds": round(sum(t["duration"] for t in tests.values()), 6),
    }


def journal_to_junit_summary(source):
    """Convert event journal to JUnit-compatible profile representation with per-phase details."""
    summary = (
        source
        if isinstance(source, dict) and "tests" in source
        else aggregate_journal(source)
    )
    return {
        "tests": [
            {
                "file": t["file"],
                "name": t["name"],
                "seconds": t["duration"],
                "status": t["status"],
                "nodeid": t["nodeid"],
                "phases": t["phases"],
                "completed": t["completed"],
            }
            for t in summary["tests"]
        ],
        "files": summary["files"],
        "count": summary["count"],
        "completed": summary["completed"],
        "partial": summary["partial"],
        "interrupted": summary["interrupted"],
    }


class JournalPlugin:
    """Pytest plugin hooking runtest log reports to append-only journal."""

    def __init__(self, path):
        self.writer = JournalWriter(path)

    def pytest_runtest_logreport(self, report):
        self.writer.record_phase(
            report.nodeid,
            report.when,
            report.outcome,
            report.duration,
        )

    def pytest_unconfigure(self, config):
        self.writer.close()


def pytest_addoption(parser):
    group = parser.getgroup("journaling", "CI test execution event journaling")
    group.addoption(
        "--journal",
        action="store",
        default=os.environ.get("CI_EVENT_JOURNAL"),
        help="Path to append-only JSONL test event journal",
    )


def pytest_configure(config):
    path = config.getoption("--journal", default=None) or os.environ.get(
        "CI_EVENT_JOURNAL"
    )
    if path and not hasattr(config, "workerinput"):
        plugin = JournalPlugin(path)
        config.pluginmanager.register(plugin, name="ci_event_journal")
