#!/usr/bin/env python3
"""Reproduce the Phase 2 JSON/field inventory; this is a design audit, not runtime.

The output enriches the hand-reviewed field contract
with the executed production DDL, its registry, static SQL call sites and public
projection syntax. Static references are leads, not claims of runtime liveness.
Only a disposable in-memory catalog is created. No network or user state is used.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from repo_catalog.adapters.sqlite.json_contracts import inventory  # noqa: E402
from repo_catalog.adapters.sqlite.schema import (  # noqa: E402
    DDL_SHA256,
    SCHEMA_VERSION,
    schema_sql,
)

CONTRACT = ROOT / "docs/phase2/field-contract.json"
TABLE_REF = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([A-Za-z_]\w*)", re.I)
SQL_METHODS = {"execute", "executemany", "all", "one"}
PUBLIC_FUNCTIONS = {
    "application/issue_queries.py": {"_fields"},
    "application/pr_queries.py": {"_current_review_fields", "pr_query"},
    "application/query_service.py": {"iter_query"},
    "application/target_queries.py": {"_commit_details", "_pr", "_search"},
}


def static_text(node):
    """Preserve f-string SQL skeletons without executing dynamic expressions."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            value.value if isinstance(value, ast.Constant) else "{dynamic}"
            for value in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = static_text(node.left), static_text(node.right)
        if left is not None or right is not None:
            return (left or "{dynamic}") + (right or "{dynamic}")
    return None


class SourceAudit(ast.NodeVisitor):
    def __init__(self, relative):
        self.relative = relative
        self.scope = []
        self.sql_calls = []
        self.public_fields = {}

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node):
        self.scope.append(node.name)
        if node.name in PUBLIC_FUNCTIONS.get(self.relative, set()):
            keys = {
                key.value
                for item in ast.walk(node)
                if isinstance(item, ast.Dict)
                for key in item.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            self.public_fields[".".join(self.scope)] = sorted(keys)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node):
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in SQL_METHODS
            and node.args
        ):
            sql = static_text(node.args[0])
            if sql and re.search(r"\b(?:SELECT|INSERT|UPDATE|DELETE)\b", sql, re.I):
                tables = sorted(set(TABLE_REF.findall(sql)))
                self.sql_calls.append(
                    {
                        "file": "src/repo_catalog/" + self.relative,
                        "symbol": ".".join(self.scope),
                        "line": node.lineno,
                        "operation": sql.lstrip().split()[0].upper(),
                        "tables": tables,
                        "dynamic_sql": "{dynamic}" in sql,
                    }
                )
        self.generic_visit(node)


def generated_inventory():
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(schema_sql())
        columns = inventory(db)
        objects = list(
            db.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE sql IS NOT NULL"
            )
        )
        table_columns = {}
        source_calls = []
        projections = []
        for path in sorted((ROOT / "src/repo_catalog").rglob("*.py")):
            relative = path.relative_to(ROOT / "src/repo_catalog").as_posix()
            audit = SourceAudit(relative)
            audit.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
            source_calls.extend(audit.sql_calls)
            projections.extend(
                {"file": "src/repo_catalog/" + relative, "symbol": symbol, "keys": keys}
                for symbol, keys in audit.public_fields.items()
            )
        for entry in columns:
            table, column = entry["table"], entry["column"]
            if table not in table_columns:
                table_columns[table] = [
                    {
                        "name": c[1],
                        "type": c[2],
                        "not_null": bool(c[3]),
                        "pk": c[5],
                        "hidden": c[6],
                    }
                    for c in db.execute(f'PRAGMA table_xinfo("{table}")')
                ]
            entry["static_sql_call_sites"] = [
                {key: value for key, value in call.items() if key != "tables"}
                for call in source_calls
                if table in call["tables"]
            ]
            entry["schema_guards_and_views"] = [
                {"type": kind, "name": name}
                for kind, name, owner, sql in objects
                if kind in {"trigger", "view"}
                and (owner == table or re.search(rf"\b{re.escape(table)}\b", sql))
                and re.search(rf"\b{re.escape(column)}\b", sql)
            ]
        return {
            "schema_version": SCHEMA_VERSION,
            "ddl_sha256": DDL_SHA256.hex(),
            "json_column_count": len(columns),
            "category_counts": dict(
                sorted(Counter(e["category"] for e in columns).items())
            ),
            "foreign_key_check": list(db.execute("PRAGMA foreign_key_check")),
            "integrity_check": [r[0] for r in db.execute("PRAGMA integrity_check")],
            "json_columns": columns,
            "json_table_columns": table_columns,
            "public_projection_syntax": projections,
            "limitations": [
                "Static SQL call sites are syntactic candidates; dynamic table names and indirect consumers require the prose investigation.",
                "Public projection keys include nested literal dictionaries and exclude dynamic keys; they are not a new public schema.",
                "Provider projection columns accept unknown keys, so no finite provider-key vocabulary can be inferred from the DDL.",
                "This is in-memory schema/AST verification, not application acceptance or a historical test receipt.",
            ],
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed generated inventory differs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=CONTRACT,
        help="Write or check a separate current inventory without changing the baseline contract",
    )
    args = parser.parse_args()
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    data["generated_inventory"] = generated_inventory()
    encoded = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.check:
        if encoded != args.output.read_text(encoding="utf-8"):
            raise SystemExit(
                "Field contract inventory is stale; regenerate scripts/audit_phase2_fields.py"
            )
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(
        json.dumps(
            {
                "json_columns": data["generated_inventory"]["json_column_count"],
                "ddl_sha256": DDL_SHA256.hex(),
                "check": args.check,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
