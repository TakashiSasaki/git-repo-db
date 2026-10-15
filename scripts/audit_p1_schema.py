#!/usr/bin/env python3
"""Reconcile every baseline column with the executable isolated P1 schemas.

The authored routes are deliberately not inferred from similar column names.
``--write`` refreshes only introspected schema evidence; it cannot invent routes.
``--check`` validates routes and compares every recorded constraint to SQLite.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from repo_catalog.adapters.sqlite import p1_schema

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/implementation/p1-disposition.json"
BASELINE = ROOT / "docs/implementation/schema-inventory.json"
DISPOSITIONS = ROOT / "docs/implementation/table-disposition.json"
STORES = ("core", "context", "operational", "search")


def introspect() -> dict[str, Any]:
    """Construct fresh stores and inspect physical columns, ordered keys and SQL."""
    result = {}
    for store in STORES:
        connection = sqlite3.connect(":memory:")
        try:
            p1_schema.register_functions(connection)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA recursive_triggers=ON")
            connection.executescript(p1_schema.compose(store))
            tables = {}
            for name, sql in connection.execute(
                "SELECT name,sql FROM sqlite_schema WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ):
                columns = list(connection.execute(f'PRAGMA table_xinfo("{name}")'))
                indexes = []
                for index in connection.execute(f'PRAGMA index_list("{name}")'):
                    if index[2]:
                        indexes.append(
                            {
                                "columns": [
                                    row[2]
                                    for row in connection.execute(
                                        f'PRAGMA index_info("{index[1]}")'
                                    )
                                ],
                                "origin": index[3],
                                "partial": bool(index[4]),
                            }
                        )
                tables[name] = {
                    "columns": [
                        {
                            "name": c[1],
                            "type": c[2],
                            "notnull": bool(c[3]),
                            "generated": c[6],
                        }
                        for c in columns
                    ],
                    "primary_key": [
                        c[1] for c in sorted(columns, key=lambda c: c[5]) if c[5]
                    ],
                    "unique": sorted(
                        indexes, key=lambda i: (i["columns"], i["origin"])
                    ),
                    "foreign_keys": [
                        list(row)
                        for row in connection.execute(
                            f'PRAGMA foreign_key_list("{name}")'
                        )
                    ],
                    "sql": sql,
                    "triggers": dict(
                        connection.execute(
                            "SELECT name,sql FROM sqlite_schema WHERE type='trigger' "
                            "AND tbl_name=? ORDER BY name",
                            (name,),
                        )
                    ),
                }
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError(f"Fresh {store} contains FK violations")
            result[store] = {
                "ddl_sha256": p1_schema.fingerprint(store),
                "tables": tables,
            }
        finally:
            connection.close()
    return result


def validate_routes(manifest: dict[str, Any], actual: dict[str, Any]) -> None:
    baseline = json.loads(BASELINE.read_text())
    dispositions = {
        r["table"]: r for r in json.loads(DISPOSITIONS.read_text())["tables"]
    }
    old = {
        name: (store, table)
        for store, schema in baseline["stores"].items()
        for name, table in schema["tables"].items()
    }
    routes = manifest["legacy_tables"]
    if set(routes) != set(old):
        raise ValueError("Baseline table set differs: omitted or unclassified table")
    for name, (store, table) in old.items():
        route = routes[name]
        if (
            route["baseline_owner"] != store
            or route["disposition"] != dispositions[name]["disposition"]
        ):
            raise ValueError(f"{name}: baseline owner/disposition drift")
        columns = {column["name"] for column in table["columns"]}
        if set(route["columns"]) != columns:
            raise ValueError(f"{name}: omitted or unclassified baseline column")
        if bool(route.get("target_tables")) == bool(route.get("elimination")):
            raise ValueError(
                f"{name}: concrete table successor or justified elimination required"
            )
        for target in route.get("target_tables", []):
            if target["table"] not in actual.get(target["store"], {}).get("tables", {}):
                raise ValueError(f"{name}: missing physical table successor")
        if route.get("target_tables") and not route.get("representation"):
            raise ValueError(f"{name}: table semantic representation missing")
        for column, value in route["columns"].items():
            if not value.get("meaning"):
                raise ValueError(f"{name}.{column}: missing semantic explanation")
            targets = value.get("targets", [])
            if bool(targets) == bool(value.get("elimination")):
                raise ValueError(
                    f"{name}.{column}: exactly one concrete route or elimination required"
                )
            for target in targets:
                owner, target_table = target["store"], target["table"]
                if owner not in actual or target_table not in actual[owner]["tables"]:
                    raise ValueError(
                        f"{name}.{column}: missing target {owner}.{target_table}"
                    )
                names = {
                    c["name"] for c in actual[owner]["tables"][target_table]["columns"]
                }
                if not target["columns"] or not set(target["columns"]) <= names:
                    raise ValueError(f"{name}.{column}: missing concrete target column")
                if not target.get("encoding"):
                    raise ValueError(
                        f"{name}.{column}: lossless semantic mapping not explained"
                    )
    target_tables = {
        f"{owner}.{name}"
        for owner, schema in actual.items()
        for name in schema["tables"]
    }
    if set(manifest["target_contracts"]) != target_tables:
        raise ValueError("Unclassified target ownership or stale target contract")
    for qualified, contract in manifest["target_contracts"].items():
        owner, name = qualified.split(".", 1)
        for required in (
            "domain",
            "durability",
            "mutation",
            "semantic_key",
            "cross_store",
            "retention",
        ):
            if not contract.get(required):
                raise ValueError(f"{qualified}: missing {required} contract")
        if contract["durability"] != (
            "authoritative" if owner in ("core", "context") else "reconstructible"
        ):
            raise ValueError(f"{qualified}: incorrect durability owner")
        table = actual[owner]["tables"][name]
        if not table["primary_key"]:
            raise ValueError(f"{qualified}: no direct semantic primary key")
        if owner == "core" and not (
            any("UPDATE" in sql.upper() for sql in table["triggers"].values())
            and any("DELETE" in sql.upper() for sql in table["triggers"].values())
        ):
            raise ValueError(f"{qualified}: missing immutable-state triggers")
        if name in {
            "payload_quarantine",
            "payload_admission_staging",
            "unresolved_payloads",
            "publications",
        }:
            raise ValueError(f"{qualified}: prohibited authority restored")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    actual = introspect()
    validate_routes(manifest, actual)
    if args.write:
        manifest["target_schemas"] = actual
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    elif manifest["target_schemas"] != actual:
        raise SystemExit(
            "P1 physical schema drift: inspect constraints, then regenerate with --write"
        )
    count = sum(len(row["columns"]) for row in manifest["legacy_tables"].values())
    print(
        f"P1 reconciliation: {len(manifest['legacy_tables'])} baseline tables, {count} columns; "
        f"{sum(len(s['tables']) for s in actual.values())} target tables; zero unclassified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
