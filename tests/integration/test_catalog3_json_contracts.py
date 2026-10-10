"""Authored references fail closed while provider JSON remains byte evidence."""

import base64
import copy
import hashlib
import json
import sqlite3
import uuid
from importlib.resources import files

import pytest

from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import (
    JsonContractError,
    MissingJsonDependencies,
    guard_sql,
    inventory,
    reference_dependencies,
    validate_catalog,
    validate_record,
)
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.schema import schema_sql
from tests.integration.test_catalog3_exchange import catalog, fixture, receive


@pytest.fixture
def facts():
    db = catalog()
    owner = fixture(db)
    other = fixture(db, source_local="other-source")
    yield db, owner, other
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    db.close()


def record(owner, provenance):
    return {
        "repository_uuidv4": owner["repository"],
        "provenance_json": json.dumps(provenance),
    }


def insert_name(db, owner, provenance):
    ident = str(uuid.uuid4())
    db.execute(
        "INSERT INTO repository_name_observations(repository_name_observation_uuidv4,repository_uuidv4,name,provenance_json) VALUES(?,?,'reference-test',?)",
        (ident, owner["repository"], json.dumps(provenance)),
    )
    return ident


def test_registry_is_exhaustive_and_packaged_guards_match(facts):
    db, *_ = facts
    entries = inventory(db)
    assert len(entries) >= 40
    assert {e["category"] for e in entries} >= {
        "authored",
        "provider",
        "operational",
        "definition",
        "fact-manifest",
    }
    assert (
        files("repo_catalog").joinpath("resources/json_contracts.sql").read_text()
        == guard_sql()
    )
    assert validate_catalog(db)["classified_fields"] == len(entries)
    db.execute("CREATE TABLE unclassified(body TEXT CHECK(json_valid(body)))")
    with pytest.raises(JsonContractError, match="Unclassified"):
        inventory(db)
    db.execute("DROP TABLE unclassified")
    db.execute("CREATE TABLE no_check(provenance_json TEXT)")
    with pytest.raises(JsonContractError, match="Unclassified"):
        inventory(db)


@pytest.mark.parametrize(
    "malformed",
    [
        None,
        1,
        [],
        "UPPERCASE",
        "00000000-0000-0000-0000-000000000000",
        "00000000-0000-4000-8000-000000000001\0",
    ],
)
def test_nested_reference_requires_canonical_typed_uuid(facts, malformed):
    db, owner, _ = facts
    provenance = {"nested": [{"fetch_occurrence_uuidv4": malformed}]}
    with pytest.raises(JsonContractError):
        validate_record(db, "repository_name_observations", record(owner, provenance))
    with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
        insert_name(db, owner, provenance)


@pytest.mark.parametrize(
    "field,source_key",
    [
        ("fetch_occurrence_uuidv4", "fetch"),
        ("document_observation_uuidv4", "observation"),
        ("parsed_result_uuidv4", "result"),
        ("repository_uuidv4", "repository"),
    ],
)
def test_nested_references_reject_foreign_repository_in_python_and_sql(
    facts, field, source_key
):
    db, owner, other = facts
    provenance = {"nested": {field: other[source_key]}}
    with pytest.raises(JsonContractError, match="ownership"):
        validate_record(db, "repository_name_observations", record(owner, provenance))
    with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
        insert_name(db, owner, provenance)


def test_valid_uuid_of_wrong_kind_is_malformed_not_missing(facts):
    db, owner, _ = facts
    provenance = {"parsed_result_uuidv4": owner["fetch"]}
    with pytest.raises(JsonContractError, match="wrong object kind"):
        validate_record(db, "repository_name_observations", record(owner, provenance))


@pytest.mark.parametrize(
    "field,identity",
    [("change_request_ids", "cr"), ("parsed_result_uuidv4s", "result")],
)
def test_aggregate_proof_reference_arrays_validate_target_owner(facts, field, identity):
    db, owner, other = facts
    valid = {"nested": {field: [owner[identity], owner[identity]]}}
    validate_record(db, "repository_name_observations", record(owner, valid))
    insert_name(db, owner, valid)
    foreign = {"nested": {field: [other[identity]]}}
    with pytest.raises(JsonContractError, match="ownership"):
        validate_record(db, "repository_name_observations", record(owner, foreign))
    with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
        insert_name(db, owner, foreign)


