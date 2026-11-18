"""ADR 0036 query and backup integration against real local observations."""

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.adapters.sqlite.p1_schema import (
    connect,
    initialize,
    register_functions,
)
from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
from repo_catalog.adapters.sqlite.repository_recovery_validation import (
    RefValidationBudgetError,
)
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_repository import OID, RepositoryFailure
from repo_catalog.domain.recovery import (
    BackupScope,
    CorruptionDetectedError,
    RecoveryBudget,
    RestoreValidationError,
)
from tests.integration.p1 import test_repository as p1_fixtures
from tests.integration.p1.test_ref_coverage_i3 import proof_fixture
from tests.integration.p1.test_repository import Budget
from tests.integration.p4 import conftest as p4_fixtures
from tests.integration.p4.conftest import fixture_note
from tests.integration.p4.test_ref_observation_i2 import discover

acquisition = p4_fixtures.acquisition
p1_repository_fixture = p1_fixtures.repository_store


def test_ref_body_and_proof_require_checked_typed_read(acquisition):
    app, _, _, repository, origin, *_ = acquisition
    _, target, _ = fixture_note(acquisition)
    result = discover(app, repository, origin, str(uuid4()))
    claim = result.enumerations[0].links[0].claim
    app.acquire_ref_note(claim, target)

    for table, column in (
        ("ref_retained_notes", "body"),
        ("ref_retained_notes", "proof_bundle"),
        ("notes_mapping_evidence", "proof_bundle"),
    ):
        with pytest.raises(sqlite3.DatabaseError, match="prohibited"):
            app.repository_store.sql(f"SELECT {column} FROM {table}")

    projection = app.repository_store.notes_mapping_projection(
        claim, target, "git-notes", "1", "native-notes-tree", app.work
    )
    mapping = projection.evidence[0].mapping
    assert (
        app.repository_store.read_ref_note(claim, mapping, app.work)
        == b"\0\xffbinary\r\n"
    )


def test_each_ref_note_copy_is_checked_individually(acquisition):
    app, _, _, repository, origin, repository_path, _ = acquisition
    _, target, note = fixture_note(acquisition)
    results = discover(app, repository, origin, str(uuid4())).enumerations
    claims = [event.links[0].claim for event in results]
    for claim in claims:
        app.acquire_ref_note(claim, target)
    copies = app.repository_store.sql(
        "SELECT physical_copy_uuidv4 FROM ref_retained_notes ORDER BY physical_copy_uuidv4"
    )
    assert len(copies) == 2
    restored_claims = set()
    for (copy,) in copies:
        stored_claim, evidence, native = app.repository_store.read_ref_note_copy(
            note, copy, app.work
        )
        restored_claims.add(stored_claim)
        assert evidence.mapping.root_object_oid == stored_claim.root_object_oid
        assert evidence.provenance.qualification == "receiver_intrinsic"
        assert native.object_oid == note and native.native_type == "blob"
        assert native.body == b"\0\xffbinary\r\n"
    assert restored_claims == set(claims)
    with pytest.raises(RepositoryFailure) as missing:
        app.repository_store.read_ref_note_copy(note, str(uuid4()), app.work)
    assert missing.value.code == "NOTES_ROLE_UNAVAILABLE"
    small = UnlimitedWorkBudget(work_limits={"input_bytes": 8})
    with pytest.raises(RepositoryFailure) as exceeded:
        app.repository_store.read_ref_note_copy(note, copies[0][0], small)
    assert exceeded.value.code == "BUDGET"
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


def test_budget_callback_cannot_borrow_checked_byte_capability(acquisition):
    app, _, _, repository, origin, *_ = acquisition
    _, target, note = fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.acquire_ref_note(claim, target)
    copy = app.repository_store.sql(
        "SELECT physical_copy_uuidv4 FROM ref_retained_notes"
    )[0][0]

    class ProbeBudget:
        def __init__(self):
            self.leaked = []
            self.blocked = 0

        def inspect(self):
            try:
                self.leaked.extend(
                    app.repository_store.sql("SELECT body FROM ref_retained_notes")
                )
            except sqlite3.DatabaseError:
                self.blocked += 1

        @property
        def limits(self):
            self.inspect()
            return app.work.limits

        def require(self, unit, amount=1):
            self.inspect()
            app.work.require(unit, amount)

        def charge(self, unit, amount):
            self.inspect()
            app.work.charge(unit, amount)

        def abandon(self, unit):
            self.inspect()
            app.work.abandon(unit)

    probe = ProbeBudget()
    _, evidence, _ = app.repository_store.read_ref_note_copy(note, copy, probe)
    app.repository_store.notes_mapping_projection(
        claim, target, "git-notes", "1", "native-notes-tree", probe
    )
    app.repository_store.read_ref_note(claim, evidence.mapping, probe)
    assert probe.blocked > 0 and not probe.leaked


