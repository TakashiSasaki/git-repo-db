"""Opt-in Access backup/inspect/fresh restore/fork. No transport or grant activation.

Explicit noninteractive administration is allowed: no commands touch live Git or
credentials. Restore always uses a new destination directory and disables routes.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from repo_catalog.adapters.sqlite.access_backup import AccessBackup
from repo_catalog.application.access_maintenance import AccessMaintenance
from repo_catalog.domain.access_backup import AccessBackupLimits
from repo_catalog.domain.access_registry import AccessRegistryError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--max-bytes", type=int, default=256 * 1024 * 1024)
    result.add_argument("--max-rows", type=int, default=100_000)
    result.add_argument("--timeout-seconds", type=int, default=60)
    commands = result.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--access-db", required=True)
    backup.add_argument("--destination", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--bundle", required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--bundle", required=True)
    restore.add_argument("--destination", required=True)
    fork = commands.add_parser("fork")
    fork.add_argument("--access-db", required=True)
    fork.add_argument("--source-scope", required=True)
    fork.add_argument("--scope-uri", required=True)
    fork.add_argument("--display-name", default="")
    fork.add_argument("--target-scope")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        limits = AccessBackupLimits(args.max_bytes, args.max_rows, args.timeout_seconds)
        app = AccessMaintenance(AccessBackup(limits))
        if args.command == "backup":
            result = app.backup(args.access_db, args.destination)
        elif args.command == "inspect":
            result = app.inspect(args.bundle)
        elif args.command == "restore":
            result = app.restore(args.bundle, args.destination)
        else:
            result = app.fork_scope(
                args.access_db,
                args.source_scope,
                args.scope_uri,
                display_name=args.display_name,
                target_scope_uuidv4=args.target_scope,
            )
        print(
            json.dumps(
                {"status": "ok", "operation": args.command, "result": result},
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 0
    except AccessRegistryError as error:
        print(json.dumps({"status": "error", "code": error.code}), file=sys.stderr)
    except (OSError, sqlite3.Error, KeyboardInterrupt):
        print('{"status":"error","code":"ACCESS_MAINTENANCE_FAILED"}', file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
