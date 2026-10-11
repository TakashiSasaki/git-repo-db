"""Inventory executable production dependencies without opening a user catalog.

Run with an explicit --output. SQLite prepares EXPLAIN statements in a fresh
in-memory schema; AST references and unresolved dynamic SQL remain explicitly
static evidence. No catalog rows, HTTP messages, or credentials are collected.
"""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import platform
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from repo_catalog.adapters.sqlite import exchange, json_contracts, schema  # noqa: E402
from repo_catalog.adapters.sqlite.cas_integrity import (  # noqa: E402
    register_git_object_sql_function,
)
from repo_catalog.cli.main import parser as cli_parser  # noqa: E402


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def prepare(db, sql):
    """Collect dependencies from SQLite compilation, never execute a mutation."""
    accesses, functions = set(), set()
    operations = {
        sqlite3.SQLITE_READ: "read",
        sqlite3.SQLITE_INSERT: "insert",
        sqlite3.SQLITE_UPDATE: "update",
        sqlite3.SQLITE_DELETE: "delete",
    }

    def authorizer(action, table, column, database, context):
        if action in operations:
            accesses.add((operations[action], table, column, database, context))
        elif action == sqlite3.SQLITE_FUNCTION:
            functions.add(column)
        return sqlite3.SQLITE_OK

    db.set_authorizer(authorizer)
    try:
        command = "EXPLAIN " + sql
        # A failed binding check follows preparation; it exposes the exact count.
        try:
            db.execute(command)
        except sqlite3.ProgrammingError as error:
            match = re.search(r"uses (\d+), and there are 0 supplied", str(error))
            if not match:
                raise
            # SQLite has already compiled the statement and invoked authorizer.
            # No binding/execution is needed, including for named parameters.
        status, error = "compiled", None
    except sqlite3.Error as failure:
        status, error = "not_compiled", str(failure)
    finally:
        db.set_authorizer(None)
    return {
        "status": status,
        "error": error,
        "accesses": [
            dict(zip(("operation", "object", "column", "database", "context"), row))
            for row in sorted(accesses, key=lambda row: tuple(str(x) for x in row))
        ],
        "functions": sorted(functions),
    }


def schema_inventory(db, ddl):
    objects, tables = {}, {}
    table_types = {
        row[1]: row[2] for row in db.execute("PRAGMA table_list") if row[0] == "main"
    }
    for kind, name, owner, sql in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
    ).fetchall():
        objects[name] = {
            "type": kind,
            "owner": owner,
            "sql_sha256": digest(sql) if sql is not None else None,
            "sql": sql if kind == "table" else None,
            "explicit": sql is not None,
        }
        if kind == "table":
            columns = [
                dict(
                    zip(
                        ("cid", "name", "type", "not_null", "default", "pk", "hidden"),
                        row,
                    )
                )
                for row in db.execute(f"PRAGMA table_xinfo({quote(name)})")
            ]
            foreign = defaultdict(list)
            for row in db.execute(f"PRAGMA foreign_key_list({quote(name)})"):
                foreign[row[0]].append(row)
            keys = []
            for rows in foreign.values():
                rows.sort(key=lambda row: row[1])
                keys.append(
                    {
                        "parent": rows[0][2],
                        "columns": [row[3] for row in rows],
                        "targets": [row[4] for row in rows],
                        "on_update": rows[0][5],
                        "on_delete": rows[0][6],
                        "match": rows[0][7],
                    }
                )
            indexes = []
            for row in db.execute(f"PRAGMA index_list({quote(name)})"):
                indexes.append(
                    {
                        "name": row[1],
                        "unique": bool(row[2]),
                        "origin": row[3],
                        "partial": bool(row[4]),
                        "components": db.execute(
                            f"PRAGMA index_xinfo({quote(row[1])})"
                        ).fetchall(),
                    }
                )
            product = table_types[name] == "table" and not name.startswith("sqlite_")
            tables[name] = {
                "product": product,
                "sqlite_kind": table_types[name],
                "columns": columns,
                "foreign_keys": keys,
                "indexes": indexes,
                "primary_key": [
                    col["name"]
                    for col in sorted(columns, key=lambda col: col["pk"])
                    if col["pk"]
                ],
            }
    views = {
        name: prepare(db, f"SELECT * FROM {quote(name)} LIMIT 0")
        for name, obj in objects.items()
        if obj["type"] == "view"
    }
    # Each statement is prepared only. All column names come from sqlite_schema.
    triggers = {}
    for table, item in tables.items():
        if not item["product"]:
            continue
        assignments = ",".join(
            f"{quote(col['name'])}={quote(col['name'])}"
            for col in item["columns"]
            if not col["hidden"]
        )
        for event, sql in {
            "insert": f"INSERT INTO {quote(table)} DEFAULT VALUES",
            "update": f"UPDATE {quote(table)} SET {assignments} WHERE 0",
            "delete": f"DELETE FROM {quote(table)} WHERE 0",
        }.items():
            triggers[f"{table}:{event}"] = prepare(db, sql)
    product = [item for item in tables.values() if item["product"]]
    return {
        "ddl_sha256": digest(ddl),
        "objects": objects,
        "tables": tables,
        "prepared_views": views,
        "prepared_mutations": triggers,
        "counts": {
            "product_tables": len(product),
            "product_columns": sum(len(item["columns"]) for item in product),
            "foreign_key_constraints": sum(
                len(item["foreign_keys"]) for item in product
            ),
            **{
                plural: sum(
                    obj["type"] == kind and obj["explicit"] for obj in objects.values()
                )
                for kind, plural in (
                    ("view", "views"),
                    ("trigger", "triggers"),
                    ("index", "indexes"),
                )
            },
        },
        "checks": {
            "foreign_keys_enabled": db.execute("PRAGMA foreign_keys").fetchone()[0],
            "recursive_triggers_enabled": db.execute(
                "PRAGMA recursive_triggers"
            ).fetchone()[0],
            "foreign_key_check": db.execute("PRAGMA foreign_key_check").fetchall(),
            "integrity_check": db.execute("PRAGMA integrity_check").fetchall(),
        },
    }


