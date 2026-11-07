"""Git-agnostic native traversal. No file bodies are retained."""

from __future__ import annotations

import hashlib
import os
import stat
import time
from dataclasses import replace
from typing import Iterator

from .models import FileEntry, native_path


def _identity(value):
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _kind(info):
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 1024:
        return "symlink"
    if stat.S_ISDIR(info.st_mode):
        return "directory"
    if stat.S_ISREG(info.st_mode):
        return "file"
    return "special"


def _entry(namespace, scan, root, relative, info):
    kind = _kind(info)
    return FileEntry(
        namespace,
        scan,
        relative,
        os.path.join(root, relative) if relative else root,
        kind,
        info.st_size if kind == "file" else None,
        info.st_mtime_ns,
        getattr(info, "st_birthtime_ns", None),
        info.st_ctime_ns,
        getattr(info, "st_file_attributes", None),
        info.st_mode,
        hash_status="pending" if kind == "file" else "not-applicable",
        observed_us=time.time_ns() // 1000,
    )


def _error(exc):
    # Error class and errno are enough; OS exception strings can contain raw paths.
    return f"{type(exc).__name__}:{getattr(exc, 'errno', None)}"


def _hash_fd(fd, initial):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or _identity(before) != _identity(initial):
        return None, "changed", "changed-before-read"
    digest = hashlib.sha256()
    count = 0
    while chunk := os.read(fd, min(1024 * 1024, before.st_size - count + 1)):
        digest.update(chunk)
        count += len(chunk)
        if count > before.st_size:
            return None, "changed", "changed-during-read"
    after = os.fstat(fd)
    if _identity(before) != _identity(after) or count != before.st_size:
        return None, "changed", "changed-during-read"
    return digest.hexdigest(), "complete", None


def _excluded(path, exclusions):
    value = path
    return any(
        value == x or value.startswith(x + os.fsencode(os.sep)) for x in exclusions
    )


def _excluded_identity(info, identities):
    return (info.st_dev, info.st_ino) in identities


