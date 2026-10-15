"""Process-death tests against two different persistent WAL database files."""

import contextlib
import json
import shutil
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tests.integration.architecture_spikes.consistency import (
    OID,
    admit,
    backup,
    connect,
    initialize,
    persisted,
    snapshots,
    state,
    validate_backup,
)

WORKER = Path(__file__).with_name("consistency.py")


def crash(directory, point, action="admit", destination=None):
    args = [sys.executable, str(WORKER), action, str(directory), point]
    if destination:
        args.append(str(destination))
    result = subprocess.run(args, capture_output=True, timeout=15)
    assert result.returncode == 86, result.stderr.decode()


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        ("before_core_commit", (0, 0, 0)),
        ("after_core_commit", (1, 0, 0)),
        ("during_context", (1, 0, 0)),
        ("after_context_commit", (1, 1, 1)),
    ],
)
def test_crash_cuts_and_identity_preserving_retry(
    tmp_path, point, expected, record_property
):
    directory = tmp_path / "live"
    initialize(directory)
    assert (directory / "core.sqlite3").stat().st_ino != (
        directory / "context.sqlite3"
    ).stat().st_ino
    for name in ("core", "context"):
        with contextlib.closing(connect(directory / f"{name}.sqlite3")) as db:
            assert db.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    crash(directory, point)
    result = persisted(directory)
    counts = tuple(len(result[k]) for k in ("objects", "issues", "links"))
    record_property("crash_cut", point)
    record_property("persisted", json.dumps(result, sort_keys=True))
    assert counts == expected
    assert result["resolved"]
    # OS process death releases the shared writer gate; same genuine evidence retries.
    admit(directory)
    first = persisted(directory)
    admit(directory)
    assert persisted(directory) == first
    assert tuple(len(first[k]) for k in ("objects", "issues", "links")) == (1, 1, 1)


def test_naive_unfenced_snapshots_can_mix_authoritative_states(tmp_path):
    directory = tmp_path / "live"
    initialize(directory)
    with contextlib.closing(connect(directory / "core.sqlite3")) as core:
        core.execute("BEGIN")
        assert core.execute("SELECT * FROM objects").fetchall() == []
        admit(directory)
        with contextlib.closing(connect(directory / "context.sqlite3")) as ctx:
            mixed = state(core, ctx)
            assert mixed["links"] and not mixed["resolved"]
            # Both actual databases are healthy. The falsely coherent read was the defect.
            assert ctx.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert persisted(directory)["resolved"]


def test_pinned_pair_stays_coherent_during_writer(tmp_path):
    directory = tmp_path / "live"
    initialize(directory)
    with snapshots(directory) as (core, ctx):
        before = state(core, ctx)
        admit(directory)
        assert state(core, ctx) == before
        assert before == {"objects": [], "issues": [], "links": [], "resolved": True}
    assert len(persisted(directory)["links"]) == 1


