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
        proof, _ = old_mapping(repository)
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
    assert c.read_ref_note(claims[0], content) == note.body
    with pytest.raises(CoreFailure, match="claim-specific"):
        c.read_ref_note(claims[1], content)
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
    assert c.read_ref_note(claim, content) == note.body
    altered = replace(claim, ref_form="direct", direct_target_oid=proof.capture.root)
    with pytest.raises(CoreFailure, match="cannot be rebound"):
        c.read_ref_note(altered, content)


def test_valid_recovery_guards_and_export_refusal(core):
    from repo_catalog.adapters.sqlite.recovery_validation import (
        validate_stored_admission_guards,
    )
    from repo_catalog.application.exchange import ExchangeService
    from repo_catalog.domain.exchange import ExchangeError, ExchangeSelectionScope

    c, path, repository = core
    obs = subject(repository)
    c.admit_ref_observation(obs)
    absence = RefAbsenceEvidence(
        "source", "scope", obs.ref_name_bytes, "lookup", "completed"
    )
    c.admit_ref_observation_claim(
        RefObservationClaim(
            obs.ref_observation_key,
            provenance("absence"),
            "absent",
            absence_evidence=absence,
        )
    )
    db = connect(path, "core")
    try:
        validate_stored_admission_guards(db, "core")
    finally:
        db.close()
    with pytest.raises(ExchangeError) as error:
        ExchangeService(path.parent).export_package(
            selection=ExchangeSelectionScope(all_selected=True, include_context=False)
        )
    assert error.value.code == "UNSUPPORTED_REF_OBSERVATION_EXPORT"


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


def test_backup_refuses_incomplete_manifest_without_stopping_healthy_core(core):
    from repo_catalog.adapters.sqlite.recovery import (
        RefObservationBackupUnsupported,
        SQLiteRecoveryAdapter,
    )
    from repo_catalog.domain.recovery import BackupScope

    c, path, repository = core
    obs = subject(repository)
    c.admit_ref_observation(obs)
    destination = path.parent.parent / (path.parent.name + "-backup")
    with pytest.raises(RefObservationBackupUnsupported, match="I3"):
        SQLiteRecoveryAdapter().create_consistent_backup(
            path.parent, destination, BackupScope.GIT_ONLY
        )
    assert not destination.exists()
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
    assert c.read_ref_note(claim, mapping) == note.body


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
        c.read_ref_note(claim, mapping)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()
