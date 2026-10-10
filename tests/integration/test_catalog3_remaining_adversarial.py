"""Independent counterexamples for the post-PR11 model contracts."""

import copy
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from repo_catalog.adapters.sqlite.cas_integrity import diagnose_corruption
from repo_catalog.adapters.sqlite.coverage import freeze_complete_proof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import reference_dependencies
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.schema import schema_sql
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.pr_queries import _collection_state
from repo_catalog.application.query_service import QueryService
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
from tests.support.cli import run


def test_unrelated_present_record_cannot_prove_complete_coverage(databases):
    """An arbitrary nonempty requires list is not acquisition evidence."""
    sender, receiver = databases
    expected = fixture(sender)
    scope = uid()
    sender.execute(
        "INSERT INTO coverage_scopes VALUES(?,?,?,'comment')",
        (scope, expected["repository"], expected["cr"]),
    )
    sender.execute(
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us) "
        "VALUES(?,'complete',-1)",
        (scope,),
    )
    graph = Graph(sender)
    unit = graph.export(expected["repository"])
    claim = graph.record("coverage_claims", graph.rows("coverage_claims")[0])
    owner_key = next(
        record["key"] for record in unit["records"] if record["table"] == "repositories"
    )
    claim["requires"] = [owner_key]
    unit["records"] = [
        record
        for record in unit["records"]
        if record["table"]
        not in {
            "fetch_occurrences",
            "parsed_results",
            "parsed_result_inputs",
            "parsed_result_publications",
            "document_observations",
            "coverage_claims",
            "fact_selection_decisions",
            "fact_selection_predecessors",
            "fact_selection_publications",
        }
    ] + [claim]
    try:
        receive(receiver, unit)
    except CatalogError as error:
        assert error.code == "INVALID_EXCHANGE"
    assert (
        receiver.execute(
            "SELECT count(*) FROM coverage_claims WHERE coverage_state='complete'"
        ).fetchone()[0]
        == 0
    )


def git_result(db):
    repository, acquisition = uid(), uid()
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'git','{}')",
        (repository,),
    )
    db.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,request) "
        "VALUES(?,?,'sha1','git','{}')",
        (acquisition, repository),
    )
    model = ParserModel(db)
    profile = model.register_profile(
        {
            "implementation": {"test": "independent-git-review"},
            "settings": {},
            "output_schema": {},
            "capabilities": [{"owner_kind": "repository", "fact_kind": "git"}],
        }
    )
    result = model.create_result(
        profile,
        repository_uuidv4=repository,
        inputs=[{"git_acquisition_id": acquisition}],
    )
    return repository, acquisition, result


def git_object(db, context, kind, *, fmt="sha1", oid=None):
    repository, acquisition, _ = context
    oid = oid or hashlib.new(fmt, f"{kind} 0\0".encode()).digest()
    ident = db.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES(?,?,?,0,1)",
        (fmt, oid, kind),
    ).lastrowid
    db.execute(
        "INSERT INTO repository_object_sources(repository_uuidv4,git_object_id,git_acquisition_id) VALUES(?,?,?)",
        (repository, ident, acquisition),
    )
    payload = intern_payload(db, b"", representation="git-object-raw-v1")
    db.execute(
        "INSERT INTO git_object_payloads(git_object_id,payload_representation,payload_sha256) VALUES(?,?,?)",
        (ident, *payload.parameters()),
    )
    return ident


def publish_git_input(db, context):
    repository, acquisition, _ = context
    objects = [
        {
            "object_format": row[0],
            "oid": row[1].hex(),
            "payload": {"representation": row[2], "sha256": row[3].hex()},
        }
        for row in db.execute(
            "SELECT g.object_format,g.oid,p.payload_representation,p.payload_sha256 "
            "FROM repository_object_sources s JOIN git_objects g USING(git_object_id) "
            "JOIN git_object_payloads p USING(git_object_id) "
            "WHERE s.repository_uuidv4=? AND s.git_acquisition_id=? ORDER BY g.object_format,g.oid",
            (repository, acquisition),
        )
    ]
    db.execute(
        "INSERT INTO git_acquisition_publications VALUES(?,?,?,?)",
        (acquisition, repository, json.dumps(objects), "[]"),
    )


