"""Synthetic HTTP acceptance of catalog3 history, listings and restart boundaries."""

import json

import httpx
import pytest

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.application.job_service import JobService
from repo_catalog.config import DEFAULTS
from repo_catalog.domain.models import CancellationToken, CatalogError, Waiting
from repo_catalog.domain.time import parse_iso8601_us
from tests.support.github_runtime import github_runtime as github_runtime
from tests.support.github_runtime import sync


@pytest.mark.parametrize(
    "headers,expected_us",
    [
        ({"retry-after": "2.000001"}, 1_002_000_124),
        ({"retry-after": "0"}, 1_000_000_123),
        ({"retry-after": "-2"}, 1_000_000_123),
        ({"retry-after": "Thu, 01 Jan 1970 00:33:20 GMT"}, 2_000_000_000),
        ({"x-ratelimit-reset": "2000"}, 2_000_000_000),
        ({"x-ratelimit-reset": "1"}, 1_001_000_123),
        ({"retry-after": "NaN"}, 1_060_000_123),
        ({"x-ratelimit-reset": "Infinity"}, 1_060_000_123),
        ({}, 1_060_000_123),
    ],
)
def test_rate_limit_boundaries_are_exact_epoch_microseconds(headers, expected_us):
    def response(request):
        return httpx.Response(429, headers=headers, json={})

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        transport = GitHubTransport(
            DEFAULTS["github"],
            CancellationToken(),
            client=client,
            clock_us=lambda: 1_000_000_123,
        )
        with pytest.raises(Waiting) as raised:
            transport.request("GET", transport.base + "/user")
    assert raised.value.code == "RATE_LIMIT"
    assert raised.value.details == {"not_before_us": expected_us}
    assert type(raised.value.details["not_before_us"]) is int


@pytest.mark.parametrize("boundary", ["root", "child"])
@pytest.mark.parametrize("data_shape", ["null", "empty", "null-resource"])
@pytest.mark.parametrize(
    "error_type,expected_code,delay_us",
    [
        ("RATE_LIMITED", "RATE_LIMIT", 60_000_000),
        ("FORBIDDEN", "GRAPHQL_PARTIAL", None),
    ],
)
def test_graphql_error_only_response_retains_backoff_and_resume_boundary(
    github_runtime,
    monkeypatch,
    boundary,
    data_shape,
    error_type,
    expected_code,
    delay_us,
):
    store, repo, fixture, api = github_runtime
    pr = {
        "change_request_id": "00000000-0000-4000-8000-000000000301:41",
        "provider_change_request_number": 41,
    }
    with store.transaction():
        store.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,"
            "repository_binding_id,change_request_kind,provider_change_request_number) "
            "VALUES('00000000-0000-4000-8000-000000000301:41','00000000-0000-4000-8000-000000000301','binding','pull_request',41)"
        )
    if boundary == "child":
        api.reply_count = 101

    stamp_us = 1_000_000
    monkeypatch.setattr(
        "repo_catalog.adapters.github.persistence.now_us", lambda: stamp_us
    )
    jobs = JobService(store, clock_us=lambda: stamp_us)
    job = jobs.create("sync", {"kind": "pr"})
    store.expected_attempt = 1
    original = api.route
    blocked = True
    requested = []
    error_payload = {
        "data": None,
        "errors": [{"type": error_type, "message": "synthetic GraphQL failure"}],
    }
    if data_shape == "empty":
        error_payload["data"] = {}
    elif data_shape == "null-resource":
        error_payload["data"] = (
            {"node": None}
            if boundary == "child"
            else {"repository": {"pullRequest": None}}
        )

    def route(method, path, params, body):
        nonlocal stamp_us
        if method == "POST":
            location = "child" if "thread" in body["variables"] else "root"
            requested.append(location)
            if blocked and location == boundary:
                stamp_us = 9_000_000
                return error_payload, {}
        return original(method, path, params, body)

    api.route = route

    def collector():
        result = GitHubCollector(store, CancellationToken())
        result.facts.principal = "fixture"
        result.http.clock_us = lambda: stamp_us
        return result

    current = collector()
    try:
        with pytest.raises(CatalogError) as raised:
            current.threads(repo, pr, job)
    finally:
        current.http.close()

    error = raised.value
    assert error.code == expected_code
    deadline_us = stamp_us + delay_us if delay_us is not None else None
    assert error.details.get("not_before_us") == deadline_us
    rejected_kind = "threads" if boundary == "root" else "thread-comments"
    if boundary == "root":
        # Independent thread interpretation still requires its original input.
        rejected = store.one(
            "SELECT o.next_cursor,o.request,b.body,u.reason "
            "FROM fetch_occurrences o "
            "JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id "
            "JOIN payloads p ON p.representation=o.payload_representation AND p.sha256=o.payload_sha256 JOIN stored_bytes b ON b.sha256=p.sha256 "
            "JOIN unresolved_payloads u ON u.payload_representation=p.representation AND u.payload_sha256=p.sha256 "
            "WHERE f.kind=? ORDER BY o.fetch_occurrence_id DESC LIMIT 1",
            (rejected_kind,),
        )
        assert json.loads(rejected["body"]) == error_payload
        assert rejected["next_cursor"] is None
        assert expected_code in rejected["reason"]
        # An error-only response has no thread resource observation, for both
        # denied access and rate limits. The raw diagnostic remains retained.
        assert json.loads(rejected["request"])["operational_only"] is True
    else:
        rejected = store.one(
            "SELECT p.fetch_collection_id,p.state,p.cursor,p.reason "
            "FROM collection_progress p JOIN fetch_collections f USING(fetch_collection_id) "
            "WHERE f.kind='thread-comments'"
        )
        assert (rejected["state"], rejected["cursor"], rejected["reason"]) == (
            "partial",
            "100",
            expected_code,
        )
        # A rejected mutable page has a durable retry boundary, no false
        # success receipt, and no mandatory HTTP body behind the domain store.
        assert not store.one(
            "SELECT 1 FROM current_collection_pages WHERE fetch_collection_id=?",
            (rejected["fetch_collection_id"],),
        )
        assert not store.one(
            "SELECT 1 FROM fetch_occurrences WHERE fetch_collection_id=?",
            (rejected["fetch_collection_id"],),
        )
        assert (
            store.one(
                "SELECT count(*) FROM review_resources WHERE kind='review-comment'"
            )[0]
            == 100
        )
    assert current.summary_observed_at_us(repo, job) == (
        1_000_000 if boundary == "child" else None
    )
    assert current.saved_thread_code_input(pr["change_request_id"])[2] == (
        1_000_000 if boundary == "child" else None
    )
    assert not store.one(
        "SELECT 1 FROM completion_markers c "
        "JOIN fetch_collections f ON f.fetch_collection_id=c.fetch_collection_id "
        "WHERE f.kind IN ('threads','thread-comments')"
    )
    if boundary == "root":
        assert not store.one(
            "SELECT 1 FROM current_coverage "
            "WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='threads'"
        )
    jobs.update(job, "waiting", expected_code, not_before_us=deadline_us)
    waiting = store.one(
        "SELECT a.state,a.not_before_us FROM jobs j "
        "JOIN job_attempts a ON a.job_id=j.job_id AND a.attempt=j.current_attempt "
        "WHERE j.job_id=?",
        (job,),
    )
    assert waiting["state"] == "waiting"
    assert waiting["not_before_us"] == deadline_us
    if deadline_us is not None:
        with pytest.raises(Waiting) as early:
            jobs.resume(job)
        assert early.value.code == "NOT_BEFORE"
        assert early.value.details["not_before_us"] == deadline_us

    request_boundary = len(requested)
    stamp_us = deadline_us if deadline_us is not None else stamp_us + 1_000_000
    jobs.resume(job)
    store.expected_attempt = 2
    blocked = False
    current = collector()
    try:
        current.threads(repo, pr, job)
    finally:
        current.http.close()
    # A child retry reads its saved root and requests only the original child
    # cursor. A rejected root restarts at the original root boundary.
    assert requested[request_boundary:] == [boundary]
    assert (
        store.one(
            "SELECT coverage_state FROM current_coverage "
            "WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='threads'"
        )[0]
        == "complete"
    )
    jobs.update(job, "complete")
    assert store.one("SELECT current_attempt FROM jobs WHERE job_id=?", (job,))[0] == 2
    assert not store.all("PRAGMA foreign_key_check")


