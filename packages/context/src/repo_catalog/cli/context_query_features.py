"""The existing context-resource CLI for the bounded independent reader."""

from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.query_contracts import QueryError


def add_commands(sub, common, page):
    command = sub.add_parser(
        "context-resource", help="Query a Context Resource and verified text"
    )
    common(command)
    command.add_argument("--service", required=True)
    command.add_argument("--kind", required=True)
    command.add_argument(
        "--id", required=True, help="Canonical Resource identity JSON TEXT"
    )

    listing = sub.add_parser(
        "context-resources", help="List Context resources with pagination"
    )
    common(listing)
    listing.add_argument("--service", default=None)
    listing.add_argument("--kind", default=None)
    listing.add_argument("--repository", default=None)
    page(listing)


def query_service(directory, *, mode):
    return ContextQueryService(directory, mode=mode)


def query_payload(service, args, page):
    if args.command == "context-resources":
        result = service.list_context_resources(
            page(args),
            service_instance_uuidv4=args.service,
            resource_kind=args.kind,
            repository_uuidv4=args.repository,
        )
        return {
            "items": [item.to_dict() for item in result.items],
            "total_count": result.total_count,
            "has_more": result.has_more,
            "next_cursor": result.next_cursor,
            "snapshot_token": result.snapshot_token,
        }
    if args.command != "context-resource":
        raise QueryError("MISSING_CAPABILITY", "cli", args.command)
    return service.get_context_resource(
        ResourceKey(args.service, args.kind, args.id), include_text=True
    ).to_dict()
