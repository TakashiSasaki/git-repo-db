"""Optional paired Search composition; loaded only with paired capability."""

from repo_catalog.application.paired_query import PairedQueryService
from repo_catalog.application.repository_search import RepositorySearchReader
from repo_catalog.application.search_query import SearchReader


class PairedSearchService(RepositorySearchReader, SearchReader, PairedQueryService):
    """Existing paired/single-authority topology with the Search extension."""
