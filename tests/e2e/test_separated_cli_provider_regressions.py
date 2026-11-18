"""Provider regression obligations at ordinary separated CLI/admission boundaries."""

import hashlib
import json
from dataclasses import dataclass, replace
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.github import production_intake as normalize
from repo_catalog.domain.context_admission import AdmissionSelection, DependencySet
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.provider_acquisition import (
    ProviderIntakeBatch,
    ProviderIssueIntake,
    ProviderRegistration,
    ProviderReviewCommentIntake,
    ProviderReviewIntake,
    make_provenance,
)
from tests.e2e.test_separated_cli import document, init, run, wire


@dataclass
class ProviderFixture:
    directory: object
    service: str
    source: str
    authority: str
    keys: dict
    query_sql_steps: int = 5_000_000

    def batch(self, **sections):
        return ProviderIntakeBatch(
            self.service, providers=(ProviderRegistration(self.service),), **sections
        )

    def admit(self, tmp_path, capsys, **sections):
        path = document(tmp_path, "provider-input.json", self.batch(**sections))
        return run(
            capsys,
            "acquire",
            "provider",
            "--catalog",
            self.directory,
            "--input",
            path,
            "--authority",
            self.authority,
        )

    def view(self, capsys, key):
        return run(
            capsys,
            "query",
            "context-resource",
            "--catalog",
            self.directory,
            "--service",
            key.service_instance_uuidv4,
            "--kind",
            key.resource_kind,
            "--id",
            key.provider_resource_id,
            "--max-sql-steps",
            self.query_sql_steps,
        )


@pytest.fixture
def provider_case(tmp_path, capsys):
    directory = tmp_path / "context"
    init(capsys, directory, "context")
    service, source = str(uuid4()), str(uuid4())
    keys = {
        "issue": ResourceKey.from_native(service, "issue", "100"),
        "other_issue": ResourceKey.from_native(service, "issue", "101"),
        "pull": ResourceKey.from_native(service, "pull_request", "20"),
        "other_pull": ResourceKey.from_native(service, "pull_request", "21"),
        "repository": ResourceKey.from_native(service, "repository", "10"),
    }
    for kind, subtype, ident, label in (
        ("review", "review_summary", "10", "review"),
        ("comment", "review_comment", "10", "comment"),
        ("comment", "review_comment", "11", "reply"),
        ("thread", "thread", "thread-one", "thread"),
        ("thread", "thread", "thread-two", "other_thread"),
        ("document", "pr_body", "20", "pr_body"),
        ("document", "pr_title", "20", "pr_title"),
    ):
        keys[label] = ResourceKey.document(keys["pull"], kind, subtype, ident)
    keys["other_comment"] = ResourceKey.document(
        keys["other_pull"], "comment", "review_comment", "10"
    )
    grants = DependencySet(
        resources=frozenset(keys.values()),
        sources=frozenset({source}),
        provider_registrations=frozenset({service}),
    )
    authority = document(
        tmp_path,
        "provider-authority.json",
        {"grants": grants, "selection": AdmissionSelection(all_selected=True)},
    )
    return ProviderFixture(directory, service, source, authority, keys)


def values(view, field):
    return [candidate["value"] for candidate in view["fields"].get(field, [])]


def issue(payload, step="original", *, observed=10):
    return ProviderIssueIntake(
        payload, observed, make_provenance("local-provider", {"step": step})
    )


@pytest.mark.parametrize("kind", ["issue", "review", "review-comment"])
@pytest.mark.parametrize(
    "identifier",
    [None, "0", "01", "1\x00hidden", "１２３", "1 "],
    ids=["null", "zero", "leading-zero", "nul", "non-ascii", "space"],
)
def test_provider_database_id_is_checked_before_cli_admission(
    provider_case, tmp_path, capsys, kind, identifier
):
    case = provider_case
    provenance = make_provenance("local-provider", "invalid-id")
    if kind == "issue":
        sections = {"issues": (ProviderIssueIntake({"id": identifier}, 1, provenance),)}
    elif kind == "review":
        sections = {
            "reviews": (ProviderReviewIntake("20", {"id": identifier}, 1, provenance),)
        }
    else:
        sections = {
            "review_comments": (
                ProviderReviewCommentIntake("20", {"id": identifier}, 1, provenance),
            )
        }
    path = document(tmp_path, "invalid-id.json", case.batch(**sections))
    error = run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        case.directory,
        "--input",
        path,
        "--authority",
        case.authority,
        expected=2,
    )
    assert error["code"] == "CANONICAL_ID_REQUIRED"
    assert (
        run(capsys, "query", "context-resources", "--catalog", case.directory)["items"]
        == []
    )
    assert not (case.directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("field", ["commit_id", "original_commit_id"])
def test_review_oid_nul_suffix_cannot_create_nominal_repository_dependency(
    provider_case, tmp_path, capsys, field
):
    case = provider_case
    intake = ProviderReviewCommentIntake(
        "20",
        {"id": 10, field: "a" * 40 + "\x00hidden"},
        1,
        make_provenance("local-provider", "bad-oid"),
    )
    path = document(tmp_path, "bad-oid.json", case.batch(review_comments=(intake,)))
    error = run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        case.directory,
        "--input",
        path,
        "--authority",
        case.authority,
        expected=2,
    )
    assert error["code"] == "INVALID_GIT_OID"
    assert (
        run(capsys, "query", "context-resources", "--catalog", case.directory)["items"]
        == []
    )
    assert not (case.directory / "repository.sqlite3").exists()


def test_sparse_projection_preserves_omitted_exact_text_and_known_fields(
    provider_case, tmp_path, capsys
):
    case = provider_case
    original = {
        "id": 100,
        "title": "preserved title",
        "body": "exact\nbody\x00suffix",
        "state": "open",
        "updated_at": 10,
        "labels": [{"name": "retained"}],
        "milestone": {"title": "retained", "state": "open"},
    }
    case.admit(tmp_path, capsys, issues=(issue(original),))
    before = case.view(capsys, case.keys["issue"])
    case.admit(
        tmp_path,
        capsys,
        issues=(
            issue(
                {"id": 100, "state": "closed", "updated_at": 20}, "sparse", observed=20
            ),
        ),
    )
    after = case.view(capsys, case.keys["issue"])
    assert list(after["resolved_texts"].values()) == [original["body"]]
    assert values(after, "title") == ["preserved title"]
    assert values(after, "labels") == [[{"name": "retained"}]]
    assert values(after, "milestone") == [{"title": "retained", "state": "open"}]
    assert values(after, "state") == ["closed"]
    assert after["fields"]["text_body_sha256"] == before["fields"]["text_body_sha256"]


