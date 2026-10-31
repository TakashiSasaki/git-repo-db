"""Typed complete Notes inventory Coverage for one actual ref result Claim."""

import json
from dataclasses import replace

import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_core import CoreCoverageScope, CoreFailure, Provenance
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ref_coverage import (
    REF_NOTES_INVENTORY,
    RefNotesInventoryCoverageProof,
)
from repo_catalog.domain.ref_observation import (
    NotesMappingGroup,
    RefObservationClaim,
    RefObservationKey,
)
from tests.integration.p1.test_core import Budget, native, provenance
from tests.integration.p1.test_core import core as core
from tests.integration.p1.test_notes import mapping, tree
from tests.integration.p1.test_ref_observation_i1 import subject


def proof_fixture(core, *, fmt="sha1", empty=False, source="source"):
    c, _path, repository = core
    original, _body = mapping(repository, fmt=fmt)
    structure = tree([], fmt) if empty else original.structures[0]
    observation = replace(subject(repository), source_attribution=source)
    result = RefObservationClaim(
        observation.ref_observation_key,
        provenance("ref-result"),
        "present",
        root_object_oid=structure.object_oid,
    )
    c.admit_ref_observation(observation)
    c.admit_ref_observation_claim(result)
    group = NotesMappingGroup(
        result,
        "git-notes",
        "1",
        "native-notes-tree",
        "all-notes-mappings",
        "known_empty" if empty else "complete",
        ()
        if empty
        else ((original.target.object_oid, original.note.object_oid, original.path),),
        provenance("inventory-report"),
    )
    c.admit_notes_mapping_group(group, Budget())
    scope = CoreCoverageScope(
        "ref_observation", (*observation.ref_observation_key.key, REF_NOTES_INVENTORY)
    )
    c.admit_coverage_scope(scope)
    claim = CoverageClaim(scope, 20, "complete")
    c.admit_coverage(claim)
    verified = Provenance(
        "receiver",
        "local-analysis",
        "inventory-check",
        "git-native-notes-inventory",
        "1",
        "receiver_intrinsic",
    )
    return RefNotesInventoryCoverageProof(claim, group, verified, (structure,))


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("empty", [False, True])
def test_complete_inventory_requires_and_rechecks_exact_structures(core, fmt, empty):
    c, path, _repository = core
    proof = proof_fixture(core, fmt=fmt, empty=empty)
    assert c.coverage(proof.coverage_claim.scope).state == "unknown"
    with pytest.raises(CoreFailure, match="typed evidence"):
        c.admit_coverage_proof(proof.coverage_claim, (), provenance("fake"))
    work = Budget()
    c.admit_ref_coverage_proof(proof, work)
    c.admit_ref_coverage_proof(proof, work)
    assert work.counts["proof_steps"] > 0
    assert work.counts["verification_bytes"] > 0 or empty
    with pytest.raises(CoreFailure) as missing_budget:
        c.coverage(proof.coverage_claim.scope)
    assert missing_budget.value.code == "QUERY_BUDGET"
    projection = c.coverage(proof.coverage_claim.scope, Budget())
    assert projection.state == "complete"
    assert projection.known_empty is empty
    assert c.ref_coverage_proofs(proof.coverage_claim, Budget()) == (proof,)
    assert not c.sql("SELECT 1 FROM ref_retained_notes")
    with connect(path, "core") as db:
        assert len(db.execute("PRAGMA table_xinfo(coverage_claims)").fetchall()) == 5
        assert db.execute("SELECT count(*) FROM ref_coverage_proofs").fetchone()[0] == 1


