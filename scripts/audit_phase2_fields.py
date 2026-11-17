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
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.audit_phase2_dependencies import (  # noqa: E402
    sql_call_method,
    sql_forwarders,
)

CONTRACT = ROOT / "docs/phase2/field-contract.json"
TABLE_REF = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([A-Za-z_]\w*)", re.I)
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
        self.forwarders = set()

    def visit_Module(self, node):
        self.forwarders = sql_forwarders(node)
        self.generic_visit(node)

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

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        if sql_call_method(node, self.scope, self.forwarders) and node.args:
            sql = static_text(node.args[0])
            if sql and re.search(
                r"\b(?:SELECT|INSERT|UPDATE|DELETE|WITH)\b", sql, re.I
            ):
                tables = sorted(set(TABLE_REF.findall(sql)))
                self.sql_calls.append(
                    {
                        "file": "src/repo_catalog/" + self.relative,
                        "symbol": ".".join(self.scope),
                        "line": node.lineno,
                        "operation": sql.lstrip().split()[0].upper(),
                        "tables": tables,
                        "dynamic_sql": "{dynamic}" in sql,
                        "evidence": "AST SQL interface/forwarding candidate; table tokens are not runtime reachability",
                    }
                )
        self.generic_visit(node)


def generated_inventory():
    """Describe role-qualified structured-field candidates, never a JSON schema."""
    from scripts.audit_callsite_dependencies import source_files
    from scripts.schema_catalog import build_catalog

    stores = build_catalog()["stores"]
    calls = []
    for path in source_files():
        audit = SourceAudit(path.relative_to(ROOT).as_posix())
        audit.visit(ast.parse(path.read_text(encoding="utf-8")))
        calls.extend(audit.sql_calls)
    fields = [
        {
            "store": role,
            "table": table,
            "column": column["name"],
            "type": column["type"],
            "category": "json-name-candidate",
        }
        for role, store in stores.items()
        for table, definition in store["tables"].items()
        for column in definition["columns"]
        if column["name"].endswith("_json")
    ]
    fingerprints = {role: store["ddl_sha256"] for role, store in stores.items()}
    return {
        "schema_version": "separated-roles",
        "ddl_sha256": hashlib.sha256(
            json.dumps(fingerprints, sort_keys=True).encode()
        ).hexdigest(),
        "role_fingerprints": fingerprints,
        "json_column_count": len(fields),
        "category_counts": dict(Counter(field["category"] for field in fields)),
        "json_columns": fields,
        "static_sql_call_sites": calls,
        "limitations": [
            "Suffix candidates are lexical field leads, not a semantic JSON contract or complete list of structured encodings.",
            "Unmodified role-qualified DDL is authoritative for all fields, keys, guards and physical FKs.",
            "Static SQL candidates and projection syntax do not establish runtime reachability.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the selected artifact with this checkout; the default artifact is the frozen historical proposal snapshot",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=CONTRACT,
        help="Write or check a separate current inventory without changing the baseline contract",
    )
    args = parser.parse_args()
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    current = generated_inventory()
    data["generated_inventory"] = current
    encoded = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.check:
        compared = args.output.read_text(encoding="utf-8")
        if encoded != compared:
            snapshot = json.loads(compared).get("generated_inventory", {})
            separate = f"artifacts/schema{current['schema_version']}-fields.json"
            raise SystemExit(
                f"Field inventory differs: {args.output}\n"
                f"Compared artifact: Schema {snapshot.get('schema_version', 'unknown')}, "
                f"DDL SHA-256 {snapshot.get('ddl_sha256', 'unknown')}\n"
                f"Current checkout: Schema {current['schema_version']}, "
                f"DDL SHA-256 {current['ddl_sha256']}\n"
                "Preserve the historical proposal snapshot. Generate and compare a "
                "separate current artifact:\n"
                f"python scripts/audit_phase2_fields.py --output {separate}\n"
                f"python scripts/audit_phase2_fields.py --check --output {separate}"
            )
    else:
        if args.output == CONTRACT:
            raise SystemExit(
                "Preserve the historical proposal snapshot; supply --output for current evidence"
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(
        json.dumps(
            {
                "json_columns": data["generated_inventory"]["json_column_count"],
                "ddl_sha256": current["ddl_sha256"],
                "check": args.check,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
