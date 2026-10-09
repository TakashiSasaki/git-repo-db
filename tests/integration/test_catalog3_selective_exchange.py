"""Selective fetch closure, exact completeness, boundedness and convergence."""

import copy
import hashlib
import json
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.cas_integrity import diagnose_corruption
from repo_catalog.adapters.sqlite.coverage import freeze_complete_proof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_cas_integrity import corrupt
from tests.integration.test_catalog3_exchange import (
    complete_collection,
    fixture,
    receive,
    uid,
)
from tests.integration.test_catalog3_exchange import (
    databases as databases,
)
from tests.integration.test_catalog3_exchange_integrity_audit import pr_observation
from tests.support.github_runtime import github_runtime as github_runtime


def history(db, *, count=3):
    expected = fixture(db, body=b"F0")
    first = db.execute(
        "SELECT fetch_collection_id FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
        (expected["fetch"],),
    ).fetchone()[0]
    model = ParserModel(db)
    fetches, results, observations = (
        [expected["fetch"]],
        [expected["result"]],
        [expected["observation"]],
    )
    for ordinal in range(1, count):
        fetch_uuid = uid()
        ref = intern_payload(db, f"F{ordinal}".encode(), representation="decoded_api")
        local = db.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,observed_at_us,parsed_at_us) VALUES(?,?,?,?,?,?,'{}',?,0)",
            (
                fetch_uuid,
                expected["repository"],
                first,
                ordinal,
                *ref.parameters(),
                ordinal,
            ),
        ).lastrowid
        result = model.create_result(
            expected["profile"],
            repository_uuidv4=expected["repository"],
            inputs=[{"fetch_occurrence_uuidv4": fetch_uuid}],
        )
        text = f"text-{ordinal}"
        digest = hashlib.sha256(text.encode()).digest()
        db.execute(
            "INSERT INTO text_bodies(body,byte_length,sha256) VALUES(?,?,?)",
            (text, len(text), digest),
        )
        observation = uid()
        db.execute(
            "INSERT INTO document_observations(document_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at_us,parsed_at_us,fetch_occurrence_id,metadata) VALUES(?,?,?,?,'comment','1',?,?,0,?,'{}')",
            (
                observation,
                result,
                expected["repository"],
                expected["cr"],
                digest,
                ordinal,
                local,
            ),
        )
        model.publish_result(result)
        fetches.append(fetch_uuid)
        results.append(result)
        observations.append(observation)
    return expected, first, fetches, results, observations


def portable_state(db, repository):
    return [
        (record["key"], record["values"], record.get("requires"))
        for record in Graph(db).export(repository)["records"]
    ]


