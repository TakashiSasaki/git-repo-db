"""Portable Provider and Source facts via locally authorized Context admission."""

import argparse

from repo_catalog.cli.separated_io import (
    authority,
    emit,
    failure,
    invocation,
)

METHODS = {
    "provider": "provider",
    "repository": "repository",
    "source": "source",
    "associate-source": "associate_source",
    "inventory": "inventory",
    "scope": "scope",
    "coverage": "admit_coverage",
    "mapping": "admit_repository_relation",
    "disposition": "admit_mapping_disposition",
    "observe": "observe",
    "relation": "relation",
    "collection": "collection",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=tuple(METHODS))
    parser.add_argument("--catalog", required=True)
    parser.add_argument(
        "--authority",
        required=True,
        help="Explicit finite local grants and selection document",
    )
    parser.add_argument(
        "--input",
        required=True,
        help='JSON {"args": [...], "kwargs": {...}} with public DTO tags',
    )
    args = parser.parse_args(argv)
    try:
        from repo_catalog.adapters.sqlite.production_context import Context

        service, admission, _ = authority(args.authority, "provider_intake")
        positional, keywords = invocation(args.input)
        with Context.transaction(
            args.catalog, authorization=service, admission=admission
        ) as store:
            result = getattr(store, METHODS[args.command])(*positional, **keywords)
        emit({"operation": args.command, "result": result})
        return 0
    except (ValueError, OSError, TypeError, KeyError) as error:
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
