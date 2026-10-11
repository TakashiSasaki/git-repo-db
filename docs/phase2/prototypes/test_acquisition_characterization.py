"""Disposable characterization of Schema 18 acquisition boundaries.

These probes describe current behavior and expose replacement requirements. They
are proposal evidence, not production lifecycle or conditional-cache policy.
Run from the checkout with:
  uv run --no-sync python -m pytest docs/phase2/prototypes/test_acquisition_characterization.py
"""

from __future__ import annotations

import copy
import json

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.conftest import offline_test_environment as offline_test_environment
from tests.support.github_runtime import github_runtime as github_runtime


def seed_pr(store, repo):
    identifier = repo["repository_uuidv4"] + ":41"
    with store.transaction():
        store.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,"
            "repository_binding_id,change_request_kind,provider_change_request_number) "
            "VALUES(?,?,'binding','pull_request',41)",
            (identifier, repo["repository_uuidv4"]),
        )
    return {"change_request_id": identifier, "provider_change_request_number": 41}


def new_job(store):
    identifier = JobService(store).create("sync", {"kind": "pr"})
    store.expected_attempt = 1
    return identifier


def collector(store):
    result = GitHubCollector(store, CancellationToken())
    result.facts.principal = "fixture"
    return result


def test_current_receipts_restart_committed_prefix_without_original(
    github_runtime, monkeypatch
):
    store, repo, _, api = github_runtime
    pr = seed_pr(store, repo)
    job = new_job(store)
    endpoint = api.url + "/repos/fixture/alpha/pulls/41/reviews"
    first, second = 100, 300
    requested = []
    current = collector(store)

    def route(method, path, params, body):
        assert path == "/repos/fixture/alpha/pulls/41/reviews"
        page = params.get("page", ["1"])[0]
        requested.append(page)
        current.http.clock_us = lambda: second if page == "2" else first
        return [{"id": int(page), "state": "APPROVED", "body": "exact body"}], (
            {"Link": f'<{endpoint}?page=2>; rel="next"'} if page == "1" else {}
        )

    api.route = route

    def interrupt(phase):
        if phase == "after_api_page_commit":
            raise CatalogError("CANCELLED", "Committed prefix")

    monkeypatch.setattr("repo_catalog.adapters.git.runner.hook", interrupt)
    try:
        with pytest.raises(CatalogError, match="Committed prefix"):
            current.current_collection(
                repo,
                pr["change_request_id"],
                "review",
                job,
                endpoint,
                current_parser.review,
            )
        assert store.one("SELECT count(*) FROM current_collection_pages")[0] == 1
        assert store.one("SELECT count(*) FROM review_resources")[0] == 1
        assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
        JobService(store).update(job, "interrupted")
        JobService(store).resume(job)
        store.expected_attempt = 2
        monkeypatch.setattr("repo_catalog.adapters.git.runner.hook", lambda phase: None)
        current.current_collection(
            repo,
            pr["change_request_id"],
            "review",
            job,
            endpoint,
            current_parser.review,
        )
        assert requested == ["1", "2"]
        assert [
            tuple(row)
            for row in store.all(
                "SELECT ordinal,observed_at_us FROM current_collection_pages ORDER BY ordinal"
            )
        ] == [(0, first), (1, second)]
        assert tuple(
            store.one(
                "SELECT coverage_state,observed_at_us FROM current_coverage WHERE kind='review'"
            )
        ) == ("complete", second)
        assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
        assert store.all("PRAGMA foreign_key_check") == []
    finally:
        current.http.close()


def test_saved_root_is_reused_with_old_observation_for_child_restart(
    github_runtime, monkeypatch
):
    store, repo, _, api = github_runtime
    pr = seed_pr(store, repo)
    job = new_job(store)
    api.reply_count = 101
    stamp = [100]
    monkeypatch.setattr(
        "repo_catalog.adapters.github.persistence.now_us", lambda: stamp[0]
    )
    current = collector(store)
    current.http.clock_us = lambda: stamp[0]
    request = current.http.request

    def stop_child(method, url, **kwargs):
        if kwargs.get("json", {}).get("variables", {}).get("thread"):
            raise CatalogError("CANCELLED", "Root committed before child request")
        return request(method, url, **kwargs)

    current.http.request = stop_child
    try:
        with pytest.raises(CatalogError, match="Root committed"):
            current.threads(repo, pr, job)
        root = store.one("SELECT * FROM fetch_occurrences")
        assert root["observed_at_us"] == 100
        pending = json.loads(
            store.one(
                "SELECT p.cursor FROM collection_progress p JOIN fetch_collections f "
                "USING(fetch_collection_id) WHERE f.kind='threads'"
            )[0]
        )
        assert pending == {"cursor": None, "occurrence": root["fetch_occurrence_id"]}
        assert store.one("SELECT count(*) FROM review_resources")[0] == 100
        JobService(store).update(job, "interrupted")
        JobService(store).resume(job)
    finally:
        current.http.close()

    root_requests_before = sum(method == "POST" for method, _, _ in api.requests)
    stamp[0] = 300
    with Store(store.path) as restarted:
        restarted.expected_attempt = 2
        later = collector(restarted)
        later.http.clock_us = lambda: stamp[0]
        statements = []
        restarted.connection.set_trace_callback(statements.append)
        try:
            later.threads(repo, pr, job)
            assert (
                sum(method == "POST" for method, _, _ in api.requests)
                == root_requests_before + 1
            )
            assert restarted.one("SELECT count(*) FROM fetch_occurrences")[0] == 1
            assert (
                restarted.one("SELECT observed_at_us FROM fetch_occurrences")[0] == 100
            )
            assert restarted.one("SELECT count(*) FROM review_resources")[0] == 101
            assert any(
                "SELECT o.*,b.body FROM fetch_occurrences" in sql for sql in statements
            )
            assert tuple(
                restarted.one(
                    "SELECT coverage_state,observed_at_us FROM current_coverage WHERE kind='threads'"
                )
            ) == ("complete", 300)
            assert restarted.all("PRAGMA foreign_key_check") == []
        finally:
            later.http.close()
            restarted.connection.set_trace_callback(None)


