"""Mutable collection works from durable domain state with recording disabled."""

import json

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime


def _job(store, kind="issue"):
    job = JobService(store).create("sync", {"kind": kind})
    store.expected_attempt = 1
    return job


def _issue(ident, number, state="open"):
    return {
        "id": ident,
        "number": number,
        "title": f"Issue {number}",
        "body": "issue body",
        "state": state,
        "updated_at": "2026-01-01T00:00:00Z",
    }


def test_all_issue_comments_retained_without_archives_across_restart(github_runtime):
    store, repo, _, api = github_runtime
    stage = 0
    requests = []

    def route(method, path, params, body):
        requests.append((path, params))
        assert method == "GET"
        if path == "/user":
            return {"id": 10}, {}
        if path == "/repos/fixture/alpha/issues":
            assert params["state"] == ["all"]
            if params.get("page") == ["2"]:
                return [_issue(102, 2, "closed")], {}
            return [
                _issue(101, 1),
                {
                    **_issue(199, 41),
                    "pull_request": {"url": api.url + "/repos/fixture/alpha/pulls/41"},
                },
            ], {
                "Link": f'<{api.url}/repos/fixture/alpha/issues?state=all&page=2>; rel="next"'
            }
        if path == "/repos/fixture/alpha/issues/1/comments":
            return [
                {
                    "id": ident,
                    "body": "edited" if stage and ident == 202 else f"comment {ident}",
                    "updated_at": "2026-02-01T00:00:00Z"
                    if stage and ident == 202
                    else "2026-01-01T00:00:00Z",
                }
                for ident in (201, 202)
            ], {}
        if path == "/repos/fixture/alpha/issues/2/comments":
            return [
                {
                    "id": 203,
                    "body": "closed comment",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ], {}
        raise AssertionError(path)

    api.route = route
    job = _job(store)
    assert (
        GitHubCollector(store, CancellationToken()).sync_issues(repo, job)["issues"]
        == 2
    )
    assert store.one("SELECT count(*) FROM issue_resources")[0] == 5
    assert store.one("SELECT count(*) FROM fetch_occurrences")[0] == 0
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
    assert store.one("SELECT count(*) FROM document_observations")[0] == 0
    assert store.one("SELECT count(*) FROM parser_profiles")[0] == 0
    assert store.one("SELECT count(*) FROM parser_profile_selection_decisions")[0] == 0
    for row in store.all("SELECT * FROM issue_resources"):
        assert row["parser_module"] == current_parser.__name__
        assert row["parser_version"] == "1"
        for evidence in json.loads(row["field_evidence_json"]).values():
            assert evidence["parser_module"] == current_parser.__name__
            assert evidence["parser_version"] == "1"
            assert "parser_profile_uuidv4" not in evidence
    for page in store.all("SELECT * FROM current_collection_pages"):
        assert page["parser_module"] == current_parser.__name__
        assert page["parser_version"] == "1"
    assert not (store.path / "transport-archive").exists()
    JobService(store).update(job, "complete")
    stage = 1
    with Store(store.path) as restarted:
        later = _job(restarted)
        GitHubCollector(restarted, CancellationToken()).sync_issues(repo, later)
        assert restarted.one("SELECT count(*) FROM issue_resources")[0] == 5
        assert (
            restarted.one(
                "SELECT b.body FROM issue_resources r JOIN text_bodies b ON b.sha256=r.text_body_sha256 WHERE r.kind='issue-comment' AND r.provider_resource_id='202'"
            )[0]
            == "edited"
        )
        assert restarted.one("SELECT count(*) FROM fetch_occurrences")[0] == 0
    assert any(
        "since" in params for path, params in requests if path.endswith("/comments")
    )


def test_unresolved_terminal_receipt_does_not_become_complete_on_resume(github_runtime):
    store, repo, _, api = github_runtime
    job = _job(store)
    collector = GitHubCollector(store, CancellationToken())
    collector.facts.principal = "10"
    path = "/repos/fixture/alpha/issues/1/comments"
    requests = []

    def route(method, requested, params, body):
        requests.append(requested)
        assert requested == path
        return [
            {"id": 200, "body": "unresolved", "updated_at": "2026-01-01T00:00:00Z"}
        ], {}

    api.route = route

    def parser(value, context, timestamp):
        return current_parser.issue_comment(
            value, {**context, "provider_issue_number": 1}, timestamp, "100"
        )

    def collect():
        return collector.current_collection(
            repo, None, "ordinary-issue-comment", job, api.url + path, parser
        )

    try:
        for _ in range(2):
            with pytest.raises(CatalogError, match="unresolved") as error:
                collect()
            assert error.value.code == "CURRENT_STATE_UNRESOLVED"
        assert requests == [path]
        assert store.one("SELECT count(*) FROM current_collection_pages")[0] == 1
        assert store.one("SELECT count(*) FROM completion_markers")[0] == 0
        assert store.one("SELECT count(*) FROM issue_resources")[0] == 0
        assert (
            store.one("SELECT reason FROM current_resource_diagnostics")[0]
            == "current_state:missing_dependency"
        )
    finally:
        collector.http.close()


def test_review_projection_has_no_fabricated_clock_and_partial_fields_are_absent():
    context = {
        "acquisition_scope": {},
        "parser_module": "caller.supplied.module",
        "parser_version": "caller-supplied-version",
    }
    value = {
        "id": 9,
        "body": "",
        "submitted_at": "2026-01-01T00:00:00Z",
        "updated_at": "not a provider review clock",
    }
    projection = current_parser.review(value, context, 10)
    assert projection["submitted_at_us"] > 0
    assert "provider_updated_at_us" not in projection
    assert "author" not in projection
    assert projection["body"] == ""
    assert projection["parser_module"] == current_parser.__name__
    assert projection["parser_version"] == "1"
    null = current_parser.review({"id": 9, "body": None}, context, 10)
    assert "body" not in null and null["body_status"] == "provider-null"
    graph = current_parser.review_comment(
        {"fullDatabaseId": "12", "body": "x"}, context, 10, graphql=True
    )
    assert "review_provider_resource_id" not in graph
    assert "target_commit_oid" not in graph
    assert "provider_updated_at_us" not in graph
    # Plain JSON projections do not hold input/archive/body dependencies.
    assert json.loads(json.dumps(graph)) == graph


def test_each_review_keeps_latest_state_without_history_or_archive(github_runtime):
    store, repo, _, api = github_runtime
    with store.transaction():
        store.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES('pr',?,'binding','pull_request',41)",
            (repo["repository_uuidv4"],),
        )
    stage = 0

    def route(method, path, params, body):
        assert path == "/repos/fixture/alpha/pulls/41/reviews"
        return [
            {
                "id": ident,
                "body": "edited review" if stage and ident == 12 else f"review {ident}",
                "state": state,
                "submitted_at": None if state == "PENDING" else "2026-01-01T00:00:00Z",
            }
            for ident, state in ((11, "PENDING"), (12, "APPROVED"), (13, "DISMISSED"))
        ], {}

    api.route = route
    collector = GitHubCollector(store, CancellationToken())
    try:
        for stage in (0, 1, 1):
            job = _job(store, "pr")
            collector.current_collection(
                repo,
                "pr",
                "review",
                job,
                api.url + "/repos/fixture/alpha/pulls/41/reviews",
                current_parser.review,
            )
            JobService(store).update(job, "complete")
            assert store.one("SELECT count(*) FROM review_resources")[0] == 3
            assert store.one("SELECT count(*) FROM document_observations")[0] == 0
            assert store.one("SELECT count(*) FROM fetch_occurrences")[0] == 0
        assert (
            store.one(
                "SELECT b.body FROM review_resources r JOIN text_bodies b ON b.sha256=r.text_body_sha256 WHERE r.provider_change_request_document_id='12'"
            )[0]
            == "edited review"
        )
        assert [
            row[0]
            for row in store.all(
                "SELECT state FROM review_resources ORDER BY provider_change_request_document_id"
            )
        ] == ["PENDING", "APPROVED", "DISMISSED"]
        assert (
            store.one(
                "SELECT count(*) FROM review_resources WHERE provider_updated_at_us IS NOT NULL"
            )[0]
            == 0
        )
        assert store.one("SELECT count(*) FROM parser_profiles")[0] == 0
        assert (
            store.one("SELECT count(*) FROM parser_profile_selection_decisions")[0] == 0
        )
        for row in store.all("SELECT * FROM review_resources"):
            assert row["parser_module"] == current_parser.__name__
            assert row["parser_version"] == "1"
    finally:
        collector.http.close()


