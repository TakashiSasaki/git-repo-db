"""Fresh reviewer assertions for corrected architecture; uses original own fixtures.
This intentionally inverts original acceptance probes. No implementer fixtures,
no HTTP, no on-disk catalog. Any residual vulnerability is recorded explicitly.
"""
import copy, hashlib, json, sqlite3, sys, uuid
from pathlib import Path
import repo_catalog
from fixtures import fixture, fresh, candidate, probe_current_conflict_deletion
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.json_contracts import validate_catalog
from repo_catalog.adapters.sqlite.schema import DDL_SHA256
from repo_catalog.domain.models import CatalogError


def rejected(fn, expected=CatalogError):
    try: fn()
    except expected as exc: return type(exc).__name__ + ': ' + str(exc)
    raise AssertionError('malformed input accepted')


def no_rows(db, table):
    assert db.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0


def closed_capture():
    results=[]
    for missing in (False,True):
        for extra in ({'raw_api_response':{'data':{'body':'REVIEW_ONLY_RESPONSE'}}},
                      {'api_response_b64':'c3ludGhldGlj'},
                      {'request_context':{'permissions':{'data':{'body':'REVIEW_ONLY_RESPONSE'}}}},
                      {'request_context':{'head':{'sha':'a'*40,'raw_api_response':{}}}}):
            db,ids=fixture(); v=candidate(ids,scope_extra=extra)
            if missing:
                v['change_request_id']=v['acquisition_scope']['change_request_id']=str(uuid.uuid4())
            results.append(rejected(lambda:CurrentApiState(db).admit('change_request_state',v,source='import')))
            no_rows(db,'change_request_state');no_rows(db,'exchange_staging');db.close()
    # The actual visibility/permission/target vocabulary remains usable.
    db,ids=fixture();v=candidate(ids,scope_extra={'visibility':'private','observed_permissions':['read'], 'request_context':{'permissions':['pull'],'head':{'sha':'a'*40},'rest_page_size':100}})
    assert CurrentApiState(db).admit('change_request_state',v,source='import').status=='accepted'
    original=dict(db.execute('SELECT * FROM change_request_state').fetchone())
    bad_scope=json.loads(original['acquisition_scope_json']);bad_scope['opaque_original']={}
    results.append(rejected(lambda:db.execute('UPDATE change_request_state SET acquisition_scope_json=?',(json.dumps(bad_scope),)),sqlite3.IntegrityError))
    evidence=json.loads(original['field_evidence_json']);next(iter(evidence.values()))['acquisition_scope']['request_context']['permissions']={'opaque_original':{}}
    results.append(rejected(lambda:db.execute('UPDATE change_request_state SET field_evidence_json=?',(json.dumps(evidence),)),sqlite3.IntegrityError))
    assert dict(db.execute('SELECT * FROM change_request_state').fetchone())==original
    # Alias is syntactically valid JSON but a second spelling of a field path.
    evidence=json.loads(original['field_evidence_json']);key=next(iter(evidence));alias=key.replace('state','\\u0073tate')
    assert alias!=key; evidence[alias]=evidence[key]
    results.append(rejected(lambda:db.execute('UPDATE change_request_state SET field_evidence_json=?',(json.dumps(evidence),)),sqlite3.IntegrityError))
    assert validate_catalog(db)['records_checked']>0;db.close()
    return {'rejected_variants':len(results),'valid_visibility_permissions_target':'accepted','rejections':results}


def issue_metadata_and_sparse_fields():
    db,ids=fixture();ids={k:v for k,v in ids.items() if k!='change_request_id'}
    v={**ids,'kind':'issue','provider_resource_id':'10','provider_issue_number':1,'body':'current domain body','observed_at_us':100,'parsed_at_us':101,'provider_updated_at_us':10,'provider_clock_scope':'github-issue-updated-at','parser_module':'review.synthetic','parser_version':'1','acquisition_scope':{**ids,'endpoint':'issues/1'},'metadata':{'raw_api_response':{'data':{'body':'REVIEW_ONLY_RESPONSE'}}}}
    rejected(lambda:CurrentResources(db).admit(v,source='import'));no_rows(db,'issue_resources')
    v['metadata']={'milestone':{'title':'first','state':'open','creator':{'login':'synthetic'}}}
    assert CurrentResources(db).admit(v,source='import').status=='accepted'
    sparse=copy.deepcopy(v);sparse.update(provider_updated_at_us=20,observed_at_us=200,parsed_at_us=201);sparse['metadata']={'milestone':{'state':'closed'}}
    assert CurrentResources(db).admit(sparse,source='import').status=='accepted'
    row=db.execute('SELECT metadata,field_evidence_json FROM issue_resources').fetchone()
    metadata=json.loads(row[0]);evidence=json.loads(row[1])
    assert metadata['milestone']=={'title':'first','state':'closed','creator':{'login':'synthetic'}}
    assert evidence['["metadata","milestone","title"]']['provider_updated_at_us']==10
    assert evidence['["metadata","milestone","state"]']['provider_updated_at_us']==20
    assert validate_catalog(db)['records_checked']>0;db.close()
    return {'replica_rejected':True,'sparse_nested_inheritance_and_field_origins':'preserved'}


