"""Stdlib-only observed timing; records share the existing invocation family.

This module also runs under the bootstrap Python >=3.9. It does not import or
verify product code. Local timing data are never uploaded automatically.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc


def atomic_write_text(path: Path, content: str) -> None:
    """Write text to a temporary file in the destination directory and replace atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, encoding="utf-8"
    ) as tf:
        tf.write(content)
        tmp_name = tf.name
    os.replace(tmp_name, path)


class InvocationTiming:
    """Checkpoint timing in the existing invocation, even before a child exits.

    An unfinished phase has no invented end or duration. SIGKILL/power loss can
    only leave that checkpoint; ordinary exceptions retain the observed end.
    """

    def __init__(self, record, path):
        self.record = record
        self.path = path
        self.start = time.perf_counter()
        self.active = {}
        record["timing"] = {
            "version": 1,
            "status": "running",
            "task_id": os.environ.get("CI_TASK_ID"),
            "session_id": os.environ.get("CI_SESSION_ID"),
            "agent_id": os.environ.get("CI_AGENT_ID"),
            "parent_invocation_id": os.environ.get("CI_PARENT_INVOCATION_ID"),
            "kind": os.environ.get("CI_PHASE_KIND", "unclassified"),
            "started_at": datetime.now(UTC).isoformat(),
            "phases": [],
        }
        self.begin("preparation")

    def save(self):
        atomic_write_text(self.path, json.dumps(self.record, indent=2) + "\n")

    def begin(self, name):
        row = {"name": name, "started_at": datetime.now(UTC).isoformat()}
        self.record["timing"]["phases"].append(row)
        self.active[name] = (row, time.perf_counter())
        self.save()

    def end(self, name, exception=None):
        row, start = self.active.pop(name)
        row.update(
            completed_at=datetime.now(UTC).isoformat(),
            elapsed_seconds=time.perf_counter() - start,
        )
        if exception is not None:
            row["exception_type"] = type(exception).__name__
        self.save()

    @contextmanager
    def phase(self, name):
        self.begin(name)
        exception = None
        try:
            yield
        except BaseException as exc:
            exception = exc
            raise
        finally:
            self.end(name, exception)

    def finish(self, status, exception=None):
        for name in list(self.active):
            self.end(name, exception)
        self.record["timing"].update(
            status=status,
            completed_at=datetime.now(UTC).isoformat(),
            elapsed_seconds=time.perf_counter() - self.start,
        )
        if exception is not None:
            self.record["timing"]["exception_type"] = type(exception).__name__
        self.save()


def utc_now():
    return datetime.now(UTC).isoformat()


def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise ValueError(
            "Use a nonsecret ID of 1-128 letters, digits, dots, underscores or hyphens"
        )
    return value


def new_record(name, kind):
    return {
        "profile_version": 1,
        "invocation_id": f"{identifier(name)}-{uuid.uuid4().hex}",
        "name": name,
        "record_kind": kind,
        "measurement_only": True,
        "verified": False,
        "exit_code": None,
    }


