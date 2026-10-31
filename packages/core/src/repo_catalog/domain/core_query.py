"""Core authoritative query view types and Core cursor positions."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from typing import TYPE_CHECKING

from repo_catalog.domain.p1_core import (
    OID,
    GitObservation,
    Projection,
    Provenance,
    RepositoryClaim,
    encode,
)
from repo_catalog.domain.query_contracts import ByteReadResult, canonical_json
from repo_catalog.domain.shared_values import uuid4_value

if TYPE_CHECKING:
    from repo_catalog.domain.ref_observation import (
        NotesMappingProjection,
        RefObservationProjection,
    )


@dataclass(frozen=True)
class GitRepositoryView:
    """Authoritative Git Core repository identity and attributed repository claims."""

    repository_uuidv4: str
    catalog_instance_uuidv4: str
    claims: dict[str, tuple[RepositoryClaim, ...]]

    def to_dict(self) -> dict[str, object]:
        return {
            "catalog_instance_uuidv4": self.catalog_instance_uuidv4,
            "claims": {
                field: [
                    {
                        "field": c.field,
                        "provenance": list(c.provenance.key),
                        "repository_uuidv4": c.repository_uuidv4,
                        "value": c.value,
                    }
                    for c in claims
                ]
                for field, claims in sorted(self.claims.items())
            },
            "repository_uuidv4": self.repository_uuidv4,
        }


def ref_projection_json(value):
    """Lossless JSON for checked ref values; bytes never pass through UTF-8."""
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if is_dataclass(value):
        return {
            f.name: ref_projection_json(getattr(value, f.name)) for f in fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [ref_projection_json(v) for v in value]
    return value


@dataclass(frozen=True)
class RefNotesTargetView:
    observation: RefObservationProjection
    mapping: NotesMappingProjection

    def to_dict(self):
        return ref_projection_json(self)


@dataclass(frozen=True)
class GitObjectView:
    """Authoritative Git Core object view with scalar/relation projections and byte status."""

    object_oid: OID
    scalars: dict[str, Projection]
    relations: dict[str, Projection]
    metadata_retained: bool
    retained_bytes: ByteReadResult | None = None
    ref_notes_targets: tuple[RefNotesTargetView, ...] = ()

    @property
    def native_type(self) -> str | None:
        type_proj = self.scalars.get("type")
        if type_proj is not None and isinstance(type_proj.canonical, list):
            if len(type_proj.canonical) == 2 and type_proj.canonical[0] == "known":
                return str(type_proj.canonical[1])
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "object_oid": self.object_oid.object_oid,
            "metadata_retained": self.metadata_retained,
            "native_type": self.native_type,
            "ref_notes_targets": [n.to_dict() for n in self.ref_notes_targets],
            "object_format": self.object_oid.object_format,
            "relations": {
                rel: {
                    "alternatives": list(proj.alternatives),
                    "canonical": proj.canonical,
                    "checked_scope": proj.checked_scope,
                    "reported_conflict": proj.reported_conflict,
                }
                for rel, proj in sorted(self.relations.items())
            },
            "retained_bytes": (
                self.retained_bytes.to_dict()
                if self.retained_bytes is not None
                else None
            ),
            "scalars": {
                field: {
                    "alternatives": list(proj.alternatives),
                    "canonical": proj.canonical,
                    "checked_scope": proj.checked_scope,
                    "reported_conflict": proj.reported_conflict,
                }
                for field, proj in sorted(self.scalars.items())
            },
        }


@dataclass(frozen=True)
class GitObservationView:
    """Authoritative Git observation view."""

    observation: GitObservation

    @property
    def semantic_key(self) -> tuple[str, str, str, str]:
        return (
            self.observation.kind,
            encode(self.observation.scope),
            self.observation.capture_origin_uuidv4,
            self.observation.capture_uuidv4,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "capture_origin_uuidv4": self.observation.capture_origin_uuidv4,
            "capture_uuidv4": self.observation.capture_uuidv4,
            "kind": self.observation.kind,
            "provenance": list(self.observation.provenance.key),
            "repository_uuidv4": self.observation.repository_uuidv4,
            "scope": list(self.observation.scope),
            "value": self.observation.value,
        }


def validate_cursor_key(endpoint: str, key: tuple) -> None:
    """Validate untrusted Core positions without accepting checksum as evidence."""
    widths = {
        "git_objects": 2,
        "ref_observations": 2,
        "git_observations": 5,
        "notes_captures": 3,
    }
    if (
        endpoint not in widths
        or not isinstance(key, tuple)
        or len(key) != widths[endpoint]
        or any(type(v) is not str or not v or len(v) > 32768 for v in key)
    ):
        raise ValueError("invalid key shape or type")
    if endpoint == "git_objects":
        OID(*key)
    elif endpoint == "ref_observations":
        from repo_catalog.domain.ref_observation import RefObservationKey

        RefObservationKey(*key)
    elif endpoint == "notes_captures":
        uuid4_value(key[1])
        uuid4_value(key[2])
    elif endpoint == "git_observations":
        if key[0] not in (
            "acquisition",
            "ref",
            "root",
            "snapshot",
            "membership",
            "manifest",
        ):
            raise ValueError("invalid observation kind")
        scope = json.loads(key[1])
        if not isinstance(scope, list) or not scope or canonical_json(scope) != key[1]:
            raise ValueError("invalid scope")
        uuid4_value(key[2])
        uuid4_value(key[3])
        provenance = json.loads(key[4])
        if (
            not isinstance(provenance, list)
            or Provenance(*provenance).encoded != key[4]
        ):
            raise ValueError("invalid provenance")
