"""Search public inputs and external index callbacks are not stored authority."""

import json
from unittest.mock import patch

import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.context_search import ContextSearchService
from repo_catalog.application.core_search import CoreSearchService
from repo_catalog.domain.query_contracts import QueryError
from repo_catalog.domain.search_query import SearchQuery
from tests.integration.p6.conftest import populate_rich_catalog


@pytest.mark.parametrize("role", ["core", "context"])
@pytest.mark.parametrize("operation", ["search", "rebuild"])
def test_index_port_error_preserves_identity_without_authority_stop(
    tmp_path, role, operation
):
    populate_rich_catalog(
        tmp_path, include_core=role == "core", include_context=role == "context"
    )
    service = (CoreSearchService if role == "core" else ContextSearchService)(
        tmp_path, mode=role + "_only"
    )
    kind = "git_metadata" if role == "core" else "context_text"
    marker = json.JSONDecodeError("external index port", "", 0)

    class Broken:
        def query_candidates(self, *args, **kwargs):
            raise marker

        def replace_projection(self, *args, **kwargs):
            raise marker

    service.search_adapter = Broken()
    with pytest.raises(json.JSONDecodeError) as caught:
        if operation == "search":
            service.search(SearchQuery("e", (kind,)))
        else:
            service.rebuild_search((kind,))
    assert caught.value is marker
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    service.search_adapter = None
    assert service.search(SearchQuery("e", (kind,))).hits


@pytest.mark.parametrize("role", ["core", "context"])
def test_stale_cursor_refuses_before_authority_extraction(tmp_path, role):
    populate_rich_catalog(
        tmp_path, include_core=role == "core", include_context=role == "context"
    )
    service = (CoreSearchService if role == "core" else ContextSearchService)(
        tmp_path, mode=role + "_only"
    )
    query = SearchQuery("e", limit=1)
    first = service.search(query)
    assert first.next_cursor
    with connect(tmp_path / (role + ".sqlite3"), role) as db:
        if role == "context":
            db.execute('UPDATE providers SET configuration_json=\'{"name":"changed"}\'')
        else:
            # A genuine additional attributed claim changes authority; no update
            # of admitted Core facts is needed for this synthetic writer.
            row = db.execute(
                "SELECT repository_uuidv4,provenance FROM repository_claims WHERE field='name' LIMIT 1"
            ).fetchone()
            provenance = json.loads(row[1])
            provenance[2] += ".search-stale-probe"
            db.execute(
                "INSERT INTO repository_claims VALUES(?,?,?,?)",
                (
                    row[0],
                    "name",
                    '"changed"',
                    json.dumps(provenance, separators=(",", ":")),
                ),
            )
    with patch.object(
        service,
        "_extract_documents",
        side_effect=AssertionError("stale cursor reached authority extraction"),
    ):
        with pytest.raises(QueryError) as caught:
            service.search(SearchQuery("e", limit=1, cursor=first.next_cursor))
    assert caught.value.code == "SNAPSHOT_MISMATCH"
    assert not (tmp_path / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("role", ["core", "context"])
def test_index_result_does_not_keep_caller_comparison_behavior(tmp_path, role):
    populate_rich_catalog(
        tmp_path, include_core=role == "core", include_context=role == "context"
    )
    service = (CoreSearchService if role == "core" else ContextSearchService)(
        tmp_path, mode=role + "_only"
    )
    kind = "git_metadata" if role == "core" else "context_text"
    with service.open_snapshot() as snap:
        docs, _ = service._extract_documents(snap, kind)
    matches = {k: v for k, v in docs.items() if "e" in v}

    class HostileDict(dict):
        def __eq__(self, other):
            raise json.JSONDecodeError("caller comparison", "", 0)

    class Index:
        def query_candidates(self, *args, **kwargs):
            return HostileDict(matches)

    service.search_adapter = Index()
    assert (
        service.search(SearchQuery("e", (kind,))).backend == "verified_projection_scan"
    )
    assert not (tmp_path / "p1-recovery-stop.json").exists()
