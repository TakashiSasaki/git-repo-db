"""Disposable Core/Context coordination experiment; never imported by the product.

All cooperating writers acquire the same OS gate. It is a process lock, not a
publication domain or durable truth. Each store remains independently committed.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Callable

REPOSITORY = "9ebbe38a-f937-40e6-a99c-701835ebcf10"
OID = "a" * 40
CORE_SQL = """
CREATE TABLE repository(repository_uuidv4 TEXT PRIMARY KEY) WITHOUT ROWID;
CREATE TABLE objects(object_format TEXT, full_oid TEXT,
 CHECK(object_format='sha1' AND length(full_oid)=40),
 PRIMARY KEY(object_format,full_oid)) WITHOUT ROWID;
CREATE TRIGGER no_update BEFORE UPDATE ON objects BEGIN
 SELECT RAISE(ABORT,'append only'); END;
CREATE TRIGGER no_delete BEFORE DELETE ON objects BEGIN
 SELECT RAISE(ABORT,'append only'); END;
"""
CONTEXT_SQL = """
CREATE TABLE repository(repository_uuidv4 TEXT PRIMARY KEY) WITHOUT ROWID;
CREATE TABLE issue_evidence(provider TEXT, issue TEXT, observed_us INTEGER,
 title TEXT NOT NULL, PRIMARY KEY(provider,issue,observed_us)) WITHOUT ROWID;
CREATE TABLE issue_git(provider TEXT, issue TEXT, observed_us INTEGER,
 role TEXT, object_format TEXT, full_oid TEXT,
 PRIMARY KEY(provider,issue,observed_us,role),
 FOREIGN KEY(provider,issue,observed_us)
 REFERENCES issue_evidence(provider,issue,observed_us)) WITHOUT ROWID;
"""


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA recursive_triggers=ON")
    db.execute("PRAGMA synchronous=FULL")
    return db


@contextlib.contextmanager
def gate(directory: Path, *, exclusive: bool):
    with (directory / "writer.lock").open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def initialize(directory: Path) -> None:
    directory.mkdir()
    for name, sql in (("core", CORE_SQL), ("context", CONTEXT_SQL)):
        with contextlib.closing(connect(directory / f"{name}.sqlite3")) as db:
            assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
            db.executescript(sql)
            db.execute("INSERT INTO repository VALUES(?)", (REPOSITORY,))


def cut(point: str, requested: str | None) -> None:
    if point == requested:
        # Deliberately bypass Python/SQLite cleanup and rollback handlers.
        os._exit(86)


def admit(directory: Path, fail_at: str | None = None) -> None:
    """Core-first, then one atomic Context unit. Identity is source evidence.

    This issue observation's source/provider/issue/time coordinates are supplied
    domain input, not a locally invented job or observation ID. Real adapters
    must use their actual field-clock/evidence identity and preserve alternatives.
    """
    with gate(directory, exclusive=True):
        with contextlib.closing(connect(directory / "core.sqlite3")) as core:
            core.execute("BEGIN IMMEDIATE")
            core.execute("INSERT OR IGNORE INTO objects VALUES('sha1',?)", (OID,))
            cut("before_core_commit", fail_at)
            core.commit()
            cut("after_core_commit", fail_at)
        with contextlib.closing(connect(directory / "context.sqlite3")) as ctx:
            ctx.execute("BEGIN IMMEDIATE")
            expected = ("provider.example", "issue-7", 12, "source title")
            existing = ctx.execute("SELECT * FROM issue_evidence").fetchall()
            if existing and existing != [expected]:
                raise ValueError("same evidence coordinates differ")
            ctx.execute(
                "INSERT OR IGNORE INTO issue_evidence VALUES(?,?,?,?)", expected
            )
            cut("during_context", fail_at)
            ctx.execute(
                "INSERT OR IGNORE INTO issue_git VALUES(?,?,?,'head','sha1',?)",
                (*expected[:3], OID),
            )
            ctx.commit()
            cut("after_context_commit", fail_at)


@contextlib.contextmanager
def snapshots(directory: Path):
    """Pin BOTH read snapshots while excluding all cooperating writers/handover."""
    with contextlib.ExitStack() as stack:
        core, ctx = [
            stack.enter_context(contextlib.closing(connect(directory / f"{s}.sqlite3")))
            for s in ("core", "context")
        ]
        with gate(directory, exclusive=False):
            for db in (core, ctx):
                db.execute("BEGIN")
                # BEGIN alone is deferred: SELECT is required to establish snapshot.
                db.execute("SELECT * FROM repository").fetchall()
        yield core, ctx


def state(core: sqlite3.Connection, ctx: sqlite3.Connection) -> dict:
    objects = core.execute("SELECT * FROM objects ORDER BY 1,2").fetchall()
    issues = ctx.execute("SELECT * FROM issue_evidence ORDER BY 1,2,3").fetchall()
    links = ctx.execute("SELECT * FROM issue_git ORDER BY 1,2,3,4").fetchall()
    coherent = all((link[-2], link[-1]) in objects for link in links)
    # Nominal identity resolution is NOT verified bytes or full Git closure.
    return {"objects": objects, "issues": issues, "links": links, "resolved": coherent}


def persisted(directory: Path) -> dict:
    with snapshots(directory) as (core, ctx):
        return state(core, ctx)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup(
    directory: Path,
    destination: Path,
    fail_at: str | None = None,
    between_copies: Callable[[], None] = lambda: None,
) -> None:
    """Create a new unpublished directory; certify only after BOTH snapshots copy.

    Holding the gate through copying is deliberately conservative. Python's
    backup API uses dedicated source connections; the gate prevents them changing
    between copies. Production can optimize with proven pinned snapshot handling.
    """
    destination.mkdir()
    with gate(directory, exclusive=False):
        for name in ("core", "context"):
            with (
                contextlib.closing(connect(directory / f"{name}.sqlite3")) as src,
                contextlib.closing(connect(destination / f"{name}.sqlite3")) as dst,
            ):
                src.backup(dst)
            if name == "core":
                cut("during_backup", fail_at)
                between_copies()
        with snapshots(destination) as (core, ctx):
            validate_pair(core, ctx, REPOSITORY)
        manifest = {
            "scope": "core+context",
            "repository_uuidv4": REPOSITORY,
            "files": {
                f"{s}.sqlite3": sha256(destination / f"{s}.sqlite3")
                for s in ("core", "context")
            },
        }
        # Manifest is the final local completion marker, not a domain authority.
        (destination / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))


def validate_backup(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["scope"] != "core+context" or set(manifest["files"]) != {
        "core.sqlite3",
        "context.sqlite3",
    }:
        raise ValueError("full pair required")
    for filename, digest in manifest["files"].items():
        if sha256(directory / filename) != digest:
            raise ValueError("snapshot pair bytes differ")
    with snapshots(directory) as (core, ctx):
        validate_pair(core, ctx, manifest["repository_uuidv4"])


def validate_pair(core, ctx, repository_uuidv4):
    """Same candidate validation before certification and after artifact transfer."""
    for db in (core, ctx):
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("database integrity")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("foreign key integrity")
        if db.execute("SELECT * FROM repository").fetchall() != [(repository_uuidv4,)]:
            raise ValueError("repository pairing")
    if not state(core, ctx)["resolved"]:
        raise ValueError("unresolved context reference")


if __name__ == "__main__":
    import sys

    action, source, point = sys.argv[1:4]
    if action == "admit":
        admit(Path(source), point)
    elif action == "backup":
        backup(Path(source), Path(sys.argv[4]), point)
    else:
        raise ValueError(action)
