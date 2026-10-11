"""Fresh scope-4 counterexamples, preserved outside the author checkout."""
import base64
import copy
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

import pytest
import repo_catalog
from repo_catalog.adapters.git.importer import GitImporter
from repo_catalog.adapters.git.parsing import GitParsing, reparse_git, validate_git_fact
from repo_catalog.adapters.sqlite.cas_integrity import repair_payload, verify_all
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph, canonical
from repo_catalog.adapters.sqlite.index import rebuild
from repo_catalog.adapters.sqlite.json_contracts import validate_catalog
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.git_query_context import decoded_fact
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.query_service import QueryService
from repo_catalog.application.repository_identity import add_endpoint
from repo_catalog.domain.models import CatalogError, CancellationToken
from tests.support.domain_facts import fresh_domain_db, candidate, repository_uuid, SERVICE, SOURCE, insert, collection
from tests.support.git_fixture import FixtureRepo
from tests.support.github_runtime import github_runtime, sync

ROOT = Path('/workspace/reviews/publication-free-final-verifier')
assert Path(repo_catalog.__file__).is_relative_to(ROOT), repo_catalog.__file__
OWNER = repository_uuid(1)

def init(path):
    MaintenanceService(path).init('catalog-text-v1', 64*1024*1024, 0)
    return path

def oid(fmt, typ, data):
    return hashlib.new(fmt, f'{typ} {len(data)}\0'.encode()+data).digest()

def git_catalog(path, remote):
    init(path)
    store = Store(path)
    with store.transaction():
        store.execute("INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'synthetic','{}')", (OWNER,))
        add_endpoint(store, OWNER, remote.url)
    repo = {'repository_uuidv4':OWNER,'name':'synthetic'}
    job=JobService(store).create('sync', {'kind':'git'})
    acquired=GitImporter(store,CancellationToken()).sync(repo,job)
    JobService(store).update(job,'complete')
    return store, acquired

def receive(store, unit):
    with store.transaction():
        result=Graph(store.connection).receive(unit)
        if result['admitted_records'] or result['received_records']:
            store.advance_local_revision()
    return result

def export(store, owner=OWNER):
    with store.transaction():
        return Graph(store.connection).export(owner)