def test_corrupt_selected_ref_copy_stops_even_when_another_copy_is_sound(acquisition):
    app, _, _, repository, origin, repository_path, _ = acquisition
    _, target, note = fixture_note(acquisition)
    claims = [
        e.links[0].claim
        for e in discover(app, repository, origin, str(uuid4())).enumerations
    ]
    for claim in claims:
        app.acquire_ref_note(claim, target)
    copies = [
        row[0]
        for row in app.repository_store.sql(
            "SELECT physical_copy_uuidv4 FROM ref_retained_notes ORDER BY physical_copy_uuidv4"
        )
    ]
    db = connect(repository_path, "repository")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_retained_notes_update'"
        ).fetchone()[0]
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("DROP TRIGGER p1_immutable_ref_retained_notes_update")
        db.execute(
            "UPDATE ref_retained_notes SET body=zeroblob(size) WHERE physical_copy_uuidv4=?",
            (copies[1],),
        )
        db.execute(trigger)
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.commit()
    finally:
        db.close()
    assert (
        app.repository_store.read_ref_note_copy(note, copies[0], app.work)[2].body
        == b"\0\xffbinary\r\n"
    )
    with pytest.raises(RepositoryFailure) as corrupt:
        app.repository_store.read_ref_note_copy(note, copies[1], app.work)
    assert corrupt.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (repository_path.parent / "p1-recovery-stop.json").exists()


def test_query_preserves_scoped_claims_evidence_and_modes(acquisition):
    app, _, fmt, repository, origin, repository_path, _ = acquisition
    _, target, _ = fixture_note(acquisition)
    result = discover(app, repository, origin, str(uuid4()), ("refs/notes/missing",))
    first, second = (item.links[0].claim for item in result.enumerations[:2])
    absent_event = next(
        item
        for item in result.enumerations
        if any(link.derivation == "absence" for link in item.links)
    )
    absent = absent_event.links[0].claim
    app.acquire_ref_note(first, target)
    competing = replace(
        first,
        provenance=replace(first.provenance, coordinate="other-report"),
        root_object_oid=OID(fmt, "b" * (40 if fmt == "sha1" else 64)),
    )
    app.repository_store.admit_ref_observation_claim(competing)

    for mode in ("auto", "repository_only"):
        service = ProductionQueryService(repository_path.parent, mode=mode)
        assert service.detect_mode() == "repository_only"
        projection = service.get_ref_observation(first.ref_observation_key, app.work)
        assert projection.conflict and set(projection.claims) == {first, competing}
        missing = service.get_ref_observation(absent.ref_observation_key, app.work)
        assert missing.claims == (absent,) and absent.root_object_oid is None
        assert (
            service.get_ref_enumeration(*absent_event.event.identity, app.work)
            == absent_event
        )
        mapping_view = service.get_notes_mapping(
            first, target, "git-notes", "1", "native-notes-tree", app.work
        )
        mapping = mapping_view.evidence[0].mapping
        body = service.read_ref_note_bytes(first, mapping, app.work)
        assert (
            body.available and body.verified and body.body_bytes == b"\0\xffbinary\r\n"
        )
        assert not service.read_ref_note_bytes(second, mapping, app.work).available
        with pytest.raises(RepositoryFailure) as exceeded:
            service.get_ref_observation(
                first.ref_observation_key, app.work, max_claims=1
            )
        assert exceeded.value.code == "QUERY_BUDGET"
        assert not (repository_path.parent / "p1-recovery-stop.json").exists()

    _, instance = app.repository_store.catalog_identity()
    initialize(
        repository_path.parent / "context.sqlite3", "context", repository, instance
    )
    assert ProductionQueryService(repository_path.parent).detect_mode() == "paired"
    assert (
        ProductionQueryService(
            repository_path.parent, mode="repository_only"
        ).detect_mode()
        == "repository_only"
    )
    paired = ProductionQueryService(repository_path.parent).get_ref_observation(
        first.ref_observation_key, app.work
    )
    assert paired.conflict and set(paired.claims) == {first, competing}


