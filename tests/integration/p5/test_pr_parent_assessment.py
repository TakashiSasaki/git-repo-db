"""Repository PR assessment preflights the real parent universe before paging."""

from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from repo_catalog.adapters.github.production_intake import make_document_key
from repo_catalog.adapters.sqlite.catalog_runtime import SnapshotReadLimits
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.application.provider_acquisition import ProviderAcquisition
from repo_catalog.application.provider_fetch import acquire_github
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.provider_acquisition import (
    ProviderPullRequestIntake,
    ProviderRepositoryIntake,
    ProviderReviewIntake,
    make_provenance,
)
from repo_catalog.domain.query_contracts import PageRequest, QueryError
from tests.integration.p5.test_pr_assessment import Fixture
from tests.integration.p5.test_separated_github_fetch import response
from tests.support.context_admission import fixture_context, fixture_service


class Parents(Fixture):
    def __init__(self, path):
        super().__init__(path, repository_store=False)
        self.provider_repository = ResourceKey.from_native(
            self.service, "repository", "10"
        )
        self.parents = (
            self.parent,
            *(
                ResourceKey.from_native(self.service, "pull_request", str(value))
                for value in (101, 102)
            ),
        )
        self.unknown = ResourceKey.from_native(self.service, "pull_request", "999")
        titles = {
            make_document_key(key, "pull_request_document", "pr_title", str(value))
            for key, value in zip(self.parents, (100, 101, 102), strict=True)
        }
        self.grants = replace(
            self.grants,
            resources=self.grants.resources
            | {self.provider_repository, self.unknown, *self.parents, *titles},
        )
        self.auth, _ = fixture_service(self.grants)
        self.admission = fixture_context(self.auth)
        self.api = ProviderAcquisition(
            path, authorization=self.auth, admission=self.admission
        )
        self.admit(
            provider_repositories=(
                ProviderRepositoryIntake(
                    {"id": 10, "full_name": "owner/repo"}, 100, self.anchor
                ),
            ),
            pull_requests=tuple(
                ProviderPullRequestIntake(
                    {
                        "id": value,
                        "number": value - 99,
                        "title": f"parent {value}",
                        "state": "open",
                        "draft": False,
                        "user": {"login": "author"},
                    },
                    200,
                    self.anchor,
                )
                for value in (100, 101, 102)
            ),
        )

    def roster(self, *, observed=300, state="complete", members=None, provenance=None):
        provenance = provenance or make_provenance(
            "parent-fixture", {"read": str(uuid4())}
        )
        self.observation(
            self.provider_repository,
            "pull_requests",
            provenance,
            canonical({}),
            observed,
            state,
            self.parents if members is None else members,
        )

    def documents(self, *, last="complete", observed=300):
        for key in self.parents:
            provenance = make_provenance("parent-fixture", {"read": str(uuid4())})
            self.observation(
                key,
                "reviews",
                provenance,
                canonical({}),
                observed,
                last if key == self.parents[-1] else "complete",
                (),
            )

    def query_parents(self, **kwargs):
        return PRQueryService(self.path).list_pr_assessments(
            self.provider_repository, kinds=("reviews",), **kwargs
        )


def test_parent_scope_preflight_is_pinned_shared_and_independent_of_page_limit(
    tmp_path, monkeypatch
):
    fixture = Parents(tmp_path)
    fixture.roster()
    fixture.documents(last="partial")
    service = PRQueryService(tmp_path)
    original = service.open_snapshot
    snapshots = []

    @contextmanager
    def counted(**kwargs):
        with original(**kwargs) as snapshot:
            snapshots.append(snapshot.token.encode())
            yield snapshot

    monkeypatch.setattr(service, "open_snapshot", counted)
    first = service.list_pr_assessments(
        fixture.provider_repository, kinds=("reviews",), page=PageRequest(limit=1)
    )
    assert len(snapshots) == 1
    assert first.state == "partial"
    assert first.page.total_count == 3 and first.page.has_more
    assert first.page.items[0].assessment.state == "complete"
    assert any(
        gap.get("parent") == fixture.parents[-1].coordinates()
        for gap in first.coverage["missing"]
    )
    full = fixture.query_parents()
    assert full.coverage == first.coverage
    second = fixture.query_parents(
        page=PageRequest(limit=1, cursor=first.page.next_cursor)
    )
    assert second.page.snapshot_token == first.page.snapshot_token
    assert second.coverage == first.coverage
    assert second.page.items != first.page.items
    assert first.to_dict()["items"][0]["document_count"] == 0


