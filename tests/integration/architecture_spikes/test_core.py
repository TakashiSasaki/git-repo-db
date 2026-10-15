"""Adversarial assertions for the isolated append-only Core experiment."""

import hashlib
import sqlite3
from uuid import uuid4

import pytest

from tests.integration.architecture_spikes.core import (
    OID,
    Core,
    Parent,
    ParentGroup,
    Provenance,
)


@pytest.fixture
def core(tmp_path):
    instance = Core(tmp_path / "core.sqlite3")
    yield instance
    instance.close()


def oid(letter="a", object_format="sha1"):
    return OID(object_format, letter * (40 if object_format == "sha1" else 64))


def evidence(observation="source-snapshot-1", coordinate="reported-field"):
    return Provenance(
        "original-source", observation, coordinate, "fixture-decoder", "1"
    )


def group(subject=None, parents=(), status="partial", provenance=None):
    return ParentGroup(
        subject or oid(),
        "reported-parent-list",
        status,
        parents,
        provenance or evidence(),
    )


def commit_fixture(parents=(), object_format="sha1"):
    tree = oid("b", object_format)
    body = (
        f"tree {tree.full_oid}\n".encode()
        + b"".join(f"parent {p.full_oid}\n".encode() for p in parents)
        + b"author Test <test@example.invalid> 0 +0000\n"
        + b"committer Test <test@example.invalid> 0 +0000\n\nmessage\n"
    )
    return OID(
        object_format,
        hashlib.new(object_format, f"commit {len(body)}\0".encode() + body).hexdigest(),
    ), body


def test_metadata_only_blob_unknown_size_no_bytes_no_context(core, tmp_path):
    core.admit_repository(str(uuid4()))
    core.admit_object(oid())
    assert core.scalar(oid(), "type")["alternatives"] == []
    core.admit_claim(oid(), "type", "blob", evidence(coordinate="type"))
    core.admit_claim(oid(), "size", None, evidence(coordinate="size"))
    assert core.scalar(oid(), "type")["canonical"] is None
    assert core.scalar(oid(), "size")["alternatives"][0]["value"] == ["unknown"]
    assert core.sql("SELECT * FROM representations") == []
    assert not (tmp_path / "context.sqlite3").exists()
    assert {p.name for p in tmp_path.iterdir()} <= {
        "core.sqlite3",
        "core.sqlite3-wal",
        "core.sqlite3-shm",
    }


def test_nominal_full_typed_identity_is_unique_without_type_or_membership(core):
    core.admit_object(oid())
    core.admit_object(oid())
    core.admit_object(oid("a", "sha256"))
    assert len(core.sql("SELECT * FROM objects")) == 2
    assert core.sql("SELECT * FROM repositories") == []
    assert core.sql("SELECT * FROM claims") == []


@pytest.mark.parametrize(
    "fmt,value", [("sha1", "a" * 12), ("sha1", "A" * 40), ("sha512", "a" * 64)]
)
def test_reject_abbreviated_uppercase_unsupported_oid(fmt, value):
    with pytest.raises(ValueError):
        OID(fmt, value)


def test_parent_references_are_nominal_not_fabricated_verified_objects(core):
    core.admit_group(group(parents=(Parent(2, oid("c")),)))
    assert len(core.sql("SELECT * FROM objects")) == 2
    assert core.sql("SELECT * FROM claims") == []
    assert core.parents(oid())["canonical"] is None
    assert core.parents(oid())["alternatives"][0]["parents"] == [[2, "sha1", "c" * 40]]


def test_exact_replay_and_genuine_independent_observation(core):
    for _ in range(3):
        core.admit_claim(oid(), "size", 1, evidence())
        core.admit_group(group(parents=(Parent(0, oid("b")),)))
    assert len(core.sql("SELECT * FROM claims")) == 1
    assert len(core.sql("SELECT * FROM parent_groups")) == 1
    assert len(core.sql("SELECT * FROM parent_members")) == 1
    core.admit_claim(oid(), "size", 1, evidence("source-snapshot-2"))
    core.admit_group(
        group(parents=(Parent(0, oid("b")),), provenance=evidence("source-snapshot-2"))
    )
    assert len(core.sql("SELECT * FROM claims")) == 2
    assert len(core.sql("SELECT * FROM parent_groups")) == 2
    assert not core.scalar(oid(), "size")["reported_conflict"]