@pytest.mark.parametrize("parser_version", ["0", "2", "999999999999"])
def test_equal_clock_alternatives_never_rank_by_observed_time_or_external_decoder(
    provider_case, tmp_path, capsys, parser_version
):
    case = provider_case
    first = issue({"id": 100, "body": "first", "updated_at": 20}, "first", observed=21)
    second = ProviderIssueIntake(
        {"id": 100, "body": "second", "updated_at": 20},
        2**60,
        make_provenance(
            "different-attributed-decoder", {"external_parser_version": parser_version}
        ),
    )
    case.admit(tmp_path, capsys, issues=(first, second))
    view = case.view(capsys, case.keys["issue"])
    assert set(view["resolved_texts"].values()) == {"first", "second"}
    candidates = view["fields"]["text_body_sha256"]
    assert len(candidates) == 2
    assert {candidate["clock"]["at_us"] for candidate in candidates} == {20}
    assert {candidate["observed_at_us"] for candidate in candidates} == {21, 2**60}
    assert all("preferred_decoder" not in candidate for candidate in candidates)
    case.admit(
        tmp_path,
        capsys,
        issues=(
            issue({"id": 100, "body": "newer", "updated_at": 30}, "newer", observed=31),
        ),
    )
    assert list(case.view(capsys, case.keys["issue"])["resolved_texts"].values()) == [
        "newer"
    ]
    assert not (case.directory / "operational.sqlite3").exists()


def test_missing_provider_clock_is_neither_zero_nor_receiver_freshness(
    provider_case, tmp_path, capsys
):
    case = provider_case
    case.admit(
        tmp_path,
        capsys,
        issues=(issue({"id": 100, "body": "known", "updated_at": 10}, "known"),),
    )
    case.admit(
        tmp_path,
        capsys,
        issues=(issue({"id": 100, "body": "unknown"}, "unknown", observed=2**60),),
    )
    view = case.view(capsys, case.keys["issue"])
    assert set(view["resolved_texts"].values()) == {"known", "unknown"}
    assert {
        candidate["clock"]["at_us"] for candidate in view["fields"]["text_body_sha256"]
    } == {None, 10}
    with pytest.raises(ValueError):
        normalize.normalize_issue(
            case.service,
            {"id": 100, "updated_at": 0},
            1,
            make_provenance("local-provider", "zero-is-invalid-provider-time"),
        )


def test_replay_cannot_rebind_original_observation_time(
    provider_case, tmp_path, capsys
):
    case = provider_case
    original = issue(
        {"id": 100, "body": "immutable original", "updated_at": 10},
        "same-original",
        observed=11,
    )
    case.admit(tmp_path, capsys, issues=(original,))
    before = case.view(capsys, case.keys["issue"])
    changed = replace(original, observed_at_us=12)
    path = document(tmp_path, "rebound.json", case.batch(issues=(changed,)))
    run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        case.directory,
        "--input",
        path,
        "--authority",
        case.authority,
        expected=2,
    )
    assert case.view(capsys, case.keys["issue"]) == before
    case.admit(tmp_path, capsys, issues=(original,))
    assert case.view(capsys, case.keys["issue"]) == before


def test_actual_parent_reports_do_not_come_from_identifier_namespace_or_rebind(
    provider_case, tmp_path, capsys
):
    from repo_catalog.domain.production_context import ResourceRelation

    case = provider_case
    provenance = make_provenance("local-provider", "comment-capture")
    case.admit(
        tmp_path,
        capsys,
        review_comments=(
            ProviderReviewCommentIntake(
                "20", {"id": 10, "body": "comment"}, 10, provenance
            ),
        ),
    )
    query = document(
        tmp_path,
        "namespace-query.json",
        {
            "kwargs": {
                "resource_kind": "comment",
                "identifier_namespace": case.keys["pull"],
            }
        },
    )
    assert (
        len(
            run(
                capsys,
                "query",
                "resources",
                "--catalog",
                case.directory,
                "--input",
                query,
            )["items"]
        )
        == 1
    )
    query = document(
        tmp_path, "parent-query.json", {"kwargs": {"parent": case.keys["pull"]}}
    )
    assert (
        run(
            capsys, "query", "resources", "--catalog", case.directory, "--input", query
        )["items"]
        == []
    )
    # A semantic Parent is a separately supplied original, not an identifying namespace.
    scope = canonical(
        {
            "clock": {"domain": "provider-parent", "at_us": 10},
            "document_kind": "review_comment",
            "state": "complete",
        }
    )
    relation = ResourceRelation(
        case.keys["comment"], "parent", (case.keys["pull"],), provenance, scope, 10
    )
    case.admit(tmp_path, capsys, relations=(relation,))
    original = case.view(capsys, case.keys["comment"])
    assert (
        len(
            run(
                capsys,
                "query",
                "resources",
                "--catalog",
                case.directory,
                "--input",
                query,
            )["items"]
        )
        == 1
    )
    rebound = replace(relation, observed_at_us=11)
    payload = document(
        tmp_path, "rebound-parent.json", case.batch(relations=(rebound,))
    )
    run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        case.directory,
        "--input",
        payload,
        "--authority",
        case.authority,
        expected=2,
    )
    assert case.view(capsys, case.keys["comment"]) == original


@pytest.mark.parametrize(
    "attack",
    [
        "null-parent",
        "wrong-kind-parent",
        "cross-service-parent",
        "wrong-number",
        "null-scope-service",
    ],
)
def test_parent_declared_scope_and_full_resource_key_resist_invalid_input(
    provider_case, tmp_path, capsys, attack
):
    from repo_catalog.domain.production_context import ResourceRelation

    case = provider_case
    provenance = make_provenance("local-provider", "parent-invalid")
    relation = ResourceRelation(
        case.keys["comment"],
        "parent",
        (case.keys["pull"],),
        provenance,
        canonical(
            {
                "clock": {"domain": "provider-parent", "at_us": 10},
                "document_kind": "review_comment",
                "state": "complete",
            }
        ),
        10,
    )
    encoded = wire(case.batch(relations=(relation,)))
    target = encoded["fields"]["relations"][0]["fields"]
    if attack == "null-parent":
        target["members"] = []
    elif attack == "wrong-kind-parent":
        target["members"] = [wire(case.keys["comment"])]
    elif attack == "cross-service-parent":
        target["members"][0]["fields"]["service_instance_uuidv4"] = str(uuid4())
    elif attack == "wrong-number":
        scope = json.loads(target["scope_json"])
        scope["provider_issue_number"] = 2
        target["scope_json"] = canonical(scope)
    else:
        target["members"][0]["fields"]["service_instance_uuidv4"] = None
    path = tmp_path / "invalid-parent.json"
    path.write_text(json.dumps(encoded))
    run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        case.directory,
        "--input",
        path,
        "--authority",
        case.authority,
        expected=2,
    )
    assert (
        run(capsys, "query", "context-resources", "--catalog", case.directory)["items"]
        == []
    )


def test_collection_membership_never_crosses_full_provider_namespace(
    provider_case, tmp_path, capsys
):
    from repo_catalog.domain.production_context import CollectionObservation

    case = provider_case
    provenance = make_provenance("local-provider", "two-independent-parents")
    case.admit(
        tmp_path,
        capsys,
        review_comments=(
            ProviderReviewCommentIntake("20", {"id": 10}, 10, provenance),
            ProviderReviewCommentIntake("21", {"id": 10}, 10, provenance),
        ),
    )
    before = case.view(capsys, case.keys["pull"])
    observation = CollectionObservation(
        case.keys["pull"],
        "comments",
        provenance,
        "{}",
        10,
        "complete",
        (case.keys["other_comment"],),
    )
    path = document(
        tmp_path, "wrong-owner-collection.json", case.batch(collections=(observation,))
    )
    error = run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        case.directory,
        "--input",
        path,
        "--authority",
        case.authority,
        expected=2,
    )
    assert error["code"] == "MEMBER_OWNER"
    assert case.view(capsys, case.keys["pull"]) == before


