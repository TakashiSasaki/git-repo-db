"""Physical corruption stays local and never rewrites acquisition evidence."""

import hashlib
import json
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.sqlite import cas_integrity
from repo_catalog.adapters.sqlite.cas_integrity import (
    diagnose_corruption,
    is_quarantined,
    repair_payload,
    stage_verified_payload,
    verify_all,
)
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application import maintenance_service
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.payload import PayloadRef


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "state"
    MaintenanceService(path).init("catalog-text-v1", 32 * 1024 * 1024, 0)
    with Store(path) as value:
        yield value
        assert not value.all("PRAGMA foreign_key_check")
        assert value.one("PRAGMA integrity_check")[0] == "ok"


def corrupt(db, digest, body):
    """Fault injection only: emulate a damaged physical object behind its key."""
    trigger = db.execute(
        "SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'"
    ).fetchone()[0]
    db.execute("DROP TRIGGER stored_bytes_immutable")
    db.execute(
        "UPDATE stored_bytes SET body=?,byte_length=? WHERE sha256=?",
        (body, len(body), digest),
    )
    db.execute(trigger)


def test_scan_records_one_physical_diagnostic_across_representations(store):
    db = store.connection
    ref = intern_payload(db, b"good")
    intern_payload(db, b"good", representation="legacy_normalized")
    corrupt(db, ref.sha256, b"bad!")
    first = verify_all(db)
    revision = store.revision()
    second = verify_all(db)
    assert first["checked"] == second["checked"] == 1
    assert first["corrupt"][0]["previously_quarantined"] is False
    assert second["corrupt"][0]["previously_quarantined"] is True
    assert (
        store.one(
            "SELECT count(*) FROM unresolved_payloads WHERE stored_sha256 IS NOT NULL"
        )[0]
        == 1
    )
    assert store.one("SELECT count(*) FROM payload_quarantine")[0] == 1
    assert store.revision() == revision
    assert store.one("SELECT count(*) FROM payloads")[0] == 2


def test_valid_reacquisition_stages_bytes_and_original_context_without_repair(store):
    db = store.connection
    ref = intern_payload(db, b"good")
    corrupt(db, ref.sha256, b"bad!")
    with pytest.raises(CatalogError) as error:
        with store.transaction():
            intern_payload(db, b"good")
    assert error.value.code == "PAYLOAD_CORRUPTION"
    context = {
        "fetch_uuid": "original-observation",
        "observed_at_us": -1,
        "request": {"page": 2},
    }
    stage_verified_payload(db, b"good", ref, context, reason=error.value.code)
    assert store.one("SELECT body FROM stored_bytes")[0] == b"bad!"
    row = store.one("SELECT body,context_json FROM payload_admission_staging")
    assert row[0] == b"good" and json.loads(row[1]) == context
    assert is_quarantined(db, ref.sha256)


def test_declared_hash_mismatch_is_never_staged(store):
    ref = PayloadRef("decoded_api", hashlib.sha256(b"good").digest())
    with pytest.raises(CatalogError) as error:
        stage_verified_payload(
            store.connection, b"bad", ref, {}, reason="PAYLOAD_CORRUPTION"
        )
    assert error.value.code == "PAYLOAD_DIGEST_MISMATCH"
    assert store.one("SELECT count(*) FROM payload_admission_staging")[0] == 0
    assert store.one("SELECT count(*) FROM unresolved_payloads")[0] == 0


def test_repair_restores_bytes_atomically_retains_diagnostic_and_tracks_recurrence(
    store,
):
    db = store.connection
    ref = intern_payload(db, b"good")
    corrupt(db, ref.sha256, b"bad!")
    first = diagnose_corruption(db, ref.sha256)
    before = store.revision()["publication_seq"]
    repaired = repair_payload(db, ref.sha256, b"good")
    assert repaired["unresolved_payload_id"] == first
    assert not is_quarantined(db, ref.sha256)
    assert store.one("SELECT body FROM stored_bytes")[0] == b"good"
    assert store.revision()["publication_seq"] == before + 1
    assert verify_all(db)["corrupt"] == []
    corrupt(db, ref.sha256, b"bad!")
    second = diagnose_corruption(db, ref.sha256)
    assert second != first
    assert store.one("SELECT count(*) FROM unresolved_payloads")[0] == 2


