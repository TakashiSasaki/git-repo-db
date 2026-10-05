"""Persistent mapping primitives; all callers must hold the target write lock.

P3 will supply contextual recipes. P2 proves representative repository identity
only, keeping existing local IDs. No URL/body/OID based merging is performed.
"""

import uuid

from scripts.schema_audit import identifier
from scripts.schema_contract import tagged_key

from .archive import decode_key
from .common import ConversionError, strict_json


def lookup(db, record_id, table, relation="identity"):
    rows = db.execute(
        "SELECT target_key FROM id_mappings WHERE record_id=? AND target_table=? AND relation=?",
        (record_id, table, relation),
    ).fetchall()
    if len(rows) > 1:
        raise ConversionError("ID_MAPPING_CONFLICT")
    return rows[0][0] if rows else None


def allocate(db, record_id, table, preferred=None):
    known = lookup(db, record_id, table)
    candidate = (
        tagged_key([("text", preferred.encode())]) if preferred is not None else None
    )
    if known is not None:
        if candidate is not None and candidate != known:
            raise ConversionError("ID_MAPPING_CONFLICT")
        return known
    return candidate or tagged_key([("text", str(uuid.uuid4()).encode())])


def persist(db, record_id, table, key, reason="P2 representative identity"):
    if not db.in_transaction:
        raise ConversionError("MAPPING_REQUIRES_ATOMIC_BATCH")
    previous = lookup(db, record_id, table)
    if previous is not None:
        if previous != key:
            raise ConversionError("ID_MAPPING_CONFLICT")
        return
    if not db.execute(
        "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)
    ).fetchone():
        raise ConversionError("ID_MAPPING_TARGET_MISSING")
    primary = sorted(
        (c for c in db.execute(f"PRAGMA table_xinfo({identifier(table)})") if c["pk"]),
        key=lambda c: c["pk"],
    )
    elements = decode_key(key)
    if not primary or len(primary) != len(elements):
        raise ConversionError("INVALID_TARGET_KEY")
    parameters = [
        value.decode("utf-8") if kind == "text" else value for kind, value in elements
    ]
    predicate = " AND ".join(f"{identifier(c['name'])}=?" for c in primary)
    expressions = ",".join(
        f"typeof({identifier(c['name'])}),CASE WHEN typeof({identifier(c['name'])}) IN ('text','blob') THEN CAST({identifier(c['name'])} AS BLOB) ELSE {identifier(c['name'])} END"
        for c in primary
    )
    found = db.execute(
        f"SELECT {expressions} FROM {identifier(table)} WHERE {predicate}", parameters
    ).fetchone()
    if (
        found is None
        or tagged_key([(found[i * 2], found[i * 2 + 1]) for i in range(len(primary))])
        != key
    ):
        raise ConversionError("ID_MAPPING_TARGET_MISSING")
    if db.execute(
        "SELECT 1 FROM id_mappings WHERE target_table=? AND target_key=? AND relation='identity' AND record_id!=?",
        (table, key, record_id),
    ).fetchone():
        raise ConversionError("ID_MAPPING_COLLISION")
    db.execute(
        "INSERT INTO id_mappings(record_id,target_table,target_key,relation,reason) VALUES(?,?,?,'identity',?)",
        (record_id, table, key, reason),
    )


def repository_projection(record):
    if record.table != "repositories":
        return None
    try:
        values = {}
        for name in ("id", "name", "metadata"):
            kind, raw = record.value(name)
            if kind != "text":
                raise ValueError()
            values[name] = raw.decode("utf-8")
        if not values["id"] or not isinstance(strict_json(values["metadata"]), dict):
            raise ValueError()
        return values
    except (ValueError, UnicodeError):
        raise ConversionError("REPRESENTATIVE_REPOSITORY_INVALID") from None
