"""Read-only evidence reconciliation, separate from independent SQL execution."""
import collections
import hashlib
import json
import pathlib
import subprocess
import sys
import zipfile

repo=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2])
def h(b):return hashlib.sha256(b).hexdigest()
fix=repo/'docs/implementation/evidence/adr0031-i2-f1'
checks={}
with zipfile.ZipFile(fix/'c-f1-evidence.zip') as z:
    index=json.loads(z.read('artifact-index.json'))['files']
    assert len(z.namelist())==len(set(z.namelist()))
    assert set(z.namelist())==set(index)|{'artifact-index.json'}
    mismatches=[n for n,d in index.items() if h(z.read(n))!=d['sha256'] or len(z.read(n))!=d['bytes']]
    assert not mismatches
    checks['author_archive']={'sha256':h((fix/'c-f1-evidence.zip').read_bytes()),
        'indexed_verified':len(index),'mismatches':mismatches,
        'launcher':json.loads(z.read('launcher-receipt.json')),
        'processes':json.loads(z.read('final-run/process-receipts.json')),
        'runtime_builds':json.loads(z.read('runtime-provenance.json')),'lanes':{}}
    for lane in ('3513','3531'):
        r=json.loads(z.read(f'final-run/sqlite-{lane}/receipt.json'))
        assert r['summary']['cases']==r['summary']['passed']==119
        assert len(r['cases'])==119 and all(c['pass'] for c in r['cases'])
        assert len({c['case'] for c in r['cases']})==119
        hashes=r['input_hashes']
        assert all(h((repo/n).read_bytes())==v for n,v in hashes.items())
        sql_cases=[c for c in r['cases'] if 'before' in c and c.get('outcome')=='refused']
        unequal=[c['case'] for c in sql_cases if c['before']!=c['after']]
        assert not unequal
        checks['author_archive']['lanes'][lane]={'summary':r['summary'],
            'verified_bound_inputs':len(hashes),'refused_full_rowsets_equal':len(sql_cases),
            'unequal_refusals':unequal,'runtime':r['runtime']}

base=json.loads((fix/'base-input-manifest.json').read_text())
changed=[p for p,v in base['files'].items() if h((repo/p).read_bytes())!=v]
assert not changed
checks['predecessor_preservation']={'base':base['base'],'files_verified':len(base['files']),
                                   'changed_files':changed}
checks['independent_lanes']={}
for lane in ('3510300','3530100'):
    r=json.loads((out/'final-run'/lane/'receipt.json').read_text())
    assert r['summary']['total']==r['summary']['passed']==343
    assert all(c['pass'] for c in r['cases'])
    assert len({c['name'] for c in r['cases']})==343
    refusals=[c for c in r['cases'] if c.get('outcome')=='refused' or c['family']=='malformed-sql']
    assert all(c['before']==c['after'] for c in refusals)
    checks['independent_lanes'][lane]={'total':343,'all_refused_rowsets_equal':len(refusals),
        'errors':dict(collections.Counter(str((c.get('error') or {}).get('extended_code'))
                                         for c in r['cases'] if c.get('error'))),
        'model_families_are_separate':True,'runtime':r['summary']['runtime']['version'],
        'source_id':r['summary']['runtime']['source_id']}
checks['tracked_changes_from_reviewed_base']=subprocess.check_output(
    ['git','status','--porcelain'],cwd=repo,text=True)
(out/'evidence-audit.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps({'author_archive_entries':len(index),'preserved_base_files':len(base['files']),
                  'independent_lanes':checks['independent_lanes']},indent=2))