def test_original_collection_receipt_survives_later_document_body_edits(
    provider_case, tmp_path, capsys
):
    from repo_catalog.domain.production_context import CollectionObservation

    case = provider_case
    provenance = make_provenance("local-provider", "first-page")
    comment = ProviderReviewCommentIntake(
        "20", {"id": 10, "body": "original body", "updated_at": 10}, 10, provenance
    )
    observation = CollectionObservation(
        case.keys["pull"],
        "comments",
        provenance,
        '{"scope":"original"}',
        10,
        "complete",
        (case.keys["comment"],),
    )
    case.admit(tmp_path, capsys, review_comments=(comment,), collections=(observation,))
    before = case.view(capsys, case.keys["pull"])["collections"]
    case.admit(
        tmp_path,
        capsys,
        review_comments=(
            replace(
                comment,
                payload={"id": 10, "body": "edited body", "updated_at": 20},
                observed_at_us=20,
                provenance_json=make_provenance("local-provider", "edit"),
            ),
        ),
    )
    assert list(case.view(capsys, case.keys["comment"])["resolved_texts"].values()) == [
        "edited body"
    ]
    assert case.view(capsys, case.keys["pull"])["collections"] == before
    assert before[0]["members"] == [list(case.keys["comment"].coordinates())]
    assert before[0]["state"] == "complete"


def test_operational_completion_cannot_manufacture_context_collection_coverage(
    provider_case, tmp_path, capsys
):
    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
    from repo_catalog.domain.p1_coordination import RequestIdentity

    case = provider_case
    case.admit(tmp_path, capsys, issues=(issue({"id": 100, "body": "known"}),))
    init(capsys, case.directory, "operational")
    request = RequestIdentity(str(uuid4()), str(uuid4()))
    with OperationalAcquisitionLedger(case.directory) as ledger:
        ledger.ensure_request(request, scope=["only-progress"], new_request=True)
        ledger.save_continuation(
            request,
            ["fake-completion"],
            {"state": "complete", "members": [list(case.keys["issue"].coordinates())]},
        )
    view = case.view(capsys, case.keys["issue"])
    assert view["collections"] == []
    assert not (case.directory / "repository.sqlite3").exists()


def _http_response(request, value):
    return httpx.Response(
        200, request=request, stream=httpx.ByteStream(json.dumps(value).encode())
    )


def _connection(nodes, *, next_cursor=None):
    return {
        "nodes": nodes,
        "pageInfo": {"hasNextPage": next_cursor is not None, "endCursor": next_cursor},
    }


def _comment(identifier):
    return {
        "id": "NODE-" + str(identifier),
        "databaseId": identifier,
        "body": "comment-" + str(identifier),
        "updatedAt": "2026-01-01T00:00:00Z",
        "author": {"login": "reviewer"},
    }


def _thread(identifier, comments):
    return {
        "id": identifier,
        "isResolved": False,
        "isOutdated": False,
        "path": "src/example.py",
        "comments": comments,
    }


class GraphQLFixture:
    def __init__(self, *, boundary=None, malformation=None, idless=False):
        self.boundary, self.malformation, self.idless = boundary, malformation, idless
        self.broken = boundary is not None
        self.calls = []

    def response(self, request):
        body = json.loads(request.content) if request.method == "POST" else None
        self.calls.append((request.method, request.url.path, body))
        if request.url.path == "/repos/owner/repo":
            return _http_response(request, {"id": 10, "full_name": "owner/repo"})
        if request.url.path == "/repos/owner/repo/pulls":
            return _http_response(request, [{"id": 20, "number": 1}])
        if request.url.path == "/repos/owner/repo/pulls/1":
            return _http_response(request, {"id": 20, "number": 1, "body": "PR body"})
        assert request.method == "POST" and request.url.path == "/graphql"
        variables = body["variables"]
        child = "id" in variables
        if child:
            connection = _connection([_comment(11)])
            payload = {"data": {"node": {"id": "thread-one", "comments": connection}}}
        else:
            comments = _connection([_comment(10)], next_cursor="next-comments")
            connection = _connection([_thread("thread-one", comments)])
            payload = {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "id": "PR_ACTUAL_20",
                            "number": 1,
                            "reviewThreads": connection,
                        }
                    }
                }
            }
        if self.broken and self.boundary == (
            "nested-child"
            if child
            else "nested-initial"
            if self.boundary == "nested-initial"
            else "root"
        ):
            target = (
                connection
                if self.boundary in ("root", "nested-child")
                else connection["nodes"][0]["comments"]
            )
            payload["transport_only_marker"] = (
                "REJECTED-TRANSPORT-ORIGINAL-MUST-NOT-BE-RETAINED"
            )
            if self.idless:
                target["nodes"][0].pop("databaseId", None)
            elif self.malformation == "missing-nodes":
                target.pop("nodes")
            elif self.malformation == "null-nodes":
                target["nodes"] = None
            elif self.malformation == "mapping-nodes":
                target["nodes"] = {}
            elif self.malformation == "empty-page-info":
                target["pageInfo"] = {}
            elif self.malformation == "null-has-next":
                target["pageInfo"]["hasNextPage"] = None
            elif self.malformation == "integer-has-next":
                target["pageInfo"]["hasNextPage"] = 0
            elif self.malformation == "missing-next-cursor":
                target["pageInfo"] = {"hasNextPage": True, "endCursor": None}
        return _http_response(request, payload)