def source_inventory(root, db, object_names):
    functions, calls, sql_sites, references, modules = {}, [], [], [], {}
    sql_cache = {}
    statements = {}

    def callable_path(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return callable_path(node.value) + "." + node.attr
        if isinstance(node, ast.Call):
            return callable_path(node.func) + "()"
        return "<" + type(node).__name__ + ">"

    class Visitor(ast.NodeVisitor):
        def __init__(self, path):
            self.path, self.scope = path, []

        def visit_ClassDef(self, node):
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node):
            self.scope.append(node.name)
            identity = self.path + ":" + ".".join(self.scope)
            functions[identity] = {
                "line": node.lineno,
                "end_line": node.end_lineno,
                "ast_sha256": digest(ast.dump(node, include_attributes=False)),
            }
            self.generic_visit(node)
            self.scope.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            target = callable_path(node.func)
            caller = self.path + ":" + ".".join(self.scope)
            calls.append({"caller": caller, "target": target, "line": node.lineno})
            if (
                target.rsplit(".", 1)[-1] in {"execute", "executemany", "executescript"}
                and node.args
            ):
                expression = node.args[0]
                literal = (
                    expression.value
                    if isinstance(expression, ast.Constant)
                    and isinstance(expression.value, str)
                    else None
                )
                item = {
                    "caller": caller,
                    "line": node.lineno,
                    "target": target,
                    "expression": ast.unparse(expression),
                    "literal": literal,
                }
                if literal and re.match(
                    r"\s*(SELECT|INSERT|UPDATE|DELETE|WITH)\b", literal, re.I
                ):
                    sql_cache.setdefault(literal, None)
                    if sql_cache[literal] is None:
                        sql_cache[literal] = prepare(db, literal)
                    item["preparation"] = sql_cache[literal]
                else:
                    item["preparation"] = {
                        "status": "dynamic_or_non_dml",
                        "error": None,
                    }
                sql_sites.append(item)
            self.generic_visit(node)

        def visit_Constant(self, node):
            if isinstance(node.value, str):
                matches = sorted(
                    set(re.findall(r"[a-z][a-z0-9_]*", node.value)) & object_names
                )
                if matches:
                    references.append(
                        {
                            "file": self.path,
                            "scope": ".".join(self.scope),
                            "line": node.lineno,
                            "objects": matches,
                            "evidence": "AST literal token; not runtime reachability",
                        }
                    )

    for base in (root / "src", root / "tests"):
        for path in sorted(base.rglob("*.py")):
            relative = str(path.relative_to(root))
            source = path.read_text()
            tree = ast.parse(source, filename=relative)
            modules[relative] = {
                "sha256": digest(source),
                "imports": sorted(
                    ast.unparse(node)
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                ),
            }
            Visitor(relative).visit(tree)
    resolved = []
    for call in calls:
        path, scope = call["caller"].split(":", 1)
        target = call["target"]
        candidates = []
        if target.startswith("self.") and "." in scope:
            candidates = [path + ":" + scope.split(".")[0] + "." + target[5:]]
        elif "." not in target:
            candidates = [path + ":" + target]
        call["local_definition"] = next(
            (value for value in candidates if value in functions), None
        )
        if call["local_definition"]:
            resolved.append(
                {
                    "caller": call["caller"],
                    "callee": call["local_definition"],
                    "line": call["line"],
                    "evidence": "syntactic local resolution; dynamic reachability unproven",
                }
            )
    for item in sql_sites:
        statement = {
            key: item.pop(key) for key in ("expression", "literal", "preparation")
        }
        identity = digest(json.dumps(statement, sort_keys=True))
        statements[identity] = statement
        item["statement"] = identity
    return {
        "modules": modules,
        "functions": functions,
        "call_sites": calls,
        "local_call_edges": resolved,
        "sql_sites": sql_sites,
        "sql_statements": statements,
        "static_object_references": references,
    }