def test_fresh_history_and_sealed_listing_reuse(github_runtime):
    store, repo, fixture, api = github_runtime
    api.etag = True
    sync(store, repo)
    assert (
        store.one(
            "SELECT count(*) FROM coverage_scopes WHERE repository_uuidv4='00000000-0000-4000-8000-000000000301' AND change_request_id IS NULL AND kind IN ('refs','structure','digests','heads-text')"
        )[0]
        == 0
    )
    assert (
        store.one(
            "SELECT count(*) FROM current_coverage WHERE kind='pr-code' AND coverage_state='complete'"
        )[0]
        == 3
    )
    assert store.one("SELECT count(*) FROM change_requests")[0] == 3
    assert store.one("SELECT count(*) FROM review_threads")[0] == 3
    assert (
        store.one("SELECT count(*) FROM review_resources WHERE kind='review'")[0] == 3
    )
    assert not store.one(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name IN ('reviews','review_comments')"
    )
    assert not store.one(
        "SELECT 1 FROM documents WHERE kind IN ('review','review-comment')"
    )
    assert store.one("SELECT count(*) FROM change_request_events")[0] == 9
    assert (
        store.one("SELECT count(*) FROM code_listing_progress WHERE state='complete'")[
            0
        ]
        == 6
    )
    assert (
        store.one("SELECT count(*) FROM root_origins WHERE origin_kind='pr_role'")[0]
        >= 6
    )
    api.stage = "B"
    sync(store, repo)
    old_page = store.one(
        "SELECT f.*,o.fetch_occurrence_id fetch_occurrence_id,o.observed_at_us page_observed_at_us,b.body FROM fetch_collections f JOIN fetch_occurrences o ON o.fetch_collection_id=f.fetch_collection_id JOIN payloads p ON p.representation=o.payload_representation AND p.sha256=o.payload_sha256 JOIN stored_bytes b ON b.sha256=p.sha256 WHERE f.change_request_id='00000000-0000-4000-8000-000000000301:41' AND f.kind='issue-comment' ORDER BY o.observed_at_us LIMIT 1"
    )
    current_version = store.one(
        "SELECT document_observation_id FROM current_document_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='issue-comment' AND provider_change_request_document_id='241'"
    )[0]
    observation_count = store.one("SELECT count(*) FROM document_observations")[0]
    from repo_catalog.adapters.github.persistence import ApiFacts

    # Independent offline reparse creates a result, not another remote fetch;
    # without explicit selection the current B interpretation remains selected.
    remote_before = [
        tuple(r)
        for r in store.all(
            "SELECT fetch_occurrence_uuidv4,observed_at_us FROM fetch_occurrences ORDER BY fetch_occurrence_id"
        )
    ]
    result_count = store.one("SELECT count(*) FROM parsed_results")[0]
    with store.transaction():
        old_value = json.loads(old_page["body"])[0]
        reparsing = ApiFacts(store, store.config["github"])
        reparsing.select_results = False
        reparsing.document(
            "00000000-0000-4000-8000-000000000301:41",
            "issue-comment",
            "241",
            old_value["body"],
            old_value,
            dict(old_page),
            old_page["fetch_occurrence_id"],
            0,
            old_page["page_observed_at_us"],
        )
        reparsing.publish()
    assert [
        tuple(r)
        for r in store.all(
            "SELECT fetch_occurrence_uuidv4,observed_at_us FROM fetch_occurrences ORDER BY fetch_occurrence_id"
        )
    ] == remote_before
    assert store.one("SELECT count(*) FROM parsed_results")[0] == result_count + 1
    assert (
        store.one(
            "SELECT document_observation_id FROM current_document_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='issue-comment' AND provider_change_request_document_id='241'"
        )[0]
        == current_version
    )
    assert (
        store.one("SELECT count(*) FROM document_observations")[0]
        == observation_count + 1
    )
    first = len(api.requests)
    api.stage = "A"
    sync(store, repo)
    assert not any(
        path.endswith(("/commits", "/files")) for _, path, _ in api.requests[first:]
    )
    versions = store.all(
        "SELECT b.body,o.fetch_occurrence_id,1 observations FROM document_observations o JOIN text_bodies b ON b.sha256=o.text_body_sha256 WHERE o.kind='issue-comment' AND o.change_request_id='00000000-0000-4000-8000-000000000301:41' ORDER BY o.document_observation_id"
    )
    assert {r["body"] for r in versions} == {"comment-marker A", "comment-marker B"}
    assert (
        len({r["fetch_occurrence_id"] for r in versions if r["body"].endswith("A")})
        == 2
    )
    assert sum(r["observations"] for r in versions if r["body"].endswith("A")) == 3
    assert len(versions) == 4
    assert (
        store.one(
            "SELECT count(DISTINCT o.text_body_sha256) FROM document_observations o WHERE o.kind='issue-comment' AND o.change_request_id='00000000-0000-4000-8000-000000000301:41'"
        )[0]
        == 2
    )
    assert store.all("PRAGMA foreign_key_check") == []
    assert b"fixture-dummy" not in store.db_path.read_bytes()


def test_terminal_page_resume_has_one_original_coverage_observation(
    github_runtime, monkeypatch
):
    store, repo, fixture, api = github_runtime
    job = JobService(store).create("sync", {"kind": "pr"})
    collector = GitHubCollector(store, CancellationToken())
    collector.facts.principal = "fixture"
    endpoint = api.url + "/repos/fixture/alpha/issues/comments"

    def interrupt(phase):
        if phase == "after_api_page_commit":
            raise CatalogError("CANCELLED", "Committed terminal page")

    monkeypatch.setattr("repo_catalog.adapters.git.runner.hook", interrupt)
    try:
        with pytest.raises(CatalogError, match="Committed terminal page"):
            collector.collection(
                repo, None, "terminal-fixture", job, endpoint, lambda *args: None
            )
        page = store.one("SELECT * FROM fetch_occurrences")
        assert page["next_cursor"] is None
        assert not store.one("SELECT 1 FROM coverage_claims")
        JobService(store).update(job, "interrupted")
        JobService(store).resume(job)
        monkeypatch.setattr("repo_catalog.adapters.git.runner.hook", lambda phase: None)
        before = len(api.requests)
        collector.collection(
            repo, None, "terminal-fixture", job, endpoint, lambda *args: None
        )
        # Finishing and then reusing that same terminal page acquires nothing.
        collector.collection(
            repo, None, "terminal-fixture", job, endpoint, lambda *args: None
        )
        assert len(api.requests) == before
        assert store.one("SELECT count(*) FROM fetch_occurrences")[0] == 1
        claims = store.all(
            "SELECT coverage_state,observed_at_us,details_json FROM coverage_claims"
        )
        assert len(claims) == 1
        assert tuple(claims[0])[:2] == ("complete", page["observed_at_us"])
        proof = json.loads(claims[0]["details_json"])
        assert proof["fetch_collection_ids"] == [page["fetch_collection_id"]]
        marker = store.one(
            "SELECT completion_marker_uuidv4,evidence FROM completion_markers"
        )
        assert proof["completion_marker_uuidv4s"] == [
            marker["completion_marker_uuidv4"]
        ]
        assert json.loads(marker["evidence"])["fetch_occurrence_uuidv4s"] == [
            page["fetch_occurrence_uuidv4"]
        ]
        assert (
            store.one("SELECT observed_at_us FROM completion_markers")[0]
            == page["observed_at_us"]
        )

        # A subsequent scan that obtains no response records operational failure,
        # while the prior observed complete claim remains current.
        next_job = JobService(store).create("sync", {"kind": "pr"})
        api.failures["/repos/fixture/alpha/issues/comments"] = [503] * 5
        with pytest.raises(CatalogError):
            collector.collection(
                repo, None, "terminal-fixture", next_job, endpoint, lambda *args: None
            )
        assert store.one("SELECT count(*) FROM coverage_claims")[0] == 1
        assert (
            store.one(
                "SELECT state FROM collection_progress WHERE job_id=?", (next_job,)
            )[0]
            == "partial"
        )
    finally:
        collector.http.close()


