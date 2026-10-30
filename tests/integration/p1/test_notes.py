"""Purpose-bound native notes proofs: no ordinary-file archival API."""

from __future__ import annotations

import subprocess
from uuid import uuid4

import pytest

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
    from types import SimpleNamespace

    fixture = SimpleNamespace(
        capture=SimpleNamespace(root=root.oid),
        target=target,
        note=note.oid,
        path=target.full_oid,
        structures=(root,),
    )
    return fixture, note


@pytest.mark.parametrize("fmt", ["sha1", "sha256"])
@pytest.mark.parametrize("body", [b"", b"simple\n", b"\x00\xffbinary\r\n"])
def test_new_role_exact_binary_body_and_git_hash(core, fmt, body):
    from repo_catalog.domain.p1_core import Provenance
    from repo_catalog.domain.ref_observation import (
        NotesMapping,
        NotesMappingEvidence,
        RefObservation,
        RefObservationClaim,
        RefObservationKey,
        new_uuid7,
    )

    c, _, repository = core
    fixture, note = mapping(repository, body, fmt)
    key = RefObservationKey(str(uuid4()), new_uuid7())
    c.admit_ref_observation(
        RefObservation(key, repository, b"refs/notes/review", "source", "visible")
    )
    claim = RefObservationClaim(
        key, provenance("read"), "present", root_oid=fixture.capture.root
    )
    c.admit_ref_observation_claim(claim)
    content = NotesMapping(
        fixture.capture.root,
        "git-notes",
        "1",
        "tree",
        fixture.target,
        note.oid,
        fixture.path,
    )
    evidence = NotesMappingEvidence(
        claim,
        content,
        "single-path",
        Provenance("local", "read", "path", "native-notes", "1", "receiver_intrinsic"),
        fixture.structures,
    )
    c.admit_ref_note(evidence, note, str(uuid4()), Budget())
    assert c.read_ref_note(claim, content, Budget()) == body
    assert not c.sql("SELECT 1 FROM retained_metadata")
    result = subprocess.run(
        ["git", "hash-object", "--stdin"], input=body, capture_output=True, check=True
    )
    if fmt == "sha1":
        assert result.stdout.strip().decode() == note.oid.full_oid
