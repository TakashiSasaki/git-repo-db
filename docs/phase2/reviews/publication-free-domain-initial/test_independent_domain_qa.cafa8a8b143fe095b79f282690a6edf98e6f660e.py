"""Independent synthetic review probes; no implementation test helpers."""
import base64
import copy
import hashlib
import json
import pathlib
import sqlite3
import subprocess
import sys
import types
import uuid

import pytest
import repo_catalog
from repo_catalog.adapters.git.parsing import GitParsing, verify_git_object_structure
from repo_catalog.adapters.sqlite.cas_integrity import repair_payload, verify_all
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.exchange_service import ExchangeService
from repo_catalog.application.git_query_context import decoded_fact, decoded_name
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.application.pr_queries import _code_observation, code_role_gaps
from repo_catalog.domain.models import CatalogError

REPO = "a1000000-0000-4000-8000-000000000001"
SERVICE = "a2000000-0000-4000-8000-000000000001"
PR = "independent-pr"
REF = b"refs/heads/qa"


def new_store(path):
    MaintenanceService(path).init("catalog-text-v1", 64 * 1024 * 1024, 0)
    return Store(path)


@pytest.fixture
def store(tmp_path):
    assert pathlib.Path(repo_catalog.__file__).is_relative_to(pathlib.Path.cwd())
    with new_store(tmp_path / "state") as value:
        yield value
        assert value.all("PRAGMA foreign_key_check") == []
        assert value.one("PRAGMA integrity_check")[0] == "ok"


def insert(s, table, **row):
    return s.execute(f"INSERT INTO {table}({','.join(row)}) VALUES({','.join('?' for _ in row)})", tuple(row.values()))


def seed(s):
    insert(s, "repositories", repository_uuidv4=REPO, name="qa", metadata="{}")
    insert(s, "service_instances", service_instance_uuidv4=SERVICE, service_kind="github", name="qa", metadata="{}")
    insert(s, "repository_bindings", repository_binding_id="qa-binding", repository_uuidv4=REPO, service_instance_uuidv4=SERVICE, provider_repository_id="qa", metadata="{}")
    insert(s, "change_requests", change_request_id=PR, repository_uuidv4=REPO, repository_binding_id="qa-binding", change_request_kind="pull_request", provider_change_request_number=1)


def candidate(clock, kind="change-request", **fields):
    return dict(repository_uuidv4=REPO, repository_binding_id="qa-binding", service_instance_uuidv4=SERVICE, change_request_id=PR, kind=kind, provider_updated_at_us=clock, provider_clock_scope="github-pr-updated-at", observed_at_us=clock, parsed_at_us=clock, parser_module="independent-qa", parser_version="qa1", acquisition_scope=dict(repository_uuidv4=REPO, repository_binding_id="qa-binding", service_instance_uuidv4=SERVICE, change_request_id=PR, endpoint="qa"), **fields)


def oid(fmt, typ, raw):
    return hashlib.new(fmt, typ.encode() + b" " + str(len(raw)).encode() + b"\0" + raw).digest()


