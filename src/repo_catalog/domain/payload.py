"""Portable logical payload identity, separate from acquisition identity."""

import re
from dataclasses import dataclass

from repo_catalog.domain.models import CatalogError

REPRESENTATIONS = frozenset({"git-object-raw-v1"})


@dataclass(frozen=True)
class PayloadRef:
    representation: str
    sha256: bytes

    def __post_init__(self):
        if (
            not isinstance(self.representation, str)
            or self.representation not in REPRESENTATIONS
            or not isinstance(self.sha256, bytes)
            or len(self.sha256) != 32
        ):
            raise CatalogError("INVALID_PAYLOAD_REFERENCE", "Invalid payload identity")

    def parameters(self):
        return self.representation, self.sha256

    def as_json(self):
        return {"representation": self.representation, "sha256": self.sha256.hex()}

    @classmethod
    def from_json(cls, value):
        if (
            not isinstance(value, dict)
            or set(value) != {"representation", "sha256"}
            or not isinstance(value["representation"], str)
            or not isinstance(value["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None
        ):
            raise CatalogError("INVALID_PAYLOAD_REFERENCE", "Invalid payload JSON")
        return cls(value["representation"], bytes.fromhex(value["sha256"]))
