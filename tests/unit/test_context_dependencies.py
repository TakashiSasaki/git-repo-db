"""I6-B pure planner boundaries; selected rows carry no receiver authority."""

import copy
from dataclasses import replace

import pytest

from repo_catalog.domain.context_dependencies import plan_context_dependencies
from repo_catalog.domain.exchange import ExchangeError, ExchangeSelectionScope
from repo_catalog.domain.p1_context import ResourceKey, canonical
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from tests.unit.test_context_wire_v5 import (
    REPOSITORY,
    SERVICE,
    SOURCE,
    collection_row,
    context_with,
    relation_row,
    resolved_transfer_context,
    source_context,
    transfer_context,
)


def selection(**kwargs):
    return ExchangeSelectionScope(all_selected=True, **kwargs)


def cyclic_context():
    a = ResourceKey.global_document(SERVICE, "A")
    b = ResourceKey.from_native(SERVICE, "x-widget", ["B", []])
    data = context_with(RI.global_document(a), RI.unscoped(b))
    data["resource_relations"] = [
        relation_row(a, [b], kind="x-unknown"),
        relation_row(b, [a], kind="links"),
    ]
    return data, a, b


def reasons(plan):
    return {omission.reason for omission in plan.omissions}


def test_T11_cyclic_explicit_member_graph_terminates_and_preserves_whole_reports():
    data, a, b = cyclic_context()
    before = copy.deepcopy(data)
    scope = selection(resource_keys=(a,), max_depth=1)
    first = plan_context_dependencies(data, scope)
    second = plan_context_dependencies(data, scope)
    assert first == second
    assert first.context == data == before
    assert first.selected_resources == frozenset({a, b})
    assert first.context["resource_relations"] == data["resource_relations"]
    assert not first.omissions
    assert first.work_units > first.emitted_units > 0


def test_T02_T11_namespace_coordinates_do_not_expand_selection_or_invent_parent():
    namespace = ResourceKey.from_native(SERVICE, "pull_request", "7")
    child = ResourceKey.document(namespace, "document", "body", "D")
    data = context_with(
        RI.unscoped(namespace), RI.scoped(child, namespace, "body", "D")
    )
    plan = plan_context_dependencies(
        data, selection(resource_keys=(child,), max_depth=8)
    )
    assert plan.selected_resources == frozenset({child})
    assert plan.context["resources"] == [data["resources"][1]]
    assert plan.context["resource_relations"] == []
    assert plan.context["collections"] == []


def test_T11_depth_zero_withholds_unfinished_report_not_member_list():
    data, a, b = cyclic_context()
    plan = plan_context_dependencies(data, selection(resource_keys=(a,), max_depth=0))
    assert plan.selected_resources == frozenset({a})
    assert not plan.context["resource_relations"]
    assert "depth_limit" in reasons(plan)
    assert data["resource_relations"][0]["members_json"] == canonical([b.coordinates()])


@pytest.mark.parametrize("limit", [0, 1, 2, 3])
def test_T11_node_limit_zero_exact_and_above_required_nodes(limit):
    data, a, b = cyclic_context()
    plan = plan_context_dependencies(
        data, selection(resource_keys=(a,)), max_nodes=limit
    )
    assert len(plan.selected_resources) <= limit
    if limit >= 2:
        assert plan.selected_resources == frozenset({a, b})
        assert plan.context == data
    else:
        assert not plan.context["resource_relations"]
        assert "node_limit" in reasons(plan)


@pytest.mark.parametrize("limit", [0, 1, 2, 3])
def test_T11_edge_limit_zero_exact_and_above_required_edges(limit):
    data, a, b = cyclic_context()
    plan = plan_context_dependencies(
        data, selection(resource_keys=(a,)), max_edges=limit
    )
    if limit >= 2:
        assert plan.context == data
    else:
        # Edge budgets apply to whole reports even if target was an explicit seed.
        assert len(plan.context["resource_relations"]) <= limit
        assert "edge_limit" in reasons(plan)