def test_two_genuinely_attributed_scalar_and_relation_alternatives(core):
    core.admit_claim(oid(), "size", 1, evidence("source-snapshot-1"))
    core.admit_claim(oid(), "size", 2, evidence("source-snapshot-2"))
    core.admit_group(
        group(parents=(Parent(0, oid("b")),), provenance=evidence("source-snapshot-1"))
    )
    core.admit_group(
        group(parents=(Parent(0, oid("c")),), provenance=evidence("source-snapshot-2"))
    )
    assert core.scalar(oid(), "size")["reported_conflict"]
    assert core.scalar(oid(), "size")["canonical"] is None
    assert core.parents(oid())["reported_conflict"]
    assert core.parents(oid())["canonical"] is None


def test_inconsistent_scalar_evidence_coordinate_rejected_without_inventing_identity(
    core,
):
    core.admit_claim(oid(), "size", 1, evidence())
    with pytest.raises(ValueError, match="inconsistent immutable evidence"):
        core.admit_claim(oid(), "size", 2, evidence())
    assert len(core.sql("SELECT * FROM claims")) == 1


def test_partial_then_separate_complete_group_never_extends_or_unions_prior(core):
    partial = group(parents=(Parent(1, oid("c")),))
    complete = group(
        parents=(Parent(0, oid("b")), Parent(1, oid("c"))),
        status="complete",
        provenance=evidence("source-snapshot-2"),
    )
    core.admit_group(partial)
    core.admit_group(complete)
    assert partial.key != complete.key
    alternatives = core.parents(oid())["alternatives"]
    assert sorted(len(g["parents"]) for g in alternatives) == [1, 2]
    assert core.parents(oid())["canonical"] is None
    assert not core.parents(oid())["reported_conflict"]


def test_unknown_known_empty_and_absent_are_distinct(core):
    assert core.parents(oid())["alternatives"] == []
    core.admit_group(group(status="unknown"))
    core.admit_group(
        group(status="known_empty", provenance=evidence("source-snapshot-2"))
    )
    assert {g["status"] for g in core.parents(oid())["alternatives"]} == {
        "unknown",
        "known_empty",
    }
    assert core.parents(oid())["canonical"] is None


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE objects SET full_oid=full_oid",
        "DELETE FROM objects",
        "REPLACE INTO objects VALUES ('sha1', ?)",
        "INSERT OR REPLACE INTO objects VALUES ('sha1', ?)",
        "PRAGMA foreign_keys=OFF",
        "DROP TRIGGER immutable_objects_DELETE",
        "INSERT INTO checked_claims SELECT * FROM checked_claims",
    ],
)
def test_supported_sql_cannot_mutate_core_or_borrow_prior_admission(core, statement):
    core.admit_object(oid())
    with pytest.raises(sqlite3.DatabaseError):
        core.sql(statement, (oid().full_oid,) if "?" in statement else ())
    assert len(core.sql("SELECT * FROM objects")) == 1


def test_sqlite_triggers_reject_update_delete_replace_on_separate_writer(
    core, tmp_path
):
    core.admit_object(oid())
    with sqlite3.connect(tmp_path / "core.sqlite3") as db:
        db.execute("PRAGMA recursive_triggers=ON")
        for statement, args in [
            ("UPDATE objects SET full_oid=full_oid", ()),
            ("DELETE FROM objects", ()),
            ("REPLACE INTO objects VALUES (?,?)", oid().key),
        ]:
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                db.execute(statement, args)


def test_frozen_group_cannot_be_mutated_or_extended(core, tmp_path):
    admitted = group(parents=(Parent(0, oid("b")),))
    core.admit_group(admitted)
    with pytest.raises(sqlite3.DatabaseError):
        core.sql("UPDATE parent_groups SET membership='[]'")
    with sqlite3.connect(tmp_path / "core.sqlite3") as db:
        db.execute("PRAGMA foreign_keys=ON")
        placeholders = ",".join("?" for _ in range(len(admitted.key) + 3))
        with pytest.raises(sqlite3.IntegrityError, match="immutable group"):
            db.execute(
                f"INSERT INTO parent_members VALUES ({placeholders})",
                (*admitted.key, 1, *oid("b").key),
            )
    assert len(core.sql("SELECT * FROM parent_members")) == 1


def test_full_composite_fk_prevents_cross_group_member_reference(core, tmp_path):
    admitted = group(parents=(Parent(0, oid("b")),))
    core.admit_group(admitted)
    false_key = list(admitted.key)
    false_key[3] = "another-evidence-scope"
    with sqlite3.connect(tmp_path / "core.sqlite3") as db:
        db.execute("PRAGMA foreign_keys=ON")
        placeholders = ",".join("?" for _ in range(len(admitted.key) + 3))
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.execute(
                f"INSERT INTO parent_members VALUES ({placeholders})",
                (*false_key, 0, *oid("b").key),
            )


