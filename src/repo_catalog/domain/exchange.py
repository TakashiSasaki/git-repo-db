"""P5 portable typed Exchange domain and wire contract (`git-repo-db/adr0031-exchange-v5`).

Enforces strict separation between:
- Transport envelope identity (`package_id`, `exported_at_us`, `sender_catalog_instance_uuidv4`)
- Durable domain identity and original observation provenance
- Sender-attributed reports vs. receiver-validated byte/proof artifacts
"""

from __future__ import annotations

import copy
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
from repo_catalog.domain.resource_identity import parse_identity
from repo_catalog.domain.time import validate_observation_us

FORMAT = "git-repo-db/adr0031-exchange-v5"
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_DEPTH = 32
MAX_ELEMENTS = 200_000
_WIRE_WORK = ContextVar("p5_wire_work", default=None)


def _quoted_size(value, remaining):
    """Bound escaped UTF-8 before building a whole canonical representation."""
    if len(value) > remaining:
        raise ExchangeError("INPUT_LIMIT", "package", "JSON string bytes")
    total = 2
    for offset in range(0, len(value), 4096):
        try:
            total += len(
                json.dumps(value[offset : offset + 4096], ensure_ascii=False)[
                    1:-1
                ].encode("utf-8")
            )
        except UnicodeError as error:
            raise ExchangeError("MALFORMED_JSON", "package", "invalid UTF-8") from error
        if total > remaining:
            raise ExchangeError("INPUT_LIMIT", "package", "escaped UTF-8 bytes")
    return total


