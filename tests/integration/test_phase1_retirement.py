"""Independent rejection checks: retry live inputs without retaining originals.

These probes concern rejected responses only. Successful historical publication,
thread-root restart and conditional reuse retain their separately declared
Phase-2 dependencies. Supplementary transport recording is disabled throughout.
"""

import base64
import copy
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from urllib.parse import parse_qs

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.sqlite.cas_integrity import stage_verified_payload
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from repo_catalog.domain.payload import PayloadRef
from tests.support.github_runtime import github_runtime as github_runtime
from tests.support.sqlite_contracts import assert_absent_tables

MARKER = "phase1_transport_only_rejected_original_8a016d73c1f542669eb804aa"
DOMAIN_BODY = "retained domain text\r\n認証 🦉"


def marker_encodings():
    raw = MARKER.encode()
    yield raw, False
    yield raw.hex().encode(), True
    # A marker may begin at any offset within a whole Base64-encoded response.
    # Each aligned interior has complete triplets and therefore no padding.
    for offset in range(3):
        interior = raw[offset:]
        interior = interior[: len(interior) // 3 * 3]
        yield base64.b64encode(interior), False


def assert_marker_absent(store):
    """Inspect every persisted cell, including BLOBs and encoded envelopes."""
    needles = list(marker_encodings())
    for (table,) in store.all(
        "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
    ):
        quoted = '"' + table.replace('"', '""') + '"'
        for row in store.all("SELECT * FROM " + quoted):
            for value in row:
                if not isinstance(value, (bytes, str)):
                    continue
                raw = value.encode() if isinstance(value, str) else value
                for needle, folded in needles:
                    assert needle not in (raw.lower() if folded else raw), table
    # SQLite cells were checked above; old physical freelist/journal contents
    # are not an authorized GC contract. Other files cannot hide a new store.
    catalog_files = {
        "catalog.sqlite3",
        "catalog.sqlite3-wal",
        "catalog.sqlite3-shm",
        "catalog.sqlite3-journal",
    }
    for path in store.path.rglob("*"):
        if not path.is_file() or path.name in catalog_files:
            continue
        raw = path.read_bytes()
        for needle, folded in needles:
            assert needle not in (raw.lower() if folded else raw), path
    assert not (store.path / "transport-archive").exists()


def assert_no_raw_intake(store):
    assert_absent_tables(
        store.connection, "fetch_occurrences", "source_input_observations"
    )
    for table in (
        "stored_bytes",
        "payloads",
        "payload_admission_staging",
        "unresolved_payloads",
    ):
        assert store.one(f"SELECT count(*) FROM {table}")[0] == 0, table
    assert_marker_absent(store)


def registered_pr(store, repo):
    identifier = repo["repository_uuidv4"] + ":41"
    with store.transaction():
        store.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,"
            "repository_binding_id,change_request_kind,provider_change_request_number) "
            "VALUES(?,?,'binding','pull_request',41)",
            (identifier, repo["repository_uuidv4"]),
        )
    return {
        "change_request_id": identifier,
        "provider_change_request_number": 41,
    }


def new_job(store):
    identifier = JobService(store).create("sync", {"kind": "pr"})
    store.expected_attempt = 1
    return identifier


def resume_job(store, identifier, reason):
    jobs = JobService(store)
    jobs.update(identifier, "waiting", reason)
    jobs.resume(identifier)
    store.expected_attempt = store.one(
        "SELECT current_attempt FROM jobs WHERE job_id=?", (identifier,)
    )[0]


@contextmanager
def collector_for(store, responder, clock):
    config = copy.deepcopy(store.config["github"])
    assert not config["record_messages"]
    config["max_attempts"] = 1
    token = CancellationToken()
    with httpx.Client(transport=httpx.MockTransport(responder)) as client:
        transport = GitHubTransport(
            config, token, client=client, clock_us=lambda: clock[0]
        )
        collector = GitHubCollector(store, token, transport=transport, config=config)
        collector.facts.principal = "fixture"
        yield collector


