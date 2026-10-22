"""P3 modeled persistence extension of the exact P1 ContextAdmission contract.

Adapters bind the port to a caller transaction or authoritative read snapshot.
All identity, candidate, clock and Coverage types remain the P1 types.
"""

from collections.abc import Callable, Sequence
from typing import Protocol

from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageProjection,
    FieldClock,
    ResourceKey,
)
from repo_catalog.domain.ports.p1_context import ContextAdmission
from repo_catalog.domain.production_context import (
    CollectionObservation,
    CoreDependency,
    CoreReference,
    ResourceObservation,
    ResourceRelation,
    SourceInventory,
)


class ContextPersistence(ContextAdmission, Protocol):
    def provider(
        self, service: str, kind: str, configuration_json: str = "{}"
    ) -> None: ...
    def repository(
        self, repository_uuidv4: str, configuration_json: str = "{}"
    ) -> None: ...
    def source(
        self, source: str, service: str, configuration_json: str = "{}"
    ) -> None: ...
    def associate_source(
        self, source: str, repository: str, attributes_json: str = "{}"
    ) -> None: ...
    def source_repositories(self, source: str) -> tuple[str, ...]: ...
    def inventory(self, observation: SourceInventory) -> None: ...
    def observe(self, observation: ResourceObservation) -> tuple[str, ...]: ...
    def inherit_fields(
        self, parent: ResourceKey, child: ResourceKey, fields: Sequence[str]
    ) -> tuple[str, ...]: ...
    def relation(
        self,
        relation: ResourceRelation,
        *,
        selected_resources: frozenset[ResourceKey] | None = None,
        permitted: Callable[[ResourceKey], bool] | None = None,
    ) -> str: ...
    def relations(
        self, resource: ResourceKey, relation_kind: str
    ) -> tuple[ResourceRelation, ...]: ...
    def collection(self, observation: CollectionObservation) -> None: ...
    def prove_collection(
        self,
        claim: CoverageClaim,
        observation: CollectionObservation,
        *,
        required_scope_json: str,
    ) -> None: ...
    def collection_coverage(
        self,
        resource: ResourceKey,
        collection_kind: str,
        provenance_json: str,
        coverage_kind: str,
        *,
        required_scope_json: str,
    ) -> CoverageProjection: ...
    def prove_inventory(
        self, claim: CoverageClaim, observation: SourceInventory
    ) -> None: ...
    def read_text(self, digest: str) -> str: ...
    def admit_text(
        self,
        resource: ResourceKey,
        text_value: str | None,
        clock: FieldClock,
        provenance_json: str,
        observed_at_us: int | None,
    ) -> str: ...
    def report_core_reference(
        self,
        reference: CoreReference,
        *,
        clock: FieldClock,
        observed_at_us: int | None,
    ) -> str: ...
    def core_dependencies(
        self,
        resource: ResourceKey,
        validate: Callable[[str, str], bool] | None = None,
    ) -> tuple[CoreDependency, ...]: ...