def test_missing_multiple_targets_and_duplicate_reference_set_semantics(facts):
    db, owner, _ = facts
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    data = record(
        owner,
        {
            "items": [
                {"fetch_occurrence_uuidv4": first},
                {"fetch_occurrence_uuidv4": second},
                {"fetch_occurrence_uuidv4": first},
            ]
        },
    )
    with pytest.raises(MissingJsonDependencies) as cause:
        validate_record(db, "repository_name_observations", data)
    assert len(cause.value.dependencies) == 2
    assert (
        validate_record(db, "repository_name_observations", data, allow_missing=True)
        == cause.value.dependencies
    )
    assert len(reference_dependencies("repository_name_observations", data)) == 2


@pytest.mark.parametrize(
    "mutation", ["uppercase", "nul", "representation", "extra", "foreign"]
)
def test_payload_reference_exact_representation_bytes_and_owner(facts, mutation):
    db, owner, other = facts
    if mutation == "foreign":
        # The other acquisition must have genuinely distinct bytes.
        from repo_catalog.adapters.sqlite.payloads import intern_payload

        ref = intern_payload(db, b"different", representation="decoded_api")
        # No owner acquisition uses these bytes: ownership cannot follow mere CAS existence.
        payload = ref.as_json()
    else:
        representation, digest = db.execute(
            "SELECT payload_representation,payload_sha256 FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
            (owner["fetch"],),
        ).fetchone()
        payload = {"representation": representation, "sha256": digest.hex()}
        if mutation == "uppercase":
            payload["sha256"] = payload["sha256"].upper()
        elif mutation == "nul":
            payload["sha256"] = payload["sha256"][:62] + "\x00a"
        elif mutation == "representation":
            payload["representation"] = "invalid"
        else:
            payload["extra"] = True
    data = record(owner, {"nested": {"payload": payload}})
    with pytest.raises(JsonContractError):
        validate_record(db, "repository_name_observations", data)
    with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
        insert_name(db, owner, {"nested": {"payload": payload}})


def test_correct_payload_reference_keeps_logical_representation(facts):
    db, owner, _ = facts
    representation, digest = db.execute(
        "SELECT payload_representation,payload_sha256 FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
        (owner["fetch"],),
    ).fetchone()
    provenance = {
        "nested": {
            "payload": {"representation": representation, "sha256": digest.hex()}
        }
    }
    validate_record(db, "repository_name_observations", record(owner, provenance))
    insert_name(db, owner, provenance)
    assert reference_dependencies(
        "repository_name_observations", record(owner, provenance)
    )[0]["values"] == (representation, digest)


def test_shared_bytes_do_not_make_delayed_owner_acquisition_malformed(facts):
    db, owner, _ = facts
    foreign = fixture(
        db, source_local="distinct-source", body=b"distinct globally shared bytes"
    )
    representation, digest = db.execute(
        "SELECT payload_representation,payload_sha256 FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
        (foreign["fetch"],),
    ).fetchone()
    later = str(uuid.uuid4())
    provenance = {
        "payload": {"representation": representation, "sha256": digest.hex()},
        "fetch_occurrence_uuidv4": later,
    }
    data = record(owner, provenance)
    with pytest.raises(MissingJsonDependencies) as failure:
        validate_record(db, "repository_name_observations", data)
    assert failure.value.dependencies == [
        {
            "table": "fetch_occurrences",
            "columns": ("fetch_occurrence_uuidv4",),
            "values": (later,),
        }
    ]
    collection = db.execute(
        "SELECT fetch_collection_id FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
        (owner["fetch"],),
    ).fetchone()[0]
    db.execute(
        "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,parsed_at_us) VALUES(?,?,?,1,?,?,'{}',0)",
        (later, owner["repository"], collection, representation, digest),
    )
    assert validate_record(db, "repository_name_observations", data) == []
    insert_name(db, owner, provenance)


def test_unknown_reference_category_and_local_ids_cannot_bypass(facts):
    db, owner, _ = facts
    for provenance in (
        {"nested": {"unregistered_uuidv4": str(uuid.uuid4())}},
        {"nested": {"fetch_occurrence_id": 1}},
        {"references": []},
    ):
        with pytest.raises(JsonContractError):
            validate_record(
                db, "repository_name_observations", record(owner, provenance)
            )
        with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
            insert_name(db, owner, provenance)


