"""Original-only exchange is absent; retained domain proof remains portable."""

import base64
import hashlib
import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.exchange import (
    FORMAT,
    Graph,
    canonical,
    encode,
    record_digest,
)
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.exchange_service import ExchangeService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_exchange import (
    complete_collection,
    fixture,
    receive,
    uid,
)
from tests.integration.test_catalog3_exchange import databases as databases

MARKER = "PHASE1_ORPHAN_TRANSPORT_ONLY_085148213"
ORIGINAL = json.dumps({"transport_only": MARKER}).encode()
ENCODED = base64.b64encode(ORIGINAL).decode()


def bare_fetch_fixture(db):
    """Create one API fetch with no published facts to justify its body."""
    repository, service, registration, binding, request, scope, collection, fetch = (
        uid() for _ in range(8)
    )
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'repo','{}')",
        (repository,),
    )
    db.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','github','{}')",
        (service,),
    )
    db.execute(
        "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('source',?,?,'github_inventory','Remote name','{}')",
        (registration, service),
    )
    db.execute(
        "INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES('source',?)",
        (repository,),
    )
    db.execute(
        "INSERT INTO repository_bindings VALUES(?,?,?,?,'{}',0)",
        (binding, repository, service, repository),
    )
    db.execute(
        "INSERT INTO change_requests VALUES(?,?,?,'pull_request',1)",
        (request, repository, binding),
    )
    db.execute(
        "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,source_id,request_context,parser_version,profile_version,confidence) VALUES(?,?, 'source','{}','parser','profile','proven')",
        (scope, repository),
    )
    db.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,source_id,kind,resume_scope_id) VALUES(?,?,?,'source','comments',?)",
        (collection, repository, request, scope),
    )
    ref = intern_payload(db, ORIGINAL, representation="decoded_api")
    db.execute(
        "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,observed_at_us,parsed_at_us) VALUES(?,?,?,0,?,?,'{}',-1,0)",
        (fetch, repository, collection, *ref.parameters()),
    )
    return {"repository": repository, "fetch": fetch}


def adversarial_record(db, table, row):
    """Construct a wire attack without using the guarded production encoder."""
    graph = Graph(db, persist_identities=False)
    values = {column: encode(value, column) for column, value in row.items()}
    primary = graph.keys[table]
    if (
        len(primary) == 1
        and graph.columns[table][primary[0]] == "INTEGER"
        and not any(primary[0] in foreign[1] for foreign in graph.foreign[table])
    ):
        values.pop(primary[0])
    for parent, children, columns in graph.foreign[table]:
        if any(row.get(column) is None for column in children):
            continue
        target = graph.lookup(
            parent, columns, tuple(row[column] for column in children)
        )
        if target is not None:
            for child, column in zip(children, columns):
                values[child] = {"$ref": graph.key(parent, target), "column": column}
    return {"key": graph.key(table, row), "table": table, "values": values}


def original_records(db, expected=None, *, representation="decoded_api"):
    ref = intern_payload(db, ORIGINAL, representation=representation)
    graph = Graph(db, persist_identities=False)
    rows = [
        ("stored_bytes", graph.lookup("stored_bytes", ("sha256",), (ref.sha256,))),
        (
            "payloads",
            graph.lookup("payloads", ("representation", "sha256"), ref.parameters()),
        ),
    ]
    if expected is not None:
        prior = db.execute(
            "SELECT fetch_collection_id FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
            (expected["fetch"],),
        ).fetchone()[0]
        fetch = uid()
        db.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,observed_at_us,parsed_at_us) VALUES(?,?,?,1,?,?,'{}',2,2)",
            (fetch, expected["repository"], prior, *ref.parameters()),
        )
        rows.append(
            (
                "fetch_occurrences",
                graph.lookup(
                    "fetch_occurrences", ("fetch_occurrence_uuidv4",), (fetch,)
                ),
            )
        )
    return rows, [adversarial_record(db, table, row) for table, row in rows]


def unit(records, repository=None):
    return {
        "format": FORMAT,
        "repository_uuidv4": repository or uid(),
        "origin_catalog_uuidv4": uid(),
        "records": records,
    }


def stage_records(db, incoming):
    for record in incoming["records"]:
        db.execute(
            "INSERT INTO exchange_staging VALUES(?,?,?,?,?,?,?)",
            (
                record["key"],
                record_digest(record),
                record["table"],
                incoming["repository_uuidv4"],
                incoming["origin_catalog_uuidv4"],
                canonical(record),
                "missing_dependency",
            ),
        )


