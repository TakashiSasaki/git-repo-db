"""Typed Protocol ports for P6 authoritative queries, pagination, and derivative Search."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from repo_catalog.domain.p1_context import CoverageScope, ResourceKey
from repo_catalog.domain.ports.core_query import CoreQueryPort
from repo_catalog.domain.ports.p1_core import WorkBudget
from repo_catalog.domain.production_query import (
    ByteReadResult,
    ContextResourceView,
    CoverageView,
    PageRequest,
    PageResult,
    PairedResourceView,
    ProviderView,
    SearchQuery,
    SearchResponse,
    SourceView,
)


class SearchIndexPort(Protocol):
    """Port for disposable derivative Search projection storage and candidate lookup."""

    def replace_projection(
        self,
        projection_kind: str,
        snapshot_token: str,
        documents: dict[str, str],
    ) -> None: ...

    def query_candidates(
        self,
        projection_kind: str,
        snapshot_token: str,
        query_text: str,
        expected_doc_count: int | None = None,
    ) -> dict[str, str] | None: ...


class ProductionQueryPort(CoreQueryPort, Protocol):
    """Port for authoritative Core, Context, Paired, and Search queries."""

    def list_providers(self) -> tuple[ProviderView, ...]: ...

    def list_source_views(
        self, service_instance_uuidv4: str | None = None
    ) -> tuple[SourceView, ...]: ...

    def get_context_resource(
        self,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
    ) -> ContextResourceView: ...

    def list_context_resources(
        self,
        page: PageRequest = PageRequest(),
        *,
        service_instance_uuidv4: str | None = None,
        resource_kind: str | None = None,
        repository_uuidv4: str | None = None,
        parent: ResourceKey | None = None,
    ) -> PageResult[ContextResourceView]: ...

    def read_context_text(self, text_sha256: str) -> ByteReadResult: ...

    def get_context_coverage(self, scope: CoverageScope) -> CoverageView: ...

    def get_paired_resource(
        self,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
        include_core_bytes: bool = False,
    ) -> PairedResourceView: ...

    def list_paired_resources(
        self,
        page: PageRequest = PageRequest(),
        *,
        resource_kind: str | None = None,
        repository_uuidv4: str | None = None,
    ) -> PageResult[PairedResourceView]: ...

    def rebuild_search(
        self,
        projection_kinds: Sequence[str] = ("git_metadata", "notes", "context_text"),
        *,
        work: WorkBudget | None = None,
    ) -> dict[str, int]: ...

    def search(
        self, query: SearchQuery, *, work: WorkBudget | None = None
    ) -> SearchResponse: ...
