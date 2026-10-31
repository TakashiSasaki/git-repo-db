"""Reproduce the implemented three-store inventory and check table dispositions.

Executes composed packaged DDL in disposable in-memory databases; never opens a
catalog. Target recommendations are authored, explicit rows, not name heuristics.
SQL/registry references are lexical evidence, not a claim to solve dynamic SQL.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_callsite_dependencies import (  # noqa: E402
    SOURCE_ROOTS,
    is_baseline_source,
    source_files,
)
from schema_inventory import introspect_all  # noqa: E402

OUTPUT = ROOT / "docs/implementation"


def source_references(names: set[str]) -> dict[str, list[dict]]:
    """Locate table tokens in actual Python code, including dynamic registries.

    Each occurrence retains its actual line, enclosing function and source text.
    A mention in a registry is intentionally distinct from a literal SQL write.
    Dynamic helpers and integration entry points need the companion human audit.
    """
    result: dict[str, list[dict]] = {name: [] for name in names}
    token = re.compile(r"\b(" + "|".join(sorted(names)) + r")\b")
    for path in source_files():
        if not is_baseline_source(path):
            continue
        content = path.read_text()
        parsed = ast.parse(content)
        scopes = [
            node
            for node in ast.walk(parsed)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        for number, line in enumerate(content.splitlines(), 1):
            matched = set(token.findall(line))
            if not matched:
                continue
            enclosing = sorted(
                (s for s in scopes if s.lineno <= number <= s.end_lineno),
                key=lambda s: s.end_lineno - s.lineno,
            )
            operation = "registry_or_reference"
            for op, pattern in (
                ("insert", r"\bINSERT(?:\s+OR\s+\w+)?\s+INTO\b"),
                ("update", r"\bUPDATE\s+\w+\s+SET\b"),
                ("delete", r"\bDELETE\s+FROM\b"),
                ("read", r"\b(?:SELECT|FROM|JOIN)\b"),
            ):
                if re.search(pattern, line, re.I):
                    operation = op
                    break
            for name in sorted(matched):
                result[name].append(
                    {
                        "path": str(path.relative_to(ROOT)),
                        "line": number,
                        "scope": enclosing[0].name if enclosing else "<module>",
                        "operation_hint": operation,
                        "excerpt": line.strip()[:500],
                        "excerpt_truncated": len(line.strip()) > 500,
                    }
                )
    return result


def build() -> tuple[dict, str]:
    inventory = introspect_all()
    mapping = json.loads((OUTPUT / "table-disposition.json").read_text())
    rows = mapping["tables"]
    names = [r["table"] for r in rows]
    if len(names) != len(set(names)):
        raise ValueError("duplicate disposition table")
    tables = {
        name: table
        for store in inventory["stores"].values()
        for name, table in store["tables"].items()
    }
    if set(names) != set(tables):
        raise ValueError(
            f"disposition mismatch: missing={sorted(set(tables) - set(names))}; "
            f"obsolete={sorted(set(names) - set(tables))}"
        )
    references = source_references(set(tables))
    dispositions = {row["table"]: row for row in rows}
    allowed = {"retain", "move", "split", "replace", "eliminate", "combine"}
    for name, table in tables.items():
        policy = dispositions[name]
        required = (
            "purpose",
            "target_stores",
            "target_domain_identity",
            "key_audit",
            "retention_and_migration_concern",
            "adrs",
            "required_tests",
            "planned_pr",
        )
        if policy["disposition"] not in allowed or any(
            not policy.get(field) for field in required
        ):
            raise ValueError(f"incomplete classification: {name}")
        actual_columns = [c["name"] for c in table["columns"]]
        if policy["current_product_columns"] != actual_columns or set(
            policy["column_disposition"]
        ) != set(actual_columns):
            raise ValueError(f"column disposition drift: {name}")
        table["implementation_recommendation"] = policy
        table["source_references"] = references[name]
        store = inventory["stores"][table["store"]]
        table["dependent_views"] = [
            vn
            for vn, view in store["views"].items()
            if re.search(r"\b" + re.escape(name) + r"\b", view["sql"])
        ]
        table["update_guard_triggers"] = [
            tn
            for tn in table["triggers"]
            if re.match(
                r"CREATE TRIGGER \S+ (?:BEFORE|AFTER) UPDATE\b",
                store["triggers"][tn]["sql"],
                re.I,
            )
        ]
        table["baseline_authority"] = policy["baseline_fact_class"]
    inventory["audit_contract"] = {
        "status": "Implemented baseline plus separate target recommendations; not target DDL",
        "inputs": [
            "src/repo_catalog/adapters/sqlite/schema.py",
            "src/repo_catalog/resources/*.sql composed by schema.py",
            *[
                f"{source.relative_to(ROOT).as_posix()}/**/*.py lexical references"
                for source in SOURCE_ROOTS
            ],
            "docs/implementation/table-disposition.json explicit authored dispositions",
        ],
        "checks": [
            "Exact table-set equality; no unclassified or duplicate product tables",
            "Composed DDL hashes from production schema functions",
            "Column including generated-column, ordered PK/FK and partial-index introspection",
            "Full trigger/view/index SQL, generated JSON guards and SQL fingerprints",
            "Source references include dynamic table registries, not just SQL statements",
            "--check compares every generated byte; DDL or reference drift fails",
        ],
        "limits": [
            "Lexical operation hints are not a Python/SQL data-flow proof",
            "Dynamic table names and generic validators are traced in callsite-dependencies.md",
            "No real catalogs opened; no production target schema or migration implemented",
        ],
        "table_counts": {
            name: store["table_count"] for name, store in inventory["stores"].items()
        },
        "disposition_counts": dict(
            sorted(Counter(r["disposition"] for r in rows).items())
        ),
        "unclassified": [],
    }
    return inventory, render(inventory)


def render(inventory: dict) -> str:
    contract = inventory["audit_contract"]
    lines = [
        "# Complete implemented table disposition audit",
        "",
        "Generated by `uv run --no-sync python scripts/audit_implementation_boundary.py`.",
        "Regeneration executes production composed SQL only in memory. `--check` detects",
        "new/deleted tables, changed DDL/guards/indexes and changed lexical call sites.",
        "Authored target rows are in `table-disposition.json`; current exact DDL, ordered",
        "PK/FK, UNIQUE constraints, partial-index predicates, generated columns, all view/",
        "trigger SQL and per-function source locations are in `schema-inventory.json`.",
        "These are implementation recommendations, not implemented target DDL.",
        "",
        f"Product tables: {contract['table_counts']}. Dispositions: {contract['disposition_counts']}.",
        "Unclassified: 0. Dynamic FTS tables/shadows and SQLite internal tables are excluded",
        "from static product counts; they remain disposable Search implementation details.",
        "See `callsite-dependencies.md` for generic reader/writer/Exchange/backup/CLI edges and",
        "`audit-notes.md` for column-level cross-domain routing and Coverage/key reconciliation.",
        "",
        "| Current store/table | Purpose | Disposition / target | Target semantic identity | Stack PR |",
        "| --- | --- | --- | --- | --- |",
    ]
    for slug, store in inventory["stores"].items():
        for name, table in store["tables"].items():
            p = table["implementation_recommendation"]
            lines.append(
                f"| {slug}.`{name}` | {p['purpose']} | {p['disposition']}: "
                f"{', '.join(p['target_stores'])} | {p['target_domain_identity']} | {p['planned_pr']} |"
            )
    for slug, store in inventory["stores"].items():
        lines += ["", f"## {slug} — Schema {store['schema_version']}", ""]
        lines += [
            f"Composed DDL SHA-256: `{store['ddl_sha256']}`; {store['table_count']} tables, "
            f"{store['view_count']} views, {store['trigger_count']} triggers, "
            f"{store['index_count']} explicit indexes, {store['foreign_key_count']} FK constraints.",
            "",
        ]
        for name, table in store["tables"].items():
            p = table["implementation_recommendation"]
            columns = ", ".join(
                c["name"] + (" [generated]" if c["is_generated"] else "")
                for c in table["columns"]
            )
            unique = (
                "; ".join(
                    "(" + ", ".join(u["columns"]) + ")"
                    for u in table["unique_constraints"]
                )
                or "none beyond PK"
            )
            fks = (
                "; ".join(
                    "("
                    + ", ".join(fk["from_columns"])
                    + ") → "
                    + fk["target_table"]
                    + "("
                    + ", ".join(fk["to_columns"])
                    + ")"
                    for fk in table["foreign_keys"]
                )
                or "none"
            )
            refs = table["source_references"]
            modules = sorted({r["path"] for r in refs})
            mutation_refs = [
                r for r in refs if r["operation_hint"] in ("insert", "update", "delete")
            ]
            writes = (
                "; ".join(
                    f"{r['operation_hint']} `{r['path']}:{r['line']}` ({r['scope']})"
                    for r in mutation_refs
                )
                or "No literal one-line SQL mutation found; inspect registry/generic adapters below"
            )
            lines += [
                f"### `{name}`",
                "",
                f"{p['purpose']}. Baseline authority: {table['baseline_authority']}.",
                "",
                f"- Columns: {columns}.",
                f"- Current PK: ({', '.join(table['primary_key'])}); UNIQUE: {unique}.",
                f"- Current FKs: {fks}.",
                f"- Key assessment: {p['key_audit']}.",
                f"- Baseline mutable columns: {', '.join(p['current_mutable_columns']) or 'none intended'}. Subject to full existing guards; this is not a permission to mutate target Core.",
                f"- Target: **{p['disposition']}** → {', '.join(p['target_stores'])}; identity: {p['target_domain_identity']}.",
                f"- Retention/extraction concern: {p['retention_and_migration_concern']}. No real-data extraction is authorized.",
                f"- Literal writer evidence: {writes}.",
                f"- Reader/writer/registry modules ({len(refs)} exact references in JSON): "
                + ", ".join(f"`{module}`" for module in modules)
                + ".",
                f"- Views: {', '.join(table['dependent_views']) or 'none'}; triggers ({len(table['triggers'])}): "
                + ", ".join(table["triggers"])
                + ". Full guard SQL in JSON.",
                "- ADRs: "
                + ", ".join(p["adrs"])
                + f"; dependent implementation: **{p['planned_pr']}**.",
                "- Required regressions: " + "; ".join(p["required_tests"]) + ".",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    inventory, markdown = build()
    artifacts = {
        "schema-inventory.json": json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        "table-disposition.md": markdown,
    }
    stale = []
    for name, content in artifacts.items():
        path = OUTPUT / name
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(
                    str(path.relative_to(ROOT))
                    if path.is_relative_to(ROOT)
                    else path.name
                )
        else:
            path.write_text(content)
    if stale:
        print("stale audit artifacts: " + ", ".join(stale), file=sys.stderr)
        return 1
    print(json.dumps(inventory["audit_contract"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
