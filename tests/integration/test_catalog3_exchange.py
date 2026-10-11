"""Portable graph closure, remapping, staging and untrusted-byte contracts."""

import copy
import hashlib
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.coverage import freeze_complete_proof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.schema import schema_sql


def uid():
    return str(uuid.uuid4())


def catalog():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(schema_sql())
    return db


@pytest.fixture
def databases():
    connections = [catalog(), catalog()]
    yield connections
    for db in connections:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        db.close()


def fixture(
    db,
    *,
    repository=None,
    source_local="source",
    source_registration=None,
    service=None,
    body=b'{"body":"hello"}',
    next_cursor=None,
):
    repository, source_registration, service = (
        repository or uid(),
        source_registration or uid(),
        service or uid(),
    )
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?, 'repo', '{}')",
        (repository,),
    )
    if not db.execute(
        "SELECT 1 FROM service_instances WHERE service_instance_uuidv4=?", (service,)
    ).fetchone():
        db.execute(
            "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','github','{}')",
            (service,),
        )
    if not db.execute(
        "SELECT 1 FROM sources WHERE source_registration_uuidv4=?",
        (source_registration,),
    ).fetchone():
        db.execute(
            "INSERT INTO sources VALUES(?,?,?,'github_inventory','Remote name',?)",
            (source_local, source_registration, service, '{"owner":"remote-owner"}'),
        )
    binding, cr, scope, collection, fetch = (uid() for _ in range(5))
    db.execute(
        "INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES(?,?)",
        (source_local, repository),
    )
    db.execute(
        "INSERT INTO repository_bindings VALUES(?,?,?,?,'{}',0)",
        (binding, repository, service, repository),
    )
    db.execute(
        "INSERT INTO change_requests VALUES(?,?,?,'pull_request',1)",
        (cr, repository, binding),
    )
    db.execute(
        "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,source_id,request_context,parser_version,profile_version,confidence) VALUES(?,?,?,'{}','parser','profile','proven')",
        (scope, repository, source_local),
    )
    db.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,source_id,kind,resume_scope_id) VALUES(?,?,?,?,'comments',?)",
        (collection, repository, cr, source_local, scope),
    )
    ref = intern_payload(db, body, representation="decoded_api")
    occurrence = db.execute(
        "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,next_cursor,observed_at_us,parsed_at_us) VALUES(?,?,?,0,?,?,'{}',?,-1,0)",
        (fetch, repository, collection, *ref.parameters(), next_cursor),
    ).lastrowid
    definition = {
        "implementation": {"test": "exact-fixture"},
        "settings": {},
        "output_schema": {},
        "capabilities": [{"owner_kind": "repository", "fact_kind": "comment"}],
    }
    model = ParserModel(db)
    profile = model.register_profile(definition)
    verification = model.verify_profile(
        profile,
        criteria={"suite": "fixture"},
        evidence={
            "definition": definition,
            "capabilities": [
                {
                    "owner_kind": "repository",
                    "fact_kind": "comment",
                    "outcome": "passed",
                    "checks": ["owner"],
                }
            ],
        },
    )
    model.trust_verification(verification)
    result = model.create_result(
        profile,
        repository_uuidv4=repository,
        inputs=[{"fetch_occurrence_uuidv4": fetch}],
    )
    text = hashlib.sha256(b"hello").digest()
    if not db.execute("SELECT 1 FROM text_bodies WHERE sha256=?", (text,)).fetchone():
        db.execute(
            "INSERT INTO text_bodies(body,byte_length,sha256) VALUES('hello',5,?)",
            (text,),
        )
    db.execute("INSERT INTO documents VALUES(?,'comment','1')", (cr,))
    observation = uid()
    db.execute(
        "INSERT INTO document_observations(document_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at_us,parsed_at_us,fetch_occurrence_id,metadata) VALUES(?,?,?,?,'comment','1',?,-1,0,?,'{}')",
        (observation, result, repository, cr, text, occurrence),
    )
    model.publish_result(result)
    model.select_profile(
        profile, verification, repository_uuidv4=repository, fact_kind="comment"
    )
    model.select_fact(
        result,
        fact_kind="comment",
        change_request_id=cr,
        kind="comment",
        provider_change_request_document_id="1",
    )
    return {
        "repository": repository,
        "source": source_registration,
        "service": service,
        "fetch": fetch,
        "result": result,
        "profile": profile,
        "verification": verification,
        "observation": observation,
        "cr": cr,
    }


