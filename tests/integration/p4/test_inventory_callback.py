"""Supported coordinator SQL cannot forge receiver inventory verification."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_coordination import PairCoordinator
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.domain.notes import NotesInventory
from repo_catalog.domain.p1_coordination import AdmissionFailure
from repo_catalog.domain.p1_core import (
    Capture,
    CoreFailure,
    NotesGroup,
    Provenance,
    account_verification,
    encode,
)
from tests.integration.p1.test_core import Budget, native, oid, provenance


@pytest.fixture(params=["sha1", "sha256"])
def catalog(tmp_path, request):
    repository, instance = str(uuid4()), str(uuid4())
    for store in ("core", "context"):
        initialize(tmp_path / (store + ".sqlite3"), store, repository, instance)
    core = GitCore(tmp_path / "core.sqlite3")
    core.admit_repository(repository)
    root = native("tree", b"", request.param)
    capture = Capture(
        str(uuid4()),
        str(uuid4()),
        repository,
        "source-\u65e5\u672c",
        "refs/notes/\u65e5\u672c\udcff",
        root.oid,
    )
    core.admit_capture(capture)
    yield tmp_path, core, capture, root
    core.close()


def group(inventory):
    evidence = [
        [
            *obj.oid.key,
            obj.native_type,
            obj.body.hex(),
            obj.declared_size,
            obj.digest_sha256,
        ]
        for obj in inventory.structures
    ]
    diagnostic = (
        None
        if inventory.failure is None
        else [inventory.failure.code, str(inventory.failure)]
    )
    return NotesGroup(
        inventory.capture,
        "all-notes-mappings",
        inventory.status,
        inventory.members,
        Provenance(
            "receiver-intrinsic",
            encode(inventory.capture.key),
            encode(["inventory", "p4-notes/1", evidence, diagnostic]),
            "git-native-notes-inventory",
            "1",
            "receiver_intrinsic",
        ),
    )


def insert(path, value):
    return PairCoordinator(path).admit(
        lambda tx: tx.execute(
            "INSERT INTO notes_groups VALUES(?,?,?,?,?,?,?)", value.key
        ),
        lambda tx: None,
    )


@pytest.mark.parametrize("status", ["known_empty", "complete", "partial"])
def test_raw_callback_receiver_words_do_not_replace_structural_proof(catalog, status):
    path, core, capture, _root = catalog
    members = ()
    if status != "known_empty":
        target, note = (
            oid("a", capture.root.object_format),
            oid("b", capture.root.object_format),
        )
        core.admit_object(target)
        core.admit_object(note)
        members = ((target.full_oid, note.full_oid, target.full_oid),)
    forged = group(NotesInventory(capture, status, members, ()))
    with pytest.raises(AdmissionFailure) as error:
        insert(path, forged)
    assert not error.value.outcome.core_committed
    assert core.sql("SELECT count(*) FROM notes_groups")[0][0] == 0
    assert core.notes_inventories(capture) == ()
    assert not (path / "p1-recovery-stop.json").exists()
    core.admit_object(oid("d", capture.root.object_format))


def test_raw_callback_actual_native_terminal_proof_and_report_alternatives(catalog):
    path, core, capture, root = catalog
    checked = group(NotesInventory(capture, "known_empty", (), (root,)))
    work = Budget()
    with account_verification(work):
        result = insert(path, checked)
    assert result.core_committed
    assert work.counts["verification_bytes"] == 0  # Actual empty body hash passes.
    assert work.counts["proof_steps"] > 0
    assert core.notes_inventories(capture)[0].status == "known_empty"
    report = NotesGroup(capture, "all-notes-mappings", "unknown", (), provenance())
    assert insert(path, report).core_committed
    assert core.sql("SELECT count(*) FROM notes_groups")[0][0] == 2
    assert len(core.notes_inventories(capture)) == 1
    assert not (path / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize(
    "mutation", ["root", "scope", "qualification", "digest", "type", "oid"]
)
def test_raw_callback_checks_actual_fk_capture_scope_and_structural_bytes(
    catalog, mutation
):
    import json

    path, core, capture, root = catalog
    checked = group(NotesInventory(capture, "known_empty", (), (root,)))
    if mutation == "scope":
        checked = replace(checked, scope="different-inventory")
    elif mutation == "root":
        other = replace(
            capture,
            capture_uuidv4=str(uuid4()),
            root=oid("e", capture.root.object_format),
        )
        core.admit_capture(other)
        checked = replace(checked, capture=other)
    elif mutation == "qualification":
        checked = replace(
            checked, provenance=replace(checked.provenance, decoder="sender-verified")
        )
    else:
        coordinates = json.loads(checked.provenance.coordinate)
        index, value = {
            "digest": (5, "0" * 64),
            "type": (2, "blob"),
            "oid": (1, oid("a", capture.root.object_format).full_oid),
        }[mutation]
        coordinates[2][0][index] = value
        checked = replace(
            checked,
            provenance=replace(checked.provenance, coordinate=encode(coordinates)),
        )
    with pytest.raises(AdmissionFailure):
        insert(path, checked)
    assert core.sql("SELECT count(*) FROM notes_groups")[0][0] == 0
    assert not (path / "p1-recovery-stop.json").exists()


def test_receiver_sql_rechecks_respect_actual_work_budget(catalog):
    path, core, capture, root = catalog
    checked = group(NotesInventory(capture, "known_empty", (), (root,)))

    class Exhausted(Budget):
        def require(self, unit, amount=1):
            if unit == "proof_steps":
                raise CoreFailure("BUDGET", unit, "no structural work allowance")
            return super().require(unit, amount)

    with pytest.raises(CoreFailure) as error:
        with account_verification(Exhausted()):
            insert(path, checked)
    assert error.value.code == "BUDGET"
    assert core.sql("SELECT count(*) FROM notes_groups")[0][0] == 0
    assert not (path / "p1-recovery-stop.json").exists()
