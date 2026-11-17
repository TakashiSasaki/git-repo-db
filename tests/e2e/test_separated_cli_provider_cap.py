"""An exhausted capped code endpoint keeps its prefix and independent file facts."""

from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.github.production_intake import (
    normalize_pr_commit,
    normalize_pr_file,
)
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.provider_acquisition import make_provenance
from tests.e2e.test_separated_cli import document
from tests.e2e.test_separated_cli_pr_assessment import query
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


@pytest.mark.parametrize(
    "expected_count,code", [(251, "API_CAP"), (2, "API_COUNT_MISMATCH")]
)
def test_cli_capped_commit_prefix_is_partial_without_discarding_independent_files(
    provider_case, tmp_path, capsys, monkeypatch, expected_count, code
):
    case, head, base, calls = provider_case, "1" * 40, "2" * 40, []
    commit = {"sha": head}
    files_payload = [
        {"filename": f"src/item-{index}.py", "status": "modified"}
        for index in range(101 if code == "API_CAP" else 1)
    ]
    original = make_provenance("fixture", "finite-permission-shape")
    resources = {
        normalize_pr_commit(case.service, "20", commit, 1, original).primary_resource,
        *(
            normalize_pr_file(case.service, "20", file, 1, original).primary_resource
            for file in files_payload
        ),
    }
    case.authority = document(
        tmp_path,
        "code-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()) | resources,
                sources=frozenset({case.source}),
                provider_registrations=frozenset({case.service}),
                object_oids=frozenset({OID("sha1", head), OID("sha1", base)}),
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )

    def handle(http):
        calls.append(http.url.path)
        if http.url.path.endswith("/pulls"):
            value = [{"id": 20, "number": 1}]
        elif http.url.path.endswith("/pulls/1"):
            value = {
                "id": 20,
                "head": {"sha": head},
                "base": {"sha": base},
                "commits": expected_count,
                "changed_files": len(files_payload),
            }
        elif http.url.path.endswith("/commits"):
            value = [commit]
        elif http.url.path.endswith("/files"):
            page = int(http.url.params.get("page", "1"))
            value = files_payload[(page - 1) * 100 : page * 100]
            if page == 1 and len(files_payload) > 100:
                return httpx.Response(
                    200,
                    request=http,
                    json=value,
                    headers={
                        "link": '<https://api.example.test/repos/owner/repo/pulls/1/files?page=2>; rel="next"'
                    },
                )
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
        "sections": ["pr_commits", "pr_files"],
        "response_bytes": 8192,
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert report["status"] == "partial" and report["failure_code"] == code
    assert calls.count("/repos/owner/repo/pulls/1/commits") == 1
    assert calls.count("/repos/owner/repo/pulls/1/files") == (
        2 if len(files_payload) > 100 else 1
    )
    collections = case.view(capsys, case.keys["pull"])["collections"]
    commits = [item for item in collections if item["collection_kind"] == "pr_commits"]
    files = [item for item in collections if item["collection_kind"] == "pr_files"]
    assert len(commits) == 1
    assert len(files) == (2 if len(files_payload) > 100 else 1)
    assert commits[0]["state"] == "partial" and len(commits[0]["members"]) == 1
    assert commits[0]["scope"]["expected_count"] == expected_count
    completed = [row for row in files if row["state"] == "complete"]
    assert len(completed) == 1 and len(completed[0]["members"]) == len(files_payload)
    if len(files_payload) > 100:
        prefix = [row for row in files if row["state"] == "partial"]
        assert len(prefix) == 1 and len(prefix[0]["members"]) == 100
    result = query(capsys, case, "pr-code", "--no-require-git", "--limit", 20)
    assert result["total_count"] == len(files_payload) + 1
    if len(files_payload) > 100:
        assert len(result["items"]) == 20
    assert result["has_more"] == (len(files_payload) > 20)
    assert result["state"] == "partial"
    assert not result["coverage"]["complete_for_requested_scope"]
    assert not (case.directory / "core.sqlite3").exists()
