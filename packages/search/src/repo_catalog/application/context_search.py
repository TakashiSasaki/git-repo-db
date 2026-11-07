"""Context-only Search; concrete Core is not imported or required."""

from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.application.search_query import SearchReader


class ContextSearchService(SearchReader, ContextQueryService):
    """Use explicit context_only scope to ignore opaque coexisting Core."""
