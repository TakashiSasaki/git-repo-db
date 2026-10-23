"""Locally supplied authorization authority, independent of Provider evidence.

A lease must serialize policy changes with commit, or make ``check_current``
atomically fence that commit. Callers retain it until their outer commit finishes.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from repo_catalog.domain.context_admission import DependencySet


class AuthorizationLease(Protocol):
    def check_current(self) -> None:
        """Refuse stale/revoked policy; diagnostics must not expose dependencies."""
        ...


class AuthorizationPolicy(Protocol):
    def lease(
        self, principal: object, operation: str, dependencies: DependencySet
    ) -> AbstractContextManager[AuthorizationLease]:
        """Check every dependency and hold the current policy fence through commit."""
        ...
