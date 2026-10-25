"""Read-only independent audit. Writes only beside this script; stdlib only."""
import base64
from collections import Counter
import fnmatch
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
sys.path.insert(0, str(ROOT))
from scripts import ci_plan
from scripts.compare_i5_failures import index, compare

HEAD = '59307c40ea65554736e131cedd00f04c9906551b'
TREE = '5ea93707d62b542c84632515392ac6a35c36cd65'
MERGE = 'e0c60765bd0d99b8276a8d0528dabfa7f4d6971a'
commands = []
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')
def command(args):
    proc = subprocess.run(args, cwd=ROOT, capture_output=True)
    commands.append({'argv': args, 'cwd': str(ROOT), 'exit_code': proc.returncode,
                     'stdout_bytes': len(proc.stdout), 'stdout_sha256': sha(proc.stdout),
                     'stderr': proc.stderr.decode(errors='replace')})
    assert proc.returncode == 0, args
    return proc.stdout
def api(path, name):
    data = json.loads(command(['gh','api', 'repos/TakashiSasaki/git-repo-db/' + path]))
    save(name, data)
    return data
def decode(tag, logname, run):
    raw = (OUT / (logname + '.log')).read_bytes() if (OUT / (logname + '.log')).exists() else gzip.decompress((OUT / (logname + '.log.gz')).read_bytes())
    log = raw.decode()
    starts = list(re.finditer(r'^\S+ CI_RECEIPTS_BEGIN_V1 ([0-9a-f]{64}) (\d+)\s*$', log, re.M))
    assert len(starts) == 1
    start = starts[0]
    digest, length = start.group(1), int(start.group(2))
    tail = log[start.end():]
    ends = list(re.finditer(r'^\S+ CI_RECEIPTS_END_V1 ([0-9a-f]{64})\s*$', tail, re.M))
    assert len(ends) == 1 and ends[0].group(1) == digest
    payload = base64.b64decode(''.join(re.findall(r'^\S+ CI_RECEIPTS_DATA_V1 ([A-Za-z0-9+/=]+)\s*$', tail[:ends[0].start()], re.M)), validate=True)
    assert len(payload) == length and sha(payload) == digest
    (OUT / (tag + '-receipts.zip')).write_bytes(payload)
    archive = zipfile.ZipFile(io.BytesIO(payload))
    names = archive.namelist()
    assert len(names) == len(set(names))
    for name in names:
        assert not name.startswith('/') and '..' not in Path(name).parts
    receipt_index = json.loads(archive.read('receipt-index.json'))
    assert set(receipt_index) == set(names) - {'receipt-index.json'}
    for name, expected in receipt_index.items():
        value = archive.read(name)
        assert len(value) == expected['bytes'] and sha(value) == expected['sha256']
    binding = json.loads(archive.read('receipt-binding.json'))
    assert binding['head'] == MERGE and binding['tree'] == TREE
    assert binding['run_id'] == str(run) and binding['run_attempt'] == '1'
    return archive, {'log_bytes': len(raw), 'log_sha256': sha(raw), 'receipt_bytes': length,
                     'receipt_sha256': digest, 'indexed_members_verified': len(receipt_index),
                     'binding': binding, 'members': names}
def jread(z, name):
    return json.loads(z.read(name))
def nodes(z, name):
    return [x for x in z.read(name).decode().splitlines() if x.startswith('tests/') and '::' in x]
def cases(z, name):
    return ET.fromstring(z.read(name)).findall('.//testcase')
def junit_node(case):
    classname = case.get('classname')
    # JUnit file is the definition source for imported/replayed tests; the
    # collection module in classname is the actual selected node's identity.
    parts = classname.split('.')
    split = next((i for i,p in enumerate(parts) if p.startswith('test_')), len(parts)-1) + 1
    file = '/'.join(parts[:split]) + '.py'
    classes = '::'.join(parts[split:])
    return file + '::' + (classes + '::' if classes else '') + case.get('name')
def counts(xml_cases):
    return {'total': len(xml_cases), 'failed': sum(c.find('failure') is not None for c in xml_cases),
            'error': sum(c.find('error') is not None for c in xml_cases),
            'skipped': sum(c.find('skipped') is not None for c in xml_cases)}