def test_positive_selected_parents_exclude_unrelated_gaps_but_unknown_membership_cannot_complete_empty(
    tmp_path,
):
    fixture = Parents(tmp_path)
    fixture.roster(state="partial", members=fixture.parents[:2])
    fixture.documents(last="partial")
    assert fixture.query_parents().state == "partial"
    selected = fixture.query_parents(parents=(fixture.parents[0],))
    assert selected.state == "complete"
    assert selected.parent_listing["state"] == "partial"
    absent = fixture.query_parents(parents=(fixture.unknown,))
    assert absent.state != "complete" and absent.page.total_count == 0
    assert any(
        gap["reason"] == "selected_parent_membership_unknown"
        for gap in absent.coverage["missing"]
    )
    assert fixture.query_parents(parents=()).state != "complete"


def test_missing_universe_is_unknown_even_when_no_known_parents_are_returned(tmp_path):
    fixture = Parents(tmp_path)
    fixture.documents()
    result = fixture.query_parents()
    assert result.state == "unknown" and result.page.total_count == 0
    assert result.parent_listing["reason"] == "matching_listing_unavailable"


@pytest.mark.parametrize("page", [False, True])
def test_positive_child_or_partial_page_cannot_prove_family_listing_or_parent_universe(
    tmp_path, page
):
    fixture = Parents(tmp_path)
    original = make_provenance("actual-parent-fixture", {"read": "child-prefix"})
    fixture.admit(
        reviews=(
            ProviderReviewIntake(
                100, {"id": 200, "body": "positive usable child"}, 300, original
            ),
        )
    )
    if page:
        fixture.observation(
            fixture.parent,
            "reviews",
            original,
            canonical({}),
            300,
            "partial",
            fixture.reviews[:1],
        )
    documents = PRQueryService(tmp_path).get_pr_documents(
        fixture.parent, kinds=("reviews",)
    )
    assert documents.state != "complete"
    assert documents.page.total_count == (1 if page else 0)
    parents = fixture.query_parents()
    assert parents.state == "unknown" and parents.page.total_count == 0
    assert parents.parent_listing["reason"] == "matching_listing_unavailable"


def test_current_parent_terminal_and_equal_clock_conflicts_are_not_borrowed(tmp_path):
    fixture = Parents(tmp_path)
    fixture.documents()
    provenance = make_provenance("parent-fixture", {"read": "same-original"})
    fixture.roster(observed=300, provenance=provenance)
    assert fixture.query_parents().state == "complete"
    fixture.roster(observed=400, state="partial", provenance=provenance)
    assert fixture.query_parents().state == "partial"
    fixture.roster(observed=500)
    assert fixture.query_parents().state == "complete"
    fixture.roster(observed=500, state="partial", members=fixture.parents[:1])
    result = fixture.query_parents()
    assert result.state == "conflict" and result.page.total_count == 0


@pytest.mark.parametrize(
    "old,latest,complete",
    [
        (("partial",), ("complete",), True),
        (("complete",), ("complete", "partial"), False),
        (("complete",), ("unknown",), False),
        (("complete", "partial"), ("complete",), True),
    ],
)
def test_current_document_terminals_ignore_stale_states_and_preserve_latest_unknown_or_conflict(
    tmp_path, old, latest, complete
):
    fixture = Parents(tmp_path)
    fixture.roster()
    fixture.documents()
    for observed, states in ((300, old), (400, latest)):
        for state in states:
            fixture.observation(
                fixture.parent,
                "reviews",
                make_provenance("parent-fixture", {"read": str(uuid4())}),
                canonical({}),
                observed,
                state,
                (),
            )
    ordinary = PRQueryService(tmp_path).get_pr_documents(
        fixture.parent, kinds=("reviews",)
    )
    aggregate = fixture.query_parents()
    assert ordinary.coverage["complete_for_requested_scope"] is complete
    assert aggregate.coverage["complete_for_requested_scope"] is complete
    if not complete:
        assert any(
            gap.get("parent") == fixture.parent.coordinates()
            for gap in aggregate.coverage["missing"]
        )


