"""Document identity and exact text content, independent of local row numbers."""

from __future__ import annotations

import hashlib
from typing import NamedTuple


class DocumentKey(NamedTuple):
    """The document's natural key; never serialize this into a local document ID."""

    change_request_id: str
    kind: str
    provider_change_request_document_id: str


def text_body_sha256(body: str) -> bytes:
    """SHA-256 of exact UTF-8: no Unicode, newline or whitespace normalization."""
    if not isinstance(body, str):
        raise TypeError("A text body must be a string")
    return hashlib.sha256(body.encode("utf-8")).digest()


def verify_text_body(body, digest, byte_length):
    """Validate accessed domain text, including a declared absent body.

    Reads do not repair damage or treat a missing body as an HTTP archive gap.
    """
    from repo_catalog.domain.models import CatalogError

    if body is None and digest is None and byte_length is None:
        return
    try:
        valid = (
            text_body_sha256(body) == digest and len(body.encode("utf8")) == byte_length
        )
    except (TypeError, UnicodeError):
        valid = False
    if not valid:
        raise CatalogError(
            "TEXT_BODY_IDENTITY_CONFLICT",
            "Stored domain body does not match its identity",
        )
