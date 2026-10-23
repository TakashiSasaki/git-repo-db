"""Non-Author adversaries; frozen helpers supply only original report/SQL setup.

No production fixture authorizer is used. Policy, failure injections and asserted
outcomes below were designed independently for this review.
"""
from contextlib import contextmanager
from copy import copy
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from threading import RLock

import pytest

from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionBudget, AdmissionContext, AdmissionRefused, AdmissionSelection,
    AuthenticatedPrincipal, ContextAdmissionService, DependencySet, dependencies,
)
from repo_catalog.domain.production_context import ContextError
from tests.integration.p3.test_transfer_admission import (
    _setup_base_records, make_transfer_report, KEY_EVENT_7,
)
from tests.support.i6a import isolated_context_db

OUT = Path(__file__).parent
OBSERVATIONS = {}


class ReviewerPolicy:
    """Finite, exact-principal grants with an invocation/session revocation epoch."""
    def __init__(self, principal, grants):
        self.principal, self.grants = principal, grants
        self.epoch, self.active, self.calls = 0, 0, []
        self.lock = RLock()

    @contextmanager
    def lease(self, principal, operation, deps):
        with self.lock:
            self.calls.append((operation, len(deps)))
            if principal is not self.principal or operation != 'provider_intake' or not deps.issubset(self.grants):
                raise AdmissionRefused('PERMISSION_DENIED')
            epoch, policy = self.epoch, self
            class Lease:
                def check_current(self):
                    if epoch != policy.epoch or not deps.issubset(policy.grants):
                        raise AdmissionRefused('PERMISSION_DENIED')
            self.active += 1
            try:
                yield Lease()
            finally:
                self.active -= 1


def issue(service, *, selection=None, operation='provider_intake'):
    return service.context('review-secret', operation,
        selection or AdmissionSelection(all_selected=True), AdmissionBudget())


@pytest.fixture
def boundary():
    with isolated_context_db() as db:
        _setup_base_records(db)
        report = make_transfer_report()
        principal = AuthenticatedPrincipal('reviewer-user', 'reviewer-session')
        policy = ReviewerPolicy(principal, dependencies(report))
        def authenticate(credential):
            if credential != 'review-secret':
                raise ValueError('untrusted credential detail')
            return principal
        service = ContextAdmissionService(policy, authenticate)
        store = ContextStore(db, authorization=service)
        yield db, store, service, policy, report
        assert policy.active == 0


def counts(db):
    return tuple(db.execute(sql).fetchone()[0] for sql in (
        "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'",
        "SELECT count(*) FROM resource_repository_relations WHERE relation_kind LIKE 'transfer_%'"))


def write(store, context, report):
    with store.transaction(admission=context):
        return store.admit_transfer_event(report, admission=context)


def no_content_reads(trace):
    reads = [sql.lower() for sql in trace if sql.lower().startswith('select')]
    assert not any('from '+table in sql for sql in reads for table in (
        'resources', 'resource_relations', 'resource_repository_relations',
        'repository_context', 'sources'))


@pytest.mark.parametrize('attack', ['constructor', 'copy', 'replace', 'foreign',
    'principal-fields', 'selection-fields', 'budget-fields'])
def test_context_substitution_before_policy_and_content(boundary, attack):
    db, store, service, policy, report = boundary
    original = issue(service)
    context = original
    if attack == 'constructor':
        context = AdmissionContext(original.principal, original.operation, original.selection, original.budget)
    elif attack == 'copy':
        context = copy(original)
    elif attack == 'replace':
        context = replace(original)
    elif attack == 'foreign':
        foreign = ContextAdmissionService(policy, lambda _: original.principal)
        context = issue(foreign)
    elif attack == 'principal-fields':
        object.__setattr__(original.principal, 'subject', 'administrator')
    elif attack == 'selection-fields':
        object.__setattr__(original.selection, 'max_units', 100_000_000)
    else:
        object.__setattr__(original.budget, 'work_limit', 100_000_000)
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(AdmissionRefused, match='^PERMISSION_DENIED$'):
        write(store, context, report)
    db.set_trace_callback(None)
    assert policy.calls == []
    no_content_reads(trace)
    assert counts(db) == (0, 0)


