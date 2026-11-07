"""Search-only public values, independent of concrete authority implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from repo_catalog.domain.query_contracts import PageRequest, QueryError, canonical_json

SearchProjectionKind = Literal["git_metadata", "notes", "context_text"]
SEARCH_PROJECTION_KINDS: tuple[SearchProjectionKind, ...] = (
    "git_metadata",
    "notes",
    "context_text",
)


@dataclass(frozen=True)
class SearchQuery:
    """Search query parameters with projection kind filter and pagination."""

    query_text: str
    projection_kinds: tuple[str, ...] = SEARCH_PROJECTION_KINDS
    limit: int = 50
    cursor: str | None = None
    expected_token: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.query_text, str)
            or not self.query_text
            or len(self.query_text) > 4096
        ):
            raise QueryError("INVALID_QUERY", "search", "nonempty query_text required")
        try:
            self.query_text.encode("utf-8")
        except UnicodeEncodeError as error:
            raise QueryError(
                "INVALID_QUERY", "search", "valid Unicode required"
            ) from error
        if (
            not self.projection_kinds
            or len(set(self.projection_kinds)) != len(self.projection_kinds)
            or any(k not in SEARCH_PROJECTION_KINDS for k in self.projection_kinds)
        ):
            raise QueryError(
                "INVALID_PROJECTION_KIND",
                "search",
                f"projection_kinds must be subset of {SEARCH_PROJECTION_KINDS}",
            )
        PageRequest(
            limit=self.limit, cursor=self.cursor, expected_token=self.expected_token
        )


@dataclass(frozen=True)
class SearchHit:
    """Authoritative-verified search hit."""

    projection_kind: str
    document_key: tuple[Any, ...]
    matched_text: str
    authoritative_summary: dict[str, object]
    snapshot_token: str

    @property
    def semantic_key(self) -> tuple[str, str]:
        return (self.projection_kind, canonical_json(list(self.document_key)))

    def to_dict(self) -> dict[str, object]:
        return {
            "authoritative_summary": self.authoritative_summary,
            "document_key": list(self.document_key),
            "matched_text": self.matched_text,
            "projection_kind": self.projection_kind,
            "snapshot_token": self.snapshot_token,
        }


@dataclass(frozen=True)
class SearchResponse:
    """Paginated search response with per-kind backend provenance ('verified_projection_scan' or 'authority_scan')."""

    hits: tuple[SearchHit, ...]
    backend: str
    backends_by_kind: dict[str, str]
    snapshot_token: str
    next_cursor: str | None
    has_more: bool
    total_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "backends_by_kind": dict(sorted(self.backends_by_kind.items())),
            "has_more": self.has_more,
            "hits": [hit.to_dict() for hit in self.hits],
            "next_cursor": self.next_cursor,
            "snapshot_token": self.snapshot_token,
            "total_count": self.total_count,
        }
