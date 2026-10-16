"""Independent P7 process/WAL evidence on disposable P1 catalogs.

These tests exercise SIGKILL/process restart on Linux; they do not simulate host
power failure or establish persistence beyond the tested filesystem contract.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import select
import signal
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.application.acquisition import GitAcquisition
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.application.recovery import RecoveryService
from repo_catalog.domain.acquisition import GitNativeAcquisitionRequest
from repo_catalog.domain.p1_context import FieldClock, ResourceKey, canonical
from repo_catalog.domain.p1_core import OID, CoreFailure
from repo_catalog.domain.production_context import CoreReference
from repo_catalog.domain.production_query import SearchQuery
from repo_catalog.domain.recovery import BackupScope
from tests.integration.p5.conftest import build_sample_git_repo
from tests.integration.p7.conftest import make_commit, make_tree

WRITER_PROBE = """
import fcntl,sys
with open(sys.argv[1], 'a+b') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('blocked')
    else:
        print('acquired')
"""


def _probe_writer(directory, lock_name="p1-writer.lock"):
    return subprocess.run(
        [sys.executable, "-c", WRITER_PROBE, str(directory / lock_name)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


def _evidence_hashes(directory):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.glob("*.sqlite3*")
        if p.is_file()
    }


@pytest.fixture
def committed_p1_wal(synthetic_catalog):
    """Keep real typed Core + Context commits exclusively in uncheckpointed WAL."""
    tree = make_tree("sha1", [(b"100644", b"wal-file", "a" * 40)])
    commit = make_commit("sha1", tree.oid.full_oid, [], message="Committed in WAL\n")
    text = "P1 Context text committed in genuine WAL frames"
    core_db = connect(synthetic_catalog / "core.sqlite3", "core")
    context_db = connect(synthetic_catalog / "context.sqlite3", "context")
    try:
        for db in (core_db, context_db):
            assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
            db.execute("PRAGMA wal_autocheckpoint=0")
        core_db.execute("BEGIN IMMEDIATE")
        with GitCore.for_transaction(core_db) as core:
            core.admit_metadata(tree, str(uuid4()), UnlimitedWorkBudget())
            core.admit_metadata(commit, str(uuid4()), UnlimitedWorkBudget())
        core_db.commit()
        digest = ContextStore(context_db).text(text)
        for role, query, args in (
            (
                "core",
                "SELECT count(*) FROM retained_metadata WHERE full_oid=?",
                (commit.oid.full_oid,),
            ),
            ("context", "SELECT count(*) FROM text_bodies WHERE sha256=?", (digest,)),
        ):
            # immutable=1 intentionally ignores WAL. This proves the new actual
            # domain unit is absent from the base DB and needs committed frames.
            path = synthetic_catalog / f"{role}.sqlite3"
            with sqlite3.connect(f"file:{path}?immutable=1", uri=True) as base:
                assert base.execute(query, args).fetchone()[0] == 0
            wal = path.with_name(path.name + "-wal")
            assert wal.stat().st_size > 32
            assert wal.read_bytes()[:4] in (b"7\x7f\x06\x82", b"7\x7f\x06\x83")
            assert path.with_name(path.name + "-shm").is_file()
        yield synthetic_catalog, commit, text
    finally:
        core_db.close()
        context_db.close()


@pytest.mark.parametrize("stopped", [False, True])
def test_actual_p1_wal_candidates_and_process_writer_cut(
    committed_p1_wal, tmp_path, monkeypatch, stopped
):
    directory, commit, text = committed_p1_wal
    lock_name = "p1-stop-fence.lock" if stopped else "p1-writer.lock"
    if stopped:
        RecoveryService().stop_suspect_catalog(directory, "synthetic diagnostic stop")
    assert _probe_writer(directory, lock_name) == "acquired"
    before = _evidence_hashes(directory)
    original = SQLiteRecoveryAdapter._salvage_store_stream
    observed = []

    def at_forensic_read(self, *args, **kwargs):
        observed.append(_probe_writer(directory, lock_name))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(
        SQLiteRecoveryAdapter, "_salvage_store_stream", at_forensic_read
    )
    output = tmp_path / "actual-wal.jsonl"
    receipt = RecoveryService().extract_salvage(directory, output)
    assert not receipt.partial, receipt.unreadable_scope
    assert observed == ["blocked", "blocked"]
    assert _evidence_hashes(directory) == before
    assert _probe_writer(directory, lock_name) == "acquired"
    records = [json.loads(line) for line in output.read_text().splitlines()]
    commits = [
        r
        for r in records
        if r["payload"].get("full_oid") == commit.oid.full_oid
        and "body_base64" in r["payload"]
    ]
    assert len(commits) == 1
    assert base64.b64decode(commits[0]["payload"]["body_base64"]) == commit.body
    assert any(r["payload"].get("text_value") == text for r in records)


COPY_CRASH = r"""
import pathlib,sys
from repo_catalog.adapters.sqlite import recovery
from repo_catalog.application.recovery import RecoveryService

