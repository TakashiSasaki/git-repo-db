"""Independent production-pair adversaries; only disposable SQLite catalogs.

These tests consume P1 values and production adapters. They do not certify P7
recovery, P8 activation, complete notes acquisition, or the public runtime.
"""

from __future__ import annotations

import hashlib
from contextlib import closing
from uuid import uuid4

import pytest
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.production_context import Context

from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator, validate_pair
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.domain.p1_context import (
    CoverageScope,
    FieldCandidate,
    FieldClock,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_coordination import AdmissionFailure, PairAdmission
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreCoverageScope,
    CoreFailure,
    NativeObject,
    native_oid,
)
from repo_catalog.domain.p1_coverage import CoverageClaim

REPOSITORY = "e82dde21-3201-49db-9273-2e58c9c9beaf"
INSTANCE = "f9976943-6d0c-4b14-879e-30b23591fb53"
SERVICE = "73b05ca2-eceb-460f-8909-84d015e81fc3"
SOURCE = "25695d63-2e0c-4a53-b2fd-0faf166fe2d5"
ORIGIN = "1c02424b-aa1d-4440-aea1-3fdcd37a0810"
CAPTURE = "3f51c7c0-ff7e-4612-9fd8-f70c1242e151"
RESOURCE = ResourceKey(SERVICE, "issue", "provider-global-71")
PROVENANCE = canonical({"source": "provider.example", "evidence": "original-event-71"})


class Budget:
    class Limits:
        note_bytes = 1024 * 1024

    limits = Limits()

    def require(self, unit, amount=1):
        assert type(amount) is int and amount >= 0

    def charge(self, unit, amount):
        assert type(amount) is int and amount >= 0


def build(path, roles=("core", "context", "operational", "search")):
    path.mkdir()
    for role in roles:
        initialize(path / f"{role}.sqlite3", role, REPOSITORY, INSTANCE)


def nominal(fmt="sha1", letter="a"):
    return OID(fmt, letter * (40 if fmt == "sha1" else 64))


def candidate(value, at=10):
    return FieldCandidate(
        RESOURCE,
        "title",
        canonical(value),
        FieldClock("provider:issue", at),
        PROVENANCE,
        at,
    )


def context_unit(directory, oid, value="original", at=10):
    def apply(db):
        with Context.for_transaction(db, directory) as context:
            context.provider(SERVICE, "github", "{}")
            context.repository(REPOSITORY, "{}")
            context.source(SOURCE, SERVICE, "{}")
            context.resource(RESOURCE, None)
            context.admit_field(candidate(value, at))
            context.link_core(RESOURCE, "head", *oid.key, PROVENANCE, lambda *_: True)

    return apply


