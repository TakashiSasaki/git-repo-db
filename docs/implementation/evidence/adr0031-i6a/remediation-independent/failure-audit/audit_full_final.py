"""Raw ordinary result plus transparent latest-node view across recorded reruns."""
from collections import Counter
import gzip
import json
import math
from pathlib import Path
import re
import sys

import audit

OUT=Path(__file__).resolve().parent
FULL,CLEAN,CACHE,SERIAL=map(lambda x:Path(x).resolve(),sys.argv[1:5])
expected,er=audit.receipt(audit.E/'after-final')
before,br=audit.receipt(audit.E/'before')
clean_rows={r['nodeid']:r for r in audit.jread(OUT/'clean743.json.gz')}
public_inputs=audit.jread(OUT/'clean478-inputs.json')
original_failed={n for n,r in before.items() if r['outcome']!='passed'}
expected_failed={n for n,r in expected.items() if r['outcome']!='passed'}
streams={};receipts={};traces={};origin_checks={};bindings={};runtime={}
for label,folder,prefix in [('full',FULL,'ordinary'),('clean743',CLEAN,'diagnostic'),('cache22',CACHE,'diagnostic'),('serial1',SERIAL,'diagnostic')]:
    result,receipt=audit.receipt(folder,prefix=prefix)
    streams[label]=result;receipts[label]=receipt
    bs=[audit.jread(folder/n) for n in ('binding-before.json','binding-after.json')]
    assert all(b['head']==audit.TARGET and b['tree']=='7072f952975a8537f74ced1bbc2a4a31d7aa3690' and b['inputs']==public_inputs for b in bs)
    bindings[label]={'head':bs[0]['head'],'tree':bs[0]['tree'],'input_count':len(bs[0]['inputs']),'before_status':bs[0]['status'],'after_status':bs[1]['status'],'source_root':bs[0].get('source_root',str(audit.ROOT))}
    if label!='full':assert all(not b['status'] for b in bs)
    events=audit.lines(folder/(prefix+'.jsonl'))
    times={r['nodeid']:r['timestamp'] for r in events if r.get('event')=='phase' and r['phase']=='teardown'}
    assert set(times)==set(result) and all(math.isfinite(t) for t in times.values())
    runtime[label]={'end_times':times,'directory':str(folder)}
    if label=='full':continue
    source=Path(bs[0]['source_root'])
    configured=[];ended=[];starts=Counter();finishes=Counter();observed={};origins=[]
    for p in sorted((folder/'trace').glob('*.jsonl')):
        records=audit.lines(p)
        cs=[r for r in records if r['event']=='configure'];es=[r for r in records if r['event']=='session_finish']
        assert len(cs)==len(es)==1 and cs[0]['source']==str(source) and cs[0]['optimization']==0
        configured+=cs;ended+=es
        os=[r for r in records if r['event']=='product_origins']
        assert len(os)==2 and {r['stage'] for r in os}=={'configure','session_finish'}
        for r in os:
            assert 'repo_catalog' in r['modules']
            for name,m in r['modules'].items():
                path=Path(m['path']).resolve();assert path.is_relative_to(source/'src')
                assert m['sha256']==public_inputs[str(path.relative_to(source))]
            origins.append({'worker':cs[0]['worker'],'stage':r['stage'],'module_count':len(r['modules'])})
        for r in records:
            n=r.get('nodeid')
            if r['event']=='start':starts[n]+=1
            if r['event']=='finish':finishes[n]+=1
            if n:observed.setdefault(n,[]).append(r)
    assert starts==finishes==Counter(result.keys())
    traces[label]=observed;origin_checks[label]={'workers':len(configured),'checks':origins,'lifecycle_complete':True}
assert set(streams['full'])==set(expected)
blocked={n for n,r in streams['full'].items() if r.get('uv_cache_error')}
assert len(blocked)==22 and blocked==set(streams['cache22'])
provisional=set(audit.jread(OUT/'full-cache-provisional-nodeids.json'))
assert provisional==blocked
new={n for n,r in streams['full'].items() if r['outcome']!='passed' and expected[n]['outcome']=='passed'}
assert len(new)==19 and len(new&blocked)==18
sole_timeout='tests/e2e/test_queries.py::test_pr_root_scopes'
assert new-blocked=={sole_timeout}
assert "'timed_out': True" in streams['full'][sole_timeout]['message']
assert "'timeout_seconds': 30" in streams['full'][sole_timeout]['message']
assert set(streams['serial1'])=={sole_timeout}
assert streams['serial1'][sole_timeout]['outcome']=='passed'
serial_command=audit.jread(SERIAL/'diagnostic.execution.json')['command']
assert '-n' not in serial_command

# Latest is the actual last completed test protocol, using recorded teardown time.
latest={}
for label,result in streams.items():
    for n,r in result.items():
        t=runtime[label]['end_times'][n]
        if n not in latest or t>latest[n]['teardown_timestamp']:
            latest[n]={'result':r,'invocation':label,'teardown_timestamp':t}
