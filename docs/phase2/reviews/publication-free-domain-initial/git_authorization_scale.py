"""Count actual record visits in the canonical-byte authorization algorithm."""
import base64
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

import repo_catalog
from repo_catalog.adapters.sqlite.exchange import Graph,canonical,encode

spec=importlib.util.spec_from_file_location("independent",pathlib.Path(__file__).with_name("test_independent_domain_qa.py"))
fixture=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
state=pathlib.Path(tempfile.mkdtemp(prefix="authorization-scale-",dir=pathlib.Path(__file__).parent))
table_reads=0
class Counted(dict):
    def __getitem__(self,key):
        global table_reads
        if key=="table":
            table_reads+=1
        return super().__getitem__(key)

def record(table,values,key_fields=None):
    identity={k:values[k] for k in key_fields} if key_fields else values
    return Counted(key=table+":"+canonical(identity),table=table,values=values)

results=[]
with fixture.new_store(state/"catalog") as store:
    _parser,acq,_ids,_bodies,_head=fixture.graph_fixture(store)
    graph=Graph(store.connection)
    repo_key=graph.key("repositories",graph.lookup("repositories",("repository_uuidv4",),(fixture.REPO,)))
    acq_key=graph.key("git_acquisitions",graph.lookup("git_acquisitions",("git_acquisition_id",),(acq,)))
    ref=lambda key,col:{"$ref":key,"column":col}
    for volume in (32,128,512,1024):
        records=[]
        for n in range(volume):
            raw=("unique authorization QA blob %d"%n).encode()
            digest=hashlib.sha256(raw).digest()
            obj=record("git_objects",dict(object_format="sha1",oid=encode(fixture.oid("sha1","blob",raw)),type="blob",size=len(raw),verified=1),("object_format","oid"))
            stored=record("stored_bytes",dict(sha256=encode(digest,"sha256"),body=encode(raw),byte_length=len(raw)),("sha256",))
            payload=record("payloads",dict(representation="git-object-raw-v1",sha256=ref(stored["key"],"sha256")))
            mapping=record("git_object_payloads",dict(git_object_id=ref(obj["key"],"git_object_id"),payload_representation=ref(payload["key"],"representation"),payload_sha256=ref(payload["key"],"sha256")),("git_object_id",))
            association=record("repository_object_sources",dict(repository_uuidv4=ref(repo_key,"repository_uuidv4"),git_object_id=ref(obj["key"],"git_object_id"),git_acquisition_id=ref(acq_key,"git_acquisition_id")))
            records.extend((obj,stored,payload,mapping,association))
        records.sort(key=lambda r:(r["table"],r["key"]))
        for row in records:
            graph.validate_record(row)
        table_reads=0
        authorization=graph._git_authorizations(records)
        assert len(authorization)==4*volume
        results.append(dict(selected_git_objects=volume,wire_records=len(records),table_record_visits=table_reads,authorized_records=len(authorization)))
head=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
tree=subprocess.check_output(["git","rev-parse","HEAD^{tree}"],text=True).strip()
result=dict(source=head,tree=tree,cwd=str(pathlib.Path.cwd()),python=sys.version,sqlite=sqlite3.sqlite_version,repo_catalog=repo_catalog.__file__,state=str(state),measurements=results)
pathlib.Path(__file__).with_name("git-authorization-scale-"+head+".json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
