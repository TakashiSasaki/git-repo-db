"""Optional Context, paired, and Search query public types."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal

from repo_catalog.domain.core_query import GitObjectView as GitObjectView
from repo_catalog.domain.core_query import GitObservationView as GitObservationView
from repo_catalog.domain.core_query import GitRepositoryView as GitRepositoryView
from repo_catalog.domain.core_query import RefNotesTargetView as RefNotesTargetView
from repo_catalog.domain.core_query import ref_projection_json as ref_projection_json
from repo_catalog.domain.query_contracts import ByteReadResult as ByteReadResult
from repo_catalog.domain.query_contracts import CatalogReadMode as CatalogReadMode
from repo_catalog.domain.query_contracts import CoverageView as CoverageView
from repo_catalog.domain.query_contracts import PageRequest as PageRequest
from repo_catalog.domain.query_contracts import PageResult as PageResult
from repo_catalog.domain.query_contracts import PaginationCursor as PaginationCursor
from repo_catalog.domain.query_contracts import QueryError as QueryError
from repo_catalog.domain.query_contracts import SnapshotFenceToken as SnapshotFenceToken
from repo_catalog.domain.query_contracts import canonical_json as canonical_json
from repo_catalog.domain.query_contracts import filter_digest as filter_digest

if TYPE_CHECKING:
    from repo_catalog.domain.p1_context import (
        FieldCandidate,
        QualifiedProviderRepositoryRole,
        ResolvedRepositoryRelation,
        ResourceKey,
    )
    from repo_catalog.domain.production_context import (
        CollectionObservation,
        CoreDependency,
        CoreReference,
        ResourceRelation,
        SourceInventory,
    )
    from repo_catalog.domain.resource_identification import ResourceIdentification

SearchProjectionKind = Literal["git_metadata", "notes", "context_text"]
SEARCH_PROJECTION_KINDS: tuple[SearchProjectionKind, ...] = (
    "git_metadata",
    "notes",
    "context_text",
)


@dataclass(frozen=True)
class ProviderView:
    """Authoritative Context Provider registration view."""

    service_instance_uuidv4: str
    provider_kind: str
    configuration: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "configuration": self.configuration,
            "provider_kind": self.provider_kind,
            "service_instance_uuidv4": self.service_instance_uuidv4,
        }


@dataclass(frozen=True)
class SourceView:
    """Authoritative Context Source registration, positive repositories, and inventories."""

    source_registration_uuidv4: str
    service_instance_uuidv4: str
    configuration: dict[str, object]
    repositories: tuple[str, ...]
    inventories: tuple[SourceInventory, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "configuration": self.configuration,
            "inventories": [
                {
                    "observed_at_us": inv.observed_at_us,
                    "provenance": json.loads(inv.provenance_json),
                    "repositories": list(inv.repositories),
                    "scope": json.loads(inv.scope_json),
                    "source_registration_uuidv4": inv.source_registration_uuidv4,
                    "state": inv.state,
                    "terminal": inv.terminal,
                }
                for inv in self.inventories
            ],
            "repositories": list(self.repositories),
            "service_instance_uuidv4": self.service_instance_uuidv4,
            "source_registration_uuidv4": self.source_registration_uuidv4,
        }


def provider_role_summary(role: QualifiedProviderRepositoryRole) -> dict[str, object]:
    """Keep original scope and complete Mapping keys separate from present qualification."""
    return {
        "resource": list(role.resource.coordinates()),
        "scope": role.scope.to_dict(),
        "provenance_json": role.provenance_json,
        "state": role.state,
        "mapping": asdict(role.mapping) if role.mapping is not None else None,
    }


def repository_relation_summary(
    relation: ResolvedRepositoryRelation,
) -> dict[str, object]:
    return asdict(relation)


@dataclass(frozen=True)
class ContextResourceView:
    """Authoritative Context resource view with field winners, relations, collections, and Core refs."""

    resource: ResourceKey
    repository_uuidv4: str | None
    repository_roles: tuple[QualifiedProviderRepositoryRole, ...]
    repository_relations: tuple[ResolvedRepositoryRelation, ...]
    identification: ResourceIdentification
    identifier_namespace: ResourceKey | None
    document_kind: str | None
    provider_document_id: str | None
    fields: dict[str, tuple[FieldCandidate, ...]]
    resolved_texts: dict[str, str | None]
    relations: tuple[ResourceRelation, ...]
    collections: tuple[CollectionObservation, ...]
    core_dependencies: tuple[CoreDependency, ...]

    def matches_repository(self, repository_uuidv4: str) -> bool:
        """Current candidate membership, including explicit Mapping alternatives.

        No parent inheritance, historical Core-target fallback or Transfer edge.
        Qualification remains available on each role even when a candidate matches.
        """
        return any(
            role.mapping is not None
            and repository_uuidv4 in role.mapping.active_repository_uuidv4s
            for role in self.repository_roles
        ) or any(
            rel.relation_kind == "represents_repository"
            and rel.claim_key in rel.supporting_bindings
            and rel.relation.target_repository_uuidv4 == repository_uuidv4
            for rel in self.repository_relations
        )

    @property
    def semantic_key(self) -> tuple[str, str, str]:
        return self.resource.coordinates()

    def to_dict(self) -> dict[str, object]:
        return {
            "collections": [
                {
                    "collection_kind": col.collection_kind,
                    "members": [list(m.coordinates()) for m in col.members],
                    "observed_at_us": col.observed_at_us,
                    "provenance": json.loads(col.provenance_json),
                    "scope": json.loads(col.scope_json),
                    "state": col.state,
                }
                for col in self.collections
            ],
            "core_dependencies": [
                {
                    "available": dep.available,
                    "object_oid": list(dep.reference.object_oid.key),
                    "provenance": json.loads(dep.reference.provenance_json),
                    "required": dep.required,
                    "role": dep.reference.role,
                }
                for dep in self.core_dependencies
            ],
            "document_kind": self.document_kind,
            "fields": {
                fname: [
                    {
                        "clock": {
                            "at_us": cand.clock.at_us,
                            "domain": cand.clock.domain,
                        },
                        "field_name": cand.field_name,
                        "observed_at_us": cand.observed_at_us,
                        "provenance": json.loads(cand.provenance_json),
                        "value": json.loads(cand.value_json),
                        "value_json": cand.value_json,
                    }
                    for cand in cands
                ]
                for fname, cands in sorted(self.fields.items())
            },
            "identification": {
                "identifier_namespace": list(self.identifier_namespace.coordinates())
                if self.identifier_namespace is not None
                else None,
                "document_kind": self.identification.document_kind,
                "provider_document_id": self.identification.provider_document_id,
            },
            "provider_document_id": self.provider_document_id,
            "provider_resource_id": self.resource.provider_resource_id,
            "relations": [
                {
                    "members": [list(m.coordinates()) for m in rel.members],
                    "observed_at_us": rel.observed_at_us,
                    "provenance": json.loads(rel.provenance_json),
                    "relation_kind": rel.relation_kind,
                    "scope": json.loads(rel.scope_json),
                }
                for rel in self.relations
            ],
            "repository_roles": [
                provider_role_summary(role) for role in self.repository_roles
            ],
            "repository_relations": [
                repository_relation_summary(rel) for rel in self.repository_relations
            ],
            "repository_uuidv4": self.repository_uuidv4,
            "resolved_texts": dict(sorted(self.resolved_texts.items())),
            "resource_kind": self.resource.resource_kind,
            "service_instance_uuidv4": self.resource.service_instance_uuidv4,
        }


@dataclass(frozen=True)
class PairedCoreResolution:
    """Resolution of a Context CoreReference against pinned Git Core authority."""

    reference: CoreReference
    available_in_core: bool
    core_required: bool
    object_view: GitObjectView | None = None
    ref_notes_targets: tuple[RefNotesTargetView, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "available_in_core": self.available_in_core,
            "core_required": self.core_required,
            "ref_notes_targets": [n.to_dict() for n in self.ref_notes_targets],
            "object_view": (
                self.object_view.to_dict() if self.object_view is not None else None
            ),
            "object_oid": list(self.reference.object_oid.key),
            "provenance": json.loads(self.reference.provenance_json),
            "role": self.reference.role,
        }


@dataclass(frozen=True)
class PairedResourceView:
    """Paired Context + Core view joining a ContextResourceView with pinned Core objects/notes."""

    context_resource: ContextResourceView
    core_resolutions: tuple[PairedCoreResolution, ...]
    snapshot_token: str

    @property
    def resource(self) -> ResourceKey:
        return self.context_resource.resource

    def to_dict(self) -> dict[str, object]:
        return {
            "context_resource": self.context_resource.to_dict(),
            "core_resolutions": [res.to_dict() for res in self.core_resolutions],
            "snapshot_token": self.snapshot_token,
        }


@dataclass(frozen=True)
class SearchQuery:
    """Search query parameters with projection kind filter and pagination."""

    query_text: str
    projection_kinds: tuple[str, ...] = SEARCH_PROJECTION_KINDS
    limit: int = 50
    cursor: str | None = None
    expected_token: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.query_text, str)
            or not self.query_text
            or len(self.query_text) > 4096
        ):
            raise QueryError("INVALID_QUERY", "search", "nonempty query_text required")
        try:
            self.query_text.encode("utf-8")
        except UnicodeEncodeError as error:
            raise QueryError(
                "INVALID_QUERY", "search", "valid Unicode required"
            ) from error
        if (
            not self.projection_kinds
            or len(set(self.projection_kinds)) != len(self.projection_kinds)
            or any(k not in SEARCH_PROJECTION_KINDS for k in self.projection_kinds)
        ):
            raise QueryError(
                "INVALID_PROJECTION_KIND",
                "search",
                f"projection_kinds must be subset of {SEARCH_PROJECTION_KINDS}",
            )
        PageRequest(
            limit=self.limit, cursor=self.cursor, expected_token=self.expected_token
        )


@dataclass(frozen=True)
class SearchHit:
    """Authoritative-verified search hit."""

    projection_kind: str
    document_key: tuple[Any, ...]
    matched_text: str
    authoritative_summary: dict[str, object]
    snapshot_token: str

    @property
    def semantic_key(self) -> tuple[str, str]:
        return (self.projection_kind, canonical_json(list(self.document_key)))

    def to_dict(self) -> dict[str, object]:
        return {
            "authoritative_summary": self.authoritative_summary,
            "document_key": list(self.document_key),
            "matched_text": self.matched_text,
            "projection_kind": self.projection_kind,
            "snapshot_token": self.snapshot_token,
        }


@dataclass(frozen=True)
class SearchResponse:
    """Paginated search response with per-kind backend provenance ('verified_projection_scan' or 'authority_scan')."""

    hits: tuple[SearchHit, ...]
    backend: str
    backends_by_kind: dict[str, str]
    snapshot_token: str
    next_cursor: str | None
    has_more: bool
    total_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "backends_by_kind": dict(sorted(self.backends_by_kind.items())),
            "has_more": self.has_more,
            "hits": [hit.to_dict() for hit in self.hits],
            "next_cursor": self.next_cursor,
            "snapshot_token": self.snapshot_token,
            "total_count": self.total_count,
        }


def validate_cursor_key(endpoint: str, key: tuple) -> None:
    """Validate positions owned by the installed Context/Search query feature."""
    widths = {"context_resources": 3, "paired_resources": 3, "search": 2}
    if (
        endpoint not in widths
        or not isinstance(key, tuple)
        or len(key) != widths[endpoint]
        or any(type(v) is not str or not v or len(v) > 32768 for v in key)
    ):
        raise ValueError("invalid key shape or type")
    if endpoint in ("context_resources", "paired_resources"):
        from repo_catalog.domain.p1_context import ResourceKey

        ResourceKey(*key)
    elif endpoint == "search":
        if key[0] not in SEARCH_PROJECTION_KINDS:
            raise ValueError("invalid projection")
        document = json.loads(key[1])
        if (
            not isinstance(document, list)
            or not document
            or any(type(v) is not str for v in document)
            or canonical_json(document) != key[1]
        ):
            raise ValueError("invalid document key")
