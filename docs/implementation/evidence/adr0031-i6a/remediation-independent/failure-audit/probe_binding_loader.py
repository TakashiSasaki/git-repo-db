"""Counterexample for the shipped classifier's compressed source-binding loader."""
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[5]
spec=importlib.util.spec_from_file_location('author_classifier',ROOT/'scripts/classify_i6a_regressions.py')
classifier=importlib.util.module_from_spec(spec)
spec.loader.exec_module(classifier)
base=ROOT/'docs/implementation/evidence/adr0031-i6a/remediation-20261023'
rows=[]
for name in ['before','after-final']:
    index,receipt=classifier.run_index(base/name)
    rows.append({'directory':name,'compressed_before_exists':(base/name/'binding-before.json.gz').exists(),'compressed_after_exists':(base/name/'binding-after.json.gz').exists(),'source_binding_before':receipt['source_binding_before'],'source_binding_after':receipt['source_binding_after'],'binding_check_present':'source_bindings_complete_and_unchanged' in receipt['checks'],'consistent_reported':receipt['consistent'],'selected':receipt['selected']})
assert all(r['compressed_before_exists'] and r['compressed_after_exists'] and r['source_binding_before'] is None and r['source_binding_after'] is None and not r['binding_check_present'] and r['consistent_reported'] for r in rows)
(HERE/'binding-loader-counterexample.json').write_text(json.dumps({'target':'scripts/classify_i6a_regressions.py:109-115','execution':'Independent invocation of unmodified run_index on actual published gzip transport inputs','rows':rows},indent=2)+'\n')
print(json.dumps(rows))
