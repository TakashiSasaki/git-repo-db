"""Read-only independent probes, intentionally external to implementation trees."""
import sys,pathlib,json,sqlite3,tempfile,hashlib,random,copy,pickle,base64,dataclasses,traceback
ROOT=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(ROOT/'src'))
from repo_catalog.domain.resource_identity import encode_identity as J,parse_identity as P,MAX_IDENTITY_BYTES,MAX_IDENTITY_NODES,MAX_IDENTITY_ARRAY_DEPTH
from repo_catalog.domain.p1_context import ResourceKey as K,FieldClock,MappingClaimKey,MappingSupport,CoverageScope,EventReportKey,canonical,encode_mapping_provenance
from repo_catalog.domain.production_context import CollectionObservation
from repo_catalog.domain.production_query import PaginationCursor,SnapshotFenceToken,canonical_json
from repo_catalog.domain.exchange import ExchangeSelectionScope,ExchangePackage,empty_context_section,decode_package,_canonical_content
from repo_catalog.domain.selective_exchange import validate_context
from repo_catalog.adapters.github.production_intake import github_resource_id,github_repository_id,github_timeline_input_id,normalize_pull_request,normalize_timeline_event
from repo_catalog.domain.acquisition import make_provenance
from repo_catalog.adapters.sqlite.p1_schema import compose,register_functions
from repo_catalog.adapters.sqlite.p1_context import ContextStore
S='11111111-1111-4111-8111-111111111111'; T='22222222-2222-4222-8222-222222222222'; R='33333333-3333-4333-8333-333333333333'
clock=FieldClock('independent:original',7); prov=make_provenance('independent://fixture',{'observed':'original'})
results=[]
def group(name,fn):
    try: detail=fn(); results.append({'name':name,'passed':True,'detail':detail})
    except Exception as e: results.append({'name':name,'passed':False,'error':repr(e),'trace':traceback.format_exc()})
def refuses(fn):
    try: fn()
    except (ValueError,TypeError,sqlite3.IntegrityError) as e: return str(e)
    raise AssertionError('Unexpected acceptance')
def same(a,b): assert a==b,(a,b)
def native_tests():
    values=['',[],[''],[[]],'731',['731'],['node','731'],'["node","731"]','é','e\u0301','😀','\0\x7f\n/"\\']
    texts=[J(v) for v in values]; assert len(set(texts))==len(texts)
    for v,t in zip(values,texts): same(P(t),v); same(K.from_native(S,'vendor',v),K(S,'vendor',t))
    return texts
group('native versus serialized injectivity and Unicode',native_tests)
for bad in ['731','null','{}','true','[false]','["x",1]',' "x"','"x"\n','"\\u0078"','"\\/"','"\\u00E9"','"é"','"\\ud800"','"\\udc00\\ud800"','[]x','["x",]','\ufeff"x"']:
    group('serialized rejection '+repr(bad),lambda bad=bad:refuses(lambda:K(S,'vendor',bad)))
for bad in [None,True,7,{},('x',),b'"x"',['x',[None]],'\ud800']:
    group('native rejection '+repr(bad),lambda bad=bad:refuses(lambda:J(bad)))
def limits():
    same(len(J('a'*(MAX_IDENTITY_BYTES-2))),MAX_IDENTITY_BYTES)
    refuses(lambda:J('a'*(MAX_IDENTITY_BYTES-1)))
    same(len(P(J(['']*(MAX_IDENTITY_NODES-1)))),MAX_IDENTITY_NODES-1)
    refuses(lambda:J(['']*MAX_IDENTITY_NODES))
    deep='x'
    for _ in range(MAX_IDENTITY_ARRAY_DEPTH): deep=[deep]
    same(P(J(deep)),deep); refuses(lambda:J([deep]))
    refuses(lambda:P('['*33+'"x"'+']'*33))
    cyc=[]; cyc.append(cyc); refuses(lambda:J(cyc))
    return {'bytes':MAX_IDENTITY_BYTES,'nodes':MAX_IDENTITY_NODES,'depth':MAX_IDENTITY_ARRAY_DEPTH}
group('exact finite limits and cyclic native refusal',limits)
def random_reference():
    rng=random.Random(20261021)
    def value(d=0):
        if d<6 and rng.random()<.35:return [value(d+1) for _ in range(rng.randrange(5))]
        return ''.join(rng.choice(['a','é','😀','\0','\x7f','"','\\','/','\n','e\u0301']) for _ in range(rng.randrange(10)))
    for _ in range(2000):
        v=value(); t=json.dumps(v,ensure_ascii=True,separators=(',',':'),allow_nan=False)
        same(J(v),t); same(P(t),v)
    return {'reference_roundtrips':2000}
