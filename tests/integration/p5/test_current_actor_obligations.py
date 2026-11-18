"""Actual typed Provider intake preserves sparse actor values and their producers."""

import json

import pytest

from repo_catalog.adapters.github import production_intake as intake
from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.domain.context_admission import (
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.provider_acquisition import (
    AcquisitionError,
    ProviderIntakeBatch,
    ProviderIssueCommentIntake,
    ProviderIssueIntake,
    ProviderReviewCommentIntake,
    ProviderReviewIntake,
)
from tests.integration.p3.test_production_context import SERVICE, SOURCE, directory
from tests.support.context_admission import fixture_transaction

__all__ = ["directory"]
FAMILIES = (
    "issue",
    "issue-comment",
    "review",
    "review-comment",
    "graphql-review-comment",
)
ABSENT = object()
CLOCKS = ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z")


def project(family, actor=ABSENT, *, stamp=100, step=0):
    payload = {"id": 51, "body": "body-" + str(step), "updated_at": CLOCKS[step]}
    if family == "issue":
        payload.update(number=2, title="Issue title", state="open")
    if family == "graphql-review-comment":
        payload.update(fullDatabaseId="51", updatedAt=payload.pop("updated_at"))
    if actor is not ABSENT:
        payload["author" if family == "graphql-review-comment" else "user"] = actor
    origin = canonical(
        {
            "source": "actual actor intake",
            "evidence": {"source_registration_uuidv4": SOURCE, "step": step},
            "module": "actor-source",
            "version": str(step + 1),
        }
    )
    if family == "issue":
        unit = intake.normalize_issue(SERVICE, payload, stamp, origin)
        batch = ProviderIntakeBatch(
            SERVICE, issues=(ProviderIssueIntake(payload, stamp, origin),)
        )
    elif family == "issue-comment":
        unit = intake.normalize_issue_comment(
            SERVICE, "issue", "12", payload, stamp, origin
        )
        batch = ProviderIntakeBatch(
            SERVICE,
            issue_comments=(
                ProviderIssueCommentIntake("issue", "12", payload, stamp, origin),
            ),
        )
    elif family == "review":
        unit = intake.normalize_review(SERVICE, "12", payload, stamp, origin)
        batch = ProviderIntakeBatch(
            SERVICE, reviews=(ProviderReviewIntake("12", payload, stamp, origin),)
        )
    else:
        graphql = family == "graphql-review-comment"
        unit = intake.normalize_review_comment(
            SERVICE, "12", payload, stamp, origin, graphql=graphql
        )
        batch = ProviderIntakeBatch(
            SERVICE,
            review_comments=(
                ProviderReviewCommentIntake(
                    "12", payload, stamp, origin, graphql=graphql
                ),
            ),
        )
    return unit, batch


def fields(unit):
    return {
        candidate.field_name: json.loads(candidate.value_json)
        for observation in unit.observations
        for candidate in observation.fields
        if candidate.resource == unit.primary_resource
    }


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize(
    "actor", (ABSENT, {}, {"id": 1}), ids=("absent", "empty-object", "id-only")
)
def test_omitted_login_does_not_assert_null(family, actor):
    assert "author" not in fields(project(family, actor)[0])


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("actor", (None, {"login": None}), ids=("null", "null-login"))
def test_explicit_null_actor_asserts_null(family, actor):
    assert fields(project(family, actor)[0])["author"] is None


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("login", ("observed-author", ""), ids=("value", "empty"))
def test_present_login_preserves_exact_value(family, login):
    assert fields(project(family, {"login": login})[0])["author"] == login


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("actor", (True, [], {"login": 1}))
def test_invalid_actor_shape_is_refused(family, actor):
    with pytest.raises(AcquisitionError) as error:
        project(family, actor)
    assert error.value.code == "MALFORMED_ACTOR"


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("actor", ({}, {"id": 1}), ids=("empty-object", "id-only"))
@pytest.mark.parametrize(
    "null_actor", (None, {"login": None}), ids=("null", "null-login")
)
def test_sparse_actor_keeps_exact_original_until_genuine_null_or_clockless_alternative(
    directory, family, actor, null_actor
):
    first, first_batch = project(family, {"login": "original-author"})
    sparse, sparse_batch = project(family, actor, stamp=200, step=1)
    cleared, cleared_batch = project(family, null_actor, stamp=300, step=2)
    keys = {
        observation.resource
        for unit in (first, sparse, cleared)
        for observation in unit.observations
    }
    keys |= {
        ResourceKey.from_native(SERVICE, kind, "12")
        for kind in ("issue", "pull_request")
    }
    grants = DependencySet(
        resources=keys, sources={SOURCE}, provider_registrations={SERVICE}
    )
    with fixture_transaction(directory, grants) as context:
        context.provider(SERVICE, "github")
        context.source(SOURCE, SERVICE)
    authorization, admission, _ = create_local_admission_service(
        "provider_intake",
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )
    service = ProviderAcquisition(
        directory, authorization=authorization, admission=admission
    )
    query = ContextQueryService(directory, mode="context_only")
    service.admit_batch(first_batch)
    before = query.get_context_resource(first.primary_resource, include_text=True)
    service.admit_batch(sparse_batch)
    current = query.get_context_resource(first.primary_resource, include_text=True)
    assert current.fields["author"] == before.fields["author"]
    assert {
        json.loads(candidate.value_json) for candidate in current.fields["author"]
    } == {"original-author"}
    assert "body-1" in current.resolved_texts.values()
    assert any(
        candidate.provenance_json == sparse.provenance_json
        and candidate.observed_at_us == 200
        for candidate in current.fields["text_body_sha256"]
    )
    service.admit_batch(cleared_batch)
    latest = query.get_context_resource(first.primary_resource, include_text=True)
    expected = {"original-author", None} if family == "review" else {None}
    assert {
        json.loads(candidate.value_json) for candidate in latest.fields["author"]
    } == expected
    assert any(
        candidate.provenance_json == cleared.provenance_json
        and candidate.observed_at_us == 300
        for candidate in latest.fields["author"]
    )
    if family == "review":
        assert before.fields["author"][0] in latest.fields["author"]
    assert not (directory / "repository.sqlite3").exists()
    assert not (directory / "p1-recovery-stop.json").exists()