def graph_fixture(s, fmt="sha1"):
    seed(s)
    bodies = {"blob": b"\xffhello", "tree": None, "commit": None}
    blob = oid(fmt, "blob", bodies["blob"])
    bodies["tree"] = b"100644 odd-\xff.txt\0" + blob
    tree = oid(fmt, "tree", bodies["tree"])
    bodies["commit"] = b"tree " + tree.hex().encode() + b"\nauthor QA <qa@example.invalid> 0 +0000\ncommitter QA <qa@example.invalid> 0 +0000\n\n\xffmessage\n"
    head = oid(fmt, "commit", bodies["commit"])
    acq = str(uuid.uuid4())
    roots = [dict(name=REF.decode(), name_b64=base64.b64encode(REF).decode(), oid=head.hex(), type="commit", peeled=None)]
    insert(s, "git_acquisitions", git_acquisition_id=acq, repository_uuidv4=REPO, object_format=fmt, kind="git", request="{}", roots_manifest=json.dumps(roots), refs_observed_at_us=-1)
    parser = GitParsing(s, REPO)
    ids = {typ: parser.install_object(fmt, oid(fmt, typ, body), typ, body, acquisition=acq) for typ, body in bodies.items()}
    insert(s, "snapshots", snapshot_id=acq, git_acquisition_id=acq, repository_uuidv4=REPO, complete=0, generation=0, created_at_us=-1)
    insert(s, "ref_observations", repository_uuidv4=REPO, snapshot_id=acq, raw_ref_name=REF, kind="head", object_format=fmt, target_oid=head, target_type="commit")
    root = insert(s, "acquisition_roots", git_acquisition_id=acq, repository_uuidv4=REPO, object_format=fmt, oid=head, role="head", complete=0).lastrowid
    insert(s, "root_origins", acquisition_root_id=root, repository_uuidv4=REPO, origin_kind="ref", raw_ref_name=REF, source_ordinal=0, snapshot_id=acq)
    parser.parse_acquisition(acq)
    assert parser.validate_acquisition(acq) == 3
    s.execute("UPDATE acquisition_roots SET complete=1 WHERE acquisition_root_id=?", (root,))
    s.execute("UPDATE snapshots SET complete=1 WHERE snapshot_id=?", (acq,))
    return parser, acq, ids, bodies, head


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_invalid_identity_missing_target_and_atomic_failure(store, fmt, monkeypatch):
    parser = GitParsing(store)
    raw = b"100644 first\0" + oid(fmt, "blob", b"absent") + b"100644 second\0" + oid(fmt, "blob", b"absent")
    before = store.revision()
    original_write = GitParsing.write
    emitted = 0
    def interrupt(self, sql, values):
        nonlocal emitted
        if sql.startswith("INSERT INTO tree_entries"):
            emitted += 1
            if emitted == 2:
                raise CatalogError("QA_INTERRUPTION", "synthetic incomplete object")
        return original_write(self, sql, values)
    monkeypatch.setattr(GitParsing, "write", interrupt)
    with pytest.raises(CatalogError, match="synthetic incomplete"):
        parser.install_object(fmt, oid(fmt, "tree", raw), "tree", raw)
    assert store.revision() == before
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 0
    assert store.one("SELECT count(*) FROM git_objects")[0] == 0
    monkeypatch.setattr(GitParsing, "write", original_write)
    tree_id = parser.install_object(fmt, oid(fmt, "tree", raw), "tree", raw)
    assert store.one("SELECT count(*) FROM tree_entries WHERE child_git_object_id IS NULL")[0] == 2
    assert store.one("SELECT count(*) FROM git_objects")[0] == 1
    with pytest.raises(CatalogError, match="missing descendants"):
        parser.manifest(tree_id)
    for declared in (b"x" * len(oid(fmt, "blob", b"bad")), b"x"):
        with pytest.raises(CatalogError):
            parser.install_object(fmt, declared, "blob", b"bad")
    for typ in ("fake", "tree"):
        with pytest.raises(CatalogError):
            parser.install_object(fmt, oid(fmt, "blob", b"bad"), typ, b"bad")
    assert store.one("SELECT count(*) FROM git_objects")[0] == 1
    assert verify_git_object_structure(store.connection, tree_id)


