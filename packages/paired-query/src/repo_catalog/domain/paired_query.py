"""Paired Query views and paired endpoint cursor semantics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from repo_catalog.domain.context_query import ContextResourceView
from repo_catalog.domain.context_query import (
    validate_cursor_key as validate_context_key,
)

if TYPE_CHECKING:
    from repo_catalog.domain.core_query import GitObjectView, RefNotesTargetView
    from repo_catalog.domain.p1_context import ResourceKey
    from repo_catalog.domain.production_context import CoreReference


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
    if endpoint != "paired_resources":
        raise ValueError("invalid paired endpoint")
    validate_context_key("context_resources", key)
