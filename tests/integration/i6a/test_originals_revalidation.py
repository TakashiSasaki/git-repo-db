"""ORIGINALS-M1: real initial/replay intake revalidates caller-owned originals.

Every positive uses the explicitly isolated synthetic fixture and its finite
policy. Normal product fence controls restore both exact packaged definitions.
"""

from dataclasses import replace

import pytest

from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import AdmissionRefused, DependencySet
from repo_catalog.domain.p1_context import (
    ProviderEndpointDeclaration,
    ResourceRepositoryRelation,
    TransferEventReport,
)
from repo_catalog.domain.resource_stage import (
    TRANSFER_FENCE_DEFINITIONS,
    UnsupportedResourceStage,
)
from tests.integration.i6a.test_admission import (
    admit,
    assert_no_dependency_reads,
    capture_sql_probe,
)
from tests.integration.i6a.test_admission import (
    boundary as admission_boundary,
)
from tests.integration.p3.test_transfer_admission import KEY_EVENT_7
from tests.support.context_admission import fixture_context


@pytest.fixture
def boundary():
    yield from admission_boundary.__wrapped__()


def rowsets(db):
    """Compare every persistent table, including preexisting immutable rows."""
    names = tuple(
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"
        )
    )
    return {
        name: tuple(sorted(db.execute(f'SELECT * FROM "{name}"'), key=repr))
        for name in names
    }


def malformed(report, mutation):
    # Start with a fully valid report on every attempt. A successful constructor
    # must not be treated as proof about the current nested input at Store intake.
    if mutation.startswith("from-") or mutation.startswith("to-"):
        field, value = mutation.split("-", 1)
        object.__setattr__(
            report.endpoint_declaration,
            f"{field}_endpoint",
            None if value == "missing" else "invalid-original-state",
        )
    elif mutation.startswith("parent-field-"):
        _, _, field, value = mutation.split("-", 3)
        object.__setattr__(
            report.parent_report.report_key,
            f"{field}_json",
            None if value == "missing" else 42,
        )
    elif mutation.startswith("parent-key-"):
        object.__setattr__(
            report.parent_report,
            "report_key",
            None if mutation.endswith("missing") else "not-a-parent-key",
        )
    elif mutation.startswith("parent-"):
        object.__setattr__(
            report,
            "parent_report",
            None if mutation.endswith("missing") else "not-a-parent-original",
        )
    else:
        raise AssertionError(mutation)
    return report


MUTATIONS = (
    "from-missing",
    "from-string",
    "to-missing",
    "to-string",
    "parent-missing",
    "parent-string",
    "parent-key-missing",
    "parent-key-string",
    "parent-field-members-missing",
    "parent-field-members-type",
    "parent-field-provenance-missing",
    "parent-field-provenance-type",
    "parent-field-scope-missing",
    "parent-field-scope-type",
)


@pytest.mark.parametrize("replay", [False, True], ids=["initial", "replay"])
@pytest.mark.parametrize("mutation", MUTATIONS)
def test_malformed_original_refused_before_lookup_or_serialization(
    boundary, mutation, replay
):
    db, store, service, policy, report = boundary
    if replay:
        assert admit(store, service, report) == "insert"
    candidate = malformed(report, mutation)
    before = rowsets(db)
    trace = []
    db.set_trace_callback(trace.append)
    try:
        with pytest.raises(AdmissionRefused) as error:
            admit(store, service, candidate)
    finally:
        db.set_trace_callback(None)
    assert error.value.code == "INCOMPLETE_ORIGINAL_REPORT"
    assert rowsets(db) == before
    assert_no_dependency_reads(trace)
    assert not any(sql.lstrip().upper().startswith("INSERT") for sql in trace)
    assert not db.in_transaction
    assert policy.active == 0
    capture_sql_probe(
        f"originals_{mutation}_{'replay' if replay else 'initial'}",
        refusal_code=error.value.code,
        rowsets_unchanged=True,
        before_rowsets=before,
        after_rowsets=rowsets(db),
        trace=trace,
        transaction_open=db.in_transaction,
        active_leases=policy.active,
    )


def lawful_variant(report, variant):
    if variant == "two-sided":
        return report
    if variant == "one-sided":
        return replace(
            report,
            endpoint_declaration=ProviderEndpointDeclaration(
                "not_reported", report.endpoint_declaration.to_endpoint
            ),
            endpoints=tuple(
                pair for pair in report.endpoints if pair[0].startswith("transfer_to")
            ),
            from_relations=(),
            to_relations=tuple(
                replace(r, event_report_members_json=None, event_report_scope_json=None)
                for r in report.to_relations
            ),
        )
    if variant == "explicit-null":
        role = "transfer_to_repository"
        relation = ResourceRepositoryRelation(
            report.event_resource,
            role,
            report.clock,
            "null",
            report.provenance_json,
            report.observed_at_us,
        )
        return TransferEventReport(
            report.report_key,
            report.parent_report,
            ProviderEndpointDeclaration("not_reported", "explicit_null"),
            ((role, "null"),),
            report.observed_at_us,
            (),
            (relation,),
        )
    if variant == "provider-only":
        return TransferEventReport(
            report.report_key,
            report.parent_report,
            ProviderEndpointDeclaration("not_reported", report.to_provider_repository),
            (),
            report.observed_at_us,
        )
    raise AssertionError(variant)


