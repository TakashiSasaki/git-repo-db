"""Provider/Source inventories, resource documents and candidate-aware filtering."""

import argparse

from repo_catalog.cli.query_limits import add_limits, read_limits
from repo_catalog.cli.separated_io import emit, failure, invocation

METHODS = {
    "providers": "list_providers",
    "sources": "list_source_views",
    "resource": "get_context_resource",
    "text": "read_context_text",
    "context-coverage": "get_context_coverage",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(*METHODS, "resources"))
    parser.add_argument("--catalog", required=True)
    parser.add_argument(
        "--mode",
        choices=("auto", "core_only", "context_only", "paired"),
        default="auto",
    )
    parser.add_argument(
        "--input",
        help='JSON {"args": [...], "kwargs": {...}}; resources accepts page, field_filters, text_literal, parent, namespace/repository filters',
    )
    add_limits(parser)
    args = parser.parse_args(argv)
    try:
        from repo_catalog.application.production_query import ProductionQueryService

        service = ProductionQueryService(
            args.catalog, mode=args.mode, read_limits=read_limits(args)
        )
        positional, keywords = invocation(args.input) if args.input else ((), {})
        if args.command == "resources":
            from repo_catalog.application.context_browse import browse

            if positional:
                raise ValueError("resources accepts keyword filters only")
            result = browse(service, **keywords)
        else:
            result = getattr(service, METHODS[args.command])(*positional, **keywords)
            if args.command == "sources":
                result = [view.to_dict() for view in result]
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
