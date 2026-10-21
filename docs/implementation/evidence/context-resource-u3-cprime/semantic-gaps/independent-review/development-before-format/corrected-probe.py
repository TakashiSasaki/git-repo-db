#!/usr/bin/env python3
"""Independent G1/G2/G3 probes, direct SQL plus explicitly identified admission."""
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
p.add_argument('--freeze', required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
root = a.repo.resolve()
base = root / 'docs/implementation/evidence/context-resource-u3-cprime'
sys.path[:0] = [str(root / 'src'), str(base / 'candidates')]
import cprime as cp  # noqa: E402
spec = importlib.util.spec_from_file_location('frozen_admission', base / 'reproduction/run.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
J = lambda x: json.dumps(x, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
S = '19489678-1234-4234-8234-123456789abc'
S2 = '29489678-1234-4234-8234-123456789abc'
R = '39489678-1234-4234-8234-123456789abc'
CLOCK = {'domain': 'independent-semantic-clock', 'at_us': 501}
PROV = {'source': 'synthetic://independent-semantic', 'evidence': 'original'}
RR = 'service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,members_json,provenance_json,scope_json,observed_at_us'
EP = 'service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us,event_report_members_json,event_report_scope_json'
records = []

assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == a.freeze
manifest = json.loads((base / 'semantic-gaps/input-freeze.json').read_text())
for path, expected in manifest['inputs_sha256'].items():
    assert hashlib.sha256((root/path).read_bytes()).hexdigest() == expected
assert hashlib.sha256(cp.sql().encode()).hexdigest() == manifest['candidate_sql_sha256']

def new():
    db = cp.connect()
    for service in (S, S2):
        db.execute('INSERT INTO providers VALUES(?,?,?)', (service, 'synthetic', '{}'))
    db.execute('INSERT INTO repository_context VALUES(?,?)', (R, '{}'))
    return db


def res(db, kind, raw, extra=(None,)*4, service=S, verb='INSERT'):
    return db.execute(verb + ' INTO resources VALUES(?,?,?,?,?,?,?)', (service, kind, raw, *extra))


def relation(db, row):
    return db.execute(f'INSERT INTO resource_relations({RR}) VALUES(?,?,?,?,?,?,?,?)', row)


def parent(raw, target, subtype=None, kind='document', prov=PROV):
    return (S, kind, raw, 'parent', J([target]), J(prov),
            J({'clock': CLOCK, 'document_kind': subtype, 'state': 'complete'}), None)


def rows(db):
    return {t: [list(r) for r in db.execute(f'SELECT * FROM {t} ORDER BY 1,2,3')]
            for t in ('resources', 'resource_relations', 'resource_repository_relations')}


def attempt(db, label, fn, expected='success'):
    trace = []
    db.set_trace_callback(trace.append)
    r = {'label': label, 'expected': expected, 'transaction_before': db.in_transaction}
    result = None
    try:
        result = fn()
        r['actual'] = 'success'
    except Exception as exc:
        r.update(actual=getattr(exc, 'sqlite_errorname', type(exc).__name__), error=str(exc))
    finally:
        db.set_trace_callback(None)
        r.update(sql=trace, transaction_after=db.in_transaction, rowsets=rows(db),
                 foreign_key_check=[list(x) for x in db.execute('PRAGMA foreign_key_check')],
                 integrity_check=[x[0] for x in db.execute('PRAGMA integrity_check')])
        records.append(r)
    assert r['actual'] == expected, r
    assert not r['foreign_key_check'] and r['integrity_check'] == ['ok']
    return result


db = new()
for native in ('doc-global', ['collection', ['slot', 'nine']], ['pull_request', 'looks', 'like', 'scoped'], '', []):
    raw = J(native)
    extra = cp.document_input('provider_global', raw)
    attempt(db, 'G1 genuine global Document ' + raw, lambda raw=raw, extra=extra: res(db, 'document', raw, extra))
assert not db.execute('SELECT 1 FROM resource_relations').fetchall()
namespace = J(['project', '7'])
pr_raw = J(['pull_request', namespace, 'title', ['document', 'part']])
extra = cp.document_input('pr_scoped', pr_raw, namespace_id=namespace,
                          document_kind='title', document_id=J(['document', 'part']))
attempt(db, 'G1 genuine PR Document before PR', lambda: res(db, 'document', pr_raw, extra))
for label, fn in (
    ('known PR no namespace cannot fallback', lambda: cp.document_input('pr_scoped', J('local'))),
    ('global input cannot discard namespace', lambda: cp.document_input('provider_global', J('local'), namespace_id=namespace)),
    ('global input cannot discard subtype', lambda: cp.document_input('provider_global', J('local'), document_kind='title')),
    ('global input cannot discard local document coordinate', lambda: cp.document_input('provider_global', J('local'), document_id=J('local'))),
    ('unknown selector cannot fallback', lambda: cp.document_input('opaque', J('local'))),
):
    attempt(db, 'G1 admission ' + label, fn, 'ValueError')
for label, raw, metadata in (
    ('all omitted', J('bad-1'), (None,)*4),
    ('wrong independent ID', J('bad-2'), (None, None, None, J('different'))),
    ('partial namespace', J('bad-3'), ('pull_request', None, None, J('bad-3'))),
    ('partial subtype', J('bad-4'), (None, None, 'title', J('bad-4'))),
):
    attempt(db, 'G1 raw SQL malformed ' + label,
            lambda raw=raw, metadata=metadata: res(db, 'document', raw, metadata), 'SQLITE_CONSTRAINT_CHECK')
first = J('doc-global')
second = J(['collection', ['slot', 'nine']])
missing = parent(first, [S, 'issue', J('missing')])
attempt(db, 'G1 missing Parent reaches FK', lambda: relation(db, missing), 'SQLITE_CONSTRAINT_FOREIGNKEY')
res(db, 'issue', J('missing'))
assert not db.execute('SELECT 1 FROM resource_relations').fetchall()
attempt(db, 'G1 Parent supplied later', lambda: relation(db, missing))
other = parent(first, [S, 'issue', J('missing')], prov={'source': 'synthetic://other', 'evidence': 'independent'})
attempt(db, 'G1 same Document independent attribution', lambda: relation(db, other))
attempt(db, 'G1 Document is Parent of Document', lambda: relation(db, parent(second, [S, 'document', first])))
res(db, 'pull_request', namespace)
attempt(db, 'G1 global cannot use PR subtype', lambda: relation(db, parent(first, [S, 'pull_request', namespace], 'title')), 'SQLITE_CONSTRAINT_FOREIGNKEY')
attempt(db, 'G1 PR cannot use independent subtype', lambda: relation(db, parent(pr_raw, [S, 'pull_request', namespace])), 'SQLITE_CONSTRAINT_FOREIGNKEY')
bad_scope = list(parent(first, [S, 'issue', J('missing')]))
bad_scope[6] = J({'clock': CLOCK, 'state': 'complete'})
attempt(db, 'G1 omitted subtype is not explicit independent null', lambda: relation(db, bad_scope), 'SQLITE_CONSTRAINT_CHECK')
res(db, 'issue', J('other-provider'), service=S2)
attempt(db, 'G1 typed Parent cross Provider rejected', lambda: relation(db, parent(first, [S2, 'issue', J('other-provider')])), 'SQLITE_CONSTRAINT_CHECK')
for verb in ('INSERT', 'INSERT OR IGNORE', 'INSERT OR REPLACE'):
    attempt(db, 'G1 cannot rebind independent contract ' + verb,
            lambda verb=verb: res(db, 'document', first, ('pull_request', namespace, 'title', J('doc-global')), verb=verb), 'SQLITE_CONSTRAINT_TRIGGER')
# A native four-coordinate-looking global key stays independent; shape has no authority.
assert cp.document_input('provider_global', J(['pull_request', 'looks', 'like', 'scoped'])) == (None, None, None, J(['pull_request', 'looks', 'like', 'scoped']))
# G2: both native Parent spaces remain distinct under the one selected encoding.
x = new()
v = ['project', '7']
t = J(v)
encoded_a = J(['pull_request', t, 'body', 'D'])
encoded_b = J(['pull_request', J(t), 'body', 'D'])
nested_a = J(['pull_request', v, 'body', 'D'])
assert encoded_a != encoded_b and encoded_a != nested_a
assert json.loads(json.loads(encoded_a)[1]) == v
assert json.loads(json.loads(encoded_b)[1]) == t
attempt(x, 'G2 array-native Parent representation', lambda: res(x, 'document', encoded_a, ('pull_request', t, 'body', J('D'))))
attempt(x, 'G2 canonical-text-native string Parent remains distinct', lambda: res(x, 'document', encoded_b, ('pull_request', J(t), 'body', J('D'))))
attempt(x, 'G2 alternative nested encoding rejected', lambda: res(x, 'document', nested_a, ('pull_request', t, 'body', J('D'))), 'SQLITE_CONSTRAINT_CHECK')
# Mixed profile would collide encoded_a with nested encoding for native t. A changed
# non-key namespace on that existing key must reject before IGNORE conflict handling.
attempt(x, 'G2 mixed-profile alias cannot pass IGNORE', lambda: res(x, 'document', encoded_a, ('pull_request', J(t), 'body', J('D')), verb='INSERT OR IGNORE'), 'SQLITE_CONSTRAINT_TRIGGER')
# G3: complete identity I7, retain I8 attributed report, withhold dependent operation.
y = new()
event = J(['issue', J('I7'), 'timeline_event', 'E-independent'])
res(y, 'comment', event, ('issue', J('I7'), 'timeline_event', J('E-independent')))
res(y, 'issue', J('I7'))
res(y, 'issue', J('I8'))
p8 = parent(event, [S, 'issue', J('I8')], 'timeline_event', kind='comment')
attempt(y, 'G3 retain conflicting I8 attributed Parent', lambda: relation(y, p8))
scope = {'clock': CLOCK, 'event_type': 'transferred', 'from_provider_repository_id': None,
         'to_provider_repository_id': None, 'provided_roles': ['transfer_from_repository'],
         'parent_members_json': p8[4], 'parent_scope_json': p8[6], 'parent_provenance_json': p8[5],
         'endpoints': [['transfer_from_repository', J(R)]]}
report = (S, 'comment', event, 'transfer_event_report', '[]', J(PROV), J(scope), None)
before = rows(y)
attempt(y, 'G3 supported admission withholds unresolved I8', lambda: h.admit(y, report), 'QualificationRequired')
assert rows(y) == before
attempt(y, 'G3 begin structural diagnostic transaction', lambda: y.execute('BEGIN'))
attempt(y, 'G3 direct SQL report has exact I8 support', lambda: relation(y, report))
endpoint = (S, 'comment', event, 'transfer_from_repository', J(R), J(CLOCK), J(PROV), None, '[]', J(scope))
attempt(y, 'G3 direct SQL endpoint has typed I8 support', lambda: y.execute(f'INSERT INTO resource_repository_relations({EP}) VALUES(?,?,?,?,?,?,?,?,?,?)', endpoint))
attempt(y, 'G3 existing raw SQL unit still not qualified on replay', lambda: h.admit(y, report), 'QualificationRequired')
attempt(y, 'G3 rollback structural diagnostic', lambda: y.execute('ROLLBACK'))
assert rows(y) == before
p7 = parent(event, [S, 'issue', J('I7')], 'timeline_event', kind='comment', prov={'source': 'synthetic://I7', 'evidence': 'original'})
relation(y, p7)
scope7 = dict(scope, parent_members_json=p7[4], parent_scope_json=p7[6], parent_provenance_json=p7[5])
r7 = (*report[:6], J(scope7), None)
attempt(y, 'G3 matching previously supported I7 unit admitted', lambda: h.admit(y, r7))
accepted = rows(y)
attempt(y, 'G3 original I7 replay idempotent', lambda: h.admit(y, r7))
assert rows(y) == accepted
output = {'freeze': a.freeze, 'tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=root, text=True).strip(),
          'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'input_manifest': manifest, 'runtime': {'python': sys.version, 'sqlite': sqlite3.sqlite_version,
              'source_id': db.execute('SELECT sqlite_source_id()').fetchone()[0],
              'compile_options': [r[0] for r in db.execute('PRAGMA compile_options')],
              'pragmas': {p: db.execute('PRAGMA ' + p).fetchone()[0] for p in ('foreign_keys', 'recursive_triggers', 'synchronous')}},
          'records': records, 'G2': {'array_parent_key': encoded_a, 'text_native_parent_key': encoded_b, 'rejected_nested_key': nested_a},
          'summary': {'observations': len(records), 'unexpected': 0, 'scope': 'G1/G2 corrected; G3 withholding only, owner semantics unresolved'}}
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps(output['summary']))
