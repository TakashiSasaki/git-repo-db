"""Explicit Repository-only or paired backup, stop, salvage, restore, merge and activation."""

import argparse

from repo_catalog.cli.separated_io import authority, emit, failure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("backup", "stop", "status", "salvage", "restore", "merge", "activate"),
    )
    parser.add_argument("--scope", choices=("git_only", "paired"), required=True)
    parser.add_argument("--catalog", required=True)
    for key in ("output", "input", "repository", "reason", "request-id", "authority"):
        parser.add_argument("--" + key)
    parser.add_argument("--max-records", type=int, default=100_000)
    parser.add_argument("--max-bytes", type=int, default=512 * 1024 * 1024)
    args = parser.parse_args(argv)
    required = {
        "backup": ("output",),
        "stop": ("reason",),
        "salvage": ("output",),
        "restore": ("input", "repository"),
        "merge": ("input",),
        "activate": ("output",),
    }
    for key in required.get(args.command, ()):
        if not getattr(args, key):
            parser.error("--" + key + " is required for " + args.command)
    try:
        from repo_catalog.application.repository_recovery import (
            RepositoryRecoveryService,
        )
        from repo_catalog.domain.recovery import BackupScope, RecoveryBudget

        if args.scope == "paired":
            from repo_catalog.application.recovery import RecoveryService

            service = RecoveryService()
        else:
            service = RepositoryRecoveryService()
        scope = BackupScope(args.scope)
        budget = RecoveryBudget(
            max_input_records=args.max_records, max_input_bytes=args.max_bytes
        )
        if args.command == "backup":
            result = service.create_consistent_backup(args.catalog, args.output, scope)
        elif args.command == "stop":
            service.stop_suspect_catalog(args.catalog, args.reason)
            result = {"stopped": True}
        elif args.command == "status":
            result = {"stopped": service.is_stopped(args.catalog)}
        elif args.command == "salvage":
            result = service.extract_salvage(
                args.catalog,
                args.output,
                budget=budget,
                request_id=args.request_id,
                scope=scope,
            )
        elif args.command == "restore":
            result = service.restore_backup(args.input, args.catalog, args.repository)
        elif args.command == "merge":
            kwargs = {}
            if args.scope == "paired":
                if not args.authority:
                    parser.error("paired merge requires --authority")
                auth, admission, _ = authority(args.authority, "salvage_merge")
                kwargs = {"authorization": auth, "admission": admission}
            result = service.merge_salvage(
                args.catalog,
                args.input,
                budget=budget,
                request_id=args.request_id,
                **kwargs,
            )
        else:
            result = service.activate_catalog(args.catalog, args.output)
        emit(result)
        return 0
    except Exception as error:
        from repo_catalog.domain.recovery import RecoveryError

        if not isinstance(error, (RecoveryError, ValueError, OSError)):
            raise
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