@pytest.mark.parametrize("fmt,width", [(fmt, width) for fmt in ("sha1", "sha256") for width in (2, 2048)])
def test_original_nul_boundary_counterexample_fixed(store, fmt, width):
    child = oid(fmt, "blob", b"missing")
    raw = b"".join(b"100644 q%04d\0" % n + child for n in range(width))
    payload = intern_payload(store.connection, raw, representation="git-object-raw-v1")
    target = insert(store, "git_objects", object_format=fmt, oid=oid(fmt,"tree",raw), type="tree", size=len(raw), verified=1).lastrowid
    store.execute("INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)", (target,payload.sha256))
    store.execute("INSERT INTO tree_objects VALUES(?,1)", (target,))
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        store.execute("INSERT INTO tree_entries VALUES(?,?,0,?,33188,?,?,NULL)", (target,raw[7:-len(child)-1],len(raw),fmt,child))
    assert not store.one("SELECT 1 FROM available_git_objects WHERE git_object_id=?", (target,))


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_decoder_reverse_repeat_reopen_onward_roundtrip(store, tmp_path, fmt):
    parser, acq, ids, bodies, head = graph_fixture(store, fmt)
    latin = GitParsing(store, REPO, text_encoding="latin-1", metadata_encoding="latin-1")
    for typ, body in bodies.items():
        latin.parse_object(store.one("SELECT * FROM git_objects WHERE git_object_id=?", (ids[typ],)), body)
    assert decoded_fact(store, ids["blob"], "blob")["decoder_conflict"]
    assert decoded_fact(store, ids["commit"], "commit")["decoder_conflict"]
    assert decoded_name(store,ids["tree"],b"odd-\xff.txt")["decoder_conflict"]
    unit = Graph(store.connection).export(REPO, git_acquisition_id=acq)
    unit["records"].reverse()
    target_path = tmp_path / "receiver"
    with new_store(target_path) as target:
        result = Graph(target.connection).receive(unit)
        assert result["rejected_records"] == 0
        assert result["staged_records"] == 0, [tuple(r) for r in target.all("SELECT table_name,reason FROM exchange_staging")]
        assert target.one("SELECT count(*) FROM available_git_objects")[0] == 3
        assert target.one("SELECT snapshot_id FROM current_snapshots")[0] == acq
        assert check_catalog(target,full=True) == []
    with Store(target_path) as target:
        replay = Graph(target.connection).receive(unit)
        assert replay["received_records"] == replay["admitted_records"] == replay["staged_records"] == 0
        obj = target.one("SELECT git_object_id FROM git_objects WHERE type='blob'")[0]
        assert decoded_fact(target,obj,"blob")["decoder_conflict"]
        assert decoded_fact(target,obj,"blob",decoder_key=latin.decoder_key)["fact"]["raw_text"] == "ÿhello"
        onward = Graph(target.connection).export(REPO)
        with new_store(tmp_path / "third") as third:
            result = Graph(third.connection).receive(onward)
            assert result["staged_records"] == 0
            assert third.one("SELECT count(*) FROM git_text_facts")[0] == 2
            assert check_catalog(third,full=True) == []


def test_current_document_missing_parent_late_arrival_and_stale_repeat(store, tmp_path):
    seed(store)
    api = CurrentApiState(store.connection)
    assert api.admit("document_state",candidate(100,"pr-body",provider_change_request_document_id="1",body_status="present",body="old"),source="import").status == "accepted"
    initial = Graph(store.connection).export(REPO)
    doc = next(r for r in initial["records"] if r["table"] == "document_state")
    part = {**initial,"records":[doc]}
    path = tmp_path / "receiver"
    with new_store(path) as target:
        result = Graph(target.connection).receive(part)
        assert result["staged_records"] == 1
        assert target.one("SELECT count(*) FROM document_state")[0] == 0
    with Store(path) as target:
        late = {**initial,"records":[r for r in initial["records"] if r is not doc]}
        result = Graph(target.connection).receive(late)
        assert result["staged_records"] == 0
        assert target.one("SELECT body FROM text_bodies JOIN document_state ON sha256=text_body_sha256")[0] == "old"
    assert api.admit("document_state",candidate(200,"pr-body",provider_change_request_document_id="1",body_status="present",body="new"),source="import").status == "accepted"
    updated = Graph(store.connection).export(REPO)
    with Store(path) as target:
        assert Graph(target.connection).receive(updated)["staged_records"] == 0
        assert Graph(target.connection).receive(initial)["staged_records"] == 0
        assert target.one("SELECT body FROM text_bodies JOIN document_state ON sha256=text_body_sha256")[0] == "new"
        assert target.one("SELECT last_checked_at_us FROM document_state")[0] is None
        onward = Graph(target.connection).export(REPO)
        assert len([r for r in onward["records"] if r["table"]=="document_state"]) == 1
        assert all(r["values"]["body"] != "old" for r in onward["records"] if r["table"]=="text_bodies")


