"""Production traversal and immutable receiver inventory, with actual Git bytes."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.notes import NotesInventory, mapping_inventory, mapping_proof
from repo_catalog.domain.p1_core import Capture, CoreFailure, NotesGroup
from tests.integration.p1.test_core import Budget, native, oid, provenance
from tests.integration.p2.test_native import commit_body, entry, git, write


@pytest.fixture(params=["sha1", "sha256"])
def case(tmp_path, request):
    path = tmp_path / "git"
    path.mkdir()
    git(path, "init", "--bare", "--object-format=" + request.param)
    repository = str(uuid4())
    db = tmp_path / "catalog" / "core.sqlite3"
    db.parent.mkdir()
    initialize(db, "core", repository, str(uuid4()))
    core = GitCore(db)
    core.admit_repository(repository)
    yield path, request.param, repository, core, db
    core.close()


def capture(case, root):
    return Capture(
        str(uuid4()),
        str(uuid4()),
        case[2],
        "original-source",
        "refs/notes/nested/review",
        root.oid,
    )


def fixture_tree(case, *, fanout=False, commit=False, body=b"\0\xff\r\n"):
    path, fmt = case[:2]
    target = oid("a", fmt)  # Annotated target deliberately unavailable.
    note = write(path, fmt, "blob", body)
    name = target.full_oid[2:] if fanout else target.full_oid
    leaf = write(path, fmt, "tree", entry(b"100644", name.encode(), note.oid))
    root = (
        write(path, fmt, "tree", entry(b"40000", b"aa", leaf.oid)) if fanout else leaf
    )
    if commit:
        root = write(path, fmt, "commit", commit_body(root.oid, (oid("b", fmt),)))
    return capture(case, root), target, note


@pytest.mark.parametrize("fanout", [False, True])
@pytest.mark.parametrize("commit", [False, True])
def test_proof_and_terminal_inventory_real_native_git(case, fanout, commit):
    cap, target, note = fixture_tree(case, fanout=fanout, commit=commit)
    source = GitNativeSource(case[0])
    work = Budget()
    proof = mapping_proof(cap, target, source.metadata, work)
    assert proof.note == note.oid
    assert proof.path == ("aa/" + target.full_oid[2:] if fanout else target.full_oid)
    assert proof.structures[0].native_type == ("commit" if commit else "tree")
    inventory = mapping_inventory(cap, source.metadata, work)
    assert inventory.status == "complete" and inventory.failure is None
    assert inventory.members == ((target.full_oid, note.oid.full_oid, proof.path),)
    core = case[3]
    core.admit_notes_inventory(inventory, work)
    charged = dict(work.counts)
    core.admit_notes_inventory(inventory, work)
    assert work.counts["verification_bytes"] > charged["verification_bytes"]
    assert len(core.notes_inventories(cap)) == 1
    assert core.notes_inventories(cap)[0].members == inventory.members
    assert core.sql("SELECT count(*) FROM notes_groups")[0][0] == 1
    assert core.sql("SELECT count(*) FROM retained_notes")[0][0] == 0
    assert core.sql("SELECT count(*) FROM retained_metadata")[0][0] == 0
    assert core.notes_projection(cap, target).canonical == note.oid
    with pytest.raises(sqlite3.DatabaseError):
        core.sql("SELECT provenance FROM notes_groups")


def test_known_empty_requires_checked_empty_tree_and_capture_scope(case):
    root = write(case[0], case[1], "tree", b"")
    cap = capture(case, root)
    source = GitNativeSource(case[0])
    empty = mapping_inventory(cap, source.metadata, Budget())
    assert empty.status == "known_empty" and empty.structures == (root,)
    core = case[3]
    core.admit_notes_inventory(empty, Budget())
    newer = replace(cap, capture_uuidv4=str(uuid4()))

    def missing(_):
        raise CoreFailure("OBJECT_UNAVAILABLE", newer.pair, "missing")

    unknown = mapping_inventory(newer, missing, Budget())
    assert unknown.status == "unknown" and not unknown.structures
    core.admit_notes_inventory(unknown, Budget())
    assert core.notes_inventories(newer)[0].status == "unknown"
    assert core.notes_inventories(cap)[0].status == "known_empty"
    with pytest.raises(CoreFailure, match="receiver structural"):
        core.admit_notes_inventory(
            replace(unknown, status="known_empty", failure=None), Budget()
        )


def test_narrow_mapping_does_not_require_unrelated_subtree_inventory_does(case):
    path, fmt = case[:2]
    target = oid("a", fmt)
    note = write(path, fmt, "blob", b"note")
    root = write(
        path,
        fmt,
        "tree",
        entry(b"100644", target.full_oid.encode(), note.oid)
        + entry(b"40000", b"bb", oid("c", fmt)),
    )
    cap, source = capture(case, root), GitNativeSource(path)
    assert mapping_proof(cap, target, source.metadata, Budget()).note == note.oid
    partial = mapping_inventory(cap, source.metadata, Budget())
    assert partial.status == "partial" and partial.failure is not None
    assert len(partial.members) == 1
    case[3].admit_notes_inventory(partial, Budget())
    assert case[3].notes_inventories(cap)[0].status == "partial"
    with pytest.raises(CoreFailure):
        case[3].admit_notes_inventory(
            replace(partial, status="complete", failure=None), Budget()
        )


@pytest.mark.parametrize(
    "mode,name",
    [(b"100755", None), (b"120000", None), (b"100644", b"README"), (b"40000", b"a")],
)
def test_unsupported_inventory_grammar_never_terminal(case, mode, name):
    target = oid("a", case[1])
    note = write(case[0], case[1], "blob", b"note")
    root = write(
        case[0],
        case[1],
        "tree",
        entry(mode, name or target.full_oid.encode(), note.oid),
        literal=True,
    )
    cap = capture(case, root)
    inventory = mapping_inventory(cap, GitNativeSource(case[0]).metadata, Budget())
    assert inventory.status == "unknown" and inventory.failure.code in (
        "NOTES_INVENTORY",
        "NOTES_ROLE",
    )
    case[3].admit_notes_inventory(inventory, Budget())
    assert case[3].notes_inventories(cap)[0].status == "unknown"


def test_body_reader_not_used_and_wrong_callback_oid_rejected(case):
    cap, target, _ = fixture_tree(case)
    work = Budget()
    wrong = native("tree", b"", case[1])
    with pytest.raises(CoreFailure) as error:
        mapping_proof(cap, target, lambda _: wrong, work)
    assert error.value.code == "NATIVE_INTEGRITY"
    assert work.counts["proof_steps"] == 1
    inventory = mapping_inventory(cap, lambda _: wrong, Budget())
    assert inventory.status == "unknown" and not inventory.structures
    forged = NotesInventory(cap, "known_empty", (), (wrong,))
    with pytest.raises(CoreFailure):
        case[3].admit_notes_inventory(forged, Budget())


def test_reports_remain_original_and_receiver_group_is_distinct(case):
    cap, target, note = fixture_tree(case)
    core = case[3]
    report = NotesGroup(
        cap,
        "all-notes-mappings",
        "complete",
        ((target.full_oid, oid("b", case[1]).full_oid, None),),
        provenance(),
    )
    core.admit_notes_group(report)
    checked = mapping_inventory(cap, GitNativeSource(case[0]).metadata, Budget())
    core.admit_notes_inventory(checked, Budget())
    projected = core.notes_projection(cap, target)
    assert projected.reported_conflict
    assert len(core.notes_inventories(cap)) == 1
    assert any(
        alternative.provenance == report.provenance
        for alternative in projected.alternatives
    )
    assert note.oid.full_oid in str(projected)


def test_native_corruption_in_receiver_inventory_persistently_stops(case):
    cap, _, _ = fixture_tree(case)
    core, db = case[3:]
    inventory = mapping_inventory(cap, GitNativeSource(case[0]).metadata, Budget())
    core.admit_notes_inventory(inventory, Budget())
    connection = sqlite3.connect(db)
    try:
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall():
            connection.execute('DROP TRIGGER "' + name + '"')
        connection.execute("PRAGMA ignore_check_constraints=ON")
        (encoded,) = connection.execute(
            "SELECT provenance FROM notes_groups"
        ).fetchone()
        value = json.loads(encoded)
        coordinate = json.loads(value[2])
        coordinate[2][0][3] = b"damaged".hex()
        from repo_catalog.domain.p1_core import encode

        value[2] = encode(coordinate)
        connection.execute("UPDATE notes_groups SET provenance=?", (encode(value),))
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(CoreFailure) as error:
        core.notes_inventories(cap)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    with pytest.raises(CoreFailure):
        core.admit_object(oid("d", case[1]))


def test_inventory_atomic_rollback_on_core_insert_failure(case, monkeypatch):
    cap, _, _ = fixture_tree(case)
    inventory = mapping_inventory(cap, GitNativeSource(case[0]).metadata, Budget())
    core = case[3]
    original = core._insert

    def fail(table, values):
        if table == "notes_groups":
            raise sqlite3.IntegrityError("injected constraint")
        return original(table, values)

    monkeypatch.setattr(core, "_insert", fail)
    work = Budget()
    with pytest.raises(sqlite3.IntegrityError):
        core.admit_notes_inventory(inventory, work)
    assert core.sql("SELECT count(*) FROM captures")[0][0] == 0
    assert core.sql("SELECT count(*) FROM notes_groups")[0][0] == 0
    assert work.counts["verification_bytes"] > 0


class FiniteBudget(Budget):
    def __init__(self, unit, limit):
        super().__init__()
        self.unit, self.limit = unit, limit

    def require(self, unit, amount=1):
        super().require(unit, amount)
        if unit == self.unit and self.counts.get(unit, 0) + amount > self.limit:
            raise CoreFailure("BUDGET", unit, "finite work allowance exhausted")


@pytest.mark.parametrize(
    "unit,limit", [("proof_steps", 0), ("metadata_units", 0), ("verification_bytes", 0)]
)
def test_actual_failed_attempt_is_prepaid_and_never_terminal(case, unit, limit):
    cap, target, _ = fixture_tree(case, fanout=True, commit=True)
    source = GitNativeSource(case[0])
    work = FiniteBudget(unit, limit)
    inventory = mapping_inventory(cap, source.metadata, work)
    assert inventory.status == "unknown" and inventory.failure.code == "BUDGET"
    before = dict(work.counts)
    with pytest.raises(CoreFailure) as error:
        mapping_proof(cap, target, source.metadata, work)
    assert error.value.code == "BUDGET"
    if unit != "proof_steps":
        assert work.counts["proof_steps"] > before["proof_steps"]
    assert not inventory.members


def test_budget_stop_after_first_mapping_preserves_partial_prefix(case):
    path, fmt = case[:2]
    note = write(path, fmt, "blob", b"note")
    targets = (oid("a", fmt), oid("b", fmt))
    root = write(
        path,
        fmt,
        "tree",
        b"".join(
            entry(b"100644", target.full_oid.encode(), note.oid) for target in targets
        ),
    )
    cap, source = capture(case, root), GitNativeSource(path)
    full = mapping_inventory(cap, source.metadata, Budget())
    # The structural read, proof-bundle sizing and role check all consume work.
    # The second member is refused after the first complete mapping.
    partial = mapping_inventory(cap, source.metadata, FiniteBudget("proof_steps", 3))
    assert full.status == "complete"
    assert partial.status == "partial" and len(partial.members) == 1
    assert partial.failure.code == "BUDGET"
    core = case[3]
    core.admit_notes_inventory(full, Budget())
    core.admit_notes_inventory(partial, Budget())
    assert {value.status for value in core.notes_inventories(cap)} == {
        "complete",
        "partial",
    }
    assert (
        next(
            value for value in core.notes_inventories(cap) if value.status == "partial"
        ).members
        == partial.members
    )


def test_real_git_notes_generated_commit_is_supported(case, monkeypatch):
    path, fmt = case[:2]
    monkeypatch.setenv("GIT_AUTHOR_NAME", "P4")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "p4@invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "P4")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "p4@invalid")
    target = write(path, fmt, "blob", b"target is file data and never acquired")
    git(
        path,
        "notes",
        "--ref=refs/notes/nested/actual",
        "add",
        "-m",
        "actual Git note",
        target.oid.full_oid,
    )
    root_oid = git(path, "rev-parse", "refs/notes/nested/actual").strip().decode()
    source = GitNativeSource(path)
    cap = capture(case, source.metadata(type(target.oid)(fmt, root_oid)))
    inventory = mapping_inventory(cap, source.metadata, Budget())
    assert inventory.status == "complete" and len(inventory.members) == 1
    assert inventory.members[0][0] == target.oid.full_oid
    case[3].admit_notes_inventory(inventory, Budget())
    assert (
        case[3].notes_projection(cap, target.oid).canonical.full_oid
        == inventory.members[0][1]
    )


@pytest.mark.parametrize("change", ["size", "digest", "type", "syntax"])
def test_structural_integrity_and_syntax_refusals_do_not_retain_incoming_bytes(
    case, change
):
    cap, target, _ = fixture_tree(case)
    original = GitNativeSource(case[0]).metadata(cap.root)
    damaged = {
        "size": replace(original, declared_size=original.declared_size + 1),
        "digest": replace(original, digest_sha256="0" * 64),
        "type": replace(original, native_type="blob"),
        "syntax": native("tree", b"malformed", case[1]),
    }[change]
    if change == "syntax":
        cap = replace(cap, root=damaged.oid)
    with pytest.raises(CoreFailure):
        mapping_proof(cap, target, lambda _: damaged, Budget())
    inventory = mapping_inventory(cap, lambda _: damaged, Budget())
    assert inventory.status == "unknown" and not inventory.structures
    case[3].admit_notes_inventory(inventory, Budget())
    assert case[3].notes_inventories(cap)[0].structures == ()
    forged = replace(inventory, structures=(damaged,))
    with pytest.raises(CoreFailure):
        case[3].admit_notes_inventory(forged, Budget())


def test_ambiguous_flat_and_fanout_mapping_rejected(case):
    path, fmt = case[:2]
    target = oid("a", fmt)
    note = write(path, fmt, "blob", b"note")
    subtree = write(
        path, fmt, "tree", entry(b"100644", target.full_oid[2:].encode(), note.oid)
    )
    root = write(
        path,
        fmt,
        "tree",
        entry(b"40000", b"aa", subtree.oid)
        + entry(b"100644", target.full_oid.encode(), note.oid),
    )
    cap, source = capture(case, root), GitNativeSource(path)
    with pytest.raises(CoreFailure) as error:
        mapping_proof(cap, target, source.metadata, Budget())
    assert error.value.code == "NOTES_ROLE"
    inventory = mapping_inventory(cap, source.metadata, Budget())
    assert inventory.status == "unknown" and not inventory.members
    with pytest.raises(CoreFailure):
        case[3].admit_notes_inventory(
            replace(inventory, status="known_empty", failure=None), Budget()
        )


@pytest.mark.parametrize("reader", ["inventory", "projection"])
def test_persisted_inventory_invalid_utf8_publishes_stop(case, reader):
    root = write(case[0], case[1], "tree", b"")
    cap = capture(case, root)
    core, db_path = case[3], case[4]
    core.admit_notes_inventory(
        mapping_inventory(cap, GitNativeSource(case[0]).metadata, Budget()), Budget()
    )
    # Privileged simulated storage damage to already admitted authoritative text.
    db = sqlite3.connect(db_path)
    db.execute("DROP TRIGGER p1_immutable_notes_groups_update")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute("UPDATE notes_groups SET status=CAST(x'ff' AS TEXT)")
    db.commit()
    db.close()
    with pytest.raises(CoreFailure) as stopped:
        if reader == "inventory":
            core.notes_inventories(cap)
        else:
            core.notes_projection(cap, oid("a", case[1]))
    assert stopped.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (db_path.parent / "p1-recovery-stop.json").is_file()
    with pytest.raises(CoreFailure) as stopped:
        core.admit_object(oid("b", case[1]))
    assert stopped.value.code == "RECOVERY_STOP"


@pytest.mark.parametrize("reader", ["inventory", "projection"])
def test_persisted_inventory_deep_json_publishes_stop(case, reader):
    root = write(case[0], case[1], "tree", b"")
    cap = capture(case, root)
    core, db_path = case[3], case[4]
    core.admit_notes_inventory(
        mapping_inventory(cap, GitNativeSource(case[0]).metadata, Budget()), Budget()
    )
    db = sqlite3.connect(db_path)
    db.execute("DROP TRIGGER p1_immutable_notes_groups_update")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute(
        "UPDATE notes_groups SET provenance=?", ("[" * 10000 + "0" + "]" * 10000,)
    )
    db.commit()
    db.close()
    with pytest.raises(CoreFailure) as stopped:
        if reader == "inventory":
            core.notes_inventories(cap)
        else:
            core.notes_projection(cap, oid("a", case[1]))
    assert stopped.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (db_path.parent / "p1-recovery-stop.json").is_file()
    with pytest.raises(CoreFailure) as stopped:
        core.admit_object(oid("b", case[1]))
    assert stopped.value.code == "RECOVERY_STOP"
