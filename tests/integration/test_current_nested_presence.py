"""GraphQL child object presence is distinct from its projected field presence."""

import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.domain.models import CatalogError
from tests.integration.test_current_author_presence import (
    NEW_CLOCK,
    NEWEST_CLOCK,
    OLD_CLOCK,
    context_for,
    live_admit,
)
from tests.integration.test_current_resources import resources as _resources_fixture

FIELDS = (
    ("pullRequestReview", "fullDatabaseId", "review_provider_resource_id", "11"),
    ("replyTo", "fullDatabaseId", "in_reply_to_provider_resource_id", "62"),
    ("commit", "oid", "target_commit_oid", "a" * 40),
    ("originalCommit", "oid", "original_commit_oid", "b" * 40),
)


@pytest.fixture(name="resources")
def _resources(tmp_path):
    yield from _resources_fixture.__wrapped__(tmp_path)


def project(fields, *, context=None, observed=100, clock=OLD_CLOCK, provider="61"):
    candidate = current_parser.review_comment(
        {
            "fullDatabaseId": provider,
            "body": "original body" if observed == 100 else "updated body",
            "updatedAt": clock,
            **fields,
        },
        context or {"acquisition_scope": {}},
        observed,
        graphql=True,
    )
    return {**candidate, "parsed_at_us": observed + 1}


@pytest.mark.parametrize("source,key,target,known", FIELDS)
@pytest.mark.parametrize("nested", ({}, {"unselected": "attribute"}))
def test_object_without_projected_identity_does_not_assert_null(
    source, key, target, known, nested
):
    assert target not in project({source: nested})


@pytest.mark.parametrize("source,key,target,known", FIELDS)
def test_explicit_null_child_object_asserts_null(source, key, target, known):
    candidate = project({source: None})
    assert target in candidate and candidate[target] is None


@pytest.mark.parametrize("source,key,target,known", FIELDS[:2])
def test_existing_parent_with_null_database_id_is_unavailable_not_absent(
    source, key, target, known
):
    with pytest.raises(CatalogError) as failure:
        project({source: {key: None}})
    assert failure.value.code == "CANONICAL_DOCUMENT_ID_MISSING"


@pytest.mark.parametrize("source,key,target,known", FIELDS[2:])
def test_explicit_null_projected_oid_asserts_null(source, key, target, known):
    candidate = project({source: {key: None}})
    assert target in candidate and candidate[target] is None


@pytest.mark.parametrize("source,key,target,known", FIELDS)
@pytest.mark.parametrize("nested", (False, 0, "", [], "not an object"))
def test_malformed_child_shape_cannot_masquerade_as_null(
    source, key, target, known, nested
):
    with pytest.raises(CatalogError) as failure:
        project({source: nested})
    assert failure.value.code == "API_SCHEMA"


@pytest.mark.parametrize("source,key,target,known", FIELDS[:2])
@pytest.mark.parametrize("invalid", (False, 0, "0", ""))
def test_present_parent_id_still_requires_canonical_identity(
    source, key, target, known, invalid
):
    with pytest.raises(CatalogError) as failure:
        project({source: {key: invalid}})
    assert failure.value.code == "CANONICAL_DOCUMENT_ID_MISSING"


@pytest.mark.parametrize("source,key,target,known", FIELDS[2:])
@pytest.mark.parametrize("invalid", ("a" * 39, "a" * 40 + "\x00hidden", {}, 1))
def test_present_oid_still_requires_valid_git_identity(
    source, key, target, known, invalid
):
    with pytest.raises(CatalogError) as failure:
        project({source: {key: invalid}})
    assert failure.value.code == "API_SCHEMA"


def seed_parents(adapter, context):
    review = current_parser.review({"id": 11, "body": "review"}, context, 1)
    assert (
        adapter.admit({**review, "parsed_at_us": 2}, source="import").status
        == "accepted"
    )
    reply = project(
        {"pullRequestReview": {"fullDatabaseId": "11"}},
        context=context,
        provider="62",
    )
    assert adapter.admit(reply, source="import").status == "accepted"


def current(adapter):
    row = adapter.c.execute(
        "SELECT * FROM review_resources WHERE kind='review-comment' "
        "AND provider_change_request_document_id='61'"
    ).fetchone()
    return adapter.candidate_from_row("review_resources", row)


@pytest.mark.parametrize("source,key,target,known", FIELDS)
@pytest.mark.parametrize("nested", ({}, {"unselected": "attribute"}))
@pytest.mark.parametrize("admission_source", ("live", "import"))
def test_sparse_child_preserves_known_target_and_original_field_capture(
    resources, source, key, target, known, nested, admission_source
):
    adapter, *_ = resources
    context = context_for(resources, "graphql-review-comment")
    seed_parents(adapter, context)
    first = project({source: {key: known}}, context=context)
    assert live_admit(adapter, first).status == "accepted"
    proof_key = f'["{target}"]'
    proof = current(adapter)["field_evidence"][proof_key]
    partial = project({source: nested}, context=context, observed=200, clock=NEW_CLOCK)
    result = (
        live_admit(adapter, partial)
        if admission_source == "live"
        else adapter.admit(partial, source="import")
    )
    assert result.status == "accepted"
    saved = current(adapter)
    assert saved[target] == known
    assert saved["field_evidence"][proof_key] == proof
    assert saved["field_evidence"]['["body"]']["observed_at_us"] == 200
    assert saved["last_checked_at_us"] == (200 if admission_source == "live" else 100)
    cleared = project({source: None}, context=context, observed=300, clock=NEWEST_CLOCK)
    result = (
        live_admit(adapter, cleared)
        if admission_source == "live"
        else adapter.admit(cleared, source="import")
    )
    assert result.status == "accepted"
    saved = current(adapter)
    assert saved[target] is None
    assert saved["field_evidence"][proof_key]["observed_at_us"] == 300
    assert (
        saved["field_evidence"][proof_key]["parser_module"] == current_parser.__name__
    )
    assert adapter.c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert adapter.c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize("source,key,target,known", FIELDS[2:])
@pytest.mark.parametrize("admission_source", ("live", "import"))
def test_explicit_null_oid_field_clears_known_target_with_its_own_evidence(
    resources, source, key, target, known, admission_source
):
    adapter, *_ = resources
    context = context_for(resources, "graphql-review-comment")
    assert (
        live_admit(adapter, project({source: {key: known}}, context=context)).status
        == "accepted"
    )
    null_field = project(
        {source: {key: None}}, context=context, observed=200, clock=NEW_CLOCK
    )
    result = (
        live_admit(adapter, null_field)
        if admission_source == "live"
        else adapter.admit(null_field, source="import")
    )
    assert result.status == "accepted"
    saved = current(adapter)
    assert saved[target] is None
    assert saved["field_evidence"][f'["{target}"]']["observed_at_us"] == 200
    assert saved["last_checked_at_us"] == (200 if admission_source == "live" else 100)
