"""Actual opt-in registry APIs; requires the real supported SQLite binding.

No committed test patches the minimum SQLite requirement. These tests do not
claim network authorization, a complete Access implementation, or P7 recovery.
"""

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from repo_catalog.adapters.sqlite import access_schema as schema
from repo_catalog.adapters.sqlite.access_registry import AccessRegistry
from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    AccessScope,
    ScopeLocatorRegistration,
)

S1 = "550e8400-e29b-41d4-a716-446655440000"
S2 = "650e8400-e29b-41d4-a716-446655440000"


def reg(stamp=1, uri="file:///srv/a", scope=S1):
    return ScopeLocatorRegistration(scope, stamp, uri)


@pytest.fixture
def path(tmp_path):
    target = tmp_path / "access.sqlite3"
    schema.initialize(target)
    with AccessRegistry(target, writable=True) as store:
        store.register_scope(AccessScope(S1, "host"))
    return target


def raw(path):
    db = sqlite3.connect(path, isolation_level=None, cached_statements=0)
    schema.register_functions(db)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    return db


def test_minimum_runtime_gate_precedes_file_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(schema.sqlite3, "sqlite_version_info", (3, 46, 1))
    with pytest.raises(AccessRegistryError, match="SQLITE_RUNTIME"):
        schema.initialize(tmp_path / "absent.sqlite3")
    assert list(tmp_path.iterdir()) == []


def test_schema_identity_and_direct_key(path):
    db = raw(path)
    try:
        assert schema.schema_rows(db) == schema.expected_schema()
        assert db.execute("SELECT * FROM access_identity").fetchall() == [
            ("access", schema.FORMAT, 1, schema.fingerprint())
        ]
        tables = [
            r
            for r in db.execute("PRAGMA table_list")
            if r[2] == "table" and not r[1].startswith("sqlite_")
        ]
        assert sorted(r[1] for r in tables) == sorted(schema.TABLES)
        assert all(r[4:] == (1, 1) for r in tables)
        columns = list(db.execute("PRAGMA table_xinfo(scope_locators)"))
        assert [(r[1], r[5]) for r in columns] == [
            ("scope_uuidv4", 1),
            ("registered_at_us", 2),
            ("scope_locator_uri", 3),
        ]
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        db.close()


def test_no_context_or_repository_seed_dependency(path):
    assert sorted(p.name for p in path.parent.iterdir()) == ["access.sqlite3"]
    with AccessRegistry(path, writable=True) as store:
        assert store.register_scope(AccessScope(S2, "host")) == "insert"
        assert store.scope(S1).display_name == store.scope(S2).display_name
        assert store.first_choices(S1) == ()


def test_history_a_b_a_and_original_replay(path):
    registrations = (reg(1), reg(2, "file:///srv/b"), reg(3))
    with AccessRegistry(path, writable=True) as store:
        for item in registrations:
            assert store.register_locator(item).status == "insert"
        assert store.register_locator(registrations[0]).status == "duplicate"
        assert store.first_choices(S1) == (registrations[2],)
        assert store.history(S1).registrations == registrations[::-1]
        assert store.history(S1).next_cursor is None


def test_latest_before_enabled_and_no_implicit_fallback(path):
    with AccessRegistry(path, writable=True) as store:
        old, latest = reg(1), reg(2, "file:///srv/b")
        store.register_locator(old)
        store.set_locator_enabled(old, True)
        store.register_locator(latest)
        assert store.first_choices(S1) == (latest,)
        assert not store.locator_enabled(latest)
        assert store.locator_enabled(old)


def test_ties_remain_even_if_only_one_enabled(path):
    a, b = reg(10), reg(10, "file:///srv/b")
    with AccessRegistry(path, writable=True) as store:
        store.register_locator(b)
        store.register_locator(a)
        store.set_locator_enabled(a, True)
        assert store.first_choices(S1) == (a, b)
        with pytest.raises(AccessRegistryError, match="CANDIDATE_LIMIT"):
            store.first_choices(S1, max_candidates=1)


def test_earlier_time_retained_without_fake_monotonicity(path):
    with AccessRegistry(path, writable=True) as store:
        store.register_locator(reg(20))
        result = store.register_locator(reg(10, "file:///srv/b"))
        assert result.precedes_latest and result.previous_latest_us == 20
        assert store.first_choices(S1) == (reg(20),)
        assert len(store.history(S1).registrations) == 2


def test_scope_label_update_does_not_change_history(path):
    with AccessRegistry(path, writable=True) as store:
        store.register_locator(reg())
        store.rename_scope(S1, "renamed")
        assert store.scope(S1) == AccessScope(S1, "renamed")
        assert store.first_choices(S1) == (reg(),)
        assert store.register_scope(AccessScope(S1, "renamed")) == "duplicate"
        with pytest.raises(AccessRegistryError, match="SCOPE_CONFLICT"):
            store.register_scope(AccessScope(S1, "other"))


