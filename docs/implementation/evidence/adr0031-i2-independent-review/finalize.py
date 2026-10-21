"""Reconcile final receipts and bind the unchanged target and review artifacts."""
import datetime,hashlib,json,pathlib,subprocess
B=pathlib.Path(__file__).resolve().parent;R=pathlib.Path('/workspace/task-d-review')
m=json.loads((B/'input-manifest.json').read_text())
changed=[name for name,sha in m['inputs'].items() if hashlib.sha256((R/name).read_bytes()).hexdigest()!=sha]
def git(*args):return subprocess.check_output(['git',*args],cwd=R,text=True).strip()
assert not changed and not git('status','--porcelain')
lanes=[]
for suffix in ['3513','3531']:
    p=json.loads((B/('verified-'+suffix)/'receipt.json').read_text())
    a=json.loads((B/'author-rerun'/('verified-'+suffix)/'receipt.json').read_text())
    frozen=[x for x in p['cases'] if not x['id'].startswith('corrective-control')]
    mitigation=[x for x in p['cases'] if x['id'].startswith('corrective-control')]
    bad_indexes=[(t,n,row) for t,idx in p['inventory']['indexes'].items() for n,rows in idx.items() for row in rows if row[5] and row[4]!='BINARY']
    assert not bad_indexes
    flags={row[0]:row[5] for row in p['inventory']['functions'] if row[0].startswith('p1_resource_')}
    assert all(value & 2048 for value in flags.values()) and len(flags)==2
    assert len(frozen)==301 and sum(not x['pass'] for x in frozen)==6
    assert all(x['pass'] for x in mitigation) and len(mitigation)==7
    assert len(a['cases'])==133 and all(x['diagnostic_pass'] for x in a['cases'])
    lanes.append({'runtime':p['runtime']['sqlite_version'],'source_id':p['runtime']['sqlite_source_id'],
     'candidate_independent':{'executed':len(frozen),'passed':sum(x['pass'] for x in frozen),'failed':sum(not x['pass'] for x in frozen)},
     'disposable_mitigation':{'executed':len(mitigation),'passed':sum(x['pass'] for x in mitigation)},
     'author_case_reexecution':{'executed':len(a['cases']),'passed':sum(x['diagnostic_pass'] for x in a['cases'])},
     'nonbinary_index_key_slots':bad_indexes,'resource_function_flags':flags,
     'candidate_index_key_slots':sum(row[5] for idx in p['inventory']['indexes'].values() for rows in idx.values() for row in rows)})
copies={name:hashlib.sha256((B/'author-rerun'/name).read_bytes()).hexdigest()==m['inputs']['docs/implementation/evidence/adr0031-i2-preparation/'+name] for name in ['probe.py','compose_proposal.py','resource_udfs.py','resources.sql','baseline_controls.py','transaction_controls.py']}
assert all(copies.values())
result={'at_utc':datetime.datetime.now(datetime.UTC).isoformat(),'verdict':'NOT READY','head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}'),
 'tracked_inputs_rechecked':len(m['inputs']),'changed_tracked_inputs':changed,'tracked_status':git('status','--porcelain'),
 'candidate_copies_byte_identical':copies,'lanes':lanes,'process_receipts':json.loads((B/'process-receipts.json').read_text()),
 'review_script_sha256':hashlib.sha256((B/'independent_review.py').read_bytes()).hexdigest()}
(B/'final-binding.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'target':result['head'],'unchanged_files':len(m['inputs']),'lanes':lanes},indent=2))
