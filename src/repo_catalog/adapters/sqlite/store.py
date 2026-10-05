from __future__ import annotations

import hashlib
import sqlite3
import uuid
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path

from repo_catalog.config import load
from repo_catalog.domain.models import CatalogError, now

SCHEMA_VERSION = 2


def migrations():
    resources = {}
    for resource in files("repo_catalog").joinpath("resources/migrations").iterdir():
        if not resource.name.endswith(".sql"):
            continue
        version = int(resource.name.split("_")[0])
        if version in resources:
            raise CatalogError("SCHEMA_ERROR", "Duplicate migration version")
        resources[version] = resource
    if sorted(resources) != list(range(1, SCHEMA_VERSION + 1)):
        raise CatalogError("SCHEMA_ERROR", "Migration versions must be contiguous")
    return resources


def statements(sql):
    pending = ""
    for line in sql.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip():
        raise CatalogError("SCHEMA_ERROR", "Incomplete migration SQL")


class Store:
    def __init__(self, state_dir, *, readonly=False, initialize=False, migrate=False):
        self.path = Path(state_dir)
        self.config = load(self.path)
        db = (self.path / self.config["database"]["filename"]).resolve()
        if not db.is_relative_to(self.path):
            raise CatalogError(
                "CONFIG_ERROR", "Database must remain inside state directory"
            )
        if not initialize and not db.is_file():
            raise CatalogError("NOT_INITIALIZED", "Catalog database does not exist")
        self.db_path = db
        self.readonly = readonly
        self.connection = sqlite3.connect(
            db.as_uri() + ("?mode=ro" if readonly else "?mode=rwc"),
            uri=True,
            autocommit=True,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute(
            f"PRAGMA busy_timeout={int(self.config['database']['busy_timeout_ms'])}"
        )
        if not readonly:
            mode = self.config["database"]["journal_mode"]
            v = tuple(map(int, sqlite3.sqlite_version.split(".")))
            if mode == "wal" and not (v >= (3, 51, 3) or v in ((3, 44, 6), (3, 50, 7))):
                raise CatalogError(
                    "UNSAFE_WAL_RUNTIME", "WAL requires a verified WAL-reset fix"
                )
            actual = self.connection.execute(f"PRAGMA journal_mode={mode}").fetchone()[
                0
            ]
            if actual != mode:
                raise CatalogError(
                    "DATABASE_ERROR", "Cannot apply configured journal mode"
                )
            self.connection.execute("PRAGMA synchronous=EXTRA")
        try:
            if initialize or migrate:
                self.migrate()
            elif (
                self.one("SELECT schema_version FROM catalog_meta WHERE id=1")[0]
                != SCHEMA_VERSION
            ):
                raise CatalogError(
                    "SCHEMA_ERROR",
                    "Explicit migration required; unknown schema cannot be written",
                )
            self.verify_migrations()
        except BaseException:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def execute(self, sql, args=()):
        return self.connection.execute(sql, args)

    def one(self, sql, args=()):
        return self.execute(sql, args).fetchone()

    def all(self, sql, args=()):
        return self.execute(sql, args).fetchall()

    @contextmanager
    def transaction(self, *, read=False):
        self.execute("BEGIN" if read else "BEGIN IMMEDIATE")
        try:
            yield self
            self.execute("COMMIT")
        except BaseException:
            if self.connection.in_transaction:
                self.execute("ROLLBACK")
            raise

    def publish(self):
        self.execute(
            "UPDATE catalog_meta SET publication_seq=publication_seq+1 WHERE id=1"
        )

    def revision(self):
        row = self.one(
            "SELECT db_instance_id,publication_seq FROM catalog_meta WHERE id=1"
        )
        return dict(row)

    def migrate(self):
        existing = self.one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        current = (
            self.one("SELECT max(version) FROM schema_migrations")[0] if existing else 0
        )
        if current and current > SCHEMA_VERSION:
            raise CatalogError(
                "SCHEMA_ERROR", "Database schema is newer than this package"
            )
        if existing:
            self.verify_migrations()
        for version, resource in sorted(migrations().items()):
            if version <= (current or 0):
                continue
            sql = resource.read_text()
            rebuild = version == 2
            if rebuild:
                self.execute("PRAGMA foreign_keys=OFF")
            try:
                with self.transaction():
                    for statement in statements(sql):
                        self.execute(statement)
                    if version == 2:
                        from repo_catalog.application.repository_identity import (
                            backfill_v2,
                        )

                        backfill_v2(self)
                    if not self.one("SELECT 1 FROM catalog_meta WHERE id=1"):
                        self.execute(
                            "INSERT INTO catalog_meta VALUES(1,?,0,?)",
                            (str(uuid.uuid4()), version),
                        )
                    else:
                        self.execute(
                            "UPDATE catalog_meta SET schema_version=? WHERE id=1",
                            (version,),
                        )
                        if current:
                            self.publish()
                    self.execute(
                        "INSERT INTO schema_migrations VALUES(?,?,?)",
                        (version, hashlib.sha256(sql.encode()).hexdigest(), now()),
                    )
                    if self.all("PRAGMA foreign_key_check"):
                        raise CatalogError(
                            "SCHEMA_ERROR", "Migration foreign key check failed"
                        )
            finally:
                if rebuild:
                    self.execute("PRAGMA foreign_keys=ON")

    def verify_migrations(self):
        resources = migrations()
        for r in self.all("SELECT * FROM schema_migrations"):
            resource = resources.get(r["version"])
            if (
                resource is None
                or hashlib.sha256(resource.read_bytes()).hexdigest() != r["checksum"]
            ):
                raise CatalogError("SCHEMA_ERROR", "Migration checksum mismatch")

    def coverage(self, owner, kind, state, details="{}"):
        self.execute(
            "INSERT INTO coverage_components VALUES(?,?,?,?) ON CONFLICT(owner_id,kind) DO UPDATE SET state=excluded.state,details=excluded.details",
            (owner, kind, state, details),
        )

    def object_id(self, algorithm, oid):
        row = self.one(
            "SELECT id FROM git_objects WHERE object_format=? AND oid=?",
            (algorithm, oid),
        )
        return row[0] if row else None
