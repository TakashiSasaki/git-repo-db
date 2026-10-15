"""Independent read-only reviewer adversaries; source lives outside the branch."""
import hashlib
import sqlite3
from dataclasses import replace
from uuid import uuid4
import pytest
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.p1_core import OID, NativeObject, CoreFailure, Capture, NotesProof, RelationGroup, RelationMember, Provenance, native_oid
from repo_catalog.domain.git_native import parse_metadata

class Budget:
    class Limits:
        note_bytes = 1048576
    limits=Limits()
    def require(self, unit, amount=1):
        assert isinstance(amount, int) and amount >= 0
    def charge(self, unit, amount):
        pass

def native(kind, body, fmt='sha1'):
    return NativeObject(OID(fmt,native_oid(fmt,kind,body)),kind,body,len(body),hashlib.sha256(body).hexdigest())

def commit_body(fmt='sha1', extra=b'', message=b'exact\xffmessage\n'):
    return b'tree '+(b'a'*(40 if fmt=='sha1' else 64))+b'\nauthor A <a@invalid> 1 +0000\ncommitter C <c@invalid> 2 +0000\n'+extra+b'\n'+message

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_lossless_extension_and_message(fmt):
    body=commit_body(fmt,b'encoding ISO-8859-1\ngpgsig -----BEGIN PGP SIGNATURE-----\n continuation\n -----END PGP SIGNATURE-----\n')
    value=parse_metadata(fmt,'commit',body)
    assert value.scalars['message'].encode('utf8','surrogateescape')==b'exact\xffmessage\n'
    assert bytes.fromhex(value.scalars['header_data'])==body.partition(b'\n\n')[0]
    assert value.relations['commit_parents']==[]

@pytest.mark.parametrize('fmt',['sha1','sha256'])
@pytest.mark.parametrize('body',[
    b'tree a\n\n',
    b'parent '+b'a'*40+b'\n\n',
    b'tree '+b'a'*40+b'\nauthor A <a> 1 +0000\ncommitter C <c> 1 +0000\nparent '+b'b'*40+b'\n\n',
    b'tree '+b'a'*40+b'\nauthor A <a> 1 +0000\ncommitter C <c> 1 +0000\nencoding utf8\nencoding latin1\n\n',
    b'tree '+b'a'*40+b'\nauthor A <a> 1 +0000\ncommitter C <c> 1 +0000\ngpgsig\n\n',
])
def test_malformed_commit_typed(fmt,body):
    with pytest.raises(CoreFailure) as exc:
        parse_metadata(fmt,'commit',body)
    assert exc.value.code=='NATIVE_SYNTAX'

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_unbounded_timestamp_typed(fmt):
    body=commit_body(fmt).replace(b'A <a@invalid> 1 +0000',b'A <a@invalid> '+b'9'*5000+b' +0000')
    with pytest.raises(CoreFailure) as exc:
        parse_metadata(fmt,'commit',body)
    assert exc.value.code=='NATIVE_SYNTAX'

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_binary_tree_order_and_truncation(fmt):
    width=20 if fmt=='sha1' else 32
    body=b'100644 a\xff\0'+b'a'*width+b'40000 b\0'+b'b'*width
    parsed=parse_metadata(fmt,'tree',body)
    assert parsed.relations['tree_entries'][0][0]==['100644','61ff']
    for bad in (body[:-1],b'40000 b\0'+b'b'*width+b'100644 a\xff\0'+b'a'*width,b'100644 .\0'+b'a'*width):
        with pytest.raises(CoreFailure):
            parse_metadata(fmt,'tree',bad)