def test_replay_never_revives_disabled_or_lost_control(path):
    with AccessRegistry(path, writable=True) as store:
        store.register_locator(reg())
        store.set_locator_enabled(reg(), True)
        store.set_locator_enabled(reg(), False)
        assert store.register_locator(reg()).status == "duplicate"
        assert not store.locator_enabled(reg())
    db = raw(path)
    db.execute("DELETE FROM scope_locator_controls")
    db.close()
    with AccessRegistry(path, writable=True) as store:
        store.register_locator(reg())
        assert not store.locator_enabled(reg())
    db = raw(path)
    assert db.execute("SELECT COUNT(*) FROM scope_locator_controls").fetchone() == (0,)
    db.close()


def test_explicit_control_operation_is_not_approval(path):
    with AccessRegistry(path, writable=True) as store:
        store.register_locator(reg())
        store.set_locator_enabled(reg(), True)
        assert store.locator_enabled(reg())
        assert not hasattr(store, "approve") and not hasattr(store, "execute")
        for bad in (1, "true", None):
            with pytest.raises(AccessRegistryError, match="TYPE"):
                store.set_locator_enabled(reg(), bad)


def test_history_pagination_ties_and_scope_binding(path):
    expected = (reg(3), reg(2), reg(2, "file:///srv/b"), reg(1))
    with AccessRegistry(path, writable=True) as store:
        for item in reversed(expected):
            store.register_locator(item)
        first = store.history(S1, limit=2)
        assert first.registrations == expected[:2]
        assert first.next_cursor == expected[1]
        second = store.history(S1, limit=2, after=first.next_cursor)
        assert second.registrations == expected[2:]
        assert second.next_cursor is None
        with pytest.raises(AccessRegistryError, match="CURSOR_SCOPE"):
            store.history(S1, after=reg(scope=S2))
        with pytest.raises(AccessRegistryError, match="CURSOR"):
            store.history(S1, after=reg(99))


