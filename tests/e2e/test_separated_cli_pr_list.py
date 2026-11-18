"""Ordinary repository PR query preflights the actual parent universe before rows."""

from uuid import uuid4

import httpx

from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.provider_acquisition import (
    ProviderPullRequestIntake,
    ProviderRepositoryIntake,
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


def query(capsys, case, *options, expected=0):
    return run(
        capsys,
        "query",
        "pr-list",
        "--catalog",
        case.directory,
        "--service-instance",
        case.service,
        "--provider-resource-id",
        case.keys["repository"].provider_resource_id,
        "--kind",
        "reviews",
        *options,
        expected=expected,
    )


def test_normal_cli_pr_list_cannot_infer_repository_roster_from_standalone_parent_facts(
    provider_case, tmp_path, capsys
):
    case = provider_case
    original = make_provenance("explicit-domain-input", "standalone-subjects")
    case.admit(
        tmp_path,
        capsys,
        provider_repositories=(
            ProviderRepositoryIntake(
                {"id": 10, "full_name": "owner/repo"}, 10, original
            ),
        ),
        pull_requests=(ProviderPullRequestIntake({"id": 20}, 10, original),),
    )
    result = query(capsys, case, "--limit", 1)
    assert result["state"] == "unknown" and result["total_count"] == 0
    assert not result["coverage"]["complete_for_requested_scope"]
    assert result["parent_listing"]["reason"] == "matching_listing_unavailable"
    selected = query(
        capsys, case, "--parent-id", case.keys["pull"].provider_resource_id
    )
    assert not selected["coverage"]["complete_for_requested_scope"]
    assert selected["items"] == []
    assert not (case.directory / "repository.sqlite3").exists()
    assert not (case.directory / "operational.sqlite3").exists()


def test_normal_cli_pr_list_preflights_hidden_parent_gaps_and_positive_selection(
    provider_case, tmp_path, capsys, monkeypatch
):
    case, broken = provider_case, [True]
    extra = {
        ResourceKey.document(case.keys["other_pull"], "review", "review_summary", "10"),
        ResourceKey.document(case.keys["other_pull"], "document", "pr_title", "21"),
    }
    case.authority = document(
        tmp_path,
        "parent-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()) | extra,
                sources=frozenset({case.source}),
                provider_registrations=frozenset({case.service}),
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )

    def handle(http):
        path = http.url.path
        if path == "/repos/owner/repo":
            value = {"id": 10, "full_name": "owner/repo"}
        elif path.endswith("/pulls"):
            value = [
                {
                    "id": ident,
                    "number": ident - 19,
                    "title": title,
                    "state": state,
                    "draft": draft,
                    "user": {"login": author},
                }
                for ident, title, state, draft, author in (
                    (20, "first", "open", False, "alice"),
                    (21, "second", "closed", True, "bob"),
                )
            ]
        elif path.endswith("/reviews"):
            value = (
                {"not": "a review list"}
                if path.endswith("/2/reviews") and broken[0]
                else [{"id": 10, "body": "selected-marker", "state": "APPROVED"}]
            )
        else:
            value = {"id": 20 if path.endswith("/1") else 21}
        return _http_response(http, value)

    request = {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["reviews"],
        "response_bytes": 8192,
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        acquired, request = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
        assert acquired["status"] == "partial"
        first = query(capsys, case, "--limit", 1)
        assert first["state"] == "partial" and first["total_count"] == 2
        assert first["has_more"] and first["items"][0]["state"] == "complete"
        assert first["items"][0]["resource"] == list(case.keys["pull"].coordinates())
        assert first["items"][0]["document_count"] == 1
        assert any(
            gap.get("parent") == list(case.keys["other_pull"].coordinates())
            for gap in first["coverage"]["missing"]
        )
        second = query(capsys, case, "--limit", 1, "--cursor", first["next_cursor"])
        assert (
            second["coverage"] == first["coverage"]
            and second["snapshot_token"] == first["snapshot_token"]
        )
        assert second["items"][0]["resource"] == list(
            case.keys["other_pull"].coordinates()
        )
        filtered = query(
            capsys,
            case,
            "--state",
            "open",
            "--no-draft",
            "--author",
            "alice",
            "--text-literal",
            "selected-marker",
        )
        assert filtered["total_count"] == 1 and filtered["state"] == "partial"
        assert filtered["coverage"] == first["coverage"]
        selected = query(
            capsys, case, "--parent-id", case.keys["pull"].provider_resource_id
        )
        assert selected["state"] == "complete" and selected["total_count"] == 1
        absent = query(capsys, case, "--parent-id", '"999"')
        assert (
            not absent["coverage"]["complete_for_requested_scope"]
            and absent["total_count"] == 0
        )
        error = query(
            capsys,
            case,
            "--limit",
            1,
            "--cursor",
            first["next_cursor"],
            "--state",
            "open",
            expected=2,
        )
        assert error["code"] == "INVALID_CURSOR"
        assert (
            query(capsys, case, "--max-work", 1, expected=2)["code"] == "QUERY_BUDGET"
        )
        broken[0] = False
        request["new_request"] = False
        refreshed, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
    assert refreshed["status"] == "complete"
    final = query(capsys, case, "--limit", 1)
    assert final["state"] == "complete" and final["coverage"]["missing"] == []
    assert final["total_count"] == 2 and final["has_more"]
    from tests.e2e.test_separated_cli_pr_assessment import query as documents

    approved = documents(
        capsys,
        case,
        "pr-documents",
        "--kind",
        "reviews",
        "--document-state",
        "APPROVED",
    )
    assert approved["state"] == "complete" and approved["total_count"] == 1
    mismatch = documents(
        capsys,
        case,
        "pr-documents",
        "--kind",
        "reviews",
        "--document-state",
        "DISMISSED",
    )
    assert mismatch["state"] == "complete" and mismatch["total_count"] == 0
    missing_author = document(
        tmp_path, "document-filters.json", {"state": "APPROVED", "author": None}
    )
    unknown = documents(
        capsys,
        case,
        "pr-documents",
        "--kind",
        "reviews",
        "--document-filters",
        missing_author,
    )
    assert unknown["state"] == "partial" and unknown["total_count"] == 0
    assert not unknown["coverage"]["complete_for_requested_scope"]
    assert not (case.directory / "repository.sqlite3").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()
