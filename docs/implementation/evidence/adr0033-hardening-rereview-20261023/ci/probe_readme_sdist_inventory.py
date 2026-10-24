"""Compare actual complete sdist source inventory and runtime hash, stdlib only."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from scripts import ci_plan
from scripts.check_sdist_contract import source_inventory
from tests.support.ci_fixture import repository, context, write, commit

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def inventory_digest(rows):
    # Exact check_sdist_contract emitter encoding, including ordinary JSON spaces.
    return sha(json.dumps(rows, sort_keys=True).encode())

with tempfile.TemporaryDirectory(prefix='adr0033-complete-sdist-input-probe-') as temporary:
    root = Path(temporary) / 'fixture'
    initial_base, initial_head = repository(root)
    write(root, '.gitignore', '# no ignored product source\n')
    write(root, 'pyproject.toml', '[project]\nname = "synthetic-sdist-input-probe"\nversion = "0.0.0"\n')
    before_commit = commit(root, 'Complete minimal sdist source fixture')
    before_plan = ci_plan.make_plan(context(root, initial_head, before_commit, event='push'), root=root)
    before_rows = source_inventory(root)
    before_blob = subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD:README.md'], text=True).strip()
    write(root, 'README.md', '# README-only required sdist source edit\n')
    after_commit = commit(root, 'Change only required README source')
    after_plan = ci_plan.make_plan(context(root, before_commit, after_commit, event='push'), root=root)
    after_rows = source_inventory(root)
    after_blob = subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD:README.md'], text=True).strip()
    assert set(before_rows) == set(after_rows) == {'.gitignore','README.md','pyproject.toml','src/repo_catalog/example.py'}
    assert [name for name in before_rows if before_rows[name] != after_rows[name]] == ['README.md']
    assert before_blob != after_blob
    assert before_plan['tree_hash'] != after_plan['tree_hash']
    assert before_plan['acceptance_input_hash'] == after_plan['acceptance_input_hash']
    assert inventory_digest(before_rows) != inventory_digest(after_rows)
    assert after_plan['preparation']['sdist_contract']['disposition'] == 'selected'
    assert after_plan['selected_files'] == []
    result = {
        'kind': 'successful reproduction of distinct runtime and complete-sdist input identities; not build/runtime acceptance',
        'reviewed_head': subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'], text=True).strip(),
        'reviewed_files': {p: sha((ROOT / p).read_bytes()) for p in ['scripts/ci_plan.py','scripts/ci_dependencies.json','scripts/check_sdist_contract.py']},
        'fixture_scope': 'Complete four-file minimal source_inventory fixture. No distribution build is claimed; synthetic metadata is read as bytes by source_inventory.',
        'changed_paths': after_plan['changed'],
        'before': {'readme_blob': before_blob, 'tree_hash': before_plan['tree_hash'], 'acceptance_input_hash': before_plan['acceptance_input_hash'], 'source_inventory_sha256': inventory_digest(before_rows), 'source_files': before_rows},
        'after': {'readme_blob': after_blob, 'tree_hash': after_plan['tree_hash'], 'acceptance_input_hash': after_plan['acceptance_input_hash'], 'source_inventory_sha256': inventory_digest(after_rows), 'source_files': after_rows, 'preparation': after_plan['preparation'], 'selected_files': after_plan['selected_files']},
        'assertions': {'only_readme_source_row_changes': True, 'readme_blob_and_tree_change': True, 'runtime_acceptance_hash_unchanged': True, 'actual_complete_source_inventory_hash_changes': True, 'sdist_gate_selected': True, 'hosted_pytest_not_selected': True},
    }
    print(json.dumps(result, indent=2))
