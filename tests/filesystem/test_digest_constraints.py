"""Exact Filesystem SHA-256 admission on the product's SQLite connection."""

import hashlib
import os
import sqlite3

import pytest

from repo_catalog.filesystem import FilesystemCatalog
from repo_catalog.filesystem.models import occurrence_uuid

EMPTY_DIGEST = hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize(
    "digest",
    [
        pytest.param("", id="empty"),
        pytest.param("a" * 63, id="short"),
        pytest.param("a" * 65, id="long"),
        pytest.param("g" * 64, id="nonhex"),
        pytest.param("A" * 64, id="uppercase"),
        pytest.param("a" * 64 + "\n", id="newline"),
        pytest.param("a" * 64 + "\0", id="trailing-nul"),
        pytest.param("a" * 64 + "\0invalid", id="nul-and-suffix"),
        pytest.param("a" * 63 + "\0", id="64-byte-nul"),
        pytest.param("a" * 32 + "\0" + "a" * 31, id="interior-64-byte-nul"),
        pytest.param("a" * 62 + "\u00e9", id="nonascii-64-bytes"),
    ],
)
def test_filesystem_digest_check_rejects_malformed_text(tmp_path, digest):
    database = tmp_path / "files.db"
    with FilesystemCatalog.initialize(database) as catalog:
        scan = occurrence_uuid()
        with catalog._db:
            catalog._db.execute(
                "INSERT INTO scans VALUES (?,?,?,?,?)",
                (catalog.namespace_uuid, scan, os.fsencode(tmp_path), 1, "[]"),
            )
        # Private SQL is used deliberately to exercise the DDL boundary;
        # public scan() generates real hashlib.hexdigest() values instead.
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            with catalog._db:
                catalog._db.execute(
                    "INSERT INTO entries "
                    "(namespace_uuid,scan_uuid,relative_path,kind,size,"
                    "sha256,hash_status) "
                    "VALUES (?,?,?,'file',0,?,'complete')",
                    (catalog.namespace_uuid, scan, b"candidate", digest),
                )
        assert catalog._db.execute("SELECT count(*) FROM entries").fetchone()[0] == 0
        assert catalog.verify()["integrity"] == "ok"


def test_filesystem_digest_check_accepts_valid_text_and_nullable_nonfile(tmp_path):
    database = tmp_path / "files.db"
    with FilesystemCatalog.initialize(database) as catalog:
        scan = occurrence_uuid()
        with catalog._db:
            catalog._db.execute(
                "INSERT INTO scans VALUES (?,?,?,?,?)",
                (catalog.namespace_uuid, scan, os.fsencode(tmp_path), 1, "[]"),
            )
            catalog._db.execute(
                "INSERT INTO entries "
                "(namespace_uuid,scan_uuid,relative_path,kind,size,"
                "sha256,hash_status) "
                "VALUES (?,?,?,'file',0,?,'complete')",
                (catalog.namespace_uuid, scan, b"file", EMPTY_DIGEST),
            )
            catalog._db.execute(
                "INSERT INTO entries "
                "(namespace_uuid,scan_uuid,relative_path,kind,hash_status) "
                "VALUES (?,?,?,'directory','not-applicable')",
                (catalog.namespace_uuid, scan, b""),
            )
            catalog._db.execute(
                "INSERT INTO scan_outcomes VALUES (?,?,?,?,?,?)",
                (catalog.namespace_uuid, scan, 2, "complete", 2, 0),
            )
        rows = {e.relative_path: e for e in catalog.iter_entries(scan)}
        assert rows[b"file"].sha256 == EMPTY_DIGEST
        assert rows[b""].sha256 is None
        assert catalog.verify()["integrity"] == "ok"

    with FilesystemCatalog.open(database, readonly=True) as reopened:
        assert reopened.verify()["integrity"] == "ok"
