"""ADR 0036 Core admission, isolation and checked Notes evidence."""

import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_core import Core
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_core import OID, CoreCoverageScope, CoreFailure, Provenance
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ref_observation import (
    NotesMapping,
    NotesMappingClaim,
    NotesMappingEvidence,
    NotesMappingGroup,
    RefAbsenceEvidence,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
)
from tests.integration.p1.test_core import Budget, provenance
from tests.integration.p1.test_core import core as core
from tests.integration.p1.test_notes import mapping as old_mapping

V7A = "01890f47-0000-7000-8000-000000000001"
V7B = "01890f47-0000-7000-8000-000000000002"


def subject(repository, value=V7A, origin=None, name=b"refs/notes/\xff"):
    return RefObservation(
        RefObservationKey(origin or str(uuid4()), value),
        repository,
        name,
        "source",
        "scope",
        10,
    )


def received(coordinate):
    return Provenance(
        "receiver",
        "verification",
        coordinate,
        "native-notes",
        "1",
        "receiver_intrinsic",
    )


def test_observation_identity_claim_replay_conflicts_and_absence(core):
    c, path, repository = core
    one = subject(repository)
    two = subject(repository, V7B, one.ref_observation_key.observation_origin_uuidv4)
    c.admit_ref_observation(one)
    c.admit_ref_observation(one)
    c.admit_ref_observation(two)
    with pytest.raises(CoreFailure, match="inconsistent"):
        c.admit_ref_observation(replace(one, visibility_scope="other"))
    unknown = RefObservationClaim(one.ref_observation_key, provenance("r1"), "present")
    c.admit_ref_observation_claim(unknown)
    root_a, root_b = OID("sha1", "a" * 40), OID("sha1", "b" * 40)
    first = RefObservationClaim(
        one.ref_observation_key, provenance("r2"), "present", root_oid=root_a
    )
    second = RefObservationClaim(
        one.ref_observation_key, provenance("r3"), "present", root_oid=root_b
    )
    c.admit_ref_observation_claim(first)
    c.admit_ref_observation_claim(first)
    c.admit_ref_observation_claim(second)
    with pytest.raises(CoreFailure, match="cannot be rebound"):
        c.admit_ref_observation_claim(replace(first, root_oid=root_b))
    same_coordinate = replace(
        first,
        provenance=replace(first.provenance, decoder="different"),
        root_oid=root_b,
    )
    with pytest.raises(CoreFailure, match="inconsistent"):
        c.admit_ref_observation_claim(same_coordinate)
    assert c.ref_observation(one.ref_observation_key, Budget()).conflict
    assert len(c.ref_observation(one.ref_observation_key, Budget()).claims) == 3
    evidence = RefAbsenceEvidence(
        "source", "scope", one.ref_name_bytes, "lookup", "completed"
    )
    absent = RefObservationClaim(
        one.ref_observation_key, provenance("r4"), "absent", absence_evidence=evidence
    )
    c.admit_ref_observation_claim(absent)
    assert c.ref_observation(one.ref_observation_key, Budget()).conflict
    wrong = replace(
        absent,
        provenance=provenance("r5"),
        absence_evidence=replace(evidence, visibility_scope="elsewhere"),
    )
    with pytest.raises(sqlite3.IntegrityError, match="absence evidence"):
        c.admit_ref_observation_claim(wrong)
    assert len(c.ref_observation(one.ref_observation_key, Budget()).claims) == 4
    for limits in ({"max_claims": 1}, {"max_bytes": 1}):
        budget = Budget()
        with pytest.raises(CoreFailure) as exceeded:
            c.ref_observation(one.ref_observation_key, budget, **limits)
        assert exceeded.value.code == "QUERY_BUDGET"
        assert budget.counts["metadata_units"] > 0
    other = Core(path)
    try:
        assert (
            other.ref_observation(
                one.ref_observation_key, Budget()
            ).ref_observation.ref_name_bytes
            == one.ref_name_bytes
        )
    finally:
        other.close()


def test_unknown_to_known_is_not_conflict_and_coverage_time_preserved(core):
    c, _, repository = core
    obs = subject(repository)
    c.admit_ref_observation(obs)
    a = RefObservationClaim(obs.ref_observation_key, provenance("a"), "present")
    b = RefObservationClaim(
        obs.ref_observation_key,
        provenance("b"),
        "present",
        root_oid=OID("sha1", "a" * 40),
    )
    c.admit_ref_observation_claim(a)
    c.admit_ref_observation_claim(b)
    assert not c.ref_observation(obs.ref_observation_key, Budget()).conflict
    scope = CoreCoverageScope(
        "ref_observation", (*obs.ref_observation_key.key, "notes")
    )
    c.admit_coverage_scope(scope)
    assert c.admit_coverage(CoverageClaim(scope, 20, "partial")) == "insert"
    assert c.admit_coverage(CoverageClaim(scope, 10, "complete")) == "stale"
    assert c.coverage(scope).state == "partial"
    complete = CoverageClaim(scope, 30, "complete")
    assert c.admit_coverage(complete) == "insert"
    with pytest.raises(CoreFailure, match="typed evidence"):
        c.admit_coverage_proof(complete, (), provenance("fake-terminal"))
    assert c.coverage(scope).state == "unknown"