def _bounded_json(value: Any, *, root: str = "generic", spend=None) -> tuple[int, int]:
    """Bound caller-owned JSON before allocation, optionally reserving work.

    ``spend`` reserves visited values, queued references and examined characters
    before their associated operation. It may stop the scan immediately. The
    returned element count remains the wire hard-cap counter, not this request's
    character-inclusive work counter.
    """

    def reserve(amount=1):
        if spend is not None:
            spend(amount)

    pending = [(value, 0, False, root)]
    active = set()
    count = 0
    size = 0
    try:
        while pending:
            reserve()
            item, depth, exiting, role = pending.pop()
            if exiting:
                active.remove(id(item))
                continue
            if type(item) in (dict, list):
                if id(item) in active:
                    raise ExchangeError(
                        "MALFORMED_JSON", "package", "cyclic JSON input"
                    )
                active.add(id(item))
                pending.append((item, depth, True, role))
            count += 1
            if depth > MAX_DEPTH or count > MAX_ELEMENTS:
                raise ExchangeError("INPUT_LIMIT", "package", "JSON depth/elements")
            if type(item) is dict:
                # Each object member contributes both its key and its value.
                # Refuse a necessarily oversize object before queuing children.
                if 2 * len(item) > MAX_ELEMENTS - count:
                    raise ExchangeError("INPUT_LIMIT", "package", "JSON elements")
                reserve(len(item))
                if any(type(key) is not str for key in item):
                    raise ExchangeError(
                        "MALFORMED_JSON", "package", "string keys required"
                    )
                count += len(item)
                size += 2 + max(0, len(item) - 1) + len(item)
                for key in item:
                    reserve(1 + len(key))
                    size += _quoted_size(key, MAX_PACKAGE_BYTES - size)
                    count += max(0, (len(key) - 1) // 4096)
                    if count > MAX_ELEMENTS:
                        raise ExchangeError("INPUT_LIMIT", "package", "JSON elements")
                for identity, relative_depth in _embedded_identity_values(
                    item, role, spend=spend
                ):
                    reserve()
                    pending.append((identity, depth + relative_depth, False, "generic"))
                reserve(len(item))
                for key, entry in item.items():
                    child_role = _wire_child_role(role, key, item)
                    pending.append((entry, depth + 1, False, "generic"))
                    if key.endswith("_json") and isinstance(entry, str):
                        # Reserve both the escaping pass and full lexical/JSON
                        # parse before either touches the embedded text.
                        reserve(2 * (1 + len(entry)))
                        _quoted_size(entry, MAX_PACKAGE_BYTES - size)
                        pending.append(
                            (_parse_json(entry), depth + 1, False, child_role)
                        )
                    elif type(entry) in (list, dict):
                        # Only one traversal: a decoded container carries its role
                        # directly; embedded JSON strings have a separate parse.
                        pending[-1] = (entry, depth + 1, False, child_role)
                    if key == "body_hex" and type(entry) is str:
                        reserve(1 + len(entry))
                    if key == "body_hex" and (
                        type(entry) is not str
                        or len(entry) > MAX_PACKAGE_BYTES
                        or len(entry) % 2
                        or any(c not in "0123456789abcdef" for c in entry)
                    ):
                        raise ExchangeError(
                            "MALFORMED_BYTES", key, "lowercase contiguous hex required"
                        )
            elif type(item) is list:
                if len(item) > MAX_ELEMENTS - count:
                    raise ExchangeError("INPUT_LIMIT", "package", "JSON elements")
                for identity, relative_depth in _embedded_identity_values(
                    item, role, spend=spend
                ):
                    reserve()
                    pending.append((identity, depth + relative_depth, False, "generic"))
                child_role = (
                    "row:" + role[5:]
                    if role.startswith("rows:")
                    else "transfer_support_entry"
                    if role == "transfer_supports"
                    else "generic"
                )
                reserve(len(item))
                pending.extend((v, depth + 1, False, child_role) for v in item)
                size += 2 + max(0, len(item) - 1)
            elif type(item) is str:
                reserve(1 + len(item))
                size += _quoted_size(item, MAX_PACKAGE_BYTES - size)
                count += max(0, (len(item) - 1) // 4096)
            elif type(item) is float and not math.isfinite(item):
                raise ExchangeError(
                    "MALFORMED_JSON", "package", "finite JSON real required"
                )
            elif item is not None and type(item) not in (int, bool, float):
                raise ExchangeError(
                    "MALFORMED_JSON", "package", "unsupported JSON value"
                )
            else:
                try:
                    size += len(json.dumps(item, allow_nan=False))
                except (ValueError, TypeError) as error:
                    raise ExchangeError(
                        "MALFORMED_JSON", "package", "bounded JSON number required"
                    ) from error
            if count > MAX_ELEMENTS:
                raise ExchangeError("INPUT_LIMIT", "package", "JSON elements")
            if size > MAX_PACKAGE_BYTES:
                raise ExchangeError("INPUT_LIMIT", "package", "JSON string bytes")
    finally:
        # Rejected input still consumed actual parsing/traversal work. Neither
        # refusal nor a caller's transaction rollback refunds that work.
        measurement = _WIRE_WORK.get()
        if measurement is not None:
            measurement["metadata_units"] += count
    return count, size


def _wire_child_role(role, key, row):
    """Carry only contract-declared positions through the generic JSON scan."""
    if role == "package":
        return {"context": "context", "selection_scope": "selection"}.get(
            key, "generic"
        )
    if role == "context" and key in CONTEXT_SECTION_KEYS:
        return "rows:" + key
    if role == "selection" and key == "resource_keys":
        return "resource_members"
    if role.startswith("row:"):
        section = role[4:]
        if key == "members_json" and (
            section in ("resource_relations", "collections")
            or section == "coverage_proofs"
            and row.get("proof_kind") == "collection"
        ):
            return "resource_members"
        if (
            key == "event_report_members_json"
            and section == "resource_repository_relations"
        ):
            return "resource_members"
        if key == "owner_coordinates_json" and row.get("owner_kind") in (
            "resource",
            "field",
            "collection",
        ):
            return "coverage_coordinates"
        if key == "scope_json" and section == "resource_relations":
            return {
                "transfer_event_report": "transfer_scope",
                "provider_repository_roles": "provider_roles_scope",
            }.get(row.get("relation_kind"), "generic")
        if (
            key == "event_report_scope_json"
            and section == "resource_repository_relations"
        ):
            return "transfer_scope"
        if key.endswith("provenance_json") and (
            section
            in (
                "resource_repository_relations",
                "repository_mapping_dispositions",
                "mapping_claims",
            )
            or section == "resource_relations"
            and row.get("relation_kind") == "transfer_event_report"
        ):
            return "provenance"
    if role == "transfer_scope" and key == "parent_members_json":
        return "resource_members"
    if role == "provider_roles_scope" and key == "repository_roles":
        return "provider_role_map"
    if role == "provider_role_map":
        return "provider_role_entry"
    if role == "provenance" and key == "evidence":
        return "mapping_evidence"
    if role == "mapping_evidence":
        return {
            "mapping_support": "mapping_support",
            "transfer_mapping_supports": "transfer_supports",
        }.get(key, "generic")
    if role == "transfer_support_entry" and key == "mapping_support":
        return "mapping_support"
    if role == "mapping_support" and key == "supporting_claims":
        return "rows:mapping_claims"
    return "generic"


def _embedded_identity_values(value, role, *, spend=None):
    """Expose decoded typed keys to aggregate caps without inspecting evidence shape."""

    def identity(text, depth, kind=None):
        try:
            if spend is not None:
                spend(1 + len(text))
            native = parse_identity(text)
            yield native, depth
            # Reserved scoped kinds explicitly parse their namespace identity;
            # Documents use their separate declaration and never shape inference.
            if (
                kind in ("review", "comment", "thread")
                and type(native) is list
                and len(native) == 4
            ):
                if spend is not None:
                    spend(1 + len(native[1]))
                yield parse_identity(native[1]), depth + 1
        except (ValueError, TypeError) as error:
            raise ExchangeError(
                "INVALID_IDENTIFICATION", "identity", "invalid canonical identity"
            ) from error

    if role.startswith("row:") and type(value) is dict:
        if "provider_resource_id" in value:
            yield from identity(
                value["provider_resource_id"], 1, value.get("resource_kind")
            )
        if role == "row:resources":
            if value.get("identifier_namespace_id") is not None:
                yield from identity(
                    value["identifier_namespace_id"],
                    1,
                    value.get("identifier_namespace_kind"),
                )
            if value.get("provider_document_id") is not None:
                yield from identity(value["provider_document_id"], 1)
    elif role == "resource_members" and type(value) is list:
        if spend is not None:
            spend(len(value))
        for member in value:
            if type(member) is list and len(member) == 3:
                yield from identity(member[2], 2, member[1])
    elif role == "coverage_coordinates" and type(value) is list and len(value) >= 3:
        yield from identity(value[2], 1, value[1])
    elif role == "transfer_scope" and type(value) is dict:
        for name in ("from_provider_repository_id", "to_provider_repository_id"):
            if value.get(name) is not None:
                yield from identity(value[name], 1, "repository")
    elif role in ("mapping_support", "provider_role_entry") and type(value) is dict:
        if value.get("provider_repository_id") is not None:
            yield from identity(value["provider_repository_id"], 1, "repository")


def _parse_json(text: str) -> Any:
    depth = 0
    quoted = escaped = False
    tokens = 0
    atom = False
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
            tokens += 1
            atom = False
        elif char in "[{":
            tokens += 1
            atom = False
            depth += 1
            if depth > MAX_DEPTH:
                raise ExchangeError("INPUT_LIMIT", "package", "JSON depth")
        elif char in "]}":
            depth -= 1
            atom = False
        elif char in ",: \t\r\n":
            atom = False
        elif not atom:
            tokens += 1
            atom = True
        if tokens > MAX_ELEMENTS:
            raise ExchangeError("INPUT_LIMIT", "package", "JSON lexical elements")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ExchangeError("MALFORMED_JSON", key, "duplicate key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError("nonfinite JSON number")

    try:
        return json.loads(
            text,
            object_pairs_hook=unique_pairs,
            parse_constant=reject_constant,
        )
    except (ValueError, TypeError, RecursionError) as error:
        raise ExchangeError("MALFORMED_JSON", "package", str(error)) from error


def _canonical_content(package: ExchangePackage) -> bytes:
    return _canonical_dictionary(package.to_dict())


def _canonical_dictionary(data: dict[str, Any]) -> bytes:
    """Encode the received or authored dictionary with one checksum profile."""
    # The digest is excluded from the checksum, never from wire limits. A
    # package emitted at the inclusive cap must remain readable by this codec.
    _bounded_json(data, root="package")
    try:
        result = json.dumps(
            {key: value for key, value in data.items() if key != "digest_sha256"},
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
        if (
            self.max_depth > MAX_DEPTH
            or self.max_bytes > MAX_PACKAGE_BYTES
            or self.max_units > MAX_ELEMENTS
        ):
            raise ExchangeError(
                "INVALID_SELECTION", "bounds", "outer hard cap exceeded"
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
                or any(type(value) is not kind for value in values)
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
        if type(data) is not dict:
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
        for key in (
            "repository_uuidv4s",
            "object_oids",
            "notes_refs",
            "resource_keys",
            "source_uuidv4s",
        ):
            if data[key] is not None and type(data[key]) is not list:
                raise ExchangeError("INVALID_SELECTION", key, "array or null required")
        for key, size in (("object_oids", 2), ("resource_keys", 3)):
            if data[key] is not None and any(
                type(item) is not list
                or len(item) != size
                or any(type(value) is not str for value in item)
                for item in data[key]
            ):
                raise ExchangeError(
                    "INVALID_SELECTION", key, "exact typed coordinates required"
                )
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
        result = cls(
            include_core=data["include_core"],
            include_context=data["include_context"],
            include_retained_bytes=data["include_retained_bytes"],
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
        # Local typed selection construction may canonicalize its sets when
        # authoring a package. Received selections must already use that exact
        # representation: a matching checksum does not authorize input repair.
        if result.to_dict() != data:
            raise ExchangeError(
                "INVALID_SELECTION",
                "selection_scope",
                "canonical unique set arrays required",
            )
        return result


def empty_core_section() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in CORE_SECTION_KEYS}


def empty_context_section() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in CONTEXT_SECTION_KEYS}


@dataclass(frozen=True)
class ExchangePackage:
    """Portable typed Exchange package (`git-repo-db/adr0031-exchange-v5`)."""

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
        if self.format != FORMAT:
            raise ExchangeError(
                "UNSUPPORTED_WIRE_VERSION", "format", f"expected {FORMAT}"
            )
        if not isinstance(self.selection_scope, ExchangeSelectionScope):
            raise ExchangeError(
                "INVALID_SELECTION", "selection_scope", "typed scope required"
            )
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
    if package.format != FORMAT:
        raise ExchangeError("UNSUPPORTED_WIRE_VERSION", "format", f"expected {FORMAT}")
    if type(package.selection_report) is not dict:
        raise ExchangeError("MALFORMED_ENVELOPE", "selection_report", "object required")
    if not isinstance(package.selection_scope, ExchangeSelectionScope):
        raise ExchangeError(
            "INVALID_SELECTION", "selection_scope", "typed scope required"
        )
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
                type(item) is not dict for item in items
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
                type(item) is not dict for item in items
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

    from repo_catalog.domain.exchange_rows import (
        validate_replay_consistency,
        validate_rows,
    )

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
    """Validate a v5 envelope, checksum, exact row grammar and key canonicality.

    Envelope decoding grants no admission authority. ``decode_context_v5`` adds
    pure typed Context semantic checks; planner/current authorized admission
    separately resolve exact dependencies and receiver-local eligibility.
    """
    if isinstance(raw, ExchangePackage):
        raw = raw.to_dict()
    if isinstance(raw, (str, bytes)):
        if len(raw) > MAX_PACKAGE_BYTES:
            raise ExchangeError("INPUT_LIMIT", "package", "wire size")
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if len(text.encode("utf-8")) > MAX_PACKAGE_BYTES:
                raise ExchangeError("INPUT_LIMIT", "package", "UTF-8 wire bytes")
            data = _parse_json(text)
        except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
            raise ExchangeError("MALFORMED_JSON", "package", str(exc)) from exc
    elif isinstance(raw, dict):
        _bounded_json(raw, root="package")
        data = copy.deepcopy(raw)
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
    if data.get("format") != FORMAT:
        raise ExchangeError("UNSUPPORTED_WIRE_VERSION", "format", f"expected {FORMAT}")
    if set(data.keys()) != required:
        raise ExchangeError(
            "MALFORMED_ENVELOPE",
            "package",
            f"unexpected or missing envelope keys: {sorted(data.keys())}",
        )
    content = _canonical_dictionary(data)
    if type(data["digest_sha256"]) is not str or len(data["digest_sha256"]) != 64:
        raise ExchangeError("DIGEST_MISMATCH", "package", "declared SHA-256 required")
    measurement = _WIRE_WORK.get()
    if measurement is not None:
        measurement["verification_bytes"] += len(content)
    if data["digest_sha256"] != hashlib.sha256(content).hexdigest():
        raise ExchangeError(
            "DIGEST_MISMATCH",
            data["package_id"],
            "declared SHA-256 differs from received canonical content",
        )
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
