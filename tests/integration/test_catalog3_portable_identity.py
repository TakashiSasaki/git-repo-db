"""Portable identity and local selector contracts (D12, CAS-55–66)."""

import json
import sqlite3
import uuid
from types import SimpleNamespace

import pytest

from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application import repository_identity as identity
from repo_catalog.application.collection_service import CollectionService
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.domain.models import CatalogError
from tests.support.sqlite_contracts import assert_absent_tables


@pytest.fixture
def store(tmp_path):
    state = tmp_path / "state"
    MaintenanceService(state).init("catalog-text-v1", 32 * 1024 * 1024, 0)
    with Store(state) as value:
        yield value
        assert not value.all("PRAGMA foreign_key_check")
        assert value.one("PRAGMA integrity_check")[0] == "ok"


def add_source(store, local_id, registration=None, name="same name"):
    registration = registration or str(uuid.uuid4())
    store.execute(
        "INSERT INTO sources(source_id,source_registration_uuidv4,discovery_kind,name,settings) "
        "VALUES(?,?,'manual_git',?,NULL)",
        (local_id, registration, name),
    )
    return registration


def test_same_named_services_remain_separate_and_require_uuid(store):
    first = identity.add_instance(store, "git", "same")
    second = identity.add_instance(store, "git", "same")
    assert first != second
    assert identity.instance(store, first)["service_instance_uuidv4"] == first
    assert identity.instance(store, second)["service_instance_uuidv4"] == second
    with pytest.raises(CatalogError, match="ambiguous"):
        identity.instance(store, "same")


def test_service_uuid_selector_is_not_shadowed_by_a_display_name(store):
    first = identity.add_instance(store, "git", "named")
    identity.add_instance(store, "git", first)
    assert identity.instance(store, first)["service_instance_uuidv4"] == first


def test_ambiguous_implicit_github_instance_is_rejected(store):
    first = identity.default_github_instance(store)
    assert identity.default_github_instance(store) == first
    identity.add_instance(store, "github", "github.com")
    with pytest.raises(CatalogError, match="Ambiguous"):
        identity.default_github_instance(store)


def test_source_names_are_not_selectors_and_id_kinds_can_be_explicit(store):
    registration = add_source(store, "local-first")
    add_source(store, "local-second")
    assert identity.source(store, registration)["source_id"] == "local-first"
    assert (
        identity.source(store, "local:local-first")["source_registration_uuidv4"]
        == registration
    )
    assert (
        identity.source(store, "registration:" + registration)["source_id"]
        == "local-first"
    )
    with pytest.raises(CatalogError):
        identity.source(store, "same name")


def test_cross_kind_source_id_collision_requires_explicit_selector(store):
    registration = add_source(store, "first")
    add_source(store, registration)
    with pytest.raises(CatalogError):
        identity.source(store, registration)
    assert (
        identity.source(store, "registration:" + registration)["source_id"] == "first"
    )
    assert identity.source(store, "local:" + registration)["source_id"] == registration


@pytest.mark.parametrize(
    "column,value",
    [
        ("source_registration_uuidv4", "00000000-0000-4000-8000-000000000001"),
        ("discovery_kind", "github_inventory"),
        ("service_instance_uuidv4", "00000000-0000-4000-8000-000000000101"),
    ],
)
def test_source_identity_is_immutable(store, column, value):
    add_source(store, "first")
    with pytest.raises(sqlite3.IntegrityError):
        store.execute(
            f"UPDATE sources SET {column}=? WHERE source_id='first'", (value,)
        )


@pytest.mark.parametrize(
    "registration", ["not-a-uuid", str(uuid.uuid5(uuid.NAMESPACE_DNS, "bad")), None]
)
def test_source_registration_requires_uuidv4(store, registration):
    with pytest.raises(sqlite3.IntegrityError):
        store.execute(
            "INSERT INTO sources(source_id,source_registration_uuidv4,discovery_kind,name,settings) "
            "VALUES('first',?,'manual_git','name',NULL)",
            (registration,),
        )


def test_source_operational_settings_allow_null_but_not_invalid_json(store):
    add_source(store, "first")
    assert identity.source(store, "first")["settings"] is None
    for value in ("[]", "false", "invalid"):
        with pytest.raises(sqlite3.IntegrityError):
            store.execute("UPDATE sources SET settings=?", (value,))
    store.execute("UPDATE sources SET name='local name',settings='{}'")
    assert identity.source(store, "first")["name"] == "local name"


