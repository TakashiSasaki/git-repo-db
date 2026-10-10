"""Coherent local units roll back values, evidence and the revision together."""

import sqlite3

import pytest

from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.application.maintenance_service import MaintenanceService


@pytest.fixture
def store(tmp_path):
    state = tmp_path / "disposable"
    MaintenanceService(state).init("catalog-text-v1", 64 * 1024 * 1024, 0)
    with Store(state) as value:
        value.execute("CREATE TABLE transaction_values(value TEXT UNIQUE)")
        yield value


def test_caught_nested_failure_does_not_commit_partial_unit(store):
    with store.transaction():
        store.execute("INSERT INTO transaction_values VALUES('outer')")
        with pytest.raises(sqlite3.IntegrityError):
            with store.transaction():
                store.execute("INSERT INTO transaction_values VALUES('inner')")
                store.advance_local_revision()
                store.execute("INSERT INTO transaction_values VALUES('outer')")
        store.execute("INSERT INTO transaction_values VALUES('after')")
    assert [row[0] for row in store.all("SELECT value FROM transaction_values")] == [
        "outer",
        "after",
    ]
    assert store.revision()["local_revision"] == 0


def test_failed_commit_rolls_back_values_and_revision(store):
    store.execute("CREATE TABLE transaction_parents(id INTEGER PRIMARY KEY)")
    store.execute(
        "CREATE TABLE transaction_children(parent INTEGER REFERENCES "
        "transaction_parents(id) DEFERRABLE INITIALLY DEFERRED)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        with store.transaction():
            store.execute("INSERT INTO transaction_values VALUES('uncommitted')")
            store.execute("INSERT INTO transaction_children VALUES(1)")
            store.advance_local_revision()
    assert not store.connection.in_transaction
    assert store.all("SELECT * FROM transaction_values") == []
    assert store.all("SELECT * FROM transaction_children") == []
    assert store.revision()["local_revision"] == 0


def test_rollback_cleanup_error_preserves_original_failure(store, monkeypatch):
    execute = store.execute

    def fail_cleanup(sql, args=()):
        if sql == "ROLLBACK":
            raise sqlite3.OperationalError("injected cleanup failure")
        return execute(sql, args)

    monkeypatch.setattr(store, "execute", fail_cleanup)
    with pytest.raises(ValueError, match="original evidence failure") as failure:
        with store.transaction():
            store.execute("INSERT INTO transaction_values VALUES('value')")
            store.advance_local_revision()
            raise ValueError("original evidence failure")
    assert failure.value.__notes__ == ["Transaction cleanup failed: OperationalError"]
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        execute("COMMIT")
    with Store(store.path) as reopened:
        assert reopened.all("SELECT * FROM transaction_values") == []
        assert reopened.revision()["local_revision"] == 0


def test_nested_read_uses_same_snapshot_and_does_not_end_outer_unit(store):
    with store.transaction():
        store.execute("INSERT INTO transaction_values VALUES('coherent')")
        with store.transaction(read=True):
            assert store.one("SELECT value FROM transaction_values")[0] == "coherent"
        assert store.connection.in_transaction
    assert not store.connection.in_transaction


def test_nested_cleanup_failure_cannot_mask_original_or_commit_outer(
    store, monkeypatch
):
    execute = store.execute

    def fail_cleanup(sql, args=()):
        if sql.startswith("ROLLBACK TO "):
            raise sqlite3.OperationalError("injected savepoint cleanup failure")
        return execute(sql, args)

    monkeypatch.setattr(store, "execute", fail_cleanup)
    with pytest.raises(ValueError, match="original resource failure") as failure:
        with store.transaction():
            store.execute("INSERT INTO transaction_values VALUES('outer')")
            with store.transaction():
                store.execute("INSERT INTO transaction_values VALUES('inner')")
                store.advance_local_revision()
                raise ValueError("original resource failure")
    assert any("OperationalError" in note for note in failure.value.__notes__)
    with Store(store.path) as reopened:
        assert reopened.all("SELECT * FROM transaction_values") == []
        assert reopened.revision()["local_revision"] == 0
