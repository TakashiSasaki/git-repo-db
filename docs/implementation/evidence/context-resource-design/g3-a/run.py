#!/usr/bin/env python3
"""Bounded G3=A counterexamples; direct SQL deliberately bypasses admit()."""

import json
import sqlite3

import harness as h

J, S, S2, R1, R2, cp = h.J, h.S, h.S2, h.R1, h.R2, h.cp
h.CASES.clear()


def scope_replace(report, **changes):
    value = list(report)
    scope = json.loads(value[6])
    scope.update(changes)
    value[6] = J(scope)
    return tuple(value)


def reject(db, label, fn, error=sqlite3.IntegrityError, contains=None):
    before = h.rows(db)
    h.step(db, label, fn, error, contains)
    assert h.rows(db) == before


def transaction(db, label, fn, error=sqlite3.IntegrityError, contains=None):
    before = h.rows(db)
    h.step(db, label + ": BEGIN", lambda: db.execute("BEGIN"))
    reject(db, label, fn, error, contains)
    h.step(db, label + ": ROLLBACK", lambda: db.execute("ROLLBACK"))
    assert h.rows(db) == before


@h.case("GA01_child_first_I8_report_SQL_and_admission")
def ga01(db):
    h.step(db, "complete E native I7 before I7 exists", lambda: h.event_resource(db))
    assert not db.execute("SELECT * FROM resource_relations").fetchall()
    assert not db.execute(
        "SELECT * FROM resources WHERE resource_kind='issue'"
    ).fetchall()
    h.step(db, "actual I8 arrives", lambda: h.resource(db, "issue", "I8"))
    p8 = h.parent_row(
        target="I8", prov=J({"source": "synthetic://I8", "evidence": "P8"})
    )
    h.step(db, "attributed I8 Parent stored", lambda: h.rr(db, p8))
    assert (
        db.execute(
            "SELECT members_json,provenance_json,scope_json,observed_at_us FROM resource_relations"
        ).fetchone()
        == p8[4:]
    )
    r8 = h.report_row(p8)
    transaction(
        db,
        "direct SQL I8 support fails typed native-I7 FK",
        lambda: h.rr(db, r8),
        contains="FOREIGN KEY",
    )
    reject(
        db,
        "admission classifies I8 as permanent Q-S10 violation",
        lambda: h.admit(db, r8),
        h.Qs10Violation,
    )
    h.step(
        db,
        "actual I7 arrives; no report auto-generated",
        lambda: h.resource(db, "issue", "I7"),
    )
    assert db.execute("SELECT count(*) FROM resource_relations").fetchone() == (1,)
    h.step(db, "original I7 report supplied", lambda: h.rr(db, h.parent_row()))
    h.step(db, "eligible I7 complete Transfer", lambda: h.admit(db, h.report_row()))
    assert db.execute(
        "SELECT count(*) FROM resource_relations WHERE relation_kind='parent'"
    ).fetchone() == (2,)
    assert db.execute(
        "SELECT count(*) FROM resource_repository_relations"
    ).fetchone() == (2,)
    reject(
        db,
        "I8 remains permanently invalid after I7 success",
        lambda: h.admit(db, r8),
        h.Qs10Violation,
    )
    # A later actual successful I7 report does not rewrite the original I8 report.
    assert (
        db.execute(
            "SELECT members_json,provenance_json,scope_json,observed_at_us FROM resource_relations WHERE provenance_json=? AND relation_kind='parent'",
            (p8[5],),
        ).fetchone()
        == p8[4:]
    )


