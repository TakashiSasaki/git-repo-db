import json,hashlib,zipfile,subprocess,tarfile
from pathlib import Path
root=Path('/workspace/adr0033-review');out=Path('/tmp/adr0033-rereview')
sha=lambda b:hashlib.sha256(b).hexdigest()
results=[]
for name in ('adr0033-independent-review-20261023','adr0033-archive-hardening-20261023'):
 d=root/'docs/implementation/evidence'/name; idx=json.loads((d/'raw-evidence-index.json').read_text());z=d/idx['archive']
 with zipfile.ZipFile(z) as f:
  bad=[n for n,r in idx['members'].items() if len(f.read(n))!=r['bytes'] or sha(f.read(n))!=r['sha256']]
  assert not bad and set(f.namelist())==set(idx['members'])|{'payload-index.json'}
  results.append({'evidence':name,'archive_sha256':sha(z.read_bytes()),'payloads_verified':len(idx['members']),'all_match':True,'index_sha256':sha((d/'raw-evidence-index.json').read_bytes())})
(out/'historical-evidence-verification.json').write_text(json.dumps(results,indent=2)+'\n')
for name,commit in [('source','59307c40ea65554736e131cedd00f04c9906551b'),('baseline','18ba867d1c2f33c7d17939b2722d22a67139363a')]:
 dest=out/name;dest.mkdir();arc=out/(name+'.tar')
 subprocess.run(['git','archive',commit,'-o',str(arc)],cwd=root,check=True)
 with tarfile.open(arc) as t:t.extractall(dest,filter='data')
(out/'source-binding.json').write_text(json.dumps({'reviewed_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'reviewed_tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=root,text=True).strip(),'source_archive_sha256':sha((out/'source.tar').read_bytes()),'baseline_archive_sha256':sha((out/'baseline.tar').read_bytes()),'tracked_status_at_start':subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root,text=True)},indent=2)+'\n')
print(json.dumps(results,indent=2))
