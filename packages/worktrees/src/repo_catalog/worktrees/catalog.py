"""Independent append-only SQLite topology observations and checked snapshots."""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import sqlite3
import stat
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from .git import discover_topology
from .models import (
    DiscoveryResult,
    WorktreeEntry,
    WorktreeError,
    native_path,
    uuid_value,
)

FORMAT = "repo-catalog/worktrees-1"
MIN_SQLITE = (3, 51, 3)
TABLES = (
    "catalog_identity",
    "observations",
    "worktrees",
    "scan_references",
    "repository_links",
)
SCHEMA = """
CREATE TABLE catalog_identity (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 format TEXT NOT NULL, namespace_uuid TEXT NOT NULL,
 path_dialect TEXT NOT NULL CHECK(path_dialect IN ('posix','nt')),
 path_encoding TEXT NOT NULL, path_errors TEXT NOT NULL,
 schema_sha256 TEXT NOT NULL
) STRICT;
CREATE TABLE observations (
 observation_uuid TEXT PRIMARY KEY, requested_path BLOB NOT NULL CHECK(length(requested_path)>0),
 common_dir BLOB, status TEXT NOT NULL CHECK(status IN ('complete','partial','not_git','error')),
 errors_json TEXT NOT NULL CHECK(json_valid(errors_json)),
 observed_at_us INTEGER NOT NULL CHECK(observed_at_us>0)
) STRICT;
CREATE TABLE worktrees (
 observation_uuid TEXT NOT NULL REFERENCES observations(observation_uuid),
 root_path BLOB NOT NULL CHECK(length(root_path)>0), git_dir BLOB, common_dir BLOB,
 head_oid TEXT, branch BLOB, bare INTEGER NOT NULL CHECK(bare IN (0,1)),
 locked BLOB, prunable BLOB, error TEXT,
 object_format TEXT CHECK(object_format IN ('sha1','sha256')),
 PRIMARY KEY(observation_uuid,root_path)
) STRICT, WITHOUT ROWID;
CREATE TABLE scan_references (
 observation_uuid TEXT NOT NULL, root_path BLOB NOT NULL,
 filesystem_namespace_uuid TEXT NOT NULL, filesystem_scan_uuid TEXT NOT NULL,
 PRIMARY KEY(observation_uuid,root_path,filesystem_namespace_uuid,filesystem_scan_uuid),
 FOREIGN KEY(observation_uuid,root_path) REFERENCES worktrees(observation_uuid,root_path)
) STRICT, WITHOUT ROWID;
CREATE TABLE repository_links (
 common_dir BLOB NOT NULL CHECK(length(common_dir)>0), repository_uuid TEXT NOT NULL,
 linked_at_us INTEGER NOT NULL CHECK(linked_at_us>0),
 PRIMARY KEY(common_dir,repository_uuid)
) STRICT, WITHOUT ROWID;
""" + "\n".join(
    f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
    "BEGIN SELECT RAISE(ABORT,'immutable topology observation'); END;"
    for table in TABLES
    for action in ("UPDATE", "DELETE")
)
FINGERPRINT = hashlib.sha256(SCHEMA.encode()).hexdigest()


def _runtime():
    if sqlite3.sqlite_version_info < MIN_SQLITE or not sqlite3.threadsafety:
        raise WorktreeError("SQLITE_RUNTIME", "SQLite >=3.51.3 with mutexes required")


def _connect(path: Path, *, readonly=False):
    _runtime()
    connection = sqlite3.connect(
        path.resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rw"),
        uri=True,
        timeout=5,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA recursive_triggers=ON")
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute("PRAGMA busy_timeout=5000")
    if readonly:
        connection.execute("PRAGMA query_only=ON")
    return connection


def _copy_snapshot(source: Path, destination: Path):
    """Hash the exact bytes copied from one pinned regular source descriptor."""
    digest = hashlib.sha256()
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(source, flags)
    with os.fdopen(descriptor, "rb") as stream, destination.open("xb") as output:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise WorktreeError("BACKUP", "backup source is not a regular file")
        remaining = before.st_size
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise WorktreeError("BACKUP", "backup source changed while copying")
            digest.update(chunk)
            output.write(chunk)
            remaining -= len(chunk)
        after = os.fstat(stream.fileno())
        if stream.read(1) or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise WorktreeError("BACKUP", "backup source changed while copying")
        output.flush()
        os.fsync(output.fileno())
    return digest.hexdigest()


def _valid_path(value, dialect):
    if not isinstance(value, bytes) or not value or b"\0" in value:
        return False
    if dialect == "nt":
        drive, tail = ntpath.splitdrive(value)
        return bool(drive) and (
            tail.startswith((b"/", b"\\"))
            or (
                not tail
                and drive.startswith((b"\\\\", b"//"))
                and not drive.endswith(b":")
            )
        )
    return value.startswith(b"/")


def _signature(connection):
    return tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name"
        )
    )


