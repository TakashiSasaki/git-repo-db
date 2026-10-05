import ctypes
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "docs/schema-hardening"
PARSER_VERSION = "p2-archive/1"


class ConversionError(Exception):
    def __init__(self, code, severity="blocking"):
        self.code, self.severity = code, severity
        super().__init__(code)  # Never print legacy values/paths/credentials.


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def reject_json_constant(value):
    raise ValueError("Non-JSON numeric constant")


def strict_json(value):
    return json.loads(value, parse_constant=reject_json_constant)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def now():
    """Converter event time ONLY; never a substitute for a source observation."""
    return datetime.now(UTC).isoformat()


def stat_identity(path):
    s = path.stat(follow_symlinks=False)
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def require_local_filesystem(path):
    # Remote/FUSE filesystems can acquire data through kernel/filesystem helpers,
    # outside a process's socket filter. P2 input/output must be local storage.
    buffer = ctypes.create_string_buffer(256)
    if ctypes.CDLL(None).statfs(os.fsencode(path), buffer) != 0:
        raise ConversionError("FILESYSTEM_IDENTIFICATION_FAILED")
    kind = ctypes.c_ulong.from_buffer(buffer).value
    if kind not in {
        0xEF53,
        0x58465342,
        0x9123683E,
        0x794C7630,
        0x01021994,
        0x858458F6,
        0x2FC12FC1,
    }:
        raise ConversionError("NONLOCAL_OR_UNSUPPORTED_FILESYSTEM")
