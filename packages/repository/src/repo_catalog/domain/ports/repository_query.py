"""Repository Query port with no optional public API or concrete Context dependency."""

from __future__ import annotations

from typing import Protocol

from repo_catalog.domain.p1_repository import OID, RepositoryCoverageScope
from repo_catalog.domain.ports.p1_repository import WorkBudget
from repo_catalog.domain.query_contracts import (
    ByteReadResult,
    CatalogReadMode,
    CoverageView,
    PageRequest,
    PageResult,
    SnapshotFenceToken,
)
from repo_catalog.domain.ref_observation import (
    NotesMapping,
    NotesMappingProjection,
    RefEnumerationResult,
    RefNotesInventoryProjection,
    RefObservationClaim,
    RefObservationKey,
    RefObservationProjection,
)
from repo_catalog.domain.repository_query import (
    GitObjectView,
    GitObservationView,
    GitRepositoryView,
)


class RepositoryQueryPort(Protocol):
    """Bounded authoritative Repository read operations."""

    def detect_mode(self) -> CatalogReadMode: ...

    def snapshot_token(self) -> SnapshotFenceToken: ...

    def get_repository_view(self) -> GitRepositoryView: ...

    def get_ref_observation(
        self,
        key: RefObservationKey,
        work: WorkBudget,
        *,
        max_claims: int = 10_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> RefObservationProjection: ...

    def list_ref_observations(
        self,
        page: PageRequest = PageRequest(),
        *,
        work: WorkBudget | None = None,
    ) -> PageResult[RefObservationProjection]: ...

    def get_ref_enumeration(
        self,
        origin_uuidv4: str,
        enumeration_uuidv7: str,
        work: WorkBudget,
        *,
        max_links: int = 200_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> RefEnumerationResult | None: ...

    def get_notes_mapping(
        self,
        claim: RefObservationClaim,
        target: OID,
        interpretation_kind: str,
        interpretation_version: str,
        interpretation_scope: str,
        work: WorkBudget,
        *,
        max_units: int = 10_000,
        max_bytes: int = 64 * 1024 * 1024,
    ) -> NotesMappingProjection: ...

    def list_ref_notes_inventories(
        self,
        claim: RefObservationClaim,
        work: WorkBudget,
        *,
        max_groups: int = 10_000,
        max_members: int = 100_000,
        max_bytes: int = 64 * 1024 * 1024,
        max_proofs: int = 1_000,
        max_structures: int = 100_000,
    ) -> RefNotesInventoryProjection: ...

    def read_ref_note_bytes(
        self,
        claim: RefObservationClaim,
        mapping: NotesMapping,
        work: WorkBudget,
        *,
        max_proof_bytes: int = 64 * 1024 * 1024,
        max_metadata_bytes: int = 64 * 1024 * 1024,
    ) -> ByteReadResult: ...

    def get_git_object(
        self,
        object_oid: OID,
        *,
        include_bytes: bool = False,
    ) -> GitObjectView: ...

    def list_git_objects(
        self,
        page: PageRequest = PageRequest(),
        *,
        object_format: str | None = None,
        native_type: str | None = None,
    ) -> PageResult[GitObjectView]: ...

    def list_git_observations(
        self,
        page: PageRequest = PageRequest(),
        *,
        observation_kind: str | None = None,
        ref_prefix: str | None = None,
    ) -> PageResult[GitObservationView]: ...

    def read_metadata_bytes(self, object_oid: OID) -> ByteReadResult: ...

    def get_repository_coverage(
        self,
        scope: RepositoryCoverageScope,
        *,
        work: WorkBudget | None = None,
        max_proofs: int = 1_000,
        max_bytes: int = 64 * 1024 * 1024,
        max_structures: int = 100_000,
        max_claims: int = 10_000,
    ) -> CoverageView: ...
