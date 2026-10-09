"""Portable equivalence assertions never merge data and support late cancellations."""

import json
import uuid

import pytest

from repo_catalog.adapters.sqlite.identity_relations import IdentityRelations
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.collection_service import select_repositories
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.repository_identity import observe_name
from repo_catalog.domain.models import CatalogError


@pytest.fixture
def catalog(tmp_path):
    MaintenanceService(tmp_path).init("catalog-text-v1", 33554432, 0)
    with Store(tmp_path) as store:
        ids = [str(uuid.uuid4()) for _ in range(3)]
        for i, ident in enumerate(ids):
            store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,?,'{}')",
                (ident, f"initial-{i}"),
            )
        yield store, ids
        assert not store.all("PRAGMA foreign_key_check")


def relation(a, b):
    return dict(
        relation_uuidv4=str(uuid.uuid4()),
        entity_kind="repository",
        left_repository_uuidv4=a,
        right_repository_uuidv4=b,
        left_service_instance_uuidv4=None,
        right_service_instance_uuidv4=None,
        evidence_json=json.dumps({"kind": "explicit-user-assertion"}),
        asserted_at_us=0,
    )


def test_transitive_equivalence_retains_independent_repo_rows(catalog):
    store, (a, b, c) = catalog
    model = IdentityRelations(store.connection)
    assert model.admit("relation", relation(a, b)) == "accepted"
    assert model.admit("relation", relation(b, c)) == "accepted"
    assert store.one(
        "SELECT 1 FROM repository_equivalence_closure WHERE repository_uuidv4=? AND equivalent_repository_uuidv4=?",
        (a, c),
    )
    assert store.one("SELECT count(*) FROM repositories")[0] == 3
    assert store.one("SELECT count(*) FROM identity_relations")[0] == 2


def test_cancellation_first_is_promoted_atomically_without_activation(catalog):
    store, (a, b, _) = catalog
    model = IdentityRelations(store.connection)
    record = relation(a, b)
    cancellation = dict(
        cancellation_uuidv4=str(uuid.uuid4()),
        relation_uuidv4=record["relation_uuidv4"],
        evidence_json="{}",
        asserted_at_us=-1,
    )
    assert model.admit("cancellation", cancellation) == "staged"
    assert model.admit("relation", record) == "accepted"
    assert store.one("SELECT count(*) FROM active_identity_relations")[0] == 0
    assert store.one("SELECT count(*) FROM identity_relation_cancellations")[0] == 1
    assert store.one("SELECT count(*) FROM identity_relation_staging")[0] == 0
    assert model.admit("relation", record) == "duplicate"
    assert model.admit("cancellation", cancellation) == "duplicate"


def test_same_uuid_different_assertion_is_staged_and_not_a_winner(catalog):
    store, (a, b, c) = catalog
    model = IdentityRelations(store.connection)
    record = relation(a, b)
    model.admit("relation", record)
    assert (
        model.admit("relation", {**record, "right_repository_uuidv4": c}) == "conflict"
    )
    assert store.one("SELECT count(*) FROM active_identity_relations")[0] == 0
    assert store.one("SELECT right_repository_uuidv4 FROM identity_relations")[0] == b


def test_names_keep_independent_observations_and_ambiguous_resolution(catalog):
    store, (a, b, _) = catalog
    first = observe_name(store, a, "historical", 0)
    second = observe_name(store, a, "historical", 0)
    assert first != second
    assert store.one("SELECT count(*) FROM repository_observed_names")[0] == 1
    assert select_repositories(store, ("historical",))[0]["repository_uuidv4"] == a
    observe_name(store, b, "historical", 1)
    with pytest.raises(CatalogError, match="Ambiguous"):
        select_repositories(store, ("historical",))
