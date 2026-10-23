"""Independent #153 admission probes; synthetic finite grants, no production fence removal."""
from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3

import pytest
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.context_admission import (
    AdmissionBudget, AdmissionRefused, AdmissionSelection, AuthenticatedPrincipal,
    ContextAdmissionService, dependencies,
)
from tests.integration.p3.test_transfer_admission import _setup_base_records, make_transfer_report
from tests.support.i6a import isolated_context_db

OBS = {}

class FinitePolicy:
    def __init__(self, principal, grants):
        self.principal = principal
        self.grants = grants
        self.active = 0
        self.calls = []
        self.epoch = 0

    @contextmanager
    def lease(self, principal, operation, needed):
        self.calls.append((principal.subject, operation, len(needed)))
        if principal is not self.principal or operation != 'provider_intake' or not needed.issubset(self.grants):
            raise AdmissionRefused('PERMISSION_DENIED')
        epoch = self.epoch
        policy = self
        class Lease:
            def check_current(self):
                if epoch != policy.epoch or not needed.issubset(policy.grants):
                    raise AdmissionRefused('PERMISSION_DENIED')
        self.active += 1
        try:
            yield Lease()
        finally:
            self.active -= 1


def issue(service, budget=None):
    return service.context('finite-credential', 'provider_intake', AdmissionSelection(all_selected=True), budget or AdmissionBudget())


def snapshot(db):
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")]
    return {t: sorted([list(r) for r in db.execute(f'SELECT * FROM "{t}"')], key=repr) for t in tables}


def counts(db):
    return tuple(db.execute(q).fetchone()[0] for q in (
        "SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'",
        "SELECT count(*) FROM resource_repository_relations WHERE relation_kind LIKE 'transfer_%'"))


@pytest.fixture
def boundary():
    with isolated_context_db() as db:
        _setup_base_records(db)
        report = make_transfer_report()
        principal = AuthenticatedPrincipal('finite-subject', 'finite-session')
        policy = FinitePolicy(principal, dependencies(report))
        service = ContextAdmissionService(policy, lambda _: principal)
        store = ContextStore(db, authorization=service)
        yield db, report, principal, policy, service, store
        assert policy.active == 0
        assert not db.in_transaction


@contextmanager
def transaction(boundary, adapter, tmp_path, context):
    db, _, _, _, service, store = boundary
    if adapter == 'store':
        with store.transaction(admission=context):
            yield store
    else:
        with Context.owned_transaction(db, tmp_path, authorization=service, admission=context) as facade:
            yield facade


def write(boundary, adapter, tmp_path, context):
    with transaction(boundary, adapter, tmp_path, context) as target:
        return target.admit_transfer_event(boundary[1], admission=context)


@pytest.mark.parametrize('adapter', ['store', 'facade'])
@pytest.mark.parametrize('replay', [False, True])
def test_foreign_service_with_identical_principal_and_policy_still_refuses(boundary, tmp_path, adapter, replay):
    db, report, principal, policy, service, _ = boundary
    if replay:
        assert write(boundary, adapter, tmp_path, issue(service)) == 'insert'
    # Stronger than equal fields: use the very same principal and policy objects.
    foreign = ContextAdmissionService(policy, lambda _: principal)
    context = issue(foreign)
    before, calls, trace = snapshot(db), len(policy.calls), []
    db.set_trace_callback(trace.append)
    try:
        with pytest.raises(AdmissionRefused, match='^PERMISSION_DENIED$'):
            write(boundary, adapter, tmp_path, context)
    finally:
        db.set_trace_callback(None)
    assert len(policy.calls) == calls
    assert snapshot(db) == before
    assert trace == []
    OBS[f'{adapter}/{replay}/foreign-same-objects'] = {'refusal': 'PERMISSION_DENIED', 'trace': trace, 'rows_unchanged': True}


@pytest.mark.parametrize('adapter', ['store', 'facade'])
def test_revocation_inside_actual_second_endpoint_statement_rolls_back(boundary, tmp_path, adapter):
    db, _, _, policy, service, _ = boundary
    before, reached, trace = snapshot(db), [], []
    def revoke():
        reached.append({'counts': counts(db), 'leases': policy.active})
        policy.epoch += 1
        return 1
    db.create_function('rr_revoke_second', 0, revoke)
    context = issue(service)
    db.set_trace_callback(trace.append)
    try:
        with pytest.raises(AdmissionRefused, match='^PERMISSION_DENIED$'):
            with transaction(boundary, adapter, tmp_path, context) as target:
                # Install fault injection after the exact packaged schema was
                # checked by facade construction; rollback removes this trigger.
                db.execute("""CREATE TRIGGER rr_second_endpoint AFTER INSERT ON resource_repository_relations
                    WHEN NEW.relation_kind='transfer_to_repository' BEGIN SELECT rr_revoke_second(); END""")
                target.admit_transfer_event(boundary[1], admission=context)
    finally:
        db.set_trace_callback(None)
    assert len(reached) == 1 and reached[0]['counts'] == (1, 2) and reached[0]['leases'] > 0
    assert snapshot(db) == before
    assert any(q.upper().startswith('ROLLBACK TO') for q in trace)
    assert any(q.upper() == 'ROLLBACK' for q in trace)
    assert not any(q.upper() == 'COMMIT' for q in trace)
    assert context.budget.used_work > 0
    OBS[f'{adapter}/second-statement-revocation'] = {'at_second_insert': reached, 'trace': trace, 'charged_work': context.budget.used_work, 'rows_unchanged': True}