def _network_cli(
    case, tmp_path, capsys, monkeypatch, client, request=None, clock_us=None
):
    import repo_catalog.application.provider_fetch as module

    original = module.acquire_github

    # Inject a real deterministic HTTP transport while retaining the entire CLI,
    # service-issued authority, durable request and normalized-admission path.
    def invoke(catalog, payload, *, authorization, admission):
        return original(
            catalog,
            payload,
            authorization=authorization,
            admission=admission,
            client=client,
            clock_us=clock_us,
        )

    monkeypatch.setattr(module, "acquire_github", invoke)
    init(capsys, case.directory, "operational")
    request = request or {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["review_threads"],
        "max_pages": 100,
        "response_bytes": 8192,
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    path = document(tmp_path, "http-request.json", request)
    result = run(
        capsys,
        "acquire",
        "github",
        "--catalog",
        case.directory,
        "--input",
        path,
        "--authority",
        case.authority,
    )
    # Restore after this call so a retry never wraps an already injected wrapper.
    monkeypatch.setattr(module, "acquire_github", original)
    return result, request


def test_cli_nested_graphql_pagination_preserves_documents_and_exact_scopes(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    api = GraphQLFixture()
    with httpx.Client(transport=httpx.MockTransport(api.response)) as client:
        result, request = _network_cli(case, tmp_path, capsys, monkeypatch, client)
    assert result["status"] == "complete"
    assert (
        result["request_identity"]["request_origin_uuidv4"]
        == request["request_identity"][0]
    )
    assert len([call for call in api.calls if call[0] == "POST"]) == 2
    assert api.calls[-1][2]["variables"] == {
        "id": "thread-one",
        "cursor": "next-comments",
    }
    assert list(case.view(capsys, case.keys["comment"])["resolved_texts"].values()) == [
        "comment-10"
    ]
    assert list(case.view(capsys, case.keys["reply"])["resolved_texts"].values()) == [
        "comment-11"
    ]
    thread = case.view(capsys, case.keys["thread"])
    complete = [item for item in thread["collections"] if item["state"] == "complete"]
    assert len(complete) == 1
    assert complete[0]["members"] == [
        list(case.keys[key].coordinates()) for key in ("comment", "reply")
    ]
    assert complete[0]["scope"]["thread_id"] == "thread-one"
    assert (
        complete[0]["provenance"]["evidence"]["request_identity"]
        == request["request_identity"]
    )
    assert not (case.directory / "repository.sqlite3").exists()
    assert not (case.directory / "transport-archive").exists()


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
def test_cli_malformed_graphql_preserves_only_real_prefix_and_retries_fresh_root(
    provider_case, tmp_path, capsys, monkeypatch, boundary, malformation
):
    case = provider_case
    api = GraphQLFixture(boundary=boundary, malformation=malformation)
    with httpx.Client(transport=httpx.MockTransport(api.response)) as client:
        result, request = _network_cli(case, tmp_path, capsys, monkeypatch, client)
        assert result["status"] == "partial"
        assert result["failure_code"] == (
            "PAGINATION_CYCLE"
            if malformation == "missing-next-cursor"
            else "API_SCHEMA"
        )
        pull = case.view(capsys, case.keys["pull"])
        assert not any(
            item["collection_kind"] == "review_threads" and item["state"] == "complete"
            for item in pull["collections"]
        )
        assert any(
            item["collection_kind"] == "review_threads" and item["state"] == "partial"
            for item in pull["collections"]
        )
        if boundary == "nested-child":
            assert list(
                case.view(capsys, case.keys["comment"])["resolved_texts"].values()
            ) == ["comment-10"]
        all_text = run(
            capsys, "query", "context-resources", "--catalog", case.directory
        )
        assert "REJECTED-TRANSPORT-ORIGINAL" not in json.dumps(all_text)
        assert not (case.directory / "p1-recovery-stop.json").exists()
        assert not (case.directory / "transport-archive").exists()
        before = len(api.calls)
        api.broken = False
        request["new_request"] = False
        resumed, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert resumed["status"] == "complete"
    graph_calls = [body for method, _, body in api.calls[before:] if method == "POST"]
    assert (
        "cursor" in graph_calls[0]["variables"]
        and graph_calls[0]["variables"]["cursor"] is None
    )
    assert resumed["request_identity"] == result["request_identity"]
    assert list(case.view(capsys, case.keys["reply"])["resolved_texts"].values()) == [
        "comment-11"
    ]


def _transport_config():
    return {
        "rest_base_url": "https://api.github.com",
        "graphql_url": "https://api.github.com/graphql",
        "token_env_var": "SEPARATED_TEST_TOKEN",
        "rest_api_version": "2022-11-28",
        "read_timeout_seconds": 30,
        "connect_timeout_seconds": 10,
        "max_attempts": 3,
    }


class _Token:
    def check(self):
        pass


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
    ids=[
        "retry-fraction",
        "retry-zero",
        "retry-negative",
        "http-date",
        "reset-future",
        "reset-past",
        "retry-nan",
        "reset-infinity",
        "default",
    ],
)
def test_shared_github_transport_retains_exact_integer_backoff(headers, expected_us):
    from repo_catalog.adapters.github.transport import GitHubTransport
    from repo_catalog.domain.models import Waiting

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, headers=headers, json={})
        )
    ) as client:
        transport = GitHubTransport(
            _transport_config(), _Token(), client=client, clock_us=lambda: 1_000_000_123
        )
        with pytest.raises(Waiting) as raised:
            transport.request("GET", transport.base + "/user")
    assert raised.value.code == "RATE_LIMIT"
    assert raised.value.details == {"not_before_us": expected_us}
    assert type(raised.value.details["not_before_us"]) is int


@pytest.mark.parametrize(
    "error_type", [ValueError, httpx.ConnectError], ids=["value-error", "connect-error"]
)
def test_optional_recording_failure_does_not_block_normalized_cli_admission_or_leak_secret(
    provider_case, tmp_path, capsys, error_type
):
    from repo_catalog.adapters.github.transport import GitHubTransport

    case = provider_case
    secret = "must-not-leak-recording-secret"
    calls = []

    class BrokenRecorder:
        def record_exchange(self, context, body):
            raise error_type(secret)

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "id": 100,
                "title": "admitted",
                "body": "domain survives recording failure",
                "updated_at": "2026-01-01T00:00:00Z",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        transport = GitHubTransport(
            _transport_config(),
            _Token(),
            client=client,
            recorder=BrokenRecorder(),
            clock_us=lambda: 1_000_000,
        )
        with pytest.warns(RuntimeWarning, match="ARCHIVE_FAILURE") as warnings:
            response = transport.request(
                "GET", transport.base + "/repos/owner/repo/issues"
            )
    assert len(calls) == 1
    assert response.extensions["repo_catalog_archive_ref"] is None
    diagnostics = response.extensions["repo_catalog_recording_diagnostics"]
    assert diagnostics[0]["code"] == "ARCHIVE_FAILURE"
    assert secret not in str(warnings[0].message)
    assert secret not in json.dumps(diagnostics)
    case.admit(
        tmp_path,
        capsys,
        issues=(
            ProviderIssueIntake(
                response.json(),
                response.extensions["catalog_observed_at_us"],
                make_provenance(
                    "actual-local-normalizer",
                    {
                        "response": "one",
                        "external_parser_module": "forged.external.module",
                    },
                ),
            ),
        ),
    )
    view = case.view(capsys, case.keys["issue"])
    assert list(view["resolved_texts"].values()) == [
        "domain survives recording failure"
    ]
    assert (
        view["fields"]["title"][0]["provenance"]["source"] == "actual-local-normalizer"
    )
    assert "preferred_parser" not in view
    assert not (case.directory / "transport-archive").exists()


class GraphQLErrorFixture(GraphQLFixture):
    def __init__(self, boundary, data_shape, error_type):
        super().__init__()
        self.error_boundary, self.data_shape, self.error_type = (
            boundary,
            data_shape,
            error_type,
        )
        self.error_enabled = True

    def response(self, request):
        result = super().response(request)
        if request.method != "POST" or not self.error_enabled:
            return result
        child = "id" in json.loads(request.content)["variables"]
        if child != (self.error_boundary == "nested-child"):
            return result
        data = (
            None
            if self.data_shape == "null"
            else {}
            if self.data_shape == "empty"
            else {"node": None}
            if child
            else {"repository": {"pullRequest": None}}
        )
        return _http_response(
            request,
            {
                "data": data,
                "errors": [{"type": self.error_type, "message": "classified failure"}],
                "transport_only_marker": "REJECTED-TRANSPORT-ORIGINAL-MUST-NOT-BE-RETAINED",
            },
        )


