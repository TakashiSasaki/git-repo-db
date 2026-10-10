"""Independent bounded audit of the actual completed fafc scoped receipts."""
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path('/workspace/review-artifacts/final-integrated/final-fafc1b2/scoped-receipt-independent-audit.json')
SHA = 'fafc1b2d4d2e1986768143cc71a0e55cba943ba3'
TREE = '6f566cb3e91e25facda60671c40108e0a9f8965b'
DDL = 'bf6deb09471a361918ab9d9e97ca1ba204060ffc78420972775a914357912f26'
issues = []

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def command(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

def binding(path):
    root = Path(path).parents[2]
    result = {'module_path': str(path), 'head': command(root, 'rev-parse', 'HEAD'),
              'tree': command(root, 'rev-parse', 'HEAD^{tree}'),
              'tracked_status': command(root, 'status', '--short', '--untracked-files=no')}
    if result['head'] != SHA or result['tree'] != TREE or result['tracked_status']:
        issues.append({'binding': result})
    return result

def verify_hashes(base, hashes):
    checked = []
    for name, expected in hashes.items():
        path = Path(name) if Path(name).is_absolute() else base / name
        actual = digest(path) if path.is_file() else None
        checked.append({'path': str(path), 'expected': expected, 'actual': actual})
        if actual != expected:
            issues.append({'artifact_hash_mismatch': str(path)})
    return checked

def xml_summary(path):
    cases = list(ET.parse(path).getroot().iter('testcase'))
    statuses = {'passed': 0, 'failure': 0, 'error': 0, 'skipped': 0}
    nodes = []
    for case in cases:
        status = next((name for name in ('failure', 'error', 'skipped')
                       if case.find(name) is not None), 'passed')
        statuses[status] += 1
        nodes.append({'classname': case.get('classname'), 'name': case.get('name'), 'status': status})
    if any(statuses[name] for name in ('failure', 'error', 'skipped')):
        issues.append({'nonpassing_xml': str(path), 'counts': statuses})
    return {'path': str(path), 'sha256': digest(path), 'case_count': len(cases),
            'statuses': statuses, 'nodes': nodes}

architecture = Path('/workspace/review-artifacts/architecture/final-fafc1b2')
acquisition = Path('/workspace/review-artifacts/acquisition/fafc-final')
domain = Path('/workspace/review-artifacts/domain-qa') / SHA
arch_summary = json.loads((architecture / 'execution-summary.json').read_text())
acq_binding = json.loads((acquisition / 'binding.json').read_text())
domain_manifest = json.loads((domain / 'manifest.json').read_text())
arch_hashes = dict((line.split('  ', 1)[1], line.split('  ', 1)[0])
                   for line in (architecture / 'artifact-sha256.txt').read_text().splitlines())
hashes = {'architecture': verify_hashes(architecture, arch_hashes),
          'acquisition': verify_hashes(acquisition, json.loads((acquisition / 'artifact-sha256.json').read_text())),
          'domain': verify_hashes(domain, domain_manifest['artifact_sha256'])}
bindings = {'architecture': binding(arch_summary['source']),
            'acquisition': binding(acq_binding['import_path']),
            'domain': binding(domain_manifest['module_path'])}
for value in (arch_summary['DDL'], acq_binding['ddl_sha256'], domain_manifest['ddl_sha256']):
    if value != DDL:
        issues.append({'DDL_mismatch': value})
xmls = {
    'architecture': [xml_summary(architecture / record['artifact']) for record in arch_summary['pytest']],
    'acquisition': [xml_summary(acquisition / name) for name in ('fafc-50-results.xml', 'native-pending-results.xml')],
}
domain_log = (domain / 'pytest-combined-66.txt').read_text()
domain_nodes = re.findall(r'^(.+::\S+) PASSED(?: \[.*\])?$', domain_log, re.MULTILINE)
domain_summary = re.search(r'=+\s+(\d+) passed in ([\d.]+)s(?: \([^\n]+\))?\s+=+', domain_log)
if len(domain_nodes) != 66 or len(set(domain_nodes)) != 66 or not domain_summary or domain_summary[1] != '66':
    issues.append({'domain_log_count_mismatch': len(domain_nodes)})
result = {'source': SHA, 'tree': TREE, 'DDL': DDL, 'overall_acceptance': False,
          'purpose': 'Exact scoped receipt, completed case and artifact binding audit; excludes whole failed gates.',
          'bindings': bindings, 'hash_checks': hashes, 'completed_xml_runs': xmls,
          'domain_completed_log': {'sha256': digest(domain / 'pytest-combined-66.txt'),
                                   'case_count': len(domain_nodes), 'nodes': domain_nodes,
                                   'summary_present': domain_summary is not None},
          'issues': issues}
OUT.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'output': str(OUT), 'hashes_checked': {scope: len(records) for scope, records in hashes.items()},
                  'xml_counts': {scope: [record['case_count'] for record in records] for scope, records in xmls.items()},
                  'domain_nodes': len(domain_nodes), 'issues': issues}, indent=2))
