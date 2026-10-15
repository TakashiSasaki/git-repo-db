"""Real Git SHA-1/SHA-256 bytes, supported grammar and atomic Core semantics."""

from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.adapters.git.native import GitNativeSource
from repo_catalog.adapters.sqlite.git_core import GitCore
from repo_catalog.adapters.sqlite.p1_schema import connect
from repo_catalog.domain.git_native import parse_metadata, parse_tree
from repo_catalog.domain.p1_core import (
    Capture,
    CoreFailure,
    GitObservation,
    NotesClaim,
    NotesProof,
    ScalarClaim,
)
from tests.integration.p1.test_core import Budget, native, oid, provenance


def git(path, *args, data=None):
    result = subprocess.run(
        ["git", "-C", str(path), *args], input=data, capture_output=True, timeout=30
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    return result.stdout


@pytest.fixture(params=["sha1", "sha256"])
def repository(tmp_path, request):
    path = tmp_path / "git"
    path.mkdir()
    git(path, "init", "--bare", "--object-format=" + request.param)
    return path, request.param


def write(path, fmt, kind, body, *, literal=False):
    expected = native(kind, body, fmt)
    assert (
        git(
            path,
            "hash-object",
            "-w",
            "-t",
            kind,
            "--stdin",
            *(["--literally"] if literal else []),
            data=body,
        )
        .strip()
        .decode()
        == expected.oid.full_oid
    )
    return expected


def commit_body(tree, parents=(), *, extra=b"", message=b"message\n"):
    return (
        b"tree "
        + tree.full_oid.encode()
        + b"\n"
        + b"".join(b"parent " + p.full_oid.encode() + b"\n" for p in parents)
        + b"author A\xff <a@invalid> 1 +0930\ncommitter C <c@invalid> 2 -0800\n"
        + extra
        + b"\n"
        + message
    )


def entry(mode, name, target):
    return mode + b" " + name + b"\0" + bytes.fromhex(target.full_oid)


def test_real_git_signed_extension_encoding_and_exact_binary_metadata(core, repository):
    c, _, _ = core
    path, fmt = repository
    tree = write(path, fmt, "tree", b"")
    # These parents are genuinely absent; only the requested commit is present.
    parents = (oid("a", fmt), oid("b", fmt))
    extras = b"encoding ISO-8859-1\ngpgsig -----BEGIN PGP SIGNATURE-----\n abc\n -----END PGP SIGNATURE-----\ngpgsig-sha256 second\n signature\nmergetag object retained-extension\n type commit\nx-extra opaque\n continuation\n"
    commit = write(
        path,
        fmt,
        "commit",
        commit_body(tree.oid, parents, extra=extras, message=b"\xffmessage\r\n"),
    )
    source = GitNativeSource(path)
    assert source.metadata(commit.oid) == commit
    c.admit_claim(ScalarClaim(commit.oid, "author", "wrong report", provenance()))
    physical = str(uuid4())
    c.admit_metadata(source.metadata(commit.oid), physical, Budget())
    c.admit_metadata(commit, physical, Budget())
    assert c.read_metadata(commit.oid) == commit.body
    assert c.scalar(commit.oid, "author").canonical == [
        "known",
        "A\udcff <a@invalid> 1 +0930",
    ]
    assert c.scalar(commit.oid, "author").reported_conflict
    assert c.scalar(commit.oid, "author_time_us").canonical == ["known", 1_000_000]
    assert (
        c.scalar(commit.oid, "message").canonical[1].encode("utf-8", "surrogateescape")
        == b"\xffmessage\r\n"
    )
    assert (
        bytes.fromhex(c.scalar(commit.oid, "header_data").canonical[1])
        == commit.body.partition(b"\n\n")[0]
    )
    assert c.scalar(commit.oid, "encoding").canonical == ["known", "ISO-8859-1"]
    assert c.relations(commit.oid, "commit_parents").canonical == [
        "complete",
        [[0, *parents[0].key], [1, *parents[1].key]],
    ]
    assert len(c.sql("SELECT physical_copy_uuidv4 FROM retained_metadata")) == 1
    assert c.scalar(parents[0], "type").canonical is None
    with pytest.raises(CoreFailure) as error:
        source.metadata(parents[0])
    assert error.value.code == "OBJECT_UNAVAILABLE"


@pytest.mark.parametrize("mode", [b"100644", b"100755", b"120000", b"160000", b"40000"])
def test_real_git_binary_tree_names_and_modes_missing_children(core, repository, mode):
    c, _, _ = core
    path, fmt = repository
    target = oid("a", fmt)
    body = entry(mode, b"a\n\xff\t", target)
    tree = write(path, fmt, "tree", body)
    c.admit_metadata(GitNativeSource(path).metadata(tree.oid), str(uuid4()), Budget())
    assert c.relations(tree.oid, "tree_entries").canonical == [
        "complete",
        [[[mode.decode(), b"a\n\xff\t".hex()], *target.key]],
    ]
    assert c.read_metadata(tree.oid) == body
    assert c.scalar(target, "size").canonical is None


def test_tree_native_basename_order_differs_from_plain_filename_order(repository):
    path, fmt = repository
    target = oid("a", fmt)
    body = (
        entry(b"100644", b"a.c", target)
        + entry(b"40000", b"a", target)
        + entry(b"100644", b"a0", target)
    )
    tree = write(path, fmt, "tree", body)
    assert GitNativeSource(path).metadata(tree.oid) == tree
    assert list(parse_tree(fmt, body)) == [b"a.c", b"a", b"a0"]


@pytest.mark.parametrize("tagger", [False, True])
@pytest.mark.parametrize("target_kind", ["commit", "tree", "blob", "tag"])
def test_real_git_annotated_tag_to_any_type_without_target_body(
    core, repository, tagger, target_kind
):
    c, _, _ = core
    path, fmt = repository
    target = oid("a", fmt)
    body = (
        f"object {target.full_oid}\ntype {target_kind}\ntag release-v1\n".encode()
        + (b"tagger A <a@invalid> 3 +0000\n" if tagger else b"")
        + b"\nannotation\n-----BEGIN PGP SIGNATURE-----\nopaque signature\n"
    )
    tag = write(path, fmt, "tag", body, literal=not tagger)
    c.admit_metadata(GitNativeSource(path).metadata(tag.oid), str(uuid4()), Budget())
    assert c.scalar(tag.oid, "tag_name").canonical == ["known", "release-v1"]
    assert c.relations(tag.oid, "tag_target").canonical == [
        "complete",
        [[0, *target.key]],
    ]
    assert c.read_metadata(tag.oid) == body
    assert c.scalar(target, "size").canonical is None


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"tree bad\n\n",
        b"tree " + b"a" * 40 + b"\n\n",
        b"tree "
        + b"a" * 40
        + b"\nauthor A <a> 0 +0000\ncommitter B <b> 0 +0000\nparent "
        + b"b" * 40
        + b"\n\n",
        b"tree " + b"0" * 40 + b"\nauthor A <a> 0 +0000\ncommitter B <b> 0 +0000\n\n",
        b"tree "
        + b"a" * 40
        + b"\nauthor A <a> "
        + b"9" * 5000
        + b" +0000\ncommitter B <b> 0 +0000\n\n",
    ],
)
def test_malformed_commit_is_typed_refusal_and_never_partial_admission(core, body):
    c, _, _ = core
    incoming = native("commit", body)
    with pytest.raises(CoreFailure) as error:
        c.admit_metadata(incoming, str(uuid4()), Budget())
    assert error.value.code == "NATIVE_SYNTAX"
    assert c.sql("SELECT * FROM git_objects") == []
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_metadata") == []


