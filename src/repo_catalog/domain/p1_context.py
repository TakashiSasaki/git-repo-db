"""Stable P1 Context values; independent of acquisition and SQLite adapters.

Canonical whole-value JSON is a reversible representation of genuine semantic
coordinates, never a locally assigned alias. Missing fields have no candidate;
JSON null is an explicitly observed value. Source clocks never use receipt time.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Final, Literal

from repo_catalog.domain.p1_coverage import (
    CoverageClaim as CoverageClaim,
)
from repo_catalog.domain.p1_coverage import (
    CoverageProjection as CoverageProjection,
)
from repo_catalog.domain.p1_coverage import (
    CoverageState as CoverageState,
)
from repo_catalog.domain.resource_identity import (
    IdentityValue,
    encode_identity,
    parse_identity,
)
from repo_catalog.domain.time import MAX_EPOCH_US, validate_observation_us

OwnerKind = Literal[
    "repository", "source", "resource", "collection", "field", "source_inventory"
]

RelationKind = Literal[
    "represents_repository",
    "owning_repository",
    "base_repository",
    "head_repository",
    "transfer_from_repository",
    "transfer_to_repository",
]

RELATION_KINDS: Final[tuple[RelationKind, ...]] = (
    "represents_repository",
    "owning_repository",
    "base_repository",
    "head_repository",
    "transfer_from_repository",
    "transfer_to_repository",
)

CURRENT_CANDIDATE_RELATION_KINDS: Final[tuple[RelationKind, ...]] = (
    "owning_repository",
    "base_repository",
    "head_repository",
)

MAPPING_RELATION_KINDS: Final[tuple[RelationKind, ...]] = (
    "owning_repository",
    "base_repository",
    "head_repository",
    "transfer_from_repository",
    "transfer_to_repository",
)

TRANSFER_RELATION_KINDS: Final[tuple[RelationKind, ...]] = (
    "transfer_from_repository",
    "transfer_to_repository",
)

DispositionKind = Literal["withdraw", "correct", "dispute"]
DISPOSITION_KINDS: Final[tuple[DispositionKind, ...]] = (
    "withdraw",
    "correct",
    "dispute",
)

RelationAdmissionOutcome = Literal[
    "insert",
    "duplicate",
    "stale",
    "missing_dependency",
    "omitted_by_selection",
    "permission_denied",
]
ADMISSION_OUTCOMES: Final[tuple[RelationAdmissionOutcome, ...]] = (
    "insert",
    "duplicate",
    "stale",
    "missing_dependency",
    "omitted_by_selection",
    "permission_denied",
)

SupportStatus = Literal[
    "self_binding",
    "explicit_null",
    "unresolved_provider_only",
    "active",
    "unconfirmed_disposition",
    "supporting_binding_disposed",
    "missing_supporting_binding",
    "conflicting_support",
]
SUPPORT_STATUSES: Final[tuple[SupportStatus, ...]] = (
    "self_binding",
    "explicit_null",
    "unresolved_provider_only",
    "active",
    "unconfirmed_disposition",
    "supporting_binding_disposed",
    "missing_supporting_binding",
    "conflicting_support",
)

MappingEvaluationState = Literal[
    "unmapped",
    "single_candidate",
    "contested_candidate",
    "conflict",
    "withdrawn",
    "unresolved_correction",
    "evidence_contradictory",
]

ClaimedIssuerState = Literal["omitted", "explicit_null", "present"]
TransferEndpointState = Literal[
    "absent",
    "omitted_by_selection",
    "explicit_null",
    "unresolved_provider_only",
    "resolved",
]
ProviderRoleState = Literal[
    "absent",
    "explicit_null",
    "unresolved_provider_only",
    "resolved",
]

_UUID4_RE: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)
_MAX_JSON_BYTES: Final[int] = 262_144
_MAX_JSON_DEPTH: Final[int] = 32


class _OmittedIssuerSentinel:
    def __repr__(self) -> str:
        return "OMITTED_ISSUER"


OMITTED_ISSUER: Final[object] = _OmittedIssuerSentinel()


def _is_nonempty_str(value: object) -> bool:
    return type(value) is str and len(value) > 0


def _is_uuid4_str(value: object) -> bool:
    return type(value) is str and bool(_UUID4_RE.match(value))


def _is_positive_int64(value: object) -> bool:
    return type(value) is int and 0 < value <= MAX_EPOCH_US


def _forbid_nonfinite(token: str) -> Any:
    raise ValueError(f"Non-finite JSON constant forbidden: {token}")


def _unique_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, val in pairs:
        if type(key) is not str or key in result:
            raise ValueError("Duplicate or non-string JSON object key")
        result[key] = val
    return result


def _parse_canonical_json(raw: object) -> Any:
    """Strictly parse and verify canonical JSON without coercion or lone surrogates."""
    if type(raw) is not str or not raw or len(raw) > _MAX_JSON_BYTES:
        raise ValueError("Canonical JSON value must be a bounded non-empty string")
    try:
        encoded_bytes = raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Invalid UTF-8 in JSON string") from exc
    if len(encoded_bytes) > _MAX_JSON_BYTES:
        raise ValueError("Canonical JSON exceeds maximum byte length")
    depth = 0
    quoted = escaped = False
    for char in raw:
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
            if depth > _MAX_JSON_DEPTH:
                raise ValueError("JSON nesting depth exceeded")
        elif char in "]}":
            depth -= 1
    parsed = json.loads(
        raw,
        parse_constant=_forbid_nonfinite,
        object_pairs_hook=_unique_object_pairs,
    )
    pending: list[tuple[int, Any]] = [(0, parsed)]
    count = 0
    while pending:
        cur_depth, item = pending.pop()
        if cur_depth > _MAX_JSON_DEPTH:
            raise ValueError("JSON nesting depth exceeded")
        count += 1
        if count > 4096:
            raise ValueError("JSON element count exceeded")
        if type(item) is dict:
            for k, v in item.items():
                k.encode("utf-8")
                pending.append((cur_depth + 1, v))
        elif type(item) is list:
            for v in item:
                pending.append((cur_depth + 1, v))
        elif type(item) is str:
            item.encode("utf-8")
    if canonical(parsed) != raw:
        raise ValueError("JSON is not in canonical form")
    return parsed


def canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _scoped_document_coordinates(
    provider_resource_id: str,
) -> tuple[str, str, str, IdentityValue]:
    """Decode the explicit scoped contract, never infer a semantic Parent report."""
    parsed = parse_identity(provider_resource_id)
    if (
        type(parsed) is not list
        or len(parsed) != 4
        or any(not _is_nonempty_str(item) for item in parsed[:3])
    ):
        raise ValueError(
            "Scoped identity requires namespace kind/TEXT, subtype and native ID"
        )
    namespace_kind, namespace_text, document_kind, native_id = parsed
    parse_identity(namespace_text)
    return namespace_kind, namespace_text, document_kind, native_id


def validate_timeline_event_coordinates(
    provider_resource_id: str,
) -> tuple[str, IdentityValue]:
    """Validate that a comment provider_resource_id is an issue-parented timeline_event."""
    parent_kind, parent_id, document_kind, event_id = _scoped_document_coordinates(
        provider_resource_id
    )
    if parent_kind != "issue" or document_kind != "timeline_event":
        raise ValueError(
            "Transfer relation requires an issue-parented timeline_event document coordinate"
        )
    return parent_id, event_id


def validate_relation_resource_kind(
    relation_kind: str,
    resource_kind: str,
    provider_resource_id: str | None = None,
) -> None:
    if relation_kind not in RELATION_KINDS:
        raise ValueError(f"Unknown repository relation_kind: {relation_kind!r}")
    if not _is_nonempty_str(resource_kind):
        raise ValueError("resource_kind must be a non-empty string")
    if relation_kind == "represents_repository":
        if resource_kind != "repository":
            raise ValueError(
                "represents_repository requires resource_kind == 'repository'"
            )
    elif relation_kind == "owning_repository":
        if resource_kind != "issue":
            raise ValueError("owning_repository requires resource_kind == 'issue'")
    elif relation_kind in ("base_repository", "head_repository"):
        if resource_kind != "pull_request":
            raise ValueError(
                f"{relation_kind} requires resource_kind == 'pull_request'"
            )
    elif relation_kind in TRANSFER_RELATION_KINDS:
        if resource_kind != "comment":
            raise ValueError(
                f"{relation_kind} requires resource_kind == 'comment' (issue timeline_event)"
            )
        if provider_resource_id is not None:
            validate_timeline_event_coordinates(provider_resource_id)


def validate_mapping_target(
    target_json: object, *, relation_kind: str | None = None
) -> str | None:
    """Validate canonical target_json ('null' or canonical UUIDv4 string).

    If relation_kind is supplied, enforces the role-specific NULL rule
    (represents_repository forbids 'null').
    """
    if relation_kind is not None and (
        type(relation_kind) is not str or relation_kind not in RELATION_KINDS
    ):
        raise ValueError(f"Invalid relation_kind: {relation_kind!r}")
    parsed = _parse_canonical_json(target_json)
    if parsed is None:
        if relation_kind == "represents_repository":
            raise ValueError("represents_repository forbids null target_json")
        return None
    if _is_uuid4_str(parsed):
        return parsed
    raise ValueError(
        "target_json must be canonical JSON null or a canonical lowercase UUIDv4 string"
    )


def validate_mapping_clock(clock_json: object) -> dict[str, Any]:
    parsed = _parse_canonical_json(clock_json)
    if type(parsed) is not dict or set(parsed.keys()) != {"domain", "at_us"}:
        raise ValueError("clock_json must be a canonical object with domain and at_us")
    if not _is_nonempty_str(parsed["domain"]):
        raise ValueError("clock_json.domain must be a non-empty string")
    at_us = parsed["at_us"]
    if at_us is not None and not _is_positive_int64(at_us):
        raise ValueError("clock_json.at_us must be null or a positive int64")
    return parsed


def _validate_embedded_mapping_support(support: object) -> None:
    if type(support) is not dict or set(support.keys()) != {
        "provider_repository_id",
        "supporting_claims",
    }:
        raise ValueError(
            "mapping_support must have exact keys {'provider_repository_id', 'supporting_claims'}"
        )
    if not _is_nonempty_str(support["provider_repository_id"]):
        raise ValueError(
            "mapping_support.provider_repository_id must be a non-empty string"
        )
    parse_identity(support["provider_repository_id"])
    claims = support["supporting_claims"]
    if type(claims) is not list or not claims:
        raise ValueError(
            "mapping_support.supporting_claims must be a non-empty list of MappingClaimKey objects"
        )
    seen: set[tuple[str, str, str, str, str, str, str]] = set()
    target_uuids: set[str] = set()
    for item in claims:
        if type(item) is not dict or set(item.keys()) != {
            "clock_json",
            "provenance_json",
            "provider_resource_id",
            "relation_kind",
            "resource_kind",
            "service_instance_uuidv4",
            "target_json",
        }:
            raise ValueError(
                "Each supporting_claim must contain exact 7-column MappingClaimKey coordinates"
            )
        if not _is_uuid4_str(item["service_instance_uuidv4"]):
            raise ValueError("Invalid service_instance_uuidv4 in supporting_claim")
        if (
            item["resource_kind"] != "repository"
            or item["relation_kind"] != "represents_repository"
            or item["provider_resource_id"] != support["provider_repository_id"]
        ):
            raise ValueError(
                "supporting_claim must be a represents_repository claim for provider_repository_id"
            )
        target_uuid = validate_mapping_target(
            item["target_json"], relation_kind="represents_repository"
        )
        assert target_uuid is not None
        validate_mapping_clock(item["clock_json"])
        validate_mapping_provenance(item["provenance_json"])
        coord = (
            item["service_instance_uuidv4"],
            item["resource_kind"],
            item["provider_resource_id"],
            item["relation_kind"],
            item["clock_json"],
            item["target_json"],
            item["provenance_json"],
        )
        if coord in seen:
            raise ValueError("Duplicate supporting_claim in mapping_support")
        seen.add(coord)
        target_uuids.add(target_uuid)
    if len(target_uuids) != 1:
        raise ValueError(
            "All supporting_claims in one mapping_support must support the same repository_uuidv4"
        )


def validate_mapping_provenance(provenance_json: object) -> dict[str, Any]:
    parsed = _parse_canonical_json(provenance_json)
    if type(parsed) is not dict:
        raise ValueError("provenance_json must be a canonical JSON object")
    keys = set(parsed.keys())
    if not keys.issubset({"source", "evidence", "claimed_issuer"}):
        raise ValueError("provenance_json contains unknown top-level keys")
    if "source" not in parsed or not _is_nonempty_str(parsed["source"]):
        raise ValueError("provenance_json.source must be a non-empty string")
    if "evidence" not in parsed or parsed["evidence"] is None:
        raise ValueError("provenance_json.evidence must be present and non-null")
    evidence = parsed["evidence"]
    if type(evidence) is dict and "mapping_support" in evidence:
        _validate_embedded_mapping_support(evidence["mapping_support"])
    if type(evidence) is dict and "transfer_mapping_supports" in evidence:
        if "mapping_support" in evidence:
            raise ValueError("Cannot combine singular and Transfer mapping support")
        entries = evidence["transfer_mapping_supports"]
        if type(entries) is not list or not entries:
            raise ValueError("transfer_mapping_supports must be a non-empty list")
        seen = set()
        for entry in entries:
            if type(entry) is not dict or set(entry) != {
                "relation_kind",
                "target_json",
                "mapping_support",
            }:
                raise ValueError("Invalid Transfer mapping support entry")
            if entry["relation_kind"] not in TRANSFER_RELATION_KINDS:
                raise ValueError("Transfer mapping support requires a Transfer role")
            validate_mapping_target(
                entry["target_json"], relation_kind="represents_repository"
            )
            support = MappingSupport.from_dict(entry["mapping_support"])
            if canonical(support.target_repository_uuidv4) != entry["target_json"]:
                raise ValueError("Transfer mapping support target mismatch")
            key = (entry["relation_kind"], entry["target_json"])
            if key in seen:
                raise ValueError("Duplicate Transfer mapping support coordinate")
            seen.add(key)
    if "claimed_issuer" in parsed:
        issuer = parsed["claimed_issuer"]
        if issuer is not None:
            if (
                type(issuer) is not dict
                or set(issuer.keys()) != {"namespace", "id"}
                or not _is_nonempty_str(issuer.get("namespace"))
                or not _is_nonempty_str(issuer.get("id"))
            ):
                raise ValueError(
                    "claimed_issuer must be null or {'id': <nonempty>, 'namespace': <nonempty>}"
                )
    return parsed


def p1_mapping_target(target_json: object) -> int:
    """Deterministic SQLite predicate returning 1 or 0 (never SQL NULL)."""
    try:
        validate_mapping_target(target_json)
        return 1
    except Exception:
        return 0


def p1_mapping_clock(clock_json: object) -> int:
    """Deterministic SQLite predicate returning 1 or 0 (never SQL NULL)."""
    try:
        validate_mapping_clock(clock_json)
        return 1
    except Exception:
        return 0


def p1_mapping_provenance(provenance_json: object) -> int:
    """Deterministic SQLite predicate returning 1 or 0 (never SQL NULL)."""
    try:
        validate_mapping_provenance(provenance_json)
        return 1
    except Exception:
        return 0


def represents_target_json(repository_uuidv4: str) -> str:
    if not _is_uuid4_str(repository_uuidv4):
        raise ValueError("repository_uuidv4 must be a lowercase UUIDv4 string")
    return canonical(repository_uuidv4)


def resolved_target_json(
    repository_uuidv4: str, provider_repository_id: str | None = None
) -> str:
    if provider_repository_id is not None and not _is_uuid4_str(repository_uuidv4):
        # Also allow positional (provider_repository_id, repository_uuidv4) call
        if _is_nonempty_str(repository_uuidv4) and _is_uuid4_str(
            provider_repository_id
        ):
            return canonical(provider_repository_id)
    if not _is_uuid4_str(repository_uuidv4):
        raise ValueError("repository_uuidv4 must be a lowercase UUIDv4 string")
    return canonical(repository_uuidv4)


def explicit_null_target_json() -> str:
    return "null"


def target_json_for_repository(
    repository_uuidv4: str | None, *, relation_kind: RelationKind | None = None
) -> str:
    encoded = canonical(repository_uuidv4)
    validate_mapping_target(encoded, relation_kind=relation_kind)
    return encoded


@dataclass(frozen=True)
class RelationAdmissionResult:
    outcome: RelationAdmissionOutcome
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in ADMISSION_OUTCOMES:
            raise ValueError(f"Unknown admission outcome: {self.outcome!r}")
        if self.detail is not None and not _is_nonempty_str(self.detail):
            raise ValueError("detail must be None or a non-empty string")


@dataclass(frozen=True)
class ClaimedIssuer:
    namespace: str
    id: str

    def __post_init__(self) -> None:
        if not _is_nonempty_str(self.namespace):
            raise ValueError("ClaimedIssuer.namespace must be a non-empty string")
        if not _is_nonempty_str(self.id):
            raise ValueError("ClaimedIssuer.id must be a non-empty string")

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "namespace": self.namespace}


@dataclass(frozen=True)
class MappingProvenance:
    source: str
    evidence: Any
    claimed_issuer_state: ClaimedIssuerState = "omitted"
    claimed_issuer: ClaimedIssuer | None = None

    def __post_init__(self) -> None:
        if not _is_nonempty_str(self.source):
            raise ValueError("MappingProvenance.source must be a non-empty string")
        if self.evidence is None:
            raise ValueError("MappingProvenance.evidence must not be None")
        if self.claimed_issuer_state not in ("omitted", "explicit_null", "present"):
            raise ValueError("Invalid claimed_issuer_state")
        if self.claimed_issuer_state in ("omitted", "explicit_null"):
            if self.claimed_issuer is not None:
                raise ValueError(
                    "claimed_issuer must be None when state is omitted or explicit_null"
                )
        else:
            if not isinstance(self.claimed_issuer, ClaimedIssuer):
                raise ValueError(
                    "claimed_issuer must be a ClaimedIssuer when state is present"
                )
        validate_mapping_provenance(self.encoded)

    @property
    def encoded(self) -> str:
        payload: dict[str, Any] = {
            "evidence": self.evidence,
            "source": self.source,
        }
        if self.claimed_issuer_state == "explicit_null":
            payload["claimed_issuer"] = None
        elif self.claimed_issuer_state == "present":
            assert self.claimed_issuer is not None
            payload["claimed_issuer"] = self.claimed_issuer.to_dict()
        return canonical(payload)

    @classmethod
    def from_json(cls, provenance_json: str) -> MappingProvenance:
        parsed = validate_mapping_provenance(provenance_json)
        if "claimed_issuer" not in parsed:
            return cls(
                source=parsed["source"],
                evidence=parsed["evidence"],
                claimed_issuer_state="omitted",
                claimed_issuer=None,
            )
        raw_issuer = parsed["claimed_issuer"]
        if raw_issuer is None:
            return cls(
                source=parsed["source"],
                evidence=parsed["evidence"],
                claimed_issuer_state="explicit_null",
                claimed_issuer=None,
            )
        return cls(
            source=parsed["source"],
            evidence=parsed["evidence"],
            claimed_issuer_state="present",
            claimed_issuer=ClaimedIssuer(
                namespace=raw_issuer["namespace"],
                id=raw_issuer["id"],
            ),
        )


def encode_mapping_provenance(
    source: str,
    evidence: Any,
    *,
    claimed_issuer: ClaimedIssuer | None | object = OMITTED_ISSUER,
) -> str:
    if claimed_issuer is OMITTED_ISSUER:
        return MappingProvenance(
            source=source,
            evidence=evidence,
            claimed_issuer_state="omitted",
            claimed_issuer=None,
        ).encoded
    if claimed_issuer is None:
        return MappingProvenance(
            source=source,
            evidence=evidence,
            claimed_issuer_state="explicit_null",
            claimed_issuer=None,
        ).encoded
    if not isinstance(claimed_issuer, ClaimedIssuer):
        raise ValueError(
            "claimed_issuer must be ClaimedIssuer, None, or OMITTED_ISSUER"
        )
    return MappingProvenance(
        source=source,
        evidence=evidence,
        claimed_issuer_state="present",
        claimed_issuer=claimed_issuer,
    ).encoded


def parse_mapping_provenance(provenance_json: str) -> MappingProvenance:
    return MappingProvenance.from_json(provenance_json)


@dataclass(frozen=True)
class ResourceKey:
    """Three exact coordinates; the constructor receives serialized identity TEXT.

    Use ``from_native`` for native strings/arrays. In particular, a native string
    that looks like JSON stays a string; no API guesses its representation.
    Known scoped factories retain identification namespaces, not Parent evidence.
    """

    service_instance_uuidv4: str
    resource_kind: str
    provider_resource_id: str
    # Factory intent is not an identity coordinate or a durable admission fact.
    # Existing scoped-only consumers must not reinterpret an explicitly global
    # native Document whose array happens to resemble their scoped layout.
    _document_contract: ClassVar[Literal["global", "scoped"] | None] = None

    def __post_init__(self) -> None:
        if not _is_uuid4_str(self.service_instance_uuidv4):
            raise ValueError(
                "service_instance_uuidv4 must be a lowercase UUIDv4 string"
            )
        if not _is_nonempty_str(self.resource_kind):
            raise ValueError("resource_kind must be a non-empty string")
        parse_identity(self.provider_resource_id)
        if self.resource_kind in {"review", "comment", "thread"}:
            self.scoped_document_coordinates()

    @classmethod
    def from_native(
        cls, service_instance_uuidv4: str, resource_kind: str, value: IdentityValue
    ) -> ResourceKey:
        """Encode an adapter-established native identity without normalization.

        Native ``document`` IDs select the global contract. Use ``document()``
        to declare a known scoped contract explicitly. Factory intent is only
        an in-memory guard: wire/durable identification metadata needs I2/I6.
        """
        key = cls(service_instance_uuidv4, resource_kind, encode_identity(value))
        if resource_kind == "document":
            object.__setattr__(key, "_document_contract", "global")
        return key

    @classmethod
    def global_document(
        cls, service_instance_uuidv4: str, value: IdentityValue
    ) -> ResourceKey:
        """Use a genuine Provider-global Document ID, with no invented namespace.

        This explicitly selected contract does not retry malformed scoped input.
        Production persistence of global Documents requires the later I2 DDL.
        """
        return cls.from_native(service_instance_uuidv4, "document", value)

    @classmethod
    def document(
        cls,
        parent: ResourceKey,
        resource_kind: str,
        document_kind: str,
        provider_document_id: IdentityValue,
    ) -> ResourceKey:
        """Encode scoped coordinates, with canonical namespace TEXT in slot two.

        ``provider_document_id`` is native, including recursive arrays. A caller
        holding serialized local ID TEXT must explicitly parse it first.
        """
        if not isinstance(parent, ResourceKey):
            raise ValueError("A scoped document requires a namespace ResourceKey")
        if resource_kind not in {"review", "comment", "thread", "document"}:
            raise ValueError("A document requires a typed document resource kind")
        if not _is_nonempty_str(document_kind):
            raise ValueError("document_kind must be a non-empty string")
        key = cls(
            parent.service_instance_uuidv4,
            resource_kind,
            encode_identity(
                [
                    parent.resource_kind,
                    parent.provider_resource_id,
                    document_kind,
                    provider_document_id,
                ]
            ),
        )
        object.__setattr__(key, "_document_contract", "scoped")
        return key

    @classmethod
    def timeline_event(
        cls, issue_parent: ResourceKey, provider_event_id: IdentityValue
    ) -> ResourceKey:
        if (
            not isinstance(issue_parent, ResourceKey)
            or issue_parent.resource_kind != "issue"
        ):
            raise ValueError("Timeline event requires an issue parent ResourceKey")
        return cls.document(
            issue_parent, "comment", "timeline_event", provider_event_id
        )

    def scoped_document_coordinates(self) -> tuple[str, str, str, IdentityValue]:
        """Read an explicitly known scoped identity; refuse other profiles.

        Calling this on an arbitrary/global Document does not select a scoped
        contract. Typed consumers must already require that identification form.
        No relationship or referent existence follows from these coordinates.
        """
        if self.resource_kind not in {"review", "comment", "thread", "document"}:
            raise ValueError("Resource does not have a known scoped document contract")
        if self._document_contract == "global":
            raise ValueError(
                "Explicit global Document identity cannot select a scoped contract; "
                "global persistence requires ADR 0031 I2"
            )
        return _scoped_document_coordinates(self.provider_resource_id)

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
        if not _is_nonempty_str(self.domain):
            raise ValueError("Clock domain must identify the genuine source clock")
        if self.at_us is not None:
            validate_observation_us(self.at_us)

    def encode(self) -> str:
        return canonical({"domain": self.domain, "at_us": self.at_us})

    @property
    def encoded(self) -> str:
        return self.encode()

    @classmethod
    def from_json(cls, clock_json: str) -> FieldClock:
        parsed = validate_mapping_clock(clock_json)
        return cls(domain=parsed["domain"], at_us=parsed["at_us"])


@dataclass(frozen=True)
class FieldCandidate:
    resource: ResourceKey
    field_name: str
    value_json: str
    clock: FieldClock
    provenance_json: str
    observed_at_us: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.resource, ResourceKey):
            raise ValueError("FieldCandidate.resource must be a ResourceKey")
        if not isinstance(self.clock, FieldClock):
            raise ValueError("FieldCandidate.clock must be a FieldClock")
        validate_observation_us(self.observed_at_us)
        if not _is_nonempty_str(self.field_name):
            raise ValueError("Field name must not be empty")
        if self.field_name == "repository_uuidv4":
            raise ValueError(
                "field_name='repository_uuidv4' is prohibited; "
                "use ResourceRepositoryRelation for Context repository relationships"
            )
        _parse_canonical_json(self.value_json)
        provenance = _parse_canonical_json(self.provenance_json)
        if (
            type(provenance) is not dict
            or not _is_nonempty_str(provenance.get("source"))
            or provenance.get("evidence") is None
        ):
            raise ValueError("Original field provenance must be an object")


@dataclass(frozen=True)
class RelationClaimKey:
    """Direct 7-column key of a Resource--Repository relation row:
    (ResourceKey, relation_kind, clock_json, target_json, provenance_json).
    """

    resource: ResourceKey
    relation_kind: RelationKind
    clock: FieldClock
    target_json: str
    provenance_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.resource, ResourceKey):
            raise ValueError("RelationClaimKey.resource must be a ResourceKey")
        if not isinstance(self.clock, FieldClock):
            raise ValueError("RelationClaimKey.clock must be a FieldClock")
        validate_relation_resource_kind(
            self.relation_kind,
            self.resource.resource_kind,
            self.resource.provider_resource_id,
        )
        validate_mapping_target(self.target_json, relation_kind=self.relation_kind)
        validate_mapping_clock(self.clock.encode())
        validate_mapping_provenance(self.provenance_json)
        support = self.embedded_support
        if support is not None:
            if self.relation_kind == "represents_repository":
                raise ValueError(
                    "represents_repository claim must not embed mapping_support"
                )
            if self.target_repository_uuidv4 is None:
                raise ValueError(
                    "Null target relation must not embed positive mapping_support"
                )
            if support.service_instance_uuidv4 != self.service_instance_uuidv4:
                raise ValueError(
                    "mapping_support service_instance_uuidv4 must match subject resource"
                )
            if support.target_repository_uuidv4 != self.target_repository_uuidv4:
                raise ValueError(
                    "mapping_support target_repository_uuidv4 must match relation target_json"
                )

    @property
    def service_instance_uuidv4(self) -> str:
        return self.resource.service_instance_uuidv4

    @property
    def resource_kind(self) -> str:
        return self.resource.resource_kind

    @property
    def provider_resource_id(self) -> str:
        return self.resource.provider_resource_id

    @property
    def clock_json(self) -> str:
        return self.clock.encode()

    @property
    def target_repository_uuidv4(self) -> str | None:
        val = json.loads(self.target_json)
        return val if type(val) is str else None

    @property
    def is_explicit_null_target(self) -> bool:
        return self.target_json == "null"

    @property
    def is_resolved_target(self) -> bool:
        return self.target_repository_uuidv4 is not None

    @property
    def provenance(self) -> MappingProvenance:
        return MappingProvenance.from_json(self.provenance_json)

    @property
    def claimed_issuer_state(self) -> ClaimedIssuerState:
        return self.provenance.claimed_issuer_state

    @property
    def claimed_issuer(self) -> ClaimedIssuer | None:
        return self.provenance.claimed_issuer

    @property
    def embedded_support(self) -> MappingSupport | None:
        return extract_mapping_support(
            self.provenance_json,
            relation_kind=self.relation_kind,
            target_json=self.target_json,
        )

    def coordinates(self) -> tuple[str, str, str, str, str, str, str]:
        return (
            self.resource.service_instance_uuidv4,
            self.resource.resource_kind,
            self.resource.provider_resource_id,
            self.relation_kind,
            self.clock.encode(),
            self.target_json,
            self.provenance_json,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "clock_json": self.clock.encode(),
            "provenance_json": self.provenance_json,
            "provider_resource_id": self.resource.provider_resource_id,
            "relation_kind": self.relation_kind,
            "resource_kind": self.resource.resource_kind,
            "service_instance_uuidv4": self.resource.service_instance_uuidv4,
            "target_json": self.target_json,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RelationClaimKey:
        if not isinstance(data, Mapping) or set(data.keys()) != {
            "clock_json",
            "provenance_json",
            "provider_resource_id",
            "relation_kind",
            "resource_kind",
            "service_instance_uuidv4",
            "target_json",
        }:
            raise ValueError("Invalid RelationClaimKey dictionary")
        resource = ResourceKey(
            data["service_instance_uuidv4"],
            data["resource_kind"],
            data["provider_resource_id"],
        )
        clock = FieldClock.from_json(data["clock_json"])
        if data["relation_kind"] == "represents_repository":
            return MappingClaimKey(
                resource=resource,
                relation_kind="represents_repository",
                clock=clock,
                target_json=data["target_json"],
                provenance_json=data["provenance_json"],
            )
        return cls(
            resource=resource,
            relation_kind=data["relation_kind"],
            clock=clock,
            target_json=data["target_json"],
            provenance_json=data["provenance_json"],
        )


@dataclass(frozen=True, init=False)
class MappingClaimKey(RelationClaimKey):
    """Full 7-column key restricted to a Provider repository Resource and represents_repository."""

    def __init__(
        self,
        resource: ResourceKey,
        relation_kind: RelationKind = "represents_repository",
        clock: FieldClock | None = None,
        target_json: str = "",
        provenance_json: str = "",
    ):
        if clock is None:
            raise ValueError("MappingClaimKey requires clock")
        object.__setattr__(self, "resource", resource)
        object.__setattr__(self, "relation_kind", relation_kind)
        object.__setattr__(self, "clock", clock)
        object.__setattr__(self, "target_json", target_json)
        object.__setattr__(self, "provenance_json", provenance_json)
        self.__post_init__()

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            self.resource.resource_kind != "repository"
            or self.relation_kind != "represents_repository"
        ):
            raise ValueError(
                "MappingClaimKey requires resource_kind='repository' and relation_kind='represents_repository'"
            )
        if self.target_repository_uuidv4 is None:
            raise ValueError("MappingClaimKey requires a non-null UUIDv4 target_json")

    @classmethod
    def for_repository(
        cls,
        provider_repository: ResourceKey,
        repository_uuidv4: str,
        *,
        clock: FieldClock,
        provenance_json: str,
    ) -> MappingClaimKey:
        return cls(
            resource=provider_repository,
            relation_kind="represents_repository",
            clock=clock,
            target_json=represents_target_json(repository_uuidv4),
            provenance_json=provenance_json,
        )


@dataclass(frozen=True)
class MappingSupport:
    """Finite original dependency evidence linking a resolved Core-target relation
    to the exact Provider Repository and MappingClaimKey(s) used for resolution.
    """

    provider_repository: ResourceKey
    supporting_claims: tuple[MappingClaimKey, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider_repository, ResourceKey)
            or self.provider_repository.resource_kind != "repository"
        ):
            raise ValueError(
                "MappingSupport.provider_repository must be a repository ResourceKey"
            )
        if not isinstance(self.supporting_claims, tuple):
            object.__setattr__(self, "supporting_claims", tuple(self.supporting_claims))
        if not self.supporting_claims:
            raise ValueError(
                "MappingSupport.supporting_claims must contain at least one MappingClaimKey"
            )
        seen: set[tuple[str, str, str, str, str, str, str]] = set()
        targets: set[str] = set()
        for claim in self.supporting_claims:
            if not isinstance(claim, MappingClaimKey):
                raise ValueError(
                    "MappingSupport.supporting_claims must contain MappingClaimKey instances"
                )
            if claim.resource != self.provider_repository:
                raise ValueError(
                    "Every supporting_claim must belong to MappingSupport.provider_repository"
                )
            coord = claim.coordinates()
            if coord in seen:
                raise ValueError("Duplicate MappingClaimKey in MappingSupport")
            seen.add(coord)
            assert claim.target_repository_uuidv4 is not None
            targets.add(claim.target_repository_uuidv4)
        if len(targets) != 1:
            raise ValueError(
                "All supporting_claims in MappingSupport must resolve to the same repository_uuidv4"
            )

    @property
    def service_instance_uuidv4(self) -> str:
        return self.provider_repository.service_instance_uuidv4

    @property
    def provider_repository_id(self) -> str:
        return self.provider_repository.provider_resource_id

    @property
    def target_repository_uuidv4(self) -> str:
        val = self.supporting_claims[0].target_repository_uuidv4
        assert val is not None
        return val

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_repository_id": self.provider_repository.provider_resource_id,
            "supporting_claims": [c.to_dict() for c in self.supporting_claims],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MappingSupport:
        _validate_embedded_mapping_support(dict(data))
        claims = tuple(
            MappingClaimKey(
                resource=ResourceKey(
                    item["service_instance_uuidv4"],
                    item["resource_kind"],
                    item["provider_resource_id"],
                ),
                relation_kind="represents_repository",
                clock=FieldClock.from_json(item["clock_json"]),
                target_json=item["target_json"],
                provenance_json=item["provenance_json"],
            )
            for item in data["supporting_claims"]
        )
        return cls(
            provider_repository=claims[0].resource,
            supporting_claims=claims,
        )


def encode_supported_provenance(
    source: str,
    evidence: Any,
    support: MappingSupport,
    *,
    claimed_issuer: ClaimedIssuer | None | object = OMITTED_ISSUER,
) -> str:
    """Embed finite MappingSupport into original provenance without salting or check logs."""
    if not isinstance(support, MappingSupport):
        raise ValueError("support must be a MappingSupport instance")
    if evidence is None:
        raise ValueError("evidence must not be None")
    if type(evidence) is dict:
        if "mapping_support" in evidence:
            raise ValueError("evidence already contains 'mapping_support'")
        merged_evidence: dict[str, Any] = dict(evidence)
        merged_evidence["mapping_support"] = support.to_dict()
    else:
        merged_evidence = {
            "mapping_support": support.to_dict(),
            "original_evidence": evidence,
        }
    return encode_mapping_provenance(
        source, merged_evidence, claimed_issuer=claimed_issuer
    )


def encode_transfer_supported_provenance(
    source: str,
    evidence: Any,
    supports: Iterable[tuple[RelationKind, MappingSupport]],
    *,
    claimed_issuer: ClaimedIssuer | None | object = OMITTED_ISSUER,
) -> str:
    """One original report provenance with exact support per (role, target)."""
    if evidence is None:
        raise ValueError("evidence must not be None")
    merged = (
        dict(evidence) if type(evidence) is dict else {"original_evidence": evidence}
    )
    if {"mapping_support", "transfer_mapping_supports"} & set(merged):
        raise ValueError("evidence already contains mapping support")
    entries = []
    for role, support in supports:
        if not isinstance(support, MappingSupport):
            raise ValueError("support must be a MappingSupport instance")
        entries.append(
            {
                "relation_kind": role,
                "target_json": canonical(support.target_repository_uuidv4),
                "mapping_support": support.to_dict(),
            }
        )
    merged["transfer_mapping_supports"] = sorted(
        entries, key=lambda e: (e["relation_kind"], e["target_json"])
    )
    return encode_mapping_provenance(source, merged, claimed_issuer=claimed_issuer)


def extract_mapping_support(
    provenance_json: str,
    *,
    relation_kind: RelationKind | None = None,
    target_json: str | None = None,
) -> MappingSupport | None:
    parsed = validate_mapping_provenance(provenance_json)
    evidence = parsed["evidence"]
    if type(evidence) is dict and "mapping_support" in evidence:
        return MappingSupport.from_dict(evidence["mapping_support"])
    if type(evidence) is dict and "transfer_mapping_supports" in evidence:
        if relation_kind not in TRANSFER_RELATION_KINDS or target_json is None:
            raise ValueError("Transfer mapping support requires endpoint coordinates")
        for entry in evidence["transfer_mapping_supports"]:
            if (entry["relation_kind"], entry["target_json"]) == (
                relation_kind,
                target_json,
            ):
                return MappingSupport.from_dict(entry["mapping_support"])
    return None


@dataclass(frozen=True)
class ResourceRepositoryRelation:
    resource: ResourceKey
    relation_kind: RelationKind
    clock: FieldClock
    target_json: str
    provenance_json: str
    observed_at_us: int | None = None

    def __post_init__(self) -> None:
        validate_observation_us(self.observed_at_us)
        _ = self.claim_key

    @property
    def claim_key(self) -> RelationClaimKey:
        if self.relation_kind == "represents_repository":
            return MappingClaimKey(
                resource=self.resource,
                relation_kind="represents_repository",
                clock=self.clock,
                target_json=self.target_json,
                provenance_json=self.provenance_json,
            )
        return RelationClaimKey(
            resource=self.resource,
            relation_kind=self.relation_kind,
            clock=self.clock,
            target_json=self.target_json,
            provenance_json=self.provenance_json,
        )

    @property
    def clock_json(self) -> str:
        return self.clock.encode()

    @property
    def target_repository_uuidv4(self) -> str | None:
        return self.claim_key.target_repository_uuidv4

    @property
    def is_explicit_null_target(self) -> bool:
        return self.claim_key.is_explicit_null_target

    @property
    def is_resolved_target(self) -> bool:
        return self.claim_key.is_resolved_target

    @property
    def provenance(self) -> MappingProvenance:
        return self.claim_key.provenance

    @property
    def claimed_issuer_state(self) -> ClaimedIssuerState:
        return self.claim_key.claimed_issuer_state

    @property
    def claimed_issuer(self) -> ClaimedIssuer | None:
        return self.claim_key.claimed_issuer

    @property
    def embedded_support(self) -> MappingSupport | None:
        return self.claim_key.embedded_support


@dataclass(frozen=True)
class MappingDispositionKey:
    """10-column DispositionKey:
    (MappingClaimKey, disposition_kind, disposition_clock_json, disposition_provenance_json).
    """

    claim_key: MappingClaimKey
    disposition_kind: DispositionKind
    disposition_clock: FieldClock
    disposition_provenance_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.claim_key, MappingClaimKey):
            raise ValueError(
                "MappingDispositionKey.claim_key must be a MappingClaimKey"
            )
        if self.disposition_kind not in DISPOSITION_KINDS:
            raise ValueError(f"Unknown disposition_kind: {self.disposition_kind!r}")
        if not isinstance(self.disposition_clock, FieldClock):
            raise ValueError(
                "MappingDispositionKey.disposition_clock must be a FieldClock"
            )
        validate_mapping_clock(self.disposition_clock.encode())
        validate_mapping_provenance(self.disposition_provenance_json)

    def coordinates(
        self,
    ) -> tuple[str, str, str, str, str, str, str, str, str, str]:
        return (
            *self.claim_key.coordinates(),
            self.disposition_kind,
            self.disposition_clock.encode(),
            self.disposition_provenance_json,
        )


@dataclass(frozen=True)
class MappingDisposition:
    claim_key: MappingClaimKey
    disposition_kind: DispositionKind
    disposition_clock: FieldClock
    disposition_provenance_json: str
    observed_at_us: int | None = None
    replacement_claim_key: MappingClaimKey | None = None

    def __post_init__(self) -> None:
        _ = self.disposition_key
        validate_observation_us(self.observed_at_us)
        if self.disposition_kind in ("withdraw", "dispute"):
            if self.replacement_claim_key is not None:
                raise ValueError(
                    f"{self.disposition_kind} disposition requires replacement_claim_key=None"
                )
        else:
            if not isinstance(self.replacement_claim_key, MappingClaimKey):
                raise ValueError(
                    "correct disposition requires a full replacement MappingClaimKey"
                )
            if self.replacement_claim_key.resource != self.claim_key.resource:
                raise ValueError(
                    "correct disposition replacement_claim_key must reference the same Provider repository Resource"
                )
            if self.replacement_claim_key == self.claim_key:
                raise ValueError(
                    "correct disposition replacement_claim_key must differ from subject claim_key"
                )

    @property
    def subject(self) -> MappingClaimKey:
        return self.claim_key

    @property
    def disposition_key(self) -> MappingDispositionKey:
        return MappingDispositionKey(
            claim_key=self.claim_key,
            disposition_kind=self.disposition_kind,
            disposition_clock=self.disposition_clock,
            disposition_provenance_json=self.disposition_provenance_json,
        )

    @property
    def disposition_clock_json(self) -> str:
        return self.disposition_clock.encode()

    @property
    def replacement_clock_json(self) -> str | None:
        return (
            None
            if self.replacement_claim_key is None
            else self.replacement_claim_key.clock_json
        )

    @property
    def replacement_target_json(self) -> str | None:
        return (
            None
            if self.replacement_claim_key is None
            else self.replacement_claim_key.target_json
        )

    @property
    def replacement_provenance_json(self) -> str | None:
        return (
            None
            if self.replacement_claim_key is None
            else self.replacement_claim_key.provenance_json
        )

    @property
    def disposition_provenance(self) -> MappingProvenance:
        return MappingProvenance.from_json(self.disposition_provenance_json)

    def key_coordinates(
        self,
    ) -> tuple[str, str, str, str, str, str, str, str, str, str]:
        return self.disposition_key.coordinates()


@dataclass(frozen=True)
class MappingOperationEvidence:
    """Explicit caller-supplied local evidence for evaluating Dispositions.

    ADR 0030 Q-S13=B & Q-S14: Claimed issuer equality, source='local', checksums,
    or catalog UUIDs never supply this evidence automatically. Without an explicit
    MappingOperationEvidence entry, withdrawals and corrections remain unconfirmed.
    """

    confirmed_disposition_keys: frozenset[MappingDispositionKey] = frozenset()
    contradicted_disposition_keys: frozenset[MappingDispositionKey] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.confirmed_disposition_keys, frozenset):
            object.__setattr__(
                self,
                "confirmed_disposition_keys",
                frozenset(self.confirmed_disposition_keys),
            )
        if not isinstance(self.contradicted_disposition_keys, frozenset):
            object.__setattr__(
                self,
                "contradicted_disposition_keys",
                frozenset(self.contradicted_disposition_keys),
            )
        if any(
            not isinstance(k, MappingDispositionKey)
            for k in self.confirmed_disposition_keys
        ) or any(
            not isinstance(k, MappingDispositionKey)
            for k in self.contradicted_disposition_keys
        ):
            raise ValueError(
                "MappingOperationEvidence sets must contain MappingDispositionKey instances"
            )


@dataclass(frozen=True)
class QualifiedMappingEvaluation:
    provider_repository: ResourceKey
    state: MappingEvaluationState
    active_claims: tuple[MappingClaimKey, ...]
    withdrawn_claims: tuple[MappingClaimKey, ...] = ()
    corrected_claims: tuple[MappingClaimKey, ...] = ()
    unconfirmed_dispositions: tuple[MappingDisposition, ...] = ()
    disputed_dispositions: tuple[MappingDisposition, ...] = ()
    contradictory_dispositions: tuple[MappingDisposition, ...] = ()

    @property
    def active_repository_uuidv4s(self) -> tuple[str, ...]:
        seen: list[str] = []
        for claim in self.active_claims:
            repo_id = claim.target_repository_uuidv4
            assert repo_id is not None
            if repo_id not in seen:
                seen.append(repo_id)
        return tuple(seen)


def evaluate_repository_mapping(
    provider_repository: ResourceKey,
    claims: Sequence[ResourceRepositoryRelation | MappingClaimKey],
    dispositions: Sequence[MappingDisposition],
    *,
    evidence: MappingOperationEvidence | None = None,
) -> QualifiedMappingEvaluation:
    """Evaluate represents_repository claims and Dispositions without Witness storage."""
    if (
        not isinstance(provider_repository, ResourceKey)
        or provider_repository.resource_kind != "repository"
    ):
        raise ValueError("provider_repository must be a repository ResourceKey")
    claim_keys: list[MappingClaimKey] = []
    for item in claims:
        key = item.claim_key if isinstance(item, ResourceRepositoryRelation) else item
        if not isinstance(key, MappingClaimKey) or key.resource != provider_repository:
            raise ValueError(
                "All claims must be MappingClaimKeys for provider_repository"
            )
        if key not in claim_keys:
            claim_keys.append(key)
    claim_set = set(claim_keys)
    confirmed = (
        evidence.confirmed_disposition_keys if evidence is not None else frozenset()
    )
    contradicted = (
        evidence.contradicted_disposition_keys if evidence is not None else frozenset()
    )

    unconfirmed_disp: list[MappingDisposition] = []
    disputed_disp: list[MappingDisposition] = []
    contradictory_disp: list[MappingDisposition] = []
    withdrawn_set: set[MappingClaimKey] = set()
    correction_edges: dict[MappingClaimKey, set[MappingClaimKey]] = {}
    unresolved_correction = False

    for disp in dispositions:
        if not isinstance(disp, MappingDisposition):
            raise ValueError("dispositions must contain MappingDisposition instances")
        if disp.claim_key.resource != provider_repository:
            raise ValueError("All dispositions must belong to provider_repository")
        if disp.claim_key not in claim_set:
            continue
        dkey = disp.disposition_key
        if dkey in contradicted or (dkey in confirmed and dkey in contradicted):
            contradictory_disp.append(disp)
            continue
        if disp.disposition_kind == "dispute":
            disputed_disp.append(disp)
        elif disp.disposition_kind == "withdraw":
            if dkey in confirmed:
                withdrawn_set.add(disp.claim_key)
            else:
                unconfirmed_disp.append(disp)
        elif disp.disposition_kind == "correct":
            assert disp.replacement_claim_key is not None
            correction_edges.setdefault(disp.claim_key, set()).add(
                disp.replacement_claim_key
            )
            if dkey not in confirmed:
                unconfirmed_disp.append(disp)

    # Check correction cycles and multi-target contradictory corrections
    for src, dsts in correction_edges.items():
        if len(dsts) > 1 or any(dst not in claim_set for dst in dsts):
            unresolved_correction = True
        for dst in dsts:
            visited = {src}
            cur = dst
            while cur in correction_edges:
                if cur in visited:
                    unresolved_correction = True
                    break
                visited.add(cur)
                next_targets = correction_edges[cur]
                if len(next_targets) != 1:
                    unresolved_correction = True
                    break
                cur = next(iter(next_targets))

    corrected_set: set[MappingClaimKey] = set()
    if not unresolved_correction:
        for disp in dispositions:
            if (
                disp.disposition_kind == "correct"
                and disp.disposition_key in confirmed
                and disp.disposition_key not in contradicted
                and disp.claim_key in claim_set
            ):
                corrected_set.add(disp.claim_key)

    active = tuple(
        c for c in claim_keys if c not in withdrawn_set and c not in corrected_set
    )
    withdrawn = tuple(c for c in claim_keys if c in withdrawn_set)
    corrected = tuple(c for c in claim_keys if c in corrected_set)

    distinct_targets = {c.target_repository_uuidv4 for c in active}
    if contradictory_disp:
        state: MappingEvaluationState = "evidence_contradictory"
    elif unresolved_correction:
        state = "unresolved_correction"
    elif not claim_keys:
        state = "unmapped"
    elif not active:
        state = "withdrawn"
    elif len(distinct_targets) > 1:
        state = "conflict"
    elif unconfirmed_disp or disputed_disp:
        state = "contested_candidate"
    else:
        state = "single_candidate"

    return QualifiedMappingEvaluation(
        provider_repository=provider_repository,
        state=state,
        active_claims=active,
        withdrawn_claims=withdrawn,
        corrected_claims=corrected,
        unconfirmed_dispositions=tuple(unconfirmed_disp),
        disputed_dispositions=tuple(disputed_disp),
        contradictory_dispositions=tuple(contradictory_disp),
    )


@dataclass(frozen=True)
class ResolvedRepositoryRelation:
    relation: ResourceRepositoryRelation
    support_status: SupportStatus
    supporting_bindings: tuple[MappingClaimKey, ...] = ()
    disposed_supporting_bindings: tuple[MappingClaimKey, ...] = ()
    dispositions: tuple[MappingDisposition, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.relation, ResourceRepositoryRelation):
            raise ValueError(
                "ResolvedRepositoryRelation.relation must be a ResourceRepositoryRelation"
            )
        if self.support_status not in SUPPORT_STATUSES:
            raise ValueError(f"Invalid support_status: {self.support_status!r}")
        if any(
            not isinstance(item, MappingClaimKey) for item in self.supporting_bindings
        ):
            raise ValueError("supporting_bindings must contain MappingClaimKey items")
        if any(
            not isinstance(item, MappingClaimKey)
            for item in self.disposed_supporting_bindings
        ):
            raise ValueError(
                "disposed_supporting_bindings must contain MappingClaimKey items"
            )
        if any(not isinstance(item, MappingDisposition) for item in self.dispositions):
            raise ValueError("dispositions must contain MappingDisposition items")

    @property
    def claim_key(self) -> RelationClaimKey:
        return self.relation.claim_key

    @property
    def resource(self) -> ResourceKey:
        return self.relation.resource

    @property
    def relation_kind(self) -> RelationKind:
        return self.relation.relation_kind

    @property
    def clock(self) -> FieldClock:
        return self.relation.clock

    @property
    def target_json(self) -> str:
        return self.relation.target_json

    @property
    def provenance_json(self) -> str:
        return self.relation.provenance_json

    @property
    def observed_at_us(self) -> int | None:
        return self.relation.observed_at_us

    @property
    def target_repository_uuidv4(self) -> str | None:
        return self.relation.target_repository_uuidv4

    @property
    def is_explicit_null_target(self) -> bool:
        return self.relation.is_explicit_null_target

    @property
    def is_disposed(self) -> bool:
        return self.support_status in (
            "supporting_binding_disposed",
            "missing_supporting_binding",
            "conflicting_support",
        )

    @property
    def is_active(self) -> bool:
        return self.support_status in (
            "self_binding",
            "active",
            "unconfirmed_disposition",
            "explicit_null",
            "unresolved_provider_only",
        )

    @property
    def is_core_resolved_active(self) -> bool:
        return (
            self.support_status in ("self_binding", "active")
            and self.relation.target_repository_uuidv4 is not None
        )


@dataclass(frozen=True)
class EventReportKey:
    """Transfer EventReportKey: (EventResourceKey, clock_json, provenance_json)."""

    event_resource: ResourceKey
    clock: FieldClock
    provenance_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.event_resource, ResourceKey):
            raise ValueError("EventReportKey.event_resource must be a ResourceKey")
        if not isinstance(self.clock, FieldClock):
            raise ValueError("EventReportKey.clock must be a FieldClock")
        validate_relation_resource_kind(
            "transfer_from_repository",
            self.event_resource.resource_kind,
            self.event_resource.provider_resource_id,
        )
        validate_mapping_clock(self.clock.encode())
        validate_mapping_provenance(self.provenance_json)

    @property
    def service_instance_uuidv4(self) -> str:
        return self.event_resource.service_instance_uuidv4

    @property
    def resource_kind(self) -> str:
        return self.event_resource.resource_kind

    @property
    def provider_resource_id(self) -> str:
        return self.event_resource.provider_resource_id

    @property
    def clock_json(self) -> str:
        return self.clock.encode()

    @property
    def issue_parent(self) -> ResourceKey:
        parent_id, _ = validate_timeline_event_coordinates(
            self.event_resource.provider_resource_id
        )
        return ResourceKey(self.service_instance_uuidv4, "issue", parent_id)

    def coordinates(self) -> tuple[str, str, str, str, str]:
        return (
            self.event_resource.service_instance_uuidv4,
            self.event_resource.resource_kind,
            self.event_resource.provider_resource_id,
            self.clock.encode(),
            self.provenance_json,
        )


@dataclass(frozen=True)
class TransferEventReport:
    """Complete or selection-qualified Transfer Event report bound to one EventReportKey."""

    report_key: EventReportKey
    observed_at_us: int | None = None
    from_relations: tuple[ResourceRepositoryRelation, ...] = ()
    to_relations: tuple[ResourceRepositoryRelation, ...] = ()
    from_provider_repository: ResourceKey | None = None
    to_provider_repository: ResourceKey | None = None
    omitted_roles: frozenset[RelationKind] = frozenset()
    event_type: str = "transferred"
    selection_truncated: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.report_key, EventReportKey):
            raise ValueError("TransferEventReport.report_key must be an EventReportKey")
        validate_observation_us(self.observed_at_us)
        if type(self.selection_truncated) is not bool:
            raise ValueError("selection_truncated must be bool")
        if self.event_type != "transferred":
            raise ValueError(
                f"TransferEventReport requires genuine event_type='transferred', got {self.event_type!r}"
            )
        if not isinstance(self.from_relations, tuple):
            object.__setattr__(self, "from_relations", tuple(self.from_relations))
        if not isinstance(self.to_relations, tuple):
            object.__setattr__(self, "to_relations", tuple(self.to_relations))
        if not isinstance(self.omitted_roles, frozenset):
            object.__setattr__(self, "omitted_roles", frozenset(self.omitted_roles))
        if not self.omitted_roles.issubset(TRANSFER_RELATION_KINDS):
            raise ValueError(
                "omitted_roles must be a subset of transfer relation kinds"
            )
        for rel in self.from_relations:
            self._validate_endpoint_relation(rel, "transfer_from_repository")
        for rel in self.to_relations:
            self._validate_endpoint_relation(rel, "transfer_to_repository")
        for provider_repo in (
            self.from_provider_repository,
            self.to_provider_repository,
        ):
            if provider_repo is not None and (
                not isinstance(provider_repo, ResourceKey)
                or provider_repo.service_instance_uuidv4
                != self.report_key.service_instance_uuidv4
                or provider_repo.resource_kind != "repository"
            ):
                raise ValueError(
                    "Unresolved transfer endpoint provider_repository must be a repository ResourceKey in the same service"
                )
        if (
            self.from_relations
            and self.from_provider_repository is not None
            and any(r.is_explicit_null_target for r in self.from_relations)
        ):
            raise ValueError(
                "Explicit null transfer_from_repository cannot also carry from_provider_repository"
            )
        if (
            self.to_relations
            and self.to_provider_repository is not None
            and any(r.is_explicit_null_target for r in self.to_relations)
        ):
            raise ValueError(
                "Explicit null transfer_to_repository cannot also carry to_provider_repository"
            )
        if not self.all_known_roles:
            raise ValueError(
                "TransferEventReport requires at least one provided or omitted transfer endpoint role"
            )
        if not self.omitted_roles.isdisjoint(self.provided_roles):
            raise ValueError("omitted_roles cannot overlap with provided_roles")
        for relations, provider in (
            (self.from_relations, self.from_provider_repository),
            (self.to_relations, self.to_provider_repository),
        ):
            if provider is not None and any(
                r.embedded_support is not None
                and r.embedded_support.provider_repository != provider
                for r in relations
            ):
                raise ValueError(
                    "Transfer MappingSupport must match its Provider endpoint"
                )

    @property
    def scope_json(self) -> str:
        return canonical(
            {
                "clock": json.loads(self.clock.encode()),
                "event_type": self.event_type,
                "from_provider_repository_id": self.from_provider_repository.provider_resource_id
                if self.from_provider_repository
                else None,
                "to_provider_repository_id": self.to_provider_repository.provider_resource_id
                if self.to_provider_repository
                else None,
                "provided_roles": sorted(self.provided_roles),
            }
        )

    @property
    def members_json(self) -> str:
        members = []
        for provider in (self.from_provider_repository, self.to_provider_repository):
            if provider is not None and list(provider.coordinates()) not in members:
                members.append(list(provider.coordinates()))
        return canonical(members)

    @classmethod
    def from_stored_scope(
        cls,
        report_key: EventReportKey,
        relations: Iterable[ResourceRepositoryRelation],
        scope_json: str,
        members_json: str,
        observed_at_us: int | None,
    ) -> TransferEventReport:
        """Recheck original scope and membership without filling missing declarations."""
        scope = _parse_canonical_json(scope_json)
        if type(scope) is not dict or set(scope) != {
            "clock",
            "event_type",
            "from_provider_repository_id",
            "to_provider_repository_id",
            "provided_roles",
        }:
            raise ValueError("Invalid stored Transfer report scope")
        rels = tuple(relations)

        def provider(name: str) -> ResourceKey | None:
            value = scope[name]
            return (
                None
                if value is None
                else ResourceKey(
                    report_key.service_instance_uuidv4, "repository", value
                )
            )

        report = cls(
            report_key,
            observed_at_us,
            from_relations=tuple(
                r for r in rels if r.relation_kind == "transfer_from_repository"
            ),
            to_relations=tuple(
                r for r in rels if r.relation_kind == "transfer_to_repository"
            ),
            from_provider_repository=provider("from_provider_repository_id"),
            to_provider_repository=provider("to_provider_repository_id"),
            event_type=scope["event_type"],
        )
        if scope_json != report.scope_json or members_json != report.members_json:
            raise ValueError(
                "Stored Transfer report scope/members do not match endpoints"
            )
        return report

    def _validate_endpoint_relation(
        self, relation: ResourceRepositoryRelation, expected_role: RelationKind
    ) -> None:
        if not isinstance(relation, ResourceRepositoryRelation):
            raise ValueError("Endpoint relation must be a ResourceRepositoryRelation")
        if relation.resource != self.report_key.event_resource:
            raise ValueError(
                "Endpoint relation.resource must match report_key.event_resource"
            )
        if relation.relation_kind != expected_role:
            raise ValueError(
                f"Endpoint relation_kind must be {expected_role!r}, got {relation.relation_kind!r}"
            )
        if relation.clock != self.report_key.clock:
            raise ValueError("Endpoint relation.clock must match report_key.clock")
        if relation.provenance_json != self.report_key.provenance_json:
            raise ValueError(
                "Endpoint relation.provenance_json must match report_key.provenance_json"
            )
        if relation.observed_at_us != self.observed_at_us:
            raise ValueError(
                "Endpoint relation.observed_at_us must match report observed_at_us"
            )

    @classmethod
    def from_targets(
        cls,
        event_resource: ResourceKey,
        *,
        clock: FieldClock,
        provenance_json: str,
        observed_at_us: int | None = None,
        from_target_json: str | Sequence[str] | None = None,
        to_target_json: str | Sequence[str] | None = None,
        from_provider_repository: ResourceKey | None = None,
        to_provider_repository: ResourceKey | None = None,
        omitted_roles: Iterable[RelationKind] = (),
        event_type: str = "transferred",
    ) -> TransferEventReport:
        report_key = EventReportKey(
            event_resource=event_resource,
            clock=clock,
            provenance_json=provenance_json,
        )

        def _make_rels(
            targets: str | Sequence[str] | None, role: RelationKind
        ) -> tuple[ResourceRepositoryRelation, ...]:
            if targets is None:
                return ()
            items = (targets,) if isinstance(targets, str) else tuple(targets)
            return tuple(
                ResourceRepositoryRelation(
                    resource=event_resource,
                    relation_kind=role,
                    clock=clock,
                    target_json=t,
                    provenance_json=provenance_json,
                    observed_at_us=observed_at_us,
                )
                for t in items
            )

        return cls(
            report_key=report_key,
            observed_at_us=observed_at_us,
            from_relations=_make_rels(from_target_json, "transfer_from_repository"),
            to_relations=_make_rels(to_target_json, "transfer_to_repository"),
            from_provider_repository=from_provider_repository,
            to_provider_repository=to_provider_repository,
            omitted_roles=frozenset(omitted_roles),
            event_type=event_type,
        )

    @property
    def event_resource(self) -> ResourceKey:
        return self.report_key.event_resource

    @property
    def issue_resource(self) -> ResourceKey:
        return self.report_key.issue_parent

    @property
    def clock(self) -> FieldClock:
        return self.report_key.clock

    @property
    def provenance_json(self) -> str:
        return self.report_key.provenance_json

    @property
    def from_relation(self) -> ResourceRepositoryRelation | None:
        return self.from_relations[0] if len(self.from_relations) == 1 else None

    @property
    def to_relation(self) -> ResourceRepositoryRelation | None:
        return self.to_relations[0] if len(self.to_relations) == 1 else None

    @property
    def provided_roles(self) -> frozenset[RelationKind]:
        roles: list[RelationKind] = []
        if self.from_relations or self.from_provider_repository is not None:
            roles.append("transfer_from_repository")
        if self.to_relations or self.to_provider_repository is not None:
            roles.append("transfer_to_repository")
        return frozenset(roles)

    @property
    def all_known_roles(self) -> frozenset[RelationKind]:
        return self.provided_roles | self.omitted_roles

    @property
    def from_state(self) -> TransferEndpointState:
        if "transfer_from_repository" in self.omitted_roles:
            return "omitted_by_selection"
        if not self.from_relations:
            return (
                "unresolved_provider_only"
                if self.from_provider_repository is not None
                else "absent"
            )
        if all(r.is_explicit_null_target for r in self.from_relations):
            return "explicit_null"
        return "resolved"

    @property
    def to_state(self) -> TransferEndpointState:
        if "transfer_to_repository" in self.omitted_roles:
            return "omitted_by_selection"
        if not self.to_relations:
            return (
                "unresolved_provider_only"
                if self.to_provider_repository is not None
                else "absent"
            )
        if all(r.is_explicit_null_target for r in self.to_relations):
            return "explicit_null"
        return "resolved"

    @property
    def is_one_sided(self) -> bool:
        return len(self.all_known_roles) == 1

    @property
    def is_two_sided(self) -> bool:
        return len(self.all_known_roles) == 2

    @property
    def has_selection_omission(self) -> bool:
        return bool(self.omitted_roles) or self.selection_truncated

    def select_for_repositories(
        self, selected_repository_uuidv4s: Iterable[str]
    ) -> TransferEventReport | None:
        selected = set(selected_repository_uuidv4s)
        for repo_id in selected:
            if not _is_uuid4_str(repo_id):
                raise ValueError(f"Invalid selected repository_uuidv4: {repo_id!r}")
        kept_from = tuple(
            r
            for r in self.from_relations
            if r.is_explicit_null_target or r.target_repository_uuidv4 in selected
        )
        kept_to = tuple(
            r
            for r in self.to_relations
            if r.is_explicit_null_target or r.target_repository_uuidv4 in selected
        )
        has_selected_from = any(
            r.target_repository_uuidv4 in selected for r in kept_from
        )
        has_selected_to = any(r.target_repository_uuidv4 in selected for r in kept_to)
        if not has_selected_from and not has_selected_to:
            return None
        omitted = set(self.omitted_roles)
        if self.from_relations and not kept_from:
            omitted.add("transfer_from_repository")
        if self.to_relations and not kept_to:
            omitted.add("transfer_to_repository")
        return TransferEventReport(
            report_key=self.report_key,
            observed_at_us=self.observed_at_us,
            from_relations=kept_from,
            to_relations=kept_to,
            from_provider_repository=(
                None
                if "transfer_from_repository" in omitted
                else self.from_provider_repository
            ),
            to_provider_repository=(
                None
                if "transfer_to_repository" in omitted
                else self.to_provider_repository
            ),
            omitted_roles=frozenset(omitted),
            event_type=self.event_type,
            selection_truncated=(
                self.selection_truncated
                or len(kept_from) != len(self.from_relations)
                or len(kept_to) != len(self.to_relations)
            ),
        )


@dataclass(frozen=True)
class ProviderRepositoryRoleScope:
    """Finite typed scope entry for a Provider Repository role on an immutable ResourceRelation."""

    relation_kind: RelationKind
    clock: FieldClock
    state: ProviderRoleState
    provider_repository_id: str | None = None
    repository_uuidv4: str | None = None
    observed_at_us: int | None = None

    def __post_init__(self) -> None:
        if self.relation_kind not in MAPPING_RELATION_KINDS:
            raise ValueError(
                f"ProviderRepositoryRoleScope requires non-represents_repository role, got {self.relation_kind!r}"
            )
        if not isinstance(self.clock, FieldClock):
            raise ValueError("ProviderRepositoryRoleScope.clock must be a FieldClock")
        validate_mapping_clock(self.clock.encode())
        validate_observation_us(self.observed_at_us)
        if self.state == "explicit_null":
            if (
                self.provider_repository_id is not None
                or self.repository_uuidv4 is not None
            ):
                raise ValueError(
                    "explicit_null role scope must have provider_repository_id=None and repository_uuidv4=None"
                )
        elif self.state == "unresolved_provider_only":
            if (
                not _is_nonempty_str(self.provider_repository_id)
                or self.repository_uuidv4 is not None
            ):
                raise ValueError(
                    "unresolved_provider_only role scope requires provider_repository_id and repository_uuidv4=None"
                )
        elif self.state == "resolved":
            if not _is_nonempty_str(self.provider_repository_id) or not _is_uuid4_str(
                self.repository_uuidv4
            ):
                raise ValueError(
                    "resolved role scope requires non-empty provider_repository_id and valid repository_uuidv4"
                )
        else:
            raise ValueError(
                f"Invalid stored ProviderRepositoryRoleScope state: {self.state!r}"
            )
        if self.provider_repository_id is not None:
            parse_identity(self.provider_repository_id)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "clock": json.loads(self.clock.encode()),
            "provider_repository_id": self.provider_repository_id,
            "repository_uuidv4": self.repository_uuidv4,
            "state": self.state,
        }
        if self.observed_at_us is not None:
            payload["observed_at_us"] = self.observed_at_us
        return payload

    @classmethod
    def explicit_null(
        cls,
        relation_kind: RelationKind,
        clock: FieldClock,
        observed_at_us: int | None = None,
    ) -> ProviderRepositoryRoleScope:
        return cls(
            relation_kind=relation_kind,
            clock=clock,
            state="explicit_null",
            observed_at_us=observed_at_us,
        )

    @classmethod
    def unresolved(
        cls,
        relation_kind: RelationKind,
        provider_repository_id: str,
        clock: FieldClock,
        observed_at_us: int | None = None,
    ) -> ProviderRepositoryRoleScope:
        return cls(
            relation_kind=relation_kind,
            clock=clock,
            state="unresolved_provider_only",
            provider_repository_id=provider_repository_id,
            observed_at_us=observed_at_us,
        )

    @classmethod
    def resolved(
        cls,
        relation_kind: RelationKind,
        provider_repository_id: str,
        repository_uuidv4: str,
        clock: FieldClock,
        observed_at_us: int | None = None,
    ) -> ProviderRepositoryRoleScope:
        return cls(
            relation_kind=relation_kind,
            clock=clock,
            state="resolved",
            provider_repository_id=provider_repository_id,
            repository_uuidv4=repository_uuidv4,
            observed_at_us=observed_at_us,
        )


@dataclass(frozen=True)
class ProviderRepositoryScope:
    """Canonical scope_json contract for resource_relations carrying Provider Repository roles."""

    roles: Mapping[RelationKind, ProviderRepositoryRoleScope] = field(
        default_factory=dict
    )
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.roles, Mapping) or not isinstance(
            self.attributes, Mapping
        ):
            raise ValueError("roles and attributes must be mappings")
        normalized_roles: dict[RelationKind, ProviderRepositoryRoleScope] = {}
        for role_key, entry in sorted(self.roles.items()):
            if role_key not in MAPPING_RELATION_KINDS:
                raise ValueError(
                    f"Unsupported ProviderRepositoryScope role: {role_key!r}"
                )
            if not isinstance(entry, ProviderRepositoryRoleScope):
                raise ValueError(
                    "Each role entry must be a ProviderRepositoryRoleScope"
                )
            if entry.relation_kind != role_key:
                raise ValueError(
                    f"Role key {role_key!r} does not match entry.relation_kind {entry.relation_kind!r}"
                )
            normalized_roles[role_key] = entry
        normalized_attrs: dict[str, Any] = {}
        for k, v in sorted(self.attributes.items()):
            if not _is_nonempty_str(k) or k == "repository_roles":
                raise ValueError(f"Invalid or reserved scope attribute key: {k!r}")
            normalized_attrs[k] = v
        _parse_canonical_json(canonical(normalized_attrs))
        object.__setattr__(self, "roles", normalized_roles)
        object.__setattr__(self, "attributes", normalized_attrs)

    def role(self, relation_kind: RelationKind) -> ProviderRepositoryRoleScope | None:
        if relation_kind not in MAPPING_RELATION_KINDS:
            raise ValueError(f"Unsupported role: {relation_kind!r}")
        return self.roles.get(relation_kind)

    def role_state(self, relation_kind: RelationKind) -> ProviderRoleState:
        entry = self.role(relation_kind)
        return "absent" if entry is None else entry.state

    @property
    def encoded(self) -> str:
        payload: dict[str, Any] = dict(self.attributes)
        payload["repository_roles"] = {
            role_key: entry.to_dict() for role_key, entry in sorted(self.roles.items())
        }
        return canonical(payload)

    @classmethod
    def from_json(cls, scope_json: str) -> ProviderRepositoryScope:
        parsed = _parse_canonical_json(scope_json)
        if type(parsed) is not dict or "repository_roles" not in parsed:
            raise ValueError(
                "ProviderRepositoryScope JSON must be a canonical object with 'repository_roles'"
            )
        raw_roles = parsed["repository_roles"]
        if type(raw_roles) is not dict:
            raise ValueError("'repository_roles' must be a JSON object")
        roles: dict[RelationKind, ProviderRepositoryRoleScope] = {}
        for role_key, raw_entry in raw_roles.items():
            if role_key not in MAPPING_RELATION_KINDS:
                raise ValueError(f"Unknown repository role in scope_json: {role_key!r}")
            if type(raw_entry) is not dict:
                raise ValueError("Role scope entry must be an object")
            allowed_keys = {
                "clock",
                "provider_repository_id",
                "repository_uuidv4",
                "state",
                "observed_at_us",
            }
            if not set(raw_entry.keys()).issubset(allowed_keys) or not {
                "clock",
                "state",
            }.issubset(raw_entry.keys()):
                raise ValueError(
                    "Role scope entry must contain clock and state without extra keys"
                )
            clock_json = canonical(raw_entry["clock"])
            validate_mapping_clock(clock_json)
            observed_at_us = raw_entry.get("observed_at_us")
            if observed_at_us is not None and not _is_positive_int64(observed_at_us):
                raise ValueError("Role scope observed_at_us must be positive int64")
            roles[role_key] = ProviderRepositoryRoleScope(
                relation_kind=role_key,
                clock=FieldClock.from_json(clock_json),
                state=raw_entry["state"],
                provider_repository_id=raw_entry.get("provider_repository_id"),
                repository_uuidv4=raw_entry.get("repository_uuidv4"),
                observed_at_us=observed_at_us,
            )
        attrs = {k: v for k, v in parsed.items() if k != "repository_roles"}
        return cls(roles=roles, attributes=attrs)


def qualify_provider_role_scopes(
    scopes: Sequence[ProviderRepositoryRoleScope],
) -> tuple[ProviderRepositoryRoleScope, ...]:
    """Return non-dominated ProviderRepositoryRoleScope entries without unioning groups."""
    for item in scopes:
        if not isinstance(item, ProviderRepositoryRoleScope):
            raise ValueError("Expected ProviderRepositoryRoleScope instances")
    max_by_domain: dict[tuple[RelationKind, str], int] = {}
    for item in scopes:
        if item.clock.at_us is not None:
            key = (item.relation_kind, item.clock.domain)
            prev = max_by_domain.get(key)
            if prev is None or item.clock.at_us > prev:
                max_by_domain[key] = item.clock.at_us
    return tuple(
        item
        for item in scopes
        if item.clock.at_us is None
        or item.clock.at_us == max_by_domain[(item.relation_kind, item.clock.domain)]
    )


def validate_provider_repository_scope(
    resource, members, provenance_json, scope_json, observed_at_us
):
    """Validate current Provider roles; real Transfer reports use their dedicated path."""
    scope = ProviderRepositoryScope.from_json(scope_json)
    MappingProvenance.from_json(provenance_json)
    expected = set()
    for role in scope.roles.values():
        if role.relation_kind not in CURRENT_CANDIDATE_RELATION_KINDS:
            raise ValueError("Transfer roles require the complete Transfer report API")
        validate_relation_resource_kind(
            role.relation_kind, resource.resource_kind, resource.provider_resource_id
        )
        if role.observed_at_us != observed_at_us:
            raise ValueError("Provider role original observation mismatch")
        if role.provider_repository_id is not None:
            expected.add(
                ResourceKey(
                    resource.service_instance_uuidv4,
                    "repository",
                    role.provider_repository_id,
                )
            )
    if len(members) != len(expected) or set(members) != expected:
        raise ValueError("Provider role members do not match declared scope")
    return scope


@dataclass(frozen=True)
class QualifiedProviderRepositoryRole:
    """Original Provider report plus present mapping qualifications; never a stored winner."""

    resource: ResourceKey
    scope: ProviderRepositoryRoleScope
    provenance_json: str
    mapping: QualifiedMappingEvaluation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.resource, ResourceKey) or not isinstance(
            self.scope, ProviderRepositoryRoleScope
        ):
            raise ValueError("Typed Resource and Provider role scope required")
        if self.scope.relation_kind not in CURRENT_CANDIDATE_RELATION_KINDS:
            raise ValueError(
                "Transfer qualification requires the complete Transfer report API"
            )
        validate_relation_resource_kind(
            self.scope.relation_kind,
            self.resource.resource_kind,
            self.resource.provider_resource_id,
        )
        MappingProvenance.from_json(self.provenance_json)
        if self.scope.state == "explicit_null":
            if self.mapping is not None:
                raise ValueError("Explicit NULL cannot carry Mapping support")
        elif self.mapping is not None:
            provider = ResourceKey(
                self.resource.service_instance_uuidv4,
                "repository",
                self.scope.provider_repository_id,
            )
            if (
                not isinstance(self.mapping, QualifiedMappingEvaluation)
                or self.mapping.provider_repository != provider
            ):
                raise ValueError(
                    "Mapping evaluation must name the exact Provider Repository"
                )
            if any(
                not isinstance(claim, MappingClaimKey) or claim.resource != provider
                for claim in self.mapping.active_claims
            ):
                raise ValueError(
                    "Supporting ClaimKeys must name the exact Provider Repository"
                )

    @property
    def state(self) -> str:
        if self.scope.state == "explicit_null":
            return "explicit_null"
        if self.mapping is None or self.mapping.state == "unmapped":
            return "unresolved_provider_only"
        return self.mapping.state

    @property
    def supports(self) -> tuple[MappingSupport, ...]:
        if self.mapping is None:
            return ()
        by_target: dict[str, list[MappingClaimKey]] = {}
        for claim in self.mapping.active_claims:
            by_target.setdefault(claim.target_json, []).append(claim)
        return tuple(
            MappingSupport(claims[0].resource, tuple(claims))
            for _, claims in sorted(by_target.items())
        )

    @property
    def resolved_candidates(self) -> tuple[ResourceRepositoryRelation, ...]:
        if self.scope.state == "explicit_null":
            return (
                ResourceRepositoryRelation(
                    self.resource,
                    self.scope.relation_kind,
                    self.scope.clock,
                    "null",
                    self.provenance_json,
                    self.scope.observed_at_us,
                ),
            )
        provenance = self.provenance
        return tuple(
            ResourceRepositoryRelation(
                self.resource,
                self.scope.relation_kind,
                self.scope.clock,
                canonical(support.target_repository_uuidv4),
                encode_supported_provenance(
                    provenance.source,
                    provenance.evidence,
                    support,
                    claimed_issuer=provenance.claimed_issuer
                    if provenance.claimed_issuer_state != "omitted"
                    else OMITTED_ISSUER,
                ),
                self.scope.observed_at_us,
            )
            for support in self.supports
        )

    @property
    def provenance(self) -> MappingProvenance:
        return MappingProvenance.from_json(self.provenance_json)


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
        if any(not _is_nonempty_str(item) for item in self.coordinates):
            raise ValueError("Scope coordinates must be genuine nonempty strings")
        if self.owner_kind in {"resource", "field", "collection"}:
            ResourceKey(*self.coordinates[:3])
        if self.owner_kind == "field" and self.coordinates[3] == "repository_uuidv4":
            raise ValueError(
                "field='repository_uuidv4' is prohibited; use CoverageScope.repository_relation"
            )
        if self.owner_kind == "resource" and self.coordinates[-1].startswith("{"):
            parsed = _parse_canonical_json(self.coordinates[-1])
            if (
                type(parsed) is not dict
                or set(parsed.keys())
                != {"coverage_kind", "relation_kind", "repository_uuidv4"}
                or not _is_nonempty_str(parsed.get("coverage_kind"))
            ):
                raise ValueError(
                    "Role-scoped resource coverage coordinate must be canonical {'coverage_kind', 'relation_kind', 'repository_uuidv4'}"
                )
            rel_kind = parsed["relation_kind"]
            validate_relation_resource_kind(
                rel_kind, self.coordinates[1], self.coordinates[2]
            )
            repo_uuid = parsed["repository_uuidv4"]
            if repo_uuid is not None and not _is_uuid4_str(repo_uuid):
                raise ValueError(
                    "Role-scoped coverage repository_uuidv4 must be null or a lowercase UUIDv4"
                )

    @property
    def encoded(self) -> str:
        return canonical(list(self.coordinates))

    @property
    def relation_kind(self) -> RelationKind | None:
        if self.owner_kind == "resource" and self.coordinates[-1].startswith("{"):
            return json.loads(self.coordinates[-1])["relation_kind"]
        return None

    @property
    def relation_repository_uuidv4(self) -> str | None:
        if self.owner_kind == "resource" and self.coordinates[-1].startswith("{"):
            return json.loads(self.coordinates[-1])["repository_uuidv4"]
        return None

    @property
    def base_coverage_kind(self) -> str:
        if self.owner_kind == "resource" and self.coordinates[-1].startswith("{"):
            return json.loads(self.coordinates[-1])["coverage_kind"]
        return self.coordinates[-1]

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
        if not isinstance(resource, ResourceKey):
            raise ValueError("resource must be a ResourceKey")
        if type(kind) is str and kind.startswith("{"):
            raise ValueError(
                "Use CoverageScope.repository_relation for structured role-scoped coverage coordinates"
            )
        return cls("resource", (*resource.coordinates(), kind))

    @classmethod
    def repository_relation(
        cls,
        repository_uuidv4: str | None,
        resource: ResourceKey,
        relation_kind: RelationKind,
        coverage_kind: str,
    ) -> CoverageScope:
        if not isinstance(resource, ResourceKey):
            raise ValueError("resource must be a ResourceKey")
        validate_relation_resource_kind(
            relation_kind, resource.resource_kind, resource.provider_resource_id
        )
        if repository_uuidv4 is not None and not _is_uuid4_str(repository_uuidv4):
            raise ValueError("repository_uuidv4 must be None or a lowercase UUIDv4")
        if not _is_nonempty_str(coverage_kind):
            raise ValueError("coverage_kind must be a non-empty string")
        token = canonical(
            {
                "coverage_kind": coverage_kind,
                "relation_kind": relation_kind,
                "repository_uuidv4": repository_uuidv4,
            }
        )
        return cls("resource", (*resource.coordinates(), token))

    @classmethod
    def field(cls, resource: ResourceKey, field: str, kind: str) -> CoverageScope:
        if field == "repository_uuidv4":
            raise ValueError(
                "field='repository_uuidv4' is prohibited; use CoverageScope.repository_relation"
            )
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
