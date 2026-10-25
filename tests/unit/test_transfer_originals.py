"""R08/R09 (V02–V08, T02–T06): originals precede filtering and survive replay.

These pure contracts do not enable normal Transfer admission or establish origin
authenticity. Store permission, exact-row time comparison and replay are separate.
"""

import json
from dataclasses import FrozenInstanceError, replace

import pytest

from repo_catalog.domain.context_admission import AdmissionRefused
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingClaimKey,
    MappingSupport,
    ProviderEndpointDeclaration,
    ResourceKey,
    TransferEventReport,
    encode_transfer_supported_provenance,
)
from repo_catalog.domain.p1_context import (
    canonical as J,
)
from repo_catalog.domain.parent_report import ParentObservation, ParentReportKey
from repo_catalog.domain.transfer_sql import event_sql, validate_event

S = "11111111-1111-4111-8111-111111111111"
CORE = "22222222-2222-4222-8222-222222222222"
CORE_2 = "33333333-3333-4333-8333-333333333333"
FROM = "transfer_from_repository"
TO = "transfer_to_repository"
P = J({"source": "fixture-provider", "evidence": "P"})
E = J({"source": "fixture-provider", "evidence": "E"})
I7 = ResourceKey.from_native(S, "issue", "I7")
EVENT = ResourceKey.document(I7, "comment", "timeline_event", "E")
PROVIDER = ResourceKey.from_native(S, "repository", "R")


def parent(*, issue=I7, clock=50, provenance=P, observed=51, event=EVENT):
    return ParentObservation(
        ParentReportKey(
            event,
            J([list(issue.coordinates())]),
            provenance,
            J(
                {
                    "clock": {"at_us": clock, "domain": "provider"},
                    "document_kind": "timeline_event",
                    "state": "complete",
                }
            ),
        ),
        observed,
    )


def report(**changes):
    args = dict(
        clock=FieldClock("provider", 100),
        provenance_json=E,
        parent_report=parent(),
        endpoint_declaration=ProviderEndpointDeclaration(
            "not_reported", "explicit_null"
        ),
        endpoints=((TO, "null"),),
        to_target_json="null",
        observed_at_us=101,
    )
    args.update(changes)
    return TransferEventReport.from_targets(EVENT, **args)


def row(value):
    return (
        *value.event_resource.coordinates(),
        value.members_json,
        value.provenance_json,
        value.scope_json,
        value.observed_at_us,
    )


def test_v03_v04_independent_parent_and_event_originals_roundtrip_t03():
    value = report()
    assert value.parent_report_key.coordinates() == parent().report_key.coordinates()
    assert len(value.parent_report_key.coordinates()) == 7
    assert value.parent_report.observed_at_us == 51
    assert value.clock == FieldClock("provider", 100)
    assert value.observed_at_us == 101
    scope = json.loads(value.scope_json)
    assert json.loads(scope["parent_scope_json"])["clock"]["at_us"] == 50
    assert scope["parent_provenance_json"] == P != value.provenance_json
    assert set(scope) == {
        "clock",
        "event_type",
        "from_provider_repository_id",
        "to_provider_repository_id",
        "provided_roles",
        "endpoints",
        "parent_members_json",
        "parent_provenance_json",
        "parent_scope_json",
    }
    validate_event(*row(value))
    assert event_sql(*row(value)) == 1
    restored = TransferEventReport.from_stored_scope(
        value.report_key,
        (*value.from_relations, *value.to_relations),
        value.scope_json,
        value.members_json,
        101,
        parent_report=parent(),
    )
    assert restored == value
    assert restored.parent_report.observed_at_us == 51
    assert restored.to_relation.event_report_scope_json == value.scope_json


def test_parent_observation_nullable_time_is_explicit_payload_not_identity():
    unknown = parent(observed=None)
    known = parent(observed=51)
    assert unknown.report_key == known.report_key
    assert unknown != known
    assert report(parent_report=unknown).parent_report.observed_at_us is None
    with pytest.raises(TypeError):
        ParentObservation(known.report_key)
    with pytest.raises(FrozenInstanceError):
        known.observed_at_us = 101


@pytest.mark.parametrize("bad", [True, 1.0, "51", 0, -1, 2**63])
def test_v08_parent_observation_rejects_coerced_or_out_of_range_times(bad):
    with pytest.raises((TypeError, ValueError)):
        parent(observed=bad)


