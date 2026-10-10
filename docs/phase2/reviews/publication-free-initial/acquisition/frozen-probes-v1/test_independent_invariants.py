"""Independent admission, transaction and progress counterexamples."""
import json
import sqlite3
import uuid

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.adapters.sqlite.transactions import atomic_unit
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from test_independent_acquisition import prepare
from tests.support.github_runtime import github_runtime


@pytest.fixture
def bare_store(tmp_path):
    path = tmp_path/'disposable-review-state'
    MaintenanceService(path).init('catalog-text-v1',64*1024*1024,0)
    with Store(path) as store:
        store.execute('CREATE TABLE probe(value TEXT UNIQUE,presence INTEGER,evidence TEXT)')
        store.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
        store.execute('CREATE TABLE child(id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)')
        yield store


@pytest.mark.parametrize('mechanism',['store','shared'])
@pytest.mark.parametrize('failure',['body','statement','commit','release'])
def test_atomic_matrix_preserves_unit_and_outer_work(bare_store,mechanism,failure):
    store = bare_store
    unit = store.transaction if mechanism == 'store' else lambda:atomic_unit(store.connection)
    if failure=='release':
        # Deferred constraints fail when releasing an outermost shared savepoint,
        # whereas nested release correctly defers them to the containing COMMIT.
        with pytest.raises(sqlite3.IntegrityError):
            with unit():
                store.execute('INSERT INTO probe VALUES(?,?,?)',('outer',1,'v1'))
                with unit():
                    store.execute('INSERT INTO probe VALUES(?,?,?)',('inner',1,'v2'))
                    store.execute('INSERT INTO child VALUES(404)')
                    store.advance_local_revision()
        assert not store.connection.in_transaction
        assert store.all('SELECT * FROM probe') == []
        assert store.revision()['local_revision']==0
        return
    with unit():
        store.execute('INSERT INTO probe VALUES(?,?,?)',('outer',1,'v1'))
        if failure=='commit':
            # Independently exercise outer COMMIT instead of an inner savepoint.
            pass
        else:
            with pytest.raises((ValueError,sqlite3.IntegrityError)):
                with unit():
                    store.execute('INSERT INTO probe VALUES(?,?,?)',('inner',0,'v2'))
                    store.advance_local_revision()
                    if failure=='body': raise ValueError('actual body failure')
                    store.execute('INSERT INTO probe VALUES(?,?,?)',('outer',1,'v3'))
            store.execute('INSERT INTO probe VALUES(?,?,?)',('after',1,'v4'))
    if failure=='commit':
        with pytest.raises(sqlite3.IntegrityError):
            with unit():
                store.execute('INSERT INTO probe VALUES(?,?,?)',('uncommitted',0,'bad'))
                store.execute('INSERT INTO child VALUES(999)')
                store.advance_local_revision()
        assert [r[0] for r in store.all('SELECT * FROM probe')] == ['outer']
    else:
        assert [r[0] for r in store.all('SELECT * FROM probe')] == ['outer','after']
    assert store.revision()['local_revision']==0
    assert not store.connection.in_transaction


@pytest.mark.parametrize('nested',[False,True])
@pytest.mark.parametrize('mechanism',['store','shared'])
def test_cleanup_failure_retires_connection(bare_store,nested,mechanism,monkeypatch):
    store = bare_store
    class Proxy:
        def __init__(self): self.closed=False
        @property
        def in_transaction(self): return store.connection.in_transaction
        def execute(self,sql):
            if sql.startswith('ROLLBACK'): raise OSError('cleanup fault with secret text')
            return store.connection.execute(sql)
        def close(self):
            self.closed=True
            store.connection.close()
    proxy=Proxy()
    if nested: store.execute('BEGIN IMMEDIATE')
    if mechanism=='store':
        execute=store.execute
        def fail_cleanup(sql,args=()):
            if sql.startswith('ROLLBACK'):raise OSError('cleanup fault with secret text')
            return execute(sql,args)
        monkeypatch.setattr(store,'execute',fail_cleanup)
    unit=store.transaction if mechanism=='store' else lambda:atomic_unit(proxy)
    with pytest.raises(ValueError,match='primary failure') as failure:
        with unit():
            store.execute("INSERT INTO probe VALUES('failed',0,'bad')")
            store.advance_local_revision()
            raise ValueError('primary failure')
    if mechanism=='shared':assert proxy.closed
    assert failure.value.__notes__ == ['Transaction cleanup failed: OSError']
    with Store(store.path) as fresh:
        assert fresh.all('SELECT * FROM probe') == []
        assert fresh.revision()['local_revision']==0


