"""Read-only re-audit of PR133 source and existing hosted executions."""
import argparse
import base64
import collections
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inputs', type=Path, default=Path(__file__).resolve().parent)
parser.add_argument('--source', type=Path, default=Path('/workspace/pr133-audit'))
parser.add_argument('--evidence', type=Path, default=Path('/workspace/pr133-evidence/docs/implementation/evidence/adr0032-host-runtime-20261022'))
args = parser.parse_args()
HERE, SOURCE, EVIDENCE = args.inputs.resolve(), args.source.resolve(), args.evidence.resolve()
HEAD = 'f16e5b1713bde9a2f18263a25397c4b450fd5773'
TREE = '6bfa580baafa9f6a117b7a0b610c4e65cd031b86'
BASE = 'a022dd3efb9c8116cf9dc0abc13ab1d5bbc88e37'

def sha(b):
    return hashlib.sha256(b).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(SOURCE), *args], text=True).strip()

def checked_zip(raw, index_name='receipt-index.json'):
    z = zipfile.ZipFile(io.BytesIO(raw))
    assert len(z.namelist()) == len(set(z.namelist()))
    idx = json.loads(z.read(index_name))
    assert set(idx) == set(z.namelist()) - {index_name}
    for name, record in idx.items():
        p = Path(name)
        assert not p.is_absolute() and '..' not in p.parts
        data = z.read(name)
        assert record == {'bytes': len(data), 'sha256': sha(data)}, name
    return z

def from_log(name):
    log = (HERE / (name + '.log')).read_text()
    begin = re.findall(r'Z CI_RECEIPTS_BEGIN_V1 ([a-f0-9]{64}) (\d+)\s*$', log, re.M)
    end = re.findall(r'Z CI_RECEIPTS_END_V1 ([a-f0-9]{64})\s*$', log, re.M)
    assert len(begin) == len(end) == 1
    raw = base64.b64decode(''.join(re.findall(r'Z CI_RECEIPTS_DATA_V1 ([A-Za-z0-9+/=]+)\s*$', log, re.M)), validate=True)
    assert sha(raw) == begin[0][0] == end[0]
    assert len(raw) == int(begin[0][1])
    (HERE / (name + '-receipts.zip')).write_bytes(raw)
    return raw, checked_zip(raw)

def junit(raw):
    cases = ET.fromstring(raw).findall('.//testcase')
    counts = collections.Counter()
    failures = {}
    for c in cases:
        key = c.get('classname') + '::' + c.get('name')
        event = next((c.find(t) for t in ('failure', 'error', 'skipped') if c.find(t) is not None), None)
        tag = event.tag if event is not None else 'passed'
        counts[tag] += 1
        if tag in ('failure', 'error'):
            assert key not in failures
            message = event.get('message', '')
            trace = event.text or ''
            frames = re.findall(r'^(tests/[^\n:]+\.py|src/[^\n:]+\.py):(\d+):(?: in (\w+))?', trace, re.M)
            codes = re.findall(r'I2_(?:TRANSFER|IDENTIFICATION_WIRE)_UNSUPPORTED', message + trace)
            failures[key] = dict(phase='teardown' if 'failed on teardown' in message else ('setup' if tag == 'error' else 'call'), message=message, frames=frames, refusal=sorted(set(codes)))
    return dict(counts), failures

def normalized_message(message):
    # Only environment-specific pytest venv prefixes and the observed pytest
    # CompletedProcess repr truncation boundary are normalized. Exception type,
    # traceback body/lines and refusal text remain required to match.
    message = re.sub(r'/tmp/pytest-of-[^\s\x27\x22]+?/venv', '<VENV>', message)
    return message.replace("'-c'...", "'-c...")

assert git('rev-parse', 'HEAD') == HEAD
assert git('rev-parse', 'HEAD^{tree}') == TREE
assert not git('diff', '--name-only', BASE, HEAD, '--', 'src')
assert not git('diff', '--name-only', BASE, HEAD, '--', 'docs/implementation/evidence')
payload = (EVIDENCE / 'payload.zip').read_bytes()
outer_idx = json.loads((EVIDENCE / 'artifact-index.json').read_text())
assert outer_idx['payload'] == {'bytes': len(payload), 'sha256': sha(payload)}
outer = zipfile.ZipFile(io.BytesIO(payload))
assert len(outer.namelist()) == len(set(outer.namelist()))
assert set(outer_idx['members']) == set(outer.namelist())
for name, record in outer_idx['members'].items():
    data = outer.read(name)
    assert record == {'bytes': len(data), 'sha256': sha(data)}, name
