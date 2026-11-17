"""Read-only physical/schema/pairing diagnostics; never initializes missing stores."""

import argparse
import sqlite3
from pathlib import Path

from repo_catalog.application.separated_initialization import inspect_role
from repo_catalog.cli.separated_io import emit, failure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--verify-retained", action="store_true")
    parser.add_argument("--scope", choices=("git_only", "paired"))
    args = parser.parse_args(argv)
    if args.verify_retained and args.scope is None:
        parser.error("--verify-retained requires explicit --scope git_only or paired")
    try:
        roles = {}
        for role in ("core", "context", "operational", "search"):
            path = args.catalog / (role + ".sqlite3")
            if path.exists():
                roles[role] = inspect_role(path, role)
        if not roles:
            raise ValueError("AUTHORITY_UNAVAILABLE: no separated catalog role exists")
        if len(set(roles.values())) != 1:
            raise ValueError("PAIR_IDENTITY: roles belong to different catalogs")
        result = {
            "roles": roles,
            "stopped": (args.catalog / "p1-recovery-stop.json").exists(),
        }
        if args.verify_retained:
            from repo_catalog.application.catalog_diagnostics import verify_retained

            result["retained_authority"] = verify_retained(args.catalog, args.scope)
        emit(result)
        return 0
    except Exception as error:
        from repo_catalog.domain.recovery import RecoveryError

        if not isinstance(
            error, (ValueError, OSError, sqlite3.Error, RecoveryError)
        ) and not hasattr(error, "code"):
            raise
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
