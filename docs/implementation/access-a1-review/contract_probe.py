"""Disposable A1 contract probes; NOT product code or a remote executor.

Run with Python 3.12+; standard-library sqlite3 only. Outputs JSON/JUnit receipts.
No repository data, network, credential store or product initializer is used.
The URI and JSON validators deliberately cover only fixture data, not a transport
security allowlist. SQL writes stand for trusted adapter operations; this harness
cannot establish that a human approved anything. Independent review is separate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from uuid import UUID
import xml.etree.ElementTree as ET

S = '9ebbe38a-f937-40e6-a99c-701835ebcf10'
S2 = '80f5c4f9-6d6b-4691-af3c-00ab02ad9f53'
R = 'aad25448-03eb-4f83-a578-ceec84375b5a'
R2 = 'a1a5dfd6-69a3-4274-bbc7-2e7f6bcd39a4'
A = 'https://runner.example/environment/a'
B = 'https://runner.example/environment/b'
L = 'file:///repos/app.git'
CONTEXT = '{"executor":"local-fixture"}'
OPTIONS = '{"transport":"fixture"}'
SQL_PATH = Path(__file__).with_name('schema_probe.sql')
DDL = SQL_PATH.read_text(encoding='utf-8')
ASSIGNMENT = (S, L, 'p', 'git-read')


def uuid_ok(v: object) -> bool:
    try:
        return isinstance(v, str) and str(UUID(v)) == v and UUID(v).version == 4
    except (ValueError, TypeError, AttributeError):
        return False


def canonical(v: object) -> str:
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def json_ok(v: object) -> bool:
    try:
        return isinstance(v, str) and canonical(json.loads(v)) == v
    except (ValueError, TypeError):
        return False


def functions(db: sqlite3.Connection) -> None:
    db.create_function('a_uuid', 1, uuid_ok, deterministic=True)
    db.create_function('a_json', 1, json_ok, deterministic=True)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA recursive_triggers=ON')


def connect(path: str = ':memory:', *, initialize: bool = True) -> sqlite3.Connection:
    db = sqlite3.connect(path, isolation_level=None)
    functions(db)
    if initialize:
        db.executescript(DDL)
    return db


def positive_time(v: object) -> int:
    if type(v) is not int or not 0 < v < 2**63:
        raise ValueError('positive int64 required; no coercion')
    return v


def register(db: sqlite3.Connection, scope: str, t: int, uri: str) -> bool:
    if not uuid_ok(scope):
        raise ValueError('UUIDv4 required')
    positive_time(t)
    if not isinstance(uri, str) or not uri or any(ord(c) < 32 or ord(c) == 127 for c in uri):
        raise ValueError('nonempty fixture URI without control characters required')
    # Retries carry the original triple. DO NOTHING never re-enables controls.
    db.execute('SAVEPOINT registration')
    try:
        cur = db.execute('INSERT INTO scope_locators VALUES(?,?,?) ON CONFLICT DO NOTHING', (scope,t,uri))
        inserted = bool(cur.rowcount)
        if inserted:
            db.execute('INSERT INTO scope_locator_controls VALUES(?,?,?,1)', (scope,t,uri))
        db.execute('RELEASE registration')
        return inserted
    except Exception:
        db.execute('ROLLBACK TO registration')
        db.execute('RELEASE registration')
        raise


def seed(db: sqlite3.Connection) -> None:
    db.execute('INSERT INTO access_scopes VALUES(?,?,?,1)', (S, 'same label', CONTEXT))
    db.execute('INSERT INTO access_scopes VALUES(?,?,?,1)', (S2, 'same label', CONTEXT))
    register(db, S, 10, A)
    db.execute('INSERT INTO repository_locators VALUES(?,?,?,1)', (S,L,R))
    db.execute('INSERT INTO connection_configurations VALUES(?,?,?,1)', (S,'p',OPTIONS))
    db.execute('INSERT INTO locator_connections VALUES(?,?,?,?,1)', ASSIGNMENT)


def grant_values(*, t: int = 10, uri: str = A, repo: str = R, options: str = OPTIONS, context: str = CONTEXT) -> tuple:
    return (*ASSIGNMENT,repo,t,uri,options,context,20)


def approve(db: sqlite3.Connection, **kwargs) -> None:
    # Fixture for ONE trusted explicit review operation; not authentication.
    db.execute('SAVEPOINT approval')
    try:
        db.execute('DELETE FROM local_access_grants WHERE scope_uuidv4=? AND locator_text=? AND configuration_name=? AND purpose=?', ASSIGNMENT)
        db.execute('INSERT INTO local_access_grants VALUES(?,?,?,?,?,?,?,?,?,?)', grant_values(**kwargs))
        db.execute('RELEASE approval')
    except Exception:
        db.execute('ROLLBACK TO approval')
        db.execute('RELEASE approval')
        raise


def first(db: sqlite3.Connection, scope: str = S) -> list[tuple]:
    return db.execute('SELECT registered_at_us,scope_locator_uri FROM scope_first_choices WHERE scope_uuidv4=? ORDER BY scope_locator_uri', (scope,)).fetchall()


def permitted(db: sqlite3.Connection, *, local_activated: bool = False,
              explicit: tuple[int,str] | None = None, context: str = CONTEXT,
              catalog_stopped: bool = False) -> bool:
    if not local_activated or catalog_stopped:
        return False
    candidates = first(db) if explicit is None else [explicit]
    if len(candidates) != 1:
        return False
    t, uri = candidates[0]
    rows = db.execute('SELECT repository_uuidv4,registered_at_us,scope_locator_uri,reviewed_options_json,reviewed_context_json FROM local_access_grants WHERE scope_uuidv4=? AND locator_text=? AND configuration_name=? AND purpose=?', ASSIGNMENT).fetchall()
    if rows != [(R,t,uri,OPTIONS,context)]:
        return False
    # Equality and all enablement are checked again before simulated dispatch.
    return bool(db.execute('''SELECT 1 FROM local_access_grants g
    JOIN scope_locators sl ON (sl.scope_uuidv4,sl.registered_at_us,sl.scope_locator_uri)=(g.scope_uuidv4,g.registered_at_us,g.scope_locator_uri)
    JOIN scope_locator_controls c ON (c.scope_uuidv4,c.registered_at_us,c.scope_locator_uri)=(g.scope_uuidv4,g.registered_at_us,g.scope_locator_uri)
    JOIN connection_configurations p ON (p.scope_uuidv4,p.configuration_name)=(g.scope_uuidv4,g.configuration_name)
    JOIN repository_locators r ON (r.scope_uuidv4,r.locator_text,r.repository_uuidv4)=(g.scope_uuidv4,g.locator_text,g.repository_uuidv4)
    JOIN access_scopes s ON s.scope_uuidv4=g.scope_uuidv4
    JOIN locator_connections a ON (a.scope_uuidv4,a.locator_text,a.configuration_name,a.purpose)=(g.scope_uuidv4,g.locator_text,g.configuration_name,g.purpose)
    WHERE g.scope_uuidv4=? AND g.locator_text=? AND g.configuration_name=? AND g.purpose=?
    AND c.enabled=1 AND p.enabled=1 AND r.enabled=1 AND a.enabled=1 AND s.enabled=1
    AND p.options_json=g.reviewed_options_json AND s.execution_context_json=g.reviewed_context_json''', ASSIGNMENT).fetchone())


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        self.addCleanup(self.db.close)
        seed(self.db)

    def count(self, table='local_access_grants'):
        return self.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]

    def test_actual_constraints(self):
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone(), ('ok',))
        for _,name,kind,_,wr,strict in self.db.execute('PRAGMA table_list'):
            if kind=='table' and not name.startswith('sqlite_'):
                self.assertEqual((wr,strict),(1,1),name)

    def test_aba_history(self):
        register(self.db,S,20,B); register(self.db,S,30,A)
        self.assertEqual(self.count('scope_locators'),3)
        self.assertEqual(first(self.db),[(30,A)])

    def test_exact_replay(self):
        self.assertFalse(register(self.db,S,10,A))
        self.assertEqual(self.count('scope_locators'),1)

    def test_equal_time_alternatives(self):
        register(self.db,S,10,B)
        self.assertEqual(set(first(self.db)),{(10,A),(10,B)})
        approve(self.db)
        self.assertFalse(permitted(self.db,local_activated=True))

    def test_clock_rollback_not_arrival_order(self):
        register(self.db,S,5,B)
        self.assertEqual(first(self.db),[(10,A)])

    def test_late_replay_cannot_promote(self):
        register(self.db,S,20,B); register(self.db,S,10,A)
        self.assertEqual(first(self.db),[(20,B)])

    def test_scope_locator_uri_not_identity(self):
        register(self.db,S2,10,A)
        self.assertEqual(self.count('scope_locators'),2)

    def test_labels_not_unique_keys(self):
        self.assertEqual(self.count('access_scopes'),2)

    def test_scope_rename_preserves_grant(self):
        approve(self.db)
        self.db.execute("UPDATE access_scopes SET display_name='renamed' WHERE scope_uuidv4=?",(S,))
        self.assertTrue(permitted(self.db,local_activated=True))

    def test_scope_rekey_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('UPDATE access_scopes SET scope_uuidv4=? WHERE scope_uuidv4=?',(R2,S))

    def test_repo_binding_is_unique(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT INTO repository_locators VALUES(?,?,?,1)',(S,L,R2))

    def test_preferences_cannot_cross_repository(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT INTO repository_access_preferences VALUES(?,?,?,?,?)',(R2,S,'git-read',L,'p'))

    def test_grant_requires_full_registration(self):
        with self.assertRaises(sqlite3.IntegrityError): approve(self.db,t=11)

    def test_grant_requires_matching_repo(self):
        with self.assertRaises(sqlite3.IntegrityError): approve(self.db,repo=R2)

    def test_grant_requires_current_profile(self):
        with self.assertRaises(sqlite3.IntegrityError): approve(self.db,options='{}')

    def test_grant_requires_current_context(self):
        with self.assertRaises(sqlite3.IntegrityError): approve(self.db,context='{}')

    def test_grant_not_authorization_on_its_own(self):
        approve(self.db)
        self.assertFalse(permitted(self.db))
        self.assertTrue(permitted(self.db,local_activated=True))

    def test_newest_unapproved_does_not_fallback(self):
        approve(self.db); register(self.db,S,20,B)
        self.assertEqual(first(self.db),[(20,B)])
        self.assertFalse(permitted(self.db,local_activated=True))

    def test_newest_disabled_does_not_fallback(self):
        approve(self.db); register(self.db,S,20,B)
        self.db.execute('UPDATE scope_locator_controls SET enabled=0 WHERE registered_at_us=20')
        self.assertEqual(first(self.db),[(20,B)])
        self.assertFalse(permitted(self.db,local_activated=True))

    def test_same_uri_new_registration_not_old_approval(self):
        approve(self.db); register(self.db,S,20,B); register(self.db,S,30,A)
        self.assertFalse(permitted(self.db,local_activated=True))
        approve(self.db,t=30)
        self.assertTrue(permitted(self.db,local_activated=True))

    def test_explicit_old_selection_is_not_automatic_fallback(self):
        approve(self.db); register(self.db,S,20,B)
        self.assertFalse(permitted(self.db,local_activated=True))
        self.assertTrue(permitted(self.db,local_activated=True,explicit=(10,A)))

    def test_profile_aba_does_not_revive_grant(self):
        approve(self.db)
        self.db.execute("UPDATE connection_configurations SET options_json='{}'")
        self.db.execute('UPDATE connection_configurations SET options_json=?',(OPTIONS,))
        self.assertEqual(self.count(),0)
        self.assertFalse(permitted(self.db,local_activated=True))

    def test_binding_aba_does_not_revive_grant(self):
        approve(self.db)
        self.db.execute('UPDATE repository_locators SET repository_uuidv4=?',(R2,))
        self.db.execute('UPDATE repository_locators SET repository_uuidv4=?',(R,))
        self.assertEqual(self.count(),0)

    def test_context_aba_does_not_revive_grant(self):
        approve(self.db)
        self.db.execute("UPDATE access_scopes SET execution_context_json='{}' WHERE scope_uuidv4=?",(S,))
        self.db.execute('UPDATE access_scopes SET execution_context_json=? WHERE scope_uuidv4=?',(CONTEXT,S))
        self.assertEqual(self.count(),0)

    def test_route_disable_enable_revokes(self):
        approve(self.db)
        self.db.execute('UPDATE scope_locator_controls SET enabled=0')
        self.db.execute('UPDATE scope_locator_controls SET enabled=1')
        self.assertEqual(self.count(),0)
        self.assertEqual(self.count('scope_locators'),1)

    def test_assignment_disable_enable_revokes(self):
        approve(self.db)
        self.db.execute('UPDATE locator_connections SET enabled=0')
        self.db.execute('UPDATE locator_connections SET enabled=1')
        self.assertEqual(self.count(),0)

    def test_control_delete_revokes_not_history(self):
        approve(self.db)
        self.db.execute('DELETE FROM scope_locator_controls')
        self.assertEqual(self.count(),0)
        self.assertEqual(first(self.db),[(10,A)])

    def test_replay_does_not_reenable_controls(self):
        self.db.execute('UPDATE scope_locator_controls SET enabled=0')
        register(self.db,S,10,A)
        self.assertEqual(self.db.execute('SELECT enabled FROM scope_locator_controls').fetchone(),(0,))

    def test_disabled_cannot_be_approved(self):
        self.db.execute('UPDATE connection_configurations SET enabled=0')
        with self.assertRaises(sqlite3.IntegrityError): approve(self.db)

    def test_failed_reapproval_rolls_back(self):
        approve(self.db)
        with self.assertRaises(sqlite3.IntegrityError): approve(self.db,t=999)
        self.assertTrue(permitted(self.db,local_activated=True))

    def test_grant_update_rejected(self):
        approve(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('UPDATE local_access_grants SET registered_at_us=999')

    def test_external_context_mismatch_denies(self):
        approve(self.db)
        self.assertFalse(permitted(self.db,local_activated=True,context='{"executor":"other"}'))

    def test_catalog_stop_has_priority(self):
        approve(self.db)
        self.assertFalse(permitted(self.db,local_activated=True,catalog_stopped=True))

    def test_fork_preserves_source_history(self):
        before=self.db.execute('SELECT * FROM scope_locators WHERE scope_uuidv4=?',(S,)).fetchall()
        register(self.db,S2,30,A)
        self.assertEqual(self.db.execute('SELECT * FROM scope_locators WHERE scope_uuidv4=?',(S,)).fetchall(),before)
        self.assertEqual(first(self.db,S2),[(30,A)])

    def test_registration_and_control_are_atomic(self):
        self.db.execute("CREATE TRIGGER inject BEFORE INSERT ON scope_locator_controls WHEN NEW.registered_at_us=30 BEGIN SELECT RAISE(ABORT,'injected control failure'); END;")
        with self.assertRaises(sqlite3.IntegrityError): register(self.db,S,30,B)
        self.assertEqual(first(self.db),[(10,A)])
        self.assertEqual(self.count('scope_locators'),1)

    def test_successful_reapproval_changes_exact_registration(self):
        approve(self.db); register(self.db,S,30,B); approve(self.db,t=30,uri=B)
        self.assertTrue(permitted(self.db,local_activated=True))
        self.assertEqual(self.count(),1)

    def test_preference_matches_both_parents(self):
        self.db.execute('INSERT INTO repository_access_preferences VALUES(?,?,?,?,?)',(R,S,'git-read',L,'p'))
        self.assertEqual(self.count('repository_access_preferences'),1)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_missing_assignment_cannot_be_approved(self):
        self.db.execute('DELETE FROM locator_connections')
        with self.assertRaises(sqlite3.IntegrityError): approve(self.db)

    def test_same_content_noop_profile_update_preserves_grant(self):
        approve(self.db)
        self.db.execute('UPDATE connection_configurations SET options_json=?',(OPTIONS,))
        self.assertTrue(permitted(self.db,local_activated=True))

    def test_profile_replace_cannot_bypass_revocation(self):
        approve(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT OR REPLACE INTO connection_configurations VALUES(?,?,?,1)',(S,'p',OPTIONS))
        self.assertTrue(permitted(self.db,local_activated=True))

    def test_wal_snapshot_and_disabled_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            live=connect(str(Path(temp)/'live.db')); self.addCleanup(live.close)
            live.execute('PRAGMA journal_mode=WAL'); seed(live); register(live,S,20,B); approve(live,t=20,uri=B)
            reader=connect(str(Path(temp)/'live.db'),initialize=False); self.addCleanup(reader.close)
            reader.execute('BEGIN'); self.assertEqual(first(reader),[(20,B)])
            register(live,S,30,A)
            self.assertEqual(first(reader),[(20,B)])
            copy=connect(str(Path(temp)/'copy.db'),initialize=False); self.addCleanup(copy.close)
            live.backup(copy)
            self.assertEqual(copy.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(copy.execute('SELECT count(*) FROM scope_locators').fetchone(),(3,))
            self.assertEqual(first(copy),[(30,A)])
            # Supported restore sanitizes local authority before exposing destination.
            copy.execute('BEGIN IMMEDIATE'); copy.execute('DELETE FROM local_access_grants')
            copy.execute('UPDATE scope_locator_controls SET enabled=0'); copy.commit()
            self.assertEqual(copy.execute('SELECT count(*) FROM local_access_grants').fetchone(),(0,))
            self.assertFalse(permitted(copy,local_activated=True))
            reader.rollback()


# Every invalid API value and destructive SQL attack is independently counted.
for n,value in enumerate([None,True,False,0,-1,2**63,1.5,'10']):
    def bad_time(self,v=value):
        with self.assertRaises(ValueError): register(self.db,S,v,A)
    setattr(ContractTests,f'test_bad_api_time_{n:02}',bad_time)
for n,value in enumerate(['invalid',S.upper(),str(UUID(int=0)),None]):
    def bad_uuid(self,v=value):
        with self.assertRaises(ValueError): register(self.db,v,10,A)
    setattr(ContractTests,f'test_bad_scope_uuid_{n:02}',bad_uuid)
for n,sql in enumerate([
    'UPDATE scope_locators SET registered_at_us=11',
    'DELETE FROM scope_locators',
    f"INSERT OR REPLACE INTO scope_locators VALUES('{S}',10,'{A}')",
    f"INSERT INTO scope_locators VALUES('{S}',10,'{A}') ON CONFLICT DO UPDATE SET registered_at_us=11",
]):
    def attack(self,statement=sql):
        with self.assertRaises(sqlite3.IntegrityError): self.db.execute(statement)
        self.assertEqual(first(self.db),[(10,A)])
    setattr(ContractTests,f'test_registration_write_attack_{n:02}',attack)


class ReceiptResult(unittest.TextTestResult):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw); self.records=[]
    def addSuccess(self,test):
        super().addSuccess(test); self.records.append({'test':test.id(),'status':'passed'})
    def addFailure(self,test,err):
        super().addFailure(test,err); self.records.append({'test':test.id(),'status':'failed'})
    def addError(self,test,err):
        super().addError(test,err); self.records.append({'test':test.id(),'status':'error'})


def main():
    p=argparse.ArgumentParser(); p.add_argument('--json',type=Path); p.add_argument('--junit',type=Path)
    args=p.parse_args(); start=datetime.now(timezone.utc).isoformat()
    result=unittest.TextTestRunner(verbosity=2,resultclass=ReceiptResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests))
    receipt={'started_at':start,'completed_at':datetime.now(timezone.utc).isoformat(),
        'python':sys.version,'sqlite':sqlite3.sqlite_version,'tests':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'schema_sha256':hashlib.sha256(SQL_PATH.read_bytes()).hexdigest(),
        'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'disposable relational contract model; not product acceptance or independent-agent review',
        'records':result.records}
    if args.json: args.json.write_text(json.dumps(receipt,indent=2)+'\n')
    if args.junit:
        root=ET.Element('testsuite',name='access-a1-contract-probe',tests=str(result.testsRun),failures=str(len(result.failures)),errors=str(len(result.errors)))
        for row in result.records:
            case=ET.SubElement(root,'testcase',name=row['test'])
            if row['status']!='passed': ET.SubElement(case,row['status'])
        ET.ElementTree(root).write(args.junit,encoding='utf-8',xml_declaration=True)
    return not result.wasSuccessful()

if __name__=='__main__': raise SystemExit(main())
