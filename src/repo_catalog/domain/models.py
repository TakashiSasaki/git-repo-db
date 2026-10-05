from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def now() -> str:
    return datetime.now(UTC).isoformat()


class CatalogError(Exception):
    def __init__(
        self, code: str, message: str, details: dict | None = None, retryable=False
    ):
        super().__init__(message)
        self.code, self.details, self.retryable = code, details or {}, retryable


class Waiting(CatalogError):
    pass


@dataclass(frozen=True)
class GitOid:
    algorithm: str
    value: bytes

    @classmethod
    def parse(cls, text: str):
        try:
            algo, value = text.split(":", 1)
            if (
                algo not in ("sha1", "sha256")
                or len(value) != {"sha1": 40, "sha256": 64}[algo]
            ):
                raise ValueError()
            return cls(algo, bytes.fromhex(value))
        except (ValueError, KeyError):
            raise CatalogError(
                "INVALID_ARGUMENT", "OID must be sha1:<40 hex> or sha256:<64 hex>"
            )


@dataclass
class CoverageReport:
    complete_for_requested_scope: bool = True
    missing: list[dict] = field(default_factory=list)
    excluded_by_policy: list[dict] = field(default_factory=list)

    def add(self, kind, reason, **extra):
        self.complete_for_requested_scope = False
        self.missing.append({"kind": kind, "reason": reason, **extra})


@dataclass
class Result:
    data: Any = None
    coverage: CoverageReport | None = field(default_factory=CoverageReport)
    status: str = "complete"
    catalog: dict | None = None
    execution: dict = field(
        default_factory=lambda: {"completed": True, "timed_out": False, "backend": None}
    )
    warnings: list = field(default_factory=list)


@dataclass
class CancellationToken:
    cancelled: bool = False

    def check(self):
        if self.cancelled:
            raise CatalogError(
                "CANCELLED", "Interrupted at a safe checkpoint", retryable=True
            )


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def path_fields(raw: bytes) -> dict:
    try:
        utf8 = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        utf8 = None
    display = raw.decode("utf-8", "backslashreplace")
    display = "".join(c if c.isprintable() else f"\\x{ord(c):02x}" for c in display)
    return {
        "path_b64": base64.b64encode(raw).decode(),
        "path_utf8": utf8,
        "path_display": display,
    }