def test_physical_shared_digest_quarantine_backup_restore_and_cas41(store,tmp_path):
    body = b"shared digest QA"
    parser = GitParsing(store)
    for fmt in ("sha1","sha256"):
        parser.install_object(fmt,oid(fmt,"blob",body),"blob",body)
    assert store.one("SELECT count(*) FROM stored_bytes")[0] == 1
    digest = hashlib.sha256(body).digest()
    # Physical fault injection restores the exact original trigger in this unit.
    trigger = store.one("SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'")[0]
    with store.transaction():
        store.execute("DROP TRIGGER stored_bytes_immutable")
        store.execute("UPDATE stored_bytes SET body=? WHERE sha256=?", (b"x"*len(body),digest))
        store.execute(trigger)
    report = verify_all(store.connection)
    assert len(report["corrupt"]) == 1
    assert store.one("SELECT count(*) FROM available_git_objects")[0] == 0
    after = store.revision()
    assert len(verify_all(store.connection)["corrupt"]) == 1
    assert store.revision() == after
    output = tmp_path / "backup.sqlite3"
    MaintenanceService(store.path).backup(store,output)
    manifest_path = output.with_name(output.name+".manifest.json")
    original = json.loads(manifest_path.read_text())
    assert original["quarantined_payload_count"] == 1
    wrong = {**original,"quarantined_payload_count":0}
    manifest_path.write_text(json.dumps(wrong))
    refused = tmp_path / "refused"
    with pytest.raises(CatalogError,match="quarantine count differs") as error:
        MaintenanceService(refused).restore(output)
    assert not refused.exists()
    staged = pathlib.Path(error.value.details["stage"])
    with sqlite3.connect(staged / store.config["database"]["filename"]) as copied:
        assert copied.execute("SELECT count(*) FROM payload_quarantine").fetchone()[0] == 1
    manifest_path.write_text(json.dumps(original))
    destination=tmp_path/"restored"
    MaintenanceService(destination).restore(output)
    with Store(destination) as restored:
        assert restored.revision()["db_instance_id"] != store.revision()["db_instance_id"]
        assert restored.revision()["local_revision"] == store.revision()["local_revision"]
        with pytest.raises(CatalogError):
            repair_payload(restored.connection,digest,b"false")
        assert repair_payload(restored.connection,digest,body)["repaired"]
        assert restored.one("SELECT count(*) FROM available_git_objects")[0] == 2
    with pytest.raises(CatalogError,match="must not exist"):
        MaintenanceService(destination).restore(output)
    assert store.one("SELECT count(*) FROM payload_quarantine")[0] == 1


def test_receiver_local_revision_is_independent_and_repeat_stable(store,tmp_path):
    seed(store)
    CurrentApiState(store.connection).admit("change_request_state",candidate(10,state="open"),source="import")
    store.execute("UPDATE database_identity SET local_revision=987654321")
    unit=Graph(store.connection).export(REPO)
    file=tmp_path/"unit.json"
    file.write_text(json.dumps(unit))
    path=tmp_path/"receiver"
    with new_store(path) as target:
        identity=target.revision()["db_instance_id"]
    service=ExchangeService(path)
    service.import_file(file)
    with Store(path) as target:
        first=target.revision()
        assert first["db_instance_id"] == identity
        assert 0 < first["local_revision"] < 987654321
        assert target.one("SELECT provider_updated_at_us FROM change_request_state")[0] == 10
    service.import_file(file)
    with Store(path) as target:
        assert target.revision() == first


