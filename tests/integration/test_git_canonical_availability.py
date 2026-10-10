"""Ordinary readers cannot promote malformed bytes or contradictory captures."""

import base64
import copy
import hashlib
import json
import sqlite3

import pytest

from repo_catalog.adapters.git.parsing import GitParsing, verify_git_object_structure
from repo_catalog.adapters.sqlite.cas_integrity import _git_object_identity_valid
from repo_catalog.adapters.sqlite.exchange import Graph
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.application.git_query_context import decoded_fact
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_git_runtime import runtime
from tests.integration.test_git_direct_objects import OWNER, oid


@pytest.fixture
def store(tmp_path):
    with runtime(tmp_path) as value:
        yield value


def raw_object(store, fmt, typ, raw, *, declared_oid=None):
    payload = intern_payload(store.connection, raw, representation="git-object-raw-v1")
    obj = store.execute(
        "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES(?,?,?,?,1)",
        (fmt, declared_oid or oid(fmt, typ, raw), typ, len(raw)),
    ).lastrowid
    store.execute(
        "INSERT INTO git_object_payloads VALUES(?,'git-object-raw-v1',?)",
        (obj, payload.sha256),
    )
    return obj


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize(
    "attack",
    [
        "tree-dot",
        "tree-dotdot",
        "tree-slash",
        "duplicate-tree",
        "bare-header",
        "tag-type-prefix",
        "tag-separator",
        "tag-target",
    ],
)
def test_canonical_hash_does_not_make_malformed_intrinsic_structure_available(
    store, fmt, attack
):
    target = oid(fmt, "blob", b"missing")
    if attack.startswith("tree-"):
        name = {"tree-dot": b".", "tree-dotdot": b"..", "tree-slash": b"dir/file"}[
            attack
        ]
        raw = b"100644 " + name + b"\0" + target
        obj = raw_object(store, fmt, "tree", raw)
        store.execute("INSERT INTO tree_objects VALUES(?,1)", (obj,))
        store.execute(
            "INSERT INTO tree_entries VALUES(?,?,0,?,33188,?,?,NULL)",
            (obj, name, len(raw), fmt, target),
        )
    elif attack in ("duplicate-tree", "bare-header"):
        header = b"tree " + target.hex().encode()
        headers = (
            header + b"\n" + (header if attack == "duplicate-tree" else b"malformed")
        )
        raw = headers + b"\n\nmessage"
        obj = raw_object(store, fmt, "commit", raw)
        store.execute(
            "INSERT INTO commits VALUES(?,?,?,NULL,0,0,?,?)",
            (obj, fmt, target, headers, b"message"),
        )
    else:
        target_type = b"blob-extra" if attack == "tag-type-prefix" else b"blob"
        raw = (
            b"object "
            + target.hex().encode()
            + b"\ntype "
            + target_type
            + b"\ntag test"
            + (b"\nmessage" if attack == "tag-separator" else b"\n\nmessage")
        )
        obj = raw_object(store, fmt, "tag", raw)
        recorded_target = (
            oid(fmt, "blob", b"different") if attack == "tag-target" else target
        )
        store.execute(
            "INSERT INTO tag_objects VALUES(?,?,?,'blob',NULL,?)",
            (obj, fmt, recorded_target, raw),
        )
    with pytest.raises(CatalogError) as error:
        verify_git_object_structure(store.connection, obj)
    assert error.value.code == "GIT_OBJECT_STRUCTURE"
    assert not store.one(
        "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (obj,)
    )


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_supported_hex_case_header_order_and_octal_spelling_stay_available(store, fmt):
    parser = GitParsing(store)
    tree = b"00100644 a\0" + oid(fmt, "blob", b"missing")
    tree_oid = oid(fmt, "tree", tree)
    tree_id = parser.install_object(fmt, tree_oid, "tree", tree)
    parent = oid(fmt, "commit", b"absent")
    commit = (
        b"author Test <t@example.invalid> 1 +0000\ntree "
        + tree_oid.hex().upper().encode()
        + b"\nparent "
        + parent.hex().upper().encode()
        + b"\n\nmessage"
    )
    commit_id = parser.install_object(fmt, oid(fmt, "commit", commit), "commit", commit)
    tag = (
        b"type tree\ntag test\nobject "
        + tree_oid.hex().upper().encode()
        + b"\n\nmessage"
    )
    tag_id = parser.install_object(fmt, oid(fmt, "tag", tag), "tag", tag)
    assert store.one("SELECT tree_oid FROM commits")[0] == tree_oid
    assert store.one("SELECT parent_oid FROM commit_parents")[0] == parent
    assert store.one("SELECT target_oid FROM tag_objects")[0] == tree_oid
    for obj in (tree_id, commit_id, tag_id):
        assert store.one(
            "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (obj,)
        )
        assert verify_git_object_structure(store.connection, obj)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_raw_mapping_requires_actual_canonical_oid_without_trusting_verified_flag(
    store, fmt
):
    body = b"genuine physical bytes"
    with pytest.raises(sqlite3.IntegrityError, match="identity mismatch"):
        raw_object(
            store, fmt, "blob", body, declared_oid=b"x" * (20 if fmt == "sha1" else 32)
        )
    assert store.one("SELECT count(*) FROM git_object_payloads")[0] == 0
    assert store.one("SELECT count(*) FROM available_git_objects")[0] == 0


