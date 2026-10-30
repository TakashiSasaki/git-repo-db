"""Explicit new-model Notes fixture composition, never legacy row conversion."""

from uuid import uuid4

from repo_catalog.domain.p1_core import Provenance
from repo_catalog.domain.ref_observation import (
    NotesMapping,
    NotesMappingEvidence,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
    new_uuid7,
)


def admit_fixture_note(
    core,
    repository,
    tree,
    target,
    note,
    work,
    *,
    copy_uuid=None,
    name=b"refs/notes/fixture",
):
    key = RefObservationKey(str(uuid4()), new_uuid7())
    core.admit_ref_observation(
        RefObservation(key, repository, name, "fixture", "visible")
    )
    claim = RefObservationClaim(
        key,
        Provenance("fixture", "read", "claim", "test", "1"),
        "present",
        root_oid=tree.oid,
    )
    core.admit_ref_observation_claim(claim)
    mapping = NotesMapping(
        tree.oid,
        "git-notes",
        "1",
        "native-notes-tree",
        target,
        note.oid,
        target.full_oid,
    )
    evidence = NotesMappingEvidence(
        claim,
        mapping,
        "single-path",
        Provenance(
            "fixture", "receiver", "path", "native-notes", "1", "receiver_intrinsic"
        ),
        (tree,),
    )
    core.admit_ref_note(evidence, note, copy_uuid or str(uuid4()), work)
    return claim, mapping