def assert_no_original(db):
    dumped = "\n".join(db.iterdump())
    assert MARKER not in dumped
    assert ENCODED not in dumped
    assert (
        db.execute(
            "SELECT count(*) FROM stored_bytes WHERE sha256=?",
            (hashlib.sha256(ORIGINAL).digest(),),
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize(
    "representation", ["decoded_api", "legacy_normalized", "git-object-raw-v1"]
)
def test_original_only_units_do_not_enter_storage_or_json_envelopes(
    databases, representation
):
    source, target = databases
    _, records = original_records(source, representation=representation)
    outcome = receive(target, unit(records))
    assert outcome["rejected_records"] == 2
    assert outcome["received_records"] == outcome["admitted_records"] == 0
    assert outcome["staged_records"] == 0
    assert_no_original(target)
    for table in (
        "stored_bytes",
        "payloads",
        "exchange_admissions",
        "exchange_local_identities",
    ):
        assert target.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


def test_original_encoder_and_explicit_fetch_selector_have_no_side_effects(databases):
    source, _ = databases
    expected = fixture(source)
    rows, _ = original_records(source, expected)
    before = "\n".join(source.iterdump())
    for table, row in rows:
        with pytest.raises(CatalogError) as rejected:
            Graph(source).record(table, row)
        assert rejected.value.code == "RETIRED_API_ORIGINAL_EXCHANGE"
    orphan = rows[-1][1]["fetch_occurrence_uuidv4"]
    with pytest.raises(CatalogError) as rejected:
        Graph(source).export(expected["repository"], fetch_occurrence_uuidv4s=[orphan])
    assert rejected.value.code == "RETIRED_API_ORIGINAL_EXCHANGE"
    assert "\n".join(source.iterdump()) == before


def test_full_and_collection_export_omit_unreferenced_originals(databases):
    source, target = databases
    expected = fixture(source)
    rows, _ = original_records(source, expected)
    collection = rows[-1][1]["fetch_collection_id"]
    for options in ({}, {"fetch_collection_id": collection}):
        exported = Graph(source).export(expected["repository"], **options)
        assert ENCODED not in canonical(exported)
        assert MARKER not in canonical(exported)
        assert receive(target, exported)["rejected_records"] == 0
        assert_no_original(target)
    assert target.execute("SELECT count(*) FROM document_observations").fetchone() == (
        1,
    )


def test_disconnected_empty_parser_publication_cannot_confer_archive_retention(
    databases,
):
    source, target = databases
    expected = fixture(source)
    rows, originals = original_records(source, expected)
    orphan = rows[-1][1]["fetch_occurrence_uuidv4"]
    model = ParserModel(source)
    parsed = model.create_result(
        expected["profile"],
        repository_uuidv4=expected["repository"],
        inputs=[{"fetch_occurrence_uuidv4": orphan}],
    )
    model.publish_result(parsed)
    exported = Graph(source).export(expected["repository"])
    exported["records"].extend(originals)
    outcome = receive(target, exported)
    assert outcome["rejected_records"] == 3
    assert_no_original(target)
    assert target.execute("SELECT count(*) FROM document_observations").fetchone() == (
        1,
    )


def test_delayed_required_bytes_satisfy_retained_domain_staging(databases):
    source, target = databases
    expected = fixture(source)
    exported = Graph(source).export(expected["repository"])
    body = [
        record for record in exported["records"] if record["table"] == "stored_bytes"
    ]
    domain = dict(
        exported,
        records=[
            record
            for record in exported["records"]
            if record["table"] != "stored_bytes"
        ],
    )
    assert receive(target, domain)["rejected_records"] == 0
    assert target.execute("SELECT count(*) FROM stored_bytes").fetchone() == (0,)
    assert receive(target, dict(exported, records=body))["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM document_observations").fetchone() == (
        1,
    )
    assert receive(target, exported)["received_records"] == 0


@pytest.mark.parametrize("direct", [False, True])
def test_direct_admission_and_pending_promotion_do_not_restore_original_intake(
    databases, direct
):
    source, target = databases
    _, records = original_records(source)
    incoming = unit(records)
    graph = Graph(target)
    if direct:
        for record in records:
            assert (
                graph._admit(
                    record,
                    incoming["origin_catalog_uuidv4"],
                    incoming["repository_uuidv4"],
                )
                == "invalid:retired_api_original"
            )
    else:
        stage_records(target, incoming)
        assert graph.promote(incoming["origin_catalog_uuidv4"]) == 0
    assert target.execute("SELECT count(*) FROM exchange_staging").fetchone() == (0,)
    assert_no_original(target)


def test_partial_reason_marker_cannot_authorize_originals(databases):
    source, target = databases
    expected = fixture(source)
    rows, originals = original_records(source, expected)
    collection = rows[-1][1]["fetch_collection_id"]
    marker = source.execute(
        "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) SELECT resume_scope_id,fetch_collection_id,'partial','{\"reason\":\"API_SCHEMA\"}',2 FROM fetch_collections WHERE fetch_collection_id=? RETURNING completion_marker_id",
        (collection,),
    ).fetchone()[0]
    graph = Graph(source)
    record = graph.record(
        "completion_markers",
        graph.lookup("completion_markers", ("completion_marker_id",), (marker,)),
    )
    exported = graph.export(expected["repository"])
    exported["records"].extend(originals)
    assert record in exported["records"]
    assert receive(target, exported)["rejected_records"] == 3
    assert_no_original(target)


def test_advisory_requires_cannot_attach_unrelated_original_to_valid_proof(databases):
    source, target = databases
    expected = fixture(source)
    complete_collection(source, expected["fetch"])
    exported = Graph(source).export(expected["repository"])
    _, originals = original_records(source, expected)
    marker = next(
        record
        for record in exported["records"]
        if record["table"] == "completion_markers"
    )
    marker["requires"].append(originals[-1]["key"])
    exported["records"].extend(originals)
    assert receive(target, exported)["rejected_records"] == 3
    assert_no_original(target)


@pytest.mark.parametrize(
    "manifest",
    [
        [{}],
        [{"table": "payloads", "key": ["original"]}],
        [{"table": "document_observations", "key": {"original": True}}],
    ],
)
def test_malformed_publication_manifest_cannot_authorize_originals(databases, manifest):
    source, target = databases
    expected = fixture(source)
    rows, originals = original_records(source, expected)
    parsed = ParserModel(source).create_result(
        expected["profile"],
        repository_uuidv4=expected["repository"],
        inputs=[{"fetch_occurrence_uuidv4": rows[-1][1]["fetch_occurrence_uuidv4"]}],
    )
    ParserModel(source).publish_result(parsed)
    exported = Graph(source).export(expected["repository"])
    publication = next(
        record
        for record in exported["records"]
        if record["table"] == "parsed_result_publications"
        and record["values"]["parsed_result_uuidv4"]["$ref"].endswith(
            canonical({"parsed_result_uuidv4": parsed})
        )
    )
    publication["values"]["fact_manifest_json"] = json.dumps(manifest)
    exported["records"].extend(originals)
    assert receive(target, exported)["rejected_records"] == 3
    assert_no_original(target)


def test_publication_for_missing_fact_cannot_retain_its_input(databases):
    source, target = databases
    expected = fixture(source)
    rows, originals = original_records(source, expected)
    parsed = ParserModel(source).create_result(
        expected["profile"],
        repository_uuidv4=expected["repository"],
        inputs=[{"fetch_occurrence_uuidv4": rows[-1][1]["fetch_occurrence_uuidv4"]}],
    )
    ParserModel(source).publish_result(parsed)
    exported = Graph(source).export(expected["repository"])
    publication = next(
        record
        for record in exported["records"]
        if record["table"] == "parsed_result_publications"
        and record["values"]["parsed_result_uuidv4"]["$ref"].endswith(
            canonical({"parsed_result_uuidv4": parsed})
        )
    )
    publication["values"]["fact_manifest_json"] = json.dumps(
        [
            {
                "table": "document_observations",
                "key": ["missing-observation-uuidv4"],
            }
        ]
    )
    exported["records"].extend(originals)
    assert receive(target, exported)["rejected_records"] == 3
    assert_no_original(target)


def test_incomplete_terminal_proof_cannot_retain_input_body(databases):
    source, target = databases
    expected = bare_fetch_fixture(source)
    complete_collection(source, expected["fetch"])
    exported = Graph(source).export(expected["repository"])
    marker = next(
        record
        for record in exported["records"]
        if record["table"] == "completion_markers"
    )
    marker["values"]["observed_at_us"] = 999
    assert receive(target, exported)["rejected_records"] > 0
    assert_no_original(target)


def test_domain_fact_rejected_by_catalog_constraint_cannot_retain_input(databases):
    source, target = databases
    expected = fixture(source)
    exported = Graph(source).export(expected["repository"])
    observation = next(
        record
        for record in exported["records"]
        if record["table"] == "document_observations"
    )
    observation["values"]["deleted"] = 2
    exported["records"] = [
        record
        for record in exported["records"]
        if record["table"]
        not in {
            "parsed_result_publications",
            "parser_profile_selection_decisions",
            "fact_selection_decisions",
        }
    ]
    assert receive(target, exported)["rejected_records"] > 0
    assert_no_original(target)


def test_pending_metadata_reference_cannot_turn_domain_row_into_original_carrier(
    databases,
):
    source, target = databases
    _, originals = original_records(source)
    body = originals[0]
    graph = Graph(target)
    observation = uid()
    values = dict.fromkeys(graph.expected_columns("document_observations"))
    values.update(
        document_observation_uuidv4=observation,
        metadata={"$ref": body["key"], "column": "body"},
    )
    carrier = {
        "key": "document_observations:"
        + canonical({"document_observation_uuidv4": observation}),
        "table": "document_observations",
        "values": values,
    }
    incoming = unit([body, carrier])
    stage_records(target, incoming)
    assert graph.promote(incoming["origin_catalog_uuidv4"]) == 0
    assert_no_original(target)
    assert target.execute("SELECT count(*) FROM exchange_admissions").fetchone() == (0,)
    assert target.execute("SELECT table_name FROM exchange_staging").fetchall() == [
        ("document_observations",)
    ]


def test_known_source_wide_parent_cannot_authorize_pending_api_bytes(databases):
    source, target = databases
    expected = fixture(source, body=ORIGINAL)
    incoming = Graph(source).export(expected["repository"])
    for record in incoming["records"]:
        if record["table"] == "parsed_results":
            record["values"]["owner_kind"] = "source"
            Graph(target).validate_record(record)
    stage_records(target, incoming)
    Graph(target).promote(incoming["origin_catalog_uuidv4"])
    assert_no_original(target)
    body = [r for r in incoming["records"] if r["table"] == "stored_bytes"]
    assert receive(target, dict(incoming, records=body))["rejected_records"] == 1
    assert_no_original(target)
    assert target.execute("SELECT count(*) FROM document_observations").fetchone() == (
        0,
    )


@pytest.mark.parametrize("pending", [False, True])
def test_generic_request_payload_reference_cannot_authorize_unrelated_original(
    databases, pending
):
    source, target = databases
    expected = fixture(source)
    incoming = Graph(source).export(expected["repository"])
    rows, originals = original_records(source)
    fetch = next(r for r in incoming["records"] if r["table"] == "fetch_occurrences")
    fetch["values"]["request"] = json.dumps(
        {
            "payload": {
                "representation": "decoded_api",
                "sha256": rows[0][1]["sha256"].hex(),
            }
        }
    )
    incoming["records"].extend(originals)
    if pending:
        stage_records(target, incoming)
        Graph(target).promote(incoming["origin_catalog_uuidv4"])
    else:
        # The injected request reference has no acquisition under this owner,
        # so it also invalidates the fetch that was otherwise used by the
        # fixture's domain publication. None of those rejected inputs may
        # preserve the original response bytes.
        assert receive(target, incoming)["rejected_records"] == 5
    assert_no_original(target)
    fixture_digest = hashlib.sha256(b'{"body":"hello"}').digest()
    assert target.execute(
        "SELECT count(*) FROM stored_bytes WHERE sha256=?", (fixture_digest,)
    ).fetchone() == (0,)
    assert target.execute("SELECT count(*) FROM fetch_occurrences").fetchone() == (0,)
    assert target.execute("SELECT count(*) FROM document_observations").fetchone() == (
        0,
    )


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("include_object", [False, True])
def test_forged_git_object_cannot_authorize_original_retention(
    databases, pending, include_object
):
    source, target = databases
    rows, records = original_records(source, representation="git-object-raw-v1")
    object_id = source.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'blob',?,1) RETURNING git_object_id",
        (bytes(20), len(ORIGINAL)),
    ).fetchone()[0]
    source.execute(
        "INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)",
        (object_id, rows[0][1]["sha256"]),
    )
    graph = Graph(source, persist_identities=False)
    records.extend(
        adversarial_record(
            source, table, graph.lookup(table, ("git_object_id",), (object_id,))
        )
        for table in (
            ("git_objects", "git_object_payloads")
            if include_object
            else ("git_object_payloads",)
        )
    )
    incoming = unit(records)
    if pending:
        stage_records(target, incoming)
        Graph(target).promote(incoming["origin_catalog_uuidv4"])
    else:
        assert receive(target, incoming)["rejected_records"] == 2
    assert_no_original(target)
    assert target.execute("SELECT count(*) FROM git_object_payloads").fetchone() == (0,)
    with pytest.raises(CatalogError) as rejected:
        Graph(source).record("stored_bytes", rows[0][1])
    assert rejected.value.code == "RETIRED_API_ORIGINAL_EXCHANGE"