inner_checks = {}
for name in outer.namelist():
    if name.endswith('receipts.zip'):
        z = checked_zip(outer.read(name))
        inner_checks[name] = len(z.namelist())
access_raw, access = from_log('access')
tests_raw, tests = from_log('offline')
assert access_raw == outer.read('hosted-f16e5b1/access-receipts.zip')
assert tests_raw == outer.read('hosted-f16e5b1/tests-receipts.zip')
for z, run_id in [(access, '39799299209'), (tests, '39799299296')]:
    binding = json.loads(z.read('receipt-binding.json'))
    assert binding['tree'] == TREE and binding['run_id'] == run_id and binding['run_attempt'] == '1'
    assert git('rev-parse', binding['head'] + '^{tree}') == TREE

prefix = 'artifacts/access-registry/'
original_counts, original_fail = junit(access.read(prefix + 'tests.xml'))
broad_counts, broad_fail = junit(access.read(prefix + 'i5/regressions.xml'))
assert original_fail.keys() == broad_fail.keys()
original_message_differences = []
for node, old in original_fail.items():
    new = broad_fail[node]
    for field in ('phase', 'frames', 'refusal'):
        assert old[field] == new[field], (node, field)
    if old['message'] != new['message']:
        assert normalized_message(old['message']) == normalized_message(new['message']), node
        original_message_differences.append({'node':node, 'original':old['message'], 'broad':new['message']})
(HERE/'original-broad-message-differences.json').write_text(json.dumps(original_message_differences,indent=2)+'\n')
baseline_path = SOURCE / 'docs/implementation/evidence/sqlite-validation-policy-20261022/payload.zip'
with zipfile.ZipFile(baseline_path) as z:
    baseline_raw = z.read('run-3594f47/i5/regressions.xml')
_, baseline_fail = junit(baseline_raw)
assert len(baseline_fail) == len(broad_fail) == 79
assert baseline_fail.keys() == broad_fail.keys()
message_differences = []
for node, old in baseline_fail.items():
    new = broad_fail[node]
    for field in ('phase', 'frames', 'refusal'):
        assert old[field] == new[field], (node, field)
    if old['message'] != new['message']:
        assert normalized_message(old['message']) == normalized_message(new['message']), node
        message_differences.append({'node': node, 'baseline': old['message'], 'current': new['message']})
failure_groups = collections.Counter((v['phase'], ','.join(v['refusal'])) for v in broad_fail.values())
(HERE / 'message-differences.json').write_text(json.dumps(message_differences, indent=2) + '\n')

runtime_names = [n for n in access.namelist() if (n.startswith('artifacts/runtime/') or n.endswith('-runtime-binding.json')) and n.endswith('.json')]
reference = json.loads(access.read('artifacts/runtime/selected.json'))
fields = ('base_executable', 'sqlite_version', 'sqlite_source_id', 'sqlite_module', 'sqlite_module_sha256', 'compile_options', 'sqlite_mappings')
for name in runtime_names:
    r = json.loads(access.read(name))
    assert all(r[f] == reference[f] for f in fields)
    assert not any(r['loader_environment'].values())
    assert r['product_safety_and_capabilities'] == 'passed'
    if 'wheel' in name or '-runtime-binding' in name:
        assert '/site-packages/' in r['product_module']
assert len(runtime_names) == 8

dist_prefix = prefix + 'i5-distribution/'
build = json.loads(access.read(dist_prefix + 'build-binding.json'))
dist_summary = json.loads(access.read(dist_prefix + 'summary.json'))
dist_results = {}
for tag, wheel_key in [('direct', 'direct_wheel'), ('sdist', 'sdist_wheel')]:
    runtime = json.loads(access.read(dist_prefix + tag + '-runtime.json'))
    assert '/site-packages/' in runtime['origin']
    assert runtime['sqlite'] == [reference['sqlite_version'], reference['sqlite_source_id']]
    requirements = access.read(dist_prefix + tag + '-requirements.txt').decode()
    assert build[wheel_key]['sha256'] in requirements
    records = {r['name']: r for r in dist_summary['processes'] if r['name'].startswith(tag + '-')}
    assert all(r['exit_code'] == (1 if n.endswith('-access') else 0) for n, r in records.items())
    assert all(arg in records[tag+'-install']['argv'] for arg in ('--offline', '--no-index', '--no-deps', '--require-hashes'))
    i4, _ = junit(access.read(dist_prefix + tag + '-i4.xml'))
    i5, _ = junit(access.read(dist_prefix + tag + '-i5.xml'))
    assert i4 == {'passed':217} and i5 == {'passed':29}
    assert 'I2_TRANSFER_UNSUPPORTED' in access.read(dist_prefix + tag + '-access.log').decode()
    dist_results[tag] = dict(wheel=build[wheel_key], i4=i4, i5=i5, steps={n:r['exit_code'] for n,r in records.items()}, installed_files=len(runtime['installed_files']))
