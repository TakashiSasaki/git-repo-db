"""Integration tests for P6 Search indexing, automatic fallback, and ordinary blob exclusion."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_core import OID, Provenance, ScalarClaim
from repo_catalog.domain.production_query import SearchQuery
from tests.integration.p6.conftest import populate_rich_catalog


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_search_projection_and_five_fallback_scenarios_never_stop_catalog(
    tmp_path: Path, fmt: str
) -> None:
    catalog_dir = tmp_path / f"search_{fmt}"
    populate_rich_catalog(catalog_dir, fmt=fmt)
    service = ProductionQueryService(catalog_dir)

    # Scenario 2 (initial state): search.sqlite3 exists but is empty/unbuilt -> authority_scan
    unbuilt_resp = service.search(SearchQuery(query_text="p6"))
    assert unbuilt_resp.backend == "authority_scan"
    assert unbuilt_resp.backends_by_kind == {
        "context_text": "authority_scan",
        "git_metadata": "authority_scan",
        "notes": "authority_scan",
    }
    assert unbuilt_resp.total_count >= 3
    baseline_hits = unbuilt_resp.hits

    # Build projections -> backend == "projection" with identical hits
    counts = service.rebuild_search()
    assert counts["git_metadata"] > 0
    assert counts["notes"] > 0
    assert counts["context_text"] > 0

    proj_resp = service.search(SearchQuery(query_text="p6"))
    assert proj_resp.backend == "projection"
    assert proj_resp.backends_by_kind == {
        "context_text": "projection",
        "git_metadata": "projection",
        "notes": "projection",
    }
    assert proj_resp.hits == baseline_hits

    # Verify individual projection kinds:
    # - git_metadata (tree entry name README.md)
    tree_resp = service.search(
        SearchQuery(query_text="README.md", projection_kinds=("git_metadata",))
    )
    assert tree_resp.backend == "projection"
    assert tree_resp.total_count == 1
    assert tree_resp.hits[0].authoritative_summary["kind"] == "tree_entry"

    # - notes (note body text "Approved for P6!")
    note_resp = service.search(
        SearchQuery(query_text="Approved for P6!", projection_kinds=("notes",))
    )
    assert note_resp.backend == "projection"
    assert note_resp.total_count == 1
    assert note_resp.hits[0].authoritative_summary["note_retained"] is True

    # - context_text (PR body text "snapshot consistency")
    ctx_resp = service.search(
        SearchQuery(
            query_text="snapshot consistency", projection_kinds=("context_text",)
        )
    )
    assert ctx_resp.backend == "projection"
    assert ctx_resp.total_count == 1

    # Scenario 4a: Delete a row from search_documents (incomplete projection) -> authority_scan
    with closing(connect(catalog_dir / "search.sqlite3", "search")) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM search_documents WHERE projection_kind='git_metadata'")
        db.commit()

    del_resp = service.search(SearchQuery(query_text="p6"))
    assert del_resp.backend == "authority_scan"
    assert del_resp.backends_by_kind["git_metadata"] == "authority_scan"
    assert del_resp.backends_by_kind["notes"] == "projection"
    assert del_resp.backends_by_kind["context_text"] == "projection"
    assert del_resp.hits == baseline_hits
    assert not (catalog_dir / "p1-recovery-stop.json").exists()

    # Rebuild and test Scenario 4b: Insert a phantom key not in authority -> authority_scan
    service.rebuild_search()
    with closing(connect(catalog_dir / "search.sqlite3", "search")) as db:
        token_str = service.snapshot_token().encode()
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO search_documents VALUES('git_metadata',?,?,?)",
            (token_str, '["phantom","key"]', "p6 phantom match"),
        )
        db.commit()

    phantom_resp = service.search(SearchQuery(query_text="p6"))
    assert phantom_resp.backends_by_kind["git_metadata"] == "authority_scan"
    assert phantom_resp.hits == baseline_hits
    assert not (catalog_dir / "p1-recovery-stop.json").exists()

    # Scenario 5a: Drop search_documents table -> authority_scan
    with closing(connect(catalog_dir / "search.sqlite3", "search")) as db:
        db.execute("DROP TABLE search_documents")

    drop_resp = service.search(SearchQuery(query_text="p6"))
    assert drop_resp.backend == "authority_scan"
    assert drop_resp.hits == baseline_hits
    assert not (catalog_dir / "p1-recovery-stop.json").exists()

    # Scenario 5b: Overwrite search.sqlite3 with corrupt bytes (DatabaseError) -> authority_scan
    (catalog_dir / "search.sqlite3").write_bytes(b"corrupt-sqlite-header-bytes")
    corrupt_resp = service.search(SearchQuery(query_text="p6"))
    assert corrupt_resp.backend == "authority_scan"
    assert corrupt_resp.hits == baseline_hits
    assert not (catalog_dir / "p1-recovery-stop.json").exists()

    # Rebuild recovers cleanly from corrupt search.sqlite3
    service.rebuild_search()
    recovered_resp = service.search(SearchQuery(query_text="p6"))
    assert recovered_resp.backend == "projection"
    assert recovered_resp.hits == baseline_hits

    # Scenario 1: Unlink search.sqlite3 from disk -> authority_scan
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(catalog_dir / "search.sqlite3") + suffix)
        if p.exists():
            p.unlink()
    missing_resp = service.search(SearchQuery(query_text="p6"))
    assert missing_resp.backend == "authority_scan"
    assert missing_resp.hits == baseline_hits
    assert not (catalog_dir / "p1-recovery-stop.json").exists()

    # Scenario 3: Stale snapshot_token_json after a new Core write -> authority_scan
    service.rebuild_search()
    assert service.search(SearchQuery(query_text="p6")).backend == "projection"

    width = 40 if fmt == "sha1" else 64
    new_oid = OID(fmt, "7" * width)

    def _admit_new_obj(core_tx):
        with GitCore.for_transaction(core_tx) as c:
            c.admit_object(new_oid)

    PairCoordinator(catalog_dir).admit(_admit_new_obj, lambda ctx_tx: None)
    stale_resp = service.search(SearchQuery(query_text="p6"))
    assert stale_resp.backend == "authority_scan"
    assert [h.matched_text for h in stale_resp.hits] == [
        h.matched_text for h in baseline_hits
    ]
    assert not (catalog_dir / "p1-recovery-stop.json").exists()


def test_ordinary_file_blobs_are_never_indexed_in_search(tmp_path: Path) -> None:
    catalog_dir = tmp_path / "no_ordinary_blobs"
    populate_rich_catalog(
        catalog_dir, fmt="sha1", include_core=True, include_context=False
    )
    service = ProductionQueryService(catalog_dir)

    # Admit a nominal blob object with reported scalar claims containing a secret needle
    blob_oid = OID("sha1", "8" * 40)
    prov = Provenance("remote", "obs-blob", "c-1", "git", "1", "reported")
    core = GitCore(catalog_dir / "core.sqlite3")
    try:
        core.admit_object(blob_oid)
        core.admit_claim(ScalarClaim(blob_oid, "type", "blob", prov))
        core.admit_claim(
            ScalarClaim(
                blob_oid,
                "decoded_name",
                "ORDINARY_BLOB_SECRET_NEEDLE",
                prov,
            )
        )
    finally:
        core.close()

    service.rebuild_search()
    resp_proj = service.search(
        SearchQuery(
            query_text="ORDINARY_BLOB_SECRET_NEEDLE",
            projection_kinds=("git_metadata",),
        )
    )
    assert resp_proj.backend == "projection"
    assert resp_proj.total_count == 0

    # Also verify authority_scan excludes ordinary file blobs
    (catalog_dir / "search.sqlite3").unlink()
    resp_scan = service.search(
        SearchQuery(
            query_text="ORDINARY_BLOB_SECRET_NEEDLE",
            projection_kinds=("git_metadata",),
        )
    )
    assert resp_scan.backend == "authority_scan"
    assert resp_scan.total_count == 0
