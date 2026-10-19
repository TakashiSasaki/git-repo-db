"""P5 portable typed Exchange domain and wire contract (`git-repo-db/adr0030-exchange-v4`).

Enforces strict separation between:
- Transport envelope identity (`package_id`, `exported_at_us`, `sender_catalog_instance_uuidv4`)
- Durable domain identity and original observation provenance
- Sender-attributed reports vs. receiver-validated byte/proof artifacts
"""

from __future__ import annotations

import hashlib
import json
import math
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from repo_catalog.domain.context_registration import (
    RegistrationError,
    validate_exchange_registrations,
)
from repo_catalog.domain.p1_context import ResourceKey
from repo_catalog.domain.p1_core import OID, CoreFailure, uuid4_value
from repo_catalog.domain.time import validate_observation_us

FORMAT = "git-repo-db/adr0030-exchange-v4"
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_DEPTH = 32
MAX_ELEMENTS = 200_000
_WIRE_WORK = ContextVar("p5_wire_work", default=None)


def _bounded_json(value: Any) -> tuple[int, int]:
    """Bound all inputs, including already decoded caller-owned dictionaries."""
    pending = [(value, 0)]
    count = 0
    size = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_ELEMENTS:
            raise ExchangeError("INPUT_LIMIT", "package", "JSON depth/elements")
        if isinstance(item, dict):
            if any(type(key) is not str for key in item):
                raise ExchangeError("MALFORMED_JSON", "package", "string keys required")
            if len(item) > MAX_ELEMENTS - count:
                raise ExchangeError("INPUT_LIMIT", "package", "JSON elements")
            pending.extend((v, depth + 1) for v in item.values())
            for key, value in item.items():
                if key.endswith("_json") and isinstance(value, str):
                    pending.append((_parse_json(value), depth + 1))
                if key == "body_hex" and (
                    type(value) is not str
                    or len(value) % 2
                    or any(c not in "0123456789abcdef" for c in value)
                ):
                    raise ExchangeError(
                        "MALFORMED_BYTES", key, "lowercase contiguous hex required"
                    )
            size += sum(len(k) for k in item)
        elif isinstance(item, (list, tuple)):
            if len(item) > MAX_ELEMENTS - count:
                raise ExchangeError("INPUT_LIMIT", "package", "JSON elements")
            pending.extend((v, depth + 1) for v in item)
        elif isinstance(item, str):
            size += len(item)
        elif type(item) is float and not math.isfinite(item):
            raise ExchangeError(
                "MALFORMED_JSON", "package", "finite JSON real required"
            )
        elif item is not None and type(item) not in (int, bool, float):
            raise ExchangeError("MALFORMED_JSON", "package", "unsupported JSON value")
        if size > MAX_PACKAGE_BYTES:
            raise ExchangeError("INPUT_LIMIT", "package", "JSON string bytes")
    measurement = _WIRE_WORK.get()
    if measurement is not None:
        measurement["metadata_units"] += count
    return count, size


def _parse_json(text: str) -> Any:
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise ExchangeError("INPUT_LIMIT", "package", "JSON depth")
        elif char in "]}":
            depth -= 1

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ExchangeError("MALFORMED_JSON", key, "duplicate key")
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=unique_pairs)
    except (ValueError, TypeError, RecursionError) as error:
        raise ExchangeError("MALFORMED_JSON", "package", str(error)) from error


