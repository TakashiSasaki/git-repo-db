"""Access Scope registry values; no acquisition, credentials or execution authority.

Scope UUID is identity. A locator registration is the direct immutable fact triple,
not an event counter. URI validation is a deliberately finite storage grammar, not
proof of reachability, Scope ownership, approval, or adapter execution support.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import unquote_to_bytes, urlsplit
from typing import Literal
from uuid import UUID

MAX_URI_BYTES = 8192
MAX_LABEL_BYTES = 1024
MAX_PAGE_SIZE = 1000
INT64_MAX = (1 << 63) - 1


class AccessRegistryError(ValueError):
    """Stable category with non-secret diagnostics; never embed supplied locators."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def scope_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise AccessRegistryError("IDENTITY", "canonical UUIDv4 required")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise AccessRegistryError("IDENTITY", "canonical UUIDv4 required") from None
    if parsed.version != 4 or str(parsed) != value:
        raise AccessRegistryError("IDENTITY", "canonical UUIDv4 required")
    return value


def registration_time(value: object) -> int:
    if type(value) is not int or not 1 <= value <= INT64_MAX:
        raise AccessRegistryError("TIME", "positive int64 epoch microseconds required")
    return value


def display_label(value: object) -> str:
    if not isinstance(value, str):
        raise AccessRegistryError("LABEL", "a bounded display label is required")
    try:
        valid = len(value.encode("utf-8")) <= MAX_LABEL_BYTES
    except UnicodeError:
        valid = False
    if not valid or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise AccessRegistryError("LABEL", "invalid display label")
    return value


def page_size(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_PAGE_SIZE:
        raise AccessRegistryError("LIMIT", "page/candidate bound must be in 1..1000")
    return value


def scope_locator(value: object) -> str:
    """Validate without rewriting; allow absolute HTTPS, SSH, and local file URIs.

    Require ASCII URI form (percent escapes may represent non-ASCII path bytes).
    No queries, fragments, passwords, HTTP userinfo, helpers, command syntax,
    backslashes or literal/escaped controls. SSH usernames are non-secret explicit
    coordinates. file authority is empty or localhost. Nothing is dereferenced.
    This does not attempt to detect secrets disguised as ordinary path segments.
    """
    bad = AccessRegistryError("LOCATOR", "unsupported or unsafe Scope locator syntax")
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_URI_BYTES:
        raise bad
    if any(ord(c) <= 32 or ord(c) >= 127 for c in value):
        raise bad
    if not re.fullmatch(r"[A-Za-z0-9._~:/\[\]@!$&'()*+,;=%-]+", value):
        raise bad
    if any(c in value for c in "\\?#") or re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise bad
    if any(b < 32 or b == 127 for b in unquote_to_bytes(value)):
        raise bad
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("https", "ssh", "file"):
            raise bad
        if not value[len(parts.scheme) :].startswith("://"):
            raise bad
        if parts.scheme == "file":
            if parts.netloc.lower() not in ("", "localhost"):
                raise bad
            if not parts.path.startswith("/") or parts.path.startswith("//"):
                raise bad
            return value
        if not parts.hostname or "%" in parts.netloc or parts.password is not None:
            raise bad
        if parts.username is not None:
            if parts.scheme != "ssh" or not re.fullmatch(r"[A-Za-z0-9._~-]+", parts.username):
                raise bad
        authority = parts.netloc.rsplit("@", 1)[-1]
        if authority.startswith("["):
            closing = authority.find("]")
            ipaddress.IPv6Address(authority[1:closing])
            suffix = authority[closing + 1 :]
            if suffix and not re.fullmatch(r":[0-9]+", suffix):
                raise bad
        else:
            if authority.count(":") > 1:
                raise bad
            host, colon, port = authority.partition(":")
            if colon and not re.fullmatch(r"[0-9]+", port):
                raise bad
            if len(host) > 253 or not all(
                re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in host.rstrip(".").split(".")
            ):
                raise bad
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise bad
        if parts.scheme == "ssh" and not parts.path.startswith("/"):
            raise bad
    except (ValueError, UnicodeError):
        raise bad from None
    return value


@dataclass(frozen=True)
class AccessScope:
    scope_uuidv4: str
    display_name: str = ""

    def __post_init__(self) -> None:
        scope_uuid(self.scope_uuidv4)
        display_label(self.display_name)


@dataclass(frozen=True)
class ScopeLocatorRegistration:
    scope_uuidv4: str
    registered_at_us: int
    scope_locator_uri: str

    def __post_init__(self) -> None:
        scope_uuid(self.scope_uuidv4)
        registration_time(self.registered_at_us)
        scope_locator(self.scope_locator_uri)

    @property
    def key(self) -> tuple[str, int, str]:
        return self.scope_uuidv4, self.registered_at_us, self.scope_locator_uri


@dataclass(frozen=True)
class RegistrationPage:
    registrations: tuple[ScopeLocatorRegistration, ...]
    next_cursor: ScopeLocatorRegistration | None


@dataclass(frozen=True)
class RegistrationResult:
    status: Literal["insert", "duplicate"]
    previous_latest_us: int | None
    precedes_latest: bool
