import collections
import hashlib
import json
import pathlib
import subprocess
import xml.etree.ElementTree as ET

ROOT=pathlib.Path('/workspace/work/review-shared-tree')
OUT=pathlib.Path('/workspace/work/review-shared-scratch')

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def check(prefix, expected):
    selected=[s.strip() for s in (OUT/f'{prefix}-selected.txt').read_text().splitlines() if '::' in s and not s.startswith(' ')]
    events=[json.loads(s) for s in (OUT/f'{prefix}-journal.jsonl').read_text().splitlines()]
    starts=[e['nodeid'] for e in events if e['event']=='start']
    phases=[e for e in events if e['event']=='phase']
    suites=ET.parse(OUT/f'{prefix}.xml')
    cases=suites.findall('.//testcase')
    finish=[e for e in events if e['event']=='finish']
    assert len(selected)==len(set(selected))==expected
    assert len(starts)==len(set(starts))==expected
    assert set(selected)==set(starts)
    assert len(phases)==3*expected
    for s in starts:
        assert collections.Counter(e['phase'] for e in phases if e['nodeid']==s)=={'setup':1,'call':1,'teardown':1}
    assert all(e['outcome']=='passed' for e in phases)
    assert len(cases)==expected
    assert not suites.findall('.//failure') and not suites.findall('.//error') and not suites.findall('.//skipped')
    assert len(finish)==1 and finish[0]['exitstatus']==0
    def junit_id(node):
        module,*rest=node.split('::')
        return ('.'.join([module.removesuffix('.py').replace('/','.'),*rest[:-1]]),rest[-1])
    assert collections.Counter(junit_id(n) for n in starts)==collections.Counter((c.attrib['classname'],c.attrib['name']) for c in cases)
    return {'selected_count':len(selected),'executed_unique_count':len(starts),'phase_count':len(phases),'junit_testcase_count':len(cases),'passed':len(cases),'failed':0,'skipped':0,'journal_exitstatus':0,'reconciled':True,'node_ids':starts,'artifacts':{name:{'sha256':digest(OUT/name),'bytes':(OUT/name).stat().st_size} for name in [f'{prefix}-selected.txt',f'{prefix}-journal.jsonl',f'{prefix}.xml',f'{prefix}.log']}}

result={
 'review_scope':'Independent shared owner-design/time/DDL/typed-snapshot review; read-only',
 'final_reviewed_commit':'f17dd2154f22f965883d8a1943c140f9cc439ae8',
 'final_reviewed_tree':'952c18132b11f393715e67baad33b730e3404e12',
 'final_acceptance_input_hash':'e3c7e35f6202f8b3e5c9a33a48866e9f24916062fb6ac7a77c09582f2d6faeaf',
 'impact_reviewed_commit':'2d4f5d4e30903a4ddd9f1f7977560b47cfe29e6b',
 'impact_reviewed_tree':'5829799cb8ab0da0dad5306f74df82ff9f84cd31',
 'impact_acceptance_input_hash':'e3b960c328cce008497c4d3e1c5893ec80d0b1f5a1fb9d4593418a82a40df0e6',
 'final_committed':check('committed-f17',119),
 'final_independent_scratch':check('independent-f17',74),
 'prior_impact':check('impact-final',816),
 'script_sha256':{p.name:digest(p) for p in OUT.glob('test_*.py')},
 'limitations':['The119 final committed nodes overlap the816 earlier impact selection; do not sum repeated nodes as new unique coverage.','Scratch tests are reviewer counterexamples outside repository suites; not installed-release tests.','Final P5/P6 combined tree, hosted CI and Release Acceptance not verified by this shared review.'],
}
(OUT/'shared-review-reconciliation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:{n:v[n] for n in ['selected_count','executed_unique_count','phase_count','reconciled']} for k,v in result.items() if isinstance(v,dict) and 'selected_count' in v},indent=2))
