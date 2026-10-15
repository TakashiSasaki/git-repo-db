"""Isolated ADR 0014/0018–0025 notes-admission spike; never a product initializer.

Only the supported API is an admission boundary. A privileged SQLite client can
remove triggers; a privileged Git client can replace files underneath reads.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


class Refused(ValueError):
    """Invalid/unsupported evidence; this does not diagnose catalog corruption."""


class BudgetStop(Refused):
    """An honest finite work stop, with no body or incomplete proof admission."""


def typed_oid(fmt: str, oid: str) -> None:
    width = {"sha1": 40, "sha256": 64}.get(fmt)
    if width is None or re.fullmatch(r"[0-9a-f]{%d}" % width, oid) is None:
        raise Refused("expected a full lowercase typed OID")


def uuid4(value: str) -> None:
    parsed = UUID(value)
    if parsed.version != 4 or str(parsed) != value:
        raise Refused("expected canonical UUIDv4")


def native_oid(fmt: str, kind: str, body: bytes) -> str:
    return hashlib.new(fmt, f"{kind} {len(body)}\0".encode() + body).hexdigest()


@dataclass(frozen=True)
class Capture:
    origin: str
    capture: str
    repository: str
    source: str
    ref: str
    fmt: str
    root: str

    @property
    def pair(self) -> tuple[str, str]:
        return self.origin, self.capture

    def validate(self) -> None:
        for value in (*self.pair, self.repository):
            uuid4(value)
        typed_oid(self.fmt, self.root)
        if not self.source or not self.ref.startswith("refs/"):
            raise Refused("genuine source and full nominated ref required")


@dataclass(frozen=True)
class Limits:
    """Small experiment defaults, not intended product defaults."""

    note_bytes: int = 4096
    input_bytes: int = 65536
    proof_objects: int = 64
    metadata_units: int = 256

    def __post_init__(self) -> None:
        for value in vars(self).values():
            if type(value) is not int or not 0 < value <= 2**63 - 1:
                raise ValueError("limits must be positive finite SQLite integers")


class RequestWork:
    """Separate Operational counters for an explicitly named acquisition request.

    Explicit start versus resume prevents missing accounting from becoming zero.
    Synchronous accounting covers normal failures/rollbacks and reopen, not a
    kill between actual external I/O and charge; production needs reservations.
    """

    def __init__(
        self, path: Path, repository: str, request: str, limits: Limits, *, start: bool
    ) -> None:
        uuid4(repository)
        if not request:
            raise ValueError("explicit acquisition request name required")
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS request_work ("
            "repository TEXT NOT NULL, request TEXT NOT NULL, settings TEXT NOT NULL, "
            "input_bytes INTEGER NOT NULL DEFAULT 0, "
            "proof_objects INTEGER NOT NULL DEFAULT 0, "
            "metadata_units INTEGER NOT NULL DEFAULT 0, "
            "PRIMARY KEY(repository, request)) WITHOUT ROWID"
        )
        self.key, self._limits = (repository, request), limits
        settings = json.dumps(vars(limits), sort_keys=True)
        if start:
            self.db.execute(
                "INSERT INTO request_work(repository, request, settings) VALUES(?,?,?)",
                (*self.key, settings),
            )
        elif (
            self.db.execute(
                "SELECT 1 FROM request_work WHERE repository=? AND request=? AND settings=?",
                (*self.key, settings),
            ).fetchone()
            is None
        ):
            raise BudgetStop(
                "prior request accounting unavailable or settings differ; cannot resume"
            )

    @property
    def limits(self) -> Limits:
        return self._limits

    @limits.setter
    def limits(self, limits: Limits) -> None:
        """An explicit finite settings change; counters never reset."""
        self.db.execute(
            "UPDATE request_work SET settings=? WHERE repository=? AND request=?",
            (json.dumps(vars(limits), sort_keys=True), *self.key),
        )
        self._limits = limits

    def counts(self) -> dict[str, int]:
        row = self.db.execute(
            "SELECT input_bytes, proof_objects, metadata_units FROM request_work "
            "WHERE repository=? AND request=?",
            self.key,
        ).fetchone()
        if row is None:
            raise BudgetStop("prior request accounting unavailable")
        return dict(zip(("input_bytes", "proof_objects", "metadata_units"), row))

    def remaining(self, unit: str) -> int:
        return max(0, getattr(self.limits, unit) - self.counts()[unit])

    def require(self, unit: str, amount: int = 1) -> None:
        if self.remaining(unit) < amount:
            raise BudgetStop(f"{unit} limit")

    def charge(self, unit: str, amount: int) -> None:
        if unit not in self.counts() or amount < 0:
            raise ValueError("invalid accounting unit")
        # Called after actual bounded work. No surrounding Core rollback can undo it.
        self.db.execute(
            f"UPDATE request_work SET {unit}={unit}+? WHERE repository=? AND request=?",
            (amount, *self.key),
        )
        if self.counts()[unit] > getattr(self.limits, unit):
            raise BudgetStop(f"{unit} limit")

    def metadata(self) -> None:
        self.require("metadata_units")
        self.charge("metadata_units", 1)


class GitInput:
    """Local objects only: no fetch, remote, target-body or history traversal."""

    def __init__(self, repository: Path, work: RequestWork) -> None:
        self.repository, self.work = repository, work
        self.fmt = self.command("rev-parse", "--show-object-format").decode().strip()

    def command(self, *args: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(self.repository), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            raise Refused("local Git object/ref unavailable")
        return result.stdout

    def stream(self, *args: str) -> bytes:
        """Read bounded ephemeral input and charge even an exhausted final chunk."""
        process = subprocess.Popen(
            ["git", "-C", str(self.repository), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        chunks: list[bytes] = []
        try:
            assert process.stdout is not None
            while True:
                remaining = self.work.remaining("input_bytes")
                chunk = process.stdout.read(min(4096, remaining + 1))
                if not chunk:
                    break
                self.work.charge("input_bytes", len(chunk))
                chunks.append(chunk)
            if process.wait() != 0:
                raise Refused("local Git read failed")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout is not None:
                process.stdout.close()
        return b"".join(chunks)

    def discover(self, nominated: tuple[str, ...] = ()) -> list[str]:
        self.work.metadata()
        refs: set[str] = set()
        observed = self.stream("for-each-ref", "--format=%(refname)", "refs/notes/")
        for ref in (*observed.decode().splitlines(), *nominated):
            self.work.metadata()
            refs.add(ref)
        return sorted(refs)

    def object(self, oid: str, *, proof: bool, note: bool = False) -> tuple[str, bytes]:
        typed_oid(self.fmt, oid)
        self.work.metadata()
        if proof:
            self.work.require("proof_objects")
            self.work.charge("proof_objects", 1)
        kind = self.command("cat-file", "-t", oid).decode().strip()
        size = int(self.command("cat-file", "-s", oid))
        if note and (kind != "blob" or size > self.work.limits.note_bytes):
            if kind != "blob":
                raise Refused("note must have native blob type")
            raise BudgetStop("individual raw-note size limit")
        if proof and kind not in {"tree", "commit"}:
            raise Refused("captured structural object must be commit or tree")
        # No unproven bytes survive outside this bounded ephemeral buffer.
        body = self.stream("cat-file", kind, oid)
        if len(body) != size or native_oid(self.fmt, kind, body) != oid:
            raise Refused("native type/size/OID verification failed")
        return kind, body


def tree_entries(body: bytes, fmt: str) -> dict[bytes, tuple[bytes, str]]:
    """Parse native binary entries; retain no unrelated descendant bodies."""
    width = {"sha1": 20, "sha256": 32}[fmt]
    entries: dict[bytes, tuple[bytes, str]] = {}
    offset = 0
    while offset < len(body):
        try:
            space, zero = body.index(b" ", offset), body.index(b"\0", offset)
        except ValueError as exc:
            raise Refused("malformed tree") from exc
        mode, name = body[offset:space], body[space + 1 : zero]
        end = zero + 1 + width
        if (
            not re.fullmatch(rb"[0-7]+", mode)
            or not name
            or b"/" in name
            or name in entries
            or end > len(body)
        ):
            raise Refused("malformed tree entry")
        entries[name] = mode, body[zero + 1 : end].hex()
        offset = end
    return entries


SCHEMA = """
CREATE TABLE git_objects (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
 PRIMARY KEY(object_format, full_oid)) WITHOUT ROWID;
