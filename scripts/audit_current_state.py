"""Compare fresh production schemas without touching a retained catalog.

The baseline composer/resources are read through git show. This receipt lists
every named object and physical column, and reports FK changes by meaning rather
than SQLite's renumbered declaration IDs. Use an explicit --output path.
"""

import argparse
import hashlib
import json
import platform
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import guard_sql, inventory
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, SCHEMA_VERSION, schema_sql

BASELINE = "3f76d4873d14604b918198ac06c1660d0fa9e1b9"
CURRENT_TABLES = ("issue_resources", "review_resources")


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(ddl, *, include_wire_columns=False):
    with sqlite3.connect(":memory:", isolation_level=None) as db:
        db.executescript(ddl)
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
        rows = db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )
        objects = {kind: {} for kind in ("table", "view", "trigger", "index")}
        for kind, name, table, sql in rows:
            objects[kind][name] = {"table": table, "sql_sha256": digest(sql.encode())}
        columns, native_fks = {}, {}
        for name in objects["table"]:
            columns[name] = [
                dict(
                    zip(
                        ("cid", "name", "type", "not_null", "default", "pk", "hidden"),
                        row,
                        strict=True,
                    )
                )
                for row in db.execute(f"PRAGMA table_xinfo({quote(name)})")
            ]
            grouped = {}
            for row in db.execute(f"PRAGMA foreign_key_list({quote(name)})"):
                identity, _, parent, child, target, update, delete, match = row
                fk = grouped.setdefault(
                    identity,
                    {
                        "parent": parent,
                        "columns": [],
                        "targets": [],
                        "on_update": update,
                        "on_delete": delete,
                        "match": match,
                    },
                )
                fk["columns"].append(child)
                fk["targets"].append(target)
            native_fks[name] = sorted(
                grouped.values(), key=lambda fk: json.dumps(fk, sort_keys=True)
            )
        foreign = db.execute("PRAGMA foreign_key_check").fetchall()
        integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
        assert not foreign and integrity == ["ok"]
        return {
            "ddl_sha256": digest(ddl.encode()),
            "object_counts": {kind: len(names) for kind, names in objects.items()},
            "objects": objects,
            "table_columns": columns,
            "native_foreign_keys": native_fks,
            "text_body_fk_owners": {
                table: [fk for fk in fks if fk["parent"] == "text_bodies"]
                for table, fks in native_fks.items()
                if any(fk["parent"] == "text_bodies" for fk in fks)
            },
            "foreign_key_check": foreign,
            "integrity_check": integrity,
            "current_wire_columns": {
                table: sorted(Graph(db).expected_columns(table))
                for table in CURRENT_TABLES
            }
            if include_wire_columns
            else {},
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def git_show(path):
        return subprocess.check_output(
            ["git", "show", f"{args.baseline}:{path}"], text=True
        )

    composer = git_show("src/repo_catalog/adapters/sqlite/schema.py")
    resources = re.findall(r'"([a-z_0-9]+\.sql)"', composer)
    before = inspect(
        "\n".join(git_show(f"src/repo_catalog/resources/{name}") for name in resources)
    )
    before["schema_version"] = int(re.search(r"SCHEMA_VERSION = (\d+)", composer)[1])
    after = inspect(schema_sql(), include_wire_columns=True)
    after["schema_version"] = SCHEMA_VERSION
    assert after["ddl_sha256"] == DDL_SHA256.hex()
    object_changes = {}
    for kind, old in before["objects"].items():
        new = after["objects"][kind]
        object_changes[kind] = {
            "added": sorted(new.keys() - old.keys()),
            "removed": sorted(old.keys() - new.keys()),
            "modified": sorted(
                name for name in new.keys() & old.keys() if new[name] != old[name]
            ),
        }

    def semantic_columns(columns):
        return {
            name: {key: value for key, value in column.items() if key != "cid"}
            for name, column in ((item["name"], item) for item in columns or [])
        }

    column_changes = {
        table: {
            "before": semantic_columns(before["table_columns"].get(table)),
            "after": semantic_columns(after["table_columns"].get(table)),
        }
        for table in before["table_columns"].keys() | after["table_columns"].keys()
        if semantic_columns(before["table_columns"].get(table))
        != semantic_columns(after["table_columns"].get(table))
    }
    removed_fks, added_fks = {}, {}
    for table in CURRENT_TABLES:
        old, new = (
            before["native_foreign_keys"][table],
            after["native_foreign_keys"][table],
        )
        removed_fks[table] = [fk for fk in old if fk not in new]
        added_fks[table] = [fk for fk in new if fk not in old]
        expected_removed_parents = {
            "parser_profile_capabilities",
            "parser_profiles",
            "repository_bindings",
        }
        assert {fk["parent"] for fk in removed_fks[table]} == expected_removed_parents
        assert not added_fks[table]
        assert any(
            fk["parent"] == "repository_bindings"
            and fk["columns"] == ["repository_binding_id", "repository_uuidv4"]
            for fk in new
        )
        assert "last_checked_at_us" not in after["current_wire_columns"][table]
    expected_column_names = {
        "current_collection_pages": {
            "removed": {"parser_profile_uuidv4"},
            "added": {"parser_module", "parser_version"},
        },
        "issue_resources": {
            "removed": {"fact_kind", "owner_kind", "parser_profile_uuidv4"},
            "added": {"parser_module", "parser_version"},
        },
        "review_resources": {
            "removed": {"owner_kind", "parser_profile_uuidv4"},
            "added": {"parser_module", "parser_version"},
        },
    }
    assert {
        table: {
            "removed": {
                column["name"] for column in before["table_columns"].get(table, [])
            }
            - {column["name"] for column in after["table_columns"].get(table, [])},
            "added": {
                column["name"] for column in after["table_columns"].get(table, [])
            }
            - {column["name"] for column in before["table_columns"].get(table, [])},
        }
        for table in expected_column_names
    } == expected_column_names
    with sqlite3.connect(":memory:", isolation_level=None) as db:
        db.executescript(schema_sql())
        registry = inventory(db)
    generated = guard_sql().encode()
    packaged = Path("src/repo_catalog/resources/json_contracts.sql").read_bytes()
    assert generated == packaged
    report = {
        "baseline_commit": args.baseline,
        "observed_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
        },
        "composition": resources,
        "baseline": before,
        "current": after,
        "object_changes": object_changes,
        "column_changes": column_changes,
        "removed_native_foreign_keys": removed_fks,
        "added_native_foreign_keys": added_fks,
        "json_inventory": registry,
        "generated_json_guard_sha256": digest(generated),
        "packaged_json_guard_sha256": digest(packaged),
        "command": f"uv run --no-sync python scripts/audit_current_state.py --output {args.output}",
        "script_sha256": digest(Path(__file__).read_bytes()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "baseline_schema": before["schema_version"],
                "current_schema": SCHEMA_VERSION,
                "ddl_sha256": after["ddl_sha256"],
                "counts": after["object_counts"],
                "removed_fks": removed_fks,
                "column_changes": column_changes,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
