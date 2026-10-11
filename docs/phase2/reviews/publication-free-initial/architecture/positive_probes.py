"""Independent positive architecture invariants; synthetic in-memory catalogs."""
import copy
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from counterexamples import candidate,fixture
from repo_catalog.adapters.git.parsing import install_git_object, verify_git_object_structure
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.application.git_query_context import decoded_fact
from repo_catalog.domain.models import CatalogError


def no_history():
    db,ids=fixture();api=CurrentApiState(db)
    for clock in range(1,10001):
        value=candidate(ids,clock=clock,state='open' if clock%2 else 'closed')
        value['observed_at_us']=value['parsed_at_us']=clock
        assert api.admit('change_request_state',value,source='import').status=='accepted'
    assert db.execute('SELECT count(*) FROM change_request_state').fetchone()[0]==1
    assert db.execute('SELECT count(*) FROM exchange_staging').fetchone()[0]==0
    assert db.execute('SELECT count(*) FROM fetch_collections').fetchone()[0]==0
    revision=db.execute('SELECT local_revision FROM database_identity').fetchone()[0]
    assert revision==10000
    counts={r[0]:db.execute('SELECT count(*) FROM '+r[0]).fetchone()[0] for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
    db.close();return {'updates':10000,'current_rows':1,'pending_rows':0,'collections':0,'local_revision':revision,'nonempty_tables':{k:v for k,v in counts.items() if v}}


def rollback():
    db,ids=fixture();api=CurrentApiState(db)
    api.admit('change_request_state',candidate(ids),source='import')
    before=dict(db.execute('SELECT * FROM change_request_state').fetchone())
    revision=db.execute('SELECT local_revision FROM database_identity').fetchone()[0]
    db.execute("CREATE TRIGGER injected_failure AFTER UPDATE ON change_request_state BEGIN SELECT RAISE(ABORT,'review failure'); END")
    db.execute('BEGIN')
    db.execute("UPDATE repositories SET name='unrelated outer edit'")
    try: api.admit('change_request_state',candidate(ids,clock=20,state='closed'),source='import')
    except sqlite3.IntegrityError: pass
    else: raise AssertionError('injection did not fire')
    db.execute('COMMIT')
    assert dict(db.execute('SELECT * FROM change_request_state').fetchone())==before
    assert db.execute('SELECT local_revision FROM database_identity').fetchone()[0]==revision
    assert db.execute('SELECT name FROM repositories').fetchone()[0]=='unrelated outer edit'
    db.close();return {'caught_nested_statement_failure':'resource/evidence/revision rolled back','unrelated_outer_edit':'committed'}


def git_intrinsic_and_decoders():
    output=[]
    for fmt in ('sha1','sha256'):
        db,ids=fixture()
        def oid(typ,body): return hashlib.new(fmt,f'{typ} {len(body)}\0'.encode()+body).digest()
        keep=install_git_object(db,fmt,oid('blob',b'keep'),'blob',b'keep')
        child=oid('blob',b'unavailable')
        tree=b'100644 first\0'+child+b'100644 second\0'+child
        db.execute("CREATE TRIGGER injected_tree_failure BEFORE INSERT ON tree_entries WHEN NEW.raw_name=X'7365636f6e64' BEGIN SELECT RAISE(ABORT,'review intrinsic failure'); END")
        try: install_git_object(db,fmt,oid('tree',tree),'tree',tree)
        except sqlite3.IntegrityError: pass
        else: raise AssertionError('intrinsic injection did not fire')
        assert db.execute('SELECT count(*) FROM git_objects').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM tree_entries').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM available_git_objects').fetchone()[0]==1
        db.execute('DROP TRIGGER injected_tree_failure')
        installed=install_git_object(db,fmt,oid('tree',tree),'tree',tree)
        entries=db.execute('SELECT child_oid,child_git_object_id FROM tree_entries').fetchall()
        assert len(entries)==2 and all(r['child_oid']==child and r['child_git_object_id'] is None for r in entries)
        assert db.execute('SELECT count(*) FROM git_objects').fetchone()[0]==2
        verify_git_object_structure(db,installed)
        text=b'caf\xe9'
        blob=install_git_object(db,fmt,oid('blob',text),'blob',text,text_encoding='utf-8')
        install_git_object(db,fmt,oid('blob',text),'blob',text,text_encoding='latin-1')
        class Reads:
            def all(self,sql,args=()): return db.execute(sql,args).fetchall()
        result=decoded_fact(Reads(),blob,'blob')
        assert result['decoder_conflict'] and result['fact'] is None and len(result['candidates'])==2
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        output.append({'format':fmt,'interrupted_object':'no partial owner/entries','unrelated_object':'available','missing_child':'real OID and NULL FK','disagreeing_decoder_count':2,'unselected_fact':None})
        db.close()
    return output


def main():
    result={}
    for fn in (rollback,git_intrinsic_and_decoders,no_history):
        result[fn.__name__]=fn()
        print(fn.__name__,'passed',flush=True)
    Path('/workspace/review-artifacts/architecture/positive-results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
