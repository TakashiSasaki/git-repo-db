"""An independent append-only SQLite filesystem observation catalog."""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import posixpath
import sqlite3
import stat
import sys
import tempfile
import time
import uuid
from pathlib import Path

from .efu import export_efu
from .models import FileEntry, FilesystemError, ScanResult, native_path, occurrence_uuid
from .scanner import walk

SCHEMA_VERSION = 1
DDL = """
CREATE TABLE catalog_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE scans (
 namespace_uuid TEXT NOT NULL, scan_uuid TEXT NOT NULL,
 root_path BLOB NOT NULL, started_us INTEGER NOT NULL CHECK(started_us > 0),
 exclusions_json TEXT NOT NULL,
 PRIMARY KEY(namespace_uuid,scan_uuid)
) STRICT;
CREATE TABLE entries (
 namespace_uuid TEXT NOT NULL, scan_uuid TEXT NOT NULL, relative_path BLOB NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('file','directory','symlink','special','unknown')),
 size INTEGER CHECK(size IS NULL OR size >= 0),
 mtime_ns TEXT, birthtime_ns TEXT, ctime_ns TEXT,
 attributes INTEGER, mode INTEGER,
 sha256 TEXT CHECK(sha256 IS NULL OR (length(CAST(sha256 AS BLOB))=64 AND instr(sha256,char(0))=0 AND sha256 NOT GLOB '*[^0-9a-f]*')),
 hash_status TEXT NOT NULL CHECK(hash_status IN ('complete','changed','not-applicable','error')),
 error TEXT, link_target BLOB, observed_us INTEGER CHECK(observed_us IS NULL OR observed_us > 0),
 CHECK((hash_status='complete' AND sha256 IS NOT NULL AND kind='file') OR (hash_status!='complete' AND sha256 IS NULL)),
 CHECK((kind='file' AND size IS NOT NULL AND hash_status IN ('complete','changed','error')) OR (kind!='file' AND hash_status='not-applicable')),
 CHECK(hash_status NOT IN ('changed','error') OR error IS NOT NULL),
 PRIMARY KEY(namespace_uuid,scan_uuid,relative_path),
 FOREIGN KEY(namespace_uuid,scan_uuid) REFERENCES scans(namespace_uuid,scan_uuid)
) STRICT;
CREATE TABLE scan_outcomes (
 namespace_uuid TEXT NOT NULL, scan_uuid TEXT NOT NULL,
 finished_us INTEGER NOT NULL CHECK(finished_us > 0),
 status TEXT NOT NULL CHECK(status IN ('complete','partial','interrupted')),
 entry_count INTEGER NOT NULL CHECK(entry_count >= 0),
 error_count INTEGER NOT NULL CHECK(error_count >= 0),
 PRIMARY KEY(namespace_uuid,scan_uuid),
 FOREIGN KEY(namespace_uuid,scan_uuid) REFERENCES scans(namespace_uuid,scan_uuid)
) STRICT;
"""
for _table in ("catalog_metadata", "scans", "entries", "scan_outcomes"):
    for _operation in ("UPDATE", "DELETE"):
        DDL += f"CREATE TRIGGER {_table}_{_operation.lower()} BEFORE {_operation} ON {_table} BEGIN SELECT RAISE(ABORT,'append-only catalog'); END;\n"
DDL += """
CREATE TRIGGER entries_closed BEFORE INSERT ON entries
WHEN EXISTS(SELECT 1 FROM scan_outcomes WHERE namespace_uuid=NEW.namespace_uuid AND scan_uuid=NEW.scan_uuid)
BEGIN SELECT RAISE(ABORT,'scan already terminal'); END;
"""


def _runtime():
    if sqlite3.sqlite_version_info < (3, 51, 3) or sqlite3.threadsafety < 1:
        raise FilesystemError("SQLite >= 3.51.3 with thread safety is required")


