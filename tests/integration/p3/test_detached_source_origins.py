"""Origin references stay detached; Source-owned units retain real local FKs."""

import sqlite3

import pytest

from repo_catalog.domain.context_admission import AdmissionRefused
from repo_catalog.domain.p1_context import CoverageScope, FieldClock, canonical
from repo_catalog.domain.production_context import ContextError, SourceInventory
from tests.integration.p3.test_production_context import (
    KEY,
    REPO,
    SERVICE,
    SOURCE,
    directory,
    production_grants,
)
from tests.support.context_admission import fixture_transaction

__all__ = ["directory"]


def test_detached_origin_does_not_supply_registration_for_source_owned_operations(
    directory,
):
    original = canonical(
        {
            "source": "reported-peer",
            "evidence": {
                "source_registration_uuidv4": SOURCE,
                "service_instance_uuidv4": SERVICE,
            },
        }
    )
    inventory = SourceInventory(
        SOURCE,
        canonical({"service_instance_uuidv4": SERVICE}),
        10,
        "partial",
        True,
        (),
        original,
    )
    with fixture_transaction(directory, production_grants()) as context:
        context.provider(SERVICE, "github")
        context.repository(REPO)
        context.resource(KEY)
        context.admit_text(
            KEY, "detached origin", FieldClock("provider", None), original, 10
        )
        candidates = context.candidates(KEY, "text_body_sha256")
        assert context.db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        with pytest.raises(AdmissionRefused, match="^MISSING_DEPENDENCY$"):
            context.scope(
                CoverageScope.source_inventory(
                    SOURCE, inventory.scope_json, "repositories"
                )
            )
        with pytest.raises(ContextError, match="SOURCE_UNAVAILABLE"):
            context.inventory(inventory)
        with pytest.raises(sqlite3.IntegrityError):
            context.associate_source(SOURCE, REPO)
        assert context.db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
        assert (
            context.db.execute("SELECT count(*) FROM source_repositories").fetchone()[0]
            == 0
        )
        assert (
            context.db.execute(
                "SELECT count(*) FROM source_inventory_evidence"
            ).fetchone()[0]
            == 0
        )
        assert context.candidates(KEY, "text_body_sha256") == candidates
        # A real explicitly authorized registration enables Source-owned units;
        # the original report's producer/time is never rewritten by its arrival.
        context.source(SOURCE, SERVICE)
        context.associate_source(SOURCE, REPO)
        context.inventory(inventory)
        context.scope(
            CoverageScope.source_inventory(SOURCE, inventory.scope_json, "repositories")
        )
        assert context.source_repositories(SOURCE) == (REPO,)
        assert context.candidates(KEY, "text_body_sha256") == candidates
    assert not (directory / "p1-recovery-stop.json").exists()