@pytest.mark.parametrize(
    "missing", ["parent_report", "endpoint_declaration", "endpoints"]
)
def test_t02_t05_admission_constructor_requires_each_original(missing):
    value = report()
    args = dict(
        report_key=value.report_key,
        parent_report=value.parent_report,
        endpoint_declaration=value.endpoint_declaration,
        endpoints=value.endpoints,
        observed_at_us=101,
        to_relations=value.to_relations,
    )
    del args[missing]
    with pytest.raises(TypeError):
        TransferEventReport(**args)
    args[missing] = None
    with pytest.raises(AdmissionRefused) as caught:
        TransferEventReport(**args)
    assert caught.value.code == "INCOMPLETE_ORIGINAL_REPORT"


def test_parent_key_cannot_bind_another_child_or_borrow_event_coordinates():
    other_event = ResourceKey.document(I7, "comment", "timeline_event", "other")
    with pytest.raises(ValueError, match="exact Event"):
        report(parent_report=parent(event=other_event))
    value = report()
    borrowed = parent(clock=100, provenance=E, observed=101)
    with pytest.raises(ValueError, match="original"):
        TransferEventReport.from_stored_scope(
            value.report_key,
            value.to_relations,
            value.scope_json,
            value.members_json,
            value.observed_at_us,
            parent_report=borrowed,
        )
    # An alternative Parent is lawful original evidence, not a winning report.
    i8 = ResourceKey.from_native(S, "issue", "I8")
    alternate = report(parent_report=parent(issue=i8))
    assert alternate.parent_issue == i8
    assert alternate.issue_resource == I7
    assert alternate.parent_report_key != value.parent_report_key


def test_stored_scope_requires_authorized_original_parent_observation():
    value = report()
    with pytest.raises(TypeError):
        TransferEventReport.from_stored_scope(
            value.report_key,
            value.to_relations,
            value.scope_json,
            value.members_json,
            value.observed_at_us,
        )


@pytest.mark.parametrize(
    "coordinate", ["parent_members_json", "parent_provenance_json", "parent_scope_json"]
)
@pytest.mark.parametrize("omit", [False, True])
def test_v08_missing_or_null_parent_coordinate_is_incomplete(coordinate, omit):
    value = report()
    scope = json.loads(value.scope_json)
    if omit:
        del scope[coordinate]
    else:
        scope[coordinate] = None
    with pytest.raises(AdmissionRefused) as caught:
        TransferEventReport.from_stored_scope(
            value.report_key,
            value.to_relations,
            J(scope),
            value.members_json,
            value.observed_at_us,
            parent_report=parent(),
        )
    assert caught.value.code == "INCOMPLETE_ORIGINAL_REPORT"


def test_v04_v06_not_reported_null_and_provider_only_have_distinct_meanings_t06():
    null = report()
    unresolved = report(
        endpoint_declaration=ProviderEndpointDeclaration("not_reported", PROVIDER),
        endpoints=(),
        to_target_json=None,
    )
    assert null.from_state == unresolved.from_state == "absent"
    assert null.to_state == "explicit_null"
    assert unresolved.to_state == "unresolved_provider_only"
    assert null.provided_roles == unresolved.provided_roles == frozenset({TO})
    assert null.endpoints == ((TO, "null"),)
    assert unresolved.endpoints == ()
    assert null.members_json == "[]"
    assert unresolved.members_json == J([list(PROVIDER.coordinates())])
    assert (
        json.loads(unresolved.scope_json)["to_provider_repository_id"]
        == PROVIDER.provider_resource_id
    )
    validate_event(*row(unresolved))
    with pytest.raises(AdmissionRefused) as caught:
        ProviderEndpointDeclaration(None, "explicit_null")
    assert caught.value.code == "INCOMPLETE_ORIGINAL_REPORT"


def test_v05_truncation_cannot_become_genuine_one_sided_t05():
    declaration = ProviderEndpointDeclaration("explicit_null", "explicit_null")
    with pytest.raises(AdmissionRefused) as caught:
        report(
            endpoint_declaration=declaration, endpoints=((FROM, "null"), (TO, "null"))
        )
    assert caught.value.code == "INCOMPLETE_ENDPOINT_SET"
    complete = report(
        endpoint_declaration=declaration,
        endpoints=((FROM, "null"), (TO, "null")),
        from_target_json="null",
    )
    assert complete.is_two_sided
    assert report().is_one_sided
    with pytest.raises(AdmissionRefused) as caught:
        replace(complete, from_relations=())
    assert caught.value.code == "INCOMPLETE_ENDPOINT_SET"
    assert len(complete.from_relations) == len(complete.to_relations) == 1


