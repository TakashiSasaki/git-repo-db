"""Selected review coverage follows terminal evidence, independent of pagination."""

import pytest

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.application.job_service import JobService
from repo_catalog.application.query_service import QueryService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime
from tests.support.github_runtime import sync


def start_threads(store):
    with store.transaction():
        if not store.one(
            "SELECT 1 FROM change_requests WHERE change_request_id='repo:41'"
        ):
            store.execute(
                "INSERT INTO change_requests(change_request_id,repository_uuidv4,"
                "repository_binding_id,change_request_kind,provider_change_request_number) "
                "VALUES('repo:41','repo','binding','pull_request',41)"
            )
    job = JobService(store).create("sync", {"kind": "pr"})
    store.expected_attempt = 1
    return job


def collect_threads(store, repo, job):
    collector = GitHubCollector(store, CancellationToken())
    collector.facts.principal = "fixture"
    try:
        return collector.threads(
            repo,
            {"change_request_id": "repo:41", "provider_change_request_number": 41},
            job,
        )
    finally:
        collector.http.close()


def selected_thread(store, *, resource="THREAD41-0", limit=1000):
    return QueryService(store.path).query(
        "pr thread",
        {
            "repo": "repo",
            "provider_change_request_number": 41,
            "provider_resource_id": resource,
        },
        limit=limit,
    )


def assert_thread_partial(store, *, count):
    first = selected_thread(store, limit=1)
    full = selected_thread(store)
    assert first.coverage == full.coverage
    assert full.status == "partial"
    assert len(full.data["items"]) == count
    assert full.coverage.missing == [
        {
            "kind": "pr",
            "reason": "thread_listing_incomplete",
            "change_request_id": "repo:41",
            "provider_resource_id": "THREAD41-0",
        }
    ]


@pytest.mark.parametrize("boundary", ["root-partial", "child-error", "child-partial"])
def test_unsaved_thread_comments_remain_partial_until_resume(github_runtime, boundary):
    store, repo, _, api = github_runtime
    api.reply_count = 101
    original = api.route
    blocked = True
    requested = []

    def route(method, path, params, body):
        if method != "POST":
            return original(method, path, params, body)
        variables = body["variables"]
        location = "child" if "thread" in variables else "root"
        requested.append((location, variables.copy()))
        if blocked and boundary == "child-error" and location == "child":
            return {"data": None, "errors": [{"message": "unavailable"}]}, {}
        payload, headers = original(method, path, params, body)
        if blocked and boundary.startswith(location):
            payload["errors"] = [{"message": "partial"}]
            if location == "child":
                # The terminal child is truncated despite the outer HTTP 200.
                payload["data"]["node"]["comments"]["nodes"] = []
        return payload, headers

    api.route = route
    job = start_threads(store)
    with pytest.raises(CatalogError, match="partial|error-only|errors"):
        collect_threads(store, repo, job)
    assert_thread_partial(store, count=100)
    assert not store.one("SELECT 1 FROM completion_markers")
    blocked = False
    before = len(requested)
    collect_threads(store, repo, job)
    completed = selected_thread(store)
    assert completed.status == "complete"
    assert completed.coverage.missing == []
    assert len(completed.data["items"]) == 101
    # Resuming child work consumes the saved root page without another request.
    expected = ["root", "child"] if boundary == "root-partial" else ["child"]
    assert [kind for kind, _ in requested[before:]] == expected


@pytest.mark.parametrize("error_type", ["FORBIDDEN", "RATE_LIMITED", "no-response"])
def test_unobserved_new_root_preserves_terminal_thread(github_runtime, error_type):
    store, repo, _, api = github_runtime
    collect_threads(store, repo, start_threads(store))
    assert selected_thread(store).status == "complete"
    original = api.route
    blocked = True

    def route(method, path, params, body):
        if blocked and method == "POST":
            return {
                "data": None,
                "errors": [{"message": "unavailable", "type": error_type}],
            }, {}
        return original(method, path, params, body)

    api.route = route
    if error_type == "no-response":
        api.failures["/graphql"] = [404]
    job = start_threads(store)
    with pytest.raises(CatalogError):
        collect_threads(store, repo, job)
    assert selected_thread(store).status == "complete"
    blocked = False
    collect_threads(store, repo, job)
    assert selected_thread(store).status == "complete"


@pytest.mark.parametrize("response_shape", ["partial", "malformed"])
def test_new_observed_root_gap_supersedes_older_terminal_thread(
    github_runtime, response_shape
):
    store, repo, _, api = github_runtime
    collect_threads(store, repo, start_threads(store))
    original = api.route

    def route(method, path, params, body):
        payload, headers = original(method, path, params, body)
        if method == "POST":
            if response_shape == "malformed":
                payload["data"]["repository"]["pullRequest"] = {}
            else:
                payload["errors"] = [{"message": "partial"}]
        return payload, headers

    api.route = route
    with pytest.raises(CatalogError):
        collect_threads(store, repo, start_threads(store))
    assert_thread_partial(store, count=1)


