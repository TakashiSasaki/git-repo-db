"""A real SQLITE_FULL never leaves half-admitted metadata in current Repository."""

import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_repository import RepositoryStore
from repo_catalog.domain.p1_repository import ScalarClaim
from tests.integration.p1.test_repository import (
    Budget,
    native,
    oid,
    provenance,
    repository_store,
)

__all__ = ["repository_store"]


def page_limit(owner, value=None):
    # Fault injection configures the disposable raw writer before admission.
    # The normal Repository authorizer is restored before any product work runs.
    owner._db.set_authorizer(None)
    try:
        if value is None:
            value = owner._db.execute("PRAGMA page_count").fetchone()[0] + 1
        owner._db.execute(f"PRAGMA max_page_count={value}")
    finally:
        owner._db.set_authorizer(owner._authorize)


def test_actual_sqlite_full_preserves_prior_claim_and_rolls_back_native_unit(
    repository_store,
):
    owner, path, _ = repository_store
    original = ScalarClaim(oid("a"), "type", "commit", provenance())
    owner.admit_claim(original)
    before = owner.sql("SELECT * FROM git_objects")
    page_limit(owner)
    body = (
        f"tree {oid('b').object_oid}\nauthor A <a@invalid> 0 +0000\n"
        "committer A <a@invalid> 0 +0000\n\n"
    ).encode() + b"actual permitted commit message\n" * 65536
    attempted = native("commit", body)
    with pytest.raises(Exception) as raised:
        owner.admit_metadata(attempted, str(uuid4()), Budget())
    pending, seen, full = [raised.value], set(), False
    while pending:
        error = pending.pop()
        if id(error) in seen:
            continue
        seen.add(id(error))
        if isinstance(error, sqlite3.Error):
            full |= getattr(error, "sqlite_errorcode", -1) & 255 == sqlite3.SQLITE_FULL
        for name in ("__cause__", "__context__", "cause"):
            cause = getattr(error, name, None)
            if isinstance(cause, BaseException):
                pending.append(cause)
    assert full, raised.value
    reopened = RepositoryStore(path)
    try:
        assert reopened.sql("SELECT * FROM git_objects") == before
        assert reopened.scalar(oid("a"), "type").alternatives
        assert reopened.sql("SELECT * FROM retained_metadata") == []
        assert reopened.sql("SELECT * FROM intrinsic_claims") == []
        assert not reopened._db.in_transaction
        page_limit(reopened, 2147483646)
        reopened.admit_object(oid("c"))
        assert oid("c").key in {
            tuple(row) for row in reopened.sql("SELECT * FROM git_objects")
        }
    finally:
        reopened.close()
    assert not (path.parent / "p1-recovery-stop.json").exists()
