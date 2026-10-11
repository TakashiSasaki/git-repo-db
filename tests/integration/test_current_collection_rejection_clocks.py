"""Current collection rejection clocks survive retries without transport bytes."""

import copy
from contextlib import contextmanager

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime

MARKER = "CURRENT_REJECTED_TRANSPORT_MARKER_20261010"


def seed_pr(store, repo):
    identifier = repo["repository_uuidv4"] + ":41"
    with store.transaction():
        store.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,"
            "repository_binding_id,change_request_kind,provider_change_request_number) "
            "VALUES(?,?,'binding','pull_request',41)",
            (identifier, repo["repository_uuidv4"]),
        )
    return identifier


def new_job(store, kind="pr"):
    identifier = JobService(store).create("sync", {"kind": kind})
    store.expected_attempt = 1
    return identifier


def resume_job(store, job):
    jobs = JobService(store)
    jobs.update(job, "waiting")
    jobs.resume(job)
    store.expected_attempt = store.one(
        "SELECT current_attempt FROM jobs WHERE job_id=?", (job,)
    )[0]


@contextmanager
def mock_collector(store, responder, clock):
    config = copy.deepcopy(store.config["github"])
    config["max_attempts"] = 1
    token = CancellationToken()
    with httpx.Client(transport=httpx.MockTransport(responder)) as client:
        transport = GitHubTransport(
            config, token, client=client, clock_us=lambda: clock[0]
        )
        current = GitHubCollector(store, token, transport=transport, config=config)
        current.facts.principal = "fixture"
        yield current


def assert_no_original(store):
    for table in (
        "stored_bytes",
        "payloads",
        "payload_admission_staging",
        "fetch_occurrences",
        "source_input_observations",
        "unresolved_payloads",
    ):
        assert store.one(f"SELECT count(*) FROM {table}")[0] == 0, table
    for (table,) in store.all("SELECT name FROM sqlite_schema WHERE type='table'"):
        quoted = '"' + table.replace('"', '""') + '"'
        for row in store.all("SELECT * FROM " + quoted):
            for value in row:
                if isinstance(value, (bytes, str)):
                    assert MARKER.encode() not in (
                        value.encode() if isinstance(value, str) else value
                    ), table
    assert not (store.path / "transport-archive").exists()
    assert store.all("PRAGMA foreign_key_check") == []


@pytest.mark.parametrize("retry_us", [175, 200, 300])
@pytest.mark.parametrize("family", ["review", "issue"])
def test_known_current_resource_rejection_preserves_latest_candidate_set(
    github_runtime, retry_us, family
):
    store, repo, _, api = github_runtime
    pr = seed_pr(store, repo)
    path = (
        "/repos/fixture/alpha/pulls/41/reviews"
        if family == "review"
        else "/repos/fixture/alpha/issues"
    )
    endpoint = api.url + path
    clock, mode, requested = [100], ["initial"], []

    def response(request):
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 10})
        assert request.url.path == path
        page = request.url.params.get("page", "1")
        requested.append((mode[0], page))
        if mode[0] == "initial":
            clock[0] = 100
            return httpx.Response(200, json=[])
        if page == "1":
            clock[0] = 150
            return httpx.Response(
                200, json=[], headers={"Link": f'<{endpoint}?page=2>; rel="next"'}
            )
        clock[0] = 200 if mode[0] == "rejected" else retry_us
        return httpx.Response(
            200,
            json=[{"id": 2, "number": 2, "body": [], "transport_only": MARKER}]
            if mode[0] == "rejected"
            else [],
        )

    with mock_collector(store, response, clock) as current:

        def collect(job):
            if family == "issue":
                return current.sync_issues(repo, job)
            return current.current_collection(
                repo, pr, "review", job, endpoint, current_parser.review
            )

        initial = new_job(store, family)
        collect(initial)
        JobService(store).update(initial, "complete")
        mode[0] = "rejected"
        interrupted = new_job(store, family)
        with pytest.raises(CatalogError) as error:
            collect(interrupted)
        assert error.value.code == (
            "ISSUE_PARTIAL" if family == "issue" else "API_SCHEMA"
        )
        assert tuple(
            store.one(
                "SELECT observed_at_us,coverage_state FROM current_coverage WHERE kind=?",
                (family,),
            )
        ) == (200, "partial")
        rejection = store.one(
            "SELECT observed_at_us,evidence FROM completion_markers WHERE asserted_state='partial'"
        )
        assert rejection["observed_at_us"] == 200
        assert_no_original(store)
        resume_job(store, interrupted)
        mode[0] = "retry"
        collect(interrupted)
        expected = (
            (200, "partial" if retry_us < 200 else "conflict")
            if retry_us <= 200
            else (300, "complete")
        )
        assert (
            tuple(
                store.one(
                    "SELECT observed_at_us,coverage_state FROM current_coverage WHERE kind=?",
                    (family,),
                )
            )
            == expected
        )
        completed = store.all(
            "SELECT c.observed_at_us FROM completion_markers c JOIN collection_progress p "
            "USING(fetch_collection_id) WHERE p.job_id=? AND c.asserted_state='complete'",
            (interrupted,),
        )
        assert [row[0] for row in completed] == [retry_us]
        complete_claims = store.all(
            "SELECT observed_at_us FROM coverage_claims c JOIN coverage_scopes s USING(coverage_scope_id) "
            "WHERE s.kind=? AND coverage_state='complete' AND observed_at_us>100",
            (family,),
        )
        assert {row[0] for row in complete_claims} == (
            set() if retry_us < 200 else {retry_us}
        )
        assert requested == [
            ("initial", "1"),
            ("rejected", "1"),
            ("rejected", "2"),
            ("retry", "2"),
        ]
        assert_no_original(store)