@pytest.mark.parametrize("order", [(1, 0, 2), (2, 1, 0)])
def test_f0_f1_f2_arrival_reopen_repeat_and_full_convergence(tmp_path, order):
    source = sqlite3.connect(":memory:", isolation_level=None)
    source.executescript(schema_sql())
    expected, collection, fetches, results, _ = history(source)
    complete_collection(source, fetches[2])
    scope = uid()
    source.execute(
        "INSERT INTO coverage_scopes VALUES(?,?,?,'comment')",
        (scope, expected["repository"], expected["cr"]),
    )
    source.execute(
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES(?,'complete',2,?)",
        (
            scope,
            freeze_complete_proof(
                source, 2, json.dumps({"fetch_collection_ids": [collection]})
            ),
        ),
    )
    full = Graph(source).export(expected["repository"])
    units = [
        Graph(source).export(
            expected["repository"], fetch_occurrence_uuidv4s=[fetch_uuid]
        )
        for fetch_uuid in fetches
    ]
    unit = units[1]
    assert {
        r["values"]["fetch_occurrence_uuidv4"]
        for r in unit["records"]
        if r["table"] == "fetch_occurrences"
    } == {fetches[1]}
    assert {
        r["values"]["parsed_result_uuidv4"]
        for r in unit["records"]
        if r["table"] == "parsed_results"
    } == {results[1]}
    assert not {"completion_markers", "coverage_claims"} & {
        r["table"] for r in unit["records"]
    }
    receiver_path = tmp_path / "receiver.db"
    receiver = sqlite3.connect(receiver_path, isolation_level=None)
    receiver.executescript(schema_sql())
    for ordinal in order:
        reverse = copy.deepcopy(units[ordinal])
        reverse["records"].reverse()
        receive(receiver, reverse)
        receiver.close()
        receiver = sqlite3.connect(receiver_path, isolation_level=None)
        receiver.execute("PRAGMA foreign_keys=ON")
        receiver.execute("PRAGMA recursive_triggers=ON")
        assert receive(receiver, units[ordinal])["received_records"] == 0
        assert receiver.execute(
            "SELECT fetch_occurrence_uuidv4 FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
            (fetches[ordinal],),
        ).fetchone() == (fetches[ordinal],)
    assert receiver.execute("SELECT count(*) FROM coverage_claims").fetchone() == (0,)
    assert receive(receiver, full)["staged_records"] == 0
    assert receiver.execute(
        "SELECT coverage_state FROM current_coverage"
    ).fetchone() == ("complete",)
    direct = sqlite3.connect(":memory:", isolation_level=None)
    direct.executescript(schema_sql())
    assert receive(direct, full)["staged_records"] == 0
    assert portable_state(receiver, expected["repository"]) == portable_state(
        direct, expected["repository"]
    )
    assert receiver.execute(
        "SELECT count(*) FROM local_parser_profile_verification_trust"
    ).fetchone() == (0,)
    assert receiver.execute("SELECT settings FROM sources").fetchone() == (None,)
    assert receiver.execute("PRAGMA foreign_key_check").fetchall() == []
    receiver.close()
    direct.close()
    source.close()


def test_collection_and_explicit_fetch_subset_exact_proof(databases):
    source, target = databases
    expected, collection, fetches, _, _ = history(source)
    complete_collection(source, fetches[2])
    scope = uid()
    source.execute(
        "INSERT INTO coverage_scopes VALUES(?,?,?,'comment')",
        (scope, expected["repository"], expected["cr"]),
    )
    source.execute(
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES(?,'complete',2,?)",
        (
            scope,
            freeze_complete_proof(
                source, 2, json.dumps({"fetch_collection_ids": [collection]})
            ),
        ),
    )
    subset = Graph(source).export(
        expected["repository"],
        fetch_collection_id=collection,
        fetch_occurrence_uuidv4s=fetches[1:],
    )
    assert not {"completion_markers", "coverage_claims"} & {
        r["table"] for r in subset["records"]
    }
    full_collection = Graph(source).export(
        expected["repository"], fetch_collection_id=collection
    )
    assert (
        len(
            [r for r in full_collection["records"] if r["table"] == "fetch_occurrences"]
        )
        == 3
    )
    assert (
        len([r for r in full_collection["records"] if r["table"] == "coverage_claims"])
        == 1
    )
    assert receive(target, full_collection)["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM completion_markers").fetchone() == (1,)
    with pytest.raises(CatalogError):
        Graph(source).export(
            expected["repository"],
            fetch_collection_id=collection,
            fetch_occurrence_uuidv4s=[uid()],
        )


