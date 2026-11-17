"""Finite candidate-aware Context filtering without hiding conflicting originals."""

import json

from repo_catalog.domain.context_query import validate_cursor_key
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.query_contracts import (
    PageRequest,
    PaginationCursor,
    filter_digest,
)


def browse(
    service, *, page=None, field_filters=None, text_literal=None, parent=None, **filters
):
    page = PageRequest() if page is None else page
    field_filters = {} if field_filters is None else field_filters
    if type(page) is not PageRequest:
        raise ValueError("PageRequest required")
    if type(field_filters) is not dict or len(field_filters) > 32:
        raise ValueError("INPUT_LIMIT: at most 32 field filters")
    if any(type(key) is not str or not key or len(key) > 1024 for key in field_filters):
        raise ValueError("bounded field names required")
    if text_literal is not None and (
        type(text_literal) is not str or len(text_literal) > 4096
    ):
        raise ValueError("INPUT_LIMIT: finite text literal required")
    if parent is not None and type(parent) is not ResourceKey:
        raise ValueError("reported Parent filter requires a typed ResourceKey")
    namespace = filters.get("identifier_namespace")
    if namespace is not None and type(namespace) is not ResourceKey:
        raise ValueError("identifier namespace requires a typed ResourceKey")
    source_filters = {
        "identifier_namespace": list(namespace.coordinates()) if namespace else None,
        "mapping_evidence": service._mapping_filter(),
        "repository_uuidv4": filters.get("repository_uuidv4"),
        "resource_kind": filters.get("resource_kind"),
        "service_instance_uuidv4": filters.get("service_instance_uuidv4"),
    }
    extra = {
        "source": source_filters,
        "field_filters": field_filters,
        "text_literal": text_literal,
        "reported_parent": list(parent.coordinates()) if parent else None,
    }
    browse_digest = filter_digest("context_resources", extra)
    source_digest = filter_digest("context_resources", source_filters)
    if page.cursor is not None:
        cursor = PaginationCursor.decode(
            page.cursor,
            expected_endpoint="context_resources",
            expected_filter_digest=browse_digest,
            current_snapshot_token=None,
            validate_key=validate_cursor_key,
        )
        source_cursor = PaginationCursor(
            "context_resources", source_digest, cursor.snapshot_token, cursor.last_key
        ).encode()
        page = PageRequest(
            page.limit, source_cursor, page.expected_token or cursor.snapshot_token
        )
    result = service.list_context_resources(page, **filters)
    items = []
    for resource in result.items:
        # These are actual Parent originals, never collection/namespace inference.
        # Retained historical alternatives remain qualified in the returned view.
        if parent is not None and not any(
            relation.relation_kind == "parent" and parent in relation.members
            for relation in resource.relations
        ):
            continue
        if not all(
            any(
                json.loads(candidate.value_json) == expected
                for candidate in resource.fields.get(field, ())
            )
            for field, expected in field_filters.items()
        ):
            continue
        if text_literal is not None:
            texts = [v for v in resource.resolved_texts.values() if isinstance(v, str)]
            texts.extend(
                json.loads(candidate.value_json)
                for candidates in resource.fields.values()
                for candidate in candidates
                if isinstance(json.loads(candidate.value_json), str)
            )
            if not any(text_literal in text for text in texts):
                continue
        items.append(resource.to_dict())
    next_cursor = None
    if result.next_cursor:
        cursor = PaginationCursor.decode(
            result.next_cursor,
            expected_endpoint="context_resources",
            expected_filter_digest=source_digest,
            current_snapshot_token=result.snapshot_token,
            validate_key=validate_cursor_key,
        )
        next_cursor = PaginationCursor(
            "context_resources", browse_digest, cursor.snapshot_token, cursor.last_key
        ).encode()
    return {
        "items": items,
        "scanned_count": len(result.items),
        "scan_has_more": result.has_more,
        "next_cursor": next_cursor,
        "snapshot_token": result.snapshot_token,
        "filter_semantics": "matches current field candidates and any retained actual Parent original; full alternatives are returned",
    }
