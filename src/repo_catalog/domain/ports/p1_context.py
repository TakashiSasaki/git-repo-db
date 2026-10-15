"""P3 Context interfaces; every mutation participates in caller transaction.

No method commits, fetches Git closure or rewrites original source provenance.
Standalone Context is durable without Core. Dependent links use coordination.
"""

from collections.abc import Callable
from typing import Protocol

from repo_catalog.domain.p1_context import (
    CoverageClaim,
    CoverageProjection,
    CoverageScope,
    FieldCandidate,
    FieldClock,
    ResourceKey,
)


class ContextAdmission(Protocol):
    def text(self, text_value: str) -> str: ...
    def scope(self, scope: CoverageScope) -> None: ...
    def resource(self, key: ResourceKey, repository_uuidv4: str | None) -> None: ...
    def admit_repository(
        self,
        resource: ResourceKey,
        repository_uuidv4: str | None,
        clock: FieldClock,
        provenance_json: str,
        observed_at_us: int,
    ) -> str: ...
    def repository_candidates(
        self, resource: ResourceKey
    ) -> tuple[FieldCandidate, ...]: ...
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
