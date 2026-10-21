"""Independent disposable I2 SQL probes. This is not a product acceptance suite."""
import hashlib
import json
import platform
import sqlite3
import sys
from pathlib import Path

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.domain import resource_identity as codec
from repo_catalog.domain.resource_identity import encode_identity as J
from compose_proposal import compose, configure

ROOT = Path(__file__).resolve().parent
S = "aad25448-03eb-4f83-a578-ceec84375b5a"
S2 = "80f5c4f9-6d6b-4691-af3c-00ab02ad9f53"
R = "794ed540-d8d2-459e-9ec6-58eb00c9055c"
C = "3d6a82ea-658c-46ec-ae42-a60cb6fcc88d"
COLS = "service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id"
INSERT = f"INSERT INTO resources({COLS}) VALUES(?,?,?,?,?,?,?)"
results = []
trace = []
out = ROOT / sys.argv[1]
out.mkdir(exist_ok=True)
db = sqlite3.connect(out / "disposable.sqlite3", isolation_level=None)
configure(db)
assert sqlite3.sqlite_version == sys.argv[2], sqlite3.sqlite_version
ddl = compose()
(out / "composed.sql").write_text(ddl)
db.executescript(ddl)
db.execute("INSERT INTO store_identity VALUES('context',?,?)", (R,C))
for service in (S,S2):
    db.execute("INSERT INTO providers VALUES(?,'synthetic','{}')", (service,))
db.execute("INSERT INTO repository_context VALUES(?,'{}')", (R,))
# Comparison-only helpers, not proposed product tables or a Parent authority.
db.executescript("""
CREATE TABLE probe_refs(s TEXT COLLATE BINARY NOT NULL,k TEXT COLLATE BINARY NOT NULL,
 i TEXT COLLATE BINARY NOT NULL,PRIMARY KEY(s,k,i),
 FOREIGN KEY(s,k,i) REFERENCES resources(service_instance_uuidv4,resource_kind,provider_resource_id)
) STRICT, WITHOUT ROWID;
CREATE TABLE probe_typed_refs(s TEXT COLLATE BINARY NOT NULL,k TEXT COLLATE BINARY NOT NULL,
 i TEXT COLLATE BINARY NOT NULL,d TEXT COLLATE BINARY NOT NULL,n TEXT COLLATE BINARY NOT NULL,
 PRIMARY KEY(s,k,i,d,n),FOREIGN KEY(s,k,i,d,n) REFERENCES resources(
 service_instance_uuidv4,resource_kind,provider_resource_id,reference_document_kind,identifier_namespace_kind)
) STRICT, WITHOUT ROWID;
CREATE TABLE probe_document_refs(s TEXT COLLATE BINARY NOT NULL,k TEXT COLLATE BINARY NOT NULL,
 i TEXT COLLATE BINARY NOT NULL,d TEXT COLLATE BINARY NOT NULL,PRIMARY KEY(s,k,i,d),
 FOREIGN KEY(s,k,i,d) REFERENCES resources(service_instance_uuidv4,resource_kind,provider_resource_id,reference_document_kind)
) STRICT, WITHOUT ROWID;
""")


def plain(kind="issue", value="7", service=S):
    return (service,kind,J(value),None,None,None,None)


def scoped(kind="comment", ns_kind="issue", ns="7", subtype="timeline_event", local="E", service=S):
    ns_text = J(ns)
    return (service,kind,J([ns_kind,ns_text,subtype,local]),ns_kind,ns_text,subtype,J(local))


def global_doc(value="D"):
    raw=J(value)
    return (S,"document",raw,None,None,None,raw)


