"""Native byte/semantic controls missing from the retired decoder cohorts."""

import sqlite3
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.git_native import parse_metadata, parse_tree
from repo_catalog.domain.p1_core import (
    CoreFailure,
    GitObservation,
    Provenance,
    RelationGroup,
    RelationMember,
    ScalarClaim,
)
from tests.integration.p1.test_core import Budget, native, oid, provenance
from tests.integration.p2.test_native import commit_body, entry, git, repository, write

__all__ = ["repository"]


@pytest.mark.parametrize(
    "raw",
    [b"a\0b", b"\xff", b"large", b""],
    ids=["nul", "non-utf8", "oversize", "empty"],
)
def test_ordinary_file_decoder_shapes_are_excluded_without_archiving_any_body(
    core, repository, raw
):
    store, path, _ = core
    git_path, fmt = repository
    incoming = write(git_path, fmt, "blob", raw)
    with pytest.raises(CoreFailure) as source_error:
        GitNativeSource(git_path).metadata(incoming.object_oid)
    assert source_error.value.code == "RETENTION_PURPOSE"
    with pytest.raises(CoreFailure) as admission_error:
        store.admit_metadata(incoming, str(uuid4()), Budget())
    assert admission_error.value.code == "RETENTION_PURPOSE"
    assert store.sql("SELECT physical_copy_uuidv4 FROM retained_metadata") == []
    assert store.sql("SELECT physical_copy_uuidv4 FROM ref_retained_notes") == []
    assert not (path.parent / "p1-recovery-stop.json").exists()
    # Excluding the ordinary-file role must not disable genuine metadata input.
    accepted = native("tree", b"", fmt)
    store.admit_metadata(accepted, str(uuid4()), Budget())
    assert store.read_metadata(accepted.object_oid) == b""


@pytest.mark.parametrize(
    "semantic",
    [b"100644", b"100755", b"120000", b"160000", b"40000"],
    ids=["regular", "executable", "symlink", "gitlink", "directory"],
)
def test_real_git_leading_zero_tree_mode_preserves_oid_bytes_and_semantic_mode(
    core, repository, semantic
):
    store, _, _ = core
    path, fmt = repository
    target = oid("a", fmt)
    name = b"a\n\xff\t"
    canonical_body = entry(semantic, name, target)
    padded_body = entry(b"00" + semantic, name, target)
    canonical = write(path, fmt, "tree", canonical_body)
    # Git's default fsck policy rejects zeroPaddedFilemode on new writes. Seed
    # this historical spelling literally, then independently prove that real
    # ls-tree/cat-file consume it; this test makes no clean-fsck assertion.
    padded = write(path, fmt, "tree", padded_body, literal=True)
    assert canonical.object_oid != padded.object_oid
    expected_type = {b"40000": b"tree", b"160000": b"commit"}.get(semantic, b"blob")
    expected_listing = (
        semantic.rjust(6, b"0")
        + b" "
        + expected_type
        + b" "
        + target.object_oid.encode()
        + b"\t"
        + name
        + b"\0"
    )
    # Actual Git interpretation is the positive control, not just hash-object's
    # ability to store a literal body. Missing target objects are not fetched.
    assert (
        git(path, "ls-tree", "-z", canonical.object_oid.object_oid) == expected_listing
    )
    assert git(path, "ls-tree", "-z", padded.object_oid.object_oid) == expected_listing
    source = GitNativeSource(path)
    for incoming, body in [(canonical, canonical_body), (padded, padded_body)]:
        assert source.metadata(incoming.object_oid).body == body
        assert git(path, "cat-file", "tree", incoming.object_oid.object_oid) == body
        store.admit_metadata(
            source.metadata(incoming.object_oid), str(uuid4()), Budget()
        )
        assert store.read_metadata(incoming.object_oid) == body
        assert store.relations(incoming.object_oid, "tree_entries").canonical == [
            "complete",
            [[[semantic.decode(), name.hex()], *target.key]],
        ]
        assert parse_tree(fmt, body) == {name: (semantic, target.object_oid)}
    assert store.scalar(target, "size").canonical is None
    assert len(store.sql("SELECT physical_copy_uuidv4 FROM retained_metadata")) == 2


