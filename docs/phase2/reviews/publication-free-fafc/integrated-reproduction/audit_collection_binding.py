"""Check exact raw ordinary collection against dispositions and actual CI plan."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--repo', type=Path, required=True)
parser.add_argument('--sha', required=True)
parser.add_argument('--raw', type=Path, required=True)
parser.add_argument('--plan', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
def git(path):
    return subprocess.check_output(['git', '-C', str(args.repo), 'show', args.sha + ':' + path])
mapping = json.loads(git('tests/support/publication_free_node_dispositions.json'))
raw = args.raw.read_bytes()
current = raw.decode().splitlines()
plan = json.loads(args.plan.read_text())
selected = plan['lanes']['tests']['test_ids']
baseline = git('tests/support/publication_free_baseline_nodes.txt')
old = baseline.decode().splitlines()
mapped = [entry['baseline_node'] for entry in mapping['entries']]
same = mapping['still_collected_same_nodes']
replacements = {node for entry in mapping['entries'] for node in entry['replacement_nodes']}
assert len(current) == len(set(current)) == mapping['current_collected_count']
assert len(old) == len(set(old)) == mapping['baseline_collected_count']
assert set(mapped).isdisjoint(same)
assert set(mapped + same) == set(old)
assert hashlib.sha256(raw).hexdigest() == mapping['node_list_sha256']['current']
assert hashlib.sha256(baseline).hexdigest() == mapping['node_list_sha256']['baseline']
assert set(replacements).issubset(current)
assert set(same).issubset(current)
assert sorted(current) == sorted(selected)
assert plan['full'] and not plan['excluded_files'] and not plan['unexecuted_files']
removed = sorted({node.split('[', 1)[0] for node in old} - {node.split('[', 1)[0] for node in current})
assert removed == mapping['removed_or_renamed_baseline_functions']
record = {
    'sha': args.sha, 'plan_tested_sha': plan['context']['tested_sha'],
    'raw_file': str(args.raw), 'raw_sha256': hashlib.sha256(raw).hexdigest(),
    'baseline_count': len(old), 'explicit_count': len(mapped), 'same_ids_count': len(same),
    'removed_or_renamed_functions': len(removed), 'ordinary_count': len(current),
    'package_count': len(plan['lanes']['packaging']['test_ids']),
    'collection_exact': True, 'mapped_replacements_all_selected': True,
    'excluded_files': plan['excluded_files'], 'unexecuted_files': plan['unexecuted_files'],
    'limitation': 'Collection and disposition accounting are not evidence of behavior equivalence or execution',
}
args.output.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
