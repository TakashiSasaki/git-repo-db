"""Public Notes pipeline uses original refs and no Capture-family production."""

import json
from dataclasses import replace

import pytest

from repo_catalog.application.notes import NotesAcquisition
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.cli.production_query import main
from repo_catalog.domain.acquisition import NotesAcquisitionSpec
from repo_catalog.domain.production_query import SearchQuery
from tests.integration.p4 import conftest as fixtures
from tests.integration.p5.test_ref_inventory_wiring import (
    budget_spent,
    enable_context,
    request_for,
    run_request,
)

acquisition = fixtures.acquisition


@pytest.mark.parametrize("metadata", [False, True])
@pytest.mark.parametrize("paired", [False, True])
def test_new_only_acquisition_query_cli_search_replay(
    acquisition, metadata, paired, capsys
):
    app, _, _, _, _, path, _ = acquisition
    _, target, note = fixtures.fixture_note(acquisition, body=b"retirementneedle")
    if paired:
        enable_context(acquisition)
    request = request_for(acquisition, metadata=metadata)
    request = replace(request, notes=replace(request.notes, target_oids=(target,)))
    report = run_request(acquisition, request, metadata=metadata, paired=paired)
    assert report.status == "complete"
    assert report.ref_note_acquisitions[0].body_retained
    assert report.ref_inventory_verifications[0].verified
    assert report.notes_discoveries[0].enumerations
    for field in ("notes_inventories", "note_acquisitions"):
        assert not hasattr(report, field)
    assert not hasattr(report.notes_discoveries[0], "captures")
    for table in (
        "captures",
        "notes_claims",
        "notes_groups",
        "note_roles",
        "retained_notes",
    ):
        assert not app.core.sql(f"SELECT 1 FROM {table}")
    assert app.core.sql("SELECT 1 FROM ref_retained_notes")
    assert not app.core.sql(
        "SELECT 1 FROM retained_metadata WHERE full_oid=?", (target.full_oid,)
    )
    service = ProductionQueryService(path.parent)
    view = service.get_git_object(target)
    assert not hasattr(view, "notes_targets")
    assert any(
        entry.mapping.canonical_note_oid == note for entry in view.ref_notes_targets
    )
    assert (
        main(["ref-observations", "--catalog", str(path.parent), "--limit", "1"]) == 0
    )
    page = json.loads(capsys.readouterr().out)
    assert page["items"] and page["snapshot_token"]
    assert "notes_targets" not in view.to_dict()
    query = SearchQuery(query_text="retirementneedle", projection_kinds=("notes",))
    authority = service.search(query)
    assert authority.total_count == len(report.ref_note_acquisitions) == 2
    assert len({hit.document_key for hit in authority.hits}) == 2
    service.rebuild_search(("notes",))
    assert service.search(query).hits == authority.hits
    before = budget_spent(acquisition, request)
    replay = run_request(
        acquisition, request, metadata=metadata, paired=paired, new_request=False
    )
    assert replay.notes_discoveries == report.notes_discoveries
    assert replay.ref_note_acquisitions == report.ref_note_acquisitions
    after = budget_spent(acquisition, request)
    assert sum(after.values()) > sum(before.values())
    assert not (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "field", ["explicit_captures", "external_claims", "external_groups"]
)
def test_retired_public_carriers_are_rejected(field):
    with pytest.raises(TypeError):
        NotesAcquisitionSpec(**{field: ()})


def test_retired_public_query_and_producer_names():
    for name in (
        "list_notes_captures",
        "get_notes_target",
        "list_notes_inventories",
        "read_note_bytes",
    ):
        assert not hasattr(ProductionQueryService, name)
    with pytest.raises(TypeError):
        ProductionQueryService.get_git_object(None, None, note_captures=())
    for name in ("inventory", "acquire_note"):
        assert not hasattr(NotesAcquisition, name)


def test_retired_cli_command_is_rejected():
    with pytest.raises(SystemExit) as error:
        main(["notes", "--catalog", "/unused"])
    assert error.value.code == 2


def test_legacy_only_rows_do_not_invent_new_claims_or_search_authority(acquisition):
    app, _, _, _, _, path, _ = acquisition
    capture, target, note = fixtures.fixture_note(acquisition, body=b"legacyonlyneedle")
    assert app._legacy_acquire_note(capture, target).body_retained
    service = ProductionQueryService(path.parent)
    assert not service.get_git_object(target).ref_notes_targets
    query = SearchQuery(query_text="legacyonlyneedle", projection_kinds=("notes",))
    assert service.search(query).total_count == 0
    service.rebuild_search(("notes",))
    assert service.search(query).total_count == 0
    assert not app.core.sql("SELECT 1 FROM ref_observations")
    # Retired projections never mutate or delete the retained old family.
    assert app.core.read_note(capture, target, note) == b"legacyonlyneedle"
