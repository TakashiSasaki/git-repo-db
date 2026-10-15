"""Purpose-bound native notes proofs: no ordinary-file archival API."""

from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_core import (
    Capture,
    CoreFailure,
    NotesClaim,
    NotesGroup,
    NotesProof,
    ScalarClaim,
    encode,
)
from tests.integration.p1.test_core import Budget, native, oid, provenance
from tests.integration.p1.test_core import core as core


def tree(entries, fmt="sha1"):
    return native(
        "tree",
        b"".join(
            mode.encode()
            + b" "
            + name.encode()
            + b"\0"
            + bytes.fromhex(target.full_oid)
            for mode, name, target in sorted(entries, key=lambda v: v[1])
        ),
        fmt,
    )


def mapping(repository, body=b"note", fmt="sha1", ref="refs/notes/review"):
    note, target = native("blob", body, fmt), oid("a", fmt)
    root = tree([("100644", target.full_oid, note.oid)], fmt)
    capture = Capture(
        str(uuid4()), str(uuid4()), repository, "original issuer report", ref, root.oid
    )
    proof = NotesProof(capture, target, note.oid, target.full_oid, (root,))
    return proof, note


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("body", [b"", b"simple\n", b"\x00\xffbinary\r\n"])
def test_direct_tree_binary_empty_unknown_targets_and_native_git_hash(core, fmt, body):
    c, _, repository = core
    proof, note = mapping(repository, body, fmt)
    work = Budget()
    c.admit_note(proof, note, str(uuid4()), work)
    assert c.read_note(proof.capture, proof.target, proof.note) == body
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_metadata") == []
    assert len(c.sql("SELECT * FROM git_objects")) == 3
    # Independent Git's implementation agrees on the native byte identity.
    actual = subprocess.run(
        ["git", "-c", "extensions.objectFormat=" + fmt, "hash-object", "--stdin"],
        input=body,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if fmt == "sha1":
        assert (
            actual.returncode == 0
            and actual.stdout.strip().decode() == note.oid.full_oid
        )
    assert work.counts["proof_steps"] == 3
    assert work.counts["verification_bytes"] == 6 * len(
        proof.structures[0].body
    ) + 4 * len(note.body)
    assert work.counts["input_bytes"] == len(note.body) + len(proof.structures[0].body)


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
def test_notes_commit_root_and_fanout_relevant_only(core, fmt):
    c, _, repository = core
    proof, note = mapping(repository, b"fanout", fmt)
    target = proof.target.full_oid
    inner = tree([("100644", target[4:], note.oid)], fmt)
    middle = tree([("40000", target[2:4], inner.oid)], fmt)
    root = tree(
        [("40000", target[:2], middle.oid), ("40000", "zz-unrelated", oid("b", fmt))],
        fmt,
    )
    commit = native(
        "commit",
        f"tree {root.oid.full_oid}\nauthor A <a@invalid> 0 +0000\ncommitter C <c@invalid> 0 +0000\n\nnotes\n".encode(),
        fmt,
    )
    proof = replace(
        proof,
        capture=replace(proof.capture, root=commit.oid),
        structures=(commit, root, middle, inner),
        path="/".join([target[:2], target[2:4], target[4:]]),
    )
    c.admit_note(proof, note, str(uuid4()), Budget())
    assert c.read_note(proof.capture, proof.target, proof.note) == b"fanout"
    assert len(c.sql("SELECT capture_origin_uuidv4 FROM note_roles")) == 1


def test_same_capture_reports_alternatives_groups_and_replay(core):
    c, _, repository = core
    proof, note = mapping(repository)
    first = NotesClaim(proof.capture, proof.target, proof.note, provenance("first"))
    c.admit_notes_claim(first)
    c.admit_notes_claim(first)
    competing = native("blob", b"alternative")
    c.admit_notes_claim(
        replace(first, note=competing.oid, provenance=provenance("other"))
    )
    group = NotesGroup(
        proof.capture,
        "explicit mapping subset",
        "partial",
        ((proof.target.full_oid, proof.note.full_oid, None),),
        provenance("group"),
    )
    c.admit_notes_group(group)
    c.admit_notes_group(group)
    with pytest.raises(CoreFailure):
        c.admit_notes_group(replace(group, status="complete"))
    assert len(c.sql("SELECT * FROM captures")) == 1
    assert len(c.sql("SELECT * FROM notes_claims")) == 2
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_notes") == []
    with pytest.raises(CoreFailure, match="receiver-proven"):
        c.read_note(proof.capture, proof.target, proof.note)
    c.admit_note(proof, note, str(uuid4()), Budget())
    assert len(c.sql("SELECT * FROM notes_claims")) == 2
    assert c.read_note(proof.capture, proof.target, proof.note) == b"note"


def test_same_blob_file_role_and_multiple_namespaces(core):
    c, _, repository = core
    proof, note = mapping(repository)
    c.admit_claim(ScalarClaim(proof.note, "type", "blob", provenance()))
    copy = str(uuid4())
    c.admit_note(proof, note, copy, Budget())
    alternate = replace(
        proof,
        capture=replace(
            proof.capture, capture_uuidv4=str(uuid4()), ref="refs/notes/team/nested"
        ),
    )
    c.admit_note(alternate, note, str(uuid4()), Budget())
    file_tree = tree([("100644", "ordinary.txt", proof.note)])
    unrelated = replace(
        proof,
        capture=replace(proof.capture, capture_uuidv4=str(uuid4()), root=file_tree.oid),
        path="ordinary.txt",
        structures=(file_tree,),
    )
    with pytest.raises(CoreFailure, match="relevant notes mapping"):
        c.admit_note(unrelated, note, str(uuid4()), Budget())
    with pytest.raises(CoreFailure, match="receiver-proven"):
        c.read_note(unrelated.capture, unrelated.target, unrelated.note)
    assert (
        len(
            c.sql(
                "SELECT * FROM git_objects WHERE object_format=? AND full_oid=?",
                proof.note.key,
            )
        )
        == 1
    )
    assert len(c.sql("SELECT capture_origin_uuidv4 FROM note_roles")) == 2
    assert not hasattr(c, "read_blob")


@pytest.mark.parametrize(
    "mode,name",
    [
        ("100755", "valid"),
        ("120000", "valid"),
        ("160000", "valid"),
        ("100644", "short"),
        ("100644", "upper"),
    ],
)
def test_false_relevant_mode_or_name_rejects_body(core, mode, name):
    c, _, repository = core
    proof, note = mapping(repository)
    target = {
        "valid": proof.target.full_oid,
        "short": proof.target.full_oid[:-1],
        "upper": proof.target.full_oid.upper(),
    }[name]
    root = tree([(mode, target, proof.note)])
    proof = replace(
        proof,
        capture=replace(proof.capture, root=root.oid),
        structures=(root,),
        path=target,
    )
    with pytest.raises(CoreFailure, match="relevant notes mapping"):
        c.admit_note(proof, note, str(uuid4()), Budget())
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_notes") == []


def test_sender_claim_hash_prefix_and_ref_do_not_authorize_retention(core):
    c, path, repository = core
    proof, note = mapping(repository)
    c.admit_notes_claim(
        NotesClaim(
            proof.capture, proof.target, proof.note, provenance("sender says verified")
        )
    )
    with pytest.raises(CoreFailure, match="ordinary-file"):
        c.admit_metadata(note, str(uuid4()), Budget())
    db = connect(path, "core")
    try:
        # Valid blob OID/type/size/digest reaches the intended role FK failure.
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            db.execute(
                "INSERT INTO retained_notes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    *note.oid.key,
                    str(uuid4()),
                    note.body,
                    note.declared_size,
                    note.digest_sha256,
                    *proof.capture.pair,
                    proof.capture.root.full_oid,
                    proof.target.full_oid,
                    proof.path,
                    proof.bundle,
                ),
            )
        invalid = replace(proof, target=oid("c"))
        c.admit_object(invalid.target)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            db.execute("INSERT INTO note_roles VALUES(?,?,?,?,?,?,?,?)", invalid.key)
    finally:
        db.close()
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_notes") == []


