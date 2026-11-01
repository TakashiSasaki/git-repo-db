"""Context and paired Recovery integration over the canonical Core lifecycle."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from repo_catalog.adapters.sqlite.core_recovery import (
    CoreRecoveryAdapter,
    _bounded_utf8,
    _confirmed_integrity_failure,
    _fsync_file,
    _hash_recovery_bytes,
    assert_catalog_not_stopped,
    stop_catalog,
)
from repo_catalog.adapters.sqlite.core_recovery_validation import (
    validate_stored_checks,
    validate_stored_text_encoding,
)
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_schema import (
    SchemaError,
    expected_schema,
    register_functions,
    schema_rows,
    uuid4,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    connect as p1_connect,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    initialize as p1_init,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    validate as p1_schema_validate,
)
from repo_catalog.adapters.sqlite.recovery_validation import (
    validate_stored_admission_guards,
    verify_existing_context_text,
)
from repo_catalog.domain.recovery import (
    ActivationError,
    BackupScope,
    BackupValidationError,
    CandidateType,
    CorruptionDetectedError,
    RecoveryError,
    RetainedByteSummary,
)


def _context_identity_for_salvage(conn, core, work):
    """Read only fixed-size Context identity fields before using that store."""
    work.require("identity_read_rows", 2)
    try:
        work.require("identity_read_bytes", 144)
    except BaseException:
        work.abandon("identity_read_rows")
        raise
    try:
        rows = conn.execute(
            "SELECT store_role='context', "
            "CASE WHEN typeof(repository_uuidv4)='text' "
            "AND octet_length(repository_uuidv4)=36 "
            "THEN CAST(repository_uuidv4 AS BLOB) END, "
            "CASE WHEN typeof(catalog_instance_uuidv4)='text' "
            "AND octet_length(catalog_instance_uuidv4)=36 "
            "THEN CAST(catalog_instance_uuidv4 AS BLOB) END "
            "FROM store_identity LIMIT 2"
        ).fetchall()
    except BaseException:
        work.abandon("identity_read_rows")
        work.abandon("identity_read_bytes")
        raise
    work.charge("identity_read_rows", len(rows))
    work.charge(
        "identity_read_bytes",
        sum(len(value) for row in rows for value in row[1:] if value is not None),
    )
    try:
        if len(rows) != 1 or rows[0][0] != 1:
            raise ValueError("one Context identity is required")
        identity = tuple(value.decode("ascii") for value in rows[0][1:])
        if not all(uuid4(value) for value in identity):
            raise ValueError("canonical Context identity is required")
        return identity
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError) as error:
        core._integrity_stop(("Context identity", str(error)))


class SQLiteRecoveryAdapter(CoreRecoveryAdapter):
    """Paired validation/admission is explicitly installed with composed features."""

    def _require_scope(self, scope):
        if not isinstance(scope, BackupScope):
            raise RecoveryError("A supported Recovery scope is required")

    def _allow_generated_source(self, store_name):
        return store_name == "context"

    def _source_candidate_type(self, store_name):
        return (
            CandidateType.CONTEXT_RESOURCE
            if store_name == "context"
            else CandidateType.GIT_METADATA
        )

    def _special_source_candidate(self, store_name, table, row):
        if store_name == "context" and table == "text_bodies":
            return (
                CandidateType.CONTEXT_DOCUMENT,
                str(row.get("sha256")),
                {"sha256": row.get("sha256"), "text_value": row.get("text_value")},
            )
        return None

    def _validate_and_summarize_context(self, context_db: Path) -> RetainedByteSummary:
        conn = sqlite3.connect(f"file:{context_db.resolve()}?mode=ro", uri=True)
        try:
            register_functions(conn)
            # Strict P1 schema validation
            try:
                from repo_catalog.adapters.sqlite.p1_schema import configure

                configure(conn)
                p1_schema_validate(conn, "context")
            except Exception as e:
                raise BackupValidationError(
                    f"Context physical schema invalid: {e}"
                ) from e
            if schema_rows(conn) != expected_schema("context"):
                raise BackupValidationError(
                    "Context physical schema rows differ from packaged expectation"
                )

            validate_stored_text_encoding(conn, "context")
            validate_stored_checks(conn, "context", retained_bytes=False)
            validate_stored_admission_guards(conn, "context")

            result = conn.execute("PRAGMA integrity_check").fetchall()
            if not result or result[0][0] != "ok":
                raise BackupValidationError(
                    f"Context database integrity check failed: {result}"
                )
            fk_result = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_result:
                raise BackupValidationError(
                    f"Context foreign key check failed: {fk_result}"
                )

            identity_row = conn.execute(
                "SELECT repository_uuidv4, catalog_instance_uuidv4 FROM store_identity WHERE store_role='context'"
            ).fetchone()
            if not identity_row:
                raise BackupValidationError(
                    "Context store_identity missing or wrong role"
                )
            repo_uuid, inst_uuid = str(identity_row[0]), str(identity_row[1])
            if not uuid4(repo_uuid) or not uuid4(inst_uuid):
                raise BackupValidationError(
                    "Context repository or catalog instance UUID is not valid UUIDv4"
                )

            total_bytes = 0
            cursor = conn.execute("SELECT sha256, text_value FROM text_bodies")
            while row := cursor.fetchone():
                expected_sha, text_value = row
                if not isinstance(text_value, str):
                    raise BackupValidationError("Context text body must be a string")
                actual_sha = hashlib.sha256(text_value.encode("utf-8")).hexdigest()
                if actual_sha != expected_sha:
                    raise BackupValidationError(
                        f"Context text body SHA-256 mismatch: recorded {expected_sha}, actual {actual_sha}"
                    )
                total_bytes += len(text_value.encode("utf-8"))

            validate_stored_checks(conn, "context", retained_bytes=True)

            return RetainedByteSummary(total_retained_bytes=total_bytes)
        except sqlite3.Error as e:
            raise BackupValidationError(f"Context database error: {e}") from e
        finally:
            conn.close()

    def _open_context_merge(
        self,
        fresh_destination_dir,
        core,
        work,
        budget,
        exhausted,
        authorization,
        admission,
    ):
        ctx_db = fresh_destination_dir / "context.sqlite3"
        ctx_store = None
        ctx_conn = None
        ctx_identity = None
        ctx_auth = authorization
        ctx_admission = admission
        if ctx_db.exists() and not exhausted:
            ctx_conn = p1_connect(ctx_db, "context")
            try:
                ctx_identity = _context_identity_for_salvage(ctx_conn, core, work)
            except BaseException:
                ctx_conn.close()
                core.close()
                raise
            if ctx_auth is None or ctx_admission is None:
                repo_id = ctx_identity[0]
                repos = {repo_id} if repo_id else set()
                perm_repos = frozenset(repos) if repos else frozenset()
                from repo_catalog.domain.context_admission import (
                    AdmissionBudget,
                    AdmissionSelection,
                    DependencySet,
                    create_local_admission_service,
                )

                ctx_auth, ctx_admission, _ = create_local_admission_service(
                    operation="salvage_merge",
                    grants=DependencySet(repositories=repos),
                    permitted_repositories=perm_repos,
                    selection=AdmissionSelection(
                        all_selected=True,
                        max_work=min(
                            100_000_000,
                            max(
                                10_000_000,
                                budget.max_work_units.get(
                                    "verification_bytes", 10_000_000
                                ),
                            ),
                        ),
                        max_bytes=min(
                            100_000_000,
                            max(16 * 1024 * 1024, budget.max_payload_bytes * 8),
                        ),
                        max_units=min(
                            100_000_000,
                            max(10_000, budget.max_input_records * 4),
                        ),
                    ),
                    budget=AdmissionBudget(
                        work_limit=min(
                            100_000_000,
                            max(
                                10_000_000,
                                budget.max_work_units.get(
                                    "verification_bytes", 10_000_000
                                ),
                            ),
                        ),
                        bytes_limit=min(
                            100_000_000,
                            max(16 * 1024 * 1024, budget.max_payload_bytes * 8),
                        ),
                        dependency_limit=min(
                            100_000_000,
                            max(100_000, budget.max_input_records * 4),
                        ),
                    ),
                    principal="recovery-coordinator",
                    credential="recovery-coordinator",
                )
            else:
                ctx_auth.validate_context(ctx_admission)
            ctx_store = ContextStore(ctx_conn, authorization=ctx_auth)

        return ctx_store, ctx_conn, ctx_admission, ctx_identity

    def _merge_context_candidate(
        self,
        payload,
        fresh_destination_dir,
        ctx_store,
        ctx_conn,
        ctx_admission,
        budget,
        work,
    ):
        text_val = payload.get("text_value")
        text_bytes = _bounded_utf8(text_val, budget.max_payload_bytes, work)
        expected_sha = payload.get("sha256")
        actual_sha = _hash_recovery_bytes(text_bytes, work)
        if expected_sha and expected_sha != actual_sha:
            raise ValueError("Text body SHA-256 mismatch")
        with ctx_store.transaction(admission=ctx_admission):
            assert_catalog_not_stopped(fresh_destination_dir)
            try:
                exists = verify_existing_context_text(
                    ctx_conn,
                    actual_sha,
                    text_bytes,
                    budget.max_payload_bytes,
                    work,
                )
            except BackupValidationError as error:
                # Publish the stop while holding the
                # writer cut, before any other ordinary
                # operation can pass the diagnosed row.
                reason = "Confirmed destination Context corruption: " + str(error)
                stop_catalog(
                    fresh_destination_dir,
                    reason,
                    details={
                        "store": "context",
                        "classification": "authoritative_data",
                    },
                )
                raise CorruptionDetectedError(reason) from error
            if not exists:
                # ContextStore hashes once; SQLite's
                # SHA-256 CHECK hashes the new row again.
                cost = len(text_bytes) * 2
                work.require("verification_bytes", cost)
                ctx_store.text(text_val)
                work.charge("verification_bytes", cost)
            assert_catalog_not_stopped(fresh_destination_dir)
        return exists

    def _validate_activation_context(self, fresh_catalog_dir, repo_uuid, inst_uuid):
        ctx_db = fresh_catalog_dir / "context.sqlite3"
        try:
            self._validate_and_summarize_context(ctx_db)
            ctx_repo_uuid, ctx_inst_uuid = self._extract_identities(ctx_db, "context")
        except (
            BackupValidationError,
            SchemaError,
            sqlite3.DatabaseError,
        ) as error:
            classification = _confirmed_integrity_failure(error)
            if classification:
                stop_catalog(
                    fresh_catalog_dir,
                    str(error),
                    details={
                        "store": "context",
                        "classification": classification,
                    },
                )
            raise ActivationError("Fresh Context validation failed") from error
        if repo_uuid != ctx_repo_uuid or inst_uuid != ctx_inst_uuid:
            stop_catalog(
                fresh_catalog_dir,
                "Core and Context identities differ",
                details={
                    "store": "core+context",
                    "classification": "authoritative_data",
                },
            )
            raise ActivationError(
                f"Catalog activation identity mismatch: Core ({repo_uuid}, {inst_uuid}) vs Context ({ctx_repo_uuid}, {ctx_inst_uuid})"
            )

    def _reconstruct_optional_stores(self, fresh_catalog_dir, repo_uuid, inst_uuid):
        # Initialize empty reconstructible stores. This does not rebuild the
        # full Search projection; its receipt explicitly says initialized_empty.
        # Reconstruct Operational and Search cleanly from compiled P1 DDL
        op_db = fresh_catalog_dir / "operational.sqlite3"
        for path in (op_db, Path(str(op_db) + "-wal"), Path(str(op_db) + "-shm")):
            if path.exists() or path.is_symlink():
                path.unlink()
        p1_init(op_db, "operational", repo_uuid, inst_uuid)
        _fsync_file(op_db)

        search_db = fresh_catalog_dir / "search.sqlite3"
        for path in (
            search_db,
            Path(str(search_db) + "-wal"),
            Path(str(search_db) + "-shm"),
        ):
            if path.exists() or path.is_symlink():
                path.unlink()
        p1_init(search_db, "search", repo_uuid, inst_uuid)
        _fsync_file(search_db)

    def _merge_optional_candidate(
        self, kind, payload, directory, store, connection, admission, budget, work
    ):
        if kind == CandidateType.CONTEXT_RESOURCE.value:
            return (
                "observation",
                "Context resource requires typed dependency reconciliation; qualified non-authoritative observation only",
            )
        if store is None:
            return "rejected", "Context store not present in destination"
        replay = self._merge_context_candidate(
            payload, directory, store, connection, admission, budget, work
        )
        return ("replayed" if replay else "admitted"), None
