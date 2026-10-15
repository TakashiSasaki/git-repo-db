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
    def notes_projection(self, capture: Capture, target: OID) -> NotesProjection: ...
    def coverage(self, scope: CoreCoverageScope) -> CoverageProjection: ...
    def scalar(self, oid: OID, field: ScalarField) -> Projection: ...
    def relations(
        self, oid: OID, relation: str, scope: str | None = None
    ) -> Projection: ...
    def read_metadata(self, oid: OID) -> bytes: ...
    def read_note(self, capture: Capture, target: OID, note: OID) -> bytes: ...
