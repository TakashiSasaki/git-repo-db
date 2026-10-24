import sys,json,zipfile,hashlib,xml.etree.ElementTree as ET
from pathlib import Path
root=Path('/workspace/adr0033-review');out=Path('/tmp/adr0033-rereview');sys.path.insert(0,str(root))
from scripts.compare_i5_failures import index,compare
sha=lambda b:hashlib.sha256(b).hexdigest()
basezip=root/'docs/implementation/evidence/adr0033-independent-review-20261023/raw-evidence.zip'
authorzip=root/'docs/implementation/evidence/adr0033-archive-hardening-20261023/raw-evidence.zip'
raws={}
with zipfile.ZipFile(basezip) as z:raws['historical133']=z.read('baseline-regressions.xml')
with zipfile.ZipFile(authorzip) as z:raws['author142']=z.read('broad/regressions.xml')
raws['independent142']=(out/'broad/regressions.xml').read_bytes()
def rawindex(raw):
 r={}
 for c in ET.fromstring(raw).findall('.//testcase'):
  for tag in ('failure','error'):
   e=c.find(tag)
   if e is not None:r[(c.get('classname'),c.get('name'))]=(tag,e.get('message'),e.text)
 return r
results={}
for tag in ('historical133','author142'):
 result=compare(index(raws[tag]),index(raws['independent142']))
 old=rawindex(raws[tag]);new=rawindex(raws['independent142']);result['same_full_raw_failure_signatures']=sum(old[k]==new.get(k) for k in old)
 result['different_full_raw_signatures']=[{'class':k[0],'name':k[1]} for k in old if old[k]!=new.get(k)]
 result['summary']={key:sum(bool(c[key]) for c in result['comparison']) for key in ('same_phase','same_message','same_stage_refusal','same_trace_paths_functions')}
 result['baseline_xml_sha256']=sha(raws[tag]);result['current_xml_sha256']=sha(raws['independent142'])
 (out/('failure-comparison-'+tag+'.json')).write_text(json.dumps(result,indent=2)+'\n');results[tag]={k:v for k,v in result.items() if k in ('baseline_non_successes','current_non_successes','same_nodes','additional','resolved','same_full_raw_failure_signatures','summary','baseline_xml_sha256','current_xml_sha256')}
(out/'baseline-comparison-summary.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
