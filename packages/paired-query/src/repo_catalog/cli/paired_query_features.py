"""Existing Context/paired CLI commands supplied by paired Query integration."""

from repo_catalog.application.paired_query import PairedQueryService
from repo_catalog.cli import context_query_features
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.query_contracts import QueryError


def add_commands(sub, common, page):
    context_query_features.add_commands(sub, common, page)
    single = sub.add_parser(
        "paired-resource",
        help="Query a paired Context resource with Core OID resolution",
    )
    common(single)
    single.add_argument("--service", required=True)
    single.add_argument("--kind", required=True)
    single.add_argument(
        "--id", required=True, help="Serialized canonical Resource identity JSON TEXT"
    )
    single.add_argument("--include-core-bytes", action="store_true")
    listing = sub.add_parser(
        "paired-resources",
        help="List paired Context resources with Core OID resolution",
    )
    common(listing)
    listing.add_argument("--kind", default=None)
    listing.add_argument("--repository", default=None)
    page(listing)


def query_service(directory, *, mode):
    return PairedQueryService(directory, mode=mode)


def query_payload(service, args, page_from_args):
    if args.command in ("context-resource", "context-resources"):
        return context_query_features.query_payload(service, args, page_from_args)
    if args.command == "paired-resource":
        return service.get_paired_resource(
            ResourceKey(args.service, args.kind, args.id),
            include_text=True,
            include_core_bytes=args.include_core_bytes,
        ).to_dict()
    if args.command == "paired-resources":
        result = service.list_paired_resources(
            page_from_args(args),
            resource_kind=args.kind,
            repository_uuidv4=args.repository,
        )
        return {
            "items": [v.to_dict() for v in result.items],
            "total_count": result.total_count,
            "has_more": result.has_more,
            "next_cursor": result.next_cursor,
            "snapshot_token": result.snapshot_token,
        }
    raise QueryError("MISSING_CAPABILITY", "cli", args.command)
