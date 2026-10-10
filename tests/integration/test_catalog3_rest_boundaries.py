"""Rejected REST inputs are discarded and retry the last safe live boundary."""

import json

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime
from tests.support.sqlite_contracts import assert_absent_tables


def _pr(store):
    with store.transaction():
        store.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,"
            "repository_binding_id,change_request_kind,provider_change_request_number) "
            "VALUES('00000000-0000-4000-8000-000000000301:41','00000000-0000-4000-8000-000000000301','binding','pull_request',41)"
        )
    return {
        "change_request_id": "00000000-0000-4000-8000-000000000301:41",
        "provider_change_request_number": 41,
    }


def _job(store):
    job = JobService(store).create("sync", {"kind": "pr"})
    store.expected_attempt = 1
    return job


def _rejected(store, kind, reason="API_SCHEMA"):
    row = store.one(
        "SELECT f.fetch_collection_id,p.state,p.cursor,p.reason "
        "FROM fetch_collections f "
        "JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id "
        "WHERE f.kind=?",
        (kind,),
    )
    assert row["state"] == "partial"
    assert row["reason"] == reason
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
    assert_absent_tables(store.connection, "fetch_occurrences")
    assert store.one("SELECT count(*) FROM unresolved_payloads")[0] == 0
    assert store.one("SELECT count(*) FROM payload_admission_staging")[0] == 0
    assert not store.one(
        "SELECT 1 FROM completion_markers WHERE fetch_collection_id=? AND asserted_state='complete'",
        (row["fetch_collection_id"],),
    )
    marker = store.one(
        "SELECT * FROM completion_markers WHERE fetch_collection_id=? AND asserted_state='partial'",
        (row["fetch_collection_id"],),
    )
    if marker is not None:
        assert json.loads(marker["evidence"]) == {"reason": row["reason"]}
    return row


@pytest.mark.parametrize(
    "bad_item",
    [
        None,
        "unexpected scalar",
        42,
        [],
        {"id": 344, "body": "bad author", "user": "writer"},
        {"id": 344, "body": "bad login", "user": {"login": []}},
        {"id": 344, "body": "bad author", "author": ["writer"]},
        {"id": 344, "body": ["not text"]},
        {"id": 344, "body": "bad URL", "html_url": {}},
        {"id": 344, "body": "bad target", "commit_id": 5},
        {"id": 344, "body": "bad target", "commit_id": "not-an-oid"},
        {"id": 344, "body": "bad author text", "user": {"login": "\ud800"}},
        {"id": 344, "body": "bad URL text", "html_url": "\udfff"},
        {"id": 344, "body": "bad metadata text", "unknown": {"nested": ["\ud800"]}},
        {"id": 344, "body": "bad metadata key", "unknown": {"\ud800": True}},
        {"id": 344, "body": "bad target", "commit_id": "aa" * 19 + "  "},
    ],
)
def test_current_rest_item_rejection_preserves_domain_prefix_and_safe_resume(
    github_runtime, bad_item
):
    store, repo, _, api = github_runtime
    pr = _pr(store)
    job = _job(store)
    path = "/repos/fixture/alpha/pulls/41/reviews"
    first_url, second_url = api.url + path, api.url + path + "?page=2"
    third_url = api.url + path + "?page=3"
    prefix = {"id": 341, "body": "committed prefix"}
    pending = {"id": 342, "body": "uncommitted prefix of rejected page"}
    corrected = {"id": 343, "body": "corrected response 認証 🦉", "user": None}
    rejected = [pending, bad_item]
    blocked = True
    requested = []

    def route(method, requested_path, params, body):
        assert method == "GET" and requested_path == path
        page = params.get("page", ["1"])[0]
        requested.append(page)
        if page == "1":
            return [prefix], {"Link": f'<{second_url}>; rel="next"'}
        assert page == "2"
        if blocked:
            # This advertised later cursor must never become the retry target.
            return rejected, {"Link": f'<{third_url}>; rel="next"'}
        return [pending, corrected], {}

    api.route = route
    collector = GitHubCollector(store, CancellationToken())
    collector.facts.principal = "fixture"

    def collect():
        return collector.current_collection(
            repo,
            pr["change_request_id"],
            "review",
            job,
            first_url,
            current_parser.review,
        )

    try:
        with pytest.raises(CatalogError) as raised:
            collect()
        assert raised.value.code == "API_SCHEMA"
        row = store.one(
            "SELECT f.fetch_collection_id,p.state,p.reason,p.cursor FROM fetch_collections f JOIN collection_progress p USING(fetch_collection_id) WHERE f.kind='review'"
        )
        assert row["state"] == "partial" and row["reason"] == "API_SCHEMA"
        assert row["cursor"] == second_url
        assert [
            r[0]
            for r in store.all(
                "SELECT provider_change_request_document_id FROM review_resources"
            )
        ] == ["341"]
        assert_absent_tables(store.connection, "document_observations")
        assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
        JobService(store).update(job, "waiting", "API_SCHEMA")
        JobService(store).resume(job)
        store.expected_attempt = 2
        blocked = False
        collection_id, _ = collect()
        assert collection_id == row["fetch_collection_id"]
        assert requested == ["1", "2", "2"]
        assert store.one("SELECT count(*) FROM review_resources")[0] == 3
        assert_absent_tables(store.connection, "document_observations")
        assert (
            store.one(
                "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
                (collection_id,),
            )[0]
            == "complete"
        )
        assert (
            store.one(
                "SELECT count(*) FROM current_collection_pages WHERE fetch_collection_id=?",
                (collection_id,),
            )[0]
            == 2
        )
        assert not store.all("PRAGMA foreign_key_check")
    finally:
        collector.http.close()