def test_selective_304_closes_original_without_sibling_fetch(databases):
    source, target = databases
    expected, _, fetches, results, _ = history(source)
    observation_uuid, _, acquisition = pr_observation(source, expected)
    original_result = source.execute(
        "SELECT parsed_result_uuidv4 FROM change_request_observations WHERE change_request_observation_uuidv4=?",
        (observation_uuid,),
    ).fetchone()[0]
    # Synthetic request evidence is immutable and names its exact saved original.
    source.execute("DROP TRIGGER fetch_occurrences_immutable")
    request = {
        "status": 304,
        "change_request_observation_uuidv4": observation_uuid,
        "parsed_result_uuidv4": original_result,
        "fetch_occurrence_uuidv4": fetches[0],
        "payload": {"representation": acquisition[2], "sha256": acquisition[3].hex()},
    }
    source.execute(
        "UPDATE fetch_occurrences SET request=? WHERE fetch_occurrence_uuidv4=?",
        (json.dumps(request), fetches[1]),
    )
    unit = Graph(source).export(
        expected["repository"], fetch_occurrence_uuidv4s=[fetches[1]]
    )
    assert {
        r["values"]["fetch_occurrence_uuidv4"]
        for r in unit["records"]
        if r["table"] == "fetch_occurrences"
    } == set(fetches[:2])
    assert fetches[2] not in json.dumps(unit)
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM validators").fetchone() == (0,)
    assert target.execute(
        "SELECT parsed_result_uuidv4 FROM parsed_results WHERE parsed_result_uuidv4=?",
        (results[1],),
    ).fetchone() == (results[1],)


def test_selected_result_closes_all_inputs_and_output_publication(databases):
    source, target = databases
    expected, _, fetches, _, _ = history(source)
    model = ParserModel(source)
    result = model.create_result(
        expected["profile"],
        repository_uuidv4=expected["repository"],
        inputs=[{"fetch_occurrence_uuidv4": value} for value in fetches[:2]],
    )
    model.publish_result(result)
    unit = Graph(source).export(
        expected["repository"], fetch_occurrence_uuidv4s=[fetches[1]]
    )
    assert {
        r["values"]["fetch_occurrence_uuidv4"]
        for r in unit["records"]
        if r["table"] == "fetch_occurrences"
    } == set(fetches[:2])
    early = dict(
        unit,
        records=[r for r in unit["records"] if r["table"] != "document_observations"],
    )
    assert receive(target, early)["staged_records"] > 0
    assert target.execute(
        "SELECT count(*) FROM parsed_result_publications WHERE json_array_length(fact_manifest_json)>0"
    ).fetchone() == (0,)
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute(
        "SELECT declared_input_count FROM parsed_result_publications WHERE parsed_result_uuidv4=?",
        (result,),
    ).fetchone() == (2,)


def test_selective_export_bounded_and_ignores_unrelated_corruption(databases):
    source, target = databases
    expected, collection, fetches, _, _ = history(source)
    for ordinal in range(3, 503):
        ref = intern_payload(
            source, f"unrelated-{ordinal}".encode(), representation="decoded_api"
        )
        source.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,observed_at_us,parsed_at_us) VALUES(?,?,?,?,?,?,'{}',?,0)",
            (
                uid(),
                expected["repository"],
                collection,
                ordinal,
                *ref.parameters(),
                ordinal,
            ),
        )
    unrelated = source.execute(
        "SELECT payload_sha256 FROM fetch_occurrences WHERE ordinal=502"
    ).fetchone()[0]
    corrupt(source, unrelated, b"corrupt")
    diagnose_corruption(source, unrelated)
    statements = []
    source.set_trace_callback(statements.append)
    unit = Graph(source).export(
        expected["repository"], fetch_occurrence_uuidv4s=[fetches[1]]
    )
    source.set_trace_callback(None)
    assert len(unit["records"]) < 30
    assert len([r for r in unit["records"] if r["table"] == "stored_bytes"]) == 1
    assert not any(
        'SELECT * FROM "fetch_occurrences"' in sql and "WHERE" not in sql
        for sql in statements
    )
    assert receive(target, unit)["staged_records"] == 0
    selected = source.execute(
        "SELECT payload_sha256 FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
        (fetches[1],),
    ).fetchone()[0]
    corrupt(source, selected, b"corrupt")
    with pytest.raises(CatalogError, match="corrupt"):
        Graph(source).export(
            expected["repository"], fetch_occurrence_uuidv4s=[fetches[1]]
        )