@pytest.mark.parametrize("bad", ["oid", "size", "digest", "kind", "format"])
def test_invalid_body_exact_checks_without_irrelevant_lexical_failure(core, bad):
    c, _, repository = core
    proof, note = mapping(repository)
    if bad == "oid":
        note = replace(note, body=b"different same reported object")
    elif bad == "size":
        note = replace(note, declared_size=note.declared_size + 1)
    elif bad == "digest":
        note = replace(note, digest_sha256="0" * 64)
    elif bad == "kind":
        note = replace(note, native_type="tree")
    else:
        proof = replace(proof, target=oid("a", "sha256"))
    with pytest.raises(CoreFailure):
        c.admit_note(proof, note, str(uuid4()), Budget())
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_notes") == []


def test_capture_binding_immutable_no_new_retry_identity(core):
    c, _, repository = core
    proof, note = mapping(repository)
    first = NotesClaim(proof.capture, proof.target, proof.note, provenance())
    c.admit_notes_claim(first)
    for field, changed in (
        ("source", "other issuer"),
        ("ref", "refs/notes/other"),
        ("root", oid("c")),
    ):
        with pytest.raises(CoreFailure, match="immutable evidence"):
            c.admit_notes_claim(
                replace(first, capture=replace(proof.capture, **{field: changed}))
            )
    budget = Budget()
    copy = str(uuid4())
    c.admit_note(proof, note, copy, budget)
    before = dict(budget.counts)
    c.admit_note(proof, note, copy, budget)
    assert budget.counts["input_bytes"] == 2 * before["input_bytes"]
    assert len(c.sql("SELECT * FROM captures")) == 1
    assert len(c.sql("SELECT physical_copy_uuidv4 FROM retained_notes")) == 1


