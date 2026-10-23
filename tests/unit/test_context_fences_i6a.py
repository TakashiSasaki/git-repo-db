"""R16/T19: both exact fences, explicit isolation and normal reopen refusal."""

import sqlite3

import pytest

from repo_catalog.adapters.sqlite import p1_schema
from repo_catalog.adapters.sqlite.p1_context import ContextStore
from repo_catalog.adapters.sqlite.p1_coordination import (
    AdmissionTransaction,
    PairCoordinator,
)
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.p1_coordination import CoordinationError
from repo_catalog.domain.production_context import ContextError
from repo_catalog.domain.resource_stage import (
    TRANSFER_FENCE_DEFINITIONS,
    UnsupportedTransferSchema,
    _isolated_transfer_fixture,
    has_transfer_fence,
    is_isolated_transfer_fixture,
    validate_stage_storage,
)
from tests.support.i6a import isolated_context_db

REPOSITORY = "9ebbe38a-f937-40e6-a99c-701835ebcf10"
INSTANCE = "aad25448-03eb-4f83-a75e-cb7055fd33be"
FENCES = tuple(row[1] for row in TRANSFER_FENCE_DEFINITIONS)


@pytest.fixture
def product_db():
    db = sqlite3.connect(":memory:", isolation_level=None)
    p1_schema.register_functions(db)
    p1_schema.configure(db)
    db.executescript(p1_schema.compose("context"))
    db.execute(
        "INSERT INTO store_identity VALUES('context',?,?)", (REPOSITORY, INSTANCE)
    )
    yield db
    db.close()


def change_fences(db, state):
    missing = {
        "missing-report": FENCES[:1],
        "missing-endpoint": FENCES[1:],
        "both-missing": FENCES,
        "altered-report": FENCES[:1],
        "altered-endpoint": FENCES[1:],
    }[state]
    for name in missing:
        db.execute(f"DROP TRIGGER {name}")
    if state.startswith("altered"):
        original = next(
            row for row in TRANSFER_FENCE_DEFINITIONS if row[1] == missing[0]
        )
        db.execute(original[3].replace("RAISE(ABORT,'I2_TRANSFER_UNSUPPORTED')", "1"))


def test_t19_exact_both_definitions_match_packaged_schema(product_db, tmp_path):
    expected = tuple(
        row for row in p1_schema.expected_schema("context") if row[1] in FENCES
    )
    assert expected == TRANSFER_FENCE_DEFINITIONS
    assert has_transfer_fence(product_db) is True
    validate_stage_storage(product_db)
    product_db.execute("BEGIN")
    with Context.for_transaction(product_db, tmp_path) as facade:
        assert facade.snapshot_identity()[0] == REPOSITORY
    product_db.rollback()


@pytest.mark.parametrize(
    "state",
    [
        "missing-report",
        "missing-endpoint",
        "both-missing",
        "altered-report",
        "altered-endpoint",
    ],
)
def test_t19_invalid_fences_refuse_helper_store_and_facade(product_db, tmp_path, state):
    change_fences(product_db, state)
    before = p1_schema.schema_rows(product_db)
    with pytest.raises(UnsupportedTransferSchema) as helper:
        has_transfer_fence(product_db)
    assert helper.value.code == "UNSUPPORTED_SCHEMA"
    with pytest.raises(UnsupportedTransferSchema):
        validate_stage_storage(product_db)
    with pytest.raises(UnsupportedTransferSchema):
        ContextStore(product_db).transfer_event_reports()
    product_db.execute("BEGIN")
    with pytest.raises(ContextError) as facade:
        Context(product_db, tmp_path)
    assert facade.value.code == "UNSUPPORTED_SCHEMA"
    assert product_db.in_transaction
    assert p1_schema.schema_rows(product_db) == before
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    product_db.rollback()


def test_t19_uninspectable_schema_refuses_helper_and_facade(product_db, tmp_path):
    def deny_schema(action, table, *unused):
        if action == sqlite3.SQLITE_READ and table in (
            "sqlite_master",
            "sqlite_schema",
        ):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    product_db.execute("BEGIN")
    product_db.set_authorizer(deny_schema)
    try:
        with pytest.raises(UnsupportedTransferSchema) as helper:
            has_transfer_fence(product_db)
        assert helper.value.code == "UNSUPPORTED_SCHEMA"
        assert isinstance(helper.value.__cause__, sqlite3.DatabaseError)
        with pytest.raises(ContextError) as facade:
            Context(product_db, tmp_path)
        assert facade.value.code == "UNSUPPORTED_SCHEMA"
        assert not (tmp_path / "p1-recovery-stop.json").exists()
    finally:
        product_db.set_authorizer(None)
        product_db.rollback()


