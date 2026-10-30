"""Original ADR 0036 input, distinct reports, and receiver-only authority."""

from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import (
    InMemoryNotesProgress,
    UnlimitedWorkBudget,
)
from repo_catalog.application.acquisition import GitAcquisition
from repo_catalog.domain.acquisition import NotesAcquisitionSpec, RefNotesInput
from repo_catalog.domain.native_acquisition import native_request_intent
from repo_catalog.domain.p1_core import CoreFailure, Provenance, encode
from repo_catalog.domain.ref_observation import (
    NotesMapping,
    NotesMappingClaim,
    NotesMappingGroup,
    RefAbsenceEvidence,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
    new_uuid7,
)
from tests.integration.p4 import conftest as fixtures
from tests.integration.p5.test_ref_inventory_wiring import (
    budget_spent,
    enable_context,
    request_for,
    run_request,
)

acquisition = fixtures.acquisition


def original_input(case, *, body=b"\x00\xfforiginal\n", commit=False):
    capture, target, note = fixtures.fixture_note(case, body=body, commit=commit)
    subject = RefObservation(
        RefObservationKey(str(uuid4()), new_uuid7()),
        case[3],
        b"refs/notes/external-\xff",
        "unauthenticated-external-report",
        "original-visibility",
        None,
    )
    provenance = Provenance("original", "original-read", "result", "reporter", "1")
    claim = RefObservationClaim(
        subject.ref_observation_key, provenance, "present", root_oid=capture.root
    )
    mapping = NotesMapping(
        capture.root, "git-notes", "1", "tree", target, note, target.full_oid
    )
    mapping_claim = NotesMappingClaim(
        claim, mapping, replace(provenance, coordinate="mapping")
    )
    group = NotesMappingGroup(
        claim,
        "git-notes",
        "1",
        "tree",
        "all-notes-mappings",
        "complete",
        ((target.full_oid, note.full_oid, target.full_oid),),
        replace(provenance, coordinate="whole-group"),
    )
    return RefNotesInput(subject, (claim,), (mapping_claim,), (group,)), target, note


def with_input(case, value, *, metadata=False, **options):
    return replace(
        request_for(case, metadata=metadata),
        notes=NotesAcquisitionSpec(ref_inputs=(value,), **options),
    )


