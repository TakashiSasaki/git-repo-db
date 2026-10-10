"""Inventory exact composed DDL and repository-wide AST before/after retirement.

Baseline resources/source are read with git show; neither tree is checked out or
any retained database opened. Output contains full column/key inventories, object
DDL fingerprints, imports, changed functions and relevant call sites. Static
edges are investigation evidence, not proof of dynamic runtime reachability.
"""

import argparse
import ast
import hashlib
import json
import platform
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_catalog.adapters.sqlite.cas_integrity import (  # noqa: E402
    register_git_object_sql_function,
)
from repo_catalog.adapters.sqlite.json_contracts import (  # noqa: E402
    guard_sql,
    inventory,
)
from repo_catalog.adapters.sqlite.schema import SCHEMA_VERSION, schema_sql  # noqa: E402
from scripts.audit_current_state import inspect, quote  # noqa: E402

BASELINE = "47fd5b88355b98019c0c04408449081e16ab4505"
CALL_SEEDS = {
    "_message",
    "_inspect_message",
    "admit",
    "aggregate_proof",
    "backup",
    "decode",
    "detail",
    "exchange",
    "export",
    "failed_graphql_page",
    "inventory",
    "inventory_input",
    "inventory_request",
    "inventory_result",
    "original_dependencies",
    "original_root",
    "page",
    "partial",
    "partial_rest_collection",
    "payload",
    "promote",
    "receive",
    "record",
    "repair_payload",
    "reparse",
    "require_original_records",
    "result",
    "restore",
    "saved_thread_code_input",
    "source_input",
    "stage_rejected",
    "stage_verified_payload",
    "threads",
    "verify_all",
    "intern_payload",
    "intern_stored_bytes",
}


def git(*arguments):
    result = subprocess.check_output(["git", *arguments], text=True)
    return result if arguments[0] == "show" else result.strip()


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def vocabulary(source):
    """Read literal registry declarations without executing historical code."""
    tree, fields, references = ast.parse(source), {}, {}
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == "_register":
                category, names = (ast.literal_eval(value) for value in call.args)
                options = {
                    keyword.arg: ast.literal_eval(keyword.value)
                    for keyword in call.keywords
                }
                for name in names.split():
                    fields[name] = {
                        "category": category,
                        "shape": options.get("shape", "object"),
                        "nullable": options.get("nullable", False),
                    }
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "REFERENCE_TARGETS",
                    "REFERENCE_LISTS",
                    "LOCAL_REFERENCE_KEYS",
                }:
                    value = ast.literal_eval(node.value)
                    references[target.id] = (
                        sorted(value) if isinstance(value, set) else value
                    )
    return {"fields": fields, "reference_vocabulary": references}


def sources(baseline=None):
    if baseline:
        paths = git(
            "ls-tree", "-r", "--name-only", baseline, "src/repo_catalog"
        ).splitlines()
        return {
            path: git("show", f"{baseline}:{path}")
            for path in paths
            if path.endswith(".py")
        }
    return {
        str(path): path.read_text()
        for path in sorted(Path("src/repo_catalog").rglob("*.py"))
    }


def runtime_inventory(source_files):
    modules, functions, calls = {}, {}, []

    class Visitor(ast.NodeVisitor):
        def __init__(self, path):
            self.path, self.scope = path, []

        def visit_ClassDef(self, node):
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def visit_FunctionDef(self, node):
            self.scope.append(node.name)
            name = self.path + ":" + ".".join(self.scope)
            functions[name] = {
                "line": node.lineno,
                "ast_sha256": sha(ast.dump(node, include_attributes=False)),
            }
            self.generic_visit(node)
            self.scope.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            target = ast.unparse(node.func)
            if target.rsplit(".", 1)[-1] in CALL_SEEDS:
                calls.append(
                    {
                        "file": self.path,
                        "line": node.lineno,
                        "caller": ".".join(self.scope),
                        "target": target,
                    }
                )
            self.generic_visit(node)

    for path, source in source_files.items():
        tree = ast.parse(source)
        modules[path] = {
            "imports": sorted(
                ast.unparse(node)
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
            )
        }
        Visitor(path).visit(tree)
    return {
        "module_count": len(modules),
        "modules": modules,
        "functions": functions,
        "call_sites": calls,
    }