def rows():
    return {
        "resources": db.execute(f"SELECT {COLS},reference_document_kind FROM resources ORDER BY 1,2,3").fetchall(),
        "relations": db.execute("SELECT * FROM resource_relations ORDER BY 1,2,3").fetchall(),
        "repository_relations": db.execute("SELECT * FROM resource_repository_relations ORDER BY 1,2,3").fetchall(),
        "probe_refs": db.execute("SELECT * FROM probe_refs ORDER BY 1,2,3").fetchall(),
        "probe_typed_refs": db.execute("SELECT * FROM probe_typed_refs ORDER BY 1,2,3").fetchall(),
        "probe_document_refs": db.execute("SELECT * FROM probe_document_refs ORDER BY 1,2,3").fetchall(),
    }


def safe(value):
    if isinstance(value, bytes):
        return {"blob_hex":value.hex()}
    if isinstance(value,(list,tuple)):
        return [safe(v) for v in value]
    return value


def run(name, sql, parameters=(), *, setup=(), reject=False, expected_rows=None):
    trace.clear()
    db.set_trace_callback(trace.append)
    db.execute("SAVEPOINT probe_case")
    for query,params in setup:
        db.execute(query,params)
    before=rows()
    record={"case":name,"sql":sql,"parameters":safe(parameters),"before":before,
            "transaction_before":db.in_transaction}
    try:
        cursor=db.execute(sql,parameters)
        actual=cursor.fetchall()
        record.update(outcome="accepted", result=actual, rowcount=cursor.rowcount)
        good=not reject and (expected_rows is None or actual==expected_rows)
    except sqlite3.Error as error:
        record.update(outcome="refused", exception=type(error).__name__,message=str(error),
            sqlite_errorcode=error.sqlite_errorcode,sqlite_errorname=error.sqlite_errorname)
        good=reject
    record.update(after=rows(),transaction_after=db.in_transaction)
    if reject:
        good = good and record["before"]==record["after"]
    db.execute("ROLLBACK TO probe_case")
    db.execute("RELEASE probe_case")
    record.update(trace=list(trace), diagnostic_pass=good)
    db.set_trace_callback(None)
    results.append(record)
    if not good:
        raise AssertionError(name+": "+record.get("message",str(record.get("result"))))


run("unknown-kind-recursive",INSERT,plain("vendor_widget",["part",["",[]]]))
run("unknown-kind-nul-is-not-empty",INSERT,plain("\x00vendor_widget",["part",[]]))
run("unknown-kind-binary-case", "SELECT COUNT(*) FROM resources",setup=[(INSERT,plain("Widget")),(INSERT,plain("widget"))],expected_rows=[(2,)])
run("unknown-kind-scope-shaped-is-opaque",INSERT,plain("vendor_widget",["pull_request",J("7"),"body","D"]))
run("unknown-kind-has-no-typed-metadata",INSERT,(S,"vendor_widget",J("D"),"issue",J("7"),"x",J("D")),reject=True)
for i,value in enumerate(("D",["node",["D",[]]],"",[],[""],[[]])):
    run(f"global-{i}",INSERT,global_doc(value))
shaped=["pull_request",J("7"),"body","D"]
g=global_doc(shaped)
p=scoped("document","pull_request","7","body","D")
assert g[:3]==p[:3]
run("global-scoped-shape-initial-admission",INSERT,g)
run("scoped-pr-before-pr",INSERT,p)
run("later-namespace-arrival-does-not-create-parent-report",
    "SELECT (SELECT COUNT(*) FROM resources),(SELECT COUNT(*) FROM resource_relations)",
    setup=[(INSERT,p),(INSERT,plain("pull_request"))], expected_rows=[(2,0)])
run("global-shaped-duplicate-preserves-global",INSERT+" ON CONFLICT DO NOTHING",g,setup=[(INSERT,g)])
for first,second,label in ((g,p,"global-to-scoped"),(p,g,"scoped-to-global")):
    for prefix,suffix,verb in (("INSERT","","insert"),("INSERT OR IGNORE","","ignore"),
        ("INSERT"," ON CONFLICT DO NOTHING","do-nothing"),("INSERT OR REPLACE","","replace"),
        ("INSERT"," ON CONFLICT DO UPDATE SET provider_document_id=excluded.provider_document_id","upsert")):
        query=INSERT.replace("INSERT",prefix,1)+suffix
        run(label+"-"+verb,query,second,setup=[(INSERT,first)],reject=True)