def _check_schema(connection):
    expected = sqlite3.connect(":memory:")
    try:
        expected.executescript(SCHEMA)
        if _signature(expected) != _signature(connection):
            raise WorktreeError(
                "SCHEMA", "worktree schema differs from supported format"
            )
    finally:
        expected.close()


class WorktreeCatalog:
    def __init__(
        self, database: Path, connection: sqlite3.Connection, *, readonly=False
    ):
        self.database = Path(database).absolute()
        self._db = connection
        self.readonly = readonly
        identity = connection.execute(
            "SELECT * FROM catalog_identity WHERE singleton=1"
        ).fetchone()
        if (
            identity is None
            or identity["format"] != FORMAT
            or identity["schema_sha256"] != FINGERPRINT
        ):
            raise WorktreeError("SCHEMA", "unsupported worktree catalog format")
        self.namespace_uuid = uuid_value(identity["namespace_uuid"], 4)
        self.path_dialect = identity["path_dialect"]

    @classmethod
    def initialize(cls, database, *, namespace_uuid=None):
        _runtime()
        namespace_uuid = uuid_value(
            str(uuid4()) if namespace_uuid is None else namespace_uuid, 4
        )
        path = Path(database).absolute()
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        connection = None
        try:
            connection = _connect(path)
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript(SCHEMA)
            connection.execute(
                "INSERT INTO catalog_identity VALUES(1,?,?,?,?,?,?)",
                (
                    FORMAT,
                    namespace_uuid,
                    os.name,
                    sys.getfilesystemencoding(),
                    sys.getfilesystemencodeerrors(),
                    FINGERPRINT,
                ),
            )
            connection.commit()
            return cls(path, connection)
        except BaseException:
            if connection is not None:
                connection.close()
            path.unlink(missing_ok=True)
            raise

    @classmethod
    def open(cls, database, *, readonly=False):
        path = Path(database).absolute()
        connection = _connect(path, readonly=readonly)
        try:
            _check_schema(connection)
            catalog = cls(path, connection, readonly=readonly)
            catalog.verify()
            return catalog
        except BaseException:
            connection.close()
            raise

    def close(self):
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _write(self):
        if self.readonly:
            raise WorktreeError("READ_ONLY", "catalog opened read-only")

    def discover(self, root, *, expand=True, **limits):
        self._write()
        if self.path_dialect != os.name:
            raise WorktreeError(
                "PATH_DIALECT", "local scan requires the catalog's native path dialect"
            )
        result = replace(
            discover_topology(root, expand=expand, **limits),
            namespace_uuid=self.namespace_uuid,
        )
        with self._db:
            self._db.execute(
                "INSERT INTO observations VALUES(?,?,?,?,?,?)",
                (
                    result.observation_uuid,
                    result.requested_path,
                    result.common_dir,
                    result.status,
                    json.dumps(result.errors),
                    result.observed_at_us,
                ),
            )
            self._db.executemany(
                "INSERT INTO worktrees VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        result.observation_uuid,
                        entry.root_path,
                        entry.git_dir,
                        entry.common_dir,
                        entry.head_oid,
                        entry.branch,
                        int(entry.bare),
                        entry.locked,
                        entry.prunable,
                        entry.error,
                        entry.object_format,
                    )
                    for entry in result.entries
                ],
            )
        return result

    def get_discovery(self, observation):
        uuid_value(observation, 7)
        row = self._db.execute(
            "SELECT * FROM observations WHERE observation_uuid=?", (observation,)
        ).fetchone()
        if row is None:
            raise WorktreeError("NOT_FOUND", "topology observation not found")
        entries = tuple(
            WorktreeEntry(
                item["root_path"],
                item["git_dir"],
                item["common_dir"],
                item["head_oid"],
                item["branch"],
                bool(item["bare"]),
                item["locked"],
                item["prunable"],
                item["error"],
                item["object_format"],
            )
            for item in self._db.execute(
                "SELECT * FROM worktrees WHERE observation_uuid=? ORDER BY root_path",
                (observation,),
            )
        )
        return DiscoveryResult(
            self.namespace_uuid,
            observation,
            row["requested_path"],
            row["common_dir"],
            entries,
            row["status"],
            tuple(json.loads(row["errors_json"])),
            row["observed_at_us"],
        )

    def list_discoveries(self):
        return tuple(
            self.get_discovery(row[0])
            for row in self._db.execute(
                "SELECT observation_uuid FROM observations ORDER BY observed_at_us,observation_uuid"
            ).fetchall()
        )

    def record_scan_reference(
        self,
        observation_uuid,
        root_path,
        filesystem_namespace_uuid,
        filesystem_scan_uuid,
    ):
        self._write()
        uuid_value(observation_uuid, 7)
        uuid_value(filesystem_namespace_uuid, 4)
        uuid_value(filesystem_scan_uuid, 7)
        path = root_path if isinstance(root_path, bytes) else native_path(root_path)
        with self._db:
            self._db.execute(
                "INSERT INTO scan_references VALUES(?,?,?,?) ON CONFLICT DO NOTHING",
                (
                    observation_uuid,
                    path,
                    filesystem_namespace_uuid,
                    filesystem_scan_uuid,
                ),
            )

    def scan_references(self, filesystem_namespace_uuid, filesystem_scan_uuid):
        uuid_value(filesystem_namespace_uuid, 4)
        uuid_value(filesystem_scan_uuid, 7)
        return tuple(
            dict(row)
            for row in self._db.execute(
                "SELECT * FROM scan_references WHERE filesystem_namespace_uuid=? AND filesystem_scan_uuid=? ORDER BY observation_uuid,root_path",
                (filesystem_namespace_uuid, filesystem_scan_uuid),
            )
        )

    def link_repository(self, common_dir, repository_uuid, *, observation_uuid=None):
        self._write()
        uuid_value(repository_uuid, 4)
        path = common_dir if isinstance(common_dir, bytes) else native_path(common_dir)
        if not _valid_path(path, self.path_dialect):
            raise WorktreeError("PATH", "absolute native common directory required")
        if observation_uuid is not None:
            observation = self.get_discovery(observation_uuid)
            if observation.common_dir != path:
                raise WorktreeError(
                    "IDENTITY", "directory differs from nominated observation"
                )
        with self._db:
            self._db.execute(
                "INSERT INTO repository_links VALUES(?,?,?) ON CONFLICT DO NOTHING",
                (
                    path,
                    repository_uuid,
                    time.time_ns() // 1000,
                ),
            )

    def repository_links(self, common_dir):
        path = common_dir if isinstance(common_dir, bytes) else native_path(common_dir)
        return tuple(
            row[0]
            for row in self._db.execute(
                "SELECT repository_uuid FROM repository_links WHERE common_dir=? ORDER BY repository_uuid",
                (path,),
            )
        )

    def verify(self):
        _check_schema(self._db)
        identity = self._db.execute(
            "SELECT * FROM catalog_identity WHERE singleton=1"
        ).fetchone()
        if (
            identity is None
            or identity["format"] != FORMAT
            or identity["schema_sha256"] != FINGERPRINT
            or identity["namespace_uuid"] != self.namespace_uuid
            or identity["path_dialect"] != self.path_dialect
        ):
            raise WorktreeError("IDENTITY", "worktree catalog identity changed")
        if [row[0] for row in self._db.execute("PRAGMA integrity_check")] != ["ok"]:
            raise WorktreeError("INTEGRITY", "worktree database integrity check failed")
        if self._db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise WorktreeError("INTEGRITY", "worktree database reference check failed")
        for row in self._db.execute("SELECT * FROM observations"):
            uuid_value(row["observation_uuid"], 7)
            errors = json.loads(row["errors_json"])
            if not isinstance(errors, list) or any(
                not isinstance(error, str) for error in errors
            ):
                raise WorktreeError("INTEGRITY", "invalid discovery errors")
            if not _valid_path(row["requested_path"], self.path_dialect) or (
                row["common_dir"] is not None
                and not _valid_path(row["common_dir"], self.path_dialect)
            ):
                raise WorktreeError("INTEGRITY", "invalid discovery path")
            if bool(errors) != (row["status"] in ("partial", "error")):
                raise WorktreeError("INTEGRITY", "discovery status contradicts errors")
        for row in self._db.execute(
            "SELECT filesystem_namespace_uuid,filesystem_scan_uuid FROM scan_references"
        ):
            uuid_value(row[0], 4)
            uuid_value(row[1], 7)
        for row in self._db.execute(
            "SELECT repository_uuid,common_dir FROM repository_links"
        ):
            uuid_value(row[0], 4)
            if not _valid_path(row[1], self.path_dialect):
                raise WorktreeError("INTEGRITY", "invalid repository association path")
        for row in self._db.execute("SELECT * FROM worktrees"):
            for key in ("root_path", "git_dir", "common_dir"):
                value = row[key]
                if value is not None and not _valid_path(value, self.path_dialect):
                    raise WorktreeError("INTEGRITY", "invalid stored native path")
            oid, fmt = row["head_oid"], row["object_format"]
            if oid is not None and not re.fullmatch(
                r"[0-9a-f]{40}"
                if fmt == "sha1"
                else r"[0-9a-f]{64}"
                if fmt == "sha256"
                else r"[0-9a-f]{40}|[0-9a-f]{64}",
                oid,
            ):
                raise WorktreeError("INTEGRITY", "invalid stored HEAD object identity")
        return {
            "status": "complete",
            "format": FORMAT,
            "schema_version": 1,
            "namespace_uuid": self.namespace_uuid,
            "counts": {
                table: self._db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in TABLES
            },
        }

    def backup(self, destination):
        self.verify()
        target = Path(destination).absolute()
        if target.exists():
            raise FileExistsError(target)
        with tempfile.TemporaryDirectory(
            prefix=".worktrees-backup-", dir=target.parent
        ) as staging:
            snapshot = Path(staging) / "snapshot.sqlite3"
            connection = sqlite3.connect(snapshot)
            try:
                self._db.backup(connection)
                connection.execute("PRAGMA journal_mode=DELETE")
            finally:
                connection.close()
            with self.open(snapshot, readonly=True) as copied:
                if copied.namespace_uuid != self.namespace_uuid:
                    raise WorktreeError("BACKUP", "snapshot namespace changed")
            target.mkdir(mode=0o700)
            manifest = {
                "format": FORMAT + "/backup",
                "namespace_uuid": self.namespace_uuid,
                "sha256": _copy_snapshot(snapshot, target / "worktrees.sqlite3"),
                "database": "worktrees.sqlite3",
            }
            with (target / "manifest.json").open("x", encoding="utf-8") as output:
                json.dump(manifest, output, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            return manifest

    @classmethod
    def restore(cls, backup, destination):
        bundle = Path(backup).absolute()
        target = Path(destination).absolute()
        if target.exists():
            raise FileExistsError(target)
        manifest_path = bundle / "manifest.json"
        if {item.name for item in bundle.iterdir()} != {
            "manifest.json",
            "worktrees.sqlite3",
        } or any(not item.is_file() or item.is_symlink() for item in bundle.iterdir()):
            raise WorktreeError(
                "BACKUP", "backup must contain only the manifest and plain database"
            )
        with manifest_path.open("rb") as stream:
            body = stream.read(16385)
        if len(body) > 16384:
            raise WorktreeError("BACKUP", "backup manifest exceeds limit")
        manifest = json.loads(body)
        source = bundle / "worktrees.sqlite3"
        if (
            not isinstance(manifest, dict)
            or set(manifest) != {"format", "namespace_uuid", "sha256", "database"}
            or manifest["format"] != FORMAT + "/backup"
            or manifest["database"] != "worktrees.sqlite3"
            or not isinstance(manifest["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest["sha256"])
        ):
            raise WorktreeError("BACKUP", "backup manifest or checksum mismatch")
        with tempfile.TemporaryDirectory(
            prefix=".worktrees-restore-", dir=target.parent
        ) as staging:
            snapshot = Path(staging) / "snapshot.sqlite3"
            if _copy_snapshot(source, snapshot) != manifest["sha256"]:
                raise WorktreeError("BACKUP", "backup manifest or checksum mismatch")
            with cls.open(snapshot, readonly=True) as original:
                if original.namespace_uuid != manifest["namespace_uuid"]:
                    raise WorktreeError("BACKUP", "backup namespace mismatch")
            copied_digest = _copy_snapshot(snapshot, target)
            if copied_digest != manifest["sha256"]:
                raise WorktreeError(
                    "BACKUP", "staged snapshot changed before activation"
                )
        return cls.open(target)
