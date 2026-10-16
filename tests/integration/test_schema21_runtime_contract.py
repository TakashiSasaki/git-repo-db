"""Public runtime execution must not weaken the physical three-store boundary."""

import sqlite3

import pytest

from repo_catalog.adapters.github.persistence import ApiFacts
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.application.query_service import QueryService
from repo_catalog.domain.models import CatalogError
from tests.support.github_runtime import github_runtime as github_runtime


def test_completed_collection_survives_operational_loss_without_shadow_state(
    github_runtime,
):
    store, repo, _, _ = github_runtime
    job = JobService(store).create("sync", {"kind": "pr"})
    facts = ApiFacts(store, store.config["github"])
    with store.transaction():
        collection = facts.begin(repo, None, "pr-list", job, "synthetic:empty")
        facts.page(collection, 100, None, [])
        facts.finish(collection)
    JobService(store).update(job, "complete")
    ident = collection["fetch_collection_id"]
    assert (
        store.operational.one(
            "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
            (ident,),
        )[0]
        == "complete"
    )
    assert (
        store.one(
            "SELECT asserted_state FROM completion_markers WHERE fetch_collection_id=?",
            (ident,),
        )[0]
        == "complete"
    )
    for connection in (store, store.operational):
        assert [row[1] for row in connection.all("PRAGMA database_list")] == ["main"]
    for table in ("jobs", "job_attempts", "collection_progress", "index_generations"):
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            store.one(f"SELECT * FROM {table}")

    # Only the disposable database is removed. Durable terminal evidence and
    # the Core revision stay identical; ordinary reads must not recreate stores.
    revision = store.revision()
    store.operational.close()
    store._operational_store = None
    (store.path / "operational.sqlite3").unlink()
    with Store(store.path, readonly=True) as reader:
        assert reader.revision() == revision
        assert (
            reader.one(
                "SELECT asserted_state FROM completion_markers WHERE fetch_collection_id=?",
                (ident,),
            )[0]
            == "complete"
        )
    assert QueryService(store.path).query("jobs list").data["items"] == []
    assert not (store.path / "operational.sqlite3").exists()
    assert not (store.path / "search.sqlite3").exists()

    # Losing execution context refuses the old job, while a deliberate new job
    # can reuse the real Core terminal evidence (not an Operational success flag).
    with pytest.raises(CatalogError) as missing:
        JobService(store).resume(job)
    assert missing.value.code == "NOT_FOUND"
    new_job = JobService(store).create("sync", {"kind": "pr"})
    reused = facts.begin(repo, None, "pr-list", new_job, "synthetic:empty", reuse=True)
    assert reused["fetch_collection_id"] == ident
    assert reused["state"] == "complete"
    assert (
        store.operational.one(
            "SELECT job_id FROM collection_progress WHERE fetch_collection_id=?",
            (ident,),
        )[0]
        == new_job
    )
    assert store.revision() == revision


def test_operational_complete_cannot_certify_rolled_back_core_collection(
    github_runtime,
):
    store, repo, _, _ = github_runtime
    job = JobService(store).create("sync", {"kind": "pr"})
    facts = ApiFacts(store, store.config["github"])
    with pytest.raises(RuntimeError, match="Core commit interrupted"):
        with store.transaction():
            abandoned = facts.begin(repo, None, "pr-list", job, "synthetic:rollback")
            facts.page(abandoned, 100, None, [])
            facts.finish(abandoned)
            raise RuntimeError("Core commit interrupted")
    ident = abandoned["fetch_collection_id"]
    assert (
        store.operational.one(
            "SELECT state FROM collection_progress WHERE fetch_collection_id=?",
            (ident,),
        )[0]
        == "complete"
    )
    assert not store.one(
        "SELECT 1 FROM completion_markers WHERE fetch_collection_id=?", (ident,)
    )
    with store.transaction():
        fresh = facts.begin(
            repo, None, "pr-list", job, "synthetic:rollback", reuse=True
        )
    assert fresh["fetch_collection_id"] != ident
    assert fresh["cursor"] is None
    assert fresh["state"] == "running"
