"""Actual persistent WAL stores, subprocess death and POSIX process exclusion."""

import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_coordination import (
    PairCoordinator,
    catalog_gate,
    validate_pair,
)
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_coordination import (
    AdmissionFailure,
    CoordinationError,
    PairAdmission,
)
from repo_catalog.domain.p1_core import OID as TypedOID
from tests.support.context_admission import fixture_context, fixture_service

REPOSITORY = "9ebbe38a-f937-40e6-a99c-701835ebcf10"
INSTANCE = "f7ebfbbf-53cc-43db-98df-d80326e80922"
PROVIDER = "e19d36ab-3876-4c36-b998-183827af06ef"
OID = "a" * 40
ISSUE = ResourceKey.from_native(PROVIDER, "issue", "7")


def fixture_authority(*, extra_resources=()):
    """Finite declarations for this file's one synthetic Context unit."""
    service, _ = fixture_service(
        DependencySet(
            resources=frozenset({ISSUE, *extra_resources}),
            repositories=frozenset({REPOSITORY}),
            provider_registrations=frozenset({PROVIDER}),
            object_oids=frozenset({TypedOID("sha1", OID)}),
        )
    )
    return service, fixture_context(service)


def admit_fixture(coordinator, core, context, **kwargs):
    """Bind finite authority at construction of the real commit owner.

    Copy only the supplied coordinator's public catalog/read configuration. The
    original object's read snapshots and their tokens remain independent.
    """
    authorization, admission = fixture_authority()
    owner = PairCoordinator(
        coordinator.directory,
        read_limits=coordinator.read_limits,
        metadata_only=coordinator.metadata_only,
        authorization=authorization,
    )
    return owner.admit(core, context, admission=admission, **kwargs)


def build(directory: Path, *, instance=INSTANCE, repository=REPOSITORY):
    directory.mkdir()
    for role in ("core", "context", "operational", "search"):
        initialize(directory / f"{role}.sqlite3", role, repository, instance)


def core_unit(db):
    db.execute("INSERT OR IGNORE INTO git_objects VALUES('sha1',?)", (OID,))


def context_unit(value):
    # A normal callback receives the coordinator's explicitly bound transaction;
    # standalone invalid-pair fixtures pass their owned Context capability.
    if isinstance(value, ContextStore):
        store, db = value, value.db
    else:
        db = value
        store = ContextStore(db)
    db.execute("INSERT OR IGNORE INTO providers VALUES(?,'github','{}')", (PROVIDER,))
    db.execute("INSERT OR IGNORE INTO repository_context VALUES(?,'{}')", (REPOSITORY,))
    store.resource(ISSUE, REPOSITORY)
    db.execute(
        "INSERT OR IGNORE INTO core_references VALUES(?,?,?,'head','sha1',?,?)",
        (
            *ISSUE.coordinates(),
            OID,
            '{"evidence":"actual-event-7","source":"provider.example"}',
        ),
    )


def context_without_core(directory):
    """Construct the existing deliberately invalid pair for backup validation.

    The Context-only transaction is authorized and locally well formed; this
    fixture deliberately has no matching Core object for the certification test.
    """
    authorization, admission = fixture_authority()
    with contextlib.closing(connect(directory / "context.sqlite3", "context")) as db:
        with Context.owned_transaction(
            db, directory, authorization=authorization, admission=admission
        ) as store:
            context_unit(store)


def counts(directory):
    with PairCoordinator(directory).snapshots() as pair:
        return (
            pair.core.execute("SELECT count(*) FROM git_objects").fetchone()[0],
            pair.context.execute("SELECT count(*) FROM resources").fetchone()[0],
            pair.context.execute("SELECT count(*) FROM core_references").fetchone()[0],
        )


