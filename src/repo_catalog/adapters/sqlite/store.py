from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path

from repo_catalog.adapters.sqlite.coverage import admit_claim
from repo_catalog.adapters.sqlite.schema import (
    DDL_SHA256,
    FORMAT_ID,
    SCHEMA_VERSION,
    schema_sql,
)
from repo_catalog.config import load
from repo_catalog.domain.coverage import STORED_COVERAGE_STATES
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import validate_epoch_us


def statements(sql):
    pending = ""
    for line in sql.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip():
        raise CatalogError("SCHEMA_ERROR", "Incomplete schema SQL")


class Store:
    """Mutable catalog3 connection; readers use SQLite transaction snapshots."""

    def __init__(
        self,
        state_dir,
        *,
        readonly=False,
        initialize=False,
        migrate=False,
        allow_building=False,
    ):
        self.path = Path(state_dir).resolve()
        self.config = load(self.path)
        db = (self.path / self.config["database"]["filename"]).resolve()
        if not db.is_relative_to(self.path):
            raise CatalogError(
                "CONFIG_ERROR", "Database must remain inside state directory"
            )
        if not initialize and not db.is_file():
            raise CatalogError("NOT_INITIALIZED", "Catalog database does not exist")
        self.db_path, self.readonly = db, readonly
        self.connection = sqlite3.connect(
            db.as_uri() + ("?mode=ro" if readonly else "?mode=rwc"),
            uri=True,
            autocommit=True,
        )
        self.connection.row_factory = sqlite3.Row
        try:
            self.execute("PRAGMA foreign_keys=ON")
            self.execute("PRAGMA recursive_triggers=ON")
            self.execute(
                f"PRAGMA busy_timeout={int(self.config['database']['busy_timeout_ms'])}"
            )
            for capability in ("foreign_keys", "recursive_triggers"):
                if self.one(f"PRAGMA {capability}")[0] != 1:
                    raise CatalogError(
                        "RUNTIME_UNSUPPORTED", f"SQLite lacks {capability}"
                    )
            # Reject an existing foreign/building catalog before any persistent
            # journal setting can alter bytes belonging to another format.
            if not initialize:
                self.verify_format(allow_building=allow_building)
            if initialize and self.one(
                "SELECT 1 FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
            ):
                raise CatalogError(
                    "SCHEMA_ERROR", "Initialization requires an empty database"
                )
            if readonly:
                self.execute("PRAGMA query_only=ON")
            else:
                mode = self.config["database"]["journal_mode"]
                version = sqlite3.sqlite_version_info
                if mode == "wal" and not (
                    version >= (3, 51, 3) or version in ((3, 44, 6), (3, 50, 7))
                ):
                    raise CatalogError(
                        "UNSAFE_WAL_RUNTIME", "WAL requires a verified WAL-reset fix"
                    )
                if self.one(f"PRAGMA journal_mode={mode}")[0] != mode:
                    raise CatalogError(
                        "DATABASE_ERROR", "Cannot apply configured journal mode"
                    )
                self.execute("PRAGMA synchronous=EXTRA")
            if initialize:
                if self.one(
                    "SELECT 1 FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
                ):
                    raise CatalogError(
                        "SCHEMA_ERROR", "Initialization requires an empty database"
                    )
                with self.transaction():
                    for statement in statements(schema_sql()):
                        self.execute(statement)
                    self.execute(
                        "INSERT INTO database_identity(singleton,format_id,schema_version,db_instance_id,publication_seq,ddl_sha256,lifecycle) VALUES(1,?,?,?,0,?,'validated')",
                        (FORMAT_ID, SCHEMA_VERSION, str(uuid.uuid4()), DDL_SHA256),
                    )
            self.verify_format(allow_building=allow_building)
        except sqlite3.Error as cause:
            self.connection.close()
            raise CatalogError(
                "SCHEMA_ERROR",
                "Current catalog format is required; initialize a new state directory",
            ) from cause
        except BaseException:
            self.connection.close()
            raise

    def verify_format(self, *, allow_building=False):
        rows = self.all(
            "SELECT singleton,format_id,schema_version,db_instance_id,publication_seq,ddl_sha256,lifecycle FROM database_identity"
        )
        if len(rows) != 1 or rows[0]["singleton"] != 1:
            raise CatalogError("SCHEMA_ERROR", "Invalid catalog identity")
        row = rows[0]
        if (
            row["format_id"] != FORMAT_ID
            or row["schema_version"] != SCHEMA_VERSION
            or bytes(row["ddl_sha256"]) != DDL_SHA256
        ):
            raise CatalogError(
                "SCHEMA_ERROR",
                "Unsupported catalog format; initialize a new catalog",
            )
        # Derived FTS/statistics do not affect identity. Structural verification is
        # explicit doctor/db-check work, not a full schema/archive audit per query.
        if row["lifecycle"] != "validated" and not (
            allow_building and row["lifecycle"] == "building"
        ):
            raise CatalogError(
                "TARGET_NOT_READY",
                "Catalog publication is incomplete",
                {"lifecycle": row["lifecycle"]},
            )

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
            "UPDATE database_identity SET publication_seq=publication_seq+1 WHERE singleton=1"
        )

    def revision(self):
        return dict(
            self.one(
                "SELECT db_instance_id,publication_seq FROM database_identity WHERE singleton=1"
            )
        )

    def migrate(self):
        raise CatalogError(
            "SCHEMA_ERROR",
            "Catalogs initialize directly; schema migration is not supported",
        )

    def coverage(
        self,
        repository_uuidv4,
        kind,
        coverage_state,
        details_json=None,
        *,
        change_request_id=None,
        observed_at_us,
    ):
        """Admit a claim for an explicit observation; never invent replay time.

        The repository is always explicit. An optional change request must belong
        to that repository; overlapping IDs never determine the owner type.
        Scope discovery and creation serialize with claim admission. Callers may
        include this operation in their existing page/publication transaction.
        """
        validate_epoch_us(observed_at_us)
        if coverage_state not in STORED_COVERAGE_STATES:
            raise ValueError("Invalid stored coverage state")
        if isinstance(details_json, dict):
            details_json = json.dumps(details_json, allow_nan=False)
        transaction = (
            nullcontext() if self.connection.in_transaction else self.transaction()
        )
        with transaction:
            if (
                self.one(
                    "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
                    (repository_uuidv4,),
                )
                is None
            ):
                raise CatalogError(
                    "INVALID_COVERAGE_OWNER", "Coverage requires an existing repository"
                )
            if (
                change_request_id is not None
                and self.one(
                    "SELECT 1 FROM change_requests WHERE change_request_id=? AND repository_uuidv4=?",
                    (change_request_id, repository_uuidv4),
                )
                is None
            ):
                raise CatalogError(
                    "INVALID_COVERAGE_OWNER",
                    "Coverage change request must belong to the specified repository",
                )
            scope = self.one(
                "SELECT coverage_scope_id FROM coverage_scopes WHERE repository_uuidv4=? AND change_request_id IS ? AND kind=?",
                (repository_uuidv4, change_request_id, kind),
            )
            scope_id = scope[0] if scope else str(uuid.uuid4())
            if scope is None:
                self.execute(
                    "INSERT INTO coverage_scopes(coverage_scope_id,repository_uuidv4,change_request_id,kind) VALUES(?,?,?,?)",
                    (scope_id, repository_uuidv4, change_request_id, kind),
                )
            return admit_claim(
                self.connection, scope_id, coverage_state, observed_at_us, details_json
            )

    def git_object_id(self, algorithm, oid):
        row = self.one(
            "SELECT git_object_id FROM git_objects WHERE object_format=? AND oid=?",
            (algorithm, oid),
        )
        return row[0] if row else None
