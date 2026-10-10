"""Live typed admission does not depend on Publication or API originals."""

import json

import httpx
import pytest

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime as github_runtime


def job(store):
    ident = JobService(store).create("sync", {"kind": "pr"})
    store.expected_attempt = 1
    return ident


def pr_value(oid, *, body="body", clock="2026-01-01T00:00:00Z"):
    return {
        "id": 1101,
        "number": 1,
        "title": "title",
        "body": body,
        "state": "open",
        "updated_at": clock,
        "head": {"sha": oid},
        "base": {"sha": oid},
        "unmodeled_provider_extension": {"secret": "must not persist"},
    }


def collector(store):
    value = GitHubCollector(store, CancellationToken())
    value.facts.principal = "10"
    return value


def seed_pr(store, repo, oid):
    value = collector(store)
    task = job(store)
    url = value.http.base + "/repos/fixture/alpha/pulls"
    revision = store.revision()
    with store.transaction():
        scope = value.facts.begin(repo, None, "pr-list", task, url)
        ident, members = value.ensure_pr(repo, pr_value(oid), scope, revision, 0, 100)
        value.facts.page(scope, 100, None, members)
        value.facts.finish(scope)
        value.facts.advance_revision()
    return value, ident, task


def test_latest_pr_documents_without_publication_or_originals(github_runtime):
    store, repo, fixture, _ = github_runtime
    value, ident, task = seed_pr(store, repo, fixture.alpha.commits["N"])
    revision = store.revision()
    newer = pr_value(
        fixture.alpha.commits["N"], body="new body", clock="2026-02-01T00:00:00Z"
    )
    newer.pop("title")
    # Parsing sparse metadata and document values preserves the existing title.
    from repo_catalog.adapters.github import current_parser

    capture = value.facts.current_context(repo, ident, value.http.base + "/pulls/1")
    with store.transaction():
        for kind in ("pr-title", "pr-body"):
            value.facts.admit_current(
                current_parser.document(newer, capture, 200, kind), revision
            )
        value.facts.advance_revision()
    rows = {
        row["kind"]: row
        for row in store.all(
            "SELECT r.*,b.body FROM document_state r LEFT JOIN text_bodies b ON b.sha256=r.text_body_sha256"
        )
    }
    assert rows["pr-title"]["body"] == "title"
    assert rows["pr-body"]["body"] == "new body"
    title_evidence = json.loads(rows["pr-title"]["field_evidence_json"])[
        json.dumps(["body"], separators=(",", ":"))
    ]
    assert title_evidence["observed_at_us"] == 100
    names = {
        row[0] for row in store.all("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert (
        not {
            "parsed_results",
            "parsed_result_publications",
            "fetch_occurrences",
            "document_observations",
            "source_input_observations",
        }
        & names
    )
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
    assert (
        "must not persist"
        not in store.one("SELECT metadata FROM change_request_state")[0]
    )


def test_valid_pr_prefix_survives_later_page_rejection(github_runtime):
    store, repo, fixture, api = github_runtime
    value = collector(store)
    task = job(store)
    url = api.url + "/repos/fixture/alpha/pulls"

    def route(method, path, params, body):
        if params.get("page") == ["2"]:
            return [{"id": 1202, "number": 2, "title": []}], {}
        return [pr_value(fixture.alpha.commits["N"])], {
            "Link": f'<{url}?page=2>; rel="next"'
        }

    api.route = route

    def normalize(item, collection, revision, position, timestamp, listing):
        return value.ensure_pr(repo, item, collection, revision, position, timestamp)[1]

    with pytest.raises(CatalogError, match="malformed"):
        value.collection(repo, None, "pr-list", task, url, normalize)
    assert store.one("SELECT count(*) FROM eligible_change_request_state")[0] == 1
    assert store.one("SELECT count(*) FROM change_requests")[0] == 1
    assert (
        store.one("SELECT coverage_state FROM current_coverage WHERE kind='pr-list'")[0]
        == "partial"
    )
    assert store.one("SELECT count(*) FROM current_collection_pages")[0] == 1


def test_empty_thread_terminal_and_observed_null_targets(github_runtime):
    store, repo, fixture, api = github_runtime
    value, ident, task = seed_pr(store, repo, fixture.alpha.commits["N"])

    def route(method, path, params, body):
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "id": "PR_1",
                        "mergeCommit": None,
                        "potentialMergeCommit": None,
                        "reviewThreads": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        },
                    }
                }
            }
        }, {}

    api.route = route
    parent = store.one(
        "SELECT * FROM change_requests WHERE change_request_id=?", (ident,)
    )
    assert value.threads(repo, parent, task) == {"merge": None, "test-merge": None}
    assert value.saved_thread_code_input(ident)[1] is True
    assert (
        store.one("SELECT coverage_state FROM current_coverage WHERE kind='threads'")[0]
        == "complete"
    )
    assert store.one("SELECT count(*) FROM thread_collection_targets")[0] == 2
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0


