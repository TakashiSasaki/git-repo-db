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
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE
REPO = EVIDENCE.parents[4]
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
        "rowsets_before": rows(db),
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
            record["sqlite_errorcode"] = exc.sqlite_errorcode
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
        record["rowsets_after"] = rows(db)
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
    """Whole-unit helper reused from F2; writes execute the current G3-constrained SQL."""
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


class Qs10Violation(ValueError):
    """Permanent ineligibility of this I8-supported Transfer under G3=A."""


class DependencyMissing(ValueError):
    """An original report can be supplied again after genuine dependencies arrive."""


def admit(db, report, endpoints=None):
    """Typed normalization/whole-unit boundary; SQL independently enforces G3=A."""
    cp.event(report[0], report[1], report[4], report[6])
    source = db.execute(
        "SELECT identifier_namespace_kind,identifier_namespace_id FROM resources "
        "WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
        report[:3],
    ).fetchone()
    target = json.loads(json.loads(report[6])["parent_members_json"])[0]
    if source is None:
        raise DependencyMissing("Event resource missing")
    if source != ("issue", target[2]) or target[0] != report[0] or target[1] != "issue":
        raise Qs10Violation(
            "Q-S10 G3=A: native Issue I7 required; I8 is permanently ineligible"
        )
    for coordinates in (target,):
        if not db.execute(
            "SELECT 1 FROM resources WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=?",
            coordinates,
        ).fetchone():
            raise DependencyMissing(
                "native Issue resource missing; original report resupply required"
            )
    scope = json.loads(report[6])
    parent_key = (
        *report[:3],
        "parent",
        scope["parent_members_json"],
        scope["parent_provenance_json"],
        scope["parent_scope_json"],
    )
    if not db.execute(
        "SELECT 1 FROM resource_relations WHERE service_instance_uuidv4=? AND resource_kind=? AND provider_resource_id=? AND relation_kind=? AND members_json=? AND provenance_json=? AND scope_json=?",
        parent_key,
    ).fetchone():
        raise DependencyMissing(
            "complete original I7 Parent report missing; resupply required"
        )
    return structural_admit(db, report, endpoints)


def seed(db, *, report=False):
    event_resource(db)
    resource(db, "issue", "I7")
    rr(db, parent_row())
    if report:
        admit(db, report_row())


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
        "product_src_git_tree": subprocess.check_output(
            ["git", "rev-parse", "HEAD:src"], cwd=REPO, text=True
        ).strip(),
        "execution_git_tree": subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=REPO, text=True
        ).strip(),
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
