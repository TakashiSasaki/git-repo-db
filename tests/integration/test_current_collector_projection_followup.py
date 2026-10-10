"""REST and GraphQL collector projections preserve field-level evidence."""

import json

import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from repo_catalog.domain.time import parse_iso8601_us
from tests.support.github_runtime import github_runtime as github_runtime

OLD_CLOCK = "2026-01-01T00:00:00Z"
NEW_CLOCK = "2026-02-01T00:00:00Z"
OLD_HUNK = "@@ -1 +1 @@\n-old"
NEW_HUNK = "@@ -1 +1 @@\n+new"


def job(store):
    identifier = JobService(store).create("sync", {"kind": "pr"})
    store.expected_attempt = 1
    return identifier


def seed_pr(store, repo):
    with store.transaction():
        store.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,"
            "repository_binding_id,change_request_kind,provider_change_request_number) "
            "VALUES('projection-pr',?,'binding','pull_request',41)",
            (repo["repository_uuidv4"],),
        )
    return {
        "change_request_id": "projection-pr",
        "provider_change_request_number": 41,
    }


def rest_full(fixture, *, newer=False, body="old body", null_relationships=False):
    return {
        "id": 502,
        "body": body,
        "updated_at": NEW_CLOCK if newer else OLD_CLOCK,
        "user": {"login": "new-author" if newer else "old-author"},
        "pull_request_review_id": None if null_relationships else 11,
        "in_reply_to_id": None if null_relationships else 501,
        "commit_id": fixture.alpha.commits["P"],
        "original_commit_id": fixture.alpha.commits["N"],
        "path": "new.py" if newer else "old.py",
        "diff_hunk": NEW_HUNK if newer else OLD_HUNK,
        "position": 2 if newer else 1,
        "original_position": 1,
        "line": 20 if newer else 10,
        "original_line": 10,
        "side": "RIGHT",
    }


def graphql_full(fixture, **kwargs):
    value = rest_full(fixture, **kwargs)
    return {
        "fullDatabaseId": str(value["id"]),
        "body": value["body"],
        "updatedAt": value["updated_at"],
        "author": value["user"],
        "pullRequestReview": {"fullDatabaseId": "11"}
        if value["pull_request_review_id"] is not None
        else None,
        "replyTo": {"fullDatabaseId": "501"}
        if value["in_reply_to_id"] is not None
        else None,
        "commit": {"oid": value["commit_id"]},
        "originalCommit": {"oid": value["original_commit_id"]},
        "path": value["path"],
        "diffHunk": value["diff_hunk"],
        "position": value["position"],
        "originalPosition": value["original_position"],
        "line": value["line"],
        "originalLine": value["original_line"],
        "side": value["side"],
    }


def partial(api_kind):
    if api_kind == "rest":
        return {
            "id": 502,
            "updated_at": NEW_CLOCK,
            "user": {"login": "new-author"},
            "diff_hunk": NEW_HUNK,
        }
    return {
        "fullDatabaseId": "502",
        "updatedAt": NEW_CLOCK,
        "author": {"login": "new-author"},
        "diffHunk": NEW_HUNK,
    }


def terminal(nodes):
    return {
        "nodes": nodes,
        "pageInfo": {"hasNextPage": False, "endCursor": None},
    }


def collect(collector, repo, pr, api, api_kind, values):
    def route(method, path, params, body):
        if api_kind == "rest":
            assert method == "GET"
            assert path == "/repos/fixture/alpha/pulls/41/comments"
            return values, {}
        assert method == "POST" and path == "/graphql"
        assert body["variables"]["number"] == 41
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "mergeCommit": None,
                        "potentialMergeCommit": None,
                        "reviewThreads": terminal(
                            [
                                {
                                    "id": "projection-thread",
                                    "isResolved": False,
                                    "isOutdated": False,
                                    "comments": terminal(values),
                                }
                            ]
                        ),
                    }
                }
            }
        }, {}

    api.route = route
    identifier = job(collector.s)
    if api_kind == "rest":
        collector.current_collection(
            repo,
            pr["change_request_id"],
            "review-comment",
            identifier,
            api.url + "/repos/fixture/alpha/pulls/41/comments",
            current_parser.review_comment,
        )
    else:
        collector.threads(repo, pr, identifier)
    JobService(collector.s).update(identifier, "complete")