def test_git_commit_cannot_bind_tree_from_another_object_format(databases):
    """A result-owned FK does not excuse an impossible Git parent identity."""
    db, _ = databases
    context = git_result(db)
    commit = git_object(db, context, "commit")
    repository, acquisition, result = context
    with pytest.raises(sqlite3.IntegrityError):
        tree = git_object(db, context, "tree", fmt="sha256")
        db.execute(
            "INSERT INTO commits(git_fact_uuidv4,parsed_result_uuidv4,repository_uuidv4,git_acquisition_id,"
            "git_object_id,tree_git_object_id,raw_headers,raw_message,message_text,metadata) "
            "VALUES(?,?,?,?,?,?,X'',X'','', '{}')",
            (uid(), result, repository, acquisition, commit, tree),
        )


@pytest.mark.parametrize(
    "column", ["parsed_result_uuidv4", "repository_uuidv4", "git_acquisition_id"]
)
def test_git_owned_fact_rejects_null_component(databases, column):
    db, _ = databases
    context = git_result(db)
    commit = git_object(db, context, "commit")
    tree = git_object(db, context, "tree")
    repository, acquisition, result = context
    values = {
        "git_fact_uuidv4": uid(),
        "parsed_result_uuidv4": result,
        "repository_uuidv4": repository,
        "git_acquisition_id": acquisition,
        "git_object_id": commit,
        "tree_git_object_id": tree,
        "raw_headers": b"",
        "raw_message": b"",
        "message_text": "",
        "metadata": "{}",
    }
    values[column] = None
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO commits("
            + ",".join(values)
            + ") VALUES("
            + ",".join("?" for _ in values)
            + ")",
            tuple(values.values()),
        )


def test_git_owned_fact_rejects_foreign_result(databases):
    db, _ = databases
    context = git_result(db)
    foreign = git_result(db)
    commit = git_object(db, context, "commit")
    tree = git_object(db, context, "tree")
    repository, acquisition, _ = context
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO commits(git_fact_uuidv4,parsed_result_uuidv4,repository_uuidv4,git_acquisition_id,"
            "git_object_id,tree_git_object_id,raw_headers,raw_message,message_text,metadata) "
            "VALUES(?,?,?,?,?,?,X'',X'','', '{}')",
            (uid(), foreign[2], repository, acquisition, commit, tree),
        )


def test_collection_subset_manifest_does_not_prove_complete_collection(databases):
    sender, _ = databases
    expected = fixture(sender)
    first = sender.execute(
        "SELECT fetch_collection_id,payload_representation,payload_sha256 FROM fetch_occurrences "
        "WHERE fetch_occurrence_uuidv4=?",
        (expected["fetch"],),
    ).fetchone()
    sender.execute(
        "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,fetch_collection_id,ordinal,"
        "payload_representation,payload_sha256,request,observed_at_us,parsed_at_us) "
        "VALUES(?,?,?,1,?,?,'{}',0,0)",
        (uid(), expected["repository"], *first),
    )
    scope = sender.execute(
        "SELECT resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?",
        (first[0],),
    ).fetchone()[0]
    try:
        sender.execute(
            "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,asserted_state,evidence,observed_at_us) "
            "VALUES(?,?,'complete',?,-1)",
            (
                scope,
                first[0],
                json.dumps({"fetch_occurrence_uuidv4s": [expected["fetch"]]}),
            ),
        )
    except sqlite3.IntegrityError:
        return
    graph = Graph(sender)
    marker = graph.rows("completion_markers")[0]
    assert graph.proof_requirements("completion_markers", marker) is None