for i,value in enumerate(("",[],["github:node_id","EV"],["nested",["",[]]])):
    run(f"composite-or-empty-local-{i}",INSERT,scoped(local=value))
for i,value in enumerate(("",[],["project","7"],[[]])):
    run(f"recursive-or-empty-namespace-{i}",INSERT,scoped(ns=value))
for i,form in enumerate((scoped("review","pull_request"),scoped("thread","review"),
                        scoped("comment","thread"),scoped("document","pull_request"))):
    run(f"known-reserved-form-{i}",INSERT,form)
for i,(kind,ns) in enumerate((("review","issue"),("thread","issue"),("document","issue"),("comment","repository"))):
    run(f"known-wrong-namespace-{i}",INSERT,scoped(kind,ns),reject=True)
run("known-comment-cannot-use-opaque-scalar",INSERT,plain("comment","opaque"),reject=True)
run("document-omitted-metadata",f"INSERT INTO resources({COLS.split(',')[0]},{COLS.split(',')[1]},{COLS.split(',')[2]}) VALUES(?,?,?)",g[:3],reject=True)
for i in range(4):
    bad=list(p);bad[3+i]=None
    run(f"partial-null-scoped-{i}",INSERT,bad,reject=True)
run("global-wrong-repeated-native-id",INSERT,(*g[:6],J("other")),reject=True)
run("native-local-double-encoded",INSERT,(*p[:6],J(J("D"))),reject=True)
run("namespace-decoded-nested-profile",INSERT,(S,"document",J(["pull_request",["project","7"],"body","D"]),"pull_request",J(["project","7"]),"body",J("D")),reject=True)
for label,kind,ident,subtype,local in (
    ("raw-namespace","pull_request","7","body",J("D")),
    ("alternate-namespace","pull_request",'"\\u0037"',"body",J("D")),
    ("forbidden-local","pull_request",J("7"),"body","null"),
    ("alternate-local","pull_request",J("7"),"body",'"\\u0044"'),
    ("missing-subtype","pull_request",J("7"),"",J("D"))):
    run("invalid-metadata-"+label,INSERT,(S,"document",p[2],kind,ident,subtype,local),reject=True)
run("projection-not-writable",f"INSERT INTO resources({COLS},reference_document_kind) VALUES(?,?,?,?,?,?,?,?)",(*p,"wrong"),reject=True)
run("global-absence-projection",f"SELECT reference_document_kind,provider_document_id=provider_resource_id FROM resources",setup=[(INSERT,g)],expected_rows=[("",1)])
run("scope-projection",f"SELECT reference_document_kind,identifier_namespace_id FROM resources",setup=[(INSERT,p)],expected_rows=[("body",J("7"))])

invalids=["731","null","true","{}","[1]",'["x",null]', '[[] ,""]',
          ' "x"','"x"\n','"\\u0078"','"\\/"','"\\u00E9"','"é"',
          '"\\ud800"','"\\udc00"','"\\udc00\\ud800"','["x",]','',"[NaN]"]
for i,raw in enumerate(invalids):
    run(f"invalid-key-{i}",INSERT,(S,"issue",raw,None,None,None,None),reject=True)
for i,value in enumerate((None,b'"7"',7,True)):
    run(f"nontext-or-affinity-key-{i}",INSERT,(S,"issue",value,None,None,None,None),reject=True)
for i in range(3):
    bad=list(plain());bad[i]=None
    run(f"null-key-component-{i}",INSERT,bad,reject=True)