group('independently generated reference vectors',random_reference)
def documents():
    parents=[K.from_native(S,'pull_request',v) for v in ['731',['node','731'],[], '']]
    keys=[]
    for parent in parents:
        for subtype in ['body','title']:
            for local in ['731',['node','731'],[], '']:
                k=K.document(parent,'document',subtype,local); keys.append(k)
                same(P(k.provider_resource_id),['pull_request',parent.provider_resource_id,subtype,local])
                same(k.scoped_document_coordinates(),('pull_request',parent.provider_resource_id,subtype,local))
                same(K(*k.coordinates()),k)
    same(len(set(keys)),len(keys))
    for kind in ['review','comment','thread']:
        refuses(lambda:K.from_native(S,kind,['pull_request',['node','731'],'body','x']))
    return {'distinct_keys':len(keys)}
group('all genuine scoped coordinates and single namespace TEXT profile',documents)
def github():
    db=github_resource_id({'id':731},graphql=False); node=github_resource_id({'id':'731'},graphql=True)
    assert db!=node; same(P(db),'731'); same(P(node),['github:node_id','731'])
    same(github_resource_id({'id':'731','databaseId':731},graphql=True),db)
    same(github_repository_id({'id':'731','databaseId':731},graphql=True),node)
    for payload,gql in [({'id':731},False),({'id':'PR_node'},True)]:
        unit=normalize_pull_request(S,{**payload,'title':'original title','body':'original body'},8,prov,graphql=gql)
        native=P(unit.primary_resource.provider_resource_id)
        for observation in unit.observations:
            if observation.resource==unit.primary_resource: continue
            c=observation.resource.scoped_document_coordinates(); same(c[1],J(native)); same(c[3],native)
    unit=normalize_timeline_event(S,'issue',731,'731',{'id':'731','issue':{'databaseId':731}},8,prov,graphql=True)
    c=unit.primary_resource.scoped_document_coordinates(); same(c,('issue',J('731'),'timeline_event',['github:node_id','731']))
    same(EventReportKey(unit.primary_resource,clock,prov).issue_parent,K.from_native(S,'issue','731'))
    return {'database':db,'node':node,'native_event':c}
group('actual GitHub native namespace and PR/Timeline producers',github)
def nested():
    repository=K.from_native(S,'repository',['github:node_id','731'])
    claim=MappingClaimKey.for_repository(repository,R,clock=clock,provenance_json=prov)
    support=MappingSupport(repository,(claim,)); same(MappingSupport.from_dict(support.to_dict()),support)
    broken=copy.deepcopy(support.to_dict()); broken['provider_repository_id']='731'; broken['supporting_claims'][0]['provider_resource_id']='731'
    refuses(lambda:MappingSupport.from_dict(broken))
    owner=K.from_native(S,'issue',['project','731'])
    for kind,suffix in [('resource',('comments',)),('field',('title','text')),('collection',('comments',prov,'all'))]:
        c=CoverageScope(kind,(*owner.coordinates(),*suffix)); same(json.loads(c.encoded)[:3],list(owner.coordinates()))
        refuses(lambda:CoverageScope(kind,(S,'issue','731',*suffix)))
    collection=CollectionObservation(owner,'children',prov,'{}',8,'complete',(repository,))
    same(json.loads(collection.members_json),[list(repository.coordinates())])
    scope=ExchangeSelectionScope(resource_keys=(owner,repository)); same(ExchangeSelectionScope.from_dict(scope.to_dict()),scope)
    broken=scope.to_dict(); broken['resource_keys'][0][2]='731'; refuses(lambda:ExchangeSelectionScope.from_dict(broken))
    return {'mapping':support.to_dict(),'members':collection.members_json}
group('nested MappingSupport Coverage Collection and selection boundaries',nested)
def cursor():
    token=SnapshotFenceToken('paired',R,T,'a'*64,'b'*64).encode(); observations=[]
    for endpoint in ['context_resources','paired_resources']:
        for identity in [J('é'),'731','"\\u0078"','[null]','"\\ud800"']:
            payload={'v':1,'endpoint_kind':endpoint,'filter_digest':'c'*64,'snapshot_token':token,'last_key':[S,'issue',identity]}
            checksum=hashlib.sha256(('p6-cursor-v1:'+canonical_json(payload)).encode()).hexdigest()
            raw=base64.urlsafe_b64encode(canonical_json({'payload':payload,'checksum_sha256':checksum}).encode()).decode()
            fn=lambda:PaginationCursor.decode(raw,expected_endpoint=endpoint,expected_filter_digest='c'*64,current_snapshot_token=token)
            if identity==J('é'): same(fn().last_key,(S,'issue',identity))
            else: observations.append(refuses(fn))
    return observations
group('freshly checksummed invalid-identity cursors',cursor)
def context_db():
    d=sqlite3.connect(':memory:',isolation_level=None); register_functions(d); d.execute('pragma foreign_keys=on'); d.execute('pragma recursive_triggers=on'); d.executescript(compose('context')); d.execute('insert into providers values(?,?,?)',(S,'test','{}')); return d,ContextStore(d)
