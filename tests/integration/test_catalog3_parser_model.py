"""End-to-end admission and current derivation contracts in a fresh catalog."""

import json
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.sqlite.parser_model import ParserModel, canonical
from repo_catalog.adapters.sqlite.schema import schema_sql
from tests.support.parser_facts import register_test_profile


def uid():
    return str(uuid.uuid4())


@pytest.fixture
def model():
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(schema_sql())
    repo, acquisition = uid(), uid()
    db.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?, 'fixture', '{}')",
        (repo,),
    )
    db.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,kind,request) VALUES(?,?,'git','{}')",
        (acquisition, repo),
    )
    profile = register_test_profile(db)
    parser = ParserModel(db)
    parser.ensure_scope_profile(profile, repository_uuidv4=repo, fact_kind="git")
    yield db, parser, repo, acquisition, profile
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    db.close()


def parsed_snapshot(model):
    db, parser, repo, acquisition, profile = model
    result = parser.create_result(
        profile, repository_uuidv4=repo, inputs=[{"git_acquisition_id": acquisition}]
    )
    snapshot = uid()
    db.execute(
        "INSERT INTO snapshots(parsed_result_uuidv4,snapshot_id,git_acquisition_id,repository_uuidv4,published,generation) VALUES(?,?,?,?,1,0)",
        (result, snapshot, acquisition, repo),
    )
    parser.publish_result(result)
    return result, snapshot


def test_independent_reparse_retains_input_and_produces_separate_output(model):
    db, parser, *_ = model
    first, one = parsed_snapshot(model)
    second, two = parsed_snapshot(model)
    assert first != second and one != two
    assert db.execute("SELECT count(*) FROM git_acquisitions").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM parsed_result_inputs").fetchone()[0] == 2
    parser.select_fact(first, fact_kind="git")
    parser.select_fact(second, fact_kind="git")
    assert db.execute("SELECT snapshot_id FROM current_snapshots").fetchall() == [
        (two,)
    ]
    assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 2


def test_delayed_predecessor_promotes_without_new_decision_or_time_order(model):
    db, parser, repo, *_ = model
    first, _ = parsed_snapshot(model)
    second, snapshot = parsed_snapshot(model)
    initial = parser.select_fact(first, fact_kind="git", decided_at_us=100)
    scope = db.execute(
        "SELECT fact_selection_scope_uuidv4 FROM fact_selection_decisions WHERE fact_selection_decision_uuidv4=?",
        (initial,),
    ).fetchone()[0]
    parent, child = uid(), uid()

    def record(ident, result, predecessors, time):
        return {
            "fact_selection_decision_uuidv4": ident,
            "fact_selection_scope_uuidv4": scope,
            "parsed_result_uuidv4": result,
            "repository_uuidv4": repo,
            "source_registration_uuidv4": None,
            "predecessor_manifest_json": canonical(predecessors),
            "issuer": "peer",
            "decided_at_us": time,
        }

    assert parser.receive_fact_decision(record(child, second, [parent], -1)) == "staged"
    assert db.execute("SELECT count(*) FROM current_snapshots").fetchone()[0] == 0
    assert (
        parser.receive_fact_decision(record(parent, first, [initial], 1000))
        == "admitted"
    )
    assert db.execute("SELECT count(*) FROM fact_selection_staging").fetchone()[0] == 0
    assert (
        db.execute(
            "SELECT fact_selection_decision_uuidv4 FROM active_fact_selections"
        ).fetchone()[0]
        == child
    )
    assert (
        db.execute("SELECT snapshot_id FROM current_snapshots").fetchone()[0]
        == snapshot
    )


def test_output_manifest_cannot_publish_an_incomplete_exchange_subset(model):
    db, parser, repo, acquisition, profile = model
    result = parser.create_result(
        profile, repository_uuidv4=repo, inputs=[{"git_acquisition_id": acquisition}]
    )
    snapshot = uid()
    manifest = canonical([{"table": "snapshots", "key": [snapshot]}])
    with pytest.raises(sqlite3.IntegrityError, match="fact manifest"):
        db.execute(
            "INSERT INTO parsed_result_publications VALUES(?,1,?,0)", (result, manifest)
        )
    db.execute(
        "INSERT INTO snapshots(parsed_result_uuidv4,snapshot_id,git_acquisition_id,repository_uuidv4,published,generation) VALUES(?,?,?,?,1,0)",
        (result, snapshot, acquisition, repo),
    )
    db.execute(
        "INSERT INTO parsed_result_publications VALUES(?,1,?,0)", (result, manifest)
    )
    assert json.loads(
        db.execute(
            "SELECT fact_manifest_json FROM parsed_result_publications WHERE parsed_result_uuidv4=?",
            (result,),
        ).fetchone()[0]
    ) == json.loads(manifest)