def wire_no_parent_and_valid_sibling():
    db,ids=fixture();CurrentApiState(db).admit('change_request_state',candidate(ids),source='import')
    unit=Graph(db).export(ids['repository_uuidv4']);valid=next(r for r in unit['records'] if r['table']=='change_request_state');bad=copy.deepcopy(valid)
    bad['values']['metadata']=json.dumps({'raw_api_response':{'body':'REVIEW_ONLY_RESPONSE'}})
    only_bad=copy.deepcopy(unit);only_bad['records']=[bad]
    receiver=fresh();outcome=Graph(receiver).receive(only_bad)
    assert outcome['rejected_records']==1;no_rows(receiver,'exchange_staging');no_rows(receiver,'change_request_state');receiver.close()
    mixed=copy.deepcopy(unit);mixed['records'].insert(0,bad);receiver=fresh();outcome=Graph(receiver).receive(mixed)
    assert outcome['rejected_records']==1;assert receiver.execute('SELECT count(*) FROM change_request_state').fetchone()[0]==1
    no_rows(receiver,'exchange_staging');assert validate_catalog(receiver)['records_checked']>0
    db.close();receiver.close();return {'unresolved_replica':'rejected_no_staging','valid_sibling':'admitted','mixed_result':outcome}


def standalone_pending():
    db,ids=fixture();results=[]
    for table,reason in (('not_a_domain_table','missing_dependency'),('change_request_state','missing_dependency'),('change_request_state','current_state:missing_dependency')):
        raw=json.dumps({'entire_api_original':{'data':{'body':'REVIEW_ONLY_RESPONSE'}}})
        results.append(rejected(lambda:db.execute('INSERT INTO exchange_staging VALUES(?,?,?,?,?,?,?)',('nonsense:record',hashlib.sha256(raw.encode()).digest(),table,ids['repository_uuidv4'],str(uuid.uuid4()),raw,reason)),sqlite3.IntegrityError))
    no_rows(db,'exchange_staging');db.close();return {'malformed_unknown_original_envelopes_rejected':len(results)}


def corrected_pending_shape_owner():
    from repo_catalog.adapters.sqlite.json_contracts import validate_record
    variants=[]
    db,ids=fixture();base=candidate(ids)
    variants.append(('minimal',{'kind':'change-request','acquisition_scope':{}}))
    for name in ('repository_uuidv4','repository_binding_id','service_instance_uuidv4','change_request_id','observed_at_us','parsed_at_us','parser_module','parser_version','acquisition_scope'):
        for null in (False,True):
            v=copy.deepcopy(base)
            if null:v[name]=None
            else:v.pop(name)
            variants.append(('minimum-'+name+('-null' if null else '-omitted'),v))
    for name in ('repository_uuidv4','repository_binding_id','service_instance_uuidv4','change_request_id'):
        v=copy.deepcopy(base);v['acquisition_scope'][name]=str(uuid.uuid4());variants.append(('wrong-capture-'+name,v))
    for timestamp in (True,1<<63,-(1<<63)-1):
        v=copy.deepcopy(base);v['observed_at_us']=timestamp;variants.append(('invalid-timestamp-'+str(timestamp),v))
    results=[]
    for name,v in variants:
        raw=json.dumps(v);row={'record_key':'current-state:'+'a'*64,'content_sha256':hashlib.sha256(raw.encode()).digest(),'table_name':'change_request_state','repository_uuidv4':ids['repository_uuidv4'],'origin_catalog_uuidv4':str(uuid.uuid4()),'record_json':raw,'reason':'current_state:missing_dependency'}
        python_error=rejected(lambda:validate_record(db,'exchange_staging',row))
        sql_error=rejected(lambda:db.execute('INSERT INTO exchange_staging VALUES(?,?,?,?,?,?,?)',tuple(row.values())),sqlite3.IntegrityError)
        results.append({'case':name,'python':python_error,'SQL':sql_error})
    no_rows(db,'exchange_staging');assert validate_catalog(db)['records_checked']>0
    assert Graph(db).export(ids['repository_uuidv4'])['records'];db.close()
    # A genuine unavailable parent remains deferrable and later promotes.
    db,ids=fixture();v=candidate(ids);new_parent=str(uuid.uuid4());v['change_request_id']=v['acquisition_scope']['change_request_id']=new_parent
    assert CurrentApiState(db).admit('change_request_state',v,source='import').status=='missing_dependency'
    assert db.execute('SELECT count(*) FROM exchange_staging').fetchone()[0]==1
    assert validate_catalog(db)['records_checked']>0
    db.execute("INSERT INTO change_requests VALUES(?,?,?,'pull_request',2)",(new_parent,ids['repository_uuidv4'],ids['repository_binding_id']))
    assert CurrentApiState(db)._promote_staging()==1
    no_rows(db,'exchange_staging');assert db.execute('SELECT count(*) FROM eligible_change_request_state').fetchone()[0]==1
    assert validate_catalog(db)['records_checked']>0;db.close()
    return {'rejected_variants':len(results),'results':results,'genuine_missing_parent':'retained_then_promoted_without_fake_owner','export':'remains_usable'}


