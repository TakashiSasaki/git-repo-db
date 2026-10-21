"""Fresh output, immutable input binding and measured child exits for Task F."""
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

repo=pathlib.Path(sys.argv[1]).resolve()
out=pathlib.Path(sys.argv[2]).resolve();out.mkdir(exist_ok=False)
here=pathlib.Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=repo,text=True).strip()
assert git('rev-parse','HEAD')=='2199a882d79c9c707fffcba3a8327ef96a3fc384'
assert git('rev-parse','HEAD^{tree}')=='b1595725bce322d04baf0f3b9b340cfdc71552a0'
files=git('ls-files').splitlines()
manifest={p:sha(repo/p) for p in files}
harness={p.name:sha(p) for p in here.glob('*.py')}
binding={'reviewed_commit':git('rev-parse','HEAD'),'reviewed_tree':git('rev-parse','HEAD^{tree}'),
         'tracked_files':manifest,'harness_inputs':harness,
         'runtimes':{n:sha(here/'runtime'/f'sqlite-amalgamation-{n}'/'libsqlite3.so.0')
                     for n in ('3510300','3530100')}}
(out/'input-binding.json').write_text(json.dumps(binding,indent=2)+'\n')
receipts=[]
for number,version in (('3510300','3.51.3'),('3530100','3.53.1')):
    overrides={'LD_LIBRARY_PATH':str(here/'runtime'/f'sqlite-amalgamation-{number}'),
               'PYTHONDONTWRITEBYTECODE':'1'}
    env=os.environ.copy();env.update(overrides)
    cmd=['/usr/bin/python3.13',str(here/'review_sql.py'),str(repo),version,str(out/number)]
    start=datetime.datetime.now(datetime.UTC).isoformat();t=time.monotonic()
    log=out/f'{number}.log'
    with log.open('w') as f: p=subprocess.run(cmd,cwd=here,env=env,stdout=f,stderr=subprocess.STDOUT)
    r={'argv':cmd,'cwd':str(here),'environment_overrides':overrides,'start_utc':start,
       'elapsed_seconds':time.monotonic()-t,'exit_code':p.returncode,'log_sha256':sha(log)}
    receipts.append(r);print(json.dumps(r),flush=True)
changed=[p for p,h in manifest.items() if sha(repo/p)!=h]
(out/'process-receipts.json').write_text(json.dumps({'children':receipts,'changed_inputs_after':changed,
    'harness_after':{p.name:sha(p) for p in here.glob('*.py')}},indent=2)+'\n')
sys.exit(1 if changed or any(r['exit_code'] for r in receipts) else 0)