@pytest.mark.parametrize(
    "ambiguous",
    [
        '{"note":1,"note":2}',
        '{"nested":[{"note":1,"note":1}]}',
        '{"nested":[{"0":1,"0":2}]}',
        '{"nested":{"note":1,"\\u006eote":1}}',
    ],
)
def test_duplicate_json_keys_are_rejected_by_python_and_sql(facts, ambiguous):
    db, owner, _ = facts
    with pytest.raises(JsonContractError, match="Duplicate"):
        validate_record(
            db,
            "repository_name_observations",
            {"repository_uuidv4": owner["repository"], "provenance_json": ambiguous},
        )
    with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
        db.execute(
            "INSERT INTO repository_name_observations(repository_name_observation_uuidv4,repository_uuidv4,name,provenance_json) VALUES(?,?,'dup',?)",
            (str(uuid.uuid4()), owner["repository"], ambiguous),
        )


def test_same_keys_and_array_indices_in_distinct_containers_are_valid(facts):
    db, owner, _ = facts
    provenance = {"nested": [{"0": 1}, {"0": 1}], "arrays": [[1, 1], [1, 1]]}
    assert (
        validate_record(db, "repository_name_observations", record(owner, provenance))
        == []
    )
    ident = insert_name(db, owner, provenance)
    assert db.execute(
        "SELECT provenance_json FROM repository_name_observations WHERE repository_name_observation_uuidv4=?",
        (ident,),
    ).fetchone() == (json.dumps(provenance),)


def test_future_selection_uuid_is_declaration_only_at_git_derivation_root(facts):
    db, owner, _ = facts
    model = ParserModel(db)
    future = str(uuid.uuid4())
    inputs = [{"fetch_occurrence_uuidv4": owner["fetch"]}]
    result = model.create_result(
        owner["profile"],
        repository_uuidv4=owner["repository"],
        inputs=inputs,
        derivation={
            "kind": "git",
            "selection_decision_uuidv4": future,
            "selection_predecessors": [],
        },
    )
    assert db.execute(
        "SELECT parsed_result_uuidv4 FROM parsed_results WHERE parsed_result_uuidv4=?",
        (result,),
    ).fetchone()
    with pytest.raises(MissingJsonDependencies):
        model.create_result(
            owner["profile"],
            repository_uuidv4=owner["repository"],
            inputs=inputs,
            derivation={"nested": {"selection_decision_uuidv4": future}},
        )


def test_provider_projection_keeps_reference_looking_fields_opaque(facts):
    db, owner, _ = facts
    provider = '{"payload":{"sha256":"UPPER","representation":"alien"},"nested":{"parsed_result_uuidv4":null}}'
    validate_record(
        db,
        "document_observations",
        {"repository_uuidv4": owner["repository"], "metadata": provider},
    )
    assert reference_dependencies("document_observations", {"metadata": provider}) == []
    result = ParserModel(db).create_result(
        owner["profile"],
        repository_uuidv4=owner["repository"],
        inputs=[{"fetch_occurrence_uuidv4": owner["fetch"]}],
    )
    db.execute(
        "INSERT INTO document_observations(document_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,kind,provider_change_request_document_id,text_body_sha256,parsed_at_us,metadata) SELECT ?,?,?,change_request_id,kind,provider_change_request_document_id,text_body_sha256,0,? FROM document_observations WHERE document_observation_uuidv4=?",
        (
            str(uuid.uuid4()),
            result,
            owner["repository"],
            provider,
            owner["observation"],
        ),
    )
    assert db.execute(
        "SELECT metadata FROM document_observations WHERE parsed_result_uuidv4=?",
        (result,),
    ).fetchone() == (provider,)


def test_nested_verification_evidence_references_are_validated(facts):
    db, owner, other = facts
    data = {
        "criteria_json": json.dumps({"reports": [{"sha256": "f" * 64}]}),
        "evidence_json": json.dumps(
            {"nested": {"parsed_result_uuidv4": str(uuid.uuid4())}}
        ),
    }
    with pytest.raises(MissingJsonDependencies):
        validate_record(db, "parser_profile_verifications", data)
    data["evidence_json"] = json.dumps(
        {"nested": {"parsed_result_uuidv4": owner["fetch"]}}
    )
    with pytest.raises(JsonContractError, match="wrong object kind"):
        validate_record(db, "parser_profile_verifications", data)


