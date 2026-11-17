"""Actual Source inventory evidence uses Provider keys without Git identity guesses."""

import json
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.github.production_intake import (
    NORMALIZER_MODULE,
    NORMALIZER_VERSION,
)
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.p1_context import CoverageScope, ResourceKey, canonical
from repo_catalog.domain.production_context import SourceInventory
from repo_catalog.domain.provider_acquisition import (
    ProviderIntakeBatch,
    make_provenance,
)
from tests.e2e.test_separated_cli import document, run
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def prepare(case, tmp_path, capsys):
    second = ResourceKey.from_native(case.service, "repository", "11")
    case.keys["second_repository"] = second
    case.authority = document(
        tmp_path,
        "inventory-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()),
                sources=frozenset({case.source}),
                provider_registrations=frozenset({case.service}),
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    for kind, args in (
        ("provider", [case.service, "github", '{"name":"explicit-provider"}']),
        (
            "source",
            [case.source, case.service, '{"name":"explicit-source","owner":"owner"}'],
        ),
    ):
        payload = document(tmp_path, "registration.json", {"args": args})
        run(
            capsys,
            "context",
            kind,
            "--catalog",
            case.directory,
            "--authority",
            case.authority,
            "--input",
            payload,
        )
    return [
        list(case.keys[label].coordinates())
        for label in ("repository", "second_repository")
    ]


def request(case, **options):
    return {
        "operation": "discover",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
        "response_bytes": 8192,
        **options,
    }


def source(capsys, case):
    providers = run(capsys, "query", "providers", "--catalog", case.directory)
    assert providers[0]["configuration"] == {"name": "explicit-provider"}
    views = run(capsys, "query", "sources", "--catalog", case.directory)
    assert len(views) == 1
    assert views[0]["configuration"] == {"name": "explicit-source", "owner": "owner"}
    assert views[0]["repositories"] == []
    assert not (case.directory / "core.sqlite3").exists()
    assert not (case.directory / "access.sqlite3").exists()
    return views[0]


def coverage(capsys, case, tmp_path, original):
    scoped = CoverageScope.source_inventory(
        case.source, canonical(original["scope"]), "provider_repositories"
    )
    payload = document(tmp_path, "coverage-query.json", {"args": [scoped]})
    return run(
        capsys,
        "query",
        "context-coverage",
        "--catalog",
        case.directory,
        "--input",
        payload,
    )


@pytest.mark.parametrize(
    "mode",
    [
        "private",
        "empty",
        "missing-counts",
        "count-mismatch",
        "missing-private",
        "organization",
    ],
)
def test_normal_cli_provider_inventory_proves_only_actual_private_selected_scope(
    provider_case, tmp_path, capsys, monkeypatch, mode
):
    case, calls = provider_case, []
    expected = prepare(case, tmp_path, capsys)
    stamp = [1_000_000]

    def handle(http):
        stamp[0] += 1_000_000
        calls.append(http.url.path)
        if http.url.path == "/user":
            value = {
                "login": "viewer" if mode == "organization" else "owner",
                "public_repos": 0,
                "owned_private_repos": 3
                if mode == "count-mismatch"
                else 0
                if mode == "empty"
                else 2,
            }
            if mode == "missing-counts":
                value.pop("owned_private_repos")
            return _http_response(http, value)
        if http.url.path == "/users/owner":
            return _http_response(http, {"type": "Organization"})
        page = http.url.params.get("page")
        if mode == "empty":
            return _http_response(http, [])
        value = {
            "id": 11 if page else 10,
            "full_name": "owner/second" if page else "owner/repo",
            "private": True,
            "archived": True,
            "fork": True,
        }
        if mode == "missing-private":
            value.pop("private")
        response = _http_response(http, [value])
        if page is None:
            response.headers["link"] = (
                "<https://api.example.test" + http.url.path + '?page=2>; rel="next"'
            )
        return response

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request(case),
            clock_us=lambda: stamp[0],
        )
    assert result["status"] == (
        "complete" if mode in ("private", "empty") else "partial"
    )
    view = source(capsys, case)
    assert view["provider_repositories"] == ([] if mode == "empty" else expected)
    terminal = [inv for inv in view["inventories"] if inv["terminal"]]
    assert len(terminal) == 1
    terminal = terminal[0]
    assert terminal["provider_repositories"] == view["provider_repositories"]
    assert terminal["repositories"] == []
    assert terminal["observed_at_us"] == stamp[0]
    projected = coverage(capsys, case, tmp_path, terminal)
    if mode in ("private", "empty"):
        assert terminal["state"] == projected["state"] == "complete"
        assert projected["known_empty"] is (mode == "empty")
    else:
        assert terminal["state"] == projected["state"] == "unknown"
        assert not projected["known_empty"]
        assert result["failure_code"] == (
            "INVENTORY_COUNT_MISMATCH"
            if mode == "count-mismatch"
            else "INVENTORY_SCOPE_UNVERIFIED"
        )
    if mode != "empty":
        assert any(
            not inv["terminal"] and inv["state"] == "partial"
            for inv in view["inventories"]
        )
        repository = case.view(capsys, case.keys["repository"])
        for field in ("private", "archived", "fork"):
            if field == "private" and mode == "missing-private":
                assert field not in repository["fields"]
                continue
            assert {
                candidate["value"] for candidate in repository["fields"][field]
            } == {True}
            assert all(
                candidate["provenance"]["evidence"]["normalizer"]
                == {
                    "module": NORMALIZER_MODULE,
                    "version": NORMALIZER_VERSION,
                }
                for candidate in repository["fields"][field]
            )
    assert all(inv["scope"]["traversal_attempt_uuidv4"] for inv in view["inventories"])
    assert all(
        inv["provenance"]["evidence"]["terminal_report"]["read_origins"]
        for inv in view["inventories"]
    )


