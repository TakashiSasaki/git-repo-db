"""Initialize only explicitly selected separated responsibility roles."""

import argparse
import sqlite3
from pathlib import Path

from repo_catalog.cli.separated_io import emit, failure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        required=True,
        choices=(
            "core",
            "context",
            "paired",
            "access",
            "operational",
            "search",
            "filesystem",
            "worktrees",
        ),
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--repository")
    parser.add_argument("--instance")
    args = parser.parse_args(argv)
    try:
        if args.scope in ("access", "filesystem", "worktrees"):
            if args.repository or args.instance:
                parser.error("--repository/--instance apply only to catalog roles")
            if args.scope == "access":
                from repo_catalog.adapters.sqlite.access_schema import (
                    initialize,
                    open_checked,
                )

                path = args.catalog / "access.sqlite3"
                reused = path.exists()
                if reused:
                    db, _ = open_checked(path)
                    db.close()
                else:
                    args.catalog.mkdir(parents=True, exist_ok=True)
                    initialize(path)
                result = {
                    "created": [] if reused else ["access"],
                    "reused": ["access"] if reused else [],
                }
            else:
                if args.scope == "filesystem":
                    from repo_catalog.filesystem.store import (
                        FilesystemCatalog as Catalog,
                    )
                else:
                    from repo_catalog.worktrees.catalog import (
                        WorktreeCatalog as Catalog,
                    )
                path = args.catalog / (args.scope + ".sqlite3")
                args.catalog.mkdir(parents=True, exist_ok=True)
                with (
                    Catalog.open(path, readonly=True)
                    if path.exists()
                    else Catalog.initialize(path)
                ) as catalog:
                    result = catalog.verify()
        else:
            from repo_catalog.application.separated_initialization import initialize

            result = initialize(
                args.catalog,
                args.scope,
                repository=args.repository,
                instance=args.instance,
            )
        emit(result)
        return 0
    except (ValueError, OSError, sqlite3.Error) as error:
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
