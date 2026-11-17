"""Actual failed HTTP projections cannot invent new Context collection evidence."""

from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.pr_assessment import PRQueryService
from tests.e2e.test_separated_cli_provider_regressions import (
    _http_response,
    _network_cli,
)
from tests.e2e.test_separated_cli_provider_regressions import (
    provider_case as provider_case,
)


def request_document(case):
    return {
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


def reviews_evidence(case):
    with Context.snapshot(case.directory) as context:
        return (
            tuple(
                tuple(row)
                for row in context.db.execute(
                    "SELECT * FROM collection_terminals WHERE collection_kind='reviews' "
                    "ORDER BY provenance_json,observed_at_us,terminal_state,members_json"
                )
            ),
            tuple(
                tuple(row)
                for row in context.db.execute(
                    "SELECT * FROM coverage_proofs WHERE collection_kind='reviews' "
                    "ORDER BY provenance_json,observed_at_us,terminal_state,members_json"
                )
            ),
            tuple(
                tuple(row)
                for row in context.db.execute(
                    "SELECT c.* FROM coverage_claims c JOIN coverage_proofs p "
                    "USING(owner_kind,owner_coordinates_json,observed_at_us,coverage_state) "
                    "WHERE p.collection_kind='reviews' ORDER BY c.owner_coordinates_json,c.observed_at_us"
                )
            ),
        )


def response_for(request, reviews):
    path = request.url.path
    if path.endswith("/reviews"):
        if reviews == "raw-json":
            return httpx.Response(200, request=request, content=b"{broken-json")
        return _http_response(request, reviews)
    if path.endswith("/pulls"):
        return _http_response(request, [{"id": 20, "number": 1}])
    if path.endswith("/pulls/1"):
        return _http_response(request, {"id": 20, "number": 1})
    assert path == "/repos/owner/repo", path
    return _http_response(request, {"id": 10, "full_name": "owner/repo"})


@pytest.mark.parametrize(
    "rejected",
    [
        "raw-json",
        {"id": 10, "body": "not a collection"},
        {"errors": [{"message": "not an observed review"}]},
        [{"body": "NO-IDENTIFIED-ORIGINAL"}],
        [{"node_id": "opaque-only", "body": "NO-IDENTIFIED-ORIGINAL"}],
    ],
    ids=["raw-json", "nonlist-resource", "error-envelope", "missing-id", "node-id"],
)
def test_unprojectable_actual_response_keeps_prior_proof_time_and_originals(
    provider_case, tmp_path, capsys, monkeypatch, rejected
):
    case, current, stamp = provider_case, [[]], [100]
    calls = []

    def handle(request):
        calls.append(request.url.path)
        return response_for(request, current[0])

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document(case),
            clock_us=lambda: stamp[0],
        )
        assert first["status"] == "complete"
        before = reviews_evidence(case)
        assert all(before) and len(before[0]) == len(before[1]) == len(before[2]) == 1
        query = PRQueryService(case.directory)
        result = query.get_pr_documents(case.keys["pull"], kinds=("reviews",))
        assert result.state == "complete" and result.page.items == ()
        current[0], stamp[0] = rejected, 200
        failed, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document(case),
            clock_us=lambda: stamp[0],
        )
        assert failed["status"] == "partial" and failed["failure_code"]
        assert failed["http_attempts"] > 0 and failed["network_bytes"] > 0
        assert calls.count("/repos/owner/repo/pulls/1/reviews") == 2
        assert reviews_evidence(case) == before
        unchanged = query.get_pr_documents(case.keys["pull"], kinds=("reviews",))
        assert unchanged.state == "complete" and unchanged.page.items == ()
        assert unchanged.coverage == result.coverage
        with Context.snapshot(case.directory) as context:
            assert context.candidates(case.keys["review"], "text_body_sha256") == ()
        # A genuinely observed empty projection is independently meaningful.
        current[0], stamp[0] = [], 300
        recovered, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document(case),
            clock_us=lambda: stamp[0],
        )
    assert recovered["status"] == "complete"
    after = reviews_evidence(case)
    assert len(after[0]) == len(before[0]) + 1
    assert len(after[1]) == len(before[1]) + 1
    assert len(after[2]) == len(before[2]) + 1
    assert not (case.directory / "p1-recovery-stop.json").exists()


def test_genuine_empty_response_proves_empty_without_manufactured_members(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: response_for(request, []))
    ) as client:
        report, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document(case),
            clock_us=lambda: 100,
        )
    assert report["status"] == "complete"
    terminals, proofs, claims = reviews_evidence(case)
    assert len(terminals) == len(proofs) == len(claims) == 1
    result = PRQueryService(case.directory).get_pr_documents(
        case.keys["pull"], kinds=("reviews",)
    )
    assert result.state == "complete" and result.page.items == ()
    with Context.snapshot(case.directory) as context:
        assert context.candidates(case.keys["review"], "text_body_sha256") == ()


def test_actual_accepted_prefix_then_rejection_keeps_partial_original_membership(
    provider_case, tmp_path, capsys, monkeypatch
):
    case = provider_case
    reviews = [
        {"id": 10, "body": "actual\x00review", "state": "APPROVED"},
        {"id": 11, "body": []},
    ]
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: response_for(request, reviews))
    ) as client:
        report, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document(case),
            clock_us=lambda: 100,
        )
    assert report["status"] == "partial" and report["failure_code"]
    view = case.view(capsys, case.keys["review"])
    assert tuple(view["resolved_texts"].values()) == ("actual\x00review",)
    terminals = [
        item
        for item in case.view(capsys, case.keys["pull"])["collections"]
        if item["collection_kind"] == "reviews"
    ]
    assert len(terminals) == 1 and terminals[0]["state"] == "partial"
    assert terminals[0]["members"] == [list(case.keys["review"].coordinates())]
    result = PRQueryService(case.directory).get_pr_documents(
        case.keys["pull"], kinds=("reviews",)
    )
    assert result.state != "complete"
    assert not (case.directory / "p1-recovery-stop.json").exists()


