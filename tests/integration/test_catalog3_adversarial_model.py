"""Independent attacks on model invariants, bypassing high-level admission."""

import hashlib
import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.cas_integrity import (
    repair_payload,
    stage_verified_payload,
    verify_all,
)
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.payload import PayloadRef


def uid():
    return str(uuid.uuid4())


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@pytest.fixture
def model():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.row_factory = sqlite3.Row
    db.executescript(schema_sql())
    ids = {
        key: uid()
        for key in (
            "service",
            "repo",
            "other",
            "source",
            "source2",
            "profile",
            "verify",
            "scope",
            "fetch",
            "fetch2",
        )
    }
    db.execute(
        "INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','fixture','{}')",
        (ids["service"],),
    )
    for key in ("repo", "other"):
        db.execute(
            "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,?,'{}')",
            (ids[key], key),
        )
    for key in ("source", "source2"):
        db.execute(
            "INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES(?,?,?,'github_inventory',?,NULL)",
            (key, ids[key], ids["service"], key),
        )
    db.execute(
        "INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,provider_repository_id,metadata) VALUES('binding',?,?,'1','{}')",
        (ids["repo"], ids["service"]),
    )
    db.execute(
        "INSERT INTO change_requests(change_request_id,repository_uuidv4,repository_binding_id,change_request_kind,provider_change_request_number) VALUES('cr',?,'binding','pull_request',1)",
        (ids["repo"],),
    )
    db.execute(
        "INSERT INTO documents(change_request_id,kind,provider_change_request_document_id) VALUES('cr','body','1')"
    )
    payload = intern_payload(db, b"{}", representation="decoded_api")
    for fetch, repo in (("fetch", "repo"), ("fetch2", "other")):
        db.execute(
            "INSERT INTO resume_scopes(resume_scope_id,repository_uuidv4,request_context,parser_version,profile_version,confidence) VALUES(?,?,'{}','fixture','fixture','proven')",
            (fetch, ids[repo]),
        )
        db.execute(
            "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,kind,resume_scope_id) VALUES(?,?,'body',?)",
            (fetch, ids[repo], fetch),
        )
        db.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,payload_representation,payload_sha256,request,observed_at_us,parsed_at_us) VALUES(?,?,?,0,?,?,'{}',-1,0)",
            (ids[fetch], ids[repo], fetch, *payload.parameters()),
        )
    definition = {
        "implementation": {"sha256": "a" * 64},
        "settings": {},
        "output_schema": {"type": "object"},
        "capabilities": [
            {"owner_kind": "repository", "fact_kind": "body"},
            {"owner_kind": "source", "fact_kind": "inventory"},
        ],
    }
    db.execute(
        "INSERT INTO parser_profiles VALUES(?,'fixture','fixture',?)",
        (ids["profile"], encoded(definition)),
    )
    for cap in definition["capabilities"]:
        db.execute(
            "INSERT INTO parser_profile_capabilities VALUES(?,?,?)",
            (ids["profile"], cap["owner_kind"], cap["fact_kind"]),
        )
    evidence = {
        "definition": definition,
        "capabilities": [
            {**cap, "outcome": "passed", "checks": ["synthetic-contract"]}
            for cap in definition["capabilities"]
        ],
    }
    db.execute(
        "INSERT INTO parser_profile_verifications VALUES(?,?,'passed','{}',?,0)",
        (ids["verify"], ids["profile"], encoded(evidence)),
    )
    db.execute(
        "INSERT INTO local_parser_profile_verification_trust VALUES(?,1,0,'{}')",
        (ids["verify"],),
    )
    db.execute(
        "INSERT INTO parser_profile_selection_scopes VALUES(?,'repository',?,NULL,NULL,'body')",
        (ids["scope"], ids["repo"]),
    )
    yield db, ids, definition, evidence
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    db.close()


def result(db, ids, *, owner="repo", inputs=None):
    ident = uid()
    inputs = inputs or [{"fetch_occurrence_uuidv4": ids["fetch"]}]
    db.execute(
        "INSERT INTO parsed_results VALUES(?,?,'repository',?,NULL,0,?,'{}')",
        (ident, ids["profile"], ids[owner], encoded(inputs)),
    )
    return ident


