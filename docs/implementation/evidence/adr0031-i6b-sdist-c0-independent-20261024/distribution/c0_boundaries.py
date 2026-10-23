"""Observe the real, closed production ZIP without replacing any operations."""

import argparse
import base64
import hashlib
import io
import json
import os
import random
import subprocess
import sys
import zipfile
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def verify(body, fixture, binding):
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        assert z.testzip() is None
        assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in z.infolist())
        index = json.loads(z.read("receipt-index.json"))
        assert set(z.namelist()) == set(index) | {"receipt-index.json"}
        for n, v in index.items():
            raw = z.read(n)
            assert len(raw) == v["bytes"] and sha(raw) == v["sha256"]
        assert json.loads(z.read("receipt-binding.json")) == binding
        assert z.read("artifacts/access-registry/payload.txt") == fixture.read_bytes()
        return {"members": len(z.infolist()), "expanded_bytes": sum(i.file_size for i in z.infolist()), "sha256": sha(body)}


def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    fixture=a.out/"synthetic-git";fixture.mkdir(exist_ok=True)
    subprocess.run(["git","init","-q"],cwd=fixture,check=True)
    (fixture/"README").write_text("Disposable synthetic C0 experiment; no real catalog.\n")
    subprocess.run(["git","add","README"],cwd=fixture,check=True)
    subprocess.run(["git","-c","user.name=Independent synthetic review","-c","user.email=review@example.invalid","commit","-qm","synthetic C0 input"],cwd=fixture,check=True)
    payload=fixture/"artifacts/access-registry/payload.txt";payload.parent.mkdir(parents=True,exist_ok=True)
    emitter=a.root/"scripts/emit_ci_evidence.py"
    observed=a.out/"last-closed.zip"
    wrapper=a.out/"observe_closed.py"
    wrapper.write_text('''import pathlib,runpy,sys
target=str(pathlib.Path(sys.argv[1]).resolve())
observed=pathlib.Path(sys.argv[2])
def trace(frame,event,arg):
    if event=="line" and frame.f_code.co_filename==target and "body" in frame.f_locals:
        observed.write_bytes(frame.f_locals["body"])
        sys.settrace(None)
        return None
    return trace
sys.settrace(trace)
runpy.run_path(target,run_name="__main__")
''')
    env={**os.environ,"GITHUB_RUN_ID":"155000001","GITHUB_RUN_ATTEMPT":"1"}
    binding={"head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=fixture,text=True).strip(),"tree":subprocess.check_output(["git","rev-parse","HEAD^{tree}"],cwd=fixture,text=True).strip(),"run_id":env["GITHUB_RUN_ID"],"run_attempt":"1"}
    rows=[];calibration=[]
    def invoke(raw):
        payload.write_bytes(raw)
        result=subprocess.run([sys.executable,str(wrapper),str(emitter),str(observed)],cwd=fixture,env=env,capture_output=True)
        return result,observed.read_bytes()
    for wanted in (2097151,2097152,2097153,2323560):
        found=None
        for seed in range(155,175):
            entropy=random.Random(seed).randbytes(2400000)
            n=wanted-850
            visited=set()
            for attempt in range(40):
                if n in visited:
                    n+=1
                visited.add(n)
                result,body=invoke(entropy[:n])
                calibration.append({"target":wanted,"seed":seed,"input_bytes":n,"closed_zip_bytes":len(body),"exit":result.returncode,"stdout_bytes":len(result.stdout)})
                if len(body)==wanted:
                    found=(result,body,entropy[:n]);break
                n+=wanted-len(body)
            if found:break
        assert found is not None, wanted
        result,body,raw=found
        assert result.returncode==(0 if wanted<=2097152 else 1)
        if wanted>2097152:
            assert result.stdout==b""
            assert result.stderr==b"CI receipt exceeds 2 MiB compressed; retrieve the uploaded GitHub Actions artifact\n"
        else:
            lines=result.stdout.decode("ascii").splitlines()
            assert lines[0]==f"CI_RECEIPTS_BEGIN_V1 {sha(body)} {len(body)}"
            assert lines[-1]=="CI_RECEIPTS_END_V1 "+sha(body)
            chunks=[]
            for line in lines[1:-1]:
                assert line.startswith("CI_RECEIPTS_DATA_V1 ")
                chunk=line.removeprefix("CI_RECEIPTS_DATA_V1 ")
                assert len(chunk)<=120
                chunks.append(chunk)
            assert base64.b64decode("".join(chunks),validate=True)==body
        assert payload.read_bytes()==raw
        details=verify(body,payload,binding)
        (a.out/f"closed-{wanted}.zip").write_bytes(body)
        rows.append({"target_bytes":wanted,"actual_closed_zip_bytes":len(body),"input_bytes":len(raw),"input_sha256":sha(raw),"exit":result.returncode,"stdout_bytes":len(result.stdout),"stdout_sha256":sha(result.stdout),"stderr":result.stderr.decode(),**details})
    # Highly compressible >2MiB total input is allowed by the compressed contract.
    result,body=invoke(b"A"*6120000)
    assert result.returncode==0 and len(body)<2097152
    details=verify(body,payload,binding)
    assert details["expanded_bytes"]>2097152
    (a.out/"closed-expanded.zip").write_bytes(body)
    rows.append({"case":"expanded-over-limit-compressed-under-limit","actual_closed_zip_bytes":len(body),"input_bytes":6120000,"exit":result.returncode,"stdout_bytes":len(result.stdout),"stdout_sha256":sha(result.stdout),"stderr":result.stderr.decode(),**details})
    # An uninstrumented production CLI control confirms refusal is not observer-created.
    payload.write_bytes(random.Random(888).randbytes(2323560))
    result=subprocess.run([sys.executable,str(emitter)],cwd=fixture,env=env,capture_output=True)
    assert result.returncode==1 and result.stdout==b"" and b"uploaded GitHub Actions artifact" in result.stderr
    save(a.out/"uninstrumented-control.json",{"exit":result.returncode,"stdout_bytes":len(result.stdout),"stderr":result.stderr.decode()})
    save(a.out/"calibration.json",calibration)
    save(a.out/"measurements.json",{"source_head":"fee364c6d61a5feebf08dbdd830a5a57ee2d872b","emitter_sha256":sha(emitter.read_bytes()),"wrapper_sha256":sha(wrapper.read_bytes()),"fixture_binding":binding,"boundaries":rows,"workflow_sha256":sha((a.root/".github/workflows/access-registry.yml").read_bytes()),"hosted_overflow_executed":False})
    print(json.dumps(rows))


if __name__=="__main__":
    main()
