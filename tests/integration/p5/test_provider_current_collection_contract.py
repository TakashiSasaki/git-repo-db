"""Actual current intake keeps sparse clocks/bodies and request-scoped reports."""

import json
from dataclasses import replace
from uuid import uuid4

import httpx

from repo_catalog.adapters.github.production_intake import (
    make_document_key,
    normalize_review,
    normalize_review_comment,
)
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.application.provider_fetch import acquire_github
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.provider_acquisition import (
    ProviderReviewIntake,
    make_provenance,
)
from tests.integration.p5.conftest import init_catalog_stores
from tests.integration.p5.test_pr_assessment import Fixture
from tests.integration.p5.test_provider_endpoint_identity import Endpoints, response
from tests.support.context_admission import fixture_context, fixture_service


def test_paginated_all_issue_comments_survive_restart_with_latest_edits_and_no_original_archive(
    tmp_path, monkeypatch
):
    init_catalog_stores(tmp_path, stores=("context", "operational"))
    service, source = str(uuid4()), str(uuid4())
    issues = [
        ResourceKey.from_native(service, "issue", str(value)) for value in (20, 21)
    ]
    comments = [
        make_document_key(issues[index], "issue_comment", "comment", str(native))
        for index, native in ((0, 201), (0, 202), (1, 203))
    ]
    grants = DependencySet(
        resources={
            ResourceKey.from_native(service, "repository", "10"),
            *issues,
            *comments,
        },
        sources={source},
        provider_registrations={service},
    )
    auth, admission, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )
    monkeypatch.delenv("RESOURCE_ATLAS_TEST_UNUSED_TOKEN", raising=False)
    stage, calls = [0], []

    def handle(request):
        calls.append((request.url.path, dict(request.url.params)))
        if request.url.path == "/repos/owner/repo":
            value = {"id": 10, "full_name": "owner/repo"}
        elif request.url.path == "/repos/owner/repo/pulls":
            value = []
        elif request.url.path == "/repos/owner/repo/issues":
            assert request.url.params["state"] == "all"
            if request.url.params.get("page") == "2":
                value = [{"id": 21, "number": 2, "state": "closed"}]
            else:
                return httpx.Response(
                    200,
                    request=request,
                    json=[
                        {"id": 20, "number": 1, "state": "open"},
                        {
                            "id": 99,
                            "number": 99,
                            "pull_request": {
                                "url": "https://api.example.test/pulls/99"
                            },
                        },
                    ],
                    headers={
                        "link": '<https://api.example.test/repos/owner/repo/issues?state=all&page=2>; rel="next"'
                    },
                )
        elif request.url.path.endswith("/issues/1/comments"):
            value = [
                {
                    "id": native,
                    "body": "edited exact\n\x00comment"
                    if stage[0] and native == 202
                    else "comment-" + str(native),
                    "updated_at": "2026-02-01T00:00:00Z"
                    if stage[0] and native == 202
                    else "2026-01-01T00:00:00Z",
                }
                for native in (201, 202)
            ]
        elif request.url.path.endswith("/issues/2/comments"):
            value = [
                {
                    "id": 203,
                    "body": "closed comment",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ]
        else:
            raise AssertionError(request.url.path)
        return httpx.Response(200, request=request, json=value)

    for number in (0, 1):
        stage[0] = number
        document = {
            "operation": "sync",
            "service_instance_uuidv4": service,
            "source_registration_uuidv4": source,
            "request_identity": [str(uuid4()), str(uuid4())],
            "new_request": True,
            "owner": "owner",
            "repository": "repo",
            "sections": ["issues", "issue_comments"],
            "rest_base_url": "https://api.example.test",
            "graphql_url": "https://api.example.test/graphql",
            "token_env_var": "RESOURCE_ATLAS_TEST_UNUSED_TOKEN",
        }
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            result = acquire_github(
                tmp_path,
                document,
                authorization=auth,
                admission=admission,
                client=client,
            )
        assert result.status == "complete"
    view = ProductionQueryService(tmp_path).get_context_resource(comments[1])
    assert set(view.resolved_texts.values()) == {"edited exact\n\x00comment"}
    with Context.snapshot(tmp_path) as context:
        assert (
            context.db.execute(
                "SELECT count(*) FROM resources WHERE resource_kind='issue'"
            ).fetchone()[0]
            == 2
        )
        assert (
            context.db.execute(
                "SELECT count(*) FROM resources WHERE document_kind='comment'"
            ).fetchone()[0]
            == 3
        )
        assert (
            context.db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name IN ('fetch_occurrences','stored_bytes','current_collection_pages','document_observations','parser_profiles')"
            ).fetchall()
            == []
        )
    assert not (tmp_path / "transport-archive").exists()
    assert sum(path.endswith("/issues/1/comments") for path, _ in calls) == 2
    assert not any("since" in params for _, params in calls)


