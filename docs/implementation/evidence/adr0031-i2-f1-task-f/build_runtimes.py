"""Task F independent official-source builds; no author runtime reuse."""
import hashlib
import json
import pathlib
import subprocess
import sys
import urllib.request
import zipfile

root = pathlib.Path(sys.argv[1])
root.mkdir(exist_ok=False)
records = []
for number in ('3510300', '3530100'):
    url = f'https://www.sqlite.org/2026/sqlite-amalgamation-{number}.zip'
    archive = root / f'{number}.zip'
    archive.write_bytes(urllib.request.urlopen(url).read())
    with zipfile.ZipFile(archive) as z:
        z.extractall(root)
    d = root / f'sqlite-amalgamation-{number}'
    argv = ['cc', '-O1', '-g0', '-fPIC', '-shared', '-DSQLITE_THREADSAFE=1',
            '-DSQLITE_ENABLE_FTS5', '-DSQLITE_ENABLE_COLUMN_METADATA',
            '-DSQLITE_ENABLE_RTREE', str(d/'sqlite3.c'), '-o', str(d/'libsqlite3.so.0'),
            '-lpthread', '-ldl', '-lm']
    proc = subprocess.run(argv, capture_output=True, text=True)
    records.append(dict(url=url, argv=argv, exit_code=proc.returncode,
                        stdout=proc.stdout, stderr=proc.stderr,
                        files={str(p.relative_to(root)):dict(bytes=p.stat().st_size,
                               sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                               for p in (archive, d/'sqlite3.c', d/'sqlite3.h', d/'libsqlite3.so.0') if p.exists()}))
    (root/'provenance.json').write_text(json.dumps(records, indent=2)+'\n')
    print(number, proc.returncode, flush=True)
    if proc.returncode:
        sys.exit(proc.returncode)
