"""Typed Protocol ports for P6 authoritative queries, pagination, and derivative Search."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from repo_catalog.domain.p1_context import CoverageScope, ResourceKey
from repo_catalog.domain.p1_core import OID, Capture, CoreCoverageScope
from repo_catalog.domain.ports.p1_core import WorkBudget
from repo_catalog.domain.production_query import (
    ByteReadResult,
    CatalogReadMode,
    ContextResourceView,
    CoverageView,
    GitObjectView,
    GitObservationView,
    GitRepositoryView,
    NotesCaptureView,
    NotesInventoryView,
    NotesTargetView,
    PageRequest,
    PageResult,
    PairedResourceView,
    ProviderView,
    SearchQuery,
    SearchResponse,
    SnapshotFenceToken,
    SourceView,
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


class SearchIndexPort(Protocol):
    """Port for disposable derivative Search projection storage and candidate lookup."""

    def replace_projection(
        self,
        projection_kind: str,
        snapshot_token: str,
        documents: dict[str, str],
    ) -> None: ...

    def query_candidates(
        self,
        projection_kind: str,
        snapshot_token: str,
        query_text: str,
        expected_doc_count: int | None = None,
    ) -> dict[str, str] | None: ...


class ProductionQueryPort(Protocol):
    """Port for authoritative Core, Context, Paired, and Search queries."""

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
        oid: OID,
        *,
        include_bytes: bool = False,
        note_captures: Sequence[Capture] = (),
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

    def list_notes_captures(
        self,
        page: PageRequest = PageRequest(),
        *,
        notes_ref: str | None = None,
    ) -> PageResult[NotesCaptureView]: ...

    def get_notes_target(
        self,
        capture: Capture,
        target: OID,
        *,
        include_bytes: bool = False,
    ) -> NotesTargetView: ...

    def list_notes_inventories(
        self, capture: Capture
    ) -> tuple[NotesInventoryView, ...]: ...

    def read_metadata_bytes(self, oid: OID) -> ByteReadResult: ...

    def read_note_bytes(
        self, capture: Capture, target: OID, note_oid: OID
    ) -> ByteReadResult: ...

    def get_core_coverage(
        self,
        scope: CoreCoverageScope,
        *,
        work: WorkBudget | None = None,
        max_proofs: int = 1_000,
        max_bytes: int = 64 * 1024 * 1024,
        max_structures: int = 100_000,
        max_claims: int = 10_000,
    ) -> CoverageView: ...

    def list_providers(self) -> tuple[ProviderView, ...]: ...

    def list_source_views(
        self, service_instance_uuidv4: str | None = None
    ) -> tuple[SourceView, ...]: ...

    def get_context_resource(
        self,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
    ) -> ContextResourceView: ...

    def list_context_resources(
        self,
        page: PageRequest = PageRequest(),
        *,
        service_instance_uuidv4: str | None = None,
        resource_kind: str | None = None,
        repository_uuidv4: str | None = None,
        parent: ResourceKey | None = None,
    ) -> PageResult[ContextResourceView]: ...

    def read_context_text(self, text_sha256: str) -> ByteReadResult: ...

    def get_context_coverage(self, scope: CoverageScope) -> CoverageView: ...

    def get_paired_resource(
        self,
        resource_key: ResourceKey,
        *,
        include_text: bool = True,
        include_core_bytes: bool = False,
    ) -> PairedResourceView: ...

    def list_paired_resources(
        self,
        page: PageRequest = PageRequest(),
        *,
        resource_kind: str | None = None,
        repository_uuidv4: str | None = None,
    ) -> PageResult[PairedResourceView]: ...

    def rebuild_search(
        self,
        projection_kinds: Sequence[str] = ("git_metadata", "notes", "context_text"),
    ) -> dict[str, int]: ...

    def search(self, query: SearchQuery) -> SearchResponse: ...
