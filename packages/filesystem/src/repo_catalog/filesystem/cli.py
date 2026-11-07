"""Command line for the independent filesystem database."""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import asdict

from .models import FilesystemError
from .store import FilesystemCatalog


def _json(value):
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii")}
    raise TypeError(type(value).__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="repo-catalog-filesystem")
    parser.add_argument("--database", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init")
    initialize.add_argument("--namespace-uuid")
    scan = commands.add_parser("scan")
    scan.add_argument("root")
    scan.add_argument("--exclude", action="append", default=[])
    commands.add_parser("scans", aliases=["list"])
    commands.add_parser("verify")
    entries = commands.add_parser("entries")
    entries.add_argument("scan_uuid")
    export = commands.add_parser("export")
    export.add_argument("scan_uuid")
    export.add_argument("--output", required=True)
    export.add_argument("--allow-partial", action="store_true")
    export.add_argument("--skip-non-utf8", action="store_true")
    export.add_argument("--column", action="append", default=[])
    export.add_argument("--path-map", nargs=2, metavar=("SOURCE", "DESTINATION"))
    backup = commands.add_parser("backup")
    backup.add_argument("destination")
    restore = commands.add_parser("restore")
    restore.add_argument("source")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            with FilesystemCatalog.initialize(
                args.database, namespace_uuid=args.namespace_uuid
            ) as catalog:
                result = catalog.verify()
        elif args.command == "restore":
            with FilesystemCatalog.restore(args.source, args.database) as catalog:
                result = catalog.verify()
        else:
            with FilesystemCatalog.open(
                args.database, readonly=args.command != "scan"
            ) as catalog:
                if args.command == "scan":
                    result = asdict(catalog.scan(args.root, exclude_paths=args.exclude))
                elif args.command in ("scans", "list"):
                    result = [asdict(scan) for scan in catalog.list_scans()]
                elif args.command == "entries":
                    for entry in catalog.iter_entries(args.scan_uuid):
                        print(
                            json.dumps(asdict(entry), default=_json, ensure_ascii=True)
                        )
                    return 0
                elif args.command == "verify":
                    result = catalog.verify()
                elif args.command == "backup":
                    result = catalog.backup(args.destination)
                else:
                    result = asdict(
                        catalog.export_efu(
                            args.scan_uuid,
                            args.output,
                            allow_partial=args.allow_partial,
                            skip_non_utf8=args.skip_non_utf8,
                            extra_columns=args.column,
                            path_map=args.path_map,
                        )
                    )
                    result["status"] = "partial" if result["skipped"] else "complete"
        print(json.dumps(result, default=_json, ensure_ascii=True, sort_keys=True))
        return (
            2
            if isinstance(result, dict)
            and result.get("status") in ("partial", "interrupted", "incomplete")
            else 0
        )
    except (FilesystemError, OSError, ValueError) as exc:
        parser.exit(2, f"{type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
