"""P5 domain models for metadata-first Git acquisition, Provider intake, and paired admission.

Enforces the architectural distinctions between:
- Domain identity vs. transport/request occurrence identity
- Original source reports vs. receiver-checked facts
- Metadata completeness vs. byte availability
- Context availability vs. Git Core availability
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from repo_catalog.application.notes import (
    Discovery,
    RefNoteAcquisition,
    RefNotesInventory,
    RefNotesInventoryVerification,
)
from repo_catalog.domain.context_registration import registration_json
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
from repo_catalog.domain.production_context import (
    CollectionObservation,
    CoreReference,
    ResourceObservation,
    ResourceRelation,
    SourceInventory,
    json_value,
)
from repo_catalog.domain.ref_observation import (
    NotesMappingClaim,
    NotesMappingGroup,
    RefEnumerationResult,
    RefNotesInventoryProjection,
    RefObservation,
    RefObservationClaim,
)
from repo_catalog.domain.time import (
    validate_observation_us,
    validate_required_observation_us,
)


class AcquisitionError(ValueError):
    """Typed acquisition domain or input validation error."""

    def __init__(self, code: str, scope: object, detail: str = ""):
        self.code = code
        self.scope = scope
        self.detail = detail
        super().__init__(f"{scope}:{code}: {detail}" if detail else f"{scope}:{code}")


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
    target_oids: tuple[OID, ...] = ()
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
    select_oids: tuple[OID, ...] = ()
    retain_bytes: bool = True
    retain_oids: frozenset[OID] | None = None
    include_refs: bool = True
    ref_prefixes: tuple[str, ...] = ()
    nominated_ref_names: tuple[bytes, ...] = ()
    traverse_structural_targets: bool = True
    nominal_missing_oids: tuple[OID, ...] = ()
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
