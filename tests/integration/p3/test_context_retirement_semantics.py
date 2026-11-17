"""Current Context obligations across typed fields, proofs and real queries."""

import json
from contextlib import contextmanager

from repo_catalog.application.context_query import ContextQueryService
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageScope,
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.production_context import (
    CollectionObservation,
    ResourceObservation,
)
from repo_catalog.domain.resource_identification import ResourceIdentification
from tests.integration.p3.test_production_context import (
    KEY,
    PROVENANCE,
    REPO,
    SERVICE,
    directory,
    production_grants,
)
from tests.support.context_admission import fixture_transaction

__all__ = ["directory"]
CHILD = ResourceKey.document(KEY, "comment", "comment", "retirement-child")


def provenance(event, parser="tests.fixture.parser-A", version="1"):
    return canonical(
        {"source": parser, "evidence": {"event": event, "parser_version": version}}
    )


def field(
    name,
    value,
    stamp,
    event,
    *,
    observed=None,
    parser="tests.fixture.parser-A",
    version="1",
):
    return FieldCandidate(
        KEY,
        name,
        canonical(value),
        FieldClock("provider.updated_at", stamp),
        provenance(event, parser, version),
        stamp if observed is None else observed,
    )


@contextmanager
def writable(directory):
    grants = production_grants() | DependencySet(resources={CHILD})
    with fixture_transaction(directory, grants) as context:
        context.provider(SERVICE, "github")
        context.repository(REPO)
        context.resource(KEY)
        yield context


def query(directory):
    return ContextQueryService(directory, mode="context_only")


def test_sparse_fields_preserve_exact_body_nested_attributes_and_original_producers(
    directory,
):
    original = provenance("body-original", version="9")
    with writable(directory) as context:
        context.admit_text(
            KEY,
            "é\x00original\r\n",
            FieldClock("provider.updated_at", 10),
            original,
            11,
        )
        context.observe(
            ResourceObservation(
                KEY,
                (
                    field("title", "retained title", 10, "title-original"),
                    field(
                        "milestone.title",
                        "retained milestone",
                        10,
                        "milestone-original",
                    ),
                    field("milestone.state", "closed", 10, "milestone-original"),
                ),
            )
        )
        before_body = context.candidates(KEY, "text_body_sha256")
        context.observe(
            ResourceObservation(
                KEY,
                (
                    field(
                        "author",
                        "new author",
                        20,
                        "sparse",
                        parser="tests.fixture.parser-B",
                        version="0",
                    ),
                    field("milestone.state", "open", 20, "sparse"),
                ),
            )
        )
        assert context.candidates(KEY, "text_body_sha256") == before_body
        assert (
            context.candidates(KEY, "text_body_sha256")[0].provenance_json == original
        )
    view = query(directory).get_context_resource(KEY, include_text=True)
    assert json.loads(view.fields["title"][0].value_json) == "retained title"
    assert (
        json.loads(view.fields["milestone.title"][0].value_json) == "retained milestone"
    )
    assert json.loads(view.fields["milestone.state"][0].value_json) == "open"
    assert "é\x00original\r\n" in view.resolved_texts.values()
    assert view.fields["text_body_sha256"][0].observed_at_us == 11
    with writable(directory) as context:
        context.admit_text(
            KEY, None, FieldClock("provider.updated_at", 30), provenance("null"), 31
        )
        assert context.candidates(KEY, "text_body_sha256")[0].value_json == "null"
        assert context.candidates(KEY, "unobserved") == ()
        context.admit_text(
            KEY, "", FieldClock("provider.updated_at", 40), provenance("empty"), 41
        )
        assert context.db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 2
    final = query(directory).get_context_resource(KEY, include_text=True)
    assert "" in final.resolved_texts.values()
    assert (
        json.loads(final.fields["milestone.title"][0].value_json)
        == "retained milestone"
    )