def cli_inventory(parser, prefix=()):
    result = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for command, child in action.choices.items():
                path = (*prefix, command)
                result.append(
                    {
                        "command": " ".join(path),
                        "options": sorted(
                            option
                            for entry in child._actions
                            for option in entry.option_strings
                        ),
                    }
                )
                result.extend(cli_inventory(child, path))
    return result


def build_report(root=ROOT):
    ddl = schema.schema_sql()
    with sqlite3.connect(":memory:", isolation_level=None, cached_statements=0) as db:
        register_git_object_sql_function(db)
        db.executescript(ddl)
        physical = schema_inventory(db, ddl)
        source = source_inventory(root, db, set(physical["objects"]))
        graph = exchange.Graph(db)
        wire = {table: sorted(graph.expected_columns(table)) for table in graph.columns}
        registry = json_contracts.inventory(db)
    packaged = root / "src/repo_catalog/resources/json_contracts.sql"
    composer = ast.parse(
        (root / "src/repo_catalog/adapters/sqlite/schema.py").read_text()
    )
    composition = [
        node.value
        for node in ast.walk(composer)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith(".sql")
    ]

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True
        ).strip()

    return {
        "format": "git-repo-db/phase2-dependency-audit-v1",
        "revision": {
            "head": git("rev-parse", "HEAD"),
            "head_tree": git("rev-parse", "HEAD^{tree}"),
            "tracked_changes": git("status", "--porcelain", "--untracked-files=no"),
        },
        "runtime": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
        },
        "loaded_modules": {
            module.__name__: str(Path(module.__file__).resolve().relative_to(root))
            for module in (schema, exchange, json_contracts)
        },
        "composition": composition,
        "schema_version": schema.SCHEMA_VERSION,
        "schema": physical,
        "source": source,
        "cli_commands": cli_inventory(cli_parser()),
        "json": {
            "inventory": registry,
            "reference_targets": json_contracts.REFERENCE_TARGETS,
            "reference_lists": json_contracts.REFERENCE_LISTS,
            "local_reference_keys": sorted(json_contracts.LOCAL_REFERENCE_KEYS),
            "generated_guards_equal": json_contracts.guard_sql()
            == packaged.read_text(),
        },
        "exchange": {
            "wire_columns": wire,
            "excluded": sorted(exchange.EXCLUDED),
            "original_proof_tables": sorted(exchange.ORIGINAL_PROOF_TABLES),
        },
        "limits": [
            "SQL preparation proves syntactic access, not a reachable product operation.",
            "AST literals and locally resolved calls are static evidence; dispatch, fixture execution and workstream traces supply runtime evidence.",
            "Dynamic SQL and unsuccessful preparation are listed, never inferred to be dead.",
            "Fresh integrity checks cover the composed schema, not retained catalog contents.",
        ],
    }


def main(argv=None):
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--output", type=Path, required=True)
    arguments.add_argument(
        "--source-output",
        type=Path,
        help="Optional deterministic gzip JSON for the full AST/SQL inventory",
    )
    args = arguments.parse_args(argv)
    report = build_report()
    if args.source_output:
        raw = json.dumps(
            report.pop("source"), sort_keys=True, separators=(",", ":")
        ).encode()
        args.source_output.parent.mkdir(parents=True, exist_ok=True)
        args.source_output.write_bytes(gzip.compress(raw, mtime=0))
        report["source"] = {
            "artifact": str(args.source_output),
            "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
            "compression": "gzip",
            "meaning": "Complete AST functions/calls/imports/static literals and prepared/dynamic SQL; no runtime reachability inference",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "schema_version": report["schema_version"],
                "ddl_sha256": report["schema"]["ddl_sha256"],
                "counts": report["schema"]["counts"],
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