def _request_usage(directory, request):
    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
    from repo_catalog.domain.p1_coordination import RequestIdentity

    with OperationalAcquisitionLedger(directory) as ledger:
        return ledger.work_ledger.usage(RequestIdentity(*request["request_identity"]))


@pytest.mark.parametrize("boundary", ["root", "nested-child"])
@pytest.mark.parametrize("data_shape", ["null", "empty", "null-resource"])
@pytest.mark.parametrize("error_type", ["RATE_LIMITED", "FORBIDDEN"])
def test_graphql_error_only_retry_deadlines_are_durable_and_do_not_reset_request(
    provider_case, tmp_path, capsys, monkeypatch, boundary, data_shape, error_type
):
    case = provider_case
    api = GraphQLErrorFixture(boundary, data_shape, error_type)
    stamp = [1_000_000]
    with httpx.Client(transport=httpx.MockTransport(api.response)) as client:
        first, request = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, clock_us=lambda: stamp[0]
        )
        assert first["status"] == "partial"
        assert first["failure_code"] == (
            "RATE_LIMIT" if error_type == "RATE_LIMITED" else "GRAPHQL_PARTIAL"
        )
        assert first["not_before_us"] == (
            61_000_000 if error_type == "RATE_LIMITED" else None
        )
        pull = case.view(capsys, case.keys["pull"])
        assert not any(
            item["collection_kind"] == "review_threads" and item["state"] == "complete"
            for item in pull["collections"]
        )
        if boundary == "nested-child":
            assert list(
                case.view(capsys, case.keys["comment"])["resolved_texts"].values()
            ) == ["comment-10"]
        request["new_request"] = False
        api.error_enabled = False
        if error_type == "RATE_LIMITED":
            before_calls, before_usage = (
                len(api.calls),
                _request_usage(case.directory, request),
            )
            stamp[0] = 60_999_999
            blocked, _ = _network_cli(
                case,
                tmp_path,
                capsys,
                monkeypatch,
                client,
                request,
                clock_us=lambda: stamp[0],
            )
            assert blocked["failure_code"] == "NOT_BEFORE"
            assert blocked["not_before_us"] == 61_000_000
            assert blocked["http_attempts"] == blocked["network_bytes"] == 0
            assert len(api.calls) == before_calls
            assert _request_usage(case.directory, request) == before_usage
            stamp[0] = 61_000_000
        else:
            stamp[0] += 1
        before = len(api.calls)
        resumed, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: stamp[0],
        )
    assert resumed["status"] == "complete"
    assert resumed["not_before_us"] is None
    assert resumed["request_identity"] == first["request_identity"]
    reports = [
        proof[1] for batch in resumed["batches"] for proof in batch["collection_proofs"]
    ]
    # Root and child responses deliberately share the actual receive clock.
    # Their partial/complete reports keep distinct original evidence without
    # inventing timestamp increments or changing the durable request identity.
    assert {report["observed_at_us"] for report in reports} == {stamp[0]}
    originals = [
        json.loads(report["provenance_json"])["evidence"] for report in reports
    ]
    assert len({original["traversal_attempt_uuidv4"] for original in originals}) == 1
    assert len(
        {original["terminal_report"]["ordinal"] for original in originals}
    ) == len(reports)
    for report, original in zip(reports, originals):
        prefix = [
            [
                member["service_instance_uuidv4"],
                member["resource_kind"],
                member["provider_resource_id"],
            ]
            for member in report["members"]
        ]
        terminal = original["terminal_report"]
        assert (
            terminal["member_prefix_sha256"]
            == hashlib.sha256(canonical(prefix).encode()).hexdigest()
        )
        assert terminal["kind"] == "response"
        assert terminal["read_origins"] and all(terminal["read_origins"])
        assert original["request_identity"] == request["request_identity"]
    graph_calls = [body for method, _, body in api.calls[before:] if method == "POST"]
    assert graph_calls[0]["variables"]["cursor"] is None
    assert list(case.view(capsys, case.keys["reply"])["resolved_texts"].values()) == [
        "comment-11"
    ]
    assert not (case.directory / "p1-recovery-stop.json").exists()


def test_repeated_real_reads_get_distinct_provenance_without_changing_original_times(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    stamp = [10_000_000]

    def handle(request):
        if request.url.path == "/user":
            return _http_response(request, {"login": "owner"})
        return _http_response(request, {"id": 10, "full_name": "owner/repo"})

    request = {
        "operation": "discover",
        "include_repositories": ["repo"],
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: stamp[0],
        )
        before = _request_usage(case.directory, request)
        stamp[0] = 20_000_000
        request["new_request"] = False
        second, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: stamp[0],
        )
    assert first["status"] == second["status"] == "complete"
    assert first["request_identity"] == second["request_identity"]
    after = _request_usage(case.directory, request)
    assert all(after[unit] >= before[unit] for unit in before)
    assert after["input_bytes"] > before["input_bytes"]
    view = case.view(capsys, case.keys["repository"])
    candidates = [
        candidate for entries in view["fields"].values() for candidate in entries
    ]
    assert {candidate["observed_at_us"] for candidate in candidates} == {
        10_000_000,
        20_000_000,
    }
    origins = {
        canonical(candidate["provenance"]["evidence"]["read_origin"])
        for candidate in candidates
    }
    assert len(origins) == 2
    assert all(
        candidate["provenance"]["evidence"]["request_identity"]
        == request["request_identity"]
        for candidate in candidates
    )


@pytest.mark.parametrize("kind", ["issue", "review", "review-comment"])
@pytest.mark.parametrize("external_field", ["parser_module", "parser_version"])
@pytest.mark.parametrize(
    "external_value", [None, "", "module\x00hidden"], ids=["null", "empty", "nul"]
)
def test_external_decoder_metadata_never_substitutes_for_required_original_attribution(
    provider_case, tmp_path, capsys, kind, external_field, external_value
):
    case = provider_case
    original = make_provenance(
        "actual-local-normalizer", {external_field: external_value}
    )
    if kind == "issue":
        sections, key = (
            {
                "issues": (
                    ProviderIssueIntake({"id": 100, "body": "attributed"}, 1, original),
                )
            },
            case.keys["issue"],
        )
    elif kind == "review":
        sections, key = (
            {
                "reviews": (
                    ProviderReviewIntake(
                        "20", {"id": 10, "body": "attributed"}, 1, original
                    ),
                )
            },
            case.keys["review"],
        )
    else:
        sections, key = (
            {
                "review_comments": (
                    ProviderReviewCommentIntake(
                        "20", {"id": 10, "body": "attributed"}, 1, original
                    ),
                )
            },
            case.keys["comment"],
        )
    case.admit(tmp_path, capsys, **sections)
    view = case.view(capsys, key)
    candidate = view["fields"]["text_body_sha256"][0]
    assert candidate["provenance"] == json.loads(original)
    assert candidate["provenance"]["source"] == "actual-local-normalizer"
    assert external_field not in candidate
    encoded = wire(case.batch(**sections))
    section = next(iter(sections))
    encoded["fields"][section][0]["fields"]["provenance_json"] = canonical(
        {"evidence": {external_field: external_value}}
    )
    path = tmp_path / "missing-original-source.json"
    path.write_text(json.dumps(encoded))
    run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        case.directory,
        "--input",
        path,
        "--authority",
        case.authority,
        expected=2,
    )
    assert case.view(capsys, key) == view


