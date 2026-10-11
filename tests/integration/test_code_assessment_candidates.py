"""Code comparisons retain real equal-clock alternatives through acquisition/Exchange."""

import copy
import json
from types import SimpleNamespace

import pytest

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.sqlite.code_assessments import current_code_assessment
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.pr_queries import _code_observation
from repo_catalog.application.query_service import QueryService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime


def acquire(store, repo, observed, *, conflict=False):
    collector = GitHubCollector(store, CancellationToken())
    collector.http.clock_us = lambda: observed
    job = JobService(store).create("sync", {"kind": "pr"})
    store.expected_attempt = 1
    if conflict:
        with pytest.raises(CatalogError) as raised:
            collector.sync(repo, job)
        assert raised.value.code == "PR_PARTIAL"
        assert any(
            failure["reason"] == "PR_CODE_CONFLICT"
            for failure in raised.value.details["missing"]
        )
    else:
        assert collector.sync(repo, job)["state"] == "complete"


def selected(store):
    pr = store.one(
        "SELECT * FROM change_requests WHERE provider_change_request_number=41"
    )
    return _code_observation(SimpleNamespace(s=store), pr)


def current_coverage(store):
    return store.one(
        "SELECT coverage_state FROM current_coverage WHERE kind='pr-code' AND change_request_id=(SELECT change_request_id FROM change_requests WHERE provider_change_request_number=41)"
    )[0]


def code_query(store, repo):
    return QueryService(store.path).query(
        "pr code",
        {"repo": repo["repository_uuidv4"], "provider_change_request_number": 41},
    )


def variable_files(api, mode):
    original = api.route

    def route(method, path, params, body):
        values, headers = original(method, path, params, body)
        if path.endswith("/pulls/41/files") and mode[0] == 2:
            values = [*values, {**values[0], "filename": "other-captured-path.txt"}]
        return values, headers

    api.route = route


def one_pr(api):
    original = api.route
    api.prs[41] = copy.deepcopy(api.prs[41])

    def route(method, path, params, body):
        if path == "/repos/fixture/alpha/pulls":
            return [api.prs[41]], {}
        return original(method, path, params, body)

    api.route = route


@pytest.mark.parametrize("counts", [(1, 2), (2, 1)])
def test_equal_clock_code_candidates_survive_exchange_and_newer_observation(
    github_runtime, tmp_path, counts
):
    store, repo, _, api = github_runtime
    one_pr(api)
    api.prs[41]["updated_at"] = "2026-01-01T00:00:00Z"
    mode = [counts[0]]
    variable_files(api, mode)
    api.prs[41]["changed_files"] = mode[0]
    acquire(store, repo, 300)
    original = dict(selected(store))
    events = [tuple(row) for row in store.all("SELECT * FROM change_request_events")]
    first_unit = Graph(store.connection).export(repo["repository_uuidv4"])
    mode[0] = counts[1]
    api.prs[41]["changed_files"] = mode[0]
    acquire(store, repo, 300, conflict=True)
    assert selected(store) is None
    assert current_coverage(store) == "conflict"
    assert code_query(store, repo).data["items"] == []
    assert (
        dict(
            store.one(
                "SELECT * FROM code_assessments WHERE code_assessment_id=?",
                (original["code_assessment_id"],),
            )
        )
        == original
    )
    conflict_unit = Graph(store.connection).export(repo["repository_uuidv4"])
    # A stale observation cannot decide the conflicting latest candidate set.
    acquire(store, repo, 275, conflict=True)
    assert selected(store) is None
    assert current_coverage(store) == "conflict"
    # A genuine newer observation resolves the current comparison; it must not
    # mutate an earlier portable assessment identity in a receiving catalog.
    # The PR field contradiction has a separate provider clock: explicitly
    # advance it too instead of using code observation time as PR freshness.
    api.prs[41]["updated_at"] = "2026-02-01T00:00:00Z"
    acquire(store, repo, 400)
    assert [
        tuple(row) for row in store.all("SELECT * FROM change_request_events")
    ] == events
    assert selected(store)["observed_at_us"] == 400
    assert current_coverage(store) == "complete"
    assert len(code_query(store, repo).data["items"]) >= counts[1]
    newer_unit = Graph(store.connection).export(repo["repository_uuidv4"])
    for order in ((first_unit, conflict_unit), (conflict_unit, first_unit)):
        state = tmp_path / ("receiver-" + str(order[0] is first_unit))
        MaintenanceService(state).init("catalog-text-v1", 67_108_864, 0)
        with Store(state) as receiver:
            for unit in (*order, conflict_unit):
                delivery = {**unit, "records": list(reversed(unit["records"]))}
                with receiver.transaction():
                    result = Graph(receiver.connection).receive(delivery)
                # The PR's changed_files field itself also disagrees at the
                # same clock. Imported alternatives correctly preserve it.
                pending = receiver.all("SELECT table_name,reason FROM exchange_staging")
                assert result["staged_records"] == len(pending)
                assert all(
                    tuple(row) == ("change_request_state", "current_state:conflict")
                    for row in pending
                )
                assert result["rejected_records"] == 0
            assert selected(receiver) is None
            assert (
                current_code_assessment(
                    receiver,
                    original["change_request_id"],
                    original["object_format"],
                    original["head_oid"],
                    original["base_oid"],
                )
                is None
            )
            assert current_coverage(receiver) == "conflict"
            assert code_query(receiver, repo).data["items"] == []
            for unit in (newer_unit, conflict_unit, newer_unit):
                with receiver.transaction():
                    result = Graph(receiver.connection).receive(unit)
                assert result["staged_records"] == 0
                assert result["rejected_records"] == 0
            assert selected(receiver)["observed_at_us"] == 400
            assert current_coverage(receiver) == "complete"
            assert not receiver.all("PRAGMA foreign_key_check")