def _canonical_content(package: ExchangePackage) -> bytes:
    data = package.to_dict()
    data.pop("digest_sha256")
    _bounded_json(data)
    try:
        result = json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ExchangeError("MALFORMED_JSON", "package", str(exc)) from exc
    if len(result) > MAX_PACKAGE_BYTES:
        raise ExchangeError("INPUT_LIMIT", "package", "canonical UTF-8 bytes")
    return result


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
    "resource_repository_relations",
    "repository_mapping_dispositions",
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
    repository_uuidv4s: tuple[str, ...] | None = None
    all_selected: bool = False
    max_depth: int = 8
    max_units: int = 10000
    max_bytes: int = 16 * 1024 * 1024
    max_work: int = 10000000
    object_oids: tuple[OID, ...] | None = None
    notes_refs: tuple[str, ...] | None = None
    resource_keys: tuple[ResourceKey, ...] | None = None
    source_uuidv4s: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        for value in (
            self.all_selected,
            self.include_core,
            self.include_context,
            self.include_retained_bytes,
        ):
            if type(value) is not bool:
                raise ExchangeError(
                    "INVALID_SELECTION",
                    "selection_scope",
                    "strict boolean flags required",
                )
        for value in (self.max_depth, self.max_units, self.max_bytes, self.max_work):
            if type(value) is not int or not 0 <= value <= 100000000:
                raise ExchangeError(
                    "INVALID_SELECTION", "bounds", "finite nonnegative integer required"
                )
        for values, kind in (
            (self.repository_uuidv4s, str),
            (self.object_oids, OID),
            (self.resource_keys, ResourceKey),
            (self.notes_refs, str),
            (self.source_uuidv4s, str),
        ):
            if values is not None and (
                not isinstance(values, tuple)
                or any(not isinstance(value, kind) for value in values)
            ):
                raise ExchangeError(
                    "INVALID_SELECTION", "selection_scope", "typed tuple required"
                )
        for value in (*(self.source_uuidv4s or ()), *(self.repository_uuidv4s or ())):
            uuid4_value(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_uuidv4s": None
            if self.repository_uuidv4s is None
            else sorted(set(self.repository_uuidv4s)),
            "all_selected": self.all_selected,
            "max_depth": self.max_depth,
            "max_units": self.max_units,
            "max_bytes": self.max_bytes,
            "max_work": self.max_work,
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
        for key in ("include_core", "include_context", "include_retained_bytes"):
            if type(data.get(key)) is not bool:
                raise ExchangeError("INVALID_SELECTION", key, "boolean required")
        if set(data) != {
            "repository_uuidv4s",
            "all_selected",
            "max_depth",
            "max_units",
            "max_bytes",
            "max_work",
            "include_core",
            "include_context",
            "include_retained_bytes",
            "object_oids",
            "notes_refs",
            "resource_keys",
            "source_uuidv4s",
        }:
            raise ExchangeError(
                "INVALID_SELECTION", "selection_scope", "exact keys required"
            )
        for key in ("object_oids", "notes_refs", "resource_keys", "source_uuidv4s"):
            if data[key] is not None and not isinstance(data[key], list):
                raise ExchangeError("INVALID_SELECTION", key, "array or null required")
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
            refs = None if raw_refs is None else tuple(raw_refs)
            rks = (
                None
                if raw_rks is None
                else tuple(ResourceKey(item[0], item[1], item[2]) for item in raw_rks)
            )
            srcs = None if raw_srcs is None else tuple(uuid4_value(s) for s in raw_srcs)
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
            repository_uuidv4s=None
            if data["repository_uuidv4s"] is None
            else tuple(data["repository_uuidv4s"]),
            all_selected=data["all_selected"],
            max_depth=data["max_depth"],
            max_units=data["max_units"],
            max_bytes=data["max_bytes"],
            max_work=data["max_work"],
        )


def empty_core_section() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in CORE_SECTION_KEYS}


def empty_context_section() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in CONTEXT_SECTION_KEYS}


