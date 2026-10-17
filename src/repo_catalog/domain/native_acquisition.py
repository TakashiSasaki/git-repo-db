"""Full semantic request intent for local Access/Git acquisition replay.

The value is an Operational request snapshot, not a new event or repository ID.
No remote endpoint lookup, credential resolution or arbitrary dataclass codec.
"""

from __future__ import annotations

from repo_catalog.domain.acquisition import (
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
)
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreFailure,
    NotesClaim,
    NotesGroup,
    Provenance,
    RelationGroup,
    RepositoryClaim,
    ScalarClaim,
    encode,
    uuid4_value,
)


def _typed(value, expected):
    if type(value) is not expected:
        raise CoreFailure("REQUEST", "native", "typed semantic value required")
    value.__post_init__()
    return value


def _oid(value):
    _typed(value, OID)


def _capture(value):
    _typed(value, Capture)
    _oid(value.root)


def _text_tuple(values):
    if any(
        type(value) is not str or not value or len(value) > 4096 or "\x00" in value
        for value in values
    ):
        raise CoreFailure("REQUEST", "native", "bounded nonempty ref text required")


def native_request_intent(request: GitNativeAcquisitionRequest) -> dict:
    """Validate repository ownership and preserve every request-defining input."""
    if type(request) is not GitNativeAcquisitionRequest:
        raise CoreFailure("REQUEST", "native", "typed native request required")
    request.__post_init__()
    if (
        type(request.source_attribution) is not str
        or not request.source_attribution
        or len(request.source_attribution) > 65_536
    ):
        raise CoreFailure(
            "REQUEST", "native", "bounded actual source attribution required"
        )
    for value in (
        request.retain_bytes,
        request.include_refs,
        request.traverse_structural_targets,
    ):
        if type(value) is not bool:
            raise CoreFailure("REQUEST", "native", "typed boolean required")
    for values in (
        request.select_oids,
        request.nominal_missing_oids,
        request.ref_prefixes,
        request.repository_claims,
        request.extra_scalar_claims,
        request.extra_relation_groups,
    ):
        if type(values) is not tuple or len(values) > 100_000:
            raise CoreFailure("REQUEST", "native", "bounded tuple input required")
    if request.retain_oids is not None and (
        type(request.retain_oids) is not frozenset or len(request.retain_oids) > 100_000
    ):
        raise CoreFailure("REQUEST", "native", "typed retention set required")
    if (
        type(request.physical_copy_uuidv4s) is not dict
        or len(request.physical_copy_uuidv4s) > 100_000
    ):
        raise CoreFailure("REQUEST", "native", "bounded copy coordinates required")
    for oid in (
        *request.select_oids,
        *request.nominal_missing_oids,
        *(request.retain_oids or ()),
        *request.physical_copy_uuidv4s,
    ):
        _oid(oid)
    for identity in request.physical_copy_uuidv4s.values():
        uuid4_value(identity)
    _text_tuple(request.ref_prefixes)
    repo = request.repository_uuidv4
    for claim in request.repository_claims:
        _typed(claim, RepositoryClaim)
        _typed(claim.provenance, Provenance)
        if claim.repository_uuidv4 != repo:
            raise CoreFailure("REPOSITORY_SCOPE", repo, "foreign repository claim")
    for claim in request.extra_scalar_claims:
        _typed(claim, ScalarClaim)
        _oid(claim.subject)
        _typed(claim.provenance, Provenance)
    for group in request.extra_relation_groups:
        _typed(group, RelationGroup)
        _oid(group.subject)
        _typed(group.provenance, Provenance)
        for member in group.members:
            _oid(member.target)
    notes = request.notes
    notes_value = None
    if notes is not None:
        if type(notes) is not NotesAcquisitionSpec:
            raise CoreFailure("REQUEST", "notes", "typed Notes specification required")
        for value in (
            notes.discover_notes,
            notes.acquire_inventories,
            notes.retain_note_bodies,
        ):
            if type(value) is not bool:
                raise CoreFailure("REQUEST", "notes", "typed boolean required")
        if notes.discovery_observation_uuidv4 is not None:
            uuid4_value(notes.discovery_observation_uuidv4)
        for values in (
            notes.explicit_captures,
            notes.external_claims,
            notes.external_groups,
            notes.target_oids,
            notes.nominated_refs,
        ):
            if type(values) is not tuple or len(values) > 100_000:
                raise CoreFailure("REQUEST", "notes", "bounded tuple input required")
        _text_tuple(notes.nominated_refs)
        for oid in notes.target_oids:
            _oid(oid)
        for capture in notes.explicit_captures:
            _capture(capture)
        for claim in notes.external_claims:
            _typed(claim, NotesClaim)
            _capture(claim.capture)
            _oid(claim.target)
            _oid(claim.note)
            _typed(claim.provenance, Provenance)
        for group in notes.external_groups:
            _typed(group, NotesGroup)
            _capture(group.capture)
            _typed(group.provenance, Provenance)
        captures = (
            *notes.explicit_captures,
            *(item.capture for item in notes.external_claims),
            *(item.capture for item in notes.external_groups),
        )
        if any(item.repository_uuidv4 != repo for item in captures):
            raise CoreFailure("REPOSITORY_SCOPE", repo, "foreign Notes capture")
        notes_value = {
            "discover": notes.discover_notes,
            "nominated_refs": list(notes.nominated_refs),
            "discovery_observation": notes.discovery_observation_uuidv4,
            "inventories": notes.acquire_inventories,
            "targets": [list(oid.key) for oid in notes.target_oids],
            "retain_bodies": notes.retain_note_bodies,
            "captures": [list(capture.key) for capture in notes.explicit_captures],
            "claims": [
                [list(item.capture.key), list(item.key)]
                for item in notes.external_claims
            ],
            "groups": [
                [list(item.capture.key), list(item.key)]
                for item in notes.external_groups
            ],
        }
    result = {
        "repository_uuidv4": repo,
        "capture_origin_uuidv4": request.capture_origin_uuidv4,
        "capture_uuidv4": request.capture_uuidv4,
        "source_attribution": request.source_attribution,
        "observed_at_us": request.observed_at_us,
        "selected": [list(oid.key) for oid in request.select_oids],
        "retain_bytes": request.retain_bytes,
        "retain_oids": None
        if request.retain_oids is None
        else sorted(list(oid.key) for oid in request.retain_oids),
        "include_refs": request.include_refs,
        "ref_prefixes": list(request.ref_prefixes),
        "traverse_structural_targets": request.traverse_structural_targets,
        "nominal_missing": [list(oid.key) for oid in request.nominal_missing_oids],
        "repository_claims": [list(claim.key) for claim in request.repository_claims],
        "extra_scalar_claims": [
            list(claim.key) for claim in request.extra_scalar_claims
        ],
        "extra_relation_groups": [
            list(group.key) for group in request.extra_relation_groups
        ],
        "physical_copies": sorted(
            [*oid.key, value] for oid, value in request.physical_copy_uuidv4s.items()
        ),
        "notes": notes_value,
    }
    # Fail before persisting an unbounded caller-authored intent. This contains no
    # ordinary file bodies; JSON size is not permission to accept secret settings.
    if len(encode(result)) > 1_000_000:
        raise CoreFailure(
            "BUDGET", "request-intent", "finite request metadata required"
        )
    return result