@pytest.mark.parametrize(
    "attack",
    [
        "null-digest",
        "uppercase-digest",
        "extra-key",
        "duplicate",
        "duplicate-key",
        "wrong-parent",
        "nul-provider",
    ],
)
def test_untyped_or_misowned_collection_members_cannot_create_terminal_evidence(
    provider_case, tmp_path, capsys, attack
):
    from repo_catalog.domain.production_context import CollectionObservation

    case = provider_case
    provenance = make_provenance("local-provider", "collection-negative")
    case.admit(
        tmp_path,
        capsys,
        review_comments=(
            ProviderReviewCommentIntake("20", {"id": 10}, 1, provenance),
            ProviderReviewCommentIntake("21", {"id": 10}, 1, provenance),
        ),
    )
    before = case.view(capsys, case.keys["pull"])
    observation = CollectionObservation(
        case.keys["pull"],
        "comments",
        provenance,
        "{}",
        1,
        "complete",
        (case.keys["comment"],),
    )
    encoded = wire(case.batch(collections=(observation,)))
    collection = encoded["fields"]["collections"][0]["fields"]
    if attack in ("null-digest", "uppercase-digest"):
        collection["member_state_digest"] = (
            None if attack == "null-digest" else "A" * 64
        )
    elif attack == "extra-key":
        collection["unregistered"] = True
    elif attack == "duplicate":
        collection["members"] *= 2
    elif attack == "wrong-parent":
        collection["members"] = [wire(case.keys["other_comment"])]
    elif attack == "nul-provider":
        collection["members"][0]["fields"]["provider_resource_id"] += "\x00hidden"
    raw = json.dumps(encoded)
    if attack == "duplicate-key":
        raw = raw.replace(
            '"state": "complete"', '"state": "complete", "state": "complete"'
        )
    path = tmp_path / "bad-collection.json"
    path.write_text(raw)
    run(
        capsys,
        "acquire",
        "provider",
        "--catalog",
        case.directory,
        "--input",
        path,
        "--authority",
        case.authority,
        expected=2,
    )
    assert case.view(capsys, case.keys["pull"]) == before
    assert not (case.directory / "p1-recovery-stop.json").exists()


def test_exchange_import_never_promotes_receiver_observation_time_to_provider_clock(
    provider_case, tmp_path, capsys
):
    from repo_catalog.domain.exchange import ExchangeSelectionScope

    case = provider_case
    case.admit(
        tmp_path,
        capsys,
        issues=(issue({"id": 100, "body": "from peer"}, "peer-original", observed=10),),
    )
    init(capsys, case.directory, "operational")
    selection = document(
        tmp_path,
        "context-selection.json",
        ExchangeSelectionScope(all_selected=True, include_repository=False),
    )
    package = tmp_path / "peer-package.json"
    run(
        capsys,
        "exchange",
        "export",
        "--catalog",
        case.directory,
        "--selection",
        selection,
        "--output",
        package,
    )
    receiver = tmp_path / "receiver"
    init(capsys, receiver, "context")
    init(capsys, receiver, "operational")
    local = ProviderFixture(
        receiver, case.service, case.source, case.authority, case.keys
    )
    local.admit(
        tmp_path,
        capsys,
        issues=(
            issue(
                {"id": 100, "body": "receiver observation"},
                "receiver-original",
                observed=2**60,
            ),
        ),
    )
    run(
        capsys,
        "exchange",
        "import",
        "--catalog",
        receiver,
        "--selection",
        selection,
        "--input",
        package,
        "--authority",
        case.authority,
        "--new-request",
    )
    view = local.view(capsys, case.keys["issue"])
    assert set(view["resolved_texts"].values()) == {"from peer", "receiver observation"}
    candidates = view["fields"]["text_body_sha256"]
    assert {candidate["clock"]["at_us"] for candidate in candidates} == {None}
    assert {candidate["observed_at_us"] for candidate in candidates} == {10, 2**60}
    assert all("receiver_revision" not in candidate for candidate in candidates)