def complete_collection(db, fetch_uuid):
    """Seal explicit immutable proof used by transportable coverage."""
    fetch = db.execute(
        "SELECT fetch_collection_id,observed_at_us FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
        (fetch_uuid,),
    ).fetchone()
    scope = db.execute(
        "SELECT resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?",
        (fetch[0],),
    ).fetchone()[0]
    manifest = [
        row[0]
        for row in db.execute(
            "SELECT fetch_occurrence_uuidv4 FROM fetch_occurrences WHERE fetch_collection_id=? ORDER BY fetch_occurrence_uuidv4",
            (fetch[0],),
        )
    ]
    db.execute(
        "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,?)",
        (
            scope,
            fetch[0],
            json.dumps({"terminal": True, "fetch_occurrence_uuidv4s": manifest}),
            fetch[1],
        ),
    )
    return fetch[0]


def receive(db, unit):
    db.execute("BEGIN IMMEDIATE")
    try:
        result = Graph(db).receive(unit)
        db.commit()
        return result
    except BaseException:
        db.rollback()
        raise


def test_complete_round_trip_remaps_local_ids_and_preserves_portable_ids(databases):
    source, target = databases
    expected = fixture(source)
    # Occupy the receiver's first local IDs without matching portable identity.
    fixture(target, source_local="source")
    unit = Graph(source).export(expected["repository"])
    outcome = receive(target, unit)
    assert outcome["staged_records"] == 0, target.execute(
        "SELECT table_name,reason FROM exchange_staging"
    ).fetchall()
    assert target.execute(
        "SELECT parsed_result_uuidv4 FROM document_observations WHERE document_observation_uuidv4=?",
        (expected["observation"],),
    ).fetchone() == (expected["result"],)
    assert target.execute(
        "SELECT fetch_occurrence_id FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
        (expected["fetch"],),
    ).fetchone() == (2,)
    row = target.execute(
        "SELECT source_id,settings FROM sources WHERE source_registration_uuidv4=?",
        (expected["source"],),
    ).fetchone()
    assert row[0] != "source" and row[1] is None
    assert (
        target.execute(
            "SELECT trusted FROM local_parser_profile_verification_trust WHERE parser_profile_verification_uuidv4=?",
            (expected["verification"],),
        ).fetchone()
        is None
    )
    assert target.execute("SELECT count(*) FROM stored_bytes").fetchone() == (1,)
    assert target.execute("SELECT count(*) FROM document_observations").fetchone() == (
        2,
    )
    assert receive(target, unit)["received_records"] == 0
    forwarded = Graph(target).export(expected["repository"])
    assert {r["key"] for r in forwarded["records"]} == {
        r["key"] for r in unit["records"]
    }


def test_missing_dependencies_survive_reopen_and_promote_without_new_ids(
    databases, tmp_path
):
    source, _ = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    early = dict(
        unit,
        records=[
            r
            for r in unit["records"]
            if r["table"] in {"document_observations", "parsed_result_inputs"}
        ],
    )
    path = tmp_path / "target.sqlite3"
    target = sqlite3.connect(path, isolation_level=None)
    target.executescript(schema_sql())
    assert receive(target, early)["staged_records"] == 2
    target.close()
    target = sqlite3.connect(path, isolation_level=None)
    target.execute("PRAGMA foreign_keys=ON")
    target.execute("PRAGMA recursive_triggers=ON")
    assert receive(target, unit)["staged_records"] == 0, target.execute(
        "SELECT table_name,reason FROM exchange_staging"
    ).fetchall()
    assert target.execute(
        "SELECT document_observation_uuidv4 FROM document_observations"
    ).fetchone() == (expected["observation"],)
    target.close()


def test_mismatched_sha_is_rejected_without_retaining_any_bytes(databases):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    for record in unit["records"]:
        if record["table"] == "stored_bytes":
            record["values"]["body"] = {"$bytes": "YmFk"}
    outcome = receive(target, unit)
    assert outcome["rejected_records"] > 0
    assert target.execute("SELECT count(*) FROM repositories").fetchone() == (1,)
    assert not any(
        "YmFk" in row[0]
        for row in target.execute("SELECT record_json FROM exchange_staging")
    )
    assert target.execute("SELECT count(*) FROM stored_bytes").fetchone() == (0,)


def test_same_uuid_different_fact_is_staged_original_preserved(databases):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    assert receive(target, unit)["staged_records"] == 0
    conflicting = copy.deepcopy(unit)
    for record in conflicting["records"]:
        if record["table"] == "document_observations":
            record["values"]["metadata"] = '{"changed":true}'
    assert receive(target, conflicting)["staged_records"] == 1
    assert target.execute("SELECT metadata FROM document_observations").fetchone() == (
        "{}",
    )
    assert (
        target.execute("SELECT reason FROM exchange_staging")
        .fetchone()[0]
        .startswith("conflict:")
    )


