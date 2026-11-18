"""Exact retired byte/key and transaction attacks on current owned authorities."""

import sqlite3
from contextlib import closing
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_repository import GitRepositoryStore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.repository_rows import ROW_TYPES as REPOSITORY_ROWS
from repo_catalog.domain.p1_repository import (
    OID,
    RelationGroup,
    RelationMember,
    RepositoryFailure,
    ScalarClaim,
    encode,
)
from tests.integration.p1.test_repository import (
    Budget,
    native,
    oid,
    provenance,
    repository_store,
)
from tests.integration.p3.test_production_context import context, directory

__all__ = ["repository_store", "context", "directory"]


def group():
    return RelationGroup(
        oid("c"),
        "commit_parents",
        "actual-original-complete-list",
        "complete",
        (RelationMember(0, oid("d")),),
        provenance(),
    )


def test_failed_inner_repository_unit_preserves_outer_writes_and_its_pinned_read(
    repository_store,
):
    reader, path, _ = repository_store
    with closing(connect(path, "repository")) as db:
        db.execute("BEGIN IMMEDIATE")
        with GitRepositoryStore.for_transaction(db) as unit:
            first = ScalarClaim(oid("a"), "type", "commit", provenance("first"))
            unit.admit_claim(first)
            assert unit.scalar(oid("a"), "type").alternatives
            assert reader.scalar(oid("a"), "type").alternatives == ()

            def fail():
                raise ValueError("actual original evidence failure")

            with pytest.raises(ValueError, match="actual original evidence failure"):
                unit.admit_group(group(), before_commit=fail)
            assert db.in_transaction
            assert unit.scalar(oid("a"), "type").alternatives
            assert unit.relations(oid("c"), "commit_parents").alternatives == ()
            unit.admit_object(oid("b"))
        assert db.in_transaction
        assert reader.scalar(oid("a"), "type").alternatives == ()
        db.execute("COMMIT")
    assert {tuple(row) for row in reader.sql("SELECT * FROM git_objects")} == {
        oid("a").key,
        oid("b").key,
    }
    assert reader.scalar(oid("a"), "type").alternatives
    assert not (path.parent / "p1-recovery-stop.json").exists()


def test_refused_repository_commit_rolls_back_the_entire_actual_unit(repository_store):
    owner, path, _ = repository_store
    original = owner._db

    class RefusingCommit:
        def __getattr__(self, name):
            return getattr(original, name)

        def execute(self, statement, *args, **kwargs):
            if statement == "COMMIT":
                assert original.in_transaction
                assert (
                    original.execute("SELECT count(*) FROM relation_groups").fetchone()[
                        0
                    ]
                    == 1
                )
                raise sqlite3.IntegrityError("injected deferred commit refusal")
            return original.execute(statement, *args, **kwargs)

    owner._db = RefusingCommit()
    try:
        with pytest.raises(sqlite3.IntegrityError, match="deferred commit refusal"):
            owner.admit_group(group())
    finally:
        owner._db = original
    assert not original.in_transaction
    assert owner.sql("SELECT * FROM git_objects") == []
    assert owner.sql("SELECT * FROM relation_groups") == []
    with closing(GitRepositoryStore(path)) as reopened:
        assert reopened.sql("SELECT * FROM git_objects") == []


