"""Nominal identities and provenance shared by independent authority readers.

No concrete Core implementation or native-admission code belongs to this module.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID


class CoreFailure(ValueError):
    """Typed failure with the smallest affected subject/scope."""

    def __init__(self, code: str, scope: object, message: str):
        self.code, self.scope = code, scope
        super().__init__(message)


def encode(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def uuid4_value(value: str) -> str:
    try:
        parsed = UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise CoreFailure("IDENTITY", value, "canonical UUIDv4 required") from exc
    return value


@dataclass(frozen=True, order=True)
class OID:
    object_format: Literal["sha1", "sha256"]
    object_oid: str

    def __post_init__(self) -> None:
        width = {"sha1": 40, "sha256": 64}.get(self.object_format)
        if (
            width is None
            or not isinstance(self.object_oid, str)
            or not re.fullmatch(f"[0-9a-f]{{{width}}}", self.object_oid)
        ):
            raise CoreFailure("IDENTITY", self, "full lowercase typed Git OID required")

    @property
    def key(self) -> tuple[str, str]:
        return self.object_format, self.object_oid


@dataclass(frozen=True)
class Provenance:
    source: str
    observation: str
    coordinate: str
    decoder: str
    decoder_version: str
    qualification: Literal["reported", "receiver_intrinsic"] = "reported"

    def __post_init__(self) -> None:
        if self.qualification not in ("reported", "receiver_intrinsic") or any(
            not isinstance(v, str) or not v for v in self.key
        ):
            raise CoreFailure(
                "PROVENANCE", self, "genuine original coordinates required"
            )

    @property
    def key(self) -> tuple[str, ...]:
        return tuple(vars(self).values())

    @property
    def encoded(self) -> str:
        return encode(self.key)
