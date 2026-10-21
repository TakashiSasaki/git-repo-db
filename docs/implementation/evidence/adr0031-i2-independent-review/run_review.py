"""Reproduce final Task D lanes with durable measured process receipts."""
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import time

B=pathlib.Path(__file__).resolve().parent
REPO=pathlib.Path('/workspace/task-d-review')
rows=[]
for short,version,number in [('3513','3.51.3','3510300'),('3531','3.53.1','3530100')]:
    overrides={'LD_LIBRARY_PATH':str(B/'runtime'/('sqlite-amalgamation-'+number)),
               'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(REPO/'src')+':'+str(B/'author-rerun')}
    env=os.environ.copy();env.update(overrides)
    for lane,cmd in [
        ('candidate-author-'+short,['/usr/bin/python3.13',str(B/'author-rerun/probe.py'),'verified-'+short,version]),
        ('independent-'+short,['/usr/bin/python3.13',str(B/'independent_review.py'),str(B/('verified-'+short)),version])]:
        path=B/(lane+'.log');started=datetime.datetime.now(datetime.UTC).isoformat();t=time.monotonic()
        with path.open('w') as f:p=subprocess.run(cmd,cwd=B,env=env,stdout=f,stderr=subprocess.STDOUT)
        item={'lane':lane,'argv':cmd,'cwd':str(B),'environment_overrides':overrides,'started_at':started,'seconds':time.monotonic()-t,'exit_code':p.returncode,'output':path.name,'output_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        rows.append(item);print(json.dumps(item),flush=True)
(B/'process-receipts.json').write_text(json.dumps(rows,indent=2)+'\n')
assert [r['exit_code'] for r in rows]==[0,1,0,1],rows
