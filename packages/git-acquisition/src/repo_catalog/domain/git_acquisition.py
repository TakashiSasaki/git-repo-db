"""Git-only acquisition public values; no Provider or Context models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from repo_catalog.application.notes import (
    Discovery,
    RefNoteAcquisition,
    RefNotesInventory,
    RefNotesInventoryVerification,
)
from repo_catalog.domain.acquisition_errors import AcquisitionError as AcquisitionError
from repo_catalog.domain.p1_core import (
    OID,
    CoreCoverageScope,
    GitObservation,
    NativeObject,
    Provenance,
    RelationGroup,
    RepositoryClaim,
    ScalarClaim,
    uuid4_value,
)
from repo_catalog.domain.p1_coverage import CoverageClaim
from repo_catalog.domain.ref_observation import (
    NotesMappingClaim,
    NotesMappingGroup,
    RefEnumerationResult,
    RefNotesInventoryProjection,
    RefObservation,
    RefObservationClaim,
)
from repo_catalog.domain.time import validate_required_observation_us


@dataclass(frozen=True)
class RefNotesInput:
    """Original subject and reported results; carries no receiver authority."""

    observation: RefObservation
    claims: tuple[RefObservationClaim, ...]
    mapping_claims: tuple[NotesMappingClaim, ...] = ()
    mapping_groups: tuple[NotesMappingGroup, ...] = ()

    def __post_init__(self) -> None:
        from repo_catalog.domain.p1_core import CoreFailure

        if type(self.observation) is not RefObservation:
            raise CoreFailure("REQUEST", "ref-notes", "typed original subject required")
        self.observation.__post_init__()
        for values, expected in (
            (self.claims, RefObservationClaim),
            (self.mapping_claims, NotesMappingClaim),
            (self.mapping_groups, NotesMappingGroup),
        ):
            if type(values) is not tuple or len(values) > 100_000:
                raise CoreFailure("REQUEST", "ref-notes", "bounded tuple required")
            for value in values:
                if type(value) is not expected:
                    raise CoreFailure("REQUEST", "ref-notes", "typed report required")
        if any(
            claim.ref_observation_key != self.observation.ref_observation_key
            for claim in self.claims
        ):
            raise CoreFailure("REQUEST", "ref-notes", "claim subject mismatch")
        claims = set(self.claims)
        if any(
            item.ref_claim not in claims
            for item in (*self.mapping_claims, *self.mapping_groups)
        ):
            raise CoreFailure("REQUEST", "ref-notes", "exact result Claim required")


@dataclass(frozen=True)
class NotesAcquisitionSpec:
    """Options for delegating Git Notes operations to P4 NotesAcquisition."""

    discover_notes: bool = False
    nominated_refs: tuple[str, ...] = ()
    discovery_observation_uuidv4: str | None = None
    acquire_inventories: bool = False
    target_object_oids: tuple[OID, ...] = ()
    retain_note_bodies: bool = True
    ref_inputs: tuple[RefNotesInput, ...] = ()


@dataclass(frozen=True)
class GitMetadataInput:
    """Metadata-first Git input unit supporting claims/relations with or without raw bytes."""

    repository_uuidv4: str
    capture_origin_uuidv4: str
    capture_uuidv4: str
    source_attribution: str
    observed_at_us: int | None
    object_format: Literal["sha1", "sha256"] = "sha1"
    repository_claims: tuple[RepositoryClaim, ...] = ()
    observations: tuple[GitObservation, ...] = ()
    nominal_objects: tuple[OID, ...] = ()
    scalar_claims: tuple[ScalarClaim, ...] = ()
    relation_groups: tuple[RelationGroup, ...] = ()
    native_objects: tuple[NativeObject, ...] = ()
    physical_copy_uuidv4s: dict[OID, str] = field(default_factory=dict)
    coverage_scopes: tuple[CoreCoverageScope, ...] = ()
    coverage_claims: tuple[CoverageClaim, ...] = ()
    coverage_proofs: tuple[tuple[CoverageClaim, tuple[OID, ...], Provenance], ...] = ()
    notes: NotesAcquisitionSpec | None = None

    def __post_init__(self) -> None:
        for uid in (
            self.repository_uuidv4,
            self.capture_origin_uuidv4,
            self.capture_uuidv4,
        ):
            uuid4_value(uid)
        validate_required_observation_us(self.observed_at_us)
        if not self.source_attribution:
            raise AcquisitionError(
                "INVALID_SOURCE", self.repository_uuidv4, "source attribution required"
            )
        if self.object_format not in ("sha1", "sha256"):
            raise AcquisitionError(
                "NATIVE_FORMAT", self.object_format, "unsupported object format"
            )


@dataclass(frozen=True)
class GitNativeAcquisitionRequest:
    """Selective metadata-first acquisition request against a local GitNativeSource."""

    repository_uuidv4: str
    capture_origin_uuidv4: str
    capture_uuidv4: str
    source_attribution: str
    observed_at_us: int | None
    select_object_oids: tuple[OID, ...] = ()
    retain_bytes: bool = True
    retain_object_oids: frozenset[OID] | None = None
    include_refs: bool = True
    ref_prefixes: tuple[str, ...] = ()
    nominated_ref_names: tuple[bytes, ...] = ()
    traverse_structural_targets: bool = True
    nominal_missing_object_oids: tuple[OID, ...] = ()
    repository_claims: tuple[RepositoryClaim, ...] = ()
    extra_scalar_claims: tuple[ScalarClaim, ...] = ()
    extra_relation_groups: tuple[RelationGroup, ...] = ()
    physical_copy_uuidv4s: dict[OID, str] = field(default_factory=dict)
    notes: NotesAcquisitionSpec | None = None

    def __post_init__(self) -> None:
        for uid in (
            self.repository_uuidv4,
            self.capture_origin_uuidv4,
            self.capture_uuidv4,
        ):
            uuid4_value(uid)
        validate_required_observation_us(self.observed_at_us)
        if not self.source_attribution:
            raise AcquisitionError(
                "INVALID_SOURCE", self.repository_uuidv4, "source attribution required"
            )


@dataclass(frozen=True)
class GitAcquisitionReport:
    """Structured outcome of a Git metadata and Notes acquisition unit."""

    repository_uuidv4: str
    capture_origin_uuidv4: str
    capture_uuidv4: str
    object_format: Literal["sha1", "sha256"]
    status: Literal["complete", "partial", "unknown", "known_empty"]
    admitted_objects: tuple[OID, ...]
    retained_objects: tuple[OID, ...]
    metadata_only_objects: tuple[OID, ...]
    nominal_missing_objects: tuple[OID, ...]
    ref_observations: tuple[GitObservation, ...]
    ref_enumerations: tuple[RefEnumerationResult, ...] = ()
    notes_discoveries: tuple[Discovery, ...] = ()
    ref_note_acquisitions: tuple[RefNoteAcquisition, ...] = ()
    ref_notes_inventories: tuple[RefNotesInventory, ...] = ()
    coverage_claims: tuple[CoverageClaim, ...] = ()
    failure_code: str | None = None
    failure_detail: str = ""
    ref_inventory_verifications: tuple[RefNotesInventoryVerification, ...] = ()
    ref_inventory_projections: tuple[RefNotesInventoryProjection | None, ...] = ()
    deferred_ref_claims: tuple[RefObservationClaim, ...] = ()
