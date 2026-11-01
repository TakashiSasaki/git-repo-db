"""Positive source-corruption evidence and independent stop/publication cuts."""

import multiprocessing
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.core_recovery import is_catalog_stopped
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.recovery import (
    BackupScope,
    BackupValidationError,
    CatalogStoppedError,
    CorruptionDetectedError,
    SourceIntegrityIndeterminateError,
)


@pytest.mark.parametrize(
    "error",
    [
        sqlite3.OperationalError("database is locked"),
        PermissionError("denied"),
        OSError("interrupted IO"),
        MemoryError("allocation"),
        RuntimeError("unsupported"),
    ],
)
def test_indeterminate_source_does_not_invent_corruption(
    synthetic_catalog, monkeypatch, error
):
    adapter = SQLiteRecoveryAdapter()

    def unavailable(_):
        # Real validators wrap SQLite exceptions; classify the cause as well.
        raise BackupValidationError("validation unavailable") from error

    monkeypatch.setattr(adapter, "_validate_and_summarize_core", unavailable)
    with pytest.raises(SourceIntegrityIndeterminateError, match="Indeterminate"):
        adapter._diagnose_and_stop_if_source_corrupt(
            synthetic_catalog,
            synthetic_catalog / "core.sqlite3",
            "core",
            ValueError("stage"),
        )
    assert not is_catalog_stopped(synthetic_catalog)


def test_real_not_a_database_stops_source(synthetic_catalog, tmp_path):
    (synthetic_catalog / "core.sqlite3").write_bytes(b"not an SQLite database" * 200)
    with pytest.raises(CorruptionDetectedError, match="Confirmed authoritative"):
        RecoveryService().create_consistent_backup(
            synthetic_catalog, tmp_path / "backup"
        )
    assert is_catalog_stopped(synthetic_catalog)
    assert not (tmp_path / "backup").exists()


def test_confirmed_schema_damage_stops_source(synthetic_catalog, tmp_path):
    connection = sqlite3.connect(synthetic_catalog / "core.sqlite3")
    connection.execute("CREATE TABLE unwanted(value)")
    connection.commit()
    connection.close()
    with pytest.raises(CorruptionDetectedError, match="physical_schema"):
        RecoveryService().create_consistent_backup(
            synthetic_catalog, tmp_path / "backup"
        )
    assert is_catalog_stopped(synthetic_catalog)


def test_already_stopped_is_not_rediagnosed(synthetic_catalog):
    service = RecoveryService()
    service.stop_suspect_catalog(synthetic_catalog, "prior incident")
    with pytest.raises(CatalogStoppedError):
        service.adapter._diagnose_and_stop_if_source_corrupt(
            synthetic_catalog,
            synthetic_catalog / "core.sqlite3",
            "core",
            ValueError("stage"),
        )


def test_context_snapshot_failure_revalidates_context(
    synthetic_catalog, tmp_path, monkeypatch
):
    adapter = SQLiteRecoveryAdapter()
    original = adapter._snapshot_database
    diagnosed = []

    def snapshot(source, target):
        if source.name == "context.sqlite3":
            raise sqlite3.OperationalError("context busy")
        original(source, target)

    def diagnose(catalog, source, role, error):
        diagnosed.append((source.name, role))

    monkeypatch.setattr(adapter, "_snapshot_database", snapshot)
    monkeypatch.setattr(adapter, "_diagnose_and_stop_if_source_corrupt", diagnose)
    with pytest.raises(BackupValidationError):
        adapter.create_consistent_backup(synthetic_catalog, tmp_path / "backup")
    assert diagnosed == [("context.sqlite3", "context")]
    assert not is_catalog_stopped(synthetic_catalog)


def _backup_waiting_at_cut(catalog, destination, at_cut, proceed, results):
    def cut():
        at_cut.set()
        assert proceed.wait(20)

    try:
        RecoveryService().create_consistent_backup(
            catalog, destination, BackupScope.PAIRED, snapshot_cut_callback=cut
        )
        results.put("published")
    except CatalogStoppedError:
        results.put("stopped")


def _stop(catalog, done):
    RecoveryService().stop_suspect_catalog(catalog, "separate process stop")
    done.set()


def test_separate_process_stop_before_publication(synthetic_catalog, tmp_path):
    ctx = multiprocessing.get_context("spawn")
    at_cut, proceed, stopped = ctx.Event(), ctx.Event(), ctx.Event()
    results = ctx.Queue()
    destination = tmp_path / "backup"
    backup = ctx.Process(
        target=_backup_waiting_at_cut,
        args=(synthetic_catalog, destination, at_cut, proceed, results),
    )
    backup.start()
    try:
        assert at_cut.wait(20)
        stop = ctx.Process(target=_stop, args=(synthetic_catalog, stopped))
        stop.start()
        stop.join(20)
        assert stop.exitcode == 0
        assert stopped.is_set()
        proceed.set()
        backup.join(20)
        assert backup.exitcode == 0
        assert results.get(timeout=5) == "stopped"
        assert not destination.exists()
        assert is_catalog_stopped(synthetic_catalog)
    finally:
        if backup.is_alive():
            backup.kill()
            backup.join()