@h.case("GA02_missing_dependencies_need_original_resupply")
def ga02(db):
    h.event_resource(db)
    original = h.rows(db)
    r7 = h.report_row()
    reject(
        db,
        "Admission missing I7 resource is dependency",
        lambda: h.admit(db, r7),
        h.DependencyMissing,
    )
    transaction(
        db,
        "SQL missing I7 Resource/Parent report rejects",
        lambda: h.rr(db, r7),
        contains="FOREIGN KEY",
    )
    assert h.rows(db) == original
    h.step(db, "actual I7 Resource arrives", lambda: h.resource(db, "issue", "I7"))
    reject(
        db,
        "I7 row without original Parent report is dependency",
        lambda: h.admit(db, r7),
        h.DependencyMissing,
    )
    transaction(
        db,
        "SQL I7 row without report rejects",
        lambda: h.rr(db, r7),
        contains="FOREIGN KEY",
    )
    assert not db.execute("SELECT * FROM resource_relations").fetchall()
    h.step(
        db, "actual original Parent report supplied", lambda: h.rr(db, h.parent_row())
    )
    assert not db.execute("SELECT * FROM resource_repository_relations").fetchall()
    assert not db.execute(
        "SELECT * FROM resource_relations WHERE relation_kind='transfer_event_report'"
    ).fetchall()
    h.step(db, "original Event report must be supplied again", lambda: h.admit(db, r7))
    before = h.rows(db)
    assert (
        h.step(db, "normal original replay is idempotent", lambda: h.admit(db, r7))
        == "duplicate"
    )
    assert before == h.rows(db)


@h.case("GA03_complete_key_mixing_and_alternative_reports")
def ga03(db):
    h.seed(db)
    p2 = h.parent_row(
        prov=J({"source": "synthetic://P2", "evidence": "P2"}),
        clock=J({"domain": "parent-2", "at_us": 21}),
        observed=22,
    )
    h.rr(db, p2)
    r1 = h.report_row()
    r2 = h.report_row(
        p2,
        report_prov=J({"source": "synthetic://E2", "evidence": "E2"}),
        report_clock=J({"domain": "event-2", "at_us": 31}),
        report_observed=32,
    )
    h.step(db, "first whole I7-supported report", lambda: h.admit(db, r1))
    h.step(
        db, "explicit alternate complete I7 ParentReportKey", lambda: h.admit(db, r2)
    )
    assert db.execute(
        "SELECT provenance_json,scope_json,observed_at_us FROM resource_relations WHERE relation_kind='parent' AND provenance_json=?",
        (p2[5],),
    ).fetchone() == (p2[5], p2[6], 22)
    assert (
        db.execute(
            "SELECT provenance_json,clock_json,observed_at_us,support_provenance_json,support_scope_json FROM resource_repository_relations WHERE provenance_json=? ORDER BY relation_kind",
            (r2[5],),
        ).fetchall()
        == [(r2[5], J(json.loads(r2[6])["clock"]), 32, p2[5], p2[6])] * 2
    )
    # All components below exist independently, but the mixed complete key does not.
    bad = scope_replace(
        h.report_row(p2, report_prov=J({"source": "synthetic://mix", "evidence": "M"})),
        parent_scope_json=h.parent_row()[6],
    )
    transaction(
        db,
        "real components from different Parent reports cannot mix",
        lambda: h.rr(db, bad),
        contains="FOREIGN KEY",
    )
    ev2 = h.event_resource(db, "E10")
    h.rr(db, h.parent_row(event=ev2))
    bad = list(r2)
    bad[2] = ev2
    transaction(
        db,
        "another Event cannot borrow complete Parent report",
        lambda: h.rr(db, bad),
        contains="FOREIGN KEY",
    )
    h.event_resource(db, service=S2)
    h.resource(db, "issue", "I7", S2)
    bad = list(r2)
    bad[0] = S2
    transaction(db, "another service cannot borrow support", lambda: h.rr(db, bad))
    endpoint = list(h.endpoint_rows(r2)[0])
    endpoint[-1] = r1[6]
    transaction(
        db,
        "endpoint cannot mix real Event report elements",
        lambda: h.end(db, endpoint),
    )
    endpoint = list(h.endpoint_rows(r2)[0])
    endpoint[2] = ev2
    transaction(
        db,
        "endpoint cannot borrow another Event report",
        lambda: h.end(db, endpoint),
        contains="FOREIGN KEY",
    )
    endpoint = list(h.endpoint_rows(r2)[0])
    endpoint[5] = h.CLOCK
    transaction(
        db, "same EventReportKey requires its own clock", lambda: h.end(db, endpoint)
    )


