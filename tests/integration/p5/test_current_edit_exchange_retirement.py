"""Current field edits travel onward without re-exporting superseded text."""

import json

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.exchange import (
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import FieldClock
from tests.integration.p5.test_context_retirement_exchange import (
    PARENT,
    REPOSITORY,
    SERVICE,
    initialize,
    provenance,
    receive,
    resource_case,
)
from tests.support.context_admission import AuthorizedExchangeService as ExchangeService
from tests.support.context_admission import fixture_transaction


@pytest.mark.parametrize("family", ["issue", "review"])
def test_actual_edit_delivery_reopen_replay_and_onward_export_omit_superseded_body(
    tmp_path, family
):
    (key, _), (declaration, _) = resource_case(family)
    grants = DependencySet(
        resources={PARENT, key},
        repositories={REPOSITORY},
        provider_registrations={SERVICE},
    )
    source, target, onward = (
        tmp_path / name for name in ("source", "target", "onward")
    )
    for directory in (source, target, onward):
        initialize(directory)
    old = "SUPERSEDED-UNREFERENCED-BODY-MUST-NOT-TRAVEL-ONWARD"
    new = "the genuinely later current document"
    with fixture_transaction(source, grants) as context:
        context.provider(SERVICE, "github")
        context.repository(REPOSITORY)
        context.resource(PARENT)
        context.resource(key, identification=declaration)
        context.admit_text(
            key, old, FieldClock("provider.updated_at", 10), provenance("old"), 10
        )
    selection = ExchangeSelectionScope(all_selected=True)

    def export(directory, observed):
        return decode_package(
            encode_package(
                ExchangeService(directory).export_package(
                    selection=selection, exported_at_us=observed
                )
            )
        )

    original = export(source, 100)
    assert old in json.dumps(original.context)
    receive(target, original)
    with fixture_transaction(source, grants) as context:
        context.admit_text(
            key, new, FieldClock("provider.updated_at", 20), provenance("new"), 20
        )
        expected = context.candidates(key, "text_body_sha256")
        assert len(expected) == 1 and expected[0].clock.at_us == 20
    current = export(source, 101)
    assert old not in json.dumps(current.context)
    receive(target, current)
    assert receive(target, original, first=False).idempotent_replay
    assert receive(target, current, first=False).idempotent_replay
    # A physically retained CAS body is not a reachable current field original.
    with Context.snapshot(target) as context:
        assert context.candidates(key, "text_body_sha256") == expected
        assert context.read_text(json.loads(expected[0].value_json)) == new
    forwarded = export(target, 102)
    assert old not in json.dumps(forwarded.context)
    assert new in json.dumps(forwarded.context)
    receive(onward, forwarded)
    with Context.snapshot(onward) as context:
        assert context.candidates(key, "text_body_sha256") == expected
        assert context.read_text(json.loads(expected[0].value_json)) == new