def rejected_collection(store, kind):
    row = store.one(
        "SELECT f.*,p.state,p.cursor,p.reason FROM fetch_collections f "
        "JOIN collection_progress p USING(fetch_collection_id) WHERE f.kind=? "
        "ORDER BY f.observed_at_us DESC LIMIT 1",
        (kind,),
    )
    assert row is not None and row["state"] == "partial"
    assert (
        store.one(
            "SELECT count(*) FROM completion_markers WHERE fetch_collection_id=? "
            "AND asserted_state='complete'",
            (row["fetch_collection_id"],),
        )[0]
        == 0
    )
    return row


@pytest.mark.parametrize(
    "boundary", ["pr-list", "pr-detail", "pr-code-check", "issue-comment"]
)
@pytest.mark.parametrize("failure", ["schema", "json"])
def test_rejected_rest_original_is_absent_and_retry_makes_a_new_request(
    github_runtime, boundary, failure
):
    store, repo, _, api = github_runtime
    pr = registered_pr(store, repo)
    job = new_job(store)
    path = "/repos/fixture/alpha/pulls/41"
    if boundary == "issue-comment":
        path = "/repos/fixture/alpha/issues/41/comments"
    url = api.url + path
    requests, blocked, clock = [], [True], [200]
    valid = (
        {"id": 501, "body": DOMAIN_BODY}
        if boundary == "issue-comment"
        else {**api.prs[41], "body": DOMAIN_BODY}
    )

    def response(request):
        assert request.method == "GET"
        requests.append(str(request.url))
        if blocked[0]:
            if failure == "json":
                return httpx.Response(200, content=b"{" + MARKER.encode() + b"]")
            invalid = {
                **valid,
                ("body" if boundary == "issue-comment" else "title"): [],
                "unmodeled_transport_marker": MARKER,
            }
            return httpx.Response(
                200,
                json=[invalid] if boundary in ("pr-list", "issue-comment") else invalid,
                headers={"Link": f'<{url}?page=999>; rel="next"'},
            )
        return httpx.Response(
            200,
            json=[valid] if boundary in ("pr-list", "issue-comment") else valid,
        )

    with collector_for(store, response, clock) as collector:

        def acquire():
            if boundary == "pr-detail":
                return collector.detail(repo, pr, job, url)
            if boundary == "pr-code-check":
                return collector.code_check(repo, pr, job, url, 0)
            normalizer = (
                collector._document_normalizer(
                    repo, pr["change_request_id"], boundary, url
                )
                if boundary == "issue-comment"
                else lambda value, collection, occurrence, position, timestamp, listing: (
                    collector.ensure_pr(
                        repo, value, collection, occurrence, position, timestamp
                    )[1]
                )
            )
            return collector.collection(
                repo,
                pr["change_request_id"] if boundary == "issue-comment" else None,
                boundary,
                job,
                url,
                normalizer,
            )

        with pytest.raises(CatalogError) as raised:
            acquire()
        assert raised.value.code == "API_SCHEMA"
        failed = rejected_collection(store, boundary)
        assert failed["cursor"] in (None, url)
        assert_no_raw_intake(store)
        assert store.one("SELECT count(*) FROM document_state")[0] == 0
        assert store.one("SELECT count(*) FROM change_request_state")[0] == 0
        resume_job(store, job, raised.value.code)
        blocked[0], clock[0] = False, 300
        acquire()
    assert requests == [url, url]
    state = store.one(
        "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
        (failed["fetch_collection_id"],),
    )[0]
    assert state == "complete"
    assert_absent_tables(store.connection, "fetch_occurrences")
    assert store.one("SELECT count(*) FROM payload_admission_staging")[0] == 0
    assert store.one("SELECT count(*) FROM unresolved_payloads")[0] == 0
    assert store.one("SELECT body FROM text_bodies WHERE body=?", (DOMAIN_BODY,))
    assert_marker_absent(store)