def test_atomic_note_admission_work_survives_rollback_and_budget_stop(core):
    c, _, repository = core
    proof, note = mapping(repository)
    budget = Budget()
    c.admit_notes_claim(
        NotesClaim(proof.capture, proof.target, proof.note, provenance())
    )

    def crash():
        raise RuntimeError("after notes rows before commit")

    with pytest.raises(RuntimeError):
        c.admit_note(proof, note, str(uuid4()), budget, before_commit=crash)
    assert budget.counts["input_bytes"] > 0
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_notes") == []
    assert c.sql("SELECT capture_origin_uuidv4 FROM note_roles") == []
    assert len(c.sql("SELECT * FROM notes_claims")) == 1

    class SmallBudget(Budget):
        class Limits:
            note_bytes = 1

        limits = Limits()

    with pytest.raises(CoreFailure, match="size limit"):
        c.admit_note(proof, note, str(uuid4()), SmallBudget())
    c.admit_note(proof, note, str(uuid4()), budget)
    assert c.read_note(proof.capture, proof.target, proof.note) == b"note"


def test_recovery_stop_on_retained_corruption_never_sibling_failover(core):
    c, path, repository = core
    proof, note = mapping(repository)
    for _ in range(2):
        c.admit_note(proof, note, str(uuid4()), Budget())
    db = connect(path, "core")
    # Privileged fault injection on disposable catalog, beyond supported boundary.
    db.execute("DROP TRIGGER p1_immutable_retained_notes_update")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute(
        "UPDATE retained_notes SET body=? WHERE physical_copy_uuidv4=(SELECT min(physical_copy_uuidv4) FROM retained_notes)",
        (b"damaged",),
    )
    db.close()
    with pytest.raises(CoreFailure) as error:
        c.read_note(proof.capture, proof.target, proof.note)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    with pytest.raises(CoreFailure) as stopped:
        c.scalar(note.oid, "type")
    assert stopped.value.code == "RECOVERY_STOP"
    from repo_catalog.adapters.sqlite.p1_core import Core

    with pytest.raises(CoreFailure) as reopen:
        Core(path)
    assert reopen.value.code == "RECOVERY_STOP"


