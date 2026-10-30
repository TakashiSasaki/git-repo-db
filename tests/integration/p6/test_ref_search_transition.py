"""Claim-specific Search identity, reports and checked copy eligibility."""

import json
from dataclasses import replace

import pytest

from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.application.production_query import ProductionQueryService
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.production_query import SearchQuery
from tests.integration.p4 import conftest as fixtures
from tests.integration.p5.test_ref_inventory_wiring import enable_context, run_request
from tests.integration.p5.test_ref_notes_inputs import original_input, with_input
from tests.integration.p6.test_corrections import _mutate

acquisition = fixtures.acquisition


def two_claims(case):
    value, target, _ = original_input(case, body=b"needle-only-one-claim")
    value = replace(
        value,
        mapping_groups=(
            replace(value.mapping_groups[0], interpretation_scope="native-notes-tree"),
        ),
    )
    other = replace(
        value.claims[0],
        provenance=replace(value.claims[0].provenance, coordinate="second"),
    )
    group = replace(value.mapping_groups[0], ref_claim=other, status="partial")
    value = replace(
        value,
        claims=(*value.claims, other),
        mapping_claims=(),
        mapping_groups=(*value.mapping_groups, group),
    )
    return value, target


@pytest.mark.parametrize("paired", [False, True])
def test_group_only_reports_keys_body_and_fallback(acquisition, paired):
    app, _, _, _, _, path, _ = acquisition
    value, target = two_claims(acquisition)
    if paired:
        enable_context(acquisition)
    run_request(acquisition, with_input(acquisition, value), paired=paired)
    service = ProductionQueryService(path.parent)
    query = SearchQuery(query_text=target.full_oid, projection_kinds=("notes",))
    report_only = service.search(query)
    assert report_only.total_count == 2
    assert len({hit.document_key for hit in report_only.hits}) == 2
    assert all(
        not hit.authoritative_summary["note_retained"] for hit in report_only.hits
    )
    assert not app.core.sql("SELECT 1 FROM captures")
    assert not app.core.sql("SELECT 1 FROM notes_mappings")
    # Acquire only the first Claim's body using the existing root-bound reader.
    first = replace(
        value, claims=(value.claims[0],), mapping_groups=(value.mapping_groups[0],)
    )
    run_request(
        acquisition,
        with_input(acquisition, first, target_oids=(target,)),
        paired=paired,
    )
    work = UnlimitedWorkBudget()
    body_query = SearchQuery(
        query_text="needle-only-one-claim", projection_kinds=("notes",)
    )
    authority = service.search(body_query, work=work)
    assert authority.total_count == 1
    assert (
        authority.hits[0].authoritative_summary["claim"]["provenance"]["coordinate"]
        == value.claims[0].provenance.coordinate
    )
    before = dict(work.usage)
    service.rebuild_search(("notes",), work=work)
    indexed = service.search(body_query, work=work)
    assert indexed.hits == authority.hits
    assert indexed.backend == "verified_projection_scan"
    assert work.usage["verification_bytes"] > before["verification_bytes"]
    all_reports = service.search(query)
    assert all_reports.total_count == 2
    assert (
        sum(hit.authoritative_summary["note_retained"] for hit in all_reports.hits) == 1
    )
    assert {
        hit.authoritative_summary["inventory_coverage"] for hit in all_reports.hits
    } == {"unknown"}
    assert any(
        source[-1] == "partial"
        for hit in all_reports.hits
        for source in hit.authoritative_summary["sources"]
        if source[0] == "group"
    )
    (path.parent / "search.sqlite3").write_bytes(b"broken derivative")
    fallback = service.search(body_query)
    assert fallback.backend == "authority_scan" and fallback.hits == indexed.hits
    assert not (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("action", ["search", "rebuild"])
@pytest.mark.parametrize("paired", [False, True])
def test_caller_callback_is_not_stored_corruption(acquisition, action, paired):
    _, _, _, _, _, path, _ = acquisition
    value, _ = two_claims(acquisition)
    if paired:
        enable_context(acquisition)
    run_request(acquisition, with_input(acquisition, value), paired=paired)
    marker = json.JSONDecodeError("caller", "", 0)

    class Broken(UnlimitedWorkBudget):
        def require(self, unit, amount=1):
            if action == "search":
                raise marker
            return super().require(unit, amount)

        def charge(self, unit, amount):
            if action == "rebuild":
                raise marker
            return super().charge(unit, amount)

    service = ProductionQueryService(path.parent)
    with pytest.raises(json.JSONDecodeError) as error:
        if action == "search":
            service.search(
                SearchQuery(query_text="needle", projection_kinds=("notes",)),
                work=Broken(),
            )
        else:
            service.rebuild_search(("notes",), work=Broken())
    assert error.value is marker
    assert not (path.parent / "p1-recovery-stop.json").exists()


def test_bad_eligible_copy_stops_before_search_output(acquisition):
    _, _, _, _, _, path, _ = acquisition
    value, target = two_claims(acquisition)
    first = replace(
        value, claims=(value.claims[0],), mapping_groups=(value.mapping_groups[0],)
    )
    run_request(acquisition, with_input(acquisition, first, target_oids=(target,)))
    _mutate(path, "ref_retained_notes", "body=zeroblob(length(body))")
    with pytest.raises(CoreFailure) as error:
        ProductionQueryService(path.parent).search(
            SearchQuery(query_text="needle", projection_kinds=("notes",))
        )
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()


def test_later_partial_coverage_does_not_reuse_old_complete(acquisition):
    app, _, _, _, _, path, _ = acquisition
    value, target = two_claims(acquisition)
    first = replace(
        value, claims=(value.claims[0],), mapping_groups=(value.mapping_groups[0],)
    )
    result = run_request(
        acquisition,
        with_input(acquisition, first, target_oids=(target,), acquire_inventories=True),
    )
    original = result.ref_inventory_verifications[0].coverage_claim
    from repo_catalog.domain.p1_coverage import CoverageClaim

    app.core.admit_coverage(
        CoverageClaim(original.scope, original.observed_at_us + 1, "partial")
    )
    service = ProductionQueryService(path.parent)
    response = service.search(
        SearchQuery(query_text="needle-only-one-claim", projection_kinds=("notes",))
    )
    assert response.total_count == 1
    summary = response.hits[0].authoritative_summary
    assert summary["inventory_coverage"] == "partial"
    assert summary["note_retained"]
    assert any(s[0] == "group" and s[-1] == "complete" for s in summary["sources"])
    budget = UnlimitedWorkBudget(work_limits={"input_bytes": 1})
    for _ in range(2):
        with pytest.raises(CoreFailure) as error:
            service.search(
                SearchQuery(query_text="needle", projection_kinds=("notes",)),
                work=budget,
            )
        assert error.value.code == "BUDGET"
    assert not (path.parent / "p1-recovery-stop.json").exists()
