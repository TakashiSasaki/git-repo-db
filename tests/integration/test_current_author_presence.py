"""Sparse provider actor objects cannot assert an unobserved null login."""

import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.domain.models import CatalogError
from tests.integration.test_current_resources import issue
from tests.integration.test_current_resources import resources as _resources_fixture

FAMILIES = (
    "issue",
    "issue-comment",
    "review",
    "review-comment",
    "graphql-review-comment",
)
ABSENT = object()
OLD_CLOCK = "2026-01-01T00:00:00Z"
NEW_CLOCK = "2026-02-01T00:00:00Z"
NEWEST_CLOCK = "2026-03-01T00:00:00Z"


@pytest.fixture(name="resources")
def _resources(tmp_path):
    yield from _resources_fixture.__wrapped__(tmp_path)


def project(
    family, actor=ABSENT, *, context=None, observed=100, newer=False, clock=None
):
    context = context or {"acquisition_scope": {}}
    value = {
        "id": 51,
        "body": "new body" if newer else "original body",
        "updated_at": clock or (NEW_CLOCK if newer else OLD_CLOCK),
    }
    if family == "issue":
        value.update(number=2, title="Issue title", state="open")
    elif family == "graphql-review-comment":
        value["fullDatabaseId"] = "51"
        value["updatedAt"] = value.pop("updated_at")
    if actor is not ABSENT:
        value["author" if family == "graphql-review-comment" else "user"] = actor
    if family == "issue-comment":
        candidate = current_parser.issue_comment(value, context, observed, "12")
    elif family == "graphql-review-comment":
        candidate = current_parser.review_comment(
            value, context, observed, graphql=True
        )
    else:
        candidate = getattr(current_parser, family.replace("-", "_"))(
            value, context, observed
        )
    return {**candidate, "parsed_at_us": observed + 1}


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize(
    "actor", (ABSENT, {}, {"id": 1}), ids=("absent", "empty-object", "id-only")
)
def test_omitted_login_never_becomes_an_explicit_null_author(family, actor):
    assert "author" not in project(family, actor)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("actor", (None, {"login": None}), ids=("null", "null-login"))
def test_explicit_null_author_remains_an_assertion(family, actor):
    candidate = project(family, actor)
    assert "author" in candidate and candidate["author"] is None


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("login", ("observed-author", ""), ids=("value", "empty"))
def test_present_login_preserves_its_exact_value(family, login):
    candidate = project(family, {"login": login})
    assert candidate["author"] == login


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("actor", (True, [], {"login": 1}))
def test_invalid_actor_shape_is_still_rejected(family, actor):
    with pytest.raises(CatalogError) as failure:
        project(family, actor)
    assert failure.value.code == "API_SCHEMA"


def context_for(resources, family):
    adapter, owner, _, change, _ = resources
    scope = {**owner, "endpoint": "synthetic/author/" + family}
    context = {**owner, "acquisition_scope": scope}
    if family == "issue-comment":
        adapter.admit(issue(resources), source="import")
        context["provider_issue_number"] = 2
    if "review" in family:
        context["change_request_id"] = change
        scope["change_request_id"] = change
    return context


def live_admit(adapter, candidate):
    revision, scope = adapter.capture_context(candidate["acquisition_scope"])
    return adapter.admit(
        candidate, source="live", base_revision=revision, scope_context=scope
    )


def current_candidate(adapter, family):
    table = "review_resources" if "review" in family else "issue_resources"
    column = (
        "provider_change_request_document_id"
        if "review" in family
        else "provider_resource_id"
    )
    row = adapter.c.execute(f"SELECT * FROM {table} WHERE {column}='51'").fetchone()
    return adapter.candidate_from_row(table, row)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("actor", ({}, {"id": 1}), ids=("empty-object", "id-only"))
@pytest.mark.parametrize(
    "null_actor", (None, {"login": None}), ids=("null", "null-login")
)
def test_sparse_actor_preserves_value_and_capture_until_explicit_null(
    resources, family, actor, null_actor, monkeypatch
):
    adapter, *_ = resources
    context = context_for(resources, family)
    # Model a field captured before the extraction correction, then parse the
    # sparse response with the corrected producer. Their origins stay distinct.
    monkeypatch.setattr(current_parser, "PARSER_VERSION", "1")
    first = project(family, {"login": "original-author"}, context=context)
    assert live_admit(adapter, first).status == "accepted"
    proof = current_candidate(adapter, family)["field_evidence"]['["author"]']
    assert proof["parser_version"] == "1"
    monkeypatch.setattr(current_parser, "PARSER_VERSION", "2")
    partial = project(family, actor, context=context, observed=200, newer=True)
    assert live_admit(adapter, partial).status == "accepted"
    saved = current_candidate(adapter, family)
    assert saved["body"] == "new body"
    assert saved["author"] == "original-author"
    assert saved["field_evidence"]['["author"]'] == proof
    assert saved["field_evidence"]['["body"]']["observed_at_us"] == 200
    assert saved["field_evidence"]['["body"]']["parser_version"] == "2"
    assert saved["last_checked_at_us"] == 200
    cleared = project(
        family,
        null_actor,
        context=context,
        observed=300,
        newer=True,
        clock=NEWEST_CLOCK,
    )
    assert live_admit(adapter, cleared).status == "accepted"
    saved = current_candidate(adapter, family)
    assert saved["author"] is None
    assert saved["field_evidence"]['["author"]']["observed_at_us"] == 300
    assert saved["field_evidence"]['["author"]']["parser_version"] == "2"
    assert (
        saved["field_evidence"]['["author"]']["parser_module"]
        == current_parser.__name__
    )
    assert adapter.c.execute("PRAGMA foreign_key_check").fetchall() == []
    assert adapter.c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