@pytest.mark.parametrize("failure", ["parser", "catalog"])
def test_current_rejection_cannot_hide_an_original_in_errors_or_files(
    github_runtime, failure
):
    store, repo, _, api = github_runtime
    pr = registered_pr(store, repo)
    job = new_job(store)
    if failure == "catalog":
        with store.transaction():
            store.execute(
                "CREATE TRIGGER synthetic_admission_failure BEFORE INSERT ON review_resources "
                "BEGIN SELECT RAISE(ABORT,'synthetic catalog rejection'); END"
            )
    value = {
        "id": 501,
        "body": [] if failure == "parser" else DOMAIN_BODY,
        "unmodeled_transport_marker": MARKER,
    }
    url = api.url + "/repos/fixture/alpha/pulls/41/reviews"
    requested = []

    def response(request):
        requested.append(str(request.url))
        return httpx.Response(200, json=[value])

    with collector_for(store, response, [200]) as collector:
        with pytest.raises(
            CatalogError if failure == "parser" else sqlite3.IntegrityError
        ):
            collector.current_collection(
                repo,
                pr["change_request_id"],
                "review",
                job,
                url,
                current_parser.review,
            )
    assert requested == [url]
    assert store.one("SELECT count(*) FROM review_resources")[0] == 0
    assert store.one("SELECT count(*) FROM current_collection_pages")[0] == 0
    assert_no_raw_intake(store)


@pytest.mark.parametrize("rejection_clock", [100, 200])
def test_observed_rest_rejection_preserves_latest_coverage_candidate_set(
    github_runtime, rejection_clock
):
    store, repo, _, api = github_runtime
    pr = registered_pr(store, repo)
    url = api.url + "/repos/fixture/alpha/issues/41/comments"
    clock, mode, requested = [100], ["empty"], []

    def response(request):
        requested.append(clock[0])
        payload = {
            "empty": [],
            "rejected": [{"id": 501, "body": [], "unmodeled_transport_marker": MARKER}],
            "corrected": [{"id": 501, "body": DOMAIN_BODY}],
        }[mode[0]]
        return httpx.Response(200, json=payload)

    with collector_for(store, response, clock) as collector:

        def acquire(job):
            return collector.collection(
                repo,
                pr["change_request_id"],
                "issue-comment",
                job,
                url,
                collector._document_normalizer(
                    repo, pr["change_request_id"], "issue-comment", url
                ),
            )

        first = new_job(store)
        acquire(first)
        JobService(store).update(first, "complete")
        assert tuple(
            store.one(
                "SELECT observed_at_us,coverage_state FROM current_coverage "
                "WHERE change_request_id=? AND kind='issue-comment'",
                (pr["change_request_id"],),
            )
        ) == (100, "complete")
        second = new_job(store)
        clock[0], mode[0] = rejection_clock, "rejected"
        with pytest.raises(CatalogError) as raised:
            acquire(second)
        assert raised.value.code == "API_SCHEMA"
        rejected_collection(store, "issue-comment")
        assert tuple(
            store.one(
                "SELECT observed_at_us,coverage_state FROM current_coverage "
                "WHERE change_request_id=? AND kind='issue-comment'",
                (pr["change_request_id"],),
            )
        ) == (rejection_clock, "conflict" if rejection_clock == 100 else "partial")
        assert_absent_tables(store.connection, "fetch_occurrences")
        assert_marker_absent(store)
        resume_job(store, second, "API_SCHEMA")
        clock[0], mode[0] = 300, "corrected"
        acquire(second)
    assert requested == [100, rejection_clock, 300]
    assert tuple(
        store.one(
            "SELECT observed_at_us,coverage_state FROM current_coverage "
            "WHERE change_request_id=? AND kind='issue-comment'",
            (pr["change_request_id"],),
        )
    ) == (300, "complete")
    assert_marker_absent(store)


