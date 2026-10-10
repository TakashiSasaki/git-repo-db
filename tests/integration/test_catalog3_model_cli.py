"""Public CLI workflows for explicit model admission and offline reanalysis."""

import json
import uuid
from types import SimpleNamespace

import pytest

from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.maintenance_service import MaintenanceService
from tests.support.cli import run
from tests.support.github_runtime import github_runtime as github_runtime
from tests.support.github_runtime import sync


@pytest.fixture
def catalog(tmp_path):
    state = tmp_path / "catalog"
    MaintenanceService(state).init("catalog-text-v1", 32 * 1024 * 1024, 0)
    with Store(state) as store:
        repository = str(uuid.uuid4())
        with store.transaction():
            store.execute(
                "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'synthetic','{}')",
                (repository,),
            )
        yield SimpleNamespace(state=state, store=store, repository=repository)
        assert not store.all("PRAGMA foreign_key_check")


def request(tmp_path, name, value):
    path = tmp_path / (name + ".json")
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_identity_cancellation_before_relation_cli_never_activates_edge(
    catalog, tmp_path
):
    other = str(uuid.uuid4())
    relation_uuid = str(uuid.uuid4())
    with catalog.store.transaction():
        catalog.store.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'other','{}')",
            (other,),
        )
    cancellation = {
        "cancellation_uuidv4": str(uuid.uuid4()),
        "relation_uuidv4": relation_uuid,
        "evidence_json": json.dumps({"fixture": "cancel first"}),
        "asserted_at_us": -1,
    }
    result = run(
        catalog.state,
        "identity",
        "cancellation",
        "--input",
        request(tmp_path, "cancel", cancellation),
        expected=3,
    )
    assert result["data"]["state"] == "staged"
    staged = run(catalog.state, "identity", "status")["data"]
    assert staged["identity_relation_staging"]
    relation = {
        "relation_uuidv4": relation_uuid,
        "entity_kind": "repository",
        "left_repository_uuidv4": catalog.repository,
        "right_repository_uuidv4": other,
        "left_service_instance_uuidv4": None,
        "right_service_instance_uuidv4": None,
        "evidence_json": json.dumps({"fixture": "assertion"}),
        "asserted_at_us": 0,
    }
    run(
        catalog.state,
        "identity",
        "relation",
        "--input",
        request(tmp_path, "relation", relation),
    )
    status = run(catalog.state, "identity", "status")["data"]
    assert (
        len(status["identity_relations"])
        == len(status["identity_relation_cancellations"])
        == 1
    )
    assert status["identity_relation_staging"] == []
    assert status["active_identity_relations"] == []
    assert status["repository_equivalence_closure"] == []


def test_source_configuration_rejects_secrets_then_saves_local_nonsecret_settings(
    catalog, tmp_path
):
    registration = str(uuid.uuid4())
    with catalog.store.transaction():
        catalog.store.execute(
            "INSERT INTO sources(source_id,source_registration_uuidv4,discovery_kind,name,settings) VALUES('received',?,'manual_git','local label',NULL)",
            (registration,),
        )
    rejected = run(
        catalog.state,
        "sources",
        "configure",
        "--source",
        "registration:" + registration,
        "--input",
        request(
            tmp_path,
            "secret",
            {"url": "file:///synthetic", "token": "fixture-not-a-secret"},
        ),
        expected=None,
    )
    assert rejected["error"]["code"] == "SOURCE_INVALID_SETTINGS"
    assert (
        catalog.store.one("SELECT settings FROM sources WHERE source_id='received'")[0]
        is None
    )
    configured = run(
        catalog.state,
        "sources",
        "configure",
        "--source",
        "registration:" + registration,
        "--input",
        request(tmp_path, "settings", {"url": "relative-synthetic-repository"}),
    )
    assert configured["data"]["source_id"] == "received"
    saved = catalog.store.one(
        "SELECT source_registration_uuidv4,name,settings FROM sources WHERE source_id='received'"
    )
    assert tuple(saved[:2]) == (registration, "local label")
    assert json.loads(saved["settings"])["url"].startswith("file:///")
    tables = {
        row[0]
        for row in catalog.store.all(
            "SELECT name FROM sqlite_schema WHERE type='table'"
        )
    }
    assert not tables.intersection({"source_input_observations", "fetch_occurrences"})


def test_cli_retires_http_reparse_without_mutation_or_remote_observation(
    github_runtime,
):
    store, repo, _, api = github_runtime
    sync(store, repo)
    before = list(store.connection.iterdump())
    requests = len(api.requests)
    rejected = run(
        store.path,
        "parser",
        "reparse",
        "http-response:" + str(uuid.uuid4()),
        expected=5,
    )
    assert rejected["status"] == "error"
    assert rejected["error"]["code"] == "PARSER_UNSUPPORTED_INPUT"
    assert "API response replay is retired" in rejected["error"]["message"]
    assert rejected["data"] is None
    assert list(store.connection.iterdump()) == before
    assert len(api.requests) == requests
    assert not store.all("PRAGMA foreign_key_check")


@pytest.mark.parametrize(
    "action", ["register", "verify", "trust", "select", "invalidate"]
)
def test_retired_profile_cli_routes_do_not_create_catalog(tmp_path, action):
    state = tmp_path / "absent-profile-catalog"
    result = run(state, "parser", action, "synthetic-retired-profile", expected=2)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert not state.exists()
