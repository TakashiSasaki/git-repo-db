from uuid import uuid4

import pytest

from repo_catalog.domain.p1_core import OID, CoreFailure, Provenance
from repo_catalog.domain.ref_observation import (
    RefAbsenceEvidence,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
)

V7 = "01890f47-0000-7000-8000-000000000001"


def report(coordinate):
    return Provenance("source", "original", coordinate, "reader", "1")


def test_observation_identity_and_lossless_ref():
    key = RefObservationKey(str(uuid4()), V7)
    ref = RefObservation(key, str(uuid4()), b"refs/heads/\xff", "source", "visible")
    assert ref.ref_name_bytes == b"refs/heads/\xff"
    with pytest.raises(CoreFailure):
        RefObservationKey(key.observation_origin_uuidv4, str(uuid4()))
    with pytest.raises(CoreFailure):
        RefObservationKey(
            key.observation_origin_uuidv4, "01890f47-0000-7000-0000-000000000001"
        )
    with pytest.raises(CoreFailure):
        RefObservation(
            key, ref.repository_uuidv4, ref.ref_name_bytes, "source", "visible", True
        )


def test_unknown_target_and_scoped_absence_are_distinct_results():
    key = RefObservationKey(str(uuid4()), V7)
    unknown = RefObservationClaim(key, report("one"), "present")
    evidence = RefAbsenceEvidence(
        "source", "visible", b"refs/heads/main", "lookup", "completed"
    )
    absent = RefObservationClaim(
        key, report("two"), "absent", absence_evidence=evidence
    )
    assert unknown != absent
    assert RefAbsenceEvidence.decode(evidence.encoded) == evidence
    with pytest.raises(CoreFailure):
        RefObservationClaim(key, report("three"), "absent")
    with pytest.raises(CoreFailure):
        RefObservationClaim(
            key,
            report("three"),
            "absent",
            root_oid=OID("sha1", "a" * 40),
            absence_evidence=evidence,
        )
    with pytest.raises(CoreFailure):
        RefAbsenceEvidence(
            "source",
            "visible",
            b"refs/heads/main",
            "enumeration",
            "partial",
            b"refs/tags/",
        )


def test_absence_requires_completed_enumeration_that_covers_the_ref():
    evidence = RefAbsenceEvidence(
        "source",
        "scope",
        b"refs/heads/topic",
        "enumeration",
        "terminal-1",
        b"refs/heads/",
        "complete",
    )
    assert RefAbsenceEvidence.decode(evidence.encoded) == evidence
    with pytest.raises(CoreFailure):
        RefAbsenceEvidence(
            "source",
            "scope",
            b"refs/heads/topic",
            "enumeration",
            "partial",
            b"refs/heads/",
        )
    with pytest.raises(CoreFailure):
        RefAbsenceEvidence(
            "source",
            "scope",
            b"refs/heads/topic",
            "enumeration",
            "terminal-1",
            b"refs/tags/",
            "complete",
        )


def test_deeply_nested_absence_input_is_rejected_as_invalid():
    from repo_catalog.domain.ref_observation import valid_ref_absence

    malformed = "[" * 2_000 + "]" * 2_000
    with pytest.raises(CoreFailure):
        RefAbsenceEvidence.decode(malformed)
    assert not valid_ref_absence(malformed)
