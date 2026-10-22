"""Task E author rerun of Task F's SQL counterexamples against product DDL.

Run with REPO OUTPUT using the environment Python and its SQLite. Adapted from frozen Task F review_sql.py;
its normalized routing model is deliberately excluded. This is author evidence,
not independent product acceptance. The unchanged Task D literal is also run.
"""

import hashlib
import itertools
import json
import pathlib
import sqlite3
import sys
import tarfile

REPO = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2])
OUT.mkdir(exist_ok=False)
with sqlite3.connect(":memory:") as runtime_db:
    (OUT / "runtime-before-checks.json").write_text(
        json.dumps(
            {
                "python": sys.version,
                "executable": sys.executable,
                "sqlite": runtime_db.execute(
                    "SELECT sqlite_version(),sqlite_source_id()"
                ).fetchone(),
                "compile_options": runtime_db.execute(
                    "PRAGMA compile_options"
                ).fetchall(),
            },
            indent=2,
        )
        + "\n"
    )
sys.path.insert(0, str(REPO / "src"))

from repo_catalog.adapters.sqlite import p1_schema  # noqa: E402

# Raw diagnostics still honor the product factory's unchanged safety gate.
p1_schema._open(":memory:", fresh=True).close()


# Independent literals/values. J is deliberately independent of the target codec.
def J(x):
    return json.dumps(
        x, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    )


def sha(x):
    return hashlib.sha256(x).hexdigest()


S = "22222222-2222-4222-8222-222222222222"
PROV = J({"source": "task-f-independent", "evidence": ["observed", 53]})
E = J(["issue", J(["project-f", "I7"]), "timeline_event", ["evt", "91"]])
EVENT = (
    S,
    "comment",
    E,
    "issue",
    J(["project-f", "I7"]),
    "timeline_event",
    J(["evt", "91"]),
)
ISSUE7 = (S, "issue", J(["project-f", "I7"]), None, None, None, None)
ISSUE8 = (S, "issue", J(["project-f", "I8"]), None, None, None, None)
NATIVE_REPO = (S, "repository", J("provider-repo-F"), None, None, None, None)
RSQL = (
    "INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,"
    "identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES(?,?,?,?,?,?,?)"
)
REL = "INSERT INTO resource_relations VALUES(?,?,?,?,?,?,?,?)"
EP = (
    "INSERT INTO resource_repository_relations(service_instance_uuidv4,resource_kind,provider_resource_id,"
    "relation_kind,target_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)"
)
CLOCK = J({"domain": "provider-f", "at_us": 53})
SCOPE = J(
    {
        "clock": {"domain": "provider-f", "at_us": 53},
        "event_type": "transferred",
        "from_provider_repository_id": NATIVE_REPO[2],
        "to_provider_repository_id": None,
        "provided_roles": ["transfer_from_repository"],
    }
)
REPORT = (*EVENT[:3], "transfer_event_report", J([NATIVE_REPO[:3]]), PROV, SCOPE, 53)
GENERIC = (*EVENT[:3], "f_relation", "[]", PROV, "{}", 53)
PARENT_SCOPE = J(
    {
        "clock": {"domain": "provider-f", "at_us": 53},
        "document_kind": "timeline_event",
        "state": "complete",
    }
)
PARENT7 = (*EVENT[:3], "parent", J([ISSUE7[:3]]), PROV, PARENT_SCOPE, 53)
PARENT8 = (*EVENT[:3], "parent", J([ISSUE8[:3]]), PROV, PARENT_SCOPE, 53)
ENDPOINTS = {
    role: (*EVENT[:3], role, "null", CLOCK, PROV, 53)
    for role in ("transfer_from_repository", "transfer_to_repository")
}
with tarfile.open(
    REPO
    / "docs/implementation/evidence/adr0031-i2-preparation/i2-preparation-evidence.tar.gz"
) as archive:
    BEFORE = archive.extractfile("minimum/composed.sql").read().decode("utf-8")
AFTER = p1_schema.compose("context")
(OUT / "before.sql").write_text(BEFORE)
(OUT / "after.sql").write_text(AFTER)