@pytest.mark.parametrize(
    "reason",
    ["invalid:payload_corruption", "conflict:payload_corruption", "constraint:body"],
)
def test_failed_api_original_envelopes_are_not_retry_staging(databases, reason):
    source, target = databases
    expected = fixture(source, body=ORIGINAL)
    incoming = Graph(source).export(expected["repository"])
    stage_records(target, incoming)
    target.execute(
        "UPDATE exchange_staging SET reason=? WHERE table_name='stored_bytes'",
        (reason,),
    )
    Graph(target).promote(incoming["origin_catalog_uuidv4"])
    assert_no_original(target)
    assert target.execute("SELECT count(*) FROM document_observations").fetchone() == (
        0,
    )


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("forged_local_git", [False, True])
def test_corrupt_api_proof_intake_never_retains_rejected_original_envelope(
    databases, pending, forged_local_git
):
    source, target = databases
    expected = fixture(source, body=ORIGINAL)
    incoming = Graph(source).export(expected["repository"])
    digest = hashlib.sha256(ORIGINAL).digest()
    corrupt_body = b"x" * len(ORIGINAL) if forged_local_git else b"corrupt"
    target.execute(
        "INSERT INTO stored_bytes VALUES(?, ?, ?)",
        (digest, corrupt_body, len(corrupt_body)),
    )
    if forged_local_git:
        target.execute("INSERT INTO payloads VALUES('git-object-raw-v1',?)", (digest,))
        object_id = target.execute(
            "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'blob',?,1) RETURNING git_object_id",
            (bytes(20), len(ORIGINAL)),
        ).fetchone()[0]
        target.execute(
            "INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)",
            (object_id, digest),
        )
    if pending:
        stage_records(target, incoming)
        Graph(target).promote(incoming["origin_catalog_uuidv4"])
    else:
        assert receive(target, incoming)["rejected_records"] == 1
    dumped = "\n".join(target.iterdump())
    assert MARKER not in dumped
    assert ENCODED not in dumped
    assert target.execute(
        "SELECT body FROM stored_bytes WHERE sha256=?", (digest,)
    ).fetchone() == (corrupt_body,)
    assert target.execute(
        "SELECT count(*) FROM exchange_admissions WHERE table_name='stored_bytes'"
    ).fetchone() == (0,)
    assert target.execute(
        "SELECT count(*) FROM payload_quarantine WHERE sha256=?", (digest,)
    ).fetchone() == (1,)
    assert target.execute(
        "SELECT reason FROM unresolved_payloads WHERE stored_sha256=?", (digest,)
    ).fetchall() == [("physical_corruption",)]
    assert target.execute("SELECT count(*) FROM document_observations").fetchone() == (
        0,
    )
    assert target.execute("SELECT count(*) FROM exchange_staging").fetchone()[0] > 0


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
@pytest.mark.parametrize("include_object", [False, True])
def test_shared_git_consumer_preserves_rejected_domain_content_staging(
    databases, object_format, include_object
):
    source, target = databases
    expected = fixture(source, body=ORIGINAL)
    ref = intern_payload(source, ORIGINAL, representation="git-object-raw-v1")
    oid = hashlib.new(
        object_format, f"blob {len(ORIGINAL)}\0".encode() + ORIGINAL
    ).digest()
    object_id = source.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES(?,?,'blob',?,1) RETURNING git_object_id",
        (object_format, oid, len(ORIGINAL)),
    ).fetchone()[0]
    source.execute(
        "INSERT INTO git_object_payloads VALUES(?,?,?)", (object_id, *ref.parameters())
    )
    graph = Graph(source)
    incoming = graph.export(expected["repository"])
    for table, columns, values in (
        ("git_objects", ("git_object_id",), (object_id,)),
        ("payloads", ("representation", "sha256"), ref.parameters()),
        ("git_object_payloads", ("git_object_id",), (object_id,)),
    ):
        if table == "git_objects" and not include_object:
            continue
        incoming["records"].append(
            graph.record(table, graph.lookup(table, columns, values))
        )
    target.execute(
        "INSERT INTO stored_bytes VALUES(?,?,?)",
        (ref.sha256, b"corrupt", len(b"corrupt")),
    )
    assert receive(target, incoming)["rejected_records"] == 0
    assert target.execute(
        "SELECT body FROM stored_bytes WHERE sha256=?", (ref.sha256,)
    ).fetchone() == (b"corrupt",)
    assert target.execute(
        "SELECT count(*) FROM exchange_admissions WHERE table_name='stored_bytes'"
    ).fetchone() == (0,)
    staged = target.execute(
        "SELECT record_json FROM exchange_staging WHERE table_name='stored_bytes'"
    ).fetchall()
    assert len(staged) == 1 and ENCODED in staged[0][0]
    if not include_object:
        assert target.execute("SELECT count(*) FROM git_objects").fetchone() == (0,)
        assert target.execute(
            "SELECT count(*) FROM git_object_payloads"
        ).fetchone() == (0,)