run("empty-kind",INSERT,(S,"",J("7"),None,None,None,None),reject=True)
run("unregistered-service",INSERT,plain(service="5e7853d5-6002-4fb8-84ea-22a308614947"),reject=True)
run("invalid-service",INSERT,plain(service="not-a-uuid"),reject=True)
run("invalid-utf8-before-python-udf",f"INSERT INTO resources({COLS.split(',')[0]},{COLS.split(',')[1]},{COLS.split(',')[2]}) VALUES(?, 'issue',CAST(X'80' AS TEXT))",(S,),reject=True)

for label,native,raw_bad in (
    ("bytes","a"*(codec.MAX_IDENTITY_BYTES-2), '"'+"a"*(codec.MAX_IDENTITY_BYTES-1)+'"'),
    ("nodes",[""]*(codec.MAX_IDENTITY_NODES-1),'['+','.join(['""']*codec.MAX_IDENTITY_NODES)+']'),
    ("depth",None,'['*33+'"x"'+']'*33)):
    if label=="depth":
        native="x"
        for _ in range(32):native=[native]
    run("inclusive-limit-"+label,INSERT,plain("limit_"+label,native))
    run("limit-plus-one-"+label,INSERT,(S,"limit_"+label,raw_bad,None,None,None,None),reject=True)
saved_loads=codec.json.loads
def forbidden_loads(*args,**kwargs):
    raise AssertionError("unbounded decoder reached")
try:
    codec.json.loads=forbidden_loads
    for label,bad in (("bytes",'"'+'a'*262143+'"'),("depth",'['*33+'"x"'+']'*33),
                      ("nodes",'['+','.join(['""']*4096)+']'),("type",'[null]')):
        run("sql-prescan-before-json-"+label,"SELECT p1_resource_identity_v1(?)",(bad,),expected_rows=[(0,)])
finally:
    codec.json.loads=saved_loads

a=plain()
for prefix,suffix,label,reject in (("INSERT","","duplicate-pk",True),
    ("INSERT OR IGNORE","","duplicate-ignore",False),
    ("INSERT"," ON CONFLICT DO NOTHING","duplicate-do-nothing",False),
    ("INSERT OR REPLACE","","equal-replace",True),
    ("REPLACE","","replace-keyword",True),
    ("INSERT"," ON CONFLICT DO UPDATE SET provider_resource_id=excluded.provider_resource_id","equal-upsert-update",True)):
    run(label,INSERT.replace("INSERT",prefix,1)+suffix,a,setup=[(INSERT,a)],reject=reject)
for sql,label in (("UPDATE resources SET provider_resource_id=provider_resource_id","no-op-update"),
    ("UPDATE resources SET provider_resource_id='\"8\"'","key-update"),
    ("DELETE FROM resources","delete")):
    run(label,sql,setup=[(INSERT,a)],reject=True)
run("rebind-with-update", "UPDATE resources SET identifier_namespace_kind=NULL,identifier_namespace_id=NULL,document_kind=NULL,provider_document_id=provider_resource_id",setup=[(INSERT,p)],reject=True)
run("atomic-multivalue-statement",INSERT+",(?,?,?,?,?,?,?)",(*a,S,"issue","bad",None,None,None,None),reject=True)

distinctions=["",[],[""],[[]],"a","A"," A ","é","e\u0301",["a","b"],["b","a"],["a"],"[\"a\"]"]
setup=[(INSERT,plain("opaque",value)) for value in distinctions]
run("binary-all-distinct", "SELECT COUNT(*) FROM resources",setup=setup,expected_rows=[(len(distinctions),)])
run("binary-full-triple-fk", "INSERT INTO probe_refs VALUES(?,?,?)",plain("opaque","é")[:3],setup=setup)
for i,key in enumerate(((S2,"opaque",J("é")),(S,"other",J("é")),(S,"opaque",J("É")),(S,"opaque",'"é"'))):
    run(f"binary-wrong-fk-{i}","INSERT INTO probe_refs VALUES(?,?,?)",key,setup=setup,reject=True)