def schema_inventory(ddl):
    result = inspect(ddl)
    with sqlite3.connect(":memory:") as db:
        register_git_object_sql_function(db)
        db.executescript(ddl)
        objects = db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
        ).fetchall()
        indexes = {}
        for kind, name, table, sql in objects:
            if kind == "index":
                indexes[name] = {
                    "table": table,
                    "implicit": sql is None,
                    "columns": db.execute(
                        f"PRAGMA index_xinfo({quote(name)})"
                    ).fetchall(),
                }
        result["indexes"] = indexes
        internal = {
            row[1]
            for row in db.execute("PRAGMA table_list")
            if row[2] in {"virtual", "shadow"} or row[1].startswith("sqlite_")
        }
        product = set(result["table_columns"]) - internal
        result["counting"] = (
            "Product tables exclude SQLite metadata/internal, FTS virtual and shadow objects. FK clauses count constraints; components count individual columns. Indexes with SQL are explicit; null SQL indexes are implicit. Counts overlap and must not be added."
        )
        result["counts"] = {
            "product_tables": len(product),
            "fts_and_sqlite_internal_tables": len(
                set(result["table_columns"]) & internal
            ),
            "columns_product": sum(
                len(result["table_columns"][name]) for name in product
            ),
            "foreign_key_clauses_product": sum(
                len(result["native_foreign_keys"][name]) for name in product
            ),
            "foreign_key_components_product": sum(
                len(fk["columns"])
                for name in product
                for fk in result["native_foreign_keys"][name]
            ),
            "views": result["object_counts"]["view"],
            "triggers": result["object_counts"]["trigger"],
            "explicit_indexes": sum(
                not value["implicit"] for value in indexes.values()
            ),
            "implicit_indexes": sum(value["implicit"] for value in indexes.values()),
        }
        result["compiled_views"] = []
        for name in result["objects"]["view"]:
            db.execute(f"SELECT * FROM {quote(name)} LIMIT 0")
            result["compiled_views"].append(name)
        result["compiled_trigger_tables"] = []
        for table in sorted({row[2] for row in objects if row[0] == "trigger"}):
            columns = [
                row[1]
                for row in db.execute(f"PRAGMA table_xinfo({quote(table)})")
                if not row[6]
            ]
            names = ",".join(quote(name) for name in columns)
            assignments = ",".join(f"{quote(name)}={quote(name)}" for name in columns)
            for statement in (
                f"INSERT INTO {quote(table)} ({names}) VALUES ({','.join('?' for _ in columns)})",
                f"UPDATE {quote(table)} SET {assignments}",
                f"DELETE FROM {quote(table)}",
            ):
                db.execute(
                    "EXPLAIN " + statement, (None,) * statement.count("?")
                ).fetchall()
            result["compiled_trigger_tables"].append(table)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    arguments = parser.parse_args()
    composer = git(
        "show", f"{arguments.baseline}:src/repo_catalog/adapters/sqlite/schema.py"
    )
    resources = re.findall(r'"([a-z_0-9]+\.sql)"', composer)
    old_ddl = "\n".join(
        git("show", f"{arguments.baseline}:src/repo_catalog/resources/{name}")
        for name in resources
    )
    before, after = schema_inventory(old_ddl), schema_inventory(schema_sql())
    before["schema_version"] = int(re.search(r"SCHEMA_VERSION = (\d+)", composer)[1])
    after["schema_version"] = SCHEMA_VERSION
    old_sources, new_sources = sources(arguments.baseline), sources()
    old_runtime, new_runtime = (
        runtime_inventory(old_sources),
        runtime_inventory(new_sources),
    )
    column_delta = {}
    fk_delta = {}
    for table in before["table_columns"].keys() | after["table_columns"].keys():
        old = {
            column["name"]: {
                key: value for key, value in column.items() if key != "cid"
            }
            for column in before["table_columns"].get(table, [])
        }
        new = {
            column["name"]: {
                key: value for key, value in column.items() if key != "cid"
            }
            for column in after["table_columns"].get(table, [])
        }
        if old != new:
            column_delta[table] = {
                "removed": sorted(old.keys() - new.keys()),
                "added": sorted(new.keys() - old.keys()),
                "modified": sorted(
                    name for name in old.keys() & new.keys() if old[name] != new[name]
                ),
            }
        old_fks, new_fks = (
            before["native_foreign_keys"].get(table, []),
            after["native_foreign_keys"].get(table, []),
        )
        if old_fks != new_fks:
            fk_delta[table] = {
                "removed": [fk for fk in old_fks if fk not in new_fks],
                "added": [fk for fk in new_fks if fk not in old_fks],
            }
    function_delta = {
        "removed": sorted(
            old_runtime["functions"].keys() - new_runtime["functions"].keys()
        ),
        "added": sorted(
            new_runtime["functions"].keys() - old_runtime["functions"].keys()
        ),
        "modified": sorted(
            name
            for name in old_runtime["functions"].keys()
            & new_runtime["functions"].keys()
            if old_runtime["functions"][name]["ast_sha256"]
            != new_runtime["functions"][name]["ast_sha256"]
        ),
    }
    generated = guard_sql()
    assert (
        generated == Path("src/repo_catalog/resources/json_contracts.sql").read_text()
    )
    with sqlite3.connect(":memory:") as db:
        register_git_object_sql_function(db)
        db.executescript(schema_sql())
        json_fields = inventory(db)
    report = {
        "baseline_commit": arguments.baseline,
        "baseline_tree": git("rev-parse", arguments.baseline + "^{tree}"),
        "observed_head": git("rev-parse", "HEAD"),
        "observed_head_tree": git("rev-parse", "HEAD^{tree}"),
        "working_tree_status": git("status", "--porcelain").splitlines(),
        "runtime": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
        },
        "composition": resources,
        "before": before,
        "after": after,
        "column_changes": column_delta,
        "foreign_key_changes": fk_delta,
        "runtime_before": old_runtime,
        "runtime_after": new_runtime,
        "function_changes": function_delta,
        "json_before": vocabulary(
            old_sources["src/repo_catalog/adapters/sqlite/json_contracts.py"]
        ),
        "json_after": vocabulary(
            new_sources["src/repo_catalog/adapters/sqlite/json_contracts.py"]
        ),
        "json_fields_executed": json_fields,
        "generated_json_guard_sha256": sha(generated),
        "script_sha256": sha(Path(__file__).read_text()),
        "runtime_limit": "AST references do not prove dynamic reachability or legitimate retained purpose; use the implementation dependency map and instrumented rejection/exchange tests.",
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if arguments.summary:
        object_delta = {}
        for kind, old in before["objects"].items():
            new = after["objects"][kind]
            object_delta[kind] = {
                "removed": sorted(old.keys() - new.keys()),
                "added": sorted(new.keys() - old.keys()),
                "modified": sorted(
                    name for name in old.keys() & new.keys() if old[name] != new[name]
                ),
            }
        summary = {
            "baseline_commit": report["baseline_commit"],
            "baseline_tree": report["baseline_tree"],
            "runtime": report["runtime"],
            "composition": resources,
            "counting": after["counting"],
            "before": {
                "schema_version": before["schema_version"],
                "ddl_sha256": before["ddl_sha256"],
                "counts": before["counts"],
            },
            "after": {
                "schema_version": after["schema_version"],
                "ddl_sha256": after["ddl_sha256"],
                "counts": after["counts"],
            },
            "object_changes": object_delta,
            "column_changes": column_delta,
            "foreign_key_changes": fk_delta,
            "function_changes": function_delta,
            "changed_python_source_fingerprints": {
                path: {
                    "before": sha(old_sources[path]) if path in old_sources else None,
                    "after": sha(new_sources[path]) if path in new_sources else None,
                }
                for path in sorted(old_sources.keys() | new_sources.keys())
                if old_sources.get(path) != new_sources.get(path)
            },
            "json_field_changes": {
                name: {
                    "before": report["json_before"]["fields"].get(name),
                    "after": report["json_after"]["fields"].get(name),
                }
                for name in sorted(
                    report["json_before"]["fields"].keys()
                    | report["json_after"]["fields"].keys()
                )
                if report["json_before"]["fields"].get(name)
                != report["json_after"]["fields"].get(name)
            },
            "json_reference_vocabulary_changed": report["json_before"][
                "reference_vocabulary"
            ]
            != report["json_after"]["reference_vocabulary"],
            "classified_json_fields": len(json_fields),
            "generated_json_guard_sha256": report["generated_json_guard_sha256"],
            "script_sha256": report["script_sha256"],
            "checks": {
                label: {
                    "foreign_key_check": snapshot["foreign_key_check"],
                    "integrity_check": snapshot["integrity_check"],
                    "compiled_views": len(snapshot["compiled_views"]),
                    "compiled_trigger_tables": len(snapshot["compiled_trigger_tables"]),
                }
                for label, snapshot in (("before", before), ("after", after))
            },
            "runtime_limit": report["runtime_limit"],
        }
        arguments.summary.parent.mkdir(parents=True, exist_ok=True)
        arguments.summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
    print(
        json.dumps(
            {
                "before": before["counts"],
                "after": after["counts"],
                "columns": column_delta,
                "fks": fk_delta,
                "removed_functions": function_delta["removed"],
                "output": str(arguments.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