def _connect(path, readonly=False):
    _runtime()
    db = sqlite3.connect(
        path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True
    )
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    # REPLACE must fire DELETE guards rather than bypass append-only history.
    db.execute("PRAGMA recursive_triggers=ON")
    db.execute("PRAGMA trusted_schema=OFF")
    db.execute("PRAGMA busy_timeout=5000")
    if not readonly:
        if db.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
            db.close()
            raise FilesystemError("WAL mode unavailable")
        db.execute("PRAGMA synchronous=FULL")
    return db


def _copy_exclusive(source, destination):
    """Pin a regular source and copy exact bounded bytes into a new file."""
    digest = hashlib.sha256()
    with open(source, "rb") as stream, open(destination, "xb") as output:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise FilesystemError("backup source is not a regular file")
        remaining = before.st_size
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise FilesystemError("backup source changed during copy")
            digest.update(chunk)
            output.write(chunk)
            remaining -= len(chunk)
        after = os.fstat(stream.fileno())
        if stream.read(1) or (
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise FilesystemError("backup source changed during copy")
        output.flush()
        os.fsync(output.fileno())
    return digest.hexdigest()


def _schema_objects(db):
    return tuple(
        tuple(row)
        for row in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' ORDER BY type,name"
        )
    )


def _verify_schema(db):
    expected = sqlite3.connect(":memory:")
    try:
        expected.executescript(DDL)
        if _schema_objects(db) != _schema_objects(expected):
            raise FilesystemError("filesystem catalog schema mismatch")
    finally:
        expected.close()


