"""P5 domain models for metadata-first Git acquisition, Provider intake, and paired admission.

Enforces the architectural distinctions between:
- Domain identity vs. transport/request occurrence identity
- Original source reports vs. receiver-checked facts
- Metadata completeness vs. byte availability
- Context availability vs. Git Core availability
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from repo_catalog.domain.acquisition_errors import AcquisitionError as AcquisitionError
from repo_catalog.domain.context_registration import registration_json
from repo_catalog.domain.git_acquisition import (
    GitAcquisitionReport as GitAcquisitionReport,
)
from repo_catalog.domain.git_acquisition import (
    GitMetadataInput as GitMetadataInput,
)
from repo_catalog.domain.git_acquisition import (
    GitNativeAcquisitionRequest as GitNativeAcquisitionRequest,
)
from repo_catalog.domain.git_acquisition import (
    NotesAcquisitionSpec as NotesAcquisitionSpec,
)
from repo_catalog.domain.git_acquisition import (
    RefNotesInput as RefNotesInput,
)
from repo_catalog.domain.p1_context import (
    CoverageClaim as ContextCoverageClaim,
)
from repo_catalog.domain.p1_context import (
    FieldClock,
    MappingDisposition,
    ResourceKey,
    ResourceRepositoryRelation,
    canonical,
)
from repo_catalog.domain.p1_coordination import PairAdmission
from repo_catalog.domain.p1_core import (
    uuid4_value,
)
from repo_catalog.domain.production_context import (
    CollectionObservation,
    CoreReference,
    ResourceObservation,
    ResourceRelation,
    SourceInventory,
    json_value,
)
from repo_catalog.domain.time import (
    validate_observation_us,
)


@dataclass(frozen=True)
class ProviderRegistration:
    service_instance_uuidv4: str
    provider_kind: str = "github"
    configuration_json: str = "{}"

    def __post_init__(self) -> None:
        uuid4_value(self.service_instance_uuidv4)
        if not self.provider_kind:
            raise AcquisitionError("PROVIDER_KIND", self.service_instance_uuidv4)
        registration_json("provider", self.configuration_json)


@dataclass(frozen=True)
class RepositoryRegistration:
    repository_uuidv4: str
    configuration_json: str = "{}"
    raw_metadata: dict[str, object] | None = None
    observed_at_us: int | None = None
    provenance_json: str | None = None
    clock_domain: str = "github:repository:updated_at"
    graphql: bool = False

    def __post_init__(self) -> None:
        uuid4_value(self.repository_uuidv4)
        registration_json("repository", self.configuration_json)
        if self.observed_at_us is not None:
            validate_observation_us(self.observed_at_us)
        if self.provenance_json is not None:
            json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class SourceRegistration:
    source_registration_uuidv4: str
    service_instance_uuidv4: str
    configuration_json: str = "{}"
    associated_repositories: tuple[str, ...] = ()
    association_attributes_json: str = "{}"

    def __post_init__(self) -> None:
        uuid4_value(self.source_registration_uuidv4)
        uuid4_value(self.service_instance_uuidv4)
        registration_json("source", self.configuration_json)
        registration_json("membership", self.association_attributes_json)
        for repo in self.associated_repositories:
            uuid4_value(repo)


@dataclass(frozen=True)
class ProviderIssueIntake:
    payload: dict[str, object]
    observed_at_us: int | None
    provenance_json: str
    graphql: bool = False

    def __post_init__(self) -> None:
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class ProviderPullRequestIntake:
    payload: dict[str, object]
    observed_at_us: int | None
    provenance_json: str
    graphql: bool = False

    def __post_init__(self) -> None:
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class ProviderReviewIntake:
    pull_request_id: str | int
    payload: dict[str, object]
    observed_at_us: int | None
    provenance_json: str
    graphql: bool = False

    def __post_init__(self) -> None:
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class ProviderReviewThreadIntake:
    pull_request_id: str | int
    payload: dict[str, object]
    observed_at_us: int | None
    provenance_json: str

    def __post_init__(self) -> None:
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class ProviderReviewCommentIntake:
    pull_request_id: str | int
    payload: dict[str, object]
    observed_at_us: int | None
    provenance_json: str
    graphql: bool = False
    thread_id: str | None = None

    def __post_init__(self) -> None:
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class ProviderIssueCommentIntake:
    parent_kind: Literal["issue", "pull_request"]
    parent_id: str | int
    payload: dict[str, object]
    observed_at_us: int | None
    provenance_json: str
    graphql: bool = False

    def __post_init__(self) -> None:
        if self.parent_kind not in ("issue", "pull_request"):
            raise AcquisitionError("PARENT_KIND", self.parent_kind)
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class ProviderTimelineIntake:
    parent_kind: Literal["issue", "pull_request"]
    parent_id: str | int
    event_id: str | int
    payload: dict[str, object]
    observed_at_us: int | None
    provenance_json: str

    graphql: bool = False
    parent_resource: ResourceKey | None = None

    def __post_init__(self) -> None:
        if self.parent_kind not in ("issue", "pull_request"):
            raise AcquisitionError("PARENT_KIND", self.parent_kind)
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)
        if self.parent_resource is not None and (
            not isinstance(self.parent_resource, ResourceKey)
            or self.parent_resource.resource_kind != self.parent_kind
        ):
            raise AcquisitionError("PARENT_KIND", "timeline_event")


@dataclass(frozen=True)
class ProviderRepositoryIntake:
    """Provider identity/metadata observation without any implied Core binding."""

    payload: dict[str, object]
    observed_at_us: int | None
    provenance_json: str
    graphql: bool = False

    def __post_init__(self):
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class ProviderCommitContextIntake:
    pull_request_id: str | int
    payload: dict[str, object]
    observed_at_us: int | None
    provenance_json: str

    def __post_init__(self) -> None:
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class ProviderFileContextIntake:
    pull_request_id: str | int
    payload: dict[str, object]
    observed_at_us: int | None
    provenance_json: str

    def __post_init__(self) -> None:
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class DetachedResourceTransfer:
    """Rejected legacy affiliation input; actual events require ProviderTimelineIntake."""

    resource: ResourceKey
    target_repository_uuidv4: str | None
    clock: FieldClock
    provenance_json: str
    observed_at_us: int | None

    def __post_init__(self) -> None:
        if self.target_repository_uuidv4 is not None:
            uuid4_value(self.target_repository_uuidv4)
        validate_observation_us(self.observed_at_us)
        json_value(self.provenance_json, provenance=True)


@dataclass(frozen=True)
class ProviderIntakeBatch:
    """Normalized batch of Provider observations and explicit Context units."""

    service_instance_uuidv4: str
    providers: tuple[ProviderRegistration, ...] = ()
    repositories: tuple[RepositoryRegistration, ...] = ()
    provider_repositories: tuple[ProviderRepositoryIntake, ...] = ()
    sources: tuple[SourceRegistration, ...] = ()
    source_inventories: tuple[SourceInventory, ...] = ()
    source_inventory_proofs: tuple[
        tuple[ContextCoverageClaim, SourceInventory], ...
    ] = ()
    issues: tuple[ProviderIssueIntake, ...] = ()
    pull_requests: tuple[ProviderPullRequestIntake, ...] = ()
    reviews: tuple[ProviderReviewIntake, ...] = ()
    review_threads: tuple[ProviderReviewThreadIntake, ...] = ()
    review_comments: tuple[ProviderReviewCommentIntake, ...] = ()
    issue_comments: tuple[ProviderIssueCommentIntake, ...] = ()
    timeline_events: tuple[ProviderTimelineIntake, ...] = ()
    pr_commits: tuple[ProviderCommitContextIntake, ...] = ()
    pr_files: tuple[ProviderFileContextIntake, ...] = ()
    mapping_claims: tuple[ResourceRepositoryRelation, ...] = ()
    mapping_dispositions: tuple[MappingDisposition, ...] = ()
    transfers: tuple[DetachedResourceTransfer, ...] = ()
    observations: tuple[ResourceObservation, ...] = ()
    relations: tuple[ResourceRelation, ...] = ()
    collections: tuple[CollectionObservation, ...] = ()
    collection_proofs: tuple[
        tuple[ContextCoverageClaim, CollectionObservation, str], ...
    ] = ()
    coverage_claims: tuple[ContextCoverageClaim, ...] = ()
    core_references: tuple[tuple[CoreReference, FieldClock, int | None], ...] = ()

    def __post_init__(self) -> None:
        uuid4_value(self.service_instance_uuidv4)
        for claim in self.mapping_claims:
            if (
                not isinstance(claim, ResourceRepositoryRelation)
                or claim.relation_kind != "represents_repository"
            ):
                raise ValueError(
                    "mapping_claims require explicit represents_repository reports"
                )
        if any(
            not isinstance(d, MappingDisposition) for d in self.mapping_dispositions
        ):
            raise ValueError("mapping_dispositions require original typed Dispositions")


@dataclass(frozen=True)
class ProviderAcquisitionReport:
    """Outcome of admitting a ProviderIntakeBatch into Context."""

    service_instance_uuidv4: str
    admitted_resources: tuple[ResourceKey, ...]
    skipped_pull_request_issues: int
    linked_core_references: tuple[CoreReference, ...]
    pending_core_references: tuple[CoreReference, ...]
    admitted_texts: tuple[str, ...]
    admitted_collections: int
    admitted_inventories: int


@dataclass(frozen=True)
class PairedAcquisitionResult:
    """Result of coordinated Core-first + Context-second admission."""

    admission: PairAdmission
    git_report: GitAcquisitionReport | None = None
    provider_report: ProviderAcquisitionReport | None = None


@dataclass(frozen=True)
class DependencyReconciliationReport:
    """Result of promoting unresolved Context CoreReferences once Git OIDs exist in Core."""

    promoted_references: tuple[CoreReference, ...]
    remaining_unresolved: tuple[CoreReference, ...]


def make_provenance(source: str, evidence: object) -> str:
    """Build canonical Context provenance JSON."""
    if not isinstance(source, str) or not source or evidence is None:
        raise AcquisitionError(
            "PROVENANCE", source, "source and non-null evidence required"
        )
    return canonical({"source": source, "evidence": evidence})