@pytest.mark.parametrize("comment_count", [2, 101])
def test_two_level_graphql_partial_prefix_resumes_to_exact_root_and_child_membership(
    provider_case, tmp_path, capsys, monkeypatch, comment_count
):
    from repo_catalog.domain.context_admission import AdmissionBudget
    from repo_catalog.domain.query_contracts import PageRequest

    # This deliberately larger finite fixture exceeds the ordinary query VM
    # allowance; configure its read budget explicitly without changing policy.
    case = replace(provider_case, query_sql_steps=50_000_000)
    comment_keys = {
        thread: [
            ResourceKey.document(
                case.keys["pull"], "comment", "review_comment", str(base + ordinal)
            )
            for ordinal in range(comment_count)
        ]
        for thread, base in (("thread-one", 1000), ("thread-two", 2000))
    }
    grants = DependencySet(
        resources=frozenset(case.keys.values())
        | frozenset(key for keys in comment_keys.values() for key in keys),
        sources=frozenset({case.source}),
        provider_registrations=frozenset({case.service}),
    )
    case.authority = document(
        tmp_path,
        "large-authority.json",
        {
            "grants": grants,
            "selection": AdmissionSelection(all_selected=True),
            "budget": AdmissionBudget(
                work_limit=10_000_000,
                bytes_limit=32 * 1024 * 1024,
                dependency_limit=100_000,
            ),
        },
    )
    calls, broken, stamp = [], [True], [1_000_000]

    def handler(request):
        stamp[0] += 1_000_000
        payload = json.loads(request.content) if request.method == "POST" else None
        calls.append((request.method, request.url.path, payload, stamp[0]))
        if request.url.path == "/repos/owner/repo":
            return _http_response(request, {"id": 10, "full_name": "owner/repo"})
        if request.url.path == "/repos/owner/repo/pulls":
            return _http_response(request, [{"id": 20, "number": 1}])
        if request.url.path == "/repos/owner/repo/pulls/1":
            return _http_response(request, {"id": 20, "number": 1})
        variables = payload["variables"]
        if "id" in variables:
            thread, first = variables["id"], 100
            base = 1000 if thread == "thread-one" else 2000
            return _http_response(
                request,
                {
                    "data": {
                        "node": {
                            "id": thread,
                            "comments": _connection(
                                [
                                    _comment(base + number)
                                    for number in range(first, comment_count)
                                ]
                            ),
                        }
                    }
                },
            )
        second = variables["cursor"] is not None
        thread, base = ("thread-two", 2000) if second else ("thread-one", 1000)
        comments = _connection(
            [_comment(base + number) for number in range(min(100, comment_count))],
            next_cursor="child-next" if comment_count > 100 else None,
        )
        connection = _connection(
            [_thread(thread, comments)], next_cursor=None if second else "root-next"
        )
        value = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "id": "PR_ACTUAL_20",
                        "number": 1,
                        "reviewThreads": connection,
                    }
                }
            }
        }
        if broken[0] and second:
            value["errors"] = [
                {"type": "FORBIDDEN", "message": "independent partial root"}
            ]
            value["transport_only_marker"] = (
                "REJECTED-TRANSPORT-ORIGINAL-MUST-NOT-BE-RETAINED"
            )
        return _http_response(request, value)

    query = document(
        tmp_path,
        "all-comments.json",
        {"kwargs": {"resource_kind": "comment", "page": PageRequest(limit=10000)}},
    )
    request = {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["review_threads"],
        "response_bytes": 1024 * 1024,
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first, request = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: stamp[0],
        )
        assert (
            first["status"] == "partial" and first["failure_code"] == "GRAPHQL_PARTIAL"
        )
        prefix = run(
            capsys,
            "query",
            "resources",
            "--catalog",
            case.directory,
            "--input",
            query,
            "--max-sql-steps",
            case.query_sql_steps,
        )
        assert len(prefix["items"]) == comment_count + min(100, comment_count)
        assert "REJECTED-TRANSPORT-ORIGINAL" not in json.dumps(prefix)
        before = len(calls)
        broken[0] = False
        request["new_request"] = False
        second, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request,
            clock_us=lambda: stamp[0],
        )
    assert second["status"] == "complete"
    assert second["request_identity"] == first["request_identity"]
    graph = [body for method, _, body, _ in calls[before:] if method == "POST"]
    assert graph[0]["variables"]["cursor"] is None
    all_comments = run(
        capsys,
        "query",
        "resources",
        "--catalog",
        case.directory,
        "--input",
        query,
        "--max-sql-steps",
        case.query_sql_steps,
    )
    assert len(all_comments["items"]) == 2 * comment_count
    pass_ids = {
        json.loads(proof[1]["provenance_json"])["evidence"]["traversal_attempt_uuidv4"]
        for batch in second["batches"]
        for proof in batch["collection_proofs"]
    }
    assert len(pass_ids) == 1
    pass_id = next(iter(pass_ids))
    for label, thread in (("thread", "thread-one"), ("other_thread", "thread-two")):
        view = case.view(capsys, case.keys[label])
        complete = [
            item
            for item in view["collections"]
            if item["state"] == "complete"
            and item["provenance"]["evidence"]["traversal_attempt_uuidv4"] == pass_id
        ]
        assert len(complete) == 1
        assert complete[0]["members"] == [
            list(key.coordinates()) for key in comment_keys[thread]
        ]
        assert complete[0]["scope"]["thread_id"] == thread
    root = case.view(capsys, case.keys["pull"])
    complete_root = [
        item
        for item in root["collections"]
        if item["collection_kind"] == "review_threads"
        and item["state"] == "complete"
        and item["provenance"]["evidence"]["traversal_attempt_uuidv4"] == pass_id
    ]
    assert len(complete_root) == 1
    assert complete_root[0]["members"] == [
        list(case.keys[key].coordinates()) for key in ("thread", "other_thread")
    ]
    # The root's resource received timestamp is its own GraphQL response time,
    # never the timestamp of a later child continuation.
    first_root_response = next(
        stamp
        for method, _, body, stamp in calls[before:]
        if method == "POST" and body["variables"].get("cursor") is None
    )
    thread = case.view(capsys, case.keys["thread"])
    assert any(
        candidate["observed_at_us"] == first_root_response
        for candidate in thread["fields"]["resolved"]
    )