def test_ref_projection_charges_repeated_reads_to_real_request(core, tmp_path):
    from repo_catalog.adapters.sqlite.p1_coordination import NotesWorkBudget, WorkLedger
    from repo_catalog.adapters.sqlite.p1_schema import initialize
    from repo_catalog.domain.p1_coordination import NotesLimits, RequestIdentity

    c, _, repository = core
    obs = subject(repository)
    c.admit_ref_observation(obs)
    for name in ("first", "second"):
        c.admit_ref_observation_claim(
            RefObservationClaim(obs.ref_observation_key, provenance(name), "present")
        )
    path = tmp_path / "projection-operational.sqlite3"
    initialize(path, "operational", repository, str(uuid4()))
    db = connect(path, "operational")
    try:
        ledger = WorkLedger(db)
        request = RequestIdentity(str(uuid4()), str(uuid4()))
        ledger.new_request(request, "{}", NotesLimits.work_limits())
        attempt = str(uuid4())
        ledger.attempt(request, attempt)
        budget = NotesWorkBudget(ledger, request, attempt, NotesLimits())
        proof, note = old_mapping(repository)
        rooted = RefObservationClaim(
            obs.ref_observation_key,
            provenance("proof-root"),
            "present",
            root_oid=proof.capture.root,
        )
        c.admit_ref_observation_claim(rooted)
        mapping = NotesMapping(
            proof.capture.root,
            "git-notes",
            "1",
            "tree",
            proof.target,
            proof.note,
            proof.path,
        )
        evidence = NotesMappingEvidence(
            rooted, mapping, "single-path", received("checked"), proof.structures
        )
        c.admit_notes_mapping_evidence(evidence, budget)
        before = ledger.usage(request)
        result = c.notes_mapping_projection(
            rooted, proof.target, "git-notes", "1", "tree", budget, max_units=4
        )
        assert result.canonical_note_oid == proof.note
        after = ledger.usage(request)
        assert after["input_bytes"] > before["input_bytes"]
        assert after["proof_steps"] > before["proof_steps"]
        copy = str(uuid4())
        c.admit_ref_note(evidence, note, copy, budget)
        before_read = ledger.usage(request)
        assert c.read_ref_note(rooted, mapping, budget) == note.body
        once = ledger.usage(request)
        assert c.read_ref_note(rooted, mapping, budget) == note.body
        twice = ledger.usage(request)
        assert twice["input_bytes"] > once["input_bytes"] > before_read["input_bytes"]
        assert (
            twice["verification_bytes"]
            > once["verification_bytes"]
            > before_read["verification_bytes"]
        )
        assert twice["proof_steps"] > once["proof_steps"] > before_read["proof_steps"]

        def fail_before_commit():
            raise RuntimeError("abort body admission")

        before_rollback = ledger.usage(request)
        with pytest.raises(RuntimeError, match="abort body admission"):
            c.admit_ref_note(
                evidence, note, str(uuid4()), budget, before_commit=fail_before_commit
            )
        after_rollback = ledger.usage(request)
        assert after_rollback["input_bytes"] > before_rollback["input_bytes"]
        assert (
            after_rollback["verification_bytes"] > before_rollback["verification_bytes"]
        )
        assert len(c.sql("SELECT 1 FROM ref_retained_notes")) == 1
        original_lookup = c._ref_note_one

        def interrupted_fetch(statement, parameters):
            if statement.startswith("SELECT * FROM ref_retained_notes"):
                raise OSError("interrupted selected-copy fetch")
            return original_lookup(statement, parameters)

        c._ref_note_one = interrupted_fetch
        try:
            before_interruption = ledger.usage(request)
            with pytest.raises(OSError, match="interrupted selected-copy fetch"):
                c.read_ref_note(rooted, mapping, budget)
            after_interruption = ledger.usage(request)
            assert (
                after_interruption["input_bytes"] > before_interruption["input_bytes"]
            )
            assert "input_bytes" not in budget.pending
        finally:
            c._ref_note_one = original_lookup
        assert c.read_ref_note(rooted, mapping, budget) == note.body
        c.ref_observation(obs.ref_observation_key, budget, max_claims=4)
        first = ledger.usage(request)
        c.ref_observation(obs.ref_observation_key, budget, max_claims=4)
        repeated = ledger.usage(request)
        assert repeated["metadata_units"] > first["metadata_units"] > 0
        assert repeated["input_bytes"] > first["input_bytes"] > 0
        with pytest.raises(CoreFailure) as exceeded:
            c.ref_observation(obs.ref_observation_key, budget, max_claims=1)
        assert exceeded.value.code == "QUERY_BUDGET"
        assert ledger.usage(request)["metadata_units"] > repeated["metadata_units"]
    finally:
        db.close()


def test_shared_mapping_claims_and_receiver_proofs_are_claim_specific(core):
    c, _, repository = core
    proof, note = old_mapping(repository)
    first = subject(repository)
    second = subject(
        repository, V7B, first.ref_observation_key.observation_origin_uuidv4
    )
    claims = []
    for index, obs in enumerate((first, second)):
        c.admit_ref_observation(obs)
        claim = RefObservationClaim(
            obs.ref_observation_key,
            provenance(f"ref-{index}"),
            "present",
            root_oid=proof.capture.root,
        )
        c.admit_ref_observation_claim(claim)
        claims.append(claim)
    content = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "full-tree",
        proof.target,
        proof.note,
        proof.path,
    )
    for index, claim in enumerate(claims):
        c.admit_notes_mapping_claim(
            NotesMappingClaim(claim, content, provenance(f"member-{index}"))
        )
    assert len(c.sql("SELECT * FROM notes_mappings")) == 1
    assert len(c.sql("SELECT * FROM notes_mapping_claims")) == 2
    ev1 = NotesMappingEvidence(
        claims[0], content, "single-path", received("e1"), proof.structures
    )
    ev2 = NotesMappingEvidence(
        claims[1], content, "single-path", received("e2"), proof.structures
    )
    c.admit_notes_mapping_evidence(ev1, Budget())
    c.admit_notes_mapping_evidence(ev1, Budget())
    c.admit_notes_mapping_evidence(ev2, Budget())
    assert len(c.sql("SELECT * FROM notes_mapping_evidence")) == 2
    c.admit_ref_note(ev1, note, str(uuid4()), Budget())
    assert c.read_ref_note(claims[0], content, Budget()) == note.body
    with pytest.raises(CoreFailure, match="claim-specific"):
        c.read_ref_note(claims[1], content, Budget())
    root_b = OID("sha1", "b" * 40)
    other = RefObservationClaim(
        first.ref_observation_key, provenance("other-root"), "present", root_oid=root_b
    )
    c.admit_ref_observation_claim(other)
    with pytest.raises(CoreFailure, match="claimed root"):
        replace(ev1, ref_claim=other)
    with pytest.raises(CoreFailure, match="cannot be rebound"):
        c.admit_notes_mapping_evidence(
            replace(
                ev1,
                ref_claim=replace(
                    claims[0], ref_form="direct", direct_target_oid=root_b
                ),
            ),
            Budget(),
        )
    assert len(c.sql("SELECT * FROM ref_retained_notes")) == 1
    from repo_catalog.adapters.sqlite.recovery_validation import (
        validate_stored_admission_guards,
    )

    db = connect(c._directory / "core.sqlite3", "core")
    try:
        validate_stored_admission_guards(db, "core")
    finally:
        db.close()


def test_groups_atomic_replay_and_no_partial_group_union(core):
    c, _, repository = core
    proof, _ = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    group = NotesMappingGroup(
        claim,
        "git-notes",
        "1",
        "full-tree",
        "partial-scope",
        "partial",
        ((proof.target.full_oid, proof.note.full_oid, None),),
        provenance("group"),
    )
    c.admit_notes_mapping_group(group)
    c.admit_notes_mapping_group(group)
    with pytest.raises(CoreFailure, match="inconsistent"):
        c.admit_notes_mapping_group(replace(group, status="complete"))
    assert len(c.sql("SELECT * FROM notes_mapping_groups")) == 1
    assert c.sql("SELECT status FROM notes_mapping_groups")[0][0] == "partial"