@pytest.mark.parametrize(
    "invalid",
    [
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
    ],
)
@pytest.mark.parametrize("boundary", ["pr-list", "pr-detail", "pr-code-check"])
def test_malformed_pr_shapes_discard_originals_and_retry(
    github_runtime, invalid, boundary
):
    store, repo, _, api = github_runtime
    pr = _pr(store)
    job = _job(store)
    corrected = api.prs[41]
    malformed = None if invalid is None else {**corrected, **invalid}
    rejected = [malformed] if boundary == "pr-list" else malformed
    path = "/repos/fixture/alpha/pulls/41"
    url = api.url + path
    blocked = True
    requests = 0

    def route(method, requested, params, body):
        nonlocal requests
        assert method == "GET" and requested == path
        requests += 1
        if blocked:
            return rejected, {}
        return ([corrected] if boundary == "pr-list" else corrected), {}

    api.route = route
    collector = GitHubCollector(store, CancellationToken())
    collector.facts.principal = "fixture"

    def acquire():
        if boundary == "pr-detail":
            return collector.detail(repo, pr, job, url)
        if boundary == "pr-code-check":
            return collector.code_check(repo, pr, job, url, 0)
        return collector.collection(
            repo,
            None,
            boundary,
            job,
            url,
            lambda value, collection, occurrence, position, timestamp, listing: (
                collector.ensure_pr(
                    repo, value, collection, occurrence, position, timestamp
                )[1]
            ),
        )

    try:
        with pytest.raises(CatalogError) as raised:
            acquire()
        assert raised.value.code == "API_SCHEMA"
        row = _rejected(store, boundary)
        assert row["cursor"] in (None, url)
        assert store.one("SELECT count(*) FROM change_request_state")[0] == 0
        assert store.one("SELECT count(*) FROM document_state")[0] == 0
        blocked = False
        acquire()
        assert requests == 2
        assert store.one("SELECT count(*) FROM change_request_state")[0] == 1
        assert (
            store.one(
                "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
                (row["fetch_collection_id"],),
            )[0]
            == "complete"
        )
        assert not store.all("PRAGMA foreign_key_check")
    finally:
        collector.http.close()


def test_programming_errors_are_not_misclassified_as_provider_data(github_runtime):
    store, repo, _, api = github_runtime
    job = _job(store)
    api.route = lambda *args: ([{}], {})
    collector = GitHubCollector(store, CancellationToken())

    def broken_normalizer(*args):
        raise AttributeError("synthetic implementation defect")

    try:
        with pytest.raises(AttributeError, match="implementation defect"):
            collector.collection(
                repo, None, "timeline", job, api.url + "/synthetic", broken_normalizer
            )
        assert store.one("SELECT count(*) FROM unresolved_payloads")[0] == 0
    finally:
        collector.http.close()


@pytest.mark.parametrize("boundary", ["pr-detail", "pr-code-check"])
def test_invalid_json_detail_discards_bytes_and_reacquires(
    github_runtime, monkeypatch, boundary
):
    store, repo, _, api = github_runtime
    pr = _pr(store)
    job = _job(store)
    url = api.url + "/repos/fixture/alpha/pulls/41"
    rejected = b'{"number":41,"title":'
    collector = GitHubCollector(store, CancellationToken())
    responses = iter(
        [
            httpx.Response(200, content=rejected),
            httpx.Response(200, json=api.prs[41]),
        ]
    )
    monkeypatch.setattr(collector, "request_get", lambda *a, **kw: next(responses))

    def acquire():
        if boundary == "pr-detail":
            return collector.detail(repo, pr, job, url)
        return collector.code_check(repo, pr, job, url, 0)

    try:
        with pytest.raises(CatalogError) as raised:
            acquire()
        assert raised.value.code == "API_SCHEMA"
        row = _rejected(store, boundary)
        assert row["cursor"] in (None, url)
        acquire()
        assert (
            store.one(
                "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
                (row["fetch_collection_id"],),
            )[0]
            == "complete"
        )
    finally:
        collector.http.close()