def test_normal_acquisition_current_drift_reverse_transfer_index_reopen_and_receipt_loss(github_runtime,tmp_path):
    sender,repo,fixture,api=github_runtime
    sync(sender,repo)
    owner=repo['repository_uuidv4']
    row=sender.one("SELECT * FROM document_state WHERE kind='pr-body' LIMIT 1")
    adapter=CurrentApiState(sender.connection)
    original=adapter.candidate_from_row('document_state',row)
    changed={k:v for k,v in original.items() if k not in {'field_evidence','last_checked_at_us'}}
    changed.update(body='scope-four-distinct-current-body',provider_updated_at_us=original['provider_updated_at_us']+1 if original['provider_updated_at_us'] is not None else None,observed_at_us=original['observed_at_us']+1,parsed_at_us=original['parsed_at_us']+1,parser_version='scope-four')
    revision, scope=adapter.capture_context(changed['acquisition_scope'])
    assert adapter.admit('document_state',changed,base_revision=revision,scope_context=scope).status=='accepted'
    for marker in sender.all("SELECT * FROM completion_markers WHERE asserted_state='complete'"):
        assert Graph(sender.connection).proof_requirements('completion_markers',dict(marker)) is not None
    unit=export(sender,owner)
    receiver_path=init(tmp_path/'receiver')
    with Store(receiver_path) as receiver:
        proof_records=[r for r in unit['records'] if r['table'] in {'completion_markers','coverage_claims','current_collection_pages'}]
        prefix={**unit,'records':list(reversed(proof_records))}
        partial=receive(receiver,prefix)
        assert partial['staged_records']>0
        assert not receiver.one("SELECT 1 FROM coverage_claims WHERE coverage_state='complete'")
        receive(receiver,{**unit,'records':list(reversed(unit['records']))})
        assert receiver.one("SELECT count(*) FROM eligible_document_state")[0]>0
        assert not receiver.one("SELECT 1 FROM exchange_staging")
        received=CurrentApiState(receiver.connection).candidate_from_row('document_state',receiver.one("SELECT * FROM document_state WHERE change_request_id=? AND kind=? AND provider_change_request_document_id=?",(row['change_request_id'],row['kind'],row['provider_change_request_document_id'])))
        assert received['body']=='scope-four-distinct-current-body'
        assert received['last_checked_at_us'] is None
        before=receiver.one("SELECT count(*) FROM eligible_document_state")[0]
        with receiver.transaction():
            for table in ('exchange_admissions','exchange_local_identities','thread_collection_continuations','resume_cursors','incremental_scans','acquisition_progress','collection_progress','job_attempts','jobs','resume_scopes'):
                receiver.execute('DELETE FROM '+table)
        assert receiver.one("SELECT count(*) FROM eligible_document_state")[0]==before
        rebuild(receiver,'pr')
        assert not check_catalog(receiver,full=True)
    visible=QueryService(receiver_path).query('search pr',{'literal':'scope-four-distinct-current-body'}).data['items']
    assert visible
    old_matches=QueryService(receiver_path).query('search pr',{'literal':original['body']}).data['items']
    assert not any((item.get('change_request_id'),item.get('kind'),item.get('provider_change_request_document_id'))==(row['change_request_id'],row['kind'],row['provider_change_request_document_id']) for item in old_matches)
    with Store(receiver_path) as receiver:
        onward=export(receiver,owner)
        assert receive(receiver,unit)['staged_records']==0
    third_path=init(tmp_path/'third')
    with Store(third_path) as third:
        assert receive(third,{**onward,'records':list(reversed(onward['records']))})['staged_records']==0
        assert third.one("SELECT count(*) FROM eligible_document_state")[0]==before
        assert not check_catalog(third,full=True)

def test_incomplete_scope_keeps_direct_document_and_independent_transfer():
    db=fresh_domain_db();db.row_factory=sqlite3.Row
    api=CurrentApiState(db)
    body=candidate(kind='pr-body',provider_change_request_document_id='90',body='valid prefix before next page fails')
    assert api.admit('document_state',body,source='import').status=='accepted'
    scope=collection(db,identity='unfinished',kind='pr-body')
    CurrentCollectionProof(db).page('unfinished',0,100,'unvisited-next',[],parser_module='scope4',parser_version='1')
    assert CurrentCollectionProof(db).evidence('unfinished') is None
    assert db.execute('SELECT count(*) FROM eligible_document_state').fetchone()[0]==1
    unit=Graph(db).export(OWNER)
    other=fresh_domain_db();other.row_factory=sqlite3.Row
    result=Graph(other).receive({**unit,'records':list(reversed(unit['records']))})
    assert other.execute('SELECT count(*) FROM eligible_document_state').fetchone()[0]==1
    assert not other.execute("SELECT 1 FROM completion_markers WHERE asserted_state='complete'").fetchone()
    assert validate_catalog(other)['records_checked']>0

def test_current_sparse_explicit_null_negative_clock_fences_and_receiver_local_check():
    db=fresh_domain_db();db.row_factory=sqlite3.Row;api=CurrentApiState(db)
    a=candidate(kind='pr-body',clock=-10,observed_at_us=-8,provider_change_request_document_id='91',body='preserved',author='A')
    assert api.admit('document_state',a,source='import').status=='accepted'
    b=candidate(kind='pr-body',clock=0,observed_at_us=0,parser_version='2',provider_change_request_document_id='91',author=None)
    assert api.admit('document_state',b,source='import').status=='accepted'
    merged=api.candidate_from_row('document_state',db.execute('SELECT * FROM document_state').fetchone())
    assert merged['body']=='preserved' and merged['author'] is None
    assert merged['field_evidence']['["body"]']['provider_updated_at_us']==-10
    c=candidate(kind='pr-body',clock=-10,observed_at_us=500,provider_change_request_document_id='91',body='equal-clock-divergence')
    assert api.admit('document_state',c,source='import').status=='conflict'
    assert not db.execute('SELECT 1 FROM eligible_document_state').fetchone()
    c.update(provider_updated_at_us=1)
    rev,scope=api.capture_context(c['acquisition_scope'])
    db.execute('UPDATE database_identity SET local_revision=local_revision+1')
    assert api.admit('document_state',c,base_revision=rev,scope_context=scope).status=='accepted'
    merged=api.candidate_from_row('document_state',db.execute('SELECT * FROM document_state').fetchone())
    assert merged['last_checked_at_us'] is None
    thread=candidate(kind='review-thread',resource='x',provider_resource_id='thread',resolved=False)
    thread.pop('resource');api.admit('review_thread_state',thread,source='import')
    rev,scope=api.capture_context(thread['acquisition_scope']);thread['resolved']=True
    db.execute('UPDATE database_identity SET local_revision=local_revision+1')
    assert api.admit('review_thread_state',thread,base_revision=rev,scope_context=scope).status=='conflict'

