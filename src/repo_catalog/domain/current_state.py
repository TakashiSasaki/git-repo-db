"""Mutable provider resources: typed identity and content, without edit histories."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, NamedTuple

from repo_catalog.domain.document import text_body_sha256


class IssueResourceKey(NamedTuple):
    service_instance_uuidv4: str
    kind: str
    provider_resource_id: str


class ReviewResourceKey(NamedTuple):
    change_request_id: str
    kind: str
    provider_change_request_document_id: str


@dataclass(frozen=True)
class AdmissionResult:
    status: str
    key: IssueResourceKey | ReviewResourceKey
    state_digest: str
    reason: str | None = None


def resource_key(candidate: Mapping) -> IssueResourceKey | ReviewResourceKey:
    if candidate["kind"] in ("issue", "issue-comment"):
        return IssueResourceKey(
            candidate["service_instance_uuidv4"],
            candidate["kind"],
            candidate["provider_resource_id"],
        )
    if candidate["kind"] in ("review", "review-comment"):
        return ReviewResourceKey(
            candidate["change_request_id"],
            candidate["kind"],
            candidate["provider_change_request_document_id"],
        )
    raise ValueError("Unsupported current resource kind")


# These values explain a capture, not the provider's semantic resource state.
_CONTEXT_FIELDS = {
    "provider_updated_at_us",
    "provider_clock_scope",
    "observed_at_us",
    "last_checked_at_us",
    "parsed_at_us",
    "acquisition_scope",
    "acquisition_scope_json",
    "text_body_id",
    "parent_kind",
    "parent_review_kind",
    "reply_kind",
}


def semantic_content(candidate: Mapping) -> dict:
    """Canonical response content; absent fields stay absent in partial proofs."""
    content = {}
    for name, value in candidate.items():
        if name in _CONTEXT_FIELDS:
            continue
        if name == "body":
            content["text_body_sha256"] = (
                text_body_sha256(value).hex() if value is not None else None
            )
        elif name == "text_body_sha256" and isinstance(value, bytes):
            content[name] = value.hex()
        elif name == "metadata" and isinstance(value, str):
            content[name] = json.loads(value)
        else:
            content[name] = value
    return content


def fingerprint_candidate(candidate: Mapping) -> str:
    """Fingerprint exact present semantic fields, suitable for page membership."""
    encoded = json.dumps(
        semantic_content(candidate),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