def test_exact_manifest_cannot_be_replaced_by_unrelated_owner(databases):
    source, target = databases
    expected, collection, fetches, _, _ = history(source)
    complete_collection(source, fetches[2])
    scope = uid()
    source.execute(
        "INSERT INTO coverage_scopes VALUES(?,?,?,'comment')",
        (scope, expected["repository"], expected["cr"]),
    )
    source.execute(
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES(?,'complete',2,?)",
        (
            scope,
            freeze_complete_proof(
                source, 2, json.dumps({"fetch_collection_ids": [collection]})
            ),
        ),
    )
    unit = Graph(source).export(expected["repository"])
    owner = next(r["key"] for r in unit["records"] if r["table"] == "repositories")
    for record in unit["records"]:
        if record["table"] == "coverage_claims":
            record["requires"] = [owner]
    assert receive(target, unit)["staged_records"] > 0
    assert target.execute("SELECT count(*) FROM coverage_claims").fetchone() == (0,)
    assert target.execute(
        "SELECT reason FROM exchange_staging WHERE table_name='coverage_claims'"
    ).fetchone() == ("invalid:completeness_manifest",)


def test_empty_304_collection_selects_boundary_and_exact_original(databases):
    source, target = databases
    expected, collection, fetches, _, _ = history(source)
    observation, _, acquisition = pr_observation(source, expected)
    result = source.execute(
        "SELECT parsed_result_uuidv4 FROM change_request_observations WHERE change_request_observation_uuidv4=?",
        (observation,),
    ).fetchone()[0]
    validation_collection, scope = uid(), uid()
    source.execute(
        "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,source_id,request_context,parser_version,profile_version,confidence) SELECT ?,repository_uuidv4,source_id,'{}','parser','profile','proven' FROM fetch_collections WHERE fetch_collection_id=?",
        (scope, collection),
    )
    source.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,source_id,kind,resume_scope_id) SELECT ?,repository_uuidv4,change_request_id,source_id,'pr-detail',? FROM fetch_collections WHERE fetch_collection_id=?",
        (validation_collection, scope, collection),
    )
    evidence = {
        "status": 304,
        "fetch_occurrence_uuidv4s": [],
        "change_request_observation_uuidv4": observation,
        "parsed_result_uuidv4": result,
        "fetch_occurrence_uuidv4": fetches[0],
        "payload": {"representation": acquisition[2], "sha256": acquisition[3].hex()},
    }
    source.execute(
        "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,3)",
        (scope, validation_collection, json.dumps(evidence)),
    )
    unit = Graph(source).export(
        expected["repository"], fetch_collection_id=validation_collection
    )
    assert {
        r["values"]["fetch_occurrence_uuidv4"]
        for r in unit["records"]
        if r["table"] == "fetch_occurrences"
    } == {fetches[0]}
    assert len([r for r in unit["records"] if r["table"] == "completion_markers"]) == 1
    assert receive(target, unit)["staged_records"] == 0
    assert target.execute("SELECT count(*) FROM fetch_occurrences").fetchone() == (1,)
    assert target.execute("SELECT count(*) FROM validators").fetchone() == (0,)


@pytest.mark.parametrize("first_variant", [False, True])
def test_conflicting_completion_marker_blocks_coverage_in_both_orders(
    databases, first_variant
):
    source, target = databases
    expected, collection, fetches, _, _ = history(source)
    complete_collection(source, fetches[2])
    scope = uid()
    source.execute(
        "INSERT INTO coverage_scopes VALUES(?,?,?,'comment')",
        (scope, expected["repository"], expected["cr"]),
    )
    details = freeze_complete_proof(
        source, 2, json.dumps({"fetch_collection_ids": [collection]})
    )
    source.execute(
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES(?,'complete',2,?)",
        (scope, details),
    )
    original = Graph(source).export(expected["repository"])
    variant = copy.deepcopy(original)
    marker = next(r for r in variant["records"] if r["table"] == "completion_markers")
    marker["values"]["evidence"] = json.dumps(
        {
            **json.loads(marker["values"]["evidence"]),
            "hint": "conflicting immutable content",
        }
    )
    ordered = [variant, original] if first_variant else [original, variant]
    assert receive(target, ordered[0])["staged_records"] == 0
    assert target.execute("SELECT coverage_state FROM current_coverage").fetchone() == (
        "complete",
    )
    assert receive(target, ordered[1])["staged_records"] == 1
    assert target.execute("SELECT coverage_state FROM current_coverage").fetchone() == (
        "conflict",
    )
    assert target.execute("SELECT coverage_state FROM coverage_claims").fetchone() == (
        "complete",
    )
    assert target.execute(
        "SELECT count(*) FROM exchange_blocked_coverage_claims"
    ).fetchone() == (1,)


