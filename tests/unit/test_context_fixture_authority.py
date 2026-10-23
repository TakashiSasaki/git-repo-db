"""Finite legacy-fixture authority never grants an unlisted caller dependency."""

import pytest

from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import AdmissionRefused, DependencySet
from tests.support.context_admission import (
    fixture_context,
    fixture_service,
    fixture_transaction,
)

SERVICE = "550e8400-e29b-41d4-a716-446655440000"
OTHER = "650e8400-e29b-41d4-a716-446655440000"
REPO = "750e8400-e29b-41d4-a716-446655440000"
INSTANCE = "850e8400-e29b-41d4-a716-446655440000"


def test_facade_fixture_grants_are_finite_and_no_product_default_is_installed(tmp_path):
    initialize(tmp_path / "context.sqlite3", "context", REPO, INSTANCE)
    grants = DependencySet(provider_registrations={SERVICE})
    with fixture_transaction(tmp_path, grants) as context:
        context.provider(SERVICE, "github")
        before = context.db.execute("SELECT * FROM providers").fetchall()
        with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
            context.provider(OTHER, "github")
        assert context.db.execute("SELECT * FROM providers").fetchall() == before
    with Context.transaction(tmp_path) as context:
        with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
            context.provider(SERVICE, "github")


def test_facade_fixture_refuses_foreign_issued_context_before_foreign_policy(tmp_path):
    initialize(tmp_path / "context.sqlite3", "context", REPO, INSTANCE)
    grants = DependencySet(provider_registrations={SERVICE})
    foreign_service, foreign_policy = fixture_service(grants)
    foreign = fixture_context(foreign_service)
    with fixture_transaction(tmp_path, grants) as context:
        with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
            context.provider(SERVICE, "github", admission=foreign)
        assert not context.db.execute("SELECT * FROM providers").fetchall()
    assert foreign_policy.calls == []
