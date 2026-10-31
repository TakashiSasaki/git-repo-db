"""Optional Context/paired/Search commands for the composed Query CLI."""

from __future__ import annotations

from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.production_query import SEARCH_PROJECTION_KINDS, SearchQuery
from repo_catalog.domain.query_contracts import QueryError


def add_commands(sub, _add_common_args, _add_page_args):
    # context-resource
    p_cres = sub.add_parser(
        "context-resource", help="Query a single Context resource by ResourceKey"
    )
    _add_common_args(p_cres)
    p_cres.add_argument("--service", required=True)
    p_cres.add_argument("--kind", required=True)
    p_cres.add_argument(
        "--id", required=True, help="Serialized canonical Resource identity JSON TEXT"
    )

    # context-resources
    p_cress = sub.add_parser(
        "context-resources", help="List Context resources with pagination"
    )
    _add_common_args(p_cress)
    p_cress.add_argument("--service", default=None)
    p_cress.add_argument("--kind", default=None)
    p_cress.add_argument("--repository", default=None)
    _add_page_args(p_cress)

    # paired-resource
    p_pres = sub.add_parser(
        "paired-resource",
        help="Query a paired Context resource with Core OID resolution",
    )
    _add_common_args(p_pres)
    p_pres.add_argument("--service", required=True)
    p_pres.add_argument("--kind", required=True)
    p_pres.add_argument(
        "--id", required=True, help="Serialized canonical Resource identity JSON TEXT"
    )
    p_pres.add_argument("--include-core-bytes", action="store_true")

    # paired-resources
    p_press = sub.add_parser(
        "paired-resources",
        help="List paired Context resources with Core OID resolution",
    )
    _add_common_args(p_press)
    p_press.add_argument("--kind", default=None)
    p_press.add_argument("--repository", default=None)
    _add_page_args(p_press)

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
    if cmd == "context-resource":
        from repo_catalog.domain.p1_context import ResourceKey

        rkey = ResourceKey(args.service, args.kind, args.id)
        view = service.get_context_resource(rkey, include_text=True)
        payload = view.to_dict()
    elif cmd == "context-resources":
        page = service.list_context_resources(
            _page_from_args(args),
            service_instance_uuidv4=args.service,
            resource_kind=args.kind,
            repository_uuidv4=args.repository,
        )
        payload = {
            "has_more": page.has_more,
            "items": [item.to_dict() for item in page.items],
            "next_cursor": page.next_cursor,
            "snapshot_token": page.snapshot_token,
            "total_count": page.total_count,
        }
    elif cmd == "paired-resource":
        from repo_catalog.domain.p1_context import ResourceKey

        rkey = ResourceKey(args.service, args.kind, args.id)
        view = service.get_paired_resource(
            rkey,
            include_text=True,
            include_core_bytes=args.include_core_bytes,
        )
        payload = view.to_dict()
    elif cmd == "paired-resources":
        page = service.list_paired_resources(
            _page_from_args(args),
            resource_kind=args.kind,
            repository_uuidv4=args.repository,
        )
        payload = {
            "has_more": page.has_more,
            "items": [item.to_dict() for item in page.items],
            "next_cursor": page.next_cursor,
            "snapshot_token": page.snapshot_token,
            "total_count": page.total_count,
        }
    elif cmd == "search-rebuild":
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
