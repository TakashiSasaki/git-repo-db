"""Stable P1 ports. Implementations do not imply cross-database atomic COMMIT.

Core-first partial success is intentional. Context units validate portable Core
dependencies before their local COMMIT. Every participating writer, reader,
backup, stop and future activation must use the same catalog gate.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol, TypeVar

from repo_catalog.domain.p1_coordination import (
    PairAdmission,
    RequestIdentity,
    SnapshotToken,
    WorkPermit,
)

Transaction = TypeVar("Transaction", contravariant=True)
Snapshot = TypeVar("Snapshot", covariant=True)


class CoordinationPort(Protocol[Transaction, Snapshot]):
    def admit(
        self,
        core_unit: Callable[[Transaction], None],
        context_unit: Callable[[Transaction], None],
    ) -> PairAdmission: ...

    def snapshots(self) -> AbstractContextManager[Snapshot]: ...

    def stop(self, reason: str) -> None: ...


class SearchAuthorityPort(Protocol):
    """Candidates are advisory until the pinned direct read validates coverage."""

    def candidates(
        self, kind: str, token: SnapshotToken, needle: str
    ) -> set[str] | None: ...

    def read(
        self,
        kind: str,
        token: SnapshotToken,
        needle: str,
        authoritative_scan: Callable[[], dict[str, str]],
    ) -> tuple[str, dict[str, str]]: ...


class AcquisitionWorkPort(Protocol):
    """Discardable state; a missing request cannot automatically resume/reset."""

    def new_request(
        self, request: RequestIdentity, scope: str, limits: dict[str, int]
    ) -> None: ...

    def attempt(
        self, request: RequestIdentity, attempt_uuidv4: str, continuation: str = "{}"
    ) -> None: ...

    def reserve(
        self,
        request: RequestIdentity,
        attempt_uuidv4: str,
        work_kind: str,
        work_coordinate: str,
        upper_bound: int,
    ) -> WorkPermit: ...

    def finish(self, permit: WorkPermit, actual: int) -> None: ...

    def increase_limit(
        self, request: RequestIdentity, work_kind: str, finite_limit: int
    ) -> None: ...
