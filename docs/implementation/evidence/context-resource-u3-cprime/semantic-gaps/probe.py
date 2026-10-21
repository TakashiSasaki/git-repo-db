#!/usr/bin/env python3
"""Focused semantic-gap receipts; runs against original or corrected candidates."""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "reproduction"))
import run as h  # noqa: E402

cp, J, S = h.cp, h.J, h.S
CORRECTED = hasattr(cp, "document_input")
h.CASES.clear()


def raw_resource(db, raw, extra):
    return db.execute(
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)", (S, "document", raw, *extra)
    )


@h.case("G1_independent_documents_and_known_contract")
def g1(db):
    # Explicit synthetic Provider-global contracts; no inferred parent/subtype.
    for value in (
        "global-doc",
        ["project", "7"],
        ["pull_request", "x", "body", "y"],
        "",
        [],
    ):
        raw = J(value)
        h.step(
            db,
            "global Document " + raw,
            lambda raw=raw: raw_resource(db, raw, (None, None, None, raw)),
            None if CORRECTED else sqlite3.IntegrityError,
        )
    for value in ("global-doc", ["project", "7"]):
        h.step(
            db,
            "all identity metadata omitted " + J(value),
            lambda value=value: raw_resource(db, J(value), (None,) * 4),
            sqlite3.IntegrityError,
        )
    pr = J(["project", "7"])
    doc = J("body")
    value = ["pull_request", pr if CORRECTED else json.loads(pr), "body", "body"]
    raw = J(value)
    h.step(
        db,
        "complete PR-scoped Document before PR",
        lambda: raw_resource(db, raw, ("pull_request", pr, "body", doc)),
    )
    for extra in (
        (None, None, None, None),
        (None, None, "body", doc),
        ("pull_request", None, "body", doc),
        ("pull_request", pr, None, doc),
    ):
        # Distinct key prevents immutable-replay trigger from masking CHECK.
        h.step(
            db,
            "malformed PR coordinates " + repr(extra),
            lambda extra=extra: raw_resource(db, J([*value[:3], "other"]), extra),
            sqlite3.IntegrityError,
        )
    if not CORRECTED:
        return
    h.step(
        db,
        "explicit PR admission cannot fall back after missing coordinates",
        lambda: cp.document_input("pr_scoped", J("body")),
        ValueError,
    )
    h.step(
        db,
        "global admission cannot silently discard PR coordinates",
        lambda: cp.document_input("provider_global", J("body"), namespace_id=pr),
        ValueError,
    )
    h.step(
        db,
        "unknown native contract rejected",
        lambda: cp.document_input("guess", J("body")),
        ValueError,
    )
    assert cp.document_input("provider_global", J("global-doc")) == (
        None,
        None,
        None,
        J("global-doc"),
    )
    assert cp.document_input(
        "pr_scoped", raw, namespace_id=pr, document_kind="body", document_id=doc
    ) == ("pull_request", pr, "body", doc)
    key = (S, "document", J("global-doc"))
    target = (S, "issue", J("I7"))
    scope = J(
        {"clock": json.loads(h.CLOCK), "document_kind": None, "state": "complete"}
    )
    parent = (*key, "parent", J([target]), h.PROV, scope, 100)
    h.step(
        db,
        "global Document missing reported Parent is real FK failure",
        lambda: h.rr(db, parent),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    h.resource(db, "issue", "I7")
    assert db.execute("SELECT count(*) FROM resource_relations").fetchone() == (0,)
    h.step(db, "subsequently supplied Parent", lambda: h.rr(db, parent))
    other = list(parent)
    other[5] = J({"source": "synthetic://second", "evidence": "independent"})
    h.step(db, "independent attributed report", lambda: h.rr(db, other))
    child = (S, "document", J(["project", "7"]))
    child_parent = (*child, "parent", J([key]), h.PROV, scope, None)
    h.step(
        db,
        "Document has Document child with actual Parent FK",
        lambda: h.rr(db, child_parent),
    )
    h.step(
        db,
        "Document owns ordered multi-member semantic relationship",
        lambda: h.rr(
            db,
            (
                *key,
                "synthetic.references",
                J([child, target]),
                h.PROV,
                J({"state": "complete"}),
                101,
            ),
        ),
    )
    forged = list(parent)
    forged[6] = J(
        {"clock": json.loads(h.CLOCK), "document_kind": "body", "state": "complete"}
    )
    forged[4] = J([[S, "pull_request", pr]])
    h.resource(db, "pull_request", json.loads(pr))
    h.step(
        db,
        "global source cannot claim PR subtype",
        lambda: h.rr(db, forged),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    forged = list(parent)
    forged[2] = raw
    h.step(
        db,
        "PR source cannot claim independent subtype",
        lambda: h.rr(db, forged),
        sqlite3.IntegrityError,
        "FOREIGN KEY",
    )
    for prefix in ("INSERT", "INSERT OR IGNORE", "INSERT OR REPLACE"):
        h.step(
            db,
            "cannot rebind independent Resource " + prefix,
            lambda prefix=prefix: db.execute(
                prefix + " INTO resources VALUES(?,?,?,?,?,?,?)",
                (*key, "pull_request", pr, "body", doc),
            ),
            sqlite3.IntegrityError,
        )
    h.ACTIVE["final_identity"] = db.execute(
        "SELECT provider_resource_id FROM resources WHERE provider_resource_id=?",
        (key[2],),
    ).fetchone()[0]
    assert h.ACTIVE["final_identity"] == J("global-doc")


@h.case("G2_parent_encoding_vectors")
def g2(db):
    vectors = []
    for native in (["project", "7"], "scalar", "", [], ["", []], '["project","7"]'):
        text = J(native)
        nested = J(["pull_request", native, "body", "D"])
        encoded = J(["pull_request", text, "body", "D"])
        assert nested != encoded
        assert json.loads(encoded)[1] == text
        assert json.loads(json.loads(encoded)[1]) == native
        assert json.loads(nested)[1] == native
        vectors.append(
            {"native": native, "parent_id": text, "nested": nested, "text": encoded}
        )
        h.step(
            db,
            "selected representation " + text,
            lambda: raw_resource(
                db,
                encoded if CORRECTED else nested,
                ("pull_request", text, "body", J("D")),
            ),
        )
        h.step(
            db,
            "alternate representation rejected " + text,
            lambda: raw_resource(
                db,
                nested if CORRECTED else encoded,
                ("pull_request", text, "body", J("D")),
            ),
            sqlite3.IntegrityError,
        )
    # Union of formats is not injective across different native parents.
    native = ["project", "7"]
    alias = J(native)
    assert J(["pull_request", J(native), "body", "D"]) == J(
        ["pull_request", alias, "body", "D"]
    )
    h.ACTIVE["vectors"] = vectors
    h.ACTIVE["mixed_format_alias"] = {
        "array_parent": native,
        "literal_string_parent": alias,
    }


@h.case("G3_namespace_I7_report_I8")
def g3(db):
    h.event_resource(db)
    h.resource(db, "issue", "I7")
    h.resource(db, "issue", "I8")
    p7 = h.parent_row()
    p8 = h.parent_row(
        target="I8", prov=J({"source": "synthetic://I8", "evidence": "report"})
    )
    h.step(db, "retain I7 Parent report", lambda: h.rr(db, p7))
    h.step(db, "retain conflicting attributed I8 Parent report", lambda: h.rr(db, p8))
    r8 = h.report_row(p8)
    before = h.rows(db)
    if CORRECTED:
        h.step(
            db,
            "supported admission withholds unresolved Q-S10 qualification",
            lambda: h.admit(db, r8),
            h.QualificationRequired,
        )
        assert h.rows(db) == before
    else:
        h.step(
            db,
            "original admission accepts unqualified I8 Transfer",
            lambda: h.admit(db, r8),
        )
    h.step(db, "begin direct SQL diagnostic", lambda: db.execute("BEGIN"))
    if not CORRECTED:
        # Original helper already stored this exact report; use replay for control.
        h.step(db, "original exact report replay", lambda: h.replay_rr(db, r8))
    else:
        h.step(db, "structural SQL permits exact I8 support", lambda: h.rr(db, r8))
        for endpoint in h.endpoint_rows(r8):
            h.step(
                db,
                "I8 Transfer endpoint FK passes",
                lambda endpoint=endpoint: h.end(db, endpoint),
            )
    h.checkpoint(db, "I8 structural diagnostic")
    h.ACTIVE["diagnostic_rowsets"] = h.rows(db)
    h.step(db, "rollback diagnostic transaction", lambda: db.execute("ROLLBACK"))
    if CORRECTED:
        assert h.rows(db) == before
        h.step(
            db,
            "I7 Transfer preserves prior qualified subset",
            lambda: h.admit(db, h.report_row(p7)),
        )
    h.ACTIVE["semantic_verdict"] = (
        "OWNER DECISION REQUIRED; FK pass is not Q-S10 semantic qualification"
    )


if __name__ == "__main__":
    result = h.main()
    output = Path(sys.argv[sys.argv.index("--output") + 1]) / "results.json"
    data = json.loads(output.read_text())
    data["probe_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    data["candidate_mode"] = "corrected" if CORRECTED else "original"
    output.write_text(json.dumps(data, indent=2) + "\n")
    raise SystemExit(result)
