"""Real SQLite/WAL, filesystem, inactive restore and immutable-history fork tests.

Uses only disposable fixtures. No independent review or power-cut qualification.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from repo_catalog.adapters.sqlite import access_backup as backup_module
from repo_catalog.adapters.sqlite import access_schema as schema
from repo_catalog.adapters.sqlite.access_backup import AccessBackup
from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.application.access_maintenance import AccessMaintenance
from repo_catalog.domain.access_backup import AccessBackupLimits, ScopeFork
from repo_catalog.domain.access_connections import (
    AccessPreference,
    AssignmentKey,
    ConnectionConfiguration,
    LocatorConnection,
    RepositoryBinding,
    ScopeExecutionContext,
    canonical,
)
from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    AccessScope,
    ScopeLocatorRegistration,
)

S1 = "550e8400-e29b-41d4-a716-446655440000"
S2 = "650e8400-e29b-41d4-a716-446655440000"
S3 = "750e8400-e29b-41d4-a716-446655440000"
R1 = "850e8400-e29b-41d4-a716-446655440000"
KEY = AssignmentKey(S1, "/repos/app.git", "local")
REGS = (
    ScopeLocatorRegistration(S1, 10, "file:///old"),
    ScopeLocatorRegistration(S1, 20, "file:///new"),
    ScopeLocatorRegistration(S1, 30, "file:///old"),
)
OPTIONS = canonical({"version": 1, "transport": "file", "path_dialect": "posix"})
CONTEXT = canonical(
    {
        "version": 1,
        "executor_kind": "local",
        "executor_ref": "runner",
        "identity_view": "owner",
        "path_dialect": "posix",
    }
)


def raw(path, **kwargs):
    db = sqlite3.connect(path, isolation_level=None, cached_statements=0, **kwargs)
    schema.register_functions(db)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    return db


def rows(path):
    db = raw(path)
    try:
        return {t: sorted(db.execute(f"SELECT * FROM {t}")) for t in schema.TABLES}
    finally:
        db.close()


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.sqlite3"
    schema.initialize(path)
    with AccessConnections(path, writable=True) as store:
        store.register_scope(AccessScope(S1, "同一Scope"))
        store.register_scope(AccessScope(S3, "別Scope"))
        for reg in REGS:
            store.register_locator(reg)
            store.set_locator_enabled(reg, True)
        store.configure_scope(ScopeExecutionContext(S1, CONTEXT, True))
        store.bind_repository(RepositoryBinding(S1, KEY.locator_text, R1, True))
        store.configure_connection(
            ConnectionConfiguration(S1, KEY.configuration_name, OPTIONS, True)
        )
        store.assign_connection(LocatorConnection(KEY, True))
        store.set_preference(AccessPreference(R1, KEY))
        store.record_local_approval(store.review_plan(R1, S1), 40)
    return path


@pytest.fixture
def bundle(source, tmp_path):
    destination = tmp_path / "backup"
    AccessBackup().backup(source, destination)
    return destination


def reseal(bundle):
    """Attacker can replace bytes AND hashes; receiver validation still matters."""
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    payload = (bundle / "access.sqlite3").read_bytes()
    manifest["store"]["bytes"] = len(payload)
    manifest["store"]["sha256"] = hashlib.sha256(payload).hexdigest()
    write_manifest(bundle, manifest)


def write_manifest(bundle, manifest):
    encoded = backup_module._encoded(manifest)
    (bundle / "manifest.json").write_bytes(encoded)
    (bundle / "manifest.sha256").write_text(hashlib.sha256(encoded).hexdigest() + "\n")


def test_backup_retains_all_history_and_settings_but_not_consent(source, bundle):
    before = rows(source)
    manifest = AccessBackup().inspect(bundle)
    actual = rows(bundle / "access.sqlite3")
    assert manifest["source_grants_omitted"] == 1
    assert manifest["row_counts"]["local_access_grants"] == 0
    for table in schema.TABLES:
        assert actual[table] == (
            [] if table == "local_access_grants" else before[table]
        )
    assert rows(source) == before
    assert set(p.name for p in bundle.iterdir()) == backup_module.FILES
    assert bundle.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in bundle.iterdir())
    with raw(bundle / "access.sqlite3") as db:
        assert db.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    # Artifact is not the live-format/activation API.
    with pytest.raises(AccessRegistryError, match="FORMAT"):
        AccessConnections(bundle / "access.sqlite3")


def test_restore_is_continuation_not_fresh_registrations(source, bundle, tmp_path):
    old = rows(source)
    original_bundle = {p.name: p.read_bytes() for p in bundle.iterdir()}
    destination = tmp_path / "restored"
    receipt = AccessBackup().restore(bundle, destination)
    assert receipt["scope_uuids_preserved"] and receipt["registration_times_preserved"]
    assert receipt["requires_local_reapproval"]
    assert set(p.name for p in destination.iterdir()) == {
        "access.sqlite3",
        "restore.json",
    }
    with AccessConnections(destination / "access.sqlite3", writable=True) as store:
        assert store.first_choices(S1) == (REGS[-1],)
        assert store.history(S1).registrations == REGS[::-1]
        assert store.scope(S1).display_name == "同一Scope"
        assert store.scope(S3).scope_uuidv4 == S3
        assert not any(store.locator_enabled(r) for r in REGS)
        with pytest.raises(AccessRegistryError, match="DISABLED"):
            store.current_grant(R1, S1)
        # Replay cannot reenable or reinstate approval.
        assert store.register_locator(REGS[-1]).status == "duplicate"
        assert not store.locator_enabled(REGS[-1])
        store.set_locator_enabled(REGS[-1], True)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(R1, S1)
    assert rows(source) == old
    assert {p.name: p.read_bytes() for p in bundle.iterdir()} == original_bundle
    assert not (tmp_path / "core.sqlite3").exists()
    assert not (tmp_path / "context.sqlite3").exists()


def test_latest_ties_survive_restore(source, tmp_path):
    other = ScopeLocatorRegistration(S1, 30, "file:///other")
    with AccessConnections(source, writable=True) as store:
        store.register_locator(other)
    backup = AccessBackup()
    backup.backup(source, tmp_path / "b")
    backup.restore(tmp_path / "b", tmp_path / "r")
    with AccessConnections(tmp_path / "r/access.sqlite3") as store:
        assert set(store.first_choices(S1)) == {REGS[-1], other}
        with pytest.raises(AccessRegistryError, match="AMBIGUOUS"):
            store.review_plan(R1, S1)


def test_committed_wal_snapshot_does_not_mix_concurrent_registration(
    source, tmp_path, monkeypatch
):
    # Keep a writer open and disable checkpointing to ensure genuine WAL content.
    writer = raw(source)
    writer.execute("PRAGMA wal_autocheckpoint=0")
    extra = ScopeLocatorRegistration(S1, 50, "file:///committed-wal")
    writer.execute("INSERT INTO scope_locators VALUES(?,?,?)", extra.key)
    assert Path(str(source) + "-wal").stat().st_size > 0
    later = ScopeLocatorRegistration(S1, 60, "file:///after-snapshot")
    original = backup_module._counts
    once = False

    def concurrent(db, budget):
        nonlocal once
        result = original(db, budget)
        if not once:
            once = True
            # Same process separate connection, commits while reader's snapshot is pinned.
            writer.execute("INSERT INTO scope_locators VALUES(?,?,?)", later.key)
        return result

    monkeypatch.setattr(backup_module, "_counts", concurrent)
    try:
        manifest = AccessBackup().backup(source, tmp_path / "wal-backup")
    finally:
        writer.close()
    assert manifest["row_counts"]["scope_locators"] == 4
    with raw(tmp_path / "wal-backup/access.sqlite3") as db:
        actual = db.execute(
            "SELECT * FROM scope_locators ORDER BY registered_at_us"
        ).fetchall()
        assert actual == [r.key for r in (*REGS, extra)]
    assert len(rows(source)["scope_locators"]) == 5


@pytest.mark.parametrize("operation", ["backup", "restore"])
@pytest.mark.parametrize("kind", ["directory", "empty-directory", "file", "symlink"])
def test_existing_target_never_overwritten(source, bundle, tmp_path, operation, kind):
    destination = tmp_path / "existing"
    if kind in ("directory", "empty-directory"):
        destination.mkdir()
        if kind == "directory":
            (destination / "sentinel").write_bytes(b"keep")
    elif kind == "file":
        destination.write_bytes(b"keep")
    else:
        destination.symlink_to(source)
    before = source.read_bytes()
    with pytest.raises(AccessRegistryError, match="EXISTS"):
        getattr(AccessBackup(), operation)(
            source if operation == "backup" else bundle, destination
        )
    assert source.read_bytes() == before
    if kind == "directory":
        assert (destination / "sentinel").read_bytes() == b"keep"
    if kind == "empty-directory":
        assert list(destination.iterdir()) == []
    if kind == "file":
        assert destination.read_bytes() == b"keep"
    if kind == "symlink":
        assert destination.is_symlink()


@pytest.mark.parametrize(
    "member", ["manifest.json", "manifest.sha256", "access.sqlite3"]
)
@pytest.mark.parametrize(
    "kind", ["symlink", "hardlink", "fifo", "permissions", "missing"]
)
def test_invalid_bundle_members_rejected(bundle, tmp_path, member, kind):
    target = bundle / member
    if kind == "permissions":
        target.chmod(0o644)
    else:
        if kind in ("symlink", "hardlink"):
            outside = tmp_path / "outside"
            outside.write_bytes(target.read_bytes())
            outside.chmod(0o600)
        target.unlink()
        if kind == "symlink":
            target.symlink_to(outside)
        if kind == "hardlink":
            os.link(outside, target)
        if kind == "fifo":
            os.mkfifo(target, 0o600)
    with pytest.raises((AccessRegistryError, OSError)):
        AccessBackup().restore(bundle, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize(
    "member",
    [
        "extra",
        "access.sqlite3-wal",
        "access.sqlite3-shm",
        "access.sqlite3.access-stop.json",
        "nested",
    ],
)
def test_unexpected_backup_members_fail(bundle, member):
    (bundle / member).touch()
    with pytest.raises(AccessRegistryError, match="BACKUP_FORMAT"):
        AccessBackup().inspect(bundle)


@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "extra",
        "format",
        "version-bool",
        "timestamp",
        "grants",
        "domain",
        "counts",
        "length",
        "digest",
        "unknown-table",
    ],
)
def test_manifest_exact_contract(bundle, tmp_path, mutation):
    data = json.loads((bundle / "manifest.json").read_bytes())
    if mutation == "path":
        data["store"]["path"] = "../source.sqlite3"
    if mutation == "extra":
        data["execute"] = True
    if mutation == "format":
        data["format"] = "legacy"
    if mutation == "version-bool":
        data["schema_version"] = True
    if mutation == "timestamp":
        data["created_at_us"] = 0
    if mutation == "grants":
        data["local_grants_included"] = True
    if mutation == "domain":
        data["domain_catalog_included"] = True
    if mutation == "counts":
        data["row_counts"]["scope_locators"] = True
    if mutation == "length":
        data["store"]["bytes"] += 1
    if mutation == "digest":
        data["store"]["sha256"] = "0" * 64
    if mutation == "unknown-table":
        data["row_counts"]["evil"] = 0
    write_manifest(bundle, data)
    with pytest.raises(AccessRegistryError):
        AccessBackup().restore(bundle, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize(
    "which", ["store", "manifest", "digest", "truncated", "duplicate-key"]
)
def test_byte_integrity(bundle, which):
    if which == "store":
        p = bundle / "access.sqlite3"
        data = bytearray(p.read_bytes())
        data[-1] ^= 1
        p.write_bytes(data)
    if which == "truncated":
        p = bundle / "access.sqlite3"
        p.write_bytes(p.read_bytes()[:-1024])
    if which == "manifest":
        (bundle / "manifest.json").write_bytes(b"{}\n")
    if which == "digest":
        (bundle / "manifest.sha256").write_bytes(b"0" * 64 + b"\n")
    if which == "duplicate-key":
        data = (bundle / "manifest.json").read_bytes()
        data = b'{"format":"extra",' + data[1:]
        (bundle / "manifest.json").write_bytes(data)
        (bundle / "manifest.sha256").write_bytes(
            hashlib.sha256(data).hexdigest().encode() + b"\n"
        )
    with pytest.raises(AccessRegistryError):
        AccessBackup().inspect(bundle)


@pytest.mark.parametrize(
    "damage", ["schema", "utf8", "missing-parent", "registration-time", "options"]
)
def test_rechecksummed_corruption_never_restored(bundle, tmp_path, damage):
    p = bundle / "access.sqlite3"
    with raw(p) as db:
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("PRAGMA foreign_keys=OFF")
        if damage == "schema":
            db.execute("CREATE TABLE unexpected(x)")
        if damage == "utf8":
            db.execute("UPDATE access_scopes SET display_name=CAST(X'ff' AS TEXT)")
        if damage == "missing-parent":
            db.execute("DELETE FROM connection_configurations")
        if damage == "registration-time":
            trigger = db.execute(
                "SELECT sql FROM sqlite_schema WHERE name='scope_registration_no_update'"
            ).fetchone()[0]
            db.execute("DROP TRIGGER scope_registration_no_update")
            db.execute(
                "UPDATE scope_locators SET registered_at_us=0 WHERE registered_at_us=10"
            )
            db.execute(trigger)
        if damage == "options":
            db.execute("UPDATE connection_configurations SET options_json='{}'")
    reseal(bundle)
    before = {p.name: p.read_bytes() for p in bundle.iterdir()}
    with pytest.raises((AccessRegistryError, sqlite3.Error)):
        AccessBackup().restore(bundle, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
    assert {p.name: p.read_bytes() for p in bundle.iterdir()} == before


def test_approval_rows_even_rechecksummed_are_not_backup_authority(
    source, bundle, tmp_path
):
    grant = rows(source)["local_access_grants"][0]
    with raw(bundle / "access.sqlite3") as db:
        db.execute("INSERT INTO local_access_grants VALUES(?,?,?,?,?,?,?,?,?,?)", grant)
    reseal(bundle)
    with pytest.raises(AccessRegistryError):
        AccessBackup().restore(bundle, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("operation", ["backup", "restore", "inspect", "fork"])
def test_explicit_cancellation_does_not_mutate(source, bundle, tmp_path, operation):
    backup = AccessBackup(cancelled=lambda: True)
    before = rows(source)
    with pytest.raises(AccessRegistryError, match="CANCELLED"):
        if operation == "inspect":
            backup.inspect(bundle)
        elif operation == "fork":
            backup.fork_scope(source, fork_request())
        else:
            getattr(backup, operation)(
                source if operation == "backup" else bundle, tmp_path / "none"
            )
    assert rows(source) == before
    assert not (tmp_path / "none").exists()


@pytest.mark.parametrize("kind", ["rows", "bytes", "deadline"])
def test_budget_limits_are_not_corruption(source, tmp_path, monkeypatch, kind):
    limits = (
        AccessBackupLimits(max_rows=1)
        if kind == "rows"
        else AccessBackupLimits(max_bytes=1)
        if kind == "bytes"
        else AccessBackupLimits()
    )
    if kind == "deadline":
        clock = [0]

        def moving():
            clock[0] += 61
            return clock[0]

        monkeypatch.setattr(backup_module.time, "monotonic", moving)
    with pytest.raises(AccessRegistryError, match="LIMIT"):
        AccessBackup(limits).backup(source, tmp_path / "over")
    assert not (tmp_path / "over").exists()
    assert not schema.stop_path(source).exists()


def test_atomic_noreplace_handles_raced_empty_directory(source, tmp_path, monkeypatch):
    original = backup_module._publish
    target = tmp_path / "race"

    def raced(fd, stage, dest):
        target.mkdir()
        return original(fd, stage, dest)

    monkeypatch.setattr(backup_module, "_publish", raced)
    with pytest.raises(AccessRegistryError, match="EXISTS"):
        AccessBackup().backup(source, target)
    assert list(target.iterdir()) == []


def test_postpublication_sync_error_does_not_delete_complete_target(
    source, tmp_path, monkeypatch
):
    original = os.fsync
    parent_identity = backup_module._identity(tmp_path.stat())

    def fail(fd):
        if backup_module._identity(os.fstat(fd)) == parent_identity:
            raise OSError("injected parent fsync failure")
        return original(fd)

    monkeypatch.setattr(backup_module.os, "fsync", fail)
    destination = tmp_path / "uncertain"
    with pytest.raises(AccessRegistryError, match="PUBLICATION_UNCERTAIN"):
        AccessBackup().backup(source, destination)
    monkeypatch.setattr(backup_module.os, "fsync", original)
    assert AccessBackup().inspect(destination)["row_counts"]["scope_locators"] == 3


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_interruption_before_publication_leaves_no_target(
    source, bundle, tmp_path, monkeypatch, operation
):
    before = rows(source)

    def fail(*args):
        raise RuntimeError("injected prepublication crash")

    monkeypatch.setattr(backup_module, "_publish", fail)
    with pytest.raises(RuntimeError):
        getattr(AccessBackup(), operation)(
            source if operation == "backup" else bundle, tmp_path / "aborted"
        )
    assert not (tmp_path / "aborted").exists()
    assert rows(source) == before
    assert not list(tmp_path.glob(".access-stage-*"))


def test_stopped_source_not_backed_up_or_forked(source, tmp_path):
    schema.persist_stop(source)
    for operation in ("backup", "fork"):
        with pytest.raises(AccessRegistryError, match="STOPPED"):
            AccessBackup().backup(
                source, tmp_path / "bad"
            ) if operation == "backup" else AccessBackup().fork_scope(
                source, fork_request()
            )
    assert not (tmp_path / "bad").exists()


def test_corrupt_source_is_preserved_and_stopped_before_rw_open(
    source, tmp_path, monkeypatch
):
    with raw(source) as db:
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE access_scopes SET display_name=char(0)")
    original_bytes = source.read_bytes()
    opens = []
    connect = schema._connect

    def observed(path, *, writable):
        opens.append(writable)
        return connect(path, writable=writable)

    monkeypatch.setattr(schema, "_connect", observed)
    with pytest.raises(AccessRegistryError, match="CORRUPT"):
        AccessBackup().fork_scope(source, fork_request())
    assert opens == [False]
    assert source.read_bytes() == original_bytes
    assert schema.stop_path(source).exists()
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def fork_request():
    return ScopeFork(
        S1,
        AccessScope(S2, "independent"),
        ScopeLocatorRegistration(S2, 100, "file:///fork"),
    )


def test_fork_preserves_origin_history_and_grants_new_scope_inactive(source):
    before = rows(source)
    receipt = AccessBackup().fork_scope(source, fork_request())
    after = rows(source)
    assert receipt["original_history_rewritten"] is False
    assert after["local_access_grants"] == before["local_access_grants"]
    with AccessConnections(source) as store:
        assert store.history(S1).registrations == REGS[::-1]
        assert store.history(S2).registrations == (fork_request().registration,)
        assert not store.locator_enabled(fork_request().registration)
        assert not store.scope_context(S2).enabled
        assert not store.binding(S2, KEY.locator_text).enabled
        assert store.binding(S2, KEY.locator_text).repository_uuidv4 == R1
        assert store.configuration(S2, KEY.configuration_name).options_json == OPTIONS
        assert not store.configuration(S2, KEY.configuration_name).enabled
        assert not store.assignment(replace(KEY, scope_uuidv4=S2)).enabled
        assert store.current_grant(R1, S1).approved_at_us == 40
    # Immutable source rows and source settings all still exist exactly.
    for table in schema.TABLES:
        assert set(before[table]) <= set(after[table])
    assert receipt["rows_added"]["scope_locators"] == 1
    assert receipt["rows_added"]["local_access_grants"] == 0


def test_fork_does_not_duplicate_missing_context_or_invent_source_registration(source):
    req = ScopeFork(
        S3,
        AccessScope(S2, "empty fork"),
        ScopeLocatorRegistration(S2, 100, "file:///empty"),
    )
    AccessBackup().fork_scope(source, req)
    with AccessConnections(source) as store:
        assert store.history(S3).registrations == ()
        assert store.history(S2).registrations == (req.registration,)
        with pytest.raises(AccessRegistryError, match="NOT_FOUND"):
            store.scope_context(S2)


@pytest.mark.parametrize("bad", ["target-exists", "source-missing"])
def test_fork_conflicts_rollback(source, bad):
    request = fork_request()
    if bad == "target-exists":
        request = ScopeFork(
            S1, AccessScope(S3), ScopeLocatorRegistration(S3, 100, "file:///x")
        )
    else:
        request = replace(
            request, source_scope_uuidv4="950e8400-e29b-41d4-a716-446655440000"
        )
    before = rows(source)
    with pytest.raises(AccessRegistryError):
        AccessBackup().fork_scope(source, request)
    assert rows(source) == before


def test_fork_capacity_failure_rolls_back_new_identity_and_rows(source):
    before = rows(source)
    count = sum(map(len, before.values()))
    with pytest.raises(AccessRegistryError, match="LIMIT"):
        AccessBackup(AccessBackupLimits(max_rows=count)).fork_scope(
            source, fork_request()
        )
    assert rows(source) == before
    assert not schema.stop_path(source).exists()


def test_fork_commit_failure_rolls_back_entire_unit(source, monkeypatch):
    before = rows(source)
    connect = schema._connect

    class Broken:
        def __init__(self, db):
            self.db = db

        def __getattr__(self, k):
            return getattr(self.db, k)

        def commit(self):
            raise sqlite3.OperationalError("injected commit failure")

    def broken(path, *, writable):
        db = connect(path, writable=writable)
        return Broken(db) if writable else db

    monkeypatch.setattr(schema, "_connect", broken)
    with pytest.raises(sqlite3.OperationalError):
        AccessBackup().fork_scope(source, fork_request())
    assert rows(source) == before


def test_concurrent_fork_only_one_registration_commits(source):
    def run():
        try:
            AccessBackup().fork_scope(source, fork_request())
            return "ok"
        except AccessRegistryError as e:
            return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(results) == ["EXISTS", "ok"]
    assert len([r for r in rows(source)["scope_locators"] if r[0] == S2]) == 1


def test_application_fork_issues_uuid_and_records_new_actual_time(source):
    app = AccessMaintenance(AccessBackup(), clock_us=lambda: 200)
    receipt = app.fork_scope(source, S1, "file:///new", display_name="new")
    target = receipt["target_scope_uuidv4"]
    assert UUID(target).version == 4 and target not in (S1, S3)
    with AccessConnections(source) as store:
        assert store.history(target).registrations == (
            ScopeLocatorRegistration(target, 200, "file:///new"),
        )
        assert store.history(S1).registrations == REGS[::-1]


def test_read_only_restore_inputs_no_outbound_or_executor_activation(
    source, tmp_path, monkeypatch
):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("outbound execution")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    a = AccessBackup()
    a.backup(source, tmp_path / "b")
    a.inspect(tmp_path / "b")
    a.restore(tmp_path / "b", tmp_path / "r")
    a.fork_scope(source, fork_request())


def cli_environment():
    env = dict(os.environ)
    root = Path(__file__).resolve().parents[3]
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, (env.get("PYTHONPATH"), str(root / "src")))
    )
    return env


def test_cli_explicit_backup_inspect_restore_and_fork(source, tmp_path):
    prefix = [sys.executable, "-m", "repo_catalog.cli.access_maintenance"]
    operations = [
        [
            "backup",
            "--access-db",
            str(source),
            "--destination",
            str(tmp_path / "cli-backup"),
        ],
        ["inspect", "--bundle", str(tmp_path / "cli-backup")],
        [
            "restore",
            "--bundle",
            str(tmp_path / "cli-backup"),
            "--destination",
            str(tmp_path / "cli-restore"),
        ],
        [
            "fork",
            "--access-db",
            str(tmp_path / "cli-restore/access.sqlite3"),
            "--source-scope",
            S1,
            "--scope-uri",
            "file:///copy",
            "--target-scope",
            S2,
        ],
    ]
    for args in operations:
        result = subprocess.run(
            prefix + args,
            capture_output=True,
            text=True,
            check=False,
            env=cli_environment(),
        )
        assert result.returncode == 0, (args, result.stderr)
        assert json.loads(result.stdout)["status"] == "ok"
    result = subprocess.run(
        prefix + operations[2], capture_output=True, text=True, env=cli_environment()
    )
    assert result.returncode == 2 and json.loads(result.stderr)["code"] == "EXISTS"


def test_cli_diagnostics_do_not_echo_secret_paths(tmp_path):
    value = "do-not-log-secret"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repo_catalog.cli.access_maintenance",
            "inspect",
            "--bundle",
            str(tmp_path / value),
        ],
        capture_output=True,
        text=True,
        env=cli_environment(),
    )
    assert result.returncode == 2
    assert value not in result.stderr


def test_core_and_context_optional_no_default_activation():
    from repo_catalog.adapters.sqlite.p1_schema import STORES
    from scripts.audit_callsite_dependencies import ISOLATED_TARGET_MODULES

    assert "access" not in STORES
    for path in (
        "domain/access_backup.py",
        "domain/ports/access_backup.py",
        "adapters/sqlite/access_backup.py",
        "application/access_maintenance.py",
        "cli/access_maintenance.py",
    ):
        assert "src/repo_catalog/" + path in ISOLATED_TARGET_MODULES


@pytest.mark.parametrize("event", ["stop", "replacement", "cancel"])
def test_final_backup_guard_after_hashing(source, tmp_path, monkeypatch, event):
    original = backup_module._hash_file
    cancelled = False

    def changed(path, budget):
        nonlocal cancelled
        result = original(path, budget)
        if event == "stop":
            schema.persist_stop(source)
        elif event == "replacement":
            other = tmp_path / "replacement.sqlite3"
            schema.initialize(other)
            os.replace(other, source)
        else:
            cancelled = True
        return result

    monkeypatch.setattr(backup_module, "_hash_file", changed)
    with pytest.raises(AccessRegistryError):
        AccessBackup(cancelled=lambda: cancelled).backup(
            source, tmp_path / "unpublished"
        )
    assert not (tmp_path / "unpublished").exists()


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_process_exit_before_rename_leaves_only_unpublished_stage(
    source, bundle, tmp_path, operation
):
    destination = tmp_path / "killed"
    code = r"""
