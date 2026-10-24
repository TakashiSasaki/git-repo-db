import subprocess,os,json,time,sys
from pathlib import Path
root=Path('/workspace/adr0033-review');out=Path('/tmp/adr0033-rereview');py=str(root/'.venv/bin/python')
os.environ.update(PATH=str(root/'.venv/bin')+os.pathsep+os.environ['PATH'],UV_CACHE_DIR='/workspace/.uv-cache',UV_PYTHON_DOWNLOADS='never')
sys.path.insert(0,str(root))
from scripts import verify_i5_offline as evidence
records=json.loads((out/'processes.json').read_text())
def run(name,args,cwd=root):
 start=time.time()
 with (out/(name+'.log')).open('w') as f:
  p=subprocess.run(list(map(str,args)),cwd=cwd,stdout=f,stderr=subprocess.STDOUT)
 row={'name':name,'argv':list(map(str,args)),'cwd':str(cwd),'started_epoch':start,'wall_seconds':time.time()-start,'exit_code':p.returncode}
 records.append(row);(out/'processes.json').write_text(json.dumps(records,indent=2)+'\n');print(json.dumps(row),flush=True);return p.returncode
focus=out/'focused';focus.mkdir()
runs={}
for name,targets in [('packaging',['tests/packaging']),('ci-focused',['tests/unit/test_ci_plan.py','tests/unit/test_ci_journal.py','tests/unit/test_ci_profile.py','tests/unit/test_test_efficiency.py','tests/integration/test_ci_execution.py']),('docs-tests',['tests/unit/test_build_docs_site.py'])]:
 nodes,collection=evidence.collect(focus,name+'-collection',targets,'not live and not benchmark');assert collection['exit_code']==0
 runs[name]=evidence.run_cohort(focus,name,nodes,0)
(focus/'summary.json').write_text(json.dumps(runs,indent=2)+'\n')
run('lint',[py,'-m','ruff','check','src','tests','scripts'])
run('format',[py,'-m','ruff','format','--check','src','tests','scripts'])
run('sqlite-policy',[py,'scripts/check_sqlite_validation_policy.py'])
run('docs-build',[py,'scripts/build_docs_site.py','--no-mermaid'])
repro=root/'docs/implementation/evidence/adr0033-independent-review-20261023/reproduce'
run('measure-distributions',[py,repro/'measure_distributions.py',out/'source',out/'baseline',out/'measurement',root/'artifacts/wheelhouse'])
run('backend-isolation',[py,repro/'check_backend_isolation.py',out/'source',out/'measurement',root/'artifacts/wheelhouse',out/'backend-isolation'])
run('installed-orchestrator',[py,'scripts/verify_i5_distribution.py','--output',out/'installed'])
