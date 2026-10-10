"""Public CLI workflows for explicit model admission and offline reanalysis."""

import json
import uuid

import pytest

from tests.integration.test_catalog3_profile_queries import catalog as catalog
from tests.support.cli import run
from tests.support.github_runtime import github_runtime as github_runtime
from tests.support.github_runtime import sync


def request(tmp_path, name, value):
    path = tmp_path / (name + ".json")
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_profile_registration_selection_trust_and_invalidation_cli(catalog, tmp_path):
    definition = {
        "implementation": {"fixture": "second-cli-parser"},
        "settings": {},
        "output_schema": {"fixture": 1},
        "capabilities": [
            {"owner_kind": "repository", "fact_kind": kind}
            for kind in ("change-request", "issue-comment")
        ],
    }
    registered = run(
        catalog.state,
        "parser",
        "register",
        "--input",
        request(tmp_path, "profile", {"definition": definition}),
    )
    profile = registered["data"]["result"]
    verified = run(
        catalog.state,
        "parser",
        "verify",
        "--input",
        request(
            tmp_path,
            "verification",
            {
                "profile_uuid": profile,
                "criteria": {"suite": "synthetic-cli"},
                "evidence": {
                    "definition": definition,
                    "capabilities": [
                        {**item, "outcome": "passed", "checks": ["fixture"]}
                        for item in definition["capabilities"]
                    ],
                },
            },
        ),
    )
    verification = verified["data"]["result"]
    run(catalog.state, "parser", "trust", verification)
    selected = run(
        catalog.state,
        "parser",
        "select-profile",
        "--input",
        request(
            tmp_path,
            "select",
            {
                "profile_uuid": profile,
                "verification_uuid": verification,
                "repository_uuidv4": catalog.repository,
                "fact_kind": "issue-comment",
            },
        ),
    )
    with catalog.store.transaction():
        observation = catalog.observe("cli selected", profile=profile, select=False)
    run(
        catalog.state,
        "parser",
        "select-fact",
        "--input",
        request(
            tmp_path,
            "fact",
            {
                "result_uuid": observation["result"],
                "fact_kind": "issue-comment",
                "change_request_id": catalog.request,
                "kind": "issue-comment",
                "provider_change_request_document_id": "1",
            },
        ),
    )
    assert [row["body"] for row in catalog.documents().data["items"]] == [
        "cli selected"
    ]
    status = run(catalog.state, "parser", "status")["data"]
    assert any(
        row["selection_decision_uuidv4"] == selected["data"]["result"]
        for row in status["active_parser_profile_selections"]
    )
    run(catalog.state, "parser", "trust", verification, "--revoke")
    assert catalog.documents().data["items"] == []
    run(catalog.state, "parser", "trust", verification)
    assert catalog.documents().data["items"]
    run(
        catalog.state,
        "parser",
        "invalidate",
        verification,
        "--reason",
        "fixture invalidation",
    )
    assert catalog.documents().data["items"] == []
    status = run(catalog.state, "parser", "status")["data"]
    assert any(
        row["parser_profile_verification_uuidv4"] == verification
        for row in status["parser_profile_verification_invalidations"]
    )


def test_admitted_late_dependency_is_partial_then_promotes_without_new_ids(
    catalog, tmp_path
):
    initial = dict(
        catalog.store.one(
            "SELECT * FROM parser_profile_selection_decisions WHERE fact_kind='issue-comment'"
        )
    )
    dependency = {
        **initial,
        "selection_decision_uuidv4": str(uuid.uuid4()),
        "predecessor_manifest_json": json.dumps([initial["selection_decision_uuidv4"]]),
    }
    later = {
        **initial,
        "selection_decision_uuidv4": str(uuid.uuid4()),
        "predecessor_manifest_json": json.dumps(
            [dependency["selection_decision_uuidv4"]]
        ),
    }
    staged = run(
        catalog.state,
        "parser",
        "admit-decision",
        "--input",
        request(
            tmp_path,
            "later",
            {
                "decision_kind": "profile",
                **later,
            },
        ),
        expected=3,
    )
    assert staged["data"]["result"] == "staged"
    assert staged["coverage"]["complete_for_requested_scope"] is False
    status = run(catalog.state, "parser", "status")["data"]
    assert (
        status["parser_profile_selection_staging"][0]["selection_decision_uuidv4"]
        == later["selection_decision_uuidv4"]
    )
    run(
        catalog.state,
        "parser",
        "admit-decision",
        "--input",
        request(
            tmp_path,
            "dependency",
            {
                "decision_kind": "profile",
                **dependency,
            },
        ),
    )
    status = run(catalog.state, "parser", "status")["data"]
    assert status["parser_profile_selection_staging"] == []
    assert any(
        row["selection_decision_uuidv4"] == later["selection_decision_uuidv4"]
        for row in status["active_parser_profile_selections"]
    )


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
    assert catalog.store.one("SELECT count(*) FROM source_input_observations")[0] == 0
    assert catalog.store.one("SELECT count(*) FROM fetch_occurrences")[0] == 0


@pytest.mark.parametrize("select", [False, True])
def test_cli_retires_http_reparse_without_mutation_or_remote_observation(
    github_runtime, select
):
    store, repo, _, api = github_runtime
    sync(store, repo)
    fetch = store.one(
        "SELECT o.* FROM fetch_occurrences o JOIN fetch_collections f USING(fetch_collection_id) WHERE f.kind='pr-detail' ORDER BY o.fetch_occurrence_id LIMIT 1"
    )
    before = list(store.connection.iterdump())
    requests = len(api.requests)
    rejected = run(
        store.path,
        "parser",
        "reparse",
        fetch["fetch_occurrence_uuidv4"],
        *(["--select"] if select else []),
        expected=5,
    )
    assert rejected["status"] == "error"
    assert rejected["error"]["code"] == "PARSER_UNSUPPORTED_INPUT"
    assert "API response replay is retired" in rejected["error"]["message"]
    assert rejected["data"] is None
    assert list(store.connection.iterdump()) == before
    assert len(api.requests) == requests
    assert not store.all("PRAGMA foreign_key_check")
