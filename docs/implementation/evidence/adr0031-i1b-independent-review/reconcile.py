import pathlib,json,collections,xml.etree.ElementTree as ET,hashlib,subprocess
B=pathlib.Path('/workspace/independent-task-b-20261021')
def junit_key(node):
    prefix,sep,parameters=node.partition('[')
    parts=prefix.split('::'); path=parts.pop(0)
    classname=path.removesuffix('.py').replace('/','.')
    if len(parts)>1: classname+='.'+'.'.join(parts[:-1])
    return classname,parts[-1]+(sep+parameters if sep else '')
out={}
for d in sorted((B/'runs').iterdir()):
    if not (d/'receipt.json').exists():continue
    receipt=json.loads((d/'receipt.json').read_text())
    if not (d/'journal.jsonl').exists():out[d.name]={'exit':receipt['exit']};continue
    events=[json.loads(s) for s in (d/'journal.jsonl').read_text().splitlines()]
    selected=next((e['nodes'] for e in events if e['event']=='collection'),[])
    starts=[e['nodeid'] for e in events if e['event']=='start'];finishes=[e['nodeid'] for e in events if e['event']=='finish']
    phases=collections.Counter((e['nodeid'],e['when']) for e in events if e['event']=='phase')
    cases=list(ET.parse(d/'junit.xml').iter('testcase'))
    no_execution='ordinary' in d.name
    out[d.name]={'exit':receipt['exit'],'selected':len(selected),'starts':len(starts),'finishes':len(finishes),'junit_cases':len(cases),'selected_equals_starts':collections.Counter(selected)==collections.Counter(starts),'starts_equals_finishes':collections.Counter(starts)==collections.Counter(finishes),'selected_equals_junit':collections.Counter(map(junit_key,selected))==collections.Counter((c.get('classname'),c.get('name')) for c in cases),'exact_three_phases':all(phases[(n,w)]==1 for n in starts for w in ['setup','call','teardown']),'finish_exit':[e['exit'] for e in events if e['event']=='sessionfinish'],'junit':receipt.get('junit'), 'failures':receipt.get('failures')}
    if not no_execution:
        assert out[d.name]['selected_equals_starts'] and out[d.name]['starts_equals_finishes'] and out[d.name]['selected_equals_junit'] and out[d.name]['exact_three_phases'],out[d.name]
hashes={}
for name,root,manifest in [('baseline',B/'repo',B/'repo/docs/implementation/evidence/adr0031-i1/author/input-manifest.json'),('remediation',B/'remediation',B/'remediation-author-receipts/final-r2-broad-3531/receipt.json')]:
    data=json.loads(manifest.read_text()); inputs=data.get('inputs',data.get('input_hashes'))
    bad=[]
    for path,value in inputs.items():
        expected=value['sha256'] if isinstance(value,dict) else value
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:bad.append(path)
    hashes[name]={'count':len(inputs),'mismatches':bad,'tracked_diff':subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()}
(B/'reconciliation.json').write_text(json.dumps({'runs':out,'final_hashes':hashes},indent=2)+'\n')
print(json.dumps({'runs':{k:{x:v for x,v in d.items() if x not in ('failures','junit')} for k,d in out.items()},'final_hashes':hashes},indent=2))