def test_sync_failure_before_any_response_preserves_saved_coverage(github_runtime):
    store, repo, fixture, api = github_runtime
    sync(store, repo)
    claims = [
        tuple(row)
        for row in store.all("SELECT * FROM coverage_claims ORDER BY coverage_claim_id")
    ]
    api.failures["/user"] = [503] * 5
    before = len(api.requests)
    with pytest.raises(CatalogError):
        sync(store, repo)
    assert {path for _, path, _ in api.requests[before:]} == {"/user"}
    assert [
        tuple(row)
        for row in store.all("SELECT * FROM coverage_claims ORDER BY coverage_claim_id")
    ] == claims


@pytest.mark.parametrize("previously_saved", [False, True])
def test_git_ref_mismatch_cannot_publish_complete_code(
    github_runtime, previously_saved
):
    from repo_catalog.application.query_service import QueryService

    store, repo, fixture, api = github_runtime
    sync(store, repo)
    new_head = fixture.alpha.commit(
        "Q", {b"new-only-Q.txt": b"required PR code"}, ("P",)
    )
    api.prs[41]["head"]["sha"] = new_head
    original = api.route

    def route(method, path, params, body):
        if path == "/repos/fixture/alpha/pulls/41/commits":
            return [{"sha": new_head}], {}
        if path == "/repos/fixture/alpha/pulls/41/files":
            return [{"filename": "new-only-Q.txt", "status": "added"}], {}
        return original(method, path, params, body)

    api.route = route
    if previously_saved:
        fixture.alpha.ref("refs/pull/41/head", "Q")
        sync(store, repo)
    fixture.alpha.ref("refs/pull/41/head", "N")
    with pytest.raises(CatalogError) as raised:
        sync(store, repo)
    assert raised.value.code == "PR_PARTIAL"
    assert any(
        failure["reason"] == "PR_CODE_RACE"
        for failure in raised.value.details["missing"]
    )
    assert (
        bool(
            store.one(
                "SELECT 1 FROM git_objects WHERE oid=?", (bytes.fromhex(new_head),)
            )
        )
        is previously_saved
    )
    code = store.one(
        "SELECT * FROM code_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' ORDER BY code_observation_id DESC LIMIT 1"
    )
    assert code["state"] == "partial"
    assert json.loads(code["details"])["expected_roles"]["head"] == new_head
    assert (
        bool(
            store.one(
                "SELECT 1 FROM code_acquisitions WHERE code_observation_id=? AND role='head'",
                (code["code_observation_id"],),
            )
        )
        is previously_saved
    )
    for pr, kind in (
        ("00000000-0000-4000-8000-000000000301:41", "pr-code"),
        (None, "pr"),
    ):
        coverage = store.one(
            "SELECT coverage_state,observed_at_us FROM current_coverage WHERE repository_uuidv4='00000000-0000-4000-8000-000000000301' AND change_request_id IS ? AND kind=?",
            (pr, kind),
        )
        assert coverage["coverage_state"] == "partial"
        assert store.one(
            "SELECT 1 FROM fetch_occurrences WHERE observed_at_us=?",
            (coverage["observed_at_us"],),
        )
    result = QueryService(store.path).query(
        "pr show",
        {
            "repo": "00000000-0000-4000-8000-000000000301",
            "provider_change_request_number": 41,
        },
    )
    assert result.status == "partial"
    assert result.coverage.missing
    assert not result.coverage.complete_for_requested_scope


def test_failed_git_refresh_reuses_preserved_exact_roles_without_new_claim(
    github_runtime, monkeypatch
):
    from repo_catalog.adapters.git.importer import GitImporter

    store, repo, fixture, api = github_runtime
    sync(store, repo)
    original = GitImporter.sync
    claim = tuple(
        store.one(
            "SELECT coverage_state,observed_at_us FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='pr-code'"
        )
    )

    def fail_refresh(self, repo, job, **kwargs):
        root = kwargs["pr_roots"][0]
        if root["number"] == 41:
            raise CatalogError("GIT_ERROR", "Synthetic transport failure before fetch")
        return original(self, repo, job, **kwargs)

    monkeypatch.setattr(GitImporter, "sync", fail_refresh)
    with pytest.raises(CatalogError):
        sync(store, repo)
    code = store.one(
        "SELECT * FROM code_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' ORDER BY code_observation_id DESC LIMIT 1"
    )
    assert code["state"] == "complete"
    assert json.loads(code["details"])["missing_roles"] == []
    assert (
        tuple(
            store.one(
                "SELECT coverage_state,observed_at_us FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='pr-code'"
            )
        )
        == claim
    )


def test_error_only_rate_during_sync_preserves_saved_code_and_claims(
    github_runtime, monkeypatch
):
    store, repo, fixture, api = github_runtime
    api.etag = True
    stamp_us = 1_000_000
    monkeypatch.setattr(
        "repo_catalog.adapters.github.persistence.now_us", lambda: stamp_us
    )
    monkeypatch.setattr(
        "repo_catalog.adapters.github.collector.now_us", lambda: stamp_us
    )
    sync(store, repo)
    claims = {
        row["coverage_scope_id"]: (row["coverage_state"], row["observed_at_us"])
        for row in store.all(
            "SELECT * FROM current_coverage WHERE kind IN ('pr-code','pr','pr-documents')"
        )
    }
    code_rows = [
        tuple(row)
        for row in store.all(
            "SELECT code_observation_id,change_request_observation_id,state FROM code_observations ORDER BY code_observation_id"
        )
    ]
    stamp_us = 2_000_000
    original = api.route

    def route(method, path, params, body):
        nonlocal stamp_us
        if method == "POST":
            stamp_us = 9_000_000
            return {"data": None, "errors": [{"type": "RATE_LIMITED"}]}, {}
        return original(method, path, params, body)

    api.route = route
    jobs = JobService(store, clock_us=lambda: stamp_us)
    job = jobs.create(
        "sync", {"kind": "pr", "repositories": ["00000000-0000-4000-8000-000000000301"]}
    )
    store.expected_attempt = 1
    collector = GitHubCollector(store, CancellationToken())
    collector.http.clock_us = lambda: stamp_us
    with pytest.raises(Waiting) as raised:
        collector.sync(repo, job)
    assert raised.value.code == "PR_PARTIAL"
    assert raised.value.details["not_before_us"] == 69_000_000
    jobs.update(job, "waiting", raised.value.code, not_before_us=69_000_000)
    assert any(
        failure["reason"] == "RATE_LIMIT" for failure in raised.value.details["missing"]
    )
    assert {
        row["coverage_scope_id"]: (row["coverage_state"], row["observed_at_us"])
        for row in store.all(
            "SELECT * FROM current_coverage WHERE kind IN ('pr-code','pr','pr-documents')"
        )
    } == claims
    assert [
        tuple(row)
        for row in store.all(
            "SELECT code_observation_id,change_request_observation_id,state FROM code_observations ORDER BY code_observation_id"
        )
    ] == code_rows
    assert collector.summary_observed_at_us(repo, job) == 2_000_000
    receipt = store.one(
        "SELECT observed_at_us FROM fetch_occurrences WHERE json_extract(request,'$.operational_only')=1"
    )
    assert receipt["observed_at_us"] == 9_000_000


