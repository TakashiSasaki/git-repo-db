"""Sequential selected-closure VM work with unrelated normalized pending roots."""
import copy
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import uuid

import repo_catalog
from repo_catalog.adapters.sqlite.exchange import Graph,canonical

spec=importlib.util.spec_from_file_location("independent",pathlib.Path(__file__).with_name("test_independent_domain_qa.py"))
fixture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
state=pathlib.Path(tempfile.mkdtemp(prefix="pending-scale-",dir=pathlib.Path(__file__).parent))
measurements=[]
with fixture.new_store(state/"catalog") as store:
    _parser,acq,_ids,_bodies,_head=fixture.graph_fixture(store)
    initial=Graph(store.connection).export(fixture.REPO,git_acquisition_id=acq)
    origin=next(r for r in initial["records"] if r["table"]=="root_origins")
    original_origin_key=json.loads(origin["key"].split(":",1)[1])
    root_template=json.loads(origin["values"]["acquisition_root_id"]["$ref"].split(":",1)[1])
    def candidates(count):
        records=[]
        for _ in range(count):
            row=copy.deepcopy(origin)
            row["key"]="root_origins:"+canonical({c:str(uuid.uuid4()) for c in original_origin_key})
            row["values"]["acquisition_root_id"]["$ref"]="acquisition_roots:"+canonical({c:str(uuid.uuid4()) for c in root_template})
            records.append(row)
        return {**initial,"records":records}
    previous=0
    for count in (0,1000,5000):
        if count>previous:
            result=Graph(store.connection).receive(candidates(count-previous))
            assert result["staged_records"]==count,result
            assert store.one("SELECT count(*) FROM exchange_staging WHERE reason='missing_dependency'")[0]==count
        steps=0
        statements=0
        def progress():
            global steps
            steps+=1
            return 0
        def trace(_sql):
            global statements
            statements+=1
        store.connection.set_progress_handler(progress,1)
        store.connection.set_trace_callback(trace)
        selected=Graph(store.connection).export(fixture.REPO,git_acquisition_id=acq)
        store.connection.set_progress_handler(None,0)
        store.connection.set_trace_callback(None)
        assert selected==initial
        measurements.append(dict(unrelated_pending_roots=count,vm_steps=steps,statements=statements,records=len(selected["records"]),records_identical=True))
        previous=count
head=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
tree=subprocess.check_output(["git","rev-parse","HEAD^{tree}"],text=True).strip()
result=dict(source=head,tree=tree,cwd=str(pathlib.Path.cwd()),python=sys.version,sqlite=sqlite3.sqlite_version,repo_catalog=repo_catalog.__file__,state=str(state),measurements=measurements)
output=pathlib.Path(__file__).with_name("selected-pending-scale-"+head+".json")
output.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