def configure(db):
    p1_schema.register_functions(db)
    for name, val in {
        "foreign_keys": "ON",
        "recursive_triggers": "ON",
        "ignore_check_constraints": "OFF",
        "defer_foreign_keys": "OFF",
        "trusted_schema": "ON",
        "synchronous": "EXTRA",
    }.items():
        db.execute(f"PRAGMA {name}={val}")
    assert dict(
        (n, db.execute(f"PRAGMA {n}").fetchone()[0])
        for n in (
            "foreign_keys",
            "recursive_triggers",
            "ignore_check_constraints",
            "defer_foreign_keys",
            "trusted_schema",
        )
    ) == {
        "foreign_keys": 1,
        "recursive_triggers": 1,
        "ignore_check_constraints": 0,
        "defer_foreign_keys": 0,
        "trusted_schema": 1,
    }


def rawdb(old=False, filename=":memory:"):
    db = sqlite3.connect(filename, isolation_level=None)
    configure(db)
    db.executescript(BEFORE if old else AFTER)
    return db


def snapshot(db):
    # All authoritative and auxiliary rows, including every column/generated field.
    return {
        n: sorted(db.execute('SELECT * FROM "' + n + '"').fetchall(), key=J)
        for (n,) in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    }


def error(e):
    return {
        "class": type(e).__name__,
        "message": str(e),
        "extended_code": getattr(e, "sqlite_errorcode", None),
        "primary_code": (getattr(e, "sqlite_errorcode", 0) & 255) or None,
        "driver_errorname": getattr(e, "sqlite_errorname", None),
        "stage_code": getattr(e, "code", None),
    }


records = []


def record(name, family, db, action, expected=None, unchanged=False, check=None):
    pre = snapshot(db)
    trace = []
    db.set_trace_callback(trace.append)
    r = {"name": name, "family": family, "before": pre, "expected": expected}
    try:
        result = action(db)
        r.update(result=result, outcome="accepted")
        ok = expected is None
    except Exception as e:
        r.update(error=error(e), outcome="refused")
        ok = (
            isinstance(e, sqlite3.Error) and r["error"]["extended_code"] == expected
            if isinstance(expected, int)
            else type(e).__name__ == expected
        )
    post = snapshot(db)
    r.update(
        after=post,
        before_sha256=sha(J(pre).encode()),
        after_sha256=sha(J(post).encode()),
        full_rowsets_equal=pre == post,
        trace=trace,
        in_transaction=db.in_transaction,
    )
    if unchanged:
        ok = ok and pre == post
    if check:
        ok = ok and check(db, r)
    r["pass"] = bool(ok)
    records.append(r)
    db.set_trace_callback(None)
    if db.in_transaction:
        db.rollback()
    db.close()


def fresh(mask=0, poisoned=None):
    db = rawdb()
    db.execute("INSERT INTO providers VALUES(?,'task-f','{}')", (S,))
    db.execute(RSQL, EVENT)
    db.execute(RSQL, NATIVE_REPO)
    # Independent existence of native I7, I8 Parent report, and endpoint.
    # Parent target I8 exists; native I7 can still be absent, by design.
    if mask & 1:
        db.execute(RSQL, ISSUE7)
    if mask & 2:
        db.execute(RSQL, ISSUE8)
        db.execute(REL, PARENT8)
    if mask & 4:
        inject(db, "transfer_to_repository")
    if poisoned:
        inject(db, poisoned)
    return db


def inject(db, representation):
    # Unsupported poisoned-state diagnostic. Restore the exact schema before test.
    report = representation == "report"
    trigger = "i2_transfer_report_stage_fence" if report else "i2_transfer_stage_fence"
    guard = "i4_event_report_admit" if report else "i4_endpoint_admit"
    definitions = [
        db.execute("SELECT sql FROM sqlite_schema WHERE name=?", (name,)).fetchone()[0]
        for name in (trigger, guard)
    ]
    for name in (trigger, guard):
        db.execute("DROP TRIGGER " + name)
    # Explicit malformed-storage injection only; these are not supported writes.
    # Keep all original poison values and all 301 diagnostic assertions intact.
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute(REL if report else EP, REPORT if report else ENDPOINTS[representation])
    for ddl in definitions:
        db.execute(ddl)
    p1_schema.configure(db)
    assert p1_schema.schema_rows(db) == p1_schema.expected_schema("context")