def test_T11_unit_budget_does_not_partially_emit_collection_alternatives():
    data, a, b = cyclic_context()
    data["resource_relations"] = []
    data["collections"] = [
        collection_row(a, [b]),
        collection_row(a, [], state="partial", observed=204),
    ]
    full = plan_context_dependencies(data, selection())
    assert full.context == data
    for bound in (
        0,
        full.emitted_units - 1,
        full.emitted_units,
        full.emitted_units + 1,
    ):
        plan = plan_context_dependencies(data, selection(max_units=bound))
        assert plan.emitted_units <= bound
        assert plan.context["collections"] in ([], data["collections"])
        if bound >= full.emitted_units:
            assert plan.context == data
        else:
            assert not plan.context["collections"]


def test_T11_byte_budget_exact_plus_one_and_short_preserve_complete_units():
    data, _, _ = cyclic_context()
    full = plan_context_dependencies(data, selection())
    for bound in (
        0,
        full.emitted_payload_bytes - 1,
        full.emitted_payload_bytes,
        full.emitted_payload_bytes + 1,
    ):
        plan = plan_context_dependencies(data, selection(max_bytes=bound))
        assert plan.emitted_payload_bytes <= bound
        for row in plan.context["resource_relations"]:
            assert row in data["resource_relations"]
        if bound >= full.emitted_payload_bytes:
            assert plan.context == data
        else:
            assert plan.context != data
            assert "byte_limit" in reasons(plan)


def test_T11_work_budget_counts_replay_and_prior_work_without_refund():
    data, _, _ = cyclic_context()
    full = plan_context_dependencies(data, selection())
    exact = plan_context_dependencies(data, selection(max_work=full.work_units))
    assert exact.context == data
    assert exact.work_units == full.work_units
    assert (
        plan_context_dependencies(data, selection(max_work=full.work_units + 1)).context
        == data
    )
    exhausted = plan_context_dependencies(data, selection(max_work=0))
    assert not any(exhausted.context.values())
    assert exhausted.work_units > 0
    assert reasons(exhausted) == {"work_limit"}
    replay = plan_context_dependencies(data, selection(), prior_work=full.work_units)
    assert replay.context == data
    assert replay.work_units == 2 * full.work_units
    retried = plan_context_dependencies(
        data, selection(max_work=full.work_units), prior_work=full.work_units
    )
    assert not any(retried.context.values())
    assert retried.work_units > full.work_units


@pytest.mark.parametrize("argument", ["prior_work", "max_nodes", "max_edges"])
@pytest.mark.parametrize("value", [True, -1, 1.0, "1", 100000001])
def test_T11_settings_require_finite_strict_nonnegative_integers(argument, value):
    data, _, _ = cyclic_context()
    with pytest.raises(ExchangeError) as error:
        plan_context_dependencies(data, selection(), **{argument: value})
    assert error.value.code == "INVALID_SELECTION"


def test_T12_T13_terminal_coverage_is_withheld_with_missing_selected_repository():
    data = source_context()
    full = plan_context_dependencies(data, selection())
    assert full.context == data
    reduced = plan_context_dependencies(
        data, selection(repository_uuidv4s=(REPOSITORY,))
    )
    assert reduced.context["source_inventories"] == []
    assert reduced.context["coverage_claims"] == []
    assert reduced.context["coverage_proofs"] == []
    assert len(reduced.context["source_repositories"]) == 1
    assert reduced.context["source_repositories"][0]["repository_uuidv4"] == REPOSITORY
    assert data["coverage_claims"][0]["coverage_state"] == "complete"


