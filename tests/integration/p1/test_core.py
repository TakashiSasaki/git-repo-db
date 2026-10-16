"""Adversarial executable P1 Core contracts against composed packaged DDL."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_core import Core
from repo_catalog.adapters.sqlite.p1_schema import connect, initialize
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreFailure,
    GitObservation,
    NativeObject,
    Provenance,
    RelationGroup,
    RelationMember,
    RepositoryClaim,
    ScalarClaim,
    encode,
    native_oid,
)


class Budget:
    class Limits:
        note_bytes = 1024 * 1024

    limits = Limits()

    def __init__(self):
        self.counts = {}

    def require(self, unit, amount=1):
        assert type(amount) is int and amount >= 0

    def charge(self, unit, amount):
        self.counts[unit] = self.counts.get(unit, 0) + amount


def provenance(observation="original", coordinate="field"):
    return Provenance("original-source", observation, coordinate, "source-parser", "1")


def oid(letter="a", fmt="sha1"):
    return OID(fmt, letter * (40 if fmt == "sha1" else 64))


def native(kind, body, fmt="sha1"):
    return NativeObject(
        OID(fmt, native_oid(fmt, kind, body)),
        kind,
        body,
        len(body),
        hashlib.sha256(body).hexdigest(),
    )


@pytest.fixture
def core(tmp_path):
    repository = str(uuid4())
    path = tmp_path / "core.sqlite3"
    initialize(path, "core", repository, str(uuid4()))
    result = Core(path)
    result.admit_repository(repository)
    yield result, path, repository
    result.close()


def test_metadata_only_core_without_context_reopen_and_unknown_size(core):
    c, path, _ = core
    c.admit_object(oid())
    c.admit_claim(ScalarClaim(oid(), "size", None, provenance()))
    assert c.scalar(oid(), "size").alternatives[0]["value"] == ["unknown"]
    assert c.scalar(oid(), "type").canonical is None
    with pytest.raises(CoreFailure, match="metadata-only") as error:
        c.read_metadata(oid())
    assert error.value.code == "BYTES_UNAVAILABLE"
    other = Core(path)
    try:
        assert len(other.scalar(oid(), "size").alternatives) == 1
        assert not (path.parent / "context.sqlite3").exists()
    finally:
        other.close()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE git_objects SET full_oid=full_oid",
        "DELETE FROM git_objects",
        "INSERT OR REPLACE INTO git_objects VALUES('sha1','" + "a" * 40 + "')",
        "CREATE TABLE unauthorized(value TEXT)",
        "DROP TABLE git_objects",
        "PRAGMA recursive_triggers=OFF",
        "PRAGMA foreign_keys=OFF",
        "ATTACH ':memory:' AS loophole",
        "BEGIN",
    ],
)
def test_supported_connection_rejects_arbitrary_operations(core, sql):
    c, _, _ = core
    c.admit_object(oid())
    with pytest.raises(sqlite3.DatabaseError):
        c.sql(sql)
    assert len(c.sql("SELECT * FROM git_objects")) == 1


@pytest.mark.parametrize(
    "action",
    [
        "UPDATE git_objects SET full_oid=full_oid",
        "DELETE FROM git_objects",
        "INSERT OR REPLACE INTO git_objects SELECT * FROM git_objects",
    ],
)
def test_triggers_reject_mutation_on_infrastructure_connection(core, action):
    c, path, _ = core
    c.admit_object(oid())
    db = connect(path, "core")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(action)
        assert db.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
    finally:
        db.close()


def test_cached_statement_authorization_does_not_leak(core):
    c, _, _ = core
    # Same INSERT text was just prepared under the internal capability.
    c.admit_object(oid())
    with pytest.raises(sqlite3.DatabaseError):
        c.sql(
            "INSERT INTO git_objects VALUES(?,?) ON CONFLICT DO NOTHING", oid("b").key
        )
    assert len(c.sql("SELECT * FROM git_objects")) == 1


def test_exact_claim_replay_monotonic_later_evidence_conflicts_and_bad_replay(core):
    c, _, _ = core
    first = ScalarClaim(oid(), "type", "tree", provenance())
    c.admit_claim(first)
    c.admit_claim(first)
    with pytest.raises(CoreFailure, match="immutable evidence"):
        c.admit_claim(replace(first, value="blob"))
    c.admit_claim(replace(first, value="blob", provenance=provenance("independent")))
    result = c.scalar(oid(), "type")
    assert result.reported_conflict and result.canonical is None
    assert len(result.alternatives) == 2


def test_ordered_groups_are_whole_atomic_and_never_union(core):
    c, _, _ = core
    group = RelationGroup(
        oid(),
        "commit_parents",
        "reported entire list",
        "partial",
        (RelationMember(3, oid("b")),),
        provenance(),
    )
    c.admit_group(group)
    c.admit_group(group)
    with pytest.raises(CoreFailure):
        c.admit_group(replace(group, members=(RelationMember(3, oid("c")),)))
    c.admit_group(
        replace(
            group,
            members=(RelationMember(3, oid("c")),),
            provenance=provenance("alternative"),
        )
    )
    assert c.relations(oid(), "commit_parents").reported_conflict
    before = [tuple(row) for row in c.sql("SELECT * FROM git_objects")]
    complete = RelationGroup(
        oid("d"),
        "commit_parents",
        "reported entire list",
        "complete",
        (RelationMember(0, oid("e")),),
        provenance(),
    )

    def crash():
        raise RuntimeError("before local commit")

    with pytest.raises(RuntimeError):
        c.admit_group(complete, before_commit=crash)
    assert [tuple(row) for row in c.sql("SELECT * FROM git_objects")] == before
    assert c.relations(oid("d"), "commit_parents").alternatives == ()


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_verified_commit_bounded_canonical_preserves_reports_and_no_closure(core, fmt):
    c, _, _ = core
    tree, parent = oid("a", fmt), oid("b", fmt)
    body = f"tree {tree.full_oid}\nparent {parent.full_oid}\nauthor A <a@invalid> 0 +0000\ncommitter C <c@invalid> 0 +0000\n\nmessage\n".encode()
    commit = native("commit", body, fmt)
    c.admit_claim(ScalarClaim(commit.oid, "type", "blob", provenance()))
    c.admit_claim(
        ScalarClaim(
            commit.oid, "author", "claimed author", provenance(coordinate="author")
        )
    )
    c.admit_metadata(commit, str(uuid4()), Budget())
    assert c.scalar(commit.oid, "type").canonical == ["known", "commit"]
    assert c.scalar(commit.oid, "type").reported_conflict
    assert c.scalar(commit.oid, "author").canonical is None
    assert c.relations(commit.oid, "commit_parents").canonical == [
        "complete",
        [[0, *parent.key]],
    ]
    assert c.read_metadata(commit.oid) == body
    assert len(c.sql("SELECT physical_copy_uuidv4 FROM retained_metadata")) == 1
    assert len(c.sql("SELECT * FROM git_objects")) == 3


def test_untrusted_report_cannot_assert_local_verification(core):
    c, _, _ = core
    claimed = replace(provenance(), qualification="receiver_intrinsic")
    with pytest.raises(CoreFailure) as error:
        c.admit_claim(ScalarClaim(oid(), "type", "commit", claimed))
    assert error.value.code == "UNTRUSTED_VERIFICATION"
    assert c.sql("SELECT * FROM intrinsic_claims") == []


def test_native_body_and_intrinsic_scope_cannot_be_forged_in_sql(core):
    c, path, _ = core
    metadata = native("tree", b"")
    copy = str(uuid4())
    c.admit_metadata(metadata, copy, Budget())
    claim = ScalarClaim(metadata.oid, "author", "forged author", provenance())
    c.admit_claim(claim)
    db = connect(path, "core")
    try:
        with pytest.raises(sqlite3.IntegrityError, match="checked intrinsic scope"):
            db.execute(
                "INSERT INTO intrinsic_claims VALUES(?,?,?,?,?,?)", (*claim.key, copy)
            )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            db.execute(
                "INSERT INTO retained_metadata VALUES(?,?,?,?,?,?,?)",
                (
                    *oid().key,
                    str(uuid4()),
                    "tree",
                    b"",
                    0,
                    hashlib.sha256(b"").hexdigest(),
                ),
            )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        db.close()


@pytest.mark.parametrize("value", [None, 1, 2**63 - 1])
def test_nullable_positive_epoch_microseconds_and_observations(core, value):
    c, _, repository = core
    observation = GitObservation(
        str(uuid4()),
        str(uuid4()),
        repository,
        "ref",
        ("refs/heads/main",),
        {
            "ref": "refs/heads/main",
            "target": list(oid().key),
            "peeled": None,
            "observed_at_us": value,
        },
        provenance(),
    )
    c.admit_observation(observation)
    c.admit_observation(observation)
    c.admit_repository_claim(
        RepositoryClaim(repository, "observation_us", value, provenance())
    )
    assert len(c.sql("SELECT * FROM git_observations")) == 1


@pytest.mark.parametrize("value", [True, 1.5, -(2**63) - 1, 2**63])
def test_bad_epoch_microseconds_rejected(core, value):
    _, _, repository = core
    with pytest.raises(CoreFailure):
        RepositoryClaim(repository, "observation_us", value, provenance())


def test_multiple_repositories_share_nominal_object_with_distinct_capture(core):
    c, _, first = core
    second = str(uuid4())
    c.admit_repository(second)
    origin = str(uuid4())
    for repository in (first, second):
        c.admit_capture(
            Capture(
                origin,
                str(uuid4()),
                repository,
                "local-git",
                "refs/notes/commits",
                oid(),
            )
        )
    assert len(c.sql("SELECT * FROM git_objects")) == 1
    assert len(c.sql("SELECT * FROM captures")) == 2
    assert len(c.sql("SELECT * FROM repositories")) == 2


def test_retained_physical_copies_are_real_distinct_domain_occurrences(core):
    c, _, _ = core
    metadata = native("tree", b"")
    first, second = str(uuid4()), str(uuid4())
    c.admit_metadata(metadata, first, Budget())
    c.admit_metadata(metadata, first, Budget())
    c.admit_metadata(metadata, second, Budget())
    assert len(c.sql("SELECT physical_copy_uuidv4 FROM retained_metadata")) == 2
    assert len(c.sql("SELECT * FROM git_objects")) == 1


def test_lossless_group_semantic_value_is_not_hash_alias():
    member = RelationMember(
        ("100644", b"strange\xffname".hex(), b"dir/strange\xffname".hex(), 27), oid()
    )
    group = RelationGroup(
        oid("b"), "tree_entries", "subtree path", "partial", (member,), provenance()
    )
    assert group.membership == encode([[list(member.coordinate), *member.target.key]])
    assert "737472616e6765ff6e616d65" in group.membership


def test_transaction_bound_core_owns_units_not_outer_commit(core):
    c, path, _ = core
    db = connect(path, "core")
    db.execute("BEGIN IMMEDIATE")
    try:
        with Core.for_transaction(db) as unit:
            unit.admit_claim(ScalarClaim(oid(), "type", "commit", provenance()))
            assert db.in_transaction
            assert c.scalar(oid(), "type").alternatives == ()
        with pytest.raises(CoreFailure, match="expired"):
            unit.admit_object(oid("b"))
        db.execute("ROLLBACK")
        assert c.scalar(oid(), "type").alternatives == ()
        with pytest.raises(CoreFailure, match="active coordinator"):
            with Core.for_transaction(db):
                pass
    finally:
        db.close()


@pytest.mark.parametrize("closed_count,partial_slot", [(0, 0), (1, 1)])
@pytest.mark.parametrize("reverse", [False, True])
def test_closed_group_excludes_later_positive_slot_in_same_scope(
    core, closed_count, partial_slot, reverse
):
    c, _, _ = core
    closed = RelationGroup(
        oid(),
        "commit_parents",
        "entire list",
        "complete" if closed_count else "known_empty",
        (RelationMember(0, oid("b")),) if closed_count else (),
        provenance("closed"),
    )
    partial = RelationGroup(
        oid(),
        "commit_parents",
        "entire list",
        "partial",
        (RelationMember(partial_slot, oid("c")),),
        provenance("partial"),
    )
    for group in (partial, closed) if reverse else (closed, partial):
        c.admit_group(group)
    assert c.relations(oid(), "commit_parents").reported_conflict


def test_closed_group_does_not_exclude_unrelated_scope(core):
    c, _, _ = core
    c.admit_group(
        RelationGroup(
            oid(),
            "commit_parents",
            "entire list",
            "known_empty",
            (),
            provenance("closed"),
        )
    )
    c.admit_group(
        RelationGroup(
            oid(),
            "commit_parents",
            "different scope",
            "partial",
            (RelationMember(0, oid("b")),),
            provenance("partial"),
        )
    )
    assert not c.relations(oid(), "commit_parents").reported_conflict


def test_core_coverage_five_columns_semantic_fk_latest_unknown_and_empty(core):
    from repo_catalog.domain.p1_core import CoreCoverageScope
    from repo_catalog.domain.p1_coverage import CoverageClaim

    c, path, repository = core
    scope = CoreCoverageScope("repository", (repository, "git-ref-inventory"))
    c.admit_coverage_scope(scope)
    assert c.coverage(scope).state == "unknown"
    assert c.coverage(scope).observed_at_us is None
    complete = CoverageClaim(scope, 1, "complete", '{"advisory":"first"}')
    assert c.admit_coverage(complete) == "insert"
    assert not c.coverage(scope).known_empty
    c.admit_coverage_proof(complete, (), provenance("terminal empty"))
    assert c.coverage(scope).known_empty
    assert (
        c.admit_coverage(replace(complete, details_json='{"advisory":"duplicate"}'))
        == "duplicate"
    )
    assert c.admit_coverage(CoverageClaim(scope, 2, "unknown")) == "insert"
    assert c.admit_coverage(complete) == "stale"
    assert c.coverage(scope).state == "unknown"
    assert not c.coverage(scope).known_empty
    assert c.admit_coverage(CoverageClaim(scope, 2, "partial")) == "insert"
    assert c.admit_coverage(CoverageClaim(scope, 2, "complete")) == "insert"
    assert c.coverage(scope).state == "conflict"
    db = connect(path, "core")
    try:
        assert len(db.execute("PRAGMA table_xinfo(coverage_claims)").fetchall()) == 5
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.execute(
                "INSERT INTO core_coverage_proofs VALUES(?,?,?,?,?,?)",
                (
                    scope.owner_kind,
                    scope.encoded,
                    999,
                    "complete",
                    "[]",
                    provenance().encoded,
                ),
            )
    finally:
        db.close()


def test_core_typed_observation_ddl_rejects_opaque_payload_and_false_terminal(core):
    c, path, repository = core
    event = GitObservation(
        str(uuid4()),
        str(uuid4()),
        repository,
        "ref",
        ("refs/heads/main",),
        {"ref": "refs/heads/main", "target": list(oid().key), "observed_at_us": 1},
        provenance(),
    )
    with pytest.raises(CoreFailure, match="terminal"):
        replace(event, value={**event.value, "enumeration_state": "complete"})
    db = connect(path, "core")
    try:
        values = (
            *event.key[:5],
            '{"body":"ordinary bytes","observed_at_us":1}',
            event.key[-1],
        )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            db.execute("INSERT INTO git_observations VALUES(?,?,?,?,?,?,?)", values)
    finally:
        db.close()
    with pytest.raises(CoreFailure):
        ScalarClaim(oid(), "raw_text", "ordinary file text", provenance())


def test_coverage_projection_pins_claims_and_proofs_across_concurrent_write(core):
    from repo_catalog.domain.p1_core import CoreCoverageScope
    from repo_catalog.domain.p1_coverage import CoverageClaim

    c, path, repository = core
    scope = CoreCoverageScope("repository", (repository, "git-ref-inventory"))
    c.admit_coverage_scope(scope)
    claim = CoverageClaim(scope, 10, "complete")
    c.admit_coverage(claim)
    c.admit_coverage_proof(claim, (), provenance("terminal"))
    writer = Core(path)
    injected = []

    def concurrent_write(statement):
        if (
            "SELECT members_json FROM core_coverage_proofs" in statement
            and not injected
        ):
            writer.admit_coverage(CoverageClaim(scope, 11, "unknown"))
            injected.append(True)

    c._db.set_trace_callback(concurrent_write)
    try:
        snapshot = c.coverage(scope)
        assert injected == [True]
        assert (snapshot.state, snapshot.observed_at_us, snapshot.known_empty) == (
            "complete",
            10,
            True,
        )
    finally:
        c._db.set_trace_callback(None)
        writer.close()
    assert c.coverage(scope).state == "unknown"
    assert c.coverage(scope).observed_at_us == 11


@pytest.mark.parametrize(
    "membership", ['[["sha1","not-an-oid"]]', '[{"storage_row_id":42}]']
)
def test_core_coverage_rejects_malformed_members_on_supported_transaction(
    core, membership
):
    from repo_catalog.adapters.sqlite.p1_coordination import AdmissionTransaction
    from repo_catalog.domain.p1_core import CoreCoverageScope
    from repo_catalog.domain.p1_coverage import CoverageClaim

    c, path, repository = core
    scope = CoreCoverageScope("repository", (repository, "git-ref-inventory"))
    c.admit_coverage_scope(scope)
    c.admit_coverage(CoverageClaim(scope, 1, "complete"))
    db = connect(path, "core")
    try:
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            AdmissionTransaction(db).execute(
                "INSERT INTO core_coverage_proofs VALUES(?,?,?,?,?,?)",
                (
                    scope.owner_kind,
                    scope.encoded,
                    1,
                    "complete",
                    membership,
                    provenance().encoded,
                ),
            )
    finally:
        db.set_authorizer(None)
        db.rollback()
        db.close()


def test_core_coverage_rejects_valid_typed_missing_nominal_member(core):
    from repo_catalog.adapters.sqlite.p1_coordination import AdmissionTransaction
    from repo_catalog.domain.p1_core import CoreCoverageScope
    from repo_catalog.domain.p1_coverage import CoverageClaim

    c, path, repository = core
    scope = CoreCoverageScope("repository", (repository, "git-ref-inventory"))
    c.admit_coverage_scope(scope)
    claim = CoverageClaim(scope, 1, "complete")
    c.admit_coverage(claim)
    assert c.coverage(scope).state == "unknown"  # no actual terminal proof
    db = connect(path, "core")
    try:
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(
            sqlite3.IntegrityError, match="missing nominal Core Coverage member"
        ):
            AdmissionTransaction(db).execute(
                "INSERT INTO core_coverage_proofs VALUES(?,?,?,?,?,?)",
                (
                    scope.owner_kind,
                    scope.encoded,
                    1,
                    "complete",
                    encode([oid().key]),
                    provenance().encoded,
                ),
            )
    finally:
        db.set_authorizer(None)
        db.rollback()
        db.close()
    c.admit_coverage_proof(claim, (oid(),), provenance())
    assert c.coverage(scope).state == "complete"
    assert not c.coverage(scope).known_empty


@pytest.mark.parametrize(
    "mode,target", [("100755", "c"), ("100755", "b"), ("100644", "c")]
)
@pytest.mark.parametrize("reverse", [False, True])
def test_tree_entry_conflicts_use_name_slot_and_mode_target_values(
    core, mode, target, reverse
):
    c, _, _ = core
    first = RelationGroup(
        oid(),
        "tree_entries",
        "native tree",
        "partial",
        (RelationMember(("100644", "61"), oid("b")),),
        provenance("first"),
    )
    second = RelationGroup(
        oid(),
        "tree_entries",
        "native tree",
        "partial",
        (RelationMember((mode, "61"), oid(target)),),
        provenance("second"),
    )
    for group in (second, first) if reverse else (first, second):
        c.admit_group(group)
    assert c.relations(oid(), "tree_entries").reported_conflict


def test_unknown_position_and_out_of_order_parents_preserve_actual_evidence(core):
    c, _, _ = core
    group = RelationGroup(
        oid(),
        "commit_parents",
        "observed membership",
        "partial",
        (
            RelationMember(None, oid("b")),
            RelationMember(7, oid("c")),
            RelationMember(2, oid("d")),
        ),
        provenance(),
    )
    c.admit_group(group)
    c.admit_group(group)
    projection = c.relations(oid(), "commit_parents")
    assert projection.alternatives[0]["membership"] == [
        [2, *oid("d").key],
        [7, *oid("c").key],
        [None, *oid("b").key],
    ]
    assert not projection.reported_conflict
    assert projection.canonical is None


@pytest.mark.parametrize("unknown_target,conflict", [("b", False), ("c", True)])
def test_unknown_parent_position_compares_membership_without_fake_slot(
    core, unknown_target, conflict
):
    c, _, _ = core
    closed = RelationGroup(
        oid(),
        "commit_parents",
        "same scope",
        "complete",
        (RelationMember(0, oid("b")),),
        provenance("closed"),
    )
    unpositioned = RelationGroup(
        oid(),
        "commit_parents",
        "same scope",
        "partial",
        (RelationMember(None, oid(unknown_target)),),
        provenance("unpositioned"),
    )
    c.admit_group(closed)
    c.admit_group(unpositioned)
    assert c.relations(oid(), "commit_parents").reported_conflict is conflict


def test_corrupt_core_open_persists_catalog_stop_before_propagating(tmp_path):
    path = tmp_path / "core.sqlite3"
    path.write_bytes(b"not a SQLite database" * 100)
    with pytest.raises(sqlite3.DatabaseError):
        Core(path)
    assert (tmp_path / "p1-recovery-stop.json").is_file()
    with pytest.raises(CoreFailure) as error:
        Core(path)
    assert error.value.code == "RECOVERY_STOP"


def test_parent_group_transport_reorder_is_exact_replay_not_new_claim(core):
    c, _, _ = core
    group = RelationGroup(
        oid(),
        "commit_parents",
        "membership subset",
        "partial",
        (
            RelationMember(7, oid("c")),
            RelationMember(None, oid("e")),
            RelationMember(2, oid("d")),
            RelationMember(None, oid("b")),
        ),
        provenance(),
    )
    reversed_group = replace(group, members=tuple(reversed(group.members)))
    assert group.key == reversed_group.key
    c.admit_group(group)
    c.admit_group(reversed_group)
    assert len(c.relations(oid(), "commit_parents").alternatives) == 1
    assert group.membership == encode(
        [
            [2, *oid("d").key],
            [7, *oid("c").key],
            [None, *oid("b").key],
            [None, *oid("e").key],
        ]
    )


@pytest.mark.parametrize("relation", ["commit_parents", "tree_entries"])
@pytest.mark.parametrize("reverse", [False, True])
def test_explicit_intrinsic_slot_conflicts_across_observation_scopes(
    core, relation, reverse
):
    c, _, _ = core
    coordinate = 0 if relation == "commit_parents" else ("100644", "61")
    first = RelationGroup(
        oid(),
        relation,
        "source-A fragment",
        "partial",
        (RelationMember(coordinate, oid("b")),),
        provenance("source-A"),
    )
    second = RelationGroup(
        oid(),
        relation,
        "source-B fragment",
        "partial",
        (RelationMember(coordinate, oid("c")),),
        provenance("source-B"),
    )
    for group in (second, first) if reverse else (first, second):
        c.admit_group(group)
    assert c.relations(oid(), relation).reported_conflict
    assert len(c.relations(oid(), relation).alternatives) == 2


@pytest.mark.parametrize("reverse", [False, True])
def test_explicit_tree_mode_conflicts_across_observation_scopes(core, reverse):
    c, _, _ = core
    first = RelationGroup(
        oid(),
        "tree_entries",
        "source-A fragment",
        "partial",
        (RelationMember(("100644", "61"), oid("b")),),
        provenance("source-A"),
    )
    second = RelationGroup(
        oid(),
        "tree_entries",
        "source-B fragment",
        "partial",
        (RelationMember(("100755", "61"), oid("b")),),
        provenance("source-B"),
    )
    for group in (second, first) if reverse else (first, second):
        c.admit_group(group)
    assert c.relations(oid(), "tree_entries").reported_conflict


@pytest.mark.parametrize("relation", ["commit_parents", "tree_entries"])
@pytest.mark.parametrize("same_slot", [False, True])
def test_cross_observation_compatible_positive_slots_do_not_conflict(
    core, relation, same_slot
):
    c, _, _ = core
    first_slot = 0 if relation == "commit_parents" else ("100644", "61")
    second_slot = (
        first_slot
        if same_slot
        else (1 if relation == "commit_parents" else ("100644", "62"))
    )
    c.admit_group(
        RelationGroup(
            oid(),
            relation,
            "source-A fragment",
            "partial",
            (RelationMember(first_slot, oid("b")),),
            provenance("source-A"),
        )
    )
    c.admit_group(
        RelationGroup(
            oid(),
            relation,
            "source-B fragment",
            "partial",
            (RelationMember(second_slot, oid("b")),),
            provenance("source-B"),
        )
    )
    assert not c.relations(oid(), relation).reported_conflict


@pytest.mark.parametrize(
    "has_parent,report_slot,report_target,conflict",
    [
        (False, 0, "c", True),
        (True, 1, "c", True),
        (True, 0, "b", False),
        (True, None, "b", False),
        (True, None, "c", True),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_checked_native_full_parent_group_excludes_across_observation_scopes(
    core, has_parent, report_slot, report_target, conflict, reverse
):
    c, _, _ = core
    parent_line = f"parent {oid('b').full_oid}\n" if has_parent else ""
    body = f"tree {oid().full_oid}\n{parent_line}author A <a@invalid> 0 +0000\ncommitter C <c@invalid> 0 +0000\n\nmessage\n".encode()
    commit = native("commit", body)
    report = RelationGroup(
        commit.oid,
        "commit_parents",
        "source-observation-A",
        "partial",
        (RelationMember(report_slot, oid(report_target)),),
        provenance("separate-source"),
    )
    if reverse:
        c.admit_group(report)
        c.admit_metadata(commit, str(uuid4()), Budget())
    else:
        c.admit_metadata(commit, str(uuid4()), Budget())
        c.admit_group(report)
    projection = c.relations(commit.oid, "commit_parents")
    expected = ["complete", [[0, *oid("b").key]]] if has_parent else ["known_empty", []]
    assert projection.canonical == expected
    assert projection.reported_conflict is conflict
    assert len(projection.alternatives) == 2