def test_multirow_group_failure_is_invisible_and_rolls_back_all_facts(core, tmp_path):
    admitted = group(parents=(Parent(0, oid("b")), Parent(1, oid("c"))))
    observed = []

    def fail_after_first(index):
        with sqlite3.connect(tmp_path / "core.sqlite3") as observer:
            observed.append(
                observer.execute("SELECT count(*) FROM parent_groups").fetchone()[0]
            )
        if index == 0:
            raise RuntimeError("deterministic failure after first parent row")

    with pytest.raises(RuntimeError, match="after first parent"):
        core.admit_group(admitted, after_member=fail_after_first)
    assert observed == [0]
    assert core.sql("SELECT * FROM objects") == []
    assert core.sql("SELECT * FROM parent_groups") == []
    assert core.sql("SELECT * FROM parent_members") == []
    core.admit_group(admitted)
    assert len(core.sql("SELECT * FROM parent_members")) == 2


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_receiver_verified_commit_adds_precise_canonical_evidence_preserving_reports(
    core, object_format
):
    parent = oid("c", object_format)
    subject, body = commit_fixture((parent,), object_format)
    core.admit_claim(subject, "type", "blob", evidence(coordinate="type"))
    core.admit_claim(subject, "size", 0, evidence(coordinate="size"))
    core.admit_group(group(subject, (Parent(0, oid("d", object_format)),)))
    for _ in range(2):
        core.admit_verified_commit(subject, body, declared_size=len(body))
    assert core.scalar(subject, "type")["canonical"] == ["known", "commit"]
    assert core.scalar(subject, "type")["reported_conflict"]
    assert sorted(
        c["checked"] for c in core.scalar(subject, "type")["alternatives"]
    ) == [False, True]
    assert core.parents(subject)["canonical"] == [[0, *parent.key]]
    assert core.parents(subject)["reported_conflict"]
    assert len(core.sql("SELECT * FROM representations")) == 1
    assert len(core.sql("SELECT * FROM checked_claims")) == 2
    assert len(core.sql("SELECT * FROM checked_groups")) == 1
    assert (
        core.sql("SELECT * FROM representations WHERE full_oid=?", (parent.full_oid,))
        == []
    )
    assert len(core.sql("SELECT * FROM commit_trees")) == 1


def test_sender_claiming_receiver_identity_is_still_unverified(core):
    spoofed = Provenance(
        "receiver-intrinsic",
        "sender-says-checked",
        "native-type",
        "spike-native-commit",
        "1",
    )
    core.admit_claim(oid(), "type", "commit", spoofed)
    assert core.scalar(oid(), "type")["canonical"] is None
    assert core.scalar(oid(), "type")["alternatives"][0]["checked"] is False


@pytest.mark.parametrize("bad_size", [-1, True, 2**63, "1"])
def test_invalid_scalar_input_does_not_create_identity_or_verification(core, bad_size):
    with pytest.raises(ValueError):
        core.admit_claim(oid(), "size", bad_size, evidence())
    assert core.sql("SELECT * FROM objects") == []
    assert core.sql("SELECT * FROM checked_claims") == []


def test_invalid_commit_and_group_input_cannot_manufacture_complete_verified_metadata(
    core,
):
    subject, body = commit_fixture()
    for bad_body, declared_size in [(body + b"x", len(body) + 1), (body, 0)]:
        with pytest.raises(ValueError):
            core.admit_verified_commit(subject, bad_body, declared_size=declared_size)
    malformed = b"tree " + b"b" * 40 + b"\n\n"
    malformed_oid = OID(
        "sha1",
        hashlib.sha1(f"commit {len(malformed)}\0".encode() + malformed).hexdigest(),
    )
    with pytest.raises(ValueError, match="headers"):
        core.admit_verified_commit(
            malformed_oid, malformed, declared_size=len(malformed)
        )
    with pytest.raises(ValueError):
        group(parents=(Parent(1, oid("b")),), status="complete")
    assert core.sql("SELECT * FROM objects") == []
    assert core.sql("SELECT * FROM representations") == []
    assert core.sql("SELECT * FROM parent_groups") == []


def test_persistent_core_reopen_without_context(tmp_path):
    path = tmp_path / "core.sqlite3"
    first = Core(path)
    first.admit_claim(oid(), "size", 0, evidence())
    first.close()
    second = Core(path)
    try:
        assert second.scalar(oid(), "size")["alternatives"][0]["value"] == ["known", 0]
        assert second.scalar(oid(), "size")["canonical"] is None
    finally:
        second.close()