def test_repository_key_name_is_used_by_all_ordinary_foreign_keys(store):
    assert "repository_uuidv4" in {
        r[1] for r in store.all("PRAGMA table_info(repositories)")
    }
    for (table,) in store.all("SELECT name FROM sqlite_schema WHERE type='table'"):
        assert "repository_id" not in {
            r[1] for r in store.all(f'PRAGMA table_info("{table}")')
        }


@pytest.mark.parametrize("selector", [None, "first"])
def test_no_usable_source_rejects_before_job_and_observation(store, selector):
    add_source(store, "first")
    with pytest.raises(CatalogError) as error:
        CollectionService(store.path).discover(selector)
    assert error.value.code == (
        "NO_USABLE_SOURCE" if selector is None else "SOURCE_UNCONFIGURED"
    )
    assert store.one("SELECT count(*) FROM jobs")[0] == 0
    assert_absent_tables(store.connection, "inventory_observations")
    assert store.one("SELECT count(*) FROM source_inventory_assessments")[0] == 0
    assert store.one("SELECT count(*) FROM source_repositories")[0] == 0
    assert store.one("SELECT count(*) FROM coverage_claims")[0] == 0


def test_batch_skip_retains_diagnostic_without_remote_observation(store):
    missing = add_source(store, "missing")
    configured = add_source(store, "configured")
    store.execute(
        "UPDATE sources SET settings=? WHERE source_id='configured'",
        ('{"url":"file:///synthetic-only"}',),
    )
    result = CollectionService(store.path).discover()
    assert result.status == "partial"
    assert result.data["skipped_sources"] == [
        {"source_registration_uuidv4": missing, "reason": "SOURCE_UNCONFIGURED"}
    ]
    assert_absent_tables(store.connection, "inventory_observations")
    assessments = store.all("SELECT * FROM source_inventory_assessments")
    assert len(assessments) == 1
    assessment = assessments[0]
    assert assessment["source_id"] == "configured"
    assert assessment["state"] == "complete" and assessment["terminal"] == 1
    members = store.all("SELECT source_id,repository_uuidv4 FROM source_repositories")
    assert len(members) == 1 and members[0]["source_id"] == "configured"
    assert json.loads(assessment["members_json"]) == [members[0]["repository_uuidv4"]]
    attempt = store.one(
        "SELECT state,checkpoint FROM job_attempts WHERE job_id=?",
        (result.data["job_id"],),
    )
    assert attempt["state"] == "complete"
    assert json.loads(attempt["checkpoint"])["result"]["status"] == "partial"
    assert (
        json.loads(attempt["checkpoint"])["result"]["skipped_sources"]
        == result.data["skipped_sources"]
    )
    assert identity.source(store, configured)["source_id"] == "configured"
    assert store.one("SELECT count(*) FROM coverage_claims")[0] == 0
    selected = QueryService(store.path).query(
        "repos list", {"source": "registration:" + configured}
    )
    assert len(selected.data["items"]) == 1
    assert identity.source(store, configured)["source_id"] == "configured"


def test_source_registration_survives_backup_restore(store, tmp_path):
    registration = add_source(store, "local-handle")
    output = tmp_path / "copy.sqlite3"
    MaintenanceService(store.path).database("backup", SimpleNamespace(output=output))
    restored = tmp_path / "restored"
    MaintenanceService(restored).restore(output)
    with Store(restored, readonly=True) as copy:
        assert dict(identity.source(copy, registration)) == dict(
            identity.source(store, registration)
        )
        assert copy.revision()["db_instance_id"] != store.revision()["db_instance_id"]


def test_job_result_and_terminal_state_commit_atomically(store):
    service = JobService(store)
    job = service.create("discover", {})
    store.execute(
        "CREATE TRIGGER reject_result BEFORE UPDATE OF checkpoint ON job_attempts BEGIN SELECT RAISE(ABORT,'synthetic write failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="synthetic write failure"):
        service.update(job, "complete", result={"status": "partial"})
    assert tuple(
        store.one("SELECT state,checkpoint FROM job_attempts WHERE job_id=?", (job,))
    ) == ("running", "{}")
