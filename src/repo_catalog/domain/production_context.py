"""Production Context units composed from the frozen P1 semantic values.

These are domain observations, not raw Provider responses or intake envelopes.
Their coordinates retain the original service, parent, scope and evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from repo_catalog.domain.p1_context import (
    ADMISSION_OUTCOMES as ADMISSION_OUTCOMES,
)
from repo_catalog.domain.p1_context import (
    CURRENT_CANDIDATE_RELATION_KINDS as CURRENT_CANDIDATE_RELATION_KINDS,
)
from repo_catalog.domain.p1_context import (
    DISPOSITION_KINDS as DISPOSITION_KINDS,
)
from repo_catalog.domain.p1_context import (
    MAPPING_RELATION_KINDS as MAPPING_RELATION_KINDS,
)
from repo_catalog.domain.p1_context import (
    OMITTED_ISSUER as OMITTED_ISSUER,
)
from repo_catalog.domain.p1_context import (
    RELATION_KINDS as RELATION_KINDS,
)
from repo_catalog.domain.p1_context import (
    SUPPORT_STATUSES as SUPPORT_STATUSES,
)
from repo_catalog.domain.p1_context import (
    TRANSFER_RELATION_KINDS as TRANSFER_RELATION_KINDS,
)
from repo_catalog.domain.p1_context import (
    ClaimedIssuer as ClaimedIssuer,
)
from repo_catalog.domain.p1_context import (
    ClaimedIssuerState as ClaimedIssuerState,
)
from repo_catalog.domain.p1_context import (
    DispositionKind as DispositionKind,
)
from repo_catalog.domain.p1_context import (
    EventReportKey as EventReportKey,
)
from repo_catalog.domain.p1_context import (
    FieldCandidate,
    ResourceKey,
    canonical,
)
from repo_catalog.domain.p1_context import (
    FieldClock as FieldClock,
)
from repo_catalog.domain.p1_context import (
    MappingClaimKey as MappingClaimKey,
)
from repo_catalog.domain.p1_context import (
    MappingDisposition as MappingDisposition,
)
from repo_catalog.domain.p1_context import (
    MappingDispositionKey as MappingDispositionKey,
)
from repo_catalog.domain.p1_context import (
    MappingEvaluationState as MappingEvaluationState,
)
from repo_catalog.domain.p1_context import (
    MappingOperationEvidence as MappingOperationEvidence,
)
from repo_catalog.domain.p1_context import (
    MappingProvenance as MappingProvenance,
)
from repo_catalog.domain.p1_context import (
    MappingSupport as MappingSupport,
)
from repo_catalog.domain.p1_context import (
    ProviderRepositoryRoleScope as ProviderRepositoryRoleScope,
)
from repo_catalog.domain.p1_context import (
    ProviderRepositoryScope as ProviderRepositoryScope,
)
from repo_catalog.domain.p1_context import (
    ProviderRoleState as ProviderRoleState,
)
from repo_catalog.domain.p1_context import (
    QualifiedMappingEvaluation as QualifiedMappingEvaluation,
)
from repo_catalog.domain.p1_context import (
    RelationAdmissionOutcome as RelationAdmissionOutcome,
)
from repo_catalog.domain.p1_context import (
    RelationAdmissionResult as RelationAdmissionResult,
)
from repo_catalog.domain.p1_context import (
    RelationClaimKey as RelationClaimKey,
)
from repo_catalog.domain.p1_context import (
    RelationKind as RelationKind,
)
from repo_catalog.domain.p1_context import (
    ResolvedRepositoryRelation as ResolvedRepositoryRelation,
)
from repo_catalog.domain.p1_context import (
    ResourceRepositoryRelation as ResourceRepositoryRelation,
)
from repo_catalog.domain.p1_context import (
    SupportStatus as SupportStatus,
)
from repo_catalog.domain.p1_context import (
    TransferEndpointState as TransferEndpointState,
)
from repo_catalog.domain.p1_context import (
    TransferEventReport as TransferEventReport,
)
from repo_catalog.domain.p1_context import (
    encode_mapping_provenance as encode_mapping_provenance,
)
from repo_catalog.domain.p1_context import (
    encode_supported_provenance as encode_supported_provenance,
)
from repo_catalog.domain.p1_context import (
    encode_transfer_supported_provenance as encode_transfer_supported_provenance,
)
from repo_catalog.domain.p1_context import (
    evaluate_repository_mapping as evaluate_repository_mapping,
)
from repo_catalog.domain.p1_context import (
    explicit_null_target_json as explicit_null_target_json,
)
from repo_catalog.domain.p1_context import (
    extract_mapping_support as extract_mapping_support,
)
from repo_catalog.domain.p1_context import (
    parse_mapping_provenance as parse_mapping_provenance,
)
from repo_catalog.domain.p1_context import (
    qualify_provider_role_scopes as qualify_provider_role_scopes,
)
from repo_catalog.domain.p1_context import (
    represents_target_json as represents_target_json,
)
from repo_catalog.domain.p1_context import (
    resolved_target_json as resolved_target_json,
)
from repo_catalog.domain.p1_context import (
    target_json_for_repository as target_json_for_repository,
)
from repo_catalog.domain.p1_context import (
    validate_mapping_clock as validate_mapping_clock,
)
from repo_catalog.domain.p1_context import (
    validate_mapping_provenance as validate_mapping_provenance,
)
from repo_catalog.domain.p1_context import (
    validate_mapping_target as validate_mapping_target,
)
from repo_catalog.domain.p1_context import (
    validate_relation_resource_kind as validate_relation_resource_kind,
)
from repo_catalog.domain.p1_context import (
    validate_timeline_event_coordinates as validate_timeline_event_coordinates,
)
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.resource_identification import (
    ResourceIdentification,
    require_identification,
)
from repo_catalog.domain.time import (
    validate_observation_us,
    validate_required_observation_us,
)


class ContextError(ValueError):
    """An invalid unit or unavailable dependency; scope identifies the boundary."""

    def __init__(self, code: str, scope: str, detail: str = ""):
        self.code, self.scope = code, scope
        super().__init__(f"{scope}:{code}: {detail}")


def json_value(encoded: str, *, provenance: bool = False) -> object:
    value = json.loads(encoded)
    if canonical(value) != encoded:
        raise ContextError("NONCANONICAL_JSON", "context")
    if provenance and (
        not isinstance(value, dict)
        or not isinstance(value.get("source"), str)
        or not value["source"]
        or value.get("evidence") is None
    ):
        raise ContextError("MISSING_PROVENANCE", "context")
    return value


@dataclass(frozen=True)
class ResourceObservation:
    resource: ResourceKey
    fields: tuple[FieldCandidate, ...] = ()
    identification: ResourceIdentification | None = None

    def __post_init__(self):
        require_identification(self.resource, self.identification)
        if any(field.resource != self.resource for field in self.fields):
            raise ContextError("FIELD_OWNER", "resource")


@dataclass(frozen=True)
class ResourceRelation:
    resource: ResourceKey
    relation_kind: str
    members: tuple[ResourceKey, ...]
    provenance_json: str
    scope_json: str
    observed_at_us: int | None

    def __post_init__(self):
        if not self.relation_kind:
            raise ContextError("MISSING_KIND", "relation")
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)
        json_value(self.scope_json)
        if len(set(self.members)) != len(self.members):
            raise ContextError("DUPLICATE_MEMBER", "relation")

    @property
    def members_json(self) -> str:
        return canonical([member.coordinates() for member in self.members])


@dataclass(frozen=True)
class CollectionObservation:
    resource: ResourceKey
    collection_kind: str
    provenance_json: str
    scope_json: str
    observed_at_us: int
    state: Literal["complete", "partial", "unknown"]
    members: tuple[ResourceKey, ...] = ()

    def __post_init__(self):
        validate_required_observation_us(self.observed_at_us)
        ResourceRelation(
            self.resource,
            self.collection_kind,
            self.members,
            self.provenance_json,
            self.scope_json,
            self.observed_at_us,
        )
        if self.state not in {"complete", "partial", "unknown"}:
            raise ContextError("INVALID_STATE", "collection")

    @property
    def members_json(self) -> str:
        return canonical([member.coordinates() for member in self.members])

    @property
    def terminal(self) -> tuple:
        return (
            *self.resource.coordinates(),
            self.collection_kind,
            self.provenance_json,
            self.observed_at_us,
            self.state,
            self.members_json,
        )


@dataclass(frozen=True)
class SourceInventory:
    source_registration_uuidv4: str
    scope_json: str
    observed_at_us: int
    state: Literal["complete", "partial", "unknown", "not_applicable"]
    terminal: bool
    repositories: tuple[str, ...]
    provenance_json: str

    def __post_init__(self):
        validate_required_observation_us(self.observed_at_us)
        json_value(self.scope_json)
        json_value(self.provenance_json, provenance=True)
        if self.state not in {"complete", "partial", "unknown", "not_applicable"}:
            raise ContextError("INVALID_STATE", "source_inventory")
        if type(self.terminal) is not bool:
            raise ContextError("INVALID_TERMINAL", "source_inventory")
        if len(set(self.repositories)) != len(self.repositories):
            raise ContextError("DUPLICATE_MEMBER", "source_inventory")

    @property
    def members_json(self) -> str:
        # A Source inventory is a set. Arrival order creates no new evidence.
        return canonical(sorted(self.repositories))

    @property
    def values(self) -> tuple:
        return (
            self.source_registration_uuidv4,
            self.scope_json,
            self.observed_at_us,
            self.state,
            int(self.terminal),
            self.members_json,
            self.provenance_json,
        )


@dataclass(frozen=True)
class CoreReference:
    resource: ResourceKey
    role: str
    oid: OID
    provenance_json: str

    def __post_init__(self):
        if not self.role:
            raise ContextError("MISSING_ROLE", "core_reference")
        json_value(self.provenance_json, provenance=True)


def validate_reported_core_reference(candidate: FieldCandidate) -> None:
    """Check the reported OID subtype before admission or Exchange binding."""
    if candidate.field_name.startswith("reported_core_reference:"):
        value = json.loads(candidate.value_json)
        if (
            not candidate.field_name.removeprefix("reported_core_reference:")
            or not isinstance(value, list)
            or len(value) != 2
            or any(not isinstance(item, str) for item in value)
        ):
            raise ContextError("REFERENCE_VALUE", "core_reference")
        OID(*value)


@dataclass(frozen=True)
class CoreDependency:
    reference: CoreReference
    available: bool
    required: bool = False
    candidate: FieldCandidate | None = None
    # Nominal presence never establishes intrinsic verification or graph closure.