@pytest.mark.parametrize("paired", [False, True], ids=["core", "paired"])
@pytest.mark.parametrize("metadata", [False, True], ids=["native", "metadata"])
def test_original_reports_never_become_receiver_proof(acquisition, paired, metadata):
    app, _, _, _, _, core_path, _ = acquisition
    value, target, note = original_input(acquisition)
    if paired:
        enable_context(acquisition)
    request = with_input(acquisition, value, metadata=metadata)
    first = run_request(acquisition, request, paired=paired, metadata=metadata)
    subject = app.core.ref_observation(value.observation.ref_observation_key, app.work)
    assert subject.ref_observation == value.observation
    assert subject.claims == value.claims
    view = app.core.ref_notes_inventory_projection(value.claims[0], app.work)
    assert [entry.group for entry in view.groups] == list(value.mapping_groups)
    assert not any(entry.current_verified for entry in view.groups)
    assert view.coverage.state == "unknown"
    assert not app.core.sql("SELECT 1 FROM ref_retained_notes")
    assert not app.core.sql("SELECT 1 FROM notes_mapping_evidence")
    with pytest.raises(CoreFailure) as unavailable:
        app.core.read_ref_note(
            value.claims[0], value.mapping_claims[0].mapping, app.work
        )
    assert unavailable.value.code == "NOTES_ROLE_UNAVAILABLE"
    assert not app.core.sql("SELECT 1 FROM captures")
    assert not first.notes_inventories and not first.note_acquisitions
    assert set((value.claims[0].root_oid, target, note)) <= set(first.admitted_objects)
    before = budget_spent(acquisition, request)
    again = run_request(
        acquisition, request, paired=paired, metadata=metadata, new_request=False
    )
    after = budget_spent(acquisition, request)
    assert again.admitted_objects == first.admitted_objects
    assert after["metadata_units"] > before["metadata_units"]
    assert after["input_bytes"] > before["input_bytes"]
    changed = replace(value.observation, visibility_scope="changed")
    altered = replace(
        request,
        notes=replace(request.notes, ref_inputs=(replace(value, observation=changed),)),
    )
    with pytest.raises(CoreFailure, match="intent changed"):
        run_request(
            acquisition, altered, paired=paired, metadata=metadata, new_request=False
        )
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("paired", [False, True], ids=["core", "paired"])
@pytest.mark.parametrize("metadata", [False, True], ids=["native", "metadata"])
def test_explicit_claims_use_real_root_specific_checks(acquisition, paired, metadata):
    app, *_ = acquisition
    value, target, note = original_input(acquisition, commit=metadata)
    if paired:
        enable_context(acquisition)
    request = with_input(
        acquisition,
        value,
        metadata=metadata,
        acquire_inventories=True,
        target_oids=(target,),
    )
    result = run_request(acquisition, request, paired=paired, metadata=metadata)
    assert result.status == "complete"
    assert len(result.ref_note_acquisitions) == len(result.ref_notes_inventories) == 1
    assert result.ref_note_acquisitions[0].body_retained
    assert all(check.verified for check in result.ref_inventory_verifications)
    assert result.ref_note_acquisitions[0].claim == value.claims[0]
    assert not app.core.sql("SELECT 1 FROM captures")
    assert not app.core.sql("SELECT 1 FROM retained_notes")
    assert not app.core.sql(
        "SELECT 1 FROM retained_metadata WHERE full_oid=?", (target.full_oid,)
    )
    assert app.core.sql(
        "SELECT 1 FROM ref_retained_notes WHERE note_oid=?", (note.full_oid,)
    )
    before = budget_spent(acquisition, request)
    replay = run_request(
        acquisition, request, paired=paired, metadata=metadata, new_request=False
    )
    assert replay.ref_note_acquisitions == result.ref_note_acquisitions
    assert replay.ref_inventory_verifications == result.ref_inventory_verifications
    assert (
        budget_spent(acquisition, request)["verification_bytes"]
        > before["verification_bytes"]
    )


@pytest.mark.parametrize("paired", [False, True], ids=["core", "paired"])
def test_all_competing_claims_keep_their_roots_and_permissions(acquisition, paired):
    app, *_ = acquisition
    value, target, _ = original_input(acquisition)
    other, _, _ = original_input(acquisition, body=b"different", commit=True)
    first = value.claims[0]
    second = replace(
        first,
        root_oid=other.claims[0].root_oid,
        provenance=replace(first.provenance, coordinate="independent-root"),
    )
    unknown = replace(
        first, root_oid=None, provenance=replace(first.provenance, coordinate="unknown")
    )
    absent = RefObservationClaim(
        first.ref_observation_key,
        replace(first.provenance, coordinate="absent"),
        "absent",
        absence_evidence=RefAbsenceEvidence(
            value.observation.source_attribution,
            value.observation.visibility_scope,
            value.observation.ref_name_bytes,
            "lookup",
            "reported-exit-2",
        ),
    )
    value = replace(value, claims=(unknown, first, second, absent))
    if paired:
        enable_context(acquisition)
    request = with_input(
        acquisition, value, acquire_inventories=True, target_oids=(target,)
    )
    result = run_request(acquisition, request, paired=paired)
    view = app.core.ref_observation(first.ref_observation_key, app.work)
    assert view.conflict and set(view.claims) == set(value.claims)
    assert result.status == "partial"
    assert result.deferred_ref_claims == (unknown, absent)
    assert {x.claim for x in result.ref_note_acquisitions} == {first, second}
    assert all(
        x.role_verified and x.body_retained for x in result.ref_note_acquisitions
    )
    assert {x.group.ref_claim for x in result.ref_inventory_verifications} == {
        first,
        second,
    }
    assert not app.core.sql("SELECT 1 FROM captures")