def test_wrong_credential_has_bounded_denial(boundary):
    _, _, service, _, _ = boundary
    with pytest.raises(AdmissionRefused) as caught:
        service.context('bad', 'provider_intake', AdmissionSelection(all_selected=True), AdmissionBudget())
    assert str(caught.value) == 'PERMISSION_DENIED'
    assert caught.value.__cause__ is None


@pytest.mark.parametrize('missing', ['service','context','owned-transaction'])
def test_no_implicit_authority(boundary, missing):
    db, store, service, policy, report = boundary
    context = issue(service)
    if missing == 'service':
        store = ContextStore(db)
    elif missing == 'context':
        context = None
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(AdmissionRefused):
        if missing == 'owned-transaction':
            store.admit_transfer_event(report, admission=context)
        else:
            write(store, context, report)
    db.set_trace_callback(None)
    no_content_reads(trace)
    assert policy.grants == dependencies(report)
    assert counts(db) == (0,0)


def test_normal_schema_has_both_exact_fences_and_refuses_transfer():
    from repo_catalog.adapters.sqlite import p1_schema
    from repo_catalog.domain.resource_stage import (
        TRANSFER_FENCE_DEFINITIONS, UnsupportedResourceStage, has_transfer_fence,
    )
    db = sqlite3.connect(':memory:', isolation_level=None)
    try:
        p1_schema.register_functions(db)
        p1_schema.configure(db)
        db.executescript(p1_schema.compose('context'))
        actual = tuple(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name IN('i2_transfer_stage_fence','i2_transfer_report_stage_fence') ORDER BY name"))
        assert actual == TRANSFER_FENCE_DEFINITIONS
        assert has_transfer_fence(db)
        _setup_base_records(db)
        report = make_transfer_report()
        principal = AuthenticatedPrincipal('reviewer-user','normal-session')
        policy = ReviewerPolicy(principal, dependencies(report))
        service = ContextAdmissionService(policy, lambda _:principal)
        store = ContextStore(db,authorization=service)
        with pytest.raises(UnsupportedResourceStage):
            write(store, issue(service), report)
        assert counts(db) == (0,0)
        assert has_transfer_fence(db)
        OBSERVATIONS['normal-fences'] = [list(row) for row in actual]
    finally:
        db.close()


@pytest.mark.parametrize('replay', [False, True])
@pytest.mark.parametrize('restriction', ['permission', 'selection', 'read-operation'])
def test_exact_replay_never_caches_authority(boundary, replay, restriction):
    db, store, service, policy, report = boundary
    if replay:
        assert write(store, issue(service), report) == 'insert'
    before = counts(db)
    expected = 'PERMISSION_DENIED'
    if restriction == 'permission':
        # Remove one resource only; other dimensions cannot grant it transitively.
        policy.grants = replace(policy.grants, resources=policy.grants.resources-{KEY_EVENT_7})
        context = issue(service)
    elif restriction == 'selection':
        deps = dependencies(report)
        context = issue(service, selection=AdmissionSelection(
            resource_keys=deps.resources-{KEY_EVENT_7}, repository_uuidv4s=deps.repositories,
            source_uuidv4s=deps.sources, object_oids=deps.object_oids))
        expected = 'OMITTED_BY_SELECTION'
    else:
        context = issue(service, operation='exchange_export')
    trace = []
    db.set_trace_callback(trace.append)
    with pytest.raises(AdmissionRefused, match='^'+expected+'$'):
        write(store, context, report)
    db.set_trace_callback(None)
    no_content_reads(trace)
    assert counts(db) == before
    assert not db.in_transaction


def test_revocation_after_success_rechecked_for_same_context(boundary):
    db, store, service, policy, report = boundary
    context = issue(service)
    assert write(store, context, report) == 'insert'
    policy.grants = DependencySet()
    with pytest.raises(AdmissionRefused, match='^PERMISSION_DENIED$'):
        write(store, context, report)
    assert counts(db) == (1, 2)


@pytest.mark.parametrize('failure', ['second-insert', 'deferred-fk', 'revocation', 'cancel'])
def test_real_sql_work_rolls_back_entire_transfer(boundary, failure):
    db, store, service, policy, report = boundary
    context, trace, observations = issue(service), [], []
    if failure == 'second-insert':
        db.create_function('review_observe', 0, lambda: observations.append(counts(db)) or 1)
        db.executescript("""CREATE TRIGGER reviewer_second_endpoint
            BEFORE INSERT ON resource_repository_relations
            WHEN NEW.relation_kind='transfer_to_repository'
            BEGIN SELECT review_observe(); SELECT RAISE(ABORT,'review-second-endpoint'); END;""")
    def trace_sql(sql):
        trace.append(sql)
        if sql.upper() == 'COMMIT':
            observations.append({'at_commit': counts(db), 'active_leases': policy.active})
    db.set_trace_callback(trace_sql)
    expected = sqlite3.IntegrityError if failure in ('second-insert', 'deferred-fk') else AdmissionRefused if failure == 'revocation' else KeyboardInterrupt
    with pytest.raises(expected) as caught:
        with store.transaction(admission=context):
            assert store.admit_transfer_event(report, admission=context) == 'insert'
            assert counts(db) == (1, 2)
            if failure == 'deferred-fk':
                db.execute('PRAGMA defer_foreign_keys=ON')
                # Real packaged FK: known service is deliberately absent as a Source.
                db.execute('INSERT INTO source_repositories VALUES(?,?,?)', (
                    'd5555555-5555-4555-8555-555555555555',
                    'd6666666-6666-4666-8666-666666666666', '{}'))
                assert db.execute('PRAGMA foreign_key_check').fetchall()
            elif failure == 'revocation':
                observations.append({'before_revoke':counts(db), 'active_leases':policy.active})
                policy.epoch += 1
            elif failure == 'cancel':
                raise KeyboardInterrupt('review cancellation after actual writes')
    db.set_trace_callback(None)
    assert counts(db) == (0, 0)
    assert not db.in_transaction
    assert policy.active == 0
    assert any(sql.upper().startswith('ROLLBACK') for sql in trace)
    assert context.budget.used_work > 0
    if failure == 'second-insert':
        assert observations == [(1, 1)]
        assert caught.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_TRIGGER
    elif failure == 'deferred-fk':
        assert caught.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY
        assert observations and observations[0]['active_leases'] > 0
        assert observations[0]['at_commit'] == (1, 2)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    elif failure == 'revocation':
        assert str(caught.value) == 'PERMISSION_DENIED'
        assert not any(sql.upper() == 'COMMIT' for sql in trace)
    OBSERVATIONS[failure] = {'trace':trace,'observations':observations,
        'exception':type(caught.value).__name__, 'message':str(caught.value),
        'sqlite_errorcode':getattr(caught.value,'sqlite_errorcode',None),
        'after_counts':counts(db), 'work_charged':context.budget.used_work}


def test_success_and_duplicate_keep_policy_lease_through_commit(boundary):
    db, store, service, policy, report = boundary
    observed = []
    db.set_trace_callback(lambda sql: observed.append((counts(db),policy.active)) if sql.upper()=='COMMIT' else None)
    assert write(store, issue(service), report) == 'insert'
    assert write(store, issue(service), report) == 'duplicate'
    db.set_trace_callback(None)
    assert len(observed) == 2
    assert all(rows == (1, 2) and active > 0 for rows, active in observed)
    OBSERVATIONS['success-and-replay'] = observed


@pytest.mark.parametrize('active,writable,code', [(True,False,'READ_ONLY'), (False,True,'CAPABILITY_EXPIRED')])
def test_facade_local_capability_precedes_sql_and_auth(active,writable,code):
    # Construct only the local capability shell: any attempted DB/auth use fails.
    class Forbidden:
        def __getattr__(self, name):
            pytest.fail('pure local capability check touched '+name)
    facade = Context.__new__(Context)
    facade._active, facade._writable = active, writable
    facade.db = facade._authorization = Forbidden()
    with pytest.raises(ContextError) as caught:
        facade.admit_transfer_event(make_transfer_report())
    assert caught.value.code == code


def test_write_observations():
    (OUT/'sql-observations.json').write_text(json.dumps(OBSERVATIONS,indent=2,sort_keys=True)+'\n')