def seed_review(collector, repo, pr, api):
    def route(method, path, params, body):
        assert path == "/repos/fixture/alpha/pulls/41/reviews"
        return [{"id": 11, "body": "review", "state": "COMMENTED"}], {}

    api.route = route
    identifier = job(collector.s)
    collector.current_collection(
        repo,
        pr["change_request_id"],
        "review",
        identifier,
        api.url + "/repos/fixture/alpha/pulls/41/reviews",
        current_parser.review,
    )
    JobService(collector.s).update(identifier, "complete")


def comment(store):
    return store.one(
        "SELECT r.*,b.body FROM review_resources r LEFT JOIN text_bodies b "
        "ON b.sha256=r.text_body_sha256 WHERE r.kind='review-comment' "
        "AND r.provider_change_request_document_id='502'"
    )


@pytest.mark.parametrize("first", ["rest", "graphql"])
@pytest.mark.parametrize("final_body", ["new exact\nbody\x00suffix", None, ""])
@pytest.mark.parametrize("arrival", ["partial-first", "full-first"])
def test_old_full_new_partial_equal_clock_full_across_collector_endpoints(
    github_runtime, first, final_body, arrival, monkeypatch
):
    store, repo, fixture, api = github_runtime
    pr = seed_pr(store, repo)
    collector = GitHubCollector(store, CancellationToken())
    other = "graphql" if first == "rest" else "rest"
    full = rest_full if first == "rest" else graphql_full
    parent = (
        {"id": 501, "body": "root body", "updated_at": OLD_CLOCK}
        if first == "rest"
        else {"fullDatabaseId": "501", "body": "root body", "updatedAt": OLD_CLOCK}
    )
    try:
        monkeypatch.setattr(current_parser, "PARSER_VERSION", "1")
        seed_review(collector, repo, pr, api)
        collect(collector, repo, pr, api, first, [parent, full(fixture)])
        monkeypatch.setattr(current_parser, "PARSER_VERSION", "2")
        if arrival == "partial-first":
            collect(collector, repo, pr, api, other, [partial(other)])
            saved = comment(store)
            assert saved["body"] == "old body"
            assert saved["raw_path"] == "old.py"
            assert saved["author"] == "new-author"
            assert saved["diff_hunk"] == NEW_HUNK
            assert saved["review_provider_resource_id"] == "11"
            assert saved["in_reply_to_provider_resource_id"] == "501"
            assert saved["target_commit_oid"] == fixture.alpha.commits["P"]
            assert json.loads(saved["metadata"])["line"] == 10
            assert saved["review_thread_provider_resource_id"] == "projection-thread"
            evidence = json.loads(saved["field_evidence_json"])
            assert evidence['["body"]']["provider_updated_at_us"] == parse_iso8601_us(
                OLD_CLOCK
            )
            assert evidence['["author"]']["provider_updated_at_us"] == parse_iso8601_us(
                NEW_CLOCK
            )
            assert evidence['["body"]']["parser_module"] == current_parser.__name__
            assert evidence['["body"]']["parser_version"] == "1"
            assert evidence['["author"]']["parser_module"] == current_parser.__name__
            assert evidence['["author"]']["parser_version"] == "2"
            assert "parser_profile_uuidv4" not in evidence['["body"]']
            assert evidence['["body"]']["acquisition_scope"]["endpoint"] == (
                api.url + "/repos/fixture/alpha/pulls/41/comments"
                if first == "rest"
                else api.url + "/graphql"
            )
        collect(
            collector,
            repo,
            pr,
            api,
            first,
            [
                full(
                    fixture,
                    newer=True,
                    body=final_body,
                    null_relationships=final_body is None,
                )
            ],
        )
        if arrival == "full-first":
            collect(collector, repo, pr, api, other, [partial(other)])
        saved = comment(store)
        assert saved["body"] == final_body
        assert saved["body_status"] == (
            "provider-null" if final_body is None else "present"
        )
        assert saved["raw_path"] == "new.py"
        assert saved["current_position"] == 2
        assert json.loads(saved["metadata"])["line"] == 20
        assert saved["review_provider_resource_id"] == (
            None if final_body is None else "11"
        )
        assert saved["in_reply_to_provider_resource_id"] == (
            None if final_body is None else "501"
        )
        assert saved["review_thread_provider_resource_id"] == "projection-thread"
        evidence = json.loads(saved["field_evidence_json"])
        assert evidence['["body"]']["parser_module"] == current_parser.__name__
        assert evidence['["body"]']["parser_version"] == "2"
        assert evidence['["author"]']["parser_version"] == "2"
        assert store.one("SELECT count(*) FROM current_resource_diagnostics")[0] == 0
        assert store.one("SELECT count(*) FROM eligible_review_resources")[0] == 3
        assert store.one("SELECT count(*) FROM review_resources")[0] == 3
        assert store.all("PRAGMA foreign_key_check") == []
    finally:
        collector.http.close()


