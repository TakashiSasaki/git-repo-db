"""Store-neutral bounded pagination; endpoint key semantics stay with each owner."""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable
from typing import TypeVar

from repo_catalog.domain.query_contracts import (
    PageRequest,
    PageResult,
    PaginationCursor,
    QueryError,
    filter_digest,
)

T = TypeVar("T")


def validate_page_request(
    page: PageRequest,
    *,
    endpoint_kind: str,
    filters: dict[str, object],
    cursor_validator: Callable[[str, tuple], None],
) -> PageRequest:
    """Check caller shape/endpoint/filter before entering stored-row classifiers.

    Snapshot equality is checked later, against the actual pinned authority.
    """
    if type(page) is not PageRequest:
        raise QueryError("INVALID_INPUT", endpoint_kind, "PageRequest required")
    if page.cursor is not None and type(page.cursor) is not str:
        raise QueryError("INVALID_CURSOR", endpoint_kind, "cursor must be a string")
    if page.expected_token is not None and type(page.expected_token) is not str:
        raise QueryError(
            "INVALID_TOKEN", endpoint_kind, "expected_token must be a string"
        )
    checked = PageRequest(page.limit, page.cursor, page.expected_token)
    if checked.cursor is not None:
        PaginationCursor.decode(
            checked.cursor,
            expected_endpoint=endpoint_kind,
            expected_filter_digest=filter_digest(endpoint_kind, filters),
            current_snapshot_token=None,
            validate_key=cursor_validator,
        )
    return checked


def _paginate_items(
    items: Iterable[T],
    *,
    key_fn: Callable[[T], tuple],
    page: PageRequest,
    endpoint_kind: str,
    filters: dict[str, object],
    snapshot_token: str,
    cursor_validator: Callable[[str, tuple], None],
) -> PageResult[T]:
    if page.expected_token is not None and page.expected_token != snapshot_token:
        raise QueryError(
            "SNAPSHOT_MISMATCH",
            endpoint_kind,
            "expected_token does not match current pinned snapshot",
        )
    f_digest = filter_digest(endpoint_kind, filters)
    last_key = None
    if page.cursor is not None:
        last_key = PaginationCursor.decode(
            page.cursor,
            expected_endpoint=endpoint_kind,
            expected_filter_digest=f_digest,
            current_snapshot_token=snapshot_token,
            validate_key=cursor_validator,
        ).last_key
    total_count = 0
    remaining_count = 0

    def eligible():
        nonlocal total_count, remaining_count
        for item in items:
            total_count += 1
            if last_key is None or key_fn(item) > last_key:
                remaining_count += 1
                yield item

    # Exact total_count still requires a bounded scan; keep only limit+1 views.
    selected = heapq.nsmallest(page.limit + 1, eligible(), key=key_fn)
    sliced = tuple(selected[: page.limit])
    has_more = remaining_count > len(sliced)
    next_cursor = None
    if has_more and sliced:
        position = key_fn(sliced[-1])
        try:
            cursor_validator(endpoint_kind, position)
        except Exception as error:
            raise QueryError(
                "INVALID_CURSOR", "pagination", "invalid endpoint key"
            ) from error
        next_cursor = PaginationCursor(
            endpoint_kind=endpoint_kind,
            filter_digest=f_digest,
            snapshot_token=snapshot_token,
            last_key=position,
        ).encode()

    return PageResult(
        items=sliced,
        snapshot_token=snapshot_token,
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
    )
