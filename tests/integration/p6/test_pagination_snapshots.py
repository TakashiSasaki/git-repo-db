# Legacy-only assertions below cover deferred physical diagnostics, not public API compatibility.
"""Integration tests for P6 deterministic pagination, snapshot fencing, and cursor validation."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.production_query import PageRequest, QueryError, SearchQuery
from tests.integration.p6.conftest import (
    REPOSITORY,
    SERVICE,
    populate_rich_catalog,
)
from tests.support.context_admission import fixture_context, fixture_service


def _collect_all_pages(fetch_page, limit: int = 2) -> tuple[list, str]:
    items = []
    cursor = None
    token = None
    seen_cursors = set()
    while True:
        page = fetch_page(PageRequest(limit=limit, cursor=cursor, expected_token=token))
        if token is None:
            token = page.snapshot_token
        assert page.snapshot_token == token
        assert len(page.items) <= limit
        items.extend(page.items)
        if not page.has_more:
            assert page.next_cursor is None
            break
        assert page.next_cursor is not None
        assert page.next_cursor not in seen_cursors
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor
    return items, token


def test_deterministic_pagination_across_all_endpoints(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "pagination_catalog"
    populate_rich_catalog(catalog_dir, fmt="sha1")
    service = ProductionQueryService(catalog_dir)
    service.rebuild_search()

    # 1. Git objects pagination
    all_objs = service.list_git_objects(PageRequest(limit=100))
    paged_objs, _ = _collect_all_pages(service.list_git_objects, limit=2)
    assert [o.object_oid for o in paged_objs] == [o.object_oid for o in all_objs.items]
    assert len(paged_objs) == all_objs.total_count
    assert [o.object_oid.key for o in paged_objs] == sorted(
        o.object_oid.key for o in paged_objs
    )

    # 2. Git observations pagination
    all_obs = service.list_git_observations(PageRequest(limit=100))
    paged_obs, _ = _collect_all_pages(service.list_git_observations, limit=1)
    assert [o.semantic_key for o in paged_obs] == [
        o.semantic_key for o in all_obs.items
    ]
    assert len(paged_obs) == all_obs.total_count

    # 3. Notes captures pagination
    all_caps = service.list_ref_observations(PageRequest(limit=100))
    paged_caps, _ = _collect_all_pages(service.list_ref_observations, limit=1)
    assert [c.semantic_key for c in paged_caps] == [
        c.semantic_key for c in all_caps.items
    ]

    # 4. Context resources pagination
    all_ctx = service.list_context_resources(PageRequest(limit=100))
    paged_ctx, _ = _collect_all_pages(service.list_context_resources, limit=2)
    assert [r.semantic_key for r in paged_ctx] == [
        r.semantic_key for r in all_ctx.items
    ]
    assert len(paged_ctx) == all_ctx.total_count
    assert [r.semantic_key for r in paged_ctx] == sorted(
        r.semantic_key for r in paged_ctx
    )

    # 5. Paired resources pagination
    all_paired = service.list_paired_resources(PageRequest(limit=100))
    paged_paired, _ = _collect_all_pages(service.list_paired_resources, limit=2)
    assert [p.resource for p in paged_paired] == [p.resource for p in all_paired.items]
    assert len(paged_paired) == all_paired.total_count

    # 6. Search hits pagination
    all_search = service.search(SearchQuery(query_text="p6", limit=100))
    assert all_search.total_count >= 2
    search_hits = []
    cursor = None
    token = None
    while True:
        resp = service.search(
            SearchQuery(
                query_text="p6",
                limit=1,
                cursor=cursor,
                expected_token=token,
            )
        )
        if token is None:
            token = resp.snapshot_token
        search_hits.extend(resp.hits)
        if not resp.has_more:
            break
        cursor = resp.next_cursor
    assert [h.semantic_key for h in search_hits] == [
        h.semantic_key for h in all_search.hits
    ]


def test_open_snapshot_isolation_and_stale_cursor_fencing_after_write(
    tmp_path: Path,
) -> None:
    catalog_dir = tmp_path / "snapshot_fence_catalog"
    populate_rich_catalog(catalog_dir, fmt="sha1")
    service = ProductionQueryService(catalog_dir)

    first_page = service.list_git_objects(PageRequest(limit=2))
    assert first_page.has_more is True
    assert first_page.next_cursor is not None
    initial_token = first_page.snapshot_token
    initial_count = first_page.total_count

    # Keep a pinned snapshot open while a concurrent writer admits new Core + Context facts
    with service.open_snapshot(required_store="paired") as pinned:
        assert pinned.token.encode() == initial_token
        new_oid = OID("sha1", "e" * 40)
        new_res = ResourceKey.from_native(SERVICE, "issue", "999")
        prov = canonical({"source": "github.rest", "evidence": "event-999"})

        def write_core(db):
            with GitCore.for_transaction(db) as core:
                core.admit_object(new_oid)

        def write_ctx(db):
            with Context.for_transaction(db, catalog_dir) as ctx:
                ctx.resource(new_res, REPOSITORY)
                ctx.admit_field(
                    FieldCandidate(
                        new_res,
                        "title",
                        canonical("Concurrent issue 999"),
                        FieldClock("github:issue", 500),
                        prov,
                        500,
                    )
                )

        authorization, _ = fixture_service(
            DependencySet(
                resources={new_res},
                repositories={REPOSITORY},
                provider_registrations={SERVICE},
                object_oids={new_oid},
            )
        )
        PairCoordinator(catalog_dir, authorization=authorization).admit(
            write_core, write_ctx, admission=fixture_context(authorization)
        )

        # Pinned snapshot continues to see only the pre-write state
        assert pinned.core is not None and pinned.context is not None
        pinned_objs = pinned.core.sql("SELECT count(*) FROM git_objects")[0][0]
        assert pinned_objs == initial_count
        assert new_res not in pinned.context.resources()

    # A fresh query sees the new snapshot token
    newer_token = service.snapshot_token().encode()
    assert newer_token != initial_token

    # Passing the old cursor to list_git_objects fails closed with SNAPSHOT_MISMATCH
    with pytest.raises(QueryError) as cursor_err:
        service.list_git_objects(PageRequest(limit=2, cursor=first_page.next_cursor))
    assert cursor_err.value.code == "SNAPSHOT_MISMATCH"

    # Passing the old expected_token fails closed with SNAPSHOT_MISMATCH
    with pytest.raises(QueryError) as token_err:
        service.list_git_objects(PageRequest(limit=2, expected_token=initial_token))
    assert token_err.value.code == "SNAPSHOT_MISMATCH"


def test_malformed_tampered_and_cross_endpoint_cursors_fail_closed(
    tmp_path: Path,
) -> None:
    catalog_dir = tmp_path / "cursor_validation_catalog"
    populate_rich_catalog(catalog_dir, fmt="sha1")
    service = ProductionQueryService(catalog_dir)

    page = service.list_git_objects(PageRequest(limit=1))
    assert page.next_cursor is not None
    valid_cursor = page.next_cursor

    # 1. Garbage base64 cursor
    with pytest.raises(QueryError) as err1:
        service.list_git_objects(PageRequest(limit=1, cursor="not-valid-base64!!!"))
    assert err1.value.code == "INVALID_CURSOR"

    # 2. Tampered MAC or payload in cursor
    padded = valid_cursor + "=" * (-len(valid_cursor) % 4)
    envelope = json.loads(
        base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    )
    envelope["payload"]["last_key"] = ["sha1", "0" * 40]
    tampered_raw = base64.urlsafe_b64encode(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    with pytest.raises(QueryError) as err2:
        service.list_git_objects(PageRequest(limit=1, cursor=tampered_raw))
    assert err2.value.code == "INVALID_CURSOR"

    # 3. Cross-endpoint cursor reuse (using git_objects cursor on context_resources)
    with pytest.raises(QueryError) as err3:
        service.list_context_resources(PageRequest(limit=1, cursor=valid_cursor))
    assert err3.value.code == "INVALID_CURSOR"

    # 4. Different filter parameters with same endpoint cursor
    with pytest.raises(QueryError) as err4:
        service.list_git_objects(
            PageRequest(limit=1, cursor=valid_cursor),
            native_type="commit",
        )
    assert err4.value.code == "INVALID_CURSOR"
