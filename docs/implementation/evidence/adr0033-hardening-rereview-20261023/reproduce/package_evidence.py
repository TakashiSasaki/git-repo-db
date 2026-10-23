import json,hashlib,zipfile,shutil
from pathlib import Path
root=Path('/workspace/adr0033-review');out=Path('/tmp/adr0033-rereview');dest=root/'docs/implementation/evidence/adr0033-hardening-rereview-20261023'
sha=lambda b:hashlib.sha256(b).hexdigest()
files=list(p for p in out.iterdir() if p.is_file() and p.suffix in {'.json','.log','.txt','.py','.xml','.jsonl'})
for name in ('broad','focused','measurement','backend-isolation','installed'):
 files.extend(p for p in (out/name).iterdir() if p.is_file() and p.suffix in {'.json','.log','.txt','.py','.xml','.jsonl'})
files.extend(p for p in (out/'installed/outside').rglob('*.py') if '__pycache__' not in p.parts)
files=sorted(set(files));members={str(p.relative_to(out)):{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in files}
zpath=dest/'raw-evidence.zip'
with zipfile.ZipFile(zpath,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in files:z.write(p,str(p.relative_to(out)))
 z.writestr('payload-index.json',json.dumps(members,sort_keys=True,indent=2)+'\n')
idx={'archive':zpath.name,'bytes':zpath.stat().st_size,'sha256':sha(zpath.read_bytes()),'payload_members':len(members),'members':members}
(dest/'raw-evidence-index.json').write_text(json.dumps(idx,indent=2)+'\n')
for name in ('verification-summary.json','baseline-comparison-summary.json','trace-difference-audit.json','verified-input-binding.json','historical-evidence-verification.json','setup-failures.json'):
 shutil.copyfile(out/name,dest/name)
for name in ('measurements.json','sdist-contract.json','after-members.json','before-members.json'):
 shutil.copyfile(out/'measurement'/name,dest/name)
for name in ('run.py','stage2.py','stage3.py','compare.py','summarize.py','prepare_evidence.py','package_evidence.py'):
 shutil.copyfile(out/name,dest/'reproduce'/name)
with zipfile.ZipFile(zpath) as z:
 assert set(z.namelist())==set(members)|{'payload-index.json'}
 for name,record in members.items():
  b=z.read(name);assert len(b)==record['bytes'] and sha(b)==record['sha256']
print(json.dumps({k:v for k,v in idx.items() if k!='members'},indent=2))
