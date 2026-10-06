"""Prepare hashes before BEGIN; SQL-only writes under an OS writer lock."""

from .common import canonical, digest


def encode(rows):
    return [
        [{"blob": v.hex()} if isinstance(v, bytes) else v for v in row] for row in rows
    ]


def proof_digest(output):
    return digest(canonical(output).encode())


def row_proof(name, row):
    key = row[:2] if name == "legacy_values" else row[:1]
    return {"key": encode([key])[0], "sha256": proof_digest(encode([row]))}


def next_id(db, table):
    return db.execute(f"SELECT coalesce(max(id),0)+1 FROM {table}").fetchone()[0]
