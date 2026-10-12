"""Append-only JSONL test event journal for per-phase timings and crash recovery."""

import json
import math
import os
import time
from pathlib import Path

VALID_EVENTS = ("start", "phase", "finish")
VALID_PHASES = ("setup", "call", "teardown")
VALID_OUTCOMES = ("passed", "failed", "skipped", "error")


class JournalWriter:
    """Crash-tolerant append-only JSONL stream for test execution events."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.path, "a", encoding="utf-8")

    def record_start(self, nodeid, worker_id="master", timestamp=None):
        if not isinstance(nodeid, str) or not nodeid.strip():
            raise ValueError(f"Malformed node ID for journal: {nodeid}")
        entry = {
            "event": "start",
            "nodeid": nodeid,
            "worker_id": str(worker_id or "master"),
            "timestamp": round(float(timestamp or time.time()), 6),
        }
        self._write_entry(entry)

    def record_phase(
        self, nodeid, phase, outcome, duration, worker_id="master", timestamp=None
    ):
        if not isinstance(nodeid, str) or not nodeid.strip():
            raise ValueError(f"Malformed node ID for journal: {nodeid}")
        if phase not in VALID_PHASES:
            raise ValueError(f"Invalid test phase: {phase}")
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"Invalid test outcome: {outcome}")
        if not math.isfinite(duration) or duration < 0:
            raise ValueError(f"Invalid phase duration: {duration}")
        entry = {
            "event": "phase",
            "nodeid": nodeid,
            "phase": phase,
            "outcome": outcome,
            "duration": round(float(duration), 6),
            "worker_id": str(worker_id or "master"),
            "timestamp": round(float(timestamp or time.time()), 6),
        }
        self._write_entry(entry)

    def record_finish(self, status="completed", exitstatus=0, timestamp=None):
        entry = {
            "event": "finish",
            "status": status,
            "exitstatus": exitstatus,
            "timestamp": round(float(timestamp or time.time()), 6),
        }
        self._write_entry(entry)

    def _write_entry(self, entry):
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
    """Parse JSONL journal lines, validating schemas and distinguishing trailing crash writes from internal corruption."""
    events = []
    path = Path(path)
    if not path.is_file():
        return events
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    non_empty_indices = [i for i, line in enumerate(lines) if line.strip()]
    last_idx = non_empty_indices[-1] if non_empty_indices else -1

    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as err:
            # Trailing partial write at EOF from abrupt process termination is recoverable
            if idx == last_idx:
                break
            # Internal corruption inside the journal is an integrity violation
            raise ValueError(
                f"Corrupted journal record at line {idx + 1}: {err}"
            ) from err

        if not isinstance(entry, dict):
            raise ValueError(
                f"Invalid journal record schema at line {idx + 1}: expected object"
            )
        ev_type = entry.get("event")
        if ev_type not in VALID_EVENTS:
            raise ValueError(f"Unknown event type in journal: {ev_type}")
        if ev_type == "phase":
            nodeid = entry.get("nodeid")
            if not isinstance(nodeid, str) or not nodeid.strip():
                raise ValueError(f"Malformed nodeid in journal phase event: {nodeid}")
            if entry.get("phase") not in VALID_PHASES:
                raise ValueError(
                    f"Invalid phase in journal event: {entry.get('phase')}"
                )
            if entry.get("outcome") not in VALID_OUTCOMES:
                raise ValueError(
                    f"Invalid outcome in journal event: {entry.get('outcome')}"
                )
            duration = entry.get("duration")
            if (
                not isinstance(duration, (int, float))
                or not math.isfinite(duration)
                or duration < 0
            ):
                raise ValueError(f"Invalid duration in journal phase event: {duration}")
        elif ev_type == "start":
            nodeid = entry.get("nodeid")
            if not isinstance(nodeid, str) or not nodeid.strip():
                raise ValueError(f"Malformed nodeid in journal start event: {nodeid}")
        events.append(entry)
    return events


def aggregate_journal(source):
    """Aggregate per-phase test events into per-test and per-file duration profiles with interruption recovery."""
    events = parse_journal(source) if isinstance(source, (str, Path)) else source
    tests = {}
    workers = set()
    finish_interrupted = False

    for ev in events:
        ev_type = ev.get("event")
        if ev_type == "finish":
            # Exit status 2 is pytest Interrupted (e.g. SIGINT/KeyboardInterrupt); 130 is SIGINT; 143 is SIGTERM
            if ev.get("status") == "interrupted" or ev.get("exitstatus") in (
                2,
                130,
                143,
            ):
                finish_interrupted = True
            continue

        nodeid = ev.get("nodeid")
        if not nodeid:
            continue
        worker = ev.get("worker_id", "master")
        workers.add(worker)

        test = tests.setdefault(
            nodeid,
            {
                "nodeid": nodeid,
                "file": nodeid.split("::")[0],
                "name": nodeid.split("::")[-1],
                "worker_id": worker,
                "phases": {"setup": 0.0, "call": 0.0, "teardown": 0.0},
                "phases_seen": [],
                "duration": 0.0,
                "status": "passed",
                "completed": False,
                "started": False,
            },
        )
        if worker != "master":
            test["worker_id"] = worker

        if ev_type == "start":
            test["started"] = True
            continue

        if ev_type == "phase":
            phase = ev.get("phase")
            duration = float(ev.get("duration", 0.0))
            outcome = ev.get("outcome", "passed")

            # Check for duplicate phase records
            if phase in test["phases_seen"]:
                raise ValueError(
                    f"Duplicate phase record for node: {nodeid}, phase: {phase}"
                )

            # Check phase ordering transitions
            if "teardown" in test["phases_seen"]:
                raise ValueError(
                    f"Invalid phase order for {nodeid}: {phase} after teardown"
                )
            if phase == "teardown" and "setup" not in test["phases_seen"]:
                raise ValueError(
                    f"Invalid phase order for {nodeid}: teardown before setup"
                )
            if phase == "call" and "setup" not in test["phases_seen"]:
                raise ValueError(f"Invalid phase order for {nodeid}: call before setup")

            test["phases_seen"].append(phase)
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
        # If test was interrupted (did not complete teardown), mark status
        if not test["completed"] and test["status"] != "failed":
            test["status"] = "interrupted"

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
    completed_passing = sum(
        1 for t in tests.values() if t["completed"] and t["status"] == "passed"
    )
    completed_failing = sum(
        1
        for t in tests.values()
        if t["completed"] and t["status"] in ("failed", "error")
    )
    skipped = sum(
        1 for t in tests.values() if t["completed"] and t["status"] == "skipped"
    )
    partial = len(tests) - completed
    cumulative_seconds = round(sum(t["duration"] for t in tests.values()), 6)
    timestamps = [
        ev["timestamp"]
        for ev in events
        if isinstance(ev.get("timestamp"), (int, float))
    ]
    wall_seconds = (
        round(max(timestamps) - min(timestamps), 6)
        if len(timestamps) >= 2
        else cumulative_seconds
    )

    return {
        "tests": list(tests.values()),
        "files": sorted(files.values(), key=lambda r: -r["seconds"]),
        "count": len(tests),
        "completed": completed,
        "completed_passing": completed_passing,
        "completed_failing": completed_failing,
        "skipped": skipped,
        "partial": partial,
        "interrupted": partial > 0 or finish_interrupted,
        "workers": sorted(workers),
        "cumulative_test_seconds": cumulative_seconds,
        "wall_seconds": wall_seconds,
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

    def pytest_runtest_logstart(self, nodeid, location):
        self.writer.record_start(nodeid)

    def pytest_runtest_logreport(self, report):
        worker = getattr(report, "node", None)
        gw = worker.gateway.id if worker else getattr(report, "worker_id", "master")
        self.writer.record_phase(
            report.nodeid,
            report.when,
            report.outcome,
            report.duration,
            worker_id=gw,
        )

    def pytest_sessionfinish(self, session, exitstatus):
        self.writer.record_finish(
            status="completed" if exitstatus == 0 else "failed",
            exitstatus=exitstatus,
        )
        self.writer.close()

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