def test_invalidated_verification_never_switches_to_newer_pass(model):
    db, parser, repo, _, profile = model
    result, _ = parsed_snapshot(model)
    parser.select_fact(result, fact_kind="git")
    verification = db.execute(
        "SELECT parser_profile_verification_uuidv4 FROM active_parser_profile_selections"
    ).fetchone()[0]
    original = db.execute(
        "SELECT criteria_json,evidence_json FROM parser_profile_verifications WHERE parser_profile_verification_uuidv4=?",
        (verification,),
    ).fetchone()
    other = parser.verify_profile(
        profile, criteria=json.loads(original[0]), evidence=json.loads(original[1])
    )
    parser.trust_verification(other)
    parser.invalidate_verification(verification, "counterexample")
    assert db.execute("SELECT count(*) FROM current_snapshots").fetchone()[0] == 0
    parser.select_profile(profile, other, repository_uuidv4=repo, fact_kind="git")
    assert db.execute("SELECT count(*) FROM current_snapshots").fetchone()[0] == 1


def test_conflicting_same_uuid_preserves_original_and_blocks_current(model):
    db, parser, *_ = model
    first, _ = parsed_snapshot(model)
    second, _ = parsed_snapshot(model)
    decision = parser.select_fact(first, fact_kind="git")
    cursor = db.execute(
        "SELECT * FROM fact_selection_decisions WHERE fact_selection_decision_uuidv4=?",
        (decision,),
    )
    record = dict(zip([c[0] for c in cursor.description], cursor.fetchone()))
    record["parsed_result_uuidv4"] = second
    assert parser.receive_fact_decision(record) == "staged"
    assert (
        db.execute(
            "SELECT parsed_result_uuidv4 FROM fact_selection_decisions WHERE fact_selection_decision_uuidv4=?",
            (decision,),
        ).fetchone()[0]
        == first
    )
    assert db.execute("SELECT count(*) FROM current_snapshots").fetchone()[0] == 0


def test_repository_names_require_published_selected_usable_parser_result(model):
    from repo_catalog.adapters.sqlite.payloads import intern_payload

    db, parser, repo, _, profile = model
    source, source_id, source_input = uid(), uid(), uid()
    db.execute(
        "INSERT INTO sources(source_id,source_registration_uuidv4,discovery_kind,name,settings) VALUES(?,?,'manual_git','fixture',NULL)",
        (source_id, source),
    )
    db.execute("INSERT INTO source_repositories VALUES(?,?,0,0)", (source_id, repo))
    payload = intern_payload(db, b'{"fixture":"names"}')
    db.execute(
        "INSERT INTO source_input_observations VALUES(?,?,?,?,?,0)",
        (source_input, source, *payload.parameters(), "{}"),
    )
    parser.ensure_scope_profile(
        profile, source_registration_uuidv4=source, fact_kind="inventory"
    )

    def name(label, parsed_profile, *, publish=True):
        result = parser.create_result(
            parsed_profile,
            source_registration_uuidv4=source,
            inputs=[{"source_input_uuidv4": source_input}],
        )
        db.execute(
            "INSERT INTO repository_name_observations VALUES(?,?,?,0,?,'{}',NULL,?)",
            (uid(), repo, label, result, source),
        )
        if publish:
            parser.publish_result(result)
        return result

    name("selected", profile)
    name("unfinished", profile, publish=False)
    definition = json.loads(
        db.execute(
            "SELECT definition_json FROM parser_profiles WHERE parser_profile_uuidv4=?",
            (profile,),
        ).fetchone()[0]
    )
    definition["implementation"] = {"fixture": "different-parser"}
    other = parser.register_profile(definition)
    name("unselected", other)
    db.execute(
        "INSERT INTO repository_name_observations VALUES(?,?,?,0,NULL,'{}',NULL,NULL)",
        (uid(), repo, "manual"),
    )
    assert db.execute(
        "SELECT name FROM repository_observed_names ORDER BY name"
    ).fetchall() == [("manual",), ("selected",)]
    diagnosis = db.execute(
        "INSERT INTO unresolved_payloads(stored_sha256,detected_at_us,diagnostic_json,reason) VALUES(?,0,'{}','physical_corruption')",
        (payload.sha256,),
    ).lastrowid
    db.execute(
        "INSERT INTO payload_quarantine VALUES(?,?)", (payload.sha256, diagnosis)
    )
    assert db.execute("SELECT name FROM repository_observed_names").fetchall() == [
        ("manual",)
    ]
