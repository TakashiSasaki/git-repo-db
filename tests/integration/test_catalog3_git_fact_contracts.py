"""Integrity contracts for directly owned Git objects and decoder candidates."""

import hashlib
import shutil
import sqlite3
import uuid

import pytest

from repo_catalog.adapters.git.parsing import GitParsing, reparse_git
from repo_catalog.adapters.sqlite.cas_integrity import (
    diagnose_corruption,
    repair_payload,
)
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.application.git_query_context import decoded_fact
from repo_catalog.domain.models import CatalogError
from tests.integration.test_catalog3_git_runtime import collect, register, runtime
from tests.support.git_fixture import FixtureRepo


def fixture(tmp_path):
    remote = FixtureRepo(tmp_path / "remote.git")
    remote.commit("A", {b"a.txt": b"immutable raw input"})
    remote.ref("refs/heads/main", "A")
    return remote


def test_offline_git_reanalysis_preserves_captures_and_verified_byte_identities(
    tmp_path,
):
    remote = fixture(tmp_path)
    with runtime(tmp_path) as store:
        repo = register(store, remote.url)
        acquired = collect(store, repo)
        tables = (
            "git_acquisitions",
            "git_objects",
            "git_object_payloads",
            "stored_bytes",
            "snapshots",
            "ref_observations",
        )
        before = {
            table: [tuple(row) for row in store.all(f"SELECT * FROM {table}")]
            for table in tables
        }
        shutil.rmtree(store.path / "cache")
        result = reparse_git(
            store, acquired["git_acquisition_id"], text_encoding="latin-1"
        )
        assert result["decoded_objects"] > 0
        for table, rows in before.items():
            assert [tuple(row) for row in store.all(f"SELECT * FROM {table}")] == rows
        assert (
            store.one("SELECT snapshot_id FROM current_snapshots")[0]
            == acquired["snapshot_id"]
        )
        assert not store.all("PRAGMA foreign_key_check")


@pytest.mark.parametrize(
    "attack", ["late", "update", "delete", "replace", "null", "other-object"]
)
def test_direct_git_decoded_values_reject_identity_reinterpretation(tmp_path, attack):
    with runtime(tmp_path) as store:
        parser = GitParsing(store)
        body = b"immutable"
        obj_id = parser.install_object(
            "sha1", hashlib.sha1(b"blob 9\0" + body).digest(), "blob", body
        )
        original = dict(store.one("SELECT * FROM git_text_facts"))
        with pytest.raises(sqlite3.IntegrityError):
            if attack == "update":
                store.execute("UPDATE git_text_facts SET raw_text='changed'")
            elif attack == "delete":
                store.execute("DELETE FROM git_text_facts")
            else:
                values = dict(original)
                values["git_fact_uuidv4"] = str(uuid.uuid4())
                if attack == "null":
                    values["git_object_id"] = None
                elif attack == "other-object":
                    values["git_object_id"] = -1
                elif attack == "replace":
                    values["raw_text"] = "changed"
                store.execute(
                    ("INSERT OR REPLACE" if attack == "replace" else "INSERT")
                    + f" INTO git_text_facts({','.join(values)}) VALUES({','.join('?' for _ in values)})",
                    tuple(values.values()),
                )
        assert dict(store.one("SELECT * FROM git_text_facts")) == original
        assert decoded_fact(store, obj_id, "blob")["fact"]["raw_text"] == "immutable"


def test_quarantine_disables_affected_git_bytes_and_reanalysis_until_real_repair(
    tmp_path,
):
    remote = fixture(tmp_path)
    with runtime(tmp_path) as store:
        repo = register(store, remote.url)
        original = collect(store, repo)
        parser = GitParsing(store)
        unrelated = b"unrelated"
        other_id = parser.install_object(
            "sha1", hashlib.sha1(b"blob 9\0" + unrelated).digest(), "blob", unrelated
        )
        physical = store.one(
            "SELECT g.git_object_id,p.payload_sha256,s.body FROM git_object_payloads p JOIN stored_bytes s ON s.sha256=p.payload_sha256 JOIN git_objects g USING(git_object_id) WHERE g.type='blob' AND s.body=?",
            (b"immutable raw input",),
        )
        obj_id, digest, raw = physical
        trigger = store.one(
            "SELECT sql FROM sqlite_schema WHERE name='stored_bytes_immutable'"
        )[0]
        store.execute("DROP TRIGGER stored_bytes_immutable")
        store.execute(
            "UPDATE stored_bytes SET body=? WHERE sha256=?", (b"x" * len(raw), digest)
        )
        store.execute(trigger)
        diagnose_corruption(store.connection, digest)
        assert not store.one("SELECT 1 FROM current_snapshots")
        assert decoded_fact(store, obj_id, "blob")["fact"] is None
        assert decoded_fact(store, other_id, "blob")["fact"]["raw_text"] == "unrelated"
        with pytest.raises(CatalogError, match="Quarantined"):
            reparse_git(store, original["git_acquisition_id"])
        repair_payload(store.connection, digest, raw)
        assert store.one("SELECT count(*) FROM current_snapshots")[0] == 1
        assert decoded_fact(store, obj_id, "blob")["fact"]["raw_text"] == raw.decode()


def test_partial_intrinsic_tree_rows_are_unavailable_without_any_acquisition_seal(
    tmp_path,
):
    # This deliberately emulates an old/interrupted normalized transfer prefix.
    # Readers must detect the actual missing structural suffix.
    with runtime(tmp_path) as store:
        child = hashlib.sha1(b"blob 7\0missing").digest()
        raw = b"100644 a\0" + child + b"100644 b\0" + child
        reference = intern_payload(
            store.connection, raw, representation="git-object-raw-v1"
        )
        obj_id = store.execute(
            "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'tree',?,1)",
            (hashlib.sha1(f"tree {len(raw)}\0".encode() + raw).digest(), len(raw)),
        ).lastrowid
        store.execute(
            "INSERT INTO git_object_payloads VALUES(?,?,?)",
            (obj_id, reference.representation, reference.sha256),
        )
        store.execute("INSERT INTO tree_objects VALUES(?,2)", (obj_id,))
        store.execute(
            "INSERT INTO tree_entries(tree_git_object_id,raw_name,entry_offset,entry_length,mode,child_format,child_oid,child_git_object_id) VALUES(?,X'61',0,29,33188,'sha1',?,NULL)",
            (obj_id, child),
        )
        assert not store.one(
            "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (obj_id,)
        )
        assert not store.one(
            "SELECT 1 FROM sqlite_schema WHERE name='git_acquisition_publications'"
        )
        GitParsing(store).parse_object(
            store.one("SELECT * FROM git_objects WHERE git_object_id=?", (obj_id,)), raw
        )
        assert store.one(
            "SELECT 1 FROM available_git_objects WHERE git_object_id=?", (obj_id,)
        )
        assert not store.all("PRAGMA foreign_key_check")
