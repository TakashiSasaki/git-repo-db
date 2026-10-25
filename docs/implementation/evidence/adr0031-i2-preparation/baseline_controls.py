"""Inspect actual frozen DDL and compare the historical helper, read-only sources."""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.resource_identity import encode_identity as J, parse_identity

root=Path(__file__).resolve().parent
S='aad25448-03eb-4f83-a578-ceec84375b5a'
db=sqlite3.connect(':memory:',isolation_level=None)
p1_schema.register_functions(db)
db.executescript('PRAGMA foreign_keys=ON; PRAGMA recursive_triggers=ON;'+p1_schema.compose('context'))
db.execute("INSERT INTO providers VALUES(?,'synthetic','{}')",(S,))
cases=[]
for name,row in (
    ('ordinary-canonical-issue',(S,'issue',J('7'),None,None,None,None)),
    ('raw-noncanonical-issue',(S,'issue','731',None,None,None,None)),
    ('unknown-kind',(S,'vendor_widget',J('V'),None,None,None,None)),
    ('global-document',(S,'document',J('D'),None,None,None,J('D'))),
    ('child-with-absent-namespace',(S,'comment',J(['issue',J('absent'),'timeline_event','E']),'issue',J('absent'),'timeline_event','E')),
    ('native-array-local',(S,'comment',J(['issue',J('7'),'timeline_event',['github:node_id','EV']]),'issue',J('7'),'timeline_event',J(['github:node_id','EV'])))):
    trace=[];db.set_trace_callback(trace.append)
    record={'case':name,'parameters':row,'before':db.execute('SELECT * FROM resources ORDER BY 1,2,3').fetchall()}
    try:
        db.execute('INSERT INTO resources VALUES(?,?,?,?,?,?,?)',row)
        record['outcome']='accepted'
        try:
            ResourceKey(*row[:3]);record['strict_reconstruction']='accepted'
        except (ValueError,TypeError) as error:
            record['strict_reconstruction']=str(error)
    except sqlite3.Error as error:
        record.update(outcome='refused',message=str(error),code=error.sqlite_errorcode,name=error.sqlite_errorname)
    record.update(after=db.execute('SELECT * FROM resources ORDER BY 1,2,3').fetchall(),trace=trace)
    cases.append(record)
db.set_trace_callback(None)
candidate=root/'repo/docs/implementation/evidence/context-resource-design/g3-a/candidates/cprime.py'
spec=importlib.util.spec_from_file_location('historical_cp',candidate)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
differential=[]
for name,raw in [('33-empty-array-containers','['*33+']'*33),('32-empty-array-containers','['*32+']'*32)]:
    row={'case':name,'input':raw}
    for label,fn in [('experimental',module.identity),('I1',parse_identity)]:
        try:fn(raw);row[label]='accepted'
        except (ValueError,TypeError) as error:row[label]='refused: '+str(error)
    differential.append(row)
assert differential[0]['experimental']=='accepted' and differential[0]['I1'].startswith('refused')
result={'scope':'unchanged actual product DDL controls plus historical-helper differential',
        'sqlite':sqlite3.sqlite_version,'source_id':db.execute('SELECT sqlite_source_id()').fetchone()[0],
        'baseline_ddl_sha256':p1_schema.fingerprint('context'),'cases':cases,'helper_differential':differential}
(root/sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'sqlite':result['sqlite'],'controls':len(cases),'helper_differential':differential}))