@pytest.mark.parametrize(
    "variant", ["one-sided", "explicit-null", "two-sided", "provider-only"]
)
def test_lawful_original_semantics_survive_store_and_exact_replay(boundary, variant):
    db, store, service, policy, original = boundary
    report = lawful_variant(original, variant)
    assert admit(store, service, report) == "insert"
    assert store.transfer_event_reports(KEY_EVENT_7) == (report,)
    before = rowsets(db)
    assert admit(store, service, report) == "duplicate"
    assert store.transfer_event_reports(KEY_EVENT_7) == (report,)
    assert rowsets(db) == before
    assert not db.in_transaction
    assert policy.active == 0


@pytest.mark.parametrize(
    "replay", [False, True], ids=["initial-denial", "revoked-replay"]
)
@pytest.mark.parametrize(
    "mutation", ["from-missing", "to-string", "parent-missing", "parent-key-missing"]
)
def test_current_authority_precedes_invalid_original_diagnostics(
    boundary, replay, mutation
):
    db, store, service, policy, report = boundary
    if replay:
        assert admit(store, service, report) == "insert"
    policy.denied = DependencySet(resources={KEY_EVENT_7})
    candidate = malformed(report, mutation)
    before = rowsets(db)
    trace = []
    db.set_trace_callback(trace.append)
    try:
        with pytest.raises(AdmissionRefused) as error:
            admit(store, service, candidate)
    finally:
        db.set_trace_callback(None)
    assert error.value.code == "PERMISSION_DENIED"
    assert_no_dependency_reads(trace)
    assert rowsets(db) == before
    assert not db.in_transaction
    assert policy.active == 0


def test_same_key_changed_original_observation_conflicts_without_row_changes(boundary):
    db, store, service, policy, report = boundary
    assert admit(store, service, report) == "insert"
    changed = replace(
        report,
        parent_report=replace(
            report.parent_report, observed_at_us=report.parent_report.observed_at_us + 1
        ),
    )
    before = rowsets(db)
    with pytest.raises(AdmissionRefused) as error:
        admit(store, service, changed)
    assert error.value.code == "IMMUTABLE_REPLAY_CONFLICT"
    assert rowsets(db) == before
    assert not db.in_transaction
    assert policy.active == 0


@pytest.mark.parametrize(
    "mutation", ["from-missing", "from-string", "to-missing", "to-string"]
)
def test_normal_both_fences_still_refuse_malformed_transfer(boundary, mutation):
    db, store, service, policy, report = boundary
    for _, _, _, sql in TRANSFER_FENCE_DEFINITIONS:
        db.execute(sql)
    before = rowsets(db)
    with pytest.raises(UnsupportedResourceStage) as error:
        admit(store, service, malformed(report, mutation))
    assert error.value.code == "I2_TRANSFER_UNSUPPORTED"
    assert rowsets(db) == before
    assert not db.in_transaction
    assert policy.active == 0


@pytest.mark.parametrize("replay", [False, True], ids=["initial", "replay"])
@pytest.mark.parametrize("mutation", MUTATIONS)
def test_facade_revalidates_originals_before_input_dependency_reads(
    boundary, tmp_path, mutation, replay
):
    db, store, service, policy, report = boundary
    if replay:
        assert admit(store, service, report) == "insert"
    candidate = malformed(report, mutation)
    before = rowsets(db)
    trace = []
    context = fixture_context(service)
    try:
        with pytest.raises(AdmissionRefused) as error:
            with Context.owned_transaction(
                db, tmp_path, authorization=service, admission=context
            ) as facade:
                # Facade creation independently verifies schema and retained
                # registration data. Observe input lookup only after that gate.
                db.set_trace_callback(trace.append)
                facade.admit_transfer_event(candidate, admission=context)
    finally:
        db.set_trace_callback(None)
    assert error.value.code == "INCOMPLETE_ORIGINAL_REPORT"
    assert_no_dependency_reads(trace)
    assert rowsets(db) == before
    assert not db.in_transaction
    assert policy.active == 0


@pytest.mark.parametrize(
    "replay", [False, True], ids=["initial-denial", "revoked-replay"]
)
def test_facade_current_authority_precedes_malformed_original(
    boundary, tmp_path, replay
):
    db, store, service, policy, report = boundary
    if replay:
        assert admit(store, service, report) == "insert"
    policy.denied = DependencySet(resources={KEY_EVENT_7})
    candidate = malformed(report, "from-missing")
    before = rowsets(db)
    trace = []
    context = fixture_context(service)
    try:
        with pytest.raises(AdmissionRefused) as error:
            with Context.owned_transaction(
                db, tmp_path, authorization=service, admission=context
            ) as facade:
                db.set_trace_callback(trace.append)
                facade.admit_transfer_event(candidate, admission=context)
    finally:
        db.set_trace_callback(None)
    assert error.value.code == "PERMISSION_DENIED"
    assert_no_dependency_reads(trace)
    assert rowsets(db) == before
    assert not db.in_transaction
    assert policy.active == 0
