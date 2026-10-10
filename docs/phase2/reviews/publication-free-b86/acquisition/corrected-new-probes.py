"""Additional independent counterexamples for shared corrections, b86 candidate."""
import copy
import json
import sqlite3

import httpx
import pytest

from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.json_contracts import JsonContractError, validate_catalog
from repo_catalog.application.collection_service import CollectionService
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CatalogError
from tests.support.github_runtime import github_runtime
from test_independent_acquisition import prepare


@pytest.mark.parametrize('kind',['foreign-id','foreign-number','bool-number','missing-owner','matching-number','matching-id'])
def test_graphql_owner_variants(github_runtime,kind):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    owner={'id':'PR_LOCAL'}
    if kind=='foreign-id':owner={'id':'PR_FOREIGN','number':1}
    elif kind=='foreign-number':owner={'id':'PR_LOCAL','number':2}
    elif kind=='bool-number':owner={'id':'PR_LOCAL','number':True}
    elif kind=='missing-owner':owner={}
    elif kind=='matching-number':
        # A matching requested number remains usable when the API has not
        # supplied an opaque alias. Do not invent alias authority.
        owner={'number':1}
        store.execute("UPDATE change_request_state SET metadata=json_remove(metadata,'$.node_id'),field_evidence_json=json_remove(field_evidence_json,'$.\"[\\\"metadata\\\",\\\"node_id\\\"]\"')")
    owner.update(reviewThreads={'nodes':[],'pageInfo':{'hasNextPage':False,'endCursor':None}},mergeCommit=None,potentialMergeCommit=None)
    api.route=lambda method,path,params,body:({'data':{'repository':{'pullRequest':owner}}},{})
    if kind.startswith('matching'):
        assert collector.threads(repo,parent,job)=={'merge':None,'test-merge':None}
        assert store.one("SELECT coverage_state FROM current_coverage WHERE kind='threads'")[0]=='complete'
    else:
        with pytest.raises(CatalogError) as failure:collector.threads(repo,parent,job)
        assert failure.value.code in {'SCOPE_MISMATCH','API_SCHEMA'}
        assert not store.one("SELECT 1 FROM completion_markers m JOIN fetch_collections f USING(fetch_collection_id) WHERE f.kind='threads' AND m.asserted_state='complete'")


@pytest.mark.parametrize('target',['current-scope','field-scope','pending-scope','pending-field-scope'])
def test_standalone_sql_rejects_hidden_scope_replica(github_runtime,target):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    blob={'provider_response':{'body':'synthetic-original-body','headers':{'fixture':'dummy'}}}
    if target=='current-scope':
        scope=json.loads(store.one("SELECT acquisition_scope_json FROM document_state WHERE kind='pr-body'")[0])
        scope.update(blob)
        sql="UPDATE document_state SET acquisition_scope_json=? WHERE kind='pr-body'"
        args=(json.dumps(scope),)
    elif target=='field-scope':
        proofs=json.loads(store.one("SELECT field_evidence_json FROM document_state WHERE kind='pr-body'")[0])
        proofs['["body"]']['acquisition_scope'].update(blob)
        sql="UPDATE document_state SET field_evidence_json=? WHERE kind='pr-body'"
        args=(json.dumps(proofs),)
    else:
        context=collector.facts.current_context(repo,parent['change_request_id'],api.url+'/pulls/1')
        candidate=current_parser.document(data,context,200,'pr-body')
        candidate.update(change_request_id='missing-parent',parsed_at_us=201)
        candidate['acquisition_scope']['change_request_id']='missing-parent'
        assert CurrentApiState(store).admit('document_state',candidate,source='import').status=='missing_dependency'
        saved=store.one("SELECT * FROM exchange_staging WHERE table_name='document_state'")
        record=json.loads(saved['record_json'])
        if target=='pending-scope':record['acquisition_scope'].update(blob)
        else:record['field_evidence']['["body"]']['acquisition_scope'].update(blob)
        sql='UPDATE exchange_staging SET record_json=? WHERE record_key=?'
        args=(json.dumps(record),saved['record_key'])
    with pytest.raises(sqlite3.IntegrityError):store.execute(sql,args)
    assert validate_catalog(store.connection)['records_checked']>0