@pytest.mark.parametrize("scenario", ["same-current", "new-current", "observed-race"])
def test_failed_code_check_after_detail_keeps_only_justified_code_observations(
    github_runtime, monkeypatch, scenario
):
    from urllib.parse import urlsplit

    from repo_catalog.application.query_service import QueryService

    store, repo, fixture, api = github_runtime
    api.etag = True
    sync(store, repo)
    previous = store.one(
        "SELECT * FROM code_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' ORDER BY code_observation_id DESC LIMIT 1"
    )
    previous_count = store.one(
        "SELECT count(*) FROM code_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41'"
    )[0]
    previous_claim = tuple(
        store.one(
            "SELECT coverage_state,observed_at_us FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='pr-code'"
        )
    )
    if scenario == "new-current":
        api.stage = "B"
        api.prs[41]["title"] = "new actual API observation"
    elif scenario == "observed-race":
        fixture.alpha.ref("refs/pull/41/head", "N")
    attempts = []
    original = httpx.Client.stream

    def stream(client, method, url, **kwargs):
        if (
            method == "GET"
            and urlsplit(str(url)).path == "/repos/fixture/alpha/pulls/41"
            and not kwargs.get("headers", {}).get("If-None-Match")
        ):
            attempts.append(str(url))
            raise httpx.ConnectError("Synthetic code-check transport failure")
        return original(client, method, url, **kwargs)

    monkeypatch.setattr(httpx.Client, "stream", stream)
    with pytest.raises(CatalogError) as raised:
        sync(store, repo)
    assert raised.value.code == "PR_PARTIAL"
    assert len(attempts) == store.config["github"]["max_attempts"]
    latest = store.one(
        "SELECT * FROM code_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' ORDER BY code_observation_id DESC LIMIT 1"
    )
    current = store.one(
        "SELECT change_request_observation_id FROM current_change_request_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41'"
    )[0]
    assert (current != previous["change_request_observation_id"]) is (
        scenario == "new-current"
    )
    result = QueryService(store.path).query(
        "pr show",
        {
            "repo": "00000000-0000-4000-8000-000000000301",
            "provider_change_request_number": 41,
        },
    )
    if scenario == "same-current":
        assert latest["code_observation_id"] == previous["code_observation_id"]
        assert (
            store.one(
                "SELECT count(*) FROM code_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41'"
            )[0]
            == previous_count
        )
        assert (
            tuple(
                store.one(
                    "SELECT coverage_state,observed_at_us FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='pr-code'"
                )
            )
            == previous_claim
        )
        assert result.status == "complete"
    else:
        assert latest["state"] == "partial"
        assert result.status == "partial"
    if scenario == "observed-race":
        assert any(
            failure["reason"] == "PR_CODE_RACE"
            for failure in raised.value.details["missing"]
        )
        assert (
            store.one(
                "SELECT coverage_state FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='pr-code'"
            )[0]
            == "partial"
        )


def test_saved_partial_graphql_retains_merge_target_and_partial_code(github_runtime):
    store, repo, fixture, api = github_runtime
    api.graphql_partial = True
    merge_oid = fixture.alpha.commit(
        "merge-Q", {b"merge-only.txt": b"observed merge target"}, ("P",)
    )
    original = api.route

    def route(method, path, params, body):
        value, headers = original(method, path, params, body)
        if method == "POST" and body["variables"].get("number") == 43:
            value["data"]["repository"]["pullRequest"]["mergeCommit"] = {
                "oid": merge_oid
            }
        return value, headers

    api.route = route
    with pytest.raises(CatalogError) as raised:
        sync(store, repo)
    assert raised.value.code == "PR_PARTIAL"
    code = store.one(
        "SELECT * FROM code_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:43' ORDER BY code_observation_id DESC LIMIT 1"
    )
    details = json.loads(code["details"])
    assert details["expected_roles"]["merge"] == merge_oid
    assert details["code_inputs_complete"] is False
    assert code["state"] == "partial"
    assert store.one(
        "SELECT 1 FROM code_acquisitions a JOIN acquisition_roots r ON r.acquisition_root_id=a.acquisition_root_id WHERE a.code_observation_id=? AND a.role='merge' AND a.oid=? AND r.published=1",
        (code["code_observation_id"], bytes.fromhex(merge_oid)),
    )
    assert (
        store.one(
            "SELECT coverage_state FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:43' AND kind='pr-code'"
        )[0]
        == "partial"
    )
    assert not store.one(
        "SELECT 1 FROM coverage_claims c JOIN coverage_scopes s ON s.coverage_scope_id=c.coverage_scope_id WHERE s.change_request_id='00000000-0000-4000-8000-000000000301:43' AND s.kind='pr-code' AND c.coverage_state='complete'"
    )


def test_unobserved_thread_retry_does_not_promote_stale_partial_code(github_runtime):
    store, repo, fixture, api = github_runtime
    api.graphql_partial = True
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    api.graphql_partial = False
    sync(store, repo)
    claims = {
        row["coverage_scope_id"]: (row["coverage_state"], row["observed_at_us"])
        for row in store.all(
            "SELECT * FROM current_coverage WHERE kind IN ('pr-code','threads','pr')"
        )
    }
    assert all(state == "complete" for state, _ in claims.values())
    api.failures["/graphql"] = [503] * 15
    with pytest.raises(CatalogError):
        sync(store, repo, job=partial.value.details["job_id"])
    assert {
        row["coverage_scope_id"]: (row["coverage_state"], row["observed_at_us"])
        for row in store.all(
            "SELECT * FROM current_coverage WHERE kind IN ('pr-code','threads','pr')"
        )
    } == claims


def test_interrupted_new_pr_head_is_not_complete_before_code_publication(
    github_runtime, monkeypatch
):
    from repo_catalog.adapters.git.importer import GitImporter
    from repo_catalog.application.query_service import QueryService

    store, repo, fixture, api = github_runtime
    sync(store, repo)
    new_head = fixture.alpha.commit("Q", {b"new-only.txt": b"unsaved code"}, ("P",))
    fixture.alpha.ref("refs/pull/41/head", "Q")
    api.prs[41]["head"]["sha"] = new_head
    original_route, original_sync = api.route, GitImporter.sync

    def route(method, path, params, body):
        if path == "/repos/fixture/alpha/pulls/41/commits":
            return [{"sha": new_head}], {}
        return original_route(method, path, params, body)

    def interrupt(self, repo, job, **kwargs):
        if kwargs["pr_roots"][0]["number"] == 41:
            raise CatalogError("CANCELLED", "After API Q, before Git Q")
        return original_sync(self, repo, job, **kwargs)

    api.route = route
    monkeypatch.setattr(GitImporter, "sync", interrupt)
    with pytest.raises(CatalogError) as raised:
        sync(store, repo)
    assert raised.value.code == "CANCELLED"
    current = store.one(
        "SELECT change_request_observation_id FROM current_change_request_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41'"
    )[0]
    assert not store.one(
        "SELECT 1 FROM code_observations WHERE change_request_observation_id=?",
        (current,),
    )
    assert not store.one(
        "SELECT 1 FROM git_objects WHERE oid=?", (bytes.fromhex(new_head),)
    )
    # Coverage history remains immutable; current-data readiness must also be
    # checked before the reader can claim the newly published PR is complete.
    assert (
        store.one(
            "SELECT coverage_state FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='pr-code'"
        )[0]
        == "complete"
    )
    result = QueryService(store.path).query(
        "pr show",
        {
            "repo": "00000000-0000-4000-8000-000000000301",
            "provider_change_request_number": 41,
        },
    )
    assert result.status == "partial"
    assert result.coverage.missing
    assert not result.coverage.complete_for_requested_scope


