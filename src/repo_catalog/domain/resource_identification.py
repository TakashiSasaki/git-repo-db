"""Explicit native identification declarations, separate from Resource identity.

Namespace coordinates do not assert a semantic Parent or its existence. Only
resource_relations can carry such a report. No declaration is inferred from an
arbitrary key's array shape or the ResourceKey factory's transient intent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from repo_catalog.domain.resource_identity import (
    IdentityValue,
    encode_identity,
    parse_identity,
)

if TYPE_CHECKING:
    from repo_catalog.domain.p1_context import ResourceKey

SCOPED_NAMESPACES = {
    "review": frozenset({"pull_request"}),
    "comment": frozenset({"pull_request", "issue", "review", "thread"}),
    "thread": frozenset({"pull_request", "review"}),
    "document": frozenset({"pull_request"}),
}


def validate_identification(kind, raw, namespace_kind, namespace_id, subtype, local):
    """Validate the complete bounded row; used by both SQL and typed admission."""
    if type(kind) is not str or not kind:
        raise ValueError("nonempty exact kind TEXT required")
    parse_identity(raw)
    metadata = (namespace_kind, namespace_id, subtype, local)
    if kind == "document" and all(x is None for x in metadata[:3]):
        parse_identity(local)
        if local != raw:
            raise ValueError("global native ID must repeat the complete identity")
    elif kind in SCOPED_NAMESPACES:
        if (
            type(namespace_kind) is not str
            or namespace_kind not in SCOPED_NAMESPACES[kind]
            or type(subtype) is not str
            or not subtype
        ):
            raise ValueError("reserved scoped identification contract")
        parse_identity(namespace_id)
        native_local = parse_identity(local)
        if raw != encode_identity(
            [namespace_kind, namespace_id, subtype, native_local]
        ):
            raise ValueError("identifying coordinates do not reconstruct the key")
    elif any(x is not None for x in metadata):
        raise ValueError("unscoped kind cannot claim known scoped metadata")


@dataclass(frozen=True)
class ResourceIdentification:
    resource: ResourceKey
    identifier_namespace_kind: str | None = None
    identifier_namespace_id: str | None = None
    document_kind: str | None = None
    provider_document_id: str | None = None

    def __post_init__(self):
        from repo_catalog.domain.p1_context import ResourceKey

        if not isinstance(self.resource, ResourceKey):
            raise ValueError("ResourceKey required")
        validate_identification(
            self.resource.resource_kind,
            self.resource.provider_resource_id,
            *self.columns,
        )

    @property
    def columns(self) -> tuple[str | None, str | None, str | None, str | None]:
        return (
            self.identifier_namespace_kind,
            self.identifier_namespace_id,
            self.document_kind,
            self.provider_document_id,
        )

    @classmethod
    def unscoped(cls, key: ResourceKey) -> ResourceIdentification:
        if key.resource_kind in SCOPED_NAMESPACES:
            raise ValueError(
                "known document kind requires explicit ResourceIdentification"
            )
        return cls(key)

    @classmethod
    def global_document(cls, key: ResourceKey) -> ResourceIdentification:
        if key.resource_kind != "document":
            raise ValueError("global Document declaration requires document kind")
        return cls(key, provider_document_id=key.provider_resource_id)

    @classmethod
    def scoped(
        cls,
        key: ResourceKey,
        namespace: ResourceKey,
        subtype: str,
        native_local: IdentityValue,
    ) -> ResourceIdentification:
        if key.service_instance_uuidv4 != namespace.service_instance_uuidv4:
            raise ValueError("identification namespace service mismatch")
        return cls(
            key,
            namespace.resource_kind,
            namespace.provider_resource_id,
            subtype,
            encode_identity(native_local),
        )

    @classmethod
    def from_storage(cls, key: ResourceKey, columns) -> ResourceIdentification:
        if len(columns) != 4:
            raise ValueError("four identification columns required")
        return cls(key, *columns)


def require_identification(key, identification=None) -> ResourceIdentification:
    from repo_catalog.domain.p1_context import ResourceKey

    if not isinstance(key, ResourceKey):
        raise ValueError("ResourceKey required")
    if identification is None:
        # Known document kinds always need an explicit declaration, even replay.
        return ResourceIdentification.unscoped(key)
    if (
        not isinstance(identification, ResourceIdentification)
        or identification.resource != key
    ):
        raise ValueError("ResourceIdentification must bind the same ResourceKey")
    # Revalidate before duplicate/conflict shortcuts.
    validate_identification(
        key.resource_kind, key.provider_resource_id, *identification.columns
    )
    return identification


def identity_sql(raw):
    try:
        parse_identity(raw)
        return 1
    except (TypeError, ValueError):
        return 0


def identification_sql(*args):
    try:
        validate_identification(*args)
        return 1
    except (TypeError, ValueError):
        return 0