def test_supported_sql_and_schema_forbid_rewrite(core):
    c, path, repository = core
    obs = subject(repository)
    c.admit_ref_observation(obs)
    with pytest.raises(sqlite3.DatabaseError):
        c.sql("DELETE FROM ref_observations")
    db = connect(path, "core")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                "UPDATE ref_observations SET source_attribution=source_attribution"
            )
    finally:
        db.close()


def test_unproven_bodies_and_unrelated_claims_cannot_gain_authority(core):
    c, _, repository = core
    proof, note = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    root_claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("root"),
        "present",
        root_oid=proof.capture.root,
    )
    unknown_claim = RefObservationClaim(
        obs.ref_observation_key, provenance("unknown"), "present"
    )
    c.admit_ref_observation_claim(root_claim)
    c.admit_ref_observation_claim(unknown_claim)
    content = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    with pytest.raises(CoreFailure, match="exact claimed root"):
        NotesMappingEvidence(
            unknown_claim, content, "single-path", received("e"), proof.structures
        )
    with pytest.raises(CoreFailure, match="supported receiver decoder"):
        NotesMappingEvidence(
            root_claim, content, "single-path", provenance("sender"), proof.structures
        )
    broken = replace(proof.structures[0], body=b"not the correct tree")
    bad = NotesMappingEvidence(
        root_claim, content, "single-path", received("broken"), (broken,)
    )
    with pytest.raises(CoreFailure):
        c.admit_ref_note(bad, note, str(uuid4()), Budget())
    assert not c.sql("SELECT * FROM notes_mapping_evidence")
    assert not c.sql("SELECT * FROM ref_retained_notes")


def test_note_transaction_rolls_back_all_new_units_on_failure(core):
    c, _, repository = core
    proof, note = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    content = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, content, "single-path", received("e"), proof.structures
    )

    def fail():
        raise RuntimeError("simulated interrupted transaction")

    with pytest.raises(RuntimeError, match="simulated"):
        c.admit_ref_note(evidence, note, str(uuid4()), Budget(), before_commit=fail)
    assert not c.sql("SELECT * FROM notes_mappings")
    assert not c.sql("SELECT * FROM notes_mapping_evidence")
    assert not c.sql("SELECT * FROM ref_retained_notes")
    c.admit_ref_note(evidence, note, str(uuid4()), Budget())
    assert c.read_ref_note(claim, content, Budget()) == note.body
    altered = replace(claim, ref_form="direct", direct_target_oid=proof.capture.root)
    with pytest.raises(CoreFailure, match="cannot be rebound"):
        c.read_ref_note(altered, content, Budget())


def test_valid_recovery_guards_and_rootless_absence_export(core):
    from repo_catalog.adapters.sqlite.recovery_validation import (
        validate_stored_admission_guards,
    )
    from repo_catalog.application.exchange import ExchangeService
    from repo_catalog.domain.exchange import ExchangeSelectionScope
    from repo_catalog.domain.ref_exchange import claim_from_wire, observation_from_wire

    c, path, repository = core
    obs = subject(repository)
    c.admit_ref_observation(obs)
    absence = RefAbsenceEvidence(
        "source", "scope", obs.ref_name_bytes, "lookup", "completed"
    )
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("absence"),
        "absent",
        absence_evidence=absence,
    )
    c.admit_ref_observation_claim(claim)
    db = connect(path, "core")
    try:
        validate_stored_admission_guards(db, "core")
    finally:
        db.close()
    package = ExchangeService(path.parent).export_package(
        selection=ExchangeSelectionScope(
            all_selected=True,
            include_context=False,
            include_retained_bytes=False,
            ref_observation_keys=(obs.ref_observation_key,),
        )
    )
    assert [observation_from_wire(row) for row in package.core["ref_observations"]] == [
        obs
    ]
    assert [claim_from_wire(row) for row in package.core["ref_observation_claims"]] == [
        claim
    ]
    assert not package.core["git_objects"]


def test_projection_preserves_reports_groups_and_verified_scope(core):
    c, _, repository = core
    proof, _ = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    competing = replace(mapping, note_oid=OID("sha1", "b" * 40), mapping_path=None)
    c.admit_notes_mapping_claim(NotesMappingClaim(claim, mapping, provenance("first")))
    c.admit_notes_mapping_claim(
        NotesMappingClaim(claim, competing, provenance("second"))
    )
    group = NotesMappingGroup(
        claim,
        "git-notes",
        "1",
        "tree",
        "partial",
        "partial",
        ((proof.target.full_oid, proof.note.full_oid, None),),
        provenance("group"),
    )
    c.admit_notes_mapping_group(group)
    for name in ("e1", "e2"):
        c.admit_notes_mapping_evidence(
            NotesMappingEvidence(
                claim, mapping, "single-path", received(name), proof.structures
            ),
            Budget(),
        )
    result = c.notes_mapping_projection(
        claim, proof.target, "git-notes", "1", "tree", Budget()
    )
    assert len(result.claims) == 2
    assert len(result.groups) == 1 and result.groups[0].status == "partial"
    assert len(result.evidence) == 2
    assert {item.provenance.coordinate for item in result.evidence} == {"e1", "e2"}
    assert result.canonical_note_oid == proof.note
    assert result.reported_conflict
    for limits in ({"max_units": 1}, {"max_bytes": 1}):
        budget = Budget()
        with pytest.raises(CoreFailure) as exceeded:
            c.notes_mapping_projection(
                claim, proof.target, "git-notes", "1", "tree", budget, **limits
            )
        assert exceeded.value.code == "QUERY_BUDGET"
        if "max_units" in limits:
            assert budget.counts["metadata_units"] > 0
        assert (
            c.ref_observation(obs.ref_observation_key, Budget()).ref_observation == obs
        )
    assert (
        c.notes_mapping_projection(
            claim, proof.target, "git-notes", "2", "tree", Budget()
        ).canonical_note_oid
        is None
    )

    class NoProofBudget(Budget):
        def require(self, unit, amount=1):
            if unit == "input_bytes":
                raise CoreFailure("BUDGET", unit, "bounded read")
            super().require(unit, amount)

    with pytest.raises(CoreFailure) as error:
        c.notes_mapping_projection(
            claim, proof.target, "git-notes", "1", "tree", NoProofBudget()
        )
    assert error.value.code == "BUDGET"
    assert c.ref_observation(obs.ref_observation_key, Budget()).ref_observation == obs

    class NoProofSteps(Budget):
        def require(self, unit, amount=1):
            if unit == "proof_steps":
                raise CoreFailure("BUDGET", unit, "bounded proof traversal")
            super().require(unit, amount)

    with pytest.raises(CoreFailure) as error:
        c.notes_mapping_projection(
            claim, proof.target, "git-notes", "1", "tree", NoProofSteps()
        )
    assert error.value.code == "BUDGET"
    assert c.ref_observation(obs.ref_observation_key, Budget()).ref_observation == obs


