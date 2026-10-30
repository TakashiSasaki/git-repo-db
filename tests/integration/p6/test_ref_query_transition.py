"""Claim-aware object association and lossless original-ref pagination."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.cli.production_query import main
from repo_catalog.domain.production_query import (
    PageRequest,
    QueryError,
    ref_projection_json,
)
from tests.integration.p4 import conftest as fixtures
from tests.integration.p5.test_ref_inventory_wiring import enable_context, run_request
from tests.integration.p5.test_ref_notes_inputs import original_input, with_input

acquisition = fixtures.acquisition


@pytest.mark.parametrize("paired", [False, True])
def test_reported_notes_visible_without_capture(acquisition, paired, capsys):
    app, _, _, _, _, path, _ = acquisition
    value, target, _ = original_input(acquisition)
    unknown = replace(
        value.claims[0],
        root_oid=None,
        provenance=replace(value.claims[0].provenance, coordinate="unknown"),
    )
    value = replace(value, claims=(*value.claims, unknown))
    if paired:
        enable_context(acquisition)
    run_request(acquisition, with_input(acquisition, value), paired=paired)
    service = ProductionQueryService(path.parent)
    view = service.get_git_object(target)
    assert not view.notes_targets
    assert len(view.ref_notes_targets) == 1
    result = view.ref_notes_targets[0]
    assert set(result.observation.claims) == set(value.claims)
    assert result.mapping.ref_claim == value.claims[0]
    assert result.mapping.claims == value.mapping_claims
    assert not result.mapping.evidence
    encoded = view.to_dict()["ref_notes_targets"][0]
    assert encoded["observation"]["ref_observation"]["ref_name_bytes"] == {
        "bytes_hex": value.observation.ref_name_bytes.hex()
    }
    assert not app.core.sql("SELECT 1 FROM captures")
    assert main(["ref-observations", "--catalog", str(path.parent)]) == 0
    assert json.loads(capsys.readouterr().out)["items"][0] == ref_projection_json(
        result.observation
    )


def test_ref_pages_pin_all_claims_and_reject_stale_cursor(acquisition):
    _, _, _, _, _, path, _ = acquisition
    value, _, _ = original_input(acquisition)
    run_request(acquisition, with_input(acquisition, value))
    from repo_catalog.domain.ref_observation import RefObservationKey, new_uuid7

    second = replace(
        value.observation,
        ref_observation_key=RefObservationKey(str(uuid4()), new_uuid7()),
    )
    second_value = replace(
        value, observation=second, claims=(), mapping_claims=(), mapping_groups=()
    )
    run_request(acquisition, with_input(acquisition, second_value))
    service = ProductionQueryService(path.parent)
    first = service.list_ref_observations(PageRequest(limit=1))
    assert first.has_more
    last = service.list_ref_observations(PageRequest(limit=1, cursor=first.next_cursor))
    assert not last.has_more
    assert first.items[0] != last.items[0]
    third = replace(
        second, ref_observation_key=RefObservationKey(str(uuid4()), new_uuid7())
    )
    run_request(
        acquisition, with_input(acquisition, replace(second_value, observation=third))
    )
    with pytest.raises(QueryError):
        service.list_ref_observations(PageRequest(limit=1, cursor=first.next_cursor))
