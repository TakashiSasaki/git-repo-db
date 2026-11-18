"""A partial actual GraphQL PR preserves its reported comparison targets."""

from contextlib import closing

import httpx

from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from tests.e2e.test_separated_cli_github_git_roles import setup
from tests.e2e.test_separated_cli_pr_assessment import query
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def test_normal_cli_partial_graphql_merge_target_is_retained_without_coobserved_comparison(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    native, objects, request, rest, calls = setup(case, tmp_path, capsys)
    # An actual extra native commit is independent of the initial head/base.
    from repo_catalog.cli.separated_io import decode, read_document
    from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
    from tests.e2e.test_separated_cli import document
    from tests.integration.p5.conftest import write_git_object

    grants = decode(read_document(case.authority)["grants"])
    merge = write_git_object(
        native,
        "sha1",
        "commit",
        (
            f"tree {objects['tree'].object_oid}\nparent {objects['commit2'].object_oid}\n"
            "author Test <test@example.test> 1700000200 +0000\n"
            "committer Test <test@example.test> 1700000200 +0000\n\npartial-graphql-merge\n"
        ).encode(),
    )
    case.authority = document(
        tmp_path,
        "merge-authority.json",
        {
            "grants": DependencySet(
                resources=grants.resources,
                sources=grants.sources,
                provider_registrations=grants.provider_registrations,
                object_oids=grants.object_oids | {merge},
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    request["sections"].append("review_threads")

    def handle(http):
        if http.method == "POST":
            import json

            assert "mergeCommit" in json.loads(http.content)["query"]
            return _http_response(
                http,
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "id": "PR_ACTUAL_20",
                                "number": 1,
                                "mergeCommit": {"oid": merge.object_oid},
                                "updatedAt": "2026-02-01T00:00:00Z",
                                "reviewThreads": {
                                    "nodes": [],
                                    "pageInfo": {
                                        "hasNextPage": False,
                                        "endCursor": None,
                                    },
                                },
                            }
                        }
                    },
                    "errors": [
                        {
                            "message": "partial field",
                            "path": ["repository", "pullRequest", "reviewThreads"],
                        }
                    ],
                },
            )
        return rest(http)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert result["status"] == "partial"
    # Native closure must include the genuinely returned merge target, even
    # though its root supplied no head/base with which to qualify comparison.
    with closing(
        GitRepositoryStore(case.directory / "repository.sqlite3")
    ) as repository_store:
        assert repository_store.read_metadata(merge) is not None
    code = query(capsys, case, "pr-code")
    assert code["state"] != "complete"
    assert not code["coverage"]["complete_for_requested_scope"]
    documents = query(capsys, case, "pr-documents", "--kind", "review_threads")
    assert documents["state"] == "partial"
    parent = case.view(capsys, case.keys["pull"])
    candidates = parent["fields"]["merge_object_oid"]
    assert any(c["value"] == merge.object_oid for c in candidates)
    producer = next(c for c in candidates if c["value"] == merge.object_oid)
    assert producer["provenance"]["evidence"]["resource_path"].endswith(
        "/review_threads/comparison"
    )