@pytest.mark.parametrize("as_list", [False, True])
def test_source_owned_nested_json_rejects_outside_repository_membership(
    databases, as_list
):
    db, _ = databases
    own = fixture(db)
    foreign = fixture(db, source_local="foreign-source")
    model = ParserModel(db)
    profile = model.register_profile(
        {
            "implementation": {"test": "independent-source-review"},
            "settings": {},
            "output_schema": {},
            "capabilities": [{"owner_kind": "source", "fact_kind": "inventory"}],
        }
    )
    payload = intern_payload(db, b"{}", representation="decoded_api")
    input_uuid = uid()
    db.execute(
        "INSERT INTO source_input_observations(source_input_uuidv4,source_registration_uuidv4,"
        "payload_representation,payload_sha256,request_context_json,observed_at_us) VALUES(?,?,?,?,'{}',0)",
        (input_uuid, own["source"], *payload.parameters()),
    )
    forged = (
        {"fetch_occurrence_uuidv4s": [foreign["fetch"]]}
        if as_list
        else {"fetch_occurrence_uuidv4": foreign["fetch"]}
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO parsed_results(parsed_result_uuidv4,parser_profile_uuidv4,owner_kind,"
            "source_registration_uuidv4,input_manifest_json,derivation_json) VALUES(?,?,'source',?,?,?)",
            (
                uid(),
                profile,
                own["source"],
                json.dumps([{"source_input_uuidv4": input_uuid}]),
                json.dumps({"nested": forged}),
            ),
        )


def test_verification_criteria_cannot_hide_malformed_nested_reference(databases):
    db, _ = databases
    expected = fixture(db)
    evidence = db.execute(
        "SELECT evidence_json FROM parser_profile_verifications "
        "WHERE parser_profile_verification_uuidv4=?",
        (expected["verification"],),
    ).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO parser_profile_verifications(parser_profile_verification_uuidv4,"
            "parser_profile_uuidv4,outcome,criteria_json,evidence_json,verified_at_us) "
            "VALUES(?,?,'passed',?,?,0)",
            (
                uid(),
                expected["profile"],
                json.dumps(
                    {"nested": {"fetch_occurrence_uuidv4": "wrong-type-domain"}}
                ),
                evidence,
            ),
        )


def test_published_git_input_cannot_acquire_late_object(databases):
    db, _ = databases
    context = git_result(db)
    repository, acquisition, result = context
    commit = git_object(db, context, "commit")
    tree = git_object(db, context, "tree")
    db.execute(
        "INSERT INTO commits(git_fact_uuidv4,parsed_result_uuidv4,repository_uuidv4,git_acquisition_id,"
        "git_object_id,tree_git_object_id,raw_headers,raw_message,message_text,metadata) "
        "VALUES(?,?,?,?,?,?,X'',X'','', '{}')",
        (uid(), result, repository, acquisition, commit, tree),
    )
    publish_git_input(db, context)
    ParserModel(db).publish_result(result)
    with pytest.raises(sqlite3.IntegrityError):
        git_object(db, context, "blob")


def test_missing_raw_git_bytes_keeps_result_unpublished_until_arrival(
    databases, tmp_path
):
    sender, _ = databases
    destination = tmp_path / "receiver.sqlite3"
    receiver = sqlite3.connect(destination, isolation_level=None)
    receiver.executescript(schema_sql())
    context = git_result(sender)
    repository, acquisition, result = context
    commit = git_object(sender, context, "commit")
    tree = git_object(sender, context, "tree")
    sender.execute(
        "INSERT INTO commits(git_fact_uuidv4,parsed_result_uuidv4,repository_uuidv4,git_acquisition_id,"
        "git_object_id,tree_git_object_id,raw_headers,raw_message,message_text,metadata) "
        "VALUES(?,?,?,?,?,?,X'',X'','', '{}')",
        (uid(), result, repository, acquisition, commit, tree),
    )
    publish_git_input(sender, context)
    ParserModel(sender).publish_result(result)
    unit = Graph(sender).export(repository)
    early = dict(
        unit,
        records=[
            record
            for record in unit["records"]
            if record["table"]
            not in {"git_object_payloads", "payloads", "stored_bytes"}
        ],
    )
    receive(receiver, early)
    assert (
        receiver.execute("SELECT count(*) FROM parsed_result_publications").fetchone()[
            0
        ]
        == 0
    )
    receiver.close()
    receiver = sqlite3.connect(destination, isolation_level=None)
    receiver.execute("PRAGMA foreign_keys=ON")
    receiver.execute("PRAGMA recursive_triggers=ON")
    assert receive(receiver, unit)["staged_records"] == 0, receiver.execute(
        "SELECT table_name,reason FROM exchange_staging"
    ).fetchall()
    assert receiver.execute(
        "SELECT parsed_result_uuidv4 FROM parsed_result_publications"
    ).fetchone() == (result,)
    assert receiver.execute("PRAGMA foreign_key_check").fetchall() == []
    assert receiver.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    receiver.close()


def test_disputed_git_input_manifest_blocks_dependent_published_result(databases):
    sender, receiver = databases
    context = git_result(sender)
    repository, acquisition, result = context
    commit = git_object(sender, context, "commit")
    tree = git_object(sender, context, "tree")
    sender.execute(
        "INSERT INTO commits(git_fact_uuidv4,parsed_result_uuidv4,repository_uuidv4,git_acquisition_id,"
        "git_object_id,tree_git_object_id,raw_headers,raw_message,message_text,metadata) "
        "VALUES(?,?,?,?,?,?,X'',X'','', '{}')",
        (uid(), result, repository, acquisition, commit, tree),
    )
    publish_git_input(sender, context)
    ParserModel(sender).publish_result(result)
    unit = Graph(sender).export(repository)
    assert receive(receiver, unit)["staged_records"] == 0, receiver.execute(
        "SELECT table_name,reason FROM exchange_staging"
    ).fetchall()
    assert receiver.execute(
        "SELECT parsed_result_uuidv4 FROM usable_parsed_results"
    ).fetchone() == (result,)
    disputed = copy.deepcopy(unit)
    for record in disputed["records"]:
        if record["table"] == "git_acquisition_publications":
            record["values"]["object_manifest_json"] = "[]"
    assert receive(receiver, disputed)["staged_records"] > 0
    assert (
        receiver.execute("SELECT count(*) FROM usable_parsed_results").fetchone()[0]
        == 0
    )


@pytest.mark.parametrize("representation", [[], {}])
def test_nested_payload_wrong_representation_type_is_a_contract_error(representation):
    with pytest.raises(CatalogError) as error:
        reference_dependencies(
            "parsed_results",
            {
                "derivation_json": json.dumps(
                    {
                        "nested": {
                            "payload": {
                                "representation": representation,
                                "sha256": "a" * 64,
                            }
                        }
                    }
                )
            },
        )
    assert error.value.code == "INVALID_JSON_REFERENCE"


def test_git_quarantine_suppresses_only_dependent_repository_readers(catalog):
    state, _, repositories = catalog
    run(state, "sync", "git")
    query = QueryService(state)
    alpha_options = {
        "repo": repositories["alpha"],
        "ref": "refs/heads/main",
        "path": "README.md",
    }
    beta_options = {
        "repo": repositories["beta"],
        "ref": "refs/heads/main",
        "path": "copy.txt",
    }
    assert query.query("file show", alpha_options).data["items"]
    assert query.query("file show", beta_options).data["items"][0]["text"] == "abc"
    with Store(state) as store, store.transaction():
        digest = store.one(
            "SELECT p.payload_sha256 FROM git_object_payloads p JOIN stored_bytes b ON b.sha256=p.payload_sha256 "
            "JOIN repository_object_sources o USING(git_object_id) WHERE o.repository_uuidv4=? AND b.body=X'6D61696E' LIMIT 1",
            (repositories["alpha"],),
        )[0]
        before = store.one("SELECT count(*) FROM commits")[0]
        corrupt(store.connection, digest, b"FAIL")
        diagnose_corruption(store.connection, digest)
        assert store.one("SELECT count(*) FROM commits")[0] == before
    affected = query.query("file show", alpha_options)
    assert affected.data["items"] == []
    assert affected.status == "partial"
    assert query.query("file show", beta_options).data["items"][0]["text"] == "abc"
    assert query.query(
        "search code", {"repo": repositories["beta"], "literal": "abc"}
    ).data["items"]


def test_git_selected_verification_invalidation_never_chooses_newer_evidence(catalog):
    state, _, repositories = catalog
    run(state, "sync", "git")
    options = {
        "repo": repositories["alpha"],
        "ref": "refs/heads/main",
        "path": "README.md",
    }
    query = QueryService(state)
    original = query.query("file show", options).data["items"][0]
    with Store(state) as store, store.transaction():
        model = ParserModel(store.connection)
        profile, selected_verification = store.one(
            "SELECT d.parser_profile_uuidv4,d.parser_profile_verification_uuidv4 "
            "FROM parser_profile_selection_decisions d JOIN parser_profile_selection_scopes s USING(selection_scope_uuidv4) "
            "WHERE s.repository_uuidv4=? AND s.fact_kind='git'",
            (repositories["alpha"],),
        )
        definition = json.loads(
            store.one(
                "SELECT definition_json FROM parser_profiles WHERE parser_profile_uuidv4=?",
                (profile,),
            )[0]
        )
        newer = model.verify_profile(
            profile,
            criteria={"test": "independent invalidation boundary"},
            evidence={
                "definition": definition,
                "capabilities": [
                    {**cap, "outcome": "passed", "checks": ["independent fixture"]}
                    for cap in definition["capabilities"]
                ],
            },
        )
        model.trust_verification(newer)
        model.invalidate_verification(
            selected_verification, "independent verification withdrawal"
        )
    unavailable = query.query("file show", options)
    assert unavailable.data["items"] == []
    assert unavailable.status == "partial"
    with Store(state) as store, store.transaction():
        ParserModel(store.connection).select_profile(
            profile,
            newer,
            repository_uuidv4=repositories["alpha"],
            fact_kind="git",
        )
    assert query.query("file show", options).data["items"][0] == original


@pytest.mark.parametrize("reverse", [False, True])
def test_git_fact_uuid_collision_suppresses_selection_in_both_orders(
    databases, reverse
):
    sender, receiver = databases
    context = git_result(sender)
    repository, acquisition, result = context
    commit = git_object(sender, context, "commit")
    tree = git_object(sender, context, "tree")
    sender.execute(
        "INSERT INTO commits(git_fact_uuidv4,parsed_result_uuidv4,repository_uuidv4,git_acquisition_id,"
        "git_object_id,tree_git_object_id,raw_headers,raw_message,message_text,metadata) "
        "VALUES(?,?,?,?,?,?,X'',X'','', '{}')",
        (uid(), result, repository, acquisition, commit, tree),
    )
    publish_git_input(sender, context)
    model = ParserModel(sender)
    model.publish_result(result)
    profile, definition_json = sender.execute(
        "SELECT p.parser_profile_uuidv4,p.definition_json FROM parsed_results r JOIN parser_profiles p USING(parser_profile_uuidv4) "
        "WHERE r.parsed_result_uuidv4=?",
        (result,),
    ).fetchone()
    definition = json.loads(definition_json)
    verification = model.verify_profile(
        profile,
        criteria={"test": "independent Git collision"},
        evidence={
            "definition": definition,
            "capabilities": [
                {**cap, "outcome": "passed", "checks": ["independent fixture"]}
                for cap in definition["capabilities"]
            ],
        },
    )
    model.trust_verification(verification)
    model.select_profile(
        profile, verification, repository_uuidv4=repository, fact_kind="git"
    )
    model.select_fact(result, fact_kind="git", git_acquisition_id=acquisition)
    original = Graph(sender).export(repository)
    alternate = copy.deepcopy(original)
    for record in alternate["records"]:
        if record["table"] == "commits":
            record["values"]["metadata"] = '{"interpretation":"alternative"}'
    first, second = (alternate, original) if reverse else (original, alternate)
    assert receive(receiver, first)["staged_records"] == 0, receiver.execute(
        "SELECT table_name,reason FROM exchange_staging"
    ).fetchall()
    ParserModel(receiver).trust_verification(verification)
    assert receiver.execute(
        "SELECT parsed_result_uuidv4 FROM selected_git_acquisition_results"
    ).fetchone() == (result,)
    assert receive(receiver, second)["staged_records"] > 0
    assert (
        receiver.execute(
            "SELECT count(*) FROM selected_git_acquisition_results"
        ).fetchone()[0]
        == 0
    )
    assert (
        receiver.execute("SELECT count(*) FROM usable_parsed_results").fetchone()[0]
        == 0
    )


@pytest.mark.parametrize("kind", ["pr-code", "pr", "pr-documents"])
def test_terminal_pr_detail_cannot_prove_broader_coverage_without_scope_evidence(
    databases, kind
):
    sender, receiver = databases
    expected = fixture(sender)
    source, resume = sender.execute(
        "SELECT c.source_id,c.resume_scope_id FROM fetch_collections c "
        "JOIN fetch_occurrences f USING(fetch_collection_id) "
        "WHERE f.fetch_occurrence_uuidv4=?",
        (expected["fetch"],),
    ).fetchone()
    collection, fetch = uid(), uid()
    sender.execute(
        "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,"
        "change_request_id,source_id,kind,resume_scope_id) "
        "VALUES(?,?,?,?,'pr-detail',?)",
        (collection, expected["repository"], expected["cr"], source, resume),
    )
    payload = sender.execute(
        "SELECT payload_representation,payload_sha256 FROM fetch_occurrences "
        "WHERE fetch_occurrence_uuidv4=?",
        (expected["fetch"],),
    ).fetchone()
    sender.execute(
        "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,"
        "fetch_collection_id,ordinal,payload_representation,payload_sha256,"
        "request,observed_at_us,parsed_at_us) VALUES(?,?,?,0,?,?,'{}',3,0)",
        (fetch, expected["repository"], collection, *payload),
    )
    complete_collection(sender, fetch)
    scope = uid()
    sender.execute(
        "INSERT INTO coverage_scopes VALUES(?,?,?,?)",
        (
            scope,
            expected["repository"],
            expected["cr"] if kind == "pr-code" else None,
            kind,
        ),
    )
    sender.execute(
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,"
        "observed_at_us,details_json) VALUES(?,'complete',3,?)",
        (
            scope,
            freeze_complete_proof(
                sender, 3, json.dumps({"fetch_collection_ids": [collection]})
            ),
        ),
    )
    graph = Graph(sender)
    unit = graph.export(expected["repository"])
    assert not any(record["table"] == "coverage_claims" for record in unit["records"])
    # A forged sender can still construct the otherwise valid HTTP proof envelope.
    marker = next(
        record for record in unit["records"] if record["table"] == "completion_markers"
    )
    claim = graph.record("coverage_claims", graph.rows("coverage_claims")[0])
    claim["requires"] = sorted({marker["key"], *marker["requires"]})
    unit["records"].append(claim)
    assert receive(receiver, unit)["staged_records"] > 0
    assert receiver.execute("SELECT count(*) FROM coverage_claims").fetchone() == (0,)
    assert receiver.execute("SELECT count(*) FROM code_observations").fetchone() == (0,)


@pytest.mark.parametrize("member", [None, "sha1:0123", {"oid": "not-an-oid"}])
def test_git_root_declarations_require_structured_reference_members(databases, member):
    db, _ = databases
    roots = json.dumps([member])
    with pytest.raises(CatalogError) as error:
        reference_dependencies("git_acquisitions", {"roots_manifest": roots})
    assert error.value.code == "INVALID_JSON_REFERENCE"
    repository = uid()
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'r','{}')",
        (repository,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,"
            "object_format,kind,request,roots_manifest) VALUES(?,?,'sha1','git','{}',?)",
            (uid(), repository, roots),
        )


