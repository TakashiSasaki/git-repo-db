"""Task D independent counterexamples. Frozen product/candidate are read-only.

Uses Task C SQL/UDF as input, not Task C tests or results as an oracle.
Each ordinary case is isolated by a savepoint; separate connection controls follow.
Exit 1 means an independently specified requirement was violated.
"""
import hashlib
import itertools
import json
import pathlib
import sqlite3
import sys

from compose_proposal import compose, configure
from resource_udfs import register
from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.domain import resource_identity as codec
from repo_catalog.domain.p1_context import ResourceKey, FieldClock, EventReportKey, TransferEventReport

OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=False)
VERSION = sys.argv[2]
S = '11111111-1111-4111-8111-111111111111'
T = '22222222-2222-4222-8222-222222222222'
ABSENT = '33333333-3333-4333-8333-333333333333'
R = '44444444-4444-4444-8444-444444444444'
C = '55555555-5555-4555-8555-555555555555'
J = codec.encode_identity
COLS = 'service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id'
INSERT = f'INSERT INTO resources({COLS}) VALUES(?,?,?,?,?,?,?)'
REL = 'INSERT INTO resource_relations VALUES(?,?,?,?,?,?,?,?)'
ENDPOINT = 'INSERT INTO resource_repository_relations(service_instance_uuidv4,resource_kind,provider_resource_id,relation_kind,target_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)'
PROV = '{"evidence":"native-observation","source":"task-d"}'
CLOCK = '{"at_us":17,"domain":"provider"}'
DDL = compose()
(OUT/'candidate.sql').write_text(DDL)
(OUT/'baseline.sql').write_text(p1_schema.compose('context'))
db = sqlite3.connect(OUT/'independent.sqlite3', isolation_level=None)
configure(db)
assert db.execute('SELECT sqlite_version()').fetchone()[0] == VERSION
db.executescript(DDL)
db.execute('INSERT INTO store_identity VALUES(?,?,?)', ('context', R, C))
for service in [S,T]: db.execute("INSERT INTO providers VALUES(?,'synthetic','{}')",(service,))
db.execute("INSERT INTO repository_context VALUES(?,'{}')",(R,))

def native(value='id', kind='opaque', service=S):
    return (service,kind,J(value),None,None,None,None)

def global_doc(value):
    raw=J(value);return (S,'document',raw,None,None,None,raw)

def scoped(kind='comment', ns='issue', nsvalue='I7', subtype='timeline_event', local='event', service=S):
    n=J(nsvalue)
    return (service,kind,J([ns,n,subtype,local]),ns,n,subtype,J(local))

def dump(v):
    return json.dumps(v,ensure_ascii=True,sort_keys=True,separators=(',',':'),default=lambda b:{'hex':b.hex()})

def digest(v):return hashlib.sha256(dump(v).encode()).hexdigest()

