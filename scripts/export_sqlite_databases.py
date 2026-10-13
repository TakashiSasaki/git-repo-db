#!/usr/bin/env python3
"""Export pristine, authoritative SQLite databases for SchemaSpy, SQLite CLI, and GUI tools.

Instantiates empty SQLite databases containing all 84 tables, physical foreign keys,
unique constraints, and generated columns directly from authoritative Python DDL.

Usage:
    uv run --no-sync python scripts/export_sqlite_databases.py
    uv run --no-sync python scripts/export_sqlite_databases.py --output-dir .build/databases
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repo_catalog.adapters.sqlite.schema import (  # noqa: E402
    operational_schema_sql,
    schema_sql,
    search_schema_sql,
)


def export_databases(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = {
        "catalog": ("Core Store (Schema 21)", schema_sql()),
        "operational": (
            "Operational Store (Schema 1)",
            operational_schema_sql(),
        ),
        "search": ("Search Store (Schema 1)", search_schema_sql()),
    }

    created_paths = {}

    for stem, (desc, ddl) in targets.items():
        db_filename = f"{stem}.sqlite3"
        sql_filename = f"{stem}.sql"
        db_path = output_dir / db_filename
        sql_path = output_dir / sql_filename

        if db_path.exists():
            db_path.unlink()

        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(ddl)
            conn.commit()
            table_count = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        finally:
            conn.close()

        sql_path.write_text(ddl, encoding="utf-8")

        created_paths[db_filename] = db_path
        created_paths[sql_filename] = sql_path
        print(
            f"  ✓ Exported {db_filename}: {desc} ({table_count} tables, {db_path.stat().st_size:,} bytes)"
        )
        print(
            f"  ✓ Exported {sql_filename}: {desc} DDL ({len(ddl.splitlines()):,} lines, {len(ddl):,} bytes)"
        )

    return created_paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export authoritative SQLite databases from DDL for SchemaSpy and external tools."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / ".build" / "databases",
        help="Directory to output SQLite database files (default: .build/databases)",
    )
    args = parser.parse_args()

    print("=================================================================")
    print(" Exporting Authoritative SQLite Databases")
    print(f" Target Directory: {args.output_dir}")
    print("=================================================================")

    export_databases(args.output_dir)

    print("=================================================================")
    print(" Export completed successfully.")
    print(" You can now run SchemaSpy against these database files.")
    print("=================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