def test_physical_damage_is_unavailable_before_a_quarantine_scan(store):
    raw = b"genuine"
    obj = GitParsing(store).install_object(
        "sha1", oid("sha1", "blob", raw), "blob", raw
    )
    trigger = store.one(
        "SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'"
    )[0]
    with store.transaction():
        store.execute("DROP TRIGGER stored_bytes_immutable")
        store.execute(
            "UPDATE stored_bytes SET body=? WHERE sha256=?",
            (b"damaged", hashlib.sha256(raw).digest()),
        )
        store.execute(trigger)
    assert not store.one("SELECT 1 FROM payload_quarantine")
    assert not store.one(
        "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (obj,)
    )


@pytest.mark.parametrize("mismatch", ["name", "type", "peeled"])
def test_completion_and_readers_require_the_same_exact_ref_capture(store, mismatch):
    store.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'test','{}')",
        (OWNER,),
    )
    raw, name = b"blob", b"refs/tags/test"
    target = oid("sha1", "blob", raw)
    refs = [
        dict(
            name=name.decode(),
            name_b64=base64.b64encode(name).decode(),
            oid=target.hex(),
            type="blob",
            peeled=None,
        )
    ]
    store.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,request,roots_manifest) VALUES('capture',?,'sha1','git','{}',?)",
        (OWNER, json.dumps(refs)),
    )
    GitParsing(store, OWNER).install_object(
        "sha1", target, "blob", raw, acquisition="capture"
    )
    store.execute(
        "INSERT INTO snapshots(snapshot_id,git_acquisition_id,repository_uuidv4,complete,generation) VALUES('snapshot','capture',?,0,0)",
        (OWNER,),
    )
    store.execute(
        "INSERT INTO ref_observations(repository_uuidv4,snapshot_id,raw_ref_name,kind,object_format,target_oid,peeled_oid,target_type) VALUES(?,'snapshot',?,'tag','sha1',?,?,?)",
        (
            OWNER,
            b"refs/tags/other" if mismatch == "name" else name,
            target,
            target if mismatch == "peeled" else None,
            "tree" if mismatch == "type" else "blob",
        ),
    )
    with pytest.raises(sqlite3.IntegrityError, match="closure incomplete"):
        store.execute("UPDATE snapshots SET complete=1 WHERE snapshot_id='snapshot'")
    assert not store.one(
        "SELECT 1 FROM valid_ref_captures WHERE snapshot_id='snapshot'"
    )
    # Readers also reject a corrupted complete flag independently of admission.
    trigger = store.one(
        "SELECT sql FROM sqlite_schema WHERE name='snapshots_complete_update'"
    )[0]
    with store.transaction():
        store.execute("DROP TRIGGER snapshots_complete_update")
        store.execute("UPDATE snapshots SET complete=1 WHERE snapshot_id='snapshot'")
        store.execute(trigger)
    assert not store.one(
        "SELECT 1 FROM available_snapshots WHERE snapshot_id='snapshot'"
    )
    assert not store.one("SELECT 1 FROM current_snapshots WHERE snapshot_id='snapshot'")


