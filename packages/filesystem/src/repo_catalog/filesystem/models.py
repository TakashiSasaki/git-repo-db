"""Small independent filesystem values; paths retain native filesystem bytes."""

from __future__ import annotations

import ntpath
import os
import secrets
import time
import uuid
from dataclasses import dataclass


class FilesystemError(ValueError):
    """A catalog operation could not fulfill its declared scope."""


def occurrence_uuid() -> str:
    """UUIDv7 for a genuine scan occurrence, independent of storage row numbers."""
    return str(
        uuid.UUID(
            int=(time.time_ns() // 1_000_000) << 80
            | 7 << 76
            | secrets.randbits(12) << 64
            | 2 << 62
            | secrets.randbits(62)
        )
    )


def native_path(path: str | bytes | os.PathLike) -> bytes:
    text = os.fsdecode(path)
    if os.name == "nt":
        drive, tail = ntpath.splitdrive(text)
        if (
            drive
            and not drive.startswith(("\\\\", "//"))
            and not tail.startswith(("/", "\\"))
        ):
            raise FilesystemError("Windows drive-relative paths are ambiguous")
    return os.fsencode(os.path.abspath(os.path.normpath(os.fsdecode(path))))


@dataclass(frozen=True)
class ScanResult:
    namespace_uuid: str
    scan_uuid: str
    root_path: bytes
    status: str
    entries: int
    errors: int
    enumeration_complete: bool = False
    hashing_complete: bool = False


@dataclass(frozen=True)
class FileEntry:
    namespace_uuid: str
    scan_uuid: str
    relative_path: bytes
    absolute_path: bytes
    kind: str
    size: int | None = None
    mtime_ns: int | None = None
    birthtime_ns: int | None = None
    ctime_ns: int | None = None
    attributes: int | None = None
    mode: int | None = None
    sha256: str | None = None
    hash_status: str = "not-applicable"
    error: str | None = None
    link_target: bytes | None = None
    observed_us: int | None = None


@dataclass(frozen=True)
class ExportResult:
    written: int
    skipped: int
