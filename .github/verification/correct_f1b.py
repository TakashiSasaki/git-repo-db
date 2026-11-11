"""Add exact digest length and its paired SQLite/graph counterexample."""
from pathlib import Path
import hashlib
import json

here = Path.cwd() / 'tools/schema-model'
def replace_once(name, old, new):
    p = here / name
    text = p.read_text()
    assert text.count(old) == 1, (name, old)
    p.write_text(text.replace(old, new, 1))
replace_once('instance_shapes.ttl', 'sh:datatype xsd:string; sh:pattern "^[0-9a-f]{64}$"',
             'sh:datatype xsd:string; sh:minLength 64; sh:maxLength 64; sh:pattern "^[0-9a-f]{64}$"')
replace_once('hash_profile.py', '        "short_digest": {"sha256": "a" * 63},',
             '        "short_digest": {"sha256": "a" * 63},\n        "trailing_newline_digest": {"sha256": "a" * 64 + "\\n"},')
replace_once('test_hash_model.py', 'self.assertEqual(len(api["hash_sqlite_rejections"]), 13)',
             'self.assertEqual(len(api["hash_sqlite_rejections"]), 14)')
replace_once('test_hash_model.py', 'for digest in (None, "", "a" * 63, "g" * 64, "A" * 64):',
             'for digest in (None, "", "a" * 63, "g" * 64, "A" * 64, "a" * 64 + "\\n"):')
replace_once('INSTANCE-PILOT.md', 'Thirteen SQLite invalid-tuple controls run with guards enabled.',
             'Fourteen SQLite invalid-tuple controls run with guards enabled. Explicit\nlength constraints reject a trailing newline even when the pattern engine\naccepts its end anchor before that newline.')
p = here / 'instance_constraints.json'
manifest = json.loads(p.read_text())
manifest['shapes_sha256'] = hashlib.sha256((here / 'instance_shapes.ttl').read_bytes()).hexdigest()
p.write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'shapes_sha256': manifest['shapes_sha256']}))
