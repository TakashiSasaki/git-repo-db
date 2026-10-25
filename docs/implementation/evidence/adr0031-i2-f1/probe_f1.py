"""C-F1 author verification on fresh disposable state, never independent approval.

Counts are case groups, with all constituent SQL/rowsets preserved. The routing
model is tested separately from real SQLite constraints and is not product code.
"""
import hashlib
import json
import pathlib
import sqlite3
import sys

from compose_f1 import compose, compose_before, configure
from stage_contract import Operation, StagedContextPrototype, StageUnsupported, StageStoredViolation, validate_stage_storage
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.domain.resource_identity import encode_identity as J

OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=False)
EXPECTED = sys.argv[2]
REPO = pathlib.Path(__file__).resolve().parents[4]
OLD = REPO/'docs/implementation/evidence/adr0031-i2-preparation'
TASK_D = REPO/'docs/implementation/evidence/adr0031-i2-independent-review'
S='11111111-1111-4111-8111-111111111111'
R='44444444-4444-4444-8444-444444444444'
C='55555555-5555-4555-8555-555555555555'
PROV='{"evidence":"native-observation","source":"task-c-f1"}'
CLOCK='{"at_us":17,"domain":"provider"}'
INSERT='INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES(?,?,?,?,?,?,?)'
REL='INSERT INTO resource_relations VALUES(?,?,?,?,?,?,?,?)'
EP='INSERT INTO resource_repository_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)'
E=J(['issue',J('I7'),'timeline_event','event'])
event=(S,'comment',E,'issue',J('I7'),'timeline_event',J('event'))
provider=(S,'repository',J('unresolved-R'),None,None,None,None)
# General scope JSON is deliberately separate from Identity J.
scope=json.dumps({'clock':{'at_us':17,'domain':'provider'},'event_type':'transferred','from_provider_repository_id':provider[2],'provided_roles':['transfer_from_repository'],'to_provider_repository_id':None},sort_keys=True,separators=(',',':'))
report=(S,'comment',E,'transfer_event_report',json.dumps([list(provider[:3])],separators=(',',':')),PROV,scope,17)
parent7=(S,'comment',E,'parent',json.dumps([[S,'issue',J('I7')]],separators=(',',':')),PROV,'{}',17)
parent8=(*parent7[:4],json.dumps([[S,'issue',J('I8')]],separators=(',',':')),*parent7[5:])
generic=(S,'comment',E,'vendor_relation','[]',PROV,'{}',17)
BEFORE=compose_before(); AFTER=compose()
assert AFTER.startswith(BEFORE)
(OUT/'before.sql').write_text(BEFORE);(OUT/'after.sql').write_text(AFTER)
cases=[]