def test_valid_git_dependencies_can_arrive_in_separate_units(databases):
    source, target = databases
    rows, records = original_records(source, representation="git-object-raw-v1")
    object_id = source.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'blob',?,1) RETURNING git_object_id",
        (
            hashlib.sha1(f"blob {len(ORIGINAL)}\0".encode() + ORIGINAL).digest(),
            len(ORIGINAL),
        ),
    ).fetchone()[0]
    source.execute(
        "INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)",
        (object_id, rows[0][1]["sha256"]),
    )
    graph = Graph(source)
    obj = graph.record(
        "git_objects", graph.lookup("git_objects", ("git_object_id",), (object_id,))
    )
    mapping = graph.record(
        "git_object_payloads",
        graph.lookup("git_object_payloads", ("git_object_id",), (object_id,)),
    )
    incoming = unit([records[1], mapping])
    assert receive(target, incoming)["rejected_records"] == 0
    assert (
        receive(target, dict(incoming, records=[records[0]]))["rejected_records"] == 0
    )
    assert target.execute("SELECT count(*) FROM git_object_payloads").fetchone() == (0,)
    assert receive(target, dict(incoming, records=[obj]))["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM git_object_payloads").fetchone() == (1,)
    assert target.execute("SELECT body FROM stored_bytes").fetchone() == (ORIGINAL,)