def test_detail_304_without_saved_normalized_state_fetches_live_response(
    github_runtime, monkeypatch
):
    store, repo, _, api = github_runtime
    pr = _pr(store)
    collector = GitHubCollector(store, CancellationToken())
    collector.facts.principal = "fixture"
    attempts = []

    def request(url, *args, **kwargs):
        assert not store.connection.in_transaction
        attempts.append(kwargs)
        return (
            httpx.Response(304)
            if len(attempts) % 2
            else httpx.Response(
                200,
                json=api.prs[41],
                extensions={"catalog_observed_at_us": len(attempts)},
            )
        )

    monkeypatch.setattr(collector, "request_get", request)
    try:
        for stage in ("A", "A", "B", "B"):
            api.stage = stage
            collector.detail(
                repo, pr, _job(store), api.url + "/repos/fixture/alpha/pulls/41"
            )
        assert len(attempts) == 8
        assert store.one("SELECT count(*) FROM change_request_state")[0] == 1
        assert store.one("SELECT count(*) FROM current_collection_pages")[0] == 4
        assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
        assert not store.all("PRAGMA foreign_key_check")
    finally:
        collector.http.close()


def test_incremental_parent_number_is_checked_before_sqlite_lookup(github_runtime):
    store, repo, _, api = github_runtime
    _pr(store)
    job = _job(store)
    endpoint = api.url + "/repos/fixture/alpha/issues/comments"
    value = {
        "id": 241,
        "body": "parent number boundary",
        "issue_url": api.url + f"/repos/fixture/alpha/issues/{1 << 63}",
    }
    api.route = lambda *args: ([value], {})
    collector = GitHubCollector(store, CancellationToken())
    collector.facts.principal = "fixture"
    try:
        with pytest.raises(CatalogError) as raised:
            collector.incremental_comments(
                repo, job, "issue-comment", endpoint, "issue_url"
            )
        assert raised.value.code == "API_SCHEMA"
        row = _rejected(store, "issue-comment-incremental")
        assert (
            row["cursor"]
            == store.one(
                "SELECT s.endpoint FROM resume_scopes s JOIN fetch_collections f USING(resume_scope_id) WHERE f.fetch_collection_id=?",
                (row["fetch_collection_id"],),
            )[0]
        )
        assert store.one("SELECT count(*) FROM incremental_scans")[0] == 0
        value["issue_url"] = api.url + "/repos/fixture/alpha/issues/41"
        collector.incremental_comments(
            repo, job, "issue-comment", endpoint, "issue_url"
        )
        assert store.one("SELECT count(*) FROM document_state")[0] == 1
        assert (
            store.one(
                "SELECT count(*) FROM completion_markers WHERE asserted_state='complete'"
            )[0]
            == 1
        )
    finally:
        collector.http.close()


@pytest.mark.parametrize("boundary", ["pr-detail", "pr-code-check"])
def test_single_pr_response_cannot_publish_a_different_pr(github_runtime, boundary):
    store, repo, _, api = github_runtime
    pr = _pr(store)
    job = _job(store)
    requested = api.prs[41]
    other = api.prs[42]
    response = other
    api.route = lambda *args: (response, {})
    collector = GitHubCollector(store, CancellationToken())
    url = api.url + "/repos/fixture/alpha/pulls/41"

    def acquire():
        if boundary == "pr-detail":
            return collector.detail(repo, pr, job, url)
        return collector.code_check(repo, pr, job, url, 0)

    try:
        with pytest.raises(CatalogError) as raised:
            acquire()
        assert raised.value.code == "SCOPE_MISMATCH"
        assert _rejected(store, boundary, "SCOPE_MISMATCH")["cursor"] in (None, url)
        assert store.one("SELECT count(*) FROM change_requests")[0] == 1
        assert store.one("SELECT count(*) FROM change_request_state")[0] == 0
        assert store.one("SELECT count(*) FROM document_state")[0] == 0
        response = requested
        acquire()
        assert store.one("SELECT count(*) FROM change_requests")[0] == 1
        assert store.one("SELECT count(*) FROM change_request_state")[0] == 1
        assert not store.all("PRAGMA foreign_key_check")
    finally:
        collector.http.close()
