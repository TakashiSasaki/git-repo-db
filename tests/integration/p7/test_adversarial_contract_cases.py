"""Exhaustive integration tests for the 18 P7 adversarial and data-integrity requirements under ADR 0026."""

from __future__ import annotations

import concurrent.futures
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.core_recovery import _sha256_file, is_catalog_stopped
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_core import Core
from repo_catalog.adapters.sqlite.p1_schema import (
    connect as p1_connect,
)
from repo_catalog.adapters.sqlite.p1_schema import (
    initialize,
    register_functions,
)
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.p1_core import (
    CoreFailure,
)
from repo_catalog.domain.recovery import (
    ActivationError,
    BackupScope,
    BackupValidationError,
    CandidateType,
    CatalogStoppedError,
    CorruptionDetectedError,
    ExtractionStatus,
    RecoveryBudget,
    RestoreValidationError,
)
from tests.integration.p7.conftest import make_commit, make_tree


def test_case_01_real_commit_survives_backup_and_restore(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 1: A real retained commit survives backup/restore exactly."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case1_backup"
    receipt = service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )
    assert receipt.verified_clean
    assert receipt.manifest.retained_byte_summary.commit_count == 1

    restore_dest = tmp_path / "restored_case1"
    restore_receipt = service.restore_backup(backup_path, restore_dest, repo_uuid)
    assert restore_receipt.revalidated_clean

    # Inspect restored core database directly
    conn = sqlite3.connect(
        f"file:{(restore_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    rows = conn.execute(
        "SELECT object_format, object_oid, native_type, body, size, digest_sha256 FROM retained_metadata WHERE native_type='commit'"
    ).fetchall()
    conn.close()

    assert len(rows) == 1
    fmt, oid, ntype, body, size, digest = rows[0]
    assert ntype == "commit"
    assert len(body) == size
    assert hashlib.sha256(body).hexdigest() == digest
    assert b"Initial commit" in body


def test_case_02_retained_byte_modified_without_digest_update_detected(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 2: A retained byte modified without updating its recorded digest is detected."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case2_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.GIT_ONLY
    )

    core_file = backup_path / "stores" / "core.sqlite3"
    conn = sqlite3.connect(str(core_file))
    register_functions(conn)
    conn.execute("PRAGMA ignore_check_constraints = ON;")
    conn.execute("DROP TRIGGER IF EXISTS p1_immutable_retained_metadata_update;")
    row = conn.execute(
        "SELECT object_oid, body FROM retained_metadata WHERE native_type='commit'"
    ).fetchone()
    object_oid, body = row
    tampered_body = b"X" + body[1:]
    conn.execute(
        "UPDATE retained_metadata SET body=? WHERE object_oid=?",
        (tampered_body, object_oid),
    )
    conn.execute(
        "CREATE TRIGGER p1_immutable_retained_metadata_update BEFORE UPDATE ON retained_metadata BEGIN SELECT RAISE(ABORT,'immutable core fact'); END;"
    )
    conn.commit()
    conn.close()

    # Recalculate store SHA-256 and update manifest so file-level hash checks pass
    new_core_sha = _sha256_file(core_file)
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["stores"]["core"]["sha256"] = new_core_sha
    manifest_data["stores"]["core"]["bytes"] = core_file.stat().st_size
    overall_h = hashlib.sha256()
    for s in sorted(manifest_data["stores"].keys()):
        overall_h.update(manifest_data["stores"][s]["sha256"].encode("ascii"))
    manifest_data["overall_sha256"] = overall_h.hexdigest()
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    # Restore must detect the domain digest mismatch during deep validation
    restore_dest = tmp_path / "restored_case2"
    with pytest.raises(RestoreValidationError, match="SHA-256 digest mismatch"):
        service.restore_backup(backup_path, restore_dest, repo_uuid)


def test_case_03_forged_backup_with_recalculated_manifest_sha_rejected(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 3: A forged backup with recalculated manifest SHA-256 but invalid domain bytes is rejected."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case3_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.GIT_ONLY
    )

    core_file = backup_path / "stores" / "core.sqlite3"
    conn = sqlite3.connect(str(core_file))
    register_functions(conn)
    conn.execute("PRAGMA ignore_check_constraints = ON;")
    conn.execute("DROP TRIGGER IF EXISTS p1_immutable_retained_metadata_update;")
    conn.execute(
        "UPDATE retained_metadata SET size = size + 100 WHERE native_type='commit'"
    )
    conn.execute(
        "CREATE TRIGGER p1_immutable_retained_metadata_update BEFORE UPDATE ON retained_metadata BEGIN SELECT RAISE(ABORT,'immutable core fact'); END;"
    )
    conn.commit()
    conn.close()

    # Recalculate file hash and update manifest
    new_core_sha = _sha256_file(core_file)
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["stores"]["core"]["sha256"] = new_core_sha
    manifest_data["stores"]["core"]["bytes"] = core_file.stat().st_size
    overall_h = hashlib.sha256()
    for s in sorted(manifest_data["stores"].keys()):
        overall_h.update(manifest_data["stores"][s]["sha256"].encode("ascii"))
    manifest_data["overall_sha256"] = overall_h.hexdigest()
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    restore_dest = tmp_path / "restored_case3"
    with pytest.raises(RestoreValidationError, match="Size mismatch"):
        service.restore_backup(backup_path, restore_dest, repo_uuid)


