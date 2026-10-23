"""R08–R15 boundaries using actual store transactions and SQL failures.

The inherited 29 I5 nodes retain their IDs and purposes in p3. Their two
positive parametrizations now use explicit fresh-memory harnesses, as normal
product database opening must keep both Transfer fences intact.
"""

import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionContext,
    AdmissionRefused,
    AdmissionSelection,
    DependencySet,
    dependencies,
)
from repo_catalog.domain.p1_context import canonical
from repo_catalog.domain.parent_report import ParentObservation
from repo_catalog.domain.resource_identification import ResourceIdentification
from tests.integration.p3.test_transfer_admission import (
    KEY_EVENT_7,
    KEY_ISSUE_7,
    KEY_PROV_REPO_1,
    KEY_PROV_REPO_2,
    REPO_1,
    REPO_2,
    SERVICE,
    _event_provenance,
    _make_mapping_support,
    _setup_base_records,
    fixture_grants,
    make_parent_report,
    make_transfer_report,
)
from tests.support.context_admission import fixture_context, fixture_service
from tests.support.i6a import isolated_context_db

SOURCE = "35555555-5555-4555-8555-555555555555"
FROM_CLAIM = _make_mapping_support(KEY_PROV_REPO_1, REPO_1).supporting_claims[0]
TO_CLAIM = _make_mapping_support(KEY_PROV_REPO_2, REPO_2).supporting_claims[0]
DENIALS = [
    ("resources", KEY_EVENT_7),
    ("resources", KEY_ISSUE_7),
    ("resources", KEY_PROV_REPO_1),
    ("resources", KEY_PROV_REPO_2),
    ("repositories", REPO_1),
    ("repositories", REPO_2),
    ("sources", SOURCE),
    ("source_repository_pairs", (SOURCE, REPO_1)),
    ("source_repository_pairs", (SOURCE, REPO_2)),
    ("mapping_claims", FROM_CLAIM),
    ("mapping_claims", TO_CLAIM),
]


def capture_sql_probe(name, **observations):
    """Opt-in synthetic raw evidence; ordinary pytest never creates artifacts."""
    target = os.environ.get("I6A_SQL_PROBE_OUTPUT")
    if target is None:
        return
    path = Path(target)
    result = json.loads(path.read_text()) if path.exists() else {}
    result[name] = observations
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


@pytest.fixture
def boundary():
    with isolated_context_db() as db:
        _setup_base_records(db)
        db.execute("INSERT INTO sources VALUES(?,?,?)", (SOURCE, SERVICE, "{}"))
        for repository in (REPO_1, REPO_2):
            db.execute(
                "INSERT INTO source_repositories VALUES(?,?,?)",
                (SOURCE, repository, "{}"),
            )
        grants = fixture_grants() | DependencySet(
            sources={SOURCE},
            source_repository_pairs={(SOURCE, REPO_1), (SOURCE, REPO_2)},
        )
        service, policy = fixture_service(grants)
        report = make_transfer_report(
            provenance=_event_provenance(
                evidence={"source_registration_uuidv4": SOURCE, "original": ["e", 2]}
            )
        )
        store = ContextStore(db, authorization=service)
        yield db, store, service, policy, report


def admit(store, service, report, *, context=None):
    context = context or fixture_context(service)
    with store.transaction(admission=context):
        return store.admit_transfer_event(report, admission=context)


def counts(db):
    return (
        db.execute(
            "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'"
        ).fetchone()[0],
        db.execute(
            "SELECT count(*) FROM resource_repository_relations WHERE relation_kind IN ('transfer_from_repository','transfer_to_repository')"
        ).fetchone()[0],
    )


def assert_no_dependency_reads(trace):
    """Schema/fence inspection is allowed; denied content lookup is not."""
    for sql in trace:
        normalized = " ".join(sql.lower().split())
        if not normalized.startswith("select"):
            continue
        for table in (
            "resources",
            "resource_relations",
            "resource_repository_relations",
            "repository_context",
            "sources",
        ):
            assert f"from {table}" not in normalized, sql


