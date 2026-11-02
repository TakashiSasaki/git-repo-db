"""Synthetic richer producer fixture for minimum Context metadata read probes."""

from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope, canonical
from repo_catalog.domain.production_context import SourceInventory
from tests.integration.p6.conftest import REPOSITORY, SERVICE, SOURCE
from tests.support.context_admission import fixture_transaction


def prepare_metadata_fixture(directory, data):
    second_repository = "22222222-2222-4222-8222-222222222222"
    second_service = "33333333-3333-4333-8333-333333333333"
    second_source = "44444444-4444-4444-8444-444444444444"
    inventory_scope = canonical(
        {"coverage_kind": "repositories", "service_instance_uuidv4": SERVICE}
    )
    conflict_scope = canonical({"coverage_kind": "repositories", "filter": "conflict"})
    scopes = [
        CoverageScope.source_inventory(SOURCE, inventory_scope, "repositories"),
        CoverageScope.source_inventory(SOURCE, conflict_scope, "repositories"),
        CoverageScope.collection(
            data["pr_key"], "reviews", data["ctx_prov_1"], "reviews"
        ),
        CoverageScope.collection(
            data["issue_key"], "comments", data["ctx_prov_2"], "comments"
        ),
        CoverageScope.resource(data["pr_key"], "unobserved"),
    ]
    grants = DependencySet(
        resources={data["pr_key"], data["issue_key"]},
        repositories={REPOSITORY, second_repository},
        sources={SOURCE, second_source},
        source_repository_pairs={(SOURCE, REPOSITORY), (SOURCE, second_repository)},
        provider_registrations={SERVICE, second_service},
    )
    with fixture_transaction(directory, grants) as context:
        context.provider(second_service, "synthetic", '{"name":"Another Provider"}')
        context.source(second_source, second_service, '{"name":"Empty Source"}')
        context.repository(second_repository)
        context.associate_source(
            SOURCE,
            second_repository,
            '{"evidence":"known-positive","source":"synthetic"}',
        )
        for encoded, state, observed, members in (
            (inventory_scope, "partial", 1700000100000100, (REPOSITORY,)),
            (conflict_scope, "partial", 1700000100000200, (REPOSITORY,)),
            (conflict_scope, "not_applicable", 1700000100000200, ()),
        ):
            observation = SourceInventory(
                SOURCE,
                encoded,
                observed,
                state,
                True,
                members,
                canonical({"source": "synthetic", "evidence": state + encoded}),
            )
            context.inventory(observation)
            scope = CoverageScope.source_inventory(SOURCE, encoded, "repositories")
            if encoded == conflict_scope:
                # Partial/not-applicable reports need no completeness proof. A genuine
                # conflicting terminal cannot be cited as a unique proof.
                context.scope(scope)
                context.admit_coverage(CoverageClaim(scope, observed, state))
            else:
                context.prove_inventory(
                    CoverageClaim(scope, observed, state), observation
                )
    query = ProductionQueryService(directory, mode="context_only")
    coverage = [query.get_context_coverage(scope).to_dict() for scope in scopes]
    assert [value["state"] for value in coverage] == [
        "partial",
        "conflict",
        "complete",
        "complete",
        "unknown",
    ]
    assert [value["known_empty"] for value in coverage] == [
        False,
        False,
        False,
        True,
        False,
    ]
    return {
        "providers": [v.to_dict() for v in query.list_providers()],
        "sources": [v.to_dict() for v in query.list_source_views()],
        "coverage": coverage,
        "service": SERVICE,
        "positive_repositories": sorted((REPOSITORY, second_repository)),
    }
