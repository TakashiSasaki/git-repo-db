"""Actual PR documents and review queries retain independent current evidence."""

import json
from uuid import uuid4

import pytest

from repo_catalog.adapters.github import production_intake as intake
from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.provider_acquisition import (
    ProviderIntakeBatch,
    ProviderPullRequestIntake,
    ProviderReviewIntake,
    ProviderReviewThreadIntake,
    make_provenance,
)
from tests.integration.p3.test_production_context import SERVICE, SOURCE, directory
from tests.integration.p5.test_modeled_metadata_retirement import (
    ORIGIN,
    batch,
    payload,
    service,
)
from tests.integration.p5.test_pr_assessment import Fixture
from tests.support.context_admission import fixture_transaction

__all__ = ["directory"]


@pytest.mark.parametrize(
    "body", ["new independently acquired body", "", None], ids=["text", "empty", "null"]
)
def test_sparse_actual_pr_body_keeps_title_document_original(directory, body):
    acquisition, parent = service(directory, "pull_request")
    acquisition.admit_batch(batch("pull_request", payload()))
    title_key = ResourceKey.document(parent, "document", "pr_title", "51")
    body_key = ResourceKey.document(parent, "document", "pr_body", "51")
    query = ContextQueryService(directory, mode="context_only")
    title_before = query.get_context_resource(title_key, include_text=True)
    body_before = query.get_context_resource(body_key, include_text=True)
    origin = canonical(
        {"source": "real sparse PR parser", "evidence": "second actual capture"}
    )
    sparse = payload(month=2)
    sparse.pop("title")
    sparse["body"] = body
    acquisition.admit_batch(
        ProviderIntakeBatch(
            SERVICE, pull_requests=(ProviderPullRequestIntake(sparse, 200, origin),)
        )
    )
    title_after = query.get_context_resource(title_key, include_text=True)
    body_after = query.get_context_resource(body_key, include_text=True)
    assert title_after.fields == title_before.fields
    assert title_after.resolved_texts == title_before.resolved_texts
    assert (
        body_after.fields["text_body_sha256"] != body_before.fields["text_body_sha256"]
    )
    assert all(
        candidate.provenance_json == origin and candidate.observed_at_us == 200
        for candidate in body_after.fields["text_body_sha256"]
    )
    assert {
        candidate.provenance_json
        for candidate in title_after.fields["text_body_sha256"]
    } == {ORIGIN}
    if body is None:
        assert body_after.fields["text_body_sha256"][0].value_json == "null"
    else:
        assert list(body_after.resolved_texts.values()) == [body]
    acquisition.admit_batch(
        ProviderIntakeBatch(
            SERVICE,
            pull_requests=(
                ProviderPullRequestIntake(
                    {
                        "id": 51,
                        "number": 2,
                        "state": "closed",
                        "updated_at": "2026-03-01T00:00:00Z",
                    },
                    300,
                    canonical(
                        {
                            "source": "real third PR parser",
                            "evidence": "no document fields",
                        }
                    ),
                ),
            ),
        )
    )
    assert query.get_context_resource(title_key).fields == title_after.fields
    assert query.get_context_resource(body_key).fields == body_after.fields


def test_dismissed_review_remains_queryable_by_actual_state_and_author(tmp_path):
    fixture = Fixture(tmp_path, repository_store=False)
    origin = make_provenance("actual review parser", {"read": str(uuid4())})
    fixture.admit(
        reviews=(
            ProviderReviewIntake(
                100,
                {
                    "id": 200,
                    "state": "APPROVED",
                    "body": "approved summary",
                    "user": {"login": "reviewer"},
                },
                300,
                origin,
            ),
            ProviderReviewIntake(
                100,
                {
                    "id": 201,
                    "state": "DISMISSED",
                    "body": "dismissed summary",
                    "user": {"login": "reviewer"},
                },
                300,
                origin,
            ),
        )
    )
    fixture.observation(
        fixture.parent,
        "reviews",
        origin,
        canonical({}),
        300,
        "complete",
        fixture.reviews[:2],
    )
    query = PRQueryService(tmp_path)
    result = query.get_pr_documents(fixture.parent, kinds=("reviews",))
    assert result.state == "complete" and result.page.total_count == 2
    assert {
        json.loads(c.value_json)
        for item in result.page.items
        for c in item.fields["state"]
    } == {"APPROVED", "DISMISSED"}
    dismissed = query.get_pr_documents(
        fixture.parent,
        kinds=("reviews",),
        metadata_filters={"state": "DISMISSED", "author": "reviewer"},
    )
    assert dismissed.state == "complete" and dismissed.page.total_count == 1
    assert dismissed.page.items[0].resource == fixture.reviews[1]
    assert "dismissed summary" in dismissed.page.items[0].resolved_texts.values()


def test_current_document_and_thread_need_nominal_parent_without_parent_field_capture(
    directory,
):
    parent = ResourceKey.from_native(SERVICE, "pull_request", "51")
    thread = intake.normalize_review_thread(
        SERVICE, "51", {"id": "THREAD-original", "isResolved": False}, 100, ORIGIN
    )
    document = intake.normalize_pull_request(
        SERVICE, {"id": 51, "body": "independent document"}, 100, ORIGIN
    )
    resources = {
        parent,
        thread.primary_resource,
        *(o.resource for o in document.observations),
    }
    resources.update(item[0] for item in document.text_admissions)
    grants = DependencySet(
        resources=resources, sources={SOURCE}, provider_registrations={SERVICE}
    )
    with fixture_transaction(directory, grants) as context:
        context.provider(SERVICE, "github")
        context.source(SOURCE, SERVICE)
    auth, admission, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )
    acquisition = ProviderAcquisition(
        directory, authorization=auth, admission=admission
    )
    acquisition.admit_batch(
        ProviderIntakeBatch(
            SERVICE,
            review_threads=(
                ProviderReviewThreadIntake(
                    "51", {"id": "THREAD-original", "isResolved": False}, 100, ORIGIN
                ),
            ),
        )
    )
    # The body document is an independent typed unit; no parent PR metadata is
    # observed or fabricated merely because its nominal namespace is needed.
    acquisition.admit_units((document,))
    query = ContextQueryService(directory, mode="context_only")
    assert query.get_context_resource(parent).fields == {}
    assert (
        query.get_context_resource(thread.primary_resource)
        .fields["resolved"][0]
        .value_json
        == "false"
    )
    body_key = ResourceKey.document(parent, "document", "pr_body", "51")
    view = query.get_context_resource(body_key, include_text=True)
    assert list(view.resolved_texts.values()) == ["independent document"]
    assert view.fields["text_body_sha256"][0].provenance_json == ORIGIN
