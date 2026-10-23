"""Attribute unchanged external I4/I5 tests and original minimal Access smoke.

This invokes existing fixture authority only for its published test scope.
Existing isolated I4 fixture drops affect disposable test databases only; no
production installation or copied test assertions are modified by this driver.
"""

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--base",type=Path,required=True);p.add_argument("--wheelhouse",type=Path,required=True);a=p.parse_args()
    out=a.base/"installed-cohorts";out.mkdir(exist_ok=True)
    outside=out/"outside";outside.mkdir(exist_ok=True)
    sys.path.insert(0,str(a.root))
    from scripts import installed_test_harness as h
    from scripts.verify_i5_offline import verified_wheelhouse
    wheelhouse,manifest=verified_wheelhouse(a.wheelhouse)
    (out/"wheelhouse-binding.json").write_text(json.dumps(manifest,indent=2)+"\n")
    h.stage_support(a.root,outside)
    guard=outside/"network_guard";guard.mkdir(exist_ok=True)
    shutil.copy2(a.root/"tests/support/network_guard/sitecustomize.py",guard/"sitecustomize.py")
    for n,source in ((4,"test_transfer_sql.py"),(5,"test_transfer_admission.py")):
        shutil.copy2(a.root/"tests/integration/p3"/source,outside/f"test_installed_i{n}.py")
    tree=ast.parse((a.root/"scripts/verify_access_distribution.py").read_text())
    smoke=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="SMOKE" for t in n.targets))
    (outside/"original_access_smoke.py").write_text(smoke)
    trace=outside/"trace_original_smoke.py"
    trace.write_text('''import ast,json,pathlib,runpy,sys
target=pathlib.Path(sys.argv[1]).resolve()
statements=sorted(n.lineno for n in ast.walk(ast.parse(target.read_text())) if isinstance(n,ast.Assert))
reached=set()
def observe(frame,event,arg):
    if event=="line" and frame.f_code.co_filename==str(target) and frame.f_lineno in statements:reached.add(frame.f_lineno)
    return observe
try:
    sys.settrace(observe)
    runpy.run_path(str(target),run_name="__main__")
finally:
    sys.settrace(None)
    pathlib.Path(sys.argv[2]).write_text(json.dumps({"assertion_statement_lines":statements,"reached_lines":sorted(reached),"unreached_lines":sorted(set(statements)-reached),"scope":"line entry only; not successful assertion or subexpression coverage"},indent=2)+"\\n")
''')
    processes=[]
    def run(name,argv,cwd=outside,env=None):
        p=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,capture_output=True)
        (out/(name+".log")).write_bytes(p.stdout+p.stderr)
        processes.append({"name":name,"argv":list(map(str,argv)),"cwd":str(cwd),"exit_code":p.returncode,"stdout_bytes":len(p.stdout),"stderr_bytes":len(p.stderr)})
        (out/"processes.json").write_text(json.dumps(processes,indent=2)+"\n")
        return p.returncode
    deps=[r for r in manifest["wheels"] if r["name"] in {"pytest","pluggy","packaging","iniconfig","pygments"}]
    summary=[]
    for label,kind in (("direct","direct"),("derived","derived")):
        wheel=next((a.base/"run1"/kind).glob("*.whl"))
        venv=a.base/(label+"-venv");py=venv/"bin/python"
        req=out/(label+"-test-requirements.txt")
        req.write_text("".join(f"{r['name']} @ {(wheelhouse/r['file']).as_uri()} --hash=sha256:{r['sha256']}\n" for r in deps))
        env={**os.environ,"UV_CACHE_DIR":str(a.base/"uv-cache"),"PYTHONPATH":str(guard),"PATH":str(venv/"bin")+os.pathsep+os.environ["PATH"],"GIT_ALLOW_PROTOCOL":"file","REPO_CATALOG_SMOKE_AUTHORITY":str(outside/"tests/support/context_admission.py")}
        for n in ("GH_TOKEN","GITHUB_TOKEN"):env.pop(n,None)
        assert run(label+"-test-deps",["uv","pip","install","--python",py,"--offline","--no-index","--no-deps","--require-hashes","-r",req],env=env)==0
        with zipfile.ZipFile(wheel) as z:
            expected={n.removeprefix("repo_catalog/"):hashlib.sha256(z.read(n)).hexdigest()for n in z.namelist()if n.startswith("repo_catalog/")and Path(n).suffix in (".py",".sql",".json")}
        h.bind_artifact(outside,expected)
        outcomes={}
        for stage in (4,5):
            outcomes["I"+str(stage)]=h.execute_tests(run,label,stage,py,outside,out,env)
        # The unchanged original smoke deliberately requires the isolated Access
        # package to operate without httpx. Use fresh product-only installations.
        minimal=a.base/(label+"-minimal-venv")
        assert run(label+"-minimal-venv",[sys.executable,"-m","venv","--without-pip",minimal],env=env)==0
        minimalpy=minimal/"bin/python"
        assert run(label+"-minimal-install",["uv","pip","install","--python",minimalpy,"--offline","--no-deps",wheel],env=env)==0
        status=run(label+"-original-access",[minimalpy,trace,outside/"original_access_smoke.py",out/(label+"-original-access-assertions.json")],env=env)
        log=(out/(label+"-original-access.log")).read_text()
        assert status==1 and "PERMISSION_DENIED" in log
        reached=json.loads((out/(label+"-original-access-assertions.json")).read_text())
        outcomes["original_Access"]={"exit":status,"refusal":"PERMISSION_DENIED","assertions_reached":len(reached["reached_lines"]),"assertions_unreached":len(reached["unreached_lines"])}
        summary.append({"artifact":label,"wheel_sha256":hashlib.sha256(wheel.read_bytes()).hexdigest(),"outcomes":outcomes})
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary))


if __name__=="__main__":main()