@pytest.mark.parametrize("newer_sync", [False, True])
def test_partial_listing_resumes_same_items_and_no_completed_pages(
    github_runtime, newer_sync
):
    store, repo, fixture, api = github_runtime
    original = api.route
    commit_path = "/repos/fixture/alpha/pulls/41/commits"
    failed = False
    api.prs[41]["commits"] = 2

    def route(method, path, params, body):
        nonlocal failed
        if path == commit_path:
            if params.get("page") == ["2"]:
                return [{"sha": fixture.alpha.commits["N"]}], {}
            if not failed:
                api.failures[path] = [500] * 5
                failed = True
            return [{"sha": fixture.alpha.commits["P"]}], {
                "Link": f'<{api.url}{path}?per_page=100&page=2>; rel="next"'
            }
        return original(method, path, params, body)

    api.route = route
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    listing = store.one(
        "SELECT l.code_listing_id,l.fetch_collection_id,p.state,p.page_count FROM code_listings l JOIN code_listing_progress p ON p.code_listing_id=l.code_listing_id WHERE l.change_request_id='00000000-0000-4000-8000-000000000301:41' AND l.kind='commits'"
    )
    assert listing["state"] == "partial" and listing["page_count"] == 1
    original_claim = store.one(
        "SELECT coverage_state,observed_at_us FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='pr-commits'"
    )
    assert original_claim["coverage_state"] == "partial"
    assert (
        original_claim["observed_at_us"]
        == store.one(
            "SELECT MAX(observed_at_us) FROM fetch_occurrences WHERE fetch_collection_id=?",
            (listing["fetch_collection_id"],),
        )[0]
    )
    assert (
        store.one(
            "SELECT count(*) FROM code_commits WHERE code_listing_id=?",
            (listing["code_listing_id"],),
        )[0]
        == 1
    )
    if newer_sync:
        # A separate fresh acquisition can finish while this original job waits.
        sync(store, repo)
        latest = {
            row["coverage_scope_id"]: (row["coverage_state"], row["observed_at_us"])
            for row in store.all(
                "SELECT * FROM current_coverage WHERE kind IN ('pr-commits','pr-code','pr')"
            )
        }
        assert all(state == "complete" for state, _ in latest.values())
        api.failures[commit_path] = [503] * 5
        with pytest.raises(CatalogError):
            sync(store, repo, job=partial.value.details["job_id"])
        assert {
            row["coverage_scope_id"]: (row["coverage_state"], row["observed_at_us"])
            for row in store.all(
                "SELECT * FROM current_coverage WHERE kind IN ('pr-commits','pr-code','pr')"
            )
        } == latest
        return
    first = len(api.requests)
    sync(store, repo, job=partial.value.details["job_id"])
    current_claim = store.one(
        "SELECT coverage_state,observed_at_us FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='pr-commits'"
    )
    assert current_claim["coverage_state"] == "complete"
    assert current_claim["observed_at_us"] > original_claim["observed_at_us"]
    assert (
        current_claim["observed_at_us"]
        == store.one(
            "SELECT MAX(observed_at_us) FROM fetch_occurrences WHERE fetch_collection_id=?",
            (listing["fetch_collection_id"],),
        )[0]
    )
    requests = api.requests[first:]
    assert [
        params.get("page") for _, path, params in requests if path == commit_path
    ] == [["2"]]
    assert not any(
        path.startswith(
            ("/repos/fixture/alpha/pulls/42", "/repos/fixture/alpha/pulls/43")
        )
        for _, path, _ in requests
    )
    assert (
        store.one(
            "SELECT count(*) FROM code_listings WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='commits'"
        )[0]
        == 1
    )
    assert (
        store.one(
            "SELECT count(*) FROM code_commits WHERE code_listing_id=?",
            (listing["code_listing_id"],),
        )[0]
        == 2
    )
    assert (
        store.one(
            "SELECT count(*) FROM fetch_occurrences WHERE fetch_collection_id=?",
            (listing["fetch_collection_id"],),
        )[0]
        == 2
    )
    assert (
        store.one(
            "SELECT state FROM code_listing_progress WHERE code_listing_id=?",
            (listing["code_listing_id"],),
        )[0]
        == "complete"
    )


def test_watermarks_failed_child_and_resume_keep_successful_boundary(github_runtime):
    store, repo, fixture, api = github_runtime
    api.incremental = True
    sync(store, repo)
    old = store.all(
        "SELECT i.safe_watermark_us,f.kind FROM incremental_scans i JOIN fetch_collections f ON f.fetch_collection_id=i.fetch_collection_id ORDER BY i.scan_started_at_us"
    )
    old_review = store.one(
        "SELECT f.observed_at_us,c.observed_at_us completed_at_us FROM fetch_collections f "
        "JOIN completion_markers c USING(fetch_collection_id) WHERE f.kind='review-comment-incremental'"
    )
    assert all(type(row["safe_watermark_us"]) is int for row in old)
    first_incremental_request = len(api.requests)
    api.stage = "B"
    api.failures["/repos/fixture/alpha/issues/comments"] = [503] * 5
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    assert (
        store.one(
            "SELECT count(*) FROM incremental_scans i JOIN fetch_collections f ON f.fetch_collection_id=i.fetch_collection_id WHERE f.kind='issue-comment-incremental'"
        )[0]
        == 1
    )
    review = store.one(
        "SELECT f.fetch_collection_id,f.observed_at_us,c.observed_at_us completed_at_us "
        "FROM fetch_collections f JOIN completion_markers c USING(fetch_collection_id) "
        "WHERE f.kind='review-comment-incremental' ORDER BY f.observed_at_us DESC LIMIT 1"
    )
    assert review["observed_at_us"] > old_review["observed_at_us"]
    assert review["completed_at_us"] > old_review["completed_at_us"]
    before = len(api.requests)
    sync(store, repo, job=partial.value.details["job_id"])
    assert not any(
        path.endswith("/pulls/comments") for _, path, _ in api.requests[before:]
    )
    assert (
        store.one(
            "SELECT observed_at_us FROM completion_markers WHERE fetch_collection_id=?",
            (review["fetch_collection_id"],),
        )[0]
        == review["completed_at_us"]
    )
    since_values = [
        params["since"][0]
        for _, path, params in api.requests[first_incremental_request:]
        if path.endswith("/issues/comments") and "since" in params
    ]
    assert since_values
    issue_watermark_us = next(
        row["safe_watermark_us"]
        for row in old
        if row["kind"] == "issue-comment-incremental"
    )
    assert all(
        parse_iso8601_us(value) == issue_watermark_us - 300_000_000
        for value in since_values
    )
    raw = store.one(
        "SELECT metadata FROM document_observations WHERE kind='issue-comment' AND json_extract(metadata,'$.updated_at') IS NOT NULL"
    )
    assert json.loads(raw[0])["updated_at"] == "2026-01-01T00:00:00Z"


def test_graphql_nested_pagination_and_partial_payload_preservation(github_runtime):
    store, repo, fixture, api = github_runtime
    api.thread_count = 2
    api.reply_count = 101
    api.graphql_partial = True
    with pytest.raises(CatalogError):
        sync(store, repo)
    assert (
        store.one(
            "SELECT count(*) FROM current_coverage WHERE kind='pr-code' AND coverage_state='partial'"
        )[0]
        >= 1
    )
    assert (
        store.one(
            "SELECT count(*) FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE f.kind='threads'"
        )[0]
        == 3
    )
    assert (
        store.one(
            "SELECT count(*) FROM review_resources WHERE kind='review-comment' AND change_request_id='00000000-0000-4000-8000-000000000301:41'"
        )[0]
        == 200
    )
    api.graphql_partial = False
    sync(store, repo)
    assert (
        store.one(
            "SELECT count(*) FROM review_resources WHERE kind='review-comment' AND change_request_id='00000000-0000-4000-8000-000000000301:41'"
        )[0]
        == 202
    )
    assert (
        store.one(
            "SELECT count(*) FROM collection_progress p JOIN fetch_collections f ON f.fetch_collection_id=p.fetch_collection_id WHERE f.kind='thread-comments' AND p.state='complete'"
        )[0]
        == 2
    )
    assert store.all("PRAGMA foreign_key_check") == []