def test_git_only_backup_restores_each_ref_note_copy_and_rootless_absence(acquisition):
    app, _, _, repository, origin, repository_path, _ = acquisition
    _, target, _ = fixture_note(acquisition)
    result = discover(app, repository, origin, str(uuid4()), ("refs/notes/missing",))
    first, second = (item.links[0].claim for item in result.enumerations[:2])
    for claim in (first, second):
        assert app.acquire_ref_note(claim, target).body_retained
    absence = next(
        link.claim
        for item in result.enumerations
        for link in item.links
        if link.derivation == "absence"
    )
    mapping = (
        app.repository_store.notes_mapping_projection(
            first, target, "git-notes", "1", "native-notes-tree", app.work
        )
        .evidence[0]
        .mapping
    )

    backup = repository_path.parent / "backups" / "git-only"
    adapter = SQLiteRecoveryAdapter()
    receipt = adapter.create_consistent_backup(
        repository_path.parent, backup, BackupScope.GIT_ONLY
    )
    assert (
        receipt.verified_clean
        and receipt.manifest.retained_byte_summary.notes_body_count == 2
    )
    assert receipt.manifest.retained_byte_summary.total_retained_bytes >= 2 * len(
        b"\0\xffbinary\r\n"
    )
    restored = repository_path.parent / "restored"
    assert adapter.restore_backup(backup, restored, repository).revalidated_clean
    query = ProductionQueryService(restored)
    assert query.detect_mode() == "repository_only"
    work = UnlimitedWorkBudget()
    assert query.get_ref_observation(absence.ref_observation_key, work).claims == (
        absence,
    )
    for claim in (first, second):
        body = query.read_ref_note_bytes(claim, mapping, work)
        assert (
            body.available and body.verified and body.body_bytes == b"\0\xffbinary\r\n"
        )


def test_backup_finite_budget_is_not_corruption(acquisition):
    app, _, _, repository, origin, repository_path, _ = acquisition
    fixture_note(acquisition)
    discover(app, repository, origin, str(uuid4()))
    backup = repository_path.parent / "backups" / "budget"
    adapter = SQLiteRecoveryAdapter(
        validation_budget=RecoveryBudget(max_input_records=1)
    )
    with pytest.raises(RefValidationBudgetError):
        adapter.create_consistent_backup(
            repository_path.parent, backup, BackupScope.GIT_ONLY
        )
    assert not backup.exists()
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()
    app.repository_store.ensure_available()
    expanded = SQLiteRecoveryAdapter(
        validation_budget=RecoveryBudget(max_input_records=20)
    )
    assert expanded.create_consistent_backup(
        repository_path.parent, backup, BackupScope.GIT_ONLY
    ).verified_clean


def test_backup_verification_exhaustion_is_not_corruption(acquisition, monkeypatch):
    from repo_catalog.adapters.sqlite import repository_recovery as recovery_module

    app, _, _, repository, origin, repository_path, _ = acquisition
    _, target, _ = fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.acquire_ref_note(claim, target)
    observed = []
    original = recovery_module.validate_stored_checks

    def capture_usage(connection, role, *, retained_bytes, work=None):
        if work is not None:
            observed.append(work.usage["verification_bytes"])
        return original(connection, role, retained_bytes=retained_bytes, work=work)

    monkeypatch.setattr(recovery_module, "validate_stored_checks", capture_usage)
    adapter = SQLiteRecoveryAdapter()
    adapter._validate_and_summarize_repository(repository_path)
    assert len(observed) == 2 and observed[-1] > observed[0]
    budget = RecoveryBudget(max_work_units={"verification_bytes": observed[0] + 1})
    limited = SQLiteRecoveryAdapter(validation_budget=budget)
    backup = repository_path.parent / "backups" / "verification-budget"
    with pytest.raises(RefValidationBudgetError):
        limited.create_consistent_backup(
            repository_path.parent, backup, BackupScope.GIT_ONLY
        )
    assert not backup.exists()
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()
    app.repository_store.ensure_available()


