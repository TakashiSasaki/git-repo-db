"""Atomic publication that never replaces an existing destination."""

import ctypes
import errno
import os
from pathlib import Path

from repo_catalog.domain.models import CatalogError


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish_file(source, destination):
    """Same-filesystem hard-link publication is an atomic no-overwrite operation."""
    try:
        os.link(source, destination)
    except FileExistsError as exc:
        raise CatalogError(
            "DESTINATION_EXISTS", "Publication destination exists"
        ) from exc
    fsync_directory(Path(destination).parent)


def publish_directory(source, destination):
    """Linux renameat2(RENAME_NOREPLACE); never emulate with check-then-rename."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise CatalogError(
            "RUNTIME_UNSUPPORTED", "Atomic no-replace directory publication unavailable"
        )
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if result:
        code = ctypes.get_errno()
        if code in (errno.EEXIST, errno.ENOTEMPTY):
            raise CatalogError(
                "DESTINATION_EXISTS", "Restore destination already exists"
            )
        if code in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise CatalogError(
                "RUNTIME_UNSUPPORTED",
                "Atomic no-replace directory publication unavailable",
            )
        raise OSError(code, os.strerror(code), str(destination))
    fsync_directory(Path(destination).parent)
