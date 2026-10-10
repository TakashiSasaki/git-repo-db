"""Acquisition plans are immutable, resumable and contain no secrets."""

import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.collection_service import CollectionService
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.models import CatalogError
from tests.support.sqlite_contracts import assert_absent_tables


@pytest.fixture
def state(tmp_path):
    path = tmp_path / "catalog"
    MaintenanceService(path).init("catalog-text-v1", 33554432, 0)
    return path


def add_manual(path, name="source"):
    return (
        MaintenanceService(path)
        .source_add("local-git", name=name, url="file:///synthetic/" + name + ".git")
        .data["source_id"]
    )


def test_discovery_resume_uses_frozen_source_set_and_settings(state, monkeypatch):
    first = add_manual(state)
    captured = []

    def pause(self, store, job, plan):
        captured.append(plan)
        JobService(store).update(job, "interrupted")
        return job

    monkeypatch.setattr(CollectionService, "_discover", pause)
    job = CollectionService(state).discover()
    with Store(state) as store:
        store.execute(
            "UPDATE sources SET settings=? WHERE source_id=?",
            ('{"url":"file:///replacement.git"}', first),
        )
    add_manual(state, "late-source")
    CollectionService(state).resume(job)
    assert captured[0] == captured[1]
    assert [src["source_id"] for src in captured[1]["sources"]] == [first]
    assert (
        json.loads(captured[1]["sources"][0]["settings"])["url"]
        == "file:///synthetic/source.git"
    )
    with Store(state) as store:
        assert (
            store.one("SELECT current_attempt FROM jobs WHERE job_id=?", (job,))[0] == 2
        )
        with pytest.raises(sqlite3.IntegrityError):
            store.execute("UPDATE jobs SET request='{}' WHERE job_id=?", (job,))


def test_missing_explicit_credentials_creates_no_job_or_remote_evidence(state):
    source = (
        MaintenanceService(state)
        .source_add(
            "github", owner="synthetic", token_env_var="MISSING_PLAN_TEST_TOKEN"
        )
        .data["source_id"]
    )
    with pytest.raises(CatalogError) as error:
        CollectionService(state).discover(source)
    assert error.value.code == "SOURCE_CREDENTIAL_UNAVAILABLE"
    with Store(state) as store:
        assert store.one("SELECT count(*) FROM jobs")[0] == 0
        assert_absent_tables(
            store.connection, "source_input_observations", "inventory_observations"
        )
        assert store.one("SELECT count(*) FROM source_inventory_assessments")[0] == 0
        assert store.one("SELECT count(*) FROM source_repositories")[0] == 0


def test_plan_saves_credential_reference_not_value(state, monkeypatch):
    monkeypatch.setenv("PLAN_TEST_TOKEN", "synthetic-secret-value")
    source = (
        MaintenanceService(state)
        .source_add("github", owner="synthetic", token_env_var="PLAN_TEST_TOKEN")
        .data["source_id"]
    )

    def pause(self, store, job, plan):
        JobService(store).update(job, "interrupted")
        return job

    monkeypatch.setattr(CollectionService, "_discover", pause)
    job = CollectionService(state).discover(source)
    with Store(state) as store:
        request = store.one("SELECT request FROM jobs WHERE job_id=?", (job,))[0]
        assert "PLAN_TEST_TOKEN" in request
        assert "synthetic-secret-value" not in request
        assert (
            json.loads(request)["sources"][0]["github_config"]["token_env_var"]
            == "PLAN_TEST_TOKEN"
        )


def test_manual_inventory_has_source_owned_current_roster_and_assessment(state):
    source = add_manual(state)
    response = CollectionService(state).discover(source)
    with Store(state) as store:
        row = store.one("SELECT * FROM source_inventory_assessments")
        assert row["source_id"] == source
        assert row["state"] == "complete" and row["terminal"] == 1
        association = store.one("SELECT * FROM source_repositories")
        assert association["source_id"] == source
        assert json.loads(row["members_json"]) == [association["repository_uuidv4"]]
        scope = json.loads(row["scope_json"])
        assert (
            scope["source_registration_uuidv4"]
            == store.one(
                "SELECT source_registration_uuidv4 FROM sources WHERE source_id=?",
                (source,),
            )[0]
        )
        assert (
            scope["kind"] == "manual_git"
            and scope["endpoint"] == "file:///synthetic/source.git"
        )
        assert (
            association["parser_module"]
            == row["parser_module"]
            == "repo_catalog.manual_source"
        )
        assert association["parser_version"] == row["parser_version"] == "1"
        assert association["name"] == "source"
        evidence = json.loads(association["field_evidence_json"])
        assert evidence['["name"]']["acquisition_scope"] == scope
        assert_absent_tables(
            store.connection,
            "source_input_observations",
            "inventory_observations",
            "parsed_results",
            "parsed_result_inputs",
            "current_inventory_observations",
            "repository_name_observations",
        )
        attempt = store.one(
            "SELECT a.state,a.checkpoint FROM job_attempts a WHERE job_id=?",
            (response.data["job_id"],),
        )
        assert attempt["state"] == "complete"
        assert (
            json.loads(attempt["checkpoint"])["result"]["source_outcomes"][0]["state"]
            == "complete"
        )
        assert store.all("PRAGMA foreign_key_check") == []