def test_unknown_incremental_parent_needs_fresh_response_before_watermark(
    github_runtime,
):
    store, repo, _, api = github_runtime
    job = new_job(store)
    endpoint = api.url + "/repos/fixture/alpha/issues/comments"
    blocked, requested, clock = [True], [], [200]

    def response(request):
        requested.append(str(request.url))
        return httpx.Response(
            200,
            json=[
                {
                    "id": 501,
                    "body": DOMAIN_BODY,
                    "issue_url": api.url + "/repos/fixture/alpha/issues/41",
                    **({"unmodeled_transport_marker": MARKER} if blocked[0] else {}),
                }
            ],
        )

    with collector_for(store, response, clock) as collector:

        def acquire():
            return collector.incremental_comments(
                repo, job, "issue-comment", endpoint, "issue_url"
            )

        with pytest.raises(CatalogError) as raised:
            acquire()
        assert raised.value.code == "COMMENT_PARENT_UNKNOWN"
        failed = rejected_collection(store, "issue-comment-incremental")
        assert store.one("SELECT count(*) FROM incremental_scans")[0] == 0
        assert store.one("SELECT count(*) FROM document_state")[0] == 0
        assert_no_raw_intake(store)
        registered_pr(store, repo)
        resume_job(store, job, raised.value.code)
        blocked[0], clock[0] = False, 300
        acquire()
    assert len(requested) == 2 and requested[0] == requested[1]
    assert (
        store.one(
            "SELECT observed_at_us FROM fetch_collections WHERE fetch_collection_id=?",
            (failed["fetch_collection_id"],),
        )[0]
        == failed["observed_at_us"]
    )
    assert store.one(
        "SELECT 1 FROM completion_markers WHERE fetch_collection_id=? AND asserted_state='complete'",
        (failed["fetch_collection_id"],),
    )
    assert store.one("SELECT count(*) FROM document_state")[0] == 1
    assert_marker_absent(store)


@pytest.mark.parametrize("failure", ["shape", "json", "error-only", "rate-limit"])
def test_rejected_graphql_root_has_no_saved_original_or_fake_completion(
    github_runtime, failure
):
    store, repo, _, api = github_runtime
    pr = registered_pr(store, repo)
    job, requested, blocked, clock = new_job(store), [], [True], [200]
    empty = {
        "data": {
            "repository": {
                "pullRequest": {
                    "mergeCommit": None,
                    "potentialMergeCommit": None,
                    "reviewThreads": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    },
                }
            }
        }
    }

    def response(request):
        assert request.method == "POST" and request.url.path == "/graphql"
        requested.append(json.loads(request.content)["variables"]["cursor"])
        if not blocked[0]:
            return httpx.Response(200, json=empty)
        if failure == "json":
            return httpx.Response(200, content=b"{" + MARKER.encode() + b"]")
        if failure in ("error-only", "rate-limit"):
            return httpx.Response(
                200,
                json={
                    "errors": [
                        {
                            "message": MARKER,
                            "type": "RATE_LIMITED"
                            if failure == "rate-limit"
                            else "NOT_FOUND",
                        }
                    ]
                },
            )
        malformed = copy.deepcopy(empty)
        resource = malformed["data"]["repository"]["pullRequest"]
        resource["unmodeled_transport_marker"] = MARKER
        resource["reviewThreads"]["nodes"] = ["malformed thread"]
        return httpx.Response(200, json=malformed)

    with collector_for(store, response, clock) as collector:
        with pytest.raises(CatalogError) as raised:
            collector.threads(repo, pr, job)
        assert (
            raised.value.code
            == {
                "shape": "API_SCHEMA",
                "json": "API_SCHEMA",
                "error-only": "GRAPHQL_PARTIAL",
                "rate-limit": "RATE_LIMIT",
            }[failure]
        )
        rejected_collection(store, "threads")
        assert_no_raw_intake(store)
        claim = store.one(
            "SELECT observed_at_us,coverage_state FROM current_coverage "
            "WHERE change_request_id=? AND kind='threads'",
            (pr["change_request_id"],),
        )
        if failure == "shape":
            assert tuple(claim) == (200, "partial")
        else:
            assert claim is None
        resume_job(store, job, raised.value.code)
        blocked[0], clock[0] = False, 300
        collector.threads(repo, pr, job)
    assert requested == [None, None]
    assert store.one(
        "SELECT 1 FROM fetch_collections f JOIN collection_progress p USING(fetch_collection_id) WHERE f.kind='threads' AND p.state='complete'"
    )
    assert tuple(
        store.one(
            "SELECT observed_at_us,coverage_state FROM current_coverage "
            "WHERE change_request_id=? AND kind='threads'",
            (pr["change_request_id"],),
        )
    ) == (300, "complete")
    assert_marker_absent(store)


