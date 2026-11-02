"""Optional Search CLI with finite authority-capability composition."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from repo_catalog.domain.query_contracts import QueryError
from repo_catalog.domain.search_query import SEARCH_PROJECTION_KINDS, SearchQuery


def _available(name):
    return importlib.util.find_spec(name) is not None


def _pair_available():
    return _available("repo_catalog.application.paired_query")


def add_commands(sub, _add_common_args, _add_page_args):
    if _pair_available():
        from repo_catalog.cli import paired_query_features

        paired_query_features.add_commands(sub, _add_common_args, _add_page_args)
    elif _available("repo_catalog.application.context_query"):
        from repo_catalog.cli import context_query_features

        context_query_features.add_commands(sub, _add_common_args, _add_page_args)
    # search-rebuild
    p_sreb = sub.add_parser(
        "search-rebuild",
        help="Rebuild derivative search.sqlite3 projections from pinned authority",
    )
    _add_common_args(p_sreb)
    p_sreb.add_argument(
        "--kinds",
        default=",".join(SEARCH_PROJECTION_KINDS),
        help="Comma-separated projection kinds",
    )

    # search
    p_search = sub.add_parser(
        "search",
        help="Search across projection kinds with automatic authority_scan fallback",
    )
    _add_common_args(p_search)
    p_search.add_argument("--query", required=True)
    p_search.add_argument(
        "--kinds",
        default=",".join(SEARCH_PROJECTION_KINDS),
        help="Comma-separated projection kinds",
    )
    _add_page_args(p_search)


def query_service(directory, *, mode):
    if _pair_available():
        from repo_catalog.application.paired_search import PairedSearchService

        return PairedSearchService(directory, mode=mode)
    directory = Path(directory)
    if mode == "paired" or (
        mode == "auto"
        and (directory / "core.sqlite3").is_file()
        and (directory / "context.sqlite3").is_file()
    ):
        raise QueryError(
            "MISSING_CAPABILITY", "query", "paired Query integration is not installed"
        )
    context = mode == "context_only" or (
        mode == "auto"
        and not (directory / "core.sqlite3").is_file()
        and (directory / "context.sqlite3").is_file()
    )
    if context or not _available("repo_catalog.application.core_query"):
        if not _available("repo_catalog.application.context_query"):
            raise QueryError(
                "MISSING_CAPABILITY", "query", "Context Query is not installed"
            )
        from repo_catalog.application.context_search import ContextSearchService

        return ContextSearchService(directory, mode=mode)
    from repo_catalog.application.core_search import CoreSearchService

    return CoreSearchService(directory, mode=mode)


def query_payload(service, args, page_from_args):
    if args.command not in ("search", "search-rebuild"):
        if _pair_available():
            from repo_catalog.cli import paired_query_features

            return paired_query_features.query_payload(service, args, page_from_args)
        if _available("repo_catalog.application.context_query"):
            from repo_catalog.cli import context_query_features

            return context_query_features.query_payload(service, args, page_from_args)
        raise QueryError("MISSING_CAPABILITY", "cli", args.command)
    cmd = args.command
    _page_from_args = page_from_args
    if cmd == "search-rebuild":
        kinds = tuple(k.strip() for k in args.kinds.split(",") if k.strip())
        counts = service.rebuild_search(kinds)
        token = service.snapshot_token()
        payload = {
            "indexed_counts": counts,
            "snapshot_token": token.encode(),
        }
    elif cmd == "search":
        kinds = tuple(k.strip() for k in args.kinds.split(",") if k.strip())
        resp = service.search(
            SearchQuery(
                query_text=args.query,
                projection_kinds=kinds,
                limit=args.limit,
                cursor=args.cursor,
                expected_token=args.expected_token,
            )
        )
        payload = resp.to_dict()
    else:
        raise QueryError("UNKNOWN_COMMAND", "cli", str(cmd))
    return payload
