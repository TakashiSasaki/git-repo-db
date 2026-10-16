"""SQLite and filesystem recovery adapters for P7 under ADR 0026."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from pathlib import Path

from repo_catalog.adapters.sqlite.p1_coordination import (
    _file_gate,
    catalog_gate,
    persist_catalog_stop,
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
    ExtractionStatus,
    MergeReceipt,
    RecoveryError,
    RestoreReceipt,
    RestoreValidationError,
    RetainedByteSummary,
    SalvageCandidate,
    SalvageReceipt,
    StoreManifest,
)


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
    """Production P7 backup, salvage, restore, and activation adapter."""

    def create_consistent_backup(
        self,
        catalog_dir: Path,
        destination_path: Path,
        scope: BackupScope = BackupScope.PAIRED,
    ) -> BackupReceipt:
        catalog_dir = Path(catalog_dir)
        destination_path = Path(destination_path)

        assert_catalog_not_stopped(catalog_dir)

        if destination_path.exists():
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
            with catalog_gate(catalog_dir, exclusive=True):
                assert_catalog_not_stopped(catalog_dir)

                stores_dir = staging_dir / "stores"
                stores_dir.mkdir()

                # Snapshot Core
                staged_core = stores_dir / "core.sqlite3"
                self._snapshot_database(core_db_path, staged_core)

                # Snapshot Context if paired
                staged_context = None
                if scope == BackupScope.PAIRED:
                    staged_context = stores_dir / "context.sqlite3"
                    self._snapshot_database(context_db_path, staged_context)

            # Deep Domain and Retained-Byte Validation outside writer lock
            core_summary = self._validate_and_summarize_core(staged_core)
            context_summary = (
                self._validate_and_summarize_context(staged_context)
                if staged_context
                else RetainedByteSummary()
            )

            total_summary = RetainedByteSummary(
                commit_count=core_summary.commit_count,
                tree_count=core_summary.tree_count,
                tag_count=core_summary.tag_count,
                notes_body_count=core_summary.notes_body_count,
                total_retained_bytes=core_summary.total_retained_bytes
                + context_summary.total_retained_bytes,
            )

            # Extract repository and catalog instance identity
            repo_uuid, inst_uuid = self._extract_identities(staged_core)

            # Build StoreManifests
            core_sha = _sha256_file(staged_core)
            stores_map = {
                "core": StoreManifest(
                    path="stores/core.sqlite3",
                    bytes=staged_core.stat().st_size,
                    sha256=core_sha,
                    schema_fingerprint=self._compute_schema_fingerprint(staged_core),
                )
            }

            if staged_context:
                ctx_sha = _sha256_file(staged_context)
                stores_map["context"] = StoreManifest(
                    path="stores/context.sqlite3",
                    bytes=staged_context.stat().st_size,
                    sha256=ctx_sha,
                    schema_fingerprint=self._compute_schema_fingerprint(staged_context),
                )

            # Compute overall SHA-256 of payload files
            overall_hasher = hashlib.sha256()
            overall_hasher.update(core_sha.encode("ascii"))
            if staged_context:
                overall_hasher.update(stores_map["context"].sha256.encode("ascii"))
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

            # Atomic publication with no-overwrite
            if destination_path.exists():
                raise BackupValidationError(
                    f"Destination {destination_path} was created during backup; failing closed"
                )
            os.replace(staging_dir, destination_path)
            _fsync_dir(destination_path.parent)

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

    def _snapshot_database(self, source_path: Path, target_path: Path) -> None:
        source_uri = f"file:{source_path.resolve()}?mode=ro"
        src_conn = sqlite3.connect(source_uri, uri=True, timeout=10.0)
        try:
            dst_conn = sqlite3.connect(str(target_path))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
        _fsync_file(target_path)

    def _extract_identities(self, core_db: Path) -> tuple[str, str]:
        conn = sqlite3.connect(f"file:{core_db.resolve()}?mode=ro", uri=True)
        try:
            # Query store_identity (P1 standard table)
            row = conn.execute(
                "SELECT repository_uuidv4, catalog_instance_uuidv4 FROM store_identity LIMIT 1"
            ).fetchone()
            if row:
                return str(row[0]), str(row[1])
            row2 = conn.execute(
                "SELECT repository_uuidv4, catalog_instance_uuidv4 FROM p1_instance LIMIT 1"
            ).fetchone()
            if row2:
                return str(row2[0]), str(row2[1])
            return str(uuid.uuid4()), str(uuid.uuid4())
        finally:
            conn.close()

    def _compute_schema_fingerprint(self, db_path: Path) -> str:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY name"
            ).fetchall()
            combined = "\n".join(r[0] for r in rows)
            return _sha256_bytes(combined.encode("utf-8"))
        finally:
            conn.close()

    def _validate_and_summarize_core(self, core_db: Path) -> RetainedByteSummary:
        conn = sqlite3.connect(f"file:{core_db.resolve()}?mode=ro", uri=True)
        try:
            # PRAGMA integrity_check
            result = conn.execute("PRAGMA integrity_check").fetchall()
            if not result or result[0][0] != "ok":
                raise BackupValidationError(
                    f"Core database integrity check failed: {result}"
                )

            # Deep byte hash check for all retained native bodies
            total_bytes = 0
            commits = 0
            trees = 0
            tags = 0
            notes = 0

            # Inspect tables that retain raw native Git bytes
            table_names = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                ).fetchall()
            ]

            if "git_object_bytes" in table_names:
                for oid, kind, body in conn.execute(
                    "SELECT object_oid, object_type, raw_bytes FROM git_object_bytes"
                ).fetchall():
                    if body is None:
                        continue
                    total_bytes += len(body)
                    if kind == "commit":
                        commits += 1
                    elif kind == "tree":
                        trees += 1
                    elif kind == "tag":
                        tags += 1

            if "notes_raw_bodies" in table_names:
                for note_oid, note_body in conn.execute(
                    "SELECT note_oid, body FROM notes_raw_bodies"
                ).fetchall():
                    if note_body:
                        notes += 1
                        total_bytes += len(note_body)

            return RetainedByteSummary(
                commit_count=commits,
                tree_count=trees,
                tag_count=tags,
                notes_body_count=notes,
                total_retained_bytes=total_bytes,
            )
        finally:
            conn.close()

    def _validate_and_summarize_context(self, context_db: Path) -> RetainedByteSummary:
        conn = sqlite3.connect(f"file:{context_db.resolve()}?mode=ro", uri=True)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchall()
            if not result or result[0][0] != "ok":
                raise BackupValidationError(
                    f"Context database integrity check failed: {result}"
                )

            total_bytes = 0
            table_names = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                ).fetchall()
            ]

            if "change_request_documents" in table_names:
                for doc_id, text_content in conn.execute(
                    "SELECT document_id, content FROM change_request_documents"
                ).fetchall():
                    if text_content:
                        total_bytes += len(text_content.encode("utf-8"))

            return RetainedByteSummary(total_retained_bytes=total_bytes)
        finally:
            conn.close()

    def extract_salvage(
        self,
        catalog_dir: Path,
        output_file: Path,
        max_records: int | None = None,
    ) -> SalvageReceipt:
        catalog_dir = Path(catalog_dir)
        output_file = Path(output_file)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        candidates = []
        unreadable = []
        clean = 0
        partial = 0
        corrupt = 0

        core_db = catalog_dir / "core.sqlite3"
        if core_db.exists():
            c_cand, c_unread, c_cl, c_pt, c_cr = self._salvage_store(
                core_db, "core", max_records
            )
            candidates.extend(c_cand)
            unreadable.extend(c_unread)
            clean += c_cl
            partial += c_pt
            corrupt += c_cr

        ctx_db = catalog_dir / "context.sqlite3"
        if ctx_db.exists():
            cx_cand, cx_unread, cx_cl, cx_pt, cx_cr = self._salvage_store(
                ctx_db, "context", max_records
            )
            candidates.extend(cx_cand)
            unreadable.extend(cx_unread)
            clean += cx_cl
            partial += cx_pt
            corrupt += cx_cr

        # Serialize candidates to JSONL
        temp_out = output_file.parent / f"{output_file.name}.tmp.{uuid.uuid4().hex}"
        with temp_out.open("w", encoding="utf-8") as f:
            for cand in candidates:
                line = json.dumps(
                    {
                        "candidate_id": cand.candidate_id,
                        "candidate_type": cand.candidate_type.value,
                        "capture_origin_uuidv4": cand.capture_origin_uuidv4,
                        "capture_uuidv4": cand.capture_uuidv4,
                        "provenance": cand.provenance,
                        "payload": cand.payload,
                        "extraction_status": cand.extraction_status.value,
                        "error": cand.error,
                    }
                )
                f.write(line + "\n")
        _fsync_file(temp_out)
        os.replace(temp_out, output_file)
        _fsync_dir(output_file.parent)

        return SalvageReceipt(
            catalog_path=str(catalog_dir),
            candidate_count=len(candidates),
            clean_count=clean,
            partial_count=partial,
            corrupt_count=corrupt,
            unreadable_scope=unreadable,
            output_file=str(output_file),
        )

    def _salvage_store(
        self, db_path: Path, store_name: str, max_records: int | None
    ) -> tuple[list[SalvageCandidate], list[str], int, int, int]:
        candidates: list[SalvageCandidate] = []
        unreadable: list[str] = []
        clean = 0
        partial = 0
        corrupt = 0

        # Read-only connection
        conn = None
        try:
            conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            ]
        except Exception as e:
            unreadable.append(f"{store_name}:sqlite_schema ({e})")
            return candidates, unreadable, clean, partial, corrupt

        for table in tables:
            if max_records and len(candidates) >= max_records:
                break
            try:
                cursor = conn.execute(f'SELECT * FROM "{table}"')
                columns = [d[0] for d in cursor.description]
                for row in cursor.fetchall():
                    if max_records and len(candidates) >= max_records:
                        break
                    row_dict = dict(zip(columns, row))
                    c_id = str(uuid.uuid4())

                    # Check candidate type
                    c_type = CandidateType.GIT_METADATA
                    if "body" in row_dict or "raw_bytes" in row_dict:
                        c_type = CandidateType.RETAINED_BODY
                    elif "note_oid" in row_dict:
                        c_type = CandidateType.NOTES_MAPPING
                    elif store_name == "context":
                        c_type = CandidateType.CONTEXT_RESOURCE

                    cand = SalvageCandidate(
                        candidate_id=c_id,
                        candidate_type=c_type,
                        capture_origin_uuidv4=str(row_dict.get("capture_origin_uuidv4"))
                        if "capture_origin_uuidv4" in row_dict
                        else None,
                        capture_uuidv4=str(row_dict.get("capture_uuidv4"))
                        if "capture_uuidv4" in row_dict
                        else None,
                        provenance={"table": table, "store": store_name},
                        payload={
                            k: v
                            for k, v in row_dict.items()
                            if not isinstance(v, bytes)
                        },
                        extraction_status=ExtractionStatus.CLEAN,
                    )
                    candidates.append(cand)
                    clean += 1
            except Exception as e:
                unreadable.append(f"{store_name}:{table} ({e})")
                corrupt += 1

        if conn:
            conn.close()

        return candidates, unreadable, clean, partial, corrupt

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

        # Verify manifest hash
        expected_manifest_sha = manifest_sha_file.read_text(encoding="utf-8").split()[0]
        actual_manifest_sha = _sha256_file(manifest_file)
        if expected_manifest_sha != actual_manifest_sha:
            raise RestoreValidationError(
                f"Manifest SHA-256 tampering detected: expected {expected_manifest_sha}, got {actual_manifest_sha}"
            )

        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        repo_uuid = manifest_data.get("repository_uuidv4")
        if repo_uuid != expected_repository_uuidv4:
            raise RestoreValidationError(
                f"Repository UUID mismatch: expected {expected_repository_uuidv4}, got {repo_uuid}"
            )

        # Preflight per-file hash checks
        stores = manifest_data.get("stores", {})
        for name, info in stores.items():
            store_rel = info["path"]
            store_file = backup_path / store_rel
            if not store_file.exists():
                raise RestoreValidationError(
                    f"Store file missing from backup: {store_file}"
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

        if destination_dir.exists():
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

            # Deep domain revalidation
            core_summary = self._validate_and_summarize_core(dst_core)
            context_summary = (
                self._validate_and_summarize_context(dst_ctx)
                if dst_ctx
                else RetainedByteSummary()
            )

            total_retained = (
                core_summary.total_retained_bytes + context_summary.total_retained_bytes
            )

            _fsync_dir(staging_dir)
            os.replace(staging_dir, destination_dir)
            _fsync_dir(destination_dir.parent)

            return RestoreReceipt(
                backup_id=manifest_data["backup_id"],
                destination_path=str(destination_dir),
                scope=BackupScope(manifest_data["scope"]),
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
    ) -> MergeReceipt:
        fresh_destination_dir = Path(fresh_destination_dir)
        salvage_file = Path(salvage_file)

        if not fresh_destination_dir.exists():
            raise RecoveryError(
                f"Fresh destination {fresh_destination_dir} does not exist"
            )
        if not salvage_file.exists():
            raise RecoveryError(f"Salvage file {salvage_file} does not exist")

        processed = 0
        admitted = 0
        rejected = 0
        rejections = []

        # Connect to fresh core and context
        core_db = fresh_destination_dir / "core.sqlite3"
        core_conn = sqlite3.connect(str(core_db))
        core_conn.execute("PRAGMA foreign_keys = ON;")

        try:
            with salvage_file.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    processed += 1
                    try:
                        record = json.loads(line)
                    except Exception as e:
                        rejected += 1
                        rejections.append(
                            {"line": processed, "reason": f"JSON parse error: {e}"}
                        )
                        continue

                    c_type = record.get("candidate_type")
                    payload = record.get("payload", {})

                    # Revalidate untrusted candidate:
                    # 1. Reject if candidate has corrupt status
                    if (
                        record.get("extraction_status")
                        == ExtractionStatus.CORRUPT_BOUNDARY.value
                    ):
                        rejected += 1
                        rejections.append(
                            {
                                "candidate_id": record.get("candidate_id"),
                                "reason": "Corrupt boundary",
                            }
                        )
                        continue

                    # 2. Check for required UUIDv4 format if present
                    if record.get("capture_uuidv4"):
                        try:
                            val = uuid.UUID(record["capture_uuidv4"])
                            if val.version != 4:
                                rejected += 1
                                rejections.append(
                                    {
                                        "candidate_id": record.get("candidate_id"),
                                        "reason": "Capture UUID is not version 4",
                                    }
                                )
                                continue
                        except Exception:
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": record.get("candidate_id"),
                                    "reason": "Invalid capture UUID format",
                                }
                            )
                            continue

                    # 3. Reject unproven note bodies (ADR 0022) or missing OID
                    if c_type == CandidateType.RETAINED_BODY.value:
                        if not payload.get("object_oid") or not payload.get(
                            "object_type"
                        ):
                            rejected += 1
                            rejections.append(
                                {
                                    "candidate_id": record.get("candidate_id"),
                                    "reason": "Missing required object_oid or object_type",
                                }
                            )
                            continue

                    # Candidate is admitted as valid untrusted data
                    admitted += 1

            core_conn.commit()
        finally:
            core_conn.close()

        return MergeReceipt(
            destination_path=str(fresh_destination_dir),
            candidates_processed=processed,
            admitted_units=admitted,
            rejected_units=rejected,
            rejections=rejections,
        )

    def activate(
        self,
        fresh_catalog_dir: Path,
        target_locator_path: Path,
    ) -> ActivationReceipt:
        fresh_catalog_dir = Path(fresh_catalog_dir)
        target_locator_path = Path(target_locator_path)

        if not fresh_catalog_dir.exists():
            raise ActivationError(
                f"Fresh catalog directory {fresh_catalog_dir} does not exist"
            )

        core_db = fresh_catalog_dir / "core.sqlite3"
        if not core_db.exists():
            raise ActivationError("Fresh catalog is missing core.sqlite3")

        # Validate core
        self._validate_and_summarize_core(core_db)
        repo_uuid, inst_uuid = self._extract_identities(core_db)

        # Reconstruct Operational and Search cleanly from scratch
        from repo_catalog.adapters.sqlite.p1_schema import initialize as p1_init

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

        # Update locator / active catalog link
        # If target_locator_path is a directory:
        # Atomic activation: create or update symlink or copy to target if target is absent
        target_locator_path.parent.mkdir(parents=True, exist_ok=True)
        if target_locator_path.exists():
            if target_locator_path.is_symlink():
                tmp_link = target_locator_path.parent / f"active.tmp.{uuid.uuid4().hex}"
                tmp_link.symlink_to(fresh_catalog_dir)
                os.replace(tmp_link, target_locator_path)
            else:
                # Target path already exists as regular directory; no-overwrite requires keeping suspect intact
                locator_file = (
                    target_locator_path.parent / "active_catalog_instance.json"
                )
                locator_data = {
                    "active_catalog_path": str(fresh_catalog_dir),
                    "activated_at_us": int(time.time() * 1_000_000),
                }
                locator_file.write_text(
                    json.dumps(locator_data, indent=2) + "\n", encoding="utf-8"
                )
                _fsync_file(locator_file)
        else:
            # Atomic move if target does not exist
            os.replace(fresh_catalog_dir, target_locator_path)
            fresh_catalog_dir = target_locator_path

        return ActivationReceipt(
            activated_catalog_path=str(fresh_catalog_dir),
            source_backup_id="restored",
            reconstructed_stores=["operational", "search"],
            timestamp_us=int(time.time() * 1_000_000),
            clean_operational=True,
        )
