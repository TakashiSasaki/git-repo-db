"""Verify the review artifact index and every bundled raw-local byte."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent
index=json.loads((ROOT/'artifact-index.json').read_text())
actual={str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts and p.suffix!='.pyc'}
assert actual==set(index['files'])|{'artifact-index.json'}, 'unindexed or missing review artifact'
for name,record in index['files'].items():
    p=ROOT/name
    assert p.is_file() and not p.is_symlink()
    raw=p.read_bytes()
    assert len(raw)==record['bytes'] and hashlib.sha256(raw).hexdigest()==record['sha256'],name
with zipfile.ZipFile(ROOT/'raw-local-evidence.zip') as z:
    assert len(z.namelist())==len(set(z.namelist()))
    inside=json.loads(z.read('receipt-index.json'))
    assert set(z.namelist())==set(inside)|{'receipt-index.json'}
    for name,record in inside.items():
        raw=z.read(name)
        assert len(raw)==record['bytes'] and hashlib.sha256(raw).hexdigest()==record['sha256'],name
print(json.dumps({'indexed_review_files':len(index['files']),'raw_local_payloads':len(inside),'outcome':'passed'}))