def source_owner_members():
    out=[]
    for case in ('wrong-source','wrong-service','foreign-pair','not-uuid','object-original','duplicate','nonterminal','integer-terminal'):
        db,ids=fixture();reg={name:str(uuid.uuid4()) for name in ('a','b')}
        for name in reg:db.execute("INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES(?,?,?,'github_inventory',?,'{}')",(name,reg[name],ids['service_instance_uuidv4'],name))
        db.execute('INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES(?,?)',('b' if case=='foreign-pair' else 'a',ids['repository_uuidv4']))
        scope={'source_registration_uuidv4':reg['b' if case=='wrong-source' else 'a'],'service_instance_uuidv4':str(uuid.uuid4()) if case=='wrong-service' else ids['service_instance_uuidv4'],'endpoint':'inventory'}
        members=[ids['repository_uuidv4']]
        if case=='not-uuid':members=['not-a-repository']
        if case=='object-original':members=[{'raw_api_response':{'body':'REVIEW_ONLY_RESPONSE'}}]
        if case=='duplicate':members*=2
        terminal=False if case=='nonterminal' else 1 if case=='integer-terminal' else True
        out.append(rejected(lambda:CurrentApiState(db).assess_source_inventory('a',scope=scope,observed_at_us=100,state='complete',members=members,terminal=terminal,parser_module='review.synthetic',parser_version='1')))
        if case!='integer-terminal':out.append(rejected(lambda:db.execute('INSERT INTO source_inventory_assessments VALUES(?,?,?,?,?,?,?,?,?,?)',('a','synthetic',json.dumps(scope),100,'complete',int(terminal),json.dumps(members),'review.synthetic','1',None)),sqlite3.IntegrityError))
        no_rows(db,'source_inventory_assessments');assert db.execute('SELECT count(*) FROM source_repositories').fetchone()[0]==1;db.close()
    db,ids=fixture();registration=str(uuid.uuid4());db.execute("INSERT INTO sources(source_id,source_registration_uuidv4,service_instance_uuidv4,discovery_kind,name,settings) VALUES('a',?,?,'github_inventory','a','{}')",(registration,ids['service_instance_uuidv4']))
    db.execute("INSERT INTO source_repositories(source_id,repository_uuidv4) VALUES('a',?)",(ids['repository_uuidv4'],))
    kw=dict(scope={'source_registration_uuidv4':registration,'service_instance_uuidv4':ids['service_instance_uuidv4'],'endpoint':'inventory'},parser_module='review.synthetic',parser_version='1')
    CurrentApiState(db).assess_source_inventory('a',observed_at_us=100,state='complete',members=[ids['repository_uuidv4']],terminal=True,**kw)
    CurrentApiState(db).assess_source_inventory('a',observed_at_us=200,state='partial',members=[],terminal=False,**kw)
    assert db.execute('SELECT count(*) FROM source_repositories').fetchone()[0]==1
    assert validate_catalog(db)['records_checked']>0;db.close();return {'rejections':len(out),'valid_assessment':'accepted','partial_scan':'prior_positive_pair_retained'}


