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


def query_service(directory, *, mode):
    return ContextQueryService(directory, mode=mode)


def query_payload(service, args, page):
    if args.command != "context-resource":
        raise QueryError("MISSING_CAPABILITY", "cli", args.command)
    return service.get_context_resource(
        ResourceKey(args.service, args.kind, args.id), include_text=True
    ).to_dict()