def decision(db, ids, *, predecessors=(), publish=True, scope=None):
    ident = uid()
    scope = scope or ids["scope"]
    db.execute(
        "INSERT INTO parser_profile_selection_decisions(selection_decision_uuidv4,selection_scope_uuidv4,owner_kind,fact_kind,parser_profile_uuidv4,parser_profile_verification_uuidv4,predecessor_manifest_json,issuer,decided_at_us) VALUES(?,?,'repository','body',?,?,?,'independent-test',0)",
        (ident, scope, ids["profile"], ids["verify"], encoded(predecessors)),
    )
    for predecessor in predecessors:
        db.execute(
            "INSERT INTO parser_profile_selection_predecessors VALUES(?,?,?)",
            (ident, predecessor, scope),
        )
    if publish:
        db.execute(
            "INSERT INTO parser_profile_selection_publications VALUES(?)", (ident,)
        )
    return ident


def active(db, scope):
    return [
        r[0]
        for r in db.execute(
            "SELECT selection_decision_uuidv4 FROM active_parser_profile_selections WHERE selection_scope_uuidv4=?",
            (scope,),
        )
    ]


def test_published_decision_cannot_gain_predecessor_and_change_its_meaning(model):
    db, ids, _, _ = model
    first = decision(db, ids)
    second = decision(db, ids)
    assert active(db, ids["scope"]) == []
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO parser_profile_selection_predecessors VALUES(?,?,?)",
            (second, first, ids["scope"]),
        )
    assert active(db, ids["scope"]) == []
    merged = decision(db, ids, predecessors=[first, second])
    assert active(db, ids["scope"]) == [merged]


def test_unsealed_decision_blocks_existing_current_until_exact_dependencies_publish(
    model,
):
    db, ids, _, _ = model
    first = decision(db, ids)
    successor = decision(db, ids, predecessors=[first], publish=False)
    assert active(db, ids["scope"]) == []
    db.execute(
        "INSERT INTO parser_profile_selection_publications VALUES(?)", (successor,)
    )
    assert active(db, ids["scope"]) == [successor]


def test_empty_cr_scope_blocks_parent_profile_inheritance(model):
    db, ids, _, _ = model
    decision(db, ids)
    assert (
        db.execute(
            "SELECT parser_profile_uuidv4 FROM effective_change_request_parser_profiles WHERE change_request_id='cr' AND fact_kind='body'"
        ).fetchone()[0]
        == ids["profile"]
    )
    db.execute(
        "INSERT INTO parser_profile_selection_scopes VALUES(?,'repository',?,NULL,'cr','body')",
        (uid(), ids["repo"]),
    )
    assert (
        db.execute(
            "SELECT parser_profile_uuidv4 FROM effective_change_request_parser_profiles WHERE change_request_id='cr' AND fact_kind='body'"
        ).fetchone()[0]
        is None
    )


def test_new_verification_does_not_silently_replace_invalidated_selected_record(model):
    db, ids, _, evidence = model
    decision(db, ids)
    newer = uid()
    db.execute(
        "INSERT INTO parser_profile_verifications VALUES(?,?,'passed','{}',?,100)",
        (newer, ids["profile"], encoded(evidence)),
    )
    db.execute(
        "INSERT INTO local_parser_profile_verification_trust VALUES(?,1,100,'{}')",
        (newer,),
    )
    db.execute(
        "INSERT INTO parser_profile_verification_invalidations VALUES(?,?,?,0)",
        (uid(), ids["verify"], "counterexample"),
    )
    assert active(db, ids["scope"]) == []
    assert (
        db.execute(
            "SELECT parser_profile_verification_uuidv4 FROM parser_profile_selection_decisions"
        ).fetchone()[0]
        == ids["verify"]
    )


@pytest.mark.parametrize(
    "attack",
    ["missing-capability", "failed-capability", "empty-checks", "wrong-definition"],
)
def test_passed_verification_requires_exact_full_profile_evidence(model, attack):
    db, ids, _, evidence = model
    if attack == "missing-capability":
        evidence["capabilities"].pop()
    elif attack == "failed-capability":
        evidence["capabilities"][0]["outcome"] = "failed"
    elif attack == "empty-checks":
        evidence["capabilities"][0]["checks"] = []
    else:
        evidence["definition"]["implementation"]["sha256"] = "b" * 64
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO parser_profile_verifications VALUES(?,?,'passed','{}',?,0)",
            (uid(), ids["profile"], encoded(evidence)),
        )


def test_sqlite_nul_termination_cannot_hide_noncanonical_profile_uuid(model):
    db, _, definition, _ = model
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO parser_profiles VALUES(?,'fixture','fixture',?)",
            (uid() + "\x00hidden", encoded(definition)),
        )


