"""Portable ref-observation and Notes interpretation values for the P1 Core.

Values record attributed reports, not issuer authentication or byte authority.
Receiver evidence is checked by the admission boundary against its exact root.
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from repo_catalog.domain.p1_core import (
    OID,
    CoreFailure,
    NativeObject,
    Provenance,
    _notes_group,
    encode,
    uuid4_value,
    valid_note_role,
)


def uuid7_value(value: str) -> str:
    try:
        parsed = UUID(value)
        if parsed.version != 7 or str(parsed) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise CoreFailure("IDENTITY", value, "canonical UUIDv7 required") from exc
    return value


def new_uuid7() -> str:
    """Issue a fresh occurrence identifier; its clock is never observation time."""
    milliseconds = time.time_ns() // 1_000_000
    if not 0 <= milliseconds < 2**48:
        raise CoreFailure("IDENTITY", "uuidv7", "system clock outside UUIDv7 range")
    random = secrets.randbits(74)
    value = (
        (milliseconds << 80)
        | (7 << 76)
        | ((random >> 62) << 64)
        | (2 << 62)
        | (random & ((1 << 62) - 1))
    )
    return str(UUID(int=value))


def _ref(value: bytes) -> bool:
    return (
        isinstance(value, bytes) and value.startswith(b"refs/") and b"\0" not in value
    )


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value)


@dataclass(frozen=True, order=True)
class RefObservationKey:
    observation_origin_uuidv4: str
    ref_observation_uuidv7: str

    def __post_init__(self) -> None:
        uuid4_value(self.observation_origin_uuidv4)
        uuid7_value(self.ref_observation_uuidv7)

    @property
    def key(self) -> tuple[str, str]:
        return self.observation_origin_uuidv4, self.ref_observation_uuidv7


@dataclass(frozen=True)
class RefObservation:
    ref_observation_key: RefObservationKey
    repository_uuidv4: str
    ref_name_bytes: bytes
    source_attribution: str
    visibility_scope: str
    observed_at_us: int | None = None

    def __post_init__(self) -> None:
        uuid4_value(self.repository_uuidv4)
        if not isinstance(self.ref_observation_key, RefObservationKey):
            raise CoreFailure(
                "IDENTITY", self.ref_observation_key, "observation key required"
            )
        if not _ref(self.ref_name_bytes):
            raise CoreFailure(
                "REF", self.ref_name_bytes, "lossless full ref name required"
            )
        if not _text(self.source_attribution) or not _text(self.visibility_scope):
            raise CoreFailure(
                "SCOPE", self.ref_observation_key, "source and visibility required"
            )
        if self.observed_at_us is not None and (
            type(self.observed_at_us) is not int or not 0 < self.observed_at_us < 2**63
        ):
            raise CoreFailure(
                "TIME",
                self.observed_at_us,
                "positive epoch microseconds or None required",
            )

    @property
    def key(self) -> tuple:
        return (
            *self.ref_observation_key.key,
            self.repository_uuidv4,
            self.ref_name_bytes,
            self.source_attribution,
            self.visibility_scope,
            self.observed_at_us,
        )


@dataclass(frozen=True)
class RefEnumerationObservation:
    """One original local enumeration, never a multi-scan operation."""

    observation_origin_uuidv4: str
    enumeration_uuidv7: str
    repository_uuidv4: str
    source_attribution: str
    visibility_scope: str
    prefixes: tuple[bytes, ...]
    nominated: tuple[bytes, ...]
    enumeration_state: Literal["complete", "partial", "unknown"]
    completion_coordinate: str | None
    observed_at_us: int | None
    byte_limit: int
    ref_limit: int
    link_count: int

    def __post_init__(self):
        uuid4_value(self.observation_origin_uuidv4)
        uuid7_value(self.enumeration_uuidv7)
        uuid4_value(self.repository_uuidv4)
        if (
            not _text(self.source_attribution)
            or not _text(self.visibility_scope)
            or type(self.prefixes) is not tuple
            or type(self.nominated) is not tuple
            or any(not _ref(value) for value in (*self.prefixes, *self.nominated))
            or tuple(sorted(set(self.prefixes))) != self.prefixes
            or tuple(sorted(set(self.nominated))) != self.nominated
            or not self.prefixes
            and not self.nominated
            or any(
                type(value) is not int or not 0 < value < 2**63
                for value in (self.byte_limit, self.ref_limit)
            )
            or len(self.prefixes) + len(self.nominated) > 2 * self.ref_limit
            or self.enumeration_state not in ("complete", "partial", "unknown")
            or self.enumeration_state == "complete"
            and not _text(self.completion_coordinate)
            or self.enumeration_state != "complete"
            and self.completion_coordinate is not None
            or self.observed_at_us is not None
            and (
                type(self.observed_at_us) is not int
                or not 0 < self.observed_at_us < 2**63
            )
            or type(self.link_count) is not int
            or not 0 <= self.link_count <= self.ref_limit + len(self.nominated)
        ):
            raise CoreFailure("ENUMERATION", self, "invalid event, scope or completion")

    @property
    def identity(self):
        return self.observation_origin_uuidv4, self.enumeration_uuidv7

    @property
    def scope_json(self):
        return encode(
            [[v.hex() for v in self.prefixes], [v.hex() for v in self.nominated]]
        )

    @property
    def key(self):
        return (
            *self.identity,
            self.repository_uuidv4,
            self.source_attribution,
            self.visibility_scope,
            self.scope_json,
            self.enumeration_state,
            self.completion_coordinate,
            self.observed_at_us,
            self.byte_limit,
            self.ref_limit,
            self.link_count,
        )

    def covers(self, name: bytes) -> bool:
        return name in self.nominated or any(
            name.startswith(prefix) for prefix in self.prefixes
        )


@dataclass(frozen=True)
class RefEnumerationLink:
    """A concrete item or nominated absence derived from exactly one scan."""

    event: RefEnumerationObservation
    observation: RefObservation
    claim: RefObservationClaim
    derivation: Literal["item", "absence"]
    position: int

    def __post_init__(self):
        e, o, c = self.event, self.observation, self.claim
        if (
            not isinstance(e, RefEnumerationObservation)
            or not isinstance(o, RefObservation)
            or not isinstance(c, RefObservationClaim)
            or o.ref_observation_key != c.ref_observation_key
            or (o.repository_uuidv4, o.source_attribution, o.visibility_scope)
            != (e.repository_uuidv4, e.source_attribution, e.visibility_scope)
            or not e.covers(o.ref_name_bytes)
            or self.derivation not in ("item", "absence")
            or type(self.position) is not int
            or not 0 <= self.position < 2**63
            or (self.derivation == "item" and c.presence_state != "present")
            or (
                self.derivation == "absence"
                and (
                    c.presence_state != "absent"
                    or e.enumeration_state != "complete"
                    or o.ref_name_bytes not in e.nominated
                    or c.absence_evidence is None
                    or c.absence_evidence.method not in ("lookup", "enumeration")
                    or c.absence_evidence.ref_name_bytes != o.ref_name_bytes
                    or c.absence_evidence.source_attribution != o.source_attribution
                    or c.absence_evidence.visibility_scope != o.visibility_scope
                    or c.absence_evidence.completion_coordinate
                    != e.completion_coordinate
                )
            )
        ):
            raise CoreFailure(
                "ENUMERATION", "link", "inconsistent event and item/absence"
            )

    @property
    def key(self):
        return (
            *self.event.identity,
            *self.observation.ref_observation_key.key,
            self.claim.provenance.encoded,
            self.derivation,
            self.position,
        )


@dataclass(frozen=True)
class RefEnumerationResult:
    event: RefEnumerationObservation
    links: tuple[RefEnumerationLink, ...]


@dataclass(frozen=True)
class RefAbsenceEvidence:
    """An attributed completed named lookup or bounded enumeration report.

    This is a source-qualified assertion, not proof of remote authenticity. A
    failed/partial enumeration cannot be encoded as a completed report here.
    """

    source_attribution: str
    visibility_scope: str
    ref_name_bytes: bytes
    method: Literal["lookup", "enumeration"]
    completion_coordinate: str
    enumeration_prefix_bytes: bytes | None = None
    enumeration_state: Literal["complete"] | None = None

    def __post_init__(self) -> None:
        if (
            not _text(self.source_attribution)
            or not _text(self.visibility_scope)
            or not _ref(self.ref_name_bytes)
            or not _text(self.completion_coordinate)
        ):
            raise CoreFailure(
                "ABSENCE", self, "named ref, source, visibility and completion required"
            )
        prefix = self.enumeration_prefix_bytes
        if self.method == "lookup":
            if prefix is not None or self.enumeration_state is not None:
                raise CoreFailure(
                    "ABSENCE", self, "lookup must not invent enumeration scope"
                )
        elif self.method == "enumeration":
            if (
                not isinstance(prefix, bytes)
                or not prefix.startswith(b"refs/")
                or b"\0" in prefix
                or not self.ref_name_bytes.startswith(prefix)
                or self.enumeration_state != "complete"
            ):
                raise CoreFailure(
                    "ABSENCE", self, "completed enumeration must cover the named ref"
                )
        else:
            raise CoreFailure(
                "ABSENCE", self, "completed lookup or enumeration required"
            )

    @property
    def encoded(self) -> str:
        return encode(
            [
                self.source_attribution,
                self.visibility_scope,
                self.ref_name_bytes.hex(),
                self.method,
                self.completion_coordinate,
                None
                if self.enumeration_prefix_bytes is None
                else self.enumeration_prefix_bytes.hex(),
                self.enumeration_state,
            ]
        )

    @classmethod
    def decode(
        cls,
        value: str,
        *,
        before_compare: Callable[[RefAbsenceEvidence], None] | None = None,
    ) -> RefAbsenceEvidence:
        try:
            data = json.loads(value)
            if not isinstance(data, list) or len(data) != 7:
                raise ValueError("invalid absence evidence")
            ref = bytes.fromhex(data[2])
            prefix = None if data[5] is None else bytes.fromhex(data[5])
            result = cls(data[0], data[1], ref, data[3], data[4], prefix, data[6])
            if before_compare is not None:
                before_compare(result)
            if result.encoded != value:
                raise ValueError("noncanonical absence evidence")
            return result
        except CoreFailure as exc:
            if exc.code in ("BUDGET", "QUERY_BUDGET"):
                raise
            raise CoreFailure("ABSENCE", value, "invalid absence evidence") from exc
        except (ValueError, TypeError, IndexError, RecursionError) as exc:
            raise CoreFailure("ABSENCE", value, "invalid absence evidence") from exc


def valid_ref_absence(value: object) -> bool:
    try:
        return isinstance(value, str) and bool(RefAbsenceEvidence.decode(value))
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class RefObservationClaim:
    ref_observation_key: RefObservationKey
    provenance: Provenance
    presence_state: Literal["present", "absent"]
    ref_form: Literal["direct", "symbolic"] | None = None
    direct_target_oid: OID | None = None
    symbolic_target_ref_name: bytes | None = None
    resolved_target_oid: OID | None = None
    peeled_target_oid: OID | None = None
    root_oid: OID | None = None
    absence_evidence: RefAbsenceEvidence | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.ref_observation_key, RefObservationKey)
            or not isinstance(self.provenance, Provenance)
            or self.provenance.qualification != "reported"
        ):
            raise CoreFailure(
                "PROVENANCE",
                self.ref_observation_key,
                "original reported attribution required",
            )
        if self.presence_state not in ("present", "absent") or self.ref_form not in (
            None,
            "direct",
            "symbolic",
        ):
            raise CoreFailure("REF", self.ref_observation_key, "invalid result state")
        oids = (
            self.direct_target_oid,
            self.resolved_target_oid,
            self.peeled_target_oid,
            self.root_oid,
        )
        if any(x is not None and not isinstance(x, OID) for x in oids):
            raise CoreFailure(
                "IDENTITY", self.ref_observation_key, "typed Git OID required"
            )
        if len({x.object_format for x in oids if x is not None}) > 1:
            raise CoreFailure(
                "IDENTITY", self.ref_observation_key, "one Git object format required"
            )
        if self.symbolic_target_ref_name is not None and not _ref(
            self.symbolic_target_ref_name
        ):
            raise CoreFailure(
                "REF", self.symbolic_target_ref_name, "lossless symbolic ref required"
            )
        if (
            self.direct_target_oid is not None
            and self.ref_form != "direct"
            or self.symbolic_target_ref_name is not None
            and self.ref_form != "symbolic"
        ):
            raise CoreFailure(
                "REF", self.ref_observation_key, "target and ref form disagree"
            )
        if self.presence_state == "absent":
            if not isinstance(self.absence_evidence, RefAbsenceEvidence) or any(
                x is not None
                for x in (*oids, self.ref_form, self.symbolic_target_ref_name)
            ):
                raise CoreFailure(
                    "ABSENCE",
                    self.ref_observation_key,
                    "confirmed absence requires evidence and no target",
                )
        elif self.absence_evidence is not None:
            raise CoreFailure(
                "REF",
                self.ref_observation_key,
                "present claim cannot carry absence evidence",
            )

    @property
    def identity(self) -> tuple[str, str, str]:
        return (*self.ref_observation_key.key, self.provenance.encoded)

    @property
    def key(self) -> tuple:
        def parts(oid: OID | None) -> tuple:
            return oid.key if oid is not None else (None, None)

        return (
            *self.identity,
            self.presence_state,
            self.ref_form,
            *parts(self.direct_target_oid),
            self.symbolic_target_ref_name,
            *parts(self.resolved_target_oid),
            *parts(self.peeled_target_oid),
            *parts(self.root_oid),
            None if self.absence_evidence is None else self.absence_evidence.encoded,
        )


@dataclass(frozen=True)
class RefObservationProjection:
    ref_observation: RefObservation
    claims: tuple[RefObservationClaim, ...]
    conflict: bool


def ref_claim_conflict(claims: tuple[RefObservationClaim, ...]) -> bool:
    """Compare only known values in like semantic fields, never arrival order."""
    if len({claim.presence_state for claim in claims}) > 1:
        return True
    for name in (
        "ref_form",
        "direct_target_oid",
        "symbolic_target_ref_name",
        "resolved_target_oid",
        "peeled_target_oid",
        "root_oid",
    ):
        known = {
            getattr(claim, name) for claim in claims if getattr(claim, name) is not None
        }
        if len(known) > 1:
            return True
    return False


@dataclass(frozen=True)
class NotesMapping:
    root_oid: OID
    interpretation_kind: str
    interpretation_version: str
    interpretation_scope: str
    annotated_object_oid: OID
    note_oid: OID
    mapping_path: str | None

    def __post_init__(self) -> None:
        if (
            not all(
                isinstance(x, OID)
                for x in (self.root_oid, self.annotated_object_oid, self.note_oid)
            )
            or len(
                {
                    self.root_oid.object_format,
                    self.annotated_object_oid.object_format,
                    self.note_oid.object_format,
                }
            )
            != 1
        ):
            raise CoreFailure(
                "NOTES_MAPPING",
                self,
                "typed same-format root, target and note required",
            )
        if (
            not all(
                _text(x)
                for x in (
                    self.interpretation_kind,
                    self.interpretation_version,
                    self.interpretation_scope,
                )
            )
            or self.mapping_path is not None
            and not _text(self.mapping_path)
        ):
            raise CoreFailure(
                "NOTES_MAPPING", self, "interpretation and actual path required"
            )

    @property
    def key(self) -> tuple[str, ...]:
        return (
            *self.root_oid.key,
            self.interpretation_kind,
            self.interpretation_version,
            self.interpretation_scope,
            self.annotated_object_oid.full_oid,
            self.note_oid.full_oid,
            encode(self.mapping_path),
        )


@dataclass(frozen=True)
class NotesMappingClaim:
    ref_claim: RefObservationClaim
    mapping: NotesMapping
    provenance: Provenance

    def __post_init__(self) -> None:
        if (
            not isinstance(self.ref_claim, RefObservationClaim)
            or not isinstance(self.mapping, NotesMapping)
            or self.ref_claim.root_oid != self.mapping.root_oid
        ):
            raise CoreFailure(
                "NOTES_MAPPING", self, "mapping requires the exact claimed typed root"
            )
        if (
            not isinstance(self.provenance, Provenance)
            or self.provenance.qualification != "reported"
        ):
            raise CoreFailure(
                "PROVENANCE", self, "mapping claim must be a reported assertion"
            )

    @property
    def key(self) -> tuple:
        return (*self.ref_claim.identity, *self.mapping.key, self.provenance.encoded)


@dataclass(frozen=True)
class NotesMappingGroup:
    ref_claim: RefObservationClaim
    interpretation_kind: str
    interpretation_version: str
    interpretation_scope: str
    group_scope: str
    status: Literal["unknown", "partial", "known_empty", "complete"]
    members: tuple[tuple[str, str, str | None], ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        if (
            not isinstance(self.ref_claim, RefObservationClaim)
            or self.ref_claim.root_oid is None
        ):
            raise CoreFailure("NOTES_GROUP", self, "claimed typed root required")
        if (
            not all(
                _text(x)
                for x in (
                    self.interpretation_kind,
                    self.interpretation_version,
                    self.interpretation_scope,
                    self.group_scope,
                )
            )
            or not isinstance(self.provenance, Provenance)
            or self.provenance.qualification != "reported"
        ):
            raise CoreFailure(
                "NOTES_GROUP", self, "scope and reported provenance required"
            )
        if (
            not isinstance(self.members, tuple)
            or not all(
                isinstance(member, tuple) and len(member) == 3
                for member in self.members
            )
            or not _notes_group(
                self.ref_claim.root_oid.object_format, self.status, encode(self.members)
            )
        ):
            raise CoreFailure("NOTES_GROUP", self, "invalid whole immutable group")

    @property
    def key(self) -> tuple:
        return (
            *self.ref_claim.identity,
            *self.ref_claim.root_oid.key,
            self.interpretation_kind,
            self.interpretation_version,
            self.interpretation_scope,
            self.group_scope,
            self.status,
            encode(self.members),
            self.provenance.encoded,
        )


@dataclass(frozen=True)
class NotesMappingEvidence:
    """A receiver-local check for one actual ref claim and one mapping."""

    ref_claim: RefObservationClaim
    mapping: NotesMapping
    verification_scope: str
    provenance: Provenance
    structures: tuple[NativeObject, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.ref_claim, RefObservationClaim)
            or not isinstance(self.mapping, NotesMapping)
            or self.ref_claim.root_oid != self.mapping.root_oid
            or self.mapping.mapping_path is None
        ):
            raise CoreFailure(
                "NOTES_ROLE", self, "exact claimed root and mapping path required"
            )
        if (
            self.mapping.interpretation_kind != "git-notes"
            or self.mapping.interpretation_version != "1"
            or self.verification_scope != "single-path"
            or not isinstance(self.provenance, Provenance)
            or self.provenance.qualification != "receiver_intrinsic"
            or self.provenance.decoder != "native-notes"
            or self.provenance.decoder_version != "1"
        ):
            raise CoreFailure(
                "NOTES_ROLE",
                self,
                "supported receiver decoder and single-path scope required",
            )
        if (
            not isinstance(self.structures, tuple)
            or not self.structures
            or not all(isinstance(x, NativeObject) for x in self.structures)
        ):
            raise CoreFailure("NOTES_ROLE", self, "native structural evidence required")

    @property
    def decoder_name(self) -> str:
        return self.provenance.decoder

    @property
    def decoder_version(self) -> str:
        return self.provenance.decoder_version

    @property
    def bundle(self) -> str:
        return encode(
            [[x.oid.full_oid, x.native_type, x.body.hex()] for x in self.structures]
        )

    def validate(self) -> None:
        for structure in self.structures:
            structure.validate()
            if structure.oid.object_format != self.mapping.root_oid.object_format:
                raise CoreFailure(
                    "NOTES_ROLE", self, "structural object format mismatch"
                )
        if not valid_note_role(
            *self.mapping.root_oid.key,
            self.mapping.annotated_object_oid.full_oid,
            self.mapping.note_oid.full_oid,
            self.mapping.mapping_path,
            self.bundle,
        ):
            raise CoreFailure(
                "NOTES_ROLE", self, "receiver-proven relevant notes mapping required"
            )

    @property
    def key(self) -> tuple:
        return (
            *self.ref_claim.identity,
            *self.mapping.key,
            self.verification_scope,
            self.provenance.encoded,
            self.bundle,
        )


# A locally checked mapping evidence unit is also the role evidence required by
# the body gate; this is a semantic alias, not an extra storage-only identifier.
NotesRoleEvidence = NotesMappingEvidence


@dataclass(frozen=True)
class NotesMappingEvidenceRecord:
    """A persisted receiver evidence coordinate, including its exact proof."""

    mapping: NotesMapping
    verification_scope: str
    provenance: Provenance
    proof_bundle: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.mapping, NotesMapping)
            or self.mapping.mapping_path is None
            or self.mapping.interpretation_kind != "git-notes"
            or self.mapping.interpretation_version != "1"
            or self.verification_scope != "single-path"
            or not isinstance(self.provenance, Provenance)
            or self.provenance.qualification != "receiver_intrinsic"
            or self.provenance.decoder != "native-notes"
            or self.provenance.decoder_version != "1"
            or not isinstance(self.proof_bundle, str)
            or not self.proof_bundle
        ):
            raise CoreFailure("NOTES_ROLE", self, "stored receiver evidence is invalid")

    @property
    def decoder_name(self) -> str:
        return self.provenance.decoder

    @property
    def decoder_version(self) -> str:
        return self.provenance.decoder_version


@dataclass(frozen=True)
class NotesMappingProjection:
    ref_claim: RefObservationClaim
    annotated_object_oid: OID
    claims: tuple[NotesMappingClaim, ...]
    groups: tuple[NotesMappingGroup, ...]
    evidence: tuple[NotesMappingEvidenceRecord, ...]
    canonical_note_oid: OID | None
    reported_conflict: bool