def test_equal_clock_equivalent_list_captures_remain_complete(github_runtime):
    store, repo, _, api = github_runtime
    one_pr(api)
    api.prs[41].pop("changed_files")
    acquire(store, repo, 300)
    api.prs[41]["changed_files"] = 1
    acquire(store, repo, 300)
    assert (
        store.one(
            "SELECT count(*) FROM code_listings WHERE kind='files' AND change_request_id=(SELECT change_request_id FROM change_requests WHERE provider_change_request_number=41)"
        )[0]
        == 2
    )
    assert selected(store)["state"] == "complete"
    assert current_coverage(store) == "complete"
    assert code_query(store, repo).data["items"]


@pytest.mark.parametrize("interrupt", [False, True])
def test_provisional_code_acquisition_exchange_converges_after_finalization(
    github_runtime, tmp_path, monkeypatch, interrupt
):
    from repo_catalog.adapters.git.importer import GitImporter

    store, repo, _, api = github_runtime
    one_pr(api)
    provisional = []
    original = GitImporter.sync

    def export_during_acquisition(importer, *args, **kwargs):
        if not provisional:
            assert selected(store)["state"] in {"pending", "partial"}
            provisional.append(
                Graph(store.connection).export(repo["repository_uuidv4"])
            )
            if interrupt:
                raise CatalogError("CANCELLED", "After real input capture before Git")
        return original(importer, *args, **kwargs)

    monkeypatch.setattr(GitImporter, "sync", export_during_acquisition)
    collector = GitHubCollector(store, CancellationToken())
    collector.http.clock_us = lambda: 300
    jobs = JobService(store)
    job = jobs.create("sync", {"kind": "pr"})
    store.expected_attempt = 1
    if interrupt:
        with pytest.raises(CatalogError, match="After real input capture"):
            collector.sync(repo, job)
        assert selected(store)["state"] == "pending"
        jobs.update(job, "interrupted")
        jobs.resume(job)
        store.expected_attempt = 2
        collector = GitHubCollector(store, CancellationToken())
        collector.http.clock_us = lambda: 300
    assert collector.sync(repo, job)["state"] == "complete"
    assert store.one("SELECT count(*) FROM code_assessments")[0] == 1
    complete = Graph(store.connection).export(repo["repository_uuidv4"])
    state = tmp_path / "interleaving-receiver"
    MaintenanceService(state).init("catalog-text-v1", 67_108_864, 0)
    with Store(state) as receiver:
        for unit in (provisional[0], complete, provisional[0], complete):
            with receiver.transaction():
                result = Graph(receiver.connection).receive(unit)
            assert result["staged_records"] == 0
            assert result["rejected_records"] == 0
        assert selected(receiver)["state"] == "complete"
        assert code_query(receiver, repo).data["items"]
    # Progress cannot replace another capture or alter already-final facts.
    for field in ("clock", "captured-detail", "final-state"):
        state = tmp_path / ("mismatch-" + field)
        MaintenanceService(state).init("catalog-text-v1", 67_108_864, 0)
        with Store(state) as receiver:
            with receiver.transaction():
                Graph(receiver.connection).receive(
                    complete if field == "final-state" else provisional[0]
                )
            before = dict(selected(receiver))
            record = copy.deepcopy(
                next(r for r in complete["records"] if r["table"] == "code_assessments")
            )
            if field == "clock":
                record["values"]["observed_at_us"] += 1
            elif field == "captured-detail":
                details = json.loads(record["values"]["details_json"])
                details["race"] = True
                record["values"]["details_json"] = json.dumps(details)
            else:
                record["values"]["state"] = "partial"
            with receiver.transaction():
                result = Graph(receiver.connection).receive(
                    {**complete, "records": [record]}
                )
            assert result["staged_records"] == 1
            assert dict(selected(receiver)) == before
            assert (
                receiver.one("SELECT reason FROM exchange_staging")[0]
                == "conflict:immutable_content"
            )
