"""Fresh execution of frozen I2/I3 and original Access probes on both wheels."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess

SOURCE=Path('/workspace/review-installed-safety-source')
WORK=Path('/workspace/review-installed-safety-work')
OUT=Path('/workspace/review-installed-smokes-v2');OUT.mkdir(exist_ok=False)
outside=WORK/'outside'
for stage in ('i2','i3'):
    shutil.copy2(SOURCE/'scripts'/f'verify_{stage}_distribution.py',outside/f'verify_{stage}_distribution.py')
tree=ast.parse((SOURCE/'scripts/verify_access_distribution.py').read_text())
smoke=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SMOKE' for t in n.targets))
(outside/'original_access_smoke.py').write_text(smoke)
records=[]
for tag in ('direct','sdist'):
    venv=WORK/(tag+'-minimal-smoke-venv')
    p=subprocess.run(['/workspace/review-runtime/bin/python','-m','venv','--without-pip',str(venv)],capture_output=True,text=True)
    assert p.returncode==0
    artifact=next((SOURCE/'dist').glob('*.whl')) if tag=='direct' else next((WORK/'from-sdist').glob('*/dist/*.whl'))
    py=venv/'bin/python'
    install=['uv','pip','install','--python',str(py),'--offline','--no-index','--no-deps',str(artifact)]
    p=subprocess.run(install,env=dict(os.environ,UV_CACHE_DIR='/workspace/uv-cache'),capture_output=True,text=True)
    (OUT/f'{tag}-install.log').write_text(p.stdout+p.stderr)
    assert p.returncode==0
    records.append({'artifact':tag,'stage':'minimal-install','command':install,'exit_code':p.returncode})
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','GH_TOKEN','GITHUB_TOKEN')}
    env.update(PATH=str(py.parent)+os.pathsep+os.environ['PATH'],PYTHONPATH=str(outside/'tests/support/network_guard'),GIT_ALLOW_PROTOCOL='file',TMPDIR='/workspace/review-tmp',REPO_CATALOG_SMOKE_AUTHORITY=str(outside/'tests/support/context_admission.py'))
    for stage in ('i2','i3','access'):
        argv=[str(py),str(outside/('original_access_smoke.py' if stage=='access' else f'verify_{stage}_distribution.py'))]
        if stage!='access':argv+=['--output',str(OUT/f'{tag}-{stage}.json')]
        p=subprocess.run(argv,cwd=outside,env=env,capture_output=True,text=True)
        (OUT/f'{tag}-{stage}.log').write_text(p.stdout+p.stderr)
        records.append({'artifact':tag,'stage':stage,'command':argv,'cwd':str(outside),'exit_code':p.returncode})
        (OUT/'executions.json').write_text(json.dumps(records,indent=2)+'\n')
        if stage!='access':assert p.returncode==0
        else:assert p.returncode==1 and 'exchange.py' in p.stderr and 'PERMISSION_DENIED' in p.stderr
print(json.dumps(records))
