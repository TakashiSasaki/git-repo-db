"""Strict, mutation-free access to the independent conversion destination."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from repo_catalog.domain.models import CatalogError

# Pins for the complete catalog3-p1 contract. Tests compare both with the
# authoritative DDL; installed query clients do not depend on checkout docs.
TARGET_DDL_SHA256 = "fd39297f3b73abc190aa82a28164f2d496048d773cbbcc9039a54972046a5709"
TARGET_SCHEMA_SHA256 = (
    "1ecbceb12f8fda1c944af628a8672a86f443b3b764fc8cb8c1e8e822f4699f19"
)


def schema_digest(connection):
    rows = [
        tuple(row)
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name"
        )
    ]
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class TargetReader:
    """Read a stopped, sidecar-free target without recovery or initialization."""

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
        self._check_sidecars()
        self.identity_before = self._file_identity()
        # The guarded converter's audited >=3.46.1 write/recovery floor is
        # separate. This reader only needs a STRICT-capable schema parser
        # (3.37+) and immutable read/query-only capabilities, checked below.
        if sqlite3.sqlite_version_info < (3, 37, 0):
            raise CatalogError(
                "SCHEMA_ERROR", "Immutable target reads require SQLite >= 3.37.0"
            )
        self.connection = sqlite3.connect(
            self.path.as_uri() + "?mode=ro&immutable=1", uri=True, autocommit=True
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
            if schema_digest(self.connection) != TARGET_SCHEMA_SHA256:
                raise CatalogError("SCHEMA_ERROR", "Target DDL does not match")
            rows = self.connection.execute("SELECT * FROM database_identity").fetchall()
            if len(rows) != 1:
                raise CatalogError("SCHEMA_ERROR", "Invalid target database identity")
            self.identity = dict(rows[0])
            if (
                self.identity["singleton"] != 1
                or self.identity["format_id"] != "repo-catalog/catalog3-p1"
                or self.identity["schema_version"] != 3
                or bytes(self.identity["ddl_sha256"]).hex() != TARGET_DDL_SHA256
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

    def _check_sidecars(self):
        if any(
            Path(str(self.path) + suffix).exists()
            or Path(str(self.path) + suffix).is_symlink()
            for suffix in ("-wal", "-shm", "-journal")
        ):
            raise CatalogError(
                "TARGET_BUSY",
                "Target sidecars require guarded recovery before diagnostic reads",
            )

    def _file_identity(self):
        stat = self.path.stat()
        return (
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
        )

    def ensure_unchanged(self):
        self._check_sidecars()
        if self._file_identity() != self.identity_before:
            raise CatalogError(
                "TARGET_BUSY",
                "Target changed during the read; retry after the writer stops",
            )

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
