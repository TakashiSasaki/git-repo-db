"""Provider text/path/target queries do not require local native Git bodies."""

from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.domain.p1_context import canonical
from repo_catalog.domain.provider_acquisition import (
    ProviderPullRequestIntake,
    ProviderReviewCommentIntake,
    make_provenance,
)
from tests.integration.p5.test_pr_assessment import Fixture


def test_exact_provider_document_selectors_are_independent_of_git_bytes_but_not_current_listing_gaps(
    tmp_path,
):
    fixture = Fixture(tmp_path, core=False)
    fixture.code()
    original = make_provenance(
        "actual-provider-document-fixture", {"read": "review-comments"}
    )
    fixture.admit(
        review_comments=(
            ProviderReviewCommentIntake(
                100,
                {
                    "id": 300,
                    "body": "actual Provider body",
                    "path": "a.txt",
                    "commit_id": fixture.head.object_oid,
                },
                300,
                original,
            ),
        )
    )
    fixture.observation(
        fixture.parent,
        "review_comments",
        original,
        canonical({}),
        300,
        "complete",
        fixture.comments[:1],
    )
    service = PRQueryService(tmp_path, mode="context_only")
    for selectors in (
        {},
        {"path": "a.txt"},
        {"commit": fixture.head},
        {"path": "absent.txt"},
    ):
        result = service.get_pr_documents(
            fixture.parent, kinds=("review_comments",), **selectors
        )
        assert result.state == "complete"
        assert result.page.total_count == (
            0 if selectors.get("path") == "absent.txt" else 1
        )
        assert result.git_metadata == {
            "state": "not_applicable",
            "reason": "document_scope",
        }
        if result.page.items:
            assert set(result.page.items[0].resolved_texts.values()) == {
                "actual Provider body"
            }
    # Native code completeness remains an explicit different request.
    assert service.get_pr_code(fixture.parent, require_git=True).state != "complete"
    assert service.get_pr_code(fixture.parent, require_git=False).state == "complete"
    fixture.admit(
        pull_requests=(
            ProviderPullRequestIntake(
                {
                    **fixture.payload,
                    "head": {"sha": fixture.base.object_oid},
                    "updated_at": "2026-02-01T00:00:00Z",
                },
                400,
                make_provenance(
                    "actual-provider-document-fixture",
                    {"read": "different-current-head"},
                ),
            ),
        )
    )
    assert (
        service.get_pr_documents(fixture.parent, kinds=("review_comments",)).state
        == "complete"
    )
    for selectors in (
        {"path": "a.txt"},
        {"commit": fixture.head},
        {"path": "absent.txt"},
    ):
        result = service.get_pr_documents(
            fixture.parent, kinds=("review_comments",), **selectors
        )
        assert result.state == "partial"
        assert any(gap["kind"] == "code_selector" for gap in result.coverage["missing"])
    assert not (tmp_path / "core.sqlite3").exists()
    assert not (tmp_path / "p1-recovery-stop.json").exists()
