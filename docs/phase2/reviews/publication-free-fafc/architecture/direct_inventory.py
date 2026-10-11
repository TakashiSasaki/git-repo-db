"""Reviewer-authored PRAGMA inventory and collected-node cross-check.

Only creates an in-memory catalog; all result files remain outside the source.
"""
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import repo_catalog
from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, schema_sql

ROOT = Path.cwd()
OUT = Path(__file__).parent
assert Path(repo_catalog.__file__).resolve() == ROOT / "src/repo_catalog/__init__.py"
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip()
assert sha == "fafc1b2d4d2e1986768143cc71a0e55cba943ba3"
assert tree == "6f566cb3e91e25facda60671c40108e0a9f8965b"
db = sqlite3.connect(":memory:", cached_statements=0)
register_git_object_sql_function(db)
db.executescript(schema_sql())
objects = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
tables = {}
for kind, name, owner, sql in objects:
    if kind != "table":
        continue
    escaped = '"' + name.replace('"', '""') + '"'
    cols = [tuple(row) for row in db.execute("PRAGMA table_xinfo(" + escaped + ")")]
    fks = [tuple(row) for row in db.execute("PRAGMA foreign_key_list(" + escaped + ")")]
    indexes = [tuple(row) for row in db.execute("PRAGMA index_list(" + escaped + ")")]
    tables[name] = {
        "sql": sql,
        "columns": cols,
        "primary_key": [c[1] for c in sorted(cols, key=lambda c: c[5]) if c[5]],
        "foreign_keys": fks,
        "indexes": indexes,
    }
counts = {
    "tables": len(tables),
    "columns_table_xinfo": sum(len(t["columns"]) for t in tables.values()),
    "generated_columns": sum(c[6] in (2, 3) for t in tables.values() for c in t["columns"]),
    "fk_constraints": sum(len({r[0] for r in t["foreign_keys"]}) for t in tables.values()),
    "fk_column_rows": sum(len(t["foreign_keys"]) for t in tables.values()),
    "views": sum(o[0] == "view" for o in objects),
    "triggers": sum(o[0] == "trigger" for o in objects),
    "indexes_excluding_sqlite_autoindexes": sum(o[0] == "index" for o in objects),
}
assert counts == {
    "tables": 84, "columns_table_xinfo": 617, "generated_columns": 3,
    "fk_constraints": 141, "fk_column_rows": 190,
    "views": 20, "triggers": 556, "indexes_excluding_sqlite_autoindexes": 55,
}, counts
old = Path("/workspace/review-artifacts/architecture/corrected-e810427/baseline-nodes.txt")
now = OUT / "ordinary-nodes.txt"
baseline = old.read_text().splitlines()
current = now.read_text().splitlines()
resolved = json.loads((OUT / "resolved-node-dispositions.json").read_text())
checked = json.loads((ROOT / "tests/support/publication_free_node_dispositions.json").read_text())
assert len(baseline) == len(set(baseline)) == 1950
assert len(current) == len(set(current)) == 2128
mapped = [r["baseline_node"] for r in resolved["entries"]]
retained = resolved["still_collected_same_nodes"]
assert len(mapped) == len(set(mapped)) == 487
assert len(retained) == len(set(retained)) == 1463
assert not set(mapped).intersection(retained)
assert set(mapped + retained) == set(baseline)
assert all(r["surviving_assertion"] and r["replacement_nodes"] and set(r["replacement_nodes"]) <= set(current) for r in resolved["entries"])
assert set(retained) <= set(current)
# Run 1 required byte-identical collection order. The independent command lists
# unit/integration/e2e explicitly, while the tracked receipt uses another order.
# Preserve that attempt and compare every semantic field plus the actual sets.
assert {k:v for k,v in resolved.items() if k != "node_list_sha256"} == {k:v for k,v in checked.items() if k != "node_list_sha256"}
tracked_path = Path("/workspace/git-repo-db/artifacts/publication-free/collection-4c738ef66d61/ordinary-collected-nodes.txt")
tracked_bytes = tracked_path.read_bytes()
assert hashlib.sha256(tracked_bytes).hexdigest() == checked["node_list_sha256"]["current"]
assert set(tracked_bytes.decode().splitlines()) == set(current)
assert checked["node_list_sha256"]["baseline"] == hashlib.sha256(old.read_bytes()).hexdigest()
result = {
    "source": repo_catalog.__file__, "sha": sha, "tree": tree,
    "python": sys.version, "sqlite": sqlite3.sqlite_version, "DDL": DDL_SHA256.hex(),
    "counts": counts,
    "generated_columns": [(name,c[1]) for name,t in tables.items() for c in t["columns"] if c[6] in (2,3)],
    "fk_check": db.execute("PRAGMA foreign_key_check").fetchall(),
    "integrity_check": db.execute("PRAGMA integrity_check").fetchall(),
    "dispositions": {
        "baseline": len(baseline), "current": len(current), "mapped": len(mapped), "same": len(retained),
        "removed_or_renamed_functions": resolved["removed_or_renamed_baseline_function_count"],
        "tracked_semantic_receipt_equal": True,
        "tracked_current_node_set_equal": True,
        "tracked_ordered_list_sha256": checked["node_list_sha256"]["current"],
        "node_list_sha256": {"baseline":hashlib.sha256(old.read_bytes()).hexdigest(),"current":hashlib.sha256(now.read_bytes()).hexdigest()},
        "limit": "Exact counterpart collection and explicit rationales are verified; this is not full assertion-sufficiency or full execution proof.",
    },
}
assert result["fk_check"] == [] and result["integrity_check"] == [("ok",)]
(OUT / "direct-pragma-inventory.json").write_text(json.dumps({"objects":objects,"tables":tables},indent=2))
(OUT / "direct-inventory-summary.json").write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