def test_structural_evidence_corruption_stops_catalog(core):
    c, path, repository = core
    proof, _ = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    c.admit_notes_mapping_evidence(
        NotesMappingEvidence(
            claim, mapping, "single-path", received("e"), proof.structures
        ),
        Budget(),
    )

    # Simulate storage corruption, restoring the original schema before read.
    db = connect(path, "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_notes_mapping_evidence_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_notes_mapping_evidence_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE notes_mapping_evidence SET proof_bundle='[]'")
        db.execute(trigger)
        db.execute("PRAGMA ignore_check_constraints=OFF")
    finally:
        db.close()
    with pytest.raises(CoreFailure) as error:
        c.notes_mapping_projection(
            claim, proof.target, "git-notes", "1", "tree", Budget()
        )
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    with pytest.raises(CoreFailure) as stopped:
        c.ref_observation(obs.ref_observation_key, Budget())
    assert stopped.value.code == "RECOVERY_STOP"


def test_audit_records_full_expression_index_sql():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "scripts/audit_p1_schema.py"
    spec = importlib.util.spec_from_file_location("p1_index_audit", path)
    assert spec and spec.loader
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    schema = audit.introspect()
    indexes = schema["core"]["tables"]["ref_observation_claims"]["unique"]
    expressions = [item for item in indexes if "expression_sql" in item]
    assert len(expressions) == 1
    assert "json_extract(provenance" in expressions[0]["expression_sql"]
    assert "<expression:2>" in expressions[0]["columns"]


def test_backup_restores_rootless_observation_without_stopping_healthy_core(core):
    from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter
    from repo_catalog.domain.recovery import BackupScope

    c, path, repository = core
    obs = subject(repository)
    c.admit_ref_observation(obs)
    destination = path.parent.parent / (path.parent.name + "-backup")
    adapter = SQLiteRecoveryAdapter()
    receipt = adapter.create_consistent_backup(
        path.parent, destination, BackupScope.GIT_ONLY
    )
    assert (
        receipt.verified_clean
        and receipt.manifest.retained_byte_summary.notes_body_count == 0
    )
    restored = path.parent.parent / (path.parent.name + "-restored")
    assert adapter.restore_backup(destination, restored, repository).revalidated_clean
    copy = Core(restored / "core.sqlite3")
    try:
        assert (
            copy.ref_observation(obs.ref_observation_key, Budget()).ref_observation
            == obs
        )
    finally:
        copy.close()
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert c.ref_observation(obs.ref_observation_key, Budget()).ref_observation == obs


def test_unsupported_salvage_is_partial_and_never_stages_new_note_bodies(core):
    import io
    import json

    from repo_catalog.adapters.sqlite.recovery import SQLiteRecoveryAdapter

    c, path, repository = core
    proof, note = old_mapping(repository, b"private-note-body")
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    content = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    c.admit_ref_note(
        NotesMappingEvidence(
            claim, content, "single-path", received("e"), proof.structures
        ),
        note,
        str(uuid4()),
        Budget(),
    )
    output = io.StringIO()
    _, _, errors, _, partial, _, _ = SQLiteRecoveryAdapter()._salvage_store_stream(
        path, "core", output, 1000, 10_000_000, 1_000_000, 0, 0
    )
    assert not errors
    assert partial >= 1
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    new_rows = [
        row
        for row in rows
        if row["extraction_provenance"]["table"]
        in {
            "ref_observations",
            "ref_observation_claims",
            "notes_mappings",
            "notes_mapping_evidence",
            "ref_retained_notes",
        }
    ]
    assert len(new_rows) >= 5
    assert all(
        row["extraction_status"] == "partial" and row["payload"] == {}
        for row in new_rows
    )
    assert "private-note-body" not in output.getvalue()


def test_structural_proof_cannot_claim_unchecked_decoder_or_full_inventory(core):
    c, path, repository = core
    proof, note = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures
    )
    with pytest.raises(CoreFailure, match="single-path"):
        replace(evidence, verification_scope="all-notes-mappings")
    with pytest.raises(CoreFailure, match="decoder"):
        replace(evidence, provenance=replace(evidence.provenance, decoder="not-run"))
    with pytest.raises(CoreFailure, match="decoder"):
        replace(evidence, mapping=replace(mapping, interpretation_version="2"))
    c.admit_notes_mapping_evidence(evidence, Budget())
    db = connect(path, "core")
    try:
        row = list(db.execute("SELECT * FROM notes_mapping_evidence").fetchone())
        row[-3] = "all-notes-mappings"
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            db.execute(
                "INSERT INTO notes_mapping_evidence VALUES("
                + ",".join("?" for _ in row)
                + ")",
                row,
            )
    finally:
        db.close()
    assert not c.sql("SELECT * FROM ref_retained_notes")
    c.admit_ref_note(evidence, note, str(uuid4()), Budget())
    assert c.read_ref_note(claim, mapping, Budget()) == note.body


def test_replay_does_not_repair_missing_nominal_root(core):
    c, path, repository = core
    obs = subject(repository)
    c.admit_ref_observation(obs)
    root = OID("sha1", "a" * 40)
    claim = RefObservationClaim(
        obs.ref_observation_key, provenance("ref"), "present", root_oid=root
    )
    c.admit_ref_observation_claim(claim)
    db = connect(path, "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_git_objects_delete'"
        ).fetchone()[0]
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("DROP TRIGGER p1_immutable_git_objects_delete")
        db.execute(
            "DELETE FROM git_objects WHERE object_format=? AND full_oid=?", root.key
        )
        db.execute(trigger)
        db.execute("PRAGMA foreign_keys=ON")
    finally:
        db.close()
    with pytest.raises(CoreFailure) as error:
        c.admit_ref_observation_claim(claim)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    with sqlite3.connect(path) as raw:
        assert not raw.execute(
            "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?", root.key
        ).fetchone()
    assert (path.parent / "p1-recovery-stop.json").exists()


