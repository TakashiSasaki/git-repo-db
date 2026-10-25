"""Independently reconcile reviewer runtime plus per-node first refusal evidence."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

import audit
import argparse

OUT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('diagnostic',type=Path)
parser.add_argument('--full',type=Path)
parser.add_argument('--rerun',type=Path)
parser.add_argument('--full-correction',type=Path)
args=parser.parse_args()
DIAG=args.diagnostic.resolve()
FULL=args.full.resolve() if args.full else None

archived_before,br=audit.receipt(audit.E/'before')
archived_after,ar=audit.receipt(audit.E/'after-final')
initial,dr=audit.receipt(DIAG,prefix='diagnostic')
actual=dict(initial)
invocations=[(DIAG,initial)]
rerun_receipt=None
if args.rerun:
    rerun,rerun_receipt=audit.receipt(args.rerun,prefix='diagnostic')
    assert len(rerun)==4 and set(rerun).issubset(actual)
    assert all(initial[n]['outcome']=='error' and 'Failed to initialize cache' in initial[n]['message'] for n in rerun)
    actual.update(rerun)
    invocations.append((args.rerun,rerun))
full=None;fr=None;correction=None;cr=None;blocked=set()
if FULL:
    full,fr=audit.receipt(FULL)
    assert set(full)==set(archived_after)
    blocked={n for n,r in full.items() if r.get('uv_cache_error')}
    if args.full_correction:
        correction,cr=audit.receipt(args.full_correction,prefix='diagnostic')
        assert set(correction)==blocked and blocked
        invocations.append((args.full_correction,correction))
        for n,r in correction.items():
            if n in actual:actual[n]=r
expected={n for n,r in archived_after.items() if r['outcome']!='passed'}
assert set(actual)==expected and len(actual)==299
observed={}
starts=Counter()
finishes=Counter()
sessions=[]
for directory,selected_run in invocations:
    invocation_binding=audit.jread(directory/'binding-before.json')
    invocation_source=invocation_binding.get('source_root',str(audit.ROOT))
    localstarts=Counter()
    localfinishes=Counter()
    for n in selected_run:observed[n]=[]
    for p in sorted((directory/'trace').glob('*.jsonl')):
        records=audit.lines(p)
        config=[r for r in records if r['event']=='configure']
        finish=[r for r in records if r['event']=='session_finish']
        assert len(config)==len(finish)==1
        assert config[0]['optimization']==0 and config[0]['source']==invocation_source
        assert finish[0]['exitstatus'] in (0,1)
        sessions.append({'invocation':str(directory),'file':p.name,'configured':config[0],'ended':finish[0]})
        for r in records:
            n=r.get('nodeid')
            if r['event']=='start':localstarts[n]+=1
            if r['event']=='finish':localfinishes[n]+=1
            if n:observed[n].append(r)
    assert localstarts==localfinishes==Counter(selected_run.keys())
result=[]
for n in sorted(expected):
    events=observed[n]
    stack=[]
    for e in events:
        if e['event']=='admission_exception':
            for f in e['stack']:
                if f['path'].startswith('src/'):
                    enriched=audit.sf(f)
                    if enriched not in stack:stack.append(enriched)
    category,proof=audit.classify(actual[n],stack)
    static=audit.literal_assertions(n,audit.TARGET)
    entered=sorted({e['line'] for e in events if e['event']=='assertion_line' and e['phase']=='call' and e['path']==n.split('::')[0] and e['line'] in (static or [])})
    result.append({'nodeid':n,'actual':actual[n],'initial_diagnostic_result':initial[n],'superseding_packaging_rerun':args.rerun is not None and n in rerun,'archived':archived_after[n],'same_outcome':actual[n]['outcome']==archived_after[n]['outcome'],'same_phase':actual[n]['phase']==archived_after[n]['phase'],'same_raw_message':actual[n]['message']==archived_after[n]['message'],'same_paths_functions':[(x['path'],x['function']) for x in actual[n]['frames']]==[(x['path'],x['function']) for x in archived_after[n]['frames']],'classification':category,'top_exception':actual[n]['message'].split(':',1)[0],'first_semantic_boundary':next((f for f in proof if f.get('actual_failed_sql_call') or 'raise AdmissionRefused' in f['source'] or 'raise UnsupportedResourceStage' in f['source']),None),'source_proof':proof,'observed_exception_frames':stack,'literal_assertion_lines':static,'literal_assertion_lines_entered':entered,'downstream_acceptance':False})
assert all(r['same_outcome'] and r['same_phase'] for r in result)
assert all(r['classification'] in {'I6-C','I7-composition','Transfer-stage'} for r in result)
summary={'initial_diagnostic_receipt':dr,'packaging_rerun_receipt':rerun_receipt,'effective_combination_counts':dict(Counter(r['outcome'] for r in actual.values())),'tracer_sessions':sessions,'trace_nodes_exactly_once_per_invocation':True,'categories':dict(Counter(r['classification'] for r in result)),'same_raw_message':sum(r['same_raw_message'] for r in result),'same_paths_functions':sum(r['same_paths_functions'] for r in result),'with_literal_assert_entry':sum(bool(r['literal_assertion_lines_entered']) for r in result),'scope':'Actual reviewer diagnostic299 plus explicit4-node environment-only rerun, overlapping ordinary test suite; all remain unsuccessful. Initial diagnostic275 FAIL/24 ERROR is preserved; combination279 FAIL/20 ERROR is not a single invocation. Source lines/exception event stacks independently determine first refusal, not future-stage success.'}
if FULL:
    full743=[]
    effectivefull=dict(full)
    if correction:effectivefull.update(correction)
    diagnostic_map={r['nodeid']:r for r in result}
    for n in sorted(n for n,r in archived_before.items() if r['outcome']!='passed'):
        rawfull=full[n]
        r=effectivefull[n]
        category='PASS' if r['outcome']=='passed' else ('Environment-cache-blocked' if 'Failed to initialize cache' in r['message'] else (diagnostic_map[n]['classification'] if n in diagnostic_map else 'UNRESOLVED-new-full-failure'))
        full743.append({'nodeid':n,'before':archived_before[n],'raw_ordinary':rawfull,'actual':r,'from_full_correction':bool(correction and n in correction),'archived_after':archived_after[n],'outcome_equals_archived':r['outcome']==archived_after[n]['outcome'],'phase_equals_archived':r['phase']==archived_after[n]['phase'],'classification':category,'literal_assertion_lines_entered_after_correction':sorted({e['line'] for e in observed.get(n,[]) if e['event']=='assertion_line' and e['phase']=='call' and e['path']==n.split('::')[0] and e['line'] in (audit.literal_assertions(n,audit.TARGET) or [])}) if correction and n in correction else None})
    summary['latest743_outcome_or_phase_differences']=[{'nodeid':r['nodeid'],'actual':r['actual'],'archived_after':r['archived_after']} for r in full743 if not (r['outcome_equals_archived'] and r['phase_equals_archived'])]
    summary['ordinary_all_outcome_or_phase_differences']=[{'nodeid':n,'actual':r,'archived_after':archived_after[n]} for n,r in full.items() if r['outcome']!=archived_after[n]['outcome'] or r['phase']!=archived_after[n]['phase']]
    summary['ordinary_receipt']=fr
    summary['full_cache_blocked_count']=len(blocked)
    summary['full_cache_blocked_nodeids']=sorted(blocked)
    summary['full_correction_receipt']=cr
    summary['latest_nodewise_counts_not_one_invocation']=dict(Counter(r['outcome'] for r in effectivefull.values()))
    summary['fresh_all743']=dict(Counter(r['classification'] for r in full743))
    summary['all33_added_pass']=all(effectivefull[n]['outcome']=='passed' for n in set(full)-set(archived_before))
    summary['no_added_unsuccessful']=not any(r['outcome']!='passed' and n not in expected for n,r in effectivefull.items())
    with gzip.open(OUT/'fresh743.json.gz','wt',encoding='utf-8') as f:json.dump(full743,f,indent=2)
with gzip.open(OUT/'fresh299.json.gz','wt',encoding='utf-8') as f:json.dump(result,f,indent=2)
(OUT/'fresh-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(OUT/'fresh-inputs.json').write_text(json.dumps(audit.inputs,indent=2)+'\n')
print(json.dumps(summary,indent=2))