def test_t19_isolation_is_connection_scoped_and_expires(product_db, tmp_path):
    change_fences(product_db, "both-missing")
    with isolated_context_db() as fixture:
        assert is_isolated_transfer_fixture(fixture)
        assert has_transfer_fence(fixture) is False
        with pytest.raises(UnsupportedTransferSchema):
            has_transfer_fence(product_db)
        with pytest.raises(UnsupportedTransferSchema):
            has_transfer_fence(fixture._connection)
        fixture.execute("BEGIN")
        with Context.for_transaction(fixture, tmp_path) as facade:
            assert is_isolated_transfer_fixture(facade.db)
            assert facade.snapshot_identity()[0] == REPOSITORY
        fixture.rollback()
    assert not is_isolated_transfer_fixture(fixture)
    with pytest.raises(UnsupportedTransferSchema):
        fixture.execute("SELECT 1")


@pytest.mark.parametrize(
    "state", ["missing-report", "missing-endpoint", "both-missing", "altered-report"]
)
def test_t19_normal_reopen_refuses_modified_catalog(tmp_path, state):
    path = tmp_path / "context.sqlite3"
    p1_schema.initialize(path, "context", REPOSITORY, INSTANCE)
    db = p1_schema.connect(path, "context")
    change_fences(db, state)
    db.close()
    with pytest.raises(p1_schema.SchemaError):
        p1_schema.connect(path, "context")
    with pytest.raises(p1_schema.SchemaError):
        with Context.transaction(tmp_path):
            pytest.fail("modified catalog became an ordinary capability")
    with pytest.raises(p1_schema.SchemaError):
        with Context.snapshot(tmp_path):
            pytest.fail("modified catalog became an ordinary snapshot")
    assert not (tmp_path / "p1-recovery-stop.json").exists()


def test_t19_private_isolation_scope_refuses_disk_catalog(tmp_path):
    path = tmp_path / "context.sqlite3"
    p1_schema.initialize(path, "context", REPOSITORY, INSTANCE)
    db = p1_schema.connect(path, "context")
    try:
        with pytest.raises(UnsupportedTransferSchema):
            with _isolated_transfer_fixture(db):
                pytest.fail("disk catalog received fixture capability")
        assert has_transfer_fence(db)
    finally:
        db.close()


@pytest.mark.parametrize("pragma", ["foreign_keys", "recursive_triggers"])
def test_t20_facade_refuses_disabled_required_pragma(product_db, tmp_path, pragma):
    product_db.execute(f"PRAGMA {pragma}=OFF")
    product_db.execute("BEGIN")
    with pytest.raises(ContextError) as error:
        Context(product_db, tmp_path)
    assert error.value.code == "UNSUPPORTED_SCHEMA"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    product_db.rollback()


@pytest.mark.parametrize("function", ["p1_parent_report_v1", "p1_transfer_event_v1"])
def test_t20_facade_refuses_wrong_udf_flags(product_db, tmp_path, function):
    product_db.create_function(function, 7, lambda *args: 1, deterministic=False)
    product_db.execute("BEGIN")
    with pytest.raises(ContextError) as error:
        Context(product_db, tmp_path)
    assert error.value.code == "UNSUPPORTED_SCHEMA"
    assert not (tmp_path / "p1-recovery-stop.json").exists()
    product_db.rollback()


def test_t19_trusted_coordinator_capabilities_keep_their_restricted_profile(tmp_path):
    for role in ("core", "context"):
        p1_schema.initialize(tmp_path / f"{role}.sqlite3", role, REPOSITORY, INSTANCE)
    with PairCoordinator(tmp_path).snapshots() as pair:
        with Context.for_snapshot(pair.context, tmp_path) as facade:
            assert has_transfer_fence(facade.db)
            assert facade.snapshot_identity()[0] == REPOSITORY
    db = p1_schema.connect(tmp_path / "context.sqlite3", "context")
    try:
        db.execute("BEGIN")
        with Context.for_transaction(AdmissionTransaction(db), tmp_path) as facade:
            assert has_transfer_fence(facade.db)
            assert facade.snapshot_identity()[0] == REPOSITORY
        db.set_authorizer(None)
        db.rollback()
    finally:
        db.close()


def test_t19_fence_inspection_preserves_recovery_stop(product_db, tmp_path):
    product_db.execute("BEGIN")
    with pytest.raises(CoordinationError) as stopped:
        with Context.for_transaction(product_db, tmp_path) as facade:
            product_db.set_trace_callback(
                lambda sql: (
                    PairCoordinator(tmp_path).stop("injected fence-read stop")
                    if sql.startswith("SELECT")
                    else None
                )
            )
            facade.resources()
    assert stopped.value.code == "RECOVERY_REQUIRED"
    product_db.set_trace_callback(None)
    product_db.rollback()


@pytest.mark.parametrize(
    "primary_code", [sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB]
)
def test_t19_fence_inspection_preserves_sqlite_corruption(primary_code):
    error = sqlite3.DatabaseError("injected schema corruption")
    error.sqlite_errorcode = primary_code

    class BrokenConnection:
        def execute(self, sql):
            raise error

    with pytest.raises(sqlite3.DatabaseError) as failure:
        has_transfer_fence(BrokenConnection())
    assert failure.value is error
