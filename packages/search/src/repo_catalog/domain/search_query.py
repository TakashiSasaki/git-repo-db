"""Search-only public values; no concrete authority or paired integration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from repo_catalog.domain.query_contracts import PageRequest, QueryError, canonical_json

SearchProjectionKind = Literal["git_metadata", "notes", "context_text"]
SEARCH_PROJECTION_KINDS: tuple[SearchProjectionKind, ...] = (
    "git_metadata",
    "notes",
    "context_text",
)


def canonical_projection_kinds(kinds):
    if (
        type(kinds) not in (tuple, list)
        or not 0 < len(kinds) <= len(SEARCH_PROJECTION_KINDS)
        or any(
            type(kind) is not str or kind not in SEARCH_PROJECTION_KINDS
            for kind in kinds
        )
        or len(set(kinds)) != len(kinds)
    ):
        raise QueryError(
            "INVALID_PROJECTION_KIND",
            "search",
            "finite unique supported projection kinds required",
        )
    return tuple(kinds)


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
            type(self.query_text) is not str
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
        object.__setattr__(
            self, "projection_kinds", canonical_projection_kinds(self.projection_kinds)
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


def validate_cursor_key(endpoint: str, key: tuple) -> None:
    if (
        endpoint != "search"
        or type(key) is not tuple
        or len(key) != 2
        or any(type(v) is not str or not v or len(v) > 32768 for v in key)
    ):
        raise ValueError("invalid Search cursor shape")
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