@pytest.mark.parametrize("failure", ["shape", "json"])
@pytest.mark.parametrize("retry_clock", [150, 200, 300])
def test_rejected_graphql_child_retries_its_safe_cursor_without_original(
    github_runtime, failure, retry_clock
):
    store, repo, _, api = github_runtime
    pr = registered_pr(store, repo)
    job, requested, blocked, clock = new_job(store), [], [True], [100]
    comments = {
        "nodes": [],
        "pageInfo": {"hasNextPage": True, "endCursor": "safe-child-cursor"},
    }
    thread = {"id": "THREAD41-0", "comments": comments}
    root = {
        "data": {
            "repository": {
                "pullRequest": {
                    "mergeCommit": None,
                    "potentialMergeCommit": None,
                    "reviewThreads": {
                        "nodes": [thread],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    },
                }
            }
        }
    }

    def response(request):
        variables = json.loads(request.content)["variables"]
        if "thread" not in variables:
            requested.append("root")
            return httpx.Response(200, json=root)
        requested.append(variables["commentCursor"])
        if blocked[0]:
            clock[0] = 200
            if failure == "json":
                return httpx.Response(200, content=b"{" + MARKER.encode() + b"]")
            return httpx.Response(
                200,
                json={
                    "data": {
                        "node": {
                            "id": "THREAD41-0",
                            "unmodeled_transport_marker": MARKER,
                            "comments": {"nodes": ["malformed comment"]},
                        }
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "node": {
                        "id": "THREAD41-0",
                        "comments": {
                            "nodes": [{"fullDatabaseId": "501", "body": DOMAIN_BODY}],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        },
                    }
                }
            },
        )

    with collector_for(store, response, clock) as collector:
        with pytest.raises(CatalogError) as raised:
            collector.threads(repo, pr, job)
        assert raised.value.code == "API_SCHEMA"
        failed = rejected_collection(store, "thread-comments")
        assert failed["cursor"] == "safe-child-cursor"
        assert_absent_tables(store.connection, "fetch_occurrences")
        # The root's known empty child prefix is normalized immediately.
        assert (
            store.one(
                "SELECT count(*) FROM current_collection_pages WHERE fetch_collection_id=?",
                (failed["fetch_collection_id"],),
            )[0]
            == 1
        )
        # The valid root remains a documented legacy restart dependency. Only
        # the rejected child's body and domain prefix must be absent.
        assert_absent_tables(store.connection, "fetch_occurrences")
        assert store.one("SELECT count(*) FROM review_resources")[0] == 0
        assert store.one("SELECT count(*) FROM payload_admission_staging")[0] == 0
        claim = store.one(
            "SELECT observed_at_us,coverage_state FROM current_coverage "
            "WHERE change_request_id=? AND kind='threads'",
            (pr["change_request_id"],),
        )
        assert tuple(claim) == (200 if failure == "shape" else 100, "partial")
        assert_marker_absent(store)
        resume_job(store, job, "API_SCHEMA")
        blocked[0], clock[0] = False, retry_clock
        collector.threads(repo, pr, job)
    assert requested == ["root", "safe-child-cursor", "safe-child-cursor"]
    assert store.one("SELECT body FROM text_bodies WHERE body=?", (DOMAIN_BODY,))
    assert tuple(
        store.one(
            "SELECT observed_at_us,coverage_state FROM current_coverage "
            "WHERE change_request_id=? AND kind='threads'",
            (pr["change_request_id"],),
        )
    ) == (
        (200, "partial" if retry_clock < 200 else "conflict")
        if failure == "shape" and retry_clock <= 200
        else (retry_clock, "complete")
    )
    marker = store.one(
        "SELECT observed_at_us FROM completion_markers WHERE fetch_collection_id=? "
        "AND asserted_state='complete'",
        (failed["fetch_collection_id"],),
    )
    assert marker[0] == retry_clock
    assert_marker_absent(store)