@pytest.mark.parametrize(
    "body",
    [
        b"100644 a\0",
        b"100664 a\0" + b"a" * 20,
        b"100644 ..\0" + b"a" * 20,
        b"100644 a/b\0" + b"a" * 20,
        b"100644 a\0" + b"\0" * 20,
        b"100644 b\0" + b"a" * 20 + b"100644 a\0" + b"a" * 20,
        b"100644 a\0" + b"a" * 20 + b"100755 a\0" + b"b" * 20,
    ],
)
def test_malformed_tree_fails_atomically(core, body):
    c, _, _ = core
    with pytest.raises(CoreFailure) as error:
        c.admit_metadata(native("tree", body), str(uuid4()), Budget())
    assert error.value.code == "NATIVE_SYNTAX"
    assert c.sql("SELECT * FROM git_objects") == []


@pytest.mark.parametrize("change", ["oid", "digest", "size", "type"])
def test_exact_native_integrity_failure_not_corruption_stop(core, change):
    c, path, _ = core
    incoming = native("tree", b"")
    bad = {
        "oid": {"oid": oid()},
        "digest": {"digest_sha256": "0" * 64},
        "size": {"declared_size": 1},
        "type": {"native_type": "tag"},
    }[change]
    with pytest.raises(CoreFailure) as error:
        c.admit_metadata(replace(incoming, **bad), str(uuid4()), Budget())
    assert error.value.code == "NATIVE_INTEGRITY"
    assert not (path.parent / "p1-recovery-stop.json").exists()
    c.admit_object(oid())


