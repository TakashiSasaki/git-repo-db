"""Current Context evidence drives Search, including failed rebuild boundaries."""

import json
from contextlib import closing

import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.context_search import ContextSearchService
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import FieldClock, ResourceKey, canonical
from repo_catalog.domain.production_context import ContextError
from repo_catalog.domain.query_contracts import QueryError
from repo_catalog.domain.search_query import SearchQuery
from repo_catalog.domain.shared_values import RepositoryFailure
from tests.integration.p3.test_production_context import (
    KEY,
    SERVICE,
    directory,
    production_grants,
)
from tests.support.context_admission import fixture_transaction

__all__ = ["directory"]


def original(label):
    return canonical({"source": "search-regression-provider", "evidence": label})


def search(service, text, **options):
    return service.search(
        SearchQuery(text, projection_kinds=("context_text",), **options)
    )


def test_current_text_edits_and_ambiguous_originals_keep_exact_search_producers_and_pages(
    directory,
):
    other = ResourceKey.from_native(SERVICE, "issue", "8")
    grants = production_grants() | DependencySet(resources={other})
    with fixture_transaction(directory, grants) as context:
        context.provider(SERVICE, "github")
        for key in (KEY, other):
            context.resource(key)
            context.admit_text(
                key, "obsolete needle", FieldClock("provider", 1), original("first"), 1
            )
    service = ContextSearchService(directory, mode="context_only")
    assert search(service, "obsolete").total_count == 2
    service.rebuild_search(("context_text",))
    with fixture_transaction(directory, grants) as context:
        context.admit_text(
            KEY, "replacement needle", FieldClock("provider", 2), original("newer"), 2
        )
    assert {
        hit.authoritative_summary["provider_resource_id"]
        for hit in search(service, "obsolete").hits
    } == {other.provider_resource_id}
    current = search(service, "replacement")
    assert current.total_count == 1
    assert current.hits[0].authoritative_summary["provenance"] == json.loads(
        original("newer")
    )
    assert current.hits[0].authoritative_summary["clock"]["at_us"] == 2
    service.rebuild_search(("context_text",))
    assert search(service, "replacement").hits == current.hits
    with fixture_transaction(directory, grants) as context:
        context.admit_text(
            KEY,
            "unclocked needle",
            FieldClock("provider", None),
            original("unknown-original"),
            2**60,
        )
    # Search reports current independent evidence, never a parser/receipt winner
    # or the retired whole-row eligible_* suppression mechanism.
    complete = search(service, "needle")
    assert {hit.matched_text for hit in complete.hits} == {
        "obsolete needle",
        "replacement needle",
        "unclocked needle",
    }
    pages, cursor = [], None
    while True:
        page = search(service, "needle", limit=1, cursor=cursor)
        pages.extend(page.hits)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert tuple(pages) == complete.hits
    assert len({hit.document_key for hit in pages}) == 3
    assert service.get_context_resource(KEY, include_text=True).fields[
        "text_body_sha256"
    ]
    assert not (directory / "repository.sqlite3").exists()


def test_cancelled_large_rebuild_rolls_back_replacement_but_preserves_current_authority(
    directory, monkeypatch
):
    keys = {
        ResourceKey.from_native(SERVICE, "issue", str(index)) for index in range(201)
    }
    grants = production_grants() | DependencySet(resources=keys)
    with fixture_transaction(directory, grants) as context:
        context.provider(SERVICE, "github")
        for key in keys:
            context.resource(key)
            context.admit_text(
                key,
                "obsolete " + key.provider_resource_id,
                FieldClock("provider", 1),
                original("old"),
                1,
            )
    service = ContextSearchService(directory, mode="context_only")
    assert service.rebuild_search(("context_text",))["context_text"] == 201

    def index_rows():
        with closing(connect(directory / "search.sqlite3", "search")) as db:
            return tuple(
                tuple(row)
                for row in db.execute(
                    "SELECT * FROM search_documents ORDER BY document_key_json"
                )
            )

    old_index = index_rows()
    with fixture_transaction(directory, grants) as context:
        for key in keys:
            context.admit_text(
                key,
                "replacement " + key.provider_resource_id,
                FieldClock("provider", 2),
                original("new"),
                2,
            )
        retained = tuple(
            tuple(row)
            for row in context.db.execute("SELECT * FROM text_bodies ORDER BY sha256")
        )
    cancellation = KeyboardInterrupt("cancel during actual index replacement")

    class CancellingDocuments(dict):
        def items(self):
            yield next(iter(super().items()))
            raise cancellation

    replace_projection = service.search_adapter.replace_projection

    def cancelled(kind, token, documents, **options):
        return replace_projection(
            kind, token, CancellingDocuments(documents), **options
        )

    with monkeypatch.context() as fault:
        fault.setattr(service.search_adapter, "replace_projection", cancelled)
        with pytest.raises(KeyboardInterrupt) as failure:
            service.rebuild_search(("context_text",))
        assert failure.value is cancellation
    assert index_rows() == old_index
    current = search(service, "replacement", limit=250)
    assert current.backend == "authority_scan" and current.total_count == 201
    assert search(service, "obsolete").total_count == 0
    assert service.rebuild_search(("context_text",))["context_text"] == 201
    assert search(service, "replacement", limit=250).hits == current.hits
    with fixture_transaction(directory, grants) as context:
        assert (
            tuple(
                tuple(row)
                for row in context.db.execute(
                    "SELECT * FROM text_bodies ORDER BY sha256"
                )
            )
            == retained
        )
    assert not (directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("damage", ["text", "digest"])
@pytest.mark.parametrize("operation", ["read", "search", "rebuild"])
def test_damaged_current_body_stops_each_actual_reader_and_rebuild(
    directory, damage, operation
):
    with fixture_transaction(directory, production_grants()) as context:
        context.provider(SERVICE, "github")
        context.resource(KEY)
        context.admit_text(
            KEY, "genuine needle", FieldClock("provider", 1), original("body"), 1
        )
    service = ContextSearchService(directory, mode="context_only")
    service.rebuild_search(("context_text",))
    with closing(connect(directory / "context.sqlite3", "context")) as db:
        ddl = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='text_bodies_no_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER text_bodies_no_update")
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("PRAGMA ignore_check_constraints=ON")
        try:
            db.execute(
                "UPDATE text_bodies SET text_value='tampered'"
                if damage == "text"
                else "UPDATE text_bodies SET sha256=?",
                () if damage == "text" else ("f" * 64,),
            )
        finally:
            db.execute("PRAGMA ignore_check_constraints=OFF")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute(ddl)
    call = {
        "read": lambda: service.get_context_resource(KEY, include_text=True),
        "search": lambda: search(service, "needle"),
        "rebuild": lambda: service.rebuild_search(("context_text",)),
    }[operation]
    with pytest.raises((ContextError, QueryError, RepositoryFailure)) as failure:
        call()
    assert failure.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (directory / "p1-recovery-stop.json").is_file()
