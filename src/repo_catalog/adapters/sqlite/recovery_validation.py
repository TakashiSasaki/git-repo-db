"""Recheck enduring admission invariants without executing recovered schema."""

import codecs
import hashlib
import re
import sqlite3

from repo_catalog.adapters.sqlite.p1_schema import expected_schema
from repo_catalog.domain.p1_core import CoreFailure
from repo_catalog.domain.recovery import BackupValidationError

# INSERT-time replay/current-terminal predicates are deliberately excluded:
# old Coverage evidence remains valid history after a later terminal arrives.
_PERSISTENT_GUARDS = {
    "core": {
        "relation_targets",
        "notes_group_targets",
        "notes_inventory_guard",
        "metadata_same_representation",
        "intrinsic_claim_guard",
        "intrinsic_group_guard",
        "notes_same_representation",
        "notes_claim_format",
        "notes_group_format",
        "core_coverage_members",
    },
    "context": {"coverage_proof_owner", "source_coverage_owner"},
}


def validate_stored_admission_guards(connection: sqlite3.Connection, role: str) -> None:
    """Evaluate trusted packaged enduring BEFORE INSERT predicates on stored rows.

    integrity_check checks CHECK constraints, not relational admission triggers.
    Only packaged SQL is interpreted here; recovered trigger bodies are never run.
    """
    remaining = set(_PERSISTENT_GUARDS[role])
    for kind, name, _, sql in expected_schema(role):
        if kind != "trigger" or name not in remaining:
            continue
        match = re.fullmatch(
            r"CREATE TRIGGER \w+ BEFORE INSERT ON (\w+)\s+WHEN (.*?)\s+BEGIN.*",
            sql,
            flags=re.DOTALL,
        )
        if match is None:
            raise RuntimeError(f"Unsupported packaged recovery guard: {name}")
        table, predicate = match.groups()
        predicate = re.sub(r"\bNEW\.(\w+)", r'"recovery_candidate"."\1"', predicate)
        if connection.execute(
            f'SELECT 1 FROM "{table}" AS recovery_candidate WHERE {predicate} LIMIT 1'
        ).fetchone():
            raise BackupValidationError(
                f"Stored {role} domain admission invariant failed: {name}"
            )
        remaining.remove(name)
    if remaining:
        raise RuntimeError(f"Missing packaged recovery guards: {sorted(remaining)}")


def _skip_sql_quoted(sql: str, position: int) -> int:
    quote = sql[position]
    closing = "]" if quote == "[" else quote
    position += 1
    while position < len(sql):
        if sql[position] == closing:
            if position + 1 < len(sql) and sql[position + 1] == closing:
                position += 2
                continue
            return position + 1
        position += 1
    raise RuntimeError("Unterminated quoted packaged SQL")


def _packaged_checks(sql: str):
    """Extract balanced CHECK expressions only from trusted packaged DDL."""
    position = 0
    while position < len(sql):
        if sql[position] in "'\"`[":
            position = _skip_sql_quoted(sql, position)
            continue
        if sql.startswith("--", position):
            end = sql.find("\n", position)
            position = len(sql) if end < 0 else end + 1
            continue
        if sql.startswith("/*", position):
            end = sql.find("*/", position + 2)
            if end < 0:
                raise RuntimeError("Unterminated packaged SQL comment")
            position = end + 2
            continue
        match = re.match(r"[A-Za-z_][A-Za-z_0-9]*", sql[position:])
        if match is None:
            position += 1
            continue
        token = match.group()
        position += len(token)
        if token.upper() != "CHECK":
            continue
        while position < len(sql) and sql[position].isspace():
            position += 1
        if position >= len(sql) or sql[position] != "(":
            raise RuntimeError("Unsupported packaged CHECK syntax")
        start = position + 1
        depth = 1
        position += 1
        while position < len(sql) and depth:
            if sql.startswith("--", position):
                end = sql.find("\n", position)
                position = len(sql) if end < 0 else end + 1
                continue
            if sql.startswith("/*", position):
                end = sql.find("*/", position + 2)
                if end < 0:
                    raise RuntimeError("Unterminated packaged CHECK comment")
                position = end + 2
                continue
            if sql[position] in "'\"`[":
                position = _skip_sql_quoted(sql, position)
                continue
            if sql[position] == "(":
                depth += 1
            elif sql[position] == ")":
                depth -= 1
            position += 1
        if depth:
            raise RuntimeError("Unbalanced packaged CHECK expression")
        yield sql[start : position - 1]


