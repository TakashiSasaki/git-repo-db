"""Exact malformed grammar and supported native byte spellings from old readers."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_repository import (
    OID,
    RelationGroup,
    RelationMember,
    RepositoryFailure,
)
from tests.integration.p1.test_repository import Budget, native, oid, provenance
from tests.integration.p2.conftest import repository_store as repository_store
from tests.integration.p2.test_native import commit_body, entry, git, repository, write

__all__ = ["repository"]


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
    ],
)
def test_hash_matching_malformed_native_shapes_never_publish_partial_authority(
    repository_store, fmt, attack
):
    store, path, _ = repository_store
    target = oid("a", fmt)
    if attack.startswith("tree-"):
        name = {"tree-dot": b".", "tree-dotdot": b"..", "tree-slash": b"dir/file"}[
            attack
        ]
        kind, body = "tree", entry(b"100644", name, target)
    elif attack in {"duplicate-tree", "bare-header"}:
        kind = "commit"
        body = commit_body(target)
        if attack == "duplicate-tree":
            body = body.replace(
                b"\nauthor ", b"\ntree " + target.object_oid.encode() + b"\nauthor ", 1
            )
        else:
            body = body.replace(b"\n\n", b"\nmalformed\n\n", 1)
    else:
        kind = "tag"
        body = (
            b"object "
            + target.object_oid.encode()
            + b"\ntype blob\ntag test\n\nmessage"
        )
        body = (
            body.replace(b"type blob", b"type blob-extra")
            if attack == "tag-type-prefix"
            else body.replace(b"\n\n", b"\n", 1)
        )
    incoming = native(kind, body, fmt)
    incoming.validate()  # Its canonical hash, byte size and digest all agree.
    with pytest.raises(RepositoryFailure) as error:
        store.admit_metadata(incoming, str(uuid4()), Budget())
    assert error.value.code == "NATIVE_SYNTAX"
    for table in (
        "git_objects",
        "retained_metadata",
        "scalar_claims",
        "relation_groups",
        "intrinsic_claims",
        "intrinsic_groups",
    ):
        assert store.sql(f"SELECT count(*) FROM {table}")[0][0] == 0
    assert not (path.parent / "p1-recovery-stop.json").exists()
    store.admit_metadata(native("tree", b"", fmt), str(uuid4()), Budget())


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_checked_tag_target_must_match_raw_initial_identity_not_recorded_copy(
    repository_store, fmt
):
    store, path, _ = repository_store
    target, unrelated = oid("a", fmt), oid("b", fmt)
    body = b"object " + target.object_oid.encode() + b"\ntype blob\ntag test\n\nmessage"
    incoming = native("tag", body, fmt)
    physical = str(uuid4())
    store.admit_metadata(incoming, physical, Budget())
    store.admit_object(unrelated)
    forged = RelationGroup(
        incoming.object_oid,
        "tag_target",
        "false-copy",
        "complete",
        (RelationMember(0, unrelated),),
        replace(provenance(), qualification="receiver_intrinsic"),
    )
    with closing(connect(path, "repository")) as db:
        db.execute("BEGIN")
        db.execute("INSERT INTO relation_groups VALUES(?,?,?,?,?,?,?)", forged.key)
        with pytest.raises(sqlite3.IntegrityError, match="checked intrinsic scope"):
            db.execute(
                "INSERT INTO intrinsic_groups VALUES(?,?,?,?,?,?,?,?)",
                (*forged.key, physical),
            )
        db.rollback()
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert store.relations(incoming.object_oid, "tag_target").canonical == [
        "complete",
        [[0, *target.key]],
    ]
    assert store.read_metadata(incoming.object_oid) == body


@pytest.mark.parametrize("kind", ["commit", "tag"])
def test_actual_git_uppercase_header_oid_preserves_bytes_and_canonical_target(
    repository_store, repository, kind
):
    store, _, _ = repository_store
    path, fmt = repository
    tree = write(path, fmt, "tree", b"")
    upper = tree.object_oid.object_oid.upper().encode()
    # Only a validated raw header spelling normalizes: public typed identity
    # coordinates retain their original strict canonical input contract.
    with pytest.raises(RepositoryFailure) as error:
        OID(fmt, upper.decode())
    assert error.value.code == "IDENTITY"
    if kind == "commit":
        body = commit_body(tree.object_oid).replace(
            tree.object_oid.object_oid.encode(), upper, 1
        )
        relation, suffix = "commit_tree", "^{tree}"
    else:
        body = b"object " + upper + b"\ntype tree\ntag uppercase\n\nmessage"
        relation, suffix = "tag_target", "^{}"
    # Git is the independent syntax/interpretation oracle, not a manual claim
    # that every byte string hash-object can write has supported native meaning.
    incoming = write(path, fmt, kind, body, literal=True)
    assert (
        git(path, "rev-parse", incoming.object_oid.object_oid + suffix).strip().decode()
        == tree.object_oid.object_oid
    )
    assert git(path, "cat-file", kind, incoming.object_oid.object_oid) == body
    store.admit_metadata(
        GitNativeSource(path).metadata(incoming.object_oid), str(uuid4()), Budget()
    )
    assert store.relations(incoming.object_oid, relation).canonical == [
        "complete",
        [[0, *tree.object_oid.key]],
    ]
    assert store.read_metadata(incoming.object_oid) == body