@pytest.mark.parametrize("external", [False, True], ids=["owned", "savepoint"])
def test_failed_repository_rollback_preserves_original_error_and_prevents_later_commit(
    repository_store, external
):
    owner, path, _ = repository_store
    original_error = ValueError("actual original evidence failure")

    def fail():
        raise original_error

    class RefusingRollback:
        def __init__(self, db):
            self.original = db

        def __getattr__(self, name):
            return getattr(self.original, name)

        def execute(self, statement, *args, **kwargs):
            if statement == (
                "ROLLBACK TO p1_repository_unit" if external else "ROLLBACK"
            ):
                assert self.original.in_transaction
                raise sqlite3.OperationalError("injected rollback cleanup failure")
            return self.original.execute(statement, *args, **kwargs)

    original = connect(path, "repository") if external else owner._db
    if external:
        original.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(ValueError) as failure:
            if external:
                with GitRepositoryStore.for_transaction(original) as unit:
                    unit.admit_object(oid("a"))
                    unit._db = RefusingRollback(original)
                    unit.admit_group(group(), before_commit=fail)
            else:
                owner._db = RefusingRollback(original)
                owner.admit_group(group(), before_commit=fail)
        assert failure.value is original_error
        assert any("OperationalError" in note for note in failure.value.__notes__)
        # The actual failed-cleanup boundary must close before this caller can
        # commit. Test teardown must never establish this postcondition itself.
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            original.execute("COMMIT")
    finally:
        if external:
            original.close()
        else:
            owner._db = original
    with closing(GitRepositoryStore(path)) as reopened:
        assert reopened.sql("SELECT * FROM git_objects") == []
        assert reopened.sql("SELECT * FROM relation_groups") == []


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("shape", ["inside-width", "after-valid-prefix"])
def test_native_oid_cannot_hide_nonhex_bytes_after_nul_at_typed_or_sql_boundary(
    repository_store, fmt, shape
):
    owner, path, _ = repository_store
    width = 40 if fmt == "sha1" else 64
    value = (
        "a" * (width - 2) + "\0a"
        if shape == "inside-width"
        else "a" * width + "\0hidden"
    )
    with pytest.raises(RepositoryFailure) as failure:
        owner.admit_object(OID(fmt, value))
    assert failure.value.code == "IDENTITY"
    with closing(connect(path, "repository")) as db:
        before = db.execute("SELECT total_changes()").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO git_objects VALUES(?,?)", (fmt, value))
        assert db.execute("SELECT total_changes()").fetchone()[0] == before
        assert db.execute("SELECT count(*) FROM git_objects").fetchone()[0] == 0
    owner.admit_object(OID(fmt, "a" * width))
    assert len(owner.sql("SELECT * FROM git_objects")) == 1


def test_repository_uuid_cannot_hide_suffix_after_nul_in_typed_or_sql_admission(
    repository_store,
):
    owner, path, repository = repository_store
    value = str(uuid4()) + "\0hidden"
    with pytest.raises(RepositoryFailure):
        owner.admit_repository(value)
    with closing(connect(path, "repository")) as db:
        before = db.execute("SELECT total_changes()").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO repositories VALUES(?)", (value,))
        assert db.execute("SELECT total_changes()").fetchone()[0] == before
        assert [
            tuple(row)
            for row in db.execute("SELECT repository_uuidv4 FROM repositories")
        ] == [(repository,)]


@pytest.mark.parametrize(
    "column",
    [
        "object_format",
        "object_oid",
        "physical_copy_uuidv4",
        "native_type",
        "body",
        "size",
        "digest_sha256",
    ],
)
def test_actual_retained_native_copy_rejects_every_missing_required_component(
    repository_store, column
):
    owner, path, _ = repository_store
    metadata = native("tree", b"")
    owner.admit_metadata(metadata, str(uuid4()), Budget())
    row_type = REPOSITORY_ROWS["retained_metadata"]
    columns = row_type.WRITE_COLUMNS
    with closing(connect(path, "repository")) as db:
        original = dict(
            zip(
                row_type.COLUMNS,
                db.execute("SELECT * FROM retained_metadata").fetchone(),
                strict=True,
            )
        )
        attempted = {**original, "physical_copy_uuidv4": str(uuid4()), column: None}
        before = db.execute("SELECT total_changes()").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO retained_metadata("
                + ",".join(columns)
                + ") VALUES("
                + ",".join("?" for _ in columns)
                + ")",
                tuple(attempted[name] for name in columns),
            )
        assert db.execute("SELECT total_changes()").fetchone()[0] == before
        assert db.execute("SELECT count(*) FROM retained_metadata").fetchone()[0] == 1
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert owner.read_metadata(metadata.object_oid) == b""


def test_commit_tree_cannot_bind_an_independently_valid_foreign_format_oid(
    repository_store,
):
    owner, path, _ = repository_store
    subject, foreign = oid(), oid("b", "sha256")
    owner.admit_object(subject)
    owner.admit_object(foreign)
    with pytest.raises(RepositoryFailure) as failure:
        owner.admit_group(
            RelationGroup(
                subject,
                "commit_tree",
                "same-original",
                "complete",
                (RelationMember(0, foreign),),
                provenance(),
            )
        )
    assert failure.value.code == "GROUP"
    with closing(connect(path, "repository")) as db:
        before = db.execute("SELECT total_changes()").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO relation_groups VALUES(?,?,?,?,?,?,?)",
                (
                    *subject.key,
                    "commit_tree",
                    "same-original",
                    "complete",
                    encode([[0, *foreign.key]]),
                    provenance().encoded,
                ),
            )
        assert db.execute("SELECT total_changes()").fetchone()[0] == before
        assert db.execute("SELECT count(*) FROM relation_groups").fetchone()[0] == 0
    valid = replace(foreign, object_format="sha1", object_oid="b" * 40)
    owner.admit_group(
        RelationGroup(
            subject,
            "commit_tree",
            "same-original",
            "complete",
            (RelationMember(0, valid),),
            provenance(),
        )
    )
    assert owner.relations(subject, "commit_tree").alternatives


