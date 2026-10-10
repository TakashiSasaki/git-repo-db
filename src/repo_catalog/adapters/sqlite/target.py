"""Mutation-free catalog3 diagnostic reads using normal SQLite locking."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from repo_catalog.adapters.sqlite.schema import DDL_SHA256, FORMAT_ID, SCHEMA_VERSION
from repo_catalog.domain.models import CatalogError


class TargetReader:
    """Read an existing catalog without initialization, migration or writes."""

    def __init__(self, database, *, allow_building=False):
        if not database:
            raise CatalogError(
                "INVALID_ARGUMENT", "An explicit target database is required"
            )
        self.path = Path(database).absolute()
        if self.path.is_symlink() or not self.path.is_file():
            raise CatalogError(
                "NOT_FOUND", "Target must be an existing regular database"
            )
        self.connection = sqlite3.connect(
            self.path.as_uri() + "?mode=ro", uri=True, autocommit=True
        )
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("PRAGMA recursive_triggers=ON")
            self.connection.execute("PRAGMA query_only=ON")
            for capability in ("foreign_keys", "recursive_triggers", "query_only"):
                enabled = self.connection.execute(f"PRAGMA {capability}").fetchone()
                if enabled is None or enabled[0] != 1:
                    raise CatalogError(
                        "SCHEMA_ERROR",
                        "Required target read capability is unavailable",
                        {"capability": capability},
                    )
            self.connection.execute("BEGIN")
            rows = self.connection.execute(
                "SELECT singleton,format_id,schema_version,db_instance_id,local_revision,ddl_sha256,lifecycle FROM database_identity"
            ).fetchall()
            if len(rows) != 1:
                raise CatalogError("SCHEMA_ERROR", "Invalid target database identity")
            self.identity = dict(rows[0])
            if (
                self.identity["singleton"] != 1
                or self.identity["format_id"] != FORMAT_ID
                or self.identity["schema_version"] != SCHEMA_VERSION
                or bytes(self.identity["ddl_sha256"]) != DDL_SHA256
            ):
                raise CatalogError(
                    "SCHEMA_ERROR", "Target identity or DDL does not match"
                )
            lifecycle = self.identity["lifecycle"]
            if lifecycle == "rejected" or lifecycle not in ("building", "validated"):
                raise CatalogError(
                    "TARGET_NOT_READY",
                    "Target lifecycle is not readable",
                    {"lifecycle": lifecycle},
                )
            if lifecycle == "building" and not allow_building:
                raise CatalogError(
                    "TARGET_NOT_READY",
                    "Building targets require explicit --allow-building diagnostic reads",
                    {"lifecycle": lifecycle},
                )
            self.ensure_unchanged()
        except BaseException:
            self.connection.close()
            raise

    def ensure_unchanged(self):
        # BEGIN pins the SQLite snapshot. Concurrent commits are visible only
        # to a later reader; changing files are never opened as immutable.
        return None

    def execute(self, sql, args=()):
        return self.connection.execute(sql, args)

    def one(self, sql, args=()):
        return self.execute(sql, args).fetchone()

    def all(self, sql, args=()):
        return self.execute(sql, args).fetchall()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.connection.close()