def test_source_partial_assessment_and_operational_state_loss_do_not_delete_positive_pairs():
    db=fresh_domain_db();db.row_factory=sqlite3.Row;api=CurrentApiState(db)
    scope={'source_registration_uuidv4':SOURCE,'service_instance_uuidv4':SERVICE,'endpoint':'synthetic-inventory'}
    for n in (1,2):
        assert api.confirm_source_repository('source',repository_uuid(n),observed_at_us=100,scope=scope,parser_module='scope4',parser_version='1',name=str(n),source='import')=='accepted'
    api.assess_source_inventory('source',scope=scope,observed_at_us=200,state='partial',members=[OWNER],terminal=False,reason='network',parser_module='scope4',parser_version='2')
    assert db.execute('SELECT count(*) FROM source_repositories').fetchone()[0]==2
    assert validate_catalog(db)['records_checked']>0
    for table in ('exchange_admissions','exchange_local_identities','resume_scopes','jobs'):
        db.execute('DELETE FROM '+table)
    assert db.execute('SELECT count(*) FROM eligible_source_repositories').fetchone()[0]==2

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_real_git_capture_decoder_ambiguity_invalid_first_exchange_and_reopen(tmp_path,fmt):
    remote=FixtureRepo(tmp_path/'remote.git',fmt)
    remote.commit('A',{b'decoded.txt':b'caf\xe9'});remote.ref('refs/heads/main','A')
    sender,acquired=git_catalog(tmp_path/'sender',remote)
    with sender:
        reparse_git(sender,acquired['git_acquisition_id'],text_encoding='latin-1')
        blob=sender.one("SELECT git_object_id FROM git_objects WHERE type='blob'")[0]
        assert decoded_fact(sender,blob,'blob')['decoder_conflict']
        unit=export(sender)
        facts=[r for r in unit['records'] if r['table']=='git_text_facts']
        forged=copy.deepcopy(facts[0]);forged['values']['text_state']='eligible';forged['values']['raw_text']='invented-not-the-canonical-bytes'
        receiver_path=init(tmp_path/'receiver')
        with Store(receiver_path) as receiver:
            first=receive(receiver,{**unit,'records':[forged]})
            assert first['staged_records']==1
            outcome=receive(receiver,{**unit,'records':list(reversed(unit['records']))})
            assert outcome['staged_records']==0
            assert not receiver.one("SELECT 1 FROM git_text_facts WHERE raw_text='invented-not-the-canonical-bytes'")
            recv_blob=receiver.one("SELECT git_object_id FROM git_objects WHERE type='blob'")[0]
            decoded=decoded_fact(receiver,recv_blob,'blob')
            assert decoded['decoder_conflict'] and len(decoded['candidates'])==2
            assert receiver.one('SELECT count(*) FROM current_snapshots')[0]==1
            assert not check_catalog(receiver,full=True)
            snapshot=receiver.one('SELECT snapshot_id FROM current_snapshots')[0]
            onward=export(receiver)
        with Store(receiver_path) as receiver:
            assert receiver.one('SELECT snapshot_id FROM current_snapshots')[0]==snapshot
            assert decoded_fact(receiver,recv_blob,'blob')['decoder_conflict']
            assert receive(receiver,onward)['staged_records']==0

