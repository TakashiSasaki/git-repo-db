"""Shared finite read controls for the ordinary Query command families."""

import math
import time


def add_limits(parser):
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--max-store-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--max-rows", type=int, default=10_000)
    parser.add_argument("--max-sql-steps", type=int, default=5_000_000)


def read_limits(args):
    from repo_catalog.adapters.sqlite.catalog_runtime import SnapshotReadLimits

    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        raise ValueError("positive finite query timeout required")
    deadline = time.monotonic() + args.timeout_seconds
    return SnapshotReadLimits(
        max_store_bytes=args.max_store_bytes,
        max_total_rows=args.max_rows,
        max_sql_vm_steps=args.max_sql_steps,
        on_steps=lambda _: time.monotonic() > deadline,
    )