@pytest.mark.parametrize(
    "rejected",
    [
        b"{invalid JSON " + MARKER.encode(),
        {"id": 2, "body": [], "transport_only": MARKER},
        {"errors": [MARKER]},
        [{"body": [], "transport_only": MARKER}],
        [{"id": "node:2", "body": [], "transport_only": MARKER}],
    ],
    ids=["raw-json", "nonlist-resource", "error-envelope", "missing-id", "node-id"],
)
def test_unidentified_current_response_adds_no_domain_observation(
    github_runtime, rejected
):
    store, repo, _, api = github_runtime
    pr = seed_pr(store, repo)
    endpoint = api.url + "/repos/fixture/alpha/pulls/41/reviews"
    clock, mode = [100], ["empty"]

    def response(request):
        if mode[0] == "empty":
            return httpx.Response(200, json=[])
        return (
            httpx.Response(200, content=rejected)
            if isinstance(rejected, bytes)
            else httpx.Response(200, json=rejected)
        )

    with mock_collector(store, response, clock) as current:

        def collect(job):
            current.current_collection(
                repo, pr, "review", job, endpoint, current_parser.review
            )

        initial = new_job(store)
        collect(initial)
        JobService(store).update(initial, "complete")
        mode[0], clock[0] = "rejected", 200
        with pytest.raises(CatalogError):
            collect(new_job(store))
        assert tuple(
            store.one(
                "SELECT observed_at_us,coverage_state FROM current_coverage WHERE kind='review'"
            )
        ) == (100, "complete")
        assert not store.one(
            "SELECT 1 FROM completion_markers WHERE asserted_state='partial'"
        )
        assert_no_original(store)


def test_out_of_scope_incremental_current_parent_adds_no_observation(github_runtime):
    store, repo, _, api = github_runtime
    seed_pr(store, repo)
    clock = [200]

    def response(request):
        return httpx.Response(
            200,
            json=[
                {
                    "id": 2,
                    "body": "exact",
                    "transport_only": MARKER,
                    "pull_request_url": api.url + "/repos/other/repository/pulls/41",
                }
            ],
        )

    with mock_collector(store, response, clock) as current:
        with pytest.raises(CatalogError) as error:
            current.current_incremental_reviews(
                repo, new_job(store), api.url + "/repos/fixture/alpha/pulls/comments"
            )
        assert error.value.code == "SCOPE_MISMATCH"
        assert not store.one("SELECT 1 FROM coverage_claims")
        assert not store.one("SELECT 1 FROM completion_markers")
        assert not store.one("SELECT 1 FROM incremental_scans")
        assert_no_original(store)