for i in range(3):
    key=list(a[:3]);key[i]=None
    run(f"partial-null-reference-{i}","INSERT INTO probe_refs VALUES(?,?,?)",key,setup=[(INSERT,a)],reject=True)
event=scoped()
run("typed-event-source", "INSERT INTO probe_typed_refs VALUES(?,?,?,?,?)",(*event[:3],"timeline_event","issue"),setup=[(INSERT,event)])
for i,tail in enumerate(((None,"issue"),("timeline_event",None),("body","issue"),("timeline_event","pull_request"))):
    run(f"typed-null-or-wrong-{i}","INSERT INTO probe_typed_refs VALUES(?,?,?,?,?)",(*event[:3],*tail),setup=[(INSERT,event)],reject=True)
run("global-reference-typed-absence", "INSERT INTO probe_document_refs VALUES(?,?,?,?)",(*g[:3],""),setup=[(INSERT,g)])
run("global-reference-wrong-subtype", "INSERT INTO probe_document_refs VALUES(?,?,?,?)",(*g[:3],"body"),setup=[(INSERT,g)],reject=True)
run("scoped-reference-wrong-absence", "INSERT INTO probe_document_refs VALUES(?,?,?,?)",(*p[:3],""),setup=[(INSERT,p)],reject=True)
for role in ("represents_repository","owning_repository","base_repository","head_repository"):
    owner=plain({"represents_repository":"repository","owning_repository":"issue"}.get(role,"pull_request"))
    query="INSERT INTO resource_repository_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)"
    run("preserved-role-"+role,query,(*owner[:3],role,J(R),'{"at_us":1,"domain":"provider"}','{"evidence":"original","source":"synthetic"}',1),setup=[(INSERT,owner)])
run("unknown-cannot-bypass-known-role",query,(*plain("opaque")[:3],"owning_repository",J(R),'{"at_us":1,"domain":"provider"}','{"evidence":"original","source":"synthetic"}',1),setup=[(INSERT,plain("opaque"))],reject=True)
run("transfer-stage-fence",query,(*event[:3],"transfer_from_repository",J(R),'{"at_us":1,"domain":"provider"}','{"evidence":"original","source":"synthetic"}',1),setup=[(INSERT,event)],reject=True)

# Explicit whole-unit transaction and reopen controls, separate from one-statement cases.
trace.clear();db.set_trace_callback(trace.append)
db.execute("BEGIN IMMEDIATE")
db.execute(INSERT,a)
db.execute("SAVEPOINT caller_unit")
db.execute(INSERT,global_doc("saved-prefix"))
try:
    db.execute(INSERT,plain("issue","bad-update")[:3]+("issue",J("7"),None,None))
    raise AssertionError("invalid metadata admitted")
except sqlite3.IntegrityError as error:
    actual={"message":str(error),"code":error.sqlite_errorcode,"name":error.sqlite_errorname}
    prefix=rows()
    db.execute("ROLLBACK TO caller_unit")
    db.execute("RELEASE caller_unit")
db.commit()
transaction={"failure":actual,"prefix_before_explicit_unit_rollback":prefix,"committed":rows(),"trace":list(trace)}
assert len(transaction["committed"]["resources"])==1
db.execute(INSERT,g)
db.close()
db=sqlite3.connect(out / "disposable.sqlite3",isolation_level=None)
configure(db)
reopened=rows()
assert len(reopened["resources"])==2
run("reopened-contract-rebind",INSERT+" ON CONFLICT DO NOTHING",p,reject=True)

