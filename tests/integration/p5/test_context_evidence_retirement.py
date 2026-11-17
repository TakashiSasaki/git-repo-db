"""Original unknown evidence survives stronger values and real Provider parsing."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.github.production_intake import normalize_review
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.exchange import (
    ExchangeSelectionScope,
    decode_package,
    encode_package,
)
from repo_catalog.domain.p1_context import FieldClock, ResourceKey
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
from tests.support.context_admission import (
    AuthorizedProviderAcquisition as ProviderAcquisition,
)
from tests.support.context_admission import fixture_transaction


@pytest.mark.parametrize("family", ["issue", "issue-comment", "review-comment"])
def test_known_same_value_clock_never_rebinds_an_unknown_original_across_exchange(
    tmp_path, family
):
    source, receiver, onward = (
        tmp_path / name for name in ("source", "receiver", "onward")
    )
    for directory in (source, receiver, onward):
        initialize(directory)
    (key, _), declarations = resource_case(family)
    grants = DependencySet(
        resources={PARENT, key},
        repositories={REPOSITORY},
        provider_registrations={SERVICE},
    )
    original_b = provenance("original-B")
    original_c = provenance("independent-C")
    with fixture_transaction(source, grants) as context:
        context.provider(SERVICE, "github")
        context.repository(REPOSITORY)
        context.resource(PARENT)
        context.resource(key, identification=declarations[0])
        context.admit_text(
            key, "A", FieldClock("provider.updated_at", 10), provenance("original-A"), 1
        )
        context.admit_text(
            key, "B", FieldClock("provider.updated_at", None), original_b, 2
        )
        context.admit_text(
            key, "C", FieldClock("provider.updated_at", None), original_c, 3
        )
        unknown = tuple(
            c
            for c in context.candidates(key, "text_body_sha256")
            if c.clock.at_us is None
        )
    exporter = ExchangeService(source)
    selection = ExchangeSelectionScope(all_selected=True)
    unordered = decode_package(
        encode_package(exporter.export_package(selection=selection))
    )
    receive(receiver, unordered)
    with fixture_transaction(source, grants) as context:
        # Even identical value/provenance/observation coordinates cannot supply
        # the unknown original's missing source clock. This is a new clocked fact.
        context.admit_text(
            key, "B", FieldClock("provider.updated_at", 20), original_b, 2
        )
        candidates = context.candidates(key, "text_body_sha256")
        assert set(unknown) <= set(candidates)
        assert {c.clock.at_us for c in candidates} == {None, 20}
        known_b = next(c for c in candidates if c.clock.at_us == 20)
        assert known_b.provenance_json == original_b and known_b.observed_at_us == 2
        assert (
            context.admit_text(
                key,
                "B",
                FieldClock("provider.updated_at", 15),
                provenance("delayed-B"),
                4,
            )
            == "stale"
        )
    strengthened = decode_package(
        encode_package(exporter.export_package(selection=selection))
    )
    receive(receiver, strengthened)
    assert receive(receiver, strengthened, first=False).idempotent_replay
    with Context.snapshot(receiver) as context:
        assert set(context.candidates(key, "text_body_sha256")) == set(candidates)
    with fixture_transaction(source, grants) as context:
        context.admit_text(
            key, "A", FieldClock("provider.updated_at", 30), provenance("later-A"), 5
        )
        final = context.candidates(key, "text_body_sha256")
        assert set(unknown) <= set(final)
        assert {c.clock.at_us for c in final} == {None, 30}
    latest = decode_package(
        encode_package(exporter.export_package(selection=selection))
    )
    receive(receiver, latest)
    # Replaying earlier known values cannot resurrect a dominated known fact or
    # erase a distinct unknown capture simply because its body matches.
    receive(receiver, unordered, first=False)
    receive(receiver, strengthened, first=False)
    # A new genuine PackageKey forces the receiver to re-evaluate the older
    # known fact; this is not merely an Operational lost-ack replay shortcut.
    resent_originals = replace(
        strengthened, package_id=str(uuid4()), digest_sha256=None
    )
    receive(receiver, decode_package(encode_package(resent_originals)))
    forwarded = ExchangeService(receiver).export_package(selection=selection)
    receive(onward, decode_package(encode_package(forwarded)))
    for directory in (receiver, onward):
        with Context.snapshot(directory) as context:
            assert set(context.candidates(key, "text_body_sha256")) == set(final)
            assert {context.read_text(json.loads(c.value_json)) for c in final} == {
                "A",
                "B",
                "C",
            }


def test_real_review_parser_never_uses_submission_or_invented_scope_as_update_clock(
    tmp_path,
):
    directory = tmp_path / "reviews"
    initialize(directory)
    pull = ResourceKey.from_native(SERVICE, "pull_request", "20")
    with fixture_transaction(
        directory, DependencySet(resources={pull}, provider_registrations={SERVICE})
    ) as context:
        context.provider(SERVICE, "github")
        context.resource(pull)
    payloads = (
        {"id": 10, "body": "first", "submitted_at": "2026-10-11T10:00:00Z"},
        {
            "id": 10,
            "body": "second",
            "submitted_at": "2026-10-12T10:00:00Z",
            "updated_at": "2026-10-13T10:00:00Z",
            "provider_clock_scope": "invented-submission-clock",
            "provider_updated_at_us": 2**60,
        },
    )
    units = tuple(
        normalize_review(SERVICE, "20", payload, stamp, provenance(f"review-{stamp}"))
        for stamp, payload in zip((10, 2**60), payloads, strict=True)
    )
    assert all(
        unit.clock == FieldClock("github:review:observation", None) for unit in units
    )
    ProviderAcquisition(directory).admit_units(units)
    with Context.snapshot(directory) as context:
        candidates = context.candidates(units[0].primary_resource, "text_body_sha256")
        assert len(candidates) == 2
        assert {c.clock.at_us for c in candidates} == {None}
        assert {c.observed_at_us for c in candidates} == {10, 2**60}
        assert {context.read_text(json.loads(c.value_json)) for c in candidates} == {
            "first",
            "second",
        }
        assert {c.provenance_json for c in candidates} == {
            unit.provenance_json for unit in units
        }
        assert (
            len(context.candidates(units[0].primary_resource, "submitted_at_us")) == 2
        )
    assert not (directory / "p1-recovery-stop.json").exists()