@pytest.mark.parametrize("replay", [False, True], ids=["initial", "replay"])
@pytest.mark.parametrize("dimension,key", DENIALS)
def test_deny_each_dependency_before_initial_or_replay_lookup(
    boundary, replay, dimension, key
):
    db, store, service, policy, report = boundary
    if replay:
        assert admit(store, service, report) == "insert"
    before = counts(db)
    policy.denied = DependencySet(**{dimension: {key}})
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(AdmissionRefused) as error:
        admit(store, service, report)
    db.set_trace_callback(None)
    assert error.value.code == "PERMISSION_DENIED"
    assert counts(db) == before
    assert not db.in_transaction
    # Pair discovery needs authorized Source/target lookups. All pure dependency
    # denials must occur before the first content lookup.
    if dimension != "source_repository_pairs":
        assert_no_dependency_reads(trace)


@pytest.mark.parametrize("replay", [False, True], ids=["initial", "replay"])
@pytest.mark.parametrize("dimension,key", DENIALS[:7])
def test_selection_checks_every_resource_repository_and_source(
    boundary, replay, dimension, key
):
    db, store, service, policy, report = boundary
    if replay:
        assert admit(store, service, report) == "insert"
    before = counts(db)
    deps = dependencies(report)
    selected = {
        "resource_keys": deps.resources,
        "repository_uuidv4s": deps.repositories,
        "source_uuidv4s": deps.sources,
        "object_oids": frozenset(),
    }
    selected_name = {
        "resources": "resource_keys",
        "repositories": "repository_uuidv4s",
        "sources": "source_uuidv4s",
    }[dimension]
    selected[selected_name] -= {key}
    context = fixture_context(service, selection=AdmissionSelection(**selected))
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(AdmissionRefused) as error:
        admit(store, service, report, context=context)
    db.set_trace_callback(None)
    assert error.value.code == "OMITTED_BY_SELECTION"
    assert counts(db) == before
    assert policy.calls
    assert_no_dependency_reads(trace)


@pytest.mark.parametrize("replay", [False, True], ids=["initial", "replay"])
@pytest.mark.parametrize(
    "forgery", ["foreign-service", "forged-principal", "mutated-principal"]
)
def test_service_handle_and_principal_substitution_never_authorize(
    boundary, replay, forgery
):
    db, store, service, policy, report = boundary
    if replay:
        assert admit(store, service, report) == "insert"
    foreign, foreign_policy = fixture_service(policy.grants)
    context = fixture_context(service)
    if forgery == "foreign-service":
        context = fixture_context(foreign)
    elif forgery == "forged-principal":
        context = AdmissionContext(
            "administrator", context.operation, context.selection, context.budget
        )
    else:
        object.__setattr__(context, "principal", "administrator")
    before, policy_calls = counts(db), len(policy.calls)
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(AdmissionRefused) as error:
        admit(store, service, report, context=context)
    db.set_trace_callback(None)
    assert error.value.code == "PERMISSION_DENIED"
    assert counts(db) == before
    assert foreign_policy.calls == []
    assert len(policy.calls) == policy_calls
    assert_no_dependency_reads(trace)


@pytest.mark.parametrize("missing", ["service", "context", "owned-transaction"])
def test_no_implicit_authority_or_caller_owned_commit(boundary, missing):
    db, store, service, policy, report = boundary
    context = fixture_context(service)
    if missing == "service":
        store = ContextStore(db)
    elif missing == "context":
        context = None
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(AdmissionRefused):
        store.admit_transfer_event(report, admission=context)
    db.set_trace_callback(None)
    assert counts(db) == (0, 0)
    assert_no_dependency_reads(trace)


def test_preexisting_transaction_is_refused_without_committing_it(boundary):
    db, store, service, policy, report = boundary
    db.execute("BEGIN IMMEDIATE")
    with pytest.raises(AdmissionRefused):
        with store.transaction(admission=fixture_context(service)):
            pytest.fail("must not enter a caller-owned transaction")
    assert db.in_transaction
    db.rollback()
    assert counts(db) == (0, 0)


def test_independent_parent_originals_are_preserved_and_rechecked(boundary):
    db, store, service, policy, report = boundary
    assert report.parent_report.observed_at_us == 51
    assert (
        report.parent_report.report_key.scope_json
        == make_parent_report().report_key.scope_json
    )
    assert report.clock.at_us == 100
    assert report.observed_at_us == 101
    assert report.provenance_json != report.parent_report.report_key.provenance_json
    assert admit(store, service, report) == "insert"
    assert store.transfer_event_reports(KEY_EVENT_7) == (report,)
    changed = replace(
        report, parent_report=ParentObservation(report.parent_report.report_key, 52)
    )
    with pytest.raises(AdmissionRefused) as error:
        admit(store, service, changed)
    assert error.value.code == "IMMUTABLE_REPLAY_CONFLICT"
    assert db.execute(
        "SELECT observed_at_us FROM resource_relations WHERE relation_kind='parent'"
    ).fetchone() == (51,)
    assert counts(db) == (1, 2)