@pytest.mark.parametrize(
    "proof",
    [
        "exact",
        "subset",
        "empty",
        "unrelated",
        "duplicate",
        "nonterminal",
        "stale",
        "unknown",
    ],
)
def test_complete_code_requires_exact_terminal_listing_sql_evidence(databases, proof):
    db, _ = databases
    expected = fixture(db)
    _, observation, original = pr_observation(db, expected)
    source, resume = db.execute(
        "SELECT source_id,resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?",
        (original[1],),
    ).fetchone()
    model = ParserModel(db)
    profile = model.register_profile(
        {
            "implementation": {"test": "independent-code-completion"},
            "settings": {},
            "output_schema": {},
            "capabilities": [{"owner_kind": "repository", "fact_kind": "code"}],
        }
    )
    listings, collections, inputs = [], [], []
    for kind in ("commits", "files"):
        collection, listing = uid(), uid()
        db.execute(
            "INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,"
            "change_request_id,source_id,kind,resume_scope_id) VALUES(?,?,?,?,?,?)",
            (
                collection,
                expected["repository"],
                expected["cr"],
                source,
                "pr-" + kind,
                resume,
            ),
        )
        db.execute(
            "INSERT INTO code_listings(code_listing_id,change_request_id,"
            "fetch_collection_id,kind,resume_scope_id) VALUES(?,?,?,?,?)",
            (listing, expected["cr"], collection, kind, resume),
        )
        listings.append(listing)
        fetches = []
        for ordinal in range(2):
            fetch = uid()
            fetches.append(fetch)
            inputs.append({"fetch_occurrence_uuidv4": fetch})
            db.execute(
                "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,"
                "fetch_collection_id,ordinal,payload_representation,payload_sha256,"
                "request,observed_at_us,parsed_at_us) VALUES(?,?,?,?,?,?,'{}',3,0)",
                (
                    fetch,
                    expected["repository"],
                    collection,
                    ordinal,
                    original[2],
                    original[3],
                ),
            )
        collections.append((collection, fetches))
    result = model.create_result(
        profile, repository_uuidv4=expected["repository"], inputs=inputs
    )

    def insert_complete():
        for ordinal, (collection, fetches) in enumerate(collections):
            manifest, terminal, observed = fetches, True, 3
            if ordinal == 0:
                if proof == "subset":
                    manifest = fetches[:1]
                elif proof == "empty":
                    manifest = []
                elif proof == "unrelated":
                    manifest = collections[1][1]
                elif proof == "duplicate":
                    manifest = [fetches[0], fetches[0]]
                elif proof == "nonterminal":
                    terminal = False
                elif proof == "stale":
                    observed = 2
                elif proof == "unknown":
                    observed = None
            db.execute(
                "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,"
                "asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,?)",
                (
                    resume,
                    collection,
                    json.dumps(
                        {"terminal": terminal, "fetch_occurrence_uuidv4s": manifest}
                    ),
                    observed,
                ),
            )
        db.execute(
            "INSERT INTO code_observations(code_observation_uuidv4,parsed_result_uuidv4,"
            "repository_uuidv4,change_request_id,change_request_observation_id,"
            "commit_code_listing_id,file_code_listing_id,state,details) "
            "VALUES(?,?,?,?,?,?,?,'complete','{}')",
            (
                uid(),
                result,
                expected["repository"],
                expected["cr"],
                observation,
                *listings,
            ),
        )

    assert db.execute("SELECT count(*) FROM code_listing_progress").fetchone() == (0,)
    if proof == "exact":
        insert_complete()
        assert db.execute("SELECT state FROM code_observations").fetchone() == (
            "complete",
        )
    else:
        with pytest.raises(sqlite3.IntegrityError):
            insert_complete()
        assert db.execute("SELECT count(*) FROM code_observations").fetchone() == (0,)


