"""Positive source-corruption evidence and independent stop/publication cuts."""

import multiprocessing
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.recovery import (
    SQLiteRecoveryAdapter,
    is_catalog_stopped,
)
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
