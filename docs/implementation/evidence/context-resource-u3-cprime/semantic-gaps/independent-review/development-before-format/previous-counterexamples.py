#!/usr/bin/env python3
"""Independent baseline-only counterexamples; run against the previous freeze."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

p = argparse.ArgumentParser()
p.add_argument('--repo', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
root = a.repo.resolve()
base = root / 'docs/implementation/evidence/context-resource-u3-cprime'
sys.path[:0] = [str(root / 'src'), str(base / 'candidates')]
spec = importlib.util.spec_from_file_location('previous_harness', base / 'reproduction/run.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
J = h.J
receipt = {
    'scope': 'independent previous-candidate counterexamples; not new-candidate acceptance',
    'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
    'tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=root, text=True).strip(),
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'input_sha256': {str(x.relative_to(root)): hashlib.sha256(x.read_bytes()).hexdigest()
                     for x in sorted((base / 'candidates').glob('*')) if x.suffix in {'.py', '.sql'}},
    'cases': [],
}
for relative in ('reproduction/run.py',):
    x = base / relative
    receipt['input_sha256'][str(x.relative_to(root))] = hashlib.sha256(x.read_bytes()).hexdigest()
for x in sorted((root / 'src/repo_catalog').rglob('*.py')) + sorted((root / 'src/repo_catalog/adapters/sqlite/p1_ddl').glob('*.sql')):
    receipt['input_sha256'][str(x.relative_to(root))] = hashlib.sha256(x.read_bytes()).hexdigest()

def observe(name, fn, error=None):
    db = h.new()
    sql = []
    db.set_trace_callback(sql.append)
    r = {'name': name, 'expected': error.__name__ if error else 'success'}
    try:
        db.execute('BEGIN')
        fn(db)
        db.execute('COMMIT')
        r['actual'] = 'success'
        if error:
            raise AssertionError('missing expected error')
    except Exception as exc:
        r.update(actual=type(exc).__name__, error=str(exc), sqlite_errorname=getattr(exc, 'sqlite_errorname', None))
        if db.in_transaction:
            db.execute('ROLLBACK')
        if error is None or not isinstance(exc, error):
            raise
    finally:
        db.set_trace_callback(None)
        r.update(sql=sql, transaction_after=db.in_transaction, rowsets=h.rows(db), checks=h.check(db))
        assert r['checks'] == {'foreign_key_check': [], 'integrity_check': ['ok']}
        receipt['cases'].append(r)
        db.close()

for value in ['global-document-41', ['space', 'global-document-41']]:
    observe('G1_global_' + ('scalar' if isinstance(value, str) else 'composite'),
            lambda db, v=value: db.execute('INSERT INTO resources VALUES(?,?,?,?,?,?,?)',
                                          (h.S, 'document', J(v), None, None, None, None)), sqlite3.IntegrityError)

def typed(db):
    db.execute('INSERT INTO resources VALUES(?,?,?,?,?,?,?)',
               (h.S, 'document', J(['pull_request', ['project', '7'], 'body', 'D1']),
                'pull_request', J(['project', '7']), 'body', J('D1')))
observe('G1_complete_PR_document_without_parent', typed)

def mismatch(db):
    h.event_resource(db)
    h.resource(db, 'issue', 'I7')
    h.resource(db, 'issue', 'I8')
    p8 = h.parent_row(target='I8', prov=J({'source': 'synthetic://independent', 'evidence': 'I8'}))
    h.rr(db, p8)
    h.admit(db, h.report_row(p8))
observe('G3_I7_identity_I8_parent_and_legacy_admission_succeed', mismatch)

v = ['project', '7']
text_key = J(['pull_request', J(v), 'body', 'D1'])
nested_key = J(['pull_request', v, 'body', 'D1'])
assert text_key != nested_key
assert json.loads(json.loads(text_key)[1]) == v
assert json.loads(nested_key)[1] == v
alias_key = J(['pull_request', J(v), 'body', 'D1'])
assert alias_key == text_key
receipt['G2'] = {
    'parent_native_value': v,
    'parent_canonical_TEXT': J(v),
    'text_component_key': text_key,
    'decoded_component_key': nested_key,
    'same_native_different_keys': text_key != nested_key,
    'both_reverse_to_parent': True,
    'mixed_profile_alias_native_parent': J(v),
    'mixed_profile_alias_key': alias_key,
}
db = h.new()
receipt['runtime'] = {'python': sys.version, 'sqlite_version': sqlite3.sqlite_version,
                      'sqlite_source_id': db.execute('SELECT sqlite_source_id()').fetchone()[0],
                      'compile_options': [r[0] for r in db.execute('PRAGMA compile_options')],
                      'foreign_keys': db.execute('PRAGMA foreign_keys').fetchone()[0],
                      'recursive_triggers': db.execute('PRAGMA recursive_triggers').fetchone()[0]}
db.close()
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({'sqlite': sqlite3.sqlite_version, 'observations': len(receipt['cases']), 'output': str(a.output)}))