def test_semantic_proof_bundle_contains_entire_native_bytes_not_hash_alias(core):
    _, _, repository = core
    proof, _ = mapping(repository)
    proof.validate()
    assert proof.structures[0].body.hex() in proof.bundle
    assert proof.bundle == encode(
        [[s.oid.full_oid, s.native_type, s.body.hex()] for s in proof.structures]
    )


def test_raw_non_utf8_ref_is_losslessly_encoded_without_alias(core):
    c, _, repository = core
    proof, note = mapping(repository)
    raw = b"refs/notes/team-\xff"
    proof = replace(
        proof,
        capture=replace(proof.capture, ref=raw.decode("utf-8", "surrogateescape")),
    )
    c.admit_note(proof, note, str(uuid4()), Budget())
    assert c.sql("SELECT ref FROM captures")[0][0] == encode(["native-ref", raw.hex()])
    assert c.read_note(proof.capture, proof.target, proof.note) == b"note"


def test_metadata_only_notes_projection_preserves_reports_groups_and_local_role(core):
    c, _, repository = core
    proof, note = mapping(repository)
    other = native("blob", b"contradictory report")
    first = NotesClaim(proof.capture, proof.target, proof.note, provenance("original"))
    c.admit_notes_claim(first)
    c.admit_notes_claim(
        replace(first, note=other.oid, provenance=provenance("independent"))
    )
    group = NotesGroup(
        proof.capture,
        "all-notes-mappings",
        "partial",
        ((proof.target.full_oid, proof.note.full_oid, proof.path),),
        provenance("group"),
    )
    c.admit_notes_group(group)
    before = c.notes_projection(proof.capture, proof.target)
    assert before.reported_conflict
    assert before.canonical is None
    assert len(before.alternatives) == 3
    assert {a.kind for a in before.alternatives} == {"claim", "group"}
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_notes") == []
    c.admit_notes_role(proof, Budget())
    after = c.notes_projection(proof.capture, proof.target)
    assert after.canonical == proof.note
    assert after.reported_conflict
    assert after.checked_scope == "relevant-root-to-target-mapping"
    assert len(after.alternatives) == 4
    assert [a for a in after.alternatives if a.kind == "claim"] == [
        a for a in before.alternatives if a.kind == "claim"
    ]
    assert {a.provenance.qualification for a in after.alternatives if a.provenance} == {
        "reported"
    }
    with pytest.raises(CoreFailure, match="role/body"):
        c.read_note(proof.capture, proof.target, proof.note)
    missing = c.notes_projection(proof.capture, oid("f"))
    assert missing.canonical is None and not missing.reported_conflict


@pytest.mark.parametrize(
    "scope,expected", [("all-notes-mappings", True), ("unrelated subset", False)]
)
def test_notes_projection_closed_scope_does_not_borrow_other_scope_absence(
    core, scope, expected
):
    c, _, repository = core
    proof, _ = mapping(repository)
    c.admit_notes_claim(
        NotesClaim(proof.capture, proof.target, proof.note, provenance("positive"))
    )
    c.admit_notes_group(
        NotesGroup(proof.capture, scope, "known_empty", (), provenance("empty"))
    )
    assert c.notes_projection(proof.capture, proof.target).reported_conflict is expected


def test_metadata_only_notes_role_obeys_zero_proof_step_budget(core):
    c, _, repository = core
    proof, _ = mapping(repository)
    c.admit_notes_claim(
        NotesClaim(
            proof.capture, proof.target, proof.note, provenance("independent metadata")
        )
    )

    class NoProofBudget(Budget):
        def require(self, unit, amount=1):
            if unit == "proof_steps" and amount:
                raise CoreFailure("BUDGET", unit, "proof_steps exhausted")
            super().require(unit, amount)

    budget = NoProofBudget()
    with pytest.raises(CoreFailure, match="proof_steps exhausted"):
        c.admit_notes_role(proof, budget)
    assert budget.counts["input_bytes"] > 0
    assert len(c.notes_projection(proof.capture, proof.target).alternatives) == 1
    assert c.sql("SELECT capture_origin_uuidv4 FROM note_roles") == []
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_notes") == []