def test_thread_member_without_required_child_cannot_complete(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    with store.transaction():
        scope=collector.facts.begin(repo,parent['change_request_id'],'threads',job,api.url+'/graphql',{'owner':'fixture','name':'alpha','number':1,'query_kind':'review-thread-root'})
        context=collector.facts.current_context(repo,parent['change_request_id'],api.url+'/graphql')
        thread=current_parser.thread({'id':'THREAD_REQUIREMENT_MISSING','isResolved':False},context,200)
        assert collector.facts.admit_current(thread,store.revision()).status=='accepted'
        collector.facts.page(scope,200,None,[collector.member(thread)])
    # The thread itself is valid. A terminal parent receipt cannot drop its
    # required child roster relation, even with matching receipt fields/counts.
    assert store.one('SELECT count(*) FROM eligible_review_thread_state')[0]==1
    with pytest.raises((CatalogError,sqlite3.IntegrityError)):
        with store.transaction():collector.facts.finish(scope)
    flat={'kind':'current-resource-pages-v1','page_ordinals':[0],'terminal':True}
    with pytest.raises(sqlite3.IntegrityError):
        store.execute("INSERT INTO completion_markers(fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,'complete',?,200)",(scope['fetch_collection_id'],json.dumps(flat)))
    assert not store.one('SELECT 1 FROM completion_markers WHERE fetch_collection_id=?',(scope['fetch_collection_id'],))


def test_foreign_child_requirement_does_not_discharge_terminal_parent(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    api.route=lambda method,path,params,body:({'data':{'repository':{'pullRequest':{
        'id':'PR_LOCAL','number':1,'reviewThreads':{'nodes':[{'id':'THREAD_1','isResolved':False,'comments':{'nodes':[],'pageInfo':{'hasNextPage':True,'endCursor':'next-child'}}}], 'pageInfo':{'hasNextPage':False,'endCursor':None}},'mergeCommit':None,'potentialMergeCommit':None}}}}, {}) if 'RepoCatalogThreads' in body['query'] else ({'data':{'node':{'id':'THREAD_FOREIGN','comments':{'nodes':[],'pageInfo':{'hasNextPage':False,'endCursor':None}}}}},{})
    with pytest.raises(CatalogError) as failure:collector.threads(repo,parent,job)
    assert failure.value.code=='SCOPE_MISMATCH'
    assert store.one('SELECT count(*) FROM eligible_review_thread_state')[0]==1
    assert store.one("SELECT coverage_state FROM current_coverage WHERE kind='threads'")[0]=='partial'
    assert not store.one("SELECT 1 FROM completion_markers m JOIN fetch_collections f USING(fetch_collection_id) WHERE f.kind='threads' AND m.asserted_state='complete'")


def test_real_permissions_header_reaches_field_origin(github_runtime):
    store,repo,git,api=github_runtime
    job=JobService(store).create('sync',{'kind':'pr'})
    store.expected_attempt=1
    # Use the real provider transport header route rather than assigning facts.
    route=api.route
    def headers(method,path,params,body):
        value,headers=route(method,path,params,body)
        if path=='/user':headers['x-oauth-scopes']='repo, read:org'
        return value,headers
    api.route=headers
    # A fresh collector avoids closing the prepare collector's owned transport.
    from repo_catalog.adapters.github.collector import GitHubCollector
    from repo_catalog.domain.models import CancellationToken
    acquisition=GitHubCollector(store,CancellationToken())
    acquisition.http.clock_us=lambda:300
    acquisition.sync(repo,job)
    assert acquisition.facts.permissions==['read:org','repo']
    row=store.one("SELECT field_evidence_json FROM document_state WHERE kind='pr-body' LIMIT 1")
    assert json.loads(row[0])['["body"]']['acquisition_scope']['observed_permissions']==['read:org','repo']


def test_redirect_does_not_forge_fence_after_final_request(github_runtime):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime,provider_clock=False)
    def request(method,url,**kwargs):
        assert not store.connection.in_transaction
        if url.endswith('/alpha/pulls/1'):
            return httpx.Response(301,headers={'location':api.url+'/repos/fixture/renamed/pulls/1'},request=httpx.Request(method,url))
        if url.endswith('/repos/fixture/renamed'):
            return httpx.Response(200,json={'id':101,'full_name':'fixture/renamed'},request=httpx.Request(method,url),extensions={'catalog_observed_at_us':200})
        # An independent writer advances revision while the final response is
        # in flight. Refreshing the fence after response would wrongly authorize.
        store.advance_local_revision()
        return httpx.Response(200,json={**data,'body':'stale while in flight','updated_at':None},request=httpx.Request(method,url),extensions={'catalog_observed_at_us':201})
    collector.http.request=request
    with pytest.raises(CatalogError) as failure:collector.detail(repo,parent,job,api.url+'/repos/fixture/alpha/pulls/1')
    assert failure.value.code=='CURRENT_STATE_UNRESOLVED'
    assert store.one("SELECT t.body FROM document_state d JOIN text_bodies t ON t.sha256=d.text_body_sha256 WHERE d.kind='pr-body'")[0]=='first body'


def test_credential_loss_before_acquisition_is_operational(github_runtime,monkeypatch):
    store,repo,git,api=github_runtime
    collector,parent,job,data=prepare(github_runtime)
    service=CollectionService(store.path)
    real=CollectionService._discover
    before=store.one('SELECT count(*) FROM source_inventory_assessments')[0]
    def lose(self,current,task,plan):
        monkeypatch.delenv('GH_TOKEN',raising=False)
        return real(self,current,task,plan)
    monkeypatch.setattr(CollectionService,'_discover',lose)
    requests=len(api.requests)
    result=service.discover('source')
    assert result.status=='partial'
    assert len(api.requests)==requests
    assert store.one('SELECT count(*) FROM source_inventory_assessments')[0]==before
    attempt=store.one("SELECT a.* FROM job_attempts a JOIN jobs j USING(job_id) WHERE j.kind='discover' ORDER BY a.created_at_us DESC LIMIT 1")
    assert attempt['state']=='complete'
    checkpoint=json.loads(attempt['checkpoint'])
    assert checkpoint['result']['source_outcomes'][0]['state']=='skipped'
    assert store.one("SELECT count(*) FROM eligible_document_state WHERE kind='pr-body'")[0]==1
    assert 'fixture-dummy' not in store.one('SELECT request FROM jobs ORDER BY created_at_us DESC LIMIT 1')[0]