@pytest.mark.parametrize("presence", ["omitted", "null"])
@pytest.mark.parametrize(
    "role,field",
    [("merge", "mergeCommit"), ("test-merge", "potentialMergeCommit")],
    ids=["merge", "test-merge"],
)
def test_saved_root_role_presence_survives_child_restart(
    github_runtime, monkeypatch, role, field, presence
):
    """A later child response cannot turn an omitted root target into null."""
    store, repo, _, api = github_runtime
    pr = seed_pr(store, repo)
    job = new_job(store)
    api.reply_count = 101
    stamp, requested = [100], []
    monkeypatch.setattr(
        "repo_catalog.adapters.github.persistence.now_us", lambda: stamp[0]
    )
    original_route = api.route

    def route(method, path, params, body):
        value, headers = original_route(method, path, params, body)
        if method == "POST":
            variables = body["variables"]
            location = "child" if "thread" in variables else "root"
            requested.append((location, variables.copy()))
            if location == "root":
                root = value["data"]["repository"]["pullRequest"]
                if presence == "omitted":
                    del root[field]
                else:
                    root[field] = None
        return value, headers

    api.route = route
    expected_roles = {"merge": None, "test-merge": None}
    if presence == "omitted":
        del expected_roles[role]
    expected_input = (expected_roles, presence == "null", 100)
    current = collector(store)
    current.http.clock_us = lambda: stamp[0]
    original_request = current.http.request

    def stop_child(method, url, **kwargs):
        if kwargs.get("json", {}).get("variables", {}).get("thread"):
            raise CatalogError(
                "CANCELLED", "Root target committed before child request"
            )
        return original_request(method, url, **kwargs)

    current.http.request = stop_child
    try:
        with pytest.raises(CatalogError, match="Root target committed"):
            current.threads(repo, pr, job)
        root = store.one("SELECT * FROM fetch_occurrences")
        assert root["observed_at_us"] == 100
        assert (
            current.saved_thread_code_input(pr["change_request_id"]) == expected_input
        )
        assert [location for location, _ in requested] == ["root"]
        assert store.one("SELECT count(*) FROM review_resources")[0] == 100
        JobService(store).update(job, "interrupted")
    finally:
        current.http.close()

    store.close()
    stamp[0] = 300
    with Store(store.path) as restarted:
        JobService(restarted).resume(job)
        restarted.expected_attempt = 2
        later = collector(restarted)
        later.http.clock_us = lambda: stamp[0]
        try:
            later.threads(repo, pr, job)
            assert [location for location, _ in requested] == ["root", "child"]
            assert requested[-1][1]["thread"] == "THREAD41-0"
            assert requested[-1][1]["commentCursor"] == "100"
            assert (
                later.saved_thread_code_input(pr["change_request_id"]) == expected_input
            )
            assert tuple(
                restarted.one(
                    "SELECT fetch_occurrence_id,observed_at_us FROM fetch_occurrences"
                )
            ) == (root["fetch_occurrence_id"], 100)
            assert restarted.one("SELECT count(*) FROM fetch_occurrences")[0] == 1
            assert restarted.one("SELECT count(*) FROM review_resources")[0] == 101
            assert [
                row[0]
                for row in restarted.all(
                    "SELECT p.observed_at_us FROM current_collection_pages p "
                    "JOIN fetch_collections f USING(fetch_collection_id) "
                    "WHERE f.kind='thread-comments' ORDER BY p.ordinal"
                )
            ] == [300]
            assert tuple(
                restarted.one(
                    "SELECT coverage_state,observed_at_us FROM current_coverage WHERE kind='threads'"
                )
            ) == ("complete", 300)
            assert restarted.all("PRAGMA foreign_key_check") == []
        finally:
            later.http.close()


