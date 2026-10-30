"""Full semantic request intent for local Access/Git acquisition replay.

The value is an Operational request snapshot, not a new event or repository ID.
No remote endpoint lookup, credential resolution or arbitrary dataclass codec.
"""

from __future__ import annotations

from repo_catalog.domain.acquisition import (
    GitMetadataInput,
    GitNativeAcquisitionRequest,
    NotesAcquisitionSpec,
    RefNotesInput,
)
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreCoverageScope,
    CoreFailure,
    GitObservation,
    NativeObject,
    NotesClaim,
    NotesGroup,
    Provenance,
    RelationGroup,
    RepositoryClaim,
    ScalarClaim,
    encode,
    uuid4_value,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ref_observation import RefObservationKey


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


def ref_notes_input_intent(value, repository):
    """Lossless original metadata coordinates for bounded request replay."""
    _typed(value, RefNotesInput)
    subject = value.observation
    _typed(subject.ref_observation_key, RefObservationKey)
    if subject.repository_uuidv4 != repository:
        raise CoreFailure("REPOSITORY_SCOPE", repository, "foreign ref observation")
    claims = []
    for claim in value.claims:
        claim.__post_init__()
        _typed(claim.provenance, Provenance)
        oids = (
            claim.direct_target_oid,
            claim.resolved_target_oid,
            claim.peeled_target_oid,
            claim.root_oid,
        )
        for oid in oids:
            if oid is not None:
                _oid(oid)
        claims.append(
            [
                list(claim.identity),
                claim.presence_state,
                claim.ref_form,
                [None if oid is None else list(oid.key) for oid in oids],
                None
                if claim.symbolic_target_ref_name is None
                else claim.symbolic_target_ref_name.hex(),
                None
                if claim.absence_evidence is None
                else claim.absence_evidence.encoded,
            ]
        )
    for item in (*value.mapping_claims, *value.mapping_groups):
        item.__post_init__()
        _typed(item.provenance, Provenance)
    return {
        "subject": [
            *subject.ref_observation_key.key,
            subject.repository_uuidv4,
            subject.ref_name_bytes.hex(),
            subject.source_attribution,
            subject.visibility_scope,
            subject.observed_at_us,
        ],
        "claims": claims,
        "mapping_claims": [list(item.key) for item in value.mapping_claims],
        "mapping_groups": [list(item.key) for item in value.mapping_groups],
    }


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
        request.nominated_ref_names,
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
    if any(
        type(value) is not bytes
        or not value.startswith(b"refs/")
        or b"\0" in value
        or len(value) > 4096
        for value in request.nominated_ref_names
    ):
        raise CoreFailure("REQUEST", "native", "bounded exact ref bytes required")
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
            notes.ref_inputs,
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
            "ref_inputs": [
                ref_notes_input_intent(item, repo) for item in notes.ref_inputs
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
        "nominated_ref_names": [name.hex() for name in request.nominated_ref_names],
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


def metadata_input_intent(unit: GitMetadataInput) -> dict:
    """Validate one selected repository and freeze external input without bodies.

    Reuse the native request's shared claims/Notes validation as a value-only
    projection, preserving every actual UUID/provenance coordinate. This does not
    execute a native request or infer repository membership for global OIDs.
    """
    _typed(unit, GitMetadataInput)
    common = native_request_intent(
        GitNativeAcquisitionRequest(
            unit.repository_uuidv4,
            unit.capture_origin_uuidv4,
            unit.capture_uuidv4,
            unit.source_attribution,
            unit.observed_at_us,
            select_oids=unit.nominal_objects,
            repository_claims=unit.repository_claims,
            extra_scalar_claims=unit.scalar_claims,
            extra_relation_groups=unit.relation_groups,
            physical_copy_uuidv4s=unit.physical_copy_uuidv4s,
            notes=unit.notes,
        )
    )
    for values in (
        unit.observations,
        unit.native_objects,
        unit.coverage_scopes,
        unit.coverage_claims,
        unit.coverage_proofs,
    ):
        if type(values) is not tuple or len(values) > 100_000:
            raise CoreFailure("REQUEST", "metadata", "bounded tuple input required")
    for observation in unit.observations:
        _typed(observation, GitObservation)
        _typed(observation.provenance, Provenance)
        if observation.repository_uuidv4 != unit.repository_uuidv4:
            raise CoreFailure("REPOSITORY_SCOPE", "metadata", "foreign observation")

    def scope_value(scope):
        _typed(scope, CoreCoverageScope)
        if (
            scope.owner_kind == "repository"
            and scope.coordinates[0] != unit.repository_uuidv4
        ):
            raise CoreFailure("REPOSITORY_SCOPE", "metadata", "foreign Coverage owner")
        return [scope.owner_kind, list(scope.coordinates)]

    def coverage_value(claim):
        _typed(claim, CoverageClaim)
        return [
            scope_value(claim.scope),
            claim.observed_at_us,
            claim.state,
            claim.details_json,
        ]

    native_values = []
    for native in unit.native_objects:
        if type(native) is not NativeObject or type(native.body) is not bytes:
            raise CoreFailure("REQUEST", "metadata", "typed native value required")
        _oid(native.oid)
        # Exact bytes are verified and charged by Core after request reservation;
        # Operational stores only their declared immutable coordinates.
        native_values.append(
            [
                list(native.oid.key),
                native.native_type,
                native.declared_size,
                native.digest_sha256,
            ]
        )
    proofs = []
    for proof in unit.coverage_proofs:
        if type(proof) is not tuple or len(proof) != 3:
            raise CoreFailure("REQUEST", "metadata", "typed Coverage proof required")
        claim, members, provenance = proof
        if type(members) is not tuple or len(members) > 100_000:
            raise CoreFailure("REQUEST", "metadata", "bounded proof members required")
        for oid in members:
            _oid(oid)
        _typed(provenance, Provenance)
        proofs.append(
            [
                coverage_value(claim),
                [list(oid.key) for oid in members],
                list(provenance.key),
            ]
        )
    result = {
        "common": common,
        "object_format": unit.object_format,
        "observations": [list(item.key) for item in unit.observations],
        "native_objects": native_values,
        "coverage_scopes": [scope_value(item) for item in unit.coverage_scopes],
        "coverage_claims": [coverage_value(item) for item in unit.coverage_claims],
        "coverage_proofs": proofs,
    }
    if len(encode(result)) > 1_000_000:
        raise CoreFailure(
            "BUDGET", "metadata-intent", "finite request metadata required"
        )
    return result