def core_unit(oid, capture=None):
    def apply(db):
        with GitCore.for_transaction(db) as core:
            core.admit_object(oid)
            if capture is not None:
                core.admit_capture(capture)

    return apply


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_original_capture_retry_after_core_success_context_rollback(tmp_path, fmt):
    directory = tmp_path / "catalog"
    build(directory)
    oid = nominal(fmt)
    capture = Capture(
        ORIGIN, CAPTURE, REPOSITORY, "original-source", "refs/notes/review", oid
    )
    coordinator = PairCoordinator(directory)
    original_context = context_unit(directory, oid)

    def fail_context(db):
        original_context(db)
        raise ValueError("injected failure after genuine Context work")

    with pytest.raises(AdmissionFailure) as failed:
        coordinator.admit(core_unit(oid, capture), fail_context)
    assert failed.value.outcome == PairAdmission(True, False)
    with coordinator.snapshots() as pair:
        assert (
            tuple(pair.core.execute("SELECT * FROM captures").fetchone()) == capture.key
        )
        assert pair.context.execute("SELECT count(*) FROM resources").fetchone()[0] == 0
        assert pair.context.execute("SELECT count(*) FROM providers").fetchone()[0] == 0
    for _ in range(2):
        assert coordinator.admit(
            core_unit(oid, capture), original_context
        ) == PairAdmission(True, True)
    with coordinator.snapshots() as pair:
        assert pair.core.execute("SELECT count(*) FROM captures").fetchone()[0] == 1
        assert pair.core.execute("SELECT count(*) FROM git_objects").fetchone()[0] == 1
        assert pair.context.execute("SELECT count(*) FROM resources").fetchone()[0] == 1
        assert (
            pair.context.execute("SELECT count(*) FROM core_references").fetchone()[0]
            == 1
        )
        with Context.for_snapshot(pair.context, directory) as context:
            assert context.candidates(RESOURCE, "title") == (candidate("original"),)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_pair_snapshot_keeps_old_two_authority_state_during_production_write(
    tmp_path, fmt
):
    directory = tmp_path / "catalog"
    build(directory)
    coordinator, first, second = (
        PairCoordinator(directory),
        nominal(fmt),
        nominal(fmt, "b"),
    )
    coordinator.admit(core_unit(first), context_unit(directory, first))
    with coordinator.snapshots() as pair:
        initial_token = pair.token
        coordinator.admit(
            core_unit(second), context_unit(directory, second, "newer", 20)
        )
        assert pair.core.execute("SELECT count(*) FROM git_objects").fetchone()[0] == 1
        with Context.for_snapshot(pair.context, directory) as context:
            assert context.candidates(RESOURCE, "title") == (candidate("original"),)
        assert validate_pair(pair.core, pair.context) == initial_token
    with coordinator.snapshots() as pair:
        assert pair.token != initial_token
        assert pair.core.execute("SELECT count(*) FROM git_objects").fetchone()[0] == 2
        with Context.for_snapshot(pair.context, directory) as context:
            assert context.candidates(RESOURCE, "title") == (candidate("newer", 20),)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_derivative_loss_preserves_production_pair(tmp_path, fmt):
    directory = tmp_path / "catalog"
    build(directory)
    coordinator, oid = PairCoordinator(directory), nominal(fmt)
    coordinator.admit(core_unit(oid), context_unit(directory, oid))
    with coordinator.snapshots() as pair:
        original_token = pair.token
    for role in ("operational", "search"):
        (directory / f"{role}.sqlite3").unlink()
    with coordinator.snapshots() as pair:
        assert pair.token == original_token
        with Context.for_snapshot(pair.context, directory) as context:
            assert context.candidates(RESOURCE, "title") == (candidate("original"),)
    core = GitCore(directory / "core.sqlite3")
    try:
        assert core.scalar(oid, "type").canonical is None
    finally:
        core.close()


def test_both_authorities_keep_exact_five_column_coverage_with_own_scope(tmp_path):
    directory = tmp_path / "catalog"
    build(directory)
    oid = nominal()
    scope = CoreCoverageScope("object", (*oid.key, "metadata"))

    def apply(db):
        with GitCore.for_transaction(db) as core:
            core.admit_object(oid)
            core.admit_coverage_scope(scope)
            core.admit_coverage(CoverageClaim(scope, 10, "partial", '{"hint":"core"}'))

    def apply_context(db):
        context_unit(directory, oid)(db)
        with Context.for_transaction(db, directory) as context:
            owner = CoverageScope.resource(RESOURCE, "comments")
            context.scope(owner)
            context.admit_coverage(
                CoverageClaim(owner, 10, "unknown", '{"hint":"context"}')
            )

    coordinator = PairCoordinator(directory)
    coordinator.admit(apply, apply_context)
    with coordinator.snapshots() as pair:
        for role in ("core", "context"):
            with closing(connect(directory / f"{role}.sqlite3", role)) as db:
                columns = db.execute("PRAGMA table_xinfo(coverage_claims)").fetchall()
                assert len(columns) == 5
                assert all(row[6] == 0 for row in columns)
        assert (
            pair.core.execute(
                "SELECT owner_kind,owner_coordinates_json FROM coverage_claims"
            ).fetchone()[1]
            == scope.encoded
        )
        with Context.for_snapshot(pair.context, directory) as context:
            projection = context.coverage(CoverageScope.resource(RESOURCE, "comments"))
            assert projection.state == "unknown"
            assert not projection.known_empty


