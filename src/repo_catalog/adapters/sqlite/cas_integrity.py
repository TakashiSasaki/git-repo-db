"""Catalog-local physical diagnostics, bounded scans and explicit byte repair.

Entry points require the catalog's existing writer lock. Hash scans must start
outside a SQLite transaction: only failure recording holds a short write lock.
Successful verification is returned to the caller, never recorded as progress.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager

from repo_catalog.domain.models import CatalogError
from repo_catalog.domain.payload import PayloadRef
from repo_catalog.domain.time import now_us


@contextmanager
def _atomic(db):
    name = "cas_" + uuid.uuid4().hex
    db.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        db.execute(f"ROLLBACK TO {name}")
        raise
    finally:
        db.execute(f"RELEASE {name}")


def is_quarantined(db: sqlite3.Connection, digest: bytes) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM payload_quarantine WHERE sha256=?", (digest,)
        ).fetchone()
        is not None
    )


def _failure(row):
    digest, body, byte_length = row
    actual = hashlib.sha256(body).digest()
    if digest == actual and len(body) == byte_length:
        return None
    return {
        "expected_sha256": digest.hex(),
        "observed_sha256": actual.hex(),
        "declared_byte_length": byte_length,
        "observed_byte_length": len(body),
    }


def diagnose_corruption(db: sqlite3.Connection, digest: bytes):
    """Record one immutable diagnostic per continuous quarantine interval."""
    with _atomic(db):
        old = db.execute(
            "SELECT unresolved_payload_id FROM payload_quarantine WHERE sha256=?",
            (digest,),
        ).fetchone()
        if old:
            return old[0]
        row = db.execute(
            "SELECT sha256,body,byte_length FROM stored_bytes WHERE sha256=?", (digest,)
        ).fetchone()
        if row is None:
            raise CatalogError("NOT_FOUND", "Physical payload does not exist")
        failure = _failure(row)
        if failure is None:
            return None
        diagnostic = db.execute(
            "INSERT INTO unresolved_payloads(reason,stored_sha256,detected_at_us,diagnostic_json) VALUES('physical_corruption',?,?,?)",
            (digest, now_us(), json.dumps(failure, sort_keys=True)),
        ).lastrowid
        db.execute(
            "INSERT INTO payload_quarantine(sha256,unresolved_payload_id) VALUES(?,?)",
            (digest, diagnostic),
        )
        db.execute(
            "UPDATE database_identity SET publication_seq=publication_seq+1 WHERE singleton=1"
        )
        return diagnostic


def diagnose_admission_failure(db: sqlite3.Connection, error: CatalogError):
    """Diagnose a corrupt incumbent after rejected admission has rolled back.

    The evidence comes only from the existing physical object and its declared
    digest. Received bytes and acquisition context are never retained here.
    """
    if not isinstance(error, CatalogError) or error.code != "PAYLOAD_CORRUPTION":
        return None
    value = error.details.get("sha256")
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        return None
    digest = bytes.fromhex(value)
    if not db.execute(
        "SELECT 1 FROM stored_bytes WHERE sha256=?", (digest,)
    ).fetchone():
        return None
    return diagnose_corruption(db, digest)


def verify_all(db: sqlite3.Connection, *, diagnose=True):
    """Full bytes scan under caller-held writer.lock, without a long SQL tx.

    diagnose=False is for the copied backup: existing quarantine is acceptable,
    but unexplained corruption must prevent publication. No success markers or
    resumable verification cursor are persisted.
    """
    if db.in_transaction:
        raise CatalogError(
            "INVALID_TRANSACTION", "Full verification requires no active transaction"
        )
    checked, failures, unexplained = 0, [], []
    # A keyset query closes each read cursor before committing diagnostics.
    previous = None
    while True:
        row = db.execute(
            "SELECT sha256,body,byte_length FROM stored_bytes "
            + ("WHERE sha256>? " if previous is not None else "")
            + "ORDER BY sha256 LIMIT 1",
            (previous,) if previous is not None else (),
        ).fetchone()
        if row is None:
            break
        checked += 1
        previous = row[0]
        failure = _failure(row)
        if failure:
            known = is_quarantined(db, row[0])
            if diagnose:
                failure["unresolved_payload_id"] = diagnose_corruption(db, row[0])
            elif not known:
                unexplained.append(row[0].hex())
            failure["previously_quarantined"] = known
            failures.append(failure)
    return {"checked": checked, "corrupt": failures, "unexplained": unexplained}


def stage_verified_payload(db, body, reference: PayloadRef, context: dict, *, reason):
    """Retain rejected raw Git content without modifying admitted stored bytes."""
    if (
        not isinstance(reference, PayloadRef)
        or reference.representation != "git-object-raw-v1"
    ):
        raise CatalogError(
            "INVALID_ARGUMENT", "Rejected acquisition staging requires raw Git content"
        )
    if not isinstance(body, bytes) or hashlib.sha256(body).digest() != reference.sha256:
        raise CatalogError("PAYLOAD_DIGEST_MISMATCH", "Invalid bytes cannot be staged")
    if reason not in {"PAYLOAD_CORRUPTION", "PAYLOAD_HASH_COLLISION"}:
        raise CatalogError("INVALID_ARGUMENT", "Unsupported payload staging reason")
    if not isinstance(context, dict):
        raise CatalogError("INVALID_ARGUMENT", "Acquisition context must be an object")
    encoded = json.dumps(context, sort_keys=True, allow_nan=False)
    ident = str(uuid.uuid4())
    with _atomic(db):
        if reason == "PAYLOAD_CORRUPTION":
            diagnose_corruption(db, reference.sha256)
        db.execute(
            "INSERT INTO payload_admission_staging(stage_uuidv4,representation,sha256,body,context_json,reason,received_at_us) VALUES(?,?,?,?,?,?,?)",
            (ident, *reference.parameters(), body, encoded, reason, now_us()),
        )
    return ident


def repair_payload(db, digest: bytes, replacement: bytes):
    """Restore retained Git bytes by their physical hash, atomically.

    The write-protection trigger is suspended and restored *within* this single
    SQLite transaction. Readers observe either the old quarantined bytes or the
    fully repaired object; failure rolls back bytes, quarantine and trigger DDL.
    The caller must hold writer.lock for the entire operation.
    """
    if (
        not isinstance(digest, bytes)
        or len(digest) != 32
        or not isinstance(replacement, bytes)
        or hashlib.sha256(replacement).digest() != digest
    ):
        raise CatalogError("PAYLOAD_DIGEST_MISMATCH", "Replacement digest mismatch")
    with _atomic(db):
        objects = db.execute(
            "SELECT g.object_format,g.oid,g.type,g.size FROM git_object_payloads p JOIN git_objects g USING(git_object_id) WHERE p.payload_representation='git-object-raw-v1' AND p.payload_sha256=?",
            (digest,),
        ).fetchall()
        if not objects:
            raise CatalogError(
                "INVALID_ARGUMENT", "Explicit repair requires retained Git object bytes"
            )
        from repo_catalog.domain.git_object import validate_git_object

        for obj in objects:
            validate_git_object(*obj, replacement, digest)
        diagnostic = db.execute(
            "SELECT unresolved_payload_id FROM payload_quarantine WHERE sha256=?",
            (digest,),
        ).fetchone()
        if diagnostic is None:
            raise CatalogError("NOT_QUARANTINED", "Explicit repair requires quarantine")
        trigger = db.execute(
            "SELECT sql FROM sqlite_schema WHERE type='trigger' AND name='stored_bytes_immutable'"
        ).fetchone()
        if trigger is None:
            raise CatalogError("SCHEMA_ERROR", "Stored bytes protection is missing")
        db.execute("DROP TRIGGER stored_bytes_immutable")
        db.execute(
            "UPDATE stored_bytes SET body=?,byte_length=? WHERE sha256=?",
            (replacement, len(replacement), digest),
        )
        db.execute(trigger[0])
        row = db.execute(
            "SELECT sha256,body,byte_length FROM stored_bytes WHERE sha256=?", (digest,)
        ).fetchone()
        if row is None or _failure(row) is not None:
            raise CatalogError("PAYLOAD_CORRUPTION", "Replacement verification failed")
        db.execute("DELETE FROM payload_quarantine WHERE sha256=?", (digest,))
        db.execute(
            "UPDATE database_identity SET publication_seq=publication_seq+1 WHERE singleton=1"
        )
    return {
        "sha256": digest.hex(),
        "unresolved_payload_id": diagnostic[0],
        "repaired": True,
    }
