"""Source history retains exact originals without manufacturing current truth."""

import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    AdmissionSelection,
    DependencySet,
    create_local_admission_service,
    dependencies,
)
from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope, ResourceKey
from repo_catalog.domain.production_context import ContextError, SourceInventory
from repo_catalog.domain.shared_values import encode


def prepare(directory):
    repository, instance, service, source = (str(uuid4()) for _ in range(4))
    initialize(directory / "context.sqlite3", "context", repository, instance)
    member = ResourceKey.from_native(service, "repository", "original-repository")
    scope = encode(
        {"coverage_kind": "repositories", "service_instance_uuidv4": service}
    )
    observation = SourceInventory(
        source,
        scope,
        100,
        "complete",
        True,
        (repository,),
        encode(
            {
                "source": "synthetic",
                "evidence": "original",
                "source_registration_uuidv4": source,
            }
        ),
        provider_repositories=(member,),
    )
    claim = CoverageClaim(
        CoverageScope.source_inventory(source, scope, "repositories"),
        100,
        "complete",
        encode({"original": True}),
    )
    grants = dependencies((observation, claim)) | DependencySet(
        provider_registrations={service}
    )
    authorization, admission, policy = create_local_admission_service(
        operation="salvage_merge",
        grants=grants,
        selection=AdmissionSelection(all_selected=True),
    )
    with Context.transaction(
        directory, authorization=authorization, admission=admission
    ) as context:
        context.provider(service, "synthetic")
        context.source(source, service)
        context.repository(repository)
        context.resource(member)
    return observation, claim, authorization, admission, policy


def test_newer_partial_then_old_complete_history_preserves_original_proof(tmp_path):
    old, claim, authorization, admission, _ = prepare(tmp_path)
    latest = replace(old, observed_at_us=200, state="partial", terminal=False)
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        context.inventory(latest)
        assert context.admit_inventory_history(old, claim) == "insert"
        assert context.admit_inventory_history(old, claim) == "duplicate"
        with pytest.raises(ContextError, match="IMMUTABLE_CLAIM_CONFLICT"):
            context.admit_inventory_history(
                old, replace(claim, details_json=encode({"original": False}))
            )
        assert (
            context.db.execute(
                "SELECT attributes_json FROM source_repositories"
            ).fetchone()[0]
            == "{}"
        )
        assert context.coverage(claim.scope).state != "complete"
        with pytest.raises(sqlite3.IntegrityError, match="superseded or conflicting"):
            context.prove_inventory(claim, old)
    with Context.snapshot(tmp_path) as context:
        assert context.coverage(claim.scope).state != "complete"
        inventories = context.db.execute(
            "SELECT * FROM source_inventory_evidence ORDER BY observed_at_us"
        ).fetchall()
        assert [tuple(row) for row in inventories] == [old.values, latest.values]
        proof = context.db.execute("SELECT * FROM source_coverage_proofs").fetchone()
        assert tuple(proof) == (
            claim.scope.owner_kind,
            claim.scope.encoded,
            claim.observed_at_us,
            claim.state,
            *old.values,
        )


def test_history_decoded_scope_sequence_keeps_exact_owner_and_original(tmp_path):
    old, claim, authorization, admission, _ = prepare(tmp_path)
    decoded_scope = CoverageScope(claim.scope.owner_kind, list(claim.scope.coordinates))
    decoded = replace(claim, scope=decoded_scope)
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        assert context.admit_inventory_history(old, decoded) == "insert"
        assert context.coverage(claim.scope).state == "complete"
        proof = context.db.execute(
            "SELECT owner_coordinates_json FROM source_coverage_proofs"
        ).fetchone()[0]
        assert proof == claim.scope.encoded


def test_inventory_refresh_and_history_preserve_authored_membership_attributes(
    tmp_path,
):
    old, claim, authorization, admission, _ = prepare(tmp_path)
    attributes = encode(
        {
            "label": "authored membership",
            "source": "synthetic",
            "evidence": "original association",
        }
    )
    updated = encode({"label": "explicitly updated membership"})
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        context.associate_source(
            old.source_registration_uuidv4, old.repositories[0], attributes
        )
        context.inventory(old)
        context.admit_inventory_history(old, claim)
        context.inventory(
            replace(old, observed_at_us=200, state="partial", terminal=False)
        )
        assert (
            context.db.execute(
                "SELECT attributes_json FROM source_repositories"
            ).fetchone()[0]
            == attributes
        )
        context.associate_source(
            old.source_registration_uuidv4, old.repositories[0], updated
        )
        context.admit_inventory_history(old, claim)
        assert (
            context.db.execute(
                "SELECT attributes_json FROM source_repositories"
            ).fetchone()[0]
            == updated
        )


def test_history_wrong_source_and_invalid_proof_roll_back_entire_unit(tmp_path):
    old, claim, authorization, admission, _ = prepare(tmp_path)
    wrong_scope = replace(
        old,
        scope_json=encode(
            {"coverage_kind": "repositories", "service_instance_uuidv4": str(uuid4())}
        ),
    )
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        with pytest.raises(ContextError, match="SOURCE_SERVICE"):
            context.admit_inventory_history(wrong_scope, claim)
        with pytest.raises(sqlite3.IntegrityError):
            context.admit_inventory_history(replace(old, terminal=False), claim)
        assert (
            context.db.execute(
                "SELECT count(*) FROM source_inventory_evidence"
            ).fetchone()[0]
            == 0
        )
        assert (
            context.db.execute("SELECT count(*) FROM source_repositories").fetchone()[0]
            == 0
        )
        assert (
            context.db.execute("SELECT count(*) FROM coverage_claims").fetchone()[0]
            == 0
        )


def test_history_needs_current_source_and_provenance_authority(tmp_path):
    old, claim, authorization, admission, policy = prepare(tmp_path)
    policy.denied = DependencySet(sources={old.source_registration_uuidv4})
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        with pytest.raises(AdmissionRefused):
            context.admit_inventory_history(old, claim)
    policy.denied = DependencySet()
    foreign = str(uuid4())
    changed = replace(
        old,
        provenance_json=encode(
            {
                "source": "synthetic",
                "evidence": "foreign",
                "source_registration_uuidv4": foreign,
            }
        ),
    )
    with Context.transaction(
        tmp_path, authorization=authorization, admission=admission
    ) as context:
        with pytest.raises(AdmissionRefused):
            context.admit_inventory_history(changed, claim)
        assert (
            context.db.execute(
                "SELECT count(*) FROM source_inventory_evidence"
            ).fetchone()[0]
            == 0
        )