CREATE TABLE captures (
 origin TEXT NOT NULL, capture TEXT NOT NULL, repository TEXT NOT NULL,
 source TEXT NOT NULL, ref TEXT NOT NULL, object_format TEXT NOT NULL,
 root TEXT NOT NULL, PRIMARY KEY(origin,capture),
 FOREIGN KEY(object_format,root) REFERENCES git_objects) WITHOUT ROWID;
CREATE TABLE reports (
 origin TEXT NOT NULL, capture TEXT NOT NULL, object_format TEXT NOT NULL,
 target TEXT NOT NULL, note TEXT NOT NULL, provenance TEXT NOT NULL,
 qualification TEXT NOT NULL CHECK(qualification='unauthenticated-report'),
 PRIMARY KEY(origin,capture,object_format,target,note,provenance,qualification),
 FOREIGN KEY(origin,capture) REFERENCES captures,
 FOREIGN KEY(object_format,target) REFERENCES git_objects,
 FOREIGN KEY(object_format,note) REFERENCES git_objects) WITHOUT ROWID;
CREATE TABLE checked_structures (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL,
 native_type TEXT NOT NULL CHECK(native_type IN ('commit','tree')),
 body BLOB NOT NULL, PRIMARY KEY(object_format,full_oid),
 FOREIGN KEY(object_format,full_oid) REFERENCES git_objects) WITHOUT ROWID;
