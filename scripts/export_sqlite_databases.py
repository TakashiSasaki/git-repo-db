#!/usr/bin/env python3
"""Export pristine, authoritative SQLite databases for SchemaSpy, SQLite CLI, and GUI tools.

Instantiates empty SQLite databases containing all 84 tables, physical foreign keys,
unique constraints, and generated columns directly from authoritative Python DDL.

Usage:
    scripts/local-run.sh python scripts/export_sqlite_databases.py
    scripts/local-run.sh python scripts/export_sqlite_databases.py --output-dir .build/databases
"""

from __future__ import annotations

import argparse
import ctypes
import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from repo_catalog.adapters.sqlite.schema import (  # noqa: E402
    operational_schema_sql,
    schema_sql,
    search_schema_sql,
)


def _open_directory(path: Path) -> int:
    """Open or create parents without following symlinks (Linux)."""
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    current = Path(path.anchor)
    try:
        for part in path.parts[1:]:
            # Refuse external checkouts/environments before creating descendants.
            if current not in {
                ROOT,
                *ROOT.parents,
                Path(path.anchor),
                Path(tempfile.gettempdir()),
            } and {".git", "pyvenv.cfg", ".venv"} & set(os.listdir(fd)):
                raise ValueError("Refusing source/environment ancestor")
            try:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
            os.close(fd)
            fd = child
            current /= part
        return fd
    except BaseException:
        os.close(fd)
        raise


def _publish_exclusive(fd: int, source: str, destination: str) -> None:
    # Linux renameat2 is the only supported atomic no-replace directory publish.
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename = libc.renameat2
    except AttributeError as exc:
        raise RuntimeError(
            "Atomic no-replace directory publication unavailable"
        ) from exc
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    if rename(fd, os.fsencode(source), fd, os.fsencode(destination), 1) != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), destination)


def export_databases(output_dir: Path) -> dict[str, Path]:
    """Publish six empty schema specimens only into a new, absent directory.

    Existing destinations, symlink ancestors and specified protected paths are
    refused. The immediate parent is checked for SQLite files and sidecars;
    this does not establish that every ancestor is free of catalog state. The
    checkout's own ancestors are exempt from checkout/environment markers.
    Parents are created without following symlinks. Linux/glibc atomic
    no-replace support is required.
    """
    if sys.platform != "linux" or not hasattr(ctypes.CDLL(None), "renameat2"):
        raise RuntimeError(
            "Safe export requires Linux/glibc renameat2; no output written"
        )
    output_dir = Path(output_dir)
    if ".." in output_dir.parts:
        raise ValueError("Parent traversal is not permitted")
    target = Path(os.path.abspath(output_dir))
    allowed = ROOT / ".build" / "databases"
    if (
        target == ROOT
        or target.is_relative_to(ROOT)
        and not (target == allowed or target.is_relative_to(allowed))
    ):
        raise ValueError("Refusing repository source or protected location")
    if set(target.parts) & {
        ".git",
        ".venv",
        ".cache",
        "cache",
        "catalogs",
        "state",
        "evidence",
    }:
        raise ValueError("Refusing protected destination")
    if os.path.lexists(target):
        raise FileExistsError("Destination must not already exist: " + str(target))
    parent_fd = _open_directory(target.parent)
    stage = ".schema-export-" + secrets.token_hex(16)
    stage_path = Path(f"/proc/self/fd/{parent_fd}") / stage
    created = False
    try:
        # Do not put generated specimens inside a directory that already holds
        # catalog files or SQLite sidecars, even when the child name is new.
        for item in os.listdir(parent_fd):
            lower = item.lower()
            if lower.endswith(
                (".db", ".sqlite", ".sqlite3", "-wal", "-shm", "-journal")
            ) or item in {".git", ".venv", "pyvenv.cfg"}:
                raise ValueError(
                    "Refusing parent containing catalog or protected state"
                )
        os.mkdir(stage, mode=0o700, dir_fd=parent_fd)
        created = True
        targets = {
            "catalog": (schema_sql(), 70),
            "operational": (operational_schema_sql(), 10),
            "search": (search_schema_sql(), 4),
        }
        for stem, (ddl, expected_tables) in targets.items():
            db_path = stage_path / (stem + ".sqlite3")
            sql_path = stage_path / (stem + ".sql")
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(ddl)
                conn.commit()
                count = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchone()[0]
                if (
                    count != expected_tables
                    or conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                    or conn.execute("PRAGMA foreign_key_check").fetchall()
                ):
                    raise ValueError("Schema specimen verification failed")
            finally:
                conn.close()
            fd = os.open(
                sql_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(ddl)
        names = {stem + suffix for stem in targets for suffix in (".sqlite3", ".sql")}
        if {p.name for p in stage_path.iterdir()} != names:
            raise ValueError("Unexpected output or SQLite sidecar")
        _publish_exclusive(parent_fd, stage, target.name)
        created = False
        return {name: target / name for name in sorted(names)}
    finally:
        if created:
            shutil.rmtree(stage_path)
        os.close(parent_fd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export authoritative SQLite databases from DDL for SchemaSpy and external tools."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / ".build" / "databases",
        help="New, absent output directory; safe parents created (default: .build/databases)",
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
