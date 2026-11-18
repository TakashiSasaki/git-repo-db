"""Explicit code scopes and historical originals never borrow sibling/current facts."""

import json

import pytest

from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.domain.provider_acquisition import (
    ProviderFileContextIntake,
    ProviderPullRequestIntake,
    make_provenance,
)
from repo_catalog.domain.query_contracts import PageRequest, QueryError
from tests.integration.p5.test_pr_assessment import Fixture


@pytest.mark.parametrize("kind", ["pr_commits", "pr_files"])
def test_selected_code_listing_is_complete_without_borrowing_sibling_scope(
    tmp_path, kind
):
    fixture = Fixture(tmp_path)
    fixture.code()
    original = fixture.query()
    sibling = next(row for row in original.collections if row["kind"] != kind)
    fixture.observation(
        fixture.parent,
        sibling["kind"],
        make_provenance("scope-fixture", {"read": "sibling-failed"}),
        sibling["alternatives"][0]["scope_json"],
        400,
        "partial",
        (),
    )
    assert fixture.query().state == "partial"
    selected = fixture.query(listing_kinds=(kind,), page=PageRequest(limit=1))
    assert selected.state == "complete"
    assert [entry["kind"] for entry in selected.collections] == [kind]
    assert selected.page.total_count == (1 if kind == "pr_commits" else 2)
    if selected.page.has_more:
        with pytest.raises(QueryError, match="CURSOR"):
            fixture.query(page=PageRequest(limit=1, cursor=selected.page.next_cursor))


@pytest.mark.parametrize("kinds", [(), ("reviews",), "pr_files", (True,)])
def test_invalid_code_listing_scope_is_refused_before_opening_catalog(tmp_path, kinds):
    fixture = Fixture(tmp_path)
    with pytest.raises(QueryError, match="INVALID_INPUT"):
        fixture.query(listing_kinds=kinds)


def test_original_capture_retains_members_and_anchors_after_current_detail_changes(
    tmp_path,
):
    fixture = Fixture(tmp_path)
    fixture.code()
    original = fixture.query()
    capture = next(row for row in original.collections if row["kind"] == "pr_files")
    provenance = capture["alternatives"][0]["provenance_json"]
    fixture.admit(
        pull_requests=(
            ProviderPullRequestIntake(
                {
                    **fixture.payload,
                    "head": {"sha": fixture.base.object_oid},
                    "updated_at": "2026-02-01T00:00:00Z",
                },
                400,
                make_provenance("scope-fixture", {"read": "new-detail"}),
            ),
        )
    )
    assert fixture.query().state != "complete"
    service = PRQueryService(tmp_path)
    first = service.get_pr_code_capture(
        fixture.parent,
        "pr_files",
        provenance,
        require_git=True,
        page=PageRequest(limit=1),
    )
    assert first.state == "complete"
    assert first.anchors == {key: original.anchors[key] for key in ("head", "base")}
    assert first.coverage["scope_kind"] == "captured_listing"
    assert first.coverage["current_provider_state_asserted"] is False
    assert first.page.total_count == 2 and first.page.has_more
    second = service.get_pr_code_capture(
        fixture.parent,
        "pr_files",
        provenance,
        require_git=True,
        page=PageRequest(limit=1, cursor=first.page.next_cursor),
    )
    assert second.state == "complete"
    assert second.page.snapshot_token == first.page.snapshot_token
    assert {view.resource for view in first.page.items + second.page.items} == set(
        fixture.files[:2]
    )


def test_capture_exposes_only_attributes_from_actual_original_member_reads(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.code(patch="captured patch")
    original = fixture.query()
    capture = next(row for row in original.collections if row["kind"] == "pr_files")
    provenance = capture["alternatives"][0]["provenance_json"]
    original_reads = json.loads(capture["alternatives"][0]["scope_json"])[
        "member_provenance_jsons"
    ]
    later = make_provenance("scope-fixture", {"read": "later-patch"})
    fixture.admit(
        pr_files=(
            ProviderFileContextIntake(
                100,
                {"filename": "a.txt", "patch": "new patch", "status": "added"},
                500,
                later,
            ),
        )
    )
    result = PRQueryService(tmp_path).get_pr_code_capture(
        fixture.parent, "pr_files", provenance
    )
    item = next(item for item in result.page.items if item.resource == fixture.files[0])
    assert {json.loads(candidate.value_json) for candidate in item.fields["patch"]} == {
        "captured patch"
    }
    assert "status" not in item.fields
    assert all(
        candidate.provenance_json in original_reads
        for candidates in item.fields.values()
        for candidate in candidates
    )
    assert item.relations == item.collections == item.repository_dependencies == ()
    assert result.coverage["current_provider_state_asserted"] is False


def test_unanchored_original_members_remain_visible_without_fabricated_comparison(
    tmp_path,
):
    fixture = Fixture(tmp_path)
    fixture.code(anchored=False, capture="unanchored")
    provenance = make_provenance(
        "actual-fixture-api", {"capture": "unanchored", "kind": "pr_files"}
    )
    result = PRQueryService(tmp_path).get_pr_code_capture(
        fixture.parent, "pr_files", provenance
    )
    assert result.state == "unknown" and result.anchors == {}
    assert result.page.total_count == 2
    assert all(not item.fields for item in result.page.items)
    assert result.coverage["missing"][0]["reason"] == "captured_comparison_unavailable"


def test_exact_capture_key_and_full_scope_budgets_are_mandatory(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.code()
    original = fixture.query()
    capture = next(row for row in original.collections if row["kind"] == "pr_files")
    provenance = capture["alternatives"][0]["provenance_json"]
    service = PRQueryService(tmp_path)
    with pytest.raises(QueryError, match="CAPTURE_NOT_FOUND"):
        service.get_pr_code_capture(fixture.parent, "pr_commits", provenance)
    with pytest.raises(QueryError, match="QUERY_BUDGET"):
        service.get_pr_code_capture(
            fixture.parent,
            "pr_files",
            provenance,
            max_work=1,
            page=PageRequest(limit=1),
        )
    with pytest.raises(QueryError, match="QUERY_BUDGET"):
        service.get_pr_code_capture(
            fixture.parent,
            "pr_files",
            provenance,
            max_bytes=1,
            page=PageRequest(limit=1),
        )


def test_repository_preflight_uses_requested_code_kinds_before_parent_pagination(
    tmp_path,
):
    from tests.integration.p5.test_pr_parent_assessment import Parents

    fixture = Parents(tmp_path)
    fixture.roster(members=(fixture.parent,))
    fixture.code()
    original = fixture.query(require_git=False)
    files = next(row for row in original.collections if row["kind"] == "pr_files")
    fixture.observation(
        fixture.parent,
        "pr_files",
        make_provenance("scope-fixture", {"read": "partial-files"}),
        files["alternatives"][0]["scope_json"],
        400,
        "partial",
        (),
    )
    service = PRQueryService(tmp_path)
    assert (
        service.list_pr_assessments(
            fixture.provider_repository, assessment="code", require_git=False
        ).state
        == "partial"
    )
    selected = service.list_pr_assessments(
        fixture.provider_repository,
        assessment="code",
        listing_kinds=("pr_commits",),
        require_git=False,
        page=PageRequest(limit=1),
    )
    assert selected.state == "complete"
    assert selected.page.items[0].assessment.page.total_count == 1
    assert [row["kind"] for row in selected.page.items[0].assessment.collections] == [
        "pr_commits"
    ]
    with pytest.raises(QueryError, match="INVALID_INPUT"):
        service.list_pr_assessments(
            fixture.provider_repository, listing_kinds=("pr_commits",)
        )
