#!/usr/bin/env python3
"""Preserved 75 reviewer observations adapted explicitly to canonical Parent TEXT.

IR15/IR16 remain direct SQL structural diagnostics, never qualified G3 admission.
The original script remains untouched in independent-review/final-probe.py.
"""

import argparse
import hashlib
import importlib.util
import json
import platform
import sqlite3
import subprocess
import sys
from pathlib import Path

args = argparse.ArgumentParser()
args.add_argument("--repo", type=Path, required=True)
args.add_argument("--output", type=Path, required=True)
args.add_argument("--freeze", required=True)
args = args.parse_args()
E = args.repo / "docs/implementation/evidence/context-resource-u3-cprime"
sys.path[:0] = [str(args.repo / "src"), str(E / "candidates")]
import cprime as cp  # noqa: E402

from repo_catalog.adapters.sqlite import p1_schema  # noqa: E402


def J(x):
    return json.dumps(
        x, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


S = "12345678-1234-4234-8234-123456789abc"
S2 = "22345678-1234-4234-8234-123456789abc"
R = "32345678-1234-4234-8234-123456789abc"
P = J({"source": "independent-review-fixture", "evidence": {"source_event": "E9"}})
C = {"domain": "independent-review-clock", "at_us": 123}
E9 = J(["issue", J("I7"), "timeline_event", "E9"])
RR = "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,observed_at_us"
EC = "service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us,event_report_members_json,event_report_scope_json"
records = []


def new():
    db = cp.connect()
    for service in (S, S2):
        db.execute("INSERT INTO providers VALUES(?,?,?)", (service, "synthetic", "{}"))
    db.execute("INSERT INTO repository_context VALUES(?,?)", (R, "{}"))
    return db


def resource(db, kind, value, service=S, namespace=None, doc=None):
    extra = (namespace, J(value[1]), doc, J(value[3])) if namespace else (None,) * 4
    encoded = J([value[0], J(value[1]), *value[2:]]) if namespace else J(value)
    db.execute(
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)", (service, kind, encoded, *extra)
    )


def child(db, name="E9", doc="timeline_event"):
    resource(db, "comment", ["issue", "I7", doc, name], namespace="issue", doc=doc)
    return J(["issue", J("I7"), doc, name])


def parent(event=E9, target="I7", prov=P, doc="timeline_event", observed=None):
    return (
        S,
        "comment",
        event,
        "parent",
        J([[S, "issue", J(target)]]),
        prov,
        J({"clock": C, "document_kind": doc, "state": "complete"}),
        observed,
    )


def report(p=None, typ="transferred"):
    p = p or parent()
    scope = {
        "clock": C,
        "event_type": typ,
        "from_provider_repository_id": None,
        "to_provider_repository_id": None,
        "provided_roles": ["transfer_from_repository"],
        "parent_members_json": p[4],
        "parent_scope_json": p[6],
        "parent_provenance_json": p[5],
        "endpoints": [["transfer_from_repository", J(R)]],
    }
    return (*p[:3], "transfer_event_report", "[]", p[5], J(scope), p[7])


def endpoint(r):
    return (
        *r[:3],
        "transfer_from_repository",
        J(R),
        J(json.loads(r[6])["clock"]),
        r[5],
        r[7],
        r[4],
        r[6],
    )


def ins(db, table, cols, row, suffix="", verb="INSERT"):
    return db.execute(
        f"{verb} INTO {table}({cols}) VALUES({','.join('?' for x in row)}) {suffix}",
        row,
    )


def rr(db, row, **kw):
    return ins(db, "resource_relations", RR, row, **kw)


def ep(db, row, **kw):
    return ins(db, "resource_repository_relations", EC, row, **kw)