def test_selected_provider_inventory_reuses_descriptions_without_storing_transport_config(
    provider_case, tmp_path, capsys, monkeypatch
):
    case, calls = provider_case, []
    expected = prepare(case, tmp_path, capsys)[:1]

    def handle(http):
        calls.append(http.url.path)
        return _http_response(
            http,
            {"login": "viewer"}
            if http.url.path == "/user"
            else {"id": 10, "full_name": "owner/repo", "private": True},
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request(case, include_repositories=["repo"]),
        )
    assert result["status"] == "complete"
    assert calls == ["/user", "/repos/owner/repo"]
    view = source(capsys, case)
    assert view["provider_repositories"] == expected
    (terminal,) = view["inventories"]
    assert terminal["scope"]["selected_repositories"] == ["repo"]
    assert terminal["scope"]["query_kind"] == "selected-repositories"
    assert coverage(capsys, case, tmp_path, terminal)["state"] == "complete"
    assert "api.example.test" not in json.dumps(view)


@pytest.mark.parametrize(
    "failure",
    [
        "malformed-page",
        "malformed-member",
        "foreign-owner",
        "duplicate-id",
        "cycle",
        "network",
        "budget",
    ],
)
def test_inventory_interruption_keeps_exact_admitted_prefix_and_retries_original_request(
    provider_case, tmp_path, capsys, monkeypatch, failure
):
    case, broken, calls = provider_case, [True], []
    expected = prepare(case, tmp_path, capsys)

    def handle(http):
        calls.append(str(http.url))
        if http.url.path == "/user":
            return _http_response(
                http, {"login": "owner", "public_repos": 0, "owned_private_repos": 2}
            )
        if http.url.params.get("page") is None:
            response = _http_response(
                http, [{"id": 10, "full_name": "owner/repo", "private": True}]
            )
            response.headers["link"] = (
                '<https://api.example.test/user/repos?page=2>; rel="next"'
            )
            return response
        if broken[0]:
            if failure == "network":
                return httpx.Response(401, json={"message": "denied"})
            if failure == "malformed-page":
                return _http_response(http, {"not": "a repository list"})
            if failure == "malformed-member":
                return _http_response(http, [False])
            if failure == "foreign-owner":
                return _http_response(
                    http, [{"id": 11, "full_name": "outside/repo", "private": True}]
                )
            if failure == "duplicate-id":
                return _http_response(
                    http, [{"id": 10, "full_name": "owner/repo", "private": True}]
                )
            if failure == "cycle":
                response = _http_response(
                    http, [{"id": 11, "full_name": "owner/second", "private": True}]
                )
                response.headers["link"] = (
                    '<https://api.example.test/user/repos?page=2>; rel="next"'
                )
                return response
        return _http_response(
            http, [{"id": 11, "full_name": "owner/second", "private": True}]
        )

    document_request = request(case, max_pages=2 if failure == "budget" else 100)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, document_request
        )
        assert first["status"] == "partial"
        view = source(capsys, case)
        prefix = expected if failure == "cycle" else expected[:1]
        assert view["provider_repositories"] == prefix
        (terminal,) = [inv for inv in view["inventories"] if inv["terminal"]]
        assert (
            terminal["state"] == "partial"
            and terminal["provider_repositories"] == prefix
        )
        assert coverage(capsys, case, tmp_path, terminal)["state"] == "partial"
        if failure == "budget":
            # Exhausted durable page bounds do not reset by re-invocation.
            before = len(calls)
            document_request["new_request"] = False
            again, _ = _network_cli(
                case, tmp_path, capsys, monkeypatch, client, document_request
            )
            assert again["failure_code"] == "PAGE_LIMIT" and len(calls) == before
            return
        broken[0] = False
        document_request["new_request"] = False
        resumed, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, document_request
        )
    assert resumed["status"] == "complete"
    assert resumed["request_identity"] == first["request_identity"]
    view = source(capsys, case)
    assert view["provider_repositories"] == expected
    assert any(
        inv["state"] == "partial" and inv["terminal"] for inv in view["inventories"]
    )
    complete = [
        inv
        for inv in view["inventories"]
        if inv["state"] == "complete" and inv["terminal"]
    ]
    assert len(complete) == 1 and complete[0]["provider_repositories"] == expected
    assert coverage(capsys, case, tmp_path, complete[0])["state"] == "complete"


