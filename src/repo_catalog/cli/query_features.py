"""Rich Query CLI delegates to the installed Search/paired feature composition."""

from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.cli.search_query_features import add_commands as add_commands
from repo_catalog.cli.search_query_features import query_payload as query_payload


def query_service(directory, *, mode):
    return ProductionQueryService(directory, mode=mode)
