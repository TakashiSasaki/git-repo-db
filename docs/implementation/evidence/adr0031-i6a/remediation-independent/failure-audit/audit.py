"""Independent stdlib receipt/trace/AST audit. Does not import Author classifier."""
import ast
from functools import lru_cache
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

ROOT = Path(__file__).resolve().parents[6]
OUT = Path(__file__).resolve().parent
E = ROOT / 'docs/implementation/evidence/adr0031-i6a/remediation-20261023'
BEFORE = 'f5dc409429cdb69955b55e3c27a7ef3c163762fb'
TARGET = '08fbb956c2e470e245146b0dbae747ed0690ea40'
inputs = {}


def raw(p):
    p = Path(p)
    if not p.exists():
        p = Path(str(p) + '.gz')
    b = p.read_bytes()
    try:
        rel = str(p.relative_to(ROOT))
    except ValueError:
        rel = str(p)
    inputs[rel] = {'size': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
    return gzip.decompress(b) if p.suffix == '.gz' else b


def jread(p):
    return json.loads(raw(p))


def lines(p):
    return [json.loads(l) for l in raw(p).splitlines() if l]


def nodekey(node):
    head, sep, param = node.partition('[')
    bits = head.split('::')
    return (bits[0][:-3].replace('/', '.') + ''.join('.'+b for b in bits[1:-1]), bits[-1]+sep+param)


def frames(text):
    found = []
    for pattern in (r'^([^\n:]+\.py):(\d+):(?: in (\w+))?', r'File "([^\n"]+\.py)", line (\d+), in (\w+)'):
        for path, line, fn in re.findall(pattern, text, flags=re.M):
            for prefix in ('tests/', 'src/repo_catalog/'):
                if prefix in path:
                    path = prefix + path.split(prefix, 1)[1]
                    break
            if '/repo_catalog/' in path:
                path = 'src/repo_catalog/' + path.split('/repo_catalog/',1)[1]
            if path.startswith(('src/', 'tests/')):
                f = {'path': path, 'line': int(line), 'function': fn}
                if f not in found:
                    found.append(f)
    return found


@lru_cache(maxsize=None)
def source(path, commit=TARGET):
    return subprocess.check_output(['git','show',commit+':'+path], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)


@lru_cache(maxsize=None)
def source_tree(path,commit=TARGET):
    return ast.parse(source(path,commit))


def source_frame(f, commit=TARGET):
    p = f['path']
    s = source(p,commit)
    tree = source_tree(p,commit)
    funcs = [n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.lineno <= f['line'] <= n.end_lineno]
    func = min(funcs,key=lambda n:n.end_lineno-n.lineno) if funcs else None
    return dict(f,enclosing=func.name if func else None,source=s.splitlines()[f['line']-1])


SOURCE_CACHE={}
def sf(f, commit=TARGET):
    k=(f['path'],f['line'],commit)
    if k not in SOURCE_CACHE: SOURCE_CACHE[k]=source_frame(f,commit)
    return SOURCE_CACHE[k]


def receipt(directory,prefix='ordinary'):
    selected=raw(directory/(prefix+'.selected.txt')).decode().splitlines()
    keymap={nodekey(n):n for n in selected}
    assert len(selected)==len(set(selected))==len(keymap)
    results={}
    for case in ET.fromstring(raw(directory/(prefix+'.xml'))).iter('testcase'):
        k=(case.get('classname'),case.get('name'))
        n=keymap[k]
        assert n not in results
        r={'outcome':'passed','phase':None,'message':'','trace_sha256':None,'frames':[]}
        for tag,phase in [('failure','call'),('error','setup'),('skipped',None)]:
            e=case.find(tag)
            if e is not None:
                text=e.text or ''
                r={'outcome':{'failure':'failed','error':'error','skipped':'skipped'}[tag], 'phase':'teardown' if 'failed on teardown' in e.get('message','') else phase, 'message':e.get('message',''), 'trace_sha256':hashlib.sha256(text.encode()).hexdigest(),'frames':frames(text),'uv_cache_error':'Failed to initialize cache' in text and 'Read-only file system' in text}
                break
        results[n]=r
    events=lines(directory/(prefix+'.jsonl'))
    typed=lines(directory/(prefix+'.report-types.jsonl'))
    ordinary=[r for r in typed if r.get('subtest_context') is None]
    subtests=[r for r in typed if r.get('subtest_context') is not None]
    phases=Counter((r['nodeid'],r['phase']) for r in ordinary)
    setup={r['nodeid']:r['outcome'] for r in ordinary if r['phase']=='setup'}
    exits=jread(directory/(prefix+'.execution.json'))
    phasekey=lambda e:(e['nodeid'],e['phase'],e['outcome'],round(e['duration'],6))
    finish=[e for e in events if e['event']=='finish']
    typed_outcomes={(r['nodeid'],r['phase']):r['outcome'] for r in ordinary}
    failed_subtest_nodes={r['nodeid'] for r in subtests if r['outcome']=='failed'}
    def expected_result(n):
        failed={p for p in ('setup','call','teardown') if typed_outcomes.get((n,p))=='failed'}
        if 'setup' in failed:return ('error','setup')
        if 'call' in failed or n in failed_subtest_nodes:return ('failed','call')
        if 'teardown' in failed:return ('error','teardown')
        if any(typed_outcomes.get((n,p))=='skipped' for p in ('setup','call','teardown')):return ('skipped',None)
        return ('passed',None)
    checks={
      'junit_results_match_actual_typed_outcomes':all((r['outcome'],r['phase'])==expected_result(n) for n,r in results.items()),
      'node_ids_exact':set(selected)==set(results),
      'starts_exact':Counter(selected)==Counter(e['nodeid'] for e in events if e['event']=='start'),
      'raw_and_typed_phases_exact':Counter(phasekey(r) for r in events if r['event']=='phase')==Counter(phasekey(r) for r in typed),
      'ordinary_setup_teardown_once':all(phases[n,p]==1 for n in selected for p in ('setup','teardown')),
      'ordinary_call_after_setup_once':all(phases[n,'call']==int(setup[n]=='passed') for n in selected),
      'ordinary_all_phases_unique':all(v==1 for v in phases.values()),
      'subtests_explicitly_typed':all(r['report_type']=='_pytest.subtests.SubtestReport' for r in subtests),
      'failed_subtests_not_hidden':all(r['outcome']!='failed' or results[r['nodeid']]['outcome']!='passed' for r in subtests),
      'finish_and_exit':len(finish)==1 and finish[0]['exitstatus']==exits['exit_code'] and exits['exit_code'] in (0,1),
    }
    # Unlike the Author classifier, resolve gzip before testing binding existence.
    bindings=[jread(directory/n) for n in ('binding-before.json','binding-after.json')]
    checks['bindings_unchanged']=all(bindings[0].get(k)==bindings[1].get(k) for k in ('head','tree','inputs','status'))
    assert all(checks.values()), checks
    return results,{'checks':checks,'selected':len(selected),'counts':dict(Counter(r['outcome'] for r in results.values())),'exit_code':exits['exit_code'],'subtests':dict(Counter(r['outcome'] for r in subtests)),'binding_head':bindings[0]['head'],'binding_tree':bindings[0]['tree']}


def supplements(commit=TARGET,before=False):
    result={}
    for name in (('before-caughtguards',) if before else ('final-caughtguards','final-recovery-export-guards')):
        data=jread(E/'classification'/name/'actual-permission-raise-stacks.json')
        assert data['exitstatus']==1
        for r in data['records']:
            f=r['raise_frame']
            path=f['file']
            if '/src/repo_catalog/' not in path:continue
            path='src/repo_catalog/'+path.split('/src/repo_catalog/',1)[1]
            result.setdefault(r['nodeid'],[]).append(sf({'path':path,'line':f['line'],'function':f['function']},commit))
    return result


def classify(r,sup=(),commit=TARGET):
    if r['outcome']=='passed':return 'PASS', []
    fs=[sf(f,commit) for f in r['frames'] if f['path'].startswith('src/')]
    if 'I2_TRANSFER_UNSUPPORTED' in r['message']:
        if any('raise UnsupportedResourceStage' in f['source'] for f in fs):
            return 'Transfer-stage',fs
        for f in reversed(r['frames']):
            if not f['path'].startswith('tests/'):continue
            enriched=sf(f,commit)
            snippet='\n'.join(source(f['path'],commit).splitlines()[f['line']-1:f['line']+10])
            if 'db.execute(' in snippet and 'INSERT INTO resource_repository_relations' in snippet:
                ddl=source('src/repo_catalog/adapters/sqlite/p1_ddl/context.sql',commit)
                trigger='CREATE TRIGGER i2_transfer_stage_fence BEFORE INSERT ON resource_repository_relations'
                assert trigger in ddl and "RAISE(ABORT,'I2_TRANSFER_UNSUPPORTED')" in ddl
                return 'Transfer-stage',fs+[dict(enriched,actual_failed_sql_call=snippet,fence_definition=ddl[ddl.index(trigger):ddl.index(trigger)+260])]
        return 'UNRESOLVED-Transfer-source',fs
    for f in fs:
        if f['path']=='src/repo_catalog/adapters/sqlite/context_admission.py' and f['source'].strip()=='raise AdmissionRefused("PERMISSION_DENIED")':
            prev=source(f['path'],commit).splitlines()[max(0,f['line']-4):f['line']]
            if any('not isinstance(service, ContextAdmissionService)' in line for line in prev):
                if any(x['path'].endswith('/recovery.py') for x in fs):return 'I7-composition',fs
                return 'I6-A-Coordinator' if any(x['path'].endswith('/p1_coordination.py') for x in fs) else 'I6-A-Store/Facade',fs
        if f['path'] in ('src/repo_catalog/application/exchange.py','src/repo_catalog/application/acquisition.py') and f['source'].strip()=='raise AdmissionRefused("PERMISSION_DENIED")':return 'I6-C',fs
    # Receipts wrap/catch these original exceptions. Require an actual matching source raise.
    actual=[x for x in sup if x['source'].strip()=='raise AdmissionRefused("PERMISSION_DENIED")']
    if any(x['path'].endswith('/context_admission.py') for x in actual) and any(x['path'].endswith('/recovery.py') for x in sup):return 'I7-composition',fs+actual
    if any(x['path'] in ('src/repo_catalog/application/acquisition.py','src/repo_catalog/application/exchange.py') for x in actual):return 'I6-C',fs+actual
    return 'UNRESOLVED',fs


def assertion_inventory(path,commit):
    tree=source_tree(path,commit)
    out={}
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_'):
            out[n.name]={
              'asserts':sorted(ast.dump(a,include_attributes=False) for a in ast.walk(n) if isinstance(a,ast.Assert)),
              'raises':sorted(ast.dump(a,include_attributes=False) for a in ast.walk(n) if isinstance(a,ast.Call) and isinstance(a.func,ast.Attribute) and isinstance(a.func.value,ast.Name) and a.func.value.id=='pytest' and a.func.attr in ('raises','warns','skip','xfail')),
              'decorators':[ast.dump(a,include_attributes=False) for a in n.decorator_list],
            }
    return out


def assertions(directory):
    observed={}
    starts=Counter()
    finishes=Counter()
    sessions=[]
    for p in sorted(directory.glob('*.jsonl.gz')):
        events=lines(p)
        configured=[r for r in events if r.get('event')=='configure']
        ended=[r for r in events if r.get('event')=='session_finish']
        assert len(configured)==len(ended)==1
        assert configured[0]['optimization']==0 and ended[0]['exitstatus'] in (0,1)
        sessions.append({'source':configured[0]['source'],'exitstatus':ended[0]['exitstatus']})
        for r in events:
            n=r.get('nodeid')
            if r['event']=='node_start':starts[n]+=1
            if r['event']=='node_finish':finishes[n]+=1
            if r['event']=='assertion_line':observed.setdefault(n,[]).append(r)
    assert starts==finishes and all(c==1 for c in starts.values())
    return observed,{'nodes':len(starts),'sessions':sessions,'starts_finish_unique_equal':True},set(starts)


def literal_assertions(node,commit):
    file,_,rest=node.partition('::')
    name=rest.split('[',1)[0].split('::')[-1]
    tree=source_tree(file,commit)
    funcs=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
    if len(funcs)!=1:return None
    return sorted(n.lineno for n in ast.walk(funcs[0]) if isinstance(n,ast.Assert))


def original79_from_raw():
    archive=ROOT/'docs/implementation/evidence/adr0031-i5/author-evidence.zip'
    expected=jread(ROOT/'docs/implementation/evidence/adr0031-i6a/author/baseline/historical-source.json')
    assert hashlib.sha256(raw(archive)).hexdigest()==expected['sha256']
    with zipfile.ZipFile(BytesIO(raw(archive))) as z:
        payloads={name:z.read(name) for name in expected['members']}
    assert all(len(payloads[name])==meta['size'] and hashlib.sha256(payloads[name]).hexdigest()==meta['sha256'] for name,meta in expected['members'].items())
    selected=payloads['author-3.53.1/regressions.selected.txt'].decode().splitlines()
    keymap={nodekey(n):n for n in selected}
    assert len(selected)==len(keymap)
    results={}
    for c in ET.fromstring(payloads['author-3.53.1/regressions.xml']).iter('testcase'):
        e=c.find('failure')
        phase='call'
        if e is None:e=c.find('error');phase='setup'
        if e is None:continue
        n=keymap[(c.get('classname'),c.get('name'))]
        assert n not in results
        results[n]={'phase':phase,'message':e.get('message',''),'frames':frames(e.text or ''),'trace_sha256':hashlib.sha256((e.text or '').encode()).hexdigest()}
    assert len(results)==79
    return results


def main():
    before, br=receipt(E/'before')
    after, ar=receipt(E/'after-final')
    author=ROOT/'docs/implementation/evidence/adr0031-i6a/author/final-v3'
    old=jread(author/'inherited-79-node-phase-exception-assertion-map.json')['rows']
    oldkeys={(r['class'],r['name']):r for r in old}
    raw79=original79_from_raw()
    before_obs,bobs_receipt,bobs_nodes=assertions(E/'classification/before-assertion-diagnostic/assertions')
    after_obs,aobs_receipt,aobs_nodes=assertions(E/'after-final/assertions')
    historical={n for n in before if nodekey(n) in oldkeys}
    assert len(historical)==79
    failed={n for n,r in before.items() if r['outcome']!='passed'}
    assert len(failed)==743
    assert bobs_nodes==failed and aobs_nodes==set(after)
    assert set(raw79)==historical
    assert len(failed-historical)==664
    sup=supplements()
    bsup=supplements(BEFORE,True)
    rows=[]
    for n in sorted(failed):
        b,a=before[n],after[n]
        cat,proof=classify(a,sup.get(n,()))
        bcat,bproof=classify(b,bsup.get(n,()),commit=BEFORE)
        oldr=oldkeys.get(nodekey(n))
        before_asserts=literal_assertions(n,BEFORE)
        after_asserts=literal_assertions(n,TARGET)
        reach={}
        for label,obs,static in [('before',before_obs,before_asserts),('after',after_obs,after_asserts)]:
            reach[label]={'local_function_identified':static is not None,'static_literal_assertion_lines':static,'entered_literal_assertions':sorted({r['line'] for r in obs.get(n,[]) if r['phase']=='call' and r['path']==n.split('::')[0] and r['line'] in (static or [])})}
        rows.append({'nodeid':n,'historical79':n in historical,'before':b,'after':a,'top_exception_before':b['message'].split(':',1)[0] if b['message'] else None,'top_exception_after':a['message'].split(':',1)[0] if a['message'] else None,'after_test_body_entered':a['phase']!='setup','first_semantic_boundary_after':next((f for f in proof if f.get('actual_failed_sql_call') or 'raise AdmissionRefused' in f['source'] or 'raise UnsupportedResourceStage' in f['source']),None),'before_classification':bcat,'classification':cat,'classification_source_proof':proof,'before_source_proof':bproof,'phase_unchanged':b['phase']==a['phase'],'message_unchanged':b['message']==a['message'],'path_function_sequence_unchanged':[(f['path'],f['function']) for f in b['frames']]==[(f['path'],f['function']) for f in a['frames']],'historical141':oldr,'original_raw79':raw79.get(n),'reachability_archived':reach})
    changed=subprocess.check_output(['git','diff','--name-only',BEFORE,TARGET,'--','tests'],cwd=ROOT,text=True).splitlines()
    changes=[]
    for p in changed:
        if not p.endswith('.py'):continue
        try: bi=assertion_inventory(p,BEFORE)
        except subprocess.CalledProcessError:continue
        ai=assertion_inventory(p,TARGET)
        for n,orig in bi.items():
            if n not in ai or orig!=ai[n]:changes.append({'path':p,'function':n,'before':orig,'after':ai.get(n)})
    ledger=jread(E/'classification/final/failure-ledger-reviewed.json')['rows']
    reported={r['nodeid']:r for r in ledger}
    def expect(c):return {'PASS':None,'I6-C':'unconnected_provider_exchange_guard','I7-composition':'recovery_context_composition_unconnected','Transfer-stage':'retained_transfer_stage_refusal'}.get(c,'UNRESOLVED')
    disagreements=[n for n in failed if expect(next(r['classification'] for r in rows if r['nodeid']==n))!=reported[n]['after_category']]
    summary={'assertion_archived_before_receipt':bobs_receipt,'assertion_archived_after_receipt':aobs_receipt,'literal_assertion_entry_before743':sum(bool(r['reachability_archived']['before']['entered_literal_assertions']) for r in rows),'literal_assertion_entry_after743':sum(bool(r['reachability_archived']['after']['entered_literal_assertions']) for r in rows),'historical79_final_phase_matches_original':sum(r['after']['phase']==r['original_raw79']['phase'] for r in rows if r['historical79']),'historical79_final_message_matches_original':sum(r['after']['message']==r['original_raw79']['message'] for r in rows if r['historical79']),'historical79_final_paths_functions_match_original':sum([(f['path'],f['function']) for f in r['after']['frames']]==[(f['path'],f['function']) for f in r['original_raw79']['frames']] for r in rows if r['historical79']),'before_receipt':br,'after_receipt':ar,'removed_nodes':sorted(set(before)-set(after)),'added_nodes':sorted(set(after)-set(before)),'new_unsuccessful':sorted(n for n in set(after)-failed if after[n]['outcome']!='passed'),'all743':dict(Counter(r['classification'] for r in rows)),'additional664_before':dict(Counter(r['before_classification'] for r in rows if not r['historical79'])),'additional664_transition':dict(Counter(str((r['before_classification'],r['classification'])) for r in rows if not r['historical79'])),'additional664':dict(Counter(r['classification'] for r in rows if not r['historical79'])),'historical79':dict(Counter(r['classification'] for r in rows if r['historical79'])),'historical79_phase_transition':dict(Counter(str((r['before']['phase'],r['after']['phase'])) for r in rows if r['historical79'])),'historical79_message_equal_before_after':sum(r['message_unchanged'] for r in rows if r['historical79']),'historical79_path_function_equal_before_after':sum(r['path_function_sequence_unchanged'] for r in rows if r['historical79']),'author_category_disagreements':disagreements,'assertion_or_raises_or_decorator_changes':len(changes),'independence':'Separate stdlib parser, exact raw JUnit/journal/report sidecars; no Author classifier imports. Current source-stack classifications derive from actual traceback coordinates plus source text; caught-exception supplement is Author provenance until fresh diagnostic supplied.'}
    for name,data in [('failure-comparison.json',rows),('summary.json',summary),('assertion-changes.json',changes),('inputs.json',inputs)]:
        payload=(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode()
        if name=='failure-comparison.json':
            (OUT/(name+'.gz')).write_bytes(gzip.compress(payload,mtime=0))
            if (OUT/name).exists():(OUT/name).unlink()
        else:(OUT/name).write_bytes(payload)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