@pytest.mark.parametrize("case", ["non-uuid", "duplicate", "replica"])
def test_source_inventory_typed_and_sql_git_member_shapes_agree(context, case):
    from repo_catalog.adapters.sqlite.context_rows import ROW_TYPES
    from repo_catalog.domain.production_context import SourceInventory
    from tests.integration.p3.test_production_context import (
        PROVENANCE,
        REPO,
        SERVICE,
        SOURCE,
    )

    db, store, _ = context
    valid = SourceInventory(
        SOURCE,
        encode({"coverage_kind": "repositories", "service_instance_uuidv4": SERVICE}),
        10,
        "complete",
        True,
        (REPO,),
        PROVENANCE,
    )
    members = {
        "non-uuid": ("not-a-repository",),
        "duplicate": (REPO, REPO),
        "replica": ({"raw_api_response": {"body": "synthetic original"}},),
    }[case]
    with pytest.raises((RepositoryFailure, ValueError)):
        store.inventory(replace(valid, repositories=members))
    assert store.source_repositories(SOURCE) == ()
    assert (
        db.execute("SELECT count(*) FROM source_inventory_evidence").fetchone()[0] == 0
    )
    # Establish a genuine positive membership first: the hostile record cannot
    # be rejected merely because a permitted member or Source is unavailable.
    store.inventory(valid)
    row_type = ROW_TYPES["source_inventory_evidence"]
    attempted = dict(zip(row_type.WRITE_COLUMNS, valid.values, strict=True))
    attempted.update(observed_at_us=11, members_json=encode(list(members)))
    columns, values = row_type.insert_bindings(attempted)
    before = db.execute("SELECT total_changes()").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO source_inventory_evidence("
            + ",".join(columns)
            + ") VALUES("
            + ",".join("?" for _ in columns)
            + ")",
            values,
        )
    assert db.execute("SELECT total_changes()").fetchone()[0] == before
    assert (
        db.execute("SELECT count(*) FROM source_inventory_evidence").fetchone()[0] == 1
    )
    assert store.source_repositories(SOURCE) == (REPO,)


def test_unclosed_source_inventory_preserves_positive_report_without_complete_proof(
    context,
):
    from repo_catalog.adapters.sqlite.context_rows import ROW_TYPES
    from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope
    from repo_catalog.domain.production_context import SourceInventory
    from tests.integration.p3.test_production_context import (
        PROVENANCE,
        REPO,
        SERVICE,
        SOURCE,
    )

    db, store, _ = context
    original = SourceInventory(
        SOURCE,
        encode({"coverage_kind": "repositories", "service_instance_uuidv4": SERVICE}),
        10,
        "complete",
        False,
        (REPO,),
        PROVENANCE,
    )
    store.inventory(original)
    claim = CoverageClaim(
        CoverageScope.source_inventory(SOURCE, original.scope_json, "repositories"),
        10,
        "complete",
    )
    store.scope(claim.scope)
    store.admit_coverage(claim)
    assert store.coverage(claim.scope).state == "unknown"
    with pytest.raises(sqlite3.IntegrityError):
        store.prove_inventory(claim, original)
    row_type = ROW_TYPES["source_coverage_proofs"]
    values = (
        claim.scope.owner_kind,
        claim.scope.encoded,
        10,
        "complete",
        *original.values,
    )
    assert len(values) == len(row_type.WRITE_COLUMNS)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO source_coverage_proofs("
            + ",".join(row_type.WRITE_COLUMNS)
            + ") VALUES("
            + ",".join("?" for _ in values)
            + ")",
            values,
        )
    assert db.execute("SELECT count(*) FROM source_coverage_proofs").fetchone()[0] == 0
    assert store.source_repositories(SOURCE) == (REPO,)
    terminal = replace(original, observed_at_us=11, terminal=True)
    store.inventory(terminal)
    completed = replace(claim, observed_at_us=11)
    store.prove_inventory(completed, terminal)
    assert store.coverage(claim.scope).state == "complete"
    assert not store.coverage(claim.scope).known_empty


