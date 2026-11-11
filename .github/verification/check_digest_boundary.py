"""Run a source-bound trailing-newline counterexample; no product imports."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / 'tools/schema-model'))
from instance_model import validate, value

data = json.loads(Path(sys.argv[1]).read_text())
data['profile'] = 'values'
data['scope'] = 'synthetic trailing-newline digest counterexample; not product admission'
key = data['hash_cases']['complete']
row = next(r for r in data['tables']['filesystem']['entries']
           if [value(r['namespace_uuid']), value(r['scan_uuid']), value(r['relative_path']).hex()] == key)
row['sha256'] = {'type': 'text', 'value': 'a' * 64 + '\n'}
result = validate(data, Path(sys.argv[2]))
status = result['families']['data_conformance']['status']
print(json.dumps({'observed_status': status, 'expected_status': sys.argv[3],
                 'source_commit': result.get('source', {}).get('source_commit'),
                 'tool_commit': result.get('tool', {}).get('commit')}))
assert status == sys.argv[3], status