def test_T12_terminal_alternative_and_coverage_are_atomic():
    data = source_context()
    original = data["source_inventories"][0]
    data["source_inventories"].append(
        {
            **original,
            "coverage_state": "partial",
            "terminal": False,
            "members_json": canonical([REPOSITORY]),
        }
    )
    full = plan_context_dependencies(data, selection())
    assert full.context == data
    for bound in (full.emitted_units - 1, full.emitted_units):
        reduced = plan_context_dependencies(data, selection(max_units=bound))
        if reduced.context["source_inventories"]:
            assert reduced.context["source_inventories"] == data["source_inventories"]
            assert reduced.context["coverage_claims"] == data["coverage_claims"]
            assert reduced.context["coverage_proofs"] == data["coverage_proofs"]
        else:
            assert not reduced.context["coverage_claims"]
            assert not reduced.context["coverage_proofs"]


def test_T13_partial_inventory_keeps_both_independent_positive_associations():
    data = source_context(partial=True, terminal=False)
    plan = plan_context_dependencies(data, selection())
    assert plan.context == data
    assert len(plan.context["source_repositories"]) == 2
    assert plan.context["coverage_claims"] == []


def test_T13_source_inventory_requires_actual_known_positive_association():
    data = source_context(partial=True)
    data["source_repositories"] = []
    plan = plan_context_dependencies(data, selection())
    assert not plan.context["source_inventories"]
    assert "missing_dependency" in reasons(plan)


def test_T13_source_registration_selects_no_provider_resources():
    data, a, _ = cyclic_context()
    sources = source_context(partial=True)
    for section in (
        "repositories",
        "sources",
        "source_repositories",
        "source_inventories",
    ):
        data[section] = sources[section]
    plan = plan_context_dependencies(
        data, selection(resource_keys=(), source_uuidv4s=(SOURCE,))
    )
    assert plan.context["resources"] == []
    assert plan.context["resource_relations"] == []
    assert plan.context["source_inventories"] == sources["source_inventories"]
    assert a not in plan.selected_resources


def test_T13_unselected_source_cannot_rescue_collection_or_inventory():
    data = source_context()
    plan = plan_context_dependencies(data, selection(source_uuidv4s=()))
    assert not plan.context["sources"]
    assert not plan.context["source_repositories"]
    assert not plan.context["source_inventories"]
    assert not plan.context["coverage_claims"]
    assert "source_not_selected" in reasons(plan)


def test_T05_T06_T11_transfer_is_whole_event_endpoint_unit_with_original_parent():
    data = transfer_context(two_sided=True)
    full = plan_context_dependencies(data, selection())
    assert full.context == data
    for budget in range(full.emitted_units + 1):
        plan = plan_context_dependencies(data, selection(max_units=budget))
        event_rows = [
            r
            for r in plan.context["resource_relations"]
            if r["relation_kind"] == "transfer_event_report"
        ]
        endpoints = plan.context["resource_repository_relations"]
        assert bool(event_rows) == bool(endpoints)
        if event_rows:
            assert len(endpoints) == 2
            assert event_rows == [data["resource_relations"][1]]
            assert data["resource_relations"][0] in plan.context["resource_relations"]


def test_T06_V07_missing_mapping_claim_withholds_whole_transfer_keeps_resources():
    data = resolved_transfer_context()
    data["resource_repository_relations"].pop(0)
    plan = plan_context_dependencies(data, selection())
    assert len(plan.context["resources"]) == len(data["resources"])
    assert not plan.context["resource_repository_relations"]
    assert [r["relation_kind"] for r in plan.context["resource_relations"]] == [
        "parent"
    ]
    assert "missing_dependency" in reasons(plan)


def test_T11_missing_member_withholds_complete_report_without_truncation():
    data, a, b = cyclic_context()
    data["resources"].pop(1)
    plan = plan_context_dependencies(data, selection())
    assert plan.selected_resources == frozenset({a})
    assert plan.context["resource_relations"] == []
    assert data["resource_relations"][0]["members_json"] == canonical([b.coordinates()])
    assert "missing_dependency" in reasons(plan)


def test_T11_no_context_selection_does_not_mutate_original_or_grant_authority():
    data, _, _ = cyclic_context()
    before = copy.deepcopy(data)
    scope = replace(selection(), include_context=False)
    plan = plan_context_dependencies(data, scope)
    assert not any(plan.context.values())
    assert data == before
    assert reasons(plan) == {"section_not_selected"}
    assert not hasattr(plan, "admission")


