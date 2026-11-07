"""Search-owned orchestration/fallback, independent of concrete authority code."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence

from repo_catalog.application.query_pagination import (
    _paginate_items,
    validate_page_request,
)
from repo_catalog.application.query_runtime import (
    _QueryWorkBoundary,
    _QueryWorkError,
    _stored_view,
)
from repo_catalog.domain.query_contracts import (
    PageRequest,
    PaginationCursor,
    QueryError,
    filter_digest,
)
from repo_catalog.domain.query_work import UnlimitedWorkBudget
from repo_catalog.domain.search_query import (
    SEARCH_PROJECTION_KINDS,
    SearchHit,
    SearchQuery,
    SearchResponse,
    canonical_projection_kinds,
    validate_cursor_key,
)
from repo_catalog.domain.shared_values import CoreFailure


class SearchReader:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._search_adapter = None

    def _search_mapping_filter(self):
        resolver = getattr(self, "_mapping_filter", None)
        return (
            resolver()
            if resolver is not None
            else {"confirmed": [], "contradicted": []}
        )

    _checked_projection_kinds = staticmethod(canonical_projection_kinds)

    def _search_filters(self, query):
        return {
            "projection_kinds": list(query.projection_kinds),
            "query_text": query.query_text,
            "mapping_evidence": self._search_mapping_filter(),
        }

    def _checked_search_query(self, query):
        if type(query) is not SearchQuery or type(query.query_text) is not str:
            raise QueryError(
                "INVALID_QUERY", "search", "SearchQuery with plain query text required"
            )
        kinds = self._checked_projection_kinds(query.projection_kinds)
        if query.cursor is not None and type(query.cursor) is not str:
            raise QueryError("INVALID_CURSOR", "search", "plain cursor required")
        if query.expected_token is not None and type(query.expected_token) is not str:
            raise QueryError("INVALID_TOKEN", "search", "plain token required")
        checked = SearchQuery(
            query.query_text, kinds, query.limit, query.cursor, query.expected_token
        )
        validate_page_request(
            PageRequest(checked.limit, checked.cursor, checked.expected_token),
            endpoint_kind="search",
            filters=self._search_filters(checked),
            cursor_validator=validate_cursor_key,
        )
        return checked

    def _index_call(self, method, *args, **kwargs):
        # External SearchIndexPort callbacks are not stored authority. Preserve
        # their original exception beyond every authority snapshot classifier.
        try:
            result = getattr(self.search_adapter, method)(*args, **kwargs)
            if method != "query_candidates" or result is None:
                return result
            from repo_catalog.adapters.sqlite.production_search import BoundedDocuments

            if (
                not isinstance(result, dict)
                or dict.__len__(result) > BoundedDocuments.max_documents
            ):
                return None
            copied = BoundedDocuments()
            try:
                for key, value in dict.items(result):
                    if type(key) is not str or type(value) is not str:
                        return None
                    copied[key] = value
            except QueryError:
                return None
            return copied
        except Exception as error:
            raise _QueryWorkError(error) from error

    @property
    def search_adapter(self):
        if self._search_adapter is None:
            from repo_catalog.adapters.sqlite.production_search import (
                ProductionSearchAdapter,
            )

            self._search_adapter = ProductionSearchAdapter(self.directory)
        return self._search_adapter

    @search_adapter.setter
    def search_adapter(self, adapter):
        self._search_adapter = adapter

    @_stored_view
    def _extract_documents(self, snapshot, kind, work=None, *, mapping_evidence=None):
        from repo_catalog.adapters.sqlite.production_search import (
            ProductionSearchAdapter,
        )

        if kind == "git_metadata":
            return ProductionSearchAdapter.extract_git_metadata_documents(snapshot.core)
        if kind == "notes":
            try:
                return self._extract_ref_notes_documents(snapshot.core, work)
            except CoreFailure as error:
                if error.code in ("BUDGET", "QUERY_BUDGET"):
                    raise QueryError(
                        "QUERY_BUDGET", "ref-notes-search", str(error)
                    ) from error
                raise
        return ProductionSearchAdapter.extract_context_documents(
            snapshot.context, evidence=mapping_evidence
        )

    def rebuild_search(
        self, projection_kinds: Sequence[str] = SEARCH_PROJECTION_KINDS, *, work=None
    ):
        projection_kinds = self._checked_projection_kinds(projection_kinds)
        guarded = _QueryWorkBoundary(
            work if work is not None else UnlimitedWorkBudget()
        )
        try:
            return self._rebuild_search(
                projection_kinds, guarded, getattr(self, "mapping_evidence", None)
            )
        except _QueryWorkError as error:
            raise error.original from None

    def _rebuild_search(
        self,
        projection_kinds: Sequence[str],
        work,
        mapping_evidence,
    ) -> dict[str, int]:
        """Rebuild requested Search projections from a single pinned snapshot."""
        for kind in projection_kinds:
            if kind not in SEARCH_PROJECTION_KINDS:
                raise QueryError("INVALID_PROJECTION_KIND", "search", str(kind))

        with self.open_snapshot() as snap:
            token_str = snap.token.encode()
            counts: dict[str, int] = {}
            for kind in projection_kinds:
                if (
                    kind in ("git_metadata", "notes")
                    and getattr(snap, "core", None) is None
                ):
                    continue
                if kind == "context_text" and getattr(snap, "context", None) is None:
                    continue
                docs, _ = self._extract_documents(
                    snap, kind, work, mapping_evidence=mapping_evidence
                )

                counts[kind] = self._index_call(
                    "replace_projection",
                    kind,
                    token_str,
                    docs,
                    repository_uuidv4=snap.token.repository_uuidv4,
                    catalog_instance_uuidv4=snap.token.catalog_instance_uuidv4,
                )
            return counts

    def search(self, query: SearchQuery, *, work=None) -> SearchResponse:
        query = self._checked_search_query(query)
        guarded = _QueryWorkBoundary(
            work if work is not None else UnlimitedWorkBudget()
        )
        try:
            return self._search(
                query,
                guarded,
                self._search_filters(query),
                getattr(self, "mapping_evidence", None),
            )
        except _QueryWorkError as error:
            raise error.original from None

    def _search(
        self, query: SearchQuery, work, filters, mapping_evidence
    ) -> SearchResponse:
        """Execute a verified search across the pinned snapshot with automatic fallback."""
        with self.open_snapshot() as snap:
            token_str = snap.token.encode()
            if query.expected_token is not None and query.expected_token != token_str:
                raise QueryError(
                    "SNAPSHOT_MISMATCH",
                    "search",
                    "expected_token does not match current pinned snapshot",
                )

            if query.cursor is not None:
                PaginationCursor.decode(
                    query.cursor,
                    expected_endpoint="search",
                    expected_filter_digest=filter_digest("search", filters),
                    current_snapshot_token=token_str,
                    validate_key=validate_cursor_key,
                )

            all_hits: list[SearchHit] = []
            backends_by_kind: dict[str, str] = {}

            for kind in query.projection_kinds:
                if (
                    kind in ("git_metadata", "notes")
                    and getattr(snap, "core", None) is None
                ):
                    continue
                if kind == "context_text" and getattr(snap, "context", None) is None:
                    continue

                authority_started = time.perf_counter_ns()
                auth_docs, auth_summaries = self._extract_documents(
                    snap, kind, work, mapping_evidence=mapping_evidence
                )

                expected_matches = {
                    doc_key: text
                    for doc_key, text in auth_docs.items()
                    if query.query_text in text
                }

                self.last_costs_ns["authority_search_validation:" + kind] = (
                    time.perf_counter_ns() - authority_started
                )
                projection_started = time.perf_counter_ns()
                candidates = self._index_call(
                    "query_candidates",
                    kind,
                    token_str,
                    query.query_text,
                    expected_doc_count=len(auth_docs),
                )
                self.last_costs_ns["projection_scan:" + kind] = (
                    time.perf_counter_ns() - projection_started
                )
                if candidates is not None and candidates == expected_matches:
                    backends_by_kind[kind] = "verified_projection_scan"
                    verified_matches = candidates
                else:
                    backends_by_kind[kind] = "authority_scan"
                    verified_matches = expected_matches

                for doc_key_json, matched_text in verified_matches.items():
                    all_hits.append(
                        SearchHit(
                            projection_kind=kind,
                            document_key=tuple(json.loads(doc_key_json)),
                            matched_text=matched_text,
                            authoritative_summary=auth_summaries[doc_key_json],
                            snapshot_token=token_str,
                        )
                    )

            overall_backend = (
                "verified_projection_scan"
                if backends_by_kind
                and all(
                    b == "verified_projection_scan" for b in backends_by_kind.values()
                )
                else "authority_scan"
            )

            page_result = _paginate_items(
                all_hits,
                cursor_validator=validate_cursor_key,
                key_fn=lambda h: h.semantic_key,
                page=PageRequest(
                    limit=query.limit,
                    cursor=query.cursor,
                    expected_token=query.expected_token,
                ),
                endpoint_kind="search",
                filters=filters,
                snapshot_token=token_str,
            )

            return SearchResponse(
                hits=page_result.items,
                backend=overall_backend,
                backends_by_kind=backends_by_kind,
                snapshot_token=token_str,
                next_cursor=page_result.next_cursor,
                has_more=page_result.has_more,
                total_count=page_result.total_count,
            )
