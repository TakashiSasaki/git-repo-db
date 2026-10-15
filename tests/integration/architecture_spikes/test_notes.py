"""Real native-Git counterexamples for the purpose-bound notes retention spike."""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from .notes import (
    BudgetStop,
    Capture,
    GitInput,
    Limits,
    NotesCore,
    Refused,
    RequestWork,
    native_oid,
)


class Fixture:
    def __init__(self, path: Path, fmt: str) -> None:
        self.path, self.fmt = path / "git", fmt
        self.path.mkdir()
        self.git("init", f"--object-format={fmt}")
        self.git("config", "user.name", "Disposable notes fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.repository, self.origin = str(uuid4()), str(uuid4())
        self.core = NotesCore(path / "notes-core.sqlite3")
        self.work_path = path / "notes-operational.sqlite3"
        self.work = RequestWork(
            self.work_path,
            self.repository,
            "import nominated note mappings",
            Limits(),
            start=True,
        )
        self.input = GitInput(self.path, self.work)

    def git(self, *args: str, data: bytes | None = None) -> bytes:
        return subprocess.run(
            ["git", "-C", str(self.path), *args],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout.strip(b"\n")

    def blob(self, body: bytes) -> str:
        return self.git("hash-object", "-w", "--stdin", data=body).decode()

    def tree(self, entries: list[tuple[str, str, str]]) -> str:
        body = b"".join(
            mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(oid)
            for mode, name, oid in sorted(entries, key=lambda entry: entry[1])
        )
        return self.git(
            "hash-object", "--literally", "-t", "tree", "-w", "--stdin", data=body
        ).decode()

    def capture(self, root: str, ref: str = "refs/notes/review") -> Capture:
        self.git("update-ref", ref, root)
        return Capture(
            self.origin,
            str(uuid4()),
            self.repository,
            "local-disposable-git",
            ref,
            self.fmt,
            root,
        )

    def mapping(
        self, body: bytes, *, target: str | None = None
    ) -> tuple[Capture, str, str]:
        target = target or self.blob(b"annotation target; body is never imported")
        note = self.blob(body)
        root = self.tree([("100644", target, note)])
        return self.capture(root), target, note

    def admit(
        self, capture: Capture, target: str, note: str, body: bytes, **kwargs: object
    ) -> None:
        self.core.admit_note(
            capture,
            target,
            note,
            self.input,
            declared_size=len(body),
            declared_digest=hashlib.sha256(body).hexdigest(),
            **kwargs,
        )

    def counts(self) -> dict[str, int]:
        return {
            table: self.core.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "git_objects",
                "captures",
                "reports",
                "checked_structures",
                "note_bodies",
                "note_roles",
                "proof_links",
            )
        }


@pytest.fixture(params=["sha1", "sha256"])
def fixture(tmp_path: Path, request: pytest.FixtureRequest) -> Fixture:
    return Fixture(tmp_path, request.param)


def test_ordinary_file_metadata_allowed_body_refused(fixture: Fixture) -> None:
    f = fixture
    body = b"ordinary repository file"
    blob = f.blob(body)
    root = f.tree([("100644", "README.txt", blob)])
    capture = f.capture(root)
    f.core.metadata(f.fmt, blob)
    with pytest.raises(Refused, match="no supported target-to-note path"):
        f.admit(capture, blob, blob, body)
    assert f.counts()["git_objects"] == 1
    assert f.counts()["note_bodies"] == 0
    assert not hasattr(f.core, "read_blob")


@pytest.mark.parametrize("body", [b"review note\n", b"", b"\x00\xff\xfe\x00binary\r\n"])
def test_standard_git_notes_actual_commit_root_and_exact_binary(
    fixture: Fixture, body: bytes
) -> None:
    f = fixture
    target, note = f.blob(b"target"), f.blob(body)
    f.git(
        "notes", "--ref=refs/notes/commits", "add", "--allow-empty", "-C", note, target
    )
    root = f.git("rev-parse", "refs/notes/commits").decode()
    capture = f.capture(root, "refs/notes/commits")
    assert f.git("cat-file", "-t", root) == b"commit"
    assert f.git("notes", "--ref=refs/notes/commits", "list", target).decode() == note
    f.admit(capture, target, note, body)
    assert f.core.read_note(capture, target, note) == body
    assert f.counts()["checked_structures"] == 2  # commit + tree, never target
    assert f.core.db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_target_not_available_direct_tree_and_unrelated_missing_subtree(
    fixture: Fixture,
) -> None:
    f = fixture
    target = "a" * (40 if f.fmt == "sha1" else 64)
    missing_tree = "b" * len(target)
    body, note = b"note for a missing target", f.blob(b"note for a missing target")
    root = f.tree([("100644", target, note), ("40000", "zz-unrelated", missing_tree)])
    capture = f.capture(root)
    with pytest.raises(subprocess.CalledProcessError):
        f.git("cat-file", "-e", target)
    f.admit(capture, target, note, body)
    assert f.core.read_note(capture, target, note) == body
    assert f.counts()["checked_structures"] == 1
    assert f.core.db.execute(
        "SELECT native_type FROM checked_structures"
    ).fetchall() == [("tree",)]


def test_same_blob_file_and_note_roles_do_not_create_file_service(
    fixture: Fixture,
) -> None:
    f = fixture
    body = b"bytes shared by a file and an annotation"
    capture, target, note = f.mapping(body)
    file_root = f.tree([("100644", "ordinary.txt", note)])
    file_capture = f.capture(file_root, "refs/notes/looks-like-notes")
    f.core.metadata(f.fmt, note)
    f.admit(capture, target, note, body)
    with pytest.raises(Refused, match="no receiver-proven note role"):
        f.core.read_note(file_capture, target, note)
    with pytest.raises(Refused, match="no supported target-to-note path"):
        f.admit(file_capture, target, note, body)
    assert f.core.read_note(capture, target, note) == body
    assert (
        f.core.db.execute(
            "SELECT count(*) FROM git_objects WHERE object_format=? AND full_oid=?",
            (f.fmt, note),
        ).fetchone()[0]
        == 1
    )


def test_namespace_discovery_nested_and_explicit_refs(fixture: Fixture) -> None:
    f = fixture
    capture, target, note = f.mapping(b"nested")
    refs = [
        "refs/notes/commits",
        "refs/notes/team/review",
        "refs/notes/team/review/nested",
    ]
    # Git prohibits a ref and a descendant ref simultaneously; use disjoint names.
    refs = [refs[0], refs[1], "refs/notes/other/review/nested"]
    for ref in refs:
        f.git("update-ref", ref, capture.root)
    f.git("update-ref", "refs/custom/annotations", capture.root)
    discovered = f.input.discover(("refs/custom/annotations",))
    assert set(refs + [capture.ref, "refs/custom/annotations"]) == set(discovered)
    for ref in discovered:
        current = f.capture(capture.root, ref)
        f.admit(current, target, note, b"nested")
    assert f.counts()["note_roles"] == len(discovered)


def test_fanout_proof_only_walks_relevant_mapping(fixture: Fixture) -> None:
    f = fixture
    target = f.blob(b"fanout target")
    note, body = f.blob(b"fanout note"), b"fanout note"
    inner = f.tree([("100644", target[4:], note)])
    middle = f.tree([("40000", target[2:4], inner)])
    root = f.tree([("40000", target[:2], middle)])
    capture = f.capture(root)
    f.admit(capture, target, note, body)
    assert f.core.read_note(capture, target, note) == body
    assert f.counts()["checked_structures"] == 3
    assert f.core.db.execute("SELECT path FROM note_roles").fetchone()[0] == "/".join(
        [target[:2], target[2:4], target[4:]]
    )


def test_ref_update_delete_preserves_prior_capture_and_genuine_observations(
    fixture: Fixture,
) -> None:
    f = fixture
    first, target, note = f.mapping(b"historic")
    f.admit(first, target, note, b"historic")
    second = f.capture(first.root, first.ref)
    f.admit(second, target, note, b"historic")
    replacement_root = f.tree([])
    f.git("update-ref", first.ref, replacement_root)
    f.git("update-ref", "-d", first.ref)
    assert f.core.read_note(first, target, note) == b"historic"
    assert f.core.read_note(second, target, note) == b"historic"
    assert f.counts()["captures"] == 2
    assert f.counts()["note_bodies"] == 1


def test_external_sender_verified_report_cannot_authorize_then_later_local_proof(
    fixture: Fixture,
) -> None:
    f = fixture
    capture, target, note = f.mapping(b"reported first")
    external = replace(capture, source="claimed-provider/API")
    f.core.report(
        external, target, note, "provider:notes/42", f.work, sender_verified=True
    )
    f.core.report(
        external, target, note, "provider:notes/42", f.work, sender_verified=True
    )
    assert f.counts()["reports"] == 1
    assert f.counts()["note_bodies"] == 0
    with pytest.raises(Refused, match="no receiver-proven note role"):
        f.core.read_note(external, target, note)
    f.admit(external, target, note, b"reported first")
    first_counts, first_work = f.counts(), f.work.counts()
    f.admit(external, target, note, b"reported first")
    assert f.counts() == first_counts
    assert f.work.counts()["input_bytes"] > first_work["input_bytes"]
    assert f.core.db.execute("SELECT qualification FROM reports").fetchall() == [
        ("unauthenticated-report",)
    ]


def test_competing_reports_kept_but_only_relevant_proof_authorizes(
    fixture: Fixture,
) -> None:
    f = fixture
    capture, target, note = f.mapping(b"real note")
    competing = f.blob(b"fabricated attachment with valid native hash")
    f.core.report(capture, target, note, "API:one", f.work)
    f.core.report(capture, target, competing, "API:two", f.work)
    with pytest.raises(Refused, match="claimed association mismatch"):
        f.admit(
            capture, target, competing, b"fabricated attachment with valid native hash"
        )
    assert f.counts()["note_bodies"] == 0
    f.admit(capture, target, note, b"real note")
    assert f.counts()["reports"] == 2
    assert f.counts()["note_bodies"] == 1
    assert f.core.db.execute("SELECT DISTINCT note FROM reports").fetchall() == sorted(
        [(note,), (competing,)]
    )


@pytest.mark.parametrize(
    "mode,name_kind",
    [
        ("100755", "full"),
        ("120000", "full"),
        ("160000", "full"),
        ("100644", "short"),
        ("100644", "upper"),
    ],
)
def test_malformed_path_or_unsupported_relevant_mode(
    fixture: Fixture, mode: str, name_kind: str
) -> None:
    f = fixture
    target, note = f.blob(b"target"), f.blob(b"note")
    name = {"full": target, "short": target[:-1], "upper": target.upper()}[name_kind]
    root = f.tree([(mode, name, note)])
    capture = f.capture(root)
    with pytest.raises(Refused, match="mode|no supported"):
        f.admit(capture, target, note, b"note")
    assert f.counts()["note_bodies"] == 0


def test_standalone_hash_and_notes_prefix_do_not_prove_attachment(
    fixture: Fixture,
) -> None:
    f = fixture
    capture, target, note = f.mapping(b"standalone")
    false_target = f.blob(b"unrelated target")
    assert native_oid(f.fmt, "blob", b"standalone") == note
    f.core.report(capture, false_target, note, "API:claimed-association", f.work)
    with pytest.raises(Refused, match="no supported target-to-note path"):
        f.admit(capture, false_target, note, b"standalone")
    assert f.counts()["note_bodies"] == 0


@pytest.mark.parametrize("mismatch", ["size", "digest", "type", "format"])
def test_exact_native_identity_and_supplied_size_digest_required(
    fixture: Fixture, mismatch: str
) -> None:
    f = fixture
    capture, target, note = f.mapping(b"exact note")
    digest, size = hashlib.sha256(b"exact note").hexdigest(), len(b"exact note")
    if mismatch == "size":
        size += 1
    elif mismatch == "digest":
        digest = "0" * 64
    elif mismatch == "type":
        note = f.tree([])
        capture = f.capture(f.tree([("100644", target, note)]))
    else:
        opposite = "sha256" if f.fmt == "sha1" else "sha1"
        width = 64 if opposite == "sha256" else 40
        # All identities are syntactically valid in the asserted format. This
        # must reach the adapter-format fence, not fail early on OID width.
        capture = replace(capture, fmt=opposite, root="a" * width)
        target, note = "b" * width, "c" * width
    reason = {
        "size": "declared exact note size/digest mismatch",
        "digest": "declared exact note size/digest mismatch",
        "type": "note must have native blob type",
        "format": "object-format mismatch",
    }[mismatch]
    with pytest.raises(Refused, match=reason):
        f.core.admit_note(
            capture, target, note, f.input, declared_size=size, declared_digest=digest
        )
    assert f.counts()["note_bodies"] == 0


def test_atomic_admission_rollback_does_not_erase_work(fixture: Fixture) -> None:
    f = fixture
    capture, target, note = f.mapping(b"atomic note")
    f.core.report(capture, target, note, "API:prior report", f.work)
    before = f.counts()
    with pytest.raises(Refused, match="injected atomic"):
        f.admit(capture, target, note, b"atomic note", interrupt_after_body=True)
    assert f.counts() == before
    assert f.work.counts()["input_bytes"] > 0
    assert f.work.counts()["proof_objects"] == 1
    f.admit(capture, target, note, b"atomic note")
    assert f.core.read_note(capture, target, note) == b"atomic note"


def test_finite_note_limit_preserves_metadata_explicit_increase_and_lower_limit(
    fixture: Fixture,
) -> None:
    f = fixture
    body = b"over test size limit"
    capture, target, note = f.mapping(body)
    f.core.report(capture, target, note, "API:oversize-report", f.work)
    f.work.limits = replace(f.work.limits, note_bytes=len(body) - 1)
    with pytest.raises(BudgetStop, match="individual raw-note"):
        f.admit(capture, target, note, body)
    assert f.counts()["reports"] == 1
    assert f.counts()["note_bodies"] == 0
    spent = f.work.counts()
    f.work.limits = replace(f.work.limits, note_bytes=len(body))
    f.admit(capture, target, note, body)
    assert f.work.counts()["proof_objects"] > spent["proof_objects"]
    f.work.limits = replace(f.work.limits, note_bytes=1)
    assert f.core.read_note(capture, target, note) == body


@pytest.mark.parametrize("unit", ["proof_objects", "input_bytes", "metadata_units"])
def test_cumulative_limits_survive_failed_attempt_and_reopen(
    fixture: Fixture, unit: str
) -> None:
    f = fixture
    capture, target, note = f.mapping(b"budgeted")
    if unit == "proof_objects":
        # Commit-root proof needs two objects, so a one-object limit stops mid-proof.
        tree = capture.root
        commit = f.git("commit-tree", tree, data=b"fixture commit\n").decode()
        capture = f.capture(commit)
    f.work.limits = replace(f.work.limits, **{unit: 1})
    with pytest.raises(BudgetStop, match=unit):
        f.admit(capture, target, note, b"budgeted")
    spent = f.work.counts()
    assert spent[unit] >= 1
    assert f.counts()["note_bodies"] == 0
    f.work.db.close()
    resumed = RequestWork(
        f.work_path,
        f.repository,
        "import nominated note mappings",
        f.work.limits,
        start=False,
    )
    f.work, f.input = resumed, GitInput(f.path, resumed)
    with pytest.raises(BudgetStop):
        f.admit(capture, target, note, b"budgeted")
    assert f.work.counts()[unit] >= spent[unit]
    f.work.limits = Limits()
    f.admit(capture, target, note, b"budgeted")
    assert f.core.read_note(capture, target, note) == b"budgeted"


def test_missing_operational_counters_refuse_resume_without_invalidating_core(
    fixture: Fixture, tmp_path: Path
) -> None:
    f = fixture
    capture, target, note = f.mapping(b"already durable")
    f.admit(capture, target, note, b"already durable")
    with pytest.raises(BudgetStop, match="accounting unavailable"):
        RequestWork(
            tmp_path / "lost-operational.sqlite3",
            f.repository,
            "import nominated note mappings",
            Limits(),
            start=False,
        )
    assert f.core.read_note(capture, target, note) == b"already durable"


def test_capture_rebinding_and_insert_only_guards(fixture: Fixture) -> None:
    f = fixture
    capture, target, note = f.mapping(b"immutable")
    f.admit(capture, target, note, b"immutable")
    with pytest.raises(Refused, match="immutable Capture binding"):
        f.core.report(
            replace(capture, source="different-source"), target, note, "API:new", f.work
        )
    for sql in [
        "UPDATE note_roles SET checker=checker",
        "DELETE FROM note_bodies",
        "INSERT OR REPLACE INTO note_bodies SELECT * FROM note_bodies",
    ]:
        with pytest.raises(sqlite3.IntegrityError, match="INSERT-only"):
            f.core.db.execute(sql)
        f.core.db.rollback()
    assert f.core.read_note(capture, target, note) == b"immutable"


@pytest.mark.parametrize("value", [0, -1, float("inf"), 1.5, True])
def test_invalid_unbounded_settings_refused(value: object) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        Limits(input_bytes=value)  # type: ignore[arg-type]


def test_real_corrupted_loose_blob_fails_receiver_native_oid_check(
    fixture: Fixture,
) -> None:
    import zlib

    f = fixture
    capture, target, note = f.mapping(b"honest bytes")
    # Corrupt the disposable incoming Git fixture, never the admitted Core.
    # cat-file on this Git version returns the bytes without recomputing the OID;
    # the receiver must detect it independently rather than trusting that command.
    loose = f.path / ".git" / "objects" / note[:2] / note[2:]
    loose.chmod(0o600)  # Git deliberately creates loose objects read-only.
    loose.write_bytes(zlib.compress(b"blob 12\0forged bytes"))
    with pytest.raises(Refused, match="native type/size/OID verification failed"):
        f.admit(capture, target, note, b"honest bytes")
    assert f.counts()["note_bodies"] == 0
    assert f.work.counts()["input_bytes"] > 0


def test_discovery_has_finite_actual_work_envelope(fixture: Fixture) -> None:
    f = fixture
    f.mapping(b"discovered")
    f.work.limits = replace(f.work.limits, input_bytes=1)
    with pytest.raises(BudgetStop, match="input_bytes"):
        f.input.discover()
    assert f.work.counts()["input_bytes"] == 2  # bounded one-byte exhaustion probe
    assert f.counts()["note_bodies"] == 0


def test_output_rejects_capture_rebinding(fixture: Fixture) -> None:
    f = fixture
    capture, target, note = f.mapping(b"qualified role")
    f.admit(capture, target, note, b"qualified role")
    with pytest.raises(Refused, match="immutable Capture binding"):
        f.core.read_note(replace(capture, root=f.tree([])), target, note)
