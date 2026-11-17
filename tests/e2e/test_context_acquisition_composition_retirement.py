"""Composed live acquisition boundaries retain actual independent admitted facts."""

import json
import sqlite3
from contextlib import closing
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.application.provider_fetch import acquire_github
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_coordination import CoordinationError
from tests.e2e.test_context_response_boundary_retirement import request_document
from tests.e2e.test_separated_cli import document, init
from tests.e2e.test_separated_cli_provider_inventory import (
    prepare,
    source,
)
from tests.e2e.test_separated_cli_provider_inventory import (
    request as inventory_request,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    _connection,
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def finite_authority(case):
    return create_local_admission_service(
        "provider_intake",
        grants=DependencySet(
            resources=frozenset(case.keys.values()),
            sources={case.source},
            provider_registrations={case.service},
        ),
        selection=AdmissionSelection(all_selected=True),
    )[:2]


def checkpoint_text(case, request):
    with closing(connect(case.directory / "operational.sqlite3", "operational")) as db:
        return repr(
            db.execute(
                "SELECT continuation_scope_json,cursor_json FROM request_continuations "
                "WHERE request_origin_uuidv4=? AND request_uuidv4=? ORDER BY continuation_scope_json",
                request["request_identity"],
            ).fetchall()
        )


@pytest.mark.parametrize("failure", ["sqlite", "recoverable"])
def test_source_second_member_callback_failure_keeps_only_actual_resource_prefix(
    provider_case, tmp_path, capsys, monkeypatch, failure
):
    case = provider_case
    prepare(case, tmp_path, capsys)
    prior_only = ResourceKey.from_native(case.service, "repository", "12")
    case.keys["prior_only"] = prior_only
    case.authority = document(
        tmp_path,
        "three-repository-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()),
                sources={case.source},
                provider_registrations={case.service},
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    changed, stamp = [False], [100]

    def handle(request):
        if request.url.path == "/user":
            return _http_response(
                request, {"login": "owner", "public_repos": 0, "owned_private_repos": 2}
            )
        assert request.url.path == "/user/repos"
        if changed[0]:
            values = [
                {
                    "id": 10,
                    "full_name": "owner/renamed",
                    "private": True,
                    "updated_at": 20,
                },
                {
                    "id": 11,
                    "full_name": "owner/failed-member",
                    "private": True,
                    "updated_at": 20,
                },
            ]
        else:
            values = [
                {
                    "id": 10,
                    "full_name": "owner/repo",
                    "private": True,
                    "updated_at": 10,
                },
                {
                    "id": 12,
                    "full_name": "owner/prior-only",
                    "private": True,
                    "updated_at": 10,
                },
            ]
        return _http_response(request, values)

    original_observe = Context.observe
    visited = []

    def refusing_member(context, observation):
        result = original_observe(context, observation)
        if observation.resource == case.keys["second_repository"]:
            visited.append(observation.resource)
            if failure == "sqlite":
                # Fail real SQLite after this resource's fields were written,
                # still within the actual Provider resource transaction.
                context.db.execute(
                    "INSERT INTO text_bodies(sha256,text_value) VALUES(?,?)",
                    ("0" * 64, "not an admitted body"),
                )
                pytest.fail("The actual content-address constraint must refuse")
            raise CatalogError(
                "SCOPE_MISMATCH", "refused actual second member callback"
            )
        return result

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        initial, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            inventory_request(case),
            clock_us=lambda: stamp[0],
        )
        assert initial["status"] == "complete"
        before = source(capsys, case)
        assert before["provider_repositories"] == [
            list(case.keys["repository"].coordinates()),
            list(prior_only.coordinates()),
        ]
        monkeypatch.setattr(Context, "observe", refusing_member)
        changed[0], stamp[0] = True, 200
        request = inventory_request(case)
        authorization, admission = finite_authority(case)
        if failure == "sqlite":
            with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
                acquire_github(
                    case.directory,
                    request,
                    authorization=authorization,
                    admission=admission,
                    client=client,
                    clock_us=lambda: stamp[0],
                )
        else:
            result = acquire_github(
                case.directory,
                request,
                authorization=authorization,
                admission=admission,
                client=client,
                clock_us=lambda: stamp[0],
            )
            assert (
                result.status == "partial" and result.failure_code == "SCOPE_MISMATCH"
            )
            assert "owner/failed-member" not in repr(result.batches)
    assert visited == [case.keys["second_repository"]]
    after = source(capsys, case)
    assert after["provider_repositories"] == before["provider_repositories"]
    # A genuinely committed first resource is independently usable. The old
    # publication page-wide rollback is deliberately not reconstructed.
    first = case.view(capsys, case.keys["repository"])
    assert [candidate["value"] for candidate in first["fields"]["full_name"]] == [
        "owner/renamed"
    ]
    with Context.snapshot(case.directory) as context:
        assert (
            context.db.execute(
                "SELECT 1 FROM resources WHERE service_instance_uuidv4=? "
                "AND resource_kind=? AND provider_resource_id=?",
                case.keys["second_repository"].coordinates(),
            ).fetchone()
            is None
        )
        assert context.db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 0
    for old in before["inventories"]:
        assert old in after["inventories"]
    new = [item for item in after["inventories"] if item not in before["inventories"]]
    if failure == "sqlite":
        assert new == []
    else:
        assert len(new) == 1 and new[0]["state"] == "partial"
        assert new[0]["provider_repositories"] == [
            list(case.keys["repository"].coordinates())
        ]
    assert "owner/failed-member" not in checkpoint_text(case, request)
    assert not (case.directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "owner_case",
    ["wrong-native-owner", "wrong-opaque-owner", "missing-canonical-owner"],
)
def test_empty_graphql_thread_root_requires_actual_returned_owner_before_proof(
    provider_case, tmp_path, capsys, monkeypatch, owner_case
):
    case, broken, roots = provider_case, [True], []
    expected_opaque = "PR_ACTUAL_20"

    def handle(request):
        if request.method == "POST":
            sent = json.loads(request.content)
            roots.append(sent)
            assert sent["variables"]["number"] == 1
            parent = {"id": expected_opaque, "number": 1, "fullDatabaseId": "20"}
            if broken[0]:
                if owner_case == "wrong-native-owner":
                    parent = {"id": "PR_OTHER_21", "number": 2, "fullDatabaseId": "21"}
                elif owner_case == "wrong-opaque-owner":
                    parent["id"] = "PR_CONTRADICTS_ACTUAL_REST_NODE"
                else:
                    parent = {"id": "PR_UNKNOWN_FROM_REST"}
            parent["reviewThreads"] = _connection([])
            return _http_response(
                request, {"data": {"repository": {"pullRequest": parent}}}
            )
        if request.url.path.endswith("/pulls") or request.url.path.endswith("/pulls/1"):
            parent = {"id": 20, "number": 1}
            if owner_case != "missing-canonical-owner":
                parent["node_id"] = expected_opaque
            return _http_response(
                request, [parent] if request.url.path.endswith("/pulls") else parent
            )
        assert request.url.path == "/repos/owner/repo"
        return _http_response(request, {"id": 10, "full_name": "owner/repo"})

    request = request_document(case)
    request["sections"] = ["review_threads"]
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        failed, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
        assert failed["status"] == "partial" and failed["failure_code"]
        roots_before = case.view(capsys, case.keys["pull"])["collections"]
        assert not any(
            item["collection_kind"] == "review_threads" for item in roots_before
        )
        view = PRQueryService(case.directory).get_pr_documents(
            case.keys["pull"], kinds=("review_threads",)
        )
        assert view.state != "complete" and view.page.items == ()
        broken[0], request["new_request"] = False, False
        succeeded, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, request
        )
    assert succeeded["status"] == "complete" and len(roots) == 2
    original = [
        item
        for item in case.view(capsys, case.keys["pull"])["collections"]
        if item["collection_kind"] == "review_threads"
    ]
    assert len(original) == 1 and original[0]["state"] == "complete"
    assert original[0]["members"] == []
    # The response owner must be selected by the real static GraphQL query,
    # rather than a mock-only key the Provider was never asked to return.
    selected = (
        roots[-1]["query"]
        .split("pullRequest(", 1)[1]
        .split("{", 1)[1]
        .split("reviewThreads", 1)[0]
    )
    assert "number" in selected and "id" in selected
    assert not (case.directory / "p1-recovery-stop.json").exists()