@pytest.mark.parametrize(
    "owner_kind,repo,source",
    [
        ("repository", None, None),
        ("source", None, None),
        ("repository", "repo", "source"),
        ("source", "repo", "source"),
    ],
)
def test_result_owner_xor_cannot_bypass_composite_foreign_keys(
    model, owner_kind, repo, source
):
    db, ids, _, _ = model
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO parsed_results VALUES(?,?,?,?,?,0,?,'{}')",
            (
                uid(),
                ids["profile"],
                owner_kind,
                ids[repo] if repo else None,
                ids[source] if source else None,
                encoded([{"fetch_occurrence_uuidv4": ids["fetch"]}]),
            ),
        )


@pytest.mark.parametrize(
    "owner_kind,repo,source,fetch",
    [
        ("repository", None, None, "fetch"),
        ("source", None, "source", "fetch"),
        ("repository", "repo", None, "fetch2"),
    ],
)
def test_parsed_input_rejects_null_bypass_and_foreign_repository(
    model, owner_kind, repo, source, fetch
):
    db, ids, _, _ = model
    if fetch == "fetch2":
        with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
            result(db, ids, inputs=[{"fetch_occurrence_uuidv4": ids[fetch]}])
    parsed = result(db, ids)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO parsed_result_inputs VALUES(?,0,?,?,?,?,NULL,NULL)",
            (
                parsed,
                owner_kind,
                ids[repo] if repo else None,
                ids[source] if source else None,
                ids[fetch],
            ),
        )


def test_publication_seals_fact_membership_not_only_input_membership(model):
    db, ids, _, _ = model
    parsed = result(db, ids)
    db.execute(
        "INSERT INTO parsed_result_inputs VALUES(?,0,'repository',?,NULL,?,NULL,NULL)",
        (parsed, ids["repo"], ids["fetch"]),
    )
    db.execute(
        "INSERT INTO parsed_result_publications(parsed_result_uuidv4,declared_input_count,fact_manifest_json,published_at_us) VALUES(?,1,'[]',0)",
        (parsed,),
    )
    body = b"late parser fact"
    db.execute(
        "INSERT INTO text_bodies(body,byte_length,sha256) VALUES(?,?,?)",
        (body.decode(), len(body), hashlib.sha256(body).digest()),
    )
    with pytest.raises(sqlite3.IntegrityError, match="sealed"):
        db.execute(
            "INSERT INTO document_observations(document_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at_us,parsed_at_us,metadata) VALUES(?,?,?,'cr','body','1',?,-1,0,'{}')",
            (uid(), parsed, ids["repo"], hashlib.sha256(body).digest()),
        )


