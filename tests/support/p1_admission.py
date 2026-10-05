"""Executable P1 admission examples, not a converter or production runtime.

Only caller-supplied local bytes/observation times are accepted. Hashing precedes
the write savepoint; the caller is the sole writer. These entry checks must be
ported into P3/P4/P5, since ordinary SQLite cannot prove cryptographic claims.
"""

import hashlib
import re
from contextlib import contextmanager
from datetime import datetime


@contextmanager
def atomic(db):
    db.execute("SAVEPOINT p1_admission")
    try:
        yield
    except BaseException:
        db.execute("ROLLBACK TO p1_admission")
        db.execute("RELEASE p1_admission")
        raise
    else:
        db.execute("RELEASE p1_admission")


def instant(value):
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})",
        value,
    ):
        raise ValueError(
            "A timezone-aware RFC3339 timestamp with at most microsecond precision is required"
        )
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("An observation timestamp must include its timezone")
    return parsed


def record_rediscovery(db, source_id, repo_id, observed_at):
    """Project known min/max; this pair row is not the discovery event history."""
    when = instant(observed_at)
    old = db.execute(
        "SELECT first_seen,last_seen FROM source_repositories "
        "WHERE source_id=? AND repo_id=?",
        (source_id, repo_id),
    ).fetchone()
    if old is None:
        with atomic(db):
            db.execute(
                "INSERT INTO source_repositories VALUES(?,?,?,?)",
                (source_id, repo_id, observed_at, observed_at),
            )
        return
    first, last = old
    if first is None or when < instant(first):
        first = observed_at
    if last is None or when > instant(last):
        last = observed_at
    if (first, last) != old:
        with atomic(db):
            db.execute(
                "UPDATE source_repositories SET first_seen=?,last_seen=? "
                "WHERE source_id=? AND repo_id=?",
                (first, last, source_id, repo_id),
            )


def prepare_text_completion(db, content_id, raw):
    """Verify bytes before the writer transaction, returning its SQL-only save."""
    if db.in_transaction:
        raise ValueError("Prepare content bytes before the writer transaction")
    row = db.execute(
        "SELECT byte_length,raw_text,text_state FROM contents WHERE id=?", (content_id,)
    ).fetchone()
    if row is None:
        raise ValueError("Missing content claim")
    length, saved, state = row
    if len(raw) != length or state != "eligible" or b"\0" in raw:
        raise ValueError("Content length or text eligibility mismatch")
    text = raw.decode("utf-8", errors="strict")
    anchors = db.execute(
        "SELECT algorithm,digest FROM content_digests "
        "WHERE content_id=? AND representation='raw-content-v1'",
        (content_id,),
    ).fetchall()
    if "sha256" not in {algorithm for algorithm, _ in anchors}:
        raise ValueError("Missing raw-content-v1 SHA-256 anchor")
    if any(
        hashlib.new(algorithm, raw).digest() != digest for algorithm, digest in anchors
    ):
        raise ValueError("Raw content digest mismatch")
    if saved is not None and saved.encode("utf-8") != raw:
        raise ValueError("Stored content bytes cannot be replaced")

    def save():
        with atomic(db):
            current = db.execute(
                "SELECT raw_text FROM contents WHERE id=?", (content_id,)
            ).fetchone()[0]
            if current is not None and current != text:
                raise ValueError("Stored content bytes cannot be replaced")
            if current is None:
                db.execute(
                    "UPDATE contents SET raw_text=? WHERE id=?", (text, content_id)
                )
            locator = f"contents:{content_id}"
            location = db.execute(
                "SELECT state FROM content_locations WHERE content_id=? "
                "AND kind='durable-content' AND locator=?",
                (content_id, locator),
            ).fetchone()
            if location is None:
                db.execute(
                    "INSERT INTO content_locations VALUES(?,'durable-content',?,NULL,'available')",
                    (content_id, locator),
                )
            elif location[0] != "available":
                db.execute(
                    "UPDATE content_locations SET state='available' WHERE content_id=? "
                    "AND kind='durable-content' AND locator=?",
                    (content_id, locator),
                )
        return text

    return save


def hydrate_text(db, content_id, raw):
    """Autocommit entry; grouped writers prepare before opening their transaction."""
    return prepare_text_completion(db, content_id, raw)()


def prepare_git_verification(db, object_id, raw):
    """Check Git's typed header + raw bytes and length before verified 0 -> 1.

    This proves OID/size, not commit/tree parsing, graph closure or availability.
    Imported legacy 'verified' assertions must not bypass P3/P4 revalidation.
    """
    if db.in_transaction:
        raise ValueError("Prepare Git bytes before the writer transaction")
    row = db.execute(
        "SELECT object_format,oid,type,size,verified FROM git_objects WHERE id=?",
        (object_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Missing Git object claim")
    algorithm, oid, kind, size, _ = row
    actual = hashlib.new(
        algorithm, f"{kind} {len(raw)}\0".encode("ascii") + raw
    ).digest()
    if len(raw) != size or actual != oid:
        raise ValueError("Git object size/type/OID mismatch")

    def save():
        with atomic(db):
            db.execute(
                "UPDATE git_objects SET verified=1 WHERE id=? AND verified=0",
                (object_id,),
            )

    return save


def verify_git_object(db, object_id, raw):
    prepare_git_verification(db, object_id, raw)()