def test_cancelled_actual_rest_prefix_survives_operational_loss_and_fresh_root(
    provider_case, tmp_path, capsys
):
    case, cancelled, resume, calls = provider_case, [False], [False], []
    init(capsys, case.directory, "operational")
    authorization, admission = finite_authority(case)
    request = request_document(case)

    def handle(http):
        path = http.url.path
        if path.endswith("/reviews"):
            page = http.url.params.get("page")
            calls.append(page)
            if page:
                cancelled[0] = not resume[0]
                return _http_response(http, [])
            response = _http_response(
                http, [{"id": 10, "body": "committed\x00prefix", "state": "APPROVED"}]
            )
            response.headers["link"] = (
                '<https://api.example.test/repos/owner/repo/pulls/1/reviews?page=2>; rel="next"'
            )
            return response
        if path.endswith("/pulls"):
            return _http_response(http, [{"id": 20, "number": 1}])
        if path.endswith("/pulls/1"):
            return _http_response(http, {"id": 20, "number": 1})
        assert path == "/repos/owner/repo"
        return _http_response(http, {"id": 10, "full_name": "owner/repo"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        interrupted = acquire_github(
            case.directory,
            request,
            authorization=authorization,
            admission=admission,
            client=client,
            cancelled=lambda: cancelled[0],
            clock_us=lambda: 100,
        )
        assert (
            interrupted.status == "partial" and interrupted.failure_code == "CANCELLED"
        )
        with Context.snapshot(case.directory) as context:
            original = context.candidates(case.keys["review"], "text_body_sha256")
            assert len(original) == 1 and original[0].observed_at_us == 100
            assert (
                context.read_text(json.loads(original[0].value_json))
                == "committed\x00prefix"
            )
        prior = case.view(capsys, case.keys["pull"])["collections"]
        terminal = [item for item in prior if item["collection_kind"] == "reviews"]
        assert len(terminal) == 1 and terminal[0]["state"] == "partial"
        assert terminal[0]["members"] == [list(case.keys["review"].coordinates())]
        (case.directory / "operational.sqlite3").unlink()
        init(capsys, case.directory, "operational")
        cancelled[0], resume[0], request["new_request"] = False, True, False
        before = list(calls)
        with pytest.raises(CoordinationError) as refused:
            acquire_github(
                case.directory,
                request,
                authorization=authorization,
                admission=admission,
                client=client,
                clock_us=lambda: 200,
            )
        assert refused.value.code == "CONTINUATION_UNAVAILABLE" and calls == before
        # Loss does not implicitly renew the old budget. A new explicit request
        # performs a fresh root traversal and receives genuinely new evidence.
        fresh = {
            **request,
            "request_identity": [str(uuid4()), str(uuid4())],
            "new_request": True,
        }
        completed = acquire_github(
            case.directory,
            fresh,
            authorization=authorization,
            admission=admission,
            client=client,
            clock_us=lambda: 200,
        )
    assert completed.status == "complete" and calls == [None, "2", None, "2"]
    with Context.snapshot(case.directory) as context:
        assert set(original) <= set(
            context.candidates(case.keys["review"], "text_body_sha256")
        )
        assert (
            context.read_text(json.loads(original[0].value_json))
            == "committed\x00prefix"
        )
    current = [
        item
        for item in case.view(capsys, case.keys["pull"])["collections"]
        if item["collection_kind"] == "reviews"
    ]
    assert all(item in current for item in terminal)
    assert any(
        item["state"] == "complete" and item["observed_at_us"] == 200
        for item in current
    )
    result = PRQueryService(case.directory).get_pr_documents(
        case.keys["pull"], kinds=("reviews",)
    )
    assert result.state == "complete" and len(result.page.items) == 1
    assert not (case.directory / "core.sqlite3").exists()
    assert not (case.directory / "p1-recovery-stop.json").exists()


def test_idless_timeline_does_not_block_independently_verified_exact_code(
    provider_case, tmp_path, capsys, monkeypatch
):
    from repo_catalog.adapters.github.production_intake import (
        normalize_pr_commit,
        normalize_pr_file,
        normalize_timeline_event,
    )
    from repo_catalog.domain.provider_acquisition import make_provenance
    from tests.e2e.test_separated_cli_github_git_roles import setup
    from tests.e2e.test_separated_cli_pr_assessment import query

    case = provider_case
    _, objects, request, ordinary, calls = setup(case, tmp_path, capsys)
    original = make_provenance("fixture", "finite-independent-scope-grants")
    event = normalize_timeline_event(
        case.service,
        "pull_request",
        "20",
        30,
        {"id": 30, "event": "closed"},
        1,
        original,
    ).primary_resource
    commit = normalize_pr_commit(
        case.service, "20", {"sha": objects["commit2"].object_oid}, 1, original
    ).primary_resource
    file = normalize_pr_file(
        case.service, "20", {"filename": "README.md", "status": "modified"}, 1, original
    ).primary_resource
    case.authority = document(
        tmp_path,
        "timeline-and-code-authority.json",
        {
            "grants": DependencySet(
                resources=frozenset(case.keys.values()) | {event, commit, file},
                sources={
                    case.source,
                    request["git_source"]["source_registration_uuidv4"],
                },
                provider_registrations={case.service},
                object_oids=frozenset(objects.values()),
            ),
            "selection": AdmissionSelection(all_selected=True),
        },
    )
    request["sections"].append("timeline")
    timeline_calls = []

    def handle(http):
        if http.url.path.endswith("/issues"):
            return _http_response(http, [])
        if http.url.path.endswith("/timeline"):
            timeline_calls.append(http.url.path)
            return _http_response(
                http,
                [
                    {"id": 30, "event": "closed"},
                    {"event": "committed", "sha": objects["commit2"].object_oid},
                ],
            )
        return ordinary(http)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert (
        report["status"] == "partial"
        and report["failure_code"] == "CANONICAL_ID_REQUIRED"
    )
    assert timeline_calls == ["/repos/owner/repo/issues/1/timeline"]
    assert "/repos/owner/repo/pulls/1/commits" in calls
    assert "/repos/owner/repo/pulls/1/files" in calls
    assert report["git_reports"]
    code = query(capsys, case, "pr-code")
    assert (
        code["state"] == "complete" and code["coverage"]["complete_for_requested_scope"]
    )
    timeline = [
        item
        for item in case.view(capsys, case.keys["pull"])["collections"]
        if item["collection_kind"] == "timeline"
    ]
    assert len(timeline) == 1 and timeline[0]["state"] == "partial"
    assert timeline[0]["members"] == [list(event.coordinates())]
    with Context.snapshot(case.directory) as context:
        assert (
            context.db.execute(
                "SELECT count(*) FROM resources WHERE resource_kind='comment'"
            ).fetchone()[0]
            == 1
        )
    assert not (case.directory / "p1-recovery-stop.json").exists()