@dataclass(frozen=True)
class ExchangePackage:
    """Portable typed Exchange package (`git-repo-db/adr0030-exchange-v4`)."""

    package_id: str
    exported_at_us: int | None
    sender_catalog_instance_uuidv4: str
    repository_uuidv4: str
    selection_scope: ExchangeSelectionScope = field(
        default_factory=ExchangeSelectionScope
    )
    core: dict[str, list[dict[str, Any]]] | None = None
    context: dict[str, list[dict[str, Any]]] | None = None
    selection_report: dict[str, Any] = field(default_factory=dict)
    format: str = FORMAT
    digest_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.digest_sha256 is None:
            object.__setattr__(
                self,
                "digest_sha256",
                hashlib.sha256(_canonical_content(self)).hexdigest(),
            )
        validate_package_envelope(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "digest_sha256": self.digest_sha256,
            "package_id": self.package_id,
            "exported_at_us": self.exported_at_us,
            "sender_catalog_instance_uuidv4": self.sender_catalog_instance_uuidv4,
            "repository_uuidv4": self.repository_uuidv4,
            "selection_scope": self.selection_scope.to_dict(),
            "selection_report": self.selection_report,
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
    omissions: tuple[dict[str, Any], ...] = ()
    core_checkpoint: bool = False
    context_checkpoint: bool = False


def validate_package_envelope(package: ExchangePackage) -> None:
    """Validate Exchange envelope metadata, section keys, and retention purpose."""
    content = _canonical_content(package)
    actual = hashlib.sha256(content).hexdigest()
    measurement = _WIRE_WORK.get()
    if measurement is not None:
        measurement["verification_bytes"] += len(content)
    if package.digest_sha256 != actual:
        raise ExchangeError(
            "DIGEST_MISMATCH",
            package.package_id,
            "declared SHA-256 differs from canonical content",
        )
    if package.format != FORMAT:
        raise ExchangeError("UNSUPPORTED_FORMAT", package.format, f"expected {FORMAT}")
    try:
        uuid4_value(package.package_id)
        uuid4_value(package.sender_catalog_instance_uuidv4)
        uuid4_value(package.repository_uuidv4)
        validate_observation_us(package.exported_at_us)
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

        try:
            validate_exchange_registrations(package.context)
        except RegistrationError as error:
            # Do not expose untrusted configuration values through diagnostics.
            raise ExchangeError(
                "CONTEXT_REGISTRATION", error.kind, error.code
            ) from None

    from repo_catalog.domain.exchange_rows import validate_rows

    validate_rows(package.core, package.context)


def encode_package(package: ExchangePackage) -> str:
    """Serialize an ExchangePackage into canonical deterministic JSON."""
    validate_package_envelope(package)
    result = json.dumps(
        package.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(result.encode("utf-8")) > MAX_PACKAGE_BYTES:
        raise ExchangeError("INPUT_LIMIT", "package", "UTF-8 wire bytes")
    return result


def decode_package(
    raw: str | bytes | dict[str, Any] | ExchangePackage,
) -> ExchangePackage:
    """Parse and validate an ExchangePackage from JSON bytes, str, or dict."""
    if isinstance(raw, ExchangePackage):
        validate_package_envelope(raw)
        return raw
    if isinstance(raw, (str, bytes)):
        if len(raw) > MAX_PACKAGE_BYTES:
            raise ExchangeError("INPUT_LIMIT", "package", "wire size")
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if len(text.encode("utf-8")) > MAX_PACKAGE_BYTES:
                raise ExchangeError("INPUT_LIMIT", "package", "UTF-8 wire bytes")
            data = _parse_json(text)
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
        "digest_sha256",
        "package_id",
        "exported_at_us",
        "sender_catalog_instance_uuidv4",
        "repository_uuidv4",
        "selection_scope",
        "selection_report",
        "core",
        "context",
    }
    if set(data.keys()) != required:
        raise ExchangeError(
            "MALFORMED_ENVELOPE",
            "package",
            f"unexpected or missing envelope keys: {sorted(data.keys())}",
        )
    _bounded_json(data)
    if type(data["digest_sha256"]) is not str or len(data["digest_sha256"]) != 64:
        raise ExchangeError("DIGEST_MISMATCH", "package", "declared SHA-256 required")
    selection = ExchangeSelectionScope.from_dict(data["selection_scope"])
    return ExchangePackage(
        format=data["format"],
        digest_sha256=data["digest_sha256"],
        package_id=data["package_id"],
        exported_at_us=data["exported_at_us"],
        sender_catalog_instance_uuidv4=data["sender_catalog_instance_uuidv4"],
        repository_uuidv4=data["repository_uuidv4"],
        selection_scope=selection,
        selection_report=data["selection_report"],
        core=data["core"],
        context=data["context"],
    )


def package_digest_sha256(package: ExchangePackage | str | bytes) -> str:
    """Compute canonical UTF-8 SHA-256 digest of the ExchangePackage."""
    decoded = decode_package(package)
    canonical_bytes = _canonical_content(decoded)
    return hashlib.sha256(canonical_bytes).hexdigest()
