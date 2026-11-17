"""Malformed same-page GraphQL siblings cannot erase valid admitted resources."""

import json

import httpx
import pytest

from tests.e2e.test_separated_cli import run
from tests.e2e.test_separated_cli_pr_assessment import query
from tests.e2e.test_separated_cli_provider_regressions import (
    GraphQLFixture,
    _comment,
    _connection,
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


@pytest.mark.parametrize("page", ["root", "child"])
@pytest.mark.parametrize("malformation", ["idless", "non-object"])
def test_cli_graphql_comment_page_keeps_valid_prefix_and_retries_same_request(
    provider_case, tmp_path, capsys, monkeypatch, page, malformation
):
    case, api, broken = provider_case, GraphQLFixture(), [True]

    def handle(request):
        response = api.response(request)
        if request.method != "POST":
            return response
        variables = json.loads(request.content)["variables"]
        child = "id" in variables
        response.read()
        payload = response.json()
        if page == "child" and not child:
            payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0][
                "comments"
            ]["nodes"] = []
            return _http_response(request, payload)
        if child != (page == "child"):
            return response
        if child:
            comments = payload["data"]["node"]["comments"]
        else:
            comments = payload["data"]["repository"]["pullRequest"]["reviewThreads"][
                "nodes"
            ][0]["comments"]
        invalid = _comment(11)
        if broken[0]:
            if malformation == "idless":
                invalid.pop("databaseId")
            else:
                invalid = "not a resource object"
        comments.update(_connection([_comment(10), invalid]))
        return _http_response(request, payload)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result, request = _network_cli(case, tmp_path, capsys, monkeypatch, client)
        assert result["status"] == "partial"
        assert result["failure_code"] == (
            "CANONICAL_ID_REQUIRED" if malformation == "idless" else "API_SCHEMA"
        )
        view = case.view(capsys, case.keys["comment"])
        assert list(view["resolved_texts"].values()) == ["comment-10"]
        original_producers = view["fields"]["text_body_sha256"]
        thread = case.view(capsys, case.keys["thread"])
        assert thread["collections"]
        assert all(item["state"] == "partial" for item in thread["collections"])
        assert any(
            {tuple(member) for member in item["members"]}
            == {case.keys["comment"].coordinates()}
            for item in thread["collections"]
        )
        assert all(
            {tuple(member) for member in item["members"]}
            <= {case.keys["comment"].coordinates()}
            for item in thread["collections"]
        )
        current = run(capsys, "query", "context-resources", "--catalog", case.directory)
        # Neither the absent decimal database ID nor the opaque Node ID may
        # manufacture a second resource or lend fields to the valid sibling.
        assert "comment-11" not in json.dumps(current)
        assert "NODE-11" not in json.dumps(current)
        selected = query(capsys, case, "pr-documents", "--thread-id", "thread-one")
        assert not selected["coverage"]["complete_for_requested_scope"]
        before_retry = len(api.calls)
        broken[0] = False
        request["new_request"] = False
        resumed, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert resumed["status"] == "complete"
    assert resumed["request_identity"] == result["request_identity"]
    posts = [body for method, _, body in api.calls[before_retry:] if method == "POST"]
    assert posts[0]["variables"]["cursor"] is None
    assert list(case.view(capsys, case.keys["reply"])["resolved_texts"].values()) == [
        "comment-11"
    ]
    selected = query(capsys, case, "pr-documents", "--thread-id", "thread-one")
    assert selected["state"] == "complete" and selected["total_count"] == 2
    # A later successful read adds producers; it does not rewrite the first read.
    assert all(
        candidate
        in case.view(capsys, case.keys["comment"])["fields"]["text_body_sha256"]
        for candidate in original_producers
    )
    assert not (case.directory / "core.sqlite3").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()