@pytest.mark.parametrize("first", ["rest", "graphql"])
def test_older_complete_response_fills_unknown_fields_without_reverting_newer_fields(
    github_runtime, first, monkeypatch
):
    store, repo, fixture, api = github_runtime
    pr = seed_pr(store, repo)
    collector = GitHubCollector(store, CancellationToken())
    other = "graphql" if first == "rest" else "rest"
    full = rest_full if first == "rest" else graphql_full
    try:
        monkeypatch.setattr(current_parser, "PARSER_VERSION", "2")
        seed_review(collector, repo, pr, api)
        collect(collector, repo, pr, api, other, [partial(other)])
        monkeypatch.setattr(current_parser, "PARSER_VERSION", "1")
        collect(
            collector,
            repo,
            pr,
            api,
            first,
            [full(fixture, null_relationships=True)],
        )
        saved = comment(store)
        assert saved["body"] == "old body"
        assert saved["raw_path"] == "old.py"
        assert saved["author"] == "new-author"
        assert saved["diff_hunk"] == NEW_HUNK
        assert json.loads(saved["metadata"])["line"] == 10
        evidence = json.loads(saved["field_evidence_json"])
        assert evidence['["body"]']["provider_updated_at_us"] == parse_iso8601_us(
            OLD_CLOCK
        )
        assert evidence['["author"]']["provider_updated_at_us"] == parse_iso8601_us(
            NEW_CLOCK
        )
        assert evidence['["body"]']["parser_module"] == current_parser.__name__
        assert evidence['["body"]']["parser_version"] == "1"
        assert evidence['["author"]']["parser_module"] == current_parser.__name__
        assert evidence['["author"]']["parser_version"] == "2"
        assert saved["provider_updated_at_us"] == parse_iso8601_us(NEW_CLOCK)
        assert store.one("SELECT count(*) FROM current_resource_diagnostics")[0] == 0
    finally:
        collector.http.close()


@pytest.mark.parametrize("first", ["rest", "graphql"])
def test_conflicting_equal_clock_overlap_remains_visible_at_collector_boundary(
    github_runtime, first, monkeypatch
):
    store, repo, fixture, api = github_runtime
    pr = seed_pr(store, repo)
    collector = GitHubCollector(store, CancellationToken())
    other = "graphql" if first == "rest" else "rest"
    full = rest_full if first == "rest" else graphql_full
    try:
        seed_review(collector, repo, pr, api)
        collect(collector, repo, pr, api, other, [partial(other)])
        request = collector.http.request

        def intervening_publication(*args, **kwargs):
            response = request(*args, **kwargs)
            # Another catalog writer commits while the HTTP request is in
            # flight, so this response has no serialized live authority.
            with Store(store.path) as competing:
                with competing.transaction():
                    competing.execute(
                        "UPDATE repositories SET metadata=? WHERE repository_uuidv4=?",
                        (
                            '{"synthetic_concurrent_write":true}',
                            repo["repository_uuidv4"],
                        ),
                    )
                    competing.publish()
            return response

        monkeypatch.setattr(collector.http, "request", intervening_publication)
        contradictory = full(
            fixture, newer=True, body="new body", null_relationships=True
        )
        contradictory["diff_hunk" if first == "rest" else "diffHunk"] = "contradictory"
        with pytest.raises(CatalogError) as raised:
            collect(collector, repo, pr, api, first, [contradictory])
        assert raised.value.code == "CURRENT_STATE_UNRESOLVED"
        assert (
            store.one(
                "SELECT count(*) FROM current_resource_diagnostics WHERE reason='current_state:conflict'"
            )[0]
            == 1
        )
        assert comment(store)["diff_hunk"] == NEW_HUNK
        assert (
            store.one(
                "SELECT count(*) FROM eligible_review_resources WHERE kind='review-comment'"
            )[0]
            == 0
        )
    finally:
        collector.http.close()