def test_inventory_must_match_whole_checked_group_not_sender_status(core):
    c, path, _ = core
    proof = proof_fixture(core)
    forged = replace(proof, structures=(tree([]),))
    with pytest.raises(CoreFailure) as invalid:
        c.admit_ref_coverage_proof(forged, Budget())
    assert invalid.value.code == "REF_COVERAGE_PROOF"
    assert c.coverage(proof.coverage_claim.scope).state == "unknown"
    assert not c.sql("SELECT 1 FROM ref_coverage_proofs")
    assert not (path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure):
        replace(proof, group=replace(proof.group, status="partial"))
    with pytest.raises(CoreFailure):
        replace(proof, group=replace(proof.group, interpretation_scope="different"))
    partial = replace(
        proof.group, status="partial", provenance=provenance("partial-one")
    )
    second_partial = replace(partial, provenance=provenance("partial-two"))
    c.admit_notes_mapping_group(partial, Budget())
    c.admit_notes_mapping_group(second_partial, Budget())
    with pytest.raises(CoreFailure):
        replace(proof, group=partial)
    with pytest.raises(CoreFailure):
        replace(proof, group=second_partial)
    assert c.coverage(proof.coverage_claim.scope).state == "unknown"
    fake_group = replace(
        proof.group,
        members=((proof.group.members[0][0], "b" * 40, proof.group.members[0][2]),),
        provenance=provenance("fabricated-complete"),
    )
    c.admit_notes_mapping_group(fake_group, Budget())
    with pytest.raises(CoreFailure) as false_complete:
        c.admit_ref_coverage_proof(replace(proof, group=fake_group), Budget())
    assert false_complete.value.code == "REF_COVERAGE_PROOF"
    c.admit_ref_coverage_proof(proof, Budget())


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_commit_and_fanout_inventory_requires_complete_ordered_closure(core, fmt):
    c, _, repository = core
    old, _note = mapping(repository, fmt=fmt)
    target = old.target.object_oid
    inner = tree([("100644", target[2:], old.note)], fmt)
    root_tree = tree([("40000", target[:2], inner.object_oid)], fmt)
    commit = native(
        "commit",
        f"tree {root_tree.object_oid.object_oid}\nauthor A <a@invalid> 0 +0000\ncommitter C <c@invalid> 0 +0000\n\nnotes\n".encode(),
        fmt,
    )
    observation = subject(repository)
    claim = RefObservationClaim(
        observation.ref_observation_key,
        provenance("commit-ref"),
        "present",
        root_object_oid=commit.object_oid,
    )
    c.admit_ref_observation(observation)
    c.admit_ref_observation_claim(claim)
    group = NotesMappingGroup(
        claim,
        "git-notes",
        "1",
        "native-notes-tree",
        "all-notes-mappings",
        "complete",
        ((target, old.note.object_oid, target[:2] + "/" + target[2:]),),
        provenance("fanout-report"),
    )
    c.admit_notes_mapping_group(group, Budget())
    scope = CoreCoverageScope(
        "ref_observation", (*observation.ref_observation_key.key, REF_NOTES_INVENTORY)
    )
    c.admit_coverage_scope(scope)
    coverage = CoverageClaim(scope, 20, "complete")
    c.admit_coverage(coverage)
    verification = Provenance(
        "receiver",
        "event",
        "whole-tree",
        "git-native-notes-inventory",
        "1",
        "receiver_intrinsic",
    )
    proof = RefNotesInventoryCoverageProof(
        coverage, group, verification, (commit, root_tree, inner)
    )
    for supplied in (
        (commit, root_tree),
        (root_tree, commit, inner),
        (commit, root_tree, inner, inner),
    ):
        with pytest.raises(CoreFailure) as error:
            c.admit_ref_coverage_proof(replace(proof, structures=supplied), Budget())
        assert error.value.code == "REF_COVERAGE_PROOF"
        assert not c.sql("SELECT 1 FROM ref_coverage_proofs")
    c.admit_ref_coverage_proof(proof, Budget())
    assert c.coverage(scope, Budget()).state == "complete"
    with pytest.raises(CoreFailure) as limited:
        c.ref_coverage_proofs(coverage, Budget(), max_structures=2)
    assert limited.value.code == "QUERY_BUDGET"
    assert c.coverage(scope, Budget()).state == "complete"


def test_lost_stored_report_group_stops_instead_of_rebinding(core):
    c, path, _ = core
    proof = proof_fixture(core)
    c.admit_ref_coverage_proof(proof, Budget())
    db = connect(path, "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_notes_mapping_groups_delete'"
        ).fetchone()[0]
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("DROP TRIGGER p1_immutable_notes_mapping_groups_delete")
        db.execute("DELETE FROM notes_mapping_groups")
        db.execute(trigger)
        db.commit()
    finally:
        db.close()
    with pytest.raises(CoreFailure) as error:
        c.admit_ref_coverage_proof(proof, Budget())
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()