@pytest.mark.parametrize(
    "endpoints",
    [
        ((TO, "null"), (FROM, "null")),
        ((FROM, "null"), (FROM, "null"), (TO, "null")),
        [(FROM, "null"), (TO, "null")],
    ],
)
def test_r09_original_endpoint_pairs_are_sorted_unique_exact_tuples(endpoints):
    with pytest.raises(ValueError):
        report(
            endpoint_declaration=ProviderEndpointDeclaration(
                "explicit_null", "explicit_null"
            ),
            endpoints=endpoints,
            from_target_json="null",
        )


@pytest.mark.parametrize(
    "declaration,endpoints",
    [
        (
            ProviderEndpointDeclaration("not_reported", "explicit_null"),
            ((FROM, "null"), (TO, "null")),
        ),
        (ProviderEndpointDeclaration("not_reported", PROVIDER), ((TO, "null"),)),
        (
            ProviderEndpointDeclaration("not_reported", "explicit_null"),
            ((TO, J(CORE)),),
        ),
    ],
)
def test_r09_declaration_cannot_be_rewritten_from_endpoint_rows(declaration, endpoints):
    with pytest.raises(ValueError):
        report(endpoint_declaration=declaration, endpoints=endpoints)


def test_v07_multiple_original_mapping_alternatives_are_preserved():
    claims = tuple(
        MappingClaimKey(
            PROVIDER,
            "represents_repository",
            FieldClock("provider", 80),
            J(target),
            J({"source": "fixture-provider", "evidence": target}),
        )
        for target in (CORE, CORE_2)
    )
    supports = tuple(MappingSupport(PROVIDER, (claim,)) for claim in claims)
    provenance = encode_transfer_supported_provenance(
        "fixture-provider", "E", [(TO, support) for support in supports]
    )
    targets = tuple(sorted((J(CORE), J(CORE_2))))
    value = report(
        provenance_json=provenance,
        endpoint_declaration=ProviderEndpointDeclaration("not_reported", PROVIDER),
        endpoints=tuple((TO, target) for target in targets),
        to_target_json=targets,
    )
    assert value.to_state == "resolved"
    assert value.endpoints == tuple((TO, target) for target in targets)
    assert len(value.to_relations) == 2
    assert {r.embedded_support for r in value.to_relations} == set(supports)
    validate_event(*row(value))
    assert value.select_for_repositories([CORE]) is None
    assert value.select_for_repositories([CORE, CORE_2]) is value


@pytest.mark.parametrize(
    "change", [dict(selection_truncated=True), dict(omitted_roles=frozenset({FROM}))]
)
def test_selection_diagnostics_cannot_become_admission_capable_reports(change):
    with pytest.raises(AdmissionRefused) as caught:
        replace(report(), **change)
    assert caught.value.code == "OMITTED_BY_SELECTION"


def test_endpoint_duplicate_and_event_original_mismatch_refuse():
    value = report()
    with pytest.raises(AdmissionRefused) as caught:
        replace(value, to_relations=(value.to_relation, value.to_relation))
    assert caught.value.code == "INCOMPLETE_ENDPOINT_SET"
    with pytest.raises(ValueError, match="Event clock/provenance/observation"):
        replace(value, to_relations=(replace(value.to_relation, observed_at_us=51),))
    with pytest.raises(ValueError, match="positive original Event clock"):
        report(clock=FieldClock("provider", None))


def test_sql_scope_keeps_nine_keys_and_rejects_unsorted_original_endpoints():
    value = report(
        endpoint_declaration=ProviderEndpointDeclaration(
            "explicit_null", "explicit_null"
        ),
        endpoints=((FROM, "null"), (TO, "null")),
        from_target_json="null",
    )
    scope = json.loads(value.scope_json)
    scope["endpoints"].reverse()
    mutated = (*row(value)[:5], J(scope), value.observed_at_us)
    assert event_sql(*mutated) == 0
    scope = json.loads(report().scope_json)
    scope["endpoints"] = [[TO, J(CORE)]]
    assert event_sql(*(*row(report())[:5], J(scope), 101)) == 0