def global_loss():
    parent=K.from_native(S,'pull_request','PR-independent'); scoped=K.document(parent,'document','body','D-independent'); global_key=K.global_document(S,P(scoped.provider_resource_id))
    same(global_key,scoped); same(hash(global_key),hash(scoped)); same(tuple(dataclasses.asdict(global_key)),('service_instance_uuidv4','resource_kind','provider_resource_id'))
    d,store=context_db();store.resource(parent)
    initial=refuses(lambda:store.resource(global_key))
    same(d.execute('select count(*) from resources').fetchone(),(1,))
    preserved={}
    for name,k in [('copy',copy.copy(global_key)),('deepcopy',copy.deepcopy(global_key)),('pickle',pickle.loads(pickle.dumps(global_key)))]:preserved[name]=refuses(lambda k=k:store.resource(k))
    losses={}
    for name,k in [('triple',K(*global_key.coordinates())),('asdict',K(**dataclasses.asdict(global_key))),('replace',dataclasses.replace(global_key))]:
        same(k,global_key); decoded=k.scoped_document_coordinates(); store.resource(k)
        losses[name]={'intent':k._document_contract,'decoded_as_scoped':decoded,'accepted':True}
    duplicate=refuses(lambda:store.resource(global_key))
    row=d.execute('select * from resources where resource_kind="document"').fetchone()
    same(row[3:],('pull_request',parent.provider_resource_id,'body','D-independent'))
    same(d.execute('select count(*) from resource_relations').fetchone(),(0,))
    return {'initial_global_refusal':initial,'direct_duplicate_refusal':duplicate,'preserving_operations':preserved,'lossy_operations':losses,'stored_row':row,'factory_state_durable':False}
group('global array shape direct/replay versus triple/asdict/dataclasses.replace intent loss',global_loss)
def storage_controls():
    d,s=context_db(); parent=K.from_native(S,'pull_request','PR'); s.resource(parent)
    for local in [[],['github:node_id','event'],'']:
        key=K.document(parent,'document','body',local); refuses(lambda:s.resource(key))
    # Product DDL still admits legacy noncanonical root IDs: separate I2 scope.
    d.execute('insert into resources values(?,?,?,?,?,?,?)',(S,'issue','731',None,None,None,None))
    refuses(lambda:K(*d.execute('select service_instance_uuidv4,resource_kind,provider_resource_id from resources where resource_kind="issue"').fetchone()))
    return {'raw_product_noncanonical_id_accepted':'731','python_reconstruction_refused':True,'product_generalization_implemented':False}
group('product DDL limitations distinguished from domain and comparison harness',storage_controls)
def sql_harness():
    d=sqlite3.connect(':memory:',isolation_level=None)
    def valid(v):
        try:P(v); return 1
        except (TypeError,ValueError):return 0
    d.create_function('id_valid',1,valid,deterministic=True);d.execute('pragma foreign_keys=on');d.execute('pragma recursive_triggers=on')
    d.executescript('CREATE TABLE r(s TEXT COLLATE BINARY NOT NULL,k TEXT COLLATE BINARY NOT NULL,i TEXT COLLATE BINARY NOT NULL CHECK(typeof(i)="text" AND id_valid(i)=1),PRIMARY KEY(s,k,i)) STRICT, WITHOUT ROWID;CREATE TABLE f(s TEXT NOT NULL,k TEXT NOT NULL,i TEXT NOT NULL,FOREIGN KEY(s,k,i) REFERENCES r(s,k,i)) STRICT;')
    keys=[K.from_native(S,'vendor',v) for v in ['',[],[''],[[]],'é','e\u0301','A','a','731',['731'],['a',['b']]]]
    for k in keys:d.execute('insert into r values(?,?,?)',k.coordinates());d.execute('insert into f values(?,?,?)',k.coordinates())
    same(d.execute('select count(*) from r').fetchone(),(len(keys),))
    refused=[]
    for triple in [(T,'vendor',J('731')),(S,'other',J('731')),(S,'vendor','"\\u0037"'),(None,'vendor',J('731')),(S,None,J('731')),(S,'vendor',None)]:refused.append(refuses(lambda triple=triple:d.execute('insert into f values(?,?,?)',triple)))
    for value in ['731','"é"','[null]','"\\u0078"',None,b'"x"']:
        refused.append(refuses(lambda value=value:d.execute('insert into r values(?,?,?)',(S,'vendor',value))))
    return {'scope':'independent disposable comparison harness, NOT product DDL','distinct_keys':len(keys),'refusals':refused,'fk_check':d.execute('pragma foreign_key_check').fetchall(),'integrity':d.execute('pragma integrity_check').fetchall(),'pragmas':{p:d.execute('pragma '+p).fetchall() for p in ['foreign_keys','recursive_triggers','encoding','journal_mode','synchronous','trusted_schema','temp_store']}}
group('independent SQL BINARY full composite FK NULL/type/canonical gates',sql_harness)
out={'root':str(ROOT),'commit':__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'python':sys.version,'runtime':sqlite3.connect(':memory:').execute('select sqlite_version(),sqlite_source_id()').fetchone(),'groups':results,'passed':sum(x['passed'] for x in results),'failed':sum(not x['passed'] for x in results)}
pathlib.Path(sys.argv[2]).write_text(json.dumps(out,ensure_ascii=True,indent=2)+'\n');print(json.dumps({'passed':out['passed'],'failed':out['failed'],'failed_groups':[x for x in results if not x['passed']]}));sys.exit(bool(out['failed']))
