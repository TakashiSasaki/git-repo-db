"""Actual SQLite COMMIT rejection and process death in the Ref body writer cut."""

import json
import signal
import sqlite3
import subprocess
import sys
from contextlib import closing
from uuid import uuid4

import pytest

from repo_catalog.adapters.sqlite.git_core import GitCore
from tests.integration.p4 import conftest as fixtures
from tests.integration.p4.test_ref_observation_i2 import discover

acquisition = fixtures.acquisition


def test_ref_body_real_commit_denial_rolls_back_and_retry_keeps_work(
    acquisition, monkeypatch
):
    app, _, _, repository, origin, path, _ = acquisition
    _, target, note = fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    denied = False
    inserted = False
    copy = str(uuid4())
    original_insert, authorize = app.core._insert, app.core._authorize

    def after_insert(table, values):
        nonlocal inserted
        original_insert(table, values)
        if table == "ref_retained_notes":
            inserted = True

    def reject_commit(action, first, *args):
        nonlocal denied
        if inserted and action == sqlite3.SQLITE_TRANSACTION and first == "COMMIT":
            denied = True
            return sqlite3.SQLITE_DENY
        return authorize(action, first, *args)

    before = app.work.ledger.usage(app.work.request)
    monkeypatch.setattr(app.core, "_insert", after_insert)
    app.core._db.set_authorizer(reject_commit)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            app.acquire_ref_note(claim, target, physical_copy_uuidv4=copy)
    finally:
        app.core._db.set_authorizer(authorize)
        monkeypatch.setattr(app.core, "_insert", original_insert)
    assert inserted and denied
    assert not app.core._db.in_transaction
    assert not app.core.sql("SELECT 1 FROM ref_retained_notes")
    after_failure = app.work.ledger.usage(app.work.request)
    assert after_failure["input_bytes"] > before["input_bytes"]
    projection = app.core.notes_mapping_projection(
        claim, target, "git-notes", "1", "native-notes-tree", app.work
    )
    assert projection.canonical_note_oid == note  # independently admitted role prefix
    result = app.acquire_ref_note(claim, target, physical_copy_uuidv4=copy)
    assert result.body_retained and result.physical_copy_uuidv4 == copy
    assert (
        app.work.ledger.usage(app.work.request)["input_bytes"]
        > after_failure["input_bytes"]
    )
    assert (
        app.core.read_ref_note(claim, projection.evidence[0].mapping, app.work)
        == b"\0\xffbinary\r\n"
    )
    assert not (path.parent / "p1-recovery-stop.json").exists()


def test_ref_body_sigkill_preserves_original_copy_and_uncommitted_retry(acquisition):
    app, git_path, _, repository, origin, path, op_path = acquisition
    _, target, note = fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    original = app.acquire_ref_note(claim, target)
    assert original.body_retained
    attempted_copy = str(uuid4())
    before = app.work.ledger.usage(app.work.request)
    script = r"""
import json,os,signal,sys
from pathlib import Path
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.acquisition import UnlimitedWorkBudget
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.adapters.sqlite.p1_coordination import WorkLedger,NotesWorkBudget
from repo_catalog.adapters.sqlite.notes import NotesProgress
from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.application.notes import NotesAcquisition
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.p1_coordination import RequestIdentity,NotesLimits
from repo_catalog.domain.ref_observation import RefObservationKey
path,op_path,git_path,key,target,request,attempt,copy=json.loads(sys.argv[1])
core=GitCore(Path(path));db=connect(Path(op_path),"operational")
claim=core.ref_observation(RefObservationKey(*key),UnlimitedWorkBudget()).claims[0]
work=NotesWorkBudget(WorkLedger(db),RequestIdentity(*request),attempt,NotesLimits())
app=NotesAcquisition(core,GitNotesSource(GitNativeSource(Path(git_path))),work,NotesProgress(work),source_attribution="local-test")
insert=core._insert
def kill_after_body(table,values):
    insert(table,values)
    if table=="ref_retained_notes":os.kill(os.getpid(),signal.SIGKILL)
core._insert=kill_after_body
app.acquire_ref_note(claim,OID(*target),physical_copy_uuidv4=copy)
"""
    payload = [
        str(path),
        str(op_path),
        str(git_path),
        claim.ref_observation_key.key,
        target.key,
        app.work.request.values(),
        app.work.attempt_uuidv4,
        attempted_copy,
    ]
    child = subprocess.run(
        [sys.executable, "-c", script, json.dumps(payload)],
        capture_output=True,
        timeout=30,
    )
    assert child.returncode == -signal.SIGKILL, child.stderr.decode("utf-8", "replace")
    assert [
        row[0]
        for row in app.core.sql("SELECT physical_copy_uuidv4 FROM ref_retained_notes")
    ] == [original.physical_copy_uuidv4]
    after_kill = app.work.ledger.usage(app.work.request)
    assert after_kill["input_bytes"] > before["input_bytes"]
    with closing(GitCore(path)) as reopened:
        stored_claim, _, native = reopened.read_ref_note_copy(
            note, original.physical_copy_uuidv4, app.work
        )
        assert stored_claim == claim and native.body == b"\0\xffbinary\r\n"
    result = app.acquire_ref_note(claim, target, physical_copy_uuidv4=attempted_copy)
    assert result.body_retained and result.physical_copy_uuidv4 == attempted_copy
    assert {
        row[0]
        for row in app.core.sql("SELECT physical_copy_uuidv4 FROM ref_retained_notes")
    } == {original.physical_copy_uuidv4, attempted_copy}
    assert (
        app.work.ledger.usage(app.work.request)["input_bytes"]
        > after_kill["input_bytes"]
    )
    assert not (path.parent / "p1-recovery-stop.json").exists()


