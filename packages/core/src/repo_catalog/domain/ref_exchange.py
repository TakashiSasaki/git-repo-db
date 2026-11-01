"""Lossless typed Ref values shared by Recovery and optional Exchange.

Wire records retain original observations and reports.  Local verification is
repeated at admission; a serialized decoder label is never itself authority.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar

from repo_catalog.domain.p1_core import (
    OID,
    NativeObject,
    Provenance,
    _performed,
    encode,
    uuid4_value,
)
from repo_catalog.domain.ref_observation import (
    NotesMapping,
    NotesMappingClaim,
    NotesMappingEvidence,
    NotesMappingGroup,
    RefAbsenceEvidence,
    RefEnumerationLink,
    RefEnumerationObservation,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
)


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("exact typed ref wire fields required")


_ref_input_observer = ContextVar("ref_codec_input_observer", default=None)


@contextmanager
def account_ref_input(observer):
    """Attach a caller's cumulative input meter without importing its feature.

    The caller owns reservations, ceilings and error classification. Actual Core
    work is independently charged through account_verification in every scope.
    """
    token = _ref_input_observer.set(observer)
    try:
        yield
    finally:
        _ref_input_observer.reset(token)


def _input_work(amount):
    observer = _ref_input_observer.get()
    if observer is not None:
        observer(amount)
    _performed("input_bytes", amount)


def _hex(value):
    if type(value) is not str:
        raise ValueError("lowercase hex bytes required")
    _input_work(len(value))
    result = bytes.fromhex(value)
    _input_work(len(value))
    if result.hex() != value:
        raise ValueError("lowercase contiguous hex bytes required")
    return result


def _oid(value):
    if value is None:
        return None
    if type(value) is not list or len(value) != 2:
        raise ValueError("typed OID pair required")
    return OID(*value)


def _provenance(value):
    if type(value) is not str:
        raise ValueError("canonical provenance required")
    _input_work(len(value))
    parsed = json.loads(value)
    if type(parsed) is not list:
        raise ValueError("canonical provenance required")
    result = Provenance(*parsed)
    _input_work(len(value))
    if result.encoded != value:
        raise ValueError("canonical provenance required")
    return result


def observation_to_wire(value: RefObservation) -> dict:
    return {
        "observation_origin_uuidv4": value.ref_observation_key.observation_origin_uuidv4,
        "ref_observation_uuidv7": value.ref_observation_key.ref_observation_uuidv7,
        "repository_uuidv4": value.repository_uuidv4,
        "ref_name_hex": value.ref_name_bytes.hex(),
        "source_attribution": value.source_attribution,
        "visibility_scope": value.visibility_scope,
        "observed_at_us": value.observed_at_us,
    }


def observation_from_wire(row: dict) -> RefObservation:
    _exact(
        row,
        (
            "observation_origin_uuidv4",
            "ref_observation_uuidv7",
            "repository_uuidv4",
            "ref_name_hex",
            "source_attribution",
            "visibility_scope",
            "observed_at_us",
        ),
    )
    return RefObservation(
        RefObservationKey(
            row["observation_origin_uuidv4"], row["ref_observation_uuidv7"]
        ),
        row["repository_uuidv4"],
        _hex(row["ref_name_hex"]),
        row["source_attribution"],
        row["visibility_scope"],
        row["observed_at_us"],
    )


def claim_to_wire(value: RefObservationClaim) -> dict:
    def pair(object_oid):
        return None if object_oid is None else list(object_oid.key)

    return {
        "observation_origin_uuidv4": value.ref_observation_key.observation_origin_uuidv4,
        "ref_observation_uuidv7": value.ref_observation_key.ref_observation_uuidv7,
        "provenance_json": value.provenance.encoded,
        "presence_state": value.presence_state,
        "ref_form": value.ref_form,
        "direct_target_object_oid": pair(value.direct_target_object_oid),
        "symbolic_target_hex": None
        if value.symbolic_target_ref_name is None
        else value.symbolic_target_ref_name.hex(),
        "resolved_target_object_oid": pair(value.resolved_target_object_oid),
        "peeled_target_object_oid": pair(value.peeled_target_object_oid),
        "root_object_oid": pair(value.root_object_oid),
        "absence_evidence_json": None
        if value.absence_evidence is None
        else value.absence_evidence.encoded,
    }


def claim_from_wire(row: dict) -> RefObservationClaim:
    _exact(
        row,
        (
            "observation_origin_uuidv4",
            "ref_observation_uuidv7",
            "provenance_json",
            "presence_state",
            "ref_form",
            "direct_target_object_oid",
            "symbolic_target_hex",
            "resolved_target_object_oid",
            "peeled_target_object_oid",
            "root_object_oid",
            "absence_evidence_json",
        ),
    )
    absence = row["absence_evidence_json"]
    if absence is not None:
        if type(absence) is not str:
            raise ValueError("canonical absence evidence required")
        _input_work(3 * len(absence))
        absence = RefAbsenceEvidence.decode(absence)
    return RefObservationClaim(
        RefObservationKey(
            row["observation_origin_uuidv4"], row["ref_observation_uuidv7"]
        ),
        _provenance(row["provenance_json"]),
        row["presence_state"],
        row["ref_form"],
        _oid(row["direct_target_object_oid"]),
        None
        if row["symbolic_target_hex"] is None
        else _hex(row["symbolic_target_hex"]),
        _oid(row["resolved_target_object_oid"]),
        _oid(row["peeled_target_object_oid"]),
        _oid(row["root_object_oid"]),
        absence,
    )


def enumeration_to_wire(value: RefEnumerationObservation) -> dict:
    return {
        "observation_origin_uuidv4": value.observation_origin_uuidv4,
        "enumeration_uuidv7": value.enumeration_uuidv7,
        "repository_uuidv4": value.repository_uuidv4,
        "source_attribution": value.source_attribution,
        "visibility_scope": value.visibility_scope,
        "enumeration_scope_json": value.scope_json,
        "enumeration_state": value.enumeration_state,
        "completion_coordinate": value.completion_coordinate,
        "observed_at_us": value.observed_at_us,
        "byte_limit": value.byte_limit,
        "ref_limit": value.ref_limit,
        "link_count": value.link_count,
    }


def enumeration_from_wire(row: dict) -> RefEnumerationObservation:
    _exact(
        row,
        (
            "observation_origin_uuidv4",
            "enumeration_uuidv7",
            "repository_uuidv4",
            "source_attribution",
            "visibility_scope",
            "enumeration_scope_json",
            "enumeration_state",
            "completion_coordinate",
            "observed_at_us",
            "byte_limit",
            "ref_limit",
            "link_count",
        ),
    )
    text = row["enumeration_scope_json"]
    if type(text) is not str:
        raise ValueError("canonical enumeration scope required")
    _input_work(len(text))
    scope = json.loads(text)
    if (
        type(scope) is not list
        or len(scope) != 2
        or any(type(part) is not list for part in scope)
    ):
        raise ValueError("enumeration scope requires two arrays")
    result = RefEnumerationObservation(
        row["observation_origin_uuidv4"],
        row["enumeration_uuidv7"],
        row["repository_uuidv4"],
        row["source_attribution"],
        row["visibility_scope"],
        tuple(_hex(v) for v in scope[0]),
        tuple(_hex(v) for v in scope[1]),
        row["enumeration_state"],
        row["completion_coordinate"],
        row["observed_at_us"],
        row["byte_limit"],
        row["ref_limit"],
        row["link_count"],
    )
    _input_work(len(text))
    if result.scope_json != text:
        raise ValueError("canonical enumeration scope required")
    return result


def link_to_wire(value: RefEnumerationLink) -> dict:
    return {
        "enumeration_origin_uuidv4": value.event.observation_origin_uuidv4,
        "enumeration_uuidv7": value.event.enumeration_uuidv7,
        "observation_origin_uuidv4": value.observation.ref_observation_key.observation_origin_uuidv4,
        "ref_observation_uuidv7": value.observation.ref_observation_key.ref_observation_uuidv7,
        "claim_provenance_json": value.claim.provenance.encoded,
        "derivation": value.derivation,
        "position": value.position,
    }


def link_from_wire(row: dict, event, observation, claim) -> RefEnumerationLink:
    _exact(
        row,
        (
            "enumeration_origin_uuidv4",
            "enumeration_uuidv7",
            "observation_origin_uuidv4",
            "ref_observation_uuidv7",
            "claim_provenance_json",
            "derivation",
            "position",
        ),
    )
    if (
        (row["enumeration_origin_uuidv4"], row["enumeration_uuidv7"]) != event.identity
        or (row["observation_origin_uuidv4"], row["ref_observation_uuidv7"])
        != observation.ref_observation_key.key
        or row["claim_provenance_json"] != claim.provenance.encoded
    ):
        raise ValueError("enumeration link dependencies differ")
    return RefEnumerationLink(
        event, observation, claim, row["derivation"], row["position"]
    )


def _claim_ref(claim):
    return {
        "observation_origin_uuidv4": claim.ref_observation_key.observation_origin_uuidv4,
        "ref_observation_uuidv7": claim.ref_observation_key.ref_observation_uuidv7,
        "ref_claim_provenance_json": claim.provenance.encoded,
    }


def _require_claim_ref(row, claim):
    if any(row[key] != value for key, value in _claim_ref(claim).items()):
        raise ValueError("mapping belongs to another original result claim")


def mapping_to_wire(mapping: NotesMapping) -> dict:
    return {
        "object_format": mapping.root_object_oid.object_format,
        "root_object_oid": mapping.root_object_oid.object_oid,
        "interpretation_kind": mapping.interpretation_kind,
        "interpretation_version": mapping.interpretation_version,
        "interpretation_scope": mapping.interpretation_scope,
        "annotated_object_oid": mapping.annotated_object_oid.object_oid,
        "note_object_oid": mapping.note_object_oid.object_oid,
        "mapping_path_json": encode(mapping.mapping_path),
    }


def mapping_from_wire(row: dict) -> NotesMapping:
    path = row["mapping_path_json"]
    if type(path) is not str:
        raise ValueError("canonical mapping path required")
    _input_work(len(path))
    decoded = json.loads(path)
    _input_work(len(path))
    if encode(decoded) != path:
        raise ValueError("canonical mapping path required")
    fmt = row["object_format"]
    return NotesMapping(
        OID(fmt, row["root_object_oid"]),
        row["interpretation_kind"],
        row["interpretation_version"],
        row["interpretation_scope"],
        OID(fmt, row["annotated_object_oid"]),
        OID(fmt, row["note_object_oid"]),
        decoded,
    )


def mapping_claim_to_wire(claim: NotesMappingClaim) -> dict:
    return {
        **_claim_ref(claim.ref_claim),
        **mapping_to_wire(claim.mapping),
        "provenance_json": claim.provenance.encoded,
    }


def mapping_claim_from_wire(row: dict, claim: RefObservationClaim) -> NotesMappingClaim:
    _require_claim_ref(row, claim)
    return NotesMappingClaim(
        claim, mapping_from_wire(row), _provenance(row["provenance_json"])
    )


def mapping_group_to_wire(
    group: NotesMappingGroup, *, membership_json=None, provenance_json=None
) -> dict:
    return {
        **_claim_ref(group.ref_claim),
        "object_format": group.ref_claim.root_object_oid.object_format,
        "root_object_oid": group.ref_claim.root_object_oid.object_oid,
        "interpretation_kind": group.interpretation_kind,
        "interpretation_version": group.interpretation_version,
        "interpretation_scope": group.interpretation_scope,
        "group_scope": group.group_scope,
        "status": group.status,
        "membership_json": encode(group.members)
        if membership_json is None
        else membership_json,
        "provenance_json": group.provenance.encoded
        if provenance_json is None
        else provenance_json,
    }


def mapping_group_from_wire(row: dict, claim: RefObservationClaim) -> NotesMappingGroup:
    _require_claim_ref(row, claim)
    if claim.root_object_oid is None or claim.root_object_oid.key != (
        row["object_format"],
        row["root_object_oid"],
    ):
        raise ValueError("mapping group belongs to another result root")
    raw = row["membership_json"]
    if type(raw) is not str:
        raise ValueError("canonical whole mapping group required")
    _input_work(len(raw))
    members = json.loads(raw)
    if type(members) is not list or any(type(member) is not list for member in members):
        raise ValueError("whole mapping group required")
    _performed("metadata_units", len(members))
    _input_work(len(raw))
    result = NotesMappingGroup(
        claim,
        row["interpretation_kind"],
        row["interpretation_version"],
        row["interpretation_scope"],
        row["group_scope"],
        row["status"],
        tuple(tuple(member) for member in members),
        _provenance(row["provenance_json"]),
    )
    _input_work(len(raw))
    if encode(result.members) != raw:
        raise ValueError("canonical whole mapping group required")
    return result


def mapping_evidence_to_wire(claim, record) -> dict:
    return {
        **_claim_ref(claim),
        **mapping_to_wire(record.mapping),
        "verification_scope": record.verification_scope,
        "evidence_provenance_json": record.provenance.encoded,
        "proof_bundle_json": record.proof_bundle,
    }


def mapping_evidence_from_wire(
    row: dict, claim: RefObservationClaim
) -> NotesMappingEvidence:
    _require_claim_ref(row, claim)
    mapping = mapping_from_wire(row)
    raw = row["proof_bundle_json"]
    if type(raw) is not str:
        raise ValueError("canonical structural proof required")
    _input_work(2 * len(raw))
    bundle = json.loads(raw)
    if type(bundle) is not list or encode(bundle) != raw:
        raise ValueError("canonical structural proof required")
    structures = []
    for entry in bundle:
        _performed("metadata_units", 1)
        if type(entry) is not list or len(entry) != 3:
            raise ValueError("typed structural proof object required")
        body = _hex(entry[2])
        _performed("verification_bytes", len(body))
        structures.append(
            NativeObject(
                OID(mapping.root_object_oid.object_format, entry[0]),
                entry[1],
                body,
                len(body),
                hashlib.sha256(body).hexdigest(),
            )
        )
    return NotesMappingEvidence(
        claim,
        mapping,
        row["verification_scope"],
        _provenance(row["evidence_provenance_json"]),
        tuple(structures),
    )


def ref_note_from_wire(
    row: dict, evidence: NotesMappingEvidence
) -> tuple[NativeObject, str]:
    body = _hex(row["body_hex"])
    native = NativeObject(
        evidence.mapping.note_object_oid,
        "blob",
        body,
        row["size"],
        row["digest_sha256"],
    )
    return native, uuid4_value(row["physical_copy_uuidv4"])