def test_old_code_anchor_never_borrows_new_head(store):
    seed(store)
    api=CurrentApiState(store.connection)
    old=oid("sha1","commit",b"old")
    newer=oid("sha1","commit",b"new")
    base=oid("sha1","commit",b"base")
    api.admit("change_request_state",candidate(100,state="open",object_format="sha1",head_oid=old.hex(),base_oid=base.hex()),source="import")
    insert(store,"code_assessments",code_assessment_id="old-assessment",change_request_id=PR,repository_uuidv4=REPO,state="partial",object_format="sha1",head_oid=old,base_oid=base,observed_at_us=100,parser_module="qa",parser_version="1",details_json="{}")
    query=types.SimpleNamespace(s=store)
    pr=dict(store.one("SELECT * FROM change_requests"))
    assert _code_observation(query,pr)["code_assessment_id"] == "old-assessment"
    api.admit("change_request_state",candidate(200,state="open",object_format="sha1",head_oid=newer.hex(),base_oid=base.hex()),source="import")
    assert _code_observation(query,pr) is None
    old_row=dict(store.one("SELECT * FROM code_assessments"))
    assert old_row["head_oid"] == old
    assert {g["role"] for g in code_role_gaps(store,pr,old_row,check=lambda:None)} == {"head","base"}


@pytest.mark.parametrize("name", [b".",b"..",b"dir/file"])
def test_invalid_intrinsic_tree_names_cannot_be_available(store,name):
    child=oid("sha1","blob",b"missing")
    raw=b"100644 "+name+b"\0"+child
    payload=intern_payload(store.connection,raw,representation="git-object-raw-v1")
    obj=insert(store,"git_objects",object_format="sha1",oid=oid("sha1","tree",raw),type="tree",size=len(raw),verified=1).lastrowid
    store.execute("INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)",(obj,payload.sha256))
    store.execute("INSERT INTO tree_objects VALUES(?,1)",(obj,))
    try:
        store.execute("INSERT INTO tree_entries VALUES(?,?,0,?,33188,'sha1',?,NULL)",(obj,name,len(raw),child))
    except sqlite3.IntegrityError:
        return
    with pytest.raises(CatalogError,match="Malformed tree entry"):
        verify_git_object_structure(store.connection,obj)
    assert not store.one("SELECT 1 FROM available_git_objects WHERE git_object_id=?",(obj,)), "invalid canonical name became available"


@pytest.mark.parametrize("typ",["tag","commit"])
def test_available_intrinsic_headers_match_canonical_parser(store,typ):
    target=oid("sha1","blob",b"missing")
    if typ=="tag":
        raw=b"object "+target.hex().encode()+b"\ntype blob-extra\ntag qa\n\nmessage"
    else:
        header=b"tree "+target.hex().encode()
        raw=header+b"\n"+header+b"\n\nmessage"
    payload=intern_payload(store.connection,raw,representation="git-object-raw-v1")
    obj=insert(store,"git_objects",object_format="sha1",oid=oid("sha1",typ,raw),type=typ,size=len(raw),verified=1).lastrowid
    store.execute("INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)",(obj,payload.sha256))
    if typ=="tag":
        store.execute("INSERT INTO tag_objects VALUES(?,'sha1',?,'blob',NULL,?)",(obj,target,raw))
    else:
        headers,message=raw.split(b"\n\n",1)
        store.execute("INSERT INTO commits VALUES(?,'sha1',?,NULL,0,0,?,?)",(obj,target,headers,message))
    with pytest.raises(CatalogError):
        verify_git_object_structure(store.connection,obj)
    assert not store.one("SELECT 1 FROM available_git_objects WHERE git_object_id=?",(obj,)), "malformed intrinsic headers became available"