@pytest.mark.parametrize('adapter', ['store', 'facade'])
def test_denied_real_transfer_savepoint_release_cannot_escape_pending_rows(boundary, tmp_path, adapter):
    db, _, _, policy, service, _ = boundary
    before, reached, trace = snapshot(db), [], []
    def deny_release(action, first, second, database, origin):
        if action == sqlite3.SQLITE_SAVEPOINT and first == 'RELEASE' and second == 'p1_transfer_event':
            reached.append({'counts': counts(db), 'leases': policy.active})
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    db.set_authorizer(deny_release)
    db.set_trace_callback(trace.append)
    context = issue(service)
    try:
        with pytest.raises(sqlite3.DatabaseError) as caught:
            write(boundary, adapter, tmp_path, context)
    finally:
        db.set_authorizer(None)
        db.set_trace_callback(None)
    assert caught.value.sqlite_errorcode == sqlite3.SQLITE_AUTH
    assert reached and reached[0]['counts'] == (1, 2) and reached[0]['leases'] > 0
    assert snapshot(db) == before
    assert any(q.upper() == 'ROLLBACK' for q in trace)
    assert not any(q.upper() == 'COMMIT' for q in trace)
    assert context.budget.used_work > 0
    OBS[f'{adapter}/release-denied'] = {'release_attempts': reached, 'trace': trace, 'sqlite_errorcode': caught.value.sqlite_errorcode, 'charged_work': context.budget.used_work, 'rows_unchanged': True}


@pytest.mark.parametrize('adapter', ['store', 'facade'])
def test_work_is_charged_again_on_same_context_replay_and_not_refunded(boundary, tmp_path, adapter):
    db, _, _, policy, service, _ = boundary
    calibration = issue(service)
    assert write(boundary, adapter, tmp_path, calibration) == 'insert'
    one_duplicate = issue(service)
    assert write(boundary, adapter, tmp_path, one_duplicate) == 'duplicate'
    # A fresh finite budget permits exactly the independently measured duplicate.
    budget = AdmissionBudget(work_limit=one_duplicate.budget.used_work)
    context = issue(service, budget)
    assert write(boundary, adapter, tmp_path, context) == 'duplicate'
    assert budget.used_work == budget.work_limit
    before, trace, prior = snapshot(db), [], budget.used_work
    db.set_trace_callback(trace.append)
    try:
        with pytest.raises(AdmissionRefused, match='^INPUT_LIMIT$'):
            write(boundary, adapter, tmp_path, context)
    finally:
        db.set_trace_callback(None)
    assert budget.used_work > prior
    assert snapshot(db) == before
    assert not any('INSERT' in q.upper() for q in trace)
    assert not db.in_transaction and policy.active == 0
    OBS[f'{adapter}/same-budget-replay'] = {'first_duplicate_work': prior, 'after_refusal_work': budget.used_work, 'trace': trace, 'rows_unchanged': True}


@pytest.mark.parametrize('adapter', ['store', 'facade'])
def test_real_deferred_fk_commit_failure_retains_lease_and_rolls_back(boundary, tmp_path, adapter):
    db, _, _, policy, service, _ = boundary
    before, commits, trace = snapshot(db), [], []
    def observe(sql):
        trace.append(sql)
        if sql.upper() == 'COMMIT':
            commits.append({'counts': counts(db), 'leases': policy.active,
                'foreign_key_violations': [list(r) for r in db.execute('PRAGMA foreign_key_check')]})
    context = issue(service)
    db.set_trace_callback(observe)
    try:
        with pytest.raises(sqlite3.IntegrityError) as caught:
            with transaction(boundary, adapter, tmp_path, context) as target:
                assert target.admit_transfer_event(boundary[1], admission=context) == 'insert'
                db.execute('PRAGMA defer_foreign_keys=ON')
                db.execute('INSERT INTO source_repositories VALUES(?,?,?)', (
                    '25555555-5555-4555-8555-555555555555',
                    '26666666-6666-4666-8666-666666666666', '{}'))
                assert db.execute('PRAGMA foreign_key_check').fetchall()
    finally:
        db.set_trace_callback(None)
    assert caught.value.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY
    assert len(commits) == 1 and commits[0]['counts'] == (1, 2) and commits[0]['leases'] > 0
    assert commits[0]['foreign_key_violations']
    assert snapshot(db) == before
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    assert context.budget.used_work > 0
    assert any(q.upper() == 'ROLLBACK' for q in trace)
    OBS[f'{adapter}/deferred-real-commit-failure'] = {'commit_attempts': commits, 'trace': trace,
        'sqlite_errorcode': caught.value.sqlite_errorcode, 'charged_work': context.budget.used_work, 'rows_unchanged': True}


def test_write_observations():
    Path(os.environ['RR_ADMISSION_OBSERVATIONS']).write_text(json.dumps(OBS, indent=2, sort_keys=True) + '\n')
