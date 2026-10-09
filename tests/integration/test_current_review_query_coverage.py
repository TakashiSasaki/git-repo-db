"""Current review coverage stays independent of historical parser authority."""

import copy

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.exchange_service import ExchangeService
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime
from tests.support.github_runtime import sync


def current_query(state, repository, kind, *, search=False):
    options = {"repo": repository, "document_kind": kind}
    if search:
        options["literal"] = (
            "review-marker" if kind == "review" else "review-comment-marker"
        )
    else:
        options["provider_change_request_number"] = 41
    return QueryService(state).query("search pr" if search else "pr documents", options)


@pytest.mark.parametrize("kind", ["review", "review-comment"])
def test_imported_current_family_needs_no_trusted_parent_interpretation(
    github_runtime, tmp_path, kind
):
    sender, repo, _, _ = github_runtime
    sync(sender, repo)
    path = tmp_path / "synthetic-full-domain-exchange.json"
    ExchangeService(sender.path).export_repository(repo["repository_uuidv4"], path)
    receiver = tmp_path / "synthetic-untrusted-history-receiver"
    MaintenanceService(receiver).init("catalog-text-v1", 67_108_864, 0)
    result = ExchangeService(receiver).import_file(path)
    assert result.data["rejected_records"] == 0
    assert result.data["staged_records"] == 0
    with Store(receiver) as received:
        assert received.one("SELECT count(*) FROM change_request_observations")[0] > 0
        assert received.one("SELECT count(*) FROM document_observations")[0] > 0
        assert (
            received.one(
                "SELECT count(*) FROM local_parser_profile_verification_trust"
            )[0]
            == 0
        )
        assert (
            received.one("SELECT count(*) FROM current_change_request_observations")[0]
            == 0
        )
        assert (
            received.one("SELECT count(*) FROM current_document_observations")[0] == 0
        )
        assert (
            received.one(
                "SELECT coverage_state FROM current_coverage WHERE repository_uuidv4=? "
                "AND change_request_id IS NULL AND kind='pr-documents'",
                (repo["repository_uuidv4"],),
            )[0]
            == "complete"
        )
        assert received.all("PRAGMA foreign_key_check") == []
        assert received.one("PRAGMA integrity_check")[0] == "ok"
    for search in (False, True):
        original = current_query(
            sender.path, repo["repository_uuidv4"], kind, search=search
        )
        imported = current_query(
            receiver, repo["repository_uuidv4"], kind, search=search
        )
        assert original.status == imported.status == "complete"
        assert imported.coverage.complete_for_requested_scope
        assert imported.coverage.missing == []
        assert imported.data["items"]
        assert imported.data["items"] == [
            {**item, "last_checked_at_us": None} for item in original.data["items"]
        ]
        assert all(
            not any(key.startswith("change_request_parser") for key in item)
            for item in imported.data["items"]
        )
    null_filters = QueryService(receiver).query(
        "pr documents",
        {
            "repo": repo["repository_uuidv4"],
            "provider_change_request_number": 41,
            "document_kind": kind,
            "state": None,
            "draft": None,
            "resolved": None,
            "outdated": None,
        },
    )
    assert null_filters.status == "complete"
    assert null_filters.data["items"]
    for filter_option in ({"state": "open"}, {"resolved": "true"}, {"path": "file.py"}):
        filtered = QueryService(receiver).query(
            "pr documents",
            {
                "repo": repo["repository_uuidv4"],
                "provider_change_request_number": 41,
                "document_kind": kind,
                **filter_option,
            },
        )
        assert filtered.status == "partial"
        assert any(
            gap["reason"] == "change_request_observation_missing"
            for gap in filtered.coverage.missing
        )
    mixed = QueryService(receiver).query(
        "pr documents",
        {"repo": repo["repository_uuidv4"], "provider_change_request_number": 41},
    )
    assert mixed.status == "partial"
    assert any(
        gap["reason"] == "document_current_selection_unresolved"
        for gap in mixed.coverage.missing
    )


@pytest.mark.parametrize("gap", ["missing-body", "conflict"])
def test_current_family_preserves_body_and_conflict_coverage(github_runtime, gap):
    store, repo, _, _ = github_runtime
    sync(store, repo)
    resources = CurrentResources(store)
    row = store.one(
        "SELECT * FROM review_resources WHERE kind='review-comment' "
        "AND change_request_id=?",
        (repo["repository_uuidv4"] + ":41",),
    )
    candidate = resources.candidate_from_row("review_resources", row)
    candidate.pop("field_evidence")
    candidate.update(parser_module=__name__, parser_version="1")
    if gap == "missing-body":
        candidate.update(body=None, body_status="missing")
        base = store.revision()
        assert (
            resources.admit(
                candidate,
                source="live",
                base_revision=base,
                scope_context=candidate["acquisition_scope"],
            ).status
            == "accepted"
        )
    else:
        candidate["body"] = "a genuine unordered current alternative"
        assert resources.admit(candidate, source="import").status == "conflict"
    result = current_query(store.path, repo["repository_uuidv4"], "review-comment")
    assert result.status == "partial"
    assert not result.coverage.complete_for_requested_scope
    expected = (
        "document_body_missing"
        if gap == "missing-body"
        else "current_resource_unresolved"
    )
    assert any(gap["reason"] == expected for gap in result.coverage.missing)


