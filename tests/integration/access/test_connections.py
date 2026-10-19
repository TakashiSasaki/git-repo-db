"""Real A1b SQLite operations, not a model of permission to execute transports."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from repo_catalog.adapters.sqlite import access_schema as schema
from repo_catalog.adapters.sqlite.access_connections import AccessConnections
from repo_catalog.adapters.sqlite.access_registry import AccessRegistry
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

S1 = "550e8400-e29b-41d4-a716-446655440000"
S2 = "650e8400-e29b-41d4-a716-446655440000"
R1 = "750e8400-e29b-41d4-a716-446655440000"
R2 = "850e8400-e29b-41d4-a716-446655440000"
LOCATOR = "https://git.example.org/team/repo.git"
KEY = AssignmentKey(S1, LOCATOR, "https-main")
ROUTE = ScopeLocatorRegistration(S1, 10, "file:///runner")
OPTIONS = canonical(
    {
        "version": 1,
        "transport": "https",
        "credential_ref": {"kind": "credential-helper", "name": "alpha"},
    }
)
CONTEXT = canonical(
    {
        "version": 1,
        "executor_kind": "local",
        "executor_ref": "workstation",
        "identity_view": "owner",
        "path_dialect": "posix",
    }
)


def raw(path):
    db = sqlite3.connect(path, isolation_level=None, cached_statements=0)
    schema.register_functions(db)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    return db


@pytest.fixture
def path(tmp_path):
    path = tmp_path / "access.sqlite3"
    schema.initialize(path)
    with AccessConnections(path, writable=True) as store:
        store.register_scope(AccessScope(S1, "work"))
        store.register_scope(AccessScope(S2, "work"))
        store.register_locator(ROUTE)
        store.set_locator_enabled(ROUTE, True)
        store.configure_scope(ScopeExecutionContext(S1, CONTEXT, True))
        store.bind_repository(RepositoryBinding(S1, LOCATOR, R1, True))
        store.configure_connection(
            ConnectionConfiguration(S1, KEY.configuration_name, OPTIONS, True)
        )
        store.assign_connection(LocatorConnection(KEY, True))
    return path


def approve(store, **selection):
    plan = store.review_plan(R1, S1, **selection)
    return store.record_local_approval(plan, 20)


def row_count(path, table):
    with raw(path) as db:
        return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_tables_direct_keys_and_no_extra_history(path):
    with raw(path) as db:
        assert schema.SCHEMA_VERSION == 2
        assert set(schema.TABLES) == {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        assert len(schema.TABLES) == 10
        for table in (
            "repository_locators",
            "local_access_grants",
            "scope_execution_contexts",
        ):
            assert db.execute(f"PRAGMA table_list('{table}')").fetchone()[4:] == (1, 1)
        assert [
            r[1] for r in db.execute("PRAGMA table_info(local_access_grants)") if r[5]
        ] == list(KEY.__dataclass_fields__)
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        schema.validate(db)


def test_review_requires_explicit_local_approval(path):
    with AccessConnections(path, writable=True) as store:
        plan = store.review_plan(R1, S1)
        assert plan.registration == ROUTE and plan.repository_uuidv4 == R1
        assert plan.options_json == OPTIONS and plan.context_json == CONTEXT
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(R1, S1)
        grant = store.record_local_approval(plan, 20)
        assert store.current_grant(R1, S1) == grant
        store.revoke_local_approval(KEY)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(R1, S1)
    assert not (path.parent / "core.sqlite3").exists()
    assert not (path.parent / "context.sqlite3").exists()


def test_same_scoped_locator_cannot_silently_rebind(path):
    with AccessConnections(path, writable=True) as store:
        old = store.binding(S1, LOCATOR)
        assert store.bind_repository(old) == "duplicate"
        with pytest.raises(AccessRegistryError, match="BINDING_CONFLICT"):
            store.bind_repository(replace(old, repository_uuidv4=R2))
        store.bind_repository(RepositoryBinding(S2, LOCATOR, R2))
        assert store.binding(S1, LOCATOR).repository_uuidv4 == R1
        assert store.binding(S2, LOCATOR).repository_uuidv4 == R2


def test_explicit_rebind_clears_old_preference_and_grant(path):
    with AccessConnections(path, writable=True) as store:
        pref = AccessPreference(R1, KEY)
        store.set_preference(pref)
        approve(store)
        old = store.binding(S1, LOCATOR)
        new = replace(old, repository_uuidv4=R2)
        assert store.bind_repository(new, expected=old) == "update"
        assert row_count(path, "local_access_grants") == 0
        assert row_count(path, "repository_access_preferences") == 0
        with pytest.raises(AccessRegistryError, match="BINDING_CONFLICT"):
            store.review_plan(R1, S1, assignment=KEY)
        assert store.review_plan(R2, S1).repository_uuidv4 == R2
        with pytest.raises(AccessRegistryError, match="STALE_SETTINGS"):
            store.bind_repository(old, expected=old)


def test_preferences_reference_assignment_and_matching_repository(path):
    with AccessConnections(path, writable=True) as store:
        with pytest.raises(AccessRegistryError):
            store.set_preference(AccessPreference(R2, KEY))
        missing = replace(KEY, configuration_name="absent")
        with pytest.raises(AccessRegistryError):
            store.set_preference(AccessPreference(R1, missing))
        assert store.set_preference(AccessPreference(R1, KEY)) == "insert"
    assert row_count(path, "repository_access_preferences") == 1


@pytest.mark.parametrize(
    "target", ["context", "route", "profile", "binding", "assignment"]
)
def test_disable_enable_aba_never_resurrects_grant(path, target):
    with AccessConnections(path, writable=True) as store:
        approve(store)
        if target == "route":
            # Exercise the original A1a API and its authorizer, too.
            with AccessRegistry(path, writable=True) as registry:
                registry.set_locator_enabled(ROUTE, False)
                registry.set_locator_enabled(ROUTE, True)
        else:
            value, writer = {
                "context": (store.scope_context(S1), store.configure_scope),
                "profile": (
                    store.configuration(S1, KEY.configuration_name),
                    store.configure_connection,
                ),
                "binding": (store.binding(S1, LOCATOR), store.bind_repository),
                "assignment": (store.assignment(KEY), store.assign_connection),
            }[target]
            disabled = replace(value, enabled=False)
            writer(disabled, expected=value)
            writer(value, expected=disabled)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(R1, S1)
        assert store.history(S1).registrations == (ROUTE,)
        assert approve(store) == store.current_grant(R1, S1)


@pytest.mark.parametrize("target", ["profile", "context", "binding"])
def test_content_aba_never_resurrects_grant(path, target):
    with AccessConnections(path, writable=True) as store:
        approve(store)
        if target == "profile":
            old = store.configuration(S1, KEY.configuration_name)
            data = json.loads(old.options_json)
            data["credential_ref"]["name"] = "beta"
            new = replace(old, options_json=canonical(data))
            writer = store.configure_connection
        elif target == "context":
            old = store.scope_context(S1)
            data = json.loads(old.context_json)
            data["identity_view"] = "other"
            new = replace(old, context_json=canonical(data))
            writer = store.configure_scope
        else:
            old = store.binding(S1, LOCATOR)
            new = replace(old, repository_uuidv4=R2)
            writer = store.bind_repository
        writer(new, expected=old)
        writer(old, expected=new)
        assert row_count(path, "local_access_grants") == 0
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(R1, S1)


def test_noop_and_labels_preserve_grant(path):
    with AccessConnections(path, writable=True) as store:
        grant = approve(store)
        profile = store.configuration(S1, KEY.configuration_name)
        assert store.configure_connection(profile, expected=profile) == "duplicate"
        store.set_locator_enabled(ROUTE, True)
        store.rename_scope(S1, "renamed")
        assert store.current_grant(R1, S1) == grant


def test_latest_unapproved_disabled_and_a_b_a(path):
    with AccessConnections(path, writable=True) as store:
        old = approve(store)
        b = ScopeLocatorRegistration(S1, 30, "file:///new-runner")
        store.register_locator(b)
        with pytest.raises(AccessRegistryError, match="DISABLED"):
            store.current_grant(R1, S1)
        store.set_locator_enabled(b, True)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(R1, S1)
        assert store.current_grant(R1, S1, registration=ROUTE) == old
        again = ScopeLocatorRegistration(S1, 40, ROUTE.scope_locator_uri)
        store.register_locator(again)
        store.set_locator_enabled(again, True)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(R1, S1)
        assert (
            store.record_local_approval(store.review_plan(R1, S1), 50).plan.registration
            == again
        )


def test_latest_ties_before_controls_and_permissions(path):
    with AccessConnections(path, writable=True) as store:
        approved = approve(store)
        tied = ScopeLocatorRegistration(S1, ROUTE.registered_at_us, "file:///other")
        store.register_locator(tied)
        with pytest.raises(AccessRegistryError, match="AMBIGUOUS"):
            store.current_grant(R1, S1)
        with pytest.raises(AccessRegistryError, match="CANDIDATE_LIMIT"):
            store.review_plan(R1, S1, max_candidates=1)
        assert store.current_grant(R1, S1, registration=ROUTE) == approved


def test_late_registration_and_replay_do_not_promote_or_enable(path):
    with AccessConnections(path, writable=True) as store:
        grant = approve(store)
        earlier = ScopeLocatorRegistration(S1, 1, "file:///past")
        store.register_locator(earlier)
        assert store.current_grant(R1, S1) == grant
        store.set_locator_enabled(ROUTE, False)
        assert store.register_locator(ROUTE).status == "duplicate"
        assert not store.locator_enabled(ROUTE)
        assert row_count(path, "local_access_grants") == 0


def test_assignment_ambiguity_does_not_select_only_approved_profile(path):
    with AccessConnections(path, writable=True) as store:
        grant = approve(store)
        key2 = replace(KEY, configuration_name="https-other")
        store.configure_connection(
            ConnectionConfiguration(S1, key2.configuration_name, OPTIONS, True)
        )
        store.assign_connection(LocatorConnection(key2, True))
        with pytest.raises(AccessRegistryError, match="AMBIGUOUS"):
            store.current_grant(R1, S1)
        store.set_preference(AccessPreference(R1, KEY))
        assert store.current_grant(R1, S1) == grant
        disabled = replace(store.assignment(KEY), enabled=False)
        store.assign_connection(disabled, expected=store.assignment(KEY))
        with pytest.raises(AccessRegistryError, match="DISABLED"):
            store.current_grant(R1, S1)


def test_cross_scope_explicit_choice_rejected(path):
    with AccessConnections(path) as store:
        with pytest.raises(AccessRegistryError, match="SCOPE_MISMATCH"):
            store.review_plan(R1, S1, assignment=replace(KEY, scope_uuidv4=S2))
        with pytest.raises(AccessRegistryError, match="SCOPE_MISMATCH"):
            store.review_plan(R1, S1, registration=replace(ROUTE, scope_uuidv4=S2))


def test_profile_shared_by_repositories_and_scope_only_conflicts(path):
    with AccessConnections(path, writable=True) as store:
        locator2 = "https://git.example.org/team/library.git"
        key2 = replace(KEY, locator_text=locator2)
        store.bind_repository(RepositoryBinding(S1, locator2, R2, True))
        store.assign_connection(LocatorConnection(key2, True))
        first = approve(store)
        other = store.record_local_approval(store.review_plan(R2, S1), 21)
        assert first.plan.repository_uuidv4 != other.plan.repository_uuidv4
        profile = store.configuration(S1, KEY.configuration_name)
        store.configure_connection(replace(profile, enabled=False), expected=profile)
        assert row_count(path, "local_access_grants") == 0


def test_transport_mismatch_rejected_without_revocation(path):
    with AccessConnections(path, writable=True) as store:
        grant = approve(store)
        profile = store.configuration(S1, KEY.configuration_name)
        incompatible = replace(
            profile, options_json=canonical({"version": 1, "transport": "ssh"})
        )
        with pytest.raises(AccessRegistryError):
            store.configure_connection(incompatible, expected=profile)
        assert store.current_grant(R1, S1) == grant
        file_key = replace(KEY, locator_text="/repos/local.git")
        store.bind_repository(RepositoryBinding(S1, file_key.locator_text, R2, True))
        with pytest.raises(AccessRegistryError):
            store.assign_connection(LocatorConnection(file_key, True))


def test_stale_review_cannot_authorize_changed_options(path):
    with AccessConnections(path, writable=True) as store:
        plan = store.review_plan(R1, S1)
        profile = store.configuration(S1, KEY.configuration_name)
        new_options = canonical({"version": 1, "transport": "https"})
        store.configure_connection(
            replace(profile, options_json=new_options), expected=profile
        )
        with pytest.raises(AccessRegistryError, match="REVIEW_CHANGED"):
            store.record_local_approval(plan, 30)
        assert row_count(path, "local_access_grants") == 0


@pytest.mark.parametrize(
    "mutation", ["profile", "registration", "repository", "purpose"]
)
def test_direct_sql_grant_attacks(path, mutation):
    with AccessConnections(path) as store:
        row = list(store.review_plan(R1, S1).row) + [20]
    index, value = {
        "profile": (7, canonical({"version": 1, "transport": "https"})),
        "registration": (5, 999),
        "repository": (4, R2),
        "purpose": (3, "git-write"),
    }[mutation]
    row[index] = value
    with raw(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO local_access_grants VALUES(?,?,?,?,?,?,?,?,?,?)", row
            )
    assert row_count(path, "local_access_grants") == 0


@pytest.mark.parametrize(
    "table",
    [
        "scope_execution_contexts",
        "repository_locators",
        "connection_configurations",
        "locator_connections",
        "repository_access_preferences",
        "local_access_grants",
    ],
)
def test_replace_cannot_bypass_invalidation(path, table):
    with AccessConnections(path, writable=True) as store:
        store.set_preference(AccessPreference(R1, KEY))
        grant = approve(store)
    with raw(path) as db:
        row = db.execute(f"SELECT * FROM {table}").fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                f"INSERT OR REPLACE INTO {table} VALUES({','.join('?' for _ in row)})",
                row,
            )
    with AccessConnections(path) as store:
        assert store.current_grant(R1, S1) == grant


def test_grant_update_forbidden_and_control_deletion_revokes(path):
    with AccessConnections(path, writable=True) as store:
        approve(store)
    with raw(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE local_access_grants SET approved_at_us=30")
        db.execute("DELETE FROM scope_locator_controls")
        assert db.execute("SELECT count(*) FROM local_access_grants").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM scope_locators").fetchone() == (1,)


def test_failed_reapproval_rolls_back_deleted_prior_grant(path):
    with AccessConnections(path, writable=True) as store:
        grant = approve(store)
        db = store._db

        class Failure:
            def __getattr__(self, key):
                return getattr(db, key)

            def execute(self, sql, args=()):
                if sql.startswith("INSERT INTO local_access_grants"):
                    raise sqlite3.IntegrityError("injected insert failure")
                return db.execute(sql, args)

        store._db = Failure()
        with pytest.raises(AccessRegistryError):
            store.record_local_approval(grant.plan, 30)
        store._db = db
        assert not db.in_transaction
        assert store.current_grant(R1, S1) == grant


def test_commit_failure_rolls_back_settings_and_revocation(path):
    with AccessConnections(path, writable=True) as store:
        grant = approve(store)
        profile = store.configuration(S1, KEY.configuration_name)
        db = store._db

        class Failure:
            def __getattr__(self, key):
                return getattr(db, key)

            def commit(self):
                raise sqlite3.OperationalError("injected commit failure")

        store._db = Failure()
        with pytest.raises(AccessRegistryError):
            store.configure_connection(
                replace(profile, enabled=False), expected=profile
            )
        store._db = db
        assert store.configuration(S1, KEY.configuration_name) == profile
        assert store.current_grant(R1, S1) == grant


def test_concurrent_cas_only_one_writer_wins(path):
    with AccessConnections(path) as store:
        old = store.scope_context(S1)

    def write(value):
        data = json.loads(CONTEXT)
        data["executor_ref"] = value
        with AccessConnections(path, writable=True) as store:
            try:
                return store.configure_scope(
                    replace(old, context_json=canonical(data)), expected=old
                )
            except AccessRegistryError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ("machine-a", "machine-b")))
    assert sorted(results) == ["STALE_SETTINGS", "update"]


@pytest.mark.parametrize("already_open", [False, True])
@pytest.mark.parametrize("damage", ["utf8", "options", "grant"])
def test_corrupt_stored_values_stop_access(path, already_open, damage):
    with AccessConnections(path, writable=True) as writer:
        approve(writer)
    store = AccessConnections(path) if already_open else None
    try:
        with raw(path) as db:
            db.execute("PRAGMA ignore_check_constraints=ON")
            if damage == "grant":
                # No trigger/DDL drift: forge permission by direct privileged insert.
                row = list(db.execute("SELECT * FROM local_access_grants").fetchone())
                db.execute("DELETE FROM local_access_grants")
                row[-1] = 0
                db.execute(
                    "INSERT INTO local_access_grants VALUES(?,?,?,?,?,?,?,?,?,?)", row
                )
            elif damage == "utf8":
                db.execute(
                    "UPDATE scope_execution_contexts SET execution_context_json=CAST(X'ff' AS TEXT)"
                )
            else:
                db.execute("UPDATE connection_configurations SET options_json='{}'")
        with pytest.raises(AccessRegistryError, match="CORRUPT"):
            if already_open:
                store.review_plan(R1, S1) if damage != "grant" else store.current_grant(
                    R1, S1
                )
            else:
                AccessConnections(path)
        assert schema.stop_path(path).exists()
    finally:
        if store is not None:
            store.close()


def test_readonly_and_no_generic_sql_or_transport(path):
    with AccessConnections(path) as store:
        with pytest.raises(AccessRegistryError, match="READ_ONLY"):
            store.record_local_approval(store.review_plan(R1, S1), 20)
        with pytest.raises(sqlite3.DatabaseError):
            store._db.execute("DELETE FROM local_access_grants")
        assert not hasattr(store, "execute") and not hasattr(store, "dispatch")


def test_damaged_foreign_key_cannot_vanish_from_candidate_join(path):
    with AccessConnections(path) as store:
        with raw(path) as db:
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("DELETE FROM connection_configurations")
        with pytest.raises(AccessRegistryError, match="CORRUPT"):
            store.review_plan(R1, S1)
        assert schema.stop_path(path).exists()


def test_scope_registration_does_not_dereference_or_probe_credentials(
    path, monkeypatch
):
    import socket
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("external execution attempted")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    with AccessConnections(path, writable=True) as store:
        assert approve(store) == store.current_grant(R1, S1)


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "30", 2**63, None])
def test_bad_approval_time_does_not_delete_existing_grant(path, value):
    with AccessConnections(path, writable=True) as store:
        grant = approve(store)
        with pytest.raises(AccessRegistryError):
            store.record_local_approval(grant.plan, value)
        assert store.current_grant(R1, S1) == grant


def test_mutated_in_memory_value_rechecked_before_storage(path):
    with AccessConnections(path, writable=True) as store:
        profile = store.configuration(S1, KEY.configuration_name)
        forged = replace(profile)
        object.__setattr__(forged, "options_json", '{"token":"do-not-store"}')
        with pytest.raises(AccessRegistryError):
            store.configure_connection(forged, expected=profile)
        assert store.configuration(S1, KEY.configuration_name) == profile


def test_unsupported_p1_store_was_not_extended_to_access():
    from repo_catalog.adapters.sqlite.p1_schema import STORES

    assert "access" not in STORES


def test_reopen_validates_and_retains_same_local_grant(path):
    with AccessConnections(path, writable=True) as store:
        original = approve(store)
    with AccessConnections(path) as store:
        assert store.current_grant(R1, S1) == original
    with raw(path) as db:
        schema.validate(db)


def test_missing_current_control_requires_explicit_operation_not_replay(path):
    with AccessConnections(path, writable=True) as store:
        approve(store)
        with raw(path) as db:
            db.execute("DELETE FROM scope_locator_controls")
        assert store.register_locator(ROUTE).status == "duplicate"
        with pytest.raises(AccessRegistryError, match="DISABLED"):
            store.review_plan(R1, S1)
        store.set_locator_enabled(ROUTE, True)
        with pytest.raises(AccessRegistryError, match="APPROVAL_REQUIRED"):
            store.current_grant(R1, S1)