def test_orphan_claim_stops_observation_read(core):
    c, path, repository = core
    obs = subject(repository)
    c.admit_ref_observation(obs)
    c.admit_ref_observation_claim(
        RefObservationClaim(obs.ref_observation_key, provenance("orphan"), "present")
    )
    db = connect(path, "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_observations_delete'"
        ).fetchone()[0]
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("DROP TRIGGER p1_immutable_ref_observations_delete")
        db.execute("DELETE FROM ref_observations")
        db.execute(trigger)
        db.execute("PRAGMA foreign_keys=ON")
    finally:
        db.close()
    with pytest.raises(CoreFailure) as error:
        c.ref_observation(obs.ref_observation_key, Budget())
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()


def test_missing_role_evidence_stops_body_read(core):
    c, path, repository = core
    proof, note = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    c.admit_ref_note(
        NotesMappingEvidence(
            claim, mapping, "single-path", received("e"), proof.structures
        ),
        note,
        str(uuid4()),
        Budget(),
    )
    db = connect(path, "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_notes_mapping_evidence_delete'"
        ).fetchone()[0]
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("DROP TRIGGER p1_immutable_notes_mapping_evidence_delete")
        db.execute("DELETE FROM notes_mapping_evidence")
        db.execute(trigger)
        db.execute("PRAGMA foreign_keys=ON")
    finally:
        db.close()
    with pytest.raises(CoreFailure) as error:
        c.read_ref_note(claim, mapping, Budget())
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    ("corruption", "same_copy"),
    [
        ("body", True),
        ("body", False),
        ("digest", True),
        ("invalid-utf8", True),
        ("missing-role", True),
        ("malformed-proof", True),
    ],
)
def test_replaying_corrupted_stored_copy_stops_catalog(core, corruption, same_copy):
    c, path, repository = core
    proof, note = old_mapping(repository, b"original note body")
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures
    )
    copy = str(uuid4())
    c.admit_ref_note(evidence, note, copy, Budget())
    db = connect(path, "core")
    try:
        if corruption == "malformed-proof":
            triggers = [
                db.execute(
                    "SELECT sql FROM sqlite_schema WHERE name=?", (name,)
                ).fetchone()[0]
                for name in (
                    "p1_immutable_ref_retained_notes_update",
                    "p1_immutable_notes_mapping_evidence_update",
                )
            ]
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("PRAGMA ignore_check_constraints=ON")
            db.execute("DROP TRIGGER p1_immutable_ref_retained_notes_update")
            db.execute("DROP TRIGGER p1_immutable_notes_mapping_evidence_update")
            malformed = "[" * 2_000 + "]" * 2_000
            db.execute("UPDATE ref_retained_notes SET proof_bundle=?", (malformed,))
            db.execute("UPDATE notes_mapping_evidence SET proof_bundle=?", (malformed,))
            for trigger in triggers:
                db.execute(trigger)
            db.execute("PRAGMA ignore_check_constraints=OFF")
            db.execute("PRAGMA foreign_keys=ON")
        elif corruption == "missing-role":
            trigger = db.execute(
                "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_notes_mapping_evidence_delete'"
            ).fetchone()[0]
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("DROP TRIGGER p1_immutable_notes_mapping_evidence_delete")
            db.execute("DELETE FROM notes_mapping_evidence")
            db.execute(trigger)
            db.execute("PRAGMA foreign_keys=ON")
        else:
            trigger = db.execute(
                "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_retained_notes_update'"
            ).fetchone()[0]
            db.execute("DROP TRIGGER p1_immutable_ref_retained_notes_update")
            db.execute("PRAGMA ignore_check_constraints=ON")
            if corruption == "body":
                db.execute(
                    "UPDATE ref_retained_notes SET body=?", (b"X" + note.body[1:],)
                )
            elif corruption == "invalid-utf8":
                db.execute(
                    "UPDATE ref_retained_notes SET digest_sha256=CAST(X'80' AS TEXT)"
                )
            else:
                db.execute("UPDATE ref_retained_notes SET digest_sha256=?", ("0" * 64,))
            db.execute(trigger)
            db.execute("PRAGMA ignore_check_constraints=OFF")
    finally:
        db.close()
    with pytest.raises(CoreFailure) as error:
        c.admit_ref_note(evidence, note, copy if same_copy else str(uuid4()), Budget())
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as stopped:
        c.ref_observation(obs.ref_observation_key, Budget())
    assert stopped.value.code == "RECOVERY_STOP"


def test_ref_note_valid_replay_and_unrelated_integrity_error_roll_back(core):
    c, path, repository = core
    proof, note = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("first"), proof.structures
    )
    copy = str(uuid4())
    c.admit_ref_note(evidence, note, copy, Budget())
    replay = Budget()
    c.admit_ref_note(evidence, note, copy, replay)
    assert len(c.sql("SELECT 1 FROM ref_retained_notes")) == 1
    assert replay.counts["input_bytes"] >= len(note.body) * 2
    assert replay.counts["proof_steps"] > 0
    with pytest.raises(CoreFailure) as limited:
        c.admit_ref_note(evidence, note, copy, Budget(), max_proof_bytes=1)
    assert limited.value.code == "BUDGET"
    assert len(c.sql("SELECT 1 FROM ref_retained_notes")) == 1
    assert not (path.parent / "p1-recovery-stop.json").exists()

    comparison = {"measured": False}
    original_cost = c._note_comparison_cost

    def track_comparison(*args):
        result = original_cost(*args)
        comparison["measured"] = True
        return result

    class IncomingOnly(Budget):
        def require(self, unit, amount=1):
            if unit == "input_bytes" and comparison["measured"]:
                raise CoreFailure("BUDGET", unit, "no existing-copy comparison budget")
            super().require(unit, amount)

    incoming_only = IncomingOnly()
    c._note_comparison_cost = track_comparison
    try:
        with pytest.raises(CoreFailure) as limited_comparison:
            c.admit_ref_note(evidence, note, str(uuid4()), incoming_only)
    finally:
        c._note_comparison_cost = original_cost
    assert limited_comparison.value.code == "BUDGET"
    assert comparison["measured"]
    assert len(c.sql("SELECT 1 FROM ref_retained_notes")) == 1
    assert not (path.parent / "p1-recovery-stop.json").exists()

    other_evidence = replace(evidence, provenance=received("second"))
    with pytest.raises(CoreFailure) as incompatible:
        c.admit_ref_note(other_evidence, note, copy, Budget())
    assert incompatible.value.code == "INCOMPATIBLE_REPLAY"
    assert len(c.sql("SELECT 1 FROM notes_mapping_evidence")) == 1

    def unrelated_failure():
        raise sqlite3.IntegrityError("unrelated synthetic constraint")

    with pytest.raises(sqlite3.IntegrityError, match="unrelated synthetic"):
        c.admit_ref_note(
            evidence, note, str(uuid4()), Budget(), before_commit=unrelated_failure
        )
    assert len(c.sql("SELECT 1 FROM ref_retained_notes")) == 1
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert c.read_ref_note(claim, mapping, Budget()) == note.body


