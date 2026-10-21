import os,sys,json,subprocess,time,hashlib,pathlib,xml.etree.ElementTree as ET

BASE=pathlib.Path('/workspace/independent-task-b-20261021')
RUNTIMES={'3513':BASE/'venv3513-dynamic/bin/python','3531':BASE/'venv3531/bin/python'}
def environment(rt, tree):
    e=os.environ.copy()
    e['PATH']=str(RUNTIMES[rt].parent)+os.pathsep+e['PATH']
    e['PYTHONPATH']=str(tree/'src')+os.pathsep+str(tree)+os.pathsep+str(BASE)
    e['TMPDIR']=str(BASE/'tmp')
    if rt=='3513': e['LD_LIBRARY_PATH']=str(BASE/'runtime3513')
    return e
def run(label,rt,tree,args):
    out=BASE/'runs'/label; out.mkdir(parents=True,exist_ok=True)
    env=environment(rt,tree)
    cmd=[str(RUNTIMES[rt]),*args]
    start=time.time()
    with (out/'output.log').open('w') as f:
        p=subprocess.run(cmd,cwd=tree,env=env,stdout=f,stderr=subprocess.STDOUT)
    receipt={'argv':cmd,'cwd':str(tree),'exit':p.returncode,'seconds':time.time()-start}
    runtime=subprocess.run([str(RUNTIMES[rt]),'-c','import sqlite3,json,sys; d=sqlite3.connect(":memory:"); print(json.dumps({"python":sys.version,"version_source":d.execute("select sqlite_version(),sqlite_source_id()").fetchone(),"compile_options":d.execute("pragma compile_options").fetchall()}))'],env=env,text=True,capture_output=True,check=True)
    receipt['runtime']=json.loads(runtime.stdout)
    if (out/'junit.xml').exists():
        root=ET.parse(out/'junit.xml')
        receipt['junit']=[s.attrib for s in root.iter('testsuite')]
        receipt['failures']=[{'classname':c.get('classname'),'name':c.get('name'),'messages':[v.get('message') for v in list(c) if v.tag in ('failure','error')]} for c in root.iter('testcase') if c.find('failure') is not None or c.find('error') is not None]
    receipt['output_sha256']=hashlib.sha256((out/'output.log').read_bytes()).hexdigest()
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(label, json.dumps(receipt.get('junit',receipt['exit'])),flush=True)
    return receipt
def pytest_args(label, paths, collect=False):
    out=BASE/'runs'/label
    return ['-m','pytest','-q','-p','review_journal',*paths,'--basetemp',str(BASE/'tmp'/label),'--junitxml',str(out/'junit.xml'),*(['--collect-only'] if collect else [])]
if __name__=='__main__':
    (BASE/'tmp').mkdir(exist_ok=True)
    cohort=json.loads((BASE/'repo/docs/implementation/evidence/adr0031-i1/author/cohort.json').read_text())['cohort']
    for rt in ['3513','3531']:
        label='baseline-cohort-'+rt
        run(label,rt,BASE/'repo',pytest_args(label,cohort))
    run('baseline-ordinary-3531','3531',BASE/'repo',pytest_args('baseline-ordinary-3531',[],True))
    for rt in ['3513','3531']:
        label='remediation-ordinary-'+rt
        run(label,rt,BASE/'remediation',pytest_args(label,[],True))
    broad=json.loads((BASE/'remediation-author-receipts/cohort.json').read_text())
    for rt in ['3513','3531']:
        label='remediation-broad-'+rt
        run(label,rt,BASE/'remediation',pytest_args(label,broad))
    for rt in ['3513','3531']:
        run('remediation-distribution-'+rt,rt,BASE/'remediation',['scripts/verify_access_distribution.py'])