@pytest.mark.parametrize("retry_us", [175, 200, 300])
def test_current_rest_rejection_boundary_characterization(
    github_runtime, monkeypatch, retry_us
):
    """The independently demonstrated newer rejection gap stays repaired.

    A list at 150 commits; a validly identified but malformed member at 200 is
    rejected. The rejected body is discarded, while partial@200 remains current
    after a terminal retry at 175. Equal time stays contradictory; 300 completes.
    The initial baseline characterization is recorded in the workstream report.
    """
    store, repo, _, api = github_runtime
    pr = seed_pr(store, repo)
    job = new_job(store)
    current = collector(store)
    endpoint = api.url + "/repos/fixture/alpha/pulls/41/reviews"
    blocked = [True]
    stamp = [150]
    current.http.clock_us = lambda: stamp[0]
    monkeypatch.setattr(
        "repo_catalog.adapters.github.persistence.now_us", lambda: stamp[0]
    )

    def route(method, path, params, body):
        page = params.get("page", ["1"])[0]
        if page == "1":
            stamp[0] = 150
            return [], {"Link": f'<{endpoint}?page=2>; rel="next"'}
        stamp[0] = 200 if blocked[0] else retry_us
        return [{"id": 2, "body": 7}] if blocked[0] else [], {}

    api.route = route
    try:
        with pytest.raises(CatalogError) as error:
            current.current_collection(
                repo,
                pr["change_request_id"],
                "review",
                job,
                endpoint,
                current_parser.review,
            )
        assert error.value.code == "API_SCHEMA"
        assert store.one("SELECT count(*) FROM completion_markers")[0] == 1
        assert tuple(
            store.one(
                "SELECT coverage_state,observed_at_us FROM current_coverage WHERE kind='review'"
            )
        ) == ("partial", 200)
        assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
        JobService(store).update(job, "waiting")
        JobService(store).resume(job)
        store.expected_attempt = 2
        blocked[0] = False
        current.current_collection(
            repo,
            pr["change_request_id"],
            "review",
            job,
            endpoint,
            current_parser.review,
        )
        assert tuple(
            store.one(
                "SELECT coverage_state,observed_at_us FROM current_coverage WHERE kind='review'"
            )
        ) == (
            ("partial", 200)
            if retry_us < 200
            else ("conflict", 200)
            if retry_us == 200
            else ("complete", retry_us)
        )
        assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
    finally:
        current.http.close()


def test_conditional_reuse_mismatch_refetches_and_match_adds_no_observation(
    github_runtime, monkeypatch
):
    store, repo, fixture, api = github_runtime
    pr = seed_pr(store, repo)
    current = collector(store)
    endpoint = api.url + "/repos/fixture/alpha/pulls/41"
    value_a = copy.deepcopy(api.prs[41])
    value_b = {
        **value_a,
        "head": {**value_a["head"], "sha": fixture.alpha.commits["N"]},
    }
    stamp = [100]
    requests = []
    responses = [
        httpx.Response(
            200,
            headers={"etag": '"A"'},
            json=value_a,
            extensions={"catalog_observed_at_us": 100},
        ),
        httpx.Response(200, json=value_b, extensions={"catalog_observed_at_us": 200}),
        httpx.Response(304),
        httpx.Response(
            200,
            headers={"etag": '"A"'},
            json=value_a,
            extensions={"catalog_observed_at_us": 300},
        ),
        httpx.Response(304),
    ]
    monkeypatch.setattr(
        "repo_catalog.adapters.github.persistence.now_us", lambda: stamp[0]
    )
    monkeypatch.setattr(
        "repo_catalog.adapters.github.collector.now_us", lambda: stamp[0]
    )

    def request(url, repo=None, **kwargs):
        requests.append(kwargs.get("headers", {}))
        return responses.pop(0)

    current.request_get = request
    try:
        _, anchor = current.detail(repo, pr, new_job(store), endpoint)
        stamp[0] = 200
        current.code_check(repo, pr, new_job(store), endpoint, anchor)
        stamp[0] = 300
        current.detail(repo, pr, new_job(store), endpoint)
        assert requests[2:4] == [{"If-None-Match": '"A"'}, {}]
        count = store.one("SELECT count(*) FROM change_request_observations")[0]
        fetches = store.one("SELECT count(*) FROM fetch_occurrences")[0]
        stamp[0] = 400
        _, reused = current.detail(repo, pr, new_job(store), endpoint)
        assert requests[-1] == {"If-None-Match": '"A"'}
        assert store.one("SELECT count(*) FROM change_request_observations")[0] == count
        assert store.one("SELECT count(*) FROM fetch_occurrences")[0] == fetches
        assert (
            store.one(
                "SELECT observed_at_us FROM change_request_observations WHERE change_request_observation_id=?",
                (reused,),
            )[0]
            == 300
        )
        marker = store.one(
            "SELECT evidence,observed_at_us FROM completion_markers WHERE json_extract(evidence,'$.status')=304"
        )
        assert marker["observed_at_us"] == 400
        assert json.loads(marker["evidence"])["change_request_observation_uuidv4"]
        assert not responses
        assert store.all("PRAGMA foreign_key_check") == []
    finally:
        current.http.close()