def test_ref_capture_type_and_peeled_tuple_cannot_gain_current_scope_from_real_object_bytes(tmp_path):
    remote=FixtureRepo(tmp_path/'remote.git')
    remote.commit('A',{b'a.txt':b'actual bytes'});remote.ref('refs/heads/main','A')
    sender,_=git_catalog(tmp_path/'sender',remote)
    with sender:unit=export(sender)
    for attack in ('type','peeled','missing'):
        damaged=copy.deepcopy(unit)
        ref=next(r for r in damaged['records'] if r['table']=='ref_observations')
        if attack=='type':ref['values']['target_type']='tree'
        elif attack=='peeled':ref['values']['peeled_oid']={'$bytes':base64.b64encode(b'q'*20).decode()}
        else:damaged['records'].remove(ref)
        with Store(init(tmp_path/attack)) as receiver:
            result=receive(receiver,{**damaged,'records':list(reversed(damaged['records']))})
            assert result['staged_records']>0
            assert receiver.one('SELECT count(*) FROM available_git_objects')[0]==3
            assert not receiver.one('SELECT 1 FROM current_snapshots')
            if attack=='missing':
                actual=next(r for r in unit['records'] if r['table']=='ref_observations')
                late=receive(receiver,{**unit,'records':[actual]})
                assert late['staged_records']==0,[dict(r) for r in receiver.all('SELECT table_name,reason,record_json FROM exchange_staging')]
                assert receiver.one('SELECT count(*) FROM current_snapshots')[0]==1

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_intrinsic_partial_tree_missing_target_and_atomic_failure(tmp_path,fmt,monkeypatch):
    path=init(tmp_path/'state')
    with Store(path) as store:
        parser=GitParsing(store);child=oid(fmt,'blob',b'missing')
        raw=b''.join(b'100644 '+name+b'\0'+child for name in (b'a',b'b'))
        original=parser.write;written=0
        def fail(sql,values):
            nonlocal written
            if sql.startswith('INSERT INTO tree_entries'):
                written+=1
                if written==2:raise CatalogError('CANCELLED','scope4 injected interruption')
            return original(sql,values)
        monkeypatch.setattr(parser,'write',fail)
        with pytest.raises(CatalogError):parser.install_object(fmt,oid(fmt,'tree',raw),'tree',raw)
        assert store.one('SELECT count(*) FROM git_objects')[0]==0
        monkeypatch.setattr(parser,'write',original)
        tree=parser.install_object(fmt,oid(fmt,'tree',raw),'tree',raw)
        assert store.one('SELECT count(*) FROM available_git_objects')[0]==1
        assert store.one('SELECT count(*) FROM tree_entries WHERE child_git_object_id IS NULL')[0]==2
        with pytest.raises(CatalogError):parser.manifest(tree)
        assert store.one('SELECT count(*) FROM git_objects')[0]==1

