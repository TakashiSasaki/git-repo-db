"""Current authority/selection precede permanent semantics, then dependencies."""

from dataclasses import replace

import pytest

from repo_catalog.domain.context_admission import (
    AdmissionRefused,
    AdmissionSelection,
    DependencySet,
)
from repo_catalog.domain.p1_context import canonical
from repo_catalog.domain.parent_report import ParentObservation, ParentReportKey
from tests.integration.i6a.test_admission import admit
from tests.integration.i6a.test_admission import boundary as boundary_fixture
from tests.integration.p3.test_transfer_admission import KEY_ISSUE_8
from tests.support.context_admission import fixture_context

MISSING_SOURCE = "6aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


@pytest.fixture
def priority_boundary():
    yield from boundary_fixture.__wrapped__()


@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize("outcome", ["denied", "omitted", "authorized"])
def test_t07_refusal_order_does_not_look_up_missing_source_before_qs10(
    priority_boundary, replay, outcome
):
    db, store, service, policy, report = priority_boundary
    if replay:
        assert admit(store, service, report) == "insert"
    policy.grants |= DependencySet(resources={KEY_ISSUE_8}, sources={MISSING_SOURCE})
    wrong_parent = ParentReportKey(
        report.event_resource,
        canonical([KEY_ISSUE_8.coordinates()]),
        canonical(
            {
                "source": "parent-original",
                "evidence": {
                    "source_registration_uuidv4": MISSING_SOURCE,
                },
            }
        ),
        report.parent_scope_json,
    )

    def original_relation(relation):
        return replace(
            relation, event_report_members_json=None, event_report_scope_json=None
        )

    candidate = replace(
        report,
        parent_report=ParentObservation(wrong_parent, 51),
        from_relations=tuple(original_relation(r) for r in report.from_relations),
        to_relations=tuple(original_relation(r) for r in report.to_relations),
    )
    selection = None
    if outcome == "denied":
        policy.denied = DependencySet(sources={MISSING_SOURCE})
        expected = "PERMISSION_DENIED"
    elif outcome == "omitted":
        selection = AdmissionSelection(
            all_selected=True, resource_keys=policy.grants.resources - {KEY_ISSUE_8}
        )
        expected = "OMITTED_BY_SELECTION"
    else:
        expected = "QS10_PARENT_INELIGIBLE"
    context = fixture_context(service, selection=selection)
    before = tuple(db.execute("SELECT * FROM resource_relations"))
    trace = []
    db.set_trace_callback(trace.append)
    try:
        with pytest.raises(AdmissionRefused) as error:
            with store.transaction(admission=context):
                store.admit_transfer_event(candidate, admission=context)
        assert error.value.code == expected
    finally:
        db.set_trace_callback(None)
    assert not any("FROM sources" in sql for sql in trace)
    assert tuple(db.execute("SELECT * FROM resource_relations")) == before