def test_missing_source_defers_checks_but_preserves_reports(acquisition):
    app, _, _, _, _, core_path, _ = acquisition
    value, _, _ = original_input(acquisition)
    unit = with_input(acquisition, value, metadata=True, acquire_inventories=True)
    result = GitAcquisition(
        core_path, operational=core_path.parent
    ).acquire_metadata_only(unit, new_request=True)
    assert result.status == "partial" and result.failure_code == "REF_NOTES_DEFERRED"
    assert result.deferred_ref_claims == value.claims
    assert not result.ref_inventory_verifications
    assert (
        app.core.ref_observation(value.observation.ref_observation_key, app.work).claims
        == value.claims
    )


def test_foreign_subject_refused_before_any_admission(acquisition):
    app, *_ = acquisition
    value, _, _ = original_input(acquisition)
    value = replace(
        value, observation=replace(value.observation, repository_uuidv4=str(uuid4()))
    )
    request = with_input(acquisition, value)
    with pytest.raises(CoreFailure) as error:
        run_request(acquisition, request)
    assert error.value.code == "REPOSITORY_SCOPE"
    assert not app.core.sql("SELECT 1 FROM ref_observations")


def test_input_budget_stop_cannot_admit_reports_or_proofs(acquisition):
    app, _, _, _, _, core_path, _ = acquisition
    value, _, _ = original_input(acquisition)
    request = with_input(acquisition, value, metadata=True)
    with pytest.raises(CoreFailure) as failure:
        GitAcquisition(core_path).acquire_metadata_only(
            request,
            work=UnlimitedWorkBudget(work_limits={"input_bytes": 1}),
            progress=InMemoryNotesProgress(),
        )
    assert failure.value.code == "BUDGET"
    assert not app.core.sql("SELECT 1 FROM ref_observations")
    assert not app.core.sql("SELECT 1 FROM notes_mapping_evidence")
    assert not (core_path.parent / "p1-recovery-stop.json").exists()


def test_rootless_metadata_stays_rootless_and_verification_deferred(acquisition):
    app, *_ = acquisition
    value, _, _ = original_input(acquisition)
    claim = replace(value.claims[0], root_oid=None)
    value = replace(value, claims=(claim,), mapping_claims=(), mapping_groups=())
    result = run_request(
        acquisition, with_input(acquisition, value, acquire_inventories=True)
    )
    assert result.status == "unknown" and result.deferred_ref_claims == (claim,)
    assert not result.admitted_objects
    assert not result.ref_inventory_verifications
    assert app.core.ref_observation(claim.ref_observation_key, app.work).claims == (
        claim,
    )
    assert not app.core.sql("SELECT 1 FROM notes_mapping_groups")


def test_intent_binds_every_original_result_and_mapping(acquisition):
    value, _, _ = original_input(acquisition)
    request = with_input(acquisition, value)
    baseline = encode(native_request_intent(request))
    variants = (
        replace(
            value,
            observation=replace(
                value.observation, ref_name_bytes=b"refs/notes/external-\xfe"
            ),
        ),
        replace(value, mapping_claims=()),
        replace(
            value, mapping_groups=(replace(value.mapping_groups[0], status="partial"),)
        ),
        replace(
            value,
            claims=(
                *value.claims,
                replace(
                    value.claims[0],
                    root_oid=None,
                    provenance=replace(
                        value.claims[0].provenance, coordinate="unknown"
                    ),
                ),
            ),
        ),
    )
    assert all(
        encode(
            native_request_intent(
                replace(request, notes=replace(request.notes, ref_inputs=(variant,)))
            )
        )
        != baseline
        for variant in variants
    )
    with pytest.raises(CoreFailure):
        replace(value, claims=())
    with pytest.raises(CoreFailure):
        replace(value, claims=[value.claims[0]])
