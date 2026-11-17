"""Rejected transport JSON has no domain original and retries a genuine read."""

import json
from contextlib import closing
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.github.production_intake import make_document_key
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from tests.e2e.test_separated_cli import document
from tests.e2e.test_separated_cli_provider_regressions import (
    GraphQLFixture,
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)

MARKER = "REJECTED-RAW-JSON-TRANSPORT-ORIGINAL-DO-NOT-ARCHIVE"


def assert_no_original(case):
    for role in ("context", "operational"):
        with closing(connect(case.directory / (role + ".sqlite3"), role)) as db:
            tables = [
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            assert not {
                "fetch_occurrences",
                "parsed_results",
                "payloads",
                "stored_bytes",
                "exchange_staging",
            } & set(tables)
            for table in tables:
                assert all(
                    MARKER not in repr(tuple(row))
                    for row in db.execute(f'SELECT * FROM "{table}"')
                )
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert not (case.directory / "transport-archive").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("boundary", ["pr-list", "pr-detail", "issue-comment"])
def test_actual_rest_raw_json_rejection_retries_fresh_without_original_or_fake_terminal(
    provider_case, tmp_path, capsys, monkeypatch, boundary
):
    case, blocked, calls = provider_case, [True], []
    comment = make_document_key(case.keys["pull"], "issue_comment", "comment", "400")
    case.authority = document(
        tmp_path,
        "raw-authority.json",
        {
            "grants": DependencySet(
                resources={*case.keys.values(), comment},
                sources={case.source},
                provider_registrations={case.service},
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    target_path = {
        "pr-list": "/repos/owner/repo/pulls",
        "pr-detail": "/repos/owner/repo/pulls/1",
        "issue-comment": "/repos/owner/repo/issues/1/comments",
    }[boundary]

    def handle(request):
        calls.append(request.url.path)
        if blocked[0] and request.url.path == target_path:
            return httpx.Response(
                200,
                request=request,
                stream=httpx.ByteStream(("{" + MARKER + "]").encode()),
            )
        if request.url.path == "/repos/owner/repo":
            value = {"id": 10, "full_name": "owner/repo"}
        elif request.url.path.endswith("/pulls"):
            value = [{"id": 20, "number": 1}]
        elif request.url.path.endswith("/pulls/1"):
            value = {"id": 20, "number": 1, "body": "actual PR body"}
        elif request.url.path.endswith("/issues"):
            value = []
        else:
            assert request.url.path == target_path
            value = [{"id": 400, "body": "actual comment body"}]
        return _http_response(request, value)

    request_document = {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["issue_comments"]
        if boundary == "issue-comment"
        else ["pull_requests"],
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        rejected, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document,
            clock_us=lambda: 100,
        )
        assert rejected["status"] == "partial" and rejected["failure_code"]
        assert MARKER not in repr(rejected)
        assert_no_original(case)
        before = len(calls)
        blocked[0], request_document["new_request"] = False, False
        accepted, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document,
            clock_us=lambda: 200,
        )
    assert accepted["status"] == "complete"
    assert target_path in calls[before:] and calls.count(target_path) == 2
    assert accepted["http_attempts"] == len(calls) - before
    assert accepted["request_identity"] == rejected["request_identity"]
    view = case.view(
        capsys, comment if boundary == "issue-comment" else case.keys["pr_body"]
    )
    assert set(view["resolved_texts"].values()) == {
        "actual comment body" if boundary == "issue-comment" else "actual PR body"
    }
    assert_no_original(case)


@pytest.mark.parametrize("boundary", ["root", "nested-child"])
def test_actual_graphql_raw_json_rejection_preserves_real_prefix_and_retries_root_without_original(
    provider_case, tmp_path, capsys, monkeypatch, boundary
):
    case, fixture, blocked = provider_case, GraphQLFixture(), [True]
    rejected_reads, actual_reads = [], []

    def handle(request):
        actual_reads.append((request.method, request.url.path))
        if request.method == "POST":
            variables = json.loads(request.content)["variables"]
            current = "nested-child" if "id" in variables else "root"
            if blocked[0] and current == boundary:
                rejected_reads.append(current)
                return httpx.Response(
                    200,
                    request=request,
                    stream=httpx.ByteStream(("{" + MARKER + "]").encode()),
                )
        return fixture.response(request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        rejected, request_document = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, clock_us=lambda: 100
        )
        assert rejected["status"] == "partial" and rejected["failure_code"]
        assert MARKER not in repr(rejected)
        assert rejected_reads == [boundary]
        assert_no_original(case)
        if boundary == "nested-child":
            assert set(
                case.view(capsys, case.keys["comment"])["resolved_texts"].values()
            ) == {"comment-10"}
        before = len(actual_reads)
        blocked[0], request_document["new_request"] = False, False
        accepted, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document,
            clock_us=lambda: 200,
        )
    assert accepted["status"] == "complete"
    assert accepted["http_attempts"] == len(actual_reads) - before
    assert accepted["request_identity"] == rejected["request_identity"]
    assert set(case.view(capsys, case.keys["reply"])["resolved_texts"].values()) == {
        "comment-11"
    }
    roots = [
        body
        for method, _, body in fixture.calls
        if method == "POST" and "id" not in body["variables"]
    ]
    assert len(roots) == (1 if boundary == "root" else 2)
    assert_no_original(case)
