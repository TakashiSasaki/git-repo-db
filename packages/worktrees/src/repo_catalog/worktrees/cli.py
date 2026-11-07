"""Standalone topology CLI; no discovery or mutation during argument parsing."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from .catalog import WorktreeCatalog
from .models import WorktreeError, json_value


def main(argv=None):
    parser = argparse.ArgumentParser(prog="repo-catalog-worktrees")
    parser.add_argument("--database", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--namespace-uuid")
    discover = commands.add_parser("discover")
    discover.add_argument("path")
    discover.add_argument("--no-expand", action="store_true")
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("observation_uuid")
    link = commands.add_parser("link")
    link.add_argument("common_dir")
    link.add_argument("repository_uuid")
    commands.add_parser("verify")
    backup = commands.add_parser("backup")
    backup.add_argument("destination")
    restore = commands.add_parser("restore")
    restore.add_argument("backup")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            with WorktreeCatalog.initialize(
                args.database, namespace_uuid=args.namespace_uuid
            ) as catalog:
                result = catalog.verify()
        elif args.command == "restore":
            with WorktreeCatalog.restore(args.backup, args.database) as catalog:
                result = catalog.verify()
        else:
            with WorktreeCatalog.open(
                args.database, readonly=args.command not in ("discover", "link")
            ) as catalog:
                if args.command == "discover":
                    result = catalog.discover(args.path, expand=not args.no_expand)
                elif args.command == "list":
                    result = catalog.list_discoveries()
                elif args.command == "show":
                    result = catalog.get_discovery(args.observation_uuid)
                elif args.command == "verify":
                    result = catalog.verify()
                elif args.command == "backup":
                    result = catalog.backup(args.destination)
                elif args.command == "link":
                    catalog.link_repository(args.common_dir, args.repository_uuid)
                    result = {
                        "repository_uuids": catalog.repository_links(args.common_dir)
                    }
        print(json.dumps(json_value(result), ensure_ascii=True, sort_keys=True))
        if args.command == "discover" and result.status in ("partial", "error"):
            return 2
        return 0
    except (WorktreeError, OSError, sqlite3.Error, ValueError) as error:
        print(
            json.dumps(
                {"error": getattr(error, "code", "IO"), "message": str(error)},
                ensure_ascii=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