def _windows_open(path, directory=False):
    """Open reparse points themselves and pin a native Windows handle."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    # Do not share deletion: an open directory cannot be replaced during traversal.
    handle = create(
        os.fsdecode(path),
        0x80000000,
        3,
        None,
        3,
        0x00200000 | (0x02000000 if directory else 0),
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close(handle)
        raise


def walk(root, namespace, scan, exclusions=()) -> Iterator[FileEntry]:
    root = native_path(root)
    exclusions = tuple(native_path(p) for p in exclusions)
    identities = set()
    for path in exclusions:
        try:
            info = os.lstat(os.fsdecode(path))
            identities.add((info.st_dev, info.st_ino))
        except OSError:
            pass
    try:
        info = os.lstat(os.fsdecode(root))
        if _kind(info) != "directory":
            raise NotADirectoryError("scan root must be a non-link directory")
        if os.name == "nt":
            yield from _walk_windows(
                root, b"", namespace, scan, exclusions, identities, info
            )
        else:
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if _identity(os.fstat(fd)) != _identity(info):
                    raise OSError("root changed before traversal")
                yield from _walk_posix(
                    root, b"", fd, namespace, scan, exclusions, identities
                )
            finally:
                os.close(fd)
    except OSError as exc:
        yield FileEntry(namespace, scan, b"", root, "unknown", error=_error(exc))


def _walk_posix(root, relative, fd, namespace, scan, exclusions, identities):
    directory = _entry(namespace, scan, root, relative, os.fstat(fd))
    try:
        # scandir(fd) pins traversal to the directory even if its name changes.
        with os.scandir(fd) as iterator:
            for child in iterator:
                name = os.fsencode(child.name)
                rel = os.path.join(relative, name) if relative else name
                absolute = os.path.join(root, rel)
                if _excluded(absolute, exclusions):
                    continue
                entry = None
                try:
                    before = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if _excluded_identity(before, identities):
                        continue
                    entry = _entry(namespace, scan, root, rel, before)
                    if entry.kind == "directory":
                        child_fd = os.open(
                            name,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd,
                        )
                        try:
                            if _identity(os.fstat(child_fd)) != _identity(before):
                                raise OSError("directory changed before traversal")
                            yield from _walk_posix(
                                root,
                                rel,
                                child_fd,
                                namespace,
                                scan,
                                exclusions,
                                identities,
                            )
                        finally:
                            os.close(child_fd)
                        continue
                    if entry.kind == "file":
                        child_fd = os.open(
                            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
                        )
                        try:
                            digest, status, error = _hash_fd(child_fd, before)
                            current = os.stat(name, dir_fd=fd, follow_symlinks=False)
                            if _identity(current) != _identity(before):
                                digest, status, error = None, "changed", "path-replaced"
                            entry = replace(
                                entry, sha256=digest, hash_status=status, error=error
                            )
                        finally:
                            os.close(child_fd)
                    elif entry.kind == "symlink":
                        entry = replace(entry, link_target=os.readlink(name, dir_fd=fd))
                    yield entry
                except OSError as exc:
                    if entry is None:
                        yield FileEntry(
                            namespace, scan, rel, absolute, "unknown", error=_error(exc)
                        )
                    else:
                        yield replace(
                            entry,
                            sha256=None,
                            hash_status="error"
                            if entry.kind == "file"
                            else "not-applicable",
                            error=_error(exc),
                        )
        after = os.fstat(fd)
        current = os.stat(
            root if not relative else os.path.join(root, relative),
            follow_symlinks=False,
        )
        if (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino):
            directory = replace(directory, error="directory-path-changed")
        elif (after.st_mtime_ns, after.st_ctime_ns) != (
            directory.mtime_ns,
            directory.ctime_ns,
        ):
            directory = replace(directory, error="directory-changed-during-scan")
    except OSError as exc:
        directory = replace(directory, error=_error(exc))
    yield directory


def _walk_windows(root, relative, namespace, scan, exclusions, identities, before):
    absolute = os.path.join(root, relative) if relative else root
    directory = _entry(namespace, scan, root, relative, before)
    fd = None
    try:
        fd = _windows_open(absolute, directory=True)
        if _kind(os.fstat(fd)) != "directory" or _identity(os.fstat(fd)) != _identity(
            before
        ):
            raise OSError("directory changed before traversal")
        with os.scandir(os.fsdecode(absolute)) as iterator:
            for child in iterator:
                rel = os.path.join(relative, os.fsencode(child.name))
                path = os.path.join(root, rel)
                if _excluded(path, exclusions):
                    continue
                entry = None
                try:
                    # Windows DirEntry.stat has zero st_dev/st_ino; path stat
                    # supplies the real identity to compare with the pinned handle.
                    info = os.lstat(os.fsdecode(path))
                    if _excluded_identity(info, identities):
                        continue
                    entry = _entry(namespace, scan, root, rel, info)
                    if entry.kind == "directory":
                        yield from _walk_windows(
                            root, rel, namespace, scan, exclusions, identities, info
                        )
                        continue
                    if entry.kind == "file":
                        child_fd = _windows_open(path)
                        try:
                            digest, status, error = _hash_fd(child_fd, info)
                            if _identity(os.lstat(os.fsdecode(path))) != _identity(
                                info
                            ):
                                digest, status, error = None, "changed", "path-replaced"
                            entry = replace(
                                entry, sha256=digest, hash_status=status, error=error
                            )
                        finally:
                            os.close(child_fd)
                    elif entry.kind == "symlink":
                        try:
                            entry = replace(
                                entry,
                                link_target=os.fsencode(os.readlink(os.fsdecode(path))),
                            )
                        except OSError:
                            # Junction and other reparse types need not have a readlink target.
                            pass
                    yield entry
                except OSError as exc:
                    if entry is None:
                        yield FileEntry(
                            namespace, scan, rel, path, "unknown", error=_error(exc)
                        )
                    else:
                        yield replace(
                            entry,
                            sha256=None,
                            hash_status="error"
                            if entry.kind == "file"
                            else "not-applicable",
                            error=_error(exc),
                        )
        after = os.fstat(fd)
        current = os.lstat(os.fsdecode(absolute))
        if (after.st_dev, after.st_ino) != (current.st_dev, current.st_ino):
            directory = replace(directory, error="directory-path-changed")
        elif (after.st_mtime_ns, after.st_ctime_ns) != (
            before.st_mtime_ns,
            before.st_ctime_ns,
        ):
            directory = replace(directory, error="directory-changed-during-scan")
    except OSError as exc:
        directory = replace(directory, error=_error(exc))
    finally:
        if fd is not None:
            os.close(fd)
    yield directory