direct = json.loads(access.read(dist_prefix + 'direct-runtime.json'))['installed_files']
sdist = json.loads(access.read(dist_prefix + 'sdist-runtime.json'))['installed_files']
assert direct == sdist
source_files = {str(p.relative_to(SOURCE/'src/repo_catalog')): sha(p.read_bytes()) for p in (SOURCE/'src/repo_catalog').rglob('*') if p.is_file() and p.suffix in ('.py','.sql','.json')}
assert source_files == direct

runs = {}
steps_report = []
for name in ('access', 'tests'):
    run = json.loads((HERE / (name + '-run.json')).read_text())
    assert run['status'] == 'completed' and run['head_sha'] == HEAD and run['run_attempt'] == 1
    jobs = json.loads((HERE / (name + '-jobs.json')).read_text())['jobs']
    runs[name] = {k:run[k] for k in ('id','status','conclusion','head_sha','run_attempt')}
    for job in jobs:
        for step in job['steps']:
            outcome = step['conclusion']
            # REST provides conclusions, not numeric job/action exit codes.
            # Only failed run-step code1 is explicit in raw logs. Success0 is
            # inferred from Actions outcome; skipped/non-process has no code.
            run_steps = {'registry-runtime': set(range(5,20)), 'offline': {5,6,7,8,10,11,12,16,17}, 'sqlite-policy': {4,5,6}}
            is_run = step['number'] in run_steps[job['name']]
            code = 1 if outcome == 'failure' else (0 if outcome == 'success' and is_run else None)
            steps_report.append(dict(run=run['id'], job=job['name'], job_conclusion=job['conclusion'], number=step['number'], name=step['name'], conclusion=outcome, exit_code=code, exit_code_basis='explicit log' if code==1 else ('Actions success inference' if code==0 else 'not exposed / no process')))
assert len(re.findall(r'##\[error\]Process completed with exit code 1\.', (HERE/'access.log').read_text())) == 5
(HERE/'steps.json').write_text(json.dumps(steps_report, indent=2)+'\n')
summary = dict(source_head=HEAD, source_tree=TREE, base=BASE, product_source_unchanged=True, prior_frozen_evidence_unchanged=True, runs=runs,
    payload_sha256=sha(payload), outer_members=len(outer.namelist()), inner_indices=inner_checks,
    fresh_log_receipts={'access':sha(access_raw),'tests':sha(tests_raw)},
    original=original_counts, broad=broad_counts,
    failure_comparison=dict(nodes=79,added=0,resolved=0,phases_refusals_full_frames_identical=True,message_differences=len(message_differences),messages_equal_after_only_pytest_temp_venv_and_repr_truncation_normalization=True, groups=[dict(phase=k[0],refusal=k[1],count=v) for k,v in failure_groups.items()]),
    runtime={k:reference[k] for k in ('python','sqlite_version','sqlite_source_id','base_executable','sqlite_module_origin','sqlite_module_sha256','product_safety_and_capabilities')}, runtime_receipts=len(runtime_names),
    installed_files_match_source=True,distributions=dist_results,distribution_build_binding=build,
    coverage=json.loads(outer.read('coverage-reconciliation.json')),
    limits=['Existing hosted execution and installed environments audited from raw receipts; no product tests rerun by this audit.', 'New local stdlib 35-test run is tool-only and does not claim local product safety acceptance.', 'Four subprocess assertion messages have pytest temporary venv path and repr truncation differences; retained and normalized comparison passes.', 'Numeric exit codes for successful run steps inferred from Actions conclusion; action/job exit codes not exposed by REST.'])
(HERE/'audit-results.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:summary[k] for k in ('source_head','source_tree','outer_members','original','broad','failure_comparison','runtime_receipts','installed_files_match_source')},indent=2))