def test_complete_child_registration_requires_no_namespace_resource_or_parent():
    with isolated_context_db() as db:
        db.execute("INSERT INTO providers VALUES(?,?,?)", (SERVICE, "test", "{}"))
        service, policy = fixture_service(fixture_grants())
        store = ContextStore(db, authorization=service)
        context = fixture_context(service)
        with store.transaction(admission=context):
            store.resource(
                KEY_EVENT_7,
                identification=ResourceIdentification.scoped(
                    KEY_EVENT_7, KEY_ISSUE_7, "timeline_event", "77"
                ),
                admission=context,
            )
        assert store.identification(KEY_EVENT_7).provider_document_id == canonical("77")
        assert db.execute("SELECT count(*) FROM resources").fetchone() == (1,)
        assert db.execute("SELECT count(*) FROM resource_relations").fetchone() == (0,)
        assert all(KEY_ISSUE_7 not in call[2].resources for call in policy.calls)


def test_real_second_endpoint_insert_failure_rolls_back_whole_unit(boundary):
    db, store, service, policy, report = boundary
    observed = []
    db.create_function(
        "i6a_observe_counts",
        2,
        lambda events, endpoints: observed.append((events, endpoints)) or 1,
    )
    db.executescript("""
        CREATE TRIGGER i6a_second_endpoint BEFORE INSERT ON resource_repository_relations
        WHEN NEW.relation_kind='transfer_to_repository' BEGIN
          SELECT i6a_observe_counts(
            (SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'),
            (SELECT count(*) FROM resource_repository_relations WHERE relation_kind='transfer_from_repository'));
          SELECT RAISE(ABORT, 'injected actual second endpoint failure');
        END;
    """)
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(
        sqlite3.IntegrityError, match="injected actual second endpoint failure"
    ) as error:
        admit(store, service, report)
    db.set_trace_callback(None)
    assert error.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_TRIGGER
    assert observed == [(1, 1)]
    assert any("INSERT INTO resource_repository_relations" in sql for sql in trace)
    assert any(sql.upper().startswith("ROLLBACK") for sql in trace)
    assert counts(db) == (0, 0)
    assert not db.in_transaction
    assert db.execute(
        "SELECT observed_at_us FROM resource_relations WHERE relation_kind='parent'"
    ).fetchone() == (51,)
    capture_sql_probe(
        "actual_second_endpoint_insert_failure",
        trace=trace,
        sqlite_errorcode=error.value.sqlite_errorcode,
        sqlite_errorname=error.value.sqlite_errorname,
        in_trigger_counts=observed,
        after_rollback_counts=counts(db),
        transaction_open=db.in_transaction,
        parent_observed_at_us=51,
    )


def test_deferred_actual_outer_commit_failure_explicitly_rolls_back(boundary):
    db, store, service, policy, report = boundary
    missing_repository = "11111111-2222-4333-8444-555555555555"

    def deferred_rows():
        return db.execute(
            "SELECT count(*) FROM source_repositories WHERE repository_uuidv4=?",
            (missing_repository,),
        ).fetchone()[0]

    trace, commits = [], []

    def observe(sql):
        trace.append(sql)
        if sql.upper() == "COMMIT":
            commits.append((counts(db), policy.active, deferred_rows()))

    db.set_trace_callback(observe)
    context = fixture_context(service)
    with pytest.raises(sqlite3.IntegrityError) as error:
        with store.transaction(admission=context):
            assert store.admit_transfer_event(report, admission=context) == "insert"
            # Trusted SQL fault injection after guarded admission. Keep every
            # packaged schema object exact; defer a real existing-table FK.
            db.execute("PRAGMA defer_foreign_keys=ON")
            db.execute(
                "INSERT INTO source_repositories VALUES(?,?,?)",
                (SOURCE, missing_repository, "{}"),
            )
            assert deferred_rows() == 1
    db.set_trace_callback(None)
    assert error.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY
    assert commits and commits[0][0] == (1, 2)
    assert commits[0][1] > 0
    assert commits[0][2] == 1
    assert any(sql.upper() == "ROLLBACK" for sql in trace)
    assert not db.in_transaction
    assert counts(db) == (0, 0)
    assert deferred_rows() == 0
    capture_sql_probe(
        "deferred_outer_commit_failure",
        trace=trace,
        sqlite_errorcode=error.value.sqlite_errorcode,
        sqlite_errorname=error.value.sqlite_errorname,
        at_commit_counts_and_active_leases=commits,
        after_rollback_counts=counts(db),
        deferred_rows=deferred_rows(),
        transaction_open=db.in_transaction,
        parent_observed_at_us=db.execute(
            "SELECT observed_at_us FROM resource_relations WHERE relation_kind='parent'"
        ).fetchone()[0],
    )


