"""Package completed raw local receipts without temporary databases or venvs."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parent
sources={
    'source-run':Path('/workspace/review-source-run'),
    'installed-safety':Path('/workspace/review-installed-safety'),
    'installed-completeness':Path('/workspace/review-installed-completeness'),
    'harness-probes':Path('/workspace/review-harness-probes'),
    'smokes-initial':Path('/workspace/review-installed-smokes'),
    'smokes-final':Path('/workspace/review-installed-smokes-v2'),
    'publication-checks':Path('/workspace/review-publication-checks'),
}
files={}
for label,directory in sources.items():
    for p in sorted(directory.iterdir()):
        if p.is_file(): files[label+'/'+p.name]=p
    if label=='harness-probes':
        for p in sorted(directory.glob('*/imports.json')):files[label+'/'+str(p.relative_to(directory))]=p
for name in ('review-source-wrapper.log','review-installed-wrapper.log','review-completeness-wrapper.log','review-harness-wrapper.log','review-smokes-wrapper.log','review-smokes-v2-wrapper.log','wheelhouse-prepare.log'):
    p=Path('/workspace')/name
    if p.is_file():files['wrapper-logs/'+name]=p
index={}
with zipfile.ZipFile(ROOT/'raw-local-evidence.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name,p in sorted(files.items()):
        raw=p.read_bytes();index[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()};z.writestr(name,raw)
    z.writestr('receipt-index.json',json.dumps(index,indent=2)+'\n')
with zipfile.ZipFile(ROOT/'raw-local-evidence.zip') as z:
    assert len(z.namelist())==len(set(z.namelist()))==len(index)+1
    for name,record in index.items():
        raw=z.read(name);assert len(raw)==record['bytes'] and hashlib.sha256(raw).hexdigest()==record['sha256']
(ROOT/'raw-local-index.json').write_text(json.dumps(index,indent=2)+'\n')
print(len(index),'raw files verified')