def test_repair_failure_restores_corrupt_bytes_quarantine_and_protection_trigger(model):
    db, _, _, _ = model
    from tests.support.git_payloads import register_git_blob

    digest = register_git_blob(db, b"good").sha256
    immutable = db.execute(
        "SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'"
    ).fetchone()[0]
    db.execute("DROP TRIGGER stored_bytes_immutable")
    db.execute("UPDATE stored_bytes SET body=? WHERE sha256=?", (b"bad!", digest))
    db.execute(immutable)
    first = verify_all(db)
    assert len(first["corrupt"]) == 1
    db.execute(
        "CREATE TRIGGER reject_quarantine_release BEFORE DELETE ON payload_quarantine BEGIN SELECT RAISE(ABORT,'repair interruption'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="repair interruption"):
        repair_payload(db, digest, b"good")
    assert (
        db.execute(
            "SELECT body FROM stored_bytes WHERE sha256=?", (digest,)
        ).fetchone()[0]
        == b"bad!"
    )
    assert db.execute("SELECT count(*) FROM payload_quarantine").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE stored_bytes SET body=? WHERE sha256=?", (b"good", digest))
    assert len(verify_all(db)["corrupt"]) == 1
    assert (
        db.execute(
            "SELECT count(*) FROM unresolved_payloads WHERE stored_sha256=?", (digest,)
        ).fetchone()[0]
        == 1
    )
    db.execute("DROP TRIGGER reject_quarantine_release")
    repair_payload(db, digest, b"good")
    assert verify_all(db)["corrupt"] == []
    assert db.execute("SELECT count(*) FROM payload_quarantine").fetchone()[0] == 0
    assert (
        db.execute(
            "SELECT count(*) FROM unresolved_payloads WHERE stored_sha256=?", (digest,)
        ).fetchone()[0]
        == 1
    )


def test_invalid_declared_hash_cannot_be_retained_even_in_staging(model):
    db, _, _, _ = model
    with pytest.raises(CatalogError) as error:
        stage_verified_payload(
            db,
            b"invalid",
            PayloadRef("git-object-raw-v1", hashlib.sha256(b"valid").digest()),
            {"object_format": "sha1"},
            reason="PAYLOAD_HASH_COLLISION",
        )
    assert error.value.code == "PAYLOAD_DIGEST_MISMATCH"
    assert (
        db.execute("SELECT count(*) FROM payload_admission_staging").fetchone()[0] == 0
    )


def test_received_source_configuration_variants_are_provenance_not_identity_conflicts(
    model,
):
    from repo_catalog.adapters.sqlite.exchange import Graph

    db, ids, _, _ = model
    db.execute(
        "INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES('source',?)",
        (ids["repo"],),
    )
    receiving = sqlite3.connect(":memory:", isolation_level=None)
    receiving.executescript(schema_sql())
    try:
        first = Graph(receiving).receive(Graph(db).export(ids["repo"]))
        assert first["staged_records"] == 0
        receiving.execute(
            "UPDATE sources SET name='local-label',settings='{\"owner\":\"local-owner\"}'"
        )
        db.execute(
            "UPDATE sources SET name='origin-renamed',settings='{\"owner\":\"origin-new-owner\"}' WHERE source_id='source'"
        )
        second = Graph(receiving).receive(Graph(db).export(ids["repo"]))
        assert second["staged_records"] == 0
        assert receiving.execute("SELECT name,settings FROM sources").fetchall() == [
            ("local-label", '{"owner":"local-owner"}')
        ]
        provenance = receiving.execute(
            "SELECT definition_json FROM exchange_source_provenance"
        ).fetchall()
        assert len(provenance) == 2
        assert any("origin-new-owner" in row[0] for row in provenance)
        assert receiving.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        receiving.close()


def test_source_result_cannot_take_another_source_input(model):
    db, ids, _, _ = model
    source_input = uid()
    db.execute(
        "INSERT INTO source_input_observations VALUES(?,?,NULL,NULL,'{}',-1)",
        (source_input, ids["source2"]),
    )
    parsed = uid()
    with pytest.raises(sqlite3.IntegrityError, match="JSON reference"):
        db.execute(
            "INSERT INTO parsed_results VALUES(?,?,'source',NULL,?,0,?,'{}')",
            (
                parsed,
                ids["profile"],
                ids["source"],
                encoded([{"source_input_uuidv4": source_input}]),
            ),
        )
    own_input = uid()
    db.execute(
        "INSERT INTO source_input_observations VALUES(?,?,NULL,NULL,'{}',-1)",
        (own_input, ids["source"]),
    )
    db.execute(
        "INSERT INTO parsed_results VALUES(?,?,'source',NULL,?,0,?,'{}')",
        (
            parsed,
            ids["profile"],
            ids["source"],
            encoded([{"source_input_uuidv4": own_input}]),
        ),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO parsed_result_inputs VALUES(?,0,'source',NULL,?,NULL,NULL,?)",
            (parsed, ids["source"], source_input),
        )


def test_profile_dag_rejects_cycle_even_before_publication(model):
    db, ids, _, _ = model
    first, second = uid(), uid()
    for ident, predecessor in ((first, second), (second, first)):
        db.execute(
            "INSERT INTO parser_profile_selection_decisions(selection_decision_uuidv4,selection_scope_uuidv4,owner_kind,fact_kind,parser_profile_uuidv4,parser_profile_verification_uuidv4,predecessor_manifest_json,issuer) VALUES(?,?,'repository','body',?,?,?,'independent-test')",
            (
                ident,
                ids["scope"],
                ids["profile"],
                ids["verify"],
                encoded([predecessor]),
            ),
        )
    db.execute(
        "INSERT INTO parser_profile_selection_predecessors VALUES(?,?,?)",
        (first, second, ids["scope"]),
    )
    with pytest.raises(sqlite3.IntegrityError, match="cycle"):
        db.execute(
            "INSERT INTO parser_profile_selection_predecessors VALUES(?,?,?)",
            (second, first, ids["scope"]),
        )
    assert active(db, ids["scope"]) == []


def test_published_profile_cannot_be_replaced_with_same_uuid(model):
    db, ids, definition, _ = model
    definition["settings"] = {"changed": True}
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT OR REPLACE INTO parser_profiles VALUES(?,'fixture','fixture',?)",
            (ids["profile"], encoded(definition)),
        )
    assert (
        json.loads(
            db.execute("SELECT definition_json FROM parser_profiles").fetchone()[0]
        )["settings"]
        == {}
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_late_generated_fact_keeps_result_unpublished_until_manifest_complete(
    model, reverse
):
    from repo_catalog.adapters.sqlite.exchange import Graph
    from repo_catalog.adapters.sqlite.parser_model import ParserModel

    db, ids, _, _ = model
    parsed = result(db, ids)
    db.execute(
        "INSERT INTO parsed_result_inputs VALUES(?,0,'repository',?,NULL,?,NULL,NULL)",
        (parsed, ids["repo"], ids["fetch"]),
    )
    body = b"result member arriving late"
    digest = hashlib.sha256(body).digest()
    db.execute(
        "INSERT INTO text_bodies(body,byte_length,sha256) VALUES(?,?,?)",
        (body.decode(), len(body), digest),
    )
    observation = uid()
    db.execute(
        "INSERT INTO document_observations(document_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at_us,parsed_at_us,metadata) VALUES(?,?,?,'cr','body','1',?,-1,0,'{}')",
        (observation, parsed, ids["repo"], digest),
    )
    ParserModel(db).publish_result(parsed)
    unit = Graph(db).export(ids["repo"])
    if reverse:
        unit["records"].reverse()
    partial = {
        **unit,
        "records": [
            record
            for record in unit["records"]
            if record["table"] != "document_observations"
        ],
    }
    receiving = sqlite3.connect(":memory:", isolation_level=None)
    receiving.executescript(schema_sql())
    try:
        pending = Graph(receiving).receive(partial)
        assert pending["staged_records"] > 0
        assert (
            receiving.execute(
                "SELECT count(*) FROM parsed_result_publications"
            ).fetchone()[0]
            == 0
        )
        completed = Graph(receiving).receive(unit)
        assert completed["staged_records"] == 0
        assert receiving.execute(
            "SELECT parsed_result_uuidv4 FROM parsed_result_publications"
        ).fetchall() == [(parsed,)]
        assert receiving.execute(
            "SELECT document_observation_uuidv4 FROM document_observations"
        ).fetchall() == [(observation,)]
        assert Graph(receiving).receive(unit)["received_records"] == 0
        assert receiving.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        receiving.close()


def test_late_source_dependency_does_not_relabel_the_original_sender(model):
    from repo_catalog.adapters.sqlite.exchange import Graph

    db, ids, _, _ = model
    db.execute(
        "INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES('source',?)",
        (ids["repo"],),
    )
    unit = Graph(db).export(ids["repo"])
    origin = unit["origin_catalog_uuidv4"]
    first = {
        **unit,
        "records": [r for r in unit["records"] if r["table"] != "service_instances"],
    }
    later = {
        **unit,
        "origin_catalog_uuidv4": uid(),
        "records": [r for r in unit["records"] if r["table"] == "service_instances"],
    }
    receiving = sqlite3.connect(":memory:", isolation_level=None)
    receiving.executescript(schema_sql())
    try:
        assert Graph(receiving).receive(first)["staged_records"] > 0
        assert Graph(receiving).receive(later)["staged_records"] == 0
        assert receiving.execute(
            "SELECT origin_catalog_uuidv4 FROM exchange_source_provenance"
        ).fetchall() == [(origin,)]
    finally:
        receiving.close()


@pytest.mark.parametrize(
    "attack", ["other-repository", "missing-owner", "unlinked-source", "other-source"]
)
def test_generated_repository_names_enforce_generator_ownership(model, attack):
    db, ids, _, _ = model
    if attack in ("other-repository", "missing-owner"):
        parsed = result(db, ids)
        owner_repo = ids["repo"] if attack == "other-repository" else None
        owner_source = None
        target_repo = ids["other"] if attack == "other-repository" else ids["repo"]
    else:
        parsed = uid()
        source_input = uid()
        db.execute(
            "INSERT INTO source_input_observations VALUES(?,?,NULL,NULL,'{}',-1)",
            (source_input, ids["source"]),
        )
        db.execute(
            "INSERT INTO parsed_results VALUES(?,?,'source',NULL,?,0,?,'{}')",
            (
                parsed,
                ids["profile"],
                ids["source"],
                encoded([{"source_input_uuidv4": source_input}]),
            ),
        )
        owner_repo = None
        owner_source = ids["source2"] if attack == "other-source" else ids["source"]
        target_repo = ids["repo"]
        if attack == "other-source":
            db.execute(
                "INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES('source2',?)",
                (target_repo,),
            )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO repository_name_observations(repository_name_observation_uuidv4,repository_uuidv4,name,observed_at_us,parsed_result_uuidv4,provenance_json,owner_repository_uuidv4,owner_source_registration_uuidv4) VALUES(?,?,'name',0,?,'{}',?,?)",
            (uid(), target_repo, parsed, owner_repo, owner_source),
        )


