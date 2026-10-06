"""Actual guarded integrated persistence, process interruption and guard probes."""

import argparse
import json
import os
import socket
import sys
from pathlib import Path

if os.environ.get("TEST_SQLITE_MINIMUM"):
    from scripts.sqlite_minimum import activate

    activate()
import sqlite3  # noqa: E402

from scripts.conversion import engine, guards, target  # noqa: E402
from scripts.conversion.common import ConversionError  # noqa: E402


def flush_target(db):
    """Force journal spill without importing another process's SQLite bootstrap."""
    parent = db.execute(
        "SELECT id,manifest FROM conversion_runs WHERE parser_version='p2-archive/1'"
    ).fetchone()
    padded = json.loads(parent["manifest"])
    padded["synthetic_test_spill"] = "x" * (8 * 1024 * 1024)
    db.execute(
        "UPDATE conversion_runs SET manifest=? WHERE id=?",
        (json.dumps(padded), parent["id"]),
    )
    db.execute(
        "UPDATE conversion_runs SET manifest=? WHERE id=?",
        (parent["manifest"], parent["id"]),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--fault")
    parser.add_argument("--fault-table")
    parser.add_argument("--spill", action="store_true")
    parser.add_argument("--probe", choices=("network", "source-write", "cache-write"))
    args = parser.parse_args()
    metadata = json.loads((args.workspace / "sealed.json").read_bytes())
    original = Path(metadata["original"]["path"])
    caches = [Path(item["path"]) for item in metadata["caches"]]
    policy = guards.install(
        args.workspace,
        [
            original,
            args.workspace / "source.sqlite3",
            args.workspace / "sealed.json",
            *caches,
        ],
    )
    if args.probe:
        try:
            if args.probe == "network":
                socket.create_connection(("127.0.0.1", 80))
            elif args.probe == "source-write":
                original.write_bytes(b"bad")
            else:
                (caches[0] / "synthetic-evidence").write_bytes(b"bad")
        except (PermissionError, OSError):
            return {"denied": args.probe}
        raise AssertionError("PROBE_NOT_DENIED")
    active = None
    if args.spill:
        connect = target.connect

        def spilling(path):
            nonlocal active
            active = connect(path)
            active.execute("PRAGMA cache_size=1")
            active.execute("PRAGMA cache_spill=1")
            return active

        target.connect = spilling

    def fault(point, **context):
        if point == args.fault and (
            args.fault_table is None or args.fault_table == context.get("table")
        ):
            if args.spill and point.startswith("before_"):
                flush_target(active)
            os._exit(77)

    return engine.run(policy, "stored", args.workspace, batch_size=2, fault=fault)


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except (ConversionError, OSError, sqlite3.Error, ValueError) as exc:
        print(
            json.dumps({"code": getattr(exc, "code", "STORAGE_FAILURE")}),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
