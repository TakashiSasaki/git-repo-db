"""Full original native request intent, separate from catalog and Access identity."""

from dataclasses import replace
from uuid import uuid4

import pytest

from repo_catalog.domain.acquisition import (
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
)
from repo_catalog.domain.native_acquisition import native_request_intent
from repo_catalog.domain.p1_core import (
    OID,
    CoreFailure,
    Provenance,
    RepositoryClaim,
    ScalarClaim,
    encode,
)


@pytest.fixture
def request_value():
    return GitNativeAcquisitionRequest(
        str(uuid4()), str(uuid4()), str(uuid4()), "actual-source", 1
    )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("source_attribution", 1),
        ("retain_bytes", 1),
        ("include_refs", None),
        ("traverse_structural_targets", "true"),
        ("select_oids", []),
        ("select_oids", ("not-an-oid",)),
        ("ref_prefixes", ("",)),
        ("ref_prefixes", ("refs/\0bad",)),
        ("ref_prefixes", (True,)),
        ("retain_oids", set()),
        ("physical_copy_uuidv4s", []),
        ("repository_claims", ("bad",)),
        ("extra_scalar_claims", ("bad",)),
        ("extra_relation_groups", ("bad",)),
        ("notes", {}),
    ],
)
def test_invalid_native_intent_rejected(request_value, field, bad):
    value = replace(request_value, **{field: bad})
    with pytest.raises(CoreFailure):
        native_request_intent(value)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("discover_notes", 1),
        ("nominated_refs", ["refs/notes/a"]),
        ("nominated_refs", ("",)),
        ("discovery_observation_uuidv4", "bad"),
        ("target_oids", ("bad",)),
        ("retain_note_bodies", 1),
    ],
)
def test_invalid_notes_intent_rejected(request_value, field, bad):
    value = replace(request_value, notes=NotesAcquisitionSpec(**{field: bad}))
    with pytest.raises(CoreFailure):
        native_request_intent(value)


def test_all_request_fields_have_operational_representation(request_value):
    oid = OID("sha1", "a" * 40)
    provenance = Provenance("s", "o", "c", "d", "1")
    claim = RepositoryClaim(
        request_value.repository_uuidv4, "name", "unchanged", provenance
    )
    extra = ScalarClaim(oid, "message", "original", provenance)
    unit = replace(
        request_value,
        repository_claims=(claim,),
        extra_scalar_claims=(extra,),
        retain_oids=frozenset([oid]),
        physical_copy_uuidv4s={oid: str(uuid4())},
        notes=NotesAcquisitionSpec(nominated_refs=("refs/notes/a",)),
    )
    original = encode(native_request_intent(unit))
    alternatives = [
        replace(unit, repository_claims=(replace(claim, value="different"),)),
        replace(unit, extra_scalar_claims=(replace(extra, value="changed"),)),
        replace(unit, physical_copy_uuidv4s={oid: str(uuid4())}),
        replace(unit, notes=replace(unit.notes, nominated_refs=("refs/notes/b",))),
    ]
    assert all(
        encode(native_request_intent(value)) != original for value in alternatives
    )
    assert encode(native_request_intent(unit)) == original


def test_mutated_nested_claim_is_revalidated(request_value):
    value = RepositoryClaim(
        request_value.repository_uuidv4,
        "name",
        "original",
        Provenance("s", "o", "c", "d", "1"),
    )
    object.__setattr__(value, "field", "unsupported")
    with pytest.raises(CoreFailure):
        native_request_intent(replace(request_value, repository_claims=(value,)))