def scoped_source_collection():
    data, a, b = cyclic_context()
    source = source_context(partial=True)
    for section in ("repositories", "sources", "source_repositories"):
        data[section] = source[section]
    data["resource_relations"] = []
    data["collections"] = [
        collection_row(
            a,
            [b],
            scope=canonical(
                {"source_registration_uuidv4": SOURCE, "repository_uuidv4": REPOSITORY}
            ),
        )
    ]
    return data


@pytest.mark.parametrize("missing", ["source", "positive-pair"])
def test_T13_explicit_collection_source_and_repository_need_actual_positive_pair(
    missing,
):
    data = scoped_source_collection()
    assert plan_context_dependencies(data, selection()).context == data
    data["sources" if missing == "source" else "source_repositories"] = []
    plan = plan_context_dependencies(data, selection())
    assert not plan.context["collections"]
    assert len(plan.context["resources"]) == 2
    assert "missing_dependency" in reasons(plan)


@pytest.mark.parametrize("location", ["scope_json", "provenance_json"])
def test_T13_explicit_source_in_original_evidence_is_selection_dependency(location):
    data = scoped_source_collection()
    if location == "provenance_json":
        data["collections"][0]["scope_json"] = "{}"
        data["collections"][0]["provenance_json"] = canonical(
            {"source": "fixture", "evidence": {"source_registration_uuidv4": SOURCE}}
        )
    plan = plan_context_dependencies(data, selection(source_uuidv4s=()))
    assert not plan.context["collections"]
    assert len(plan.context["resources"]) == 2
    assert "source_not_selected" in reasons(plan)


def test_T13_attributed_source_text_does_not_create_source_registration_dependency():
    data, _, _ = cyclic_context()
    assert data["sources"] == []
    assert plan_context_dependencies(data, selection()).context == data


def test_T09_explicit_empty_dimensions_emit_no_unrelated_provider_registration():
    data, _, _ = cyclic_context()
    plan = plan_context_dependencies(
        data, selection(resource_keys=(), source_uuidv4s=(), repository_uuidv4s=())
    )
    assert not any(plan.context.values())
    assert not plan.selected_resources


def test_T11_unreferenced_text_body_is_not_selected_by_resource_seed():
    import hashlib

    data, a, _ = cyclic_context()
    text = "orphan Context text"
    data["text_bodies"] = [
        {"sha256": hashlib.sha256(text.encode()).hexdigest(), "text_value": text}
    ]
    plan = plan_context_dependencies(data, selection(resource_keys=(a,)))
    assert not plan.context["text_bodies"]
    assert len(plan.context["resources"]) == 2
    assert data["text_bodies"][0]["text_value"] == text


def test_T11_planner_stops_charging_after_first_exhausted_work_operation():
    from repo_catalog.domain.exchange import _bounded_json

    data, _, _ = cyclic_context()
    scanned, _ = _bounded_json(data, root="context")
    budget = scanned + 1
    plan = plan_context_dependencies(data, selection(max_work=budget))
    assert plan.work_units <= budget + 1
    assert not plan.context["resource_relations"]
    assert "work_limit" in reasons(plan)


def test_T11_late_work_stop_preserves_completed_independent_units_only():
    data, a, b = cyclic_context()
    full = plan_context_dependencies(data, selection())
    budget = full.work_units - 1
    plan = plan_context_dependencies(data, selection(max_work=budget))
    assert plan.work_units <= budget + 1
    assert plan.selected_resources == frozenset({a, b})
    assert plan.context["providers"] == data["providers"]
    assert len(plan.context["resource_relations"]) < len(data["resource_relations"])
    assert all(
        row in data["resource_relations"] for row in plan.context["resource_relations"]
    )
    assert "work_limit" in reasons(plan)