def test_thread_children_resume_from_normalized_committed_prefix(github_runtime):
    store, repo, fixture, api = github_runtime
    value, ident, task = seed_pr(store, repo, fixture.alpha.commits["N"])
    attempts = {"root": 0, "child": 0}

    def comment(ident):
        return {
            "fullDatabaseId": ident,
            "body": f"comment {ident}",
            "updatedAt": "2026-01-01T00:00:00Z",
        }

    def route(method, path, params, body):
        if "RepoCatalogThreads" in body["query"]:
            attempts["root"] += 1
            return {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "id": "PR_1",
                            "mergeCommit": None,
                            "potentialMergeCommit": None,
                            "reviewThreads": {
                                "nodes": [
                                    {
                                        "id": "THREAD_1",
                                        "isResolved": False,
                                        "isOutdated": False,
                                        "comments": {
                                            "nodes": [comment(1201)],
                                            "pageInfo": {
                                                "hasNextPage": True,
                                                "endCursor": "child-next",
                                            },
                                        },
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            },
                        }
                    }
                }
            }, {}
        assert body["variables"]["thread"] == "THREAD_1"
        assert body["variables"]["commentCursor"] == "child-next"
        attempts["child"] += 1
        if attempts["child"] == 1:
            return {"errors": [{"message": "temporary"}]}, {}
        return {
            "data": {
                "node": {
                    "id": "THREAD_1",
                    "comments": {
                        "nodes": [comment(1202)],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    },
                }
            }
        }, {}

    api.route = route
    parent = store.one(
        "SELECT * FROM change_requests WHERE change_request_id=?", (ident,)
    )
    with pytest.raises(CatalogError):
        value.threads(repo, parent, task)
    assert store.one("SELECT count(*) FROM review_resources")[0] == 1
    value.threads(repo, parent, task)
    assert attempts["root"] == 1
    assert attempts["child"] == 2
    assert store.one("SELECT count(*) FROM review_resources")[0] == 2
    assert (
        store.one("SELECT coverage_state FROM current_coverage WHERE kind='threads'")[0]
        == "complete"
    )
    assert store.one("PRAGMA foreign_key_check") is None


