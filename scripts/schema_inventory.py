"""Mechanical implemented-store schema inventory, independent of renderers.

Preserves the complete DDL-derived IR for the current separated schemas.
No documentation package is imported and no persistent database is opened.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Ensure all namespace distribution source roots are importable
ROOT = Path(__file__).resolve().parents[1]
for source in (
    ROOT / "src",
    ROOT / "packages/repository/src",
    ROOT / "packages/contracts/src",
    ROOT / "packages/runtime/src",
    ROOT / "packages/context/src",
    ROOT / "packages/access/src",
    ROOT / "packages/paired-query/src",
    ROOT / "packages/search/src",
    ROOT / "packages/operational/src",
    ROOT / "packages/git-acquisition/src",
    ROOT / "packages/exchange/src",
    ROOT / "packages/paired-recovery/src",
    ROOT / "packages/filesystem/src",
    ROOT / "packages/worktrees/src",
):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def introspect_store(
    store_slug: str,
    store_title: str,
    db_filename: str,
    format_id: str | None,
    schema_version: int | None,
    expected_sha256: bytes,
    ddl: str,
    group_map: dict[str, list[str]],
    *,
    prepare: Callable[[sqlite3.Connection], None] | None = None,
    include_runtime_details: bool = False,
) -> dict[str, Any]:
    """Introspect a single SQLite schema entirely in memory."""
    ddl_sha256 = hashlib.sha256(ddl.encode()).digest()
    if ddl_sha256 != expected_sha256:
        raise ValueError(
            f"DDL hash mismatch for {store_slug}: computed {ddl_sha256.hex()}, declared {expected_sha256.hex()}"
        )
    db = sqlite3.connect(":memory:")
    try:
        db.execute("PRAGMA foreign_keys=ON")
        if prepare is not None:
            prepare(db)
        db.executescript(ddl)
        result = _read_store_schema(
            db,
            store_slug,
            store_title,
            db_filename,
            format_id,
            schema_version,
            ddl_sha256,
            group_map,
        )
        if include_runtime_details:
            result["extracted_objects"] = [
                {"type": kind, "name": name}
                for kind, name in db.execute(
                    "SELECT type,name FROM sqlite_schema WHERE sql IS NOT NULL "
                    "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'catalog_fts_%' ORDER BY type,name"
                )
            ]
            result["extraction_connection"] = {
                "pragmas": {
                    name: db.execute(f"PRAGMA {name}").fetchone()[0]
                    for name in (
                        "foreign_keys",
                        "recursive_triggers",
                        "trusted_schema",
                        "ignore_check_constraints",
                        "defer_foreign_keys",
                    )
                },
                "registered_functions": sorted(
                    (
                        {"name": row[0], "arity": row[4], "flags": row[5]}
                        for row in db.execute("PRAGMA function_list")
                        if row[1] == 0
                    ),
                    key=lambda row: (row["name"], row["arity"]),
                ),
            }
            for _, name, kind, ncol, without_rowid, strict in db.execute(
                "PRAGMA table_list"
            ):
                if name in result["tables"]:
                    result["tables"][name].update(
                        is_strict=bool(strict),
                        without_rowid=bool(without_rowid),
                        sqlite_table_type=kind,
                        column_count=ncol,
                    )
        return result
    finally:
        db.close()


def _read_store_schema(
    db,
    store_slug,
    store_title,
    db_filename,
    format_id,
    schema_version,
    ddl_sha256,
    group_map,
) -> dict[str, Any]:

    # Invert group map: table_name -> group_slug
    table_to_group: dict[str, str] = {}
    for group_slug, tables in group_map.items():
        for table in tables:
            table_to_group[table] = group_slug

    raw_objects = db.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_schema "
        "WHERE name NOT LIKE 'sqlite_%' AND name NOT LIKE 'catalog_fts_%' "
        "ORDER BY type, name"
    ).fetchall()

    tables: dict[str, Any] = {}
    views: dict[str, Any] = {}
    triggers: dict[str, Any] = {}
    explicit_indexes: dict[str, Any] = {}

    for obj_type, name, tbl_name, sql in raw_objects:
        if obj_type == "view":
            view_cols = [
                c[1] for c in db.execute(f'PRAGMA table_xinfo("{name}")').fetchall()
            ]
            views[name] = {
                "name": name,
                "sql": sql,
                "columns": view_cols,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            }
        elif obj_type == "trigger":
            triggers[name] = {
                "name": name,
                "table_name": tbl_name,
                "sql": sql,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            }
        elif obj_type == "index":
            explicit_indexes[name] = {
                "name": name,
                "table_name": tbl_name,
                "sql": sql,
                "sql_sha256": hashlib.sha256(sql.encode()).hexdigest() if sql else None,
            }

    # Introspect each table
    table_names = [
        row[1]
        for row in raw_objects
        if row[0] == "table"
        and not row[1].startswith("sqlite_")
        and not row[1].startswith("catalog_fts_")
    ]

    for t_name in sorted(table_names):
        t_sql = next((r[3] for r in raw_objects if r[1] == t_name), "")
        raw_cols = db.execute(f'PRAGMA table_xinfo("{t_name}")').fetchall()
        # raw_cols: cid, name, type, notnull, dflt_value, pk, hidden
        columns: list[dict[str, Any]] = []
        pk_cols: list[str] = []

        # Sort columns to find PK order
        pk_candidates = [
            (c[1], c[5]) for c in raw_cols if c[5] > 0
        ]  # c[5] is 1-based rank
        pk_cols = [c[0] for c in sorted(pk_candidates, key=lambda x: x[1])]

        for cid, col_name, col_type, notnull, dflt, pk_pos, hidden in raw_cols:
            is_generated = hidden in (2, 3)
            # In SQLite 3.31+ PRAGMA table_xinfo: hidden==2 is VIRTUAL, hidden==3 is STORED
            gen_type = "VIRTUAL" if hidden == 2 else "STORED" if hidden == 3 else None
            columns.append(
                {
                    "cid": cid,
                    "name": col_name,
                    "type": col_type,
                    "notnull": bool(notnull),
                    "default_value": dflt,
                    "is_pk": pk_pos > 0,
                    "pk_position": pk_pos,
                    "is_generated": is_generated,
                    "generation_type": gen_type,
                    "is_hidden": hidden == 1,
                }
            )

        # Foreign keys: PRAGMA foreign_key_list(t_name)
        # rows: id, seq, table, from, to, on_update, on_delete, match
        fk_rows = db.execute(f'PRAGMA foreign_key_list("{t_name}")').fetchall()
        fk_groups: dict[int, list[Any]] = {}
        for row in fk_rows:
            fk_groups.setdefault(row[0], []).append(row)

        foreign_keys: list[dict[str, Any]] = []
        for fk_id in sorted(fk_groups.keys()):
            rows = sorted(fk_groups[fk_id], key=lambda r: r[1])  # sort by seq
            target_table = rows[0][2]
            from_cols = [r[3] for r in rows]
            to_cols = [r[4] for r in rows]
            on_update = rows[0][5]
            on_delete = rows[0][6]
            foreign_keys.append(
                {
                    "id": fk_id,
                    "target_table": target_table,
                    "from_columns": from_cols,
                    "to_columns": to_cols,
                    "is_composite": len(from_cols) > 1,
                    "on_update": on_update,
                    "on_delete": on_delete,
                    "match": rows[0][7],
                }
            )

        # Unique constraints and indexes
        idx_list = db.execute(f'PRAGMA index_list("{t_name}")').fetchall()
        # idx_list: seq, name, unique, origin, partial
        unique_constraints: list[dict[str, Any]] = []
        table_indexes: list[dict[str, Any]] = []

        for _, idx_name, is_unique, origin, is_partial in idx_list:
            xinfo = db.execute(f'PRAGMA index_xinfo("{idx_name}")').fetchall()
            # xinfo: seqno, cid, name, desc, coll, key
            idx_cols = [row[2] for row in xinfo if row[1] >= 0 and row[5] == 1]

            idx_sql_row = db.execute(
                "SELECT sql FROM sqlite_schema WHERE type='index' AND name=?",
                (idx_name,),
            ).fetchone()
            idx_sql = idx_sql_row[0] if idx_sql_row else None
            where_clause = None
            if is_partial and idx_sql:
                m = re.search(r"\bWHERE\s+(.+)$", idx_sql, re.IGNORECASE)
                if m:
                    where_clause = m.group(1).strip()

            # origin 'pk' is the primary key autoindex, handled by primary_key metadata.
            # Only unconditional unique constraints are added to unique_constraints (C3).
            if is_unique and origin != "pk" and not is_partial:
                unique_constraints.append(
                    {
                        "name": idx_name,
                        "columns": idx_cols,
                        "is_composite": len(idx_cols) > 1,
                        "origin": origin,
                        "partial": False,
                        "predicate": None,
                    }
                )

            # Explicit indexes (origin 'c')
            if origin == "c":
                table_indexes.append(
                    {
                        "name": idx_name,
                        "columns": idx_cols,
                        "unique": bool(is_unique),
                        "partial": bool(is_partial),
                        "predicate": where_clause,
                        "sql": idx_sql,
                    }
                )

        # Table triggers
        table_triggers = [
            trig_name
            for trig_name, trig_data in triggers.items()
            if trig_data["table_name"] == t_name
        ]

        group = table_to_group.get(t_name, "unclassified")
        tables[t_name] = {
            "name": t_name,
            "store": store_slug,
            "group": group,
            "group_title": group.replace("_", " ").title(),
            "is_strict": "STRICT" in t_sql.upper(),
            "columns": columns,
            "primary_key": pk_cols,
            "is_composite_pk": len(pk_cols) > 1,
            "foreign_keys": foreign_keys,
            "unique_constraints": unique_constraints,
            "indexes": table_indexes,
            "triggers": table_triggers,
            "sql": t_sql,
            "sql_sha256": hashlib.sha256(t_sql.encode()).hexdigest(),
        }

    # Compute incoming foreign keys for each table
    for t_name, t_meta in tables.items():
        t_meta["incoming_foreign_keys"] = []

    for src_name, src_meta in tables.items():
        for fk in src_meta["foreign_keys"]:
            tgt_name = fk["target_table"]
            if tgt_name in tables:
                tables[tgt_name]["incoming_foreign_keys"].append(
                    {
                        "source_table": src_name,
                        "source_columns": fk["from_columns"],
                        "target_columns": fk["to_columns"],
                        "is_composite": fk["is_composite"],
                        "on_update": fk["on_update"],
                        "on_delete": fk["on_delete"],
                        "constraint_id": fk["id"],
                    }
                )

    total_fks = sum(len(t["foreign_keys"]) for t in tables.values())
    return {
        "slug": store_slug,
        "title": store_title,
        "db_filename": db_filename,
        "format_id": format_id,
        "schema_version": schema_version,
        "ddl_sha256": ddl_sha256.hex(),
        "table_count": len(tables),
        "view_count": len(views),
        "trigger_count": len(triggers),
        "index_count": len(explicit_indexes),
        "foreign_key_count": total_fks,
        "tables": tables,
        "views": views,
        "triggers": triggers,
        "explicit_indexes": explicit_indexes,
    }


def introspect_all(
    profile: str = "all", *, include_runtime_details: bool = False
) -> dict[str, Any]:
    """Extract every current role, without opening any retained instance.

    The registry is a catalog of definitions, never a startup prescription.
    Connection details are included for every role; the keyword is retained for
    callers that explicitly request those observed extraction settings.
    """
    if profile != "all":
        raise ValueError("Unknown inventory profile: " + profile)
    from scripts.schema_catalog import build_catalog

    return build_catalog()


def validate_logical_dependencies(ir: dict[str, Any]) -> list[str]:
    """Validate cross-store logical dependencies against introspected schemas."""
    errors = []
    stores = ir["stores"]
    for dep in ir.get("logical_dependencies", []):
        dep_id = dep["id"]
        src_store_slug = dep["source_store"]
        tgt_store_slug = dep["target_store"]
        if src_store_slug not in stores:
            errors.append(f"{dep_id}: unknown source store '{src_store_slug}'")
            continue
        if tgt_store_slug not in stores:
            errors.append(f"{dep_id}: unknown target store '{tgt_store_slug}'")
            continue

        src_store = stores[src_store_slug]
        tgt_store = stores[tgt_store_slug]
        src_table_name = dep["source_table"]
        tgt_table_name = dep["target_table"]

        if src_table_name not in src_store["tables"]:
            errors.append(
                f"{dep_id}: source table '{src_table_name}' not found in {src_store_slug}"
            )
            continue
        if tgt_table_name not in tgt_store["tables"]:
            errors.append(
                f"{dep_id}: target table '{tgt_table_name}' not found in {tgt_store_slug}"
            )
            continue

        src_table = src_store["tables"][src_table_name]
        tgt_table = tgt_store["tables"][tgt_table_name]
        src_col_names = {c["name"] for c in src_table["columns"]}
        tgt_col_names = {c["name"] for c in tgt_table["columns"]}

        for col in dep.get("source_columns", []):
            if col not in src_col_names:
                errors.append(
                    f"{dep_id}: source column '{col}' not found in {src_table_name}"
                )

        for col in dep.get("target_columns", []):
            if col not in tgt_col_names:
                errors.append(
                    f"{dep_id}: target column '{col}' not found in {tgt_table_name}"
                )

    return errors


PRODUCER_CONTROLS = frozenset(
    {
        "scripts/schema_inventory.py",
        "scripts/schema_catalog.py",
        "scripts/verification_outputs.py",
        "pyproject.toml",
        "uv.lock",
    }
)


def producer_input_names(root: Path, source: str) -> list[str]:
    """Conservative committed product/control closure, shared with reconciliation."""
    import subprocess

    names = (
        subprocess.check_output(
            ["git", "-C", str(root), "ls-tree", "-rz", "--name-only", source]
        )
        .decode()
        .split("\0")
    )
    selected = {
        p
        for p in names
        if p.startswith(("src/", "packages/"))
        or p.startswith("scripts/")
        and p.endswith(".py")
        or p in PRODUCER_CONTROLS
    }
    if not PRODUCER_CONTROLS.issubset(selected):
        raise ValueError("Required producer control inputs missing")
    return sorted(selected)


def verify_producer_bytes(root: Path, source: str, inputs: list[str]) -> dict[str, str]:
    import subprocess

    result = {}
    for name in inputs:
        path = root / name
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Linked producer input refused: " + name)
        committed = subprocess.check_output(
            ["git", "-C", str(root), "show", source + ":" + name]
        )
        if path.read_bytes() != committed:
            raise ValueError("Producer input differs from selected source: " + name)
        result[name] = hashlib.sha256(committed).hexdigest()
    return result


def executed_producer_inputs(root: Path, inputs: list[str]) -> list[str]:
    """Unknown repository-local executable inputs fail before publication."""
    executed = set()
    root = root.resolve()
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.is_relative_to(root) and not path.is_relative_to(root / ".venv"):
            relative = path.relative_to(root).as_posix()
            if relative not in inputs:
                raise ValueError(
                    "Executed producer input outside bound inventory: " + relative
                )
            executed.add(relative)
        elif name == "repo_catalog" or name.startswith(("repo_catalog.", "scripts.")):
            raise ValueError(
                "Producer module loaded outside selected checkout: " + name
            )
    return sorted(executed)


def validate_inventory(inventory: dict[str, Any], profile: str = "all") -> list[str]:
    if profile != "all":
        return ["Unknown inventory profile: " + profile]
    from scripts.schema_catalog import validate_catalog

    return validate_catalog(inventory)


def export_inventory(output: Path, source: str, profile: str = "all") -> dict[str, Any]:
    """Export complete IR from this exact committed producer checkout."""
    import json
    import os
    import platform
    import subprocess

    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(ROOT), *args])

    from scripts.verification_outputs import (
        private_path,
        write_private,
        write_private_json,
    )

    output = Path(os.path.abspath(output))
    allowed = ROOT / "website/.build/inputs"
    if output != allowed and allowed not in output.parents:
        raise ValueError("Producer output must remain in website/.build/inputs")
    # Preflight both sinks before reading/executing inputs or publishing either.
    inventory_path = private_path(ROOT, output / "inventory.json")
    manifest_path = private_path(ROOT, output / "producer.json")
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("Explicit full product source SHA required")
    if git("rev-parse", "HEAD").decode().strip() != source:
        raise ValueError("Producer must execute the selected product checkout")
    inputs = producer_input_names(ROOT, source)
    hashes = verify_producer_bytes(ROOT, source, inputs)
    inventory = introspect_all(profile)
    errors = validate_inventory(inventory, profile)
    if errors:
        raise ValueError("Invalid neutral inventory: " + "; ".join(errors))
    executed = executed_producer_inputs(ROOT, inputs)
    # Control imports and validators can mutate files; recheck after execution.
    if verify_producer_bytes(ROOT, source, inputs) != hashes:
        raise ValueError("Producer inputs changed during execution")
    raw = (json.dumps(inventory, separators=(",", ":")) + "\n").encode()
    manifest = {
        "schema_version": 1,
        "product_source": {
            "commit": source,
            "tree": git("rev-parse", source + "^{tree}").decode().strip(),
        },
        "ir_sha256": hashlib.sha256(raw).hexdigest(),
        "input_sha256": hashes,
        "executed_python_inputs": executed,
        "runtime": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
        },
    }
    manifest["inventory_profile"] = profile
    write_private(ROOT, inventory_path, raw)
    write_private_json(ROOT, manifest_path, manifest)
    return manifest


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source")
    parser.add_argument("--profile", choices=("all",), default="all")
    args = parser.parse_args()
    if args.check:
        ir = introspect_all(args.profile)
        errors = validate_inventory(ir, args.profile)
        if errors:
            parser.exit(1, "\n".join(errors) + "\n")
        print(
            f"Neutral inventory ({args.profile}): {len(ir['stores'])} schema definitions checked"
        )
    elif args.output and args.source:
        manifest = export_inventory(args.output, args.source, args.profile)
        print("Neutral IR exported: " + manifest["ir_sha256"])
    else:
        parser.error("choose --check or --output with explicit --source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