def test_legacy_copy_identity_conflict_is_not_misclassified_as_corruption(core):
    c, path, repository = core
    proof, note = old_mapping(repository)
    copy = str(uuid4())
    c.admit_note(proof, note, copy, Budget())
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures
    )
    with pytest.raises(
        sqlite3.IntegrityError, match="conflicting exact note representation"
    ):
        c.admit_ref_note(evidence, note, copy, Budget())
    assert not c.sql("SELECT 1 FROM ref_retained_notes")
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert c.read_note(proof.capture, proof.target, proof.note) == note.body


def test_conflicting_other_copy_diagnosis_respects_budget_and_rolls_back(core):
    c, path, repository = core
    proof, note = old_mapping(repository, b"original note")
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures
    )
    copies = sorted(str(uuid4()) for _ in range(3))
    for copy in copies:
        c.admit_ref_note(evidence, note, copy, Budget())
    db = connect(path, "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_retained_notes_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_retained_notes_update")
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(
            "UPDATE ref_retained_notes SET body=? WHERE physical_copy_uuidv4=?",
            (b"X" + note.body[1:], copies[-1]),
        )
        db.execute(trigger)
        db.execute("PRAGMA ignore_check_constraints=OFF")
    finally:
        db.close()
    replacement = str(uuid4())
    with pytest.raises(CoreFailure) as limited:
        c.admit_ref_note(evidence, note, replacement, Budget(), max_existing_copies=1)
    assert limited.value.code == "BUDGET"
    assert len(c.sql("SELECT 1 FROM ref_retained_notes")) == 3
    assert not (path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as detected:
        c.admit_ref_note(evidence, note, replacement, Budget(), max_existing_copies=3)
    assert detected.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()


def test_ref_note_read_fetches_only_one_copy_and_charges_actual_work(core):
    c, _, repository = core
    proof, note = old_mapping(repository, b"x" * (256 * 1024))
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures
    )
    for _ in range(4):
        c.admit_ref_note(evidence, note, str(uuid4()), Budget())
    fetched = []
    original_factory = c._db.row_factory

    def track_body(cursor, values):
        names = [column[0] for column in cursor.description]
        if "body" in names:
            body = values[names.index("body")]
            if isinstance(body, bytes):
                fetched.append(len(body))
        return sqlite3.Row(cursor, values)

    c._db.row_factory = track_body
    try:
        budget = Budget()
        assert c.read_ref_note(claim, mapping, budget) == note.body
        assert fetched == [len(note.body)]
        assert budget.counts["input_bytes"] >= len(note.body)
        assert budget.counts["verification_bytes"] >= len(note.body)
        assert budget.counts["proof_steps"] > 0
    finally:
        c._db.row_factory = original_factory


def test_ref_note_read_limits_reserve_before_body_and_do_not_stop_catalog(core):
    c, path, repository = core
    proof, note = old_mapping(repository, b"bounded body")
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures
    )
    c.admit_ref_note(evidence, note, str(uuid4()), Budget())
    fetched = []
    original_factory = c._db.row_factory

    def track_body(cursor, values):
        names = [column[0] for column in cursor.description]
        if "body" in names:
            fetched.append(values[names.index("body")])
        return sqlite3.Row(cursor, values)

    class NoInput(Budget):
        def require(self, unit, amount=1):
            if unit == "input_bytes":
                raise CoreFailure("BUDGET", unit, "no body reservation")
            super().require(unit, amount)

    class NoVerification(Budget):
        def require(self, unit, amount=1):
            if unit == "verification_bytes":
                raise CoreFailure("BUDGET", unit, "no verification reservation")
            super().require(unit, amount)

    class NoProofSteps(Budget):
        def require(self, unit, amount=1):
            if unit == "proof_steps":
                raise CoreFailure("BUDGET", unit, "no structural verification")
            super().require(unit, amount)

    class SmallLimit:
        note_bytes = len(note.body) - 1

    c._db.row_factory = track_body
    try:
        small = Budget()
        small.limits = SmallLimit()
        for budget, options in (
            (NoInput(), {}),
            (small, {}),
            (Budget(), {"max_proof_bytes": 1}),
        ):
            with pytest.raises(CoreFailure) as exceeded:
                c.read_ref_note(claim, mapping, budget, **options)
            assert exceeded.value.code == "BUDGET"
            assert not fetched
        denied = NoVerification()
        with pytest.raises(CoreFailure) as exceeded:
            c.read_ref_note(claim, mapping, denied)
        assert exceeded.value.code == "BUDGET"
        assert denied.counts["input_bytes"] >= len(note.body)
        assert len(fetched) == 1
        fetched.clear()
        denied = NoProofSteps()
        with pytest.raises(CoreFailure) as exceeded:
            c.read_ref_note(claim, mapping, denied)
        assert exceeded.value.code == "BUDGET"
        assert denied.counts["input_bytes"] >= len(note.body)
        assert len(fetched) == 1
    finally:
        c._db.row_factory = original_factory
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert c.read_ref_note(claim, mapping, Budget()) == note.body


def test_note_read_charges_repeated_dependencies_and_exact_finite_budget(core):
    c, path, repository = core
    proof, note = old_mapping(repository, b"note under a finite budget")
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures
    )
    c.admit_ref_note(evidence, note, str(uuid4()), Budget())
    measured = Budget()
    assert c.read_ref_note(claim, mapping, measured) == note.body
    needed = measured.counts["input_bytes"]
    assert needed > len(note.body) + len(evidence.bundle)

    class Capped(Budget):
        def __init__(self, cap):
            super().__init__()
            self.cap = cap

        def require(self, unit, amount=1):
            if unit == "input_bytes" and self.counts.get(unit, 0) + amount > self.cap:
                raise CoreFailure("BUDGET", unit, "finite cumulative input budget")
            super().require(unit, amount)

    exact = Capped(needed)
    assert c.read_ref_note(claim, mapping, exact) == note.body
    assert exact.counts["input_bytes"] == needed
    short = Capped(needed - 1)
    with pytest.raises(CoreFailure) as error:
        c.read_ref_note(claim, mapping, short)
    assert error.value.code == "BUDGET"
    assert not (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("value", ["ordinary", '"\\\n\x00', "é😀", "\ud800"])
def test_bounded_json_provenance_size_matches_canonical_encoding(core, value):
    c, _, _ = core
    attribution = received(value)
    work = Budget()
    c._meter_provenance_encoding(work, attribution, 1_000_000)
    assert work.counts["input_bytes"] == len(attribution.encoded)


@pytest.mark.parametrize("method", ["lookup", "enumeration"])
def test_bounded_absence_size_matches_canonical_encoding(core, method):
    c, _, _ = core
    evidence = RefAbsenceEvidence(
        'source"é',
        "scope😀",
        b"refs/heads/\xff",
        method,
        "terminal",
        b"refs/heads/" if method == "enumeration" else None,
        "complete" if method == "enumeration" else None,
    )
    work = Budget()
    c._meter_absence_encoding(work, evidence, 1_000_000)
    assert work.counts["input_bytes"] == len(evidence.encoded)

    def refuse(_):
        raise CoreFailure("BUDGET", "absence", "small budget")

    with pytest.raises(CoreFailure) as error:
        RefAbsenceEvidence.decode(evidence.encoded, before_compare=refuse)
    assert error.value.code == "BUDGET"


@pytest.mark.parametrize("count", [1, 2, 3])
def test_bounded_proof_size_matches_canonical_bundle(core, count):
    c, _, repository = core
    proof, _ = old_mapping(repository, b"\x00\xff")
    obs = subject(repository)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures * count
    )
    work = Budget()
    c._meter_proof_bundle(work, evidence, 1_000_000)
    assert work.counts["input_bytes"] == len(evidence.bundle)


