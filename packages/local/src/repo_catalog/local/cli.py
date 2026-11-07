"""Explicit composition commands; package installation creates no databases."""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

from .service import LocalCatalog


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return {"native_path_base64": base64.b64encode(value).decode("ascii")}
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="repo-catalog-local")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "scan", "export"):
        command = commands.add_parser(name)
        command.add_argument("--filesystem-db", required=True, type=Path)
        command.add_argument("--worktrees-db", required=name != "export", type=Path)
        if name == "init":
            command.add_argument("--namespace")
        elif name == "scan":
            command.add_argument("roots", nargs="+", type=Path)
            command.add_argument("--include-git-admin", action="store_true")
        else:
            command.add_argument("--scan", required=True, action="append")
            command.add_argument("--output", required=True, type=Path)
            command.add_argument("--allow-partial", action="store_true")
            command.add_argument("--skip-non-utf8", action="store_true")
            command.add_argument("--extra-column", action="append", default=[])
            command.add_argument(
                "--path-map", nargs=2, metavar=("SOURCE", "DESTINATION")
            )
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            with LocalCatalog.initialize(
                args.filesystem_db, args.worktrees_db, namespace_uuid=args.namespace
            ) as catalog:
                result = {"namespace_uuid": catalog.filesystem.namespace_uuid}
        else:
            with LocalCatalog.open(
                args.filesystem_db,
                args.worktrees_db,
                readonly=args.command == "export",
            ) as catalog:
                if args.command == "scan":
                    result = catalog.scan(
                        args.roots, include_git_admin=args.include_git_admin
                    )
                else:
                    result = catalog.export_efu(
                        args.scan,
                        args.output,
                        allow_partial=args.allow_partial,
                        extra_columns=args.extra_column,
                        skip_non_utf8=args.skip_non_utf8,
                        path_map=tuple(args.path_map) if args.path_map else None,
                    )
        payload = _jsonable(result)
        status = getattr(result, "status", "complete")
        if getattr(result, "skipped", 0):
            status = "partial"
        if isinstance(payload, dict):
            payload["status"] = status
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
        return 0 if status == "complete" else 2
    except (OSError, ValueError, sqlite3.Error) as error:
        print(
            json.dumps({"error": type(error).__name__, "message": str(error)}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
