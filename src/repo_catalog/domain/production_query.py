"""Optional Context, paired, and Search query public types."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repo_catalog.domain.context_query import (
    ContextResourceView as ContextResourceView,
)
from repo_catalog.domain.context_query import ProviderView as ProviderView
from repo_catalog.domain.context_query import SourceView as SourceView
from repo_catalog.domain.context_query import (
    provider_role_summary as provider_role_summary,
)
from repo_catalog.domain.context_query import (
    repository_relation_summary as repository_relation_summary,
)
from repo_catalog.domain.core_query import GitObjectView as GitObjectView
from repo_catalog.domain.core_query import GitObservationView as GitObservationView
from repo_catalog.domain.core_query import GitRepositoryView as GitRepositoryView
from repo_catalog.domain.core_query import RefNotesTargetView as RefNotesTargetView
from repo_catalog.domain.core_query import ref_projection_json as ref_projection_json
from repo_catalog.domain.paired_query import (
    PairedCoreResolution as PairedCoreResolution,
)
from repo_catalog.domain.paired_query import PairedResourceView as PairedResourceView
from repo_catalog.domain.query_contracts import ByteReadResult as ByteReadResult
from repo_catalog.domain.query_contracts import CatalogReadMode as CatalogReadMode
from repo_catalog.domain.query_contracts import CoverageView as CoverageView
from repo_catalog.domain.query_contracts import PageRequest as PageRequest
from repo_catalog.domain.query_contracts import PageResult as PageResult
from repo_catalog.domain.query_contracts import PaginationCursor as PaginationCursor
from repo_catalog.domain.query_contracts import QueryError as QueryError
from repo_catalog.domain.query_contracts import SnapshotFenceToken as SnapshotFenceToken
from repo_catalog.domain.query_contracts import canonical_json as canonical_json
from repo_catalog.domain.query_contracts import filter_digest as filter_digest

if TYPE_CHECKING:
    pass

from repo_catalog.domain.search_query import (
    SEARCH_PROJECTION_KINDS as SEARCH_PROJECTION_KINDS,
)
from repo_catalog.domain.search_query import SearchHit as SearchHit
from repo_catalog.domain.search_query import (
    SearchProjectionKind as SearchProjectionKind,
)
from repo_catalog.domain.search_query import SearchQuery as SearchQuery
from repo_catalog.domain.search_query import SearchResponse as SearchResponse


def validate_cursor_key(endpoint: str, key: tuple) -> None:
    if endpoint == "context_resources":
        from repo_catalog.domain.context_query import validate_cursor_key as validator
    elif endpoint == "paired_resources":
        from repo_catalog.domain.paired_query import validate_cursor_key as validator
    else:
        from repo_catalog.domain.search_query import validate_cursor_key as validator
    validator(endpoint, key)