assert set(latest)==set(expected)
volatile=r'/workspace/(?:i6a-runs/after-final|review-source-run|review-clean743|review-full-cache-corrected|review-serial-timeout)/basetemp/popen-gw\d+/[^\s\'\",)]*'
def norm(s):return re.sub(volatile,'<VOLATILE_TEST_PATH>',s)
rows=[]
for n in sorted(latest):
    chosen=latest[n];r=chosen['result'];label=chosen['invocation']
    stack=[]
    if label in traces:
        for event in traces[label][n]:
            if event['event']=='admission_exception':
                for f in event['stack']:
                    if f['path'].startswith('src/'):
                        sf=audit.sf(f)
                        if sf not in stack:stack.append(sf)
    category,proof=audit.classify(r,stack)
    support=None
    if category.startswith('UNRESOLVED') and n in clean_rows:
        cr=clean_rows[n]
        assert r['outcome']==cr['actual_clean']['outcome'] and r['phase']==cr['actual_clean']['phase']
        assert norm(r['message'])==norm(cr['actual_clean']['message'])
        category=cr['classification'];proof=cr['source_proof']
        support='Underlying caught exception independently observed in clean743; this full result agrees in phase/outcome and volatile-path-normalized message. Raw stack is not invented.'
    assert category in {'PASS','I6-C','I7-composition','Transfer-stage'},(n,category)
    history=[{'invocation':lab,'outcome':res[n]['outcome'],'phase':res[n]['phase'],'teardown_timestamp':runtime[lab]['end_times'][n]} for lab,res in streams.items() if n in res]
    rows.append({'nodeid':n,'raw_full':streams['full'][n],'verification_history':history,'latest_invocation':label,'latest_teardown_timestamp':chosen['teardown_timestamp'],'latest':r,'archived_after':expected[n],'same_latest_outcome_phase_as_archived':r['outcome']==expected[n]['outcome'] and r['phase']==expected[n]['phase'],'classification':category,'source_proof':proof,'diagnostic_support':support,'was_uv_cache_blocked_in_full':n in blocked,'was_extra_timeout_in_full':n==sole_timeout})
latest_counts=dict(Counter(r['latest']['outcome'] for r in rows))
assert latest_counts=={'passed':5675,'failed':279,'error':20}
assert all(r['same_latest_outcome_phase_as_archived'] for r in rows)
added=set(expected)-set(before)
assert len(added)==33 and all(latest[n]['result']['outcome']=='passed' for n in added)
summary={'raw_ordinary':receipts['full'],'clean743':receipts['clean743'],'corrected_cache22':receipts['cache22'],'serial_timeout_repeat':receipts['serial1'],'raw_uv_cache_error_count':len(blocked),'raw_uv_cache_error_previous_outcomes':dict(Counter(expected[n]['outcome'] for n in blocked)),'all_provisional_candidates_causally_confirmed_uv_cache':provisional==blocked,'sole_additional_noncache_failure':{'nodeid':sole_timeout,'raw_failure':'CLI search path returns3/partial/timed_out=true with timeout_seconds30 during overlapped workload.','serial_result':'PASS with unchanged source/test/30s timeout, no xdist workers; raw FAIL remains. This is an observed timing/environment-sensitive repeat, not proof of its precise resource cause.'},'raw_new_unsuccessful_count':len(new),'raw_outcome_phase_differences':sum(streams['full'][n]['outcome']!=expected[n]['outcome'] or streams['full'][n]['phase']!=expected[n]['phase'] for n in expected),'latest_unique_node_count':len(rows),'latest_nodewise_counts_NOT_ONE_INVOCATION':latest_counts,'latest_unsuccessful_classes':dict(Counter(r['classification'] for r in rows if r['classification']!='PASS')),'latest_original743_classes':dict(Counter(r['classification'] for r in rows if r['nodeid'] in original_failed)),'all_original5941_ids_retained':set(before).issubset(expected),'added33_all_latest_pass':True,'all_latest_outcome_phases_match_archived':True,'bindings':bindings,'source_layout_distinction':'Raw full runs from /workspace/i6a-independent with untracked review evidence, while all478 execution inputs equal public Git blobs and tracked status is clean. clean743/cache22/serial1 run from separate fully pristine /workspace/i6a-review-clean with separate editable runtime and empty full-untracked status; own in-pytest origins/hashes are checked.','in_pytest_origin_checks':origin_checks,'scope':'5974 latest unique node outcomes combine four actual invocations by last protocol teardown timestamp. They are NOT a single successful full invocation or complete release acceptance; failed raw full and all overlapping repetitions remain separately counted.'}
(OUT/'full-latest-node-map.json.gz').write_bytes(gzip.compress(json.dumps(rows,indent=2).encode(),mtime=0))
(OUT/'full-final-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(OUT/'full-final-inputs.json').write_text(json.dumps(audit.inputs,indent=2)+'\n')
print(json.dumps(summary,indent=2))
