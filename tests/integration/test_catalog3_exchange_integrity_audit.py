"""Independent adversarial audit of portable closure and local CAS state."""

import copy
import json
import uuid

import pytest

from repo_catalog.adapters.sqlite.cas_integrity import diagnose_corruption
from repo_catalog.adapters.sqlite.coverage import freeze_complete_proof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.exchange_service import ExchangeService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_cas_integrity import corrupt
from tests.integration.test_catalog3_exchange import (
    complete_collection,
    fixture,
    receive,
)
from tests.integration.test_catalog3_exchange import databases as databases


def source_derived_name(db, expected):
    profile = ParserModel(db).register_profile(
        {
            "implementation": {"test": "inventory"},
            "settings": {},
            "output_schema": {},
            "capabilities": [{"owner_kind": "source", "fact_kind": "inventory"}],
        }
    )
    ref = intern_payload(db, b'{"source-wide-secret":"other-repository-inventory"}')
    input_uuid = str(uuid.uuid4())
    db.execute(
        "INSERT INTO source_input_observations(source_input_uuidv4,source_registration_uuidv4,payload_representation,payload_sha256,request_context_json,observed_at_us) VALUES(?,?,?,?, '{}',1)",
        (input_uuid, expected["source"], *ref.parameters()),
    )
    result = ParserModel(db).create_result(
        profile,
        source_registration_uuidv4=expected["source"],
        inputs=[{"source_input_uuidv4": input_uuid}],
    )
    db.execute(
        "INSERT INTO repository_name_observations(repository_name_observation_uuidv4,repository_uuidv4,name,observed_at_us,parsed_result_uuidv4,provenance_json,owner_source_registration_uuidv4) VALUES(?,?, 'observed-name',1,?,'{}',?)",
        (str(uuid.uuid4()), expected["repository"], result, expected["source"]),
    )
    ParserModel(db).publish_result(result)
    return input_uuid, result, ref


def test_source_derived_name_never_leaks_source_wide_evidence_or_dangles(databases):
    source, target = databases
    expected = fixture(source)
    input_uuid, result_uuid, reference = source_derived_name(source, expected)
    unit = Graph(source).export(expected["repository"])
    encoded = json.dumps(unit)
    assert input_uuid not in encoded
    assert reference.sha256.hex() not in encoded
    assert result_uuid not in encoded
    # A locally exported unit is closed, not a promise of source-wide evidence
    # that this exchange format deliberately cannot send later.
    assert receive(target, unit)["staged_records"] == 0
    assert (
        target.execute("SELECT count(*) FROM source_input_observations").fetchone()[0]
        == 0
    )


def test_local_quarantine_diagnostics_and_staging_do_not_cross_exchange(databases):
    source, target = databases
    expected = fixture(source)
    unrelated = fixture(source, source_local="other-source")
    isolated = intern_payload(source, b"unrelated damaged bytes")
    corrupt(source, isolated.sha256, b"changed bytes")
    diagnose_corruption(source, isolated.sha256)
    unit = Graph(source).export(expected["repository"])
    assert not {
        "payload_quarantine",
        "unresolved_payloads",
        "payload_admission_staging",
    } & {r["table"] for r in unit["records"]}
    assert unrelated["repository"] not in json.dumps(unit)
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM payload_quarantine").fetchone()[0] == 0
    assert target.execute("SELECT count(*) FROM unresolved_payloads").fetchone()[0] == 0


def test_forged_local_quarantine_record_rejects_entire_unit(databases):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    unit["records"].append(
        {
            "key": "payload_quarantine:forged",
            "table": "payload_quarantine",
            "values": {},
        }
    )
    with pytest.raises(CatalogError) as error:
        receive(target, unit)
    assert error.value.code == "INVALID_EXCHANGE"
    assert target.execute("SELECT count(*) FROM repositories").fetchone()[0] == 0
    assert target.execute("SELECT count(*) FROM payload_quarantine").fetchone()[0] == 0