def test_reader_cannot_enter_between_core_and_context_commit(tmp_path):
    directory = tmp_path / "live"
    initialize(directory)
    # A real subprocess owns the OS gate and pauses at the otherwise vulnerable cut.
    code = """
import pathlib, sys
sys.path.insert(0, sys.argv[1])
from tests.integration.architecture_spikes import consistency as c
original = c.cut
def pause(point, requested):
    if point == 'after_core_commit':
        print('cut', flush=True)
        sys.stdin.readline()
c.cut = pause
c.admit(pathlib.Path(sys.argv[2]))
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(Path(__file__).parents[3]), str(directory)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    entered = threading.Event()
    finished = threading.Event()
    result = []

    def read_pair():
        entered.set()
        result.append(persisted(directory))
        finished.set()

    try:
        assert proc.stdout.readline().strip() == "cut"
        thread = threading.Thread(target=read_pair)
        thread.start()
        assert entered.wait(3)
        assert not finished.wait(0.1)
        proc.communicate("continue\n", timeout=10)
        assert proc.returncode == 0
        assert finished.wait(5)
        thread.join()
        assert result[0]["resolved"] and len(result[0]["links"]) == 1
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def test_context_transaction_failure_never_leaks_partial_unit(tmp_path):
    directory = tmp_path / "live"
    initialize(directory)
    crash(directory, "after_core_commit")
    with contextlib.closing(connect(directory / "context.sqlite3")) as ctx:
        ctx.execute("BEGIN IMMEDIATE")
        ctx.execute("INSERT INTO issue_evidence VALUES('p','i',1,'t')")
        with pytest.raises(sqlite3.IntegrityError):
            ctx.execute(
                "INSERT INTO issue_git VALUES('p','other',1,'head','sha1',?)", (OID,)
            )
        ctx.rollback()
    result = persisted(directory)
    assert len(result["objects"]) == 1
    assert result["issues"] == result["links"] == []


def test_interrupted_pair_backup_has_no_certificate(tmp_path):
    directory, destination = tmp_path / "live", tmp_path / "copy"
    initialize(directory)
    admit(directory)
    crash(directory, "during_backup", "backup", destination)
    assert (destination / "core.sqlite3").exists()
    assert not (destination / "manifest.json").exists()
    with pytest.raises(FileNotFoundError):
        validate_backup(destination)
    # Retry is a new disposable destination, never blessing the partial result.
    backup(directory, tmp_path / "retry")
    validate_backup(tmp_path / "retry")


def test_pair_backup_fence_blocks_writer_and_rejects_mismatch(tmp_path):
    directory = tmp_path / "live"
    initialize(directory)
    proc = None

    def concurrent_writer():
        nonlocal proc
        code = """
import fcntl, pathlib, runpy, sys
source = pathlib.Path(sys.argv[2])
with (source / 'writer.lock').open('a+b') as handle:
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('blocked', flush=True)
    else:
        print('UNFENCED', flush=True)
        sys.exit(2)
module = runpy.run_path(sys.argv[1])
module['admit'](source)
"""
        proc = subprocess.Popen(
            [sys.executable, "-c", code, str(WORKER), str(directory)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # A nonblocking OS lock attempt gives deterministic evidence at this cut:
        # removing backup's shared gate yields UNFENCED, regardless of scheduling.
        assert proc.stdout.readline().strip() == "blocked"

    backup(directory, tmp_path / "before", between_copies=concurrent_writer)
    proc.wait(timeout=10)
    assert proc.returncode == 0
    validate_backup(tmp_path / "before")
    assert persisted(tmp_path / "before")["links"] == []
    backup(directory, tmp_path / "after")
    validate_backup(tmp_path / "after")
    assert len(persisted(tmp_path / "after")["links"]) == 1
    shutil.copyfile(
        tmp_path / "after/context.sqlite3", tmp_path / "before/context.sqlite3"
    )
    with pytest.raises(ValueError, match="pair bytes differ"):
        validate_backup(tmp_path / "before")


def test_missing_context_is_not_full_backup_or_invalid_core(tmp_path):
    directory = tmp_path / "live"
    initialize(directory)
    crash(directory, "after_core_commit")
    (directory / "context.sqlite3").unlink()
    with contextlib.closing(connect(directory / "core.sqlite3")) as core:
        assert core.execute("SELECT * FROM objects").fetchall() == [("sha1", OID)]
    # A Core-only file has no full-pair certificate; no Context recreation is a restore.
    with pytest.raises(FileNotFoundError):
        validate_backup(directory)


@pytest.mark.parametrize("defect", ["repository", "foreign_key", "core_dependency"])
def test_invalid_pair_never_receives_full_backup_manifest(tmp_path, defect):
    directory, destination = tmp_path / "live", tmp_path / "bad-copy"
    initialize(directory)
    admit(directory)
    with contextlib.closing(connect(directory / "context.sqlite3")) as ctx:
        if defect == "repository":
            ctx.execute("UPDATE repository SET repository_uuidv4='other-repository'")
        elif defect == "foreign_key":
            ctx.execute("PRAGMA foreign_keys=OFF")
            ctx.execute("DELETE FROM issue_evidence")
        else:
            ctx.execute("UPDATE issue_git SET full_oid=?", ("b" * 40,))
    with pytest.raises(ValueError):
        backup(directory, destination)
    assert not (destination / "manifest.json").exists()
