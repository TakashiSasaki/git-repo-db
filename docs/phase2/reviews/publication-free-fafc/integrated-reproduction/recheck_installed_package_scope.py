"""Independent actual installed CLI scope check after truthful repository import."""
from pathlib import Path
import json
import subprocess

base = Path('/workspace/review-artifacts/fafc1b2d4d2e-packaging-state')
records = []
for variant, relative in [('wheel', 'popen-gw0/test_wheel_sdist_cli_wheel_0'), ('sdist-wheel', 'popen-gw1/test_wheel_sdist_cli_sdist_whe0')]:
    root = base / relative
    cli = root / 'venv/bin/repo-catalog'
    state = root / 'disposable-receiver'
    owner = json.loads((root / 'repository.json').read_text())['repository_uuidv4']
    def query(args):
        command = [str(cli), '--state-dir', str(state), '--format', 'json', *args]
        result = subprocess.run(command, cwd=root / 'outside', capture_output=True, text=True, timeout=120)
        return command, result.returncode, json.loads(result.stdout)
    global_command, global_exit, global_value = query(['search', 'code', '--literal', '認証'])
    scoped_command, scoped_exit, scoped_value = query(['search', 'code', '--repo', owner, '--literal', '認証'])
    check_command, check_exit, check_value = query(['db', 'check', '--full'])
    assert global_exit == 3 and global_value['status'] == 'partial'
    assert scoped_exit == 0 and scoped_value['coverage']['complete_for_requested_scope']
    assert global_value['data']['items'] == scoped_value['data']['items']
    gaps = global_value['coverage']['missing']
    assert gaps and {(gap['kind'], gap['reason']) for gap in gaps} == {('inventory', 'inventory_incomplete')}
    assert check_exit == 0, check_value
    binding = json.loads(subprocess.check_output([str(root / 'venv/bin/python'), '-c', "import json,sqlite3,sys,repo_catalog; from repo_catalog.adapters.sqlite.schema import DDL_SHA256; print(json.dumps(dict(module=repo_catalog.__file__,python=sys.version,sqlite=sqlite3.sqlite_version,ddl=DDL_SHA256.hex())))"], cwd=root / 'outside', text=True))
    assert binding['ddl'] == 'bf6deb09471a361918ab9d9e97ca1ba204060ffc78420972775a914357912f26'
    assert str(root / 'venv') in binding['module']
    records.append({'variant': variant, 'binding': binding, 'repository': owner, 'global_command': global_command, 'global_exit': global_exit, 'global_status': global_value['status'], 'global_gaps': gaps, 'scoped_command': scoped_command, 'scoped_exit': scoped_exit, 'scoped_complete': True, 'same_usable_hit_count': len(scoped_value['data']['items']), 'full_check_command': check_command, 'full_check_exit': check_exit})
print(json.dumps(records, indent=2))
