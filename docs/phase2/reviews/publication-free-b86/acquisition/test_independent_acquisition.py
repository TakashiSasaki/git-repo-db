"""Independent synthetic review probes; no retained catalogs or authenticated hosts."""
import json
import hashlib
import sqlite3

import httpx
import pytest

from repo_catalog.adapters.github.collector import GitHubCollector
from repo_catalog.adapters.github import current_parser
from repo_catalog.adapters.github.persistence import canonical
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.transactions import atomic_unit
from repo_catalog.application.job_service import JobService
from repo_catalog.domain.models import CancellationToken, CatalogError
from tests.support.github_runtime import github_runtime


def prepare(runtime, clock=100, provider_clock=True):
    store, repo, git, api = runtime
    collector = GitHubCollector(store, CancellationToken())
    collector.http.clock_us = lambda: clock
    collector.facts.principal = '10'
    job = JobService(store).create('sync', {'kind': 'pr'})
    store.expected_attempt = 1
    data = {'id': 1101, 'number': 1, 'title': 'first', 'body': 'first body',
            'updated_at': '2026-01-01T00:00:00Z' if provider_clock else None, 'state': 'open',
            'node_id':'PR_LOCAL', 'head': {'sha': git.alpha.commits['N']}, 'base': {'sha': git.alpha.commits['N']}}
    with store.transaction():
        scope = collector.facts.begin(repo, None, 'pr-list', job, api.url+'/repos/fixture/alpha/pulls')
        change, members = collector.ensure_pr(repo, data, scope, store.revision(), 0, clock)
        collector.facts.page(scope, clock, None, members)
        collector.facts.finish(scope)
        collector.facts.advance_revision()
    parent = store.one('SELECT * FROM change_requests WHERE change_request_id=?', (change,))
    return collector, parent, job, data


def test_capped_commits_still_collect_independent_files(github_runtime):
    store, repo, git, api = github_runtime
    collector, parent, job, data = prepare(github_runtime)
    data.update(commits=251, changed_files=1)
    seen = []
    def route(method, path, params, body):
        seen.append(path)
        if path.endswith('/commits'):
            return [{'sha': git.alpha.commits['N']}], {}
        if path.endswith('/files'):
            return [{'filename':'independent.txt', 'status':'modified', 'sha':git.alpha.blob(b'file bytes')}], {}
        raise AssertionError(path)
    api.route = route
    try:
        collector._code_collect(repo, parent, job, api.url+'/repos/fixture/alpha/pulls/1', data)
    except CatalogError:
        pass
    assert any(path.endswith('/files') for path in seen), seen
    assert store.one('SELECT count(*) FROM code_file_changes')[0] == 1


def test_partial_listing_ids_recoverable_for_assessment(github_runtime):
    store, repo, git, api = github_runtime
    collector=GitHubCollector(store,CancellationToken())
    collector.http.clock_us=lambda:200
    task=JobService(store).create('sync',{'kind':'pr'})
    store.expected_attempt=1
    route=api.route
    def capped_route(method,path,params,body):
        value,headers=route(method,path,params,body)
        if isinstance(value,dict) and path.endswith('/pulls/41'):
            value={**value,'commits':251}
        return value,headers
    api.route=capped_route
    with pytest.raises(CatalogError):collector.sync(repo,task)
    partial=store.one("SELECT l.code_listing_id FROM code_listings l JOIN change_requests c USING(change_request_id) WHERE c.provider_change_request_number=41 AND l.kind='commits'")
    assessment=store.one('SELECT a.* FROM code_assessments a JOIN change_requests c USING(change_request_id) WHERE c.provider_change_request_number=41')
    assert assessment['commit_code_listing_id']==partial[0], dict(assessment)


def test_field_capture_records_observed_permissions(github_runtime):
    store, repo, git, api = github_runtime
    collector, parent, job, data = prepare(github_runtime)
    collector.facts.permissions = ['repo', 'read:org']
    context = collector.facts.current_context(repo, parent['change_request_id'], api.url+'/repos/fixture/alpha/pulls/1')
    assert context['acquisition_scope'].get('observed_permissions') == collector.facts.permissions


