"""P1 coordination values: authority snapshots and explicit acquisition occurrences.

Hashes identify checked snapshot content, never domain rows or completion authority.
Request and attempt UUIDs identify genuine explicitly initiated work occurrences.
"""

import json
from dataclasses import dataclass
from uuid import UUID


class CoordinationError(RuntimeError):
    """A scope-qualified unavailable/invalid authority boundary."""

    def __init__(self, code: str, scope: str, detail: str = ""):
        self.code, self.scope = code, scope
        super().__init__(f"{scope}:{code}: {detail}")


@dataclass(frozen=True)
class SnapshotToken:
    repository_uuidv4: str
    catalog_instance_uuidv4: str
    core_sha256: str
    context_sha256: str

    def encode(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class PairAdmission:
    core_committed: bool
    context_committed: bool


class AdmissionFailure(CoordinationError):
    """Acknowledged failure with the independently committed durable outcome."""

    def __init__(self, outcome: PairAdmission, cause: Exception):
        self.outcome = outcome
        self.cause = cause
        super().__init__("ADMISSION_FAILED", "core+context", str(cause))


@dataclass(frozen=True)
class RequestIdentity:
    request_origin_uuidv4: str
    request_uuidv4: str

    def __post_init__(self):
        for value in self.values():
            parsed = UUID(value)
            if parsed.version != 4 or str(parsed) != value:
                raise ValueError("request occurrence requires canonical UUIDv4")

    def values(self) -> tuple[str, str]:
        return self.request_origin_uuidv4, self.request_uuidv4


@dataclass(frozen=True)
class WorkPermit:
    request: RequestIdentity
    attempt_uuidv4: str
    work_kind: str
    work_coordinate: str
    reserved: int


@dataclass(frozen=True)
class NotesLimits:
    note_bytes: int

    def __post_init__(self):
        if type(self.note_bytes) is not int or not 0 <= self.note_bytes <= 2**63 - 1:
            raise ValueError("finite nonnegative signed int64 note byte limit required")