@pytest.mark.parametrize(
    "details",
    [
        {"expected_roles": []},
        {"expected_roles": {"head": "not-a-git-oid"}},
        {"expected_roles": {"head": "A" * 40}},
        {"expected_roles": {"unknown": "a" * 40}},
        {"api_head_base_stable": "yes"},
        {"code_inputs_complete": 1},
        {"missing_roles": [None]},
        {"provider_limits": {"commits": True}},
        {"merge": {"merge": "not-an-oid"}},
    ],
)
def test_interpreted_code_details_reject_malformed_git_declarations(facts, details):
    db, owner, _ = facts
    data = {
        "repository_uuidv4": owner["repository"],
        "object_format": "sha1",
        "details": json.dumps(details),
    }
    with pytest.raises(JsonContractError):
        validate_record(db, "code_observations", data)
    from tests.support.parser_facts import register_test_profile

    result = ParserModel(db).create_result(
        register_test_profile(db),
        repository_uuidv4=owner["repository"],
        inputs=[{"fetch_occurrence_uuidv4": owner["fetch"]}],
    )
    parent = db.execute(
        "INSERT INTO change_request_observations(change_request_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,published,payload,parsed_at_us) VALUES(?,?,?,?,1,'{}',0)",
        (str(uuid.uuid4()), result, owner["repository"], owner["cr"]),
    ).lastrowid
    with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
        db.execute(
            "INSERT INTO code_observations(code_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,change_request_observation_id,state,object_format,details) VALUES(?,?,?,?,?,'partial','sha1',?)",
            (
                str(uuid.uuid4()),
                result,
                owner["repository"],
                owner["cr"],
                parent,
                data["details"],
            ),
        )


def test_valid_code_expectations_are_declarations_before_git_acquisition(facts):
    db, owner, _ = facts
    details = {
        "api_head_base_stable": False,
        "code_inputs_complete": False,
        "expected_roles": {"head": "a" * 40, "review-target:" + "b" * 40: "b" * 40},
        "missing_roles": ["head"],
        "provider_limits": {"commits": 250, "files": 3000},
        "merge": {"merge": None, "test-merge": "c" * 40},
    }
    assert (
        validate_record(
            db,
            "code_observations",
            {
                "repository_uuidv4": owner["repository"],
                "object_format": "sha1",
                "details": json.dumps(details),
            },
        )
        == []
    )


@pytest.mark.parametrize(
    "acquisition_request",
    [
        {"variables": []},
        {"variables": {"thread": []}},
        {"variables": {"pageSize": True}},
        {"variables": {"cursor": {}}},
        {"context_proven": 1},
        {"terminal": "true"},
    ],
)
def test_interpreted_acquisition_request_fields_have_concrete_types(
    facts, acquisition_request
):
    db, owner, _ = facts
    with pytest.raises(JsonContractError):
        validate_record(
            db,
            "fetch_occurrences",
            {
                "repository_uuidv4": owner["repository"],
                "request": json.dumps(acquisition_request),
            },
        )
    collection, representation, digest = db.execute(
        "SELECT fetch_collection_id,payload_representation,payload_sha256 FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
        (owner["fetch"],),
    ).fetchone()
    with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
        db.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,parsed_at_us) VALUES(?,?,?,1,?,?,?,0)",
            (
                str(uuid.uuid4()),
                owner["repository"],
                collection,
                representation,
                digest,
                json.dumps(acquisition_request),
            ),
        )