def cross_domain_and_marker_mirror():
    db,ids=fixture();collection=str(uuid.uuid4());scope={k:v for k,v in ids.items() if k!='change_request_id'};scope['endpoint']='issues'
    db.execute("INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,kind,scope_json) VALUES(?,?,'issues',?)",(collection,ids['repository_uuidv4'],json.dumps(scope)))
    proof=CurrentCollectionProof(db);proof.page(collection,0,100,None,[],parser_module='review.synthetic',parser_version='1');marker=str(uuid.uuid4())
    db.execute("INSERT INTO completion_markers(completion_marker_uuidv4,fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,?,'complete',?,100)",(marker,collection,json.dumps(proof.evidence(collection))))
    db.execute("INSERT INTO coverage_scopes(coverage_scope_id,repository_uuidv4,kind) VALUES('git-scope',?,'git')",(ids['repository_uuidv4'],))
    db.execute("INSERT INTO coverage_claims(coverage_scope_id,coverage_state,observed_at_us,details_json) VALUES('git-scope','complete',100,?)",(json.dumps({'completion_marker_uuidv4s':[marker]}),))
    claim=dict(db.execute('SELECT * FROM coverage_claims').fetchone());assert db.execute('SELECT count(*) FROM coverage_claim_markers').fetchone()[0]==1
    assert Graph(db).proof_requirements('coverage_claims',claim) is None
    unit=Graph(db).export(ids['repository_uuidv4']);receiver=fresh();outcome=Graph(receiver).receive(unit)
    assert receiver.execute("SELECT count(*) FROM current_coverage WHERE kind='git' AND coverage_state='complete'").fetchone()[0]==0
    unrelated=str(uuid.uuid4());rejected(lambda:db.execute('INSERT INTO coverage_claim_markers VALUES(?,?)',(claim['coverage_claim_id'],unrelated)),sqlite3.IntegrityError)
    db.close();receiver.close();return {'wrong_domain':'not_qualified','mirror_present':'does_not_qualify','receiver':outcome}


def thread_roster():
    results=[]
    for populated in (False,True):
        db,ids=fixture();members=[]
        if populated:
            v=candidate(ids);v.update(kind='review-thread',provider_resource_id='thread-1',provider_updated_at_us=None,provider_clock_scope=None,resolved=False);v.pop('state');assert CurrentApiState(db).admit('review_thread_state',v,source='import').status=='accepted'
            members=[{'family':'thread','change_request_id':ids['change_request_id'],'provider_resource_id':'thread-1','state_digest':'a'*64}]
        collection=str(uuid.uuid4());db.execute("INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,scope_json) VALUES(?,?,?,'threads',?)",(collection,ids['repository_uuidv4'],ids['change_request_id'],json.dumps({**ids,'endpoint':'threads'})))
        proof=CurrentCollectionProof(db);proof.page(collection,0,100,None,members,parser_module='review.synthetic',parser_version='1')
        evidence={**proof.evidence(collection),'kind':'current-resource-tree-v1','fetch_collection_ids':[]};marker={'fetch_collection_id':collection,'asserted_state':'complete','evidence':json.dumps(evidence),'observed_at_us':100}
        assert proof.is_complete_marker(marker)==(not populated)
        if populated:
            assert Graph(db).proof_requirements('completion_markers',marker) is None
            rejected(lambda:db.execute("INSERT INTO completion_markers(fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,'complete',?,100)",(collection,json.dumps(evidence))),sqlite3.IntegrityError)
        else:
            db.execute("INSERT INTO completion_markers(fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,'complete',?,100)",(collection,json.dumps(evidence)))
            stored=dict(db.execute('SELECT * FROM completion_markers').fetchone());assert Graph(db).proof_requirements('completion_markers',stored) is not None
        results.append({'threads':len(members),'omitted_reply_obligation':'rejected' if populated else 'legitimate_empty_tree_accepted'});db.close()
    return results


def main():
    output={'source':repo_catalog.__file__,'python':sys.version,'sqlite':sqlite3.sqlite_version,'DDL':DDL_SHA256.hex(),'binding':'fafc1b2d4d2e1986768143cc71a0e55cba943ba3'}
    failed=False
    for fn in (closed_capture,issue_metadata_and_sparse_fields,wire_no_parent_and_valid_sibling,standalone_pending,source_owner_members,cross_domain_and_marker_mirror,thread_roster,probe_current_conflict_deletion,corrected_pending_shape_owner):
        try:output[fn.__name__]=fn();print(fn.__name__,'completed',flush=True)
        except Exception as exc:output[fn.__name__]={'FAIL':type(exc).__name__,'message':str(exc)};failed=True;print(fn.__name__,'FAIL',repr(exc),flush=True)
    Path(__file__).with_name('rejection-results.json').write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2));raise SystemExit(1 if failed else 0)
if __name__=='__main__':main()
