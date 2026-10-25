"""Run bounded C-F1 author validation; never claim independent review."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

P=argparse.ArgumentParser()
P.add_argument('output',type=pathlib.Path)
P.add_argument('--runtime-root',type=pathlib.Path,required=True)
P.add_argument('--python',default='/usr/bin/python3.13')
args=P.parse_args();args.output.mkdir(parents=True,exist_ok=False)
HERE=pathlib.Path(__file__).resolve().parent;REPO=HERE.parents[3]
base=json.loads((HERE/'base-input-manifest.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()==base['base'] or subprocess.check_output(['git','merge-base',base['base'],'HEAD'],cwd=REPO,text=True).strip()==base['base']
base_changes=[p for p,h in base['files'].items() if sha(REPO/p)!=h]
assert not base_changes,base_changes
inputs={str(p.relative_to(REPO)):sha(p) for p in HERE.iterdir() if p.is_file() and p.suffix in ['.py','.sql','.md','.json']}
binding={'role':'C-F1 author verification, independent review pending','base':base['base'],'base_tree':base['base_tree'],'base_files_verified':len(base['files']),'base_manifest_sha256':sha(HERE/'base-input-manifest.json'),'changed_base_inputs':base_changes,'new_design_and_harness_inputs':inputs,'runtimes':{}}
processes=[]
for label,number,version in [('3513','3510300','3.51.3'),('3531','3530100','3.53.1')]:
    rt=args.runtime_root/('sqlite-amalgamation-'+number)
    binding['runtimes'][label]={name:sha(rt/name) for name in ['sqlite3.c','sqlite3.h','libsqlite3.so.0']}
    envvars={'LD_LIBRARY_PATH':str(rt),'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(REPO/'src')+':'+str(HERE)+':'+str(HERE.parent/'adr0031-i2-preparation')}
    env=os.environ.copy();env.update(envvars)
    cmd=[args.python,str(HERE/'probe_f1.py'),str(args.output/('sqlite-'+label)),version]
    start=datetime.datetime.now(datetime.UTC).isoformat();t=time.monotonic()
    log=args.output/(label+'.log')
    with log.open('w') as f:p=subprocess.run(cmd,cwd=REPO,env=env,stdout=f,stderr=subprocess.STDOUT)
    item={'lane':label,'argv':cmd,'cwd':str(REPO),'environment_overrides':envvars,'start_utc':start,'seconds':time.monotonic()-t,'exit_code':p.returncode,'log_sha256':sha(log)}
    processes.append(item);print(json.dumps(item),flush=True)
binding['new_inputs_after']={p:sha(REPO/p) for p in inputs}
binding['base_changes_after']=[p for p,h in base['files'].items() if sha(REPO/p)!=h]
assert binding['new_inputs_after']==inputs and not binding['base_changes_after']
(args.output/'input-binding.json').write_text(json.dumps(binding,indent=2)+'\n')
(args.output/'process-receipts.json').write_text(json.dumps({'processes':processes},indent=2)+'\n')
sys.exit(1 if any(p['exit_code'] for p in processes) else 0)