def test_git_late_physical_arrival_and_pending_onward(store,tmp_path):
    _parser,acq,_ids,_bodies,_head=graph_fixture(store)
    unit=Graph(store.connection).export(REPO)
    initial={**unit,"records":[r for r in unit["records"] if r["table"] not in {"stored_bytes","payloads"}]}
    path=tmp_path/"receiver"
    with new_store(path) as target:
        result=Graph(target.connection).receive(initial)
        assert result["staged_records"]>0
        assert not target.one("SELECT 1 FROM available_git_objects")
        assert not target.one("SELECT 1 FROM current_snapshots")
        staged=[json.loads(r[0]) for r in target.all("SELECT record_json FROM exchange_staging")]
        assert all("body" not in r["values"] for r in staged)
        onward=Graph(target.connection).export(REPO)
        assert any(r["table"]=="git_object_payloads" for r in onward["records"])
    with Store(path) as target:
        late={**unit,"records":[r for r in unit["records"] if r["table"] in {"stored_bytes","payloads"}]}
        result=Graph(target.connection).receive(late)
        assert result["staged_records"]==0, [tuple(r) for r in target.all("SELECT table_name,reason FROM exchange_staging")]
        assert target.one("SELECT count(*) FROM available_git_objects")[0]==3
        assert target.one("SELECT snapshot_id FROM current_snapshots")[0]==acq
        assert Graph(target.connection).receive(unit)["staged_records"]==0


def test_fake_original_label_and_foreign_repository_record_rejected(store,tmp_path):
    _parser,_acq,_ids,_bodies,_head=graph_fixture(store)
    unit=Graph(store.connection).export(REPO)
    fake=copy.deepcopy(unit)
    payload=next(r for r in fake["records"] if r["table"]=="payloads")
    payload["values"]["representation"]="decoded_api"
    with new_store(tmp_path/"receiver") as target:
        with pytest.raises(CatalogError):
            Graph(target.connection).receive(fake)
        assert target.one("SELECT count(*) FROM stored_bytes")[0]==0
        foreign=copy.deepcopy(unit)
        foreign["repository_uuidv4"]=str(uuid.uuid4())
        with pytest.raises(CatalogError,match="Foreign repository"):
            Graph(target.connection).receive(foreign)
        assert target.one("SELECT count(*) FROM git_objects")[0]==0


def test_inconsistent_ref_capture_cannot_qualify_available_snapshot(store):
    seed(store)
    fmt="sha1"
    raw=b"blob"
    head=oid(fmt,"blob",raw)
    acq=str(uuid.uuid4())
    declared=b"refs/heads/declared"
    actual=b"refs/heads/different"
    roots=[dict(name=declared.decode(),name_b64=base64.b64encode(declared).decode(),oid=head.hex(),type="blob",peeled=None)]
    insert(store,"git_acquisitions",git_acquisition_id=acq,repository_uuidv4=REPO,object_format=fmt,kind="git",request="{}",roots_manifest=json.dumps(roots))
    parser=GitParsing(store,REPO)
    parser.install_object(fmt,head,"blob",raw,acquisition=acq)
    insert(store,"snapshots",snapshot_id=acq,git_acquisition_id=acq,repository_uuidv4=REPO,complete=0,generation=0)
    insert(store,"ref_observations",repository_uuidv4=REPO,snapshot_id=acq,raw_ref_name=actual,kind="head",object_format=fmt,target_oid=head,target_type="blob")
    store.execute("UPDATE snapshots SET complete=1 WHERE snapshot_id=?",(acq,))
    with pytest.raises(CatalogError,match="Ref capture differs"):
        parser.validate_acquisition(acq)
    assert not store.one("SELECT 1 FROM available_snapshots WHERE snapshot_id=?",(acq,)), "inconsistent capture became available"


