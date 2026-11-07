"""Optional Context, paired, and Search query public types."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from repo_catalog.domain.context_query import (
    ContextResourceView as ContextResourceView,
)
from repo_catalog.domain.context_query import (
    provider_role_summary as provider_role_summary,
)
from repo_catalog.domain.context_query import (
    repository_relation_summary as repository_relation_summary,
)
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
from repo_catalog.domain.search_query import (
    SEARCH_PROJECTION_KINDS as SEARCH_PROJECTION_KINDS,
)
from repo_catalog.domain.search_query import (
    SearchHit as SearchHit,
)
from repo_catalog.domain.search_query import (
    SearchProjectionKind as SearchProjectionKind,
)
from repo_catalog.domain.search_query import (
    SearchQuery as SearchQuery,
)
from repo_catalog.domain.search_query import (
    SearchResponse as SearchResponse,
)

if TYPE_CHECKING:
    from repo_catalog.domain.p1_context import (
        ResourceKey,
    )
    from repo_catalog.domain.production_context import (
        CoreReference,
        SourceInventory,
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


def validate_cursor_key(endpoint: str, key: tuple) -> None:
    """Validate positions owned by the installed Context/Search query feature."""
    if endpoint == "context_resources":
        from repo_catalog.domain.context_query import (
            validate_cursor_key as validate_context_key,
        )

        return validate_context_key(endpoint, key)
    widths = {"paired_resources": 3, "search": 2}
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
