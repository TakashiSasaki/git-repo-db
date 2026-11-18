"""Recovery receipts cannot complete after owned cleanup loses safety state."""

import json
import os
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite import repository_recovery as module
from repo_catalog.adapters.sqlite.catalog_runtime import persist_catalog_stop
from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.application.repository_recovery import RepositoryRecoveryService
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.recovery import BackupScope, RecoveryError


@pytest.fixture(params=[BackupScope.GIT_ONLY, BackupScope.PAIRED])
def restored(tmp_path, request):
    scope = request.param
    source = tmp_path / "source"
    source.mkdir()
    repository, instance = str(uuid4()), str(uuid4())
    for role in (
        ("repository", "context") if scope == BackupScope.PAIRED else ("repository",)
    ):
        initialize(source / (role + ".sqlite3"), role, repository, instance)
    service = (
        RecoveryService()
        if scope == BackupScope.PAIRED
        else RepositoryRecoveryService()
    )
    backup, fresh = tmp_path / "backup", tmp_path / "fresh"
    service.create_consistent_backup(source, backup, scope)
    service.restore_backup(backup, fresh, repository)
    service.stop_suspect_catalog(source, "synthetic stopped source")
    preserved = {p.name: p.read_bytes() for p in source.iterdir() if p.is_file()}
    stream = tmp_path / "input.jsonl"
    stream.write_text(
        json.dumps(
            {
                "candidate_type": "git_metadata",
                "extraction_status": "clean",
                "extraction_provenance": {"table": "git_objects", "scope": scope.value},
                "payload": {"object_format": "sha1", "object_oid": "5" * 40},
            }
        )
        + "\n"
    )
    yield service, fresh, stream
    assert {
        p.name: p.read_bytes() for p in source.iterdir() if p.is_file()
    } == preserved


def test_merge_owned_repository_cleanup_stop_refuses_receipt(restored, monkeypatch):
    service, fresh, stream = restored
    original = GitRepositoryStore.close
    closed = []

    def stopped(repository_store):
        original(repository_store)
        closed.append(True)
        persist_catalog_stop(fresh, "synthetic after Repository.close")

    monkeypatch.setattr(GitRepositoryStore, "close", stopped)
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        service.merge_salvage(fresh, stream)
    assert closed and service.is_stopped(fresh)


@pytest.mark.parametrize("owner", ["catalog", "locator-parent"])
def test_activation_owned_descriptor_cleanup_stop_refuses_receipt(
    restored, tmp_path, owner
):
    service, fresh, _ = restored
    locator = tmp_path / "active"
    original_open, original_close = module._open_directory_nofollow, os.close
    watched = fresh if owner == "catalog" else locator.parent
    state = {"fd": None, "fired": False}

    def tracked(path, *args, **kwargs):
        descriptor = original_open(path, *args, **kwargs)
        if Path(path).absolute() == watched.absolute() and state["fd"] is None:
            state["fd"] = descriptor
        return descriptor

    def stopped(descriptor):
        selected = descriptor == state["fd"] and not state["fired"]
        original_close(descriptor)
        if selected and locator.exists():
            state["fired"] = True
            persist_catalog_stop(fresh, "synthetic after owned descriptor close")

    with (
        patch.object(module, "_open_directory_nofollow", tracked),
        patch.object(os, "close", stopped),
    ):
        with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
            service.activate_catalog(fresh, locator)
    assert state["fired"] and service.is_stopped(fresh)
    # Publication may already be committed; the stopped target is out of service.
    assert locator.resolve() == fresh.resolve()


@pytest.mark.parametrize("missing", ["report", "reservation", "registry", "marker"])
def test_final_accounting_loss_never_returns_or_repairs_receipt(
    restored, monkeypatch, missing
):
    service, fresh, stream = restored
    paths = {
        "report": fresh / "p1-recovery-request-final.json",
        "reservation": fresh / "p1-recovery-request-final.reserved.json",
        "registry": fresh / "p1-recovery-requests.json",
        "marker": fresh / "p1-recovery-requests.initialized",
    }
    lost = paths[missing]
    original = GitRepositoryStore.close
    removed = []

    def remove_after_close(repository_store):
        original(repository_store)
        if lost.exists():
            lost.unlink()
            removed.append(True)

    monkeypatch.setattr(GitRepositoryStore, "close", remove_after_close)
    with pytest.raises(RecoveryError):
        service.merge_salvage(fresh, stream, request_id="final")
    assert removed and not lost.exists()
    assert not service.is_stopped(fresh)
    with closing(GitRepositoryStore(fresh / "repository.sqlite3")) as repository_store:
        assert len(repository_store.sql("SELECT * FROM git_objects")) == 1