def pause():
    print('copy-started', flush=True)
    sys.stdin.buffer.read(1)

if hasattr(recovery, '_copy_forensic_files'):
    # The bounded copier uses descriptor-backed reads. Pause after actual input
    # has been read, before returning it to the destination writer.
    original = recovery.os.fdopen
    class InterruptedReader:
        def __init__(self, stream):
            self.stream = stream
        def __getattr__(self, name):
            return getattr(self.stream, name)
        def __enter__(self):
            self.stream.__enter__()
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def read(self, *args):
            data = self.stream.read(*args)
            pause()
            return data
    def paused_fdopen(fd, mode, *args, **kwargs):
        stream = original(fd, mode, *args, **kwargs)
        return InterruptedReader(stream) if mode == 'rb' else stream
    recovery.os.fdopen = paused_fdopen
else:
    # Preserve exact baseline counterexample execution before the bounded-copy
    # correction is integrated; both paths stop inside the forensic copy cut.
    original = recovery.shutil.copy2
    def paused_copy(source, target, *args, **kwargs):
        value = original(source, target, *args, **kwargs)
        pause()
        return value
    recovery.shutil.copy2 = paused_copy
RecoveryService().extract_salvage(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
"""


def test_sigkill_during_forensic_copy_preserves_source_and_retry(
    committed_p1_wal, tmp_path
):
    directory, commit, _ = committed_p1_wal
    before = _evidence_hashes(directory)
    output = tmp_path / "interrupted.jsonl"
    child = subprocess.Popen(
        [sys.executable, "-c", COPY_CRASH, str(directory), str(output)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready, _, _ = select.select([child.stdout], [], [], 20)
        assert ready, "child failed to reach actual forensic copy cut"
        assert child.stdout.readline().strip() == "copy-started"
        assert _probe_writer(directory) == "blocked"
        os.kill(child.pid, signal.SIGKILL)
        child.wait(timeout=10)
        assert child.returncode == -signal.SIGKILL
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
    assert _evidence_hashes(directory) == before
    assert not output.exists()
    assert _probe_writer(directory) == "acquired"
    receipt = RecoveryService().extract_salvage(directory, output)
    assert not receipt.partial
    assert _evidence_hashes(directory) == before
    assert any(
        json.loads(line)["payload"].get("full_oid") == commit.oid.full_oid
        for line in output.read_text().splitlines()
    )


def test_stop_fences_actual_p5_acquisition_and_p6_query_search(
    synthetic_catalog, tmp_path, repo_uuid
):
    native = tmp_path / "native.git"
    build_sample_git_repo(native)
    source = GitNativeSource(native)
    acquisition = GitAcquisition(
        synthetic_catalog, operational=synthetic_catalog / "operational.sqlite3"
    )
    request = GitNativeAcquisitionRequest(
        repo_uuid, str(uuid4()), str(uuid4()), "local-test", 1
    )
    query = ProductionQueryService(synthetic_catalog)
    assert query.get_repository_view() is not None  # healthy control
    RecoveryService().stop_suspect_catalog(
        synthetic_catalog, "synthetic known corruption"
    )
    # Operational/Search loss does not make these real application paths usable.
    for role in ("operational", "search"):
        (synthetic_catalog / f"{role}.sqlite3").unlink()
    before = _evidence_hashes(synthetic_catalog)
    for operation in (
        lambda: acquisition.acquire_from_native(source, request, new_request=True),
        query.get_repository_view,
        lambda: query.search(SearchQuery("review")),
        query.rebuild_search,
    ):
        with pytest.raises(CoreFailure) as error:
            operation()
        assert error.value.code == "RECOVERY_STOP"
    assert _evidence_hashes(synthetic_catalog) == before
    # A new interpreter must read the durable stop, rather than inherit service
    # objects or process-local state from the detector.
    restarted = subprocess.run(
        [
            sys.executable,
            "-c",
            RESTARTED_STOP_PROBE,
            str(synthetic_catalog),
            str(native),
            repo_uuid,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert restarted.returncode == 0, restarted.stderr
    assert restarted.stdout.splitlines() == ["RECOVERY_STOP"] * 4
    assert _evidence_hashes(synthetic_catalog) == before


RESTARTED_STOP_PROBE = r"""
from pathlib import Path
import sys
from uuid import uuid4
from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.application.acquisition import GitAcquisition
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.acquisition import GitNativeAcquisitionRequest
from repo_catalog.domain.production_query import SearchQuery
from repo_catalog.domain.p1_core import CoreFailure
catalog, native = Path(sys.argv[1]), Path(sys.argv[2])
request = GitNativeAcquisitionRequest(sys.argv[3], str(uuid4()), str(uuid4()), "restart", 1)
acquisition = GitAcquisition(catalog, operational=catalog / "operational.sqlite3")
query = ProductionQueryService(catalog)
for operation in (
    lambda: acquisition.acquire_from_native(GitNativeSource(native), request, new_request=True),
    query.get_repository_view,
    lambda: query.search(SearchQuery("review")),
    query.rebuild_search,
):
    try:
        operation()
    except CoreFailure as error:
        assert error.code == "RECOVERY_STOP"
        print(error.code)
    else:
        raise AssertionError("stopped entry point completed")
"""


def test_actual_unresolved_context_reference_survives_restore_and_salvage(
    synthetic_catalog, tmp_path, repo_uuid
):
    service_id = str(uuid4())
    key = ResourceKey(service_id, "pull_request", "unresolved-1")
    missing = OID("sha1", "e" * 40)
    provenance = canonical({"source": "test", "evidence": "original-reference"})
    reference = CoreReference(key, "head", missing, provenance)
    with Context.transaction(synthetic_catalog) as context:
        context.provider(service_id, "github")
        context.repository(repo_uuid)
        context.resource(key, repo_uuid)
        context.report_core_reference(
            reference, clock=FieldClock("provider.updated_at", 9), observed_at_us=10
        )
    service = RecoveryService()
    backup = tmp_path / "unresolved-backup"
    service.create_consistent_backup(
        synthetic_catalog, backup, scope=BackupScope.PAIRED
    )
    restored = tmp_path / "unresolved-restored"
    service.restore_backup(backup, restored, repo_uuid)
    view = ProductionQueryService(restored).get_paired_resource(key)
    assert len(view.core_resolutions) == 1
    resolution = view.core_resolutions[0]
    assert resolution.reference == reference
    assert not resolution.available_in_core
    assert not resolution.core_required
    assert resolution.object_view is None
    output = tmp_path / "unresolved.jsonl"
    receipt = service.extract_salvage(synthetic_catalog, output)
    assert not receipt.partial
    records = [json.loads(line) for line in output.read_text().splitlines()]
    candidates = [
        r
        for r in records
        if r["payload"].get("field_name") == "reported_core_reference:head"
    ]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert json.loads(candidate["payload"]["value_json"]) == list(missing.key)
    assert candidate["payload"]["provenance_json"] == provenance
    # An unresolved attributed dependency is not authoritative corruption.
    assert not service.is_stopped(synthetic_catalog)
    assert not service.is_stopped(restored)
