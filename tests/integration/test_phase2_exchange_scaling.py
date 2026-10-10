"""Bound ordinary conflict-free intake without weakening resolution barriers."""

import copy
import json

import pytest

from repo_catalog.adapters.sqlite.coverage import freeze_complete_proof
from repo_catalog.adapters.sqlite.exchange import Graph, canonical
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from tests.integration.test_catalog3_exchange import (
    complete_collection,
    fixture,
    receive,
    uid,
)
from tests.integration.test_catalog3_exchange import databases as databases
from tests.integration.test_phase1_exchange_scaling import (
    _add_unrelated_git_objects,
    _catalog,
    _measure_vm_steps,
    _repository,
)


def _complete_claim(db, expected):
    collection = complete_collection(db, expected["fetch"])
    scope = uid()
    db.execute(
        "INSERT INTO coverage_scopes VALUES(?,?,?,'comment')",
        (scope, expected["repository"], expected["cr"]),
    )
    db.execute(
        "INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) "
        "VALUES(?,'complete',-1,?)",
        (
            scope,
            freeze_complete_proof(
                db, -1, json.dumps({"fetch_collection_ids": [collection]})
            ),
        ),
    )


def test_conflict_free_refresh_work_is_bounded_as_other_git_history_grows():
    db = _catalog()
    try:
        unrelated = [_repository(db, "unrelated-a"), _repository(db, "unrelated-b")]
        before, _ = _measure_vm_steps(
            db, Graph(db, persist_identities=False).refresh_resolution_blocks
        )
        _add_unrelated_git_objects(db, unrelated, 4096)
        statements = []
        db.set_trace_callback(statements.append)
        try:
            after, _ = _measure_vm_steps(
                db, Graph(db, persist_identities=False).refresh_resolution_blocks
            )
        finally:
            db.set_trace_callback(None)
        assert after <= before + 2_000
        # No physical bytes or Git graph are needed to recompute an empty
        # conflict closure. Loading their rows would create linear work/memory.
        assert not any(
            "FROM STORED_BYTES" in statement.upper()
            or "FROM GIT_OBJECTS" in statement.upper()
            for statement in statements
        )
    finally:
        db.close()


def test_refresh_clears_prior_barriers_when_no_conflicts_remain(databases):
    db, _ = databases
    expected = fixture(db)
    _complete_claim(db, expected)
    db.execute("INSERT INTO exchange_blocked_results VALUES(?)", (expected["result"],))
    db.execute(
        "INSERT INTO exchange_blocked_coverage_claims SELECT coverage_claim_id FROM coverage_claims"
    )
    for kind, table, column in (
        ("profile", "parser_profile_selection_scopes", "selection_scope_uuidv4"),
        ("fact", "fact_selection_scopes", "fact_selection_scope_uuidv4"),
    ):
        scope = db.execute(f"SELECT {column} FROM {table}").fetchone()[0]
        db.execute(
            "INSERT INTO exchange_selection_blocks VALUES(?,?,?)",
            (kind, scope, "stale-synthetic-barrier"),
        )
    assert db.execute(
        "SELECT count(*) FROM current_document_observations"
    ).fetchone() == (0,)
    assert db.execute("SELECT coverage_state FROM current_coverage").fetchone() == (
        "conflict",
    )

    Graph(db).refresh_resolution_blocks()

    for table in (
        "exchange_blocked_results",
        "exchange_blocked_coverage_claims",
        "exchange_selection_blocks",
    ):
        assert db.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    assert db.execute(
        "SELECT count(*) FROM current_document_observations"
    ).fetchone() == (1,)
    assert db.execute("SELECT coverage_state FROM current_coverage").fetchone() == (
        "complete",
    )


def test_pending_selection_scopes_stay_blocked_without_conflict_seeds(databases):
    source, target = databases
    expected = fixture(source)
    unit = Graph(source).export(expected["repository"])
    assert receive(target, unit)["staged_records"] == 0
    ParserModel(target).trust_verification(expected["verification"])
    assert target.execute(
        "SELECT count(*) FROM current_document_observations"
    ).fetchone() == (1,)

    pending = copy.deepcopy(unit)
    pending["records"] = [
        record
        for record in pending["records"]
        if record["table"]
        in {"parser_profile_selection_decisions", "fact_selection_decisions"}
    ]
    for record in pending["records"]:
        identity_column = (
            "selection_decision_uuidv4"
            if record["table"] == "parser_profile_selection_decisions"
            else "fact_selection_decision_uuidv4"
        )
        record["values"][identity_column] = uid()
        record["key"] = (
            record["table"]
            + ":"
            + canonical({identity_column: record["values"][identity_column]})
        )
        # The new decision references a genuinely absent predecessor in the
        # same decision family. It cannot become a current selection head.
        record["values"]["predecessor_manifest_json"] = json.dumps([uid()])
    outcome = receive(target, pending)
    assert outcome["staged_records"] == 2
    assert target.execute(
        "SELECT count(*) FROM exchange_blocked_results"
    ).fetchone() == (0,)
    assert target.execute(
        "SELECT count(*) FROM exchange_blocked_coverage_claims"
    ).fetchone() == (0,)
    assert target.execute(
        "SELECT scope_kind,count(*) FROM exchange_selection_blocks GROUP BY scope_kind ORDER BY scope_kind"
    ).fetchall() == [("fact", 1), ("profile", 1)]
    assert target.execute(
        "SELECT count(*) FROM current_document_observations"
    ).fetchone() == (0,)


@pytest.mark.parametrize(
    "conflicted_table", ["document_observations", "completion_markers"]
)
def test_actual_local_conflicts_still_propagate_to_result_or_coverage(
    databases, conflicted_table
):
    source, target = databases
    expected = fixture(source)
    _complete_claim(source, expected)
    unit = Graph(source).export(expected["repository"])
    assert receive(target, unit)["staged_records"] == 0
    ParserModel(target).trust_verification(expected["verification"])
    variant = copy.deepcopy(unit)
    variant["records"] = [
        record for record in variant["records"] if record["table"] == conflicted_table
    ]
    record = variant["records"][0]
    if conflicted_table == "document_observations":
        record["values"]["author"] = "contradictory-domain-author"
    else:
        evidence = json.loads(record["values"]["evidence"])
        record["values"]["evidence"] = canonical(
            {**evidence, "hint": "contradictory-immutable-evidence"}
        )
    assert receive(target, variant)["staged_records"] == 1

    if conflicted_table == "document_observations":
        assert target.execute(
            "SELECT parsed_result_uuidv4 FROM exchange_blocked_results"
        ).fetchall() == [(expected["result"],)]
        assert target.execute(
            "SELECT count(*) FROM current_document_observations"
        ).fetchone() == (0,)
    else:
        assert target.execute(
            "SELECT count(*) FROM exchange_blocked_coverage_claims"
        ).fetchone() == (1,)
        assert target.execute(
            "SELECT coverage_state FROM current_coverage"
        ).fetchone() == ("conflict",)