def test_paired_backup_preserves_ref_claims_and_store_scope(acquisition):
    app, _, _, repository, origin, repository_path, _ = acquisition
    fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0]
    _, instance = app.repository_store.catalog_identity()
    initialize(
        repository_path.parent / "context.sqlite3", "context", repository, instance
    )
    backup = repository_path.parent / "backups" / "paired"
    adapter = SQLiteRecoveryAdapter()
    receipt = adapter.create_consistent_backup(
        repository_path.parent, backup, BackupScope.PAIRED
    )
    assert receipt.verified_clean and set(receipt.manifest.stores) == {
        "repository",
        "context",
    }
    restored = repository_path.parent / "paired-restored"
    adapter.restore_backup(backup, restored, repository)
    query = ProductionQueryService(restored)
    assert query.detect_mode() == "paired"
    assert (
        query.get_ref_enumeration(*event.event.identity, UnlimitedWorkBudget()) == event
    )


def test_backup_detects_corrupt_ref_note_and_stops_source(acquisition):
    app, _, _, repository, origin, repository_path, _ = acquisition
    _, target, _ = fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.acquire_ref_note(claim, target)
    db = connect(repository_path, "repository")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_retained_notes_update'"
        ).fetchone()[0]
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("DROP TRIGGER p1_immutable_ref_retained_notes_update")
        db.execute("UPDATE ref_retained_notes SET body = zeroblob(size)")
        db.execute(trigger)
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.commit()
    finally:
        db.close()
    backup = repository_path.parent / "backups" / "corrupt"
    with pytest.raises(CorruptionDetectedError):
        SQLiteRecoveryAdapter().create_consistent_backup(
            repository_path.parent, backup, BackupScope.GIT_ONLY
        )
    assert not backup.exists()
    assert (repository_path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(RepositoryFailure) as stopped:
        app.repository_store.ensure_available()
    assert stopped.value.code == "RECOVERY_STOP"


def test_backup_detects_invalid_stored_enumeration_scope(acquisition):
    app, _, _, repository, origin, repository_path, _ = acquisition
    fixture_note(acquisition)
    event = discover(app, repository, origin, str(uuid4())).enumerations[0].event
    db = connect(repository_path, "repository")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_enumeration_observations_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_enumeration_observations_update")
        db.execute(
            "UPDATE ref_enumeration_observations SET enumeration_scope_json='[[],[]]' WHERE enumeration_uuidv7=?",
            (event.enumeration_uuidv7,),
        )
        db.execute(trigger)
        db.commit()
    finally:
        db.close()
    backup = repository_path.parent / "backups" / "scope-corrupt"
    with pytest.raises(CorruptionDetectedError):
        SQLiteRecoveryAdapter().create_consistent_backup(
            repository_path.parent, backup, BackupScope.GIT_ONLY
        )
    assert not backup.exists()
    assert (repository_path.parent / "p1-recovery-stop.json").exists()


def test_restore_rechecks_ref_note_after_attacker_rehashes_manifest(acquisition):
    app, _, _, repository, origin, repository_path, _ = acquisition
    _, target, _ = fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.acquire_ref_note(claim, target)
    adapter = SQLiteRecoveryAdapter()
    backup = repository_path.parent / "backups" / "forged"
    adapter.create_consistent_backup(
        repository_path.parent, backup, BackupScope.GIT_ONLY
    )
    saved_repository = backup / "stores" / "repository.sqlite3"
    db = sqlite3.connect(saved_repository)
    register_functions(db)
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_retained_notes_update'"
        ).fetchone()[0]
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("DROP TRIGGER p1_immutable_ref_retained_notes_update")
        db.execute("UPDATE ref_retained_notes SET body=zeroblob(size)")
        db.execute(trigger)
        db.commit()
    finally:
        db.close()
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    digest = hashlib.sha256(saved_repository.read_bytes()).hexdigest()
    manifest["stores"]["repository"]["sha256"] = digest
    manifest["stores"]["repository"]["bytes"] = saved_repository.stat().st_size
    manifest["overall_sha256"] = hashlib.sha256(digest.encode("ascii")).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (backup / "manifest.json.sha256").write_text(manifest_sha + "  manifest.json\n")
    destination = repository_path.parent / "forged-restore"
    with pytest.raises(RestoreValidationError):
        adapter.restore_backup(backup, destination, repository)
    assert not destination.exists()
    assert not (repository_path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("empty", [False, True])
def test_verified_ref_coverage_survives_backup_and_typed_query(
    p1_repository_fixture, empty
):
    repository_store, path, repository = p1_repository_fixture
    proof = proof_fixture(p1_repository_fixture, empty=empty)
    repository_store.admit_ref_coverage_proof(proof, Budget())
    query = ProductionQueryService(path.parent)
    with query.open_snapshot(required_store="repository") as snap:
        with pytest.raises(sqlite3.DatabaseError, match="prohibited"):
            snap.repository_store.sql("SELECT structures_json FROM ref_coverage_proofs")

        class CoverageProbe(Budget):
            blocked = 0
            leaked = []

            def require(self, unit, amount=1):
                try:
                    self.leaked.extend(
                        snap.repository_store.sql(
                            "SELECT structures_json FROM ref_coverage_proofs"
                        )
                    )
                except sqlite3.DatabaseError:
                    self.blocked += 1
                super().require(unit, amount)

        probe = CoverageProbe()
        assert snap.repository_store.ref_coverage_proofs(
            proof.coverage_claim, probe
        ) == (proof,)
        assert probe.blocked > 0 and not probe.leaked
    result = query.get_repository_coverage(proof.coverage_claim.scope, work=Budget())
    assert result.state == "complete" and result.known_empty is empty
    with pytest.raises(RepositoryFailure) as no_budget:
        query.get_repository_coverage(proof.coverage_claim.scope)
    assert no_budget.value.code == "QUERY_BUDGET"
    with pytest.raises(RepositoryFailure) as small_limit:
        query.get_repository_coverage(
            proof.coverage_claim.scope, work=Budget(), max_bytes=1
        )
    assert small_limit.value.code == "QUERY_BUDGET"
    assert not (path.parent / "p1-recovery-stop.json").exists()

    backup = path.parent.parent / (path.parent.name + "-coverage-backup")
    adapter = SQLiteRecoveryAdapter()
    assert adapter.create_consistent_backup(
        path.parent, backup, BackupScope.GIT_ONLY
    ).verified_clean
    restored = path.parent.parent / (path.parent.name + "-coverage-restored")
    assert adapter.restore_backup(backup, restored, repository).revalidated_clean
    restored_query = ProductionQueryService(restored)
    result = restored_query.get_repository_coverage(
        proof.coverage_claim.scope, work=Budget()
    )
    assert result.state == "complete" and result.known_empty is empty
    with closing(
        GitRepositoryStore(restored / "repository.sqlite3")
    ) as restored_repository:
        assert restored_repository.ref_coverage_proofs(
            proof.coverage_claim, Budget()
        ) == (proof,)


def test_backup_rechecks_coverage_structure_and_stops_source(p1_repository_fixture):
    repository_store, path, _ = p1_repository_fixture
    proof = proof_fixture(p1_repository_fixture)
    repository_store.admit_ref_coverage_proof(proof, Budget())
    db = connect(path, "repository")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_coverage_proofs_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_coverage_proofs_update")
        data = json.loads(
            db.execute("SELECT structures_json FROM ref_coverage_proofs").fetchone()[0]
        )
        data[0][3] = "00" + data[0][3][2:]
        db.execute(
            "UPDATE ref_coverage_proofs SET structures_json=?",
            (json.dumps(data, separators=(",", ":")),),
        )
        db.execute(trigger)
        db.commit()
    finally:
        db.close()
    backup = path.parent.parent / (path.parent.name + "-corrupt-coverage-backup")
    with pytest.raises(CorruptionDetectedError):
        SQLiteRecoveryAdapter().create_consistent_backup(
            path.parent, backup, BackupScope.GIT_ONLY
        )
    assert not backup.exists()
    assert (path.parent / "p1-recovery-stop.json").exists()


def test_backup_stops_on_invalid_utf8_mapping_key(acquisition):
    app, _, _, repository, origin, repository_path, _ = acquisition
    _, target, _ = fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    app.acquire_ref_note(claim, target)
    db = connect(repository_path, "repository")
    try:
        db.execute(
            "INSERT INTO notes_mappings "
            "SELECT object_format,root_object_oid,interpretation_kind,interpretation_version,"
            "CAST(X'80' AS TEXT),annotated_object_oid,note_object_oid,mapping_path_json "
            "FROM notes_mappings LIMIT 1"
        )
        db.commit()
    finally:
        db.close()
    backup = repository_path.parent / "backups" / "utf8-corrupt"
    with pytest.raises(CorruptionDetectedError):
        SQLiteRecoveryAdapter().create_consistent_backup(
            repository_path.parent, backup, BackupScope.GIT_ONLY
        )
    assert not backup.exists()
    assert (repository_path.parent / "p1-recovery-stop.json").exists()
