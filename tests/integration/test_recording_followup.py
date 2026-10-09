"""Supplementary recorder diagnostics never replace acquisition outcomes."""

import itertools
import json
import sqlite3
import warnings

import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.recording import RecordingError
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime

SECRET = "synthetic-private-recorder-secret"


def issue():
    return {
        "id": 1,
        "number": 1,
        "title": "saved Issue",
        "body": "current body survives recorder failure",
        "state": "open",
        "updated_at": "2026-01-01T00:00:00Z",
    }


def job(store):
    identifier = JobService(store).create("sync", {"kind": "issue"})
    store.expected_attempt = 1
    return identifier


class BrokenRecorder:
    def __init__(self, error):
        self.error = error

    def record_exchange(self, context, body):
        raise self.error


def test_collection_aggregate_retains_only_the_last_100_capture_diagnostics(
    github_runtime,
):
    store, repo, _, api = github_runtime
    timestamps = itertools.count()

    def route(method, path, params, body):
        if path == "/user":
            return {"id": 10}, {}
        if path == "/repos/fixture/alpha/issues":
            page = int(params.get("page", ["0"])[0])
            if page < 103:
                return [], {
                    "Link": f'<{api.url}/repos/fixture/alpha/issues?page={page + 1}>; rel="next"'
                }
            return [issue()], {}
        assert path == "/repos/fixture/alpha/issues/1/comments"
        return [], {}

    api.route = route
    transport = GitHubTransport(
        store.config["github"],
        CancellationToken(),
        recorder=BrokenRecorder(OSError(SECRET)),
        clock_us=lambda: next(timestamps),
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            result = GitHubCollector(
                store, CancellationToken(), transport=transport
            ).sync_issues(repo, job(store))
        assert result["state"] == "complete"
        assert len(api.requests) == 106
        assert len(result["recording_diagnostics"]) == 100
        assert [
            item["observed_at_us"] for item in result["recording_diagnostics"]
        ] == list(range(6, 106))
        assert result["recording_diagnostics"] == transport.recording_diagnostics
        assert store.one("SELECT count(*) FROM issue_resources")[0] == 1
    finally:
        transport.close()


@pytest.mark.parametrize(
    "error,expected",
    [
        (OSError(SECRET), "ARCHIVE_FAILURE"),
        (RecordingError("ARCHIVE_IO", SECRET), "ARCHIVE_IO"),
        (RecordingError(SECRET * 1000, SECRET), "ARCHIVE_FAILURE"),
    ],
)
def test_warning_error_filter_preserves_actual_collection_and_admission(
    github_runtime, error, expected
):
    store, repo, _, api = github_runtime

    def route(method, path, params, body):
        assert method == "GET"
        if path == "/user":
            return {"id": 10}, {}
        if path == "/repos/fixture/alpha/issues":
            return [issue()], {}
        assert path == "/repos/fixture/alpha/issues/1/comments"
        return [{"id": 2, "body": "comment survives too"}], {}

    api.route = route
    transport = GitHubTransport(
        store.config["github"],
        CancellationToken(),
        recorder=BrokenRecorder(error),
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            result = GitHubCollector(
                store, CancellationToken(), transport=transport
            ).sync_issues(repo, job(store))
        assert result["state"] == "complete"
        assert result["issues"] == 1
        assert len(result["recording_diagnostics"]) == 3
        assert {item["code"] for item in result["recording_diagnostics"]} == {expected}
        assert SECRET not in json.dumps(result["recording_diagnostics"])
        assert all(
            set(item) == {"code", "observed_at_us", "attempt"}
            for item in result["recording_diagnostics"]
        )
        assert [
            row[0]
            for row in store.all(
                "SELECT b.body FROM issue_resources r JOIN text_bodies b "
                "ON b.sha256=r.text_body_sha256 ORDER BY r.provider_resource_id"
            )
        ] == [issue()["body"], "comment survives too"]
        assert store.one("SELECT count(*) FROM current_collection_pages")[0] == 2
        assert store.one("SELECT count(*) FROM completion_markers")[0] >= 2
        assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
        assert not (store.path / "transport-archive").exists()
    finally:
        transport.close()


@pytest.mark.parametrize("failure", ["parser", "storage"])
def test_recorder_failure_preserves_actual_parser_and_storage_errors(
    github_runtime, failure
):
    store, repo, _, api = github_runtime
    value = issue()
    if failure == "parser":
        value["body"] = ["malformed provider body"]
        expected_error = CatalogError
    else:
        with store.transaction():
            store.execute(
                "CREATE TRIGGER synthetic_reject_issue BEFORE INSERT ON issue_resources "
                "BEGIN SELECT RAISE(ABORT, 'synthetic catalog failure'); END"
            )
        expected_error = sqlite3.IntegrityError

    def route(method, path, params, body):
        assert path == "/repos/fixture/alpha/issues"
        return [value], {}

    api.route = route
    token = CancellationToken()
    transport = GitHubTransport(
        store.config["github"], token, recorder=BrokenRecorder(OSError(SECRET))
    )
    collector = GitHubCollector(store, token, transport=transport)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            with pytest.raises(expected_error) as raised:
                collector.current_collection(
                    repo,
                    None,
                    "issue",
                    job(store),
                    api.url + "/repos/fixture/alpha/issues",
                    current_parser.issue,
                )
        if failure == "parser":
            assert raised.value.code == "API_SCHEMA"
        else:
            assert str(raised.value) == "synthetic catalog failure"
        assert transport.recording_diagnostics[0]["code"] == "ARCHIVE_FAILURE"
        assert store.one("SELECT count(*) FROM issue_resources")[0] == 0
        assert store.one("SELECT count(*) FROM current_collection_pages")[0] == 0
        assert store.one("SELECT count(*) FROM completion_markers")[0] == 0
    finally:
        transport.close()