def test_generated_name_is_in_output_manifest_and_cannot_arrive_after_sealing(model):
    from repo_catalog.adapters.sqlite.parser_model import ParserModel

    db, ids, _, _ = model
    parsed = result(db, ids)
    db.execute(
        "INSERT INTO parsed_result_inputs VALUES(?,0,'repository',?,NULL,?,NULL,NULL)",
        (parsed, ids["repo"], ids["fetch"]),
    )
    observation = uid()
    sql = "INSERT INTO repository_name_observations(repository_name_observation_uuidv4,repository_uuidv4,name,observed_at_us,parsed_result_uuidv4,provenance_json,owner_repository_uuidv4,owner_source_registration_uuidv4) VALUES(?,?,'name',0,?,'{}',?,NULL)"
    db.execute(sql, (observation, ids["repo"], parsed, ids["repo"]))
    ParserModel(db).publish_result(parsed)
    manifest = json.loads(
        db.execute(
            "SELECT fact_manifest_json FROM parsed_result_publications WHERE parsed_result_uuidv4=?",
            (parsed,),
        ).fetchone()[0]
    )
    assert {"table": "repository_name_observations", "key": [observation]} in manifest
    with pytest.raises(sqlite3.IntegrityError, match="sealed"):
        db.execute(sql, (uid(), ids["repo"], parsed, ids["repo"]))


