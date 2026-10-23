"""R04 reservations precede scanner parsing and allocation, including retries."""

from unittest.mock import patch

import pytest

from repo_catalog.domain import context_dependencies, exchange
from repo_catalog.domain.context_dependencies import plan_context_dependencies
from repo_catalog.domain.exchange import (
    ExchangeError,
    ExchangeSelectionScope,
    _bounded_json,
)
from tests.unit.test_context_dependencies import cyclic_context


def scope(**kwargs):
    return ExchangeSelectionScope(all_selected=True, **kwargs)


@pytest.mark.parametrize("budget,prior", [(0, 0), (1, 0), (17, 0), (17, 17), (17, 23)])
def test_exhausted_request_does_not_parse_or_escape_input(budget, prior):
    data, _, _ = cyclic_context()
    # A large irrelevant, already materialized suffix must not be touched merely
    # to return the same refusal. Full codec validation is a separate boundary.
    data["resource_relations"] *= 1000
    with (
        patch.object(exchange, "_parse_json", wraps=exchange._parse_json) as parse,
        patch.object(
            exchange, "parse_identity", wraps=exchange.parse_identity
        ) as identity,
        patch.object(exchange, "_quoted_size", wraps=exchange._quoted_size) as quote,
    ):
        result = plan_context_dependencies(
            data, scope(max_work=budget), prior_work=prior
        )
    assert prior < result.work_units <= max(budget, prior) + 1
    if prior >= budget:
        assert result.work_units == prior + 1
    assert not any(result.context.values())
    assert {item.reason for item in result.omissions} == {"work_limit"}
    assert parse.call_count == identity.call_count == quote.call_count == 0
    print(
        {
            "budget": budget,
            "prior": prior,
            "charged": result.work_units,
            "embedded_parses": parse.call_count,
            "identity_parses": identity.call_count,
            "quoted_strings": quote.call_count,
        }
    )


def test_scanner_exact_work_and_next_operation_are_separate_boundaries():
    data, _, _ = cyclic_context()
    reservations = []
    plain = _bounded_json(data, root="context")
    assert _bounded_json(data, root="context", spend=reservations.append) == plain
    scanned_work = sum(reservations)
    assert scanned_work > plain[0]
    for budget in (scanned_work - 1, scanned_work, scanned_work + 1):
        result = plan_context_dependencies(data, scope(max_work=budget))
        assert result.work_units <= budget + 1
        assert not any(result.context.values())
        assert {item.reason for item in result.omissions} == {"work_limit"}
    full = plan_context_dependencies(data, scope())
    for budget in (full.work_units, full.work_units + 1):
        result = plan_context_dependencies(data, scope(max_work=budget))
        assert result.context == data
        assert result.work_units == full.work_units
    print(
        {
            "elements": plain[0],
            "scanner_work": scanned_work,
            "full_work": full.work_units,
        }
    )


def test_embedded_parser_reserves_whole_text_before_first_parse():
    data, _, _ = cyclic_context()
    # Unrelated small reports can precede this value in the iterative scan.
    data["providers"][0]["configuration_json"] = '"' + "x" * 100_000 + '"'
    with patch.object(exchange, "_parse_json", wraps=exchange._parse_json) as parse:
        result = plan_context_dependencies(data, scope(max_work=10_000))
    assert not any(result.context.values())
    assert result.work_units <= 10_001
    assert all(len(call.args[0]) < 100_000 for call in parse.call_args_list)
    assert sum(len(call.args[0]) for call in parse.call_args_list) <= 10_000


@pytest.mark.parametrize(
    "kind,code",
    [("cycle", "MALFORMED_JSON"), ("depth", "INPUT_LIMIT"), ("bytes", "INPUT_LIMIT")],
)
def test_scanner_hard_bounds_still_refuse_with_adequate_work(monkeypatch, kind, code):
    data, _, _ = cyclic_context()
    if kind == "cycle":
        data["resources"].append(data)
    elif kind == "depth":
        nested = []
        for _ in range(exchange.MAX_DEPTH + 1):
            nested = [nested]
        data["resources"].append(nested)
    else:
        monkeypatch.setattr(exchange, "MAX_PACKAGE_BYTES", 2048)
        data["providers"][0]["configuration_json"] = '"' + "x" * 2048 + '"'
    with pytest.raises(ExchangeError) as error:
        plan_context_dependencies(data, scope(max_work=100_000_000, max_bytes=2048))
    assert error.value.code == code
    # If already exhausted, no malformed suffix inspection runs at all.
    result = plan_context_dependencies(data, scope(max_work=0, max_bytes=2048))
    assert result.work_units == 1
    assert not any(result.context.values())


@pytest.mark.parametrize("levels", [31, 32, 33])
def test_scanner_depth_inclusive_boundary_with_work_reservations(levels):
    value = 0
    for _ in range(levels):
        value = [value]
    reserved = []
    if levels <= exchange.MAX_DEPTH:
        elements, _ = _bounded_json(value, spend=reserved.append)
        assert elements == levels + 1
    else:
        with pytest.raises(ExchangeError) as error:
            _bounded_json(value, spend=reserved.append)
        assert error.value.code == "INPUT_LIMIT"
    assert sum(reserved) <= 3 * levels + 1


def test_scanner_escaped_byte_cap_exact_and_one_short(monkeypatch):
    value = {"embedded_json": '"\\u00e9"', "plain": 'é\\"'}
    measured = []
    expected = _bounded_json(value, spend=measured.append)
    for bound in (expected[1], expected[1] + 1):
        monkeypatch.setattr(exchange, "MAX_PACKAGE_BYTES", bound)
        charges = []
        assert _bounded_json(value, spend=charges.append) == expected
        assert charges == measured
    monkeypatch.setattr(exchange, "MAX_PACKAGE_BYTES", expected[1] - 1)
    with pytest.raises(ExchangeError) as error:
        _bounded_json(value, spend=lambda amount: None)
    assert error.value.code == "INPUT_LIMIT"


def test_zero_budget_preserves_fixed_envelope_hard_cap_before_row_indexing():
    data, _, _ = cyclic_context()
    data["resources"] = [None] * exchange.MAX_ELEMENTS
    with patch.object(exchange, "_parse_json") as parse:
        with pytest.raises(ExchangeError) as error:
            plan_context_dependencies(data, scope(max_work=0))
    assert error.value.code == "INPUT_LIMIT"
    assert parse.call_count == 0


def test_oversize_root_refuses_without_building_unbounded_key_sets():
    # Input is already materialized by the caller. Observe the actual key-set
    # allocation boundary separately from embedded parsing/output counters.
    data = {str(index): [] for index in range(20_000)}
    with patch.object(context_dependencies, "set", wraps=set, create=True) as sets:
        with pytest.raises(ExchangeError) as error:
            plan_context_dependencies(data, scope(max_work=0))
    assert error.value.code == "MALFORMED_SECTION"
    assert not any(call.args and call.args[0] is data for call in sets.call_args_list)
