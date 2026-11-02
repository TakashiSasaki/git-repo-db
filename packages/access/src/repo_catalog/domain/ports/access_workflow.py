"""Trusted local integration ports; no remotely supplied adapter or grant flag."""

from collections.abc import Callable
from typing import Protocol, TypeVar

from repo_catalog.domain.access_connections import AccessReviewPlan

T = TypeVar("T")


class BoundAccessExecutor(Protocol):
    def evidence(self) -> str:
        """Exact canonical locally measured context; raises when binding is stale."""
        ...

    def invoke(self, operation: Callable[[int], T]) -> T:
        """Trusted callback over a pinned local-directory descriptor, once admitted."""
        ...

    def close(self) -> None: ...


class AccessExecutorFactory(Protocol):
    def bind(self, plan: AccessReviewPlan) -> BoundAccessExecutor: ...