def test_core_only_and_context_only_are_independently_durable(tmp_path):
    core_directory, context_directory = tmp_path / "git-only", tmp_path / "context-only"
    build(core_directory, ("core",))
    build(context_directory, ("context",))
    oid = nominal("sha256")
    core = GitCore(core_directory / "core.sqlite3")
    try:
        core.admit_object(oid)
    finally:
        core.close()
    with Context.transaction(context_directory) as context:
        context.provider(SERVICE, "github", "{}")
        context.resource(RESOURCE, None)
        context.admit_field(candidate("durable without Git"))
    with Context.transaction(context_directory) as context:
        assert context.candidates(RESOURCE, "title") == (
            candidate("durable without Git"),
        )
    core = GitCore(core_directory / "core.sqlite3")
    try:
        assert core.scalar(oid, "type").canonical is None
    finally:
        core.close()
    assert not (core_directory / "context.sqlite3").exists()
    assert not (context_directory / "core.sqlite3").exists()


def test_detected_core_byte_corruption_permanently_fences_context_success(tmp_path):
    directory = tmp_path / "catalog"
    build(directory)
    body = b""
    native = NativeObject(
        OID("sha1", native_oid("sha1", "tree", body)),
        "tree",
        body,
        0,
        hashlib.sha256(body).hexdigest(),
    )
    core = GitCore(directory / "core.sqlite3")
    try:
        core.admit_metadata(native, str(uuid4()), Budget())
    finally:
        core.close()
    PairCoordinator(directory).admit(
        core_unit(native.oid), context_unit(directory, native.oid)
    )
    # Deliberately corrupt an already admitted representation with final schema
    # restored. This emulates damage outside the supported application boundary.
    with closing(connect(directory / "core.sqlite3", "core")) as db:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_retained_metadata_update'"
        ).fetchone()[0]
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("BEGIN IMMEDIATE")
        db.execute("DROP TRIGGER p1_immutable_retained_metadata_update")
        db.execute("UPDATE retained_metadata SET body=x'78'")
        db.execute(trigger)
        db.commit()
    core = GitCore(directory / "core.sqlite3")
    try:
        with pytest.raises(CoreFailure) as failed:
            core.read_metadata(native.oid)
        assert failed.value.code == "AUTHORITATIVE_CORRUPTION"
    finally:
        core.close()
    marker = directory / "p1-recovery-stop.json"
    assert marker.exists()
    original_marker = marker.read_bytes()
    for role in ("operational", "search"):
        (directory / f"{role}.sqlite3").unlink()
    with pytest.raises(Exception) as blocked:
        with Context.transaction(directory) as context:
            context.admit_field(candidate("must never commit", 30))
    assert getattr(blocked.value, "code", "") in {"RECOVERY_REQUIRED", "RECOVERY_STOP"}
    with pytest.raises(Exception) as blocked:
        PairCoordinator(directory).admit(
            core_unit(native.oid), context_unit(directory, native.oid)
        )
    assert getattr(blocked.value, "code", "") in {"RECOVERY_REQUIRED", "RECOVERY_STOP"}
    assert marker.read_bytes() == original_marker


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_durable_unavailable_context_reference_is_not_a_certified_pair(tmp_path, fmt):
    from repo_catalog.domain.production_context import CoreReference

    directory = tmp_path / "catalog"
    build(directory)
    oid = nominal(fmt)
    reference = CoreReference(RESOURCE, "base", oid, PROVENANCE)
    with Context.transaction(directory) as context:
        context.provider(SERVICE, "github", "{}")
        context.resource(RESOURCE, None)
        context.report_core_reference(
            reference, clock=FieldClock("provider:issue", 10), observed_at_us=10
        )
        unresolved = context.core_dependencies(RESOURCE)
        assert len(unresolved) == 1
        assert unresolved[0].reference == reference
        assert unresolved[0].available is False
        assert unresolved[0].required is False
        assert unresolved[0].candidate is not None
        assert unresolved[0].candidate.clock == FieldClock("provider:issue", 10)
        assert unresolved[0].candidate.provenance_json == PROVENANCE
        assert unresolved[0].candidate.observed_at_us == 10
    coordinator = PairCoordinator(directory)
    with coordinator.snapshots() as pair:
        with Context.for_snapshot(pair.context, directory) as context:
            assert context.core_dependencies(RESOURCE)[0].available is False
    assert not (directory / "p1-recovery-stop.json").exists()
    core = GitCore(directory / "core.sqlite3")
    try:
        core.admit_object(oid)
        assert core.scalar(oid, "type").canonical is None
    finally:
        core.close()
    with Context.transaction(directory) as context:
        context.link_core(
            RESOURCE,
            "base",
            *oid.key,
            PROVENANCE,
            lambda object_format, full_oid: (object_format, full_oid) == oid.key,
        )
    with coordinator.snapshots() as pair:
        with Context.for_snapshot(pair.context, directory) as context:
            resolved = context.core_dependencies(
                RESOURCE,
                lambda object_format, full_oid: bool(
                    pair.core.execute(
                        "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?",
                        (object_format, full_oid),
                    ).fetchone()
                ),
            )
            assert resolved
            assert all(item.reference == reference for item in resolved)
            assert all(item.available is True for item in resolved)
            assert any(item.required for item in resolved)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_forbidden_git_blob_retention_does_not_poison_legitimate_context_text(
    tmp_path, fmt
):
    directory = tmp_path / "catalog"
    build(directory)
    body = b"ordinary-file-candidate"
    native = NativeObject(
        OID(fmt, native_oid(fmt, "blob", body)),
        "blob",
        body,
        len(body),
        hashlib.sha256(body).hexdigest(),
    )
    core = GitCore(directory / "core.sqlite3")
    try:
        with pytest.raises(CoreFailure):
            core.admit_metadata(native, str(uuid4()), Budget())
        assert not core.sql("SELECT * FROM retained_metadata")
        assert not core.sql("SELECT * FROM retained_notes")
    finally:
        core.close()
    assert not (directory / "p1-recovery-stop.json").exists()
    with Context.transaction(directory) as context:
        # Same octets can be genuine Provider text; its domain, identity and
        # purpose remain Context, and do not license Git blob retention.
        digest = context.text(body.decode())
        assert digest == hashlib.sha256(body).hexdigest()
    with PairCoordinator(directory).snapshots() as pair:
        assert (
            pair.core.execute("SELECT count(*) FROM retained_metadata").fetchone()[0]
            == 0
        )
        assert (
            pair.context.execute("SELECT text_value FROM text_bodies").fetchone()[0]
            == body.decode()
        )


def test_partial_and_empty_source_inventories_preserve_positive_cross_store_state(
    tmp_path,
):
    from repo_catalog.domain.production_context import SourceInventory

    directory = tmp_path / "catalog"
    build(directory)
    oid = nominal()
    coordinator = PairCoordinator(directory)
    coordinator.admit(core_unit(oid), context_unit(directory, oid))
    with Context.transaction(directory) as context:
        context.associate_source(SOURCE, REPOSITORY)
        context.inventory(
            SourceInventory(
                SOURCE,
                '{"coverage_kind":"repositories"}',
                20,
                "partial",
                False,
                (),
                PROVENANCE,
            )
        )
        context.inventory(
            SourceInventory(
                SOURCE,
                '{"coverage_kind":"repositories"}',
                30,
                "complete",
                True,
                (),
                PROVENANCE,
            )
        )
        assert REPOSITORY in context.source_repositories(SOURCE)
    with coordinator.snapshots() as pair:
        assert pair.core.execute("SELECT count(*) FROM git_objects").fetchone()[0] == 1
        assert (
            pair.context.execute(
                "SELECT repository_uuidv4 FROM source_repositories"
            ).fetchone()[0]
            == REPOSITORY
        )
