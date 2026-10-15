"""Production Context units composed from the frozen P1 semantic values.

These are domain observations, not raw Provider responses or intake envelopes.
Their coordinates retain the original service, parent, scope and evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from repo_catalog.domain.p1_context import FieldCandidate, ResourceKey, canonical
from repo_catalog.domain.p1_core import OID
from repo_catalog.domain.time import validate_epoch_us


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

    def __post_init__(self):
        if any(field.resource != self.resource for field in self.fields):
            raise ContextError("FIELD_OWNER", "resource")


@dataclass(frozen=True)
class ResourceRelation:
    resource: ResourceKey
    relation_kind: str
    members: tuple[ResourceKey, ...]
    provenance_json: str
    scope_json: str
    observed_at_us: int

    def __post_init__(self):
        if not self.relation_kind:
            raise ContextError("MISSING_KIND", "relation")
        validate_epoch_us(self.observed_at_us)
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
        validate_epoch_us(self.observed_at_us)
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


@dataclass(frozen=True)
class CoreDependency:
    reference: CoreReference
    available: bool
    required: bool = False
    candidate: FieldCandidate | None = None
    # Nominal presence never establishes intrinsic verification or graph closure.
