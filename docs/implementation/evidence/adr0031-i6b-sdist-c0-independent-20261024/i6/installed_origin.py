"""Read-only pytest observer asserting actual external installed product origins."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys


def pytest_sessionfinish(session, exitstatus):
    site = (Path(sys.prefix) / "lib/python3.12/site-packages/repo_catalog").resolve()
    modules = {}
    for name, module in sorted(sys.modules.items()):
        if name == "repo_catalog" or name.startswith("repo_catalog."):
            file = getattr(module,"__file__",None)
            if file:
                path = Path(file).resolve()
                assert path.is_relative_to(site), (name,str(path),str(site))
                modules[name]={"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
    assert modules
    db=sqlite3.connect(":memory:")
    result={"pytest_exitstatus":int(exitstatus),"executable":sys.executable,
        "prefix":sys.prefix,"sqlite_version":sqlite3.sqlite_version,
        "sqlite_source_id":db.execute("SELECT sqlite_source_id()").fetchone()[0],
        "all_product_origins_in_expected_site_packages":True,"modules":modules}
    db.close()
    Path(os.environ["INSTALLED_I6_ORIGINS"]).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
