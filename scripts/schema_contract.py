"""Validate/generate P1 design artifacts. No source DB or cache is opened.

The contract is a typed recipe specification, not a converter. Pure scalar rules
are executable here; lookup/allocation/replay and persistence are P2--P4 work.
"""

import argparse
import csv
import hashlib
import json
import sqlite3
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "docs/schema-hardening"

# Registered grammar: adding a transform requires a reviewed signature here as
# well as a contract entry. Contextual recipes are implemented by later stages.
SIGNATURES = {
    "copy": (1, None),
    "oid_decode": (1, "BLOB"),
    "utf8_bytes": (1, "BLOB"),
    "byte_length": (1, "INTEGER"),
    "sha256": (1, "BLOB"),
    "source_kind": (1, "TEXT"),
    "constant": (0, None),
    "null": (0, None),
    "caller": (1, None),
    "allocate_id": (1, None),
    "lookup_binding": (2, "TEXT"),
    "lookup_body": (1, "INTEGER"),
    "lookup_scope": (1, "TEXT"),
    "lookup_last_attempt": (1, "INTEGER"),
    "replay_listing": (1, "TEXT"),
    "lookup_occurrence": (1, "INTEGER"),
    "lookup_root": (1, "INTEGER"),
    "lookup_cache": (1, "TEXT"),
    "lookup_cr": (2, "TEXT"),
    "oid_format": (1, "TEXT"),
    "job_kind": (1, "TEXT"),
    "legacy_state": (1, "TEXT"),
    "sqlite_exact_bytes": (1, "BLOB"),
}


def construct(sql=None):
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.executescript(sql or (ROOT / "target-schema.sql").read_text())
    return db


def inventory(db):
    result = {}
    for (name,) in db.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
    ):
        result[name] = [
            dict(
                zip(("cid", "name", "type", "notnull", "default", "pk", "hidden"), row)
            )
            for row in db.execute(f"PRAGMA table_xinfo({name})")
        ]
    return result


def scalar(rule, value):
    if rule == "copy":
        return value
    if rule == "utf8_bytes":
        return value.encode("utf-8")
    if rule == "byte_length":
        return len(value.encode("utf-8") if isinstance(value, str) else value)
    if rule == "sha256":
        return hashlib.sha256(
            value.encode("utf-8") if isinstance(value, str) else value
        ).digest()
    if rule == "oid_decode":
        if (
            not isinstance(value, str)
            or len(value) not in (40, 64)
            or any(c not in "0123456789abcdefABCDEF" for c in value)
        ):
            raise ValueError("INVALID_OID")
        return bytes.fromhex(value)
    if rule == "source_kind":
        return {
            "local-git": "manual_git",
            "git-url": "manual_git",
            "github": "github_inventory",
        }[value]
    raise ValueError("Not a scalar rule")


def archive_bytes(storage_type, value):
    """TEXT/BLOB inputs are exact bytes obtained with SQLite CAST(value AS BLOB)."""
    if storage_type == "null":
        if value is not None:
            raise ValueError("NULL type mismatch")
        return b""
    if storage_type == "integer":
        if type(value) is not int or not -(2**63) <= value < 2**63:
            raise ValueError("INTEGER type mismatch")
        return str(value).encode("ascii")
    if storage_type == "real":
        if type(value) is not float:
            raise ValueError("REAL type mismatch")
        return struct.pack(">d", value)
    if storage_type in ("text", "blob"):
        if not isinstance(value, bytes):
            raise ValueError("Use exact CAST bytes")
        return value
    raise ValueError("Unknown SQLite storage type")


def tagged_key(values):
    """PK-order (typeof, value) pairs; type tag + uint64 length + exact bytes."""
    tags = {"null": b"N", "integer": b"I", "real": b"R", "text": b"T", "blob": b"B"}
    encoded = []
    for kind, value in values:
        raw = archive_bytes(kind, value)
        encoded.append(tags[kind] + len(raw).to_bytes(8, "big") + raw)
    return b"".join(encoded)


def row_digest(values):
    """Schema column-order (name, typeof, value); name length/name + tagged value."""
    material = []
    for name, kind, value in values:
        raw_name = name.encode("utf-8")
        material.append(
            len(raw_name).to_bytes(8, "big") + raw_name + tagged_key([(kind, value)])
        )
    return hashlib.sha256(b"".join(material)).digest()