def test_partial_dag_preserves_external_heads_as_unresolved(databases):
    source, target = databases
    expected, _, fetches, results, _ = history(source)
    model = ParserModel(source)
    # Two immutable children of the original decision are an explicit fork.
    predecessor = source.execute(
        "SELECT fact_selection_decision_uuidv4 FROM fact_selection_decisions"
    ).fetchone()[0]
    for result in results[1:]:
        model.select_fact(
            result,
            fact_kind="comment",
            change_request_id=expected["cr"],
            kind="comment",
            provider_change_request_document_id="1",
            predecessors=[predecessor],
        )
    unit = Graph(source).export(
        expected["repository"], fetch_occurrence_uuidv4s=[fetches[1]]
    )
    assert {
        r["values"]["fetch_occurrence_uuidv4"]
        for r in unit["records"]
        if r["table"] == "fetch_occurrences"
    } == {fetches[1]}
    assert receive(target, unit)["staged_records"] > 0
    ParserModel(target).trust_verification(expected["verification"])
    assert target.execute(
        "SELECT count(*) FROM current_document_observations"
    ).fetchone() == (0,)
    for fetch_uuid in (fetches[0], fetches[2]):
        receive(
            target,
            Graph(source).export(
                expected["repository"], fetch_occurrence_uuidv4s=[fetch_uuid]
            ),
        )
    assert target.execute("SELECT count(*) FROM exchange_staging").fetchone() == (0,)
    assert target.execute(
        "SELECT count(*) FROM current_document_observations"
    ).fetchone() == (0,)
    assert (
        len(
            target.execute("SELECT parsed_result_uuidv4 FROM parsed_results").fetchall()
        )
        == 3
    )