@pytest.mark.parametrize("reverse", [False, True])
def test_invalid_decoder_claim_cannot_replace_valid_candidate_in_either_order(
    store, tmp_path, reverse
):
    store.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'test','{}')",
        (OWNER,),
    )
    store.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,request,roots_manifest) VALUES('capture',?,'sha1','pr','{}','[]')",
        (OWNER,),
    )
    raw = b"actual text"
    GitParsing(store, OWNER).install_object(
        "sha1", oid("sha1", "blob", raw), "blob", raw, acquisition="capture"
    )
    original = Graph(store.connection).export(OWNER)
    forged = copy.deepcopy(original)
    fact = next(
        record for record in forged["records"] if record["table"] == "git_text_facts"
    )
    fact["values"]["raw_text"] = "forged interpretation"
    target_path = tmp_path / "target"
    target_path.mkdir()
    with runtime(target_path) as target:
        graph = Graph(target.connection)
        rejected = []
        for unit in (forged, original) if reverse else (original, forged):
            rejected.append(graph.receive(unit)["rejected_records"])
        graph.receive(original)
        assert target.one("SELECT count(*) FROM available_git_objects")[0] == 1
        assert target.one("SELECT raw_text FROM git_text_facts")[0] == "actual text"
        assert target.one("SELECT count(*) FROM git_text_facts")[0] == 1
        obj = target.one("SELECT git_object_id FROM git_objects")[0]
        assert not decoded_fact(target, obj, "blob")["decoder_conflict"]
        assert sum(rejected) == 1
        assert not target.one("SELECT 1 FROM exchange_staging")


@pytest.mark.parametrize("width", [2, 2048])
def test_closure_hashes_each_exact_source_once_and_ignores_unrelated_objects(
    store, width
):
    store.execute(
        "INSERT INTO repositories(repository_uuidv4,name,metadata) VALUES(?,'test','{}')",
        (OWNER,),
    )
    body = b"actual blob"
    blob = oid("sha1", "blob", body)
    tree = b"".join(b"100644 q%04d\0" % n + blob for n in range(width))
    tree_oid = oid("sha1", "tree", tree)
    name = b"refs/tags/tree"
    refs = [
        dict(
            name=name.decode(),
            name_b64=base64.b64encode(name).decode(),
            oid=tree_oid.hex(),
            type="tree",
            peeled=None,
        )
    ]
    store.execute(
        "INSERT INTO git_acquisitions(git_acquisition_id,repository_uuidv4,object_format,kind,request,roots_manifest) VALUES('capture',?,'sha1','git','{}',?)",
        (OWNER, json.dumps(refs)),
    )
    parser = GitParsing(store, OWNER)
    parser.install_object("sha1", blob, "blob", body, acquisition="capture")
    parser.install_object("sha1", tree_oid, "tree", tree, acquisition="capture")
    for n in range(128):
        unrelated = b"unrelated %d" % n
        parser.install_object("sha1", oid("sha1", "blob", unrelated), "blob", unrelated)
    calls = {}

    def identity(*args):
        calls[args[1]] = calls.get(args[1], 0) + 1
        return _git_object_identity_valid(*args)

    store.connection.create_function(
        "repo_catalog_git_object_identity_valid", 6, identity, deterministic=True
    )
    assert store.one(
        "SELECT 1 FROM available_git_acquisitions WHERE git_acquisition_id='capture'"
    )
    assert calls == {blob.hex().upper(): 1, tree_oid.hex().upper(): 1}


def test_same_length_content_map_cannot_contradict_canonical_blob_digests(store):
    parser = GitParsing(store)
    genuine = parser.install_object("sha1", oid("sha1", "blob", b"abc"), "blob", b"abc")
    cid = store.one(
        "SELECT content_id FROM blob_content_map WHERE git_object_id=?", (genuine,)
    )[0]
    forged = raw_object(store, "sha1", "blob", b"xyz")
    store.execute("INSERT INTO blob_content_map VALUES(?,?)", (forged, cid))
    with pytest.raises(CatalogError, match="Blob content digest contradicts"):
        verify_git_object_structure(store.connection, forged)
    assert not store.one(
        "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (forged,)
    )
    assert store.one(
        "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (genuine,)
    )
