"""Regression evidence for P6 review corrections; all stores are disposable."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import SnapshotReadLimits
from repo_catalog.application.production_query import (
    ProductionQueryService,
    _paginate_items,
)
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_core import OID, CoreFailure
from repo_catalog.domain.production_query import (
    PageRequest,
    QueryError,
    SearchQuery,
    canonical_json,
)
from tests.integration.p6.conftest import (
    ORIGIN,
    REPOSITORY,
    SERVICE,
    UnlimitedTestBudget,
    init_catalog,
    make_native,
    make_tree,
    populate_rich_catalog,
)
from tests.support.context_admission import fixture_transaction


def _mutate(path, table, assignment):
    """Restore exact trigger schema after synthetic persisted-value corruption."""
    with sqlite3.connect(path) as db:
        triggers = db.execute(
            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name=?",
            (table,),
        ).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name + '"')
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE " + table + " SET " + assignment)
        for _, sql in triggers:
            db.execute(sql)


def _rechecksum(cursor, key):
    envelope = json.loads(base64.urlsafe_b64decode(cursor))
    envelope["payload"]["last_key"] = key
    envelope["checksum_sha256"] = hashlib.sha256(
        ("p6-cursor-v1:" + canonical_json(envelope["payload"])).encode()
    ).hexdigest()
    return base64.urlsafe_b64encode(canonical_json(envelope).encode()).decode()


@pytest.mark.parametrize(
    "key",
    [
        [],
        ["sha1"],
        ["sha1", "a" * 39],
        [True, "a" * 40],
        ["sha1", 1],
        [["sha1"], "a" * 40],
        ["sha256", "g" * 64],
    ],
)
def test_recomputed_checksum_still_validates_key(tmp_path, key):
    populate_rich_catalog(tmp_path, include_context=False)
    service = ProductionQueryService(tmp_path)
    page = service.list_git_objects(PageRequest(limit=1))
    with pytest.raises(QueryError) as error:
        service.list_git_objects(
            PageRequest(limit=1, cursor=_rechecksum(page.next_cursor, key))
        )
    assert error.value.code == "INVALID_CURSOR"
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_recomputed_valid_position_grants_no_authenticity(tmp_path):
    populate_rich_catalog(tmp_path, include_context=False)
    service = ProductionQueryService(tmp_path)
    page = service.list_git_objects(PageRequest(limit=1))
    result = service.list_git_objects(
        PageRequest(limit=1, cursor=_rechecksum(page.next_cursor, ["sha1", "0" * 40]))
    )
    assert result.items[0].object_oid == page.items[0].object_oid


@pytest.mark.parametrize("stored", ["'{'", "'123'", "CAST(x'ff' AS TEXT)"])
def test_persisted_json_utf8_and_typed_metadata_stop(tmp_path, stored):
    populate_rich_catalog(tmp_path, include_context=False)
    _mutate(tmp_path / "core.sqlite3", "repository_claims", "value=" + stored)
    with pytest.raises(CoreFailure) as error:
        ProductionQueryService(tmp_path).get_repository_view()
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (tmp_path / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as stopped:
        ProductionQueryService(tmp_path).snapshot_token()
    assert stopped.value.code == "RECOVERY_STOP"


def test_metadata_queries_do_not_hydrate_or_rehash_all_retained_bodies(tmp_path):
    fixture = populate_rich_catalog(tmp_path)
    oid = fixture["commit_obj"].object_oid
    _mutate(
        tmp_path / "core.sqlite3", "retained_metadata", "body=zeroblob(length(body))"
    )
    service = ProductionQueryService(tmp_path)
    assert service.get_git_object(oid).metadata_retained
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as corrupt:
        service.read_metadata_bytes(oid)
    assert corrupt.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (tmp_path / "p1-recovery-stop.json").exists()


def test_core_and_context_snapshot_capabilities_expire(tmp_path):
    populate_rich_catalog(tmp_path)
    with ProductionQueryService(tmp_path).open_snapshot() as snap:
        core, context = snap.core, snap.context
    with pytest.raises(CoreFailure) as expired:
        core.sql("SELECT 1")
    assert expired.value.code == "CAPABILITY_EXPIRED"
    with pytest.raises(Exception) as expired_context:
        context.resources()
    assert getattr(expired_context.value, "code", None) == "CAPABILITY_EXPIRED"


@pytest.mark.parametrize("mode", ["paired", "core_only", "context_only"])
def test_snapshot_budget_refusal_preserves_ordinary_reads(tmp_path, mode):
    populate_rich_catalog(tmp_path)
    service = ProductionQueryService(
        tmp_path, mode=mode, read_limits=SnapshotReadLimits(max_store_bytes=1)
    )
    with pytest.raises(QueryError) as error:
        service.snapshot_token()
    assert error.value.code == "QUERY_BUDGET"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    ProductionQueryService(tmp_path, mode=mode).snapshot_token()


@pytest.mark.parametrize(
    "query", ["日本語", "😀", "a", "*", '"', "\\", "\x00", "café", "p6", "P6"]
)
def test_literal_unicode_short_special_search_semantics_and_cost_phases(
    tmp_path, query
):
    populate_rich_catalog(tmp_path)
    resource = ResourceKey.from_native(SERVICE, "pull_request", "42")
    grants = DependencySet(
        resources={resource},
        repositories={REPOSITORY},
        provider_registrations={SERVICE},
    )
    with fixture_transaction(tmp_path, grants) as context:
        context.admit_field(
            FieldCandidate(
                resource,
                "special",
                canonical('日本語 😀 a * " \\ \x00 café p6 P6'),
                FieldClock("test", 1000),
                canonical({"source": "github.rest", "evidence": "special"}),
                1000,
            )
        )
    service = ProductionQueryService(tmp_path)
    before = service.search(SearchQuery(query_text=query))
    assert before.total_count > 0
    service.rebuild_search()
    after = service.search(SearchQuery(query_text=query))
    assert before.hits == after.hits
    assert after.backend == "verified_projection_scan"
    assert service.last_costs_ns["snapshot_total"] > 0
    assert service.last_costs_ns["authority_validation"] > 0
    assert service.last_costs_ns["snapshot_token_generation"] > 0
    assert service.last_costs_ns["authority_search_validation:context_text"] > 0
    assert service.last_costs_ns["projection_scan:context_text"] > 0
    with pytest.raises(QueryError, match="INVALID_QUERY"):
        SearchQuery(query_text="")


def test_binary_notes_rebuild_and_scan_equivalence(tmp_path):
    init_catalog(tmp_path, ("core", "search"))
    blob = make_native("sha1", "blob", b"hello\xff\x00world")
    target = OID("sha1", "1" * 40)
    tree = make_tree(
        "sha1", [(b"100644", target.object_oid.encode(), blob.object_oid.object_oid)]
    )
    from repo_catalog.domain.p1_core import Provenance
    from repo_catalog.domain.ref_observation import (
        NotesMapping,
        NotesMappingEvidence,
        RefObservation,
        RefObservationClaim,
        RefObservationKey,
        new_uuid7,
    )

    key = RefObservationKey(ORIGIN, new_uuid7())
    subject = RefObservation(key, REPOSITORY, b"refs/notes/binary", "source", "visible")
    claim = RefObservationClaim(
        key,
        Provenance("source", "read", "claim", "test", "1"),
        "present",
        root_object_oid=tree.object_oid,
    )
    mapping = NotesMapping(
        tree.object_oid,
        "git-notes",
        "1",
        "native-notes-tree",
        target,
        blob.object_oid,
        target.object_oid,
    )
    evidence = NotesMappingEvidence(
        claim,
        mapping,
        "single-path",
        Provenance(
            "source", "receiver", "path", "native-notes", "1", "receiver_intrinsic"
        ),
        (tree,),
    )
    with closing(GitCore(tmp_path / "core.sqlite3")) as core:
        core.admit_ref_observation(subject)
        core.admit_ref_observation_claim(claim)
        core.admit_ref_note(evidence, blob, str(uuid4()), UnlimitedTestBudget())
    service = ProductionQueryService(tmp_path)
    before = service.search(
        SearchQuery(query_text="\\xff", projection_kinds=("notes",))
    )
    assert before.total_count == 1
    assert "hello\\xff\x00world" in before.hits[0].matched_text
    service.rebuild_search(("notes",))
    assert (
        service.search(
            SearchQuery(query_text="\\xff", projection_kinds=("notes",))
        ).hits
        == before.hits
    )


def test_oversize_derivative_row_falls_back_before_text_construction(
    tmp_path, monkeypatch
):
    from repo_catalog.adapters.sqlite.production_search import BoundedDocuments

    populate_rich_catalog(tmp_path)
    service = ProductionQueryService(tmp_path)
    before = service.search(SearchQuery(query_text="p6"))
    service.rebuild_search()
    with sqlite3.connect(tmp_path / "search.sqlite3") as db:
        db.execute(
            "UPDATE search_documents SET searchable_text=? WHERE projection_kind='git_metadata'",
            ("p6" * (1024 * 1024),),
        )
    original = BoundedDocuments.__setitem__

    def guarded(self, key, value):
        assert len(value) < 1024 * 1024
        return original(self, key, value)

    monkeypatch.setattr(BoundedDocuments, "__setitem__", guarded)
    after = service.search(SearchQuery(query_text="p6"))
    assert after.hits == before.hits
    assert after.backends_by_kind["git_metadata"] == "authority_scan"
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_page_selection_memory_scales_with_limit_not_catalog(tmp_path):
    populate_rich_catalog(tmp_path, include_context=False)
    token = ProductionQueryService(tmp_path).snapshot_token().encode()

    class Item:
        alive = 0
        peak = 0

        def __init__(self, n):
            self.key = ("sha1", f"{n:040x}")
            Item.alive += 1
            Item.peak = max(Item.peak, Item.alive)

        def __del__(self):
            Item.alive -= 1

    for count in (100, 10000):
        Item.peak = 0
        selected = _paginate_items(
            (Item(n) for n in range(count, -1, -1)),
            key_fn=lambda item: item.key,
            page=PageRequest(limit=5),
            endpoint_kind="git_objects",
            filters={},
            snapshot_token=token,
        )
        assert len(selected.items) == 5
        assert selected.total_count == count + 1
        assert Item.peak <= 14
        del selected


def test_unlimited_p6_read_configuration_is_rejected(tmp_path):
    with pytest.raises(QueryError) as invalid:
        ProductionQueryService(tmp_path, read_limits=None)
    assert invalid.value.code == "INVALID_LIMIT"


@pytest.mark.parametrize("stored", ["'123'", "'[]'", "'{}'"])
def test_persisted_provenance_shape_failure_stops(tmp_path, stored):
    populate_rich_catalog(tmp_path, include_context=False)
    _mutate(tmp_path / "core.sqlite3", "repository_claims", "provenance=" + stored)
    with pytest.raises(CoreFailure) as invalid:
        ProductionQueryService(tmp_path).get_repository_view()
    assert invalid.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (tmp_path / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("operation", ["search", "rebuild"])
def test_persisted_search_observation_shape_stops(tmp_path, operation):
    populate_rich_catalog(tmp_path, include_context=False)
    _mutate(tmp_path / "core.sqlite3", "git_observations", "value='[]'")
    service = ProductionQueryService(tmp_path)
    with pytest.raises(CoreFailure) as invalid:
        if operation == "search":
            service.search(
                SearchQuery(query_text="p6", projection_kinds=("git_metadata",))
            )
        else:
            service.rebuild_search(("git_metadata",))
    assert invalid.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (tmp_path / "p1-recovery-stop.json").exists()


def test_derivative_deep_json_falls_back_without_catalog_stop(tmp_path):
    populate_rich_catalog(tmp_path)
    service = ProductionQueryService(tmp_path)
    expected = service.search(SearchQuery(query_text="P6"))
    service.rebuild_search()
    with sqlite3.connect(tmp_path / "search.sqlite3") as db:
        key = "[" * 10000 + "0" + "]" * 10000
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(
            "UPDATE search_documents SET document_key_json=?, searchable_text='P6' WHERE projection_kind='git_metadata' AND document_key_json=(SELECT min(document_key_json) FROM search_documents WHERE projection_kind='git_metadata')",
            (key,),
        )
    result = service.search(SearchQuery(query_text="P6"))
    assert result.hits == expected.hits
    assert result.backends_by_kind["git_metadata"] == "authority_scan"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