@h.case("GA04_null_canonical_kind_subtype_and_generated_columns")
def ga04(db):
    h.seed(db)
    for i, replacement in enumerate(
        (
            None,
            "null",
            "[]",
            "[null]",
            J([[S, "issue", None]]),
            J([[S, "issue", "null"]]),
            J([[S2, "issue", h.I7]]),
            J([[S, "repository", h.I7]]),
            J([[S, "issue", '"I7" ']]),
        )
    ):
        report = scope_replace(
            h.report_row(
                report_prov=J({"source": "synthetic://bad", "evidence": str(i)})
            ),
            parent_members_json=replacement,
        )
        transaction(
            db,
            f"NULL/missing/noncanonical/cross-service/wrong-kind support {i}",
            lambda report=report: h.rr(db, report),
        )
    for key in ("parent_scope_json", "parent_provenance_json"):
        for value in (None, "null", "{}", "not json"):
            report = scope_replace(h.report_row(), **{key: value})
            transaction(
                db,
                f"incomplete support {key}={value!r}",
                lambda report=report: h.rr(db, report),
            )
    missing = list(h.report_row())
    data = json.loads(missing[6])
    del data["parent_members_json"]
    missing[6] = J(data)
    transaction(db, "missing sole support payload", lambda: h.rr(db, missing))
    for raw in (None, "null", "{}", "1", '["issue", "I7"]', '["a",true]'):
        transaction(
            db,
            "invalid Resource canonical identity " + repr(raw),
            lambda raw=raw: db.execute(
                "INSERT INTO resources VALUES(?,?,?,NULL,NULL,NULL,NULL)",
                (S, "future.kind", raw),
            ),
        )
    bad_ns = (
        S,
        "comment",
        J(["issue", h.I7, "timeline_event", "E11"]),
        "issue",
        J("I8"),
        "timeline_event",
        J("E11"),
    )
    transaction(
        db,
        "namespace metadata cannot disagree with Identity",
        lambda: db.execute("INSERT INTO resources VALUES(?,?,?,?,?,?,?)", bad_ns),
    )
    ordinary = h.event_resource(db, "ordinary", doc="comment")
    ordinary_parent = h.parent_row(event=ordinary, doc="comment")
    h.rr(db, ordinary_parent)
    bad = list(h.report_row(ordinary_parent))
    data = json.loads(bad[6])
    data["parent_scope_json"] = h.parent_row(event=ordinary)[6]
    bad[6] = J(data)
    transaction(
        db,
        "ordinary comment cannot claim timeline_event subtype",
        lambda: h.rr(db, bad),
        contains="FOREIGN KEY",
    )
    native_pr = J(["pull_request", J("PR1"), "timeline_event", "E12"])
    db.execute(
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
        (S, "comment", native_pr, "pull_request", J("PR1"), "timeline_event", J("E12")),
    )
    native_pr_parent = h.parent_row(event=native_pr)
    h.rr(db, native_pr_parent)
    transaction(
        db,
        "Q-S10 must have issue native namespace, not PR",
        lambda: h.rr(db, h.report_row(native_pr_parent)),
        contains="FOREIGN KEY",
    )
    # Neither generated namespace support nor subtype can be independently written.
    report = h.report_row()
    columns = ",".join(h.RR_COLS) + ",support_parent_id"
    reject(
        db,
        "generated support ID cannot be written",
        lambda: db.execute(
            "INSERT INTO resource_relations("
            + columns
            + ") VALUES("
            + ",".join("?" for _ in range(9))
            + ")",
            (*report, J("I7")),
        ),
        sqlite3.OperationalError,
        "generated",
    )
    h.step(
        db, "commit eligible control after SQL rejections", lambda: h.admit(db, report)
    )


