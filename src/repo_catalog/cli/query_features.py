"""Optional Context/paired/Search commands for the composed Query CLI."""

from __future__ import annotations

from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.cli import paired_query_features
from repo_catalog.domain.production_query import SEARCH_PROJECTION_KINDS, SearchQuery
from repo_catalog.domain.query_contracts import QueryError


def add_commands(sub, _add_common_args, _add_page_args):
    paired_query_features.add_commands(sub, _add_common_args, _add_page_args)

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
    return ProductionQueryService(directory, mode=mode)


def query_payload(service, args, page_from_args):
    cmd = args.command
    _page_from_args = page_from_args
    if cmd not in ("search", "search-rebuild"):
        return paired_query_features.query_payload(service, args, page_from_args)
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
