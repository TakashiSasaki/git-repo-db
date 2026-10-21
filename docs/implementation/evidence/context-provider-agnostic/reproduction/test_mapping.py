"""Synthetic mapping audit against packaged Context DDL and production facade.

These fixtures model attributed claims, not authenticated Provider operations.
MappingOperationEvidence below tests the trusted caller contract only.
"""

import sqlite3
from dataclasses import replace

import pytest

from repo_catalog.adapters.sqlite import p1_schema as schema
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingDisposition,
    MappingOperationEvidence,
    ProviderRepositoryRoleScope,
    ProviderRepositoryScope,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.production_context import ResourceRelation

R1 = "9ebbe38a-f937-40e6-a99c-701835ebcf10"
R2 = "c58b4f17-f58c-4a33-8bc6-eb52c42337d1"
S1 = "aad25448-03eb-4f83-a578-ceec84375b5a"
S2 = "80f5c4f9-6d6b-4691-af3c-00ab02ad9f53"
SOURCE = "4d756d99-892a-43f8-a096-e05ff8c88d74"
P1 = ResourceKey(S1, "repository", "42")
P2 = ResourceKey(S2, "repository", "42")
PROV = canonical({"source": "synthetic.audit", "evidence": "mapping-report-1"})


def claim(resource=P1, target=R1, time=10):
    return ResourceRepositoryRelation(
        resource,
        "represents_repository",
        FieldClock("provider", time),
        canonical(target),
        PROV,
        time + 1,
    )


@pytest.fixture
def catalog(tmp_path):
    assert sqlite3.sqlite_version_info >= (3, 51, 3)
    schema.initialize(tmp_path / "context.sqlite3", "context", R1, S1)
    with Context.transaction(tmp_path) as ctx:
        ctx.provider(S1, "github")
        ctx.provider(S2, "gitlab")
        ctx.repository(R1)
        ctx.repository(R2)
        ctx.resource(P1)
        ctx.resource(P2)
    return tmp_path


def test_mapping_forward_reverse_multi_provider_same_id(catalog):
    with Context.transaction(catalog) as ctx:
        for key in (P1, P2):
            assert ctx.admit_repository_relation(claim(key)) == "insert"
            evaluation = ctx.evaluate_provider_repository(key)
            assert evaluation.state == "single_candidate"
            assert evaluation.active_repository_uuidv4s == (R1,)
            assert len(ctx.relations_for_provider_repository(key)) == 1
        reverse = ctx.relations_for_repository(R1, "represents_repository")
        assert {r.resource for r in reverse} == {P1, P2}
        assert all(r.is_core_resolved_active for r in reverse)


def test_mapping_conflict_not_latest_winner_and_exact_replay(catalog):
    older, newer = claim(), claim(target=R2, time=20)
    with Context.transaction(catalog) as ctx:
        assert ctx.admit_repository_relation(newer) == "insert"
        assert ctx.admit_repository_relation(older) == "insert"
        assert ctx.admit_repository_relation(older) == "duplicate"
        evaluation = ctx.evaluate_provider_repository(P1)
        assert evaluation.state == "conflict"
        assert set(evaluation.active_repository_uuidv4s) == {R1, R2}
        assert len(ctx.repository_relations(P1)) == 2
        assert all(
            not row.is_core_resolved_active for row in ctx.repository_relations(P1)
        )
        with pytest.raises(ValueError, match="observation time changed"):
            ctx.admit_repository_relation(replace(older, observed_at_us=99))
        assert len(ctx.repository_relations(P1)) == 2