import os,sys
from repo_catalog.adapters.sqlite import access_backup as module
module._publish = lambda *args: os._exit(77)
getattr(module.AccessBackup(),sys.argv[1])(sys.argv[2],sys.argv[3])
"""
    before = rows(source)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            operation,
            str(source if operation == "backup" else bundle),
            str(destination),
        ],
        env=cli_environment(),
        capture_output=True,
    )
    assert result.returncode == 77, result.stderr
    assert not destination.exists()
    assert rows(source) == before
    assert list(tmp_path.glob(".access-stage-*"))
    # These are not valid named destinations or automatically activated stores.


def test_disabled_restore_requires_new_user_approval_before_workflow(
    source, bundle, tmp_path
):
    from repo_catalog.application.access_workflow import AccessWorkflow
    from repo_catalog.domain.access_workflow import AccessSelection

    dest = tmp_path / "workflow"
    AccessBackup().restore(bundle, dest)
    with AccessConnections(dest / "access.sqlite3", writable=True) as store:
        store.set_locator_enabled(REGS[-1], True)
        with AccessWorkflow(store) as workflow:
            shown = []
            with pytest.raises(AccessRegistryError, match="DECLINED"):
                workflow.approve(
                    workflow.begin_review(AccessSelection(R1, S1)),
                    lambda document: shown.append(document) or False,
                )
            assert len(shown) == 1
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(R1, S1)