def collection_owned_coverage_context():
    from repo_catalog.domain.p1_context import CoverageScope

    data, owner, child = cyclic_context()
    data["resource_relations"] = []
    terminal = collection_row(owner, [child])
    data["collections"] = [terminal]
    scope = CoverageScope.collection(
        owner, "related", terminal["provenance_json"], "related"
    )
    scope_row = {
        "owner_kind": scope.owner_kind,
        "owner_coordinates_json": scope.encoded,
    }
    data["coverage_scopes"] = [scope_row]
    data["coverage_claims"] = [
        {
            **scope_row,
            "observed_at_us": 204,
            "coverage_state": "complete",
            "details_json": None,
        }
    ]
    data["coverage_proofs"] = [
        {
            **scope_row,
            **{
                key: terminal[key]
                for key in (
                    "service_instance_uuidv4",
                    "resource_kind",
                    "provider_resource_id",
                    "collection_kind",
                    "provenance_json",
                    "members_json",
                )
            },
            "observed_at_us": 204,
            "coverage_state": "complete",
            "proof_kind": "collection",
            "terminal_observed_at_us": terminal["observed_at_us"],
            "terminal_state": terminal["terminal_state"],
        }
    ]
    return data, owner, child


def test_T12_actual_collection_scope_and_terminal_dependencies_preserve_positive_cycle():
    from repo_catalog.domain.context_wire import decode_context_v5

    data, _, _ = collection_owned_coverage_context()
    assert decode_context_v5(data) == data
    plan = plan_context_dependencies(data, selection())
    assert plan.context == data
    assert not plan.omissions


def test_T12_withheld_collection_header_withholds_owned_scope_claim_and_proof():
    data, owner, child = collection_owned_coverage_context()
    plan = plan_context_dependencies(
        data, selection(resource_keys=(owner,), max_depth=0)
    )
    assert plan.selected_resources == frozenset({owner})
    assert child not in plan.selected_resources
    assert plan.context["collections"] == []
    assert plan.context["coverage_scopes"] == []
    assert plan.context["coverage_claims"] == []
    assert plan.context["coverage_proofs"] == []


def test_T12_missing_actual_scope_withholds_claim_and_proof_without_synthesizing_scope():
    data, owner, child = collection_owned_coverage_context()
    data["coverage_scopes"] = []
    plan = plan_context_dependencies(data, selection())
    assert plan.selected_resources == frozenset({owner, child})
    assert plan.context["coverage_scopes"] == []
    assert plan.context["coverage_claims"] == []
    assert plan.context["coverage_proofs"] == []
    assert "missing_dependency" in reasons(plan)


def test_T12_collection_owned_scope_needs_exact_actual_header_not_only_resource():
    data, owner, child = collection_owned_coverage_context()
    data["collections"] = []
    data["coverage_claims"] = []
    data["coverage_proofs"] = []
    plan = plan_context_dependencies(data, selection())
    assert plan.selected_resources == frozenset({owner, child})
    assert plan.context["coverage_scopes"] == []
    assert "missing_dependency" in reasons(plan)


@pytest.mark.parametrize("scope_json", ["[]", "null", "true", "1", '"opaque"'])
def test_T12_collection_proof_requires_typed_scope_object(scope_json):
    from repo_catalog.domain.context_wire import decode_context_v5

    data, _, _ = collection_owned_coverage_context()
    data["collections"][0]["scope_json"] = scope_json
    with pytest.raises(ExchangeError) as refusal:
        decode_context_v5(data)
    assert refusal.value.code == "INVALID_COVERAGE_PROOF"


@pytest.mark.parametrize("scope_json", ["[]", "null", "true", "1", '"opaque"'])
def test_T12_generic_collection_scope_without_proof_is_preserved(scope_json):
    from repo_catalog.domain.context_wire import decode_context_v5

    data, _, _ = collection_owned_coverage_context()
    data["collections"][0]["scope_json"] = scope_json
    for section in ("coverage_scopes", "coverage_claims", "coverage_proofs"):
        data[section] = []
    assert decode_context_v5(data) == data
