"""Explicit local Context authority retained through PairCoordinator commit."""

import sqlite3
from contextlib import contextmanager

import pytest

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionBudget,
    AdmissionRefused,
    AdmissionSelection,
    ContextAdmissionService,
    DependencySet,
    dependencies,
)
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_coordination import (
    AdmissionFailure,
    CoordinationError,
    PairAdmission,
)
from tests.support.context_admission import fixture_context, fixture_service

REPOSITORY = "9ebbe38a-f937-40e6-a99c-701835ebcf10"
INSTANCE = "f7ebfbbf-53cc-43db-98df-d80326e80922"
PROVIDER = "e19d36ab-3876-4c36-b998-183827af06ef"
KEY = ResourceKey.from_native(PROVIDER, "issue", "7")


@pytest.fixture
def catalog(tmp_path):
    for role in ("core", "context"):
        initialize(tmp_path / f"{role}.sqlite3", role, REPOSITORY, INSTANCE)
    return tmp_path


def authority():
    service, policy = fixture_service(
        dependencies(KEY) | DependencySet(repositories={REPOSITORY})
    )
    return service, policy, fixture_context(service)


def resource_count(directory):
    with connect(directory / "context.sqlite3", "context") as db:
        return db.execute("SELECT count(*) FROM resources").fetchone()[0]


@pytest.mark.parametrize("facade", [False, True])
def test_local_authority_survives_callback_until_actual_commit(catalog, facade):
    service, policy, admission = authority()
    captured = []
    checked = []

    def context_unit(tx):
        if facade:
            with Context.for_transaction(tx, catalog) as context:
                context.provider(PROVIDER, "synthetic")
                context.resource(KEY)
                captured.append(context)
        else:
            tx.execute("INSERT INTO providers VALUES(?,'synthetic','{}')", (PROVIDER,))
            store = ContextStore(tx)
            store.resource(KEY)
            captured.append(store)
        assert policy.active > 0

    def cut(point):
        if point == "during_context":
            assert policy.active > 0
            checked.append(point)

    result = PairCoordinator(catalog, authorization=service).admit(
        lambda tx: None,
        context_unit,
        authorization=service,
        admission=admission,
        cut=cut,
    )
    assert result == PairAdmission(True, True)
    assert checked == ["during_context"] and resource_count(catalog) == 1
    assert policy.active == 0
    calls_before = len(policy.calls)
    with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
        captured[0].resource(KEY)
    assert len(policy.calls) == calls_before


def test_revocation_after_callback_rolls_back_context_before_commit(catalog):
    service, policy, admission = authority()

    def context_unit(tx):
        tx.execute("INSERT INTO providers VALUES(?,'synthetic','{}')", (PROVIDER,))
        ContextStore(tx).resource(KEY)

    def cut(point):
        if point == "during_context":
            policy.grants = DependencySet()

    with pytest.raises(AdmissionFailure) as failure:
        PairCoordinator(catalog, authorization=service).admit(
            lambda tx: None,
            context_unit,
            authorization=service,
            admission=admission,
            cut=cut,
        )
    assert failure.value.outcome == PairAdmission(True, False)
    assert failure.value.cause.code == "PERMISSION_DENIED"
    assert resource_count(catalog) == 0 and policy.active == 0


def test_missing_context_binding_does_not_create_authority(catalog):
    with pytest.raises(AdmissionFailure) as failure:
        PairCoordinator(catalog).admit(
            lambda tx: None, lambda tx: ContextStore(tx).resource(KEY)
        )
    assert failure.value.cause.code == "PERMISSION_DENIED"
    assert resource_count(catalog) == 0


def test_foreign_context_refuses_before_store_lookup_or_core_callback(tmp_path):
    service, policy, _ = authority()
    foreign, foreign_policy, foreign_context = authority()
    calls = []
    coordinator = PairCoordinator(tmp_path / "nonexistent", authorization=service)
    coordinator._open = lambda role: calls.append(role)
    with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
        coordinator.admit(
            lambda tx: calls.append("core"),
            lambda tx: None,
            authorization=service,
            admission=foreign_context,
        )
    assert calls == [] and not policy.calls and not foreign_policy.calls
    assert foreign is not service


def test_conflicting_local_binding_cannot_replace_coordinator_invocation(catalog):
    service, policy, admission = authority()
    foreign, _, foreign_context = authority()

    def context_unit(tx):
        with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
            ContextStore(tx, authorization=foreign)
        with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
            with Context.for_transaction(
                tx, catalog, authorization=foreign, admission=foreign_context
            ):
                pytest.fail("foreign facade bound")
        other_context = fixture_context(service)
        calls_before = len(policy.calls)
        with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
            ContextStore(tx).resource(KEY, admission=other_context)
        assert len(policy.calls) == calls_before

    assert PairCoordinator(catalog, authorization=service).admit(
        lambda tx: None, context_unit, authorization=service, admission=admission
    ) == PairAdmission(True, True)


