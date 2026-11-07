"""Optional Context, paired, and Search query public types."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

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
from repo_catalog.domain.search_query import SearchHit as SearchHit
from repo_catalog.domain.search_query import SearchQuery as SearchQuery
from repo_catalog.domain.search_query import SearchResponse as SearchResponse

if TYPE_CHECKING:
    pass

SearchProjectionKind = Literal["git_metadata", "notes", "context_text"]
SEARCH_PROJECTION_KINDS: tuple[SearchProjectionKind, ...] = (
    "git_metadata",
    "notes",
    "context_text",
)


def validate_cursor_key(endpoint: str, key: tuple) -> None:
    """Validate positions owned by the installed Context/Search query feature."""
    if endpoint == "context_resources":
        from repo_catalog.domain.context_query import (
            validate_cursor_key as validate_context_key,
        )

        return validate_context_key(endpoint, key)
    if endpoint == "paired_resources":
        from repo_catalog.domain.paired_query import (
            validate_cursor_key as validate_paired_key,
        )

        return validate_paired_key(endpoint, key)
    if (
        endpoint != "search"
        or type(key) is not tuple
        or len(key) != 2
        or any(type(v) is not str or not v or len(v) > 32768 for v in key)
    ):
        raise ValueError("invalid key shape or type")
    if endpoint == "search":
        if key[0] not in SEARCH_PROJECTION_KINDS:
            raise ValueError("invalid projection")
        document = json.loads(key[1])
        if (
            not isinstance(document, list)
            or not document
            or any(type(v) is not str for v in document)
            or canonical_json(document) != key[1]
        ):
            raise ValueError("invalid document key")