def session_transition(
    output,
    session_id,
    action,
    *,
    task_id=None,
    reason=None,
    parent_id=None,
    interrupted=False,
):
    """Serialize explicit observations; cross-process durations use UTC, not perf_counter."""
    session_id = identifier(session_id)
    path = output / "invocations" / f"session-{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        now = utc_now()
        if action == "start":
            if path.exists():
                raise ValueError("Session already exists; choose a new session ID")
            if not task_id:
                raise ValueError("A nonsecret task ID is required")
            if parent_id == f"session-{session_id}":
                raise ValueError("A session cannot be its own parent")
            if reason or interrupted:
                raise ValueError("Start cannot pause or interrupt a session")
            record = new_record("session", "session")
            record["invocation_id"] = f"session-{session_id}"
            record["timing"] = {
                "version": 1,
                "status": "active",
                "kind": "work_session",
                "task_id": task_id,
                "session_id": session_id,
                "agent_id": os.environ.get("CI_AGENT_ID"),
                "parent_invocation_id": parent_id
                or os.environ.get("CI_PARENT_INVOCATION_ID"),
                "started_at": now,
                "duration_clock": "utc_cross_process",
                "phases": [{"name": "active", "started_at": now}],
            }
        else:
            record = json.loads(path.read_text())
            timing = record["timing"]
            state = timing["status"]
            if (
                record.get("record_kind") != "session"
                or timing["session_id"] != session_id
            ):
                raise ValueError("Not the requested session record")
            allowed = {
                "pause": {"active"},
                "resume": {"paused"},
                "end": {"active", "paused"},
            }
            if action not in allowed or state not in allowed[action]:
                raise ValueError(f"Cannot {action} a {state} session")
            if action == "pause" and reason not in {
                "approval_wait",
                "environment_wait",
                "deliberate_pause",
            }:
                raise ValueError(
                    "Pause requires approval_wait, environment_wait or deliberate_pause"
                )
            if action != "pause" and reason:
                raise ValueError("Reason belongs to a pause transition")
            if interrupted and action != "end":
                raise ValueError("Only end can mark an interrupted session")
            current = timing["phases"][-1]
            current["completed_at"] = now
            elapsed = (
                datetime.fromisoformat(now)
                - datetime.fromisoformat(current["started_at"])
            ).total_seconds()
            current["elapsed_seconds"] = elapsed if elapsed >= 0 else None
            if elapsed < 0:
                current["clock_error"] = "wall_clock_reversed"
            if action == "end":
                timing["status"] = "interrupted" if interrupted else "ended"
                timing["completed_at"] = now
                elapsed = (
                    datetime.fromisoformat(now)
                    - datetime.fromisoformat(timing["started_at"])
                ).total_seconds()
                timing["elapsed_seconds"] = elapsed if elapsed >= 0 else None
            else:
                timing["status"] = "paused" if action == "pause" else "active"
                phase = {
                    "name": "pause" if action == "pause" else "active",
                    "started_at": now,
                }
                if reason:
                    phase["reason"] = reason
                timing["phases"].append(phase)
        atomic_write_text(path, json.dumps(record, indent=2) + "\n")
    return path, record


def run_external(output, name, command, kind="preparation"):
    """Time external preparation without requiring/claiming a verified product runtime."""
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise ValueError("A command is required")
    record = new_record(name, "external")
    record["command"] = command
    path = output / "invocations" / (record["invocation_id"] + ".json")
    timing = InvocationTiming(record, path)
    record["timing"]["kind"] = kind
    timing.end("preparation")
    try:
        with timing.phase("command"), path.with_suffix(".log").open("wb") as log:
            result = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                env={**os.environ, "CI_PARENT_INVOCATION_ID": record["invocation_id"]},
                check=False,
            )
        record["exit_code"] = result.returncode
        timing.finish(
            "interrupted"
            if result.returncode < 0 or result.returncode in (130, 143)
            else "completed"
        )
    except BaseException as error:
        record["exit_code"] = 130 if isinstance(error, KeyboardInterrupt) else 2
        timing.finish(
            "interrupted" if isinstance(error, KeyboardInterrupt) else "error", error
        )
        raise
    return path, record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("start", "pause", "resume", "end"):
        item = actions.add_parser(action)
        item.add_argument("--output", type=Path, default=Path("artifacts/local-timing"))
        item.add_argument(
            "--session-id",
            default=os.environ.get("CI_SESSION_ID"),
            required=not os.environ.get("CI_SESSION_ID"),
        )
        if action == "start":
            item.add_argument("--task-id", default=os.environ.get("CI_TASK_ID"))
            item.add_argument("--parent-id")
        elif action == "pause":
            item.add_argument(
                "--reason",
                required=True,
                choices=("approval_wait", "environment_wait", "deliberate_pause"),
            )
        elif action == "end":
            item.add_argument("--interrupted", action="store_true")
    run = actions.add_parser("run")
    run.add_argument("--output", type=Path, default=Path("artifacts/local-timing"))
    run.add_argument("--name", required=True)
    run.add_argument(
        "--kind",
        choices=("preparation", "build_install", "review", "other"),
        default="preparation",
    )
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.action == "run":
            path, record = run_external(args.output, args.name, args.command, args.kind)
        else:
            path, record = session_transition(
                args.output,
                args.session_id,
                args.action,
                task_id=getattr(args, "task_id", None),
                reason=getattr(args, "reason", None),
                parent_id=getattr(args, "parent_id", None),
                interrupted=getattr(args, "interrupted", False),
            )
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f"Timing refused: {error}\n")
    print(
        json.dumps(
            {
                "invocation_id": record["invocation_id"],
                "status": record["timing"]["status"],
                "exit_code": record["exit_code"],
                "evidence": str(path),
            }
        )
    )
    return record["exit_code"] if args.action == "run" else 0


if __name__ == "__main__":
    raise SystemExit(main())
