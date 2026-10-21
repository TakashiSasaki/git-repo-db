#!/usr/bin/env python3
"""Independently authored reviewer probes; raw SQL does not invoke Admission."""

import argparse
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import traceback
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--f2-candidates", type=Path, required=True)
a = parser.parse_args()
root = a.repo.resolve()
ev = root / "docs/implementation/evidence/context-resource-design/g3-a"
sys.path[:0] = [str(ev), str(ev / "candidates"), str(root / "src")]
import cprime as cp  # noqa: E402
import harness as h  # noqa: E402

J = cp.canonical
S = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"
R = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
R2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
MISSING = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
RR = (
    "service_instance_uuidv4",
    "resource_kind",
    "provider_resource_id",
    "relation_kind",
    "members_json",
    "provenance_json",
    "scope_json",
    "observed_at_us",
)
EP = (
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
records = []
failures = []


def prov(name):
    return J(
        {"source": "synthetic://independent/" + name, "evidence": {"original": name}}
    )


def clock(name, t):
    return {"domain": "independent-" + name, "at_us": t}


def insert(db, table, cols, row, prefix="INSERT", suffix=""):
    return db.execute(
        prefix
        + " INTO "
        + table
        + "("
        + ",".join(cols)
        + ") VALUES("
        + ",".join("?" for _ in cols)
        + ")"
        + suffix,
        row,
    )


def rr(db, row, **kw):
    return insert(db, "resource_relations", RR, row, **kw)


def ep(db, row, **kw):
    return insert(db, "resource_repository_relations", EP, row, **kw)


def snap(db):
    return {
        t: [list(v) for v in db.execute("SELECT * FROM " + t + " ORDER BY 1,2,3,4")]
        for t in ("resources", "resource_relations", "resource_repository_relations")
    }


def obs(db, cid, fn, expected=None, code=None):
    before = snap(db)
    trace = []
    db.set_trace_callback(trace.append)
    r = {
        "id": cid,
        "before": before,
        "transaction_before": db.in_transaction,
        "expected": expected.__name__ if expected else "success",
    }
    try:
        result = fn()
        r["result"] = "success"
        if expected:
            raise AssertionError("expected " + expected.__name__)
    except Exception as e:
        r.update(
            result=type(e).__name__,
            error=str(e),
            sqlite_errorname=getattr(e, "sqlite_errorname", None),
            sqlite_errorcode=getattr(e, "sqlite_errorcode", None),
        )
        if (
            expected is None
            or not isinstance(e, expected)
            or (code is not None and getattr(e, "sqlite_errorcode", None) != code)
        ):
            raise
    finally:
        db.set_trace_callback(None)
        r.update(after=snap(db), sql=trace, transaction_after=db.in_transaction)
        records.append(r)
    if expected:
        assert r["after"] == before, cid + " changed rows on refusal"
    return result if not expected else None


def conn():
    db = cp.connect()
    db.executemany(
        "INSERT INTO providers VALUES(?,?,?)", [(s, "synthetic", "{}") for s in (S, S2)]
    )
    db.executemany(
        "INSERT INTO repository_context VALUES(?,?)", [(r, "{}") for r in (R, R2)]
    )
    return db


def resource(db, kind, value, s=S, extra=None):
    raw = J(value)
    db.execute(
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
        (s, kind, raw, *(extra or (None,) * 4)),
    )
    return raw


def event(db, issue="I7", event="EV", s=S, sub="timeline_event"):
    native = J(issue)
    raw = J(["issue", native, sub, event])
    db.execute(
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
        (s, "comment", raw, "issue", native, sub, J(event)),
    )
    return raw


def parent(
    e, issue="I7", tag="P", s=S, t=17, at=18, kind="issue", sub="timeline_event"
):
    return (
        s,
        "comment",
        e,
        "parent",
        J([[s, kind, J(issue)]]),
        prov(tag),
        J({"clock": clock(tag, t), "document_kind": sub, "state": "complete"}),
        at,
    )


def report(p, tag="T", t=27, at=28, typ="transferred", target=R2):
    scope = {
        "clock": clock(tag, t),
        "event_type": typ,
        "from_provider_repository_id": None,
        "to_provider_repository_id": None,
        "provided_roles": ["transfer_from_repository", "transfer_to_repository"],
        "parent_members_json": p[4],
        "parent_scope_json": p[6],
        "parent_provenance_json": p[5],
        "endpoints": [
            ["transfer_from_repository", J(R)],
            ["transfer_to_repository", J(target)],
        ],
    }
    return (*p[:3], "transfer_event_report", "[]", prov(tag), J(scope), at)


def endpoints(r):
    s = json.loads(r[6])
    return [
        (*r[:3], role, target, J(s["clock"]), r[5], r[7], r[4], r[6])
        for role, target in s["endpoints"]
    ]


def change(r, **kw):
    x = list(r)
    s = json.loads(r[6])
    s.update(kw)
    x[6] = J(s)
    return tuple(x)


def setup():
    db = conn()
    e = event(db)
    resource(db, "issue", "I7")
    p = parent(e)
    rr(db, p)
    return db, e, p


def group1():
    db = conn()
    e = event(db)
    assert db.execute("SELECT count(*) FROM resource_relations").fetchone() == (0,)
    assert db.execute(
        "SELECT count(*) FROM resources WHERE resource_kind='issue'"
    ).fetchone() == (0,)
    obs(db, "IRG01.E.before-I7.no-synthesized-parent", lambda: None)
    resource(db, "issue", "I8")
    p8 = parent(e, "I8", "P8")
    rr(db, p8)
    r8 = report(p8)
    obs(
        db,
        "IRG01.I8.attributed-report-reread",
        lambda: db.execute(
            "SELECT members_json,provenance_json,scope_json,observed_at_us FROM resource_relations"
        ).fetchone(),
    )
    obs(db, "IRG01.raw-BEGIN", lambda: db.execute("BEGIN"))
    obs(db, "IRG01.raw-I8-FK-787", lambda: rr(db, r8), sqlite3.IntegrityError, 787)
    obs(db, "IRG01.raw-ROLLBACK", lambda: db.execute("ROLLBACK"))
    obs(db, "IRG01.Admission-permanent-I8", lambda: h.admit(db, r8), h.Qs10Violation)
    resource(db, "issue", "I7")
    p7 = parent(e)
    rr(db, p7)
    r7 = report(p7)
    obs(db, "IRG01.raw-I7-BEGIN", lambda: db.execute("BEGIN"))
    obs(db, "IRG01.raw-I7-report", lambda: rr(db, r7))
    for i, row in enumerate(endpoints(r7)):
        obs(db, "IRG01.raw-I7-endpoint-" + str(i), lambda row=row: ep(db, row))
    obs(db, "IRG01.raw-I7-COMMIT", lambda: db.execute("COMMIT"))
    assert db.execute(
        "SELECT count(*) FROM resource_relations WHERE relation_kind='parent'"
    ).fetchone() == (2,)
    obs(db, "IRG01.supported-I7-exact-replay", lambda: h.admit(db, r7))
    obs(
        db,
        "IRG01.I8-still-permanently-ineligible",
        lambda: h.admit(db, r8),
        h.Qs10Violation,
    )
    db.close()


def group2():
    db = conn()
    e = event(db)
    p = parent(e)
    r = report(p)
    obs(db, "IRG02.missing-I7-row", lambda: h.admit(db, r), h.DependencyMissing)
    obs(
        db,
        "IRG02.raw-missing-I7-report",
        lambda: rr(db, r),
        sqlite3.IntegrityError,
        787,
    )
    resource(db, "issue", "I7")
    obs(
        db,
        "IRG02.missing-I7-report-after-row",
        lambda: h.admit(db, r),
        h.DependencyMissing,
    )
    assert db.execute("SELECT count(*) FROM resource_relations").fetchone() == (0,)
    rr(db, p)
    assert db.execute(
        "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchone() == (0,)
    obs(db, "IRG02.Parent-arrival-no-auto-replay", lambda: None)
    obs(db, "IRG02.original-report-resupplied", lambda: h.admit(db, r))
    db.close()


def group3():
    db, e, p = setup()
    p2 = parent(e, tag="P2", t=37, at=38)
    rr(db, p2)
    r = report(p2, tag="T2", t=47, at=48)
    obs(db, "IRG03.exact-alternate-complete-Parent-report", lambda: h.admit(db, r))
    assert (
        p2[5] != r[5]
        and json.loads(p2[6])["clock"] != json.loads(r[6])["clock"]
        and p2[7] != r[7]
    )
    obs(db, "IRG03.Parent-Event-independent-original-evidence", lambda: None)
    bad = change(report(p2, tag="MIX"), parent_scope_json=p[6])
    obs(
        db,
        "IRG03.existing-elements-not-one-complete-Parent-key",
        lambda: rr(db, bad),
        sqlite3.IntegrityError,
        787,
    )
    e2 = event(db, event="EV2")
    resource(db, "issue", "I7", s=S2)
    event(db, s=S2)
    bad = list(r)
    bad[2] = e2
    obs(
        db,
        "IRG03.other-Event-no-borrowing",
        lambda: rr(db, bad),
        sqlite3.IntegrityError,
        787,
    )
    bad = list(r)
    bad[0] = S2
    obs(
        db,
        "IRG03.other-service-no-borrowing",
        lambda: rr(db, bad),
        sqlite3.IntegrityError,
    )
    epbad = list(endpoints(r)[0])
    epbad[7] = p2[7]
    obs(
        db,
        "IRG03.endpoint-own-EventReport-observed-time",
        lambda: ep(db, epbad),
        sqlite3.IntegrityError,
    )
    db.close()


def group4():
    db, e, p = setup()
    for n, payload in enumerate(
        (
            None,
            "null",
            "[]",
            "[null]",
            J([[S, "issue", None]]),
            J([[S, "issue", '"I7" ']]),
            J([[S2, "issue", J("I7")]]),
            J([[S, "repository", J("I7")]]),
        )
    ):
        bad = change(report(p, tag="BAD" + str(n)), parent_members_json=payload)
        obs(
            db,
            "IRG04.support-invalid-" + str(n),
            lambda bad=bad: rr(db, bad),
            sqlite3.IntegrityError,
        )
    for val in (None, "null", "{}", '["bad",false]', '"\\u0049"'):
        obs(
            db,
            "IRG04.Identity-invalid-" + repr(val),
            lambda val=val: db.execute(
                "INSERT INTO resources VALUES(?,?,?,NULL,NULL,NULL,NULL)",
                (S, "future", val),
            ),
            sqlite3.IntegrityError,
        )
    eordinary = event(db, event="ordinary", sub="comment")
    pordinary = parent(eordinary, sub="comment")
    rr(db, pordinary)
    bad = change(report(pordinary), parent_scope_json=p[6])
    obs(
        db,
        "IRG04.ordinary-comment-not-timeline",
        lambda: rr(db, bad),
        sqlite3.IntegrityError,
        787,
    )
    r = report(p)
    obs(
        db,
        "IRG04.generated-support-not-writable",
        lambda: db.execute(
            "INSERT INTO resource_relations("
            + ",".join(RR)
            + ",support_parent_id) VALUES("
            + ",".join("?" for _ in range(9))
            + ")",
            (*r, J("I7")),
        ),
        sqlite3.OperationalError,
    )
    db.close()


def group5():
    db, e, p = setup()
    r = report(p)
    h.admit(db, r)
    for table, cols, row, keylen in [
        (
            "resources",
            (
                "service_instance_uuidv4",
                "resource_kind",
                "provider_resource_id",
                "identifier_namespace_kind",
                "identifier_namespace_id",
                "document_kind",
                "provider_document_id",
            ),
            (S, "comment", e, "issue", J("I7"), "timeline_event", J("EV")),
            3,
        ),
        ("resource_relations", RR, p, 7),
        ("resource_relations", RR, r, 7),
        ("resource_repository_relations", EP, endpoints(r)[0], 7),
    ]:
        tag = "IRG05." + table + "." + row[3]
        where = " AND ".join(c + "=?" for c in cols[:keylen])
        key = row[:keylen]
        obs(
            db,
            tag + ".UPDATE",
            lambda table=table, cols=cols, where=where, key=key: db.execute(
                "UPDATE "
                + table
                + " SET "
                + cols[-1]
                + "="
                + cols[-1]
                + " WHERE "
                + where,
                key,
            ),
            sqlite3.IntegrityError,
        )
        obs(
            db,
            tag + ".DELETE",
            lambda table=table, where=where, key=key: db.execute(
                "DELETE FROM " + table + " WHERE " + where, key
            ),
            sqlite3.IntegrityError,
        )
        obs(
            db,
            tag + ".REPLACE-equal",
            lambda table=table, cols=cols, row=row: insert(
                db, table, cols, row, "REPLACE"
            ),
            sqlite3.IntegrityError,
        )
        bad = list(row)
        if table == "resources":
            bad[4] = J("I8")
        elif table == "resource_relations":
            bad[7] = 1234
        else:
            bad[9] = change(r, event_type="closed")[6]
        for prefix, suffix in [
            ("INSERT OR IGNORE", ""),
            ("INSERT", " ON CONFLICT DO NOTHING"),
            (
                "INSERT",
                " ON CONFLICT DO UPDATE SET " + cols[-1] + "=excluded." + cols[-1],
            ),
        ]:
            obs(
                db,
                tag + "." + prefix + suffix,
                lambda table=table, cols=cols, bad=bad, prefix=prefix, suffix=suffix: (
                    insert(db, table, cols, bad, prefix, suffix)
                ),
                sqlite3.IntegrityError,
            )
    db.close()


def group6():
    db, e, p = setup()
    r = report(p)
    obs(
        db,
        "IRG06.actual-closed-event-I7-still-refused",
        lambda: h.admit(db, change(r, event_type="closed")),
        ValueError,
    )
    for value in (True, 17.0, "17"):
        bad = list(r)
        bad[7] = value
        obs(
            db,
            "IRG06.original-time-type-" + repr(value),
            lambda bad=bad: h.admit(db, bad),
            TypeError,
        )
    obs(
        db,
        "IRG06.truncated-endpoint-unit",
        lambda: h.admit(db, r, endpoints(r)[:1]),
        ValueError,
    )
    bad = report(p, target=MISSING)
    obs(db, "IRG06.outer-BEGIN", lambda: db.execute("BEGIN"))
    obs(
        db,
        "IRG06.second-endpoint-FK-entire-Admission-unit-rollback",
        lambda: h.admit(db, bad),
        sqlite3.IntegrityError,
        787,
    )
    assert db.in_transaction
    obs(db, "IRG06.outer-COMMIT-preexisting-E-Parent", lambda: db.execute("COMMIT"))
    assert db.execute(
        "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchone() == (0,)
    obs(db, "IRG06.good-original-resupply-after-failure", lambda: h.admit(db, r))
    obs(
        db,
        "IRG06.invalid-replay-not-approved-by-stored-rows",
        lambda: h.admit(db, change(r, event_type="closed")),
        ValueError,
    )
    db.close()


def group7():
    for issue in (["project", "7"], [], "", ["", [[]]]):
        db = conn()
        e = event(db, issue)
        resource(db, "issue", issue)
        p = parent(e, issue)
        rr(db, p)
        r = report(p)
        obs(
            db,
            "IRG07.native-composite-or-empty-Issue-positive-" + J(issue),
            lambda: h.admit(db, r),
        )
        resource(db, "issue", "I8")
        p8 = parent(e, "I8", "P8")
        rr(db, p8)
        obs(
            db,
            "IRG07.native-composite-or-empty-Issue-rejects-I8-" + J(issue),
            lambda: rr(db, report(p8, tag="T8")),
            sqlite3.IntegrityError,
            787,
        )
        db.close()


def group8():
    db = conn()
    native = J(["pull_request", J(["proj", "PR1"]), "body", "D"])
    resource(
        db,
        "document",
        json.loads(native),
        extra=("pull_request", J(["proj", "PR1"]), "body", J("D")),
    )
    resource(db, "pull_request", "PR2")
    p = (
        S,
        "document",
        native,
        "parent",
        J([[S, "pull_request", J("PR2")]]),
        prov("GD"),
        J({"clock": clock("GD", 7), "document_kind": "body", "state": "complete"}),
        8,
    )
    obs(db, "IRG08.general-Document-namespace-not-Parent", lambda: rr(db, p))
    for val in ("", [], ["global", "D"]):
        raw = J(val)
        obs(
            db,
            "IRG08.independent-Document-" + raw,
            lambda raw=raw: db.execute(
                "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
                (S, "document", raw, None, None, None, raw),
            ),
        )
    child = (
        S,
        "document",
        J(["global", "D"]),
        "parent",
        J([[S, "document", J("")]]),
        prov("DC"),
        J({"clock": clock("DC", 9), "document_kind": None, "state": "complete"}),
        10,
    )
    obs(db, "IRG08.Document-child-of-independent-Document", lambda: rr(db, child))
    for val in ("", [], ["", [[]]]):
        obs(
            db,
            "IRG08.unknown-kind-empty-Identity-" + J(val),
            lambda val=val: resource(db, "vendor.x", val),
        )
    obs(
        db,
        "IRG08.known-PR-no-global-fallback",
        lambda: cp.document_input("pr_scoped", J("bad")),
        ValueError,
    )
    nested = J(["pull_request", ["proj", "PR1"], "body", "N"])
    obs(
        db,
        "IRG08.G2-mixed-decoded-namespace-rejected",
        lambda: db.execute(
            "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
            (S, "document", nested, "pull_request", J(["proj", "PR1"]), "body", J("N")),
        ),
        sqlite3.IntegrityError,
    )
    db.close()


def group9():
    spec = importlib.util.spec_from_file_location(
        "independent_f2", a.f2_candidates / "cprime.py"
    )
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    expected = "2892a5fb0bcef8a0e0ea916fc1b71687a0a2afe545849e27dec4f7fd3600171f"
    assert hashlib.sha256(old.sql().encode()).hexdigest() == expected
    db = old.connect()
    db.execute("INSERT INTO providers VALUES(?,?,?)", (S, "synthetic", "{}"))
    db.executemany(
        "INSERT INTO repository_context VALUES(?,?)", [(r, "{}") for r in (R, R2)]
    )
    e = event(db)
    resource(db, "issue", "I8")
    p8 = parent(e, "I8", "differential-P8")
    rr(db, p8)
    r8 = report(p8, tag="differential-T8")
    obs(db, "IRG09.F2-direct-SQL-I8-BEGIN", lambda: db.execute("BEGIN"))
    obs(db, "IRG09.F2-direct-SQL-I8-report-success", lambda: rr(db, r8))
    for i, row in enumerate(endpoints(r8)):
        obs(
            db, "IRG09.F2-direct-SQL-I8-endpoint-" + str(i), lambda row=row: ep(db, row)
        )
    obs(db, "IRG09.F2-direct-SQL-I8-COMMIT", lambda: db.execute("COMMIT"))
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    db.close()
    db = conn()
    event(db)
    resource(db, "issue", "I8")
    rr(db, p8)
    obs(db, "IRG09.G3-identical-direct-SQL-I8-BEGIN", lambda: db.execute("BEGIN"))
    obs(
        db,
        "IRG09.G3-identical-direct-SQL-I8-FK787",
        lambda: rr(db, r8),
        sqlite3.IntegrityError,
        787,
    )
    obs(db, "IRG09.G3-identical-direct-SQL-I8-ROLLBACK", lambda: db.execute("ROLLBACK"))
    db.close()
    receipt["differential"] = {
        "F2_commit": "9eeacb28f7e4a426114a9ce40e2324b4da302817",
        "F2_sql_sha256": expected,
        "G3_sql_sha256": hashlib.sha256(cp.sql().encode()).hexdigest(),
        "same_parent_report": p8,
        "same_Event_report": r8,
        "F2_actual_candidate_module": str(Path(old.__file__).resolve()),
    }


a.output.parent.mkdir(parents=True, exist_ok=True)
metadata_db = conn()
receipt = {
    "reviewed_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip(),
    "reviewed_tree": subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True
    ).strip(),
    "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "composed_sql_sha256": hashlib.sha256(cp.sql().encode()).hexdigest(),
    "actual_candidate_module": str(Path(cp.__file__).resolve()),
    "actual_admission_module": str(Path(h.__file__).resolve()),
    "python": sys.version,
    "sqlite_version": sqlite3.sqlite_version,
    "sqlite_source_id": metadata_db.execute("SELECT sqlite_source_id()").fetchone()[0],
    "compile_options": [x[0] for x in metadata_db.execute("PRAGMA compile_options")],
    "pragmas": {
        p: metadata_db.execute("PRAGMA " + p).fetchone()[0]
        for p in (
            "foreign_keys",
            "recursive_triggers",
            "trusted_schema",
            "ignore_check_constraints",
            "defer_foreign_keys",
            "synchronous",
        )
    },
    "functions": [
        list(x)
        for x in metadata_db.execute("PRAGMA function_list")
        if x[0].startswith(("cp_", "p1_"))
    ],
    "table_count_measured": metadata_db.execute(
        "SELECT count(*) FROM sqlite_schema WHERE type='table'"
    ).fetchone()[0],
}
metadata_db.close()
for fn in (group1, group2, group3, group4, group5, group6, group7, group8, group9):
    try:
        fn()
    except Exception as e:
        failures.append(
            {"group": fn.__name__, "error": str(e), "traceback": traceback.format_exc()}
        )
        break
receipt.update(
    observations=records,
    observation_count=len(records),
    failures=failures,
    passed=not failures,
)
a.output.write_text(json.dumps(receipt, indent=2) + "\n")
print(
    json.dumps(
        {
            "sqlite": receipt["sqlite_version"],
            "observations": len(records),
            "failures": failures,
        },
        indent=2,
    )
)
raise SystemExit(bool(failures))
