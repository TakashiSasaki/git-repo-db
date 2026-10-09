"""Admission of portable equivalence evidence with atomic cancellation promotion."""

import hashlib
import json
import sqlite3
import uuid

from repo_catalog.adapters.sqlite.json_contracts import validate_record
from repo_catalog.domain.models import CatalogError


class IdentityRelations:
    def __init__(self, connection):
        self.db = connection

    def admit(self, kind, record):
        if kind not in ("relation", "cancellation"):
            raise CatalogError("INVALID_ARGUMENT", "Unknown identity evidence kind")
        key = "relation_uuidv4" if kind == "relation" else "cancellation_uuidv4"
        ident = record.get(key)
        try:
            valid = (
                str(uuid.UUID(ident, version=4)) == ident
                and uuid.UUID(ident).version == 4
            )
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise CatalogError("INVALID_ARGUMENT", "Canonical UUIDv4 is required")
        table = (
            "identity_relations"
            if kind == "relation"
            else "identity_relation_cancellations"
        )
        columns = [row[1] for row in self.db.execute(f"PRAGMA table_info({table})")]
        if set(record) != set(columns):
            raise CatalogError(
                "INVALID_ARGUMENT", "Identity evidence fields do not match schema"
            )
        missing = validate_record(self.db, table, record, allow_missing=True)
        raw = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(raw.encode()).digest()
        self.db.execute("SAVEPOINT identity_admission")
        try:
            existing = self.db.execute(
                f"SELECT * FROM {table} WHERE {key}=?", (ident,)
            ).fetchone()
            if existing is not None:
                if list(existing) == [record[col] for col in columns]:
                    state = "duplicate"
                else:
                    self._stage(
                        ident, digest, kind, raw, "immutable_identity_collision"
                    )
                    state = "conflict"
            else:
                try:
                    if missing:
                        self._stage(ident, digest, kind, raw, "JSON_DEPENDENCY_MISSING")
                        self.db.execute("RELEASE identity_admission")
                        return "staged"
                    self.db.execute(
                        f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                        [record[col] for col in columns],
                    )
                    state = "accepted"
                except sqlite3.IntegrityError as cause:
                    self._stage(ident, digest, kind, raw, str(cause))
                    state = "staged"
            if state in ("accepted", "duplicate"):
                self.db.execute(
                    "DELETE FROM identity_relation_staging WHERE record_uuidv4=? AND content_sha256=?",
                    (ident, digest),
                )
            if kind == "relation" and state in ("accepted", "duplicate"):
                # No commit or observer-visible activation occurs before every
                # cancellation that arrived first has been applied.
                for row in self.db.execute(
                    "SELECT record_uuidv4,content_sha256,record_json FROM identity_relation_staging WHERE kind='cancellation' AND json_extract(record_json,'$.relation_uuidv4')=?",
                    (ident,),
                ).fetchall():
                    result = self.admit("cancellation", json.loads(row[2]))
                    if result in ("accepted", "duplicate"):
                        self.db.execute(
                            "DELETE FROM identity_relation_staging WHERE record_uuidv4=? AND content_sha256=?",
                            (row[0], row[1]),
                        )
            self.db.execute(
                "UPDATE database_identity SET publication_seq=publication_seq+1 WHERE singleton=1"
            )
            self.db.execute("RELEASE identity_admission")
            return state
        except BaseException:
            self.db.execute("ROLLBACK TO identity_admission")
            self.db.execute("RELEASE identity_admission")
            raise

    def _stage(self, ident, digest, kind, raw, reason):
        self.db.execute(
            "INSERT OR IGNORE INTO identity_relation_staging VALUES(?,?,?,?,?)",
            (ident, digest, kind, raw, reason),
        )
