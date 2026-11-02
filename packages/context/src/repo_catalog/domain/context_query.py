"""Context query public types and Context-owned cursor positions."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

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
        ResourceRelation,
    )
    from repo_catalog.domain.resource_identification import ResourceIdentification


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


def validate_cursor_key(endpoint: str, key: tuple) -> None:
    """Validate only Context Resource positions; paired/Search belong to composition."""
    from repo_catalog.domain.p1_context import ResourceKey

    if endpoint != "context_resources" or type(key) is not tuple or len(key) != 3:
        raise ValueError("invalid Context cursor shape")
    if any(type(value) is not str or not value or len(value) > 32768 for value in key):
        raise ValueError("invalid Context cursor coordinates")
    ResourceKey(*key)