def test_resource_update_constraint_failure_has_no_text_or_origin_leak(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    old=tuple(store.one("SELECT * FROM document_state WHERE kind='pr-body'"))
    text_count=store.one('SELECT count(*) FROM text_bodies')[0]
    revision=store.revision()
    store.execute("CREATE TEMP TRIGGER reject_new_body BEFORE UPDATE ON document_state WHEN NEW.kind='pr-body' BEGIN SELECT RAISE(ABORT,'evidence sink unavailable'); END")
    candidate=current_parser.document({**data,'body':'would-leak','updated_at':'2026-02-01T00:00:00Z'},collector.facts.current_context(repo,parent['change_request_id'],api.url+'/pulls/1'),200,'pr-body')
    candidate['parsed_at_us']=201
    with pytest.raises(sqlite3.IntegrityError):
        CurrentApiState(store).admit('document_state',candidate,source='import')
    assert tuple(store.one("SELECT * FROM document_state WHERE kind='pr-body'"))==old
    assert store.one('SELECT count(*) FROM text_bodies')[0]==text_count
    assert store.revision()==revision


def test_sparse_clocks_null_and_inherited_v1_v2_origin(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    adapter=CurrentApiState(store)
    scope=collector.facts.current_context(repo,parent['change_request_id'],api.url+'/pulls/1')
    def document(clock,version,**fields):
        candidate=current_parser.document({'id':1101,'number':1,'updated_at':clock,**fields},scope,200,'pr-body')
        candidate.update(parsed_at_us=202,parser_module='review.synthetic.parser',parser_version=version)
        return candidate
    assert adapter.admit('document_state',document('2026-02-01T00:00:00Z','v2',user={'login':'changed'}),source='import').status=='accepted'
    row=adapter.candidate_from_row('document_state',store.one("SELECT * FROM document_state WHERE kind='pr-body'"))
    assert row['body']=='first body'
    assert row['field_evidence']['["body"]']['parser_version']=='3'
    assert row['field_evidence']['["author"]']['parser_version']=='v2'
    assert adapter.admit('document_state',document('2026-03-01T00:00:00Z','v3',body=None),source='import').status=='accepted'
    row=adapter.candidate_from_row('document_state',store.one("SELECT * FROM document_state WHERE kind='pr-body'"))
    assert row['body'] is None and row['body_status']=='provider-null'
    assert adapter.admit('document_state',document('2026-02-15T00:00:00Z','v4',body='old'),source='import').status in {'stale','identical'}
    assert adapter.admit('document_state',document('2026-03-01T00:00:00Z','v5',body='equal-clock-alternative'),source='import').status=='conflict'
    assert store.one("SELECT count(*) FROM eligible_document_state WHERE kind='pr-body'")[0]==0


def test_coverage_candidate_order_and_unknown(github_runtime):
    store,repo,git,api=github_runtime
    for stamp,state,expected in [(100,'complete','complete'),(200,'partial','partial'),(175,'complete','partial'),(300,'complete','complete'),(300,'partial','conflict'),(400,'unknown','unknown')]:
        store.coverage(repo['repository_uuidv4'],'pr-list',state,observed_at_us=stamp)
        assert store.one("SELECT coverage_state FROM current_coverage WHERE kind='pr-list'")[0]==expected
    assert len(store.all('PRAGMA table_info(coverage_claims)'))==5


def test_terminal_empty_missing_terminal_and_missing_child(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    no_terminal=collector.facts.begin(repo,parent['change_request_id'],'review',job,api.url+'/review')
    with pytest.raises(CatalogError,match='terminal'):
        collector.facts.finish(no_terminal)
    collector.facts.page(no_terminal,100,None,[])
    collector.facts.finish(no_terminal)
    assert CurrentCollectionProof(store.connection).evidence(no_terminal['fetch_collection_id'])['terminal']
    api.route=lambda method,path,params,body:({'data':{'repository':{'pullRequest':{'id':'PR_LOCAL','reviewThreads':{'nodes':[{'id':'THREAD_1','isResolved':False,'isOutdated':False}], 'pageInfo':{'hasNextPage':False,'endCursor':None}}}}}}, {})
    with pytest.raises(CatalogError):collector.threads(repo,parent,job)
    assert store.one("SELECT coverage_state FROM current_coverage WHERE kind='threads'")[0]=='partial'
    assert not store.one("SELECT 1 FROM completion_markers m JOIN fetch_collections f USING(fetch_collection_id) WHERE f.kind='threads' AND m.asserted_state='complete'")


def test_cancel_resume_prefix_and_cache_loss_do_not_invalidate_resources(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    count={'requests':0}
    url=api.url+'/repos/fixture/alpha/pulls'
    def route(method,path,params,body):
        count['requests']+=1
        assert not store.connection.in_transaction
        if not params.get('page'):
            return [data], {'Link':f'<{url}?page=2>; rel="next"'}
        collector.token.cancelled=True
        return [], {}
    api.route=route
    normalizer=lambda item,scope,revision,position,stamp,listing:collector.ensure_pr(repo,item,scope,revision,position,stamp)[1]
    with pytest.raises(CatalogError) as failed:collector.collection(repo,None,'pr-list',job,url,normalizer,context={'distinct':'resume-case'})
    assert failed.value.code=='CANCELLED'
    assert store.one("SELECT count(*) FROM eligible_document_state WHERE kind='pr-body'")[0]==1
    collector.token.cancelled=False
    store.execute("UPDATE collection_progress SET cursor=NULL WHERE state='partial'")
    with pytest.raises(CatalogError) as failed:collector.collection(repo,None,'pr-list',job,url,normalizer,context={'distinct':'resume-case'})
    assert failed.value.code=='RESUME_UNAVAILABLE'
    assert store.one("SELECT count(*) FROM eligible_document_state WHERE kind='pr-body'")[0]==1


def test_304_cache_loss_forces_real_body_then_rejects_repeat(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    requests=[]
    def request(method,url,**kwargs):
        assert not store.connection.in_transaction
        requests.append(kwargs)
        return httpx.Response(304,request=httpx.Request(method,url),extensions={'catalog_observed_at_us':200})
    collector.http.request=request
    with pytest.raises(CatalogError) as failure:collector.detail(repo,parent,job,api.url+'/pulls/1')
    assert failure.value.code=='REUSE_UNAVAILABLE'
    assert len(requests)==2 and requests[1]['headers']=={'Cache-Control':'no-cache'}
    assert store.one("SELECT count(*) FROM eligible_document_state WHERE kind='pr-body'")[0]==1


def test_escaped_field_alias_is_rejected_by_sql(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    context=collector.facts.current_context(repo,None,api.url+'/issues/1')
    candidate=current_parser.issue({'id':33,'number':33,'title':'issue','body':'body','state':'open','updated_at':'2026-01-01T00:00:00Z'},context,100)
    candidate['parsed_at_us']=101
    CurrentResources(store).admit(candidate,source='import')
    evidence=json.loads(store.one("SELECT field_evidence_json FROM issue_resources WHERE kind='issue'")[0])
    evidence['["\\u0062ody"]']=evidence['["body"]']
    with pytest.raises(sqlite3.IntegrityError):
        store.execute("UPDATE issue_resources SET field_evidence_json=? WHERE kind='issue'",(json.dumps(evidence),))


def test_code_check_304_cache_loss_fetches_real_representation(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    calls=[]
    def request(method,url,**kwargs):
        assert not store.connection.in_transaction
        calls.append(kwargs)
        return httpx.Response(304 if len(calls)==1 else 200,
            content=b'' if len(calls)==1 else json.dumps(data).encode(),
            request=httpx.Request(method,url),extensions={'catalog_observed_at_us':200})
    collector.http.request=request
    value=collector.code_check(repo,parent,job,api.url+'/pulls/1')
    assert value['id']==1101 and len(calls)==2


@pytest.mark.parametrize('pending',[False,True])
def test_capture_cannot_hide_provider_response_replica(github_runtime,pending):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    context=collector.facts.current_context(repo,parent['change_request_id'],api.url+'/pulls/1')
    context['acquisition_scope']={**context['acquisition_scope'],'provider_response':{'body':'raw-provider-sentinel','unknown_field':[{'secret':'dummy-only'}], 'headers':{'x-provider':'dummy'}}}
    candidate=current_parser.document({**data,'body':'new domain body','updated_at':'2026-02-01T00:00:00Z'},context,200,'pr-body')
    candidate['parsed_at_us']=201
    if pending:
        candidate['change_request_id']='missing-parent'
        candidate['acquisition_scope']['change_request_id']='missing-parent'
    with pytest.raises(CatalogError):
        CurrentApiState(store).admit('document_state',candidate,source='import')


def test_real_acquisition_complete_partial_older_complete_new_complete(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    url=api.url+'/repos/fixture/alpha/pulls'
    for timestamp,malformed,expected in [(100,False,'complete'),(200,True,'partial'),(175,False,'partial'),(300,False,'complete')]:
        task=JobService(store).create('sync',{'kind':'pr'})
        collector.http.clock_us=lambda:timestamp
        api.route=lambda method,path,params,body:([{**data,'title':[]} if malformed else data],{})
        normalizer=lambda item,scope,revision,position,stamp,listing:collector.ensure_pr(repo,item,scope,revision,position,stamp)[1]
        if malformed:
            with pytest.raises(CatalogError):collector.collection(repo,None,'pr-list',task,url,normalizer)
        else:collector.collection(repo,None,'pr-list',task,url,normalizer)
        row=store.one("SELECT * FROM current_coverage WHERE kind='pr-list'")
        assert row['coverage_state']==expected
        assert row['observed_at_us']==200 if timestamp==175 else row['observed_at_us']==timestamp
    assert not store.all('PRAGMA foreign_key_check')
    assert store.one('PRAGMA integrity_check')[0]=='ok'


def test_source_partial_R1_preserves_R2_and_inherited_origin(github_runtime):
    store,repo,git,api=github_runtime
    adapter=CurrentApiState(store)
    second=str(uuid.uuid4())
    store.execute("INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'R2','{}')",(second,))
    source=store.one("SELECT * FROM sources WHERE source_id='source'")
    scope={'source_registration_uuidv4':source['source_registration_uuidv4'],'service_instance_uuidv4':source['service_instance_uuidv4'],'endpoint':api.url+'/inventory','owner':'fixture'}
    for ident,name in [(repo['repository_uuidv4'],'R1'),(second,'R2')]:
        revision=store.revision()
        assert adapter.confirm_source_repository('source',ident,observed_at_us=100,parsed_at_us=101,scope=scope,parser_module='review.source',parser_version='v1',name=name,metadata={'private':False},base_revision=revision,scope_context=scope)=='accepted'
    before_R2=tuple(store.one('SELECT * FROM source_repositories WHERE repository_uuidv4=?',(second,)))
    adapter.assess_source_inventory('source',scope=scope,observed_at_us=100,state='complete',members=[repo['repository_uuidv4'],second],terminal=True,parser_module='review.source',parser_version='v1')
    revision=store.revision()
    assert adapter.confirm_source_repository('source',repo['repository_uuidv4'],observed_at_us=200,parsed_at_us=201,scope=scope,parser_module='review.source',parser_version='v2',metadata={'archived':True},base_revision=revision,scope_context=scope)=='accepted'
    adapter.assess_source_inventory('source',scope=scope,observed_at_us=200,state='partial',members=[repo['repository_uuidv4']],terminal=False,parser_module='review.source',parser_version='v2')
    assert tuple(store.one('SELECT * FROM source_repositories WHERE repository_uuidv4=?',(second,)))==before_R2
    row=store.one('SELECT * FROM source_repositories WHERE repository_uuidv4=?',(repo['repository_uuidv4'],))
    evidence=json.loads(row['field_evidence_json'])
    assert row['name']=='R1'
    assert evidence['["name"]']['parser_version']=='v1'
    assert evidence['["metadata","archived"]']['parser_version']=='v2'


def test_receiver_local_check_and_scope_revision_fences(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime,provider_clock=False)
    adapter=CurrentApiState(store)
    context=collector.facts.current_context(repo,parent['change_request_id'],api.url+'/pulls/1')
    def make(body,checked=None):
        candidate=current_parser.document({**data,'body':body},context,200,'pr-body')
        candidate['parsed_at_us']=201
        if checked is not None:candidate['last_checked_at_us']=checked
        return candidate
    assert adapter.admit('document_state',make('first body',999999),source='import').status=='identical'
    assert store.one("SELECT last_checked_at_us FROM document_state WHERE kind='pr-body'")[0]==100
    stale_revision=store.revision()
    store.advance_local_revision()
    assert adapter.admit('document_state',make('stale unclocked'),source='live',base_revision=stale_revision,scope_context=context['acquisition_scope']).status=='conflict'
    fresh_revision=store.revision()
    assert adapter.admit('document_state',make('fresh live'),source='live',base_revision=fresh_revision,scope_context={**context['acquisition_scope'],'endpoint':'different'}).status=='conflict'
    fresh_revision=store.revision()
    assert adapter.admit('document_state',make('fresh live'),source='live',base_revision=fresh_revision,scope_context=context['acquisition_scope']).status=='accepted'
    assert store.one("SELECT last_checked_at_us FROM document_state WHERE kind='pr-body'")[0]==200


def test_detached_captured_ids_survive_without_fabricating_registrations(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    resources=CurrentResources(store)
    context=collector.facts.current_context(repo,None,api.url+'/issues/33')
    ordinary=current_parser.issue({'id':33,'number':33,'title':'issue','state':'open'},context,100)
    ordinary['parsed_at_us']=101
    assert resources.admit(ordinary,source='import').status=='accepted'
    captured_repo=str(uuid.uuid4());captured_source=str(uuid.uuid4())
    detached={**context,'acquisition_scope':{**context['acquisition_scope'],'repository_uuidv4':captured_repo,'repository_binding_id':'historical-detached','source_registration_uuidv4':captured_source}}
    child=current_parser.issue_comment({'id':34,'body':'captured before transfer'},detached,50,'33')
    child.update(provider_issue_number=33,parsed_at_us=51)
    assert resources.admit(child,source='import').status=='accepted'
    assert not store.one('SELECT 1 FROM repositories WHERE repository_uuidv4=?',(captured_repo,))
    assert not store.one('SELECT 1 FROM sources WHERE source_registration_uuidv4=?',(captured_source,))
    saved=json.loads(store.one("SELECT acquisition_scope_json FROM issue_resources WHERE kind='issue-comment'")[0])
    assert saved['repository_uuidv4']==captured_repo
    registered_other=str(uuid.uuid4())
    store.execute("INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'different-known-repository','{}')",(registered_other,))
    store.execute("INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,metadata) VALUES('historical-detached',?,?,'{}')",(registered_other,context['service_instance_uuidv4']))
    with pytest.raises(CatalogError):resources.admit(child,source='import')


def test_optional_archive_warning_failures_are_bounded_and_nonfatal(github_runtime,monkeypatch):
    import warnings
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    class Recorder:
        def record_exchange(self,context,body):raise RuntimeError('raw-provider-secret-must-not-retain')
    collector.http.recorder=Recorder()
    monkeypatch.setattr(warnings,'warn',lambda *args,**kwargs:(_ for _ in ()).throw(OSError('broken diagnostic hook')))
    api.route=lambda method,path,params,body:({**data,'body':'kept domain body','updated_at':'2026-02-01T00:00:00Z','opaque_response_marker':'raw-provider-secret-must-not-retain'}, {})
    collector.detail(repo,parent,job,api.url+'/pulls/1')
    assert store.one("SELECT t.body FROM eligible_document_state d JOIN text_bodies t ON t.sha256=d.text_body_sha256 WHERE d.kind='pr-body'")[0]=='kept domain body'
    assert collector.recording_diagnostics[0]['code']=='ARCHIVE_FAILURE'
    assert 'raw-provider-secret' not in json.dumps(collector.recording_diagnostics)
    assert store.one('SELECT count(*) FROM stored_bytes')[0]==0
    assert all('raw-provider-secret' not in row[0] for row in store.all('SELECT record_json FROM exchange_staging'))


def test_head_change_does_not_borrow_previous_assessment(github_runtime):
    from types import SimpleNamespace
    from repo_catalog.application.pr_queries import _code_observation
    store,repo,git,api=github_runtime
    collector=GitHubCollector(store,CancellationToken())
    collector.http.clock_us=lambda:100
    job=JobService(store).create('sync',{'kind':'pr'})
    store.expected_attempt=1
    collector.sync(repo,job)
    code=store.one("SELECT * FROM code_assessments WHERE state='complete' LIMIT 1")
    parent=store.one('SELECT * FROM change_requests WHERE change_request_id=?',(code['change_request_id'],))
    query=SimpleNamespace(s=store)
    assert _code_observation(query,parent) is not None
    data=collector._current_pr_value(parent['change_request_id'])
    data.update(id=10000+parent['provider_change_request_number'],number=parent['provider_change_request_number'],head={'sha':git.alpha.commits['N']},updated_at='2026-02-01T00:00:00Z')
    context=collector.facts.current_context(repo,parent['change_request_id'],api.url+'/pulls/changed')
    candidate=current_parser.pull_request(data,context,200)
    candidate['parsed_at_us']=201
    adapter=CurrentApiState(store)
    assert adapter.admit('change_request_state',candidate,source='live',base_revision=store.revision(),scope_context=context['acquisition_scope']).status=='accepted'
    assert _code_observation(query,parent) is None
    assert store.one('SELECT count(*) FROM code_assessments WHERE code_assessment_id=?',(code['code_assessment_id'],))[0]==1
    assert not store.one("SELECT 1 FROM sqlite_schema WHERE name='change_request_observations'")
