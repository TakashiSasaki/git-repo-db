"""Typed query, snapshot, pagination, byte-read, and Search domain models for P6.

Enforces the six explicit P5/P6 architectural distinctions:
1. Domain identity vs. transport envelope identity (pagination cursors and page
   wrappers never become durable PK/FK identities).
2. Original source reports vs. receiver-checked facts (`canonical` vs.
   `alternatives`, `role_verified`, `verified` byte reads).
3. Metadata completeness vs. byte availability (`metadata_retained`,
   `note_retained`, `ByteReadResult.available` vs. `CoverageView.state`).
4. Context availability vs. Git Core availability (`core_only`, `context_only`,
   `paired` topologies and `PairedCoreResolution`).
5. Durable authority vs. Operational progress.
6. Authoritative query results vs. derivative Search candidates (`SearchHit`
   always verified against the pinned authoritative snapshot).
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

from repo_catalog.domain.p1_coordination import SnapshotToken
from repo_catalog.domain.p1_core import (
    OID,
    Capture,
    CoreCoverageScope,
    GitObservation,
    NotesAlternative,
    Projection,
    Provenance,
    RepositoryClaim,
    encode,
    uuid4_value,
)
from repo_catalog.domain.p1_coverage import CoverageClaim, CoverageOwner

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
    from repo_catalog.domain.ref_observation import (
        NotesMappingProjection,
        RefObservationProjection,
    )
    from repo_catalog.domain.resource_identification import ResourceIdentification

T = TypeVar("T")

CatalogReadMode = Literal["core_only", "context_only", "paired"]
SearchProjectionKind = Literal["git_metadata", "notes", "context_text"]
SEARCH_PROJECTION_KINDS: tuple[SearchProjectionKind, ...] = (
    "git_metadata",
    "notes",
    "context_text",
)


class QueryError(ValueError):
    """Typed P6 query, snapshot fence, pagination, or search boundary failure."""

    def __init__(self, code: str, scope: object, detail: str = ""):
        self.code = code
        self.scope = scope
        self.detail = detail
        super().__init__(f"{scope}:{code}: {detail}" if detail else f"{scope}:{code}")


def _reject_json_constant(value):
    raise ValueError("nonfinite JSON number: " + value)


def canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _sha256_hex(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SnapshotFenceToken:
    """Canonical JSON snapshot fence token supporting paired and single-store reads.

    In `paired` mode, `.encode()` produces the exact same canonical JSON as
    `SnapshotToken.encode()` (`{"catalog_instance_uuidv4":...,"context_sha256":...,
    "core_sha256":...,"repository_uuidv4":...}`) so `PairSnapshot.token` and
    `search.sqlite3` tokens interoperate seamlessly.
    In `core_only` or `context_only` mode, the absent store's digest is `None`.
    """

    mode: CatalogReadMode
    repository_uuidv4: str
    catalog_instance_uuidv4: str
    core_sha256: str | None = None
    context_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in ("core_only", "context_only", "paired"):
            raise QueryError("INVALID_MODE", "snapshot", str(self.mode))
        try:
            uuid4_value(self.repository_uuidv4)
            uuid4_value(self.catalog_instance_uuidv4)
        except Exception as error:
            raise QueryError(
                "INVALID_TOKEN", "snapshot", "canonical UUIDv4 required"
            ) from error
        if self.mode == "paired":
            if not _valid_sha256(self.core_sha256) or not _valid_sha256(
                self.context_sha256
            ):
                raise QueryError(
                    "INVALID_TOKEN",
                    "snapshot",
                    "paired token requires core and context sha256",
                )
        elif self.mode == "core_only":
            if not _valid_sha256(self.core_sha256) or self.context_sha256 is not None:
                raise QueryError(
                    "INVALID_TOKEN",
                    "snapshot",
                    "core_only token requires core_sha256 only",
                )
        elif self.mode == "context_only":
            if not _valid_sha256(self.context_sha256) or self.core_sha256 is not None:
                raise QueryError(
                    "INVALID_TOKEN",
                    "snapshot",
                    "context_only token requires context_sha256 only",
                )

    @classmethod
    def from_pair_token(cls, token: SnapshotToken) -> SnapshotFenceToken:
        return cls(
            mode="paired",
            repository_uuidv4=token.repository_uuidv4,
            catalog_instance_uuidv4=token.catalog_instance_uuidv4,
            core_sha256=token.core_sha256,
            context_sha256=token.context_sha256,
        )

    def to_pair_token(self) -> SnapshotToken:
        if (
            self.mode != "paired"
            or self.core_sha256 is None
            or self.context_sha256 is None
        ):
            raise QueryError(
                "MODE_MISMATCH", "snapshot", "not a paired SnapshotFenceToken"
            )
        return SnapshotToken(
            repository_uuidv4=self.repository_uuidv4,
            catalog_instance_uuidv4=self.catalog_instance_uuidv4,
            core_sha256=self.core_sha256,
            context_sha256=self.context_sha256,
        )

    def encode(self) -> str:
        if self.mode == "paired":
            return canonical_json(
                {
                    "catalog_instance_uuidv4": self.catalog_instance_uuidv4,
                    "context_sha256": self.context_sha256,
                    "core_sha256": self.core_sha256,
                    "repository_uuidv4": self.repository_uuidv4,
                }
            )
        return canonical_json(
            {
                "catalog_instance_uuidv4": self.catalog_instance_uuidv4,
                "context_sha256": self.context_sha256,
                "core_sha256": self.core_sha256,
                "mode": self.mode,
                "repository_uuidv4": self.repository_uuidv4,
            }
        )

    @classmethod
    def parse(cls, raw: str) -> SnapshotFenceToken:
        if not isinstance(raw, str) or not raw or len(raw) > 65536:
            raise QueryError("INVALID_TOKEN", "snapshot", "nonempty token required")
        try:
            data = json.loads(raw, parse_constant=_reject_json_constant)
        except Exception as error:
            raise QueryError(
                "INVALID_TOKEN", "snapshot", "malformed token JSON"
            ) from error
        if not isinstance(data, dict) or canonical_json(data) != raw:
            raise QueryError(
                "INVALID_TOKEN", "snapshot", "noncanonical snapshot token JSON"
            )
        mode = data.get("mode", "paired")
        expected_keys = (
            {
                "catalog_instance_uuidv4",
                "context_sha256",
                "core_sha256",
                "repository_uuidv4",
            }
            if "mode" not in data
            else {
                "catalog_instance_uuidv4",
                "context_sha256",
                "core_sha256",
                "mode",
                "repository_uuidv4",
            }
        )
        if set(data.keys()) != expected_keys:
            raise QueryError(
                "INVALID_TOKEN", "snapshot", "unexpected snapshot token keys"
            )
        token = cls(
            mode=mode,
            repository_uuidv4=data["repository_uuidv4"],
            catalog_instance_uuidv4=data["catalog_instance_uuidv4"],
            core_sha256=data["core_sha256"],
            context_sha256=data["context_sha256"],
        )
        if token.encode() != raw:
            raise QueryError(
                "INVALID_TOKEN", "snapshot", "noncanonical snapshot token encoding"
            )
        return token


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


@dataclass(frozen=True)
class PageRequest:
    """Pagination request with optional cursor and snapshot token fence."""

    limit: int = 50
    cursor: str | None = None
    expected_token: str | None = None

    def __post_init__(self) -> None:
        if type(self.limit) is not int or self.limit <= 0 or self.limit > 10_000:
            raise QueryError(
                "INVALID_LIMIT", "pagination", "limit must be int in 1..10000"
            )
        if self.cursor is not None and (
            not isinstance(self.cursor, str)
            or not self.cursor
            or len(self.cursor) > 65536
        ):
            raise QueryError(
                "INVALID_CURSOR", "pagination", "cursor must be a nonempty string"
            )
        if self.expected_token is not None:
            SnapshotFenceToken.parse(self.expected_token)


@dataclass(frozen=True)
class PaginationCursor:
    """Deterministic cursor binding endpoint, filter digest, snapshot token, and last key."""

    endpoint_kind: str
    filter_digest: str
    snapshot_token: str
    last_key: tuple[Any, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint_kind, str) or not self.endpoint_kind:
            raise QueryError("INVALID_CURSOR", "pagination", "endpoint_kind required")
        if not _valid_sha256(self.filter_digest):
            raise QueryError(
                "INVALID_CURSOR", "pagination", "valid filter_digest required"
            )
        SnapshotFenceToken.parse(self.snapshot_token)
        _validate_cursor_key(self.endpoint_kind, self.last_key)

    def encode(self) -> str:
        payload = {
            "endpoint_kind": self.endpoint_kind,
            "filter_digest": self.filter_digest,
            "last_key": list(self.last_key),
            "snapshot_token": self.snapshot_token,
            "v": 1,
        }
        payload_json = canonical_json(payload)
        checksum = _sha256_hex(f"p6-cursor-v1:{payload_json}")
        envelope = canonical_json({"checksum_sha256": checksum, "payload": payload})
        return base64.urlsafe_b64encode(envelope.encode("utf-8")).decode("ascii")

    @classmethod
    def decode(
        cls,
        raw: str,
        *,
        expected_endpoint: str,
        expected_filter_digest: str,
        current_snapshot_token: str,
    ) -> PaginationCursor:
        if not isinstance(raw, str) or not raw or len(raw) > 65536:
            raise QueryError("INVALID_CURSOR", "pagination", "empty cursor")
        try:
            padded = raw + "=" * (-len(raw) % 4)
            decoded_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
            if base64.urlsafe_b64encode(decoded_bytes).decode("ascii").rstrip(
                "="
            ) != raw.rstrip("="):
                raise ValueError("noncanonical base64")
            envelope_text = decoded_bytes.decode("utf-8")
            envelope = json.loads(envelope_text, parse_constant=_reject_json_constant)
        except Exception as error:
            raise QueryError(
                "INVALID_CURSOR", "pagination", "malformed cursor encoding"
            ) from error
        if (
            not isinstance(envelope, dict)
            or set(envelope.keys()) != {"checksum_sha256", "payload"}
            or canonical_json(envelope) != envelope_text
        ):
            raise QueryError(
                "INVALID_CURSOR", "pagination", "malformed cursor envelope"
            )
        payload = envelope["payload"]
        if (
            not isinstance(payload, dict)
            or set(payload.keys())
            != {"endpoint_kind", "filter_digest", "last_key", "snapshot_token", "v"}
            or type(payload.get("v")) is not int
            or payload.get("v") != 1
            or not isinstance(payload.get("last_key"), list)
            or not payload["last_key"]
        ):
            raise QueryError("INVALID_CURSOR", "pagination", "malformed cursor payload")
        expected_checksum = _sha256_hex(f"p6-cursor-v1:{canonical_json(payload)}")
        if envelope["checksum_sha256"] != expected_checksum:
            raise QueryError("INVALID_CURSOR", "pagination", "cursor checksum mismatch")
        cursor_obj = cls(
            endpoint_kind=payload["endpoint_kind"],
            filter_digest=payload["filter_digest"],
            snapshot_token=payload["snapshot_token"],
            last_key=tuple(payload["last_key"]),
        )
        if cursor_obj.endpoint_kind != expected_endpoint:
            raise QueryError(
                "INVALID_CURSOR",
                "pagination",
                f"cursor endpoint mismatch: {cursor_obj.endpoint_kind} != {expected_endpoint}",
            )
        if cursor_obj.filter_digest != expected_filter_digest:
            raise QueryError(
                "INVALID_CURSOR",
                "pagination",
                "cursor filter parameters do not match query",
            )
        if cursor_obj.snapshot_token != current_snapshot_token:
            raise QueryError(
                "SNAPSHOT_MISMATCH",
                "pagination",
                "cursor snapshot token does not match current pinned snapshot",
            )
        return cursor_obj


def _validate_cursor_key(endpoint: str, key: tuple[Any, ...]) -> None:
    """Validate untrusted positions independently of the public checksum.

    A checksum detects accidental changes only. Anyone can recompute it and
    choose another valid position; cursors grant no authority or access rights.
    """
    widths = {
        "git_objects": 2,
        "ref_observations": 2,
        "git_observations": 5,
        "notes_captures": 3,
        "context_resources": 3,
        "paired_resources": 3,
        "search": 2,
    }
    try:
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
        elif endpoint in ("context_resources", "paired_resources"):
            from repo_catalog.domain.p1_context import ResourceKey

            ResourceKey(*key)
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
            if (
                not isinstance(scope, list)
                or not scope
                or canonical_json(scope) != key[1]
            ):
                raise ValueError("invalid scope")
            uuid4_value(key[2])
            uuid4_value(key[3])
            provenance = json.loads(key[4])
            if (
                not isinstance(provenance, list)
                or Provenance(*provenance).encoded != key[4]
            ):
                raise ValueError("invalid provenance")
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
    except Exception as error:
        raise QueryError(
            "INVALID_CURSOR", "pagination", "invalid endpoint key"
        ) from error


def filter_digest(endpoint_kind: str, filters: dict[str, object]) -> str:
    return _sha256_hex(canonical_json({"endpoint": endpoint_kind, "filters": filters}))


@dataclass(frozen=True)
class PageResult(Generic[T]):
    """Deterministic page response carrying the pinned snapshot token."""

    items: tuple[T, ...]
    snapshot_token: str
    next_cursor: str | None
    has_more: bool
    total_count: int


@dataclass(frozen=True)
class ByteReadResult:
    """Verification-aware read result for retained metadata, note blobs, and Context text."""

    available: bool
    verified: bool
    body_bytes: bytes | None = None
    text_value: str | None = None
    declared_size: int | None = None
    digest_sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "body_hex": self.body_bytes.hex() if self.body_bytes is not None else None,
            "declared_size": self.declared_size,
            "digest_sha256": self.digest_sha256,
            "text_value": self.text_value,
            "verified": self.verified,
        }


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

    oid: OID
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
            "full_oid": self.oid.full_oid,
            "metadata_retained": self.metadata_retained,
            "native_type": self.native_type,
            "ref_notes_targets": [n.to_dict() for n in self.ref_notes_targets],
            "object_format": self.oid.object_format,
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


@dataclass(frozen=True)
class _LegacyNotesTargetView:
    """Authoritative Notes target projection and byte retention state."""

    capture: Capture
    target: OID
    canonical: OID | None
    alternatives: tuple[NotesAlternative, ...]
    reported_conflict: bool
    checked_scope: str | None
    role_verified: bool
    note_retained: bool
    note_bytes: ByteReadResult | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "alternatives": [
                {
                    "capture_pair": list(alt.capture_pair),
                    "checked": alt.checked,
                    "kind": alt.kind,
                    "membership": [list(m) for m in alt.membership],
                    "note": list(alt.note.key) if alt.note is not None else None,
                    "path": alt.path,
                    "provenance": (
                        list(alt.provenance.key) if alt.provenance is not None else None
                    ),
                    "scope": alt.scope,
                    "status": alt.status,
                    "target": list(alt.target.key),
                }
                for alt in self.alternatives
            ],
            "canonical": (
                list(self.canonical.key) if self.canonical is not None else None
            ),
            "capture": {
                "capture_origin_uuidv4": self.capture.capture_origin_uuidv4,
                "capture_uuidv4": self.capture.capture_uuidv4,
                "ref": self.capture.ref,
                "repository_uuidv4": self.capture.repository_uuidv4,
                "root": list(self.capture.root.key),
                "source": self.capture.source,
            },
            "checked_scope": self.checked_scope,
            "note_bytes": (
                self.note_bytes.to_dict() if self.note_bytes is not None else None
            ),
            "note_retained": self.note_retained,
            "reported_conflict": self.reported_conflict,
            "role_verified": self.role_verified,
            "target": list(self.target.key),
        }


@dataclass(frozen=True)
class _LegacyNotesInventoryView:
    """Authoritative Notes inventory view."""

    capture: Capture
    scope: str
    status: str
    members: tuple[tuple[str, str, str | None], ...]
    provenance: Provenance
    receiver_verified: bool
    diagnostic: tuple[str, str] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "capture_origin_uuidv4": self.capture.capture_origin_uuidv4,
            "capture_uuidv4": self.capture.capture_uuidv4,
            "diagnostic": list(self.diagnostic)
            if self.diagnostic is not None
            else None,
            "members": [list(m) for m in self.members],
            "provenance": list(self.provenance.key),
            "receiver_verified": self.receiver_verified,
            "scope": self.scope,
            "status": self.status,
        }


@dataclass(frozen=True)
class _LegacyNotesCaptureView:
    """Authoritative Notes capture summary with targets and inventories."""

    capture: Capture
    targets: tuple[OID, ...]
    inventories: tuple[_LegacyNotesInventoryView, ...]

    @property
    def semantic_key(self) -> tuple[str, str, str]:
        return (
            self.capture.ref,
            self.capture.capture_origin_uuidv4,
            self.capture.capture_uuidv4,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "capture_origin_uuidv4": self.capture.capture_origin_uuidv4,
            "capture_uuidv4": self.capture.capture_uuidv4,
            "inventories": [inv.to_dict() for inv in self.inventories],
            "ref": self.capture.ref,
            "repository_uuidv4": self.capture.repository_uuidv4,
            "root": list(self.capture.root.key),
            "source": self.capture.source,
            "targets": [list(t.key) for t in self.targets],
        }


@dataclass(frozen=True)
class CoverageView:
    """Authoritative Coverage projection view for Core or Context scopes."""

    scope: CoreCoverageScope | CoverageOwner
    state: str
    known_empty: bool
    latest_observed_at_us: int | None
    claims: tuple[CoverageClaim, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "claims": [
                {
                    "details": (
                        json.loads(c.details_json)
                        if c.details_json is not None
                        else None
                    ),
                    "observed_at_us": c.observed_at_us,
                    "state": c.state,
                }
                for c in self.claims
            ],
            "known_empty": self.known_empty,
            "latest_observed_at_us": self.latest_observed_at_us,
            "owner_coordinates": json.loads(self.scope.encoded),
            "owner_kind": self.scope.owner_kind,
            "state": self.state,
        }


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
                    "oid": list(dep.reference.oid.key),
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
            "oid": list(self.reference.oid.key),
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