inventory={"tables":db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'probe_%' ORDER BY name").fetchall(),
 "resource_columns":db.execute("PRAGMA table_xinfo(resources)").fetchall(),
 "resource_foreign_keys":db.execute("PRAGMA foreign_key_list(resources)").fetchall(),
 "typed_index":db.execute("PRAGMA index_xinfo(resources_typed_event_fk)").fetchall(),
 "native_index":db.execute("PRAGMA index_xinfo(resources_native_event_fk)").fetchall(),
 "function_flags":[row for row in db.execute("PRAGMA function_list") if row[0].startswith("p1_resource_")],
 "coverage_columns":db.execute("PRAGMA table_info(coverage_claims)").fetchall()}
inventory["incoming_resource_fks"]={name[0]:[
    row for row in db.execute(f'PRAGMA foreign_key_list("{name[0]}")') if row[2]=="resources"]
    for name in inventory["tables"]}
assert len(inventory["tables"])==19
assert len(inventory["coverage_columns"])==5
assert len(inventory["resource_foreign_keys"])==1
assert all(row[4]=="BINARY" for row in inventory["typed_index"] if row[5])
runtime={"python":platform.python_version(),"executable":sys.executable,
 "sqlite":sqlite3.sqlite_version,"sqlite_source_id":db.execute("SELECT sqlite_source_id()").fetchone()[0],
 "compile_options":db.execute("PRAGMA compile_options").fetchall(),
 "pragmas":{n:db.execute("PRAGMA "+n).fetchall() for n in ("foreign_keys","recursive_triggers","ignore_check_constraints","defer_foreign_keys","trusted_schema","encoding","synchronous","journal_mode")}}
validation={"foreign_keys":db.execute("PRAGMA foreign_key_check").fetchall(),"integrity":db.execute("PRAGMA integrity_check").fetchall()}
assert validation=={"foreign_keys":[],"integrity":[("ok",)]}
db.close()
# Unsupported connection settings are explicit controls, never supported PASS.
misconfiguration=[]
for pragma,value in (("foreign_keys","OFF"),("recursive_triggers","OFF"),
                      ("ignore_check_constraints","ON"),("trusted_schema","OFF")):
    bad=sqlite3.connect(":memory:",isolation_level=None)
    configure(bad)
    bad.executescript(ddl)
    bad.execute(f"PRAGMA {pragma}={value}")
    item={"pragma":pragma,"set_to":value,"status":"unsupported connection control",
          "observed":bad.execute("PRAGMA "+pragma).fetchall()}
    try:
        bad.execute("INSERT INTO providers VALUES(?,'synthetic','{}')",(S,))
        bad.execute(INSERT,p)
        if pragma=="recursive_triggers":
            bad.execute(INSERT.replace("INSERT","INSERT OR REPLACE",1),p)
        item.update(outcome="SQL accepted under unsupported configuration")
    except sqlite3.Error as error:
        item.update(outcome="SQL refused",message=str(error),code=error.sqlite_errorcode,name=error.sqlite_errorname)
    misconfiguration.append(item)
    bad.close()
receipt={"scope":"disposable I2 proposal, not implemented product DDL", "runtime":runtime,
 "cases":results,"transaction":transaction,"reopened":reopened,"inventory":inventory,"validation":validation,
 "input_hashes":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/"resource_udfs.py",ROOT/"resources.sql",ROOT/"compose_proposal.py",ROOT/"probe.py",ROOT/"repo/src/repo_catalog/domain/resource_identity.py",ROOT/"repo/src/repo_catalog/adapters/sqlite/p1_ddl/context.sql",ROOT/"repo/src/repo_catalog/adapters/sqlite/p1_schema.py"]},
 "ddl_sha256":hashlib.sha256(ddl.encode()).hexdigest(),"misconfiguration_controls":misconfiguration}
(out/"receipt.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=True)+"\n")
print(json.dumps({"runtime":runtime["sqlite"],"cases":len(results),"diagnostic_passes":sum(r["diagnostic_pass"] for r in results),"sql_refusals":sum(r["outcome"]=="refused" for r in results),"ddl_sha256":receipt["ddl_sha256"],"validation":validation}))
