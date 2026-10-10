"""Additional independent composed-boundary checks after integrated corrections."""
import copy,hashlib,json,sqlite3,uuid
from pathlib import Path
from fixtures import fixture
from repo_catalog.adapters.git.parsing import install_git_object
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof


def computed_git_and_nul_guard():
    results=[]
    for fmt in ('sha1','sha256'):
        db,ids=fixture();width=20 if fmt=='sha1' else 32;child=b'\x22'*width
        valid=b'100644 first\0'+child+b'100644 second\0'+child
        invalid=b'100644 duplicate\0'+child+b'100644 duplicate\0'+child
        assert db.execute('SELECT repo_catalog_git_tree_shape_valid(?,?)',(fmt,valid)).fetchone()[0]==1
        assert db.execute('SELECT repo_catalog_git_tree_shape_valid(?,?)',(fmt,invalid)).fetchone()[0]==0
        oid=hashlib.new(fmt,f'tree {len(valid)}\0'.encode()+valid).digest();tree=install_git_object(db,fmt,oid,'tree',valid)
        before=db.execute('SELECT count(*) FROM available_git_objects').fetchone()[0]
        try:db.execute('INSERT INTO tree_entries VALUES(?,?,?,?,?,?,?,?)',(tree,b'fabricated\0merged',1000,100,33188,fmt,child,None))
        except sqlite3.IntegrityError as exc:assert 'instr(raw_name' in str(exc);nul_rejected=str(exc)
        else:raise AssertionError('NUL-bearing intrinsic name accepted')
        assert db.execute('SELECT count(*) FROM tree_entries').fetchone()[0]==2
        db.execute('DELETE FROM exchange_admissions');db.execute('DELETE FROM exchange_local_identities')
        assert db.execute('SELECT count(*) FROM available_git_objects').fetchone()[0]==before==1
        for algorithm in ('md5','sha1','sha256'):
            digest=hashlib.new(algorithm,b'canonical').digest()
            assert db.execute('SELECT repo_catalog_git_content_digest_valid(?,?,?)',(b'canonical',algorithm,digest)).fetchone()[0]==1
            assert db.execute('SELECT repo_catalog_git_content_digest_valid(?,?,?)',(b'contradic',algorithm,digest)).fetchone()[0]==0
        results.append({'format':fmt,'canonical_predicate':'valid sequence accepted; duplicate rejected','NUL_row':nul_rejected,'operational_deletion':'availability unchanged','digest_algorithms':['md5','sha1','sha256']});db.close()
    return results


def selected_stage_closure():
    db,ids=fixture();collection=str(uuid.uuid4());scope={**ids,'endpoint':'pulls/1/body'}
    db.execute("INSERT INTO fetch_collections(fetch_collection_id,repository_uuidv4,change_request_id,kind,scope_json) VALUES(?,?,?,'pr-body',?)",(collection,ids['repository_uuidv4'],ids['change_request_id'],json.dumps(scope)))
    proof=CurrentCollectionProof(db);proof.page(collection,0,100,None,[],parser_module='review.synthetic',parser_version='1')
    db.execute("INSERT INTO completion_markers(fetch_collection_id,asserted_state,evidence,observed_at_us) VALUES(?,'complete',?,100)",(collection,json.dumps(proof.evidence(collection))))
    graph=Graph(db);original=graph.export(ids['repository_uuidv4'],fetch_collection_id=collection)
    row=dict(db.execute('SELECT * FROM fetch_collections').fetchone());unrelated=[]
    for _ in range(200):
        other=copy.deepcopy(row);other['fetch_collection_id']=str(uuid.uuid4());other['change_request_id']=str(uuid.uuid4());other_scope=copy.deepcopy(scope);other_scope['change_request_id']=other['change_request_id'];other['scope_json']=json.dumps(other_scope)
        unrelated.append(graph.record('fetch_collections',other))
    result=Graph(db).receive({**original,'records':unrelated})
    assert result['staged_records']==200
    exported=Graph(db).export(ids['repository_uuidv4'],fetch_collection_id=collection)
    assert exported==original
    plan=[tuple(r) for r in db.execute('EXPLAIN QUERY PLAN SELECT record_json FROM exchange_staging WHERE record_key=? AND repository_uuidv4=?',(original['records'][0]['key'],ids['repository_uuidv4']))]
    assert any('exchange_staging_record_owner' in str(r) for r in plan)
    assert all(r['key'] not in {s['key'] for s in unrelated} for r in exported['records'])
    db.close();return {'unrelated_genuine_pending_collections':200,'selected_export_unchanged':True,'query_plan':plan}


def main():
    output={}
    for fn in (computed_git_and_nul_guard,selected_stage_closure):output[fn.__name__]=fn();print(fn.__name__,'passed',flush=True)
    Path(__file__).with_name('cross-module-results.json').write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2))
if __name__=='__main__':main()