def test_sparse_rest_detail_preserves_title(github_runtime):
    store, repo, git, api = github_runtime
    collector, parent, job, data = prepare(github_runtime)
    data = {**data, 'body':'sparse body', 'updated_at':'2026-02-01T00:00:00Z'}
    del data['title']
    api.route = lambda method, path, params, body: (data, {})
    collector.detail(repo, parent, job, api.url+'/repos/fixture/alpha/pulls/1')
    rows = {r['kind']:r['body'] for r in store.all('SELECT r.kind,t.body FROM document_state r LEFT JOIN text_bodies t ON t.sha256=r.text_body_sha256')}
    assert rows == {'pr-title':'first', 'pr-body':'sparse body'}


def test_redirect_live_response_refreshes_fence_before_final_request(github_runtime):
    store, repo, git, api = github_runtime
    collector, parent, job, data = prepare(github_runtime, provider_clock=False)
    old_request = collector.http.request
    def request(method, url, **kwargs):
        assert not store.connection.in_transaction
        if '/repos/fixture/alpha/pulls/1' in url:
            return httpx.Response(301, headers={'location':api.url+'/repos/fixture/renamed/pulls/1'}, request=httpx.Request(method,url))
        if url == api.url+'/repos/fixture/renamed':
            return httpx.Response(200, json={'id':101,'full_name':'fixture/renamed'}, request=httpx.Request(method,url), extensions={'catalog_observed_at_us':200})
        if url == api.url+'/repos/fixture/renamed/pulls/1':
            return httpx.Response(200, json={**data, 'body':'after rename', 'updated_at':None}, request=httpx.Request(method,url), extensions={'catalog_observed_at_us':201})
        return old_request(method,url,**kwargs)
    # The initial value has no comparable clock either; only live fencing permits replacement.
    collector.http.request = request
    collector.detail(repo, parent, job, api.url+'/repos/fixture/alpha/pulls/1')
    assert store.one("SELECT t.body FROM eligible_document_state d JOIN text_bodies t ON t.sha256=d.text_body_sha256 WHERE d.kind='pr-body'")[0] == 'after rename'


def test_graphql_foreign_root_id_is_rejected(github_runtime):
    store, repo, git, api = github_runtime
    collector, parent, job, data = prepare(github_runtime)
    api.route = lambda method,path,params,body: ({'data':{'repository':{'pullRequest':{
        'id':'PR_SOME_OTHER_PULL_REQUEST', 'mergeCommit':None,'potentialMergeCommit':None,
        'reviewThreads':{'nodes':[], 'pageInfo':{'hasNextPage':False,'endCursor':None}}}}}}, {})
    with pytest.raises(CatalogError) as failure:
        collector.threads(repo, parent, job)
    assert failure.value.code == 'SCOPE_MISMATCH'


def test_older_code_assessment_cannot_replace_newer_complete(github_runtime):
    store, repo, git, api = github_runtime
    collector = GitHubCollector(store, CancellationToken())
    collector.http.clock_us = lambda: 300
    job = JobService(store).create('sync', {'kind':'pr'})
    store.expected_attempt = 1
    collector.sync(repo,job)
    assessment = store.one("SELECT * FROM code_assessments WHERE state='complete' LIMIT 1")
    assert assessment is not None
    parent = store.one('SELECT * FROM change_requests WHERE change_request_id=?',(assessment['change_request_id'],))
    before = collector._current_pr_value(parent['change_request_id'])
    old = GitHubCollector(store,CancellationToken())
    old.facts.principal = collector.facts.principal
    oldjob = JobService(store).create('sync', {'kind':'pr'})
    oldscope = old.facts.begin(repo,parent['change_request_id'],'pr-detail',oldjob,api.url+'/repos/fixture/alpha/pulls/'+str(parent['provider_change_request_number']))
    old.facts.page(oldscope,175,None,[])
    old.facts.finish(oldscope)
    result = old._assess_code(repo,parent,oldjob,before,before,None,False,[])
    latest = store.one('SELECT state,observed_at_us FROM code_assessments WHERE code_assessment_id=?',(result,))
    assert tuple(latest) == ('complete',300), tuple(latest)
