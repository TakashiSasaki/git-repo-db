"""P3 Context interfaces; every mutation participates in caller transaction.

No method commits, fetches Git closure or rewrites original source provenance.
Standalone Context is durable without Core. Dependent links use coordination.
"""

from collections.abc import Callable, Iterable
from typing import Protocol

from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageProjection,
    CoverageScope,
    FieldCandidate,
    MappingClaimKey,
    MappingDisposition,
    MappingOperationEvidence,
    QualifiedMappingEvaluation,
    RelationKind,
    ResolvedRepositoryRelation,
    ResourceKey,
    ResourceRepositoryRelation,
    TransferEventReport,
)


class ContextAdmission(Protocol):
    def text(self, text_value: str) -> str: ...
    def scope(self, scope: CoverageScope) -> None: ...
    def resource(
        self, key: ResourceKey, repository_uuidv4: str | None = None
    ) -> None: ...
    def admit_repository_relation(
        self,
        relation: ResourceRepositoryRelation,
        *,
        require_support: bool = False,
    ) -> str: ...
    def admit_transfer_event(self, report: TransferEventReport) -> str: ...
    def admit_mapping_disposition(self, disposition: MappingDisposition) -> str: ...
    def repository_relations(
        self,
        resource: ResourceKey,
        relation_kind: RelationKind | None = None,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> tuple[ResolvedRepositoryRelation, ...]: ...
    def relations_for_repository(
        self,
        repository_uuidv4: str,
        relation_kind: RelationKind | None = None,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> tuple[ResolvedRepositoryRelation, ...]: ...
    def relations_for_provider_repository(
        self,
        service_instance_uuidv4: str,
        provider_repository_id: str,
        relation_kind: RelationKind | None = None,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> tuple[ResolvedRepositoryRelation, ...]: ...
    def evaluate_provider_repository(
        self,
        provider_repository: ResourceKey,
        *,
        evidence: MappingOperationEvidence | None = None,
    ) -> QualifiedMappingEvaluation: ...
    def mapping_dispositions(
        self, subject: MappingClaimKey | ResourceKey | None = None
    ) -> tuple[MappingDisposition, ...]: ...
    def transfer_event_reports(
        self,
        resource: ResourceKey | None = None,
        *,
        repository_uuidv4: str | None = None,
        selected_repositories: Iterable[str] | None = None,
    ) -> tuple[TransferEventReport, ...]: ...
    def admit_field(self, candidate: FieldCandidate) -> str: ...
    def candidates(
        self, resource: ResourceKey, field_name: str
    ) -> tuple[FieldCandidate, ...]: ...
    def admit_coverage(self, claim: CoverageClaim) -> str: ...
    def coverage(self, scope: CoverageScope) -> CoverageProjection: ...
    def link_core(
        self,
        resource: ResourceKey,
        role: str,
        object_format: str,
        full_oid: str,
        provenance_json: str,
        validate: Callable[[str, str], bool],
    ) -> None: ...