def test_native_atomic_failure_after_intrinsic_install_rolls_back(core, monkeypatch):
    c, _, _ = core
    incoming = native("commit", commit_body(oid()))
    original = c._insert

    def fail(table, values):
        if table == "intrinsic_claims" and values[2] == "author":
            raise RuntimeError("injected after retained bytes and groups")
        original(table, values)

    monkeypatch.setattr(c, "_insert", fail)
    with pytest.raises(RuntimeError):
        c.admit_metadata(incoming, str(uuid4()), Budget())
    for table in (
        "git_objects",
        "scalar_claims",
        "relation_groups",
        "intrinsic_groups",
    ):
        assert c.sql("SELECT * FROM " + table) == []
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_metadata") == []


def test_no_context_no_derivatives_reopen_preserves_native_authority(core):
    c, path, _ = core
    incoming = native("tree", b"")
    c.admit_metadata(incoming, str(uuid4()), Budget())
    other = GitCore(path)
    try:
        assert other.relations(incoming.oid, "tree_entries").canonical == [
            "known_empty",
            [],
        ]
        assert other.read_metadata(incoming.oid) == b""
        assert not any(
            (path.parent / (name + ".sqlite3")).exists()
            for name in ("context", "operational", "search")
        )
    finally:
        other.close()


def test_corruption_metadata_history_independent_until_byte_read_stops_catalog(core):
    c, path, _ = core
    incoming = native("tree", b"")
    copy = str(uuid4())
    c.admit_metadata(incoming, copy, Budget())
    # Privileged adversary damages actual stored bytes outside supported APIs.
    db = connect(path, "core")
    db.execute("DROP TRIGGER p1_immutable_retained_metadata_update")
    db.execute("PRAGMA ignore_check_constraints=ON")
    db.execute("UPDATE retained_metadata SET body=x'01'")
    db.close()
    assert c.relations(incoming.oid, "tree_entries").canonical == ["known_empty", []]
    with pytest.raises(CoreFailure) as error:
        c.read_metadata(incoming.oid)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()
    with pytest.raises(CoreFailure) as stopped:
        c.admit_object(oid())
    assert stopped.value.code == "RECOVERY_STOP"
    with pytest.raises(CoreFailure):
        GitCore(path)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT body FROM retained_metadata",
        "SELECT hex(body) FROM retained_metadata",
        "SELECT body FROM retained_notes",
        "SELECT proof_bundle FROM note_roles",
    ],
)
def test_generic_sql_cannot_emit_unchecked_retained_payloads(core, query):
    with pytest.raises(sqlite3.DatabaseError):
        core[0].sql(query)


def test_ordinary_blob_excluded_before_source_body_read(core, repository):
    c, _, _ = core
    path, fmt = repository
    blob = write(path, fmt, "blob", b"ordinary file")
    with pytest.raises(CoreFailure) as error:
        GitNativeSource(path).metadata(blob.oid)
    assert error.value.code == "RETENTION_PURPOSE"
    with pytest.raises(CoreFailure):
        c.admit_metadata(blob, str(uuid4()), Budget())
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_metadata") == []