@pytest.fixture
def production(tmp_path):
    from repo_catalog.adapters.sqlite.git_core import GitCore
    repo=str(uuid4())
    path=tmp_path/'core.sqlite3'
    initialize(path,'core',repo,str(uuid4()))
    adapter=GitCore(path)
    adapter.admit_repository(repo)
    yield adapter,path,repo
    adapter.close()

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_production_negative_closure_and_exact_replay(production,fmt):
    core,path,repo=production
    obj=native('commit',commit_body(fmt),fmt)
    p=Provenance('source','original','parents','reported-decoder','1')
    reported=RelationGroup(obj.oid,'commit_parents','independently labeled fragment','partial',(RelationMember(17,OID(fmt,'b'*(40 if fmt=='sha1' else 64))),),p)
    core.admit_group(reported)
    core.admit_metadata(obj,str(uuid4()),Budget())
    core.admit_group(reported)
    result=core.relations(obj.oid,'commit_parents')
    assert result.canonical==['known_empty',[]]
    assert result.reported_conflict
    assert len(result.alternatives)==2
    assert sum(x['checked'] for x in result.alternatives)==1
    assert core.read_metadata(obj.oid)==obj.body
    assert not (path.parent/'context.sqlite3').exists()

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_production_role_proof_malformed_root_is_typed(production,fmt):
    core,path,repo=production
    target=OID(fmt,'b'*(40 if fmt=='sha1' else 64))
    note=native('blob',b'notes body',fmt)
    tree=native('tree',b'100644 '+target.full_oid.encode()+b'\0'+bytes.fromhex(note.oid.full_oid),fmt)
    malformed=native('commit',b'tree '+tree.oid.full_oid.encode()+b'\n\n',fmt)
    capture=Capture(str(uuid4()),str(uuid4()),repo,'original-source','refs/notes/commits',malformed.oid)
    proof=NotesProof(capture,target,note.oid,target.full_oid,(malformed,tree))
    with pytest.raises(CoreFailure):
        core.admit_notes_role(proof,Budget())
    with pytest.raises(CoreFailure):
        core.admit_note(proof,note,str(uuid4()),Budget())
    assert core.notes_projection(capture,target).canonical is None

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_production_ordinary_blob_refused(production,fmt):
    core,_,_=production
    with pytest.raises(CoreFailure) as exc:
        core.admit_metadata(native('blob',b'ordinary file',fmt),str(uuid4()),Budget())
    assert exc.value.code=='RETENTION_PURPOSE'

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_production_no_canonical_zero_reference(production,fmt):
    core,_,_=production
    obj=native('tree',b'100644 a\0'+b'\0'*(20 if fmt=='sha1' else 32),fmt)
    with pytest.raises(CoreFailure) as exc:
        core.admit_metadata(obj,str(uuid4()),Budget())
    assert exc.value.code=='NATIVE_SYNTAX'

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_production_corruption_stops_after_historical_metadata(production,fmt):
    core,path,_=production
    obj=native('commit',commit_body(fmt),fmt)
    core.admit_metadata(obj,str(uuid4()),Budget())
    assert core.scalar(obj.oid,'author_name').canonical==['known','A']
    # Privileged disposable damage deliberately bypasses the supported adapter.
    damage=sqlite3.connect(path)
    damage.execute('PRAGMA ignore_check_constraints=ON')
    for (name,) in damage.execute("SELECT name FROM sqlite_schema WHERE type='trigger' AND tbl_name='retained_metadata'").fetchall():
        damage.execute('DROP TRIGGER "'+name.replace('"','""')+'"')
    damage.execute('UPDATE retained_metadata SET body=?',(b'damaged bytes',))
    damage.commit();damage.close()
    assert core.scalar(obj.oid,'author_name').canonical==['known','A']
    with pytest.raises(CoreFailure) as exc:
        core.read_metadata(obj.oid)
    assert exc.value.code=='AUTHORITATIVE_CORRUPTION'
    assert (path.parent/'p1-recovery-stop.json').exists()
    with pytest.raises(CoreFailure) as exc:
        core.scalar(obj.oid,'author_name')
    assert exc.value.code=='RECOVERY_STOP'


def test_production_generic_sql_cannot_export_unchecked_bodies(production):
    core,_,_=production
    obj=native('tree',b'')
    core.admit_metadata(obj,str(uuid4()),Budget())
    for sql in ('SELECT body FROM retained_metadata','SELECT hex(body) FROM retained_metadata','SELECT body AS payload FROM retained_metadata','SELECT proof_bundle FROM note_roles'):
        with pytest.raises(sqlite3.DatabaseError):
            core.sql(sql)
    assert core.read_metadata(obj.oid)==b''

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_production_nul_commit_message_is_typed(production,fmt):
    core,_,_=production
    obj=native('commit',commit_body(fmt,message=b'bad\0message\n'),fmt)
    with pytest.raises(CoreFailure) as exc:
        core.admit_metadata(obj,str(uuid4()),Budget())
    assert exc.value.code=='NATIVE_SYNTAX'

@pytest.mark.parametrize('fmt',['sha1','sha256'])
def test_production_tag_structural_header_position(production,fmt):
    core,_,_=production
    width=40 if fmt=='sha1' else 64
    body=b'object '+b'a'*width+b'\ntype commit\ntag release\nx-other value\ntagger A <a> 1 +0000\n\nmessage\n'
    with pytest.raises(CoreFailure) as exc:
        core.admit_metadata(native('tag',body,fmt),str(uuid4()),Budget())
    assert exc.value.code=='NATIVE_SYNTAX'