def rowsets(db):
    return {
        table: [list(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY 1,2,3")]
        for table in (
            "resources",
            "resource_relations",
            "resource_repository_relations",
        )
    }


def attempt(db, ident, fn, error=None):
    trace = []
    db.set_trace_callback(lambda sql: trace.append(sql) if sql not in trace else None)
    record = {
        "id": ident,
        "expected": error or "success",
        "transaction_before": db.in_transaction,
    }
    try:
        fn()
        record["actual"] = "success"
    except Exception as exc:
        record["actual"] = getattr(exc, "sqlite_errorname", type(exc).__name__)
        record["error"] = str(exc)
    finally:
        db.set_trace_callback(None)
    record["sql"] = trace
    record["transaction_after"] = db.in_transaction
    record["rows"] = rowsets(db)
    record["matches_expectation"] = record["actual"] == (error or "success")
    records.append(record)
    assert record["matches_expectation"], record


def check(db, label):
    fk = [list(r) for r in db.execute("PRAGMA foreign_key_check")]
    integrity = [r[0] for r in db.execute("PRAGMA integrity_check")]
    assert not fk and integrity == ["ok"], (label, fk, integrity)
    checkpoints.append(
        {"label": label, "foreign_key_check": fk, "integrity_check": integrity}
    )


checkpoints = []
assert (
    subprocess.check_output(
        ["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True
    ).strip()
    == args.freeze
)
input_paths = sorted((E / "candidates").glob("*.py")) + sorted(
    (E / "candidates").glob("*.sql")
)
input_paths += [E / "reproduction/run.py"]
input_paths += sorted((args.repo / "src/repo_catalog").rglob("*.py"))
input_paths += sorted(
    (args.repo / "src/repo_catalog/adapters/sqlite/p1_ddl").glob("*.sql")
)
inputs = {
    str(p.relative_to(args.repo)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in input_paths
}
for path in input_paths:
    relative = str(path.relative_to(args.repo))
    assert path.read_bytes() == subprocess.check_output(
        ["git", "-C", str(args.repo), "show", args.freeze + ":" + relative]
    )
freeze = {
    "inputs_manifest_sha256": hashlib.sha256(J(inputs).encode()).hexdigest(),
    "candidate_sql_sha256": hashlib.sha256(cp.sql().encode()).hexdigest(),
}
db = new()
tables = {r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
base = sqlite3.connect(":memory:")
p1_schema.register_functions(base)
base.executescript(p1_schema.compose("context"))
assert (
    tables
    == {r[0] for r in base.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    and len(tables) == 19
)
assert len(db.execute("PRAGMA table_info(coverage_claims)").fetchall()) == 5
assert {r[2] for r in db.execute("PRAGMA foreign_key_list(resources)")} == {"providers"}
assert not {"parent_resource_kind", "parent_provider_resource_id"} & {
    r[1] for r in db.execute("PRAGMA table_info(resources)")
}
schema_inventory = {
    "tables": sorted(tables),
    "resources_foreign_keys": [
        list(r) for r in db.execute("PRAGMA foreign_key_list(resources)")
    ],
    "relations_foreign_keys": [
        list(r) for r in db.execute("PRAGMA foreign_key_list(resource_relations)")
    ],
    "endpoint_foreign_keys": [
        list(r)
        for r in db.execute("PRAGMA foreign_key_list(resource_repository_relations)")
    ],
}
attempt(db, "IR01-child-before-parent", lambda: child(db))
attempt(
    db,
    "IR02-parent-missing-real-fk",
    lambda: rr(db, parent()),
    "SQLITE_CONSTRAINT_FOREIGNKEY",
)
attempt(db, "IR03-parent-arrival-no-synthesis", lambda: resource(db, "issue", "I7"))
assert not db.execute("SELECT * FROM resource_relations").fetchall()
attempt(
    db,
    "IR04-parent-alone-not-support",
    lambda: rr(db, report()),
    "SQLITE_CONSTRAINT_FOREIGNKEY",
)
attempt(db, "IR05-original-parent-resupplied", lambda: rr(db, parent()))
attempt(db, "IR06-genuine-one-sided-report", lambda: rr(db, report()))
attempt(db, "IR07-genuine-one-sided-endpoint", lambda: ep(db, endpoint(report())))
attempt(db, "IR08-commit-original-null-time", db.commit)
assert db.execute("SELECT observed_at_us FROM resource_relations").fetchall() == [
    (None,),
    (None,),
]
check(db, "one-sided unit after original resupply")
for col in (8, 9):
    other = new()
    child(other)
    resource(other, "issue", "I7")
    rr(other, parent())
    rr(other, report())
    row = list(endpoint(report()))
    row[col] = None
    attempt(
        other,
        f"IR09-null-support-{col}",
        lambda row=row: ep(other, row),
        "SQLITE_CONSTRAINT_CHECK",
    )
    check(other, f"null support {col}")
other = new()
child(other)
resource(other, "issue", "I7")
for name, members in [
    ("zero", []),
    ("multiple", [[S, "issue", J("I7")]] * 2),
    ("missing", [[S, "issue"]]),
    ("null", [[S, "issue", None]]),
]:
    p = list(parent())
    p[4] = J(members)
    attempt(
        other,
        f"IR10-parent-shape-{name}",
        lambda p=p: rr(other, p),
        "SQLITE_CONSTRAINT_CHECK",
    )
other = new()
ordinary = child(other, doc="ordinary_comment")
resource(other, "issue", "I7")
attempt(
    other,
    "IR11-ordinary-comment-not-timeline",
    lambda: rr(other, parent(event=ordinary)),
    "SQLITE_CONSTRAINT_FOREIGNKEY",
)
other = new()
child(other)
resource(other, "issue", "I7")
rr(other, parent())
r = list(report())
r[2] = child(other, "E10")
attempt(
    other,
    "IR12-other-event-cannot-borrow-support",
    lambda: rr(other, r),
    "SQLITE_CONSTRAINT_FOREIGNKEY",
)
r = list(report())
r[5] = J({"source": "independent-review-fixture-B", "evidence": {"source_event": "E9"}})
attempt(
    other,
    "IR13-independent-report-provenance-explicit-support",
    lambda: rr(other, r),
)
# Same Event can preserve two attributed Parent reports; no broad UNIQUE(event,parent).
resource(db, "issue", "I8")
p2 = parent(
    target="I8", prov=J({"source": "independent-B", "evidence": {"source_event": "E9"}})
)
attempt(db, "IR14-competing-parent-report", lambda: rr(db, p2))
attempt(
    db, "IR15-structural-only-competing-dependent-report", lambda: rr(db, report(p2))
)
attempt(
    db,
    "IR16-structural-only-competing-dependent-endpoint",
    lambda: ep(db, endpoint(report(p2))),
)
assert (
    db.execute(
        "SELECT count(*) FROM resource_relations WHERE relation_kind='parent'"
    ).fetchone()[0]
    == 2
)
check(db, "competing reports without winner")
for name, fn in [
    (
        "update",
        lambda: db.execute(
            "UPDATE resource_relations SET observed_at_us=77 WHERE relation_kind='parent'"
        ),
    ),
    (
        "delete",
        lambda: db.execute(
            "DELETE FROM resource_relations WHERE relation_kind='parent'"
        ),
    ),
    ("replace", lambda: rr(db, parent(), verb="INSERT OR REPLACE")),
]:
    attempt(db, "IR17-immutable-" + name, fn, "SQLITE_CONSTRAINT_TRIGGER")
p = list(parent())
p[7] = 456
attempt(
    db,
    "IR18-ignore-changed-observation-rejected",
    lambda: rr(db, p, verb="INSERT OR IGNORE"),
    "SQLITE_CONSTRAINT_TRIGGER",
)
e = list(endpoint(report()))
e[9] = report(p2)[6]
attempt(
    db,
    "IR19-ignore-changed-support-rejected",
    lambda: ep(db, e, suffix="ON CONFLICT DO NOTHING"),
    "SQLITE_CONSTRAINT_TRIGGER",
)
attempt(
    db,
    "IR20-exact-ignore-rowset-retained",
    lambda: rr(db, parent(), verb="INSERT OR IGNORE"),
)
check(db, "immutable conflict paths")
other = new()
for i, value in enumerate(
    ["", [], [""], [[]], "9" * 150, " A ", "é", "e\u0301", ["a", ["b", []]], ["b", "a"]]
):
    attempt(
        other,
        f"IR21-identity-{i}",
        lambda value=value: resource(other, "synthetic.genuine-opaque", value),
    )
for i, value in enumerate(
    [None, "null", "1", "false", "{}", "[1]", '["x",null]', '[ "x" ]', '"\\u0078"']
):
    attempt(
        other,
        f"IR22-invalid-identity-{i}",
        lambda value=value: other.execute(
            "INSERT INTO resources VALUES(?,?,?,NULL,NULL,NULL,NULL)",
            (S, "synthetic.genuine-opaque", value),
        ),
        "SQLITE_CONSTRAINT_NOTNULL" if value is None else "SQLITE_CONSTRAINT_CHECK",
    )
attempt(
    other,
    "IR23-known-comment-cannot-generic-fallback",
    lambda: resource(other, "comment", "bogus"),
    "SQLITE_CONSTRAINT_CHECK",
)
check(other, "identity fixtures")
# General groups are not flattened; their referent existence remains application-only.
other = new()
for value in ("owner", "a", "b"):
    resource(other, "vendor.future", value)
g = (
    S,
    "vendor.future",
    J("owner"),
    "ordered.general",
    J([[S, "vendor.future", J("b")], [S, "vendor.future", J("a")]]),
    P,
    J({"state": "complete", "ordered": True}),
    321,
)
attempt(other, "IR24-general-multimember-ordered", lambda: rr(other, g))
missing = list(g)
missing[3] = "generic.missing-reference"
missing[4] = J([[S, "vendor.future", J("not-admitted")]])
attempt(other, "IR25-generic-member-existence-not-sql-fk", lambda: rr(other, missing))
check(other, "general syntax vs member referent boundary")
# SQL does not check actual event semantics or the reverse endpoint-set closure.
other = new()
child(other)
resource(other, "issue", "I7")
rr(other, parent())
false_report = report(typ="closed")
attempt(
    other,
    "IR26-structural-false-type-not-authenticated",
    lambda: rr(other, false_report),
)
attempt(
    other,
    "IR27-false-type-endpoint-structurally-valid",
    lambda: ep(other, endpoint(false_report)),
)
check(other, "SQL syntax does not certify actual event")
spec = importlib.util.spec_from_file_location(
    "author_typed_admission", E / "reproduction/run.py"
)
admission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admission)
attempt(
    other,
    "IR28-typed-admission-rejects-wrong-event-type",
    lambda: admission.admit(other, false_report),
    "ValueError",
)
other = new()
child(other)
resource(other, "issue", "I7")
rr(other, parent())
attempt(other, "IR29-sql-group-no-reverse-endpoint-fk", lambda: rr(other, report()))
assert not other.execute("SELECT * FROM resource_repository_relations").fetchall()
attempt(
    other,
    "IR30-typed-admission-rejects-endpoint-cut",
    lambda: admission.admit(other, report(), []),
    "ValueError",
)
check(other, "atomic endpoint set remains typed-unit obligation")
# Counterexamples to broader support/replay preservation, characterized honestly.
other = new()
child(other)
resource(other, "issue", "I7")
rr(other, parent())
independent_prov = list(report())
independent_prov[5] = J(
    {"source": "independent-transfer-observer", "evidence": {"source_event": "E9"}}
)
attempt(
    other,
    "IR31-existing-support-independent-transfer-provenance-preserved",
    lambda: rr(other, independent_prov),
)
independent_clock = list(report())
scope = json.loads(independent_clock[6])
scope["clock"] = {"domain": "independent-transfer-clock", "at_us": 456}
independent_clock[6] = J(scope)
attempt(
    other,
    "IR32-existing-support-independent-transfer-clock-preserved",
    lambda: rr(other, independent_clock),
)
before = rowsets(other)
attempt(
    other,
    "IR33-ignore-resource-nonkey-rebind-rejected",
    lambda: other.execute(
        "INSERT OR IGNORE INTO resources VALUES(?,?,?,?,?,?,?)",
        (S, "comment", E9, "issue", J("changed-namespace"), "timeline_event", J("E9")),
    ),
    "SQLITE_CONSTRAINT_TRIGGER",
)
assert rowsets(other) == before
check(other, "review findings leave original rows intact")
# Independently exercise all relevant Resource conflict verbs after the fix.
changed = (S, "comment", E9, "issue", J("wrong"), "timeline_event", J("E9"))
for name, sql in (
    ("insert", "INSERT INTO resources VALUES(?,?,?,?,?,?,?)"),
    ("replace", "INSERT OR REPLACE INTO resources VALUES(?,?,?,?,?,?,?)"),
    ("nothing", "INSERT INTO resources VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING"),
    (
        "update",
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?) ON CONFLICT DO UPDATE SET identifier_namespace_id=excluded.identifier_namespace_id",
    ),
):
    attempt(
        other,
        "IR34-resource-rebind-" + name,
        lambda sql=sql: other.execute(sql, changed),
        "SQLITE_CONSTRAINT_TRIGGER",
    )
original = (S, "comment", E9, "issue", J("I7"), "timeline_event", J("E9"))
attempt(
    other,
    "IR35-exact-resource-upsert-update-rejected",
    lambda: other.execute(
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?) ON CONFLICT DO UPDATE SET provider_document_id=excluded.provider_document_id",
        original,
    ),
    "SQLITE_CONSTRAINT_TRIGGER",
)
attempt(
    other,
    "IR36-exact-resource-do-nothing-idempotent",
    lambda: other.execute(
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING", original
    ),
)
assert rowsets(other) == before
# Cross-pairing support fields from independent reports must still fail.
x = new()
child(x)
resource(x, "issue", "I7")
resource(x, "issue", "I8")
rr(x, parent())
pb = parent(target="I8", prov=J({"source": "parent-B", "evidence": "B"}))
rr(x, pb)
for name, key, value in (
    ("provenance", "parent_provenance_json", pb[5]),
    ("members", "parent_members_json", pb[4]),
    ("null-provenance", "parent_provenance_json", None),
):
    mixed = list(report())
    scope = json.loads(mixed[6])
    scope[key] = value
    mixed[6] = J(scope)
    mixed[5] = J({"source": "mixed-test-" + name, "evidence": name})
    attempt(
        x,
        "IR37-cross-paired-support-" + name,
        lambda mixed=mixed: rr(x, mixed),
        "SQLITE_CONSTRAINT_CHECK"
        if name == "null-provenance"
        else "SQLITE_CONSTRAINT_FOREIGNKEY",
    )
check(x, "independent support rejects cross-paired complete coordinates")
# Second endpoint failure must roll back the already inserted report and first endpoint.
x = new()
child(x)
resource(x, "issue", "I7")
rr(x, parent())
two = list(report())
scope = json.loads(two[6])
scope["provided_roles"] = ["transfer_from_repository", "transfer_to_repository"]
scope["endpoints"].append(
    ["transfer_to_repository", J("42345678-1234-4234-8234-123456789abc")]
)
two[6] = J(scope)
prior = rowsets(x)
attempt(
    x,
    "IR38-mid-unit-second-endpoint-FK-rollback",
    lambda: admission.admit(x, two),
    "SQLITE_CONSTRAINT_FOREIGNKEY",
)
assert rowsets(x) == prior
trace = records[-1]["sql"]
writes = [q for q in trace if q.startswith("INSERT INTO resource_repository_relations")]
assert len(writes) == 2, writes
assert not x.in_transaction
check(x, "second endpoint failed and full transfer unit rolled back")
# Characterize the uncovered declared Provider-member admission dependency.
x = new()
child(x)
resource(x, "issue", "I7")
rr(x, parent())
missing_member_report = list(report())
missing_member_scope = json.loads(missing_member_report[6])
missing_member_scope["from_provider_repository_id"] = J("absent-provider-repository")
missing_member_report[4] = J([[S, "repository", J("absent-provider-repository")]])
missing_member_report[6] = J(missing_member_scope)
attempt(
    x,
    "IR39-missing-declared-Provider-member-withheld",
    lambda: admission.admit(x, missing_member_report),
    "ValueError",
)
assert (
    x.execute(
        "SELECT count(*) FROM resources WHERE resource_kind='repository'"
    ).fetchone()[0]
    == 0
)
records[-1]["contract_assessment"] = (
    "Corrected: declared Provider member absence withholds the full typed unit without fabricating referents or durable staging."
)
check(x, "missing Provider member is outside SQL FK projection")
# Python/API observation input type must be checked before SQLite affinity.
for time_label, observed in (
    ("bool", True),
    ("float", 100.0),
    ("numeric-string", "100"),
):
    x = new()
    child(x)
    resource(x, "issue", "I7")
    rr(x, parent())
    ill_typed_time = list(report())
    ill_typed_time[7] = observed
    attempt(
        x,
        "IR40-ill-typed-observation-rejected-" + time_label,
        lambda ill_typed_time=ill_typed_time: admission.admit(x, ill_typed_time),
        "TypeError",
    )
    records[-1]["contract_assessment"] = (
        "Corrected: strict Python observation-time validation refuses non-integer input before SQLite affinity."
    )
    check(x, "stored integer cannot prove original input type " + time_label)
# Re-supply after actual selected Provider-member arrival, preserving original unit.
y = new()
child(y)
resource(y, "issue", "I7")
rr(y, parent())
original_before = rowsets(y)
attempt(
    y,
    "IR41-missing-provider-unit-leaves-no-stage",
    lambda: admission.admit(y, missing_member_report),
    "ValueError",
)
assert rowsets(y) == original_before
attempt(
    y,
    "IR42-actual-selected-provider-member-arrives",
    lambda: resource(y, "repository", "absent-provider-repository"),
)
assert (
    y.execute(
        "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchone()[0]
    == 0
)
attempt(
    y,
    "IR43-original-whole-report-resupplied",
    lambda: admission.admit(y, missing_member_report),
)
accepted = rowsets(y)
attempt(
    y,
    "IR44-original-whole-report-replay",
    lambda: admission.admit(y, missing_member_report),
)
assert rowsets(y) == accepted
check(y, "late genuine Provider member plus original report replay")
# Dependent endpoints retain independent Parent/report provenance, clock and observation.
y = new()
child(y)
resource(y, "issue", "I7")
rr(y, parent())
independent = list(report())
sc = json.loads(independent[6])
sc["clock"] = {"domain": "transfer-only-clock", "at_us": 987}
independent[6] = J(sc)
independent[5] = J(
    {"source": "transfer-only-source", "evidence": "independent-source-report"}
)
independent[7] = 654
attempt(
    y, "IR45-independent-support-whole-unit", lambda: admission.admit(y, independent)
)
stored_parent = y.execute(
    "SELECT scope_json,provenance_json,observed_at_us FROM resource_relations WHERE relation_kind='parent'"
).fetchone()
assert stored_parent == (parent()[6], P, None)
stored_endpoint = y.execute(
    "SELECT clock_json,provenance_json,observed_at_us,support_scope_json,support_provenance_json FROM resource_repository_relations"
).fetchone()
assert stored_endpoint == (J(sc["clock"]), independent[5], 654, parent()[6], P)
check(y, "all independent original support and report coordinates preserved")
metadata = {
    "python": platform.python_version(),
    "sqlite_version": sqlite3.sqlite_version,
    "sqlite_source_id": db.execute("SELECT sqlite_source_id()").fetchone()[0],
    "compile_options": [r[0] for r in db.execute("PRAGMA compile_options")],
    "pragmas": {
        p: db.execute("PRAGMA " + p).fetchone()[0]
        for p in ("foreign_keys", "recursive_triggers", "synchronous")
    },
    "frozen_commit": subprocess.check_output(
        ["git", "-C", str(args.repo), "rev-parse", "HEAD"], text=True
    ).strip(),
    "input_manifest_sha256": freeze["inputs_manifest_sha256"],
    "candidate_sql_sha256": freeze["candidate_sql_sha256"],
    "reviewer_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}
output = {
    "metadata": metadata,
    "inputs_sha256": inputs,
    "schema_inventory": schema_inventory,
    "collected_case_ids": [r["id"] for r in records],
    "executed_case_ids": [r["id"] for r in records],
    "records": records,
    "checkpoints": checkpoints,
    "summary": {
        "checks": len(records),
        "matched_expectations": sum(r["matches_expectation"] for r in records),
        "unexpected_failures": 0,
        "scope": "Independent direct-SQL cases plus eleven calls to frozen typed admission; author full rerun reported separately. Repeated runtimes and author overlaps are not additive.",
    },
}
args.output.write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps(output["summary"]))