def test_ref_narrow_path_and_body_refusal_preserve_role_reports(
    acquisition, monkeypatch
):
    from dataclasses import replace

    from repo_catalog.domain.p1_core import OID

    app, git_path, fmt, repository, origin, path, _ = acquisition
    _, target, note = fixtures.fixture_note(acquisition)
    missing = OID(fmt, "b" * len(target.full_oid))
    root = fixtures.write(
        git_path,
        fmt,
        "tree",
        fixtures.entry(b"100644", target.full_oid.encode(), note)
        + fixtures.entry(b"40000", b"zz-unrelated", missing),
    )
    fixtures.git(git_path, "update-ref", "refs/notes/nested/review", root.full_oid)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    read = app.source.metadata
    inspected = []

    def metadata(oid, work):
        inspected.append(oid)
        return read(oid, work)

    monkeypatch.setattr(app.source, "metadata", metadata)
    role = app.acquire_ref_note(claim, target, retain_body=False)
    assert role.role_verified and not role.body_retained
    assert missing not in inspected
    inventory = app.inventory_ref(claim)
    assert inventory.failure_code and inventory.group.status in ("partial", "unknown")
    before = app.core.notes_mapping_projection(
        claim, target, "git-notes", "1", "native-notes-tree", app.work
    )
    original_body = app.source.note_body

    def bad_body(evidence, work):
        return replace(
            original_body(evidence, work), body=b"not the claimed native bytes"
        )

    monkeypatch.setattr(app.source, "note_body", bad_body)
    result = app.acquire_ref_note(claim, target)
    assert (
        result.role_verified
        and not result.body_retained
        and result.failure_code == "NATIVE_INTEGRITY"
    )
    after = app.core.notes_mapping_projection(
        claim, target, "git-notes", "1", "native-notes-tree", app.work
    )
    assert after.canonical_note_oid == before.canonical_note_oid == note
    assert not app.core.sql("SELECT 1 FROM ref_retained_notes")
    assert not (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("damage", ["mode", "ambiguous"])
def test_ref_unsupported_or_ambiguous_native_path_never_grants_body(
    acquisition, damage
):
    app, git_path, fmt, repository, origin, path, _ = acquisition
    _, target, note = fixtures.fixture_note(acquisition)
    if damage == "mode":
        body = fixtures.entry(b"100755", target.full_oid.encode(), note)
    else:
        inner = fixtures.write(
            git_path,
            fmt,
            "tree",
            fixtures.entry(b"100644", target.full_oid[2:].encode(), note),
        )
        body = fixtures.entry(
            b"40000", target.full_oid[:2].encode(), inner
        ) + fixtures.entry(b"100644", target.full_oid.encode(), note)
    root = fixtures.write(git_path, fmt, "tree", body)
    fixtures.git(git_path, "update-ref", "refs/notes/nested/review", root.full_oid)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    result = app.acquire_ref_note(claim, target)
    assert (
        not result.role_verified
        and not result.body_retained
        and result.failure_code == "NOTES_ROLE"
    )
    assert app.inventory_ref(claim).group.status in ("unknown", "partial")
    assert not app.core.sql("SELECT 1 FROM ref_retained_notes")
    assert not (path.parent / "p1-recovery-stop.json").exists()


def test_ref_group_insert_failure_rolls_back_new_objects_and_keeps_original(
    acquisition, monkeypatch
):
    from dataclasses import replace

    from repo_catalog.domain.p1_core import OID

    app, _, fmt, repository, origin, path, _ = acquisition
    fixtures.fixture_note(acquisition)
    claim = (
        discover(app, repository, origin, str(uuid4())).enumerations[0].links[0].claim
    )
    original = app.inventory_ref(claim).group
    width = 40 if fmt == "sha1" else 64
    target, note = OID(fmt, "c" * width), OID(fmt, "d" * width)
    new = replace(
        original,
        members=((target.full_oid, note.full_oid, target.full_oid),),
        provenance=replace(original.provenance, coordinate="independent-report"),
    )
    insert = app.core._insert

    def fail_after_group(table, values):
        insert(table, values)
        if table == "notes_mapping_groups":
            raise sqlite3.IntegrityError("synthetic failure after real Group insert")

    before = app.work.ledger.usage(app.work.request)
    monkeypatch.setattr(app.core, "_insert", fail_after_group)
    with pytest.raises(sqlite3.IntegrityError, match="after real Group insert"):
        app.core.admit_notes_mapping_group(new, app.work)
    monkeypatch.setattr(app.core, "_insert", insert)
    assert not app.core._db.in_transaction
    for oid in (target, note):
        assert not app.core.sql(
            "SELECT 1 FROM git_objects WHERE object_format=? AND full_oid=?", oid.key
        )
    projection = app.core.ref_notes_inventory_projection(claim, app.work)
    assert tuple(entry.group for entry in projection.groups) == (original,)
    after = app.work.ledger.usage(app.work.request)
    assert after["metadata_units"] > before["metadata_units"]
    app.core.admit_notes_mapping_group(new, app.work)
    projection = app.core.ref_notes_inventory_projection(claim, app.work)
    assert {entry.group for entry in projection.groups} == {original, new}
    assert (
        app.work.ledger.usage(app.work.request)["metadata_units"]
        > after["metadata_units"]
    )
    assert not (path.parent / "p1-recovery-stop.json").exists()
