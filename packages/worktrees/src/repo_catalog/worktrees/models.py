"""Lossless topology values and genuine observation identities."""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import asdict, dataclass
from uuid import UUID


class WorktreeError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def uuid_value(value: str, version: int) -> str:
    try:
        parsed = UUID(value)
        if str(parsed) != value or parsed.version != version:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise WorktreeError("IDENTITY", f"canonical UUIDv{version} required") from None
    return value


def observation_uuid() -> str:
    value = (time.time_ns() // 1_000_000) << 80
    value |= 7 << 76 | secrets.randbits(12) << 64
    value |= 2 << 62 | secrets.randbits(62)
    return str(UUID(int=value))


def native_path(path: str | bytes | os.PathLike) -> bytes:
    raw = os.fspath(path)
    text = os.fsdecode(raw)
    if not text or "\x00" in text:
        raise WorktreeError("PATH", "nonempty native path required")
    if os.name == "nt":
        drive, tail = os.path.splitdrive(text)
        unc_volume_root = (
            drive.startswith(("\\\\", "//")) and not drive.endswith(":") and not tail
        )
        if drive and not tail.startswith(("/", "\\")) and not unc_volume_root:
            raise WorktreeError("PATH", "drive-relative paths are ambiguous")
    return os.fsencode(os.path.abspath(os.path.normpath(text)))


@dataclass(frozen=True)
class WorktreeEntry:
    root_path: bytes
    git_dir: bytes | None
    common_dir: bytes | None
    head_oid: str | None = None
    branch: bytes | None = None
    bare: bool = False
    locked: bytes | None = None
    prunable: bytes | None = None
    error: str | None = None
    object_format: str | None = None


@dataclass(frozen=True)
class DiscoveryResult:
    namespace_uuid: str | None
    observation_uuid: str
    requested_path: bytes
    common_dir: bytes | None
    entries: tuple[WorktreeEntry, ...]
    status: str
    errors: tuple[str, ...]
    observed_at_us: int


def json_value(value):
    """Include exact bytes without invalid Unicode in JSON consumers."""
    if hasattr(value, "__dataclass_fields__"):
        return json_value(asdict(value))
    if isinstance(value, bytes):
        return {"text": os.fsdecode(value), "hex": value.hex()}
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    return value
