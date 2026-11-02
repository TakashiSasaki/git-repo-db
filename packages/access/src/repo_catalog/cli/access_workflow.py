"""Explicit opt-in Access review/approval/local-directory preflight.

Run with python -m repo_catalog.cli.access_workflow. This module is NOT imported
by the normal CLI. No --yes, imported consent, credentials, shell or Git execution.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from repo_catalog.adapters.filesystem.access_executor import LocalDirectoryExecutor
from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.application.access_workflow import AccessWorkflow
from repo_catalog.domain.access_connections import AssignmentKey
from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    ScopeLocatorRegistration,
)
from repo_catalog.domain.access_workflow import AccessSelection


def _confirm(document: dict) -> bool:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise AccessRegistryError(
            "LOCAL_TTY_REQUIRED", "interactive local terminal required"
        )
    plan = document["plan"]
    expected = (
        document["operation"]
        + " "
        + plan["scope_uuidv4"]
        + " "
        + plan["repository_uuidv4"]
    )
    # ASCII JSON escapes controls/bidi/Unicode rather than terminal-interpreting them.
    sys.stderr.write(
        json.dumps(document, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    )
    sys.stderr.write(
        "Type exactly to confirm (otherwise decline): " + expected + "\n> "
    )
    sys.stderr.flush()
    return sys.stdin.readline(256).rstrip("\r\n") == expected


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("review", "approve", "preflight"))
    result.add_argument("--access-db", required=True)
    result.add_argument("--repository", required=True)
    result.add_argument("--scope", required=True)
    result.add_argument("--locator")
    result.add_argument("--profile")
    result.add_argument("--scope-uri")
    result.add_argument("--registered-at-us", type=int)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    if bool(args.locator) != bool(args.profile):
        arguments.error("--locator and --profile must be supplied together")
    if (args.scope_uri is None) != (args.registered_at_us is None):
        arguments.error("--scope-uri and --registered-at-us must be supplied together")
    try:
        selection = AccessSelection(
            args.repository,
            args.scope,
            None
            if args.locator is None
            else AssignmentKey(args.scope, args.locator, args.profile),
            None
            if args.scope_uri is None
            else ScopeLocatorRegistration(
                args.scope, args.registered_at_us, args.scope_uri
            ),
        )
        # Reject noninteractive mutations/probes before opening any writable store.
        if args.command != "review" and (
            not sys.stdin.isatty() or not sys.stderr.isatty()
        ):
            raise AccessRegistryError(
                "LOCAL_TTY_REQUIRED", "interactive local terminal required"
            )
        with AccessConnections(
            args.access_db, writable=args.command == "approve"
        ) as store:
            with AccessWorkflow(store) as workflow:
                if args.command == "review":
                    output = {
                        "status": "review-only",
                        "plan": workflow.inspect(selection),
                    }
                elif args.command == "approve":
                    grant = workflow.approve(workflow.begin_review(selection), _confirm)
                    output = {
                        "status": "approved-locally",
                        "approved_at_us": grant.approved_at_us,
                    }
                else:
                    token = workflow.activate(
                        selection, LocalDirectoryExecutor(), _confirm
                    )

                    # This operation only inspects the pinned directory, not Git
                    # contents or a catalog. A4 must supply its real P7 stop guard.
                    def inspect(fd):
                        info = os.fstat(fd)
                        return {"device": info.st_dev, "inode": info.st_ino}

                    output = {
                        "status": "local-directory-preflight-only",
                        "directory": workflow.dispatch_once(
                            token, inspect, guard=lambda: None
                        ),
                        "git_acquired": False,
                    }
        print(json.dumps(output, ensure_ascii=True, sort_keys=True))
        return 0
    except AccessRegistryError as error:
        print(json.dumps({"status": "error", "code": error.code}), file=sys.stderr)
        return 2
    except (OSError, EOFError, KeyboardInterrupt):
        print('{"status":"error","code":"LOCAL_OPERATION_FAILED"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
