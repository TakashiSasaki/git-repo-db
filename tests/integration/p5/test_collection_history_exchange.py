"""Immutable Collection originals survive reverse delivery and current gaps."""

import json
import sqlite3
from dataclasses import replace

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.application.pr_assessment import PRQueryService
from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    AdmissionSelection,
    create_local_admission_service,
)
from repo_catalog.domain.p1_context import CoverageScope
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.production_context import CollectionObservation
from tests.integration.p5.conftest import init_catalog_stores
from tests.integration.p5.test_selected_collection_exchange import setup
from tests.support.context_admission import fixture_transaction


@pytest.mark.parametrize(
    "newer_terminal", [False, True], ids=["claim-only", "terminal"]
)
@pytest.mark.parametrize("reverse", [False, True], ids=["ordinary", "reversed"])
def test_original_collection_proof_survives_later_partial_in_both_delivery_orders(
    tmp_path, newer_terminal, reverse
):
    fixture, selection, key = setup(tmp_path / "sender")
    before = ExchangeService(fixture.path).export_package(selection=selection)
    original = before.context["collections"][0]
    observation = CollectionObservation(
        fixture.parent,
        "pr_files",
        key[4],
        original["scope_json"],
        600,
        "complete",
        tuple(fixture.files[:2]),
    )
    scope = CoverageScope.collection(fixture.parent, "pr_files", key[4], "pr_files")
    with fixture_transaction(fixture.path, fixture.grants) as context:
        if newer_terminal:
            context.collection(
                replace(
                    observation,
                    observed_at_us=700,
                    state="partial",
                    members=tuple(fixture.files[:1]),
                )
            )
        context.admit_coverage(CoverageClaim(scope, 700, "partial"))
        if newer_terminal:
            with pytest.raises(sqlite3.IntegrityError, match="superseded"):
                context.prove_collection(
                    CoverageClaim(scope, 600, "complete"),
                    observation,
                    required_scope_json=observation.scope_json,
                )
    after = ExchangeService(fixture.path).export_package(selection=selection)
    assert after.context["coverage_proofs"] == before.context["coverage_proofs"]
    target = tmp_path / "receiver"
    init_catalog_stores(
        target, repository_uuidv4=fixture.repository, stores=("context", "operational")
    )
    auth, admission, _ = create_local_admission_service(
        "exchange_import",
        grants=fixture.grants,
        selection=AdmissionSelection(all_selected=True),
    )
    receiver = ExchangeService(target, authorization=auth, admission=admission)
    for packet in (after, before) if reverse else (before, after):
        receiver.import_package(packet, new_request=True)
    assert receiver.import_package(before).idempotent_replay
    assert receiver.import_package(after).idempotent_replay
    result = PRQueryService(target, mode="context_only").get_pr_code_capture(
        fixture.parent, "pr_files", key[4]
    )
    assert result.state == "partial"
    assert result.page.total_count == (1 if newer_terminal else 2)
    with Context.snapshot(target) as context:
        assert context.coverage(scope).state == "partial"
        assert context.db.execute(
            "SELECT count(*) FROM coverage_proofs"
        ).fetchone() == (1,)
        assert context.db.execute(
            "SELECT observed_at_us,coverage_state FROM coverage_claims ORDER BY observed_at_us"
        ).fetchall() == [(600, "complete"), (700, "partial")]
    onward = ExchangeService(target).export_package(selection=selection)
    assert onward.context["coverage_proofs"] == before.context["coverage_proofs"]
    assert onward.context["collections"] == after.context["collections"]
    assert not (target / "p1-recovery-stop.json").exists()


def test_collection_history_still_requires_exact_owner_members_and_explicit_authority(
    tmp_path,
):
    fixture, selection, key = setup(tmp_path)
    package = ExchangeService(tmp_path).export_package(selection=selection)
    original = package.context["collections"][0]
    observation = CollectionObservation(
        fixture.parent,
        "pr_files",
        key[4],
        original["scope_json"],
        600,
        "complete",
        tuple(fixture.files[:2]),
    )
    forged = CoverageClaim(
        CoverageScope.collection(fixture.parent, "pr_files", key[4], "git"),
        600,
        "complete",
    )
    with fixture_transaction(tmp_path, fixture.grants) as context:
        before = context.db.execute("SELECT * FROM coverage_claims").fetchall()
        with pytest.raises(sqlite3.IntegrityError, match="owner mismatch"):
            context.admit_collection_history(observation, forged)
        assert context.db.execute("SELECT * FROM coverage_claims").fetchall() == before
        assert context.db.in_transaction
    with fixture_transaction(
        tmp_path,
        replace(
            fixture.grants, resources=fixture.grants.resources - {fixture.files[0]}
        ),
    ) as context:
        with pytest.raises(AdmissionRefused):
            context.admit_collection_history(
                observation,
                CoverageClaim(
                    CoverageScope.collection(
                        fixture.parent, "pr_files", key[4], "pr_files"
                    ),
                    600,
                    "complete",
                ),
            )
    assert json.loads(observation.scope_json)["expected_count"] == 2
    assert not (tmp_path / "p1-recovery-stop.json").exists()