def validate(contract=None, schema=None):
    c = contract or json.loads((ROOT / "conversion-contract.json").read_text())
    db = construct(schema)
    target = inventory(db)
    if not {"legacy_records", "legacy_values"} <= set(target):
        raise ValueError("Nonexistent typed archive")
    if not {"record_id", "column_name", "storage_type", "value_bytes"} <= {
        x["name"] for x in target["legacy_values"]
    }:
        raise ValueError("Nonexistent archive column")
    source = json.loads((ROOT / "current-schema.json").read_text())
    old = {(t["name"], col["name"]) for t in source["tables"] for col in t["columns"]}
    actual = [(r["table"], r["column"]) for r in c["source_columns"]]
    if len(actual) != len(set(actual)) or set(actual) != old:
        raise ValueError("Unmapped or duplicate source column")
    if (
        c["ddl_sha256"]
        != hashlib.sha256(
            (schema or (ROOT / "target-schema.sql").read_text()).encode()
        ).hexdigest()
    ):
        raise ValueError("DDL hash mismatch")
    if c["source_schema_sha256"] != source["schema_sha256"]:
        raise ValueError("Source fingerprint mismatch")
    contexts = c["contexts"]
    producers = {p["id"]: p for p in c["productions"]}
    if len(producers) != len(c["productions"]):
        raise ValueError("Duplicate production")
    coverage = set()
    for p in producers.values():
        if p["target"] not in target:
            raise ValueError("Nonexistent target table")
        columns = {x["name"]: x for x in target[p["target"]]}
        if set(p["outputs"]) != set(columns):
            raise ValueError("Target reverse coverage missing")
        if p["cardinality"] not in ("one", "many", "merge", "zero_until_runtime"):
            raise ValueError("Invalid cardinality")
        for dep in p["dependencies"]:
            if dep not in producers:
                raise ValueError("Undefined dependency")
        if not p.get("recipe") and not p.get("factory"):
            raise ValueError("Undefined producer recipe/factory")
        for column, expression in p["outputs"].items():
            if expression.get("type") != columns[column]["type"]:
                raise ValueError("Output type mismatch")
            rule = c["rules"].get(expression["rule"])
            signature = SIGNATURES.get(expression["rule"])
            if (
                not rule
                or not signature
                or rule["implementation"] not in ("scalar", "recipe", "caller")
            ):
                raise ValueError("Undefined transform rule")
            if rule["arity"] != signature[0] or (
                signature[1] and signature[1] != expression["type"]
            ):
                raise ValueError("Transform signature mismatch")
            refs = expression["inputs"]
            if len(refs) != rule["arity"]:
                raise ValueError("Rule arity mismatch")
            for ref in refs:
                if ref.startswith("source."):
                    table, col = ref.removeprefix("source.").split(".")
                    if (table, col) not in old:
                        raise ValueError("Nonexistent source input")
                    if table not in p["source_tables"]:
                        raise ValueError("Undeclared source dependency")
                elif ref not in contexts:
                    raise ValueError("Undefined context input")
                elif (
                    expression["rule"] == "caller"
                    and contexts[ref]["type"] != expression["type"]
                ):
                    raise ValueError("Context type mismatch")
            if expression["rule"] == "null" and (
                columns[column]["notnull"] or columns[column]["pk"]
            ):
                raise ValueError("Required target column has no provider")
            if expression["rule"] == "constant":
                value = expression["value"]
                kind = columns[column]["type"]
                if value is None and (
                    columns[column]["notnull"] or columns[column]["pk"]
                ):
                    raise ValueError("Required constant is NULL")
                if value is not None and not isinstance(
                    value,
                    {"TEXT": str, "INTEGER": int, "REAL": (int, float), "BLOB": bytes}[
                        kind
                    ],
                ):
                    raise ValueError("Constant type mismatch")
            if expression["rule"] == "copy" and refs[0].startswith("source."):
                table, col = refs[0].split(".")[1:]
                old_type = next(
                    x["type"]
                    for t in source["tables"]
                    if t["name"] == table
                    for x in t["columns"]
                    if x["name"] == col
                )
                if old_type != columns[column]["type"]:
                    raise ValueError("Copy storage type mismatch")
            coverage.add((p["target"], column))
    if coverage != {(t, x["name"]) for t, cols in target.items() for x in cols}:
        raise ValueError("Target table without producer")
    for r in c["source_columns"]:
        for recipe in r.get("dependent_recipes", []):
            if recipe not in producers or r["table"] not in producers[recipe].get(
                "recipe", {}
            ).get("input_tables", []):
                raise ValueError("Undefined reanalysis dependency")
        a = r["archive"]
        if a != {
            "table": "legacy_values",
            "value_column": "value_bytes",
            "type_column": "storage_type",
            "record_table": "legacy_records",
            "key_columns": ["source_id", "source_table", "source_key"],
            "column_key": r["column"],
            "rule": "sqlite_exact_bytes",
        }:
            raise ValueError("Undefined archive location or encoding")
        if r["failure"] not in ("blocking", "partial", "archive_only"):
            raise ValueError("Undefined failure classification")
        if not r["validation"] or any(
            v not in c["validations"] for v in r["validation"]
        ):
            raise ValueError("Undefined validation")
        if r["relation"] not in ("identity", "split", "merge", "derived", "archive"):
            raise ValueError("Invalid relation")
        for output in r["outputs"]:
            p = producers.get(output["production"])
            if not p or output["column"] not in p["outputs"]:
                raise ValueError("Nonexistent migration destination")
            expression = p["outputs"][output["column"]]
            if f"source.{r['table']}.{r['column']}" not in expression["inputs"]:
                raise ValueError("Unconnected source destination")

    # Non-deferred dependencies must form an executable construction order.
    def visit(name, path):
        if name in path:
            raise ValueError("Non-deferred dependency cycle")
        for dep in producers[name]["dependencies"]:
            visit(dep, path | {name})

    for name in producers:
        visit(name, set())
    db.close()
    return c, target


