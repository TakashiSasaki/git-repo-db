"""Access maintenance values: configuration continuity is not execution authority."""

from __future__ import annotations

from dataclasses import dataclass

from repo_catalog.domain.access_registry import (
    INT64_MAX,
    AccessRegistryError,
    AccessScope,
    ScopeLocatorRegistration,
    scope_uuid,
)


@dataclass(frozen=True)
class AccessBackupLimits:
    max_bytes: int = 256 * 1024 * 1024
    max_rows: int = 100_000
    timeout_seconds: int = 60

    def __post_init__(self) -> None:
        for value in (self.max_bytes, self.max_rows, self.timeout_seconds):
            if type(value) is not int or not 1 <= value <= INT64_MAX:
                raise AccessRegistryError(
                    "LIMIT", "positive finite integer limits required"
                )


@dataclass(frozen=True)
class ScopeFork:
    source_scope_uuidv4: str
    target_scope: AccessScope
    registration: ScopeLocatorRegistration

    def __post_init__(self) -> None:
        scope_uuid(self.source_scope_uuidv4)
        if (
            type(self.target_scope) is not AccessScope
            or type(self.registration) is not ScopeLocatorRegistration
        ):
            raise AccessRegistryError("TYPE", "typed fork values required")
        AccessScope(self.target_scope.scope_uuidv4, self.target_scope.display_name)
        ScopeLocatorRegistration(*self.registration.key)
        if self.source_scope_uuidv4 == self.target_scope.scope_uuidv4:
            raise AccessRegistryError(
                "IDENTITY", "an independent fork requires a new Scope UUID"
            )
        if self.target_scope.scope_uuidv4 != self.registration.scope_uuidv4:
            raise AccessRegistryError(
                "IDENTITY", "new registration must belong to the fork"
            )
