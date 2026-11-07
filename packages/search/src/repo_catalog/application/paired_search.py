"""Optional paired Search composition; loaded only with paired capability."""

from repo_catalog.application.core_search import CoreSearchReader
from repo_catalog.application.paired_query import PairedQueryService
from repo_catalog.application.search_query import SearchReader


class PairedSearchService(CoreSearchReader, SearchReader, PairedQueryService):
    """Existing paired/single-authority topology with the Search extension."""