def test_304_never_attaches_cached_head_to_newer_race_observation(github_runtime):
    store, repo, fixture, api = github_runtime
    api.etag = True
    original = api.route
    detail_requests = 0

    def route(method, path, params, body):
        nonlocal detail_requests
        value, headers = original(method, path, params, body)
        if path == "/repos/fixture/alpha/pulls/41":
            detail_requests += 1
            if detail_requests == 2:
                value["head"] = {**value["head"], "sha": fixture.alpha.commits["N"]}
                api.stage = "B"
        return value, headers

    api.route = route
    with pytest.raises(CatalogError):
        sync(store, repo)
    current = store.one(
        "SELECT o.payload FROM current_change_request_observations o WHERE o.change_request_id='00000000-0000-4000-8000-000000000301:41'"
    )
    assert json.loads(current[0])["head"]["sha"] == fixture.alpha.commits["N"]
    api.stage = "A"
    first = len(api.requests)
    sync(store, repo)
    assert (
        len(
            [
                path
                for _, path, _ in api.requests[first:]
                if path == "/repos/fixture/alpha/pulls/41"
            ]
        )
        == 3
    )
    # Every complete code observation is backed by exactly its admitted head/base,
    # including after A -> code-race B -> cached conditional A.
    for row in store.all(
        "SELECT c.head_oid,c.base_oid,o.payload FROM code_observations c JOIN change_request_observations o ON o.change_request_observation_id=c.change_request_observation_id WHERE c.state='complete'"
    ):
        value = json.loads(row["payload"])
        assert row["head_oid"].hex() == value["head"]["sha"]
        assert row["base_oid"].hex() == value["base"]["sha"]
    for row in store.all(
        "SELECT p.change_request_observation_id FROM current_change_request_observations p"
    ):
        assert (
            store.one(
                "SELECT count(*) FROM root_origins WHERE change_request_observation_id=?",
                (row[0],),
            )[0]
            > 0
        )


def test_review_target_failure_is_retried_on_resume(github_runtime, monkeypatch):
    from repo_catalog.adapters.git.importer import GitImporter

    store, repo, fixture, api = github_runtime
    original = GitImporter.sync
    attempts = []
    failed = False

    def acquire(self, repo, job, **kwargs):
        nonlocal failed
        root = kwargs["pr_roots"][0]
        if root["number"] == 41 and root["role"].startswith("review-target:"):
            attempts.append(root["role"])
            if not failed:
                failed = True
                raise CatalogError("API_ACCESS", "synthetic review target failure")
        return original(self, repo, job, **kwargs)

    monkeypatch.setattr(GitImporter, "sync", acquire)
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    first = len(api.requests)
    sync(store, repo, job=partial.value.details["job_id"])
    assert len(attempts) == 2
    assert not any(
        path.endswith(("/reviews", "/comments", "/timeline", "/commits", "/files"))
        for _, path, _ in api.requests[first:]
    )
    code = store.one(
        "SELECT code_observation_id FROM code_observations WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' ORDER BY code_observation_id DESC LIMIT 1"
    )[0]
    assert (
        store.one(
            "SELECT count(*) FROM code_acquisitions WHERE code_observation_id=? AND role LIKE 'review-target:%'",
            (code,),
        )[0]
        == 1
    )