def test_case_04_verified_notes_body_survives_recovery(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 4: An actual verified Notes body survives recovery."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case4_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    restore_dest = tmp_path / "restored_case4"
    service.restore_backup(backup_path, restore_dest, repo_uuid)

    conn = sqlite3.connect(
        f"file:{(restore_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    rows = conn.execute(
        "SELECT object_format, object_oid, body, size, digest_sha256 FROM ref_retained_notes"
    ).fetchall()
    role_count = conn.execute("SELECT count(*) FROM notes_mapping_evidence").fetchone()[
        0
    ]
    conn.close()

    assert len(rows) == 1
    fmt, oid, body, size, digest = rows[0]
    assert len(body) == size
    assert hashlib.sha256(body).hexdigest() == digest
    assert b"Reviewed-by: Admin" in body
    assert role_count == 1


def test_case_06_context_text_survives_with_verified_sha256(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 6: Actual Context text survives with verified SHA-256."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case6_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    restore_dest = tmp_path / "restored_case6"
    service.restore_backup(backup_path, restore_dest, repo_uuid)

    ctx_conn = p1_connect(restore_dest / "context.sqlite3", "context")
    rows = ctx_conn.execute("SELECT sha256, text_value FROM text_bodies").fetchall()
    ctx_conn.close()

    assert len(rows) == 1
    sha256_val, text_val = rows[0]
    assert text_val == "Sample review document content for PR #1"
    assert hashlib.sha256(text_val.encode("utf-8")).hexdigest() == sha256_val


def test_case_07_valid_salvage_causes_observable_new_rows(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 7: Valid salvage candidates cause observable new rows in the restored catalog."""
    import base64

    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case7_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    fresh_dest = tmp_path / "restored_case7"
    service.restore_backup(backup_path, fresh_dest, repo_uuid)

    # Inspect initial commit count
    conn = sqlite3.connect(
        f"file:{(fresh_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    init_commits = conn.execute(
        "SELECT count(*) FROM retained_metadata WHERE native_type='commit'"
    ).fetchone()[0]
    tree_object_oid = conn.execute(
        "SELECT object_oid FROM retained_metadata WHERE native_type='tree'"
    ).fetchone()[0]
    conn.close()

    # Create a valid new commit to salvage
    new_commit = make_commit(
        "sha1", tree_object_oid, [], message="Second salvaged commit\n"
    )
    salvage_file = tmp_path / "valid_salvage.jsonl"
    cand = {
        "candidate_id": f"sha1:{new_commit.object_oid.object_oid}:{uuid4()}",
        "candidate_type": CandidateType.RETAINED_BODY.value,
        "capture_origin_uuidv4": None,
        "capture_uuidv4": None,
        "provenance": {"store": "core", "table": "retained_metadata"},
        "payload": {
            "object_format": "sha1",
            "object_oid": new_commit.object_oid.object_oid,
            "physical_copy_uuidv4": str(uuid4()),
            "native_type": "commit",
            "size": len(new_commit.body),
            "digest_sha256": hashlib.sha256(new_commit.body).hexdigest(),
            "body_base64": base64.b64encode(new_commit.body).decode("ascii"),
        },
        "extraction_status": ExtractionStatus.CLEAN.value,
        "error": None,
    }
    salvage_file.write_text(json.dumps(cand) + "\n", encoding="utf-8")

    merge_receipt = service.merge_salvage(fresh_dest, salvage_file)
    assert merge_receipt.admitted_units == 1
    assert merge_receipt.rejected_units == 0

    # Verify observable new row exists in restored core
    conn = sqlite3.connect(
        f"file:{(fresh_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    post_commits = conn.execute(
        "SELECT count(*) FROM retained_metadata WHERE native_type='commit'"
    ).fetchone()[0]
    new_row = conn.execute(
        "SELECT object_oid, body FROM retained_metadata WHERE object_oid=?",
        (new_commit.object_oid.object_oid,),
    ).fetchone()
    conn.close()

    assert post_commits == init_commits + 1
    assert new_row is not None
    assert new_row[0] == new_commit.object_oid.object_oid
    assert b"Second salvaged commit" in new_row[1]


def test_case_08_rejected_candidates_cause_no_mutation(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 8: Rejected candidates cause no authoritative mutation."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case8_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    fresh_dest = tmp_path / "restored_case8"
    service.restore_backup(backup_path, fresh_dest, repo_uuid)

    conn = sqlite3.connect(
        f"file:{(fresh_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    init_rows = conn.execute("SELECT count(*) FROM retained_metadata").fetchone()[0]
    conn.close()

    # Salvage file containing corrupt candidate and invalid capture candidate
    salvage_file = tmp_path / "bad_candidates.jsonl"
    corrupt_cands = [
        {
            "candidate_id": "bad-1",
            "candidate_type": CandidateType.RETAINED_BODY.value,
            "extraction_status": ExtractionStatus.CORRUPT_BOUNDARY.value,
            "payload": {},
        },
        {
            "candidate_id": "bad-2",
            "candidate_type": CandidateType.GIT_METADATA.value,
            "capture_uuidv4": "not-valid-uuid",
            "extraction_status": ExtractionStatus.CLEAN.value,
            "payload": {},
        },
    ]
    salvage_file.write_text(
        "\n".join(json.dumps(c) for c in corrupt_cands) + "\n", encoding="utf-8"
    )

    merge_receipt = service.merge_salvage(fresh_dest, salvage_file)
    assert merge_receipt.admitted_units == 0
    assert merge_receipt.rejected_units == 2

    # Verify zero rows mutated
    conn = sqlite3.connect(
        f"file:{(fresh_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    post_rows = conn.execute("SELECT count(*) FROM retained_metadata").fetchone()[0]
    conn.close()

    assert init_rows == post_rows


def test_case_10_read_only_salvage_preserves_db_and_wal(synthetic_catalog, tmp_path):
    """Case 10: Read-only salvage preserves the original SQLite DB/WAL/journal evidence."""
    service = RecoveryService()
    core_path = synthetic_catalog / "core.sqlite3"
    wal_path = synthetic_catalog / "core.sqlite3-wal"
    shm_path = synthetic_catalog / "core.sqlite3-shm"

    # Ensure WAL and SHM exist with active uncheckpointed state by disabling autocheckpoint
    # and keeping the connection active during the read-only salvage
    conn = sqlite3.connect(str(core_path))
    register_functions(conn)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA wal_autocheckpoint = 0;")
    wal_repository = str(uuid4())
    conn.execute(
        "INSERT INTO repositories (repository_uuidv4) VALUES (?)", (wal_repository,)
    )
    conn.commit()

    assert wal_path.exists(), "WAL file must exist after committed transaction"
    assert wal_path.stat().st_size > 0, "WAL file must have non-zero size"

    pre_core_sha = _sha256_file(core_path)
    pre_wal_sha = _sha256_file(wal_path)
    pre_shm_sha = _sha256_file(shm_path) if shm_path.exists() else None

    salvage_file = tmp_path / "salvage_case10.jsonl"
    service.extract_salvage(synthetic_catalog, salvage_file)

    # Recheck source files: extract_salvage must not touch source files
    assert _sha256_file(core_path) == pre_core_sha
    assert _sha256_file(wal_path) == pre_wal_sha
    if pre_shm_sha is not None:
        assert _sha256_file(shm_path) == pre_shm_sha

    # Verify that candidates were extracted from the WAL-committed state
    lines = [
        json.loads(line)
        for line in salvage_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    wal_test_cands = [
        c
        for c in lines
        if c.get("extraction_provenance", {}).get("table") == "repositories"
        and c.get("payload", {}).get("repository_uuidv4") == wal_repository
    ]
    assert len(wal_test_cands) == 1

    conn.close()


def test_case_11_writer_cannot_cross_declared_backup_cut(synthetic_catalog, tmp_path):
    """Case 11: A writer cannot cross the declared paired backup cut."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case11_backup"

    callback_executed = False

    def cut_callback() -> None:
        nonlocal callback_executed
        callback_executed = True
        # Verify cross-process writer exclusion: while backup cut is held, non-blocking lock fails
        lock_file = synthetic_catalog / "p1-writer.lock"
        assert lock_file.exists(), "p1-writer.lock must exist during backup cut"
        fd = lock_file.open("r")
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            fd.close()

    # Normal backup succeeds cleanly and executes snapshot cut under lock
    receipt = service.create_consistent_backup(
        synthetic_catalog,
        backup_path,
        scope=BackupScope.PAIRED,
        snapshot_cut_callback=cut_callback,
    )
    assert callback_executed
    assert receipt.verified_clean


def test_case_12_concurrent_destination_creation_no_overwrite(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 12: Concurrent destination creation cannot be overwritten."""
    service = RecoveryService()

    # 1. Concurrent racing backup publishers to the exact same destination
    race_backup_path = tmp_path / "race_backup_dest"
    num_threads = 4

    def run_concurrent_backup():
        return service.create_consistent_backup(
            synthetic_catalog, race_backup_path, scope=BackupScope.GIT_ONLY
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(run_concurrent_backup) for _ in range(num_threads)]
        successes = 0
        conflicts = 0
        for f in futures:
            try:
                receipt = f.result()
                if receipt.verified_clean:
                    successes += 1
            except BackupValidationError as e:
                if "already exists" in str(e):
                    conflicts += 1
                else:
                    raise

    assert successes == 1, (
        f"Expected exactly 1 winning backup publisher, got {successes}"
    )
    assert conflicts == num_threads - 1, (
        f"Expected {num_threads - 1} no-overwrite rejections, got {conflicts}"
    )
    assert (race_backup_path / "manifest.json").exists()

    # 2. Concurrent racing restore publishers to the exact same destination
    race_restore_path = tmp_path / "race_restore_dest"

    def run_concurrent_restore():
        return service.restore_backup(race_backup_path, race_restore_path, repo_uuid)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(run_concurrent_restore) for _ in range(num_threads)]
        successes = 0
        conflicts = 0
        for f in futures:
            try:
                receipt = f.result()
                if receipt.revalidated_clean:
                    successes += 1
            except RestoreValidationError as e:
                if "already exists" in str(e):
                    conflicts += 1
                else:
                    raise

    assert successes == 1, (
        f"Expected exactly 1 winning restore publisher, got {successes}"
    )
    assert conflicts == num_threads - 1, (
        f"Expected {num_threads - 1} no-overwrite restore rejections, got {conflicts}"
    )
    assert (race_restore_path / "core.sqlite3").exists()


def test_case_13_symlink_and_path_traversal_rejection(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 13: Symlink and path traversal inputs cannot escape the recovery staging root."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case13_backup"
    service.create_consistent_backup(synthetic_catalog, backup_path)

    # 1. Path traversal in manifest
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["stores"]["core"]["path"] = "../../etc/passwd"
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    with pytest.raises(RestoreValidationError, match="Path traversal detected"):
        service.restore_backup(backup_path, tmp_path / "dest13_traversal", repo_uuid)

    # 2. Symlink store file
    valid_backup = tmp_path / "backups" / "symlink_backup"
    service.create_consistent_backup(synthetic_catalog, valid_backup)
    core_file = valid_backup / "stores" / "core.sqlite3"
    outside_target = tmp_path / "outside_target.sqlite3"
    shutil.copy2(core_file, outside_target)
    core_file.unlink()
    core_file.symlink_to(outside_target)

    # Update manifest sha
    man_file = valid_backup / "manifest.json"
    man_sha = valid_backup / "manifest.json.sha256"
    man_sha.write_text(_sha256_file(man_file) + "  manifest.json\n", encoding="utf-8")

    with pytest.raises(RestoreValidationError, match="Symlink store forbidden"):
        service.restore_backup(valid_backup, tmp_path / "dest13_symlink", repo_uuid)


def test_case_14_interrupted_activation_no_publication(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 14: An interrupted activation cannot publish a partially validated destination."""
    service = RecoveryService()
    active_locator = tmp_path / "active_catalog_link"
    active_locator.symlink_to(synthetic_catalog.resolve())

    # Create invalid fresh destination missing core.sqlite3
    invalid_fresh = tmp_path / "invalid_fresh_dest"
    invalid_fresh.mkdir()

    with pytest.raises(ActivationError, match="missing core.sqlite3"):
        service.activate_catalog(invalid_fresh, active_locator)

    # Active locator is untouched and still points to original catalog
    assert active_locator.resolve() == synthetic_catalog.resolve()


def test_case_15_stop_survives_process_restart_and_operational_loss(
    synthetic_catalog,
):
    """Case 15: The catalog stop survives process restart and loss of Operational/Search."""
    service1 = RecoveryService()
    service1.stop_suspect_catalog(
        synthetic_catalog, "Authoritative byte corruption stop"
    )

    # Delete Operational and Search
    op_path = synthetic_catalog / "operational.sqlite3"
    search_path = synthetic_catalog / "search.sqlite3"
    if op_path.exists():
        op_path.unlink()
    if search_path.exists():
        search_path.unlink()

    # Fresh service instance
    service2 = RecoveryService()
    assert service2.is_stopped(synthetic_catalog)
    with pytest.raises(CatalogStoppedError):
        service2.assert_not_stopped(synthetic_catalog)


def test_case_16_p5_p6_reject_stopped_catalog(synthetic_catalog):
    """Case 16: Existing P5/P6 readers and writers actually reject the stopped catalog."""
    service = RecoveryService()
    service.stop_suspect_catalog(synthetic_catalog, "Test fencing on stopped catalog")

    # P2-P6 Core connection must fail with RECOVERY_STOP
    core_path = synthetic_catalog / "core.sqlite3"
    with pytest.raises(CoreFailure) as exc_info:
        Core(core_path)
    assert exc_info.value.code == "RECOVERY_STOP"


def test_case_17_sha1_and_sha256_git_formats(tmp_path):
    """Case 17: Both SHA-1 and SHA-256 Git formats are exercised."""
    service = RecoveryService()
    repo_256 = str(uuid4())
    inst_256 = str(uuid4())
    catalog_256 = tmp_path / "catalog_sha256"
    catalog_256.mkdir()

    core_path = catalog_256 / "core.sqlite3"
    initialize(core_path, "core", repo_256, inst_256)
    initialize(catalog_256 / "context.sqlite3", "context", repo_256, inst_256)
    initialize(catalog_256 / "operational.sqlite3", "operational", repo_256, inst_256)
    initialize(catalog_256 / "search.sqlite3", "search", repo_256, inst_256)

    # Populate sha256 objects
    core = GitCore(core_path)
    core.admit_repository(repo_256)
    budget = UnlimitedWorkBudget()

    tree_256 = make_tree("sha256", [(b"100644", b"file.txt", "a" * 64)])
    commit_256 = make_commit(
        "sha256", tree_256.object_oid.object_oid, [], message="SHA-256 commit\n"
    )

    core.admit_metadata(tree_256, str(uuid4()), budget)
    core.admit_metadata(commit_256, str(uuid4()), budget)

    # Backup and restore sha256 catalog
    backup_path = tmp_path / "backup_sha256"
    receipt = service.create_consistent_backup(
        catalog_256, backup_path, scope=BackupScope.PAIRED
    )
    assert receipt.verified_clean
    assert receipt.manifest.retained_byte_summary.commit_count == 1

    restore_dest = tmp_path / "restored_sha256"
    rest_receipt = service.restore_backup(backup_path, restore_dest, repo_256)
    assert rest_receipt.revalidated_clean


def test_case_18_wrong_ddl_with_valid_file_hashes_rejected(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 18: A database with tampered DDL but recomputed file and manifest hashes is rejected."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case18_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.GIT_ONLY
    )

    core_file = backup_path / "stores" / "core.sqlite3"
    conn = sqlite3.connect(str(core_file))
    register_functions(conn)
    # Alter DDL by adding an unauthorized table
    conn.execute("CREATE TABLE rogue_table (id INT PRIMARY KEY);")
    conn.commit()
    conn.close()

    # Recalculate file hash and update manifest so file-level checks pass
    new_core_sha = _sha256_file(core_file)
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["stores"]["core"]["sha256"] = new_core_sha
    manifest_data["stores"]["core"]["bytes"] = core_file.stat().st_size
    overall_h = hashlib.sha256()
    for s in sorted(manifest_data["stores"].keys()):
        overall_h.update(manifest_data["stores"][s]["sha256"].encode("ascii"))
    manifest_data["overall_sha256"] = overall_h.hexdigest()
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    restore_dest = tmp_path / "restored_case18"
    with pytest.raises(
        RestoreValidationError, match="schema differs from packaged target"
    ):
        service.restore_backup(backup_path, restore_dest, repo_uuid)


def test_case_19_inconsistent_store_identities_rejected(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 19: Stores with inconsistent catalog_instance_uuidv4 are rejected during restore."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case19_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    ctx_file = backup_path / "stores" / "context.sqlite3"
    conn = sqlite3.connect(str(ctx_file))
    register_functions(conn)
    conn.execute("PRAGMA ignore_check_constraints = ON;")
    conn.execute("DROP TRIGGER IF EXISTS p1_immutable_store_identity_update;")
    # Tamper catalog_instance_uuidv4 in context store_identity
    conn.execute("UPDATE store_identity SET catalog_instance_uuidv4=?", (str(uuid4()),))
    conn.execute(
        "CREATE TRIGGER p1_immutable_store_identity_update BEFORE UPDATE ON store_identity BEGIN SELECT RAISE(ABORT,'immutable context fact'); END;"
    )
    conn.commit()
    conn.close()

    # Recompute file and manifest hashes
    new_ctx_sha = _sha256_file(ctx_file)
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["stores"]["context"]["sha256"] = new_ctx_sha
    manifest_data["stores"]["context"]["bytes"] = ctx_file.stat().st_size
    overall_h = hashlib.sha256()
    for s in sorted(manifest_data["stores"].keys()):
        overall_h.update(manifest_data["stores"][s]["sha256"].encode("ascii"))
    manifest_data["overall_sha256"] = overall_h.hexdigest()
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    restore_dest = tmp_path / "restored_case19"
    with pytest.raises(RestoreValidationError, match="Paired store identity mismatch"):
        service.restore_backup(backup_path, restore_dest, repo_uuid)


def test_case_20_wrong_native_oid_rejected(synthetic_catalog, tmp_path, repo_uuid):
    """Case 20: Tampered native OID calculation mismatch is detected during restore."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case20_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.GIT_ONLY
    )

    core_file = backup_path / "stores" / "core.sqlite3"
    conn = sqlite3.connect(str(core_file))
    register_functions(conn)
    conn.execute("PRAGMA ignore_check_constraints = ON;")
    conn.execute("DROP TRIGGER IF EXISTS p1_immutable_retained_metadata_update;")
    row = conn.execute(
        "SELECT object_oid, body FROM retained_metadata WHERE native_type='commit'"
    ).fetchone()
    object_oid, body = row
    tampered_body = b"X" + body[1:]
    tampered_digest = hashlib.sha256(tampered_body).hexdigest()
    # Update body and digest so digest check passes, but native OID check fails
    conn.execute(
        "UPDATE retained_metadata SET body=?, digest_sha256=? WHERE object_oid=?",
        (tampered_body, tampered_digest, object_oid),
    )
    conn.execute(
        "CREATE TRIGGER p1_immutable_retained_metadata_update BEFORE UPDATE ON retained_metadata BEGIN SELECT RAISE(ABORT,'immutable core fact'); END;"
    )
    conn.commit()
    conn.close()

    # Recompute file and manifest hashes
    new_core_sha = _sha256_file(core_file)
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["stores"]["core"]["sha256"] = new_core_sha
    manifest_data["stores"]["core"]["bytes"] = core_file.stat().st_size
    overall_h = hashlib.sha256()
    for s in sorted(manifest_data["stores"].keys()):
        overall_h.update(manifest_data["stores"][s]["sha256"].encode("ascii"))
    manifest_data["overall_sha256"] = overall_h.hexdigest()
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    restore_dest = tmp_path / "restored_case20"
    with pytest.raises(RestoreValidationError, match="Native OID calculation mismatch"):
        service.restore_backup(backup_path, restore_dest, repo_uuid)


def test_case_21_invalid_context_text_digest_rejected(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 21: Tampered context text payload with mismatched sha256 is detected."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case21_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    ctx_file = backup_path / "stores" / "context.sqlite3"
    conn = sqlite3.connect(str(ctx_file))
    register_functions(conn)
    row = conn.execute("SELECT sha256, text_value FROM text_bodies LIMIT 1").fetchone()
    assert row is not None
    sha, text_val = row
    conn.execute("PRAGMA ignore_check_constraints = ON;")
    conn.execute("DROP TRIGGER IF EXISTS text_bodies_no_update;")
    conn.execute(
        "UPDATE text_bodies SET text_value = ? WHERE sha256 = ?",
        (text_val + " TAMPERED", sha),
    )
    conn.execute(
        "CREATE TRIGGER text_bodies_no_update BEFORE UPDATE ON text_bodies BEGIN SELECT RAISE(ABORT,'immutable Context evidence'); END;"
    )
    conn.commit()
    conn.close()

    # Recompute file and manifest hashes
    new_ctx_sha = _sha256_file(ctx_file)
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["stores"]["context"]["sha256"] = new_ctx_sha
    manifest_data["stores"]["context"]["bytes"] = ctx_file.stat().st_size
    overall_h = hashlib.sha256()
    for s in sorted(manifest_data["stores"].keys()):
        overall_h.update(manifest_data["stores"][s]["sha256"].encode("ascii"))
    manifest_data["overall_sha256"] = overall_h.hexdigest()
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    restore_dest = tmp_path / "restored_case21"
    with pytest.raises(
        RestoreValidationError, match="Context text body SHA-256 mismatch"
    ):
        service.restore_backup(backup_path, restore_dest, repo_uuid)


def test_case_22_inconsistent_core_context_pairing_rejected(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 22: Inconsistent Core/Context scope declaration and store set is rejected."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case22_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    # Change scope to git_only while retaining context in stores map
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["scope"] = BackupScope.GIT_ONLY.value
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8"
    )

    manifest_sha_file = backup_path / "manifest.json.sha256"
    manifest_sha_file.write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    restore_dest = tmp_path / "restored_case22"
    with pytest.raises(RestoreValidationError, match="do not match expected scope"):
        service.restore_backup(backup_path, restore_dest, repo_uuid)


def test_case_23_legitimately_unresolved_context_references_admitted(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 23: Context documents with legitimately unresolved Git references under P3/P5 remain admissible."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case23_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    fresh_dest = tmp_path / "fresh_case23"
    restore_receipt = service.restore_backup(backup_path, fresh_dest, repo_uuid)
    assert restore_receipt.revalidated_clean

    # Salvage candidate referencing an unresolved OID
    salvage_file = tmp_path / "salvage_case23.jsonl"
    cand_sha = hashlib.sha256(b"Unresolved external doc").hexdigest()
    context_cand = {
        "candidate_id": cand_sha,
        "candidate_type": CandidateType.CONTEXT_DOCUMENT.value,
        "capture_origin_uuidv4": str(uuid4()),
        "capture_uuidv4": str(uuid4()),
        "extraction_provenance": {"store": "context", "table": "text_bodies"},
        "payload": {
            "sha256": cand_sha,
            "text_value": "Unresolved external doc",
        },
        "extraction_status": ExtractionStatus.CLEAN.value,
        "error": None,
    }
    salvage_file.write_text(json.dumps(context_cand) + "\n", encoding="utf-8")

    merge_receipt = service.merge_salvage(fresh_dest, salvage_file)
    assert merge_receipt.admitted_units == 1
    assert merge_receipt.rejected_units == 0


def test_case_24_confirmed_source_corruption_stops_catalog_and_raises(
    synthetic_catalog, tmp_path
):
    """Case 24: Confirmed corruption in authoritative source stops catalog and raises CorruptionDetectedError."""
    service = RecoveryService()
    core_path = synthetic_catalog / "core.sqlite3"

    # Intentionally corrupt authoritative stored core database bytes
    conn = sqlite3.connect(str(core_path))
    register_functions(conn)
    conn.execute("PRAGMA ignore_check_constraints = ON;")
    conn.execute("DROP TRIGGER IF EXISTS p1_immutable_retained_metadata_update;")
    row = conn.execute(
        "SELECT object_oid, body FROM retained_metadata WHERE native_type='commit'"
    ).fetchone()
    object_oid, body = row
    tampered_body = b"X" + body[1:]
    conn.execute(
        "UPDATE retained_metadata SET body=? WHERE object_oid=?",
        (tampered_body, object_oid),
    )
    conn.execute(
        "CREATE TRIGGER p1_immutable_retained_metadata_update BEFORE UPDATE ON retained_metadata BEGIN SELECT RAISE(ABORT,'immutable core fact'); END;"
    )
    conn.commit()
    conn.close()

    backup_path = tmp_path / "backups" / "case24_backup"
    with pytest.raises(CorruptionDetectedError):
        service.create_consistent_backup(
            synthetic_catalog, backup_path, scope=BackupScope.PAIRED
        )

    # Assert source catalog is persistently stopped with stop sentinel
    assert is_catalog_stopped(synthetic_catalog)
    stop_file = synthetic_catalog / "p1-recovery-stop.json"
    assert stop_file.exists()


def test_case_25_staging_copy_defect_raises_validation_error_without_stopping_sound_source(
    synthetic_catalog, tmp_path
):
    """Case 25: Isolated staging copy defect raises BackupValidationError without stopping sound source catalog."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case25_backup"

    # Inject damage only to staged files during snapshot cut callback
    def damage_staging():
        for staged_core in backup_path.parent.glob("**/stores/core.sqlite3"):
            conn = sqlite3.connect(str(staged_core))
            register_functions(conn)
            conn.execute("PRAGMA ignore_check_constraints = ON;")
            conn.execute(
                "DROP TRIGGER IF EXISTS p1_immutable_retained_metadata_update;"
            )
            row = conn.execute(
                "SELECT object_oid, body FROM retained_metadata WHERE native_type='commit'"
            ).fetchone()
            object_oid, body = row
            conn.execute(
                "UPDATE retained_metadata SET body=? WHERE object_oid=?",
                (b"X" + body[1:], object_oid),
            )
            conn.execute(
                "CREATE TRIGGER p1_immutable_retained_metadata_update BEFORE UPDATE ON retained_metadata BEGIN SELECT RAISE(ABORT,'immutable core fact'); END;"
            )
            conn.commit()
            conn.close()

    with pytest.raises(BackupValidationError):
        service.create_consistent_backup(
            synthetic_catalog,
            backup_path,
            scope=BackupScope.PAIRED,
            snapshot_cut_callback=damage_staging,
        )

    # Authoritative source catalog MUST remain healthy and unstopped
    assert not is_catalog_stopped(synthetic_catalog)
    assert not (synthetic_catalog / "p1-recovery-stop.json").exists()


def test_case_26_completion_fence_aborts_backup_publication_if_stopped(
    synthetic_catalog, tmp_path
):
    """Case 26: Backup publication fence aborts publication if catalog stops in flight."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case26_backup"

    def stop_during_cut():
        service.stop_suspect_catalog(synthetic_catalog, "Emergency stop during backup")

    with pytest.raises(CatalogStoppedError):
        service.create_consistent_backup(
            synthetic_catalog,
            backup_path,
            scope=BackupScope.PAIRED,
            snapshot_cut_callback=stop_during_cut,
        )

    assert not backup_path.exists()


def test_case_29_cumulative_request_budget_persists_across_retries(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 29: Cumulative request budget persists across retries without resetting."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case29_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )
    fresh_dest = tmp_path / "fresh_case29"
    service.restore_backup(backup_path, fresh_dest, repo_uuid)

    salvage_file = tmp_path / "salvage_case29.jsonl"
    import base64

    conn = sqlite3.connect(
        f"file:{(fresh_dest / 'core.sqlite3').resolve()}?mode=ro", uri=True
    )
    register_functions(conn)
    tree_object_oid = conn.execute(
        "SELECT object_oid FROM retained_metadata WHERE native_type='tree'"
    ).fetchone()[0]
    conn.close()

    commit1 = make_commit("sha1", tree_object_oid, [], message="Commit 1\n")
    cand1 = {
        "candidate_id": f"commit-1-{uuid4()}",
        "candidate_type": CandidateType.RETAINED_BODY.value,
        "capture_origin_uuidv4": None,
        "capture_uuidv4": None,
        "extraction_provenance": {"store": "core", "table": "retained_metadata"},
        "payload": {
            "object_format": "sha1",
            "object_oid": commit1.object_oid.object_oid,
            "physical_copy_uuidv4": str(uuid4()),
            "native_type": "commit",
            "size": len(commit1.body),
            "digest_sha256": hashlib.sha256(commit1.body).hexdigest(),
            "body_base64": base64.b64encode(commit1.body).decode("ascii"),
        },
        "extraction_status": ExtractionStatus.CLEAN.value,
        "error": None,
    }
    salvage_file = tmp_path / "salvage_case29.jsonl"
    salvage_file.write_text(json.dumps(cand1) + "\n", encoding="utf-8")

    # One commit spends its decoded input once in recovery and once again
    # through production Core admission. Preserve allowance for exactly one
    # such candidate, with insufficient remainder for a second decoding.
    budget = RecoveryBudget(max_work_units={"input_bytes": 2 * len(commit1.body) + 30})
    receipt1 = service.merge_salvage(
        fresh_dest, salvage_file, budget=budget, request_id="req-persist-1"
    )
    assert receipt1.admitted_units == 1

    # Check budget state file was written with cumulative usage
    budget_state_file = fresh_dest / "p1-recovery-request-req-persist-1.json"
    assert budget_state_file.exists()
    state_data1 = json.loads(budget_state_file.read_text(encoding="utf-8"))
    assert state_data1["cumulative_usage"]["input_bytes"] >= len(commit1.body)

    # Second commit under the same request_id exhausts budget
    commit2 = make_commit("sha1", tree_object_oid, [], message="Commit 2\n")
    cand2 = {
        "candidate_id": f"commit-2-{uuid4()}",
        "candidate_type": CandidateType.RETAINED_BODY.value,
        "capture_origin_uuidv4": None,
        "capture_uuidv4": None,
        "extraction_provenance": {"store": "core", "table": "retained_metadata"},
        "payload": {
            "object_format": "sha1",
            "object_oid": commit2.object_oid.object_oid,
            "physical_copy_uuidv4": str(uuid4()),
            "native_type": "commit",
            "size": len(commit2.body),
            "digest_sha256": hashlib.sha256(commit2.body).hexdigest(),
            "body_base64": base64.b64encode(commit2.body).decode("ascii"),
        },
        "extraction_status": ExtractionStatus.CLEAN.value,
        "error": None,
    }
    salvage_file2 = tmp_path / "salvage_case29_b.jsonl"
    salvage_file2.write_text(json.dumps(cand2) + "\n", encoding="utf-8")

    receipt2 = service.merge_salvage(
        fresh_dest, salvage_file2, budget=budget, request_id="req-persist-1"
    )
    assert receipt2.unprocessed_units >= 1
    assert receipt2.admitted_units == 0
    state_data2 = json.loads(budget_state_file.read_text(encoding="utf-8"))
    assert state_data2.get("budget_exhausted") is True


def test_case_30_restore_validation_rejects_mismatches_hardlinks_and_extraneous_files(
    synthetic_catalog, tmp_path, repo_uuid
):
    """Case 30: Restore validation rejects mismatched identities, hardlinks, and unexpected root files."""
    service = RecoveryService()
    backup_path = tmp_path / "backups" / "case30_backup"
    service.create_consistent_backup(
        synthetic_catalog, backup_path, scope=BackupScope.PAIRED
    )

    # 1. Hardlink rejection in stores
    hardlink_path = backup_path / "stores" / "core_hl.sqlite3"
    try:
        os.link(backup_path / "stores" / "core.sqlite3", hardlink_path)
        with pytest.raises(
            RestoreValidationError, match="Hardlink forbidden|Unexpected or undeclared"
        ):
            service.restore_backup(backup_path, tmp_path / "dest1", repo_uuid)
    finally:
        if hardlink_path.exists():
            hardlink_path.unlink()

    # 2. Unexpected extraneous file in backup root
    extra_file = backup_path / "unexpected_root_file.txt"
    extra_file.write_text("evil")
    try:
        with pytest.raises(
            RestoreValidationError, match="Unexpected.*files in backup root directory"
        ):
            service.restore_backup(backup_path, tmp_path / "dest2", repo_uuid)
    finally:
        extra_file.unlink()

    # 3. Mismatched catalog instance UUIDv4
    manifest_file = backup_path / "manifest.json"
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest_data["catalog_instance_uuidv4"] = str(uuid4())
    manifest_file.write_text(json.dumps(manifest_data) + "\n", encoding="utf-8")
    (backup_path / "manifest.json.sha256").write_text(
        _sha256_file(manifest_file) + "  manifest.json\n", encoding="utf-8"
    )

    with pytest.raises(RestoreValidationError, match="catalog instance UUID mismatch"):
        service.restore_backup(backup_path, tmp_path / "dest3", repo_uuid)


def test_case_31_recovery_budget_rejects_boolean_negative_and_float_limits():
    """Case 31: RecoveryBudget strictly validates types, rejecting booleans, floats, and negative integers."""
    with pytest.raises(ValueError, match="must be a positive integer"):
        RecoveryBudget(max_input_records=True)

    with pytest.raises(ValueError, match="must be a positive integer"):
        RecoveryBudget(max_input_bytes=False)

    with pytest.raises(ValueError, match="must be a positive integer"):
        RecoveryBudget(max_payload_bytes=-100)

    with pytest.raises(ValueError, match="must be a positive integer"):
        RecoveryBudget(max_json_depth=0)

    with pytest.raises(ValueError, match="must be a positive integer"):
        RecoveryBudget(max_input_records=10.5)

    with pytest.raises(ValueError, match="must be a positive integer"):
        RecoveryBudget(max_work_units={"input_bytes": True})

    with pytest.raises(ValueError, match="must be a positive integer"):
        RecoveryBudget(max_work_units={"metadata_units": -5})