def test_source_wide_local_policy_and_second_repository_are_not_exported(databases):
    source, target = databases
    expected = fixture(source)
    other = fixture(
        source, source_registration=expected["source"], service=expected["service"]
    )
    source.execute(
        "INSERT INTO source_input_observations(source_input_uuidv4,source_registration_uuidv4,request_context_json) VALUES(?,?,'{}')",
        (uid(), expected["source"]),
    )
    unit = Graph(source).export(expected["repository"])
    tables = {r["table"] for r in unit["records"]}
    assert "source_input_observations" not in tables
    assert "local_parser_profile_verification_trust" not in tables
    assert "validators" not in tables
    assert not any(other["repository"] in json.dumps(r) for r in unit["records"])
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM repositories").fetchone() == (1,)


def test_sources_reconfigure_locally_without_import_overwrite(databases):
    source, target = databases
    expected = fixture(source)
    assert (
        receive(target, Graph(source).export(expected["repository"]))["staged_records"]
        == 0
    )
    target.execute("UPDATE sources SET name='My display',settings='{}'")
    source.execute(
        "UPDATE sources SET name='Sender renamed',settings='{\"owner\":\"different\"}'"
    )
    assert (
        receive(target, Graph(source).export(expected["repository"]))["staged_records"]
        == 0
    )
    assert target.execute("SELECT name,settings FROM sources").fetchone() == (
        "My display",
        "{}",
    )
    assert target.execute(
        "SELECT COUNT(*) FROM exchange_source_provenance"
    ).fetchone() == (2,)


def test_competing_unadmitted_variants_are_both_held(databases):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    original = next(r for r in unit["records"] if r["table"] == "document_observations")
    conflict = copy.deepcopy(original)
    conflict["values"]["metadata"] = '{"conflicting":true}'
    unit["records"].append(conflict)
    outcome = receive(target, unit)
    assert outcome["staged_records"] >= 2
    assert target.execute("SELECT COUNT(*) FROM document_observations").fetchone() == (
        0,
    )
    assert target.execute(
        "SELECT COUNT(*) FROM exchange_staging WHERE table_name='document_observations' AND reason='conflict:competing_variants'"
    ).fetchone() == (2,)


def test_existing_corrupt_bytes_get_diagnosed_without_automatic_repair(databases):
    source, target = databases
    expected = fixture(source)
    digest, body = source.execute("SELECT sha256,body FROM stored_bytes").fetchone()
    target.execute("INSERT INTO stored_bytes VALUES(?,?,?)", (digest, b"corrupt", 7))
    outcome = receive(target, Graph(source).export(expected["repository"]))
    assert outcome["staged_records"] > 0
    assert target.execute("SELECT body FROM stored_bytes").fetchone() == (b"corrupt",)
    assert target.execute("SELECT sha256 FROM payload_quarantine").fetchone() == (
        digest,
    )
    assert target.execute(
        "SELECT COUNT(*) FROM unresolved_payloads WHERE reason='physical_corruption'"
    ).fetchone() == (1,)
    assert body != b"corrupt"


def test_application_export_import_reopens_fresh_catalogs(tmp_path):
    from repo_catalog.adapters.sqlite.store import Store
    from repo_catalog.application.exchange_service import ExchangeService
    from repo_catalog.application.maintenance_service import MaintenanceService

    first, second = tmp_path / "first", tmp_path / "second"
    for state in (first, second):
        MaintenanceService(state).init("catalog-text-v1", 32 * 1024 * 1024, 0)
    with Store(first) as store, store.transaction():
        expected = fixture(store.connection)
    path = tmp_path / "repository.json"
    assert (
        ExchangeService(first).export_repository(expected["repository"], path).status
        == "complete"
    )
    assert ExchangeService(second).import_file(path).status == "complete"
    with Store(second, readonly=True) as store:
        assert (
            store.one("SELECT parsed_result_uuidv4 FROM parsed_results")[0]
            == expected["result"]
        )
        assert store.one("PRAGMA integrity_check")[0] == "ok"
        assert store.all("PRAGMA foreign_key_check") == []
    assert ExchangeService(second).staging().data == []


