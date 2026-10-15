"""Isolated Core admission experiment; never used by the production initializer.

The supported API owns transactions and SQL preparation. Generic SQL is read-only.
Full relation membership is a recoverable value in its semantic composite key,
not a digest, generated group ID, publication seal, or mutable current pointer.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


def encode(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class OID:
    object_format: str
    full_oid: str

    def __post_init__(self) -> None:
        lengths = {"sha1": 40, "sha256": 64}
        if (
            self.object_format not in lengths
            or len(self.full_oid) != lengths.get(self.object_format)
            or any(c not in "0123456789abcdef" for c in self.full_oid)
        ):
            raise ValueError("a lowercase full typed Git OID is required")

    @property
    def key(self) -> tuple[str, str]:
        return self.object_format, self.full_oid


@dataclass(frozen=True)
class Provenance:
    """Actual original attribution/coordinates; receiver arrival is not a key."""

    source: str
    observation: str
    coordinate: str
    decoder: str
    decoder_version: str
    qualification: str = "reported"

    def __post_init__(self) -> None:
        if self.qualification not in {"reported", "receiver_intrinsic"}:
            raise ValueError("unsupported provenance qualification")
        if any(not isinstance(v, str) or not v for v in self.key):
            raise ValueError("all genuine evidence coordinates must be supplied")

    @property
    def key(self) -> tuple[str, ...]:
        return (
            self.source,
            self.observation,
            self.coordinate,
            self.decoder,
            self.decoder_version,
            self.qualification,
        )


@dataclass(frozen=True)
class Parent:
    """Ordinal must be actually reported; partial groups may have holes."""

    ordinal: int
    target: OID

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise ValueError("parent ordinal must be an evidenced nonnegative integer")

    @property
    def value(self) -> list[object]:
        return [self.ordinal, *self.target.key]


@dataclass(frozen=True)
class ParentGroup:
    subject: OID
    scope: str
    status: str
    parents: tuple[Parent, ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        if not self.scope or self.status not in {
            "unknown",
            "partial",
            "known_empty",
            "complete",
        }:
            raise ValueError("explicit supported scope/status required")
        slots = [p.ordinal for p in self.parents]
        if slots != sorted(set(slots)):
            raise ValueError("parent slots must be distinct and in asserted order")
        if any(
            p.target.object_format != self.subject.object_format for p in self.parents
        ):
            raise ValueError("one native Git relation cannot mix object formats")
        if self.status in {"unknown", "known_empty"} and self.parents:
            raise ValueError("unknown/known-empty cannot carry members")
        if self.status == "complete" and (
            not self.parents or slots != list(range(len(self.parents)))
        ):
            raise ValueError("use known_empty or a complete contiguous asserted order")

    @property
    def key(self) -> tuple[str, ...]:
        return (
            *self.subject.key,
            "commit_parents",
            self.scope,
            self.status,
            encode([p.value for p in self.parents]),
            *self.provenance.key,
        )


_PROVENANCE = (
    "source TEXT NOT NULL, observation TEXT NOT NULL, coordinate TEXT NOT NULL, "
    "decoder TEXT NOT NULL, decoder_version TEXT NOT NULL, "
    "qualification TEXT NOT NULL CHECK(qualification IN ('reported','receiver_intrinsic'))"
)
_PKEY = "source,observation,coordinate,decoder,decoder_version,qualification"
_GROUP_COLUMNS = "object_format,full_oid,relation,scope,status,membership," + _PKEY
_GROUP_DEFS = (
    "object_format TEXT NOT NULL, full_oid TEXT NOT NULL, relation TEXT NOT NULL, "
    "scope TEXT NOT NULL, status TEXT NOT NULL, membership TEXT NOT NULL, "
    + _PROVENANCE
)
_CLAIM_COLUMNS = "object_format,full_oid,field,value," + _PKEY
_SCHEMA = f"""
CREATE TABLE repositories(repository_uuidv4 TEXT PRIMARY KEY NOT NULL) WITHOUT ROWID;
CREATE TABLE objects(
    object_format TEXT NOT NULL CHECK(object_format IN ('sha1','sha256')),
    full_oid TEXT NOT NULL CHECK(
        full_oid NOT GLOB '*[^0-9a-f]*' AND
        length(full_oid)=CASE object_format WHEN 'sha1' THEN 40 ELSE 64 END),
    PRIMARY KEY(object_format,full_oid)
) WITHOUT ROWID;
CREATE TABLE claims(
    object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
    field TEXT NOT NULL CHECK(field IN ('type','size')),
    value TEXT NOT NULL CHECK(json_valid(value)), {_PROVENANCE},
    PRIMARY KEY({_CLAIM_COLUMNS}),
    UNIQUE(object_format,full_oid,field,{_PKEY}),
    FOREIGN KEY(object_format,full_oid) REFERENCES objects(object_format,full_oid)
) WITHOUT ROWID;
CREATE TABLE parent_groups(
    {_GROUP_DEFS},
    CHECK(relation='commit_parents'),
    CHECK(status IN ('unknown','partial','known_empty','complete')),
    CHECK(json_valid(membership) AND json_type(membership)='array'),
    PRIMARY KEY({_GROUP_COLUMNS}),
    FOREIGN KEY(object_format,full_oid) REFERENCES objects(object_format,full_oid)
) WITHOUT ROWID;
CREATE TABLE parent_members(
    {_GROUP_DEFS},
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    target_format TEXT NOT NULL, target_oid TEXT NOT NULL,
    PRIMARY KEY({_GROUP_COLUMNS},ordinal),
    FOREIGN KEY({_GROUP_COLUMNS}) REFERENCES parent_groups({_GROUP_COLUMNS}),
    FOREIGN KEY(target_format,target_oid) REFERENCES objects(object_format,full_oid)
) WITHOUT ROWID;
CREATE TRIGGER membership_guard BEFORE INSERT ON parent_members
WHEN NOT EXISTS (
    SELECT 1 FROM json_each(NEW.membership) j
    WHERE json_extract(j.value,'$[0]')=NEW.ordinal
      AND json_extract(j.value,'$[1]')=NEW.target_format
      AND json_extract(j.value,'$[2]')=NEW.target_oid
) BEGIN SELECT RAISE(ABORT,'member does not belong to immutable group'); END;
CREATE TABLE representations(
    object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
    native_type TEXT NOT NULL CHECK(native_type='commit'),
    body BLOB NOT NULL, size INTEGER NOT NULL CHECK(size=length(body)),
    sha256 TEXT NOT NULL,
    PRIMARY KEY(object_format,full_oid,native_type),
    FOREIGN KEY(object_format,full_oid) REFERENCES objects(object_format,full_oid)
) WITHOUT ROWID;
CREATE TABLE commit_trees(
    object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
    native_type TEXT NOT NULL CHECK(native_type='commit'),
    tree_format TEXT NOT NULL, tree_oid TEXT NOT NULL,
    PRIMARY KEY(object_format,full_oid,native_type,tree_format,tree_oid),
    FOREIGN KEY(object_format,full_oid,native_type)
      REFERENCES representations(object_format,full_oid,native_type),
    FOREIGN KEY(tree_format,tree_oid) REFERENCES objects(object_format,full_oid)
) WITHOUT ROWID;
CREATE TABLE checked_claims(
    object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
    field TEXT NOT NULL, value TEXT NOT NULL, {_PROVENANCE},
    native_type TEXT NOT NULL,
    PRIMARY KEY({_CLAIM_COLUMNS},native_type),
    FOREIGN KEY({_CLAIM_COLUMNS}) REFERENCES claims({_CLAIM_COLUMNS}),
    FOREIGN KEY(object_format,full_oid,native_type)
      REFERENCES representations(object_format,full_oid,native_type)
) WITHOUT ROWID;
CREATE TABLE checked_groups(
    {_GROUP_DEFS}, native_type TEXT NOT NULL,
    PRIMARY KEY({_GROUP_COLUMNS},native_type),
    FOREIGN KEY({_GROUP_COLUMNS}) REFERENCES parent_groups({_GROUP_COLUMNS}),
    FOREIGN KEY(object_format,full_oid,native_type)
      REFERENCES representations(object_format,full_oid,native_type)
) WITHOUT ROWID;
"""


class Core:
    """Application connection boundary, not protection against its DB owner.

    No body fetcher, Context path, network client or mutable revision exists.
    SQLite triggers reject fact mutation; authorizer rejects generic DML/DDL and
    PRAGMAs. Statement caching is disabled: authorization must run at preparation
    on every call, including after an internal admission capability was closed.
    """

    def __init__(self, path: Path):
        self._admitting = True
        self._db = sqlite3.connect(path, isolation_level=None, cached_statements=0)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA recursive_triggers=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        tables = [
            r[0]
            for r in self._db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        ]
        if not tables:
            self._db.executescript(_SCHEMA)
            tables = [
                r[0]
                for r in self._db.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                )
            ]
            for table in tables:
                for action in ("UPDATE", "DELETE"):
                    self._db.execute(
                        f"CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} "
                        "BEGIN SELECT RAISE(ABORT,'Core facts are immutable'); END"
                    )
        self._admitting = False
        self._db.set_authorizer(self._authorize)

    def _authorize(self, action: int, _a: str, _b: str, _db: str, _trigger: str) -> int:
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        if self._admitting:
            allowed |= {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_TRANSACTION}
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self._admitting:
            raise RuntimeError("nested admission not supported")
        self._admitting = True
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        finally:
            self._admitting = False

    def close(self) -> None:
        self._db.close()

    def sql(self, statement: str, parameters: tuple = ()) -> list[sqlite3.Row]:
        """Read-only SQL inspection through the same supported connection."""
        if self._admitting:
            raise RuntimeError("generic SQL cannot borrow an admission capability")
        return self._db.execute(statement, parameters).fetchall()

    def _insert(self, table: str, values: tuple) -> None:
        self._db.execute(
            f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)}) "
            "ON CONFLICT DO NOTHING",
            values,
        )

    def _object(self, oid: OID) -> None:
        self._insert("objects", oid.key)

    def admit_repository(self, repository_uuidv4: str) -> None:
        parsed = UUID(repository_uuidv4)
        if parsed.version != 4 or str(parsed) != repository_uuidv4:
            raise ValueError("permanent repository identity must be canonical UUIDv4")
        with self._transaction():
            self._insert("repositories", (repository_uuidv4,))

    def admit_object(self, oid: OID) -> None:
        with self._transaction():
            self._object(oid)

    @staticmethod
    def _value(field: str, value: object) -> str:
        if field == "type":
            if value is not None and value not in ("commit", "tree", "blob", "tag"):
                raise ValueError("invalid reported native type")
        elif field == "size":
            if value is not None and (type(value) is not int or not 0 <= value < 2**63):
                raise ValueError("invalid reported size")
        else:
            raise ValueError("unsupported field")
        return encode(["unknown"] if value is None else ["known", value])

    def _claim(
        self, oid: OID, field: str, value: object, provenance: Provenance
    ) -> tuple:
        key = (*oid.key, field, self._value(field, value), *provenance.key)
        # One actual immutable evidence coordinate cannot silently change value.
        rows = self._db.execute(
            f"SELECT value FROM claims WHERE object_format=? AND full_oid=? "
            f"AND field=? AND {' AND '.join(f'{c}=?' for c in _PKEY.split(','))}",
            (*oid.key, field, *provenance.key),
        ).fetchall()
        if rows and rows[0][0] != key[3]:
            raise ValueError("inconsistent immutable evidence coordinate")
        self._object(oid)
        self._insert("claims", key)
        return key

    def admit_claim(
        self, oid: OID, field: str, value: object, provenance: Provenance
    ) -> None:
        self._value(field, value)
        if provenance.qualification != "reported":
            raise ValueError("report API cannot assert receiver-derived evidence")
        with self._transaction():
            self._claim(oid, field, value, provenance)

    def _group(
        self, group: ParentGroup, after_member: Callable[[int], None] | None = None
    ) -> None:
        old = self._db.execute(
            f"SELECT status,membership FROM parent_groups WHERE "
            "object_format=? AND full_oid=? AND relation=? AND scope=? AND "
            f"{' AND '.join(f'{c}=?' for c in _PKEY.split(','))}",
            (*group.subject.key, "commit_parents", group.scope, *group.provenance.key),
        ).fetchone()
        if old is not None and tuple(old) != (group.status, group.key[5]):
            raise ValueError("inconsistent immutable group evidence coordinate")
        self._object(group.subject)
        self._insert("parent_groups", group.key)
        for index, member in enumerate(group.parents):
            self._object(member.target)
            self._insert("parent_members", (*group.key, *member.value))
            if after_member is not None:
                after_member(index)

    def admit_group(
        self, group: ParentGroup, *, after_member: Callable[[int], None] | None = None
    ) -> None:
        if group.provenance.qualification != "reported":
            raise ValueError("report API cannot assert receiver-derived evidence")
        with self._transaction():
            self._group(group, after_member)

    def admit_verified_commit(
        self, oid: OID, body: bytes, *, declared_size: int
    ) -> None:
        """Narrow real intrinsic verifier; stores only permitted commit bodies.

        The experimental parser accepts one tree, zero or more ordered parents,
        one author and one committer; rejects extension/multiline headers. It
        checks only these native fields, without claiming graph closure, author
        authenticity, decoder-independent text, or present byte health forever.
        """
        if (
            type(body) is not bytes
            or type(declared_size) is not int
            or len(body) != declared_size
        ):
            raise ValueError("exact native body size required")
        digest = hashlib.new(
            oid.object_format, f"commit {len(body)}\0".encode() + body
        ).hexdigest()
        if digest != oid.full_oid:
            raise ValueError("native commit OID mismatch")
        headers, separator, _message = body.partition(b"\n\n")
        if not separator:
            raise ValueError("commit requires header/body separator")
        lines = headers.split(b"\n")
        if not lines or not lines[0].startswith(b"tree "):
            raise ValueError("commit requires first tree header")
        tree = OID(oid.object_format, lines[0][5:].decode("ascii"))
        parents: list[Parent] = []
        index = 1
        while index < len(lines) and lines[index].startswith(b"parent "):
            parents.append(
                Parent(
                    len(parents),
                    OID(oid.object_format, lines[index][7:].decode("ascii")),
                )
            )
            index += 1
        if (
            len(lines[index:]) != 2
            or re.fullmatch(
                rb"author [^\n\x00<>]*<[^\n\x00<>]*> -?[0-9]+ [+-][0-9]{4}",
                lines[index],
            )
            is None
            or re.fullmatch(
                rb"committer [^\n\x00<>]*<[^\n\x00<>]*> -?[0-9]+ [+-][0-9]{4}",
                lines[index + 1],
            )
            is None
        ):
            raise ValueError("unsupported or malformed commit headers")
        base = ("receiver-intrinsic", f"git:{oid.object_format}:{oid.full_oid}")
        provenance = Provenance(
            *base,
            "commit-parent-headers",
            "spike-native-commit",
            "1",
            "receiver_intrinsic",
        )
        group = ParentGroup(
            oid,
            "native-parent-header-list",
            "complete" if parents else "known_empty",
            tuple(parents),
            provenance,
        )
        with self._transaction():
            self._object(oid)
            self._object(tree)
            old = self._db.execute(
                "SELECT body FROM representations WHERE object_format=? AND full_oid=?",
                oid.key,
            ).fetchone()
            if old is not None and old[0] != body:
                raise ValueError("conflicting exact representation")
            self._insert(
                "representations",
                (*oid.key, "commit", body, len(body), hashlib.sha256(body).hexdigest()),
            )
            self._insert("commit_trees", (*oid.key, "commit", *tree.key))
            for field, value in (("type", "commit"), ("size", len(body))):
                p = Provenance(
                    *base,
                    f"native-{field}",
                    "spike-native-commit",
                    "1",
                    "receiver_intrinsic",
                )
                key = self._claim(oid, field, value, p)
                self._insert("checked_claims", (*key, "commit"))
            self._group(group)
            self._insert("checked_groups", (*group.key, "commit"))

    def scalar(self, oid: OID, field: str) -> dict:
        rows = self.sql(
            f"SELECT c.*, EXISTS(SELECT 1 FROM checked_claims v WHERE "
            f"{' AND '.join(f'v.{c}=c.{c}' for c in _CLAIM_COLUMNS.split(','))}) checked "
            "FROM claims c WHERE object_format=? AND full_oid=? AND field=?",
            (*oid.key, field),
        )
        alternatives = [
            {
                "value": json.loads(r["value"]),
                "checked": bool(r["checked"]),
                "provenance": [r[c] for c in _PKEY.split(",")],
            }
            for r in rows
        ]
        checked = {encode(r["value"]) for r in alternatives if r["checked"]}
        known_reports = {
            encode(r["value"]) for r in alternatives if r["value"][0] == "known"
        }
        return {
            "canonical": json.loads(next(iter(checked))) if len(checked) == 1 else None,
            "reported_conflict": len(known_reports) > 1,
            "alternatives": alternatives,
        }

    def parents(self, oid: OID) -> dict:
        rows = self.sql(
            f"SELECT g.*, EXISTS(SELECT 1 FROM checked_groups v WHERE "
            f"{' AND '.join(f'v.{c}=g.{c}' for c in _GROUP_COLUMNS.split(','))}) checked "
            "FROM parent_groups g WHERE object_format=? AND full_oid=?",
            oid.key,
        )
        alternatives = [
            {
                "status": r["status"],
                "parents": json.loads(r["membership"]),
                "scope": r["scope"],
                "checked": bool(r["checked"]),
                "provenance": [r[c] for c in _PKEY.split(",")],
            }
            for r in rows
        ]
        slots: dict[int, set[tuple[str, str]]] = {}
        complete = set()
        closed_slots = []
        checked = set()
        for group in alternatives:
            if group["status"] in {"complete", "known_empty"}:
                complete.add(encode(group["parents"]))
                closed_slots.append({p[0] for p in group["parents"]})
            if group["checked"]:
                checked.add(encode(group["parents"]))
            for ordinal, fmt, full_oid in group["parents"]:
                slots.setdefault(ordinal, set()).add((fmt, full_oid))
        return {
            "canonical": json.loads(next(iter(checked))) if len(checked) == 1 else None,
            # A complete/known-empty native parent list also asserts absence
            # outside its listed slots. A partial extra slot contradicts that
            # closure even when no two positive targets share an ordinal.
            "reported_conflict": len(complete) > 1
            or any(len(v) > 1 for v in slots.values())
            or any(set(slots) - asserted_slots for asserted_slots in closed_slots),
            "alternatives": alternatives,
        }
