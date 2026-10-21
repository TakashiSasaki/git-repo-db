#!/usr/bin/env python3
"""Reproduce isolated Context C-prime evidence; stdlib plus baseline source only."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
REPO = EVIDENCE.parents[3]
sys.path[:0] = [str(REPO / "src"), str(EVIDENCE / "candidates")]
import cprime as cp  # noqa: E402

from repo_catalog.adapters.sqlite import p1_schema  # noqa: E402
from repo_catalog.domain.time import validate_observation_us  # noqa: E402

J = cp.canonical
S = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"
R1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
R2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CLOCK = J({"domain": "synthetic-clock", "at_us": 99})
PROV = J({"source": "synthetic://fixture", "evidence": {"report": "A"}})
E9 = J(["issue", J("I7"), "timeline_event", "E9"])
I7 = J("I7")
RR_COLS = (
    "service_instance_uuidv4",
    "resource_kind",
    "provider_resource_id",
    "relation_kind",
    "members_json",
    "provenance_json",
    "scope_json",
    "observed_at_us",
)
END_COLS = (
    "service_instance_uuidv4",
    "resource_kind",
    "provider_resource_id",
    "relation_kind",
    "target_json",
    "clock_json",
    "provenance_json",
    "observed_at_us",
    "event_report_members_json",
    "event_report_scope_json",
)
OBSERVED = (
    "resources",
    "resource_relations",
    "resource_repository_relations",
    "collections",
    "collection_terminals",
    "field_candidates",
)
CASES = []
ACTIVE = None


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn

    return wrap


def rows(db):
    result = {}
    for table in OBSERVED:
        result[table] = [
            list(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY 1,2,3")
        ]
    return result


def check(db):
    return {
        "foreign_key_check": [list(r) for r in db.execute("PRAGMA foreign_key_check")],
        "integrity_check": [r[0] for r in db.execute("PRAGMA integrity_check")],
    }


def checkpoint(db, name):
    receipt = check(db)
    ACTIVE["checkpoints"].append({"name": name, **receipt})
    assert receipt == {"foreign_key_check": [], "integrity_check": ["ok"]}, receipt


def step(db, label, fn, error=None, contains=None):
    sql = []
    db.set_trace_callback(lambda s: sql.append(s) if s not in sql else None)
    record = {
        "label": label,
        "expected": error.__name__ if error else "success",
        "transaction_before": db.in_transaction,
    }
    result = None
    try:
        result = fn()
        record["actual"] = "success"
        if error:
            raise AssertionError(f"{label}: expected {error.__name__}, no error")
    except Exception as exc:
        record["actual"] = type(exc).__name__
        record["error"] = str(exc)
        if hasattr(exc, "sqlite_errorname"):
            record["sqlite_errorname"] = exc.sqlite_errorname
        if (
            error is None
            or not isinstance(exc, error)
            or (contains and contains not in str(exc))
        ):
            raise
    finally:
        db.set_trace_callback(None)
        record["sql"] = sql
        record["transaction_after"] = db.in_transaction
        ACTIVE["steps"].append(record)
    return result


def insert(db, table, cols, values, prefix="INSERT"):
    return db.execute(
        f"{prefix} INTO {table}({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",
        values,
    )


def resource(
    db, kind, value, service=S, doc="timeline_event", namespace="issue", ns="I7"
):
    # Fixtures supply native coordinates; encode the namespace exactly once.
    identity = J([value[0], J(value[1]), *value[2:]]) if kind in cp.TYPED else J(value)
    extra = (namespace, J(ns), doc, J(value[3])) if kind in cp.TYPED else (None,) * 4
    db.execute(
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)", (service, kind, identity, *extra)
    )
    return identity


def new(path=":memory:"):
    db = cp.connect(path)
    db.execute("INSERT INTO providers VALUES(?,?,?)", (S, "synthetic", "{}"))
    db.execute("INSERT INTO providers VALUES(?,?,?)", (S2, "synthetic", "{}"))
    for r in (R1, R2):
        db.execute("INSERT INTO repository_context VALUES(?,?)", (r, "{}"))
    return db


def event_resource(db, event="E9", doc="timeline_event", service=S):
    return resource(db, "comment", ["issue", "I7", doc, event], service, doc)


def parent_row(
    event=E9,
    target="I7",
    *,
    prov=PROV,
    clock=CLOCK,
    doc="timeline_event",
    kind="issue",
    service=S,
    observed=100,
):
    return (
        service,
        "comment",
        event,
        "parent",
        J([[service, kind, J(target)]]),
        prov,
        J({"clock": json.loads(clock), "document_kind": doc, "state": "complete"}),
        observed,
    )


def report_row(
    parent=None,
    endpoints=None,
    *,
    event_type="transferred",
    provider=None,
    report_prov=None,
    report_clock=None,
    report_observed="same-as-parent",
):
    p = parent or parent_row()
    endpoints = (
        endpoints
        if endpoints is not None
        else [["transfer_from_repository", J(R1)], ["transfer_to_repository", J(R2)]]
    )
    members = [[p[0], "repository", J(provider)]] if provider else []
    roles = set(e[0] for e in endpoints)
    if provider:
        roles.add("transfer_from_repository")
    scope = {
        "clock": json.loads(report_clock)
        if report_clock is not None
        else json.loads(p[6])["clock"],
        "event_type": event_type,
        "from_provider_repository_id": J(provider) if provider else None,
        "to_provider_repository_id": None,
        "provided_roles": sorted(roles),
        "parent_members_json": p[4],
        "parent_scope_json": p[6],
        "parent_provenance_json": p[5],
        "endpoints": endpoints,
    }
    return (
        *p[:3],
        "transfer_event_report",
        J(members),
        report_prov if report_prov is not None else p[5],
        J(scope),
        p[7] if report_observed == "same-as-parent" else report_observed,
    )


def endpoint_rows(report):
    scope = json.loads(report[6])
    return [
        (
            *report[:3],
            role,
            target,
            J(scope["clock"]),
            report[5],
            report[7],
            report[4],
            report[6],
        )
        for role, target in scope["endpoints"]
    ]


def rr(db, row, prefix="INSERT"):
    return insert(db, "resource_relations", RR_COLS, row, prefix)


def end(db, row, prefix="INSERT"):
    return insert(db, "resource_repository_relations", END_COLS, row, prefix)


def replay(db, table, cols, row, key_cols):
    key = [row[cols.index(c)] for c in key_cols]
    old = db.execute(
        f"SELECT {','.join(cols)} FROM {table} WHERE "
        + " AND ".join(f"{c} IS ?" for c in key_cols),
        key,
    ).fetchone()
    if old is not None:
        if tuple(old) != tuple(row):
            raise ValueError("immutable replay payload mismatch")
        return "duplicate"
    insert(db, table, cols, row)
    return "insert"


def replay_rr(db, row):
    return replay(db, "resource_relations", RR_COLS, row, RR_COLS[:7])


def replay_end(db, row):
    return replay(db, "resource_repository_relations", END_COLS, row, END_COLS[:7])


def structural_admit(db, report, endpoints=None):
    """Earlier bounded admission diagnostic; does not settle G3 qualification."""
    validate_observation_us(report[7])
    cp.event(report[0], report[1], report[4], report[6])
    if json.loads(report[6])["event_type"] != "transferred":
        raise ValueError("actual normalized event_type must be transferred")
    expected = endpoint_rows(report)
    supplied = expected if endpoints is None else endpoints
    for item in supplied:
        validate_observation_us(item[7])
    if sorted(supplied) != sorted(expected):
        raise ValueError("whole original endpoint unit required")
    db.execute("SAVEPOINT transfer_unit")
    try:
        # Whole Provider membership is an arbitrary-length JSON group. Its
        # referents require typed admission checks; no projected-array FK is claimed.
        for coordinates in json.loads(report[4]):
            if not db.execute(
                "SELECT 1 FROM resources WHERE service_instance_uuidv4=? "
                "AND resource_kind=? AND provider_resource_id=?",
                coordinates,
            ).fetchone():
                raise ValueError(
                    "missing declared Provider Repository member; withhold whole Transfer unit"
                )
        outcome = replay_rr(db, report)
        for item in supplied:
            replay_end(db, item)
        db.execute("RELEASE transfer_unit")
        return outcome
    except BaseException:
        db.execute("ROLLBACK TO transfer_unit")
        db.execute("RELEASE transfer_unit")
        raise


class QualificationRequired(ValueError):
    """An unresolved Q-S10 interpretation withholds the dependent operation."""


def admit(db, report, endpoints=None):
    """Supported experimental admission; unresolved G3 never becomes success.

    This temporary withholding boundary is not a universal Parent-equality rule
    or an owner decision that a mismatched report is intrinsically invalid.
    """
    cp.event(report[0], report[1], report[4], report[6])
    source = db.execute(
        "SELECT identifier_namespace_kind,identifier_namespace_id FROM resources "
        "WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
        report[:3],
    ).fetchone()
    scope = json.loads(report[6])
    target = json.loads(scope["parent_members_json"])[0]
    if source is not None and source != (target[1], target[2]):
        raise QualificationRequired(
            "Q-S10 namespace/Parent mismatch requires owner qualification"
        )
    return structural_admit(db, report, endpoints)


def seed(db, *, report=False):
    event_resource(db)
    resource(db, "issue", "I7")
    rr(db, parent_row())
    if report:
        admit(db, report_row())


@case("T01_identity_exact_and_rejected_inputs")
def t01(db):
    values = [
        "",
        [],
        [""],
        [[]],
        "9" * 120,
        "A",
        "a",
        " A ",
        "e\u0301",
        "é",
        '\n"\\',
        ["a", ["b", []]],
        ["a", "b"],
        ["b", "a"],
    ]
    for i, v in enumerate(values):
        step(
            db,
            f"legitimate synthetic opaque complete identity {i}",
            lambda v=v: resource(db, "synthetic.opaque", v),
        )
    step(
        db,
        "exact resource replay unique error",
        lambda: resource(db, "synthetic.opaque", values[0]),
        sqlite3.IntegrityError,
        "UNIQUE",
    )
    assert len(db.execute("SELECT * FROM resources").fetchall()) == len(values)
    for raw in (
        "1",
        "true",
        "false",
        "{}",
        "null",
        None,
        "not json",
        '["a",1]',
        '[ "a" ]',
        '"\\u0061"',
        '["x",null]',
    ):
        step(
            db,
            f"invalid identity {raw!r}",
            lambda raw=raw: db.execute(
                "INSERT INTO resources VALUES(?,?,?,NULL,NULL,NULL,NULL)",
                (S, "synthetic.opaque", raw),
            ),
            sqlite3.IntegrityError,
        )
    step(
        db,
        "known comment cannot fall through generic",
        lambda: db.execute(
            "INSERT INTO resources VALUES(?,?,?,NULL,NULL,NULL,NULL)",
            (S, "comment", J("E9")),
        ),
        sqlite3.IntegrityError,
    )
    step(
        db,
        "known PR document preserves coordinates",
        lambda: resource(
            db,
            "document",
            ["pull_request", "PR1", "body", "body"],
            doc="body",
            namespace="pull_request",
            ns="PR1",
        ),
    )
    assert (
        len(
            db.execute(
                "SELECT * FROM resources WHERE provider_resource_id IN (?,?,?,?)",
                tuple(J(v) for v in values[:4]),
            ).fetchall()
        )
        == 4
    )


@case("T02_T03_child_parent_arrival_original_replay")
def t0203(db):
    step(db, "child first", lambda: event_resource(db))
    original = rows(db)
    step(
        db,
        "missing Parent rejects relationship",
        lambda: rr(db, parent_row()),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    step(
        db,
        "missing Parent support rejects Transfer unit",
        lambda: admit(db, report_row()),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    assert rows(db) == original
    step(
        db,
        "genuinely supplied bare Parent admitted",
        lambda: resource(db, "issue", "I7"),
    )
    assert not db.execute("SELECT * FROM resource_relations").fetchall()
    assert not db.execute("SELECT * FROM field_candidates").fetchall()
    step(
        db,
        "Parent alone is no support",
        lambda: end(db, endpoint_rows(report_row())[0]),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    step(db, "resupplied original Parent report", lambda: rr(db, parent_row()))
    step(db, "resupplied original Transfer", lambda: admit(db, report_row()))
    before = rows(db)
    assert (
        step(db, "identical Transfer replay", lambda: admit(db, report_row()))
        == "duplicate"
    )
    assert (
        step(db, "identical Parent replay", lambda: replay_rr(db, parent_row()))
        == "duplicate"
    )
    assert before == rows(db)
    assert (
        db.execute(
            "SELECT provider_resource_id FROM resources WHERE resource_kind='comment'"
        ).fetchone()[0]
        == E9
    )
    checkpoint(db, "after original replay")


@case("T04_typed_reference_rejections")
def t04(db):
    event_resource(db)
    resource(db, "issue", "I7")
    resource(db, "repository", "repo")
    for label, p in (
        ("missing Parent", parent_row(target="missing")),
        ("wrong kind", parent_row(target="repo", kind="repository")),
    ):
        step(db, label, lambda p=p: rr(db, p), sqlite3.IntegrityError)
    p = list(parent_row())
    p[4] = J([[S2, "issue", I7]])
    resource(db, "issue", "I7", S2)
    step(db, "wrong service namespace", lambda: rr(db, p), sqlite3.IntegrityError)
    rr(db, parent_row())
    ev = event_resource(db, "E10")
    p = parent_row(event=ev)
    rr(db, p)
    report = report_row()
    forged = list(endpoint_rows(report)[0])
    forged[2] = ev
    step(
        db,
        "wrong Event cannot borrow report",
        lambda: end(db, forged),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    ordinary = event_resource(db, "C1", doc="comment")
    p = parent_row(event=ordinary, doc="timeline_event")
    step(
        db,
        "ordinary Comment fails typed source FK",
        lambda: rr(db, p),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    p = parent_row(event=ordinary, doc="comment")
    rr(db, p)
    forged = list(endpoint_rows(report_row())[0])
    forged[2] = ordinary
    step(
        db,
        "ordinary Comment cannot transfer",
        lambda: end(db, forged),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    missing = report_row(
        parent_row(prov=J({"source": "synthetic://missing", "evidence": "B"}))
    )
    step(
        db,
        "nonexistent support exact provenance",
        lambda: rr(db, missing),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )


@case("T05_exact_report_coherence_one_sided_and_clocks")
def t05(db):
    seed(db)
    one = report_row(endpoints=[["transfer_from_repository", J(R1)]])
    step(db, "genuine one sided report", lambda: admit(db, one))
    assert (
        len(db.execute("SELECT * FROM resource_repository_relations").fetchall()) == 1
    )
    missing = list(endpoint_rows(report_row())[1])
    missing[-1] = one[6]
    step(
        db,
        "cannot invent absent endpoint",
        lambda: end(db, missing),
        sqlite3.IntegrityError,
        "CHECK",
    )
    step(
        db,
        "cannot enlarge immutable original group",
        lambda: rr(db, report_row()),
        sqlite3.IntegrityError,
        "whole event report",
    )
    changed = list(endpoint_rows(one)[0])
    changed[7] = 101
    step(
        db,
        "cannot change observation",
        lambda: end(db, changed),
        sqlite3.IntegrityError,
    )
    wrong = list(endpoint_rows(one)[0])
    wrong[5] = J({"domain": "other", "at_us": 99})
    step(
        db,
        "cannot cross pair clocks",
        lambda: end(db, wrong),
        sqlite3.IntegrityError,
        "CHECK",
    )
    invalid = report_row(
        parent_row(prov=J({"source": "synthetic://invalid", "evidence": "N"})),
        endpoints=[["transfer_from_repository", "null"]],
        provider="provider1",
    )
    step(
        db,
        "explicit NULL cannot also be unresolved Provider",
        lambda: rr(db, invalid),
        sqlite3.IntegrityError,
        "CHECK",
    )
    nullp = parent_row(
        prov=J({"source": "synthetic://null", "evidence": "N"}), observed=None
    )
    rr(db, nullp)
    nullr = report_row(nullp)
    admit(db, nullr)
    changed = list(endpoint_rows(nullr)[0])
    changed[7] = 1
    step(
        db,
        "NULL original time is not wildcard",
        lambda: end(db, changed),
        sqlite3.IntegrityError,
    )


@case("T05_independent_Parent_report_provenance_and_clock")
def t05_independent(db):
    event_resource(db)
    resource(db, "issue", "I7")
    independent_parent = parent_row(
        prov=J({"source": "synthetic://parent-only", "evidence": "P"}),
        clock=J({"domain": "parent-domain", "at_us": 41}),
        observed=42,
    )
    rr(db, independent_parent)
    report = report_row(
        independent_parent, report_prov=PROV, report_clock=CLOCK, report_observed=100
    )
    step(
        db,
        "explicit original Parent support with independent provenance and clock",
        lambda: admit(db, report),
    )
    stored = db.execute(
        "SELECT provenance_json,scope_json,observed_at_us FROM resource_relations WHERE relation_kind='parent'"
    ).fetchone()
    assert stored == (independent_parent[5], independent_parent[6], 42)
    endpoint = db.execute(
        "SELECT provenance_json,clock_json,observed_at_us,support_provenance_json,support_scope_json FROM resource_repository_relations LIMIT 1"
    ).fetchone()
    assert endpoint == (PROV, CLOCK, 100, independent_parent[5], independent_parent[6])
    for name, value in (
        ("parent_provenance_json", PROV),
        ("parent_scope_json", parent_row()[6]),
    ):
        altered = json.loads(report[6])
        altered[name] = value
        forged = list(report)
        forged[5] = J({"source": "synthetic://independent-negative", "evidence": name})
        forged[6] = J(altered)
        step(
            db,
            "cannot cross-pair independently sourced support " + name,
            lambda forged=forged: rr(db, forged),
            sqlite3.IntegrityError,
            "FOREIGN KEY",
        )
    missing = json.loads(report[6])
    del missing["parent_provenance_json"]
    forged = list(report)
    forged[5] = J({"source": "synthetic://missing-parent-provenance", "evidence": "N"})
    forged[6] = J(missing)
    step(
        db,
        "missing Parent provenance cannot null-bypass FK",
        lambda: rr(db, forged),
        sqlite3.IntegrityError,
        "CHECK",
    )
    ACTIVE["evaluation"] = (
        "Exact support is explicitly supplied. Independent clocks/attribution remain original; no semantic winner or external authenticity follows."
    )


@case("T06_competing_attributed_reports")
def t06(db):
    event_resource(db)
    resource(db, "issue", "I7")
    resource(db, "issue", "I8")
    p1 = parent_row()
    p2 = parent_row(
        target="I8", prov=J({"source": "synthetic://other", "evidence": "B"})
    )
    step(db, "first Parent report", lambda: rr(db, p1))
    step(db, "alternative Parent report", lambda: rr(db, p2))
    step(
        db,
        "same target independent attribution",
        lambda: rr(
            db, parent_row(prov=J({"source": "synthetic://third", "evidence": "C"}))
        ),
    )
    step(
        db,
        "same Event clock provenance can preserve competing target",
        lambda: rr(db, parent_row(target="I8")),
    )
    step(
        db,
        "Transfer explicitly supported by report A",
        lambda: admit(db, report_row(p1)),
    )
    step(
        db,
        "structural diagnostic only: Transfer explicitly supported by report B",
        lambda: structural_admit(db, report_row(p2)),
    )
    assert (
        db.execute(
            "SELECT count(*) FROM resource_relations WHERE relation_kind='parent'"
        ).fetchone()[0]
        == 4
    )
    r = report_row(p2)
    forged = list(endpoint_rows(r)[0])
    forged[6] = PROV
    step(
        db,
        "same Event cannot borrow B under A attribution",
        lambda: end(db, forged),
        sqlite3.IntegrityError,
    )
    ACTIVE["evaluation"] = (
        "All four Parent reports remain. The experiment infers no semantic winner or issuer authenticity."
    )


@case("T07_NULL_cardinality_malformed_generated_and_layers")
def t07(db):
    event_resource(db)
    resource(db, "issue", "I7")
    for label, m in (
        ("zero", "[]"),
        ("multiple", J([[S, "issue", I7], [S, "issue", I7]])),
        ("missing key", J([[S, "issue"]])),
        ("NULL ID", J([[S, "issue", None]])),
        ("wrong JSON type", "{}"),
        ("noncanonical", '[ ["x"] ]'),
        ("numeric ID", J([[S, "issue", "7"]])),
    ):
        p = list(parent_row())
        p[4] = m
        step(db, label, lambda p=p: rr(db, p), sqlite3.IntegrityError)
    for col in (0, 1, 2, 4, 5, 6):
        p = list(parent_row())
        p[col] = None
        step(
            db,
            f"Parent NULL coordinate {col}",
            lambda p=p: rr(db, p),
            sqlite3.IntegrityError,
        )
    rr(db, parent_row())
    r = report_row()
    rr(db, r)
    resource(db, "issue", "")
    step(
        db,
        "genuine empty Parent ID remains nonnull complete coordinate",
        lambda: rr(db, parent_row(target="")),
    )
    for cols in ((8,), (9,), (8, 9)):
        e = list(endpoint_rows(r)[0])
        for col in cols:
            e[col] = None
        step(
            db,
            f"support partial/all NULL {cols}",
            lambda e=e: end(db, e),
            sqlite3.IntegrityError,
            "CHECK",
        )
    scope = json.loads(r[6])
    del scope["parent_scope_json"]
    e = list(endpoint_rows(r)[0])
    e[9] = J(scope)
    step(
        db,
        "missing generated value",
        lambda: end(db, e),
        sqlite3.IntegrityError,
        "CHECK",
    )
    step(
        db,
        "generated column cannot be supplied",
        lambda: db.execute(
            "INSERT INTO resource_relations(service_instance_uuidv4,parent_kind) VALUES(?,?)",
            (S, "issue"),
        ),
        sqlite3.OperationalError,
        "generated",
    )
    # Distinguish SQL CHECK's NULL acceptance and FK's partial-NULL escape using TEMP controls only.
    db.execute("CREATE TEMP TABLE check_control(x INTEGER CHECK(x>0))")
    step(
        db,
        "raw CHECK(NULL) accepts",
        lambda: db.execute("INSERT INTO check_control VALUES(NULL)"),
    )
    db.execute("CREATE TEMP TABLE fk_parent(a,b,UNIQUE(a,b))")
    db.execute(
        "CREATE TEMP TABLE fk_child(a,b,FOREIGN KEY(a,b) REFERENCES fk_parent(a,b))"
    )
    step(
        db,
        "raw partial NULL FK accepts",
        lambda: db.execute("INSERT INTO fk_child VALUES(1,NULL)"),
    )
    step(
        db,
        "raw complete FK rejects",
        lambda: db.execute("INSERT INTO fk_child VALUES(1,2)"),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    ACTIVE["control_rowsets"] = {
        "check_control": [list(x) for x in db.execute("SELECT * FROM check_control")],
        "fk_child": [list(x) for x in db.execute("SELECT * FROM fk_child")],
    }
    db.execute("DROP TABLE fk_child")
    db.execute("DROP TABLE fk_parent")
    db.execute("DROP TABLE check_control")


@case("T08_mutation_conflict_paths")
def t08(db):
    seed(db, report=True)
    before = rows(db)
    original_resource = db.execute(
        "SELECT service_instance_uuidv4,resource_kind,provider_resource_id,"
        "identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id "
        "FROM resources WHERE resource_kind='comment'"
    ).fetchone()
    changed_resource = list(original_resource)
    changed_resource[4] = J("WRONG")
    for prefix in ("INSERT", "INSERT OR IGNORE", "INSERT OR REPLACE"):
        step(
            db,
            prefix + " invalid Resource replay rejects",
            lambda prefix=prefix: db.execute(
                prefix + " INTO resources VALUES(?,?,?,?,?,?,?)", changed_resource
            ),
            sqlite3.IntegrityError,
            "rebind",
        )
    step(
        db,
        "Resource DO NOTHING invalid replay rejects",
        lambda: db.execute(
            "INSERT INTO resources VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            changed_resource,
        ),
        sqlite3.IntegrityError,
        "rebind",
    )
    step(
        db,
        "Resource exact REPLACE remains immutable",
        lambda: db.execute(
            "INSERT OR REPLACE INTO resources VALUES(?,?,?,?,?,?,?)", original_resource
        ),
        sqlite3.IntegrityError,
        "immutable",
    )
    for table in ("resources", "resource_relations", "resource_repository_relations"):
        step(
            db,
            f"UPDATE {table}",
            lambda table=table: db.execute(
                f"UPDATE {table} SET provider_resource_id=provider_resource_id"
            ),
            sqlite3.IntegrityError,
            "immutable",
        )
        step(
            db,
            f"DELETE {table}",
            lambda table=table: db.execute(f"DELETE FROM {table}"),
            sqlite3.IntegrityError,
        )
    step(
        db,
        "REPLACE Parent exact input",
        lambda: rr(db, parent_row(), "INSERT OR REPLACE"),
        sqlite3.IntegrityError,
        "immutable",
    )
    step(
        db,
        "REPLACE endpoint exact input",
        lambda: end(db, endpoint_rows(report_row())[0], "INSERT OR REPLACE"),
        sqlite3.IntegrityError,
    )
    conflict = list(parent_row())
    conflict[7] = 101
    for prefix in ("INSERT", "INSERT OR IGNORE", "INSERT OR REPLACE"):
        step(
            db,
            f"{prefix} changed observation",
            lambda prefix=prefix: rr(db, conflict, prefix),
            sqlite3.IntegrityError,
            "rebind",
        )
    query = (
        "INSERT INTO resource_relations("
        + ",".join(RR_COLS)
        + ") VALUES("
        + ",".join("?" for _ in RR_COLS)
        + ") ON CONFLICT DO NOTHING"
    )
    step(
        db,
        "ON CONFLICT DO NOTHING changed payload still rejects",
        lambda: db.execute(query, conflict),
        sqlite3.IntegrityError,
        "rebind",
    )
    step(
        db,
        "ON CONFLICT DO UPDATE rejects",
        lambda: db.execute(
            query.replace(
                "DO NOTHING", "DO UPDATE SET observed_at_us=excluded.observed_at_us"
            ),
            parent_row(),
        ),
        sqlite3.IntegrityError,
        "immutable",
    )
    changed_endpoint = list(endpoint_rows(report_row())[0])
    changed_endpoint[8] = J([[S, "repository", J("missing")]])
    statement = (
        "INSERT INTO resource_repository_relations("
        + ",".join(END_COLS)
        + ") VALUES("
        + ",".join("?" for _ in END_COLS)
        + ") ON CONFLICT DO NOTHING"
    )
    step(
        db,
        "endpoint support nonkey rebind cannot hide in DO NOTHING",
        lambda: db.execute(statement, changed_endpoint),
        sqlite3.IntegrityError,
        "rebind",
    )
    step(
        db,
        "typed replay rejects changed payload",
        lambda: replay_rr(db, conflict),
        ValueError,
        "payload",
    )
    assert rows(db) == before


@case("T09_transaction_order_rollback_and_configuration")
def t09(db):
    step(db, "BEGIN", lambda: db.execute("BEGIN"))
    event_resource(db)
    step(
        db,
        "immediate FK rejects before Parent",
        lambda: rr(db, parent_row()),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    assert db.in_transaction
    step(
        db,
        "foreign_keys OFF inside transaction is ineffective",
        lambda: db.execute("PRAGMA foreign_keys=OFF"),
    )
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    step(db, "ROLLBACK entire unit", db.rollback)
    assert not db.execute("SELECT * FROM resources").fetchall()
    step(db, "BEGIN good order", lambda: db.execute("BEGIN"))
    seed(db)
    admit(db, report_row())
    step(db, "COMMIT good unit", db.commit)
    checkpoint(db, "committed unit")
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "reopen.sqlite3")
        other = new(path)
        seed(other, report=True)
        original = rows(other)
        other.close()
        reopened = cp.connect(path, fresh=False)
        ACTIVE["reopen_pragmas"] = {
            p: reopened.execute(f"PRAGMA {p}").fetchone()[0]
            for p in ("foreign_keys", "recursive_triggers", "synchronous")
        }
        assert rows(reopened) == original
        checkpoint(reopened, "separate connection reopens committed evidence")
        reopened.close()
    ACTIVE["constraint_timing"] = (
        "All candidate FKs are immediate; no DEFERRABLE constraint or COMMIT hook is claimed."
    )


@case("T09_unsupported_misconfiguration_control")
def t09bad(db):
    event_resource(db)
    step(
        db,
        "disable FKs outside transaction (unsupported)",
        lambda: db.execute("PRAGMA foreign_keys=OFF"),
    )
    step(db, "unsupported orphan can then be inserted", lambda: rr(db, parent_row()))
    step(
        db,
        "reenable does not retroactively reject",
        lambda: db.execute("PRAGMA foreign_keys=ON"),
    )
    violations = [list(x) for x in db.execute("PRAGMA foreign_key_check")]
    assert violations
    ACTIVE["deliberate_violations"] = violations
    ACTIVE["skip_final_integrity"] = (
        "Deliberately unsupported foreign_keys=OFF orphan, disposed after recording."
    )
    # recursive_triggers OFF permits REPLACE deletion despite no-delete trigger.
    other = new()
    seed(other)
    other.execute("PRAGMA recursive_triggers=OFF")
    step(
        other,
        "unsupported REPLACE bypass without recursive triggers",
        lambda: rr(other, parent_row(), "INSERT OR REPLACE"),
    )
    other.close()


@case("T10_general_coherent_groups_and_collections")
def t10(db):
    resource(db, "synthetic.opaque", "root")
    root = (S, "synthetic.opaque", J("root"))
    # Unrecognized resource kind participates through common format; does not gain typed meaning.
    for key in ("a", "b"):
        resource(db, "synthetic.opaque", key)
    a = [S, "synthetic.opaque", J("a")]
    b = [S, "synthetic.opaque", J("b")]
    for state, members in (
        ("unknown", []),
        ("complete", []),
        ("partial", [a]),
        ("complete", [a, b]),
    ):
        row = (*root, "general-members", J(members), PROV, J({"state": state}), 100)
        step(db, f"general {state} {members}", lambda row=row: rr(db, row))
    step(
        db,
        "multi-member relation cannot shrink by UPDATE",
        lambda: db.execute(
            "UPDATE resource_relations SET members_json='[]' WHERE members_json=?",
            (J([a, b]),),
        ),
        sqlite3.IntegrityError,
        "immutable",
    )
    db.execute(
        "INSERT INTO collections VALUES(?,?,?,?,?,?)",
        (*root, "members", PROV, J({"state": "declared"})),
    )
    for time, state, members in (
        (100, "unknown", []),
        (101, "complete", []),
        (102, "partial", [a]),
        (103, "complete", [a, b]),
    ):
        step(
            db,
            f"Collection terminal {state}/{time}",
            lambda time=time, state=state, members=members: db.execute(
                "INSERT INTO collection_terminals VALUES(?,?,?,?,?,?,?,?)",
                (*root, "members", PROV, time, state, J(members)),
            ),
        )
    assert db.execute("SELECT count(*) FROM resource_relations").fetchone()[0] == 4
    assert db.execute("SELECT count(*) FROM collection_terminals").fetchone()[0] == 4
    step(
        db,
        "malformed generic member key rejected",
        lambda: rr(
            db, (*root, "generic-bad", J([[S, "synthetic.opaque"]]), PROV, "{}", 100)
        ),
        sqlite3.IntegrityError,
    )
    # B3: generic coherent relations need not form a tree; Documents may own groups.
    doc_id = resource(
        db,
        "document",
        ["pull_request", "PR1", "body", "body"],
        doc="body",
        namespace="pull_request",
        ns="PR1",
    )
    doc_key = [S, "document", doc_id]
    for owner, member_key in ((doc_key, a), (a, b), (b, a)):
        relation = (
            *owner,
            "synthetic.links",
            J([member_key]),
            PROV,
            J({"state": "complete"}),
            100,
        )
        step(
            db,
            "nonleaf Document or generic cycle " + owner[2],
            lambda relation=relation: rr(db, relation),
        )
    ACTIVE["absence_control"] = db.execute(
        "SELECT count(*) FROM resource_relations WHERE relation_kind='never_observed'"
    ).fetchone()[0]


@case("T11_experimental_reconstruction_and_snapshot")
def t11(db):
    seed(db, report=True)
    original = rows(db)
    destination = new()
    event_resource(destination)
    step(
        destination,
        "selected child admitted without Parent",
        lambda: destination.execute("BEGIN"),
    )
    step(
        destination,
        "omitted Parent withholds complete relation",
        lambda: rr(destination, parent_row()),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    step(destination, "commit independent child", destination.commit)
    assert not destination.execute("SELECT * FROM resource_relations").fetchall()
    resource(destination, "issue", "I7")
    step(
        destination,
        "Parent present support omitted withholds report",
        lambda: admit(destination, report_row()),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    assert not destination.execute("SELECT * FROM resource_relations").fetchall()
    rr(destination, parent_row())
    step(
        destination,
        "selected endpoint cut rejected before unit writes",
        lambda: admit(destination, report_row(), endpoint_rows(report_row())[:1]),
        ValueError,
        "whole original",
    )
    assert not destination.execute(
        "SELECT * FROM resource_repository_relations"
    ).fetchall()
    step(
        destination,
        "original full supplied data after dependencies",
        lambda: admit(destination, report_row()),
    )
    assert rows(destination) == original
    checkpoint(destination, "reconstructed references")
    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "snapshot.sqlite3")
        snapshot = sqlite3.connect(path, isolation_level=None)
        db.backup(snapshot)
        snapshot.close()
        reopened = cp.connect(path, fresh=False)
        assert rows(reopened) == original
        checkpoint(reopened, "snapshot reference preservation")
        reopened.close()
    destination.close()
    # Generic common-format reconstruction retains explicit selection and full groups.
    generic_source = new()
    for ident in ("root", "a", "b", "unselected"):
        resource(generic_source, "vendor.future", ident)
    group = (
        S,
        "vendor.future",
        J("root"),
        "future.members",
        J([[S, "vendor.future", J("a")], [S, "vendor.future", J("b")]]),
        PROV,
        J({"state": "complete", "ordered": True}),
        88,
    )
    rr(generic_source, group)
    target = new()
    for ident in ("root", "a"):
        resource(target, "vendor.future", ident)

    def generic_admit():
        for coord in json.loads(group[4]):
            if not target.execute(
                "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
                coord,
            ).fetchone():
                raise ValueError(
                    "missing selected generic member; withhold original whole group"
                )
        return replay_rr(target, group)

    step(
        target,
        "unselected member withholds full generic group",
        generic_admit,
        ValueError,
        "whole group",
    )
    assert not target.execute("SELECT * FROM resource_relations").fetchall()
    resource(target, "vendor.future", "b")
    step(
        target,
        "resupply original generic report after selected dependencies",
        generic_admit,
    )
    step(target, "exact generic replay", generic_admit)
    assert not target.execute(
        "SELECT * FROM resources WHERE provider_resource_id=?", (J("unselected"),)
    ).fetchall()
    assert target.execute(
        "SELECT members_json,scope_json,observed_at_us FROM resource_relations"
    ).fetchone() == (group[4], group[6], 88)
    ACTIVE["generic_selected_rowsets"] = rows(target)
    checkpoint(target, "generic common-format reconstructed")
    generic_source.close()
    target.close()
    ACTIVE["scope"] = (
        "Experimental Context-only reconstruction/SQLite backup harness; not product Exchange or paired Core+Context recovery acceptance."
    )


@case("T11_missing_Provider_member_withheld_and_original_resupplied")
def t11_provider_member(db):
    seed(db)
    original_report = report_row(provider="absent-provider-repository", endpoints=[])
    before = rows(db)
    step(
        db,
        "missing declared Provider member withholds whole Transfer",
        lambda: admit(db, original_report),
        ValueError,
        "missing declared Provider Repository member",
    )
    assert rows(db) == before
    assert not db.execute(
        "SELECT * FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchall()
    assert not db.execute("SELECT * FROM resource_repository_relations").fetchall()
    assert not db.execute(
        "SELECT * FROM resources WHERE resource_kind='repository'"
    ).fetchall()
    step(
        db,
        "actual selected Provider member arrives",
        lambda: resource(db, "repository", "absent-provider-repository"),
    )
    assert not db.execute(
        "SELECT * FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchall()
    step(
        db, "original unresolved report resupplied", lambda: admit(db, original_report)
    )
    stored = db.execute(
        "SELECT members_json,provenance_json,scope_json,observed_at_us FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchone()
    assert stored == original_report[4:]
    assert not db.execute("SELECT * FROM resource_repository_relations").fetchall()
    after = rows(db)
    assert (
        step(db, "exact unresolved report replay", lambda: admit(db, original_report))
        == "duplicate"
    )
    assert rows(db) == after
    ACTIVE["boundary"] = (
        "Provider member existence is a typed-admission dependency check inside the savepoint. Unresolved Provider-to-Core mapping does not become an observed NULL or invented Repository endpoint."
    )


@case("T12_strict_original_observation_types_before_affinity_or_replay")
def t12_time(db):
    seed(db)
    before = rows(db)
    for value in (True, False, 100.0, "100"):
        report = report_row(report_observed=value)
        step(
            db,
            "typed report rejects " + repr(value),
            lambda report=report: admit(db, report),
            TypeError,
            "integer",
        )
        assert rows(db) == before
    for value in (0, -1, 2**63):
        report = report_row(report_observed=value)
        step(
            db,
            "typed report rejects out-of-domain " + repr(value),
            lambda report=report: admit(db, report),
            ValueError,
        )
        assert rows(db) == before
    for value in (None, 1, 100):
        prov = J({"source": "synthetic://valid-time", "evidence": repr(value)})
        report = report_row(report_prov=prov, report_observed=value)
        step(
            db,
            "positive-or-NULL original time " + repr(value),
            lambda report=report: admit(db, report),
        )
        stored = db.execute(
            "SELECT observed_at_us FROM resource_relations WHERE relation_kind='transfer_event_report' AND provenance_json=?",
            (prov,),
        ).fetchone()[0]
        assert stored == value and type(stored) is type(value)
        unchanged = rows(db)
        assert (
            step(
                db,
                "valid time exact replay " + repr(value),
                lambda report=report: admit(db, report),
            )
            == "duplicate"
        )
        assert rows(db) == unchanged
        bad_values = (
            (True, 1.0, "1") if value == 1 else ((100.0, "100") if value == 100 else ())
        )
        for bad in bad_values:
            endpoints = endpoint_rows(report)
            altered = list(endpoints[0])
            altered[7] = bad
            endpoints[0] = tuple(altered)
            step(
                db,
                "typed endpoint rejects original " + repr(bad),
                lambda endpoints=endpoints, report=report: admit(db, report, endpoints),
                TypeError,
                "integer",
            )
            assert rows(db) == unchanged
    # SQLite only observes post-affinity storage types; raw SQL is a distinct boundary.
    raw = report_row(
        report_prov=J({"source": "synthetic://raw-affinity", "evidence": "float"}),
        report_observed=100.0,
    )
    step(
        db, "direct SQL float time is coerced by INTEGER affinity", lambda: rr(db, raw)
    )
    assert db.execute(
        "SELECT typeof(observed_at_us),observed_at_us FROM resource_relations WHERE provenance_json=? AND relation_kind='transfer_event_report'",
        (raw[5],),
    ).fetchone() == ("integer", 100)
    ACTIVE["boundary"] = (
        "Baseline validate_observation_us rejects bool/float/string before equality or SQL affinity. SQL CHECK enforces positive-or-NULL stored values only; it does not prove original input types."
    )


@case("T12_SQL_versus_typed_admission_boundary")
def t12(db):
    seed(db)
    false = report_row(event_type="closed")
    step(
        db,
        "typed admission rejects non-transfer actual normalized event",
        lambda: admit(db, false),
        ValueError,
        "event_type",
    )
    assert not db.execute(
        "SELECT * FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchall()
    step(
        db,
        "direct SQL structurally consistent but false event report",
        lambda: rr(db, false),
    )
    for item in endpoint_rows(false):
        step(
            db,
            "direct SQL endpoint structural FK passes",
            lambda item=item: end(db, item),
        )
    ACTIVE["boundary"] = (
        "CHECK/FK establish structural references, not external event semantics or authenticity. Actual normalized event_type is required by supported typed unit admission. Passing SQL cannot authenticate this deliberately fabricated report."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    generated = cp.sql()
    (args.output / "candidate.sql").write_text(generated)
    db = cp.connect()
    schema = [
        list(r)
        for r in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
        )
    ]
    runtime = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "sqlite_version": db.execute("SELECT sqlite_version()").fetchone()[0],
        "sqlite_source_id": db.execute("SELECT sqlite_source_id()").fetchone()[0],
        "compile_options": [r[0] for r in db.execute("PRAGMA compile_options")],
        "pragmas": {
            p: db.execute(f"PRAGMA {p}").fetchone()[0]
            for p in (
                "foreign_keys",
                "recursive_triggers",
                "synchronous",
                "journal_mode",
                "defer_foreign_keys",
                "ignore_check_constraints",
                "trusted_schema",
            )
        },
        "minimum_declared": list(p1_schema.MIN_SQLITE),
    }
    inventory = {
        "schema": schema,
        "tables": {
            r[1]: {
                "columns": [
                    list(x) for x in db.execute(f'PRAGMA table_xinfo("{r[1]}")')
                ],
                "foreign_keys": [
                    list(x) for x in db.execute(f'PRAGMA foreign_key_list("{r[1]}")')
                ],
                "indexes": [
                    list(x) for x in db.execute(f'PRAGMA index_list("{r[1]}")')
                ],
            }
            for r in schema
            if r[0] == "table"
        },
    }
    db.close()
    inputs = {}
    for directory in (EVIDENCE / "candidates", HERE):
        for file in sorted(directory.iterdir()):
            if file.is_file() and file.suffix in {".py", ".sql", ".sh"}:
                inputs[str(file.relative_to(REPO))] = hashlib.sha256(
                    file.read_bytes()
                ).hexdigest()
    for relative in (
        "src/repo_catalog/adapters/sqlite/p1_schema.py",
        "src/repo_catalog/adapters/sqlite/p1_context.py",
        "src/repo_catalog/domain/p1_context.py",
        "src/repo_catalog/domain/time.py",
        "src/repo_catalog/adapters/sqlite/p1_ddl/context.sql",
        "src/repo_catalog/adapters/sqlite/p1_ddl/coverage.sql",
    ):
        inputs[relative] = hashlib.sha256((REPO / relative).read_bytes()).hexdigest()
    receipt = {
        "baseline_commit": "efb55af84ccbf1183d47547d22bb6c57d8fbc8f9",
        "baseline_tree": "117d580b31098ecb8287281bd843894fdfad71fc",
        "execution_git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "inputs_sha256": inputs,
        "candidate_sql_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        "runtime": runtime,
        "collected_case_ids": [name for name, _ in CASES],
        "executed_case_ids": [],
        "cases": [],
    }
    global ACTIVE
    for name, fn in CASES:
        ACTIVE = {"id": name, "steps": [], "checkpoints": []}
        db = new()
        try:
            fn(db)
            if not ACTIVE.get("skip_final_integrity"):
                checkpoint(db, "final")
            ACTIVE["rowsets"] = rows(db)
            ACTIVE["outcome"] = "passed"
        except Exception as exc:
            ACTIVE["outcome"] = "failed"
            ACTIVE["failure"] = str(exc)
            ACTIVE["traceback"] = traceback.format_exc()
            ACTIVE["rowsets"] = rows(db)
        finally:
            db.close()
        receipt["cases"].append(ACTIVE)
        receipt["executed_case_ids"].append(name)
        print(name, ACTIVE["outcome"], ACTIVE.get("failure", ""))
    receipt["passed"] = sum(c["outcome"] == "passed" for c in receipt["cases"])
    receipt["failed"] = len(CASES) - receipt["passed"]
    receipt["collection_execution_equal"] = (
        receipt["collected_case_ids"] == receipt["executed_case_ids"]
    )
    (args.output / "results.json").write_text(
        json.dumps(receipt, ensure_ascii=True, indent=2) + "\n"
    )
    (args.output / "inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=True, indent=2) + "\n"
    )
    print(
        f"{receipt['passed']}/{len(CASES)} cases passed; SQLite {sqlite3.sqlite_version}"
    )
    return bool(receipt["failed"])


if __name__ == "__main__":
    raise SystemExit(main())