def test_revision_revoked_after_first_insert_rolls_back_and_charges_work(boundary):
    db, store, service, policy, report = boundary
    observations = []

    def revoke():
        observations.append(counts(db))
        policy.revision += 1
        return 1

    db.create_function("i6a_revoke", 0, revoke)
    db.executescript("""
        CREATE TRIGGER i6a_revoke_after_event AFTER INSERT ON resource_relations
        WHEN NEW.relation_kind='transfer_event_report' BEGIN SELECT i6a_revoke(); END;
    """)
    budget = AdmissionBudget()
    context = fixture_context(service, budget=budget)
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(AdmissionRefused) as error:
        admit(store, service, report, context=context)
    db.set_trace_callback(None)
    assert error.value.code == "PERMISSION_DENIED"
    assert observations == [(1, 0)]
    assert counts(db) == (0, 0)
    assert not db.in_transaction
    assert budget.used_work > 0
    assert policy.active == 0
    capture_sql_probe(
        "revision_revoked_after_event_insert",
        trace=trace,
        refusal_code=error.value.code,
        at_revocation_counts=observations,
        after_rollback_counts=counts(db),
        transaction_open=db.in_transaction,
        used_work=budget.used_work,
        active_leases=policy.active,
    )


def test_policy_lease_remains_held_through_successful_commit(boundary):
    db, store, service, policy, report = boundary
    commits = []
    db.set_trace_callback(
        lambda sql: commits.append(policy.active) if sql.upper() == "COMMIT" else None
    )
    assert admit(store, service, report) == "insert"
    db.set_trace_callback(None)
    assert commits and all(active > 0 for active in commits)
    assert policy.active == 0
    assert counts(db) == (1, 2)


@pytest.mark.parametrize("replay", [False, True], ids=["initial", "stored-endpoints"])
def test_missing_declared_endpoint_cannot_be_rescued_from_local_rows(boundary, replay):
    db, store, service, policy, report = boundary
    if replay:
        assert admit(store, service, report) == "insert"
    before = counts(db)
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(AdmissionRefused) as error:
        # Preserve the whole original declaration while dropping received data.
        # Construction refuses before the store can consult previously held rows.
        candidate = replace(report, to_relations=())
        admit(store, service, candidate)
    db.set_trace_callback(None)
    assert error.value.code == "INCOMPLETE_ENDPOINT_SET"
    assert trace == []
    assert counts(db) == before


@pytest.mark.parametrize("replay", [False, True], ids=["initial", "replay"])
def test_zero_work_budget_cannot_reuse_existing_report_as_authority(boundary, replay):
    db, store, service, policy, report = boundary
    if replay:
        assert admit(store, service, report) == "insert"
    before = counts(db)
    budget = AdmissionBudget(work_limit=0)
    context = fixture_context(service, budget=budget)
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(AdmissionRefused) as error:
        admit(store, service, report, context=context)
    db.set_trace_callback(None)
    assert error.value.code == "INPUT_LIMIT"
    assert counts(db) == before
    assert budget.used_work > 0
    assert_no_dependency_reads(trace)


