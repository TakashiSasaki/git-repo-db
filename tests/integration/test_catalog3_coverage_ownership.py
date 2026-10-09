"""Coverage ownership remains explicit when repository and PR IDs overlap."""

import sqlite3

import pytest

from repo_catalog.adapters.sqlite.coverage import current_coverages
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.repository_identity import add_instance, bind
from repo_catalog.domain.models import CatalogError


@pytest.fixture
def store(tmp_path):
    state = tmp_path / "catalog"
    MaintenanceService(state).init("catalog-text-v1", 67_108_864, 0)
    with Store(state) as saved:
        with saved.transaction():
            namespace = add_instance(saved, "github", "synthetic")
            for repository_uuidv4 in ("repo", "shared-id"):
                saved.execute(
                    "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,?,'{}')",
                    (repository_uuidv4, repository_uuidv4),
                )
            bind(saved, "repo", namespace, "1")
            binding = saved.one(
                "SELECT repository_binding_id FROM repository_bindings WHERE repository_uuidv4='repo'"
            )[0]
            saved.execute(
                "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES('shared-id','repo',?,'pull_request',1)",
                (binding,),
            )
        yield saved
        assert not saved.all("PRAGMA foreign_key_check")
        assert saved.one("PRAGMA integrity_check")[0] == "ok"


def test_repository_and_pr_claims_with_equal_ids_keep_their_explicit_owners(store):
    repository_claim = store.coverage("shared-id", "git", "complete", observed_at_us=1)
    pr_claim = store.coverage(
        "repo", "git", "partial", change_request_id="shared-id", observed_at_us=1
    )
    repository_scope = current_coverages(store.connection, "shared-id")[0]
    pr_scope = current_coverages(store.connection, "repo")[0]
    assert repository_scope["repository_uuidv4"] == "shared-id"
    assert repository_scope["change_request_id"] is None
    assert repository_scope["coverage_state"] == "complete"
    assert repository_scope["claims"][0]["coverage_claim_id"] == repository_claim
    assert pr_scope["repository_uuidv4"] == "repo"
    assert pr_scope["change_request_id"] == "shared-id"
    assert pr_scope["coverage_state"] == "partial"
    assert pr_scope["claims"][0]["coverage_claim_id"] == pr_claim


@pytest.mark.parametrize(
    "repository_uuidv4,change_request_id",
    [
        ("shared-id", "shared-id"),
        ("repo", "absent-pr"),
        ("absent-repository", "shared-id"),
        ("absent-repository", None),
    ],
)
def test_unknown_or_cross_repository_coverage_owner_is_rejected_before_writing(
    store, repository_uuidv4, change_request_id
):
    before = store.connection.total_changes
    with store.transaction():
        with pytest.raises(CatalogError) as error:
            store.coverage(
                repository_uuidv4,
                "git",
                "complete",
                change_request_id=change_request_id,
                observed_at_us=1,
            )
        assert error.value.code == "INVALID_COVERAGE_OWNER"
        assert store.connection.total_changes == before
        assert not store.one("SELECT 1 FROM coverage_scopes")
        assert not store.one("SELECT 1 FROM coverage_claims")
        assert store.connection.in_transaction


def test_explicit_owner_admission_preserves_original_details_and_caller_rollback(store):
    original = '{ "observed": "first", "spacing": true }'
    with store.transaction():
        first = store.coverage(
            "repo",
            "git",
            "complete",
            original,
            change_request_id="shared-id",
            observed_at_us=10,
        )
        before = store.connection.total_changes
        assert (
            store.coverage(
                "repo",
                "git",
                "complete",
                '{"ignored":true}',
                change_request_id="shared-id",
                observed_at_us=10,
            )
            is None
        )
        assert (
            store.coverage(
                "repo",
                "git",
                "partial",
                '{"stale":true}',
                change_request_id="shared-id",
                observed_at_us=9,
            )
            is None
        )
        assert store.connection.total_changes == before
        assert (
            store.one(
                "SELECT details_json FROM coverage_claims WHERE coverage_claim_id=?",
                (first,),
            )[0]
            == original
        )
    before_rollback = [tuple(row) for row in store.all("SELECT * FROM coverage_claims")]
    with pytest.raises(RuntimeError, match="rollback"):
        with store.transaction():
            store.coverage("shared-id", "git", "complete", observed_at_us=10)
            store.coverage(
                "repo",
                "git",
                "partial",
                change_request_id="shared-id",
                observed_at_us=10,
            )
            raise RuntimeError("rollback")
    assert [
        tuple(row) for row in store.all("SELECT * FROM coverage_claims")
    ] == before_rollback
    assert current_coverages(store.connection, "shared-id") == []


def test_store_accepts_auto_id_after_negative_id_and_keeps_replace_protection(store):
    assert store.one("PRAGMA recursive_triggers")[0] == 1
    with store.transaction():
        store.execute(
            "INSERT INTO coverage_scopes(coverage_scope_id,repository_uuidv4,kind) VALUES('scope','repo','git')"
        )
        original = '{ "source": "explicit negative ID" }'
        store.execute(
            "INSERT INTO coverage_claims(coverage_claim_id,coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES(-1,'scope','complete',1,?)",
            (original,),
        )
        second = store.coverage("repo", "git", "partial", observed_at_us=1)
        assert second is not None and second != -1
        with pytest.raises(sqlite3.IntegrityError):
            store.execute(
                "INSERT OR REPLACE INTO coverage_claims(coverage_claim_id,coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES(-1,'scope','unknown',2,'{}')"
            )
        assert (
            store.one(
                "SELECT details_json FROM coverage_claims WHERE coverage_claim_id=-1"
            )[0]
            == original
        )
    assert (
        current_coverages(store.connection, "repo")[0]["coverage_state"] == "conflict"
    )