def test_scope_mapping_forwarding_and_independent_dag_heads(databases):
    source, target = databases
    expected = fixture(source)
    assert (
        receive(target, Graph(source).export(expected["repository"]))["staged_records"]
        == 0
    )
    original_scope = source.execute(
        "SELECT selection_scope_uuidv4 FROM parser_profile_selection_scopes"
    ).fetchone()[0]
    receiver_scope = target.execute(
        "SELECT selection_scope_uuidv4 FROM parser_profile_selection_scopes"
    ).fetchone()[0]
    assert original_scope != receiver_scope
    assert (
        receive(source, Graph(target).export(expected["repository"]))["staged_records"]
        == 0
    )
    for db in (source, target):
        model = ParserModel(db)
        model.trust_verification(expected["verification"])
        model.select_profile(
            expected["profile"],
            expected["verification"],
            repository_uuidv4=expected["repository"],
            fact_kind="comment",
        )
    assert (
        receive(source, Graph(target).export(expected["repository"]))["staged_records"]
        == 0
    )
    assert source.execute(
        "SELECT count(*) FROM active_parser_profile_selections"
    ).fetchone() == (0,)
    assert (
        receive(target, Graph(source).export(expected["repository"]))["staged_records"]
        == 0
    )
    assert target.execute(
        "SELECT count(*) FROM active_parser_profile_selections"
    ).fetchone() == (0,)
    model = ParserModel(source)
    predecessors = [
        row[0]
        for row in source.execute(
            "SELECT d.selection_decision_uuidv4 FROM parser_profile_selection_decisions d WHERE NOT EXISTS(SELECT 1 FROM parser_profile_selection_predecessors p WHERE p.predecessor_decision_uuidv4=d.selection_decision_uuidv4)"
        )
    ]
    merge = model.select_profile(
        expected["profile"],
        expected["verification"],
        predecessors=predecessors,
        repository_uuidv4=expected["repository"],
        fact_kind="comment",
    )
    assert (
        receive(target, Graph(source).export(expected["repository"]))["staged_records"]
        == 0
    )
    assert target.execute(
        "SELECT selection_decision_uuidv4 FROM active_parser_profile_selections"
    ).fetchone() == (merge,)


def test_conflicting_fact_never_leaves_first_arrival_as_current(databases):
    source, target = databases
    expected = fixture(source)
    original = Graph(source).export(expected["repository"])
    conflicting = copy.deepcopy(original)
    for record in conflicting["records"]:
        if record["table"] == "document_observations":
            record["values"]["metadata"] = '{"conflicting":true}'
    for first, second in ((original, conflicting), (conflicting, original)):
        receiver = catalog()
        receive(receiver, first)
        ParserModel(receiver).trust_verification(expected["verification"])
        assert receiver.execute(
            "SELECT count(*) FROM current_document_observations"
        ).fetchone() == (1,)
        assert receive(receiver, second)["staged_records"] == 1
        assert receiver.execute(
            "SELECT count(*) FROM current_document_observations"
        ).fetchone() == (0,)
        assert receiver.execute(
            "SELECT parsed_result_uuidv4 FROM exchange_blocked_results"
        ).fetchone() == (expected["result"],)
        receiver.close()


def test_truncated_unit_cannot_publish_complete_coverage(databases):
    source, target = databases
    expected = fixture(source)
    scope = uid()
    source.execute(
        "INSERT INTO coverage_scopes VALUES(?,?,?,'comment')",
        (scope, expected["repository"], expected["cr"]),
    )
    source.execute(
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES(?,'complete',-1,?)",
        (
            scope,
            freeze_complete_proof(
                source,
                -1,
                json.dumps(
                    {
                        "fetch_collection_ids": [
                            complete_collection(source, expected["fetch"])
                        ]
                    }
                ),
            ),
        ),
    )
    unit = Graph(source).export(expected["repository"])
    partial = dict(
        unit,
        records=[
            record
            for record in unit["records"]
            if record["table"] != "fetch_occurrences"
        ],
    )
    assert receive(target, partial)["staged_records"] > 0
    assert target.execute(
        "SELECT COUNT(*) FROM coverage_claims WHERE coverage_state='complete'"
    ).fetchone() == (0,)
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute(
        "SELECT coverage_state,observed_at_us FROM current_coverage"
    ).fetchone() == ("complete", -1)


def test_unsubstantiated_complete_claim_is_not_exported(databases):
    source, target = databases
    repository, scope = uid(), uid()
    source.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'empty','{}')",
        (repository,),
    )
    source.execute(
        "INSERT INTO coverage_scopes VALUES(?,?,NULL,'refs')", (scope, repository)
    )
    source.execute(
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us) VALUES(?,'complete',0)",
        (scope,),
    )
    unit = Graph(source).export(repository)
    assert not any(record["table"] == "coverage_claims" for record in unit["records"])
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute("SELECT coverage_state FROM current_coverage").fetchone() == (
        "unknown",
    )


def test_source_membership_interval_growth_is_not_immutable_collision(databases):
    source, target = databases
    expected = fixture(source)
    source.execute("UPDATE source_repositories SET first_seen_us=0,last_seen_us=1")
    assert (
        receive(target, Graph(source).export(expected["repository"]))["staged_records"]
        == 0
    )
    source.execute("UPDATE source_repositories SET first_seen_us=-1,last_seen_us=5")
    assert (
        receive(target, Graph(source).export(expected["repository"]))["staged_records"]
        == 0
    )
    assert target.execute(
        "SELECT first_seen_us,last_seen_us FROM source_repositories"
    ).fetchone() == (-1, 5)
