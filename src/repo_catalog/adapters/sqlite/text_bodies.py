"""Content-addressed text admission. The digest is identity, not just an index."""

from __future__ import annotations

import sqlite3

from repo_catalog.domain.document import text_body_sha256
from repo_catalog.domain.models import CatalogError


def intern_text_body(
    db: sqlite3.Connection, body: str, *, expected_sha256: bytes | None = None
) -> bytes:
    """Resolve by SHA-256, checking bytes before reusing an existing body.

    The caller owns the writer transaction. A conflicting body is an integrity
    failure, not an alternative row under the same digest or a successful merge.
    """
    try:
        digest = text_body_sha256(body)
        byte_length = len(body.encode("utf-8"))
    except (TypeError, UnicodeError) as error:
        raise CatalogError(
            "INVALID_TEXT_BODY", "Body must be valid UTF-8 text"
        ) from error
    if expected_sha256 is not None and digest != expected_sha256:
        raise CatalogError(
            "TEXT_BODY_DIGEST_MISMATCH", "Text does not match its SHA-256"
        )
    stored = db.execute(
        "SELECT body,byte_length FROM text_bodies WHERE sha256=?", (digest,)
    ).fetchone()
    if stored is not None:
        if stored[0] != body or stored[1] != byte_length:
            raise CatalogError(
                "TEXT_BODY_IDENTITY_CONFLICT", "Same SHA-256 identifies different text"
            )
        return digest
    db.execute(
        "INSERT INTO text_bodies(body,byte_length,sha256) VALUES(?,?,?)",
        (body, byte_length, digest),
    )
    return digest
