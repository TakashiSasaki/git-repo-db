"""Fresh independently authored corrected-tree cross-module correctness probes."""
import base64
import copy
import hashlib
import json
import sqlite3
import uuid

import pytest

from test_independent_domain_qa import (
    REPO, SERVICE, PR, REF, candidate, graph_fixture, insert, new_store, oid, seed, store,
)
from repo_catalog.adapters.git.parsing import GitParsing, verify_git_object_structure
from repo_catalog.adapters.sqlite.current_api import CurrentApiState
from repo_catalog.adapters.sqlite.current_collections import CurrentCollectionProof
from repo_catalog.adapters.sqlite.current_resources import CurrentResources
from repo_catalog.adapters.sqlite.coverage import admit_claim
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.adapters.sqlite.target import TargetReader
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.domain.models import CatalogError


def raw_object(s, fmt, typ, raw):
    payload = intern_payload(s.connection, raw, representation="git-object-raw-v1")
    obj = insert(s, "git_objects", object_format=fmt, oid=oid(fmt, typ, raw), type=typ, size=len(raw), verified=1).lastrowid
    s.execute("INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)", (obj, payload.sha256))
    return obj


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_duplicate_tree_name_never_available(store, fmt):
    child = oid(fmt, "blob", b"missing")
    entry = b"100644 same\0" + child
    raw = entry + entry
    obj = raw_object(store, fmt, "tree", raw)
    store.execute("INSERT INTO tree_objects VALUES(?,1)", (obj,))
    try:
        store.execute("INSERT INTO tree_entries VALUES(?,?,0,?,33188,?,?,NULL)", (obj, b"same", len(raw), fmt, child))
    except sqlite3.IntegrityError:
        pass
    with pytest.raises(CatalogError):
        verify_git_object_structure(store.connection, obj)
    assert not store.one("SELECT 1 FROM available_git_objects WHERE git_object_id=?", (obj,))


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_same_length_blob_map_with_wrong_digest_never_available(store, fmt):
    real = GitParsing(store).install_object(fmt, oid(fmt, "blob", b"abc"), "blob", b"abc")
    cid = store.one("SELECT content_id FROM blob_content_map WHERE git_object_id=?", (real,))[0]
    other = raw_object(store, fmt, "blob", b"xyz")
    store.execute("INSERT INTO blob_content_map VALUES(?,?)", (other, cid))
    with pytest.raises(CatalogError, match="digest contradicts"):
        verify_git_object_structure(store.connection, other)
    assert not store.one("SELECT 1 FROM available_git_objects WHERE git_object_id=?", (other,))
    assert store.one("SELECT 1 FROM available_git_objects WHERE git_object_id=?", (real,))


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("mismatch", ["type", "peeled"])
def test_exact_ref_capture_type_and_peeled_match(store, fmt, mismatch):
    seed(store)
    parser = GitParsing(store, REPO)
    body = b"target"
    target = oid(fmt, "blob", body)
    acq = str(uuid.uuid4())
    roots = [dict(name=REF.decode(), name_b64=base64.b64encode(REF).decode(), oid=target.hex(), type="blob", peeled=None)]
    insert(store, "git_acquisitions", git_acquisition_id=acq, repository_uuidv4=REPO, object_format=fmt, kind="git", request="{}", roots_manifest=json.dumps(roots))
    parser.install_object(fmt, target, "blob", body, acquisition=acq)
    insert(store, "snapshots", snapshot_id=acq, git_acquisition_id=acq, repository_uuidv4=REPO, complete=0, generation=0)
    insert(store, "ref_observations", repository_uuidv4=REPO, snapshot_id=acq, raw_ref_name=REF, kind="head", object_format=fmt, target_oid=target, target_type="tag" if mismatch == "type" else "blob", peeled_oid=target if mismatch == "peeled" else None)
    try:
        store.execute("UPDATE snapshots SET complete=1 WHERE snapshot_id=?", (acq,))
    except sqlite3.IntegrityError:
        pass
    with pytest.raises(CatalogError, match="Ref capture differs"):
        parser.validate_acquisition(acq)
    assert not store.one("SELECT 1 FROM available_snapshots WHERE snapshot_id=?", (acq,))