def test_parent_preflight_does_not_materialize_later_result_bodies(
    tmp_path, monkeypatch
):
    fixture = Parents(tmp_path)
    fixture.roster()
    fixture.documents(last="partial")
    service = PRQueryService(tmp_path)
    original = service._view
    materialized = []

    def measured(context, key, work, **options):
        if options.get("include_text"):
            materialized.append(key)
        return original(context, key, work, **options)

    monkeypatch.setattr(service, "_view", measured)
    result = service.list_pr_assessments(
        fixture.provider_repository, kinds=("reviews",), page=PageRequest(limit=1)
    )
    assert result.state == "partial" and result.page.total_count == 3
    assert materialized == [fixture.parents[0]]


def test_parent_preflight_read_interruption_after_first_parent_issues_no_page_or_cursor(
    tmp_path, monkeypatch
):
    fixture = Parents(tmp_path)
    fixture.roster()
    fixture.documents()
    stopped = [False]
    service = PRQueryService(
        tmp_path, read_limits=SnapshotReadLimits(on_steps=lambda _: stopped[0])
    )
    assess = service._assess_pr_documents
    view = service._view
    completed, materialized = [], []

    def interrupt_after_one(*args, **kwargs):
        result = assess(*args, **kwargs)
        completed.append(result.resource)
        stopped[0] = True
        return result

    def measured(context, key, work, **options):
        if options.get("include_text"):
            materialized.append(key)
        return view(context, key, work, **options)

    monkeypatch.setattr(service, "_assess_pr_documents", interrupt_after_one)
    monkeypatch.setattr(service, "_view", measured)
    with pytest.raises((QueryError, CoordinationError)) as error:
        service.list_pr_assessments(
            fixture.provider_repository, kinds=("reviews",), page=PageRequest(limit=1)
        )
    assert error.value.code == "QUERY_BUDGET"
    assert completed == [fixture.parents[0]]
    assert materialized == []
    assert not (tmp_path / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "filters",
    [
        {"state": "closed"},
        {"draft": True},
        {"author": "other"},
        {"text_literal": "not present"},
    ],
)
def test_metadata_and_literal_filters_never_hide_later_parent_gaps(tmp_path, filters):
    fixture = Parents(tmp_path)
    fixture.roster()
    fixture.documents(last="partial")
    result = fixture.query_parents(**filters)
    assert result.state == "partial" and result.page.total_count == 0
    assert any(
        gap.get("parent") == fixture.parents[-1].coordinates()
        for gap in result.coverage["missing"]
    )


def test_document_parent_scope_does_not_inherit_unrequested_code_or_timeline_gaps(
    tmp_path,
):
    fixture = Parents(tmp_path)
    fixture.roster()
    fixture.documents()
    assert fixture.query_parents().state == "complete"
    assert (
        fixture.query_parents(assessment="code", require_git=False).state != "complete"
    )
    assert fixture.query_parents(path="unseen.txt").state != "complete"


def test_metadata_filter_returning_no_parents_does_not_hide_missing_exact_code_listings(
    tmp_path,
):
    fixture = Parents(tmp_path)
    fixture.roster()
    result = fixture.query_parents(assessment="code", require_git=False, state="closed")
    assert result.state != "complete" and result.page.total_count == 0
    missing = {
        gap["kind"]
        for gap in result.coverage["missing"]
        if gap.get("parent") == fixture.parent.coordinates()
    }
    assert {"pr_commits", "pr_files"} <= missing


def test_literal_filter_reads_actual_context_document_body_with_a_finite_shared_byte_budget(
    tmp_path,
):
    fixture = Parents(tmp_path)
    fixture.roster()
    fixture.documents()
    provenance = make_provenance("parent-fixture", {"read": "review-body"})
    fixture.admit(
        reviews=(
            ProviderReviewIntake(
                100, {"id": 200, "body": "precise needle\n\x00tail"}, 400, provenance
            ),
        )
    )
    fixture.observation(
        fixture.parent,
        "reviews",
        provenance,
        canonical({}),
        400,
        "complete",
        fixture.reviews[:1],
    )
    result = fixture.query_parents(text_literal="needle\n\x00tail")
    assert result.state == "complete" and result.page.total_count == 1
    assert result.page.items[0].resource == fixture.parent
    assert fixture.query_parents(text_literal="NEEDLE").page.total_count == 0
    with pytest.raises(QueryError) as error:
        fixture.query_parents(text_literal="needle", max_bytes=1)
    assert error.value.code == "QUERY_BUDGET"