def test_recorder_failure_reports_diagnostics_without_invalidating_current_state(
    github_runtime,
):
    store, repo, _, api = github_runtime

    class BrokenRecorder:
        def record_exchange(self, context, body):
            raise OSError("synthetic recording failure")

    def route(method, path, params, body):
        if path == "/user":
            return {"id": 10}, {}
        if path.endswith("/issues"):
            return [_issue(1, 1)], {}
        assert path.endswith("/issues/1/comments")
        return [{"id": 2, "body": "saved despite recorder failure"}], {}

    api.route = route
    transport = GitHubTransport(
        store.config["github"], CancellationToken(), recorder=BrokenRecorder()
    )
    try:
        with pytest.warns(RuntimeWarning, match="recording failed"):
            result = GitHubCollector(
                store, CancellationToken(), transport=transport
            ).sync_issues(repo, _job(store))
        assert result["state"] == "complete"
        assert len(result["recording_diagnostics"]) == 3
        assert {item["code"] for item in result["recording_diagnostics"]} == {
            "ARCHIVE_FAILURE"
        }
        assert store.one("SELECT count(*) FROM issue_resources")[0] == 2
        assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
    finally:
        transport.close()


def test_two_service_bindings_keep_same_number_in_distinct_pr_owners(github_runtime):
    store, repo, _, api = github_runtime
    with store.transaction():
        store.execute(
            "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES(?,?,'binding','pull_request',41)",
            (repo["repository_uuidv4"] + ":41", repo["repository_uuidv4"]),
        )
        store.execute(
            "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES('00000000-0000-4000-8000-000000000102','github','other','{}')"
        )
        store.execute(
            "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('other-source','00000000-0000-4000-8000-000000000202','00000000-0000-4000-8000-000000000102','github_inventory','other','{\"owner\":\"fixture\"}')"
        )
        store.execute(
            "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata) VALUES('other-binding',?,'00000000-0000-4000-8000-000000000102','101','{}')",
            (repo["repository_uuidv4"],),
        )
    other_repo = {**repo, "source_id": "other-source"}
    collector = GitHubCollector(store, CancellationToken())
    try:
        job = _job(store, "pr")
        with store.transaction():
            collection = collector.facts.begin(
                other_repo, None, "pr-list", job, api.url + "/repos/fixture/alpha/pulls"
            )
            occurrence, _, timestamp = collector.facts.page(
                collection, httpx.Response(200, json=[api.prs[41]]), {}, None
            )
            owner = collector.ensure_pr(
                other_repo, api.prs[41], collection, occurrence, 0, timestamp
            )
            collector.facts.publish()
        assert owner == "other-binding:41"
        assert (
            store.one(
                "SELECT repository_binding_id FROM change_requests WHERE change_request_id=?",
                (owner,),
            )[0]
            == "other-binding"
        )
        assert (
            store.one(
                "SELECT count(*) FROM change_requests WHERE provider_change_request_number=41"
            )[0]
            == 2
        )
        assert (
            store.one(
                "SELECT count(*) FROM document_observations WHERE change_request_id=?",
                (repo["repository_uuidv4"] + ":41",),
            )[0]
            == 0
        )
    finally:
        collector.http.close()


