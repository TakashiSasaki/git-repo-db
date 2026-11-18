"""Actual collection SQL authority matches typed Context membership admission."""

import sqlite3

import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.adapters.sqlite.recovery_validation import (
    validate_stored_admission_guards,
)
from repo_catalog.adapters.sqlite.repository_recovery_validation import (
    validate_stored_checks,
)
from repo_catalog.domain.collection_members import validate_collection_members
from repo_catalog.domain.context_admission import DependencySet
from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageScope,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.production_context import CollectionObservation, ContextError
from repo_catalog.domain.recovery import BackupValidationError
from repo_catalog.domain.resource_identification import ResourceIdentification as RI
from tests.integration.p3.test_production_context import (
    KEY,
    OTHER_SERVICE,
    PROVENANCE,
    SERVICE,
    directory,
    production_grants,
)
from tests.support.context_admission import fixture_transaction

__all__ = ["directory"]
OTHER = ResourceKey.from_native(SERVICE, "issue", "8")
CHILD = ResourceKey.document(KEY, "comment", "comment", "guard-child")
WRONG_OWNER = ResourceKey.document(OTHER, "comment", "comment", "guard-child")
FOREIGN_OWNER = ResourceKey.from_native(OTHER_SERVICE, "issue", "7")
FOREIGN_CHILD = ResourceKey.document(FOREIGN_OWNER, "comment", "comment", "guard-child")
MISSING = ResourceKey.document(KEY, "comment", "comment", "late-child")
GENERIC = ResourceKey.from_native(SERVICE, "provider_opaque", ["opaque", "\x00native"])
SCOPE_JSON = canonical({"coverage_kind": "comments"})
SCOPE = CoverageScope.collection(KEY, "comments", PROVENANCE, "comments")


def register(db, declaration):
    db.execute(
        "INSERT INTO resources(service_instance_uuidv4,resource_kind,provider_resource_id,identifier_namespace_kind,identifier_namespace_id,document_kind,provider_document_id) VALUES(?,?,?,?,?,?,?)",
        (*declaration.resource.coordinates(), *declaration.columns),
    )


def members(*keys):
    return canonical([key.coordinates() for key in keys])


def terminal(db, encoded, *, state="complete", stamp=1, kind="comments"):
    db.execute(
        "INSERT INTO collection_terminals VALUES(?,?,?,?,?,?,?,?)",
        (*KEY.coordinates(), kind, PROVENANCE, stamp, state, encoded),
    )


def proof(db, encoded, *, stamp=1):
    db.execute(
        "INSERT INTO coverage_proofs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            SCOPE.owner_kind,
            SCOPE.encoded,
            1,
            "complete",
            *KEY.coordinates(),
            "comments",
            PROVENANCE,
            stamp,
            "complete",
            encoded,
        ),
    )


@pytest.fixture
def membership_db(directory):
    db = connect(directory / "context.sqlite3", "context")
    for service in (SERVICE, OTHER_SERVICE):
        db.execute("INSERT INTO providers VALUES(?,?,?)", (service, "fixture", "{}"))
    for key in (KEY, OTHER, GENERIC):
        register(db, RI.unscoped(key))
    for child, owner in (
        (CHILD, KEY),
        (WRONG_OWNER, OTHER),
        (FOREIGN_CHILD, FOREIGN_OWNER),
    ):
        register(db, RI.scoped(child, owner, "comment", "guard-child"))
    db.execute(
        "INSERT INTO collections VALUES(?,?,?,?,?,?)",
        (*KEY.coordinates(), "comments", PROVENANCE, SCOPE_JSON),
    )
    db.execute(
        "INSERT INTO coverage_scopes(owner_kind,owner_coordinates_json,service_instance_uuidv4,resource_kind,provider_resource_id,collection_kind,collection_provenance_json,coverage_kind) VALUES(?,?,?,?,?,?,?,?)",
        (
            SCOPE.owner_kind,
            SCOPE.encoded,
            *KEY.coordinates(),
            "comments",
            PROVENANCE,
            "comments",
        ),
    )
    db.execute(
        "INSERT INTO coverage_claims VALUES(?,?,?,?,?)",
        (SCOPE.owner_kind, SCOPE.encoded, 1, "complete", None),
    )
    try:
        yield db
    finally:
        db.close()


BAD_SHAPES = (
    "null",
    "{}",
    '"original"',
    "[",
    "[[]]",
    '[{"resource_kind":"comment"}]',
    canonical([[SERVICE, "comment"]]),
    canonical([[SERVICE, "comment", CHILD.provider_resource_id, "extra"]]),
    canonical([[SERVICE, "comment", None]]),
    canonical([[SERVICE, "comment", 7]]),
    canonical([[SERVICE, "comment", "raw-unencoded-id"]]),
    canonical([[SERVICE, "comment", '"noncanonical" ']]),
    members(CHILD, CHILD),
    members(CHILD) + " ",
    canonical([[[SERVICE], "comment", CHILD.provider_resource_id]]),
)