def snapshot():
    result={}
    for (name,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        rows=db.execute('SELECT * FROM "'+name+'"').fetchall()
        result[name]={'count':len(rows),'rowset_sha256':digest(sorted(rows,key=dump))}
    return result

def error_info(er):
    return {'type':type(er).__name__,'message':str(er),'code':getattr(er,'sqlite_errorcode',None),'name':getattr(er,'sqlite_errorname',None)}

cases=[]
def case(name, sql, args=(), *, setup=(), refuse=False, result=None, must_error=None, finding=None):
    trace=[];db.set_trace_callback(trace.append);db.execute('SAVEPOINT independent_case')
    for q,p in setup:db.execute(q,p)
    before=snapshot(); row={'id':name,'sql':sql,'parameters':args,'expected':'refused' if refuse else 'accepted','before':before}
    try:
        cur=db.execute(sql,args); actual=cur.fetchall()
        row.update(outcome='accepted',result=actual,rowcount=cur.rowcount)
        good=not refuse and (result is None or result==actual)
    except sqlite3.Error as er:
        row.update(outcome='refused',error=error_info(er))
        good=refuse and (must_error is None or must_error in str(er))
    after=snapshot();row['after']=after
    row['pass']=good and (not refuse or before==after)
    if finding:row['finding']=finding
    db.execute('ROLLBACK TO independent_case');db.execute('RELEASE independent_case');db.set_trace_callback(None)
    row['trace']=trace;cases.append(row)

tables=[x[0] for x in db.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name")]
inventory={'tables':tables,'table_xinfo':{},'indexes':{},'fks':{},'functions':db.execute('PRAGMA function_list').fetchall()}
for table in tables:
    inventory['table_xinfo'][table]=db.execute(f'PRAGMA table_xinfo({table})').fetchall()
    inventory['fks'][table]=db.execute(f'PRAGMA foreign_key_list({table})').fetchall()
    inventory['indexes'][table]={idx[1]:db.execute(f'PRAGMA index_xinfo("{idx[1]}")').fetchall() for idx in db.execute(f'PRAGMA index_list({table})')}
for width,tail in [(3,[]),(4,['reference_document_kind']),(5,['reference_document_kind','identifier_namespace_kind']),(6,['reference_document_kind','identifier_namespace_kind','identifier_namespace_id'])]:
    cols=['s','k','i']+['d','n','v'][:width-3]
    target=['service_instance_uuidv4','resource_kind','provider_resource_id']+tail
    db.execute(f'CREATE TABLE d_ref{width}('+','.join(c+' TEXT COLLATE BINARY NOT NULL' for c in cols)+',FOREIGN KEY('+','.join(cols)+') REFERENCES resources('+','.join(target)+')) STRICT')

# Independent codec/SQL agreement including string scalars that resemble JSON.
valid=['',[],[''],[[]],'a','A',' a ','é','e\u0301','日本','😀','\x00\x7f\n\t','"\\/','["native"]',['x',['',[]]]]
for n,v in enumerate(valid):
    raw=J(v); assert codec.parse_identity(raw)==v
    case(f'identity-positive-{n}',INSERT,native(v))
    case(f'global-positive-{n}',INSERT,global_doc(v))
    case(f'scoped-native-positive-{n}',INSERT,scoped(local=v))
bad=['', '123','-1','true','false','null','{}','[{}]','[1]','[[false]]','[null]','"é"','"😀"','"\\ud800"','"\\udc00"','"\\udc00\\ud800"','"\\u0041"','"\\u00E9"','"\\/"',' "a"','"a"\n','\ufeff"a"','["x",]','[NaN]','"a"x']
for n,raw in enumerate(bad):
    try:codec.parse_identity(raw);raise AssertionError(raw)
    except (TypeError,ValueError):pass
    case(f'identity-refusal-{n}',INSERT,(S,'opaque',raw,None,None,None,None),refuse=True)
    case(f'global-local-refusal-{n}',INSERT,(S,'document',J('ok'),None,None,None,raw),refuse=True)

# All metadata omissions, not just one NULL at a time.
p=scoped('document','pull_request','P','body','D');g=global_doc(codec.parse_identity(p[2]))
assert p[:3]==g[:3]
for mask in itertools.product([False,True],repeat=4):
    row=(*p[:3],*[x if keep else None for x,keep in zip(p[3:],mask)])
    case('scoped-null-mask-'+''.join(map(lambda x:str(int(x)),mask)),INSERT,row,refuse=not all(mask))
for first,second,label in [(g,p,'global-to-scoped'),(p,g,'scoped-to-global')]:
    for prefix,suffix,verb in [('INSERT','','insert'),('INSERT OR IGNORE','','ignore'),('INSERT',' ON CONFLICT DO NOTHING','nothing'),('REPLACE','','replace'),('INSERT',' ON CONFLICT DO UPDATE SET document_kind=excluded.document_kind','upsert')]:
        case('declaration-rebind-'+label+'-'+verb,INSERT.replace('INSERT',prefix,1)+suffix,second,setup=[(INSERT,first)],refuse=True,must_error='rebind')
    case('exact-replay-'+label,INSERT+' ON CONFLICT DO NOTHING',first,setup=[(INSERT,first)])
case('opaque-scoped-shape',INSERT,native(codec.parse_identity(p[2]),'provider_widget'))
case('opaque-cannot-carry-known-metadata',INSERT,(*p[:1],'provider_widget',*p[2:]),refuse=True)
for kind,allowed in [('review',{'pull_request'}),('thread',{'pull_request','review'}),('comment',{'pull_request','issue','review','thread'}),('document',{'pull_request'})]:
    for ns in ['pull_request','issue','review','thread','repository','opaque']:
        case('reserved-'+kind+'-'+ns,INSERT,scoped(kind,ns),refuse=ns not in allowed)
    case('reserved-no-opaque-fallback-'+kind,INSERT,native('x',kind),refuse=True)
case('provider-scoped-equal-name-id','SELECT count(*) FROM resources',setup=[(INSERT,native('same','widget',S)),(INSERT,native('same','widget',T))],result=[(2,)])
case('binary-kind-case','SELECT count(*) FROM resources',setup=[(INSERT,native('id','Widget')),(INSERT,native('id','widget'))],result=[(2,)])
case('nonempty-nul-kind',INSERT,native('id','\x00vendor'))
case('empty-kind',INSERT,native('id',''),refuse=True)
case('native-local-consistent-json-looking-string',INSERT,scoped(local=J('D')))
case('native-local-one-sided-double-encoding',INSERT,(*p[:6],J(J('D'))),refuse=True)
case('decoded-namespace-profile',INSERT,(S,'document',J(['pull_request',['P'],'body','D']),'pull_request',J(['P']),'body',J('D')),refuse=True)
case('projection-explicit-insert',f'INSERT INTO resources({COLS},reference_document_kind) VALUES(?,?,?,?,?,?,?,?)',(*p,'forged'),refuse=True)
for n in range(3):
    row=list(native());row[n]=None
    case('pk-null-'+str(n),INSERT,row,refuse=True)
case('missing-provider',INSERT,native(service=ABSENT),refuse=True,must_error='FOREIGN KEY')
for raw in [None,b'"id"',17,True]:case('identity-type-'+str(type(raw)),INSERT,(S,'opaque',raw,None,None,None,None),refuse=True)
case('invalid-utf8',f"INSERT INTO resources({COLS}) VALUES(?,'opaque',CAST(X'80' AS TEXT),NULL,NULL,NULL,NULL)",(S,),refuse=True)

# Independently construct inclusive maxima and +1 for every structural limit.
limits={'bytes':('"'+'x'*262142+'"','"'+'x'*262143+'"'),
        'nodes':('['+','.join(['""']*4095)+']','['+','.join(['""']*4096)+']'),
        'depth-nonempty':('['*32+'"x"'+']'*32,'['*33+'"x"'+']'*33),
        'depth-empty':('['*32+']'*32,'['*33+']'*33)}
for label,(yes,no) in limits.items():
    codec.parse_identity(yes)
    try:codec.parse_identity(no);raise AssertionError('over-limit accepted by I1')
    except ValueError:pass
    case('limit-exact-'+label,INSERT,(S,'opaque',yes,None,None,None,None))
    case('limit-over-'+label,INSERT,(S,'opaque',no,None,None,None,None),refuse=True)
    case('sql-codec-over-'+label,'SELECT p1_resource_identity_v1(?)',(no,),result=[(0,)])
local_at_limit=codec.parse_identity(limits['bytes'][0])
raw='["issue",'+json.dumps(J('I7'))+',"timeline_event",'+limits['bytes'][0]+']'
case('local-fits-but-container-exceeds',INSERT,(S,'comment',raw,'issue',J('I7'),'timeline_event',J(local_at_limit)),refuse=True)

# Actual FK targets, including four-column typed absence and six-column native index.
for width,tail in [(3,[]),(4,['body']),(5,['body','pull_request']),(6,['body','pull_request',J('P')])]:
    vals=(*p[:3],*tail);sql=f'INSERT INTO d_ref{width} VALUES('+','.join('?' for _ in vals)+')'
    case(f'fk{width}-matching-index',sql,vals,setup=[(INSERT,p)])
    for n in range(width):
        v=list(vals);v[n]=None
        case(f'fk{width}-null-{n}',sql,v,setup=[(INSERT,p)],refuse=True)
    for n in range(width):
        v=list(vals);v[n]=T if n==0 else v[n]+'X'
        case(f'fk{width}-wrong-{n}',sql,v,setup=[(INSERT,p)],refuse=True,must_error='FOREIGN KEY')
case('global-reference-absence','INSERT INTO d_ref4 VALUES(?,?,?,?)',(*g[:3],''),setup=[(INSERT,g)])
case('global-reference-null-absence','INSERT INTO d_ref4 VALUES(?,?,?,?)',(*g[:3],None),setup=[(INSERT,g)],refuse=True)
case('global-reference-scoped-subtype','INSERT INTO d_ref4 VALUES(?,?,?,?)',(*g[:3],'body'),setup=[(INSERT,g)],refuse=True)
case('binary-nfc-nfd-case','SELECT count(*) FROM resources',setup=[(INSERT,native(v)) for v in valid],result=[(len(valid),)])
for n,v in enumerate(['é','e\u0301','A',' a ']):
    case('binary-fk-'+str(n),'INSERT INTO d_ref3 VALUES(?,?,?)',native(v)[:3],setup=[(INSERT,native(v))])

# Statement-level immutability and error-before-conflict; whole-unit rollback below.
for verb in ['UPDATE resources SET document_kind=document_kind','DELETE FROM resources']:
    case('immutable-'+verb,verb,setup=[(INSERT,p)],refuse=True)
for q in [INSERT.replace('INSERT','REPLACE',1),INSERT.replace('INSERT','INSERT OR REPLACE',1),INSERT+' ON CONFLICT DO UPDATE SET resource_kind=excluded.resource_kind']:
    case('same-declaration-immutable-'+q.split('VALUES')[0],q,p,setup=[(INSERT,p)],refuse=True)
case('multirow-abort',INSERT+',('+','.join('?' for _ in range(7))+')',(*native('prefix'),S,'document',J('bad'),None,None,None,None),refuse=True)
for badrow,label in [((*g[:6],None),'global-missing-local'),((*p[:6],'null'),'scoped-invalid-local')]:
    initial=g if label.startswith('global') else p
    for prefix,suffix,verb in [('INSERT','','insert'),('INSERT OR IGNORE','','ignore'),('INSERT',' ON CONFLICT DO NOTHING','nothing'),('REPLACE','','replace'),('INSERT',' ON CONFLICT DO UPDATE SET provider_document_id=excluded.provider_document_id','upsert')]:
        case('invalid-replay-before-conflict-'+label+'-'+verb,INSERT.replace('INSERT',prefix,1)+suffix,badrow,setup=[(INSERT,initial)],refuse=True,must_error='invalid Resource identification')

# Test the real incoming tables as well as the auxiliary exact-index probes.
real_rows=[
 ('field_candidates','INSERT INTO field_candidates(service_instance_uuidv4,resource_kind,provider_resource_id,field_name,value_json,clock_json,provenance_json,observed_at_us) VALUES(?,?,?,?,?,?,?,?)',(*native()[:3],'title','"text"',CLOCK,PROV,17)),
 ('resource_relations',REL,(*native()[:3],'vendor_relation','[]',PROV,'{}',17)),
 ('collections','INSERT INTO collections VALUES(?,?,?,?,?,?)',(*native()[:3],'vendor_collection',PROV,'{}')),
 ('core_references','INSERT INTO core_references VALUES(?,?,?,?,?,?,?)',(*native()[:3],'vendor_ref','sha1','a'*40,PROV)),
]
for table,query,args in real_rows:
    case('actual-incoming-fk-positive-'+table,query,args,setup=[(INSERT,native())])
    for n in range(3):
        badargs=list(args);badargs[n]=None
        case('actual-incoming-fk-null-'+table+'-'+str(n),query,badargs,setup=[(INSERT,native())],refuse=True)
    badargs=list(args);badargs[2]=J('absent')
    case('actual-incoming-fk-absent-'+table,query,badargs,setup=[(INSERT,native())],refuse=True,must_error='FOREIGN KEY')
coverage_q='INSERT INTO coverage_scopes(owner_kind,owner_coordinates_json,service_instance_uuidv4,resource_kind,provider_resource_id,coverage_kind) VALUES(?,?,?,?,?,?)'
coverage_args=('resource',J([S,'opaque',J('id'),'vendor_coverage']),S,'opaque',J('id'),'vendor_coverage')
case('actual-resource-coverage-positive',coverage_q,coverage_args,setup=[(INSERT,native())])
for n in [2,3,4]:
    a=list(coverage_args);a[n]=None
    case('actual-resource-coverage-null-'+str(n),coverage_q,a,setup=[(INSERT,native())],refuse=True)
source_setup=[('INSERT INTO sources VALUES(?,?,?)',(ABSENT,S,'{}')),('INSERT INTO source_repositories VALUES(?,?,?)',(ABSENT,R,'{}'))]
case('source-positive-durable','DELETE FROM source_repositories',setup=source_setup,refuse=True,must_error='known-positive')
case('source-positive-unchanged','SELECT count(*) FROM source_repositories',setup=source_setup,result=[(1,)])
case('text-body-exact','INSERT INTO text_bodies VALUES(?,?)',(hashlib.sha256('日本\n'.encode()).hexdigest(),'日本\n'))
case('text-body-wrong-hash','INSERT INTO text_bodies VALUES(?,?)',('0'*64,'日本\n'),refuse=True)
case('child-without-parent','SELECT (SELECT count(*) FROM resources),(SELECT count(*) FROM resource_relations)',setup=[(INSERT,p)],result=[(1,0)])
case('parent-arrival-no-report','SELECT (SELECT count(*) FROM resources),(SELECT count(*) FROM resource_relations)',setup=[(INSERT,p),(INSERT,native('P','pull_request'))],result=[(2,0)])

# Six existing role constraints, all conflict verbs on both Transfer endpoint roles.
e=scoped(); ep_setup=[(INSERT,e)]
for kind,role in [('repository','represents_repository'),('issue','owning_repository'),('pull_request','base_repository'),('pull_request','head_repository')]:
    key=native('owner',kind)
    case('preserved-role-'+role,ENDPOINT,(*key[:3],role,J(R),CLOCK,PROV,17),setup=[(INSERT,key)])
    case('known-role-no-unknown-fallback-'+role,ENDPOINT,(*native()[:3],role,J(R),CLOCK,PROV,17),setup=[(INSERT,native())],refuse=True)
for role in ['transfer_from_repository','transfer_to_repository']:
    for prefix,suffix,name in [('INSERT','','insert'),('INSERT OR IGNORE','','ignore'),('INSERT',' ON CONFLICT DO NOTHING','nothing'),('REPLACE','','replace'),('INSERT',' ON CONFLICT DO UPDATE SET target_json=excluded.target_json','upsert')]:
        case('endpoint-fence-'+role+'-'+name,ENDPOINT.replace('INSERT',prefix,1)+suffix,(*e[:3],role,J(R),CLOCK,PROV,17),setup=ep_setup,refuse=True,must_error='Transfer requires')

# NEW COUNTEREXAMPLE: unresolved-provider-only reports never touch the fenced table.
issue=ResourceKey.from_native(S,'issue','I7')
event=ResourceKey.timeline_event(issue,'event')
provider=ResourceKey.from_native(S,'repository','unresolved-R')
report=TransferEventReport(EventReportKey(event,FieldClock('provider',17),PROV),observed_at_us=17,from_provider_repository=provider)
report_args=(*event.coordinates(),'transfer_event_report',report.members_json,report.provenance_json,report.scope_json,17)
report_setup=[(INSERT,e),(INSERT,native('unresolved-R','repository'))]
for prefix,suffix,name in [('INSERT','','insert'),('INSERT OR IGNORE','','ignore'),('INSERT',' ON CONFLICT DO NOTHING','nothing'),('REPLACE','','replace'),('INSERT',' ON CONFLICT DO UPDATE SET observed_at_us=excluded.observed_at_us','upsert')]:
    case('F1-report-fence-'+name,REL.replace('INSERT',prefix,1)+suffix,report_args,setup=report_setup,refuse=True,finding='F1')
case('F1-malformed-reserved-report',REL,(*event.coordinates(),'transfer_event_report','[]',PROV,'{}',17),setup=report_setup,refuse=True,finding='F1')

db.execute('SAVEPOINT reader_counterexample')
for q,args in report_setup:db.execute(q,args)
db.execute(REL,report_args)
read_reports=ContextStore(db).transfer_event_reports()
counterexample={'report_parameters':report_args,'issue_rows':db.execute("SELECT count(*) FROM resources WHERE resource_kind='issue'").fetchone()[0],
 'parent_report_rows':db.execute("SELECT count(*) FROM resource_relations WHERE relation_kind='parent'").fetchone()[0],
 'endpoint_rows':db.execute('SELECT count(*) FROM resource_repository_relations').fetchone()[0],
 'returned_reports':[{'event':r.event_resource.coordinates(),'from_state':r.from_state,'scope':r.scope_json} for r in read_reports],
 'foreign_key_check':db.execute('PRAGMA foreign_key_check').fetchall(),'integrity_check':db.execute('PRAGMA integrity_check').fetchall()}
db.execute('ROLLBACK TO reader_counterexample');db.execute('RELEASE reader_counterexample')

# Minimal corrective design control, in a disposable DB only. No product/candidate edit.
fix="CREATE TRIGGER d_transfer_report_fence BEFORE INSERT ON resource_relations WHEN NEW.relation_kind='transfer_event_report' BEGIN SELECT RAISE(ABORT,'Transfer report requires I3-I5 implementation'); END;"
db.execute(fix)
for prefix,suffix,name in [('INSERT','','insert'),('INSERT OR IGNORE','','ignore'),('INSERT',' ON CONFLICT DO NOTHING','nothing'),('REPLACE','','replace'),('INSERT',' ON CONFLICT DO UPDATE SET observed_at_us=excluded.observed_at_us','upsert')]:
    case('corrective-control-report-'+name,REL.replace('INSERT',prefix,1)+suffix,report_args,setup=report_setup,refuse=True,must_error='Transfer report requires')
case('corrective-control-generic-report',REL,(*e[:3],'vendor_relation','[]',PROV,'{}',17),setup=ep_setup)
case('corrective-control-I8-general-report',REL,(*e[:3],'parent',json.dumps([[S,'issue',J('I8')]],separators=(',',':')),PROV,'{}',17),setup=ep_setup+[(INSERT,native('I8','issue'))])
db.execute('DROP TRIGGER d_transfer_report_fence')

# Explicit failure transaction: statement ABORT preserves prefix; caller rollback removes unit.
db.execute('BEGIN IMMEDIATE');db.execute(INSERT,native('outer'))
db.execute('SAVEPOINT whole_unit');db.execute(INSERT,native('unit-prefix'))
try:db.execute(INSERT,(S,'document',J('invalid'),None,None,None,None));raise AssertionError('accepted')
except sqlite3.IntegrityError as er: unit={'error':error_info(er),'prefix_count':db.execute('SELECT count(*) FROM resources').fetchone()[0],'active_after_error':db.in_transaction}
db.execute('ROLLBACK TO whole_unit');db.execute('RELEASE whole_unit');db.commit()
unit['after_unit_rollback']=db.execute('SELECT provider_resource_id FROM resources').fetchall()
db.close();db=sqlite3.connect(OUT/'independent.sqlite3',isolation_level=None);configure(db)
unit['reopened']=db.execute('SELECT provider_resource_id FROM resources').fetchall()
assert unit['prefix_count']==2 and unit['after_unit_rollback']==unit['reopened']==[(J('outer'),)]
db.execute('BEGIN');db.execute('PRAGMA defer_foreign_keys=ON');db.execute(INSERT,native('deferred',service=ABSENT))
try:db.commit();raise AssertionError('bad deferred commit passed')
except sqlite3.IntegrityError as er: deferred={'error':error_info(er),'active_after_failed_commit':db.in_transaction,'rows_before_rollback':snapshot()}
db.rollback();deferred['rows_after_rollback']=snapshot();assert deferred['active_after_failed_commit'] and deferred['rows_after_rollback']['resources']['count']==1

# Independently execute integration and misconfiguration controls; these diagnose risks,
# not failed normative cases under the supported candidate configuration.
controls=[]
def control(name,fn):
    try: controls.append({'id':name,'outcome':'accepted','result':fn()})
    except Exception as er:controls.append({'id':name,'outcome':'refused','error':error_info(er)})

def open_old_registration():
    d=sqlite3.connect(':memory:',isolation_level=None);p1_schema.register_functions(d);d.executescript(DDL)
    return d
control('old-registration-candidate-ddl',open_old_registration)
def absent_new_udf():
    d=sqlite3.connect(OUT/'independent.sqlite3',isolation_level=None);p1_schema.register_functions(d)
    return d.execute('PRAGMA integrity_check').fetchall()
control('reopen-old-registration-integrity',absent_new_udf)
for pragma,value in [('trusted_schema','OFF'),('foreign_keys','OFF'),('recursive_triggers','OFF'),('ignore_check_constraints','ON')]:
    def run_misconfig(pragma=pragma,value=value):
        d=sqlite3.connect(':memory:',isolation_level=None);configure(d);d.executescript(DDL)
        d.execute(f'PRAGMA {pragma}={value}')
        d.execute("INSERT INTO providers VALUES(?,'synthetic','{}')",(S,))
        if pragma=='foreign_keys':
            d.execute(INSERT,native(service=ABSENT));return {'orphan_resources':d.execute('SELECT count(*) FROM resources').fetchone()[0]}
        if pragma=='recursive_triggers':
            d.execute(INSERT,native());d.execute(INSERT.replace('INSERT','REPLACE',1),native());return {'replace_accepted':True}
        if pragma=='ignore_check_constraints':
            try:d.execute(INSERT,(S,'document',J('bad'),None,None,None,None))
            except sqlite3.Error as er:return {'resource_guard':error_info(er),'note':'other-table CHECKs disabled'}
        d.execute(INSERT,native());return 'write accepted'
    control('unsupported-'+pragma,run_misconfig)
def mismatched_fk_fragment_only():
    old=p1_schema.compose('context');start=old.index('CREATE TABLE resources(');end=old.index('CREATE TABLE text_bodies(',start)
    frag=pathlib.Path(__import__('compose_proposal').__file__).with_name('resources.sql').read_text()
    d=sqlite3.connect(':memory:',isolation_level=None);configure(d);d.executescript(old[:start]+frag+old[end:])
    d.execute("INSERT INTO providers VALUES(?,'synthetic','{}')",(S,));d.execute(INSERT,native('owner','issue'))
    return d.execute(ENDPOINT,(*native('owner','issue')[:3],'owning_repository','null',CLOCK,PROV,17)).fetchall()
control('copy-fragment-without-endpoint-fk-rewrite',mismatched_fk_fragment_only)
control('old-parent-column-read',lambda:db.execute('SELECT parent_resource_kind,parent_provider_resource_id FROM resources').fetchall())
control('product-connect-on-candidate',lambda:p1_schema.connect(OUT/'independent.sqlite3','context'))
def metadata_loss():
    d=sqlite3.connect(':memory:',isolation_level=None);configure(d);d.executescript(DDL);d.execute("INSERT INTO providers VALUES(?,'synthetic','{}')",(S,));d.execute(INSERT,g)
    reconstructed=ResourceKey(*d.execute('SELECT service_instance_uuidv4,resource_kind,provider_resource_id FROM resources').fetchone())
    original=ResourceKey.global_document(S,codec.parse_identity(g[2]))
    try:original.scoped_document_coordinates()
    except ValueError as er:original_refusal=str(er)
    return {'original_global_guard':original_refusal,'reconstructed_contract':reconstructed._document_contract,'reconstructed_scoped_coordinates':reconstructed.scoped_document_coordinates(),'stored_global_metadata':d.execute('SELECT identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id FROM resources').fetchone()}
control('bare-triple-reader-loses-global-declaration',metadata_loss)
def copy_then_check():
    target=sqlite3.connect(OUT/'backup.sqlite3',isolation_level=None)
    db.backup(target)
    copied=target.execute('SELECT count(*) FROM resources').fetchone()[0]
    try:target.execute('PRAGMA integrity_check').fetchall()
    except sqlite3.Error as er:missing=error_info(er)
    configure(target);checked=target.execute('PRAGMA integrity_check').fetchall();target.close()
    return {'copied_without_udf':copied,'unregistered_integrity_error':missing,'registered_integrity':checked}
control('backup-copy-vs-schema-validation',copy_then_check)
control('old-registered-search-store-expected-schema',lambda:len(p1_schema.expected_schema('search')))

runtime={'sqlite_version':db.execute('SELECT sqlite_version()').fetchone()[0],'sqlite_source_id':db.execute('SELECT sqlite_source_id()').fetchone()[0],
 'python':sys.version,'executable':sys.executable,'compile_options':db.execute('PRAGMA compile_options').fetchall(),
 'pragmas':{p:db.execute('PRAGMA '+p).fetchall() for p in ['foreign_keys','recursive_triggers','ignore_check_constraints','defer_foreign_keys','trusted_schema','encoding','synchronous','journal_mode']}}
validation={'foreign_key_check':db.execute('PRAGMA foreign_key_check').fetchall(),'integrity_check':db.execute('PRAGMA integrity_check').fetchall()}
summary={'cases':len(cases),'passes':sum(x['pass'] for x in cases),'failures':sum(not x['pass'] for x in cases),'accepted':sum(x['outcome']=='accepted' for x in cases),'refused':sum(x['outcome']=='refused' for x in cases),'failed_ids':[x['id'] for x in cases if not x['pass']]}
receipt={'runtime':runtime,'ddl_sha256':hashlib.sha256(DDL.encode()).hexdigest(),'summary':summary,'cases':cases,'inventory':inventory,'F1_reader_counterexample':counterexample,'corrective_control_sql':fix,'transaction':unit,'deferred_commit':deferred,'controls':controls,'validation':validation}
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=True,default=lambda v:{'blob_hex':v.hex()} if isinstance(v,bytes) else str(v))+'\n')
(OUT/'summary.json').write_text(json.dumps({'runtime':runtime,'summary':summary,'F1_reader_counterexample':counterexample,'controls':controls,'validation':validation},indent=2,default=str)+'\n')
print(json.dumps(summary));sys.exit(1 if summary['failures'] else 0)