def test_typed_inventory_refuses_ungranted_provider_member_without_git_identity_mapping(
    provider_case, tmp_path, capsys
):
    case = provider_case
    prepare(case, tmp_path, capsys)
    foreign = ResourceKey.from_native(str(uuid4()), "repository", "10")
    value = SourceInventory(
        case.source,
        canonical({"coverage_kind": "provider_repositories"}),
        10,
        "complete",
        True,
        (),
        make_provenance("reported", "foreign-service"),
        (foreign,),
    )
    payload = document(
        tmp_path,
        "foreign-inventory.json",
        ProviderIntakeBatch(case.service, source_inventories=(value,)),
    )
    error = run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        case.directory,
        "--authority",
        case.authority,
        "--input",
        payload,
        expected=2,
    )
    assert error["code"] == "PERMISSION_DENIED"
    assert source(capsys, case)["inventories"] == []


@pytest.mark.parametrize(
    "selection",
    [["outside/repo"], ["repo", "REPO"], [], [".."]],
    ids=["foreign-owner", "duplicate", "empty", "dotdot"],
)
def test_invalid_explicit_inventory_selection_is_refused_before_http(
    provider_case, tmp_path, capsys, monkeypatch, selection
):
    case = provider_case
    prepare(case, tmp_path, capsys)
    calls = []

    def unexpected(http):
        calls.append(str(http.url))
        raise AssertionError("invalid selection reached HTTP")

    with httpx.Client(transport=httpx.MockTransport(unexpected)) as client:
        result, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request(case, include_repositories=selection),
        )
    assert (
        result["status"] == "partial" and result["failure_code"] == "INVALID_ARGUMENT"
    )
    assert result["http_attempts"] == result["network_bytes"] == 0
    assert calls == []
    assert source(capsys, case)["inventories"] == []


@pytest.mark.parametrize("refresh", ["unknown-empty", "unobserved-failure"])
def test_uncertain_refresh_preserves_prior_positive_source_members_and_original_coverage(
    provider_case, tmp_path, capsys, monkeypatch, refresh
):
    case, phase = provider_case, ["complete"]
    expected = prepare(case, tmp_path, capsys)[:1]

    def handle(http):
        if http.url.path == "/user":
            if phase[0] == "unobserved-failure":
                return httpx.Response(401, json={"message": "denied"})
            value = {"login": "owner"}
            if phase[0] == "complete":
                value.update(public_repos=0, owned_private_repos=1)
            return _http_response(http, value)
        return _http_response(
            http,
            [{"id": 10, "full_name": "owner/repo", "private": True}]
            if phase[0] == "complete"
            else [],
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        complete, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request(case)
        )
        assert complete["status"] == "complete"
        before = source(capsys, case)
        (original,) = before["inventories"]
        phase[0] = refresh
        uncertain, uncertain_request = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request(case)
        )
    assert uncertain["status"] == "partial"
    after = source(capsys, case)
    assert after["provider_repositories"] == expected
    assert original in after["inventories"]
    assert coverage(capsys, case, tmp_path, original)["state"] == "complete"
    if refresh == "unobserved-failure":
        assert after == before
        assert uncertain["failure_code"] == "CREDENTIALS_MISSING"
    else:
        assert uncertain["failure_code"] == "INVENTORY_SCOPE_UNVERIFIED"
        (unknown,) = [inv for inv in after["inventories"] if inv["state"] == "unknown"]
        assert unknown["provider_repositories"] == []
        projected = coverage(capsys, case, tmp_path, unknown)
        assert projected["state"] == "unknown" and not projected["known_empty"]
    phase[0] = "complete"
    uncertain_request["new_request"] = False
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        resumed, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, uncertain_request
        )
    assert resumed["status"] == "complete"
    assert resumed["request_identity"] == uncertain["request_identity"]
    assert source(capsys, case)["provider_repositories"] == expected