def test_readonly_target_uses_predicates_without_writes(store):
    _parser, acq, _ids, _bodies, _head = graph_fixture(store)
    before = store.revision()
    database = store.path / store.config["database"]["filename"]
    before_bytes = hashlib.sha256(database.read_bytes()).digest()
    with TargetReader(database, allow_building=True) as target:
        assert target.one("SELECT count(*) FROM available_git_objects")[0] == 3
        assert target.one("SELECT snapshot_id FROM available_snapshots")[0] == acq
        assert target.connection.total_changes == 0
        with pytest.raises(sqlite3.OperationalError):
            target.execute("UPDATE database_identity SET local_revision=0")
    assert store.revision() == before
    assert hashlib.sha256(database.read_bytes()).digest() == before_bytes


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_accepted_header_spelling_and_gitlink_remain_usable(store, fmt):
    parser = GitParsing(store)
    missing = oid(fmt, "commit", b"external-gitlink")
    raw = b"0160000 submodule\0" + missing
    tree = parser.install_object(fmt, oid(fmt, "tree", raw), "tree", raw)
    parser.manifest(tree)
    assert store.one("SELECT child_git_object_id FROM tree_entries")[0] is None
    tree_oid = oid(fmt, "tree", raw)
    commit_raw = b"author QA <qa@example.invalid> 0 +0000\ntree " + tree_oid.hex().upper().encode() + b"\n\nmessage"
    commit = parser.install_object(fmt, oid(fmt, "commit", commit_raw), "commit", commit_raw)
    tag_raw = b"type commit\ntag qa\nobject " + oid(fmt, "commit", commit_raw).hex().upper().encode() + b"\n\nmessage"
    tag = parser.install_object(fmt, oid(fmt, "tag", tag_raw), "tag", tag_raw)
    for obj in (tree, commit, tag):
        assert verify_git_object_structure(store.connection, obj)
        assert store.one("SELECT 1 FROM available_git_objects WHERE git_object_id=?", (obj,))


@pytest.mark.parametrize("family,field", [("git_text_facts", "raw_text"), ("git_commit_facts", "message_text"), ("git_name_facts", "decoded_name")])
@pytest.mark.parametrize("forged_first", [False, True])
def test_forged_decoder_arrival_does_not_monopolize_valid_value(store, tmp_path, family, field, forged_first):
    graph_fixture(store)
    latin = GitParsing(store, REPO, text_encoding="latin-1", metadata_encoding="latin-1")
    for row in store.all("SELECT g.*,b.body FROM git_objects g JOIN git_object_payloads p USING(git_object_id) JOIN stored_bytes b ON b.sha256=p.payload_sha256"):
        latin.parse_object(row, row["body"])
    unit = Graph(store.connection).export(REPO)
    valid = next(r for r in unit["records"] if r["table"] == family and r["values"]["decoder_key"] == latin.decoder_key)
    forged = copy.deepcopy(valid)
    forged["values"][field] = "ordinary invalid interpretation"
    path = tmp_path / "receiver"
    with new_store(path) as target:
        if forged_first:
            first = Graph(target.connection).receive({**unit, "records": [forged]})
            assert first["staged_records"] == 1
        unit["records"].reverse()
        valid_result = Graph(target.connection).receive(unit)
        if not forged_first:
            reject = Graph(target.connection).receive({**unit, "records": [forged]})
            assert reject["rejected_records"] == 1
        else:
            assert valid_result["rejected_records"] == 1
        assert target.one("SELECT count(*) FROM exchange_staging")[0] == 0
        value = target.one(f"SELECT {field} FROM {family} WHERE decoder_key=?", (latin.decoder_key,))[0]
        assert value == valid["values"][field]
        assert check_catalog(target, full=True) == []
        assert Graph(target.connection).receive(unit)["staged_records"] == 0
        onward = Graph(target.connection).export(REPO)
        assert all(r["values"].get(field) != "ordinary invalid interpretation" for r in onward["records"] if r["table"] == family)
    with new_store(tmp_path / "third") as third:
        assert Graph(third.connection).receive(onward)["staged_records"] == 0