def test_304_without_corresponding_state_fetches_fresh_response(
    github_runtime, monkeypatch
):
    store, repo, fixture, api = github_runtime
    value, ident, task = seed_pr(store, repo, fixture.alpha.commits["N"])
    calls = []

    def request(method, url, **kwargs):
        assert not store.connection.in_transaction
        calls.append(url)
        return httpx.Response(
            304 if len(calls) == 1 else 200,
            json=None
            if len(calls) == 1
            else pr_value(
                fixture.alpha.commits["N"], body="fetched", clock="2026-02-01T00:00:00Z"
            ),
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(value.http, "request", request)
    parent = store.one(
        "SELECT * FROM change_requests WHERE change_request_id=?", (ident,)
    )
    value.detail(repo, parent, task, api.url + "/repos/fixture/alpha/pulls/1")
    assert len(calls) == 2
    assert (
        store.one(
            "SELECT b.body FROM document_state r JOIN text_bodies b ON b.sha256=r.text_body_sha256 WHERE r.kind='pr-body'"
        )[0]
        == "fetched"
    )


def test_full_pr_sync_direct_resources_and_comparison_anchors(github_runtime):
    from tests.support.github_runtime import sync

    store, repo, _, api = github_runtime
    try:
        sync(store, repo)
    except CatalogError as error:
        pytest.fail(repr(error.details))
    assert store.one("SELECT count(*) FROM eligible_change_request_state")[0] == 3
    assert (
        store.one("SELECT count(*) FROM code_assessments WHERE state='complete'")[0]
        == 3
    )
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
    assert (
        store.one("SELECT 1 FROM payloads WHERE representation<>'git-object-raw-v1'")
        is None
    )
    assert store.all("PRAGMA foreign_key_check") == []


def test_identityless_event_multiplicity_is_explicit_and_scope_partial(github_runtime):
    store, repo, fixture, api = github_runtime
    value, ident, task = seed_pr(store, repo, fixture.alpha.commits["N"])
    api.route = lambda method, path, params, body: (
        [{"event": "referenced"}, {"event": "referenced"}],
        {},
    )

    def normalize(item, collection, revision, position, timestamp, listing):
        return [value._event(repo, ident, item, timestamp)]

    with pytest.raises(CatalogError) as error:
        value.collection(
            repo, ident, "timeline", task, api.url + "/timeline", normalize
        )
    assert error.value.code == "CURRENT_STATE_UNRESOLVED"
    # Two actually observed entries survive with unavailable provider identity;
    # the application cannot conclude whether they identify distinct occurrences.
    assert (
        store.one(
            "SELECT count(*) FROM change_request_events WHERE provider_event_id IS NULL"
        )[0]
        == 2
    )
    assert store.one("SELECT count(*) FROM eligible_change_request_state")[0] == 1
    assert (
        store.one("SELECT coverage_state FROM current_coverage WHERE kind='timeline'")[
            0
        ]
        == "partial"
    )
    assert (
        store.one(
            "SELECT 1 FROM completion_markers m JOIN fetch_collections c USING(fetch_collection_id) WHERE c.kind='timeline' AND m.asserted_state='complete'"
        )
        is None
    )


def test_timeline_ambiguity_does_not_downgrade_independent_code(github_runtime):
    from tests.support.github_runtime import sync

    store, repo, _, api = github_runtime
    original = api.route

    def route(method, path, params, body):
        if path.endswith("/timeline"):
            return [{"event": "referenced", "actor": {"login": "writer"}}], {}
        return original(method, path, params, body)

    api.route = route
    with pytest.raises(CatalogError) as error:
        sync(store, repo)
    assert error.value.code == "PR_PARTIAL"
    assert (
        store.one("SELECT count(*) FROM code_assessments WHERE state='complete'")[0]
        == 3
    )
    assert (
        store.one(
            "SELECT coverage_state FROM current_coverage WHERE kind='pr-code' AND change_request_id IS NULL"
        )[0]
        == "complete"
    )
    assert (
        store.one(
            "SELECT count(*) FROM change_request_events WHERE provider_event_id IS NULL"
        )[0]
        == 3
    )


def test_unobserved_same_target_check_failure_preserves_accepted_code(
    github_runtime, monkeypatch
):
    from tests.support.github_runtime import sync

    store, repo, _, _ = github_runtime
    sync(store, repo)
    before = [
        tuple(row)
        for row in store.all(
            "SELECT * FROM code_assessments ORDER BY code_assessment_id"
        )
    ]
    claims = [
        tuple(row)
        for row in store.all(
            "SELECT coverage_scope_id,coverage_state,observed_at_us FROM current_coverage WHERE kind='pr-code' AND change_request_id IS NOT NULL ORDER BY coverage_scope_id"
        )
    ]

    def fail(*args):
        raise CatalogError("HTTP_ERROR", "Synthetic failure before target observation")

    monkeypatch.setattr(GitHubCollector, "code_check", fail)
    with pytest.raises(CatalogError) as error:
        sync(store, repo)
    assert error.value.code == "PR_PARTIAL"
    assert [
        tuple(row)
        for row in store.all(
            "SELECT * FROM code_assessments ORDER BY code_assessment_id"
        )
    ] == before
    assert [
        tuple(row)
        for row in store.all(
            "SELECT coverage_scope_id,coverage_state,observed_at_us FROM current_coverage WHERE kind='pr-code' AND change_request_id IS NOT NULL ORDER BY coverage_scope_id"
        )
    ] == claims
    assert not store.all("PRAGMA foreign_key_check")


def test_source_discovery_partial_prefix_keeps_known_absent_repository(github_runtime):
    from repo_catalog.application.collection_service import CollectionService

    store, repo, fixture, api = github_runtime
    service = CollectionService(store.path)
    original = api.route

    def initial_route(method, path, params, body):
        if path == "/user":
            return {"login": "fixture", "public_repos": 0, "owned_private_repos": 2}, {}
        if path == "/user/repos":
            return [
                {
                    "id": 101,
                    "full_name": "fixture/alpha",
                    "clone_url": fixture.alpha.url,
                    "private": True,
                },
                {
                    "id": 102,
                    "full_name": "fixture/beta",
                    "clone_url": fixture.alpha.url,
                    "private": True,
                },
            ], {}
        return original(method, path, params, body)

    api.route = initial_route
    initial = service.discover("source")
    assert initial.status == "complete"
    known = {
        row["repository_uuidv4"]: row["name"]
        for row in store.all(
            "SELECT repository_uuidv4,name FROM source_repositories WHERE source_id='source'"
        )
    }
    assert len(known) == 2

    def route(method, path, params, body):
        if path == "/user/repos":
            if params.get("page") == ["2"]:
                return [
                    {
                        "id": 999,
                        "full_name": "foreign/outside",
                        "clone_url": fixture.alpha.url,
                    }
                ], {}
            return [
                {
                    "id": 101,
                    "full_name": "fixture/alpha",
                    "clone_url": fixture.alpha.url,
                }
            ], {"Link": f'<{api.url}/user/repos?page=2>; rel="next"'}
        return original(method, path, params, body)

    api.route = route
    partial = service.discover("source")
    assert partial.status == "partial"
    assert partial.data["repositories"] == [
        {"repository_uuidv4": repo["repository_uuidv4"], "name": "fixture/alpha"}
    ]
    assert {
        row["repository_uuidv4"]: row["name"]
        for row in store.all(
            "SELECT repository_uuidv4,name FROM source_repositories WHERE source_id='source'"
        )
    } == known
    inventory = store.one(
        "SELECT * FROM source_inventory_assessments ORDER BY observed_at_us DESC LIMIT 1"
    )
    assert inventory["state"] == "partial"
    assert json.loads(inventory["members_json"]) == [repo["repository_uuidv4"]]
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
    assert not store.all("PRAGMA foreign_key_check")


def test_source_discovery_midpage_callback_failure_rolls_back_members(github_runtime):
    import sqlite3

    from repo_catalog.application.collection_service import CollectionService

    store, repo, fixture, api = github_runtime
    service = CollectionService(store.path)
    assert service.discover("source").status == "complete"
    before = [
        tuple(row)
        for row in store.all(
            "SELECT * FROM source_repositories ORDER BY repository_uuidv4"
        )
    ]
    original = api.route

    def route(method, path, params, body):
        if path == "/user/repos":
            return [
                {
                    "id": 101,
                    "full_name": "fixture/alpha-renamed",
                    "clone_url": fixture.alpha.url,
                },
                {
                    "id": 999,
                    "full_name": "fixture/rejected",
                    "clone_url": fixture.alpha.url,
                },
            ], {}
        return original(method, path, params, body)

    api.route = route
    with store.transaction():
        store.execute(
            "CREATE TRIGGER injected_discovery_failure BEFORE INSERT ON repositories WHEN NEW.name='fixture/rejected' BEGIN SELECT RAISE(ABORT,'Injected callback failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="Injected callback failure"):
        service.discover("source")
    assert [
        tuple(row)
        for row in store.all(
            "SELECT * FROM source_repositories ORDER BY repository_uuidv4"
        )
    ] == before
    assert not store.one("SELECT 1 FROM repositories WHERE name='fixture/rejected'")
    assert not store.one(
        "SELECT 1 FROM source_repositories WHERE name='fixture/alpha-renamed'"
    )
    latest = store.one(
        "SELECT checkpoint FROM job_attempts ORDER BY rowid DESC LIMIT 1"
    )
    assert latest is None or latest[0] is None or "alpha-renamed" not in latest[0]
    assert not store.all("PRAGMA foreign_key_check")


def test_source_discovery_recoverable_callback_failure_has_no_phantom_result(
    github_runtime, monkeypatch
):
    from repo_catalog.adapters.sqlite.current_api import CurrentApiState
    from repo_catalog.application.collection_service import CollectionService

    store, repo, fixture, api = github_runtime
    service = CollectionService(store.path)
    assert service.discover("source").status == "complete"
    before = [tuple(row) for row in store.all("SELECT * FROM source_repositories")]
    assessment_count = store.one("SELECT count(*) FROM source_inventory_assessments")[0]
    original_route = api.route
    original_confirm = CurrentApiState.confirm_source_repository

    def route(method, path, params, body):
        if path == "/user/repos":
            return [
                {
                    "id": 101,
                    "full_name": "fixture/alpha-renamed",
                    "clone_url": fixture.alpha.url,
                },
                {
                    "id": 999,
                    "full_name": "fixture/rejected",
                    "clone_url": fixture.alpha.url,
                },
            ], {}
        return original_route(method, path, params, body)

    def confirm(self, *args, **kwargs):
        if kwargs["name"] == "fixture/rejected":
            raise CatalogError("SCOPE_MISMATCH", "Synthetic midpage callback rejection")
        return original_confirm(self, *args, **kwargs)

    api.route = route
    monkeypatch.setattr(CurrentApiState, "confirm_source_repository", confirm)
    result = service.discover("source")
    assert result.status == "partial"
    assert result.data["repositories"] == []
    assert [
        tuple(row) for row in store.all("SELECT * FROM source_repositories")
    ] == before
    assert (
        store.one("SELECT count(*) FROM source_inventory_assessments")[0]
        == assessment_count
    )
    assert not store.one("SELECT 1 FROM repositories WHERE name='fixture/rejected'")
    assert not store.all("PRAGMA foreign_key_check")
