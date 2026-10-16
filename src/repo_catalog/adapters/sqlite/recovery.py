"""SQLite and filesystem recovery adapters for P7 under ADR 0026."""

from __future__ import annotations

import base64
import ctypes
import errno
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_coordination import (
    NotesLimits,
    _file_gate,
    catalog_completion,
    catalog_gate,
    persist_catalog_stop,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    SchemaError,
    expected_schema,
    oid,
    register_functions,
    schema_rows,
    uuid4,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    connect as p1_connect,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    fingerprint as p1_schema_fingerprint,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    initialize as p1_init,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    validate as p1_schema_validate,
)
from repo_catalog.domain.git_native import parse_metadata
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreFailure,
    NativeObject,
    NotesProof,
    native_oid,
    valid_note_role,
)
from repo_catalog.domain.recovery import (
    ActivationError,
    ActivationReceipt,
    BackupManifest,
    BackupReceipt,
    BackupScope,
    BackupValidationError,
    CandidateType,
    CatalogStoppedError,
    CorruptionDetectedError,
    ExtractionStatus,
    MergeReceipt,
    RecoveryBudget,
    RecoveryError,
    RestoreReceipt,
    RestoreValidationError,
    RetainedByteSummary,
    SalvageError,
    SalvageReceipt,
    SourceIntegrityIndeterminateError,
    StoreManifest,
)

AT_FDCWD = -100
RENAME_NOREPLACE = 1


def _decode_native_ref(raw_ref: str | None) -> str | None:
    if not raw_ref:
        return raw_ref
    if raw_ref.startswith("refs/"):
        return raw_ref
    try:
        parsed = json.loads(raw_ref)
        if isinstance(parsed, list) and len(parsed) == 2 and parsed[0] == "native-ref":
            return bytes.fromhex(parsed[1]).decode("utf-8", "surrogateescape")
    except Exception:
        pass
    return raw_ref


def _atomic_publish_noreplace(staging_dir: Path, destination_path: Path) -> None:
    """Publish staging_dir to destination_path atomically without overwriting destination.

    Uses renameat2(RENAME_NOREPLACE) on Linux POSIX filesystems. Fails closed if
    destination exists, if crossing filesystem boundary, or if atomic primitive is unsupported.
    """
    staging_dir = Path(staging_dir).resolve()
    destination_path = Path(destination_path)

    if staging_dir == destination_path:
        raise RecoveryError(
            f"Staging and destination paths are identical: {staging_dir}"
        )
    if not staging_dir.exists():
        raise RecoveryError(f"Staging directory missing: {staging_dir}")
    if destination_path.parent.resolve() != staging_dir.parent.resolve():
        raise RecoveryError(
            f"Staging {staging_dir} and destination {destination_path} must share the same parent directory"
        )

    if destination_path.exists() or destination_path.is_symlink():
        raise BackupValidationError(
            f"Destination {destination_path} already exists; no-overwrite publication prevented clobbering"
        )

    if os.name == "posix":
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            if hasattr(libc, "renameat2"):
                libc.renameat2.argtypes = [
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_uint,
                ]
                libc.renameat2.restype = ctypes.c_int
                src_bytes = os.fsencode(str(staging_dir))
                dst_bytes = os.fsencode(str(destination_path))
                res = libc.renameat2(
                    AT_FDCWD, src_bytes, AT_FDCWD, dst_bytes, RENAME_NOREPLACE
                )
                if res != 0:
                    err = ctypes.get_errno()
                    if err == errno.EEXIST:
                        raise BackupValidationError(
                            f"Destination {destination_path} already exists; no-overwrite publication prevented clobbering"
                        )
                    raise RecoveryError(
                        f"renameat2 failed with errno {err}: {os.strerror(err)}"
                    )
                _fsync_dir(destination_path.parent)
                return
        except (AttributeError, OSError) as e:
            if isinstance(e, BackupValidationError):
                raise
            raise RecoveryError(f"Atomic no-overwrite renameat2 failed: {e}") from e

    raise RecoveryError(
        "Atomic no-overwrite renameat2(RENAME_NOREPLACE) is not available on this platform; failing closed"
    )


def _check_json_depth(
    obj: Any,
    current_depth: int = 1,
    max_depth: int = 16,
    max_elements: int = 10_000,
    element_counter: list[int] | None = None,
) -> None:
    if current_depth > max_depth:
        raise ValueError(
            f"JSON nesting depth exceeds maximum allowed limit of {max_depth}"
        )
    if element_counter is None:
        element_counter = [0]
    if isinstance(obj, dict):
        element_counter[0] += len(obj)
        if element_counter[0] > max_elements:
            raise ValueError(
                f"JSON element count exceeds maximum allowed limit of {max_elements}"
            )
        for v in obj.values():
            _check_json_depth(
                v, current_depth + 1, max_depth, max_elements, element_counter
            )
    elif isinstance(obj, list):
        element_counter[0] += len(obj)
        if element_counter[0] > max_elements:
            raise ValueError(
                f"JSON element count exceeds maximum allowed limit of {max_elements}"
            )
        for v in obj:
            _check_json_depth(
                v, current_depth + 1, max_depth, max_elements, element_counter
            )


class RecoveryWorkBudget:
    """Finite work budget enforcing explicit resource limits during recovery merge."""

    def __init__(
        self,
        *,
        note_bytes: int = 16 * 1024 * 1024,
        work_limits: Mapping[str, int] | None = None,
        initial_usage: Mapping[str, int] | None = None,
    ) -> None:
        self.limits = NotesLimits(note_bytes=note_bytes)
        self._max = dict(NotesLimits.work_limits())
        if work_limits is not None:
            self._max.update(work_limits)
        self.usage: dict[str, int] = dict.fromkeys(self._max, 0)
        if initial_usage:
            for k, v in initial_usage.items():
                if k in self.usage and type(v) is int and v >= 0:
                    self.usage[k] = v
        self._pending: dict[str, int] = {}

    def is_exhausted(self, unit: str | None = None) -> bool:
        if unit is not None:
            limit = self._max.get(unit)
            return limit is not None and self.usage.get(unit, 0) >= limit
        return any(self.usage[u] >= self._max[u] for u in self._max if u in self.usage)

    def require(self, unit: str, amount: int = 1) -> None:
        if type(amount) is not int or amount < 0:
            raise ValueError("nonnegative integer work amount required")
        limit = self._max.get(unit)
        if limit is None:
            raise ValueError(f"unknown work unit: {unit}")
        if self.usage[unit] + amount > limit:
            raise CoreFailure(
                "BUDGET",
                unit,
                f"finite cumulative recovery work budget exhausted ({unit})",
            )
        if unit in self._pending:
            raise CoordinationError("UNSETTLED_WORK", "recovery", unit)
        self.usage[unit] += amount
        self._pending[unit] = amount

    def abandon(self, unit: str) -> None:
        if unit not in self._pending:
            raise CoordinationError("UNRESERVED_WORK", "recovery", unit)
        del self._pending[unit]

    def charge(self, unit: str, amount: int) -> None:
        if unit not in self._pending:
            raise CoordinationError("UNRESERVED_WORK", "recovery", unit)
        reserved = self._pending.pop(unit)
        if type(amount) is not int or amount < 0 or amount > reserved:
            raise ValueError("invalid charged work amount")


def _confirmed_integrity_failure(error: Exception) -> str | None:
    """Only positive integrity evidence can label a source corrupt.

    Validation wrappers retain causes. A lock, IO/permission failure, resource
    exhaustion or unexpected implementation failure anywhere in that chain is
    indeterminate, even when wrapped as BackupValidationError.
    """
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__
    for cause in chain:
        if isinstance(cause, sqlite3.Error):
            code = getattr(cause, "sqlite_errorcode", 0)
            if code & 255 not in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                return None
        elif isinstance(cause, (OSError, MemoryError, CoordinationError)):
            return None
        elif isinstance(cause, CoreFailure) and cause.code not in (
            "NATIVE_SYNTAX",
            "INVALID_IDENTITY",
            "INVALID_OBJECT",
        ):
            return None
        elif not isinstance(cause, (BackupValidationError, SchemaError, CoreFailure)):
            return None
    if any(isinstance(cause, SchemaError) for cause in chain):
        return "physical_schema"
    if isinstance(error, BackupValidationError) or any(
        isinstance(cause, sqlite3.Error) for cause in chain
    ):
        return "authoritative_data"
    return None


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as f:
        os.fsync(f.fileno())


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def is_catalog_stopped(catalog_dir: Path) -> bool:
    catalog_dir = Path(catalog_dir)
    return (catalog_dir / "recovery.stop").exists() or (
        catalog_dir / "p1-recovery-stop.json"
    ).exists()


def assert_catalog_not_stopped(catalog_dir: Path) -> None:
    if is_catalog_stopped(catalog_dir):
        raise CatalogStoppedError(
            f"Catalog at {catalog_dir} is in recovery stop mode; normal operations are fenced"
        )


def stop_catalog(catalog_dir: Path, reason: str, details: dict | None = None) -> None:
    catalog_dir = Path(catalog_dir)
    persist_catalog_stop(catalog_dir, reason)
    stop_file = catalog_dir / "recovery.stop"
    payload = {
        "reason": reason,
        "stopped_at_us": int(time.time() * 1_000_000),
        "details": details or {},
    }
    with _file_gate(catalog_dir / "p1-stop-fence.lock", exclusive=True):
        if not stop_file.exists():
            temp_path = catalog_dir / f"recovery.stop.tmp.{uuid.uuid4().hex}"
            temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            _fsync_file(temp_path)
            os.replace(temp_path, stop_file)
            _fsync_dir(catalog_dir)