def main():
    result = {'scope': 'Independent read-only CI receipt and input audit; no test rerun or release validation'}
    assert command(['git','rev-parse','HEAD']).decode().strip() == HEAD
    assert command(['git','rev-parse','HEAD^{tree}']).decode().strip() == TREE
    tests, tr = decode('tests', 'tests-offline', 39892052621)
    access, ar = decode('access', 'access-registry', 39892052634)
    save('receipt-verification.json', {'tests': tr, 'access': ar})
    runs = {}
    for tag, run, expected in [('tests',39892052621,'success'), ('access',39892052634,'failure')]:
        value = api(f'actions/runs/{run}', tag + '-run-live.json')
        assert value['status'] == 'completed' and value['conclusion'] == expected
        assert value['head_sha'] == HEAD and value['run_attempt'] == 1
        runs[tag] = {k: value[k] for k in ['id','status','conclusion','head_sha','run_attempt','event','html_url','updated_at']}
    merge = api('git/commits/' + MERGE, 'test-merge-commit-live.json')
    feature = api('git/commits/' + HEAD, 'feature-commit-live.json')
    assert merge['tree']['sha'] == feature['tree']['sha'] == TREE
    assert HEAD in [p['sha'] for p in merge['parents']]
    result['authoritative_runs'] = runs
    result['feature_test_merge_effective_tree_verified'] = True
    plan = jread(tests, 'plan.json')
    manifest = jread(tests, 'validation-manifest.json')
    assert plan['context'] == manifest['context']
    assert plan['context']['tested_sha'] == MERGE and plan['context']['feature_sha'] == HEAD
    entries = ci_plan.tree(ROOT, HEAD)
    rules = ci_plan.policy(ROOT)
    files = ci_plan.acceptance_files(entries, rules)
    recalculated = {
        'tree_hash': ci_plan.digest(entries),
        'policy_hash': ci_plan.digest({p: entries.get(p) for p in rules['policy_inputs']}),
        'acceptance_input_hash': ci_plan.digest({p: e for p,e in entries.items() if p in files or ci_plan.matches(p, rules['shared_inputs'] + rules['executable_inputs']) or not ci_plan.matches(p, rules['prose'] + rules.get('report_inputs', []))})}
    for key, value in recalculated.items():
        assert plan[key] == value
    assert manifest['acceptance_input_hash'] == recalculated['acceptance_input_hash']
    assert manifest['tree_sha'] == TREE and manifest['full_acceptance'] is False
    result['tests'] = {'recomputed_input_hashes': recalculated,
        'acceptance_status': manifest['acceptance_status'], 'full_acceptance': manifest['full_acceptance'],
        'evidence_status': manifest['evidence_status'],
        'coverage': {k: len(v) if isinstance(v,list) else v for k,v in manifest['coverage'].items()},
        'preparation': plan['preparation'], 'changed': plan['changed'],
        'note': 'executed=0 describes planned pytest lanes; independent sqlite-policy unittest checks did execute'}
    input_maps = {}
    for name in access.namelist():
        if not name.endswith('.json'):
            continue
        data = jread(access,name)
        if not isinstance(data,dict):
            continue
        if name.endswith(('inputs-before.json','inputs-after.json')):
            candidates = data
        elif name.endswith('/input-binding.json'):
            assert data['head'] == MERGE and data['tree'] == TREE
            candidates = data['inputs']
        elif name.endswith('/binding.json') and 'files' in data:
            assert data['head'] == MERGE and data['tree'] == TREE
            candidates = data['files']
        else:
            continue
        for path, expected in candidates.items():
            local_path = path.removeprefix('/home/runner/work/git-repo-db/git-repo-db/')
            actual = sha((ROOT / local_path).read_bytes())
            assert expected == actual, (name,path,expected,actual)
        input_maps[name] = len(candidates)
    sdist = jread(access, 'artifacts/access-registry/i5-distribution/sdist-contract.json')
    for path, expected in sdist['source_files'].items():
        raw = (ROOT / path).read_bytes()
        assert len(raw) == expected['bytes'] and sha(raw) == expected['sha256']
    assert sha(json.dumps(sdist['source_files'], sort_keys=True).encode()) == sdist['source_inventory_sha256']
    result['access_source_hash_verification'] = {'input_maps': input_maps,
        'sdist_source_files': len(sdist['source_files']), 'source_inventory_sha256': sdist['source_inventory_sha256']}
    xml = 'artifacts/access-registry/i5/regressions.xml'
    broad_cases = cases(access, xml)
    focused_cases = cases(access, 'artifacts/access-registry/tests.xml')
    broad_nodes = [junit_node(c) for c in broad_cases]
    focus_nodes = [junit_node(c) for c in focused_cases]
    selected = nodes(access, 'artifacts/access-registry/i5/regressions.selected.txt')
    assert Counter(selected) == Counter(broad_nodes)
    journal = [json.loads(x) for x in access.read('artifacts/access-registry/i5/regressions.jsonl').decode().splitlines()]
    starts = [e['nodeid'] for e in journal if e['event'] == 'start']
    assert Counter(starts) == Counter(selected)
    finishes = [e for e in journal if e['event'] == 'finish']
    assert len(finishes) == 1 and finishes[0]['exitstatus'] == 1 and finishes[0]['status'] == 'failed'
    ordinary = set(nodes(access, 'artifacts/access-registry/i5/ordinary-collection.nodes.txt'))
    executed = set(broad_nodes) | set(focus_nodes)
    missing = sorted(ordinary - executed)
    (OUT / 'access-unexecuted-ordinary-nodeids.txt').write_text('\n'.join(missing) + '\n')
    baseline_path = ROOT / 'docs/implementation/evidence/adr0031-i4/author-evidence.zip'
    with zipfile.ZipFile(baseline_path) as baseline:
        baseline_xml = baseline.read('author-3.51.3/regressions.xml')
    comparison = compare(index(baseline_xml),index(access.read(xml)))
    assert comparison['same_nodes'] and comparison['baseline_non_successes'] == 79
    assert all(c['same_phase'] and c['same_stage_refusal'] and c['same_trace_paths_functions'] for c in comparison['comparison'])
    comparison['baseline_archive_sha256'] = sha(baseline_path.read_bytes())
    comparison['baseline_entry'] = 'author-3.51.3/regressions.xml'
    comparison['current_sha256'] = sha(access.read(xml))
    save('independent-inherited-failure-comparison.json', comparison)
    result['access_test_execution'] = {'focused': counts(focused_cases), 'broad': counts(broad_cases),
        'broad_exact_selected_junit_journal_nodes_verified': True,
        'focused_broad_overlap': len(set(focus_nodes) & set(broad_nodes)),
        'ordinary_inventory': len(ordinary), 'executed_unique_ordinary': len(ordinary & executed),
        'unexecuted_ordinary_after_union': len(missing),
        'inherited_failures': {k:comparison[k] for k in ['baseline_non_successes','current_non_successes','same_nodes','resolved','additional']},
        'xml_cohorts': {p: counts(cases(access,p)) for p in access.namelist() if p.endswith('.xml')}}
    distribution = jread(access,'artifacts/access-registry/i5-distribution/build-binding.json')
    assert distribution['head'] == MERGE and distribution['tree'] == TREE
    assert distribution['direct_wheel'] == distribution['sdist_wheel']
    assert distribution['sdist']['sha256'] == sdist['sha256']
    result['distribution'] = {'binding': distribution,
        'processes': jread(access, 'artifacts/access-registry/i5-distribution/summary.json')['processes'],
        'limitation': 'Artifact binary blobs are not in the emitted receipt ZIP; their reported hashes agree, but were not independently rehashed from downloaded wheel/sdist binaries in this CI audit. Source inventory and all receipt bytes were independently rehashed.'}
    paths = ['.github/workflows/pages.yml','scripts/build_docs_site.py','scripts/schema_viz.py','mkdocs.yml']
    old = 'ef3ca118d4ab5e52dc2d1c7de384c3557509add2'
    unchanged = {}
    for path in paths:
        before = command(['git','show',old+':'+path])
        after = (ROOT / path).read_bytes()
        assert before == after
        unchanged[path] = sha(after)
    diff = command(['git','diff','--name-only',old,HEAD]).decode().splitlines()
    result['pages'] = {'key_inputs_unchanged_from_PR142_base': unchanged, 'changed_paths': diff,
        'note': 'No pages run for final HEAD in authoritative commit workflow enumeration. PR142 change paths miss existing publication/build trigger allowlist. Access ran build_docs_site.py --no-mermaid successfully; this is placeholder-diagram build evidence, not a full Pages run or deployment.'}
    result['runtime'] = {'tests': plan['runtime'], 'access_runtime_paths': {p:jread(access,p) for p in access.namelist() if p.startswith('artifacts/runtime/') and p.endswith('.json')}}
    save('independent-audit.json', result)
    save('command-records.json', commands)
    print(json.dumps({'verified':True,'tests':result['tests']['acceptance_status'], 'access':runs['access']['conclusion'], 'execution':result['access_test_execution']},indent=2))

if __name__ == '__main__':
    try:
        main()
    finally:
        save('command-records.json', commands)