def test_stopped_actual_request_cannot_admit_a_received_review_or_failure_terminal(
    provider_case, tmp_path, capsys, monkeypatch
):
    from repo_catalog.adapters.sqlite.operations_admin import OperationsAdmin
    from repo_catalog.application.provider_fetch import acquire_github
    from repo_catalog.domain.context_admission import (
        AdmissionSelection,
        DependencySet,
        create_local_admission_service,
    )
    from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity

    case, current = provider_case, [[]]
    document = request_document(case)
    identity = RequestIdentity(*document["request_identity"])
    stop = [False]

    def handle(request):
        if stop[0] and request.url.path.endswith("/reviews"):
            stop[0] = False
            assert (
                OperationsAdmin(case.directory).transition(identity)["state"]
                == "stopped"
            )
        return response_for(request, current[0])

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document(case),
            clock_us=lambda: 100,
        )
        assert first["status"] == "complete"
        before = reviews_evidence(case)
        authorization, admission, _ = create_local_admission_service(
            "provider_intake",
            grants=DependencySet(
                resources=frozenset(case.keys.values()),
                sources={case.source},
                provider_registrations={case.service},
            ),
            selection=AdmissionSelection(all_selected=True),
        )
        current[0] = [
            {"id": 10, "body": "received but not admitted", "state": "APPROVED"}
        ]
        stop[0] = True
        with pytest.raises(CoordinationError) as failure:
            acquire_github(
                case.directory,
                document,
                client=client,
                authorization=authorization,
                admission=admission,
                clock_us=lambda: 200,
            )
        assert failure.value.code == "CONTINUATION_UNAVAILABLE"
        assert reviews_evidence(case) == before
        with Context.snapshot(case.directory) as context:
            assert context.candidates(case.keys["review"], "text_body_sha256") == ()
        assert (
            OperationsAdmin(case.directory).transition(identity, resume=True)["state"]
            == "open"
        )
        document["new_request"] = False
        retried = acquire_github(
            case.directory,
            document,
            client=client,
            authorization=authorization,
            admission=admission,
            clock_us=lambda: 300,
        )
    assert retried.status == "complete"
    view = case.view(capsys, case.keys["review"])
    assert tuple(view["resolved_texts"].values()) == ("received but not admitted",)
    assert not (case.directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("boundary", ["before-commit", "after-commit"])
def test_terminal_cancellation_preserves_only_actually_committed_whole_proof(
    provider_case, tmp_path, capsys, monkeypatch, boundary
):
    from repo_catalog.application.provider_acquisition import ProviderAcquisition
    from repo_catalog.domain.models import CatalogError

    case = provider_case
    original_prove, original_admit = (
        Context.prove_collection,
        ProviderAcquisition.admit_batch,
    )
    armed, stamp = [False], [100]

    def prove(context, claim, observation, **kwargs):
        result = original_prove(context, claim, observation, **kwargs)
        if armed[0] and observation.collection_kind == "reviews":
            armed[0] = False
            # Genuine terminal+proof SQL has run, inside its actual transaction.
            raise CatalogError("CANCELLED", "before actual terminal unit commit")
        return result

    def admit(acquisition, batch, **kwargs):
        result = original_admit(acquisition, batch, **kwargs)
        if armed[0] and any(
            observation.collection_kind == "reviews"
            for _, observation, _ in batch.collection_proofs
        ):
            armed[0] = False
            # The actual facade has committed the whole proof before returning.
            raise CatalogError("CANCELLED", "after actual terminal unit commit")
        return result

    with httpx.Client(
        transport=httpx.MockTransport(lambda request: response_for(request, []))
    ) as client:
        first, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document(case),
            clock_us=lambda: stamp[0],
        )
        assert first["status"] == "complete"
        before = reviews_evidence(case)
        if boundary == "before-commit":
            monkeypatch.setattr(Context, "prove_collection", prove)
        else:
            monkeypatch.setattr(ProviderAcquisition, "admit_batch", admit)
        armed[0], stamp[0] = True, 200
        cancelled, document = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            request_document(case),
            clock_us=lambda: stamp[0],
        )
        assert (
            cancelled["status"] == "partial"
            and cancelled["failure_code"] == "CANCELLED"
        )
        assert not armed[0]
        after = reviews_evidence(case)
        if boundary == "before-commit":
            assert after == before
        else:
            assert all(len(a) == len(b) + 1 for a, b in zip(after, before, strict=True))
        reports = [
            item
            for item in case.view(capsys, case.keys["pull"])["collections"]
            if item["collection_kind"] == "reviews"
        ]
        assert all(
            item["state"] == "complete" and item["members"] == [] for item in reports
        )
        assert {item["observed_at_us"] for item in reports} == (
            {100} if boundary == "before-commit" else {100, 200}
        )
        # Retry is the same cumulative request, with a genuinely new response.
        document["new_request"], stamp[0] = False, 300
        recovered, _ = _network_cli(
            case,
            tmp_path,
            capsys,
            monkeypatch,
            client,
            document,
            clock_us=lambda: stamp[0],
        )
    assert recovered["status"] == "complete"
    final = reviews_evidence(case)
    assert all(len(a) == len(b) + 1 for a, b in zip(final, after, strict=True))
    assert not (case.directory / "p1-recovery-stop.json").exists()
