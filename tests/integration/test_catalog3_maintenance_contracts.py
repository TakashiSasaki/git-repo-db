"""Full maintenance checks independently validate Git identity above physical CAS."""

import hashlib
import sqlite3

import pytest

from repo_catalog.adapters.sqlite.cas_integrity import verify_all
from repo_catalog.adapters.sqlite.payloads import intern_payload
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.catalog_validation import check_catalog
from repo_catalog.application.maintenance_service import MaintenanceService


@pytest.mark.parametrize("forged", [False, True], ids=["exact-oid", "forged-oid"])
def test_full_check_detects_wrong_git_identity_with_valid_physical_bytes(
    tmp_path, forged
):
    state = tmp_path / "state"
    MaintenanceService(state).init("catalog-text-v1", 32 * 1024 * 1024, 0)
    body = b"hello"
    oid = hashlib.sha1(b"blob 5\0" + body).digest()
    with Store(state) as store, store.transaction():
        ref = intern_payload(store.connection, body, representation="git-object-raw-v1")
        obj = store.execute(
            "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'blob',5,1)",
            (b"x" * 20 if forged else oid,),
        ).lastrowid
        mapping = "INSERT INTO git_object_payloads VALUES(?,?,?)"
        if forged:
            # Actual DDL rejects this identity before it can become a mapping.
            with pytest.raises(sqlite3.IntegrityError, match="identity mismatch"):
                store.execute(mapping, (obj, *ref.parameters()))
            assert not store.one(
                "SELECT 1 FROM git_object_payloads WHERE git_object_id=?", (obj,)
            )
            # Retained-data fault injection is separate from normal admission:
            # restore the guard before testing independent full maintenance.
            guard = store.one(
                "SELECT sql FROM sqlite_schema WHERE name='git_object_payloads_identity'"
            )[0]
            store.execute("DROP TRIGGER git_object_payloads_identity")
            store.execute(mapping, (obj, *ref.parameters()))
            store.execute(guard)
        else:
            store.execute(mapping, (obj, *ref.parameters()))
    with Store(state) as store:
        assert verify_all(store.connection, diagnose=False)["unexplained"] == []
        assert check_catalog(store) == []
        assert check_catalog(store, full=True) == (
            [{"code": "GIT_OBJECT_IDENTITY", "git_object_id": obj}] if forged else []
        )
        assert not store.all("PRAGMA foreign_key_check")
        assert store.one("PRAGMA integrity_check")[0] == "ok"
