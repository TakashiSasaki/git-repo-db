"""Attributed identity assertions; equivalence never merges physical authorities."""

import argparse
from contextlib import ExitStack
from pathlib import Path

from repo_catalog.cli.separated_io import (
    authority,
    decode,
    emit,
    failure,
    read_document,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("relation", "cancellation", "status"))
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--scope", required=True, choices=("core", "context", "paired"))
    parser.add_argument("--entity-kind", choices=("repository", "service"))
    parser.add_argument(
        "--input", help='JSON {"record": {...}, "provenance": tagged Provenance}'
    )
    parser.add_argument("--authority")
    args = parser.parse_args(argv)
    if args.command != "status" and args.input is None:
        parser.error("identity mutation requires --input")
    if args.command == "cancellation" and args.entity_kind is None:
        parser.error("cancellation requires --entity-kind before its assertion exists")
    if args.command != "status" and args.scope == "paired":
        parser.error("choose the owning core or context scope for one assertion")
    if args.command != "status" and args.scope == "context" and args.authority is None:
        parser.error("Context identity admission requires --authority")
    try:
        from repo_catalog.application.identity_assertions import IdentityAssertions

        with ExitStack() as stack:
            core, context = None, None
            if args.scope in ("core", "paired"):
                from repo_catalog.adapters.sqlite.git_core import GitCore

                core = GitCore(args.catalog / "core.sqlite3")
                stack.callback(core.close)
            if args.scope in ("context", "paired"):
                from repo_catalog.adapters.sqlite.production_context import Context

                if args.command == "status":
                    context = stack.enter_context(Context.snapshot(args.catalog))
                else:
                    auth, admission, _ = authority(args.authority, "provider_intake")
                    context = stack.enter_context(
                        Context.transaction(
                            args.catalog, authorization=auth, admission=admission
                        )
                    )
            app = IdentityAssertions(core=core, context=context)
            if args.command == "status":
                result = app.status()
            else:
                document = decode(read_document(args.input))
                result = app.admit(
                    args.command,
                    document["record"],
                    document["provenance"],
                    entity_kind=args.entity_kind,
                )
        emit(result)
        return 0
    except Exception as error:
        if not isinstance(
            error, (ValueError, OSError, KeyError, TypeError)
        ) and not hasattr(error, "code"):
            raise
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