@pytest.mark.parametrize(
    "bad",
    [
        "name",
        "name_b64",
        "oid",
        "peeled",
        "type",
        "pr-number",
        "oid-nul",
        "peeled-nul",
        "expected-nul",
    ],
)
def test_captured_git_refs_validate_interpreted_fields_before_objects_exist(facts, bad):
    db, owner, _ = facts
    ref = {
        "name": "refs/heads/main",
        "name_b64": base64.b64encode(b"refs/heads/main").decode(),
        "oid": "a" * 40,
        "type": "commit",
        "peeled": None,
    }
    good = {
        "repository_uuidv4": owner["repository"],
        "object_format": "sha1",
        "roots_manifest": json.dumps([ref]),
    }
    assert validate_record(db, "git_acquisitions", good) == []
    if bad == "pr-number":
        ref.update(role="head", expected=ref["oid"], number=False)
    elif bad == "expected-nul":
        ref.update(role="head", expected="a" * 38 + "\x00a", number=1)
    elif bad.endswith("-nul"):
        ref[bad.removesuffix("-nul")] = "a" * 38 + "\x00a"
    elif bad == "name_b64":
        ref[bad] = "!!!!"
    elif bad == "type":
        ref[bad] = "alien"
    elif bad == "name":
        ref[bad] = None
    else:
        ref[bad] = "A" * 40
    malformed = {**good, "roots_manifest": json.dumps([ref])}
    with pytest.raises(JsonContractError):
        validate_record(db, "git_acquisitions", malformed)
    with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
        db.execute(
            "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,request,roots_manifest) VALUES(?,?,'sha1','git','{}',?)",
            (str(uuid.uuid4()), owner["repository"], malformed["roots_manifest"]),
        )


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
@pytest.mark.parametrize("column", ["object_manifest_json", "root_manifest_json"])
def test_sealed_git_membership_rejects_embedded_nul_oid(facts, object_format, column):
    from repo_catalog.adapters.sqlite.payloads import intern_payload

    db, owner, _ = facts
    acquisition = str(uuid.uuid4())
    db.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,request) VALUES(?,?,?,'git','{}')",
        (acquisition, owner["repository"], object_format),
    )
    oid = hashlib.new(object_format, b"blob 0\0").digest()
    obj = db.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES(?,?,'blob',0,1)",
        (object_format, oid),
    ).lastrowid
    payload = intern_payload(db, b"", representation="git-object-raw-v1")
    db.execute(
        "INSERT INTO git_object_payloads(git_object_id,payload_representation,payload_sha256) VALUES(?,?,?)",
        (obj, *payload.parameters()),
    )
    db.execute(
        "INSERT INTO repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id) VALUES(?,?,?)",
        (owner["repository"], obj, acquisition),
    )
    db.execute(
        "INSERT INTO acquisition_roots(git_acquisition_id,repository_uuidv4,object_format,oid,role,published) VALUES(?,?,?,?,'traversal',1)",
        (acquisition, owner["repository"], object_format, oid),
    )
    valid = {
        "git_acquisition_id": acquisition,
        "repository_uuidv4": owner["repository"],
        "object_manifest_json": json.dumps(
            [
                {
                    "object_format": object_format,
                    "oid": oid.hex(),
                    "payload": payload.as_json(),
                }
            ]
        ),
        "root_manifest_json": json.dumps(
            [{"object_format": object_format, "oid": oid.hex(), "role": "traversal"}]
        ),
    }
    assert validate_record(db, "git_acquisition_publications", valid) == []
    members = json.loads(valid[column])
    members[0]["oid"] = oid.hex()[:-2] + "\0a"
    malformed = {**valid, column: json.dumps(members)}
    with pytest.raises(JsonContractError):
        validate_record(db, "git_acquisition_publications", malformed)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO git_acquisition_publications VALUES(?,?,?,?)",
            tuple(malformed.values()),
        )
    db.execute(
        "INSERT INTO git_acquisition_publications VALUES(?,?,?,?)",
        tuple(valid.values()),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_missing_authored_target_stages_reopens_and_promotes_without_new_identity(
    facts, tmp_path, reverse
):
    db, owner, _ = facts
    name = insert_name(
        db, owner, {"nested": {"document_observation_uuidv4": owner["observation"]}}
    )
    unit = Graph(db).export(owner["repository"])
    target = sqlite3.connect(tmp_path / "receiver.db", isolation_level=None)
    target.executescript(schema_sql())
    early = copy.deepcopy(unit)
    early["records"] = [
        r for r in early["records"] if r["table"] != "document_observations"
    ]
    if reverse:
        early["records"].reverse()
    assert receive(target, early)["staged_records"] > 0
    assert not target.execute(
        "SELECT 1 FROM repository_name_observations WHERE repository_name_observation_uuidv4=?",
        (name,),
    ).fetchone()
    target.close()
    target = sqlite3.connect(tmp_path / "receiver.db", isolation_level=None)
    target.execute("PRAGMA foreign_keys=ON")
    target.execute("PRAGMA recursive_triggers=ON")
    if reverse:
        unit["records"].reverse()
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute(
        "SELECT repository_name_observation_uuidv4 FROM repository_name_observations"
    ).fetchall() == [(name,)]
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute(
        "SELECT count(*) FROM repository_name_observations"
    ).fetchone() == (1,)
    target.close()