DEST = "a1000000-0000-4000-8000-000000000002"


def issue_candidate(kind, provider, clock, body):
    return dict(kind=kind, service_instance_uuidv4=SERVICE, repository_uuidv4=REPO, repository_binding_id="qa-binding", provider_resource_id=provider, provider_issue_number=1, body_status="present", body=body, provider_updated_at_us=clock, provider_clock_scope="github-issue-updated-at" if kind == "issue" else "github-issue-comment-updated-at", observed_at_us=clock, parsed_at_us=clock, parser_module="independent-qa", parser_version="1", acquisition_scope=dict(repository_uuidv4=REPO, repository_binding_id="qa-binding", service_instance_uuidv4=SERVICE, endpoint="qa-issue"))


def transferred_unit(s):
    seed(s)
    api = CurrentResources(s.connection)
    parent = issue_candidate("issue", "10", 100, "parent")
    child = {**issue_candidate("issue-comment", "11", 50, "historical child"), "parent_provider_resource_id": "10"}
    assert api.admit(parent, source="import").status == "accepted"
    assert api.admit(child, source="import").status == "accepted"
    insert(s, "repositories", repository_uuidv4=DEST, name="dest", metadata="{}")
    insert(s, "repository_bindings", repository_binding_id="qa-dest-binding", repository_uuidv4=DEST, service_instance_uuidv4=SERVICE, provider_repository_id="dest", metadata="{}")
    moved = {**parent, "repository_uuidv4": DEST, "repository_binding_id": "qa-dest-binding", "provider_issue_number": 2, "provider_updated_at_us": 200, "acquisition_scope": {**parent["acquisition_scope"], "repository_uuidv4": DEST, "repository_binding_id": "qa-dest-binding"}}
    assert api.admit(moved, source="import").status == "accepted"
    return Graph(s.connection).export(DEST)


@pytest.mark.parametrize("contradict_capture", [False, True])
def test_detached_issue_capture_shape_before_parent_strict_after_resolution(store, tmp_path, contradict_capture):
    unit = transferred_unit(store)
    child = next(r for r in unit["records"] if r["table"] == "issue_resources" and r["values"]["kind"] == "issue-comment")
    assert json.loads(child["values"]["acquisition_scope_json"])["repository_uuidv4"] == REPO
    if contradict_capture:
        child = copy.deepcopy(child)
        scope = json.loads(child["values"]["acquisition_scope_json"])
        scope["repository_binding_id"] = "qa-dest-binding"
        child["values"]["acquisition_scope_json"] = json.dumps(scope)
    with new_store(tmp_path / "receiver") as target:
        first = Graph(target.connection).receive({**unit, "records": [child]})
        assert first["staged_records"] == 1
        rest = [r for r in unit["records"] if not (r["table"] == "issue_resources" and r["values"]["kind"] == "issue-comment")]
        result = Graph(target.connection).receive({**unit, "records": rest})
        if contradict_capture:
            assert not target.one("SELECT 1 FROM issue_resources WHERE kind='issue-comment'")
            assert target.one("SELECT reason FROM exchange_staging")[0].startswith("invalid:")
        else:
            assert result["staged_records"] == 0
            captured = target.one("SELECT repository_uuidv4,acquisition_scope_json FROM issue_resources WHERE kind='issue-comment'")
            assert captured[0] == DEST and json.loads(captured[1])["repository_uuidv4"] == REPO
            assert not target.one("SELECT 1 FROM repositories WHERE repository_uuidv4=?", (REPO,))
            assert Graph(target.connection).receive(unit)["staged_records"] == 0
            assert check_catalog(target, full=True) == []
            onward = Graph(target.connection).export(DEST)
            with new_store(tmp_path / "third") as third:
                assert Graph(third.connection).receive(onward)["staged_records"] == 0