@pytest.mark.parametrize("fmt",["sha1","sha256"])
def test_commit_parent_interruption_and_process_death_rollback(store,fmt,monkeypatch):
    parser=GitParsing(store)
    keep=b"keep-prefix"
    parser.install_object(fmt,oid(fmt,"blob",keep),"blob",keep)
    tree=oid(fmt,"tree",b"")
    parent=oid(fmt,"commit",b"missing")
    raw=b"tree "+tree.hex().encode()+b"\nparent "+parent.hex().encode()+b"\nparent "+parent.hex().encode()+b"\n\nmessage"
    before=store.revision()
    real=GitParsing.write
    def interrupt(self,sql,values):
        if sql.startswith("INSERT INTO commit_parents") and values[1]==1:
            raise CatalogError("QA_INTERRUPTION","partial parent sequence")
        return real(self,sql,values)
    monkeypatch.setattr(GitParsing,"write",interrupt)
    with pytest.raises(CatalogError,match="partial parent sequence"):
        parser.install_object(fmt,oid(fmt,"commit",raw),"commit",raw)
    assert store.revision()==before
    assert not store.one("SELECT 1 FROM commits")
    assert not store.one("SELECT 1 FROM commit_parents")
    monkeypatch.setattr(GitParsing,"write",real)
    code='''
import os,sys,hashlib
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.adapters.git.parsing import GitParsing
path,fmt,hexraw=sys.argv[1:]
raw=bytes.fromhex(hexraw)
oid=hashlib.new(fmt,b'commit '+str(len(raw)).encode()+b'\\0'+raw).digest()
real=GitParsing.write
def crash(self,sql,values):
    if sql.startswith('INSERT INTO commit_parents') and values[1]==1:
        os._exit(73)
    return real(self,sql,values)
GitParsing.write=crash
with Store(path) as s:
    GitParsing(s).install_object(fmt,oid,'commit',raw)
'''
    result=subprocess.run([sys.executable,"-c",code,str(store.path),fmt,raw.hex()],capture_output=True,text=True)
    assert result.returncode==73,result.stderr
    assert store.revision()==before
    assert store.one("SELECT count(*) FROM git_objects")[0]==1
    assert store.one("SELECT count(*) FROM stored_bytes")[0]==1
    assert not store.one("SELECT 1 FROM commits")


def test_direct_raw_git_mapping_cannot_assert_fake_oid(store):
    raw=b"ordinary genuine bytes"
    payload=intern_payload(store.connection,raw,representation="git-object-raw-v1")
    fake_oid=b"x"*20
    obj=insert(store,"git_objects",object_format="sha1",oid=fake_oid,type="blob",size=len(raw),verified=1).lastrowid
    try:
        store.execute("INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)",(obj,payload.sha256))
    except sqlite3.IntegrityError:
        return
    cid=insert(store,"contents",byte_length=len(raw)).lastrowid
    store.execute("INSERT INTO blob_content_map VALUES(?,?)",(obj,cid))
    with pytest.raises(CatalogError):
        verify_git_object_structure(store.connection,obj)
    assert not store.one("SELECT 1 FROM available_git_objects WHERE git_object_id=?",(obj,)), "fake declared Git OID became available"


def test_equal_clock_current_conflicts_survive_repeat_and_onward(store,tmp_path):
    seed(store)
    api=CurrentApiState(store.connection)
    first=candidate(100,"pr-body",provider_change_request_document_id="1",body_status="present",body="first")
    alternative={**first,"body":"alternative","parser_version":"newer-version"}
    assert api.admit("document_state",first,source="import").status=="accepted"
    assert api.admit("document_state",alternative,source="import").status=="conflict"
    assert not store.one("SELECT 1 FROM eligible_document_state")
    unit=Graph(store.connection).export(REPO)
    assert len([r for r in unit["records"] if r["table"]=="document_state"])==2
    path=tmp_path/"receiver"
    with new_store(path) as target:
        result=Graph(target.connection).receive(unit)
        assert result["staged_records"]==1
        assert not target.one("SELECT 1 FROM eligible_document_state")
        before=target.one("SELECT count(*) FROM exchange_staging")[0]
        Graph(target.connection).receive(unit)
        assert target.one("SELECT count(*) FROM exchange_staging")[0]==before
        onward=Graph(target.connection).export(REPO)
        assert len([r for r in onward["records"] if r["table"]=="document_state"])==2
    with new_store(tmp_path/"third") as third:
        onward["records"].reverse()
        result=Graph(third.connection).receive(onward)
        assert result["staged_records"]==1
        assert not third.one("SELECT 1 FROM eligible_document_state")


