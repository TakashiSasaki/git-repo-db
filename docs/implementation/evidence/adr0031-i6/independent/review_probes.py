"""Independent baseline counterexamples; NOT an I6 implementation or v5 oracle.

Run with PYTHONPATH=src and the environment's unchanged Python/SQLite.
Only disposable :memory: connections are used. Product DDL files are never edited.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
import sys

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.domain.p1_context import (
    FieldClock,
    ResourceKey,
    TransferEventReport,
    canonical,
)
from repo_catalog.domain.parent_report import ParentReportKey
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from repo_catalog.domain.resource_stage import UnsupportedResourceStage

SERVICE = "11111111-1111-4111-8111-111111111111"
ISSUE = ResourceKey.from_native(SERVICE, "issue", "review-I7")
EVENT = ResourceKey.document(ISSUE, "comment", "timeline_event", "review-E")
ECLOCK, PCLOCK = FieldClock("provider", 100), FieldClock("provider", 50)
EPROV, PPROV = (
    canonical({"source": "review-event", "evidence": "E"}),
    canonical({"source": "review-parent", "evidence": "P"}),
)
FENCES = ("i2_transfer_stage_fence", "i2_transfer_report_stage_fence")
RESULTS = []


def database(isolated=True, parent=True):
    db = sqlite3.connect(":memory:", isolation_level=None)
    p1_schema.register_functions(db)
    p1_schema.configure(db)
    db.executescript(p1_schema.compose("context"))
    assert p1_schema.schema_rows(db) == p1_schema.expected_schema("context")
    if isolated:
        for name in FENCES:
            db.execute(f"DROP TRIGGER {name}")
    db.execute("INSERT INTO providers VALUES(?,?,?)", (SERVICE, "review", "{}"))
    store = ContextStore(db)
    # Child first, even in the baseline; namespace is identification, not Parent.
    store.resource(
        EVENT, identification=RI.scoped(EVENT, ISSUE, "timeline_event", "review-E")
    )
    assert db.execute("SELECT count(*) FROM resources").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM resource_relations").fetchone()[0] == 0
    store.resource(ISSUE)
    key = ParentReportKey(
        EVENT,
        canonical([list(ISSUE.coordinates())]),
        PPROV,
        canonical(
            {
                "clock": json.loads(PCLOCK.encode()),
                "document_kind": "timeline_event",
                "state": "complete",
            }
        ),
    )
    if parent:
        db.execute(
            "INSERT INTO resource_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)",
            (*key.coordinates(), 51),
        )
    return db, store, key


def report(parent, two=False):
    return TransferEventReport.from_targets(
        EVENT,
        clock=ECLOCK,
        provenance_json=EPROV,
        observed_at_us=101,
        parent_report=parent,
        to_target_json="null",
        from_target_json="null" if two else None,
    )


def counts(db):
    return [
        db.execute(
            "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchone()[0],
        db.execute("SELECT count(*) FROM resource_repository_relations").fetchone()[0],
    ]


def run(name, action):
    value = action()
    RESULTS.append({"id": name, "outcome": "PASS", "observation": value})


def authorization_baseline():
    db, store, parent = database()
    assert "admission" not in inspect.signature(store.admit_transfer_event).parameters
    unit = report(parent)
    first = store.admit_transfer_event(unit)
    replay = store.admit_transfer_event(unit)
    assert (first, replay, counts(db)) == ("insert", "duplicate", [1, 1])
    db.close()
    return {
        "admission_parameter": False,
        "without_local_policy": first,
        "replay_without_current_grant": replay,
        "interpretation": "I5-A1 remains in baseline; R10/R11/T07/T08 require future refusal",
    }


def independent_parent():
    db, store, parent = database()
    inferred = report(None)
    assert inferred.parent_scope_json != parent.scope_json
    try:
        store.admit_transfer_event(inferred)
    except ValueError as error:
        refusal = str(error)
        assert "eligible Parent report not found" in refusal
    else:
        raise AssertionError("expected false missing dependency from inferred Parent")
    assert counts(db) == [0, 0]
    assert store.admit_transfer_event(report(parent)) == "insert"
    assert (
        db.execute(
            "SELECT observed_at_us FROM resource_relations WHERE relation_kind='parent'"
        ).fetchone()[0]
        == 51
    )
    db.close()
    return {
        "inferred_parent_refusal": refusal,
        "explicit_parent": "insert",
        "parent_clock_time": [50, 51],
        "event_clock_time": [100, 101],
        "interpretation": "R08/T03 must remove constructor synthesis, preserve independent originals",
    }


def lost_endpoint():
    db, store, parent = database()
    full = report(parent, two=True)
    # Model a transport losing the from row BEFORE an old constructor is called.
    # Construct surviving endpoint afresh to avoid importing full-scope reference.
    truncated = report(parent, two=False)
    assert len(full.endpoints) == 2 and len(truncated.endpoints) == 1
    assert store.admit_transfer_event(truncated) == "insert"
    assert counts(db) == [1, 1]
    db.close()
    return {
        "original_endpoints": list(full.endpoints),
        "reconstructed_survivors": list(truncated.endpoints),
        "baseline": "insert",
        "interpretation": "I5-C1 reproduced; R09/V05/T05 must compare original declaration before filtering",
    }


def second_insert_rollback():
    db, store, parent = database()
    trace, seen = [], []
    db.set_trace_callback(trace.append)

    def observe():
        seen.append(counts(db))
        return 1

    db.create_function("review_observe", 0, observe)
    db.executescript("""CREATE TEMP TRIGGER review_abort_second BEFORE INSERT ON resource_repository_relations
        WHEN NEW.relation_kind='transfer_to_repository' BEGIN
        SELECT review_observe(); SELECT RAISE(ABORT,'review second INSERT'); END;""")
    try:
        store.admit_transfer_event(report(parent, two=True))
    except sqlite3.IntegrityError as error:
        assert "review second INSERT" in str(error)
        code = error.sqlite_errorname
    else:
        raise AssertionError("injected SQL error did not occur")
    assert seen == [[1, 1]], seen
    assert counts(db) == [0, 0]
    assert any("ROLLBACK TO p1_transfer_event" in sql for sql in trace)
    assert (
        db.execute(
            "SELECT observed_at_us FROM resource_relations WHERE relation_kind='parent'"
        ).fetchone()[0]
        == 51
    )
    assert not db.in_transaction
    db.close()
    return {
        "at_second_insert_event_endpoint_counts": seen,
        "after": [0, 0],
        "error": code,
        "trace": trace,
        "interpretation": "actual SQL rollback, unlike preflight-only tests; R15/T17",
    }


def ordinary_stage_refusal():
    db, store, parent = database(isolated=False)
    try:
        store.admit_transfer_event(report(parent))
    except UnsupportedResourceStage as error:
        code = error.code
    else:
        raise AssertionError("normal connection admitted Transfer")
    assert counts(db) == [0, 0]
    actual = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_schema WHERE name IN (?,?) ORDER BY name", FENCES
        )
    ]
    assert set(actual) == set(FENCES)
    db.close()
    return {"code": code, "fences": actual, "rows": [0, 0]}


if __name__ == "__main__":
    for name, action in [
        ("B-A1", authorization_baseline),
        ("B-B1", independent_parent),
        ("B-C1", lost_endpoint),
        ("B-D1", second_insert_rollback),
        ("B-STAGE", ordinary_stage_refusal),
    ]:
        run(name, action)
    db = sqlite3.connect(":memory:")
    print(
        json.dumps(
            {
                "python": sys.version,
                "executable": sys.executable,
                "sqlite": db.execute(
                    "SELECT sqlite_version(),sqlite_source_id()"
                ).fetchone(),
                "results": RESULTS,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