@pytest.mark.parametrize("reply_count", [1, 101])
def test_production_github_complete_proofs_cover_the_asserted_scope(
    github_runtime, reply_count
):
    from tests.support.github_runtime import sync

    store, repo, _, api = github_runtime
    api.etag = True
    api.reply_count = reply_count
    sync(store, repo)
    sync(store, repo)
    graph = Graph(store.connection)
    claims = graph.rows("coverage_claims")
    complete = [claim for claim in claims if claim["coverage_state"] == "complete"]
    missing = [
        (
            graph.lookup(
                "coverage_scopes", ("coverage_scope_id",), (claim["coverage_scope_id"],)
            )["kind"],
            json.loads(claim["details_json"] or "{}"),
        )
        for claim in complete
        if graph.proof_requirements("coverage_claims", claim) is None
    ]
    diagnostics = []
    for kind, details in missing:
        for result in details.get("parsed_result_uuidv4s", []):
            observation = graph.matching(
                "code_observations",
                ("parsed_result_uuidv4", "state"),
                (result, "complete"),
            )[0]
            code = graph.code_proof(
                result, repo["repository_uuidv4"], observation["change_request_id"]
            )
            diagnostics.append(
                {
                    "kind": kind,
                    "request": observation["change_request_id"],
                    "code_valid": code is not None,
                    "missing_listing_collections": sorted(
                        code["collections"] - set(details["fetch_collection_ids"])
                    )
                    if code
                    else [],
                }
            )
    assert not missing, diagnostics or missing
    unit = graph.export(repo["repository_uuidv4"])
    assert len(
        [
            record
            for record in unit["records"]
            if record["table"] == "coverage_claims"
            and record["values"]["coverage_state"] == "complete"
        ]
    ) == len(complete)
    from repo_catalog.adapters.sqlite.store import Store
    from repo_catalog.application.maintenance_service import MaintenanceService
    from repo_catalog.application.query_service import QueryService

    receiver_state = store.path.parent / "receiver"
    MaintenanceService(receiver_state).init("catalog-text-v1", 64 * 1024 * 1024, 0)
    with Store(receiver_state) as received:
        receiver = received.connection
        with received.transaction():
            outcome = Graph(receiver).receive(unit)
            received.publish()
        assert outcome["staged_records"] == 0, receiver.execute(
            "SELECT table_name,reason,count(*) FROM exchange_staging GROUP BY table_name,reason"
        ).fetchall()
        assert (
            receiver.execute(
                "SELECT count(*) FROM code_listing_progress WHERE state='complete'"
            ).fetchone()[0]
            == 0
        )
        assert (
            receiver.execute(
                "SELECT count(*) FROM current_code_observations"
            ).fetchone()[0]
            == 0
        )
        with received.transaction():
            model = ParserModel(receiver)
            for trusted in store.all(
                "SELECT parser_profile_verification_uuidv4 FROM local_parser_profile_verification_trust WHERE trusted=1"
            ):
                if received.one(
                    "SELECT 1 FROM parser_profile_verifications WHERE parser_profile_verification_uuidv4=?",
                    (trusted[0],),
                ):
                    model.trust_verification(trusted[0])
            received.publish()
        source_code = {
            tuple(row)
            for row in store.all(
                "SELECT code_observation_uuidv4,parsed_result_uuidv4,state FROM current_code_observations"
            )
        }
        receiver_code = {
            tuple(row)
            for row in received.all(
                "SELECT code_observation_uuidv4,parsed_result_uuidv4,state FROM current_code_observations"
            )
        }
        assert receiver_code == source_code
        assert len(receiver_code) == 3

    def portable_query(value):
        """Compare domain state without local handles or receiver-local checks."""
        if isinstance(value, list):
            return [portable_query(item) for item in value]
        if isinstance(value, dict):
            return {
                key: portable_query(item)
                for key, item in value.items()
                if key not in {"source_id", "last_checked_at_us"}
                and not (key.endswith("_id") and type(item) is int)
            }
        return value

    options = {"repo": repo["repository_uuidv4"], "provider_change_request_number": 41}
    source_result = QueryService(store.path).query("pr show", options)
    received_result = QueryService(receiver_state).query("pr show", options)
    assert received_result.status == source_result.status == "complete", {
        "source_status": source_result.status,
        "source_gaps": source_result.coverage.missing,
        "receiver_status": received_result.status,
        "receiver_gaps": received_result.coverage.missing,
    }
    assert portable_query(received_result.data["items"]) == portable_query(
        source_result.data["items"]
    )
    thread_options = {**options, "provider_resource_id": "THREAD41-0"}
    source_thread = QueryService(store.path).query("pr thread", thread_options)
    received_thread = QueryService(receiver_state).query("pr thread", thread_options)
    assert received_thread.status == source_thread.status == "complete", {
        "source": source_thread.coverage.missing,
        "receiver": received_thread.coverage.missing,
    }
    # A successful live check belongs to the catalog that performed it.
    # Imported thread bodies and capture evidence remain portable; importing
    # them cannot assert that this receiver contacted the provider.
    assert all(
        type(item["last_checked_at_us"]) is int
        and item["last_checked_at_us"] >= item["observed_at_us"]
        for item in source_thread.data["items"]
    )
    assert all(
        item["last_checked_at_us"] is None for item in received_thread.data["items"]
    )
    assert portable_query(received_thread.data["items"]) == portable_query(
        source_thread.data["items"]
    )