def test_coverage_latest_stale_and_equal_time_conflict_survive(core):
    c, _, _ = core
    proof = proof_fixture(core, empty=True)
    c.admit_ref_coverage_proof(proof, Budget())
    scope = proof.coverage_claim.scope
    assert c.coverage(scope, Budget()).known_empty
    assert c.admit_coverage(CoverageClaim(scope, 19, "complete")) == "stale"
    assert c.admit_coverage(CoverageClaim(scope, 20, "partial")) == "insert"
    assert c.coverage(scope, Budget()).state == "conflict"
    assert c.admit_coverage(CoverageClaim(scope, 21, "unknown")) == "insert"
    assert c.coverage(scope, Budget()).state == "unknown"


def test_conflicting_ref_result_is_not_hidden_by_one_complete_inventory(core):
    c, _, _ = core
    proof = proof_fixture(core, empty=True)
    c.admit_ref_coverage_proof(proof, Budget())
    other_root = tree([("100644", "a" * 40, proof.group.ref_claim.root_object_oid)])
    other = replace(
        proof.group.ref_claim,
        root_object_oid=other_root.object_oid,
        provenance=provenance("other-ref-result"),
    )
    c.admit_ref_observation_claim(other)
    result = c.coverage(proof.coverage_claim.scope, Budget())
    assert result.state == "conflict"
    assert not result.known_empty


def test_evidence_coordinate_cannot_rebind_to_later_coverage_time(core):
    c, path, _ = core
    proof = proof_fixture(core)
    c.admit_ref_coverage_proof(proof, Budget())
    later = CoverageClaim(proof.coverage_claim.scope, 21, "complete")
    c.admit_coverage(later)
    with pytest.raises(CoreFailure) as error:
        c.admit_ref_coverage_proof(replace(proof, coverage_claim=later), Budget())
    assert error.value.code == "INCOMPATIBLE_REPLAY"
    assert c.coverage(later.scope).state == "unknown"
    assert not (path.parent / "p1-recovery-stop.json").exists()


def test_distinct_receiver_checks_remain_distinct_under_bounded_reads(core):
    c, path, _ = core
    proof = proof_fixture(core)
    second = replace(
        proof,
        verification_provenance=replace(
            proof.verification_provenance, observation="independent-analysis"
        ),
    )
    c.admit_ref_coverage_proof(proof, Budget())
    c.admit_ref_coverage_proof(second, Budget())
    with pytest.raises(CoreFailure) as limited:
        c.ref_coverage_proofs(proof.coverage_claim, Budget(), max_proofs=1)
    assert limited.value.code == "QUERY_BUDGET"
    assert not (path.parent / "p1-recovery-stop.json").exists()
    result = c.ref_coverage_proofs(proof.coverage_claim, Budget())
    assert set(result) == {proof, second}
    assert c.coverage(proof.coverage_claim.scope, Budget()).state == "complete"


@pytest.mark.parametrize("via_replay", [False, True])
def test_stored_structural_corruption_causes_persistent_stop(core, via_replay):
    c, path, _ = core
    proof = proof_fixture(core)
    c.admit_ref_coverage_proof(proof, Budget())
    db = connect(path, "core")
    try:
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE name='p1_immutable_ref_coverage_proofs_update'"
        ).fetchone()[0]
        db.execute("DROP TRIGGER p1_immutable_ref_coverage_proofs_update")
        row = db.execute("SELECT structures_json FROM ref_coverage_proofs").fetchone()
        data = json.loads(row[0])
        data[0][3] = "00" + data[0][3][2:]
        db.execute(
            "UPDATE ref_coverage_proofs SET structures_json=?",
            (json.dumps(data, separators=(",", ":")),),
        )
        db.execute(trigger)
        db.commit()
    finally:
        db.close()
    with pytest.raises(CoreFailure) as error:
        if via_replay:
            c.admit_ref_coverage_proof(proof, Budget())
        else:
            c.coverage(proof.coverage_claim.scope, Budget())
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as stopped:
        c.ref_observation(
            RefObservationKey(*proof.coverage_claim.scope.coordinates[:2]), Budget()
        )
    assert stopped.value.code == "RECOVERY_STOP"
    blocked_work = Budget()
    with pytest.raises(CoreFailure) as stopped_admission:
        c.admit_ref_coverage_proof(proof, blocked_work)
    assert stopped_admission.value.code == "RECOVERY_STOP"
    assert blocked_work.counts == {}


