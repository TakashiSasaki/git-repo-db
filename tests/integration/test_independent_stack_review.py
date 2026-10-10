"""Additional disposable counterexamples for the stacked PR review."""

from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.application.query_service import QueryService
from tests.support.github_runtime import github_runtime as github_runtime
from tests.support.github_runtime import sync


def test_current_review_comment_is_not_complete_when_review_parent_is_conflicted(
    github_runtime,
):
    store, repo, _, _ = github_runtime
    sync(store, repo)
    request = repo["repository_uuidv4"] + ":41"
    resources = CurrentResources(store)
    parent = store.one(
        "SELECT * FROM review_resources WHERE change_request_id=? AND kind='review' LIMIT 1",
        (request,),
    )
    child = store.one(
        "SELECT * FROM review_resources WHERE change_request_id=? AND kind='review-comment' LIMIT 1",
        (request,),
    )
    child_candidate = resources.candidate_from_row("review_resources", child)
    child_candidate.pop("field_evidence")
    child_candidate["review_provider_resource_id"] = parent[
        "provider_change_request_document_id"
    ]
    assert resources.admit(child_candidate, source="import").status == "accepted"
    alternate = resources.candidate_from_row("review_resources", parent)
    alternate.pop("field_evidence")
    alternate["body"] = "independent conflicting review parent"
    assert resources.admit(alternate, source="import").status == "conflict"
    result = QueryService(store.path).query(
        "pr documents",
        {
            "repo": repo["repository_uuidv4"],
            "provider_change_request_number": 41,
            "document_kind": "review-comment",
        },
    )
    assert result.status == "partial"
    assert any(
        gap.get("document_kind") == "review-comment"
        and gap["reason"] == "current_resource_unresolved"
        for gap in result.coverage.missing
    )
