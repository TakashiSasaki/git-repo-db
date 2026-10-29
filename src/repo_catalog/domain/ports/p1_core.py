"""Stable P2/P4 contracts. Each admission is one local Core transaction.

A relation group is one whole immutable value. The caller coordinates paired
Core/Context admissions outside this port. Original reports never use local
verification provenance, and local checks never rewrite original attribution.
"""

from __future__ import annotations

from typing import Protocol

from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreCoverageScope,
    GitObservation,
    NativeObject,
    NotesClaim,
    NotesGroup,
    NotesProjection,
    NotesProof,
    Projection,
    RelationGroup,
    RepositoryClaim,
    ScalarClaim,
    ScalarField,
)
from repo_catalog.domain.p1_coverage import CoverageClaim, CoverageProjection
from repo_catalog.domain.ref_observation import (
    NotesMapping,
    NotesMappingClaim,
    NotesMappingEvidence,
    NotesMappingGroup,
    NotesMappingProjection,
    RefObservation,
    RefObservationClaim,
    RefObservationKey,
    RefObservationProjection,
)


class NoteLimits(Protocol):
    note_bytes: int


class WorkBudget(Protocol):
    """Operational durable reservations survive failed/rolled-back processing."""

    limits: NoteLimits

    def require(self, unit: str, amount: int = 1) -> None: ...
    def charge(self, unit: str, amount: int) -> None: ...


class CoreAdmission(Protocol):
    def admit_repository(self, repository_uuidv4: str) -> None: ...
    def admit_repository_claim(self, claim: RepositoryClaim) -> None: ...
    def admit_observation(self, observation: GitObservation) -> None: ...
    def admit_ref_observation(self, observation: RefObservation) -> None: ...
    def admit_ref_observation_claim(self, claim: RefObservationClaim) -> None: ...
    def admit_ref_enumeration(self, event, links: tuple, work: WorkBudget) -> None: ...
    def admit_notes_mapping_claim(self, claim: NotesMappingClaim) -> None: ...
    def admit_notes_mapping_group(
        self, group: NotesMappingGroup, work: WorkBudget | None = None
    ) -> None: ...
    def admit_notes_mapping_evidence(
        self,
        evidence: NotesMappingEvidence,
        work: WorkBudget,
        *,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        max_proof_bytes: int = 64 * 1024 * 1024,
    ) -> None: ...
    def admit_ref_note(
        self,
        evidence: NotesMappingEvidence,
        native: NativeObject,
        physical_copy_uuidv4: str,
        work: WorkBudget,
        *,
        max_proof_bytes: int = 64 * 1024 * 1024,
        max_metadata_bytes: int = 64 * 1024 * 1024,
        max_existing_copies: int = 1_000,
    ) -> None: ...
    def admit_coverage_scope(self, scope: CoreCoverageScope) -> None: ...
    def admit_coverage(self, claim: CoverageClaim) -> str: ...
    def admit_coverage_proof(
        self, claim: CoverageClaim, members: tuple[OID, ...], provenance
    ) -> None: ...
    def admit_object(self, oid: OID) -> None: ...
    def admit_claim(self, claim: ScalarClaim) -> None: ...
    def admit_group(self, group: RelationGroup) -> None: ...
    def admit_capture(self, capture: Capture) -> None: ...
    def admit_notes_claim(self, claim: NotesClaim) -> None: ...
    def admit_notes_group(self, group: NotesGroup) -> None: ...
    def admit_notes_role(self, proof: NotesProof, work: WorkBudget) -> None: ...
    def admit_metadata(
        self, native: NativeObject, physical_copy_uuidv4: str, work: WorkBudget
    ) -> None: ...
    def admit_note(
        self,
        proof: NotesProof,
        native: NativeObject,
        physical_copy_uuidv4: str,
        work: WorkBudget,
    ) -> None: ...


class CoreRead(Protocol):
    def ref_enumeration(
        self,
        origin,
        event_id,
        work: WorkBudget,
        *,
        max_links: int = 10_000,
        max_bytes: int = 64 * 1024 * 1024,
    ): ...
    def ref_observation(
        self,
        key: RefObservationKey,
        work: WorkBudget,
        *,
        max_claims: int = 10_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> RefObservationProjection: ...
    def notes_mapping_projection(
        self,
        ref_claim: RefObservationClaim,
        annotated_object_oid: OID,
        interpretation_kind: str,
        interpretation_version: str,
        interpretation_scope: str,
        work: WorkBudget,
        *,
        max_units: int = 10_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> NotesMappingProjection: ...
    def read_ref_note(
        self,
        claim: RefObservationClaim,
        mapping: NotesMapping,
        work: WorkBudget,
        *,
        max_proof_bytes: int = 64 * 1024 * 1024,
        max_metadata_bytes: int = 64 * 1024 * 1024,
    ) -> bytes: ...
    def notes_projection(self, capture: Capture, target: OID) -> NotesProjection: ...
    def coverage(self, scope: CoreCoverageScope) -> CoverageProjection: ...
    def scalar(self, oid: OID, field: ScalarField) -> Projection: ...
    def relations(
        self, oid: OID, relation: str, scope: str | None = None
    ) -> Projection: ...
    def read_metadata(self, oid: OID) -> bytes: ...
    def read_note(self, capture: Capture, target: OID, note: OID) -> bytes: ...
