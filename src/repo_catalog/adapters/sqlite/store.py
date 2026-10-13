from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path

from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
from repo_catalog.adapters.sqlite.coverage import admit_claim
from repo_catalog.adapters.sqlite.schema import (
    DDL_SHA256,
    FORMAT_ID,
    OPERATIONAL_DDL_SHA256,
    OPERATIONAL_FORMAT_ID,
    OPERATIONAL_SCHEMA_VERSION,
    SCHEMA_VERSION,
    SEARCH_DDL_SHA256,
    SEARCH_FORMAT_ID,
    SEARCH_SCHEMA_VERSION,
    operational_schema_sql,
    schema_sql,
    search_schema_sql,
)
from repo_catalog.config import load
from repo_catalog.domain.coverage import STORED_COVERAGE_STATES
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.time import now_us, validate_epoch_us


def statements(sql):
    pending = ""
    for line in sql.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip():
        raise CatalogError("SCHEMA_ERROR", "Incomplete schema SQL")


class BaseConnection:
    connection: sqlite3.Connection

    def execute(self, sql, args=()):
        return self.connection.execute(sql, args)

    def one(self, sql, args=()):
        return self.execute(sql, args).fetchone()

    def all(self, sql, args=()):
        return self.execute(sql, args).fetchall()

    @contextmanager
    def transaction(self, *, read=False):
        # Every nested unit has its own rollback boundary, including units whose
        # caller catches the error and continues the surrounding transaction.
        savepoint = (
            "unit_" + uuid.uuid4().hex if self.connection.in_transaction else None
        )
        self.execute(
            f"SAVEPOINT {savepoint}"
            if savepoint
            else "BEGIN"
            if read
            else "BEGIN IMMEDIATE"
        )
        try:
            yield self
            self.execute(f"RELEASE {savepoint}" if savepoint else "COMMIT")
        except BaseException as error:
            try:
                if self.connection.in_transaction:
                    if savepoint:
                        self.execute(f"ROLLBACK TO {savepoint}")
                        self.execute(f"RELEASE {savepoint}")
                    else:
                        self.execute("ROLLBACK")
            except BaseException as cleanup_error:
                error.add_note(
                    "Transaction cleanup failed: " + type(cleanup_error).__name__
                )
                # Retire a connection whose rollback cannot be completed.
                try:
                    self.connection.close()
                except BaseException as close_error:
                    error.add_note(
                        "Connection retirement failed: " + type(close_error).__name__
                    )
            raise

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Store(BaseConnection):
    """Mutable catalog3 core connection; readers use SQLite transaction snapshots."""

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
        self._operational_store: OperationalStore | None = None
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
        register_git_object_sql_function(self.connection)
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
                        "INSERT INTO database_identity(singleton,format_id,schema_version,db_instance_id,local_revision,ddl_sha256,lifecycle) VALUES(1,?,?,?,0,?,'validated')",
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
            "SELECT singleton,format_id,schema_version,db_instance_id,local_revision,ddl_sha256,lifecycle FROM database_identity"
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
                "Catalog installation is incomplete",
                {"lifecycle": row["lifecycle"]},
            )

    @property
    def operational(self) -> OperationalStore:
        if self._operational_store is None:
            self._operational_store = OperationalStore(
                self.path,
                catalog_db_instance_id=self.revision()["db_instance_id"],
                readonly=self.readonly,
                config=self.config,
            )
        return self._operational_store

    def open_search(self, *, create=False, readonly=None) -> SearchStore:
        return SearchStore(
            self.path,
            catalog_db_instance_id=self.revision()["db_instance_id"],
            create=create,
            readonly=self.readonly if readonly is None else readonly,
            config=self.config,
        )

    def close(self):
        if self._operational_store is not None:
            try:
                self._operational_store.close()
            finally:
                self._operational_store = None
        self.connection.close()

    def advance_local_revision(self):
        self.execute(
            "UPDATE database_identity SET local_revision=local_revision+1 WHERE singleton=1"
        )

    def revision(self):
        return dict(
            self.one(
                "SELECT db_instance_id,local_revision FROM database_identity WHERE singleton=1"
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
        include this operation in their existing resource transaction.
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


class OperationalStore(BaseConnection):
    """Dedicated operational SQLite connection for jobs, leases, progress, and telemetry (PF-P06, PF-P11, PF-P12)."""

    def __init__(
        self,
        state_dir,
        *,
        catalog_db_instance_id: str,
        readonly=False,
        config=None,
    ):
        self.path = Path(state_dir).resolve()
        self.config = config or load(self.path)
        self.catalog_db_instance_id = catalog_db_instance_id
        db = (
            self.path
            / self.config["database"].get("operational_filename", "operational.sqlite3")
        ).resolve()
        if not db.is_relative_to(self.path):
            raise CatalogError(
                "CONFIG_ERROR",
                "Operational database must remain inside state directory",
            )
        self.db_path = db
        self.readonly = readonly

        needs_init = not db.is_file()
        if readonly and needs_init:
            raise CatalogError("NOT_INITIALIZED", "Operational database does not exist")

        self.connection = sqlite3.connect(
            db.as_uri() + ("?mode=ro" if readonly and not needs_init else "?mode=rwc"),
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
            if needs_init:
                self._initialize()
            else:
                self.verify_format()
            if readonly:
                self.execute("PRAGMA query_only=ON")
            else:
                mode = self.config["database"]["journal_mode"]
                self.execute(f"PRAGMA journal_mode={mode}")
                self.execute("PRAGMA synchronous=EXTRA")
        except CatalogError:
            self.connection.close()
            raise
        except sqlite3.DatabaseError as cause:
            self.connection.close()
            # PF-P12: Never silently overwrite or delete corrupt DB.
            raise CatalogError(
                "DATABASE_CORRUPT",
                "Operational database is corrupt; requires explicit administrator recovery or removal",
            ) from cause
        except BaseException:
            self.connection.close()
            raise

    def _initialize(self):
        with self.transaction():
            for statement in statements(operational_schema_sql()):
                self.execute(statement)
            self.execute(
                "INSERT INTO operational_identity(singleton,format_id,schema_version,operational_instance_id,catalog_db_instance_id,created_at_us,ddl_sha256) VALUES(1,?,?,?,?,?,?)",
                (
                    OPERATIONAL_FORMAT_ID,
                    OPERATIONAL_SCHEMA_VERSION,
                    str(uuid.uuid4()),
                    self.catalog_db_instance_id,
                    now_us(),
                    OPERATIONAL_DDL_SHA256,
                ),
            )

    def verify_format(self):
        try:
            row = self.one(
                "SELECT singleton,format_id,schema_version,operational_instance_id,catalog_db_instance_id,ddl_sha256 FROM operational_identity"
            )
        except sqlite3.DatabaseError as cause:
            raise CatalogError(
                "DATABASE_CORRUPT",
                "Operational database is corrupt; requires explicit administrator recovery or removal",
            ) from cause
        if row is None or row["singleton"] != 1:
            raise CatalogError("DATABASE_CORRUPT", "Invalid operational identity")
        if (
            row["format_id"] != OPERATIONAL_FORMAT_ID
            or row["schema_version"] != OPERATIONAL_SCHEMA_VERSION
            or bytes(row["ddl_sha256"]) != OPERATIONAL_DDL_SHA256
        ):
            raise CatalogError(
                "SCHEMA_ERROR", "Unsupported operational database schema"
            )
        # PF-P11: Verify ownership to prevent cross-Catalog use.
        if row["catalog_db_instance_id"] != self.catalog_db_instance_id:
            raise CatalogError(
                "WRONG_CATALOG_OWNER",
                f"Operational database belongs to catalog instance {row['catalog_db_instance_id']}, expected {self.catalog_db_instance_id}",
            )

    def record_rebuild_metric(
        self,
        started_at_us: int,
        ended_at_us: int,
        duration_ms: int,
        documents_indexed: int,
        bytes_indexed: int,
        status: str,
    ):
        with self.transaction():
            self.execute(
                "INSERT INTO search_rebuild_metrics(started_at_us,ended_at_us,duration_ms,documents_indexed,bytes_indexed,status) VALUES(?,?,?,?,?,?)",
                (
                    started_at_us,
                    ended_at_us,
                    duration_ms,
                    documents_indexed,
                    bytes_indexed,
                    status,
                ),
            )

    def estimate_rebuild_cost(self) -> dict:
        row = self.one(
            "SELECT count(*) as runs, coalesce(avg(duration_ms), 0) as avg_duration_ms, coalesce(avg(duration_ms * 1.0 / max(documents_indexed, 1)), 0.0) as ms_per_doc, coalesce(avg(documents_indexed), 0) as avg_docs FROM search_rebuild_metrics WHERE status='complete'"
        )
        last_row = self.one(
            "SELECT duration_ms FROM search_rebuild_metrics WHERE status='complete' ORDER BY rebuild_id DESC LIMIT 1"
        )
        previous_duration_ms = (
            int(last_row["duration_ms"])
            if last_row and last_row["duration_ms"] is not None
            else None
        )
        if not row or row["runs"] == 0:
            return {
                "runs": 0,
                "historical_average_duration_ms": None,
                "previous_measured_duration_ms": None,
                "estimated_duration_ms": None,
                "previous_duration_ms": None,
                "avg_duration_ms": None,
                "ms_per_doc": None,
                "avg_documents_indexed": 0,
                "estimate_basis": "historical_average",
                "scope_note": "across_all_recorded_rebuilds",
            }
        avg_dur = round(float(row["avg_duration_ms"]), 2)
        return {
            "runs": row["runs"],
            "historical_average_duration_ms": avg_dur,
            "previous_measured_duration_ms": previous_duration_ms,
            "estimated_duration_ms": avg_dur,
            "previous_duration_ms": previous_duration_ms,
            "avg_duration_ms": avg_dur,
            "ms_per_doc": round(float(row["ms_per_doc"]), 4),
            "avg_documents_indexed": int(row["avg_docs"]),
            "estimate_basis": "historical_average",
            "scope_note": "across_all_recorded_rebuilds",
        }


class SearchStore(BaseConnection):
    """Dedicated search SQLite connection for rebuildable FTS5 and search projections (PF-P14, PF-P16, PF-P17)."""

    def __init__(
        self,
        state_dir,
        *,
        catalog_db_instance_id: str,
        create=False,
        readonly=False,
        config=None,
    ):
        self.path = Path(state_dir).resolve()
        self.config = config or load(self.path)
        self.catalog_db_instance_id = catalog_db_instance_id
        db = (
            self.path / self.config["database"].get("search_filename", "search.sqlite3")
        ).resolve()
        if not db.is_relative_to(self.path):
            raise CatalogError(
                "CONFIG_ERROR", "Search database must remain inside state directory"
            )
        self.db_path = db
        self.readonly = readonly

        if not db.is_file():
            if not create:
                # PF-P17: Search DB creation is explicit. Reads/searches must not create it.
                raise CatalogError(
                    "INDEX_UNAVAILABLE",
                    "Search database does not exist; requires explicit index rebuild",
                )
            needs_init = True
        else:
            needs_init = False

        self.connection = sqlite3.connect(
            db.as_uri() + ("?mode=ro" if readonly and not needs_init else "?mode=rwc"),
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
            if needs_init:
                self._initialize()
            else:
                self.verify_format()
            if readonly:
                self.execute("PRAGMA query_only=ON")
            else:
                mode = self.config["database"]["journal_mode"]
                self.execute(f"PRAGMA journal_mode={mode}")
                self.execute("PRAGMA synchronous=EXTRA")
        except CatalogError:
            self.connection.close()
            raise
        except sqlite3.DatabaseError as cause:
            self.connection.close()
            # PF-P17: Never silently overwrite corrupt Search DB.
            raise CatalogError(
                "DATABASE_CORRUPT",
                "Search database is corrupt; requires explicit repair or removal",
            ) from cause
        except BaseException:
            self.connection.close()
            raise

    def _initialize(self):
        with self.transaction():
            for statement in statements(search_schema_sql()):
                self.execute(statement)
            self.execute(
                "INSERT INTO search_identity(singleton,format_id,schema_version,search_instance_id,catalog_db_instance_id,created_at_us,last_rebuilt_at_us,core_revision_fence,ddl_sha256) VALUES(1,?,?,?,?,?,NULL,NULL,?)",
                (
                    SEARCH_FORMAT_ID,
                    SEARCH_SCHEMA_VERSION,
                    str(uuid.uuid4()),
                    self.catalog_db_instance_id,
                    now_us(),
                    SEARCH_DDL_SHA256,
                ),
            )

    def verify_format(self):
        try:
            row = self.one(
                "SELECT singleton,format_id,schema_version,search_instance_id,catalog_db_instance_id,ddl_sha256 FROM search_identity"
            )
        except sqlite3.DatabaseError as cause:
            raise CatalogError(
                "DATABASE_CORRUPT",
                "Search database is corrupt; requires explicit repair or removal",
            ) from cause
        if row is None or row["singleton"] != 1:
            raise CatalogError("DATABASE_CORRUPT", "Invalid search identity")
        if (
            row["format_id"] != SEARCH_FORMAT_ID
            or row["schema_version"] != SEARCH_SCHEMA_VERSION
            or bytes(row["ddl_sha256"]) != SEARCH_DDL_SHA256
        ):
            raise CatalogError("SCHEMA_ERROR", "Unsupported search database schema")
        # PF-P17: Ownership verification
        if row["catalog_db_instance_id"] != self.catalog_db_instance_id:
            raise CatalogError(
                "WRONG_CATALOG_OWNER",
                f"Search database belongs to catalog instance {row['catalog_db_instance_id']}, expected {self.catalog_db_instance_id}",
            )

    def update_last_rebuilt(
        self, timestamp_us: int, core_revision_fence: int | None = None
    ):
        with self.transaction():
            self.execute(
                "UPDATE search_identity SET last_rebuilt_at_us=?,core_revision_fence=? WHERE singleton=1",
                (timestamp_us, core_revision_fence),
            )

    def index_age_us(self) -> int | None:
        row = self.one(
            "SELECT last_rebuilt_at_us FROM search_identity WHERE singleton=1"
        )
        if not row or row["last_rebuilt_at_us"] is None:
            return None
        return max(0, now_us() - row["last_rebuilt_at_us"])

    def estimate_rebuild_cost(self, operational_store=None) -> dict:
        op = operational_store
        close_op = False
        if op is None:
            try:
                op = OperationalStore(
                    self.path,
                    catalog_db_instance_id=self.catalog_db_instance_id,
                    readonly=True,
                    config=self.config,
                )
                close_op = True
            except CatalogError as e:
                is_uninit = e.code == "NOT_INITIALIZED"
                return {
                    "runs": 0,
                    "historical_average_duration_ms": None,
                    "previous_measured_duration_ms": None,
                    "estimated_duration_ms": None,
                    "previous_duration_ms": None,
                    "avg_duration_ms": None,
                    "ms_per_doc": None,
                    "avg_documents_indexed": 0,
                    "telemetry_status": "uninitialized" if is_uninit else "unavailable",
                    "telemetry_diagnostic": "Operational database not initialized"
                    if is_uninit
                    else f"Operational database error: {e.code}",
                }
            except Exception as e:
                return {
                    "runs": 0,
                    "historical_average_duration_ms": None,
                    "previous_measured_duration_ms": None,
                    "estimated_duration_ms": None,
                    "previous_duration_ms": None,
                    "avg_duration_ms": None,
                    "ms_per_doc": None,
                    "avg_documents_indexed": 0,
                    "telemetry_status": "unavailable",
                    "telemetry_diagnostic": f"Operational database error: {type(e).__name__}",
                }
        try:
            res = op.estimate_rebuild_cost()
            res["telemetry_status"] = "available"
            return res
        except Exception as e:
            return {
                "runs": 0,
                "historical_average_duration_ms": None,
                "previous_measured_duration_ms": None,
                "estimated_duration_ms": None,
                "previous_duration_ms": None,
                "avg_duration_ms": None,
                "ms_per_doc": None,
                "avg_documents_indexed": 0,
                "telemetry_status": "unavailable",
                "telemetry_diagnostic": f"Telemetry query error: {type(e).__name__}",
            }
        finally:
            if close_op and op is not None:
                op.close()