def test_repair_failure_rolls_back_bytes_quarantine_and_protection_trigger(store):
    db = store.connection
    ref = intern_payload(db, b"good")
    corrupt(db, ref.sha256, b"bad!")
    diagnose_corruption(db, ref.sha256)
    db.execute(
        "CREATE TRIGGER fail_repair BEFORE DELETE ON payload_quarantine BEGIN SELECT RAISE(ABORT,'injected repair interruption'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="injected repair"):
        repair_payload(db, ref.sha256, b"good")
    assert store.one("SELECT body FROM stored_bytes")[0] == b"bad!"
    assert is_quarantined(db, ref.sha256)
    with pytest.raises(sqlite3.IntegrityError, match="Immutable stored bytes"):
        db.execute("UPDATE stored_bytes SET body=X'676F6F64'")


def test_interrupted_scan_keeps_diagnostics_and_next_attempt_starts_over(
    store, monkeypatch
):
    db = store.connection
    refs = [intern_payload(db, raw) for raw in (b"one", b"two")]
    for ref in refs:
        corrupt(db, ref.sha256, b"bad")
    original = cas_integrity._failure
    calls = 0

    def interrupted(row):
        nonlocal calls
        calls += 1
        # First row is checked once by scan and again by diagnosis.
        if calls == 3:
            raise KeyboardInterrupt()
        return original(row)

    monkeypatch.setattr(cas_integrity, "_failure", interrupted)
    with pytest.raises(KeyboardInterrupt):
        verify_all(db)
    assert not db.in_transaction
    assert store.one("SELECT count(*) FROM payload_quarantine")[0] == 1
    monkeypatch.setattr(cas_integrity, "_failure", original)
    assert verify_all(db)["checked"] == 2
    assert store.one("SELECT count(*) FROM payload_quarantine")[0] == 2


def test_full_scan_rejects_a_long_write_transaction(store):
    with store.transaction(), pytest.raises(CatalogError) as error:
        verify_all(store.connection)
    assert error.value.code == "INVALID_TRANSACTION"


def test_verification_uses_existing_nonblocking_writer_lock(store):
    with (
        FileLock(store.path / "locks/writer.lock"),
        pytest.raises(CatalogError) as error,
    ):
        MaintenanceService(store.path).database("verify-payloads", SimpleNamespace())
    assert error.value.code == "WRITER_BUSY"


def test_backup_detects_corruption_and_restore_retains_quarantine(store, tmp_path):
    ref = intern_payload(store.connection, b"good")
    corrupt(store.connection, ref.sha256, b"bad!")
    backup = tmp_path / "backup.sqlite3"
    result = MaintenanceService(store.path).database(
        "backup", SimpleNamespace(output=backup)
    )
    assert set(result.data["manifest"]) == {
        "schema_version",
        "catalog",
        "sha256",
        "configuration",
    }
    destination = tmp_path / "restored"
    MaintenanceService(destination).restore(backup)
    with Store(destination) as restored:
        assert restored.one("SELECT body FROM stored_bytes")[0] == b"bad!"
        assert is_quarantined(restored.connection, ref.sha256)
        assert restored.one("SELECT count(*) FROM unresolved_payloads")[0] == 1
        repair_payload(restored.connection, ref.sha256, b"good")
        assert verify_all(restored.connection)["corrupt"] == []
    assert is_quarantined(store.connection, ref.sha256)


def test_backup_copy_new_corruption_blocks_publication_and_keeps_stage(
    store, tmp_path, monkeypatch
):
    ref = intern_payload(store.connection, b"good")
    original = maintenance_service.verify_all

    def corrupt_copy(db, *, diagnose=True):
        if not diagnose:
            path = db.execute("PRAGMA database_list").fetchone()[2]
            with sqlite3.connect(path, isolation_level=None) as writer:
                corrupt(writer, ref.sha256, b"bad!")
        return original(db, diagnose=diagnose)

    monkeypatch.setattr(maintenance_service, "verify_all", corrupt_copy)
    backup = tmp_path / "backup.sqlite3"
    with pytest.raises(CatalogError) as error:
        MaintenanceService(store.path).database(
            "backup", SimpleNamespace(output=backup)
        )
    assert error.value.code == "BACKUP_INTEGRITY"
    assert not backup.exists()
    assert list(tmp_path.glob(".repo-catalog-backup-*/catalog.sqlite3"))
    assert store.one("SELECT body FROM stored_bytes")[0] == b"good"


def test_interrupted_backup_keeps_incomplete_pair_and_never_overwrites(
    store, tmp_path, monkeypatch
):
    backup = tmp_path / "backup.sqlite3"
    original = maintenance_service.publish_file

    def interrupt_manifest(source, destination):
        if str(destination).endswith(".manifest.json"):
            raise KeyboardInterrupt()
        original(source, destination)

    monkeypatch.setattr(maintenance_service, "publish_file", interrupt_manifest)
    with pytest.raises(KeyboardInterrupt):
        MaintenanceService(store.path).database(
            "backup", SimpleNamespace(output=backup)
        )
    assert backup.exists()
    assert not backup.with_name(backup.name + ".manifest.json").exists()
    assert list(tmp_path.glob(".repo-catalog-backup-*"))
    with pytest.raises(CatalogError, match="new files"):
        MaintenanceService(store.path).database(
            "backup", SimpleNamespace(output=backup)
        )
    with pytest.raises(CatalogError, match="manifest"):
        MaintenanceService(tmp_path / "restore").restore(backup)


def test_restore_failure_and_retry_keep_distinct_stages(store, tmp_path):
    backup = tmp_path / "backup.sqlite3"
    MaintenanceService(store.path).database("backup", SimpleNamespace(output=backup))
    manifest = backup.with_name(backup.name + ".manifest.json")
    value = json.loads(manifest.read_text())
    value["sha256"] = "0" * 64
    manifest.write_text(json.dumps(value))
    for _ in range(2):
        with pytest.raises(CatalogError, match="checksum"):
            MaintenanceService(tmp_path / "restore").restore(backup)
    assert len(list(tmp_path.glob(".repo-catalog-restore-*"))) == 2
    assert not (tmp_path / "restore").exists()


def test_restore_atomic_publish_loser_keeps_stage_and_winner_unchanged(
    store, tmp_path, monkeypatch
):
    backup = tmp_path / "backup.sqlite3"
    MaintenanceService(store.path).database("backup", SimpleNamespace(output=backup))
    destination = tmp_path / "restore"
    original = maintenance_service.publish_directory

    def competing_restore(stage, target):
        target.mkdir()
        (target / "winner").write_text("keep")
        original(stage, target)

    monkeypatch.setattr(maintenance_service, "publish_directory", competing_restore)
    with pytest.raises(CatalogError) as error:
        MaintenanceService(destination).restore(backup)
    assert error.value.code == "DESTINATION_EXISTS"
    assert (destination / "winner").read_text() == "keep"
    assert any(
        (stage / store.config["database"]["filename"]).is_file()
        for stage in tmp_path.glob(".repo-catalog-restore-*")
    )


def test_restore_manifest_cannot_write_outside_its_new_stage(store, tmp_path):
    backup = tmp_path / "backup.sqlite3"
    MaintenanceService(store.path).database("backup", SimpleNamespace(output=backup))
    manifest_path = backup.with_name(backup.name + ".manifest.json")
    manifest = json.loads(manifest_path.read_text())
    protected = tmp_path / "protected"
    protected.write_bytes(b"preserve")
    manifest["configuration"]["database"]["filename"] = "../protected"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(CatalogError, match="escapes"):
        MaintenanceService(tmp_path / "restore").restore(backup)
    assert protected.read_bytes() == b"preserve"


def test_process_death_during_repair_recovers_original_quarantined_bytes(store):
    db = store.connection
    ref = intern_payload(db, b"good")
    corrupt(db, ref.sha256, b"bad!")
    diagnose_corruption(db, ref.sha256)
    db.execute(
        "CREATE TRIGGER crash_repair BEFORE DELETE ON payload_quarantine BEGIN SELECT injected_exit(); END"
    )
    code = """
import os, sys
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.adapters.sqlite.cas_integrity import repair_payload
from repo_catalog.adapters.filesystem.locks import FileLock
with FileLock(sys.argv[1] + '/locks/writer.lock'), Store(sys.argv[1]) as store:
    store.connection.create_function('injected_exit', 0, lambda: os._exit(73))
    repair_payload(store.connection, bytes.fromhex(sys.argv[2]), b'good')
"""
    child = subprocess.run(
        [sys.executable, "-c", code, str(store.path), ref.sha256.hex()],
        capture_output=True,
        text=True,
    )
    assert child.returncode == 73, child.stderr
    # SQLite hot-journal recovery also restores transactional trigger DDL.
    assert store.one("SELECT body FROM stored_bytes")[0] == b"bad!"
    assert is_quarantined(db, ref.sha256)
    assert store.one("SELECT count(*) FROM unresolved_payloads")[0] == 1
    assert store.one("SELECT 1 FROM sqlite_schema WHERE name='stored_bytes_immutable'")
    db.execute("DROP TRIGGER crash_repair")
    assert repair_payload(db, ref.sha256, b"good")["repaired"]


def test_restore_rejects_manifest_claim_for_a_different_catalog(store, tmp_path):
    backup = tmp_path / "backup.sqlite3"
    MaintenanceService(store.path).database("backup", SimpleNamespace(output=backup))
    manifest_path = backup.with_name(backup.name + ".manifest.json")
    manifest = json.loads(manifest_path.read_text())
    manifest["catalog"]["publication_seq"] += 1
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(CatalogError, match="identity differs"):
        MaintenanceService(tmp_path / "restore").restore(backup)
    assert not (tmp_path / "restore").exists()
    assert list(tmp_path.glob(".repo-catalog-restore-*"))
