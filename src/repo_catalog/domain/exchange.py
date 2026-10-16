"""P5 portable typed Exchange domain and wire contract (`git-repo-db/p5-exchange-v1`).

Enforces strict separation between:
- Transport envelope identity (`package_id`, `exported_at_us`, `sender_catalog_instance_uuidv4`)
- Durable domain identity and original observation provenance
- Sender-attributed reports vs. receiver-validated byte/proof artifacts
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_core import OID, CoreFailure, encode, uuid4_value
from repo_catalog.domain.time import validate_epoch_us

FORMAT = "git-repo-db/p5-exchange-v1"

CORE_SECTION_KEYS = (
    "repositories",
    "repository_claims",
    "git_objects",
    "scalar_claims",
    "relation_groups",
    "git_observations",
    "captures",
    "notes_claims",
    "notes_groups",
    "notes_inventories",
    "retained_metadata",
    "note_roles",
    "retained_notes",
    "coverage_scopes",
    "coverage_claims",
    "coverage_proofs",
)

CONTEXT_SECTION_KEYS = (
    "providers",
    "repositories",
    "repository_candidates",
    "sources",
    "source_repositories",
    "source_inventories",
    "resources",
    "resource_relations",
    "collections",
    "text_bodies",
    "field_candidates",
    "core_references",
    "coverage_scopes",
    "coverage_claims",
    "coverage_proofs",
)


class ExchangeError(ValueError):
    """Typed Exchange wire format or validation failure."""

    def __init__(self, code: str, scope: object, detail: str = ""):
        self.code = code
        self.scope = scope
        self.detail = detail
        super().__init__(f"{scope}:{code}: {detail}" if detail else f"{scope}:{code}")


@dataclass(frozen=True)
class ExchangeSelectionScope:
    """Selective export/import filter specification."""

    include_core: bool = True
    include_context: bool = True
    include_retained_bytes: bool = True
    object_oids: tuple[OID, ...] | None = None
    notes_refs: tuple[str, ...] | None = None
    resource_keys: tuple[ResourceKey, ...] | None = None
    source_uuidv4s: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "include_core": self.include_core,
            "include_context": self.include_context,
            "include_retained_bytes": self.include_retained_bytes,
            "object_oids": (
                None
                if self.object_oids is None
                else [
                    list(oid.key) if isinstance(oid, OID) else ["sha1", str(oid)]
                    for oid in sorted(
                        set(self.object_oids),
                        key=lambda o: (
                            list(o.key) if isinstance(o, OID) else ["sha1", str(o)]
                        ),
                    )
                ]
            ),
            "notes_refs": (
                None if self.notes_refs is None else sorted(set(self.notes_refs))
            ),
            "resource_keys": (
                None
                if self.resource_keys is None
                else [
                    list(rk.coordinates())
                    for rk in sorted(
                        set(self.resource_keys), key=lambda k: k.coordinates()
                    )
                ]
            ),
            "source_uuidv4s": (
                None
                if self.source_uuidv4s is None
                else sorted(set(self.source_uuidv4s))
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExchangeSelectionScope:
        if not isinstance(data, dict):
            raise ExchangeError("INVALID_SELECTION", "selection_scope", "dict required")
        raw_oids = data.get("object_oids")
        raw_refs = data.get("notes_refs")
        raw_rks = data.get("resource_keys")
        raw_srcs = data.get("source_uuidv4s")
        try:
            oids = (
                None
                if raw_oids is None
                else tuple(OID(item[0], item[1]) for item in raw_oids)
            )
            refs = None if raw_refs is None else tuple(str(r) for r in raw_refs)
            rks = (
                None
                if raw_rks is None
                else tuple(ResourceKey(item[0], item[1], item[2]) for item in raw_rks)
            )
            srcs = (
                None
                if raw_srcs is None
                else tuple(uuid4_value(str(s)) for s in raw_srcs)
            )
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            raise ExchangeError(
                "INVALID_SELECTION", "selection_scope", str(exc)
            ) from exc
        return cls(
            include_core=bool(data.get("include_core", True)),
            include_context=bool(data.get("include_context", True)),
            include_retained_bytes=bool(data.get("include_retained_bytes", True)),
            object_oids=oids,
            notes_refs=refs,
            resource_keys=rks,
            source_uuidv4s=srcs,
        )


def empty_core_section() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in CORE_SECTION_KEYS}


def empty_context_section() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in CONTEXT_SECTION_KEYS}


@dataclass(frozen=True)
class ExchangePackage:
    """Portable typed Exchange package (`git-repo-db/p5-exchange-v1`)."""

    package_id: str
    exported_at_us: int
    sender_catalog_instance_uuidv4: str
    repository_uuidv4: str
    selection_scope: ExchangeSelectionScope = field(
        default_factory=ExchangeSelectionScope
    )
    core: dict[str, list[dict[str, Any]]] | None = None
    context: dict[str, list[dict[str, Any]]] | None = None
    format: str = FORMAT

    def __post_init__(self) -> None:
        validate_package_envelope(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "package_id": self.package_id,
            "exported_at_us": self.exported_at_us,
            "sender_catalog_instance_uuidv4": self.sender_catalog_instance_uuidv4,
            "repository_uuidv4": self.repository_uuidv4,
            "selection_scope": self.selection_scope.to_dict(),
            "core": self.core,
            "context": self.context,
        }


@dataclass(frozen=True)
class ExchangeImportReport:
    """Structured report of importing an ExchangePackage."""

    package_id: str
    package_digest_sha256: str
    sender_catalog_instance_uuidv4: str
    repository_uuidv4: str
    core_imported: bool
    context_imported: bool
    idempotent_replay: bool
    admitted_core_objects: int
    admitted_retained_metadata: int
    admitted_note_roles: int
    admitted_retained_notes: int
    ignored_unverified_intrinsic_claims: int
    ignored_unverified_intrinsic_groups: int
    admitted_context_resources: int
    linked_core_references: int
    pending_core_references: int


def validate_package_envelope(package: ExchangePackage) -> None:
    """Validate Exchange envelope metadata, section keys, and retention purpose."""
    if package.format != FORMAT:
        raise ExchangeError("UNSUPPORTED_FORMAT", package.format, f"expected {FORMAT}")
    try:
        uuid4_value(package.package_id)
        uuid4_value(package.sender_catalog_instance_uuidv4)
        uuid4_value(package.repository_uuidv4)
        validate_epoch_us(package.exported_at_us)
    except (ValueError, TypeError, CoreFailure) as exc:
        raise ExchangeError("ENVELOPE_IDENTITY", package.package_id, str(exc)) from exc
    if not isinstance(package.selection_scope, ExchangeSelectionScope):
        raise ExchangeError(
            "INVALID_SELECTION", package.package_id, "ExchangeSelectionScope required"
        )
    if package.core is not None:
        if not isinstance(package.core, dict) or set(package.core.keys()) != set(
            CORE_SECTION_KEYS
        ):
            raise ExchangeError(
                "MALFORMED_CORE_SECTION",
                package.package_id,
                "core section must contain exact CORE_SECTION_KEYS",
            )
        for key, items in package.core.items():
            if not isinstance(items, list) or any(
                not isinstance(item, dict) for item in items
            ):
                raise ExchangeError(
                    "MALFORMED_CORE_SECTION",
                    key,
                    "core section entry must be a list of dicts",
                )
        for meta in package.core["retained_metadata"]:
            native_type = meta.get("native_type")
            if native_type == "blob":
                oid = OID(
                    str(meta.get("object_format", "sha1")),
                    str(meta.get("full_oid", "0" * 40)),
                )
                raise CoreFailure(
                    "RETENTION_PURPOSE",
                    oid,
                    "ordinary file blob bodies are excluded from retained_metadata",
                )
            if native_type not in ("commit", "tree", "tag"):
                raise ExchangeError(
                    "INVALID_NATIVE_TYPE",
                    native_type,
                    "retained_metadata requires commit, tree, or tag",
                )
    if package.context is not None:
        if not isinstance(package.context, dict) or set(package.context.keys()) != set(
            CONTEXT_SECTION_KEYS
        ):
            raise ExchangeError(
                "MALFORMED_CONTEXT_SECTION",
                package.package_id,
                "context section must contain exact CONTEXT_SECTION_KEYS",
            )
        for key, items in package.context.items():
            if not isinstance(items, list) or any(
                not isinstance(item, dict) for item in items
            ):
                raise ExchangeError(
                    "MALFORMED_CONTEXT_SECTION",
                    key,
                    "context section entry must be a list of dicts",
                )


def encode_package(package: ExchangePackage) -> str:
    """Serialize an ExchangePackage into canonical deterministic JSON."""
    validate_package_envelope(package)
    return encode(package.to_dict())


def decode_package(
    raw: str | bytes | dict[str, Any] | ExchangePackage,
) -> ExchangePackage:
    """Parse and validate an ExchangePackage from JSON bytes, str, or dict."""
    if isinstance(raw, ExchangePackage):
        validate_package_envelope(raw)
        return raw
    if isinstance(raw, (str, bytes)):
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            data = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise ExchangeError("MALFORMED_JSON", "package", str(exc)) from exc
    elif isinstance(raw, dict):
        data = raw
    else:
        raise ExchangeError("MALFORMED_JSON", "package", "unsupported package input")
    if not isinstance(data, dict):
        raise ExchangeError("MALFORMED_JSON", "package", "JSON object required")
    required = {
        "format",
        "package_id",
        "exported_at_us",
        "sender_catalog_instance_uuidv4",
        "repository_uuidv4",
        "selection_scope",
        "core",
        "context",
    }
    if set(data.keys()) != required:
        raise ExchangeError(
            "MALFORMED_ENVELOPE",
            "package",
            f"unexpected or missing envelope keys: {sorted(data.keys())}",
        )
    selection = ExchangeSelectionScope.from_dict(data["selection_scope"])
    return ExchangePackage(
        format=data["format"],
        package_id=data["package_id"],
        exported_at_us=data["exported_at_us"],
        sender_catalog_instance_uuidv4=data["sender_catalog_instance_uuidv4"],
        repository_uuidv4=data["repository_uuidv4"],
        selection_scope=selection,
        core=data["core"],
        context=data["context"],
    )


def package_digest_sha256(package: ExchangePackage | str | bytes) -> str:
    """Compute canonical UTF-8 SHA-256 digest of the ExchangePackage."""
    decoded = decode_package(package)
    canonical_bytes = encode_package(decoded).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()