def test_resumed_thread_coverage_includes_prior_children_only_for_its_root(
    github_runtime, monkeypatch
):
    store, repo, fixture, api = github_runtime
    pr = {
        "change_request_id": "00000000-0000-4000-8000-000000000301:41",
        "provider_change_request_number": 41,
    }
    store.execute(
        "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES('00000000-0000-4000-8000-000000000301:41','00000000-0000-4000-8000-000000000301','binding','pull_request',41)"
    )
    job = JobService(store).create("sync", {"kind": "pr"})
    collector = GitHubCollector(store, CancellationToken())
    collector.facts.principal = "fixture"
    stamp, requested = 0, []
    monkeypatch.setattr(
        "repo_catalog.adapters.github.persistence.now_us", lambda: stamp
    )
    collector.http.clock_us = lambda: stamp

    def route(method, path, params, body):
        nonlocal stamp
        variables = body["variables"]
        if "thread" in variables:
            stamp = 300
            requested.append("child")
            return {
                "data": {
                    "node": {
                        "comments": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            }, {}
        if variables.get("cursor") is None:
            stamp = 100
            requested.append("root-1")
            connection = {
                "nodes": [
                    {
                        "id": "thread-1",
                        "comments": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": True, "endCursor": "child"},
                        },
                    }
                ],
                "pageInfo": {"hasNextPage": True, "endCursor": "root-2"},
            }
        else:
            stamp = 200
            requested.append("root-2")
            connection = {
                "nodes": [],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        return {
            "data": {"repository": {"pullRequest": {"reviewThreads": connection}}}
        }, {}

    api.route = route
    request = collector.http.request
    interrupted = False

    def interrupt_later_root(method, url, **kwargs):
        nonlocal interrupted
        if kwargs["json"]["variables"].get("cursor") == "root-2" and not interrupted:
            interrupted = True
            raise CatalogError("CANCELLED", "After advancing root cursor")
        return request(method, url, **kwargs)

    monkeypatch.setattr(collector.http, "request", interrupt_later_root)
    try:
        with pytest.raises(CatalogError, match="After advancing root cursor"):
            collector.threads(repo, pr, job)
        root = store.one("SELECT * FROM fetch_collections WHERE kind='threads'")
        progress = store.one(
            "SELECT cursor FROM collection_progress WHERE fetch_collection_id=?",
            (root["fetch_collection_id"],),
        )[0]
        assert json.loads(progress) == {"cursor": "root-2"}
        child = store.one(
            "SELECT scope.request_context FROM fetch_collections f JOIN resume_scopes scope ON scope.resume_scope_id=f.resume_scope_id WHERE f.kind='thread-comments'"
        )
        assert (
            json.loads(child[0])["parent_fetch_collection_id"]
            == root["fetch_collection_id"]
        )

        # A different root in the same repository, PR and job has a later child.
        # A query scoped only by those owners would incorrectly select 900.
        stamp = 900
        with store.transaction():
            other_root = collector.facts.begin(
                repo,
                pr["change_request_id"],
                "threads",
                job,
                collector.http.graphql,
                {"query": "unrelated-root"},
            )
            other_child = collector.facts.begin(
                repo,
                pr["change_request_id"],
                "thread-comments",
                job,
                collector.http.graphql,
                {
                    "thread": "unrelated-child",
                    "query": "child",
                    "parent_fetch_collection_id": other_root["fetch_collection_id"],
                },
            )
            from repo_catalog.adapters.sqlite.current_collections import (
                CurrentCollectionProof,
            )

            proof = CurrentCollectionProof(store.connection)
            proof.page(
                other_child["fetch_collection_id"],
                0,
                stamp,
                None,
                [],
                parser_module="repo_catalog.adapters.github.current_parser",
                parser_version="1",
            )
            collector.facts.finish(
                other_child, evidence=proof.evidence(other_child["fetch_collection_id"])
            )
        assert collector.facts.thread_observed_at_us(root) == 300
        JobService(store).update(job, "interrupted")
        JobService(store).resume(job)
        collector.threads(repo, pr, job)
        assert requested == ["root-1", "child", "root-2"]
        claim = store.one(
            "SELECT coverage_state,observed_at_us FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='threads'"
        )
        assert tuple(claim) == ("complete", 300)
        assert (
            store.one(
                "SELECT observed_at_us FROM completion_markers WHERE fetch_collection_id=?",
                (root["fetch_collection_id"],),
            )[0]
            == 300
        )
    finally:
        collector.http.close()


def test_malformed_nested_cursor_retries_saved_boundary(github_runtime):
    store, repo, fixture, api = github_runtime
    api.reply_count = 101
    original = api.route
    child_requests = []

    def route(method, path, params, body):
        value, headers = original(method, path, params, body)
        if method == "POST" and body["variables"].get("thread") == "THREAD41-0":
            child_requests.append(body["variables"]["commentCursor"])
            if len(child_requests) == 1:
                value["data"]["node"]["comments"].pop("pageInfo")
        return value, headers

    api.route = route
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    child = store.one(
        "SELECT p.state,p.cursor,f.fetch_collection_id FROM collection_progress p JOIN fetch_collections f ON f.fetch_collection_id=p.fetch_collection_id WHERE f.kind='thread-comments' AND f.change_request_id='00000000-0000-4000-8000-000000000301:41'"
    )
    assert child["state"] == "partial" and child["cursor"] == "100"
    partial_claim = store.one(
        "SELECT coverage_state,observed_at_us FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='threads'"
    )
    assert partial_claim["coverage_state"] == "partial"
    root_pages = store.one(
        "SELECT count(*) FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE f.kind='threads'"
    )[0]
    sync(store, repo, job=partial.value.details["job_id"])
    complete_claim = store.one(
        "SELECT coverage_state,observed_at_us FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='threads'"
    )
    assert complete_claim["coverage_state"] == "complete"
    assert complete_claim["observed_at_us"] > partial_claim["observed_at_us"]
    assert (
        complete_claim["observed_at_us"]
        == store.one(
            "SELECT MAX(o.observed_at_us) FROM (SELECT fetch_collection_id,observed_at_us FROM fetch_occurrences UNION ALL SELECT fetch_collection_id,observed_at_us FROM current_collection_pages) o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE f.change_request_id='00000000-0000-4000-8000-000000000301:41' AND f.kind IN ('threads','thread-comments')"
        )[0]
    )
    assert child_requests == ["100", "100"]
    assert (
        store.one(
            "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
            (child["fetch_collection_id"],),
        )[0]
        == "complete"
    )
    assert (
        store.one(
            "SELECT count(*) FROM fetch_occurrences o JOIN fetch_collections f ON f.fetch_collection_id=o.fetch_collection_id WHERE f.kind='threads'"
        )[0]
        == root_pages
    )


def test_malformed_current_rest_page_keeps_retry_boundary_without_required_archive(
    github_runtime,
):
    store, repo, fixture, api = github_runtime
    original = api.route
    requests = 0
    path = "/repos/fixture/alpha/pulls/41/reviews"
    rejected = {"malformed": "original synthetic response"}

    def route(method, requested, params, body):
        nonlocal requests
        if requested == path:
            requests += 1
            if requests == 1:
                return rejected, {}
        return original(method, requested, params, body)

    api.route = route
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    row = store.one(
        "SELECT f.fetch_collection_id,p.cursor,p.state,p.reason FROM fetch_collections f JOIN collection_progress p ON p.fetch_collection_id=f.fetch_collection_id WHERE f.change_request_id='00000000-0000-4000-8000-000000000301:41' AND f.kind='review'"
    )
    assert row["state"] == "partial"
    assert row["reason"] == "API_SCHEMA"
    assert row["cursor"] is None
    assert not store.one(
        "SELECT 1 FROM current_collection_pages WHERE fetch_collection_id=?",
        (row["fetch_collection_id"],),
    )
    assert not store.one(
        "SELECT 1 FROM fetch_occurrences WHERE fetch_collection_id=?",
        (row["fetch_collection_id"],),
    )
    assert not store.one(
        "SELECT 1 FROM review_resources WHERE kind='review' AND change_request_id='00000000-0000-4000-8000-000000000301:41'"
    )
    assert not (store.path / "transport-archive").exists()
    sync(store, repo, job=partial.value.details["job_id"])
    assert requests == 2
    assert (
        store.one(
            "SELECT count(*) FROM current_collection_pages WHERE fetch_collection_id=?",
            (row["fetch_collection_id"],),
        )[0]
        == 1
    )
    assert (
        store.one(
            "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
            (row["fetch_collection_id"],),
        )[0]
        == "complete"
    )


def test_changed_observed_permission_scope_refreshes_complete_listings(github_runtime):
    store, repo, fixture, api = github_runtime
    original = api.route
    permission = "repo"

    def route(method, path, params, body):
        value, headers = original(method, path, params, body)
        if path == "/user":
            headers["X-OAuth-Scopes"] = permission
        return value, headers

    api.route = route
    sync(store, repo)
    first = len(api.requests)
    permission = "read:org,repo"
    sync(store, repo)
    assert (
        len(
            [
                path
                for _, path, _ in api.requests[first:]
                if path.endswith(("/commits", "/files"))
            ]
        )
        == 6
    )
    scopes = {
        tuple(json.loads(row[0])["permissions"])
        for row in store.all("SELECT request_context FROM resume_scopes")
    }
    assert scopes == {
        ("repo",),
        ("read:org", "repo"),
    }
    assert (
        store.one("SELECT count(*) FROM code_listing_progress WHERE state='complete'")[
            0
        ]
        == 12
    )


@pytest.mark.parametrize("child_page", [False, True], ids=["root-page", "child-page"])
def test_missing_graphql_database_id_retains_page_and_resumes_without_node_alias(
    github_runtime, child_page
):
    store, repo, fixture, api = github_runtime
    api.reply_count = 101 if child_page else 1
    original = api.route
    enabled = True
    rejected_nodes = []

    def route(method, path, params, body):
        result, headers = original(method, path, params, body)
        if enabled and method == "POST":
            variables = body["variables"]
            if (
                child_page
                and "thread" in variables
                and variables["thread"].startswith("THREAD41-")
            ):
                comment = result["data"]["node"]["comments"]["nodes"][0]
            elif not child_page and variables.get("number") == 41:
                comment = result["data"]["repository"]["pullRequest"]["reviewThreads"][
                    "nodes"
                ][0]["comments"]["nodes"][0]
            else:
                return result, headers
            rejected_nodes.append(comment["id"])
            comment["fullDatabaseId"] = None
        return result, headers

    api.route = route
    with pytest.raises(CatalogError) as partial:
        sync(store, repo)
    assert rejected_nodes
    if child_page:
        failed_child = store.one(
            "SELECT p.fetch_collection_id,p.state,p.cursor,p.reason FROM collection_progress p "
            "JOIN fetch_collections f USING(fetch_collection_id) "
            "WHERE f.kind='thread-comments' AND f.change_request_id='00000000-0000-4000-8000-000000000301:41'"
        )
        assert (
            failed_child["state"],
            failed_child["cursor"],
            failed_child["reason"],
        ) == ("partial", "100", "CANONICAL_DOCUMENT_ID_MISSING")
        assert not store.one(
            "SELECT 1 FROM current_collection_pages WHERE fetch_collection_id=?",
            (failed_child["fetch_collection_id"],),
        )
        assert not store.one(
            "SELECT 1 FROM fetch_occurrences WHERE fetch_collection_id=?",
            (failed_child["fetch_collection_id"],),
        )
    else:
        assert (
            store.one(
                "SELECT count(*) FROM unresolved_payloads WHERE reason LIKE '%CANONICAL_DOCUMENT_ID_MISSING%'"
            )[0]
            > 0
        )
    for node in rejected_nodes:
        assert not store.one(
            "SELECT 1 FROM review_resources WHERE provider_change_request_document_id=?",
            (node,),
        )
        if not child_page:
            assert any(
                node.encode() in row[0]
                for row in store.all("SELECT body FROM stored_bytes")
            )
    enabled = False
    sync(store, repo, job=partial.value.details["job_id"])
    assert (
        store.one(
            "SELECT count(*) FROM eligible_review_resources WHERE kind='review-comment' AND change_request_id='00000000-0000-4000-8000-000000000301:41' AND review_thread_provider_resource_id='THREAD41-0'"
        )[0]
        == api.reply_count
    )
    assert not store.all("PRAGMA foreign_key_check")


@pytest.mark.parametrize("boundary", ["root", "nested-initial", "nested-child"])
@pytest.mark.parametrize(
    "malformation",
    [
        "missing-nodes",
        "null-nodes",
        "mapping-nodes",
        "empty-page-info",
        "null-has-next",
        "integer-has-next",
        "missing-next-cursor",
    ],
)
def test_malformed_graphql_connections_are_partial_and_retryable(
    github_runtime, boundary, malformation
):
    store, repo, fixture, api = github_runtime
    pr = {
        "change_request_id": "00000000-0000-4000-8000-000000000301:41",
        "provider_change_request_number": 41,
    }
    with store.transaction():
        store.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES('00000000-0000-4000-8000-000000000301:41','00000000-0000-4000-8000-000000000301','binding','pull_request',41)"
        )
    if boundary == "nested-child":
        api.reply_count = 101
    original = api.route
    malformed_response = None

    def route(method, path, params, body):
        nonlocal malformed_response
        value, headers = original(method, path, params, body)
        if method != "POST":
            return value, headers
        child = "thread" in body["variables"]
        if child != (boundary == "nested-child"):
            return value, headers
        if child:
            connection = value["data"]["node"]["comments"]
        else:
            connection = value["data"]["repository"]["pullRequest"]["reviewThreads"]
            if boundary == "nested-initial":
                connection = connection["nodes"][0]["comments"]
        if malformation == "missing-nodes":
            connection.pop("nodes")
        elif malformation == "null-nodes":
            connection["nodes"] = None
        elif malformation == "mapping-nodes":
            connection["nodes"] = {}
        elif malformation == "empty-page-info":
            connection["pageInfo"] = {}
        elif malformation == "null-has-next":
            connection["pageInfo"]["hasNextPage"] = None
        elif malformation == "integer-has-next":
            connection["pageInfo"]["hasNextPage"] = 0
        else:
            connection["pageInfo"] = {"hasNextPage": True, "endCursor": None}
        malformed_response = value
        return value, headers

    api.route = route
    jobs = JobService(store)
    job = jobs.create("sync", {"kind": "pr"})
    collector = GitHubCollector(store, CancellationToken())
    collector.facts.principal = "fixture"
    try:
        with pytest.raises(CatalogError) as raised:
            collector.threads(repo, pr, job)
        assert raised.value.code == "API_SCHEMA"
    finally:
        collector.http.close()
    assert malformed_response is not None
    if boundary == "nested-child":
        failed_child = store.one(
            "SELECT p.fetch_collection_id,p.state,p.cursor,p.reason FROM collection_progress p "
            "JOIN fetch_collections f USING(fetch_collection_id) WHERE f.kind='thread-comments'"
        )
        assert (
            failed_child["state"],
            failed_child["cursor"],
            failed_child["reason"],
        ) == ("partial", "100", "API_SCHEMA")
        assert not store.one(
            "SELECT 1 FROM current_collection_pages WHERE fetch_collection_id=?",
            (failed_child["fetch_collection_id"],),
        )
        assert not store.one(
            "SELECT 1 FROM fetch_occurrences WHERE fetch_collection_id=?",
            (failed_child["fetch_collection_id"],),
        )
        assert (
            store.one(
                "SELECT count(*) FROM eligible_review_resources WHERE kind='review-comment'"
            )[0]
            == 100
        )
    else:
        assert any(
            json.loads(row["body"]) == malformed_response
            for row in store.all(
                "SELECT b.body FROM unresolved_payloads u JOIN payloads p ON p.representation=u.payload_representation AND p.sha256=u.payload_sha256 JOIN stored_bytes b ON b.sha256=p.sha256"
            )
        )
    assert (
        store.one(
            "SELECT coverage_state FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='threads'"
        )[0]
        == "partial"
    )
    assert not store.one(
        "SELECT 1 FROM fetch_collections f JOIN completion_markers c ON c.fetch_collection_id=f.fetch_collection_id WHERE f.kind IN ('threads','thread-comments')"
    )
    jobs.update(job, "waiting")
    jobs.resume(job)
    api.route = original
    collector = GitHubCollector(store, CancellationToken())
    collector.facts.principal = "fixture"
    try:
        collector.threads(repo, pr, job)
    finally:
        collector.http.close()
    assert (
        store.one(
            "SELECT coverage_state FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='threads'"
        )[0]
        == "complete"
    )
    assert not store.all("PRAGMA foreign_key_check")


def test_git_ref_race_records_partial_code_and_repository_coverage(github_runtime):
    store, repo, fixture, api = github_runtime
    sync(store, repo)

    fixture.alpha.commit(
        "Q",
        {**fixture.m, b"pr-only.txt": b"new-pr-code"},
        ("P",),
    )
    expected = fixture.alpha.commits["Q"]
    api.prs[41]["head"]["sha"] = expected
    original = api.route

    def route(method, path, params, body):
        if path == "/repos/fixture/alpha/pulls/41/commits":
            return [{"sha": expected}], {}
        return original(method, path, params, body)

    api.route = route
    # The API consistently observes Q while the Git PR ref still resolves to N.
    fixture.alpha.ref("refs/pull/41/head", "N")

    with pytest.raises(CatalogError):
        sync(store, repo)

    pr_code = store.one(
        "SELECT coverage_state,observed_at_us FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='pr-code'"
    )
    repository = store.one(
        "SELECT coverage_state,observed_at_us FROM current_coverage WHERE repository_uuidv4='00000000-0000-4000-8000-000000000301' AND change_request_id IS NULL AND kind='pr'"
    )
    assert pr_code["coverage_state"] == "partial"
    assert repository["coverage_state"] == "partial"

    code = store.one(
        "SELECT c.* FROM current_code_observations c JOIN current_change_request_observations p ON p.change_request_id=c.change_request_id WHERE c.change_request_id='00000000-0000-4000-8000-000000000301:41' AND c.change_request_observation_id=p.change_request_observation_id ORDER BY c.code_observation_id DESC LIMIT 1"
    )
    details = json.loads(code["details"])
    assert details["expected_roles"]["head"] == expected
    assert not store.one(
        "SELECT 1 FROM code_acquisitions WHERE code_observation_id=? AND role='head'",
        (code["code_observation_id"],),
    )
    assert not store.one(
        "SELECT 1 FROM git_objects WHERE oid=?",
        (bytes.fromhex(expected),),
    )


def test_graphql_page_info_requires_boolean_has_next_page(github_runtime):
    store, repo, fixture, api = github_runtime
    original = api.route
    injected = False

    def route(method, path, params, body):
        nonlocal injected
        payload, headers = original(method, path, params, body)
        if (
            not injected
            and method == "POST"
            and body["variables"].get("number") == 41
            and "thread" not in body["variables"]
        ):
            injected = True
            payload["data"]["repository"]["pullRequest"]["reviewThreads"][
                "pageInfo"
            ] = {}
        return payload, headers

    api.route = route
    with pytest.raises(CatalogError):
        sync(store, repo)

    thread_coverage = store.one(
        "SELECT coverage_state FROM current_coverage WHERE change_request_id='00000000-0000-4000-8000-000000000301:41' AND kind='threads'"
    )
    assert thread_coverage["coverage_state"] == "partial"