@h.case("GA05_mutation_conflict_ignore_replace_upsert_guards")
def ga05(db):
    h.seed(db, report=True)
    report = h.report_row()
    p = h.parent_row()
    endpoint = h.endpoint_rows(report)[0]
    for table, cols, row, key_cols in (
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
            (S, "comment", h.E9, "issue", h.I7, "timeline_event", J("E9")),
            3,
        ),
        ("resource_relations", h.RR_COLS, p, 7),
        ("resource_relations", h.RR_COLS, report, 7),
        ("resource_repository_relations", h.END_COLS, endpoint, 7),
    ):
        where = " AND ".join(c + "=?" for c in cols[:key_cols])
        key = tuple(row[:key_cols])
        transaction(
            db,
            table + " UPDATE immutable",
            lambda table=table, where=where, key=key, cols=cols: db.execute(
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
            contains="immutable",
        )
        transaction(
            db,
            table + " DELETE immutable",
            lambda table=table, where=where, key=key: db.execute(
                "DELETE FROM " + table + " WHERE " + where, key
            ),
        )
        transaction(
            db,
            table + " exact REPLACE refuses",
            lambda table=table, cols=cols, row=row: h.insert(
                db, table, cols, row, "INSERT OR REPLACE"
            ),
        )
        bad = list(row)
        if table == "resources":
            bad[4] = J("I8")
        elif table == "resource_relations":
            bad[-1] = 101
        else:
            bad[-1] = scope_replace(
                report, parent_members_json=J([[S, "issue", J("I8")]])
            )[6]
        for prefix, suffix in (
            ("INSERT OR IGNORE", ""),
            ("INSERT", " ON CONFLICT DO NOTHING"),
            ("INSERT OR REPLACE", ""),
            (
                "INSERT",
                " ON CONFLICT DO UPDATE SET " + cols[-1] + "=excluded." + cols[-1],
            ),
        ):
            sql = (
                prefix
                + " INTO "
                + table
                + "("
                + ",".join(cols)
                + ") VALUES("
                + ",".join("?" for _ in cols)
                + ")"
                + suffix
            )
            transaction(
                db,
                table + " malicious " + prefix + suffix,
                lambda sql=sql, bad=bad: db.execute(sql, bad),
                contains="rebind",
            )
        # SQL no-op ignore remains safe only because all original bytes match.
        h.step(
            db,
            table + " exact INSERT OR IGNORE harmless",
            lambda table=table, cols=cols, row=row: h.insert(
                db, table, cols, row, "INSERT OR IGNORE"
            ),
        )
    # A new ineligible report also cannot hide behind IGNORE/DO NOTHING.
    h.resource(db, "issue", "I8")
    p8 = h.parent_row(
        target="I8", prov=J({"source": "synthetic://I8", "evidence": "P8"})
    )
    h.rr(db, p8)
    bad = h.report_row(
        p8,
        report_prov=J({"source": "synthetic://bad", "evidence": "I8"}),
        report_clock=J({"domain": "bad", "at_us": 88}),
    )
    for prefix, suffix in (
        ("INSERT OR IGNORE", ""),
        ("INSERT", " ON CONFLICT DO NOTHING"),
        ("INSERT OR REPLACE", ""),
        ("INSERT", " ON CONFLICT DO UPDATE SET observed_at_us=excluded.observed_at_us"),
    ):
        sql = (
            prefix
            + " INTO resource_relations("
            + ",".join(h.RR_COLS)
            + ") VALUES("
            + ",".join("?" for _ in h.RR_COLS)
            + ")"
            + suffix
        )
        transaction(
            db,
            "new I8 Event report " + prefix + suffix,
            lambda sql=sql: db.execute(sql, bad),
            contains="FOREIGN KEY",
        )
    before = h.rows(db)
    assert (
        h.step(
            db,
            "supported exact replay revalidates then deduplicates",
            lambda: h.admit(db, report),
        )
        == "duplicate"
    )
    assert before == h.rows(db)


@h.case("GA06_admission_event_member_time_and_atomicity")
def ga06(db):
    h.seed(db)
    reject(
        db,
        "native I7 alone does not qualify actual closed event",
        lambda: h.admit(db, h.report_row(event_type="closed")),
        ValueError,
        "event_type",
    )
    reject(
        db,
        "missing declared Provider member",
        lambda: h.admit(db, h.report_row(provider="missing", endpoints=[])),
        ValueError,
        "missing declared",
    )
    report = h.report_row()
    reject(
        db,
        "truncated endpoint unit",
        lambda: h.admit(db, report, h.endpoint_rows(report)[:1]),
        ValueError,
        "whole original",
    )
    for value in (True, False, 100.0, "100"):
        reject(
            db,
            "original report timestamp type " + repr(value),
            lambda value=value: h.admit(db, h.report_row(report_observed=value)),
            TypeError,
            "integer",
        )
    for value in (0, -1, 2**63):
        reject(
            db,
            "original report timestamp range " + repr(value),
            lambda value=value: h.admit(db, h.report_row(report_observed=value)),
            ValueError,
        )
    endpoints = h.endpoint_rows(report)
    bad = list(endpoints[0])
    bad[7] = 100.0
    endpoints[0] = tuple(bad)
    reject(
        db,
        "original endpoint timestamp type before replay",
        lambda: h.admit(db, report, endpoints),
        TypeError,
        "integer",
    )
    unknown = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    failure = h.report_row(
        endpoints=[
            ["transfer_from_repository", J(R1)],
            ["transfer_to_repository", J(unknown)],
        ]
    )
    before = h.rows(db)
    h.step(db, "BEGIN outer unit", lambda: db.execute("BEGIN"))
    reject(
        db,
        "second endpoint FK fails and admission savepoint rolls back first endpoint and report",
        lambda: h.admit(db, failure),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    assert db.in_transaction and before == h.rows(db)
    h.step(db, "COMMIT independent preexisting E/Parent", lambda: db.execute("COMMIT"))
    assert before == h.rows(db)
    h.step(
        db, "complete good unit succeeds after failed unit", lambda: h.admit(db, report)
    )
    before = h.rows(db)
    reject(
        db,
        "stored valid rows cannot turn invalid replay into success",
        lambda: h.admit(db, h.report_row(event_type="closed")),
        ValueError,
        "event_type",
    )
    assert before == h.rows(db)


@h.case("GA07_SQL_boundary_does_not_authenticate_or_promise_unit_atomicity")
def ga07(db):
    h.seed(db)
    false = h.report_row(event_type="closed")
    reject(
        db,
        "typed Admission rejects false actual event",
        lambda: h.admit(db, false),
        ValueError,
        "event_type",
    )
    h.step(
        db,
        "SQL structural row does not establish external actual event type",
        lambda: h.rr(db, false),
    )
    for endpoint in h.endpoint_rows(false):
        h.step(
            db,
            "SQL structural endpoint control",
            lambda endpoint=endpoint: h.end(db, endpoint),
        )
    reject(
        db,
        "stored structural row is revalidated by admission",
        lambda: h.admit(db, false),
        ValueError,
        "event_type",
    )
    # Preserve SQL affinity limitation: caller types remain Admission responsibility.
    raw = h.report_row(
        report_prov=J({"source": "synthetic://raw", "evidence": "affinity"}),
        report_clock=J({"domain": "raw", "at_us": 1}),
        report_observed=100.0,
    )
    h.step(db, "SQL INTEGER affinity sees stored integer only", lambda: h.rr(db, raw))
    assert db.execute(
        "SELECT typeof(observed_at_us),observed_at_us FROM resource_relations WHERE relation_kind='transfer_event_report' AND provenance_json=?",
        (raw[5],),
    ).fetchone() == ("integer", 100)
    h.ACTIVE["boundary"] = (
        "SQL guarantees native-I7 and complete structural references. Actual external event type, provenance authenticity, original timestamp type, arbitrary declared-member existence and whole-unit completeness remain typed Admission obligations. Direct SQL statements are not a whole-unit API."
    )


@h.case("GA08_general_namespace_parent_and_identity_regressions")
def ga08(db):
    # A3/B3 deliberately allow namespace PR1 and semantic Parent PR2.
    raw = J(["pull_request", J("PR1"), "body", "D"])
    h.step(
        db,
        "complete scoped Document before namespace Parent exists",
        lambda: db.execute(
            "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
            (S, "document", raw, "pull_request", J("PR1"), "body", J("D")),
        ),
    )
    h.resource(db, "pull_request", "PR2")
    p = (
        S,
        "document",
        raw,
        "parent",
        J([[S, "pull_request", J("PR2")]]),
        h.PROV,
        J({"clock": json.loads(h.CLOCK), "document_kind": "body", "state": "complete"}),
        100,
    )
    h.step(
        db, "general scoped namespace differs from semantic Parent", lambda: h.rr(db, p)
    )
    assert not db.execute(
        "SELECT * FROM resources WHERE provider_resource_id=?", (J("PR1"),)
    ).fetchall()
    for value in ("global", ["project", "7"], "", []):
        ident = J(value)
        h.step(
            db,
            "genuine independent Document " + ident,
            lambda ident=ident: db.execute(
                "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
                (S, "document", ident, None, None, None, ident),
            ),
        )
    global_key = (S, "document", J("global"))
    child = (S, "document", J(["project", "7"]))
    p = (
        *child,
        "parent",
        J([global_key]),
        h.PROV,
        J({"clock": json.loads(h.CLOCK), "document_kind": None, "state": "complete"}),
        101,
    )
    h.step(db, "independent Document child of Document", lambda: h.rr(db, p))
    for value in ("", [], ["", []]):
        h.step(
            db,
            "unknown kind genuine empty/composite Identity " + J(value),
            lambda value=value: h.resource(db, "vendor.future", value),
        )
    reject(
        db,
        "known malformed PR input cannot fallback to global",
        lambda: cp.document_input("pr_scoped", J("body")),
        ValueError,
    )
    reject(
        db,
        "global selector cannot discard known PR coordinates",
        lambda: cp.document_input("provider_global", J("body"), namespace_id=J("PR1")),
        ValueError,
    )
    for native in (["project", "7"], "scalar", "", [], ["", []], '["project","7"]'):
        parent = J(native)
        chosen = J(["pull_request", parent, "body", "encoding"])
        nested = J(["pull_request", native, "body", "encoding"])
        h.step(
            db,
            "G2 canonical Parent ID TEXT " + parent,
            lambda chosen=chosen, parent=parent: db.execute(
                "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
                (S, "document", chosen, "pull_request", parent, "body", J("encoding")),
            ),
        )
        reject(
            db,
            "G2 decoded-array profile not mixed " + parent,
            lambda nested=nested, parent=parent: db.execute(
                "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
                (S, "document", nested, "pull_request", parent, "body", J("encoding")),
            ),
        )


@h.case("GA09_reopen_reconstruction_revalidate_no_flags")
def ga09(db):
    h.seed(db, report=True)
    destination = h.new()
    h.event_resource(destination)
    report = h.report_row()
    reject(
        destination,
        "experimental import no forged dependency closure",
        lambda: h.admit(destination, report),
        h.DependencyMissing,
    )
    h.resource(destination, "issue", "I7")
    reject(
        destination,
        "experimental recovery I7 row not original report",
        lambda: h.admit(destination, report),
        h.DependencyMissing,
    )
    h.rr(destination, h.parent_row())
    h.step(
        destination,
        "resupplied original whole unit reconstructs",
        lambda: h.admit(destination, report),
    )
    assert h.rows(destination) == h.rows(db)
    h.resource(destination, "issue", "I8")
    p8 = h.parent_row(
        target="I8", prov=J({"source": "synthetic://bad", "evidence": "P8"})
    )
    h.rr(destination, p8)
    reject(
        destination,
        "import/recovery route calls same permanent-Q-S10 validation",
        lambda: h.admit(destination, h.report_row(p8)),
        h.Qs10Violation,
    )
    # Snapshot is only a disposable Context SQLite control, not product paired recovery.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temp:
        path = str(Path(temp) / "snapshot.sqlite3")
        snapshot = sqlite3.connect(path, isolation_level=None)
        destination.backup(snapshot)
        snapshot.close()
        reopened = cp.connect(path, fresh=False)
        assert h.rows(reopened) == h.rows(destination)
        reject(
            reopened,
            "reopen/retained rows never qualify I8 replay",
            lambda: h.admit(reopened, h.report_row(p8)),
            h.Qs10Violation,
        )
        h.checkpoint(reopened, "separate connection settings and rows")
        reopened.close()
    destination.close()
    h.ACTIVE["unexecuted_product_paths"] = (
        "I6 production Relation/Collection/Selective Exchange and I7 stored-data validation/paired Backup/Recovery must rerun typed Q-S10 admission, never trust stored rows or sender validated flags. These product paths were not executed or implemented here."
    )


@h.case("GA10_direct_SQL_commit_and_statement_atomicity_boundary")
def ga10(db):
    h.seed(db)
    report = h.report_row()
    h.step(db, "BEGIN direct SQL control", lambda: db.execute("BEGIN"))
    h.step(db, "direct SQL whole eligible I7 Event report", lambda: h.rr(db, report))
    for endpoint in h.endpoint_rows(report):
        h.step(
            db,
            "direct SQL eligible endpoint",
            lambda endpoint=endpoint: h.end(db, endpoint),
        )
    h.step(db, "COMMIT direct SQL eligible control", lambda: db.execute("COMMIT"))
    # Direct SQL is statement atomic only. Caller intentionally commits one endpoint
    # of a different report after a second statement fails; this is NOT Admission.
    report = h.report_row(
        report_prov=J({"source": "synthetic://raw", "evidence": "partial"}),
        report_clock=J({"domain": "partial", "at_us": 4}),
        endpoints=[
            ["transfer_from_repository", J(R1)],
            ["transfer_to_repository", J("cccccccc-cccc-4ccc-8ccc-cccccccccccc")],
        ],
    )
    h.step(db, "BEGIN arbitrary multi-statement caller", lambda: db.execute("BEGIN"))
    h.step(db, "direct SQL report structurally valid", lambda: h.rr(db, report))
    h.step(
        db,
        "direct SQL first endpoint succeeds",
        lambda: h.end(db, h.endpoint_rows(report)[0]),
    )
    reject(
        db,
        "direct SQL second endpoint fails only its statement",
        lambda: h.end(db, h.endpoint_rows(report)[1]),
        contains="FOREIGN KEY",
    )
    h.step(db, "caller can commit partial raw-SQL work", lambda: db.execute("COMMIT"))
    assert db.execute(
        "SELECT count(*) FROM resource_repository_relations WHERE provenance_json=?",
        (report[5],),
    ).fetchone() == (1,)
    h.ACTIVE["boundary"] = (
        "An arbitrary direct SQL caller can commit a structurally valid report and partial endpoint set. Only normal typed Admission promises whole-unit rollback. This case is an explicit negative guarantee, not a qualified Transfer acceptance."
    )


@h.case("GA11_genuine_one_sided_null_and_unknown_time_controls")
def ga11(db):
    h.event_resource(db)
    h.resource(db, "issue", "I7")
    parent = h.parent_row(observed=None)
    h.rr(db, parent)
    for i, endpoints in enumerate(
        ([["transfer_from_repository", J(R1)]], [["transfer_to_repository", "null"]])
    ):
        report = h.report_row(
            parent,
            endpoints=endpoints,
            report_prov=J({"source": "synthetic://one-sided", "evidence": str(i)}),
            report_clock=J({"domain": "one-sided", "at_us": i + 1}),
            report_observed=None,
        )
        h.step(
            db,
            "genuine complete one-sided/null report " + str(i),
            lambda report=report: h.admit(db, report),
        )
        stored = db.execute(
            "SELECT relation_kind,target_json,observed_at_us FROM resource_repository_relations WHERE provenance_json=?",
            (report[5],),
        ).fetchall()
        assert stored == [(endpoints[0][0], endpoints[0][1], None)]
        h.step(
            db,
            "exact one-sided/null replay " + str(i),
            lambda report=report: h.admit(db, report),
        )
    assert db.execute(
        "SELECT count(*) FROM resource_repository_relations"
    ).fetchone() == (2,)


if __name__ == "__main__":
    raise SystemExit(h.main())
