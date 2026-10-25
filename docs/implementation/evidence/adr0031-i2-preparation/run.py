"""Run final external SQL inputs sequentially and bind real exit codes."""
import hashlib
import json
import os
import pathlib
import subprocess
import time

root=pathlib.Path(__file__).resolve().parent
repo=root/'repo'
source_paths=subprocess.check_output(['git','ls-files','-z'],cwd=repo).split(b'\0')
def snapshot():
    return {p.decode():hashlib.sha256((repo/p.decode()).read_bytes()).hexdigest()
            for p in source_paths if p and (repo/p.decode()).is_file()}
before=snapshot()
summaries=[]
for lane,version,venv in (('minimum','3.51.3','venv3513'),('newer','3.53.1','venv3531')):
    env=dict(os.environ)
    env.update(PYTHONPATH=str(repo/'src'),PYTHONDONTWRITEBYTECODE='1')
    overrides={k:env[k] for k in ('PYTHONPATH','PYTHONDONTWRITEBYTECODE')}
    if lane=='minimum':
        env['LD_LIBRARY_PATH']=str(root/'runtime3513')
        overrides['LD_LIBRARY_PATH']=env['LD_LIBRARY_PATH']
    argv=[str(root/venv/'bin/python'),str(root/'probe.py'),lane,version]
    start=time.time()
    run=subprocess.run(argv,cwd=root,env=env,text=True,capture_output=True)
    (root/(lane+'-final.log')).write_text(run.stdout+run.stderr)
    receipt={'argv':argv,'cwd':str(root),'environment_overrides':overrides,
             'exit_code':run.returncode,'elapsed_seconds':time.time()-start,
             'stdout':run.stdout,'stderr':run.stderr}
    (root/(lane+'-command.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)
    summaries.append(receipt)
after=snapshot()
binding={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
         'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=repo,text=True).strip(),
         'status':subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True),
         'tracked_file_count':len(before),'before':before,'after':after,
         'changed_hashes':[p for p in before if before[p]!=after[p]]}
(root/'source-binding.json').write_text(json.dumps(binding,indent=2)+'\n')
assert not binding['changed_hashes'] and not binding['status']
assert all(r['exit_code']==0 for r in summaries)