def test_nonterminal_current_page_cannot_inherit_complete_family_coverage(
    github_runtime,
):
    store, repo, _, api = github_runtime
    sync(store, repo)
    timestamp = (
        store.one("SELECT max(observed_at_us) FROM current_collection_pages")[0] + 1
    )
    endpoint = api.url + "/repos/fixture/alpha/pulls/41/comments"
    config = copy.deepcopy(store.config["github"])
    config["max_attempts"] = 1

    def response(request):
        if request.url.params.get("page") == "2":
            return httpx.Response(
                503, json={"message": "synthetic missing terminal page"}
            )
        return httpx.Response(
            200, json=[], headers={"link": f'<{endpoint}?page=2>; rel="next"'}
        )

    token = CancellationToken()
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        transport = GitHubTransport(
            config, token, client=client, clock_us=lambda: timestamp
        )
        collector = GitHubCollector(store, token, transport=transport, config=config)
        job = JobService(store).create("sync", {"kind": "pr"})
        store.expected_attempt = 1
        with pytest.raises(CatalogError):
            collector.current_collection(
                repo,
                repo["repository_uuidv4"] + ":41",
                "review-comment",
                job,
                endpoint,
                current_parser.review_comment,
            )
    collection = store.one(
        "SELECT c.fetch_collection_id FROM fetch_collections c JOIN collection_progress p "
        "USING(fetch_collection_id) WHERE c.kind='review-comment' AND p.job_id=?",
        (job,),
    )[0]
    proof = CurrentCollectionProof(store.connection)
    assert len(proof.pages(collection)) == 1
    assert proof.evidence(collection) is None
    result = current_query(store.path, repo["repository_uuidv4"], "review-comment")
    assert result.status == "partial"
    assert any(
        gap["reason"] == "collection_incomplete"
        and gap.get("fetch_collection_id") == collection
        for gap in result.coverage.missing
    )


def test_current_family_keeps_repository_parent_set_completeness(github_runtime):
    store, repo, _, _ = github_runtime
    sync(store, repo)
    summary = store.one(
        "SELECT observed_at_us FROM current_coverage WHERE repository_uuidv4=? "
        "AND change_request_id IS NULL AND kind='pr-documents'",
        (repo["repository_uuidv4"],),
    )
    store.coverage(
        repo["repository_uuidv4"],
        "pr-documents",
        "partial",
        observed_at_us=summary[0] + 1,
    )
    result = current_query(store.path, repo["repository_uuidv4"], "review-comment")
    assert result.status == "partial"
    assert any(
        gap.get("scope_kind") == "pr-documents" for gap in result.coverage.missing
    )


@pytest.mark.parametrize("child_page", [False, True])
def test_current_rows_or_child_pages_cannot_prove_family_listing(
    github_runtime, child_page
):
    store, repo, _, api = github_runtime
    request = repo["repository_uuidv4"] + ":41"
    with store.transaction():
        store.execute(
            "INSERT INTO change_requests VALUES(?,?,?,'pull_request',41)",
            (request, repo["repository_uuidv4"], "binding"),
        )
        scope = {
            "repository_uuidv4": repo["repository_uuidv4"],
            "repository_binding_id": "binding",
            "service_instance_uuidv4": "00000000-0000-4000-8000-000000000101",
            "change_request_id": request,
            "endpoint": api.url + "/repos/fixture/alpha/pulls/41/comments",
        }
        candidate = {
            **{key: value for key, value in scope.items() if key != "endpoint"},
            "kind": "review-comment",
            "provider_change_request_document_id": "1",
            "body": "saved independently observed current comment",
            "observed_at_us": 1,
            "parsed_at_us": 2,
            "parser_module": __name__,
            "parser_version": "1",
            "acquisition_scope": scope,
        }
        assert (
            CurrentResources(store).admit(candidate, source="import").status
            == "accepted"
        )
    if child_page:
        collector = GitHubCollector(store, CancellationToken())
        job = JobService(store).create("sync", {"kind": "pr"})
        store.expected_attempt = 1
        try:
            with store.transaction():
                collection = collector.facts.begin(
                    repo,
                    request,
                    "thread-comments",
                    job,
                    scope["endpoint"],
                    {"thread": "known-thread"},
                )
                proof = CurrentCollectionProof(store.connection)
                proof.page(
                    collection["fetch_collection_id"],
                    0,
                    3,
                    None,
                    [],
                    parser_module=__name__,
                    parser_version="1",
                )
                collector.facts.finish(
                    collection,
                    evidence=proof.evidence(collection["fetch_collection_id"]),
                )
        finally:
            collector.http.close()
    result = current_query(store.path, repo["repository_uuidv4"], "review-comment")
    assert result.status == "partial"
    assert result.data["items"]
    assert any(
        gap["reason"] == "collection_incomplete"
        and gap.get("collection_kind") == "review-comment"
        for gap in result.coverage.missing
    )


def test_unknown_document_scope_stays_conservatively_incomplete(github_runtime):
    store, repo, _, _ = github_runtime
    sync(store, repo)
    store.coverage(
        repo["repository_uuidv4"],
        "future-document-kind",
        "partial",
        change_request_id=repo["repository_uuidv4"] + ":41",
        observed_at_us=1,
    )
    result = current_query(store.path, repo["repository_uuidv4"], "review-comment")
    assert result.status == "partial"
    assert any(
        gap["reason"] == "saved_scope_incomplete" for gap in result.coverage.missing
    )