def test_deferred_context_commit_failure_rolls_back_real_pending_rows(catalog):
    service, policy, admission = authority()
    coordinator = PairCoordinator(catalog, authorization=service)
    original_open = coordinator._open
    pending = []

    class DeferredForeignKeys:
        def __init__(self, connection):
            self._connection = connection

        def __getattr__(self, name):
            return getattr(self._connection, name)

        def execute(self, sql, parameters=()):
            cursor = self._connection.execute(sql, parameters)
            if sql == "BEGIN IMMEDIATE":
                # Enable in the real transaction: an earlier autocommit SELECT
                # resets this pragma on this environment's loaded SQLite.
                self._connection.execute("PRAGMA defer_foreign_keys=ON")
            return cursor

    def open_deferred(role):
        db = original_open(role)
        return DeferredForeignKeys(db) if role == "context" else db

    coordinator._open = open_deferred

    def context_unit(tx):
        # Provider FK is deliberately missing; defer it until actual COMMIT.
        ContextStore(tx).resource(KEY)
        pending.append(tx.execute("SELECT count(*) FROM resources").fetchone()[0])

    with pytest.raises(AdmissionFailure) as failure:
        coordinator.admit(
            lambda tx: None, context_unit, authorization=service, admission=admission
        )
    assert pending == [1], repr(failure.value.cause)
    assert isinstance(failure.value.cause, sqlite3.IntegrityError)
    assert failure.value.outcome == PairAdmission(True, False)
    assert resource_count(catalog) == 0 and policy.active == 0
    assert not (catalog / "p1-recovery-stop.json").exists()


class ExportPolicy:
    """Finite export grant only; never a production permissive fallback."""

    def __init__(self):
        self.grants = dependencies(KEY)
        self.calls = []

    @contextmanager
    def lease(self, principal, operation, deps):
        self.calls.append((principal, operation, deps))
        if (
            principal != "export-user"
            or operation != "exchange_export"
            or not deps.issubset(self.grants)
        ):
            raise AdmissionRefused("PERMISSION_DENIED")

        class Lease:
            def check_current(self):
                pass

        yield Lease()


def test_export_invocation_cannot_open_mutation_or_commit_core(catalog):
    policy = ExportPolicy()
    service = ContextAdmissionService(policy, lambda credential: "export-user")
    admission = service.context(
        "local",
        "exchange_export",
        AdmissionSelection(all_selected=True),
        AdmissionBudget(),
    )
    core_called = []
    with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
        PairCoordinator(catalog, authorization=service).admit(
            lambda tx: core_called.append(True),
            lambda tx: None,
            authorization=service,
            admission=admission,
        )
    with connect(catalog / "context.sqlite3", "context") as db:
        statements = []
        db.set_trace_callback(statements.append)
        store = ContextStore(db, authorization=service)
        with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
            with store.admission_transaction(admission=admission):
                pytest.fail("export acquired write transaction")
        with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
            store.resource(KEY, admission=admission)
        assert statements == [] and not db.in_transaction
    assert not core_called and not policy.calls


class SubstitutionAttackPolicy:
    """Adversarial test handle: attempts to grant every requested dependency."""

    def __init__(self):
        self.calls = []

    @contextmanager
    def lease(self, principal, operation, deps):
        self.calls.append((principal, operation, deps))

        class Lease:
            def check_current(self):
                pass

        yield Lease()


@pytest.mark.parametrize("bound", [False, True])
def test_foreign_policy_service_cannot_supply_coordinator_authority(tmp_path, bound):
    service, policy, _ = authority()
    attack_policy = SubstitutionAttackPolicy()
    attack_service = ContextAdmissionService(attack_policy, lambda credential: "admin")
    attack_context = attack_service.context(
        "forged",
        "provider_intake",
        AdmissionSelection(all_selected=True),
        AdmissionBudget(),
    )
    coordinator = PairCoordinator(
        tmp_path / "absent", authorization=service if bound else None
    )
    events = []
    coordinator._open = lambda role: events.append(role)
    with pytest.raises(AdmissionRefused, match="^PERMISSION_DENIED$"):
        coordinator.admit(
            lambda tx: events.append("core"),
            lambda tx: events.append("context"),
            authorization=attack_service,
            admission=attack_context,
        )
    assert not events and not policy.calls and not attack_policy.calls


def test_bound_source_repository_coverage_closes_cursors_and_expires_them(catalog):
    from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope

    source = "c1111111-1111-4111-8111-111111111111"
    claim = CoverageClaim(
        CoverageScope.source(source, REPOSITORY, "known"), 20, "partial"
    )
    service, policy = fixture_service(dependencies(claim))
    admission = fixture_context(service)
    held = []

    def context_unit(tx):
        tx.execute("INSERT INTO providers VALUES(?,'synthetic','{}')", (PROVIDER,))
        tx.execute("INSERT INTO repository_context VALUES(?,'{}')", (REPOSITORY,))
        tx.execute("INSERT INTO sources VALUES(?,?,'{}')", (source, PROVIDER))
        tx.execute(
            "INSERT INTO source_repositories VALUES(?,?,'{}')", (source, REPOSITORY)
        )
        store = ContextStore(tx)
        store.scope(claim.scope)
        assert store.admit_coverage(claim) == "insert"
        cursor = tx.execute("SELECT 1")
        cursor.close()
        held.append(cursor)

    assert PairCoordinator(catalog, authorization=service).admit(
        lambda tx: None, context_unit, admission=admission
    ) == PairAdmission(True, True)
    assert policy.active == 0
    calls_before = len(policy.calls)
    with pytest.raises(CoordinationError) as expired:
        held[0].fetchone()
    assert getattr(expired.value, "code", None) == "CAPABILITY_EXPIRED"
    assert len(policy.calls) == calls_before
    with connect(catalog / "context.sqlite3", "context") as db:
        assert db.execute("SELECT count(*) FROM coverage_claims").fetchone()[0] == 1