def test_cas41_mismatch_precedes_new_copy_diagnosis(store,tmp_path):
    import shutil
    raw=b"unexplained copy corruption"
    GitParsing(store).install_object("sha1",oid("sha1","blob",raw),"blob",raw)
    backup=tmp_path/"backup.sqlite3"
    MaintenanceService(store.path).backup(store,backup)
    bad=tmp_path/"changed-copy.sqlite3"
    shutil.copyfile(backup,bad)
    with sqlite3.connect(bad,isolation_level=None) as writer:
        trigger=writer.execute("SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'").fetchone()[0]
        writer.execute("DROP TRIGGER stored_bytes_immutable")
        writer.execute("UPDATE stored_bytes SET body=?",(b"x"*len(raw),))
        writer.execute(trigger)
    manifest=json.loads(backup.with_name(backup.name+".manifest.json").read_text())
    manifest["sha256"]=hashlib.sha256(bad.read_bytes()).hexdigest()
    manifest["quarantined_payload_count"]=1
    bad.with_name(bad.name+".manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(CatalogError,match="quarantine count differs") as error:
        MaintenanceService(tmp_path/"refused").restore(bad)
    stage=pathlib.Path(error.value.details["stage"])
    with sqlite3.connect(stage/store.config["database"]["filename"]) as copydb:
        assert copydb.execute("SELECT count(*) FROM payload_quarantine").fetchone()[0]==0
        assert copydb.execute("SELECT count(*) FROM unresolved_payloads").fetchone()[0]==0


def test_complete_exact_code_listing_roundtrip_derives_receiver_progress(store,tmp_path):
    seed(store)
    head=oid("sha1","commit",b"head")
    base=oid("sha1","commit",b"base")
    scope=candidate(100)["acquisition_scope"]
    scope["request_context"]={"object_format":"sha1","head_oid":head.hex(),"base_oid":base.hex()}
    for kind in ("commits","files"):
        collection="qa-"+kind
        listing="listing-"+kind
        insert(store,"fetch_collections",fetch_collection_id=collection,repository_uuidv4=REPO,change_request_id=PR,kind=kind,observed_at_us=100,scope_json=json.dumps(scope))
        insert(store,"code_listings",code_listing_id=listing,change_request_id=PR,fetch_collection_id=collection,kind=kind,object_format="sha1",head_oid=head,base_oid=base)
        proof=CurrentCollectionProof(store.connection)
        proof.page(collection,0,100,None,[],parser_module="independent-qa",parser_version="1")
        insert(store,"completion_markers",fetch_collection_id=collection,asserted_state="complete",evidence=json.dumps(proof.evidence(collection)),observed_at_us=100)
        insert(store,"code_listing_progress",code_listing_id=listing,state="complete",terminal=1,page_count=1,context_proven=1)
    insert(store,"code_assessments",code_assessment_id="qa-complete-code",change_request_id=PR,repository_uuidv4=REPO,commit_code_listing_id="listing-commits",file_code_listing_id="listing-files",state="complete",object_format="sha1",head_oid=head,base_oid=base,observed_at_us=100,parser_module="independent-qa",parser_version="1",details_json="{}")
    unit=Graph(store.connection).export(REPO)
    with new_store(tmp_path/"receiver") as target:
        result=Graph(target.connection).receive(unit)
        assert result["staged_records"]==0, [tuple(r) for r in target.all("SELECT table_name,reason FROM exchange_staging")]
        assert target.one("SELECT count(*) FROM code_listing_progress WHERE state='complete'")[0]==2
        assert target.one("SELECT state FROM code_assessments")[0]=="complete"

