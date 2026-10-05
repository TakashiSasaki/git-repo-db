import sqlite3

import pytest

from repo_catalog.adapters.filesystem.capacity import Capacity
from repo_catalog.adapters.filesystem.locks import FileLock
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


def test_constraints_migration_atomicity(state):
    with Store(state) as s:
        with pytest.raises(sqlite3.IntegrityError):
            with s.transaction():
                s.execute(
                    "INSERT INTO git_objects(object_format,oid,type,size) VALUES('sha1',?,'blob',0)",
                    (b"bad",),
                )
        with pytest.raises(sqlite3.OperationalError), s.transaction():
            s.execute("CREATE TABLE rolled_back(x TEXT) STRICT")
            s.execute("UPDATE catalog_meta SET schema_version=999")
            s.execute("THIS IS NOT SQL")
        assert s.one("SELECT name FROM sqlite_master WHERE name='rolled_back'") is None
        assert s.one("SELECT schema_version FROM catalog_meta")[0] == 2
    with Store(state, readonly=True) as s, pytest.raises(sqlite3.OperationalError):
        s.publish()


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
                    "INSERT INTO contents(byte_length,raw_text,text_state,created_at) VALUES(?,?,?,?)",
                    (1048576, "x" * 1048576, "eligible", "fixture"),
                )
                s.publish()
        assert s.revision() == old and not s.connection.in_transaction
