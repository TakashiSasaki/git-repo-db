"""Actual current HTTP intake rejects malformed PR units before publishing fields."""

from contextlib import closing
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
    values,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)

INVALID = [
    None,
    {"head": "not an object"},
    {"base": []},
    {"head": {"sha": 123}},
    {"commits": "1"},
    {"changed_files": True},
    {"title": []},
    {"title": "unpaired surrogate \ud800"},
    {"number": 1 << 63},
    {"commits": 1 << 63},
    {"changed_files": 1 << 63},
    {"head": {"sha": "a" * 40}, "base": {"sha": "b" * 64}},
    {"head": {"sha": "aa" * 19 + "  "}},
]


@pytest.mark.parametrize("boundary", ["list", "detail"])
@pytest.mark.parametrize("invalid", INVALID)
def test_actual_http_malformed_pr_unit_rejects_before_fields_and_retries_fresh(
    provider_case, tmp_path, capsys, monkeypatch, boundary, invalid
):
    case, blocked, calls = provider_case, [True], []
    good = {
        "id": 20,
        "number": 1,
        "title": "healthy title",
        "body": "healthy body",
        "updated_at": 10,
    }
    bad = (
        None
        if invalid is None
        else {**good, "body": "REJECTED-ORIGINAL-MARKER", **invalid}
    )

    def handle(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/pulls"):
            value = (
                [bad]
                if blocked[0] and boundary == "list"
                else [{"id": 20, "number": 1}]
            )
        elif request.url.path.endswith("/pulls/1"):
            value = bad if blocked[0] and boundary == "detail" else good
        else:
            value = {"id": 10, "full_name": "owner/repo"}
        return _http_response(request, value)

    request = {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["pull_requests"],
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
        assert first["status"] == "partial"
        assert first["failure_code"] is not None
        with closing(connect(case.directory / "context.sqlite3", "context")) as db:
            assert not db.execute(
                "SELECT 1 FROM text_bodies WHERE text_value LIKE '%REJECTED-ORIGINAL-MARKER%'"
            ).fetchall()
            assert not db.execute("PRAGMA foreign_key_check").fetchall()
        before = len(calls)
        blocked[0], request["new_request"] = False, False
        second, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert second["status"] == "complete"
    assert calls[before:] == [
        "/repos/owner/repo",
        "/repos/owner/repo/pulls",
        "/repos/owner/repo/pulls/1",
    ]
    assert values(case.view(capsys, case.keys["pull"]), "title") == ["healthy title"]
    assert not (case.directory / "transport-archive").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()


def test_actual_http_detail_cannot_publish_another_pr_and_retries_original_owner(
    provider_case, tmp_path, capsys, monkeypatch
):
    case, wrong, paths = provider_case, [True], []

    def handle(http):
        paths.append(http.url.path)
        if http.url.path.endswith("/pulls"):
            value = [{"id": 20, "number": 1}]
        elif http.url.path.endswith("/pulls/1"):
            value = {
                "id": 21 if wrong[0] else 20,
                "number": 1,
                "title": "foreign original" if wrong[0] else "actual owner",
            }
        else:
            value = {"id": 10, "full_name": "owner/repo"}
        return _http_response(http, value)

    request = {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["pull_requests"],
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
        assert (
            first["status"] == "partial" and first["failure_code"] == "SCOPE_MISMATCH"
        )
        with closing(connect(case.directory / "context.sqlite3", "context")) as db:
            assert not db.execute(
                "SELECT 1 FROM resources WHERE resource_kind='pull_request' AND provider_resource_id=?",
                (case.keys["other_pull"].provider_resource_id,),
            ).fetchall()
        wrong[0], request["new_request"] = False, False
        second, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert second["status"] == "complete"
    assert values(case.view(capsys, case.keys["pull"]), "title") == ["actual owner"]
    assert paths.count("/repos/owner/repo/pulls/1") == 2


def test_actual_http_normalizer_programming_error_keeps_original_exception(
    provider_case, tmp_path, capsys, monkeypatch
):
    from repo_catalog.adapters.github import production_intake

    original = AttributeError("synthetic implementation defect")

    def broken(*args, **kwargs):
        raise original

    monkeypatch.setattr(production_intake, "normalize_pull_request", broken)

    def handle(http):
        value = (
            [{"id": 20, "number": 1}]
            if http.url.path.endswith("/pulls")
            else {"id": 10, "full_name": "owner/repo"}
        )
        return _http_response(http, value)

    request = {
        "operation": "sync",
        "service_instance_uuidv4": provider_case.service,
        "source_registration_uuidv4": provider_case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["pull_requests"],
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(AttributeError) as raised:
            _network_cli(provider_case, tmp_path, capsys, monkeypatch, client, request)
    assert raised.value is original
    with closing(connect(provider_case.directory / "context.sqlite3", "context")) as db:
        assert not db.execute(
            "SELECT 1 FROM resources WHERE resource_kind='pull_request'"
        ).fetchall()
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