@pytest.mark.parametrize("retry_clock", [150, 200, 300])
def test_sync_retry_cannot_use_rejected_clock_for_complete_summary_or_code(
    github_runtime, retry_clock
):
    store, repo, _, api = github_runtime
    api.reply_count = 101
    job, blocked, clock, requested = new_job(store), [True], [50], []
    change_request_id = repo["repository_uuidv4"] + ":41"

    def response(request):
        clock[0] = 50
        body = json.loads(request.content) if request.method == "POST" else None
        variables = body["variables"] if body else {}
        if request.method == "POST" and variables.get("thread") == "THREAD41-0":
            requested.append(("child", variables["commentCursor"]))
            clock[0] = 200 if blocked[0] else retry_clock
            if blocked[0]:
                return httpx.Response(
                    200,
                    json={
                        "data": {
                            "node": {
                                "id": "THREAD41-0",
                                "unmodeled_transport_marker": MARKER,
                                "comments": {"nodes": ["malformed comment"]},
                            }
                        }
                    },
                )
        elif request.method == "POST" and variables.get("number") == 41:
            requested.append(("root", variables.get("cursor")))
            clock[0] = 100
        payload, headers = api.route(
            request.method,
            request.url.path,
            parse_qs(request.url.query.decode()),
            body,
        )
        return httpx.Response(200, json=payload, headers=headers)

    scopes = [
        ("threads", change_request_id),
        ("pr-code", change_request_id),
        ("pr", None),
    ]

    def current_claim(kind, parent):
        return tuple(
            store.one(
                "SELECT observed_at_us,coverage_state FROM current_coverage "
                "WHERE repository_uuidv4=? AND kind=? AND change_request_id IS ?",
                (repo["repository_uuidv4"], kind, parent),
            )
        )

    with collector_for(store, response, clock) as collector:
        with pytest.raises(CatalogError) as raised:
            collector.sync(repo, job)
        assert raised.value.code == "PR_PARTIAL"
        assert raised.value.details["missing"] == [
            {"kind": "threads", "reason": "API_SCHEMA"}
        ]
        for kind, parent in scopes:
            assert current_claim(kind, parent) == (200, "partial")
        assert_marker_absent(store)
        resume_job(store, job, raised.value.code)
        blocked[0] = False
        assert collector.sync(repo, job)["state"] == "complete"

    assert requested == [("root", None), ("child", "100"), ("child", "100")]
    expected = (
        (200, "partial" if retry_clock < 200 else "conflict")
        if retry_clock <= 200
        else (retry_clock, "complete")
    )
    for kind, parent in scopes:
        # Coverage admission ignores an older complete assessment. The newer
        # rejected boundary stays partial; a genuine equal-time completion
        # remains a conflict rather than a chosen winner.
        complete_clocks = {
            row[0]
            for row in store.all(
                "SELECT c.observed_at_us FROM coverage_claims c "
                "JOIN coverage_scopes s USING(coverage_scope_id) "
                "WHERE s.repository_uuidv4=? AND s.kind=? "
                "AND s.change_request_id IS ? AND c.coverage_state='complete'",
                (repo["repository_uuidv4"], kind, parent),
            )
        }
        assert complete_clocks == (
            set()
            if retry_clock < 200 or kind == "pr-code" and retry_clock == 200
            else {retry_clock}
        ), kind
        assert current_claim(kind, parent) == (
            (200, "partial") if kind == "pr-code" and retry_clock == 200 else expected
        ), kind
    assert {
        row[0]
        for row in store.all(
            "SELECT m.observed_at_us FROM completion_markers m "
            "JOIN fetch_collections f USING(fetch_collection_id) "
            "WHERE f.change_request_id=? AND f.kind IN ('threads','thread-comments') "
            "AND m.asserted_state='complete'",
            (change_request_id,),
        )
    } == {retry_clock}
    assert_marker_absent(store)


