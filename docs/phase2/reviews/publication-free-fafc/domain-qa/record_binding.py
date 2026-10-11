"""Capture frozen source/runtime and fresh collection/map bindings."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import repo_catalog
from repo_catalog.adapters.sqlite.schema import DDL_SHA256

qa = Path(__file__).resolve().parent
root = Path('/workspace/reviews/publication-free-domain-qa-corrected')
node = [line for line in (qa / 'current-ordinary-collection.txt').read_text().splitlines()
        if line.startswith('tests/') and '::' in line]
assert len(node) == len(set(node)) == 2128
(qa / 'current-ordinary-nodes.txt').write_text('\n'.join(node) + '\n')
baseline = Path('/workspace/review-artifacts/domain-qa/b86ff2c96d7558379b2230489e1494630b073ef7/baseline-ordinary-nodes.txt')
(qa / 'baseline-ordinary-nodes.txt').write_bytes(baseline.read_bytes())
actual = json.loads((qa / 'schema-map-actual.json').read_text())
committed = json.loads((root / 'docs/phase2/publication-free-schema-map.json').read_text())
assert actual == committed
cur = actual['current']
binding = {
    'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
    'status': subprocess.check_output(['git', 'status', '--short'], text=True).strip(),
    'runtime': sys.version, 'executable': sys.executable, 'sqlite': sqlite3.sqlite_version,
    'module_path': repo_catalog.__file__, 'ddl_sha256': DDL_SHA256.hex(),
    'schema_map_matches': True,
    'schema_counts': {key: len(cur[key]) for key in ['tables', 'views', 'triggers', 'indexes']},
    'ordinary_collection': len(node),
    'ordinary_node_sha256': hashlib.sha256((qa / 'current-ordinary-nodes.txt').read_bytes()).hexdigest(),
    'baseline_node_sha256': hashlib.sha256((qa / 'baseline-ordinary-nodes.txt').read_bytes()).hexdigest(),
    'model': 'not exposed', 'reasoning_effort': 'not exposed',
}
assert binding['source'] == 'fafc1b2d4d2e1986768143cc71a0e55cba943ba3'
assert binding['tree'] == '6f566cb3e91e25facda60671c40108e0a9f8965b'
assert binding['status'] == ''
assert binding['ddl_sha256'] == 'bf6deb09471a361918ab9d9e97ca1ba204060ffc78420972775a914357912f26'
assert Path(repo_catalog.__file__).is_relative_to(root)
(qa / 'binding.json').write_text(json.dumps(binding, indent=2) + '\n')
print(json.dumps(binding, indent=2))
