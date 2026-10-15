"""Stable P1 Context values; independent of acquisition and SQLite adapters.

Canonical whole-value JSON is a reversible representation of genuine semantic
coordinates, never a locally assigned alias. Missing fields have no candidate;
JSON null is an explicitly observed value. Source clocks never use receipt time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from repo_catalog.domain.p1_coverage import (
    CoverageClaim as CoverageClaim,
)
from repo_catalog.domain.p1_coverage import (
    CoverageProjection as CoverageProjection,
)
from repo_catalog.domain.p1_coverage import (
    CoverageState as CoverageState,
)
from repo_catalog.domain.time import validate_epoch_us

OwnerKind = Literal[
    "repository", "source", "resource", "collection", "field", "source_inventory"
]


def canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


@dataclass(frozen=True)
class ResourceKey:
    service_instance_uuidv4: str
    resource_kind: str
    provider_resource_id: str

    @classmethod
    def document(
        cls,
        parent: ResourceKey,
        resource_kind: str,
        document_kind: str,
        provider_document_id: str,
    ) -> ResourceKey:
        if resource_kind not in {"review", "comment", "thread", "document"}:
            raise ValueError("A document requires a typed document resource kind")
        return cls(
            parent.service_instance_uuidv4,
            resource_kind,
            canonical(
                [
                    parent.resource_kind,
                    parent.provider_resource_id,
                    document_kind,
                    provider_document_id,
                ]
            ),
        )

    def coordinates(self) -> tuple[str, str, str]:
        return (
            self.service_instance_uuidv4,
            self.resource_kind,
            self.provider_resource_id,
        )


@dataclass(frozen=True)
class FieldClock:
    """An actual source clock; None explicitly means no comparable source clock."""

    domain: str
    at_us: int | None

    def __post_init__(self) -> None:
        if not self.domain:
            raise ValueError("Clock domain must identify the genuine source clock")
        if self.at_us is not None:
            validate_epoch_us(self.at_us)

    def encode(self) -> str:
        return canonical({"domain": self.domain, "at_us": self.at_us})


@dataclass(frozen=True)
class FieldCandidate:
    resource: ResourceKey
    field_name: str
    value_json: str
    clock: FieldClock
    provenance_json: str
    observed_at_us: int

    def __post_init__(self) -> None:
        validate_epoch_us(self.observed_at_us)
        if canonical(json.loads(self.value_json)) != self.value_json:
            raise ValueError("Value must be canonical JSON")
        provenance = json.loads(self.provenance_json)
        if (
            not isinstance(provenance, dict)
            or not isinstance(provenance.get("source"), str)
            or not provenance["source"]
            or provenance.get("evidence") is None
        ):
            raise ValueError("Original field provenance must be an object")
        if canonical(json.loads(self.provenance_json)) != self.provenance_json:
            raise ValueError("Provenance must be canonical JSON")
        if not self.field_name:
            raise ValueError("Field name must not be empty")


@dataclass(frozen=True)
class CoverageScope:
    owner_kind: OwnerKind
    coordinates: tuple[str, ...]

    def __post_init__(self) -> None:
        sizes = {
            "repository": 2,
            "source": 3,
            "resource": 4,
            "collection": 6,
            "field": 5,
            "source_inventory": 3,
        }
        if (
            self.owner_kind not in sizes
            or len(self.coordinates) != sizes[self.owner_kind]
        ):
            raise ValueError("Full typed owner coordinates required")
        if any(not isinstance(item, str) or not item for item in self.coordinates):
            raise ValueError("Scope coordinates must be genuine nonempty strings")

    @property
    def encoded(self) -> str:
        return canonical(list(self.coordinates))

    @classmethod
    def repository(cls, repository_uuidv4: str, kind: str) -> CoverageScope:
        return cls("repository", (repository_uuidv4, kind))

    @classmethod
    def source(
        cls, source_registration_uuidv4: str, repository_uuidv4: str, kind: str
    ) -> CoverageScope:
        return cls("source", (source_registration_uuidv4, repository_uuidv4, kind))

    @classmethod
    def source_inventory(
        cls, source_registration_uuidv4: str, scope_json: str, kind: str
    ) -> CoverageScope:
        return cls("source_inventory", (source_registration_uuidv4, scope_json, kind))

    @classmethod
    def resource(cls, resource: ResourceKey, kind: str) -> CoverageScope:
        return cls("resource", (*resource.coordinates(), kind))

    @classmethod
    def field(cls, resource: ResourceKey, field: str, kind: str) -> CoverageScope:
        return cls("field", (*resource.coordinates(), field, kind))

    @classmethod
    def collection(
        cls,
        resource: ResourceKey,
        collection_kind: str,
        original_provenance_json: str,
        kind: str,
    ) -> CoverageScope:
        return cls(
            "collection",
            (*resource.coordinates(), collection_kind, original_provenance_json, kind),
        )