@pytest.mark.parametrize(
    "boundary",
    [
        "identity",
        "identity_empty",
        "owner",
        "repository",
        "repository_id",
        "repository_name_empty",
        "repository_name_extra",
        "selected_clone_empty",
        "page",
    ],
)
def test_rejected_inventory_page_does_not_become_source_input(github_runtime, boundary):
    store, repo, fixture, api = github_runtime
    if boundary in {"repository", "selected_clone_empty"}:
        with store.transaction():
            store.execute(
                "UPDATE sources SET settings=? WHERE source_id='source'",
                (json.dumps({"owner": "fixture", "include_repositories": ["alpha"]}),),
            )
    source = dict(store.one("SELECT * FROM sources WHERE source_id='source'"))
    job, blocked, requested = new_job(store), [True], []
    valid_identity = {"login": "fixture", "public_repos": 1, "owned_private_repos": 0}
    if boundary == "owner":
        valid_identity["login"] = "different-authenticated-user"
    valid_repository = {
        "id": 101,
        "full_name": repo["name"],
        "clone_url": fixture.alpha.url,
        "private": False,
    }
    rejected_path = {
        "identity": "/user",
        "identity_empty": "/user",
        "owner": "/users/fixture",
        "repository": "/repos/fixture/alpha",
        "repository_id": "/user/repos",
        "repository_name_empty": "/user/repos",
        "repository_name_extra": "/user/repos",
        "selected_clone_empty": "/repos/fixture/alpha",
        "page": "/user/repos",
    }[boundary]

    def response(request):
        requested.append(request.url.path)
        if request.url.path == "/user":
            identity = dict(valid_identity)
            if blocked[0] and boundary == "identity":
                identity["login"] = []
            if blocked[0] and boundary == "identity_empty":
                identity["login"] = ""
            return httpx.Response(
                200,
                json={**identity, "unmodeled_transport_marker": MARKER}
                if blocked[0] and boundary in {"identity", "identity_empty"}
                else identity,
            )
        if request.url.path == "/repos/fixture/alpha":
            invalid = {
                **valid_repository,
                "unmodeled_transport_marker": MARKER,
            }
            if boundary == "repository":
                invalid["full_name"] = "foreign/wrong-owner"
            else:
                invalid["clone_url"] = ""
            return httpx.Response(
                200,
                json=invalid if blocked[0] else valid_repository,
            )
        if request.url.path == "/users/fixture":
            return httpx.Response(
                200,
                json={"type": "User", "login": "fixture", "transport_marker": MARKER}
                if blocked[0]
                else {"type": "Organization", "login": "fixture"},
            )
        assert request.url.path in ("/user/repos", "/orgs/fixture/repos")
        values = [valid_repository]
        if blocked[0] and boundary == "repository_id":
            values[0] = {**valid_repository, "id": {"unexpected": 7}}
        if blocked[0] and boundary == "repository_name_empty":
            values[0] = {**valid_repository, "full_name": "fixture/"}
        if blocked[0] and boundary == "repository_name_extra":
            values[0] = {**valid_repository, "full_name": "fixture/alpha/extra"}
        if blocked[0] and boundary != "owner":
            values.append(
                {
                    **valid_repository,
                    "id": 102,
                    "full_name": "foreign/wrong-owner",
                    "unmodeled_transport_marker": MARKER,
                }
            )
        return httpx.Response(200, json=values)

    with collector_for(store, response, [200]) as collector:
        with pytest.raises(CatalogError) as raised:
            collector.inventory(source, job)
        assert raised.value.code == (
            "API_SCHEMA"
            if boundary
            in {
                "identity",
                "identity_empty",
                "repository_id",
                "selected_clone_empty",
            }
            else "SCOPE_UNSUPPORTED"
            if boundary == "owner"
            else "SCOPE_MISMATCH"
        )
        assert_absent_tables(store.connection, "source_input_observations")
        assert_absent_tables(store.connection, "source_input_observations")
        assert store.one("SELECT count(*) FROM payload_admission_staging")[0] == 0
        assert store.one("SELECT count(*) FROM unresolved_payloads")[0] == 0
        assert_marker_absent(store)
        blocked[0] = False
        result = collector.inventory(source, job)
    assert len(result) == 1 and result[0]["provider_repository_id"] == "101"
    assert requested.count(rejected_path) == 2
    assert_marker_absent(store)