def test_source_size_limit_and_environment_cannot_redirect(
    repository, tmp_path, monkeypatch
):
    path, fmt = repository
    tree = write(path, fmt, "tree", b"")
    commit = write(path, fmt, "commit", commit_body(tree.oid))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "unavailable"))
    source = GitNativeSource(path, metadata_bytes=1)
    with pytest.raises(CoreFailure) as error:
        source.metadata(commit.oid)
    assert error.value.code == "BUDGET"
    assert source.metadata(tree.oid) == tree


def test_real_ref_root_observations_retain_force_push_and_replay(core, repository):
    c, _, repo = core
    path, fmt = repository
    first = write(path, fmt, "commit", commit_body(oid("a", fmt)))
    second = write(path, fmt, "commit", commit_body(oid("b", fmt)))
    source = GitNativeSource(path)
    origin = str(uuid4())
    for number, incoming in enumerate((first, second)):
        git(path, "update-ref", "refs/heads/main", incoming.oid.full_oid)
        refs = source.refs()
        assert refs == ((b"refs/heads/main", incoming.oid, "commit", None),)
        capture = str(uuid4())
        observation = GitObservation(
            origin,
            capture,
            repo,
            "ref",
            ("refs/heads/main",),
            {
                "ref": "refs/heads/main",
                "observed_at_us": number,
                "target": incoming.oid.key,
            },
            provenance(str(number)),
        )
        c.admit_observation(observation)
        c.admit_observation(observation)
    assert len(c.sql("SELECT * FROM git_observations")) == 2


def test_receiver_notes_role_checks_full_native_commit_and_metadata_without_body(
    core, repository
):
    c, _, repo = core
    path, fmt = repository
    note = write(path, fmt, "blob", b"purpose-bound note")
    target = oid("a", fmt)
    root = write(
        path, fmt, "tree", entry(b"100644", target.full_oid.encode(), note.oid)
    )
    commit = write(
        path,
        fmt,
        "commit",
        commit_body(root.oid, extra=b"gpgsig signature\n continuation\n"),
    )
    capture = Capture(
        str(uuid4()),
        str(uuid4()),
        repo,
        "original",
        "refs/notes/nested/review",
        commit.oid,
    )
    proof = NotesProof(capture, target, note.oid, target.full_oid, (commit, root))
    c.admit_notes_claim(NotesClaim(capture, target, note.oid, provenance()))
    c.admit_notes_role(proof, Budget())
    assert c.notes_projection(capture, target).canonical == note.oid
    assert c.sql("SELECT physical_copy_uuidv4 FROM retained_notes") == []
    c.admit_note(proof, note, str(uuid4()), Budget())
    assert c.read_note(capture, target, note.oid) == note.body
    malformed = native(
        "commit",
        b"tree " + root.oid.full_oid.encode() + b"\n\ninvalid missing identities",
        fmt,
    )
    bad_capture = replace(capture, capture_uuidv4=str(uuid4()), root=malformed.oid)
    bad_proof = replace(proof, capture=bad_capture, structures=(malformed, root))
    with pytest.raises(CoreFailure) as error:
        c.admit_notes_role(bad_proof, Budget())
    assert error.value.code == "NOTES_ROLE"
    assert len(c.sql("SELECT * FROM captures")) == 1


def test_parser_format_and_tag_refusals_are_typed():
    for body in (
        b"object bad\ntype commit\ntag a\n\n",
        b"object " + b"a" * 40 + b"\ntype file\ntag a\n\n",
        b"object " + b"a" * 40 + b"\ntype commit\ntag a\ntagger invalid\n\n",
    ):
        with pytest.raises(CoreFailure) as error:
            parse_metadata("sha1", "tag", body)
        assert error.value.code == "NATIVE_SYNTAX"


