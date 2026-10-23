"""Independent complete product-file/wheel/RECORD and CLI verification."""
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

SOURCE = Path('/workspace/review-installed-safety-source')
WORK = Path('/workspace/review-installed-safety-work')
OUT = Path('/workspace/review-installed-completeness')
OUT.mkdir(exist_ok=False)
artifacts = [next((SOURCE/'dist').glob('*.whl')), next((WORK/'from-sdist').glob('*/dist/*.whl'))]
maps=[]
for artifact in artifacts:
    with zipfile.ZipFile(artifact) as z:
        files={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
    record_name=next(n for n in files if n.endswith('.dist-info/RECORD'))
    records=list(csv.reader(io.StringIO(files[record_name].decode())))
    assert {r[0] for r in records} == set(files)
    for name, encoded, size in records:
        if name == record_name:
            assert not encoded and not size
        else:
            assert encoded == 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(files[name]).digest()).decode().rstrip('=')
            assert int(size)==len(files[name])
    assert not any(n.startswith(('tests/','scripts/')) for n in files)
    maps.append(files)
assert maps[0] == maps[1], 'direct and derived wheel members differ'
expected={n[len('repo_catalog/'):]:hashlib.sha256(v).hexdigest() for n,v in maps[0].items() if n.startswith('repo_catalog/')}
source={str(p.relative_to(SOURCE/'src/repo_catalog')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE/'src/repo_catalog').rglob('*') if p.is_file()}
assert source == expected
probe = '''import hashlib,json,sqlite3,sys,repo_catalog\nfrom pathlib import Path\nr=Path(repo_catalog.__file__).resolve().parent\nassert r.is_relative_to(Path(sys.prefix).resolve())\nfiles={str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}\nprint(json.dumps({'origin':str(r),'prefix':sys.prefix,'sqlite':sqlite3.sqlite_version,'files':files}))\n'''
results=[]
for tag in ('direct','sdist'):
    venv=WORK/(tag+'-venv'); py=venv/'bin/python'
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','GH_TOKEN','GITHUB_TOKEN')}
    measured=json.loads(subprocess.check_output([str(py),'-I','-c',probe],cwd=OUT,env=env,text=True))
    assert measured['files']==expected
    cmds=[[str(venv/'bin/repo-catalog'),'doctor'],[str(py),'-I','-m','repo_catalog','--help']]
    statuses=[]
    for i,cmd in enumerate(cmds):
        p=subprocess.run(cmd,cwd=OUT,env=env,capture_output=True,text=True)
        (OUT/f'{tag}-cli-{i}.log').write_text(p.stdout+p.stderr)
        statuses.append({'command':cmd,'exit_code':p.returncode})
        assert p.returncode==0
    results.append({'artifact':tag,**measured,'cli':statuses})
(OUT/'result.json').write_text(json.dumps({'source_product_files':len(source),'extensions':{ext:sum(Path(n).suffix==ext for n in source) for ext in sorted({Path(n).suffix for n in source})},'source_equals_wheel':True,'direct_equals_derived_all_members':True,'record_verified':True,'expected':expected,'installed':results},indent=2)+'\n')
print(json.dumps({'verified_product_files':len(source),'installed_forms':len(results)}))