@pytest.mark.parametrize("kind", ["dispute", "withdraw", "correct"])
def test_mapping_disposition_retains_report_and_requires_local_evidence(catalog, kind):
    original, replacement = claim(), claim(target=R2, time=20)
    disposition = MappingDisposition(
        original.claim_key,
        kind,
        FieldClock("operation", 30),
        PROV,
        31,
        replacement.claim_key if kind == "correct" else None,
    )
    with Context.transaction(catalog) as ctx:
        ctx.admit_repository_relation(original)
        if kind == "correct":
            ctx.admit_repository_relation(replacement)
        ctx.admit_mapping_disposition(disposition)
        before = ctx.evaluate_provider_repository(P1)
        assert original.claim_key in before.active_claims
        evidence = MappingOperationEvidence(frozenset({disposition.disposition_key}))
        qualified = ctx.evaluate_provider_repository(P1, evidence=evidence)
        assert (
            qualified.state
            == {
                "dispute": "contested_candidate",
                "withdraw": "withdrawn",
                "correct": "single_candidate",
            }[kind]
        )
        assert len(ctx.mapping_dispositions(P1)) == 1
        assert len(ctx.repository_relations(P1)) == (2 if kind == "correct" else 1)
        # Ephemeral qualification is not persisted or silently reused.
        assert ctx.evaluate_provider_repository(P1) == before


def test_mapping_unmapped_provider_relation_is_not_null(catalog):
    issue = ResourceKey(S1, "issue", "7")
    role = ProviderRepositoryRoleScope(
        "owning_repository",
        FieldClock("provider", 10),
        "unresolved_provider_only",
        P1.provider_resource_id,
        observed_at_us=11,
    )
    scope = ProviderRepositoryScope({"owning_repository": role})
    relation = ResourceRelation(
        issue, "provider_repository_roles", (P1,), PROV, scope.encoded, 11
    )
    with Context.transaction(catalog) as ctx:
        ctx.resource(issue)
        assert ctx.evaluate_provider_repository(P1).state == "unmapped"
        assert ctx.repository_relations(issue) == ()
        assert ctx.provider_repository_roles(issue) == ()
        ctx.relation(relation)
        roles = ctx.provider_repository_roles(issue)
        assert len(roles) == 1 and roles[0].mapping.state == "unmapped"
        assert roles[0].scope.state == "unresolved_provider_only"
        assert roles[0].scope.provider_repository_id == "42"
        assert ctx.repository_relations(issue) == ()
        ctx.admit_repository_relation(claim())
        assert (
            ctx.provider_repository_roles(issue)[0].mapping.state == "single_candidate"
        )
        assert ctx.relations(issue, "provider_repository_roles") == (relation,)


def test_mapping_registration_precondition_not_core_existence(catalog):
    # Context can remain valid and queryable with zero Core/Access databases.
    assert not (catalog / "core.sqlite3").exists()
    assert not (catalog / "access.sqlite3").exists()
    with Context.transaction(catalog) as ctx:
        ctx.admit_repository_relation(claim())
        assert ctx.repository_relations(P1)[0].is_core_resolved_active
        unknown = "cd32f292-45f9-4f98-90e8-33beb53c6f9f"
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            ctx.admit_repository_relation(claim(target=unknown))
        assert len(ctx.repository_relations(P1)) == 1
    with Context.snapshot(catalog) as ctx:
        assert ctx.evaluate_provider_repository(P1).active_repository_uuidv4s == (R1,)


def test_mapping_source_membership_and_registration_do_not_assert_mapping(catalog):
    with Context.transaction(catalog) as ctx:
        ctx.source(SOURCE, S1)
        ctx.associate_source(SOURCE, R1)
        ctx.resource(P1, R1)
        assert ctx.source_repositories(SOURCE) == (R1,)
        assert ctx.evaluate_provider_repository(P1).state == "unmapped"
        assert ctx.relations_for_repository(R1, "represents_repository") == ()


def test_mapping_disposition_missing_claim_rejected_without_staging(catalog):
    disposition = MappingDisposition(
        claim().claim_key, "withdraw", FieldClock("operation", 30), PROV, 31
    )
    with Context.transaction(catalog) as ctx:
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            ctx.admit_mapping_disposition(disposition)
        assert ctx.mapping_dispositions(P1) == ()
        ctx.admit_repository_relation(claim())
        assert ctx.admit_mapping_disposition(disposition) == "insert"
        assert ctx.admit_mapping_disposition(disposition) == "duplicate"