@pytest.mark.parametrize(
    "mode",
    [
        b"100648",
        b"100644x",
        b"-100644",
        b"+100644",
        b"100600",
        b"000",
        b"20000",
        b"0o100644",
    ],
    ids=[
        "invalid-digit",
        "suffix",
        "negative",
        "positive-sign",
        "unsupported-permissions",
        "zero",
        "unsupported-kind",
        "python-prefix",
    ],
)
@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_unsupported_or_non_octal_tree_modes_are_rejected_without_partial_admission(
    core, mode, fmt
):
    store, path, _ = core
    incoming = native("tree", entry(mode, b"name", oid("a", fmt)), fmt)
    incoming.validate()  # Hash matching is insufficient to prove native grammar.
    with pytest.raises(CoreFailure) as error:
        store.admit_metadata(incoming, str(uuid4()), Budget())
    assert error.value.code == "NATIVE_SYNTAX"
    assert store.sql("SELECT * FROM git_objects") == []
    assert store.sql("SELECT physical_copy_uuidv4 FROM retained_metadata") == []
    assert not (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("mode", ["autocommit", "transaction", "savepoint"])
def test_original_capture_snapshot_coordinates_and_facts_cannot_be_rebound(core, mode):
    store, path, repository = core
    store.admit_repository(repository)
    observation = GitObservation(
        str(uuid4()),
        str(uuid4()),
        repository,
        "snapshot",
        ("requested-scope",),
        {"roots": [], "predecessor": None, "observed_at_us": 1},
        provenance(),
    )
    store.admit_observation(observation)
    db = connect(path, "core")
    try:
        original = [tuple(row) for row in db.execute("SELECT * FROM git_observations")]
        if mode == "transaction":
            db.execute("BEGIN")
        elif mode == "savepoint":
            db.execute("SAVEPOINT attack")
        for column in (
            "capture_origin_uuidv4",
            "capture_uuidv4",
            "repository_uuidv4",
            "kind",
            "scope",
            "value",
            "provenance",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable core fact"):
                db.execute(f'UPDATE git_observations SET "{column}"=?', ("forged",))
        with pytest.raises(sqlite3.IntegrityError, match="immutable core fact"):
            db.execute("DELETE FROM git_observations")
        with pytest.raises(sqlite3.IntegrityError, match="immutable core fact"):
            db.execute(
                "INSERT OR REPLACE INTO git_observations SELECT * FROM git_observations"
            )
        assert [
            tuple(row) for row in db.execute("SELECT * FROM git_observations")
        ] == original
        if mode == "transaction":
            db.execute("ROLLBACK")
        elif mode == "savepoint":
            db.execute("ROLLBACK TO attack")
            db.execute("RELEASE attack")
        assert not db.in_transaction
    finally:
        db.close()
    assert tuple(store.sql("SELECT * FROM git_observations")[0]) == observation.key


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_long_zero_prefix_is_normalized_without_an_unbounded_integer_conversion(fmt):
    target = oid("a", fmt)
    body = entry(b"0" * 10_000 + b"100644", b"name", target)
    parsed = parse_metadata(fmt, "tree", body)
    assert parsed.relations["tree_entries"] == [
        [["100644", b"name".hex()], *target.key]
    ]
    assert parsed.scalars["size"] == len(body)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("family", ["message", "author", "tree-name"])
@pytest.mark.parametrize(
    "false_first", [True, False], ids=["false-first", "real-first"]
)
def test_actual_ddl_refuses_fabricated_checked_values_in_both_arrival_orders(
    core, fmt, family, false_first
):
    store, path, _ = core
    target = oid("a", fmt)
    name = b"caf\xc3\xa9.txt"
    incoming = (
        native("tree", entry(b"100644", name, target), fmt)
        if family == "tree-name"
        else native(
            "commit", commit_body(target, message=b"genuine caf\xc3\xa9 message"), fmt
        )
    )
    physical = str(uuid4())
    store.admit_object(target)
    store.admit_object(incoming.object_oid)
    if not false_first:
        store.admit_metadata(incoming, physical, Budget())
    receiver_claim = Provenance(
        "independent.supported.producer",
        "attempt",
        family,
        "independent.native.sql",
        "unranked",
        "receiver_intrinsic",
    )
    if family == "tree-name":
        false = RelationGroup(
            incoming.object_oid,
            "tree_entries",
            "forged-name",
            "complete",
            (RelationMember(["100644", b"fabricated-name".hex()], target),),
            receiver_claim,
        )
        source_table, checked_table = "relation_groups", "intrinsic_groups"
    else:
        false = ScalarClaim(
            incoming.object_oid,
            family,
            "fabricated byte interpretation",
            receiver_claim,
        )
        source_table, checked_table = "scalar_claims", "intrinsic_claims"
    db = connect(path, "core")
    try:
        db.execute("BEGIN")
        if false_first:
            db.execute(
                "INSERT INTO retained_metadata VALUES(?,?,?,?,?,?,?)",
                (
                    *incoming.object_oid.key,
                    physical,
                    incoming.native_type,
                    incoming.body,
                    incoming.declared_size,
                    incoming.digest_sha256,
                ),
            )
        db.execute(
            f"INSERT INTO {source_table} VALUES({','.join('?' for _ in false.key)})",
            false.key,
        )
        with pytest.raises(sqlite3.IntegrityError, match="checked intrinsic scope"):
            values = (*false.key, physical)
            db.execute(
                f"INSERT INTO {checked_table} VALUES({','.join('?' for _ in values)})",
                values,
            )
        db.rollback()
        assert not db.in_transaction
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        db.close()
    if false_first:
        store.admit_metadata(incoming, physical, Budget())
    assert store.read_metadata(incoming.object_oid) == incoming.body
    if family == "tree-name":
        projection = store.relations(incoming.object_oid, "tree_entries")
        assert projection.canonical == [
            "complete",
            [[["100644", name.hex()], *target.key]],
        ]
        reported = RelationGroup(
            incoming.object_oid,
            "tree_entries",
            "original-report",
            "complete",
            false.members,
            provenance("contradictory report"),
        )
        store.admit_group(reported)
        after = store.relations(incoming.object_oid, "tree_entries")
    else:
        projection = store.scalar(incoming.object_oid, family)
        expected = (
            "genuine caf\u00e9 message"
            if family == "message"
            else "A\udcff <a@invalid> 1 +0930"
        )
        assert projection.canonical == ["known", expected]
        store.admit_claim(
            ScalarClaim(
                incoming.object_oid,
                family,
                "fabricated byte interpretation",
                provenance("contradictory report"),
            )
        )
        after = store.scalar(incoming.object_oid, family)
    # ADR 0014 preserves attributed contradictory reports; their presence never
    # promotes fabricated bytes into receiver-checked canonical interpretation.
    assert after.canonical == projection.canonical
    assert after.reported_conflict
    assert len(store.sql("SELECT physical_copy_uuidv4 FROM retained_metadata")) == 1
    assert not (path.parent / "p1-recovery-stop.json").exists()