def test_proof_meter_rejects_long_invalid_type_before_character_walk(core, monkeypatch):
    c, _, repository = core
    proof, _ = old_mapping(repository)
    claim = RefObservationClaim(
        subject(repository).ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    bad = replace(proof.structures[0], native_type="tree" + "x" * 65_536)
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), (bad,)
    )
    original = c._json_string_bytes

    def checked(value):
        assert len(value) < 1000
        return original(value)

    monkeypatch.setattr(c, "_json_string_bytes", checked)
    with pytest.raises(CoreFailure) as error:
        c._meter_proof_bundle(Budget(), evidence, 512)
    assert error.value.code == "NOTES_ROLE"


def test_budget_exhaustion_inside_stored_decoder_is_not_corruption(core):
    c, path, repository = core
    proof, note = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("distinct-role"), proof.structures
    )
    c.admit_ref_note(evidence, note, str(uuid4()), Budget())
    before_role = []
    original_meter = c._meter_provenance_encoding

    def observe(work, attribution, *args, **kwargs):
        if attribution == evidence.provenance:
            before_role.append(work.counts.get("input_bytes", 0))
        return original_meter(work, attribution, *args, **kwargs)

    c._meter_provenance_encoding = observe
    try:
        assert c.read_ref_note(claim, mapping, Budget()) == note.body
    finally:
        c._meter_provenance_encoding = original_meter
    assert len(before_role) == 1

    class Capped(Budget):
        def require(self, unit, amount=1):
            if (
                unit == "input_bytes"
                and self.counts.get(unit, 0) + amount > before_role[0]
            ):
                raise CoreFailure("BUDGET", unit, "exhausted during stored role decode")
            super().require(unit, amount)

    with pytest.raises(CoreFailure) as error:
        c.read_ref_note(claim, mapping, Capped())
    assert error.value.code == "BUDGET"
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert c.read_ref_note(claim, mapping, Budget()) == note.body