def test_shared_git_physical_digest_quarantine_repair_backup_restore_and_no_overwrite(tmp_path):
    path=init(tmp_path/'state');raw=b'shared bytes for two canonical formats'
    with Store(path) as store:
        for fmt in ('sha1','sha256'):
            GitParsing(store).install_object(fmt,oid(fmt,'blob',raw),'blob',raw)
        digest=hashlib.sha256(raw).digest()
        assert store.one('SELECT count(*) FROM stored_bytes')[0]==1
        trigger=store.one("SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'")[0]
        with store.transaction():
            store.execute('DROP TRIGGER stored_bytes_immutable')
            store.execute('UPDATE stored_bytes SET body=? WHERE sha256=?',(b'x'*len(raw),digest))
            store.execute(trigger)
        assert store.one('SELECT count(*) FROM available_git_objects')[0]==0
        report=verify_all(store.connection)
        assert len(report['corrupt'])==1
        backup=tmp_path/'quarantine.sqlite3'
        MaintenanceService(path).backup(store,backup)
        manifest_path=backup.with_name(backup.name+'.manifest.json')
        manifest=json.loads(manifest_path.read_text());assert manifest['quarantined_payload_count']==1
        wrong=copy.deepcopy(manifest);wrong['quarantined_payload_count']=0;manifest_path.write_text(json.dumps(wrong))
        rejected=tmp_path/'wrong-count'
        with pytest.raises(CatalogError,match='quarantine count'):MaintenanceService(rejected).restore(backup)
        assert not rejected.exists()
        manifest_path.write_text(json.dumps(manifest))
        restored=tmp_path/'restored';MaintenanceService(restored).restore(backup)
        with Store(restored) as other:
            assert other.one('SELECT count(*) FROM payload_quarantine')[0]==1
            repair_payload(other.connection,digest,raw)
            assert other.one('SELECT count(*) FROM available_git_objects')[0]==2
            assert not check_catalog(other,full=True)
        with pytest.raises(CatalogError,match='must not exist'):MaintenanceService(restored).restore(backup)
        repair_payload(store.connection,digest,raw)
        assert store.one('SELECT count(*) FROM available_git_objects')[0]==2

