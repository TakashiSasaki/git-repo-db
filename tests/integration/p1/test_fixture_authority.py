"""Finite fixture composition still exercises real admission and commit fences."""

import pytest

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.domain.context_admission import AdmissionRefused, DependencySet
from repo_catalog.domain.p1_context import ResourceKey
from tests.support.authorized_context import FixtureContextStore

SERVICE = "22222222-2222-4222-8222-222222222222"
FOREIGN_SERVICE = "33333333-3333-4333-8333-333333333333"
REPO = "44444444-4444-4444-8444-444444444444"
KEY = ResourceKey.from_native(SERVICE, "issue", "authorized")
OUTSIDE = ResourceKey.from_native(SERVICE, "issue", "outside")
FOREIGN = ResourceKey.from_native(FOREIGN_SERVICE, "issue", "foreign")


@pytest.fixture
def fixture_store(tmp_path):
    path = tmp_path / "context.sqlite3"
    p1_schema.initialize(path, "context", REPO, SERVICE)
    db = p1_schema.connect(path, "context")
    for service in (SERVICE, FOREIGN_SERVICE):
        db.execute("INSERT INTO providers VALUES(?,'fixture','{}')", (service,))
    store = FixtureContextStore(
        db,
        DependencySet(resources={KEY, FOREIGN}, provider_registrations={SERVICE}),
    )
    try:
        yield db, store
    finally:
        store.close()
        db.close()


@pytest.mark.parametrize("dimension", ["resource", "repository", "provider"])
def test_finite_fixture_never_expands_authority_after_refusal(fixture_store, dimension):
    db, store = fixture_store
    grants = store.policy.grants
    with pytest.raises(AdmissionRefused, match="PERMISSION_DENIED"):
        if dimension == "resource":
            store.resource(OUTSIDE)
        elif dimension == "repository":
            store.resource(KEY, REPO)
        else:
            store.resource(FOREIGN)
    assert store.policy.grants is grants
    assert not db.execute("SELECT 1 FROM resources").fetchall()
    assert store.policy.active == 0
    assert not db.in_transaction


def test_fixture_transaction_propagates_revoke_after_insert_and_rolls_back(
    fixture_store,
):
    db, store = fixture_store
    inserted = []

    def revoke():
        inserted.append(db.execute("SELECT count(*) FROM resources").fetchone()[0])
        store.policy.revision += 1
        return 0

    db.create_function("fixture_revoke", 0, revoke)
    # Instrument only the verified disposable fixture; retain the production
    # schema during transaction entry, then install the actual failure trigger.
    with pytest.raises(AdmissionRefused, match="PERMISSION_DENIED"):
        with store.transaction():
            db.execute(
                "CREATE TEMP TRIGGER fixture_revoke AFTER INSERT ON resources "
                "BEGIN SELECT fixture_revoke(); END"
            )
            store.resource(KEY)
    assert inserted == [1]
    assert not db.execute("SELECT 1 FROM resources").fetchall()
    assert store.policy.active == 0
    assert not db.in_transaction


def test_fixture_never_adopts_caller_transaction(fixture_store):
    db, store = fixture_store
    db.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(AdmissionRefused, match="ADMISSION_TRANSACTION_REQUIRED"):
            store.resource(KEY)
        assert db.in_transaction
        assert not db.execute("SELECT 1 FROM resources").fetchall()
    finally:
        db.rollback()


def test_expired_fixture_cannot_issue_another_invocation(fixture_store):
    db, store = fixture_store
    store.close()
    with pytest.raises(AdmissionRefused, match="PERMISSION_DENIED"):
        store.resource(KEY)
    assert not db.execute("SELECT 1 FROM resources").fetchall()
    assert not db.in_transaction
