"""Run with each installed Python from an external working directory."""

import base64
import csv
import hashlib
import importlib.metadata
import io
import json
import sqlite3
import sys
from pathlib import Path

import repo_catalog
import repo_catalog.domain.context_dependencies
import repo_catalog.domain.exchange

manifest=json.loads(Path(sys.argv[1]).read_text())
package=Path(repo_catalog.__file__).resolve().parent
assert "site-packages" in package.parts
checked={}
for n,v in manifest.items():
    if not n.startswith("src/"):
        continue
    path=package.parent/n.removeprefix("src/")
    raw=path.read_bytes()
    assert len(raw)==v["bytes"] and hashlib.sha256(raw).hexdigest()==v["sha256"]
    checked[n.removeprefix("src/")]={"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}
dist=importlib.metadata.distribution("repo-catalog")
rows=list(csv.reader(io.StringIO(dist.read_text("RECORD"))))
for name,digest,size in rows:
    path=package.parent/name
    assert path.is_file(),name
    if digest:
        raw=path.read_bytes()
        actual=base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode()
        assert digest=="sha256="+actual and size==str(len(raw)),name
conn=sqlite3.connect(":memory:")
print(json.dumps({
    "python":sys.version,"executable":sys.executable,"base_executable":sys._base_executable,
    "sqlite_version":sqlite3.sqlite_version,"sqlite_source_id":conn.execute("select sqlite_source_id()").fetchone()[0],
    "sqlite_options":[r[0] for r in conn.execute("pragma compile_options")],
    "package_origin":str(package),"context_scanner_origin":repo_catalog.domain.context_dependencies.__file__,
    "exchange_origin":repo_catalog.domain.exchange.__file__,"product_files":checked,
    "installed_RECORD_rows":len(rows),"installed_RECORD_all_hashes_verified":True,
    "dependencies":{d.metadata["Name"]:d.version for d in importlib.metadata.distributions()},
},indent=2,sort_keys=True))
