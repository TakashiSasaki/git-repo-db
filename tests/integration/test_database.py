import sqlite3

import pytest

from repo_catalog.adapters.filesystem.capacity import Capacity
from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.sqlite.schema import SCHEMA_VERSION
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.job_service import JobService
from repo_catalog.application.maintenance_service import MaintenanceService
from repo_catalog.domain.models import Waiting


@pytest.fixture
def state(tmp_path):
    p = tmp_path / "state"
    MaintenanceService(p).init("catalog-text-v1", 32 * 1024 * 1024, 0)
    return p


def test_runtime_journal(state):
    with Store(state) as s:
        assert s.one("PRAGMA journal_mode")[0] == "delete"
        assert s.one("PRAGMA synchronous")[0] == 3
        assert s.one("PRAGMA foreign_keys")[0] == 1


def test_constraints_and_transaction_atomicity(state):
    with Store(state) as s:
        original = s.revision()
        with pytest.raises(sqlite3.IntegrityError):
            with s.transaction():
                s.execute(
                    "INSERT INTO git_objects(object_format,oid,type,size,verified) VALUES('sha1',?,'blob',0,1)",
                    (b"bad",),
                )
        with pytest.raises(sqlite3.OperationalError), s.transaction():
            s.execute("CREATE TABLE rolled_back(x TEXT) STRICT")
            s.execute("UPDATE database_identity SET local_revision=999")
            s.execute("THIS IS NOT SQL")
        assert s.one("SELECT name FROM sqlite_master WHERE name='rolled_back'") is None
        assert (
            s.one("SELECT schema_version FROM database_identity")[0] == SCHEMA_VERSION
        )
        assert s.revision() == original
    with Store(state, readonly=True) as s, pytest.raises(sqlite3.OperationalError):
        s.advance_local_revision()


def test_writer_and_capacity(state):
    with FileLock(state / "locks/writer.lock"), pytest.raises(Waiting):
        with FileLock(state / "locks/writer.lock"):
            pass
    with Store(state) as s:
        job = JobService(s).create("sync", {})
        with pytest.raises(Waiting):
            Capacity(s).reserve(job, 33 * 1024 * 1024)
        assert s.one("SELECT count(*) FROM space_reservations")[0] == 0


def test_full_rollback(state):
    with Store(state) as s:
        old = s.revision()
        pages = s.one("PRAGMA page_count")[0]
        s.execute(f"PRAGMA max_page_count={pages + 1}")
        with pytest.raises(sqlite3.OperationalError):
            with s.transaction():
                s.execute(
                    "INSERT INTO stored_bytes(sha256,body,byte_length) VALUES(?,?,?)",
                    (b"x" * 32, b"x" * 1048576, 1048576),
                )
                s.advance_local_revision()
        assert s.revision() == old and not s.connection.in_transaction