def test_current_terminal_cancellation_finishes_locally_without_false_partial(
    github_runtime, monkeypatch
):
    store, repo, _, api = github_runtime
    pr = seed_pr(store, repo)
    endpoint = api.url + "/repos/fixture/alpha/pulls/41/reviews"
    clock, requested = [100], []

    def response(request):
        requested.append(request.url.path)
        return httpx.Response(200, json=[])

    def interrupt(phase):
        if phase == "after_api_page_commit":
            raise CatalogError("CANCELLED", "Committed terminal receipt")

    with mock_collector(store, response, clock) as current:
        monkeypatch.setattr("repo_catalog.adapters.git.runner.hook", interrupt)
        job = new_job(store)
        with pytest.raises(CatalogError, match="Committed terminal"):
            current.current_collection(
                repo, pr, "review", job, endpoint, current_parser.review
            )
        assert not store.one("SELECT 1 FROM coverage_claims")
        assert not store.one("SELECT 1 FROM completion_markers")
        resume_job(store, job)
        clock[0] = 300
        monkeypatch.setattr("repo_catalog.adapters.git.runner.hook", lambda phase: None)
        current.current_collection(
            repo, pr, "review", job, endpoint, current_parser.review
        )
        assert len(requested) == 1
        assert tuple(
            store.one(
                "SELECT observed_at_us,coverage_state FROM current_coverage WHERE kind='review'"
            )
        ) == (100, "complete")
        assert store.one("SELECT observed_at_us FROM completion_markers")[0] == 100
        assert_no_original(store)


def test_current_stale_attempt_cannot_publish_response_or_failure_boundary(
    github_runtime, monkeypatch
):
    store, repo, _, api = github_runtime
    pr = seed_pr(store, repo)
    clock = [200]
    job = new_job(store)

    def response(request):
        return httpx.Response(
            200, json=[{"id": 2, "body": "exact", "state": "APPROVED"}]
        )

    def obsolete(phase):
        if phase == "before_api_page_commit":
            JobService(store).resume(job)

    with mock_collector(store, response, clock) as current:
        monkeypatch.setattr("repo_catalog.adapters.git.runner.hook", obsolete)
        with pytest.raises(CatalogError) as error:
            current.current_collection(
                repo,
                pr,
                "review",
                job,
                api.url + "/repos/fixture/alpha/pulls/41/reviews",
                current_parser.review,
            )
        assert error.value.code == "STALE_ATTEMPT"
        for table in (
            "current_collection_pages",
            "review_resources",
            "text_bodies",
            "coverage_claims",
            "completion_markers",
        ):
            assert store.one(f"SELECT count(*) FROM {table}")[0] == 0, table
        assert_no_original(store)


def test_current_rejected_page_rolls_back_every_member_but_keeps_clock(github_runtime):
    store, repo, _, api = github_runtime
    pr = seed_pr(store, repo)
    clock = [200]

    def response(request):
        return httpx.Response(
            200,
            json=[
                {"id": 1, "body": "committed nowhere", "state": "APPROVED"},
                {"id": 2, "body": [], "transport_only": MARKER},
            ],
        )

    with mock_collector(store, response, clock) as current:
        with pytest.raises(CatalogError) as error:
            current.current_collection(
                repo,
                pr,
                "review",
                new_job(store),
                api.url + "/repos/fixture/alpha/pulls/41/reviews",
                current_parser.review,
            )
        assert error.value.code == "API_SCHEMA"
        for table in ("current_collection_pages", "review_resources", "text_bodies"):
            assert store.one(f"SELECT count(*) FROM {table}")[0] == 0, table
        assert tuple(
            store.one(
                "SELECT observed_at_us,coverage_state FROM current_coverage WHERE kind='review'"
            )
        ) == (200, "partial")
        assert_no_original(store)