def test_pr_summary_time_includes_current_pages_with_exact_job_scope(github_runtime):
    from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof

    store, repo, _, _ = github_runtime
    collector = GitHubCollector(store, CancellationToken())
    try:
        job, other_job = _job(store, "pr"), _job(store, "pr")
        with store.transaction():
            raw = collector.facts.begin(
                repo, None, "pr-list", job, "https://github.test/pulls"
            )
            collector.facts.page(
                raw,
                httpx.Response(
                    200, content=b"[]", extensions={"catalog_observed_at_us": 10}
                ),
                {},
                None,
            )
            operational = collector.facts.begin(
                repo, None, "threads", job, "https://github.test/error"
            )
            collector.facts.page(
                operational,
                httpx.Response(
                    200, content=b"{}", extensions={"catalog_observed_at_us": 999}
                ),
                {"operational_only": True},
                None,
            )
            current = collector.facts.begin(
                repo, None, "review", job, "https://github.test/reviews"
            )
            CurrentCollectionProof(store.connection).page(
                current["fetch_collection_id"],
                0,
                20,
                None,
                [],
                parser_module=current_parser.__name__,
                parser_version="1",
            )
            unrelated = collector.facts.begin(
                repo, None, "review", other_job, "https://github.test/other"
            )
            CurrentCollectionProof(store.connection).page(
                unrelated["fetch_collection_id"],
                0,
                400,
                None,
                [],
                parser_module=current_parser.__name__,
                parser_version="1",
            )
        assert collector.summary_observed_at_us(repo, job) == 20
        assert collector.summary_observed_at_us(repo, job, documents_only=True) == 20
        with store.transaction():
            code = collector.facts.begin(
                repo, None, "pr-files", job, "https://github.test/files"
            )
            collector.facts.page(
                code,
                httpx.Response(
                    200, content=b"[]", extensions={"catalog_observed_at_us": 30}
                ),
                {},
                None,
            )
        assert collector.summary_observed_at_us(repo, job) == 30
        assert collector.summary_observed_at_us(repo, job, documents_only=True) == 20
    finally:
        collector.http.close()


def test_changed_parser_rescans_instead_of_reusing_collection_receipts(
    github_runtime, monkeypatch
):
    store, repo, _, api = github_runtime
    api.route = lambda *args: ([], {})
    collector = GitHubCollector(store, CancellationToken())
    endpoint = api.url + "/repos/fixture/alpha/issues?state=all&per_page=100"
    context = {"incremental_endpoint": endpoint}
    try:
        job = _job(store)
        collector.current_collection(
            repo, None, "issue", job, endpoint, current_parser.issue, context=context
        )
        JobService(store).update(job, "complete")
        next_job = _job(store)
        url, baseline = collector.current_incremental_url(
            repo, next_job, "issue", endpoint, context
        )
        assert "since=" in url and baseline["completion_marker_uuidv4"]
        # Preserve the existing conservative full-rescan behavior across a
        # producer change. This does not rank or supersede any domain value.
        monkeypatch.setattr(current_parser, "PARSER_VERSION", "2")
        url, baseline = collector.current_incremental_url(
            repo, next_job, "issue", endpoint, context
        )
        assert url == endpoint and "completion_marker_uuidv4" not in baseline
        page = store.one("SELECT * FROM current_collection_pages")
        assert page["parser_module"] == current_parser.__name__
        assert page["parser_version"] == "1"
        assert store.one("SELECT count(*) FROM parser_profiles")[0] == 0
    finally:
        collector.http.close()
