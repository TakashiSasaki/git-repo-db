"""Seal only this reviewer's outside-repository final artifacts."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


qa = Path(__file__).resolve().parent
root = Path('/workspace/reviews/publication-free-domain-qa-corrected')
old = qa.parent / 'b86ff2c96d7558379b2230489e1494630b073ef7'
binding = json.loads((qa / 'binding.json').read_text())
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == binding['source']
assert subprocess.check_output(['git', 'status', '--short'], cwd=root, text=True) == ''
passed = (qa / 'pytest-combined-66.txt').read_text()
assert 'collected 66 items' in passed and '66 passed' in passed
assert '\nFAILED ' not in passed and '\nERROR ' not in passed
assert sum(' PASSED [' in line for line in passed.splitlines()) == 66

preservation = {}
for directory, metadata in [
    (old, old / 'metadata.json'),
    (qa.parent, qa.parent / 'metadata-final-initial-cafa8a8b143fe095b79f282690a6edf98e6f660e.json'),
]:
    recorded = json.loads(metadata.read_text())['artifact_sha256']
    check = {name: sha(directory / name) == digest for name, digest in recorded.items()}
    assert all(check.values()), [name for name, result in check.items() if not result]
    preservation[str(metadata)] = {'metadata_sha256': sha(metadata), 'checked_files': len(check), 'all_recorded_hashes_unchanged': True}

copied = {name: sha(qa / name) == sha(old / name) for name in [
    'test_independent_domain_qa.py', 'test_corrected_crossmod.py', 'test_corrected_code_proof.py',
    'selected_pending_scale.py', 'git_authorization_scale.py',
]}
assert all(copied.values())
coverage_before = (old / 'selected_coverage_scale.py').read_text()
coverage_after = (qa / 'selected_coverage_scale.py').read_text()
assert coverage_after == coverage_before.replace(old.name, qa.name)
copied['selected_coverage_scale.py'] = 'only exact-commit output directory substitution'

for source in [
    'docs/phase2/publication-free-schema-map.json',
    'docs/phase2/publication-free-test-disposition.json',
    'tests/support/publication_free_node_dispositions.json',
    'tests/support/schema20_contract_replacements.json',
]:
    shutil.copyfile(root / source, qa / Path(source).name)

measurements = {}
for label in ['selected-coverage-scale', 'selected-pending-scale', 'git-authorization-scale']:
    result = json.loads((qa / f'{label}-{qa.name}.json').read_text())
    assert result['source'] == binding['source'] and result['tree'] == binding['tree']
    assert result['repo_catalog'] == binding['module_path']
    measurements[label] = result['measurements']

removed = []
for directory in [qa / 'disposable-correctness', *qa.glob('pending-scale-*'), *qa.glob('authorization-scale-*'), qa / '__pycache__']:
    if directory.is_dir():
        removed.append(str(directory))
        shutil.rmtree(directory)

source_paths = subprocess.check_output(['git', 'ls-files', 'src/repo_catalog'], cwd=root, text=True).splitlines()
source_hashes = {name: sha(root / name) for name in source_paths}
unchanged_paths = [
    'src/repo_catalog/adapters/sqlite/cas_integrity.py',
    'src/repo_catalog/adapters/sqlite/payloads.py',
    'src/repo_catalog/adapters/sqlite/store.py',
    'src/repo_catalog/adapters/sqlite/transactions.py',
    'src/repo_catalog/application/maintenance_service.py',
    'src/repo_catalog/resources/cas_integrity.sql',
    'src/repo_catalog/domain/git_intrinsic.py',
    'src/repo_catalog/adapters/sqlite/current_collections.py',
]
old_sources = json.loads((old / 'metadata.json').read_text())['source_file_sha256']
unchanged = {}
for name in unchanged_paths:
    original_bytes = subprocess.check_output(['git', 'show', f'{old.name}:{name}'], cwd=root)
    original_sha = hashlib.sha256(original_bytes).hexdigest()
    assert original_sha == source_hashes[name]
    if name in old_sources:
        assert original_sha == old_sources[name]
    unchanged[name] = original_sha

manifest = {
    **binding, 'schema_version': 20, 'production_authorship': False,
    'independent_node_count': 66, 'coherent_fresh_execution': True,
    'test_result': '66 passed, exit 0, no skips or deselections',
    'scope_findings': {f'D{i}': 'resolved by actual exact-final rerun' for i in range(1, 7)},
    'prior_scope3_findings': {'tree_entry_NUL_boundary': 'passing in final coherent suite', 'selected_same_scope_coverage_history': 'passing exact-final sequential work count'},
    'controlled_workloads_order': ['selected coverage history', 'selected pending history', 'selected authorization volume'],
    'measurements': measurements,
    'exclusive_wall_time_or_throughput_claim': False,
    'overall_acceptance': False,
    'limits': ['Complete ordinary execution, lint/format, package execution and hosted CI belong to parent/final verifier.', 'No native SQLite 3.45.1 execution, authenticated/live acquisition, snapshot concurrency or full selected-volume CLI benchmark by this reviewer.', 'Full integrated diff preserved but not wholly read line by line; manual scope limits in receipt.'],
    'copied_script_equivalence': copied,
    'original_artifact_preservation': preservation,
    'b86_equal_source_files': unchanged,
    'source_file_sha256': source_hashes,
    'removed_synthetic_fixture_directories': removed,
    'artifact_sha256': {str(p.relative_to(qa)): sha(p) for p in sorted(qa.rglob('*')) if p.is_file() and p.name != 'manifest.json'},
}
(qa / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'source': binding['source'], 'nodes': 66, 'source_files': len(source_hashes), 'artifacts': len(manifest['artifact_sha256']), 'original_preservation': preservation, 'removed_synthetic_fixtures': removed}, indent=2))