def serial(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'),default=repr)

def snapshot(db):
    return {name:sorted(db.execute('SELECT * FROM "'+name+'"').fetchall(),key=serial)
            for (name,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")}

def digest(value):return hashlib.sha256(serial(value).encode()).hexdigest()

def err(e):return {'type':type(e).__name__,'message':str(e),'sqlite_errorcode':getattr(e,'sqlite_errorcode',None),'sqlite_errorname':getattr(e,'sqlite_errorname',None),'stage_code':getattr(e,'code',None)}

def fresh(*, old=False, dependencies=False):
    db=sqlite3.connect(':memory:',isolation_level=None);configure(db)
    assert db.execute('SELECT sqlite_version()').fetchone()[0]==EXPECTED
    db.executescript(BEFORE if old else AFTER)
    db.execute('INSERT INTO store_identity VALUES(?,?,?)',('context',R,C))
    db.execute("INSERT INTO providers VALUES(?,'synthetic','{}')",(S,))
    db.execute("INSERT INTO repository_context VALUES(?,'{}')",(R,))
    db.execute(INSERT,event);db.execute(INSERT,provider)
    if dependencies:
        for name in ['I7','I8']:db.execute(INSERT,(S,'issue',J(name),None,None,None,None))
        db.execute(REL,parent7);db.execute(REL,parent8)
    return db

def register_issues(db):
    for name in ['I7','I8']:db.execute(INSERT,(S,'issue',J(name),None,None,None,None))

def inject(db,kind):
    """Unsupported diagnostic fixture only; restores exact trigger before action."""
    name='i2_transfer_report_stage_fence' if kind=='report' else 'i2_transfer_stage_fence'
    ddl=db.execute('SELECT sql FROM sqlite_schema WHERE type=\'trigger\' AND name=?',(name,)).fetchone()[0]
    db.execute('DROP TRIGGER '+name)
    if kind=='report':db.execute(REL,report)
    else:db.execute(EP,(*event[:3],'transfer_from_repository','null',CLOCK,PROV,17))
    db.execute(ddl)

def case(name,action,*,expect=None,message=None,setup=None,dependencies=False,unchanged=None,family='sql',sql=None,parameters=None,expected_result=None):
    db=fresh(dependencies=dependencies);trace=[];db.set_trace_callback(trace.append)
    if setup:setup(db)
    before=snapshot(db)
    rec={'case':name,'family':family,'expected_error':expect.__name__ if expect else None,'sql':sql,'parameters':parameters,'before':before,'before_sha256':digest(before)}
    try:
        result=action(db);rec.update(outcome='accepted',result=result);ok=expect is None and (expected_result is None or result==expected_result)
    except Exception as e:
        rec.update(outcome='refused',error=err(e));ok=expect is not None and isinstance(e,expect) and (message is None or message in str(e))
    after=snapshot(db);rec.update(after=after,after_sha256=digest(after),trace=trace,in_transaction=db.in_transaction)
    if unchanged is None:unchanged=expect is not None
    if unchanged:ok=ok and before==after
    rec['pass']=ok;cases.append(rec)
    if db.in_transaction:db.rollback()
    db.close()

def sql_case(name,sql,args=(),**kw):
    case(name,lambda d:d.execute(sql,args).fetchall(),sql=sql,parameters=args,**kw)

# Exact unchanged literal SQL from Task D; execute every statement and record all rowsets.
def minimal(old):
    db=sqlite3.connect(':memory:',isolation_level=None);configure(db);db.executescript(BEFORE if old else AFTER)
    text=(TASK_D/'F1-reproduction.sql').read_text();statements=[];pending=''
    for line in text.splitlines(True):
        pending+=line
        if sqlite3.complete_statement(pending):statements.append(pending);pending=''
    assert not pending.strip()
    observations=[]
    for sql in statements:
        pre=snapshot(db);item={'sql':sql,'before':pre}
        try:item.update(outcome='accepted',result=db.execute(sql).fetchall())
        except sqlite3.Error as e:item.update(outcome='refused',error=err(e))
        item['after']=snapshot(db);observations.append(item)
    report_step=next(x for x in observations if 'INSERT INTO resource_relations' in x['sql'])
    count=db.execute("SELECT count(*) FROM resource_relations WHERE relation_kind='transfer_event_report'").fetchone()[0]
    reports=ContextStore(db).transfer_event_reports()
    result={'case':'Task-D-minimal-before' if old else 'Task-D-minimal-after','family':'exact-minimal','statements':observations,'report_rows':count,'i7_rows':db.execute("SELECT count(*) FROM resources WHERE resource_kind='issue'").fetchone()[0],'endpoint_rows':db.execute('SELECT count(*) FROM resource_repository_relations').fetchone()[0],'unadapted_reference_reader_reports':len(reports),'foreign_key_check':db.execute('PRAGMA foreign_key_check').fetchall(),'integrity_check':db.execute('PRAGMA integrity_check').fetchall()}
    if old:result['pass']=report_step['outcome']=='accepted' and count==len(reports)==1
    else:result['pass']=report_step['outcome']=='refused' and report_step['error']['sqlite_errorcode']==1811 and report_step['before']==report_step['after'] and count==len(reports)==0
    assert result['i7_rows']==result['endpoint_rows']==0
    cases.append(result);db.close()
minimal(True);minimal(False)

verbs=[('insert','INSERT',''),('ignore','INSERT OR IGNORE',''),('nothing','INSERT',' ON CONFLICT DO NOTHING'),('replace','REPLACE',''),('or-replace','INSERT OR REPLACE',''),('upsert','INSERT',' ON CONFLICT DO UPDATE SET observed_at_us=excluded.observed_at_us'),('upsert-no-op','INSERT',' ON CONFLICT DO UPDATE SET observed_at_us=excluded.observed_at_us WHERE 0')]
for dependencies in [False,True]:
    for name,prefix,suffix in verbs:
        q=REL.replace('INSERT',prefix,1)+suffix
        sql_case('report-'+name+'-dependencies-'+str(dependencies),q,report,dependencies=dependencies,expect=sqlite3.IntegrityError,message='Transfer reports require')
for name,prefix,suffix in verbs:
    sql_case('report-existing-conflict-'+name,REL.replace('INSERT',prefix,1)+suffix,report,setup=lambda d:inject(d,'report'),expect=sqlite3.IntegrityError,message='Transfer reports require',family='unsupported-storage-fixture')
for role in ['transfer_from_repository','transfer_to_repository']:
    for name,prefix,suffix in verbs:
        # Endpoint table has the same observed_at_us non-key column.
        sql_case(role+'-'+name,EP.replace('INSERT',prefix,1)+suffix,(*event[:3],role,'null',CLOCK,PROV,17),expect=sqlite3.IntegrityError,message='Transfer requires')
for name,prefix,suffix in verbs:
    sql_case('endpoint-existing-conflict-'+name,EP.replace('INSERT',prefix,1)+suffix,(*event[:3],'transfer_from_repository','null',CLOCK,PROV,17),setup=lambda d:inject(d,'endpoint'),expect=sqlite3.IntegrityError,message='Transfer requires',family='unsupported-storage-fixture')
for n,row in enumerate([(*report[:4],None,*report[5:]),(*report[:6],None,17),(*report[:6],'{}',17),(*report[:4],'not-json',*report[5:]),(*report[:5],'{}',*report[6:])]):
    sql_case('reserved-report-malformed-'+str(n),REL,row,expect=sqlite3.IntegrityError,message='Transfer reports require')

# Direct generic UPDATE and UPSERT-update cannot manufacture reserved reports/endpoints.
for q in ["UPDATE resource_relations SET relation_kind='transfer_event_report'", "UPDATE resource_relations SET relation_kind=relation_kind",'DELETE FROM resource_relations']:
    sql_case('report-immutable-'+q,q,setup=lambda d:d.execute(REL,generic),expect=sqlite3.IntegrityError,message='immutable Context evidence')
sql_case('generic-incoming-upsert-to-reserved',REL+" ON CONFLICT DO UPDATE SET relation_kind='transfer_event_report'",generic,setup=lambda d:d.execute(REL,generic),expect=sqlite3.IntegrityError,message='immutable Context evidence')
owner=(S,'issue',J('ordinary-owner'),None,None,None,None)
owning=(*owner[:3],'owning_repository','null',CLOCK,PROV,17)
def setup_owning(d):d.execute(INSERT,owner);d.execute(EP,owning)
for q,args in [("UPDATE resource_repository_relations SET relation_kind='transfer_to_repository',resource_kind='comment',provider_resource_id=?",(E,)),(EP+" ON CONFLICT DO UPDATE SET relation_kind='transfer_to_repository'",owning)]:
    sql_case('endpoint-immutable-'+q,q,args,setup=setup_owning,expect=sqlite3.IntegrityError,message='immutable repository relation')

# Positives preserve common relation storage; these do not prove I3 semantics.
for row,label in [(parent7,'I7-parent'),(parent8,'I8-parent'),(generic,'opaque-relation'),((*parent7[:4],json.dumps([[S,'issue',J('I8')],[S,'issue',J('I7')]],separators=(',',':')),*parent7[5:]),'ordered-multimember')]:
    sql_case('general-positive-'+label,REL,row,setup=register_issues)
sql_case('general-I8-parent-without-native-I7',REL,parent8,setup=lambda d:d.execute(INSERT,(S,'issue',J('I8'),None,None,None,None)))
for name in ['Transfer_Event_Report','transfer_event_report ','vendor_transfer_report','transfer_event_report\x00opaque']:
    sql_case('opaque-name-'+repr(name),REL,(*generic[:3],name,*generic[4:]))
sql_case('general-report-payload-can-mention-transfer',REL,(*generic[:6],'{"description":"transfer_event_report"}',17))
for name,prefix,suffix in [('ignore','INSERT OR IGNORE',''),('nothing','INSERT',' ON CONFLICT DO NOTHING')]:
    sql_case('general-identical-replay-'+name,REL.replace('INSERT',prefix,1)+suffix,generic,setup=lambda d:d.execute(REL,generic))
sql_case('multirow-report-abort',REL+',('+','.join('?' for _ in report)+')',(*generic,*report),expect=sqlite3.IntegrityError,message='Transfer reports require')
sql_case('multirow-report-ignore-abort',REL.replace('INSERT','INSERT OR IGNORE',1)+',('+','.join('?' for _ in report)+')',(*generic,*report),expect=sqlite3.IntegrityError,message='Transfer reports require')
sql_case('complete-child-without-I7','SELECT (SELECT count(*) FROM resources WHERE resource_kind=\'issue\'),(SELECT count(*) FROM resource_relations)',unchanged=True,expected_result=[(0,0)])
for value in ['',[],['',[]],['pull_request',J('P'),'body','D']]:
    raw=J(value);sql_case('global-document-'+repr(value),INSERT,(S,'document',raw,None,None,None,raw))
sql_case('unknown-resource-unchanged',INSERT,(S,'vendor_widget',J(['',[]]),None,None,None,None))
sql_case('scoped-PR-document-before-namespace',INSERT,(S,'document',J(['pull_request',J('absent-PR'),'body',[]]),'pull_request',J('absent-PR'),'body',J([])))
def later_I7(d):
    d.execute(INSERT,(S,'issue',J('I7'),None,None,None,None))
    return d.execute('SELECT count(*) FROM resource_relations').fetchall()
case('later-I7-arrival-creates-no-report',later_I7,expected_result=[(0,)])

# Routing-model tests remain a separate family: Python refusals are not SQL proof.
for operation in [Operation('typed_transfer'),Operation('relation',report),Operation('endpoint',(*event[:3],'transfer_from_repository','null',CLOCK,PROV,17)),Operation('endpoint',(*event[:3],'transfer_to_repository','null',CLOCK,PROV,17))]:
    case('model-typed-write-'+operation.family+str(operation.row[3:4]),lambda d,op=operation:StagedContextPrototype(d).admit(op),expect=StageUnsupported,family='routing-model')
    for duplicate in [False,True]:
        for position,ordered in enumerate([(Operation('relation',generic),operation),(operation,Operation('relation',generic))]):
            case('model-import-preflight-'+operation.family+str(operation.row[3:4])+str(duplicate)+'-position-'+str(position),lambda d,ops=ordered,dup=duplicate:StagedContextPrototype(d).import_selected(ops,duplicate=dup),expect=StageUnsupported,family='routing-model')
    case('model-export-reserved-'+operation.family+str(operation.row[3:4]),lambda d,op=operation:StagedContextPrototype(d).export_selected([op]),expect=StageUnsupported,family='routing-model')
case('model-empty-transfer-query',lambda d:StagedContextPrototype(d).transfer_event_reports(),expect=StageUnsupported,family='routing-model')
case('model-generic-reserved-query',lambda d:StagedContextPrototype(d).relations('transfer_event_report'),expect=StageUnsupported,family='routing-model')
case('model-positive-generic-import',lambda d:StagedContextPrototype(d).import_selected([Operation('relation',generic)]),family='routing-model')
case('model-positive-duplicate-import',lambda d:StagedContextPrototype(d).import_selected([Operation('relation',generic)],duplicate=True),unchanged=True,family='routing-model')
case('model-positive-general-read',lambda d:StagedContextPrototype(d).relations('parent'),dependencies=True,unchanged=True,family='routing-model')
case('model-positive-general-export',lambda d:len(StagedContextPrototype(d).export_selected([Operation('relation',generic)])),unchanged=True,family='routing-model')
case('model-no-opaque-operation-family',lambda d:StagedContextPrototype(d).import_selected([Operation('unknown')]),expect=ValueError,message='Unknown normalized',family='routing-model')
for kind in ['report','endpoint']:
    for action,name in [(lambda d:validate_stage_storage(d),'open-check'),(lambda d:StagedContextPrototype(d).relations(),'ordinary-read'),(lambda d:StagedContextPrototype(d).export_selected([]),'ordinary-export'),(lambda d:StagedContextPrototype(d).import_selected([],duplicate=True),'duplicate-import')]:
        case('model-injected-'+kind+'-'+name,action,setup=lambda d,k=kind:inject(d,k),expect=StageStoredViolation,family='routing-model-unsupported-fixture')

def import_rollback(d):
    absent=(*generic[:2],J('absent'),*generic[3:])
    try:StagedContextPrototype(d).import_selected([Operation('relation',generic),Operation('relation',absent)])
    except sqlite3.IntegrityError as e:
        assert e.sqlite_errorcode==787;return err(e)
    raise AssertionError('missing referent accepted')
case('model-normal-import-fk-failure-rolls-back-prefix',import_rollback,unchanged=True,family='routing-model')

def transaction(d):
    d.execute('BEGIN IMMEDIATE');d.execute(REL,generic);d.execute('SAVEPOINT caller_unit')
    second=(*generic[:3],'second_generic',*generic[4:]);d.execute(REL,second)
    try:d.execute(REL,report)
    except sqlite3.IntegrityError as e:
        assert e.sqlite_errorcode==1811
        rec={'failure':err(e),'before_explicit_unit_rollback':snapshot(d),'in_transaction_after_statement_abort':d.in_transaction}
    else:raise AssertionError('reserved report accepted')
    d.execute('ROLLBACK TO caller_unit');d.execute('RELEASE caller_unit');d.commit()
    rec['after_unit_rollback_and_commit']=snapshot(d)
    assert d.execute('SELECT relation_kind FROM resource_relations').fetchall()==[('vendor_relation',)]
    return rec
case('caller-unit-rollback-keeps-outer-prefix',transaction,family='transaction')

def deferred(d):
    original=snapshot(d);d.execute('BEGIN');d.execute('PRAGMA defer_foreign_keys=ON')
    d.execute(REL,(*generic[:2],J('missing'),*generic[3:]))
    pending=snapshot(d)
    try:d.commit()
    except sqlite3.IntegrityError as e:
        assert e.sqlite_errorcode==787 and d.in_transaction;failure=err(e)
    else:raise AssertionError('deferred invalid commit succeeded')
    d.rollback();assert snapshot(d)==original
    return {'commit_error':failure,'pending_before_rollback':pending,'after_rollback':snapshot(d)}
case('explicit-deferred-commit-control',deferred,unchanged=True,family='transaction-unsupported-defer-control')

# Physical schema comparison proves no Resources or existing guard change.
before_db=fresh(old=True);after_db=fresh()
def schema(d):return {tuple(r[:2]):r[2:] for r in d.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")}
before_schema=schema(before_db);after_schema=schema(after_db)
delta=[{'key':key,'before':before_schema.get(key),'after':after_schema.get(key)} for key in sorted(before_schema.keys()|after_schema.keys()) if before_schema.get(key)!=after_schema.get(key)]
assert [x['key'] for x in delta]==[('trigger','i2_transfer_report_stage_fence')]
assert before_schema[('table','resources')]==after_schema[('table','resources')]
assert before_schema[('trigger','i2_transfer_stage_fence')]==after_schema[('trigger','i2_transfer_stage_fence')]
runtime={'version':after_db.execute('SELECT sqlite_version()').fetchone()[0],'source_id':after_db.execute('SELECT sqlite_source_id()').fetchone()[0],'python':sys.version,'executable':sys.executable,'compile_options':after_db.execute('PRAGMA compile_options').fetchall(),'pragmas':{n:after_db.execute('PRAGMA '+n).fetchall() for n in ['foreign_keys','recursive_triggers','ignore_check_constraints','defer_foreign_keys','trusted_schema','synchronous','encoding','journal_mode']}}
validation={'foreign_key_check':after_db.execute('PRAGMA foreign_key_check').fetchall(),'integrity_check':after_db.execute('PRAGMA integrity_check').fetchall()}
filedb=sqlite3.connect(OUT/'fresh-reopen.sqlite3',isolation_level=None);configure(filedb);filedb.executescript(AFTER);filedb.close()
filedb=sqlite3.connect(OUT/'fresh-reopen.sqlite3',isolation_level=None);configure(filedb);validate_stage_storage(filedb)
assert filedb.execute("SELECT count(*) FROM sqlite_schema WHERE name IN('i2_transfer_stage_fence','i2_transfer_report_stage_fence')").fetchone()==(2,)
filedb.close();before_db.close();after_db.close()
summary={'cases':len(cases),'passed':sum(c['pass'] for c in cases),'failed':sum(not c['pass'] for c in cases),'failed_cases':[c['case'] for c in cases if not c['pass']],'by_family':{f:{'cases':sum(c['family']==f for c in cases),'passed':sum(c['family']==f and c['pass'] for c in cases)} for f in sorted({c['family'] for c in cases})},'sql_case_refusals':sum(c['family']=='sql' and c.get('outcome')=='refused' for c in cases)}
assert len({c['case'] for c in cases})==len(cases), 'Duplicate case identifiers'
inputs=[pathlib.Path(__file__),pathlib.Path(__file__).with_name('compose_f1.py'),pathlib.Path(__file__).with_name('fence.sql'),pathlib.Path(__file__).with_name('stage_contract.py'),pathlib.Path(__file__).with_name('I2-F1-ADDENDUM.md'),OLD/'resources.sql',OLD/'resource_udfs.py',OLD/'compose_proposal.py',TASK_D/'F1-reproduction.sql',REPO/'src/repo_catalog/domain/resource_identity.py',REPO/'src/repo_catalog/adapters/sqlite/p1_ddl/context.sql',REPO/'src/repo_catalog/adapters/sqlite/p1_schema.py']
receipt={'role':'C-F1 author validation; independent re-review pending','runtime':runtime,'before_ddl_sha256':hashlib.sha256(BEFORE.encode()).hexdigest(),'after_ddl_sha256':hashlib.sha256(AFTER.encode()).hexdigest(),'input_hashes':{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},'schema_delta':delta,'summary':summary,'cases':cases,'validation':validation,'fresh_reopen_both_fences':True}
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=True)+'\n')
(OUT/'summary.json').write_text(json.dumps({k:v for k,v in receipt.items() if k!='cases'},indent=2)+'\n')
print(json.dumps(summary));sys.exit(1 if summary['failed'] else 0)
