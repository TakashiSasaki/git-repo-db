"""Verified admission of physical bytes and logical payload registrations."""

import hashlib
import sqlite3

from repo_catalog.adapters.sqlite.cas_integrity import is_quarantined
from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.payload import PayloadRef


def intern_stored_bytes(db: sqlite3.Connection, body: bytes, expected_sha256: bytes):
    """Caller owns the writer transaction. Never replace an existing body."""
    if not isinstance(body, bytes) or not isinstance(expected_sha256, bytes):
        raise CatalogError("INVALID_PAYLOAD", "Payload body and digest must be bytes")
    if len(expected_sha256) != 32 or hashlib.sha256(body).digest() != expected_sha256:
        raise CatalogError(
            "PAYLOAD_DIGEST_MISMATCH", "Body does not match declared SHA-256"
        )
    stored = db.execute(
        "SELECT body,byte_length FROM stored_bytes WHERE sha256=?", (expected_sha256,)
    ).fetchone()
    if stored is not None:
        if is_quarantined(db, expected_sha256):
            raise CatalogError(
                "PAYLOAD_CORRUPTION",
                "Stored bytes are quarantined; explicit repair required",
                {"sha256": expected_sha256.hex()},
            )
        if stored[0] != body or stored[1] != len(body):
            if (
                hashlib.sha256(stored[0]).digest() != expected_sha256
                or len(stored[0]) != stored[1]
            ):
                raise CatalogError(
                    "PAYLOAD_CORRUPTION",
                    "Stored bytes are corrupt; explicit repair required",
                    {"sha256": expected_sha256.hex()},
                )
            raise CatalogError(
                "PAYLOAD_HASH_COLLISION",
                "Different valid bytes have the same SHA-256",
                {"sha256": expected_sha256.hex()},
            )
        return
    db.execute(
        "INSERT INTO stored_bytes(sha256,body,byte_length) VALUES(?,?,?)",
        (expected_sha256, body, len(body)),
    )


def intern_payload(
    db: sqlite3.Connection,
    body: bytes,
    *,
    representation,
    expected_sha256=None,
) -> PayloadRef:
    """Register explicitly identified content; never infer its meaning from bytes.

    Retained Git content and temporary legacy API-original paths share physical
    integrity checks, but callers must declare which logical contract they use.
    """
    if not isinstance(body, bytes):
        raise CatalogError("INVALID_PAYLOAD", "Payload body must be bytes")
    reference = PayloadRef(
        representation,
        expected_sha256
        if expected_sha256 is not None
        else hashlib.sha256(body).digest(),
    )
    # A failed logical registration must not leave an orphan physical object,
    # even when its caller catches the error inside a larger transaction.
    db.execute("SAVEPOINT payload_admission")
    try:
        intern_stored_bytes(db, body, reference.sha256)
        if (
            db.execute(
                "SELECT 1 FROM payloads WHERE representation=? AND sha256=?",
                reference.parameters(),
            ).fetchone()
            is None
        ):
            db.execute(
                "INSERT INTO payloads(representation,sha256) VALUES(?,?)",
                reference.parameters(),
            )
    except BaseException:
        db.execute("ROLLBACK TO payload_admission")
        raise
    finally:
        db.execute("RELEASE payload_admission")
    return reference