@pytest.mark.parametrize("reason", ["PAYLOAD_CORRUPTION", "PAYLOAD_HASH_COLLISION"])
def test_api_original_cannot_use_shared_git_rejection_staging(github_runtime, reason):
    store, _, _, _ = github_runtime
    body = json.dumps({"transport_only": MARKER}).encode()
    with pytest.raises(CatalogError) as invalid:
        PayloadRef("decoded_api", hashlib.sha256(body).digest())
    assert invalid.value.code == "INVALID_PAYLOAD_REFERENCE"
    # The public constructor rejects the retired representation before intake.
    reference = PayloadRef("git-object-raw-v1", hashlib.sha256(body).digest())
    before = list(store.connection.iterdump())
    with pytest.raises(CatalogError) as raised:
        stage_verified_payload(store.connection, body, reference, {}, reason=reason)
    assert raised.value.code == "INVALID_ARGUMENT"
    assert list(store.connection.iterdump()) == before
    with pytest.raises(sqlite3.IntegrityError):
        store.execute(
            "INSERT INTO payload_admission_staging(stage_uuidv4,representation,sha256,"
            "body,context_json,reason,received_at_us) VALUES(?,?,?,?, '{}',?,0)",
            (str(uuid.uuid4()), "decoded_api", reference.sha256, body, reason),
        )
    assert list(store.connection.iterdump()) == before
    assert_no_raw_intake(store)


def test_failed_api_hash_admission_does_not_create_or_stage_original(github_runtime):
    store, _, _, _ = github_runtime
    body = json.dumps({"transport_only": MARKER}).encode()
    with pytest.raises(CatalogError) as raised:
        intern_payload(
            store.connection,
            body,
            representation="decoded_api",
            expected_sha256=hashlib.sha256(b"different bytes").digest(),
        )
    assert raised.value.code == "INVALID_PAYLOAD_REFERENCE"
    assert_no_raw_intake(store)


def test_live_api_domain_admission_is_independent_of_quarantined_git_bytes(
    github_runtime,
):
    from repo_catalog.adapters.sqlite.cas_integrity import verify_all
    from tests.integration.test_catalog3_cas_integrity import corrupt
    from tests.support.git_payloads import register_git_blob

    store, repo, _, api = github_runtime
    pr = registered_pr(store, repo)
    reference = register_git_blob(store.connection, b"actual canonical Git blob")
    with store.transaction():
        corrupt(store.connection, reference.sha256, b"corrupt")
        verify_all(store.connection)
    job = new_job(store)
    payload = {**api.prs[41], "body": DOMAIN_BODY, "unmodeled_transport_marker": MARKER}
    with collector_for(
        store, lambda request: httpx.Response(200, json=payload), [200]
    ) as collector:
        collector.detail(repo, pr, job, api.url + "/repos/fixture/alpha/pulls/41")
    assert store.one("SELECT body FROM text_bodies WHERE body=?", (DOMAIN_BODY,))
    assert store.one("SELECT sha256 FROM payload_quarantine")[0] == reference.sha256
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 1
    assert store.one("SELECT count(*) FROM document_state")[0] == 2
    assert_absent_tables(store.connection, "fetch_occurrences", "document_observations")
    assert_marker_absent(store)


def test_fresh_schema_has_only_physical_unresolved_payload_evidence(github_runtime):
    store, _, _, _ = github_runtime
    columns = {row[1] for row in store.all("PRAGMA table_xinfo(unresolved_payloads)")}
    assert columns == {
        "unresolved_payload_id",
        "stored_sha256",
        "detected_at_us",
        "diagnostic_json",
        "reason",
    }
    assert {
        row[2] for row in store.all("PRAGMA foreign_key_list(unresolved_payloads)")
    } == {"stored_bytes"}
    unresolved_sql = [
        row[0]
        for row in store.all(
            "SELECT sql FROM sqlite_schema WHERE tbl_name='unresolved_payloads' "
            "AND sql IS NOT NULL"
        )
    ]
    assert not any(
        old in statement
        for statement in unresolved_sql
        for old in ("payload_representation", "payload_sha256", "payload_ref_json")
    )
    with pytest.raises(sqlite3.OperationalError, match="payload_representation"):
        store.execute(
            "INSERT INTO unresolved_payloads(payload_representation,payload_sha256,"
            "reason) VALUES('decoded_api',?,'saved-retry')",
            (hashlib.sha256(MARKER.encode()).digest(),),
        )
    assert_no_raw_intake(store)