VERBS = [
    ("insert", "INSERT", ""),
    ("ignore", "INSERT OR IGNORE", ""),
    ("nothing", "INSERT", " ON CONFLICT DO NOTHING"),
    ("replace", "REPLACE", ""),
    ("or_replace", "INSERT OR REPLACE", ""),
    (
        "upsert_update",
        "INSERT",
        " ON CONFLICT DO UPDATE SET observed_at_us=excluded.observed_at_us",
    ),
    (
        "upsert_noop",
        "INSERT",
        " ON CONFLICT DO UPDATE SET observed_at_us=observed_at_us WHERE 0",
    ),
]


def sqlcase(
    name,
    db,
    sql,
    args=(),
    expected=None,
    unchanged=False,
    check=None,
    family="direct-sql",
):
    def action(d):
        return d.execute(sql, args).fetchall()

    record(name, family, db, action, expected, unchanged, check)
    records[-1].update(sql=sql, parameters=args)


# The original Task D script is read verbatim, including comments and SELECTs.
literal = (
    REPO
    / "docs/implementation/evidence/adr0031-i2-independent-review/F1-reproduction.sql"
).read_text()
for old in (True, False):
    db = rawdb(old)
    steps = []
    pending = ""
    for line in literal.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            pre = snapshot(db)
            item = {"sql": pending, "before": pre}
            try:
                item.update(result=db.execute(pending).fetchall(), outcome="accepted")
            except sqlite3.Error as e:
                item.update(error=error(e), outcome="refused")
            item["after"] = snapshot(db)
            steps.append(item)
            pending = ""
    assert not pending.strip()
    step = next(s for s in steps if "INSERT INTO resource_relations" in s["sql"])
    count = db.execute(
        "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchone()[0]
    selected = len(
        db.execute(
            "SELECT * FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchall()
    )  # SQL diagnostic, not a product reader.
    ok = (
        count == selected == 1 and step["outcome"] == "accepted"
        if old
        else count == selected == 0
        and step.get("error", {}).get("extended_code") == 1811
        and step["before"] == step["after"]
    )
    records.append(
        dict(
            name="unchanged-task-d-" + ("before" if old else "after"),
            family="literal-sql-before-after",
            pass_=ok,
            steps=steps,
            sql_selected_report_count=selected,
            report_rows=count,
            literal_sha256=sha(literal.encode()),
            **{"pass": ok},
        )
    )
    db.close()

# All 8 existence combinations, all verbs and all 3 reserved representations.
for mask, (verb, prefix, suffix), representation in itertools.product(
    range(8), VERBS, ("report", *ENDPOINTS)
):
    base, row = (
        (REL, REPORT) if representation == "report" else (EP, ENDPOINTS[representation])
    )
    sqlcase(
        f"{representation}/{verb}/dependencies-{mask}",
        fresh(mask),
        base.replace("INSERT", prefix, 1) + suffix,
        row,
        1811,
        True,
    )

# Even the correct native I7 Parent report cannot enable the unimplemented stage.
for (verb, prefix, suffix), representation in itertools.product(
    VERBS, ("report", *ENDPOINTS)
):
    db = fresh(1)
    db.execute(REL, PARENT7)
    base, row = (
        (REL, REPORT) if representation == "report" else (EP, ENDPOINTS[representation])
    )
    sqlcase(
        f"correct-I7-parent/{representation}/{verb}",
        db,
        base.replace("INSERT", prefix, 1) + suffix,
        row,
        1811,
        True,
    )

# Same-key replay: impossible old rows injected only to force actual PK collision.
for (verb, prefix, suffix), representation in itertools.product(
    VERBS, ("report", *ENDPOINTS)
):
    base, row = (
        (REL, REPORT) if representation == "report" else (EP, ENDPOINTS[representation])
    )
    sqlcase(
        f"poisoned-same-key/{representation}/{verb}",
        fresh(poisoned=representation),
        base.replace("INSERT", prefix, 1) + suffix,
        row,
        1811,
        True,
        family="poisoned-sql-control",
    )

# NULL/malformed/wrong metadata over all payload coordinates. Malformed endpoint
# generated expressions may fail before BEFORE triggers (SQLITE_ERROR), still atomic.
for representation in ("report", *ENDPOINTS):
    base, row = (
        (REL, REPORT) if representation == "report" else (EP, ENDPOINTS[representation])
    )
    for idx, val in itertools.product(range(4, 8), (None, "{broken", "{}", -7)):
        changed = list(row)
        changed[idx] = val
        # Discover actual error, require any SQL refusal + complete rowset equality.
        db = fresh()
        pre = snapshot(db)
        trace = []
        db.set_trace_callback(trace.append)
        try:
            db.execute(base, changed)
            err = None
        except sqlite3.Error as e:
            err = error(e)
        post = snapshot(db)
        records.append(
            dict(
                name=f"malformed/{representation}/{idx}/{J(val)}",
                family="malformed-sql",
                sql=base,
                parameters=changed,
                before=pre,
                after=post,
                trace=trace,
                error=err,
                full_rowsets_equal=pre == post,
                **{"pass": err is not None and pre == post},
            )
        )
        db.close()

# Valid generic rows changing through UPDATE and UPSERT-update.
owner = (S, "issue", J("owner-F"), None, None, None, None)
own = (*owner[:3], "owning_repository", "null", CLOCK, PROV, 53)
for rep in ("report", *ENDPOINTS):
    db = fresh()
    if rep == "report":
        db.execute(REL, GENERIC)
        base, row = REL, GENERIC
        table = "resource_relations"
    else:
        db.execute(RSQL, owner)
        db.execute(EP, own)
        base, row = EP, own
        table = "resource_repository_relations"
    sqlcase(
        "generic-update/" + rep,
        db,
        f"UPDATE {table} SET relation_kind=?",
        ("transfer_event_report" if rep == "report" else rep,),
        1811,
        True,
    )
    db = fresh()
    if rep == "report":
        db.execute(REL, GENERIC)
    else:
        db.execute(RSQL, owner)
        db.execute(EP, own)
    target = "transfer_event_report" if rep == "report" else rep
    sqlcase(
        "generic-upsert-update/" + rep,
        db,
        base + f" ON CONFLICT DO UPDATE SET relation_kind='{target}'",
        row,
        1811,
        True,
    )

# INSERT SELECT, scalar subquery, NOCASE source expression and RETURNING.
for prefix in ("INSERT", "INSERT OR IGNORE", "INSERT OR REPLACE"):
    q = (
        prefix
        + " INTO resource_relations SELECT ?,?,?,? COLLATE NOCASE,?,?,?,? RETURNING relation_kind"
    )
    sqlcase("insert-select-returning/" + prefix, fresh(), q, REPORT, 1811, True)

# Two-row VALUES: valid prefix followed by reserved row aborts entire statement.
for prefix in ("INSERT", "INSERT OR IGNORE", "INSERT OR FAIL", "INSERT OR ROLLBACK"):
    q = REL.replace("INSERT", prefix, 1) + ", (?,?,?,?,?,?,?,?) RETURNING relation_kind"
    sqlcase("multirow/" + prefix, fresh(), q, GENERIC + REPORT, 1811, True)

# Statement ABORT retains earlier transaction prefix; caller unit rollback removes it.
db = fresh()
db.execute("BEGIN")
outer = snapshot(db)
db.execute("SAVEPOINT f_unit")
db.execute(REL, GENERIC)
pre = snapshot(db)
try:
    db.execute(REL, REPORT)
    raise AssertionError("reserved accepted")
except sqlite3.Error as e:
    failure = error(e)
statement_post = snapshot(db)
db.execute("ROLLBACK TO f_unit")
db.execute("RELEASE f_unit")
rolled = snapshot(db)
db.commit()
records.append(
    dict(
        name="caller-savepoint",
        family="transaction",
        before=outer,
        prefix=pre,
        statement_after=statement_post,
        after=rolled,
        error=failure,
        **{
            "pass": failure["extended_code"] == 1811
            and pre == statement_post
            and rolled == outer
        },
    )
)
db.close()

# Positive complete child first, lawful I8 without I7, distinct Parent reports,
# order-sensitive multi-member rows and opaque resource kinds.
db = fresh()


def positive(d):
    assert (
        d.execute(
            "SELECT count(*) FROM resources WHERE resource_kind='issue'"
        ).fetchone()[0]
        == 0
    )
    d.execute(RSQL, ISSUE8)
    d.execute(REL, PARENT8)
    assert (
        d.execute(
            "SELECT count(*) FROM resources WHERE provider_resource_id=?", (ISSUE7[2],)
        ).fetchone()[0]
        == 0
    )
    d.execute(RSQL, ISSUE7)
    d.execute(REL, PARENT7)
    d.execute(
        REL,
        (
            *PARENT8[:5],
            J({"source": "task-f-other", "evidence": "independent"}),
            PARENT_SCOPE,
            71,
        ),
    )
    a, b = ISSUE8[:3], ISSUE7[:3]
    for members in ([a, b], [b, a]):
        d.execute(REL, (*GENERIC[:4], J(members), *GENERIC[5:]))
    opaque = (S, "future/F-kind", J([[], ["opaque", ""]]), None, None, None, None)
    d.execute(RSQL, opaque)
    d.execute(REL, (*opaque[:3], "future_ordered", J([a, b]), PROV, "{}", None))
    return {
        "parents": d.execute(
            "SELECT * FROM resource_relations WHERE relation_kind='parent'"
        ).fetchall()
    }


record(
    "positive-child-I8-alternatives-order-opaque",
    "positive-sql",
    db,
    positive,
    check=lambda d, r: len(r["result"]["parents"]) == 3,
)

# Names are exact BINARY; these are opaque and grant no Transfer meaning.
for name in (
    "Transfer_event_report",
    "transfer_event_report ",
    "transfer_event_report\x00suffix",
    "vendor_transfer_event_report",
):
    sqlcase(
        "binary-opaque-name/" + repr(name),
        fresh(),
        REL,
        (*GENERIC[:3], name, *GENERIC[4:]),
    )

# Global/scoped declarations, including the same-key array-shaped-global conflict.
shape = ["pull_request", J(["pr", "F"]), "body", ["doc", "F"]]
globalrow = (S, "document", J(shape), None, None, None, J(shape))
scopedrow = (
    S,
    "document",
    J(shape),
    "pull_request",
    J(["pr", "F"]),
    "body",
    J(["doc", "F"]),
)
for first, second, label in (
    (globalrow, scopedrow, "global-first"),
    (scopedrow, globalrow, "scoped-first"),
):
    for verb, prefix, suffix in VERBS:
        db = fresh()
        db.execute(RSQL, first)
        sqlcase(
            "identification-rebind/" + label + "/" + verb,
            db,
            RSQL.replace("INSERT", prefix, 1)
            + suffix.replace("observed_at_us", "document_kind"),
            second,
            1811,
            True,
        )
    db = fresh()
    db.execute(RSQL, first)
    sqlcase(
        "identification-exact-replay/" + label,
        db,
        RSQL + " ON CONFLICT DO NOTHING",
        first,
        None,
        True,
    )
for value in ("global-F", [], ["", []]):
    row = (S, "document", J(value), None, None, None, J(value))
    sqlcase("global-complete/" + J(value), fresh(), RSQL, row)
sqlcase(
    "global-omitted",
    fresh(),
    RSQL,
    (*globalrow[:3], None, None, None, None),
    1811,
    True,
)

# File-backed re-open of complete metadata and no auto-generated Parent reports.
filedb = OUT / "reopen.sqlite"
db = rawdb(filename=str(filedb))
db.execute("INSERT INTO providers VALUES(?,'task-f','{}')", (S,))
db.execute(RSQL, EVENT)
db.execute(RSQL, globalrow)
db.execute(RSQL, ISSUE7)
pre = snapshot(db)
db.close()
db = sqlite3.connect(filedb, isolation_level=None)
configure(db)
post = snapshot(db)
records.append(
    dict(
        name="file-reopen",
        family="reopen",
        before=pre,
        after=post,
        **{"pass": pre == post and not post["resource_relations"]},
    )
)
db.close()
filedb.unlink()  # no retained databases in the review publication

# Structural delta and exact FK/index/collation/UDF inventories.
old, new = rawdb(True), rawdb()


def schema(d):
    return {
        n: (t, tbl, sql)
        for t, n, tbl, sql in d.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY name"
        )
    }


a, b = schema(old), schema(new)
delta = {
    n: {"before": a.get(n), "after": b.get(n)}
    for n in a.keys() | b.keys()
    if a.get(n) != b.get(n)
}
inventory = {}
for (table,) in new.execute(
    "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
):
    inventory[table] = {
        "table_xinfo": new.execute(f'PRAGMA table_xinfo("{table}")').fetchall(),
        "foreign_keys": new.execute(f'PRAGMA foreign_key_list("{table}")').fetchall(),
        "indexes": {
            i[1]: new.execute(f'PRAGMA index_xinfo("{i[1]}")').fetchall()
            for i in new.execute(f'PRAGMA index_list("{table}")')
        },
    }
collations = [
    slot[4]
    for t in inventory.values()
    for idx in t["indexes"].values()
    for slot in idx
    if slot[5]
]
functions = [
    r for r in new.execute("PRAGMA function_list") if r[0].startswith("p1_resource_")
]
meta = {
    "version": new.execute("SELECT sqlite_version()").fetchone()[0],
    "source_id": new.execute("SELECT sqlite_source_id()").fetchone()[0],
    "python": sys.version,
    "executable": sys.executable,
    "compile_options": new.execute("PRAGMA compile_options").fetchall(),
    "pragmas": {
        n: new.execute(f"PRAGMA {n}").fetchall()
        for n in (
            "foreign_keys",
            "recursive_triggers",
            "ignore_check_constraints",
            "defer_foreign_keys",
            "trusted_schema",
            "encoding",
            "journal_mode",
            "synchronous",
        )
    },
    "before_sql_sha256": sha(BEFORE.encode()),
    "after_sql_sha256": sha(AFTER.encode()),
    "schema_delta": delta,
    "inventory": inventory,
    "resource_functions": functions,
    "integrity": new.execute("PRAGMA integrity_check").fetchall(),
    "foreign_key_check": new.execute("PRAGMA foreign_key_check").fetchall(),
}
ok = (
    p1_schema.schema_rows(new) == p1_schema.expected_schema("context")
    and all(c == "BINARY" for c in collations)
    and all(f[-1] & 2048 for f in functions)
    and len(functions) == 2
)
records.append(
    {"name": "schema-delta-collation-udf", "family": "inventory", "pass": ok}
)
old.close()
new.close()
counts = {
    f: {
        "executed": sum(r["family"] == f for r in records),
        "passed": sum(r["family"] == f and r["pass"] for r in records),
    }
    for f in sorted({r["family"] for r in records})
}
summary = {
    "runtime": meta,
    "counts": counts,
    "total": len(records),
    "passed": sum(r["pass"] for r in records),
    "failures": [r["name"] for r in records if not r["pass"]],
    "unique_names": len({r["name"] for r in records}) == len(records),
}
(OUT / "receipt.json").write_text(
    json.dumps({"summary": summary, "cases": records}, indent=2, ensure_ascii=True)
    + "\n"
)
(OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({k: v for k, v in summary.items() if k != "runtime"}))
sys.exit(0 if summary["passed"] == summary["total"] and summary["unique_names"] else 1)
