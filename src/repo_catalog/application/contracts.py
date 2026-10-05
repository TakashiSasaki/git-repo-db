"""CLI-independent request contracts; adapters receive these typed values."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PageRequest:
    limit: int = 100
    cursor: str | None = None


@dataclass(frozen=True)
class SearchQuery:
    kind: str
    literal: str | None = None
    scope: str = "current"
    repositories: tuple[str, ...] = ()
    options: dict = field(default_factory=dict)
    page: PageRequest = field(default_factory=PageRequest)
    timeout_seconds: float = 30


@dataclass(frozen=True)
class CollectionRequest:
    kind: str = "all"
    repositories: tuple[str, ...] = ()
    source: str | None = None
    job_id: str | None = None
    endpoint_id: str | None = None


@dataclass(frozen=True)
class HydrateRequest:
    content_id: int
    repository: str | None = None


@dataclass(frozen=True)
class QueryRequest:
    command: str
    options: dict = field(default_factory=dict)
    page: PageRequest = field(default_factory=PageRequest)
    timeout_seconds: float = 30
