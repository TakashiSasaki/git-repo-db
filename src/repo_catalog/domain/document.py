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
