"""Copied-transport counterexamples for the gzip source-binding omission."""
import gzip
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

import audit

ROOT=audit.ROOT
OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('author_classifier',ROOT/'scripts/classify_i6a_regressions.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
original=audit.E/'after-final'
copy=Path(tempfile.mkdtemp(prefix='review-binding-loader-',dir='/workspace'))
for name in ['ordinary.selected.txt.gz','ordinary.xml.gz','ordinary.jsonl.gz','ordinary.report-types.jsonl.gz','ordinary.execution.json','binding-before.json.gz','binding-after.json.gz']:
    shutil.copy2(original/name,copy/name)
results=[]
for label in ['intact','mismatching-after','missing-after']:
    if label=='mismatching-after':
        p=copy/'binding-after.json.gz'
        b=json.loads(gzip.decompress(p.read_bytes()))
        b['tree']='f'*40
        p.write_bytes(gzip.compress(json.dumps(b).encode(),mtime=0))
    elif label=='missing-after':(copy/'binding-after.json.gz').unlink()
    _,author=mod.run_index(copy)
    rejected=None
    try:_,own=audit.receipt(copy)
    except (AssertionError,FileNotFoundError) as e:
        own=None;rejected=type(e).__name__
    results.append({'case':label,'author_consistent':author['consistent'],'author_binding_check_present':'source_bindings_complete_and_unchanged' in author['checks'],'author_bindings':[author['source_binding_before'],author['source_binding_after']],'reviewer_accepted':own is not None,'reviewer_rejection':rejected})
assert results[0]['reviewer_accepted']
assert all(r['author_consistent'] and not r['author_binding_check_present'] for r in results)
assert all(not r['reviewer_accepted'] for r in results[1:])
(OUT/'binding-loader-controls.json').write_text(json.dumps({'scope':'Original evidence untouched; controls alter only separately copied compressed metadata. No test or product invocation occurs.','source':'remediation-20261023/after-final','results':results},indent=2)+'\n')
print(json.dumps(results))
