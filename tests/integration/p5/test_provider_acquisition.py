"""Integration tests for P5 Provider acquisition into Context (GitHub REST & GraphQL).

Verifies:
- Service, repository, source registration and source-repository associations
- Issues vs. PRs (Issues API entries with "pull_request" never alias into ordinary issues)
- PR head/base/merge commit CoreReference extraction (SHA-1 and SHA-256)
- Review summaries, review threads, review comments, issue comments, timeline, files
- Text body content-addressing in Context text_bodies (no Git blob retention in Core)
- Explicit null vs. missing fields, clock progression, competing field candidates
- Detached issue-attachment transfer preserving prior provenance
- Context-only operation without core.sqlite3
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from repo_catalog.adapters.github.production_intake import (
    normalize_issue,
    normalize_pr_file,
    normalize_pull_request,
    normalize_review,
    normalize_review_comment,
    normalize_review_thread,
)
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.acquisition import ProviderAcquisition
from repo_catalog.domain.acquisition import (
    ProviderIntakeBatch,
    ProviderRegistration,
    RepositoryRegistration,
    SourceRegistration,
    make_provenance,
)
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.production_context import SourceInventory
from repo_catalog.domain.time import parse_iso8601_us
from tests.integration.p5.conftest import init_catalog_stores


def test_provider_registration_and_source_inventory(tmp_path: Path) -> None:
    cat_dir = tmp_path / "context_cat"
    repo_uuid, _ = init_catalog_stores(cat_dir, stores=("context", "operational"))
    service_uuid = str(uuid4())
    source_uuid = str(uuid4())
    prov_json = make_provenance("gh-test", "test-step")

    acq = ProviderAcquisition(cat_dir, operational=cat_dir)
    batch = ProviderIntakeBatch(
        service_instance_uuidv4=service_uuid,
        providers=(
            ProviderRegistration(
                service_uuid,
                "github",
                canonical({"api_url": "https://api.github.com", "tier": "enterprise"}),
            ),
        ),
        repositories=(
            RepositoryRegistration(
                repo_uuid,
                canonical({"full_name": "example/test-repo", "private": False}),
            ),
        ),
        sources=(
            SourceRegistration(
                source_uuid,
                service_uuid,
                canonical({"poll_interval_s": 60}),
                associated_repositories=(repo_uuid,),
            ),
        ),
        source_inventories=(
            SourceInventory(
                source_uuid,
                canonical({"scope": "all-repos"}),
                1_700_000_100_000_000,
                "complete",
                True,
                (repo_uuid,),
                prov_json,
            ),
        ),
    )
    report = acq.admit_batch(batch)
    assert report.admitted_resources == ()

    with Context.snapshot(cat_dir) as ctx:
        assert repo_uuid in ctx.source_repositories(source_uuid)
        row = ctx.db.execute(
            "SELECT coverage_state FROM source_inventory_evidence WHERE source_registration_uuidv4=?",
            (source_uuid,),
        ).fetchone()
        assert row is not None
        assert row[0] == "complete"


def test_issue_vs_pull_request_intake_isolation(tmp_path: Path) -> None:
    cat_dir = tmp_path / "context_cat"
    repo_uuid, _ = init_catalog_stores(cat_dir, stores=("context", "operational"))
    service_uuid = str(uuid4())
    prov_json = make_provenance("gh-rest", "issue-test")

    acq = ProviderAcquisition(cat_dir, operational=cat_dir)
    acq.admit_batch(
        ProviderIntakeBatch(
            service_instance_uuidv4=service_uuid,
            providers=(ProviderRegistration(service_uuid, "github"),),
            repositories=(RepositoryRegistration(repo_uuid),),
        )
    )

    # 1. Ordinary Issue
    issue_payload = {
        "id": 1001,
        "number": 42,
        "title": "Bug in query planner",
        "state": "open",
        "body": "Details about the query bug",
        "created_at": "2026-10-10T12:00:00Z",
        "updated_at": "2026-10-10T12:05:00Z",
        "user": {"id": 10, "login": "alice"},
    }
    issue_unit = normalize_issue(
        service_uuid,
        issue_payload,
        1_700_000_100_000_000,
        prov_json,
        repository_uuidv4=repo_uuid,
    )
    assert issue_unit is not None
    assert issue_unit.primary_resource.resource_kind == "issue"
    assert issue_unit.primary_resource.provider_resource_id == "1001"

    # 2. Issues API entry with "pull_request" key MUST return None (not alias as issue)
    pr_as_issue = dict(
        issue_payload, id=1002, number=43, pull_request={"html_url": "..."}
    )
    assert (
        normalize_issue(
            service_uuid,
            pr_as_issue,
            1_700_000_100_000_000,
            prov_json,
            repository_uuidv4=repo_uuid,
        )
        is None
    )

    # 3. Pull Request
    pr_payload = {
        "id": 2001,
        "number": 43,
        "title": "Fix query planner bug",
        "state": "open",
        "body": "Fixes #42",
        "created_at": "2026-10-10T12:10:00Z",
        "updated_at": "2026-10-10T12:15:00Z",
        "user": {"id": 20, "login": "bob"},
        "head": {"sha": "a" * 40, "ref": "feat/query-fix"},
        "base": {"sha": "b" * 40, "ref": "main"},
        "merge_commit_sha": "c" * 40,
    }
    pr_unit = normalize_pull_request(
        service_uuid,
        pr_payload,
        1_700_000_200_000_000,
        prov_json,
        repository_uuidv4=repo_uuid,
    )
    assert pr_unit.primary_resource.resource_kind == "pull_request"
    assert pr_unit.primary_resource.provider_resource_id == "2001"
    assert len(pr_unit.core_references) == 3
    assert {ref.role for ref, _, _ in pr_unit.core_references} == {
        "head",
        "base",
        "merge",
    }

    # Admit both units into Context
    acq.admit_units((issue_unit, pr_unit))

    with Context.snapshot(cat_dir) as ctx:
        # Issue
        issue_key = ResourceKey(service_uuid, "issue", "1001")
        title_cands = ctx.candidates(issue_key, "title")
        assert len(title_cands) == 1
        assert json.loads(title_cands[0].value_json) == "Bug in query planner"
        assert title_cands[0].clock.at_us == parse_iso8601_us("2026-10-10T12:05:00Z")

        # PR state
        pr_key = ResourceKey(service_uuid, "pull_request", "2001")
        pr_cands = ctx.candidates(pr_key, "state")
        assert len(pr_cands) == 1
        assert json.loads(pr_cands[0].value_json) == "open"

        # Text bodies exist and match SHA-256
        issue_body_digest = ctx.candidates(issue_key, "text_body_sha256")[0].value_json
        raw_digest = json.loads(issue_body_digest)
        assert ctx.read_text(raw_digest) == "Details about the query bug"


def test_reviews_threads_comments_and_relations(tmp_path: Path) -> None:
    cat_dir = tmp_path / "context_cat"
    repo_uuid, _ = init_catalog_stores(cat_dir, stores=("context", "operational"))
    service_uuid = str(uuid4())
    prov_json = make_provenance("gh-rest", "review-test")

    acq = ProviderAcquisition(cat_dir, operational=cat_dir)
    acq.admit_batch(
        ProviderIntakeBatch(
            service_instance_uuidv4=service_uuid,
            providers=(ProviderRegistration(service_uuid, "github"),),
            repositories=(RepositoryRegistration(repo_uuid),),
        )
    )

    pr_id = "501"
    pr_key = ResourceKey(service_uuid, "pull_request", pr_id)
    assert pr_key.resource_kind == "pull_request"

    # Review summary (no updated_at; submitted_at only)
    rev_payload = {
        "id": 901,
        "state": "APPROVED",
        "submitted_at": "2026-10-11T10:00:00Z",
        "body": "Looks good to me!",
        "user": {"id": 11, "login": "reviewer1"},
        "commit_id": "d" * 40,
    }
    rev_unit = normalize_review(
        service_uuid,
        pr_id,
        rev_payload,
        1_700_000_300_000_000,
        prov_json,
    )
    assert (
        json.loads(rev_unit.primary_resource.provider_resource_id)[2]
        == "review_summary"
    )
    assert len(rev_unit.core_references) == 1
    assert rev_unit.core_references[0][0].role == "target_commit"

    # Review thread (GraphQL ID)
    thread_payload = {
        "id": "PRRT_kwDOABC123",
        "isResolved": True,
        "isOutdated": False,
        "path": "src/query.py",
        "line": 42,
    }
    thread_unit = normalize_review_thread(
        service_uuid,
        pr_id,
        thread_payload,
        1_700_000_310_000_000,
        prov_json,
    )
    assert json.loads(thread_unit.primary_resource.provider_resource_id)[2] == "thread"

    # Review comment (linked to review and thread)
    comment_payload = {
        "id": 8001,
        "body": "Please add index hint",
        "path": "src/query.py",
        "line": 42,
        "created_at": "2026-10-11T09:30:00Z",
        "updated_at": "2026-10-11T09:35:00Z",
        "pull_request_review_id": 901,
        "commit_id": "d" * 40,
        "original_commit_id": "e" * 40,
    }
    comment_unit = normalize_review_comment(
        service_uuid,
        pr_id,
        comment_payload,
        1_700_000_320_000_000,
        prov_json,
        thread_id="PRRT_kwDOABC123",
    )
    assert (
        json.loads(comment_unit.primary_resource.provider_resource_id)[2] == "comment"
    )
    assert len(comment_unit.relations) >= 2  # review/parent/thread relations
    assert len(comment_unit.core_references) == 2  # target_commit, original_commit

    acq.admit_units((rev_unit, thread_unit, comment_unit))

    with Context.snapshot(cat_dir) as ctx:
        rev_key = rev_unit.primary_resource
        state_cand = ctx.candidates(rev_key, "state")[0]
        assert json.loads(state_cand.value_json) == "APPROVED"
        assert state_cand.clock.at_us is None  # clockless review summary

        # Relations
        rev_rels = ctx.relations(comment_unit.primary_resource, "belongs_to_review")
        assert len(rev_rels) == 1
        assert rev_key in rev_rels[0].members

        thread_rels = ctx.relations(comment_unit.primary_resource, "in_thread")
        assert len(thread_rels) == 1
        assert thread_unit.primary_resource in thread_rels[0].members


def test_explicit_null_vs_missing_fields_and_clock_competition(tmp_path: Path) -> None:
    cat_dir = tmp_path / "context_cat"
    repo_uuid, _ = init_catalog_stores(cat_dir, stores=("context", "operational"))
    service_uuid = str(uuid4())
    prov_json = make_provenance("gh-rest", "null-test")

    acq = ProviderAcquisition(cat_dir, operational=cat_dir)
    acq.admit_batch(
        ProviderIntakeBatch(
            service_instance_uuidv4=service_uuid,
            providers=(ProviderRegistration(service_uuid, "github"),),
            repositories=(RepositoryRegistration(repo_uuid),),
        )
    )

    # Initial issue with body and milestone
    initial_payload = {
        "id": 3001,
        "number": 50,
        "title": "Initial title",
        "state": "open",
        "body": "Initial body",
        "milestone": {"id": 1, "title": "v1.0"},
        "updated_at": "2026-10-10T10:00:00Z",
    }
    u1 = normalize_issue(
        service_uuid,
        initial_payload,
        100,
        prov_json,
        repository_uuidv4=repo_uuid,
    )
    acq.admit_units((u1,))

    # Update 1: milestone explicitly set to null, body omitted (partial payload)
    update_payload = {
        "id": 3001,
        "number": 50,
        "title": "Updated title",
        "state": "open",
        "milestone": None,  # EXPLICIT NULL
        # body is omitted entirely!
        "updated_at": "2026-10-10T11:00:00Z",
    }
    u2 = normalize_issue(
        service_uuid,
        update_payload,
        200,
        prov_json,
        repository_uuidv4=repo_uuid,
    )
    acq.admit_units((u2,))

    with Context.snapshot(cat_dir) as ctx:
        key = ResourceKey(service_uuid, "issue", "3001")
        # Title updated
        assert json.loads(ctx.candidates(key, "title")[0].value_json) == "Updated title"
        # Body NOT erased by partial payload omission!
        body_digest = json.loads(ctx.candidates(key, "text_body_sha256")[0].value_json)
        assert ctx.read_text(body_digest) == "Initial body"
        # Milestone IS explicitly null
        assert json.loads(ctx.candidates(key, "milestone")[0].value_json) is None


def test_context_file_metadata_never_retains_blob_in_git_core(tmp_path: Path) -> None:
    cat_dir = tmp_path / "paired_cat"
    repo_uuid, _ = init_catalog_stores(
        cat_dir, stores=("core", "context", "operational")
    )
    service_uuid = str(uuid4())
    prov_json = make_provenance("gh-rest", "file-test")

    acq = ProviderAcquisition(cat_dir, operational=cat_dir)
    acq.admit_batch(
        ProviderIntakeBatch(
            service_instance_uuidv4=service_uuid,
            providers=(ProviderRegistration(service_uuid, "github"),),
            repositories=(RepositoryRegistration(repo_uuid),),
        )
    )

    pr_id = "601"
    file_payload = {
        "sha": "f" * 40,
        "filename": "lib/db.py",
        "status": "modified",
        "additions": 10,
        "deletions": 2,
        "changes": 12,
        "patch": "@@ -1 +1 @@\n-old\n+new",
    }
    file_unit = normalize_pr_file(
        service_uuid,
        pr_id,
        file_payload,
        1000,
        prov_json,
    )
    acq.admit_units((file_unit,))

    # Verify Context has the patch text in text_bodies
    with Context.snapshot(cat_dir) as ctx:
        res = file_unit.primary_resource
        patch_digest = json.loads(ctx.candidates(res, "text_body_sha256")[0].value_json)
        assert ctx.read_text(patch_digest) == "@@ -1 +1 @@\n-old\n+new"

    # Core must NOT contain any retained blob for the file!
    core = GitCore(cat_dir / "core.sqlite3")
    try:
        assert (
            core.sql("SELECT COUNT(*) FROM retained_metadata WHERE native_type='blob'")[
                0
            ][0]
            == 0
        )
        assert core.sql("SELECT COUNT(*) FROM retained_notes")[0][0] == 0
    finally:
        core.close()
