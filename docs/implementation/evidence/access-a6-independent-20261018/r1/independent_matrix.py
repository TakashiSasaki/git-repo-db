"""Independent Access identity/history probes; synthetic data only.

Run using the locked environment and actual SQLite >= 3.51.3. No product monkeypatch,
pytest fixture, existing test helper or minimum-version override participates.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from repo_catalog.adapters.sqlite import access_schema as schema
from repo_catalog.adapters.sqlite.access_backup import AccessBackup
from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.adapters.sqlite.access_registry import AccessRegistry
from repo_catalog.application.access_maintenance import AccessMaintenance
from repo_catalog.domain.access_connections import (
    AccessPreference,
    AssignmentKey,
    ConnectionConfiguration,
    LocatorConnection,
    RepositoryBinding,
    ScopeExecutionContext,
    canonical,
)
from repo_catalog.domain.access_registry import (
    AccessRegistryError,
    AccessScope,
    ScopeLocatorRegistration,
)

CHECKOUT = Path(os.environ.get("R1_REVIEW_CHECKOUT", "/workspace/access-review-ro"))
OUT = Path(__file__).parent
S1 = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"
R0 = "33333333-3333-4333-8333-333333333333"
R1 = "44444444-4444-4444-8444-444444444444"
LOC = "/synthetic/repositories/one"
KEY = AssignmentKey(S1, LOC, "local")
ROUTE = ScopeLocatorRegistration(S1, 10, "file:///synthetic/a")
CONTEXT = canonical({"version": 1, "executor_kind": "local", "executor_ref": "one", "identity_view": "owner", "path_dialect": "posix"})
FILE_OPTIONS = canonical({"version": 1, "transport": "file", "path_dialect": "posix"})


def now():
    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S JST")


def git(*args):
    return subprocess.check_output(["git", "-C", str(CHECKOUT), *args], text=True).strip()


def raw(path):
    db = sqlite3.connect(path, isolation_level=None, cached_statements=0)
    schema.register_functions(db)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    return db


def rows(path, table):
    with raw(path) as db:
        return sorted(db.execute(f"SELECT * FROM {table}"))


def setup(directory):
    directory.mkdir(mode=0o700)
    path = directory / "access.sqlite3"
    schema.initialize(path)
    with AccessConnections(path, writable=True) as store:
        for s in (S1, S2):
            store.register_scope(AccessScope(s, "same-display-label"))
        store.register_locator(ROUTE)
        store.set_locator_enabled(ROUTE, True)
        store.configure_scope(ScopeExecutionContext(S1, CONTEXT, True))
        store.bind_repository(RepositoryBinding(S1, LOC, R0, True))
        store.configure_connection(ConnectionConfiguration(S1, "local", FILE_OPTIONS, True))
        store.assign_connection(LocatorConnection(KEY, True))
        plan = store.review_plan(R0, S1)
        grant = store.record_local_approval(plan, 100)
    return path, grant


def expect(code, operation):
    try:
        operation()
    except AccessRegistryError as error:
        assert error.code == code, (code, error.code)
        return error.code
    raise AssertionError(f"Expected {code}")


def expect_sql(operation):
    try:
        operation()
    except sqlite3.IntegrityError as error:
        return str(error)
    raise AssertionError("Expected SQL integrity rejection")


def key_inventory(root):
    path, _ = setup(root / "inventory")
    expected = {
        "access_identity": ["store_role"],
        "access_scopes": ["scope_uuidv4"],
        "scope_locators": ["scope_uuidv4", "registered_at_us", "scope_locator_uri"],
        "scope_locator_controls": ["scope_uuidv4", "registered_at_us", "scope_locator_uri"],
        "scope_execution_contexts": ["scope_uuidv4"],
        "repository_locators": ["scope_uuidv4", "locator_text"],
        "connection_configurations": ["scope_uuidv4", "configuration_name"],
        "locator_connections": ["scope_uuidv4", "locator_text", "configuration_name", "purpose"],
        "repository_access_preferences": ["repository_uuidv4", "scope_uuidv4", "purpose"],
        "local_access_grants": ["scope_uuidv4", "locator_text", "configuration_name", "purpose"],
    }
    actual = {}
    with raw(path) as db:
        assert set(schema.TABLES) == set(expected)
        for table, pk in expected.items():
            columns = list(db.execute(f"PRAGMA table_info('{table}')"))
            observed = [r[1] for r in sorted(columns, key=lambda row: row[5]) if r[5]]
            assert observed == pk
            assert all(r[3] == 1 for r in columns if r[5])
            actual[table] = {"pk": observed, "fk_rows": list(db.execute(f"PRAGMA foreign_key_list('{table}')"))}
        assert not list(db.execute("PRAGMA foreign_key_check"))
        schema.validate(db)
    return actual


def history_ranking(root):
    path, grant = setup(root / "history")
    b = ScopeLocatorRegistration(S1, 20, "file:///synthetic/b")
    a_again = ScopeLocatorRegistration(S1, 30, ROUTE.scope_locator_uri)
    older = ScopeLocatorRegistration(S1, 15, "file:///synthetic/late")
    tie = ScopeLocatorRegistration(S1, 30, "file:///synthetic/z")
    with AccessConnections(path, writable=True) as store:
        for registration in (b, a_again):
            assert store.register_locator(registration).status == "insert"
        result = store.register_locator(older)
        assert result.precedes_latest and result.previous_latest_us == 30
        assert store.first_choices(S1) == (a_again,)
        expect("DISABLED", lambda: store.review_plan(R0, S1))
        assert store.current_grant(R0, S1, registration=ROUTE) == grant
        store.set_locator_enabled(a_again, True)
        expect("APPROVAL_REQUIRED", lambda: store.current_grant(R0, S1))
        store.register_locator(tie)
        assert store.first_choices(S1) == (a_again, tie)
        expect("AMBIGUOUS", lambda: store.review_plan(R0, S1))
        expect("CANDIDATE_LIMIT", lambda: store.first_choices(S1, max_candidates=1))
        page, observed = None, []
        while True:
            page = store.history(S1, limit=1, after=None if page is None else page.next_cursor)
            observed.extend(page.registrations)
            if page.next_cursor is None:
                break
        expected = [a_again, tie, b, older, ROUTE]
        assert observed == expected
        for item in expected:
            assert store.register_locator(item).status == "duplicate"
        assert not store.locator_enabled(tie)
    with raw(path) as db:
        sql_choices = list(db.execute("SELECT * FROM scope_first_choices WHERE scope_uuidv4=? ORDER BY scope_locator_uri", (S1,)))
        assert sql_choices == [a_again.key, tie.key]
        assert db.execute("SELECT count(*) FROM scope_locators").fetchone()[0] == 5
    return {"history": [r.key for r in observed], "sql_choices": sql_choices, "default": "AMBIGUOUS", "clock_regression": result.__dict__}


def replay_missing_control(root):
    path, _ = setup(root / "replay-control")
    with raw(path) as db:
        db.execute("DELETE FROM scope_locator_controls")
        assert not db.execute("SELECT * FROM local_access_grants").fetchall()
    with AccessConnections(path, writable=True) as store:
        assert store.register_locator(ROUTE).status == "duplicate"
        assert not store.locator_enabled(ROUTE)
    assert rows(path, "scope_locator_controls") == []
    return {"history": rows(path, "scope_locators"), "controls_after_replay": []}


def rebind_and_scope(root):
    path, _ = setup(root / "rebind")
    with AccessConnections(path, writable=True) as store:
        original = store.binding(S1, LOC)
        store.set_preference(AccessPreference(R0, KEY))
        expect("BINDING_CONFLICT", lambda: store.bind_repository(replace(original, repository_uuidv4=R1)))
        alternate = replace(original, repository_uuidv4=R1)
        store.bind_repository(alternate, expected=original)
        assert not rows(path, "local_access_grants")
        assert not rows(path, "repository_access_preferences")
        expect("BINDING_CONFLICT", lambda: store.review_plan(R0, S1, assignment=KEY))
        assert store.review_plan(R1, S1).repository_uuidv4 == R1
        store.bind_repository(original, expected=alternate)
        expect("APPROVAL_REQUIRED", lambda: store.current_grant(R0, S1))
        expect("STALE_SETTINGS", lambda: store.bind_repository(alternate, expected=alternate))
        store.bind_repository(RepositoryBinding(S2, LOC, R1, True))
        assert store.binding(S2, LOC).repository_uuidv4 == R1
        assert store.binding(S1, LOC).repository_uuidv4 == R0
    return {"bindings": rows(path, "repository_locators"), "grants": rows(path, "local_access_grants")}


def every_aba(root):
    result = {}
    for target in ("scope-enabled", "scope-content", "binding-enabled", "binding-uuid", "profile-enabled", "profile-content", "assignment-enabled", "route-enabled"):
        path, grant = setup(root / target)
        with AccessConnections(path, writable=True) as store:
            if target.startswith("scope"):
                old = store.scope_context(S1)
                options = json.loads(CONTEXT)
                options["executor_ref"] = "changed"
                new = replace(old, enabled=False) if target.endswith("enabled") else replace(old, context_json=canonical(options))
                method = store.configure_scope
            elif target.startswith("binding"):
                old = store.binding(S1, LOC)
                new = replace(old, enabled=False) if target.endswith("enabled") else replace(old, repository_uuidv4=R1)
                method = store.bind_repository
            elif target.startswith("profile"):
                old = store.configuration(S1, "local")
                if target == "profile-content":
                    # File profile has no second valid semantic value. Use a separate
                    # real HTTPS assignment with finite helper-reference rotation.
                    https_key = AssignmentKey(S1, "https://git.example.test/r.git", "https")
                    options = canonical({"version": 1, "transport": "https", "credential_ref": {"kind": "credential-helper", "name": "alpha"}})
                    store.bind_repository(RepositoryBinding(S1, https_key.locator_text, R1, True))
                    store.configure_connection(ConnectionConfiguration(S1, "https", options, True))
                    store.assign_connection(LocatorConnection(https_key, True))
                    plan = store.review_plan(R1, S1)
                    store.record_local_approval(plan, 101)
                    old = store.configuration(S1, "https")
                    new = replace(old, options_json=options.replace("alpha", "beta"))
                    key, repository = https_key, R1
                else:
                    new = replace(old, enabled=False)
                method = store.configure_connection
            elif target.startswith("assignment"):
                old = store.assignment(KEY)
                new = replace(old, enabled=False)
                method = store.assign_connection
            else:
                store.set_locator_enabled(ROUTE, False)
                store.set_locator_enabled(ROUTE, True)
                expect("APPROVAL_REQUIRED", lambda: store.current_grant(R0, S1))
                result[target] = "grant absent after false->true"
                continue
            method(new, expected=old)
            method(old, expected=new)
            if target == "profile-content":
                expect("APPROVAL_REQUIRED", lambda: store.current_grant(repository, S1, assignment=key))
                assert store.current_grant(R0, S1) == grant  # Unaffected profile remains.
            else:
                expect("APPROVAL_REQUIRED", lambda: store.current_grant(R0, S1))
            result[target] = "grant absent after A->B->A"
    path, grant = setup(root / "noop-label")
    with AccessConnections(path, writable=True) as store:
        store.rename_scope(S1, "same-uuid-new-label")
        assert store.configure_scope(store.scope_context(S1), expected=store.scope_context(S1)) == "duplicate"
        assert store.current_grant(R0, S1) == grant
    result["noop-label"] = "grant preserved"
    return result


def sql_constraints(root):
    path, grant = setup(root / "sql")
    messages = {}
    with raw(path) as db:
        for key, statement, args in (
            ("history-update", "UPDATE scope_locators SET registered_at_us=11", ()),
            ("history-delete", "DELETE FROM scope_locators", ()),
            ("history-replace", "INSERT OR REPLACE INTO scope_locators VALUES(?,?,?)", ROUTE.key),
            ("control-partial-fk", "INSERT INTO scope_locator_controls VALUES(?,?,?,1)", (S1, 11, ROUTE.scope_locator_uri)),
            ("scope-rekey", "UPDATE access_scopes SET scope_uuidv4=? WHERE scope_uuidv4=?", ("55555555-5555-4555-8555-555555555555", S1)),
            ("grant-update", "UPDATE local_access_grants SET approved_at_us=101", ()),
            ("repository-duplicate", "INSERT INTO repository_locators VALUES(?,?,?,1)", (S1, LOC, R1)),
            ("preference-wrong-repository", "INSERT INTO repository_access_preferences VALUES(?,?,?,?,?)", (R1, S1, "git-read", LOC, "local")),
        ):
            messages[key] = expect_sql(lambda: db.execute(statement, args))
        before = list(db.execute("SELECT * FROM local_access_grants"))
        assert len(before) == 1
        # Matching content alone cannot retain approval across SQL settings ABA.
        db.execute("UPDATE repository_locators SET enabled=0 WHERE scope_uuidv4=?", (S1,))
        db.execute("UPDATE repository_locators SET enabled=1 WHERE scope_uuidv4=?", (S1,))
        assert not list(db.execute("SELECT * FROM local_access_grants"))
        assert list(db.execute("SELECT * FROM scope_locators")) == [ROUTE.key]
        assert not list(db.execute("PRAGMA foreign_key_check"))
        schema.validate(db)
    return messages


def concurrent_replay(root):
    path, _ = setup(root / "concurrency")
    registration = ScopeLocatorRegistration(S1, 25, "file:///synthetic/concurrent")
    def insert():
        with AccessRegistry(path, writable=True) as store:
            return store.register_locator(registration).status
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: insert(), range(2)))
    assert statuses == ["duplicate", "insert"]
    with raw(path) as db:
        assert db.execute("SELECT count(*) FROM scope_locators WHERE registered_at_us=25").fetchone()[0] == 1
    return statuses


def restore_and_fork(root):
    path, grant = setup(root / "maintenance")
    for_copy = (ScopeLocatorRegistration(S1, 20, "file:///synthetic/b"), ScopeLocatorRegistration(S1, 30, ROUTE.scope_locator_uri), ScopeLocatorRegistration(S1, 30, "file:///synthetic/tie"))
    with AccessConnections(path, writable=True) as store:
        for registration in for_copy:
            store.register_locator(registration)
    before = {table: rows(path, table) for table in schema.TABLES}
    bundle = path.parent / "bundle"
    restored = path.parent / "restored"
    adapter = AccessBackup()
    manifest = adapter.backup(path, bundle)
    adapter.restore(bundle, restored)
    dest = restored / "access.sqlite3"
    assert before == {table: rows(path, table) for table in schema.TABLES}
    assert rows(dest, "scope_locators") == before["scope_locators"]
    assert not rows(dest, "local_access_grants")
    assert all(r[3] == 0 for r in rows(dest, "scope_locator_controls"))
    with AccessConnections(dest, writable=True) as store:
        assert len(store.first_choices(S1)) == 2
        store.register_locator(ROUTE)
        assert not store.locator_enabled(ROUTE)
        store.set_locator_enabled(ROUTE, True)
        expect("APPROVAL_REQUIRED", lambda: store.current_grant(R0, S1, registration=ROUTE))
    new_scope = "66666666-6666-4666-8666-666666666666"
    actual_new_time = 123456789
    service = AccessMaintenance(adapter, clock_us=lambda: actual_new_time)
    receipt = service.fork_scope(dest, S1, "file:///synthetic/fork", target_scope_uuidv4=new_scope)
    with raw(dest) as db:
        assert list(db.execute("SELECT * FROM scope_locators WHERE scope_uuidv4=?", (S1,))) == before["scope_locators"]
        new_history = list(db.execute("SELECT * FROM scope_locators WHERE scope_uuidv4=?", (new_scope,)))
        assert new_history == [(new_scope, actual_new_time, "file:///synthetic/fork")]
        for table in ("scope_execution_contexts", "repository_locators", "connection_configurations", "locator_connections"):
            assert all(row[-1] == 0 for row in db.execute(f"SELECT * FROM {table} WHERE scope_uuidv4=?", (new_scope,)))
        assert not list(db.execute("SELECT * FROM local_access_grants WHERE scope_uuidv4=?", (new_scope,)))
        assert list(db.execute("SELECT repository_uuidv4 FROM repository_locators WHERE scope_uuidv4=?", (new_scope,))) == [(R0,)]
        assert not list(db.execute("PRAGMA foreign_key_check"))
        schema.validate(db)
    return {"source_unchanged": True, "restored_history": before["scope_locators"], "fork_history": new_history, "fork": receipt, "backup_counts": manifest["row_counts"]}


def time_inputs(root):
    rejected = []
    for value in (None, False, True, 0, -1, 1.0, "1", (1 << 63)):
        expect("TIME", lambda: ScopeLocatorRegistration(S1, value, ROUTE.scope_locator_uri))
        rejected.append(repr(value))
    for value in (1, (1 << 63) - 1):
        assert ScopeLocatorRegistration(S1, value, ROUTE.scope_locator_uri).registered_at_us == value
    return {"rejected": rejected, "accepted": [1, (1 << 63) - 1]}


def main():
    schema.require_runtime()
    started = now()
    binding = {
        "started_at_jst": started,
        "head": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "dirty_before": git("status", "--porcelain"),
        "python": sys.version,
        "python_executable": sys.executable,
        "git": subprocess.check_output(["git", "--version"], text=True).strip(),
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_source_id": sqlite3.connect(":memory:").execute("SELECT sqlite_source_id()").fetchone()[0],
        "loaded_schema": str(Path(schema.__file__).resolve()),
        "platform": platform.platform(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    results = []
    with tempfile.TemporaryDirectory(prefix="r1-synthetic-", dir=OUT) as directory:
        root = Path(directory)
        for test in (key_inventory, history_ranking, replay_missing_control, rebind_and_scope, every_aba, sql_constraints, concurrent_replay, restore_and_fork, time_inputs):
            item = {"case": test.__name__, "started_at_jst": now()}
            try:
                item.update(status="passed", observed=test(root))
            except BaseException as error:
                item.update(status="failed", error=repr(error), traceback=traceback.format_exc())
            item["ended_at_jst"] = now()
            results.append(item)
            print(f"[{item['ended_at_jst']}][R1][{item['status']}] {test.__name__}", flush=True)
    binding.update(ended_at_jst=now(), dirty_after=git("status", "--porcelain"))
    output = {"binding": binding, "results": results}
    (OUT / "independent-matrix.json").write_text(json.dumps(output, indent=2) + "\n")
    return 0 if all(item["status"] == "passed" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