@pytest.mark.parametrize("entry", ["unit", "units", "batch"])
def test_unconnected_provider_routes_refuse_before_resource_lookup(
    tmp_path, monkeypatch, entry
):
    from repo_catalog.adapters.github.production_intake import NormalizedContextUnit
    from repo_catalog.adapters.sqlite.production_context import Context
    from repo_catalog.application.acquisition import ProviderAcquisition
    from repo_catalog.domain.acquisition import ProviderIntakeBatch
    from tests.integration.p3.test_transfer_admission import CLOCK_EVENT, PROV_EVENT

    def forbidden(*args, **kwargs):
        pytest.fail("unconnected Provider route reached Context or reference lookup")

    monkeypatch.setattr(Context, "transaction", forbidden)
    monkeypatch.setattr(Context, "snapshot", forbidden)
    monkeypatch.setattr(ProviderAcquisition, "_register_reference", forbidden)
    acquisition = ProviderAcquisition(tmp_path)
    unit = NormalizedContextUnit(
        KEY_EVENT_7, CLOCK_EVENT, PROV_EVENT, 101, (), (), (), (), ()
    )
    with pytest.raises(AdmissionRefused) as error:
        if entry == "unit":
            acquisition.admit_unit(unit)
        elif entry == "units":
            acquisition.admit_units((unit,))
        else:
            acquisition.admit_batch(ProviderIntakeBatch(SERVICE))
    assert error.value.code == "PERMISSION_DENIED"
    assert list(tmp_path.iterdir()) == []


def test_unconnected_exchange_export_refuses_before_identity_or_context_lookup(
    tmp_path, monkeypatch
):
    from repo_catalog.application.exchange import ExchangeService
    from repo_catalog.domain.exchange import ExchangeSelectionScope

    service = ExchangeService(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail(
            "unconnected Context export reached stored identity or dependencies"
        )

    monkeypatch.setattr(service, "_store_identity", forbidden)
    monkeypatch.setattr(service, "_export_context", forbidden)
    with pytest.raises(AdmissionRefused) as error:
        service.export_package(selection=ExchangeSelectionScope(all_selected=True))
    assert error.value.code == "PERMISSION_DENIED"


@pytest.mark.parametrize("cached", [False, True], ids=["initial", "cached-receipt"])
def test_unconnected_exchange_import_refuses_before_progress_and_cached_success(
    tmp_path, monkeypatch, cached
):
    from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
    from repo_catalog.application.exchange import ExchangeService
    from repo_catalog.domain.exchange import (
        ExchangePackage,
        ExchangeSelectionScope,
        empty_context_section,
    )
    from tests.integration.p5.conftest import init_catalog_stores

    repository, instance = init_catalog_stores(
        tmp_path, stores=("context", "operational")
    )
    section = empty_context_section()
    section["resources"] = [
        dict(
            zip(
                ("service_instance_uuidv4", "resource_kind", "provider_resource_id"),
                KEY_ISSUE_7.coordinates(),
            )
        )
    ]
    package = ExchangePackage(
        "43333333-3333-4333-8333-333333333333",
        101,
        "41111111-1111-4111-8111-111111111111",
        repository,
        selection_scope=ExchangeSelectionScope(all_selected=True),
        context=section,
    )
    with OperationalAcquisitionLedger(tmp_path) as ledger:
        if cached:
            ledger.record_exchange_receipt(
                package.package_id,
                package.digest_sha256,
                package.sender_catalog_instance_uuidv4,
                {"idempotent_replay": True, "context_imported": True},
            )
            assert (
                ledger.get_exchange_receipt(package.package_id, package.digest_sha256)
                is not None
            )
        service = ExchangeService(tmp_path, operational=ledger)
        # Store identity is infrastructure; no Context dependency lookup is
        # required to establish this already known paired fixture identity.
        monkeypatch.setattr(service, "_store_identity", lambda: (repository, instance))

        def forbidden(*args, **kwargs):
            pytest.fail(
                "unconnected import reached progress, receipt or Context dependencies"
            )

        monkeypatch.setattr(ledger, "get_exchange_receipt", forbidden)
        monkeypatch.setattr(ledger.work_ledger, "set_progress_once", forbidden)
        monkeypatch.setattr(service, "_context_dependencies", forbidden)
        monkeypatch.setattr(service, "_import_context_into", forbidden)
        with pytest.raises(AdmissionRefused) as error:
            service.import_package(package, new_request=True)
        assert error.value.code == "PERMISSION_DENIED"
    db = sqlite3.connect(tmp_path / "context.sqlite3")
    try:
        assert db.execute("SELECT count(*) FROM resources").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM resource_relations").fetchone() == (0,)
    finally:
        db.close()
