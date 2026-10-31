"""Shared read-result, fence, and pagination contracts; no concrete store implementation."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

from repo_catalog.domain.p1_coordination import SnapshotToken
from repo_catalog.domain.shared_values import uuid4_value

if TYPE_CHECKING:
    from repo_catalog.domain.p1_coverage import CoverageClaim, CoverageOwner

T = TypeVar("T")
CatalogReadMode = Literal["core_only", "context_only", "paired"]


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
        validate_key: Callable[[str, tuple], None],
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
        try:
            validate_key(cursor_obj.endpoint_kind, cursor_obj.last_key)
        except Exception as error:
            raise QueryError(
                "INVALID_CURSOR", "pagination", "invalid endpoint key"
            ) from error
        if cursor_obj.snapshot_token != current_snapshot_token:
            raise QueryError(
                "SNAPSHOT_MISMATCH",
                "pagination",
                "cursor snapshot token does not match current pinned snapshot",
            )
        return cursor_obj


def _validate_cursor_key(endpoint: str, key: tuple[Any, ...]) -> None:
    """Validate the shared transport shape; the owning endpoint validates meaning."""
    if (
        not isinstance(key, tuple)
        or not key
        or any(type(v) is not str or not v or len(v) > 32768 for v in key)
    ):
        raise QueryError("INVALID_CURSOR", "pagination", "invalid endpoint key shape")


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
class CoverageView:
    """Authoritative Coverage projection view for Core or Context scopes."""

    scope: CoverageOwner
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