def test_original_only_service_import_keeps_catalog_revision(tmp_path):
    state = tmp_path / "state"
    MaintenanceService(state).init("catalog-text-v1", 33554432, 0)
    source = sqlite3.connect(":memory:")
    source.executescript(schema_sql())
    _, records = original_records(source)
    path = tmp_path / "original.json"
    path.write_text(canonical(unit(records)), encoding="utf-8")
    with Store(state) as store:
        before = store.revision()
    result = ExchangeService(state).import_file(path)
    assert result.data["rejected_records"] == 2
    with Store(state) as store:
        assert store.revision() == before
        assert_no_original(store.connection)
    source.close()


def test_promotion_groups_staged_candidates_before_preflight_scans(databases):
    source, target = databases
    graph = Graph(source, persist_identities=False)
    origins = [uid() for _ in range(24)]
    for index, repository in enumerate(origins):
        body = f"unpublished-api-original-{index}".encode()
        reference = intern_payload(source, body, representation="decoded_api")
        row = graph.lookup("stored_bytes", ("sha256",), (reference.sha256,))
        record = adversarial_record(source, "stored_bytes", row)
        digest = record_digest(record)
        target.execute(
            "INSERT INTO exchange_staging VALUES(?,?,?,?,?,?,?)",
            (
                record["key"],
                digest,
                "stored_bytes",
                repository,
                uid(),
                canonical(record),
                "missing_dependency",
            ),
        )

    statements = []
    target.set_trace_callback(statements.append)
    Graph(target).promote(uid())
    target.set_trace_callback(None)
    repository_scans = [
        statement
        for statement in statements
        if "FROM exchange_staging WHERE repository_uuidv4=" in statement
    ]
    assert repository_scans == []
    assert target.execute("SELECT count(*) FROM exchange_staging").fetchone() == (0,)
    assert target.execute("SELECT count(*) FROM stored_bytes").fetchone() == (0,)
    assert target.execute("SELECT count(*) FROM repositories").fetchone() == (0,)
