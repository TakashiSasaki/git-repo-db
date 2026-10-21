"""Integration tests for P6 Git-only, Context-only, Paired queries, and verification-aware byte reads."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_context import CoverageScope
from repo_catalog.domain.p1_core import CoreCoverageScope, CoreFailure
from repo_catalog.domain.production_context import ContextError
from repo_catalog.domain.production_query import QueryError
from tests.integration.p6.conftest import (
    INSTANCE,
    REPOSITORY,
    SERVICE,
    SOURCE,
    populate_rich_catalog,
)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_core_only_queries_objects_claims_relations_notes_and_coverage(
    tmp_path: Path, fmt: str
) -> None:
    catalog_dir = tmp_path / f"core_only_{fmt}"
    fixtures = populate_rich_catalog(
        catalog_dir, fmt=fmt, include_core=True, include_context=False
    )
    assert not (catalog_dir / "context.sqlite3").exists()

    service = ProductionQueryService(catalog_dir)
    assert service.detect_mode() == "core_only"
    token = service.snapshot_token()
    assert token.mode == "core_only"
    assert token.repository_uuidv4 == REPOSITORY
    assert token.catalog_instance_uuidv4 == INSTANCE
    assert token.core_sha256 is not None
    assert token.context_sha256 is None

    # Repository view
    repo_view = service.get_repository_view()
    assert repo_view.repository_uuidv4 == REPOSITORY
    assert repo_view.claims["name"][0].value == "git-repo-db"
    assert repo_view.claims["object_format"][0].value == fmt

    # Verified commit with competing reported message claim
    commit_obj = fixtures["commit_obj"]
    commit_view = service.get_git_object(commit_obj.oid, include_bytes=True)
    assert commit_view.native_type == "commit"
    assert commit_view.metadata_retained is True
    assert commit_view.retained_bytes is not None
    assert commit_view.retained_bytes.available is True
    assert commit_view.retained_bytes.verified is True
    assert commit_view.retained_bytes.body_bytes == commit_obj.body
    assert commit_view.scalars["message"].canonical == [
        "known",
        "feat: add p6 production query support\n",
    ]
    assert commit_view.scalars["message"].reported_conflict is True
    assert len(commit_view.scalars["message"].alternatives) == 2

    # Commit relations: commit_tree and commit_parents
    tree_obj = fixtures["tree_obj"]
    missing_parent_oid = fixtures["missing_parent_oid"]
    assert commit_view.relations["commit_tree"].canonical == [
        "complete",
        [[0, fmt, tree_obj.oid.full_oid]],
    ]
    assert commit_view.relations["commit_parents"].canonical == [
        "complete",
        [[0, fmt, missing_parent_oid.full_oid]],
    ]

    # Tree object & tree_entries relation
    tree_view = service.get_git_object(tree_obj.oid, include_bytes=True)
    assert tree_view.native_type == "tree"
    assert tree_view.scalars["type"].canonical == ["known", "tree"]
    assert tree_view.scalars["size"].canonical == ["known", len(tree_obj.body)]
    assert tree_view.relations["tree_entries"].canonical == [
        "complete",
        [
            [
                ["100644", b"README.md".hex()],
                fmt,
                fixtures["missing_blob_oid"].full_oid,
            ]
        ],
    ]

    # Tag object & tag_target relation
    tag_obj = fixtures["tag_obj"]
    tag_view = service.get_git_object(tag_obj.oid, include_bytes=True)
    assert tag_view.native_type == "tag"
    assert tag_view.scalars["tag_name"].canonical == ["known", "v1.0.0-p6"]
    assert tag_view.relations["tag_target"].canonical == [
        "complete",
        [[0, fmt, commit_obj.oid.full_oid]],
    ]

    # Missing child/parent OIDs are nominal entries in git_objects without retained bytes
    missing_view = service.get_git_object(missing_parent_oid, include_bytes=True)
    assert missing_view.metadata_retained is False
    assert missing_view.scalars["type"].canonical is None
    assert missing_view.retained_bytes is not None
    assert missing_view.retained_bytes.available is False

    # Metadata-only commit with reported claims and partial relation group
    unretained_view = service.get_git_object(
        fixtures["unretained_commit_oid"], include_bytes=True
    )
    assert unretained_view.metadata_retained is False
    assert unretained_view.scalars["type"].canonical is None
    assert unretained_view.scalars["type"].alternatives[0]["value"] == [
        "known",
        "commit",
    ]
    assert (
        unretained_view.relations["commit_parents"].alternatives[0]["status"]
        == "partial"
    )

    # Ref observations
    obs_page = service.list_git_observations(
        observation_kind="ref", ref_prefix="refs/heads/"
    )
    assert obs_page.total_count == 1
    assert obs_page.items[0].observation.value["ref"] == "refs/heads/main"

    # Notes captures, target projection, byte read, and inventory
    capture = fixtures["capture"]
    notes_page = service.list_notes_captures(notes_ref="refs/notes/commits")
    assert notes_page.total_count == 1
    cap_view = notes_page.items[0]
    assert cap_view.capture == capture
    assert commit_obj.oid in cap_view.targets

    note_target = service.get_notes_target(capture, commit_obj.oid, include_bytes=True)
    assert note_target.canonical == fixtures["note_blob"].oid
    assert note_target.role_verified is True
    assert note_target.note_retained is True
    assert note_target.reported_conflict is True
    assert note_target.note_bytes is not None
    assert note_target.note_bytes.available is True
    assert note_target.note_bytes.body_bytes == fixtures["note_body_bytes"]

    inventories = service.list_notes_inventories(capture)
    assert any(
        inv.receiver_verified and inv.status == "complete" for inv in inventories
    )
    assert any(
        not inv.receiver_verified and inv.status == "partial" for inv in inventories
    )

    # Core Coverage
    cov_scope = CoreCoverageScope("repository", (REPOSITORY, "refs"))
    cov = service.get_core_coverage(cov_scope)
    assert cov.state == "complete"
    assert cov.known_empty is False
    assert cov.latest_observed_at_us == 1700000300000000

    # Context queries on core_only catalog fail closed with STORE_UNAVAILABLE
    with pytest.raises(QueryError) as err:
        service.list_context_resources()
    assert err.value.code == "STORE_UNAVAILABLE"


def test_context_only_queries_resources_fields_relations_inventories_and_coverage(
    tmp_path: Path,
) -> None:
    catalog_dir = tmp_path / "context_only"
    fixtures = populate_rich_catalog(
        catalog_dir, fmt="sha1", include_core=False, include_context=True
    )
    assert not (catalog_dir / "core.sqlite3").exists()

    service = ProductionQueryService(catalog_dir)
    assert service.detect_mode() == "context_only"
    token = service.snapshot_token()
    assert token.mode == "context_only"
    assert token.context_sha256 is not None
    assert token.core_sha256 is None

    # Providers and Sources
    providers = service.list_providers()
    assert len(providers) == 1
    assert providers[0].service_instance_uuidv4 == SERVICE
    assert providers[0].provider_kind == "github"

    sources = service.list_source_views(SERVICE)
    assert len(sources) == 1
    assert sources[0].source_registration_uuidv4 == SOURCE
    assert sources[0].repositories == (REPOSITORY,)
    assert len(sources[0].inventories) == 1
    assert sources[0].inventories[0].state == "complete"

    # Pull Request 42: competing candidates, explicit null vs unobserved, text body, and unresolved Core refs
    pr_view = service.get_context_resource(fixtures["pr_key"], include_text=True)
    assert pr_view.repository_uuidv4 == REPOSITORY
    assert pr_view.identifier_namespace is None
    assert len(pr_view.fields["title"]) == 1
    assert json.loads(pr_view.fields["title"][0].value_json) == (
        "Implement P6 query and search"
    )
    # Competing incomparable candidates on 'state'
    assert len(pr_view.fields["state"]) == 2
    assert {json.loads(c.value_json) for c in pr_view.fields["state"]} == {
        "open",
        "merged",
    }
    # Explicit null vs unobserved
    assert "closed_at" in pr_view.fields
    assert json.loads(pr_view.fields["closed_at"][0].value_json) is None
    assert "milestone" not in pr_view.fields

    # Verified UTF-8 text body
    assert any(
        "P6 snapshot consistency" in (txt or "")
        for txt in pr_view.resolved_texts.values()
    )

    # In context_only mode, Core dependencies are reported with available=False, required=False
    assert len(pr_view.core_dependencies) == 2
    assert all(not dep.available for dep in pr_view.core_dependencies)
    assert all(not dep.required for dep in pr_view.core_dependencies)

    # Child resources and relations
    children = service.list_context_resources(identifier_namespace=fixtures["pr_key"])
    assert children.total_count == 3
    comment_view = service.get_context_resource(fixtures["comment_key"])
    assert comment_view.identifier_namespace == fixtures["pr_key"]
    assert comment_view.document_kind == "review_comment"
    assert len(comment_view.relations) == 1
    assert comment_view.relations[0].relation_kind == "in_review_thread"
    assert comment_view.relations[0].members == (fixtures["thread_key"],)

    # Context Coverage: non-empty complete collection vs known-empty complete collection
    pr_rev_cov = service.get_context_coverage(
        CoverageScope.collection(
            fixtures["pr_key"], "reviews", fixtures["ctx_prov_1"], "reviews"
        )
    )
    assert pr_rev_cov.state == "complete"
    assert pr_rev_cov.known_empty is False

    issue_empty_cov = service.get_context_coverage(
        CoverageScope.collection(
            fixtures["issue_key"], "comments", fixtures["ctx_prov_2"], "comments"
        )
    )
    assert issue_empty_cov.state == "complete"
    assert issue_empty_cov.known_empty is True

    # Core queries on context_only catalog fail closed with STORE_UNAVAILABLE
    with pytest.raises(QueryError) as err:
        service.list_git_objects()
    assert err.value.code == "STORE_UNAVAILABLE"


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_paired_cross_store_resolution_present_vs_absent_core_oids(
    tmp_path: Path, fmt: str
) -> None:
    catalog_dir = tmp_path / f"paired_{fmt}"
    fixtures = populate_rich_catalog(
        catalog_dir, fmt=fmt, include_core=True, include_context=True
    )

    service = ProductionQueryService(catalog_dir)
    assert service.detect_mode() == "paired"
    paired_pr = service.get_paired_resource(
        fixtures["pr_key"], include_text=True, include_core_bytes=True
    )
    assert paired_pr.snapshot_token == service.snapshot_token().encode()

    by_role = {res.reference.role: res for res in paired_pr.core_resolutions}
    assert set(by_role.keys()) == {"head", "base"}

    # 'head' points to commit_obj.oid which IS in Core and linked via link_core
    head_res = by_role["head"]
    assert head_res.available_in_core is True
    assert head_res.core_required is True
    assert head_res.object_view is not None
    assert head_res.object_view.oid == fixtures["commit_obj"].oid
    assert head_res.object_view.native_type == "commit"
    assert head_res.object_view.retained_bytes is not None
    assert head_res.object_view.retained_bytes.body_bytes == fixtures["commit_obj"].body
    assert len(head_res.notes_targets) == 1
    assert head_res.notes_targets[0].canonical == fixtures["note_blob"].oid

    # 'base' points to absent_oid which is NOT in Core (reported only)
    base_res = by_role["base"]
    assert base_res.available_in_core is False
    assert base_res.core_required is False
    assert base_res.object_view is None
    assert base_res.notes_targets == ()


def test_verification_aware_byte_reads_detect_corruption_and_fence_catalog(
    tmp_path: Path,
) -> None:
    # 1. Tamper with retained_metadata in core.sqlite3 (core_only mode verifies selected bytes)
    cat_meta = tmp_path / "corrupt_metadata"
    fix_meta = populate_rich_catalog(
        cat_meta, fmt="sha1", include_core=True, include_context=False
    )
    commit_oid = fix_meta["commit_obj"].oid
    service_meta = ProductionQueryService(cat_meta)

    valid_res = service_meta.read_metadata_bytes(commit_oid)
    assert valid_res.available is True and valid_res.verified is True

    with closing(connect(cat_meta / "core.sqlite3", "core")) as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_retained_metadata_update'"
        ).fetchone()[0]
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TRIGGER p1_immutable_retained_metadata_update")
        db.execute(
            "UPDATE retained_metadata SET body=x'636f7272757074' WHERE full_oid=?",
            (commit_oid.full_oid,),
        )
        db.execute(trigger)
        db.commit()

    with pytest.raises(CoreFailure) as exc_info:
        service_meta.read_metadata_bytes(commit_oid)
    assert exc_info.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (cat_meta / "p1-recovery-stop.json").exists()

    # Subsequent reads are fenced
    with pytest.raises(CoreFailure) as fenced_err:
        service_meta.snapshot_token()
    assert fenced_err.value.code == "RECOVERY_STOP"

    # 2. Tamper with retained_notes in core.sqlite3 (core_only mode verifies selected bytes)
    cat_note = tmp_path / "corrupt_note"
    fix_note = populate_rich_catalog(
        cat_note, fmt="sha1", include_core=True, include_context=False
    )
    service_note = ProductionQueryService(cat_note)
    capture = fix_note["capture"]
    note_oid = fix_note["note_blob"].oid

    valid_note = service_note.read_note_bytes(
        capture, fix_note["commit_obj"].oid, note_oid
    )
    assert valid_note.available is True and valid_note.verified is True

    with closing(connect(cat_note / "core.sqlite3", "core")) as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_retained_notes_update'"
        ).fetchone()[0]
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TRIGGER p1_immutable_retained_notes_update")
        db.execute("UPDATE retained_notes SET body=x'001122'")
        db.execute(trigger)
        db.commit()

    with pytest.raises(CoreFailure) as note_exc:
        service_note.read_note_bytes(capture, fix_note["commit_obj"].oid, note_oid)
    assert note_exc.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (cat_note / "p1-recovery-stop.json").exists()

    # 3. Tamper with text_bodies in context.sqlite3 (context_only mode verifies selected bytes)
    cat_ctx = tmp_path / "corrupt_context_text"
    populate_rich_catalog(cat_ctx, fmt="sha1", include_core=False, include_context=True)
    service_ctx = ProductionQueryService(cat_ctx)

    with closing(connect(cat_ctx / "context.sqlite3", "context")) as db:
        digest = db.execute("SELECT sha256 FROM text_bodies LIMIT 1").fetchone()[0]
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='text_bodies_no_update'"
        ).fetchone()[0]
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TRIGGER text_bodies_no_update")
        db.execute(
            "UPDATE text_bodies SET text_value='tampered text' WHERE sha256=?",
            (digest,),
        )
        db.execute(trigger)
        db.commit()

    with pytest.raises(ContextError) as ctx_exc:
        service_ctx.read_context_text(digest)
    assert ctx_exc.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (cat_ctx / "p1-recovery-stop.json").exists()
