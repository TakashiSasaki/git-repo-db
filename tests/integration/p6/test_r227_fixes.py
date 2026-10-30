"""R227-01 Group-only discovery and R227-02 callback/corruption separation."""

import json
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_core import OID, CoreFailure, Provenance
from repo_catalog.domain.ref_observation import (
    NotesMappingGroup,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
    new_uuid7,
)
from tests.integration.p4 import conftest as fixtures
from tests.integration.p5.test_ref_inventory_wiring import enable_context, run_request
from tests.integration.p5.test_ref_notes_inputs import original_input, with_input
from tests.integration.p6.conftest import REPOSITORY, populate_rich_catalog
from tests.integration.p6.test_corrections import _mutate

acquisition = fixtures.acquisition


@pytest.mark.parametrize("paired", [False, True])
def test_r227_01_group_only_object_and_wrong_claim_target(acquisition, paired):
    app, _, _, _, _, path, _ = acquisition
    value, target, _ = original_input(acquisition)
    other = replace(
        value.claims[0],
        provenance=replace(value.claims[0].provenance, coordinate="unreported-claim"),
    )
    value = replace(value, claims=(*value.claims, other), mapping_claims=())
    if paired:
        enable_context(acquisition)
    run_request(acquisition, with_input(acquisition, value), paired=paired)
    assert not app.core.sql("SELECT 1 FROM notes_mappings")
    service = ProductionQueryService(path.parent)
    entries = service.get_git_object(target).ref_notes_targets
    assert len(entries) == 1
    assert entries[0].mapping.ref_claim == value.claims[0]
    assert entries[0].mapping.groups == value.mapping_groups
    assert not entries[0].mapping.claims and not entries[0].mapping.evidence
    assert entries[0].mapping.canonical_note_oid is None
    wrong = OID(target.object_format, "b" * len(target.full_oid))
    app.core.admit_object(wrong)
    assert not service.get_git_object(wrong).ref_notes_targets
    assert not app.core.sql("SELECT 1 FROM notes_mappings")


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_r227_01_group_only_paired_resource(tmp_path, fmt):
    catalog = tmp_path / "paired"
    data = populate_rich_catalog(catalog, fmt=fmt)
    key = RefObservationKey(str(uuid4()), new_uuid7())
    subject = RefObservation(
        key, REPOSITORY, b"refs/notes/group-only", "external", "visible"
    )
    provenance = Provenance("external", "read", "claim", "test", "1")
    claim = RefObservationClaim(
        key, provenance, "present", root_oid=data["notes_tree"].oid
    )
    target, note = data["commit_obj"].oid, data["note_blob"].oid
    group = NotesMappingGroup(
        claim,
        "git-notes",
        "1",
        "tree",
        "all",
        "complete",
        ((target.full_oid, note.full_oid, target.full_oid),),
        provenance,
    )
    with closing(GitCore(catalog / "core.sqlite3")) as core:
        core.admit_ref_observation(subject)
        core.admit_ref_observation_claim(claim)
        core.admit_notes_mapping_group(group, UnlimitedWorkBudget())
    view = ProductionQueryService(catalog).get_paired_resource(data["pr_key"])
    head = next(
        r
        for r in view.core_resolutions
        if r.object_view and r.object_view.oid == target
    )
    assert any(group in entry.mapping.groups for entry in head.ref_notes_targets)


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("hook", ["require", "charge"])
def test_r227_02_callback_identity_and_healthy_catalog(acquisition, paired, hook):
    _, _, _, _, _, path, _ = acquisition
    value, _, _ = original_input(acquisition)
    if paired:
        enable_context(acquisition)
    run_request(acquisition, with_input(acquisition, value), paired=paired)
    marker = json.JSONDecodeError("caller budget diagnostic", "", 0)

    class BrokenBudget(UnlimitedWorkBudget):
        def require(self, unit, amount=1):
            if hook == "require":
                raise marker
            return super().require(unit, amount)

        def charge(self, unit, amount):
            if hook == "charge":
                raise marker
            return super().charge(unit, amount)

    service = ProductionQueryService(path.parent)
    with pytest.raises(json.JSONDecodeError) as observed:
        service.list_ref_observations(work=BrokenBudget())
    assert observed.value is marker
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert service.list_ref_observations().items


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("route", ["observation", "group"])
def test_r227_02_real_stored_corruption_still_stops(acquisition, paired, route):
    _, _, _, _, _, path, _ = acquisition
    value, target, _ = original_input(acquisition)
    value = replace(value, mapping_claims=())
    if paired:
        enable_context(acquisition)
    run_request(acquisition, with_input(acquisition, value), paired=paired)
    if route == "observation":
        if paired:
            # Preserve PK/FK pairing so the test reaches the Query reader,
            # rather than the earlier coordinator foreign-key gate.
            _mutate(path, "ref_observations", "source_attribution='' ")
        else:
            # Valid JSON keeps the expression index evaluable; the stored
            # provenance remains invalid and must stop checked reads.
            _mutate(path, "ref_observation_claims", "provenance='[]' ")
    else:
        _mutate(path, "notes_mapping_groups", "membership='{' ")
    service = ProductionQueryService(path.parent)
    with pytest.raises(CoreFailure) as failure:
        if route == "observation":
            service.list_ref_observations()
        else:
            service.get_git_object(target)
    assert failure.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as stopped:
        service.list_ref_observations()
    assert stopped.value.code == "RECOVERY_STOP"