@pytest.mark.parametrize("corruption", ["body", "digest", "missing-role"])
@pytest.mark.parametrize("with_ref_copy", [False, True])
def test_corrupt_legacy_note_conflict_stops_new_note_admission(
    core, corruption, with_ref_copy
):
    c, path, repository = core
    proof, note = old_mapping(repository, b"original legacy note")
    legacy_copy = str(uuid4())
    c.admit_note(proof, note, legacy_copy, Budget())
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures
    )
    if with_ref_copy:
        c.admit_ref_note(evidence, note, str(uuid4()), Budget())
    db = connect(path, "core")
    try:
        if corruption == "missing-role":
            trigger = db.execute(
                "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_note_roles_delete'"
            ).fetchone()[0]
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("DROP TRIGGER p1_immutable_note_roles_delete")
            db.execute("DELETE FROM note_roles")
            db.execute(trigger)
            db.execute("PRAGMA foreign_keys=ON")
        else:
            trigger = db.execute(
                "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_retained_notes_update'"
            ).fetchone()[0]
            db.execute("DROP TRIGGER p1_immutable_retained_notes_update")
            db.execute("PRAGMA ignore_check_constraints=ON")
            if corruption == "body":
                db.execute("UPDATE retained_notes SET body=?", (b"X" + note.body[1:],))
            else:
                db.execute("UPDATE retained_notes SET digest_sha256=?", ("0" * 64,))
            db.execute(trigger)
            db.execute("PRAGMA ignore_check_constraints=OFF")
    finally:
        db.close()
    requested_copy = str(uuid4()) if corruption == "body" else legacy_copy
    diagnosing = {"active": False}
    original_diagnosis = c._diagnose_ref_note_conflict

    def track_diagnosis(*args):
        diagnosing["active"] = True
        return original_diagnosis(*args)

    class NoDiagnosticInput(Budget):
        def require(self, unit, amount=1):
            if unit == "input_bytes" and diagnosing["active"]:
                raise CoreFailure("BUDGET", unit, "no diagnostic input budget")
            super().require(unit, amount)

    c._diagnose_ref_note_conflict = track_diagnosis
    try:
        with pytest.raises(CoreFailure) as limited:
            c.admit_ref_note(evidence, note, requested_copy, NoDiagnosticInput())
    finally:
        c._diagnose_ref_note_conflict = original_diagnosis
    assert limited.value.code == "BUDGET"
    assert diagnosing["active"]
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert len(c.sql("SELECT 1 FROM ref_retained_notes")) == int(with_ref_copy)
    with pytest.raises(CoreFailure) as error:
        c.admit_ref_note(evidence, note, requested_copy, Budget())
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("field", ["direct", "symbolic", "resolved", "peeled"])
def test_exact_copy_replay_rejects_changed_immutable_claim_fields(core, field):
    c, path, repository = core
    proof, note = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures
    )
    copy = str(uuid4())
    c.admit_ref_note(evidence, note, copy, Budget())
    c.admit_ref_note(evidence, note, copy, Budget())
    change = {
        "direct": {"ref_form": "direct", "direct_target_oid": OID("sha1", "b" * 40)},
        "symbolic": {
            "ref_form": "symbolic",
            "symbolic_target_ref_name": b"refs/heads/other",
        },
        "resolved": {"resolved_target_oid": OID("sha1", "b" * 40)},
        "peeled": {"peeled_target_oid": OID("sha1", "b" * 40)},
    }[field]
    altered = replace(evidence, ref_claim=replace(claim, **change))
    with pytest.raises(CoreFailure) as error:
        c.admit_ref_note(altered, note, copy, Budget())
    assert error.value.code == "INCOMPATIBLE_REPLAY"
    assert len(c.sql("SELECT 1 FROM ref_retained_notes")) == 1
    assert not (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "large_field", ["role", "subject", "subject-ref", "claim", "symbolic", "mapping"]
)
def test_note_read_reserves_all_fetched_metadata_before_loading(core, large_field):
    c, path, repository = core
    proof, note = old_mapping(repository)
    obs = subject(repository)
    if large_field == "subject":
        obs = replace(obs, source_attribution="s" * 65_536)
    if large_field == "subject-ref":
        obs = replace(obs, ref_name_bytes=b"refs/heads/" + b"x" * 65_536)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("c" * 65_536 if large_field == "claim" else "ref"),
        "present",
        ref_form="symbolic" if large_field == "symbolic" else None,
        symbolic_target_ref_name=(b"refs/heads/" + b"x" * 65_536)
        if large_field == "symbolic"
        else None,
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "m" * 65_536 if large_field == "mapping" else "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim,
        mapping,
        "single-path",
        received("e" * 65_536 if large_field == "role" else "e"),
        proof.structures,
    )
    c.admit_ref_note(evidence, note, str(uuid4()), Budget())

    class Limited(Budget):
        def require(self, unit, amount=1):
            if unit == "input_bytes" and self.counts.get(unit, 0) + amount > 1_024:
                raise CoreFailure("BUDGET", unit, "small cumulative metadata budget")
            super().require(unit, amount)

    large_fetched = []
    original_factory = c._db.row_factory

    def track_large(cursor, values):
        for value in values:
            if isinstance(value, (str, bytes)) and len(value) > 1_024:
                large_fetched.append(len(value))
        return sqlite3.Row(cursor, values)

    c._db.row_factory = track_large
    try:
        budget = Limited()
        with pytest.raises(CoreFailure) as error:
            c.read_ref_note(claim, mapping, budget)
        assert error.value.code == "BUDGET"
        assert not large_fetched
        assert budget.counts.get("input_bytes", 0) <= 1_024
    finally:
        c._db.row_factory = original_factory
    assert not (path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as per_row_limit:
        c.read_ref_note(claim, mapping, Budget(), max_metadata_bytes=1_024)
    assert per_row_limit.value.code == "BUDGET"
    assert c.read_ref_note(claim, mapping, Budget()) == note.body


@pytest.mark.parametrize("operation", ["observation", "projection", "evidence", "note"])
def test_related_ref_operations_bound_subject_dependencies(core, operation):
    c, path, repository = core
    proof, note = old_mapping(repository)
    obs = replace(subject(repository), source_attribution="s" * 65_536)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance("ref"),
        "present",
        root_oid=proof.capture.root,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim, mapping, "single-path", received("e"), proof.structures
    )

    class Limited(Budget):
        def require(self, unit, amount=1):
            if unit == "input_bytes" and self.counts.get(unit, 0) + amount > 1_024:
                raise CoreFailure("BUDGET", unit, "small cumulative input budget")
            super().require(unit, amount)

    seen = []
    original_factory = c._db.row_factory

    def track_large(cursor, values):
        seen.extend(
            len(value)
            for value in values
            if isinstance(value, (str, bytes)) and len(value) > 1_024
        )
        return sqlite3.Row(cursor, values)

    c._db.row_factory = track_large
    try:
        work = Limited()
        with pytest.raises(CoreFailure) as error:
            if operation == "observation":
                c.ref_observation(obs.ref_observation_key, work)
            elif operation == "projection":
                c.notes_mapping_projection(
                    claim, proof.target, "git-notes", "1", "tree", work
                )
            elif operation == "evidence":
                c.admit_notes_mapping_evidence(evidence, work)
            else:
                c.admit_ref_note(evidence, note, str(uuid4()), work)
        assert error.value.code == "BUDGET"
        assert not seen
        assert work.counts.get("input_bytes", 0) <= 1_024
    finally:
        c._db.row_factory = original_factory
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert not c.sql("SELECT 1 FROM ref_retained_notes")


@pytest.mark.parametrize("operation", ["evidence", "note", "read", "projection"])
@pytest.mark.parametrize(
    "large_field",
    ["claim", "escaped_claim", "mapping", "role", "escaped_role", "symbolic"],
)
def test_related_ref_operations_bound_large_incoming_metadata(
    core, operation, large_field
):
    c, path, repository = core
    proof, note = old_mapping(repository)
    obs = subject(repository)
    c.admit_ref_observation(obs)
    claim = RefObservationClaim(
        obs.ref_observation_key,
        provenance(
            "c" * 65_536
            if large_field == "claim"
            else '"' * 6_000
            if large_field == "escaped_claim"
            else "ref"
        ),
        "present",
        root_oid=proof.capture.root,
        ref_form="symbolic" if large_field == "symbolic" else None,
        symbolic_target_ref_name=(b"refs/heads/" + b"x" * 65_536)
        if large_field == "symbolic"
        else None,
    )
    c.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        proof.capture.root,
        "git-notes",
        "1",
        "m" * 65_536 if large_field == "mapping" else "tree",
        proof.target,
        proof.note,
        proof.path,
    )
    evidence = NotesMappingEvidence(
        claim,
        mapping,
        "single-path",
        received(
            "e" * 65_536
            if large_field == "role"
            else '"' * 6_000
            if large_field == "escaped_role"
            else "e"
        ),
        proof.structures,
    )
    if operation in ("read", "projection"):
        c.admit_ref_note(evidence, note, str(uuid4()), Budget())

    class Limited(Budget):
        def require(self, unit, amount=1):
            if unit == "input_bytes" and self.counts.get(unit, 0) + amount > 10_000:
                raise CoreFailure("BUDGET", unit, "small cumulative metadata budget")
            super().require(unit, amount)

    work = Limited()
    with pytest.raises(CoreFailure) as error:
        if operation == "evidence":
            c.admit_notes_mapping_evidence(evidence, work)
        elif operation == "note":
            c.admit_ref_note(evidence, note, str(uuid4()), work)
        elif operation == "read":
            c.read_ref_note(claim, mapping, work)
        else:
            c.notes_mapping_projection(
                claim,
                proof.target,
                "git-notes",
                "1",
                mapping.interpretation_scope,
                work,
            )
    assert error.value.code == "BUDGET"
    assert work.counts.get("input_bytes", 0) <= 10_000
    assert not (path.parent / "p1-recovery-stop.json").exists()