def test_export_corruption_failure_persists_local_diagnosis_without_output(tmp_path):
    state = tmp_path / "state"
    MaintenanceService(state).init("catalog-text-v1", 33554432, 0)
    with Store(state) as store:
        expected = fixture(store.connection)
        digest = store.one("SELECT sha256 FROM stored_bytes")[0]
        corrupt(store.connection, digest, b"corrupted")
    output = tmp_path / "unit.json"
    with pytest.raises(CatalogError) as error:
        ExchangeService(state).export_repository(expected["repository"], output)
    assert error.value.code == "PAYLOAD_CORRUPTION"
    assert not output.exists()
    with Store(state) as store:
        assert store.one("SELECT sha256 FROM payload_quarantine")[0] == digest
        assert store.one("SELECT count(*) FROM unresolved_payloads")[0] == 1


def test_required_bytes_repeat_in_each_repository_unit_and_deduplicate_on_receive(
    databases,
):
    source, target = databases
    first = fixture(source)
    second = fixture(source, source_local="other-source")
    units = [Graph(source).export(item["repository"]) for item in (first, second)]
    for unit in units:
        objects = [r for r in unit["records"] if r["table"] == "stored_bytes"]
        assert len(objects) == 1 and objects[0]["values"]["body"]
        assert receive(target, unit)["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM stored_bytes").fetchone()[0] == 1
    assert target.execute("SELECT count(*) FROM fetch_occurrences").fetchone()[0] == 2


def test_record_order_permutation_preserves_observation_and_selection_sets(databases):
    source, first = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    reverse = copy.deepcopy(unit)
    reverse["records"].reverse()
    assert receive(first, reverse)["staged_records"] == 0
    # Independent trust does not arrive with the sender's verified choice.
    assert (
        first.execute("SELECT count(*) FROM active_fact_selections").fetchone()[0] == 0
    )
    assert (
        first.execute("SELECT parsed_result_uuidv4 FROM parsed_results").fetchone()[0]
        == expected["result"]
    )
    assert receive(first, unit)["received_records"] == 0


def pr_observation(db, expected):
    model = ParserModel(db)
    profile = model.register_profile(
        {
            "implementation": {"fixture": "pr-state"},
            "settings": {},
            "output_schema": {},
            "capabilities": [
                {"owner_kind": "repository", "fact_kind": "change-request"}
            ],
        }
    )
    result = model.create_result(
        profile,
        repository_uuidv4=expected["repository"],
        inputs=[{"fetch_occurrence_uuidv4": expected["fetch"]}],
    )
    acquisition = db.execute(
        "SELECT fetch_occurrence_id,fetch_collection_id,payload_representation,payload_sha256 FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
        (expected["fetch"],),
    ).fetchone()
    portable = str(uuid.uuid4())
    local = db.execute(
        "INSERT INTO change_request_observations(change_request_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,observed_at_us,published,payload,parsed_at_us,origin_fetch_occurrence_id) VALUES(?,?,?,?,0,1,'{}',0,?)",
        (portable, result, expected["repository"], expected["cr"], acquisition[0]),
    ).lastrowid
    model.publish_result(result)
    return portable, local, acquisition


def test_304_self_authored_evidence_uses_received_original_observation(databases):
    source, target = databases
    incoming = fixture(source)
    portable, original_id, acquisition = pr_observation(source, incoming)
    existing = fixture(target)
    _, occupied_id, _ = pr_observation(target, existing)
    assert original_id == occupied_id
    scope = source.execute(
        "SELECT resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?",
        (acquisition[1],),
    ).fetchone()[0]
    source.execute(
        "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,-1)",
        (
            scope,
            acquisition[1],
            json.dumps(
                {
                    "status": 304,
                    "fetch_occurrence_uuidv4s": [incoming["fetch"]],
                    "payload": {
                        "representation": acquisition[2],
                        "sha256": acquisition[3].hex(),
                    },
                    "change_request_observation_uuidv4": portable,
                    "parsed_result_uuidv4": source.execute(
                        "SELECT parsed_result_uuidv4 FROM change_request_observations WHERE change_request_observation_uuidv4=?",
                        (portable,),
                    ).fetchone()[0],
                    "fetch_occurrence_uuidv4": incoming["fetch"],
                }
            ),
        ),
    )
    unit = Graph(source).export(incoming["repository"])
    assert receive(target, unit)["staged_records"] == 0
    remapped = target.execute(
        "SELECT change_request_observation_id FROM change_request_observations WHERE change_request_observation_uuidv4=?",
        (portable,),
    ).fetchone()[0]
    assert remapped != original_id
    marker = json.loads(
        target.execute("SELECT evidence FROM completion_markers").fetchone()[0]
    )
    assert marker["change_request_observation_uuidv4"] == portable
    assert marker["fetch_occurrence_uuidv4"] == incoming["fetch"]
    assert "change_request_observation_id" not in marker
    assert target.execute("SELECT count(*) FROM validators").fetchone()[0] == 0