def test_resumed_older_job_uses_new_observation_instead_of_later_started_job(
    github_runtime,
):
    store, repo, _, api = github_runtime
    api.reply_count = 101
    api.graphql_partial = True
    earlier = start_threads(store)
    with pytest.raises(CatalogError):
        collect_threads(store, repo, earlier)
    api.reply_count = 1
    api.graphql_partial = False
    collect_threads(store, repo, start_threads(store))
    assert selected_thread(store).status == "complete"
    api.reply_count = 101
    original = api.route

    def route(method, path, params, body):
        if method == "POST" and "thread" in body["variables"]:
            return {"data": None, "errors": [{"message": "unavailable"}]}, {}
        return original(method, path, params, body)

    api.route = route
    with pytest.raises(CatalogError):
        collect_threads(store, repo, earlier)
    assert_thread_partial(store, count=100)


@pytest.mark.parametrize("child_has_data", [False, True])
def test_resumed_child_observation_governs_its_thread_without_new_root_request(
    github_runtime, child_has_data
):
    store, repo, _, api = github_runtime
    api.reply_count = 101
    original = api.route
    child_data = False
    requested = []

    def route(method, path, params, body):
        if method == "POST":
            requested.append(body["variables"].copy())
            if "thread" in body["variables"]:
                payload = (
                    original(method, path, params, body)[0]
                    if child_data
                    else {"data": None}
                )
                payload["errors"] = [{"message": "unavailable"}]
                return payload, {}
        return original(method, path, params, body)

    api.route = route
    earlier = start_threads(store)
    with pytest.raises(CatalogError):
        collect_threads(store, repo, earlier)
    api.reply_count = 1
    collect_threads(store, repo, start_threads(store))
    assert selected_thread(store).status == "complete"
    api.reply_count = 101
    child_data = child_has_data
    before = len(requested)
    with pytest.raises(CatalogError):
        collect_threads(store, repo, earlier)
    assert len(requested[before:]) == 1
    assert requested[-1]["thread"] == "THREAD41-0"
    if child_has_data:
        assert_thread_partial(store, count=101)
    else:
        assert selected_thread(store).status == "complete"


@pytest.mark.parametrize("selected_needs_child", [False, True])
def test_unrelated_child_failure_keeps_selected_terminal_thread_complete(
    github_runtime, selected_needs_child
):
    store, repo, _, api = github_runtime
    api.reply_count = 101
    api.thread_count = 2
    original = api.route

    def route(method, path, params, body):
        if method == "POST" and body["variables"].get("thread") == "THREAD41-1":
            return {"data": None, "errors": [{"message": "unavailable"}]}, {}
        payload, headers = original(method, path, params, body)
        if (
            method == "POST"
            and "thread" not in body["variables"]
            and not selected_needs_child
        ):
            selected = payload["data"]["repository"]["pullRequest"]["reviewThreads"][
                "nodes"
            ][0]
            selected["comments"]["nodes"] = selected["comments"]["nodes"][:1]
            selected["comments"]["pageInfo"] = {"hasNextPage": False, "endCursor": None}
        return payload, headers

    api.route = route
    with pytest.raises(CatalogError):
        collect_threads(store, repo, start_threads(store))
    selected = selected_thread(store)
    assert selected.status == "complete"
    assert len(selected.data["items"]) == (101 if selected_needs_child else 1)
    assert selected_thread(store, resource="THREAD41-1").status == "partial"


def test_child_completion_from_another_root_does_not_prove_selected_thread(
    github_runtime,
):
    store, repo, _, api = github_runtime
    api.reply_count = 101
    collect_threads(store, repo, start_threads(store))
    assert selected_thread(store).status == "complete"
    # A new root cannot borrow the older root's completed child, even though
    # the PR and thread IDs are identical and its comments remain stored.
    original = api.route

    def route(method, path, params, body):
        if method == "POST" and "thread" in body["variables"]:
            return {"data": None, "errors": [{"message": "unavailable"}]}, {}
        return original(method, path, params, body)

    api.route = route
    with pytest.raises(CatalogError):
        collect_threads(store, repo, start_threads(store))
    assert_thread_partial(store, count=101)


def test_timeline_failure_is_outside_document_scope(github_runtime):
    store, repo, _, api = github_runtime
    api.failures["/repos/fixture/alpha/issues/41/timeline"] = [404]
    with pytest.raises(CatalogError) as raised:
        sync(store, repo)
    assert raised.value.code == "PR_PARTIAL"
    with store.transaction():
        for kind in ("timeline", "pr-timeline"):
            store.coverage(
                "repo", kind, "partial", change_request_id="repo:41", observed_at_us=1
            )
    query = QueryService(store.path)
    options = {"repo": "repo", "provider_change_request_number": 41}
    for command in ("pr documents", "search pr"):
        result = query.query(command, {**options, "literal": "body-marker"})
        assert result.status == "complete"
        assert result.coverage.missing == []
        assert result.data["items"]
    for command in ("pr timeline", "pr show"):
        result = query.query(command, options)
        assert result.status == "partial"
        assert any(
            gap.get("collection_kind") == "timeline" for gap in result.coverage.missing
        )