@pytest.mark.parametrize("member", [None, "sha1:0123", {"oid": "not-an-oid"}])
def test_root_enumeration_requires_structured_native_oid_members_in_typed_and_sql_admission(
    repository_store, member
):
    from repo_catalog.domain.p1_repository import GitObservation

    owner, path, repository = repository_store
    origin, capture = str(uuid4()), str(uuid4())
    value = {"roots": [member], "predecessor": None, "observed_at_us": 10}
    with pytest.raises((RepositoryFailure, ValueError, TypeError)):
        owner.admit_observation(
            GitObservation(
                origin,
                capture,
                repository,
                "snapshot",
                ("selected-roots",),
                value,
                provenance(),
            )
        )
    with closing(connect(path, "repository")) as db:
        before = db.execute("SELECT total_changes()").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO git_observations VALUES(?,?,?,?,?,?,?)",
                (
                    origin,
                    capture,
                    repository,
                    "snapshot",
                    encode(["selected-roots"]),
                    encode(value),
                    provenance().encoded,
                ),
            )
        assert db.execute("SELECT total_changes()").fetchone()[0] == before
        assert db.execute("SELECT count(*) FROM git_observations").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM git_objects").fetchone()[0] == 0
    genuine = oid()
    owner.admit_observation(
        GitObservation(
            origin,
            capture,
            repository,
            "snapshot",
            ("selected-roots",),
            {"roots": [list(genuine.key)], "predecessor": None, "observed_at_us": 10},
            provenance(),
        )
    )
    assert len(owner.sql("SELECT * FROM git_observations")) == 1
    assert owner.scalar(genuine, "type").canonical is None
    assert owner.sql("SELECT count(*) FROM retained_metadata")[0][0] == 0


@pytest.mark.parametrize(
    "attack",
    [
        "exact",
        "subset",
        "empty",
        "unrelated",
        "duplicate",
        "nonterminal",
        "stale",
        "unknown",
    ],
)
def test_complete_proof_quotes_one_actual_whole_terminal_without_subset_or_counter_repair(
    context, attack
):
    from repo_catalog.domain.p1_context import CoverageClaim, CoverageScope, ResourceKey
    from repo_catalog.domain.production_context import CollectionObservation
    from tests.integration.p3.test_production_context import (
        KEY,
        PR,
        PROVENANCE,
        SERVICE,
    )

    db, store, _ = context
    other = ResourceKey.from_native(SERVICE, "issue", "other")
    store.resource(PR)
    store.resource(other)
    kind = "exact-original-member-collection"
    observation = CollectionObservation(
        KEY,
        kind,
        PROVENANCE,
        encode({"coverage_kind": kind}),
        10,
        "complete",
        (KEY, PR),
    )
    store.collection(observation)
    claim = CoverageClaim(CoverageScope.resource(KEY, kind), 10, "complete")
    store.scope(claim.scope)
    store.admit_coverage(claim)
    assert store.coverage(claim.scope).state == "unknown"
    if attack == "exact":
        store.prove_collection(
            claim, observation, required_scope_json=observation.scope_json
        )
        assert store.coverage(claim.scope).state == "complete"
        assert not store.coverage(claim.scope).known_empty
        return

    changes = {
        "subset": {"members": (KEY,)},
        "empty": {"members": ()},
        "unrelated": {"members": (other,)},
        "duplicate": {"members": (KEY, KEY)},
        "nonterminal": {"state": "partial"},
        "stale": {"observed_at_us": 9},
        "unknown": {"observed_at_us": None},
    }[attack]
    with pytest.raises((sqlite3.IntegrityError, ValueError, TypeError)):
        altered = replace(observation, **changes)
        store.prove_collection(
            claim, altered, required_scope_json=observation.scope_json
        )
    terminal = list(observation.terminal)
    for field, value in changes.items():
        if field == "members":
            terminal[7] = encode([member.coordinates() for member in value])
        else:
            terminal[5 if field == "observed_at_us" else 6] = value
    before = db.execute("SELECT total_changes()").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO coverage_proofs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (claim.scope.owner_kind, claim.scope.encoded, 10, "complete", *terminal),
        )
    assert db.execute("SELECT total_changes()").fetchone()[0] == before
    assert db.execute("SELECT count(*) FROM coverage_proofs").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM collection_terminals").fetchone()[0] == 1
    assert store.coverage(claim.scope).state == "unknown"
    store.prove_collection(
        claim, observation, required_scope_json=observation.scope_json
    )
    assert store.coverage(claim.scope).state == "complete"