def test_actual_relation_work_is_charged_on_replay_and_rejected_parse(core):
    c, _, _ = core
    incoming = native("commit", commit_body(oid(), (oid("b"), oid("c"))))
    work = Budget()
    physical = str(uuid4())
    c.admit_metadata(incoming, physical, work)
    first = dict(work.counts)
    assert first["metadata_units"] > 3
    c.admit_metadata(incoming, physical, work)
    assert work.counts["metadata_units"] == 2 * first["metadata_units"]
    before = work.counts["metadata_units"]
    with pytest.raises(CoreFailure):
        c.admit_metadata(
            native("commit", b"tree invalid\n\nmessage"), str(uuid4()), work
        )
    assert work.counts["metadata_units"] > before
    assert work.counts["input_bytes"] > 2 * len(incoming.body)


def test_relation_budget_exhaustion_rolls_back_without_corruption_stop(core):
    c, path, _ = core

    class Limited(Budget):
        def require(self, unit, amount=1):
            if unit == "metadata_units" and self.counts.get(unit, 0) + amount > 2:
                raise CoreFailure("BUDGET", unit, "test metadata work limit")

    with pytest.raises(CoreFailure) as error:
        c.admit_metadata(native("commit", commit_body(oid())), str(uuid4()), Limited())
    assert error.value.code == "BUDGET"
    assert not (path.parent / "p1-recovery-stop.json").exists()
    assert c.sql("SELECT * FROM git_objects") == []


def test_source_operating_system_and_timeout_failures_are_scoped(
    repository, monkeypatch
):
    path, _ = repository

    def missing(*args, **kwargs):
        raise FileNotFoundError("synthetic missing Git")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(CoreFailure) as error:
        GitNativeSource(path)
    assert error.value.code == "GIT_INPUT"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 30)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(CoreFailure) as error:
        GitNativeSource(path)
    assert error.value.code == "GIT_INPUT"


def test_native_messages_with_nul_are_rejected_not_silently_truncated(core):
    c, _, _ = core
    incoming = native("commit", commit_body(oid(), message=b"a\0b"))
    with pytest.raises(CoreFailure) as error:
        c.admit_metadata(incoming, str(uuid4()), Budget())
    assert error.value.code == "NATIVE_SYNTAX"
    assert c.sql("SELECT * FROM git_objects") == []


def test_loss_of_admitted_metadata_copy_is_corruption_not_optional_nonacquisition(core):
    c, path, _ = core
    incoming = native("tree", b"")
    c.admit_metadata(incoming, str(uuid4()), Budget())
    db = connect(path, "core")
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("DROP TRIGGER p1_immutable_retained_metadata_delete")
    db.execute("DELETE FROM retained_metadata")
    db.close()
    assert c.relations(incoming.oid, "tree_entries").canonical == ["known_empty", []]
    with pytest.raises(CoreFailure) as error:
        c.read_metadata(incoming.oid)
    assert error.value.code == "AUTHORITATIVE_CORRUPTION"
    assert (path.parent / "p1-recovery-stop.json").exists()


@pytest.mark.parametrize("operation", ["scalar", "relations", "bytes", "sql"])
def test_stop_published_during_last_read_prevents_ordinary_completion(core, operation):
    from repo_catalog.adapters.sqlite.p1_coordination import persist_catalog_stop

    c, path, _ = core
    incoming = native("tree", b"")
    c.admit_metadata(incoming, str(uuid4()), Budget())
    patterns = {
        "scalar": "FROM scalar_claims c",
        "relations": "FROM relation_groups g",
        "bytes": "SELECT * FROM retained_metadata",
        "sql": "SELECT full_oid FROM git_objects",
    }
    fired = []

    def trace(statement):
        if patterns[operation] in statement and not fired:
            fired.append(True)
            persist_catalog_stop(path.parent, "independent detector during last read")

    c._db.set_trace_callback(trace)
    with pytest.raises(CoreFailure) as error:
        if operation == "scalar":
            c.scalar(incoming.oid, "size")
        elif operation == "relations":
            c.relations(incoming.oid, "tree_entries")
        elif operation == "bytes":
            c.read_metadata(incoming.oid)
        else:
            c.sql("SELECT full_oid FROM git_objects")
    assert fired
    assert error.value.code == "RECOVERY_STOP"
    assert not c._db.in_transaction
