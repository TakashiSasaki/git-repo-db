"""Independently bind and reconcile this review lane's raw evidence.

Arguments: checkout, raw artifact directory, output directory. No product writes.
"""

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET

REVIEWED = "fee364c6d61a5feebf08dbdd830a5a57ee2d872b"
BASE = "91827360c185cbf813277bf32a6627d894b1b20a"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def reconcile(journal, junit, collection=None, external=False):
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    starts = Counter(r["nodeid"] for r in rows if r["event"] == "start")
    assert starts and all(n == 1 for n in starts.values())
    phases = Counter((r["nodeid"], r["phase"], r["outcome"]) for r in rows if r["event"] == "phase")
    assert phases == Counter({(node, phase, "passed"):1 for node in starts for phase in ("setup", "call", "teardown")})
    assert rows[-1]["event"] == "finish" and rows[-1]["exitstatus"] == 0
    cases = list(ET.parse(junit).iter("testcase"))
    assert all(not list(case) for case in cases)
    if external:
        actual = Counter(case.attrib["name"] for case in cases)
        expected = Counter(node.split("::",1)[1] for node in starts)
    else:
        actual = Counter(case.attrib["classname"].replace(".","/")+".py::"+case.attrib["name"] for case in cases)
        expected = starts
    assert actual == expected, (actual-expected,expected-actual)
    if collection:
        selected = Counter(line for line in collection.read_text().splitlines() if "::test_" in line)
        if external:
            selected = Counter({line.split("::",1)[1]:count for line,count in selected.items()})
            assert selected == expected
        else:
            assert selected == starts
    return {"unique_nodes":len(starts),"junit_cases":len(cases),"normal_passing_phases":sum(phases.values()),"duplicate_starts":0,"missing_or_extra_nodes":0,"finish_exit":0,"collection_reconciled":collection is not None,"nodes":sorted(starts)}


def main():
    root, raw, out = map(Path,sys.argv[1:])
    out.mkdir(parents=True,exist_ok=True)
    binding=[]
    paths = git(root,"ls-tree","-r","--name-only",REVIEWED,"src/repo_catalog").decode().splitlines()
    paths += ["pyproject.toml","uv.lock","AGENTS.md","tests/support/i6a.py","tests/support/context_admission.py","tests/integration/p3/test_transfer_admission.py"]
    paths += sorted(set(line.split("::",1)[0] for line in (raw/"collection.log").read_text().splitlines() if line.startswith("tests/") and "::" in line))
    for path in sorted(set(paths)):
        current=(root/path).read_bytes()
        reviewed=git(root,"show",f"{REVIEWED}:{path}")
        base=git(root,"show",f"{BASE}:{path}")
        assert current==reviewed
        binding.append({"path":path,"bytes":len(current),"sha256":digest(current),"reviewed_git_blob":git(root,"rev-parse",f"{REVIEWED}:{path}").decode().strip(),"equal_reviewed":True,"equal_base154":current==base})
    reused_path="docs/implementation/evidence/adr0031-i6b-rereview-20261023/admission/test_retained_admission.py.txt"
    reused=(raw/"reused/test_retained_admission.py").read_bytes()
    assert reused == git(root,"show",f"{BASE}:{reused_path}")
    binding.append({"path":reused_path,"sha256":digest(reused),"bytes":len(reused),"reused_probe_equal_base154":True,"attribution":"Prior independent #154 admission probe; fixture body construction and isolated factory remain reused"})
    reconciliations={
        "retained446":reconcile(raw/"existing.jsonl",raw/"existing.xml",raw/"collection.log"),
        "reused13":reconcile(raw/"reused/journal.jsonl",raw/"reused/junit.xml",raw/"reused/collection.log",external=True),
        "actual_sql2":reconcile(raw/"actual-sql/journal.jsonl",raw/"actual-sql/junit.xml"),
    }
    for lane in ("installed-direct", "installed-derived"):
        if (raw/lane/"junit.xml").exists():
            reconciliations[lane] = reconcile(raw/lane/"journal.jsonl",raw/lane/"junit.xml",raw/lane/"collection.log")
            assert (raw/lane/"exit.txt").read_text().strip()=="0"
            assert (raw/lane/"collection.exit").read_text().strip()=="0"
            origins=json.loads((raw/lane/"origins.json").read_text())
            assert origins["pytest_exitstatus"]==0 and origins["all_product_origins_in_expected_site_packages"]
            initial=raw/lane/"initial-execution"
            if initial.exists():
                reconciliations[lane+"-initial-execution"] = reconcile(initial/"journal.jsonl",initial/"junit.xml")
    for exitfile in (raw/"existing.exit",raw/"collection.exit",raw/"independent.exit",raw/"reused/exit.txt",raw/"reused/collection.exit",raw/"actual-sql/exit.txt"):
        assert exitfile.read_text().strip()=="0",exitfile
    from repo_catalog.adapters.sqlite import p1_schema
    import repo_catalog.domain.context_admission as ca
    import repo_catalog.domain.exchange as exchange
    import repo_catalog.domain.context_wire as cw
    db=sqlite3.connect(":memory:",isolation_level=None)
    p1_schema.register_functions(db);p1_schema.configure(db)
    db.executescript(p1_schema.compose("context"))
    db.execute("INSERT INTO store_identity VALUES('context',?,?)",("5ac89b05-b306-46db-9b09-dc6f261a7b8a","af55d733-03fd-4419-b891-b483102a1f07"))
    p1_schema.validate(db,"context")
    runtime={"python":sys.version,"executable":sys.executable,"base_executable":sys._base_executable,"sqlite_version":sqlite3.sqlite_version,"sqlite_source_id":db.execute("SELECT sqlite_source_id()").fetchone()[0],"sqlite_compile_options":[row[0] for row in db.execute("PRAGMA compile_options")],"foreign_keys":db.execute("PRAGMA foreign_keys").fetchone()[0],"recursive_triggers":db.execute("PRAGMA recursive_triggers").fetchone()[0],"integrity_check":db.execute("PRAGMA integrity_check").fetchall(),"foreign_key_check":db.execute("PRAGMA foreign_key_check").fetchall(),"fences":db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name IN('i2_transfer_stage_fence','i2_transfer_report_stage_fence') ORDER BY name").fetchall(),"origins":{module.__name__:module.__file__ for module in (p1_schema,ca,exchange,cw)}}
    assert runtime["foreign_keys"]==runtime["recursive_triggers"]==1
    assert runtime["integrity_check"]==[("ok",)] and not runtime["foreign_key_check"]
    db.close()
    for name, data in (("source-binding.json",binding),("reconciliation.json",reconciliations),("runtime.json",runtime)):
        (out/name).write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    for path in sorted(raw.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or "installed-harness" in path.parts:
            continue
        destination=out/"raw"/path.relative_to(raw)
        destination.parent.mkdir(parents=True,exist_ok=True)
        data=path.read_bytes()
        if path.suffix in (".xml",".jsonl") or path.name in ("collection.log",):
            destination=destination.with_suffix(destination.suffix+".gz")
            destination.write_bytes(gzip.compress(data,mtime=0))
        else:
            destination.write_bytes(data)
    print(json.dumps({k:{key:value for key,value in v.items() if key!="nodes"} for k,v in reconciliations.items()},indent=2))


if __name__=="__main__":
    main()
