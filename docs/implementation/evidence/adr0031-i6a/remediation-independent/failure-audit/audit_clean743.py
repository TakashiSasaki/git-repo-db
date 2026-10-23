"""Reconcile one pristine-source743 diagnostic and its own actual traces."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import audit

OUT=Path(__file__).resolve().parent
RUN=Path(sys.argv[1]).resolve()
actual,receipt=audit.receipt(RUN,prefix='diagnostic')
before,before_receipt=audit.receipt(audit.E/'before')
after,after_receipt=audit.receipt(audit.E/'after-final')
failed_before={n for n,r in before.items() if r['outcome']!='passed'}
assert len(actual)==743 and set(actual)==failed_before
bindings=[audit.jread(RUN/n) for n in ('binding-before.json','binding-after.json')]
clean=Path(bindings[0]['source_root']).resolve()
assert clean!=audit.ROOT
expected_files=subprocess.check_output(['git','ls-tree','-r','--name-only',audit.TARGET,'--','src','tests','scripts','.github/workflows','pyproject.toml','uv.lock'],cwd=clean,text=True).splitlines()
assert len(expected_files)==478
expected_hashes={p:hashlib.sha256(subprocess.check_output(['git','show',audit.TARGET+':'+p],cwd=clean)).hexdigest() for p in expected_files}
for b in bindings:
    assert b['head']==audit.TARGET and b['tree']=='7072f952975a8537f74ced1bbc2a4a31d7aa3690'
    assert not b['status'] and b['source_root']==str(clean)
    assert b['inputs']==expected_hashes
runtime=audit.jread(RUN/'runtime.json')
assert Path(runtime['product_origin']).resolve().is_relative_to(clean/'src')
assert runtime['executable']=='/workspace/review-clean-runtime/bin/python'
starts=Counter();finishes=Counter();observations={};sessions=[];origins=[]
for p in sorted((RUN/'trace').glob('*.jsonl')):
    records=audit.lines(p)
    configured=[r for r in records if r['event']=='configure']
    ended=[r for r in records if r['event']=='session_finish']
    origin_events=[r for r in records if r['event']=='product_origins']
    assert len(configured)==len(ended)==1
    assert configured[0]['optimization']==0 and configured[0]['source']==str(clean)
    assert {r['stage'] for r in origin_events}=={'configure','session_finish'} and len(origin_events)==2
    for r in origin_events:
        assert 'repo_catalog' in r['modules']
        for name,mod in r['modules'].items():
            path=Path(mod['path']).resolve()
            assert path.is_relative_to(clean/'src'),(name,str(path))
            assert mod['sha256']==expected_hashes[str(path.relative_to(clean))]
        origins.append({'worker':configured[0]['worker'],'stage':r['stage'],'module_count':len(r['modules'])})
    sessions.append({'file':p.name,'configured':configured[0],'ended':ended[0]})
    for r in records:
        n=r.get('nodeid')
        if r['event']=='start':starts[n]+=1
        if r['event']=='finish':finishes[n]+=1
        if n:observations.setdefault(n,[]).append(r)
assert starts==finishes==Counter(failed_before)
archived_ledger=audit.jread(audit.E/'classification/final/failure-ledger-reviewed.json')['rows']
old={r['nodeid']:r for r in archived_ledger}
rows=[]
for n in sorted(failed_before):
    obs=observations[n]
    stack=[]
    for e in obs:
        if e['event']=='admission_exception':
            for f in e['stack']:
                if f['path'].startswith('src/'):
                    sf=audit.sf(f)
                    if sf not in stack:stack.append(sf)
    classification,proof=audit.classify(actual[n],stack)
    static=audit.literal_assertions(n,audit.TARGET)
    entered=sorted({e['line'] for e in obs if e['event']=='assertion_line' and e['phase']=='call' and e['path']==n.split('::')[0] and e['line'] in (static or [])})
    archived_entered=old[n]['after_reachability'].get('actual_test_function_assertion_lines_entered')
    rows.append({'nodeid':n,'historical79':old[n]['historical79'],'before':before[n],'actual_clean':actual[n],'archived_after':after[n],'same_outcome_phase_as_archived':actual[n]['outcome']==after[n]['outcome'] and actual[n]['phase']==after[n]['phase'],'classification':classification,'first_semantic_boundary':next((f for f in proof if f.get('actual_failed_sql_call') or 'raise AdmissionRefused' in f['source'] or 'raise UnsupportedResourceStage' in f['source']),None),'source_proof':proof,'actual_admission_exception_frames':stack,'test_body_completed':actual[n]['outcome']=='passed','literal_assertion_lines':static,'literal_assertion_lines_entered':entered,'archived_literal_assertion_lines_entered':archived_entered,'literal_entry_set_matches_archived':entered==archived_entered,'scope':'Actual single pristine-source diagnostic; statement entry is not branch/subexpression/child-process coverage.'})
summary={'source_head':bindings[0]['head'],'source_tree':bindings[0]['tree'],'source_root':str(clean),'source_status_before_after':[b['status'] for b in bindings],'exact_public_input_count':len(expected_hashes),'source_bindings_equal_public_git_blobs':True,'runtime':runtime,'receipt':receipt,'trace_starts_finishes_exact':True,'sessions':sessions,'in_pytest_origin_checks':origins,'all743':dict(Counter(r['classification'] for r in rows)),'additional664':dict(Counter(r['classification'] for r in rows if not r['historical79'])),'original79':dict(Counter(r['classification'] for r in rows if r['historical79'])),'all_original743_outcome_phases_match_archived':all(r['same_outcome_phase_as_archived'] for r in rows),'outcome_phase_differences':[r['nodeid'] for r in rows if not r['same_outcome_phase_as_archived']],'literal_assertion_entered_nodes':sum(bool(r['literal_assertion_lines_entered']) for r in rows),'literal_assertion_entered_resolved444_nodes':sum(bool(r['literal_assertion_lines_entered']) for r in rows if r['classification']=='PASS'),'literal_assertion_entry_set_matches_archived_count':sum(r['literal_entry_set_matches_archived'] for r in rows),'all_local_test_functions_identified':all(r['literal_assertion_lines'] is not None for r in rows),'scope':'One new reviewer743 invocation from a separate pristine frozen checkout and separately editable-bound venv; it overlaps ordinary/root/299 diagnostics and is not added to their aggregate or presented as complete product release acceptance.'}
(OUT/'clean743.json.gz').write_bytes(gzip.compress(json.dumps(rows,indent=2).encode(),mtime=0))
(OUT/'clean743-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(OUT/'clean743-inputs.json').write_text(json.dumps(audit.inputs,indent=2)+'\n')
(OUT/'clean478-inputs.json').write_text(json.dumps(expected_hashes,indent=2)+'\n')
print(json.dumps(summary,indent=2))
assert summary['all_original743_outcome_phases_match_archived']
assert summary['all743']=={'PASS':444,'I6-C':242,'I7-composition':14,'Transfer-stage':43}
