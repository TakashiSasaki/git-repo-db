"""Independent Architecture/DDL probes against the frozen Schema 20 source.

No production fixtures imported. Memory-only catalogs, no HTTP or retained data.
Run with the exact worktree PYTHONPATH and shared interpreter described in report.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import sys
import uuid
from pathlib import Path

import repo_catalog
from repo_catalog.adapters.sqlite.cas_integrity import register_git_object_sql_function
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import validate_catalog, validate_record
from repo_catalog.adapters.sqlite.schema import DDL_SHA256, FORMAT_ID, SCHEMA_VERSION, schema_sql


def fresh():
    db = sqlite3.connect(':memory:', autocommit=True)
    db.row_factory = sqlite3.Row
    register_git_object_sql_function(db)
    db.executescript(schema_sql())
    db.execute("INSERT INTO database_identity VALUES(1,?,?,?,?,?,'validated')", (FORMAT_ID,SCHEMA_VERSION,str(uuid.uuid4()),0,DDL_SHA256))
    return db


def fixture():
    db = fresh()
    ids = {key:str(uuid.uuid4()) for key in ('repository_uuidv4','repository_binding_id','service_instance_uuidv4','change_request_id')}
    db.execute("INSERT INTO service_instances(service_instance_uuidv4,service_kind,name,metadata) VALUES(?,'github','synthetic','{}')", (ids['service_instance_uuidv4'],))
    db.execute("INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'synthetic','{}')", (ids['repository_uuidv4'],))
    db.execute("INSERT INTO repository_bindings(repository_binding_id,repository_uuidv4,service_instance_uuidv4,metadata) VALUES(?,?,?,'{}')", (ids['repository_binding_id'],ids['repository_uuidv4'],ids['service_instance_uuidv4']))
    db.execute("INSERT INTO change_requests VALUES(?,?,?,'pull_request',1)", (ids['change_request_id'],ids['repository_uuidv4'],ids['repository_binding_id']))
    return db, ids


def candidate(ids, *, clock=10, state='open', scope_extra=None):
    return {**ids,'kind':'change-request','provider_resource_id':'12','state':state,'observed_at_us':100,'parsed_at_us':101,'parser_module':'review.synthetic','parser_version':'1','provider_updated_at_us':clock,'provider_clock_scope':'github-pr-updated-at','acquisition_scope':{**ids,'endpoint':'pulls/1', **(scope_extra or {})}}


def probe_scope_replica():
    db, ids = fixture()
    secret_marker = 'REVIEW_ONLY_SYNTHETIC_RESPONSE'
    replica = {'raw_api_response':{'data':{'pullRequest':{'body':secret_marker,'title':'superseded'}}},'api_response_b64':'eyJib2R5IjoiUlZfUkVQTElDQSJ9'}
    api = CurrentApiState(db)
    result = api.admit('change_request_state', candidate(ids,scope_extra=replica), source='import')
    assert result.status == 'accepted'
    row = db.execute('SELECT * FROM change_request_state').fetchone()
    assert json.loads(row['acquisition_scope_json'])['raw_api_response']==replica['raw_api_response']
    assert validate_catalog(db)['records_checked'] > 0
    unit = Graph(db).export(ids['repository_uuidv4'])
    assert secret_marker in json.dumps(unit)
    receiver = fresh()
    received = Graph(receiver).receive(unit)
    restored = receiver.execute('SELECT acquisition_scope_json,field_evidence_json FROM change_request_state').fetchone()
    assert restored and secret_marker in restored['acquisition_scope_json'] and secret_marker in restored['field_evidence_json']
    result_data={'admission':result.status,'catalog_validation':'passed','export_contains_replica':True,'receiver':received,'receiver_field_evidence_contains_replica':True}
    db.close(); receiver.close()
    return result_data


def probe_issue_metadata_replica():
    from repo_catalog.adapters.sqlite.current_resources import CurrentResources
    db,ids=fixture()
    issue_ids={k:v for k,v in ids.items() if k!='change_request_id'}
    value={**issue_ids,'kind':'issue','provider_resource_id':'10','provider_issue_number':1,'body':'current domain text','observed_at_us':100,'parsed_at_us':101,'provider_updated_at_us':10,'provider_clock_scope':'github-issue-updated-at','parser_module':'review.synthetic','parser_version':'1','acquisition_scope':{**issue_ids,'endpoint':'issues/1'},'metadata':{'raw_api_response':{'data':{'body':'REVIEW_ONLY_ISSUE_METADATA_RESPONSE'}}}}
    assert CurrentResources(db).admit(value,source='import').status=='accepted'
    assert validate_catalog(db)['records_checked']>0
    unit=Graph(db).export(ids['repository_uuidv4'])
    assert 'REVIEW_ONLY_ISSUE_METADATA_RESPONSE' in json.dumps(unit)
    db.close()
    return {'opaque_Issue_metadata':'accepted','catalog_validation':'passed','export_contains_replica':True}


def probe_pending_replica():
    db, ids = fixture()
    # Independent natural parent is deliberately unavailable.
    ids['change_request_id'] = str(uuid.uuid4())
    value = candidate(ids,scope_extra={'raw_api_response':{'data':{'body':'REVIEW_ONLY_PENDING_RESPONSE'}}})
    result = CurrentApiState(db).admit('change_request_state', value, source='import')
    assert result.status == 'missing_dependency'
    stored = db.execute('SELECT record_json FROM exchange_staging').fetchone()[0]
    assert 'REVIEW_ONLY_PENDING_RESPONSE' in stored
    assert validate_catalog(db)['records_checked']>0
    db.close()
    return {'admission':result.status,'pending_contains_replica':True,'catalog_validation':'passed'}


def probe_staging_vocab():
    db, ids = fixture()
    raw = json.dumps({'entire_api_original':{'data':{'body':'REVIEW_ONLY_UNMODELED'}}})
    db.execute('INSERT INTO exchange_staging VALUES(?,?,?,?,?,?,?)',('nonsense:record',hashlib.sha256(raw.encode()).digest(),'not_a_domain_table',ids['repository_uuidv4'],str(uuid.uuid4()),raw,'missing_dependency'))
    assert validate_catalog(db)['records_checked']>0
    db.close()
    return {'SQL_insertion':'accepted','catalog_validation':'passed','table_name':'not_a_domain_table'}


def probe_source_assessment_owner_and_members():
    db,ids=fixture(); adapter=CurrentApiState(db)
    registrations={name:str(uuid.uuid4()) for name in ('a','b')}
    for name,registration in registrations.items():
        db.execute("INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES(?,?,?,'github_inventory',?,'{}')", (name,registration,ids['service_instance_uuidv4'],name))
    db.execute("INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES('b',?)", (ids['repository_uuidv4'],))
    adapter.assess_source_inventory('a',scope={'source_registration_uuidv4':registrations['b'],'service_instance_uuidv4':ids['service_instance_uuidv4'],'endpoint':'inventory'},observed_at_us=100,state='complete',members=[ids['repository_uuidv4']],terminal=True,parser_module='review.synthetic',parser_version='1')
    adapter.assess_source_inventory('a',scope={'source_registration_uuidv4':registrations['a'],'service_instance_uuidv4':ids['service_instance_uuidv4'],'endpoint':'inventory'},observed_at_us=200,state='complete',members=['not-a-repository',{'raw_api_response':{'body':'REVIEW_ONLY_INVENTORY_RESPONSE'}}],terminal=True,parser_module='review.synthetic',parser_version='1')
    assert validate_catalog(db)['records_checked']>0
    rows=[dict(r) for r in db.execute("SELECT * FROM source_inventory_assessments WHERE source_id='a' ORDER BY observed_at_us")]
    assert len(rows)==2 and all(r['state']=='complete' for r in rows)
    assert db.execute("SELECT count(*) FROM source_repositories WHERE source_id='a'").fetchone()[0]==0
    db.close()
    return {'foreign_source_scope':'accepted_as_complete','unassociated_member':'accepted_as_complete','nonidentity_and_replica_members':'accepted_as_complete','catalog_validation':'passed','actual_source_a_associations':0}


def probe_cross_domain_coverage_proof():
    from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
    db,ids=fixture()
    collection=str(uuid.uuid4())
    scope={k:v for k,v in ids.items() if k!='change_request_id'}
    scope['endpoint']='issues'
    db.execute("INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,kind,scope_json) VALUES(?,?,'issues',?)",(collection,ids['repository_uuidv4'],json.dumps(scope)))
    proof=CurrentCollectionProof(db)
    proof.page(collection,0,100,None,[],parser_module='review.synthetic',parser_version='1')
    marker=str(uuid.uuid4())
    db.execute("INSERT INTO completion_markers(completion_marker_uuidv4,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,100)",(marker,collection,json.dumps(proof.evidence(collection))))
    db.execute("INSERT INTO coverage_scopes(coverage_scope_id,repository_uuidv4,kind) VALUES('git-scope',?,'git')",(ids['repository_uuidv4'],))
    db.execute("INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES('git-scope','complete',100,?)",(json.dumps({'completion_marker_uuidv4s':[marker]}),))
    graph=Graph(db)
    claim=dict(db.execute('SELECT * FROM coverage_claims').fetchone())
    qualified=graph.proof_requirements('coverage_claims',claim)
    assert qualified is not None
    unit=graph.export(ids['repository_uuidv4'])
    assert any(r['table']=='coverage_claims' for r in unit['records'])
    receiver=fresh(); outcome=Graph(receiver).receive(unit)
    coverage=dict(receiver.execute("SELECT * FROM current_coverage WHERE kind='git'").fetchone())
    assert coverage['coverage_state']=='complete'
    assert receiver.execute('SELECT count(*) FROM git_acquisitions').fetchone()[0]==0
    db.close();receiver.close()
    return {'empty_issues_list_qualifies_git_claim':True,'receiver_git_coverage':coverage['coverage_state'],'receiver_git_acquisitions':0,'receiver':outcome}


def probe_missing_thread_obligation():
    from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
    db,ids=fixture()
    value=candidate(ids)
    value.update(kind='review-thread',provider_resource_id='thread-1',provider_updated_at_us=None,provider_clock_scope=None,resolved=False)
    value.pop('state')
    assert CurrentApiState(db).admit('review_thread_state',value,source='import').status=='accepted'
    collection=str(uuid.uuid4())
    scope={**ids,'endpoint':'threads'}
    db.execute("INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,scope_json) VALUES(?,?,?,'threads',?)",(collection,ids['repository_uuidv4'],ids['change_request_id'],json.dumps(scope)))
    proof=CurrentCollectionProof(db)
    proof.page(collection,0,100,None,[{'family':'thread','change_request_id':ids['change_request_id'],'provider_resource_id':'thread-1','state_digest':'a'*64}],parser_module='review.synthetic',parser_version='1')
    evidence={**proof.evidence(collection),'kind':'current-resource-tree-v1','fetch_collection_ids':[]}
    db.execute("INSERT INTO completion_markers(fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,'complete',?,100)",(collection,json.dumps(evidence)))
    marker=dict(db.execute('SELECT * FROM completion_markers').fetchone())
    assert proof.is_complete_marker(marker)
    assert Graph(db).proof_requirements('completion_markers',marker) is not None
    unit=Graph(db).export(ids['repository_uuidv4'])
    receiver=fresh();outcome=Graph(receiver).receive(unit)
    assert receiver.execute('SELECT count(*) FROM completion_markers').fetchone()[0]==1
    assert receiver.execute('SELECT count(*) FROM thread_collection_requirements').fetchone()[0]==0
    db.close();receiver.close()
    return {'thread_roster_members':1,'required_reply_child_records':0,'complete_tree_proof':'accepted_and_exported','receiver':outcome}


def probe_current_conflict_deletion():
    db,ids=fixture(); api=CurrentApiState(db)
    assert api.admit('change_request_state',candidate(ids),source='import').status=='accepted'
    assert api.admit('change_request_state',candidate(ids,state='closed'),source='import').status=='conflict'
    blocked=db.execute('SELECT count(*) FROM eligible_change_request_state').fetchone()[0]
    assert blocked==0
    db.execute('DELETE FROM exchange_admissions')
    unchanged=db.execute('SELECT count(*) FROM eligible_change_request_state').fetchone()[0]
    db.execute('DELETE FROM exchange_local_identities')
    unchanged2=db.execute('SELECT count(*) FROM eligible_change_request_state').fetchone()[0]
    assert unchanged==unchanged2==0
    # These are domain conflict candidates, unlike the discardable indexes.
    db.close()
    return {'conflict':'blocked','after_operational_receipt_deletion':'still_blocked'}


def main():
    result={'source':repo_catalog.__file__,'python':sys.version,'sqlite':sqlite3.sqlite_version,'DDL_sha256':DDL_SHA256.hex()}
    for func in (probe_scope_replica,probe_issue_metadata_replica,probe_pending_replica,probe_staging_vocab,probe_source_assessment_owner_and_members,probe_cross_domain_coverage_proof,probe_missing_thread_obligation,probe_current_conflict_deletion):
        try:
            result[func.__name__]=func()
        except Exception as exc:
            result[func.__name__]={'exception':type(exc).__name__,'message':str(exc)}
    output=Path('/workspace/review-artifacts/architecture/counterexamples-results.json')
    output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
