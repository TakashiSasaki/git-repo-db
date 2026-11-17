"""Optional recorder errors cannot replace real HTTP intake outcomes."""

import json
import sqlite3
import warnings
from contextlib import closing

import httpx
import pytest

from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application import provider_fetch
from tests.integration.p5.test_separated_github_fetch import response, setup

SECRET = "synthetic-recorder-private-error-must-not-escape"


@pytest.mark.parametrize("failure", ["parser", "storage"])
def test_failing_recorder_preserves_actual_parser_or_storage_outcome(
    tmp_path, monkeypatch, failure
):
    document, authorization, admission = setup(tmp_path)
    transports, calls = [], []
    storage_error = sqlite3.IntegrityError("synthetic current field storage refusal")

    class BrokenRecorder:
        def record_exchange(self, context, body):
            raise OSError(SECRET)

    def transport(*args, **kwargs):
        result = GitHubTransport(*args, **kwargs, recorder=BrokenRecorder())
        transports.append(result)
        return result

    monkeypatch.setattr(provider_fetch, "GitHubTransport", transport)
    if failure == "storage":
        original = Context.observe

        def refuse_issue(self, observation):
            if observation.resource.resource_kind == "issue":
                raise storage_error
            return original(self, observation)

        monkeypatch.setattr(Context, "observe", refuse_issue)

    def handle(request):
        calls.append(request.url.path)
        if request.url.path == "/repos/owner/repo":
            return response(request, {"id": 10, "full_name": "owner/repo"})
        return response(
            request,
            [{"id": 20, "number": 1, "body": [] if failure == "parser" else "valid"}],
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            if failure == "parser":
                report = provider_fetch.acquire_github(
                    tmp_path,
                    document,
                    authorization=authorization,
                    admission=admission,
                    client=client,
                )
                assert (
                    report.status == "partial"
                    and report.failure_code == "INVALID_FIELD"
                )
            else:
                with pytest.raises(Exception) as raised:
                    provider_fetch.acquire_github(
                        tmp_path,
                        document,
                        authorization=authorization,
                        admission=admission,
                        client=client,
                    )
                pending, seen, chain = [raised.value], set(), []
                while pending:
                    error = pending.pop()
                    if id(error) in seen:
                        continue
                    seen.add(id(error))
                    chain.append(error)
                    for attribute in ("__cause__", "__context__", "cause"):
                        cause = getattr(error, attribute, None)
                        if isinstance(cause, BaseException):
                            pending.append(cause)
                assert storage_error in chain
    assert calls == ["/repos/owner/repo", "/repos/owner/repo/issues"]
    diagnostics = transports[0].recording_diagnostics
    assert len(diagnostics) == 2
    assert {item["code"] for item in diagnostics} == {"ARCHIVE_FAILURE"}
    assert all(
        set(item) == {"code", "observed_at_us", "attempt"} for item in diagnostics
    )
    assert SECRET not in json.dumps(diagnostics)
    with closing(connect(tmp_path / "context.sqlite3", "context")) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM resources WHERE resource_kind='repository'"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM field_candidates WHERE resource_kind='repository'"
            ).fetchone()[0]
            > 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM resources WHERE resource_kind='issue'"
            ).fetchone()[0]
            == 0
        )
        assert db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 0
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert not (tmp_path / "transport-archive").exists()