def test_bulk_zero_usable_sources_creates_no_job(state):
    with pytest.raises(CatalogError) as error:
        CollectionService(state).discover()
    assert error.value.code == "NO_USABLE_SOURCE"
    with Store(state) as store:
        assert store.one("SELECT count(*) FROM jobs")[0] == 0


@pytest.mark.parametrize(
    "settings",
    [
        {"api_settings": {"rest_base_url": "https://user:secret@example.invalid"}},
        {
            "clone_url_overrides": {
                "1": "https://example.invalid/repo.git?access_token=secret"
            }
        },
        {"api_settings": {"Authorization": "secret"}},
    ],
)
def test_secret_bearing_settings_rejected_before_plan_persistence(settings):
    from repo_catalog.application.job_plans import reject_secrets

    with pytest.raises(CatalogError):
        reject_secrets(settings)


def test_cancelled_discovery_attempt_is_interrupted(state):
    from repo_catalog.domain.models import CancellationToken

    add_manual(state)
    token = CancellationToken()
    token.cancelled = True
    with pytest.raises(CatalogError) as error:
        CollectionService(state, token).discover()
    assert error.value.code == "CANCELLED"
    with Store(state) as store:
        assert store.one("SELECT state FROM job_attempts")[0] == "interrupted"
        assert_absent_tables(store.connection, "inventory_observations")
        assert store.one("SELECT count(*) FROM source_inventory_assessments")[0] == 0


def test_bulk_mixed_sources_persist_partial_result_with_complete_attempt(state):
    add_manual(state)
    MaintenanceService(state).source_add(
        "github", owner="synthetic", token_env_var="MISSING_PLAN_TEST_TOKEN"
    )
    result = CollectionService(state).discover()
    assert result.status == "partial"
    with Store(state) as store:
        row = store.one(
            "SELECT j.request,a.state,a.checkpoint FROM jobs j JOIN job_attempts a ON a.job_id=j.job_id AND a.attempt=j.current_attempt"
        )
        assert row["state"] == "complete"
        assert len(json.loads(row["request"])["source_registration_uuids"]) == 2
        saved = json.loads(row["checkpoint"])["result"]
        assert saved["status"] == "partial"
        assert len(saved["skipped_sources"]) == 1
        assert_absent_tables(store.connection, "source_input_observations")
        assert store.one("SELECT count(*) FROM source_inventory_assessments")[0] == 1
        assert store.one("SELECT count(*) FROM source_repositories")[0] == 1


def test_credentials_lost_after_job_creation_complete_partial_without_evidence(
    state, monkeypatch
):
    monkeypatch.setenv("PLAN_TEST_TOKEN", "synthetic-secret-value")
    source = (
        MaintenanceService(state)
        .source_add("github", owner="synthetic", token_env_var="PLAN_TEST_TOKEN")
        .data["source_id"]
    )
    real = CollectionService._discover

    def lose(self, store, job, plan):
        monkeypatch.delenv("PLAN_TEST_TOKEN")
        return real(self, store, job, plan)

    monkeypatch.setattr(CollectionService, "_discover", lose)
    result = CollectionService(state).discover(source)
    assert result.status == "partial"
    with Store(state) as store:
        assert store.one("SELECT state FROM job_attempts")[0] == "complete"
        assert_absent_tables(
            store.connection, "source_input_observations", "inventory_observations"
        )
        assert store.one("SELECT count(*) FROM source_inventory_assessments")[0] == 0
        assert store.one("SELECT count(*) FROM source_repositories")[0] == 0


def test_explicit_configuration_reuses_source_registration_and_does_not_rewrite_job(
    state, tmp_path, monkeypatch
):
    from repo_catalog.application.source_service import configure_source

    source = add_manual(state)

    def pause(self, store, job, plan):
        JobService(store).update(job, "interrupted")
        return job

    monkeypatch.setattr(CollectionService, "_discover", pause)
    job = CollectionService(state).discover(source)
    settings = tmp_path / "settings.json"
    settings.write_text('{"url":"file:///changed.git"}')
    response = configure_source(state, source, settings)
    assert response.data["source_id"] == source
    with Store(state) as store:
        assert (
            json.loads(
                store.one("SELECT settings FROM sources WHERE source_id=?", (source,))[
                    0
                ]
            )["url"]
            == "file:///changed.git"
        )
        assert (
            "file:///changed.git"
            not in store.one("SELECT request FROM jobs WHERE job_id=?", (job,))[0]
        )
