"""Run actual frozen packaged Context control; no candidate implementation."""

import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from repo_catalog.adapters.sqlite import p1_schema

ROOT = Path(__file__).resolve().parents[5]
S = "11111111-1111-4111-8111-111111111111"
R = "22222222-2222-4222-8222-222222222222"
C = "33333333-3333-4333-8333-333333333333"
canonical = p1_schema.canonical
result = {
    "baseline_commit": subprocess.check_output(
        ["git", "rev-parse", "efb55af84ccbf1183d47547d22bb6c57d8fbc8f9"], text=True
    ).strip(),
    "baseline_tree": subprocess.check_output(
        ["git", "rev-parse", "efb55af84ccbf1183d47547d22bb6c57d8fbc8f9^{tree}"],
        text=True,
    ).strip(),
    "python": sys.version,
    "python_executable": sys.executable,
    "platform": platform.platform(),
    "sqlite_version": sqlite3.sqlite_version,
    "declared_minimum": p1_schema.MIN_SQLITE,
    "inputs": {},
    "cases": [],
}
for name in [
    "pyproject.toml",
    "uv.lock",
    "src/repo_catalog/adapters/sqlite/p1_schema.py",
    "src/repo_catalog/adapters/sqlite/p1_ddl/context.sql",
    "src/repo_catalog/adapters/sqlite/p1_ddl/coverage.sql",
    "src/repo_catalog/adapters/sqlite/p1_ddl/fingerprints.json",
]:
    p = Path(name)
    if p.exists():
        result["inputs"][name] = hashlib.sha256(p.read_bytes()).hexdigest()
result["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix="u3-baseline-") as tmp:
    path = Path(tmp) / "context.sqlite3"
    p1_schema.initialize(path, "context", R, C)
    db = p1_schema.connect(path, "context")
    result["source_id"] = db.execute("select sqlite_source_id()").fetchone()[0]
    result["compile_options"] = [row[0] for row in db.execute("pragma compile_options")]
    result["pragmas"] = {
        p: db.execute("pragma " + p).fetchone()[0]
        for p in [
            "foreign_keys",
            "recursive_triggers",
            "synchronous",
            "journal_mode",
            "defer_foreign_keys",
            "ignore_check_constraints",
            "trusted_schema",
        ]
    }
    result["tables"] = [
        r[0]
        for r in db.execute(
            "select name from sqlite_schema where type='table' order by name"
        )
    ]
    result["schema_rows"] = [list(r) for r in p1_schema.schema_rows(db)]
    result["foreign_keys"] = {
        t: [list(r) for r in db.execute("pragma foreign_key_list(" + t + ")")]
        for t in ["resources", "resource_relations", "resource_repository_relations"]
    }

    def case(name, sql, params, expected):
        outcome = "accepted"
        error = None
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute(sql, params)
            db.commit()
        except sqlite3.Error as exc:
            error = {
                "class": type(exc).__name__,
                "message": str(exc),
                "code": exc.sqlite_errorcode,
                "name": exc.sqlite_errorname,
            }
            outcome = "rejected"
            db.rollback()
        result["cases"].append(
            {
                "id": name,
                "sql": sql,
                "parameters": params,
                "expected": expected,
                "actual": outcome,
                "error": error,
                "transaction": "committed" if outcome == "accepted" else "rolled_back",
                "rows": [
                    list(r)
                    for r in db.execute(
                        "SELECT * FROM resources ORDER BY resource_kind,provider_resource_id"
                    )
                ],
                "pass": expected == outcome,
            }
        )

    db.execute("INSERT INTO providers VALUES(?,?,?)", (S, "synthetic", "{}"))
    event = canonical(["issue", "I7", "timeline_event", "E9"])
    ordinary = canonical(["issue", "I7", "comment", "C1"])
    case(
        "B01_child_before_parent",
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
        (S, "comment", event, "issue", "I7", "timeline_event", "E9"),
        "rejected",
    )
    case(
        "B02_parent",
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
        (S, "issue", "I7", None, None, None, None),
        "accepted",
    )
    case(
        "B03_timeline_event",
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
        (S, "comment", event, "issue", "I7", "timeline_event", "E9"),
        "accepted",
    )
    case(
        "B04_ordinary_comment",
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
        (S, "comment", ordinary, "issue", "I7", "comment", "C1"),
        "accepted",
    )
    sql = "INSERT INTO resource_repository_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)"
    payload = (
        "transfer_to_repository",
        "null",
        canonical({"domain": "synthetic", "at_us": 10}),
        canonical({"source": "synthetic", "evidence": "report1"}),
        10,
    )
    case(
        "B05_ordinary_comment_transfer",
        sql,
        (S, "comment", ordinary, *payload),
        "rejected",
    )
    case(
        "B06_typed_event_transfer_direct_sql",
        sql,
        (S, "comment", event, *payload),
        "accepted",
    )
    case(
        "B07_pull_request",
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
        (S, "pull_request", "P7", None, None, None, None),
        "accepted",
    )
    wrong_parent = canonical(["pull_request", "P7", "timeline_event", "E10"])
    case(
        "B08_wrong_parent_timeline_event",
        "INSERT INTO resources VALUES(?,?,?,?,?,?,?)",
        (S, "comment", wrong_parent, "pull_request", "P7", "timeline_event", "E10"),
        "accepted",
    )
    case(
        "B09_wrong_parent_transfer",
        sql,
        (S, "comment", wrong_parent, *payload),
        "rejected",
    )
    result["direct_transfer_without_report_group"] = [
        list(r) for r in db.execute("select * from resource_repository_relations")
    ]
    result["relation_groups"] = [
        list(r) for r in db.execute("select * from resource_relations")
    ]
    result["foreign_key_check"] = [
        list(r) for r in db.execute("pragma foreign_key_check")
    ]
    result["integrity_check"] = [r[0] for r in db.execute("pragma integrity_check")]
    db.close()
    with p1_schema.connect(path, "context") as reopened:
        result["reopened_pragmas"] = {
            p: reopened.execute("pragma " + p).fetchone()[0]
            for p in ["foreign_keys", "recursive_triggers"]
        }
result["pass"] = (
    all(c["pass"] for c in result["cases"])
    and not result["foreign_key_check"]
    and result["integrity_check"] == ["ok"]
    and len(result["tables"]) == 19
)
print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
sys.exit(0 if result["pass"] else 1)
