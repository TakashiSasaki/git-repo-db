"""Actual production acquisition, exact bytes, observation/retry and failures."""

import sqlite3
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.notes import GitNotesSource
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.p1_coordination import NotesLimits
from repo_catalog.domain.p1_core import OID, CoreFailure, NotesClaim, Provenance

from .conftest import entry, fixture_note, git, write


@pytest.mark.parametrize("body", [b"", b"a\0\xff\xfe\r\n"])
@pytest.mark.parametrize("fanout,commit", [(0, True), (0, False), (2, False)])
def test_exact_role_body_inventory_and_replay(acquisition, body, fanout, commit):
    app, path, fmt, *_ = acquisition
    capture, target, note = fixture_note(
        acquisition, body, fanout=fanout, commit=commit
    )
    result = app.acquire_note(capture, target)
    assert result.body_retained and result.role_verified
    assert app.core.read_note(capture, target, note) == body
    usage = app.work.ledger.usage(app.work.request)
    replay = app.acquire_note(capture, target)
    assert replay == result
    assert (
        app.work.ledger.usage(app.work.request)["verification_bytes"]
        > usage["verification_bytes"]
        or body == b""
    )
    assert len(app.core.sql("SELECT physical_copy_uuidv4 FROM retained_notes")) == 1
    app.acquire_note(capture, target, physical_copy_uuidv4=str(uuid4()))
    assert len(app.core.sql("SELECT physical_copy_uuidv4 FROM retained_notes")) == 2
    inventory = app.inventory(capture)
    assert inventory.status == "complete"
    assert inventory.members == (
        (
            target.full_oid,
            note.full_oid,
            "/".join(["aa"] * fanout + [target.full_oid[2 * fanout :]]),
        ),
    )
    assert not (path.parent / "context.sqlite3").exists()


def test_discovery_full_scope_original_pair_and_historical_refs(acquisition):
    app, path, fmt, repository, origin, *_ = acquisition
    capture, target, note = fixture_note(acquisition)
    git(path, "update-ref", "refs/custom/annotation", capture.root.full_oid)
    observation = str(uuid4())
    args = (repository, "local-test", origin, observation, 1_000_000)
    found = app.discover(
        *args, nominated=("refs/custom/annotation", "refs/custom/absent")
    )
    assert found.observation.value["enumeration_state"] == "complete"
    assert {c.ref for c in found.captures} == {capture.ref, "refs/custom/annotation"}
    assert all(c.source == "local-test" for c in found.captures)
    git(path, "update-ref", "-d", capture.ref)
    replay = app.discover(
        *args, nominated=("refs/custom/annotation", "refs/custom/absent")
    )
    assert replay == found  # historical observation replay, no current-state claim
    newer = app.discover(repository, "local-test", origin, str(uuid4()), 2_000_000)
    assert newer.observation.value["enumeration_state"] == "known_empty"
    git(path, "update-ref", capture.ref, capture.root.full_oid)
    returned = app.discover(repository, "local-test", origin, str(uuid4()), 3_000_000)
    assert returned.captures[0].pair != found.captures[-1].pair
    assert returned.captures[0].root == capture.root
    assert app.acquire_note(found.captures[-1], target).body_retained
    with pytest.raises(CoreFailure, match="rebound"):
        app.discover(
            repository,
            "other-source",
            origin,
            observation,
            1_000_000,
            nominated=("refs/custom/annotation", "refs/custom/absent"),
        )


def test_ref_movement_new_observation_does_not_modify_old_capture(acquisition):
    app, path, fmt, repository, origin, *_ = acquisition
    capture, target, note = fixture_note(acquisition)
    old = app.discover(repository, "local-test", origin, str(uuid4()), 1).captures[0]
    assert app.acquire_note(old, target).body_retained
    empty = write(path, fmt, "tree", b"")
    git(path, "update-ref", capture.ref, empty.full_oid)
    new = app.discover(repository, "local-test", origin, str(uuid4()), 2).captures[0]
    assert new.pair != old.pair and new.root != old.root
    assert app.inventory(new).status == "known_empty"
    assert app.core.read_note(old, target, note) == b"\0\xffbinary\r\n"


def test_missing_targets_unrelated_subtrees_and_file_role(acquisition):
    app, path, fmt, *_ = acquisition
    capture, target, note = fixture_note(acquisition)
    missing = OID(fmt, "b" * len(target.full_oid))
    root = write(
        path,
        fmt,
        "tree",
        entry(b"100644", target.full_oid.encode(), note)
        + entry(b"40000", b"bb", missing),
    )
    capture = replace(capture, root=root)
    assert app.acquire_note(capture, target).body_retained
    assert app.inventory(capture).status == "partial"
    assert app.acquire_note(capture, missing).body_retained is False
    # The note OID also serves as an ordinary file, without authorizing file access.
    file_tree = write(path, fmt, "tree", entry(b"100644", b"ordinary.txt", note))
    file_capture = replace(capture, capture_uuidv4=str(uuid4()), root=file_tree)
    result = app.acquire_note(file_capture, target)
    assert result.failure_code == "NOTES_ROLE"
    assert not hasattr(app.source, "blob")


def test_valid_reports_survive_wrong_association_and_body_refusal(acquisition):
    app, path, fmt, *_ = acquisition
    capture, target, note = fixture_note(acquisition)
    other = write(path, fmt, "blob", b"wrong associated body")
    report = Provenance(
        "external-source", "original-observation", "member-1", "external", "1"
    )
    app.core.admit_notes_claim(NotesClaim(capture, target, other, report))
    app.core.admit_notes_claim(
        NotesClaim(capture, target, note, replace(report, source="independent"))
    )
    app.work.limits = NotesLimits(note_bytes=1)
    result = app.acquire_note(capture, target)
    assert (
        result.role_verified
        and not result.body_retained
        and result.failure_code == "BUDGET"
    )
    projection = app.core.notes_projection(capture, target)
    assert projection.reported_conflict and projection.canonical == note
    assert len(app.core.sql("SELECT note FROM notes_claims")) == 2
    assert not app.core.sql("SELECT physical_copy_uuidv4 FROM retained_notes")


