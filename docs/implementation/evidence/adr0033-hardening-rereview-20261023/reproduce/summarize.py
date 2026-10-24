import sys,json,hashlib,subprocess,zipfile,difflib,collections,xml.etree.ElementTree as ET
from pathlib import Path
root=Path('/workspace/adr0033-review');out=Path('/tmp/adr0033-rereview');sys.path.insert(0,str(root))
from scripts import verify_i5_offline as e
sha=lambda b:hashlib.sha256(b).hexdigest()
b=json.loads((out/'broad/summary.json').read_text());f=json.loads((out/'focused/summary.json').read_text());ordinary=set(e.nodes(out/'broad/ordinary-collection.nodes.txt'));executed=set(e.nodes(out/'broad/regressions.selected.txt'))
for name in f:executed.update(e.nodes(out/'focused'/(name+'.selected.txt')))
assert executed<=ordinary
(out/'ordinary-unexecuted.txt').write_text(''.join(n+'\n' for n in sorted(ordinary-executed)))
# Every trace difference is retained and inspected by line category. This classification
# does not normalize the source traces or turn non-successes into passes.
rows=json.loads((out/'full-trace-differences.json').read_text());allowed={'units','context_db','tmp_path_factory','self','resources','p1_distributions','env','report'};counter=collections.Counter();other=[]
for row in rows:
 for s in row['diff']:
  if not s.startswith(('+','-')) or s.startswith(('+++','---')):continue
  line=s[1:];name=line.split(' = ')[0]
  if name in allowed:counter[name]+=1
  elif line in ('tests/packaging/test_p1_distribution.py:24: AssertionError','tests/packaging/test_p1_distribution.py:26: AssertionError'):counter['test_p1_distribution frame24->26']+=1
  else:other.append({'node':row['name'],'line':line})
assert not other
(out/'trace-difference-audit.json').write_text(json.dumps({'all_79_full_raw_traces_differ':True,'differing_line_categories':dict(counter),'other_differing_lines':other,'meaning':'All differing lines are fixture value/environment rendering or four packaging helper frame coordinates; original traceback bodies are preserved.'},indent=2)+'\n')
inputs=e.input_hashes();frozen=json.loads((out/'broad/input-binding.json').read_text())['inputs'];assert inputs==frozen
binding={'tested_head':e.git('rev-parse','HEAD'),'tested_tree':e.git('rev-parse','HEAD^{tree}'),'execution_inputs_unchanged':True,'execution_inputs':inputs,'input_inventory_sha256':sha(json.dumps(inputs,sort_keys=True).encode()),'source_tree':e.git('rev-parse','HEAD:src'),'tracked_status':e.git('status','--porcelain','--untracked-files=no')}
(out/'verified-input-binding.json').write_text(json.dumps(binding,indent=2)+'\n')
c=json.loads((out/'measurement/sdist-contract.json').read_text())
summary={'reviewed_head':binding['tested_head'],'reviewed_tree':binding['tested_tree'],'ordinary_collected':len(ordinary),'executed_unique_ordinary':len(executed),'unexecuted_ordinary':len(ordinary-executed),'live_not_run':1,'benchmark_not_run':1,'full_release_acceptance':False,'broad':b,'focused':f,'installed_journal':json.loads((out/'installed-journal-summary.json').read_text()),'source_inputs_unchanged':True,'measurements':json.loads((out/'measurement/measurements.json').read_text()),'budgets':c['budgets'],'tar_stream_bytes':c['tar_stream_bytes'],'raw_header_count':c['raw_header_count'],'source_inventory_sha256':c['source_inventory_sha256']}
(out/'verification-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ('broad','focused','installed_journal','measurements')},indent=2))
