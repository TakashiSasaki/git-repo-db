"""Independent explicit-configuration and late-import adversaries, installed wheels."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path('/workspace/i6a-independent')
sys.path.insert(0,str(ROOT))
from scripts import installed_test_harness as h
OUT=Path('/workspace/review-harness-probes'); OUT.mkdir(exist_ok=False)
SOURCE=Path('/workspace/review-installed-safety-source')
WHEEL=next((SOURCE/'dist').glob('*.whl'))
with zipfile.ZipFile(WHEEL) as z:
    expected={n.removeprefix('repo_catalog/'):hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('repo_catalog/') and Path(n).suffix in ('.py','.sql','.json')}
(OUT/'pyproject.toml').write_text('[tool.pytest.ini_options]\npythonpath=["/workspace/i6a-independent/src"]\n')
records=[]
for tag in ('direct','sdist'):
    py=Path('/workspace/review-installed-safety-work')/(tag+'-venv/bin/python')
    for case in ('positive','wrong-hash','late-module'):
        outside=OUT/(tag+'-'+case); outside.mkdir()
        h.stage_support(SOURCE,outside); h.bind_artifact(outside,expected)
        code='import sys\nfrom pathlib import Path\nimport repo_catalog\ndef test_installed():\n    assert Path(repo_catalog.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())\n'
        if case=='wrong-hash':
            altered=dict(expected);altered['__init__.py']='0'*64
            (outside/'artifact-files.json').write_text(json.dumps(altered))
        if case=='late-module':
            code+='    import types\n    m=types.ModuleType("repo_catalog.injected_reviewer")\n    m.__file__="/workspace/untrusted-synthetic/reviewer.py"\n    sys.modules[m.__name__]=m\n'
        (outside/'test_probe.py').write_text(code)
        env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','GH_TOKEN','GITHUB_TOKEN')}
        env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',REPO_CATALOG_IMPORT_RECEIPT=str(outside/'imports.json'))
        argv=[str(py),'-m','pytest','-q','test_probe.py','-c',str(outside/'pytest.ini'),'--rootdir='+str(outside),'--confcutdir='+str(outside)]
        p=subprocess.run(argv,cwd=outside,env=env,capture_output=True,text=True)
        (OUT/(tag+'-'+case+'.log')).write_text(p.stdout+p.stderr)
        receipts=json.loads((outside/'imports.json').read_text()) if (outside/'imports.json').exists() else []
        if case=='positive':
            assert p.returncode==0 and [r['phase'] for r in receipts]==['sessionstart','sessionfinish']
        else:
            assert p.returncode!=0 and 'AssertionError' in p.stdout+p.stderr
            assert len(receipts)==int(case=='late-module')
        records.append({'artifact':tag,'case':case,'argv':argv,'exit_code':p.returncode,'phases':[r['phase'] for r in receipts],'expected_outcome_verified':True,'imports':receipts})
(OUT/'result.json').write_text(json.dumps(records,indent=2)+'\n')
print('6 independent installed harness controls verified (2 success, 4 expected failure)')