def child_code(code, directory, *args, stdin=None):
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[3] / "src"))
    return subprocess.Popen(
        [sys.executable, "-c", code, str(directory), *map(str, args)],
        env=env,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


@pytest.mark.parametrize(
    ("cut", "expected"),
    [
        ("before_core_commit", (0, 0, 0)),
        ("after_core_commit", (1, 0, 0)),
        ("during_context", (1, 0, 0)),
        ("after_context_commit", (1, 1, 1)),
    ],
)
def test_crash_cuts_preserve_independent_commits_and_exact_retry(
    tmp_path, cut, expected
):
    directory = tmp_path / "live"
    build(directory)
    code = """
from tests.integration.p1.test_coordination import admit_fixture
import os,sys
from pathlib import Path
from tests.integration.p1.test_coordination import core_unit, context_unit
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
def cut(point):
    if point == sys.argv[2]: os._exit(86)
admit_fixture(PairCoordinator(Path(sys.argv[1])), core_unit,context_unit,cut=cut)
"""
    process = child_code(code, directory, cut)
    _, err = process.communicate(timeout=15)
    assert process.returncode == 86, err
    assert counts(directory) == expected
    coordinator = PairCoordinator(directory)
    admit_fixture(coordinator, core_unit, context_unit)
    with coordinator.snapshots() as pair:
        token = pair.token
    admit_fixture(coordinator, core_unit, context_unit)
    with coordinator.snapshots() as pair:
        assert pair.token == token
    assert counts(directory) == (1, 1, 1)


def test_context_failure_rolls_back_whole_unit_without_erasing_core(tmp_path):
    directory = tmp_path / "live"
    build(directory)

    def fail(db):
        context_unit(db)
        raise ValueError("after unit writes")

    with pytest.raises(AdmissionFailure) as failure:
        admit_fixture(PairCoordinator(directory), core_unit, fail)
    assert failure.value.outcome == PairAdmission(True, False)
    assert isinstance(failure.value.cause, ValueError)
    assert counts(directory) == (1, 0, 0)


def test_invalid_cross_store_reference_rejected_at_context_commit(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    with pytest.raises(CoordinationError, match="MISSING_CORE_REFERENCE"):
        admit_fixture(PairCoordinator(directory), lambda db: None, context_unit)
    assert counts(directory) == (0, 0, 0)
    assert not (directory / "p1-recovery-stop.json").exists()


def test_pinned_pair_and_naive_mixed_snapshot_counterexample(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    coordinator = PairCoordinator(directory)
    with coordinator.snapshots() as pair:
        old_token = pair.token
        admit_fixture(coordinator, core_unit, context_unit)
        assert pair.core.execute("SELECT count(*) FROM git_objects").fetchone()[0] == 0
        assert (
            pair.context.execute("SELECT count(*) FROM core_references").fetchone()[0]
            == 0
        )
        assert validate_pair(pair.core, pair.context) == old_token
    with coordinator.snapshots() as pair:
        assert pair.token != old_token

    # Reset creates a second disposable catalog to demonstrate the actual bug.
    mixed = tmp_path / "mixed"
    build(mixed)
    with (
        contextlib.closing(connect(mixed / "core.sqlite3", "core")) as old_core,
        contextlib.closing(
            connect(mixed / "context.sqlite3", "context")
        ) as new_context,
    ):
        old_core.execute("BEGIN")
        old_core.execute("SELECT * FROM git_objects").fetchall()
        admit_fixture(PairCoordinator(mixed), core_unit, context_unit)
        with pytest.raises(CoordinationError, match="MISSING_CORE_REFERENCE"):
            validate_pair(old_core, new_context)


def test_os_reader_gate_blocks_between_two_commits(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    code = """
from tests.integration.p1.test_coordination import admit_fixture
from pathlib import Path
import sys
from tests.integration.p1.test_coordination import core_unit,context_unit
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
def cut(point):
    if point == 'after_core_commit':
        print('cut',flush=True)
        sys.stdin.readline()
admit_fixture(PairCoordinator(Path(sys.argv[1])), core_unit,context_unit,cut=cut)
"""
    process = child_code(code, directory, stdin=subprocess.PIPE)
    finished = threading.Event()
    result = []

    def read():
        result.append(counts(directory))
        finished.set()

    try:
        assert process.stdout.readline().strip() == "cut"
        # Real nonblocking flock attempt proves lock acquisition was attempted.
        import fcntl

        with (directory / "p1-writer.lock").open("a+b") as handle:
            with pytest.raises(BlockingIOError):
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        thread = threading.Thread(target=read)
        thread.start()
        assert not finished.wait(0.1)
        _, error = process.communicate("continue\n", timeout=15)
        assert process.returncode == 0, error
        assert finished.wait(5)
        thread.join()
        assert result == [(1, 1, 1)]
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


@pytest.mark.parametrize("role", ["operational", "search", "context"])
def test_authority_availability_after_store_loss(tmp_path, role):
    directory = tmp_path / "live"
    build(directory)
    coordinator = PairCoordinator(directory)
    admit_fixture(coordinator, core_unit, context_unit)
    (directory / f"{role}.sqlite3").unlink()
    with coordinator.core_snapshot() as core:
        assert core.execute("SELECT object_oid FROM git_objects").fetchone()[0] == OID
        with pytest.raises(sqlite3.DatabaseError, match="authorized"):
            core.execute("INSERT INTO git_objects VALUES('sha1',?)", ("b" * 40,))
    if role == "context":
        with pytest.raises(CoordinationError, match="AUTHORITY_UNAVAILABLE"):
            with coordinator.snapshots():
                pass
    else:
        assert counts(directory) == (1, 1, 1)
        initialize(directory / f"{role}.sqlite3", role, REPOSITORY, INSTANCE)
        assert counts(directory) == (1, 1, 1)


@pytest.mark.parametrize("identity", ["repository", "instance"])
def test_mismatched_repository_and_catalog_instances_rejected(tmp_path, identity):
    directory, other = tmp_path / "live", tmp_path / "other"
    build(directory)
    build(
        other,
        repository=str(uuid4()) if identity == "repository" else REPOSITORY,
        instance=str(uuid4()) if identity == "instance" else INSTANCE,
    )
    shutil.copyfile(other / "context.sqlite3", directory / "context.sqlite3")
    with pytest.raises(CoordinationError, match="PAIR_IDENTITY"):
        with PairCoordinator(directory).snapshots():
            pass


@pytest.mark.parametrize(
    "cut", ["after_core_backup", "after_context_backup", "before_certificate"]
)
def test_interrupted_backup_never_certifies_candidate(tmp_path, cut):
    directory, destination = tmp_path / "live", tmp_path / "candidate"
    build(directory)
    admit_fixture(PairCoordinator(directory), core_unit, context_unit)
    code = """
import os,sys
from pathlib import Path
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
def cut(point):
    if point==sys.argv[2]: os._exit(86)
PairCoordinator(Path(sys.argv[1])).backup_candidate(Path(sys.argv[3]),cut=cut)
"""
    process = child_code(code, directory, cut, destination)
    _, error = process.communicate(timeout=15)
    assert process.returncode == 86, error
    assert not (destination / "p1-pair-candidate.json").exists()
    with pytest.raises(FileNotFoundError):
        PairCoordinator.validate_backup(destination)
    with pytest.raises(FileExistsError):
        PairCoordinator(directory).backup_candidate(destination)
    token = PairCoordinator(directory).backup_candidate(tmp_path / "fresh")
    assert PairCoordinator.validate_backup(tmp_path / "fresh") == token


def test_backup_gate_and_invalid_pair_pre_certification(tmp_path):
    directory = tmp_path / "live"
    build(directory)

    def probe(point):
        if point != "after_core_backup":
            return
        code = """
import fcntl,sys
from pathlib import Path
with (Path(sys.argv[1])/'p1-writer.lock').open('a+b') as handle:
    try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: print('blocked')
    else: print('UNFENCED')
"""
        process = child_code(code, directory)
        output, error = process.communicate(timeout=15)
        assert process.returncode == 0, error
        assert output.strip() == "blocked"

    destination = tmp_path / "candidate"
    PairCoordinator(directory).backup_candidate(destination, cut=probe)
    PairCoordinator.validate_backup(destination)
    context_without_core(directory)  # Locally valid, missing portable Core dependency.
    bad = tmp_path / "bad"
    with pytest.raises(CoordinationError, match="MISSING_CORE_REFERENCE"):
        PairCoordinator(directory).backup_candidate(bad)
    assert not (bad / "p1-pair-candidate.json").exists()


def test_backup_revalidates_domains_even_if_file_digest_is_updated(tmp_path):
    directory, destination = tmp_path / "live", tmp_path / "candidate"
    build(directory)
    PairCoordinator(directory).backup_candidate(destination)
    context_without_core(destination)
    manifest_path = destination / "p1-pair-candidate.json"
    manifest = json.loads(manifest_path.read_text())
    import hashlib

    manifest["files"]["context.sqlite3"] = hashlib.sha256(
        (destination / "context.sqlite3").read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(CoordinationError, match="MISSING_CORE_REFERENCE"):
        PairCoordinator.validate_backup(destination)


def test_recovery_stop_survives_restart_and_derivative_loss(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    coordinator = PairCoordinator(directory)
    with coordinator.snapshots() as pair:
        coordinator.stop("detected authoritative corruption")
        with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
            pair.core.execute("SELECT * FROM git_objects").fetchall()
    for role in ("operational", "search"):
        (directory / f"{role}.sqlite3").unlink()
    for operation in (
        lambda: admit_fixture(PairCoordinator(directory), core_unit, context_unit),
        lambda: PairCoordinator(directory).backup_candidate(tmp_path / "blocked"),
    ):
        with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
            operation()
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        with PairCoordinator(directory).core_snapshot():
            pass
    assert not hasattr(coordinator, "activate")


def test_gate_explicitly_rejects_unsupported_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "unsupported")
    with pytest.raises(CoordinationError, match="UNSUPPORTED_PLATFORM"):
        with catalog_gate(tmp_path, exclusive=False):
            pass


@pytest.mark.parametrize(
    "statement",
    ["COMMIT", "ROLLBACK", "PRAGMA query_only=OFF", "DROP TABLE git_objects"],
)
def test_pinned_read_boundary_rejects_snapshot_escape(tmp_path, statement):
    directory = tmp_path / "live"
    build(directory)
    with PairCoordinator(directory).snapshots() as pair:
        with pytest.raises(sqlite3.DatabaseError, match="authorized"):
            pair.core.execute(statement)
        assert pair.core.in_transaction


@pytest.mark.parametrize(
    "mode",
    [
        "method",
        "sql",
        "script",
        "reset_authorizer",
        "cursor_connection",
        "ddl",
        "pragma",
    ],
)
def test_callback_cannot_commit_enclosing_transaction(tmp_path, mode):
    directory = tmp_path / "live"
    build(directory)

    def early_commit(db):
        core_unit(db)
        if mode == "method":
            db.commit()
        elif mode == "script":
            db.executescript("SELECT 1;")
        elif mode == "cursor_connection":
            db.execute("SELECT 1").connection.commit()
        elif mode == "ddl":
            db.execute("DROP TABLE git_objects")
        elif mode == "pragma":
            db.execute("PRAGMA recursive_triggers=OFF")
        else:
            if mode == "reset_authorizer":
                db.set_authorizer(None)
            db.execute("COMMIT")

    with pytest.raises(AdmissionFailure) as failure:
        admit_fixture(PairCoordinator(directory), early_commit, context_unit)
    assert failure.value.outcome == PairAdmission(False, False)
    assert counts(directory) == (0, 0, 0)


def test_typed_core_unit_uses_coordinator_transaction_without_outer_commit(tmp_path):
    from repo_catalog.adapters.sqlite.p1_core import Core
    from repo_catalog.domain.p1_core import OID as TypedOID
    from repo_catalog.domain.p1_core import CoreFailure

    directory = tmp_path / "live"
    build(directory)
    expired = []

    def typed_core(db):
        with Core.for_transaction(db) as core:
            core.admit_object(TypedOID("sha1", OID))
            expired.append(core)

    def failed_context(db):
        context_unit(db)
        raise ValueError("after Context writes")

    with pytest.raises(AdmissionFailure) as failure:
        admit_fixture(PairCoordinator(directory), typed_core, failed_context)
    assert failure.value.outcome == PairAdmission(True, False)
    assert counts(directory) == (1, 0, 0)
    with pytest.raises(CoreFailure) as expired_failure:
        expired[0].admit_object(TypedOID("sha1", "b" * 40))
    assert expired_failure.value.code == "CAPABILITY_EXPIRED"
    admit_fixture(PairCoordinator(directory), typed_core, context_unit)
    assert counts(directory) == (1, 1, 1)


def test_read_capabilities_expire_and_cannot_expose_mutable_connection(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    with PairCoordinator(directory).snapshots() as pair:
        cursor = pair.core.execute("SELECT * FROM git_objects")
        assert cursor.connection is pair.core
        assert not hasattr(cursor.connection, "set_authorizer")
        assert not hasattr(cursor.connection, "commit")
    with pytest.raises(CoordinationError, match="SNAPSHOT_EXPIRED"):
        cursor.fetchall()
    with pytest.raises(CoordinationError, match="SNAPSHOT_EXPIRED"):
        pair.core.execute("SELECT 1")


def test_detected_durable_context_corruption_stops_catalog(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    admit_fixture(PairCoordinator(directory), core_unit, context_unit)
    with contextlib.closing(connect(directory / "context.sqlite3", "context")) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("DELETE FROM providers")  # Deliberate unsupported FK damage.
    with pytest.raises(CoordinationError, match="FOREIGN_KEY"):
        with PairCoordinator(directory).snapshots():
            pass
    assert (directory / "p1-recovery-stop.json").exists()
    with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
        with PairCoordinator(directory).core_snapshot():
            pass


def test_receiver_detected_corruption_in_admission_stops_after_gate_release(tmp_path):
    from repo_catalog.domain.p1_core import CoreFailure

    directory = tmp_path / "live"
    build(directory)

    def detected(db):
        raise CoreFailure("AUTHORITATIVE_CORRUPTION", "retained bytes", "mismatch")

    with pytest.raises(AdmissionFailure) as failure:
        admit_fixture(PairCoordinator(directory), detected, context_unit)
    assert failure.value.outcome == PairAdmission(False, False)
    assert (directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("operation", ["admission", "core_read", "pair_read", "backup"])
def test_corruption_during_connection_open_stops_before_transaction_exists(
    tmp_path, operation
):
    directory = tmp_path / "live"
    build(directory)
    (directory / "core.sqlite3").write_bytes(b"broken sqlite header")
    with pytest.raises(sqlite3.DatabaseError) as failure:
        coordinator = PairCoordinator(directory)
        if operation == "admission":
            admit_fixture(coordinator, core_unit, context_unit)
        elif operation == "core_read":
            with coordinator.core_snapshot():
                pass
        elif operation == "pair_read":
            with coordinator.snapshots():
                pass
        else:
            coordinator.backup_candidate(tmp_path / "candidate")
    assert failure.value.sqlite_errorcode == sqlite3.SQLITE_NOTADB
    assert (directory / "p1-recovery-stop.json").exists()


def test_corruption_stop_precedes_gate_release_even_if_detector_dies(tmp_path):
    directory = tmp_path / "live"
    build(directory)
    detector_code = """
from tests.integration.p1.test_coordination import admit_fixture
import sys
from pathlib import Path
import repo_catalog.adapters.sqlite.core_coordination as c
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.domain.p1_core import CoreFailure
original=c.persist_catalog_stop
def stopped(directory,reason):
    original(directory,reason)
    print('marker-persisted',flush=True)
    sys.stdin.readline()
c.persist_catalog_stop=stopped
def detect(db):
    raise CoreFailure('AUTHORITATIVE_CORRUPTION','retained bytes','mismatch')
admit_fixture(PairCoordinator(Path(sys.argv[1])), detect,lambda db:None)
"""
    writer_code = """
from tests.integration.p1.test_coordination import admit_fixture
import sys
from pathlib import Path
from tests.integration.p1.test_coordination import core_unit,context_unit
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.domain.p1_coordination import CoordinationError
try: admit_fixture(PairCoordinator(Path(sys.argv[1])), core_unit,context_unit)
except CoordinationError as error: print(error.code,flush=True)
else: print('COMMITTED',flush=True)
"""
    detector = child_code(detector_code, directory, stdin=subprocess.PIPE)
    writer = None
    try:
        assert detector.stdout.readline().strip() == "marker-persisted"
        assert (directory / "p1-recovery-stop.json").exists()
        writer = child_code(writer_code, directory)
        # Die at the formerly unsafe transition: before rollback/gate release.
        detector.kill()
        detector.communicate(timeout=15)
        output, error = writer.communicate(timeout=15)
        assert writer.returncode == 0, error
        assert output.strip() == "RECOVERY_REQUIRED"
        for role, table in (("core", "git_objects"), ("context", "resources")):
            with contextlib.closing(connect(directory / f"{role}.sqlite3", role)) as db:
                assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        for role in ("operational", "search"):
            (directory / f"{role}.sqlite3").unlink()
        with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
            admit_fixture(PairCoordinator(directory), core_unit, context_unit)
    finally:
        for process in (detector, writer):
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()


def test_next_supported_writer_cannot_enter_during_stop_transition(
    tmp_path, monkeypatch
):
    import repo_catalog.adapters.sqlite.core_coordination as coordination
    from repo_catalog.domain.p1_core import CoreFailure

    directory = tmp_path / "live"
    build(directory)
    original, observed = coordination.persist_catalog_stop, []

    def transition(directory, reason):
        original(directory, reason)
        with pytest.raises(CoordinationError, match="RECOVERY_REQUIRED"):
            admit_fixture(PairCoordinator(directory), core_unit, context_unit)
        observed.append("refused before detector unwinds")

    monkeypatch.setattr(coordination, "persist_catalog_stop", transition)

    def detected(db):
        raise CoreFailure("AUTHORITATIVE_CORRUPTION", "retained bytes", "mismatch")

    with pytest.raises(AdmissionFailure):
        admit_fixture(PairCoordinator(directory), detected, context_unit)
    assert observed


@pytest.mark.parametrize(
    "point,core_count", [("before_core_commit", 0), ("during_context", 1)]
)
def test_stop_outside_writer_gate_fences_inflight_commit(tmp_path, point, core_count):
    directory = tmp_path / "live"
    build(directory)
    code = """
from tests.integration.p1.test_coordination import admit_fixture
import json,sys
from pathlib import Path
from tests.integration.p1.test_coordination import core_unit,context_unit
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.domain.p1_coordination import AdmissionFailure
def cut(point):
    if point==sys.argv[2]:
        print('before-commit',flush=True)
        sys.stdin.readline()
try: admit_fixture(PairCoordinator(Path(sys.argv[1])), core_unit,context_unit,cut=cut)
except AdmissionFailure as error:
    print(json.dumps([error.cause.code,error.outcome.core_committed,error.outcome.context_committed]),flush=True)
else: print('COMMITTED',flush=True)
"""
    process = child_code(code, directory, point, stdin=subprocess.PIPE)
    try:
        assert process.stdout.readline().strip() == "before-commit"
        # A pinned read detects corruption after releasing the initial gate.
        # stop() must publish its fence immediately without waiting for writer.
        PairCoordinator(directory).stop("authoritative corruption detected by reader")
        output, error = process.communicate("continue\n", timeout=15)
        assert process.returncode == 0, error
        assert json.loads(output.strip()) == [
            "RECOVERY_REQUIRED",
            bool(core_count),
            False,
        ]
        with contextlib.closing(connect(directory / "core.sqlite3", "core")) as db:
            assert (
                db.execute("SELECT count(*) FROM git_objects").fetchone()[0]
                == core_count
            )
        with contextlib.closing(
            connect(directory / "context.sqlite3", "context")
        ) as db:
            assert db.execute("SELECT count(*) FROM resources").fetchone()[0] == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_stop_outside_backup_gate_prevents_certificate(tmp_path):
    directory, destination = tmp_path / "live", tmp_path / "candidate"
    build(directory)
    code = """
import sys
from pathlib import Path
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.domain.p1_coordination import CoordinationError
def cut(point):
    if point=='before_certificate':
        print('before-certificate',flush=True)
        sys.stdin.readline()
try: PairCoordinator(Path(sys.argv[1])).backup_candidate(Path(sys.argv[2]),cut=cut)
except CoordinationError as error: print(error.code,flush=True)
else: print('CERTIFIED',flush=True)
"""
    process = child_code(code, directory, destination, stdin=subprocess.PIPE)
    try:
        assert process.stdout.readline().strip() == "before-certificate"
        PairCoordinator(directory).stop("authoritative corruption detected by reader")
        output, error = process.communicate("continue\n", timeout=15)
        assert process.returncode == 0, error
        assert output.strip() == "RECOVERY_REQUIRED"
        assert not (destination / "p1-pair-candidate.json").exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


@pytest.mark.parametrize("operation", ["snapshot", "backup"])
def test_existing_embedded_reference_is_revalidated_before_certification(
    tmp_path, operation
):
    from repo_catalog.adapters.sqlite.p1_core import Core
    from repo_catalog.domain.p1_core import CoreFailure, RelationGroup, RelationMember
    from tests.integration.p1.test_core import oid, provenance

    directory = tmp_path / "live"
    build(directory)
    core = Core(directory / "core.sqlite3")
    core.admit_group(
        RelationGroup(
            oid(),
            "commit_parents",
            "entire list",
            "complete",
            (RelationMember(0, oid("b")),),
            provenance(),
        )
    )
    core.close()
    # Simulate persisted corruption with the final schema restored exactly.
    # Ordinary SQLite checks cannot see a foreign key embedded in whole JSON.
    with contextlib.closing(connect(directory / "core.sqlite3", "core")) as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_git_objects_delete'"
        ).fetchone()[0]
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TRIGGER p1_immutable_git_objects_delete")
        db.execute("DELETE FROM git_objects WHERE object_oid=?", ("b" * 40,))
        db.execute(trigger)
        db.commit()
        assert [tuple(row) for row in db.execute("PRAGMA integrity_check")] == [("ok",)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(CoreFailure) as error:
        if operation == "snapshot":
            with PairCoordinator(directory).snapshots():
                pass
        else:
            PairCoordinator(directory).backup_candidate(tmp_path / "candidate")
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (directory / "p1-recovery-stop.json").exists()
    assert not (tmp_path / "candidate/p1-pair-candidate.json").exists()
