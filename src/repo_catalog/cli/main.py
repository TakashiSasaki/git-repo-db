"""Ordinary CLI composition for the separated persistence roles.

Each command delegates to its owning capability. No legacy backend fallback.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sqlite3
import sys

from repo_catalog._version import __version__

COMMANDS = {
    "init": "repo_catalog.cli.separated_init",
    "query": "repo_catalog.cli.separated_query",
    "context": "repo_catalog.cli.context_admin",
    "access": "repo_catalog.cli.access_admin",
    "acquire": "repo_catalog.cli.separated_acquisition",
    "exchange": "repo_catalog.cli.separated_exchange",
    "recovery": "repo_catalog.cli.separated_recovery",
    "doctor": "repo_catalog.cli.separated_doctor",
    "operations": "repo_catalog.cli.operations_admin",
    "reparse": "repo_catalog.cli.metadata_reparse",
    "identity": "repo_catalog.cli.separated_identity",
    "recording": "repo_catalog.cli.separated_recording",
}


def parser():
    result = argparse.ArgumentParser(prog="repo-catalog", description=__doc__)
    result.add_argument("--version", action="version", version=__version__)
    result.add_argument("command", choices=tuple(COMMANDS))
    return result


def main(argv=None):
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] in ("-h", "--help", "--version"):
        parser().parse_args(values)
    command = values.pop(0)
    if command not in COMMANDS:
        parser().error("unknown command: " + command)
    try:
        return importlib.import_module(COMMANDS[command]).main(values)
    except KeyboardInterrupt:
        print(
            json.dumps(
                {"status": "error", "code": "CANCELLED", "message": "Interrupted"}
            ),
            file=sys.stderr,
        )
        return 130
    except ModuleNotFoundError as error:
        if not error.name.startswith("repo_catalog."):
            raise
        print(
            json.dumps({"code": "MISSING_CAPABILITY", "module": error.name}),
            file=sys.stderr,
        )
        return 2
    except Exception as error:
        if not isinstance(error, (ValueError, OSError, sqlite3.Error)) and not hasattr(
            error, "code"
        ):
            raise
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": getattr(error, "code", "INVALID_ARGUMENT"),
                    "error_type": type(error).__name__,
                    "message": str(error),
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