def test_budget_refusal_preserves_unfinished_proof_without_corruption(core):
    c, path, _ = core
    proof = proof_fixture(core)
    with pytest.raises(CoreFailure) as error:
        c.admit_ref_coverage_proof(proof, Budget(), max_bytes=32)
    assert error.value.code == "BUDGET"
    assert not c.sql("SELECT 1 FROM ref_coverage_proofs")
    assert not (path.parent / "p1-recovery-stop.json").exists()
    c.admit_ref_coverage_proof(proof, Budget())
    with pytest.raises(CoreFailure) as read_error:
        c.ref_coverage_proofs(proof.coverage_claim, Budget(), max_bytes=32)
    assert read_error.value.code == "QUERY_BUDGET"
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert c.coverage(proof.coverage_claim.scope, Budget()).state == "complete"


def test_scope_byte_limit_applies_to_dependent_ref_subject(core):
    c, path, _ = core
    proof = proof_fixture(core, empty=True, source="s" * 8192)
    c.admit_ref_coverage_proof(proof, Budget())
    with pytest.raises(CoreFailure) as error:
        c.coverage(proof.coverage_claim.scope, Budget(), max_bytes=2048)
    assert error.value.code == "QUERY_BUDGET"
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert c.coverage(proof.coverage_claim.scope, Budget()).known_empty


def test_large_latest_details_are_reserved_before_fetch(core):
    class Tight(Budget):
        def require(self, unit, amount=1):
            super().require(unit, amount)
            if unit == "input_bytes" and self.counts.get(unit, 0) + amount > 1024:
                raise CoreFailure("BUDGET", unit, "finite request bytes")

    c, path, repository = core
    observation = subject(repository)
    c.admit_ref_observation(observation)
    scope = CoreCoverageScope(
        "ref_observation", (*observation.ref_observation_key.key, "reported-scope")
    )
    c.admit_coverage_scope(scope)
    details = json.dumps({"detail": "x" * 65536}, separators=(",", ":"), sort_keys=True)
    c.admit_coverage(CoverageClaim(scope, 20, "partial", details))
    statements = []
    c._db.set_trace_callback(statements.append)
    try:
        with pytest.raises(CoreFailure) as error:
            c.coverage(scope, Tight())
        assert error.value.code == "BUDGET"
    finally:
        c._db.set_trace_callback(None)
    assert any("octet_length(details_json)" in statement for statement in statements)
    assert not any(
        "SELECT observed_at_us,coverage_state,details_json FROM coverage_claims"
        in statement
        for statement in statements
    )
    assert not (path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as local_limit:
        c.coverage(scope, max_bytes=1024)
    assert local_limit.value.code == "QUERY_BUDGET"
    work = Budget()
    assert c.coverage(scope, work).state == "partial"
    assert work.counts["input_bytes"] >= len(details)


def test_large_requested_scope_is_bounded_before_encoding(core):
    class Tight(Budget):
        def require(self, unit, amount=1):
            super().require(unit, amount)
            if unit == "input_bytes" and self.counts.get(unit, 0) + amount > 1024:
                raise CoreFailure("BUDGET", unit, "finite request bytes")

    c, path, repository = core
    observation = subject(repository)
    c.admit_ref_observation(observation)
    scope = CoreCoverageScope(
        "ref_observation", (*observation.ref_observation_key.key, "x" * 65536)
    )
    statements = []
    c._db.set_trace_callback(statements.append)
    try:
        with pytest.raises(CoreFailure) as error:
            c.coverage(scope, Tight())
        assert error.value.code == "BUDGET"
    finally:
        c._db.set_trace_callback(None)
    assert not any("FROM coverage_claims" in statement for statement in statements)
    assert not (path.parent / "p1-recovery-stop.json").exists()


def test_proof_steps_are_cumulative_on_failed_retries(core):
    class Limited(Budget):
        def require(self, unit, amount=1):
            super().require(unit, amount)
            if unit == "proof_steps" and self.counts.get(unit, 0) + amount > 1:
                raise CoreFailure("BUDGET", unit, "finite cumulative work")

    c, path, _ = core
    proof = proof_fixture(core)
    work = Limited()
    for _ in range(2):
        with pytest.raises(CoreFailure) as error:
            c.admit_ref_coverage_proof(proof, work)
        assert error.value.code == "BUDGET"
        assert work.counts["proof_steps"] == 1
        assert not c.sql("SELECT 1 FROM ref_coverage_proofs")
    assert not (path.parent / "p1-recovery-stop.json").exists()