def validate_stored_checks(connection: sqlite3.Connection, role: str) -> None:
    # SQLite readonly integrity_check can report 'ok' without surfacing failed
    # application-UDF CHECKs. Re-evaluate every trusted expression explicitly.
    # SQLite CHECK accepts NULL: WHERE NOT(expression) preserves that meaning.
    for kind, table, _, sql in expected_schema(role):
        if kind != "table":
            continue
        for expression in _packaged_checks(sql):
            if connection.execute(
                f'SELECT 1 FROM "{table}" WHERE NOT ({expression}) LIMIT 1'
            ).fetchone():
                raise BackupValidationError(
                    f"Stored {role} CHECK constraint failed: {table}"
                )


def validate_stored_text_encoding(connection: sqlite3.Connection, role: str) -> None:
    """Decode actual TEXT bytes before UDF/SQLite automatic decoding can hide it.

    BLOBs (including binary Notes and native Git bytes) are deliberately excluded.
    Chunking bounds Python materialization even for a huge metadata TEXT value.
    The temporary row offsets are read coordinates, never persisted identity.
    """
    chunk_bytes = 65536
    for kind, table, _, _ in expected_schema(role):
        if kind != "table":
            continue
        for column in connection.execute(f'PRAGMA table_xinfo("{table}")'):
            name, declared_type, hidden = column[1], column[2], column[6]
            if declared_type.upper() != "TEXT" or hidden:
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            base = f"FROM \"{table}\" NOT INDEXED WHERE typeof({quoted})='text'"
            rows = connection.execute(
                f"SELECT length(CAST({quoted} AS BLOB)), "
                f"substr(CAST({quoted} AS BLOB),1,{chunk_bytes}) {base}"
            )
            for ordinal, (size, first) in enumerate(rows):
                decoder = codecs.getincrementaldecoder("utf-8")()
                try:
                    if size == 0:
                        first = b""
                    decoder.decode(first, final=size <= chunk_bytes)
                    offset = len(first)
                    while offset < size:
                        raw = connection.execute(
                            f"SELECT substr(CAST({quoted} AS BLOB),?,?) {base} LIMIT 1 OFFSET ?",
                            (offset + 1, min(chunk_bytes, size - offset), ordinal),
                        ).fetchone()[0]
                        if not raw:
                            raise RuntimeError("Stored text changed during validation")
                        offset += len(raw)
                        decoder.decode(raw, final=offset >= size)
                except UnicodeDecodeError:
                    raise BackupValidationError(
                        f"Stored authoritative {role} TEXT {table}.{name} is invalid UTF-8"
                    ) from None


def verify_existing_context_text(connection, digest, expected_bytes, max_bytes, work):
    """Verify one exact existing text key inside the caller's writer transaction.

    Reserve finite allocation and verification work before fetching stored bytes.
    A digest mismatch is positive evidence about retained authority, independently
    of the already checked incoming text. A limit or read error proves no damage.
    """
    work.require("metadata_units", 1)
    row = connection.execute(
        "SELECT length(CAST(text_value AS BLOB)) FROM text_bodies WHERE sha256=?",
        (digest,),
    ).fetchone()
    work.charge("metadata_units", 1)
    if row is None:
        return False
    size = row[0]
    if size > max_bytes:
        raise CoreFailure(
            "BUDGET", "context_text", "existing text exceeds finite payload limit"
        )
    work.require("input_bytes", size)
    # Hashing and exact byte comparison each process the stored representation.
    work.require("verification_bytes", size * 2)
    raw = connection.execute(
        "SELECT CAST(text_value AS BLOB) FROM text_bodies WHERE sha256=?",
        (digest,),
    ).fetchone()[0]
    work.charge("input_bytes", len(raw))
    actual_digest = hashlib.sha256(raw).hexdigest()
    exact = raw == expected_bytes
    work.charge("verification_bytes", len(raw) * 2)
    if actual_digest != digest:
        raise BackupValidationError("Existing retained Context text SHA-256 mismatch")
    if not exact:
        raise ValueError("Exact UTF8 text digest collision")
    return True
