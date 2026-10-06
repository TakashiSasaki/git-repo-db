"""Fresh guarded P3B process with deterministic termination/spill probes."""

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

if os.environ.get("TEST_SQLITE_MINIMUM"):
    from scripts.sqlite_minimum import activate

    activate()
import sqlite3  # noqa: E402

from scripts.conversion import engine, guards, target  # noqa: E402
from scripts.conversion.common import ConversionError  # noqa: E402


def flush_target(db):
    """Force real journal spill; restore exact historical receipt in-tx."""
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
    parser.add_argument(
        "--action",
        choices=("identity-init", "identity", "verify-identity"),
        default="identity",
    )
    parser.add_argument("--fault")
    parser.add_argument("--fault-table")
    parser.add_argument("--hard-exit", action="store_true")
    parser.add_argument("--spill", action="store_true")
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--probe")
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
    metadata = json.loads((args.workspace / "sealed.json").read_bytes())
    original = Path(metadata["original"]["path"])
    cache = Path(metadata["caches"][0]["path"])
    policy = guards.install(
        args.workspace,
        [
            original,
            args.workspace / "source.sqlite3",
            args.workspace / "sealed.json",
            cache,
        ],
    )
    if args.probe:
        operations = {
            "source-write": lambda: original.write_bytes(b"bad"),
            "copy-write": lambda: (args.workspace / "source.sqlite3").write_bytes(
                b"bad"
            ),
            "cache-write": lambda: (cache / "synthetic-evidence").write_bytes(b"bad"),
            "network": lambda: socket.create_connection(("127.0.0.1", 80)),
            "child": lambda: subprocess.run(["/bin/true"], check=True),
        }
        try:
            operations[args.probe]()
        except (PermissionError, OSError, sqlite3.Error):
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
    fired = False

    def fault(point, **context):
        nonlocal fired
        if (
            point == args.fault
            and not fired
            and (args.fault_table is None or args.fault_table == context.get("table"))
        ):
            fired = True
            if args.spill and point.startswith("before_"):
                flush_target(active)
            if args.hard_exit:
                os._exit(77)
            raise ConversionError("INJECTED_FAILURE")

    options = {"contract": args.contract} if args.contract else {}
    if args.action != "verify-identity":
        options.update(fault=fault, batch_size=2)
    if args.action == "identity":
        options["max_batches"] = args.max_batches
    return engine.run(policy, args.action, args.workspace, **options)


if __name__ == "__main__":
    try:
        print(json.dumps({**main(), "_sqlite_version": sqlite3.sqlite_version}))
    except (ConversionError, OSError, sqlite3.Error, ValueError) as exc:
        print(
            json.dumps({"code": getattr(exc, "code", "STORAGE_FAILURE")}),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