@pytest.mark.parametrize("missing_parent", [False, True])
def test_malformed_current_candidate_rejected_but_valid_sibling_admitted(store, tmp_path, missing_parent):
    seed(store)
    api = CurrentApiState(store.connection)
    for ident, body in (("1", "bad fixture"), ("2", "independent sibling")):
        assert api.admit("document_state", candidate(100, "pr-body", provider_change_request_document_id=ident, body_status="present", body=body), source="import").status == "accepted"
    unit = Graph(store.connection).export(REPO)
    bad = next(r for r in unit["records"] if r["table"] == "document_state" and '"provider_change_request_document_id":"1"' in r["key"])
    evidence = json.loads(bad["values"]["field_evidence_json"])
    for proof in evidence.values():
        proof["acquisition_scope"]["opaque_unmodeled_response"] = {"data": "not a normalized resource"}
    bad["values"]["field_evidence_json"] = json.dumps(evidence)
    with new_store(tmp_path / "receiver") as target:
        if missing_parent:
            first = Graph(target.connection).receive({**unit, "records": [bad]})
            assert first["rejected_records"] == 1 and first["staged_records"] == 0
            rest = {**unit, "records": [r for r in unit["records"] if r is not bad]}
            result = Graph(target.connection).receive(rest)
        else:
            result = Graph(target.connection).receive(unit)
            assert result["rejected_records"] == 1
        assert result["staged_records"] == 0
        assert target.one("SELECT count(*) FROM document_state")[0] == 1
        assert target.one("SELECT body FROM document_state JOIN text_bodies ON text_body_sha256=sha256")[0] == "independent sibling"
        assert check_catalog(target, full=True) == []


def test_issue_terminal_marker_does_not_prove_git_scope(store, tmp_path):
    seed(store)
    collection = "independent-issues"
    insert(store, "fetch_collections", fetch_collection_id=collection, repository_uuidv4=REPO, kind="issues", observed_at_us=100, scope_json=json.dumps({"repository_uuidv4": REPO, "repository_binding_id": "qa-binding", "service_instance_uuidv4": SERVICE, "endpoint": "issues"}))
    proof = CurrentCollectionProof(store.connection)
    proof.page(collection, 0, 100, None, [], parser_module="qa", parser_version="1")
    marker = insert(store, "completion_markers", fetch_collection_id=collection, asserted_state="complete", evidence=json.dumps(proof.evidence(collection)), observed_at_us=100).lastrowid
    marker_uuid = store.one("SELECT completion_marker_uuidv4 FROM completion_markers WHERE completion_marker_id=?", (marker,))[0]
    scope = "independent-git-scope"
    insert(store, "coverage_scopes", coverage_scope_id=scope, repository_uuidv4=REPO, kind="git")
    claim_id = admit_claim(store.connection, scope, "complete", 100, json.dumps({"completion_marker_uuidv4s": [marker_uuid]}))
    claim = dict(store.one("SELECT * FROM coverage_claims WHERE coverage_claim_id=?", (claim_id,)))
    assert Graph(store.connection).proof_requirements("coverage_claims", claim) is None
    graph = Graph(store.connection)
    unit = graph.export(REPO)
    assert not any(r["table"] == "coverage_claims" for r in unit["records"])
    unit["records"].append(graph.record("coverage_claims", claim))
    with new_store(tmp_path / "receiver") as target:
        result = Graph(target.connection).receive(unit)
        assert result["staged_records"] > 0
        assert not target.one("SELECT 1 FROM coverage_claims WHERE coverage_state='complete'")
        assert not target.one("SELECT 1 FROM git_objects")