CREATE TABLE note_bodies (
 object_format TEXT NOT NULL, full_oid TEXT NOT NULL, size INTEGER NOT NULL,
 digest_sha256 TEXT NOT NULL, body BLOB NOT NULL,
 PRIMARY KEY(object_format,full_oid),
 UNIQUE(object_format,full_oid,size,digest_sha256),
 CHECK(size=length(body)),
 FOREIGN KEY(object_format,full_oid) REFERENCES git_objects) WITHOUT ROWID;
CREATE TABLE note_roles (
 origin TEXT NOT NULL, capture TEXT NOT NULL, object_format TEXT NOT NULL,
 target TEXT NOT NULL, note TEXT NOT NULL, path TEXT NOT NULL,
 proof_chain TEXT NOT NULL, checker TEXT NOT NULL CHECK(checker='native-notes-v1'),
 size INTEGER NOT NULL, digest_sha256 TEXT NOT NULL,
 PRIMARY KEY(origin,capture,object_format,target,note,path,proof_chain,checker),
 FOREIGN KEY(origin,capture) REFERENCES captures,
 FOREIGN KEY(object_format,target) REFERENCES git_objects,
 FOREIGN KEY(object_format,note,size,digest_sha256)
   REFERENCES note_bodies(object_format,full_oid,size,digest_sha256)) WITHOUT ROWID;
CREATE TABLE proof_links (
 origin TEXT NOT NULL, capture TEXT NOT NULL, object_format TEXT NOT NULL,
 target TEXT NOT NULL, note TEXT NOT NULL, path TEXT NOT NULL,
 proof_chain TEXT NOT NULL, checker TEXT NOT NULL,
 ordinal INTEGER NOT NULL, structural_oid TEXT NOT NULL,
 PRIMARY KEY(origin,capture,object_format,target,note,path,proof_chain,checker,ordinal),
 FOREIGN KEY(origin,capture,object_format,target,note,path,proof_chain,checker)
   REFERENCES note_roles,
 FOREIGN KEY(object_format,structural_oid)
   REFERENCES checked_structures(object_format,full_oid)) WITHOUT ROWID;
