"""Fresh official SQLite source downloads/builds for C-F1 author validation."""
import concurrent.futures,hashlib,json,pathlib,subprocess,time,urllib.request,zipfile
B=pathlib.Path(__file__).resolve().parent
def prepare(n):
    d=B/'runtime'/('sqlite-amalgamation-'+n);d.parent.mkdir(exist_ok=True)
    url='https://www.sqlite.org/2026/sqlite-amalgamation-'+n+'.zip'
    archive=d.parent/(d.name+'.zip');archive.write_bytes(urllib.request.urlopen(url).read())
    with zipfile.ZipFile(archive) as z:z.extractall(d.parent)
    cmd=['cc','-O2','-fPIC','-shared','-DSQLITE_THREADSAFE=1','-DSQLITE_ENABLE_FTS5','-DSQLITE_ENABLE_COLUMN_METADATA','-DSQLITE_ENABLE_RTREE',str(d/'sqlite3.c'),'-o',str(d/'libsqlite3.so.0'),'-lpthread','-ldl','-lm']
    t=time.monotonic();p=subprocess.run(cmd,capture_output=True,text=True)
    record={'url':url,'download_bytes':archive.stat().st_size,'download_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'command':cmd,'exit_code':p.returncode,'seconds':time.monotonic()-t,'stdout':p.stdout,'stderr':p.stderr,'files':{name:hashlib.sha256((d/name).read_bytes()).hexdigest() for name in ['sqlite3.c','sqlite3.h','libsqlite3.so.0'] if (d/name).exists()}}
    (d/'provenance.json').write_text(json.dumps(record,indent=2)+'\n');return n,record
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    records=dict(pool.map(prepare,['3510300','3530100']))
(B/'runtime-provenance.json').write_text(json.dumps(records,indent=2)+'\n')
assert all(r['exit_code']==0 for r in records.values())
print(json.dumps({n:{'exit_code':v['exit_code'],'download_sha256':v['download_sha256']} for n,v in records.items()}))