def test_shared_parent_budget_and_changed_snapshot_refuse_without_page_success(
    tmp_path,
):
    fixture = Parents(tmp_path)
    fixture.roster()
    fixture.documents()
    with pytest.raises(QueryError) as error:
        fixture.query_parents(max_work=1)
    assert error.value.code == "QUERY_BUDGET"
    first = fixture.query_parents(page=PageRequest(limit=1))
    fixture.roster(observed=500, state="partial")
    with pytest.raises(QueryError):
        fixture.query_parents(page=PageRequest(limit=1, cursor=first.page.next_cursor))


@pytest.mark.parametrize(
    "options", [{"assessment": "code", "path": "ignored.txt"}, {"path": ""}]
)
def test_requested_selectors_are_validated_even_without_a_known_parent_universe(
    tmp_path, options
):
    fixture = Parents(tmp_path)
    with pytest.raises(QueryError) as error:
        fixture.query_parents(**options)
    assert error.value.code == "INVALID_INPUT"


@pytest.mark.parametrize("repository_scope", [False, True])
def test_unknown_document_kind_cannot_become_complete_from_a_generic_collection_claim(
    tmp_path, repository_scope
):
    fixture = Parents(tmp_path)
    fixture.roster()
    fixture.observation(
        fixture.parent,
        "unknown-document-family",
        make_provenance("actual-parent-fixture", {"read": "unsupported-family"}),
        canonical({}),
        300,
        "complete",
        (),
    )
    query = PRQueryService(tmp_path)
    with pytest.raises(QueryError) as error:
        if repository_scope:
            query.list_pr_assessments(
                fixture.provider_repository, kinds=("unknown-document-family",)
            )
        else:
            query.get_pr_documents(fixture.parent, kinds=("unknown-document-family",))
    assert error.value.code == "INVALID_INPUT"


@pytest.mark.parametrize("bounded", [False, True])
def test_real_http_paginated_all_pr_parent_universe_retains_truthful_prefix(
    tmp_path, bounded
):
    fixture = Parents(tmp_path)
    fixture.documents()
    source = str(uuid4())
    grants = replace(fixture.grants, sources={source})
    authorization, _ = fixture_service(grants)
    admission = fixture_context(authorization)
    document = {
        "operation": "sync",
        "service_instance_uuidv4": fixture.service,
        "source_registration_uuidv4": source,
        "request_identity": [str(uuid4()), str(uuid4())],
        "new_request": True,
        "owner": "owner",
        "repository": "repo",
        "sections": ["pull_requests"],
        "rest_base_url": "https://api.example.test",
        "graphql_url": "https://api.example.test/graphql",
    }
    if bounded:
        document["max_pages"] = 2
    calls = []

    def handle(request):
        calls.append(request)
        if request.url.path == "/repos/owner/repo":
            return response(request, {"id": 10, "full_name": "owner/repo"})
        if request.url.path.endswith("/pulls"):
            assert request.url.params["state"] == "all"
            if request.url.params.get("page") == "2":
                return response(request, [{"id": 101, "number": 2}])
            return response(
                request,
                [{"id": 100, "number": 1}],
                link='<https://api.example.test/repos/owner/repo/pulls?state=all&per_page=100&page=2>; rel="next"',
            )
        return response(request, {"id": 99 + int(request.url.path.rsplit("/", 1)[1])})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        report = acquire_github(
            tmp_path,
            document,
            authorization=authorization,
            admission=admission,
            client=client,
        )
    result = fixture.query_parents()
    assert result.parent_listing["state"] == ("partial" if bounded else "complete")
    assert result.page.total_count == (1 if bounded else 2)
    assert result.state == ("partial" if bounded else "complete")
    assert report.network_bytes > 0 and report.http_attempts == len(calls)
