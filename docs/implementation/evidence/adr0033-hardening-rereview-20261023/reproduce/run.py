import subprocess,os,json,time,sys
from pathlib import Path
root=Path('/workspace/adr0033-review'); out=Path('/tmp/adr0033-rereview'); py=str(root/'.venv/bin/python')
env={**os.environ,'PATH':str(root/'.venv/bin')+os.pathsep+os.environ['PATH'],'UV_CACHE_DIR':'/workspace/.uv-cache','UV_PYTHON_DOWNLOADS':'never'}
records=[]
def run(name,args,cwd=root):
 start=time.time()
 with (out/(name+'.log')).open('w') as f:
  p=subprocess.run(list(map(str,args)),cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
 row={'name':name,'argv':list(map(str,args)),'cwd':str(cwd),'started_epoch':start,'wall_seconds':time.time()-start,'exit_code':p.returncode}
 records.append(row);(out/'processes.json').write_text(json.dumps(records,indent=2)+'\n');print(json.dumps(row),flush=True);return p.returncode
run('prepare-wheelhouse',[py,'scripts/prepare_wheelhouse.py'])
run('broad',[py,'scripts/verify_i5.py','--output',out/'broad','--workers','2'])