class SQLiteRecoveryAdapter:
    """Production P7 backup, salvage, restore, and activation adapter under ADR 0026."""

    def create_consistent_backup(
        self,
        catalog_dir: Path,
        destination_path: Path,
        scope: BackupScope = BackupScope.PAIRED,
        *,
        snapshot_cut_callback: Callable[[], None] | None = None,
    ) -> BackupReceipt:
        catalog_dir = Path(catalog_dir)
        destination_path = Path(destination_path)

        assert_catalog_not_stopped(catalog_dir)

        if destination_path.exists() or destination_path.is_symlink():
            raise BackupValidationError(
                f"Destination path {destination_path} already exists; no-overwrite invariant violated"
            )

        core_db_path = catalog_dir / "core.sqlite3"
        context_db_path = catalog_dir / "context.sqlite3"

        if not core_db_path.exists():
            raise BackupValidationError(
                f"Authoritative core database missing at {core_db_path}"
            )

        if scope == BackupScope.PAIRED and not context_db_path.exists():
            raise BackupValidationError(
                f"Paired scope requires context database, but {context_db_path} is missing"
            )

        backup_id = str(uuid.uuid4())
        created_at_us = int(time.time() * 1_000_000)

        staging_dir = (
            destination_path.parent / f"{destination_path.name}.tmp.{backup_id}"
        )
        staging_dir.mkdir(parents=True, exist_ok=False)

        try:
            try:
                with catalog_gate(catalog_dir, exclusive=True):
                    assert_catalog_not_stopped(catalog_dir)

                    stores_dir = staging_dir / "stores"
                    stores_dir.mkdir()

                    # Snapshot Core
                    staged_core = stores_dir / "core.sqlite3"
                    snapshot_source, snapshot_role = core_db_path, "core"
                    self._snapshot_database(core_db_path, staged_core)

                    # Snapshot Context if paired
                    staged_context = None
                    if scope == BackupScope.PAIRED:
                        staged_context = stores_dir / "context.sqlite3"
                        snapshot_source, snapshot_role = context_db_path, "context"
                        self._snapshot_database(context_db_path, staged_context)

                    # Execute cut callback while lock is actively held, if provided
                    if snapshot_cut_callback is not None:
                        snapshot_cut_callback()
            except sqlite3.Error as e:
                self._diagnose_and_stop_if_source_corrupt(
                    catalog_dir, snapshot_source, snapshot_role, e
                )
                raise BackupValidationError(str(e)) from e

            # Deep Domain and Retained-Byte Validation outside writer lock
            try:
                core_summary = self._validate_and_summarize_core(staged_core)
            except (BackupValidationError, sqlite3.Error) as e:
                self._diagnose_and_stop_if_source_corrupt(
                    catalog_dir, core_db_path, "core", e
                )
                raise BackupValidationError(str(e)) from e

            context_summary = RetainedByteSummary()
            if staged_context:
                try:
                    context_summary = self._validate_and_summarize_context(
                        staged_context
                    )
                except (BackupValidationError, sqlite3.Error) as e:
                    self._diagnose_and_stop_if_source_corrupt(
                        catalog_dir, context_db_path, "context", e
                    )
                    raise BackupValidationError(str(e)) from e

            total_summary = RetainedByteSummary(
                commit_count=core_summary.commit_count,
                tree_count=core_summary.tree_count,
                tag_count=core_summary.tag_count,
                notes_body_count=core_summary.notes_body_count,
                total_retained_bytes=core_summary.total_retained_bytes
                + context_summary.total_retained_bytes,
            )

            # Extract repository and catalog instance identity
            repo_uuid, inst_uuid = self._extract_identities(staged_core, "core")

            if staged_context:
                ctx_repo_uuid, ctx_inst_uuid = self._extract_identities(
                    staged_context, "context"
                )
                if repo_uuid != ctx_repo_uuid or inst_uuid != ctx_inst_uuid:
                    raise BackupValidationError(
                        f"Paired store identity mismatch: Core ({repo_uuid}, {inst_uuid}) vs Context ({ctx_repo_uuid}, {ctx_inst_uuid})"
                    )

            # Clean up any transient -wal or -shm sidecars created during read-only validation
            for sidecar in stores_dir.glob("*.sqlite3-*"):
                sidecar.unlink()

            # Build StoreManifests
            core_sha = _sha256_file(staged_core)
            stores_map = {
                "core": StoreManifest(
                    path="stores/core.sqlite3",
                    bytes=staged_core.stat().st_size,
                    sha256=core_sha,
                    schema_fingerprint=self._compute_schema_fingerprint(
                        staged_core, "core"
                    ),
                )
            }

            if staged_context:
                ctx_sha = _sha256_file(staged_context)
                stores_map["context"] = StoreManifest(
                    path="stores/context.sqlite3",
                    bytes=staged_context.stat().st_size,
                    sha256=ctx_sha,
                    schema_fingerprint=self._compute_schema_fingerprint(
                        staged_context, "context"
                    ),
                )

            # Compute overall SHA-256 of payload files in deterministic sorted store order
            overall_hasher = hashlib.sha256()
            for name in sorted(stores_map.keys()):
                overall_hasher.update(stores_map[name].sha256.encode("ascii"))
            overall_sha256 = overall_hasher.hexdigest()

            manifest = BackupManifest(
                manifest_version=1,
                backup_id=backup_id,
                created_at_us=created_at_us,
                repository_uuidv4=repo_uuid,
                catalog_instance_uuidv4=inst_uuid,
                scope=scope,
                stores=stores_map,
                retained_byte_summary=total_summary,
                overall_sha256=overall_sha256,
            )

            # Write manifest.json and manifest.json.sha256
            manifest_path = staging_dir / "manifest.json"
            manifest_json = json.dumps(
                {
                    "manifest_version": manifest.manifest_version,
                    "backup_id": manifest.backup_id,
                    "created_at_us": manifest.created_at_us,
                    "repository_uuidv4": manifest.repository_uuidv4,
                    "catalog_instance_uuidv4": manifest.catalog_instance_uuidv4,
                    "scope": manifest.scope.value,
                    "stores": {
                        k: {
                            "path": v.path,
                            "bytes": v.bytes,
                            "sha256": v.sha256,
                            "schema_fingerprint": v.schema_fingerprint,
                        }
                        for k, v in manifest.stores.items()
                    },
                    "retained_byte_summary": {
                        "commit_count": total_summary.commit_count,
                        "tree_count": total_summary.tree_count,
                        "tag_count": total_summary.tag_count,
                        "notes_body_count": total_summary.notes_body_count,
                        "total_retained_bytes": total_summary.total_retained_bytes,
                    },
                    "overall_sha256": manifest.overall_sha256,
                },
                indent=2,
            )
            manifest_path.write_text(manifest_json + "\n", encoding="utf-8")
            _fsync_file(manifest_path)

            manifest_sha_path = staging_dir / "manifest.json.sha256"
            manifest_sha_path.write_text(
                _sha256_file(manifest_path) + "  manifest.json\n", encoding="utf-8"
            )
            _fsync_file(manifest_sha_path)

            _fsync_dir(stores_dir)
            _fsync_dir(staging_dir)

            # Atomic publication with no-overwrite primitive under catalog completion fence
            try:
                with catalog_completion(catalog_dir):
                    assert_catalog_not_stopped(catalog_dir)
                    _atomic_publish_noreplace(staging_dir, destination_path)
            except CoordinationError as ce:
                raise CatalogStoppedError(
                    f"Catalog at {catalog_dir} entered recovery stop; normal backup publication prevented: {ce}"
                ) from ce

            return BackupReceipt(
                backup_id=backup_id,
                backup_path=str(destination_path),
                scope=scope,
                manifest=manifest,
                overall_sha256=overall_sha256,
                verified_retained_bytes=total_summary.total_retained_bytes,
                verified_clean=True,
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def _diagnose_and_stop_if_source_corrupt(
        self,
        catalog_dir: Path,
        source_db_path: Path,
        store_role: str,
        staging_error: Exception,
    ) -> None:
        """Distinguish confirmed authoritative source corruption from staging-only copy defects.

        Under ADR 0026: if authoritative source exhibits integrity, schema or retained-data
        corruption, immediately persist catalog recovery stop and fence ordinary operations.
        If source is sound (staging copy defect only), do not stop healthy authoritative catalog.
        """
        if store_role not in ("core", "context"):
            raise ValueError("unknown authoritative store role")
        with catalog_gate(catalog_dir, exclusive=True):
            assert_catalog_not_stopped(catalog_dir)
            try:
                if store_role == "core":
                    self._validate_and_summarize_core(source_db_path)
                else:
                    self._validate_and_summarize_context(source_db_path)
            except Exception as source_error:
                category = _confirmed_integrity_failure(source_error)
                if category is None:
                    raise SourceIntegrityIndeterminateError(
                        f"Indeterminate {store_role} source integrity; validation unavailable: {source_error}"
                    ) from source_error
                # Persist the fence before releasing the protected writer cut.
                # A diagnostic write to the suspect database is never required.
                reason = f"Confirmed authoritative {store_role} corruption ({category}): {source_error}"
                stop_catalog(
                    catalog_dir,
                    reason,
                    details={
                        "store": store_role,
                        "classification": category,
                        "staging_error": str(staging_error),
                        "source_error": str(source_error),
                    },
                )
                raise CorruptionDetectedError(reason) from source_error

    def _snapshot_database(self, source_path: Path, target_path: Path) -> None:
        source_uri = f"file:{source_path.resolve()}?mode=ro"
        src_conn = sqlite3.connect(source_uri, uri=True, timeout=1.0)
        try:
            register_functions(src_conn)
            dst_conn = sqlite3.connect(str(target_path))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
        _fsync_file(target_path)

    def _extract_identities(
        self, db_path: Path, store: str = "core"
    ) -> tuple[str, str]:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
        try:
            register_functions(conn)
            row = conn.execute(
                "SELECT repository_uuidv4, catalog_instance_uuidv4 FROM store_identity WHERE store_role=?",
                (store,),
            ).fetchone()
            if row:
                repo_id, inst_id = str(row[0]), str(row[1])
                if not uuid4(repo_id) or not uuid4(inst_id):
                    raise BackupValidationError(
                        f"{store} store_identity UUID is not valid canonical UUIDv4"
                    )
                return repo_id, inst_id
            raise BackupValidationError(
                f"{store} store_identity missing or wrong role; cannot extract authoritative identity"
            )
        finally:
            conn.close()

    def _compute_schema_fingerprint(self, db_path: Path, store: str) -> str:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
        try:
            register_functions(conn)
            try:
                p1_schema_validate(conn, store)
            except Exception as e:
                raise BackupValidationError(
                    f"Physical schema validation failed for {store}: {e}"
                ) from e
            if schema_rows(conn) != expected_schema(store):
                raise BackupValidationError(
                    f"Physical schema for {store} differs from authoritative target schema"
                )
            return p1_schema_fingerprint(store)
        finally:
            conn.close()

    def _validate_and_summarize_core(self, core_db: Path) -> RetainedByteSummary:
        conn = sqlite3.connect(f"file:{core_db.resolve()}?mode=ro", uri=True)
        try:
            register_functions(conn)
            # PRAGMA integrity_check
            result = conn.execute("PRAGMA integrity_check").fetchall()
            if not result or result[0][0] != "ok":
                raise BackupValidationError(
                    f"Core database integrity check failed: {result}"
                )
            fk_result = conn.execute("PRAGMA foreign_key_check").fetchall()
            if fk_result:
                raise BackupValidationError(
                    f"Core foreign key check failed: {fk_result}"
                )

            # Strict P1 schema validation
            try:
                p1_schema_validate(conn, "core")
            except Exception as e:
                raise BackupValidationError(f"Core physical schema invalid: {e}") from e
            if schema_rows(conn) != expected_schema("core"):
                raise BackupValidationError(
                    "Core physical schema rows differ from packaged expectation"
                )

            # Verify store_identity
            identity_row = conn.execute(
                "SELECT repository_uuidv4, catalog_instance_uuidv4 FROM store_identity WHERE store_role='core'"
            ).fetchone()
            if not identity_row:
                raise BackupValidationError("Core store_identity missing or wrong role")
            repo_uuid, inst_uuid = str(identity_row[0]), str(identity_row[1])
            if not uuid4(repo_uuid) or not uuid4(inst_uuid):
                raise BackupValidationError(
                    "Core repository or catalog instance UUID is not valid UUIDv4"
                )

            total_bytes = 0
            commits = 0
            trees = 0
            tags = 0
            notes = 0

            # 1. Inspect retained_metadata: commits, trees, tags
            cursor = conn.execute(
                "SELECT object_format, full_oid, physical_copy_uuidv4, native_type, body, size, digest_sha256 FROM retained_metadata"
            )
            while row := cursor.fetchone():
                (
                    obj_fmt,
                    full_oid,
                    copy_uuid,
                    ntype,
                    body,
                    size,
                    digest_sha,
                ) = row
                if not uuid4(str(copy_uuid)):
                    raise BackupValidationError(
                        f"Invalid physical copy UUIDv4 in retained_metadata for {full_oid}"
                    )
                if not oid(obj_fmt, full_oid):
                    raise BackupValidationError(
                        f"Invalid native OID format in retained_metadata: {full_oid}"
                    )
                if len(body) != size:
                    raise BackupValidationError(
                        f"Size mismatch in retained_metadata for {full_oid}: expected {size}, got {len(body)}"
                    )
                actual_digest = hashlib.sha256(body).hexdigest()
                if actual_digest != digest_sha:
                    raise BackupValidationError(
                        f"SHA-256 digest mismatch in retained_metadata for {full_oid}: expected {digest_sha}, got {actual_digest}"
                    )
                expected_oid = native_oid(obj_fmt, ntype, body)
                if expected_oid != full_oid:
                    raise BackupValidationError(
                        f"Native OID calculation mismatch in retained_metadata for {full_oid}: expected {expected_oid}"
                    )
                if ntype not in ("commit", "tree", "tag"):
                    raise BackupValidationError(
                        f"Unsupported native_type in retained_metadata: {ntype}"
                    )
                # Verify native grammar
                try:
                    parse_metadata(obj_fmt, ntype, body)
                except Exception as e:
                    raise BackupValidationError(
                        f"Native git {ntype} grammar validation failed for {full_oid}: {e}"
                    ) from e

                total_bytes += len(body)
                if ntype == "commit":
                    commits += 1
                elif ntype == "tree":
                    trees += 1
                elif ntype == "tag":
                    tags += 1

            # 2. Inspect retained_notes: verified notes blob bodies and role proofs
            cursor = conn.execute(
                "SELECT object_format, full_oid, physical_copy_uuidv4, body, size, digest_sha256, capture_origin_uuidv4, capture_uuidv4, root, target, path, proof_bundle FROM retained_notes"
            )
            while row := cursor.fetchone():
                (
                    obj_fmt,
                    full_oid,
                    copy_uuid,
                    body,
                    size,
                    digest_sha,
                    cap_origin,
                    cap_id,
                    root,
                    target,
                    path,
                    proof_bundle,
                ) = row
                if not uuid4(str(copy_uuid)):
                    raise BackupValidationError(
                        f"Invalid physical copy UUIDv4 in retained_notes for {full_oid}"
                    )
                if not uuid4(str(cap_origin)) or not uuid4(str(cap_id)):
                    raise BackupValidationError(
                        f"Invalid capture UUIDv4 pair in retained_notes for {full_oid}"
                    )
                if (
                    not oid(obj_fmt, full_oid)
                    or not oid(obj_fmt, root)
                    or not oid(obj_fmt, target)
                ):
                    raise BackupValidationError(
                        f"Invalid OID in retained_notes for {full_oid}"
                    )
                if len(body) != size:
                    raise BackupValidationError(
                        f"Size mismatch in retained_notes for {full_oid}: expected {size}, got {len(body)}"
                    )
                actual_digest = hashlib.sha256(body).hexdigest()
                if actual_digest != digest_sha:
                    raise BackupValidationError(
                        f"SHA-256 digest mismatch in retained_notes for {full_oid}: expected {digest_sha}, got {actual_digest}"
                    )
                expected_oid = native_oid(obj_fmt, "blob", body)
                if expected_oid != full_oid:
                    raise BackupValidationError(
                        f"Native OID calculation mismatch in retained_notes for {full_oid}: expected {expected_oid}"
                    )

                # Full structural role verification under ADR 0022
                if not valid_note_role(
                    obj_fmt, root, target, full_oid, path, proof_bundle
                ):
                    raise BackupValidationError(
                        f"Retained note {full_oid} failed structural role receiver verification (ADR 0022)"
                    )

                # Verify corresponding note_roles entry exists
                role_check = conn.execute(
                    "SELECT 1 FROM note_roles WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? AND root=? AND target=? AND note=? AND path=? AND proof_bundle=?",
                    (
                        cap_origin,
                        cap_id,
                        obj_fmt,
                        root,
                        target,
                        full_oid,
                        path,
                        proof_bundle,
                    ),
                ).fetchone()
                if not role_check:
                    raise BackupValidationError(
                        f"Retained note {full_oid} lacks valid corresponding role proof in note_roles"
                    )

                notes += 1
                total_bytes += len(body)

            return RetainedByteSummary(
                commit_count=commits,
                tree_count=trees,
                tag_count=tags,
                notes_body_count=notes,
                total_retained_bytes=total_bytes,
            )
        except sqlite3.Error as e:
            raise BackupValidationError(f"Core database error: {e}") from e
        finally:
            conn.close()

    def _validate_and_summarize_context(self, context_db: Path) -> RetainedByteSummary:
        conn = sqlite3.connect(f"file:{context_db.resolve()}?mode=ro", uri=True)
        try:
            register_functions(conn)
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

            # Strict P1 schema validation
            try:
                p1_schema_validate(conn, "context")
            except Exception as e:
                raise BackupValidationError(
                    f"Context physical schema invalid: {e}"
                ) from e
            if schema_rows(conn) != expected_schema("context"):
                raise BackupValidationError(
                    "Context physical schema rows differ from packaged expectation"
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
                    raise BackupValidationError(
                        "Context text body must be a string"
                    )
                actual_sha = hashlib.sha256(text_value.encode("utf-8")).hexdigest()
                if actual_sha != expected_sha:
                    raise BackupValidationError(
                        f"Context text body SHA-256 mismatch: recorded {expected_sha}, actual {actual_sha}"
                    )
                total_bytes += len(text_value.encode("utf-8"))

            return RetainedByteSummary(total_retained_bytes=total_bytes)
        except sqlite3.Error as e:
            raise BackupValidationError(f"Context database error: {e}") from e
        finally:
            conn.close()

    def extract_salvage(
        self,
        catalog_dir: Path,
        output_file: Path,
        max_records: int | None = None,
        max_bytes: int | None = None,
        budget: RecoveryBudget | None = None,
    ) -> SalvageReceipt:
        catalog_dir = Path(catalog_dir)
        output_file = Path(output_file)

        b = budget or RecoveryBudget()
        limit_records = max_records if max_records is not None else b.max_input_records
        limit_bytes = max_bytes if max_bytes is not None else b.max_input_bytes
        max_payload_bytes = b.max_payload_bytes

        output_file.parent.mkdir(parents=True, exist_ok=True)
        unreadable: list[str] = []
        clean = 0
        partial = 0
        corrupt = 0
        total_records = 0
        total_bytes = 0
        is_partial = False

        # Finite resource bound: total forensic copy size must not exceed limit_bytes
        total_copy_bytes = sum(
            f.stat().st_size for f in catalog_dir.glob("*.sqlite3*") if f.is_file()
        )
        if total_copy_bytes > limit_bytes:
            raise SalvageError(
                f"Suspect catalog total size {total_copy_bytes} exceeds recovery budget max_input_bytes {limit_bytes}"
            )

        # Forensic preservation: create isolated working copy of suspect files
        # under stop fence or exclusive writer lock so concurrent writers cannot cross the cut
        with (
            _file_gate(catalog_dir / "p1-stop-fence.lock", exclusive=False)
            if is_catalog_stopped(catalog_dir)
            else catalog_gate(catalog_dir, exclusive=True)
        ):
            with tempfile.TemporaryDirectory() as forensic_tmp:
                forensic_dir = Path(forensic_tmp)
                for f in catalog_dir.glob("*.sqlite3*"):
                    if f.is_file():
                        shutil.copy2(f, forensic_dir / f.name)

                temp_out = (
                    output_file.parent / f"{output_file.name}.tmp.{uuid.uuid4().hex}"
                )
                with temp_out.open("w", encoding="utf-8") as out_f:
                    core_db = forensic_dir / "core.sqlite3"
                    if core_db.exists():
                        (
                            c_cnt,
                            c_bytes,
                            c_unread,
                            c_cl,
                            c_pt,
                            c_cr,
                            c_stopped,
                        ) = self._salvage_store_stream(
                            core_db,
                            "core",
                            out_f,
                            max_records=limit_records,
                            max_bytes=limit_bytes,
                            max_payload_bytes=max_payload_bytes,
                            records_offset=total_records,
                            bytes_offset=total_bytes,
                        )
                        total_records += c_cnt
                        total_bytes += c_bytes
                        unreadable.extend(c_unread)
                        clean += c_cl
                        partial += c_pt
                        corrupt += c_cr
                        if c_stopped:
                            is_partial = True

                    ctx_db = forensic_dir / "context.sqlite3"
                    if ctx_db.exists() and not is_partial:
                        rem_records = limit_records - total_records
                        rem_bytes = limit_bytes - total_bytes
                        if rem_records > 0 and rem_bytes > 0:
                            (
                                cx_cnt,
                                cx_bytes,
                                cx_unread,
                                cx_cl,
                                cx_pt,
                                cx_cr,
                                cx_stopped,
                            ) = self._salvage_store_stream(
                                ctx_db,
                                "context",
                                out_f,
                                max_records=limit_records,
                                max_bytes=limit_bytes,
                                max_payload_bytes=max_payload_bytes,
                                records_offset=total_records,
                                bytes_offset=total_bytes,
                            )
                            total_records += cx_cnt
                            total_bytes += cx_bytes
                            unreadable.extend(cx_unread)
                            clean += cx_cl
                            partial += cx_pt
                            corrupt += cx_cr
                            if cx_stopped:
                                is_partial = True

                _fsync_file(temp_out)
                os.replace(temp_out, output_file)
                _fsync_dir(output_file.parent)

        if corrupt > 0 or len(unreadable) > 0:
            is_partial = True

        return SalvageReceipt(
            catalog_path=str(catalog_dir),
            candidate_count=total_records,
            clean_count=clean,
            partial_count=partial,
            corrupt_count=corrupt,
            unreadable_scope=unreadable,
            output_file=str(output_file),
            partial=is_partial,
        )

    def _salvage_store_stream(
        self,
        db_path: Path,
        store_name: str,
        out_f,
        max_records: int,
        max_bytes: int,
        max_payload_bytes: int,
        records_offset: int,
        bytes_offset: int,
    ) -> tuple[int, int, list[str], int, int, int, bool]:
        unreadable: list[str] = []
        clean = 0
        partial = 0
        corrupt = 0
        written_records = 0
        written_bytes = 0
        stopped_due_to_limits = False

        conn = None
        try:
            try:
                conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
                register_functions(conn)
                tables = [
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                ]
            except Exception as e:
                unreadable.append(f"{store_name}:sqlite_schema ({e})")
                return 0, 0, unreadable, 0, 0, 1, False

            for table in tables:
                if (records_offset + written_records) >= max_records:
                    stopped_due_to_limits = True
                    break
                if (bytes_offset + written_bytes) >= max_bytes:
                    stopped_due_to_limits = True
                    break

                try:
                    if store_name == "core" and table == "retained_metadata":
                        cursor = conn.execute(
                            "SELECT object_format, full_oid, physical_copy_uuidv4, native_type, size, digest_sha256, "
                            "(CASE WHEN length(body) > ? THEN NULL ELSE body END) AS body FROM retained_metadata",
                            (max_payload_bytes,),
                        )
                    elif store_name == "core" and table == "retained_notes":
                        cursor = conn.execute(
                            "SELECT object_format, full_oid, physical_copy_uuidv4, size, digest_sha256, "
                            "capture_origin_uuidv4, capture_uuidv4, root, target, path, proof_bundle, "
                            "(CASE WHEN length(body) > ? THEN NULL ELSE body END) AS body FROM retained_notes",
                            (max_payload_bytes,),
                        )
                    else:
                        cursor = conn.execute(f'SELECT * FROM "{table}"')
                    columns = [d[0] for d in cursor.description]

                    while row := cursor.fetchone():
                        if (records_offset + written_records) >= max_records:
                            stopped_due_to_limits = True
                            break
                        if (bytes_offset + written_bytes) >= max_bytes:
                            stopped_due_to_limits = True
                            break

                        row_dict = dict(zip(columns, row))

                        # Classify candidate and format payload preserving exact bytes
                        c_type = CandidateType.GIT_METADATA
                        c_id = ""
                        payload: dict = {}
                        cap_origin = None
                        cap_id = None
                        orig_provenance = None
                        extraction_prov = {"store": store_name, "table": table}

                        if store_name == "core" and table == "retained_metadata":
                            c_type = CandidateType.RETAINED_BODY
                            c_id = f"{row_dict.get('object_format')}:{row_dict.get('full_oid')}:{row_dict.get('physical_copy_uuidv4')}"
                            raw_body = row_dict.get("body")
                            body_len = (
                                row_dict.get("size")
                                if row_dict.get("size") is not None
                                else (
                                    len(raw_body) if isinstance(raw_body, bytes) else 0
                                )
                            )
                            if raw_body is None and body_len > max_payload_bytes:
                                cand_record = {
                                    "candidate_id": c_id,
                                    "candidate_type": c_type.value,
                                    "capture_origin_uuidv4": None,
                                    "capture_uuidv4": None,
                                    "extraction_provenance": extraction_prov,
                                    "payload": {
                                        "object_format": row_dict.get("object_format"),
                                        "full_oid": row_dict.get("full_oid"),
                                        "size": row_dict.get("size"),
                                    },
                                    "extraction_status": ExtractionStatus.PARTIAL.value,
                                    "error": f"Payload size {body_len} exceeds limit {max_payload_bytes}",
                                }
                                line = json.dumps(cand_record) + "\n"
                                out_f.write(line)
                                written_records += 1
                                written_bytes += len(line.encode("utf-8"))
                                partial += 1
                                continue

                            payload = {
                                "object_format": row_dict.get("object_format"),
                                "full_oid": row_dict.get("full_oid"),
                                "physical_copy_uuidv4": row_dict.get(
                                    "physical_copy_uuidv4"
                                ),
                                "native_type": row_dict.get("native_type"),
                                "size": row_dict.get("size"),
                                "digest_sha256": row_dict.get("digest_sha256"),
                                "body_base64": base64.b64encode(raw_body).decode(
                                    "ascii"
                                )
                                if isinstance(raw_body, bytes)
                                else None,
                            }
                        elif store_name == "core" and table == "retained_notes":
                            c_type = CandidateType.NOTES_MAPPING
                            c_id = f"{row_dict.get('object_format')}:{row_dict.get('full_oid')}:{row_dict.get('physical_copy_uuidv4')}"
                            cap_origin = (
                                str(row_dict.get("capture_origin_uuidv4"))
                                if row_dict.get("capture_origin_uuidv4")
                                else None
                            )
                            cap_id = (
                                str(row_dict.get("capture_uuidv4"))
                                if row_dict.get("capture_uuidv4")
                                else None
                            )
                            raw_body = row_dict.get("body")
                            body_len = (
                                row_dict.get("size")
                                if row_dict.get("size") is not None
                                else (
                                    len(raw_body) if isinstance(raw_body, bytes) else 0
                                )
                            )
                            if raw_body is None and body_len > max_payload_bytes:
                                cand_record = {
                                    "candidate_id": c_id,
                                    "candidate_type": c_type.value,
                                    "capture_origin_uuidv4": cap_origin,
                                    "capture_uuidv4": cap_id,
                                    "extraction_provenance": extraction_prov,
                                    "payload": {
                                        "object_format": row_dict.get("object_format"),
                                        "full_oid": row_dict.get("full_oid"),
                                        "size": row_dict.get("size"),
                                    },
                                    "extraction_status": ExtractionStatus.PARTIAL.value,
                                    "error": f"Notes body size {body_len} exceeds limit {max_payload_bytes}",
                                }
                                line = json.dumps(cand_record) + "\n"
                                out_f.write(line)
                                written_records += 1
                                written_bytes += len(line.encode("utf-8"))
                                partial += 1
                                continue

                            payload = {
                                "object_format": row_dict.get("object_format"),
                                "full_oid": row_dict.get("full_oid"),
                                "physical_copy_uuidv4": row_dict.get(
                                    "physical_copy_uuidv4"
                                ),
                                "native_type": "blob",
                                "size": row_dict.get("size"),
                                "digest_sha256": row_dict.get("digest_sha256"),
                                "capture_origin_uuidv4": cap_origin,
                                "capture_uuidv4": cap_id,
                                "root": row_dict.get("root"),
                                "target": row_dict.get("target"),
                                "path": row_dict.get("path"),
                                "proof_bundle": row_dict.get("proof_bundle"),
                                "body_base64": base64.b64encode(raw_body).decode(
                                    "ascii"
                                )
                                if isinstance(raw_body, bytes)
                                else None,
                            }
                            # Preserve original Capture source and nominated ref if present in captures table
                            try:
                                cap_row = conn.execute(
                                    "SELECT source, ref FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? AND root=?",
                                    (
                                        cap_origin,
                                        cap_id,
                                        row_dict.get("object_format"),
                                        row_dict.get("root"),
                                    ),
                                ).fetchone()
                                if cap_row:
                                    payload["source"] = cap_row[0]
                                    payload["ref"] = _decode_native_ref(cap_row[1])
                            except Exception:
                                pass
                        elif store_name == "core" and table == "captures":
                            c_type = CandidateType.GIT_METADATA
                            c_id = f"{row_dict.get('capture_origin_uuidv4')}:{row_dict.get('capture_uuidv4')}"
                            cap_origin = (
                                str(row_dict.get("capture_origin_uuidv4"))
                                if row_dict.get("capture_origin_uuidv4")
                                else None
                            )
                            cap_id = (
                                str(row_dict.get("capture_uuidv4"))
                                if row_dict.get("capture_uuidv4")
                                else None
                            )
                            payload = dict(row_dict)
                        elif store_name == "context" and table == "text_bodies":
                            c_type = CandidateType.CONTEXT_DOCUMENT
                            c_id = str(row_dict.get("sha256"))
                            payload = {
                                "sha256": row_dict.get("sha256"),
                                "text_value": row_dict.get("text_value"),
                            }
                        else:
                            if store_name == "context":
                                c_type = CandidateType.CONTEXT_RESOURCE
                            else:
                                c_type = CandidateType.GIT_METADATA

                            c_id = str(uuid.uuid4())
                            if "capture_origin_uuidv4" in row_dict and row_dict.get(
                                "capture_origin_uuidv4"
                            ):
                                cap_origin = str(row_dict.get("capture_origin_uuidv4"))
                            if "capture_uuidv4" in row_dict and row_dict.get(
                                "capture_uuidv4"
                            ):
                                cap_id = str(row_dict.get("capture_uuidv4"))

                            # Extract original domain provenance if available
                            if "provenance_json" in row_dict and row_dict.get(
                                "provenance_json"
                            ):
                                try:
                                    orig_provenance = json.loads(
                                        str(row_dict["provenance_json"])
                                    )
                                except Exception:
                                    orig_provenance = {
                                        "raw": str(row_dict["provenance_json"])
                                    }
                            elif "provenance" in row_dict and row_dict.get(
                                "provenance"
                            ):
                                orig_provenance = {"value": row_dict["provenance"]}

                            for k, v in row_dict.items():
                                if isinstance(v, bytes):
                                    payload[f"{k}_base64"] = base64.b64encode(v).decode(
                                        "ascii"
                                    )
                                else:
                                    payload[k] = v

                        cand_record = {
                            "candidate_id": c_id,
                            "candidate_type": c_type.value,
                            "capture_origin_uuidv4": cap_origin,
                            "capture_uuidv4": cap_id,
                            "extraction_provenance": extraction_prov,
                            "provenance": orig_provenance,
                            "payload": payload,
                            "extraction_status": ExtractionStatus.CLEAN.value,
                            "error": None,
                        }

                        line = json.dumps(cand_record) + "\n"
                        line_bytes = len(line.encode("utf-8"))

                        if (bytes_offset + written_bytes + line_bytes) > max_bytes:
                            stopped_due_to_limits = True
                            break

                        out_f.write(line)
                        written_records += 1
                        written_bytes += line_bytes
                        clean += 1
                except Exception as e:
                    unreadable.append(f"{store_name}:{table} ({e})")
                    corrupt += 1
        finally:
            if conn:
                conn.close()

        return (
            written_records,
            written_bytes,
            unreadable,
            clean,
            partial,
            corrupt,
            stopped_due_to_limits,
        )

    def restore_backup(
        self,
        backup_path: Path,
        destination_dir: Path,
        expected_repository_uuidv4: str,
    ) -> RestoreReceipt:
        backup_path = Path(backup_path)
        destination_dir = Path(destination_dir)

        if not backup_path.exists():
            raise RestoreValidationError(f"Backup path {backup_path} does not exist")

        manifest_file = backup_path / "manifest.json"
        manifest_sha_file = backup_path / "manifest.json.sha256"

        if not manifest_file.exists() or not manifest_sha_file.exists():
            raise RestoreValidationError(
                f"Backup manifest or sha256 missing at {backup_path}"
            )

        # Verify no unexpected files exist in backup root directory
        actual_root_files = {p.name for p in backup_path.iterdir() if p.is_file()}
        allowed_root_files = {"manifest.json", "manifest.json.sha256"}
        if actual_root_files != allowed_root_files:
            raise RestoreValidationError(
                f"Unexpected files in backup root directory: {actual_root_files - allowed_root_files}"
            )

        # Verify manifest hash
        expected_manifest_sha = manifest_sha_file.read_text(encoding="utf-8").split()[0]
        actual_manifest_sha = _sha256_file(manifest_file)
        if expected_manifest_sha != actual_manifest_sha:
            raise RestoreValidationError(
                f"Manifest SHA-256 tampering detected: expected {expected_manifest_sha}, got {actual_manifest_sha}"
            )

        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception as e:
            raise RestoreValidationError(f"Manifest JSON parsing failed: {e}") from e

        if manifest_data.get("manifest_version") != 1:
            raise RestoreValidationError(
                f"Unsupported manifest version: {manifest_data.get('manifest_version')}"
            )

        scope_val = manifest_data.get("scope")
        if scope_val not in (BackupScope.GIT_ONLY.value, BackupScope.PAIRED.value):
            raise RestoreValidationError(f"Unsupported backup scope: {scope_val}")
        scope = BackupScope(scope_val)

        repo_uuid = manifest_data.get("repository_uuidv4")
        if repo_uuid != expected_repository_uuidv4:
            raise RestoreValidationError(
                f"Repository UUID mismatch: expected {expected_repository_uuidv4}, got {repo_uuid}"
            )

        manifest_inst_uuid = manifest_data.get("catalog_instance_uuidv4")
        if not manifest_inst_uuid or not uuid4(str(manifest_inst_uuid)):
            raise RestoreValidationError(
                f"Invalid or missing catalog_instance_uuidv4 in manifest: {manifest_inst_uuid}"
            )

        stores = manifest_data.get("stores", {})
        expected_store_names = (
            {"core"} if scope == BackupScope.GIT_ONLY else {"core", "context"}
        )
        if set(stores.keys()) != expected_store_names:
            raise RestoreValidationError(
                f"Declared stores {set(stores.keys())} do not match expected scope {scope_val} stores {expected_store_names}"
            )

        backup_resolved = backup_path.resolve()
        for name, info in stores.items():
            store_rel = info.get("path", "")
            rel_p = Path(store_rel)
            if rel_p.is_absolute() or ".." in rel_p.parts:
                raise RestoreValidationError(
                    f"Path traversal detected in manifest store path: {store_rel}"
                )

        # Verify no undeclared store files exist in stores/
        stores_dir = backup_path / "stores"
        if stores_dir.exists():
            actual_store_files = {
                p.relative_to(backup_path).as_posix()
                for p in stores_dir.iterdir()
                if p.is_file()
                and not p.name.endswith("-wal")
                and not p.name.endswith("-shm")
            }
            declared_store_files = {info["path"] for info in stores.values()}
            if actual_store_files != declared_store_files:
                raise RestoreValidationError(
                    f"Unexpected or undeclared files in stores directory: {actual_store_files - declared_store_files}"
                )

        overall_hasher = hashlib.sha256()

        for name in sorted(stores.keys()):
            info = stores[name]
            store_rel = info["path"]
            rel_p = Path(store_rel)

            store_file = backup_path / store_rel
            if store_file.is_symlink():
                raise RestoreValidationError(
                    f"Symlink store forbidden in backup: {store_file}"
                )

            if not store_file.resolve().is_relative_to(backup_resolved):
                raise RestoreValidationError(
                    f"Path escape detected in store path: {store_rel}"
                )

            if not store_file.exists():
                raise RestoreValidationError(
                    f"Store file missing from backup: {store_file}"
                )
            if store_file.stat().st_nlink > 1:
                raise RestoreValidationError(
                    f"Hardlink forbidden for store file: {store_file}"
                )
            if store_file.stat().st_size != info["bytes"]:
                raise RestoreValidationError(
                    f"Store file size mismatch for {name}: expected {info['bytes']}, got {store_file.stat().st_size}"
                )
            actual_sha = _sha256_file(store_file)
            if actual_sha != info["sha256"]:
                raise RestoreValidationError(
                    f"Store SHA-256 mismatch for {name}: expected {info['sha256']}, got {actual_sha}"
                )
            overall_hasher.update(actual_sha.encode("ascii"))

            # Verify declared schema fingerprint against trusted compiled expectations
            expected_fp = p1_schema_fingerprint(name)
            if info.get("schema_fingerprint") != expected_fp:
                raise RestoreValidationError(
                    f"Declared schema fingerprint for {name} does not match expected P1 target schema: declared {info.get('schema_fingerprint')}, expected {expected_fp}"
                )

        # Verify overall checksum
        recomputed_overall_sha = overall_hasher.hexdigest()
        if recomputed_overall_sha != manifest_data.get("overall_sha256"):
            raise RestoreValidationError(
                f"Overall backup SHA-256 mismatch: recorded {manifest_data.get('overall_sha256')}, recomputed {recomputed_overall_sha}"
            )

        if destination_dir.exists() or destination_dir.is_symlink():
            raise RestoreValidationError(
                f"Destination directory {destination_dir} already exists; no-overwrite invariant requires fresh destination"
            )

        staging_dir = (
            destination_dir.parent / f"{destination_dir.name}.tmp.{uuid.uuid4().hex}"
        )
        staging_dir.mkdir(parents=True, exist_ok=False)

        revalidated_stores = []
        try:
            # Copy stores
            dst_core = staging_dir / "core.sqlite3"
            shutil.copy2(backup_path / stores["core"]["path"], dst_core)
            _fsync_file(dst_core)
            revalidated_stores.append("core")

            dst_ctx = None
            if "context" in stores:
                dst_ctx = staging_dir / "context.sqlite3"
                shutil.copy2(backup_path / stores["context"]["path"], dst_ctx)
                _fsync_file(dst_ctx)
                revalidated_stores.append("context")

            # Deep domain revalidation on restored physical databases
            try:
                core_summary = self._validate_and_summarize_core(dst_core)
                context_summary = (
                    self._validate_and_summarize_context(dst_ctx)
                    if dst_ctx
                    else RetainedByteSummary()
                )
            except BackupValidationError as e:
                raise RestoreValidationError(
                    f"Restored database failed domain validation: {e}"
                ) from e

            # Verify paired store identity consistency
            core_repo_uuid, core_inst_uuid = self._extract_identities(dst_core, "core")
            if core_repo_uuid != expected_repository_uuidv4:
                raise RestoreValidationError(
                    f"Restored core repository UUID mismatch: expected {expected_repository_uuidv4}, got {core_repo_uuid}"
                )
            if core_inst_uuid != manifest_inst_uuid:
                raise RestoreValidationError(
                    f"Restored core catalog instance UUID mismatch: manifest {manifest_inst_uuid} vs actual {core_inst_uuid}"
                )
            if dst_ctx:
                ctx_repo_uuid, ctx_inst_uuid = self._extract_identities(
                    dst_ctx, "context"
                )
                if core_repo_uuid != ctx_repo_uuid or core_inst_uuid != ctx_inst_uuid:
                    raise RestoreValidationError(
                        f"Paired store identity mismatch: Core ({core_repo_uuid}, {core_inst_uuid}) vs Context ({ctx_repo_uuid}, {ctx_inst_uuid})"
                    )

            total_retained = (
                core_summary.total_retained_bytes + context_summary.total_retained_bytes
            )

            # Reconcile restored retained byte summary against manifest
            manifest_summary = manifest_data.get("retained_byte_summary", {})
            if (
                core_summary.commit_count != manifest_summary.get("commit_count")
                or core_summary.tree_count != manifest_summary.get("tree_count")
                or core_summary.tag_count != manifest_summary.get("tag_count")
                or core_summary.notes_body_count
                != manifest_summary.get("notes_body_count")
                or total_retained != manifest_summary.get("total_retained_bytes")
            ):
                raise RestoreValidationError(
                    f"Retained byte summary mismatch: manifest {manifest_summary} vs restored "
                    f"(commits={core_summary.commit_count}, trees={core_summary.tree_count}, "
                    f"tags={core_summary.tag_count}, notes={core_summary.notes_body_count}, "
                    f"total_bytes={total_retained})"
                )

            _fsync_dir(staging_dir)

            # Atomic publication with no-overwrite primitive
            try:
                _atomic_publish_noreplace(staging_dir, destination_dir)
            except BackupValidationError as e:
                raise RestoreValidationError(str(e)) from e

            return RestoreReceipt(
                backup_id=manifest_data["backup_id"],
                destination_path=str(destination_dir),
                scope=scope,
                revalidated_stores=revalidated_stores,
                revalidated_retained_bytes=total_retained,
                revalidated_clean=True,
            )
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def merge_salvage(
        self,
        fresh_destination_dir: Path,
        salvage_file: Path,
        budget: RecoveryBudget | None = None,
        request_id: str | None = None,
        *,
        fault_stage: str | None = None,
    ) -> MergeReceipt:
        fresh_destination_dir = Path(fresh_destination_dir)
        salvage_file = Path(salvage_file)

        if not fresh_destination_dir.exists():
            raise RecoveryError(
                f"Fresh destination {fresh_destination_dir} does not exist"
            )
        if not salvage_file.exists():
            raise RecoveryError(f"Salvage file {salvage_file} does not exist")

        req_id = request_id or "default"
        budget_file = fresh_destination_dir / f"p1-recovery-request-{req_id}.json"
        initial_usage = {}
        budget_already_exhausted = False
        if budget_file.exists():
            try:
                state_data = json.loads(budget_file.read_text(encoding="utf-8"))
                initial_usage = state_data.get("cumulative_usage", {})
                budget_already_exhausted = state_data.get("budget_exhausted", False)
            except Exception:
                pass

        b = budget or RecoveryBudget()
        work_budget = RecoveryWorkBudget(
            note_bytes=b.max_payload_bytes,
            work_limits=b.max_work_units,
            initial_usage=initial_usage,
        )

        processed = 0
        admitted = 0
        replayed = 0
        observation = 0
        rejected = 0
        deferred = 0
        unprocessed = 0
        rejections: list[dict] = []
        budget_exhausted = budget_already_exhausted or work_budget.is_exhausted()

        # Connect to fresh core via GitCore production admission interface
        core_db = fresh_destination_dir / "core.sqlite3"
        core = GitCore(core_db)

        # Connect to fresh context if present
        ctx_db = fresh_destination_dir / "context.sqlite3"
        ctx_store = None
        ctx_conn = None
        if ctx_db.exists():
            ctx_conn = p1_connect(ctx_db, "context")
            ctx_store = ContextStore(ctx_conn)

        def _save_budget_state():
            tmp = fresh_destination_dir / f"{budget_file.name}.tmp.{uuid.uuid4().hex}"
            data = {
                "request_id": req_id,
                "cumulative_usage": dict(work_budget.usage),
                "budget_exhausted": budget_exhausted,
                "updated_at_us": int(time.time() * 1_000_000),
            }
            tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            _fsync_file(tmp)
            os.replace(tmp, budget_file)
            _fsync_dir(fresh_destination_dir)

        try:
            with salvage_file.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    processed += 1

                    if budget_exhausted:
                        unprocessed += 1
                        continue

                    line_bytes = len(line.encode("utf-8"))
                    if line_bytes > b.max_payload_bytes:
                        rejected += 1
                        rejections.append(
                            {
                                "line": processed,
                                "reason": f"Line size {line_bytes} exceeds payload limit {b.max_payload_bytes}",
                            }
                        )
                        continue

                    try:
                        record = json.loads(line)
                        _check_json_depth(record, max_depth=b.max_json_depth)
                    except Exception as e:
                        rejected += 1
                        rejections.append(
                            {
                                "line": processed,
                                "reason": f"JSON parse error or depth: {e}",
                            }
                        )
                        continue

                    c_type = record.get("candidate_type")
                    payload = record.get("payload", {})
                    cand_id = record.get("candidate_id", str(processed))

                    # 1. Reject if candidate has corrupt status; treat partial candidate as qualified observation
                    status_val = record.get("extraction_status")
                    if status_val == ExtractionStatus.CORRUPT_BOUNDARY.value:
                        rejected += 1
                        rejections.append(
                            {
                                "candidate_id": cand_id,
                                "reason": "Corrupt boundary extraction status",
                            }
                        )
                        continue
                    if status_val == ExtractionStatus.PARTIAL.value:
                        observation += 1
                        rejections.append(
                            {
                                "candidate_id": cand_id,
                                "reason": f"Partial extraction candidate ({record.get('error') or 'incomplete'}); admitted only as qualified non-authoritative observation",
                            }
                        )
                        continue

                    # 2. Check for required UUIDv4 format if present
                    if record.get("capture_uuidv4"):
                        try:
                            val = uuid.UUID(str(record["capture_uuidv4"]))
                            if val.version != 4:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": "Capture UUID is not version 4",
                                    }
                                )
                                continue
                        except Exception:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Invalid capture UUID format",
                                }
                            )
                            continue

                    # Injected fault stage check after work is performed
                    if fault_stage == "after_partial_work" and processed >= 1:
                        _save_budget_state()
                        raise RecoveryError("Injected failure after partial work")

                    # 3. Admitting Retained Metadata Bodies (commits, trees, tags)
                    if c_type in (
                        CandidateType.RETAINED_BODY.value,
                        "retained_metadata",
                    ):
                        if not payload.get("full_oid") or not payload.get(
                            "native_type"
                        ):
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Missing required object_oid or object_type",
                                }
                            )
                            continue

                        b64_body = payload.get("body_base64")
                        if not b64_body:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Missing body_base64 in retained body candidate",
                                }
                            )
                            continue

                        try:
                            body_bytes = base64.b64decode(b64_body)
                        except Exception as e:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Base64 decoding failed: {e}",
                                }
                            )
                            continue

                        digest_sha = payload.get("digest_sha256")
                        actual_sha = hashlib.sha256(body_bytes).hexdigest()
                        if digest_sha and digest_sha != actual_sha:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Digest SHA-256 mismatch in candidate body",
                                }
                            )
                            continue

                        obj_fmt = payload.get("object_format", "sha1")
                        ntype = payload["native_type"]
                        full_oid = payload["full_oid"]
                        copy_uuid = payload.get("physical_copy_uuidv4")

                        # Check if this exact unit is already admitted in core
                        if copy_uuid:
                            exists = core.sql(
                                "SELECT digest_sha256 FROM retained_metadata WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                                (obj_fmt, full_oid, copy_uuid),
                            )
                            if exists:
                                ex_digest = exists[0][0]
                                if ex_digest == actual_sha:
                                    replayed += 1
                                else:
                                    rejected += 1
                                    rejections.append(
                                        {
                                            "candidate_id": cand_id,
                                            "reason": "Conflicting exact metadata representation for physical copy",
                                        }
                                    )
                                continue
                        else:
                            exists = core.sql(
                                "SELECT physical_copy_uuidv4, digest_sha256 FROM retained_metadata WHERE object_format=? AND full_oid=?",
                                (obj_fmt, full_oid),
                            )
                            if exists and any(row[1] == actual_sha for row in exists):
                                replayed += 1
                                continue
                            copy_uuid = str(uuid.uuid4())

                        try:
                            native = NativeObject(
                                oid=OID(obj_fmt, full_oid),
                                native_type=ntype,
                                body=body_bytes,
                                declared_size=payload.get("size", len(body_bytes)),
                                digest_sha256=actual_sha,
                            )
                            core.admit_metadata(native, copy_uuid, work_budget)
                            admitted += 1
                        except CoreFailure as cf:
                            if cf.code == "BUDGET":
                                budget_exhausted = True
                                unprocessed += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Work budget exhausted: {cf}",
                                    }
                                )
                            else:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Core admission error: {cf}",
                                    }
                                )
                            continue
                        except Exception as e:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Core admission error: {e}",
                                }
                            )
                            continue

                    # 4. Admitting Retained Notes with Role Proof
                    elif c_type in (CandidateType.NOTES_MAPPING.value, "retained_note"):
                        b64_body = payload.get("body_base64")
                        proof_bundle_str = payload.get("proof_bundle")
                        if not b64_body or not proof_bundle_str:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Missing required notes role proof or body",
                                }
                            )
                            continue

                        try:
                            body_bytes = base64.b64decode(b64_body)
                            bundle_data = json.loads(proof_bundle_str)
                            obj_fmt = payload.get("object_format", "sha1")
                            structures = tuple(
                                NativeObject(
                                    oid=OID(obj_fmt, s[0]),
                                    native_type=s[1],
                                    body=bytes.fromhex(s[2]),
                                    declared_size=len(bytes.fromhex(s[2])),
                                    digest_sha256=hashlib.sha256(
                                        bytes.fromhex(s[2])
                                    ).hexdigest(),
                                )
                                for s in bundle_data
                            )
                            repo_uuid, _ = self._extract_identities(core_db, "core")
                            cap_orig_id = payload.get(
                                "capture_origin_uuidv4"
                            ) or record.get("capture_origin_uuidv4")
                            cap_val_id = payload.get("capture_uuidv4") or record.get(
                                "capture_uuidv4"
                            )
                            if not cap_orig_id or not cap_val_id:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": "Missing capture UUIDv4 pair in notes candidate",
                                    }
                                )
                                continue

                            orig_source = payload.get("source")
                            orig_ref = _decode_native_ref(payload.get("ref"))
                            if not orig_source or not orig_ref:
                                cap_query = core.sql(
                                    "SELECT source, ref FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=? AND object_format=? AND root=?",
                                    (
                                        cap_orig_id,
                                        cap_val_id,
                                        obj_fmt,
                                        payload["root"],
                                    ),
                                )
                                if cap_query:
                                    orig_source, orig_ref = (
                                        cap_query[0][0],
                                        _decode_native_ref(cap_query[0][1]),
                                    )

                            if not orig_source or not orig_ref:
                                observation += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": "Cannot establish original Capture binding; withheld from authoritative admission as qualified observation",
                                    }
                                )
                                continue

                            existing_cap = core.sql(
                                "SELECT repository_uuidv4, source, ref, object_format, root FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                                (cap_orig_id, cap_val_id),
                            )
                            if existing_cap:
                                ex_repo, ex_source, ex_ref, ex_fmt, ex_root = (
                                    existing_cap[0]
                                )
                                if (
                                    ex_source,
                                    _decode_native_ref(ex_ref),
                                    ex_fmt,
                                    ex_root,
                                ) != (
                                    orig_source,
                                    orig_ref,
                                    obj_fmt,
                                    payload["root"],
                                ):
                                    rejected += 1
                                    rejections.append(
                                        {
                                            "candidate_id": cand_id,
                                            "reason": f"Conflicting immutable Capture binding: existing ({ex_source}, {_decode_native_ref(ex_ref)}) vs candidate ({orig_source}, {orig_ref})",
                                        }
                                    )
                                    continue
                            else:
                                cap = Capture(
                                    cap_orig_id,
                                    cap_val_id,
                                    repo_uuid,
                                    orig_source,
                                    orig_ref,
                                    OID(obj_fmt, payload["root"]),
                                )
                                core.admit_capture(cap)

                            cap = Capture(
                                cap_orig_id,
                                cap_val_id,
                                repo_uuid,
                                orig_source,
                                orig_ref,
                                OID(obj_fmt, payload["root"]),
                            )
                            proof = NotesProof(
                                capture=cap,
                                target=OID(obj_fmt, payload["target"]),
                                note=OID(obj_fmt, payload["full_oid"]),
                                path=payload["path"],
                                structures=structures,
                            )
                            copy_uuid = payload.get("physical_copy_uuidv4")

                            # Check if already admitted
                            if copy_uuid:
                                exists = core.sql(
                                    "SELECT digest_sha256 FROM retained_notes WHERE object_format=? AND full_oid=? AND physical_copy_uuidv4=?",
                                    (obj_fmt, payload["full_oid"], copy_uuid),
                                )
                                if exists:
                                    ex_digest = exists[0][0]
                                    actual_sha = hashlib.sha256(body_bytes).hexdigest()
                                    if ex_digest == actual_sha:
                                        replayed += 1
                                    else:
                                        rejected += 1
                                        rejections.append(
                                            {
                                                "candidate_id": cand_id,
                                                "reason": "Conflicting exact notes representation for physical copy",
                                            }
                                        )
                                    continue
                            else:
                                exists = core.sql(
                                    "SELECT digest_sha256 FROM retained_notes WHERE object_format=? AND full_oid=?",
                                    (obj_fmt, payload["full_oid"]),
                                )
                                actual_sha = hashlib.sha256(body_bytes).hexdigest()
                                if exists and any(
                                    row[0] == actual_sha for row in exists
                                ):
                                    replayed += 1
                                    continue
                                observation += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": "Missing original physical copy UUID; withheld from authoritative admission",
                                    }
                                )
                                continue

                            native_note = NativeObject(
                                oid=OID(obj_fmt, payload["full_oid"]),
                                native_type="blob",
                                body=body_bytes,
                                declared_size=payload.get("size", len(body_bytes)),
                                digest_sha256=hashlib.sha256(body_bytes).hexdigest(),
                            )
                            core.admit_note(proof, native_note, copy_uuid, work_budget)
                            admitted += 1
                        except CoreFailure as cf:
                            if cf.code == "BUDGET":
                                budget_exhausted = True
                                unprocessed += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Work budget exhausted: {cf}",
                                    }
                                )
                            else:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": cand_id,
                                        "reason": f"Notes admission error: {cf}",
                                    }
                                )
                            continue
                        except Exception as e:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Notes admission error: {e}",
                                }
                            )
                            continue

                    # 5. Admitting Context Text Bodies
                    elif c_type in (
                        CandidateType.CONTEXT_DOCUMENT.value,
                        "context_text",
                    ):
                        if not ctx_store:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Context store not present in destination",
                                }
                            )
                            continue

                        text_val = payload.get("text_value")
                        if text_val is None:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Missing text_value in context candidate",
                                }
                            )
                            continue

                        expected_sha = payload.get("sha256")
                        actual_sha = hashlib.sha256(
                            text_val.encode("utf-8")
                        ).hexdigest()
                        if expected_sha and expected_sha != actual_sha:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": "Text body SHA-256 mismatch",
                                }
                            )
                            continue

                        # Check if already admitted
                        exists = ctx_conn.execute(
                            "SELECT 1 FROM text_bodies WHERE sha256=?", (actual_sha,)
                        ).fetchone()
                        if exists:
                            replayed += 1
                            continue

                        try:
                            ctx_store.text(text_val)
                            admitted += 1
                        except Exception as e:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Context admission error: {e}",
                                }
                            )
                            continue

                    # 6. Admitting Git Metadata Objects (repositories, git_objects, captures)
                    elif c_type == CandidateType.GIT_METADATA.value:
                        prov_tbl = record.get("extraction_provenance", {}).get(
                            "table"
                        ) or record.get("provenance", {}).get("table")
                        try:
                            if (
                                prov_tbl == "repositories"
                                and "repository_uuidv4" in payload
                            ):
                                repo_id = payload["repository_uuidv4"]
                                exists = core.sql(
                                    "SELECT 1 FROM repositories WHERE repository_uuidv4=?",
                                    (repo_id,),
                                )
                                if exists:
                                    replayed += 1
                                else:
                                    core.admit_repository(repo_id)
                                    admitted += 1
                            elif prov_tbl == "git_objects" and "full_oid" in payload:
                                obj_f = payload.get("object_format", "sha1")
                                f_oid = payload["full_oid"]
                                exists = core.sql(
                                    "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                                    (obj_f, f_oid),
                                )
                                if exists:
                                    replayed += 1
                                else:
                                    core.admit_object(OID(obj_f, f_oid))
                                    admitted += 1
                            elif prov_tbl == "captures":
                                cap_orig = payload.get("capture_origin_uuidv4")
                                cap_id = payload.get("capture_uuidv4")
                                repo_id = payload.get("repository_uuidv4")
                                src = payload.get("source")
                                rf = payload.get("ref")
                                rf = _decode_native_ref(payload.get("ref"))
                                obj_f = payload.get("object_format", "sha1")
                                rt = payload.get("root")
                                if not (
                                    cap_orig
                                    and cap_id
                                    and repo_id
                                    and src
                                    and rf
                                    and rt
                                ):
                                    rejected += 1
                                    rejections.append(
                                        {
                                            "candidate_id": cand_id,
                                            "reason": "Missing required field in captures candidate",
                                        }
                                    )
                                    continue
                                existing_cap = core.sql(
                                    "SELECT repository_uuidv4, source, ref, object_format, root FROM captures WHERE capture_origin_uuidv4=? AND capture_uuidv4=?",
                                    (cap_orig, cap_id),
                                )
                                if existing_cap:
                                    ex_repo, ex_source, ex_ref, ex_fmt, ex_root = (
                                        existing_cap[0]
                                    )
                                    if (
                                        ex_source,
                                        _decode_native_ref(ex_ref),
                                        ex_fmt,
                                        ex_root,
                                    ) == (
                                        src,
                                        rf,
                                        obj_f,
                                        rt,
                                    ):
                                        replayed += 1
                                    else:
                                        rejected += 1
                                        rejections.append(
                                            {
                                                "candidate_id": cand_id,
                                                "reason": "Conflicting immutable Capture binding",
                                            }
                                        )
                                else:
                                    core.admit_capture(
                                        Capture(
                                            cap_orig,
                                            cap_id,
                                            repo_id,
                                            src,
                                            rf,
                                            OID(obj_f, rt),
                                        )
                                    )
                                    admitted += 1
                            else:
                                # Candidate is accepted as a qualified recovery observation without authoritative mutation
                                observation += 1
                        except Exception as e:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": cand_id,
                                    "reason": f"Metadata admission error: {e}",
                                }
                            )
                            continue

                    else:
                        # Unknown or unhandled candidate type
                        rejected += 1
                        rejections.append(
                            {
                                "candidate_id": cand_id,
                                "reason": f"Unknown candidate type: {c_type}",
                            }
                        )
        finally:
            _save_budget_state()
            if ctx_conn:
                ctx_conn.close()

        return MergeReceipt(
            destination_path=str(fresh_destination_dir),
            candidates_processed=processed,
            admitted_units=admitted,
            rejected_units=rejected,
            replayed_units=replayed,
            observation_units=observation,
            deferred_units=deferred,
            unprocessed_units=unprocessed,
            rejections=rejections,
        )

    def activate(
        self,
        fresh_catalog_dir: Path,
        target_locator_path: Path,
        *,
        fault_stage: str | None = None,
    ) -> ActivationReceipt:
        fresh_catalog_dir = Path(fresh_catalog_dir)
        target_locator_path = Path(target_locator_path)

        if not fresh_catalog_dir.exists():
            raise ActivationError(
                f"Fresh catalog directory {fresh_catalog_dir} does not exist"
            )

        if fault_stage == "before_validation":
            raise ActivationError("Injected failure before validation")

        core_db = fresh_catalog_dir / "core.sqlite3"
        if not core_db.exists():
            raise ActivationError("Fresh catalog is missing core.sqlite3")

        # Validate core
        self._validate_and_summarize_core(core_db)
        repo_uuid, inst_uuid = self._extract_identities(core_db, "core")

        if fault_stage == "between_core_and_context":
            raise ActivationError("Injected failure between core and context")

        # Validate context if present
        ctx_db = fresh_catalog_dir / "context.sqlite3"
        if ctx_db.exists():
            self._validate_and_summarize_context(ctx_db)
            ctx_repo_uuid, ctx_inst_uuid = self._extract_identities(ctx_db, "context")
            if repo_uuid != ctx_repo_uuid or inst_uuid != ctx_inst_uuid:
                raise ActivationError(
                    f"Catalog activation identity mismatch: Core ({repo_uuid}, {inst_uuid}) vs Context ({ctx_repo_uuid}, {ctx_inst_uuid})"
                )

        # Reconstruct Operational and Search cleanly from scratch from compiled P1 DDL
        op_db = fresh_catalog_dir / "operational.sqlite3"
        if op_db.exists():
            op_db.unlink()
        p1_init(op_db, "operational", repo_uuid, inst_uuid)
        _fsync_file(op_db)

        search_db = fresh_catalog_dir / "search.sqlite3"
        if search_db.exists():
            search_db.unlink()
        p1_init(search_db, "search", repo_uuid, inst_uuid)
        _fsync_file(search_db)

        _fsync_dir(fresh_catalog_dir)

        if fault_stage == "after_operational_init":
            raise ActivationError("Injected failure after operational initialization")

        # Atomic locator update
        target_locator_path.parent.mkdir(parents=True, exist_ok=True)
        activated_catalog_path = str(fresh_catalog_dir)

        if fault_stage == "during_locator_replacement":
            raise ActivationError("Injected failure during locator replacement")

        if target_locator_path.exists():
            if target_locator_path.is_symlink():
                tmp_link = target_locator_path.parent / f"active.tmp.{uuid.uuid4().hex}"
                tmp_link.symlink_to(fresh_catalog_dir.resolve())
                os.replace(tmp_link, target_locator_path)
                _fsync_dir(target_locator_path.parent)
                activated_catalog_path = str(target_locator_path)
            elif target_locator_path.is_file():
                locator_data = {
                    "active_catalog_path": str(fresh_catalog_dir.resolve()),
                    "activated_at_us": int(time.time() * 1_000_000),
                    "repository_uuidv4": repo_uuid,
                    "catalog_instance_uuidv4": inst_uuid,
                }
                tmp_loc = (
                    target_locator_path.parent
                    / f"{target_locator_path.name}.tmp.{uuid.uuid4().hex}"
                )
                tmp_loc.write_text(
                    json.dumps(locator_data, indent=2) + "\n", encoding="utf-8"
                )
                _fsync_file(tmp_loc)
                os.replace(tmp_loc, target_locator_path)
                _fsync_dir(target_locator_path.parent)
                activated_catalog_path = str(fresh_catalog_dir.resolve())
            else:
                # Target path already exists as regular directory; no-overwrite requires keeping suspect intact
                locator_file = (
                    target_locator_path.parent / "active_catalog_instance.json"
                )
                locator_data = {
                    "active_catalog_path": str(fresh_catalog_dir.resolve()),
                    "activated_at_us": int(time.time() * 1_000_000),
                    "repository_uuidv4": repo_uuid,
                    "catalog_instance_uuidv4": inst_uuid,
                }
                tmp_loc = (
                    locator_file.parent
                    / f"active_catalog_instance.tmp.{uuid.uuid4().hex}.json"
                )
                tmp_loc.write_text(
                    json.dumps(locator_data, indent=2) + "\n", encoding="utf-8"
                )
                _fsync_file(tmp_loc)
                os.replace(tmp_loc, locator_file)
                _fsync_dir(locator_file.parent)
                activated_catalog_path = str(fresh_catalog_dir.resolve())
        else:
            try:
                target_locator_path.symlink_to(fresh_catalog_dir.resolve())
                _fsync_dir(target_locator_path.parent)
                activated_catalog_path = str(target_locator_path)
            except OSError:
                _atomic_publish_noreplace(fresh_catalog_dir, target_locator_path)
                _fsync_dir(target_locator_path.parent)
                activated_catalog_path = str(target_locator_path)

        return ActivationReceipt(
            activated_catalog_path=activated_catalog_path,
            source_backup_id="restored",
            reconstructed_stores=["operational", "search"],
            timestamp_us=int(time.time() * 1_000_000),
            clean_operational=True,
            search_derivative_state="initialized_empty",
        )
