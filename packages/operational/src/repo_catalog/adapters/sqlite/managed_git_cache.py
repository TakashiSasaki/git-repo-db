"""Finite managed Git cache policy over checkpointed Operational progress.

These are temporary acquisition inputs, never a file-body archive or authority.
Reuse offers an unverified candidate requiring normal Git verification. Missing
Operational progress or changed file metadata means reuse unavailable. Only
explicitly registered managed Git directories can become GC candidates.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import ExitStack, contextmanager
from pathlib import Path

from repo_catalog.adapters.sqlite.acquisition import OperationalAcquisitionLedger
from repo_catalog.adapters.sqlite.catalog_runtime import (
    catalog_completion,
    catalog_gate,
)
from repo_catalog.adapters.sqlite.operational_rows import ROW_TYPES
from repo_catalog.domain.p1_coordination import CoordinationError, RequestIdentity
from repo_catalog.domain.shared_values import encode, uuid4_value
from repo_catalog.domain.time import now_us as clock_us
from repo_catalog.domain.time import validate_required_observation_us

_PREFIX = "managed-git-cache"


def _space_reservation(scope, value):
    if (
        type(scope) is not list
        or len(scope) != 3
        or scope[:2] != [_PREFIX, "space"]
        or type(value) is not dict
    ):
        raise ValueError("invalid cache reservation")
    uuid4_value(scope[2])
    if (
        set(value) != {"reserved_bytes", "baseline_used_bytes", "state"}
        or value["state"] not in ("reserved", "released")
        or any(
            type(value[key]) is not int or value[key] < 0
            for key in ("reserved_bytes", "baseline_used_bytes")
        )
        or value["state"] == "released"
        and value["reserved_bytes"]
    ):
        raise ValueError("invalid cache reservation")
    return value["reserved_bytes"]


def reserved_disk_bytes(db, request):
    """Inspect a request after its caller verifies the accounting checkpoint.

    The caller owns the transaction. No filesystem access, allocation mutation
    or ledger opening occurs here, so completion can refuse atomically.
    """
    total = 0
    try:
        for row in db.execute(
            "SELECT continuation_scope_json,cursor_json FROM request_continuations "
            "WHERE request_origin_uuidv4=? AND request_uuidv4=? "
            "AND json_extract(continuation_scope_json,'$[0]')=? "
            "AND json_extract(continuation_scope_json,'$[1]')='space'",
            (*request.values(), _PREFIX),
        ):
            total += _space_reservation(json.loads(row[0]), json.loads(row[1]))
    except (ValueError, TypeError, KeyError) as error:
        raise CoordinationError("CONTINUATION_UNAVAILABLE", "cache") from error
    return total


def _relative(value):
    supplied = os.fspath(value)
    if len(supplied) > 4096:
        raise ValueError("finite managed cache path limit")
    raw = os.fsencode(supplied)
    if len(raw) > 4096:
        raise ValueError("finite managed cache path limit")
    parts = tuple(raw.split(b"/"))
    if (
        not raw
        or b"\0" in raw
        or os.path.isabs(raw)
        or any(part in (b"", b".", b"..") for part in parts)
        or b"\\" in raw
    ):
        raise ValueError("relative managed cache path required")
    return parts


@contextmanager
def _descend(root, parts):
    fd = os.dup(root)
    try:
        for name in parts:
            child = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _tree(root, parts, limit):
    nodes = []

    def visit(parent, prefix, depth):
        if depth > 64:
            raise ValueError("finite cache nesting limit")
        names = []
        with os.scandir(parent) as listing:
            for entry in listing:
                if len(nodes) + len(names) >= limit:
                    raise ValueError("finite cache entry limit")
                names.append(os.fsencode(entry.name))
        for raw in sorted(names):
            info = os.stat(raw, dir_fd=parent, follow_symlinks=False)
            path = (*prefix, raw)
            nodes.append(
                (
                    path,
                    info.st_dev,
                    info.st_ino,
                    info.st_mode,
                    info.st_size,
                    info.st_mtime_ns,
                )
            )
            if len(nodes) > limit:
                raise ValueError("finite cache entry limit")
            if stat.S_ISDIR(info.st_mode):
                with _descend(parent, (raw,)) as child:
                    visit(child, path, depth + 1)

    with _descend(root, parts) as fd:
        visit(fd, (), 0)
    return nodes


def _signature(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns]


def _capture(root, parts, limit):
    with _descend(root, parts) as entry:
        identity = _signature(os.fstat(entry))
        nodes = _tree(entry, (), limit)
        if _signature(os.fstat(entry)) != identity:
            raise ValueError("managed cache changed during metadata capture")
    with _descend(root, parts) as named:
        if _signature(os.fstat(named)) != identity:
            raise ValueError("managed cache root changed during metadata capture")
    return identity, nodes


def _preflight(root, parts, identity, nodes):
    # Check every target before the first unlink. A current path name alone
    # grants no deletion right to a replacement or changed managed tree.
    with _descend(root, parts) as entry:
        if _signature(os.fstat(entry)) != identity:
            raise ValueError("managed cache root changed")
        for path, *expected in nodes:
            with _descend(entry, path[:-1]) as parent:
                if (
                    _signature(os.stat(path[-1], dir_fd=parent, follow_symlinks=False))
                    != expected
                ):
                    raise ValueError("managed cache target changed")


def _inventory(nodes):
    return hashlib.sha256(
        encode([[b"/".join(path).hex(), *values] for path, *values in nodes]).encode(
            "ascii"
        )
    ).hexdigest()


class ManagedGitCache:
    def __init__(
        self, directory, *, max_bytes, min_free_bytes=0, ttl_seconds, max_entries=10000
    ):
        if (
            any(
                type(value) is not int or value < 0
                for value in (max_bytes, min_free_bytes, ttl_seconds)
            )
            or type(max_entries) is not int
            or max_entries <= 0
        ):
            raise ValueError("finite nonnegative cache bounds required")
        self.directory = Path(directory).resolve()
        self.root = self.directory / "cache"
        self.max_bytes, self.min_free_bytes = max_bytes, min_free_bytes
        self.ttl_us, self.max_entries = ttl_seconds * 1_000_000, max_entries

    def _stop(self):
        if (self.directory / "p1-recovery-stop.json").exists():
            raise CoordinationError("RECOVERY_REQUIRED", "catalog")

    @contextmanager
    def _open(self):
        self._stop()
        if not (self.directory / "operational.sqlite3").is_file():
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "cache")
        with (
            catalog_gate(self.directory, exclusive=True),
            OperationalAcquisitionLedger(self.directory) as store,
        ):
            try:
                self.root.lstat()
            except FileNotFoundError:
                fd = None
            else:
                fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                self._stop()
                yield store, fd
            finally:
                if fd is not None:
                    os.close(fd)

    @contextmanager
    def _checked(self, request, attempt=None, *, write=False):
        with self._open() as (store, fd), ExitStack() as completion:
            with store.work_ledger._checked(
                request, attempt, write=write
            ) as checkpoint:
                yield store, fd, checkpoint
                completion.enter_context(catalog_completion(self.directory))
                self._stop()
                if (
                    store.work_ledger._stat_identity()
                    != store.work_ledger._file_identity
                ):
                    raise CoordinationError("CONTINUATION_UNAVAILABLE", "cache")

    def _checkpoint(self, ledger, request):
        row = ledger.db.execute(
            "SELECT request_scope_json FROM acquisition_requests WHERE request_origin_uuidv4=? AND request_uuidv4=?",
            request.values(),
        ).fetchone()
        saved = ledger.db.execute(
            "SELECT cursor_json FROM request_continuations WHERE request_origin_uuidv4=? AND request_uuidv4=? AND continuation_scope_json=?",
            (*request.values(), ledger._CHECKPOINT_SCOPE),
        ).fetchone()
        if row is None or saved is None:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "cache")
        try:
            checkpoint = json.loads(saved[0])
            ledger._check_inventory(request, row[0], checkpoint)
            return checkpoint
        except (ValueError, TypeError, KeyError) as error:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "cache") from error

    def _slots(self, ledger):
        rows = ledger.db.execute(
            "SELECT * FROM request_continuations WHERE json_extract(continuation_scope_json,'$[0]')=? LIMIT ?",
            (_PREFIX, self.max_entries + 1),
        ).fetchall()
        if len(rows) > self.max_entries:
            raise ValueError("finite cache progress limit")
        result, checked = [], set()
        try:
            for row in rows:
                item = ROW_TYPES["request_continuations"].from_record(row)
                request = RequestIdentity(
                    item.request_origin_uuidv4, item.request_uuidv4
                )
                if request not in checked:
                    self._checkpoint(ledger, request)
                    checked.add(request)
                scope, value = (
                    json.loads(item.continuation_scope_json),
                    json.loads(item.cursor_json),
                )
                if (
                    type(scope) is not list
                    or len(scope) != 3
                    or scope[1] not in ("space", "entry")
                    or type(value) is not dict
                ):
                    raise ValueError("invalid managed cache progress")
                if scope[1] == "space":
                    _space_reservation(scope, value)
                else:
                    if (
                        set(value)
                        != {
                            "path_hex",
                            "last_used_us",
                            "state",
                            "inventory_sha256",
                            "root_identity",
                        }
                        or value["path_hex"] != scope[2]
                        or value["state"] not in ("available", "missing")
                    ):
                        raise ValueError("invalid managed cache entry")
                    identity = value["root_identity"]
                    if (
                        type(identity) is not list
                        or len(identity) != 5
                        or any(type(part) is not int for part in identity)
                        or any(part < 0 for part in identity[:4])
                        or not stat.S_ISDIR(identity[2])
                    ):
                        raise ValueError("invalid registered cache root identity")
                    raw_path = bytes.fromhex(scope[2])
                    _relative(raw_path)
                    if raw_path.hex() != scope[2]:
                        raise ValueError("noncanonical cache path")
                    validate_required_observation_us(value["last_used_us"])
                    digest = value["inventory_sha256"]
                    if (
                        type(digest) is not str
                        or len(digest) != 64
                        or any(char not in "0123456789abcdef" for char in digest)
                    ):
                        raise ValueError("invalid cache metadata digest")
                result.append((request, item.continuation_scope_json, scope, value))
        except (ValueError, TypeError, KeyError) as error:
            raise CoordinationError("CONTINUATION_UNAVAILABLE", "cache") from error
        return result

    def _usage(self, fd):
        if fd is None:
            parent = os.open(
                self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            try:
                disk = os.fstatvfs(parent)
            finally:
                os.close(parent)
            return 0, disk.f_bavail * disk.f_frsize
        nodes = _tree(fd, (), self.max_entries)
        used = sum(node[4] for node in nodes if stat.S_ISREG(node[3]))
        disk = os.fstatvfs(fd)
        return used, disk.f_bavail * disk.f_frsize

    def status(self):
        with self._open() as (store, fd):
            store.db.execute("BEGIN")
            try:
                slots = self._slots(store.work_ledger)
                used, free = self._usage(fd)
                return {
                    "used_bytes": used,
                    "free_bytes": free,
                    "max_bytes": self.max_bytes,
                    "min_free_bytes": self.min_free_bytes,
                    "ttl_seconds": self.ttl_us // 1_000_000,
                    "reservations": [
                        {"request": owner.values(), "attempt_uuidv4": scope[2], **value}
                        for owner, _, scope, value in slots
                        if scope[1] == "space"
                    ],
                    "entries": [
                        value for _, _, scope, value in slots if scope[1] == "entry"
                    ],
                }
            finally:
                store.db.rollback()

    def reserve(self, request, attempt, amount):
        uuid4_value(attempt)
        if type(amount) is not int or amount < 0:
            raise ValueError("finite nonnegative disk reservation required")
        scope = encode([_PREFIX, "space", attempt])
        with self._checked(request, attempt, write=True) as (store, fd, checkpoint):
            other = sum(
                value["reserved_bytes"]
                for owner, slot, key, value in self._slots(store.work_ledger)
                if key[1] == "space"
                and value["state"] == "reserved"
                and (owner != request or slot != scope)
            )
            used, free = self._usage(fd)
            if (
                used + other + amount > self.max_bytes
                or free - other - amount < self.min_free_bytes
            ):
                raise CoordinationError("CAPACITY_WAIT", "cache")
            value = {
                "reserved_bytes": amount,
                "baseline_used_bytes": used,
                "state": "reserved",
            }
            store.work_ledger._put_continuation(
                request, checkpoint, scope, encode(value)
            )
            return {
                "request": request.values(),
                "attempt_uuidv4": attempt,
                **value,
                "used_bytes": used,
                "free_bytes": free,
                "reserved_elsewhere": other,
            }

    def monitor(self, request, attempt):
        uuid4_value(attempt)
        scope = encode([_PREFIX, "space", attempt])
        with self._checked(request, attempt) as (store, fd, _checkpoint):
            slots = self._slots(store.work_ledger)
            own = [
                value
                for owner, slot, key, value in slots
                if owner == request and slot == scope and value["state"] == "reserved"
            ]
            if len(own) != 1:
                raise CoordinationError("CAPACITY_RESERVATION_UNAVAILABLE", "cache")
            used, free = self._usage(fd)
            other = sum(
                value["reserved_bytes"]
                for owner, slot, key, value in slots
                if key[1] == "space"
                and value["state"] == "reserved"
                and (owner != request or slot != scope)
            )
            if (
                used + other > self.max_bytes
                or free - other < self.min_free_bytes
                or used - own[0]["baseline_used_bytes"] > own[0]["reserved_bytes"]
            ):
                raise CoordinationError("CAPACITY_WAIT", "cache")
            return {
                "used_bytes": used,
                "free_bytes": free,
                "reserved_elsewhere": other,
                **own[0],
            }

    def release(self, request, attempt):
        uuid4_value(attempt)
        scope = encode([_PREFIX, "space", attempt])
        with self._checked(request, attempt, write=True) as (store, _fd, checkpoint):
            matches = [
                value
                for owner, slot, key, value in self._slots(store.work_ledger)
                if owner == request and slot == scope and key[1] == "space"
            ]
            if len(matches) != 1:
                raise CoordinationError("CAPACITY_RESERVATION_UNAVAILABLE", "cache")
            value = {**matches[0], "reserved_bytes": 0, "state": "released"}
            store.work_ledger._put_continuation(
                request, checkpoint, scope, encode(value)
            )
            return value

    def register(self, request, attempt, relative_path, last_used_us):
        validate_required_observation_us(last_used_us)
        uuid4_value(attempt)
        parts = _relative(relative_path)
        path_hex = b"/".join(parts).hex()
        scope = encode([_PREFIX, "entry", path_hex])
        with self._checked(request, attempt, write=True) as (store, fd, checkpoint):
            if fd is None:
                raise ValueError("managed Git cache directory is absent")
            slots = self._slots(store.work_ledger)
            for _, _, key, value in slots:
                if key[1] == "entry" and value["path_hex"] != path_hex:
                    other = _relative(bytes.fromhex(value["path_hex"]))
                    if parts[: len(other)] == other or other[: len(parts)] == parts:
                        raise ValueError("managed cache registrations cannot overlap")
            with _descend(fd, parts) as entry:
                head = os.stat(b"HEAD", dir_fd=entry, follow_symlinks=False)
                if not stat.S_ISREG(head.st_mode):
                    raise ValueError(
                        "a managed Git directory with a regular HEAD is required"
                    )
            identity, nodes = _capture(fd, parts, self.max_entries)
            digest = _inventory(nodes)
            for _, _, key, old in slots:
                if (
                    key[1] == "entry"
                    and old["path_hex"] == path_hex
                    and old["state"] == "available"
                    and (
                        old["root_identity"] != identity
                        or old["inventory_sha256"] != digest
                    )
                ):
                    raise ValueError(
                        "registered cache changed; use a fresh managed generation"
                    )
            previous = [
                value
                for owner, slot, key, value in slots
                if owner == request and slot == scope
            ]
            if previous and last_used_us < previous[0]["last_used_us"]:
                raise ValueError("cache last-use time cannot move backwards")
            value = {
                "path_hex": path_hex,
                "last_used_us": last_used_us,
                "state": "available",
                "inventory_sha256": digest,
                "root_identity": identity,
            }
            store.work_ledger._put_continuation(
                request, checkpoint, scope, encode(value)
            )
            return value

    touch = register

    def reuse(self, relative_path):
        try:
            return self._reuse(relative_path)
        except CoordinationError as error:
            if error.code == "CONTINUATION_UNAVAILABLE":
                return {"availability": "reuse_unavailable"}
            raise
        except OSError:
            return {"availability": "reuse_unavailable"}

    def _reuse(self, relative_path):
        parts = _relative(relative_path)
        key = b"/".join(parts).hex()
        with self._open() as (store, fd):
            store.db.execute("BEGIN")
            try:
                matches = [
                    value
                    for _, _, scope, value in self._slots(store.work_ledger)
                    if scope[1] == "entry"
                    and value["path_hex"] == key
                    and value["state"] == "available"
                ]
                if not matches or fd is None:
                    return {"availability": "reuse_unavailable"}
                try:
                    identity, nodes = _capture(fd, parts, self.max_entries)
                    inventory = _inventory(nodes)
                except (OSError, ValueError):
                    return {"availability": "reuse_unavailable"}
                current = max(matches, key=lambda value: value["last_used_us"])
                return {
                    "availability": "reuse_candidate"
                    if identity == current["root_identity"]
                    and inventory == current["inventory_sha256"]
                    else "reuse_unavailable",
                    "verification": "Git verification required",
                }
            finally:
                store.db.rollback()

    def collect(self, *, apply=False, now_us=None):
        if type(apply) is not bool:
            raise TypeError("apply must be boolean")
        now = clock_us() if now_us is None else validate_required_observation_us(now_us)
        with self._open() as (store, fd):
            store.db.execute("BEGIN IMMEDIATE")
            try:
                active = store.db.execute(
                    "SELECT count(*) FROM acquisition_requests WHERE state IN ('open','stopped')"
                ).fetchone()[0]
                slots = self._slots(store.work_ledger)
                reservations = sum(
                    value["reserved_bytes"]
                    for _, _, scope, value in slots
                    if scope[1] == "space" and value["state"] == "reserved"
                )
                report = {
                    "protected_requests": active,
                    "reserved_bytes": reservations,
                    "candidates": [],
                    "removed": [],
                    "retained": [],
                    "bytes": 0,
                }
                entries = {}
                for owner, slot, scope, value in slots:
                    if scope[1] == "entry" and value["state"] == "available":
                        entries.setdefault(value["path_hex"], []).append(
                            (owner, slot, value)
                        )
                for path_hex, originals in entries.items():
                    parts = _relative(bytes.fromhex(path_hex))
                    if (
                        active
                        or reservations
                        or now - max(value["last_used_us"] for _, _, value in originals)
                        < self.ttl_us
                    ):
                        report["retained"].append(path_hex)
                        continue
                    if fd is None:
                        report["retained"].append(path_hex)
                        continue
                    try:
                        identity, nodes = _capture(fd, parts, self.max_entries)
                    except (OSError, ValueError):
                        report["retained"].append(path_hex)
                        continue
                    digest = _inventory(nodes)
                    if any(
                        value["root_identity"] != identity
                        or value["inventory_sha256"] != digest
                        for _, _, value in originals
                    ):
                        report["retained"].append(path_hex)
                        continue
                    if any(
                        not (stat.S_ISREG(node[3]) or stat.S_ISDIR(node[3]))
                        for node in nodes
                    ):
                        report["retained"].append(path_hex)
                        continue
                    report["candidates"].append(path_hex)
                    report["bytes"] += sum(
                        node[4] for node in nodes if stat.S_ISREG(node[3])
                    )
                    if apply:
                        _preflight(fd, parts, identity, nodes)
                        for path, device, inode, mode, size, _mtime in sorted(
                            nodes, key=lambda node: len(node[0]), reverse=True
                        ):
                            with _descend(fd, parts) as named:
                                if _signature(os.fstat(named))[:3] != identity[:3]:
                                    raise ValueError(
                                        "registered cache root changed during collection"
                                    )
                            with _descend(fd, (*parts, *path[:-1])) as parent:
                                info = os.stat(
                                    path[-1], dir_fd=parent, follow_symlinks=False
                                )
                                if (
                                    (info.st_dev, info.st_ino, info.st_mode)
                                    != (device, inode, mode)
                                    or stat.S_ISREG(mode)
                                    and (info.st_size, info.st_mtime_ns)
                                    != (size, _mtime)
                                ):
                                    raise ValueError("cache changed during collection")
                                (os.rmdir if stat.S_ISDIR(mode) else os.unlink)(
                                    path[-1], dir_fd=parent
                                )
                        with _descend(fd, parts) as named:
                            if _signature(os.fstat(named))[:3] != identity[:3]:
                                raise ValueError(
                                    "registered cache root changed during collection"
                                )
                        with _descend(fd, parts[:-1]) as parent:
                            os.rmdir(parts[-1], dir_fd=parent)
                        for owner, slot, value in originals:
                            checkpoint = self._checkpoint(store.work_ledger, owner)
                            store.work_ledger._put_continuation(
                                owner,
                                checkpoint,
                                slot,
                                encode({**value, "state": "missing"}),
                            )
                            store.work_ledger._save_checkpoint(owner, checkpoint)
                        report["removed"].append(path_hex)
                all_nodes = [] if fd is None else _tree(fd, (), self.max_entries)
                registered = [_relative(bytes.fromhex(key)) for key in entries]
                report["retained_unregistered"] = [
                    b"/".join(path).hex()
                    for path, *_ in all_nodes
                    if not any(
                        path[: len(base)] == base or base[: len(path)] == path
                        for base in registered
                    )
                ]
                with catalog_completion(self.directory):
                    self._stop()
                    if (
                        store.work_ledger._stat_identity()
                        != store.work_ledger._file_identity
                    ):
                        raise CoordinationError("CONTINUATION_UNAVAILABLE", "cache")
                    store.db.commit()
                return report
            except BaseException:
                store.db.rollback()
                raise