def marker_unit(db, expected):
    portable, _, acquisition = pr_observation(db, expected)
    result_uuid = db.execute(
        "SELECT parsed_result_uuidv4 FROM change_request_observations WHERE change_request_observation_uuidv4=?",
        (portable,),
    ).fetchone()[0]
    scope = db.execute(
        "SELECT resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?",
        (acquisition[1],),
    ).fetchone()[0]
    db.execute(
        "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,-1)",
        (
            scope,
            acquisition[1],
            json.dumps(
                {
                    "status": 304,
                    "fetch_occurrence_uuidv4s": [expected["fetch"]],
                    "payload": {
                        "representation": acquisition[2],
                        "sha256": acquisition[3].hex(),
                    },
                    "change_request_observation_uuidv4": portable,
                    "parsed_result_uuidv4": result_uuid,
                    "fetch_occurrence_uuidv4": expected["fetch"],
                }
            ),
        ),
    )
    return Graph(db).export(expected["repository"])


def test_304_marker_cannot_complete_before_its_original_payload_and_observation(
    databases,
):
    source, target = databases
    expected = fixture(source)
    unit = marker_unit(source, expected)
    owners_only = copy.deepcopy(unit)
    owners_only["records"] = [
        r
        for r in unit["records"]
        if r["table"]
        in {
            "repositories",
            "service_instances",
            "sources",
            "repository_bindings",
            "source_repositories",
            "change_requests",
            "resume_scopes",
            "fetch_collections",
            "completion_markers",
        }
    ]
    outcome = receive(target, owners_only)
    assert outcome["staged_records"] > 0
    assert target.execute("SELECT count(*) FROM completion_markers").fetchone()[0] == 0
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM completion_markers").fetchone()[0] == 1


def test_304_marker_rejects_an_original_observation_from_another_repository(databases):
    source, target = databases
    expected = fixture(source)
    other = fixture(target)
    other_observation, _, _ = pr_observation(target, other)
    unit = marker_unit(source, expected)
    marker = next(r for r in unit["records"] if r["table"] == "completion_markers")
    evidence = json.loads(marker["values"]["evidence"])
    evidence["change_request_observation_uuidv4"] = other_observation
    marker["values"]["evidence"] = json.dumps(evidence)
    assert receive(target, unit)["staged_records"] > 0
    assert target.execute("SELECT count(*) FROM completion_markers").fetchone()[0] == 0


def test_complete_claim_keeps_identity_when_unrelated_repository_records_grow(
    databases,
):
    source, target = databases
    expected = fixture(source)
    scope = str(uuid.uuid4())
    source.execute(
        "INSERT INTO coverage_scopes(coverage_scope_id,repository_uuidv4,change_request_id,kind) VALUES(?,?,?,'comment')",
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
    first = Graph(source).export(expected["repository"])
    assert receive(target, first)["staged_records"] == 0
    source.execute(
        "INSERT INTO repository_endpoints(repository_endpoint_id,repository_uuidv4,url,transport,metadata) VALUES(?,?,'file:///unrelated-endpoint.git','file','{}')",
        (str(uuid.uuid4()), expected["repository"]),
    )
    second = Graph(source).export(expected["repository"])
    assert receive(target, second)["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM coverage_claims").fetchone()[0] == 1