class FilesystemCatalog:
    def __init__(self, database, db, readonly):
        self.database = Path(database).absolute()
        self._db = db
        self.readonly = readonly
        metadata = dict(db.execute("SELECT key,value FROM catalog_metadata"))
        if metadata.get("schema_version") != str(SCHEMA_VERSION):
            raise FilesystemError("unsupported filesystem catalog schema")
        self.namespace_uuid = metadata["namespace_uuid"]
        self.path_dialect = metadata["path_dialect"]
        self.path_encoding = metadata["path_encoding"]
        self._identity_metadata = metadata

    @classmethod
    def initialize(cls, database, *, namespace_uuid=None):
        _runtime()
        database = Path(database).absolute()
        namespace_uuid = namespace_uuid or str(uuid.uuid4())
        if (
            str(uuid.UUID(namespace_uuid)) != namespace_uuid
            or uuid.UUID(namespace_uuid).version != 4
        ):
            raise FilesystemError("filesystem namespace must be a canonical UUIDv4")
        fd = os.open(database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        db = _connect(database)
        try:
            db.executescript(DDL)
            with db:
                db.executemany(
                    "INSERT INTO catalog_metadata VALUES (?,?)",
                    {
                        "schema_version": str(SCHEMA_VERSION),
                        "namespace_uuid": namespace_uuid,
                        "path_dialect": os.name,
                        "path_encoding": sys.getfilesystemencoding(),
                        "path_errors": sys.getfilesystemencodeerrors(),
                    }.items(),
                )
            return cls(database, db, False)
        except BaseException:
            db.close()
            raise

    @classmethod
    def open(cls, database, *, readonly=False):
        database = Path(database).absolute()
        db = _connect(database, readonly)
        try:
            _verify_schema(db)
            result = cls(database, db, readonly)
            result.verify()
            return result
        except BaseException:
            db.close()
            raise

    def close(self):
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def verify(self):
        _verify_schema(self._db)
        if (
            dict(self._db.execute("SELECT key,value FROM catalog_metadata"))
            != self._identity_metadata
        ):
            raise FilesystemError("filesystem catalog identity changed")
        if [r[0] for r in self._db.execute("PRAGMA integrity_check")] != ["ok"]:
            raise FilesystemError("filesystem catalog integrity failure")
        if self._db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise FilesystemError("filesystem catalog reference failure")
        if uuid.UUID(self.namespace_uuid).version != 4:
            raise FilesystemError("invalid filesystem namespace")
        if self.path_dialect not in ("nt", "posix") or self.path_encoding != "utf-8":
            raise FilesystemError("unsupported native path convention")
        path_module = ntpath if self.path_dialect == "nt" else posixpath
        for row in self._db.execute("SELECT root_path,exclusions_json FROM scans"):
            if not path_module.isabs(row[0]) or b"\0" in row[0]:
                raise FilesystemError("invalid scan root")
            try:
                exclusions = json.loads(row[1])
                if not isinstance(exclusions, list) or any(
                    not path_module.isabs(bytes.fromhex(value)) for value in exclusions
                ):
                    raise ValueError
            except (ValueError, TypeError):
                raise FilesystemError("invalid scan exclusions") from None
        for row in self._db.execute(
            "SELECT relative_path,mtime_ns,birthtime_ns,ctime_ns FROM entries"
        ):
            relative = row[0]
            if (
                b"\0" in relative
                or path_module.isabs(relative)
                or bool(path_module.splitdrive(relative)[0])
                or (
                    relative
                    and (
                        path_module.normpath(relative) != relative
                        or relative == b".."
                        or relative.startswith(
                            b".." + (b"\\" if self.path_dialect == "nt" else b"/")
                        )
                    )
                )
            ):
                raise FilesystemError("invalid relative file path")
            for value in row[1:]:
                if value is not None:
                    try:
                        if str(int(value)) != value:
                            raise ValueError
                    except ValueError:
                        raise FilesystemError("invalid native timestamp") from None
        for row in self._db.execute(
            "SELECT s.namespace_uuid,s.scan_uuid,o.entry_count,o.error_count,o.status,(SELECT count(*) FROM entries e WHERE e.namespace_uuid=s.namespace_uuid AND e.scan_uuid=s.scan_uuid) n,(SELECT count(*) FROM entries e WHERE e.namespace_uuid=s.namespace_uuid AND e.scan_uuid=s.scan_uuid AND e.error IS NOT NULL) errors FROM scans s LEFT JOIN scan_outcomes o USING(namespace_uuid,scan_uuid)"
        ):
            if (
                row["namespace_uuid"] != self.namespace_uuid
                or uuid.UUID(row["scan_uuid"]).version != 7
            ):
                raise FilesystemError("invalid scan identity")
            if row["status"] is not None and (
                row["entry_count"] != row["n"]
                or row["error_count"] != row["errors"]
                or (row["status"] == "complete" and row["errors"])
            ):
                raise FilesystemError("scan outcome does not describe its observations")
        return {
            "schema_version": SCHEMA_VERSION,
            "namespace_uuid": self.namespace_uuid,
            "integrity": "ok",
        }

    def scan(self, root, *, exclude_paths=()):
        if self.readonly:
            raise FilesystemError("read-only catalog")
        if (
            self.path_dialect != os.name
            or self.path_encoding != sys.getfilesystemencoding()
        ):
            raise FilesystemError(
                "scanning requires the catalog's native filesystem platform"
            )
        root = native_path(root)
        scan_uuid = occurrence_uuid()
        own = [
            native_path(str(self.database) + suffix)
            for suffix in ("", "-wal", "-shm", "-journal")
        ]
        exclusions = tuple(
            sorted(set(native_path(p) for p in exclude_paths) | set(own))
        )
        with self._db:
            self._db.execute(
                "INSERT INTO scans VALUES (?,?,?,?,?)",
                (
                    self.namespace_uuid,
                    scan_uuid,
                    root,
                    time.time_ns() // 1000,
                    json.dumps([p.hex() for p in exclusions]),
                ),
            )
        entries = errors = 0
        batch = []
        storage_failed = False

        def flush():
            nonlocal entries, errors, storage_failed
            if not batch:
                return
            try:
                with self._db:
                    self._db.executemany(
                        "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        batch,
                    )
            except BaseException:
                storage_failed = True
                raise
            entries += len(batch)
            errors += sum(row[12] is not None for row in batch)
            batch.clear()

        status = "complete"
        try:
            for entry in walk(root, self.namespace_uuid, scan_uuid, exclusions):
                batch.append(
                    (
                        entry.namespace_uuid,
                        entry.scan_uuid,
                        entry.relative_path,
                        entry.kind,
                        entry.size,
                        *(
                            str(x) if x is not None else None
                            for x in (
                                entry.mtime_ns,
                                entry.birthtime_ns,
                                entry.ctime_ns,
                            )
                        ),
                        entry.attributes,
                        entry.mode,
                        entry.sha256,
                        "error"
                        if entry.hash_status == "pending"
                        else entry.hash_status,
                        entry.error,
                        entry.link_target,
                        entry.observed_us,
                    )
                )
                if len(batch) >= 128:
                    flush()
            flush()
            status = "partial" if errors else "complete"
        except sqlite3.Error:
            # Storage failure leaves an incomplete observation. Never retry the
            # failing batch or write a terminal record to a suspect database.
            raise
        except BaseException:
            if storage_failed:
                raise
            flush()
            status = "interrupted"
            with self._db:
                self._db.execute(
                    "INSERT INTO scan_outcomes VALUES (?,?,?,?,?,?)",
                    (
                        self.namespace_uuid,
                        scan_uuid,
                        time.time_ns() // 1000,
                        status,
                        entries,
                        errors,
                    ),
                )
            raise
        with self._db:
            self._db.execute(
                "INSERT INTO scan_outcomes VALUES (?,?,?,?,?,?)",
                (
                    self.namespace_uuid,
                    scan_uuid,
                    time.time_ns() // 1000,
                    status,
                    entries,
                    errors,
                ),
            )
        return self.get_scan(scan_uuid)

    def list_scans(self):
        return [
            self.get_scan(r[0])
            for r in self._db.execute(
                "SELECT scan_uuid FROM scans WHERE namespace_uuid=? ORDER BY started_us,scan_uuid",
                (self.namespace_uuid,),
            )
        ]

    def get_scan(self, scan_uuid):
        row = self._db.execute(
            "SELECT s.root_path,o.status,o.entry_count,o.error_count FROM scans s LEFT JOIN scan_outcomes o USING(namespace_uuid,scan_uuid) WHERE s.namespace_uuid=? AND s.scan_uuid=?",
            (self.namespace_uuid, scan_uuid),
        ).fetchone()
        if row is None:
            raise FilesystemError("unknown scan")
        if row[1] is None:
            count, errors = self._db.execute(
                "SELECT count(*),coalesce(sum(error IS NOT NULL),0) FROM entries WHERE namespace_uuid=? AND scan_uuid=?",
                (self.namespace_uuid, scan_uuid),
            ).fetchone()
            return ScanResult(
                self.namespace_uuid, scan_uuid, row[0], "incomplete", count, errors
            )
        incomplete_enumeration, incomplete_hashing = self._db.execute(
            "SELECT coalesce(sum(error IS NOT NULL AND kind!='file'),0),coalesce(sum((kind='file' AND hash_status!='complete') OR kind='unknown'),0) FROM entries WHERE namespace_uuid=? AND scan_uuid=?",
            (self.namespace_uuid, scan_uuid),
        ).fetchone()
        terminal = row[1] in ("complete", "partial")
        return ScanResult(
            self.namespace_uuid,
            scan_uuid,
            row[0],
            row[1],
            row[2],
            row[3],
            terminal and not incomplete_enumeration,
            terminal and not incomplete_hashing,
        )

    def iter_entries(self, scan_uuid):
        scan = self.get_scan(scan_uuid)
        for row in self._db.execute(
            "SELECT * FROM entries WHERE namespace_uuid=? AND scan_uuid=? ORDER BY relative_path",
            (self.namespace_uuid, scan_uuid),
        ):
            values = dict(row)
            path_module = ntpath if self.path_dialect == "nt" else posixpath
            values["absolute_path"] = (
                path_module.join(scan.root_path, values["relative_path"])
                if values["relative_path"]
                else scan.root_path
            )
            for field in ("mtime_ns", "birthtime_ns", "ctime_ns"):
                values[field] = (
                    int(values[field]) if values[field] is not None else None
                )
            yield FileEntry(**values)

    def export_efu(self, scan_uuid, destination, *, allow_partial=False, **options):
        if not allow_partial and self.get_scan(scan_uuid).status != "complete":
            raise FilesystemError("partial/incomplete scan requires allow_partial")
        destination = Path(destination).absolute()

        def guard():
            for suffix in ("", "-wal", "-shm", "-journal"):
                artifact = Path(str(self.database) + suffix)
                if destination.resolve() == artifact.resolve() or (
                    destination.exists()
                    and artifact.exists()
                    and os.path.samefile(destination, artifact)
                ):
                    raise FilesystemError("export cannot replace catalog artifacts")

        guard()
        fd, name = tempfile.mkstemp(prefix=".efu-", dir=destination.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
                result = export_efu(self.iter_entries(scan_uuid), output, **options)
                output.flush()
                os.fsync(output.fileno())
            guard()
            os.replace(name, destination)
            return result
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def backup(self, destination):
        self.verify()
        destination = Path(destination).absolute()
        manifest_path = Path(str(destination) + ".manifest.json")
        if destination.exists() or manifest_path.exists():
            raise FileExistsError(destination)
        with tempfile.TemporaryDirectory(
            prefix=".filesystem-backup-", dir=destination.parent
        ) as staging:
            snapshot = Path(staging) / "snapshot.sqlite3"
            target = sqlite3.connect(snapshot)
            try:
                self._db.backup(target)
                target.execute("PRAGMA journal_mode=DELETE")
            finally:
                target.close()
            with self.open(snapshot, readonly=True) as check:
                check.verify()
                if check.namespace_uuid != self.namespace_uuid:
                    raise FilesystemError("backup namespace mismatch")
            digest = _copy_exclusive(snapshot, destination)
            manifest = {
                "format": "filesystem-backup-v1",
                "namespace_uuid": self.namespace_uuid,
                "sha256": digest,
            }
            with manifest_path.open("x", encoding="utf-8") as output:
                json.dump(manifest, output, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            return manifest

    @classmethod
    def restore(cls, source, destination):
        source, destination = Path(source).absolute(), Path(destination).absolute()
        if destination.exists():
            raise FileExistsError(destination)
        with Path(str(source) + ".manifest.json").open("rb") as stream:
            body = stream.read(4097)
        if len(body) > 4096:
            raise FilesystemError("backup manifest is too large")
        manifest = json.loads(body)
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != "filesystem-backup-v1"
        ):
            raise FilesystemError("backup manifest or digest mismatch")
        if any(
            Path(str(source) + suffix).exists()
            for suffix in ("-wal", "-shm", "-journal")
        ):
            raise FilesystemError("backup must be a standalone checkpointed database")
        with tempfile.TemporaryDirectory(
            prefix=".filesystem-restore-", dir=destination.parent
        ) as staging:
            snapshot = Path(staging) / "snapshot.sqlite3"
            if _copy_exclusive(source, snapshot) != manifest.get("sha256"):
                raise FilesystemError("backup manifest or digest mismatch")
            with cls.open(snapshot, readonly=True) as original:
                if original.namespace_uuid != manifest.get("namespace_uuid"):
                    raise FilesystemError("backup namespace mismatch")
            _copy_exclusive(snapshot, destination)
        result = cls.open(destination)
        result.verify()
        return result