def test_valid_empty_context_text_is_not_corruption(synthetic_catalog, tmp_path):
    from repo_catalog.adapters.sqlite.p1_schema import connect
    from tests.integration.p7.conftest import DEFAULT_REPO_UUID, admit_context_text

    connection = connect(synthetic_catalog / "context.sqlite3", "context")
    digest = admit_context_text(connection, "")
    connection.close()
    service = RecoveryService()
    backup = tmp_path / "backup"
    assert service.create_consistent_backup(synthetic_catalog, backup).verified_clean
    restored = tmp_path / "restored"
    assert service.restore_backup(backup, restored, DEFAULT_REPO_UUID).revalidated_clean
    assert service.activate_catalog(restored, tmp_path / "active").clean_operational
    connection = sqlite3.connect(restored / "context.sqlite3")
    assert connection.execute(
        "SELECT text_value FROM text_bodies WHERE sha256=?", (digest,)
    ).fetchone() == ("",)
    connection.close()
    assert not is_catalog_stopped(synthetic_catalog)


def test_intrinsic_projection_damage_is_not_certified(synthetic_catalog, tmp_path):
    from repo_catalog.adapters.sqlite.p1_schema import (
        expected_schema,
        register_functions,
        schema_rows,
    )

    connection = sqlite3.connect(synthetic_catalog / "core.sqlite3")
    register_functions(connection)
    triggers = connection.execute(
        "SELECT name, sql FROM sqlite_schema WHERE name IN ('p1_immutable_scalar_claims_update','p1_immutable_intrinsic_claims_update')"
    ).fetchall()
    for name, _ in triggers:
        connection.execute(f'DROP TRIGGER "{name}"')
    connection.execute(
        "UPDATE scalar_claims SET value='[\"known\",999]' WHERE field='size'"
    )
    connection.execute(
        "UPDATE intrinsic_claims SET value='[\"known\",999]' WHERE field='size'"
    )
    for _, sql in triggers:
        connection.execute(sql)
    connection.commit()
    assert schema_rows(connection) == expected_schema("core")
    assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()
    with pytest.raises(CorruptionDetectedError, match="intrinsic_claim_guard"):
        RecoveryService().create_consistent_backup(
            synthetic_catalog, tmp_path / "backup"
        )
    assert is_catalog_stopped(synthetic_catalog)


def test_invalid_persisted_utf8_is_confirmed_damage(synthetic_catalog, tmp_path):
    connection = sqlite3.connect(synthetic_catalog / "context.sqlite3")
    sql = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE name='text_bodies_no_update'"
    ).fetchone()[0]
    connection.execute("DROP TRIGGER text_bodies_no_update")
    connection.execute("PRAGMA ignore_check_constraints=ON")
    connection.execute("UPDATE text_bodies SET text_value=CAST(x'ff' AS TEXT)")
    connection.execute(sql)
    connection.commit()
    connection.close()
    with pytest.raises(CorruptionDetectedError, match="invalid UTF-8"):
        RecoveryService().create_consistent_backup(
            synthetic_catalog, tmp_path / "backup"
        )
    assert is_catalog_stopped(synthetic_catalog)


def test_source_pair_mismatch_stops_after_reconfirmation(synthetic_catalog, tmp_path):
    from repo_catalog.adapters.sqlite.p1_schema import register_functions

    connection = sqlite3.connect(synthetic_catalog / "context.sqlite3")
    register_functions(connection)
    sql = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_store_identity_update'"
    ).fetchone()[0]
    connection.execute("DROP TRIGGER p1_immutable_store_identity_update")
    connection.execute(
        "UPDATE store_identity SET catalog_instance_uuidv4='99999999-9999-4999-8999-999999999999'"
    )
    connection.execute(sql)
    connection.commit()
    connection.close()
    with pytest.raises(
        CorruptionDetectedError, match="Source paired store identity mismatch"
    ):
        RecoveryService().create_consistent_backup(
            synthetic_catalog, tmp_path / "backup"
        )
    assert is_catalog_stopped(synthetic_catalog)


def test_staging_pair_mismatch_does_not_stop_healthy_source(
    synthetic_catalog, tmp_path
):
    from repo_catalog.adapters.sqlite.p1_schema import register_functions

    destination = tmp_path / "backup"

    def damage_stage():
        (stage,) = tmp_path.glob("backup.tmp.*/stores/context.sqlite3")
        connection = sqlite3.connect(stage)
        register_functions(connection)
        sql = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_store_identity_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER p1_immutable_store_identity_update")
        connection.execute(
            "UPDATE store_identity SET catalog_instance_uuidv4='99999999-9999-4999-8999-999999999999'"
        )
        connection.execute(sql)
        connection.commit()
        connection.close()

    with pytest.raises(BackupValidationError, match="Paired store identity mismatch"):
        RecoveryService().create_consistent_backup(
            synthetic_catalog, destination, snapshot_cut_callback=damage_stage
        )
    assert not is_catalog_stopped(synthetic_catalog)
    assert not destination.exists()


def test_separate_sqlite_lock_has_finite_backup_wait(synthetic_catalog, tmp_path):
    import subprocess
    import sys
    import time

    locker = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA locking_mode=EXCLUSIVE'); c.execute('BEGIN EXCLUSIVE'); print('LOCKED',flush=True); sys.stdin.read()",
            str(synthetic_catalog / "core.sqlite3"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert locker.stdout.readline().strip() == "LOCKED"
        started = time.monotonic()
        with pytest.raises(BackupValidationError, match="finite deadline"):
            RecoveryService().create_consistent_backup(
                synthetic_catalog, tmp_path / "backup"
            )
        assert time.monotonic() - started < 5
        assert not is_catalog_stopped(synthetic_catalog)
        assert not (tmp_path / "backup").exists()
    finally:
        locker.stdin.close()
        locker.wait(timeout=10)
