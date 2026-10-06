"""Test-only fresh process: deterministic faults/protection probes."""

import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

if os.environ.get("TEST_SQLITE_MINIMUM"):
    from scripts.sqlite_minimum import activate

    activate()
import sqlite3  # noqa: E402

if os.environ.get("TEST_SQLITE_MINIMUM"):
    assert sqlite3.sqlite_version == os.environ["TEST_SQLITE_MINIMUM"]

from scripts.conversion import engine, guards, source, target
from scripts.conversion.common import ConversionError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument(
        "--action",
        choices=("archive", "verify", "handoff", "verify-phase"),
        default="archive",
    )
    parser.add_argument("--fault")
    parser.add_argument("--fault-table")
    parser.add_argument("--hard-exit", action="store_true")
    parser.add_argument("--spill", action="store_true")
    parser.add_argument("--probe")
    parser.add_argument("--free", type=int)
    parser.add_argument("--max-batches", type=int)
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
            "source-open": lambda: original.write_bytes(b"bad"),
            "source-sqlite": lambda: sqlite3.connect(original).execute(
                "DELETE FROM catalog_meta"
            ),
            "source-hardlink-open": lambda: (
                args.workspace / "input-alias"
            ).write_bytes(b"bad"),
            "cache-hardlink-open": lambda: (args.workspace / "input-alias").write_bytes(
                b"bad"
            ),
            "source-ro": lambda: write_sql(args.workspace / "source.sqlite3"),
            "cache-open": lambda: (cache / "objects/evidence").write_bytes(b"bad"),
            "cache-unlink": lambda: (cache / "objects/evidence").unlink(),
            "cache-ref": lambda: (cache / "new-ref").write_text("bad"),
            "cache-chmod": lambda: (cache / "objects/evidence").chmod(0o777),
            "git-fetch": lambda: subprocess.run(
                ["git", "-C", str(cache), "fetch"], check=True
            ),
            "git-gc": lambda: subprocess.run(
                ["git", "-C", str(cache), "gc"], check=True
            ),
            "git-prune": lambda: subprocess.run(
                ["git", "-C", str(cache), "prune"], check=True
            ),
            "git-ref": lambda: subprocess.run(
                ["git", "-C", str(cache), "update-ref", "refs/heads/a", "0" * 40],
                check=True,
            ),
            "git-lazy": lambda: subprocess.run(
                ["git", "-C", str(cache), "cat-file", "-p", "0" * 40], check=True
            ),
            "rest": lambda: urllib.request.urlopen(
                "http://127.0.0.1:80/repos/synthetic/repo"
            ),
            "graphql": lambda: urllib.request.urlopen(
                urllib.request.Request(
                    "http://127.0.0.1:80/graphql",
                    data=b'{"query":"query { viewer { login } }"}',
                )
            ),
            "http": lambda: socket.create_connection(("127.0.0.1", 80)),
            "raw-socket": raw_socket,
            "raw-exec": raw_exec,
            "cache-dirfd": lambda: raw_dirfd(cache),
            "attach": lambda: attach(args.workspace / "source.sqlite3", original),
        }
        try:
            operations[args.probe]()
        except (PermissionError, OSError, sqlite3.Error):
            return {"denied": args.probe}
        raise AssertionError("PROBE_NOT_DENIED")

    fired = False
    spilling_connection = None
    if args.spill:
        connect = target.connect

        def spilling(path):
            nonlocal spilling_connection
            db = connect(path)
            db.execute("PRAGMA cache_size=1")
            db.execute("PRAGMA cache_spill=1")
            spilling_connection = db
            return db

        target.connect = spilling

    def fault(point, **context):
        nonlocal fired
        if (
            point == args.fault
            and not fired
            and (args.fault_table is None or args.fault_table == context.get("table"))
        ):
            fired = True
            if args.spill and point == "before_handoff_commit":
                flush_target(spilling_connection)
            if args.hard_exit:
                os._exit(77)
            if args.fault == "after_data":
                raise sqlite3.OperationalError("database or disk is full")
            raise ConversionError("INJECTED_FAILURE")

    if args.action != "archive":
        return engine.run(
            policy,
            args.action,
            args.workspace,
            **({"fault": fault} if args.action == "handoff" else {}),
        )
    return engine.run(
        policy,
        "archive",
        args.workspace,
        batch_size=2,
        map_repositories=True,
        free_bytes=args.free,
        max_batches=args.max_batches,
        fault=fault,
    )


def flush_target(db):
    """Test-only transient metadata pressure spills the pending receipt.

    Restore the exact parent manifest before termination; neither temporary
    padding nor the inserted phase receipt may survive rollback recovery.
    SQLite writes normally through the same guarded target connection.
    """
    parent = db.execute(
        "SELECT id,manifest FROM conversion_runs WHERE parser_version='p2-archive/1'"
    ).fetchone()
    padded = json.loads(parent["manifest"])
    padded["test_spill_padding"] = "x" * (8 * 1024 * 1024)
    db.execute(
        "UPDATE conversion_runs SET manifest=? WHERE id=?",
        (json.dumps(padded), parent["id"]),
    )
    db.execute(
        "UPDATE conversion_runs SET manifest=? WHERE id=?",
        (parent["manifest"], parent["id"]),
    )


def write_sql(path):
    with source.readonly(path) as db:
        db.execute("UPDATE catalog_meta SET publication_seq=123")


def attach(path, original):
    with source.readonly(path) as db:
        db.execute("ATTACH DATABASE ? AS other", (str(original),))


def raw_socket():
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.socket(2, 1, 0)
    if fd == -1:
        raise OSError(ctypes.get_errno(), "socket denied")
    os.close(fd)


def raw_exec():
    libc = ctypes.CDLL(None, use_errno=True)
    argv = (ctypes.c_char_p * 2)(b"/bin/true", None)
    env = (ctypes.c_char_p * 1)(None)
    if libc.execve(b"/bin/true", argv, env) == -1:
        raise OSError(ctypes.get_errno(), "exec denied")


def raw_dirfd(cache):
    directory = os.open(cache / "objects", os.O_DIRECTORY | os.O_RDONLY)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        fd = libc.openat(directory, b"evidence", os.O_WRONLY)
        if fd == -1:
            raise OSError(ctypes.get_errno(), "FD-relative open denied")
        os.close(fd)
    finally:
        os.close(directory)


if __name__ == "__main__":
    try:
        print(json.dumps({**main(), "_sqlite_version": sqlite3.sqlite_version}))
    except (ConversionError, sqlite3.Error, OSError) as exc:
        print(
            json.dumps({"code": getattr(exc, "code", "STORAGE_FAILURE")}),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