def test_issue_summary_does_not_borrow_another_sources_clock(github_runtime):
    store, repo, _, api = github_runtime
    with store.transaction():
        store.execute(
            "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,"
            "discovery_kind,name,settings) VALUES('other-source',"
            "'00000000-0000-4000-8000-000000000202',"
            "'00000000-0000-4000-8000-000000000101','github_inventory','other','{\"owner\":\"fixture\"}')"
        )
        store.execute(
            "INSERT INTO source_repositories(source_id,repository_uuidv4,first_seen_us,last_seen_us) "
            "VALUES('other-source',?,NULL,NULL)",
            (repo["repository_uuidv4"],),
        )
    job = new_job(store, "issue")
    clock = [900]

    def response(request):
        return httpx.Response(
            200, json={"id": 10} if request.url.path == "/user" else []
        )

    with mock_collector(store, response, clock) as current:
        current.current_collection(
            {**repo, "source_id": "other-source"},
            None,
            "issue",
            job,
            api.url + "/repos/fixture/alpha/issues",
            current_parser.issue,
        )
        prior = [tuple(row) for row in store.all("SELECT * FROM coverage_claims")]
        clock[0] = 100
        current.sync_issues(repo, job)
        # A stale but successful scan of this Source cannot lend itself the other
        # Source's 900 clock to manufacture an equal-time complete assessment.
        assert [
            tuple(row) for row in store.all("SELECT * FROM coverage_claims")
        ] == prior
        assert {
            row[0]
            for row in store.all("SELECT observed_at_us FROM current_collection_pages")
        } == {100, 900}
        assert_no_original(store)


def test_current_incremental_watermark_stays_at_original_scan_start(
    github_runtime, monkeypatch
):
    store, repo, _, api = github_runtime
    seed_pr(store, repo)
    endpoint = api.url + "/repos/fixture/alpha/pulls/comments"
    clock, blocked, requested = [100], [True], []
    monkeypatch.setattr(
        "repo_catalog.adapters.github.persistence.now_us", lambda: clock[0]
    )

    def response(request):
        page = request.url.params.get("page", "1")
        requested.append(page)
        if page == "1":
            clock[0] = 150
            return httpx.Response(
                200, json=[], headers={"Link": f'<{endpoint}?page=2>; rel="next"'}
            )
        clock[0] = 200 if blocked[0] else 300
        return httpx.Response(
            200,
            json=[
                {
                    "id": 2,
                    "body": [],
                    "transport_only": MARKER,
                    "pull_request_url": api.url + "/repos/fixture/alpha/pulls/41",
                }
            ]
            if blocked[0]
            else [],
        )

    with mock_collector(store, response, clock) as current:
        job = new_job(store)
        with pytest.raises(CatalogError):
            current.current_incremental_reviews(repo, job, endpoint)
        assert not store.one("SELECT 1 FROM incremental_scans")
        assert tuple(
            store.one(
                "SELECT observed_at_us,coverage_state FROM current_coverage WHERE kind='review-comment-incremental'"
            )
        ) == (200, "partial")
        resume_job(store, job)
        blocked[0] = False
        current.current_incremental_reviews(repo, job, endpoint)
        assert requested == ["1", "2", "2"]
        assert tuple(
            store.one(
                "SELECT scan_started_at_us,safe_watermark_us FROM incremental_scans"
            )
        ) == (100, 100)
        assert (
            store.one(
                "SELECT observed_at_us FROM completion_markers WHERE asserted_state='complete'"
            )[0]
            == 300
        )
        assert_no_original(store)


@pytest.mark.parametrize("invalid_clock", [True, False, 1.5, 1 << 63, -(1 << 63) - 1])
def test_invalid_response_clock_cannot_become_rejected_observation(
    github_runtime, monkeypatch, invalid_clock
):
    store, repo, _, api = github_runtime
    pr = seed_pr(store, repo)
    clock = [100]

    with mock_collector(
        store, lambda request: httpx.Response(200, json=[]), clock
    ) as current:
        # Normal transport validates/owns its clock. A malformed injected
        # adapter response still cannot coerce a Boolean/float into domain time.
        monkeypatch.setattr(
            current,
            "request_get",
            lambda *args, **kwargs: httpx.Response(
                200,
                json=[{"id": 2, "body": [], "transport_only": MARKER}],
                extensions={"catalog_observed_at_us": invalid_clock},
            ),
        )
        with pytest.raises(CatalogError):
            current.current_collection(
                repo,
                pr,
                "review",
                new_job(store),
                api.url + "/repos/fixture/alpha/pulls/41/reviews",
                current_parser.review,
            )
        assert not store.one("SELECT 1 FROM completion_markers")
        assert not store.one("SELECT 1 FROM coverage_claims")
        assert_no_original(store)
