import sys,pathlib,json,sqlite3,tempfile,hashlib,copy,traceback
ROOT=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(ROOT/'src'))
from repo_catalog.domain.exchange import ExchangePackage,ExchangeSelectionScope,empty_context_section,decode_package,_canonical_content
from repo_catalog.application.exchange import ExchangeService
from repo_catalog.adapters.sqlite.p1_schema import initialize,connect
from repo_catalog.domain.p1_context import ResourceKey,canonical,CoverageScope
from repo_catalog.domain.acquisition import make_provenance
from uuid import uuid4
S='11111111-1111-4111-8111-111111111111';R='33333333-3333-4333-8333-333333333333';I='44444444-4444-4444-8444-444444444444'
owner=ResourceKey.from_native(S,'issue','731'); member=ResourceKey.from_native(S,'repository',['github:node_id','731']); prov=make_provenance('independent://exchange','actual observation')
context=empty_context_section();context['providers']=[dict(service_instance_uuidv4=S,provider_kind='test',configuration_json='{}')]
context['resources']=[dict(zip(('service_instance_uuidv4','resource_kind','provider_resource_id'),k.coordinates())) for k in [owner,member]]
context['collections']=[{**context['resources'][0],'collection_kind':'opaque_children','members_json':canonical([member.coordinates()]),'observed_at_us':8,'provenance_json':prov,'scope_json':'{}','terminal_state':'complete'}]
context['coverage_scopes']=[{'owner_kind':'resource','owner_coordinates_json':CoverageScope.resource(owner,'all').encoded}]
scope=ExchangeSelectionScope(include_core=False,include_context=True,all_selected=True)
observations=[]
def run(name,ctx,should_fail):
    package=ExchangePackage(str(uuid4()),8,I,R,selection_scope=scope,context=ctx)
    content=_canonical_content(package);assert package.digest_sha256==hashlib.sha256(content).hexdigest()
    wire=package.to_dict();p=decode_package(wire)
    with tempfile.TemporaryDirectory(prefix='independent-exchange-',dir='/workspace/independent-task-b-20261021/tmp') as tmp:
        d=pathlib.Path(tmp)
        for role in ['core','context','operational']:initialize(d/(role+'.sqlite3'),role,R,I)
        before=sqlite3.connect(d/'context.sqlite3').execute('select count(*) from resources').fetchone()[0]
        try:
            result=ExchangeService(d).import_package(p,new_request=True)
        except Exception as e:
            if not should_fail: raise
            after=sqlite3.connect(d/'context.sqlite3').execute('select count(*) from resources').fetchone()[0]
            assert after==before==0
            observations.append({'name':name,'digest_consistent':True,'exception':str(e),'type':type(e).__name__,'context_rows_before_after':[before,after]})
        else:
            assert not should_fail,'unexpected domain admission'
            db=connect(d/'context.sqlite3','context'); rows=db.execute('select service_instance_uuidv4,resource_kind,provider_resource_id from resources order by resource_kind').fetchall(); assert len(rows)==2
            observations.append({'name':name,'digest_consistent':True,'admitted_resources':[tuple(row) for row in rows]})
run('valid nested native array reference roundtrip',copy.deepcopy(context),False)
for name,modify in [
    ('invalid nested Collection member identity',lambda c:c['collections'][0].update(members_json=canonical([(S,'repository','731')]))),
    ('invalid Coverage owner identity',lambda c:c['coverage_scopes'][0].update(owner_coordinates_json=canonical([S,'issue','731','all']))),
    ('invalid root Resource identity',lambda c:c['resources'][1].update(provider_resource_id='731')),
    ('alternate nested Collection member escape',lambda c:c['collections'][0].update(members_json=canonical([(S,'repository','"\\u0037"')]))),
]:
    c=copy.deepcopy(context);modify(c);run(name,c,True)
out={'runtime':sqlite3.connect(':memory:').execute('select sqlite_version(),sqlite_source_id()').fetchone(),'groups':observations,'passed':len(observations)}
pathlib.Path(sys.argv[2]).write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps(out))