def test_sql_decoder_value_must_not_become_ordinary_fact_without_byte_validation(tmp_path):
    path=init(tmp_path/'state');raw=b'canonical real text'
    with Store(path) as store:
        parser=GitParsing(store);obj=parser.install_object('sha1',oid('sha1','blob',raw),'blob',raw,decode=False)
        settings={**parser.decoder,'parser_module':'scope4.independent','parser_version':'unranked'}
        key=hashlib.sha256(json.dumps(settings,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        row={'git_fact_uuidv4':str(uuid.uuid4()),'git_object_id':obj,'content_id':store.one('SELECT content_id FROM blob_content_map')[0],'decoder_key':key,**settings,'text_state':'eligible','raw_text':'fabricated-decoded-content'}
        try:
            store.execute('INSERT INTO git_text_facts('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
        except (CatalogError,sqlite3.IntegrityError):
            return
        with pytest.raises(CatalogError):validate_git_fact(store.connection,'git_text_facts',row)
        accepted=decoded_fact(store,obj,'blob',decoder_key=key)
        assert accepted['fact'] is None, 'ordinary decoded_fact trusts a false value that validate_git_fact rejects'

def test_coverage_clock_candidate_set_partial_stale_unknown_conflict_and_recovery():
    from repo_catalog.adapters.sqlite.coverage import admit_claim
    db=fresh_domain_db();db.row_factory=sqlite3.Row
    insert(db,'coverage_scopes',coverage_scope_id='scope4-coverage',repository_uuidv4=OWNER,change_request_id='pr1',kind='pr')
    state=lambda:db.execute("SELECT coverage_state,observed_at_us FROM current_coverage WHERE coverage_scope_id='scope4-coverage'").fetchone()
    for stamp,value,expected in [(100,'complete','complete'),(200,'partial','partial'),(175,'complete','partial'),(300,'complete','complete'),(300,'unknown','complete'),(300,'partial','conflict'),(400,'unknown','unknown')]:
        admit_claim(db,'scope4-coverage',value,stamp)
        assert tuple(state())==(expected,max(100,stamp,200 if stamp==175 else stamp))
    assert db.execute('SELECT count(*) FROM coverage_claims WHERE observed_at_us=175').fetchone()[0]==0

def test_outer_commit_failure_rolls_back_resource_evidence_text_and_revision(tmp_path,monkeypatch):
    path=init(tmp_path/'state')
    with Store(path) as store:
        from tests.support.domain_facts import seed_owners
        with store.transaction():seed_owners(store.connection)
        before=store.revision();original=store.execute
        def fail(sql,args=()):
            if sql=='COMMIT':raise sqlite3.OperationalError('scope4 COMMIT failure')
            return original(sql,args)
        monkeypatch.setattr(store,'execute',fail)
        with pytest.raises(sqlite3.OperationalError,match='COMMIT failure'):
            with store.transaction():
                api=CurrentApiState(store)
                api.admit('document_state',candidate(kind='pr-body',provider_change_request_document_id='92',body='never commit'),source='import')
                store.advance_local_revision()
        assert store.revision()==before
        for table in ('document_state','documents','text_bodies','exchange_staging'):
            assert store.one('SELECT count(*) FROM '+table)[0]==0
        assert not store.connection.in_transaction

def test_issue_transfer_detached_capture_reverse_import_onward_and_late_old_membership():
    db=fresh_domain_db();db.row_factory=sqlite3.Row;adapter=CurrentResources(db)
    insert(db,'source_repositories',source_id='source',repository_uuidv4=OWNER,first_seen_us=100,last_seen_us=100)
    scope={'repository_uuidv4':OWNER,'repository_binding_id':'binding-1','service_instance_uuidv4':SERVICE,'source_registration_uuidv4':SOURCE,'endpoint':'synthetic-original-Issue'}
    parent={'kind':'issue','service_instance_uuidv4':SERVICE,'provider_resource_id':'310','repository_uuidv4':OWNER,'repository_binding_id':'binding-1','provider_issue_number':3,'title':'ordinary','body':'parent','state':'open','provider_updated_at_us':100,'provider_clock_scope':'github-issue-updated-at','observed_at_us':100,'parsed_at_us':101,'parser_module':'scope4','parser_version':'1','acquisition_scope':scope}
    child={**parent,'kind':'issue-comment','provider_resource_id':'311','parent_provider_resource_id':'310','title':None,'state':None,'body':'captured in A','provider_clock_scope':'github-issue-comment-updated-at'}
    assert adapter.admit(parent,source='import').status=='accepted'
    assert adapter.admit(child,source='import').status=='accepted'
    before=adapter.candidate_from_row('issue_resources',db.execute("SELECT * FROM issue_resources WHERE kind='issue-comment'").fetchone())
    target=repository_uuid(2)
    moved={**parent,'repository_uuidv4':target,'repository_binding_id':'binding-2','provider_issue_number':7,'provider_updated_at_us':200,'observed_at_us':200,'parsed_at_us':201,'acquisition_scope':{**scope,'repository_uuidv4':target,'repository_binding_id':'binding-2','source_registration_uuidv4':None}}
    moved['acquisition_scope'].pop('source_registration_uuidv4')
    assert adapter.admit(moved,source='import').status=='accepted'
    after=adapter.candidate_from_row('issue_resources',db.execute("SELECT * FROM issue_resources WHERE kind='issue-comment'").fetchone())
    assert after['repository_uuidv4']==target and after['acquisition_scope']==before['acquisition_scope']
    unit=Graph(db).export(target)
    assert sum(r['table']=='repositories' for r in unit['records'])==1
    other=sqlite3.connect(':memory:',isolation_level=None);other.row_factory=sqlite3.Row
    from repo_catalog.adapters.sqlite.schema import schema_sql,DDL_SHA256,SCHEMA_VERSION
    from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
    register_git_object_sql_function(other);other.executescript(schema_sql())
    other.execute("INSERT INTO database_identity VALUES(1,'repo-catalog/catalog3',?,?,0,?,'validated')",(SCHEMA_VERSION,str(uuid.uuid4()),DDL_SHA256))
    assert Graph(other).receive({**unit,'records':list(reversed(unit['records']))})['staged_records']==0
    assert not other.execute('SELECT 1 FROM repositories WHERE repository_uuidv4=?',(OWNER,)).fetchone()
    assert not other.execute('SELECT 1 FROM sources WHERE source_registration_uuidv4=?',(SOURCE,)).fetchone()
    transferred=CurrentResources(other).candidate_from_row('issue_resources',other.execute("SELECT * FROM issue_resources WHERE kind='issue-comment'").fetchone())
    assert transferred['repository_uuidv4']==target and transferred['acquisition_scope']==scope
    assert Graph(other).receive(unit)['staged_records']==0
    assert validate_catalog(other)['records_checked']>0
    onward=Graph(other).export(target)
    assert sum(r['table']=='repositories' for r in onward['records'])==1