"""


class NotesCore:
    """Receiver-local, role-scoped content API, not a generic blob/CAS service."""

    def __init__(self, path: Path) -> None:
        fresh = not path.exists()
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA recursive_triggers=ON")
        if fresh:
            self.db.executescript(SCHEMA)
            tables = self.db.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ).fetchall()
            for (table,) in tables:
                for operation in ("UPDATE", "DELETE"):
                    self.db.execute(
                        f"CREATE TRIGGER {table}_{operation} BEFORE {operation} "
                        f"ON {table} BEGIN SELECT RAISE(ABORT,'INSERT-only'); END"
                    )
            self.db.commit()

    def _nominal(self, fmt: str, oid: str) -> None:
        typed_oid(fmt, oid)
        self.db.execute(
            "INSERT INTO git_objects VALUES(?,?) ON CONFLICT DO NOTHING", (fmt, oid)
        )

    def _capture(self, value: Capture) -> None:
        value.validate()
        row = self.db.execute(
            "SELECT * FROM captures WHERE origin=? AND capture=?", value.pair
        ).fetchone()
        expected = tuple(vars(value).values())
        if row is not None and row != expected:
            raise Refused("immutable Capture binding conflict")
        self._nominal(value.fmt, value.root)
        self.db.execute(
            "INSERT INTO captures VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
            expected,
        )

    def metadata(self, fmt: str, oid: str) -> None:
        """Ordinary blob identity is allowed without body/type/size claims."""
        with self.db:
            self._nominal(fmt, oid)

    def report(
        self,
        value: Capture,
        target: str,
        note: str,
        provenance: str,
        work: RequestWork,
        *,
        sender_verified: bool = False,
    ) -> None:
        del sender_verified  # Not receiver authority and never a canonicality flag.
        if not provenance:
            raise Refused("genuine original report provenance required")
        if work.key[0] != value.repository:
            raise Refused("request repository mismatch")
        work.metadata()
        with self.db:
            self._capture(value)
            self._nominal(value.fmt, target)
            self._nominal(value.fmt, note)
            self.db.execute(
                "INSERT INTO reports VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (
                    *value.pair,
                    value.fmt,
                    target,
                    note,
                    provenance,
                    "unauthenticated-report",
                ),
            )

    def admit_note(
        self,
        value: Capture,
        target: str,
        note: str,
        git: GitInput,
        *,
        declared_size: int,
        declared_digest: str,
        interrupt_after_body: bool = False,
    ) -> None:
        """Validate precisely one mapping, then publish its body/proof atomically."""
        value.validate()
        typed_oid(value.fmt, target)
        typed_oid(value.fmt, note)
        if git.fmt != value.fmt:
            raise Refused("object-format mismatch")
        if git.work.key[0] != value.repository:
            raise Refused("request repository mismatch")
        proof: list[tuple[str, str, bytes]] = []
        oid = value.root
        kind, body = git.object(oid, proof=True)
        proof.append((oid, kind, body))
        if kind == "commit":
            first = body.partition(b"\n")[0]
            if not re.fullmatch(rb"tree [0-9a-f]+", first):
                raise Refused("unsupported commit tree header")
            oid = first[5:].decode()
            kind, body = git.object(oid, proof=True)
            if kind != "tree":
                raise Refused("commit must link to a tree")
            proof.append((oid, kind, body))
        path: list[str] = []
        suffix = target
        while True:
            entries = tree_entries(body, value.fmt)
            leaf, directory = suffix.encode(), suffix[:2].encode()
            has_leaf = leaf in entries
            has_dir = len(suffix) > 2 and directory in entries
            if has_leaf and has_dir:
                raise Refused("ambiguous supported notes mapping")
            if has_leaf:
                mode, found = entries[leaf]
                if mode != b"100644" or found != note:
                    raise Refused(
                        "unsupported note mode or claimed association mismatch"
                    )
                path.append(leaf.decode())
                break
            if not has_dir or entries[directory][0] != b"40000":
                raise Refused("no supported target-to-note path")
            path.append(directory.decode())
            suffix = suffix[2:]
            oid = entries[directory][1]
            kind, body = git.object(oid, proof=True)
            if kind != "tree":
                raise Refused("notes fanout must link a tree")
            proof.append((oid, kind, body))
        kind, body = git.object(note, proof=False, note=True)
        digest = hashlib.sha256(body).hexdigest()
        if declared_size != len(body) or declared_digest != digest:
            raise Refused("declared exact note size/digest mismatch")
        chain = json.dumps(
            [(oid, kind) for oid, kind, _ in proof], separators=(",", ":")
        )
        role = (
            *value.pair,
            value.fmt,
            target,
            note,
            "/".join(path),
            chain,
            "native-notes-v1",
        )
        git.work.metadata()
        with self.db:
            self._capture(value)
            for intrinsic_oid, intrinsic_type, intrinsic_body in proof:
                self._nominal(value.fmt, intrinsic_oid)
                existing_structure = self.db.execute(
                    "SELECT native_type,body FROM checked_structures "
                    "WHERE object_format=? AND full_oid=?",
                    (value.fmt, intrinsic_oid),
                ).fetchone()
                if existing_structure is not None and existing_structure != (
                    intrinsic_type,
                    intrinsic_body,
                ):
                    raise Refused("checked structural representation conflict")
                self.db.execute(
                    "INSERT INTO checked_structures VALUES(?,?,?,?) ON CONFLICT DO NOTHING",
                    (value.fmt, intrinsic_oid, intrinsic_type, intrinsic_body),
                )
            self._nominal(value.fmt, target)
            self._nominal(value.fmt, note)
            existing = self.db.execute(
                "SELECT body FROM note_bodies WHERE object_format=? AND full_oid=?",
                (value.fmt, note),
            ).fetchone()
            if existing is not None and existing[0] != body:
                raise Refused(
                    "existing retained bytes differ; production must stop recovery"
                )
            self.db.execute(
                "INSERT INTO note_bodies VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING",
                (value.fmt, note, len(body), digest, body),
            )
            if interrupt_after_body:
                raise Refused("injected atomic admission interruption")
            self.db.execute(
                "INSERT INTO note_roles VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (*role, len(body), digest),
            )
            for ordinal, (structural_oid, _, _) in enumerate(proof):
                self.db.execute(
                    "INSERT INTO proof_links VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                    (*role, ordinal, structural_oid),
                )

    def read_note(self, value: Capture, target: str, note: str) -> bytes:
        value.validate()
        binding = self.db.execute(
            "SELECT * FROM captures WHERE origin=? AND capture=?", value.pair
        ).fetchone()
        if binding is not None and binding != tuple(vars(value).values()):
            raise Refused("immutable Capture binding conflict")
        row = self.db.execute(
            "SELECT b.body,b.size,b.digest_sha256 FROM note_roles r "
            "JOIN note_bodies b ON b.object_format=r.object_format AND b.full_oid=r.note "
            "WHERE r.origin=? AND r.capture=? AND r.object_format=? "
            "AND r.target=? AND r.note=?",
            (*value.pair, value.fmt, target, note),
        ).fetchone()
        if row is None:
            raise Refused("no receiver-proven note role for this Capture/target/note")
        body, size, digest = row
        if (
            len(body) != size
            or hashlib.sha256(body).hexdigest() != digest
            or native_oid(value.fmt, "blob", body) != note
        ):
            raise Refused("retained-byte corruption; production must stop recovery")
        return body