def test_source_wrong_type_and_wrong_proof_never_reads_arbitrary_blob(acquisition):
    app, path, fmt, *_ = acquisition
    capture, target, note = fixture_note(acquisition)
    from repo_catalog.domain.notes import mapping_proof

    proof = mapping_proof(
        capture, target, lambda oid: app.source.metadata(oid, app.work), app.work
    )
    with pytest.raises(CoreFailure) as refused:
        app.source.note_body(replace(proof, note=target), app.work)
    assert refused.value.code == "NOTES_ROLE"
    with pytest.raises(CoreFailure) as refused:
        app.source.metadata(note, app.work)
    assert refused.value.code == "RETENTION_PURPOSE"


def test_discovery_detects_change_and_truncated_enumeration(acquisition, monkeypatch):
    app, path, fmt, *_ = acquisition
    capture, target, note = fixture_note(acquisition)
    original = app.source._scan
    calls = 0

    def changing(*args):
        nonlocal calls
        original(*args)
        calls += 1
        if calls == 1:
            git(path, "update-ref", "-d", capture.ref)

    monkeypatch.setattr(app.source, "_scan", changing)
    result = app.source.discover(app.work)
    assert result.failure_code == "REF_CHANGED" and not result.terminal
    assert result.status == "partial"
    git(path, "update-ref", capture.ref, capture.root.full_oid)
    limited = GitNotesSource(app.source.source, discovery_bytes=1)
    result = limited.discover(app.work)
    assert (
        not result.terminal
        and result.status == "unknown"
        and result.failure_code == "BUDGET"
    )


def test_body_atomic_rollback_and_existing_stop(acquisition, monkeypatch):
    app, path, fmt, *_ = acquisition
    capture, target, note = fixture_note(acquisition)
    insert = app.core._insert

    def broken(table, values):
        insert(table, values)
        if table == "retained_notes":
            raise sqlite3.IntegrityError("injected post-body constraint failure")

    monkeypatch.setattr(app.core, "_insert", broken)
    with pytest.raises(sqlite3.IntegrityError):
        app.acquire_note(capture, target)
    assert not app.core.sql("SELECT physical_copy_uuidv4 FROM retained_notes")
    assert app.core.notes_projection(capture, target).canonical == note
    monkeypatch.setattr(app.core, "_insert", insert)
    assert app.acquire_note(capture, target).body_retained
    from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop

    persist_catalog_stop(path.parent, "test existing stop")
    with pytest.raises(CoreFailure) as stopped:
        app.acquire_note(capture, target)
    assert stopped.value.code == "RECOVERY_STOP"


def test_corruption_stops_persistently_without_copy_failover(acquisition):
    app, path, fmt, _, _, core_path, *_ = acquisition
    capture, target, note = fixture_note(acquisition)
    assert app.acquire_note(capture, target).body_retained
    app.acquire_note(capture, target, physical_copy_uuidv4=str(uuid4()))
    # Privileged fixture damage, outside supported INSERT-only boundary.
    db = connect(core_path, "core")
    db.execute("DROP TRIGGER p1_immutable_retained_notes_update")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute("UPDATE retained_notes SET body=x'00'")
    db.close()
    with pytest.raises(CoreFailure) as corrupted:
        app.core.read_note(capture, target, note)
    assert corrupted.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").is_file()
    with pytest.raises(CoreFailure):
        app.acquire_note(capture, target)


def test_actual_git_notes_command_and_no_lazy_network(acquisition):
    app, path, fmt, repository, origin, *_ = acquisition
    target = write(path, fmt, "blob", b"ordinary target body must not be retained")
    note = write(path, fmt, "blob", b"\0\xfeoriginal\r\n")
    git(
        path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@invalid",
        "notes",
        "--ref=refs/notes/actual/git",
        "add",
        "--allow-empty",
        "-C",
        note.full_oid,
        target.full_oid,
    )
    listed = git(path, "notes", "--ref=refs/notes/actual/git", "list").strip().decode()
    assert listed == note.full_oid + " " + target.full_oid
    found = app.discover(repository, "local-test", origin, str(uuid4()), 1)
    capture = found.captures[0]
    assert app.acquire_note(capture, target).body_retained
    assert app.core.read_note(capture, target, note) == b"\0\xfeoriginal\r\n"
    assert app.source.source._environment()["GIT_NO_LAZY_FETCH"] == "1"
    assert app.core.sql("SELECT full_oid FROM retained_notes")[0][0] == note.full_oid
    assert not app.core.sql(
        "SELECT full_oid FROM retained_notes WHERE full_oid=?", (target.full_oid,)
    )


def test_source_incoming_loose_object_corruption_is_refusal_without_stop(acquisition):
    app, path, fmt, *_ = acquisition
    capture, target, note = fixture_note(acquisition)
    import zlib

    object_root = path / ("objects" if (path / "objects").is_dir() else ".git/objects")
    loose = object_root / note.full_oid[:2] / note.full_oid[2:]
    loose.chmod(0o600)
    loose.write_bytes(zlib.compress(b"blob 3\0bad"))
    result = app.acquire_note(capture, target)
    assert not result.body_retained and result.failure_code == "NATIVE_INTEGRITY"
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert app.core.notes_projection(capture, target).canonical == note