def test_query_preserves_ties_unknown_clocks_and_real_parser_attribution(directory):
    first = field("title", "first", 10, "first", version="99")
    tied = field(
        "title",
        "second",
        10,
        "second",
        observed=2**60,
        parser="tests.fixture.parser-B",
        version="0",
    )
    with writable(directory) as context:
        for candidate in (first, tied):
            assert context.admit_field(candidate) == "insert"
    alternatives = query(directory).get_context_resource(KEY).fields["title"]
    assert set(alternatives) == {first, tied}
    newer = field(
        "title", "first", 30, "newer", parser="tests.fixture.parser-B", version="0"
    )
    with writable(directory) as context:
        assert context.admit_field(newer) == "insert"
        assert context.admit_field(field("title", "delayed", 20, "delayed")) == "stale"
    assert query(directory).get_context_resource(KEY).fields["title"] == (newer,)
    unknown = field("title", "unknown-clock", None, "unclocked", observed=2**61)
    with writable(directory) as context:
        assert context.admit_field(unknown) == "insert"
    assert set(query(directory).get_context_resource(KEY).fields["title"]) == {
        newer,
        unknown,
    }


def test_membership_proof_survives_later_child_body_edit_without_rebinding(directory):
    scope_json = canonical({"coverage_kind": "comments"})
    observation = CollectionObservation(
        KEY, "comments", PROVENANCE, scope_json, 10, "complete", (CHILD,)
    )
    scope = CoverageScope.collection(KEY, "comments", PROVENANCE, "comments")
    claim = CoverageClaim(scope, 10, "complete")
    with writable(directory) as context:
        context.resource(
            CHILD,
            identification=ResourceIdentification.scoped(
                CHILD, KEY, "comment", "retirement-child"
            ),
        )
        context.admit_text(
            CHILD,
            "old child body",
            FieldClock("provider.updated_at", 1),
            provenance("child-old"),
            1,
        )
        context.collection(observation)
        context.prove_collection(claim, observation, required_scope_json=scope_json)
        before = [
            tuple(row) for row in context.db.execute("SELECT * FROM coverage_proofs")
        ]
    initial = query(directory).get_context_coverage(scope)
    assert initial.state == "complete" and not initial.known_empty
    with writable(directory) as context:
        context.admit_text(
            CHILD,
            "edited child body",
            FieldClock("provider.updated_at", 20),
            provenance("child-new"),
            21,
        )
        assert [
            tuple(row) for row in context.db.execute("SELECT * FROM coverage_proofs")
        ] == before
    after = query(directory).get_context_coverage(scope)
    assert after == initial
    assert (
        "edited child body"
        in query(directory)
        .get_context_resource(CHILD, include_text=True)
        .resolved_texts.values()
    )


def test_query_coverage_owner_and_kind_isolation_has_no_fabricated_empty_claim(
    directory,
):
    empty = CoverageScope.repository(REPO, "api")
    git = CoverageScope.repository(REPO, "git")
    resource = CoverageScope.resource(KEY, "api")
    with writable(directory) as context:
        for scope in (empty, git, resource):
            context.scope(scope)
        context.admit_coverage(
            CoverageClaim(git, 1, "partial", '{"reason":"git only"}')
        )
        context.admit_coverage(
            CoverageClaim(resource, 2, "partial", '{"reason":"resource only"}')
        )
    service = query(directory)
    no_claim = service.get_context_coverage(empty)
    assert no_claim.state == "unknown" and not no_claim.known_empty
    assert no_claim.latest_observed_at_us is None and no_claim.claims == ()
    git_view = service.get_context_coverage(git)
    resource_view = service.get_context_coverage(resource)
    assert git_view.latest_observed_at_us == 1
    assert resource_view.latest_observed_at_us == 2
    assert git_view.scope.owner_kind == "repository"
    assert resource_view.scope.owner_kind == "resource"
    assert git_view.claims[0].details_json == '{"reason":"git only"}'
    assert resource_view.claims[0].details_json == '{"reason":"resource only"}'