@pytest.mark.parametrize(
    "operation",
    [
        "UPDATE scope_locators SET registered_at_us=99",
        "DELETE FROM scope_locators",
        "INSERT OR REPLACE INTO scope_locators VALUES('%s',1,'file:///srv/a')" % S1,
        "UPDATE access_scopes SET scope_uuidv4='%s'" % S2,
        "DELETE FROM access_scopes",
        "INSERT OR REPLACE INTO access_scopes VALUES('%s','replacement')" % S1,
        "UPDATE access_identity SET ddl_sha256=printf('%064d',0)",
        "DELETE FROM access_identity",
    ],
)
def test_raw_mutation_guards(path, operation):
    with AccessRegistry(path, writable=True) as store:
        store.register_locator(reg())
    db = raw(path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(operation)
        assert db.execute("SELECT * FROM scope_locators").fetchall() == [reg().key]
    finally:
        db.close()


def test_replace_cannot_bypass_history_even_without_recursive_triggers(path):
    with AccessRegistry(path, writable=True) as store:
        store.register_locator(reg())
    db = raw(path)
    db.execute("PRAGMA recursive_triggers=OFF")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT OR REPLACE INTO scope_locators VALUES(?,?,?)", reg().key)
    db.close()


def test_full_registration_fk_and_invalid_input_constraints(path):
    db = raw(path)
    try:
        for values in (
            (S2, 1, "file:///srv/a"),
            (S1, 0, "file:///srv/a"),
            (S1, None, "file:///srv/a"),
            (S1, 1, "https://u:secret@host/env"),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("INSERT INTO scope_locators VALUES(?,?,?)", values)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO scope_locator_controls VALUES(?,?,?,1)", reg().key)
        db.execute("INSERT INTO scope_locators VALUES(?,?,?)", reg().key)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO scope_locator_controls VALUES(?,?,?,1)", reg(2).key)
    finally:
        db.close()


def test_default_handle_read_only_and_no_public_sql(path):
    with AccessRegistry(path) as store:
        assert store.scope(S1).scope_uuidv4 == S1
        with pytest.raises(AccessRegistryError, match="READ_ONLY"):
            store.register_locator(reg())
        for sql in (
            "SELECT * FROM access_scopes",
            "PRAGMA foreign_keys=OFF",
            "DELETE FROM scope_locators",
            "BEGIN",
        ):
            with pytest.raises(sqlite3.DatabaseError):
                store._db.execute(sql)
    with pytest.raises(AccessRegistryError, match="CLOSED"):
        store.scope(S1)


def test_missing_or_existing_file_is_never_implicitly_created_or_replaced(path):
    before = path.read_bytes()
    with pytest.raises(AccessRegistryError, match="EXISTS"):
        schema.initialize(path)
    with pytest.raises(AccessRegistryError, match="MISSING"):
        AccessRegistry(path.parent / "absent.sqlite3")
    assert path.read_bytes() == before
    assert not (path.parent / "absent.sqlite3").exists()


def test_wrong_format_readonly_preflight_leaves_bytes(path):
    other = path.parent / "unrelated.sqlite3"
    db = sqlite3.connect(other)
    db.execute("CREATE TABLE unrelated(x)")
    db.close()
    other.chmod(0o600)
    before = other.read_bytes()
    with pytest.raises(AccessRegistryError, match="FORMAT"):
        AccessRegistry(other, writable=True)
    assert other.read_bytes() == before
    assert not schema.stop_path(other).exists()


@pytest.mark.parametrize("kind", ["permissions", "symlink", "hardlink"])
def test_path_policy(path, kind):
    target = path
    if kind == "permissions":
        path.chmod(0o644)
    elif kind == "symlink":
        target = path.parent / "link.sqlite3"
        target.symlink_to(path)
    else:
        target = path.parent / "hardlink.sqlite3"
        os.link(path, target)
    with pytest.raises(AccessRegistryError, match="PATH"):
        AccessRegistry(target)


def test_access_stop_blocks_new_and_existing_handles_without_core_stop(path):
    with AccessRegistry(path) as store:
        schema.persist_stop(path)
        with pytest.raises(AccessRegistryError, match="STOPPED"):
            store.first_choices(S1)
    with pytest.raises(AccessRegistryError, match="STOPPED"):
        AccessRegistry(path)
    assert not (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("damage", ["label", "utf8", "registration_time"])
def test_persisted_invalid_values_stop_access_on_open(path, damage):
    with AccessRegistry(path, writable=True) as store:
        store.register_locator(reg())
    db = raw(path)
    # Privileged synthetic corruption, outside the supported write API.
    db.execute("PRAGMA ignore_check_constraints=ON")
    if damage == "label":
        db.execute("UPDATE access_scopes SET display_name=char(0)")
    elif damage == "utf8":
        db.execute("UPDATE access_scopes SET display_name=CAST(X'80' AS TEXT)")
    else:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("DROP TRIGGER scope_registration_no_update")
        db.execute("UPDATE scope_locators SET registered_at_us=0")
        sql = next(
            r[3]
            for r in schema.expected_schema()
            if r[1] == "scope_registration_no_update"
        )
        db.execute(sql)
    db.close()
    with pytest.raises(AccessRegistryError, match="CORRUPT"):
        AccessRegistry(path)
    assert schema.stop_path(path).exists()
    assert not (path.parent / "p1-recovery-stop.json").exists()


def test_persisted_invalid_utf8_stops_already_open_handle(path):
    with AccessRegistry(path) as store:
        db = raw(path)
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute("UPDATE access_scopes SET display_name=CAST(X'80' AS TEXT)")
        db.close()
        with pytest.raises(AccessRegistryError, match="CORRUPT"):
            store.scope(S1)
    assert schema.stop_path(path).exists()


def test_inode_change_detected_before_next_operation(path):
    with AccessRegistry(path) as store:
        replacement = path.parent / "replacement.sqlite3"
        schema.initialize(replacement)
        os.replace(replacement, path)
        with pytest.raises(AccessRegistryError, match="PATH_CHANGED"):
            store.scope(S1)


def test_two_handles_exact_replay_and_competing_ties(path):
    def write(item):
        with AccessRegistry(path, writable=True) as store:
            return store.register_locator(item).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(write, (reg(), reg())))
    assert sorted(statuses) == ["duplicate", "insert"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(write, (reg(2), reg(2, "file:///srv/b"))))
    with AccessRegistry(path) as store:
        assert store.first_choices(S1) == (reg(2), reg(2, "file:///srv/b"))


def test_control_failure_rolls_back_registration(path):
    with AccessRegistry(path, writable=True) as store:
        original = store._authorize

        def deny_control(action, a, b, database, trigger):
            if action == sqlite3.SQLITE_INSERT and a == "scope_locator_controls":
                return sqlite3.SQLITE_DENY
            return original(action, a, b, database, trigger)

        store._db.set_authorizer(deny_control)
        with pytest.raises(AccessRegistryError, match="SQLITE"):
            store.register_locator(reg())
        store._db.set_authorizer(original)
        assert store.history(S1).registrations == ()
        assert store.register_locator(reg()).status == "insert"


def test_sqlite_backup_preserves_history_not_runtime_authority(path):
    with AccessRegistry(path, writable=True) as store:
        store.register_locator(reg())
        store.register_locator(reg(2, "file:///srv/b"))
        source = raw(path)
        copy_path = path.parent / "snapshot.sqlite3"
        destination = sqlite3.connect(copy_path)
        source.backup(destination)
        assert destination.execute(
            "SELECT COUNT(*) FROM scope_locators"
        ).fetchone() == (2,)
        destination.close()
        source.close()
    # This is a SQLite copy exercise, not an Access backup/restore API or approval.
    assert copy_path.is_file()


def test_commit_failure_rolls_back_the_entire_registration(path):
    with AccessRegistry(path, writable=True) as store:
        original = store._authorize

        def deny_commit(action, a, b, database, trigger):
            if action == sqlite3.SQLITE_TRANSACTION and a == "COMMIT":
                return sqlite3.SQLITE_DENY
            return original(action, a, b, database, trigger)

        store._db.set_authorizer(deny_commit)
        with pytest.raises(AccessRegistryError, match="SQLITE"):
            store.register_locator(reg())
        store._db.set_authorizer(original)
        assert store.history(S1).registrations == ()
        assert store.register_locator(reg()).status == "insert"