def test_completion_marker_uuid_cannot_hide_noncanonical_suffix_after_nul(databases):
    db, _ = databases
    expected = fixture(db)
    collection, resume = db.execute(
        "SELECT c.fetch_collection_id,c.resume_scope_id FROM fetch_collections c "
        "JOIN fetch_occurrences f USING(fetch_collection_id) WHERE f.fetch_occurrence_uuidv4=?",
        (expected["fetch"],),
    ).fetchone()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO completion_markers(completion_marker_uuidv4,resume_scope_id,"
            "fetch_collection_id,asserted_state,evidence,observed_at_us) "
            "VALUES(?,?,?,'partial','{}',0)",
            (uid() + "\0hidden", resume, collection),
        )


@pytest.mark.parametrize(
    "details",
    [
        {"expected_roles": []},
        {"expected_roles": {"head": "not-a-git-oid"}},
        {"api_head_base_stable": "yes"},
        {"code_inputs_complete": {}},
        {"missing_roles": {"head": "missing"}},
    ],
)
def test_code_detail_consumers_reject_malformed_authored_types(databases, details):
    db, _ = databases
    encoded = json.dumps(details)
    with pytest.raises(CatalogError) as error:
        reference_dependencies(
            "code_observations", {"object_format": "sha1", "details": encoded}
        )
    assert error.value.code == "INVALID_JSON_REFERENCE"
    expected = fixture(db)
    _, observation, _ = pr_observation(db, expected)
    model = ParserModel(db)
    profile = model.register_profile(
        {
            "implementation": {"test": "independent-code-detail"},
            "settings": {},
            "output_schema": {},
            "capabilities": [{"owner_kind": "repository", "fact_kind": "code"}],
        }
    )
    result = model.create_result(
        profile,
        repository_uuidv4=expected["repository"],
        inputs=[{"fetch_occurrence_uuidv4": expected["fetch"]}],
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO code_observations(code_observation_uuidv4,parsed_result_uuidv4,"
            "repository_uuidv4,change_request_id,change_request_observation_id,state,object_format,details) "
            "VALUES(?,?,?,?,?,'partial','sha1',?)",
            (
                uid(),
                result,
                expected["repository"],
                expected["cr"],
                observation,
                encoded,
            ),
        )


@pytest.mark.parametrize(
    "request_data",
    [{"variables": []}, {"variables": None}],
)
def test_fetch_request_consumers_reject_malformed_authored_types(
    databases, request_data
):
    db, _ = databases
    encoded = json.dumps(request_data)
    with pytest.raises(CatalogError) as error:
        reference_dependencies("fetch_occurrences", {"request": encoded})
    assert error.value.code == "INVALID_JSON_REFERENCE"
    expected = fixture(db)
    collection, representation, digest = db.execute(
        "SELECT fetch_collection_id,payload_representation,payload_sha256 "
        "FROM fetch_occurrences WHERE fetch_occurrence_uuidv4=?",
        (expected["fetch"],),
    ).fetchone()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO fetch_occurrences(fetch_occurrence_uuidv4,repository_uuidv4,"
            "fetch_collection_id,ordinal,payload_representation,payload_sha256,request,observed_at_us) "
            "VALUES(?,?,?,1,?,?,?,3)",
            (
                uid(),
                expected["repository"],
                collection,
                representation,
                digest,
                encoded,
            ),
        )


@pytest.mark.parametrize("object_format,width", [("sha1", 40), ("sha256", 64)])
@pytest.mark.parametrize("field", ["expected_roles", "merge", "missing_roles"])
def test_code_git_oid_cannot_hide_nonhex_suffix_after_nul(
    databases, object_format, width, field
):
    db, _ = databases
    # The byte count is correct, but SQLite TEXT length/GLOB stop before NUL.
    oid = "a" * (width - 2) + "\0a"
    details = {
        "expected_roles": {"head": oid},
        "merge": {"merge": oid},
        "missing_roles": ["review-target:" + oid],
    }[field]
    encoded = json.dumps({field: details})
    with pytest.raises(CatalogError) as error:
        reference_dependencies(
            "code_observations",
            {"object_format": object_format, "details": encoded},
        )
    assert error.value.code == "INVALID_JSON_REFERENCE"
    expected = fixture(db)
    _, observation, _ = pr_observation(db, expected)
    model = ParserModel(db)
    profile = model.register_profile(
        {
            "implementation": {"test": "independent-code-oid"},
            "settings": {},
            "output_schema": {},
            "capabilities": [{"owner_kind": "repository", "fact_kind": "code"}],
        }
    )
    result = model.create_result(
        profile,
        repository_uuidv4=expected["repository"],
        inputs=[{"fetch_occurrence_uuidv4": expected["fetch"]}],
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO code_observations(code_observation_uuidv4,parsed_result_uuidv4,"
            "repository_uuidv4,change_request_id,change_request_observation_id,state,object_format,details) "
            "VALUES(?,?,?,?,?,'partial',?,?)",
            (
                uid(),
                result,
                expected["repository"],
                expected["cr"],
                observation,
                object_format,
                encoded,
            ),
        )


@pytest.mark.parametrize("digest", ["a" * 62 + "\0a", "a" * 64 + "\0hidden"])
def test_parser_definition_digest_cannot_hide_nonhex_suffix_after_nul(
    databases, digest
):
    db, _ = databases
    definition = json.dumps(
        {
            "implementation": {"test_sha256": digest},
            "settings": {},
            "output_schema": {},
            "capabilities": [{"owner_kind": "repository", "fact_kind": "code"}],
        }
    )
    with pytest.raises(CatalogError) as error:
        reference_dependencies("parser_profiles", {"definition_json": definition})
    assert error.value.code == "INVALID_JSON_REFERENCE"
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO parser_profiles(parser_profile_uuidv4,parser_version,profile_version,definition_json) "
            "VALUES(?,'independent','1',?)",
            (uid(), definition),
        )


@pytest.mark.parametrize(
    ("later_state", "observed"), [("partial", 0), ("unknown", 0), ("partial", -1)]
)
def test_immutable_collection_state_never_falls_back_from_newer_or_tied_incomplete(
    databases, later_state, observed
):
    db, _ = databases
    expected = fixture(db)
    collection = complete_collection(db, expected["fetch"])
    resume = db.execute(
        "SELECT resume_scope_id FROM fetch_collections WHERE fetch_collection_id=?",
        (collection,),
    ).fetchone()[0]
    db.execute(
        "INSERT INTO completion_markers(resume_scope_id,fetch_collection_id,"
        "asserted_state,evidence,observed_at_us) VALUES(?,?,?,'{}',?)",
        (resume, collection, later_state, observed),
    )

    prior_factory = db.row_factory
    db.row_factory = sqlite3.Row
    try:
        query = SimpleNamespace(
            s=SimpleNamespace(
                connection=db,
                one=lambda sql, parameters: db.execute(sql, parameters).fetchone(),
            ),
            check=lambda: None,
        )
        assert (
            _collection_state(query, {"fetch_collection_id": collection, "state": None})
            != "complete"
        )
    finally:
        db.row_factory = prior_factory