def render_rows(contract):
    records = []
    for r in contract["source_columns"]:
        outputs = [f"{p['production']}.{p['column']}" for p in r["outputs"]]
        records.append(
            {
                "source_table": r["table"],
                "source_column": r["column"],
                "target": " | ".join(outputs + ["legacy_values.value_bytes"]),
                "relation": r["relation"],
                "dependent_recipes": " | ".join(r.get("dependent_recipes", [])),
                "transform_rules": " | ".join(
                    sorted(
                        {
                            next(
                                p
                                for p in contract["productions"]
                                if p["id"] == o["production"]
                            )["outputs"][o["column"]]["rule"]
                            for o in r["outputs"]
                        }
                        | {"sqlite_exact_bytes"}
                    )
                ),
                "failure_policy": r["failure"],
                "validation": " | ".join(r["validation"]),
            }
        )
    return records


def generate():
    contract, target = validate()
    records = render_rows(contract)
    with (ROOT / "column-conversion.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(records[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(records)
    lines = [
        "# v2テーブル変換対応（機械契約から生成）",
        "",
        "正本: conversion-contract.json。全旧値はlegacy_records/legacy_valuesにも型・key・exact bytes付きで保持する。converterは未実装。",
        "",
        "| v2 table | target producers | archive-only columns |",
        "|---|---|---|",
    ]
    for table in sorted({r["table"] for r in contract["source_columns"]}):
        rows = [r for r in contract["source_columns"] if r["table"] == table]
        producers = sorted({o["production"] for r in rows for o in r["outputs"]})
        lines.append(
            f"| {table} | {', '.join(producers) or 'legacy_records / legacy_values'} | {', '.join(r['column'] for r in rows if not r['outputs']) or 'none'} |"
        )
    (ROOT / "table-conversion.md").write_text("\n".join(lines) + "\n")
    (ROOT / "target-inventory.json").write_text(
        json.dumps({"ddl_sha256": contract["ddl_sha256"], "tables": target}, indent=2)
        + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    if args.generate:
        generate()
    contract, target = validate()
    print(
        f"Validated {len(contract['source_columns'])} source columns and {len(target)} target tables"
    )