def test_review_projection_and_repeated_admission_preserve_clockless_states_sparse_absence_and_body_alternatives(
    tmp_path,
):
    fixture = Fixture(tmp_path, repository_store=False)
    third = make_document_key(fixture.parent, "review", "review_summary", "202")
    fixture.grants = replace(
        fixture.grants, resources=fixture.grants.resources | {third}
    )
    fixture.auth, _ = fixture_service(fixture.grants)
    fixture.admission = fixture_context(fixture.auth)
    fixture.api = ProviderAcquisition(
        tmp_path, authorization=fixture.auth, admission=fixture.admission
    )
    original = make_provenance(
        "caller-supplied-reporter", {"parser_module": "not-a-decoder-authority"}
    )
    unit = normalize_review(
        fixture.service,
        100,
        {
            "id": 200,
            "body": "",
            "submitted_at": "2026-01-01T00:00:00Z",
            "updated_at": "not a review edit clock",
        },
        300,
        original,
    )
    names = {
        candidate.field_name
        for observation in unit.observations
        for candidate in observation.fields
    }
    assert "author" not in names and "provider_updated_at_us" not in names
    assert unit.clock.at_us is None
    comment = normalize_review_comment(
        fixture.service,
        100,
        {"fullDatabaseId": "300", "body": "x"},
        300,
        original,
        graphql=True,
    )
    assert all(
        candidate.clock.at_us is None
        for observation in comment.observations
        for candidate in observation.fields
    )
    assert not comment.repository_references
    for observed in (300, 400, 500):
        fixture.admit(
            reviews=tuple(
                ProviderReviewIntake(
                    100,
                    {
                        "id": native,
                        "state": state,
                        "submitted_at": None
                        if state == "PENDING"
                        else "2026-01-01T00:00:00Z",
                        "body": "edited"
                        if observed > 300 and native == 201
                        else "review-" + str(native),
                    },
                    observed,
                    make_provenance(
                        "actual-review-observation", {"read": str(observed)}
                    ),
                )
                for native, state in (
                    (200, "PENDING"),
                    (201, "APPROVED"),
                    (202, "DISMISSED"),
                )
            )
        )
    views = [
        ProductionQueryService(tmp_path).get_context_resource(key)
        for key in (*fixture.reviews, third)
    ]
    assert [json.loads(view.fields["state"][0].value_json) for view in views] == [
        "PENDING",
        "APPROVED",
        "DISMISSED",
    ]
    assert set(views[1].resolved_texts.values()) == {"edited", "review-201"}
    bodies = views[1].fields["text_body_sha256"]
    assert {candidate.observed_at_us for candidate in bodies} == {300, 400, 500}
    assert {
        json.loads(candidate.provenance_json)["evidence"]["read"]
        for candidate in bodies
    } == {"300", "400", "500"}
    assert all(
        candidate.clock.at_us is None
        for view in views
        for candidates in view.fields.values()
        for candidate in candidates
    )
    with Context.snapshot(tmp_path) as context:
        assert (
            context.db.execute(
                "SELECT count(*) FROM resources WHERE document_kind='review_summary'"
            ).fetchone()[0]
            == 3
        )
        assert (
            context.db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name IN ('document_observations','fetch_occurrences','parser_profiles','parser_profile_selection_decisions')"
            ).fetchall()
            == []
        )


def test_each_http_report_contains_only_its_actual_request_originals_and_times_not_other_request_maxima(
    tmp_path, monkeypatch
):
    fixture = Endpoints(tmp_path)
    monkeypatch.delenv("RESOURCE_ATLAS_TEST_UNUSED_TOKEN", raising=False)
    documents = [fixture.document(0, base="https://alpha.example") for _ in range(2)]
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        first = acquire_github(
            tmp_path,
            documents[0],
            authorization=fixture.auth,
            admission=fixture.admission,
            client=client,
            clock_us=lambda: 900,
        )
        second = acquire_github(
            tmp_path,
            documents[1],
            authorization=fixture.auth,
            admission=fixture.admission,
            client=client,
            clock_us=lambda: 100,
        )
    assert first.status == second.status == "complete"
    assert second.request_identity.values() == tuple(documents[1]["request_identity"])
    originals, times = [], []
    for batch in second.batches:
        for section in (batch.provider_repositories, batch.issues):
            for intake in section:
                originals.append(
                    json.loads(intake.provenance_json)["evidence"]["request_identity"]
                )
                times.append(intake.observed_at_us)
        for claim, observation, _ in batch.collection_proofs:
            originals.append(
                json.loads(observation.provenance_json)["evidence"]["request_identity"]
            )
            times.extend((claim.observed_at_us, observation.observed_at_us))
    assert originals and all(
        value == documents[1]["request_identity"] for value in originals
    )
    assert times and set(times) == {100}