def test_nested_child_read_cannot_retimestamp_sibling_thread_from_original_root(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    third = ResourceKey.document(case.keys["pull"], "comment", "review_comment", "12")
    grants = DependencySet(
        resources=frozenset(case.keys.values()) | {third},
        sources=frozenset({case.source}),
        provider_registrations=frozenset({case.service}),
    )
    case.authority = document(
        tmp_path,
        "sibling-authority.json",
        {"grants": grants, "selection": AdmissionSelection(all_selected=True)},
    )
    api, stamp, roots, children = GraphQLFixture(), [1_000_000], [], []

    def handle(request):
        stamp[0] += 1_000_000
        response = api.response(request)
        if request.method == "POST":
            variables = json.loads(request.content)["variables"]
            if "id" in variables:
                children.append(stamp[0])
            else:
                roots.append(stamp[0])
                response.read()
                value = response.json()
                value["data"]["repository"]["pullRequest"]["reviewThreads"][
                    "nodes"
                ].append(_thread("thread-two", _connection([_comment(12)])))
                response = _http_response(request, value)
        return response

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result, _ = _network_cli(
            case, tmp_path, capsys, monkeypatch, client, clock_us=lambda: stamp[0]
        )
    assert result["status"] == "complete"
    assert len(roots) == len(children) == 1
    assert roots[0] < children[0]
    for label in ("thread", "other_thread"):
        candidates = case.view(capsys, case.keys[label])["fields"]["resolved"]
        assert {candidate["observed_at_us"] for candidate in candidates} == {roots[0]}


def test_failure_before_any_new_response_preserves_prior_context_coverage(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    api, blocked = GraphQLFixture(), [False]

    def handle(request):
        if blocked[0]:
            api.calls.append((request.method, request.url.path, None))
            return httpx.Response(
                401, json={"transport_only_marker": "unusable credentials"}
            )
        return api.response(request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first, request = _network_cli(case, tmp_path, capsys, monkeypatch, client)
        assert first["status"] == "complete"
        before = run(capsys, "query", "context-resources", "--catalog", case.directory)
        root_before = case.view(capsys, case.keys["pull"])["collections"]
        boundary = len(api.calls)
        request["new_request"] = False
        blocked[0] = True
        failed, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert (
        failed["status"] == "partial"
        and failed["failure_code"] == "CREDENTIALS_MISSING"
    )
    assert failed["http_attempts"] == 1
    assert len(api.calls) == boundary + 1
    assert (
        run(capsys, "query", "context-resources", "--catalog", case.directory) == before
    )
    assert case.view(capsys, case.keys["pull"])["collections"] == root_before


def test_malformed_rest_review_page_is_partial_then_reacquired_without_archive(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    api, broken, reviews = GraphQLFixture(), [True], []

    def handle(request):
        if request.url.path.endswith("/reviews"):
            reviews.append(request)
            return _http_response(
                request,
                {"malformed": "REJECTED-REVIEW-ORIGINAL"}
                if broken[0]
                else [{"id": 10, "body": "review body", "state": "APPROVED"}],
            )
        return api.response(request)

    request = {
        "operation": "sync",
        "service_instance_uuidv4": case.service,
        "source_registration_uuidv4": case.source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["reviews"],
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
        assert first["status"] == "partial" and first["failure_code"] == "API_SCHEMA"
        first_collections = case.view(capsys, case.keys["pull"])["collections"]
        assert not any(
            item["collection_kind"] == "reviews" for item in first_collections
        )
        assert "REJECTED-REVIEW-ORIGINAL" not in json.dumps(
            run(capsys, "query", "context-resources", "--catalog", case.directory)
        )
        request["new_request"] = False
        broken[0] = False
        second, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert second["status"] == "complete"
    assert len(reviews) == 2
    assert list(case.view(capsys, case.keys["review"])["resolved_texts"].values()) == [
        "review body"
    ]
    assert not (case.directory / "transport-archive").exists()


@pytest.mark.parametrize("boundary", ["nested-initial", "nested-child"])
def test_graphql_review_comments_require_database_id_without_node_alias_fallback(
    provider_case, tmp_path, capsys, monkeypatch, boundary
):
    case = provider_case
    api = GraphQLFixture(boundary=boundary, idless=True)
    with httpx.Client(transport=httpx.MockTransport(api.response)) as client:
        first, request = _network_cli(case, tmp_path, capsys, monkeypatch, client)
        assert (
            first["status"] == "partial"
            and first["failure_code"] == "CANONICAL_ID_REQUIRED"
        )
        all_resources = run(
            capsys, "query", "context-resources", "--catalog", case.directory
        )
        assert (
            "NODE-10" if boundary == "nested-initial" else "NODE-11"
        ) not in json.dumps(all_resources)
        assert not (case.directory / "transport-archive").exists()
        request["new_request"] = False
        api.broken = False
        second, _ = _network_cli(case, tmp_path, capsys, monkeypatch, client, request)
    assert second["status"] == "complete"
    assert list(case.view(capsys, case.keys["comment"])["resolved_texts"].values()) == [
        "comment-10"
    ]
    assert list(case.view(capsys, case.keys["reply"])["resolved_texts"].values()) == [
        "comment-11"
    ]


@pytest.mark.parametrize("graphql", [False, True], ids=["rest", "graphql"])
def test_same_pr_and_decimal_id_keep_issue_and_review_comment_subtypes_independent(
    provider_case, tmp_path, capsys, graphql
):
    from repo_catalog.domain.production_context import ResourceRelation
    from repo_catalog.domain.provider_acquisition import ProviderIssueCommentIntake

    case = provider_case
    discussion = ResourceKey.document(case.keys["pull"], "comment", "comment", "10")
    discussion_parent = ResourceKey.document(
        case.keys["pull"], "comment", "comment", "11"
    )
    assert discussion != case.keys["comment"]
    assert discussion_parent != case.keys["reply"]
    grants = DependencySet(
        resources=frozenset(case.keys.values()) | {discussion, discussion_parent},
        sources=frozenset({case.source}),
        provider_registrations=frozenset({case.service}),
    )
    case.authority = document(
        tmp_path,
        "comment-subtype-authority.json",
        {"grants": grants, "selection": AdmissionSelection(all_selected=True)},
    )

    def payload(identifier, family, **fields):
        identity = (
            {"databaseId": identifier, "id": family + "-native-node-" + str(identifier)}
            if graphql
            else {"id": identifier}
        )
        return {**identity, **fields}

    issue_payload = payload(10, "IC", body="discussion body")
    review_payload = payload(10, "PRRC")
    originals = json.loads(json.dumps([issue_payload, review_payload]))
    provenance = make_provenance("local-provider", "known-endpoint-subtypes")
    # The separate review endpoint omits body: it must not borrow the issue
    # discussion body's fields merely because the same decimal ID was supplied.
    case.admit(
        tmp_path,
        capsys,
        issue_comments=(
            ProviderIssueCommentIntake(
                "pull_request", "20", issue_payload, 10, provenance, graphql=graphql
            ),
        ),
        review_comments=(
            ProviderReviewCommentIntake(
                "20", review_payload, 10, provenance, graphql=graphql
            ),
        ),
    )
    assert [issue_payload, review_payload] == originals
    assert list(case.view(capsys, discussion)["resolved_texts"].values()) == [
        "discussion body"
    ]
    assert case.view(capsys, case.keys["comment"])["resolved_texts"] == {}
    assert case.view(capsys, discussion)["document_kind"] == "comment"
    assert case.view(capsys, case.keys["comment"])["document_kind"] == "review_comment"
    reply_reference = (
        {"replyTo": {"id": "PRRC-native-node-11", "databaseId": 11}}
        if graphql
        else {"in_reply_to_id": 11}
    )
    final_review = payload(10, "PRRC", body="review body", **reply_reference)
    review_parent = payload(11, "PRRC", body="review parent")
    issue_parent = payload(11, "IC", body="discussion parent")
    case.admit(
        tmp_path,
        capsys,
        issue_comments=(
            ProviderIssueCommentIntake(
                "pull_request",
                "20",
                issue_parent,
                20,
                make_provenance("local-provider", "issue-parent"),
                graphql=graphql,
            ),
        ),
        review_comments=(
            ProviderReviewCommentIntake(
                "20",
                review_parent,
                20,
                make_provenance("local-provider", "review-parent"),
                graphql=graphql,
            ),
            ProviderReviewCommentIntake(
                "20",
                final_review,
                20,
                make_provenance("local-provider", "review-reply"),
                graphql=graphql,
                thread_id="thread-one",
            ),
        ),
    )
    review_view = case.view(capsys, case.keys["comment"])
    assert list(review_view["resolved_texts"].values()) == ["review body"]
    reply_relations = [
        relation
        for relation in review_view["relations"]
        if relation["relation_kind"] == "in_reply_to"
    ]
    assert reply_relations and all(
        relation["members"] == [list(case.keys["reply"].coordinates())]
        for relation in reply_relations
    )
    assert all(
        list(discussion_parent.coordinates()) not in relation["members"]
        for relation in reply_relations
    )
    assert list(case.view(capsys, discussion)["resolved_texts"].values()) == [
        "discussion body"
    ]
    assert list(case.view(capsys, discussion_parent)["resolved_texts"].values()) == [
        "discussion parent"
    ]
    assert list(case.view(capsys, case.keys["reply"])["resolved_texts"].values()) == [
        "review parent"
    ]
    # Semantic Parent originals carry their own actual document subtype and key.
    scope = canonical(
        {
            "clock": {"domain": "explicit-parent-report", "at_us": 20},
            "document_kind": "review_comment",
            "state": "complete",
        }
    )
    parent = ResourceRelation(
        case.keys["comment"],
        "parent",
        (case.keys["pull"],),
        make_provenance("local-provider", "actual-review-parent"),
        scope,
        20,
    )
    case.admit(tmp_path, capsys, relations=(parent,))
    assert not any(
        relation["relation_kind"] == "parent"
        for relation in case.view(capsys, discussion)["relations"]
    )
    assert any(
        relation["relation_kind"] == "parent"
        for relation in case.view(capsys, case.keys["comment"])["relations"]
    )
    if graphql:
        assert issue_payload["id"] == "IC-native-node-10"
        assert review_payload["id"] == final_review["id"] == "PRRC-native-node-10"