@pytest.mark.parametrize("encoded", BAD_SHAPES)
@pytest.mark.parametrize("state", ["complete", "partial"])
def test_malformed_members_rejected_by_domain_terminal_and_proof_sql(
    membership_db, encoded, state
):
    db = membership_db
    with pytest.raises((ValueError, TypeError)):
        validate_collection_members(KEY, "comments", encoded)
    with pytest.raises(sqlite3.IntegrityError):
        terminal(db, encoded, state=state)
    # A coherent terminal does not make a different malformed proof admissible.
    terminal(db, members(CHILD))
    with pytest.raises(sqlite3.IntegrityError):
        proof(db, encoded)
    assert db.execute("SELECT count(*) FROM coverage_proofs").fetchone()[0] == 0


@pytest.mark.parametrize("key", [WRONG_OWNER, FOREIGN_CHILD, GENERIC, MISSING])
def test_actual_member_resource_kind_service_and_identification_owner_are_required(
    membership_db, key
):
    db = membership_db
    with pytest.raises(sqlite3.IntegrityError):
        terminal(db, members(key))
    assert db.execute("SELECT count(*) FROM collection_terminals").fetchone()[0] == 0
    assert (
        db.execute(
            "SELECT count(*) FROM resources WHERE provider_resource_id=?",
            (MISSING.provider_resource_id,),
        ).fetchone()[0]
        == 0
    )


def test_valid_partial_empty_and_full_proofs_need_no_body_or_repository_target(
    membership_db, directory
):
    db = membership_db
    terminal(db, members(CHILD))
    proof(db, members(CHILD))
    terminal(db, members(CHILD), state="partial", stamp=2)
    terminal(db, "[]", stamp=3)
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert db.execute("SELECT count(*) FROM text_bodies").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM repository_references").fetchone()[0] == 0
    # Unknown collection kinds have no invented child namespace restriction.
    db.execute(
        "INSERT INTO collections VALUES(?,?,?,?,?,?)",
        (*KEY.coordinates(), "pr_files", PROVENANCE, "{}"),
    )
    terminal(db, members(GENERIC), kind="pr_files")
    validate_stored_checks(db, "context", retained_bytes=False)
    validate_stored_admission_guards(db, "context")
    assert not (directory / "p1-recovery-stop.json").exists()


def test_detached_original_is_preserved_and_replayed_after_real_nominal_resupply(
    directory,
):
    observation = CollectionObservation(
        KEY, "comments", PROVENANCE, SCOPE_JSON, 1, "complete", (MISSING,)
    )
    original = observation.terminal
    grants = production_grants() | DependencySet(resources={MISSING})
    with fixture_transaction(directory, grants) as context:
        context.provider(SERVICE, "fixture")
        context.resource(KEY)
        with pytest.raises(ContextError) as failure:
            context.collection(observation)
        assert failure.value.code == "RESOURCE_UNAVAILABLE"
        assert observation.terminal == original
        assert (
            context.db.execute("SELECT count(*) FROM collection_terminals").fetchone()[
                0
            ]
            == 0
        )
        context.resource(
            MISSING, identification=RI.scoped(MISSING, KEY, "comment", "late-child")
        )
        context.collection(observation)
        context.prove_collection(
            CoverageClaim(SCOPE, 1, "complete"),
            observation,
            required_scope_json=SCOPE_JSON,
        )
        result = context.coverage(SCOPE)
        assert result.state == "complete" and not result.known_empty
        assert (
            tuple(context.db.execute("SELECT * FROM collection_terminals").fetchone())
            == original
        )
        assert (
            context.db.execute("SELECT count(*) FROM resource_relations").fetchone()[0]
            == 0
        )
    assert not (directory / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("encoded", [members(WRONG_OWNER), members(GENERIC)])
def test_stored_invalid_membership_stops_projection_and_fails_recovery(
    membership_db, directory, encoded
):
    db = membership_db
    trigger = db.execute(
        "SELECT sql FROM sqlite_schema WHERE type='trigger' AND name='collection_terminal_members_owner'"
    ).fetchone()[0]
    db.execute("DROP TRIGGER collection_terminal_members_owner")
    db.execute("PRAGMA ignore_check_constraints=ON")
    try:
        terminal(db, encoded)
        proof(db, encoded)
    finally:
        db.execute("PRAGMA ignore_check_constraints=OFF")
        db.execute(trigger)
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    # One case is structurally typed but has the wrong actual owner; the other
    # violates the known collection kind. Both are retained authority faults.
    with pytest.raises(BackupValidationError):
        validate_stored_checks(db, "context", retained_bytes=False)
        validate_stored_admission_guards(db, "context")
    db.execute("BEGIN")
    try:
        with pytest.raises(ContextError) as failure:
            with Context.for_snapshot(db, directory) as context:
                context.coverage(SCOPE)
        assert failure.value.code == "AUTHORITATIVE_CORRUPTION"
        assert isinstance(failure.value.__cause__, ValueError)
    finally:
        db.rollback()
    assert (directory / "p1-recovery-stop.json").is_file()