@pytest.mark.parametrize("reverse", [False, True])
def test_same_fact_uuid_conflict_blocks_current_independently_of_arrival_order(
    model, reverse
):
    import copy

    from repo_catalog.adapters.sqlite.exchange import Graph
    from repo_catalog.adapters.sqlite.parser_model import ParserModel

    db, ids, _, _ = model
    parsed = result(db, ids)
    db.execute(
        "INSERT INTO parsed_result_inputs VALUES(?,0,'repository',?,NULL,?,NULL,NULL)",
        (parsed, ids["repo"], ids["fetch"]),
    )
    body = b"same evidence"
    digest = hashlib.sha256(body).digest()
    db.execute(
        "INSERT INTO text_bodies(body,byte_length,sha256) VALUES(?,?,?)",
        (body.decode(), len(body), digest),
    )
    db.execute(
        "INSERT INTO document_observations(document_observation_uuidv4,parsed_result_uuidv4,repository_uuidv4,change_request_id,kind,provider_change_request_document_id,text_body_sha256,observed_at_us,parsed_at_us,metadata) VALUES(?,?,?,'cr','body','1',?,-1,0,'{\"variant\":\"first\"}')",
        (uid(), parsed, ids["repo"], digest),
    )
    api = ParserModel(db)
    api.publish_result(parsed)
    api.select_profile(
        ids["profile"], ids["verify"], repository_uuidv4=ids["repo"], fact_kind="body"
    )
    api.select_fact(
        parsed,
        fact_kind="body",
        change_request_id="cr",
        kind="body",
        provider_change_request_document_id="1",
    )
    original = Graph(db).export(ids["repo"])
    conflict = copy.deepcopy(original)
    for row in conflict["records"]:
        if row["table"] == "document_observations":
            row["values"]["metadata"] = '{"variant":"conflicting"}'
    receiving = sqlite3.connect(":memory:", isolation_level=None)
    receiving.executescript(schema_sql())
    try:
        units = (conflict, original) if reverse else (original, conflict)
        assert Graph(receiving).receive(units[0])["staged_records"] == 0
        ParserModel(receiving).trust_verification(ids["verify"])
        assert (
            receiving.execute(
                "SELECT count(*) FROM current_document_observations"
            ).fetchone()[0]
            == 1
        )
        assert Graph(receiving).receive(units[1])["staged_records"] > 0
        assert (
            receiving.execute(
                "SELECT count(*) FROM current_document_observations"
            ).fetchone()[0]
            == 0
        )
        assert (
            receiving.execute("SELECT count(*) FROM document_observations").fetchone()[
                0
            ]
            == 1
        )
        assert (
            receiving.execute("SELECT count(*) FROM fetch_occurrences").fetchone()[0]
            == 1
        )
        assert receiving.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        receiving.close()