def test_unverified_spoofed_local_coordinate_cannot_poison_later_intrinsic_admission(
    core,
):
    subject, body = commit_fixture((oid("c"),))
    local_coordinate = (
        "receiver-intrinsic",
        f"git:{subject.object_format}:{subject.full_oid}",
    )
    spoofed = Provenance(*local_coordinate, "native-type", "spike-native-commit", "1")
    core.admit_claim(subject, "type", "blob", spoofed)
    fake_group = ParentGroup(
        subject,
        "native-parent-header-list",
        "complete",
        (Parent(0, oid("d")),),
        Provenance(
            *local_coordinate, "commit-parent-headers", "spike-native-commit", "1"
        ),
    )
    core.admit_group(fake_group)
    core.admit_verified_commit(subject, body, declared_size=len(body))
    assert core.scalar(subject, "type")["canonical"] == ["known", "commit"]
    assert core.scalar(subject, "type")["reported_conflict"]
    assert core.parents(subject)["canonical"] == [[0, "sha1", "c" * 40]]
    assert len(core.sql("SELECT * FROM claims WHERE field='type'")) == 2


def test_report_api_cannot_self_assert_receiver_derivation_qualification(core):
    forged = Provenance(
        "receiver", "observation", "field", "decoder", "1", "receiver_intrinsic"
    )
    with pytest.raises(ValueError, match="cannot assert receiver"):
        core.admit_claim(oid(), "type", "commit", forged)
    with pytest.raises(ValueError, match="cannot assert receiver"):
        core.admit_group(group(provenance=forged))
    assert core.sql("SELECT * FROM objects") == []


def test_inconsistent_group_evidence_coordinate_rejected(core):
    original = group(parents=(Parent(0, oid("b")),))
    core.admit_group(original)
    with pytest.raises(ValueError, match="inconsistent immutable group"):
        core.admit_group(group(parents=(Parent(0, oid("c")),)))
    assert len(core.sql("SELECT * FROM parent_groups")) == 1
    assert len(core.sql("SELECT * FROM parent_members")) == 1
    assert (
        core.sql("SELECT * FROM objects WHERE full_oid=?", (oid("c").full_oid,)) == []
    )


def test_native_blob_body_cannot_be_retained_through_commit_verifier(core):
    body = b"ordinary repository file bytes"
    blob = OID("sha1", hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest())
    core.admit_claim(blob, "type", "blob", evidence())
    with pytest.raises(ValueError, match="native commit OID mismatch"):
        core.admit_verified_commit(blob, body, declared_size=len(body))
    assert core.sql("SELECT * FROM representations") == []
    assert core.scalar(blob, "type")["canonical"] is None


@pytest.mark.parametrize("closed_count", [0, 1])
@pytest.mark.parametrize("reverse", [False, True])
def test_closed_parent_group_conflicts_with_partial_extra_slot(
    core, closed_count, reverse
):
    closed_parents = (Parent(0, oid("b")),) if closed_count else ()
    closed = group(
        parents=closed_parents,
        status="complete" if closed_count else "known_empty",
        provenance=evidence("closed-observation"),
    )
    extra = group(
        parents=(Parent(closed_count, oid("c")),),
        provenance=evidence("partial-observation"),
    )
    for assertion in (extra, closed) if reverse else (closed, extra):
        core.admit_group(assertion)
    result = core.parents(oid())
    assert result["reported_conflict"]
    assert result["canonical"] is None
    assert len(result["alternatives"]) == 2


@pytest.mark.parametrize(
    "closed_count,partial_status,partial_count",
    [(1, "unknown", 0), (1, "partial", 0), (1, "partial", 1), (0, "unknown", 0)],
)
def test_closed_parent_group_does_not_conflict_with_compatible_partial_or_unknown(
    core, closed_count, partial_status, partial_count
):
    core.admit_group(
        group(
            parents=(Parent(0, oid("b")),) if closed_count else (),
            status="complete" if closed_count else "known_empty",
            provenance=evidence("closed-observation"),
        )
    )
    core.admit_group(
        group(
            parents=(Parent(0, oid("b")),) if partial_count else (),
            status=partial_status,
            provenance=evidence("separate-observation"),
        )
    )
    result = core.parents(oid())
    assert not result["reported_conflict"]
    assert result["canonical"] is None
    assert len(result["alternatives"]) == 2
