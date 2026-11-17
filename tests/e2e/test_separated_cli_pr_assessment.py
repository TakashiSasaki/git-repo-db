"""Ordinary CLI reaches exact PR assessments rather than generic resource browse."""

import httpx

from repo_catalog.domain.provider_acquisition import (
    ProviderPullRequestIntake,
    make_provenance,
)
from tests.e2e.test_separated_cli import run
from tests.e2e.test_separated_cli_provider_regressions import (
    GraphQLFixture,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def query(capsys, case, command, *options, expected=0):
    return run(
        capsys,
        "query",
        command,
        "--catalog",
        case.directory,
        "--service-instance",
        case.service,
        "--provider-resource-id",
        case.keys["pull"].provider_resource_id,
        *options,
        expected=expected,
    )


def test_normal_cli_pr_assessment_requires_actual_listing_and_respects_finite_work(
    provider_case, tmp_path, capsys
):
    case = provider_case
    case.admit(
        tmp_path,
        capsys,
        pull_requests=(
            ProviderPullRequestIntake(
                {"id": 20, "title": "known standalone metadata"},
                10,
                make_provenance("local-provider", "standalone-pr"),
            ),
        ),
    )
    for command, options in (
        ("pr-code", ("--no-require-git",)),
        ("pr-documents", ("--kind", "reviews")),
    ):
        result = query(capsys, case, command, *options)
        assert result["state"] == "unknown"
        assert not result["coverage"]["complete_for_requested_scope"]
        assert result["coverage"]["missing"]
        assert result["items"] == []
    error = query(
        capsys, case, "pr-code", "--no-require-git", "--max-work", 0, expected=2
    )
    assert error["code"] == "INVALID_INPUT"
    assert not (case.directory / "core.sqlite3").exists()
    assert not (case.directory / "operational.sqlite3").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()


def test_normal_cli_pr_documents_preflights_all_thread_children_before_pagination(
    provider_case, tmp_path, capsys, monkeypatch
):
    case, api = provider_case, GraphQLFixture()
    with httpx.Client(transport=httpx.MockTransport(api.response)) as client:
        acquired, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client)
    assert acquired["status"] == "complete"
    result = query(
        capsys, case, "pr-documents", "--kind", "review_threads", "--limit", 1
    )
    assert result["state"] == "complete"
    assert result["coverage"]["complete_for_requested_scope"]
    assert result["coverage"]["missing"] == []
    assert len(result["items"]) == 1 and result["has_more"]
    assert result["total_count"] == 3
    assert result["next_cursor"]
    next_page = query(
        capsys,
        case,
        "pr-documents",
        "--kind",
        "review_threads",
        "--limit",
        1,
        "--cursor",
        result["next_cursor"],
    )
    assert next_page["state"] == "complete" and len(next_page["items"]) == 1
    assert next_page["items"] != result["items"]
    assert not (case.directory / "core.sqlite3").exists()


def test_normal_cli_selected_thread_remains_complete_when_unrelated_sibling_fails(
    provider_case, tmp_path, capsys, monkeypatch
):
    import json

    from tests.e2e.test_separated_cli_provider_regressions import (
        _http_response,
        _thread,
    )

    case, api = provider_case, GraphQLFixture()

    def handler(request):
        response = api.response(request)
        if (
            request.method == "POST"
            and "id" not in json.loads(request.content)["variables"]
        ):
            response.read()
            value = response.json()
            value["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"].append(
                _thread("thread-two", {"not": "a valid connection"})
            )
            return _http_response(request, value)
        return response

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        acquired, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client)
    assert acquired["status"] == "partial"
    family = query(capsys, case, "pr-documents", "--kind", "review_threads")
    assert not family["coverage"]["complete_for_requested_scope"]
    selected = query(
        capsys, case, "pr-documents", "--thread-id", "thread-one", "--limit", 1
    )
    assert selected["state"] == "complete"
    assert selected["coverage"]["complete_for_requested_scope"]
    assert selected["total_count"] == 2 and selected["has_more"]
    assert len(selected["items"]) == 1
    assert selected["collections"][0]["kind"] == "review_thread_comments"
    following = query(
        capsys,
        case,
        "pr-documents",
        "--thread-id",
        "thread-one",
        "--limit",
        1,
        "--cursor",
        selected["next_cursor"],
    )
    assert following["state"] == "complete" and not following["has_more"]
    assert {
        item["provider_resource_id"]
        for page in (selected, following)
        for item in page["items"]
    } == {
        case.keys["comment"].provider_resource_id,
        case.keys["reply"].provider_resource_id,
    }
    matching = query(
        capsys,
        case,
        "pr-documents",
        "--thread-id",
        "thread-one",
        "--no-resolved",
        "--no-outdated",
    )
    assert matching["state"] == "complete" and matching["total_count"] == 2
    mismatch = query(
        capsys, case, "pr-documents", "--thread-id", "thread-one", "--resolved"
    )
    assert mismatch["state"] == "complete" and mismatch["total_count"] == 0
    assert not (case.directory / "core.sqlite3").exists()
